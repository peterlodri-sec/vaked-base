import { FieldRow, type FieldSpec } from "./FieldRow";
import { useGraphStore } from "@/store";
import { getKindConfig } from "@/graph/kindConfig";
import type { VakedNode } from "@/types/graph";

// Hardcoded field specs for core kinds (matches vaked/schema/builtins.vaked)
const KIND_FIELDS: Record<string, FieldSpec[]> = {
  index: [
    { name: "source", type: "Source | List<Source>", constraints: ["required"] },
    { name: "normalize", type: "Normalizer", constraints: ["optional"] },
    { name: "chunk", type: "ChunkSpec", constraints: ["optional"] },
    { name: "emit", type: "ArtifactTarget", constraints: ["required"] },
    { name: "schema", type: "schema ref", constraints: ["optional"] },
    { name: "trust", type: "String", constraints: ["optional"] },
  ],
  catalog: [
    { name: "from", type: "index ref", constraints: ["required"] },
    { name: "key", type: "List<String>", constraints: ["required", "nonempty"] },
    { name: "emit", type: "ArtifactTarget", constraints: ["required"] },
  ],
  stream: [
    { name: "source", type: "Source", constraints: ["required"] },
    { name: "type", type: "schema ref", constraints: ["required"] },
    { name: "retention", type: "Duration", constraints: ["optional"] },
    { name: "fps", type: "Int", constraints: ["optional", "> 0"] },
  ],
  fiber: [
    { name: "engine", type: "engine ref", constraints: ["required"] },
    { name: "input", type: "stream ref", constraints: ["required"] },
    { name: "output", type: "ArtifactTarget", constraints: ["required"] },
    { name: "policy", type: "Policy { ... }", constraints: ["optional"] },
  ],
  surface: [
    { name: "mode", type: "SurfaceMode", constraints: ["required", "oneof [raylib]"] },
    { name: "fps", type: "Int", constraints: ["optional", "> 0"] },
    { name: "input", type: "List<Stream | Graph | Catalog>", constraints: ["required", "nonempty"] },
    { name: "views", type: "List<String>", constraints: ["required", "nonempty"] },
    { name: "budget", type: "budget ref", constraints: ["optional"] },
  ],
  mesh: [
    { name: "node declarations", type: "node name { role?, capabilities? }", constraints: ["open"] },
    { name: "edges", type: "ref -> ref [: label]", constraints: ["open"] },
  ],
  workflow: [
    { name: "step declarations", type: "use agent on(stream) { ... }", constraints: ["open"] },
    { name: "edges", type: "step -> step [: label]", constraints: ["open"] },
  ],
  parallel: [
    { name: "fibers", type: "List<fiber ref>", constraints: ["required", "nonempty"] },
    { name: "strategy", type: "String", constraints: ["optional"] },
    { name: "supervisor", type: "Supervisor", constraints: ["optional", "default = otp"] },
  ],
  memory: [
    { name: "source", type: "List<stream ref>", constraints: ["required", "nonempty"] },
    { name: "schema", type: "schema ref", constraints: ["optional"] },
    { name: "mine", type: "Normalizer", constraints: ["required"] },
    { name: "scope", type: "String", constraints: ["optional", "oneof [session, agent, runtime]"] },
    { name: "retention", type: "Duration", constraints: ["optional"] },
    { name: "emit", type: "ArtifactTarget", constraints: ["optional"] },
  ],
  budget: [
    { name: "tokens", type: "Int", constraints: ["optional"] },
    { name: "wallClock", type: "Duration", constraints: ["optional"] },
    { name: "toolCalls", type: "Int", constraints: ["optional"] },
    { name: "fuel", type: "Int", constraints: ["optional"] },
  ],
};

function getFieldsForNode(node: VakedNode): FieldSpec[] {
  const base = KIND_FIELDS[node.kind] ?? [];
  // Augment with actual props values where we have them
  return base.map((f) => {
    const propValue = node.props[f.name];
    return propValue !== undefined ? { ...f, value: propValue } : f;
  });
}

export function SchemaInspector() {
  const selectedNodeId = useGraphStore((s) => s.selectedNodeId);
  const graph = useGraphStore((s) => s.graph);

  const node = selectedNodeId
    ? graph.nodes.find((n) => n.id === selectedNodeId) ?? null
    : null;

  if (!node) {
    return (
      <div style={{ padding: "16px", color: "#6b7280", fontSize: "13px" }}>
        Select a node to inspect its schema.
      </div>
    );
  }

  const cfg = getKindConfig(node.kind);
  const fields = getFieldsForNode(node);

  return (
    <div style={{ overflow: "auto", height: "100%" }}>
      {/* Header */}
      <div style={{
        background: cfg.bg,
        padding: "10px 12px",
        display: "flex",
        alignItems: "center",
        gap: "8px",
        borderBottom: "1px solid #1f2937",
      }}>
        <span style={{ fontSize: "18px" }}>{cfg.icon}</span>
        <div>
          <div style={{ color: cfg.color, fontSize: "11px", opacity: 0.8, textTransform: "uppercase" }}>
            {cfg.label}
          </div>
          <div style={{ color: cfg.color, fontSize: "14px", fontFamily: "monospace", fontWeight: 700 }}>
            {node.name}
          </div>
        </div>
      </div>

      {/* Node ID */}
      <div style={{ padding: "6px 10px", color: "#4b5563", fontSize: "10px", fontFamily: "monospace" }}>
        id: {node.id}
      </div>

      {/* Fields */}
      <div>
        <div style={{ padding: "6px 10px", color: "#6b7280", fontSize: "11px", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Schema Fields
        </div>
        {fields.length > 0 ? (
          fields.map((f, i) => <FieldRow key={i} field={f} />)
        ) : (
          <div style={{ padding: "8px 10px", color: "#6b7280", fontSize: "12px" }}>
            Schema is open (no closed field set for {node.kind})
          </div>
        )}
      </div>

      {/* Labels */}
      {node.labels.length > 0 && (
        <div style={{ padding: "8px 10px", borderTop: "1px solid #1f2937" }}>
          <div style={{ color: "#6b7280", fontSize: "11px", marginBottom: "4px" }}>Labels</div>
          <div>
            {node.labels.map((l, i) => (
              <span key={i} style={{
                display: "inline-block",
                background: "#1f2937",
                borderRadius: "4px",
                padding: "1px 6px",
                fontSize: "11px",
                fontFamily: "monospace",
                color: "#9ca3af",
                marginRight: "4px",
              }}>
                {l}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Provenance */}
      {node.provenance && (
        <div style={{ padding: "8px 10px", borderTop: "1px solid #1f2937" }}>
          <div style={{ color: "#6b7280", fontSize: "11px", marginBottom: "4px" }}>Provenance</div>
          <div style={{ color: "#4b5563", fontSize: "11px", fontFamily: "monospace" }}>
            {node.provenance.file}:{node.provenance.span.line}:{node.provenance.span.col}
          </div>
        </div>
      )}
    </div>
  );
}
