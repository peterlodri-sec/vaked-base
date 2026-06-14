//! adk-rust runner construction, a single agent turn, and the read_file tool.

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;

use adk_core::{Content, GenerateContentConfig, SessionId, UserId};
use adk_rust::prelude::*;
use adk_rust::session::{CreateRequest, SessionService};
use adk_rust::{RetryBudget, ToolExecutionStrategy};
use adk_runner::compaction::{CompactionConfig, TruncationCompaction};
use anyhow::{Result, anyhow};
use futures::StreamExt;
use serde_json::{Value, json};

use crate::config::Config;
use crate::consts::{CACHE_KEY, COMPACTION_BUDGET_TOKENS, COMPACTION_PRESERVE_RECENT};
use crate::guardrails;
use crate::output::output_schema;
use crate::prompts::system_prompt;
use crate::ralph;

pub(crate) struct ProvostRunner {
    pub(crate) runner: Runner,
    pub(crate) sessions: Arc<dyn SessionService>,
}

pub(crate) fn build_runner(cfg: &Config, api_key: &str) -> Result<ProvostRunner> {
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
        .tool(ralph_decisions_tool())
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
pub(crate) async fn ask(rr: &ProvostRunner, prompt: String) -> Result<String> {
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

fn ralph_decisions_tool() -> Arc<dyn Tool> {
    Arc::new(
        FunctionTool::new(
            "get_ralph_decisions",
            "Read the ralph autonomous track decision ledger \
             (tools/ralph/state/events.jsonl) and return a summary of the most \
             recent decided tracks. Call this before proposing epics to avoid \
             duplicating tracks already active in the ralph loop.",
            |_ctx: Arc<dyn ToolContext>, _args: Value| async move {
                let summary = ralph::recent_decisions("tools/ralph/state/events.jsonl", 3);
                Ok(json!({"decisions": summary}))
            },
        )
        .with_read_only(true)
        .with_concurrency_safe(true),
    )
}
