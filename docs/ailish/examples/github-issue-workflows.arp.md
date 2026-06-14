# AI-lish V1 — example library: GitHub-issue browsing & triage workflows

100 ARP (AI-lish V1) commands across 10 categories, themed for browsing/triaging open-source GitHub issues. Notation: the V1 RFC / cheatsheet under docs/ailish/. Doubles as parser-conformance fixtures.

## triage — Issue triage + auto-labeling: browse open issues, classify (bug/feat/docs), label, route to owner, detect stale.

```text
# Simple browse-filter-classify pass
[!X] %0 browse gh:repo/cli/cli issues?state=open → %1 filter(%0, no:label) → %2 map(%1, body→{bug,feat,docs}) ∵ keyword-match model=haiku

# Full pipeline: triage open issues, label, commit
[!P] schedule browse→classify→label→commit nightly model=sonnet
[!X] %0 browse gh:repo/vercel/next.js issues?state=open&per_page=100 → %1 map(%0, argmax(score{bug,feat,docs})) → %2 edit(%1, +label) model=sonnet
[!V] %3 review(%2) gate(parse:pass) gate(english:pass)
[!C] %4 commit(%2) ∵ gate(*:pass)

# Stale detection via set-difference
[!X] %0 browse gh:repo/rust-lang/rust issues?state=open → %1 browse gh:repo/rust-lang/rust issues?state=open&since=90d → %2 %0 ∖ %1 ∵ no-update-90d
[!A] %3 write(stale.md, %2) → %4 edit(%2, +label:stale)

# Owner routing with conditional
[!X] %0 fetch gh:issue/facebook/react/28000 → %1 map(%0, area) → %2 (area=renderer)?owner:@sebmarkbage:owner:@gaearon → %3 open(gh:assign %2)
[!V] %4 review(%3) gate(no_cjk:pass)

# Multi-model classification with intersect for high-confidence
[!X] %0 browse gh:repo/tensorflow/tensorflow issues?state=open&labels= → %1 map(%0, label) models=[opus,gemini,codex] → %2 intersect(%1) ∵ consensus-only → %3 edit(%2, +label)
[!C] %4 commit(%3) gate(commit:pass)

# Gate fails: commit freezes, route to human review
[!X] %0 browse gh:repo/kubernetes/kubernetes issues?state=open → %1 map(%0, classify) model=qwen
[!V] %2 review(%1) gate(english:fail) ∵ ambiguous-titles
[!C] %3 commit(%1) gate(*:fail) → freeze ∵ gate(english:fail) → %4 open(gh:assign @triage-team)

# Bench classifier accuracy before rollout
[!P] schedule bench→review→commit model=sonnet
[!X] %0 browse gh:repo/pytorch/pytorch issues?state=open&per_page=50 → %1 map(%0, label) model=haiku
[!B] %2 test(%1, gold-labels) gate(bench:pass) ∵ f1>=0.85
[!C] %3 commit(%1) ∵ gate(bench:pass)

# Risk-gated auto-close of stale issues
[!R] %0 browse gh:repo/nodejs/node issues?state=open&labels=stale → %1 filter(%0, no-activity>180d) gate(parse:warn) ∵ guard-false-positive → %2 edit(%1, comment:closing-soon)
[!C] %3 commit(%2) gate(commit:pass)

# Dedup duplicate-report cluster, assign single owner
[!X] %0 search gh:repo/golang/go issues?q=crash+open → %1 dedup(%0, title-sim) → %2 argmax(%1, reactions) → %3 open(gh:link-duplicates %2) model=gemini
[!A] %4 write(dupes.json, %0 ∖ %2)

# Merge label sets across two classifiers, commit union
[!X] %0 browse gh:repo/django/django issues?state=open → %1 map(%0, label) model=opus → %2 map(%0, label) model=codex → %3 %1 ∪ %2 ∵ recall-over-precision → %4 edit(%3, +labels)
[!V] %5 review(%4) gate(parse:pass) gate(no_cjk:skip)
[!C] %6 commit(%4) ∵ gate(*:pass)
```

## repro — Bug reproduction + verification: read issue, build minimal repro, run it, confirm/refute, attach evidence.

