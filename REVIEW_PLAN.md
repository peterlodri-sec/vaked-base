# PR #103 Review Process (Two Rounds)

**Goal:** Catch issues, validate claims, polish for arxiv submission  
**Timeline:** Today (Round 1) → Tomorrow (Round 2) → Ready to merge

---

## Round 1: Critical Path Review (Today)

**Focus:** Core claims, soundness, evaluation rigor  
**Owner:** Primary reviewer  
**Time:** 2-3 hours  
**Sign-off:** "Critical path clear / Issues found"

### Checklist: Paper (docs/papers/vaked-language-v0.1.md)

- [ ] **Abstract** — Does it clearly state the problem, solution, and contribution?
- [ ] **Introduction** — Motivation is compelling; problem is well-framed
- [ ] **Related Work** — Fair comparison; no misrepresentation of prior systems
- [ ] **Type System** — POLA rules clearly stated; partial order property explained
- [ ] **Evaluation** — Benchmarks support claims; case studies are realistic
- [ ] **Threat Model** — Attack scenarios covered; runtime/compile-time boundary is clear
- [ ] **Conclusion** — Ties back to future work; optimization roadmap is realistic
- [ ] **References** — All citations are accurate; 25+ sources (check format)

**Issues to look for:**
- Overclaiming (e.g., "prevents all privilege escalation" — should be "static verification prevents")
- Unsupported claims (e.g., benchmarks don't match performance claims)
- Typos, formatting, consistency

### Checklist: Threat Model (docs/language/THREAT_MODEL.md)

- [ ] **POLA Statement** — Formally stated (even if informally proved)
- [ ] **Soundness Argument** — §4.5 logic is sound (partial order → POLA holds)
- [ ] **Attack Scenarios** — Cover privilege escalation, amplification, undeclared use
- [ ] **No Overclaiming** — Clearly states what Vaked does NOT guarantee
- [ ] **Runtime Boundary** — Clear which properties are static vs. runtime

**Issues to look for:**
- Circular reasoning in soundness proof
- Missing attack scenarios (e.g., compromise of root authority)
- Ambiguity about what "POLA guarantee" means (static only)

### Checklist: Evaluation (examples/evaluation/)

- [ ] **Benchmarks** — Times make sense (< 100ms for 1500-line files)
- [ ] **Determinism Oracle** — 19/19 examples deterministic is credible
- [ ] **Case Studies** — 4 examples clearly demonstrate language features + POLA
- [ ] **Scalability** — 8 → 1K → 10K worker progression is logical
- [ ] **Honest Limits** — 10K test timeout is honest assessment, not hidden

**Issues to look for:**
- Cherry-picked benchmarks (only fast cases shown)
- Determinism claim without evidence (check baseline.json exists)
- Case studies that don't actually use POLA features
- Hidden failures (e.g., 10K test error masked)

### Checklist: Optimization Roadmap (docs/compiler/OPTIMIZATION_ROADMAP.md)

- [ ] **Phases 1-4** — Concrete pseudocode provided
- [ ] **References** — 25+ citations are real papers (spot-check 5)
- [ ] **Performance Targets** — Realistic (2-5× Phase 1, 10-20× cumulative)
- [ ] **Rust Rewrite** — Justified (true parallelism, memory efficiency)

**Issues to look for:**
- Made-up paper titles
- Unrealistic speedup claims (e.g., "50× speedup" without justification)
- No justification for Rust rewrite (should explain GIL, memory, SIMD)

---

## Round 2: Polish & Validation (Tomorrow)

**Focus:** Clarity, consistency, missing pieces  
**Owner:** Secondary reviewer / different person  
**Time:** 1.5-2 hours  
**Sign-off:** "Ready for arxiv / Final tweaks needed"

### Checklist: Presentation & Clarity

- [ ] **Paper reads smoothly** — No awkward sentences; consistent terminology
- [ ] **Figure/Table quality** — Clear captions; referenced in text
- [ ] **Notation consistency** — Same symbols used for same concepts (e.g., `⊑` used consistently)
- [ ] **Examples are clear** — Operator-field example explains itself
- [ ] **Section transitions** — No abrupt jumps between topics

**Issues to look for:**
- Jargon not explained (e.g., "LPG" used without definition on first use)
- Inconsistent notation (e.g., `≤` sometimes, `⊑` sometimes for different concepts)
- Examples that assume too much background knowledge
- Missing connections between sections

### Checklist: Claims Validation

**For each major claim, verify:**

| Claim | Location | Evidence | Status |
|---|---|---|---|
| "Type system enforces POLA" | §3.2, §4.5 | Use check + attenuation check rules | ✓ |
| "Deterministic lowering" | §3.3, 0012 | baseline.json shows 100 runs identical | ✓ |
| "Scalable to 1K fibers" | §5.2 | bench shows 1K workers in 350ms | ✓ |
| "O(n) currently, O(n log n) possible" | Optimization roadmap | Phases 1-4 are grounded in CS literature | ✓ |
| "No POLA violations in examples" | CASE_STUDIES.md | All 4 case studies pass type-check | ✓ |

**If any claim is unverified:** Flag for removal or evidence gathering

### Checklist: Consistency

- [ ] **Claims in abstract match body** — All abstract claims appear in paper
- [ ] **Benchmarks in introduction match evaluation** — Same numbers reported
- [ ] **Threat model matches paper** — Security claims don't contradict each other
- [ ] **References are consistent** — Same papers cited same way everywhere
- [ ] **Examples work** — swe-swarm-loadtest.vaked actually parses + type-checks

**Issues to look for:**
- Abstract claims something paper doesn't prove
- Introduction says "X is fast" but evaluation says "X took Y seconds" (inconsistent)
- Threat model says "runtime enforces this" but paper claims it's compile-time

### Checklist: Completeness

- [ ] **All sections have content** — No placeholder "[TODO]" or "[FIXME]"
- [ ] **All references are cited** — No orphaned references
- [ ] **All examples are explained** — Each code snippet has context
- [ ] **All figures have captions** — No unlabeled tables/figures
- [ ] **All claims have citations** — "POLA is important" should reference security papers

**Issues to look for:**
- Incomplete sections (e.g., "Future Work" is just a heading with no content)
- Unused references (bibliography has papers not cited)
- Figures without captions
- Claims with no citations

### Checklist: Final Polish

- [ ] **Typos/spelling** — Run spellcheck
- [ ] **Formatting** — Consistent (indentation, capitalization, punctuation)
- [ ] **Line length** — No lines exceed 100 characters (readability)
- [ ] **Whitespace** — Consistent spacing (1 blank line between sections)
- [ ] **Code formatting** — Syntax highlighting is consistent, readable

**Issues to look for:**
- "Vaked" vs "VAKED" inconsistency
- "fiber" vs "Fiber" (should be consistent)
- Trailing spaces or mixed tabs/spaces

---

## Critical Issues to Catch (Both Rounds)

### 🚨 Showstoppers (Must Fix Before Submission)

1. **False claims** — "X is guaranteed" when it's not
2. **Wrong citations** — Citing papers that don't support the claim
3. **Broken examples** — swe-swarm-loadtest.vaked doesn't type-check
4. **Missing evidence** — "Deterministic" claimed but no baseline.json
5. **Logical contradictions** — "POLA is static" but then "runtime enforces it"

### ⚠️ Important Issues (Fix If Time)

1. **Clarity** — Jargon not explained; notation inconsistent
2. **Incomplete references** — Authors missing, wrong venue, wrong year
3. **Unsupported claims** — "Linear scaling" claimed but only 3 data points
4. **Missing details** — Pseudocode provided for phases 1-2 but not 3-4

### 💡 Nice-to-Have (Polish If Time)

1. **Typos** — Spelling, grammar
2. **Formatting** — Consistent spacing, line length
3. **Examples** — Could be clearer but work as-is
4. **References** — Could use 5-10 more recent citations

---

## Review Process (Hour by Hour)

### Round 1 (Today, ~2.5 hours)

**00:00-00:30:** Read paper cover-to-cover (intro through conclusion)
**00:30-01:00:** Check critical claims (POLA, determinism, scalability)
**01:00-01:30:** Verify evidence (benchmarks, case studies, threat model)
**01:30-02:00:** Check for overclaiming, logical errors
**02:00-02:30:** Document issues in GitHub comment

**Outcome:** "Critical path clear ✓" or "Issues found: [list]"

### Round 2 (Tomorrow, ~1.5 hours)

**00:00-00:30:** Skim paper again (looking for inconsistencies)
**00:30-01:00:** Check presentation (clarity, notation, examples)
**01:00-01:30:** Validate all claims against evidence
**01:30-02:00:** Polish (typos, formatting, completeness)

**Outcome:** "Ready for arxiv ✓" or "Final tweaks: [list]"

---

## Sign-Off Criteria

### Round 1 Sign-Off: "Critical Path Clear"

✅ **All of:**
- POLA guarantee is clearly stated (not overclaimed)
- Threat model is logically sound
- Evaluation supports all claims
- No false citations
- Examples work (type-check + lower)

### Round 2 Sign-Off: "Ready for ArXiv"

✅ **All of:**
- Paper reads smoothly (clear + consistent)
- No typos or formatting issues
- All claims validated against evidence
- All sections complete (no placeholders)
- References are accurate

---

## Template GitHub Comments

### Round 1 Findings

```markdown
## Round 1 Review (Critical Path)

**Status:** ✓ Clear / ⚠️ Issues Found

### Showstoppers
- [ ] None found (or list them)

### Important Issues
- [ ] Item 1: [description] (Location: paper §X)
- [ ] Item 2: [description]

### Nice-to-Have
- [ ] Item 1: [description]

**Recommendation:** Proceed to Round 2 / Hold for fixes
```

### Round 2 Findings

```markdown
## Round 2 Review (Polish & Validation)

**Status:** ✓ Ready / ⚠️ Tweaks Needed

### Critical Issues
- [ ] None found

### Important Issues
- [ ] Item 1: [fix required]
- [ ] Item 2: [suggested improvement]

### Polish Items
- [ ] Typos: [line numbers]
- [ ] Formatting: [sections]

**Recommendation:** Ready for merge / One more pass
```

---

## Next Actions (After Reviews)

1. **Gather feedback** — Both rounds comment on PR
2. **Triage issues** — Categorize: critical / important / nice-to-have
3. **Fix critical** — No submission without fixes
4. **Fix important** — If time allows (2-3 hours work)
5. **Decide on polish** — OK to defer formatting to post-arxiv
6. **Merge PR** — After sign-off from both rounds
7. **Tag v0.1** — Create GitHub release
8. **Announce** — Send to researchers + communities

---

## Schedule

| Time | Round | Owner | Status |
|------|-------|-------|--------|
| **Today @ 18:00** | Round 1 | Primary | In Progress |
| **Today @ 20:30** | Round 1 feedback | — | Pending |
| **Tomorrow @ 10:00** | Round 2 | Secondary | Pending |
| **Tomorrow @ 12:00** | Round 2 feedback | — | Pending |
| **Tomorrow @ 13:00** | Fix critical issues | Team | Pending |
| **Tomorrow @ 15:00** | Merge + Release | Owner | Pending |

---

## Ready? Start Round 1!

**Next step:** Primary reviewer begins critical path check.
**Target:** "Critical path clear ✓" within 3 hours.
