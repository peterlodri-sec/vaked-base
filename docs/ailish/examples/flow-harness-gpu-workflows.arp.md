# AI-lish V1 — example library: flow control, harness, optimizations, GPU

100 ARP (AI-lish V1) commands across 10 categories (flow-control, harness, error-handling, cache, budget, parallelism, optimization, GPU, scheduling, observability). Notation: the V1 RFC / cheatsheet under docs/ailish/. Parser-conformance fixtures.

## flow-control — Native flow control: conditionals (cond?a:b), early-exit, retry-with-backoff, branch/merge, guard clauses, switch on result.

```text
# guard clause: skip review when no diff
[!T] %d = git diff --stat ; %n = wc(%d, lines).
[!X] cond(%n == 0)? exit(0) : open review(%d).

# retry-with-backoff on flaky network test
[!P] schedule retry test(net) loop(until=gate(ci:pass) ∨ attempts==4).
[!X] %r = test(suite=net, model=haiku) ; backoff = map([1s,2s,4s,8s], attempt).
[!R] gate(ci:fail)? retry(%r, backoff) : continue ∵ transient-flake.
[!C] commit(net-fix) cond(gate(ci:pass))? freeze : abort.

# switch on lint result, route by severity
[!X] %l = lint(src/, model=sonnet) ; %sev = argmax(%l.findings, severity).
[!T] switch(%sev){ error?edit(%l.error): warn?annotate(%l.warn): clean?skip }.
[!V] review(%l) gate(parse:pass).

# early-exit fast path vs full deep-research
[!T] %q = read(issue.body) ; %hit = memory_search(%q).
[!X] cond(%hit.score > 0.9)? answer(%hit) : launch_agent(deep-research, model=opus).
[!C] commit(answer) gate(english:pass).

# branch/merge two model drafts, pick best
[!P] schedule fan-out draft(spec) models=[opus,gemini].
[!X] %a = write(draft, model=opus) ; %b = write(draft, model=gemini).
[!V] %best = argmax([%a,%b], review.score) ; %m = merge(%best, base).
[!C] commit(%m) cond(gate(parse:pass) ∧ gate(no_cjk:pass))? merge(main) : hold.

# conditional model downgrade on token budget
[!T] %tok = bench(context, tokens) ; %mdl = cond(%tok > 100000)? haiku : sonnet.
[!X] %s = summary(logs/, model=%mdl) ; edit(report.md, %s).
[!B] bench(report.md, tokens) gate(bench:pass).

# guard clauses chain before destructive build
[!R] cond(branch == main)? abort ∵ protected : continue.
[!R] %dirty = git status ; cond(%dirty != ∅)? abort : continue.
[!X] build(target=release) gate(ci:pass) ; commit(artifact) gate(commit:pass).

# retry parse with escalating model
[!P] schedule parse(ai-lish) loop(until=gate(parse:pass) ∨ attempts==3).
[!X] %p = test(parse, model=qwen) ; cond(gate(parse:fail))? retry(model=sonnet) : %p.
[!R] gate(parse:fail) ∧ attempts==3? launch_agent(fixer, model=opus) : done.
[!A] artifact(parsed.json) gate(artifact:pass).

# switch on PR check status, dispatch handler
[!X] %ci = gh pr checks ; %st = fold(%ci, worst-status).
[!T] switch(%st){ fail?launch_agent(triage,model=codex): pending?wait: pass?merge(pr) }.
[!C] commit(merge) cond(gate(ci:pass))? open release : skip.

# conditional branch + dedup + merge filtered set
[!X] %errs = err(build.log, model=haiku) ; %u = dedup(%errs).
[!T] %crit = filter(%u, level==error) ; cond(%crit != ∅)? edit(src/) : annotate(%u).
[!V] %fixed = join(%crit, patches) intersect open-files ; review(%fixed) gate(english:pass).
[!C] commit(%fixed) cond(gate(no_cjk:pass) ∧ gate(parse:pass))? merge : abort.
```

## harness — Orchestration harness: pipeline vs parallel(barrier), worktree isolation, fan-out/fan-in, sub-workflow nesting, resumable checkpoints.

