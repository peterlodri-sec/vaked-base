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
use opentelemetry::trace::TracerProvider as _;
use opentelemetry_otlp::{WithExportConfig, WithHttpConfig};
use opentelemetry_sdk::trace::SdkTracerProvider;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use tracing::{info, warn};
use tracing_subscriber::layer::SubscriberExt;
use tracing_subscriber::util::SubscriberInitExt;

mod guardrails;

#[global_allocator]
static GLOBAL: mimalloc::MiMalloc = mimalloc::MiMalloc;

const DEFAULT_MODEL: &str = "deepseek/deepseek-v4-flash";
const DEFAULT_BASE_URL: &str = "https://openrouter.ai/api/v1";
const DEFAULT_MAX_ITERS: u32 = 8;
const COMPACTION_BUDGET_TOKENS: usize = 80_000;
const COMPACTION_PRESERVE_RECENT: usize = 4;
const CACHE_KEY: &str = "vaked-provost-v1";
const EPIC_LABEL: &str = "type/epic";
const RFC_DIR: &str = "protocol/rfcs";
const SPEC_DIR: &str = "docs/superpowers/specs";
const PLAN_DIR: &str = "docs/superpowers/plans";
const MAX_ISSUES: usize = 100;

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

#[derive(Debug, PartialEq, Clone)]
enum Mode {
    All,
    Rfc,
    Epic,
    Link,
}

impl Mode {
    fn from_str(s: &str) -> Self {
        match s.to_ascii_lowercase().trim() {
            "rfc" => Mode::Rfc,
            "epic" => Mode::Epic,
            "link" => Mode::Link,
            _ => Mode::All,
        }
    }

    fn as_str(&self) -> &'static str {
        match self {
            Mode::All => "all",
            Mode::Rfc => "rfc",
            Mode::Epic => "epic",
            Mode::Link => "link",
        }
    }
}

struct Config {
    repo: String,
    mode: Mode,
    model: String,
    base_url: String,
    api_key: Option<String>,
    max_iters: u32,
}

impl Config {
    fn from_env() -> Result<Self> {
        let repo = std::env::var("GITHUB_REPOSITORY")
            .unwrap_or_else(|_| "peterlodri-sec/vaked-base".to_string());
        let mode = Mode::from_str(&std::env::var("MODE").unwrap_or_default());
        let model =
            std::env::var("PROVOST_MODEL").unwrap_or_else(|_| DEFAULT_MODEL.to_string());
        let base_url = std::env::var("OPENROUTER_BASE_URL")
            .unwrap_or_else(|_| DEFAULT_BASE_URL.to_string());
        let api_key = std::env::var("PROVOST_API_KEY")
            .ok()
            .or_else(|| std::env::var("OPENROUTER_API_KEY").ok())
            .filter(|s| !s.is_empty());
        let max_iters = std::env::var("PROVOST_MAX_ITERS")
            .ok()
            .and_then(|s| s.parse().ok())
            .unwrap_or(DEFAULT_MAX_ITERS);
        Ok(Config { repo, mode, model, base_url, api_key, max_iters })
    }
}

