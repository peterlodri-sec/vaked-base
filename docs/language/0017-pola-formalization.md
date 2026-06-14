# 0017 — POLA Formalization (deferred mechanization)

## §1 Status

**DEFERRED / post-v1.0 scaffold.** This note is an **outline, not a proof**. It
scaffolds the work of mechanizing the abstract POLA soundness theorem that
[`0011-type-system.md`](./0011-type-system.md) §4.5 argues for **informally**;
§4.5 is the informal counterpart this RFC will eventually discharge.

**Prerequisite.** The use-check (`used(p)`, diagnostic `E-CAP-USE`) must be
**implemented in `vakedc` first**. Today `check.py` enforces only ref-validity
(`E-CAP-UNKNOWN-DOMAIN` / `E-CAP-UNKNOWN-GRANT` / `E-CAP-ORDER-*`) and mesh-edge
attenuation (`E-CAP-ATTENUATION`); there is no `used(p)` computation. Mechanizing
the theorem before the use-check lands would **certify a premise the tool does
not enforce** — i.e. prove a property of a checker that does not yet exist. The
use-check must land first (see §10).

## §2 Goal & scope

Mechanize the **abstract** POLA soundness theorem (the property §1/§4.5 argue
informally) in **Lean 4 (Mathlib)** or **Coq**.

**In scope (the abstract model):**

- the order theory underpinning attenuation (§4);
- path attenuation along delegation edges (§6);
- the cyclic case (§7);
- composition of the local checks into the global invariant (§5, §8).

**Out of scope (v1):** proving that `vakedc/check.py` **faithfully implements**
the abstract model. That is a separate verification effort (extraction,
property-based testing, or a verified rewrite — §9). It is named here as the
**residual risk**: this RFC proves the *model* sound, not the *implementation*
faithful to the model.

## §3 Datatypes

The abstract model (sketch; final names follow Mathlib conventions):

```text
Domain      : a finite set of capability domains (net, fs, ebpf, mcp, …)
Grant       : a per-domain grant value
Capability  : Domain × Grant
<           : per-domain strict order on Grant (the `order` chain; 0011 §4.2)
Principal   : a node holding capabilities
  granted   : Principal → Finset Capability
delegation  : a relation Principal → Principal (mesh `->` edges; 0011 §4.4)
used        : Principal → Finset Capability   (the exercised capabilities; §5)
```

## §4 Attenuation order

- `≤` := **`ReflTransGen` of `<`** (the reflexive-transitive closure of the
  per-domain strict order).
- **Lemma 4.1** — `≤` is a `PartialOrder`, *given `<` is acyclic*. Reflexivity
  and transitivity are immediate from `ReflTransGen`; **antisymmetry is the
  content** of the lemma (it is exactly where acyclicity of the `order` chain is
  used — cf. `E-CAP-ORDER-CYCLE` in `check.py`).
- Define `⊑` on grant-*sets*: `G ⊑ H` iff every capability in `G` is dominated
  (`≤`, same domain) by some capability in `H` (0011 §4.3, lifted to sets).
- **Lemma 4.2** — `⊑` is a `Preorder` (reflexive + transitive; transitivity
  follows from transitivity of `≤` within each domain).

## §5 Local checks as predicates

The two local checks, as predicates over the model:

- **use-check** — `used p ⊑ granted p` for every principal `p` (0011 §4.3;
  **prerequisite, §1**).
- **edge-attenuation** — `granted r ⊑ granted s` for every delegation edge
  `s -> r` (0011 §4.4; this is the one `check.py` enforces today via
  `E-CAP-ATTENUATION`).

## §6 Path attenuation

- **Lemma 6.1** — induction over `ReflTransGen` of the delegation relation: if
  edge-attenuation holds for every edge, then for every path `s ->* r`,
  `granted r ⊑ granted s`. The induction step composes one edge's `⊑` with the
  inductive hypothesis using Lemma 4.2 (transitivity of `⊑`).

## §7 Cyclic case

- **Lemma 7.1** — **the hardest case; flag as a budget risk.** On a strongly
  connected component (SCC) of the delegation graph, edge-attenuation around the
  cycle gives mutual `⊑` between every pair on the cycle; conclude **pointwise
  grant equivalence** (all principals on the SCC hold `⊑`-equivalent grant-sets).
  This is where antisymmetry-style reasoning on the *set* preorder is delicate
  (`⊑` is only a preorder, so "mutual `⊑` ⟹ equal" needs the per-domain
  partial-order structure of §4 lifted carefully). Budget risk: the SCC argument
  may require quotienting by `⊑`-equivalence to get a partial order to do the
  antisymmetry step.

## §8 Main theorem

- **Theorem 8.1 — `pola_sound`.** Given use-check (§5) **and** edge-attenuation
  (§5) hold for all principals/edges, the authority any principal can *exercise*
  is bounded by the **root grant**: for every `p` and every `c ∈ used p`, there
  is a root delegator `s` with `s ->* p` such that `c` is dominated by some grant
  in `granted s`. Composes Lemma 6.1 (path attenuation), Lemma 7.1 (cycles), and
  the use-check premise.

## §9 What stays informal

Even after Theorem 8.1, these are **not** discharged by this RFC:

- **Model → `check.py` correspondence.** Three candidate strategies, none in
  scope for v1: (a) **extraction** of a verified checker from the Lean/Coq
  development; (b) **property-based testing** of `check.py` against the model;
  (c) a **verified rewrite** of the checker. This is the residual risk named in
  §2.
- **Runtime enforcement.** Out of scope per 0011 §4.5 (the type system is the
  authority of record); the runtime projection is specified separately in
  [`0016-runtime-enforcement.md`](./0016-runtime-enforcement.md), and it enforces
  only a *subset* of the proved property.

## §10 Effort & milestones

| Milestone | Estimate | Dependency |
|-----------|----------|------------|
| Use-check (`used(p)`, `E-CAP-USE`) implemented in `vakedc` | — | **must land first** (§1) |
| Abstract proof (§§3–8) in Lean 4 / Coq | ≈ 4–6 person-days | use-check landed |
| Model → `check.py` link (§9) | ≈ 2–4 weeks | deferred; strategy TBD |

Lemma 7.1 (cyclic case) is the line item most likely to overrun the abstract-proof
budget.

## §11 Cross-references

- 0011 — type system: capability attenuation order (§4) and the informal
  soundness argument this RFC discharges (§4.5) —
  [`0011-type-system.md`](./0011-type-system.md)
- 0014 — typed capability graph: the graph the model abstracts —
  [`0014-typed-capability-graph.md`](./0014-typed-capability-graph.md)
- 0016 — runtime enforcement: the subset of this property projected to kernel
  predicates — [`0016-runtime-enforcement.md`](./0016-runtime-enforcement.md)
- The checker design spec / implementation — [`vakedc/README.md`](../../vakedc/README.md)
