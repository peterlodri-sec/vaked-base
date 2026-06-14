# 0011: The Vaked Type System (Goal 2)

## Status

Normative. This note defines the Vaked type system — the *discipline*, *type
model*, *constraint set*, *capability taxonomy*, *generics*, and *checking
pipeline* that turn a parsed Vaked file into a validated, ready-to-lower typed
semantic graph. It is the specification for the **Goal 2** checker.

It is paired with two documents:

- **Surface syntax** — [`vaked/grammar/vaked-v0-plus.ebnf`](../../vaked/grammar/vaked-v0-plus.ebnf)
  (v0.3) fixes what is *writable*: `schema` field declarations with constraint
  refinements, and `capability` declarations. See
  [`vaked/grammar/README.md`](../../vaked/grammar/README.md).
- **Built-in catalog** — [`vaked/schema/parallel-types.md`](../../vaked/schema/parallel-types.md)
  is the normative built-in schema catalog (one schema per primitive kind) plus
  the built-in capability taxonomy. This note defines the *rules*; that catalog
  is the *data* the rules are applied to.

It realizes manifesto principles
([`0001-language-manifesto.md`](./0001-language-manifesto.md)) directly:
*Make capabilities explicit*, *Validate before generating*, *Explain
everything*, *Prefer structure over cleverness*, and *Keep evaluation
deterministic and side-effect-free*. The primitives it types are introduced in
[`0008-parallel-fibers-indexes-surfaces.md`](./0008-parallel-fibers-indexes-surfaces.md).

### Scope (what this is NOT)

To keep the mantra intact (*Vaked declares. Nix materializes. Zig enforces.
eBPF testifies.*), the type system is deliberately bounded:

- **No lowering / codegen.** Producing `flake.nix`, Zig configs, eBPF manifests,
  etc. is **Goal 3**. This note stops at "validated graph, ready to lower."
- **No runtime enforcement.** Capability *attenuation* is checked at eval-time
  (POLA as a typing rule). Runtime membranes, revocation, and dynamic
  capability passing are the daemons' job (OTP/Zig/eBPF), explicitly **out**.
- **No general inference.** Checking is structural and local. There is no
  Hindley–Milner-style unification beyond binding the explicit generic
  parameters described in §5.
- **No expression/predicate language.** The constraint set (§3) is **closed**.
  Adding a user-defined predicate function would make checking Turing-equivalent
  and break totality; it is forbidden by design (see §6.2).

---

## 1. Discipline: structural typing + schema contracts

Vaked is **structurally typed**: a value's type is determined by its shape
(scalars, lists, records, refs), never by a nominal declaration. There is no
subclassing and no nominal record identity.

