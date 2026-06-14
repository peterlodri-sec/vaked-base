//! Runtime configuration (env vars).

use anyhow::Result;

use crate::consts::{DEFAULT_BASE_URL, DEFAULT_MAX_ITERS, DEFAULT_MODEL};

#[derive(Debug, PartialEq, Clone)]
pub(crate) enum Mode {
    Label,
    Changelog,
    MilestoneSync,
    All,
}

impl Mode {
    pub(crate) fn from_str(s: &str) -> Self {
        match s.to_ascii_lowercase().trim() {
            "changelog" => Mode::Changelog,
            "milestone-sync" | "milestone_sync" => Mode::MilestoneSync,
            "all" => Mode::All,
            _ => Mode::Label,
        }
    }
}

pub(crate) struct Config {
    pub(crate) repo: String,
    pub(crate) mode: Mode,
    pub(crate) pr_number: Option<u64>,
    pub(crate) issue_number: Option<u64>,
    pub(crate) base_sha: Option<String>,
    pub(crate) head_sha: Option<String>,
    pub(crate) model: String,
    pub(crate) base_url: String,
    pub(crate) api_key: Option<String>,
    pub(crate) max_iters: u32,
    pub(crate) dry_run: bool,
}

impl Config {
    pub(crate) fn from_env() -> Result<Self> {
        let repo = std::env::var("GITHUB_REPOSITORY")
            .unwrap_or_else(|_| "peterlodri-sec/vaked-base".to_string());
        let mode = Mode::from_str(&std::env::var("MODE").unwrap_or_default());
        let pr_number = std::env::var("PR_NUMBER")
            .ok()
            .and_then(|s| s.parse::<u64>().ok());
        let issue_number = std::env::var("ISSUE_NUMBER")
            .ok()
            .and_then(|s| s.parse::<u64>().ok());
        let base_sha = std::env::var("BASE_SHA").ok().filter(|s| !s.is_empty());
        let head_sha = std::env::var("HEAD_SHA").ok().filter(|s| !s.is_empty());
        let model = std::env::var("LABEL_TAGGER_MODEL")
            .unwrap_or_else(|_| DEFAULT_MODEL.to_string());
        let base_url = std::env::var("OPENROUTER_BASE_URL")
            .unwrap_or_else(|_| DEFAULT_BASE_URL.to_string());
        let api_key = std::env::var("LABEL_TAGGER_API_KEY")
            .ok()
            .or_else(|| std::env::var("OPENROUTER_API_KEY").ok())
            .filter(|s| !s.is_empty());
        let max_iters = std::env::var("LABEL_TAGGER_MAX_ITERS")
            .ok()
            .and_then(|s| s.parse().ok())
            .unwrap_or(DEFAULT_MAX_ITERS);
        let dry_run = std::env::var("DRY_RUN")
            .map(|s| s == "1" || s.to_ascii_lowercase() == "true")
            .unwrap_or(false);
        Ok(Config { repo, mode, pr_number, issue_number, base_sha, head_sha, model, base_url, api_key, max_iters, dry_run })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mode_from_str_roundtrip() {
        assert_eq!(Mode::from_str("label"), Mode::Label);
        assert_eq!(Mode::from_str("changelog"), Mode::Changelog);
        assert_eq!(Mode::from_str("milestone-sync"), Mode::MilestoneSync);
        assert_eq!(Mode::from_str("all"), Mode::All);
        assert_eq!(Mode::from_str(""), Mode::Label);
        assert_eq!(Mode::from_str("unknown"), Mode::Label);
    }
}
