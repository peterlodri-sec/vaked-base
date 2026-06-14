//! AI-lish V1 runtime.
//!
//! AI-lish V1 is a lowerable agent execution-graph protocol: a compact notation
//! a model emits to make its reasoning, tool use, and side effects
//! machine-traceable. This crate provides:
//!
//! * a typed AST mirroring the §2 grammar of the RFC,
//! * a [`nom`]-based parser ([`parse_message`]) that accepts both the long
//!   (`[R:think]`, `combine(`) and compact (`[!T]`, `&(`) forms under one
//!   grammar (§5 token compaction),
//! * a register-monad guardrail ([`validate`]) enforcing the §3 structural
//!   rules, and
//! * the freeze invariant ([`is_frozen`]) — a live `gate(*:fail)` before any
//!   `R:commit` line freezes execution.
//!
//! The companion formatter lives in [`fmt`] and is re-exported here.

mod fmt;
mod parser;

pub use fmt::{ailishfmt, token_estimate, FmtMode};

// ---------------------------------------------------------------------------
// AST — mirrors §2 of the RFC and the SDD public-API contract verbatim.
// ---------------------------------------------------------------------------

/// SSA execution register. Each frame opens with exactly one register, which
/// constrains what its lines may contain (§3 register monads).
#[derive(Debug, Clone, PartialEq)]
pub enum Register {
    Think,
    Plan,
    Tool,
    Risk,
    Artifact,
    Commit,
    Review,
    Bench,
}

/// A single frame: one register followed by one or more lines.
#[derive(Debug, Clone, PartialEq)]
pub struct Frame {
    pub register: Register,
    pub lines: Vec<Line>,
}

/// A line inside a frame: either an SSA assignment or a bare statement.
#[derive(Debug, Clone, PartialEq)]
pub enum Line {
    Assign(SsaAssign),
    Stmt(Stmt),
}

/// `%N = expr ; key=value, ...` — binds an expression's result to an SSA
/// register and carries optional annotation facts.
#[derive(Debug, Clone, PartialEq)]
pub struct SsaAssign {
    pub var: Variable,
    pub expr: Expression,
    pub annotation: Vec<Arg>,
}

/// An SSA register reference `%N`.
#[derive(Debug, Clone, PartialEq)]
pub struct Variable(pub u32);

/// The right-hand side of an assignment: an effecting action or a pure eval.
#[derive(Debug, Clone, PartialEq)]
pub enum Expression {
    Action(Action),
    Eval(Evaluation),
}

/// A (possibly side-effecting) verb invocation, e.g. `fetch(pr=205)`.
#[derive(Debug, Clone, PartialEq)]
pub struct Action {
    pub verb: Verb,
    pub args: Vec<Arg>,
}

/// A pure set-operation invocation: `combine`/`join`/`intersect`/`depend`.
#[derive(Debug, Clone, PartialEq)]
pub struct Evaluation {
    pub func: Func,
    pub args: Vec<Arg>,
}

/// A non-assigning statement.
#[derive(Debug, Clone, PartialEq)]
pub enum Stmt {
    Relation(Relation),
    Gate(Gate),
    Schedule(Schedule),
}

/// `operand → operand` or `operand ∵ operand` — an explicit dataflow edge.
#[derive(Debug, Clone, PartialEq)]
pub struct Relation {
    pub lhs: Operand,
    pub flow: Dataflow,
    pub rhs: Operand,
}

/// Dataflow edge kind.
#[derive(Debug, Clone, PartialEq)]
pub enum Dataflow {
    /// `→` — output(lhs) feeds input(rhs).
    Feeds,
    /// `∵` — rhs is the justification of lhs.
    Justifies,
}

/// `→ target(...)` — an `R:plan`-only schedule directive (never executes).
#[derive(Debug, Clone, PartialEq)]
pub struct Schedule {
    pub target: Action,
}

/// `gate(name:state) ∵ operand` — a guardrail checkpoint.
#[derive(Debug, Clone, PartialEq)]
pub struct Gate {
    pub name: GateName,
    pub state: GateState,
    pub because: Option<Operand>,
}

/// An operand of a relation: a variable or a typed atom.
#[derive(Debug, Clone, PartialEq)]
pub enum Operand {
    Var(Variable),
    Atom(Atom),
}

