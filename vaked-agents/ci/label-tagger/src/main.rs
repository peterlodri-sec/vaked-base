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
use opentelemetry_sdk::trace::SdkTracerProvider;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use tracing::{debug, info, warn};

mod guardrails;

#[global_allocator]
static GLOBAL: mimalloc::MiMalloc = mimalloc::MiMalloc;

const DEFAULT_MODEL: &str = "deepseek/deepseek-v4-flash";
const DEFAULT_BASE_URL: &str = "https://openrouter.ai/api/v1";
const DEFAULT_MAX_ITERS: u32 = 6;
const COMPACTION_BUDGET_TOKENS: usize = 80_000;
const COMPACTION_PRESERVE_RECENT: usize = 4;
const CACHE_KEY: &str = "vaked-label-tagger-v1";
const OPT_OUT_LABEL: &str = "no-auto-label";
const COMMENT_MARKER: &str = "<!-- vaked-label-tagger -->";
const MAX_DIFF_CHARS: usize = 16_000;

// ---------------------------------------------------------------------------
// Config
// ---------------------------------------------------------------------------

#[derive(Debug, PartialEq, Clone)]
enum Mode {
    Label,
    Changelog,
    MilestoneSync,
    All,
}

impl Mode {
    fn from_str(s: &str) -> Self {
        match s.to_ascii_lowercase().trim() {
            "changelog" => Mode::Changelog,
            "milestone-sync" | "milestone_sync" => Mode::MilestoneSync,
            "all" => Mode::All,
            _ => Mode::Label,
        }
    }
}

struct Config {
    repo: String,
    mode: Mode,
    pr_number: Option<u64>,
    issue_number: Option<u64>,
    base_sha: Option<String>,
    head_sha: Option<String>,
    model: String,
    base_url: String,
    api_key: Option<String>,
    max_iters: u32,
    dry_run: bool,
}

impl Config {
    fn from_env() -> Result<Self> {
        let repo = std::env::var("GITHUB_REPOSITORY")
            .unwrap_or_else(|_| "peterlodri-sec/vaked-base".to_string());
        let mode = Mode::from_str(&std::env::var("MODE").unwrap_or_default());
        let pr_number = std::env::var("PR_NUMBER")
            .ok()
            .and_then(|s| s.parse::<u64>().ok());
        let issue_number = std::env::var("ISSUE_NUMBER")
            .ok()
            .and_then(|s| s.parse::<u64>().ok());
        let base_sha = std::env::var("BASE_SHA").ok().filter(|s| !s.is_empty());
        let head_sha = std::env::var("HEAD_SHA").ok().filter(|s| !s.is_empty());
        let model = std::env::var("LABEL_TAGGER_MODEL")
            .unwrap_or_else(|_| DEFAULT_MODEL.to_string());
        let base_url = std::env::var("OPENROUTER_BASE_URL")
            .unwrap_or_else(|_| DEFAULT_BASE_URL.to_string());
        let api_key = std::env::var("LABEL_TAGGER_API_KEY")
            .ok()
            .or_else(|| std::env::var("OPENROUTER_API_KEY").ok())
            .filter(|s| !s.is_empty());
        let max_iters = std::env::var("LABEL_TAGGER_MAX_ITERS")
            .ok()
            .and_then(|s| s.parse().ok())
            .unwrap_or(DEFAULT_MAX_ITERS);
        let dry_run = std::env::var("DRY_RUN")
            .map(|s| s == "1" || s.to_ascii_lowercase() == "true")
            .unwrap_or(false);
        Ok(Config { repo, mode, pr_number, issue_number, base_sha, head_sha, model, base_url, api_key, max_iters, dry_run })
    }
}

// ---------------------------------------------------------------------------
// Output schema
// ---------------------------------------------------------------------------

