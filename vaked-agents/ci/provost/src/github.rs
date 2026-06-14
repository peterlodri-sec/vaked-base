//! `gh` CLI helper + live GitHub state (open issues, milestones).

use std::process::Command as StdCommand;

use anyhow::{Context, Result, anyhow};
use serde_json::Value;

use crate::config::Config;
use crate::consts::{EPIC_LABEL, MAX_ISSUES};

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

#[derive(Debug, Default)]
pub(crate) struct GhState {
    pub(crate) issues: Vec<IssueLite>,
    pub(crate) milestones: Vec<String>,
}

#[derive(Debug)]
pub(crate) struct IssueLite {
    pub(crate) number: u64,
    pub(crate) title: String,
    pub(crate) labels: Vec<String>,
    pub(crate) milestone: Option<String>,
    pub(crate) is_epic: bool,
}

pub(crate) fn fetch_gh_state(cfg: &Config) -> GhState {
    let mut state = GhState::default();

    // Open issues — jq-projected to only the fields we use, so the wire payload
    // is ~90% smaller than fetching full issue JSON.
    let limit = MAX_ISSUES.to_string();
    let jq = r#"[.[] | {number, title, labels: [.labels[].name], milestone: .milestone.title}]"#;
    if let Ok(raw) = gh(&[
        "issue", "list", "--repo", &cfg.repo, "--state", "open",
        "--limit", &limit, "--json", "number,title,labels,milestone",
        "--jq", jq,
    ]) {
        if let Ok(Value::Array(arr)) = serde_json::from_str::<Value>(&raw) {
            for v in arr {
                let labels: Vec<String> = v["labels"]
                    .as_array()
                    .map(|a| a.iter().filter_map(|l| l.as_str().map(String::from)).collect())
                    .unwrap_or_default();
                let milestone = v["milestone"].as_str().map(String::from);
                let is_epic = labels.iter().any(|l| l == EPIC_LABEL);
                state.issues.push(IssueLite {
                    number: v["number"].as_u64().unwrap_or(0),
                    title: v["title"].as_str().unwrap_or_default().to_string(),
                    labels,
                    milestone,
                    is_epic,
                });
            }
        }
    } else {
        eprintln!("provost: could not list issues (no GH_TOKEN?) — proceeding with empty issue set");
    }

    // Milestone titles.
    let endpoint = format!("repos/{}/milestones", cfg.repo);
    if let Ok(raw) = gh(&["api", &endpoint, "--jq", ".[].title"]) {
        state.milestones = raw.lines().map(|l| l.trim().to_string()).filter(|l| !l.is_empty()).collect();
    }

    state
}