```text
# Triage one open issue: read, repro, confirm
[!P] plan(read→repro→run→confirm) → %g0
[!X] %i = browse "gh issue view 4821 --repo vercel/next.js" model=haiku
[!X] %r = write repro.test.ts ∵ %i ; %run = test %r model=sonnet → gate(parse:pass)
[!C] commit "repro #4821 confirmed" ∵ %run(fail-as-expected) gate(artifact:pass)

# Search labeled bugs, build minimal repro for top hit
[!X] %hits = search "gh issue list --repo facebook/react --label bug --state open" model=haiku
[!T] %top = argmax(%hits, reactions) ∵ signal>noise
[!X] %repro = write min.jsx ∵ fetch "gh issue view %top --json body,title" → %r2 = test %repro → gate(no_cjk:pass) gate(parse:pass)

# Refute a stale issue (cannot reproduce on current main)
[!X] %body = browse "https://github.com/expressjs/express/issues/5512" model=haiku
[!X] %case = write refute_repro.js ∵ %body ; %out = test %case model=sonnet
[!R] gate(artifact:pass) ? %out=green : risk(maybe-fixed-upstream) → mitigate(diff %body.version vs HEAD)
[!V] review %out → comment "cannot reproduce on v5.0.1" model=opus

# Fan-out: triage three issue URLs, dedup repro steps
[!X] %a = fetch "gh issue view 12001 -R denoland/deno --json body" model=haiku ; %b = fetch "gh issue view 12044 -R denoland/deno --json body" model=haiku ; %c = fetch "gh issue view 12099 -R denoland/deno --json body" model=haiku
[!T] %steps = dedup(map(combine(%a,%b,%c), extract_repro)) ∵ overlap
[!A] write triage_matrix.md ∵ %steps → gate(english:pass)

# Bisect-driven repro confirmation across commits
[!X] %iss = browse "gh issue view 887 -R sveltejs/svelte" model=sonnet
[!X] %repro = write bug887.spec.ts ∵ %iss ; %a = test %repro@HEAD ; %b = test %repro@v4.2.0
[!T] %verdict = (%a:fail ∖ %b:pass) ∵ regression-window → gate(bench:pass)
[!C] commit "confirm #887 regressed since v4.2.0" gate(commit:pass)

# Attach evidence: run repro, capture logs, post to issue
[!X] %r = write repro.py ∵ fetch "gh issue view 3310 -R psf/requests --json body,comments" model=haiku
[!X] %log = test %r model=sonnet → gate(parse:pass)
[!A] write evidence.txt ∵ %log → %ev
[!X] commit %ev ; browse "gh issue comment 3310 -R psf/requests --body-file evidence.txt" ∵ gate(artifact:pass)

# Cross-repo: same symptom in two projects, intersect causes
[!X] %x = search "gh search issues 'segfault tokenizer' --repo huggingface/tokenizers" model=haiku ; %y = search "gh search issues 'segfault tokenizer' --repo openai/tiktoken" model=haiku
[!T] %shared = intersect(map(%x,root_cause), map(%y,root_cause)) ∵ common-dep
[!X] %repro = write shared_repro.rs ∵ %shared → test %repro → gate(no_cjk:pass) gate(parse:pass)

# Conditional repro: needs flaky network, gate then mitigate
[!X] %i = browse "gh issue view 671 -R aiohttp/aiohttp --json body" model=haiku
[!X] %r = write flaky_repro.py ∵ %i ; %run = test %r model=sonnet
[!R] %run=flaky ? mitigate(launch_agent retry×5 model=haiku) → %stable : gate(parse:pass)
[!V] review %stable → comment "reproduces 4/5 under packet loss" gate(english:pass)

# Multi-model repro: draft with haiku, verify with opus
[!X] %iss = fetch "gh issue view 2055 -R pallets/flask --json title,body" model=haiku
[!A] %draft = write repro_flask.py ∵ %iss models=[haiku,sonnet]
[!X] %check = test %draft model=opus → gate(artifact:pass) gate(parse:pass)
[!C] commit "minimal repro for #2055" ∵ %check(fail-as-expected) gate(commit:pass)

# Refute-or-confirm pipeline with frozen commit on gate fail
[!X] %i = browse "https://github.com/golang/go/issues/64321" model=sonnet
[!X] %r = write issue64321_test.go ∵ %i ; %out = test %r model=sonnet → gate(parse:fail)
[!T] %verdict = %out=parse_err ? refute(invalid-repro) : confirm ∵ build-must-pass
[!C] commit(frozen) ∵ gate(parse:fail) → review %verdict model=opus
```

## security — Dependency + security-advisory handling: scan deps, match CVE/GHSA, open fix PR, gate on ci.

```text
# Triage open dependency-advisory issues and synthesize a fix PR
[!P] browse gh "repo:acme/api is:issue is:open label:security" model=haiku → %1
[!X] search %1 "GHSA-|CVE-" → %2 ; filter %2 fixable → %3 ∵ only-issues-with-upstream-patch
[!X] fetch "https://github.com/advisories/GHSA-jr5f-v2jv-69x6" model=opus → %4 ; edit package-lock.json combine(%3,%4) → %5
[!C] open pr %5 ? gate(ci:pass) : freeze ∵ commit-blocked-until-green

# Skim a noisy advisory thread, drop non-English noise, escalate the real CVE
[!X] browse gh "https://github.com/openssl/openssl/issues/24221" model=haiku → %1
[!V] read %1 → %2 gate(english:warn) gate(no_cjk:warn) ∵ thread-has-translated-replies
[!X] search %2 "CVE-2024-" → %3 ; launch_agent triage(%3) model=opus → %4
[!C] commit %4 gate(parse:pass)

# Fan-out review of three candidate fix PRs referenced from one issue
[!X] fetch "https://github.com/acme/web/issues/881" → %1 ; search %1 "#\d+" → %2
[!X] map browse(%2) models=[haiku,sonnet,codex] → %3 ; argmax %3 by-ci-health → %4
[!V] diff %4 baseline → %5 gate(ci:pass) gate(artifact:pass)
[!C] merge %4 ? gate(commit:pass) : skip ∵ awaiting-maintainer-ack

# Cross-reference open issues against the GHSA database, dedup duplicates
[!X] browse gh "org:acme is:issue is:open in:title GHSA" model=haiku → %1
[!X] fetch "https://github.com/advisories?query=ecosystem:npm" → %2 ; intersect %1 %2 → %3
[!T] dedup %3 → %4 ∵ same-CVE-filed-across-repos
[!A] write triage-report.md %4 gate(artifact:pass) gate(no_cjk:pass)

# Promote a confirmed vuln issue into a patched lockfile and gate on CI
[!P] search gh "repo:acme/cli label:vuln is:open" → %1
[!X] fetch "https://github.com/acme/cli/issues/302" model=sonnet → %2 ; build deps %2 → %3 gate(parse:fail)
[!R] read %3 → %4 ∵ resolution-conflict-must-mitigate
[!C] open pr %4 ? gate(ci:pass) : freeze ∵ parse-gate-failed-upstream

# Subtract already-fixed advisories from the open backlog
[!X] browse gh "repo:acme/core is:issue is:open label:security" → %1
[!X] fetch "https://github.com/acme/core/security/advisories" → %2 ; %1 ∖ %2 → %3 ∵ remove-resolved
[!V] map read(%3) model=haiku → %4 gate(english:pass)
[!C] commit %4 gate(commit:pass)

# Verify an advisory's affected-range claim before opening a fix
[!X] fetch "https://github.com/advisories/GHSA-9w4x-2hr5-q3qj" model=opus → %1
[!X] search %1 "affected: <" → %2 ; read package.json → %3 ; intersect %2 %3 → %4
[!B] test %4 → %5 gate(bench:warn) ∵ regression-suite-slow-not-blocking
[!C] open pr combine(%4,%5) ? gate(ci:pass) : skip

# Triage a stale CVE issue, route patch synthesis to codex
[!X] browse gh "https://github.com/acme/auth/issues/57" model=haiku → %1
[!T] read %1 → %2 ∵ confirm-still-reproducible-on-main
[!X] launch_agent patch(%2) model=codex → %3 ; diff %3 baseline → %4 gate(parse:pass) gate(ci:pass)
[!C] open pr %4 gate(commit:pass)

# Join issue metadata with advisory severity, prioritize by score
[!X] search gh "org:acme is:issue is:open label:dependencies" model=haiku → %1
[!X] map fetch(%1) → %2 ; join %2 ghsa-severity → %3 ; argmax %3 by-cvss → %4
[!V] read %4 → %5 gate(artifact:pass) gate(no_cjk:pass)
[!C] commit %5 ? gate(ci:pass) : freeze ∵ unverified-severity

# Union two repos' open security issues, draft a consolidated upgrade PR
[!X] browse gh "repo:acme/api is:issue is:open label:cve" → %1 ; browse gh "repo:acme/sdk is:issue is:open label:cve" → %2
[!X] %1 ∪ %2 → %3 ; filter %3 npm-ecosystem → %4 ∵ shared-transitive-dep
[!X] edit pnpm-lock.yaml %4 model=opus → %5 ; build deps %5 → %6 gate(parse:pass)
[!C] open pr combine(%5,%6) ? gate(ci:pass) : skip ∵ wait-for-monorepo-check
```