```text
# Pipeline stages serialized into a barrier-gated fan-out
[!P] %stages = [lint test build] ; map(launch_agent, %stages) model=haiku
[!X] %r = loop(until=all(%stages:done)) launch_agent ; %joined = fold(join, %r)
[!V] gate(ci:pass) ∵ barrier(%joined) ∧ no failed stage
[!C] commit %joined cond?gate(ci:pass):skip

# Worktree isolation per agent, fan-in via merge
[!P] %wt = map(open, [wt-a wt-b wt-c]) ∵ isolate edits ; models=[sonnet sonnet codex]
[!X] %edits = map(edit, %wt) ; %clean = filter(no_conflict, %edits)
[!R] gate(parse:warn) ∵ cross-worktree drift → mitigate dedup(%clean)
[!C] %m = merge(fold(combine, %clean)) ; commit %m cond?gate(parse:pass):skip

# Fan-out test shards, fan-in worst-case bench
[!P] %shards = map(launch_agent, [s0 s1 s2 s3]) model=qwen
[!X] %res = loop(until=count(%shards)==4) test ; %slow = argmax(latency, %res)
[!B] bench %slow ; gate(bench:warn) ∵ %slow exceeds budget
[!C] commit %res cond?gate(bench:warn):commit

# Nested sub-workflow: outer plan delegates inner pipeline
[!P] %inner = launch_agent(pipeline=[read diff write]) model=gemini
[!X] %out = %inner → map(test, %out) ; %ok = filter(green, %out)
[!V] gate(english:pass) intersect gate(ci:pass) ∵ inner+outer both clean
[!C] commit join(%inner, %ok)

# Resumable checkpoint: skip completed, resume remainder
[!T] %ckpt = read(.state) ; %remaining = %all ∖ %ckpt
[!X] %done = loop(until=empty(%remaining)) launch_agent ; write(.state, %done)
[!C] commit %done ∵ checkpoint advanced cond?gate(ci:pass):skip

# Parallel discover then sequential synthesize barrier
[!P] %hits = map(fetch, [src1 src2 src3]) model=haiku ; %clean = dedup(%hits)
[!X] %syn = fold(combine, %clean) ∵ barrier waits all fetch ; launch_agent(synth=%syn) model=opus
[!V] gate(no_cjk:pass) ∧ gate(english:pass)
[!A] write report = %syn

# Fan-out review across models, intersect approvals
[!P] %reviews = map(launch_agent, models=[opus sonnet gemini codex])
[!X] %approve = fold(intersect, map(filter(approved), %reviews))
[!R] gate(commit:fail) ∵ not unanimous → mitigate: re-launch_agent(dissent) model=opus
[!C] commit %approve cond?gate(commit:pass):skip

# Worktree-isolated bisect with resumable frontier
[!P] %frontier = read(.bisect) ; %wt = open(worktree=bisect)
[!X] %step = loop(until=len(%frontier)==1) test ; %bad = argmax(regress, %step)
[!A] write(.bisect, %bad) ∵ checkpoint frontier
[!C] commit %bad cond?gate(ci:pass):commit

# Sub-workflow nesting 3 levels, fold results upward
[!P] %l1 = launch_agent(child=launch_agent(child=launch_agent(leaf))) models=[opus sonnet haiku]
[!X] %up = fold(combine, %l1) ; %merged = merge(%up)
[!V] gate(parse:pass) ∵ all nested frames parse
[!C] commit %merged

# Pipeline-vs-parallel hybrid: parallel build, serial deploy gate
[!P] %built = map(build, [api web worker]) model=codex ∵ parallel
[!X] %arts = filter(success, %built) ; %deploy = fold(join, %arts) → launch_agent(deploy=%deploy)
[!R] gate(bench:fail) ∵ deploy SLO miss → mitigate: rollback %deploy ∪ alert
[!C] commit %deploy cond?gate(bench:pass):skip
```

## error — Error handling: gate→freeze→mitigate, fallback chains, rollback, compensating actions, dead-letter, circuit-breaker.

