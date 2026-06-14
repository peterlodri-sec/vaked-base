//! `gh` / `git` helpers + PR/issue metadata, diffs, and recent-commit gathering.

use std::process::Command as StdCommand;

use anyhow::{Context, Result, anyhow};
use serde_json::Value;

use crate::config::Config;
use crate::consts::MAX_DIFF_CHARS;

fn gh(args: &[&str]) -> Result<String> {
    let out = StdCommand::new("gh")
        .args(args)
        .output()
        .with_context(|| format!("running `gh {}`", args.join(" ")))?;
    if !out.status.success() {
        return Err(anyhow!(
            "`gh {}` failed: {}",
            args.join(" "),
            String::from_utf8_lossy(&out.stderr).trim()
        ));
    }
    Ok(String::from_utf8_lossy(&out.stdout).into_owned())
}

fn git(args: &[&str]) -> Result<String> {
    let out = StdCommand::new("git")
        .args(args)
        .output()
        .with_context(|| format!("running `git {}`", args.join(" ")))?;
    if !out.status.success() {
        return Err(anyhow!("`git {}` failed", args.join(" ")));
    }
    Ok(String::from_utf8_lossy(&out.stdout).into_owned())
}

pub(crate) struct PrMeta {
    pub(crate) number: u64,
    pub(crate) title: String,
    pub(crate) body: String,
    pub(crate) files: Vec<String>,
    pub(crate) labels: Vec<String>,
}

pub(crate) fn fetch_pr_meta(cfg: &Config, pr: u64) -> Result<PrMeta> {
    let pr_s = pr.to_string();
    let raw = gh(&["pr", "view", &pr_s, "--repo", &cfg.repo, "--json", "title,body,files,labels,number"])?;
    let v: Value = serde_json::from_str(&raw).context("parsing gh pr view JSON")?;
    let files = v["files"].as_array().map(|a| {
        a.iter().filter_map(|f| f["path"].as_str().map(String::from)).collect()
    }).unwrap_or_default();
    let labels = v["labels"].as_array().map(|a| {
        a.iter().filter_map(|l| l["name"].as_str().map(String::from)).collect()
    }).unwrap_or_default();
    Ok(PrMeta {
        number: v["number"].as_u64().unwrap_or(pr),
        title: v["title"].as_str().unwrap_or_default().to_string(),
        body: v["body"].as_str().unwrap_or_default().to_string(),
        files,
        labels,
    })
}

pub(crate) struct IssueMeta {
    pub(crate) number: u64,
    pub(crate) title: String,
    pub(crate) body: String,
    pub(crate) labels: Vec<String>,
}

pub(crate) fn fetch_issue_meta(cfg: &Config, issue: u64) -> Result<IssueMeta> {
    let issue_s = issue.to_string();
    let raw = gh(&["issue", "view", &issue_s, "--repo", &cfg.repo, "--json", "title,body,labels,number"])?;
    let v: Value = serde_json::from_str(&raw).context("parsing gh issue view JSON")?;
    let labels = v["labels"].as_array().map(|a| {
        a.iter().filter_map(|l| l["name"].as_str().map(String::from)).collect()
    }).unwrap_or_default();
    Ok(IssueMeta {
        number: v["number"].as_u64().unwrap_or(issue),
        title: v["title"].as_str().unwrap_or_default().to_string(),
        body: v["body"].as_str().unwrap_or_default().to_string(),
        labels,
    })
}

pub(crate) fn fetch_pr_diff(cfg: &Config, pr: u64) -> String {
    // Try git diff over base..head first (fast, no network), fall back to gh.
    if let (Some(base), Some(head)) = (&cfg.base_sha, &cfg.head_sha) {
        if let Ok(d) = git(&["diff", &format!("{base}..{head}")]) {
            if !d.trim().is_empty() {
                return chunk_diff(&d, MAX_DIFF_CHARS);
            }
        }
    }
    let pr_s = pr.to_string();
    let d = gh(&["pr", "diff", &pr_s, "--repo", &cfg.repo]).unwrap_or_default();
    chunk_diff(&d, MAX_DIFF_CHARS)
}

fn score_file(path: &str) -> u8 {
    if path.ends_with(".lock") { return 0; }
    let top = path.split('/').next().unwrap_or(path);
    match top {
        "vaked" | "vakedc" | "vakedz" | "protocol" | "vaked-agents"
        | "daemons" | "agent_guardd" | "eventd" => 5,
        ".github" | "tools" => 4,
        _ if path.ends_with(".md") || path.ends_with(".txt") => 2,
        _ => 3,
    }
}

fn extract_diff_path(section: &str) -> &str {
    section
        .lines()
        .next()
        .and_then(|l| l.strip_prefix("diff --git a/"))
        .map(|rest| rest.split_once(' ').map_or(rest, |(a, _)| a))
        .unwrap_or("?")
}

