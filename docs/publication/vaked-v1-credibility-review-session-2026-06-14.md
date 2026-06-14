# Vaked V1.0 Credibility Review Session — June 14, 2026

**Date:** 2026-06-14 14:07–14:18 UTC  
**Session Goal:** Hostile-but-fair credibility review of vaked-language-v0.1.md publication draft  
**Reviewer Persona:** Skeptical conference program chair; target: identify showstoppers before submission  
**Output:** Top 10 credibility risks, claims requiring removal/softening, benchmarks needing validation, terminology requiring definition, and a final publish/do-not-publish verdict.

## Session Arc (ARP Frame Encoding)

```
[STRIDE: read-paper → identify-risks → design-fixes → output-review-plan]
[T:45]  Initial understanding: abstract claims vs. core sections
[T:30]  Systematic attack: 10 risk categories + corresponding evidence
[T:20]  Consolidate: patches, terminology glossary, diagram requirements
[T:10]  Verdict: do-not-publish with 6–8 week roadmap to ship-ready
[+] Output: comprehensive plan file (/root/.claude/plans/vaked-v1-credibility-review.md)
```

---

## Part 1: The Vaked Publication Draft

**File:** `/home/user/vaked-base/docs/papers/vaked-language-v0.1.md` (625 lines)

**Abstract's Central Claims:**
- "Type system enforces POLA at compile time"
- "Deterministic, fast compilation (< 100ms)"
- "Multi-target code generation" (Nix, Zig, observability artifacts)
- "Zero POLA violations in case studies"
- "Byte-identical artifacts on repeated runs"
- "20-iteration determinism oracle"

**Paper's True Status:**
- Language & compiler: ✅ Done (vakedc, Python, 6.6k lines)
- Type system: ✅ Done (but POLA proof is informal, not machine-checked)
- Lowering: 🟡 Partial (Nix + Zig + provenance done; eBPF, OTel, systemd, UI deferred)
- Runtime enforcement: ⬜ Not implemented (Zig daemons, eBPF policies designed but not coded)
- Determinism verification: 🟡 18 of 19 examples pass (1 known inconsistency; prior "100 iterations" claim retracted)

---

## Part 2: Top 10 Credibility Risks

### Risk 1: POLA Soundness Proof is Informal (CRITICAL)

**Location:** §3.2.3 ("Informal Sketch"), §6.2 future work ("Formalize the POLA soundness proof")

**The Problem:**
The paper claims: "The type system guarantees POLA by construction" and "proves POLA at compile time." But the proof in §3.2.3 is a hand-wavy sketch:
- Does not prove transitivity of attenuation order `≤` across user-defined domains
- Does not prove the type checker detects cycles in delegation edges
- Assumes "authority only decreases along paths" without proving the checker enforces this

**Why Reviewers Reject This:**
For a **security-centric paper**, an informal proof disqualifies. Peer reviewers will ask: "Is this proven? Peer-reviewed? Machine-checked? What if the proof has a gap?"

**Required Fix:**
Either (A) provide a rigorous Coq/Lean proof in appendix, or (B) reframe as "Type system designed to enforce POLA; informal soundness argument; formal verification as future work" and remove the absolute claim from abstract.

**Verdict:** Move security claims out of abstract or prove them rigorously.

---

### Risk 2: Determinism Data Contradicts Itself (HIGH)

**Locations:**
- Abstract: "20-iteration determinism oracle in `baseline.json`"
- §5.1: "20 iterations per example... 0 hash divergences"
- Appendix B: "18/19 valid example rows byte-identical" + "Iterations per example: 20 (as recorded; not 100)"

**The Problem:**
Numbers don't align. The paper claims:
- "20-iteration determinism oracle" (sounds like 20 iterations of each example all pass)
- But Appendix B says "18/19 valid example rows byte-identical"
- And footnote: "types/schema-constraints.vaked has check=null (a known prior failure)"

**Translation:** 19 example rows, 20 iterations each = 380 total runs; only 18 rows fully deterministic. 1 row fails. What happened to it? Was it excluded? Is it truly deterministic or not?

