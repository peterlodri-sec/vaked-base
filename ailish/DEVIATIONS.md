# AI-lish V1 — implementation conformance & deviations

This records where the `ailish` crate deviates from a strict reading of the RFC
§2 EBNF, and which §3 rules are enforced strictly vs leniently. It is the output
of a completeness audit against
[`docs/ailish/2026-06-14-ailish-v1-rfc.md`](../docs/ailish/2026-06-14-ailish-v1-rfc.md)
and should be read alongside any future RFC revision.

## Coverage summary

Fully covered: all §2 productions except the `(";" line)*` intra-frame separator
(see below); all 14 verbs, 4 funcs, 7 gate names, 4 gate states; all 8 register
monads (§3); the freeze invariant; the entire §4 example; and the §5 compaction
map with an idempotent formatter.

## Deviations from the EBNF (parser accepts a superset)

The RFC §2 EBNF and the §4 worked example **contradict each other**. The parser
sides with the example (so the canonical example parses) and is therefore broader
than the literal grammar. Each case below should be fixed in the RFC, not the
code.

1. **Positional arguments.** EBNF: `arg ::= key "=" value`. The §4 example uses
   positional operands (`combine(%1, %2)`, `depend(%3, %4)`). The parser accepts
   both `key=value` and positional operands.
2. **Calls as relation operands.** EBNF: `relation ::= operand dataflow operand`
   (operand = variable | atom). The §4 example has `depend(%3,%4) → target(...)`,
   i.e. calls on both sides. The parser widens relation/schedule terms to
   `FlowTerm = operand | call`.
3. **`∵` justification on an assignment.** EBNF `ssa_assignment` has only an
   optional `annotation`. The §4 example has `%6 = merge(pr=205) ∵ %3`. The
   parser accepts an optional trailing `∵ operand` (and is tolerant of
   annotation/justification order).
4. **`target` is undefined.** EBNF `schedule ::= "→" target` references a
   `target` production the RFC never defines. The parser treats the schedule RHS
   as a generic call/operand.

## Not implemented

- **`frame ::= "[" register "]" line (";" line)*` — the `;`-separated intra-frame
  line form.** The framer is newline-driven; `;` is consumed exclusively as an
  annotation prefix (which is unambiguous against the §4 example, where `;` only
  ever introduces annotations). A producer emitting multiple `;`-separated lines
  on one physical line is not supported. This is the one §2 production the parser
  does not handle, and stems from the RFC overloading `;`.

## Enforced strictly (§3)

- `R:think` / `R:review` MUST NOT contain side-effecting verbs.
- `R:plan` MUST NOT invoke a side-effecting verb directly (`launch_agent` is
  treated as orchestration, not a direct mutation, per the §4 example).
- `R:risk` MUST emit a `gate(*:fail)` or a mitigation (`check_permission` /
  `block`).
- `R:artifact` MUST assert an `english` / `no_cjk` posture.
- `R:bench` `test` / `build` lines MUST bind metrics in an annotation.
- `R:commit` MUST have a `gate(ci:pass)` present.
- **Freeze invariant:** any live `gate(*:fail)` freezes every `R:commit` action
  line.

## Enforced leniently (safe-direction)

- The **positive** allowed-sets ("may contain …") are not enforced; only the
  MUST / MUST NOT halves are. A non-side-effecting action (e.g. `fetch`) in
  `R:think` or `R:plan` is not flagged.
- `R:commit`'s "preceded by `gate(ci:pass)` **in dataflow**" is reduced to
  "a `gate(ci:pass)` exists in the message" — no dataflow-ordering check.
- The freeze invariant is **global** ("any live fail gate"), not dataflow-scoped
  to the commit's upstream — matching the RFC §3 invariant wording, which is
  stricter than the table's "upstream" qualifier. Errs toward freezing.
