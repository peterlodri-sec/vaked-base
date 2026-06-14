# SDD run — AI-lish V1 runtime (Phase B + C)

Date: 2026-06-14 · Target: [`docs/ailish/2026-06-14-ailish-v1-rfc.md`](../../ailish/2026-06-14-ailish-v1-rfc.md) · Orchestrator: this session

## Frame (P0)

The RFC (Phase A) is the complete normative spec, so P1 research / P2 spec are
already satisfied — the RFC *is* the dossier. This run executes P3 (implement),
P4 (independent tests + bench), P5 (broker PR). Build/test run in the remote
Linux execution container (`cargo` present); this is not the M1 dev machine the
no-build rule protects.

## Wave-DAG

| wave | role | output | acceptance gate |
|---|---|---|---|
| W1a | coder (worktree) | `tools/ailish/` crate: `Cargo.toml`, `Cargo.lock`, `src/lib.rs` (AST + nom parser + guardrail), `src/fmt.rs` (ailishfmt + §5 compaction + token bench helper) | `cargo build --locked` clean, 0 warnings |
| W1b | test-author (worktree, spec-only) | `tests/parse.rs`, `tests/fmt.rs` authored from the RFC + API contract below — **without** seeing W1a code | tests compile against the contract once merged |
| W2 | orchestrator | merge W1a+W1b, `cargo test --locked` | all tests green, 0 warnings |
| W3 | coherence/completeness-critic | coverage report: every §2 production + §3 rule has parser support AND a test | 0 confirmed-missing, or gaps re-fanned to coder |
| W4 | broker | commit → push `claude/e2e-hcp-litany-workflow-pxsflg` → PR ready-for-review | CI gate green |

## Public API contract (the coder/test-author interface — both build to this)

```rust
// ---- AST (src/lib.rs) ----
pub enum Register { Think, Plan, Tool, Risk, Artifact, Commit, Review, Bench }
pub struct Frame { pub register: Register, pub lines: Vec<Line> }
pub enum Line { Assign(SsaAssign), Stmt(Stmt) }
pub struct SsaAssign { pub var: Variable, pub expr: Expression, pub annotation: Vec<Arg> }
pub struct Variable(pub u32);                 // %N
pub enum Expression { Action(Action), Eval(Evaluation) }
pub struct Action { pub verb: Verb, pub args: Vec<Arg> }
pub struct Evaluation { pub func: Func, pub args: Vec<Arg> } // combine/join/intersect/depend
pub enum Stmt { Relation(Relation), Gate(Gate), Schedule(Schedule) }
pub struct Relation { pub lhs: Operand, pub flow: Dataflow, pub rhs: Operand }
pub enum Dataflow { Feeds, Justifies }        // "→", "∵"
pub struct Schedule { pub target: Action }    // R:plan only: "→ target(...)"
pub struct Gate { pub name: GateName, pub state: GateState, pub because: Option<Operand> }
pub enum Operand { Var(Variable), Atom(Atom) }
pub enum Atom { Literal(Literal), Env(String), Path(String), Symbol(String) }
pub enum Literal { Number(f64), Quoted(String), Bool(bool) }
pub struct Arg { pub key: String, pub value: Value }
pub enum Value { Var(Variable), Atom(Atom) }
pub enum Verb { Fetch, Read, Edit, Write, Test, Build, Diff, Commit, Open, Merge,
                LaunchAgent, AgentWrite, CheckPermission, Block }
pub enum Func { Combine, Join, Intersect, Depend }
pub enum GateName { Artifact, English, NoCjk, Ci, Bench, Parse, Commit }
pub enum GateState { Pass, Fail, Warn, Skip }

// ---- parser + guardrail (src/lib.rs) ----
pub fn parse_message(input: &str) -> Result<Vec<Frame>, ParseError>;   // accepts long AND compact
pub fn validate(frames: &[Frame]) -> Result<(), Vec<GuardrailError>>;  // §3 register-monad rules
pub fn is_frozen(frames: &[Frame]) -> bool;  // true iff a live gate(*:fail) precedes any R:commit line

// ---- formatter (src/fmt.rs) ----
pub enum FmtMode { Long, Compact }
pub fn ailishfmt(frames: &[Frame], mode: FmtMode) -> String;  // idempotent: fmt(parse(fmt(x))) == fmt(x)
pub fn token_estimate(s: &str) -> usize;  // coarse token proxy for long-vs-compact bench
```

`ParseError` and `GuardrailError` are public, `Debug`-printable; `GuardrailError`
carries the offending register + a rule id. All public enums derive
`Debug, Clone, PartialEq`.

## Spec anchors (coder + test-author both cite these)

- §2 grammar EBNF (registers, SSA, operators `→`/`∵`, typed atoms, verb/func/gate vocab).
- §3 register-monad table (May/MUST/MUST NOT per register) + the freeze invariant.
- §4 lowering example — MUST parse exactly; round-trips through `ailishfmt`.
- §5 compaction map — `[R:think]↔[!T]` … `combine(↔&(`, `intersect(↔^(`; both forms one grammar.
- only dependency: `nom`; edition 2021; warning-free; `Cargo.lock` committed (`--locked`).

## Anti-patterns honored

Orchestrator merges only (no code authoring); test-author never sees impl;
critic is adversarial and distinct from coder; PR opened ready-for-review, never
self-merged without approval.