## ci-fail — CI failure diagnosis: fetch failing run logs, localize, propose fix, verify green.

```text
# Triage open issue reporting red CI, localize, fix, verify green
[!X] %1=browse gh:repo/acme/widgets/issues?label=ci-failure model=haiku ; %2=filter(%1, "build failed") → %3=fetch gh:run/%2.run_url model=haiku
[!T] %4=read %3 ∵ localize failing job model=sonnet ; %5=argmax(%4.errors, severity)
[!A] %6=edit src/index.ts → write %6 model=sonnet
[!C] commit %6 ∵ green-on-rerun ; gate(ci:pass) gate(commit:pass)

# Dependency bump issue: fetch matrix logs, intersect failures across versions
[!X] %1=search gh:repo/oss/lib/issues "node 20 CI broken" model=haiku ; %2=fetch gh:run/%1.run_id/jobs model=sonnet
[!T] %3=map(%2.jobs, parse_log) → %4=intersect(%3) ∵ failure common to node18 ∪ node20 model=sonnet
[!A] %5=edit package.json ∵ pin transitive dep ; test %5 → gate(ci:pass) gate(parse:pass)
[!C] commit %5 ; gate(commit:pass)

# Flaky test reported in issue: confirm via rerun, propose retry guard
[!P] schedule: browse → fetch → diff → verify model=sonnet
[!X] %1=browse gh:repo/x/y/issues/4412 model=haiku ; %2=fetch gh:run/%1.failed_run model=haiku → %3=fetch gh:run/%1.passed_run model=haiku
[!V] %4=diff %2 %3 ∵ nondeterministic order ; gate(ci:warn) gate(english:pass)
[!C] commit none ∵ flake unconfirmed ; gate(commit:skip)

# Lint failure surfaced in issue: localize, format, verify, ensemble review
[!X] %1=fetch gh:repo/a/b/issues/77 model=haiku ; %2=fetch gh:run/%1.run_url logs=eslint model=haiku
[!A] %3=filter(%2.lines, "error") → %4=edit src/util.js model=sonnet ; test %4
[!V] %5=combine(review(%4, models=[sonnet,gemini])) → %6=argmax(%5, confidence) ∵ pick strongest verdict
[!C] commit %4 ; gate(ci:pass) gate(no_cjk:pass) gate(commit:pass)

# OOM in CI from issue thread: localize hungry step, propose cap, freeze on fail
[!X] %1=browse gh:repo/big/mono/issues?label=oom model=haiku ; %2=fetch gh:run/%1.run_id/logs model=sonnet
[!T] %3=argmax(%2.steps, mem_peak) ∵ jest heap overflow model=sonnet
[!A] %4=edit jest.config.js → test %4 ; gate(ci:fail) ∵ still over limit
[!C] commit %4 ∵ frozen ; gate(commit:fail)

# Snapshot drift issue: fetch diff artifacts, dedupe noise, propose update
[!X] %1=search gh:repo/ui/kit/issues "snapshot mismatch" model=haiku → %2=fetch gh:run/%1.run_id/artifacts model=sonnet
[!T] %3=dedup(%2.snapshots) → %4=map(%3, classify_drift) ∵ separate intentional ∖ regression model=sonnet
[!A] %5=edit __snapshots__/Button.snap ? %4.intentional : edit src/Button.tsx model=sonnet ; test %5
[!C] commit %5 ; gate(artifact:pass) gate(ci:pass) gate(commit:pass)

# Compile error in issue: localize across files, verify build green
[!X] %1=fetch gh:repo/lang/tool/issues/901 model=haiku ; %2=fetch gh:run/%1.run_url logs=tsc model=sonnet
[!T] %3=filter(%2.diagnostics, "TS2345") → %4=map(%3, locate_symbol) model=sonnet ∵ type narrowing lost
[!A] %5=edit %4 → build %5 ; gate(ci:pass) gate(parse:pass) gate(commit:pass)

# Cross-issue dedup: join failing-run links from duplicate reports
[!X] %1=search gh:repo/web/app/issues "pipeline red" model=haiku ; %2=browse gh:repo/web/app/issues?label=duplicate model=haiku
[!T] %3=join(%1, %2, by=run_id) → %4=dedup(%3) ∵ collapse same failure ; %5=fetch gh:run/%4.run_id model=sonnet
[!V] %6=review(%5, models=[sonnet,gemini,codex]) → argmax(%6, agreement) ; gate(english:pass) gate(no_cjk:pass)

# i18n PR issue with non-latin logs: gate no_cjk on fix output
[!X] %1=fetch gh:repo/intl/site/issues/55 model=haiku → %2=fetch gh:run/%1.run_url model=sonnet
[!A] %3=edit locales/strings.json ∵ escape unicode keys model=sonnet ; test %3
[!R] %4=filter(%3.diff, contains_cjk) ∵ must strip from source ; gate(no_cjk:warn)
[!C] commit %3 ? %4=∅ : commit none ; gate(commit:pass)

# Perf regression issue: fetch bench logs, compare baseline, propose fix
[!P] schedule: browse → fetch bench → bench compare → commit model=sonnet
[!X] %1=browse gh:repo/perf/core/issues?label=regression model=haiku ; %2=fetch gh:run/%1.run_id logs=bench model=sonnet
[!B] %3=combine(%2.samples) → %4=diff %3 baseline ∵ p99 up 30pct ; gate(bench:fail)
[!C] commit none ∵ awaiting fix ; gate(commit:skip)
```

