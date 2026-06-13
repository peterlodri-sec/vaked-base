# vaked-agents — fleet backlog

`vaked-agents/` is the home for the **Vaked agent fleet**. The first inhabitant is
[`ci/pr-review`](ci/pr-review/README.md) — the advisory CI PR reviewer
(adk-rust + OpenRouter, crabcc-indexed, Langfuse-traced). This file is the fleet's
**backlog**: lightweight capture of where the fleet is headed, grounded in
[adk-rust](https://github.com/zavora-ai/adk-rust) 1.0 APIs.

**How the backlog works.** Items here are intentions, not designs. When one is
picked up it graduates to the repo's normal cycle (per `CLAUDE.md`): a dated
design record in [`docs/superpowers/specs/`](../docs/superpowers/specs/) →
a checklist in [`docs/superpowers/plans/`](../docs/superpowers/plans/) →
implementation. Protocol work lands as RFCs under
[`protocol/rfcs/`](../protocol/rfcs/) (use the `hcp-rfc-author` skill).

**Legend.** Scope: `reviewer` (extends `ci/pr-review`) · `fleet` (shared infra) ·
`new-agent` · `protocol`. Effort: S / M / L / XL. ⭐ = user-flagged priority.

**Shipped.** **yardmaster** (`new-agent` · merge-train conductor) — sequences the
fan-out fleet's *integration*: builds the open-PR dependency DAG (catches stacked
PRs like #112-on-#103), topo-orders the train, and plans merge / update-branch /
wait / block-conflict / hold-on-base onto an `eventd` ledger. Advisory dry-run,
opt-in `train:auto`, never auto-resolves conflicts. See
[`tools/yardmaster/`](../tools/yardmaster/README.md).

---

## A. Reviewer upgrades — extend `ci/pr-review`

### 1. ParallelAgent — `reviewer` · M
Replace the hand-rolled `map_reduce_review` (parallel per-file passes +
synthesis) with adk's workflow agents: a `ParallelAgent::new(name, sub_agents)`
fan-out of per-file reviewers, then a `SequentialAgent` synthesis step
(`adk_agent`). Declarative, adk-managed concurrency; retires the bespoke
`buffer_unordered` orchestration.

### 2. CacheCapable — `reviewer` · S
Check whether `OpenRouterClient` implements `CacheCapable`; if so, wire
`Runner::builder().cache_capable(..)` + `RunConfig.auto_cache` for explicit
prefix caching on top of today's `with_prompt_cache_key`. Cuts cost on
map-reduce, where the ~1.5 KB system prompt is re-sent per file.

### 3. Tool sampling + strategy — `reviewer` · M
`mcp-sampling` (`McpToolset::with_sampling_handler`) so MCP tools (crabcc) can
request model completions mid-call; plus `adk_tool::sampling` and per-workload
`ToolExecutionStrategy` tuning (we currently set `Auto`).

### 4. Context compaction — `reviewer` · S–M
`RunConfig.compaction` (`CompactionConfig`) to auto-summarize context on overflow
instead of the current blunt char truncation — for monster diffs / single files.

### 5. Guardrails — `reviewer` · M (security)
Adopt the `guardrail` crate: move secret-redaction into an **input guardrail** and
add **prompt-injection defense** (the diff is untrusted input); add an **output
guardrail** enforcing the JSON schema / `max_findings` cap.

---

## B. Shared fleet infrastructure

### 6. Memory (self-hosted) — `fleet` · L
adk memory backends (`postgres` / `redis` / `sqlite` / `neo4j`-memory +
`memory-tools`) on self-hosted storage: persistent review memory ("seen this
finding/pattern before"), per-repo learned conventions, cross-PR dedupe. Reusable
by every fleet agent. Needs a self-hosted store.

### 7. Agent registry — `fleet` · L
adk-server `agent-registry` + `yaml-agent`: declare agents in YAML and
serve/discover them from a registry — strongly Vaked-aligned ("Vaked declares;
Nix materializes"). Becomes the fleet's front door.

### 8. Ambient agents — `fleet` · M
`adk_agent::ambient` `CronTrigger` / `WebhookTrigger` / `FileWatchTrigger` +
`AmbientAgent`. Uses: the PR-watch / babysit-CI loop as a webhook-triggered agent;
a replacement for the `tools/ralph` cron loop; the pattern for Vaked's
event-driven daemons.

---

## C. New agents

### 9. ⭐ CTO copilot — realtime avatar/voice — `new-agent` · XL
A personal agent for the CTO (you): watches CI, runs research, and brainstorms by
voice/avatar. adk `realtime` (`RealtimeAgent` / `RealtimeRunner`, WebRTC + avatar).
The largest item — lands in a new subtree (e.g. `vaked-agents/personal/cto/`) and
warrants its own design spec + plan before any code.

---

## D. Protocol research — feeds `protocol/rfcs/`

### 10. HCP / Litany reference study — `protocol` · M (research)
Mine adk's **A2A / ACP / AWP** agent-wire protocols as prior art for HCP: map
their framing, version negotiation, flow control, and multi-agent state-dependency
onto **Votive Frames**, **Litany Wire**, and
[`0004-multi-agent-state-dependency.md`](../protocol/rfcs/0004-multi-agent-state-dependency.md).
Output: notes + RFC edits, not agent code.

---

## E. Eval & carried-over tuning items

### 11. Adopt `adk_eval` + personas — `reviewer` · M
Replace/augment the `--eval` harness (`ci/pr-review/evals/`) with adk's eval
framework: persona-based scoring, a larger corpus, regression gating on agent PRs.

**Deferred tuning items** (captured here as the single source of truth):
- Inline review comments + GitHub `suggestion` blocks (structured findings already
  carry `path:line` + `fix`).
- Incremental review — only the delta since the last reviewed SHA.
- Severity-gated / blocking mode (opt-in; default stays advisory).
- Per-PR cost guard — estimate/trim/track spend, surface in the status.
- In-repo `.vaked-review.toml` config (per-repo model/thresholds/excludes).
- ~~`@vaked-ci` interactive replies (comment-triggered workflow).~~ **DONE** — `--respond` mode + `vaked-ci-respond.yml` (answers questions / `re-review`; advisory; author-association gated).
- Expand the eval corpus (nix/zig/security/large-diff) — ties to item 11.
