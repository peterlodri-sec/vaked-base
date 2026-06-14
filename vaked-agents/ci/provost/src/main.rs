//! Vaked CI provost agent — the product-owner / coordination agent.
//!
//! Doc-grounded project-graph reconciler for vaked-base. On every run it reads
//! the live GOALS.md, docs/context/TIMELINE.md, .github/labels.yml, and the RFC
//! index (docs/protocol/README.md) — so every decision is grounded in what is
//! currently in the repository, not hard-coded knowledge — plus a pre-scanned
//! catalog of the RFC series, the design specs/plans, and current GitHub state
//! (open issues, milestones, epics). It then emits a coordination plan as JSON.
//!
//! The binary is **read-only**: it reads GitHub state via `gh` and emits a single
//! JSON object to stdout. The wrapper shell in the GitHub Actions workflow reads
//! that JSON and applies the mutations, enforcing the safety boundary:
//!   * auto-applied (reversible GitHub metadata): label add/remove, native
//!     sub-issue parent↔child links, assigning an existing milestone;
//!   * surfaced for approval (content / new objects): proposed new epics/issues,
//!     RFC stubs, and the proposed RFC index — written into ONE coordination
//!     issue (and, for new RFC stub files, ONE coordination PR).
//!
//! It NEVER blocks CI: any failure logs and exits 0 after printing a safe no-op.
//!
//! Modes (set by the `MODE` env var):
//!   all   — full reconciliation (epics + RFC process + cross-links). Default.
//!   rfc   — RFC process: index/status/tracking-issue reconciliation only.
//!   epic  — epics: epic creation/linking reconciliation only.
//!   link  — pure cross-linking + label sync (the safe-sync subset), no proposals.
//!
//! Env vars:
//!   OPENROUTER_API_KEY | PROVOST_API_KEY  (required for LLM-driven proposals)
//!   PROVOST_MODEL                          (default: deepseek/deepseek-v4-flash)
//!   OPENROUTER_BASE_URL                    (default: https://openrouter.ai/api/v1)
//!   MODE                                   (all|rfc|epic|link)
//!   GITHUB_REPOSITORY                      (owner/repo)
//!   LANGFUSE_URL, LANGFUSE_API_KEY         (optional; tracing degrades gracefully)

mod agent;
mod config;
mod consts;
mod github;
mod guardrails;
mod output;
mod parse;
mod prompts;
mod run;
mod scan;
mod telemetry;

use consts::{GIT_SHA, VERSION};
use output::noop_json;
use run::run;
use telemetry::setup_tracing;

#[global_allocator]
static GLOBAL: mimalloc::MiMalloc = mimalloc::MiMalloc;

#[tokio::main]
async fn main() {
    if std::env::args().any(|a| a == "--version" || a == "-V") {
        println!("vaked-provost {VERSION}+{GIT_SHA}");
        return;
    }

    let tracer_provider = setup_tracing();

    let code = match run().await {
        Ok(()) => 0,
        Err(e) => {
                eprintln!("provost: {e:#}");
            println!("{}", noop_json());
            0
        }
    };

    if let Some(provider) = tracer_provider {
        if let Err(e) = provider.shutdown() {
            eprintln!("provost: telemetry flush failed: {e}");
        }
    }
    std::process::exit(code);
}
