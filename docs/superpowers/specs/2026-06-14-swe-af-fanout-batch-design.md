# swe-af fan-out batch — distributed, Aperture-backed, NATS-queued (design)

## Status

Design (2026-06-14). Builds on the Rust `vaked-agents/ci/swe-af` agent and its
lowered `workflow swe_af` (plan -> code -> review -> publish). Supersedes the
GHA-only execution path of
[`2026-06-13-swe-af-gha-runner-design.md`](2026-06-13-swe-af-gha-runner-design.md)
for **batch** runs: instead of one issue per GHA trigger, a pool of sandboxed
workers drains a NATS work-queue, fanning out across owned compute.

## Why

`swe_af` today runs one issue at a time as a GitHub-Actions job. The goal is a
**wide fan-out batch**: drain N independent SWE tasks concurrently across owned
hardware, route every model call through the tailnet **Aperture** AI gateway
(one paid OpenRouter key, never distributed), and keep the work auditable
(eventd) and visible (Sentinel Console). The original framing ("reserve the whole
dev-cx53 instance") was inverted by reality (see Constraints) — cx53 is a packed
services hub, so execution moves **off** cx53 onto dedicated worker hosts.

## Constraints discovered (ground truth, 2026-06-14)

- **dev-cx53** (tailnet `100.105.72.88`, tag:agents/server/homelab/exit): NixOS
  26.05, 16 vCPU EPYC-Rome, **30 GB RAM (~22 GB free), disk 84% full (~46 GB
  free)**, cgroup-v2. Runs ~28 containers (langfuse full stack incl. clickhouse,
  telemetry uptrace/rotel/clickhouse, ollama+litellm, honcho, mempalace,
  agentfield-postgres, chromadb, rustfs, uptime-kuma) + atticd/nginx/nixery/
  dashboards. **Not a batch host** — it is the fleet. Role here: control plane
  only (enqueue + monitor). A "2 GB/4 CPU for services" fence would OOM the fleet;
  rejected.
- **bench-node** (`178.105.245.135`): Ubuntu 26.04, 8 vCPU, 15 GB RAM, **273 GB
  free disk**, cgroup-v2 (all controllers), **bubblewrap 0.11.1 present**, git +
  node + python3 present, **no rust/cargo, no gh**. Already runs a *separate
  Python* `swe_af` agentfield node + local nats + control-plane + postgres.
  **Not on this tailnet today** -> cannot reach Aperture or crabcc-nats until
  joined. Chosen primary worker host.
- **Aperture** (`nixai-base` `100.65.183.126`, `https://nixai-base.tail2870dc.ts.net/aperture`):
  live, OpenAPI 200. Single provider = **OpenRouter** (proxied; real key injected
  server-side). Compatibility flags on: `openai_chat`, `openai_responses`,
  `anthropic_messages`, gemini. Auth = **Tailscale identity, no client API key**.
  Models include `deepseek/deepseek-v4-flash`, `deepseek/deepseek-v4-pro`,
  `anthropic/claude-sonnet-4.6`, `anthropic/claude-opus-4.6`, `openai/gpt-5.3-codex`,
  `qwen/qwen3-235b-a22b-2507`. **Current grants give only `peter.lodri@gmail.com`
  the admin role** — a `tag:agents` user-role + model grant must be added.
- **crabcc-nats** (`100.73.72.35:4222`, tailnet): the central bus the Sentinel
  Console already subscribes to. Reachable from cx53; ACL grant #6 allows
  `tag:agents -> tag:server:4222`.
- **swe-af binary** (`vaked-agents/ci/swe-af`): plan/code modes, honors
  `OPENROUTER_BASE_URL` (default `https://openrouter.ai/api/v1`) and
  `SWE_AF_API_KEY`/`OPENROUTER_API_KEY`, holds **no GH token**, emits full-file
  writes, has input guardrails (`guardrails.rs`). main.rs:60,123 are the model
  base-url/key wiring; main.rs:663 hard-fails if no key present.

## Architecture

```
                      enqueue (CLI / control panel)
                                |
              crabcc-nats JetStream  stream SWE_AF_TASKS  subject swe.af.tasks
                                |  (durable pull consumer: swe-af-workers)
        +-----------------------+------------------------+
        |                                                |
   bench-node (tag:agents)                          [phase 2: GCP c3 pools,
   swe-af-orchestrator (Rust daemon)                 crabcc-ccx33 ...]
        |  pool of K worker slots (cgroup-capped)
        |  per task:
        |    1. lease msg (ack-wait, max-deliver=3)
        |    2. capped scratch dir (disk quota + df guard)
        |    3. git clone --filter=blob:none <repo> @ ref
        |    4. swe-af MODE=plan   -> plan.json   (Aperture)
        |    5. swe-af MODE=code   -> {files,...} (Aperture)
        |    6. apply full files, commit, push swe-af/<task>
        |    7. broker step: gh pr create --draft   (only GH-write actor)
        |    8. review: pr-review agent on the PR    (advisory)
        |    9. eventd append per node + verify
        |   10. publish swe.af.status.<task>.<node> -> Console; ack
        v
   draft PRs on the target repos + eventd audit logs + live Console feed
```

### Components (new unless noted)

1. **Task schema** (NATS message, JSON):
   ```json
   {
     "task_id": "string (uuid)",
     "repo": "owner/name",
     "ref": "main",
     "issue_number": 123,            // optional; OR
     "prompt": "freeform task text", // one of issue_number|prompt required
     "budget": { "tokens": 2000000, "wall_clock_s": 7200, "max_files": 20 },
     "plan_model": "deepseek/deepseek-v4-flash",
     "code_model": "openai/gpt-5.3-codex"
   }
   ```
2. **`swe-af-orchestrator`** (new Rust daemon, `vaked-agents/ci/swe-af-orchestrator/`
   or a `--serve` subcommand on swe-af): JetStream durable pull consumer; bounded
   worker pool (K slots); per-task lifecycle above; emits `swe.af.status.*`.
   Reuses swe-af's parser/guardrails. Holds the **only** `GH_TOKEN` (broker step).
3. **Worker execution** = the existing `swe-af` binary (plan+code), unchanged
   logic, invoked per task by the orchestrator inside a **sandboxd/bwrap cgroup
   cell** (`memory.max`, `pids.max`, `cpu.max`, disk-quota scratch). Model calls
   -> Aperture (env below).
4. **Aperture wiring** (env on workers): `OPENROUTER_BASE_URL=https://nixai-base.tail2870dc.ts.net/aperture/v1`,
   `SWE_AF_API_KEY=tailscale-identity` (placeholder to satisfy the presence check;
   Aperture authenticates by tailnet identity and injects the real key). Models
   are OpenRouter-style FQNs, already valid in Aperture's config.
5. **Disk discipline**: orchestrator owns `/var/lib/swe-af/scratch` capped at
   **20 GB** (XFS project quota or a sized loopback fs); shallow/partial clones
   (`--filter=blob:none`); per-task cleanup; a **df guard** pauses message intake
   when free < 10 GB. Pre-batch reclaim: `docker image prune` + targeted cleanup.
6. **Audit (eventd)**: each node appends to `var/lib/agent-field/eventd/log.jsonl`
   via `python3 -m eventd append`; `eventd verify` gates task success.
7. **Console integration**: `swe.af.status.*` frames flow over crabcc-nats; the
   Sentinel Console Feed/Fleet tabs already render `crabcc.>`/status frames
   (see desktop-console memory) — add the `swe.af.>` subject to the subscriber.

### Infra prerequisites (one-time, before first batch)

- **P1. bench-node onto the tailnet as `tag:agents`**: install tailscale,
  `tailscale up --advertise-tags=tag:agents` (auth key from admin console; admin
  approves). Unblocks Aperture (grant #7) + crabcc-nats (grant #6). *Operator-run
  (interactive auth).* 
- **P2. Aperture grant for `tag:agents`**: add a user-role grant + model glob
  (e.g. `["anthropic/*","deepseek/*","openai/gpt-5.3-codex","qwen/*"]`) to the
  Aperture config via `PUT /aperture/config` (admin). Reversible.
- **P3. bench-node tooling**: install `gh` (broker step); ship the prebuilt
  `swe-af-bin` (no rust toolchain on the box) — reuse `swe-af-build.yml`'s release
  artifact.
- **P4. Disk reclaim** on bench-node + cx53 control-plane dir, then apply the
  20 GB scratch cap.

## Safety / POLA (preserved from the GHA design)

- Workers hold **no GH token**; only the orchestrator's broker step writes to
  GitHub, and only `gh pr create --draft` / `gh pr ready`. **Never auto-merge.**
- Untrusted issue/prompt text passes `guardrails.rs` (secret-redaction +
  injection-defense) before prompt assembly.
- Budgets (tokens / wall-clock / files) map to cgroup caps + Aperture spend
  quota + the file-count clamp. Path traversal (`..`, leading `/`) dropped by the
  existing parser.
- One paid OpenRouter key, server-side in Aperture, never on a worker.

## Scope

**In (v1):** orchestrator daemon, NATS work-queue + status, bench-node worker
pool with cgroup + disk caps, Aperture routing, eventd audit, Console subject,
enqueue CLI, the four infra prerequisites, deploy unit for bench-node (systemd;
**not** NixOS — plain unit + shipped binary).

**Out (phase 2):** GCP Cloud Build c3 pools + crabcc-ccx33 as additional workers
(needs tailscale-in-build or a cx53 Aperture/NATS proxy); autoscaling by queue
depth; the Python `swe_af` agentfield node convergence; cx53 NixOS colmena module
for the control plane.

## Verification

- **Unit**: orchestrator task-lifecycle state machine; task-schema parse;
  df-guard threshold; scratch-quota enforcement. swe-af's existing 7 tests stay
  green.
- **Reachability (post-P1/P2)**: from bench-node, `curl .../aperture/openapi.json`
  == 200 and a 1-token chat completion through Aperture succeeds with no client
  key; NATS `4222` open.
- **End-to-end (1 task)**: enqueue one small self-contained task -> a draft PR
  appears from `swe-af/<task>`, eventd log shows `plan->code->review->publish` and
  `eventd verify` is clean, `swe.af.status.*` frames show in the Console.
- **Fan-out (K tasks)**: enqueue K>pool-size tasks; pool stays <= K slots; disk
  free never < 10 GB (df guard holds); all tasks reach a terminal state
  (PR | graceful no-op | failed-with-audit).
- **Blast-radius**: cx53 fleet metrics flat during a batch (no execution there).

## Open risks

- Aperture concurrency/rate ceiling is OpenRouter-account-bound + quota-bucket
  bound, not a documented hard limit -> start K=6, raise on observed 429 rate.
- bench-node has a *second* Python `swe_af` + local nats; avoid port/name
  collisions (use distinct unit names, distinct scratch path, central crabcc-nats
  not the local one).
- 8 GB usable RAM after the box's existing services -> hard `MemoryMax` per worker
  + systemd-oomd as backstop.
