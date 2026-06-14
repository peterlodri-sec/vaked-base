# Vaked V1.0 Credibility Review Fixes — SDD Orchestration

**Date:** 2026-06-14  
**Scope:** Address 10 credibility risks identified in hostile review (vaked-language-v0.1.md publication)  
**Target:** Ship-ready paper by 2026-08-31 (8 weeks)  
**Methodology:** Subagent-driven development (5 dependency-ordered waves)  
**Orchestrator:** [you] — gates, merges, ledger only (no code/spec writing)

---

## Wave DAG (Dependency Graph)

```
P0 Frame [orch]
  ├─→ P1 Research (parallel, 3 agents)
  ├─→ P2 Spec (blockers: P1 green)
  ├─→ P3 Code (blockers: P2 green; parallel worktrees)
  ├─→ P4 Test (blockers: P3 green; independent)
  └─→ P5 Broker (blockers: P4 green; stacked PRs)
```

---

## Phase P0 — Frame & Decompose

**Orchestrator Input:** Credibility review findings (vaked-v1-credibility-review-session-2026-06-14.md)

**Decomposition into 5 waves:**

### Wave 1: Formalize Definitions & Terminology (FOUNDATION)

**Why first:** All downstream specs depend on formal definitions of Principal, Capability, Attenuation Order, POLA.

| Risk | Action | Owner | Acceptance Criteria |
|------|--------|-------|-------------------|
| Risk 10: Terminology undefined | Draft Definitions section (Appendix A.1) with 10 formal definitions | spec-author | Lexicon covers: Principal, Capability, Attenuation Order, Granted, Used, Structural Typing, POLA, Conformance, Provenance, LPG |
| Risk 10: Glossary missing | Expand each definition with 1-sentence plain-English gloss | spec-author | All 10 terms have formal + gloss; internal cross-refs validate |

**Gate:** `dockeeper` 0 errors on new definitions section; proof-reader (not author) approves clarity.

---

### Wave 2: POLA Proof Strategy & Runtime Design (CORE)

**Why:** Risks 1, 5 are foundational; all claims about security rest on these.

| Risk | Action | Owner | Acceptance Criteria |
|------|--------|-------|-------------------|
| Risk 1: Soundness proof informal | Decide: (A) Machine-check in Coq/Lean, or (B) Reposition as "informal soundness argument" | researcher | Decision recorded with reasoning; if (A), scaffold RFC 0010-pola-formalization.md |
| Risk 5: Runtime enforcement missing | Design spec for minimal Zig daemon + eBPF policy emitter | spec-author | RFC 0011-runtime-enforcement.md drafted; diagram of daemon → kernel → syscall chain |
| Risk 5: Runtime enforcement missing | Stub implementation (reference only; not production-ready) | coder (worktree) | eBPF allow-list generator emits valid BPF code; Zig daemon compiles cleanly with 0 warnings |

**Gate:**
- If (A): Coq proof file compiles (`coq_makefile`); informal sketch removed from paper
- If (B): Abstract revised; threat-model clarified
- Daemon stubs compile; `zig build test` passes on reference examples

---

### Wave 3: Data Validation & Benchmarks (EVIDENCE)

**Why:** Risks 2, 4 undermine credibility; re-running benchmarks with full transparency is prerequisite for any submission.

| Risk | Action | Owner | Acceptance Criteria |
|------|--------|-------|-------------------|
| Risk 2: Determinism data contradicts | Re-run determinism oracle with 100 iterations per example; publish SHA-256 hashes | coder (worktree) | `baseline-2026-06-14.json` contains 22 × 100 = 2200 runs; hash convergence ≥99.5% for valid rows |
| Risk 4: Scalability failure hidden | Compile 10, 100, 500, 1K, 5K, 10K fiber examples; plot (fibers vs. time) | coder (worktree) | Plot saved to `docs/evaluation/scalability.png`; complexity curve labeled O(n), O(n log n), O(n²) |
| Risk 4: O(n²) bottleneck | Profile vakedc lower stage; identify bottleneck; either fix or document | coder (worktree) | If fixed: benchmark re-run shows improvement; if documented: §5.4 updated with complexity analysis + roadmap |
| Risk 6: Negative tests missing | Write 8 test cases where POLA should be violated | test-author (independent) | `test/negative/pola-violations/{use-check, attenuation-check, domain-mismatch, ...}` each with `.vaked` file + expected error |