/// A typed atom — the guardrail treats each variant differently.
#[derive(Debug, Clone, PartialEq)]
pub enum Atom {
    Literal(Literal),
    /// `$IDENT` — environment / secret reference.
    Env(String),
    /// A bare path token.
    Path(String),
    /// `` `symbol` `` — a backtick-quoted symbol.
    Symbol(String),
}

/// A literal atom.
#[derive(Debug, Clone, PartialEq)]
pub enum Literal {
    Number(f64),
    Quoted(String),
    Bool(bool),
}

/// `key=value` — an argument or annotation fact.
#[derive(Debug, Clone, PartialEq)]
pub struct Arg {
    pub key: String,
    pub value: Value,
}

/// An argument's value: a variable or a typed atom.
#[derive(Debug, Clone, PartialEq)]
pub enum Value {
    Var(Variable),
    Atom(Atom),
}

/// A (possibly side-effecting) verb (§2 `verb`).
#[derive(Debug, Clone, PartialEq)]
pub enum Verb {
    Fetch,
    Read,
    Edit,
    Write,
    Test,
    Build,
    Diff,
    Commit,
    Open,
    Merge,
    LaunchAgent,
    AgentWrite,
    CheckPermission,
    Block,
}

/// A pure function (§2 `func`).
#[derive(Debug, Clone, PartialEq)]
pub enum Func {
    Combine,
    Join,
    Intersect,
    Depend,
}

/// A gate name (§2 `gate_name`).
#[derive(Debug, Clone, PartialEq)]
pub enum GateName {
    Artifact,
    English,
    NoCjk,
    Ci,
    Bench,
    Parse,
    Commit,
}

/// A gate state (§2 `gate_state`).
#[derive(Debug, Clone, PartialEq)]
pub enum GateState {
    Pass,
    Fail,
    Warn,
    Skip,
}

// ---------------------------------------------------------------------------
// Errors
// ---------------------------------------------------------------------------

/// A parse failure. `Debug`-printable; carries a human-readable reason and the
/// remaining unconsumed input where available.
#[derive(Debug, Clone, PartialEq)]
pub struct ParseError {
    pub message: String,
}

impl std::fmt::Display for ParseError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "ailish parse error: {}", self.message)
    }
}

impl std::error::Error for ParseError {}

/// A guardrail (§3 register-monad) violation. Carries the offending register
/// and a stable rule id string.
#[derive(Debug, Clone, PartialEq)]
pub struct GuardrailError {
    pub register: Register,
    pub rule: String,
    pub detail: String,
}

impl std::fmt::Display for GuardrailError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(
            f,
            "ailish guardrail [{}] on {:?}: {}",
            self.rule, self.register, self.detail
        )
    }
}

impl std::error::Error for GuardrailError {}

// ---------------------------------------------------------------------------
// Public entry points
// ---------------------------------------------------------------------------

/// Parse a complete AI-lish V1 message into a sequence of [`Frame`]s.
///
/// Accepts both the long form (`[R:think]`, `combine(`) and the compact form
/// (`[!T]`, `&(`) under one grammar, plus the unicode operators `→` (feeds)
/// and `∵` (justifies).
pub fn parse_message(input: &str) -> Result<Vec<Frame>, ParseError> {
    parser::parse_message(input)
}

/// Validate frames against the §3 register-monad rules. Returns every
/// violation found (not just the first).
pub fn validate(frames: &[Frame]) -> Result<(), Vec<GuardrailError>> {
    let mut errors = Vec::new();
    for frame in frames {
        validate_frame(frame, &mut errors);
    }
    validate_commit_dataflow(frames, &mut errors);
    if errors.is_empty() {
        Ok(())
    } else {
        Err(errors)
    }
}

