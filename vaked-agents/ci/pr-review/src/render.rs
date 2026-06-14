//! Rendering structured model output → the final markdown review.

use serde::Deserialize;

/// Render the model's raw output (JSON or prose) to the final markdown review,
/// returning (markdown, total_findings, blocking_findings). Falls back to raw
/// Coerce a finding's `line` from string, integer, float, or null into a String.
fn de_loc<'de, D: serde::Deserializer<'de>>(d: D) -> Result<String, D::Error> {
    #[derive(Deserialize)]
    #[serde(untagged)]
    enum Loc {
        S(String),
        I(i64),
        F(f64),
    }
    Ok(match Option::<Loc>::deserialize(d)? {
        Some(Loc::S(s)) => s,
        Some(Loc::I(i)) => i.to_string(),
        Some(Loc::F(f)) => f.to_string(),
        None => String::new(),
    })
}

/// text if JSON parsing fails, so a non-conforming provider never breaks posting.
#[derive(Deserialize, Default)]
pub(crate) struct Finding {
    #[serde(default)]
    pub(crate) severity: String,
    #[serde(default)]
    pub(crate) path: String,
    // Models emit `line` as a bare number (`"line": 414`) as often as a string;
    // accept either (or null) so the whole structured review still parses instead
    // of falling back to dumping raw JSON with a 0-findings count.
    #[serde(default, deserialize_with = "de_loc")]
    pub(crate) line: String,
    #[serde(default)]
    pub(crate) problem: String,
    #[serde(default)]
    pub(crate) fix: String,
    // Exact verbatim replacement text for the cited line(s) — used to post a
    // committable GitHub ```suggestion``` block for Nit/Minor mechanical fixes.
    // Empty when the model judged the finding not mechanically autofixable.
    #[serde(default)]
    pub(crate) suggestion: String,
    // Optional end of a multi-line suggestion range (≥ line); empty = single line.
    #[serde(default, deserialize_with = "de_loc")]
    pub(crate) end_line: String,
    // Exact verbatim CURRENT text of the cited line(s) that `suggestion` replaces.
    // A committable ```suggestion``` is posted ONLY when this byte-matches the file
    // at [line, end_line] — so a drifted anchor can never replace the wrong lines
    // (the failure mode that corrupted code when suggestions were applied blind).
    #[serde(default)]
    pub(crate) original: String,
}

#[derive(Deserialize, Default)]
pub(crate) struct StructuredReview {
    #[serde(default)]
    pub(crate) verdict: String,
    #[serde(default)]
    pub(crate) prose: String,
    #[serde(default)]
    pub(crate) findings: Vec<Finding>,
    #[serde(default)]
    pub(crate) exceptions: Vec<String>,
}

/// Parse the model's raw output into a StructuredReview, or None if it isn't
/// structured JSON (same acceptance check `render_review` uses). Lets the summary
/// renderer and the inline-suggestion path share one parse without diverging.
pub(crate) fn parse_structured(raw: &str) -> Option<StructuredReview> {
    let cleaned = strip_code_fences(raw.trim());
    serde_json::from_str::<StructuredReview>(cleaned)
        .ok()
        .filter(|r| !(r.verdict.is_empty() && r.prose.is_empty() && r.findings.is_empty()))
}

pub(crate) fn render_review(raw: &str, max_findings: usize) -> (String, usize, usize) {
    if let Some(r) = parse_structured(raw) {
        let verdict = r.verdict.trim();
        let total = r.findings.len();
        let blocking = r
            .findings
            .iter()
            .filter(|f| f.severity == "Blocking")
            .count();

        let prose = r.prose.trim();
        let mut body = if prose.is_empty() {
            let head = if verdict.is_empty() {
                "see findings"
            } else {
                verdict
            };
            format!(
                "**Verdict:** {head}\n{}",
                render_findings(&r.findings, max_findings)
            )
        } else if prose.starts_with("**Verdict:") || verdict.is_empty() {
            prose.to_string()
        } else {
            format!("**Verdict:** {verdict}\n\n{prose}")
        };

        let notes: Vec<&str> = r
            .exceptions
            .iter()
            .map(|s| s.trim())
            .filter(|s| !s.is_empty())
            .collect();
        if !notes.is_empty() {
            body.push_str("\n\n### Notes\n");
            for e in notes {
                body.push_str(&format!("- {e}\n"));
            }
        }
        return (body.trim().to_string(), total, blocking);
    }

    let (total, blocking) = count_findings(raw);
    (raw.trim().to_string(), total, blocking)
}

fn render_findings(findings: &[Finding], max: usize) -> String {
    let mut out = String::new();
    for sev in ["Blocking", "Major", "Minor", "Nit"] {
        let group: Vec<&Finding> = findings.iter().filter(|f| f.severity == sev).collect();
        if group.is_empty() {
            continue;
        }
        out.push_str(&format!("\n### {sev}\n"));
        for f in group.into_iter().take(max) {
            let path = if f.path.is_empty() { "?" } else { &f.path };
            let line = if f.line.is_empty() { "?" } else { &f.line };
            out.push_str(&format!(
                "- `{path}:{line}` — {}; {}\n",
                f.problem.trim(),
                f.fix.trim()
            ));
        }
    }
    out
}

fn strip_code_fences(s: &str) -> &str {
    let s = s.trim();
    if let Some(rest) = s.strip_prefix("```json").or_else(|| s.strip_prefix("```")) {
        return rest.trim_end_matches("```").trim();
    }
    s
}

fn count_findings(review: &str) -> (usize, usize) {
    let (mut total, mut blocking) = (0usize, 0usize);
    let mut in_blocking = false;
    for line in review.lines() {
        let t = line.trim_start();
        if let Some(h) = t.strip_prefix("### ") {
            in_blocking = h.trim().eq_ignore_ascii_case("blocking");
        } else if t.starts_with("- `") {
            total += 1;
            if in_blocking {
                blocking += 1;
            }
        }
    }
    (total, blocking)
}

#[cfg(test)]
mod render_tests {
    use super::*;

    #[test]
    fn numeric_line_still_parses_and_renders() {
        // Model emits `line` as a bare number — must render markdown + count the
        // finding, not fall back to dumping raw JSON with 0 findings.
        let raw = r#"{"verdict":"Issues.","prose":"","findings":[{"severity":"Minor","path":"a.rs","line":414,"problem":"x","fix":"y"}],"exceptions":[]}"#;
        let (body, total, blocking) = render_review(raw, 20);
        assert_eq!(total, 1);
        assert_eq!(blocking, 0);
        assert!(!body.trim_start().starts_with('{'), "rendered, not raw JSON");
        assert!(body.contains("`a.rs:414`"), "coerced numeric line: {body}");
    }

    #[test]
    fn narration_preamble_is_not_structured() {
        // The live failure mode: the model narrates tool intent instead of emitting
        // the structured JSON. parse_structured MUST return None so the review path
        // flags it degenerate (visible no-op) rather than posting the preamble.
        assert!(parse_structured("I'll start by reading the files to understand the changes.").is_none());
        assert!(parse_structured("Let me read the diff first.").is_none());
        // A genuine structured review still parses.
        let real = r#"{"verdict":"No blocking issues.","prose":"Looks fine.","findings":[],"exceptions":[]}"#;
        assert!(parse_structured(real).is_some());
    }
}