```text
# gate fail freezes commit, risk mitigates before retry
[!X] %1 = test ./suite → gate(ci:fail) .
[!R] gate(ci:fail) ? %2 = edit ./flaky_spec : %2 = read ./logs ; %3 = build %2 .
[!C] gate(ci:fail) ? commit %3 [frozen] : commit %3 .

# fallback chain across model routing with dead-letter split
[!T] %1 = read ./batch ∵ classify each record .
[!X] %2 = map(%1, model=opus) → gate(parse:warn) ; %3 = %1 ∖ %2 ∵ unparsed→dead-letter .
[!X] %4 = map(%3, models=[sonnet,haiku]) ? %5 = %2 ∪ %4 : write ./deadletter %3 .

# rollback edit on artifact gate failure
[!A] %1 = edit ./config.toml → gate(artifact:fail) .
[!R] gate(artifact:fail) ? %2 = diff %1 ./config.bak : %2 = %1 .
[!C] gate(artifact:fail) ? commit %2 [frozen] : commit %2 .

# circuit-breaker retry loop until ci passes or skip
[!P] schedule retry ∵ transient upstream errors .
[!X] loop(until=gate(ci:pass)) %1 = test ./integration → gate(ci:warn) .
[!R] gate(ci:warn) ? %2 = build ./fixtures : gate(ci:skip) ∵ breaker open .

# compensating action after partial merge
[!X] %1 = merge feat/x → gate(commit:fail) .
[!R] gate(commit:fail) ? %2 = edit ./rollback.sh ; %3 = build %2 : %3 = %1 .
[!V] review %3 model=sonnet → gate(english:pass) .
[!C] gate(commit:fail) ? commit %3 [frozen] : commit %3 .

# dead-letter dedup and re-enqueue via set ops
[!X] %1 = fetch ./queue ; %2 = filter(%1, status=err) → gate(parse:fail) .
[!A] %3 = dedup(%2) ; %4 = %1 ∖ %3 ; write ./dlq %3 .
[!R] gate(parse:fail) ? %5 = fold(%4, combine) : %5 = %4 .

# fallback model routing with bench-gated promotion
[!X] %1 = read ./prompts → gate(no_cjk:pass) .
[!B] %2 = bench %1 models=[opus,gemini,codex] → gate(bench:warn) .
[!R] gate(bench:warn) ? %3 = argmax(%2) : %3 = profile %1 model=qwen .

# launch_agent fallback on tool failure, freeze on fail
[!X] %1 = launch_agent ./repair model=opus → gate(ci:fail) .
[!X] gate(ci:fail) ? %2 = launch_agent ./repair model=sonnet : %2 = %1 ; %3 = test %2 → gate(ci:pass) .
[!C] gate(ci:pass) ? commit %3 : commit %3 [frozen] .

# rollback chain with diff justification and intersect verify
[!X] %1 = open ./pr/42 ; %2 = diff %1 ./main → gate(artifact:warn) ∵ drift detected .
[!R] gate(artifact:warn) ? %3 = edit %1 : %3 = %1 ; %4 = %3 intersect ./main .
[!V] review %4 models=[sonnet,haiku] → gate(english:pass) .

# multi-gate freeze: any fail blocks commit, compensate then re-test
[!X] %1 = build ./svc → gate(parse:pass) ; %2 = test %1 → gate(ci:fail) .
[!R] join(gate(parse:pass), gate(ci:fail)) ? %3 = edit ./svc ∵ compensate : %3 = %1 .
[!X] %4 = test %3 → gate(ci:pass) .
[!C] gate(ci:fail) ? commit %4 [frozen] : commit %4 .
```

## cache — Caching/memoization: reuse prior %N, warm-cache, dedup work, content-hash skip-if-unchanged, incremental recompute.

```text
# warm npm install cache before parallel build fan-out
[!P] schedule warm-cache(node_modules) ; map(installs, workspaces) ; model=haiku .
[!X] %1 = read package-lock.json ; %2 = fetch registry.npmjs.org/_cache ; combine(%1,%2) → %3 .
[!C] commit warm-cache(%3) ; gate(parse:pass) .

# content-hash skip-if-unchanged on tsc emit
[!T] hash(src) == hash(prev) ? reuse %4 : recompute ∵ avoid redundant tsc emit .
[!X] %4 = read .tsbuildinfo ; %5 = build tsc --incremental ; diff(%4,%5) → %6 .
[!V] review cond(%6 == empty)?skip:emit ; gate(ci:pass) ; gate(bench:warn) .

# dedup memoized test selection across two suites
[!X] %7 = test jest --listTests ; %8 = test vitest --listTests ; %9 = dedup(join(%7,%8)) .
[!X] %10 = %9 ∖ cache(passed) ; filter(%10, changed) → %11 ; model=sonnet .
[!C] commit cache(%11) ; gate(no_cjk:pass) ; gate(artifact:pass) .

# incremental recompute loop until cache converges
[!P] schedule incremental recompute(deps) ; loop(until=cache_stable) .
[!X] loop(until=hash(out)==hash(prev)) { %12 = build cargo build ; profile %12 → %13 } .
[!B] bench fold(%13, durations) ; argmax(%13) → %14 ; gate(bench:pass) .
[!C] commit %14 ; gate(commit:pass) .

# reuse prior %N to skip recompute, gate fails freeze commit
[!T] reuse %14 ∵ inputs unchanged ; map(%14, targets) → %15 .
[!X] %16 = test pytest -k cache ; %17 = %15 intersect cache(green) .
[!V] review %16 ; gate(ci:fail) ∵ flaky warm-cache miss .
[!C] commit frozen ∵ gate(ci:fail) ; gate(commit:skip) .

# multi-model route for cache-key synthesis with risk gate
[!P] schedule synthesize(cache-key) ; models=[opus,gemini,codex] .
[!R] risk hash-collision(cache-key) ; mitigate salt ∪ namespace ; gate(risk:warn) .
[!X] %18 = map([opus,gemini,codex], propose) ; %19 = dedup(%18) ; argmax(%19, entropy) → %20 .
[!C] commit cache-key(%20) ; gate(parse:pass) ; gate(no_cjk:pass) .

# warm CDN edge cache and verify artifact
[!X] %21 = fetch origin/assets ; %22 = write edge-cache(%21) ; open edge-cache → %23 .
[!V] review %23 ; gate(artifact:pass) ; gate(english:pass) ; model=qwen .

# dedup work via set-difference of already-hashed blobs
[!X] %24 = read manifest.lock ; %25 = filter(%24, blobs) ; %26 = %25 ∖ cache(hashed) .
[!X] %27 = map(%26, hash) ; %28 = cache(hashed) ∪ %27 ; fold(%28, index) → %29 .
[!A] artifact %29 ; gate(artifact:pass) ; gate(parse:pass) .

# conditional warm vs cold start with profile bench
[!T] cache(warm) ? launch_agent(reuse) : launch_agent(cold) ∵ minimize startup ; model=gemini .
[!X] %30 = launch_agent(reuse) ; profile %30 → %31 ; %32 = %31 intersect baseline .
[!B] bench %32 ; gate(bench:skip) ∵ no baseline yet ; gate(english:warn) .

# full incremental pipeline: think, plan, execute, review, commit
[!T] reuse %29 ∵ content-hash matches ; combine(%29, delta) → %33 .
[!P] schedule recompute(delta) ; loop(until=delta==empty) ; model=opus .
[!X] %34 = merge(%33, cache(prev)) ; %35 = build next build --skip-env ; diff(%34,%35) → %36 .
[!C] commit incremental(%36) ; gate(ci:pass) ; gate(bench:pass) ; gate(commit:pass) .
```