/// §3 R:commit dataflow rules, evaluated in document order across frames.
/// A commit MUST be preceded by a `gate(ci:pass)` (rule `R:commit/requires-ci-pass`) —
/// the merge-to-main classifier block the protocol is built around (§1, §3) — and
/// MUST NOT run while an upstream `gate(*:fail)` is live (rule
/// `R:commit/frozen-fail-gate`), mirroring [`is_frozen`]'s scan. At most one of
/// each violation is recorded per commit frame.
fn validate_commit_dataflow(frames: &[Frame], errors: &mut Vec<GuardrailError>) {
    let mut fail_live = false;
    let mut ci_pass_seen = false;
    for frame in frames {
        let is_commit = frame.register == Register::Commit;
        let mut frozen_flagged = false;
        let mut ci_flagged = false;
        for line in &frame.lines {
            if is_commit && is_executable_commit_line(line) {
                if fail_live && !frozen_flagged {
                    errors.push(err(
                        &Register::Commit,
                        "R:commit/frozen-fail-gate",
                        "R:commit MUST NOT run while an upstream gate(*:fail) is live",
                    ));
                    frozen_flagged = true;
                }
                if !ci_pass_seen && !ci_flagged {
                    errors.push(err(
                        &Register::Commit,
                        "R:commit/requires-ci-pass",
                        "R:commit MUST be preceded by gate(ci:pass) in dataflow",
                    ));
                    ci_flagged = true;
                }
            }
            if let Line::Stmt(Stmt::Gate(gate)) = line {
                if gate.state == GateState::Fail {
                    fail_live = true;
                }
                if gate.name == GateName::Ci && gate.state == GateState::Pass {
                    ci_pass_seen = true;
                }
            }
        }
    }
}

/// True iff a live `gate(*:fail)` precedes any `R:commit` line in document
/// order — the freeze invariant (§3). A `gate(commit:pass)` or `gate(ci:pass)`
/// does not clear a previously-emitted failing gate; a failing gate stays live
/// for the rest of the message.
pub fn is_frozen(frames: &[Frame]) -> bool {
    let mut fail_live = false;
    for frame in frames {
        let is_commit = frame.register == Register::Commit;
        for line in &frame.lines {
            // A commit line encountered while a fail gate is live => frozen.
            if is_commit && fail_live && is_executable_commit_line(line) {
                return true;
            }
            if let Line::Stmt(Stmt::Gate(gate)) = line {
                if gate.state == GateState::Fail {
                    fail_live = true;
                }
            }
        }
    }
    false
}

/// A commit-register line is "executable" if it is an action assignment or a
/// bare commit/merge/open action — i.e. it would cause a side effect. Gates and
/// pure relations inside an `R:commit` frame do not themselves trigger freeze.
fn is_executable_commit_line(line: &Line) -> bool {
    match line {
        Line::Assign(a) => matches!(a.expr, Expression::Action(_)),
        Line::Stmt(Stmt::Relation(_)) => false,
        Line::Stmt(Stmt::Gate(_)) => false,
        Line::Stmt(Stmt::Schedule(_)) => true,
    }
}

// ---------------------------------------------------------------------------
// Guardrail — §3 register-monad table.
// ---------------------------------------------------------------------------

fn err(register: &Register, rule: &str, detail: impl Into<String>) -> GuardrailError {
    GuardrailError {
        register: register.clone(),
        rule: rule.to_string(),
        detail: detail.into(),
    }
}

/// Side-effecting verbs (everything except the read-only `CheckPermission`).
/// `CheckPermission` and `Block` are control verbs permitted in `R:risk`.
fn is_side_effecting(verb: &Verb) -> bool {
    matches!(
        verb,
        Verb::Fetch
            | Verb::Read
            | Verb::Edit
            | Verb::Write
            | Verb::Test
            | Verb::Build
            | Verb::Diff
            | Verb::Commit
            | Verb::Open
            | Verb::Merge
            | Verb::LaunchAgent
            | Verb::AgentWrite
    )
}

fn validate_frame(frame: &Frame, errors: &mut Vec<GuardrailError>) {
    let reg = &frame.register;
    match reg {
        Register::Think => validate_think(frame, errors),
        Register::Plan => validate_plan(frame, errors),
        Register::Tool => validate_tool(frame, errors),
        Register::Risk => validate_risk(frame, errors),
        Register::Artifact => validate_artifact(frame, errors),
        Register::Commit => validate_commit(frame, errors),
        Register::Review => validate_review(frame, errors),
        Register::Bench => validate_bench(frame, errors),
    }
}

// R:think — May: evaluations, relations. MUST NOT: side-effecting verbs.
fn validate_think(frame: &Frame, errors: &mut Vec<GuardrailError>) {
    for line in &frame.lines {
        if let Some(verb) = effecting_verb_of(line) {
            if is_side_effecting(verb) {
                errors.push(err(
                    &frame.register,
                    "R:think/no-side-effect",
                    format!("R:think may not invoke side-effecting verb {verb:?}"),
                ));
            }
        }
    }
}

