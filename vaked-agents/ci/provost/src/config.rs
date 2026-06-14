//! Runtime configuration (env vars).

use anyhow::Result;

use crate::consts::{DEFAULT_BASE_URL, DEFAULT_MAX_ITERS, DEFAULT_MODEL};

#[derive(Debug, PartialEq, Clone)]
pub(crate) enum Mode {
    All,
    Rfc,
    Epic,
    Link,
}

impl Mode {
    pub(crate) fn from_str(s: &str) -> Self {
        match s.to_ascii_lowercase().trim() {
            "rfc" => Mode::Rfc,
            "epic" => Mode::Epic,
            "link" => Mode::Link,
            _ => Mode::All,
        }
    }

    pub(crate) fn as_str(&self) -> &'static str {
        match self {
            Mode::All => "all",
            Mode::Rfc => "rfc",
            Mode::Epic => "epic",
            Mode::Link => "link",
        }
    }
}

pub(crate) struct Config {
    pub(crate) repo: String,
    pub(crate) mode: Mode,
    pub(crate) model: String,
    pub(crate) base_url: String,
    pub(crate) api_key: Option<String>,
    pub(crate) max_iters: u32,
}

impl Config {
    pub(crate) fn from_env() -> Result<Self> {
        let repo = std::env::var("GITHUB_REPOSITORY")
            .unwrap_or_else(|_| "peterlodri-sec/vaked-base".to_string());
        let mode = Mode::from_str(&std::env::var("MODE").unwrap_or_default());
        let model =
            std::env::var("PROVOST_MODEL").unwrap_or_else(|_| DEFAULT_MODEL.to_string());
        let base_url = std::env::var("OPENROUTER_BASE_URL")
            .unwrap_or_else(|_| DEFAULT_BASE_URL.to_string());
        let api_key = std::env::var("PROVOST_API_KEY")
            .ok()
            .or_else(|| std::env::var("OPENROUTER_API_KEY").ok())
            .filter(|s| !s.is_empty());
        let max_iters = std::env::var("PROVOST_MAX_ITERS")
            .ok()
            .and_then(|s| s.parse().ok())
            .unwrap_or(DEFAULT_MAX_ITERS);
        Ok(Config { repo, mode, model, base_url, api_key, max_iters })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mode_from_str_roundtrip() {
        assert_eq!(Mode::from_str("all"), Mode::All);
        assert_eq!(Mode::from_str("rfc"), Mode::Rfc);
        assert_eq!(Mode::from_str("epic"), Mode::Epic);
        assert_eq!(Mode::from_str("link"), Mode::Link);
        assert_eq!(Mode::from_str(""), Mode::All);
        assert_eq!(Mode::from_str("unknown"), Mode::All);
    }
}
