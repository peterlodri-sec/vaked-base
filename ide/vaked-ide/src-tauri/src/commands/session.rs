use std::sync::Arc;
use tauri::{AppHandle, Emitter, State};
use uuid::Uuid;

use crate::error::{AppError, Result};
use crate::session::gateway::{build_router_request, build_sub_agent_request};
use crate::session::human::{build_request_body, parse_sse_chunk, StreamEvent};
use crate::session::{Message, SessionState};

const ANTHROPIC_URL: &str = "https://api.anthropic.com/v1/messages";

async fn call_anthropic_stream(
    api_key: &str,
    body: serde_json::Value,
    session_id: &str,
    agent_role: &str,
    app: &AppHandle,
) -> Result<String> {
    let client = reqwest::Client::new();
    let response = client
        .post(ANTHROPIC_URL)
        .header("x-api-key", api_key)
        .header("anthropic-version", "2023-06-01")
        .header("content-type", "application/json")
        .json(&body)
        .send()
        .await?;

    if !response.status().is_success() {
        let err_text = response.text().await.unwrap_or_default();
        return Err(AppError(format!("Anthropic API error: {err_text}")));
    }

    use futures_util::StreamExt;
    let mut stream = response.bytes_stream();
    let mut full_text = String::new();
    let mut buf = String::new();

    while let Some(chunk) = stream.next().await {
        let bytes = chunk.map_err(|e| AppError(e.to_string()))?;
        buf.push_str(&String::from_utf8_lossy(&bytes));

        // Process complete SSE lines
        while let Some(pos) = buf.find('\n') {
            let line = buf[..pos].to_string();
            buf = buf[pos + 1..].to_string();

            if let Some(event) = parse_sse_chunk(&line) {
                match event {
                    StreamEvent::TextDelta(text) => {
                        full_text.push_str(&text);
                        let _ = app.emit(
                            "session-stream-chunk",
                            serde_json::json!({
                                "session_id": session_id,
                                "agent_role": agent_role,
                                "text": text
                            }),
                        );
                    }
                    StreamEvent::Done => {
                        let _ = app.emit(
                            "session-stream-done",
                            serde_json::json!({
                                "session_id": session_id,
                                "agent_role": agent_role,
                            }),
                        );
                    }
                }
            }
        }
    }

    Ok(full_text)
}

async fn call_anthropic_sync(api_key: &str, body: serde_json::Value) -> Result<String> {
    let client = reqwest::Client::new();
    let response = client
        .post(ANTHROPIC_URL)
        .header("x-api-key", api_key)
        .header("anthropic-version", "2023-06-01")
        .header("content-type", "application/json")
        .json(&body)
        .send()
        .await?;

    if !response.status().is_success() {
        let err_text = response.text().await.unwrap_or_default();
        return Err(AppError(format!("Anthropic API error: {err_text}")));
    }

    let v: serde_json::Value = response.json().await?;
    Ok(v["content"][0]["text"].as_str().unwrap_or("").to_string())
}

#[tauri::command]
pub async fn create_session(
    kind: String,
    label: String,
    state: State<'_, SessionState>,
    app: AppHandle,
) -> std::result::Result<String, AppError> {
    let session_id = Uuid::new_v4().to_string();
    let mut sessions = state.sessions.lock().await;
    sessions.insert(session_id.clone(), Vec::new());

    // For a2a sessions, start/ensure the Yjs relay and emit the port
    if kind == "a2a" {
        let mut port_guard = state.yjs_port.lock().await;
        if port_guard.is_none() {
            let port = crate::session::a2a::start_yjs_relay()
                .await
                .map_err(|e| AppError(e.to_string()))?;
            *port_guard = Some(port);
        }
        let port = port_guard.unwrap();
        let _ = app.emit("yjs-port", port);
    }

    Ok(session_id)
}

#[tauri::command]
pub async fn send_session_message(
    session_id: String,
    content: String,
    graph_context: Option<String>,
    state: State<'_, SessionState>,
    app: AppHandle,
) -> std::result::Result<(), AppError> {
    let api_key = state.api_key.clone();
    if api_key.is_empty() {
        return Err(AppError("ANTHROPIC_API_KEY not set".into()));
    }

    // Append user message to history
    {
        let mut sessions = state.sessions.lock().await;
        if let Some(history) = sessions.get_mut(&session_id) {
            history.push(Message {
                role: "user".into(),
                content: content.clone(),
            });
        }
    }

    let history = {
        let sessions = state.sessions.lock().await;
        sessions.get(&session_id).cloned().unwrap_or_default()
    };

    let body = build_request_body(&history, graph_context.as_deref());

    let full_text = call_anthropic_stream(
        &api_key,
        body,
        &session_id,
        "claude",
        &app,
    )
    .await?;

    // Append assistant response to history
    {
        let mut sessions = state.sessions.lock().await;
        if let Some(history) = sessions.get_mut(&session_id) {
            history.push(Message {
                role: "assistant".into(),
                content: full_text,
            });
        }
    }

    Ok(())
}

#[tauri::command]
pub async fn gateway_route(
    session_id: String,
    query: String,
    graph_context: String,
    state: State<'_, SessionState>,
    app: AppHandle,
) -> std::result::Result<String, AppError> {
    let api_key = state.api_key.clone();
    if api_key.is_empty() {
        return Err(AppError("ANTHROPIC_API_KEY not set".into()));
    }

    // Step 1: Router call (sync, fast, opus)
    let router_body = build_router_request(&query, &graph_context);
    let route_json = call_anthropic_sync(&api_key, router_body).await?;

    let route: serde_json::Value =
        serde_json::from_str(&route_json).unwrap_or(serde_json::json!({
            "routedTo": "schema-advisor",
            "rationale": "fallback"
        }));

    let routed_to = route["routedTo"].as_str().unwrap_or("schema-advisor").to_string();
    let rationale = route["rationale"].as_str().unwrap_or("").to_string();

    let route_result = serde_json::json!({
        "routedTo": routed_to,
        "rationale": rationale
    });

    // Emit routing decision
    let _ = app.emit(
        "session-gateway-route",
        serde_json::json!({
            "session_id": session_id,
            "route": route_result
        }),
    );

    // Step 2: Sub-agent call (streaming)
    let sub_body = build_sub_agent_request(&routed_to, &query, &graph_context);
    call_anthropic_stream(&api_key, sub_body, &session_id, &routed_to, &app).await?;

    Ok(serde_json::to_string(&route_result).unwrap_or_default())
}

#[tauri::command]
pub async fn get_yjs_port(
    state: State<'_, SessionState>,
) -> std::result::Result<Option<u16>, AppError> {
    let guard = state.yjs_port.lock().await;
    Ok(*guard)
}
