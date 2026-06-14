//! Review orchestration: the `run_review` entrypoint + the map-reduce path.

use std::sync::Arc;

use adk_rust::prelude::Toolset;
use anyhow::{Result, anyhow};
use serde_json::json;
use tracing::{Instrument, field, info, info_span, warn};

use crate::agent::{
    Usage, ask, build_runner_with, connect_crabcc, parallel_agent_review,
};
use crate::autofix::{estimate_cost_usd, post_inline_suggestions, print_dry_run_suggestions};
use crate::config::{Config, truncate};
use crate::consts::{
    COMMENT_MARKER, MAX_FILES_MAPREDUCE, OPT_OUT_LABEL, PERFILE_REASONING_EFFORT, footer_signature,
};
use crate::diff::{count_changed_lines, diff_right_lines, filter_unified, split_per_file};
use crate::github::{
    fetch_diff, fetch_pr_meta, post_review, rtk_condensed, set_advisory_status,
};
use crate::cleanup::cleanup_pr_comments;
use crate::prompts::{
    build_prompt, docs_review_prompt, is_doc_file, language_addenda, system_prompt,
};
use crate::provenance::fetch_provenance;
use crate::render::{parse_structured, render_review};
use crate::telemetry::{commit_html_url, langfuse_trace_url, pr_html_url, record_mode, run_html_url};
use crate::agent::ReviewRunner;
use crate::github::PrMeta;