## budget — Budget/cost control: token budgets, cost-routed model cascade, loop-until-budget, spend ledger, early-stop on diminishing returns.

```text
# Cost-routed cascade: cheapest model that clears confidence
[!X] %draft → map(haiku, tasks) ; %low → filter(conf<0.7, %draft) ; %esc → map(sonnet, %low) model=sonnet.
[!V] %final → combine(%draft∖%low, %esc) ; gate(parse:pass) ∵ all_routed.

# Loop until token budget exhausted
[!P] schedule loop(until=%spent>=%cap) over chunks model=haiku.
[!X] %spent → fold(combine, map(profile, %chunks)) ; cond?%spent>=%cap:%halt:%next.

# Spend ledger artifact appended per call
[!X] %cost → map(profile, %calls) ; %ledger → fold(join, %cost).
[!A] write %ledger → ledger.jsonl ; gate(artifact:pass) ∵ %ledger==%prior∪%cost.

# Early-stop on diminishing returns
[!X] %scores → map(test, %iters) ; %delta → map(diff, %scores).
[!T] cond?argmax(%delta)<%eps:stop:continue ∵ marginal_gain_below_threshold.
[!B] gate(bench:fail) ∵ %spent>%cap before target reached.

# Three-tier escalation: haiku then sonnet then opus
[!X] %t1 → map(haiku, %q) ; %fail → filter(verdict==reject, %t1) models=[haiku,sonnet,opus].
[!X] %t2 → map(sonnet, %fail) ; %t3 → map(opus, filter(verdict==reject, %t2)) ; %ans → combine(%t1∖%fail, %t2, %t3).

# Risk-gated overspend with hard cap
[!R] cond?%spent>0.9*%cap:throttle:proceed ∵ budget_guardrail ; mitigate=switch(model=haiku).
[!X] %out → map(haiku, %remaining) ; gate(bench:warn) ∵ degraded_quality_accepted.

# Bench cost-per-token across candidate models
[!B] %perf → map(bench, models=[haiku,sonnet,gemini,qwen]) ; %ratio → map(profile, %perf).
[!V] %pick → argmax(%ratio) ; gate(bench:pass) ∵ best_quality_per_dollar.

# Dedup cached prompts to cut spend before routing
[!X] %unique → dedup(%prompts) ; %hits → %prompts∖%unique ; %saved → fold(combine, map(profile, %hits)).
[!X] %resp → map(haiku, %unique) model=haiku ; gate(parse:pass).

# Budget split across parallel agents then merge
[!P] schedule launch_agent(model=sonnet) over %shards intersect %inbudget.
[!X] %parts → map(launch_agent, %shards) ; %merged → fold(merge, %parts) ; cond?%spent<=%cap:%commit:%defer.
[!C] commit %merged ∵ gate(commit:pass) join gate(parse:pass).

# Skip costly model when cheap result passes review
[!X] %cheap → map(haiku, %q) model=haiku ; %ok → filter(conf>=0.8, %cheap).
[!V] cond?%ok==%cheap:skip_opus:escalate ; gate(bench:skip) ∵ all_cheap_passed.
```

## parallel — Parallelism: map-reduce, concurrency-cap waves (min(16,cores-2)), barrier vs streaming pipeline, scatter/gather, race-first-to-finish.