fn chunk_diff(diff: &str, max_chars: usize) -> String {
    if diff.len() <= max_chars {
        return diff.to_string();
    }
    let marker = "\ndiff --git ";
    let mut sections: Vec<&str> = Vec::new();
    let mut start = 0;
    let mut search = if diff.starts_with("diff --git ") { "diff --git ".len() } else { 0 };
    while let Some(rel) = diff[search..].find(marker) {
        let abs = search + rel;
        sections.push(&diff[start..abs]);
        start = abs + 1;
        search = start + marker.len() - 1;
    }
    sections.push(&diff[start..]);

    let mut scored: Vec<(u8, &str)> = sections.iter()
        .map(|&s| (score_file(extract_diff_path(s)), s))
        .collect();
    scored.sort_by(|a, b| b.0.cmp(&a.0));

    let footer_reserve: usize = 300;
    let budget = max_chars.saturating_sub(footer_reserve);
    let mut out = String::with_capacity(max_chars);
    let mut omitted: Vec<&str> = Vec::new();

    for (_, chunk) in &scored {
        let sep = usize::from(!out.is_empty());
        if out.len() + sep + chunk.len() <= budget {
            if !out.is_empty() { out.push('\n'); }
            out.push_str(chunk);
        } else {
            omitted.push(extract_diff_path(chunk));
        }
    }
    if !omitted.is_empty() {
        use std::fmt::Write as _;
        let _ = write!(out, "\n\n[{} file(s) omitted: {}]", omitted.len(), omitted.join(", "));
    }
    out
}

pub(crate) async fn fetch_commits_since_tag(repo: &str) -> String {
    // Get the latest semver tag, then list commits since it.
    let last_tag = git(&["describe", "--tags", "--abbrev=0", "--match", "v*"])
        .unwrap_or_else(|_| String::new());
    let last_tag = last_tag.trim().to_string();
    let range = if last_tag.is_empty() {
        "HEAD~20..HEAD".to_string()
    } else {
        format!("{last_tag}..HEAD")
    };

    // git log (local) and gh pr list (network) are independent — run concurrently.
    let range_clone = range.clone();
    let repo_owned = repo.to_string();
    let (log_res, prs_res) = tokio::join!(
        tokio::task::spawn_blocking(move || {
            git(&["log", "--oneline", "--no-merges", "--pretty=format:%h %s", &range_clone])
                .unwrap_or_default()
        }),
        tokio::task::spawn_blocking(move || {
            gh(&[
                "pr", "list", "--repo", &repo_owned, "--state", "merged", "--limit", "20",
                "--json", "number,title,labels,mergedAt",
            ])
            .unwrap_or_default()
        }),
    );
    let log = log_res.unwrap_or_default();
    let prs = prs_res.unwrap_or_default();
    format!("Last tag: {last_tag}\nCommits since tag:\n{log}\n\nRecently merged PRs:\n{prs}")
}

fn truncate(s: &str, max: usize) -> (&str, bool) {
    let chars: Vec<char> = s.chars().collect();
    if chars.len() <= max {
        (s, false)
    } else {
        let byte_pos = s.char_indices()
            .nth(max)
            .map(|(i, _)| i)
            .unwrap_or(s.len());
        (&s[..byte_pos], true)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn score_file_lockfile() {
        assert_eq!(score_file("Cargo.lock"), 0);
        assert_eq!(score_file("flake.lock"), 0);
    }

    #[test]
    fn score_file_vaked_is_highest() {
        assert_eq!(score_file("vaked/grammar/vaked.ebnf"), 5);
        assert_eq!(score_file("vaked-agents/ci/label-tagger/src/run.rs"), 5);
        assert!(score_file("vaked/src/lib.rs") > score_file("docs/website/index.html"));
    }

    #[test]
    fn extract_diff_path_roundtrip() {
        let section = "diff --git a/vaked/foo.rs b/vaked/foo.rs\n@@ -1 +1 @@\n-old\n+new";
        assert_eq!(extract_diff_path(section), "vaked/foo.rs");
    }

    #[test]
    fn chunk_diff_passthrough() {
        let diff = "diff --git a/foo.rs b/foo.rs\n+change";
        assert_eq!(chunk_diff(diff, 10_000), diff);
    }

    #[test]
    fn chunk_diff_drops_lockfile_first() {
        let lock = "diff --git a/Cargo.lock b/Cargo.lock\n".to_string() + &"x".repeat(5_000);
        let src = "diff --git a/vaked/src/lib.rs b/vaked/src/lib.rs\n".to_string() + &"y".repeat(5_000);
        let diff = format!("{lock}\n{src}");
        // Budget just enough for src but not both.
        let result = chunk_diff(&diff, 6_000);
        assert!(result.contains("vaked/src/lib.rs"), "high-score file must be included");
        assert!(result.contains("Cargo.lock") == false || result.contains("[1 file(s) omitted"),
            "lockfile must be omitted or noted");
    }

    #[test]
    fn chunk_diff_prioritises_vaked_over_docs() {
        let docs = "diff --git a/docs/website/index.html b/docs/website/index.html\n".to_string()
            + &"d".repeat(4_000);
        let src = "diff --git a/vaked/grammar/g.ebnf b/vaked/grammar/g.ebnf\n".to_string()
            + &"s".repeat(4_000);
        // docs comes first in the raw diff
        let diff = format!("{docs}\n{src}");
        let result = chunk_diff(&diff, 5_000);
        assert!(result.contains("vaked/grammar/g.ebnf"), "vaked file must survive");
    }

    #[test]
    fn truncate_clips_at_char_boundary() {
        let s = "hello world";
        let (clipped, truncated) = truncate(s, 5);
        assert_eq!(clipped, "hello");
        assert!(truncated);
        let (full, trunc2) = truncate(s, 100);
        assert_eq!(full, s);
        assert!(!trunc2);
    }
}
