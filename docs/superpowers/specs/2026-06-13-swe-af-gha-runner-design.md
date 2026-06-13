# swe_af GHA runner — run the lowered workflow for real (design)

## Status

Design (2026-06-13). Realizes the `workflow swe_af` declared in
[`vaked/examples/agentfield-swe.vaked`](../../../vaked/examples/agentfield-swe.vaked)
and lowered to
[`gen/workflow/swe_af.json`](../../../vaked/examples/lowering-agentfield/gen/workflow/swe_af.json).
Relates to [#27](https://github.com/peterlodri-sec/vaked-base/issues/27) (define
`workflow`) and the agent fleet (`vaked-agents/`). Convention: subsystem =
design → plan → impl; this is the design.

## Why

`swe_af` lowers to a JSON DAG and stops — nothing runs it. The intended target,
`dev-cx53`'s agentfield control panel, is unreachable from the web-session sandbox
(no `ssh`/`tailscale`/key; egress allowlist blocks the tailnet-only host). The
**reachable** trigger is the one the spec already declares —
`on = "github.issue.labeled:agent"` — so we materialize `swe_af` as a GitHub-Actions
pipeline. This closes the declare → lower → **run** loop on infra we can drive, and
reuses the existing adk-rust/OpenRouter fleet. The colmena deploy to `dev-cx53` is a
documented follow-up, not this slice.

## Design

**Single source of truth.** `swe-af.yml` reads `gen/workflow/swe_af.json` for the
eventd log path and `maxDepth`, so the run is driven by what Vaked emitted, not a
hand-copied DAG.

**Node → execution, preserving the mesh's POLA.** In `agentfield-swe.vaked`, mesh
nodes hold attenuated capabilities; only `broker` holds `mcp.github_write`.

| node | mesh caps | impl | write boundary |
|---|---|---|---|
| `plan` | planner · `fs.repo_ro` | `vaked-swe-af MODE=plan` → JSON plan | read-only |
| `code` | coder · `fs.repo_rw` | `vaked-swe-af MODE=code` → full-file writes; **shell** writes+commits | agent emits, shell applies |
| `review` | reviewer · `fs.repo_ro` | reuse the **pr-review** agent on the opened PR | advisory comment |
| `publish` | broker · `mcp.github_write` | shell `gh pr create` + `gh pr ready` | the only GitHub write |

The `vaked-swe-af` binary holds **no `GH_TOKEN`** — it reads the issue (`gh issue
view`) and repo (read-only tools) and prints JSON. The workflow shell is the
`fs.repo_rw`/`mcp.github_write` actor. The PR is opened **draft** as the substrate
for the review node, then the broker marks it **ready** as the publish step.

**Full-file writes, not diffs.** The `code` node returns `{path, content}` whole
files — far more robust to apply than LLM patches. The parser drops unsafe paths
(`..`, leading `/`), clamps content size, and caps file count (`budget` discipline).

**Audit spine (eventd).** Every node appends to the lowered log
(`var/lib/agent-field/eventd/log.jsonl`) via `python3 -m eventd append`; a final
`eventd verify` gates the run and the log is uploaded as an artifact. This is the
"testifies" leg for the SWE loop.

**Budget.** `budget swe` (tokens 2M / wallClock 2h / toolCalls 400) maps to job
`timeout-minutes`, per-mode `max_output_tokens`/reasoning effort, and the file cap.

## Safety

Autonomous code+PR is gated hard: only the **`agent` label**, applied by the **repo
owner** (`github.event.sender.login == github.repository_owner`), with
`OPENROUTER_API_KEY` present, triggers a run (else graceful no-op). PRs are **never
auto-merged** — output is a normal PR for human + pr-review review. Untrusted issue
text passes the fleet's input guardrails (secret-redaction + injection-defense) and
is sanitized before being baked into prompts. Graceful degradation: no files → issue
comment with the plan; no net diff → stop; review failure is non-blocking.

## Components

- `vaked-agents/ci/swe-af/` — the Rust agent (plan/code), sibling to `pr-review`.
- `.github/workflows/swe-af.yml` — the DAG orchestration + eventd + safety gate.
- `.github/workflows/swe-af-build.yml` — rolling prebuilt `swe-af-bin` release.
- `.github/labels.yml` — the `agent` trigger label.
- `Taskfile.yml: swe-af` — hermetic build + unit-test target.

## Verification

- CI: `swe-af-build.yml` compiles the crate; `cargo test` (7 unit tests) green;
  existing `spec-tests` / `vakedz-ci` unaffected.
- POLA proof: `task swe-af` builds+tests with no network/model; the binary has no
  GitHub-write path.
- End-to-end: label a small, self-contained issue `agent` → a PR appears from
  `swe-af/issue-<n>` with the plan as body and the pr-review verdict attached; the
  uploaded eventd log shows `plan → code → review → publish` and verifies clean.

## Out of scope

- Deploying the agentfield runtime to `dev-cx53` via colmena (#51) and driving the
  real control panel — deferred to an on-box session (runbook).
- Standalone `coder`/`reviewer`/`broker` Rust agents — v0 reuses pr-review for review
  and the shell for publish.