**Gate:**
- All 22 examples run cleanly; determinism ≥99.5%
- Scalability plot shows measured data for 10, 100, 500, 1K, 5K, 10K
- 8 negative tests each produce expected error diagnostic (`E-CAP-USE`, `E-CAP-ATTENUATION`, etc.)

---

### Wave 4: Implement Fixes & Generate Artifacts (BUILD)

**Why:** Missing diagrams, soft claims, incomplete case-study table all lower perceived rigor.

| Risk | Action | Owner | Acceptance Criteria |
|------|--------|-------|-------------------|
| Risk 3: Lowering is 50% incomplete | Audit §3.3.1; clarify emitter status matrix | spec-author | Table: 8 emitters, 4 implemented (✅), 4 deferred (🟡) with v0.2 target |
| Risk 7: Domains undefined | Show `capability` declaration syntax; example defining `custom` domain | coder (worktree) | Example in `examples/custom-domain.vaked` compiles; schema validation proves acyclicity of attenuation order |
| Risk 8: Novelty claim unsubstantiated | Create feature matrix: Nickel/CUE/OPA/SPIFFE/Dhall vs. Vaked (3-axis: struct types, POLA checking, deterministic lowering) | researcher | Matrix shows which combination is unique to Vaked; if competitors exist, update claims |
| Risk 9: Case-study metrics inconsistent | Unified benchmark table: all 7 cases with Lines, Nodes (clarify definition), Parse/Check/Lower times, Determinism, Errors | coder (worktree) | Table in §5.2 with footnotes explaining node-count taxonomy |
| Diagram: POLA flowchart | Author: parse → resolve → check (POLA) stages visually | spec-author | Flowchart in §3 or appendix with decision points highlighted |
| Diagram: Attenuation order DAG | Author: example from paper (e.g., `fs` domain) showing allowed/forbidden transitions | spec-author | Visual in §3.2.2 or appendix |
| Diagram: Delegation chain | Author: §5.2.2 (planning → implementation → testing) with capability flow annotated | spec-author | Diagram in case-study section |
| Diagram: Scalability plot | Already generated in Wave 3 | — | — |

**Gate:**
- All 8 diagrams present and reviewed for clarity
- Feature matrix published with reasoning
- All 7 case studies in one coherent benchmark table
- `examples/custom-domain.vaked` validates domain extension claim

---

### Wave 5: Patch Abstract & Integrate PRs (FINALIZE)

**Why:** Claims must be softened/reframed per hostile review before any submission.

| Risk | Action | Owner | Acceptance Criteria |
|------|--------|-------|-------------------|
| All 10 risks | Apply 5 recommended patches to abstract + critical sections | coder (worktree) | Patch 1: POLA claim reframed; Patch 2: determinism data corrected; Patch 3: lowering clarified; Patch 4: negative tests added; Patch 5: definitions formalized |
| Integration | Stacked PRs: RFC(s) → paper revisions → new tests → benchmarks | broker | 5 dependent PRs, each marked ready-for-review; no auto-merge |

**Gate:**
- All patches applied; no absolute claims remaining ("enforces", "proves", "deterministic")
- Abstract revised per Patch 1
- `dockeeper` 0 errors
- CI green on all 5 PRs

---

## Roles & Worktrees

| Role | Count | Worktree | Models |
|------|-------|----------|--------|
| orchestrator | 1 | none (main) | — |
| researcher | 3 | N/A (read-only) | deep-research (Opus, Sonnet) |
| spec-author | 1 | none (edits plan doc + dossier) | Sonnet (structured output) |
| coherence-critic | 1 | none (read-only) | Opus (adversarial) |
| coder | 3 | `wt-determinism`, `wt-scalability`, `wt-fixes` | Sonnet (isolated worktrees) |
| test-author | 1 | `wt-tests` (independent) | Haiku (parallel test generation) |
| reviewer | 1 | none (diff review) | Opus (pr-review skill) |
| broker | 1 | none (stacked PRs, no merge) | Sonnet (GitHub MCP) |

---

## Acceptance Gates per Wave

