import { useEditorStore, useGraphStore } from "@/store";

export function StatusBar() {
  const lspReady = useEditorStore((s) => s.lspReady);
  const cursorLine = useEditorStore((s) => s.cursorLine);
  const cursorCol = useEditorStore((s) => s.cursorCol);
  const diagnostics = useEditorStore((s) => s.diagnostics);
  const graph = useGraphStore((s) => s.graph);
  const filePath = useGraphStore((s) => s.filePath);

  const errorCount = diagnostics.filter((d) => d.severity === 1).length;
  const nodeCount = graph.nodes.filter((n) => n.kind !== "external").length;
  const edgeCount = graph.edges.length;

  return (
    <div style={{
      display: "flex",
      alignItems: "center",
      gap: "16px",
      padding: "4px 14px",
      background: "rgba(10, 13, 18, 0.98)",
      borderTop: "1px solid #1e293b",
      height: "26px",
      flexShrink: 0,
      fontSize: "11px",
      fontFamily: "monospace",
      color: "#64748b",
    }}>
      {/* LSP & Quantum Telemetry Status */}
      <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
        <span style={{
          width: "7px",
          height: "7px",
          borderRadius: "50%",
          background: lspReady ? "#22c55e" : "#eab308",
          boxShadow: lspReady ? "0 0 8px #22c55e" : "0 0 8px #eab308",
          display: "inline-block",
        }} />
        <span style={{ color: lspReady ? "#4ade80" : "#eab308", fontWeight: 600 }}>
          {lspReady ? "vakedc-lsp [READY]" : "vakedc-lsp [STARTING]"}
        </span>
      </div>

      {/* Diagnostics */}
      {diagnostics.length > 0 && (
        <span style={{ color: errorCount > 0 ? "#f87171" : "#fb923c", fontWeight: 600 }}>
          {errorCount > 0 ? `✕ ${errorCount} E` : ""}{" "}
          {diagnostics.filter((d) => d.severity === 2).length > 0
            ? `⚠ ${diagnostics.filter((d) => d.severity === 2).length} W`
            : ""}
        </span>
      )}

      {/* Graph stats */}
      {nodeCount > 0 && (
        <span style={{ color: "#38bdf8", fontWeight: 500 }}>
          ⚡ {nodeCount} nodes · {edgeCount} edges
        </span>
      )}

      <span style={{ marginLeft: "auto", color: "#94a3b8" }}>
        {filePath ? `Ln ${cursorLine}, Col ${cursorCol}` : (
          <span style={{ color: "#475569" }}>Press ⌘K for command palette</span>
        )}
      </span>

      <span style={{ color: "#cbd5e1", fontWeight: 600, background: "#1e1b4b", padding: "1px 6px", borderRadius: "3px", border: "1px solid #4c1d95" }}>
        vaked-ide v0.1.0
      </span>
    </div>
  );
}

