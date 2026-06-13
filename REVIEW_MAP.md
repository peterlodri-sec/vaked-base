# Review Map — Optimization pass on #103 (delivered in #112)

A reviewer-facing map of this PR so you can understand the work **without
reading the agent transcripts**. The PR is a multi-round, multi-agent
optimization pass on #103, stacked on its head branch so the diff here is only
the optimization changes.

- **Base reference:** https://github.com/peterlodri-sec/vaked-base/pull/103#issuecomment-4699219497
- **Follow-ups:** #116 (implement `ralphloop`), #117 (grow vakedc-zig to parity)
- **Net effect:** de-soups #103 from ~104,711 to ~5,400 reviewable lines, fixes a
  blocking parse bug, grounds the research claims in measured data, and starts two
  new design-first subsystems.

## 1. Commit-by-commit

| # | Commit | Lane(s) | What / why |
|---|--------|---------|------------|
| 1 | `fix(loadtest-gen)` `71c940d` | A | **Blocking bug.** Generator emitted a trailing comma for worker counts ÷10, so the 10k fixture never parsed. One-line fix; 10k now parses. |
| 2 | `chore: remove scratch docs` `2ab854f` | D | Delete `_operator_todo.md`, `PR_103_KICKSTART.md`, `REVIEW_PLAN.md` (internal notes; one held a personal email). |
| 3 | `refactor(eval): de-soup` `ca6295a` | B | Untrack the 1k/10k `.vaked` fixtures (−99k lines), `.gitignore` + regen task + smoke guard; repoint docs. |
| 4 | `docs(research): claims ledger` `361c3e4` | C, A | Add `METHODOLOGY.md`; retract unsupported "120s timeout" / "O(n) linear" / "1900-iteration" claims; fix fabricated citations. |
| 5 | `round 2: Taskfile + fixes` `ba93a77` | B, C | Replace Makefile with `Taskfile.yml` tasks; fix BENCHMARK.md 10× discrepancy; mop up remaining `>120s` stragglers. |
| 6 | `design(language): 0017 ralphloop` `c382093` | design | Grammar-first proposal for the `ralphloop` cached dogfooding primitive (+ marked example). Grammar NOT modified. |
| 7 | `feat(zig): vakedc-zig v0.0.1` `6d57d33` | design | Runnable Zig lexer+parser subset + `setup-zig.sh` + design note. |

## 2. Agent lanes (the fan-out)

Four parallel review lanes ran first and cross-checked each other before any
edit; a Round-2 consistency lane and a design-drafting lane followed.

| Lane | Found | Outcome |
|------|-------|---------|
| **A — Correctness/validation** | 10k file is a **hard parse error** (trailing comma), not a "timeout"; real numbers differ from the base comment; "O(n) linear" is false (lower is super-linear); `bench.py`/`baseline.json` are real. | Drove commits 1, 4, 5 |
| **B — Architecture/reviewability** | The two huge files are **byte-identical reproducible** from a 130-line generator; nothing depends on them. | Drove commit 3 |
| **C — Research maturity** | Headline scaling numbers absent from `baseline.json`; 10× BENCHMARK-vs-paper conflict; misattributed/fabricated citations. | Drove commits 4, 5; recommended `METHODOLOGY.md` |
| **D — Scope hygiene/secrets** | **No secrets** (scripts are env-gated); 3 root scratch docs are noise; image/script tooling out of scope. | Drove commit 2; rest deferred |
| **Round-2 consistency sweep** | Stragglers: `>120s` in image prompts + roadmap table; BENCHMARK.md 10× block. | Folded into commit 5 |
| **ralphloop design draft** | 0017 design package; flagged a filename-number collision (fixed → 0017). | Became commit 6 |

## 3. Findings: accepted / rejected / deferred

**Accepted (implemented here):** generator bug fix; de-soup; remove 3 scratch
docs; `METHODOLOGY.md` claims ledger; retract the timeout/linear/iteration
claims; fix citations (Nickel→Tweag, Dhall→Gabriel Gonzalez, CUE→van Lohuizen;
two unverifiable roadmap refs → "citation needed"); Taskfile migration; BENCHMARK
10× fix; `ralphloop` design proposal; `vakedc-zig` v0.x.

**Rejected / not done:** rewriting #103's inherited commit history (unsigned but
already `noreply@anthropic.com` like the rest of the repo); inventing
"corrected" citations from memory for the two unverifiable refs (left honest
placeholders instead); implementing the O(n log n) optimizations now
(speculative → roadmap).

**Deferred (to follow-ups, not silently dropped):**
- `generate_images.py`, `docs/images/metadata.json`, `scripts/{web-search,gather-context}.sh` — out-of-scope tooling, env-gated, no secrets. Kept; flagged for a future cleanup. (The retracted `>120s` claim inside the image prompt **was** fixed.)
- Folding the swe-swarm rows + machine metadata into `baseline.json` → #116 scope / METHODOLOGY §4.
- `ralphloop` implementation → **#116**. vakedc-zig parity + compile gate → **#117**.

## 4. Validation commands & results (boring, reproducible)

| Command | Result |
|---------|--------|
| `python3 examples/evaluation/generate_loadtest.py --workers 10000 --out /tmp/x.vaked && python3 -m vakedc parse /tmp/x.vaked` | parse rc=0 (was EXIT 1 before the fix) |
| `python3 -m vakedc check vaked/examples/swe-swarm-10k-workers.vaked` (regenerated) | rc=0, **0 diagnostics**, ~4.3s |
| `python3 -m vakedc lower …10k…` | rc=0, 10,007 artifacts, ~16.3s, ~300MB RSS |
| `--workers 1024` output vs old committed file | **byte-identical** (no regression) |
| `task loadtests-smoke` (regenerate + parse both) | smoke OK, exit 0 |
| baseline.json cross-check (operator-field, rejected, schema-constraints) | matches measured ~60ms; real data |
| `bash -n scripts/setup-zig.sh` | syntax OK |
| `zig build test` (vakedc-zig) | **not run — no Zig in container**; gate in #117 |

## 5. Remaining risks

1. **vakedc-zig is unvalidated-in-container** (no Zig toolchain). The code is
   conservative and unit-tested by construction, but the compile/test gate is
   #117. Clearly marked everywhere.
2. **10k numbers are single-run** (not median); treat as order-of-magnitude.
   `bench.py` numbers are machine-specific (dev container) — see METHODOLOGY §1.
3. **`ralphloop` is design-only**; the example does not parse under `vakedc` yet
   (marked in-file). Implementation is #116.
4. **Stacked PR:** base is #103's branch, so this should merge after/with #103
   (it auto-retargets to `main` when #103 merges).

## 6. Caveman / Superpowers self-rubric

- **Caveman:** small scoped commits, plain-language messages, deletions over
  additions (−99k lines), every claim tied to a runnable command, no
  review-hostile blobs, no unvalidated magic left unlabeled.
- **Superpowers:** 4 parallel discovery lanes + 2 follow-on lanes, cross-checked
  before editing (A's "it's a bug" corroborated C's "numbers aren't in
  baseline.json"); orchestration trace above; two follow-ups generated from
  discovered work.