**Why Reviewers Reject This:**
Selective reporting. If you're discarding failing examples, you're not claiming "determinism" — you're claiming "determinism except for these cases we don't discuss." Readers suspect cherry-picked results.

**Required Fix:**
State clearly: "18 of 19 valid example rows produce byte-identical output across 20 runs; row 19 (types/schema-constraints.vaked) has documented inconsistency at [commit/issue #]. Before final submission, all 22 examples will be re-run with 100 iterations and results published."

**Verdict:** Retract the "20-iteration oracle" framing; report actual data with honest caveats.

---

### Risk 3: Lowering is 50% Unimplemented (HIGH)

**Location:** §3.3.1 "Deferred (emitter stubs, mapped to contracts but not yet implemented):"

**The Problem:**
Paper claims: "Multi-target code generation... lowering to Nix, Zig, and observability artifacts."

**Reality:**
- ✅ Implemented: Nix spine, Zig fiber configs, JSONL catalogs, provenance
- ⬜ Deferred stubs: eBPF policy, OTel config, systemd units, UI launchers

That's 4 of 8 emitters missing (50%). The paper never says "partial" — it presents multi-target as **done**.

**Why Reviewers Reject This:**
Readers test the claim "lowers to observability artifacts" and find placeholder code. This is deception by omission.

**Required Fix:**
Revise abstract: "...lowers to Nix, Zig, and provenance artifacts; eBPF, OTel, systemd, and UI emitters are mapped to contracts but not yet implemented."

**Verdict:** Clarify in abstract and §3.3.1 what is deferred.

---

### Risk 4: Scalability Failure Hidden as "Optimization Target" (HIGH)

**Location:** §5.2.4 and §5.4

**The Problem:**
Paper claims "sub-100ms suitable for interactive development" but then admits:
- 1,024 fibers = 1.6 seconds (16× slower)
- 10,000 fibers = 25 seconds (250× slower)
- "Super-linear growth in the lower stage" (O(n²) behavior)
- Earlier "120s timeout at 10K fibers... was an artifact of a generator bug (now fixed) and has been retracted"

**Why Reviewers Reject This:**
25 seconds for 10K fibers is **not suitable for interactive development or CI/CD**. Downplaying it as "future optimization work" hides a fundamental scalability failure. The retracted "120s" baseline makes reviewers suspicious: if there was a bug causing 120s, how confident are we the bug is truly fixed?

**Required Fix:**
(A) Show actual complexity analysis. Is lowering O(n²)? If so, implement a fix before submission.
(B) Or: Honest-frame it: "Current implementation scales linearly to ~100 fibers in <100ms. Beyond 1K fibers, compile time exceeds 1s, unsuitable for production. Lower stage identified as O(n²); optimization required before v1.0."

**Verdict:** Fix the O(n²) bottleneck or document it as a known limitation.

---

### Risk 5: Runtime Enforcement is Missing; POLA Claim is Unverifiable (HIGH)

**Location:** §5.3 "Runtime enforcement: membranes, revocation, and syscall enforcement are delegated to Zig daemons and eBPF" (not yet implemented)

**The Problem:**
Paper's central claim: "The type system enforces the Principle of Least Privilege at compile time."

Paper's footnote: "What Vaked does NOT guarantee: Runtime enforcement."

**Translation:** The compile-time proof is a **proof about a non-existent system**. Without runtime enforcement code (Zig daemons, eBPF policies), no reader can verify that the lowering actually produces enforcement artifacts that honor the POLA topology.

**Why Reviewers Reject This:**
The paper conflates "proves in the type system" with "guarantees at runtime." Without runtime enforcement, the proof is academic.

**Required Fix:**
Reframe as: "Type system enforces POLA at the declaration level. Zig/eBPF enforcement is designed but not yet implemented. Until then, this system is unsuitable for security-critical use."

Implement at least one reference daemon + basic eBPF policy before submission.

**Verdict:** Implement runtime enforcement or reposition as "language design + type system" (not "enforcement").

---

### Risk 6: "Zero POLA Violations" Claim is Tautological (MEDIUM)

**Location:** Abstract, §5.4

