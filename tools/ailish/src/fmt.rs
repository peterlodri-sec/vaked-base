//! Phase C — `ailishfmt`, the idempotent formatter, plus the §5 token
//! compaction map and a coarse token estimator for the long-vs-compact bench.

use crate::{
    Action, Arg, Atom, Dataflow, Evaluation, Expression, Frame, Func, Gate, GateName, GateState,
    Line, Literal, Operand, Register, Relation, Schedule, SsaAssign, Stmt, Value, Variable, Verb,
};

/// Output dialect for [`ailishfmt`].
#[derive(Debug, Clone, PartialEq)]
pub enum FmtMode {
    /// Canonical human-readable form (`[R:think]`, `combine(`).
    Long,
    /// Token-compacted form (§5): `[!T]`, `&(`, `^(`.
    Compact,
}

/// Render frames to canonical AI-lish text in the requested mode.
///
/// Idempotent: `ailishfmt(parse_message(&ailishfmt(f, m)).unwrap(), m)` equals
/// `ailishfmt(f, m)` for any well-formed `f`.
pub fn ailishfmt(frames: &[Frame], mode: FmtMode) -> String {
    let mut out = String::new();
    for (i, frame) in frames.iter().enumerate() {
        if i > 0 {
            out.push('\n');
        }
        out.push_str(&render_register(&frame.register, &mode));
        for (j, line) in frame.lines.iter().enumerate() {
            if j == 0 {
                out.push(' ');
            } else {
                out.push('\n');
            }
            out.push_str(&render_line(line, &mode));
        }
    }
    out
}

fn render_register(register: &Register, mode: &FmtMode) -> String {
    let token = match (register, mode) {
        (Register::Think, FmtMode::Long) => "R:think",
        (Register::Plan, FmtMode::Long) => "R:plan",
        (Register::Tool, FmtMode::Long) => "R:tool",
        (Register::Risk, FmtMode::Long) => "R:risk",
        (Register::Artifact, FmtMode::Long) => "R:artifact",
        (Register::Commit, FmtMode::Long) => "R:commit",
        (Register::Review, FmtMode::Long) => "R:review",
        (Register::Bench, FmtMode::Long) => "R:bench",
        (Register::Think, FmtMode::Compact) => "!T",
        (Register::Plan, FmtMode::Compact) => "!P",
        (Register::Tool, FmtMode::Compact) => "!X",
        (Register::Risk, FmtMode::Compact) => "!R",
        (Register::Artifact, FmtMode::Compact) => "!A",
        (Register::Commit, FmtMode::Compact) => "!C",
        (Register::Review, FmtMode::Compact) => "!V",
        (Register::Bench, FmtMode::Compact) => "!B",
    };
    format!("[{token}]")
}

fn render_line(line: &Line, mode: &FmtMode) -> String {
    match line {
        Line::Assign(a) => render_assign(a, mode),
        Line::Stmt(s) => render_stmt(s, mode),
    }
}

fn render_assign(a: &SsaAssign, mode: &FmtMode) -> String {
    let mut s = format!("{} = {}", render_var(&a.var), render_expr(&a.expr, mode));
    if !a.annotation.is_empty() {
        s.push_str(" ; ");
        s.push_str(&render_args(&a.annotation, mode));
    }
    s
}

fn render_expr(expr: &Expression, mode: &FmtMode) -> String {
    match expr {
        Expression::Action(act) => render_action(act, mode),
        Expression::Eval(ev) => render_eval(ev, mode),
    }
}

fn render_action(act: &Action, mode: &FmtMode) -> String {
    format!("{}({})", render_verb(&act.verb), render_args(&act.args, mode))
}

fn render_eval(ev: &Evaluation, mode: &FmtMode) -> String {
    let head = match (mode, &ev.func) {
        (FmtMode::Compact, Func::Combine) => "&(".to_string(),
        (FmtMode::Compact, Func::Intersect) => "^(".to_string(),
        (_, func) => format!("{}(", render_func(func)),
    };
    format!("{}{})", head, render_args(&ev.args, mode))
}

fn render_stmt(stmt: &Stmt, mode: &FmtMode) -> String {
    match stmt {
        Stmt::Relation(r) => render_relation(r, mode),
        Stmt::Gate(g) => render_gate(g, mode),
        Stmt::Schedule(s) => render_schedule(s, mode),
    }
}

fn render_relation(r: &Relation, mode: &FmtMode) -> String {
    format!(
        "{} {} {}",
        render_operand(&r.lhs, mode),
        render_dataflow(&r.flow),
        render_operand(&r.rhs, mode)
    )
}

fn render_dataflow(flow: &Dataflow) -> &'static str {
    match flow {
        Dataflow::Feeds => "→",
        Dataflow::Justifies => "∵",
    }
}

fn render_schedule(s: &Schedule, mode: &FmtMode) -> String {
    format!("→ target({})", render_args(&s.target.args, mode))
}

fn render_gate(g: &Gate, mode: &FmtMode) -> String {
    let mut s = format!("gate({}:{})", render_gate_name(&g.name), render_gate_state(&g.state));
    if let Some(operand) = &g.because {
        s.push_str(" ∵ ");
        s.push_str(&render_operand(operand, mode));
    }
    s
}

fn render_args(args: &[Arg], mode: &FmtMode) -> String {
    args.iter()
        .map(|a| render_arg(a, mode))
        .collect::<Vec<_>>()
        .join(", ")
}

fn render_arg(arg: &Arg, mode: &FmtMode) -> String {
    if arg.key.is_empty() {
        render_value(&arg.value, mode)
    } else {
        format!("{}={}", arg.key, render_value(&arg.value, mode))
    }
}

