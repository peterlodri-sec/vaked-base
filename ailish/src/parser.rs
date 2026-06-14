//! nom-based parser for AI-lish V1 (RFC §2, Phase B).
//!
//! Framing (splitting a message into register-tagged frames) is handled in
//! [`crate::lib`]; this module parses an individual physical line into a
//! [`Line`] and exposes the line-level grammar productions. Both the long form
//! (`combine(%1, %2)`) and the compact form (`&(%1, %2)`, RFC §5) parse under
//! one grammar.

use nom::{
    branch::alt,
    bytes::complete::{tag, take_while, take_while1},
    character::complete::{char, multispace0, satisfy},
    combinator::{all_consuming, map, opt, recognize, value},
    error::{Error, ErrorKind},
    multi::{separated_list0, separated_list1},
    sequence::{delimited, pair},
    IResult,
};

use crate::ast::*;

// --- lexical helpers --------------------------------------------------------

fn is_path_char(c: char) -> bool {
    c.is_ascii_alphanumeric() || matches!(c, '_' | '.' | '/' | ':' | '-')
}
fn is_ident_start(c: char) -> bool {
    c.is_ascii_alphabetic() || c == '_'
}
fn is_ident_char(c: char) -> bool {
    c.is_ascii_alphanumeric() || c == '_' || c == '-'
}

/// Skip leading whitespace before `inner`.
fn lex<'a, O, F>(mut inner: F) -> impl FnMut(&'a str) -> IResult<&'a str, O>
where
    F: FnMut(&'a str) -> IResult<&'a str, O>,
{
    move |i: &'a str| {
        let (i, _) = multispace0(i)?;
        inner(i)
    }
}

fn err<I>(i: I) -> nom::Err<Error<I>> {
    nom::Err::Error(Error::new(i, ErrorKind::Tag))
}

fn ident(i: &str) -> IResult<&str, &str> {
    recognize(pair(satisfy(is_ident_start), take_while(is_ident_char)))(i)
}

// --- atoms / operands (RFC §2 typed_atom, operand) --------------------------

fn var(i: &str) -> IResult<&str, Var> {
    let (i, _) = char('%')(i)?;
    let (i, d) = take_while1(|c: char| c.is_ascii_digit())(i)?;
    let n = d.parse::<u64>().map_err(|_| err(i))?;
    Ok((i, Var(n)))
}

fn quoted(i: &str) -> IResult<&str, Atom> {
    let (i, _) = char('"')(i)?;
    let (i, s) = take_while(|c| c != '"')(i)?;
    let (i, _) = char('"')(i)?;
    Ok((i, Atom::Quoted(s.to_string())))
}

fn env(i: &str) -> IResult<&str, Atom> {
    let (i, _) = char('$')(i)?;
    let (i, s) = ident(i)?;
    Ok((i, Atom::Env(s.to_string())))
}

fn symbol(i: &str) -> IResult<&str, Atom> {
    let (i, _) = char('`')(i)?;
    let (i, s) = take_while(|c| c != '`')(i)?;
    let (i, _) = char('`')(i)?;
    Ok((i, Atom::Symbol(s.to_string())))
}

fn is_number(s: &str) -> bool {
    // -?[0-9]+(\.[0-9]+)?
    let b = s.strip_prefix('-').unwrap_or(s);
    let mut parts = b.splitn(2, '.');
    let int = match parts.next() {
        Some(x) => x,
        None => return false,
    };
    if int.is_empty() || !int.bytes().all(|c| c.is_ascii_digit()) {
        return false;
    }
    if let Some(frac) = parts.next() {
        if frac.is_empty() || !frac.bytes().all(|c| c.is_ascii_digit()) {
            return false;
        }
    }
    true
}

fn classify_bareword(s: &str) -> Atom {
    match s {
        "true" => Atom::Bool(true),
        "false" => Atom::Bool(false),
        _ if is_number(s) => Atom::Number(s.to_string()),
        _ => Atom::Path(s.to_string()),
    }
}

fn bareword(i: &str) -> IResult<&str, Atom> {
    let (i, s) = take_while1(is_path_char)(i)?;
    Ok((i, classify_bareword(s)))
}

fn atom(i: &str) -> IResult<&str, Atom> {
    alt((quoted, env, symbol, bareword))(i)
}

fn operand(i: &str) -> IResult<&str, Operand> {
    alt((map(var, Operand::Var), map(atom, Operand::Atom)))(i)
}

// --- arguments (RFC §2 args/arg) --------------------------------------------

fn named_arg(i: &str) -> IResult<&str, Arg> {
    let (i, k) = ident(i)?;
    let (i, _) = lex(char('='))(i)?;
    let (i, v) = lex(operand)(i)?;
    Ok((
        i,
        Arg::Named {
            key: k.to_string(),
            value: v,
        },
    ))
}

fn arg(i: &str) -> IResult<&str, Arg> {
    alt((named_arg, map(operand, Arg::Positional)))(i)
}

fn arg_list(i: &str) -> IResult<&str, Vec<Arg>> {
    separated_list0(lex(char(',')), lex(arg))(i)
}

// --- calls / expressions (RFC §2 expression, action, evaluation) ------------

