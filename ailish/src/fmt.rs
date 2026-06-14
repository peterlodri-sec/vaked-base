//! `ailishfmt` rendering + token compaction (RFC §5, Phase C).
//!
//! Renders a [`Message`] back to text in either the canonical **long** form or
//! the **compact** form (RFC §5 map). Rendering is deterministic and the parser
//! round-trips it, so `format(format(x)) == format(x)` — the formatter is
//! idempotent in each mode. [`count_tokens`] gives a cheap token proxy for the
//! long-vs-compact benchmark.

use crate::ast::*;

const INDENT: &str = "  ";

fn render_atom(a: &Atom) -> String {
    match a {
        Atom::Number(s) => s.clone(),
        Atom::Quoted(s) => format!("\"{s}\""),
        Atom::Bool(true) => "true".to_string(),
        Atom::Bool(false) => "false".to_string(),
        Atom::Env(s) => format!("${s}"),
        Atom::Path(s) => s.clone(),
        Atom::Symbol(s) => format!("`{s}`"),
    }
}

fn render_operand(o: &Operand) -> String {
    match o {
        Operand::Var(Var(n)) => format!("%{n}"),
        Operand::Atom(a) => render_atom(a),
    }
}

fn render_arg(a: &Arg) -> String {
    match a {
        Arg::Named { key, value } => format!("{key}={}", render_operand(value)),
        Arg::Positional(o) => render_operand(o),
    }
}

fn render_args(args: &[Arg]) -> String {
    args.iter().map(render_arg).collect::<Vec<_>>().join(", ")
}

fn render_func_head(f: Func, compact: bool) -> String {
    if compact {
        match f {
            Func::Combine => return "&".to_string(),
            Func::Intersect => return "^".to_string(),
            _ => {}
        }
    }
    f.long().to_string()
}

fn render_expr(e: &Expr, compact: bool) -> String {
    match e {
        Expr::Action { verb, args } => format!("{}({})", verb.name(), render_args(args)),
        Expr::Eval { func, args } => {
            format!(
                "{}({})",
                render_func_head(*func, compact),
                render_args(args)
            )
        }
    }
}

fn render_call_name(name: &str, compact: bool) -> String {
    if compact {
        match name {
            "combine" => return "&".to_string(),
            "intersect" => return "^".to_string(),
            _ => {}
        }
    }
    name.to_string()
}

fn render_call(c: &Call, compact: bool) -> String {
    format!(
        "{}({})",
        render_call_name(&c.name, compact),
        render_args(&c.args)
    )
}

fn render_flow_term(t: &FlowTerm, compact: bool) -> String {
    match t {
        FlowTerm::Operand(o) => render_operand(o),
        FlowTerm::Call(c) => render_call(c, compact),
    }
}

fn render_dataflow(d: Dataflow) -> &'static str {
    match d {
        Dataflow::Then => "→",
        Dataflow::Because => "∵",
    }
}

fn render_annotation(ann: &[(String, Operand)]) -> String {
    ann.iter()
        .map(|(k, v)| format!("{k}={}", render_operand(v)))
        .collect::<Vec<_>>()
        .join(", ")
}

fn render_line(line: &Line, compact: bool) -> String {
    match line {
        Line::Assign(a) => {
            let mut s = format!("%{} = {}", a.var.0, render_expr(&a.expr, compact));
            if !a.annotation.is_empty() {
                s.push_str(&format!(" ; {}", render_annotation(&a.annotation)));
            }
            if let Some(b) = &a.because {
                s.push_str(&format!(" ∵ {}", render_operand(b)));
            }
            s
        }
        Line::Gate(g) => {
            let mut s = format!("gate({}:{})", g.name.name(), g.state.name());
            if let Some(b) = &g.because {
                s.push_str(&format!(" ∵ {}", render_operand(b)));
            }
            s
        }
        Line::Flow(f) => {
            let rhs = render_flow_term(&f.rhs, compact);
            match &f.lhs {
                Some(lhs) => format!(
                    "{} {} {}",
                    render_flow_term(lhs, compact),
                    render_dataflow(f.op),
                    rhs
                ),
                None => format!("{} {}", render_dataflow(f.op), rhs),
            }
        }
    }
}

fn render_register(r: Register, compact: bool) -> String {
    if compact {
        format!("[{}]", r.compact())
    } else {
        format!("[{}]", r.long())
    }
}

fn render_frame(frame: &Frame, compact: bool) -> String {
    let mut out = render_register(frame.register, compact);
    for line in &frame.lines {
        out.push('\n');
        out.push_str(INDENT);
        out.push_str(&render_line(line, compact));
    }
    out
}

/// Render a full message in long (`compact = false`) or compact form.
pub fn render(msg: &Message, compact: bool) -> String {
    let mut out = msg
        .frames
        .iter()
        .map(|f| render_frame(f, compact))
        .collect::<Vec<_>>()
        .join("\n");
    out.push('\n');
    out
}

/// Parse then re-render `src`; idempotent in each mode.
pub fn format_message(src: &str, compact: bool) -> Result<String, String> {
    let msg = crate::parse_message(src)?;
    Ok(render(&msg, compact))
}

/// A cheap token proxy: structural punctuation each counts as one token, the
/// rest split on whitespace. Good enough to compare long vs compact forms.
pub fn count_tokens(s: &str) -> usize {
    let mut spaced = String::with_capacity(s.len() * 2);
    for c in s.chars() {
        if matches!(c, '(' | ')' | '[' | ']' | ',' | ';' | '=' | ':' | '→' | '∵') {
            spaced.push(' ');
            spaced.push(c);
            spaced.push(' ');
        } else {
            spaced.push(c);
        }
    }
    spaced.split_whitespace().count()
}