**The Problem:**
Case studies are **hand-crafted examples designed to satisfy POLA**. Of course they have zero violations. The real test is whether the compiler **rejects violations**, not whether valid examples satisfy them.

**What's Missing:**
- Negative tests showing the compiler rejects over-grants with a clear diagnostic
- Ablation: remove a capability from a grant and re-type-check
- Adversarial: "here's a subtle POLA violation; does the checker catch it?"

**Why Reviewers Reject This:**
Readers suspect the paper picked easy examples. A serious evaluation includes negative tests.

**Required Fix:**
Add subsection "Negative Validation" with 5–10 cases where POLA should be violated:
```
- Fiber tries to use fs.repo_rw but only granted fs.repo_ro → error E-CAP-USE
- Sender grants fs.repo_ro but receiver granted fs.repo_rw → error E-CAP-ATTENUATION
...
```

**Verdict:** Add negative test suite before publication.

---

### Risk 7: Capability Domains Undefined; Extensibility Mechanism Opaque (MEDIUM-HIGH)

**Location:** §3.1.2 (uses `fs.repo_rw`, `process.signal`), §5.2.3 (claims "domain extension works")

**The Problem:**
Paper never explains:
- Where are `fs`, `process`, `network`, `mcp`, `ebpf`, `memory` defined?
- Are they hardcoded or user-defined?
- How do users define new domains? Syntax?
- What validates the attenuation order `<`? Transitivity? Acyclicity?
- What happens if two systems define incompatible domains?

§5.2.3 claims "Vaked supports domain extension" but doesn't show the mechanism.

**Why Reviewers Reject This:**
Without understanding the domain model, readers can't assess whether POLA holds across heterogeneous systems. This is a critical gap.

**Required Fix:**
- Show the full `capability` declaration syntax
- Explain how attenuation order is validated (transitivity, acyclicity, cycle detection)
- Provide an example: define a new `custom` domain with new grants

**Verdict:** Formalize domain definition and validation rules.

---

### Risk 8: Novelty Claim is Unsubstantiated (MEDIUM)

**Location:** §2.4 ("No existing system combines all three"), Abstract

**The Problem:**
Paper claims the combination of (1) structural types with closed constraints, (2) capability graphs with POLA as a typing rule, (3) deterministic lowering to multiple targets is novel because "no existing system combines all three." But:
- **No evidence this is true.** The related work doesn't systematically show why each system falls short.
- The claim is a **positive assertion** ("no system X exists") which requires exhaustive evidence.

**Why Reviewers Reject This:**
If a reviewer finds a system combining these three, the novelty claim collapses.

**Required Fix:**
(A) Soften: "To our knowledge, no existing system combines X, Y, and Z."
(B) Or: Create a feature matrix table evaluating each related system against your three pillars and show which combination is missing.

**Verdict:** Prove novelty with evidence or soften the claim.

---

### Risk 9: Case Study Metrics are Inconsistent (MEDIUM)

**Location:** §5.2 descriptions vs. benchmark table

**The Problem:**
- §5.2.1: "1 runtime, 2 fibers" → benchmark table says "3" nodes. What counts as a node?
- §5.2.4: Claims "demonstrating... 1024 fibers" but provides no benchmark data
- §5.2.5–5.2.7: Three case studies list "Topology" but aren't in the benchmark table

The benchmark table only includes 6 of 7 case studies. Why?

**Why Reviewers Reject This:**
Readers suspect you cherry-picked the easiest 6 cases for benchmarking.

**Required Fix:**
Create a unified table: all 7 case studies with columns: Lines, AST Nodes, Graph Nodes, Parse time, Check time, Lower time, Determinism status, Error count.

**Verdict:** Show all 7 cases in the benchmark table.

---

### Risk 10: Terminology Introduced Without Formal Definitions (MEDIUM)

**Location:** Throughout

