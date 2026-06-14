//! Runtime configuration (env + CLI args) and small env/arg helpers.

use anyhow::{Result, anyhow};

use crate::consts::*;

pub(crate) struct Config {
    pub(crate) repo: String,
    pub(crate) pr: u64,
    pub(crate) model: String,
    pub(crate) base_url: String,
    pub(crate) api_key: Option<String>,
    pub(crate) max_diff_chars: usize,
    pub(crate) dry_run: bool,
    pub(crate) rtk_bin: String,
    pub(crate) use_rtk: bool,
    pub(crate) base_sha: Option<String>,
    pub(crate) head_sha: Option<String>,
    pub(crate) reasoning_effort: String,
    pub(crate) mapreduce_lines: usize,
    pub(crate) max_findings: u32,
    pub(crate) crabcc_budget: u32,
    pub(crate) max_iters: u32,
    pub(crate) concurrency: usize,
    pub(crate) structured: bool,
    pub(crate) trace_payloads: bool,
    pub(crate) parallel_agent: bool,
    pub(crate) autofix: bool,
    pub(crate) usd_per_mtok: f64,
    pub(crate) provenance: bool,
    pub(crate) cleanup: bool,
}

impl Config {
    pub(crate) fn from_env_and_args() -> Result<Self> {
        let mut repo = std::env::var("GITHUB_REPOSITORY").ok();
        let mut pr: Option<u64> = None;
        let mut model =
            env_first(&["PR_REVIEW_MODEL"]).unwrap_or_else(|| DEFAULT_MODEL.to_string());
        let mut dry_run = false;

        let mut args = std::env::args().skip(1);
        while let Some(a) = args.next() {
            match a.as_str() {
                "--repo" => repo = args.next(),
                "--pr" => pr = args.next().and_then(|v| v.parse().ok()),
                "--model" => {
                    if let Some(v) = args.next() {
                        model = v;
                    }
                }
                "--dry-run" => dry_run = true,
                "--respond" => {} // interactive-responder mode (dispatched in main)
                "--eval" => {
                    let _ = args.next();
                }
                other => return Err(anyhow!("unknown arg: {other}")),
            }
        }

        let pr = match pr {
            Some(n) => n,
            None => detect_pr_number().ok_or_else(|| {
                anyhow!("no PR number — pass --pr or run in a pull_request event")
            })?,
        };
        let repo = repo.ok_or_else(|| anyhow!("no repo — pass --repo or set GITHUB_REPOSITORY"))?;

        Ok(Self {
            repo,
            pr,
            model,
            base_url: env_first(&["OPENROUTER_BASE_URL"])
                .unwrap_or_else(|| DEFAULT_BASE_URL.to_string()),
            api_key: env_first(&["PR_REVIEW_API_KEY", "OPENROUTER_API_KEY"]),
            max_diff_chars: env_usize("PR_REVIEW_MAX_DIFF_CHARS", DEFAULT_MAX_DIFF_CHARS),
            dry_run,
            rtk_bin: env_first(&["RTK_BIN"]).unwrap_or_else(|| "rtk".to_string()),
            use_rtk: std::env::var("PR_REVIEW_NO_RTK").is_err(),
            base_sha: env_first(&["BASE_SHA"]),
            head_sha: env_first(&["HEAD_SHA"]),
            reasoning_effort: env_first(&["PR_REVIEW_REASONING_EFFORT"])
                .unwrap_or_else(|| DEFAULT_REASONING_EFFORT.to_string()),
            mapreduce_lines: env_usize("PR_REVIEW_MAPREDUCE_LINES", DEFAULT_MAPREDUCE_LINES),
            max_findings: env_usize("PR_REVIEW_MAX_FINDINGS", DEFAULT_MAX_FINDINGS as usize) as u32,
            crabcc_budget: env_usize("PR_REVIEW_CRABCC_BUDGET", DEFAULT_CRABCC_BUDGET as usize)
                as u32,
            max_iters: env_usize("PR_REVIEW_MAX_ITERS", DEFAULT_MAX_ITERS as usize) as u32,
            concurrency: env_usize("PR_REVIEW_CONCURRENCY", DEFAULT_CONCURRENCY).max(1),
            structured: std::env::var("PR_REVIEW_NO_STRUCTURED").is_err(),
            trace_payloads: std::env::var("PR_REVIEW_TRACE_PAYLOADS").is_ok(),
            parallel_agent: std::env::var("PR_REVIEW_PARALLEL_AGENT").is_ok(),
            autofix: std::env::var("PR_REVIEW_NO_AUTOFIX").is_err(),
            usd_per_mtok: std::env::var("PR_REVIEW_USD_PER_MTOK")
                .ok()
                .and_then(|v| v.parse().ok())
                .unwrap_or(DEFAULT_USD_PER_MTOK),
            provenance: std::env::var("PR_REVIEW_NO_PROVENANCE").is_err(),
            cleanup: std::env::var("PR_REVIEW_NO_CLEANUP").is_err(),
        })
    }

