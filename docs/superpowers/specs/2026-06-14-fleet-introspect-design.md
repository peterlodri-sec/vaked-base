# fleet-introspect — a daily, gated fleet self-improvement loop over Langfuse telemetry (design)

## Status

Design + shipped (2026-06-14). **Tooling**, not the Vaked language — no grammar gate.
Owner-approved scope. A **second binary in the optitron Go module** (`cmd/introspect`) that
**reuses optitron's core** (`internal/ledger`, `internal/llm`) rather than re-implementing it.
Stacks on the optitron PR (#157).

## Why

Every CI bot emits Langfuse traces, but **nothing reads them back** — the fleet's own
observability never feeds improvement. fleet-introspect closes the loop: once a day it ingests the
last ≤2 days of the fleet's Langfuse traces (+ the hash-chained ledgers + recent CI), **auto-detects
the most salient finding**, ideates **one** novel solution, **always reviews** it (fail-closed), and
hands a survivor to **swe_af**. It also surfaces the **fleet economy** — real spend projected to a
normal day/week/month — so cost creep stays visible.

## Constraints honoured (owner direction)

- **Reuse the optitron core** for the agent implementation — so it lives *inside* the optitron Go
  module (Go's `internal/` packages can't be imported across module boundaries). It shares
  `internal/ledger` (its own ledger file) and `internal/llm` (the Eino OpenRouter wrapper +
  `CallJSON`); the only new public surface is `llm.NamedSchema`/`llm.NewSchema` so the agent can
  register its own strict schemas.
- **ralph is live — read only.** The loop reads `tools/ralph/state/events.jsonl` as a data source
  and never modifies `tools/ralph/` (no ralph code is touched).
- **Auto-detect the finding** (with an optional `--focus` operator override at dispatch).
- **agent issue → swe_af** hand-off; **always review** (the fail-closed gate); **double-confirmed**
  manual trigger.

## The loop (`introspect run` — one daily run; abstain by default)

1. **Ingest (no LLM).** `internal/introspect/langfuse.go` pages
   `GET /api/public/observations?type=GENERATION&fromStartTime=…&toStartTime=…` (HTTP Basic from the
   key pair). Real (OTel) spans are named `gen_ai.generate`, so it **groups by `model`** (always
   present) and **computes cost client-side from tokens** (Langfuse self-hosted omits server cost);
   per-span-name counts give the bot signal. Plus the ralph (read-only) + optitron ledgers via
   `ledger.Load`, and recent `gh run list` outcomes.
2. **Economy roll-up.** Real per-model spend → a *normal, non-optimistic* projection (`/day`, `×7`,
   `×30.4`), emitted in the digest, CI summary, ledger event, and issue body.
3. **Detect** (`deepseek-v4-flash`) — the single most salient finding, grounded in exact numbers.
4. **Ideate** (`claude-opus-4.8`) — ONE novel solution: mechanism, novelty, target files, signature.
5. **Review — always** (`claude-opus-4.8`) — `approved && novel && grounded && actionable &&
   confidence ≥ 0.75`, plus deterministic novelty (`git grep` signature + ledger title dedupe).
6. **Act (survivor only)** — `agent`-labelled issue (swe_af trigger) + announce; append `found`.
   Nothing survives ⇒ `none`, CI log only.

## Files

- **`tools/optitron/internal/llm/`** — export `NamedSchema` + add `NewSchema()` (the only change to
  optitron's core, enabling schema reuse).
- **`tools/optitron/internal/introspect/`** — `config.go`, `langfuse.go` (REST query client),
  `digest.go` (aggregate-by-model + economy + ledger/CI), `schemas.go` (typed stages + prompts),
  `gate.go`, `pipeline.go`, `PURPOSE.md`, `introspect_test.go`.
- **`tools/optitron/cmd/introspect/main.go`** — CLI (`run`, `events`).
- **`tools/optitron/state/introspect.jsonl`** — the agent's OWN hash-chained ledger.
- **`.github/workflows/fleet-introspect.yml`** — daily `schedule` + gated `workflow_dispatch`
  (`approve` job on the protected **`introspect-manual`** Environment, confirm #2, gated on typed
  `confirm == 'RUN'`, confirm #1). Tests ride the existing `optitron-go` `go test ./...` job.
- Registry/docs: `VAKED_AGENTS.md`, `docs/agents/ci.md`, this spec, `tools/optitron/README.md`.

## Economy (own cost — measured at first dry-run)
3 calls/run (~$0.20–0.45 normal; ceiling = the $3 cap). The fleet projection is computed live from
real Langfuse cost — at design time the measured 2-day fleet spend was ~$0.77 → **~$11.7/month**.

## One-time owner setup
GitHub → Settings → Environments → create **`introspect-manual`** → add yourself as a Required
reviewer. No secrets on it — the loop runs in `ci`.

## Verification
`go -C tools/optitron run ./cmd/introspect run --dry-run` (real digest + economy, no model calls) ·
`go test -race ./...` (introspect aggregation incl. client-side cost, economy, the gate) ·
`INTROSPECT_DRY_ACT=1 introspect run --once` (full loop, issue/toot only drafted) · dispatch
`fleet-introspect.yml` with `confirm=RUN` ⇒ pauses on the `introspect-manual` approval.
