# Kickoff prompt — "FIX ALL OPEN ISSUES" expressed across every shape (AI-lish V1 / ARP)

A worked example: one intent — *gather every open issue + PR, fan out one
`subagent-driven-development` run per item, verify, then compress the results* —
written in every notation this repo speaks, from natural language down to the
executable host runtime. It is both a teaching artifact for AI-lish V1 / ARP and a
real, paste-able kickoff prompt.

- Grammar: `docs/ailish/2026-06-14-ailish-v1-rfc.md` (registers, SSA, gates, compaction).
- Behavioral signals: `protocol/rfcs/0009-arp.md` (Stride / Tension / Valence / Branch).
- Prior art (the per-issue fan-out shape): `docs/superpowers/plans/2026-06-14-ail-0-sdd-fanout.md`.
- Skill executed per item: `subagent-driven-development` (superpowers plugin).

> **Provenance / forward-reference.** The three spec files above currently live on the
> unmerged ARP branches — PR #238 (`feat/arp-behavioral-primitives`, RFC 0009) and PR #211
> (`worktree-feat+ail-0-bridge`, AIL-0). They are referenced as plain paths (not links) on
> purpose: the links resolve once #211/#238 merge to main. Until then, read them with
> `git show origin/feat/arp-behavioral-primitives:<path>`.

