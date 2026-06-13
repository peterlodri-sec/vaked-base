# vaked-optitron — Go (Eino) rewrite + gated manual trigger (design)

## Status

Design (2026-06-13). **Tooling**, not the Vaked language — no grammar gate. Owner-approved
scope, evolving [PR #157](https://github.com/peterlodri-sec/vaked-base/pull/157). Supersedes the
runtime described in `2026-06-13-vaked-optitron-design.md`: the agent's *behaviour* and gate are
unchanged (the declarative `SKILL.md` is the source of truth), only the concrete runtime moves
from a stdlib-Python harness to a **Go binary built on [Eino](https://github.com/cloudwego/eino)**.

## Why

Three owner asks on top of the shipped optitron:
1. **Dogfood Go for the fleet** — the agents are otherwise Rust/Python; prove out a Go agent and
   use **goroutines** for real concurrency.
2. **Gate manual runs** behind a *double confirmation* without hurting DX (an on-demand crawl
   spends money and can open an `agent` issue, so a human-in-the-loop is warranted).
3. **Refresh models** to the June-2026 frontier and **reuse ideas from PentestGPT**.

## Framework decision — Eino (CloudWeGo)

Evaluated three Go agent stacks:
- **Eino** *(chosen)* — Go-native, goroutine-first; ships an `openrouter` chat-model component
  with strict `json_schema` structured output + reasoning-effort, plus `schema.Message` types and
  a Langfuse callback. Best concurrency story, least impedance.
- **Genkit Go** (Google) — great DX/flows but heavier, Google-centric; OpenRouter only via an
  OpenAI-compat shim.
- **LangChainGo** — familiar chains/agents, less Go-idiomatic, more abstraction overhead.

We use Eino for the **model layer** (the `openrouter.ChatModel` component, message types, strict
schema output, reasoning effort) and keep the **orchestration** in idiomatic Go (`errgroup` +
channels + `context`), which fits optitron's crawl-fan-out / worker-pool / first-wins shape far
better than a graph DSL.

## Concurrency model (the goroutine story)

| Concern | Mechanism |
|---|---|
| **Crawl fan-out** | one `errgroup` goroutine per source family (arXiv · LLVM/Cranelift · Zig · Rust · allocators); candidates merged + de-duped by title |
| **Candidate evaluation** | bounded `errgroup` worker-pool (`SetLimit(4)`); each worker runs verify→bench→adjudicate→gate concurrently |
| **One finding per run** | first worker to clear the gate claims the win via `sync.Once`, acts, and `cancel()`s the shared context to wind the rest down |
| **Budget cap** | a mutex-guarded `Budget`; every model call checks `Over()` first and records its cost, so spend can't run away across goroutines |
| **Ledger integrity** | the hash chain needs a single writer — all appends serialize through a mutex-guarded `ledger.Writer`, so the chain stays valid under concurrency (covered by a `-race` test) |

## PentestGPT lineage (pattern reuse, no code vendored)

PentestGPT splits a monolithic LLM call into cooperating **reasoning / generation / parsing**
modules over a persistent task structure. optitron adopts the split:
- **Generator** — `internal/llm` crawl + bench codegen.
- **Reasoner** — the skeptical cross-check + adjudication (Eino reasoning effort = medium).
- **Parser** — `internal/gate`, the deterministic verdict (no model in the loop).
- **Persistent memory** — the hash-chained ledger (cross-run novelty); **bounded iteration** =
  one finding per run + the budget cap (PentestGPT's max-iterations/context-file idea).

## Models (June-2026 defaults; all env-overridable)

| Leg | Env | Default | Rationale |
|---|---|---|---|
| Crawl (web) | `OPTITRON_CRAWL_MODEL` | `openai/gpt-5.5:online` | needs `:online`; broad recall |
| Verify + Adjudicate | `OPTITRON_VERIFY_MODEL` | `anthropic/claude-opus-4.8` | current frontier reasoner → best skeptical adjudication (the anti-hallucination crux) |
| Bench codegen | `OPTITRON_BENCH_MODEL` | `deepseek/deepseek-v4-flash` | cheap, fast code; swap to `anthropic/claude-fable-5` for stronger codegen |

The $4/run hard cap is unchanged; verify/adjudicate calls are small so the frontier reasoner
stays affordable. `$0` when the key is absent.

## Gated manual trigger — native GitHub double-confirm

`optitron-crawl.yml` keeps the daily `schedule` (trusted, no approval) and reworks
`workflow_dispatch` into two confirmations:
1. **Typed gate** — `confirm: RUN` input; anything else skips the `approve` job ⇒ no crawl.
2. **Environment approval** — the `approve` job targets a new protected **`optitron-manual`**
   Environment with **Required reviewers**, so GitHub pauses for an approval click *before* the
   `crawl` job (which `needs: approve`) runs. The crawl runs in `ci` (where secrets live), so
   `optitron-manual` needs no secrets — it's purely the gate.

DX cost: one dispatch with a typed word + one approval click; full audit trail; zero new infra.
One-time owner setup: create the `optitron-manual` Environment and add yourself as a reviewer.

## Files

- **New Go module** `tools/optitron/`: `go.mod`, `cmd/optitron/main.go`,
  `internal/{ledger,gate,llm,run}/…` + `*_test.go`. Removes `optitron.py`, `optitroncore.py`.
- **Preserved**: `sources.json`, `PURPOSE.md`, `state/events.jsonl` (ledger continuity).
- **Workflow**: `.github/workflows/optitron-crawl.yml` (two-job gated dispatch + `setup-go`).
- **Toolchain**: `flake.nix` devShell gains `go` + `gopls`.
- **Registry/docs**: `VAKED_AGENTS.md`, `docs/agents/ci.md`, `SKILL.md` runtime line, this spec.

## Verification

`cd tools/optitron && go build ./... && go test -race ./...` (ledger incl. concurrent append,
gate thresholds + source independence, real compiled C micro-bench). `go run ./cmd/optitron
crawl --dry-run` (prompts + cost estimate, no network). `OPTITRON_DRY_ACT=1 … crawl --once`
(full concurrent run, issue/toot only drafted). Dispatch the workflow with `confirm=RUN` and
confirm it pauses on the `optitron-manual` approval before any spend.
