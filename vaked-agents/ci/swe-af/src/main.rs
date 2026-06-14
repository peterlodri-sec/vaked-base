//! Vaked CI swe_af agent.
//!
//! This binary realizes the **plan** and **code** nodes of the lowered
//! `workflow swe_af` declared in `vaked/examples/agentfield-swe.vaked`
//! (`vaked/examples/lowering-agentfield/gen/workflow/swe_af.json`). The workflow
//! is triggered by labeling a GitHub issue `agent`
//! (`on = "github.issue.labeled:agent"`); the GitHub-Actions shell in
//! `.github/workflows/swe-af.yml` drives the DAG (plan → code → review → publish),
//! testifying every step to an eventd hash chain.
//!
//! Two modes (set by the `MODE` env var):
//!   plan  — read the issue + repo context, emit a structured implementation plan.
//!   code  — given the plan, read the target files and emit FULL new file contents.
//!
//! POLA: this binary holds **no** `GH_TOKEN` and performs **no** GitHub writes.
//! It only reads (issue via `gh issue view`, repo files via the read_file tool)
//! and prints a single JSON object to stdout. The workflow shell applies the
//! side effects: `code` writes the files + commits to a branch; the broker step
//! (`gh pr create`) is the only thing that touches GitHub write. This mirrors the
//! mesh in agentfield-swe.vaked, where only `broker` holds `mcp.github_write`.
//!
//! Env vars:
//!   OPENROUTER_API_KEY | SWE_AF_API_KEY   (required; absent ⇒ graceful no-op)
//!   SWE_AF_MODEL                          (default: deepseek/deepseek-v4-flash)
//!   SWE_AF_CODE_MODEL                     (code mode override; default: SWE_AF_MODEL)
//!   OPENROUTER_BASE_URL                   (default: https://openrouter.ai/api/v1)
//!   MODE                                  (plan|code)
//!   ISSUE_NUMBER                          (required)
//!   PLAN_FILE                             (code mode: path to the plan markdown)
//!   GITHUB_REPOSITORY                     (owner/repo)
//!   SWE_AF_MAX_FILES                      (code mode cap; default 20)
//!   LANGFUSE_URL, LANGFUSE_API_KEY        (optional; tracing degrades gracefully)
//!   DRY_RUN=1                             (print JSON without calling the model)

use std::collections::HashMap;
use std::process::Command as StdCommand;
use std::sync::Arc;
use std::time::Duration;

use adk_core::{Content, GenerateContentConfig, SessionId, UserId};
use adk_rust::prelude::*;
use adk_rust::session::{CreateRequest, SessionService};
use adk_rust::{RetryBudget, ToolExecutionStrategy};
use adk_runner::compaction::{CompactionConfig, TruncationCompaction};
use anyhow::{Context, Result, anyhow};
use futures::StreamExt;

use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use tracing::{info, warn};
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;

mod guardrails;

#[global_allocator]
static GLOBAL: mimalloc::MiMalloc = mimalloc::MiMalloc;

// Cheap, tool-call-reliable Gemini-family default (the swe_af loop needs real
// tool calls; deepseek/claude narrate instead). ~6x cheaper than gemini-3.5-flash.
const DEFAULT_MODEL: &str = "google/gemini-3.1-flash-lite";
const DEFAULT_BASE_URL: &str = "https://openrouter.ai/api/v1";
const DEFAULT_MAX_ITERS: u32 = 12;
const COMPACTION_BUDGET_TOKENS: usize = 120_000;
const COMPACTION_PRESERVE_RECENT: usize = 6;
const CACHE_KEY: &str = "vaked-swe-af-v1";
const DEFAULT_MAX_FILES: usize = 20;
const MAX_FILE_CHARS: usize = 64_000;
const MAX_ISSUE_CHARS: usize = 16_000;

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

#[derive(Debug, PartialEq, Clone, Copy)]
enum Mode {
    Plan,
    Code,
}