```text
# map-reduce over shards: scatter files, fold partial counts into total
[!P] %1 = filter(read("shards/*"), nonempty) ; schedule map over %1
[!X] %2 = map(%1, count_tokens) → %3 = fold(%2, add, 0)
[!V] review %3 ∵ sum(%2) must equal %3 ; gate(parse:pass)
[!C] commit %3 ∵ gate(commit:pass)

# concurrency-cap wave: bound fan-out at min(16,cores-2)
[!P] %1 = read("queue.jsonl") ; cap = min(16,cores-2)
[!X] %2 = map(%1, fetch) loop(until=empty(%1)) ; wave_size = cap
[!R] risk overload ∵ cap>cores ? throttle : proceed ; gate(ci:warn)
[!C] commit %2 ∵ gate(commit:pass)

# barrier join: all workers must finish before aggregate
[!X] %1 = launch_agent(models=[sonnet,sonnet,sonnet], test) → %2 = join(%1)
[!V] review %2 ∵ barrier ? aggregate(%2) : block ; gate(bench:pass)
[!C] commit %2 ∵ gate(commit:pass)

# streaming pipeline: fold each result as it lands, no barrier
[!P] %1 = read("events/*") ; schedule stream
[!X] %2 = map(%1, profile) → %3 = fold(%2, combine) loop(until=eof(%1))
[!B] bench %3 ∵ p95 < 200ms ? ok : regress ; gate(bench:warn)
[!C] commit %3 ∵ gate(commit:pass)

# scatter/gather across model fleet: union distinct findings
[!X] %1 = launch_agent(models=[opus,gemini,codex], open) → %2 = gather(%1)
[!V] %3 = fold(%2, union) ∵ dedup overlapping findings ; gate(english:pass)
[!C] commit %3 ∵ gate(commit:pass)

# race first-to-finish: pick earliest passing branch
[!X] %1 = launch_agent(models=[haiku,sonnet], build) → %2 = argmax(%1, speed)
[!V] review %2 ∵ %2.exit==0 ? keep : fallback(%1) ; gate(ci:pass)
[!C] commit %2 ∵ gate(commit:pass)

# map-reduce with frozen commit: a shard failed parse
[!X] %1 = map(read("logs/*"), test) → %2 = fold(%1, combine)
[!R] risk partial ∵ any(%1:err) ? quarantine : merge ; gate(parse:fail)
[!C] commit %2 ∵ gate(commit:fail) frozen

# concurrency-cap with diff intersection: only changed files re-tested
[!P] %1 = diff("HEAD~1","HEAD") ; cap = min(16,cores-2)
[!X] %2 = intersect(%1, read("tests/*")) → %3 = map(%2, test)
[!V] review %3 ∵ gate(ci:pass) ; gate(no_cjk:skip)
[!C] commit %3 ∵ gate(commit:pass)

# scatter/gather set-difference: gather edits minus conflicted paths
[!X] %1 = launch_agent(models=[sonnet,qwen], edit) → %2 = gather(%1)
[!V] %3 = %2 ∖ filter(%2, conflicted) ∵ drop merge-conflict edits ; gate(artifact:pass)
[!A] write %3 → %4 = join(%3, lockfile) ; gate(parse:pass)
[!C] commit %4 ∵ gate(commit:pass)

# race with barrier fallback: first-done wins, else join all
[!P] %1 = read("specs/*") ; schedule race+barrier
[!X] %2 = map(%1, launch_agent(model=gemini)) → %3 = argmax(%2, finished_at)
[!V] review %3 ∵ %3 ? %3 : join(%2) ; gate(bench:pass) ; gate(english:warn)
[!C] commit %3 ∵ gate(commit:pass)
```

## optimize — Optimizations: hot-path short-circuit, batching, lazy eval, prune search space, speculative execution, dedup-before-expensive-stage.