## flaky — Flaky-test hunting: rerun N times, detect nondeterminism, bisect, quarantine or fix.

```text
# triage flaky-labeled issues, dedup dup reports, route per repo
[!T] %1 = search("org:nodejs label:flaky state:open") ∵ surface known nondeterministic suites
[!X] %2 = browse(%1) → %3 = dedup(%2) ∵ collapse duplicate flaky reports ; gate(parse:pass)
[!X] %4 = map(%3, fetch) model=haiku → %5 = filter(%4, "has:reproduction")

# rerun candidate test N times, diff run outputs, quarantine-or-fix on ci
[!X] %1 = fetch("https://github.com/pytest-dev/pytest/issues/4321") → %2 = test(%1, runs=200) model=sonnet
[!X] %3 = diff(%2) ∵ output variance across reruns == nondeterminism
[!C] gate(ci:pass)?commit(%3, msg="fix flaky"):quarantine(%1, tag="@flaky")

# bisect flaky regression: candidate commits minus known-good window
[!P] schedule launch_agent(bisect, span="v18..v20") models=[codex,opus]
[!X] %1 = search("repo:vercel/next.js label:flaky") → %2 = combine(%1, "git log v18..HEAD")
[!X] %3 = %2 ∖ "known-good@v18.3" → %4 = argmax(map(%3, test), key=failrate) model=gemini
[!B] bench(%4, runs=500) → gate(bench:warn) ∵ flake reproduces 6% under load

# intersect CI-failing and locally-failing to isolate true flakes
[!X] %1 = fetch("https://github.com/rust-lang/rust/issues/9911") → %2 = test(%1, env="ci")
[!X] %3 = test(%1, env="local") → %4 = intersect(%2, %3) ∵ flaky iff fails in both nondeterministically
[!R] gate(ci:fail) → mitigate: rerun(%4, runs=50) before quarantine ∵ avoid masking real regression

# union flaky issue sets across forks, fan-out triage agents
[!P] schedule launch_agent(triage, repos=["upstream","fork-a","fork-b"]) models=[haiku,qwen,sonnet]
[!X] %1 = search("upstream label:flaky") ∪ search("fork-a label:flaky") ∪ search("fork-b label:flaky")
[!X] %2 = combine(%1, browse) → %3 = dedup(%2) ; gate(no_cjk:pass)

# full pipeline: triage, reproduce, fix, merge with english + no_cjk gates
[!P] schedule test → diff → edit → merge ∵ flaky issue #7782 blocks release
[!X] %1 = browse("https://github.com/jestjs/jest/issues/7782") → %2 = test(%1, runs=100) model=opus
[!V] %3 = diff(%2) → review(%3) gate(english:pass) gate(no_cjk:pass) gate(artifact:pass)
[!C] %4 = edit(%1, "await flushPromises()") → gate(ci:pass)?merge(%4):commit(%4, msg="wip")

# rank flakiest tests by failure rate, benchmark stability
[!X] %1 = search("repo:golang/go label:flaky is:open") → %2 = map(%1, fetch) model=qwen
[!B] %3 = argmax(%2, key=flakerate) → bench(%3, runs=1000) gate(bench:pass) ∵ confirm <0.1% after fix

# risky autofix: edit timing assumptions, gate artifact before write
[!X] %1 = fetch("https://github.com/denoland/deno/issues/5550") → %2 = test(%1, runs=80) model=codex
[!R] %3 = edit(%2, "replace sleep(100) with waitFor") → gate(artifact:warn) ∵ heuristic patch, needs human review
[!A] write(%3, path="patches/5550.diff") gate(parse:pass)

# join flaky issue to its blocking PR, open tracking issue if unfixed
[!X] %1 = search("label:flaky") → %2 = join(%1, search("label:flaky linked:pr"), on=number)
[!X] %3 = filter(%2, "pr:none") → open(%3, title="quarantine flaky", label="needs-fix")
[!C] commit(%3, msg="quarantine batch") ∵ frozen gate(commit:fail) ∵ english gate unresolved on 2 issues

# skip stable issues, read repro, classify nondeterminism source
[!X] %1 = search("label:flaky") → %2 = filter(%1, "reruns>10") gate(ci:skip) ∵ already stabilized upstream
[!X] %3 = read(%2, "repro.md") → %4 = map(%3, classify) models=[gemini,sonnet] → diff(%4) ∵ agree on root cause
```

