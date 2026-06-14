//! Inline ```suggestion``` autofix comments + the per-run cost estimate.

use std::collections::HashMap;

use anyhow::{Context, Result};
use serde_json::{Value, json};
use tracing::warn;

use crate::config::Config;
use crate::consts::{AUTOFIX_MARKER, MAX_INLINE_SUGGESTIONS};
use crate::github::gh;
use crate::render::Finding;

/// A finding is autofixable iff it's Nit/Minor with a non-empty suggestion that
/// won't break the ```suggestion``` fence.
fn is_autofixable(f: &Finding) -> bool {
    matches!(f.severity.as_str(), "Minor" | "Nit")
        && !f.suggestion.trim().is_empty()
        && !f.suggestion.contains("```")
}

/// Findings eligible for an inline suggestion, in posting order (Minor before Nit),
/// filtered to lines actually present in the current diff, capped at `cap`.
fn select_suggestions<'a>(
    findings: &'a [Finding],
    right: &HashMap<String, std::collections::HashSet<u32>>,
    cap: usize,
) -> Vec<&'a Finding> {
    let mut out: Vec<&Finding> = Vec::new();
    for sev in ["Minor", "Nit"] {
        for f in findings.iter().filter(|f| f.severity == sev && is_autofixable(f)) {
            let Ok(line) = f.line.parse::<u32>() else { continue };
            if line == 0 {
                continue;
            }
            let Some(lines) = right.get(&f.path) else { continue };
            if !lines.contains(&line) {
                continue; // stale / off-diff
            }
            if let Ok(end) = f.end_line.parse::<u32>()
                && end > line
                && !(line..=end).all(|n| lines.contains(&n))
            {
                continue; // range not fully in-diff
            }
            out.push(f);
            if out.len() >= cap {
                return out;
            }
        }
    }
    out
}

/// True when `original` byte-matches the file's current content at the inclusive
/// 1-based range `[line, end_line]`. This is the anchor check that makes the
/// autofix safe: GitHub applies a ```suggestion``` as a literal span replacement,
/// so if the model's line number has drifted, replacing the wrong span corrupts
/// the file. Requiring the model to echo the exact bytes it intends to replace —
/// and verifying them against the file — means a drifted anchor simply fails to
/// match and the suggestion is never posted as committable. Empty `original`
/// never matches (fail-closed: no echo ⇒ no committable suggestion).
fn anchor_text_matches(file_text: &str, line: u32, end_line: u32, original: &str) -> bool {
    if original.trim().is_empty() || line == 0 || end_line < line {
        return false;
    }
    let lines: Vec<&str> = file_text.lines().collect();
    let (s, e) = (line as usize, end_line as usize);
    if e > lines.len() {
        return false; // anchor past EOF — stale/drifted
    }
    lines[s - 1..e].join("\n") == original.trim_end_matches('\n')
}

/// Read the cited file and verify the finding's `original` matches the anchored
/// lines. Fail-closed: any parse/read error ⇒ false (no committable suggestion).
/// Runs against the checked-out HEAD (the PR head the review is posted on).
fn verify_anchor(f: &Finding) -> bool {
    let Ok(line) = f.line.parse::<u32>() else {
        return false;
    };
    let end = f.end_line.parse::<u32>().ok().filter(|&e| e >= line).unwrap_or(line);
    match std::fs::read_to_string(&f.path) {
        Ok(text) => anchor_text_matches(&text, line, end, &f.original),
        Err(_) => false,
    }
}

/// One GitHub review-comment object carrying a ```suggestion``` block.
fn build_suggestion_comment(f: &Finding) -> Value {
    let body = format!(
        "{AUTOFIX_MARKER}\n{} — {}\n```suggestion\n{}\n```",
        f.problem.trim(),
        f.fix.trim(),
        f.suggestion
    );
    let line: u32 = f.line.parse().unwrap_or(0);
    match f.end_line.parse::<u32>().ok().filter(|&e| e > line) {
        Some(end) => json!({
            "path": f.path, "start_line": line, "start_side": "RIGHT",
            "line": end, "side": "RIGHT", "body": body
        }),
        None => json!({ "path": f.path, "line": line, "side": "RIGHT", "body": body }),
    }
}

fn build_review_payload(commit_id: &str, comments: Vec<Value>) -> Value {
    json!({
        "commit_id": commit_id,
        "event": "COMMENT",
        "body": format!("{AUTOFIX_MARKER} {} committable suggestion(s) from the vaked reviewer.", comments.len()),
        "comments": comments,
    })
}