```text
# hot-path short-circuit: skip validation when cache key unchanged
[!T] read %0=cache.key ; diff %0 prev.key → %1 ; %1==0?short-circuit:revalidate.
[!X] cond? %1==0 : return cached ; revalidate ∵ key drift.
[!V] gate(parse:pass) ; gate(english:pass).

# batching: coalesce per-row writes into one bulk flush
[!P] schedule fold(writes) → batch ∵ amortize round-trips ; flush(threshold=512).
[!X] read %0=pending ; %1=combine(%0) → bulk ; write %1.
[!B] bench %1 → throughput ; gate(bench:pass).
[!C] commit ∵ gate(bench:pass)∧gate(ci:pass).

# lazy eval: defer expensive thunk until first consumer
[!T] map config → thunks %0 ; %1=filter(%0, accessed) ∵ force only demanded.
[!X] loop(until=consumer.requests) ; open %1 → materialize %2.
[!V] gate(parse:pass) ; gate(no_cjk:pass).

# prune search space: drop dominated candidates before scoring
[!T] read %0=candidates ; %1=%0 ∖ dominated ∵ shrink frontier.
[!X] %2=filter(%1, feasible) ; %3=argmax(%2, score) → best.
[!R] gate(bench:warn) ∵ pruning may skip global optimum ; mitigate=widen-beam.

# speculative execution: prefetch likely branch, discard on miss
[!P] schedule fetch branch.likely ∵ hide latency ; cancel-on-miss.
[!X] launch_agent model=haiku → %0 speculative ; cond? predicted==taken : keep %0 : discard %0.
[!V] gate(parse:pass).
[!C] commit ∵ gate(commit:pass).

# dedup-before-expensive-stage: collapse duplicate docs pre-embedding
[!T] read %0=docs ; %1=dedup(%0) ∵ embedding is O(n)·costly.
[!X] %2=map(%1, embed) model=gemini → vectors ; write %2.
[!B] bench %2 ; gate(bench:pass) ; gate(ci:pass).

# hot-path short-circuit: bail early on empty intersection
[!T] read %0=setA ; %1=setB ; %2=%0 intersect %1 → common.
[!X] cond? %2==∅ : return early : process %2 ∵ skip dead work.
[!R] gate(english:fail) ∵ doc lacks rationale ; mitigate=add-note.
[!C] commit frozen ∵ gate(english:fail).

# batching + speculative: prebuild merge set across shards
[!P] schedule combine shards → %0 ∵ one pass beats N ; speculate next-shard.
[!X] %1=%0 ∪ incoming ; merge %1 → unified ; launch_agent models=[sonnet,codex] → %2 verify.
[!V] gate(parse:pass) ; gate(no_cjk:pass) ; gate(artifact:pass).

# lazy eval: stream-fold metrics without buffering
[!T] read %0=stream ; fold(%0, +) → %1 running ∵ avoid full materialize.
[!X] loop(until=eof) ; %2=filter(%1, anomaly) → alerts ; profile %2.
[!B] bench %1 → mem ; gate(bench:skip) ∵ stream too short.

# prune + dedup: cut redundant test targets before CI
[!T] read %0=changed ; %1=dedup(%0) ; %2=%1 ∖ untested ∵ minimize CI fan-out.
[!P] schedule map(%2, select-suite) → %3 ; join %3 → plan.
[!X] test %3 model=qwen → %4 ; argmax(%4, coverage) → gate(ci:pass).
[!C] commit ∵ gate(ci:pass)∧gate(artifact:pass).
```

## gpu — GPU tweaks: device placement, batch-size autotune, mixed precision (fp16/bf16), kernel/memory pinning, multi-GPU shard, OOM-guard + grad-accum fallback.

```text
# device placement: profile per-GPU free mem and bind hot module to least-loaded device
[!X] %0 = profile devices ; %1 = map free_mem %0 ; %2 = argmax %1 ∵ pick-least-loaded.
[!V] read %2 ; gate(parse:pass) ; gate(no_cjk:pass).
[!C] commit %2 ∵ device-bind frozen-config.

# batch-size autotune: sweep candidates, bench throughput, keep argmax that clears OOM
[!P] schedule sweep batch∈[8,16,32,64] model=haiku.
[!X] %0 = build harness ; %1 = map bench %0 ; %2 = filter clears_oom %1 ; %3 = argmax %2.
[!V] gate(bench:warn) ∵ %3 within 3% of runner-up ; gate(english:pass).
[!C] commit %3.

# mixed precision: enable bf16 on supported set, fp16 elsewhere, verify no NaN regression
[!X] %0 = profile gpus ; %1 = filter supports_bf16 %0 ; %2 = %0 ∖ %1.
[!X] %3 = edit cfg(%1, bf16) ; %4 = edit cfg(%2, fp16) ; %5 = combine %3 %4.
[!V] test %5 ; cond(nan_seen)?gate(ci:fail):gate(ci:pass).
[!C] commit %5 ∵ frozen-if(ci:fail).

# kernel + pinned-memory tuning: enable pinned host buffers and fused kernels, diff before/after
[!X] %0 = read dataloader ; %1 = edit %0 pin_memory ; %2 = edit %1 fused_kernel.
[!B] %3 = bench %1 ; %4 = bench %2 ; %5 = argmax join(%3,%4).
[!V] diff %0 %2 ; gate(parse:pass) ; gate(no_cjk:skip).

# multi-GPU shard: partition layers across visible devices via set-union, launch shard agents
[!P] schedule shard across devices models=[opus,sonnet].
[!X] %0 = profile devices ; %1 = filter visible %0 ; %2 = map partition %1.
[!X] %3 = launch_agent shard(%2) model=codex ; %4 = %2 ∪ %3.
[!C] commit %4 ∵ shard-plan ; gate(commit:pass).

# OOM-guard with grad-accum fallback: on OOM trip mitigation, freeze commit on failed bench
[!X] %0 = build train_step ; %1 = bench %0 batch=64.
[!R] cond(oom)?grad_accum:continue ∵ mitigate-OOM ; gate(bench:fail).
[!C] commit %1 ∵ frozen ∵ gate(bench:fail).

# device placement vs DataParallel: intersect feasible devices with NVLink peers, route remainder
[!X] %0 = profile devices ; %1 = filter feasible %0 ; %2 = filter nvlink_peer %0.
[!X] %3 = intersect %1 %2 ; %4 = %1 ∖ %3 ; %5 = combine %3 %4.
[!V] read %5 ; gate(english:pass) ; gate(artifact:pass).
[!C] commit %5.

# batch autotune under fixed VRAM: loop raise batch until OOM, fold peak mem, keep last-good
[!X] %0 = loop(until=oom) map bench raise_batch ; %1 = fold peak_mem %0 ; %2 = filter last_good %0.
[!V] gate(bench:pass) ∵ %2 stable 5-iter ; gate(parse:pass).
[!C] commit %2 ∵ %1 → headroom-report.

# mixed precision + loss-scale: dedup precision configs, autotune scale, gate on overflow rate
[!P] schedule fp16+dynamic_scale model=qwen.
[!X] %0 = map gen_cfg scales ; %1 = dedup %0 ; %2 = map bench %1 ; %3 = argmax %2.
[!R] cond(overflow_hi)?halve_scale:keep ∵ mitigate-overflow ; gate(ci:warn).
[!A] write %3 → checkpoint ; gate(artifact:pass).

# multi-GPU shard rebalance: diff old vs new placement, merge shard agents, commit if ci clears
[!X] %0 = read placement ; %1 = profile devices ; %2 = map rebalance %1.
[!V] %3 = diff %0 %2 ; gate(ci:pass) ; gate(no_cjk:pass).
[!X] %4 = merge launch_agent(%2) model=gemini.
[!C] commit %4 ∵ %3 → rebalance-applied.
```