// R:plan — May: schedule (→ target), depend(). MUST: only schedule.
// MUST NOT: invoke a side-effecting verb directly.
fn validate_plan(frame: &Frame, errors: &mut Vec<GuardrailError>) {
    for line in &frame.lines {
        match line {
            Line::Stmt(Stmt::Schedule(_)) => {}
            Line::Stmt(Stmt::Relation(_)) => {}
            Line::Assign(a) => match &a.expr {
                Expression::Eval(_) => {}
                Expression::Action(act) => {
                    errors.push(err(
                        &frame.register,
                        "R:plan/no-direct-action",
                        format!("R:plan may not invoke verb {:?} directly; schedule it", act.verb),
                    ));
                }
            },
            Line::Stmt(Stmt::Gate(_)) => {
                errors.push(err(
                    &frame.register,
                    "R:plan/schedule-only",
                    "R:plan may only schedule or depend(), not emit gates",
                ));
            }
        }
    }
}

// R:tool — May: any verb. MUST: bind result to %N.
fn validate_tool(frame: &Frame, errors: &mut Vec<GuardrailError>) {
    for line in &frame.lines {
        match line {
            Line::Assign(a) if matches!(a.expr, Expression::Action(_)) => {}
            Line::Assign(_) => {}
            _ => {
                errors.push(err(
                    &frame.register,
                    "R:tool/bind-result",
                    "R:tool actions MUST bind their result to %N",
                ));
            }
        }
    }
}

// R:risk — May: gate, check_permission, block. MUST: emit gate(*:fail) OR a
// mitigation step. MUST NOT: pass silently.
fn validate_risk(frame: &Frame, errors: &mut Vec<GuardrailError>) {
    let mut has_fail_gate = false;
    let mut has_mitigation = false;
    for line in &frame.lines {
        match line {
            Line::Stmt(Stmt::Gate(g)) => {
                if g.state == GateState::Fail {
                    has_fail_gate = true;
                }
            }
            Line::Assign(a) => {
                if let Expression::Action(act) = &a.expr {
                    // A bare `check_permission` is an inquiry, not a mitigation —
                    // it must still resolve to a gate(*:fail) or a `block`
                    // (see the §4 pattern: check_permission then gate(commit:fail)).
                    // Only `block` is itself a mitigation step.
                    if matches!(act.verb, Verb::Block) {
                        has_mitigation = true;
                    }
                }
            }
            _ => {}
        }
    }
    if !has_fail_gate && !has_mitigation {
        errors.push(err(
            &frame.register,
            "R:risk/no-silent-pass",
            "R:risk MUST emit a gate(*:fail) or a mitigation step (block)",
        ));
    }
}

// R:artifact — May: gate, key=value facts. MUST: assert no_cjk / english posture.
fn validate_artifact(frame: &Frame, errors: &mut Vec<GuardrailError>) {
    let mut asserts_posture = false;
    for line in &frame.lines {
        if let Line::Stmt(Stmt::Gate(g)) = line {
            if matches!(g.name, GateName::NoCjk | GateName::English) {
                asserts_posture = true;
            }
        }
    }
    if !asserts_posture {
        errors.push(err(
            &frame.register,
            "R:artifact/posture",
            "R:artifact MUST assert a no_cjk or english posture gate",
        ));
    }
}

// R:commit — May: commit/merge/open. MUST: be preceded by gate(ci:pass).
// MUST NOT: run if any upstream gate(*:fail) (enforced at runtime via is_frozen).
fn validate_commit(frame: &Frame, errors: &mut Vec<GuardrailError>) {
    for line in &frame.lines {
        match line {
            Line::Assign(a) => {
                if let Expression::Action(act) = &a.expr {
                    if !matches!(act.verb, Verb::Commit | Verb::Merge | Verb::Open) {
                        errors.push(err(
                            &frame.register,
                            "R:commit/verb",
                            format!(
                                "R:commit may only commit/merge/open, found {:?}",
                                act.verb
                            ),
                        ));
                    }
                }
            }
            Line::Stmt(Stmt::Gate(_)) => {}
            Line::Stmt(Stmt::Relation(_)) => {}
            Line::Stmt(Stmt::Schedule(_)) => {
                errors.push(err(
                    &frame.register,
                    "R:commit/verb",
                    "R:commit may not schedule; it commits/merges/opens",
                ));
            }
        }
    }
}

