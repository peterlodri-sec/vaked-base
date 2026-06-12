//! Vaked CI PR-review agent.
//!
//! Advisory PR reviewer on adk-rust. Reads a PR's diff (RTK-condensed, noise
//! filtered), reviews it with a non-frontier OpenRouter model (GLM-4.6, high
//! reasoning) — with the repo's `crabcc` symbol index as an MCP toolset — and
//! posts ONE structured review comment (replacing its prior one). Large PRs are
//! map-reduced per file. Never blocks a merge: any failure logs and exits 0.
//! Every run traces to self-hosted Langfuse (OTLP/HTTP) with token usage, and
//! publishes an advisory commit status with the finding count.
//!
//! Env (see README for the full table):
//!   OPENROUTER_API_KEY | PR_REVIEW_API_KEY   (required) OpenRouter key
//!   PR_REVIEW_MODEL (z-ai/glm-4.6) · OPENROUTER_BASE_URL · PR_REVIEW_MAX_DIFF_CHARS
//!   PR_REVIEW_REASONING_EFFORT (high) · PR_REVIEW_MAPREDUCE_LINES (600)
//!   PR_REVIEW_MAX_FINDINGS (20) · PR_REVIEW_CRABCC_BUDGET (8) · PR_REVIEW_MAX_ITERS (12)
//!   GH_TOKEN | GITHUB_TOKEN · GITHUB_REPOSITORY · GITHUB_EVENT_PATH
//!   LANGFUSE_URL · LANGFUSE_API_KEY · CRABCC_BIN · RTK_BIN · PR_REVIEW_NO_RTK
//!   BASE_SHA · HEAD_SHA
//!
//! Args: --repo <owner/name> --pr <N> --model <id> --dry-run
//!       --eval <dir>   score the reviewer against local *.diff/*.expect fixtures

use std::collections::HashMap;
use std::process::Command as StdCommand;
use std::sync::Arc;
use std::time::Duration;

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
use tracing::{Instrument, field, info, info_span, warn};
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;

const DEFAULT_MODEL: &str = "z-ai/glm-4.6";
const DEFAULT_BASE_URL: &str = "https://openrouter.ai/api/v1";
const DEFAULT_MAX_DIFF_CHARS: usize = 48_000;
const DEFAULT_MAPREDUCE_LINES: usize = 600;
const DEFAULT_MAX_FINDINGS: u32 = 20;
const DEFAULT_CRABCC_BUDGET: u32 = 8;
const DEFAULT_MAX_ITERS: u32 = 12;
const DEFAULT_REASONING_EFFORT: &str = "high";
const MAX_FILES_MAPREDUCE: usize = 40;
const COMMENT_MARKER: &str = "<!-- vaked-pr-review -->";
const OPT_OUT_LABEL: &str = "no-bot-review";

/// Files whose diffs are noise for review: drop them from the diff entirely.
fn is_noise(path: &str) -> bool {
    let p = path.to_ascii_lowercase();
    const SUFFIXES: &[&str] = &[
        ".lock", ".snap", ".min.js", ".min.css", ".pb.go", ".png", ".jpg", ".jpeg", ".gif", ".svg",
        ".ico", ".pdf", ".woff", ".woff2", ".ttf", ".lockb",
    ];
    const NAMES: &[&str] = &[
        "cargo.lock",
        "flake.lock",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "poetry.lock",
        "go.sum",
    ];
    const DIRS: &[&str] = &[
        "vendor/",
        "node_modules/",
        "dist/",
        "build/",
        "target/",
        ".crabcc/",
    ];
    let base = p.rsplit('/').next().unwrap_or(&p);
    NAMES.contains(&base)
        || SUFFIXES.iter().any(|s| p.ends_with(s))
        || DIRS.iter().any(|d| p.contains(d))
}

