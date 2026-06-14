# 2026-06-14 — Vaked self-drive: proving the language can model AND enforce its own issue-driving fleet

Status: evidence record (dogfood). Companion to designs 0015 (workflow), 0011 (capability attenuation), 0012 (lowering).

## Thesis

Vaked is usually pitched as a declarative language for *infrastructure* — flakes, daemons, eBPF policy. This session tested a stronger claim: that the same language can model **and statically enforce** the *agentic loop that develops the repository itself* — a multi-model fleet that sweeps open issues, self-verifies each against `main`, abstains on the already-done, implements the rest, and folds the evidence back into the docs.

The proof is self-referential: the language compiled the very loop that drove this session's issue work.

## What was built (four dogfooded topologies)

All four are real `.vaked` files under `vaked/examples/`, each passing `parse → check → lower` clean and emitting 9 artifacts (`flake.nix`, `gen/workflow/<wf>.json` with precomputed critical-path depth, `gen/otp/*_sup.erl` supervision tree, `gen/eventd.json` replay contract, per-fiber Zig config, catalog, provenance).

| File | Models | Workflow shape | Depth |
|------|--------|----------------|-------|
| `pr-multimodel-pipeline.vaked` | the multi-model loop that produced PR #219 | collect → implement → review → publish → checkin | 5 |
| `issue-driver-team.vaked` | a multi-layer, multi-coder Team-Topologies fleet driving one issue to a green PR | triage → route → {3 coder lanes} ⤳ review → verify → integrate → publish | 7 |
| `session-drive-loop.vaked` | **this session**: sweep all open issues, abstain-or-implement, then reflect | collect → triage → verifyExisting → {coder lanes} ⤳ review → reflect → integrate → publish | 8 |
| `ralph-dogfood-loop.vaked` | the autonomous track-decision loop (`tools/ralph/`) on **self-hosted Ollama** (qwen3:8b); proposer tracks are loopback-only (can't egress/publish), recorder appends the immutable ledger, announcer egresses | rank → write → critique → record → announce | 5 |

Model assignment is the cost/effort discipline the user asked for: cheap **no-reasoning** flash models (gemini-3-flash-lite, haiku-4-5) orchestrate / route / verify; the latest **top agentic** models via OpenRouter (claude-opus-4-8, gpt-5, gemini-3-pro) do the coding; only the integrator holds `mcp.github_write`.

## What was proven (enforcement, not decoration)

The checker is not cosmetic. Negative tests forced each guard to fire:

- **`E-WORKFLOW-CYCLE`** — injecting a back-edge `checkin -> collect` into `pr_loop` was rejected; the diagnostic printed the cycle path and told the author to express revision loops as `retries`, not back-edges.
- **`E-WORKFLOW-DEPTH`** — setting `maxDepth = 3` against the depth-5 chain was rejected with the computed critical-path depth.
- **`E-CAP-ATTENUATION`** — the *first* draft of `issue-driver-team.vaked` gave the integrator `network.egress` while the root operator lacked it. The checker refused to lower: *"delegation `operator -> integrator` escalates authority: receiver holds `network.egress` but sender holds (none)."* POLA is a compile-time fact — a routing/integrator model cannot acquire authority its delegator never held. Fixed by granting the superset at the root.

The compile-time invariant the whole design buys: **no single model can widen its authority across a step boundary.** The reviewer holds no `repo_rw`; the coders hold no `mcp.github_write`. The capability split is checked before anything runs.

## The abstain gate (the session's sharpest evidence)

The user asked the fleet to drive issues **#192** and **#58** to green PRs. The verifier layer instead found both **already implemented and merged on `main`**:

- **#192** — `docs/SWE_AF_SMOKE.md` already exists on `main` with the exact requested content `swe-af smoke run OK`.
- **#58** — all three eventd/ralph fixes (O(1) cached-head append, fsync + torn-tail boot recovery, `cmd_run` `EventLogTamper` hard-fail gate) are present in `tools/ralph/ralph.py` on `main`; the full `test_ralph.py` suite passes (**109 passed, 0 failed**).

Both were **closed as completed with evidence comments** — no redundant PRs manufactured. This is exactly the `verifyExisting` ABSTAIN gate in `session-drive-loop.vaked`: the correct output for an already-done issue is *nothing*, and the topology encodes that as a first-class step rather than a missing edge. (It echoes issue #208's "abstain this window" ethos — surface nothing rather than fabricate a change.)

The one issue that survived verification as genuinely-open and tractable — **#25** (vakedc drops same-name, different-kind top-level decls from the LPG with no diagnostic) — was handed to a coder lane (claude-opus-4-8, worktree-isolated) to implement the issue's own recommended fix: a conservative `E-DECL-NAME-COLLISION` resolve-time diagnostic that avoids churning the frozen goldens (#15).

## Theory advanced

1. **Two-graph discipline scales to the fleet that writes the code.** The 0015 split (mesh = authority, workflow = ordering) is enough to model an autonomous SWE swarm, not just a single agent. The `reflect` step added here shows the loop can be made to *advance its own documentation* as a checked node, not an afterthought.
2. **Abstention is a modelable, checkable state.** A self-verifying fleet must be allowed to do nothing. Encoding `verifyExisting` as a step (with `retries` carrying the re-checks) makes "already green" a legible outcome instead of a silent skip.
3. **Capability attenuation makes multi-model trust boundaries a compile-time fact.** Mixing a no-reasoning flash router, a high-reasoning coder, and a write-holding integrator is safe *because* the checker forbids any of them widening authority across an edge.

## Reproduce it — the one-shot prompt

The whole loop, as a single driver prompt (the "best one-shot" the session converged on):

> Sweep every OPEN issue in this repo. For each, **self-verify against `main` first** — if the work is already merged, close it with an evidence comment and **do not open a PR**. For the genuinely-open, tractable ones, run a multi-model swarm: cheap no-reasoning flash models triage/route/verify, top OpenRouter agentic models implement in worktree-isolated lanes, a mid model reviews, and a single integrator (the only `github_write` holder) opens the PR and drives CI to green/mergeable. Model the loop itself as a Vaked capability graph (`mesh` = attenuated authority, `workflow` = checked ordering DAG with `retries` for kick-until-green, an abstain gate, and a `reflect` step), dogfood it through `vakedc parse|check|lower`, and **fold the run's evidence — compile outputs, negative tests, the attenuation catch — back into a dated proof record under `docs/superpowers/specs/`**. Drive `main` further; document everything.

Verify locally:

```bash
for f in pr-multimodel-pipeline issue-driver-team session-drive-loop ralph-dogfood-loop; do
  python3 -m vakedc check  vaked/examples/$f.vaked
  python3 -m vakedc lower  vaked/examples/$f.vaked --out /tmp/$f
done
```

## Artifacts this session landed

- `vaked/examples/pr-multimodel-pipeline.vaked`, `issue-driver-team.vaked`, `session-drive-loop.vaked`, `ralph-dogfood-loop.vaked` (+ their lowerings)
- `open-issues.txt` — the swept backlog (36 open at session start)
- Issues **#192**, **#58** closed with evidence
- Issue **#25** fix in flight on branch `claude/issue-25-decl-collision`
- This record
