//! Orchestration: dispatch the label / changelog / milestone-sync modes.

use anyhow::{Result, anyhow};
use tracing::{debug, info, warn};

use crate::agent::{ask, build_runner};
use crate::config::{Config, Mode};
use crate::consts::{GIT_SHA, OPT_OUT_LABEL, VERSION};
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

/// Append the shared advisory footer to the agent's comment (baked into the
/// binary so every agent's footer matches). Fills only the fields label-tagger
/// tracks; tokens/cost are omitted.
fn append_footer(cfg: &Config, output: &mut TaggerOutput, runtime_s: f64) {
    let Some(comment) = output.comment.take() else { return };
    let comment = comment.trim().to_string();
    if comment.is_empty() {
        return;
    }
    let model_short = cfg.model.rsplit('/').next().unwrap_or(&cfg.model);
    let metrics = [
        ("model", model_short.to_string()),
        ("labels", output.labels.len().to_string()),
    ];
    let links = format!(
        "{}{}",
        vaked_agents_shared::footer::commit_link(&cfg.repo, cfg.head_sha.as_deref()),
        vaked_agents_shared::footer::run_link(&cfg.repo),
    );
    let sig = vaked_agents_shared::footer::signature(VERSION, GIT_SHA);
    let footer = vaked_agents_shared::footer::Footer {
        agent: "vaked-label-tagger",
        metrics: &metrics,
        runtime_s: Some(runtime_s),
        slowest: None,
        links: &links,
        signature: &sig,
    }
    .render();
    output.comment = Some(format!("{comment}\n\n---\n{footer}"));
}

async fn run_label(cfg: &Config) -> Result<()> {
    let started = std::time::Instant::now();
    let api_key = cfg.api_key.as_deref()
        .ok_or_else(|| anyhow!("no OPENROUTER_API_KEY — set it to enable labeling"))?;

    let prompt = if let Some(issue) = cfg.issue_number {
        // Context files and issue meta are independent — overlap them.
        let cfg2 = cfg.clone();
        let (ctx_res, meta_res) = tokio::join!(
            tokio::task::spawn_blocking(load_context),
            tokio::task::spawn_blocking(move || fetch_issue_meta(&cfg2, issue)),
        );
        let ctx = ctx_res?;
        let meta = meta_res??;
        if meta.labels.iter().any(|l| l == OPT_OUT_LABEL) {
            info!("'{OPT_OUT_LABEL}' on issue — skipping");
            println!("{}", noop_json());
            return Ok(());
        }
        build_label_issue_prompt(&meta, &ctx)
    } else if let Some(pr) = cfg.pr_number {
        // Context files, PR meta (network), and PR diff (local git) are all
        // independent — fire them all at once.
        let cfg2 = cfg.clone();
        let cfg3 = cfg.clone();
        let (ctx_res, meta_res, diff_res) = tokio::join!(
            tokio::task::spawn_blocking(load_context),
            tokio::task::spawn_blocking(move || fetch_pr_meta(&cfg2, pr)),
            tokio::task::spawn_blocking(move || fetch_pr_diff(&cfg3, pr)),
        );
        let ctx = ctx_res?;
        let meta = meta_res??;
        let diff = diff_res?;
        if meta.labels.iter().any(|l| l == OPT_OUT_LABEL) {
            info!("'{OPT_OUT_LABEL}' on PR — skipping");
            println!("{}", noop_json());
            return Ok(());
        }
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
    let mut output = parse_output(&raw);
    append_footer(cfg, &mut output, started.elapsed().as_secs_f64());
    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}

async fn run_changelog(cfg: &Config) -> Result<()> {
    let api_key = cfg.api_key.as_deref()
        .ok_or_else(|| anyhow!("no OPENROUTER_API_KEY — set it to enable changelog mode"))?;

    // File reads and git/network fetches are independent — overlap them.
    let (ctx_res, commits) = tokio::join!(
        tokio::task::spawn_blocking(load_context),
        fetch_commits_since_tag(&cfg.repo),
    );
    let ctx = ctx_res?;
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
