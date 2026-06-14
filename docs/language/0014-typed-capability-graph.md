# 0014 — Typed Capability Graph: zero-proof containment

## §1 Status

Seed draft. Grammar: v0.4 (no grammar changes — the `capability` kind,
`grant_decl`, `order_decl`, and `ref` productions already cover the constructs
described here). vakedc checker: partial — `check.py` already emits
`E-CAP-UNKNOWN-DOMAIN`, `E-CAP-UNKNOWN-GRANT`, and `E-CAP-ATTENUATION` for mesh
edge attenuation. Typed ref validation in fiber policy, surface, and parallel
contexts, plus lowering outputs (`capabilities.json`, eBPF manifests,
`RUNTIME.md` capability matrix): not yet started.

## §2 Summary

Vaked's semantic output **is** a capability graph. Every fiber, mesh node,
surface, and parallel group holds a capability set — but today those sets are
expressed as untyped `ref` lists (e.g. `capabilities = [fs.repo_rw,
mcp.github_read]`) that the checker treats as opaque values and ignores.

This note specifies three things:

1. **Typed composition** — how `capability` domain declarations compose with
   site references in mesh node, fiber policy, and surface input contexts.
2. **Traversability** — the capability graph is queryable at compile time. The
   compiler can answer "what capabilities does fiber X hold?" or "does any fiber
   in parallel group P hold `fs.repo_rw`?" purely from the typed semantic graph.
3. **Zero-proof containment** — if `vakedc check` succeeds, every capability ref
   in the file resolves to a declared grant in a declared domain, and every
   delegation satisfies the attenuation partial order. No runtime capability check
   can fail due to an undeclared grant — the graph is closed at compile time.

## §3 Concepts

### Capability domain

```vaked
capability fs {
  grant repo_ro repo_rw
  order repo_ro < repo_rw
}
```

A `capability` declaration names one domain (here `fs`) and enumerates its
grants. The `order` statement defines the attenuation partial order: `repo_ro <
repo_rw` means `repo_rw` is strictly more powerful. A holder of `repo_rw` may
delegate `repo_ro` but not vice versa. Multiple chains in a single `order`
statement (`;`-separated) yield a partial order that is not necessarily total.

### Capability reference

`fs.repo_rw` is a `ref` of the form `domain.grant`. In a **checked context** —
mesh node `capabilities`, fiber `policy` `capabilities`, surface `input` refs —
these must resolve: `fs` must name a declared `capability` domain, and `repo_rw`
must be one of its declared grants. Unresolvable refs are hard checker errors:
`E-CAP-UNKNOWN-DOMAIN` if the leading identifier does not name a declared
`capability` domain; `E-CAP-UNKNOWN-GRANT` if the domain is found but the grant
identifier is not among its declared grants.

### Traversable capability graph

The compiler builds a directed capability graph over the typed semantic graph:

- **Nodes** — fibers, mesh nodes, parallel groups, surfaces.
- **Edges** — "holds" edges (entity → grant) and "delegates" edges (entity →
  entity, carrying the subset of grants transferred).

This graph is a pure function of the source. Traversal queries like "what is the
resolved capability set of fiber `mediaCompress`?" or "can any node in mesh
`agentfield` reach `fs.repo_rw`?" are compile-time computations with no external
inputs.

### Zero-proof containment (compile-time guarantee)

If `vakedc check` exits 0, the capability graph is **closed**: every ref in every
`capabilities` list resolves to a declared grant, and no delegation violates the
attenuation order. The runtime does not need to check for undeclared grants — they
provably cannot exist in checked output.

This is the capability analog of type safety: the checker acts as the proof
obligation; a clean check result is the proof. The property is called
"zero-proof" because it requires no separate proof artifact — the check result
itself is the certificate.

## §4 Grammar

No grammar changes are required. The existing productions already cover
capability declarations and references:

```ebnf
kind        = ... | "capability" ;

grant_decl  = "grant" ident { ident } ;
order_decl  = "order" order_chain { ";" order_chain } ;
order_chain = ident "<" ident { "<" ident } ;

ref         = ident { "." ident } ;
```

`capability` is already in the `kind` list (v0.3). `grant_decl` and
`order_decl` are soft-keyword statements legal inside any `block`; the checker
restricts them to `capability` bodies. `ref` (used in `capabilities = [...]`
list values) already supports the `domain.grant` form.

What is missing is checker logic to validate refs — that is the work this note
specifies and defers to a future implementation task.

## §5 Output-first

What artifacts does the capability graph lower to?

| Projection | Artifact |
|---|---|
| **`capabilities.json`** | Generated JSON listing all capability domains, their grants, and the resolved capability set of each declared entity (fibers, mesh nodes, surfaces). One entry per entity with a `capability_set: ["domain.grant", ...]` field. |
| **eBPF policy manifests** | Each fiber's resolved capability set becomes an allow-list in the generated eBPF program. The eBPF enforcement daemon verifies at runtime that the process does not exceed its declared capability set. |
| **`RUNTIME.md`** | The generated runtime documentation includes a capability matrix (entity → capability set) per parallel group, human-readable and diff-stable. |
| **Checker diagnostics** | `E-CAP-UNKNOWN-DOMAIN` — ref's domain not declared. `E-CAP-UNKNOWN-GRANT` — domain found but grant not declared. `E-CAP-ATTENUATION` — delegation violates attenuation order. All three already implemented in `check.py`. |

## §6 Determinism

Capability graph traversal at check time is a **pure function** of the typed
semantic graph. No external refs, no runtime queries, no environment reads. Same
source ⇒ same resolved capability sets ⇒ same generated artifacts. This upholds
the existing lowering determinism invariant (0012 §6).

## §7 v0 boundary

| Feature | v0 target | Notes |
|---|---|---|
| Ref resolution (`E-CAP-UNKNOWN-DOMAIN`, `E-CAP-UNKNOWN-GRANT`) | **done** | Already implemented in `check.py` for mesh contexts |
| Attenuation order (`E-CAP-ATTENUATION`) | **done** | Already implemented in `check.py` (0011 §4) |
| Extend ref validation to fiber policy + surface contexts | **v0** | `check.py` does not yet validate caps outside mesh |
| `capabilities.json` output | **post-v0** | 0012 emitter does not produce this; requires lowering pass extension |
| Capability matrix in `RUNTIME.md` | **post-v0** | 0012 emitter does not append capability sections |
| eBPF policy manifest generation | **post-v0** | Requires eBPF emitter design (see 0012 §7 deferred targets) |
| Transitive graph traversal queries (`vaked explain graph capability`) | **post-v0** | CLI query interface deferred; the graph is built but not exposed as a query surface in v0 |
