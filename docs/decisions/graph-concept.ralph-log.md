# Ralph decision log — graph-concept

> Machine-generated, ADVISORY. Each entry is one strategic decision surfaced by the ralph loop (qwen3-235b-thinking → deepseek-v4-flash). A human ratifies; entries are appended, never rewritten.

## 2026-06-13 — Decision #1: Decision / question:** Decide whether to merge 'memory' into the type system as 
- **Track:** graph-concept · **Models:** stage1 deepseek-v4-flash · stage2 deepseek-v4-flash
- **Context snapshot:** HEAD 39a6185, 0 open issues

**Decision / question:** Decide whether to merge 'memory' into the type system as a first-class primitive or keep it as a runtime library

**Options:**
1. **First-class primitive** — Add `memory` as a new top-level kind in the grammar, type system, and lowering pipeline, with its own schema, capability domain (`mem`), and emitter (`memory.store` in the 0012 registry).
2. **Runtime library** — Keep `memory` as an external runtime component (e.g., a Zig daemon or OTP process) that agents interact with via opaque streams or APIs, with no special type-system support.
3. **Hybrid** — Add `memory` as a first-class primitive in the type system for declaration and validation, but defer the runtime implementation (eventd integration, memoryd daemon) to a later phase.

**Recommendation:** Option 1 — First-class primitive, with the runtime implementation deferred to a separate design/implement cycle (consistent with the staged adoption pattern from 0013).

**Risks:**
- **Grammar and checker complexity** — Adding a new top-level kind requires changes to the EBNF grammar, the type-checking pipeline (0011 §6.1), and the built-in schema catalog (`parallel-types.md`). This is a non-trivial surface-area change that must be coordinated with the existing `index`, `catalog`, `stream`, `fiber`, `surface`, `mesh`, `device`, `mediaPipeline`, `parallel`, `engine`, `capability`, and `schema` kinds.
- **Capability domain collision** — The proposed `memory` capability domain name collides with the `schema memory` declaration in the LPG's kind-agnostic decl ids (noted in 0014 as issue #25). The recommendation uses `mem` as the domain name, which avoids the collision but introduces a naming inconsistency (`memory` kind vs. `mem` capability).
- **Runtime dependency** — The primitive's semantics depend on the eventd log (#18) and the memoryd daemon, neither of which exist yet. Without the runtime, the lowering emitter (`memory.store`) produces config files that reference non-existent daemons, creating a "dead artifact" risk.
- **Scope creep** — The `memory` primitive introduces runtime-appended, mutable state into a system designed for deterministic, build-time validation. This could erode the "validate before generating" invariant if not carefully bounded (e.g., mining is a runtime effect, not an evaluation-time one — 0014 is explicit about this, but the boundary must be enforced in the checker).

**Next actions:**
1. **Land the grammar change** — Add `memory` as a top-level kind in `vaked-v0-plus.ebnf`, with the schema fields from 0014 (`source`, `schema`, `mine`, `scope`, `retention`, `emit`). This is the blocking dependency for all downstream work.
2. **Update the built-in schema catalog** — Add the `memory` schema and the `mem` capability domain to `parallel-types.md`, with the `none < recall < append < admin` order.
3. **Implement the checker rule** — Add conformance checking for `memory` declarations (0011 §1.1), including the `nonempty` constraint on `source`, the `oneof` constraint on `scope`, and the capability-flow check for the `mem` domain (0011 §4.3–§4.4).
4. **Implement the lowering emitter** — Add the `memory.store` emitter to the 0012 §3.4 registry, emitting `gen/memory/<name>.json` per memory decl. This is a pure projection of the typed graph (0012 §2.4) and requires no runtime.
5. **Add the `gen/eventd.json` emitter** — Emit the per-runtime eventd log path whenever a runtime declares any memory or workflow (0014 lowering table). This is a structural artifact that references the eventd daemon contract.
6. **Defer the runtime implementation** — Create a tracking issue for the memoryd daemon (roster entry, eventd integration, recall API) and mark it as a post-MVP dependency. The lowering emitter produces config files that are valid but reference a non-existent daemon; the daemon implementation is a separate design → plan → implement cycle.

**Confidence:** High — The design is well-motivated (0014 §"Why a new primitive"), the schema is concrete, the capability domain is defined, and the lowering emitter is a pure projection with no runtime dependency. The grammar and checker changes are bounded and follow established patterns (0011 §1–§3, 0012 §3.4). The only uncertainty is the runtime implementation timeline, which is explicitly deferred.