## pr-review — PR review + merge-train: review diff (multi-model), adversarial verify findings, gate, merge only if fleet-safe.

```text
# Triage open issues, fan-out review, merge if fleet-safe
[!P] schedule browse→search→review→merge ∵ issue-driven merge-train
[!X] %1=browse gh://acme/api/issues?state=open ; %2=filter(%1, label:bug) → %3=search %2 "regression" ; %4=fetch gh://acme/api/pull/812
[!V] %5=review %4 models=[opus,sonnet,gemini] ∵ multi-model adversarial verify ; gate(parse:pass) gate(english:pass)
[!C] gate(ci:pass)?merge %4:hold ∵ commit frozen if any gate(*:fail)

# Dedup duplicate issue reports before gating the PR
[!X] %1=browse gh://core/runtime/issues?label=crash model=haiku ; %2=dedup %1 → %3=map(%2, fetch) ∵ collapse dup crash reports
[!V] %4=review %3 join (fetch gh://core/runtime/pull/4501) models=[opus,codex] ; gate(no_cjk:pass) ∵ upstream report has CJK trace
[!C] gate(commit:pass)?merge:hold

# Difference set: untriaged issues only, single-model risk pass
[!X] %1=search gh://web/ui/issues "memory leak" ; %2=browse gh://web/ui/issues?label=triaged → %3=%1 ∖ %2 ∵ untriaged remainder
[!R] %4=review %3 model=sonnet ; gate(bench:warn) ∵ leak repro flaky, mitigate before merge-train
[!C] gate(ci:pass)?merge:hold

# Adversarial verify findings, freeze on failing gate
[!X] %1=fetch gh://data/etl/pull/77 ; %2=browse gh://data/etl/issues?milestone=v3 → %3=intersect(%1,%2) ∵ PR closes milestone issues
[!V] %4=review %3 models=[opus,gemini,qwen] ∵ adversarial cross-check ; gate(english:fail) ∵ finding text unverifiable
[!C] gate(parse:skip) ; commit frozen ∵ gate(english:fail)

# Argmax highest-severity issue drives merge decision
[!P] schedule triage→argmax→review→merge
[!X] %1=browse gh://infra/k8s/issues?label=severity → %2=argmax(%1, severity) ∵ pick worst regression ; %3=fetch gh://infra/k8s/pull/990
[!V] %4=review combine(%2,%3) models=[opus,sonnet] ; gate(bench:pass) gate(ci:pass)
[!C] gate(commit:pass)?merge %3:hold ∵ fleet-safe only on all pass

# Union of two label queues, multi-model triage
[!X] %1=search gh://lang/parser/issues "panic" ; %2=browse gh://lang/parser/issues?label=P0 → %3=%1 ∪ %2 ∵ merge panic+P0 queues
[!V] %4=review map(%3, fetch) models=[gemini,codex,haiku] ; gate(no_cjk:warn) gate(parse:pass)
[!C] gate(ci:pass)?merge:hold

# Single-frame transparent rewrite via gh issue search
[!X] %1=browse gh://acme/sdk/issues?state=open model=haiku → %2=filter(%1, label:good-first-issue) ∵ cheap triage pass, no merge yet

# Bench gate decides fleet safety before merge-train
[!X] %1=fetch gh://perf/bench/pull/333 ; %2=browse gh://perf/bench/issues?label=perf-regression → %3=join(%1,%2) ∵ link PR to perf reports
[!B] %4=review %3 models=[opus,gemini] ; gate(bench:fail) ∵ throughput drop 12%
[!C] commit frozen ∵ gate(bench:fail) ; merge held not fleet-safe

# Skip CJK gate when issue corpus is English-only
[!X] %1=browse gh://us/app/issues?lang=en ; %2=search %1 "auth bypass" → %3=dedup %2 ∵ security triage
[!V] %4=review %3 join (fetch gh://us/app/pull/120) model=opus ; gate(no_cjk:skip) gate(english:pass) gate(parse:pass)
[!C] gate(ci:pass)?merge:hold

# Full four-layer: plan, triage, fleet review, risk, conditional merge
[!P] schedule browse→intersect→review→risk→merge ∵ guard fleet on cross-cutting issues
[!X] %1=browse gh://acme/api/issues?label=flaky ; %2=browse gh://acme/api/issues?label=needs-merge → %3=intersect(%1,%2) ; %4=fetch gh://acme/api/pull/650
[!V] %5=review combine(%3,%4) models=[opus,sonnet,gemini,codex] ∵ adversarial verify findings ; gate(english:pass) gate(no_cjk:pass)
[!C] gate(ci:pass)?merge %4:hold ∵ commit frozen if any gate(*:fail)
```

## dedup — Duplicate/cross-issue dedup: embed all open issues, cluster, link duplicates, consolidate.

