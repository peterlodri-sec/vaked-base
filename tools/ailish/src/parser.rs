//! `nom`-based parser for AI-lish V1 (§2 grammar).
//!
//! One grammar accepts both the long (`[R:think]`, `combine(`) and compact
//! (`[!T]`, `&(`) forms (§5). Whitespace including newlines is treated as
//! intra-frame separator; frames begin at a `[` register token.

use nom::{
    branch::alt,
    bytes::complete::{tag, take_while, take_while1},
    character::complete::{char, multispace0, none_of},
    combinator::{map, opt, recognize, value},
    multi::{many0, many1, separated_list0},
    number::complete::double,
    sequence::{delimited, pair, preceded, separated_pair, terminated},
    IResult,
};

use crate::{
    Action, Arg, Atom, Dataflow, Evaluation, Expression, Frame, Func, Gate, GateName, GateState,
    Line, Literal, Operand, ParseError, Register, Relation, Schedule, SsaAssign, Stmt, Value,
    Variable, Verb,
};

/// Parse a complete message into frames, or report a [`ParseError`].
pub fn parse_message(input: &str) -> Result<Vec<Frame>, ParseError> {
    let stripped = strip_comments(input);
    let result = terminated(many1(frame), multispace0)(stripped.as_str());
    match result {
        Ok(("", frames)) => Ok(frames),
        Ok((rest, _)) => Err(ParseError {
            message: format!("unconsumed input near: {:?}", truncate(rest)),
        }),
        Err(e) => Err(ParseError {
            message: format!("{e}"),
        }),
    }
}

/// Strip `# ...` line comments (as in the §4 `# frozen while ...` note),
/// preserving `#` inside quoted strings and backtick symbols.
fn strip_comments(input: &str) -> String {
    let mut out = String::with_capacity(input.len());
    for raw_line in input.split_inclusive('\n') {
        let mut in_quote = false;
        let mut in_sym = false;
        let mut cut = raw_line.len();
        for (i, c) in raw_line.char_indices() {
            match c {
                '"' if !in_sym => in_quote = !in_quote,
                '`' if !in_quote => in_sym = !in_sym,
                '#' if !in_quote && !in_sym => {
                    cut = i;
                    break;
                }
                _ => {}
            }
        }
        let kept = raw_line[..cut].trim_end_matches([' ', '\t']);
        out.push_str(kept);
        if raw_line.ends_with('\n') {
            out.push('\n');
        }
    }
    out
}

fn truncate(s: &str) -> &str {
    let n = s.char_indices().nth(40).map(|(i, _)| i).unwrap_or(s.len());
    &s[..n]
}

// ---- horizontal whitespace (no newline) ------------------------------------

fn hspace0(input: &str) -> IResult<&str, &str> {
    take_while(|c| c == ' ' || c == '\t')(input)
}

// ---- frame -----------------------------------------------------------------

fn frame(input: &str) -> IResult<&str, Frame> {
    let (input, _) = multispace0(input)?;
    let (input, register) = register(input)?;
    let (input, _) = hspace0(input)?;
    let (input, first) = line(input)?;
    let (input, mut rest) = many0(preceded(line_sep, line))(input)?;
    let mut lines = Vec::with_capacity(rest.len() + 1);
    lines.push(first);
    lines.append(&mut rest);
    Ok((input, Frame { register, lines }))
}

/// A line separator: a `;` OR a newline (so a frame may span lines), each
/// surrounded by optional whitespace. We must NOT cross into the next frame's
/// `[register]`, so after consuming the separator we peek that the next
/// non-space char is not `[`.
fn line_sep(input: &str) -> IResult<&str, ()> {
    // Try an explicit `;` separator first.
    if let Ok((rest, _)) = preceded::<_, _, _, nom::error::Error<&str>, _, _>(
        hspace0,
        char::<_, nom::error::Error<&str>>(';'),
    )(input)
    {
        let (rest, _) = multispace0(rest)?;
        if rest.starts_with('[') || rest.is_empty() {
            // `;` immediately before a new frame is malformed; reject.
            return Err(nom::Err::Error(nom::error::Error::new(
                input,
                nom::error::ErrorKind::Char,
            )));
        }
        return Ok((rest, ()));
    }
    // Otherwise require at least one newline as the separator.
    let (rest, _) = hspace0(input)?;
    let (rest, _) = take_while1(|c| c == '\n' || c == '\r')(rest)?;
    let (rest, _) = multispace0(rest)?;
    if rest.starts_with('[') || rest.is_empty() {
        // Next token starts a new frame (or EOF): not a continuation line.
        return Err(nom::Err::Error(nom::error::Error::new(
            input,
            nom::error::ErrorKind::Many0,
        )));
    }
    Ok((rest, ()))
}