impl Mode {
    fn from_str(s: &str) -> Self {
        match s.to_ascii_lowercase().trim() {
            "code" => Mode::Code,
            _ => Mode::Plan,
        }
    }
    fn as_str(self) -> &'static str {
        match self {
            Mode::Plan => "plan",
            Mode::Code => "code",
        }
    }
}

struct Config {
    repo: String,
    mode: Mode,
    issue_number: Option<u64>,
    plan_file: Option<String>,
    model: String,
    base_url: String,
    api_key: Option<String>,
    max_iters: u32,
    max_files: usize,
    dry_run: bool,
}

impl Config {
    fn from_env() -> Result<Self> {
        let repo = std::env::var("GITHUB_REPOSITORY")
            .unwrap_or_else(|_| "peterlodri-sec/vaked-base".to_string());
        let mode = Mode::from_str(&std::env::var("MODE").unwrap_or_default());
        let issue_number = std::env::var("ISSUE_NUMBER")
            .ok()
            .and_then(|s| s.parse::<u64>().ok());
        let plan_file = std::env::var("PLAN_FILE").ok().filter(|s| !s.is_empty());
        // Code mode may use a stronger model than plan; fall back to SWE_AF_MODEL.
        let base_model = std::env::var("SWE_AF_MODEL").unwrap_or_else(|_| DEFAULT_MODEL.to_string());
        let model = if mode == Mode::Code {
            std::env::var("SWE_AF_CODE_MODEL").unwrap_or(base_model)
        } else {
            base_model
        };
        let base_url = std::env::var("OPENROUTER_BASE_URL")
            .unwrap_or_else(|_| DEFAULT_BASE_URL.to_string());
        let api_key = std::env::var("SWE_AF_API_KEY")
            .ok()
            .or_else(|| std::env::var("OPENROUTER_API_KEY").ok())
            .filter(|s| !s.is_empty());
        let max_iters = std::env::var("SWE_AF_MAX_ITERS")
            .ok()
            .and_then(|s| s.parse().ok())
            .unwrap_or(DEFAULT_MAX_ITERS);
        let max_files = std::env::var("SWE_AF_MAX_FILES")
            .ok()
            .and_then(|s| s.parse().ok())
            .unwrap_or(DEFAULT_MAX_FILES);
        let dry_run = std::env::var("DRY_RUN")
            .map(|s| s == "1" || s.to_ascii_lowercase() == "true")
            .unwrap_or(false);
        Ok(Config {
            repo, mode, issue_number, plan_file, model, base_url, api_key,
            max_iters, max_files, dry_run,
        })
    }
}

// ---------------------------------------------------------------------------
// Output schemas (one per mode)
// ---------------------------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Default)]
struct PlanOutput {
    /// Markdown implementation plan (becomes the PR body).
    plan: String,
    /// Repo-relative paths the coder should create or modify.
    #[serde(default)]
    target_files: Vec<String>,
    /// One-line summary used as the branch/PR title suffix.
    #[serde(default)]
    summary: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct FileEdit {
    /// Repo-relative path (no '..', no leading '/').
    path: String,
    /// FULL new content of the file (not a diff).
    content: String,
}

#[derive(Debug, Serialize, Deserialize, Default)]
struct CodeOutput {
    /// Full-content writes (create or overwrite). The shell writes each verbatim.
    #[serde(default)]
    files: Vec<FileEdit>,
    /// Conventional-commits message for the change.
    #[serde(default)]
    commit_message: String,
    /// Short notes for the reviewer (limitations, follow-ups).
    #[serde(default)]
    notes: String,
}

fn plan_schema() -> Value {
    json!({
        "type": "object",
        "additionalProperties": false,
        "required": ["plan", "target_files", "summary"],
        "properties": {
            "plan": { "type": "string", "description": "Markdown implementation plan" },
            "target_files": {
                "type": "array",
                "items": { "type": "string" },
                "description": "Repo-relative files to create or modify"
            },
            "summary": { "type": "string", "description": "One-line change summary" }
        }
    })
}

fn code_schema() -> Value {
    json!({
        "type": "object",
        "additionalProperties": false,
        "required": ["files", "commit_message", "notes"],
        "properties": {
            "files": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": false,
                    "required": ["path", "content"],
                    "properties": {
                        "path": { "type": "string" },
                        "content": { "type": "string" }
                    }
                },
                "description": "Full new content per file (create/overwrite)"
            },
            "commit_message": { "type": "string" },
            "notes": { "type": "string" }
        }
    })
}