// ---------------------------------------------------------------------------
// Output schema (the JSON contract the workflow shell consumes)
// ---------------------------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Default)]
struct ProvostOutput {
    /// Auto-applied: label add/remove on existing issues.
    #[serde(default)]
    label_ops: Vec<LabelOp>,
    /// Auto-applied: native sub-issue parent↔child links.
    #[serde(default)]
    link_ops: Vec<LinkOp>,
    /// Auto-applied: assign an EXISTING milestone to an issue.
    #[serde(default)]
    milestone_ops: Vec<MilestoneOp>,
    /// Surfaced: proposed RFC index entries (rendered into the coordination issue).
    #[serde(default)]
    rfc_index_ops: Vec<RfcIndexOp>,
    /// Surfaced: proposed new epics (checklist in the coordination issue).
    #[serde(default)]
    proposed_epics: Vec<ProposedEpic>,
    /// Surfaced: proposed new issues (checklist in the coordination issue).
    #[serde(default)]
    proposed_issues: Vec<ProposedIssue>,
    /// Surfaced: proposed new RFC stubs (written to the coordination PR).
    #[serde(default)]
    proposed_rfcs: Vec<ProposedRfc>,
    /// Note for a human: milestones referenced but absent (run label-tagger milestone-sync).
    #[serde(default)]
    missing_milestones: Vec<String>,
    /// Complete markdown body for the coordination issue (LLM-authored).
    #[serde(default)]
    summary: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct LabelOp {
    issue: u64,
    #[serde(default)]
    add: Vec<String>,
    #[serde(default)]
    remove: Vec<String>,
}

#[derive(Debug, Serialize, Deserialize)]
struct LinkOp {
    parent_issue: u64,
    child_issue: u64,
}

#[derive(Debug, Serialize, Deserialize)]
struct MilestoneOp {
    issue: u64,
    milestone_title: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct RfcIndexOp {
    rfc_file: String,
    title: String,
    status: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct ProposedEpic {
    title: String,
    #[serde(default)]
    body: String,
    #[serde(default)]
    labels: Vec<String>,
    #[serde(default)]
    milestone: Option<String>,
    #[serde(default)]
    children: Vec<u64>,
}

#[derive(Debug, Serialize, Deserialize)]
struct ProposedIssue {
    title: String,
    #[serde(default)]
    body: String,
    #[serde(default)]
    labels: Vec<String>,
    #[serde(default)]
    epic: Option<u64>,
}

#[derive(Debug, Serialize, Deserialize)]
struct ProposedRfc {
    number: String,
    slug: String,
    title: String,
    #[serde(default)]
    track: String,
    #[serde(default)]
    rationale: String,
}

/// JSON schema for the LLM structured output.
fn output_schema() -> Value {
    json!({
        "type": "object",
        "additionalProperties": false,
        "required": [
            "label_ops", "link_ops", "milestone_ops", "rfc_index_ops",
            "proposed_epics", "proposed_issues", "proposed_rfcs",
            "missing_milestones", "summary"
        ],
        "properties": {
            "label_ops": {
                "type": "array",
                "description": "Label add/remove on existing issues (safe-sync)",
                "items": {
                    "type": "object",
                    "additionalProperties": false,
                    "required": ["issue", "add", "remove"],
                    "properties": {
                        "issue": { "type": "integer" },
                        "add": { "type": "array", "items": { "type": "string" } },
                        "remove": { "type": "array", "items": { "type": "string" } }
                    }
                }
            },
            "link_ops": {
                "type": "array",
                "description": "Native sub-issue parent↔child links (safe-sync)",
                "items": {
                    "type": "object",
                    "additionalProperties": false,
                    "required": ["parent_issue", "child_issue"],
                    "properties": {
                        "parent_issue": { "type": "integer" },
                        "child_issue": { "type": "integer" }
                    }
                }
            },
            "milestone_ops": {
                "type": "array",
                "description": "Assign an EXISTING milestone to an issue (safe-sync)",
                "items": {
                    "type": "object",
                    "additionalProperties": false,
                    "required": ["issue", "milestone_title"],
                    "properties": {
                        "issue": { "type": "integer" },
                        "milestone_title": { "type": "string" }
                    }
                }
            },
            "rfc_index_ops": {
                "type": "array",
                "description": "Proposed RFC index rows (surfaced in coordination issue)",
                "items": {
                    "type": "object",
                    "additionalProperties": false,
                    "required": ["rfc_file", "title", "status"],
                    "properties": {
                        "rfc_file": { "type": "string" },
                        "title": { "type": "string" },
                        "status": { "type": "string" }
                    }
                }
            },
            "proposed_epics": {
                "type": "array",
                "description": "Proposed new epics (surfaced for human approval)",
                "items": {
                    "type": "object",
                    "additionalProperties": false,
                    "required": ["title", "body", "labels", "milestone", "children"],
                    "properties": {
                        "title": { "type": "string" },
                        "body": { "type": "string" },
                        "labels": { "type": "array", "items": { "type": "string" } },
                        "milestone": { "type": ["string", "null"] },
                        "children": { "type": "array", "items": { "type": "integer" } }
                    }
                }
            },
            "proposed_issues": {
                "type": "array",
                "description": "Proposed new issues (surfaced for human approval)",
                "items": {
                    "type": "object",
                    "additionalProperties": false,
                    "required": ["title", "body", "labels", "epic"],
                    "properties": {
                        "title": { "type": "string" },
                        "body": { "type": "string" },
                        "labels": { "type": "array", "items": { "type": "string" } },
                        "epic": { "type": ["integer", "null"] }
                    }
                }
            },
            "proposed_rfcs": {
                "type": "array",
                "description": "Proposed new RFC stubs (surfaced via coordination PR)",
                "items": {
                    "type": "object",
                    "additionalProperties": false,
                    "required": ["number", "slug", "title", "track", "rationale"],
                    "properties": {
                        "number": { "type": "string" },
                        "slug": { "type": "string" },
                        "title": { "type": "string" },
                        "track": { "type": "string" },
                        "rationale": { "type": "string" }
                    }
                }
            },
            "missing_milestones": {
                "type": "array",
                "items": { "type": "string" },
                "description": "Milestones referenced but absent in the repo"
            },
            "summary": {
                "type": "string",
                "description": "Complete markdown body for the coordination issue"
            }
        }
    })
}

/// The empty fallback emitted when anything goes wrong (advisory — never block CI).
fn noop_json() -> String {
    serde_json::to_string(&ProvostOutput::default()).unwrap()
}

// ---------------------------------------------------------------------------
// Tracing (identical pattern to label-tagger / pr-review)
// ---------------------------------------------------------------------------

fn setup_tracing() -> Option<SdkTracerProvider> {
    let base = std::env::var("LANGFUSE_URL").ok().filter(|s| !s.is_empty())?;
    let token = std::env::var("LANGFUSE_API_KEY").ok().filter(|s| !s.is_empty());
    let endpoint = format!("{}/api/public/otel/v1/traces", base.trim_end_matches('/'));
    let mut headers = HashMap::new();
    if let Some(token) = token {
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
            eprintln!("provost: Langfuse exporter init failed: {e}");
            return None;
        }
    };
    let resource = opentelemetry_sdk::Resource::builder_empty()
        .with_attributes([opentelemetry::KeyValue::new("service.name", "vaked-provost")])
        .build();
    let provider = SdkTracerProvider::builder()
        .with_batch_exporter(exporter)
        .with_resource(resource)
        .build();
    let tracer = provider.tracer("vaked-provost");
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

// ---------------------------------------------------------------------------
// adk-rust runner
// ---------------------------------------------------------------------------

struct ProvostRunner {
    runner: Runner,
    sessions: Arc<dyn SessionService>,
}

fn build_runner(cfg: &Config, api_key: &str) -> Result<ProvostRunner> {
    let or_config = OpenRouterConfig::new(api_key.to_string(), cfg.model.clone())
        .with_base_url(cfg.base_url.clone())
        .with_http_referer("https://github.com/peterlodri-sec/vaked-base")
        .with_title("vaked-provost")
        .with_default_api_mode(OpenRouterApiMode::ChatCompletions);
    let model = OpenRouterClient::new(or_config).map_err(|e| anyhow!("OpenRouter client: {e}"))?;

    let mut gen_cfg = GenerateContentConfig {
        temperature: Some(0.1),
        top_p: Some(0.9),
        max_output_tokens: Some(2048),
        seed: Some(42),
        response_schema: Some(output_schema()),
        ..Default::default()
    };
    OpenRouterRequestOptions::default()
        .with_reasoning(OpenRouterReasoningConfig {
            effort: Some("medium".to_string()),
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

    let agent = LlmAgentBuilder::new("vaked-provost")
        .instruction(system_prompt())
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
        .input_guardrails(guardrails::input_guardrails())
        .build()
        .map_err(|e| anyhow!("agent build: {e}"))?;

    let sessions: Arc<dyn SessionService> = Arc::new(InMemorySessionService::new());
    let run_config = RunConfig::builder().auto_cache(true).build();
    let runner = Runner::builder()
        .app_name("vaked-provost")
        .agent(Arc::new(agent))
        .session_service(sessions.clone())
        .run_config(run_config)
        .context_compaction(CompactionConfig::new(
            Box::new(TruncationCompaction { preserve_recent: COMPACTION_PRESERVE_RECENT }),
            COMPACTION_BUDGET_TOKENS,
        ))
        .build()
        .map_err(|e| anyhow!("runner build: {e}"))?;
    Ok(ProvostRunner { runner, sessions })
}

/// One agent turn (fresh session); returns the model's full text response.
async fn ask(rr: &ProvostRunner, prompt: String) -> Result<String> {
    let session_id = SessionId::generate();
    rr.sessions
        .create(CreateRequest {
            app_name: "vaked-provost".into(),
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
// read_file tool
// ---------------------------------------------------------------------------

fn read_file_tool() -> Arc<dyn Tool> {
    Arc::new(
        FunctionTool::new(
            "read_file",
            "Read a full repo-relative file (read-only). Use this to read GOALS.md, \
             docs/context/TIMELINE.md, .github/labels.yml, and docs/protocol/README.md \
             before making coordination decisions, and to read any specific RFC or spec.",
            |_ctx: Arc<dyn ToolContext>, args: Value| async move {
                let path = args
                    .get("path")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string();
                if path.is_empty() || path.contains("..") || path.starts_with('/') {
                    return Ok(json!({"error": "path must be repo-relative, no '..', no leading /"}));
                }
                match std::fs::read_to_string(&path) {
                    Ok(t) => Ok(json!({"path": path, "content": t.chars().take(32_000).collect::<String>()})),
                    Err(e) => Ok(json!({"error": format!("read {path}: {e}")})),
                }
            },
        )
        .with_read_only(true)
        .with_concurrency_safe(true),
    )
}

// ---------------------------------------------------------------------------
// System prompt (doc-grounded)
// ---------------------------------------------------------------------------

fn system_prompt() -> String {
    r#"You are the Vaked CI provost: the product-owner / coordination agent for the
vaked-base monorepo. Your job is to keep the project graph coherent — epics, the
RFC process, issues, milestones, and the links between them — always grounded in
the CURRENT repository docs. You are advisory and you NEVER block CI.

## Tools you MUST call first

`read_file(path)` — read a repo file. Before deciding ANYTHING, read:
1. `GOALS.md` — the 6 phases (0–5). Each `### Phase N — Title` heading is a
   milestone and the natural anchor for an epic.
2. `docs/context/TIMELINE.md` — current posture (✅ done / 🟡 in progress /
   🟦 stub / ⬜ planned).
3. `.github/labels.yml` — the COMPLETE label taxonomy. Only use labels whose
   `name:` appears verbatim here. NEVER invent labels.
4. `docs/protocol/README.md` — the RFC overview + vocabulary; the RFC index lives
   here. Use the established protocol vocabulary exactly.

The user message gives you a pre-scanned catalog of the RFC series, the design
specs/plans, and current GitHub state (open issues, milestones, epics). Reason
from that catalog plus the files you read.

## The safety boundary (critical)

Split every action into one of two buckets:

AUTO-APPLIED — reversible GitHub *metadata* only. Put these in the structured op
arrays; the workflow applies them directly:
- `label_ops`   — add/remove labels on EXISTING open issues (e.g. backfill a
  missing `area/*` or `phase/*`, or add `type/epic` to an issue that is an epic).
- `link_ops`    — link a child issue under its parent epic (native sub-issues).
  Only link when the catalog clearly shows the child belongs to that epic (e.g.
  a spec says "Track B of the 1.0 epic (#17), issue #18" ⇒ link #18 under #17).
- `milestone_ops` — assign an EXISTING milestone (one whose title is in the
  catalog's milestone list) to an issue. If the milestone does not exist, DO NOT
  invent it — add its title to `missing_milestones` instead.

SURFACED FOR APPROVAL — anything that creates content or new objects. NEVER apply
these yourself; describe them so a human can approve:
- `proposed_epics`  — new epic issues warranted by a GOALS.md phase or a major
  design spec that has no epic yet.
- `proposed_issues` — new tracking issues for design specs/plans that lack one.
- `proposed_rfcs`   — new RFC stubs ONLY when a protocol design spec exists with
  no corresponding RFC. Use sequential zero-padded numbers after the highest
  existing RFC. Honor the RFC vocabulary and Track.
- `rfc_index_ops`   — the rows the RFC index in docs/protocol/README.md SHOULD
  contain (one per existing RFC: file, title, status from its front-matter).

## Rules

- Be conservative. Prefer a small, correct plan over a large speculative one.
- Never propose closing or deleting anything. You only add and link.
- Do not duplicate label-tagger's job: do NOT create milestones and do NOT label
  individual PRs. You operate at the epic / RFC / cross-link layer.
- An issue is an epic if it carries the `type/epic` label OR the catalog marks it
  as one. The "1.0 epic" is issue #17.
- Only emit links/labels for issue numbers that appear in the catalog.

## `summary` field

Write `summary` as the COMPLETE markdown body for the coordination issue. Include:
- a one-paragraph status of the project graph;
- a checklist of `proposed_epics` and `proposed_issues` (each `- [ ] ...`);
- a checklist of `proposed_rfcs` if any;
- a "Proposed RFC index" table built from `rfc_index_ops`;
- a "Missing milestones" note if `missing_milestones` is non-empty (tell the
  reader to run the label-tagger `milestone-sync` workflow).
Keep it blunt and factual. This is the human's single pane of glass.

## Output contract

Respond ONLY with JSON matching the schema. No prose, no markdown fences.
Every array must be present (use [] when empty). On uncertainty, prefer fewer
ops and explain the gap in `summary`."#
        .to_string()
}

// ---------------------------------------------------------------------------
// gh / git helpers
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

// ---------------------------------------------------------------------------
// Pre-scan: RFC series, specs/plans, GitHub state
// ---------------------------------------------------------------------------

#[derive(Debug, Clone)]
struct RfcMeta {
    file: String,
    title: String,
    status: String,
    track: String,
}

/// Strip markdown list/bold markers and split a "Key: Value" line.
fn md_kv(line: &str) -> Option<(String, String)> {
    let t = line.trim().trim_start_matches('-').trim();
    let t = t.replace("**", "");
    let (k, v) = t.split_once(':')?;
    Some((k.trim().to_ascii_lowercase(), v.trim().to_string()))
}

fn parse_rfc_front(text: &str, file: &str) -> RfcMeta {
    let mut title = String::new();
    let mut status = String::new();
    let mut track = String::new();
    for line in text.lines().take(40) {
        let t = line.trim();
        if title.is_empty() {
            if let Some(h) = t.strip_prefix("# ") {
                title = h.trim().to_string();
            }
        }
        if let Some((k, v)) = md_kv(t) {
            match k.as_str() {
                "status" if status.is_empty() => status = v,
                "track" if track.is_empty() => track = v,
                _ => {}
            }
        }
    }
    RfcMeta {
        file: file.to_string(),
        title: if title.is_empty() { file.to_string() } else { title },
        status: if status.is_empty() { "Unknown".to_string() } else { status },
        track,
    }
}

fn scan_rfcs() -> Vec<RfcMeta> {
    let mut rfcs = Vec::new();
    let Ok(entries) = std::fs::read_dir(RFC_DIR) else {
        return rfcs;
    };
    let mut paths: Vec<String> = entries
        .filter_map(|e| e.ok())
        .map(|e| e.path().to_string_lossy().into_owned())
        .filter(|p| p.ends_with(".md") && !p.ends_with("README.md"))
        .collect();
    paths.sort();
    for p in paths {
        if let Ok(text) = std::fs::read_to_string(&p) {
            rfcs.push(parse_rfc_front(&text, &p));
        }
    }
    rfcs
}

#[derive(Debug, Clone)]
struct SpecMeta {
    file: String,
    title: String,
    issue_refs: Vec<u64>,
}

/// Pull `#NNN` issue references out of text.
fn extract_issue_refs(text: &str) -> Vec<u64> {
    let bytes = text.as_bytes();
    let mut refs = Vec::new();
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'#' {
            let mut j = i + 1;
            let mut n: u64 = 0;
            let mut any = false;
            while j < bytes.len() && bytes[j].is_ascii_digit() {
                n = n.saturating_mul(10).saturating_add((bytes[j] - b'0') as u64);
                j += 1;
                any = true;
            }
            if any {
                refs.push(n);
            }
            i = j;
        } else {
            i += 1;
        }
    }
    refs.sort_unstable();
    refs.dedup();
    refs
}

fn scan_specs_in(dir: &str) -> Vec<SpecMeta> {
    let mut specs = Vec::new();
    let Ok(entries) = std::fs::read_dir(dir) else {
        return specs;
    };
    let mut paths: Vec<String> = entries
        .filter_map(|e| e.ok())
        .map(|e| e.path().to_string_lossy().into_owned())
        .filter(|p| p.ends_with(".md") && !p.ends_with("README.md"))
        .collect();
    paths.sort();
    for p in paths {
        if let Ok(text) = std::fs::read_to_string(&p) {
            let title = text
                .lines()
                .find_map(|l| l.trim().strip_prefix("# ").map(|h| h.trim().to_string()))
                .unwrap_or_else(|| p.clone());
            // Issue refs from the top of the file (the status block).
            let head: String = text.lines().take(15).collect::<Vec<_>>().join("\n");
            specs.push(SpecMeta {
                file: p.clone(),
                title,
                issue_refs: extract_issue_refs(&head),
            });
        }
    }
    specs
}

fn scan_specs() -> Vec<SpecMeta> {
    let mut all = scan_specs_in(SPEC_DIR);
    all.extend(scan_specs_in(PLAN_DIR));
    all
}

#[derive(Debug, Default)]
struct GhState {
    issues: Vec<IssueLite>,
    milestones: Vec<String>,
}

#[derive(Debug)]
struct IssueLite {
    number: u64,
    title: String,
    labels: Vec<String>,
    milestone: Option<String>,
    is_epic: bool,
}

fn fetch_gh_state(cfg: &Config) -> GhState {
    let mut state = GhState::default();

    // Open issues — jq-projected to only the fields we use, so the wire payload
    // is ~90% smaller than fetching full issue JSON.
    let limit = MAX_ISSUES.to_string();
    let jq = r#"[.[] | {number, title, labels: [.labels[].name], milestone: .milestone.title}]"#;
    if let Ok(raw) = gh(&[
        "issue", "list", "--repo", &cfg.repo, "--state", "open",
        "--limit", &limit, "--json", "number,title,labels,milestone",
        "--jq", jq,
    ]) {
        if let Ok(Value::Array(arr)) = serde_json::from_str::<Value>(&raw) {
            for v in arr {
                let labels: Vec<String> = v["labels"]
                    .as_array()
                    .map(|a| a.iter().filter_map(|l| l.as_str().map(String::from)).collect())
                    .unwrap_or_default();
                let milestone = v["milestone"].as_str().map(String::from);
                let is_epic = labels.iter().any(|l| l == EPIC_LABEL);
                state.issues.push(IssueLite {
                    number: v["number"].as_u64().unwrap_or(0),
                    title: v["title"].as_str().unwrap_or_default().to_string(),
                    labels,
                    milestone,
                    is_epic,
                });
            }
        }
    } else {
        eprintln!("provost: could not list issues (no GH_TOKEN?) — proceeding with empty issue set");
    }

    // Milestone titles.
    let endpoint = format!("repos/{}/milestones", cfg.repo);
    if let Ok(raw) = gh(&["api", &endpoint, "--jq", ".[].title"]) {
        state.milestones = raw.lines().map(|l| l.trim().to_string()).filter(|l| !l.is_empty()).collect();
    }

    state
}

// ---------------------------------------------------------------------------
// Prompt builder
// ---------------------------------------------------------------------------

fn build_reconcile_prompt(cfg: &Config, rfcs: &[RfcMeta], specs: &[SpecMeta], gh: &GhState) -> String {
    let mut s = String::new();
    s.push_str(&format!("# Reconcile the project graph (mode: {})\n\n", cfg.mode.as_str()));
    match cfg.mode {
        Mode::Rfc => s.push_str("Focus on the RFC process: index rows, status, and tracking issues for RFCs. Leave epics/links unless trivially correct.\n\n"),
        Mode::Epic => s.push_str("Focus on epics: propose missing epics and link child issues to their epic. Leave RFC index unless trivially correct.\n\n"),
        Mode::Link => s.push_str("Focus ONLY on the safe-sync subset: label_ops, link_ops, milestone_ops. Leave all proposed_* arrays empty.\n\n"),
        Mode::All => s.push_str("Full reconciliation across epics, the RFC process, and cross-links.\n\n"),
    }

    s.push_str("## RFC series (protocol/rfcs/)\n");
    if rfcs.is_empty() {
        s.push_str("(none found)\n");
    } else {
        for r in rfcs {
            s.push_str(&format!(
                "- `{}` — {} [Status: {}{}]\n",
                r.file,
                guardrails::sanitize_untrusted(&r.title),
                r.status,
                if r.track.is_empty() { String::new() } else { format!(", Track: {}", r.track) },
            ));
        }
    }

    s.push_str("\n## Design specs & plans (docs/superpowers/)\n");
    if specs.is_empty() {
        s.push_str("(none found)\n");
    } else {
        for sp in specs {
            let refs = if sp.issue_refs.is_empty() {
                "no issue refs".to_string()
            } else {
                format!("refs: {}", sp.issue_refs.iter().map(|n| format!("#{n}")).collect::<Vec<_>>().join(" "))
            };
            s.push_str(&format!("- `{}` — {} ({})\n", sp.file, guardrails::sanitize_untrusted(&sp.title), refs));
        }
    }

    s.push_str("\n## Open issues\n");
    if gh.issues.is_empty() {
        s.push_str("(none / unavailable)\n");
    } else {
        for i in &gh.issues {
            let ms = i.milestone.as_deref().unwrap_or("—");
            s.push_str(&format!(
                "- #{}{} {} [labels: {}] [milestone: {}]\n",
                i.number,
                if i.is_epic { " (EPIC)" } else { "" },
                guardrails::sanitize_untrusted(&i.title),
                i.labels.join(", "),
                ms,
            ));
        }
    }

    s.push_str("\n## Existing milestones\n");
    if gh.milestones.is_empty() {
        s.push_str("(none / unavailable)\n");
    } else {
        for m in &gh.milestones {
            s.push_str(&format!("- {m}\n"));
        }
    }

    s.push_str(
        "\nNow read GOALS.md, docs/context/TIMELINE.md, .github/labels.yml, and \
         docs/protocol/README.md. Then emit the coordination JSON per the schema.",
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

fn parse_output(raw: &str) -> ProvostOutput {
    let clean = strip_fences(raw);
    match serde_json::from_str::<ProvostOutput>(clean) {
        Ok(mut out) => {
            // Safety caps so a runaway plan can't spam the repo.
            out.label_ops.truncate(50);
            out.link_ops.truncate(50);
            out.milestone_ops.truncate(50);
            out.rfc_index_ops.truncate(50);
            out.proposed_epics.truncate(20);
            out.proposed_issues.truncate(30);
            out.proposed_rfcs.truncate(10);
            out.missing_milestones.truncate(20);
            out
        }
        Err(e) => {
            warn!(error = %e, "failed to parse agent JSON output — using noop");
            ProvostOutput::default()
        }
    }
}

/// Deterministic plan when no API key is available: surface the RFC index rows
/// (computed from front-matter) and nothing judgment-heavy.
fn deterministic_plan(rfcs: &[RfcMeta]) -> ProvostOutput {
    let rfc_index_ops: Vec<RfcIndexOp> = rfcs
        .iter()
        .map(|r| RfcIndexOp {
            rfc_file: r.file.clone(),
            title: r.title.clone(),
            status: r.status.clone(),
        })
        .collect();
    let mut summary = String::from(
        "<!-- provost: deterministic -->\n\n\
         **Provost ran without an API key** — only the deterministic RFC index \
         reconciliation is shown below. Judgment-heavy proposals (epics, new \
         issues, links) are skipped until `OPENROUTER_API_KEY` is set.\n\n\
         ## Proposed RFC index\n\n| RFC | Title | Status |\n|-----|-------|--------|\n",
    );
    for r in rfcs {
        summary.push_str(&format!("| `{}` | {} | {} |\n", r.file, r.title, r.status));
    }
    ProvostOutput { rfc_index_ops, summary, ..Default::default() }
}

// ---------------------------------------------------------------------------
// Orchestration
// ---------------------------------------------------------------------------

const VERSION: &str = env!("CARGO_PKG_VERSION");
const GIT_SHA: &str = env!("GIT_SHA");

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

async fn run() -> Result<()> {
    let cfg = Config::from_env()?;

    let rfcs = scan_rfcs();
    let specs = scan_specs();
    let gh_state = fetch_gh_state(&cfg);
    let output = match cfg.api_key.as_deref() {
        Some(api_key) => {
            let prompt = build_reconcile_prompt(&cfg, &rfcs, &specs, &gh_state);
            let runner = build_runner(&cfg, api_key)?;
            let raw = ask(&runner, prompt).await?;
            parse_output(&raw)
        }
        None => {
            warn!("no OPENROUTER_API_KEY — emitting deterministic RFC-index plan only");
            deterministic_plan(&rfcs)
        }
    };

    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mode_from_str_roundtrip() {
        assert_eq!(Mode::from_str("all"), Mode::All);
        assert_eq!(Mode::from_str("rfc"), Mode::Rfc);
        assert_eq!(Mode::from_str("epic"), Mode::Epic);
        assert_eq!(Mode::from_str("link"), Mode::Link);
        assert_eq!(Mode::from_str(""), Mode::All);
        assert_eq!(Mode::from_str("unknown"), Mode::All);
    }

    #[test]
    fn md_kv_parses_bold_and_plain() {
        assert_eq!(md_kv("- **Status:** Draft"), Some(("status".into(), "Draft".into())));
        assert_eq!(md_kv("Track: Protocol"), Some(("track".into(), "Protocol".into())));
        assert_eq!(md_kv("no colon here"), None);
    }

    #[test]
    fn parse_rfc_front_extracts_fields() {
        let text = "# 0007 — Post-Quantum Litany\n\n- **Status:** Draft\n- **Created:** 2026-06-13\n- **Track:** Protocol\n\n## Abstract\n";
        let m = parse_rfc_front(text, "protocol/rfcs/0007-pq.md");
        assert_eq!(m.title, "0007 — Post-Quantum Litany");
        assert_eq!(m.status, "Draft");
        assert_eq!(m.track, "Protocol");
    }

    #[test]
    fn parse_rfc_front_defaults_when_missing() {
        let m = parse_rfc_front("no heading, no front matter", "protocol/rfcs/x.md");
        assert_eq!(m.status, "Unknown");
        assert_eq!(m.title, "protocol/rfcs/x.md");
    }

    #[test]
    fn extract_issue_refs_finds_numbers() {
        let refs = extract_issue_refs("Track B of the 1.0 epic (#17), issue #18. See #18 again.");
        assert_eq!(refs, vec![17, 18]);
    }

    #[test]
    fn extract_issue_refs_empty() {
        assert!(extract_issue_refs("no refs here").is_empty());
    }

    #[test]
    fn parse_output_handles_valid_json() {
        let json = r#"{"label_ops":[{"issue":18,"add":["type/epic"],"remove":[]}],"link_ops":[{"parent_issue":17,"child_issue":18}],"milestone_ops":[],"rfc_index_ops":[],"proposed_epics":[],"proposed_issues":[],"proposed_rfcs":[],"missing_milestones":[],"summary":"ok"}"#;
        let out = parse_output(json);
        assert_eq!(out.label_ops.len(), 1);
        assert_eq!(out.label_ops[0].issue, 18);
        assert_eq!(out.link_ops[0].parent_issue, 17);
        assert_eq!(out.summary, "ok");
    }

    #[test]
    fn parse_output_handles_invalid_json() {
        let out = parse_output("not json at all");
        assert!(out.label_ops.is_empty());
        assert!(out.summary.is_empty());
    }

    #[test]
    fn parse_output_strips_fences() {
        let json = "```json\n{\"label_ops\":[],\"link_ops\":[],\"milestone_ops\":[],\"rfc_index_ops\":[],\"proposed_epics\":[],\"proposed_issues\":[],\"proposed_rfcs\":[],\"missing_milestones\":[],\"summary\":\"x\"}\n```";
        let out = parse_output(json);
        assert_eq!(out.summary, "x");
    }

    #[test]
    fn noop_json_is_valid() {
        let s = noop_json();
        let v: Value = serde_json::from_str(&s).expect("noop JSON must be valid");
        assert!(v["label_ops"].is_array());
        assert!(v["summary"].is_string());
    }

    #[test]
    fn deterministic_plan_lists_rfcs() {
        let rfcs = vec![RfcMeta {
            file: "protocol/rfcs/0001-hcp.md".into(),
            title: "HCP".into(),
            status: "Draft".into(),
            track: "Protocol".into(),
        }];
        let plan = deterministic_plan(&rfcs);
        assert_eq!(plan.rfc_index_ops.len(), 1);
        assert!(plan.summary.contains("0001-hcp.md"));
        assert!(plan.proposed_epics.is_empty());
    }

    #[test]
    fn output_schema_is_object() {
        let schema = output_schema();
        assert_eq!(schema["type"], "object");
        assert!(schema["properties"]["summary"].is_object());
    }
}