```text
# Embed all open issues then dedup into clusters
[!P] browse gh issue list repo:rust-lang/rust state:open → %issues
[!X] map %issues model=qwen → %vec ∵ embed-each-issue-body-cheaply
[!X] %clusters = dedup %vec ; argmax %clusters → %canonical

# Cross-repo overlap detection via intersect
[!P] browse "github.com/tokio-rs/tokio/issues?q=is:open" → %a
[!X] search "github.com/tokio-rs/axum/issues?q=is:open" → %b
[!X] %dups = intersect(map %a model=haiku, map %b model=haiku) ∵ shared-embedding-space
[!V] gate(parse:pass) ?: gate(parse:fail)

# Frozen commit when parse gate fails on dedup output
[!P] fetch gh issue list repo:vercel/next.js label:bug state:open → %raw
[!X] %canon = dedup(map %raw model=sonnet) → %links
[!V] gate(parse:fail)
[!C] merge %links ∵ commit-frozen-on-parse-fail

# Consolidate duplicate set via union then link
[!X] browse "github.com/pandas-dev/pandas/issues?q=is:open+label:Bug" → %open
[!X] %clusters = dedup(map %open model=opus) ; %merged = %clusters ∪ %canonical
[!A] write dedup-report.md ← %merged
[!C] open gh issue comment --link %merged ∵ gate(artifact:pass)

# Remove already-linked dupes with set difference
[!P] search gh issue list repo:numpy/numpy state:open label:duplicate → %known
[!X] browse gh issue list repo:numpy/numpy state:open → %all
[!X] %new = %all ∖ %known ; %candidates = dedup(map %new model=qwen)
[!V] gate(english:pass)

# Fan-out embedding across models then argmax canonical issue
[!X] fetch "github.com/kubernetes/kubernetes/issues?q=is:open+sig/network" → %net
[!X] %scored = map %net models=[gemini,sonnet,qwen] ∵ ensemble-embed-vote
[!X] %canonical = argmax(dedup %scored) → %primary
[!C] commit edit %primary ∵ gate(commit:pass)

# Conditional reroute to stronger model on low-confidence cluster
[!P] browse gh issue list repo:facebook/react state:open → %issues
[!X] %c = dedup(map %issues model=haiku) → %conf
[!T] %route = %conf ?: model=opus ∵ escalate-ambiguous-clusters
[!X] map %route model=opus → %refined

# No-CJK gate on consolidated triage summary
[!X] search "github.com/golang/go/issues?q=is:open+label:NeedsInvestigation" → %g
[!X] %dups = dedup(map %g model=sonnet) ; %summary = combine %dups
[!A] write triage-dedup.md ← %summary
[!V] gate(no_cjk:pass) ∵ ascii-only-issue-titles

# Bench dedup precision before linking duplicates
[!P] fetch gh issue list repo:django/django state:open label:bug → %d
[!X] %clusters = dedup(map %d models=[qwen,haiku])
[!B] gate(bench:warn) ∵ recall-below-threshold-flag-only
[!V] gate(ci:pass) ?: gate(ci:fail)

# Risk-gated auto-close of confirmed duplicates
[!P] browse gh issue list repo:apache/airflow state:open → %open
[!X] %canon = argmax(dedup(map %open model=opus)) → %primary
[!R] gate(commit:warn) ∵ auto-close-needs-maintainer-review ; filter %canon → %safe
[!C] merge open gh issue close %safe ∵ gate(artifact:pass)
```

## browser — Browser-driven repro (Playwright on live issue pages / hosted repro apps): navigate, snapshot, extract, screenshot-diff.

```text
# Triage newest open bugs across two upstream repos
[!P] schedule: unreviewed-first
[!X model=haiku] %1 = search "repo:facebook/react repo:vercel/next.js is:issue is:open label:bug sort:created-desc"
[!X model=sonnet] %2 = browse %1 → %3 = fetch %2 → %4 = filter %3 ∵ has-repro-link
[!V model=opus] gate(parse:pass) ? %4 : gate(parse:fail)

# Reproduce a live hosted repro app and screenshot-diff against baseline
[!X model=sonnet] %1 = browse "https://github.com/microsoft/vscode/issues/204315" → %2 = read %1 → %3 = open %2.repro_url
[!X model=sonnet] %4 = read %3 ; %5 = read "./baseline/204315.png"
[!B model=opus] %6 = diff %4 %5 → gate(bench:pass)
[!C] commit %6 ∵ visual-regression-confirmed

# Find duplicate issue reports and pick the canonical one
[!X model=haiku] %1 = search "repo:nodejs/node is:issue is:open in:title fetch hangs"
[!T] %2 = dedup %1 ∵ same-stacktrace
[!X model=opus] %3 = argmax(%2, reactions) → %4 = browse %3
[!C] commit %4 gate(commit:pass)

# Untriaged set = all open minus already-labeled
[!X model=haiku] %1 = search "repo:denoland/deno is:issue is:open"
[!X model=haiku] %2 = search "repo:denoland/deno is:issue is:open label:triaged"
[!T] %3 = %1 ∖ %2
[!A] write %3 → gate(artifact:pass)

# Locale gate on a non-English bug report before repro
[!X model=sonnet] %1 = browse "https://github.com/grafana/grafana/issues/88210" → %2 = read %1
[!X model=sonnet] %3 = open %2.repro_url → %4 = read %3
[!R] gate(no_cjk:fail) ? launch_agent translate : gate(english:pass)
[!C] commit %4 ∵ repro-rendered

# Cross-repo issue union, extract reproduction steps
[!X model=haiku] %1 = search "repo:withastro/astro is:issue is:open label:repro-needed"
[!X model=haiku] %2 = search "repo:vitejs/vite is:issue is:open label:repro-needed"
[!T] %3 = %1 ∪ %2 → %4 = map(%3, extract_steps)
[!V model=sonnet] gate(parse:pass) ∵ steps-structured

# Reactive screenshot-diff: reopen or close based on regression
[!X model=sonnet] %1 = open "https://repro.example.dev/issue-9921" → %2 = read %1
[!B model=opus] %3 = diff %2 "./baseline/9921.png"
[!C] gate(bench:fail) ? commit %3 ∵ reopen : commit %3 ∵ close-as-fixed

# Ensemble review of a flaky screenshot-diff
[!X model=sonnet] %1 = browse "https://github.com/playwright-community/issues/512" → %2 = open %1.repro_url
[!B model=sonnet] %3 = read %2 → %4 = diff %3 "./baseline/512.png"
[!V models=[opus,gemini,codex]] %5 = combine(%4, votes) → gate(bench:warn)
[!C] commit %5 ∵ majority-flaky

# Run hosted repro under CI and gate on result
[!X model=sonnet] %1 = browse "https://github.com/prisma/prisma/issues/24310" → %2 = read %1
[!X model=sonnet] %3 = open %2.repro_url → %4 = test %3
[!R] gate(ci:fail) ? launch_agent bisect : gate(ci:pass)
[!C] commit %4 gate(commit:pass)

# Top open issue by reactions, snapshot persists but commit frozen on parse fail
[!P] schedule: reactions-desc
[!X model=haiku] %1 = search "repo:tailwindlabs/tailwindcss is:issue is:open sort:reactions-desc"
[!X model=sonnet] %2 = argmax(%1, reactions) → %3 = browse %2 → %4 = read %3
[!V] gate(parse:fail) ∵ malformed-snapshot
[!C] commit %4
```

