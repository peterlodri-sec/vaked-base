# PR #113 Review Kickoff: vakedc-zig Design & Bootstrap

**PR**: [peterlodri-sec/vaked-base#113](https://github.com/peterlodri-sec/vaked-base/pull/113)  
**Branch**: `claude/zig-vaked-compiler-parser-ahmm23`  
**Status**: Design + project scaffold (Phase 1 readiness)

---

## What You're Reviewing

A **design specification and project bootstrap** for a native Zig rewrite of the Vaked language compiler, targeting **complete feature parity** with the Python reference implementation (vakedc).

This PR is **NOT implementation** — it's architecture, design decisions, and project scaffolding. Phase 1 implementation follows once this design is approved.

---

## Key Deliverables (Read in This Order)

### 1. Design Spec (Primary)
📄 [`docs/superpowers/specs/2026-06-13-vakedc-zig-compiler-bootstrap.md`](../../docs/superpowers/specs/2026-06-13-vakedc-zig-compiler-bootstrap.md)

**What to assess**:
- ✅ Is the 4-stage pipeline architecture (lexer → parser → graph → emit) clear?
- ✅ Do the phase breakdown (1: parser→JSON, 2: checker+lowering, 3: LSP+dogfeeding) make sense?
- ✅ Is Ralph loop integration (`-ralphloop-cache` as native primitive) justified and clear?
- ✅ Are success criteria per phase specific and measurable?
- ✅ Does the file structure make sense?

**Key sections**:
- §2: Architecture (lexer/parser/graph/resolver/emit subsystems)
- §3: `-ralphloop-cache` rationale (closure: compiler describes itself)
- §4: Phase breakdown with acceptance criteria
- §5: File structure
- §6: Testing & verification (oracle test, determinism check)

### 2. Implementation Plan (Detailed)
📄 [`docs/superpowers/plans/2026-06-13-vakedc-zig-phase-1.md`](../../docs/superpowers/plans/2026-06-13-vakedc-zig-phase-1.md)

**What to assess**:
- ✅ Is the 15-hour time budget realistic?
- ✅ Are Zig type signatures correct (Token, Decl, Expr, App, GraphNode)?
- ✅ Is the PEG-ordered statement dispatch strategy sound?
- ✅ Does the newline-awareness handling look correct?
- ✅ Is the test strategy (unit + oracle + determinism) sufficient?

**Key sections**:
- §2: Lexer design (token kinds, Unicode, group tracking)
- §3: Parser design (AST types, soft-keyword dispatch, newline semantics)
- §4: Graph builder & resolver (node ID derivation, symbol table, edge emission)
- §5: JSON emission (deterministic, stable key order)
- §7: Testing checklist (debugging guidance)

### 3. Research Summary (Context)
📄 [`docs/superpowers/specs/2026-06-13-vakedc-zig-research-summary.md`](../../docs/superpowers/specs/2026-06-13-vakedc-zig-research-summary.md)

**What to assess**:
- ✅ Is the fan-out research of vakedc (Python reference) accurate?
- ✅ Are lexer/parser/graph/lowering characteristics correctly summarized?
- ✅ Is the test oracle strategy (byte-identical JSON vs. Python) sound?
- ✅ Does the dogfeeding loop closure make sense?

**Key sections**:
- §1: vakedc architecture overview (4-stage pipeline)
- §1.2–1.5: Subsystem characteristics (lexer/parser/graph/lowering)
- §1.6: Test verification approach
- §2: Design decisions (why Zig, architecture mapping)
- §3: Implementation strategy
- §6: Dogfeeding loop (vakedos.vaked → compile → deploy → observe → feed back)

### 4. Zig Project Scaffold
📁 [`vakedc-zig/`](../../vakedc-zig/)

**What to assess**:
- ✅ Is `build.zig` correct (stdlib-only, no external deps)?
- ✅ Do `src/{main,lexer,parser}.zig` have proper structure for Phase 1?
- ✅ Is the README clear about project status + usage?

**Files**:
- `build.zig`: Zig build config (executable + test targets)
- `src/main.zig`: CLI entry point (parse/lex/parse-ast subcommands)
- `src/lexer.zig`: Token types + Lexer struct (stubs)
- `src/parser.zig`: Parser struct (stub)
- `tests/test_main.zig`: Test harness placeholder
- `README.md`: Usage, architecture, dogfeeding plan

---

## Acceptance Criteria for This PR

### Architecture Soundness

- [ ] **4-stage pipeline is correct**: Lexer (tokens) → Parser (AST) → Graph (LPG) → Emit (JSON)
- [ ] **Phase breakdown makes sense**: Phase 1 parser validates before Phase 2 checker, Phase 2 checker validates before Phase 3 lowering
- [ ] **Ralph integration is justified**: `-ralphloop-cache` as memory primitive is explained and scoped
- [ ] **Success criteria are measurable**: All 15 examples parse, JSON byte-identical to Python, determinism verified

### Design Decisions

- [ ] **Why Zig is sound**: Embeddable in daemons, stdlib-only, deterministic (not a random choice)
- [ ] **Test oracle strategy is clear**: Byte-identical JSON comparison to Python reference (catches subtle bugs)
- [ ] **Determinism-first approach justified**: Stable node IDs + sorted JSON + per-artifact hashing

### Phase 1 Readiness

- [ ] **15-hour breakdown is realistic**: Lexer (4h), Parser (5h), Graph (3h), Emit+test (3h)
- [ ] **Zig types are correct**: Token, Decl, Expr, App, GraphNode definitions make sense
- [ ] **Parser dispatch strategy is sound**: PEG ordering (field/grant/order before assignment, open after)
- [ ] **Newline semantics are clear**: Suppressed in groups, terminate statements at depth 0

### Testing Strategy

- [ ] **Oracle test is sufficient**: Compare vakedc-zig JSON to vakedc (Python) byte-for-byte on all 15 examples
- [ ] **Determinism check is clear**: Two runs of same file must produce identical bytes
- [ ] **Debugging checklist is useful**: Covers token → AST → graph → JSON failure modes

### Documentation Quality

- [ ] **Three docs are self-contained**: Design spec, implementation plan, research summary each stand alone
- [ ] **Dogfeeding plan is clear**: vakedos.vaked → compile → deploy → observe → feed back → close loop
- [ ] **README is accurate**: Project status, usage, architecture overview are correct

---

## What NOT to Review (Out of Scope)

- ❌ Actual Phase 1 implementation (lexer/parser/graph/emit code) — that comes next
- ❌ Type checker implementation (deferred to Phase 2)
- ❌ Lowering implementation (deferred to Phase 2)
- ❌ LSP server (deferred to Phase 3)
- ❌ Dogfeeding deployment (deferred to Phase 3)

---

## Key Questions for Reviewers

### Architecture

1. **Is the 4-stage pipeline correct and complete?**
   - Lexer: tokens with byte spans ✓
   - Parser: AST matching EBNF v0.3 ✓
   - Graph: stable node IDs + edges ✓
   - Emit: canonical JSON ✓
   
   *Or are there missing stages/components?*

2. **Should Phase 1 include anything else before proceeding to Phase 2?**
   - Currently: parser validates language (no type checking)
   - Phase 2 adds: type checker (0011) + lowering (0012)
   
   *Or should Phase 1 include checker?*

3. **Is Ralph integration scoped correctly?**
   - Currently: sketched as `-ralphloop-cache` memory primitive
   - Implementation: Phase 2+ (after lowering is complete)
   
   *Or should it be Phase 1?*

### Design Decisions

4. **Is Zig the right choice, or should we reconsider Rust/Go?**
   - Zig: stdlib-only, embeddable, deterministic ✓
   - Tradeoff: smaller ecosystem, newer language
   
   *Any concerns?*

5. **Is byte-identical JSON comparison sufficient, or do we need stronger tests?**
   - Oracle test: vakedc-zig JSON == vakedc JSON on all 15 examples ✓
   - Determinism: two runs = identical bytes ✓
   
   *Or should we add property-based testing, fuzzing, etc.?*

### Phase 1 Scope

6. **Is the 15-hour budget realistic?**
   - Lexer: 4h (tokenization, NFC, group tracking)
   - Parser: 5h (recursive descent, soft keywords, newlines)
   - Graph: 3h (node instantiation, symbol table, edge emission)
   - Emit+test: 3h (JSON, oracle test, determinism)
   
   *Too optimistic, too pessimistic, or on target?*

7. **Should Phase 1 include error recovery, or defer to Phase 2?**
   - Currently: simple error tokens, defer recovery
   
   *Or is error recovery essential for Phase 1?*

---

## Timeline

- **Current**: Design review (this PR)
- **Next**: Phase 1 implementation (2–3 days, 6–9 hrs focused work)
  - Implement lexer, parser, graph, emit
  - Run oracle test (all 15 examples vs. Python reference)
  - Verify determinism
- **Then**: Phase 2 (type checker + lowering)
- **Future**: Phase 3 (LSP + dogfeeding vakedos.vaked)

---

## How to Review

1. **Start with design spec** (§2: architecture is the core)
2. **Skim implementation plan** (§3–§5 have Zig details; §7 has debugging guidance)
3. **Check research summary** for context (§1: vakedc architecture, §6: dogfeeding loop)
4. **Verify project scaffold** (build.zig, main.zig are correct)
5. **Ask questions** on specific sections if anything is unclear

**Expected time**: 30–45 minutes (design review, not deep code review)

---

## Links

- **PR**: https://github.com/peterlodri-sec/vaked-base/pull/113
- **Design Spec**: `docs/superpowers/specs/2026-06-13-vakedc-zig-compiler-bootstrap.md`
- **Phase 1 Plan**: `docs/superpowers/plans/2026-06-13-vakedc-zig-phase-1.md`
- **Research Summary**: `docs/superpowers/specs/2026-06-13-vakedc-zig-research-summary.md`
- **Zig Project**: `vakedc-zig/`
- **Reference**: `vakedc/README.md` (Python implementation)
- **Grammar**: `vaked/grammar/vaked-v0-plus.ebnf`
- **Type System**: `docs/language/0011-type-system.md`
- **Lowering**: `docs/language/0012-lowering.md`

---

## Notes

- **This is a design + bootstrap PR**, not implementation
- **Phase 1 is a well-scoped, 15-hour sprint** with clear acceptance criteria
- **Test oracle (byte-identical JSON) is the main quality gate**
- **Dogfeeding loop closes post-Phase 2** (once lowering is complete)

---

**Ready for review.** 🚀
