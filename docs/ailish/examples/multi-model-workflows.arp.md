# AI-lish V1 — example library: complex multi-layer, multi-model workflows

Ten one-shot ARP (AI-lish V1) commands. Each expresses a complex workflow as a
single dense frame set. Notation per [the V1 RFC](../2026-06-14-ailish-v1-rfc.md):
SSA `%N` registers, dataflow `→`, justification `∵`, set-ops `join`/`∖`/`∪`,
per-node `model=`/`models=[...]` routing, and gate-frozen `[!C]` commits.

Layer convention: `[!P]` schedule → `[!X]` execute → `[!V]` verify → `[!C]` commit.

```text
# 1 — judge panel: N drafts (diverse models) → score → synthesize from winner
[!P] %0=fork(task=$GOAL, models=[opus,sonnet,gemini]) → %1=map(%0, draft())
[!V] %2=map(%1, score(judge=opus)) ; rubric="mvp,risk,user"
[!X] %3=argmax(%2) ⊕ %4=graft(loser_ideas=%1∖%3) → synth(%3,%4); gate(artifact:pass)∵%2

# 2 — Graph-RAG multi-hop → MMR rerank → grounded answer
[!X] %0=embed(q=$Q,model=haiku) → %1=hop(graph=kg,depth=3,seed=%0)
     %2=rerank(%1,strategy="mmr",model=sonnet) → %3=answer(ctx=%2,model=opus)
[!R] %4=cite_check(%3,src=%2); gate(parse:fail)∵%4 ⇒ block(answer)

# 3 — adversarial verify: 3 skeptics refute each finding, majority kills
[!X] %0=find(target=$DIFF,model=sonnet) → %1=map(%0.bugs, λb·
       join(refute(b,model=opus),refute(b,model=gemini),refute(b,model=haiku)))
[!V] %2=filter(%1, real ≥ 2of3) ; gate(review:pass)∵%2

# 4 — map-reduce migration over files, worktree-isolated, per-file gate
[!P] %0=glob("src/**/*.ts") → %1=map(%0, λf· migrate(f,model=sonnet,iso=worktree))
[!B] %2=map(%1, test()) → %3=filter(%2, ci:pass) ; gate(ci:fail)∵(%2∖%3) ⇒ block(merge)

# 5 — four-model debate → moderated consensus
[!X] %0=join(pos(claude),neg(gemini),pos(codex),neg(qwen)) ; rounds=3
[!V] %1=moderate(%0,model=opus) → consensus ; gate(english:pass)∵%1

# 6 — tiered pipeline: plan(opus)→code(sonnet)→review(gemini)→bench(local)
[!P] %0=plan(spec=$SPEC,model=opus) → %1=code(%0,model=sonnet)
[!V] %2=review(%1,model=gemini) ∵ %1
[!B] %3=bench(%1,host=`cargo`) ; gate(ci:pass)∵join(%2,%3)
[!C] %4=open(pr,base=%1) ∵ gate(ci:pass)        # frozen if any gate(*:fail)

# 7 — loop-until-dry discovery, dedup vs seen, diverse-lens verify
[!P] %0=loop(until="2 dry rounds", λ· dedup(find(models=[sonnet,gemini]), seen))
[!V] %1=map(%0, lens=[correctness,security,repro]·judge(opus)) ; keep ≥2 → seen∪=%1

# 8 — multi-modal research sweep (4 angles) → synth → completeness critic
[!X] %0=join(web(gemini),code(sonnet),memory(haiku),time(sonnet)) → %1=synth(opus,%0)
[!V] %2=critic(%1,ask="what modality unrun / claim unverified?",model=opus)
     gate(artifact:warn)∵%2 ⇒ %3=launch_agent(scope=%2.missing)

# 9 — cost-routed cascade: cheap first, escalate on low-confidence
[!X] %0=ask(haiku,$Q) ; conf=eval(%0)
     %1 = conf<0.7 ? ask(sonnet,$Q) : %0 ; conf2=eval(%1)
     %2 = conf2<0.7 ? ask(opus,$Q) : %1 ; gate(bench:pass)∵%2  # ledger: tokens spent
[!A] cost=track(%0,%1,%2); output=%2

# 10 — tournament bracket: 8 candidates, pairwise judge, single winner
[!P] %0=fork(n=8,models=[opus,sonnet,gemini,codex]) → %1=draft(%0)
[!V] %2=bracket(%1, pair_judge=opus, rounds=3) → %3=champion(%2)
[!C] %4=commit(%3) ∵ gate(review:pass)∵%2
```

## Reading guide

- **Layers** — every workflow lowers through schedule (`[!P]`) → execute (`[!X]`) →
  verify (`[!V]`/`[!R]`/`[!B]`) → commit (`[!C]`). A `[!C]` line is frozen by the
  guardrail (RFC §3) while any `gate(*:fail)` is live.
- **Multi-model** — model routing is per-node (`model=opus`, `models=[...]`), so one
  frame set spans tiers (haiku cheap-path → opus arbiter) and vendors (claude/gemini/
  codex/qwen) without leaving the notation.
- **Dataflow** — `→` passes output to input; `∵` marks justification; `∖`/`∪` are set
  difference/union over result sets (`%1∖%3` = losers, `seen∪=%1` = accumulate).