#[derive(Debug, Serialize, Deserialize, Default)]
struct TaggerOutput {
    /// Labels to apply (area/*, type/*, phase/* from .github/labels.yml only).
    labels: Vec<String>,
    /// Optional short markdown comment to post on the PR/issue.
    comment: Option<String>,
    /// Exact GOALS.md phase title to assign as milestone, or null.
    milestone: Option<String>,
    /// Keep-a-Changelog formatted entry string, or null.
    changelog_entry: Option<String>,
    /// Git tag to create (e.g. "v0.3.0"), or null. Only set in changelog mode.
    new_tag: Option<String>,
    /// Milestones to upsert (milestone-sync mode only).
    #[serde(skip_serializing_if = "Vec::is_empty", default)]
    milestones_to_upsert: Vec<MilestoneSpec>,
}

#[derive(Debug, Serialize, Deserialize)]
struct MilestoneSpec {
    title: String,
    description: String,
}

/// JSON schema for the LLM structured output (label/changelog modes).
fn output_schema() -> Value {
    json!({
        "type": "object",
        "additionalProperties": false,
        "required": ["labels", "comment", "milestone", "changelog_entry", "new_tag"],
        "properties": {
            "labels": {
                "type": "array",
                "items": { "type": "string" },
                "description": "Labels to apply from the labels.yml taxonomy"
            },
            "comment": {
                "type": ["string", "null"],
                "description": "Short markdown comment to post, or null"
            },
            "milestone": {
                "type": ["string", "null"],
                "description": "Exact phase title from GOALS.md to assign, or null"
            },
            "changelog_entry": {
                "type": ["string", "null"],
                "description": "Keep-a-Changelog formatted entry, or null"
            },
            "new_tag": {
                "type": ["string", "null"],
                "description": "Git tag to create (changelog mode only), or null"
            }
        }
    })
}

/// The empty fallback emitted when anything goes wrong (advisory — never block CI).
fn noop_json() -> String {
    serde_json::to_string(&TaggerOutput::default()).unwrap()
}

// ---------------------------------------------------------------------------
// Tracing → self-hosted Langfuse, via the shared `vaked-telemetry` crate
// (single source of truth for the LANGFUSE_* env resolution).
// ---------------------------------------------------------------------------

fn setup_tracing() -> Option<SdkTracerProvider> {
    vaked_telemetry::setup_tracing("vaked-label-tagger", "vaked-label-tagger")
}

// ---------------------------------------------------------------------------
// adk-rust runner
// ---------------------------------------------------------------------------

struct TaggerRunner {
    runner: Runner,
    sessions: Arc<dyn SessionService>,
}

