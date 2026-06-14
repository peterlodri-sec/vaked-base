//! Orchestrator configuration, parsed from environment (or a map, for tests).

use anyhow::{Result, anyhow};
use std::collections::HashMap;

#[derive(Debug, Clone)]
pub struct Config {
    pub nats_url: String,
    pub nats_creds: Option<String>,
    pub stream: String,
    pub subject: String,
    pub consumer: String,
    pub status_prefix: String,
    pub pool: usize,
    pub scratch: String,
    pub min_free_bytes: u64,
    pub scratch_cap_bytes: u64,
    pub swe_af_bin: String,
    pub base_url: String,
    pub api_key: String,
    pub gh_read_token: Option<String>,
    pub gh_write_token: Option<String>,
    pub plan_model: String,
    pub code_model: String,
}

fn get<'a>(m: &'a HashMap<String, String>, k: &str) -> Option<&'a str> {
    m.get(k).map(String::as_str).filter(|s| !s.is_empty())
}
fn or(m: &HashMap<String, String>, k: &str, d: &str) -> String {
    get(m, k).unwrap_or(d).to_string()
}
fn gb(m: &HashMap<String, String>, k: &str, d: u64) -> u64 {
    get(m, k).and_then(|s| s.parse::<u64>().ok()).unwrap_or(d) * 1024 * 1024 * 1024
}

impl Config {
    pub fn from_env() -> Result<Self> {
        Self::from_map(&std::env::vars().collect())
    }

    pub fn from_map(m: &HashMap<String, String>) -> Result<Self> {
        let nats_url = get(m, "NATS_URL")
            .ok_or_else(|| anyhow!("NATS_URL required"))?
            .to_string();
        Ok(Config {
            nats_url,
            nats_creds: get(m, "NATS_CREDS").map(String::from),
            stream: or(m, "SWE_AF_STREAM", "SWE_AF_TASKS"),
            subject: or(m, "SWE_AF_SUBJECT", "swe.af.tasks"),
            consumer: or(m, "SWE_AF_CONSUMER", "swe-af-workers"),
            status_prefix: or(m, "SWE_AF_STATUS_PREFIX", "swe.af.status"),
            pool: get(m, "SWE_AF_POOL")
                .and_then(|s| s.parse().ok())
                .unwrap_or(6),
            scratch: or(m, "SWE_AF_SCRATCH", "/var/lib/swe-af/scratch"),
            min_free_bytes: gb(m, "SWE_AF_MIN_FREE_GB", 10),
            scratch_cap_bytes: gb(m, "SWE_AF_SCRATCH_CAP_GB", 20),
            swe_af_bin: or(m, "SWE_AF_BIN", "/usr/local/bin/vaked-swe-af"),
            base_url: or(
                m,
                "OPENROUTER_BASE_URL",
                "https://nixai-base.tail2870dc.ts.net/aperture/v1",
            ),
            api_key: or(m, "SWE_AF_API_KEY", "tailscale-identity"),
            gh_read_token: get(m, "GH_TOKEN").map(String::from),
            gh_write_token: get(m, "SWE_AF_GH_WRITE_TOKEN").map(String::from),
            plan_model: or(m, "SWE_AF_PLAN_MODEL", "deepseek/deepseek-v4-flash"),
            code_model: or(m, "SWE_AF_CODE_MODEL", "openai/gpt-5.3-codex"),
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn base() -> HashMap<String, String> {
        let mut m = HashMap::new();
        m.insert("NATS_URL".into(), "nats://x:4222".into());
        m
    }

    #[test]
    fn defaults_apply() {
        let c = Config::from_map(&base()).unwrap();
        assert_eq!(c.pool, 6);
        assert_eq!(c.subject, "swe.af.tasks");
        assert_eq!(c.min_free_bytes, 10 * 1024 * 1024 * 1024);
        assert_eq!(c.scratch_cap_bytes, 20 * 1024 * 1024 * 1024);
        assert_eq!(c.plan_model, "deepseek/deepseek-v4-flash");
        assert_eq!(c.api_key, "tailscale-identity");
    }

    #[test]
    fn requires_nats_url() {
        assert!(Config::from_map(&HashMap::new()).is_err());
    }

    #[test]
    fn overrides_parse() {
        let mut m = base();
        m.insert("SWE_AF_POOL".into(), "12".into());
        m.insert("SWE_AF_MIN_FREE_GB".into(), "5".into());
        m.insert("GH_TOKEN".into(), "gh_read".into());
        let c = Config::from_map(&m).unwrap();
        assert_eq!(c.pool, 12);
        assert_eq!(c.min_free_bytes, 5 * 1024 * 1024 * 1024);
        assert_eq!(c.gh_read_token.as_deref(), Some("gh_read"));
        assert_eq!(c.gh_write_token, None);
    }

    #[test]
    fn empty_env_value_falls_back_to_default() {
        let mut m = base();
        m.insert("SWE_AF_SUBJECT".into(), String::new());
        assert_eq!(Config::from_map(&m).unwrap().subject, "swe.af.tasks");
    }
}