pub(crate) async fn run_review() -> Result<()> {
    let started = std::time::Instant::now();
    let cfg = Config::from_env_and_args()?;
    // Link the Langfuse trace back to the PR (deterministic URL) and, once posted,
    // to the exact review comment. `langfuse.trace.*` / `langfuse.session.*` are the
    // attribute keys Langfuse maps off OTLP spans (tracing-opentelemetry exports span
    // field names verbatim); re-reviews of the same PR share one session.
    let pr_url = pr_html_url(&cfg.repo, cfg.pr);
    let session_id = format!("{}#{}", cfg.repo, cfg.pr);
    let trace_name = format!("pr-review {}#{}", cfg.repo, cfg.pr);
    let trace_tags = serde_json::to_string(&["pr-review", cfg.model.as_str()]).unwrap_or_default();
    let span = info_span!(
        "pr_review",
        repo = %cfg.repo,
        pr = cfg.pr,
        model = %cfg.model,
        changed_lines = field::Empty,
        mode = field::Empty,
        total_tokens = field::Empty,
        thinking_tokens = field::Empty,
        cached_tokens = field::Empty,
        findings = field::Empty,
        // Langfuse trace identity + filterable metadata (+ links to the PR / comment).
        "langfuse.trace.name" = %trace_name,
        "langfuse.session.id" = %session_id,
        "langfuse.trace.tags" = %trace_tags,
        "langfuse.trace.metadata.repo" = %cfg.repo,
        "langfuse.trace.metadata.pr" = cfg.pr,
        "langfuse.trace.metadata.model" = %cfg.model,
        "langfuse.trace.metadata.pr_url" = %pr_url,
        "langfuse.trace.metadata.mode" = field::Empty,
        "langfuse.trace.metadata.total_tokens" = field::Empty,
        "langfuse.trace.metadata.cached_tokens" = field::Empty,
        "langfuse.trace.metadata.findings" = field::Empty,
        "langfuse.trace.metadata.comment_url" = field::Empty,
    );
    async move {
        // Lightweight per-stage timers → the footer's "slowest" runtime breakdown.
        let mut stages: Vec<(&str, f64)> = Vec::new();
        let st = std::time::Instant::now();
        let meta = fetch_pr_meta(&cfg)?;
        if meta.labels.iter().any(|l| l == OPT_OUT_LABEL) {
            info!("'{OPT_OUT_LABEL}' label present — skipping");
            return Ok(());
        }

        // Inline comment cleanup: sweep bot noise + collapse duplicate bot review
        // comments before posting this run's review (advisory, best-effort).
        if cfg.cleanup {
            let (noise, dupes) = cleanup_pr_comments(&cfg.repo, cfg.pr);
            if noise + dupes > 0 {
                info!(noise, dupes, "cleanup: swept PR comments before review");
            }
        }
        stages.push(("meta", st.elapsed().as_secs_f64()));

        let st = std::time::Instant::now();
        let raw = fetch_diff(&cfg)?;
        // Secret redaction now happens in the agent's input guardrail (uniformly,
        // at the model boundary), so it is no longer applied inline here.
        let diff = filter_unified(&raw);
        if diff.trim().is_empty() {
            info!("empty diff after filtering — nothing to review");
            return Ok(());
        }
        let changed = count_changed_lines(&diff);
        let span = tracing::Span::current();
        span.record("changed_lines", changed);
        // RIGHT-side lines present in the current diff — computed before `diff` is
        // moved into the size-routing block, used to drop stale/off-diff findings
        // when posting inline suggestions.
        let right_lines = diff_right_lines(&diff);
        stages.push(("diff", st.elapsed().as_secs_f64()));

        let api_key = cfg.api_key.clone().ok_or_else(|| {
            anyhow!("no OpenRouter key — set OPENROUTER_API_KEY or PR_REVIEW_API_KEY")
        })?;
        let st = std::time::Instant::now();
        let crabcc = connect_crabcc(&cfg).await.map_or_else(
            |e| {
                warn!(error = %e, "crabcc unavailable — reviewing without it");
                None
            },
            |t| Some(Arc::new(t) as Arc<dyn Toolset>),
        );
        stages.push(("crabcc", st.elapsed().as_secs_f64()));

        let st = std::time::Instant::now();
        let addenda = language_addenda(&meta.files);
        let mut usage = Usage::default();

        // Docs/prose-only PRs get a lighter, doc-focused reviewer and stay single-pass
        // — the 7-lens engineering council yields noise on a design doc.
        let docs_only = !meta.files.is_empty() && meta.files.iter().all(|f| is_doc_file(f));

        // High-reasoning, structured final-output runner (single-pass + synthesis).
        let high = build_runner_with(
            &cfg, &api_key, &cfg.reasoning_effort, 4096, cfg.structured, crabcc.clone(),
            if docs_only {
                docs_review_prompt(cfg.max_findings, cfg.crabcc_budget, cfg.structured)
            } else {
                system_prompt(cfg.max_findings, cfg.crabcc_budget, cfg.structured)
            },
        )?;

        let raw_review = if !docs_only && changed > cfg.mapreduce_lines {
            if cfg.parallel_agent {
                // Opt-in adk workflow-agent pipeline (PR_REVIEW_PARALLEL_AGENT). Kept
                // opt-in until validated live — its runtime behaviour (multi-agent
                // context propagation) can't be exercised in CI without a model key —
                // and it falls back to the proven map-reduce if it errors.
                record_mode(&span, "parallel-agent");
                info!(changed, threshold = cfg.mapreduce_lines, "large PR — parallel-agent pipeline");
                match parallel_agent_review(
                    &cfg, &api_key, &meta, &diff, &addenda, crabcc.clone(), &mut usage,
                )
                .await
                {
                    Ok(r) => r,
                    Err(e) => {
                        warn!(error = %e, "parallel-agent path failed — falling back to map-reduce");
                        record_mode(&span, "map-reduce-fallback");
                        let med = build_runner_with(
                            &cfg, &api_key, PERFILE_REASONING_EFFORT, 1024, false, crabcc.clone(),
                            system_prompt(cfg.max_findings, cfg.crabcc_budget, false),
                        )?;
                        map_reduce_review(&med, &high, &cfg, &meta, &diff, &addenda, &mut usage)
                            .await?
                    }
                }
            } else {
                record_mode(&span, "map-reduce");
                info!(changed, threshold = cfg.mapreduce_lines, "large PR — map-reduce");
                let med = build_runner_with(
                    &cfg, &api_key, PERFILE_REASONING_EFFORT, 1024, false, crabcc.clone(),
                    system_prompt(cfg.max_findings, cfg.crabcc_budget, false),
                )?;
                map_reduce_review(&med, &high, &cfg, &meta, &diff, &addenda, &mut usage).await?
            }
        } else {
            record_mode(&span, if docs_only { "docs-single-pass" } else { "single-pass" });
            let body = rtk_condensed(&cfg)
                .map(|c| filter_unified(&c))
                .filter(|c| !c.trim().is_empty())
                .unwrap_or(diff);
            let (body, truncated) = truncate(&body, cfg.max_diff_chars);
            let prompt = build_prompt(&meta, &body, truncated, &addenda);
            let (text, u) = ask(&high, prompt).await?;
            usage += u;
            text
        };
        stages.push(("review", st.elapsed().as_secs_f64()));

        let (review, n_findings, n_blocking) = render_review(&raw_review, cfg.max_findings as usize);
        if review.is_empty() {
            return Err(anyhow!("model returned empty review"));
        }
        // Structured findings (if any) drive the inline ```suggestion``` comments.
        let findings = parse_structured(&raw_review)
            .map(|r| r.findings)
            .unwrap_or_default();

        span.record("total_tokens", usage.total);
        span.record("thinking_tokens", usage.thinking);
        span.record("cached_tokens", usage.cached);
        span.record("findings", n_findings);
        // Mirror the run totals into filterable Langfuse trace metadata.
        span.record("langfuse.trace.metadata.total_tokens", usage.total);
        span.record("langfuse.trace.metadata.cached_tokens", usage.cached);
        span.record("langfuse.trace.metadata.findings", n_findings);
        info!(total = usage.total, cached = usage.cached, findings = n_findings, blocking = n_blocking, "review ready");

        let cost = estimate_cost_usd(usage.total, cfg.usd_per_mtok);
        // GitHub→Langfuse: link the comment to its own trace when a project id is set.
        let trace_link = langfuse_trace_url(&span)
            .map(|u| format!(" · [trace]({u})"))
            .unwrap_or_default();
        // Provenance round: surface commit-signature status (best-effort, advisory).
        let st = std::time::Instant::now();
        let provenance = if cfg.provenance {
            fetch_provenance(&cfg).map(|p| p.summary_line()).unwrap_or_default()
        } else {
            String::new()
        };
        stages.push(("provenance", st.elapsed().as_secs_f64()));

        // Compact, parse-friendly footer: ` · `-delimited `key=value` tokens + markdown
        // links. `runtime` shows the total plus the 3 slowest of the timed stages, so a
        // slow run is self-diagnosing without reading the trace.
        let total_s = started.elapsed().as_secs_f64();
        stages.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
        let slowest = stages.iter().take(3)
            .map(|(name, s)| format!("{name} {s:.1}s"))
            .collect::<Vec<_>>()
            .join(", ");
        let commit_link = cfg.head_sha.as_deref().map(|sha| {
            format!(" · [commit {}]({})", &sha[..sha.len().min(7)], commit_html_url(&cfg.repo, sha))
        }).unwrap_or_default();
        let run_link = run_html_url(&cfg.repo)
            .map(|u| format!(" · [run]({u})"))
            .unwrap_or_default();
        let body = format!(
            "{COMMENT_MARKER}\n{review}\n{provenance}\n\n---\n\
             <sub>🦴 vaked-ci-reviewer · advisory · model={} · findings={} · tok={} (cached {}) · \
             cost=${:.4} · runtime={:.1}s (slowest: {}){}{}{} · {}</sub>",
            cfg.model, n_findings, usage.total, usage.cached, cost, total_s, slowest,
            commit_link, run_link, trace_link, footer_signature()
        );

        if cfg.dry_run {
            println!("===== DRY RUN: review comment =====\n{body}");
            if cfg.autofix {
                print_dry_run_suggestions(&findings, &right_lines);
            }
        } else {
            // Langfuse→GitHub: record the posted comment's URL on the trace.
            if let Some(url) = post_review(&cfg, &body)? {
                span.record("langfuse.trace.metadata.comment_url", url.as_str());
            }
            let desc = format!("{n_findings} findings ({n_blocking} blocking) · {} tok", usage.total);
            set_advisory_status(&cfg, &desc);
            info!("posted advisory review + status");
            // Inline ```suggestion``` comments for small findings — never fail the run.
            if cfg.autofix {
                match post_inline_suggestions(&cfg, &findings, &right_lines) {
                    Ok(0) => {}
                    Ok(n) => info!(count = n, "posted inline autofix suggestions"),
                    Err(e) => warn!(error = %e, "inline suggestions failed — continuing"),
                }
            }
        }
        Ok(())
    }
    .instrument(span)
    .await
}

