//! Reviewer agent + Runner construction, the `read_lines`/crabcc tools, the
//! single-turn `ask` helper, and the opt-in workflow-agent (ParallelAgent →
//! SequentialAgent) map-reduce pipeline.

use std::collections::HashMap;
use std::process::Command as StdCommand;
use std::sync::Arc;
use std::time::Duration;

use adk_agent::{ParallelAgent, SequentialAgent};
use adk_core::{Agent, GenerateContentConfig, SessionId, UserId};
use adk_rust::prelude::*;
use adk_rust::session::{CreateRequest, SessionService};
use adk_rust::tool::McpToolset;
use adk_rust::{RetryBudget, ToolConcurrencyConfig, ToolExecutionStrategy};
use adk_runner::compaction::{CompactionConfig, TruncationCompaction};
use anyhow::{Context, Result, anyhow};
use futures::StreamExt;
use rmcp::ServiceExt;
use rmcp::transport::TokioChildProcess;
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use tokio::process::Command as TokioCommand;
use tracing::{info, warn};

use crate::config::{Config, env_first, truncate};
use crate::consts::{
    CACHE_KEY, COMPACTION_BUDGET_TOKENS, COMPACTION_PRESERVE_RECENT, MAX_FILES_MAPREDUCE,
    PERFILE_REASONING_EFFORT,
};
use crate::diff::split_per_file;
use crate::github::PrMeta;
use crate::guardrails;
use crate::prompts::{findings_schema, system_prompt};
use crate::review::clean_verdict;

/// A built reviewer agent plus the session service it runs on.
pub(crate) struct ReviewRunner {
    pub(crate) runner: Runner,
    pub(crate) sessions: Arc<dyn SessionService>,
}

#[derive(Default, Clone, Copy)]
pub(crate) struct Usage {
    pub(crate) total: i64,
    pub(crate) thinking: i64,
    pub(crate) cached: i64,
    pub(crate) calls: u32,
}
impl std::ops::AddAssign for Usage {
    fn add_assign(&mut self, o: Self) {
        self.total += o.total;
        self.thinking += o.thinking;
        self.cached += o.cached;
        self.calls += o.calls;
    }
}

/// Build a reviewer (model + reasoning + caching + tools + loop bounds) and Runner.
pub(crate) fn build_runner_with(
    cfg: &Config,
    api_key: &str,
    effort: &str,
    max_out: i32,
    structured: bool,
    crabcc: Option<Arc<dyn Toolset>>,
    instruction: String,
) -> Result<ReviewRunner> {
    let model = build_or_model(cfg, api_key)?;
    let gen_cfg = gen_config(&cfg.model, effort, max_out, structured)?;

    // Bounded retries so a flaky tool call retries instead of failing the turn.
    let retry = || RetryBudget {
        max_retries: 2,
        delay: Duration::from_millis(250),
    };
    let mut builder = LlmAgentBuilder::new("vaked-ci-reviewer")
        .instruction(instruction)
        .model(Arc::new(model))
        .generate_content_config(gen_cfg)
        .max_iterations(cfg.max_iters)
        .tool_timeout(Duration::from_secs(60))
        .tool_execution_strategy(ToolExecutionStrategy::Auto)
        .tool_retry_budget("crabcc", retry())
        .tool_retry_budget("read_lines", retry())
        .tool(read_lines_tool())
        // Security guardrails (item 5). Input: redact secrets + defang injection
        // on the untrusted diff. Output: cap findings. All Transform/Pass — never
        // Fail — so a guardrail can never suppress this advisory reviewer.
        .input_guardrails(guardrails::input_guardrails())
        .output_guardrails(guardrails::output_guardrails(cfg.max_findings as usize));
    if let Some(ts) = crabcc {
        builder = builder.toolset(ts);
    }
    let agent = builder.build().map_err(|e| anyhow!("agent build: {e}"))?;

    // Optionally record prompt/response payloads into spans for richer Langfuse
    // generations (safe — the diff is already redacted before it reaches here).
    let run_config = RunConfig::builder()
        .tool_concurrency(ToolConcurrencyConfig {
            max_concurrency: Some(cfg.concurrency),
            ..Default::default()
        })
        // Prompt caching (item 2). `auto_cache` is provider-level (Anthropic/Bedrock/
        // OpenAI); OpenRouter does NOT implement adk's `CacheCapable`, so for our
        // provider the real win stays the `with_prompt_cache_key` set in the request
        // options above. Kept explicit (default is already true) to document intent.
        .auto_cache(true)
        .record_payloads(cfg.trace_payloads)
        .trace_payload_max_bytes(16_384)
        .build();

    let sessions: Arc<dyn SessionService> = Arc::new(InMemorySessionService::new());
    let runner = Runner::builder()
        .app_name("vaked-ci-reviewer")
        .agent(Arc::new(agent))
        .session_service(sessions.clone())
        .run_config(run_config)
        // Context compaction (item 4): overflow guard for the tool loop.
        .context_compaction(CompactionConfig::new(
            Box::new(TruncationCompaction {
                preserve_recent: COMPACTION_PRESERVE_RECENT,
            }),
            COMPACTION_BUDGET_TOKENS,
        ))
        .build()
        .map_err(|e| anyhow!("runner build: {e}"))?;
    Ok(ReviewRunner { runner, sessions })
}

