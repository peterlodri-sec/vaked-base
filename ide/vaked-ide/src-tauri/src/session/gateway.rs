use crate::error::{AppError, Result};

const ROUTER_SYSTEM: &str = r#"You are the gateway router for the Vaked IDE.
Your job: classify the user's query and route it to the best sub-agent.

Available sub-agents:
- schema-advisor: questions about field types, constraints, schema conformance, missing required fields
- capability-expert: questions about POLA attenuation, capability domains, grant order lattices, mesh delegation
- lowering-guide: questions about flake.nix output, Nix spine, artifact emission, provenance.json

Respond with ONLY valid JSON:
{"routedTo": "<sub-agent-id>", "rationale": "<one sentence why>"}"#;

pub const SUB_AGENT_SYSTEMS: &[(&str, &str)] = &[
    ("schema-advisor", r#"You are a Vaked schema expert.

Focus on: field types (String, Int, Float, Bool, Path, Duration, Bytes, Null, List<T>, Record),
structural typing rules, conformance checking (required/optional/default fields),
constraint set (oneof, ranges >=/<=/>/< , in lo..hi, nonempty, matches /regex/),
and schema declarations.

Diagnostic codes you know: E-CONFORM-MISSING-FIELD, E-CONFORM-TYPE-MISMATCH,
E-CONFORM-UNKNOWN-FIELD, E-CONFORM-CLOSED, E-CONSTRAINT-*.

Be precise. Reference specific field names and types from the user's graph context."#),

    ("capability-expert", r#"You are a Vaked capability expert.

Focus on: the six domains (fs, network, mcp, ebpf, process, mem),
grant partial orders (a < b means a is weaker than b),
POLA attenuation on mesh edges (a -> b: receiver grants ⊆ sender grants),
capability declarations, order chains.

Diagnostic codes: E-CAP-ESCALATION, E-CAP-UNRESOLVED-GRANT, E-CAP-ORDER-CYCLE.

Visualize the grant lattice when helpful. Explain attenuation violations precisely."#),

    ("lowering-guide", r#"You are a Vaked lowering and artifact expert.

Focus on: flake.nix Nix spine generation (0012), per-kind emitters
(NixOS modules, Zig daemon configs, eBPF manifests, OTel config, CrabCC indexes),
provenance.json, inputsHash, byte-identical re-lowering.

The surface kind emits a deferred apps.<name> stub — vaked-ide is the surface launcher.
Explain how each declaration maps to its artifact."#),
];

pub fn get_sub_agent_system(role: &str) -> &'static str {
    SUB_AGENT_SYSTEMS
        .iter()
        .find(|(id, _)| *id == role)
        .map(|(_, sys)| *sys)
        .unwrap_or("You are a Vaked expert.")
}

pub fn build_router_request(query: &str, graph_context: &str) -> serde_json::Value {
    let user_msg = if graph_context.is_empty() {
        query.to_string()
    } else {
        format!("Graph context:\n```json\n{graph_context}\n```\n\nQuery: {query}")
    };

    serde_json::json!({
        "model": "claude-opus-4-8",
        "max_tokens": 256,
        "stream": false,
        "system": ROUTER_SYSTEM,
        "messages": [{"role": "user", "content": user_msg}]
    })
}

pub fn build_sub_agent_request(
    role: &str,
    query: &str,
    graph_context: &str,
) -> serde_json::Value {
    let system = get_sub_agent_system(role);
    let user_msg = if graph_context.is_empty() {
        query.to_string()
    } else {
        format!("Graph context:\n```json\n{graph_context}\n```\n\n{query}")
    };

    serde_json::json!({
        "model": "claude-sonnet-4-6",
        "max_tokens": 4096,
        "stream": true,
        "system": system,
        "messages": [{"role": "user", "content": user_msg}]
    })
}
