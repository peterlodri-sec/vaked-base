use crate::error::{AppError, Result};
use crate::session::{Message, SessionState};

const SYSTEM_PROMPT: &str = r#"You are an expert assistant for the Vaked capability-graph language.

Vaked is a flake-native language that declares typed semantic graphs. Key primitives:
- runtime, index, catalog, stream, fiber, surface, mesh, device, mediaPipeline, parallel
- workflow (typed agent-step DAG), schema, capability, memory, budget, runclass

The type system (0011) uses structural typing with a closed constraint set:
  required, optional, default, oneof, ranges (>=, <=, >, <, in lo..hi), nonempty, matches /regex/

Capabilities are declared with POLA attenuation: grant order forms partial orders per domain
(fs, network, mcp, ebpf, process, mem). A mesh edge `a -> b` delegates grants from a to b.
The receiver's grant-set must be ⊆ the sender's.

Diagnostic codes: E-CONFORM-* (conformance), E-CONSTRAINT-* (field constraints),
E-CAP-* (capability), E-GENERIC-* (generics), E-REF-UNRESOLVED.

When asked to suggest edits, respond with:
<suggest_edit>
range: {"startLine": N, "startCol": N, "endLine": N, "endCol": N}
newText: |
  ... replacement text ...
rationale: why this change fixes the issue
</suggest_edit>

Be concise. Explain the graph semantics. Always reference specific field names and kind schemas."#;

pub fn build_request_body(
    history: &[Message],
    graph_context: Option<&str>,
) -> serde_json::Value {
    let mut messages: Vec<serde_json::Value> = history
        .iter()
        .map(|m| {
            serde_json::json!({
                "role": m.role,
                "content": m.content
            })
        })
        .collect();

    // Inject graph context before the last user message
    if let Some(ctx) = graph_context {
        if !ctx.is_empty() {
            // Find last user message index and prepend context
            if let Some(last) = messages.last_mut() {
                if last["role"] == "user" {
                    let original = last["content"].as_str().unwrap_or("").to_string();
                    last["content"] = serde_json::Value::String(format!(
                        "Current Vaked graph (LPG JSON):\n```json\n{ctx}\n```\n\n{original}"
                    ));
                }
            }
        }
    }

    serde_json::json!({
        "model": "claude-sonnet-4-6",
        "max_tokens": 4096,
        "stream": true,
        "system": SYSTEM_PROMPT,
        "messages": messages
    })
}

/// Parse SSE data lines from the Anthropic streaming response.
/// Returns Some(text_delta) when a content text delta is found, None otherwise.
pub fn parse_sse_chunk(data: &str) -> Option<StreamEvent> {
    let trimmed = data.trim();
    if !trimmed.starts_with("data: ") {
        return None;
    }
    let json_str = &trimmed["data: ".len()..];
    if json_str == "[DONE]" {
        return Some(StreamEvent::Done);
    }
    let v: serde_json::Value = serde_json::from_str(json_str).ok()?;
    match v["type"].as_str()? {
        "content_block_delta" => {
            let text = v["delta"]["text"].as_str()?.to_string();
            Some(StreamEvent::TextDelta(text))
        }
        "message_stop" => Some(StreamEvent::Done),
        _ => None,
    }
}

pub enum StreamEvent {
    TextDelta(String),
    Done,
}