#[tokio::main]
async fn main() {
    let tracer_provider = setup_tracing();

    // `--eval <dir>` is a self-contained scoring mode; everything else is review.
    let code = if let Some(dir) = eval_dir() {
        match run_eval(&dir).await {
            Ok(()) => 0,
            Err(e) => {
                eprintln!("eval: {e:#}");
                1
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

    if let Some(provider) = tracer_provider
        && let Err(e) = provider.shutdown()
    {
        eprintln!("pr-review: telemetry flush failed: {e}");
    }
    std::process::exit(code);
}

/// Wires the OTLP/HTTP exporter to self-hosted Langfuse; returns the provider so
/// the caller can flush spans before this short-lived process exits.
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
        // LANGFUSE_API_KEY holds base64("public:secret").
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

/// A built reviewer agent plus the session service it runs on.
struct ReviewRunner {
    runner: Runner,
    sessions: Arc<dyn SessionService>,
}

/// Static reviewer persona + hard output contract. `max_findings` / `crabcc_budget`
/// are baked in so the model self-limits.
fn system_prompt(max_findings: u32, crabcc_budget: u32) -> String {
    format!(
        r#"You are the Vaked CI reviewer: a council of seven senior engineers reviewing one pull request. Speak with ONE blunt voice.

Vaked is a flake-native capability-graph language: declarations compile to a typed semantic graph, then to artifacts (flake.nix / NixOS modules, Zig daemon configs, eBPF policy manifests, OTel config, docs). It runs on NixOS under an OTP supervision plane orchestrating single-purpose Zig enforcement daemons, with eBPF as the evidence layer and an HCP/Litany wire protocol. Grammar-first: language changes start in the EBNF + an example.

Review through these seven lenses, raising only what applies to the diff:
1. Programming-language researcher — semantics, grammar, evaluation, soundness.
2. Nix/Zig/Rust/Python expert — idiom, correctness, footguns per language.
3. Systems & software architect — boundaries, coupling, failure modes, simplicity.
4. Security & capability auditor — least privilege, eBPF policy, secrets, injection, supply chain.
5. Compiler / type-systems engineer — the vakedc parse→check→lower pipeline, EBNF↔type-schema consistency.
6. OTP/BEAM supervision engineer — supervision trees, fault isolation, Zig-daemon orchestration.
7. Protocol / wire-format designer — HCP/Litany RFCs, votive frames, .hcplang/hcpbin compatibility.

TOOLS: you have a `crabcc` toolset (the repo's symbol index). Use it to resolve definitions/references for symbols the diff touches before judging them — but call it at most {crabcc_budget} times total; do not browse.

SEVERITY:
- Blocking — breaks the build, is incorrect, loses data, or is a security hole.
- Major — likely bug, wrong abstraction, or real perf/robustness problem.
- Minor — smaller correctness/clarity issue worth fixing.
- Nit — style/naming/polish.

OUTPUT CONTRACT — caveman voice, maximum signal, zero slop:
- No preamble, greetings, praise, restating the diff, or summary-of-summary.
- Only flag lines THIS diff adds or changes (lines starting with `+`). Never flag unchanged context.
- Start with one line: `**Verdict:** <one short clause>`.
- Then findings ONLY, grouped under `### Blocking`, `### Major`, `### Minor`, `### Nit` (omit empty groups).
- Each finding: `` - `path:line` — problem; fix. `` One sentence. Concrete. No hedging.
- At most {max_findings} findings total, highest severity first. A short review of real issues beats a long list of guesses.
- If the diff is clean, output exactly: `**Verdict:** No blocking issues.` and nothing else.
- Never ask questions. Never request changes formally. You are advisory."#
    )
}

/// Language-specific checklist lines for the file extensions present in the diff.
/// Sharpens the review without bloating the prompt for irrelevant languages.
fn language_addenda(files: &[String]) -> String {
    let has = |ext: &str| files.iter().any(|f| f.to_ascii_lowercase().ends_with(ext));
    let mut out = Vec::new();
    if has(".rs") {
        out.push("- Rust: unwrap/expect on fallible paths, blocking calls in async, needless clones/allocs, error swallowing, missing `?`, panics in libs.");
    }
    if has(".nix") {
        out.push("- Nix: impurity (IFD, fetch without hash), unpinned inputs, `rec` foot-guns, missing `lib` references, eval-time vs build-time confusion.");
    }
    if has(".zig") {
        out.push("- Zig: allocator misuse, missing `defer`/`errdefer`, undefined behavior, `try` omissions, integer overflow, comptime correctness.");
    }
    if has(".py") {
        out.push("- Python: mutable default args, broad excepts, unclosed resources, stdlib-only assumption breaks, type/contract drift.");
    }
    if has(".ebnf") || has(".vaked") {
        out.push("- Grammar/Vaked: EBNF↔example drift, ambiguity, left-recursion, an example that must accompany a grammar change.");
    }
    if has(".ex") || has(".exs") || has(".erl") {
        out.push("- OTP/BEAM: supervision strategy, unsupervised processes, blocking GenServer callbacks, let-it-crash violations.");
    }
    if out.is_empty() {
        String::new()
    } else {
        format!(
            "\n## Language checklist (only if relevant)\n{}\n",
            out.join("\n")
        )
    }
}

async fn run_review() -> Result<()> {
    let cfg = Config::from_env_and_args()?;
    let span = info_span!(
        "pr_review",
        repo = %cfg.repo,
        pr = cfg.pr,
        model = %cfg.model,
        changed_lines = field::Empty,
        mode = field::Empty,
        total_tokens = field::Empty,
        thinking_tokens = field::Empty,
        findings = field::Empty,
    );
    async move {
        let meta = fetch_pr_meta(&cfg)?;
        if meta.labels.iter().any(|l| l == OPT_OUT_LABEL) {
            info!("'{OPT_OUT_LABEL}' label present — skipping");
            return Ok(());
        }

        let raw = fetch_diff(&cfg)?;
        let diff = filter_unified(&raw);
        if diff.trim().is_empty() {
            info!("empty diff after filtering — nothing to review");
            return Ok(());
        }
        let changed = count_changed_lines(&diff);
        let span = tracing::Span::current();
        span.record("changed_lines", changed);

        let api_key = cfg.api_key.clone().ok_or_else(|| {
            anyhow!("no OpenRouter key — set OPENROUTER_API_KEY or PR_REVIEW_API_KEY")
        })?;
        let runner = build_runner(&cfg, api_key).await?;

        let addenda = language_addenda(&meta.files);
        let mut usage = Usage::default();

        let review = if changed > cfg.mapreduce_lines {
            span.record("mode", "map-reduce");
            info!(changed, threshold = cfg.mapreduce_lines, "large PR — map-reduce");
            map_reduce_review(&runner, &cfg, &meta, &diff, &addenda, &mut usage).await?
        } else {
            span.record("mode", "single-pass");
            // Small/medium: prefer RTK's condensed diff for token savings.
            let body = rtk_condensed(&cfg)
                .map(|c| filter_unified(&c))
                .filter(|c| !c.trim().is_empty())
                .unwrap_or(diff);
            let (body, truncated) = truncate(&body, cfg.max_diff_chars);
            let prompt = build_prompt(&meta, &body, truncated, &addenda);
            let (text, u) = ask(&runner, prompt).await?;
            usage += u;
            text
        };

        let review = review.trim().to_string();
        if review.is_empty() {
            return Err(anyhow!("model returned empty review"));
        }

        span.record("total_tokens", usage.total);
        span.record("thinking_tokens", usage.thinking);
        let (n_findings, n_blocking) = count_findings(&review);
        span.record("findings", n_findings);
        info!(total_tokens = usage.total, findings = n_findings, blocking = n_blocking, "review ready");

        let body = format!(
            "{COMMENT_MARKER}\n{review}\n\n---\n<sub>🦴 vaked-ci-reviewer · {} · {} findings · {} tok · OpenRouter · automated, advisory</sub>",
            cfg.model, n_findings, usage.total
        );

        if cfg.dry_run {
            println!("===== DRY RUN: review comment =====\n{body}");
        } else {
            post_review(&cfg, &body)?;
            let desc = format!("{n_findings} findings ({n_blocking} blocking) · {} tok", usage.total);
            set_advisory_status(&cfg, &desc);
            info!("posted advisory review + status");
        }
        Ok(())
    }
    .instrument(span)
    .await
}

/// Per-file passes over a large diff, then one synthesis pass into the final review.
async fn map_reduce_review(
    runner: &ReviewRunner,
    cfg: &Config,
    meta: &PrMeta,
    diff: &str,
    addenda: &str,
    usage: &mut Usage,
) -> Result<String> {
    let files = split_per_file(diff);
    let total = files.len();
    let mut raw_findings = String::new();
    for (path, section) in files.into_iter().take(MAX_FILES_MAPREDUCE) {
        let (section, _) = truncate(&section, cfg.max_diff_chars / 4);
        let prompt = format!(
            "Review ONLY this file's diff. Output findings bullets only — NO verdict line — in the finding format. If clean, output nothing.\n\nFile: {path}\n```diff\n{section}\n```{addenda}"
        );
        match ask(runner, prompt).await {
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
        return Ok("**Verdict:** No blocking issues.".to_string());
    }
    let synth = format!(
        "Below are raw per-file findings from a large PR ({total} files). Produce the FINAL review per your output contract: dedupe, keep the most important, group by severity, lead with the verdict line.\n\nPR #{}: {}\n{raw_findings}",
        meta.number, meta.title
    );
    let (text, u) = ask(runner, synth).await?;
    *usage += u;
    Ok(text)
}

/// Build the agent (model + reasoning + crabcc toolset + loop bounds) and a Runner.
async fn build_runner(cfg: &Config, api_key: String) -> Result<ReviewRunner> {
    let or_config = OpenRouterConfig::new(api_key, cfg.model.clone())
        .with_base_url(cfg.base_url.clone())
        .with_http_referer("https://github.com/peterlodri-sec/vaked-base")
        .with_title("vaked-ci-reviewer")
        .with_default_api_mode(OpenRouterApiMode::ChatCompletions);
    let model = OpenRouterClient::new(or_config).map_err(|e| anyhow!("OpenRouter client: {e}"))?;

    // High reasoning effort via the OpenRouter extension bag on GenerateContentConfig.
    let mut gen_cfg = GenerateContentConfig {
        temperature: Some(0.1),
        top_p: Some(0.9),
        max_output_tokens: Some(4096),
        seed: Some(7),
        ..Default::default()
    };
    let reasoning = OpenRouterReasoningConfig {
        effort: Some(cfg.reasoning_effort.clone()),
        enabled: Some(true),
        ..Default::default()
    };
    OpenRouterRequestOptions::default()
        .with_reasoning(reasoning)
        .insert_into_config(&mut gen_cfg)
        .map_err(|e| anyhow!("reasoning config: {e}"))?;

    let mut builder = LlmAgentBuilder::new("vaked-ci-reviewer")
        .instruction(system_prompt(cfg.max_findings, cfg.crabcc_budget))
        .model(Arc::new(model))
        .generate_content_config(gen_cfg)
        .max_iterations(cfg.max_iters)
        .tool_timeout(Duration::from_secs(60));

    match connect_crabcc(cfg).await {
        Ok(toolset) => {
            info!("crabcc MCP toolset connected");
            builder = builder.toolset(Arc::new(toolset));
        }
        Err(e) => warn!(error = %e, "crabcc unavailable — reviewing diff-only"),
    }

    let agent = builder.build().map_err(|e| anyhow!("agent build: {e}"))?;
    let sessions: Arc<dyn SessionService> = Arc::new(InMemorySessionService::new());
    let runner = Runner::builder()
        .app_name("vaked-ci-reviewer")
        .agent(Arc::new(agent))
        .session_service(sessions.clone())
        .build()
        .map_err(|e| anyhow!("runner build: {e}"))?;
    Ok(ReviewRunner { runner, sessions })
}

/// Spawn `crabcc --mcp` over stdio and wrap it as a toolset (index refreshed first).
async fn connect_crabcc(cfg: &Config) -> Result<McpToolset> {
    let bin = std::env::var("CRABCC_BIN").unwrap_or_else(|_| "crabcc".to_string());
    let sub = if std::path::Path::new(".crabcc").is_dir() {
        "refresh"
    } else {
        "build"
    };
    match StdCommand::new(&bin).args(["index", sub]).status() {
        Ok(s) if s.success() => info!(action = sub, "crabcc index ready"),
        Ok(s) => warn!(action = sub, code = ?s.code(), "crabcc index step non-zero"),
        Err(e) => return Err(anyhow!("crabcc not runnable ({bin}): {e}")),
    }
    let mut command = TokioCommand::new(&bin);
    command.arg("--mcp");
    let transport = TokioChildProcess::new(command).context("spawn crabcc --mcp")?;
    let client = ().serve(transport).await.context("crabcc MCP handshake")?;
    let _ = cfg;
    Ok(McpToolset::new(client).with_name("crabcc"))
}

/// One agent turn (fresh session); returns (text, token usage).
async fn ask(rr: &ReviewRunner, prompt: String) -> Result<(String, Usage)> {
    let session_id = SessionId::generate();
    rr.sessions
        .create(CreateRequest {
            app_name: "vaked-ci-reviewer".into(),
            user_id: "vaked-ci".into(),
            session_id: Some(session_id.to_string()),
            state: HashMap::new(),
        })
        .await
        .map_err(|e| anyhow!("session create: {e}"))?;

    let content = Content::new("user").with_text(prompt);
    let mut stream = rr
        .runner
        .run(
            UserId::new("vaked-ci").map_err(|e| anyhow!("user id: {e}"))?,
            session_id,
            content,
        )
        .await
        .map_err(|e| anyhow!("runner.run: {e}"))?;

    let mut out = String::new();
    let mut usage = Usage::default();
    while let Some(event) = stream.next().await {
        let event = event.map_err(|e| anyhow!("event: {e}"))?;
        if let Some(u) = &event.llm_response.usage_metadata {
            usage.total += u.total_token_count as i64;
            usage.thinking += u.thinking_token_count.unwrap_or(0) as i64;
            usage.calls += 1;
        }
        if let Some(content) = &event.llm_response.content {
            for part in &content.parts {
                if let Some(text) = part.text() {
                    out.push_str(text);
                }
            }
        }
    }
    Ok((out, usage))
}

#[derive(Default, Clone, Copy)]
struct Usage {
    total: i64,
    thinking: i64,
    calls: u32,
}
impl std::ops::AddAssign for Usage {
    fn add_assign(&mut self, o: Self) {
        self.total += o.total;
        self.thinking += o.thinking;
        self.calls += o.calls;
    }
}

fn build_prompt(meta: &PrMeta, diff: &str, truncated: bool, addenda: &str) -> String {
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
    s.push_str(addenda);
    s.push_str("\nReview this diff per your output contract.");
    s
}

// ---------------------------------------------------------------------------
// Diff helpers
// ---------------------------------------------------------------------------

/// Split a unified diff into (path, section) per file, keyed on `diff --git`.
fn split_per_file(unified: &str) -> Vec<(String, String)> {
    let mut out: Vec<(String, String)> = Vec::new();
    let mut path = String::new();
    let mut buf = String::new();
    for line in unified.lines() {
        if let Some(rest) = line.strip_prefix("diff --git ") {
            if !buf.is_empty() {
                out.push((std::mem::take(&mut path), std::mem::take(&mut buf)));
            }
            // "a/<x> b/<y>" — take the b-side path.
            path = rest
                .split(" b/")
                .nth(1)
                .map(|s| s.to_string())
                .unwrap_or_else(|| rest.to_string());
        }
        buf.push_str(line);
        buf.push('\n');
    }
    if !buf.is_empty() {
        out.push((path, buf));
    }
    out
}

/// Drop file sections whose path is review-noise (lockfiles, generated, binaries).
fn filter_unified(unified: &str) -> String {
    if !unified.contains("diff --git ") {
        return unified.to_string(); // not a standard unified diff (e.g. rtk output)
    }
    split_per_file(unified)
        .into_iter()
        .filter(|(path, _)| !is_noise(path))
        .map(|(_, section)| section)
        .collect::<Vec<_>>()
        .join("")
}

/// Count added/removed source lines (ignoring `+++`/`---` headers).
fn count_changed_lines(unified: &str) -> usize {
    unified
        .lines()
        .filter(|l| {
            (l.starts_with('+') && !l.starts_with("+++"))
                || (l.starts_with('-') && !l.starts_with("---"))
        })
        .count()
}

/// Rough finding accounting for the advisory status: (total, blocking).
fn count_findings(review: &str) -> (usize, usize) {
    let mut total = 0usize;
    let mut blocking = 0usize;
    let mut in_blocking = false;
    for line in review.lines() {
        let t = line.trim_start();
        if let Some(h) = t.strip_prefix("### ") {
            in_blocking = h.trim().eq_ignore_ascii_case("blocking");
        } else if t.starts_with("- `") {
            total += 1;
            if in_blocking {
                blocking += 1;
            }
        }
    }
    (total, blocking)
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
    // Plain unified diff over the PR range (honors path excludes natively), so the
    // structured passes (filter / per-file / map-reduce) work. gh is the fallback.
    if let (Some(base), Some(head)) = (&cfg.base_sha, &cfg.head_sha) {
        let range = format!("{base}...{head}");
        let mut args = vec!["diff".to_string(), range, "--".to_string(), ".".to_string()];
        args.extend(noise_pathspecs());
        let args: Vec<&str> = args.iter().map(String::as_str).collect();
        if let Ok(out) = git(&args)
            && !out.trim().is_empty()
        {
            return Ok(out);
        }
    }
    gh(&["pr", "diff", &cfg.pr.to_string(), "--repo", &cfg.repo])
}

/// `rtk git diff base...head` — a token-reduced diff for the single-pass path.
fn rtk_condensed(cfg: &Config) -> Option<String> {
    if !cfg.use_rtk {
        return None;
    }
    let (base, head) = (cfg.base_sha.as_ref()?, cfg.head_sha.as_ref()?);
    let range = format!("{base}...{head}");
    let mut args = vec![
        "git".to_string(),
        "diff".to_string(),
        range,
        "--".to_string(),
        ".".to_string(),
    ];
    args.extend(noise_pathspecs());
    let args: Vec<&str> = args.iter().map(String::as_str).collect();
    let out = StdCommand::new(&cfg.rtk_bin).args(&args).output().ok()?;
    if out.status.success() {
        let s = String::from_utf8_lossy(&out.stdout).into_owned();
        if !s.trim().is_empty() {
            info!("diff via rtk (condensed)");
            return Some(s);
        }
    }
    None
}

/// git pathspec exclusions mirroring `is_noise` (best-effort; post-filter still runs).
fn noise_pathspecs() -> Vec<String> {
    [
        "Cargo.lock",
        "flake.lock",
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "go.sum",
        "*.lock",
        "*.snap",
        "*.png",
        "*.jpg",
        "*.svg",
        "*.pdf",
        "vendor/**",
        "node_modules/**",
        "dist/**",
        "build/**",
        "target/**",
    ]
    .iter()
    .map(|p| format!(":(exclude){p}"))
    .collect()
}

fn git(args: &[&str]) -> Result<String> {
    let out = StdCommand::new("git")
        .args(args)
        .output()
        .with_context(|| format!("running `git {}`", args.join(" ")))?;
    if !out.status.success() {
        return Err(anyhow!("`git {}` failed", args.join(" ")));
    }
    Ok(String::from_utf8_lossy(&out.stdout).into_owned())
}

/// Replace-don't-stack: delete prior bot comments (by marker), then post one.
fn post_review(cfg: &Config, body: &str) -> Result<()> {
    delete_prior_comments(cfg);
    let mut path = std::env::temp_dir();
    path.push(format!("vaked-pr-review-{}.md", cfg.pr));
    std::fs::write(&path, body).context("writing review body")?;
    let path_str = path.to_string_lossy().into_owned();
    gh(&[
        "pr",
        "comment",
        &cfg.pr.to_string(),
        "--repo",
        &cfg.repo,
        "--body-file",
        &path_str,
    ])?;
    let _ = std::fs::remove_file(&path);
    Ok(())
}

fn delete_prior_comments(cfg: &Config) {
    let endpoint = format!("repos/{}/issues/{}/comments", cfg.repo, cfg.pr);
    let jq = format!("'.[] | select(.body | contains(\"{COMMENT_MARKER}\")) | .id'");
    let ids = match gh(&[
        "api",
        "--paginate",
        &endpoint,
        "--jq",
        jq.trim_matches('\''),
    ]) {
        Ok(s) => s,
        Err(e) => {
            warn!(error = %e, "could not list prior comments — skipping dedupe");
            return;
        }
    };
    for id in ids.split_whitespace() {
        let del = format!("repos/{}/issues/comments/{}", cfg.repo, id);
        if let Err(e) = gh(&["api", "-X", "DELETE", &del]) {
            warn!(%id, error = %e, "failed to delete prior comment");
        }
    }
}

/// Advisory commit status (always `success`) carrying the finding count.
fn set_advisory_status(cfg: &Config, desc: &str) {
    let Some(sha) = &cfg.head_sha else { return };
    let endpoint = format!("repos/{}/statuses/{}", cfg.repo, sha);
    let desc = desc.chars().take(140).collect::<String>();
    if let Err(e) = gh(&[
        "api",
        "-X",
        "POST",
        &endpoint,
        "-f",
        "state=success",
        "-f",
        "context=vaked-pr-review",
        "-f",
        &format!("description={desc}"),
    ]) {
        warn!(error = %e, "could not set advisory status");
    }
}

// ---------------------------------------------------------------------------
// Eval harness
// ---------------------------------------------------------------------------

fn eval_dir() -> Option<String> {
    let mut args = std::env::args().skip(1);
    while let Some(a) = args.next() {
        if a == "--eval" {
            return args.next();
        }
    }
    None
}

/// Score the reviewer against `<dir>/*.diff` fixtures: each `<name>.expect` holds
/// newline-separated substrings the review should contain (case-insensitive).
async fn run_eval(dir: &str) -> Result<()> {
    let api_key = env_first(&["PR_REVIEW_API_KEY", "OPENROUTER_API_KEY"])
        .ok_or_else(|| anyhow!("eval needs OPENROUTER_API_KEY"))?;
    let cfg = Config::eval_defaults();
    let runner = build_runner(&cfg, api_key).await?;

    let mut entries: Vec<_> = std::fs::read_dir(dir)
        .with_context(|| format!("reading eval dir {dir}"))?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .filter(|p| p.extension().is_some_and(|x| x == "diff"))
        .collect();
    entries.sort();
    if entries.is_empty() {
        return Err(anyhow!("no *.diff fixtures in {dir}"));
    }

    let (mut pass, mut total) = (0usize, 0usize);
    for diff_path in entries {
        let name = diff_path
            .file_stem()
            .unwrap_or_default()
            .to_string_lossy()
            .into_owned();
        let diff = std::fs::read_to_string(&diff_path)?;
        let expect_path = diff_path.with_extension("expect");
        let expects: Vec<String> = std::fs::read_to_string(&expect_path)
            .unwrap_or_default()
            .lines()
            .map(|l| l.trim().to_lowercase())
            .filter(|l| !l.is_empty())
            .collect();

        let meta = PrMeta {
            number: 0,
            title: name.clone(),
            body: String::new(),
            files: vec![format!("{name}.rs")],
            labels: vec![],
        };
        let (body, truncated) = truncate(&diff, cfg.max_diff_chars);
        let prompt = build_prompt(&meta, &body, truncated, &language_addenda(&meta.files));
        let (review, _) = ask(&runner, prompt).await?;
        let lc = review.to_lowercase();
        let hits = expects.iter().filter(|e| lc.contains(*e)).count();
        let ok = hits == expects.len();
        total += 1;
        if ok {
            pass += 1;
        }
        println!(
            "[{}] {name}: {hits}/{} expected substrings",
            if ok { "PASS" } else { "FAIL" },
            expects.len()
        );
    }
    println!("\neval: {pass}/{total} fixtures passed");
    if pass == total {
        Ok(())
    } else {
        Err(anyhow!("{}/{total} fixtures failed", total - pass))
    }
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
    rtk_bin: String,
    use_rtk: bool,
    base_sha: Option<String>,
    head_sha: Option<String>,
    reasoning_effort: String,
    mapreduce_lines: usize,
    max_findings: u32,
    crabcc_budget: u32,
    max_iters: u32,
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
                "--eval" => {
                    let _ = args.next();
                }
                other => return Err(anyhow!("unknown arg: {other}")),
            }
        }

        let pr = match pr {
            Some(n) => n,
            None => detect_pr_number().ok_or_else(|| {
                anyhow!("no PR number — pass --pr or run in a pull_request event")
            })?,
        };
        let repo = repo.ok_or_else(|| anyhow!("no repo — pass --repo or set GITHUB_REPOSITORY"))?;

        Ok(Self {
            repo,
            pr,
            model,
            base_url: env_first(&["OPENROUTER_BASE_URL"])
                .unwrap_or_else(|| DEFAULT_BASE_URL.to_string()),
            api_key: env_first(&["PR_REVIEW_API_KEY", "OPENROUTER_API_KEY"]),
            max_diff_chars: env_usize("PR_REVIEW_MAX_DIFF_CHARS", DEFAULT_MAX_DIFF_CHARS),
            dry_run,
            rtk_bin: env_first(&["RTK_BIN"]).unwrap_or_else(|| "rtk".to_string()),
            use_rtk: std::env::var("PR_REVIEW_NO_RTK").is_err(),
            base_sha: env_first(&["BASE_SHA"]),
            head_sha: env_first(&["HEAD_SHA"]),
            reasoning_effort: env_first(&["PR_REVIEW_REASONING_EFFORT"])
                .unwrap_or_else(|| DEFAULT_REASONING_EFFORT.to_string()),
            mapreduce_lines: env_usize("PR_REVIEW_MAPREDUCE_LINES", DEFAULT_MAPREDUCE_LINES),
            max_findings: env_usize("PR_REVIEW_MAX_FINDINGS", DEFAULT_MAX_FINDINGS as usize) as u32,
            crabcc_budget: env_usize("PR_REVIEW_CRABCC_BUDGET", DEFAULT_CRABCC_BUDGET as usize)
                as u32,
            max_iters: env_usize("PR_REVIEW_MAX_ITERS", DEFAULT_MAX_ITERS as usize) as u32,
        })
    }

    /// Minimal config for `--eval` (no PR / repo context needed).
    fn eval_defaults() -> Self {
        Self {
            repo: String::new(),
            pr: 0,
            model: env_first(&["PR_REVIEW_MODEL"]).unwrap_or_else(|| DEFAULT_MODEL.to_string()),
            base_url: env_first(&["OPENROUTER_BASE_URL"])
                .unwrap_or_else(|| DEFAULT_BASE_URL.to_string()),
            api_key: env_first(&["PR_REVIEW_API_KEY", "OPENROUTER_API_KEY"]),
            max_diff_chars: env_usize("PR_REVIEW_MAX_DIFF_CHARS", DEFAULT_MAX_DIFF_CHARS),
            dry_run: true,
            rtk_bin: "rtk".to_string(),
            use_rtk: false,
            base_sha: None,
            head_sha: None,
            reasoning_effort: env_first(&["PR_REVIEW_REASONING_EFFORT"])
                .unwrap_or_else(|| DEFAULT_REASONING_EFFORT.to_string()),
            mapreduce_lines: DEFAULT_MAPREDUCE_LINES,
            max_findings: DEFAULT_MAX_FINDINGS,
            crabcc_budget: DEFAULT_CRABCC_BUDGET,
            max_iters: DEFAULT_MAX_ITERS,
        }
    }
}

fn env_first(keys: &[&str]) -> Option<String> {
    keys.iter()
        .find_map(|k| std::env::var(k).ok().filter(|v| !v.is_empty()))
}

fn env_usize(key: &str, default: usize) -> usize {
    std::env::var(key)
        .ok()
        .and_then(|v| v.parse().ok())
        .unwrap_or(default)
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