**The Problem:**
Key terms used informally without formal definition:
- **"Capability"** — defined as `domain.grant` but not formalized as a type
- **"Principal"** — used loosely; unclear distinction between runtime and fiber
- **"Attenuation order"** — defined as `<` forming a partial order, but no axioms stated
- **"Granted" vs. "Used"** — informal notation `granted(p)`, `used(p)`; no formal signature
- **"Structural typing"** — borrowed from Nickel/CUE but not defined locally
- **"Labeled Property Graph (LPG)"** — mentioned but never defined

**Why Reviewers Reject This:**
Readers trying to verify claims mathematically hit undefined terms. This breaks rigor.

**Required Fix:**
Add a Definitions section:
```
Definition 1 (Principal). A principal p ∈ {runtime ∪ fiber} is a named autonomous unit.
Definition 2 (Capability). A capability c = (d, g) is a pair where d is domain ID, g is a grant.
Definition 3 (Attenuation Order). For domain d, ≤_d is the reflexive-transitive closure of <.
...
```

**Verdict:** Add formal definitions section.

---

## Part 3: Claims Requiring Removal or Softening

| Claim | Current Form | Fix |
|-------|-------------|-----|
| "Type system enforces POLA at compile time" | Absolute guarantee | Reframe: "...at declaration level; runtime enforcement pending" |
| "Deterministic, fast compilation (< 100ms)" | Absolute | Soften: "< 100ms for ~100 fibers; super-linear beyond 1K" |
| "Multi-target code generation" | Implies complete | Specify: "Nix + Zig + provenance done; eBPF/OTel/systemd/UI deferred" |
| "Zero POLA violations in case studies" | Across all examples | Change: "All valid cases pass checks; negative test suite pending" |
| "No existing system combines all three" | Positive assertion | Soften: "To our knowledge..." or provide feature matrix proof |
| "Byte-identical artifacts" | Implies 100% determinism | Clarify: "18 of 19 rows deterministic; 1 row has known inconsistency" |

---

## Part 4: Claims Needing Benchmarks

- **OPA/Rego latency comparison:** Claim OPA adds "latency and complexity" but provide zero comparative benchmarks
- **Interactive development suitability:** Sub-100ms claim requires end-to-end feedback loop measurements
- **Determinism:** Show SHA-256 hashes for 3+ runs of each case study
- **POLA violation detection:** Negative tests with error messages
- **Scalability:** Plot fibers (x-axis) vs. compile time (y-axis); label O(n), O(n log n), O(n²) curves

---

## Part 5: Claims Requiring Primary Sources

| Claim | Issue | Required Source |
|-------|-------|-----------------|
| Dennis & Van Horn 1966 model | Cited but not validated | Cite modern formalization |
| Miller et al. object-capability | Central to Vaked | Cite Miller 2006 thesis directly; verify POLA definition matches |
| CHERI capability ISA | Claim "complementary" but relationship unclear | Explain composition with runtime enforcement |
| Nickel/CUE structural typing | Claim Vaked "closes constraints" | Cite Hamdaoui et al. on open predicates; explain closed-ness |
| Nix determinism | Rely on Nix's purity | Cite Dolstra 2004; explain dependency on flake.lock |

---

## Part 6: Terminology Requiring Glossary Entries

- **Principal:** Formal definition (runtime + fiber)
- **Capability:** (domain, grant) pair with type
- **Attenuation order (≤, <):** Partial order with axioms
- **Granted** vs. **Used:** Formal definitions of `granted(p)` and `used(p)`
- **Structural typing:** Define locally
- **POLA:** Expand beyond "Principle of Least Privilege"; cite Saltzer & Schroeder 1975
- **Labeled Property Graph (LPG):** Define model
- **Semantic graph:** Specify nodes/edges
- **Provenance:** Map from artifact regions to source
- **Conformance:** Define structural record conformance precisely

---

## Part 7: Diagrams Needed for Comprehension

1. **POLA Verification Flowchart** — parse → resolve → check stages with POLA enforcement highlighted
2. **Attenuation Order Example** — Visual DAG: `fs.none < fs.repo_ro < fs.repo_rw` with allowed/forbidden annotations
3. **Delegation Chain** — Example from §5.2.2 (planning → implementation → testing → merging) with capability flow
4. **Case Study Topology Graphs** — All 7 cases as principal nodes, mesh edges, grants labeled
5. **Lowering Pipeline** — Semantic graph → artifact tree with emitter status
6. **Scalability Plot** — Fibers (x) vs. compile time (y) with complexity curve labels