// ---- register --------------------------------------------------------------

fn register(input: &str) -> IResult<&str, Register> {
    delimited(
        char('['),
        alt((
            // Long forms.
            value(Register::Think, tag("R:think")),
            value(Register::Plan, tag("R:plan")),
            value(Register::Tool, tag("R:tool")),
            value(Register::Risk, tag("R:risk")),
            value(Register::Artifact, tag("R:artifact")),
            value(Register::Commit, tag("R:commit")),
            value(Register::Review, tag("R:review")),
            value(Register::Bench, tag("R:bench")),
            // Compact forms (§5).
            value(Register::Think, tag("!T")),
            value(Register::Plan, tag("!P")),
            value(Register::Tool, tag("!X")),
            value(Register::Risk, tag("!R")),
            value(Register::Artifact, tag("!A")),
            value(Register::Commit, tag("!C")),
            value(Register::Review, tag("!V")),
            value(Register::Bench, tag("!B")),
        )),
        char(']'),
    )(input)
}

// ---- line ------------------------------------------------------------------

fn line(input: &str) -> IResult<&str, Line> {
    alt((
        map(ssa_assignment, Line::Assign),
        map(stmt, Line::Stmt),
    ))(input)
}

// ---- ssa assignment --------------------------------------------------------

fn ssa_assignment(input: &str) -> IResult<&str, SsaAssign> {
    let (input, var) = variable(input)?;
    let (input, _) = ws_around(char('='))(input)?;
    let (input, expr) = expression(input)?;
    // §4 attaches a justification `∵ operand` to a commit assignment
    // (`%6 = merge(pr=205) ∵ %3`). The operand is the evidence link; the AST
    // captures the gate justifications used by the freeze invariant, so the
    // assignment-level `∵` is accepted and dropped (the formatter never re-emits
    // it, keeping round-trips idempotent).
    let (input, _) = opt(preceded(ws_around(char('∵')), operand))(input)?;
    let (input, annotation) = opt(annotation)(input)?;
    Ok((
        input,
        SsaAssign {
            var,
            expr,
            annotation: annotation.unwrap_or_default(),
        },
    ))
}

fn expression(input: &str) -> IResult<&str, Expression> {
    // `func(...)` is a pure eval; any other call is an action. Try eval first
    // because the func vocabulary (and aliases) is a strict subset.
    alt((
        map(evaluation, Expression::Eval),
        map(action, Expression::Action),
    ))(input)
}

fn action(input: &str) -> IResult<&str, Action> {
    let (input, verb) = verb(input)?;
    let (input, args) = call_args(input)?;
    Ok((input, Action { verb, args }))
}

fn evaluation(input: &str) -> IResult<&str, Evaluation> {
    // The compact aliases `&(` / `^(` glue the operator to the paren, so the
    // func parser must consume up to and including the `(`. We parse the func
    // token, then the rest of the call.
    let (input, (func, args)) = func_call(input)?;
    Ok((input, Evaluation { func, args }))
}

/// Parse a pure-func head plus its argument list. Handles both long
/// (`combine(`) and compact (`&(`) forms; positional args are accepted as
/// bare values rendered as `_0=`, `_1=` keys? No — §2 args are key=value, but
/// the §4 example passes bare `%N`. We accept both: a bare operand becomes an
/// arg with an empty key.
fn func_call(input: &str) -> IResult<&str, (Func, Vec<Arg>)> {
    alt((
        // Long forms: name then `(`.
        func_named(Func::Combine, "combine"),
        func_named(Func::Join, "join"),
        func_named(Func::Intersect, "intersect"),
        func_named(Func::Depend, "depend"),
        // Compact aliases: the operator already includes `(`.
        func_alias(Func::Combine, "&("),
        func_alias(Func::Intersect, "^("),
    ))(input)
}

fn func_named<'a>(
    f: Func,
    name: &'static str,
) -> impl FnMut(&'a str) -> IResult<&'a str, (Func, Vec<Arg>)> {
    move |input: &'a str| {
        let (input, _) = tag(name)(input)?;
        let (input, args) = call_args(input)?;
        Ok((input, (f.clone(), args)))
    }
}

fn func_alias<'a>(
    f: Func,
    op: &'static str,
) -> impl FnMut(&'a str) -> IResult<&'a str, (Func, Vec<Arg>)> {
    move |input: &'a str| {
        let (input, _) = tag(op)(input)?;
        // `op` already consumed the `(`; parse the body and closing `)`.
        let (input, args) = arg_body(input)?;
        Ok((input, (f.clone(), args)))
    }
}