/// Per-file passes (in parallel) over a large diff, then one synthesis pass.
#[allow(clippy::too_many_arguments)]
async fn map_reduce_review(
    med: &ReviewRunner,
    high: &ReviewRunner,
    cfg: &Config,
    meta: &PrMeta,
    diff: &str,
    addenda: &str,
    usage: &mut Usage,
) -> Result<String> {
    use futures::StreamExt;
    use futures::stream;

    let files = split_per_file(diff);
    let total = files.len();
    let budget = cfg.max_diff_chars / 4;

    let results: Vec<(String, Result<(String, Usage)>)> =
        stream::iter(files.into_iter().take(MAX_FILES_MAPREDUCE).map(|(path, section)| async move {
            let (section, _) = truncate(&section, budget);
            let prompt = format!(
                "Review ONLY this file's diff per your rules. File: {path}\n```diff\n{section}\n```{addenda}"
            );
            (path, ask(med, prompt).await)
        }))
        .buffer_unordered(cfg.concurrency)
        .collect()
        .await;

    let mut raw_findings = String::new();
    for (path, res) in results {
        match res {
            Ok((text, u)) => {
                *usage += u;
                let t = text.trim();
                if !t.is_empty() {
                    raw_findings.push_str(&format!("\n## {path}\n{t}\n"));
                }
            }
            Err(e) => warn!(%path, error = %e, "per-file pass failed — skipping file"),
        }
    }
    if total > MAX_FILES_MAPREDUCE {
        raw_findings.push_str(&format!(
            "\n(note: {total} files changed; reviewed first {MAX_FILES_MAPREDUCE})\n"
        ));
    }
    if raw_findings.trim().is_empty() {
        return Ok(clean_verdict(cfg.structured));
    }

    let synth = format!(
        "Below are raw per-file findings from a large PR ({total} files). Produce the FINAL review per your output contract: dedupe, keep the most important, group by severity, lead with the verdict line.\n\nPR #{}: {}\n{raw_findings}",
        meta.number, meta.title
    );
    let (text, u) = ask(high, synth).await?;
    *usage += u;
    Ok(text)
}

pub(crate) fn clean_verdict(structured: bool) -> String {
    if structured {
        json!({"verdict":"No blocking issues.","prose":"**Verdict:** No blocking issues.","findings":[],"exceptions":[]}).to_string()
    } else {
        "**Verdict:** No blocking issues.".to_string()
    }
}