### Wave 1 Gate (Definitions)
- [ ] Appendix A.1 drafted with 10 formal definitions + glosses
- [ ] `dockeeper` validation: 0 errors
- [ ] Proof-reader (not author) confirms clarity
- **Estimated effort:** 1 day

### Wave 2 Gate (POLA & Runtime)
- [ ] POLA proof path decided (Coq or reposition)
- [ ] RFC 0010 (if Coq path) or updated threat-model (if reposition) reviewed
- [ ] Minimal Zig daemon stub compiles; eBPF emitter generates valid BPF
- **Estimated effort:** 2–3 days

### Wave 3 Gate (Data Validation)
- [ ] Determinism oracle: 22 examples × 100 runs, ≥99.5% hash convergence
- [ ] Scalability plot: measured data for 10, 100, 500, 1K, 5K, 10K fibers
- [ ] 8 negative test cases, each producing expected error
- [ ] O(n²) bottleneck either fixed or formally documented
- **Estimated effort:** 3–4 days

### Wave 4 Gate (Artifacts)
- [ ] All 8 diagrams completed and clarity-reviewed
- [ ] Feature matrix: Nickel/CUE/OPA/SPIFFE/Dhall vs. Vaked
- [ ] Unified benchmark table (all 7 case studies, consistent node-count definition)
- [ ] Custom domain example compiles and validates
- **Estimated effort:** 2–3 days

### Wave 5 Gate (Finalize)
- [ ] All 5 patches applied; abstract reframed
- [ ] Stacked PRs opened (5 PR chain, dependency-ordered)
- [ ] `dockeeper` 0 errors; CI green on all PRs
- [ ] Ready-for-review status (not auto-merged)
- **Estimated effort:** 1 day

---

## Ledger & Resumability

Each wave closes with an entry in this plan file:

```
## Wave [N] Ledger

**Opened:** [date] [time] UTC  
**Closed:** [date] [time] UTC  
**Hash:** [first commit of wave]

**Status:** ✅ PASS | ❌ FAIL | 🟡 BLOCKED

**Artifacts:**
- [file path]: [brief description]

**Decisions:**
- [decision 1]: [rationale]

**Blockers (if any):**
- [issue]
```

This ledger allows resumption across sessions/container restarts.

---

## Timeline (8 weeks total)

| Week | Waves | Milestones |
|------|-------|-----------|
| Week 1 (Jun 14–20) | P0, P1, P2 | Definitions drafted; research dossier; spec scaffolded |
| Week 2 (Jun 21–27) | P2 gate, P3 start | Spec reviewed; coding worktrees active |
| Weeks 3–4 (Jun 28–Jul 11) | P3, P4 | Determinism re-run; scalability benchmark; negative tests |
| Week 5 (Jul 12–18) | P4 gate, P5 start | Tests green; diagrams finalized; PR prep |
| Weeks 6–7 (Jul 19–Aug 1) | P5 | Patches applied; stacked PRs ready-for-review |
| Week 8 (Aug 2–8) | Review & feedback | Human reviewers approve or request changes |
| Target completion | — | 2026-08-31 (ship-ready for PLDI 2027 / ICFP 2027 submission) |

---

## Anti-patterns (Do NOT)

- ❌ Orchestrator writing specs or code (delegate to agents)
- ❌ Fanning P3 before P2 gate is green
- ❌ Test-author seeing coder's implementation before writing tests
- ❌ Building on developer machine (use dev-cx53 or GHA)
- ❌ Auto-merging PRs; stop at ready-for-review
- ❌ Merging P3 before P4 tests pass

---

## Success Criteria (End of P5)

1. Paper passes hostile review in all 10 risk categories (claims softened or proven)
2. Determinism oracle shows ≥99.5% hash convergence (transparent data, no cherry-picking)
3. Scalability benchmarks published (measured data, complexity curve labeled)
4. 8 negative tests validate POLA rejection (not just validation)
5. All diagrams present and clear
6. Stacked PRs ready-for-review (no merge until human approval)

---

**Status:** P0 COMPLETE. Ready to fan-out P1 researchers.

**Next step:** Launch 3 research subagents (P1) for:
1. POLA proof feasibility study (Coq/Lean effort, alternatives)
2. Runtime enforcement design patterns (compare Zig daemon models)
3. Novelty claim validation (feature matrix across related systems)