/// Post a single review of inline ```suggestion``` comments for the autofixable
/// findings. Deletes our prior suggestions first (idempotent). Returns the count
/// posted. Never fails the run — the caller logs and continues on error.
pub(crate) fn post_inline_suggestions(
    cfg: &Config,
    findings: &[Finding],
    right: &HashMap<String, std::collections::HashSet<u32>>,
) -> Result<usize> {
    let Some(head) = cfg.head_sha.as_deref() else {
        warn!("no head SHA — skipping inline suggestions");
        return Ok(0);
    };
    delete_prior_suggestions(cfg);
    // In-diff selection, then the anchor gate: only keep suggestions whose echoed
    // `original` still matches the file, so a drifted anchor can't corrupt code.
    let picks: Vec<&Finding> = select_suggestions(findings, right, MAX_INLINE_SUGGESTIONS)
        .into_iter()
        .filter(|f| verify_anchor(f))
        .collect();
    if picks.is_empty() {
        return Ok(0);
    }
    let comments: Vec<Value> = picks.iter().map(|f| build_suggestion_comment(f)).collect();
    let n = comments.len();
    let payload = build_review_payload(head, comments);
    let mut path = std::env::temp_dir();
    path.push(format!("vaked-pr-suggest-{}.json", cfg.pr));
    std::fs::write(&path, serde_json::to_vec(&payload)?).context("writing suggestions payload")?;
    let path_str = path.to_string_lossy().into_owned();
    let res = gh(&[
        "api",
        "-X",
        "POST",
        &format!("repos/{}/pulls/{}/reviews", cfg.repo, cfg.pr),
        "--input",
        &path_str,
    ]);
    let _ = std::fs::remove_file(&path);
    res?;
    Ok(n)
}

/// Delete our prior inline suggestion comments (review-comments endpoint — distinct
/// from the issue-comments endpoint `delete_prior_comments` uses for the summary).
fn delete_prior_suggestions(cfg: &Config) {
    let endpoint = format!("repos/{}/pulls/{}/comments", cfg.repo, cfg.pr);
    let jq = format!(".[] | select(.body | contains(\"{AUTOFIX_MARKER}\")) | .id");
    let ids = match gh(&["api", "--paginate", &endpoint, "--jq", &jq]) {
        Ok(s) => s,
        Err(e) => {
            warn!(error = %e, "could not list prior suggestion comments — skipping dedupe");
            return;
        }
    };
    for id in ids.split_whitespace() {
        let del = format!("repos/{}/pulls/comments/{}", cfg.repo, id);
        if let Err(e) = gh(&["api", "-X", "DELETE", &del]) {
            warn!(%id, error = %e, "failed to delete prior suggestion comment");
        }
    }
}

pub(crate) fn print_dry_run_suggestions(
    findings: &[Finding],
    right: &HashMap<String, std::collections::HashSet<u32>>,
) {
    let picks = select_suggestions(findings, right, MAX_INLINE_SUGGESTIONS);
    println!("===== DRY RUN: {} inline suggestion(s) =====", picks.len());
    for f in picks {
        let end = if f.end_line.trim().is_empty() {
            String::new()
        } else {
            format!("-{}", f.end_line)
        };
        let anchor = if verify_anchor(f) { "anchor OK" } else { "anchor MISMATCH → dropped when posting" };
        println!("[{}] {}:{}{} ({anchor})\n```suggestion\n{}\n```", f.severity, f.path, f.line, end, f.suggestion);
    }
}

/// Rough USD estimate for a run from a blended $/million-token rate.
pub(crate) fn estimate_cost_usd(total_tokens: i64, usd_per_mtok: f64) -> f64 {
    (total_tokens.max(0) as f64 / 1_000_000.0) * usd_per_mtok
}

#[cfg(test)]
mod suggestion_tests {
    use super::*;
    use crate::consts::AUTOFIX_MARKER;
    use crate::diff::diff_right_lines;
    use crate::render::Finding;

    fn f(sev: &str, path: &str, line: &str, sugg: &str) -> Finding {
        Finding {
            severity: sev.into(),
            path: path.into(),
            line: line.into(),
            problem: "p".into(),
            fix: "do x".into(),
            suggestion: sugg.into(),
            end_line: String::new(),
            original: String::new(),
        }
    }

    const DIFF: &str = "diff --git a/src/x.rs b/src/x.rs\n--- a/src/x.rs\n+++ b/src/x.rs\n@@ -1,2 +1,3 @@\n unchanged\n-old line\n+new line 2\n+new line 3\n";

    #[test]
    fn right_lines_maps_added_and_context_only() {
        let m = diff_right_lines(DIFF);
        let s = m.get("src/x.rs").expect("file keyed by +++ b/ path");
        // new-file lines: 1 (context), 2 (+), 3 (+). Deleted line never advances.
        assert!(s.contains(&1) && s.contains(&2) && s.contains(&3));
        assert!(!s.contains(&4));
    }