## escalate — Cross-repo + cost-routed escalation: cheap model first, escalate to opus on low confidence, fan across repos.

```text
# cheap triage of one repo, escalate single low-confidence issue to opus
[!X] %1=search(model=haiku,"gh issue list -R rust-lang/rust --label C-bug --json number,title,url") → %2=filter(%1,"needs-triage")
[!X] %3=browse(model=haiku,"https://github.com/rust-lang/rust/issues/118923") → %4=map(%3,score) → %5=(%4<0.6 ? browse(model=opus,"https://github.com/rust-lang/rust/issues/118923") : %3)
[!V] read(%5) ; gate(english:pass)
[!C] commit(%5) ∵ triaged

# fan across three repos with haiku, union the bug candidates
[!P] {torvalds/linux} ∪ {rust-lang/rust} ∪ {golang/go}
[!X] %1=search(model=haiku,"gh issue list -R torvalds/linux --label bug --json number,url") ; %2=search(model=haiku,"gh issue list -R rust-lang/rust --label bug --json number,url") ; %3=search(model=haiku,"gh issue list -R golang/go --label bug --json number,url")
[!X] %4=(%1 ∪ %2 ∪ %3) → %5=filter(%4,"unassigned")
[!A] write(%5,"triage-queue.json") ; gate(artifact:pass)

# escalate the most ambiguous issue, picked by argmax over confidence
[!X] %1=search(models=[haiku,qwen],"gh issue list -R kubernetes/kubernetes --label kind/bug --json number,title,url")
[!T] %2=map(%1,classify) → %3=argmax(%2,ambiguity) → %4=map(%3,score)
[!X] %5=(%4<0.55 ? fetch(model=opus,"https://github.com/kubernetes/kubernetes/issues/121456") : fetch(model=haiku,"https://github.com/kubernetes/kubernetes/issues/121456"))
[!V] review(%5) ; gate(english:pass) ; gate(parse:pass)

# cross-repo duplicate detection via intersect, opus adjudicates
[!X] %1=search(model=haiku,"gh issue list -R vercel/next.js --label bug --json title,url") → %2=search(model=haiku,"gh issue list -R facebook/react --label bug --json title,url")
[!X] %3=intersect(%1,%2) → %4=map(%3,score)
[!X] %5=(%4<0.7 ? browse(model=opus,%3) : %3) → %6=dedup(%5)
[!A] write(%6,"cross-repo-dupes.md") ; gate(no_cjk:pass)

# per-repo agent fan-out, each agent escalates locally
[!P] {denoland/deno} ∪ {oven-sh/bun} ∪ {nodejs/node}
[!X] %1=launch_agent(model=haiku,"triage denoland/deno open issues") ; %2=launch_agent(model=haiku,"triage oven-sh/bun open issues") ; %3=launch_agent(model=haiku,"triage nodejs/node open issues")
[!X] %4=combine(%1,%2,%3) → %5=map(%4,score) → %6=(%5<0.6 ? launch_agent(model=opus,"re-triage low-confidence set") : %4)
[!C] commit(%6) ∵ fan-out complete

# frozen commit: parse gate fails on malformed issue dump
[!X] %1=search(model=qwen,"gh issue list -R apache/kafka --json number,body,url") → %2=map(%1,extract) → %3=map(%2,score)
[!X] %4=(%3<0.5 ? fetch(model=opus,"https://github.com/apache/kafka/issues/15022") : %2)
[!V] review(%4) ; gate(parse:fail)
[!C] commit(%4) ∵ frozen ; gate(commit:fail)

# exclude already-labeled issues, escalate remainder
[!X] %1=search(model=haiku,"gh issue list -R pandas-dev/pandas --json number,labels,url") → %2=search(model=haiku,"gh issue list -R pandas-dev/pandas --label triaged --json number,url")
[!X] %3=(%1 ∖ %2) → %4=filter(%3,"no-repro") → %5=map(%4,score)
[!X] %6=(%5<0.65 ? browse(model=opus,%4) : %4)
[!A] write(%6,"needs-repro.json") ; gate(artifact:pass) ; gate(english:pass)

# risk-gated cross-repo escalation on security-labeled issues
[!X] %1=search(model=haiku,"gh issue list -R openssl/openssl --label security --json number,url") ∪ %2=search(model=haiku,"gh issue list -R libressl/portable --label security --json number,url") → %3=map((%1 ∪ %2),score)
[!R] %4=(%3<0.8 ? fetch(model=opus,"https://github.com/openssl/openssl/issues/23456") : fetch(model=haiku,"https://github.com/openssl/openssl/issues/23456")) ; gate(english:pass)
[!V] review(%4) ∵ security-sensitive
[!C] commit(%4) ∵ risk-cleared

# tiered model list, cross-repo dedup, escalate then bench the routing
[!X] %1=search(models=[qwen,haiku,sonnet],"gh issue list -R tensorflow/tensorflow --label type:bug --json number,url") ∪ %2=search(models=[qwen,haiku,sonnet],"gh issue list -R pytorch/pytorch --label bug --json number,url")
[!X] %3=dedup(%1 ∪ %2) → %4=map(%3,score) → %5=(%4<0.6 ? browse(model=opus,argmax(%3,severity)) : %3)
[!B] %6=test(%5) ; gate(bench:pass)
[!C] commit(%6) ∵ routed

# join issue metadata with comments, escalate threads needing deep read
[!X] %1=search(model=haiku,"gh issue list -R microsoft/vscode --json number,url") → %2=fetch(model=haiku,"gh issue view 198765 -R microsoft/vscode --comments")
[!X] %3=join(%1,%2) → %4=map(%3,score) → %5=(%4<0.6 ? fetch(model=opus,"https://github.com/microsoft/vscode/issues/198765") : %3)
[!V] review(%5) ; gate(english:pass) ; gate(no_cjk:pass)
[!A] write(%5,"vscode-triage.md") ; gate(artifact:pass)
```