// R:review — May: evaluations, gate. MUST NOT: mutate state.
fn validate_review(frame: &Frame, errors: &mut Vec<GuardrailError>) {
    for line in &frame.lines {
        if let Some(verb) = effecting_verb_of(line) {
            if is_side_effecting(verb) {
                errors.push(err(
                    &frame.register,
                    "R:review/no-mutate",
                    format!("R:review may not mutate state via {verb:?}"),
                ));
            }
        }
    }
}

// R:bench — May: test/build actions, gate. MUST: bind metrics in annotation.
fn validate_bench(frame: &Frame, errors: &mut Vec<GuardrailError>) {
    for line in &frame.lines {
        match line {
            Line::Assign(a) => {
                if let Expression::Action(act) = &a.expr {
                    if matches!(act.verb, Verb::Test | Verb::Build) && a.annotation.is_empty() {
                        errors.push(err(
                            &frame.register,
                            "R:bench/metrics",
                            format!(
                                "R:bench {:?} action MUST bind metrics in its annotation",
                                act.verb
                            ),
                        ));
                    }
                }
            }
            Line::Stmt(Stmt::Gate(_)) => {}
            _ => {}
        }
    }
}

/// If `line` directly invokes a verb (assignment action or bare relation has
/// none), return it for register checks.
fn effecting_verb_of(line: &Line) -> Option<&Verb> {
    match line {
        Line::Assign(a) => match &a.expr {
            Expression::Action(act) => Some(&act.verb),
            Expression::Eval(_) => None,
        },
        Line::Stmt(Stmt::Schedule(s)) => Some(&s.target.verb),
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const SECTION4: &str = "[R:bench]  %0 = fetch(pr=205, scope=\"scalars\")\n           %1 = test(target=%0) ; pass=61\n           %2 = build(target=%0, kind=\"rust\") ; duration_s=22\n           %3 = combine(%1, %2)\n           gate(ci:pass) ∵ %3\n[R:risk]   %4 = check_permission(verb=\"merge\", tool=`gh`) ; state=\"classifier_blocked\"\n           gate(commit:fail) ∵ %4\n[R:plan]   depend(%3, %4) → target(user_action=\"paste_merge_cmd\")\n           %5 = launch_agent(scope=\"aggregates\", base=%0)\n[R:commit] %6 = merge(pr=205) ∵ %3        # frozen while gate(commit:fail) live";

    #[test]
    fn parses_section4_example() {
        let frames = parse_message(SECTION4).expect("section 4 must parse");
        assert_eq!(frames.len(), 4);
        assert_eq!(frames[0].register, Register::Bench);
        assert_eq!(frames[0].lines.len(), 5);
        assert_eq!(frames[3].register, Register::Commit);
    }

    #[test]
    fn section4_is_frozen() {
        let frames = parse_message(SECTION4).unwrap();
        assert!(is_frozen(&frames));
    }

    #[test]
    fn compact_equals_long() {
        let long = parse_message("[R:think] %0 = combine(%1, %2)").unwrap();
        let compact = parse_message("[!T] %0 = &(%1, %2)").unwrap();
        assert_eq!(long, compact);
    }

    #[test]
    fn intersect_alias() {
        let long = parse_message("[R:think] %0 = intersect(%1, %2)").unwrap();
        let compact = parse_message("[!T] %0 = ^(%1, %2)").unwrap();
        assert_eq!(long, compact);
    }

    #[test]
    fn think_rejects_side_effect() {
        let frames = parse_message("[R:think] %0 = write(path=lib.rs)").unwrap();
        let errs = validate(&frames).unwrap_err();
        assert_eq!(errs[0].register, Register::Think);
        assert_eq!(errs[0].rule, "R:think/no-side-effect");
    }

    #[test]
    fn risk_must_not_pass_silently() {
        let frames = parse_message("[R:risk] %0 = combine(%1, %2)").unwrap();
        let errs = validate(&frames).unwrap_err();
        assert_eq!(errs[0].rule, "R:risk/no-silent-pass");
    }

    #[test]
    fn not_frozen_without_fail_gate() {
        let frames = parse_message(
            "[R:bench] gate(ci:pass) ∵ %0\n[R:commit] %1 = merge(pr=1) ∵ %0",
        )
        .unwrap();
        assert!(!is_frozen(&frames));
    }
}
