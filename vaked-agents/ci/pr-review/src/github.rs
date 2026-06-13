//! `gh` CLI / `git` wrappers, PR metadata + diff fetching, and comment posting.

use std::process::Command as StdCommand;

use anyhow::{Context, Result, anyhow};
use tracing::{info, warn};

use crate::config::Config;
use crate::consts::COMMENT_MARKER;

pub(crate) fn gh(args: &[&str]) -> Result<String> {
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

pub(crate) fn fetch_pr_meta(cfg: &Config) -> Result<PrMeta> {
    let pr = cfg.pr.to_string();
    let raw = gh(&[
        "pr",
        "view",
        &pr,
        "--repo",
        &cfg.repo,
        "--json",
        "title,body,files,labels,number",
    ])?;
    let v: serde_json::Value = serde_json::from_str(&raw).context("parsing gh pr view JSON")?;
    let files = v["files"]
        .as_array()
        .map(|a| {
            a.iter()
                .filter_map(|f| f["path"].as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default();
    let labels = v["labels"]
        .as_array()
        .map(|a| {
            a.iter()
                .filter_map(|l| l["name"].as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default();
    Ok(PrMeta {
        number: v["number"].as_u64().unwrap_or(cfg.pr),
        title: v["title"].as_str().unwrap_or_default().to_string(),
        body: v["body"].as_str().unwrap_or_default().to_string(),
        files,
        labels,
    })
}

pub(crate) fn fetch_diff(cfg: &Config) -> Result<String> {
    if let (Some(base), Some(head)) = (&cfg.base_sha, &cfg.head_sha) {
        let range = format!("{base}...{head}");
        let mut args = vec!["diff".to_string(), range, "--".to_string(), ".".to_string()];
        args.extend(noise_pathspecs());
        let args: Vec<&str> = args.iter().map(String::as_str).collect();
        if let Ok(out) = git(&args)
            && !out.trim().is_empty()
        {
            return Ok(out);
        }
    }
    gh(&["pr", "diff", &cfg.pr.to_string(), "--repo", &cfg.repo])
}

pub(crate) fn rtk_condensed(cfg: &Config) -> Option<String> {
    if !cfg.use_rtk {
        return None;
    }
    let (base, head) = (cfg.base_sha.as_ref()?, cfg.head_sha.as_ref()?);
    let range = format!("{base}...{head}");
    let mut args = vec![
        "git".to_string(),
        "diff".to_string(),
        range,
        "--".to_string(),
        ".".to_string(),
    ];
    args.extend(noise_pathspecs());
    let args: Vec<&str> = args.iter().map(String::as_str).collect();
    let out = StdCommand::new(&cfg.rtk_bin).args(&args).output().ok()?;
    if out.status.success() {
        let s = String::from_utf8_lossy(&out.stdout).into_owned();
        if !s.trim().is_empty() {
            info!("diff via rtk (condensed)");
            return Some(s);
        }
    }
    None
}

fn noise_pathspecs() -> Vec<String> {
    [
        "Cargo.lock",
        "flake.lock",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "go.sum",
        "*.lock",
        "*.snap",
        "*.png",
        "*.jpg",
        "*.svg",
        "*.pdf",
        "vendor/**",
        "node_modules/**",
        "dist/**",
        "build/**",
        "target/**",
    ]
    .iter()
    .map(|p| format!(":(exclude){p}"))
    .collect()
}

/// Posts the review comment, returning the created comment's web URL (`gh pr comment`
/// prints it to stdout) so the caller can link it from the Langfuse trace.
pub(crate) fn post_review(cfg: &Config, body: &str) -> Result<Option<String>> {
    delete_prior_comments(cfg);
    let mut path = std::env::temp_dir();
    path.push(format!("vaked-pr-review-{}.md", cfg.pr));
    std::fs::write(&path, body).context("writing review body")?;
    let path_str = path.to_string_lossy().into_owned();
    let out = gh(&[
        "pr",
        "comment",
        &cfg.pr.to_string(),
        "--repo",
        &cfg.repo,
        "--body-file",
        &path_str,
    ])?;
    let _ = std::fs::remove_file(&path);
    // gh prints the new comment URL (last non-empty line) on success.
    let url = out
        .lines()
        .rev()
        .map(str::trim)
        .find(|l| l.starts_with("http"))
        .map(String::from);
    Ok(url)
}

fn delete_prior_comments(cfg: &Config) {
    let endpoint = format!("repos/{}/issues/{}/comments", cfg.repo, cfg.pr);
    let jq = format!(".[] | select(.body | contains(\"{COMMENT_MARKER}\")) | .id");
    let ids = match gh(&["api", "--paginate", &endpoint, "--jq", &jq]) {
        Ok(s) => s,
        Err(e) => {
            warn!(error = %e, "could not list prior comments — skipping dedupe");
            return;
        }
    };
    for id in ids.split_whitespace() {
        let del = format!("repos/{}/issues/comments/{}", cfg.repo, id);
        if let Err(e) = gh(&["api", "-X", "DELETE", &del]) {
            warn!(%id, error = %e, "failed to delete prior comment");
        }
    }
}

pub(crate) fn set_advisory_status(cfg: &Config, desc: &str) {
    let Some(sha) = &cfg.head_sha else { return };
    let endpoint = format!("repos/{}/statuses/{}", cfg.repo, sha);
    let desc = desc.chars().take(140).collect::<String>();
    if let Err(e) = gh(&[
        "api",
        "-X",
        "POST",
        &endpoint,
        "-f",
        "state=success",
        "-f",
        "context=vaked-pr-review",
        "-f",
        &format!("description={desc}"),
    ]) {
        warn!(error = %e, "could not set advisory status");
    }
}

/// Post an `@vaked-ci` reply comment (thread persists — not deduped/deleted).
pub(crate) fn post_reply(cfg: &Config, body: &str) -> Result<()> {
    let mut path = std::env::temp_dir();
    path.push(format!("vaked-ci-reply-{}.md", cfg.pr));
    std::fs::write(&path, body).context("writing reply body")?;
    let path_str = path.to_string_lossy().into_owned();
    let res = gh(&[
        "pr",
        "comment",
        &cfg.pr.to_string(),
        "--repo",
        &cfg.repo,
        "--body-file",
        &path_str,
    ]);
    let _ = std::fs::remove_file(&path);
    res.map(|_| ())
}
