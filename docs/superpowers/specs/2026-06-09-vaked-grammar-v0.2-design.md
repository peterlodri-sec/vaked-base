# Vaked grammar v0.2 — design

- **Date:** 2026-06-09
- **Status:** Approved (brainstorm) → implementing via subagent-driven execution
- **Goal 1** of the language session: harden `vaked/grammar/vaked-v0-plus.ebnf` so every primitive parses, with an example each. (Goal 2 = type-checking semantics; Goal 3 = lowering.)

## Decisions (the four forks + minor defaults)

1. **Scope — parse types, defer checking.** v0.2 parses type *syntax* (annotations, return types, generics `<…>`, unions `A|B`, parameterized decls) so the surface is stable and every current example parses; type *checking/inference* is Goal 2.
2. **Expression model — uniform & explicit.** One applicative form `app = ref [ "(" args ")" ] [ record ]`. Calls always parenthesized; every `{ … }` is a record of `field = value`. Replaces the old `function_call`/`block_stmt`/`record` tangle. Normalize `sqlite "path"` → `sqlite("path")`.
3. **Backpressure — deferred.** `parallel` = `fibers`/`strategy`/`supervisor` only. No `when/reduce/to` rule sub-grammar in v0.2 (the 0008 backpressure example stays non-parseable until a later pass).
4. **Graph — first-class reusable block.** `node <name> { record }` + directed edges `a -> b` (chains `a -> b -> c`, optional label `a -> b : "role"`), usable in `mesh` / `workflow` / `parallel`.

**Minor defaults (approved):** `#` line comments · `"${ref}"` string interpolation · keep `inherit` · `@annotation` for docs/metadata · raw-Nix escape hatch = `nix("…literal nix…")`.

## The v0.2 grammar (normative target)

```ebnf
file        = { item } ;
item        = decl | import ;
import      = "use" string ;

decl        = { annotation } kind name [ signature ] block ;
name        = ident | string ;
signature   = "(" [ param { "," param } ] ")" [ "->" type ] ;
param       = ident ":" type [ "=" expr ] ;
kind        = "runtime"|"input"|"engine"|"host"|"network"|"filesystem"|"mcp"|"ebpf"
            | "budget"|"observability"|"runclass"|"workflow"|"index"|"catalog"|"stream"
            | "fiber"|"surface"|"mesh"|"device"|"mediaPipeline"|"parallel"|"schema" ;

block       = "{" { stmt } "}" ;
stmt        = assignment | inherit_stmt | edge | node_decl | decl | app ;
assignment  = ident assign_op expr ;
assign_op   = "=" | "?=" ;
inherit_stmt= "inherit" ident { ident } ;

node_decl   = "node" name block ;
edge        = ref "->" ref { "->" ref } [ ":" string ] ;

expr        = literal | list | record | app ;
app         = ref [ "(" [ arg { "," arg } ] ")" ] [ record ] ;
arg         = expr ;
ref         = ident { "." ident } ;
record      = "{" { assignment | inherit_stmt } "}" ;
list        = "[" [ expr { "," expr } ] "]" ;
literal     = string | number | bool | path | duration | bytes | "null" ;

type        = type_atom { "|" type_atom } ;
type_atom   = qualname [ "<" type { "," type } ">" ]
            | "(" [ type { "," type } ] ")" "->" type ;
qualname    = ident { "." ident } ;

annotation  = "@" ident [ "(" [ arg { "," arg } ] ")" ] ;
string      = '"' { char | interp } '"' ;
interp      = "${" ref "}" ;
comment     = "#" { any } eol ;
ident       = letter { letter | digit | "_" | "-" } ;
```

## Implementation tasks (for subagent-driven execution)

- **T1 — Grammar.** Write `vaked/grammar/vaked-v0-plus.ebnf` as the v0.2 grammar above, with a header documenting the notation (mirror `protocol/hcplang/grammar.ebnf` style), the 4 decisions, and the deferrals. Self-contained: every RHS nonterminal defined, no dead rules.
- **T2 — Examples.** One minimal valid-v0.2 example per primitive under `vaked/examples/primitives/` — `index`, `catalog`, `stream`, `fiber`, `surface`, `mesh` (with `node` + `->`), `device`, `mediaPipeline`, `parallel`. Each MUST derive from the T1 grammar. Also normalize `vaked/examples/operator-field.vaked` + `engines/zig.vaked` to v0.2 (`sqlite("./x")`, confirm `pinned { … }` / `zig.build { … }` parse).
- **T3 — Docs.** `vaked/grammar/README.md`: explain v0.2, the type-syntax-parsed-not-checked note, and the deferrals; cross-link from `docs/language/0008-…` and `docs/language/README.md`.

## Review criteria (per task)

Spec compliance (covers the grammar/decisions above, nothing extra) + quality (grammar self-consistency: all nonterminals defined, no dead rules; **every example derives from the grammar** — verify by hand-derivation or a from-EBNF parser, as in the RFC 0002 review).

## Deferred

Backpressure `when/reduce/to` rules; type checking/inference (Goal 2); deep `device`/`mediaPipeline` field schemas; the lowering-to-artifacts story (Goal 3).