fn render_value(value: &Value, mode: &FmtMode) -> String {
    match value {
        Value::Var(v) => render_var(v),
        Value::Atom(a) => render_atom(a, mode),
    }
}

fn render_operand(operand: &Operand, mode: &FmtMode) -> String {
    match operand {
        Operand::Var(v) => render_var(v),
        Operand::Atom(a) => render_atom(a, mode),
    }
}

fn render_var(v: &Variable) -> String {
    format!("%{}", v.0)
}

fn render_atom(atom: &Atom, _mode: &FmtMode) -> String {
    match atom {
        Atom::Literal(l) => render_literal(l),
        Atom::Env(s) => format!("${s}"),
        Atom::Path(s) => s.clone(),
        Atom::Symbol(s) => format!("`{s}`"),
    }
}

fn render_literal(l: &Literal) -> String {
    match l {
        Literal::Number(n) => render_number(*n),
        Literal::Quoted(s) => format!("\"{s}\""),
        Literal::Bool(b) => b.to_string(),
    }
}

/// Render a number canonically: integral values without a trailing `.0` so the
/// round-trip `205` → `205.0` → `205` is stable.
fn render_number(n: f64) -> String {
    if n.is_finite() && n.fract() == 0.0 && n.abs() < 1e15 {
        format!("{}", n as i64)
    } else {
        let mut s = format!("{n}");
        if !s.contains('.') && !s.contains('e') && !s.contains("inf") && !s.contains("NaN") {
            s.push_str(".0");
        }
        s
    }
}

fn render_verb(verb: &Verb) -> &'static str {
    match verb {
        Verb::Fetch => "fetch",
        Verb::Read => "read",
        Verb::Edit => "edit",
        Verb::Write => "write",
        Verb::Test => "test",
        Verb::Build => "build",
        Verb::Diff => "diff",
        Verb::Commit => "commit",
        Verb::Open => "open",
        Verb::Merge => "merge",
        Verb::LaunchAgent => "launch_agent",
        Verb::AgentWrite => "agent_write",
        Verb::CheckPermission => "check_permission",
        Verb::Block => "block",
    }
}

fn render_func(func: &Func) -> &'static str {
    match func {
        Func::Combine => "combine",
        Func::Join => "join",
        Func::Intersect => "intersect",
        Func::Depend => "depend",
    }
}

fn render_gate_name(name: &GateName) -> &'static str {
    match name {
        GateName::Artifact => "artifact",
        GateName::English => "english",
        GateName::NoCjk => "no_cjk",
        GateName::Ci => "ci",
        GateName::Bench => "bench",
        GateName::Parse => "parse",
        GateName::Commit => "commit",
    }
}

fn render_gate_state(state: &GateState) -> &'static str {
    match state {
        GateState::Pass => "pass",
        GateState::Fail => "fail",
        GateState::Warn => "warn",
        GateState::Skip => "skip",
    }
}

/// A coarse, deterministic token proxy: the count of whitespace- and
/// punctuation-delimited lexemes. Used only to compare long vs compact density
/// in the bench — not a real tokenizer.
pub fn token_estimate(s: &str) -> usize {
    let mut count = 0usize;
    let mut in_token = false;
    for c in s.chars() {
        let boundary = c.is_whitespace()
            || matches!(
                c,
                '(' | ')' | ',' | ';' | '=' | ':' | '[' | ']' | '→' | '∵' | '`' | '"'
            );
        if boundary {
            if in_token {
                count += 1;
                in_token = false;
            }
            // Count structural punctuation (non-whitespace) as its own token.
            if !c.is_whitespace() {
                count += 1;
            }
        } else {
            in_token = true;
        }
    }
    if in_token {
        count += 1;
    }
    count
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::parse_message;

    const SECTION4: &str = "[R:bench] %0 = fetch(pr=205, scope=\"scalars\")\n%1 = test(target=%0) ; pass=61\n%2 = build(target=%0, kind=\"rust\") ; duration_s=22\n%3 = combine(%1, %2)\ngate(ci:pass) ∵ %3\n[R:risk] %4 = check_permission(verb=\"merge\", tool=`gh`) ; state=\"classifier_blocked\"\ngate(commit:fail) ∵ %4\n[R:plan] depend(%3, %4) → target(user_action=\"paste_merge_cmd\")\n%5 = launch_agent(scope=\"aggregates\", base=%0)\n[R:commit] %6 = merge(pr=205) ∵ %3";

    fn idempotent(input: &str, mode: FmtMode) {
        let frames = parse_message(input).expect("parse");
        let once = ailishfmt(&frames, mode.clone());
        let twice = ailishfmt(&parse_message(&once).expect("reparse"), mode);
        assert_eq!(once, twice, "ailishfmt not idempotent");
    }

    #[test]
    fn long_is_idempotent() {
        idempotent(SECTION4, FmtMode::Long);
    }

    #[test]
    fn compact_is_idempotent() {
        idempotent(SECTION4, FmtMode::Compact);
    }

    #[test]
    fn compact_is_denser() {
        let frames = parse_message(SECTION4).unwrap();
        let long = ailishfmt(&frames, FmtMode::Long);
        let compact = ailishfmt(&frames, FmtMode::Compact);
        assert!(token_estimate(&compact) <= token_estimate(&long));
    }

    #[test]
    fn long_and_compact_parse_equal() {
        let frames = parse_message(SECTION4).unwrap();
        let long = ailishfmt(&frames, FmtMode::Long);
        let compact = ailishfmt(&frames, FmtMode::Compact);
        assert_eq!(parse_message(&long).unwrap(), parse_message(&compact).unwrap());
    }
}