## novel — Novel patterns applied to issues: tournament bracket of fixes, loop-until-dry discovery, completeness-critic, judge-panel synthesis.

```text
# judge-panel synthesis: rank a flaky-test issue's candidate root causes
[!X] %1=fetch gh:facebook/react#28901 ; %2=browse https://github.com/facebook/react/issues/28901#comments
[!V] models=[opus,gemini,codex] %3=map(verdict, %1→%2) ; %4=combine(%3) ∵ panel-consensus
[!A] model=opus %5=argmax(confidence, %4) → write triage-note(%5) ; gate(english:pass)

# tournament bracket of fixes: pit four patch candidates head-to-head
[!P] schedule rounds=[semi,final] over %cands ∵ single-elim
[!X] models=[sonnet,codex,qwen,gemini] %1=launch_agent(draft_fix, gh:vercel/next.js#62000)×4 → %2=combine(%1)
[!B] model=opus %3=map(bench, %2) ; %4=argmax(green_ci ∧ speed, %3) ; gate(bench:pass)
[!C] model=opus %5=commit(%4) ?gate(ci:pass): freeze ∵ frozen-if-fail

# loop-until-dry discovery: re-query labels until no new triable issues surface
[!P] schedule re-query batch ∵ until gate(no_cjk:skip)∧dry
[!X] model=haiku %1=search gh:owner/repo label:bug is:open created:>2026-06-01 → %2=filter(untriaged, %1)
[!T] model=sonnet %3=(%2≠∅) ?: feed(%2→search) : halt(dry) ∵ fixpoint-reached
[!V] model=opus %4=dedup(%2) ; gate(parse:pass)

# completeness-critic: gate a fix that omits a reported edge case
[!X] %1=fetch gh:tinygrad/tinygrad#5012 → %2=edit patch(%1)
[!V] model=opus %3=critic(coverage, %2 ∖ repro_steps) ; gate(artifact:fail) ∵ edge-case-missing
[!C] %4=commit(%2) ?gate(artifact:pass): freeze → reopen %1

# risk-gated triage: label a security issue only after mitigation passes
[!X] %1=fetch https://github.com/openssl/openssl/issues/24500 → %2=open thread(%1)
[!R] model=opus %3=assess(disclosure_risk, %2) ; gate(commit:warn) → mitigate(embargo) ∵ CVE-pending
[!A] %4=write triage-label(security, %2) ?gate(commit:pass): hold

# intersect duplicate-detection across two repos' open bug streams
[!X] model=haiku %1=search gh:rust-lang/rust label:I-crash is:open ; %2=search gh:rust-lang/cargo label:crash is:open
[!V] model=sonnet %3=intersect(stacktrace, %1, %2) → %4=dedup(%3) ; gate(parse:pass) ∵ cross-repo-dupes

# map-filter prioritization: route triaged issues to fixer tiers by severity
[!X] %1=browse gh:pytest-dev/pytest is:open label:bug → %2=fetch %1
[!T] model=sonnet %3=map(severity, %2) ; %4=filter(sev≥high, %3) ; %5=argmax(reach, %4) ∵ blast-radius
[!P] schedule %5→launch_agent(fix) model=codex ; gate(english:pass)

# union-merge issue sources then synthesize one triage digest
[!X] %1=search gh:numpy/numpy is:open label:regression ; %2=fetch https://github.com/numpy/numpy/discussions/26000
[!V] models=[opus,gemini] %3=join(%1, %2) ; %4=combine(map(summary, %1∪%2)) ∵ digest
[!A] model=opus %5=write digest(%4) → diff(%5, prior_digest) ; gate(no_cjk:pass)

# tournament + completeness-critic combined: bracket fixes, drop the incomplete ones
[!X] models=[codex,qwen] %1=launch_agent(fix, gh:django/django#17800)×2 → %2=map(test, %1)
[!V] model=opus %3=critic(completeness, %2) ; %4=%2 ∖ filter(incomplete, %3) ; gate(artifact:warn)
[!B] %5=argmax(pass_rate, %4) ; gate(bench:pass) ∵ survivor-fastest-green
[!C] %6=merge(%5) ?gate(ci:pass): freeze

# judge-panel on triage labels with a frozen commit when CI rejects
[!X] %1=fetch gh:kubernetes/kubernetes#124500 → %2=open thread(%1)
[!V] models=[opus,sonnet,gemini] %3=combine(map(label_vote, %2)) ; %4=argmax(quorum, %3) ∵ majority
[!C] model=opus %5=commit(label %4) ?gate(ci:fail): freeze → %6=build(verify) ; gate(commit:skip)
```