/// The OpenRouter model client (shared shape for every reviewer agent).
fn build_or_model(cfg: &Config, api_key: &str) -> Result<OpenRouterClient> {
    let or_config = OpenRouterConfig::new(api_key.to_string(), cfg.model.clone())
        .with_base_url(cfg.base_url.clone())
        .with_http_referer("https://github.com/peterlodri-sec/vaked-base")
        .with_title("vaked-ci-reviewer")
        .with_default_api_mode(OpenRouterApiMode::ChatCompletions);
    OpenRouterClient::new(or_config).map_err(|e| anyhow!("OpenRouter client: {e}"))
}

/// Generation config: low-temp/fixed-seed + reasoning effort, a stable prompt-cache
/// key (OpenRouter caches the static system-prompt prefix), provider fallbacks, and
/// the structured-output schema when `structured`.
fn gen_config(
    model: &str,
    effort: &str,
    max_out: i32,
    structured: bool,
) -> Result<GenerateContentConfig> {
    let mut gen_cfg = GenerateContentConfig {
        temperature: Some(0.1),
        top_p: Some(0.9),
        max_output_tokens: Some(max_out),
        seed: Some(7),
        ..Default::default()
    };
    if structured {
        gen_cfg.response_schema = Some(findings_schema());
    }
    // Provider pinning for cache hits: OpenRouter's prefix cache is per-provider, so
    // letting it route the map-reduce per-file passes to different DeepSeek hosts cold-
    // starts the cache each time. Pin the first-party DeepSeek provider first (keeping
    // `allow_fallbacks` for resilience) so the byte-stable system-prompt prefix stays
    // warm across passes. Only pin for deepseek/* models; override via
    // PR_REVIEW_PROVIDER_ORDER (comma-separated provider slugs).
    let order = env_first(&["PR_REVIEW_PROVIDER_ORDER"])
        .map(|s| {
            s.split(',')
                .map(|p| p.trim().to_string())
                .filter(|p| !p.is_empty())
                .collect::<Vec<_>>()
        })
        .or_else(|| model.starts_with("deepseek/").then(|| vec!["DeepSeek".to_string()]))
        .filter(|v| !v.is_empty());

    let mut opts = OpenRouterRequestOptions::default()
        .with_reasoning(OpenRouterReasoningConfig {
            effort: Some(effort.to_string()),
            enabled: Some(true),
            ..Default::default()
        })
        .with_prompt_cache_key(CACHE_KEY)
        .with_provider_preferences(OpenRouterProviderPreferences {
            allow_fallbacks: Some(true),
            order,
            ..Default::default()
        });
    // Usage accounting: without `usage.include`, OpenRouter omits prompt_tokens_details,
    // so cached-token counts (DeepSeek prefix-cache reads) never surface in the trace.
    opts.extra
        .insert("usage".to_string(), json!({ "include": true }));
    opts.insert_into_config(&mut gen_cfg)
        .map_err(|e| anyhow!("openrouter options: {e}"))?;
    Ok(gen_cfg)
}