/// `( args? )` — leading `(` present.
fn call_args(input: &str) -> IResult<&str, Vec<Arg>> {
    let (input, _) = char('(')(input)?;
    arg_body(input)
}

/// The interior of an argument list plus closing `)`. Accepts both
/// `key=value` args and bare operands (rendered as positional args with an
/// empty key, used by pure funcs in the §4 example).
fn arg_body(input: &str) -> IResult<&str, Vec<Arg>> {
    let (input, _) = hspace0(input)?;
    let (input, args) = separated_list0(ws_around(char(',')), arg)(input)?;
    let (input, _) = hspace0(input)?;
    let (input, _) = char(')')(input)?;
    Ok((input, args))
}

fn arg(input: &str) -> IResult<&str, Arg> {
    alt((
        // key=value
        map(
            separated_pair(ident, ws_around(char('=')), value_parser),
            |(key, value)| Arg {
                key: key.to_string(),
                value,
            },
        ),
        // bare positional operand (pure-func style)
        map(value_parser, |value| Arg {
            key: String::new(),
            value,
        }),
    ))(input)
}

fn value_parser(input: &str) -> IResult<&str, Value> {
    alt((
        map(variable, Value::Var),
        map(typed_atom, Value::Atom),
    ))(input)
}

// ---- statements ------------------------------------------------------------

fn stmt(input: &str) -> IResult<&str, Stmt> {
    alt((
        map(gate, Stmt::Gate),
        map(schedule, Stmt::Schedule),
        map(relation, Stmt::Relation),
    ))(input)
}

fn schedule(input: &str) -> IResult<&str, Schedule> {
    // `→ target(...)` — `target` is parsed as an action whose verb token is the
    // literal `target`. Since `target` isn't in the verb vocab, we accept it
    // specially here and store it as a synthetic action.
    //
    // §3 also permits an `R:plan` line to be a `depend()` evaluation that feeds
    // a schedule, as in the §4 example `depend(%3, %4) → target(...)`. We accept
    // an optional leading evaluation before the `→`; the dependency it carries
    // is contextual and the schedule's `target` is what the AST captures.
    let (input, _) = opt(terminated(evaluation, ws_around(char('→'))))(input)?;
    let (input, _) = opt(char('→'))(input)?;
    let (input, _) = hspace0(input)?;
    let (input, _) = tag("target")(input)?;
    let (input, args) = call_args(input)?;
    Ok((
        input,
        Schedule {
            // `target(...)` schedules a host action; we model the directive as
            // an Open action carrying the scheduling args. The verb is a
            // placeholder — a schedule never executes.
            target: Action {
                verb: Verb::Open,
                args,
            },
        },
    ))
}

fn gate(input: &str) -> IResult<&str, Gate> {
    let (input, _) = tag("gate(")(input)?;
    let (input, name) = gate_name(input)?;
    let (input, _) = char(':')(input)?;
    let (input, state) = gate_state(input)?;
    let (input, _) = char(')')(input)?;
    let (input, because) = opt(preceded(ws_around(char('∵')), operand))(input)?;
    Ok((
        input,
        Gate {
            name,
            state,
            because,
        },
    ))
}

fn gate_name(input: &str) -> IResult<&str, GateName> {
    alt((
        value(GateName::Artifact, tag("artifact")),
        value(GateName::English, tag("english")),
        value(GateName::NoCjk, tag("no_cjk")),
        value(GateName::Ci, tag("ci")),
        value(GateName::Bench, tag("bench")),
        value(GateName::Parse, tag("parse")),
        value(GateName::Commit, tag("commit")),
    ))(input)
}

fn gate_state(input: &str) -> IResult<&str, GateState> {
    alt((
        value(GateState::Pass, tag("pass")),
        value(GateState::Fail, tag("fail")),
        value(GateState::Warn, tag("warn")),
        value(GateState::Skip, tag("skip")),
    ))(input)
}

fn relation(input: &str) -> IResult<&str, Relation> {
    let (input, lhs) = operand(input)?;
    let (input, flow) = ws_around(dataflow)(input)?;
    let (input, rhs) = operand(input)?;
    Ok((input, Relation { lhs, flow, rhs }))
}

fn dataflow(input: &str) -> IResult<&str, Dataflow> {
    alt((
        value(Dataflow::Feeds, char('→')),
        value(Dataflow::Justifies, char('∵')),
    ))(input)
}

fn operand(input: &str) -> IResult<&str, Operand> {
    alt((
        map(variable, Operand::Var),
        map(typed_atom, Operand::Atom),
    ))(input)
}

