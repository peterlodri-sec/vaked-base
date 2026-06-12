//! Vaked CI PR-review agent.
//!
//! A small, advisory PR reviewer built on adk-rust. It reads a pull request's
//! diff (+ metadata) via `gh`, lets a non-frontier OpenRouter model (GLM-4.6 by
//! default) review it — with the repo's own `crabcc` symbol index wired in as an
//! MCP toolset so the model can look up definitions/references beyond the diff —
//! and posts ONE structured, advisory-only review comment. It never blocks a
//! merge: any failure logs and exits 0.
//!
//! Every run is traced to a self-hosted Langfuse over OTLP/HTTP.
//!
//! Env:
//!   OPENROUTER_API_KEY | PR_REVIEW_API_KEY   (required) OpenRouter key
//!   PR_REVIEW_MODEL                          model id (default z-ai/glm-4.6)
//!   OPENROUTER_BASE_URL                       OpenRouter base (default public)
//!   PR_REVIEW_MAX_DIFF_CHARS                  diff budget (default 48000)
//!   GH_TOKEN | GITHUB_TOKEN                    auth for the `gh` CLI
//!   GITHUB_REPOSITORY / GITHUB_EVENT_PATH     provided by GitHub Actions
//!   LANGFUSE_URL, LANGFUSE_API_KEY            optional tracing (base64 basic token)
//!   CRABCC_BIN                                crabcc binary (default `crabcc`)
//!
//! Args: --repo <owner/name> --pr <N> --model <id> --dry-run

use std::collections::HashMap;
use std::process::Command as StdCommand;
use std::sync::Arc;

use adk_core::{GenerateContentConfig, SessionId, UserId};
use adk_rust::prelude::*;
use adk_rust::session::{CreateRequest, SessionService};
use adk_rust::tool::McpToolset;
use anyhow::{Context, Result, anyhow};
use futures::StreamExt;
use opentelemetry::trace::TracerProvider as _;
use opentelemetry_otlp::{WithExportConfig, WithHttpConfig};
use opentelemetry_sdk::trace::SdkTracerProvider;
use rmcp::ServiceExt;
use rmcp::transport::TokioChildProcess;
use tokio::process::Command as TokioCommand;
use tracing::{Instrument, info, info_span, warn};
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;

const DEFAULT_MODEL: &str = "z-ai/glm-4.6";
const DEFAULT_BASE_URL: &str = "https://openrouter.ai/api/v1";
const DEFAULT_MAX_DIFF_CHARS: usize = 48_000;
const COMMENT_MARKER: &str = "<!-- vaked-pr-review -->";
const OPT_OUT_LABEL: &str = "no-bot-review";

/// The reviewer's persona + hard output contract.
///
/// A seven-hat council (caveman voice) keeps the model focused and on-domain
/// for the Vaked stack; the OUTPUT CONTRACT is what kills the slop.
const SYSTEM_PROMPT: &str = r#"You are the Vaked CI reviewer: a council of seven senior engineers reviewing one pull request. Speak with ONE blunt voice.

Vaked is a flake-native capability-graph language: declarations compile to a typed semantic graph, then to artifacts (flake.nix / NixOS modules, Zig daemon configs, eBPF policy manifests, OTel config, docs). It runs on NixOS under an OTP supervision plane orchestrating single-purpose Zig enforcement daemons, with eBPF as the evidence layer and an HCP/Litany wire protocol. Grammar-first: language changes start in the EBNF + an example.

Review through these seven lenses, but only raise what actually applies to the diff:
1. Programming-language researcher — semantics, grammar, evaluation, soundness.
2. Nix/Zig/Rust/Python expert — idiom, correctness, footguns in each language.
3. Systems & software architect — boundaries, coupling, failure modes, simplicity.
4. Security & capability auditor — least privilege, eBPF policy, secrets, injection, supply chain.
5. Compiler / type-systems engineer — the vakedc parse→check→lower pipeline, EBNF↔type-schema consistency.
6. OTP/BEAM supervision engineer — supervision trees, fault isolation, Zig-daemon orchestration.
7. Protocol / wire-format designer — HCP/Litany RFCs, votive frames, .hcplang/hcpbin compatibility.

