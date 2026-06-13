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
      padding: "3px 12px",
      background: "#0a0d12",
      borderTop: "1px solid #1f2937",
      height: "24px",
      flexShrink: 0,
      fontSize: "11px",
      fontFamily: "monospace",
      color: "#4b5563",
    }}>
      {/* LSP status */}
      <span style={{ color: lspReady ? "#16a34a" : "#4b5563" }}>
        {lspReady ? "◉ vakedc-lsp" : "○ lsp starting…"}
      </span>

      {/* Diagnostics */}
      {diagnostics.length > 0 && (
        <span style={{ color: errorCount > 0 ? "#ef4444" : "#f97316" }}>
          {errorCount > 0 ? `✕ ${errorCount} E` : ""}{" "}
          {diagnostics.filter((d) => d.severity === 2).length > 0
            ? `⚠ ${diagnostics.filter((d) => d.severity === 2).length} W`
            : ""}
        </span>
      )}

      {/* Graph stats */}
      {nodeCount > 0 && (
        <span>
          {nodeCount} nodes · {edgeCount} edges
        </span>
      )}

      <span style={{ marginLeft: "auto" }}>
        {filePath ? `Ln ${cursorLine}, Col ${cursorCol}` : (
          <span style={{ color: "#374151" }}>⌘K to open commands</span>
        )}
      </span>

      <span>vaked-ide v0.1.0</span>
    </div>
  );
}