## 2026-06-13 — Decision #2: Decision / question:** Should `memory` become a first‑class primitive in the typ
- **Track:** graph-concept · **Models:** stage1 deepseek-v4-flash · stage2 deepseek-v4-pro
- **Context snapshot:** HEAD 39c6841, 0 open issues

**Decision / question:** Should `memory` become a first‑class primitive in the type system (kind), or remain an external runtime concern?

**Options**
1. **First‑class primitive** — Add `memory` as a new top‑level kind in the grammar and type system. The checker validates memory declarations under the closed constraint set (0011 §3); lowering emits pure projection artifacts per 0012. Runtime daemon is deferred.
2. **Runtime library** — Keep memory outside the language; agents interact via opaque streams/APIs with no type‑system support.
3. **Hybrid** — Add `memory` to the type system for declaration/validation but defer the runtime implementation (eventd, daemon) to a later cycle.

**Recommendation**
**Option 1 (first‑class primitive).** The type system (0011) is designed to be extended with new domain types that obey structural typing and the closed constraint set. Adding `memory` requires no new evaluation or side‑effects during validation (0011 §6.2, §6.4). Lowering is a pure projection of the typed graph (0012); a `memory.store` emitter would produce an inspectable artifact referencing a yet‑to‑be‑implemented daemon without violating *validate before generating*. The grammar change is a single production addition, and the checker change is a new case in the conformance fold (0011 §1.1). The concrete schema is proposed in `docs/language/0014-memory-primitive.md`; finalising it is part of implementation.

**Risks**
- **Grammar and checker surface** — A new top‑level kind requires a grammar production, a built‑in schema entry in `vaked/schema/parallel-types.md`, and a checker case. The risk is bounded because no new constraint types or evaluation are introduced (0011 §3 closed set, §6.2).
- **“Dead artifact”** — The artifact will reference a memoryd daemon that does not yet exist. This is acceptable: the runtime belongs to the daemon layer (0011 Scope); the artifact remains valid and inspectable.
- **Constraint fit** — If the memory schema eventually requires a new refinement beyond the closed set, the design must stop and propose a language change per 0011 §6.2. The schema should be designed to use only the existing refinements.

**Next actions**
1. Open a PR to add the `memory` kind to `vaked/grammar/vaked-v0-plus.ebnf` (top‑level production) with a placeholder schema block, using the fields proposed in `docs/language/0014-memory-primitive.md`.
2. Update the built‑in schema catalog `vaked/schema/parallel-types.md` to register the `memory` schema.
3. Extend the checker’s elaboration and conformance stages (0011 §1.1, §6.1) to handle the new kind with the standard record‑conformance logic.
4. Extend the lowering pass (0012) with a `memory.store` emitter that produces `gen/memory/<name>.json` as a pure projection; no runtime integration is needed.
5. Create an issue tracking the memoryd runtime daemon (eventd integration, recall API) marked post‑MVP and blocked on the lowering artifacts.

**Confidence**
**High.** Adding a domain type is a bounded extension to the existing 13 kinds (0011 §2.3) and follows the same structural

## 2026-06-14 — Decision #3: Decision / question: Decide whether to merge ‘memory’ into the type system as a 
- **Track:** graph-concept · **Models:** stage1 deepseek-v4-flash · stage2 deepseek-v4-pro
- **Context snapshot:** HEAD 5806db2, 7 open issues

**Decision / question:** Decide whether to merge ‘memory’ into the type system as a first‑class primitive or keep it as a runtime‑only concept.

**Options**
1. **First‑class primitive** — Add `memory` as a new top‑level kind in the grammar, built‑in schema catalog, type‑checker, and lowering pipeline. The schema uses only existing refinements (`nonempty`, `oneof`, `required`, `optional`) and the new `mem` capability domain preserves the partial‑order discipline of `docs/language/0011-type-system.md` §4. The checker validates memory declarations under the closed constraint set (`docs/language/0011-type-system.md` §3). Lowering emits pure projection artifacts per `docs/language/0012-lowering.md` §2.4. The runtime daemon (`memoryd`) is deferred, consistent with the staged adoption pattern of `docs/language/0013-mlir-topology-compilation.md`.
2. **Runtime‑only** — Keep the `memory` semantics entirely outside the language; agents interact with an opaque runtime service via streams/APIs, with no language‑level declaration, type‑checking, or lowering.
3. **Hybrid** — Accept `memory` in the type system only as a declaration container that stores schema/metadata, but defer the runtime integration (lowering emits configs referencing a future daemon). This is a subset of Option 1; the full first‑class path is straighter.