/// Safe no-op JSON per mode so the shell wrapper never crashes on empty stdout.
fn noop_json(mode: Mode) -> String {
    match mode {
        Mode::Plan => serde_json::to_string(&PlanOutput::default()).unwrap(),
        Mode::Code => serde_json::to_string(&CodeOutput::default()).unwrap(),
    }
}

// ---------------------------------------------------------------------------
// adk-rust runner
// ---------------------------------------------------------------------------

struct AgentRunner {
    runner: Runner,
    sessions: Arc<dyn SessionService>,
}

fn build_runner(cfg: &Config, api_key: &str) -> Result<AgentRunner> {
    let or_config = OpenRouterConfig::new(api_key.to_string(), cfg.model.clone())
        .with_base_url(cfg.base_url.clone())
        .with_http_referer("https://github.com/peterlodri-sec/vaked-base")
        .with_title("vaked-swe-af")
        .with_default_api_mode(OpenRouterApiMode::ChatCompletions);
    let model = OpenRouterClient::new(or_config).map_err(|e| anyhow!("OpenRouter client: {e}"))?;

    // Plans are small; code emits whole files, so it needs a far bigger budget.
    let (schema, max_out, effort) = match cfg.mode {
        Mode::Plan => (plan_schema(), 4096, "medium"),
        Mode::Code => (code_schema(), 16384, "high"),
    };

    let mut gen_cfg = GenerateContentConfig {
        temperature: Some(0.1),
        top_p: Some(0.9),
        max_output_tokens: Some(max_out),
        seed: Some(7),
        response_schema: Some(schema),
        ..Default::default()
    };
    OpenRouterRequestOptions::default()
        .with_reasoning(OpenRouterReasoningConfig {
            effort: Some(effort.to_string()),
            enabled: Some(true),
            ..Default::default()
        })
        .with_prompt_cache_key(CACHE_KEY)
        .with_provider_preferences(OpenRouterProviderPreferences {
            allow_fallbacks: Some(true),
            ..Default::default()
        })
        .insert_into_config(&mut gen_cfg)
        .map_err(|e| anyhow!("OpenRouter options: {e}"))?;

    let agent = LlmAgentBuilder::new("vaked-swe-af")
        .instruction(system_prompt(cfg.mode))
        .model(Arc::new(model))
        .generate_content_config(gen_cfg)
        .max_iterations(cfg.max_iters)
        .tool_timeout(Duration::from_secs(30))
        .tool_execution_strategy(ToolExecutionStrategy::Auto)
        .tool_retry_budget("read_file", RetryBudget {
            max_retries: 2,
            delay: Duration::from_millis(200),
        })
        .tool(read_file_tool())
        .tool(list_dir_tool())
        .input_guardrails(guardrails::input_guardrails())
        .build()
        .map_err(|e| anyhow!("agent build: {e}"))?;

    let sessions: Arc<dyn SessionService> = Arc::new(InMemorySessionService::new());
    let run_config = RunConfig::builder().auto_cache(true).build();
    let runner = Runner::builder()
        .app_name("vaked-swe-af")
        .agent(Arc::new(agent))
        .session_service(sessions.clone())
        .run_config(run_config)
        .context_compaction(CompactionConfig::new(
            Box::new(TruncationCompaction { preserve_recent: COMPACTION_PRESERVE_RECENT }),
            COMPACTION_BUDGET_TOKENS,
        ))
        .build()
        .map_err(|e| anyhow!("runner build: {e}"))?;
    Ok(AgentRunner { runner, sessions })
}