> **Honesty stance (inherited from #211).** Register tags are a *token tax*, not a
> proven saving; the win is a lowerable, replayable graph. So the value here is the
> **lowering** (one intent → an executable plan a harness can run and verify), not the
> byte count. Gates carry the rigor; the prose registers stay free-text.

---

## The three-layer lowering (AI-lish architecture)

```
  Shape 1–2   prompt-space     natural language / one-line command   (human authors)
      │  lower / desugar
      ▼
  Shape 3–6   AI-lish V0→V1    semantic log → strict SSA graph        (parser + guardrail)
      │  compile / execute
      ▼
  Shape 7–8   host runtime     Vaked workflow / Workflow() JS         (gh, sdd agents, dev-cx53)
```

---

## Shape 1 — Natural language (the intent)

> Fetch every open issue and every open PR. Treat each as one unit of work. For each,
> launch a `subagent-driven-development` run in an isolated worktree. Verify each
> (tests/CI) on a remote builder — never on this machine. Keep the green ones, drop the
> red ones, open a ready-for-review PR per green item, and return one compressed digest
> of what closed, what shipped, and what was skipped. Do not self-merge.

## Shape 2 — One-line slash command (prompt-space)

```
/subagent-driven-development ∀ x ∈ gh:{issues,prs}@open : worktree → fix → test@dev-cx53 → gate(ci:pass) ? open(pr) : drop  ⇒ digest   # no self-merge
```

## Shape 3 — AI-lish V0 (semantic log sketch — ambiguous, pre-SSA)

```text
[R:tool]  gh issues+prs @open → corpus(≈39)
[R:plan]  corpus → ∀ item ⊕ sdd-agent(worktree) ⇒ fix → test → ci
[R:risk]  build on dev machine ✗ (NEVER-BUILD) ⇒ remote dev-cx53/GHA only
[R:bench] green ⇒ open PR; red ⇒ drop
[R:artifact] results ⇒ compress(digest)   # no self-merge
```

*(Why this is not enough: `→` means three things, no `%N` so "the green ones" cannot
reference a prior result. Lower it.)*

## Shape 4 — AI-lish V1 (strict SSA graph — the canonical contract)

```text
[R:tool]     %0 = fetch(src=`gh`, kind="issues", state="open")
             %1 = fetch(src=`gh`, kind="prs", state="open")
             %2 = combine(%0, %1) ; n=39
[R:plan]     depend(%2) → target(action="∀ item ∈ %2 : one sdd run, isolated worktree")
[R:risk]     %3 = check_permission(verb="build", host="dev-cx53") ; reason="NEVER-BUILD on dev machine"
             gate(commit:fail) ∵ %3
[R:tool]     %4 = launch_agent(scope=%2, skill="subagent-driven-development", isolation="worktree")
[R:bench]    %5 = test(target=%4, host="dev-cx53") ; per_item=true
             gate(ci:pass) ∵ %5
[R:review]   %6 = intersect(%4, %5) ; keep="green", drop="red"
[R:artifact] %7 = combine(%6) ; compress="digest", fields="closed[],pr_urls[],skipped[]"
             gate(artifact:pass) ∵ %7
[R:commit]   %8 = open(prs=%6) ∵ %5        # frozen while gate(commit:fail) live; human merges
```

Every `%N` is independently validatable; a failed item falls back to the exact register
that produced its bad input. `R:commit` is frozen by the live `gate(commit:fail)` — the
guardrail requires a human to paste the merge.

## Shape 5 — AI-lish V1 compact (the "bytecode" — what a model emits under token pressure)

```text
[!X] %0=fetch(`gh`,issues,open);%1=fetch(`gh`,prs,open);%2=&(%0,%1);n=39
[!P] depend(%2)→target("∀ x∈%2: sdd, worktree")
[!R] %3=check_permission(build,dev-cx53);gate(commit:fail)∵%3
[!X] %4=launch_agent(scope=%2,skill=sdd,iso=worktree)
[!B] %5=test(%4,dev-cx53);per_item;gate(ci:pass)∵%5
[!V] %6=^(%4,%5);keep=green
[!A] %7=&(%6);compress=digest;gate(artifact:pass)∵%7
[!C] %8=open(%6)∵%5
```

`ailishfmt` is idempotent between Shape 4 and Shape 5.

## Shape 6 — ARP-augmented (V1 + behavioral signals, RFC 0009)

ARP rides *alongside* V1 — advisory progress/affect/fork signals, no authority.

```text
[STRIDE: gather → fan-out → verify → compress → open]
[T:90]  [!X] %2 = &(fetch(`gh`,issues@open), fetch(`gh`,prs@open)) ; n=39        [+]
[T:70]  [!R] gate(commit:fail) ∵ check_permission(build, dev-cx53)               [!]
[T:55]  [!X] %4 = launch_agent(scope=%2, skill=sdd, iso=worktree)
        [BRANCH: green → open(pr) | red → drop ; condition: gate(ci:pass)]
[T:30]  [!B] %5 = test(%4, dev-cx53) ; gate(ci:pass) ∵ %5                         [+]
[T:10]  [!A] %7 = &(intersect(%4,%5)) ; compress=digest ; gate(artifact:pass)     [+]
```

Tension falls as the task converges; a harness escalates if `[T:N]` stays high or it sees
a run of `[-]`.

## Shape 7 — Vaked workflow (the typed agent-step DAG, issue #27)

The same graph as a `workflow` kind — typed steps, explicit DAG, the native repo form:

```vaked
workflow fix-all-open {
  step gather    { run = "gh:{issues,prs}@open";          out = corpus }
  step fanout    { for-each = corpus; skill = "sdd";       isolation = worktree; out = runs }
  step verify    { needs = fanout; run = "test"; host = "dev-cx53"; gate = "ci:pass" }
  step compress  { needs = verify; reduce = "digest";      gate = "artifact:pass" }
  step open-prs  { needs = verify; run = "gh pr create";   freeze-on = "commit:fail" }  # no self-merge
}
```

## Shape 8 — Host runtime: executable `Workflow()` script (FULL-LOWER)

The lowest layer — the V1 graph compiled to the orchestration runtime. `pipeline()` runs
each item through fix → verify independently (no barrier); builds dispatch to `dev-cx53`
inside each agent (never local). This is what actually runs.

```js
export const meta = {
  name: 'fix-all-open-issues',
  description: 'Fan out one subagent-driven-development run per open issue/PR, verify on dev-cx53, compress',
  phases: [{ title: 'Gather' }, { title: 'Fix' }, { title: 'Verify' }, { title: 'Compress' }],
}

phase('Gather')
// %0,%1,%2 — fetch corpus (the orchestrator scout passes it in via args)
const corpus = args?.items ?? []          // [{kind:'issue'|'pr', number, title}]
log(`corpus n=${corpus.length}`)

// %3 — risk gate is structural: every coder agent is told to build ONLY on dev-cx53.
const REMOTE = 'dev-cx53'

const results = await pipeline(
  corpus,
  // %4 — one sdd run per item, isolated worktree
  item => agent(
    `Run subagent-driven-development to fix ${item.kind} #${item.number}: "${item.title}". ` +
    `Build/test ONLY on ${REMOTE} (NEVER on the dev machine). No self-merge.`,
    { label: `sdd:${item.kind}#${item.number}`, phase: 'Fix', isolation: 'worktree',
      schema: { type:'object', required:['number','green','pr_url','skipped'],
        properties:{ number:{type:'number'}, green:{type:'boolean'},
                     pr_url:{type:['string','null']}, skipped:{type:'boolean'} } } }
  ),
  // %5,%6 — verify gate(ci:pass); keep green, drop red
  (r, item) => r && r.green
    ? agent(`Confirm CI green for #${item.number} on ${REMOTE}; report pass/fail only.`,
        { label:`verify:#${item.number}`, phase:'Verify',
          schema:{ type:'object', required:['ci_pass'], properties:{ ci_pass:{type:'boolean'} } } })
        .then(v => ({ ...r, ci_pass: !!v?.ci_pass }))
    : { ...(r||{number:item.number}), ci_pass:false }
)

