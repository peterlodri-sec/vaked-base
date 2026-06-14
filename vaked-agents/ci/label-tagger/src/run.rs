//! Orchestration: dispatch the label / changelog / milestone-sync modes.

use anyhow::{Result, anyhow};
use tracing::{debug, info, warn};

use crate::agent::{ask, build_runner};
use crate::config::{Config, Mode};
use crate::consts::OPT_OUT_LABEL;
use crate::github::{fetch_commits_since_tag, fetch_issue_meta, fetch_pr_diff, fetch_pr_meta};
use crate::goals::parse_goals_phases;
use crate::output::{MilestoneSpec, TaggerOutput, noop_json};
use crate::parse::parse_output;
use crate::prompts::{
    RepoContext, build_changelog_prompt, build_label_issue_prompt, build_label_pr_prompt,
    build_milestone_sync_prompt,
};

fn load_context() -> RepoContext {
    RepoContext {
        goals_md: std::fs::read_to_string("GOALS.md").unwrap_or_default(),
        timeline_md: std::fs::read_to_string("docs/context/TIMELINE.md").unwrap_or_default(),
        labels_yml: std::fs::read_to_string(".github/labels.yml").unwrap_or_default(),
    }
}

pub(crate) async fn run() -> Result<()> {
    let cfg = Config::from_env()?;

    match cfg.mode.clone() {
        Mode::MilestoneSync => run_milestone_sync(&cfg).await,
        Mode::Changelog => run_changelog(&cfg).await,
        Mode::Label => run_label(&cfg).await,
        Mode::All => {
            // Milestone sync first (idempotent), then label if we have a target.
            run_milestone_sync(&cfg).await?;
            if cfg.pr_number.is_some() || cfg.issue_number.is_some() {
                run_label(&cfg).await?;
            }
            Ok(())
        }
    }
}

async fn run_label(cfg: &Config) -> Result<()> {
    let api_key = cfg.api_key.as_deref()
        .ok_or_else(|| anyhow!("no OPENROUTER_API_KEY — set it to enable labeling"))?;

    let ctx = load_context();
    let prompt = if let Some(issue) = cfg.issue_number {
        let meta = fetch_issue_meta(cfg, issue)?;
        if meta.labels.iter().any(|l| l == OPT_OUT_LABEL) {
            info!("'{OPT_OUT_LABEL}' on issue — skipping");
            println!("{}", noop_json());
            return Ok(());
        }
        build_label_issue_prompt(&meta, &ctx)
    } else if let Some(pr) = cfg.pr_number {
        let meta = fetch_pr_meta(cfg, pr)?;
        if meta.labels.iter().any(|l| l == OPT_OUT_LABEL) {
            info!("'{OPT_OUT_LABEL}' on PR — skipping");
            println!("{}", noop_json());
            return Ok(());
        }
        let diff = fetch_pr_diff(cfg, pr);
        build_label_pr_prompt(&meta, &diff, &ctx)
    } else {
        return Err(anyhow!("label mode requires PR_NUMBER or ISSUE_NUMBER"));
    };

    if cfg.dry_run {
        debug!("dry-run: would send label prompt ({} chars)", prompt.len());
        println!("{}", noop_json());
        return Ok(());
    }

    let runner = build_runner(cfg, api_key)?;
    let raw = ask(&runner, prompt).await?;
    let output = parse_output(&raw);
    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}

async fn run_changelog(cfg: &Config) -> Result<()> {
    let api_key = cfg.api_key.as_deref()
        .ok_or_else(|| anyhow!("no OPENROUTER_API_KEY — set it to enable changelog mode"))?;

    let ctx = load_context();
    let commits = fetch_commits_since_tag(&cfg.repo);
    let prompt = build_changelog_prompt(&commits, &ctx);

    if cfg.dry_run {
        debug!("dry-run: would send changelog prompt ({} chars)", prompt.len());
        println!("{}", noop_json());
        return Ok(());
    }

    let runner = build_runner(cfg, api_key)?;
    let raw = ask(&runner, prompt).await?;
    let output = parse_output(&raw);
    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}

async fn run_milestone_sync(cfg: &Config) -> Result<()> {
    // Milestone sync is cheap: try a quick LLM pass to let it read GOALS.md
    // and extract phases with descriptions. Fall back to regex parsing in Rust.
    let ctx = load_context();
    let milestones = if let Some(api_key) = &cfg.api_key {
        if !cfg.dry_run {
            let runner = build_runner(cfg, api_key)?;
            let raw = ask(&runner, build_milestone_sync_prompt(&ctx)).await?;
            let out = parse_output(&raw);
            if !out.milestones_to_upsert.is_empty() {
                out.milestones_to_upsert
            } else {
                extract_milestones_from_file()
            }
        } else {
            extract_milestones_from_file()
        }
    } else {
        extract_milestones_from_file()
    };

    let output = TaggerOutput {
        milestones_to_upsert: milestones,
        ..Default::default()
    };
    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}

fn extract_milestones_from_file() -> Vec<MilestoneSpec> {
    let goals_md = std::fs::read_to_string("GOALS.md").unwrap_or_default();
    if goals_md.is_empty() {
        warn!("GOALS.md not found — returning empty milestone list");
        return Vec::new();
    }
    parse_goals_phases(&goals_md)
}