// ---------------------------------------------------------------------------
// Workflow-agent pipeline (backlog item 1) — OPT-IN via PR_REVIEW_PARALLEL_AGENT.
//
// Replaces the hand-rolled `buffer_unordered` map-reduce with adk's workflow
// agents: a `ParallelAgent` fan-out of per-file reviewers feeding a
// `SequentialAgent` synthesis step. Kept opt-in (the proven `map_reduce_review`
// stays the default, and is the runtime fallback if this path errors) until it is
// validated live, since adk multi-agent context propagation can't be exercised in
// CI without a model key.
//
// NB: each per-file diff is baked into the sub-agent *instruction* (ParallelAgent
// broadcasts identical user content, so per-file fan-out has to live in the
// instruction). Input guardrails only see user content, so the diff is run through
// `guardrails::sanitize_untrusted` first to keep the same redaction/injection
// protection at that choke point.
// ---------------------------------------------------------------------------

/// Build one reviewer `LlmAgent` for the workflow pipeline (a per-file reviewer or
/// the synthesis step), writing its final text to session state under `output_key`.
#[allow(clippy::too_many_arguments)]
fn build_pipeline_agent(
    cfg: &Config,
    model: Arc<OpenRouterClient>,
    name: &str,
    effort: &str,
    max_out: i32,
    structured: bool,
    instruction: String,
    output_key: &str,
    crabcc: Option<Arc<dyn Toolset>>,
    output_guardrail: bool,
    isolate_history: bool,
) -> Result<LlmAgent> {
    let gen_cfg = gen_config(&cfg.model, effort, max_out, structured)?;
    let retry = || RetryBudget {
        max_retries: 2,
        delay: Duration::from_millis(250),
    };
    // Per-file reviewers run in later sequential batches after earlier batches have
    // emitted findings into the shared session; `IncludeContents::None` keeps each
    // reviewer on its own turn (instruction + trigger) so it can't see — and
    // misattribute — another file's findings. The synthesis step keeps `Default`
    // so it *does* see every per-file result.
    let include = if isolate_history {
        adk_core::IncludeContents::None
    } else {
        adk_core::IncludeContents::Default
    };
    let mut builder = LlmAgentBuilder::new(name)
        .instruction(instruction)
        .model(model)
        .generate_content_config(gen_cfg)
        .include_contents(include)
        .max_iterations(cfg.max_iters)
        .tool_timeout(Duration::from_secs(60))
        .tool_execution_strategy(ToolExecutionStrategy::Auto)
        .tool_retry_budget("crabcc", retry())
        .tool_retry_budget("read_lines", retry())
        .tool(read_lines_tool())
        .output_key(output_key);
    if output_guardrail {
        builder =
            builder.output_guardrails(guardrails::output_guardrails(cfg.max_findings as usize));
    }
    if let Some(ts) = crabcc {
        builder = builder.toolset(ts);
    }
    builder.build().map_err(|e| anyhow!("agent build: {e}"))
}

