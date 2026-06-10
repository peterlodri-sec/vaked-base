# Vaked type system (Goal 2) — design

- **Date:** 2026-06-10
- **Status:** Approved (brainstorm) → implementing via subagent-driven execution
- **Goal 2** of the language session: turn `vaked/schema/parallel-types.md` into a real typed-semantic-graph spec — what types exist, the per-primitive schemas, capability typing, generics, and the eval/checking rules. (Goal 1 = grammar v0.2, done. Goal 3 = lowering.)

## Decisions

1. **Discipline — structural + schema contracts.** Values are structurally typed; each `kind` has a schema (record-type-with-constraints) its block must satisfy; users declare their own via the first-class `schema` kind. Conformance = required fields present+typed, optionals optional, unknown fields rejected unless the schema is `open`, and all constraints hold.
2. **Constraints — bounded predicate set (closed).** Per field: `oneof […]`, ranges (`>=`,`<=`,`in`), `required`/`optional`, `nonempty`, `matches /re/`, `default =`. No user-defined functions → total/deterministic.
3. **Capabilities — typed taxonomy + attenuation order.** A `Capability` is `domain.grant` from a taxonomy; each domain declares grants + an attenuation partial order (`none < repo_ro < repo_rw`). Checker verifies: refs valid; a node/fiber uses ⊆ granted; routing/delegation only attenuates (POLA at type-time). Runtime membranes/revocation stay the daemons'.
4. **Generics.** `T` parameterizes content/message types — Index/Catalog over item-schema, `Stream<T>` over event type, `Fiber<I,O>` over in/out, `Mesh<Node,Edge>` over node/edge records. Checked for consistency (`catalog.from : Index<T>` ⇒ same `T`). Bounded user-generics (no higher-kinded).
5. **Checking pipeline (at eval — total + deterministic).** parse → resolve imports/refs → elaborate the **typed semantic graph** (each node typed by its kind-schema) → check (conformance + constraints + capability attenuation/flow) → valid ⇒ ready to lower (Goal 3). *Validate before generating.* Terminates (finite graph, bounded constraints, no general recursion); side-effect-free; errors explainable + source-mapped.

**Ratified defaults:** (a) grammar bump **v0.2 → v0.3** to carry schema constraint-refinements + a `capability` declaration form; (b) generics = built-ins + bounded user-generics; (c) docs = new `docs/language/0011-type-system.md` + rewrite `vaked/schema/parallel-types.md` into the normative type spec + built-in-schema catalog.

## Types (model)

Scalars: `String, Int, Float, Bool, Path, Duration, Bytes, Null`. Compound: `List<T>`, structural `Record` (named typed fields), unions `A | B`, refs. Domain types: `Index<T>, Catalog<T>, Stream<T>, Fiber<I,O>, Surface, Mesh<Node,Edge>, Device, MediaPipeline, ParallelGroup`. Structural matching (a record satisfies a schema by shape).

## Implementation tasks (for subagent-driven execution)

- **T1 — Type-system spec.** `docs/language/0011-type-system.md`: the normative spec — the 5 decisions above as full sections (types & structural matching; schemas/contracts + conformance rules; the closed constraint set + semantics; the capability taxonomy + attenuation order + the POLA/flow check; generics; the checking pipeline + totality/determinism argument; error/source-map model). Cross-link the grammar + parallel-types.
- **T2 — Built-in schemas + capability taxonomy.** Rewrite `vaked/schema/parallel-types.md` into the normative catalog: a precise field schema (with constraints) for each primitive (`index, catalog, stream, fiber, surface, mesh, device, mediaPipeline, parallel`, plus `runtime`/`engine` as used by the examples), AND the built-in capability taxonomy (domains `fs, network, mcp, ebpf, process, …` with grants + attenuation orders). Must be consistent with the v0.2 examples (every example's blocks conform to these schemas) — if an example violates a schema, fix the SCHEMA to match reality or note the discrepancy.
- **T3 — Grammar v0.3.** Extend `vaked/grammar/vaked-v0-plus.ebnf` → v0.3: (i) a schema field **constraint-refinement** form (e.g. `field : Type oneof […]` / `Type >= n` / `nonempty` / `matches /re/`), (ii) a `capability` declaration form (domain + grants + order). Keep self-contained (every nonterminal defined, no dead rules); **all existing v0.2 examples must still parse**. Bump the header to v0.3 and note the additions.
- **T4 — Examples.** Under `vaked/examples/types/`: a user-defined `schema` with constraints; a `capability` taxonomy + an attenuation use (a node delegating an attenuated cap); and a short note pairing one **conformant** vs one **rejected** block (to illustrate checking) — all derivable from grammar v0.3.

## Review criteria (per task / final)

Spec internal consistency (types ↔ schemas ↔ constraints ↔ capabilities ↔ checking pipeline agree). Grammar v0.3: build a parser and confirm **every** `.vaked` example (v0.2 primitives + the new type examples + operator-field + zig.vaked) still derives; self-contained. Capability attenuation is a well-defined partial order and the POLA/flow check is sound (delegation only attenuates). Constraints are a closed set (no general computation) and checking is argued total/deterministic. No scope creep into lowering (Goal 3) or runtime enforcement.

## Deferred

Lowering/codegen (Goal 3); runtime capability enforcement (daemons); full ocap membranes/revocation; heavy type inference (we check, not infer).