    #[test]
    fn selects_only_nit_minor_in_diff_with_suggestion() {
        let right = diff_right_lines(DIFF);
        let findings = vec![
            f("Blocking", "src/x.rs", "2", "x"),      // wrong severity
            f("Minor", "src/x.rs", "2", "fixed 2"),   // ok
            f("Nit", "src/x.rs", "3", "fixed 3"),     // ok
            f("Minor", "src/x.rs", "9", "off-diff"),  // line not in diff -> stale
            f("Minor", "src/x.rs", "3", ""),          // empty suggestion
            f("Nit", "other.rs", "1", "no such file"), // path not in diff
        ];
        let picks = select_suggestions(&findings, &right, 10);
        // Minor before Nit; only the two in-diff ones with suggestions.
        assert_eq!(picks.len(), 2);
        assert_eq!(picks[0].line, "2"); // Minor first
        assert_eq!(picks[1].line, "3"); // then Nit
    }

    #[test]
    fn comment_payload_shapes() {
        let single = build_suggestion_comment(&f("Minor", "src/x.rs", "2", "new line 2"));
        assert_eq!(single["line"], 2);
        assert_eq!(single["side"], "RIGHT");
        assert!(single.get("start_line").is_none());
        assert!(single["body"].as_str().unwrap().contains("```suggestion"));
        assert!(single["body"].as_str().unwrap().contains(AUTOFIX_MARKER));

        let mut multi = f("Minor", "src/x.rs", "2", "two\nlines");
        multi.end_line = "3".into();
        let c = build_suggestion_comment(&multi);
        assert_eq!(c["start_line"], 2);
        assert_eq!(c["line"], 3);
        assert_eq!(c["start_side"], "RIGHT");

        let review = build_review_payload("deadbeef", vec![single]);
        assert_eq!(review["commit_id"], "deadbeef");
        assert_eq!(review["event"], "COMMENT");
        assert_eq!(review["comments"].as_array().unwrap().len(), 1);
    }

    #[test]
    fn fence_breaking_suggestion_is_skipped() {
        let right = diff_right_lines(DIFF);
        let bad = vec![f("Nit", "src/x.rs", "2", "has ``` fence")];
        assert!(select_suggestions(&bad, &right, 10).is_empty());
    }

    #[test]
    fn cost_estimate() {
        // 2_000_000 tokens at $0.5/Mtok = $1.00
        assert!((estimate_cost_usd(2_000_000, 0.5) - 1.0).abs() < 1e-9);
        assert_eq!(estimate_cost_usd(0, 0.5), 0.0);
    }

    #[test]
    fn anchor_match_gates_committable_suggestions() {
        let file = "alpha\nbeta\ngamma\n";
        // Exact single-line and range echoes match → safe to commit.
        assert!(anchor_text_matches(file, 2, 2, "beta"));
        assert!(anchor_text_matches(file, 2, 3, "beta\ngamma"));
        assert!(anchor_text_matches(file, 2, 3, "beta\ngamma\n")); // trailing NL tolerated
        // A drifted anchor: the echoed `original` no longer matches the line → dropped.
        assert!(!anchor_text_matches(file, 2, 2, "gamma"));
        // No echo at all → never committable (fail-closed, the old corrupting path).
        assert!(!anchor_text_matches(file, 2, 2, ""));
        // Out-of-range / inverted ranges are rejected.
        assert!(!anchor_text_matches(file, 9, 9, "beta"));
        assert!(!anchor_text_matches(file, 0, 0, "alpha"));
        assert!(!anchor_text_matches(file, 3, 2, "beta"));
    }

    #[test]
    fn verify_anchor_reads_real_file() {
        // Write a temp file and point a finding's path at it; verify_anchor reads
        // it relative to CWD, so use an absolute path via a temp dir.
        let dir = std::env::temp_dir().join(format!("vaked-anchor-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let path = dir.join("sample.txt");
        std::fs::write(&path, "one\ntwo\nthree\n").unwrap();
        let p = path.to_string_lossy().into_owned();

        let mut good = f("Nit", &p, "2", "TWO");
        good.original = "two".into();
        assert!(verify_anchor(&good), "matching original should verify");

        let mut drifted = f("Nit", &p, "2", "TWO");
        drifted.original = "three".into(); // wrong line content
        assert!(!verify_anchor(&drifted), "mismatched original must be rejected");

        let no_echo = f("Nit", &p, "2", "TWO"); // original empty
        assert!(!verify_anchor(&no_echo), "absent original must be rejected");

        let missing = {
            let mut m = f("Nit", "no/such/file.txt", "1", "X");
            m.original = "anything".into();
            m
        };
        assert!(!verify_anchor(&missing), "unreadable file fails closed");

        let _ = std::fs::remove_dir_all(&dir);
    }
}
