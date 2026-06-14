# AI-lish V1 — cheatsheet

One-screen reference. Full grammar: [the V1 RFC](2026-06-14-ailish-v1-rfc.md).

## Frame shape

```
[<register>] <line> ; <line> ; ...
```
A line is an SSA assignment (`%N = expr`) or a statement (relation / gate / schedule).

## Registers (long ↔ compact)

| Long | Compact | Role | Constraint |
|---|---|---|---|
| `[R:think]` | `[!T]` | reasoning | no side-effecting verbs |
| `[R:plan]` | `[!P]` | scheduling | schedule only — never execute |
| `[R:tool]` | `[!X]` | execution | bind result to `%N` |
| `[R:risk]` | `[!R]` | hazards | MUST emit `gate(*:fail)` or a mitigation |
| `[R:artifact]` | `[!A]` | outputs/facts | assert `no_cjk`/`english` posture |
| `[R:commit]` | `[!C]` | state mutation | **frozen** while any `gate(*:fail)` live |
| `[R:review]` | `[!V]` | evaluation | no state mutation |
| `[R:bench]` | `[!B]` | metrics | bind metrics in annotation |

## Operators

| Token | Meaning |
|---|---|
| `→` | dataflow: `output(lhs)` feeds `input(rhs)` |
| `∵` | justification: rhs is why lhs holds |
| `?:` | conditional select (cascade/escalation) |
| `∖` `∪` | set difference / union over result sets |

## Functions (pure) and verbs (effecting)

- **func** (no side effect): `combine` `join` `intersect` `depend` `map` `filter` `argmax`
- **verb** (effecting, bind to `%N`): `fetch` `read` `edit` `write` `test` `build` `diff` `commit` `open` `merge` `launch_agent` `check_permission` `block`
- Operator → function lowering (kills math-context hallucination): `⊕`→`combine()`, `⊗`→`intersect()`.

## Atoms (typed)

| Form | Type | Example |
|---|---|---|
| `42` `1.5` `true` `"str"` | literal | `pass=61` |
| `$IDENT` | env / secret | `$TELEGRAM_TOKEN` |
| `a/b/c.rs` | path | `src/lib.rs` |
| `` `x` `` | symbol | `` `cargo` `` |
| `%N` | SSA variable | `%3` |

## Gates

```
gate(<name>:<state>) [∵ <operand>]
```
- name ∈ `artifact englih no_cjk ci bench parse commit`
- state ∈ `pass fail warn skip`
- **Guardrail:** a live `gate(*:fail)` freezes every downstream `[!C]` until human override.

## Layer convention

```
[!P] schedule  →  [!X] execute  →  [!V]/[!R]/[!B] verify  →  [!C] commit (gate-frozen)
```

## Multi-model routing

Per-node: `model=opus`, `models=[opus,sonnet,gemini]`. One frame set spans tiers
(haiku cheap-path → opus arbiter) and vendors (claude/gemini/codex/qwen).

## Minimal example

```text
[!X] %0=test(target=`hcpbin`) ; pass=81
[!B] gate(ci:pass) ∵ %0
[!C] %1=merge(pr=206) ∵ gate(ci:pass)
```