You have a `crabcc` toolset (the repo's symbol index). USE IT to resolve definitions/references for symbols touched by the diff before judging them — do not guess at code you can look up.

OUTPUT CONTRACT — caveman voice, maximum signal, zero slop:
- No preamble, no greetings, no praise, no restating the diff, no summary of your summary.
- Start with one line: `**Verdict:** <one short clause>`.
- Then findings ONLY, grouped under `### Blocking`, `### Major`, `### Minor`, `### Nit` (omit empty groups).
- Each finding: `` - `path:line` — problem; fix. `` One sentence. Concrete. No hedging ("might", "consider", "maybe") unless you genuinely cannot tell.
- Only report what you are confident about. A short review of real issues beats a long list of guesses.
- If the diff is clean, output exactly: `**Verdict:** No blocking issues.` and nothing else.
- Never ask questions. Never request changes formally. You are advisory."#;

#[tokio::main]
async fn main() {
    // Telemetry is best-effort; keep the provider so we can flush on exit.
    let tracer_provider = setup_tracing();

    let code = match run_review().instrument(info_span!("pr_review")).await {
        Ok(()) => 0,
        Err(e) => {
            // Advisory contract: log, but never fail the PR check.
            warn!(error = %e, "pr-review failed (advisory — exiting 0)");
            eprintln!("pr-review: {e:#}");
            0
        }
    };

    // Flush spans before the process exits (short-lived CLI).
    if let Some(provider) = tracer_provider
        && let Err(e) = provider.shutdown()
    {
        eprintln!("pr-review: telemetry flush failed: {e}");
    }
    std::process::exit(code);
}

/// Wire a tracing subscriber that exports to self-hosted Langfuse over OTLP/HTTP.
///
/// Returns the provider (so the caller can flush) or `None` when tracing is
/// disabled/unconfigured. adk-rust's own `tracing` spans nest under our root.
fn setup_tracing() -> Option<SdkTracerProvider> {
    let base = std::env::var("LANGFUSE_URL")
        .ok()
        .filter(|s| !s.is_empty())?;
    let token = std::env::var("LANGFUSE_API_KEY")
        .ok()
        .filter(|s| !s.is_empty());

    let endpoint = format!("{}/api/public/otel/v1/traces", base.trim_end_matches('/'));
    let mut headers = HashMap::new();
    if let Some(token) = token {
        // User-chosen scheme: LANGFUSE_API_KEY holds base64("public:secret").
        headers.insert("Authorization".to_string(), format!("Basic {token}"));
    }

    let exporter = match opentelemetry_otlp::SpanExporter::builder()
        .with_http()
        .with_endpoint(&endpoint)
        .with_headers(headers)
        .build()
    {
        Ok(e) => e,
        Err(e) => {
            eprintln!("pr-review: Langfuse exporter init failed, tracing off: {e}");
            return None;
        }
    };

    let resource = opentelemetry_sdk::Resource::builder_empty()
        .with_attributes([opentelemetry::KeyValue::new(
            "service.name",
            "vaked-ci-reviewer",
        )])
        .build();
    let provider = SdkTracerProvider::builder()
        .with_batch_exporter(exporter)
        .with_resource(resource)
        .build();

    let tracer = provider.tracer("vaked-pr-review");
    let filter = tracing_subscriber::EnvFilter::try_from_default_env()
        .unwrap_or_else(|_| tracing_subscriber::EnvFilter::new("info"));
    tracing_subscriber::registry()
        .with(filter)
        .with(tracing_subscriber::fmt::layer().with_writer(std::io::stderr))
        .with(tracing_opentelemetry::layer().with_tracer(tracer))
        .try_init()
        .ok();
    opentelemetry::global::set_tracer_provider(provider.clone());

    info!(langfuse.endpoint = %endpoint, "Langfuse tracing enabled");
    Some(provider)
}

async fn run_review() -> Result<()> {
    let cfg = Config::from_env_and_args()?;
    info!(repo = %cfg.repo, pr = cfg.pr, model = %cfg.model, "starting review");

    // Honour an opt-out label and skip empty diffs early.
    let meta = fetch_pr_meta(&cfg)?;
    if meta.labels.iter().any(|l| l == OPT_OUT_LABEL) {
        info!("'{OPT_OUT_LABEL}' label present — skipping");
        return Ok(());
    }

    let diff = fetch_diff(&cfg)?;
    if diff.trim().is_empty() {
        info!("empty diff — nothing to review");
        return Ok(());
    }
    let (diff, truncated) = truncate(&diff, cfg.max_diff_chars);

    // Build the agent (GLM-4.6 via OpenRouter) + crabcc MCP toolset.
    let api_key = cfg.api_key.clone().ok_or_else(|| {
        anyhow!("no OpenRouter key — set OPENROUTER_API_KEY or PR_REVIEW_API_KEY")
    })?;
    let or_config = OpenRouterConfig::new(api_key, cfg.model.clone())
        .with_base_url(cfg.base_url.clone())
        .with_http_referer("https://github.com/peterlodri-sec/vaked-base")
        .with_title("vaked-ci-reviewer")
        .with_default_api_mode(OpenRouterApiMode::ChatCompletions);
    let model = OpenRouterClient::new(or_config).map_err(|e| anyhow!("OpenRouter client: {e}"))?;

    let gen_cfg = GenerateContentConfig {
        temperature: Some(0.1),
        top_p: Some(0.9),
        max_output_tokens: Some(4096),
        seed: Some(7),
        ..Default::default()
    };

    let mut builder = LlmAgentBuilder::new("vaked-ci-reviewer")
        .instruction(SYSTEM_PROMPT)
        .model(Arc::new(model))
        .generate_content_config(gen_cfg);

    // crabcc as an MCP toolset (best-effort: a missing binary just means
    // diff-only review rather than a hard failure).
    match connect_crabcc(&cfg).await {
        Ok(toolset) => {
            info!("crabcc MCP toolset connected");
            builder = builder.toolset(Arc::new(toolset));
        }
        Err(e) => warn!(error = %e, "crabcc unavailable — reviewing diff-only"),
    }

    let agent = builder.build().map_err(|e| anyhow!("agent build: {e}"))?;

    let prompt = build_prompt(&meta, &diff, truncated);
    let review = run_agent(agent, prompt).await?;
    let review = review.trim();
    if review.is_empty() {
        return Err(anyhow!("model returned empty review"));
    }

    let body = format!(
        "{COMMENT_MARKER}\n{review}\n\n---\n<sub>🦴 vaked-ci-reviewer · {} · OpenRouter · automated, advisory</sub>",
        cfg.model
    );

    if cfg.dry_run {
        println!("===== DRY RUN: review comment =====\n{body}");
    } else {
        post_review(&cfg, &body)?;
        info!("posted advisory review");
    }
    Ok(())
}

/// Spawn `crabcc --mcp` over stdio and wrap it as an adk-rust toolset.
///
/// Refreshes the on-disk `.crabcc/` index first (build if absent, else refresh)
/// so CI runs reuse a cached index instead of rebuilding from scratch.
async fn connect_crabcc(cfg: &Config) -> Result<McpToolset> {
    let bin = std::env::var("CRABCC_BIN").unwrap_or_else(|_| "crabcc".to_string());

    // Index reuse: cheap refresh if `.crabcc/` exists, else a one-time build.
    let index_exists = std::path::Path::new(".crabcc").is_dir();
    let sub = if index_exists { "refresh" } else { "build" };
    match StdCommand::new(&bin).args(["index", sub]).status() {
        Ok(s) if s.success() => info!(action = sub, "crabcc index ready"),
        Ok(s) => warn!(action = sub, code = ?s.code(), "crabcc index step non-zero"),
        Err(e) => return Err(anyhow!("crabcc not runnable ({bin}): {e}")),
    }

    let mut command = TokioCommand::new(&bin);
    command.arg("--mcp");
    let transport = TokioChildProcess::new(command).context("spawn crabcc --mcp")?;
    let client = ().serve(transport).await.context("crabcc MCP handshake")?;
    let _ = cfg; // reserved for future per-repo crabcc scoping
    Ok(McpToolset::new(client).with_name("crabcc"))
}

/// Drive the agent once and concatenate the assistant's text parts.
async fn run_agent(agent: LlmAgent, prompt: String) -> Result<String> {
    let sessions: Arc<dyn SessionService> = Arc::new(InMemorySessionService::new());
    let session_id = SessionId::generate();
    sessions
        .create(CreateRequest {
            app_name: "vaked-ci-reviewer".into(),
            user_id: "vaked-ci".into(),
            session_id: Some(session_id.to_string()),
            state: HashMap::new(),
        })
        .await
        .map_err(|e| anyhow!("session create: {e}"))?;

    let runner = Runner::builder()
        .app_name("vaked-ci-reviewer")
        .agent(Arc::new(agent))
        .session_service(sessions)
        .build()
        .map_err(|e| anyhow!("runner build: {e}"))?;

    let content = Content::new("user").with_text(prompt);
    let mut stream = runner
        .run(
            UserId::new("vaked-ci").map_err(|e| anyhow!("user id: {e}"))?,
            session_id,
            content,
        )
        .await
        .map_err(|e| anyhow!("runner.run: {e}"))?;

    let mut out = String::new();
    while let Some(event) = stream.next().await {
        let event = event.map_err(|e| anyhow!("event: {e}"))?;
        if let Some(content) = &event.llm_response.content {
            for part in &content.parts {
                if let Some(text) = part.text() {
                    out.push_str(text);
                }
            }
        }
    }
    Ok(out)
}

fn build_prompt(meta: &PrMeta, diff: &str, truncated: bool) -> String {
    let mut s = String::new();
    s.push_str(&format!("PR #{}: {}\n\n", meta.number, meta.title));
    if !meta.body.trim().is_empty() {
        s.push_str("## Description\n");
        s.push_str(meta.body.trim());
        s.push_str("\n\n");
    }
    if !meta.files.is_empty() {
        s.push_str(&format!("## Changed files ({})\n", meta.files.len()));
        for f in &meta.files {
            s.push_str(&format!("- {f}\n"));
        }
        s.push('\n');
    }
    s.push_str("## Diff\n```diff\n");
    s.push_str(diff);
    s.push_str("\n```\n");
    if truncated {
        s.push_str("\n(diff truncated to fit the review budget — review what is shown)\n");
    }
    s.push_str("\nReview this diff per your output contract.");
    s
}

// ---------------------------------------------------------------------------
// gh CLI helpers
// ---------------------------------------------------------------------------

fn gh(args: &[&str]) -> Result<String> {
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

struct PrMeta {
    number: u64,
    title: String,
    body: String,
    files: Vec<String>,
    labels: Vec<String>,
}

fn fetch_pr_meta(cfg: &Config) -> Result<PrMeta> {
    let pr = cfg.pr.to_string();
    let raw = gh(&[
        "pr",
        "view",
        &pr,
        "--repo",
        &cfg.repo,
        "--json",
        "title,body,files,labels,number",
    ])?;
    let v: serde_json::Value = serde_json::from_str(&raw).context("parsing gh pr view JSON")?;
    let files = v["files"]
        .as_array()
        .map(|a| {
            a.iter()
                .filter_map(|f| f["path"].as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default();
    let labels = v["labels"]
        .as_array()
        .map(|a| {
            a.iter()
                .filter_map(|l| l["name"].as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default();
    Ok(PrMeta {
        number: v["number"].as_u64().unwrap_or(cfg.pr),
        title: v["title"].as_str().unwrap_or_default().to_string(),
        body: v["body"].as_str().unwrap_or_default().to_string(),
        files,
        labels,
    })
}

fn fetch_diff(cfg: &Config) -> Result<String> {
    gh(&["pr", "diff", &cfg.pr.to_string(), "--repo", &cfg.repo])
}

fn post_review(cfg: &Config, body: &str) -> Result<()> {
    // Write the body to a temp file (avoids arg-length and shell-quoting limits).
    let mut path = std::env::temp_dir();
    path.push(format!("vaked-pr-review-{}.md", cfg.pr));
    std::fs::write(&path, body).context("writing review body")?;
    let path_str = path.to_string_lossy().into_owned();
    gh(&[
        "pr",
        "review",
        &cfg.pr.to_string(),
        "--repo",
        &cfg.repo,
        "--comment",
        "--body-file",
        &path_str,
    ])?;
    let _ = std::fs::remove_file(&path);
    Ok(())
}

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

struct Config {
    repo: String,
    pr: u64,
    model: String,
    base_url: String,
    api_key: Option<String>,
    max_diff_chars: usize,
    dry_run: bool,
}

impl Config {
    fn from_env_and_args() -> Result<Self> {
        let mut repo = std::env::var("GITHUB_REPOSITORY").ok();
        let mut pr: Option<u64> = None;
        let mut model =
            env_first(&["PR_REVIEW_MODEL"]).unwrap_or_else(|| DEFAULT_MODEL.to_string());
        let mut dry_run = false;

        let mut args = std::env::args().skip(1);
        while let Some(a) = args.next() {
            match a.as_str() {
                "--repo" => repo = args.next(),
                "--pr" => pr = args.next().and_then(|v| v.parse().ok()),
                "--model" => {
                    if let Some(v) = args.next() {
                        model = v;
                    }
                }
                "--dry-run" => dry_run = true,
                other => return Err(anyhow!("unknown arg: {other}")),
            }
        }

        let pr = match pr {
            Some(n) => n,
            None => detect_pr_number().ok_or_else(|| {
                anyhow!("no PR number — pass --pr or run inside a pull_request event")
            })?,
        };
        let repo = repo.ok_or_else(|| anyhow!("no repo — pass --repo or set GITHUB_REPOSITORY"))?;

        let max_diff_chars = std::env::var("PR_REVIEW_MAX_DIFF_CHARS")
            .ok()
            .and_then(|v| v.parse().ok())
            .unwrap_or(DEFAULT_MAX_DIFF_CHARS);

        Ok(Self {
            repo,
            pr,
            model,
            base_url: env_first(&["OPENROUTER_BASE_URL"])
                .unwrap_or_else(|| DEFAULT_BASE_URL.to_string()),
            api_key: env_first(&["PR_REVIEW_API_KEY", "OPENROUTER_API_KEY"]),
            max_diff_chars,
            dry_run,
        })
    }
}

fn env_first(keys: &[&str]) -> Option<String> {
    keys.iter()
        .find_map(|k| std::env::var(k).ok().filter(|v| !v.is_empty()))
}

/// PR number from the Actions event payload, else the `refs/pull/<N>/merge` ref.
fn detect_pr_number() -> Option<u64> {
    if let Ok(path) = std::env::var("GITHUB_EVENT_PATH")
        && let Ok(raw) = std::fs::read_to_string(&path)
        && let Ok(v) = serde_json::from_str::<serde_json::Value>(&raw)
    {
        if let Some(n) = v["pull_request"]["number"].as_u64() {
            return Some(n);
        }
        if let Some(n) = v["number"].as_u64() {
            return Some(n);
        }
    }
    let r = std::env::var("GITHUB_REF").ok()?;
    r.strip_prefix("refs/pull/")?
        .split('/')
        .next()?
        .parse()
        .ok()
}

/// Truncate to a char budget on a line boundary; returns (text, was_truncated).
fn truncate(s: &str, max: usize) -> (String, bool) {
    if s.len() <= max {
        return (s.to_string(), false);
    }
    let cut = s[..max].rfind('\n').unwrap_or(max);
    (s[..cut].to_string(), true)
}