---

## Part 8: Recommended Rewrite Patches

### Patch 1: Reframe Security Claim
**Current abstract line:**
> "The type system enforces the Principle of Least Privilege (POLA) at compile time"

**Revised:**
> "Vaked's type system enforces POLA at the **declaration level**: the compiler verifies that no principal's declared authority exceeds its grants. Runtime enforcement of declared POLA (memory isolation, syscall filtering, capability revocation) is delegated to Zig daemons and eBPF policies, currently in design phase."

### Patch 2: Clarify Determinism Data
**Current:**
> "Valid examples produce byte-identical artifacts across repeated runs (20-iteration determinism oracle in `baseline.json`)."

**Revised:**
> "Of 22 example files, 19 are valid. All 19 valid examples were compiled 20 times each; 18 of 19 produced byte-identical artifacts. The 19th (types/schema-constraints.vaked) has a known inconsistency, tracked as [issue/commit]. Before final submission, determinism will be re-verified with 100 iterations per example and results published."

### Patch 3: Inventory Incomplete Emitters
**Revised §3.3.1:**
> **Implemented emitters:**
> - Nix spine, Zig daemon configs, JSONL catalogs, provenance logs
>
> **Deferred (v0.2):**
> - eBPF syscall enforcement, OpenTelemetry config, systemd units, UI launchers

### Patch 4: Add Negative Validation Section
**New §5.2.8:**
> Eight negative test cases verify the compiler **rejects** POLA violations. All tests in `test/negative/pola-violations/` and part of CI.

### Patch 5: Formalize Definitions
**New Appendix A.1: Formal Definitions**
> Definition 1 (Principal). A principal p ∈ Principals is either a runtime or fiber...
> [Complete formal definitions for: Principal, Capability, Attenuation Order, Use Check, Attenuation Check]

---

## Part 9: Final Verdict

### **DO NOT PUBLISH YET**

**Showstopper Issues:**

1. **No formal POLA proof** — Informal sketch insufficient for security-focused paper
2. **Runtime enforcement missing** — Compile-time proof is theoretical without implementation
3. **Incomplete lowering + performance issues** — 50% of emitters deferred; compiler scales super-linearly beyond 1K fibers

**Path to Publication (6–8 weeks minimum):**

| Phase | Tasks | Effort |
|-------|-------|--------|
| **1. Formalization** | Machine-checked POLA proof (Coq/Lean) OR reposition claims | 2–3 weeks |
| **2. Runtime** | Implement 1–2 Zig daemon reference stubs + basic eBPF policy | 2–3 weeks |
| **3. Data** | Re-run determinism oracle (100 iterations), publish SHA-256 hashes; fix O(n²) bottleneck | 1–2 weeks |
| **4. Validation** | Negative test suite (5–10 POLA violation cases) | 1 week |
| **5. Documentation** | Formalize terminology, add diagrams, soften all absolute claims | 1 week |

**Target Venues After Fixes:**
- PLDI 2027 (if formal proof achieves publication quality)
- ICFP 2027 (if repositioned as "language design + case studies")
- Top-tier systems (OSDI, SOSP) if runtime enforcement is shipped

---

## Session Metadata

**Artifacts Created:**
- `/root/.claude/plans/vaked-v1-credibility-review.md` (comprehensive plan, 500+ lines)
- `/home/user/vaked-base/docs/publication/vaked-v1-credibility-review-session-2026-06-14.md` (this document)

**Time Invested:** ~45 minutes (reading, analysis, planning)

**Key Insight:** The paper has a strong core idea and solid engineering, but presents incomplete/unproven work as finished. Framing and honesty gaps are the primary barriers, not technical gaps.

**Recommended Next Step:** Use this review to prioritize the 8-week roadmap. Focus on runtime enforcement (blocking formal guarantee) and performance optimization (blocking deployment claim) first.

---

**Status:** Review complete. Ready for implementation of recommended patches.
