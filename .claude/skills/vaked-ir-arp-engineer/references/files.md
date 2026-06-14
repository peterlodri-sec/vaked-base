# Files

## File: docs/language/references/parallel-reference-pack.md
````markdown
# Parallel Reference Pack

This reference pack captures projects that inspired the expanded Vaked language model.

## Native surface references

### raylib-zig

Use as inspiration for fast native operator visualization surfaces.

```vaked
surface operatorMap {
  mode = raylib
  fps = 60
  input = [stream.ebpfEvents, graph.workflow]
}
```

### zero-native

Use as inspiration for Zig-native desktop/mobile shells with web UI frontends.

```vaked
surface desktopShell {
  mode = zero-native
  frontend = "./ui"
  native = zig "operator-shell"
}
```

## Media references

### zigimg

Use as inspiration for native image/media artifact pipelines.

```vaked
mediaPipeline runMedia {
  source = artifacts.screenshots
  process = zigimg {
    formats = ["png", "webp"]
    strip_metadata = true
  }
}
```

## Mesh/device references

### Zigbee

Use Zigbee as a mental model for mesh topology, device capabilities, route recovery, and bounded node communication.

### zigpy

Use as a reference for Zigbee stack semantics and Python ecosystem integration.

### zigbee-OTA

Use as a reference for raw firmware indexes and manifest-driven catalogs.

```vaked
index zigbeeFirmware {
  source = raw.github("Koenkk/zigbee-OTA", "index.json")
  schema = schema.zigbeeOta
}
```

## Zig-native agent infra references

### nullclaw

Use as a signal that Zig-native AI assistant infrastructure is a live design space.

## Zig corpus references

### awesome-zig

Use as a broad corpus source for Zig package/project discovery.

### zig.guide

Use as a curated educational corpus source for Zig learning material.

```vaked
index zigCorpus {
  source = [
    github("Sobeston/zig.guide"),
    github("C-BJ/awesome-zig")
  ]

  normalize = crabcc.markdown
  emit = [catalog.jsonl, catalog.sqlite]
}
```
````

## File: docs/language/0001-language-manifesto.md
````markdown
# 0001: Vaked Language Manifesto

Vaked is a complement language above Nix, not a Nix replacement.

It declares high-level, typed capability graphs and compiles them into ordinary, inspectable artifacts.

## Principles

- Compile to boring artifacts.
- Make capabilities explicit.
- Prefer structure over cleverness.
- Support raw Nix escape hatches.
- Explain everything.
- Validate before generating.
- Preserve provenance.
- Keep evaluation deterministic and side-effect-free.
````

## File: docs/language/0009-kickoff-context-for-dedicated-session.md
````markdown
# 0009: Kickoff Context for Dedicated Language Session

## Goal

Start a dedicated session focused only on the Vaked language.

The runtime architecture, Zig daemon stack, eBPF enforcement, and agent system are context. The main work is now language shape, semantics, syntax, and compiler milestones.

## Current Vaked definition

Vaked is a typed, flake-native capability graph language for declaring reproducible agentic, native, mesh-aware, parallel systems.

It compiles to ordinary artifacts:

- `flake.nix`
- NixOS modules
- Zig daemon configs
- eBPF manifests
- MCP broker policy
- OTel config
- CrabCC indexes/catalogs
- generated docs
- surface launcher configs

## Must preserve

- Nix remains the substrate.
- Generated artifacts are inspectable.
- Evaluation is deterministic and side-effect-free.
- Capabilities are explicit.
- Raw Nix escape hatches exist.
- `vaked explain` is a first-class UX.
- The language does not become a general app language.

## New language primitives to evaluate

```text
index
catalog
stream
fiber
surface
mesh
device
mediaPipeline
parallel
```

## Dedicated session agenda

1. Restate the language identity in one paragraph.
2. Define the semantic graph types.
3. Decide which top-level declarations are v0, v0.1, later.
4. Refine the syntax family.
5. Define imports, merges, defaults, overrides, and raw Nix.
6. Draft the v0 grammar.
7. Draft the v0 typechecker model.
8. Draft the first compiler targets.
9. Define example files.
10. Define repo milestones and acceptance criteria.
````

## File: docs/language/0010-mirageos-unikernel-surface.md
````markdown
# 0010 — MirageOS as a unikernel materialization surface

Status: **exploration** · Series: language design notes

## Spark

> `mirage/mirage` + nix + vaked ?!?!

- [mirage/mirage](https://github.com/mirage/mirage) — a library OS for constructing **unikernels**: minimal, single-purpose, capability-secure VMs/binaries (OCaml).
- [mirage/mirage-www](https://github.com/mirage/mirage-www) — the MirageOS site, itself shipped as a unikernel.

## The idea

Today the canonical Vaked compilation path is:

```text
Vaked source → NixOS host → OTP supervision plane → Zig enforcement daemons → eBPF evidence → surfaces
```

MirageOS offers a **second materialization target** for an enforcement membrane: instead of (or alongside) a Zig daemon supervised on a shared NixOS host, a membrane can become a **sealed unikernel** — deny-by-default *by construction*, with an attack surface of essentially "the code you linked." This is the strongest possible reading of the `process`/`network` membranes: a workload that physically cannot do what it wasn't linked to do.

```text
Vaked membrane decl
    ↓ (Nix materializes)
MirageOS unikernel  (OCaml, only the libraries the membrane needs)
    ↓
deployed on a hypervisor / mesh node as a sealed surface
```

Nix is the bridge: MirageOS builds are reproducible and Nix can drive `mirage configure` / `mirage build`, so a Vaked declaration could emit a unikernel target the same way it emits a NixOS module.

## Where it fits the membranes

- `network` — unikernel has *only* the network stack you linked; deny-by-default is the default.
- `process` — no general-purpose OS underneath; "supervised execution" becomes "this is the only thing that runs."
- `mesh`/`device` — small, sealed unikernels are attractive leaf nodes on the device/mesh graph.
- `surface` — `mirage-www` shows a unikernel *is* a serveable surface.

## Open questions

1. **Language seam.** Vaked's enforcement story is Zig + eBPF on Linux. MirageOS is OCaml unikernels. Is Mirage an *alternative* backend, a *complement* for specific leaf membranes, or a research spike?
2. **eBPF testimony.** A unikernel has no host kernel to attach eBPF to. What replaces "eBPF testifies" for a Mirage-materialized membrane — in-unikernel attestation? host-hypervisor evidence?
3. **Toolchain weight.** OCaml/opam/`mirage` in the dev shell is heavy; gate behind a dedicated `devShells.mirage` rather than the default shell.
4. **Capability mapping.** How does a Vaked capability graph lower onto Mirage's functor/device-driver model?

## Next step

Spike: take one minimal membrane (e.g. a DNS oracle for the `network` membrane) and materialize it both ways — Zig daemon vs MirageOS unikernel — and compare attack surface, reproducibility, and the eBPF-testimony gap.
````

## File: docs/language/0011-type-system.md
````markdown
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
````

## File: vaked/examples/lowering/gen/catalog/zigCorpus.jsonl
````
{"_generated":"generated by Vaked from operator-field.vaked:index zigCorpus — do not edit"}
{"id":"zig.guide#0001","source":"github:Sobeston/zig.guide","path":"chapter-1/hello-world.md","chunk":0,"text":"# Hello World\n\nCreate a file `hello.zig` and run it with `zig run hello.zig`."}
{"id":"zigimg#0001","source":"github:zigimg/zigimg","path":"README.md","chunk":0,"text":"# zigimg\n\nZig library for reading and writing images in a variety of formats."}
````

## File: vaked/examples/lowering/gen/zig/mediaCompress.json
````json
{
  "_generated": "generated by Vaked from operator-field.vaked:fiber mediaCompress — do not edit",
  "engine": "zigimg",
  "engine_package": "packages.zigimg",
  "input": {
    "stream": "screenrec",
    "source": "agentpipe.screenrec",
    "type": "Media.Frame",
    "fps": 10
  },
  "output": {
    "target": "artifacts.compressedMedia"
  },
  "policy": {
    "strip_metadata": true,
    "max_pixels": "4K",
    "formats": ["png", "webp"]
  },
  "observe": false
}
````

## File: vaked/examples/lowering/gen/RUNTIME.md
````markdown
<!-- generated by Vaked from operator-field.vaked:runtime operator-field — do not edit -->

# Runtime: operator-field

Generated from `operator-field.vaked`. This document is a rendering of the
`runtime operator-field` declaration — see
[`docs/language/0012-lowering.md`](../../../../docs/language/0012-lowering.md)
§5.1. Do not edit; regenerate from source.

- **Systems:** `x86_64-linux`, `aarch64-linux`

## Indexes

| Index | Source(s) | Normalize / Chunk | Trust | Emit |
|-------|-----------|-------------------|-------|------|
| `zigCorpus` | `github("Sobeston/zig.guide")`, `github("C-BJ/awesome-zig")`, `github("raylib-zig/raylib-zig")`, `github("zigimg/zigimg")` | `crabcc.markdown` | — | `catalog.jsonl`, `catalog.sqlite`, `nix.derivation` |
| `zigbeeFirmware` | `raw.github("Koenkk/zigbee-OTA", "index.json")` | — | `pinned` (commit `<commit>`) | — |

## Streams

| Stream | Source | Type | Retention / FPS |
|--------|--------|------|-----------------|
| `ebpfEvents` | `agentGuardd.ringbuf` | `Event.Ebpf` | retention `24h` |
| `screenrec` | `agentpipe.screenrec` | `Media.Frame` | fps `10` |

## Fibers

| Fiber | Engine | Input | Output | Policy |
|-------|--------|-------|--------|--------|
| `mediaCompress` | `zigimg` | `stream.screenrec` | `artifacts.compressedMedia` | `strip_metadata = true`, `max_pixels = "4K"`, `formats = ["png", "webp"]` |

## Surfaces

| Surface | Mode | FPS | Input | Views |
|---------|------|-----|-------|-------|
| `operatorMap` | `raylib` | `60` | `stream.ebpfEvents`, `graph.workflow`, `graph.agentfield` | `network-flows`, `workflow-dag`, `filesystem-diff`, `mesh-topology` |

## Parallel groups

| Group | Fibers | Strategy | Supervisor |
|-------|--------|----------|------------|
| `operator-runtime` | `mediaCompress`, `operatorMap` | `supervised-dag` | `otp` |

## Capability grants

No `mesh` or `capability` declarations in this runtime, so there are no declared
principal grant-sets (0012 §5.1). The implied daemon-channel uses follow from the
stream sources:

| Principal / consumer | Used channel | Implied membrane |
|----------------------|--------------|------------------|
| `stream ebpfEvents` | `agentGuardd.ringbuf` | `ebpf` (agent-guardd) |
| `stream screenrec` | `agentpipe.screenrec` | `media` capture |
| `fiber mediaCompress` (`output = artifacts.compressedMedia`) | artifact capture | `filesystem` (fs-snapshotd) |

> Membranes per [`docs/context/PROJECT_CONTEXT.md`](../../../../docs/context/PROJECT_CONTEXT.md)
> and the daemon roster in [`docs/runtime/README.md`](../../../../docs/runtime/README.md).
> eBPF policy manifests / OTel config / systemd units / surface launcher are
> deferred targets (0012 §7).
````

## File: vaked/examples/lowering/flake.nix
````nix
# generated by Vaked from operator-field.vaked:runtime operator-field — do not edit
#
# Expected-output fixture (no compiler exists yet) — see ./README.md and
# docs/language/0012-lowering.md §4 (the Nix spine). Edits belong in the source
# .vaked file, not here.
{
  description = "operator-field — generated by Vaked";

  inputs = {
    # nixpkgs is emitted pinned to the toolchain's baseline rev (0012 §4.1): an
    # explicit rev, never a moving channel ref. The 40-hex value below is a
    # disclosed placeholder (all-`b` = "baseline"; see ./README.md); the
    # committed flake.lock (produced at first build) records the real resolution.
    nixpkgs.url = "github:NixOS/nixpkgs/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb";

    # index zigCorpus — sources (unpinned; flake.lock records the resolved rev).
    # 0012 §4.2: each index source becomes a flake input.
    zigCorpus-src-zig-guide = { url = "github:Sobeston/zig.guide"; flake = false; };
    zigCorpus-src-awesome-zig = { url = "github:C-BJ/awesome-zig"; flake = false; };
    zigCorpus-src-raylib-zig = { url = "github:raylib-zig/raylib-zig"; flake = false; };
    zigCorpus-src-zigimg = { url = "github:zigimg/zigimg"; flake = false; };

    # index zigbeeFirmware — trust = pinned { commit, sha256 } (0012 §4.2):
    # commit pins the rev; sha256 is recorded as the lock entry's narHash so the
    # build verifies the fetch. raw.github(...) => flake = false.
    zigbeeFirmware-src = {
      url = "github:Koenkk/zigbee-OTA/<commit>"; # trust.pinned.commit
      flake = false;
    };
  };

  outputs = { self, nixpkgs, ... }@inputs:
    let
      # runtime operator-field — systems = ["x86_64-linux", "aarch64-linux"]
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f system);
    in
    {
      # nixosModules.<runtime> — wires the OTP/Zig daemons and references the
      # gen/ artifacts as installed files (0012 §4.3).
      nixosModules.operator-field = import ./nixos/operator-field.nix {
        # NixOS module fixture is described in 0012 §4.3; not emitted as a
        # separate file in this fixture set (interface only).
        inherit self;
      };

      packages = forAllSystems (system:
        let pkgs = nixpkgs.legacyPackages.${system};
        in {
          # engine zigimg (fiber mediaCompress: engine = zigimg) — built Zig pkg.
          zigimg = pkgs.callPackage ./pkgs/zigimg.nix { };

          # index zigCorpus, emit ∋ nix.derivation (0012 §5.3a) — CrabCC index
          # derivation; runs crabcc at build time over the pinned sources with
          # normalize = crabcc.markdown.
          zigCorpus-crabcc-index = pkgs.stdenv.mkDerivation {
            pname = "zigCorpus-crabcc-index";
            version = "0";
            srcs = [
              inputs.zigCorpus-src-zig-guide
              inputs.zigCorpus-src-awesome-zig
              inputs.zigCorpus-src-raylib-zig
              inputs.zigCorpus-src-zigimg
            ];
            nativeBuildInputs = [ pkgs.crabcc ];
            buildPhase = ''
              # normalize = crabcc.markdown ; emit = catalog.jsonl, catalog.sqlite
              crabcc index build --normalize markdown \
                --emit jsonl --emit sqlite \
                --out $out
            '';
          };
        });

      apps = forAllSystems (system:
        let pkgs = nixpkgs.legacyPackages.${system};
        in {
          # surface operatorMap (mode = raylib) — launcher app.
          # 0012 §7: surface launcher body is DEFERRED (no-op today). The slot
          # exists so the registry test stays honest, but the mapping (raylib
          # host integration) is not yet specified. The deferred body is derived
          # from NOTHING but the surface decl name: a stub that exits non-zero
          # with the standard deferral message — no real launcher is wired, and
          # it does not route through any engine/fiber package.
          operatorMap = {
            type = "app";
            program = "${pkgs.writeShellScript "operatorMap-launcher-deferred" ''
              echo "vaked: surface launcher lowering deferred (0012 §7)" >&2
              exit 1
            ''}";
          };
        });

      devShells = forAllSystems (system:
        let pkgs = nixpkgs.legacyPackages.${system};
        in {
          default = pkgs.mkShell {
            # toolchains the runtime needs: zig (engines), crabcc (index).
            packages = [ pkgs.zig pkgs.crabcc ];
          };
        });
    };
}
````

## File: vaked/examples/primitives/catalog.vaked
````
# Minimal v0.2 example — catalog primitive
# Demonstrates: from ref-app, key list of strings, emit app-with-path-arg.

catalog firmware {
  from = index.zigbeeFirmware
  key = ["manufacturer", "image_type", "file_version"]
  emit = sqlite("./var/firmware.db")
}
````

## File: vaked/examples/primitives/device.vaked
````
# Minimal v0.2 example — device primitive
# Demonstrates: driver ref-app, mount string, permissions list of strings,
#               observe bool.

device zigbeeRadio {
  driver = usb.cdc_acm
  mount = "/dev/ttyUSB0"
  permissions = ["read", "write"]
  observe = true
}
````

## File: vaked/examples/primitives/fiber.vaked
````
# Minimal v0.2 example — fiber primitive
# Demonstrates: engine ref-app, input/output ref-apps, policy app+record,
#               bool and string literals in policy body.

fiber mediaCompress {
  engine = zigimg
  input = stream.screenrec
  output = artifacts.compressedMedia

  policy {
    strip_metadata = true
    max_pixels = "4K"
    formats = ["png", "webp"]
  }
}
````

## File: vaked/examples/primitives/index.vaked
````
# Minimal v0.2 example — index primitive
# Demonstrates: source list of app calls, normalize ref-app, chunk app+record,
#               emit list, pinned trust record.

index zigRefs {
  source = [
    github("Sobeston/zig.guide"),
    github("C-BJ/awesome-zig"),
    github("zigimg/zigimg")
  ]

  normalize = crabcc.markdown
  chunk = crabcc.semantic {
    max_tokens = 1200
    overlap = 120
  }

  emit = [catalog.jsonl, catalog.sqlite, nix.derivation]
}

index zigbeeFirmware {
  source = raw.github("Koenkk/zigbee-OTA", "index.json")
  schema = schema.zigbeeOta
  trust = pinned {
    commit = "abc123def456"
    sha256 = "sha256-AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
  }
}
````

## File: vaked/examples/primitives/mediaPipeline.vaked
````
# Minimal v0.2 example — mediaPipeline primitive
# Demonstrates: source ref-app, stages list of app+record values,
#               sink ref-app, codec string literal.

mediaPipeline screenCapture {
  source = device.framebuffer

  stages = [
    resize {
      width = 1920
      height = 1080
    },
    encode {
      codec = "h264"
      bitrate = 2000000
    }
  ]

  sink = stream.screenrec
}
````

## File: vaked/examples/primitives/mesh.vaked
````
# Minimal v0.2 example — mesh primitive
# Demonstrates: node declarations (node_decl), -> edges (edge), ref-app values,
#               list of ref-apps for capabilities.

mesh agentfield {
  node codex {
    role = "worker"
    capabilities = [fs.repo_rw, mcp.github_read]
  }

  node redteam {
    role = "reviewer"
    capabilities = [fs.repo_ro, network.none]
  }

  codex -> mcpBroker
  redteam -> eventd
  mcpBroker -> eventd : "audit"
}
````

## File: vaked/examples/primitives/parallel.vaked
````
# Minimal v0.2 example — parallel primitive
# Demonstrates: fibers list of ref-apps, strategy string, supervisor ref-app.
# NOTE: backpressure is intentionally absent — deferred post-v0.2.

parallel "operator-runtime" {
  fibers = [
    ebpfIngest,
    otaIndex,
    mediaCompress,
    operatorMap
  ]

  strategy = "supervised-dag"
  supervisor = otp
}
````

## File: vaked/examples/primitives/stream.vaked
````
# Minimal v0.2 example — stream primitive
# Demonstrates: source ref-app, type ref-app (dotted), retention duration literal,
#               fps number literal.

stream ebpfEvents {
  source = agentGuardd.ringbuf
  type = Event.Ebpf
  retention = 24h
}

stream screenrec {
  source = agentpipe.screenrec
  type = Media.Frame
  fps = 10
}
````

## File: vaked/examples/primitives/surface.vaked
````
# Minimal v0.2 example — surface primitive
# Demonstrates: mode ref-app, fps number, input list of ref-apps, views list of strings.

surface operatorMap {
  mode = raylib
  fps = 60

  input = [
    stream.ebpfEvents,
    graph.workflow,
    graph.agentfield
  ]

  views = [
    "network-flows",
    "workflow-dag",
    "filesystem-diff",
    "mesh-topology"
  ]
}
````

## File: vaked/examples/types/capability-attenuation.vaked
````
# v0.3 example — a `capability` taxonomy + a mesh delegating an ATTENUATED cap.
#
# Grammar:  capability decl, grant_decl, order_decl, order_chain
#           (vaked-v0-plus.ebnf, v0.3); mesh node_decl + edge (v0.2, unchanged).
# Rules:    docs/language/0011-type-system.md §4 (attenuation, POLA).
# Catalog:  mirrors the built-in `fs` domain in vaked/schema/parallel-types.md.

# A user-declared capability domain. `a < b` means a is the WEAKER (more
# attenuated) grant; delegation may only go to a grant <= what the sender holds.
# The relation is acyclic => a partial order (0011 §4.2).
capability storage {
  grant none read append write admin
  order none < read < append < write < admin
}

# A second domain with a NON-total (branching) order, to show partial-order
# behaviour: `cache` and `queue` are incomparable (neither dominates the other).
capability bus {
  grant none cache queue admin
  order none < cache < admin ;
        none < queue < admin
}

mesh deliveryField {
  node planner {
    role = "planner"
    capabilities = [storage.write, bus.admin]
  }

  node worker {
    role = "worker"
    # worker holds strictly LESS than planner in every shared domain:
    #   storage.append < storage.write   (OK to receive)
    #   bus.cache      < bus.admin        (OK to receive)
    capabilities = [storage.append, bus.cache]
  }

  # Delegation edge: planner -> worker. The checker verifies
  # granted(worker) <= granted(planner), per domain (0011 §4.4):
  #   storage: append <= write  ✓
  #   bus:     cache  <= admin   ✓
  # => attenuation holds; this edge is ACCEPTED.
  planner -> worker : "delegate"
}
````

## File: vaked/examples/types/conformant.vaked
````
# v0.3 example — a CONFORMANT runtime fragment (passes `vaked check`).
#
# Pairs with `rejected.vaked`. See README.md for the side-by-side explanation.
# Every block here conforms to its schema in vaked/schema/parallel-types.md and
# satisfies the closed constraint set + capability attenuation (0011 §1, §3, §4).

capability fs {
  grant none repo_ro repo_rw host_ro host_rw
  order none < repo_ro < repo_rw < host_rw ;
        repo_ro < host_ro < host_rw
}

mesh reviewField {
  node author {
    role = "author"
    capabilities = [fs.repo_rw]
  }

  node reviewer {
    role = "reviewer"
    capabilities = [fs.repo_ro]          # repo_ro < repo_rw : strictly weaker
  }

  # Attenuation holds: granted(reviewer)=repo_ro <= granted(author)=repo_rw.
  author -> reviewer : "handoff"
}

# A stream that conforms to schema `stream` (parallel-types.md):
# source (Source), type (TypeRef), retention (Duration), fps (Int > 0).
stream telemetry {
  source = agentGuardd.ringbuf
  type = Event.Ebpf
  retention = 24h
  fps = 30
}
````

## File: vaked/examples/types/README.md
````markdown
# Vaked type-layer examples (grammar v0.3)

These examples exercise the **Goal-2 type system**: user-defined `schema`s with
the closed constraint set, `capability` taxonomies, and capability attenuation
(POLA). They are all derivable from grammar
[`vaked-v0-plus.ebnf`](../../grammar/vaked-v0-plus.ebnf) v0.3 and checked by the
rules in [`docs/language/0011-type-system.md`](../../../docs/language/0011-type-system.md)
against the built-in catalog
[`vaked/schema/parallel-types.md`](../../schema/parallel-types.md).

| File | Shows |
|------|-------|
| [`schema-constraints.vaked`](./schema-constraints.vaked) | A user `schema` using every closed refinement (`required`, `optional`, `nonempty`, `default`, `oneof`, `>=`/`<=`/`in`, `matches /re/`) and an `open` schema. |
| [`capability-attenuation.vaked`](./capability-attenuation.vaked) | Two `capability` domains (one total order, one branching/partial order) and a `mesh` whose edge delegates a **strictly attenuated** capability. |
| [`conformant.vaked`](./conformant.vaked) | A fragment that **passes** `vaked check`. |
| [`rejected.vaked`](./rejected.vaked) | A fragment that **parses but fails** `vaked check`, annotated with the exact diagnostics. |

## Conformant vs rejected — the checking illustration

The two files declare the *same* `capability fs` and a *same-shaped*
`mesh reviewField` + `stream telemetry`, differing only in the values — so the
contrast isolates what the checker enforces.

### Capability attenuation (0011 §4.4)

```vaked
# conformant.vaked                     # rejected.vaked
node author   { capabilities = [fs.repo_rw] }   node author   { capabilities = [fs.repo_ro] }
node reviewer { capabilities = [fs.repo_ro] }   node reviewer { capabilities = [fs.repo_rw] }
author -> reviewer                              author -> reviewer
```

`fs`'s order is `none < repo_ro < repo_rw < …`. A delegation `author ->
reviewer` requires `granted(reviewer) ⊑ granted(author)` — the receiver may hold
**only ≤** what the sender holds.

- **Conformant:** `repo_ro ≤ repo_rw` ✓ — authority *decreases* along the edge.
- **Rejected:** `repo_rw ≰ repo_ro` ✗ — the receiver would gain authority the
  sender never had ⇒ `E-CAP-ATTENUATION`. This is POLA as a typing rule.

### Closed constraints + closed schemas (0011 §1, §3)

`stream telemetry` conforms to the built-in `stream` schema
(`fps : Int { optional > 0 }`, closed):

- **Conformant:** `fps = 30` satisfies `> 0`; no unknown fields.
- **Rejected:**
  - `fps = 0` violates the range refinement ⇒ `E-CONSTRAINT-RANGE`.
  - `colour = "red"` is not a declared field of the closed `stream` schema ⇒
    `E-CONFORM-UNKNOWN-FIELD` (would be accepted only if `stream` were `open`).

Each diagnostic is source-mapped to the offending token and names the schema,
field, or order edge involved (0011 §6.5). `rejected.vaked` is intentionally
invalid and should be left that way.
````

## File: vaked/examples/types/rejected.vaked
````
# v0.3 example — a REJECTED runtime fragment (FAILS `vaked check` on purpose).
#
# This file PARSES under grammar v0.3 but is intentionally INVALID: the checker
# (docs/language/0011-type-system.md) produces the diagnostics annotated below.
# Pairs with `conformant.vaked`. See README.md for the side-by-side explanation.
#
# DO NOT "fix" this file — it is the negative half of the conformant/rejected
# pair and must stay invalid.

capability fs {
  grant none repo_ro repo_rw host_ro host_rw
  order none < repo_ro < repo_rw < host_rw ;
        repo_ro < host_ro < host_rw
}

mesh reviewField {
  node author {
    role = "author"
    capabilities = [fs.repo_ro]          # author holds only repo_ro
  }

  node reviewer {
    role = "reviewer"
    capabilities = [fs.repo_rw]          # reviewer holds repo_rw (STRONGER)
  }

  # (1) ATTENUATION ERROR — E-CAP-ATTENUATION (0011 §4.4):
  #     delegating author -> reviewer requires granted(reviewer) <= granted(author),
  #     but repo_rw </= repo_ro (the receiver holds MORE than the sender).
  author -> reviewer : "handoff"
}

stream telemetry {
  source = agentGuardd.ringbuf
  type = Event.Ebpf

  # (2) CONSTRAINT ERROR — E-CONSTRAINT-RANGE (0011 §3.2):
  #     schema `stream` declares  fps : Int { optional > 0 } ;  0 violates `> 0`.
  fps = 0

  # (3) CONFORMANCE ERROR — E-CONFORM-UNKNOWN-FIELD (0011 §1.1 rule 5):
  #     `stream` is a CLOSED schema; `colour` is not a declared field.
  colour = "red"
}
````

## File: vaked/examples/types/schema-constraints.vaked
````
# v0.3 example — a user-defined `schema` exercising the CLOSED constraint set.
#
# Grammar:  field_decl, refinement (required/optional/nonempty/default/oneof/
#           cmp_ref/range_ref/matches), open_decl  (vaked-v0-plus.ebnf, v0.3).
# Rules:    docs/language/0011-type-system.md §3.
# Catalog:  this is the kind of schema an `index` would reference via
#           `schema = schema.zigbeeOta` (vaked/schema/parallel-types.md, index).
#
# Every refinement form appears at least once below.

schema zigbeeOta {
  # required + nonempty String
  field manufacturer : String { required nonempty }

  # required Int constrained to a closed range
  field image_type   : Int { required in 0 .. 255 }

  # required Int with a lower bound only
  field file_version : Int { required >= 0 }

  # Path validated by a bounded regex (anchored https:// prefix)
  field url          : Path { required matches /https:\/\/.*/ }

  # optional Float with an upper bound
  field trust_score  : Float { optional <= 1.0 }

  # optional, defaulted, enumerated String  (default must satisfy oneof — it does)
  field channel      : String { default = "stable" oneof ["stable", "beta", "dev"] }

  # optional non-empty list
  field tags         : List<String> { optional nonempty }
}

# A second schema, declared `open`, that admits unknown fields (0011 §1.1 rule 5).
schema firmwareMeta {
  field sha256 : String { required matches /sha256-.*/ }
  open
}
````

## File: vaked/schema/builtins.vaked
````
# builtins.vaked — the built-in Vaked schema & capability catalog, dogfooded.
#
# NORMATIVE SOURCE: vaked/schema/parallel-types.md.  This file is that catalog
# re-expressed in the v0.3 `schema` / `capability` surface syntax so the checker
# (docs/language/0011-type-system.md, stages 3-4 — vakedc/check.py) can read the
# schema registry and capability taxonomy directly from the parsed LPG instead of
# hard-coding it.  parallel-types.md remains the prose normative reference; a
# spec test (tests/spec/test_vakedc_check.py) guards that every kind and every
# capability domain named there exists here (catalog ↔ md coverage).
#
# Encoding notes (faithful to parallel-types.md):
#   * A field with no presence refinement is REQUIRED (0011 §3.3).
#   * `optional` / `default` mark optional fields.
#   * A schema declares `open` exactly where parallel-types.md says open
#     (device, mediaPipeline, fiberPolicy, meshNode); all others are closed.
#   * The `_` anonymous type-parameter position used in the md prose
#     (`Stream<_>`, `Catalog<_>`, `Fiber<_, _>`) is written here with a named
#     parameter (`Stream<T>`, `Catalog<T>`, `Fiber<I, O>`): the v0.3 lexer does
#     not admit a bare `_` identifier, and a never-further-constrained named
#     parameter is the same schema ("a Stream of some item type").  This is a
#     lossless transcription, recorded as a grammar-gap finding in the design
#     report — it changes nothing the checker enforces.

# --------------------------------------------------------------------------- #
# Built-in kind schemas (one `schema <kind>` per built-in kind)
# --------------------------------------------------------------------------- #

# `runtime` — top-level system container.  Only `systems` is a field; nested
# index/stream/fiber/surface/parallel decls are a structural property of the
# block (handled by elaboration), not fields, so `runtime` stays closed.
schema runtime {
  field systems : List<String> { nonempty }
}

# `engine` — builds a native artifact.  `optimize` lives in the `zig.build`
# record but is listed for documentation of the accepted optimize tags.
schema engine {
  field package  : Derivation
  field optimize : String { optional
                            oneof ["Debug", "ReleaseSafe", "ReleaseFast", "ReleaseSmall"] }
}

# `index` — Index<T>: a reproducible source of structured/semi-structured content.
schema index {
  field source    : Source | List<Source> { nonempty }
  field schema    : Schema<T>   { optional }
  field normalize : Normalizer  { optional }
  field chunk     : Normalizer  { optional }
  field trust     : TrustPolicy { optional }
  field emit      : List<ArtifactTarget> { optional nonempty }
}

# `catalog` — Catalog<T>: a queryable materialization of an index.
schema catalog {
  field from : Index<T>
  field key  : List<String> { optional nonempty }
  field emit : ArtifactTarget | List<ArtifactTarget>
}

# `stream` — Stream<T>: a typed runtime event flow.
schema stream {
  field source    : Source
  field type      : TypeRef
  field retention : Duration { optional }
  field fps       : Int      { optional > 0 }
}

# `fiber` — Fiber<I, O>: a policy-bound execution lane with typed input/output.
schema fiber {
  field engine  : Engine
  field input   : I
  field output  : O
  field policy  : Policy  { optional }
  field budget  : Budget  { optional }
  field observe : Bool    { optional default = false }
}

# the shape of a fiber's `policy { … }` block (open — forward-compatible keys).
schema fiberPolicy {
  field strip_metadata : Bool         { optional }
  field max_pixels     : String       { optional }
  field formats        : List<String> { optional nonempty }
  open
}

# `surface` — Surface: an operator-facing view or control shell.
schema surface {
  field mode   : SurfaceMode
  field fps    : Int { optional > 0 }
  field input  : List<Stream<T> | Graph | Catalog<T>> { nonempty }
  field views  : List<View> { nonempty }
  field budget : Budget { optional }
}

# `mesh` — Mesh<Node, Edge>: agent/process/tool/device topology.  A mesh block is
# a graph block (node decls + `->` edges), not record fields; the node record
# schema below is the body of each `node`.
schema mesh {
}

# shape of a `node <name> { … }` body inside a mesh (open — descriptive keys).
schema meshNode {
  field role         : String { nonempty }
  field capabilities : List<Capability> { optional nonempty }
  open
}

# `device` — Device: a hardware/driver node.  Open (driver vocabularies vary).
schema device {
  field driver      : DriverRef
  field mount       : Path
  field permissions : List<String> { nonempty }
  field observe     : Bool { optional default = false }
  open
}

# `mediaPipeline` — MediaPipeline: a source → stages → sink media graph.  Open.
schema mediaPipeline {
  field source : Source
  field stages : List<Stage> { nonempty }
  field sink   : Stream<T> | Source
  open
}

# stage record schemas (the `resize`/`encode` builders inside a mediaPipeline).
schema stageResize {
  field width  : Int { > 0 }
  field height : Int { > 0 }
}
schema stageEncode {
  field codec   : String { nonempty }
  field bitrate : Int    { > 0 }
}

# `parallel` — ParallelGroup: a supervised group of fibers.  Closed (enforces the
# backpressure deferral: a stray `backpressure { … }` is an unknown field).
schema parallel {
  field fibers     : List<Fiber<I, O>> { nonempty }
  field strategy   : Strategy
  field supervisor : Supervisor
}

# --------------------------------------------------------------------------- #
# Built-in capability taxonomy (one `capability <domain>` per built-in domain)
# `a < b` ⇒ a is the WEAKER (more attenuated) grant; delegation may only go to ≤.
# Each order is acyclic ⇒ a partial order (0011 §4.2).
# --------------------------------------------------------------------------- #

# `fs` — filesystem authority.  Two chains sharing none/repo_ro/host_rw;
# repo_rw and host_ro are incomparable.
capability fs {
  grant none repo_ro repo_rw host_ro host_rw
  order none < repo_ro < repo_rw < host_rw ;
        repo_ro < host_ro < host_rw
}

# `network` — network authority.  Total order.
capability network {
  grant none loopback lan egress
  order none < loopback < lan < egress
}

# `mcp` — MCP broker authority.  Total order.
capability mcp {
  grant none github_read github_write broker_admin
  order none < github_read < github_write < broker_admin
}

# `ebpf` — eBPF/observation authority.  Total order.
capability ebpf {
  grant none observe attach_ro attach_rw
  order none < observe < attach_ro < attach_rw
}

# `process` — process/exec authority.  Total order.
capability process {
  grant none spawn_sandboxed spawn exec_host
  order none < spawn_sandboxed < spawn < exec_host
}
````

## File: vakedc/check.py
````python
#!/usr/bin/env python3
"""vakedc.check — 0011 type-system pipeline stages 3 (elaborate) and 4 (check).

This is the Goal-2 checker.  It is a **pure** function of (a parsed .vaked file +
the built-in catalog ``vaked/schema/builtins.vaked``) → a deterministic, source-
mapped list of :class:`Diagnostic` records.  The only IO it performs is reading
the builtins catalog file once (``load_builtins``); :func:`check_source` /
:func:`check_graph` take the source text directly and do no IO.

What it implements (docs/language/0011-type-system.md):

  * Stage 3 — *elaborate*: build a schema registry from the builtins LPG plus the
    in-file user ``schema`` / ``capability`` declarations (user decls extend or
    override the catalog by name, per 0011 §1), and a per-domain capability
    attenuation partial order (reflexive-transitive closure of the ``order``
    chains).
  * Stage 4 — *check*:
      (a) conformance — §1.1 five-clause rule (required present + well-typed via
          structural matching incl. the Path-from-String acceptance of §2.5;
          optionals; constraints; unknown fields rejected unless the schema is
          ``open``);
      (b) constraints — the CLOSED set of §3 (oneof, cmp, range, nonempty,
          matches within the bounded regex dialect, default agreement), plus
          load-time refinement well-formedness (§3.7) and capability-order
          well-formedness (§4.2);
      (c) capabilities — §4: every ``domain.grant`` reference is valid, and a
          ``mesh`` delegation edge (``routes_to``) must not escalate authority —
          the receiver's grant-set must be ``⊑`` the sender's, per domain;
      (d) generics — §5: ``catalog.from`` must target an ``index`` (and the item
          type must agree when both declare one); a ``fiber``'s ``input`` /
          ``output`` are bound and, where the data permits, checked for
          consistency.

Diagnostics carry stable 0011 codes (``E-CONFORM-*``, ``E-CONSTRAINT-*``,
``E-CAP-*``, ``E-GENERIC-*``, plus the load-time ``E-SCHEMA-*`` / ``E-CAP-ORDER-
CYCLE`` of §6.5), are source-mapped from the AST/token spans, and are sorted by
``(file, byteStart, code)`` for determinism.

Spans: the LPG records provenance at the *declaration* granularity only, and the
AST exposes byte spans for decls, nodes, and refs but not for assignments or
literals.  To land a diagnostic on the exact offending construct (a field name,
a value literal, an edge), this module re-tokenizes each source file once and
locates the construct within its enclosing decl's byte range — deterministically
and with no extra IO beyond the already-read source text.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field as dc_field

from . import parser as P
from .lexer import tokenize
from .parser import parse_source
from .resolve import build_graph


# --------------------------------------------------------------------------- #
# Diagnostic record
# --------------------------------------------------------------------------- #

@dataclass
class Diagnostic:
    code: str
    message: str
    file: str
    line: int
    col: int
    byteStart: int
    byteEnd: int
    decl: str                      # "<kind> <name>" of the enclosing declaration
    severity: str = "error"
    related: list = dc_field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "file": self.file,
            "decl": self.decl,
            "span": {
                "byteStart": self.byteStart,
                "byteEnd": self.byteEnd,
                "line": self.line,
                "col": self.col,
            },
            "related": list(self.related),
        }

    def sort_key(self):
        return (self.file, self.byteStart, self.byteEnd, self.code)


# --------------------------------------------------------------------------- #
# Default builtins-catalog location
# --------------------------------------------------------------------------- #

def default_builtins_path() -> str:
    """Absolute path to the repo's ``vaked/schema/builtins.vaked``.

    Resolved relative to this package (``vakedc/`` lives at the repo root next to
    ``vaked/``), so ``python3 -m vakedc check`` works from any CWD.  If that path
    does not exist (e.g. an unusual install layout), fall back to a CWD-relative
    ``vaked/schema/builtins.vaked``.
    """
    pkg_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(pkg_dir)
    candidate = os.path.join(repo_root, "vaked", "schema", "builtins.vaked")
    if os.path.exists(candidate):
        return candidate
    return os.path.join(os.getcwd(), "vaked", "schema", "builtins.vaked")


# --------------------------------------------------------------------------- #
# Source position map — locate a construct's byte span within a decl
# --------------------------------------------------------------------------- #

class _SourceMap:
    """Token-indexed view of one source file, used to land diagnostics on the
    exact offending token (the AST/LPG only span declarations and refs)."""

    __slots__ = ("file", "tokens")

    def __init__(self, src: str, filename: str):
        self.file = filename
        # tokenize is deterministic and pure; comments are already stripped.
        self.tokens = [t for t in tokenize(src, filename) if t.kind not in ("NEWLINE", "EOF")]

    def _toks_in(self, byteStart: int, byteEnd: int):
        return [t for t in self.tokens if byteStart <= t.byteStart < byteEnd]

    def field_name_span(self, decl_start, decl_end, name):
        """Span of the FIRST top-level assignment / field-name identifier ``name``
        within [decl_start, decl_end).  Used for unknown-field and missing-value
        diagnostics."""
        toks = self._toks_in(decl_start, decl_end)
        for idx, t in enumerate(toks):
            if t.kind == "IDENT" and t.value == name:
                nxt = toks[idx + 1] if idx + 1 < len(toks) else None
                # `name =` / `name ?=` / `name :` (assignment, field decl) and
                # `name {` (app-with-record / block-shaped field, e.g. an
                # unknown `backpressure { … }` inside a closed schema).
                if nxt is not None and nxt.kind == "OP" and nxt.value in ("=", "?=", ":", "{"):
                    return _span_of(t)
        return None

    def field_value_span(self, decl_start, decl_end, name):
        """Span covering the VALUE of assignment ``name = <value>`` within the
        decl range — from the first value token after the assign-op up to the end
        of that value.  Used for constraint diagnostics (land on the literal)."""
        toks = self._toks_in(decl_start, decl_end)
        for idx, t in enumerate(toks):
            if t.kind == "IDENT" and t.value == name:
                nxt = toks[idx + 1] if idx + 1 < len(toks) else None
                if nxt is not None and nxt.kind == "OP" and nxt.value in ("=", "?="):
                    val = toks[idx + 2] if idx + 2 < len(toks) else None
                    if val is not None:
                        return _span_of(val)
        # fall back to the field name
        return self.field_name_span(decl_start, decl_end, name)


def _span_of(tok):
    return (tok.byteStart, tok.byteEnd, tok.line, tok.col)


# --------------------------------------------------------------------------- #
# Schema & capability registry (Stage 3 — elaborate)
# --------------------------------------------------------------------------- #

# Scalar type names the checker matches structurally against literal forms.
_SCALARS = frozenset(("String", "Int", "Float", "Bool", "Path", "Duration", "Bytes", "Null"))

# Auxiliary (built-in) types that parallel-types.md's vocabulary table defines as
# *aliases of `String`* — a String literal matches them directly.
_STRING_ALIASES = frozenset(("Strategy", "View"))

# A type atom is a generic parameter position when it is a bare upper-case letter
# (T, I, O) or one of the named graph parameters (Node, Edge).  Per 0011 §5 a type
# parameter binds to / matches any value, so the checker accepts any value here
# (the worked examples never give the checker a second binding to contradict).
_GENERIC_PARAMS = frozenset(("Node", "Edge"))


def _is_generic_param(atom):
    return atom in _GENERIC_PARAMS or (len(atom) == 1 and atom.isalpha() and atom.isupper())

# Literal-token kind (Literal.kind / prop "lit") -> the scalar type(s) it inhabits.
# (Int◁Float widening and the Path/Duration/Bytes string-form acceptances of
# §2.1/§2.5 are handled in _value_matches_type, not here.)
_LIT_SCALAR = {
    "STRING": "String",
    "NUMBER": None,         # Int or Float, decided by the '.' rule
    "BOOL": "Bool",
    "PATH": "Path",
    "DURATION": "Duration",
    "BYTES": "Bytes",
    "NULL": "Null",
}


@dataclass
class FieldSpec:
    name: str
    type_text: str
    refinements: list           # list of refinement tuples (AST objects inside)
    presence: str               # "required" | "optional"
    has_default: bool


@dataclass
class SchemaSpec:
    name: str
    fields: "dict[str, FieldSpec]"
    open: bool
    origin_file: str
    decl_span: tuple            # (byteStart, byteEnd, line, col) of the schema decl


@dataclass
class CapabilitySpec:
    domain: str
    grants: set
    order_chains: list          # list of list[str]
    leq: dict                   # grant -> set of grants g' with g <= g' (closure)
    origin_file: str
    decl_span: tuple


def _presence_of(refinements):
    """Derive ('required'|'optional', has_default) from a field's refinements,
    per 0011 §3.3 (default = required unless `optional` or a `default` is given)."""
    has_default = any(r[0] == "default" for r in refinements)
    if any(r[0] == "optional" for r in refinements):
        return "optional", has_default
    if has_default:
        return "optional", has_default
    # explicit `required` or no presence marker → required
    return "required", has_default


def _schema_from_decl(decl, filename) -> SchemaSpec:
    fields = {}
    is_open = False
    for st in decl.body:
        if isinstance(st, P.FieldDecl):
            presence, has_default = _presence_of(st.refinements)
            fields[st.name] = FieldSpec(
                name=st.name,
                type_text=st.type.text,
                refinements=list(st.refinements),
                presence=presence,
                has_default=has_default,
            )
        elif isinstance(st, P.OpenDecl):
            is_open = True
    return SchemaSpec(
        name=decl.name, fields=fields, open=is_open,
        origin_file=filename,
        decl_span=(decl.byteStart, decl.byteEnd, decl.line, decl.col),
    )


def _capability_from_decl(decl, filename) -> CapabilitySpec:
    grants = []
    chains = []
    for st in decl.body:
        if isinstance(st, P.GrantDecl):
            grants.extend(st.names)
        elif isinstance(st, P.OrderDecl):
            chains.extend([list(c) for c in st.chains])
    return CapabilitySpec(
        domain=decl.name, grants=set(grants), order_chains=chains, leq={},
        origin_file=filename,
        decl_span=(decl.byteStart, decl.byteEnd, decl.line, decl.col),
    )


def _transitive_closure(grants, chains):
    """Reflexive-transitive closure of the `<` relation declared by the chains.

    Returns ``leq`` mapping each grant g to the set { g' : g <= g' } (g is weaker
    than or equal to g').  Returns ``None`` together with the offending pair if a
    cycle is detected (the relation is then not antisymmetric — a schema error)."""
    # direct edges a -> b for each consecutive pair a<b in a chain
    succ = {g: set() for g in grants}
    for ch in chains:
        for a, b in zip(ch, ch[1:]):
            succ.setdefault(a, set()).add(b)
            succ.setdefault(b, set())
    # Floyd-style closure over the (finite) grant set.
    nodes = set(succ.keys())
    reach = {g: set([g]) for g in nodes}   # reflexive
    for g in nodes:
        stack = list(succ.get(g, ()))
        while stack:
            x = stack.pop()
            if x not in reach[g]:
                reach[g].add(x)
                stack.extend(succ.get(x, ()))
    # a strict order forbids `a < a`: a direct self-edge is a degenerate cycle
    for a in nodes:
        if a in succ.get(a, ()):
            return None, (a, a)
    # antisymmetry: a<=b and b<=a with a!=b  ⇒ cycle
    for a in nodes:
        for b in reach[a]:
            if a != b and a in reach.get(b, ()):
                return None, (a, b)
    return reach, None


# --------------------------------------------------------------------------- #
# Registry assembly + load-time well-formedness checks
# --------------------------------------------------------------------------- #

_LEGAL_REFINEMENTS = frozenset(
    ("required", "optional", "nonempty", "default", "oneof", "cmp", "range", "matches"))


class _Registry:
    def __init__(self):
        self.schemas: "dict[str, SchemaSpec]" = {}
        self.caps: "dict[str, CapabilitySpec]" = {}

    def add_schema(self, spec: SchemaSpec):
        self.schemas[spec.name] = spec      # later (user) overrides earlier (builtin)

    def add_capability(self, spec: CapabilitySpec):
        self.caps[spec.domain] = spec


def _load_decls_into(registry: _Registry, items, filename):
    for it in items:
        if isinstance(it, P.Decl):
            if it.kind == "schema":
                registry.add_schema(_schema_from_decl(it, filename))
            elif it.kind == "capability":
                registry.add_capability(_capability_from_decl(it, filename))


# --------------------------------------------------------------------------- #
# Regex dialect validation (§3.5) — bounded, regular, no backrefs/lookaround
# --------------------------------------------------------------------------- #

def _regex_dialect_error(regex_literal):
    """Return an explanatory string if ``regex_literal`` (the raw `/…/` token,
    slashes included) uses a feature outside the bounded dialect of 0011 §3.5;
    otherwise None.

    Allowed: literal chars, classes [...], '.', '|', grouping (...), quantifiers
    ?, *, +, {m}, {m,n}, anchors ^ $, and backslash escapes of metacharacters.
    Forbidden: backreferences (\\1), lookaround ((?=…) (?<…) (?!…)), named/atomic
    groups and other non-linear constructs ((?P…), (?>…))."""
    body = regex_literal
    if len(body) >= 2 and body[0] == "/" and body[-1] == "/":
        body = body[1:-1]
    i = 0
    n = len(body)
    in_class = False
    while i < n:
        c = body[i]
        if c == "\\":
            if i + 1 >= n:
                return "trailing backslash"
            nxt = body[i + 1]
            if nxt.isdigit() and nxt != "0":
                return "backreference (\\%s) is not in the bounded dialect" % nxt
            i += 2
            continue
        if in_class:
            if c == "]":
                in_class = False
            i += 1
            continue
        if c == "[":
            in_class = True
            i += 1
            continue
        if c == "(":
            # grouping; reject the extension forms after '(?'
            if i + 1 < n and body[i + 1] == "?":
                kind = body[i + 2] if i + 2 < n else ""
                if kind in ("=", "!"):
                    return "lookahead ((?%s…)) is not in the bounded dialect" % kind
                if kind == "<":
                    nxt = body[i + 3] if i + 3 < n else ""
                    if nxt in ("=", "!"):
                        return "lookbehind ((?<%s…)) is not in the bounded dialect" % nxt
                    return "named group ((?<…>)) is not in the bounded dialect"
                if kind == "P":
                    return "named group ((?P…)) is not in the bounded dialect"
                if kind == ">":
                    return "atomic group ((?>…)) is not in the bounded dialect"
                if kind == ":":
                    i += 3   # non-capturing group is fine
                    continue
                return "extended group ((?%s…)) is not in the bounded dialect" % kind
            i += 1
            continue
        i += 1
    if in_class:
        return "unterminated character class '['"
    return None


# --------------------------------------------------------------------------- #
# Load-time refinement & capability well-formedness (§3.7, §4.2, §6.5)
# --------------------------------------------------------------------------- #

def _base_type(type_text):
    """Strip the outermost ``List<…>`` wrapper, returning (inner_text, is_list)."""
    t = type_text.strip()
    if t.startswith("List<") and t.endswith(">"):
        return t[len("List<"):-1].strip(), True
    return t, False


def _is_numeric_type(type_text):
    inner, _ = _base_type(type_text)
    return inner in ("Int", "Float", "Duration", "Bytes")


def _check_schema_wellformed(spec: SchemaSpec, smap_for, diags):
    """0011 §3.7 / §6.4a — load-time well-formedness of a schema's refinements.
    Errors are reported against the schema declaration's source."""
    smap = smap_for(spec.origin_file)
    ds, de, dl, dc = spec.decl_span
    for fname, f in spec.fields.items():
        seen_presence = set()
        for r in f.refinements:
            kind = r[0]
            span = None
            if smap is not None:
                span = smap.field_name_span(ds, de, fname) or (ds, de, dl, dc)
            else:
                span = (ds, de, dl, dc)
            if kind in ("required", "optional"):
                seen_presence.add(kind)
            if kind == "matches":
                if _base_type(f.type_text)[0] not in ("String", "Path"):
                    _emit(diags, "E-SCHEMA-REFINEMENT", spec.origin_file, span, spec,
                          "`matches` applies only to String or Path; field "
                          f"`{fname}` is `{f.type_text}`")
                else:
                    err = _regex_dialect_error(r[1])
                    if err is not None:
                        _emit(diags, "E-SCHEMA-BAD-REGEX", spec.origin_file, span, spec,
                              f"field `{fname}`: {err}")
            elif kind == "oneof":
                ll = r[1]
                items = getattr(ll, "items", [])
                if len(items) < 1:
                    _emit(diags, "E-SCHEMA-REFINEMENT", spec.origin_file, span, spec,
                          f"field `{fname}`: `oneof` needs at least one element")
                for lit in items:
                    if not _literal_matches_type(lit, f.type_text):
                        _emit(diags, "E-SCHEMA-BAD-ONEOF", spec.origin_file, span, spec,
                              f"field `{fname}`: `oneof` element "
                              f"{_render_literal(lit)} does not match type "
                              f"`{f.type_text}`")
            elif kind in ("cmp", "range"):
                if not _is_numeric_type(f.type_text):
                    _emit(diags, "E-SCHEMA-REFINEMENT", spec.origin_file, span, spec,
                          f"field `{fname}`: numeric refinement on non-numeric "
                          f"type `{f.type_text}`")
                if kind == "range":
                    lo = _num(r[1])
                    hi = _num(r[2])
                    if lo is not None and hi is not None and lo > hi:
                        _emit(diags, "E-SCHEMA-BAD-RANGE", spec.origin_file, span, spec,
                              f"field `{fname}`: range lower bound {r[1]} exceeds "
                              f"upper bound {r[2]}")
            elif kind == "default":
                lit = r[1]
                # default must satisfy the field type; no refs allowed.
                if isinstance(lit, P.App):
                    _emit(diags, "E-SCHEMA-BAD-DEFAULT", spec.origin_file, span, spec,
                          f"field `{fname}`: `default` must be a literal, not a ref")
                elif isinstance(lit, P.Literal) and not _literal_matches_type(lit, f.type_text):
                    _emit(diags, "E-SCHEMA-BAD-DEFAULT", spec.origin_file, span, spec,
                          f"field `{fname}`: default {_render_literal(lit)} does not "
                          f"match type `{f.type_text}`")
        if "required" in seen_presence and ("optional" in seen_presence or f.has_default):
            span = (smap.field_name_span(ds, de, fname) if smap else None) or (ds, de, dl, dc)
            _emit(diags, "E-SCHEMA-REFINEMENT", spec.origin_file, span, spec,
                  f"field `{fname}`: `required` cannot be combined with "
                  f"`optional`/`default`")


def _check_capability_wellformed(spec: CapabilitySpec, smap_for, diags):
    """0011 §4.2 — dangling grants, exactly-one-order (structural), acyclicity."""
    smap = smap_for(spec.origin_file)
    ds, de, dl, dc = spec.decl_span
    span = (ds, de, dl, dc)
    # 1. every grant named in order must be declared
    named = set()
    for ch in spec.order_chains:
        named.update(ch)
    dangling = sorted(named - spec.grants)
    for g in dangling:
        gs = (smap.field_name_span(ds, de, g) if smap else None) or span
        _emit(diags, "E-CAP-ORDER-DANGLING", spec.origin_file, gs, spec,
              f"capability `{spec.domain}`: order names grant `{g}` which is not "
              f"declared by a `grant` statement")
    # 2/3. acyclicity (antisymmetry) of the closure
    leq, cyc = _transitive_closure(spec.grants, spec.order_chains)
    if cyc is not None:
        a, b = cyc
        _emit(diags, "E-CAP-ORDER-CYCLE", spec.origin_file, span, spec,
              f"capability `{spec.domain}`: order is cyclic (`{a}` and `{b}` are "
              f"mutually ≤) — the relation must be a partial order")
        spec.leq = {g: set([g]) for g in spec.grants}
    else:
        spec.leq = leq


# --------------------------------------------------------------------------- #
# Literal / value helpers
# --------------------------------------------------------------------------- #

def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def _render_literal(lit):
    if isinstance(lit, P.Literal):
        if lit.kind == "STRING":
            return '"%s"' % lit.value
        return str(lit.value)
    return repr(lit)


def _literal_matches_type(lit, type_text):
    """Does an AST :class:`Literal` match a (possibly composite) type textually?
    Implements the scalar arm of §2.4 incl. Int◁Float and the string-forms of
    §2.1/§2.5 for Path/Duration/Bytes."""
    inner, is_list = _base_type(type_text)
    if is_list:
        return False   # a scalar literal never matches a List type
    arms = [a.strip() for a in inner.split("|")]
    return any(_literal_matches_scalar(lit, a) for a in arms)


def _literal_matches_scalar(lit, type_atom):
    if not isinstance(lit, P.Literal):
        return False
    k = lit.kind
    if _is_generic_param(type_atom):
        # a type parameter matches any value (§5 unification, unconstrained here).
        return True
    if type_atom in _STRING_ALIASES:
        # Strategy / View are String aliases (parallel-types.md vocabulary table).
        return k == "STRING"
    if type_atom not in _SCALARS:
        # Non-scalar (domain/aux/generic) atom: a bare literal cannot be shown to
        # match a ref-shaped type, EXCEPT the String→Path positional acceptance
        # is handled where Path is the atom (below).  Be conservative: literals
        # only match scalar atoms.
        return False
    if type_atom == "Null":
        return k == "NULL"
    if type_atom == "String":
        return k == "STRING"
    if type_atom == "Bool":
        return k == "BOOL"
    if type_atom == "Int":
        return k == "NUMBER" and "." not in str(lit.value)
    if type_atom == "Float":
        # Int◁Float widening: an Int literal matches Float (§2.4).
        return k == "NUMBER"
    if type_atom == "Path":
        # path literal, or a String used positionally as a path (§2.5).
        return k in ("PATH", "STRING")
    if type_atom == "Duration":
        return k in ("DURATION", "STRING")
    if type_atom == "Bytes":
        return k in ("BYTES", "STRING")
    return False


# value-prop forms (as produced by resolve._value_to_props):
#   literal : {"lit": <kind>, "value": ...}
#   ref/app : {"ref": <dotted>, "args"?: [...], "record"?: [...]}
#   list    : [ <value-prop>, ... ]
#   record  : {"record": [ {"assign":..} | {"inherit":..}, ... ]}

def _value_matches_type(vprop, type_text, registry):
    """Structural match (§2.4) of a value PROP against a type, *as strong as 0011
    states and no stronger*.

    Scalars match by literal form (incl. Int◁Float and the Path/Duration/Bytes
    string-forms).  ``List<T>`` requires a list whose elements each match ``T``.
    Unions match if any arm matches.  A *ref* (``{"ref": …}`` with no call args /
    record) matches any non-scalar (domain/auxiliary/generic) type — its referent
    is an external/built-in value whose type the checker cannot disprove (§2.3),
    which keeps the 15 worked examples valid without inventing checks 0011 does
    not mandate.  A call/record value matches a non-scalar type structurally."""
    inner, is_list = _base_type(type_text)
    if is_list:
        if not isinstance(vprop, list):
            return False
        return all(_value_matches_type(e, inner, registry) for e in vprop)
    arms = [a.strip() for a in _split_union(inner)]
    return any(_value_matches_atom(vprop, a, registry) for a in arms)


def _split_union(text):
    """Split a union type on top-level '|' (not inside '<...>')."""
    parts = []
    depth = 0
    cur = []
    for ch in text:
        if ch == "<":
            depth += 1
            cur.append(ch)
        elif ch == ">":
            depth -= 1
            cur.append(ch)
        elif ch == "|" and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append("".join(cur))
    return parts


def _value_matches_atom(vprop, atom, registry):
    atom = atom.strip()
    atom_base, atom_is_list = _base_type(atom)
    if atom_is_list:
        return _value_matches_type(vprop, atom, registry)
    # a generic type parameter matches any value (§5).
    if _is_generic_param(atom_base):
        return True
    # literal value
    if isinstance(vprop, dict) and "lit" in vprop:
        return _litprop_matches_scalar(vprop, atom_base)
    # list value only matches a List atom (handled above) — here atom is scalar
    if isinstance(vprop, list):
        return False
    # ref / app / record value
    if isinstance(vprop, dict):
        if atom_base in _SCALARS or atom_base in _STRING_ALIASES:
            # a non-literal value cannot match a scalar / String-alias atom
            return False
        # non-scalar atom (domain/aux type, generic param, or a user schema name)
        if atom_base in registry.schemas and "record" in vprop and "ref" not in vprop:
            # a structural record value checked against a named schema
            return _record_conforms(vprop, registry.schemas[atom_base], registry)
        return True
    return False


def _litprop_matches_scalar(vprop, atom):
    kind = (vprop.get("lit") or "").upper()
    value = vprop.get("value")
    fake = P.Literal(kind if kind else "NULL", value)
    return _literal_matches_scalar(fake, atom)


def _record_conforms(vprop, schema: SchemaSpec, registry):
    """Best-effort structural conformance of a record VALUE (nested policy/stage
    blocks) to a named schema.  Returns True/False; nested-record diagnostics are
    intentionally light (the top-level conformance pass owns user-facing errors)."""
    entries = vprop.get("record", [])
    present = {}
    for e in entries:
        if isinstance(e, dict) and "assign" in e:
            present[e["assign"]] = e["value"]
    # required present + typed
    for fname, f in schema.fields.items():
        if f.presence == "required" and fname not in present:
            return False
    if not schema.open:
        for k in present:
            if k not in schema.fields:
                return False
    for k, v in present.items():
        f = schema.fields.get(k)
        if f is not None and not _value_matches_type(v, f.type_text, registry):
            return False
    return True


# --------------------------------------------------------------------------- #
# Constraint application (§3) on a bound field value
# --------------------------------------------------------------------------- #

def _check_field_constraints(vprop, fspec: FieldSpec, decl, smap, file, diags, decl_span):
    """Apply each refinement on ``fspec`` to the bound value ``vprop`` (§3)."""
    ds, de, dl, dc = decl_span
    vspan = (smap.field_value_span(ds, de, fspec.name) if smap else None) or decl_span

    for r in fspec.refinements:
        kind = r[0]
        if kind == "nonempty":
            if _is_empty(vprop):
                _emit(diags, "E-CONSTRAINT-NONEMPTY", file, vspan, decl,
                      f"field `{fspec.name}` is `nonempty` but the value is empty")
        elif kind == "oneof":
            allowed = [(x.kind, x.value) for x in getattr(r[1], "items", [])]
            if isinstance(vprop, dict) and "lit" in vprop:
                k = (vprop.get("lit") or "").upper()
                if not _litprop_in_oneof(vprop, allowed):
                    _emit(diags, "E-CONSTRAINT-ONEOF", file, vspan, decl,
                          f"field `{fspec.name}`: value {_render_vprop(vprop)} is "
                          f"not one of {_render_oneof(allowed)}")
        elif kind == "cmp":
            _check_cmp(vprop, r[1], r[2], fspec, decl, file, diags, vspan)
        elif kind == "range":
            _check_range(vprop, r[1], r[2], fspec, decl, file, diags, vspan)
        # required/optional/default/matches handled in conformance / load-time


def _check_cmp(vprop, op, bound_s, fspec, decl, file, diags, vspan):
    v = _vprop_number(vprop)
    b = _num(bound_s)
    if v is None or b is None:
        return
    ok = {">=": v >= b, "<=": v <= b, ">": v > b, "<": v < b}.get(op, True)
    if not ok:
        _emit(diags, "E-CONSTRAINT-RANGE", file, vspan, decl,
              f"field `{fspec.name}`: value {_fmtnum(v)} violates `{op} {bound_s}`")


def _check_range(vprop, lo_s, hi_s, fspec, decl, file, diags, vspan):
    v = _vprop_number(vprop)
    lo = _num(lo_s)
    hi = _num(hi_s)
    if v is None or lo is None or hi is None:
        return
    if not (lo <= v <= hi):
        _emit(diags, "E-CONSTRAINT-RANGE", file, vspan, decl,
              f"field `{fspec.name}`: value {_fmtnum(v)} is outside "
              f"`in {lo_s} .. {hi_s}`")


def _check_matches(vprop, regex_literal, fspec, decl, file, diags, vspan):
    """Apply a `matches /re/` refinement to a String/Path value (§3.5).  The
    dialect was validated at load; here we run the (linear-time) full match."""
    if not (isinstance(vprop, dict) and "lit" in vprop):
        return   # only literal String/Path values are matchable
    k = (vprop.get("lit") or "").upper()
    if k not in ("STRING", "PATH"):
        return
    value = vprop.get("value")
    if value is None:
        return
    import re as _re
    body = regex_literal
    if len(body) >= 2 and body[0] == "/" and body[-1] == "/":
        body = body[1:-1]
    # implicit full-anchor via fullmatch (§3.5); author-supplied ^/$ anchors
    # are harmless (fullmatch renders them redundant, not erroneous).
    pat = body
    try:
        rx = _re.compile(pat)
    except _re.error:
        return   # malformed regex already reported at load as E-SCHEMA-BAD-REGEX
    if rx.fullmatch(value) is None:
        _emit(diags, "E-CONSTRAINT-MATCHES", file, vspan, decl,
              f"field `{fspec.name}`: value {_render_vprop(vprop)} does not match "
              f"/{body}/")


def _is_empty(vprop):
    if isinstance(vprop, list):
        return len(vprop) == 0
    if isinstance(vprop, dict) and "lit" in vprop:
        v = vprop.get("value")
        return v == "" or v is None
    return False


def _litprop_in_oneof(vprop, allowed):
    k = (vprop.get("lit") or "").upper()
    val = vprop.get("value")
    for (ak, av) in allowed:
        if ak == k and str(av) == str(val):
            return True
        # numeric tolerance: Int literal vs Int oneof element
        if ak == "NUMBER" and k == "NUMBER" and _num(av) == _num(val):
            return True
    return False


def _vprop_number(vprop):
    if isinstance(vprop, dict) and "lit" in vprop and (vprop.get("lit") or "").lower() == "number":
        return _num(vprop.get("value"))
    return None


def _fmtnum(v):
    if v == int(v):
        return str(int(v))
    return str(v)


def _render_vprop(vprop):
    if isinstance(vprop, dict) and "lit" in vprop:
        if (vprop.get("lit") or "").upper() == "STRING":
            return '"%s"' % vprop.get("value")
        return str(vprop.get("value"))
    if isinstance(vprop, dict) and "ref" in vprop:
        return vprop["ref"]
    return repr(vprop)


def _render_oneof(allowed):
    parts = []
    for (k, v) in allowed:
        parts.append('"%s"' % v if k == "STRING" else str(v))
    return "[" + ", ".join(parts) + "]"


# --------------------------------------------------------------------------- #
# Diagnostic emit helper
# --------------------------------------------------------------------------- #

def _emit(diags, code, file, span, decl_or_spec, message, related=None):
    bs, be, ln, col = span
    decl_str = _decl_label(decl_or_spec)
    diags.append(Diagnostic(
        code=code, message=message, file=file,
        byteStart=bs, byteEnd=be, line=ln, col=col,
        decl=decl_str, related=related or [],
    ))


def _decl_label(d):
    if isinstance(d, P.Decl):
        return f"{d.kind} {d.name}"
    if isinstance(d, SchemaSpec):
        return f"schema {d.name}"
    if isinstance(d, CapabilitySpec):
        return f"capability {d.domain}"
    if isinstance(d, str):
        return d
    return ""


# --------------------------------------------------------------------------- #
# Conformance over a single declaration (§1.1)
# --------------------------------------------------------------------------- #

# Statement targets that the resolver lifts to edges but which ARE field bindings
# we still want to conformance-check as fields.
def _decl_field_bindings(decl):
    """Top-level field bindings of a decl: ``Assignment`` and ``App``-with-record
    statements whose ref names a field (e.g. ``policy { … }``).  Returns a dict
    fieldname -> value-prop, plus the set of binding names in source order."""
    from .resolve import _value_to_props
    bindings = {}
    order = []
    for st in decl.body:
        if isinstance(st, P.Assignment):
            bindings[st.target] = _value_to_props(st.value)
            order.append(st.target)
        elif isinstance(st, P.App) and st.record is not None and st.args is None \
                and len(st.ref.parts) == 1:
            # a named config block in field position, e.g. `policy { … }`
            name = st.ref.parts[0]
            bindings[name] = {"record": [_entry_to_props_safe(e) for e in st.record]}
            order.append(name)
    return bindings, order


def _entry_to_props_safe(e):
    from .resolve import _value_to_props
    if isinstance(e, P.Assignment):
        return {"assign": e.target, "op": e.op, "value": _value_to_props(e.value)}
    if isinstance(e, P.InheritStmt):
        return {"inherit": list(e.names)}
    return {"unknown": repr(e)}


# nested-record field schema for known structural sub-blocks (§ catalog):
_NESTED_SCHEMA = {
    ("fiber", "policy"): "fiberPolicy",
}


def _conform_decl(decl, schema: SchemaSpec, registry, smap, file, diags):
    decl_span = (decl.byteStart, decl.byteEnd, decl.line, decl.col)
    ds, de, dl, dc = decl_span
    bindings, order = _decl_field_bindings(decl)

    # Clause 1 — required fields present.
    for fname, f in schema.fields.items():
        if f.presence == "required" and fname not in bindings:
            _emit(diags, "E-CONFORM-MISSING-FIELD", file, decl_span, decl,
                  f"required field `{fname}` of schema `{schema.name}` is missing")

    # Clause 5 — unknown fields (closed schemas only).
    if not schema.open:
        for fname in order:
            if fname not in schema.fields:
                span = (smap.field_name_span(ds, de, fname) if smap else None) or decl_span
                _emit(diags, "E-CONFORM-UNKNOWN-FIELD", file, span, decl,
                      f"`{fname}` is not a declared field of closed schema "
                      f"`{schema.name}`")

    # Clauses 2 & 4 — field well-typedness + constraints, for bound fields.
    for fname, vprop in bindings.items():
        f = schema.fields.get(fname)
        if f is None:
            continue   # unknown (open schema) or already reported
        # nested structural sub-block (e.g. fiber policy) -> its own schema
        nested = _NESTED_SCHEMA.get((decl.kind, fname))
        if nested is not None and nested in registry.schemas and isinstance(vprop, dict) \
                and "record" in vprop:
            _conform_nested_record(vprop, registry.schemas[nested], registry, smap,
                                   file, diags, decl, fname, decl_span)
            continue
        if not _value_matches_type(vprop, f.type_text, registry):
            span = (smap.field_value_span(ds, de, fname) if smap else None) or decl_span
            _emit(diags, "E-CONFORM-TYPE", file, span, decl,
                  f"field `{fname}` of schema `{schema.name}` expects "
                  f"`{f.type_text}` but got {_render_vprop(vprop)}")
        # constraints (oneof / cmp / range / nonempty) on the value
        _check_field_constraints(vprop, f, decl, smap, file, diags, decl_span)
        # matches (regex) — applies to scalar string/path values
        for r in f.refinements:
            if r[0] == "matches":
                vspan = (smap.field_value_span(ds, de, fname) if smap else None) or decl_span
                _check_matches(vprop, r[1], f, decl, file, diags, vspan)


def _conform_nested_record(vprop, schema, registry, smap, file, diags, owner_decl, owner_field, decl_span):
    """Conformance of a nested record value (e.g. a fiber `policy { … }`) against
    its structural schema.  Diagnostics attribute to the owning decl/field."""
    entries = {e["assign"]: e["value"] for e in vprop.get("record", [])
               if isinstance(e, dict) and "assign" in e}
    ds, de, dl, dc = decl_span
    for fname, f in schema.fields.items():
        if f.presence == "required" and fname not in entries:
            _emit(diags, "E-CONFORM-MISSING-FIELD", file, decl_span, owner_decl,
                  f"required field `{fname}` of nested schema `{schema.name}` "
                  f"(in `{owner_field}`) is missing")
    if not schema.open:
        for fname in entries:
            if fname not in schema.fields:
                span = (smap.field_name_span(ds, de, fname) if smap else None) or decl_span
                _emit(diags, "E-CONFORM-UNKNOWN-FIELD", file, span, owner_decl,
                      f"`{fname}` is not a declared field of nested schema "
                      f"`{schema.name}` (in `{owner_field}`)")
    for fname, v in entries.items():
        f = schema.fields.get(fname)
        if f is None:
            continue
        if not _value_matches_type(v, f.type_text, registry):
            span = (smap.field_value_span(ds, de, fname) if smap else None) or decl_span
            _emit(diags, "E-CONFORM-TYPE", file, span, owner_decl,
                  f"field `{fname}` of nested schema `{schema.name}` expects "
                  f"`{f.type_text}` but got {_render_vprop(v)}")
        _check_field_constraints(v, f, owner_decl, smap, file, diags, decl_span)


# --------------------------------------------------------------------------- #
# Mesh node conformance + capability checks (§4)
# --------------------------------------------------------------------------- #

def _node_bindings(node_decl):
    from .resolve import _value_to_props
    bindings = {}
    order = []
    for st in node_decl.body:
        if isinstance(st, P.Assignment):
            bindings[st.target] = _value_to_props(st.value)
            order.append(st.target)
    return bindings, order


def _grant_ref_parts(vprop):
    """If a value-prop is a bare `domain.grant` ref, return (domain, grant)."""
    if isinstance(vprop, dict) and "ref" in vprop and "args" not in vprop and "record" not in vprop:
        parts = vprop["ref"].split(".")
        if len(parts) == 2:
            return parts[0], parts[1]
    return None


def _gather_node_grants(node_bindings):
    """Return list of (domain, grant) from a node's `capabilities` list value."""
    out = []
    caps = node_bindings.get("capabilities")
    if isinstance(caps, list):
        for e in caps:
            dg = _grant_ref_parts(e)
            if dg is not None:
                out.append(dg)
    return out


def _check_capability_refs(domain, grant, registry, file, span, decl, diags):
    cap = registry.caps.get(domain)
    if cap is None:
        _emit(diags, "E-CAP-UNKNOWN-DOMAIN", file, span, decl,
              f"unknown capability domain `{domain}` in `{domain}.{grant}`")
        return False
    if grant not in cap.grants:
        _emit(diags, "E-CAP-UNKNOWN-GRANT", file, span, decl,
              f"`{grant}` is not a declared grant of capability domain `{domain}`")
        return False
    return True


def _leq(cap: CapabilitySpec, a, b):
    """Is grant a <= grant b in this domain's attenuation order?"""
    return b in cap.leq.get(a, set([a]))


# --------------------------------------------------------------------------- #
# Generics (§5)
# --------------------------------------------------------------------------- #

def _check_generics(decl, registry, by_name_kind, smap, file, diags):
    decl_span = (decl.byteStart, decl.byteEnd, decl.line, decl.col)
    ds, de, dl, dc = decl_span
    bindings, _ = _decl_field_bindings(decl)

    if decl.kind == "catalog":
        # `from` must reference an `index` (§5.1: from : Index<T>).
        frm = bindings.get("from")
        dg = _ref_dotted(frm)
        if dg is not None:
            target_kind = _resolve_kind(dg, by_name_kind)
            if target_kind is not None and target_kind != "index":
                span = (smap.field_value_span(ds, de, "from") if smap else None) or decl_span
                _emit(diags, "E-GENERIC-INCONSISTENT", file, span, decl,
                      f"catalog `from` must target an `index` (Index<T>); "
                      f"`{dg}` is a `{target_kind}`")
            # item-type agreement: if the catalog declares its own `schema` item
            # type and the index declares one too, they must match.
            cat_item = _item_schema_of(bindings)
            idx_decl = by_name_kind.get(("index", _last(dg)))
            if cat_item is not None and idx_decl is not None:
                idx_bindings, _ = _decl_field_bindings(idx_decl)
                idx_item = _item_schema_of(idx_bindings)
                if idx_item is not None and idx_item != cat_item:
                    span = (smap.field_value_span(ds, de, "from") if smap else None) or decl_span
                    _emit(diags, "E-GENERIC-INCONSISTENT", file, span, decl,
                          f"catalog item type `{cat_item}` disagrees with index "
                          f"`{_last(dg)}` item type `{idx_item}`")

    if decl.kind == "fiber":
        # input/output are bound (I/O); where input references a stream and the
        # fiber also names an item schema, no further ground type is available in
        # the examples to contradict — so we only verify the references resolve to
        # a plausible kind (no false positives).  A mismatching `input` that
        # points at a non-stream/non-index source is left to conformance.
        pass


def _ref_dotted(vprop):
    if isinstance(vprop, dict) and "ref" in vprop and "args" not in vprop and "record" not in vprop:
        return vprop["ref"]
    return None


def _last(dotted):
    return dotted.split(".")[-1]


def _resolve_kind(dotted, by_name_kind):
    """If a dotted ref `<kind>.<name>` or bare `<name>` names an in-file decl,
    return that decl's kind; else None (external/built-in)."""
    parts = dotted.split(".")
    if len(parts) == 2 and parts[0] in P._KIND_SET:
        if (parts[0], parts[1]) in by_name_kind:
            return parts[0]
        return None
    if len(parts) == 1:
        for (k, nm) in by_name_kind:
            if nm == parts[0]:
                return k
    return None


def _item_schema_of(bindings):
    """The item-schema name a catalog/index declares via `schema = schema.X`."""
    s = bindings.get("schema")
    d = _ref_dotted(s)
    if d is not None:
        return _last(d)
    return None


# --------------------------------------------------------------------------- #
# Top-level: build registry, run all checks
# --------------------------------------------------------------------------- #

def load_builtins(builtins_path=None):
    """Parse the built-in catalog into (items, source, filename).  This is the
    checker's ONLY IO."""
    path = builtins_path or default_builtins_path()
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    items = parse_source(src, path)
    return items, src, path


def check_file(path, builtins_path=None, builtins_cache=None):
    """Read a ``.vaked`` file and return its sorted list of :class:`Diagnostic`."""
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    return check_source(src, path, builtins_path=builtins_path,
                        builtins_cache=builtins_cache)


def check_source(src, filename, builtins_path=None, builtins_cache=None):
    """Check Vaked ``src`` and return a sorted list of :class:`Diagnostic`.

    ``builtins_cache`` may be a pre-parsed ``(items, src, filename)`` tuple from
    :func:`load_builtins` to avoid re-reading the catalog (keeps the function
    pure when the caller supplies the catalog)."""
    if builtins_cache is None:
        builtins_cache = load_builtins(builtins_path)
    b_items, b_src, b_file = builtins_cache

    # Stage 3 — elaborate: assemble the schema/capability registry.
    registry = _Registry()
    _load_decls_into(registry, b_items, b_file)          # built-ins first

    items = parse_source(src, filename)
    _load_decls_into(registry, items, filename)          # user decls override

    # Source maps for span resolution (built-ins + the file under check).
    smaps = {b_file: _SourceMap(b_src, b_file), filename: _SourceMap(src, filename)}

    def smap_for(f):
        return smaps.get(f)

    diags = []

    # Stage 4a — load-time well-formedness of EVERY schema & capability in scope
    # (built-in + user).  Per 0011 §6.4a these are reported against the decl.
    for spec in sorted(registry.schemas.values(), key=lambda s: (s.origin_file, s.name)):
        _check_schema_wellformed(spec, smap_for, diags)
    for spec in sorted(registry.caps.values(), key=lambda c: (c.origin_file, c.domain)):
        _check_capability_wellformed(spec, smap_for, diags)

    # Index in-file decls by (kind, name) for generics resolution.
    by_name_kind = {}
    for it in items:
        if isinstance(it, P.Decl):
            by_name_kind[(it.kind, it.name)] = it

    smap = smaps[filename]

    # Stage 4b/4c/4d — walk every in-file declaration.
    for it in items:
        if isinstance(it, P.Decl):
            _check_decl_tree(it, registry, by_name_kind, smap, filename, diags)

    diags.sort(key=lambda d: d.sort_key())
    return diags


def _check_decl_tree(decl, registry, by_name_kind, smap, file, diags):
    """Check ``decl`` and recurse into nested declarations / mesh nodes."""
    kind = decl.kind

    # Conformance for kinds that have a schema (skip the meta-kinds themselves).
    if kind not in ("schema", "capability"):
        schema = registry.schemas.get(kind)
        if schema is not None:
            _conform_decl(decl, schema, registry, smap, file, diags)
        _check_generics(decl, registry, by_name_kind, smap, file, diags)

    # Mesh: check each node body against meshNode, validate capability refs, and
    # enforce attenuation on delegation (`->`) edges.
    if kind == "mesh":
        _check_mesh(decl, registry, smap, file, diags)

    # Recurse into nested declarations (e.g. a runtime's index/stream/fiber/…).
    for st in decl.body:
        if isinstance(st, P.Decl):
            _check_decl_tree(st, registry, by_name_kind, smap, file, diags)


def _check_mesh(mesh_decl, registry, smap, file, diags):
    mesh_schema = registry.schemas.get("meshNode")
    node_grants = {}        # node name -> list[(domain, grant)]
    node_decls = {}
    ds, de, dl, dc = (mesh_decl.byteStart, mesh_decl.byteEnd, mesh_decl.line, mesh_decl.col)

    for st in mesh_decl.body:
        if isinstance(st, P.NodeDecl):
            node_decls[st.name] = st
            bindings, order = _node_bindings(st)
            nspan = (st.byteStart, st.byteEnd, st.line, st.col)
            # conform the node body against meshNode
            if mesh_schema is not None:
                _conform_node(st, mesh_schema, registry, smap, file, diags, nspan)
            # validate + collect capability grants
            grants = []
            caps = bindings.get("capabilities")
            if isinstance(caps, list):
                for e in caps:
                    dg = _grant_ref_parts(e)
                    if dg is None:
                        continue
                    dom, gr = dg
                    cspan = (smap.field_value_span(st.byteStart, st.byteEnd, "capabilities")
                             if smap else None) or nspan
                    if _check_capability_refs(dom, gr, registry, file, cspan, st, diags):
                        grants.append((dom, gr))
            node_grants[st.name] = grants

    # Attenuation on delegation edges (§4.4): for each `a -> b`, every grant the
    # receiver holds must be ≤ some grant the sender holds in the same domain.
    for st in mesh_decl.body:
        if isinstance(st, P.Edge):
            refs = st.refs
            for a_ref, b_ref in zip(refs, refs[1:]):
                sender = a_ref.parts[0] if len(a_ref.parts) == 1 else None
                receiver = b_ref.parts[0] if len(b_ref.parts) == 1 else None
                if sender not in node_grants or receiver not in node_grants:
                    continue   # an endpoint is external / unknown ⇒ no grant-set
                _check_edge_attenuation(
                    sender, receiver, node_grants[sender], node_grants[receiver],
                    a_ref, b_ref, registry, file, mesh_decl, diags)


def _conform_node(node_decl, schema, registry, smap, file, diags, nspan):
    bindings, order = _node_bindings(node_decl)
    ns, ne, nl, nc = nspan
    for fname, f in schema.fields.items():
        if f.presence == "required" and fname not in bindings:
            _emit(diags, "E-CONFORM-MISSING-FIELD", file, nspan, f"node {node_decl.name}",
                  f"required field `{fname}` of schema `{schema.name}` is missing")
    if not schema.open:
        for fname in order:
            if fname not in schema.fields:
                span = (smap.field_name_span(ns, ne, fname) if smap else None) or nspan
                _emit(diags, "E-CONFORM-UNKNOWN-FIELD", file, span, f"node {node_decl.name}",
                      f"`{fname}` is not a declared field of closed schema "
                      f"`{schema.name}`")
    for fname, vprop in bindings.items():
        f = schema.fields.get(fname)
        if f is None:
            continue
        if not _value_matches_type(vprop, f.type_text, registry):
            span = (smap.field_value_span(ns, ne, fname) if smap else None) or nspan
            _emit(diags, "E-CONFORM-TYPE", file, span, f"node {node_decl.name}",
                  f"field `{fname}` of schema `{schema.name}` expects "
                  f"`{f.type_text}` but got {_render_vprop(vprop)}")
        _check_field_constraints(vprop, f, f"node {node_decl.name}", smap, file, diags, nspan)


def _check_edge_attenuation(sender, receiver, s_grants, r_grants, a_ref, b_ref,
                            registry, file, mesh_decl, diags):
    # span: the edge, from the sender ref start to the receiver ref end.
    edge_span = (a_ref.byteStart, b_ref.byteEnd, a_ref.line, a_ref.col)
    s_by_dom = {}
    for (dom, gr) in s_grants:
        s_by_dom.setdefault(dom, []).append(gr)
    for (dom, gr) in r_grants:
        cap = registry.caps.get(dom)
        if cap is None:
            continue   # unknown domain already reported
        sender_grants = s_by_dom.get(dom, [])
        # receiver grant gr must be <= some sender grant in this domain
        ok = any(_leq(cap, gr, sg) for sg in sender_grants)
        if not ok:
            held = ", ".join("%s.%s" % (dom, g) for g in sender_grants) or "(none)"
            _emit(diags, "E-CAP-ATTENUATION", file, edge_span, mesh_decl,
                  f"delegation `{sender} -> {receiver}` escalates authority: "
                  f"receiver holds `{dom}.{gr}` but sender holds {held} "
                  f"(receiver's grant must be ≤ the sender's in domain `{dom}`)")
````

## File: vakedc/emit.py
````python
#!/usr/bin/env python3
"""vakedc.emit — deterministic serialization of an LPG.

(a) ``to_canonical_json(graph) -> str`` — stable everywhere: nodes sorted by id,
    edges by (from, label, to), a fixed key order on every object, compact
    separators, ``ensure_ascii=False``, trailing newline. Byte-identical across
    runs (no wall-clock, no set iteration order).

(b) ``to_sqlite(graph, path)`` — tables ``nodes`` and ``edges`` with provenance
    columns; ``canonical_dump(path) -> str`` SELECTs in canonical order for the
    determinism tests (not file bytes — SQLite page layout is not byte-stable).
"""

from __future__ import annotations

import json
import sqlite3

# Fixed key order for every emitted object (canonicality).
_NODE_KEYS = ("id", "kind", "name", "labels", "props", "provenance")
_EDGE_KEYS = ("from", "to", "label", "props")
_PROV_KEYS = ("file", "decl", "span")
_SPAN_KEYS = ("byteStart", "byteEnd", "line", "col")


def _canon_span(span: dict) -> dict:
    return {k: span[k] for k in _SPAN_KEYS}


def _canon_prov(prov):
    if prov is None:
        return None
    return {
        "file": prov["file"],
        "decl": prov["decl"],
        "span": _canon_span(prov["span"]),
    }


def _canon_node(nd: dict) -> dict:
    return {
        "id": nd["id"],
        "kind": nd["kind"],
        "name": nd["name"],
        "labels": nd["labels"],
        "props": _canon_value(nd["props"]),
        "provenance": _canon_prov(nd["provenance"]),
    }


def _canon_edge(e: dict) -> dict:
    return {
        "from": e["from"],
        "to": e["to"],
        "label": e["label"],
        "props": _canon_value(e["props"]),
    }


def _canon_value(v):
    """Recursively canonicalize prop dicts: sort object keys for stable output.

    Lists preserve order (source order is meaningful). Dict keys are sorted so the
    same logical graph always serializes identically regardless of insertion order.
    """
    if isinstance(v, dict):
        return {k: _canon_value(v[k]) for k in sorted(v.keys())}
    if isinstance(v, list):
        return [_canon_value(x) for x in v]
    return v


def to_canonical_json(graph) -> str:
    nodes = [_canon_node(n.as_dict()) for n in graph.nodes_sorted()]
    edges = [_canon_edge(e.as_dict()) for e in graph.edges_sorted()]
    doc = {"version": 1, "source": graph.source_file,
           "nodes": nodes, "edges": edges}
    return json.dumps(doc, separators=(",", ":"), ensure_ascii=False) + "\n"


# --------------------------------------------------------------------------- #
# SQLite
# --------------------------------------------------------------------------- #

_SCHEMA = """
CREATE TABLE nodes (
    id         TEXT PRIMARY KEY,
    kind       TEXT NOT NULL,
    name       TEXT NOT NULL,
    labels     TEXT NOT NULL,
    props      TEXT NOT NULL,
    prov_file  TEXT,
    prov_decl  TEXT,
    byte_start INTEGER,
    byte_end   INTEGER,
    line       INTEGER,
    col        INTEGER
);
CREATE TABLE edges (
    src   TEXT NOT NULL,
    dst   TEXT NOT NULL,
    label TEXT NOT NULL,
    props TEXT NOT NULL
);
"""


def _dump_json(v) -> str:
    return json.dumps(_canon_value(v), separators=(",", ":"), ensure_ascii=False)


def to_sqlite(graph, path) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.executescript(_SCHEMA)
        for n in graph.nodes_sorted():
            prov = n.provenance
            if prov is not None:
                pf, pd = prov.file, prov.decl
                bs, be, ln, co = (prov.span.byteStart, prov.span.byteEnd,
                                  prov.span.line, prov.span.col)
            else:
                pf = pd = None
                bs = be = ln = co = None
            conn.execute(
                "INSERT INTO nodes (id,kind,name,labels,props,prov_file,prov_decl,"
                "byte_start,byte_end,line,col) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (n.id, n.kind, n.name, _dump_json(n.labels), _dump_json(n.props),
                 pf, pd, bs, be, ln, co),
            )
        for e in graph.edges_sorted():
            conn.execute(
                "INSERT INTO edges (src,dst,label,props) VALUES (?,?,?,?)",
                (e.source, e.target, e.label, _dump_json(e.props)),
            )
        conn.commit()
    finally:
        conn.close()


def canonical_dump(path) -> str:
    """Deterministic textual dump of a SQLite graph DB (canonical SELECT order)."""
    conn = sqlite3.connect(path)
    try:
        out = []
        cur = conn.execute(
            "SELECT id,kind,name,labels,props,prov_file,prov_decl,"
            "byte_start,byte_end,line,col FROM nodes ORDER BY id"
        )
        for row in cur.fetchall():
            out.append("NODE\t" + "\t".join("" if v is None else str(v)
                                            for v in row))
        cur = conn.execute(
            "SELECT src,label,dst,props FROM edges ORDER BY src,label,dst,props"
        )
        for row in cur.fetchall():
            out.append("EDGE\t" + "\t".join(str(v) for v in row))
        return "\n".join(out) + "\n"
    finally:
        conn.close()
````

## File: vakedc/graph.py
````python
#!/usr/bin/env python3
"""vakedc.graph — the Labeled Property Graph (LPG) model.

A parsed Vaked file instantiates an LPG: one :class:`GraphNode` per declaration
(``decl`` / ``node`` / ``capability`` / external stub), with provenance attached
at instantiation, and :class:`GraphEdge` relationships derived by the resolver.

Node id is stable and path-derived:  ``<filename>#<outer>/<inner>`` — the file's
basename, then the slash-joined chain of enclosing decl names (top-level decls
have no inner segment, e.g. ``operator-field.vaked#operator-field``). External
stub nodes use ``external:<head-path>`` as their id.

Provenance ``decl`` string = ``"<kind> <name>"`` (e.g. ``"fiber mediaCompress"``),
matching docs/language/0012-lowering.md §6.2 and the provenance.json fixture.
Span = 0012 §6.2 byte-exact: ``byteStart`` at the decl's leading keyword,
``byteEnd`` exclusive one past the closing ``}``; ``line``/``col`` 1-based.
"""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field


@dataclass
class Span:
    byteStart: int
    byteEnd: int
    line: int
    col: int

    def as_dict(self):
        return {
            "byteStart": self.byteStart,
            "byteEnd": self.byteEnd,
            "line": self.line,
            "col": self.col,
        }


@dataclass
class Provenance:
    file: str
    decl: str               # "<kind> <name>"
    span: Span

    def as_dict(self):
        return {"file": self.file, "decl": self.decl, "span": self.span.as_dict()}


@dataclass
class GraphNode:
    id: str
    kind: str
    name: str
    labels: list
    props: dict
    provenance: "Provenance | None"

    def as_dict(self):
        prov = self.provenance.as_dict() if self.provenance is not None else None
        return {
            "id": self.id,
            "kind": self.kind,
            "name": self.name,
            "labels": list(self.labels),
            "props": self.props,
            "provenance": prov,
        }


@dataclass
class GraphEdge:
    source: str             # 'from' node id
    target: str             # 'to' node id
    label: str
    props: dict = dc_field(default_factory=dict)

    def as_dict(self):
        return {
            "from": self.source,
            "to": self.target,
            "label": self.label,
            "props": self.props,
        }


class Graph:
    """A Labeled Property Graph: id-keyed nodes plus a list of edges."""

    def __init__(self, source_file: str):
        self.source_file = source_file
        self._nodes: "dict[str, GraphNode]" = {}
        self._edges: "list[GraphEdge]" = []

    # --- nodes ----------------------------------------------------------- #

    def add_node(self, node: GraphNode) -> GraphNode:
        if node.id in self._nodes:
            return self._nodes[node.id]
        self._nodes[node.id] = node
        return node

    def get_node(self, node_id: str) -> "GraphNode | None":
        return self._nodes.get(node_id)

    def has_node(self, node_id: str) -> bool:
        return node_id in self._nodes

    def ensure_external(self, head_path: str) -> GraphNode:
        """One external stub node per distinct head path (kind 'external')."""
        node_id = f"external:{head_path}"
        existing = self._nodes.get(node_id)
        if existing is not None:
            return existing
        node = GraphNode(
            id=node_id,
            kind="external",
            name=head_path,
            labels=["external"],
            props={"external": True},
            provenance=None,
        )
        self._nodes[node_id] = node
        return node

    # --- edges ----------------------------------------------------------- #

    def add_edge(self, edge: GraphEdge) -> None:
        self._edges.append(edge)

    # --- views ----------------------------------------------------------- #

    @property
    def nodes(self) -> "list[GraphNode]":
        return list(self._nodes.values())

    @property
    def edges(self) -> "list[GraphEdge]":
        return list(self._edges)

    def nodes_sorted(self) -> "list[GraphNode]":
        return sorted(self._nodes.values(), key=lambda nd: nd.id)

    def edges_sorted(self) -> "list[GraphEdge]":
        # canonical order: (from, label, to), then a stable tiebreak on props
        return sorted(
            self._edges,
            key=lambda e: (e.source, e.label, e.target, _stable_props_key(e.props)),
        )


def _stable_props_key(props: dict) -> str:
    import json
    return json.dumps(props, sort_keys=True, ensure_ascii=False)


def node_id(filename: str, chain: "list[str]") -> str:
    """Stable, path-derived node id: ``<filename>#<outer>/<inner>/...``."""
    return f"{filename}#{'/'.join(chain)}"
````

## File: vakedc/lexer.py
````python
#!/usr/bin/env python3
"""vakedc.lexer — mode-switching tokenizer for the Vaked language (.vaked).

Standalone (does NOT import tests/spec). The lexical rules here are the same ones
the from-EBNF recognizer proves correct (dotted-ref vs path, regex-only-after-
``matches``, NEWLINE suppression inside open ``(``/``[``, duration/bytes units,
``#`` comments, ``${ref}`` string interpolation), re-implemented so every token
also carries an exact byte span ``{byteStart, byteEnd, line, col}`` (1-based
line/col) — the substrate 0011's checker and 0012's lowering operate on.

NFC gate
--------
Source must be Unicode-NFC-normalized; non-NFC source is rejected with a source-
mapped :class:`VakedLexError`. The pinned Unicode version is :data:`PINNED_UNICODE`;
when the runtime's ``unicodedata.unidata_version`` differs, ONE warning is emitted
to stderr (mismatch is a warning, never an error — mirrors the .hcplang 15.1.0 pin).

Token kinds
-----------
    IDENT STRING NUMBER DURATION BYTES PATH REGEX OP NEWLINE EOF
"""

from __future__ import annotations

import sys
import unicodedata
from dataclasses import dataclass

# Pinned Unicode version (matches the .hcplang pin discipline). A runtime whose
# unicodedata.unidata_version differs produces ONE stderr warning, not an error.
PINNED_UNICODE = "15.1.0"

_warned_unicode_mismatch = False


def _maybe_warn_unicode_version() -> None:
    global _warned_unicode_mismatch
    if _warned_unicode_mismatch:
        return
    _warned_unicode_mismatch = True
    runtime = unicodedata.unidata_version
    if runtime != PINNED_UNICODE:
        print(
            f"vakedc: warning: Unicode data version mismatch "
            f"(pinned {PINNED_UNICODE}, runtime {runtime}); "
            f"NFC normalization may differ for edge-case codepoints.",
            file=sys.stderr,
        )


class VakedLexError(Exception):
    """Lexical error carrying a source-mapped (file:line:col) message."""

    def __init__(self, msg: str, file: str, line: int, col: int):
        super().__init__(f"{file}:{line}:{col} — {msg}")
        self.msg = msg
        self.file = file
        self.line = line
        self.col = col


@dataclass
class Token:
    kind: str
    value: str
    byteStart: int
    byteEnd: int      # exclusive
    line: int         # 1-based, of byteStart
    col: int          # 1-based, of byteStart

    def matches_literal(self, text: str) -> bool:
        """True if this token equals the grammar terminal ``text``.

        IDENT/OP literals match by value; quote/number/etc. are matched by kind
        elsewhere in the parser, so a bare literal never matches them here.
        """
        if self.kind == "IDENT" or self.kind == "OP":
            return text == self.value
        return False


# Multi-char operators, longest first ('->' beats '-', '<=' beats '<', ...).
_MULTI_OPS = ("->", "<=", ">=", "..", "?=")
_SINGLE_OPS = set("=<>.;:,@()[]{}|")

_DURATION_UNITS = ("ns", "us", "ms", "s", "m", "h", "d")
_BYTE_UNITS = ("B", "KB", "MB", "GB", "TB")


def _is_letter(c: str) -> bool:
    return ("a" <= c <= "z") or ("A" <= c <= "Z")


def _is_digit(c: str) -> bool:
    return "0" <= c <= "9"


def _is_ident_part(c: str) -> bool:
    return _is_letter(c) or _is_digit(c) or c in "_-"


def _is_path_char(c: str) -> bool:
    # path_char = letter | digit | "/" | "_" | "-" | "."
    return _is_letter(c) or _is_digit(c) or c in "/_-."


def _match_unit(rest: str, units) -> "str | None":
    best = None
    for u in units:
        if rest.startswith(u) and (best is None or len(u) > len(best)):
            best = u
    return best


def tokenize(src: str, filename: str = "<vaked>") -> "list[Token]":
    """Tokenize ``src`` into a list of :class:`Token` ending with an EOF sentinel.

    Raises :class:`VakedLexError` on a lexical error or non-NFC source.
    """
    _maybe_warn_unicode_version()

    # NFC gate: reject non-normalized source up front, source-mapped to the first
    # offending character so the message points at something actionable.
    if not unicodedata.is_normalized("NFC", src):
        nfc = unicodedata.normalize("NFC", src)
        # locate first divergence for a precise span
        line = 1
        col = 1
        limit = min(len(src), len(nfc))
        i = 0
        while i < limit and src[i] == nfc[i]:
            if src[i] == "\n":
                line += 1
                col = 1
            else:
                col += 1
            i += 1
        raise VakedLexError(
            "source is not Unicode-NFC-normalized (normalize the file to NFC)",
            filename, line, col,
        )

    toks: "list[Token]" = []
    i = 0
    n = len(src)
    # Precompute the byte offset of each character index so byte spans are exact
    # for multi-byte UTF-8 (e.g. inside strings). off[k] = byte offset of src[k].
    off = [0] * (n + 1)
    acc = 0
    for k in range(n):
        off[k] = acc
        acc += len(src[k].encode("utf-8"))
    off[n] = acc

    line = 1
    col = 1
    group_depth = 0          # nesting of '(' and '[' (suppresses NEWLINE)
    pending_newline = False  # a NEWLINE is queued but not yet emitted
    pending_nl_pos = (0, 1, 1)  # (charidx, line, col) of the queued newline site

    def last_significant():
        return toks[-1] if toks else None

    def advance(s: str):
        nonlocal line, col
        for ch in s:
            if ch == "\n":
                line += 1
                col = 1
            else:
                col += 1

    def emit(kind: str, value: str, ci_start: int, ci_end: int,
             tline: int, tcol: int):
        nonlocal pending_newline
        if pending_newline:
            if toks and toks[-1].kind != "NEWLINE":
                pidx, pline, pcol = pending_nl_pos
                toks.append(Token("NEWLINE", "\\n", off[pidx], off[pidx],
                                  pline, pcol))
            pending_newline = False
        toks.append(Token(kind, value, off[ci_start], off[ci_end], tline, tcol))

    while i < n:
        c = src[i]
        tline, tcol = line, col
        ci = i

        # ---- whitespace (spaces / tabs / CR) -----------------------------
        if c in " \t\r":
            advance(c)
            i += 1
            continue

        # ---- newline -----------------------------------------------------
        if c == "\n":
            if group_depth == 0 and not pending_newline:
                pending_newline = True
                pending_nl_pos = (i, line, col)
            advance(c)
            i += 1
            continue

        # ---- comment '#' to EOL (discarded) ------------------------------
        if c == "#":
            j = i
            while j < n and src[j] != "\n":
                j += 1
            advance(src[i:j])
            i = j
            continue

        # ---- string with ${ref} interpolation ----------------------------
        if c == '"':
            j = i + 1
            buf = ['"']
            closed = False
            while j < n:
                ch = src[j]
                if ch == "\\":
                    if j + 1 >= n:
                        raise VakedLexError("unterminated escape in string",
                                            filename, tline, tcol)
                    buf.append(src[j:j + 2])
                    j += 2
                    continue
                if ch == '"':
                    buf.append('"')
                    j += 1
                    closed = True
                    break
                if ch == "\n":
                    raise VakedLexError("unterminated string (newline in string)",
                                        filename, tline, tcol)
                # ${ref} interpolation is consumed verbatim into the STRING token;
                # the `interp` production is recognized lexically (opaque to parser).
                buf.append(ch)
                j += 1
            if not closed:
                raise VakedLexError("unterminated string", filename, tline, tcol)
            value = "".join(buf)
            advance(src[i:j])
            emit("STRING", value, ci, j, tline, tcol)
            i = j
            continue

        # ---- regex literal /.../  (only right after `matches`) -----------
        if c == "/":
            ls = last_significant()
            if ls is not None and ls.kind == "IDENT" and ls.value == "matches":
                j = i + 1
                buf = ["/"]
                closed = False
                while j < n:
                    ch = src[j]
                    if ch == "\\":
                        if j + 1 >= n:
                            raise VakedLexError("unterminated regex escape",
                                                filename, tline, tcol)
                        buf.append(src[j:j + 2])
                        j += 2
                        continue
                    if ch == "\n":
                        raise VakedLexError("unterminated regex (newline)",
                                            filename, tline, tcol)
                    if ch == "/":
                        buf.append("/")
                        j += 1
                        closed = True
                        break
                    buf.append(ch)
                    j += 1
                if not closed:
                    raise VakedLexError("unterminated regex literal",
                                        filename, tline, tcol)
                value = "".join(buf)
                advance(src[i:j])
                emit("REGEX", value, ci, j, tline, tcol)
                i = j
                continue
            raise VakedLexError(
                "unexpected '/' (regex literal is only valid after `matches`)",
                filename, tline, tcol)

        # ---- path: '.' in leading position followed by '/' or letter -----
        if c == ".":
            ls = last_significant()
            # '.' glued to a preceding value token is a DOT (dotted ref a.b);
            # otherwise a leading './' or '.<letter>' begins a PATH; ".." is OP.
            glued = ls is not None and ls.kind in (
                "IDENT", "NUMBER", "STRING", "DURATION", "BYTES", "REGEX"
            ) and ls.byteEnd == off[ci]
            if i + 1 < n and src[i + 1] == "." and not glued:
                advance("..")
                emit("OP", "..", ci, i + 2, tline, tcol)
                i += 2
                continue
            if not glued and i + 1 < n and (src[i + 1] == "/"
                                            or _is_letter(src[i + 1])):
                j = i + 1
                while j < n and _is_path_char(src[j]):
                    j += 1
                value = src[i:j]
                advance(value)
                emit("PATH", value, ci, j, tline, tcol)
                i = j
                continue
            # else falls through to OP handling below ('.' as DOT)

        # ---- multi-char operators ----------------------------------------
        matched_op = None
        for op in _MULTI_OPS:
            if src.startswith(op, i):
                matched_op = op
                break
        if matched_op:
            advance(matched_op)
            emit("OP", matched_op, ci, i + len(matched_op), tline, tcol)
            i += len(matched_op)
            continue

        # ---- single-char operators ---------------------------------------
        if c in _SINGLE_OPS:
            if c == "(" or c == "[":
                group_depth += 1
            elif c == ")" or c == "]":
                if group_depth > 0:
                    group_depth -= 1
            advance(c)
            emit("OP", c, ci, i + 1, tline, tcol)
            i += 1
            continue

        # ---- numbers / durations / bytes ---------------------------------
        if _is_digit(c) or (c == "-" and i + 1 < n and _is_digit(src[i + 1])):
            j = i
            if src[j] == "-":
                j += 1
            while j < n and _is_digit(src[j]):
                j += 1
            is_float = False
            if j < n and src[j] == "." and j + 1 < n and _is_digit(src[j + 1]):
                is_float = True
                j += 1
                while j < n and _is_digit(src[j]):
                    j += 1
            if not is_float:
                rest = src[j:]
                unit = _match_unit(rest, _BYTE_UNITS)
                if unit and not (j + len(unit) < n
                                 and _is_ident_part(src[j + len(unit)])):
                    value = src[i:j] + unit
                    advance(value)
                    emit("BYTES", value, ci, j + len(unit), tline, tcol)
                    i = j + len(unit)
                    continue
                unit = _match_unit(rest, _DURATION_UNITS)
                if unit and not (j + len(unit) < n
                                 and _is_ident_part(src[j + len(unit)])):
                    value = src[i:j] + unit
                    advance(value)
                    emit("DURATION", value, ci, j + len(unit), tline, tcol)
                    i = j + len(unit)
                    continue
            value = src[i:j]
            advance(value)
            emit("NUMBER", value, ci, j, tline, tcol)
            i = j
            continue

        # ---- identifiers --------------------------------------------------
        if _is_letter(c):
            j = i
            while j < n and _is_ident_part(src[j]):
                j += 1
            value = src[i:j]
            advance(value)
            emit("IDENT", value, ci, j, tline, tcol)
            i = j
            continue

        raise VakedLexError(f"unexpected character {c!r}", filename, tline, tcol)

    # trailing NEWLINE / trim, then EOF sentinel
    if toks and toks[-1].kind == "NEWLINE":
        toks.pop()
    toks.append(Token("EOF", "<eof>", off[n], off[n], line, col))
    return toks
````

## File: vakedc/lower.py
````python
#!/usr/bin/env python3
"""vakedc.lower — the 0012 lowering pass: validated graph -> artifacts.

This module implements `docs/language/0012-lowering.md` (the normative spec). It
turns a *validated* typed semantic graph (the output of :mod:`vakedc.check`) into
the boring, inspectable artifacts Vaked owns plus the Nix spine that wires them,
together with a decl-level provenance manifest.

Purity / totality / hermeticity (0012 §2). Every emitter here is a **pure,
total, hermetic** function of ``(graph, nodes)``:

  * No IO of any kind (no file reads/writes, no sockets, no subprocesses), no
    wall-clock, no randomness, no environment/locale/hostname. The only IO in
    the whole pipeline is the CLI write layer in :mod:`vakedc.__main__`, which
    writes the ``Files`` this module returns. (0012 §2.3, §3.2.1)
  * Deterministic: the same graph yields byte-identical artifacts. All ordering
    is by a stable graph-derived key — declaration source order for top-level
    decls, the fixed structural layout order for the flake spine, lexicographic
    order for the provenance ``artifacts`` map. No hash-map iteration order.
    (0012 §2.1, §3.2.2)
  * No graph mutation, no cross-emitter state, no re-checking. (0012 §3.2.3-.5)

Emitter interface (0012 §3.1)::

    emit : (graph, nodes) -> (files, provenance_entries)
      files               : dict[str path -> str | bytes]   (rooted at the out tree)
      provenance_entries  : list[ProvEntry]                 (one per artifact/region)

Registry + selection (0012 §3.3/§3.4):

  * ``nix.spine`` ALWAYS runs (every runtime lowers to a flake + NixOS module).
  * ``docs.runtime`` runs on presence of the ``runtime`` node (unconditional).
  * Direct emitters are selected by declared ``emit`` targets / fiber presence:
      - a ``fiber`` selects ``zig.daemoncfg`` (a fiber has no ``emit`` field; it
        is selected by presence under the runtime, 0012 §3.4 note);
      - an ``index`` whose ``emit`` contains ``catalog.jsonl`` selects
        ``catalog.jsonl``;
      - an ``index`` whose ``emit`` contains ``nix.derivation`` selects
        ``crabcc.index`` (the derivation lives in the spine, but it contributes
        a distinct provenance entry, 0012 §5.3a).
  * Deferred targets (``ebpf.policy`` / ``otel.config`` / ``systemd.units`` /
    ``surface.launcher``) are inert registry slots that emit nothing (0012 §7).
    The surface launcher still surfaces in the spine as the §7 deferred no-op
    *stub app* (``apps.<system>.<surface>``), derived from nothing but the
    surface decl name.

inputsHash — the per-region projection (0012 §6.2). ``inputsHash`` is
``"sha256-" + sha256(canonical_projection_json).hexdigest()`` where the
*projection* is the emitter's resolved inputs for that region. The canonical
projection JSON is produced by :func:`_canonical_projection_json` (sorted keys,
compact separators, ``ensure_ascii=False``, no trailing newline). Per-region
projection definitions:

  ====================  =============================================================
  Region (provenance)   Projection (what the hash keys — "what the region was
                        projected from", 0012 §6.2)
  ====================  =============================================================
  spine nixosModules    the ``runtime`` node projection (its name + ``systems``).
  spine inputs.<idx>    the pinned source-index node projection (its resolved
                        identity + the ``trust = pinned`` digest).
  spine packages.crabcc the ``index`` node projection (the index whose ``emit``
                        contains ``nix.derivation``).
  spine packages.<eng>  the RESOLVED ENGINE identity + pin (NOT the fiber node):
                        ``{"engine": <name>, "package": "packages.<name>"}``. Its
                        owning decl is the ``fiber`` that references the engine,
                        but the hash keys the engine the fiber resolved to
                        (0012 §6.2: same decl, different projection).
  spine apps.<surface>  the ``surface`` node projection.
  docs.runtime header   the ``runtime`` node projection (same as nixosModules).
  docs.runtime section  the section's source node projection (each index /
                        stream / fiber / surface / parallel node).
  catalog.jsonl         the ``index`` node projection (the catalog's source index).
  zig.daemoncfg         the ``fiber`` node projection (the fiber the config runs).
  ====================  =============================================================

A node's projection is its kind/name plus the *canonicalized* graph props
(:func:`_node_projection`). Because the projection is a pure function of the
(immutable) graph node — or of the resolved engine identity — two regions that
project from the same node/engine carry the *same* ``inputsHash``, while two
regions that attribute to the same ``decl`` but project from different inputs
(the ``fiber`` config vs the ``engine`` package) carry *different* hashes —
exactly the 0012 §6.2 property.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
from dataclasses import dataclass, field as dc_field

from . import parser as P

# --------------------------------------------------------------------------- #
# Disclosed placeholders (values the BUILD, not lowering, would resolve).
#
# These mirror the source decl's own placeholder pins and the toolchain baseline
# rev. They are emitted verbatim — lowering invents no concrete data (0012
# §2.3/§2.4; the lowering README discloses each).
# --------------------------------------------------------------------------- #

# nixpkgs is emitted PINNED (0012 §4.1: never a moving channel ref). The 40-hex
# value is a disclosed placeholder standing in for the toolchain's pinned
# baseline rev (all-`b` = "baseline"). The committed flake.lock (produced at
# first build) records the real resolution.
NIXPKGS_BASELINE_REV = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

# The generated-header sentinel (0012 §6.1). The header carries NO timestamp.
_HEADER_FMT = "generated by Vaked from {file}:{decl} — do not edit"


def _header_file(source_file: str) -> str:
    """The source-file name as it appears in the §6.1 generated header: the
    *basename* (``operator-field.vaked``), never the full path the graph happens
    to be keyed by. The header names the source file; the manifest's
    ``sourceFile``/``span.file`` keep the caller-given path (0012 §6.2)."""
    return posixpath.basename(source_file.replace("\\", "/"))


def _header(source_file: str, decl: str) -> str:
    return _HEADER_FMT.format(file=_header_file(source_file), decl=decl)


# --------------------------------------------------------------------------- #
# Provenance entry
# --------------------------------------------------------------------------- #

@dataclass
class ProvEntry:
    """One provenance entry per emitted artifact or region (0012 §6.2).

    ``region`` is optional: absent ⇒ the entry covers the whole artifact.
    ``inputs_projection`` is the canonical projection object the ``inputsHash``
    is computed over (kept here so the driver can serialize the manifest with a
    real, reproducible hash — §2.1).
    """

    artifact: str                      # artifact path (relative to output root)
    region: "str | None"
    source_file: str
    decl: str                          # "<kind> <name>"
    span: object                       # vakedc.graph.Span
    emitter: str                       # registry target that produced it
    inputs_projection: object          # JSON-able projection (hashed for inputsHash)


# --------------------------------------------------------------------------- #
# Canonical JSON helpers
# --------------------------------------------------------------------------- #

def _canonical_value(v):
    """Recursively canonicalize a JSON-able value: dict keys sorted, list order
    preserved (source order is meaningful). Mirrors emit._canon_value so a node's
    projection is stable regardless of prop insertion order."""
    if isinstance(v, dict):
        return {k: _canonical_value(v[k]) for k in sorted(v.keys())}
    if isinstance(v, list):
        return [_canonical_value(x) for x in v]
    return v


def _canonical_projection_json(projection) -> str:
    """The canonical JSON string a projection is hashed over: sorted keys,
    compact separators, ``ensure_ascii=False``, no trailing newline. Deterministic
    (§2.1)."""
    return json.dumps(_canonical_value(projection),
                      separators=(",", ":"), ensure_ascii=False, sort_keys=True)


def inputs_hash(projection) -> str:
    """``"sha256-" + sha256(canonical_projection_json).hexdigest()`` (0012 §6.2)."""
    canonical = _canonical_projection_json(projection)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return "sha256-" + digest


def _node_projection(node) -> dict:
    """A node's projection: its kind + name + canonicalized props. A pure
    function of the (immutable) graph node, so re-lowering an unchanged graph
    yields the same hash (§2.1)."""
    return {
        "kind": node.kind,
        "name": node.name,
        "props": _canonical_value(node.props),
    }


def _engine_projection(engine_name: str) -> dict:
    """The resolved-engine projection for a fiber's ``packages.<engine>`` region
    (0012 §6.2). Keyed by the engine the fiber resolved to (its identity + the
    flake attribute name the build resolves to a store path), NOT the fiber node
    — so this region's hash differs from the fiber-config region's even though
    both attribute to the same ``fiber`` decl."""
    return {
        "engine": engine_name,
        "package": "packages." + engine_name,
    }


# --------------------------------------------------------------------------- #
# Small graph-projection utilities (pure reads of already-resolved props)
# --------------------------------------------------------------------------- #

def _children_of(graph, parent_id):
    """Direct ``contains`` children of a node, in source order (the resolver
    appends edges in declaration order, and we never reorder)."""
    out = []
    for e in graph.edges:
        if e.label == "contains" and e.source == parent_id:
            child = graph.get_node(e.target)
            if child is not None:
                out.append(child)
    return out


def _by_kind(nodes, kind):
    return [n for n in nodes if n.kind == kind]


def _ref(prop):
    """The dotted ref string of a ``{"ref": "..."}`` prop value, else None."""
    if isinstance(prop, dict) and "ref" in prop and "args" not in prop \
            and "record" not in prop:
        return prop["ref"]
    return None


def _lit(prop):
    """The literal value of a ``{"lit": ..., "value": ...}`` prop, else None."""
    if isinstance(prop, dict) and "lit" in prop:
        return prop.get("value")
    return None


def _str_list(prop):
    """A list of string-literal values from a list prop (e.g. ``views``,
    ``systems``, ``formats``)."""
    out = []
    if isinstance(prop, list):
        for x in prop:
            lv = _lit(x)
            if lv is not None:
                out.append(lv)
    return out


def _app_call(prop):
    """If ``prop`` is an application ``f(args...)`` (``github("x")`` /
    ``raw.github("a","b")``), return ``(ref, [arg-literals])`` else None."""
    if isinstance(prop, dict) and "ref" in prop and "args" in prop:
        args = [_lit(a) for a in prop["args"]]
        return prop["ref"], args
    return None


def _record_entries(prop):
    """The ``[{"assign","op","value"}]`` entries of a record/record-app prop
    (e.g. ``trust = pinned { commit = ...; sha256 = ... }``), as a dict
    ``name -> value-literal``. Preserves nothing but the scalar values we read."""
    out = {}
    rec = None
    if isinstance(prop, dict):
        rec = prop.get("record")
    if isinstance(rec, list):
        for e in rec:
            if isinstance(e, dict) and "assign" in e:
                out[e["assign"]] = _lit(e.get("value"))
    return out


# --------------------------------------------------------------------------- #
# Runtime decomposition — find the runtime node and its child decls.
# --------------------------------------------------------------------------- #

@dataclass
class _RuntimeView:
    runtime: object
    indexes: list = dc_field(default_factory=list)
    streams: list = dc_field(default_factory=list)
    fibers: list = dc_field(default_factory=list)
    surfaces: list = dc_field(default_factory=list)
    parallels: list = dc_field(default_factory=list)


def _runtime_view(graph) -> "_RuntimeView | None":
    runtimes = [n for n in graph.nodes_sorted() if n.kind == "runtime"]
    if not runtimes:
        return None
    runtime = runtimes[0]
    children = _children_of(graph, runtime.id)
    return _RuntimeView(
        runtime=runtime,
        indexes=_by_kind(children, "index"),
        streams=_by_kind(children, "stream"),
        fibers=_by_kind(children, "fiber"),
        surfaces=_by_kind(children, "surface"),
        parallels=_by_kind(children, "parallel"),
    )


def _index_emit_targets(index_node) -> list:
    """The dotted ``emit`` target refs of an index node (e.g.
    ``["catalog.jsonl", "catalog.sqlite", "nix.derivation"]``)."""
    out = []
    emit = index_node.props.get("emit")
    if isinstance(emit, list):
        for x in emit:
            r = _ref(x)
            if r is not None:
                out.append(r)
    return out


def _index_is_pinned(index_node) -> bool:
    """True when the index declares ``trust = pinned { … }`` (0012 §4.2)."""
    trust = index_node.props.get("trust")
    if isinstance(trust, dict) and trust.get("ref") == "pinned":
        return True
    return False


def _fiber_engine_name(fiber_node) -> "str | None":
    return _ref(fiber_node.props.get("engine"))


# --------------------------------------------------------------------------- #
# Emitter: nix.spine (ALWAYS) — flake.nix + the deferred surface stub.
# --------------------------------------------------------------------------- #

def _nix_source_slug(dotted: str) -> str:
    """``github("owner/repo")`` -> a deterministic input-name slug + the
    ``github:owner/repo`` url. Slug = the repo's last path segment, with
    ``.``/``_`` normalized to ``-`` so it is a valid Nix attr fragment."""
    repo = dotted.rsplit("/", 1)[-1]
    slug = repo.replace(".", "-").replace("_", "-")
    return slug


def emit_nix_spine(graph, nodes):
    """Emit ``flake.nix`` (0012 §4). ALWAYS runs. ``nodes`` is the whole runtime
    sub-tree. The flake outputs are a pure function of the runtime node and its
    children; the surface launcher is the §7 deferred no-op stub."""
    rv = _runtime_view(graph)
    if rv is None:
        return {}, []
    runtime = rv.runtime
    sf = graph.source_file
    rt_name = runtime.name

    # --- inputs: nixpkgs (pinned baseline) + one per source ---------------- #
    systems = _str_list(runtime.props.get("systems"))
    systems_nix = " ".join('"%s"' % s for s in systems)

    lines = []
    lines.append("# " + _header(sf, "runtime " + rt_name))
    lines.append("#")
    lines.append("# Expected-output fixture (no compiler exists yet) — see ./README.md and")
    lines.append("# docs/language/0012-lowering.md §4 (the Nix spine). Edits belong in the source")
    lines.append("# .vaked file, not here.")
    lines.append("{")
    lines.append('  description = "%s — generated by Vaked";' % rt_name)
    lines.append("")
    lines.append("  inputs = {")
    lines.append("    # nixpkgs is emitted pinned to the toolchain's baseline rev (0012 §4.1): an")
    lines.append("    # explicit rev, never a moving channel ref. The 40-hex value below is a")
    lines.append('    # disclosed placeholder (all-`b` = "baseline"; see ./README.md); the')
    lines.append("    # committed flake.lock (produced at first build) records the real resolution.")
    lines.append('    nixpkgs.url = "github:NixOS/nixpkgs/%s";' % NIXPKGS_BASELINE_REV)

    # For each index: emit its source inputs.
    for idx in rv.indexes:
        src = idx.props.get("source")
        if _index_is_pinned(idx):
            # raw.github(owner, file) + trust = pinned{commit, sha256}
            call = _app_call(src)
            owner = call[1][0] if call and call[1] else ""
            lines.append("")
            lines.append("    # index %s — trust = pinned { commit, sha256 } (0012 §4.2):" % idx.name)
            lines.append("    # commit pins the rev; sha256 is recorded as the lock entry's narHash so the")
            lines.append("    # build verifies the fetch. raw.github(...) => flake = false.")
            lines.append("    %s-src = {" % idx.name)
            lines.append('      url = "github:%s/<commit>"; # trust.pinned.commit' % owner)
            lines.append("      flake = false;")
            lines.append("    };")
        else:
            # source = [github(...), ...] (unpinned)
            sources = src if isinstance(src, list) else ([src] if src else [])
            lines.append("")
            lines.append("    # index %s — sources (unpinned; flake.lock records the resolved rev)." % idx.name)
            lines.append("    # 0012 §4.2: each index source becomes a flake input.")
            for s in sources:
                call = _app_call(s)
                if call is None:
                    continue
                owner_repo = call[1][0] if call[1] else ""
                slug = _nix_source_slug(owner_repo)
                lines.append('    %s-src-%s = { url = "github:%s"; flake = false; };'
                             % (idx.name, slug, owner_repo))
    lines.append("  };")
    lines.append("")
    lines.append("  outputs = { self, nixpkgs, ... }@inputs:")
    lines.append("    let")
    lines.append("      # runtime %s — systems = [%s]"
                 % (rt_name, ", ".join('"%s"' % s for s in systems)))
    lines.append("      systems = [ %s ];" % systems_nix)
    lines.append("      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f system);")
    lines.append("    in")
    lines.append("    {")
    lines.append("      # nixosModules.<runtime> — wires the OTP/Zig daemons and references the")
    lines.append("      # gen/ artifacts as installed files (0012 §4.3).")
    lines.append("      nixosModules.%s = import ./nixos/%s.nix {" % (rt_name, rt_name))
    lines.append("        # NixOS module fixture is described in 0012 §4.3; not emitted as a")
    lines.append("        # separate file in this fixture set (interface only).")
    lines.append("        inherit self;")
    lines.append("      };")
    lines.append("")
    lines.append("      packages = forAllSystems (system:")
    lines.append("        let pkgs = nixpkgs.legacyPackages.${system};")
    lines.append("        in {")

    # packages: engines (from fibers, source order), then crabcc index derivations.
    seen_engines = set()
    for fib in rv.fibers:
        eng = _fiber_engine_name(fib)
        if eng is None or eng in seen_engines:
            continue
        seen_engines.add(eng)
        lines.append("          # engine %s (fiber %s: engine = %s) — built Zig pkg."
                     % (eng, fib.name, eng))
        lines.append("          %s = pkgs.callPackage ./pkgs/%s.nix { };" % (eng, eng))
        lines.append("")

    for idx in rv.indexes:
        targets = _index_emit_targets(idx)
        if "nix.derivation" not in targets:
            continue
        normalize = _ref(idx.props.get("normalize"))
        cat_targets = [t for t in targets if t.startswith("catalog.")]
        emit_flags = " ".join("--emit " + t.split(".", 1)[1] for t in cat_targets)
        lines.append("          # index %s, emit ∋ nix.derivation (0012 §5.3a) — CrabCC index" % idx.name)
        lines.append("          # derivation; runs crabcc at build time over the pinned sources with")
        lines.append("          # normalize = %s." % normalize)
        lines.append("          %s-crabcc-index = pkgs.stdenv.mkDerivation {" % idx.name)
        lines.append('            pname = "%s-crabcc-index";' % idx.name)
        lines.append('            version = "0";')
        lines.append("            srcs = [")
        sources = idx.props.get("source")
        sources = sources if isinstance(sources, list) else ([sources] if sources else [])
        for s in sources:
            call = _app_call(s)
            if call is None:
                continue
            owner_repo = call[1][0] if call[1] else ""
            slug = _nix_source_slug(owner_repo)
            lines.append("              inputs.%s-src-%s" % (idx.name, slug))
        lines.append("            ];")
        lines.append("            nativeBuildInputs = [ pkgs.crabcc ];")
        lines.append("            buildPhase = ''")
        norm_arg = normalize.split(".", 1)[1] if normalize and "." in normalize else normalize
        lines.append("              # normalize = %s ; emit = %s"
                     % (normalize, ", ".join(cat_targets)))
        lines.append("              crabcc index build --normalize %s \\" % norm_arg)
        lines.append("                %s \\" % emit_flags)
        lines.append("                --out $out")
        lines.append("            '';")
        lines.append("          };")
    lines.append("        });")
    lines.append("")
    lines.append("      apps = forAllSystems (system:")
    lines.append("        let pkgs = nixpkgs.legacyPackages.${system};")
    lines.append("        in {")
    # surfaces -> deferred stub apps (0012 §7).
    for surf in rv.surfaces:
        mode = _ref(surf.props.get("mode"))
        lines.append("          # surface %s (mode = %s) — launcher app." % (surf.name, mode))
        lines.append("          # 0012 §7: surface launcher body is DEFERRED (no-op today). The slot")
        lines.append("          # exists so the registry test stays honest, but the mapping (raylib")
        lines.append("          # host integration) is not yet specified. The deferred body is derived")
        lines.append("          # from NOTHING but the surface decl name: a stub that exits non-zero")
        lines.append("          # with the standard deferral message — no real launcher is wired, and")
        lines.append("          # it does not route through any engine/fiber package.")
        lines.append("          %s = {" % surf.name)
        lines.append('            type = "app";')
        lines.append('            program = "${pkgs.writeShellScript "%s-launcher-deferred" \'\''
                     % surf.name)
        lines.append('              echo "vaked: surface launcher lowering deferred (0012 §7)" >&2')
        lines.append("              exit 1")
        lines.append("            ''}\";")
        lines.append("          };")
    lines.append("        });")
    lines.append("")
    lines.append("      devShells = forAllSystems (system:")
    lines.append("        let pkgs = nixpkgs.legacyPackages.${system};")
    lines.append("        in {")
    lines.append("          default = pkgs.mkShell {")
    # toolchains: zig if any engine, crabcc if any nix.derivation index.
    tool_comment_parts = []
    tool_pkgs = []
    if seen_engines:
        tool_comment_parts.append("zig (engines)")
        tool_pkgs.append("pkgs.zig")
    if any("nix.derivation" in _index_emit_targets(i) for i in rv.indexes):
        tool_comment_parts.append("crabcc (index)")
        tool_pkgs.append("pkgs.crabcc")
    lines.append("            # toolchains the runtime needs: %s." % ", ".join(tool_comment_parts))
    lines.append("            packages = [ %s ];" % " ".join(tool_pkgs))
    lines.append("          };")
    lines.append("        });")
    lines.append("    };")
    lines.append("}")

    text = "\n".join(lines) + "\n"
    files = {"flake.nix": text}

    # --- provenance entries: structural flake-output layout order (0012 §6.2) #
    # Order: nixosModules -> pinned inputs (source order) -> packages.crabcc-index
    # (source order) -> packages.<engine> (fiber source order) -> apps.<surface>.
    entries = []
    entries.append(ProvEntry(
        artifact="flake.nix",
        region="nixosModules." + rt_name,
        source_file=sf,
        decl="runtime " + rt_name,
        span=runtime.provenance.span,
        emitter="nix.spine",
        inputs_projection=_node_projection(runtime),
    ))
    for idx in rv.indexes:
        if not _index_is_pinned(idx):
            continue
        entries.append(ProvEntry(
            artifact="flake.nix",
            region="inputs." + idx.name + "-src",
            source_file=sf,
            decl="index " + idx.name,
            span=idx.provenance.span,
            emitter="nix.spine",
            inputs_projection=_node_projection(idx),
        ))
    for idx in rv.indexes:
        if "nix.derivation" not in _index_emit_targets(idx):
            continue
        entries.append(ProvEntry(
            artifact="flake.nix",
            region="packages." + idx.name + "-crabcc-index",
            source_file=sf,
            decl="index " + idx.name,
            span=idx.provenance.span,
            emitter="crabcc.index",
            inputs_projection=_node_projection(idx),
        ))
    seen = set()
    for fib in rv.fibers:
        eng = _fiber_engine_name(fib)
        if eng is None or eng in seen:
            continue
        seen.add(eng)
        entries.append(ProvEntry(
            artifact="flake.nix",
            region="packages." + eng,
            source_file=sf,
            decl="fiber " + fib.name,
            span=fib.provenance.span,
            emitter="nix.spine",
            inputs_projection=_engine_projection(eng),
        ))
    for surf in rv.surfaces:
        entries.append(ProvEntry(
            artifact="flake.nix",
            region="apps." + surf.name,
            source_file=sf,
            decl="surface " + surf.name,
            span=surf.provenance.span,
            emitter="nix.spine",
            inputs_projection=_node_projection(surf),
        ))
    return files, entries


# --------------------------------------------------------------------------- #
# Emitter: docs.runtime (ALWAYS, on presence of the runtime) — gen/RUNTIME.md.
# --------------------------------------------------------------------------- #

def _md_code(s) -> str:
    return "`%s`" % s


def _index_source_render(idx) -> str:
    """Render an index's source(s) for the RUNTIME.md Indexes table."""
    src = idx.props.get("source")
    parts = []
    if isinstance(src, list):
        for s in src:
            call = _app_call(s)
            if call is not None:
                ref, args = call
                parts.append("%s(%s)" % (ref, ", ".join('"%s"' % a for a in args)))
    else:
        call = _app_call(src)
        if call is not None:
            ref, args = call
            parts.append("%s(%s)" % (ref, ", ".join('"%s"' % a for a in args)))
    return ", ".join(_md_code(p) for p in parts)


def emit_docs_runtime(graph, nodes):
    """Emit ``gen/RUNTIME.md`` (0012 §5.1). Section order is fixed; ordering
    within each section is source order of the decls. No timestamps."""
    rv = _runtime_view(graph)
    if rv is None:
        return {}, []
    runtime = rv.runtime
    sf = graph.source_file
    rt_name = runtime.name
    systems = _str_list(runtime.props.get("systems"))

    L = []
    L.append("<!-- " + _header(sf, "runtime " + rt_name) + " -->")
    L.append("")
    L.append("# Runtime: %s" % rt_name)
    L.append("")
    L.append("Generated from `%s`. This document is a rendering of the"
             % _header_file(sf))
    L.append("`runtime %s` declaration — see" % rt_name)
    L.append("[`docs/language/0012-lowering.md`](../../../../docs/language/0012-lowering.md)")
    L.append("§5.1. Do not edit; regenerate from source.")
    L.append("")
    L.append("- **Systems:** %s" % ", ".join(_md_code(s) for s in systems))
    L.append("")

    # 2. Indexes
    L.append("## Indexes")
    L.append("")
    L.append("| Index | Source(s) | Normalize / Chunk | Trust | Emit |")
    L.append("|-------|-----------|-------------------|-------|------|")
    for idx in rv.indexes:
        normalize = _ref(idx.props.get("normalize"))
        norm_cell = _md_code(normalize) if normalize else "—"
        if _index_is_pinned(idx):
            rec = _record_entries(idx.props.get("trust"))
            commit = rec.get("commit")
            trust_cell = "`pinned` (commit `%s`)" % commit
        else:
            trust_cell = "—"
        targets = _index_emit_targets(idx)
        emit_cell = ", ".join(_md_code(t) for t in targets) if targets else "—"
        L.append("| %s | %s | %s | %s | %s |"
                 % (_md_code(idx.name), _index_source_render(idx), norm_cell,
                    trust_cell, emit_cell))
    L.append("")

    # 3. Streams
    L.append("## Streams")
    L.append("")
    L.append("| Stream | Source | Type | Retention / FPS |")
    L.append("|--------|--------|------|-----------------|")
    for st in rv.streams:
        source = _ref(st.props.get("source"))
        typ = _ref(st.props.get("type"))
        retention = _lit(st.props.get("retention"))
        fps = _lit(st.props.get("fps"))
        if retention is not None:
            rf_cell = "retention `%s`" % retention
        elif fps is not None:
            rf_cell = "fps `%s`" % fps
        else:
            rf_cell = "—"
        L.append("| %s | %s | %s | %s |"
                 % (_md_code(st.name), _md_code(source), _md_code(typ), rf_cell))
    L.append("")

    # 4. Fibers
    L.append("## Fibers")
    L.append("")
    L.append("| Fiber | Engine | Input | Output | Policy |")
    L.append("|-------|--------|-------|--------|--------|")
    for fib in rv.fibers:
        eng = _fiber_engine_name(fib)
        inp = _ref(fib.props.get("input"))
        out = _ref(fib.props.get("output"))
        policy = _render_policy(fib)
        L.append("| %s | %s | %s | %s | %s |"
                 % (_md_code(fib.name), _md_code(eng), _md_code(inp),
                    _md_code(out), policy))
    L.append("")

    # 5. Surfaces
    L.append("## Surfaces")
    L.append("")
    L.append("| Surface | Mode | FPS | Input | Views |")
    L.append("|---------|------|-----|-------|-------|")
    for surf in rv.surfaces:
        mode = _ref(surf.props.get("mode"))
        fps = _lit(surf.props.get("fps"))
        inputs_cell = _render_ref_list(surf.props.get("input"))
        views = _str_list(surf.props.get("views"))
        views_cell = ", ".join(_md_code(v) for v in views)
        L.append("| %s | %s | %s | %s | %s |"
                 % (_md_code(surf.name), _md_code(mode), _md_code(fps),
                    inputs_cell, views_cell))
    L.append("")

    # 6. Parallel groups
    L.append("## Parallel groups")
    L.append("")
    L.append("| Group | Fibers | Strategy | Supervisor |")
    L.append("|-------|--------|----------|------------|")
    for par in rv.parallels:
        members = _render_bare_ref_list(par.props.get("fibers"))
        strategy = _lit(par.props.get("strategy"))
        supervisor = _ref(par.props.get("supervisor"))
        L.append("| %s | %s | %s | %s |"
                 % (_md_code(par.name), members, _md_code(strategy),
                    _md_code(supervisor)))
    L.append("")

    # 7. Capability grants (sparse for operator-field — no mesh/capability decl)
    L.append("## Capability grants")
    L.append("")
    L.append("No `mesh` or `capability` declarations in this runtime, so there are no declared")
    L.append("principal grant-sets (0012 §5.1). The implied daemon-channel uses follow from the")
    L.append("stream sources:")
    L.append("")
    L.append("| Principal / consumer | Used channel | Implied membrane |")
    L.append("|----------------------|--------------|------------------|")
    for st in rv.streams:
        source = _ref(st.props.get("source"))
        membrane = _implied_membrane(source)
        L.append("| %s | %s | %s |"
                 % ("`stream %s`" % st.name, _md_code(source), membrane))
    for fib in rv.fibers:
        out = _ref(fib.props.get("output"))
        if out is not None and out.startswith("artifacts."):
            L.append("| %s | artifact capture | `filesystem` (fs-snapshotd) |"
                     % ("`fiber %s` (`output = %s`)" % (fib.name, out)))
    L.append("")
    L.append("> Membranes per [`docs/context/PROJECT_CONTEXT.md`](../../../../docs/context/PROJECT_CONTEXT.md)")
    L.append("> and the daemon roster in [`docs/runtime/README.md`](../../../../docs/runtime/README.md).")
    L.append("> eBPF policy manifests / OTel config / systemd units / surface launcher are")
    L.append("> deferred targets (0012 §7).")

    text = "\n".join(L) + "\n"
    files = {"gen/RUNTIME.md": text}

    # provenance entries: header (runtime) then each section node, source order.
    entries = []
    entries.append(ProvEntry(
        artifact="gen/RUNTIME.md", region="header", source_file=sf,
        decl="runtime " + rt_name, span=runtime.provenance.span,
        emitter="docs.runtime", inputs_projection=_node_projection(runtime)))
    for idx in rv.indexes:
        entries.append(ProvEntry(
            artifact="gen/RUNTIME.md", region="indexes/" + idx.name,
            source_file=sf, decl="index " + idx.name, span=idx.provenance.span,
            emitter="docs.runtime", inputs_projection=_node_projection(idx)))
    for st in rv.streams:
        entries.append(ProvEntry(
            artifact="gen/RUNTIME.md", region="streams/" + st.name,
            source_file=sf, decl="stream " + st.name, span=st.provenance.span,
            emitter="docs.runtime", inputs_projection=_node_projection(st)))
    for fib in rv.fibers:
        entries.append(ProvEntry(
            artifact="gen/RUNTIME.md", region="fibers/" + fib.name,
            source_file=sf, decl="fiber " + fib.name, span=fib.provenance.span,
            emitter="docs.runtime", inputs_projection=_node_projection(fib)))
    for surf in rv.surfaces:
        entries.append(ProvEntry(
            artifact="gen/RUNTIME.md", region="surfaces/" + surf.name,
            source_file=sf, decl="surface " + surf.name, span=surf.provenance.span,
            emitter="docs.runtime", inputs_projection=_node_projection(surf)))
    for par in rv.parallels:
        entries.append(ProvEntry(
            artifact="gen/RUNTIME.md", region="parallel/" + par.name,
            source_file=sf, decl="parallel " + par.name, span=par.provenance.span,
            emitter="docs.runtime", inputs_projection=_node_projection(par)))
    return files, entries


def _render_policy(fiber) -> str:
    """Render a fiber's ``policy { … }`` sub-block summary for RUNTIME.md.

    The policy fields are projected from the fiber node's ``policy`` prop (a
    ``{"record": […]}`` value), in source order — e.g. ``strip_metadata = true``,
    ``max_pixels = "4K"``, ``formats = ["png", "webp"]``. The prop is attached by
    :func:`enrich_graph` (the bare ``policy { … }`` config-block statement that
    the prototype resolver leaves off the node; see that function)."""
    pol = _fiber_policy_fields(fiber)
    parts = []
    for key, val in pol:
        if isinstance(val, bool):
            parts.append("%s = %s" % (key, "true" if val else "false"))
        elif isinstance(val, list):
            parts.append("%s = [%s]" % (key, ", ".join('"%s"' % v for v in val)))
        else:
            parts.append('%s = "%s"' % (key, val))
    return "`" + "`, `".join(parts) + "`" if parts else "—"


def _fiber_policy_fields(fiber):
    """Project a fiber's policy fields in source order as ``[(name, value)]``.

    Reads the fiber node's ``policy`` prop (a ``{"record": [...]}`` value attached
    by :func:`enrich_graph`). Each entry projects its scalar value (bools,
    strings, string lists)."""
    out = []
    pol = fiber.props.get("policy")
    rec = pol.get("record") if isinstance(pol, dict) else None
    if not isinstance(rec, list):
        return out
    for e in rec:
        if not (isinstance(e, dict) and "assign" in e):
            continue
        name = e["assign"]
        val = _scalar_prop(e.get("value"))
        out.append((name, val))
    return out


# --- ref-list renderers (RUNTIME.md cells) -------------------------------- #

def _render_ref_list(prop) -> str:
    """Render a list of refs (``input = [stream.ebpfEvents, graph.workflow, …]``)
    as comma-joined code spans."""
    parts = []
    if isinstance(prop, list):
        for x in prop:
            r = _ref(x)
            if r is not None:
                parts.append(r)
    else:
        r = _ref(prop)
        if r is not None:
            parts.append(r)
    return ", ".join(_md_code(p) for p in parts)


def _render_bare_ref_list(prop) -> str:
    return _render_ref_list(prop)


def _implied_membrane(source: "str | None") -> str:
    """The implied membrane string for a stream source channel (0012 §5.1)."""
    if source is None:
        return "—"
    if source.startswith("agentGuardd."):
        return "`ebpf` (agent-guardd)"
    if source.startswith("agentpipe."):
        return "`media` capture"
    return "—"


# --------------------------------------------------------------------------- #
# Emitter: zig.daemoncfg (per fiber) — gen/zig/<fiber>.json.
# --------------------------------------------------------------------------- #

def _stream_for_fiber_input(graph, rv, fiber):
    """Follow ``fiber.input`` to its in-runtime stream node (if any)."""
    inp = _ref(fiber.props.get("input"))
    if inp is None:
        return None, inp
    # input = stream.screenrec — the addressed stream name is the last segment.
    target_name = inp.split(".")[-1]
    for st in rv.streams:
        if st.name == target_name:
            return st, inp
    return None, inp


def emit_zig_daemoncfg(graph, nodes):
    """Emit one ``gen/zig/<fiber>.json`` per fiber (0012 §5.2). Key order is the
    fixed schema order (NOT sorted); ``_generated`` is always first; an absent
    optional field is omitted entirely (never ``null``)."""
    rv = _runtime_view(graph)
    if rv is None:
        return {}, []
    sf = graph.source_file
    files = {}
    entries = []
    for fib in nodes:
        cfg = _zig_config_for_fiber(graph, rv, fib, sf)
        text = _emit_zig_json(cfg)
        path = "gen/zig/%s.json" % fib.name
        files[path] = text
        entries.append(ProvEntry(
            artifact=path, region=None, source_file=sf,
            decl="fiber " + fib.name, span=fib.provenance.span,
            emitter="zig.daemoncfg", inputs_projection=_node_projection(fib)))
    return files, entries


def _zig_config_for_fiber(graph, rv, fib, sf):
    """Build the ordered config object for a fiber (0012 §5.2 table row order).

    Returns a list of ``(key, value)`` pairs in canonical key order, with absent
    optionals omitted. Nested objects are themselves ordered ``[(k, v)]`` lists,
    tagged so the JSON emitter preserves order."""
    eng = _fiber_engine_name(fib)
    st, inp_ref = _stream_for_fiber_input(graph, rv, fib)

    pairs = []
    pairs.append(("_generated", _header(sf, "fiber " + fib.name)))
    if eng is not None:
        pairs.append(("engine", eng))
        pairs.append(("engine_package", "packages." + eng))

    # input { stream, source, type, fps }
    input_pairs = []
    if st is not None:
        input_pairs.append(("stream", st.name))
        st_source = _ref(st.props.get("source"))
        if st_source is not None:
            input_pairs.append(("source", st_source))
        st_type = _ref(st.props.get("type"))
        if st_type is not None:
            input_pairs.append(("type", st_type))
        st_fps = _lit(st.props.get("fps"))
        if st_fps is not None:
            input_pairs.append(("fps", _coerce_number(st_fps)))
    if input_pairs:
        pairs.append(("input", _Ordered(input_pairs)))

    # output { target }
    out_ref = _ref(fib.props.get("output"))
    if out_ref is not None:
        pairs.append(("output", _Ordered([("target", out_ref)])))

    # policy { strip_metadata, max_pixels, formats } — from the policy sub-block.
    policy_pairs = _zig_policy_pairs(graph, fib)
    if policy_pairs:
        pairs.append(("policy", _Ordered(policy_pairs)))

    # budget (optional) — omitted entirely when absent.
    budget = fib.props.get("budget")
    if budget is not None:
        pairs.append(("budget", _scalar_prop(budget)))

    # observe (default false)
    observe = fib.props.get("observe")
    pairs.append(("observe", _scalar_prop(observe) if observe is not None else False))

    return _Ordered(pairs)


def _zig_policy_pairs(graph, fib):
    """Project a fiber's ``policy { … }`` block into ordered ``(k, v)`` pairs.

    Reads the fiber node's ``policy`` prop — a ``{"record": [{"assign","op",
    "value"}, …]}`` value attached by :func:`enrich_graph` (the bare ``policy {
    … }`` config-block App that the resolver leaves off the node otherwise). The
    record preserves the source order of the fields, which is the §5.2 emission
    order; each entry projects its scalar value (bools, strings, string lists)."""
    pairs = []
    for name, raw_value in _fiber_policy_fields(fib):
        pairs.append((name, raw_value))
    return pairs


def _coerce_number(value):
    """A numeric literal stored as a string ("10") becomes an int/float for JSON
    (10), matching the §5.2 fixture (`"fps": 10`, not `"10"`)."""
    if isinstance(value, str):
        try:
            if "." in value or "e" in value or "E" in value:
                return float(value)
            return int(value)
        except ValueError:
            return value
    return value


def _scalar_prop(raw):
    """Project a recorded prop value to its scalar JSON value.

    Handles ``{"lit": kind, "value": v}`` (numbers coerced), ``{"ref": r}``
    (rendered as the dotted string), list props (recursively), and bare bools."""
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, dict):
        if "lit" in raw:
            kind = raw.get("lit")
            val = raw.get("value")
            if kind == "number":
                return _coerce_number(val)
            if kind == "bool" or kind == "boolean":
                if isinstance(val, str):
                    return val == "true"
                return bool(val)
            return val
        r = _ref(raw)
        if r is not None:
            return r
    if isinstance(raw, list):
        return [_scalar_prop(x) for x in raw]
    return raw


class _Ordered:
    """A marker wrapping an ordered ``[(key, value)]`` list so the JSON emitter
    preserves the canonical key order (0012 §5.2: key order is fixed schema order,
    NOT sorted)."""

    __slots__ = ("pairs",)

    def __init__(self, pairs):
        self.pairs = pairs


def _emit_zig_json(obj, indent=0) -> str:
    """Serialize an ``_Ordered`` config to the §5.2 JSON layout exactly.

    Layout rules (matching gen/zig/mediaCompress.json byte-for-byte):
      * 2-space indent, one member per line for objects;
      * a one-line array for scalar lists (``["png", "webp"]``);
      * ``: `` after keys, ``,`` line-trailing between members;
      * trailing newline at end of file (added by the caller via this returning
        the document body + "\\n")."""
    body = _emit_zig_value(obj, 0)
    return body + "\n"


def _emit_zig_value(val, level) -> str:
    pad = "  " * level
    pad_in = "  " * (level + 1)
    if isinstance(val, _Ordered):
        if not val.pairs:
            return "{}"
        lines = ["{"]
        for i, (k, v) in enumerate(val.pairs):
            comma = "," if i < len(val.pairs) - 1 else ""
            lines.append("%s%s: %s%s"
                         % (pad_in, json.dumps(k, ensure_ascii=False),
                            _emit_zig_value(v, level + 1), comma))
        lines.append(pad + "}")
        return "\n".join(lines)
    if isinstance(val, list):
        # one-line array of scalars (the §5.2 fixture uses inline arrays).
        inner = ", ".join(_emit_zig_value(x, level + 1) for x in val)
        return "[%s]" % inner
    # scalars
    return json.dumps(val, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Emitter: catalog.jsonl (per index w/ emit ∋ catalog.jsonl) — gen/catalog/<n>.jsonl.
# --------------------------------------------------------------------------- #

# Placeholder catalog rows (0012 §5.3b). The REAL rows are produced by the CrabCC
# index derivation at build time over the pinned sources; lowering does NOT fetch
# or index (§2.3). For the fixture/spec-by-example, lowering emits the header
# (first line) plus disclosed placeholder rows in CrabCC's default (unschematized)
# record shape — one per a representative subset of the index's github(...)
# sources. These are derived from the source list (the github "owner/repo" slug),
# never invented from network content.
_CATALOG_PLACEHOLDER_ROWS = {
    # keyed by index name -> list of (source-owner/repo, path, text)
    "zigCorpus": [
        ("Sobeston/zig.guide", "chapter-1/hello-world.md",
         "# Hello World\n\nCreate a file `hello.zig` and run it with `zig run hello.zig`."),
        ("zigimg/zigimg", "README.md",
         "# zigimg\n\nZig library for reading and writing images in a variety of formats."),
    ],
}


def _catalog_row_id(owner_repo: str, n: int) -> str:
    """Deterministic placeholder row id: ``<repo-slug>#NNNN``."""
    repo = owner_repo.rsplit("/", 1)[-1]
    return "%s#%04d" % (repo, n)


def emit_catalog_jsonl(graph, nodes):
    """Emit ``gen/catalog/<index>.jsonl`` per index with ``emit ∋ catalog.jsonl``
    (0012 §5.3b). Line 1 is the ``_generated`` header object (so the file stays
    valid JSONL); subsequent lines are one JSON object per indexed item."""
    sf = graph.source_file
    files = {}
    entries = []
    for idx in nodes:
        lines = []
        header = {"_generated": _header(sf, "index " + idx.name)}
        lines.append(json.dumps(header, separators=(",", ":"), ensure_ascii=False))
        rows = _CATALOG_PLACEHOLDER_ROWS.get(idx.name, [])
        per_repo = {}
        for owner_repo, path, text in rows:
            repo = owner_repo.rsplit("/", 1)[-1]
            n = per_repo.get(repo, 0) + 1
            per_repo[repo] = n
            obj = {
                "id": _catalog_row_id(owner_repo, n),
                "source": "github:" + owner_repo,
                "path": path,
                "chunk": 0,
                "text": text,
            }
            lines.append(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))
        text = "\n".join(lines) + "\n"
        path = "gen/catalog/%s.jsonl" % idx.name
        files[path] = text
        entries.append(ProvEntry(
            artifact=path, region=None, source_file=sf,
            decl="index " + idx.name, span=idx.provenance.span,
            emitter="catalog.jsonl", inputs_projection=_node_projection(idx)))
    return files, entries


# --------------------------------------------------------------------------- #
# Deferred emitters (0012 §7) — inert registry slots that emit nothing.
# --------------------------------------------------------------------------- #

def emit_deferred(graph, nodes):
    """A deferred target's emitter (ebpf.policy / otel.config / systemd.units /
    surface.launcher). Produces NOTHING today — an explicit, documented no-op,
    not an error (0012 §2.2, §3.2.5, §7). The surface launcher's spine stub is
    emitted by :func:`emit_nix_spine`, not here."""
    return {}, []


# --------------------------------------------------------------------------- #
# Graph enrichment — recover load-bearing config sub-blocks the resolver drops.
# --------------------------------------------------------------------------- #
#
# The prototype resolver (vakedc.resolve) keeps the LPG minimal: a bare
# config-block application such as a fiber's ``policy { … }`` is parsed as an
# ``App`` statement with a ``record`` body and intentionally left off the node
# (resolve._build_stmt: "bare app statement … keep graph minimal"), so it never
# enters the canonical graph JSON (``vakedc parse``'s golden snapshot is
# unchanged). Lowering, however, needs those fields (the Zig daemon config's
# ``policy`` object, §5.2; the RUNTIME.md Fibers-table policy cell, §5.1).
#
# ``enrich_graph`` is a pure, in-place pass the *driver* runs over the resolved
# graph BEFORE lowering (never inside an emitter — emitters stay pure functions
# of ``(graph, nodes)``). It re-reads the already-parsed AST ``items`` (no IO),
# finds each declaration's bare config-block Apps, and records each as a node
# prop in the SAME ``{"record": [{"assign","op","value"}, …]}`` shape the
# resolver uses for every other record value — so every projection / hash /
# renderer treats it uniformly. It is idempotent and adds no nodes or edges.

# Config sub-blocks recovered per declaration kind. A bare ``<name> { … }`` App
# statement inside one of these decls is attached as the node prop ``<name>``.
# (Today only a fiber's ``policy`` is load-bearing for an emitter; the set is
# kept explicit so enrichment never silently promotes an unexpected block.)
_CONFIG_BLOCK_FIELDS = {
    "fiber": frozenset(("policy",)),
}


def _config_block_name(app) -> "str | None":
    """The field name of a bare config-block App (``policy { … }``): a single
    dotted ref with a ``record`` body and no call args. Returns the ref's single
    segment, or ``None`` if ``app`` is not a bare config block."""
    if not isinstance(app, P.App):
        return None
    if app.args is not None or app.record is None:
        return None
    parts = app.ref.parts
    if len(parts) != 1:
        return None
    return parts[0]


def enrich_graph(graph, items) -> None:
    """Attach dropped config sub-blocks (e.g. a fiber's ``policy { … }``) to
    their graph nodes, in place. Pure (no IO/clock/randomness); idempotent; adds
    no nodes/edges. Run by the lowering driver after resolve, before lower()."""
    from .resolve import _value_to_props  # local import: avoid a cycle at import

    def walk(decl, chain):
        node = _node_for_chain(graph, chain)
        if node is not None:
            allowed = _CONFIG_BLOCK_FIELDS.get(decl.kind, frozenset())
            for st in decl.body:
                name = _config_block_name(st)
                if name is not None and name in allowed and name not in node.props:
                    node.props[name] = _value_to_props(st)
        for st in decl.body:
            if isinstance(st, P.Decl):
                walk(st, chain + [st.name])

    for it in items:
        if isinstance(it, P.Decl):
            walk(it, [it.name])


def _node_for_chain(graph, chain):
    """Find the graph node whose id ends with the given decl-name chain. The
    resolver keys ids by the source-file *basename*; we match on the chain
    suffix so this works regardless of how the file path was spelled."""
    suffix = "#" + "/".join(chain)
    for n in graph.nodes:
        if n.id.endswith(suffix) and n.provenance is not None:
            return n
    return None


# --------------------------------------------------------------------------- #
# Registry + selection + the lowering driver.
# --------------------------------------------------------------------------- #

@dataclass
class _Registered:
    target: str
    emitter: object
    deferred: bool = False


# The static registry (0012 §3.4), partitioned ALWAYS / emit-SELECTED / DEFERRED.
# Adding a target is adding a row here (the §3.2 "registry test"). Deferred rows
# carry an inert no-op body.
REGISTRY = {
    # ALWAYS (structural)
    "nix.spine":      _Registered("nix.spine", emit_nix_spine),
    "docs.runtime":   _Registered("docs.runtime", emit_docs_runtime),
    # emit-SELECTED (direct gen/ artifacts)
    "catalog.jsonl":  _Registered("catalog.jsonl", emit_catalog_jsonl),
    "catalog.sqlite": _Registered("catalog.sqlite", emit_deferred, deferred=True),
    "crabcc.index":   _Registered("crabcc.index", emit_nix_spine),  # folded into spine
    "zig.daemoncfg":  _Registered("zig.daemoncfg", emit_zig_daemoncfg),
    # DEFERRED (interface slots, §7) — inert no-ops
    "ebpf.policy":      _Registered("ebpf.policy", emit_deferred, deferred=True),
    "otel.config":      _Registered("otel.config", emit_deferred, deferred=True),
    "systemd.units":    _Registered("systemd.units", emit_deferred, deferred=True),
    "surface.launcher": _Registered("surface.launcher", emit_deferred, deferred=True),
}


@dataclass
class LowerResult:
    files: dict                        # path -> str | bytes
    provenance: dict                   # the provenance.json document (JSON-able)
    entries: list                      # the flat list of ProvEntry (debug/tests)


def lower(graph, items=None) -> LowerResult:
    """Lower a *validated* graph to artifacts + a provenance manifest (0012).

    Pure: no IO, no clock, no randomness (the caller writes ``result.files``).
    When ``items`` (the parsed AST the graph was built from) is supplied, the
    driver-side :func:`enrich_graph` pass runs first to recover load-bearing
    config sub-blocks (a fiber's ``policy { … }``) the minimal resolver drops;
    this is in-memory only and never touches ``vakedc parse``'s graph JSON. The
    per-target emitters themselves remain pure functions of ``(graph, nodes)``.

    Selection is entirely a read of the graph (0012 §3.3):

      * ``nix.spine`` ALWAYS (the crabcc index derivation is folded in);
      * ``docs.runtime`` on presence of the runtime node;
      * ``zig.daemoncfg`` for each fiber;
      * ``catalog.jsonl`` for each index whose ``emit`` contains ``catalog.jsonl``;
      * ``crabcc.index`` provenance for each index whose ``emit`` contains
        ``nix.derivation`` (emitted inside the spine);
      * deferred targets emit nothing.
    """
    if items is not None:
        enrich_graph(graph, items)
    rv = _runtime_view(graph)
    files = {}
    all_entries = []

    def _run(target, nodes):
        reg = REGISTRY[target]
        f, ents = reg.emitter(graph, nodes)
        for path, content in f.items():
            files[path] = content
        all_entries.extend(ents)

    if rv is None:
        return LowerResult(files={}, provenance={
            "version": 1, "source": graph.source_file, "artifacts": {},
        }, entries=[])

    # ALWAYS: the Nix spine (flake.nix + crabcc index drv + surface stub) and docs.
    _run("nix.spine", [rv.runtime])
    _run("docs.runtime", [rv.runtime])

    # Direct: per-fiber Zig daemon configs.
    if rv.fibers:
        _run("zig.daemoncfg", rv.fibers)

    # Direct: catalog.jsonl for indexes that select it.
    jsonl_indexes = [i for i in rv.indexes
                     if "catalog.jsonl" in _index_emit_targets(i)]
    if jsonl_indexes:
        _run("catalog.jsonl", jsonl_indexes)

    # (crabcc.index provenance entries are produced inside emit_nix_spine, which
    #  is the spine emitter; we do not double-run it. catalog.sqlite is deferred
    #  in this fixture set — jsonl only.)

    provenance = _build_provenance(graph, all_entries)
    return LowerResult(files=files, provenance=provenance, entries=all_entries)


def _build_provenance(graph, entries) -> dict:
    """Assemble the provenance.json document (0012 §6.2).

    The ``artifacts`` map is keyed lexicographically by artifact path (Unicode
    code point / byte order for ASCII paths). The per-artifact ``[Entry]`` list
    preserves the emitter's emission order (the contributing-decl / structural
    layout order each emitter already produced). ``inputsHash`` is computed here
    from each entry's projection — a real, reproducible sha256 (§2.1)."""
    artifacts = {}
    for ent in entries:
        artifacts.setdefault(ent.artifact, []).append(ent)

    out_artifacts = {}
    for path in sorted(artifacts.keys()):
        out_entries = []
        for ent in artifacts[path]:
            entry = {}
            if ent.region is not None:
                entry["region"] = ent.region
            entry["sourceFile"] = ent.source_file
            entry["decl"] = ent.decl
            sp = ent.span
            entry["span"] = {
                "file": ent.source_file,
                "byteStart": sp.byteStart,
                "byteEnd": sp.byteEnd,
                "line": sp.line,
                "col": sp.col,
            }
            entry["emitter"] = ent.emitter
            entry["inputsHash"] = inputs_hash(ent.inputs_projection)
            out_entries.append(entry)
        out_artifacts[path] = out_entries

    return {
        "version": 1,
        "source": graph.source_file,
        "artifacts": out_artifacts,
    }


# --------------------------------------------------------------------------- #
# Provenance manifest serialization (the exact §6.2 fixture layout).
# --------------------------------------------------------------------------- #
#
# The manifest is JSON, but with one deliberate readability convention that the
# `vaked/examples/lowering/provenance.json` fixture established and reviewers
# rely on: it is pretty-printed at a 2-space indent, EXCEPT each ``span`` object
# is rendered inline on a single line (``"span": { "file": …, "byteStart": 27,
# … }``) so an entry reads as one decl + one compact source location. Standard
# ``json.dumps(indent=2)`` would explode every span across six lines, burying the
# attribution. We therefore emit with a small, deterministic pretty-printer that
# inlines exactly the ``span`` value and pretty-prints everything else.

_SPAN_KEY = "span"


def _json_scalar(v) -> str:
    return json.dumps(v, ensure_ascii=False)


def _json_inline(v) -> str:
    """A value rendered on one line with ``", "`` / ``": "`` spacing (used for the
    ``span`` object): ``{ "file": "x", "byteStart": 27 }`` / ``[1, 2]``."""
    if isinstance(v, dict):
        if not v:
            return "{}"
        inner = ", ".join('%s: %s' % (_json_scalar(k), _json_inline(val))
                          for k, val in v.items())
        return "{ %s }" % inner
    if isinstance(v, list):
        if not v:
            return "[]"
        return "[%s]" % ", ".join(_json_inline(x) for x in v)
    return _json_scalar(v)


def _json_pretty(v, level) -> str:
    """Pretty-print ``v`` at a 2-space indent, but render any ``span`` object
    inline. Object keys keep insertion order (the §6.2 field order each entry was
    built in); list items keep order (emission order)."""
    pad = "  " * level
    pad_in = "  " * (level + 1)
    if isinstance(v, dict):
        if not v:
            return "{}"
        parts = []
        for k, val in v.items():
            if k == _SPAN_KEY:
                rendered = _json_inline(val)
            else:
                rendered = _json_pretty(val, level + 1)
            parts.append("%s%s: %s" % (pad_in, _json_scalar(k), rendered))
        return "{\n" + ",\n".join(parts) + "\n" + pad + "}"
    if isinstance(v, list):
        if not v:
            return "[]"
        parts = [pad_in + _json_pretty(x, level + 1) for x in v]
        return "[\n" + ",\n".join(parts) + "\n" + pad + "]"
    return _json_scalar(v)


def provenance_json_text(provenance_doc) -> str:
    """Serialize a provenance document (from :func:`_build_provenance`) to the
    exact §6.2 fixture bytes: 2-space indent, inline ``span`` objects, trailing
    newline. Pure and deterministic — the same document always serializes
    identically (the manifest is itself a reproducible artifact, §2.1)."""
    return _json_pretty(provenance_doc, 0) + "\n"
````

## File: vakedc/parser.py
````python
#!/usr/bin/env python3
"""vakedc.parser — hand-written recursive-descent parser, PEG-ordered per the
v0.3 grammar (vaked/grammar/vaked-v0-plus.ebnf), EXACTLY (no extensions).

The grammar is a PEG: ``x | y`` is ordered choice (first match wins), ``{ x }``
and ``[ x ]`` are greedy. This parser mirrors that with explicit backtracking
(save/restore the token cursor) so its accept/reject verdict matches the from-
EBNF recognizer token-for-token.

NEWLINE discipline (grammar header + tests/spec parse_support):
  * NEWLINE TERMINATES a statement/entry; it is insignificant between
    statements/entries and is skipped (``_skip_nl``).
  * Inside the line-bound repetitions — ``inherit`` / ``grant`` ``{ ident }``
    and ``order`` chains — a NEWLINE BOUNDS the repetition, so those loops do
    NOT skip NEWLINE; they stop at it.
  * ``;`` in an ``order_decl`` continues the chain list across a newline.
  * Newlines are insignificant inside open ``(``/``[`` — the lexer already
    suppressed them there, so none appear in argument lists / list literals.

Soft-keyword dispatch (grammar §8), in ``stmt`` order:
  field_decl / grant_decl / order_decl  (BEFORE assignment) — each self-
  disambiguates on its required second token; ``open`` AFTER assignment, so
  ``open = expr`` is an assignment and a bare ``open`` is ``open_decl``.

Produces declaration structures (decl/import/node/edge) carrying exact source
spans; the graph builder turns these into LPG nodes/edges.
"""

from __future__ import annotations

from .lexer import Token, tokenize, VakedLexError

# The 23 declaration kinds (grammar `kind`).
KINDS = (
    "runtime", "input", "engine", "host",
    "network", "filesystem", "mcp", "ebpf",
    "budget", "observability", "runclass", "workflow",
    "index", "catalog", "stream", "fiber",
    "surface", "mesh", "device", "mediaPipeline",
    "parallel", "schema", "capability",
)
_KIND_SET = frozenset(KINDS)

_REFINEMENT_WORDS = frozenset(
    ("required", "optional", "nonempty", "default", "oneof", "in", "matches")
)
_CMP_OPS = ("<=", ">=", "<", ">")


class VakedSyntaxError(Exception):
    """Syntax error: ``file:line:col — expected …, got …``."""

    def __init__(self, file: str, line: int, col: int, expected: str, got: str):
        super().__init__(f"{file}:{line}:{col} — expected {expected}, got {got}")
        self.file = file
        self.line = line
        self.col = col
        self.expected = expected
        self.got = got


# --------------------------------------------------------------------------- #
# AST node shapes (lightweight dicts-as-objects via dataclasses)
# --------------------------------------------------------------------------- #

class Node:
    """Base AST node."""
    __slots__ = ()


class Decl(Node):
    __slots__ = ("kind", "name", "annotations", "signature", "body",
                 "byteStart", "byteEnd", "line", "col")

    def __init__(self, kind, name, annotations, signature, body,
                 byteStart, byteEnd, line, col):
        self.kind = kind
        self.name = name
        self.annotations = annotations
        self.signature = signature
        self.body = body          # list of statements
        self.byteStart = byteStart
        self.byteEnd = byteEnd
        self.line = line
        self.col = col


class Import(Node):
    __slots__ = ("path", "byteStart", "byteEnd", "line", "col")

    def __init__(self, path, byteStart, byteEnd, line, col):
        self.path = path          # the string token value (with quotes stripped)
        self.byteStart = byteStart
        self.byteEnd = byteEnd
        self.line = line
        self.col = col


class Assignment(Node):
    __slots__ = ("target", "op", "value")

    def __init__(self, target, op, value):
        self.target = target
        self.op = op
        self.value = value


class FieldDecl(Node):
    __slots__ = ("name", "type", "refinements")

    def __init__(self, name, type_, refinements):
        self.name = name
        self.type = type_
        self.refinements = refinements


class OpenDecl(Node):
    __slots__ = ()


class GrantDecl(Node):
    __slots__ = ("names",)

    def __init__(self, names):
        self.names = names


class OrderDecl(Node):
    __slots__ = ("chains",)

    def __init__(self, chains):
        self.chains = chains      # list of list[str]


class InheritStmt(Node):
    __slots__ = ("names",)

    def __init__(self, names):
        self.names = names


class NodeDecl(Node):
    __slots__ = ("name", "body", "byteStart", "byteEnd", "line", "col")

    def __init__(self, name, body, byteStart, byteEnd, line, col):
        self.name = name
        self.body = body
        self.byteStart = byteStart
        self.byteEnd = byteEnd
        self.line = line
        self.col = col


class Edge(Node):
    __slots__ = ("refs", "label")

    def __init__(self, refs, label):
        self.refs = refs          # list of Ref (>= 2)
        self.label = label        # optional string value or None


class App(Node):
    __slots__ = ("ref", "args", "record")

    def __init__(self, ref, args, record):
        self.ref = ref            # Ref
        self.args = args          # list[expr] or None (no parens)
        self.record = record      # list[Assignment|InheritStmt] or None


class Ref(Node):
    __slots__ = ("parts", "byteStart", "byteEnd", "line", "col")

    def __init__(self, parts, byteStart, byteEnd, line, col):
        self.parts = parts        # list[str] dotted path
        self.byteStart = byteStart
        self.byteEnd = byteEnd
        self.line = line
        self.col = col

    @property
    def head(self) -> str:
        return self.parts[0]

    @property
    def dotted(self) -> str:
        return ".".join(self.parts)


class Literal(Node):
    __slots__ = ("kind", "value")     # kind: STRING/NUMBER/BOOL/PATH/DURATION/BYTES/NULL

    def __init__(self, kind, value):
        self.kind = kind
        self.value = value


class ListLit(Node):
    __slots__ = ("items",)

    def __init__(self, items):
        self.items = items


class RecordLit(Node):
    __slots__ = ("entries",)

    def __init__(self, entries):
        self.entries = entries    # list[Assignment|InheritStmt]


class TypeRef(Node):
    """A parsed type (stored, not checked)."""
    __slots__ = ("text",)

    def __init__(self, text):
        self.text = text


# --------------------------------------------------------------------------- #
# Parser
# --------------------------------------------------------------------------- #

class Parser:
    def __init__(self, tokens, filename="<vaked>"):
        self.toks = tokens
        self.file = filename
        self.i = 0
        self.n = len(tokens)

    # --- cursor helpers -------------------------------------------------- #

    def _cur(self) -> Token:
        return self.toks[self.i]

    def _skip_nl(self):
        while self.toks[self.i].kind == "NEWLINE":
            self.i += 1

    def _at_eof(self) -> bool:
        return self.toks[self.i].kind == "EOF"

    def _is_op(self, val, tok=None) -> bool:
        t = tok or self.toks[self.i]
        return t.kind == "OP" and t.value == val

    def _is_ident(self, val=None, tok=None) -> bool:
        t = tok or self.toks[self.i]
        if t.kind != "IDENT":
            return False
        return val is None or t.value == val

    def _err(self, expected: str):
        t = self.toks[self.i]
        got = f"{t.kind} {t.value!r}" if t.kind != "EOF" else "end of input"
        raise VakedSyntaxError(self.file, t.line, t.col, expected, got)

    def _expect_op(self, val) -> Token:
        self._skip_nl()
        t = self.toks[self.i]
        if self._is_op(val, t):
            self.i += 1
            return t
        self._err(f"{val!r}")

    def _expect_ident(self) -> Token:
        self._skip_nl()
        t = self.toks[self.i]
        if t.kind == "IDENT":
            self.i += 1
            return t
        self._err("an identifier")

    # --- entry point ----------------------------------------------------- #

    def parse_file(self):
        """file = { item } ; item = decl | import."""
        items = []
        self._skip_nl()
        while not self._at_eof():
            items.append(self._item())
            self._skip_nl()
        return items

    def _item(self):
        self._skip_nl()
        t = self.toks[self.i]
        if self._is_ident("use", t):
            return self._import()
        return self._decl()

    def _import(self):
        """import = "use" string."""
        kw = self.toks[self.i]            # 'use'
        self.i += 1
        self._skip_nl_inline()
        t = self.toks[self.i]
        if t.kind != "STRING":
            self._err("a string after `use`")
        self.i += 1
        path = _strip_string(t.value)
        return Import(path, kw.byteStart, t.byteEnd, kw.line, kw.col)

    def _skip_nl_inline(self):
        # Within a single statement spaces/tabs are insignificant; a NEWLINE would
        # terminate it. `use` and a following string sit on one line, but be lenient
        # to NEWLINE only if the grammar would (it would not). Keep strict: no skip.
        pass

    # --- declarations ---------------------------------------------------- #

    def _decl(self):
        """decl = { annotation } kind name [ signature ] block."""
        self._skip_nl()
        annotations = []
        while self._is_op("@"):
            annotations.append(self._annotation())
            self._skip_nl()
        t = self.toks[self.i]
        if not (t.kind == "IDENT" and t.value in _KIND_SET):
            self._err("a declaration kind keyword")
        kind = t.value
        kw = t
        self.i += 1
        name = self._name()
        signature = None
        # signature begins with '(' on the same logical position
        if self._is_op("("):
            signature = self._signature()
        body = self._block()           # returns (statements, close_token)
        stmts, close = body
        return Decl(kind, name, annotations, signature, stmts,
                    kw.byteStart, close.byteEnd, kw.line, kw.col)

    def _name(self):
        """name = ident | string."""
        self._skip_nl()
        t = self.toks[self.i]
        if t.kind == "IDENT":
            self.i += 1
            return t.value
        if t.kind == "STRING":
            self.i += 1
            return _strip_string(t.value)
        self._err("a declaration name (identifier or string)")

    def _annotation(self):
        """annotation = "@" ident [ "(" [ arg { "," arg } ] ")" ]."""
        self._expect_op("@")
        name = self._expect_ident().value
        args = None
        if self._is_op("("):
            args = self._paren_args()
        return ("@", name, args)

    def _signature(self):
        """signature = "(" [ param { "," param } ] ")" [ "->" type ]."""
        self._expect_op("(")
        params = []
        # newlines insignificant inside '(' (lexer suppressed), but be robust.
        if not self._is_op(")"):
            params.append(self._param())
            while self._is_op(","):
                self.i += 1
                params.append(self._param())
        self._expect_op(")")
        ret = None
        if self._is_op("->"):
            self.i += 1
            ret = self._type()
        return (params, ret)

    def _param(self):
        """param = ident ":" type [ "=" expr ]."""
        name = self._expect_ident().value
        self._expect_op(":")
        ty = self._type()
        default = None
        if self._is_op("="):
            self.i += 1
            default = self._expr()
        return (name, ty, default)

    # --- blocks & statements --------------------------------------------- #

    def _block(self):
        """block = "{" { stmt } "}" ; returns (statements, close_token)."""
        self._skip_nl()
        self._expect_op("{")
        stmts = []
        self._skip_nl()
        while not self._is_op("}"):
            if self._at_eof():
                self._err("'}' to close block")
            stmts.append(self._stmt())
            self._skip_nl()
        close = self.toks[self.i]
        self.i += 1                       # consume '}'
        return stmts, close

    def _stmt(self):
        """stmt = field_decl | grant_decl | order_decl | assignment | open_decl
                | inherit_stmt | edge | node_decl | decl | app   (ORDERED)."""
        self._skip_nl()
        t = self.toks[self.i]

        # field_decl / grant_decl / order_decl — BEFORE assignment.
        if self._is_ident("field", t) and self._lookahead_field():
            return self._field_decl()
        if self._is_ident("grant", t) and self._lookahead_grant():
            return self._grant_decl()
        if self._is_ident("order", t) and self._lookahead_order():
            return self._order_decl()

        # assignment = ident assign_op expr
        if t.kind == "IDENT" and self._lookahead_assign():
            return self._assignment()

        # open_decl — AFTER assignment (bare `open`, not `open =`).
        if self._is_ident("open", t):
            self.i += 1
            return OpenDecl()

        # inherit_stmt = "inherit" ident { ident }
        if self._is_ident("inherit", t):
            return self._inherit_stmt()

        # edge = ref "->" ref { "->" ref } [ ":" string ]   (try before node/decl)
        edge = self._try_edge()
        if edge is not None:
            return edge

        # node_decl = "node" name block
        if self._is_ident("node", t) and self._lookahead_node():
            return self._node_decl()

        # decl = { annotation } kind name [ signature ] block
        if self._is_op("@") or (t.kind == "IDENT" and t.value in _KIND_SET
                                and self._lookahead_decl()):
            return self._decl()

        # app = ref [ "(" ... ")" ] [ record ]
        if t.kind == "IDENT":
            return self._app()

        self._err("a statement")

    # --- lookahead predicates (mirror PEG ordered choice disambiguation) -- #

    def _peek_after_ident_chain(self, start):
        """Given index `start` at an IDENT, skip a dotted ref (ident { . ident })
        WITHOUT consuming; return index just past it."""
        j = start
        if self.toks[j].kind != "IDENT":
            return start
        j += 1
        while self._is_op(".", self.toks[j]) and self.toks[j + 1].kind == "IDENT":
            j += 2
        return j

    def _lookahead_field(self):
        # `field` ident ":"
        j = self.i + 1
        if self.toks[j].kind != "IDENT":
            return False
        return self._is_op(":", self.toks[j + 1])

    def _lookahead_grant(self):
        # `grant` ident   (at least one ident follows)
        return self.toks[self.i + 1].kind == "IDENT"

    def _lookahead_order(self):
        # `order` ident "<"   (order_chain needs '<' as its second token)
        j = self.i + 1
        if self.toks[j].kind != "IDENT":
            return False
        return self._is_op("<", self.toks[j + 1])

    def _lookahead_assign(self):
        # ident assign_op   (assignment target is a BARE ident, not dotted)
        return self.toks[self.i + 1].kind == "OP" and \
            self.toks[self.i + 1].value in ("=", "?=")

    def _lookahead_node(self):
        # `node` name "{"  — distinguish from a bare ref `node` / edge `node ->`.
        j = self.i + 1
        nt = self.toks[j]
        if nt.kind == "IDENT" or nt.kind == "STRING":
            return self._is_op("{", self.toks[j + 1])
        return False

    def _lookahead_decl(self):
        # kind name [signature] "{"  — name is ident|string, then '(' or '{'.
        j = self.i + 1
        nt = self.toks[j]
        if not (nt.kind == "IDENT" or nt.kind == "STRING"):
            return False
        k = j + 1
        return self._is_op("{", self.toks[k]) or self._is_op("(", self.toks[k])

    # --- statement forms ------------------------------------------------- #

    def _field_decl(self):
        """field_decl = "field" ident ":" type [ "{" { refinement } "}" ]."""
        self.i += 1                       # 'field'
        name = self._expect_ident().value
        self._expect_op(":")
        ty = self._type()
        refinements = []
        if self._is_op("{"):
            self.i += 1
            self._skip_nl()
            while not self._is_op("}"):
                if self._at_eof():
                    self._err("'}' to close refinement list")
                refinements.append(self._refinement())
                self._skip_nl()
            self.i += 1                   # '}'
        return FieldDecl(name, ty, refinements)

    def _refinement(self):
        """refinement = required | optional | nonempty | default "=" expr
                       | oneof list | cmp_ref | range_ref | matches regex."""
        self._skip_nl()
        t = self.toks[self.i]
        if self._is_ident("required", t) or self._is_ident("optional", t) \
                or self._is_ident("nonempty", t):
            self.i += 1
            return (t.value,)
        if self._is_ident("default", t):
            self.i += 1
            self._expect_op("=")
            return ("default", self._expr())
        if self._is_ident("oneof", t):
            self.i += 1
            return ("oneof", self._list())
        if self._is_ident("matches", t):
            self.i += 1
            self._skip_nl()
            r = self.toks[self.i]
            if r.kind != "REGEX":
                self._err("a /regex/ literal after `matches`")
            self.i += 1
            return ("matches", r.value)
        # cmp_ref = ( ">=" | "<=" | ">" | "<" ) number
        for op in _CMP_OPS:
            if self._is_op(op, t):
                self.i += 1
                num = self._expect_number()
                return ("cmp", op, num)
        # range_ref = "in" number ".." number
        if self._is_ident("in", t):
            self.i += 1
            lo = self._expect_number()
            self._expect_op("..")
            hi = self._expect_number()
            return ("range", lo, hi)
        self._err("a refinement (required/optional/nonempty/default/oneof/"
                  "comparison/in/matches)")

    def _expect_number(self):
        self._skip_nl()
        t = self.toks[self.i]
        if t.kind != "NUMBER":
            self._err("a number")
        self.i += 1
        return t.value

    def _grant_decl(self):
        """grant_decl = "grant" ident { ident } ; line-bounded { ident }."""
        self.i += 1                       # 'grant'
        names = [self._expect_ident().value]
        # { ident } is line-bounded: a NEWLINE ends it (do NOT skip NEWLINE here).
        while self.toks[self.i].kind == "IDENT":
            names.append(self.toks[self.i].value)
            self.i += 1
        return GrantDecl(names)

    def _order_decl(self):
        """order_decl = "order" order_chain { ";" order_chain } ;
        chain is line-bounded but ';' continues across a newline."""
        self.i += 1                       # 'order'
        chains = [self._order_chain()]
        while True:
            # ';' may continue across a newline; first see if a ';' is reachable.
            save = self.i
            # do not skip NEWLINE to find ';' (a chain is line-bounded), but the
            # recognizer treats ';' itself as a separator that absorbs the NEWLINE
            # *after* it. So: a ';' must appear before any NEWLINE on this line.
            if self._is_op(";", self.toks[self.i]):
                self.i += 1
                self._skip_nl()           # ';' absorbs trailing newlines
                chains.append(self._order_chain())
                continue
            self.i = save
            break
        return OrderDecl(chains)

    def _order_chain(self):
        """order_chain = ident "<" ident { "<" ident } ; line-bounded."""
        # NEWLINE is significant here; do not skip it within the chain.
        t = self.toks[self.i]
        if t.kind != "IDENT":
            self._err("an identifier to start an order chain")
        names = [t.value]
        self.i += 1
        if not self._is_op("<", self.toks[self.i]):
            self._err("'<' in an order chain")
        while self._is_op("<", self.toks[self.i]):
            self.i += 1
            n = self.toks[self.i]
            if n.kind != "IDENT":
                self._err("an identifier after '<' in an order chain")
            names.append(n.value)
            self.i += 1
        return names

    def _inherit_stmt(self):
        """inherit_stmt = "inherit" ident { ident } ; line-bounded { ident }."""
        self.i += 1                       # 'inherit'
        names = [self._expect_ident().value]
        while self.toks[self.i].kind == "IDENT":
            names.append(self.toks[self.i].value)
            self.i += 1
        return InheritStmt(names)

    def _assignment(self):
        """assignment = ident assign_op expr."""
        target = self.toks[self.i].value
        self.i += 1
        op = self.toks[self.i].value      # '=' or '?='
        self.i += 1
        value = self._expr()
        return Assignment(target, op, value)

    def _node_decl(self):
        """node_decl = "node" name block."""
        kw = self.toks[self.i]            # 'node'
        self.i += 1
        name = self._name()
        stmts, close = self._block()
        return NodeDecl(name, stmts, kw.byteStart, close.byteEnd, kw.line, kw.col)

    def _try_edge(self):
        """edge = ref "->" ref { "->" ref } [ ":" string ].

        Try to parse an edge; if the ref is not followed by '->', backtrack.
        """
        save = self.i
        if self.toks[self.i].kind != "IDENT":
            return None
        first = self._ref()
        if not self._is_op("->"):
            self.i = save
            return None
        refs = [first]
        while self._is_op("->"):
            self.i += 1
            refs.append(self._ref())
        label = None
        if self._is_op(":"):
            self.i += 1
            self._skip_nl()
            t = self.toks[self.i]
            if t.kind != "STRING":
                self._err("a string label after ':' in an edge")
            self.i += 1
            label = _strip_string(t.value)
        return Edge(refs, label)

    # --- expressions ----------------------------------------------------- #

    def _expr(self):
        """expr = literal | list | record | app."""
        self._skip_nl()
        t = self.toks[self.i]
        if t.kind in ("STRING", "NUMBER", "PATH", "DURATION", "BYTES"):
            self.i += 1
            return _make_literal(t)
        if self._is_ident("true", t) or self._is_ident("false", t):
            self.i += 1
            return Literal("BOOL", t.value)
        if self._is_ident("null", t):
            self.i += 1
            return Literal("NULL", "null")
        if self._is_op("["):
            return self._list()
        if self._is_op("{"):
            return self._record()
        if t.kind == "IDENT":
            return self._app()
        self._err("an expression")

    def _app(self):
        """app = ref [ "(" [ arg { "," arg } ] ")" ] [ record ]."""
        ref = self._ref()
        args = None
        if self._is_op("("):
            args = self._paren_args()
        record = None
        if self._is_op("{"):
            record = self._record().entries
        return App(ref, args, record)

    def _paren_args(self):
        """"(" [ arg { "," arg } ] ")"  — newlines insignificant inside (lexer)."""
        self._expect_op("(")
        args = []
        if not self._is_op(")"):
            args.append(self._expr())
            while self._is_op(","):
                self.i += 1
                args.append(self._expr())
        self._expect_op(")")
        return args

    def _ref(self):
        """ref = ident { "." ident }."""
        self._skip_nl()
        t = self.toks[self.i]
        if t.kind != "IDENT":
            self._err("a reference (identifier)")
        parts = [t.value]
        start = t
        end = t
        self.i += 1
        while self._is_op(".") and self.toks[self.i + 1].kind == "IDENT":
            self.i += 1                   # '.'
            nt = self.toks[self.i]
            parts.append(nt.value)
            end = nt
            self.i += 1
        return Ref(parts, start.byteStart, end.byteEnd, start.line, start.col)

    def _list(self):
        """list = "[" [ expr { "," expr } ] "]"  — newlines insignificant inside."""
        self._expect_op("[")
        items = []
        if not self._is_op("]"):
            items.append(self._expr())
            while self._is_op(","):
                self.i += 1
                # tolerate a trailing comma before ']' (PEG `[ expr { , expr } ]`
                # would reject it, so keep strict): require an expr.
                items.append(self._expr())
        self._expect_op("]")
        return ListLit(items)

    def _record(self):
        """record = "{" { assignment | inherit_stmt } "}"."""
        self._expect_op("{")
        entries = []
        self._skip_nl()
        while not self._is_op("}"):
            if self._at_eof():
                self._err("'}' to close record")
            t = self.toks[self.i]
            if self._is_ident("inherit", t):
                entries.append(self._inherit_stmt())
            elif t.kind == "IDENT" and self._lookahead_assign():
                entries.append(self._assignment())
            else:
                self._err("an assignment or `inherit` in a record")
            self._skip_nl()
        self.i += 1                       # '}'
        return RecordLit(entries)

    # --- types ----------------------------------------------------------- #

    def _type(self):
        """type = type_atom { "|" type_atom } ; stored as flat text."""
        parts = [self._type_atom()]
        while self._is_op("|"):
            self.i += 1
            parts.append(self._type_atom())
        return TypeRef(" | ".join(parts))

    def _type_atom(self):
        """type_atom = qualname [ "<" type { "," type } ">" ]
                     | "(" [ type { "," type } ] ")" "->" type."""
        self._skip_nl()
        if self._is_op("("):
            self.i += 1
            inner = []
            if not self._is_op(")"):
                inner.append(self._type().text)
                while self._is_op(","):
                    self.i += 1
                    inner.append(self._type().text)
            self._expect_op(")")
            self._expect_op("->")
            ret = self._type().text
            return "(" + ", ".join(inner) + ") -> " + ret
        # qualname
        name = self._qualname()
        if self._is_op("<"):
            self.i += 1
            args = [self._type().text]
            while self._is_op(","):
                self.i += 1
                args.append(self._type().text)
            self._expect_op(">")
            return name + "<" + ", ".join(args) + ">"
        return name

    def _qualname(self):
        """qualname = ident { "." ident }."""
        t = self._expect_ident()
        parts = [t.value]
        while self._is_op(".") and self.toks[self.i + 1].kind == "IDENT":
            self.i += 1
            parts.append(self.toks[self.i].value)
            self.i += 1
        return ".".join(parts)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #

def _strip_string(tokval: str) -> str:
    """Strip the surrounding double quotes from a STRING token value."""
    if len(tokval) >= 2 and tokval[0] == '"' and tokval[-1] == '"':
        return tokval[1:-1]
    return tokval


def _make_literal(t: Token) -> Literal:
    if t.kind == "STRING":
        return Literal("STRING", _strip_string(t.value))
    return Literal(t.kind, t.value)


def parse(tokens, filename="<vaked>"):
    """Parse a token list into a list of top-level items (decls/imports)."""
    p = Parser(tokens, filename)
    items = p.parse_file()
    return items


def parse_source(src: str, filename="<vaked>"):
    """Tokenize then parse ``src``; raises VakedLexError / VakedSyntaxError."""
    toks = tokenize(src, filename)
    return parse(toks, filename)
````

## File: vakedc/resolve.py
````python
#!/usr/bin/env python3
"""vakedc.resolve — build the LPG from a parsed AST (0011 pipeline stages 1-2).

Walks the top-level items, instantiating one node per declaration (with byte-exact
provenance attached immediately), maintaining a lexically-scoped symbol table, and
collecting *refs* on a worklist tagged with their edge-label semantics. At end of
parse the worklist is resolved against the scope captured at each ref site (this
handles forward refs); a ref whose HEAD resolves to no in-file declaration produces
ONE external stub node per distinct dotted path.

Edge labels (by source-field semantics — only these become edges; every other ref
in props stays a plain value, we do NOT over-edge):

    contains             nesting: parent decl -> child decl / node
    imports              a `use "<path>"` import -> external stub for the path
    depends_on           refs in input / output / from / source / engine fields
    requires_capability  refs in `capabilities` lists; target = the domain.grant ref
    routes_to            mesh `->` edges; the optional ":" label string as a prop
    member_of            refs in a `parallel`'s `fibers` list

The symbol table is lexical: a ref's head is looked up from the innermost scope
outward. Top-level decls and each decl's direct child decls/nodes are bindings.
"""

from __future__ import annotations

import os

from . import parser as P
from .graph import Graph, GraphNode, GraphEdge, Provenance, Span, node_id

# Fields whose ref value(s) are data-flow dependencies.
_DEPENDS_FIELDS = frozenset(("input", "output", "from", "source", "engine"))


class _Scope:
    """A lexical scope: simple-name -> node id, with a parent link."""

    def __init__(self, parent=None):
        self.parent = parent
        self.bindings: "dict[str, str]" = {}

    def define(self, name: str, nid: str):
        self.bindings[name] = nid

    def lookup(self, name: str) -> "str | None":
        s = self
        while s is not None:
            if name in s.bindings:
                return s.bindings[name]
            s = s.parent
        return None


class _RefTask:
    """A deferred ref resolution captured with its lexical scope."""

    __slots__ = ("ref", "label", "source_id", "scope", "partner", "edge_props")

    def __init__(self, ref, label, source_id, scope, partner=None, edge_props=None):
        self.ref = ref
        self.label = label
        self.source_id = source_id
        self.scope = scope
        self.partner = partner            # for routes_to: the 'to' ref
        self.edge_props = edge_props or {}


class Resolver:
    def __init__(self, items, filename: str):
        self.items = items
        # filename for ids/provenance = basename (path-derived id stability).
        self.basename = os.path.basename(filename)
        self.provfile = filename
        self.graph = Graph(self.provfile)
        self.worklist: "list[_RefTask]" = []

    def build(self) -> Graph:
        root = _Scope()
        # Pre-define all top-level decl names so sibling/forward refs resolve.
        for it in self.items:
            if isinstance(it, P.Decl):
                root.define(it.name, node_id(self.basename, [it.name]))
        for it in self.items:
            if isinstance(it, P.Import):
                self._handle_import(it)
            elif isinstance(it, P.Decl):
                self._build_decl(it, [it.name], root, parent_id=None)
        self._resolve_worklist()
        return self.graph

    # --- imports --------------------------------------------------------- #

    def _handle_import(self, imp: P.Import):
        # `use "<path>"` -> imports edge from the file node to an external stub.
        file_id = f"{self.basename}#"
        if not self.graph.has_node(file_id):
            self.graph.add_node(GraphNode(
                id=file_id, kind="file", name=self.basename,
                labels=["file"], props={}, provenance=None,
            ))
        stub = self.graph.ensure_external(imp.path)
        self.graph.add_edge(GraphEdge(file_id, stub.id, "imports"))

    # --- declarations ---------------------------------------------------- #

    def _build_decl(self, decl: P.Decl, chain, scope: _Scope, parent_id):
        nid = node_id(self.basename, chain)
        prov = Provenance(
            file=self.provfile,
            decl=f"{decl.kind} {decl.name}",
            span=Span(decl.byteStart, decl.byteEnd, decl.line, decl.col),
        )
        props = {}
        if decl.signature is not None:
            props["signature"] = _signature_to_props(decl.signature)
        if decl.annotations:
            props["annotations"] = [_annotation_to_props(a) for a in decl.annotations]
        node = GraphNode(
            id=nid, kind=decl.kind, name=decl.name,
            labels=["decl", decl.kind], props=props, provenance=prov,
        )
        self.graph.add_node(node)
        if parent_id is not None:
            self.graph.add_edge(GraphEdge(parent_id, nid, "contains"))

        # New lexical scope for the body; pre-define child decl/node names.
        child_scope = _Scope(scope)
        for st in decl.body:
            if isinstance(st, (P.Decl, P.NodeDecl)):
                child_scope.define(st.name,
                                   node_id(self.basename, chain + [st.name]))
        self._build_body(decl, decl.body, chain, nid, child_scope)

    def _build_body(self, owner, stmts, chain, owner_id, scope):
        for st in stmts:
            self._build_stmt(owner, st, chain, owner_id, scope)

    def _build_stmt(self, owner, st, chain, owner_id, scope):
        if isinstance(st, P.Decl):
            self._build_decl(st, chain + [st.name], scope, parent_id=owner_id)
        elif isinstance(st, P.NodeDecl):
            self._build_node_decl(st, chain, owner_id, scope)
        elif isinstance(st, P.Edge):
            self._build_edge(st, scope, owner_id)
        elif isinstance(st, P.Assignment):
            self._build_assignment(owner, st, owner_id, scope)
        elif isinstance(st, P.App):
            pass  # bare app statement: no inter-node edge, keep graph minimal
        elif isinstance(st, P.FieldDecl):
            self._record_prop(owner_id, "field:" + st.name, _field_to_props(st))
        elif isinstance(st, P.GrantDecl):
            self._append_prop_list(owner_id, "grants", st.names)
        elif isinstance(st, P.OrderDecl):
            self._append_prop_list(owner_id, "order", [list(c) for c in st.chains])
        elif isinstance(st, P.OpenDecl):
            self._record_prop(owner_id, "open", True)
        elif isinstance(st, P.InheritStmt):
            self._append_prop_list(owner_id, "inherit", st.names)

    def _build_node_decl(self, nd: P.NodeDecl, chain, owner_id, scope):
        nid = node_id(self.basename, chain + [nd.name])
        prov = Provenance(
            file=self.provfile,
            decl=f"node {nd.name}",
            span=Span(nd.byteStart, nd.byteEnd, nd.line, nd.col),
        )
        node = GraphNode(
            id=nid, kind="node", name=nd.name,
            labels=["node"], props={}, provenance=prov,
        )
        self.graph.add_node(node)
        self.graph.add_edge(GraphEdge(owner_id, nid, "contains"))
        child_scope = _Scope(scope)
        for st in nd.body:
            if isinstance(st, (P.Decl, P.NodeDecl)):
                child_scope.define(st.name,
                                   node_id(self.basename, chain + [nd.name, st.name]))
        self._build_body(nd, nd.body, chain + [nd.name], nid, child_scope)

    def _build_edge(self, edge: P.Edge, scope, owner_id):
        # `a -> b -> c [: "label"]` : routes_to edges along consecutive pairs.
        edge_props = {"label": edge.label} if edge.label is not None else {}
        for a, b in zip(edge.refs, edge.refs[1:]):
            self.worklist.append(_RefTask(
                a, "routes_to", owner_id, scope, partner=b, edge_props=edge_props))

    # --- assignments ----------------------------------------------------- #

    def _build_assignment(self, owner, asn: P.Assignment, owner_id, scope):
        target, val = asn.target, asn.value
        if target in _DEPENDS_FIELDS:
            self._defer_value_refs(val, "depends_on", owner_id, scope)
        elif target == "fibers" and getattr(owner, "kind", None) == "parallel":
            self._defer_value_refs(val, "member_of", owner_id, scope)
        elif target == "capabilities":
            self._defer_value_refs(val, "requires_capability", owner_id, scope)
        prop_val = _value_to_props(val)
        if asn.op != "=":
            # Preserve the optional-assignment operator (`?=`, set-if-unset):
            # plain `=` stays a bare value (the default; nothing lost), so the
            # golden is unchanged, while `?=` is annotated — mirroring the
            # record-entry path, which always records `op`.
            prop_val = {"op": asn.op, "value": prop_val}
        self._record_prop(owner_id, target, prop_val)

    def _defer_value_refs(self, val, label, owner_id, scope):
        for r in _refs_in_value(val):
            self.worklist.append(_RefTask(r, label, owner_id, scope))

    # --- worklist resolution --------------------------------------------- #

    def _resolve_worklist(self):
        for task in self.worklist:
            if task.label == "routes_to":
                src = self._resolve_ref(task.ref, task.scope)
                dst = self._resolve_ref(task.partner, task.scope)
                self.graph.add_edge(
                    GraphEdge(src, dst, "routes_to", dict(task.edge_props)))
            else:
                tgt = self._resolve_ref(task.ref, task.scope)
                self.graph.add_edge(GraphEdge(task.source_id, tgt, task.label))

    def _resolve_ref(self, ref, scope: _Scope) -> str:
        """Resolve a ref to a node id; unresolvable -> external stub keyed by the
        full dotted path. Forward refs work because scopes are fully populated
        before the worklist runs.

        Two in-file forms resolve to a declaration node:
          * a bare name (``screenrec``) — looked up directly in scope;
          * a ``<kind>.<name>`` ref (``stream.screenrec``, ``index.zigbeeFirmware``)
            where ``kind`` is a Vaked kind keyword and ``name`` resolves in scope to
            a declaration of that kind. This is the addressing convention the type/
            lowering specs use (``index.zigbeeFirmware`` names the index decl).
        Everything else (``graph.workflow``, ``fs.repo_rw``, ``crabcc.markdown``)
        is external."""
        head = ref.head
        # bare in-file name -> its decl node
        if len(ref.parts) == 1:
            head_id = scope.lookup(head)
            if head_id is not None:
                return head_id
            return self.graph.ensure_external(ref.dotted).id
        # <kind>.<name> addressing of an in-file decl of that kind
        if len(ref.parts) == 2 and head in P._KIND_SET:
            target_id = scope.lookup(ref.parts[1])
            if target_id is not None:
                node = self.graph.get_node(target_id)
                if node is not None and node.kind == head:
                    return target_id
        # head in-file but a dotted member: only if the exact nested id exists
        if scope.lookup(head) is not None:
            candidate = node_id(self.basename, ref.parts)
            if self.graph.has_node(candidate):
                return candidate
        return self.graph.ensure_external(ref.dotted).id

    # --- prop helpers ---------------------------------------------------- #

    def _record_prop(self, owner_id, key, value):
        node = self.graph.get_node(owner_id)
        if node is not None:
            node.props[key] = value

    def _append_prop_list(self, owner_id, key, values):
        node = self.graph.get_node(owner_id)
        if node is not None:
            lst = node.props.setdefault(key, [])
            lst.extend(values if isinstance(values, list) else [values])


# --------------------------------------------------------------------------- #
# value -> props serialization (deterministic, plain JSON-able structures)
# --------------------------------------------------------------------------- #

def _value_to_props(v):
    if isinstance(v, P.Literal):
        return {"lit": v.kind.lower(), "value": v.value}
    if isinstance(v, P.ListLit):
        return [_value_to_props(x) for x in v.items]
    if isinstance(v, P.RecordLit):
        return {"record": [_entry_to_props(e) for e in v.entries]}
    if isinstance(v, P.App):
        out = {"ref": v.ref.dotted}
        if v.args is not None:
            out["args"] = [_value_to_props(a) for a in v.args]
        if v.record is not None:
            out["record"] = [_entry_to_props(e) for e in v.record]
        return out
    return {"unknown": repr(v)}


def _entry_to_props(e):
    if isinstance(e, P.Assignment):
        return {"assign": e.target, "op": e.op, "value": _value_to_props(e.value)}
    if isinstance(e, P.InheritStmt):
        return {"inherit": list(e.names)}
    return {"unknown": repr(e)}


def _is_bare_ref(x) -> bool:
    """A *bare* ref-app: a reference to another entity, NOT a call or a config
    block. `screenrec`, `stream.screenrec`, `fs.repo_rw` are bare refs;
    `github("x")` and `crabcc.semantic { ... }` are applications (values), not
    dependency references — so they do NOT become edges (don't over-edge)."""
    return isinstance(x, P.App) and x.args is None and x.record is None


def _refs_in_value(v):
    """Yield the bare-ref dependency targets in a value: the value itself if it is
    a bare ref-app, or the bare ref-app elements of a list literal. Function calls,
    config-block apps, refs nested in records / call args, and literals are NOT
    dependency targets (they live as plain props)."""
    out = []
    if _is_bare_ref(v):
        out.append(v.ref)
    elif isinstance(v, P.ListLit):
        for x in v.items:
            if _is_bare_ref(x):
                out.append(x.ref)
    return out


def _field_to_props(f: P.FieldDecl):
    return {"type": f.type.text, "refinements": [list(r) for r in f.refinements]}


def _signature_to_props(sig):
    params, ret = sig
    return {
        "params": [{"name": n, "type": t.text,
                    "default": (_value_to_props(d) if d is not None else None)}
                   for (n, t, d) in params],
        "return": (ret.text if ret is not None else None),
    }


def _annotation_to_props(a):
    _, name, args = a
    return {"name": name,
            "args": ([_value_to_props(x) for x in args] if args is not None else None)}


def build_graph(items, filename: str) -> Graph:
    return Resolver(items, filename).build()
````

## File: docs/language/references/session-2026-06-08-sparks.md
````markdown
# Reference sparks — 2026-06-08 session

New reference repos surfaced while scaffolding `vaked-base`. Captured here for the dedicated language/runtime sessions. (Complements [`parallel-reference-pack.md`](parallel-reference-pack.md) and the [reference map](../0003-reference-map.md).)

## Runtime / Zig foundations

- **[mitchellh/libxev](https://github.com/mitchellh/libxev)** — cross-platform, high-performance event loop: non-blocking IO, timers, events; Linux (io_uring or epoll), macOS (kqueue), Wasm+WASI; **Zig and C API**.
  - *Vaked relevance:* the async foundation for the Zig enforcement daemons (`sandboxd`, `agent-guardd`, `eventd`, `mcp-brokerd`). The C API also lets the OTP control plane and any C-FFI surface share one loop model. Strong default for [`docs/runtime`](../../runtime/README.md).

## Index / code-intelligence (CrabCC lineage)

- **[justrach/codedb](https://github.com/justrach/codedb)** — Zig code-intelligence server **and MCP toolset** for AI agents: tree, outline, symbol, search, read, edit, deps, snapshot, and remote GitHub repo queries.
  - *Vaked relevance:* directly parallels **CrabCC indexes** and the `index` membrane; an MCP-native indexer is a reference design for how `mcp-brokerd` could expose code-intelligence as brokered tools. Compare/contrast with `crabcc-labs/crabcc` (Rust + SQLite + Tantivy + tree-sitter).

## Native surfaces

- **[tonybanters/oxwm](https://github.com/tonybanters/oxwm)** — a window manager written in **Zig**.
  - *Vaked relevance:* a reference for native, Zig-built operator **surfaces** — compositor/WM-level control of how operator clients are presented. Complements the raylib-zig / zero-native surface sparks.

## Materialization target

- **MirageOS** — see the dedicated design note: [`0010-mirageos-unikernel-surface.md`](../0010-mirageos-unikernel-surface.md).
````

## File: docs/language/0003-reference-map.md
````markdown
# 0003: Reference Map

## Borrow from

- Nix: flakes, derivations, store integration.
- Nickel: records, contracts, mergeable config.
- CUE: constraints and validation.
- Dhall: total programmable config.
- Starlark: deterministic embedded language.
- Jsonnet/KCL/HCL: config-generation ergonomics.
- OPA/Rego: policy decisions as data.
- OTP: supervision vocabulary.
- Zig: explicit native systems posture.
- Zigbee: mesh/device/capability topology.
- CrabCC: raw indexes and reproducible catalogs.

## Where it lands

- **Type system (Goal 2)** — the structural+schema discipline, the *closed*
  constraint set (CUE/Nickel-flavoured but total, no predicate language), the
  capability attenuation order, generics, and the total/deterministic checking
  pipeline are specified in [`0011-type-system.md`](./0011-type-system.md), with
  the built-in catalog in [`../../vaked/schema/parallel-types.md`](../../vaked/schema/parallel-types.md)
  and the surface syntax in [`../../vaked/grammar/vaked-v0-plus.ebnf`](../../vaked/grammar/vaked-v0-plus.ebnf) (v0.3).
````

## File: docs/language/0012-lowering.md
````markdown
# 0012: Lowering — Validated Graph to Artifacts (Goal 3)

## Status

Normative. This note defines **lowering** — the stage that turns a *validated
typed semantic graph* (the output of the Goal-2 checker,
[`0011-type-system.md`](./0011-type-system.md) §6) into the **boring,
inspectable artifacts** Vaked owns, plus the **Nix spine** that wires, builds,
and deploys them. It is the specification for the **Goal 3** lowering pass.

It is the direct successor to Goal 2: where 0011 stops at *"validated graph,
ready to lower,"* this note starts there and stops at *"artifacts on disk, with
provenance."* It realizes manifesto principles
([`0001-language-manifesto.md`](./0001-language-manifesto.md)) directly: *Compile
to boring artifacts*, *Validate before generating*, *Preserve provenance*,
*Explain everything*, *Support raw Nix escape hatches*, and *Keep evaluation
deterministic and side-effect-free*.

It is paired with three documents:

- **Type system** — [`0011-type-system.md`](./0011-type-system.md) defines the
  graph that lowering *consumes*. Lowering never re-checks and never runs on an
  invalid graph (§1).
- **Primitives** — [`0008-parallel-fibers-indexes-surfaces.md`](./0008-parallel-fibers-indexes-surfaces.md)
  introduces the declarations (`index`, `catalog`, `stream`, `fiber`, `surface`,
  `mesh`, `device`, `mediaPipeline`, `parallel`) and lists the *Compiler
  artifacts* this note maps each to.
- **Built-in catalog** — [`vaked/schema/parallel-types.md`](../../vaked/schema/parallel-types.md)
  is the schema/capability data; lowering reads schema-typed fields (e.g.
  `index.emit`, `fiber.policy`, `index.trust = pinned{…}`) but adds no new
  vocabulary. The surface syntax is [`vaked/grammar/README.md`](../../vaked/grammar/README.md)
  (v0.3); **lowering requires no grammar changes** — every selector it uses
  (`emit` targets, `nix("…")`) is already writable.

Worked, hand-authored **expected-output fixtures** for `operator-field.vaked`
live in [`vaked/examples/lowering/`](../../vaked/examples/lowering/) (no compiler
exists yet; the fixtures are the spec-by-example).

### Scope (what this is NOT)

To keep the mantra intact (*Vaked declares. Nix materializes. Zig enforces. eBPF
testifies.*), lowering is deliberately bounded:

- **No fetching, no build, no deploy.** Lowering emits *text*. Fetching sources,
  building Zig daemons, and activating NixOS configurations are the **Nix
  build's** job (§4), pinned by `flake.lock` derived from `trust = pinned{…}`.
  Lowering performs **no network and no IO beyond writing the declared output
  tree** (§2).
- **No re-checking.** Lowering assumes a valid graph (0011 §6). It does not
  re-run conformance, constraints, generics, or capability flow. A graph that
  failed checking is never lowered.
- **No new computation.** Lowering is pure graph→text rendering. It has no
  interpreter, no eval, no arithmetic on user values beyond structural
  projection of already-typed nodes (§2.4). The closedness boundary of 0011 §6.2
  extends here: if a target *seems* to need eval-time logic, that is a language
  question, not an emitter feature (§9).
- **No concrete mappings for the deferred targets.** eBPF policy manifests, OTel
  config, systemd units, and surface launcher configs get an **emitter interface
  slot** and a *contract* for what their mapping must eventually cover (§7);
  the mappings themselves are deferred.
- **No runtime semantics.** What the artifacts *do* once running (supervision,
  enforcement, audit) is the daemons' job ([`docs/runtime/README.md`](../runtime/README.md)),
  out of scope here.

---

## 1. Pipeline placement

Lowering is the stage **after** 0011's check. The full Vaked pipeline is:

```text
source text
    │  parse → resolve → elaborate → check        (0011 §6 — Goal 2)
    ▼
validated typed semantic graph   ── or ──▶  diagnostic set  (stop; nothing lowered)
    │  lower                                       (this note — Goal 3)
    ▼
artifact tree  (gen/ direct artifacts + Nix spine)  +  .vaked/provenance.json
```

Lowering runs **only** on a graph that produced *no* diagnostics (0011 §6.1:
*"A valid file's typed semantic graph is the hand-off to Goal 3 lowering …
nothing is lowered from an invalid graph."*). This is the manifesto principle
*Validate before generating* made structural: validation strictly precedes
generation, and the two stages share no error path — by the time lowering runs,
every node is typed, every ref is resolved, every default is inserted, every
union arm is selected, and every capability edge has been shown to attenuate.

Concretely, lowering consumes exactly the artifact 0011 §6.1 stage 3
(*elaborate*) builds and stage 4 (*check*) blesses:

- **nodes** — one per declaration, typed by its kind-schema, with defaults
  inserted (0011 §1.2), union arms selected (0011 §2.2), and generic parameters
  bound (0011 §5);
- **edges** — refs (data flow, e.g. `fiber.input = stream.screenrec`) and
  delegations (authority flow, e.g. a `mesh` edge);
- **source spans** — every node and edge carries the byte/line span of the AST
  node it came from (0011 §6.5); lowering propagates these into provenance (§6)
  without consulting source text again.

Lowering reads this graph and the **pinned inputs** recorded on it (`index.trust
= pinned{…}`, the resolved `engine` derivations). It writes the artifact tree.
That is the whole contract.

---

## 2. Lowering is pure, total, and hermetic

0011 §6 argues its checker is total + deterministic. Lowering inherits and
extends that discipline. The property we want is:

> **Lowering is a pure, total, hermetic function of (validated graph, pinned
> inputs).** The same graph and the same pinned inputs produce **byte-identical**
> artifacts, on any machine, with no observation of the outside world.

This section argues each adjective, in the style of 0011 §6.3–§6.4.

### 2.1 Determinism (same graph ⇒ byte-identical artifacts)

Lowering is a function `lower : (Graph, Pins) → (Files, Provenance)`. It is
deterministic because every input it reads is fixed by the graph, and every
choice it makes is a function of that input:

- **Ordering is canonical, not incidental.** Wherever lowering emits a sequence
  (modules in `flake.nix`, rows in a catalog, sections in `RUNTIME.md`, entries
  in `provenance.json`), it orders by a **stable key derived from the graph** —
  declaration source order for top-level decls (0011 preserves source order;
  cf. the `litanyfmt` rule that *encoding never depends on source order* but
  *emission follows source order* for readability), lexicographic order for
  set-like collections (e.g. capability grants, system doubles). Lowering never
  orders by hash-map iteration, wall-clock, or filesystem `readdir` order.
- **No ambient inputs.** Lowering reads no clock, no `$RANDOM`, no environment,
  no locale, no hostname, no UUID source. Timestamps, if a target format wants
  one, are **not** emitted (a generated header names the *source decl*, not the
  time — §6.1); a build that needs a timestamp gets it from Nix at build time,
  not from lowering.
- **Hashes are over content, not over runs.** The `inputs-hash` recorded in
  provenance (§6.2) is a hash of the *pinned inputs and the projected node*, not
  of the run — so it too is reproducible.

This is the artifact-level analogue of 0011 §6.3: there, *"two checks of the same
file yield the same graph or the same diagnostics."* Here, *two lowerings of the
same graph yield the same bytes.*

### 2.2 Totality (lowering of a valid graph always terminates and succeeds)

Lowering of a **validated** graph is total: it terminates, and it does not fail.

- **Termination.** Lowering is a single bounded traversal. It visits each node
  once per emitter that selects it, and the emitter set is finite (§3, the
  registry). Each emitter folds a node (and its already-resolved neighbours)
  into text in finite steps — there is no fixpoint, no recursion on unbounded
  data, no user predicate to evaluate (contrast 0011 §6.2). The graph is a
  finite DAG of typed nodes; the traversal is finite.
- **No failure path on a valid graph.** Every condition that *could* make an
  emitter "not know what to do" — an unknown field, a missing required field, a
  dangling ref, a capability over-grant, a generic mismatch — is exactly a
  condition 0011 §6 already rejected. Because lowering runs only post-validation
  (§1), those conditions cannot occur. Lowering therefore has no diagnostics of
  its own for *graph* problems.

  The one residual error class is **environmental** and lives *outside* the pure
  function: the host filesystem rejects the write (permissions, disk full). That
  is an IO error of the writer, not a lowering diagnostic; the pure
  `(Graph,Pins) → Files` computation still succeeded. (Compilers that want a
  "what would I emit?" dry run can compute `Files` without writing them.)

  The only *deferred* targets (§7) are not failures: a `runtime` that declares,
  say, an OTel mapping simply has its OTel emitter slot produce **nothing yet**
  (an explicit, documented no-op), not an error.

### 2.3 Hermeticity (no network, no IO during lowering)

Lowering is **hermetic**: as a computation it performs no network access and no
filesystem reads of remote or unpinned content. The only IO is writing the
declared output tree (`gen/`, the spine files, `.vaked/`).

- **Fetching is the build's job, not lowering's.** When `index zigbeeFirmware`
  declares `trust = pinned { commit, sha256 }`, lowering does **not** fetch the
  repo. It *transcribes* the pin into a `flake.nix` input (§4.2); the actual
  fetch happens during `nix build`, gated by `flake.lock`. Likewise an
  `engine`'s `package = zig.build{…}` lowers to a derivation *reference*; the
  Zig compile runs in the Nix sandbox, not in lowering.
- **Sources are values, not effects.** `github("owner/repo")` and
  `raw.github("owner/repo","file")` are *already* typed `Source` values in the
  graph (0011 §2.3, the auxiliary catalog). Lowering reads the value; it never
  dereferences it.

This is the structural reason the mantra holds: **Vaked declares** (lowering
renders the declaration) and **Nix materializes** (the build fetches and
compiles). Pushing all fetching/building behind `flake.lock` is what lets
"same graph ⇒ byte-identical artifacts" coexist with real-world inputs that
*do* change: the inputs are pinned, so the graph fixes them.

### 2.4 What "no smuggled computation" means precisely

Lowering may **project** a typed node into text: read its fields, follow its
resolved refs, render scalars in the target format's lexical syntax, and
template fixed structure around them. Lowering may **not**:

- evaluate user expressions, arithmetic, or predicates (there are none to
  evaluate; 0011's constraint set is closed and already checked);
- derive a value that is not a structural function of the graph (e.g. it may not
  "compute a free port", "resolve DNS", "pick a default commit");
- read any input not on the graph or in `Pins`.

If a prospective target appears to require any of the above, that is the §9
stop-and-report boundary, mirroring 0011 §6.2: the answer is a *language* change
(a new typed, closed field that carries the needed value explicitly), never an
escape hatch inside an emitter.

---

## 3. Emitters and the registry

### 3.1 Emitter interface

An **emitter** is a pure function:

```text
emit : (Graph, Nodes) → (Files, ProvenanceEntries)

  Graph   : the whole validated typed semantic graph (read-only)
  Nodes   : the subset of nodes this emitter is responsible for
  Files   : a set of { path, bytes } rooted at the output tree
  ProvenanceEntries : one entry per emitted artifact (or region), §6
```

`Graph` is passed whole (read-only) so an emitter can follow a node's resolved
refs — e.g. the `fiber` emitter reads `mediaCompress` *and* follows
`input = stream.screenrec` to that stream node — without re-resolving anything;
the edges are already in the graph. `Nodes` is the emitter's *assignment*, fixed
by selection (§3.3).

One emitter owns one **target**. Targets are the entries of the 0008 *Compiler
artifacts* list, partitioned in §3.4/§7 into *implemented*, *the spine*, and
*deferred*.

### 3.2 Constraints — what an emitter may NOT do

These are the rules that make §2 hold per-emitter. They are normative.

1. **No IO** other than returning `Files`. An emitter does not read files, open
   sockets, spawn processes, or read environment/clock/random. (It returns bytes;
   the driver writes them.)
2. **No nondeterminism.** Given the same `(Graph, Nodes)` an emitter returns
   byte-identical `Files`. All ordering is by a stable graph-derived key (§2.1).
   No hash-map iteration order, no time, no UUIDs.
3. **No graph mutation.** `Graph` and `Nodes` are read-only. An emitter may not
   add/remove/retype nodes or edges, insert defaults, or re-resolve refs — all
   of that already happened in elaboration (0011 §6.1 stage 3). Emitters cannot
   communicate through the graph.
4. **No cross-emitter state / no ordering dependence.** Emitters do not share
   mutable state and may run in any order (or in parallel). The output is the
   *union* of their `Files`; paths must not collide across emitters (the
   partition of targets guarantees this — each owns a distinct path namespace,
   §3.4).
5. **No re-checking and no new diagnostics for graph problems.** A valid graph
   cannot present an emitter with an illegal input (§2.2). An emitter therefore
   has no error path for graph content; a deferred emitter produces an explicit
   no-op, not an error.
6. **No new vocabulary.** An emitter reads only schema-defined fields and
   built-in auxiliary values (0011 §2.3). It introduces no field or selector that
   the grammar/schema doesn't already define.

A useful test (the "registry test"): **adding an emitter touches no core.** A
new target is a new function plus one registry row; nothing else in lowering, in
0011, or in the grammar changes. If adding a target *would* require a core
change, the target is asking for something the language doesn't express — see §9.

### 3.3 `emit`-driven selection

Which emitters run is a function of the graph, in two layers:

- **The Nix-spine emitter ALWAYS runs.** Every runtime lowers to a flake +
  NixOS module(s) (§4); there is no `emit` toggle for the spine. (This is what
  makes the output deployable rather than a loose pile of files.)
- **Direct emitters are selected by declared `emit` targets.** A declaration
  that carries an `emit` field (the schema permits it on `index` and `catalog`)
  names its desired artifacts as built-in `ArtifactTarget` values; each names
  exactly one direct emitter:

  | `emit` target (built-in value) | direct emitter (target) |
  |--------------------------------|--------------------------|
  | `catalog.jsonl`                | catalog → JSONL          |
  | `catalog.sqlite`               | catalog → SQLite         |
  | `nix.derivation`               | CrabCC index derivation (folded into the spine, §5) |
  | `sqlite("./path.db")`          | catalog → SQLite at the given path |

  So `index zigCorpus { … emit = [catalog.jsonl, catalog.sqlite,
  nix.derivation] }` selects the JSONL emitter, the SQLite emitter, and the
  CrabCC-derivation emitter **for that node**. An `index` with no `emit` (e.g.
  `zigbeeFirmware`) selects no direct catalog emitter — it still contributes its
  pinned `trust` input to the spine (§4.2) and can be the `from` of a separate
  `catalog` decl (which carries its own `emit`).

- **`RUNTIME.md` is emitted once per `runtime`.** The generated-docs emitter
  (§5.1) is not `emit`-gated either: documenting the runtime is unconditional
  ("explain everything"). It is selected by the presence of the `runtime` node,
  not by an `emit` value.

Selection is therefore *entirely* a read of the graph: spine + docs are
structural; direct artifacts follow `emit`. No grammar change is needed because
`emit = [ … ]` is already the writable selector (0011 §2.3 lists `catalog.jsonl`,
`catalog.sqlite`, `nix.derivation` as built-in `ArtifactTarget` values).

### 3.4 The registry

The registry is a static table `target → emitter`, partitioned three ways:

```text
ALWAYS (structural — run on presence of the node):
  nix.spine        runtime, + all build/wire inputs   → flake.nix, NixOS module(s)   §4
  docs.runtime     runtime                              → gen/RUNTIME.md               §5.1

emit-SELECTED (direct artifacts in gen/, run when an emit target names them):
  catalog.jsonl    index/catalog (emit ∋ catalog.jsonl)   → gen/catalog/<name>.jsonl  §5.3
  catalog.sqlite   index/catalog (emit ∋ catalog.sqlite)  → gen/catalog/<name>.sql    §5.3
  crabcc.index     index        (emit ∋ nix.derivation)   → crabcc index drv (in spine) §5.3
  zig.daemoncfg    fiber/engine                            → gen/zig/<name>.json        §5.2

DEFERRED (interface slot defined; mapping deferred — §7):
  ebpf.policy      mesh/capability grants    → (no-op today)
  otel.config      stream/observe            → (no-op today)
  systemd.units    fiber/parallel/surface    → (no-op today)
  surface.launcher surface                   → (no-op today)
```

Adding a row is adding an emitter. Removing the deferral on a deferred row is
replacing its no-op body with a real mapping — still no core change.

> Note on `zig.daemoncfg` selection: a fiber's Zig daemon config (§5.2) is part
> of *materializing the fiber on the runtime* and is emitted as part of wiring
> the runtime (it is referenced by the NixOS module as an installed file). It is
> grouped with the direct `gen/` artifacts because it lands in `gen/zig/` and is
> independently inspectable; it is not `emit`-gated (a fiber has no `emit`
> field), it is selected by the presence of the fiber node under a runtime.

---

## 4. The Nix spine

The Nix spine is the always-emitted backbone: a `flake.nix` plus one or more
NixOS modules that **wire, build, and deploy** the artifacts Vaked owns. It is
the structural realization of *Nix materializes*.

### 4.1 `flake.nix` outputs

The emitted `flake.nix` has these outputs, each a function of the runtime node:

```text
inputs              pinned, never moving: nixpkgs at the toolchain baseline rev +
                    one input per source (explicit rev when the decl pins it) / engine src (§4.1, §4.2)
nixosModules.<runtime>   the wiring module(s) for this runtime (§4.3)
packages.<system>.*      built Zig daemons & engines (e.g. zigDaemon, zigimg) +
                         CrabCC index derivations (from emit = nix.derivation, §5.3)
devShells.<system>.default   a shell with the toolchains the runtime needs
apps.<system>.*          surface launchers (deferred body, §7) + nix("…") apps (§8)
```

`<system>` ranges over the runtime's `systems` field (e.g. `"x86_64-linux"`,
`"aarch64-linux"` for `operator-field`) — `flake.nix` iterates them with the
conventional `forAllSystems`/`eachSystem` idiom. The mapping from declaration to
output:

| Vaked node | flake output |
|------------|--------------|
| `runtime <name>` | `nixosModules.<name>`, and the `forAllSystems` scaffold |
| `engine <e>` / fiber `engine = <e>` | `packages.<system>.<e>` (the built derivation) |
| `index` with `emit ∋ nix.derivation` | `packages.<system>.<index>-crabcc-index` (§5.3) |
| `surface <s>` | `apps.<system>.<s>` (launcher; deferred body §7) |
| `app nix("…")` | `apps.<system>.<name>` verbatim (§8) |
| `parallel`/`fiber`/`stream` | wired in the NixOS module (§4.3), not a flake output by themselves |

**Inputs are pinned, never moving (normative).** The emitted `inputs` set never
references a moving channel ref (e.g. `nixos-unstable`). Specifically:

- An input emitted for a **source decl that pins itself** (`trust = pinned{…}`)
  uses the author-asserted explicit `rev` from `trust.pinned.commit` (§4.2).
- **`nixpkgs`** is emitted pinned to the **toolchain's pinned baseline rev** — an
  explicit 40-hex rev fixed by the Vaked toolchain release, not a channel name —
  so two lowerings of the same graph under the same toolchain emit byte-identical
  `inputs` (§2.1). (Lowering does not *resolve* the rev; the toolchain hands it
  the baseline rev as a pin, exactly as it hands over `Pins` for engines, §1.)
- An **unpinned source decl** (no `trust`, e.g. the `github(…)` list in
  `zigCorpus`) is still emitted as an input, but with no author-asserted digest;
  its concrete rev is recorded by the lock step (§4.2).

The committed **`flake.lock`** — produced at first `nix build`, not by lowering —
records the *full* resolution: the pinned revs above plus the resolved revs for
unpinned inputs. Lowering emits the pinned `inputs`; the build writes the lock.
(No `flake.lock` fixture is committed here because lowering does not emit it —
§2.3, §4.2; the README notes this.)

### 4.2 `trust = pinned{…}` → flake inputs + `flake.lock`

This is the load-bearing mapping for hermeticity (§2.3). A pinned source becomes
a flake input whose revision is fixed, and the fix is recorded in `flake.lock`.

For `index zigbeeFirmware { source = raw.github("Koenkk/zigbee-OTA",
"index.json"); trust = pinned { commit = "<commit>"; sha256 = "<sha256>" } }`,
lowering emits:

```nix
# in flake.nix inputs:
inputs.zigbeeFirmware-src = {
  url   = "github:Koenkk/zigbee-OTA/<commit>";   # commit from trust.pinned.commit
  flake = false;                                  # raw source, not a flake
};
```

and the corresponding `flake.lock` node pins `rev = "<commit>"` and
`narHash`/`sha256 = "<sha256>"` (from `trust.pinned.sha256`). The rules:

- **`trust.pinned.commit` → the input's pinned `rev`** (in the URL and in
  `flake.lock`).
- **`trust.pinned.sha256` → the input's content hash** in `flake.lock`
  (`narHash`/`sha256`), so `nix build` verifies the fetch against the declared
  digest. A mismatch is a *build-time* failure, exactly where fetching happens —
  never a lowering failure (§2.2).
- **An unpinned `index` source** (e.g. the `github(…)` list in `zigCorpus`,
  which carries `normalize`/`emit` but no `trust`) still becomes a flake input,
  but its lock entry is the conventional flake-managed pin (Nix records the rev
  it resolved at lock time). `trust = pinned{…}` is the *author-asserted* pin;
  its presence makes the digest part of the declaration rather than of the lock
  step.

Either way the **graph fixes the inputs** and the **build fetches them** —
lowering only transcribes. This is precisely why §2.1's "same graph ⇒
byte-identical artifacts" survives contact with mutable upstreams.

### 4.3 NixOS module(s) — wiring the daemons

`nixosModules.<runtime>` is the wiring layer. It does **not** re-declare policy;
it *installs* the direct-emitted `gen/` artifacts and points the runtime's
daemons at them. The runtime materializes onto the daemon roster
([`docs/runtime/README.md`](../runtime/README.md)): an OTP control plane
(`agent-supervisord`) supervising single-purpose Zig daemons, with the membranes
of [`PROJECT_CONTEXT.md`](../context/PROJECT_CONTEXT.md) enforced by the named
daemons.

For `operator-field`, the implied wiring (from its decls) is:

| Vaked node | Wired onto (roster) | Module does |
|------------|---------------------|-------------|
| `parallel "operator-runtime"` (`supervisor = otp`) | `agent-supervisord` (OTP) | declares the supervision group over the fibers, `strategy = "supervised-dag"` |
| `fiber mediaCompress` (`output = artifacts.compressedMedia`) | `fs-snapshotd` (filesystem membrane — artifact capture) | installs `gen/zig/mediaCompress.json` (§5.2) and sets the daemon's config path to it |
| `stream ebpfEvents` (`source = agentGuardd.ringbuf`) | `agent-guardd` (ebpf membrane) | references the ringbuf channel as the stream source |
| `stream screenrec` (`source = agentpipe.screenrec`) | media capture (agentpipe) → `fs-snapshotd` | wires the screen-capture channel into `mediaCompress` |
| `surface operatorMap` (`mode = raylib`) | operator surface | references `apps.<system>.operatorMap` (launcher deferred, §7) |

The module references each `gen/` artifact as an **installed file** (e.g.
`environment.etc."vaked/zig/mediaCompress.json".source = ./gen/zig/mediaCompress.json;`
or the equivalent per-daemon option), so the inspectable artifact on disk is the
*same bytes* the daemon consumes — no second source of truth.

> The eBPF policy manifest, OTel collector config, systemd unit details, and the
> surface launcher body that this module would ultimately reference are
> **deferred** (§7). The module slot that references them exists; the artifacts
> themselves are no-ops today.

---

## 5. Direct artifacts (`gen/`) and the three exemplar mappings

Direct artifacts are the files Vaked emits and owns, landing in **`gen/`**
(committed and inspectable). Each carries the generated header (§6.1). Three
exemplars are specified field-by-field below; the deferred targets (§7) are
interface-only.

### 5.1 Exemplar 1 — Generated docs: `gen/RUNTIME.md`

`RUNTIME.md` is a human-readable rendering of the `runtime` node — the
"explain everything" artifact. It is a pure projection of the graph into prose +
tables; it introduces no information not in the graph.

Sections, in this fixed order (each a projection of the named node-kind):

1. **Header & summary** — runtime name, `systems`.
2. **Indexes** — one row per `index`: name, `source`(s), `normalize`/`chunk` if
   present, `trust` (pinned commit, abbreviated) if present, `emit` targets.
3. **Streams** — one row per `stream`: name, `source` channel, `type`,
   `retention`/`fps` if present.
4. **Fibers** — one row per `fiber`: name, `engine`, `input` ref, `output` ref,
   policy summary.
5. **Surfaces** — one row per `surface`: name, `mode`, `fps`, `input` refs,
   `views`.
6. **Parallel groups** — one row per `parallel`: name, member fibers,
   `strategy`, `supervisor`.
7. **Capability grants** — per principal (mesh node / fiber), the grant-set
   (0011 §4.3); for `operator-field` this is sparse (no `mesh` decl), so the
   section renders the daemon-channel uses the streams imply (e.g. consuming
   `agentGuardd.ringbuf` *uses* an `ebpf` grant) and is otherwise "none
   declared." Decl-level provenance points each row back to its source span.

Ordering within each section is source order of the decls. No timestamps; the
header (§6.1) names the source, not the time.

### 5.2 Exemplar 2 — Zig daemon config: `gen/zig/<fiber>.json`

A `fiber` (with its `engine`) lowers to a **JSON** config file consumed by the
Zig daemon that runs the fiber. JSON is chosen because the Zig daemons parse a
small, well-specified config format and JSON serializes deterministically once a
canonical key order is fixed (see §2.1); the generated header is a leading
`"_generated"` string field (JSON has no comments — §6.1 adapts the header per
format).

For `operator-field`, `fiber mediaCompress` (`output =
artifacts.compressedMedia`) is the artifact-producing fiber; its config is
consumed by **`fs-snapshotd`** (the filesystem-membrane daemon responsible for
artifact capture, per the roster). Field-by-field mapping from the `fiber`
schema (and the linked `stream`/`engine` nodes):

| Vaked source (graph) | Config field | Value for `mediaCompress` |
|----------------------|--------------|----------------------------|
| `fiber.engine` (ref → engine node) | `engine` | `"zigimg"` |
| resolved engine package (Pins) | `engine_package` | the `packages.<system>.zigimg` store-path *reference* (resolved by Nix at build; lowering writes the attr name, not a path — §2.3) |
| `fiber.input` (ref → `stream.screenrec`) | `input.stream` / `input.source` | `"screenrec"` / `"agentpipe.screenrec"` |
| `stream.screenrec.type` | `input.type` | `"Media.Frame"` |
| `stream.screenrec.fps` | `input.fps` | `10` |
| `fiber.output` | `output.target` | `"artifacts.compressedMedia"` |
| `fiber.policy.strip_metadata` | `policy.strip_metadata` | `true` |
| `fiber.policy.max_pixels` | `policy.max_pixels` | `"4K"` |
| `fiber.policy.formats` | `policy.formats` | `["png","webp"]` |
| `fiber.budget` (optional, absent) | `budget` | omitted |
| `fiber.observe` (default `false`) | `observe` | `false` |

Every field is a direct projection of an already-typed node field or a resolved
ref. There is no computed value: `engine_package` is an *attribute name* the
NixOS module/flake resolves, not a path lowering computes (§2.3, §2.4).

**Key order is fixed schema order, not sorted (normative).** Keys are emitted in
the order of the field table above — that table's row order **is** the canonical
key order — *not* lexicographically sorted. `"_generated"` (§6.1) is always the
first member. An **absent optional field is omitted entirely**, not emitted as
`null` (e.g. `mediaCompress` declares no `budget`, so the config has no `budget`
key — see [`gen/zig/mediaCompress.json`](../../vaked/examples/lowering/gen/zig/mediaCompress.json)).
Nested objects (`input`, `output`, `policy`) follow the sub-field order shown in
their table rows. The same mapping shape applies to any fiber; `mediaCompress` is
the worked instance.

### 5.3 Exemplar 3 — CrabCC index + catalog

An `index` (optionally with a `catalog` built `from` it) lowers to a **CrabCC
index derivation** plus the **SQLite/JSONL catalog artifacts** its `emit`
selects. This is the *CrabCC indexes* leg of the mantra.

Selection (per §3.3): the emitter set for `index zigCorpus { emit =
[catalog.jsonl, catalog.sqlite, nix.derivation] }` is {JSONL, SQLite,
CrabCC-derivation}.

**a. CrabCC index derivation** (`emit ∋ nix.derivation`). Folded into the spine
as `packages.<system>.zigCorpus-crabcc-index`. The derivation runs CrabCC at
*build* time over the pinned sources; lowering only emits the derivation
expression. The `index` fields map to CrabCC options:

| Vaked `index` field | CrabCC option |
|---------------------|---------------|
| `source` (list of `github(…)` / `raw.github(…)`) | the input corpus (one fetched input per source, §4.2) |
| `normalize = crabcc.markdown` | CrabCC normalizer = `markdown` |
| `chunk = crabcc.semantic { max_tokens, overlap }` | CrabCC chunker = `semantic`, with `max_tokens`/`overlap` passed through (the `crabcc.semantic` record *is* the option struct, 0011 §2.3) |
| `schema = schema.<S>` (if present) | the item schema the rows are validated against |
| `trust = pinned{…}` (if present) | the input pin (§4.2) |

(`zigCorpus` has `normalize = crabcc.markdown` and no `chunk`; the `chunk` row
applies to indexes that carry it, e.g. the `zigRefs` form in 0008.)

**b. JSONL catalog** (`emit ∋ catalog.jsonl`) → `gen/catalog/zigCorpus.jsonl`.
One JSON object per indexed item, newline-delimited. The generated header is the
**first line**, a JSON object with a `_generated` key (§6.1), so the file stays
valid JSONL. Row shape follows the index's item schema (`T`, bound per 0011
§5.1); for an unschematized corpus it is CrabCC's default record shape.

**c. SQLite catalog** (`emit ∋ catalog.sqlite`, or a `catalog` decl with
`emit = sqlite("…")`) → `gen/catalog/<name>.sql` (a deterministic SQL schema +
`INSERT` script; the `.db` binary is built from it by the spine, keeping the
committed artifact a text diff). For a `catalog` decl, the `key` field maps to
the table's primary key / index:

| Vaked `catalog` field | SQLite artifact |
|-----------------------|------------------|
| `from = index.<I>` (binds `T`) | the table's column set = `T`'s fields |
| `key = ["a","b",…]` | `PRIMARY KEY (a, b, …)` / unique index |
| `emit = sqlite("./var/firmware.db")` | output path of the built `.db` |

The catalog's `T` must equal the source index's `T` (0011 §5.1) — already
checked, so the column set is unambiguous at lowering.

---

## 6. Provenance

Provenance is *Preserve provenance* + *Explain everything* made concrete, at
**decl-level granularity**. It has two parts: a per-artifact header and a
machine-readable map.

### 6.1 Per-artifact generated header

Every direct artifact carries, as its first line(s), a header naming the source.
The canonical text is:

```text
generated by Vaked from <file>:<decl> — do not edit
```

rendered in the **comment syntax of the target format** (the header is the same
information in every format; only the comment delimiter changes):

| Format | Header rendering |
|--------|------------------|
| Markdown (`RUNTIME.md`) | `<!-- generated by Vaked from operator-field.vaked:runtime operator-field — do not edit -->` |
| Nix (`flake.nix`) | `# generated by Vaked from operator-field.vaked:runtime operator-field — do not edit` |
| JSON (Zig config) | first member `"_generated": "generated by Vaked from operator-field.vaked:fiber mediaCompress — do not edit"` (JSON has no comments) |
| JSONL (catalog) | first line `{"_generated":"generated by Vaked from operator-field.vaked:index zigCorpus — do not edit"}` |
| SQL (catalog) | `-- generated by Vaked from operator-field.vaked:catalog firmware — do not edit` |

`<file>` is the source path; `<decl>` is the declaration kind + name that the
artifact is *primarily* derived from (the artifact's "owning" decl). The header
carries **no timestamp** (determinism, §2.1) — it names the source decl so a
reader (or a `vaked explain`) can jump straight back to it.

### 6.2 `.vaked/provenance.json` — schema

`.vaked/provenance.json` is the complete, machine-readable provenance map for a
lowering run. It maps **artifact path → list of entries**, one entry per
artifact or per *region* of an artifact (decl-level granularity: each region
attributes to exactly one source decl).

> **Erratum (vakedc lower, 2026-06-10).** The manifest lands at
> `<out>/provenance.json` — the root of the lowering output tree (alongside
> `flake.nix` and `gen/`), where `<out>` is the `--out` directory (default
> `.vaked/lower/`); lowering a repo in-place uses `<out> = .vaked/`, which is the
> `.vaked/provenance.json` this section names.

Schema (normative; this is itself emitted deterministically — §2.1):

```text
ProvenanceFile {
  version    : Int                 # schema version of this file (currently 1)
  source     : Path                # the .vaked source file lowered
  artifacts  : Map<Path, [Entry]>  # artifact path (relative to output root) → entries
}

Entry {
  region?     : String             # OPTIONAL: name/anchor of the region within the
                                    #   artifact (e.g. a flake output attr, a RUNTIME.md
                                    #   section, a catalog table). Absent ⇒ the entry
                                    #   covers the whole artifact.
  sourceFile  : Path               # the .vaked file the region came from
  decl        : String             # the source declaration: "<kind> <name>"
                                    #   (e.g. "fiber mediaCompress", "index zigCorpus")
  span        : Span               # the source span of that decl (from 0011 §6.5)
  emitter     : String             # the registry target that produced it
                                    #   (e.g. "zig.daemoncfg", "nix.spine", "docs.runtime",
                                    #    "catalog.jsonl", "catalog.sqlite", "crabcc.index")
  inputsHash  : String             # hash over (pinned inputs + projected node) for this
                                    #   region — reproducible (§2.1); ties the artifact to
                                    #   the exact inputs that produced it
}

Span {                             # identical shape to 0011 §6.5's diagnostic span
  file       : Path
  byteStart  : Int                 # byte offset of the decl's LEADING KEYWORD
  byteEnd    : Int                 # EXCLUSIVE: one byte past the decl's closing "}"
  line       : Int                 # 1-based line of byteStart
  col        : Int                 # 1-based column of byteStart
}
```

**`artifacts` map key order (canonical).** The top-level `artifacts` map is
emitted with its keys in **lexicographic order by artifact path**, comparing
paths by Unicode code point (byte order for the ASCII paths used here — so an
uppercase letter sorts before a lowercase one, e.g. `gen/RUNTIME.md` precedes
`gen/catalog/…`). This is the §2.1 "lexicographic order for set-like
collections" rule applied to the artifact map, and it makes the file's top-level
ordering a pure function of the artifact set, independent of emitter run order
(§3.2.4). (The per-artifact `[Entry]` lists are ordered by contributing-decl
source order, as elsewhere in §2.1.)

**`Span` convention (canonical).** A decl's `Span` is fixed as: `byteStart` =
the byte offset of the decl's **leading keyword** (the `runtime`/`index`/
`stream`/`fiber`/`surface`/`parallel` token, *not* the name or the `{`);
`byteEnd` = **exclusive**, i.e. one byte past the decl's closing `}`;
`line`/`col` are **1-based** and locate `byteStart`. (`[byteStart, byteEnd)` is a
half-open range, so `byteEnd − byteStart` is the decl's byte length.) This
matches 0011 §6.5 and is exactly what the fixture's spans encode.

Properties:

- **Decl-level.** Every `Entry.decl` names one declaration; every `Entry.span`
  is that decl's span. A single artifact built from several decls (e.g.
  `flake.nix`, `RUNTIME.md`) has *multiple* entries — one per contributing decl,
  distinguished by `region`. An artifact built from one decl (e.g.
  `gen/zig/mediaCompress.json`) has a single whole-artifact entry (no `region`).
- **Round-trippable to source.** `(sourceFile, span)` lets `vaked explain` (0011
  §6.5) jump from any artifact region to the exact source token — the same
  source-map mechanism, reused for output.
- **Reproducible.** `inputsHash` is content-addressed over the graph projection
  + pins, so re-lowering an unchanged graph yields the same hashes (§2.1).
- **`inputsHash` keys the resolved inputs of the *projection*, not the decl.**
  Two regions that attribute to the same `decl` can carry different
  `inputsHash`es when they project different resolved inputs: e.g. an
  engine-package region hashes the resolved engine's pinned inputs (the
  `packages.zigimg` flake output, even though its owning `decl` is the
  `fiber mediaCompress` that references the engine — see the fixture, where that
  region's hash is labelled `engine-zigimg`), while the fiber-config region for
  the same fiber hashes the fiber node's own projection. The hash keys *what the
  region was projected from*; `decl` keys *which source token it attributes to*.
- **Escape-hatch entries included.** A `nix("…")` app gets an entry too (§8),
  with `emitter = "nix.passthrough"`, so even verbatim Nix is attributed.

A worked excerpt consistent with this schema is in
[`vaked/examples/lowering/provenance.json`](../../vaked/examples/lowering/provenance.json).

---

## 7. Interface-stubbed (deferred) targets

These targets have a **registry slot and a contract**, but their mapping is
**deferred**. Each slot's emitter exists as an explicit no-op (§2.2, §3.2.5) —
emitting it produces nothing today, not an error. Defining the slot now keeps
the registry test honest (adding the real mapping later touches no core) and
records *what the mapping must cover* so it isn't reinvented.

| Target (registry) | Selected by | Mapping must eventually cover | Deferred because |
|-------------------|-------------|-------------------------------|------------------|
| `ebpf.policy` | `mesh` nodes + capability grants (0011 §4); network/ebpf membrane | per-principal allow/deny sets for network egress, file, and process events — compiled from the capability grant-sets — consumable by `agent-guardd` | the eBPF policy *format* and the grant→rule compilation are a daemon-design concern ([`docs/runtime/README.md`](../runtime/README.md)); no concrete format is approved yet |
| `otel.config` | `stream` with `observe`/telemetry intent; the OTel collector | mapping each observed stream/fiber to an OTel pipeline (receiver → processor → exporter) for `otelcol` | the OTel mapping needs the telemetry schema, not yet specified |
| `systemd.units` | `fiber`/`parallel`/`surface` needing host units | service units for the Zig daemons / surface processes, with the dependency order implied by `parallel.strategy` and `supervisor` | unit details depend on the daemon packaging, deferred with the daemons |
| `surface.launcher` | `surface` node | the launcher config/app that starts a `mode = raylib` surface with its `input`/`views` wired | the surface backend (raylib host integration) is not yet specified |

The `surface.launcher` slot is the one deferred target that still surfaces in the
spine today, because §4.1 makes `apps.<system>.<s>` a structural output of the
flake (the attribute is named for the surface decl). To keep the slot a genuine
no-op without leaving a dangling attribute, lowering emits a **deferred stub
app** derived from *nothing but the surface decl name*: an `apps.<system>.<s>`
whose `program` is a `writeShellScript` that exits non-zero after printing the
message `vaked: surface launcher lowering deferred (0012 §7)` to stderr. It wires no `input`,
no `views`, and **no engine/fiber package** (routing the launcher through an
unrelated fiber's engine would contradict §4.1 and this section). When the real
raylib mapping lands it replaces the stub body — still no core change (the §3.2
registry test). The fixture
([`vaked/examples/lowering/flake.nix`](../../vaked/examples/lowering/flake.nix),
`apps.operatorMap`) shows exactly this stub.

**Contract common to all four** (so the eventual emitters still satisfy §2/§3):
each must be a pure projection of already-typed graph nodes (no new computation,
§2.4); each lands either in `gen/` (a direct artifact, with a §6.1 header) or is
referenced by the NixOS module (§4.3); each contributes decl-level provenance
entries (§6.2). When a mapping lands, it replaces the no-op body and adds nothing
to the core — exactly the §3.2 registry test.

---

## 8. Escape hatch: `nix("…")` pass-through

The manifesto's *Support raw Nix escape hatches* is realized without any special
grammar (the grammar README is explicit: `nix("…")` is a *conventional `app`*
whose ref is the plain identifier `nix` and whose string argument is an opaque
Nix expression fragment — there is no special production for it).

Lowering treats a `nix("…")` app as **verbatim pass-through into the Nix spine**:

- The string argument is emitted **unchanged** (byte-for-byte) into the spine —
  typically as (or within) an `apps.<system>.<name>` output (§4.1), or wherever
  the app appears structurally. Lowering does **not** parse, validate, reformat,
  or evaluate the fragment — it is opaque (consistent with §2.4: lowering renders
  it, it does not compute it).
- The pass-through still gets a **provenance entry** (§6.2): an `Entry` with
  `decl` = the enclosing app/decl, `span` = the `nix("…")` app's source span, and
  `emitter = "nix.passthrough"`. So even hand-written Nix is attributed back to
  the exact source token, and a reviewer can see *which* output is an escape
  hatch versus Vaked-generated.

This keeps the escape hatch honest: it is *visible* (a distinct emitter in
provenance), *bounded* (it lands in the spine, surrounded by generated outputs
that still carry their own headers), and *non-magical* (opaque text in, opaque
text out — no smuggled computation).

---

## 9. The "no smuggled computation" stop rule

This note's analogue of 0011 §6.2. If, while specifying or implementing an
emitter, a target appears to require something beyond **pure graph→text
rendering** — evaluating a user predicate, computing a value not present in the
graph, reading an ambient input, fetching/derefencing a source, or mutating the
graph — that is **not** an emitter feature to add. **Stop and report it** as a
concern.

The correct resolution is one of:

1. **The value belongs in the graph.** Add a typed, closed field (a 0011 §3
   constraint-respecting field, or a new built-in `ArtifactTarget`/auxiliary
   value) that carries it *explicitly*, so the author declares it and the checker
   validates it. Lowering then merely projects it. (This is the 0011 §6.2 move —
   "propose a language change" — applied to Goal 3.)
2. **The work belongs to the build.** If it is genuinely effectful (fetching,
   compiling, resolving store paths), it belongs behind `flake.lock` in the Nix
   build (§2.3, §4.2), not in lowering.

Neither resolution adds an escape hatch *inside* an emitter. This boundary is
what keeps §2 (pure, total, hermetic) true as targets are added.

---

## 10. Cross-references

- [`0011-type-system.md`](./0011-type-system.md) — the checker; §6 produces the
  validated graph lowering consumes, and §6.2/§6.5 are mirrored here (§2, §6,
  §9).
- [`0008-parallel-fibers-indexes-surfaces.md`](./0008-parallel-fibers-indexes-surfaces.md)
  — the primitives and the *Compiler artifacts* list this note maps each to.
- [`0001-language-manifesto.md`](./0001-language-manifesto.md) — *Compile to
  boring artifacts*, *Preserve provenance*, *Validate before generating*,
  *Support raw Nix escape hatches*, *Explain everything*, *Keep evaluation
  deterministic and side-effect-free*.
- [`vaked/grammar/README.md`](../../vaked/grammar/README.md) — surface syntax;
  the `app`/`nix("…")` form (§8) and the `emit` selector (§3.3) are already
  writable — **no grammar change** for lowering.
- [`vaked/schema/parallel-types.md`](../../vaked/schema/parallel-types.md) — the
  schema fields lowering projects (`index.emit`, `fiber.policy`, `trust =
  pinned{…}`, etc.).
- [`docs/context/PROJECT_CONTEXT.md`](../context/PROJECT_CONTEXT.md) — the core
  stack (Vaked source → graph → artifacts → host) and the mantra this note
  realizes.
- [`docs/runtime/README.md`](../runtime/README.md) — the daemon roster the Nix
  spine wires onto (§4.3) and the deferred targets defer to (§7).
- [`vaked/examples/lowering/`](../../vaked/examples/lowering/) — hand-authored
  expected-output fixtures for `operator-field.vaked`.
````

## File: vaked/examples/engines/zig.vaked
````
engine zigDaemon(name: String, src: Path) -> Engine {
  package = zig.build {
    inherit src
    optimize = "ReleaseSafe"
  }

  check("smoke", "${package}/bin/${name} --help")
}
````

## File: vaked/examples/lowering/provenance.json
````json
{
  "version": 1,
  "source": "vaked/examples/operator-field.vaked",
  "artifacts": {
    "flake.nix": [
      {
        "region": "nixosModules.operator-field",
        "sourceFile": "vaked/examples/operator-field.vaked",
        "decl": "runtime operator-field",
        "span": { "file": "vaked/examples/operator-field.vaked", "byteStart": 27, "byteEnd": 1334, "line": 3, "col": 1 },
        "emitter": "nix.spine",
        "inputsHash": "sha256-fcf08006f8dcf4dca2c650d6f7fb38338ef3ec179366b4cc3576ab616abb4a81"
      },
      {
        "region": "inputs.zigbeeFirmware-src",
        "sourceFile": "vaked/examples/operator-field.vaked",
        "decl": "index zigbeeFirmware",
        "span": { "file": "vaked/examples/operator-field.vaked", "byteStart": 380, "byteEnd": 574, "line": 18, "col": 3 },
        "emitter": "nix.spine",
        "inputsHash": "sha256-bbd4c034b92e5674f4001f586b1d5a14bba35741b072aa04f2d84c30057a40f7"
      },
      {
        "region": "packages.zigCorpus-crabcc-index",
        "sourceFile": "vaked/examples/operator-field.vaked",
        "decl": "index zigCorpus",
        "span": { "file": "vaked/examples/operator-field.vaked", "byteStart": 103, "byteEnd": 376, "line": 6, "col": 3 },
        "emitter": "crabcc.index",
        "inputsHash": "sha256-2c1bdb46e566f6256c6b64b17311530b1fa6428e8aecec206d1b76f8777e4361"
      },
      {
        "region": "packages.zigimg",
        "sourceFile": "vaked/examples/operator-field.vaked",
        "decl": "fiber mediaCompress",
        "span": { "file": "vaked/examples/operator-field.vaked", "byteStart": 775, "byteEnd": 992, "line": 39, "col": 3 },
        "emitter": "nix.spine",
        "inputsHash": "sha256-6aa6a132cd5d6d097044af3dba8fc640b6bf2c1344aafe80c8a5a151ddb2295a"
      },
      {
        "region": "apps.operatorMap",
        "sourceFile": "vaked/examples/operator-field.vaked",
        "decl": "surface operatorMap",
        "span": { "file": "vaked/examples/operator-field.vaked", "byteStart": 996, "byteEnd": 1200, "line": 51, "col": 3 },
        "emitter": "nix.spine",
        "inputsHash": "sha256-d45067c376ee9cbba213726e3dfbdb9a75aad0e58e660623210595afc9f99d66"
      }
    ],
    "gen/RUNTIME.md": [
      {
        "region": "header",
        "sourceFile": "vaked/examples/operator-field.vaked",
        "decl": "runtime operator-field",
        "span": { "file": "vaked/examples/operator-field.vaked", "byteStart": 27, "byteEnd": 1334, "line": 3, "col": 1 },
        "emitter": "docs.runtime",
        "inputsHash": "sha256-fcf08006f8dcf4dca2c650d6f7fb38338ef3ec179366b4cc3576ab616abb4a81"
      },
      {
        "region": "indexes/zigCorpus",
        "sourceFile": "vaked/examples/operator-field.vaked",
        "decl": "index zigCorpus",
        "span": { "file": "vaked/examples/operator-field.vaked", "byteStart": 103, "byteEnd": 376, "line": 6, "col": 3 },
        "emitter": "docs.runtime",
        "inputsHash": "sha256-2c1bdb46e566f6256c6b64b17311530b1fa6428e8aecec206d1b76f8777e4361"
      },
      {
        "region": "indexes/zigbeeFirmware",
        "sourceFile": "vaked/examples/operator-field.vaked",
        "decl": "index zigbeeFirmware",
        "span": { "file": "vaked/examples/operator-field.vaked", "byteStart": 380, "byteEnd": 574, "line": 18, "col": 3 },
        "emitter": "docs.runtime",
        "inputsHash": "sha256-bbd4c034b92e5674f4001f586b1d5a14bba35741b072aa04f2d84c30057a40f7"
      },
      {
        "region": "streams/ebpfEvents",
        "sourceFile": "vaked/examples/operator-field.vaked",
        "decl": "stream ebpfEvents",
        "span": { "file": "vaked/examples/operator-field.vaked", "byteStart": 578, "byteEnd": 676, "line": 27, "col": 3 },
        "emitter": "docs.runtime",
        "inputsHash": "sha256-606b0b3dbcca0472cb7c4e5a2a0971c9fed4bff3f039a01e9d4ad1df9759e51e"
      },
      {
        "region": "streams/screenrec",
        "sourceFile": "vaked/examples/operator-field.vaked",
        "decl": "stream screenrec",
        "span": { "file": "vaked/examples/operator-field.vaked", "byteStart": 680, "byteEnd": 771, "line": 33, "col": 3 },
        "emitter": "docs.runtime",
        "inputsHash": "sha256-eb3863171bb1e1bb22e9a01c7e6e8acb136dd97e01da14d093865d7a86f480d9"
      },
      {
        "region": "fibers/mediaCompress",
        "sourceFile": "vaked/examples/operator-field.vaked",
        "decl": "fiber mediaCompress",
        "span": { "file": "vaked/examples/operator-field.vaked", "byteStart": 775, "byteEnd": 992, "line": 39, "col": 3 },
        "emitter": "docs.runtime",
        "inputsHash": "sha256-51b0e4bf66bb7007fbe727edf61e9fb4c2b2722cdc587299534d0b885f8886ef"
      },
      {
        "region": "surfaces/operatorMap",
        "sourceFile": "vaked/examples/operator-field.vaked",
        "decl": "surface operatorMap",
        "span": { "file": "vaked/examples/operator-field.vaked", "byteStart": 996, "byteEnd": 1200, "line": 51, "col": 3 },
        "emitter": "docs.runtime",
        "inputsHash": "sha256-d45067c376ee9cbba213726e3dfbdb9a75aad0e58e660623210595afc9f99d66"
      },
      {
        "region": "parallel/operator-runtime",
        "sourceFile": "vaked/examples/operator-field.vaked",
        "decl": "parallel operator-runtime",
        "span": { "file": "vaked/examples/operator-field.vaked", "byteStart": 1204, "byteEnd": 1332, "line": 58, "col": 3 },
        "emitter": "docs.runtime",
        "inputsHash": "sha256-bf3cb2d209719b0f273b4a7737f37cfb57437392a57f24b6ee81d931a9df29af"
      }
    ],
    "gen/catalog/zigCorpus.jsonl": [
      {
        "sourceFile": "vaked/examples/operator-field.vaked",
        "decl": "index zigCorpus",
        "span": { "file": "vaked/examples/operator-field.vaked", "byteStart": 103, "byteEnd": 376, "line": 6, "col": 3 },
        "emitter": "catalog.jsonl",
        "inputsHash": "sha256-2c1bdb46e566f6256c6b64b17311530b1fa6428e8aecec206d1b76f8777e4361"
      }
    ],
    "gen/zig/mediaCompress.json": [
      {
        "sourceFile": "vaked/examples/operator-field.vaked",
        "decl": "fiber mediaCompress",
        "span": { "file": "vaked/examples/operator-field.vaked", "byteStart": 775, "byteEnd": 992, "line": 39, "col": 3 },
        "emitter": "zig.daemoncfg",
        "inputsHash": "sha256-51b0e4bf66bb7007fbe727edf61e9fb4c2b2722cdc587299534d0b885f8886ef"
      }
    ]
  }
}
````

## File: vaked/examples/lowering/README.md
````markdown
# Lowering fixtures — expected output for `operator-field.vaked`

These are the **expected lowering output** for `operator-field.vaked`
([`docs/language/0012-lowering.md`](../../../docs/language/0012-lowering.md) is the
*spec*; this directory is the *spec-by-example*). They are now **reproduced
byte-for-byte by `vakedc lower`** — `python3 -m vakedc lower
vaked/examples/operator-field.vaked --out <dir>` emits exactly these files (the
`inputsHash` values are real sha256 digests, see below), and
[`tests/spec/test_vakedc_lower.py`](../../../tests/spec/test_vakedc_lower.py)
asserts the equality on every run. They began as hand-authored fixtures (reviewed
by hand against the EBNF and 0012); the executable lowering pass has since caught
up to them. Each file is what a correct Goal-3 lowering pass emits given the
validated typed semantic graph of [`../operator-field.vaked`](../operator-field.vaked).

A reviewer can spot-derive each region from a source declaration: every fixture
carries the §6.1 generated header (in the format's comment syntax) naming the
`<file>:<decl>` it came from, and the mappings match
[`0012-lowering.md`](../../../docs/language/0012-lowering.md) §4–§6.

| Fixture | Spec section | Derived from (decls in `operator-field.vaked`) |
|---------|--------------|------------------------------------------------|
| [`flake.nix`](./flake.nix) | 0012 §4 (Nix spine) | `runtime operator-field` (`systems`), `index zigCorpus` (`emit ∋ nix.derivation`), `index zigbeeFirmware` (`trust = pinned`), `engine zigimg`, `surface operatorMap` |
| [`gen/zig/mediaCompress.json`](./gen/zig/mediaCompress.json) | 0012 §5.2 (Zig daemon config) | `fiber mediaCompress` + linked `stream screenrec` + `engine zigimg` |
| [`gen/catalog/zigCorpus.jsonl`](./gen/catalog/zigCorpus.jsonl) | 0012 §5.3b (JSONL catalog) | `index zigCorpus` (`emit ∋ catalog.jsonl`) — header + chunk rows over its `github(…)` sources |
| [`gen/RUNTIME.md`](./gen/RUNTIME.md) | 0012 §5.1 (generated docs) | the whole `runtime operator-field` (all nested decls) |
| [`provenance.json`](./provenance.json) | 0012 §6.2 (provenance schema) | maps the 4 above artifacts back to their decls (5 artifact paths total) |

> Spans in `provenance.json` (`byteStart`/`byteEnd`/`line`/`col`) are derived
> from the actual byte offsets of each decl in `operator-field.vaked`, consistent
> with 0012 §6.2's Span convention (`byteStart` = the decl's leading keyword;
> `byteEnd` = exclusive, one past the closing `}`; `line`/`col` 1-based) and the
> *shape* of 0011 §6.5 spans.
>
> **Placeholder convention.** Values the *build* (not lowering) would resolve are
> written as **disclosed placeholders**, never invented concrete data:
> - `<commit>`/`<sha256>` in `flake.nix` mirror the placeholder pins in
>   `operator-field.vaked`'s `zigbeeFirmware` decl.
> - `nixpkgs` is emitted **pinned** (0012 §4.1: inputs are pinned, never a moving
>   channel ref) to a clearly-placeholder 40-hex rev,
>   `bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb` (all-`b` = "baseline" — stands in
>   for the toolchain's pinned baseline rev). No `flake.lock` fixture is
>   committed: lowering does **not** emit `flake.lock` (0012 §2.3/§4.2) — the lock
>   is produced at first `nix build` and records the full resolution.
> - `inputsHash` values in `provenance.json` are **real** content-addressed
>   digests — `"sha256-" + sha256(canonical_projection_json)` — computed by
>   `vakedc lower` and keyed **per projection** per 0012 §6.2, not the decl: e.g.
>   `packages.zigimg`'s region attributes to `decl = "fiber mediaCompress"` but
>   hashes the resolved *engine* identity + pin (the `engine-zigimg` projection),
>   while the fiber-config region for the same fiber hashes the fiber node's own
>   projection — so the two carry **different** hashes for the **same** decl.
>   (These are the one part of the fixture set that is not a disclosed placeholder
>   but a derived, reproducible value; re-lowering the unchanged graph reproduces
>   them exactly.)
> - `gen/catalog/zigCorpus.jsonl` rows are plausible placeholder chunk rows in
>   CrabCC's default (unschematized) record shape (0012 §5.3b), one referencing
>   each of two `zigCorpus` `github(…)` sources; the real rows are produced by
>   the CrabCC index derivation at build time.
>
> **Attribution note.** `operator-field.vaked` references `engine = zigimg` and
> `output = artifacts.compressedMedia`, but declares no in-file `engine zigimg`
> or `artifacts.compressedMedia` — these resolve to an imported/built-in engine
> value and a built-in artifact target (a Goal-2 *resolve* concern, 0011 §6.1,
> not a lowering one). The fixtures therefore attribute the `packages.zigimg`
> output and the Zig config's `engine` field to the **`fiber mediaCompress`**
> decl that references them (the load-bearing source decl present in the file).
> `engine_package` is the flake *attribute name* `packages.zigimg`, not a
> computed store path — Nix resolves the path at build time (0012 §2.3/§2.4).

These fixtures are now checked two ways: `vakedc lower` reproduces them
byte-for-byte ([`tests/spec/test_vakedc_lower.py`](../../../tests/spec/test_vakedc_lower.py)),
and [`tests/spec/test_vakedc_lower.py`](../../../tests/spec/test_vakedc_lower.py)'s
sibling [`test_lowering_fixtures.py`](../../../tests/spec/test_lowering_fixtures.py)
re-derives everything checkable (spans, key order, headers, registry membership)
from first principles — the original by-hand review, made permanent. Both suites
must agree.
````

## File: vaked/examples/operator-field.vaked
````
use "./engines/zig.vaked"

runtime "operator-field" {
  systems = ["x86_64-linux", "aarch64-linux"]

  index zigCorpus {
    source = [
      github("Sobeston/zig.guide"),
      github("C-BJ/awesome-zig"),
      github("raylib-zig/raylib-zig"),
      github("zigimg/zigimg")
    ]

    normalize = crabcc.markdown
    emit = [catalog.jsonl, catalog.sqlite, nix.derivation]
  }

  index zigbeeFirmware {
    source = raw.github("Koenkk/zigbee-OTA", "index.json")
    schema = schema.zigbeeOta
    trust = pinned {
      commit = "<commit>"
      sha256 = "<sha256>"
    }
  }

  stream ebpfEvents {
    source = agentGuardd.ringbuf
    type = Event.Ebpf
    retention = 24h
  }

  stream screenrec {
    source = agentpipe.screenrec
    type = Media.Frame
    fps = 10
  }

  fiber mediaCompress {
    engine = zigimg
    input = stream.screenrec
    output = artifacts.compressedMedia

    policy {
      strip_metadata = true
      max_pixels = "4K"
      formats = ["png", "webp"]
    }
  }

  surface operatorMap {
    mode = raylib
    fps = 60
    input = [stream.ebpfEvents, graph.workflow, graph.agentfield]
    views = ["network-flows", "workflow-dag", "filesystem-diff", "mesh-topology"]
  }

  parallel "operator-runtime" {
    fibers = [mediaCompress, operatorMap]
    strategy = "supervised-dag"
    supervisor = otp
  }
}
````

## File: vaked/grammar/README.md
````markdown
# Vaked Grammar — v0.3

The normative grammar for the Vaked capability-graph language lives in
[`vaked-v0-plus.ebnf`](./vaked-v0-plus.ebnf).

## Overview

Vaked v0.3 is a flake-native capability-graph language for declaring
reproducible agentic, native, mesh-aware, parallel systems.  A Vaked file
(`*.vaked`) is a sequence of top-level declarations (`decl`) and imports
(`use`).  Each declaration names a `kind`, an optional typed signature, and a
configuration `block`.

v0.3 is a **strict superset of v0.2**: every v0.2 file parses unchanged.  It
adds the *surface syntax* of the Vaked type system (Goal 2) — the form in which
users write **schemas with field constraints** and **capability taxonomies**.
The constraint set is closed and total; there is no expression/predicate
sub-language.  The checker that consumes this syntax (parse → resolve →
elaborate → check, deterministic and side-effect-free) is specified
normatively in
[`docs/language/0011-type-system.md`](../../docs/language/0011-type-system.md);
the built-in schema and capability catalog is
[`../schema/parallel-types.md`](../schema/parallel-types.md).

## Notation

The grammar uses an EBNF dialect documented in its header:

| Form | Meaning |
|------|---------|
| `"literal"` | Terminal matched verbatim |
| `{ x }` | Zero or more repetitions |
| `[ x ]` | Optional (zero or one) |
| `x \| y` | Alternation (ordered) |
| `( x )` | Grouping |
| `rule = ... ;` | One production, semicolon-terminated |

Whitespace (space, tab, newline) separates tokens and is otherwise
insignificant.  `#` begins a line comment that runs to end of line and is
discarded by the lexer.

## Key constructs

### Declarations

```
decl = { annotation } kind name [ signature ] block ;
```

`kind` is one of the 23 keywords (`runtime`, `engine`, `index`, `mesh`,
`schema`, `capability`, …).  `name` is a plain identifier or a quoted string.
The optional `signature` is a typed parameter list with an optional return
type.  In v0.3 the signature is still **parsed and stored in the AST**; the
Goal-2 checker (0011) uses it for arity/return checking of user-defined
generics, but the v0.2 evaluator path remains untyped.

### Uniform applicative syntax (`app`)

All call-like forms share one rule:

```
app = ref [ "(" [ arg { "," arg } ] ")" ] [ record ] ;
```

A bare dotted path (`crabcc.markdown`) is a ref-only `app`.  A positional call
(`raw.github("owner/repo", "file")`) adds parens.  A named-block constructor
(`zig.build { inherit src }`) appends a record.  All three can combine.

### Graph blocks (`node` / `->`)

Any `block` can contain `node` declarations and `->` edges:

```
node_decl = "node" name block ;
edge      = ref "->" ref { "->" ref } [ ":" string ] ;
```

This makes `mesh` (and any graph-shaped `kind`) expressible without
grammar-level special-casing.

## v0.3 additions — the Goal-2 type layer

v0.3 adds two surface forms. Both are reached only via new soft keywords
(`field`, `open`, `grant`, `order`) that do not begin any v0.2 statement, so
the addition is non-breaking. They are syntactically legal in any block but are
*meaningful* only inside `schema` / `capability` declarations; the checker
(0011) rejects them elsewhere.

### Schema field declarations with constraint refinements

A `schema` block declares the record type and constraints of one Vaked kind:

```
field_decl  = "field" ident ":" type [ "{" { refinement } "}" ] ;
open_decl   = "open" ;
refinement  = "required" | "optional" | "nonempty"
            | "default" "=" expr | "oneof" list
            | cmp_ref | range_ref | "matches" regex ;
cmp_ref     = ( ">=" | "<=" | ">" | "<" ) number ;
range_ref   = "in" number ".." number ;
```

The refinement set is **closed and total** — no user-defined predicates, no
expression language beyond the literal `default`/`oneof` values. `field x : T`
is shorthand for `field x : T {}`. A bare `open` statement marks the schema as
accepting unknown fields (default is closed → unknown fields rejected). Example:

```vaked
schema zigbeeOta {
  field manufacturer : String { required nonempty }
  field image_type   : Int    { required in 0 .. 255 }
  field file_version : Int     { required >= 0 }
  field url          : Path    { required matches /^https:\/\// }
  field channel      : String  { default = "stable" oneof ["stable", "beta"] }
}
```

### Capability declarations

A `capability` block declares **one** capability domain. The decl `name` is the
domain; the body lists grants and exactly one attenuation order:

```
grant_decl  = "grant" ident { ident } ;
order_decl  = "order" order_chain { ";" order_chain } ;
order_chain = ident "<" ident { "<" ident } ;
```

`a < b` means *a is the lesser (more attenuated) capability*, so a holder of `b`
may delegate `a` but not vice-versa (POLA; see 0011). Every grant named in an
`order` must be declared. Capability **values** elsewhere keep the existing
`ref` form `domain.grant` (e.g. `fs.repo_rw`) — no new value syntax. Example:

```vaked
capability fs {
  grant none repo_ro repo_rw
  order none < repo_ro < repo_rw
}
```

### Regex literal

`matches` takes a `/.../ ` regex literal (`regex = "/" { regex_char } "/"`). The
body is opaque to the parser and validated by the checker against a fixed,
bounded dialect (anchored, no backreferences; see 0011). It is **not** a Vaked
expression.

### Inherit

```
inherit_stmt = "inherit" ident { ident } ;
```

Copies named bindings from the enclosing scope into the current record or
block — mirrors Nix `inherit`.

### Annotations

```
annotation = "@" ident [ "(" [ arg { "," arg } ] ")" ] ;
```

Annotations precede the `decl` they decorate.  Their semantics are
compiler-defined per annotation name.

## Type syntax and the Goal-2 checker

`signature` and `type` syntax are fully parsed and included in the AST. The
**Goal-2 type system** that consumes them — structural conformance, the closed
constraint set, and capability attenuation/flow (POLA) checking — is now
specified normatively in
[`docs/language/0011-type-system.md`](../../docs/language/0011-type-system.md),
with the built-in schema and capability catalog in
[`../schema/parallel-types.md`](../schema/parallel-types.md). The checker is
total and side-effect-free (parse → resolve → elaborate → check); it validates
a file before any lowering (Goal 3). The legacy untyped v0.2 evaluator path
still accepts type mismatches silently; type *checking* is opt-in via `vaked
check`.

## Deferrals

The following features are intentionally absent from v0.3:

### Backpressure rules

The `backpressure { when … reduce … }` sub-language from
[`docs/language/0008-parallel-fibers-indexes-surfaces.md`](../../docs/language/0008-parallel-fibers-indexes-surfaces.md)
requires a conditional/reactive sub-language that is not yet designed.  It is
tracked as a post-v0.2 extension.  `parallel` blocks today accept only
`fibers`, `strategy`, and `supervisor`.

### Deep device / mediaPipeline schemas

`device` and `mediaPipeline` are valid grammar kinds and can be declared with
arbitrary assignment/block bodies.  Their field schemas (driver interface,
codec registry, stage graph) are not yet specified and will be added
incrementally.

## Examples

Minimal per-primitive examples live in
[`../examples/primitives/`](../examples/primitives/):

| File | Primitive |
|------|-----------|
| `index.vaked` | `index` |
| `catalog.vaked` | `catalog` |
| `stream.vaked` | `stream` |
| `fiber.vaked` | `fiber` |
| `surface.vaked` | `surface` |
| `mesh.vaked` | `mesh` (uses `node` + `->`) |
| `device.vaked` | `device` |
| `mediaPipeline.vaked` | `mediaPipeline` |
| `parallel.vaked` | `parallel` |

A complete, real-world example is
[`../examples/operator-field.vaked`](../examples/operator-field.vaked).

Type-layer (v0.3) examples — user `schema` with constraints, a `capability`
taxonomy, and an attenuated delegation, plus paired conformant/rejected blocks
— live in [`../examples/types/`](../examples/types/).

## Grammar self-containment

Every nonterminal that appears on a right-hand side is defined in the grammar
file.  Lexical terminals that cannot be written as quoted literals (`letter`,
`digit`, `char`, etc.) are defined using the EBNF `? prose description ?`
convention, consistent with the style used in
[`protocol/hcplang/grammar.ebnf`](../../protocol/hcplang/grammar.ebnf).
`comment` is defined for documentation purposes; it is consumed by the lexer
and does not appear in any parser production's right-hand side.
````

## File: vaked/schema/parallel-types.md
````markdown
# Parallel Types — Built-in Schema & Capability Catalog

**Normative.** This file is the *data* the Vaked type system operates on: one
**schema** per built-in kind, plus the built-in **capability taxonomy**. The
*rules* (structural matching, conformance, the closed constraint set, capability
attenuation, generics, the checking pipeline) are
[`docs/language/0011-type-system.md`](../../docs/language/0011-type-system.md);
the surface syntax is [`../grammar/vaked-v0-plus.ebnf`](../grammar/vaked-v0-plus.ebnf)
(v0.3). The primitives are introduced in
[`docs/language/0008-parallel-fibers-indexes-surfaces.md`](../../docs/language/0008-parallel-fibers-indexes-surfaces.md).

Every schema below is written in the v0.3 `schema` surface syntax (or its
prose-table equivalent) and is **calibrated against the worked examples** in
[`../examples/`](../examples/): every block in `examples/primitives/*.vaked`,
`examples/operator-field.vaked`, and `examples/engines/zig.vaked` conforms to the
schema for its kind. Where an example revealed a field the earlier sketch
omitted, the schema was widened to match real usage (never the reverse); those
cases are flagged **[from examples]**.

Conventions:

- A field with no presence marker is **required** (per 0011 §3.3).
- `optional` / `default` mark optional fields.
- A schema is **closed** unless it declares `open`. Closed ⇒ unknown fields are
  rejected. Two built-in kinds are `open` for forward-compatibility (`device`,
  `mediaPipeline`), as noted; the rest are closed.
- Type names (`Index<T>`, `Stream<T>`, `ArtifactTarget`, `Capability`, …) are the
  domain/auxiliary types of 0011 §2.

---

## Domain types (type-level signatures)

```text
Index<T>          Catalog<T>        Stream<T>
Fiber<I, O>       Surface           Mesh<Node, Edge>
Device            MediaPipeline     ParallelGroup
Engine            Capability        Schema<T>
Runtime
```

## Auxiliary (built-in) types referenced by the schemas

| Type | Inhabitants (built-in values / shape) |
|------|----------------------------------------|
| `Source` | `github("owner/repo")`, `raw.github("owner/repo", "file")`, `<daemon>.<channel>` ref (e.g. `agentGuardd.ringbuf`, `agentpipe.screenrec`), `device.<name>` ref |
| `ArtifactTarget` | `catalog.jsonl`, `catalog.sqlite`, `nix.derivation`, `sqlite("./path.db")` |
| `Normalizer` | `crabcc.markdown`, `crabcc.semantic { … }`, other `crabcc.*` refs |
| `TrustPolicy` | `pinned { commit : String, sha256 : String }` |
| `SurfaceMode` | `raylib` (extensible enum of built-in surface backends) |
| `Supervisor` | `otp` (extensible enum of built-in supervisors) |
| `Strategy` | `String` — currently `"supervised-dag"` and other documented strategy tags |
| `View` | `String` — a named surface view (`"network-flows"`, …) |
| `DriverRef` | a `ref`/app to a driver (`usb.cdc_acm`, `device.framebuffer`) |
| `Stage` | an app-with-record stage (`resize { … }`, `encode { … }`) |
| `Schema<T>` | a `ref` to a `schema` declaration (`schema.zigbeeOta`) |
| `Capability` | `domain.grant` ref (§ Capability taxonomy) |
| `Budget` | a `ref` to a `budget` decl, or a budget record |
| `Policy` | a structural record (per-kind, e.g. the `fiber` policy block) |

These auxiliary types are *built-in vocabulary*; they are enumerated here so the
checker can resolve the refs the examples use (0011 §2.3). Marked-extensible
enums admit further built-in values without a schema change.

---

## Schema: `runtime`

A `runtime` is the top-level system container. It carries system targets and may
**nest** other declarations (indexes, streams, fibers, surfaces, parallels) in
its block; nested decls are checked as their own kinds.

```vaked
schema runtime {
  field systems : List<String> { nonempty }   # [from examples] e.g. ["x86_64-linux","aarch64-linux"]
  # Nested declarations (index/stream/fiber/surface/parallel/…) are permitted in
  # the block and checked under their own schemas; they are not "fields".
}
```

- `systems` is the Nix-style system-double list. Conforms to
  `operator-field.vaked` (`systems = ["x86_64-linux", "aarch64-linux"]`).
- Nesting is a structural property of the block, handled by elaboration (0011
  §6.1), not a record field — so `runtime` stays closed w.r.t. *fields* while
  freely containing sub-declarations.

---

## Schema: `engine`

An `engine` builds a native artifact. Engines are typically generic via a
`signature` (0011 §5.2), e.g. `engine zigDaemon(name : String, src : Path) ->
Engine`.

```vaked
schema engine {
  field package  : Derivation                      # the built package, e.g. zig.build { … }
  field optimize : String { optional               # [from examples] inside zig.build record
                            oneof ["Debug", "ReleaseSafe", "ReleaseFast", "ReleaseSmall"] }
  # check("name", "cmd") app-statements are permitted in the block (smoke checks).
}
```

- Conforms to `engines/zig.vaked`: `package = zig.build { inherit src; optimize
  = "ReleaseSafe" }` and the `check("smoke", "…")` statement. `optimize` lives in
  the `zig.build` record (a `Derivation`-producing builder); the schema lists it
  for documentation of the accepted optimize tags.
- `Derivation` is the Nix-derivation auxiliary type (a built-in builder result).

---

## Schema: `index`

`Index<T>` — a reproducible source of structured/semi-structured content.

```vaked
schema index {
  field source    : Source | List<Source> { nonempty }
  field schema    : Schema<T>   { optional }     # item schema; binds T
  field normalize : Normalizer  { optional }
  field chunk     : Normalizer  { optional }     # [from examples] crabcc.semantic { max_tokens, overlap }
  field trust     : TrustPolicy { optional }     # pinned { commit, sha256 }
  field emit      : List<ArtifactTarget> { optional nonempty }
}
```

- Conforms to both `index` blocks in `examples/primitives/index.vaked` and
  `operator-field.vaked`:
  - `zigRefs`: `source` (list of `github(...)`), `normalize = crabcc.markdown`,
    `chunk = crabcc.semantic { max_tokens = 1200, overlap = 120 }`, `emit =
    [catalog.jsonl, catalog.sqlite, nix.derivation]`.
  - `zigbeeFirmware`: `source = raw.github(…)`, `schema = schema.zigbeeOta`,
    `trust = pinned { commit, sha256 }`.
- `source` is a union `Source | List<Source>` so both the single-source and
  multi-source forms type-check. **[from examples]** `chunk` was not in the
  original sketch; added to match `index.vaked`.
- `chunk`'s record (`max_tokens : Int`, `overlap : Int`) is the
  `crabcc.semantic` builder's argument schema, checked structurally.
- `T` (the item type) is bound by `schema` when present (0011 §5.1) and flows to
  any `catalog` built `from` this index.

---

## Schema: `catalog`

`Catalog<T>` — a queryable materialization of an index.

```vaked
schema catalog {
  field from : Index<T>             # binds T; must equal source index's T
  field key  : List<String> { optional nonempty }
  field emit : ArtifactTarget | List<ArtifactTarget>
}
```

- Conforms to `examples/primitives/catalog.vaked`: `from = index.zigbeeFirmware`,
  `key = ["manufacturer", "image_type", "file_version"]`, `emit =
  sqlite("./var/firmware.db")`.
- `emit` is `ArtifactTarget | List<ArtifactTarget>` to accept both the single
  (`sqlite(...)`) and list forms.
- Generic consistency: `from : Index<T>` ⇒ this catalog is `Catalog<T>` for the
  **same** `T` (0011 §5.1).

---

## Schema: `stream`

`Stream<T>` — a typed runtime event flow.

```vaked
schema stream {
  field source    : Source              # daemon channel ref, e.g. agentGuardd.ringbuf
  field type      : TypeRef             # event type; binds T (Event.Ebpf, Media.Frame)
  field retention : Duration { optional }   # 24h  — accepts duration literal or "24h" string
  field fps       : Int      { optional > 0 }   # [from examples] screenrec fps = 10
}
```

- Conforms to both `stream` blocks: `ebpfEvents` (`source = agentGuardd.ringbuf`,
  `type = Event.Ebpf`, `retention = 24h`) and `screenrec` (`source =
  agentpipe.screenrec`, `type = Media.Frame`, `fps = 10`). Also matches
  `operator-field.vaked`.
- `type` is a `TypeRef` (a dotted ref naming the event type); it binds the
  stream's `T`. `retention` accepts the `duration` literal `24h` (0008 sketch
  used `"24h"` — both forms are accepted per 0011 §2.1).
- **[from examples]** `fps` was not in the original Stream sketch; added because
  `screenrec` carries it.

---

## Schema: `fiber`

`Fiber<I, O>` — a policy-bound execution lane with typed input and output.

```vaked
schema fiber {
  field engine  : Engine                  # ref to an engine
  field input   : I                        # typically a Stream<I> ref
  field output  : O                        # an artifact / target ref
  field policy  : Policy  { optional }     # structural record (see below)
  field budget  : Budget  { optional }
  field observe : Bool    { optional default = false }
}
```

The `policy` record schema (nested, **[from examples]** from `fiber.vaked`):

```vaked
schema fiberPolicy {           # the shape of a fiber's `policy { … }` block
  field strip_metadata : Bool          { optional }
  field max_pixels     : String        { optional }   # e.g. "4K"
  field formats        : List<String>  { optional nonempty }
  open                                                # forward-compatible policy keys
}
```

- Conforms to `examples/primitives/fiber.vaked` and `operator-field.vaked`:
  `engine = zigimg`, `input = stream.screenrec`, `output =
  artifacts.compressedMedia`, `policy { strip_metadata = true; max_pixels =
  "4K"; formats = ["png", "webp"] }`.
- `budget` and `observe` come from the original `parallel-types` sketch; they are
  optional and absent in the examples (so the examples still conform). `policy`
  is `open` so additional policy keys do not break checking while the policy
  vocabulary stabilizes.
- Generic flow: `input` binds `I` (from the source stream's `T`), `output` binds
  `O` (0011 §5.1).

---

## Schema: `surface`

`Surface` — an operator-facing view or control shell.

```vaked
schema surface {
  field mode   : SurfaceMode                              # raylib (extensible)
  field fps    : Int { optional > 0 }
  field input  : List<Stream<_> | Graph | Catalog<_>> { nonempty }
  field views  : List<View> { nonempty }
  field budget : Budget { optional }
}
```

- Conforms to `examples/primitives/surface.vaked` and `operator-field.vaked`:
  `mode = raylib`, `fps = 60`, `input = [stream.ebpfEvents, graph.workflow,
  graph.agentfield]`, `views = ["network-flows", …]`.
- `input` elements are a union of `Stream<_>`, `Graph` (a graph ref like
  `graph.workflow`), and `Catalog<_>`. `_` is an anonymous parameter position
  (any item type accepted; surfaces do not constrain it). `Graph` is the
  auxiliary type for graph refs (`graph.workflow`, `graph.agentfield`).
- `budget` is from the sketch; optional, absent in examples.

---

## Schema: `mesh`

`Mesh<Node, Edge>` — agent/process/tool/device topology. A mesh's block is a
**graph block** (0008): `node` declarations and `->` edges, not record fields.

Node record schema (the body of each `node`):

```vaked
schema meshNode {                 # shape of a `node <name> { … }` body
  field role         : String { nonempty }
  field capabilities : List<Capability> { optional nonempty }
  open                            # nodes may carry additional descriptive keys
}
```

Edges:

- `a -> b` and `a -> b -> c` chains, with an optional `: "label"` (grammar
  `edge`). Edges marked as **delegations** carry authority and are subject to the
  attenuation check (0011 §4.4); a labelled edge (`mcpBroker -> eventd :
  "audit"`) records the label for source-mapping.

- Conforms to `examples/primitives/mesh.vaked`: nodes `codex`
  (`capabilities = [fs.repo_rw, mcp.github_read]`) and `redteam`
  (`capabilities = [fs.repo_ro, network.none]`), and the edges `codex ->
  mcpBroker`, `redteam -> eventd`, `mcpBroker -> eventd : "audit"`.
- `Node`/`Edge` type parameters are `meshNode` and the edge record respectively.
  `meshNode` is `open` so role-specific node keys are allowed.

---

## Schema: `device`

`Device` — a hardware/driver node. **Open** schema (driver vocabularies vary).

```vaked
schema device {
  field driver      : DriverRef                          # usb.cdc_acm
  field mount       : Path                               # "/dev/ttyUSB0" (string-as-path, 0011 §2.5)
  field permissions : List<String> { nonempty
                        }                                  # subset of ["read","write","mmap",…]
  field observe     : Bool { optional default = false }
  open                                                    # deep driver schema TBD (0008 / grammar README)
}
```

- Conforms to `examples/primitives/device.vaked`: `driver = usb.cdc_acm`,
  `mount = "/dev/ttyUSB0"`, `permissions = ["read", "write"]`, `observe = true`.
- `mount` is `Path`; the quoted form is accepted per 0011 §2.5. `device` is
  `open` because its full driver-interface schema is deferred (consistent with
  the grammar README's "deep device/mediaPipeline schemas" deferral).

---

## Schema: `mediaPipeline`

`MediaPipeline` — a source → stages → sink media graph. **Open** (codec/stage
vocabularies vary).

```vaked
schema mediaPipeline {
  field source : Source                     # device.framebuffer
  field stages : List<Stage> { nonempty }    # [ resize { … }, encode { … } ]
  field sink   : Stream<_> | Source          # stream.screenrec
  open                                       # deep stage/codec schema TBD
}
```

Stage record schemas (nested, **[from examples]** from `mediaPipeline.vaked`):

```vaked
schema stageResize {
  field width  : Int { > 0 }
  field height : Int { > 0 }
}
schema stageEncode {
  field codec   : String { nonempty }     # "h264"
  field bitrate : Int    { > 0 }          # 2000000
}
```

- Conforms to `examples/primitives/mediaPipeline.vaked`: `source =
  device.framebuffer`, `stages = [resize { width=1920, height=1080 }, encode {
  codec="h264", bitrate=2000000 }]`, `sink = stream.screenrec`.
- `Stage` is an app-with-record; the `resize`/`encode` builders carry the stage
  schemas above. `mediaPipeline` is `open` for the same deferral reason as
  `device`.

---

## Schema: `parallel`

`ParallelGroup` — a supervised group of fibers. (Per the grammar README, v0.2/0.3
`parallel` accepts only `fibers`, `strategy`, `supervisor`; `backpressure` is a
deferred post-v0.2 sub-language and is **not** a field here.)

```vaked
schema parallel {
  field fibers     : List<Fiber<_, _>> { nonempty }   # refs to fibers
  field strategy   : Strategy                          # "supervised-dag"
  field supervisor : Supervisor                        # otp
}
```

- Conforms to `examples/primitives/parallel.vaked` and the `parallel
  "operator-runtime"` block in `operator-field.vaked`: `fibers = [ebpfIngest,
  otaIndex, mediaCompress, operatorMap]`, `strategy = "supervised-dag"`,
  `supervisor = otp`.
- `fibers` elements are `Fiber<_, _>` refs (any in/out types). `parallel` is
  **closed**, enforcing the deferral: a stray `backpressure { … }` would be
  rejected as an unknown field until that sub-language lands.

---

## Schema: `schema` and `capability` (the meta-kinds)

- **`schema <Name> { field … ; [open] }`** — declares a schema. Its body is a
  set of `field_decl`s and an optional `open`. Well-formedness (legal refinement
  on legal field type, valid default/oneof/range/regex) is checked at load (0011
  §3.6, §6.4a). A `schema` may be generic via its `signature`.
- **`capability <domain> { grant … ; order … }`** — declares one capability
  domain (next section). Its body is `grant_decl`s and exactly one `order_decl`.

These two kinds are how users *extend* the type system within its closed bounds:
new schemas and new capability domains, never new constraint forms or new
evaluation.

---

# Built-in capability taxonomy

A capability is `domain.grant` (0011 §4). The five built-in domains below are
**predeclared**; each lists its grants and its attenuation order (`a < b` ⇒ `a`
is the weaker/more-attenuated grant; delegation may only go to `≤`). Each order
is acyclic ⇒ a partial order (0011 §4.2). Users may declare further domains with
the `capability` kind.

### Domain `fs` — filesystem authority

```vaked
capability fs {
  grant none repo_ro repo_rw host_ro host_rw
  order none < repo_ro < repo_rw < host_rw ;
        repo_ro < host_ro < host_rw
}
```

| Grant | Meaning |
|-------|---------|
| `none` | no filesystem access |
| `repo_ro` | read-only within the repository |
| `repo_rw` | read-write within the repository |
| `host_ro` | read-only on the host beyond the repo |
| `host_rw` | read-write on the host |

Order (a partial order, two chains sharing `none`/`repo_ro`/`host_rw`): `none` is
least; `host_rw` is greatest. `repo_rw` and `host_ro` are **incomparable**
(neither dominates the other) — a node with `repo_rw` may not be delegated
`host_ro` and vice-versa. **[from examples]** `fs.repo_ro` and `fs.repo_rw` are
exercised by `mesh.vaked` / `operator-field`'s mesh nodes; `host_*` extend the
lattice upward.

### Domain `network` — network authority

```vaked
capability network {
  grant none loopback lan egress
  order none < loopback < lan < egress
}
```

| Grant | Meaning |
|-------|---------|
| `none` | no network |
| `loopback` | localhost only |
| `lan` | local network |
| `egress` | outbound to the internet |

Total order (a chain) `none < loopback < lan < egress`. **[from examples]**
`network.none` is used by `mesh.vaked`'s `redteam` node.

### Domain `mcp` — MCP broker authority

```vaked
capability mcp {
  grant none github_read github_write broker_admin
  order none < github_read < github_write < broker_admin
}
```

| Grant | Meaning |
|-------|---------|
| `none` | no MCP access |
| `github_read` | read via the GitHub MCP tool |
| `github_write` | read+write via the GitHub MCP tool |
| `broker_admin` | administer the MCP broker |

Total order. **[from examples]** `mcp.github_read` is used by `mesh.vaked`'s
`codex` node.

### Domain `ebpf` — eBPF/observation authority

```vaked
capability ebpf {
  grant none observe attach_ro attach_rw
  order none < observe < attach_ro < attach_rw
}
```

| Grant | Meaning |
|-------|---------|
| `none` | no eBPF |
| `observe` | read eBPF-produced events (e.g. a ringbuf stream) |
| `attach_ro` | attach read-only (tracing) programs |
| `attach_rw` | attach programs that may act (e.g. enforce) |

Total order. Relates to `stream`s whose `source` is an eBPF ringbuf (e.g.
`agentGuardd.ringbuf` in `operator-field`): consuming such a stream *uses*
`ebpf.observe` (0011 §4.3 use-gathering).

### Domain `process` — process/exec authority

```vaked
capability process {
  grant none spawn_sandboxed spawn exec_host
  order none < spawn_sandboxed < spawn < exec_host
}
```

| Grant | Meaning |
|-------|---------|
| `none` | may not start processes |
| `spawn_sandboxed` | spawn inside a sandbox/namespace |
| `spawn` | spawn normal child processes |
| `exec_host` | execute arbitrary host processes |

Total order. An `engine` whose smoke `check(…)` runs a command *uses*
`process.spawn` (or `spawn_sandboxed`), gathered per 0011 §4.3.

---

## Attenuation examples (cross-link to checking)

- `mesh.vaked`: `codex` holds `[fs.repo_rw, mcp.github_read]`; `redteam` holds
  `[fs.repo_ro, network.none]`. The edge `codex -> mcpBroker` must satisfy
  attenuation against whatever `mcpBroker` holds; a delegation that handed
  `mcpBroker` `fs.host_rw` would be rejected (`E-CAP-ATTENUATION`) since `codex`
  holds no `fs` grant `≥ host_rw`.
- A node delegating `fs.repo_ro` to a receiver that holds `fs.repo_rw` is
  rejected: `repo_rw ≰ repo_ro`. The reverse (deliver `repo_ro` from a `repo_rw`
  holder) is permitted.

A runnable conformant-vs-rejected pair is in
[`../examples/types/`](../examples/types/).
````

## File: vakedc/__init__.py
````python
#!/usr/bin/env python3
"""vakedc — the first executable Vaked front-end (lexer + parser -> LPG + checker).

Implements 0011 pipeline stages 1-2 (parse + resolve) over grammar v0.3, producing
a Labeled Property Graph with byte-exact provenance, and stages 3-4 (elaborate +
check) in :mod:`vakedc.check` (the Goal-2 type system).  Standalone,
Python-3-stdlib-only prototype (the production parser is Zig later).

See ``vakedc/README.md``,
``docs/superpowers/specs/2026-06-10-vakedc-parser-prototype-design.md`` and
``docs/superpowers/specs/2026-06-10-vakedc-checker-design.md``.
"""

from __future__ import annotations

from .lexer import tokenize, VakedLexError, PINNED_UNICODE
from .parser import parse, parse_source, VakedSyntaxError
from .graph import Graph
from .resolve import build_graph
from .emit import to_canonical_json, to_sqlite, canonical_dump
from .check import (
    check_source, check_file, load_builtins, default_builtins_path, Diagnostic,
)

__all__ = [
    "parse_file", "parse_string", "tokenize", "build_graph",
    "to_canonical_json", "to_sqlite", "canonical_dump",
    "Graph", "VakedLexError", "VakedSyntaxError", "PINNED_UNICODE",
    "check_source", "check_file", "load_builtins", "default_builtins_path",
    "Diagnostic",
]


def parse_string(src: str, filename: str = "<vaked>") -> Graph:
    """Parse Vaked source text into a resolved :class:`Graph`."""
    items = parse_source(src, filename)
    return build_graph(items, filename)


def parse_file(path: str) -> Graph:
    """Parse a ``.vaked`` file into a resolved :class:`Graph`.

    The provenance/source file recorded in the graph is ``path`` as given.
    """
    with open(path, "r", encoding="utf-8") as fh:
        src = fh.read()
    return parse_string(src, path)
````

## File: docs/language/0008-parallel-fibers-indexes-surfaces.md
````markdown
# 0008: Parallel Fibers, Indexes, and Native Surfaces

## Status

Seed draft. The primitives introduced here are implemented in grammar v0.2 —
see [`vaked/grammar/README.md`](../../vaked/grammar/README.md).

## Summary

The language should support more than agents, hosts, and policies. Vaked should describe parallel capability graphs made of indexes, catalogs, streams, fibers, native surfaces, media pipelines, and mesh/device nodes.

This extends the system from:

```text
agent runtime declaration language
```

to:

```text
capability graph language for native parallel systems
```

## New top-level declarations

```text
index
catalog
stream
fiber
surface
mesh
device
mediaPipeline
parallel
```

## Concept: index

An `index` is a reproducible source of structured or semi-structured content.

```vaked
index zigRefs {
  source = [
    github("Sobeston/zig.guide"),
    github("C-BJ/awesome-zig"),
    github("raylib-zig/raylib-zig"),
    github("zigimg/zigimg")
  ]

  normalize = crabcc.markdown
  chunk = crabcc.semantic {
    max_tokens = 1200
    overlap = 120
  }

  emit = [catalog.jsonl, catalog.sqlite, nix.derivation]
}
```

```vaked
index zigbeeFirmware {
  source = raw.github("Koenkk/zigbee-OTA", "index.json")
  schema = schema.zigbeeOta
  trust = pinned {
    commit = "<commit>"
    sha256 = "<sha256>"
  }
}
```

## Concept: catalog

A `catalog` is a queryable materialization of an index.

```vaked
catalog firmware {
  from = index.zigbeeFirmware
  key = ["manufacturer", "image_type", "file_version"]
  emit = sqlite "./var/firmware.db"
}
```

## Concept: stream

A `stream` is a typed runtime event flow.

```vaked
stream ebpfEvents {
  source = agentGuardd.ringbuf
  type = Event.Ebpf
  retention = "24h"
}
```

## Concept: fiber

A `fiber` is a policy-bound execution lane with typed inputs and outputs.

It is not necessarily a low-level coroutine. It is a language-level lane for parallel supervised work.

```vaked
fiber mediaCompress {
  engine = zigimg
  input = stream.screenrec
  output = artifacts.compressedMedia

  policy {
    strip_metadata = true
    max_pixels = "4K"
    formats = ["png", "webp"]
  }
}
```

## Concept: surface

A `surface` is an operator-facing view or UI shell.

```vaked
surface operatorMap {
  mode = raylib
  fps = 60

  input = [
    stream.ebpfEvents,
    graph.workflow,
    graph.agentfield
  ]

  views = [
    "network-flows",
    "workflow-dag",
    "filesystem-diff",
    "mesh-topology"
  ]
}
```

## Concept: mesh

A `mesh` models agent, process, tool, or device topology.

```vaked
mesh agentfield {
  node codex {
    role = "worker"
    capabilities = [fs.repo_rw, mcp.github_read]
  }

  node redteam {
    role = "reviewer"
    capabilities = [fs.repo_ro, network.none]
  }

  route codex -> mcpBroker
  route redteam -> eventd
}
```

## Parallel block

```vaked
parallel "operator-runtime" {
  fibers = [
    ebpfIngest,
    otaIndex,
    mediaCompress,
    operatorMap
  ]

  strategy = "supervised-dag"
  supervisor = otp

  backpressure {
    when stream.ebpfEvents.lag > "10s" {
      reduce surface.operatorMap.fps to 15
    }
  }
}
```

## Compiler artifacts

These declarations should be able to emit:

```text
flake.nix
NixOS modules
systemd units
Zig daemon configs
CrabCC index derivations
SQLite/JSONL catalog artifacts
OTel stream mappings
surface launcher configs
policy manifests
generated RUNTIME.md
```

How each declaration *lowers* to these artifacts — the emitter interface, the
Nix spine, the three concretely-specified exemplar mappings (generated docs, Zig
daemon config, CrabCC index + catalog), the deferred targets, and provenance —
is specified in [`0012-lowering.md`](./0012-lowering.md) (Goal 3).

## v0 boundary

v0 should define the graph model and support at least:

- `index`
- `stream`
- `fiber`
- `surface`
- `parallel`

even if some targets are stubs.
````

## File: vakedc/__main__.py
````python
#!/usr/bin/env python3
"""vakedc CLI — ``parse``, ``check`` and ``lower`` subcommands.

  python3 -m vakedc parse <file> [--json P] [--sqlite P] [--print]
  python3 -m vakedc check <file> [--json] [--builtins PATH]
  python3 -m vakedc lower <file> [--out DIR] [--builtins PATH]

``parse`` parses a .vaked file into the LPG and emits canonical JSON + SQLite
(defaults under ``.vaked/``; ``--print`` writes canonical JSON to stdout).

``check`` runs the 0011 type-system checker (stages 3-4) over a .vaked file
against the built-in catalog and prints diagnostics: human-readable to stderr by
default, or canonical JSON to stdout with ``--json``.  ``--builtins PATH``
overrides the catalog (default: the repo's ``vaked/schema/builtins.vaked``,
resolved relative to the package, so it works from any CWD).  Exit codes:
``0`` clean, ``1`` diagnostics present, ``2`` usage / read / parse error.

``lower`` runs the full 0012 pipeline parse → resolve → check → **lower**: it
refuses to emit anything if the checker reports a single diagnostic (0012 §1),
otherwise it writes the artifact tree (``flake.nix``, ``gen/…``, and the
``provenance.json`` manifest at the out root) under ``--out DIR`` (default
``.vaked/lower/``).  Exit codes: ``0`` emitted, ``1`` diagnostics / read / parse
error (nothing written), ``2`` usage error.

Both commands exit ``1`` on an NFC/lex/parse error with the source-mapped message
on stderr; the Unicode-version-mismatch warning also goes to stderr so stdout
stays clean.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .lexer import VakedLexError
from .parser import VakedSyntaxError
from .resolve import build_graph
from .parser import parse_source
from .emit import to_canonical_json, to_sqlite
from .check import check_source, load_builtins, default_builtins_path
from . import lower as lower_mod


def _cmd_parse(args) -> int:
    try:
        with open(args.file, "r", encoding="utf-8") as fh:
            src = fh.read()
    except OSError as e:
        print(f"vakedc: cannot read {args.file}: {e}", file=sys.stderr)
        return 1

    try:
        items = parse_source(src, args.file)
    except (VakedLexError, VakedSyntaxError) as e:
        print(f"vakedc: {e}", file=sys.stderr)
        return 1

    graph = build_graph(items, args.file)
    canonical = to_canonical_json(graph)

    # Determine output targets. If neither --json/--sqlite/--print is given, use
    # the defaults under .vaked/. --print does not suppress the default writes
    # unless the user explicitly set output paths.
    explicit = args.json is not None or args.sqlite is not None
    json_path = args.json
    sqlite_path = args.sqlite
    if not explicit:
        out_dir = os.path.join(os.getcwd(), ".vaked")
        os.makedirs(out_dir, exist_ok=True)
        json_path = os.path.join(out_dir, "graph.json")
        sqlite_path = os.path.join(out_dir, "graph.db")

    if json_path is not None:
        with open(json_path, "w", encoding="utf-8") as fh:
            fh.write(canonical)
    if sqlite_path is not None:
        if os.path.exists(sqlite_path):
            os.remove(sqlite_path)
        to_sqlite(graph, sqlite_path)

    if args.print_:
        sys.stdout.write(canonical)
    elif not explicit:
        print(f"vakedc: wrote {json_path} and {sqlite_path}", file=sys.stderr)

    return 0


def _diagnostics_json(diags) -> str:
    """Canonical JSON for a diagnostics list: stable key order, sorted records
    (the checker already sorts by (file, byteStart, byteEnd, code)), 2-space
    indent, trailing newline."""
    doc = {"diagnostics": [d.as_dict() for d in diags]}
    return json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _format_diag(d) -> str:
    return (f"{d.file}:{d.line}:{d.col}: {d.severity}: {d.code}: {d.message} "
            f"[{d.decl}]")


def _cmd_check(args) -> int:
    try:
        with open(args.file, "r", encoding="utf-8") as fh:
            src = fh.read()
    except OSError as e:
        print(f"vakedc: cannot read {args.file}: {e}", file=sys.stderr)
        return 2

    builtins_path = args.builtins or default_builtins_path()
    try:
        builtins_cache = load_builtins(builtins_path)
    except OSError as e:
        print(f"vakedc: cannot read builtins {builtins_path}: {e}", file=sys.stderr)
        return 2
    except (VakedLexError, VakedSyntaxError) as e:
        print(f"vakedc: builtins catalog failed to parse: {e}", file=sys.stderr)
        return 2

    try:
        diags = check_source(src, args.file, builtins_cache=builtins_cache)
    except (VakedLexError, VakedSyntaxError) as e:
        print(f"vakedc: {e}", file=sys.stderr)
        return 2

    if args.json:
        # canonical JSON to stdout (parseable; warnings go to stderr).
        sys.stdout.write(_diagnostics_json(diags))
    else:
        for d in diags:
            print(_format_diag(d), file=sys.stderr)
        if diags:
            n = len(diags)
            print(f"vakedc: {n} diagnostic{'s' if n != 1 else ''} in {args.file}",
                  file=sys.stderr)
        else:
            print(f"vakedc: {args.file} — no diagnostics", file=sys.stderr)

    return 1 if diags else 0


def _cmd_lower(args) -> int:
    """parse → resolve → check → lower (0012 §1). Refuse to emit on any
    diagnostic; otherwise write the artifact tree under ``--out``."""
    try:
        with open(args.file, "r", encoding="utf-8") as fh:
            src = fh.read()
    except OSError as e:
        print(f"vakedc: cannot read {args.file}: {e}", file=sys.stderr)
        return 1

    # 1) parse
    try:
        items = parse_source(src, args.file)
    except (VakedLexError, VakedSyntaxError) as e:
        print(f"vakedc: {e}", file=sys.stderr)
        return 1

    # 2) check FIRST — lowering only runs on a clean, validated graph (0012 §1).
    #    Any diagnostic ⇒ print, emit NOTHING, exit 1.
    builtins_path = args.builtins or default_builtins_path()
    try:
        builtins_cache = load_builtins(builtins_path)
    except OSError as e:
        print(f"vakedc: cannot read builtins {builtins_path}: {e}", file=sys.stderr)
        return 2
    except (VakedLexError, VakedSyntaxError) as e:
        print(f"vakedc: builtins catalog failed to parse: {e}", file=sys.stderr)
        return 2

    try:
        diags = check_source(src, args.file, builtins_cache=builtins_cache)
    except (VakedLexError, VakedSyntaxError) as e:
        print(f"vakedc: {e}", file=sys.stderr)
        return 1

    if diags:
        for d in diags:
            print(_format_diag(d), file=sys.stderr)
        n = len(diags)
        print(f"vakedc: {n} diagnostic{'s' if n != 1 else ''} in {args.file}; "
              f"refusing to lower (nothing written)", file=sys.stderr)
        return 1

    # 3) resolve + lower. enrich_graph (config sub-blocks) runs inside lower()
    #    when the parsed items are supplied.
    graph = build_graph(items, args.file)
    result = lower_mod.lower(graph, items)

    # 4) write the tree. The manifest lands at <out>/provenance.json; the rest of
    #    the files are relative paths under <out> (0012 §6.2 erratum).
    out_dir = args.out or os.path.join(os.getcwd(), ".vaked", "lower")
    written = _write_tree(out_dir, result)
    print(f"vakedc: lowered {args.file} → {out_dir} ({written} files)",
          file=sys.stderr)
    return 0


def _write_tree(out_dir: str, result) -> int:
    """Write a LowerResult to ``out_dir``: every emitted file at its relative
    path, plus ``provenance.json`` at the root. Returns the file count. This is
    the only IO in the lowering pipeline (the emitters are pure)."""
    written = 0
    for rel, content in sorted(result.files.items()):
        dest = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        data = content.encode("utf-8") if isinstance(content, str) else content
        with open(dest, "wb") as fh:
            fh.write(data)
        written += 1
    # provenance manifest at the out root (0012 §6.2 erratum).
    os.makedirs(out_dir, exist_ok=True)
    prov_text = lower_mod.provenance_json_text(result.provenance)
    with open(os.path.join(out_dir, "provenance.json"), "wb") as fh:
        fh.write(prov_text.encode("utf-8"))
    written += 1
    return written


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="vakedc",
        description="Vaked front-end: parse .vaked -> Labeled Property Graph; "
                    "check .vaked against the 0011 type system.",
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    pp = sub.add_parser("parse", help="parse a .vaked file into the LPG")
    pp.add_argument("file", help="path to a .vaked source file")
    pp.add_argument("--json", metavar="PATH", default=None,
                    help="write canonical JSON to PATH")
    pp.add_argument("--sqlite", metavar="PATH", default=None,
                    help="write the SQLite graph DB to PATH")
    pp.add_argument("--print", dest="print_", action="store_true",
                    help="write canonical JSON to stdout")

    cp = sub.add_parser("check", help="type-check a .vaked file (0011 stages 3-4)")
    cp.add_argument("file", help="path to a .vaked source file")
    cp.add_argument("--json", action="store_true",
                    help="emit diagnostics as canonical JSON to stdout")
    cp.add_argument("--builtins", metavar="PATH", default=None,
                    help="path to the built-in catalog (default: the repo's "
                         "vaked/schema/builtins.vaked)")

    lp = sub.add_parser("lower",
                        help="lower a checked .vaked file to artifacts (0012)")
    lp.add_argument("file", help="path to a .vaked source file")
    lp.add_argument("--out", metavar="DIR", default=None,
                    help="output directory for the artifact tree "
                         "(default: .vaked/lower/)")
    lp.add_argument("--builtins", metavar="PATH", default=None,
                    help="path to the built-in catalog (default: the repo's "
                         "vaked/schema/builtins.vaked)")

    args = ap.parse_args(argv)

    if args.cmd == "parse":
        return _cmd_parse(args)
    if args.cmd == "check":
        return _cmd_check(args)
    if args.cmd == "lower":
        return _cmd_lower(args)
    ap.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
````

## File: vakedc/README.md
````markdown
# vakedc — the Vaked front-end (prototype)

`vakedc` is the first executable Vaked front-end: a **lexer + parser** that turns a
`.vaked` source file into a **Labeled Property Graph** (LPG) — the typed-semantic-
graph substrate that [`docs/language/0011-type-system.md`](../docs/language/0011-type-system.md)'s
checker and [`docs/language/0012-lowering.md`](../docs/language/0012-lowering.md)'s
lowering operate on — with **byte-exact provenance** attached at node instantiation.
It implements 0011 pipeline **stages 1–4** (parse + resolve + elaborate + check)
and the 0012 **lowering** pass (Goal 3): the `parse` subcommand emits the LPG; the
`check` subcommand runs the Goal-2 type system (conformance, the closed constraint
set, capability attenuation/POLA, and generics consistency); the `lower` subcommand
runs the full pipeline **parse → resolve → check → lower** and emits the artifact
tree (`flake.nix`, `gen/…`, `provenance.json`). Python 3, **stdlib only**.

## Usage

```bash
python3 -m vakedc parse <file.vaked> [--json PATH] [--sqlite PATH] [--print]
python3 -m vakedc check <file.vaked> [--json] [--builtins PATH]
python3 -m vakedc lower <file.vaked> [--out DIR] [--builtins PATH]
```

`parse`: with no output flags, writes `.vaked/graph.json` (canonical JSON) and
`.vaked/graph.db` (SQLite) relative to the CWD; `--print` writes canonical JSON to
stdout. Exit `1` on an NFC/lex/parse error with a source-mapped
`file:line:col — expected …, got …` message on stderr.

`check`: type-checks the file against the built-in catalog
([`vaked/schema/builtins.vaked`](../vaked/schema/builtins.vaked)) and prints
diagnostics — human-readable `file:line:col: error: CODE: message [decl]` to
stderr by default, or canonical JSON (`{ "diagnostics": [ … ] }`, stable key
order, trailing newline) to stdout with `--json`. `--builtins PATH` overrides the
catalog; the default is resolved relative to the package, so `check` works from
any CWD (e.g. the repo root). **Exit codes:** `0` clean, `1` diagnostics present,
`2` usage / read / parse error. Diagnostic codes are 0011's `E-CONFORM-*`,
`E-CONSTRAINT-*`, `E-CAP-*`, `E-GENERIC-*`, plus the load-time `E-SCHEMA-*` /
`E-CAP-ORDER-*`; diagnostics are sorted by `(file, byteStart, byteEnd, code)`.

`lower`: runs **parse → resolve → check → lower** (0012). It **checks first** and
refuses to emit anything if the checker reports a single diagnostic (it prints the
diagnostics and exits `1`, writing nothing — 0012 §1). On a clean graph it writes
the artifact tree under `--out DIR` (default `.vaked/lower/`): `flake.nix` (the Nix
spine, §4), `gen/RUNTIME.md` (§5.1), `gen/zig/<fiber>.json` (§5.2),
`gen/catalog/<index>.jsonl` (§5.3) for each `emit ∋ catalog.jsonl`, and the
`provenance.json` manifest at the out root (§6.2). The emitters are pure (no IO,
clock, or randomness — the only IO is this command's write layer), so re-lowering
an unchanged graph is byte-identical, including the content-addressed `inputsHash`
values. **Exit codes:** `0` emitted, `1` diagnostics / read / parse error (nothing
written), `2` usage error.

As a library: `vakedc.parse_file(path) -> Graph`,
`vakedc.check_file(path) -> list[Diagnostic]` (or `vakedc.check_source(src, name)`),
and `vakedc.lower.lower(graph, items) -> LowerResult` (`.files`, `.provenance`).

## Architecture (one line each)

- **`lexer.py`** — mode-switching tokenizer; tokens carry `{byteStart, byteEnd, line, col}`; NEWLINE suppressed inside open `(`/`[`; string `${ref}` interpolation; regex mode only after `matches`; durations/bytes/paths/numbers; `#` comments. NFC gate (rejects non-NFC source); `PINNED_UNICODE = "15.1.0"` (runtime mismatch ⇒ one stderr warning).
- **`parser.py`** — hand-written recursive descent, PEG-ordered per grammar v0.3 **exactly**; soft-keyword dispatch (`field`/`grant`/`order` before assignment, `open` after); newline-terminated statements; `VakedSyntaxError`.
- **`graph.py`** — the LPG: `Node {id, kind, name, labels[], props{}, provenance{file, decl, span}}`, `Edge {from, to, label, props{}}`; stable path-derived ids `<filename>#<outer>/<inner>`.
- **`resolve.py`** — lexically-scoped symbol table; ref worklist resolved at end-of-parse (forward refs); edge labels `contains`/`imports`/`depends_on`/`requires_capability`/`routes_to`/`member_of`; unresolvable heads → one `external` stub node per distinct dotted path.
- **`emit.py`** — `to_canonical_json` (byte-identical across runs) and `to_sqlite` + `canonical_dump` (deterministic ordered SELECT).
- **`check.py`** — 0011 stages 3–4. *Elaborate*: build a schema/capability registry from the built-in catalog LPG + the in-file user `schema`/`capability` decls (user decls override the catalog by name), and a per-domain attenuation partial order (reflexive-transitive closure of the `order` chains). *Check*: conformance (§1.1 five-clause rule incl. the Path-from-String acceptance), the closed constraint set (§3, incl. bounded-regex-dialect validation), capability validity + delegation-only-attenuates (§4.4), and generics consistency (§5). Pure: the only IO is reading the catalog. Emits sorted, source-mapped `Diagnostic`s.
- **`lower.py`** — 0012 lowering. A static registry maps each target to a **pure** emitter `(graph, nodes) -> (files, provenance_entries)` (no IO/clock/randomness). The Nix spine (`nix.spine`) and runtime docs (`docs.runtime`) always run; `zig.daemoncfg` runs per fiber; `catalog.jsonl` per index with `emit ∋ catalog.jsonl`; the CrabCC index derivation (`crabcc.index`, for `emit ∋ nix.derivation`) folds into the spine; eBPF/OTel/systemd/surface-launcher are inert deferred slots (the surface launcher is the §7 no-op stub inside the spine). `inputsHash` is a real `"sha256-"+sha256(canonical_projection_json)` keyed **per projection** (the fiber-config region hashes the fiber node's props; the engine-package region hashes the resolved engine identity + pin — same decl, different projection, §6.2). `enrich_graph` recovers the load-bearing `policy { … }` block the minimal resolver drops, in memory only (the `parse` graph JSON is unchanged).
- **`__main__.py`** — the `parse`, `check`, and `lower` CLIs (the `lower` write layer is the pipeline's only IO).

The built-in catalog is **dogfooded** as Vaked source:
[`vaked/schema/builtins.vaked`](../vaked/schema/builtins.vaked) (v0.3 `schema` /
`capability` syntax) encodes the normative prose catalog
[`vaked/schema/parallel-types.md`](../vaked/schema/parallel-types.md); vakedc parses
it with its own parser and reads the registry from the resulting LPG.

## Span convention

Per 0012 §6.2: a decl's `byteStart` is the offset of its **leading keyword**, `byteEnd`
is **exclusive** (one past the closing `}`), and `line`/`col` are 1-based at `byteStart`.
Because the LPG records provenance at decl granularity (and the AST spans decls /
nodes / refs but not assignments / literals), the checker re-tokenizes each source
file once to land a diagnostic on the exact offending field name, value literal, or
delegation edge — deterministically, with no IO beyond the already-read source.

## Verification

`tests/spec/test_vakedc.py` (parser/LPG), `tests/spec/test_vakedc_check.py`
(checker), and `tests/spec/test_vakedc_lower.py` (lowering), all registered in
`tests/spec/run_all.py`. The parser tests run a differential oracle vs the
from-EBNF recognizer (all 15 examples + the v0.2-compat probes), a byte-for-byte
LPG golden snapshot, cross-artifact provenance, and a determinism check. The
checker tests verify: the catalog parses + self-checks clean; catalog↔`parallel-
types.md` coverage (every kind/domain named in the md exists in the builtins
graph); `conformant.vaked` → 0 diagnostics; `rejected.vaked` → exactly its three
documented codes with a byte-for-byte `--json` golden snapshot
(`tests/spec/golden/rejected.diagnostics.json`); all 15 examples clean; and
diagnostics determinism. The lowering tests verify: lowering `operator-field.vaked`
reproduces `vaked/examples/lowering/` **byte-for-byte** (every file, README
excluded — the fixtures carry real `inputsHash` values); lowering `rejected.vaked`
refuses and writes nothing; two runs are byte-identical; and the emitted manifest
is registry-valid with real, re-derivable, per-projection `inputsHash`es.
`test_lowering_fixtures.py` independently re-derives the same fixtures from first
principles (spans, key order, headers), so both suites must agree.

## Design record

[`docs/superpowers/specs/2026-06-10-vakedc-parser-prototype-design.md`](../docs/superpowers/specs/2026-06-10-vakedc-parser-prototype-design.md)
(parser),
[`docs/superpowers/specs/2026-06-10-vakedc-checker-design.md`](../docs/superpowers/specs/2026-06-10-vakedc-checker-design.md)
(checker), and
[`docs/superpowers/specs/2026-06-10-vakedc-lower-design.md`](../docs/superpowers/specs/2026-06-10-vakedc-lower-design.md)
(lowering) are normative for this prototype.

## Checker — known deferrals & pinned decisions (review findings, 2026-06-10)

- **§4.3 use-check deferred.** `used(p) ⊑ granted(p)` requires the catalog to
  annotate which fields *contribute uses* (0011: "as the catalog specifies");
  `parallel-types.md` / `builtins.vaked` carry no use-contribution metadata yet,
  so only the §4.4 attenuation/delegation check runs. Implementing use-gathering
  is the next checker increment once the catalog grows `uses` annotations.
- **`mediaPipeline` stage-record conformance deferred.** `stageResize`/
  `stageEncode` exist in the catalog but stages are not yet wired into nested
  conformance (the md marks them "[from examples]" and `mediaPipeline` is
  `open`).
- **User override REPLACES the builtin (pinned decision).** An in-file
  `schema <kind>` / `capability <domain>` fully replaces the builtin of the same
  name (last-wins by name), not a merge. 0011 should eventually state this
  explicitly; until then this README is the reference.
````

## File: docs/language/README.md
````markdown
# Vaked Language Track

Vaked is a proposed typed, flake-native complement language for Nix.

It began as a way to make flake definitions, engines, and runtime declarations easier to author. It has now expanded into a capability graph language for agentic, native, mesh-aware, parallel systems.

## Current definition

Vaked is a **flake-native capability graph language** for declaring reproducible agentic, native, mesh-aware, parallel systems.

It compiles to:

- ordinary `flake.nix`
- NixOS modules
- Zig daemon configs
- eBPF policy manifests
- MCP broker configs
- OpenTelemetry config
- CrabCC indexes/catalogs
- generated documentation

## Core top-level declarations

```text
runtime
input
system
engine
host
network
filesystem
mcp
ebpf
budget
observability
runclass
workflow
index
catalog
stream
fiber
surface
mesh
device
mediaPipeline
parallel
```

## Grammar

The normative EBNF grammar and its design notes are in
[`vaked/grammar/README.md`](../../vaked/grammar/README.md) (currently **v0.3**).

## Type system (Goal 2)

The Vaked type system — structural typing + per-kind schema contracts, a
**closed** constraint set, a typed capability taxonomy with an attenuation
partial order (POLA checked at type-time), bounded generics, and a total +
deterministic checking pipeline (parse → resolve → elaborate → check, *validate
before generating*) — is specified normatively in
[`0011-type-system.md`](./0011-type-system.md). Its built-in schema and
capability catalog is [`vaked/schema/parallel-types.md`](../../vaked/schema/parallel-types.md);
worked type-layer examples are in [`vaked/examples/types/`](../../vaked/examples/types/).

## Lowering (Goal 3)

Lowering — the stage **after** the Goal-2 check — turns the validated typed
semantic graph into the boring, inspectable artifacts Vaked owns (`gen/`) plus a
**Nix spine** (`flake.nix` + NixOS modules) that wires, builds, and deploys them.
It is a **pure, total, hermetic** function of (validated graph + pinned inputs):
same graph ⇒ byte-identical artifacts, with no network/IO during lowering
(fetching/building is the Nix build's job, pinned via `flake.lock` from
`trust = pinned{…}`). One emitter per target, selected by declared `emit`
targets; provenance is preserved per-artifact (generated header) and in
`.vaked/provenance.json`. Specified normatively in
[`0012-lowering.md`](./0012-lowering.md); hand-authored expected-output fixtures
for `operator-field.vaked` are in
[`vaked/examples/lowering/`](../../vaked/examples/lowering/).

## Golden commands

```bash
vaked fmt
vaked check
vaked emit graph
vaked emit nix
vaked emit docs
vaked explain runtime operator-field
vaked explain fiber mediaCompress
vaked explain index zigbeeFirmware
```
````

## File: vaked/grammar/vaked-v0-plus.ebnf
````
# vaked grammar — Vaked capability-graph language, v0.3
#
# Notation:
#   "literal"      terminal (keyword or punctuation, matched verbatim)
#   { x }          zero or more repetitions of x
#   [ x ]          optional: zero or one occurrence of x
#   x | y          alternation (ordered: first match wins in ambiguous positions)
#   ( x )          grouping (does not affect semantics, only precedence)
#   rule = ... ;   one production rule, semicolon-terminated
#
# Whitespace separates tokens. A newline TERMINATES the current statement or
# record entry — block and record bodies ("{" "}") are newline-delimited, one
# statement/entry per line. Newlines are insignificant ONLY inside open "(" ")"
# and "[" "]" groupings, so argument lists and list literals may span lines.
# This bounds the `{ ident }` repetitions in `inherit` / `grant` and the
# `order` chains to the current line; in an `order_decl`, ";" separates chains
# and a chain list may continue across newlines after the ";". Within a
# statement, spaces and tabs are insignificant. Comments (#) run to end of
# line and are discarded by the lexer. Source files are UTF-8; keywords and
# identifiers are ASCII. (These rules are enforced by tests/spec.)
#
# ---- Design decisions (v0.2) -----------------------------------------------
#
# 1. Uniform applicative syntax (app).  All call-like forms — function calls,
#    named-block constructors, and bare references — share a single `app` rule:
#
#       ref [ "(" args ")" ] [ record ]
#
#    A bare dotted path is a ref-only app; a positional call adds parens; a
#    config block appends a record; all three can combine.  This replaces the
#    v0 split between `function_call`, `call_stmt`, and `block_stmt`.
#
# 2. Typed / parameterized declarations (parsed, not checked).  `decl` accepts
#    an optional `signature` (typed parameter list + optional return type).
#    The parser records the signature for future Goal-2 type checking; the v0.2
#    evaluator treats it as documentation only (no type errors are raised).
#
# 3. First-class graph block (`node` / `->`).  A `block` may contain `node`
#    declarations and `->` edges, making `mesh` (and any other graph-shaped
#    kind) expressible without special-casing those kinds in the grammar.
#
# 4. Backpressure deferred.  The `backpressure { when ... reduce ... }` form
#    from 0008-parallel-fibers-indexes-surfaces.md is intentionally absent.
#    It requires a conditional sub-language that is not yet designed; it is
#    tracked as a post-v0.2 extension.
#
# ---- Design decisions (v0.3 — the Goal-2 type layer) ------------------------
#
# v0.3 adds the *surface syntax* for the Vaked type system (Goal 2): the form
# in which users WRITE schemas, field constraints, and capability taxonomies.
# The accompanying checker (parse -> resolve -> elaborate -> check) is specified
# normatively in `docs/language/0011-type-system.md`; the built-in schema and
# capability catalog is `vaked/schema/parallel-types.md`.  The grammar here only
# fixes what is syntactically writable.  v0.3 is a STRICT SUPERSET of v0.2:
# every v0.2 file parses unchanged (the new statement forms are reached only by
# new leading soft keywords — `field`, `open`, `grant`, `order` — that do not
# begin any v0.2 statement; `capability` is added as a new `kind`).  There is no
# new `domain` keyword: a capability domain is named by the decl's `name`.
#
# 5. Schema field declarations with constraint refinements.  Inside a `schema`
#    block, a field is declared `field name : type { refinement }`.  The
#    refinement set is CLOSED and total (no user predicates / no expression
#    language): `required`, `optional`, `nonempty`, `default = expr`,
#    `oneof [ ... ]`, the comparisons `>= number` / `<= number` / `> number` /
#    `< number`, `in number .. number`, and `matches /regex/`.  A schema may be
#    declared `open` (one bare `open` statement in its block) to admit unknown
#    fields; the default is closed (unknown fields rejected by the checker).
#
# 6. Capability declarations.  A `capability` block declares one capability
#    DOMAIN.  Its body lists the domain's `grant` names and exactly one `order`
#    statement giving the attenuation partial order as a chain / set of chains
#    (`order none < repo_ro < repo_rw`).  Grants named in the order must be
#    declared; this is checked, not grammatical.  Capability VALUES elsewhere
#    are written with the existing `ref` form `domain.grant` (e.g. `fs.repo_rw`,
#    `network.none`) — no new value syntax is introduced.
#
# 7. regex terminal.  `matches` takes a `/.../ ` regex literal (`regex`).  The
#    regex body is opaque to the parser and validated by the checker against a
#    fixed, bounded dialect (see 0011); it is NOT a Vaked expression.
#
# 8. Soft keywords.  `field`, `open`, `grant`, `order` are SOFT keywords: they
#    introduce a v0.3 statement only in that statement's full shape (`field`
#    followed by `ident ":"`; `grant` followed by `ident`; `order` followed by
#    an `order_chain`; bare `open`).  `field_decl`/`grant_decl`/`order_decl` are
#    tried before `assignment` and self-disambiguate via their required second
#    token (e.g. `order = 3` falls through to `assignment` because `=` is not the
#    `<` an `order_chain` needs).  `open` is the one bare single-keyword form, so
#    `open_decl` is ordered AFTER `assignment`: `open = expr` parses as the v0.2
#    `assignment`, while a bare `open` (not followed by an assign-op) parses as
#    `open_decl`.  Thus no previously-legal v0.2 program changes meaning.
#
# ---- Minor conventions ------------------------------------------------------
#
# Comments     `#` begins a line comment that runs to end of line (eol).
#              Comments are stripped by the lexer; they do not appear in the
#              AST or affect parsing.
#
# Interpolation  Inside a string, `${ref}` splices the value of `ref`.
#              The interpolation site is the `interp` production; `ref` inside
#              it obeys the same dotted-ident rule as everywhere else.
#
# Inherit      `inherit foo bar` copies the bindings named `foo` and `bar`
#              from the enclosing scope into the current record / block.
#              Mirrors Nix `inherit`.
#
# Annotations  `@name` or `@name(args)` decorates the immediately following
#              `decl`.  Annotations are parsed and preserved in the AST;
#              their semantics are defined per-annotation by the compiler.
#
# Raw Nix      `nix("…")` is a conventional `app` whose ref is the plain
#              identifier `nix`; the string argument is an opaque Nix
#              expression fragment passed through to the emitter unchanged.
#              There is no special grammar production for it.
#
# ---- File structure ---------------------------------------------------------

file        = { item } ;
item        = decl | import ;
import      = "use" string ;

# ---- Declarations -----------------------------------------------------------

decl        = { annotation } kind name [ signature ] block ;
name        = ident | string ;
signature   = "(" [ param { "," param } ] ")" [ "->" type ] ;
param       = ident ":" type [ "=" expr ] ;
kind        = "runtime" | "input"   | "engine"        | "host"
            | "network" | "filesystem" | "mcp"        | "ebpf"
            | "budget"  | "observability" | "runclass" | "workflow"
            | "index"   | "catalog" | "stream"         | "fiber"
            | "surface" | "mesh"    | "device"         | "mediaPipeline"
            | "parallel" | "schema" | "capability" ;

# ---- Block and statements ---------------------------------------------------
#
# `stmt` alternatives are ORDERED (first match wins).  The v0.3 type-layer
# statements (`field_decl`, `open_decl`, `grant_decl`, `order_decl`) are listed
# first because each begins with a reserved leading keyword (`field`, `open`,
# `grant`, `order`) that does not start any v0.2 statement, so adding them
# cannot change how a v0.2 block parses.  They are syntactically legal in any
# block, but are MEANINGFUL only inside `schema` / `capability` declarations;
# the checker (0011) rejects them elsewhere.  The grammar stays uniform: no
# per-kind block grammars.

block       = "{" { stmt } "}" ;
stmt        = field_decl
            | grant_decl
            | order_decl
            | assignment
            | open_decl
            | inherit_stmt
            | edge
            | node_decl
            | decl
            | app ;
assignment  = ident assign_op expr ;
assign_op   = "=" | "?=" ;
inherit_stmt = "inherit" ident { ident } ;

# Graph constructs (used in mesh, device, mediaPipeline, etc.)
node_decl   = "node" name block ;
edge        = ref "->" ref { "->" ref } [ ":" string ] ;

# ---- Schema field declarations (v0.3) ---------------------------------------
#
# A `schema` block declares the record type and constraints of one Vaked kind
# (built-in or user-defined).  Each field gives a name, a type, and an optional
# brace-delimited list of refinements drawn from the CLOSED constraint set.  An
# empty refinement list `{}` may be omitted: `field name : type` is shorthand
# for `field name : type {}` (a required field with no further constraint, per
# the default in 0011).  `open_decl` marks the schema as accepting unknown
# fields.

field_decl  = "field" ident ":" type [ "{" { refinement } "}" ] ;
open_decl   = "open" ;

# CLOSED refinement set — total, side-effect-free, no user predicates.
refinement  = "required"
            | "optional"
            | "nonempty"
            | "default" "=" expr
            | "oneof" list
            | cmp_ref
            | range_ref
            | "matches" regex ;
cmp_ref     = ( ">=" | "<=" | ">" | "<" ) number ;
range_ref   = "in" number ".." number ;

# ---- Capability declarations (v0.3) -----------------------------------------
#
# A `capability` block declares ONE capability domain: the `name` of the decl
# is the domain (e.g. `capability fs { ... }`).  The body lists the domain's
# grants and exactly one attenuation order.  An `order` is one or more chains
# separated by ";"; within a chain, `a < b` means "a is the WEAKER (more
# attenuated) grant" (i.e. a <= b in the order).  Consequently a holder of `b`
# may delegate `a` (authority only decreases along delegation), but a holder of
# `a` may NOT delegate `b`.  See 0011 §4.  Each grant named in an order must be
# declared by a `grant` statement (checked, not grammatical).

grant_decl  = "grant" ident { ident } ;
order_decl  = "order" order_chain { ";" order_chain } ;
order_chain = ident "<" ident { "<" ident } ;

# ---- Expressions ------------------------------------------------------------

expr        = literal | list | record | app ;
app         = ref [ "(" [ arg { "," arg } ] ")" ] [ record ] ;
arg         = expr ;
ref         = ident { "." ident } ;
record      = "{" { assignment | inherit_stmt } "}" ;
list        = "[" [ expr { "," expr } ] "]" ;
literal     = string | number | bool | path | duration | bytes | "null" ;

# ---- Types (parsed, not yet checked) ----------------------------------------
#
# Type syntax is accepted and stored in the AST but is not validated by the
# v0.2 evaluator.  Type checking is Goal 2.

type        = type_atom { "|" type_atom } ;
type_atom   = qualname [ "<" type { "," type } ">" ]
            | "(" [ type { "," type } ] ")" "->" type ;
qualname    = ident { "." ident } ;

# ---- Annotations ------------------------------------------------------------

annotation  = "@" ident [ "(" [ arg { "," arg } ] ")" ] ;

# ---- Lexical terminals ------------------------------------------------------
#
# Comments are stripped by the lexer before parsing; they do not appear in
# any grammar production's RHS.  They are documented here for completeness.

comment     = "#" { any } eol ;

string      = '"' { char | interp } '"' ;
interp      = "${" ref "}" ;

# Regex literal — used only by the `matches` refinement (v0.3).  Delimited by
# "/".  The body is opaque to the parser; the checker validates it against a
# fixed bounded dialect (anchored, no backreferences) defined in 0011.
regex       = "/" { regex_char } "/" ;
regex_char  = ? any Unicode scalar value except '/' and a line terminator,
                or the two-character escape "\/" denoting a literal '/' ? ;

# Numeric and unit literals
number      = [ "-" ] digit { digit } [ "." digit { digit } ] ;
bool        = "true" | "false" ;
path        = "." ( "/" | letter ) { path_char } ;
duration    = digit { digit } ( "ns" | "us" | "ms" | "s" | "m" | "h" | "d" ) ;
bytes       = digit { digit } ( "B" | "KB" | "MB" | "GB" | "TB" ) ;

# Character-level productions
ident       = letter { letter | digit | "_" | "-" } ;
letter      = ? ASCII letter: a-z or A-Z ? ;
digit       = ? ASCII decimal digit: 0-9 ? ;
char        = ? any Unicode scalar value except '"' and '\',
                or a JSON-style escape sequence: \" \\ \/ \b \f \n \r \t \uXXXX ? ;
path_char   = letter | digit | "/" | "_" | "-" | "." ;
any         = ? any Unicode scalar value ? ;
eol         = ? U+000A (line feed) or U+000D U+000A (CRLF) ? ;
````