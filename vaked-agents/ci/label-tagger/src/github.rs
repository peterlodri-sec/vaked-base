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
        if let Ok(d) = git(&["diff", &format!("{base}...{head}")]) {
            if !d.trim().is_empty() {
                let (truncated, _) = truncate(&d, MAX_DIFF_CHARS);
                return truncated.to_string();
            }
        }
    }
    let pr_s = pr.to_string();
    let d = gh(&["pr", "diff", &pr_s, "--repo", &cfg.repo]).unwrap_or_default();
    let (truncated, _) = truncate(&d, MAX_DIFF_CHARS);
    truncated.to_string()
}

pub(crate) fn fetch_commits_since_tag(repo: &str) -> String {
    // Get the latest semver tag, then list commits since it.
    let last_tag = git(&["describe", "--tags", "--abbrev=0", "--match", "v*"])
        .unwrap_or_else(|_| String::new());
    let last_tag = last_tag.trim().to_string();
    let range = if last_tag.is_empty() {
        "HEAD~20..HEAD".to_string()
    } else {
        format!("{last_tag}..HEAD")
    };
    let log = git(&[
        "log", "--oneline", "--no-merges", "--pretty=format:%h %s", &range,
    ]).unwrap_or_default();
    // Also try to pull merged PR numbers from recent merge commits
    let prs = gh(&[
        "pr", "list", "--repo", repo, "--state", "merged", "--limit", "20",
        "--json", "number,title,labels,mergedAt",
    ]).unwrap_or_default();
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