## schedule — Scheduling: cron/interval, debounce, backpressure, rate-limit, priority queue, deadline-aware preemption.

```text
# cron-driven nightly index rebuild with parse gate
[!P] %1 = cron("0 3 * * *") ; %2 = read("index.cfg") → %1
[!X] %3 = build(%2) → bench(%3) ; %4 = profile(%3)
[!V] gate(parse:pass) ; gate(bench:pass) ∵ %4 < deadline
[!C] commit(%3) cond?gate(bench:pass):skip

# fixed-interval poll loop with dedup of fetched events
[!P] %1 = loop(until=interval>=30s) ; %2 = fetch("/events?since=%cursor")
[!X] %3 = map(%2, parse) → %4 = dedup(%3) ∵ at-most-once
[!A] write("events.ndjson", %4) ; gate(artifact:pass)

# debounce burst of file-change triggers into one build
[!P] %1 = read("fswatch.stream") ; %2 = fold(%1, debounce=200ms) → %3
[!X] %4 = build(%3) cond?%2.count>0:skip ; gate(ci:pass)
[!C] commit(%4)

# backpressure: drop low-priority work when queue saturates
[!T] %1 = read("queue.depth") ∵ bounded-buffer
[!P] %2 = %1 > hwm ? filter(intake, priority>=high) : intake
[!X] %3 = map(%2, run) → %4 = profile(%3) ; gate(bench:warn) ∵ shed-load

# token-bucket rate-limit on outbound API with model routing
[!P] %1 = loop(until=tokens>=1) ; %2 = fetch("/api/sync") → %1 ∵ 10rps
[!X] model=haiku %3 = map(%2, summarize) → %4 = filter(%3, err) ; gate(parse:pass)
[!V] gate(english:pass) ∵ no_cjk in %4

# priority queue merge with deadline-aware argmax dispatch
[!P] %1 = join(hot.q, cold.q) → %2 = argmax(%1, priority/age)
[!X] models=[opus,sonnet] %3 = launch_agent(%2, deadline=5m) → %4 = profile(%3)
[!V] gate(bench:pass) ∵ %4.p99 < deadline ; gate(artifact:pass)
[!C] commit(%3) cond?gate(bench:pass):skip

# deadline-aware preemption: cancel overrunning job, reschedule tail
[!P] %1 = launch_agent(job, deadline=2m) ; %2 = %1.elapsed > deadline ? preempt : %1
[!X] %3 = %2 == preempt ? edit("backlog", requeue) : write("done", %1) ∵ tail-latency
[!R] gate(commit:fail) ∵ preempted-incomplete
[!C] commit frozen cond?gate(commit:fail):skip

# cron + debounce combo: hourly digest deduped across sources
[!P] %1 = cron("0 * * * *") → %2 = combine(src.a, src.b, src.c)
[!X] %3 = fold(%2, debounce=5s) → %4 = dedup(%3) ; model=qwen %5 = map(%4, classify)
[!A] write("digest.md", %5) ; gate(artifact:pass) ; gate(no_cjk:pass)

# rate-limit + backpressure: adaptive shed under sustained load
[!T] %1 = read("rps.window") ∵ sliding-window
[!P] %2 = loop(until=rps<=limit) ; %3 = %1 > limit ? (intake ∖ priority>=low) : (intake ∪ shed.buffer)
[!X] %4 = map(%3, run) → %5 = filter(%4, err) ; gate(ci:warn) ∵ degraded

# starvation-safe priority queue with aging and gate-frozen commit
[!T] %1 = read("pq.snapshot") ∵ aging prevents starvation
[!P] %2 = argmax(%1, priority + age*k) → %3 = intersect(%2, ready)
[!X] models=[codex,gemini] %4 = launch_agent(%3, deadline=10m) → bench(%4)
[!V] gate(bench:fail) ∵ %4.p99 > deadline ; gate(commit:fail)
```