/// One agent turn (fresh session); returns the model's full text response.
async fn ask(rr: &AgentRunner, prompt: String) -> Result<String> {
    let session_id = SessionId::generate();
    rr.sessions
        .create(CreateRequest {
            app_name: "vaked-swe-af".into(),
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

// ---------------------------------------------------------------------------
// Read-only repo tools
// ---------------------------------------------------------------------------

/// Reject paths that escape the repo or are absolute.
fn safe_rel_path(path: &str) -> bool {
    !path.is_empty() && !path.contains("..") && !path.starts_with('/')
}

fn read_file_tool() -> Arc<dyn Tool> {
    Arc::new(
        FunctionTool::new(
            "read_file",
            "Read a full repo-relative file (read-only). Use this to inspect the \
             files you plan to change BEFORE emitting their new content.",
            |_ctx: Arc<dyn ToolContext>, args: Value| async move {
                let path = args.get("path").and_then(Value::as_str).unwrap_or_default().to_string();
                if !safe_rel_path(&path) {
                    return Ok(json!({"error": "path must be repo-relative, no '..', no leading /"}));
                }
                match std::fs::read_to_string(&path) {
                    Ok(t) => Ok(json!({"path": path, "content": t.chars().take(48_000).collect::<String>()})),
                    Err(e) => Ok(json!({"error": format!("read {path}: {e}")})),
                }
            },
        )
        .with_read_only(true)
        .with_concurrency_safe(true),
    )
}

fn list_dir_tool() -> Arc<dyn Tool> {
    Arc::new(
        FunctionTool::new(
            "list_dir",
            "List the entries of a repo-relative directory (read-only). Use to \
             discover file names before reading them.",
            |_ctx: Arc<dyn ToolContext>, args: Value| async move {
                let path = args.get("path").and_then(Value::as_str).unwrap_or(".").to_string();
                if !safe_rel_path(&path) && path != "." {
                    return Ok(json!({"error": "path must be repo-relative, no '..', no leading /"}));
                }
                match std::fs::read_dir(&path) {
                    Ok(rd) => {
                        let mut entries: Vec<String> = rd
                            .filter_map(|e| e.ok())
                            .map(|e| {
                                let name = e.file_name().to_string_lossy().into_owned();
                                if e.path().is_dir() { format!("{name}/") } else { name }
                            })
                            .collect();
                        entries.sort();
                        entries.truncate(400);
                        Ok(json!({"path": path, "entries": entries}))
                    }
                    Err(e) => Ok(json!({"error": format!("list {path}: {e}")})),
                }
            },
        )
        .with_read_only(true)
        .with_concurrency_safe(true),
    )
}

// ---------------------------------------------------------------------------
// System prompts (per mode)
// ---------------------------------------------------------------------------

fn system_prompt(mode: Mode) -> String {
    match mode {
        Mode::Plan => PLAN_SYSTEM.to_string(),
        Mode::Code => CODE_SYSTEM.to_string(),
    }
}

const PLAN_SYSTEM: &str = r#"You are the PLAN node of the Vaked `swe_af` workflow (the `planner` mesh role,
read-only: capabilities fs.repo_ro + mem.recall). Given a GitHub issue, produce a
concrete, minimal implementation plan for the vaked-base monorepo.

## Tools (read-only)
- `list_dir(path)` — discover files in a directory.
- `read_file(path)` — read a repo-relative file.
Call them to ground your plan in the ACTUAL repo layout and existing conventions
(read README.md, CLAUDE.md, and the files you intend to touch). Never invent paths.

## Discipline
- Smallest change that fully resolves the issue. Prefer editing existing files and
  reusing existing utilities over adding new ones.
- Respect repo conventions (grammar-first for language changes; design→plan→impl
  for subsystems). If the issue is a versioned-language change, note that in the plan.
- The plan becomes the PR body — write it for a human reviewer: numbered steps, the
  exact files to change, and how to verify.

## Output contract
Respond ONLY with JSON matching the schema (no prose, no markdown fences):
- `plan`: the markdown plan.
- `target_files`: every repo-relative path the coder will create or modify.
- `summary`: a <=72-char imperative one-liner (used as the PR title).
Keep `target_files` tight and correct — the coder will only edit those files."#;

const CODE_SYSTEM: &str = r#"You are the CODE node of the Vaked `swe_af` workflow (the `coder` mesh role:
capabilities fs.repo_rw + process.spawn_sandboxed + mem.recall). You are given an
issue and an approved plan. Produce the actual change as FULL file contents.

## Tools (read-only)
- `list_dir(path)` and `read_file(path)` — ALWAYS read a file's current content
  before rewriting it, so you preserve everything you are not deliberately changing.

## How to emit changes
For each file you create or modify, return an object `{ "path", "content" }` where
`content` is the COMPLETE new file (NOT a diff, NOT a fragment). The workflow writes
each file verbatim, commits, and opens a PR — so partial content WILL corrupt files.

## Discipline
- Implement exactly the approved plan. Stay within the plan's target files unless a
  change is strictly required elsewhere (then include that file fully too).
- Match the surrounding code's style, naming, and comment density.
- Do not add license headers, unrelated reformatting, or generated artifacts.
- Keep the change minimal and correct. If something in the plan is infeasible, do
  your best partial and explain the gap in `notes`.

## Output contract
Respond ONLY with JSON matching the schema (no prose, no markdown fences):
- `files`: array of `{ path, content }` full-content writes.
- `commit_message`: a conventional-commits message (e.g. `fix(eventd): ...`).
- `notes`: short reviewer notes — limitations, follow-ups, anything you skipped."#;

// ---------------------------------------------------------------------------
// gh helpers (read-only)
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

struct IssueMeta {
    number: u64,
    title: String,
    body: String,
    labels: Vec<String>,
}

fn fetch_issue_meta(cfg: &Config, issue: u64) -> Result<IssueMeta> {
    let issue_s = issue.to_string();
    let raw = gh(&["issue", "view", &issue_s, "--repo", &cfg.repo, "--json", "title,body,labels,number"])?;
    let v: Value = serde_json::from_str(&raw).context("parsing gh issue view JSON")?;
    let labels = v["labels"].as_array().map(|a| {
        a.iter().filter_map(|l| l["name"].as_str().map(String::from)).collect()
    }).unwrap_or_default();
    Ok(IssueMeta {
        number: v["number"].as_u64().unwrap_or(issue),
        title: v["title"].as_str().unwrap_or_default().to_string(),
        body: v["body"].as_str().unwrap_or_default().to_string(),
        labels,
    })
}

fn truncate(s: &str, max: usize) -> String {
    if s.chars().count() <= max {
        s.to_string()
    } else {
        s.chars().take(max).collect::<String>() + "\n…(truncated)…"
    }
}

// ---------------------------------------------------------------------------
// Prompt builders
// ---------------------------------------------------------------------------

fn build_plan_prompt(meta: &IssueMeta) -> String {
    let mut s = String::new();
    s.push_str("# Plan the fix for this issue\n\n");
    s.push_str(&format!("Issue #{}: {}\n", meta.number, guardrails::sanitize_untrusted(&meta.title)));
    if !meta.body.trim().is_empty() {
        s.push_str("\n## Issue body\n");
        s.push_str(&truncate(&guardrails::sanitize_untrusted(meta.body.trim()), MAX_ISSUE_CHARS));
        s.push('\n');
    }
    if !meta.labels.is_empty() {
        s.push_str(&format!("\nLabels: {}\n", meta.labels.join(", ")));
    }
    s.push_str(
        "\nUse list_dir/read_file to ground yourself in the repo (start with README.md \
         and CLAUDE.md), then emit the JSON plan, target_files, and summary.",
    );
    s
}

fn build_code_prompt(meta: &IssueMeta, plan: &str) -> String {
    let mut s = String::new();
    s.push_str("# Implement the approved plan\n\n");
    s.push_str(&format!("Issue #{}: {}\n", meta.number, guardrails::sanitize_untrusted(&meta.title)));
    if !meta.body.trim().is_empty() {
        s.push_str("\n## Issue body\n");
        s.push_str(&truncate(&guardrails::sanitize_untrusted(meta.body.trim()), MAX_ISSUE_CHARS));
        s.push('\n');
    }
    s.push_str("\n## Approved plan\n");
    s.push_str(&truncate(&guardrails::sanitize_untrusted(plan), MAX_ISSUE_CHARS));
    s.push_str(
        "\n\nRead each target file with read_file BEFORE rewriting it, then emit the JSON \
         `files` (full content per file), `commit_message`, and `notes`.",
    );
    s
}

// ---------------------------------------------------------------------------
// Output parsing
// ---------------------------------------------------------------------------

fn strip_fences(s: &str) -> &str {
    let s = s.trim();
    if let Some(rest) = s.strip_prefix("```json").or_else(|| s.strip_prefix("```")) {
        return rest.trim_end_matches("```").trim();
    }
    s
}

fn parse_plan(raw: &str) -> PlanOutput {
    match serde_json::from_str::<PlanOutput>(strip_fences(raw)) {
        Ok(mut out) => {
            out.target_files.retain(|p| safe_rel_path(p));
            out.target_files.truncate(40);
            out
        }
        Err(e) => {
            warn!(error = %e, "failed to parse plan JSON — using noop");
            PlanOutput::default()
        }
    }
}

fn parse_code(raw: &str, max_files: usize) -> CodeOutput {
    match serde_json::from_str::<CodeOutput>(strip_fences(raw)) {
        Ok(mut out) => {
            // Drop unsafe paths and clamp content size; cap the file count.
            out.files.retain(|f| safe_rel_path(&f.path));
            for f in &mut out.files {
                if f.content.chars().count() > MAX_FILE_CHARS {
                    f.content = f.content.chars().take(MAX_FILE_CHARS).collect();
                }
            }
            out.files.truncate(max_files);
            if out.commit_message.trim().is_empty() {
                out.commit_message = "chore(swe_af): apply agent-generated change".to_string();
            }
            out
        }
        Err(e) => {
            warn!(error = %e, "failed to parse code JSON — using noop");
            CodeOutput::default()
        }
    }
}

// ---------------------------------------------------------------------------
// Orchestration
// ---------------------------------------------------------------------------

const VERSION: &str = env!("CARGO_PKG_VERSION");
const GIT_SHA: &str = env!("GIT_SHA");

#[tokio::main]
async fn main() {
    if std::env::args().any(|a| a == "--version" || a == "-V") {
        println!("vaked-swe-af {VERSION}+{GIT_SHA}");
        return;
    }

    let tracer_provider = vaked_telemetry::setup_tracing("vaked-swe-af", "vaked-swe-af");
    let mode = Mode::from_str(&std::env::var("MODE").unwrap_or_default());

    let code = match run().await {
        Ok(()) => 0,
        Err(e) => {
            warn!(error = %e, "swe-af failed (advisory — exiting 0)");
            eprintln!("swe-af: {e:#}");
            // Emit a safe no-op JSON so the shell wrapper never crashes on empty stdout.
            println!("{}", noop_json(mode));
            0
        }
    };

    if let Some(provider) = tracer_provider {
        // Short-lived process: force_flush drains the batch span processor before
        // shutdown, so the run's trace reliably reaches Langfuse instead of being
        // dropped on exit.
        if let Err(e) = provider.force_flush() {
            eprintln!("swe-af: telemetry force_flush failed: {e}");
        }
        if let Err(e) = provider.shutdown() {
            eprintln!("swe-af: telemetry shutdown failed: {e}");
        }
    }
    std::process::exit(code);
}

async fn run() -> Result<()> {
    let cfg = Config::from_env()?;
    let issue = cfg.issue_number
        .ok_or_else(|| anyhow!("swe-af requires ISSUE_NUMBER"))?;
    let api_key = cfg.api_key.as_deref()
        .ok_or_else(|| anyhow!("no OPENROUTER_API_KEY — set it to enable swe_af"))?;

    let meta = fetch_issue_meta(&cfg, issue)?;
    info!(issue = meta.number, mode = cfg.mode.as_str(), "swe-af start");

    match cfg.mode {
        Mode::Plan => {
            let prompt = build_plan_prompt(&meta);
            if cfg.dry_run {
                eprintln!("swe-af: dry-run plan — prompt {} chars", prompt.len());
                println!("{}", noop_json(Mode::Plan));
                return Ok(());
            }
            let runner = build_runner(&cfg, api_key)?;
            let raw = ask(&runner, prompt).await?;
            info!(response_chars = raw.len(), "plan response received");
            println!("{}", serde_json::to_string(&parse_plan(&raw))?);
        }
        Mode::Code => {
            let plan = match &cfg.plan_file {
                Some(p) => std::fs::read_to_string(p)
                    .with_context(|| format!("reading PLAN_FILE {p}"))?,
                None => return Err(anyhow!("code mode requires PLAN_FILE")),
            };
            let prompt = build_code_prompt(&meta, &plan);
            if cfg.dry_run {
                eprintln!("swe-af: dry-run code — prompt {} chars", prompt.len());
                println!("{}", noop_json(Mode::Code));
                return Ok(());
            }
            let runner = build_runner(&cfg, api_key)?;
            let raw = ask(&runner, prompt).await?;
            info!(response_chars = raw.len(), "code response received");
            println!("{}", serde_json::to_string(&parse_code(&raw, cfg.max_files))?);
        }
    }
    Ok(())
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mode_from_str() {
        assert_eq!(Mode::from_str("plan"), Mode::Plan);
        assert_eq!(Mode::from_str("code"), Mode::Code);
        assert_eq!(Mode::from_str(""), Mode::Plan);
        assert_eq!(Mode::from_str("CODE"), Mode::Code);
    }

    #[test]
    fn safe_rel_path_rejects_escapes() {
        assert!(safe_rel_path("vaked/examples/x.vaked"));
        assert!(!safe_rel_path("../etc/passwd"));
        assert!(!safe_rel_path("/etc/passwd"));
        assert!(!safe_rel_path(""));
    }

    #[test]
    fn parse_plan_valid() {
        let j = r#"{"plan":"do x","target_files":["a.md","../bad"],"summary":"fix x"}"#;
        let out = parse_plan(j);
        assert_eq!(out.summary, "fix x");
        assert_eq!(out.target_files, vec!["a.md"]); // ../bad dropped
    }

    #[test]
    fn parse_plan_invalid_is_noop() {
        let out = parse_plan("not json");
        assert!(out.plan.is_empty());
        assert!(out.target_files.is_empty());
    }

    #[test]
    fn parse_code_drops_unsafe_and_defaults_msg() {
        let j = r#"{"files":[{"path":"ok.txt","content":"hi"},{"path":"/abs","content":"x"}],"commit_message":"","notes":""}"#;
        let out = parse_code(j, 20);
        assert_eq!(out.files.len(), 1);
        assert_eq!(out.files[0].path, "ok.txt");
        assert!(!out.commit_message.is_empty()); // defaulted
    }

    #[test]
    fn parse_code_strips_fences() {
        let j = "```json\n{\"files\":[],\"commit_message\":\"x\",\"notes\":\"\"}\n```";
        let out = parse_code(j, 20);
        assert!(out.files.is_empty());
        assert_eq!(out.commit_message, "x");
    }

    #[test]
    fn noop_json_valid_both_modes() {
        for m in [Mode::Plan, Mode::Code] {
            let v: Value = serde_json::from_str(&noop_json(m)).unwrap();
            assert!(v.is_object());
        }
    }

    #[test]
    fn truncate_clips() {
        assert_eq!(truncate("hello", 100), "hello");
        assert!(truncate("hello world", 5).starts_with("hello"));
    }
}
