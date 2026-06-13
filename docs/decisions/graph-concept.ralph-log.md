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

