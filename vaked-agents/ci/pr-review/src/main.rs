//! Vaked CI PR-review agent.
//!
//! Advisory PR reviewer on adk-rust. Reads a PR's diff (RTK-condensed, noise
//! filtered), reviews it with a non-frontier OpenRouter model (DeepSeek V4 Flash) — with the
//! repo's `crabcc` symbol index + a `read_lines` tool as MCP / native tools — and
//! posts ONE structured review comment (replacing its prior one). The untrusted
//! diff is secret-redacted, injection-defanged, and findings-capped by adk
//! guardrails; context compaction guards the tool loop. Large PRs are map-reduced
//! per file in parallel (opt-in: an adk `ParallelAgent`/`SequentialAgent` pipeline
//! via `PR_REVIEW_PARALLEL_AGENT`). Tiered reasoning: high for the final pass,
//! medium for per-file passes. Output is structured JSON (verdict / findings /
//! caveman prose / exceptions), rendered to markdown. Never blocks a merge: any
//! failure logs and exits 0. Traces to self-hosted Langfuse.
//!
//! Large PRs use a `buffer_unordered` map-reduce by default; an adk
//! `ParallelAgent`/`SequentialAgent` pipeline is opt-in via `PR_REVIEW_PARALLEL_AGENT`
//! (it also serves as the runtime fallback's counterpart — the pipeline falls back
//! to map-reduce if it errors). Kept opt-in until validated live.
//!
//! Env (see README for the full table):
//!   OPENROUTER_API_KEY | PR_REVIEW_API_KEY · PR_REVIEW_MODEL · OPENROUTER_BASE_URL
//!   PR_REVIEW_MAX_DIFF_CHARS · PR_REVIEW_REASONING_EFFORT · PR_REVIEW_MAPREDUCE_LINES
//!   PR_REVIEW_MAX_FINDINGS · PR_REVIEW_CRABCC_BUDGET · PR_REVIEW_MAX_ITERS
//!   PR_REVIEW_CONCURRENCY · PR_REVIEW_NO_STRUCTURED · PR_REVIEW_NO_RTK
//!   PR_REVIEW_PARALLEL_AGENT · PR_REVIEW_EVAL_TOLERANCE · PR_REVIEW_TRACE_PAYLOADS
//!   PR_REVIEW_NO_AUTOFIX (disable inline suggestions) · PR_REVIEW_USD_PER_MTOK (cost rate)
//!   PR_REVIEW_NO_PROVENANCE · PR_REVIEW_NO_CLEANUP · PR_REVIEW_CLEANUP_KEEP · PR_REVIEW_PROVIDER_ORDER
//!   GH_TOKEN | GITHUB_TOKEN · GITHUB_REPOSITORY · GITHUB_EVENT_PATH · GITHUB_SERVER_URL
//!   LANGFUSE_HOST | LANGFUSE_BASE_URL | LANGFUSE_URL · LANGFUSE_PUBLIC_KEY + LANGFUSE_SECRET_KEY
//!   | LANGFUSE_API_KEY · LANGFUSE_PROJECT_ID · CRABCC_BIN · RTK_BIN · BASE_SHA · HEAD_SHA
//!
//! Args: --repo <owner/name> --pr <N> --model <id> --dry-run
//!       --eval <dir>   score the reviewer against local *.diff/*.expect fixtures
//!                      (adk-eval ResponseScorer + BaselineStore regression gating)
//!       --cleanup      sweep bot-noise + duplicate comments on --pr (or every open
//!                      PR when --pr is omitted); comments only, no model call
//!       --respond      interactive @vaked-ci responder mode

use tracing::warn;

mod agent;
mod autofix;
mod cleanup;
mod config;
mod consts;
mod diff;
mod eval;
mod github;
mod guardrails;
mod prompts;
mod provenance;
mod render;
mod respond;
mod review;
mod telemetry;

use cleanup::{cleanup_requested, run_cleanup};
use eval::{eval_dir, run_eval};
use respond::{respond_requested, run_respond};
use review::run_review;
use telemetry::setup_tracing;

// mimalloc: a faster general-purpose allocator for the agent's String/Vec/JSON
// churn (diff parsing, rendering). A global bump/arena would be unsound here —
// tokio/reqwest/rustls hold long-lived allocations that must be freed.
#[global_allocator]
static GLOBAL: mimalloc::MiMalloc = mimalloc::MiMalloc;

#[tokio::main]
async fn main() {
    let tracer_provider = setup_tracing();

    let code = if let Some(dir) = eval_dir() {
        match run_eval(&dir).await {
            Ok(()) => 0,
            Err(e) => {
                eprintln!("eval: {e:#}");
                1
            }
        }
    } else if cleanup_requested() {
        match run_cleanup().await {
            Ok(()) => 0,
            Err(e) => {
                warn!(error = %e, "cleanup failed (advisory — exiting 0)");
                eprintln!("cleanup: {e:#}");
                0
            }
        }
    } else if respond_requested() {
        match run_respond().await {
            Ok(()) => 0,
            Err(e) => {
                warn!(error = %e, "vaked-ci respond failed (advisory — exiting 0)");
                eprintln!("vaked-ci: {e:#}");
                0
            }
        }
    } else {
        match run_review().await {
            Ok(()) => 0,
            Err(e) => {
                warn!(error = %e, "pr-review failed (advisory — exiting 0)");
                eprintln!("pr-review: {e:#}");
                0
            }
        }
    };

    if let Some(provider) = tracer_provider {
        // Short-lived process: force_flush drains the batch span processor before
        // shutdown, so the run's trace reliably reaches Langfuse instead of being
        // dropped on exit.
        if let Err(e) = provider.force_flush() {
            eprintln!("pr-review: telemetry force_flush failed: {e}");
        }
        if let Err(e) = provider.shutdown() {
            eprintln!("pr-review: telemetry shutdown failed: {e}");
        }
    }
    std::process::exit(code);
}