On top of structural typing, every **kind** (`runtime`, `index`, `fiber`,
`capability`, …) carries a **schema**: a record type plus a set of field
constraints. A schema is itself a value of the structural type "record type with
constraints," and users declare new schemas with the `schema` kind. Built-in
kinds have built-in schemas (the catalog in `parallel-types.md`); user `schema`
declarations register additional named schemas that other declarations may
reference (e.g. an `index`'s `schema = schema.zigbeeOta`).

A schema `S` has:

- a finite set of **fields**, each with a name, a **type** (§2), and a
  (possibly empty) set of **refinements** (§3);
- an **openness** flag: *closed* (default) or *open* (declared with a bare
  `open` statement in the schema body).

### 1.1 Conformance

A block (record) `b` **conforms** to schema `S`, written `b ⊨ S`, iff **all** of:

1. **Required fields present.** Every field of `S` marked `required` (the
   default — see §3.3) has a binding in `b`.
2. **Field well-typedness.** For every field `f : T` of `S` that is bound in
   `b`, the bound value `b.f` matches `T` structurally (§2.4).
3. **Optionals optional.** A field marked `optional` (or carrying a `default`)
   may be absent; if present it must satisfy 2 and 4.
4. **Constraints hold.** For every field bound in `b`, every refinement on that
   field holds for `b.f` (§3).
5. **Unknown fields.** If `S` is *closed*, every field name in `b` must be a
   declared field of `S` (unknown field ⇒ reject). If `S` is *open*, unknown
   fields are admitted and carry the *structural* type inferred from their
   value, but are otherwise unconstrained.

Conformance is **decidable** and **monotone**: it inspects a finite record
against a finite schema with a finite, total constraint set. No fixpoint, no
backtracking search.

### 1.2 Defaults and elaboration

A field with `default = v` that is absent in `b` is *elaborated* to carry value
`v` in the typed graph (so downstream lowering sees a total record). `default`
does not relax typing: `v` must itself match the field type and satisfy the
field's other refinements, and this is checked once, on the schema, at load
(§3.6). Defaulting is a pure substitution; it introduces no evaluation.

---

## 2. Type model

### 2.1 Scalars

The base scalar types are:

| Type | Values | Literal form (grammar) |
|------|--------|------------------------|
| `String` | UTF-8 text | `string` (`"…"`, with `${ref}` interpolation) |
| `Int` | arbitrary-precision integer | `number` with no `.` |
| `Float` | IEEE-754 double | `number` with a `.` |
| `Bool` | `true` / `false` | `bool` |
| `Path` | filesystem-relative path | `path` (`./…`) **or** a `String` literal used positionally where a path is expected (see §2.5) |
| `Duration` | time span, normalized to nanoseconds | `duration` (`24h`, `120ms`) **or** a `String` like `"24h"` |
| `Bytes` | byte size, normalized to bytes | `bytes` (`2GB`) **or** a `String` like `"2GB"` |
| `Null` | the single value `null` | `"null"` |

`Int` and `Float` are distinct; an `Int` literal does **not** match `Float` and
vice-versa, except that a field typed `Float` accepts an `Int` literal by the
widening rule in §2.4 (Int ◁ Float). `Duration` and `Bytes` have canonical
normalized representations (ns and bytes); two literals are equal iff their
normalized values are equal (`1000ms = 1s`).

### 2.2 Composite types

- **`List<T>`** — a homogeneous, ordered sequence; every element matches `T`.
  The empty list `[]` matches `List<T>` for every `T`. (`nonempty`, §3.4,
  rejects `[]` where required.)
- **Structural records** — `{ f1 : T1, …, fn : Tn }`, matched structurally per
  §1.1. Schemas are the *named, constrained* form of record types; bare
  structural records (e.g. a `policy { … }` body) are matched against the
  corresponding nested schema (§ catalog).
- **Unions** — `A | B | …` (grammar `type = type_atom { "|" type_atom }`). A
  value matches a union iff it matches **at least one** arm. Union matching is
  by *trial*: the value is matched against each arm left-to-right; the first arm
  it matches wins (this is total — finite arms, each match decidable). Unions
  are **untagged** structurally but the checker records *which* arm matched for
  source-mapping and lowering.

### 2.3 Refs and domain types

- **Refs.** A `ref` (`stream.ebpfEvents`, `index.zigbeeFirmware`,
  `catalog.jsonl`) denotes another declaration or a built-in emitter/target.
  Its type is the type of the referent: a reference to a `stream X` has type
  `Stream<T>` for that stream's event type `T`; a reference to an `index X` has
  type `Index<T>`; etc. Refs to *built-in targets* (`nix.derivation`,
  `catalog.jsonl`, `crabcc.markdown`, `otp`, `raylib`) resolve to built-in
  values with built-in types (`ArtifactTarget`, `Normalizer`, `Supervisor`,
  `SurfaceMode`, …) enumerated in the catalog.
- **Domain types.** The primitive kinds are the domain types of the system.
  Their parameterized signatures (the *type-level* view, distinct from the
  block schema in `parallel-types.md`) are:

  ```text
  Index<T>          Catalog<T>        Stream<T>
  Fiber<I, O>       Surface           Mesh<Node, Edge>
  Device            MediaPipeline     ParallelGroup
  Engine            Capability        Schema<T>
  ```

  These are the same names used in `parallel-types.md`. `Surface`, `Device`,
  `MediaPipeline`, `ParallelGroup`, `Engine`, `Capability` are non-generic.
  `Device` represents a named hardware or protocol endpoint (e.g. Zigbee node,
  USB peripheral) declared in the capability graph; `MediaPipeline` represents
  a named composition of media-processing stages. Both have schemas in
  `parallel-types.md` and are accepted by the checker; their lowering targets
  are not yet specified (see `0012-lowering.md` §5.4).

### 2.4 Structural matching relation (`◁`)

`v ◁ T` ("value `v` matches type `T`") is defined inductively and totally:

- **Scalar.** `v ◁ Scalar` iff `v` is a literal of that scalar (with `Int ◁
  Float` widening, and the string-form acceptances for `Path`/`Duration`/`Bytes`
  in §2.1).
- **List.** `v ◁ List<T>` iff `v` is a list and `∀ e ∈ v. e ◁ T`.
- **Record/Schema.** `v ◁ S` iff `v ⊨ S` (§1.1).
- **Union.** `v ◁ (A | B)` iff `v ◁ A ∨ v ◁ B`.
- **Ref.** A ref `r` *matches* `T` iff `typeof(referent(r)) ◁: T`, where `◁:` is
  the **generic-compatibility** relation of §5 (e.g. a `ref` to `Index<Doc>`
  matches the parameter type `Index<T>` by binding `T := Doc`).
- **Null.** `null ◁ Null`, and `null ◁ T` only if `T` is `Null` or a union arm
  is `Null`. (There is no implicit nullability.)

`◁` is structural, finite, and decidable. No coercion happens except the two
explicit widenings (Int◁Float; scalar string-forms). The checker never executes
the value to decide a match.

### 2.5 Where `Path` strings come from

Several built-ins are written as positional calls whose argument is a quoted
string used as a path (`sqlite("./var/firmware.db")`, `raw.github("repo",
"file")`). The catalog gives such built-ins signatures (e.g.
`sqlite(p : Path) -> ArtifactTarget`) and §2.1 lets a `String` literal match
`Path` positionally. This is the one place a `String` is accepted for `Path`; it
keeps the existing examples valid without a general `String <: Path` subtyping
rule.

---

## 3. The constraint set (CLOSED)

Refinements constrain a field beyond its type. The set is **closed**: exactly
the forms below, no more. Each is **total** (decidable in finite time with no
side effects) and **monotone** (adding a refinement can only shrink the set of
conforming values). Surface syntax is the grammar's `refinement` production.

> **Why closed.** A user-extensible predicate language would let a constraint
> embed arbitrary computation, making conformance undecidable in general and
> defeating *Validate before generating*. Vaked therefore fixes the set. If a
> real schema appears to need a predicate the set cannot express, that is a
> **language-design event** — see §6.2 — not something the author works around.

For each refinement, "applies to" lists the field types it is *well-formed* on;
applying it to any other field type is a **schema error** caught at load (§3.6).

### 3.1 `oneof [ v1, …, vn ]`

The field value must be **equal** to one of the listed literals. Applies to:
any scalar type, and `List<Scalar>` (where it means "the whole list equals one
of the listed lists"). Each `vi` must itself match the field type (checked at
load). Equality is the normalized literal equality of §2.1. `n ≥ 1` required.

### 3.2 Ranges: `>= n`, `<= n`, `> n`, `< n`, `in lo .. hi`

Numeric bounds. Applies to: `Int`, `Float`, `Duration`, `Bytes` (the latter two
compared on their normalized values; `n` may be written as the corresponding
literal, e.g. `>= 0`, `in 0 .. 255`, `<= 4GB` *(when the field is `Bytes`)*).
`in lo .. hi` is the closed interval `lo ≤ v ≤ hi` and requires `lo ≤ hi`
(checked at load). Multiple bounds on one field conjoin (`>= 0` and `<= 255` is
the same constraint as `in 0 .. 255`).

### 3.3 `required` / `optional`

Presence. **`required` is the default**: a field with neither marker and no
`default` is required. `optional` makes absence legal. `required` and `optional`
on the same field is a schema error. A field with a `default` is implicitly
optional at the source level (it may be omitted) but total in the elaborated
graph (§1.2); writing `required default = v` is a schema error (contradiction).

### 3.4 `nonempty`

Applies to: `String`, `List<T>`, `Bytes`. Means length/size `> 0` (a `String`
with no characters, an empty `List`, or zero `Bytes` is rejected). On any other
type it is a schema error.

### 3.5 `matches /regex/`

Applies to: `String` (and `Path`, treating the path textually). The value must
be fully matched by the regex. The regex dialect is **fixed and bounded** to
preserve totality and determinism:

- Anchored implicitly at both ends (the whole value must match; `^…$` may be
  written and are redundant).
- Allowed: literal characters, character classes `[...]`, `.`, alternation `|`,
  grouping `(...)`, and the quantifiers `?`, `*`, `+`, `{m}`, `{m,n}`.
- **Forbidden**: backreferences (`\1`), lookaround (`(?=…)`, `(?<…)`), and any
  feature whose matcher is not linear-time. The checker rejects a regex using a
  forbidden feature as a **schema error** at load.

This dialect is a regular language ⇒ matching is `O(|regex| · |value|)`, total,
and deterministic. The regex is data, not a Vaked expression (it never sees a
`ref` or interpolation).

### 3.6 `default = v`

Supplies a value when the field is absent (§1.2). `v` is a literal/value
expression with **no refs and no interpolation** (so defaulting needs no
resolution and stays pure). At **load** the checker verifies `v ◁ fieldType`
and that `v` satisfies every other refinement on the field; a bad default is a
schema error, surfaced against the schema, before any block is checked.

### 3.7 Refinement well-formedness summary

| Refinement | Well-formed on | Load-time checks |
|------------|----------------|------------------|
| `oneof [..]` | scalar, `List<Scalar>` | each elem `◁` field type; `n ≥ 1` |
| `>= <= > <` | `Int Float Duration Bytes` | bound literal `◁` field type |
| `in lo..hi` | `Int Float Duration Bytes` | `lo ≤ hi`; both `◁` field type |
| `required` | any | not combined with `optional`/`default` |
| `optional` | any | not combined with `required` |
| `nonempty` | `String List Bytes` | — |
| `matches /re/` | `String Path` | regex in bounded dialect |
| `default = v` | any | `v ◁` field type ∧ `v` sat. other refinements; no refs |

Load-time ("schema") errors are reported against the schema declaration; per-
block conformance errors (§1.1) are reported against the offending block. Both
are source-mapped (§6.5).

---

## 4. Capabilities: typed taxonomy + attenuation

### 4.1 Capability values and domains

A **capability** is a value of type `Capability`, written `domain.grant` (the
existing `ref` form — e.g. `fs.repo_rw`, `network.none`, `mcp.github_read`).
`domain` is a capability **domain**; `grant` is one of that domain's declared
grants.

A domain is declared with the `capability` kind:

```vaked
capability fs {
  grant none repo_ro repo_rw
  order none < repo_ro < repo_rw
}
```

The decl `name` is the domain. The body declares the domain's grants
(`grant_decl`, one or more) and exactly one **attenuation order** (`order_decl`).
The built-in domains (`fs`, `network`, `mcp`, `ebpf`, `process`) are defined in
`parallel-types.md`; users may declare further domains the same way.

### 4.2 The attenuation order (a partial order)

For each domain, `order` declares a relation over its grants by listing one or
more **chains**: `order none < repo_ro < repo_rw` (chains separated by `;`).
Read `a < b` as **"a is weaker than b"** — `a` is the more attenuated (lesser)
capability.

Let `≤` be the reflexive–transitive closure of the declared `<` relation within
a domain. The checker requires `≤` to be a **partial order**, i.e.:

- **Reflexive** — `a ≤ a` (by construction of the closure).
- **Transitive** — `a ≤ b ∧ b ≤ c ⇒ a ≤ c` (by construction of the closure).
- **Antisymmetric** — `a ≤ b ∧ b ≤ a ⇒ a = b`. Equivalently, the declared `<`
  relation is **acyclic**. A cycle (e.g. `order a < b ; b < a`) is a schema
  error reported at load.

Grants in different domains are **incomparable** (`fs.repo_ro` and
`network.loopback` have no order relation). The order is therefore a partial
order over each domain's grants, and the system-wide capability order is the
disjoint union of the per-domain partial orders. Each domain has a least element
by convention (`none`, or the documented bottom in the catalog), but a least
element is not required for the relation to be a valid partial order.

Well-formedness checked at load:

1. Every grant named in `order` is declared by a `grant` statement (no
   dangling grant).
2. The declared `<` relation is acyclic (antisymmetry).
3. Exactly one `order` statement per domain.

### 4.3 The grant-set of a node / fiber

A node, fiber, or other principal may be **granted** a set of capabilities
(e.g. a mesh node's `capabilities = [fs.repo_rw, mcp.github_read]`). It may
**use** capabilities (the capabilities its referenced engines/streams/effects
require). The checker computes, for each principal:

- `granted(p)` — the capability set written on `p`.
- `used(p)` — the capabilities `p` exercises, gathered structurally from its
  body (engine requirements, stream sources, surface inputs, etc., as the
  catalog specifies which fields contribute).

**Use check (POLA, local):** for every principal `p`,

```text
used(p) ⊑ granted(p)
```

where `c ⊑ G` ("`c` is authorized by grant-set `G`") holds iff there exists
`g ∈ G` in the **same domain** as `c` with `c ≤ g` (a stronger held grant
authorizes a weaker use). If `p` uses a capability in a domain it holds nothing
in, or uses a grant strictly above everything it holds, that is a
**capability-use error**.

### 4.4 Delegation / routing only attenuates

Edges in a `mesh` (and any sender→receiver relation the catalog marks as a
*delegation*) move authority from a sender `s` to a receiver `r`. The rule is
**monotone attenuation**: a receiver's capabilities must be `≤` the sender's,
per domain.

Formally, for a delegating edge `s -> r`, for every grant `cr ∈ granted(r)`:

```text
∃ cs ∈ granted(s) :  same_domain(cs, cr) ∧ cr ≤ cs
```

i.e. **`granted(r) ⊑ granted(s)`** under §4.3's `⊑`, lifted to sets. The
receiver may hold *less* authority (lower in the order) or *equal*, never more.
Delegating a capability the sender does not itself hold, or one strictly above
what the sender holds, is an **attenuation error**. This is POLA enforced as a
*typing rule*: authority only ever decreases along delegation paths.

### 4.5 Soundness of the POLA check

The check is sound w.r.t. the intended semantics — "no principal ends up able to
exercise authority that was never transitively granted to it from a strictly
greater holder" — because:

1. `≤` is a partial order (§4.2), so `⊑` is a well-defined preorder on grant
   sets (reflexive: `G ⊑ G`; transitive: `G1 ⊑ G2 ∧ G2 ⊑ G3 ⇒ G1 ⊑ G3`, since
   `≤` is transitive within each domain).
2. The use check (§4.3) guarantees every *exercised* capability is dominated by
   a *held* one.
3. The delegation check (§4.4) guarantees `granted` only decreases along edges:
   if `s ->* r` (a delegation path), then `granted(r) ⊑ granted(s)` by
   transitivity of `⊑`.

Composing 2 and 3: any capability a principal can exercise is `≤` some grant it
holds, and any grant it holds is `≤` some grant held by every upstream
delegator. Hence authority along any path is non-increasing and bounded by the
root grant — the POLA invariant. (Cycles in the *mesh* are allowed structurally;
because `⊑` along a cycle forces all grant-sets on the cycle to be `⊑`-equal,
the check degenerates to equality on cycles, which is sound and still total.)

Runtime *enforcement* of this invariant (membranes, revocation) is out of scope
(§Scope); the type system certifies the static authority assignment is
POLA-consistent before lowering.

---

## 5. Generics

`T` (and `I`, `O`, `Node`, `Edge`) are **type parameters** that thread a content
or message type through the domain types:

- `Index<T>` / `Catalog<T>` — `T` is the item schema of the indexed/catalogued
  content.
- `Stream<T>` — `T` is the event type (`Event.Ebpf`, `Media.Frame`, …).
- `Fiber<I, O>` — `I` the input type, `O` the output type.
- `Mesh<Node, Edge>` — `Node` the node record type, `Edge` the edge record type.
- `Schema<T>` — a schema describing values of type `T`.

### 5.1 Consistency (flow) checking

Generic parameters are bound by **structural unification at the point of use**,
with no inference beyond it:

- When a value of type `Index<Doc>` flows into a position typed `Index<T>`, `T`
  is bound to `Doc`. A second use that would bind `T` to a different type is a
  **generic-consistency error**.
- `catalog C { from = index.I }` requires `C : Catalog<T>` and `index.I :
  Index<T>` for the **same** `T`. If the catalog declares its own item type
  (via `schema`) it must equal the index's `T`.
- `fiber F { input = stream.S; output = … }` requires the stream's `T` to match
  `F`'s `I`, and `F`'s `O` to match the declared `output` target's accepted
  type.

`◁:` (generic-compatibility, used in §2.4) is: `C1<a..> ◁: C2<b..>` iff `C1 =
C2`, same arity, and each `ai ◁: bi` where a parameter position unifies
(binds a free parameter) or matches structurally (both ground). This is
first-order unification over a **finite** set of explicitly-written parameters
— it terminates and is deterministic.

### 5.2 Bounded user generics; no higher-kinded types

A user declaration may be generic via its `signature`
(`engine zigDaemon(name : String, src : Path) -> Engine`; or
`schema Doc(item : Schema<T>) -> Schema<T>`). Parameters are **bounded** by
their written types and may be constrained by a kind, but:

- **No higher-kinded parameters** — a parameter may not itself take type
  arguments (`F<_>` is not expressible). The grammar's `type_atom` only allows
  `qualname [ "<" type {…} ">" ]`, i.e. application of a *named* constructor to
  types, never a *variable* constructor. This keeps unification first-order and
  decidable.
- **No recursion through type parameters** that would create an infinite type;
  the elaboration graph (§6.1) is finite and acyclic in its type-formation
  edges, checked as part of termination (§6.4).

---

## 6. The checking pipeline (eval-time, total + deterministic)

### 6.1 Stages

Checking a Vaked file runs four stages. Each is a pure function of its input;
together they map source text to either a **validated typed semantic graph** or
a non-empty, source-mapped **diagnostic set**.

1. **Parse.** Source → AST per the v0.3 grammar. Lexical/syntactic errors are
   reported here with byte/line spans. (Parsing is the grammar's job; this note
   assumes a successful parse.)
2. **Resolve.** Resolve `use` imports (acyclically — an import cycle is an
   error) and every `ref`/`qualname` to a declaration or a built-in. Produces a
   *resolved AST* in which every name points at exactly one binding. Unresolved
   ref ⇒ error; ambiguous binding ⇒ error.
3. **Elaborate.** Build the **typed semantic graph**: one node per declaration,
   each typed by its kind-schema (built-in from `parallel-types.md`, or a user
   `schema`). Field values become typed sub-nodes; refs become typed edges;
   defaults are inserted (§1.2); union arms are selected (§2.2); generic
   parameters are bound (§5). The graph's nodes are the declarations; its edges
   are refs (data flow) and delegations (authority flow).
4. **Check.** Over the typed graph, run, in order:
   a. **Schema well-formedness** — every schema (built-in and user) is
      well-formed: refinements applied to legal field types, valid defaults,
      valid `oneof`/range/regex (§3.6); every capability order is a partial
      order (§4.2).
   b. **Conformance** — every declaration block conforms to its schema (§1.1),
      including nested records.
   c. **Constraints** — every field refinement holds (§3).
   d. **Generics consistency** — all parameter bindings are consistent (§5.1).
   e. **Capability flow** — the use check (§4.3) and the attenuation check
      (§4.4) pass for every principal and delegation edge.

   The check stage is **collecting**, not fail-fast: it accumulates *all*
   diagnostics (subject to §6.5) so one run reports every problem.

A file is **valid** iff stages 1–4 produce no diagnostics. A valid file's typed
semantic graph is the hand-off to **Goal 3** lowering. *Validation strictly
precedes generation* (manifesto: *Validate before generating*) — nothing is
lowered from an invalid graph.

### 6.2 Closedness as a checker invariant

Because the constraint set (§3) and the capability vocabulary (domains/grants,
§4) are the *only* extension points, and neither admits arbitrary computation,
the checker has no interpreter for user code. There is no stage at which Vaked
*runs* a value. If a future requirement seems to need a predicate the closed set
cannot express (e.g. "field B must be ≥ field A"), the correct response is to
**stop and propose a language change** (a new closed refinement with defined,
total semantics), not to add an escape hatch. This is the boundary that keeps §6
total.

### 6.3 Determinism

Every stage is a deterministic function of (source files, built-in catalog):

- Parsing is deterministic (the grammar's alternation is ordered — first match
  wins — and the soft-keyword rule, grammar note 8, is unambiguous).
- Resolution depends only on the declaration set and import graph; name lookup
  is by a fixed scoping rule (lexical, then enclosing, then imported, then
  built-in), so it is order-independent and reproducible.
- Elaboration, conformance, constraints, generics, and capability checks are all
  structural folds over finite data with no clocks, no randomness, no filesystem
  reads beyond the already-resolved imports, no network. Diagnostic *ordering* is
  fixed (by source position, then a stable stage/rule key), so even the error
  output is byte-reproducible.

Hence: same inputs ⇒ identical typed graph and identical diagnostics, on any
host. This is the eval-time half of *Keep evaluation deterministic and
side-effect-free*; the run-time half belongs to the generated artifacts.

### 6.4 Totality (termination) argument

The checker terminates on every input:

1. **Finite declaration graph.** A file is a finite sequence of declarations;
   imports are resolved over an **acyclic** import graph (cycle ⇒ error in stage
   2), so the total declaration set is finite. Elaboration produces one node per
   declaration plus finitely many sub-nodes (one per field/element, and the AST
   is finite) ⇒ a finite graph.
2. **No general recursion.** There is no value-level recursion or evaluation
   (§6.2). Type formation is first-order (§5.2: no higher-kinded params), and the
   type-formation edges are checked acyclic, so generic binding/unification is
   over a finite, acyclic structure and terminates.
3. **Bounded constraints.** Each refinement is decided in time bounded by the
   size of the value (and, for `matches`, `|regex|·|value|` — linear, by the
   bounded regular dialect §3.5). The closed set has no recursive or
   fixpoint-defined constraint.
4. **Bounded capability checks.** `≤` is the transitive closure of a finite
   acyclic `<` (computable once per domain); the use/attenuation checks visit
   each principal and each delegation edge a constant number of times.

Each stage is therefore a terminating fold over finite data with bounded
per-element work. Composition of terminating stages terminates. ∎

### 6.5 Errors: explainable + source-mapped

Every diagnostic is a structured, explainable record:

```text
Diagnostic {
  severity : error | warning
  code     : stable identifier   # e.g. E-CONFORM-UNKNOWN-FIELD,
                                  #      E-CONSTRAINT-RANGE,
                                  #      E-CAP-ATTENUATION,
                                  #      E-GENERIC-INCONSISTENT,
                                  #      E-SCHEMA-BAD-DEFAULT,
                                  #      E-CAP-ORDER-CYCLE
  span     : { file, byteStart, byteEnd, line, col }   # source map
  message  : human-readable, names the schema/field/grant involved
  expected : the rule that was violated (type, refinement, or order edge)
  got      : the offending value or capability (rendered from the AST)
  related  : [ span … ]          # e.g. the schema decl, the granting node,
                                  #      the conflicting prior generic binding
  fix?     : optional suggested edit (e.g. "add field X", "weaken to fs.repo_ro")
}
```

Source-mapping is preserved end-to-end (manifesto: *Explain everything*,
*Source-mapped & explainable*): elaboration tags every typed node and edge with
the span of the AST node it came from, so a check failure several stages
downstream still points at the exact source token. Because elaboration keeps
names and structure traceable (no anonymization), `vaked explain <kind> <name>`
can render the typed node, its schema, its resolved refs, and its capability
sets directly from the graph.

Representative diagnostics:

- *Unknown field in closed schema.* `E-CONFORM-UNKNOWN-FIELD` at the field's
  span; `related` → the schema decl; `fix` → "declare the field or mark the
  schema `open`."
- *Range violation.* `E-CONSTRAINT-RANGE`: `expected` = `in 0 .. 255`, `got` =
  `300`, span on the literal.
- *Over-grant on delegation.* `E-CAP-ATTENUATION`: receiver holds `fs.repo_rw`
  but sender holds only `fs.repo_ro`; spans on both the edge and the two grant
  sites; `fix` → "weaken receiver to `fs.repo_ro` or raise sender."
- *Generic inconsistency.* `E-GENERIC-INCONSISTENT`: `catalog.from` is
  `Index<Doc>` but the catalog's item schema is `Firmware`; `related` → both
  binding sites.

---

## 7. Worked example (end-to-end)

```vaked
schema zigbeeOta {
  field manufacturer : String { required nonempty }
  field image_type   : Int    { required in 0 .. 255 }
  field file_version : Int     { required >= 0 }
}

capability fs {
  grant none repo_ro repo_rw
  order none < repo_ro < repo_rw
}

mesh agentfield {
  node codex   { role = "worker"   capabilities = [fs.repo_rw] }
  node redteam { role = "reviewer" capabilities = [fs.repo_ro] }
  codex -> redteam            # OK: repo_ro ≤ repo_rw (attenuation)
}
```

- The `schema` is well-formed: `nonempty` on `String`, `in 0..255`/`>= 0` on
  `Int` (§3.7). An `index` whose `schema = schema.zigbeeOta` then has its rows
  checked field-by-field (§1.1).
- The `capability fs` order `none < repo_ro < repo_rw` is acyclic ⇒ a partial
  order (§4.2). (This is a *minimal* `fs` for the example; the full built-in
  `fs` domain — `none repo_ro repo_rw host_ro host_rw` with a branching order —
  is in `parallel-types.md`. The checking rules are identical regardless.)
- The edge `codex -> redteam` delegates from a `repo_rw` holder to a `repo_ro`
  holder; `repo_ro ≤ repo_rw`, so attenuation holds (§4.4). Reversing it
  (`redteam -> codex`) would raise `E-CAP-ATTENUATION`.

Runnable forms of this example, plus a deliberately-rejected counterpart, are in
[`vaked/examples/types/`](../../vaked/examples/types/).

---

## 8. Cross-references

- Grammar (surface syntax, v0.3): [`vaked/grammar/vaked-v0-plus.ebnf`](../../vaked/grammar/vaked-v0-plus.ebnf),
  [`vaked/grammar/README.md`](../../vaked/grammar/README.md)
- Built-in schema + capability catalog: [`vaked/schema/parallel-types.md`](../../vaked/schema/parallel-types.md)
- Primitives & graph model: [`0008-parallel-fibers-indexes-surfaces.md`](./0008-parallel-fibers-indexes-surfaces.md)
- Principles: [`0001-language-manifesto.md`](./0001-language-manifesto.md)
- Type-layer examples: [`vaked/examples/types/`](../../vaked/examples/types/)
