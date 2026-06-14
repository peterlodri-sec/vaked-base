//! AI-lish V1 — a lowerable agent execution-graph protocol.
//!
//! This crate implements the runtime side of the AI-lish V1 RFC:
//!
//! * [`parse_message`] — a `nom`-based parser (Phase B) turning V1 text into a
//!   typed [`Message`] AST.
//! * [`guardrail::check`] — the register-monad guardrail (Phase B, RFC §3),
//!   including the freeze invariant on live `gate(*:fail)` before `R:commit`.
//! * [`fmt::render`] / [`fmt::format_message`] — the idempotent `ailishfmt`
//!   formatter and the §5 long/compact token-compaction map (Phase C).
//!
//! Framing (splitting a message into register frames and stripping `#`
//! comments) lives here; the line grammar lives in [`parser`].

pub mod ast;
pub mod fmt;
pub mod guardrail;
pub mod parser;

pub use ast::*;
pub use fmt::{count_tokens, format_message, render};
pub use guardrail::{check as guardrail_check, GuardrailReport, Violation};

use parser::parse_line;

/// The canonical RFC §4 V1 example (SSA graph). Reused by the token benchmark
/// and the test-suite as the golden valid frame.
pub const EXAMPLE_V1: &str = r#"[R:bench]  %0 = fetch(pr=205, scope="scalars")
           %1 = test(target=%0) ; pass=61
           %2 = build(target=%0, kind="rust") ; duration_s=22
           %3 = combine(%1, %2)
           gate(ci:pass) ∵ %3
[R:risk]   %4 = check_permission(verb="merge", tool=`gh`) ; state="classifier_blocked"
           gate(commit:fail) ∵ %4
[R:plan]   depend(%3, %4) → target(user_action="paste_merge_cmd")
           %5 = launch_agent(scope="aggregates", base=%0)
[R:commit] %6 = merge(pr=205) ∵ %3        # frozen while gate(commit:fail) live
"#;

/// Strip a trailing `#` comment, respecting `"…"` and `` `…` `` literals.
fn strip_comment(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let mut in_quote = false;
    let mut in_backtick = false;
    for c in s.chars() {
        match c {
            '"' if !in_backtick => {
                in_quote = !in_quote;
                out.push(c);
            }
            '`' if !in_quote => {
                in_backtick = !in_backtick;
                out.push(c);
            }
            '#' if !in_quote && !in_backtick => break,
            _ => out.push(c),
        }
    }
    out
}

/// If `trimmed` opens with a `[register]` header, return the parsed register and
/// the remainder of the line (which may hold the frame's first line).
fn parse_header(trimmed: &str) -> Result<Option<(Register, &str)>, String> {
    if !trimmed.starts_with('[') {
        return Ok(None);
    }
    let end = trimmed
        .find(']')
        .ok_or_else(|| format!("unterminated register header: {trimmed:?}"))?;
    let token = trimmed[1..end].trim();
    let reg = Register::from_token(token).ok_or_else(|| format!("unknown register: {token:?}"))?;
    Ok(Some((reg, &trimmed[end + 1..])))
}

/// Parse a full V1 message into a typed [`Message`].
pub fn parse_message(src: &str) -> Result<Message, String> {
    let mut frames: Vec<Frame> = Vec::new();
    let mut current: Option<Frame> = None;

    for raw in src.lines() {
        let stripped = strip_comment(raw);
        let trimmed = stripped.trim();
        if trimmed.is_empty() {
            continue;
        }
        match parse_header(trimmed)? {
            Some((reg, remainder)) => {
                if let Some(f) = current.take() {
                    frames.push(f);
                }
                let mut frame = Frame {
                    register: reg,
                    lines: Vec::new(),
                };
                let rem = remainder.trim();
                if !rem.is_empty() {
                    frame.lines.push(parse_line(rem)?);
                }
                current = Some(frame);
            }
            None => match current.as_mut() {
                Some(f) => f.lines.push(parse_line(trimmed)?),
                None => return Err(format!("line outside any frame: {trimmed:?}")),
            },
        }
    }

    if let Some(f) = current.take() {
        frames.push(f);
    }
    if frames.is_empty() {
        return Err("empty message: no frames".to_string());
    }
    Ok(Message { frames })
}
