//! Vaked CI label-tagger agent.
//!
//! Doc-grounded triage automation for vaked-base. On every run it reads the
//! live versions of GOALS.md, docs/context/TIMELINE.md, and .github/labels.yml
//! before making any labeling decision — so the taxonomy and milestone names
//! are always derived from what is currently in the repository, not hard-coded.
//!
//! Three operating modes (set by the `MODE` env var):
//!   label         — classify a PR or issue: emit labels, phase, milestone, comment
//!   changelog     — push-to-main: generate a changelog entry and decide if a tag is warranted
//!   milestone-sync — emit the full milestone list to upsert from GOALS.md phases
//!   all           — milestone-sync then label (dispatch default)
//!
//! The binary prints a single JSON object to stdout. The wrapper shell in the
//! GitHub Actions workflow reads that JSON and calls `gh` to apply mutations.
//! The binary itself holds no GH_TOKEN and makes no GitHub API calls.
//!
//! Env vars:
//!   OPENROUTER_API_KEY | LABEL_TAGGER_API_KEY  (required for label/changelog modes)
//!   LABEL_TAGGER_MODEL                          (default: deepseek/deepseek-v4-flash)
//!   OPENROUTER_BASE_URL                         (default: https://openrouter.ai/api/v1)
//!   MODE                                        (label|changelog|milestone-sync|all)
//!   PR_NUMBER                                   (required for label mode on PRs)
//!   ISSUE_NUMBER                                (for label mode on issues; takes priority over PR_NUMBER)
//!   BASE_SHA, HEAD_SHA                          (for diff in label/changelog modes)
//!   GITHUB_REPOSITORY                           (owner/repo)
//!   LANGFUSE_URL, LANGFUSE_API_KEY              (optional; tracing degrades gracefully)
//!   DRY_RUN=1                                   (print JSON without applying any mutations)

mod agent;
mod config;
mod consts;
mod github;
mod goals;
mod guardrails;
mod output;
mod parse;
mod prompts;
mod run;
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
        println!("vaked-label-tagger {VERSION}+{GIT_SHA}");
        return;
    }

    let tracer_provider = setup_tracing();

    let code = match run().await {
        Ok(()) => 0,
        Err(e) => {
                eprintln!("label-tagger: {e:#}");
            // Emit a safe no-op JSON so the shell wrapper never crashes on empty stdout.
            println!("{}", noop_json());
            0
        }
    };

    if let Some(provider) = tracer_provider {
        if let Err(e) = provider.shutdown() {
            eprintln!("label-tagger: telemetry flush failed: {e}");
        }
    }
    std::process::exit(code);
}