// %7 — compress to one digest; gate(artifact:pass)
phase('Compress')
const ok = results.filter(Boolean).filter(r => r.green && r.ci_pass)
const digest = {
  closed:  ok.map(r => r.number),
  pr_urls: ok.map(r => r.pr_url).filter(Boolean),
  skipped: results.filter(Boolean).filter(r => r.skipped || !r.ci_pass).map(r => r.number),
}
log(`digest: closed=${digest.closed.length} prs=${digest.pr_urls.length} skipped=${digest.skipped.length}`)
return digest   // %8 open(prs) happened inside each sdd run; human merges. gate(commit:fail) ⇒ no self-merge.
```

---

## Which shape is ideal? (the answer to "find the ideal shape-form-workflow-type")

| Audience | Ideal shape | Why |
|----------|-------------|-----|
| Human kickoff | **Shape 2** (one-liner) | densest paste-able intent; a human reads it in one glance |
| Model ↔ harness contract | **Shape 4** (V1 SSA) | the only *validatable, replayable* form; `%N` addressability + gates |
| Model under token pressure | Shape 5 (compact) | `ailishfmt`-equivalent to Shape 4; fewer tokens |
| Native repo artifact | Shape 7 (`workflow`) | typed DAG, fits issue #27 once `workflow` lands |
| **What actually runs** | **Shape 8** (`Workflow()` JS) | the FULL-LOWER — deterministic fan-out, per-item verify, remote builds |

**Ideal = Shape 4 as the contract, lowered to Shape 8 as the executor, with Shape 2 as
the human entry point.** Shape 4 is the pivot: it is the highest form that is still
machine-checkable (parser + guardrail), and it lowers mechanically to Shape 8. The single
load-bearing gate is `gate(commit:fail)` from `R:risk` (NEVER-BUILD + no self-merge),
which freezes `R:commit` exactly as the protocol's merge-to-main block intends.

## Caveats (no silent truncation)

- `n=39` is the corpus at authoring time (35 open issues + 4 open PRs). Re-fetch before
  any run; the number is illustrative, not pinned.
- Open PRs as fan-out items is risky — they already carry branches, so a per-PR `sdd` run
  can collide with in-flight work. Prefer issues-only unless a PR is explicitly stale.
- A full 39-item run is a large, real spend and triggers remote builds — it is a
  deliberate, gated action, not a default.
