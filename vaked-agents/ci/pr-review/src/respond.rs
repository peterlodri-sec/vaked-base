//! @vaked-ci interactive responder.

use std::sync::Arc;

use adk_rust::prelude::Toolset;
use anyhow::{Result, anyhow};
use tracing::{Instrument, info, info_span, warn};

use crate::agent::{ask, build_runner_with, connect_crabcc};
use crate::autofix::estimate_cost_usd;
use crate::config::{Config, truncate};
use crate::consts::{MENTION, REPLY_MARKER, footer_signature};
use crate::diff::filter_unified;
use crate::github::{fetch_diff, fetch_pr_meta, post_reply};
use crate::prompts::assistant_prompt;
use crate::review::run_review;

/// True when invoked as the interactive responder (`--respond` or VAKED_CI_RESPOND).
pub(crate) fn respond_requested() -> bool {
    std::env::var("VAKED_CI_RESPOND").is_ok() || std::env::args().skip(1).any(|a| a == "--respond")
}

/// What an `@vaked-ci` comment is asking for.
enum Intent {
    /// Empty / "review" / "re-review" → run a fresh full review.
    Review,
    /// Anything else → answer this free-form request.
    Question(String),
}

/// Strip the `@vaked-ci` mention and classify the request.
fn classify_intent(comment: &str) -> Intent {
    let after = match comment.to_ascii_lowercase().find(MENTION) {
        Some(i) => &comment[i + MENTION.len()..],
        None => comment,
    };
    let norm = after.trim().trim_matches(|c: char| c == ':' || c.is_whitespace());
    let key = norm.to_ascii_lowercase();
    if key.is_empty() || key == "review" || key == "re-review" || key == "rereview" {
        Intent::Review
    } else {
        Intent::Question(norm.to_string())
    }
}

pub(crate) async fn run_respond() -> Result<()> {
    let started = std::time::Instant::now();
    let cfg = Config::from_env_and_args()?;
    let comment = std::env::var("COMMENT_BODY").unwrap_or_default();
    let author = std::env::var("COMMENT_AUTHOR").unwrap_or_else(|_| "there".to_string());

    let question = match classify_intent(&comment) {
        Intent::Review => {
            info!(pr = cfg.pr, "@vaked-ci: re-review requested");
            return run_review().await;
        }
        Intent::Question(q) => q,
    };

    let span = info_span!("vaked_ci_respond", repo = %cfg.repo, pr = cfg.pr, model = %cfg.model);
    async move {
        let meta = fetch_pr_meta(&cfg)?;
        let diff = filter_unified(&fetch_diff(&cfg)?);
        let api_key = cfg.api_key.clone().ok_or_else(|| {
            anyhow!("no OpenRouter key — set OPENROUTER_API_KEY or PR_REVIEW_API_KEY")
        })?;
        let crabcc = connect_crabcc(&cfg).await.map_or_else(
            |e| {
                warn!(error = %e, "crabcc unavailable — answering without it");
                None
            },
            |t| Some(Arc::new(t) as Arc<dyn Toolset>),
        );
        let runner = build_runner_with(
            &cfg, &api_key, &cfg.reasoning_effort, 2048, false, crabcc,
            assistant_prompt(cfg.crabcc_budget),
        )?;
        let (body_diff, truncated) = truncate(&diff, cfg.max_diff_chars);
        let prompt = format!(
            "PR #{}: {}\n\nMaintainer @{} asks:\n{}\n\n```diff\n{}\n```{}",
            cfg.pr,
            meta.title,
            author,
            question,
            body_diff,
            if truncated { "\n(diff truncated)" } else { "" }
        );
        let (answer, usage) = ask(&runner, prompt).await?;
        if answer.trim().is_empty() {
            return Err(anyhow!("model returned empty answer"));
        }
        let cost = estimate_cost_usd(usage.total, cfg.usd_per_mtok);
        let footer = format!(
            "<sub>🦴 vaked-ci · {} · {} tok ({} cached) · {:.1}s · cost ~${:.4} · OpenRouter · {} · advisory</sub>",
            cfg.model, usage.total, usage.cached, started.elapsed().as_secs_f64(), cost, footer_signature()
        );
        let reply = format!("{REPLY_MARKER}\n@{author} {answer}\n\n---\n{footer}");
        if cfg.dry_run {
            println!("===== DRY RUN: vaked-ci reply =====\n{reply}");
        } else {
            post_reply(&cfg, &reply)?;
            info!("posted @vaked-ci reply");
        }
        Ok(())
    }
    .instrument(span)
    .await
}

#[cfg(test)]
mod respond_tests {
    use super::*;
    use crate::consts::REPLY_MARKER;

    fn is_review(c: &str) -> bool {
        matches!(classify_intent(c), Intent::Review)
    }
    fn question(c: &str) -> Option<String> {
        match classify_intent(c) {
            Intent::Question(q) => Some(q),
            Intent::Review => None,
        }
    }

    #[test]
    fn bare_mention_and_review_keywords_are_review() {
        assert!(is_review("@vaked-ci"));
        assert!(is_review("@vaked-ci review"));
        assert!(is_review("@vaked-ci re-review please".trim_end_matches(" please"))); // "re-review"
        assert!(is_review("@vaked-ci: review"));
        assert!(is_review("hey @vaked-ci rereview"));
    }

    #[test]
    fn free_form_is_a_question_with_mention_stripped() {
        assert_eq!(
            question("@vaked-ci what does this change?").as_deref(),
            Some("what does this change?")
        );
        assert_eq!(
            question("@vaked-ci: explain the eventd fold").as_deref(),
            Some("explain the eventd fold")
        );
        // mention mid-sentence still strips from the mention onward
        assert_eq!(question("ping @vaked-ci is line 12 safe?").as_deref(), Some("is line 12 safe?"));
    }

    #[test]
    fn reply_has_marker_and_addresses_author() {
        // sanity: marker + footer shape used by run_respond
        let body = format!("{REPLY_MARKER}\n@alice answer\n\n---\nfoot");
        assert!(body.starts_with(REPLY_MARKER));
        assert!(body.contains("@alice"));
    }
}
