# RFC — AI-lish V1: a lowerable agent execution-graph protocol

- **Status:** Draft
- **Created:** 2026-06-14
- **Track:** Agent protocol / tooling
- **Supersedes:** AI-lish V0 grammar sketch (semantic-log DSL)

## Abstract

AI-lish is a compact notation an agent emits to make its reasoning, tool use, and
side effects **machine-traceable**. V0 was an expressive *log sketch* — readable,
but ambiguous: a relation operator (`→`) could mean "then", "produces", or
"because", and there were no variables, so no downstream step could reference a
prior result. V1 turns the sketch into a **lowerable execution-graph format**:
Static Single Assignment (SSA) registers, explicit dataflow edges, typed atoms,
per-register structural rules, and a token-compaction layer. The design mirrors a
compiler pipeline — High-Level (V0, prompt-space) → Low-Level (V1, SSA graph) →
Host Runtime (gh/cargo/zig) — so a V1 frame is parseable, validatable, and
replayable, not just legible.

## 1. Architecture (three layers)

```
  AI-lish V0  — semantic log / prompt-space        (humans + model author this)
      │  lower / desugar
      ▼
  AI-lish V1  — strict SSA graph                    (parser + guardrail consume this)
      │  compile / execute
      ▼
  Host runtime — gh, cargo, zig, fs                 (effects happen here)
```

V1 is the IR. It is the contract between the model (producer) and a host
interpreter (consumer): the model emits V1; a validator parses it; a guardrail
engine executes or freezes on `gate(*:fail)`.

## 2. Grammar (V1, normative EBNF)

```ebnf
message        ::= frame+
frame          ::= "[" register "]" line (";" line)*
line           ::= ssa_assignment | stmt

register       ::= "R:think" | "R:plan" | "R:tool" | "R:risk"
                 | "R:artifact" | "R:commit" | "R:review" | "R:bench"

ssa_assignment ::= variable "=" expression annotation?
expression     ::= action | evaluation
action         ::= verb "(" args? ")"
evaluation     ::= func "(" args? ")"            (* pure: combine/join/intersect/depend *)

stmt           ::= relation | gate | schedule
relation       ::= operand dataflow operand
schedule       ::= "→" target                    (* R:plan only: schedule, never execute *)
gate           ::= "gate(" gate_name ":" gate_state ")" ("∵" operand)?

operand        ::= variable | atom
dataflow       ::= "→"                            (* output(lhs) feeds input(rhs) *)
                 | "∵"                            (* rhs is the justification of lhs *)

args           ::= arg ("," arg)*
arg            ::= key "=" value
value          ::= variable | typed_atom
annotation     ::= ";" key "=" value ("," key "=" value)*

variable       ::= "%" [0-9]+
typed_atom     ::= literal | env | path | symbol
literal        ::= number | quoted | bool
env           ::= "$" ident                       (* environment / secret reference *)
path           ::= /[A-Za-z0-9_./:-]+/
symbol         ::= "`" /[^`]+/ "`"
quoted         ::= "\"" /[^"]*/ "\""
number         ::= /-?[0-9]+(\.[0-9]+)?/
bool           ::= "true" | "false"
ident          ::= /[a-zA-Z_][a-zA-Z0-9_-]*/

verb           ::= "fetch" | "read" | "edit" | "write" | "test" | "build"
                 | "diff" | "commit" | "open" | "merge" | "launch_agent"
                 | "agent_write" | "check_permission" | "block"
func           ::= "combine" | "join" | "intersect" | "depend"
gate_name      ::= "artifact" | "english" | "no_cjk" | "ci" | "bench" | "parse" | "commit"
gate_state     ::= "pass" | "fail" | "warn" | "skip"
```

### 2.1 What changed from V0 (and why)

| V0 | V1 | Reason |
|----|----|--------|
| bare relations, no IDs | `%N = expr` SSA registers | every result is addressable; downstream steps reference `%N`, eliminating "which state does `→` mean" |
| `→` overloaded (then/produces/because) | `→` = dataflow only; `∵` = justification | one operator, one meaning — no parser ambiguity |
| `⊕`/`⊗` math symbols | `combine()`/`join()`/`intersect()` funcs | LLMs hallucinate math context around `⊕`; named pure funcs don't |
| untyped atoms | `literal` / `$env` / `path` / `` `symbol` `` | a secret (`$TELEGRAM_TOKEN`) is not a path is not a literal; the guardrail can treat them differently |
| any register does anything | per-register monad rules (§3) | `R:plan` can schedule but not execute; `R:risk` must emit a gate or mitigation |

