//! Comment-cleanup subroutine (advisory; COMMENTS only, never issues).
//!
//! Sweeps bot "usage/rate-limit/quota" noise, then collapses duplicate bot
//! review/update comments to the most-recent-per-bot. Runs inline before each
//! review and on a schedule (cleanup.yml, `--cleanup` mode).

use std::collections::HashMap;

use anyhow::{Result, anyhow};
use tracing::{info, warn};

use crate::config::env_first;
use crate::consts::{AUTOFIX_MARKER, COMMENT_MARKER, REPLY_MARKER};
use crate::github::gh;

/// True when invoked as the cleanup subroutine (`--cleanup`).
pub(crate) fn cleanup_requested() -> bool {
    std::env::args().skip(1).any(|a| a == "--cleanup")
}

/// Case-insensitive substrings that mark a bot usage/rate-limit/quota notice — pure
/// noise deleted on sight (e.g. the Codex "you have reached your usage limits" comment).
const CLEANUP_NOISE_NEEDLES: &[&str] = &[
    "usage limit",
    "rate limit",
    "rate-limit",
    "quota",
    "reached your",
    "upgrade your account",
    "out of credits",
    "add credits",
];

/// Minimal view of a PR issue comment for the cleanup pass.
struct PrComment {
    id: u64,
    login: String,
    is_bot: bool,
    body: String,
}

/// Our own comments carry these markers and are managed by the review flow — the
/// cleanup pass must never touch them.
fn is_own_comment(body: &str) -> bool {
    body.contains(COMMENT_MARKER) || body.contains(REPLY_MARKER) || body.contains(AUTOFIX_MARKER)
}

fn is_noise_comment(body: &str) -> bool {
    let b = body.to_ascii_lowercase();
    CLEANUP_NOISE_NEEDLES.iter().any(|n| b.contains(n))
}

/// Fetch the PR's issue comments in chronological order (id, author, bot?, body head).
fn fetch_pr_comments(repo: &str, pr: u64) -> Result<Vec<PrComment>> {
    let endpoint = format!("repos/{repo}/issues/{pr}/comments");
    // One TSV row per comment; body flattened + clipped (enough to classify).
    let jq = r#".[] | [(.id|tostring), (.user.login // ""), (.user.type // ""), ((.body // "") | gsub("[\t\n\r]";" ") | .[0:600])] | @tsv"#;
    let out = gh(&["api", "--paginate", &endpoint, "--jq", jq])?;
    let mut v = Vec::new();
    for line in out.lines() {
        let mut it = line.splitn(4, '\t');
        let Some(id) = it.next().and_then(|s| s.trim().parse().ok()) else {
            continue;
        };
        let login = it.next().unwrap_or("").to_string();
        let is_bot = it.next() == Some("Bot");
        let body = it.next().unwrap_or("").to_string();
        v.push(PrComment {
            id,
            login,
            is_bot,
            body,
        });
    }
    Ok(v)
}

fn delete_comment(repo: &str, id: u64) -> Result<()> {
    gh(&[
        "api",
        "-X",
        "DELETE",
        &format!("repos/{repo}/issues/comments/{id}"),
    ])
    .map(|_| ())
}

/// Sweep one PR's comments: (1) delete bot usage/rate-limit/quota noise, then
/// (2) collapse duplicate bot review/update comments to the newest per author.
/// Returns `(noise_deleted, dupes_deleted)`. Advisory + idempotent; logs and
/// continues on any per-comment failure.
pub(crate) fn cleanup_pr_comments(repo: &str, pr: u64) -> (usize, usize) {
    // Logins never collapsed: our own surface posts as github-actions[bot] and other
    // workflows post distinct comments under it. Extend via PR_REVIEW_CLEANUP_KEEP.
    let mut keep: Vec<String> = vec!["github-actions[bot]".to_string()];
    if let Some(extra) = env_first(&["PR_REVIEW_CLEANUP_KEEP"]) {
        keep.extend(
            extra
                .split(',')
                .map(|s| s.trim().to_string())
                .filter(|s| !s.is_empty()),
        );
    }
    let kept = |login: &str| keep.iter().any(|k| k.eq_ignore_ascii_case(login));

    let comments = match fetch_pr_comments(repo, pr) {
        Ok(c) => c,
        Err(e) => {
            warn!(error = %e, "cleanup: could not list PR comments — skipping");
            return (0, 0);
        }
    };

    let mut noise = 0usize;
    // Pass 1 — delete bot noise; keep everything else as a dedupe candidate.
    let mut survivors: Vec<&PrComment> = Vec::new();
    for c in &comments {
        if c.is_bot && !is_own_comment(&c.body) && is_noise_comment(&c.body) {
            match delete_comment(repo, c.id) {
                Ok(()) => {
                    noise += 1;
                    info!(id = c.id, login = %c.login, "cleanup: deleted bot noise comment");
                }
                Err(e) => warn!(id = c.id, error = %e, "cleanup: noise delete failed"),
            }
        } else {
            survivors.push(c);
        }
    }

    // Pass 2 — collapse duplicates: for each eligible bot login keep only the newest
    // (comments are chronological, so the last index wins) and delete the rest.
    let eligible = |c: &PrComment| c.is_bot && !is_own_comment(&c.body) && !kept(&c.login);
    let mut newest: HashMap<&str, usize> = HashMap::new();
    for (i, c) in survivors.iter().enumerate() {
        if eligible(c) {
            newest.insert(c.login.as_str(), i);
        }
    }
    let mut dupes = 0usize;
    for (i, c) in survivors.iter().enumerate() {
        if eligible(c) && newest.get(c.login.as_str()) != Some(&i) {
            match delete_comment(repo, c.id) {
                Ok(()) => {
                    dupes += 1;
                    info!(id = c.id, login = %c.login, "cleanup: collapsed duplicate bot comment");
                }
                Err(e) => warn!(id = c.id, error = %e, "cleanup: dupe delete failed"),
            }
        }
    }
    (noise, dupes)
}

/// `--cleanup` entrypoint: sweep one PR (`--pr`) or every open PR (no `--pr`).
pub(crate) async fn run_cleanup() -> Result<()> {
    let mut repo = std::env::var("GITHUB_REPOSITORY").ok();
    let mut pr: Option<u64> = None;
    let mut args = std::env::args().skip(1);
    while let Some(a) = args.next() {
        match a.as_str() {
            "--repo" => repo = args.next(),
            "--pr" => pr = args.next().and_then(|v| v.parse().ok()),
            _ => {}
        }
    }
    let repo = repo.ok_or_else(|| anyhow!("cleanup: no repo — pass --repo or set GITHUB_REPOSITORY"))?;
    let prs: Vec<u64> = match pr {
        Some(n) => vec![n],
        None => {
            let out = gh(&[
                "pr", "list", "--repo", &repo, "--state", "open", "--limit", "100", "--json",
                "number", "-q", ".[].number",
            ])?;
            out.lines().filter_map(|l| l.trim().parse().ok()).collect()
        }
    };
    let (mut tn, mut td) = (0usize, 0usize);
    for pr in prs {
        let (n, d) = cleanup_pr_comments(&repo, pr);
        tn += n;
        td += d;
        if n + d > 0 {
            info!(pr, noise = n, dupes = d, "cleanup: swept PR");
        }
    }
    info!(total_noise = tn, total_dupes = td, "cleanup complete");
    Ok(())
}
