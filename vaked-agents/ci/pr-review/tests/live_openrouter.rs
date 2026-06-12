//! Live smoke test for the adk-rust → OpenRouter → Runner path.
//!
//! Ignored by default (hits the network and spends a fraction of a cent). Run it
//! with a key when you want to confirm the agent stack actually talks to GLM-4.6:
//!
//!   OPENROUTER_API_KEY=sk-or-... \
//!     cargo test --manifest-path vaked-agents/ci/pr-review/Cargo.toml \
//!     --test live_openrouter -- --ignored --nocapture

use std::collections::HashMap;
use std::sync::Arc;

use adk_core::{SessionId, UserId};
use adk_rust::prelude::*;
use adk_rust::session::{CreateRequest, SessionService};
use futures::StreamExt;

#[tokio::test]
#[ignore = "requires OPENROUTER_API_KEY and network"]
async fn glm_roundtrip() {
    let key = std::env::var("OPENROUTER_API_KEY").expect("OPENROUTER_API_KEY");
    let model = std::env::var("PR_REVIEW_MODEL").unwrap_or_else(|_| "z-ai/glm-4.6".to_string());

    let config =
        OpenRouterConfig::new(key, model).with_default_api_mode(OpenRouterApiMode::ChatCompletions);
    let client = OpenRouterClient::new(config).expect("client");

    let agent = LlmAgentBuilder::new("smoke")
        .instruction("You are terse. Reply with exactly one word.")
        .model(Arc::new(client))
        .build()
        .expect("agent");

    let sessions: Arc<dyn SessionService> = Arc::new(InMemorySessionService::new());
    let sid = SessionId::generate();
    sessions
        .create(CreateRequest {
            app_name: "smoke".into(),
            user_id: "t".into(),
            session_id: Some(sid.to_string()),
            state: HashMap::new(),
        })
        .await
        .expect("session");

    let runner = Runner::builder()
        .app_name("smoke")
        .agent(Arc::new(agent))
        .session_service(sessions)
        .build()
        .expect("runner");

    let content = Content::new("user").with_text("Say the word PONG and nothing else.");
    let mut stream = runner
        .run(UserId::new("t").unwrap(), sid, content)
        .await
        .expect("run");

    let mut out = String::new();
    while let Some(ev) = stream.next().await {
        let ev = ev.expect("event");
        if let Some(c) = &ev.llm_response.content {
            for p in &c.parts {
                if let Some(t) = p.text() {
                    out.push_str(t);
                }
            }
        }
    }
    println!("model said: {out:?}");
    assert!(
        out.to_uppercase().contains("PONG"),
        "expected PONG, got {out:?}"
    );
}