**Recommendation**
**Option 1 — first‑class primitive.** The `memory` shape described in `docs/language/0014-memory-primitive.md` fits as a new domain type in the type system defined by `docs/language/0011-type-system.md`. The schema uses only existing refinements (`docs/language/0011-type-system.md` §3). The checker can validate memory declarations with no new evaluation or side‑effects (`docs/language/0011-type-system.md` §6.2). Lowering can emit `gen/memory/<name>.json` as a pure graph projection (`docs/language/0012-lowering.md` §2.4), and the `memory.store` emitter has already been registered in the 0012 §3.4 registry. Making ‘memory’ first‑class gives agents a typed, capability‑checked declaration for their runtime memories, integrates with the `eventd` log (issue #18), and provides the foundation for eventual `memoryd` implementation without adding compiler‑time dependence on the runtime.

**Risks**
- **Dead artifact until runtime exists** — The `gen/memory/<name>.json` artifacts will reference a `memoryd` daemon that does not yet exist. This is acceptable because the artifact is still inspectable and the daemon is explicitly deferred; the same pattern is used for the pending `workflow.spec` emitter (issue #27).
- **Grammar and checker surface** — Adding a new top‑level kind requires a production in `vaked/grammar/vaked-v0-plus.ebnf`, a schema entry in `vaked/schema/parallel-types.md`, and a new case in the elaboration/conformance stages. The risk is bounded because no new constraint types or evaluation are introduced; the closed constraint set (`docs/language/0011-type-system.md` §3) still covers memory’s fields.
- **Capability domain naming collision** — The natural domain name `memory` would collide with a `schema memory` declaration in the LPG’s kind‑agnostic ids (issue #25). Using the domain name `mem` avoids the collision but introduces an inconsistency between the kind name `memory` and its capability domain `mem`. This is a documentation concern.
- **Scope creep into runtime state** — The `memory` primitive introduces runtime‑appended mutable state. The design explicitly separates declaration (checked at compiler time) from runtime effects (`docs/language/0014-memory-primitive.md` §Semantics), preserving the “validate before generating” invariant. This boundary must be enforced strictly as the runtime implementation evolves.

**Next actions**
1. **Open PR to add `memory` to the grammar and schema**  
   - Add the `memory` production to `vaked/grammar/vaked-v0-plus.ebnf` (top‑level kind) using the field set from `docs/language/0014-memory-primitive.md`.  
   - Register the `memory` schema in `vaked/schema/parallel-types.md`, including the `mem` capability domain with order `none < recall < append < admin`.
2. **Extend the checker**  
   - In the elaboration stage (`docs/language/0011-type-system.md` §6.1), add a case for `memory` nodes that applies standard record conformance (same pattern as `index`, `catalog`, etc.).  
   - Validate the `source` field’s `nonempty` constraint, the `scope` `oneof`, and the capability‑flow for the `mem` domain.
3. **Implement the `memory.store` lowering emitter**  
   - Existing registry entry (`docs/language/0012-lowering.md` §3.4) lists `memory.store`; implement the emitter that projects each `memory` node into `gen/memory/<name>.json` (pure structural mapping per 0012 §2.4).  
   - Emit the `gen/eventd.json` log‑contract artifact whenever a runtime declares any `memory` or `workflow`.
4. **Tracking issue for the runtime daemon**  
   - Create an issue (linked to #24) to design and implement `memoryd` — the mining daemon that consumes source streams, appends to `eventd`, and serves recall queries. Mark it as post‑MVP and note that lowering artifacts already define the contract.

**Confidence:** High — The type system’s extensibility with new domain types is proven (`docs/language/0011-type-system.md` §2.3 lists 13 kinds; adding a 14th is a bounded change). The design note (`docs/language/0014-memory-primitive.md`) provides a concrete, constraint‑compatible schema, and the lowering interface is already defined in 0012’s emitter registry. The only deferred work is the runtime daemon, which does not block language integration.