/// Parse a call head, accepting compact func sigils (`&` → combine, `^` →
/// intersect, RFC §5) or a long identifier. Positioned just before `(`.
fn call_head(i: &str) -> IResult<&str, String> {
    alt((
        value("combine".to_string(), char('&')),
        value("intersect".to_string(), char('^')),
        map(ident, |s: &str| s.to_string()),
    ))(i)
}

fn parens(i: &str) -> IResult<&str, Vec<Arg>> {
    delimited(lex(char('(')), arg_list, lex(char(')')))(i)
}

/// Assignment expression: `action` (verb) or `evaluation` (pure func).
fn expr(i: &str) -> IResult<&str, Expr> {
    let (i, name) = call_head(i)?;
    let (i, args) = parens(i)?;
    if let Some(v) = Verb::from_name(&name) {
        Ok((i, Expr::Action { verb: v, args }))
    } else if let Some(f) = Func::from_name(&name) {
        Ok((i, Expr::Eval { func: f, args }))
    } else {
        Err(err(i))
    }
}

/// Generic call used as a dataflow term (`depend(...)`, `target(...)`).
fn call(i: &str) -> IResult<&str, Call> {
    let (i, name) = call_head(i)?;
    let (i, args) = parens(i)?;
    Ok((i, Call { name, args }))
}

fn flow_term(i: &str) -> IResult<&str, FlowTerm> {
    alt((map(call, FlowTerm::Call), map(operand, FlowTerm::Operand)))(i)
}

fn dataflow(i: &str) -> IResult<&str, Dataflow> {
    alt((
        value(Dataflow::Then, char('→')),
        value(Dataflow::Because, char('∵')),
    ))(i)
}

// --- line suffixes (annotation / justification) -----------------------------

fn kv(i: &str) -> IResult<&str, (String, Operand)> {
    let (i, k) = ident(i)?;
    let (i, _) = lex(char('='))(i)?;
    let (i, v) = lex(operand)(i)?;
    Ok((i, (k.to_string(), v)))
}

fn annotation(i: &str) -> IResult<&str, Vec<(String, Operand)>> {
    let (i, _) = lex(char(';'))(i)?;
    separated_list1(lex(char(',')), lex(kv))(i)
}

fn because(i: &str) -> IResult<&str, Operand> {
    let (i, _) = lex(char('∵'))(i)?;
    lex(operand)(i)
}

// --- lines (RFC §2 line) ----------------------------------------------------

fn assign(i: &str) -> IResult<&str, Line> {
    let (i, v) = var(i)?;
    let (i, _) = lex(char('='))(i)?;
    let (i, e) = lex(expr)(i)?;

    // Optional `; k=v` annotation and/or `∵ operand` justification, any order.
    let mut input = i;
    let mut ann: Vec<(String, Operand)> = Vec::new();
    let mut bec: Option<Operand> = None;
    loop {
        if let Ok((rest, a)) = annotation(input) {
            ann.extend(a);
            input = rest;
            continue;
        }
        if bec.is_none() {
            if let Ok((rest, b)) = because(input) {
                bec = Some(b);
                input = rest;
                continue;
            }
        }
        break;
    }

    Ok((
        input,
        Line::Assign(Assign {
            var: v,
            expr: e,
            annotation: ann,
            because: bec,
        }),
    ))
}

fn gate_line(i: &str) -> IResult<&str, Line> {
    let (i, _) = tag("gate")(i)?;
    let (i, _) = lex(char('('))(i)?;
    let (i, nm) = lex(ident)(i)?;
    let (i, _) = lex(char(':'))(i)?;
    let (i, st) = lex(ident)(i)?;
    let (i, _) = lex(char(')'))(i)?;
    let name = GateName::from_name(nm).ok_or_else(|| err(i))?;
    let state = GateState::from_name(st).ok_or_else(|| err(i))?;
    let (i, bec) = opt(because)(i)?;
    Ok((
        i,
        Line::Gate(GateStmt {
            name,
            state,
            because: bec,
        }),
    ))
}

fn flow_line(i: &str) -> IResult<&str, Line> {
    // schedule: `→ target` (no lhs), RFC §2 schedule.
    if let Ok((rest, op)) = lex(dataflow)(i) {
        let (rest, rhs) = lex(flow_term)(rest)?;
        return Ok((rest, Line::Flow(FlowStmt { lhs: None, op, rhs })));
    }
    let (i, lhs) = lex(flow_term)(i)?;
    let (i, op) = lex(dataflow)(i)?;
    let (i, rhs) = lex(flow_term)(i)?;
    Ok((
        i,
        Line::Flow(FlowStmt {
            lhs: Some(lhs),
            op,
            rhs,
        }),
    ))
}

fn line(i: &str) -> IResult<&str, Line> {
    alt((assign, gate_line, flow_line))(i)
}

/// Parse a single physical line (already comment-stripped) into a [`Line`].
pub fn parse_line(src: &str) -> Result<Line, String> {
    let trimmed = src.trim();
    match all_consuming(delimited(multispace0, line, multispace0))(trimmed) {
        Ok((_, l)) => Ok(l),
        Err(e) => Err(format!("parse error in line {trimmed:?}: {e:?}")),
    }
}
