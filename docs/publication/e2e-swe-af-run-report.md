# Autonomous SWE agent, live end-to-end: enqueue an issue → get a PR

**TL;DR.** A GitHub issue was dropped onto a NATS work-queue. A worker daemon on
a remote host leased it, cloned the repo, ran an LLM software-engineering agent
(plan → code) with every model call routed through a tailnet AI gateway, applied
the change, pushed a branch, and **opened a draft pull request** — the whole thing
testified to a hash-chained audit log. End to end in ~12 seconds of work, proven
on real infrastructure. ([17s asciinema cast](../demo/swe-af-smoke.cast).)

---

## The problem

The `swe_af` agent already existed but ran **one issue at a time** as a GitHub
Actions job. We wanted a **fan-out batch**: drain many independent SWE tasks
concurrently across our own hardware, route every model call through **one shared
gateway** (so the provider key is never distributed), keep the work **bounded**
(disk, RAM, budget) and **auditable**, and surface it live to a console.

## Architecture

```
  enqueue (CLI / control plane)
        │
   NATS JetStream  ── stream SWE_AF_TASKS (work-queue, R-replicated)
        │  durable pull consumer
  ┌─────┴───────────── worker host ─────────────────────────┐
  │  swe-af-orchestrator (Rust, tokio)                       │
  │   bounded pool (semaphore) · disk guard · scratch/task   │
  │   per task:                                              │
  │     lease → git clone → swe-af PLAN → swe-af CODE         │
  │            → apply files → push branch                    │
  │            → broker: gh pr create --draft  (only writer)  │
  │            → eventd hash-chain append + verify            │
  │            → publish swe.af.status.* → console            │
  └──────────────────────────────────────────────────────────┘
        model calls ───────────► tailnet AI gateway (OpenAI-compatible /v1)
                                  identity auth, no client key → provider
```

Two small Rust binaries: `swe-af-orchestrator` (the pool daemon) and
`swe-af-enqueue` (the producer). The existing `swe-af` agent is reused unchanged.

### Design choices that mattered

- **Work-queue, not fan-out RPC.** A JetStream work-queue gives exactly-once-ish
  delivery to one worker, bounded redelivery, and natural backpressure. Adding a
  host = another competing consumer.
- **The agent holds no write credential.** It reads the issue and repo and prints
  JSON. Only the orchestrator's *broker* step writes to GitHub, and only
  `gh pr create --draft`. **Nothing is ever auto-merged.** This mirrors the
  capability mesh: one role holds the write grant.
- **One gateway, no distributed keys.** Model calls go to a tailnet AI gateway
  that authenticates by network identity and injects the provider key
  server-side. Workers send no real API key.
- **Bounded by construction.** A per-task cgroup/disk budget plus a free-space
  guard that pauses intake; each task's scratch is removed on completion.
- **Auditable.** Every node appends to a hash-chained event log; a final `verify`
  gates success.

## The live run

A self-contained smoke issue ("create a one-line marker file") was enqueued. The
captured session:

```
$ swe-af-enqueue --repo <org>/<repo> --issue 192
enqueued 8954bf2f… -> <org>/<repo> (issue #192)

# orchestrator (journald)
orchestrator up  pool=3  subject=swe.af.tasks
task lease  task=8954bf2f  issue=192
  git clone --filter=blob:none … done
  swe-af MODE=plan  -> gateway /v1  deepseek-v4-flash … plan ready
  swe-af MODE=code  -> gateway /v1  deepseek-v4-flash … 1 file
  apply docs/SWE_AF_SMOKE.md ; git push swe-af/issue-192
eventd: chain OK (3 entries)
task done  task=8954bf2f  pr=…/pull/193
```

The agent produced exactly the requested diff:

```diff
+++ b/docs/SWE_AF_SMOKE.md
@@ -0,0 +1 @@
+swe-af smoke run OK
```

Result: a **draft PR**, a clean **eventd chain (3 entries)**, and live
`swe.af.status.*` events — all from one enqueued issue.

## What it proves

The full loop works on real infrastructure: queue → bounded worker → LLM
plan+code through the shared gateway → branch → draft PR → audit. POLA held
(draft only, never merged), the run was cost-tracked, and **no secret was
persisted** (the worker used a credential helper / keyring, not a token file).

## Stack

Rust (tokio, `async-nats` JetStream), NixOS-deployable (systemd slice + unit),
Tailscale-style tailnet AI gateway (OpenAI-compatible, identity auth),
OpenRouter-backed models (`deepseek-v4-flash` for this run), a hash-chained
`eventd` audit log. Worker isolation via cgroups + bubblewrap.

## Engineering notes (the honest part)

- **Caught live, pre-prod:** the gateway's OpenAI API is at the root `/v1`, not
  under the management prefix — found by an actual call returning 404, fixed
  before any production use.
- **No secrets in files:** persisting a token to the worker was deliberately
  avoided; the worker authenticates GitHub via the gh keyring + git credential
  helper, with the service's `HOME` set so it resolves.
- **Backgrounding a daemon over one-shot SSH is a trap** — `systemd-run` (a
  transient unit, journald logs, survives disconnect) is the right tool.

## Reproduce

```bash
# replay the recording
asciinema play docs/demo/swe-af-smoke.cast
# run it live against a deployed orchestrator (opens a fresh draft PR)
NATS_URL=… REPO=<org>/<repo> scripts/demo/swe-af-smoke.sh
```

Deploy guide: `vaked-agents/ci/swe-af-orchestrator/deploy/README.md`.
Design + plan: `docs/superpowers/specs|plans/2026-06-14-swe-af-fanout-batch-*`.

> Identifiers (IPs, tailnet name, emails, provider key) are redacted for
> publication. Internal copies retain the real values.