/// Run a built pipeline once and pull the final review out of session state
/// (`output_key`), falling back to the synthesis agent's streamed text. Also sums
/// token usage across every sub-agent turn.
async fn run_collect(
    rr: &ReviewRunner,
    prompt: &str,
    output_key: &str,
    initial_state: HashMap<String, Value>,
) -> Result<(String, Usage)> {
    let session_id = SessionId::generate();
    rr.sessions
        .create(CreateRequest {
            app_name: "vaked-ci-reviewer".into(),
            user_id: "vaked-ci".into(),
            session_id: Some(session_id.to_string()),
            state: initial_state,
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

    let mut keyed = String::new();
    let mut synth_text = String::new();
    let mut usage = Usage::default();
    while let Some(event) = stream.next().await {
        let event = event.map_err(|e| anyhow!("event: {e}"))?;
        if let Some(u) = &event.llm_response.usage_metadata {
            usage.total += u.total_token_count as i64;
            usage.thinking += u.thinking_token_count.unwrap_or(0) as i64;
            usage.cached += u.cache_read_input_token_count.unwrap_or(0) as i64;
            usage.calls += 1;
        }
        if let Some(v) = event.actions.state_delta.get(output_key).and_then(Value::as_str) {
            keyed = v.to_string();
        }
        if event.author == "synthesis"
            && let Some(content) = &event.llm_response.content
        {
            for part in &content.parts {
                if let Some(t) = part.text() {
                    synth_text.push_str(t);
                }
            }
        }
    }
    let text = if keyed.trim().is_empty() {
        synth_text
    } else {
        keyed
    };
    Ok((text, usage))
}

/// Per-file reviewers (adk `ParallelAgent`) → synthesis (`SequentialAgent`).
#[allow(clippy::too_many_arguments)]
pub(crate) async fn parallel_agent_review(
    cfg: &Config,
    api_key: &str,
    meta: &PrMeta,
    diff: &str,
    addenda: &str,
    crabcc: Option<Arc<dyn Toolset>>,
    usage: &mut Usage,
) -> Result<String> {
    let files = split_per_file(diff);
    let total = files.len();
    let budget = cfg.max_diff_chars / 4;
    let model = Arc::new(build_or_model(cfg, api_key)?);

    // Untrusted text (per-file diff/path, PR title) goes into SESSION STATE and is
    // referenced from the instruction by a single `{placeholder}`. adk templates
    // instructions via `inject_session_state`, and the injected value is not
    // re-scanned — so the diff's own `{...}` (format strings, blocks, even a
    // literal `{review_0}`) can't trigger templating, which would otherwise error
    // or splice another file's findings into this one's instruction. It is still
    // sanitized (guardrails don't see instructions or injected state).
    let mut initial_state: HashMap<String, Value> = HashMap::new();
    let mut reviewers: Vec<Arc<dyn Agent>> = Vec::new();
    for (i, (path, section)) in files.into_iter().take(MAX_FILES_MAPREDUCE).enumerate() {
        let (section, _) = truncate(&section, budget);
        let body = format!(
            "File: {}\n```diff\n{}\n```{addenda}",
            guardrails::sanitize_untrusted(&path),
            guardrails::sanitize_untrusted(&section),
        );
        initial_state.insert(format!("file_body_{i}"), Value::String(body));
        let instruction = format!(
            "{}\n\n## Your assignment\nReview ONLY this file's diff per your rules. Output findings bullets only — no verdict line, no JSON. If clean, output nothing.\n{{file_body_{i}}}",
            system_prompt(cfg.max_findings, cfg.crabcc_budget, false)
        );
        let agent = build_pipeline_agent(
            cfg,
            model.clone(),
            &format!("file-reviewer-{i}"),
            PERFILE_REASONING_EFFORT,
            1024,
            false,
            instruction,
            &format!("review_{i}"),
            crabcc.clone(),
            false, // output_guardrail
            true,  // isolate_history — ignore other files' findings
        )?;
        reviewers.push(Arc::new(agent));
    }
    if reviewers.is_empty() {
        return Ok(clean_verdict(cfg.structured));
    }
    let note = if total > MAX_FILES_MAPREDUCE {
        format!(" (only the first {MAX_FILES_MAPREDUCE} of {total} files were reviewed)")
    } else {
        String::new()
    };

    // Bound fan-out to PR_REVIEW_CONCURRENCY: adk's `ParallelAgent` has no built-in
    // cap (it launches every sub-agent at once), so run the per-file reviewers in
    // sequential batches of `concurrency` — each batch a `ParallelAgent`, the
    // batches chained by the `SequentialAgent`. Mirrors the legacy path's
    // `buffer_unordered(cfg.concurrency)` throttle.
    let conc = cfg.concurrency.max(1);
    let mut stages: Vec<Arc<dyn Agent>> = reviewers
        .chunks(conc)
        .enumerate()
        .map(|(n, chunk)| {
            Arc::new(ParallelAgent::new(format!("file-reviewers-{n}"), chunk.to_vec()))
                as Arc<dyn Agent>
        })
        .collect();

    // The PR title is untrusted too — sanitize it and pass it via state (same
    // templating hazard as the diff), referenced by `{pr_title}`.
    initial_state.insert(
        "pr_title".to_string(),
        Value::String(guardrails::sanitize_untrusted(&meta.title)),
    );
    let synth_instruction = format!(
        "{}\n\n## Your assignment\nThe conversation above holds per-file findings from a large PR ({total} files){note}. Produce the FINAL review per your output contract: dedupe, drop noise, keep the most important, group by severity, lead with the verdict line.\n\nPR #{}: {{pr_title}}",
        system_prompt(cfg.max_findings, cfg.crabcc_budget, cfg.structured),
        meta.number,
    );
    let synth = build_pipeline_agent(
        cfg,
        model.clone(),
        "synthesis",
        &cfg.reasoning_effort,
        4096,
        cfg.structured,
        synth_instruction,
        "final_review",
        None,
        true,  // output_guardrail — cap the final findings
        false, // isolate_history — synthesis must see every per-file result
    )?;
    stages.push(Arc::new(synth));

    let pipeline = SequentialAgent::new("review-pipeline", stages);

    let run_config = RunConfig::builder().auto_cache(true).build();
    let sessions: Arc<dyn SessionService> = Arc::new(InMemorySessionService::new());
    let runner = Runner::builder()
        .app_name("vaked-ci-reviewer")
        .agent(Arc::new(pipeline))
        .session_service(sessions.clone())
        .run_config(run_config)
        .build()
        .map_err(|e| anyhow!("pipeline runner build: {e}"))?;

    let rr = ReviewRunner { runner, sessions };
    let (text, u) = run_collect(
        &rr,
        "Review the pull request per your instructions.",
        "final_review",
        initial_state,
    )
    .await?;
    *usage += u;
    if text.trim().is_empty() {
        return Err(anyhow!("parallel pipeline produced no synthesis output"));
    }
    Ok(text)
}

/// A read-only tool: pull an inclusive 1-based line range from a repo file.
#[derive(Deserialize, Serialize, JsonSchema)]
struct ReadLinesArgs {
    /// Repository-relative file path (no leading `/`, no `..`).
    path: String,
    /// 1-based inclusive start line.
    start: u32,
    /// 1-based inclusive end line.
    end: u32,
}

fn read_lines_tool() -> Arc<dyn Tool> {
    Arc::new(
        FunctionTool::new(
            "read_lines",
            "Read an inclusive 1-based line range from a repo-relative file (read-only).",
            |_ctx: Arc<dyn ToolContext>, args: Value| async move {
                let path = args
                    .get("path")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string();
                let start = args
                    .get("start")
                    .and_then(Value::as_u64)
                    .unwrap_or(1)
                    .max(1) as usize;
                let end = args
                    .get("end")
                    .and_then(Value::as_u64)
                    .unwrap_or(start as u64) as usize;
                if path.is_empty() || path.contains("..") || path.starts_with('/') {
                    return Ok(json!({"error": "path must be repo-relative, no '..'"}));
                }
                let text = match std::fs::read_to_string(&path) {
                    Ok(t) => t,
                    Err(e) => return Ok(json!({"error": format!("read {path}: {e}")})),
                };
                let lines: Vec<&str> = text.lines().collect();
                let s = start.saturating_sub(1).min(lines.len());
                let e = end.min(lines.len()).max(s).min(s + 400); // cap 400 lines
                let slice: String = lines[s..e].join("\n").chars().take(8000).collect();
                Ok(json!({"path": path, "start": start, "end": e, "content": slice}))
            },
        )
        .with_read_only(true)
        .with_concurrency_safe(true)
        .with_parameters_schema::<ReadLinesArgs>(),
    )
}

/// Spawn `crabcc --mcp` over stdio and wrap it as a toolset (index refreshed first).
pub(crate) async fn connect_crabcc(cfg: &Config) -> Result<McpToolset> {
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

/// One agent turn (fresh session); returns (text, token usage incl. cached).
pub(crate) async fn ask(rr: &ReviewRunner, prompt: String) -> Result<(String, Usage)> {
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
            usage.cached += u.cache_read_input_token_count.unwrap_or(0) as i64;
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