## 3. Register monads (structural rules)

Each register constrains what its lines may contain. A validator rejects a frame
that violates its register's rule.

| Register | May contain | MUST | MUST NOT |
|---|---|---|---|
| `R:think` | evaluations, relations | — | side-effecting verbs |
| `R:plan` | `schedule` (`→ target`), `depend()` | only schedule | invoke a side-effecting verb directly |
| `R:tool` | actions (any verb) | bind result to `%N` | — |
| `R:risk` | gate, `check_permission`, `block` | emit `gate(*:fail)` **or** a mitigation step | pass silently |
| `R:artifact` | gate, key=value facts | assert `no_cjk` / `english` posture | — |
| `R:commit` | `commit`/`merge`/`open` actions | be preceded by `gate(ci:pass)` in dataflow | run if any upstream `gate(*:fail)` |
| `R:review` | evaluations, gate | — | mutate state |
| `R:bench` | `test`/`build` actions, gate | bind metrics in annotation | — |

**Invariant (guardrail):** if any `gate(*:fail)` is live, the interpreter MUST
freeze before executing any `R:commit` line and require human override. This is
exactly the merge-to-main classifier block this protocol was designed around.

## 4. Lowering example (V0 → V1)

### V0 (semantic log)
```text
[R:bench] PR205 scalars → test(pass=61) ⊕ rust-build(22s) ⇒ gate(ci:pass)
[R:plan]  PR205 → user merge; agent ⇒ write(lib.rs ⊕ tests/aggregates.rs)
```

### V1 (SSA graph)
```text
[R:bench]  %0 = fetch(pr=205, scope="scalars")
           %1 = test(target=%0) ; pass=61
           %2 = build(target=%0, kind="rust") ; duration_s=22
           %3 = combine(%1, %2)
           gate(ci:pass) ∵ %3
[R:risk]   %4 = check_permission(verb="merge", tool=`gh`) ; state="classifier_blocked"
           gate(commit:fail) ∵ %4
[R:plan]   depend(%3, %4) → target(user_action="paste_merge_cmd")
           %5 = launch_agent(scope="aggregates", base=%0)
[R:commit] %6 = merge(pr=205) ∵ %3        # frozen while gate(commit:fail) live
```

Every `%N` is independently validatable; a downstream failure can fall back on the
exact register that produced the bad input.

## 5. Token compaction (the "bytecode")

Once the schema is stable, registers and operators map to single-token forms. The
long form stays canonical for humans; the compact form is what a model emits under
token pressure. A formatter (`ailishfmt`) is idempotent between them.

| Long | Compact | | Long | Compact |
|---|---|---|---|---|
| `[R:think]` | `[!T]` | | `[R:bench]` | `[!B]` |
| `[R:plan]` | `[!P]` | | `[R:risk]` | `[!R]` |
| `[R:tool]` | `[!X]` | | `[R:commit]` | `[!C]` |
| `[R:artifact]` | `[!A]` | | `[R:review]` | `[!V]` |
| `combine(` | `&(` | | `intersect(` | `^(` |

Compact form is lexically distinct (`[!X]` can never collide with a path), so the
parser accepts both with one grammar.

## 6. Roadmap (drives this RFC to production)

- **Phase A — codify (this doc):** grammar §2, register monads §3, atom typing,
  operator→function lowering §2.1.
- **Phase B — runtime:** a `nom`-based Rust parser/validator that reads V1 frames
  into a typed `Frame`/`Stmt` AST, plus a guardrail engine enforcing §3 (freeze on
  live `gate(*:fail)` before `R:commit`).
- **Phase C — optimize:** the §5 compaction map + `ailishfmt` idempotent formatter;
  measure tokens-per-frame long vs compact.

The companion workflow `.claude/workflows/ailish-v1-drive.js` orchestrates A→B→C.

## 7. Non-goals

Not a general programming language (no loops, no arithmetic — `combine`/`join` are
set ops, not math). Not a replacement for the host shell; it *describes* host
effects and gates them. Not a transport (it is text emitted inline in a model turn).
