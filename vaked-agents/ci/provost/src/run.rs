//! Orchestration: scan repo + GitHub state, then plan (LLM or deterministic).

use anyhow::Result;
use tracing::warn;

use crate::agent::{ask, build_runner};
use crate::config::Config;
use crate::github::fetch_gh_state;
use crate::parse::{deterministic_plan, parse_output};
use crate::prompts::build_reconcile_prompt;
use crate::scan::{scan_rfcs, scan_specs};

pub(crate) async fn run() -> Result<()> {
    let cfg = Config::from_env()?;

    let rfcs = scan_rfcs();
    let specs = scan_specs();
    let gh_state = fetch_gh_state(&cfg);
    let output = match cfg.api_key.as_deref() {
        Some(api_key) => {
            let prompt = build_reconcile_prompt(&cfg, &rfcs, &specs, &gh_state);
            let runner = build_runner(&cfg, api_key)?;
            let raw = ask(&runner, prompt).await?;
            parse_output(&raw)
        }
        None => {
            warn!("no OPENROUTER_API_KEY — emitting deterministic RFC-index plan only");
            deterministic_plan(&rfcs)
        }
    };

    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}