    pub(crate) fn eval_defaults() -> Self {
        Self {
            repo: String::new(),
            pr: 0,
            model: env_first(&["PR_REVIEW_MODEL"]).unwrap_or_else(|| DEFAULT_MODEL.to_string()),
            base_url: env_first(&["OPENROUTER_BASE_URL"])
                .unwrap_or_else(|| DEFAULT_BASE_URL.to_string()),
            api_key: env_first(&["PR_REVIEW_API_KEY", "OPENROUTER_API_KEY"]),
            max_diff_chars: env_usize("PR_REVIEW_MAX_DIFF_CHARS", DEFAULT_MAX_DIFF_CHARS),
            dry_run: true,
            rtk_bin: "rtk".to_string(),
            use_rtk: false,
            base_sha: None,
            head_sha: None,
            reasoning_effort: env_first(&["PR_REVIEW_REASONING_EFFORT"])
                .unwrap_or_else(|| DEFAULT_REASONING_EFFORT.to_string()),
            mapreduce_lines: DEFAULT_MAPREDUCE_LINES,
            max_findings: DEFAULT_MAX_FINDINGS,
            crabcc_budget: DEFAULT_CRABCC_BUDGET,
            max_iters: DEFAULT_MAX_ITERS,
            concurrency: DEFAULT_CONCURRENCY,
            structured: std::env::var("PR_REVIEW_NO_STRUCTURED").is_err(),
            trace_payloads: false,
            parallel_agent: false,
            autofix: false,
            usd_per_mtok: DEFAULT_USD_PER_MTOK,
            provenance: false,
            cleanup: false,
        }
    }
}

pub(crate) fn env_first(keys: &[&str]) -> Option<String> {
    keys.iter()
        .find_map(|k| std::env::var(k).ok().filter(|v| !v.is_empty()))
}

pub(crate) fn env_usize(key: &str, default: usize) -> usize {
    std::env::var(key)
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(default)
}

pub(crate) fn detect_pr_number() -> Option<u64> {
    if let Ok(path) = std::env::var("GITHUB_EVENT_PATH")
        && let Ok(raw) = std::fs::read_to_string(&path)
        && let Ok(v) = serde_json::from_str::<serde_json::Value>(&raw)
    {
        if let Some(n) = v["pull_request"]["number"].as_u64() {
            return Some(n);
        }
        if let Some(n) = v["number"].as_u64() {
            return Some(n);
        }
    }
    let r = std::env::var("GITHUB_REF").ok()?;
    r.strip_prefix("refs/pull/")?
        .split('/')
        .next()?
        .parse()
        .ok()
}

pub(crate) fn truncate(s: &str, max: usize) -> (String, bool) {
    if s.len() <= max {
        return (s.to_string(), false);
    }
    let cut = s[..max].rfind('\n').unwrap_or(max);
    (s[..cut].to_string(), true)
}