All 10 verified against the closed vocabularies (gate names, verbs, funcs, models, registers) and structural rules. Deliverable also saved at /Users/lodripeter/../tmp/schedule_arp.txt (absolute: /tmp/schedule_arp.txt).

Coverage: (1) cron, (2) interval/poll, (3) debounce, (4) backpressure, (5) rate-limit, (6) priority queue, (7) deadline-aware preemption, plus combos (8) cron+debounce, (9) rate-limit+backpressure, (10) priority-queue+deadline+starvation. Collectively exercises all 8 funcs (combine/join/intersect/map/filter/argmax/dedup/fold), all set-ops (∖, ∪, intersect), → ∵ cond?a:b loop(until=) gate(), all 6 models via both model= and models=[...], all 7 gate names, and the [!C] freeze rule (examples 7 and 10).

## observe — Observability/bench: tracing spans, metric capture, perf gate (p99/latency), profile→optimize→re-bench loop, regression detection.

```text
# Capture distributed trace spans across request path
[!X] fetch spans(traceID=%t) → %raw ; map(%raw, extract_duration) → %durs ; fold(%durs, sum) → %total.
[!V] gate(parse: %raw≠∅ ? pass : fail) ; %total ∵ root-span wall-clock.

# Emit p99 latency metric and gate on threshold
[!X] read metrics(svc=checkout, window=5m) → %m ; argmax(%m.percentiles, p99) → %p99.
[!B] bench(%p99, SLO=250ms) → %verdict ; gate(bench: %p99<250ms ? pass : fail).
[!C] gate(bench:fail) ? freeze : commit ∵ no SLO breach merges.

# Profile hot path then optimize and re-bench until passing
[!P] schedule profile→edit→bench loop ; model=haiku.
[!X] profile cpu(target=serializeJSON) → %flame ; argmax(%flame.frames, self_time) → %hot.
[!X] loop(until=gate(bench:pass)) edit %hot → %patch ; bench %patch → %lat ; gate(bench: %lat<%baseline ? pass : warn).
[!C] commit %patch ∵ latency below baseline.

# Detect regression by diffing head bench against baseline
[!X] bench head → %head ; bench baseline → %base ; diff(%head, %base) → %delta.
[!R] %head ∖ %base → %regressed ; gate(bench: %regressed=∅ ? pass : fail) ; mitigate ∵ block on any slower case.

# Aggregate metrics from multiple regions and dedup spans
[!X] models=[opus,gemini] ; fetch metrics(region=[us,eu,ap]) → %r ; combine(%r) → %all ; dedup(%all.spans) → %clean.
[!V] gate(no_cjk: pass) ; %clean ∵ cross-region union deduplicated.

# Correlate trace and log timelines via set intersection
[!X] read spans(svc=auth) → %s ; read logs(svc=auth) → %l ; intersect(%s.window, %l.window) → %overlap.
[!T] %overlap → root_cause_candidates ∵ co-occurring error window ; filter(%overlap, level=error) → %err.

# Gate CI build on bench regression with commit freeze
[!B] bench suite=micro → %r ; gate(bench: %r.p99≤%budget ? pass : fail).
[!V] gate(ci: %r.exit=0 ? pass : fail) ; gate(artifact: %r.report≠∅ ? pass : fail).
[!C] (gate(bench:fail) ∪ gate(ci:fail)) ? freeze : commit %r.report.

# Fold span tree to compute critical-path latency
[!X] fetch trace(id=%t) → %tree ; fold(%tree, max_child) → %critpath ; map(%critpath, span_name) → %names.
[!A] write report(critpath=%critpath, spans=%names) → %doc ; gate(artifact: %doc≠∅ ? pass : fail).

# Bisect performance regression across commit range
[!P] schedule bisect over range=[abc123..def456] ; model=sonnet.
[!X] loop(until=%delta<5%) bench %commit → %lat ; diff(%lat, %baseline) → %delta ; %lat → %culprit.
[!R] %culprit ∵ first commit exceeding budget ; gate(bench: %culprit=∅ ? pass : fail) ; mitigate=revert.

# Launch parallel bench agents and join sharded results
[!P] schedule launch_agent bench(shards=4) ; models=[haiku,qwen].
[!X] map([s0,s1,s2,s3], bench) → %parts ; join(%parts) → %merged ; argmax(%merged, latency) → %worst.
[!B] bench(%worst, SLO=300ms) → %v ; gate(bench: %v<300ms ? pass : warn).
[!C] commit %merged ∵ warn non-blocking, only gate(bench:fail) freezes.
```