fn build_runner(cfg: &Config, api_key: &str) -> Result<TaggerRunner> {
    let or_config = OpenRouterConfig::new(api_key.to_string(), cfg.model.clone())
        .with_base_url(cfg.base_url.clone())
        .with_http_referer("https://github.com/peterlodri-sec/vaked-base")
        .with_title("vaked-label-tagger")
        .with_default_api_mode(OpenRouterApiMode::ChatCompletions);
    let model = OpenRouterClient::new(or_config).map_err(|e| anyhow!("OpenRouter client: {e}"))?;

    let mut gen_cfg = GenerateContentConfig {
        temperature: Some(0.1),
        top_p: Some(0.9),
        max_output_tokens: Some(1024),
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

    let agent = LlmAgentBuilder::new("vaked-label-tagger")
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
        .app_name("vaked-label-tagger")
        .agent(Arc::new(agent))
        .session_service(sessions.clone())
        .run_config(run_config)
        .context_compaction(CompactionConfig::new(
            Box::new(TruncationCompaction { preserve_recent: COMPACTION_PRESERVE_RECENT }),
            COMPACTION_BUDGET_TOKENS,
        ))
        .build()
        .map_err(|e| anyhow!("runner build: {e}"))?;
    Ok(TaggerRunner { runner, sessions })
}

/// One agent turn (fresh session); returns the model's full text response.
async fn ask(rr: &TaggerRunner, prompt: String) -> Result<String> {
    let session_id = SessionId::generate();
    rr.sessions
        .create(CreateRequest {
            app_name: "vaked-label-tagger".into(),
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
             docs/context/TIMELINE.md, and .github/labels.yml before making labeling decisions.",
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
    r#"You are the Vaked CI label-tagger: a doc-grounded automation agent for the
vaked-base monorepo. Your ONLY job is to classify a PR, issue, or set of merged
commits and emit structured JSON. You are advisory — you NEVER block CI.

## Tool you MUST call first

`read_file(path)` — read a repo file. Before making ANY decision, call it for:
1. `GOALS.md` — 6 phases (0–5). Each `### Phase N — Title` heading is a milestone.
   Map the change to the most relevant phase.
2. `docs/context/TIMELINE.md` — current project posture (✅ done / 🟡 in progress /
   🟦 stub / ⬜ planned). Use this to judge which phase the change advances.
3. `.github/labels.yml` — the COMPLETE label taxonomy. You MUST only emit labels
   whose `name:` field appears verbatim in this file. DO NOT invent labels.

## Label selection rules (label mode)

`area/*` — ONE or TWO area labels max. Map changed file paths:
  vaked/             → area/language
  vakedc/            → area/compiler
  docs/              → area/docs
  protocol/          → area/protocol
  daemons/, hosts/   → area/runtime
  vaked-agents/      → area/agents
  tools/             → area/tools
  .github/           → area/ci
  flake.nix, *.nix   → area/nix

`type/*` — ONE type label:
  new capability or construct → type/feature
  bug repair                 → type/fix
  restructure only           → type/refactor
  markdown/docs only         → type/docs
  deps, CI, maintenance      → type/chore
  design record              → type/design
  RFC or EBNF spec change    → type/spec

`phase/*` — at most ONE. Choose the GOALS.md phase whose unchecked items this
PR/issue advances. Omit if ambiguous or if the change is purely internal tooling.

`status/*` — DO NOT apply status labels (those are set by humans).
`no-auto-label`, `no-bot-review` — never apply these.

Emit at most 8 labels total across all categories.

## Milestone rule
Derive `milestone` from the `phase/*` label (if chosen). The value MUST be the
exact text of the `### Phase N — Title` heading from GOALS.md (e.g.
"Phase 0 — Language foundation"). Only set `milestone` when you also set `phase/*`.

## Comment rule
Set `comment` to a 1-3 sentence markdown explanation of your labeling reasoning.
Keep it blunt and factual — no praise, no hedging. The user reads this on the PR.
Start with the labels chosen.

## Changelog entry rules (changelog mode)
Group entries by area label. Each entry: `- <type>(<area>): <one-line> (#<PR>)`
Section header: `## [unreleased] — <YYYY-MM-DD>`. Omit empty sections.
Only set `new_tag` for a grammar version bump (EBNF file changed), a compiler
version bump in Cargo.toml, or a significant protocol RFC milestone.
Format: `vN.M.P`. Be conservative — leave `new_tag` null when unsure.

## Milestone-sync rules (milestone-sync mode)
Read GOALS.md. Return `milestones_to_upsert` with all 6 phase milestones.
Each: `{ "title": "Phase N — ...", "description": "<first two bullet points>" }`.

## Output contract
Respond ONLY with JSON matching the schema. No prose, no markdown fences.
On any uncertainty, omit the field (null) rather than guess.
If `no-auto-label` is present on the PR/issue, set `labels: []` and return."#.to_string()
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

// ---------------------------------------------------------------------------
// PR / issue metadata
// ---------------------------------------------------------------------------

struct PrMeta {
    number: u64,
    title: String,
    body: String,
    files: Vec<String>,
    labels: Vec<String>,
}

fn fetch_pr_meta(cfg: &Config, pr: u64) -> Result<PrMeta> {
    let pr_s = pr.to_string();
    let raw = gh(&["pr", "view", &pr_s, "--repo", &cfg.repo, "--json", "title,body,files,labels,number"])?;
    let v: Value = serde_json::from_str(&raw).context("parsing gh pr view JSON")?;
    let files = v["files"].as_array().map(|a| {
        a.iter().filter_map(|f| f["path"].as_str().map(String::from)).collect()
    }).unwrap_or_default();
    let labels = v["labels"].as_array().map(|a| {
        a.iter().filter_map(|l| l["name"].as_str().map(String::from)).collect()
    }).unwrap_or_default();
    Ok(PrMeta {
        number: v["number"].as_u64().unwrap_or(pr),
        title: v["title"].as_str().unwrap_or_default().to_string(),
        body: v["body"].as_str().unwrap_or_default().to_string(),
        files,
        labels,
    })
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

fn fetch_pr_diff(cfg: &Config, pr: u64) -> String {
    // Try git diff over base..head first (fast, no network), fall back to gh.
    if let (Some(base), Some(head)) = (&cfg.base_sha, &cfg.head_sha) {
        if let Ok(d) = git(&["diff", &format!("{base}...{head}")]) {
            if !d.trim().is_empty() {
                let (truncated, _) = truncate(&d, MAX_DIFF_CHARS);
                return truncated.to_string();
            }
        }
    }
    let pr_s = pr.to_string();
    let d = gh(&["pr", "diff", &pr_s, "--repo", &cfg.repo]).unwrap_or_default();
    let (truncated, _) = truncate(&d, MAX_DIFF_CHARS);
    truncated.to_string()
}

fn fetch_commits_since_tag(repo: &str) -> String {
    // Get the latest semver tag, then list commits since it.
    let last_tag = git(&["describe", "--tags", "--abbrev=0", "--match", "v*"])
        .unwrap_or_else(|_| String::new());
    let last_tag = last_tag.trim().to_string();
    let range = if last_tag.is_empty() {
        "HEAD~20..HEAD".to_string()
    } else {
        format!("{last_tag}..HEAD")
    };
    let log = git(&[
        "log", "--oneline", "--no-merges", "--pretty=format:%h %s", &range,
    ]).unwrap_or_default();
    // Also try to pull merged PR numbers from recent merge commits
    let prs = gh(&[
        "pr", "list", "--repo", repo, "--state", "merged", "--limit", "20",
        "--json", "number,title,labels,mergedAt",
    ]).unwrap_or_default();
    format!("Last tag: {last_tag}\nCommits since tag:\n{log}\n\nRecently merged PRs:\n{prs}")
}

fn truncate(s: &str, max: usize) -> (&str, bool) {
    let chars: Vec<char> = s.chars().collect();
    if chars.len() <= max {
        (s, false)
    } else {
        let byte_pos = s.char_indices()
            .nth(max)
            .map(|(i, _)| i)
            .unwrap_or(s.len());
        (&s[..byte_pos], true)
    }
}

// ---------------------------------------------------------------------------
// Parse GOALS.md phases (for milestone-sync mode without LLM)
// ---------------------------------------------------------------------------

fn parse_goals_phases(goals_md: &str) -> Vec<MilestoneSpec> {
    let mut milestones = Vec::new();
    let mut current_title: Option<String> = None;
    let mut bullets: Vec<String> = Vec::new();

    for line in goals_md.lines() {
        if let Some(rest) = line.strip_prefix("### Phase ") {
            // Flush the previous phase before starting the new one.
            if let Some(title) = current_title.take() {
                let desc = bullets.iter().take(3).cloned().collect::<Vec<_>>().join("\n");
                milestones.push(MilestoneSpec { title, description: desc });
                bullets.clear();
            }
            // rest = "0 — Language foundation *(in progress)*"
            // Strip the *(status)* annotation and prepend "Phase " back so the
            // title matches the exact phase heading text from GOALS.md.
            let clean = rest.trim().split(" *(").next().unwrap_or(rest.trim()).trim();
            current_title = Some(format!("Phase {clean}"));
        } else if line.starts_with("- [") && current_title.is_some() {
            bullets.push(line.trim().to_string());
        }
    }
    // Flush the last phase.
    if let Some(title) = current_title {
        let desc = bullets.iter().take(3).cloned().collect::<Vec<_>>().join("\n");
        milestones.push(MilestoneSpec { title, description: desc });
    }
    milestones
}

// ---------------------------------------------------------------------------
// Prompt builders
// ---------------------------------------------------------------------------

fn build_label_pr_prompt(meta: &PrMeta, diff: &str) -> String {
    let mut s = String::new();
    s.push_str("# Label this PR\n\n");
    s.push_str(&format!("PR #{}: {}\n", meta.number, guardrails::sanitize_untrusted(&meta.title)));
    if !meta.body.trim().is_empty() {
        s.push_str("\n## PR Description\n");
        s.push_str(&guardrails::sanitize_untrusted(meta.body.trim()));
        s.push('\n');
    }
    if !meta.files.is_empty() {
        s.push_str(&format!("\n## Changed files ({})\n", meta.files.len()));
        for f in &meta.files {
            s.push_str(&format!("- {f}\n"));
        }
    }
    if !diff.trim().is_empty() {
        s.push_str("\n## Diff (may be truncated)\n```diff\n");
        s.push_str(diff);
        s.push_str("\n```\n");
    }
    s.push_str("\nRead GOALS.md, docs/context/TIMELINE.md, and .github/labels.yml now.\nThen emit the JSON labels, milestone, and comment.");
    s
}

fn build_label_issue_prompt(meta: &IssueMeta) -> String {
    let mut s = String::new();
    s.push_str("# Label this issue\n\n");
    s.push_str(&format!("Issue #{}: {}\n", meta.number, guardrails::sanitize_untrusted(&meta.title)));
    if !meta.body.trim().is_empty() {
        s.push_str("\n## Issue Body\n");
        s.push_str(&guardrails::sanitize_untrusted(meta.body.trim()));
        s.push('\n');
    }
    s.push_str("\nRead GOALS.md, docs/context/TIMELINE.md, and .github/labels.yml now.\nThen emit the JSON labels, milestone, and comment.");
    s
}

fn build_changelog_prompt(commits: &str) -> String {
    let today = chrono_today();
    format!(
        "# Generate changelog entry\n\n\
         Today: {today}\n\n\
         ## Recent activity\n{commits}\n\n\
         Read GOALS.md, docs/context/TIMELINE.md, and .github/labels.yml now.\n\
         Then generate a `changelog_entry` grouped by area. Decide if a `new_tag` \
         is warranted (only for grammar/compiler/protocol version milestones). \
         Set `labels: []`, `comment: null`, `milestone: null`."
    )
}

fn build_milestone_sync_prompt() -> String {
    "# Milestone sync\n\n\
     Read GOALS.md now. Extract all 6 phase headings (Phase 0 through Phase 5).\n\
     Return a `milestones_to_upsert` array with title = exact phase heading text and \
     description = the first 2-3 bullet points from that phase.\n\
     Set `labels: []`, `comment: null`, `milestone: null`, `changelog_entry: null`, `new_tag: null`."
        .to_string()
}

fn chrono_today() -> String {
    // Use `date` command — avoids adding a chrono dependency.
    StdCommand::new("date")
        .arg("+%Y-%m-%d")
        .output()
        .ok()
        .and_then(|o| String::from_utf8(o.stdout).ok())
        .map(|s| s.trim().to_string())
        .unwrap_or_else(|| "2026-01-01".to_string())
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

fn parse_output(raw: &str) -> TaggerOutput {
    let clean = strip_fences(raw);
    match serde_json::from_str::<TaggerOutput>(clean) {
        Ok(mut out) => {
            // Safety: cap labels to a reasonable number.
            out.labels.truncate(10);
            out
        }
        Err(e) => {
            warn!(error = %e, "failed to parse agent JSON output — using noop");
            TaggerOutput::default()
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

async fn run() -> Result<()> {
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

async fn run_label(cfg: &Config) -> Result<()> {
    let api_key = cfg.api_key.as_deref()
        .ok_or_else(|| anyhow!("no OPENROUTER_API_KEY — set it to enable labeling"))?;

    let prompt = if let Some(issue) = cfg.issue_number {
        let meta = fetch_issue_meta(cfg, issue)?;
        if meta.labels.iter().any(|l| l == OPT_OUT_LABEL) {
            info!("'{OPT_OUT_LABEL}' on issue — skipping");
            println!("{}", noop_json());
            return Ok(());
        }
        build_label_issue_prompt(&meta)
    } else if let Some(pr) = cfg.pr_number {
        let meta = fetch_pr_meta(cfg, pr)?;
        if meta.labels.iter().any(|l| l == OPT_OUT_LABEL) {
            info!("'{OPT_OUT_LABEL}' on PR — skipping");
            println!("{}", noop_json());
            return Ok(());
        }
        let diff = fetch_pr_diff(cfg, pr);
        build_label_pr_prompt(&meta, &diff)
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
    let output = parse_output(&raw);
    println!("{}", serde_json::to_string(&output)?);
    Ok(())
}

async fn run_changelog(cfg: &Config) -> Result<()> {
    let api_key = cfg.api_key.as_deref()
        .ok_or_else(|| anyhow!("no OPENROUTER_API_KEY — set it to enable changelog mode"))?;

    let commits = fetch_commits_since_tag(&cfg.repo);
    let prompt = build_changelog_prompt(&commits);

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
    let milestones = if let Some(api_key) = &cfg.api_key {
        if !cfg.dry_run {
            let runner = build_runner(cfg, api_key)?;
            let raw = ask(&runner, build_milestone_sync_prompt()).await?;
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

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn mode_from_str_roundtrip() {
        assert_eq!(Mode::from_str("label"), Mode::Label);
        assert_eq!(Mode::from_str("changelog"), Mode::Changelog);
        assert_eq!(Mode::from_str("milestone-sync"), Mode::MilestoneSync);
        assert_eq!(Mode::from_str("all"), Mode::All);
        assert_eq!(Mode::from_str(""), Mode::Label);
        assert_eq!(Mode::from_str("unknown"), Mode::Label);
    }

    #[test]
    fn parse_goals_phases_extracts_all_six() {
        let goals = r#"
### Phase 0 — Language foundation *(in progress)*
- [x] EBNF grammar
- [ ] Full lowering

### Phase 1 — Compiler maturity
- [ ] vakedc check
- [ ] LSP server

### Phase 2 — Runtime: stubs → real
- [ ] OTP plane

### Phase 3 — Wire protocol
- [ ] HCP RFCs

### Phase 4 — Surfaces and observability
- [ ] Operator surface

### Phase 5 — Language v1
- [ ] Grammar stable
"#;
        let phases = parse_goals_phases(goals);
        assert_eq!(phases.len(), 6);
        assert!(phases[0].title.contains("Language foundation") || phases[0].title.contains("0"));
        assert!(phases[5].title.contains("Language v1") || phases[5].title.contains("5"));
    }

    #[test]
    fn parse_output_handles_valid_json() {
        let json = r#"{"labels":["area/language","type/feature"],"comment":"test","milestone":"Phase 0 — Language foundation","changelog_entry":null,"new_tag":null}"#;
        let out = parse_output(json);
        assert_eq!(out.labels.len(), 2);
        assert_eq!(out.labels[0], "area/language");
    }

    #[test]
    fn parse_output_handles_invalid_json() {
        let out = parse_output("not json at all");
        assert!(out.labels.is_empty());
        assert!(out.comment.is_none());
    }

    #[test]
    fn parse_output_strips_fences() {
        let json = "```json\n{\"labels\":[],\"comment\":null,\"milestone\":null,\"changelog_entry\":null,\"new_tag\":null}\n```";
        let out = parse_output(json);
        assert!(out.labels.is_empty());
    }

    #[test]
    fn noop_json_is_valid() {
        let s = noop_json();
        let v: Value = serde_json::from_str(&s).expect("noop JSON must be valid");
        assert!(v["labels"].is_array());
    }

    #[test]
    fn truncate_clips_at_char_boundary() {
        let s = "hello world";
        let (clipped, truncated) = truncate(s, 5);
        assert_eq!(clipped, "hello");
        assert!(truncated);
        let (full, trunc2) = truncate(s, 100);
        assert_eq!(full, s);
        assert!(!trunc2);
    }
}