// ---- atoms -----------------------------------------------------------------

fn variable(input: &str) -> IResult<&str, Variable> {
    let (input, _) = char('%')(input)?;
    let (input, digits) = take_while1(|c: char| c.is_ascii_digit())(input)?;
    let n: u32 = digits.parse().map_err(|_| {
        nom::Err::Error(nom::error::Error::new(input, nom::error::ErrorKind::Digit))
    })?;
    Ok((input, Variable(n)))
}

fn typed_atom(input: &str) -> IResult<&str, Atom> {
    alt((
        map(literal, Atom::Literal),
        map(env_ref, |s| Atom::Env(s.to_string())),
        map(symbol, |s| Atom::Symbol(s.to_string())),
        map(path, |s| Atom::Path(s.to_string())),
    ))(input)
}

fn literal(input: &str) -> IResult<&str, Literal> {
    alt((
        value(Literal::Bool(true), tag("true")),
        value(Literal::Bool(false), tag("false")),
        map(quoted, |s| Literal::Quoted(s.to_string())),
        map(number, Literal::Number),
    ))(input)
}

fn number(input: &str) -> IResult<&str, f64> {
    // `double` would happily eat a leading number out of a path like `205abc`;
    // guard by ensuring the next char isn't a path continuation.
    let (rest, n) = double(input)?;
    if let Some(c) = rest.chars().next() {
        if is_path_char(c) {
            return Err(nom::Err::Error(nom::error::Error::new(
                input,
                nom::error::ErrorKind::Float,
            )));
        }
    }
    Ok((rest, n))
}

fn quoted(input: &str) -> IResult<&str, &str> {
    delimited(char('"'), recognize(many0(none_of("\""))), char('"'))(input)
}

fn symbol(input: &str) -> IResult<&str, &str> {
    delimited(char('`'), recognize(many0(none_of("`"))), char('`'))(input)
}

fn env_ref(input: &str) -> IResult<&str, &str> {
    preceded(char('$'), ident)(input)
}

fn is_path_char(c: char) -> bool {
    c.is_ascii_alphanumeric() || matches!(c, '_' | '.' | '/' | ':' | '-')
}

fn path(input: &str) -> IResult<&str, &str> {
    take_while1(is_path_char)(input)
}

fn ident(input: &str) -> IResult<&str, &str> {
    recognize(pair(
        take_while1(|c: char| c.is_ascii_alphabetic() || c == '_'),
        take_while(|c: char| c.is_ascii_alphanumeric() || c == '_' || c == '-'),
    ))(input)
}

// ---- verbs -----------------------------------------------------------------

fn verb(input: &str) -> IResult<&str, Verb> {
    alt((
        // Longer tokens first to avoid prefix shadowing (e.g. `agent_write`
        // before any `agent`; `check_permission` before nothing, etc.).
        value(Verb::LaunchAgent, tag("launch_agent")),
        value(Verb::AgentWrite, tag("agent_write")),
        value(Verb::CheckPermission, tag("check_permission")),
        value(Verb::Block, tag("block")),
        value(Verb::Fetch, tag("fetch")),
        value(Verb::Read, tag("read")),
        value(Verb::Edit, tag("edit")),
        value(Verb::Write, tag("write")),
        value(Verb::Test, tag("test")),
        value(Verb::Build, tag("build")),
        value(Verb::Diff, tag("diff")),
        value(Verb::Commit, tag("commit")),
        value(Verb::Open, tag("open")),
        value(Verb::Merge, tag("merge")),
    ))(input)
}

// ---- annotation ------------------------------------------------------------

fn annotation(input: &str) -> IResult<&str, Vec<Arg>> {
    let (input, _) = ws_around(char(';'))(input)?;
    separated_list0(ws_around(char(',')), annotation_arg)(input)
}

fn annotation_arg(input: &str) -> IResult<&str, Arg> {
    map(
        separated_pair(ident, ws_around(char('=')), value_parser),
        |(key, value)| Arg {
            key: key.to_string(),
            value,
        },
    )(input)
}

// ---- helpers ---------------------------------------------------------------

/// Wrap a parser so horizontal whitespace on either side is consumed.
fn ws_around<'a, O, F>(mut inner: F) -> impl FnMut(&'a str) -> IResult<&'a str, O>
where
    F: FnMut(&'a str) -> IResult<&'a str, O>,
{
    move |input: &'a str| {
        let (input, _) = hspace0(input)?;
        let (input, out) = inner(input)?;
        let (input, _) = hspace0(input)?;
        Ok((input, out))
    }
}
