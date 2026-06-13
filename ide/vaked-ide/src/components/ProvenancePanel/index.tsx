import { SpanLink } from "./SpanLink";
import { useProvenance } from "@/hooks/useProvenance";
import { useGraphStore } from "@/store";

export function ProvenancePanel() {
  const { links, navigateToNode } = useProvenance();
  const highlightedNodeId = useGraphStore((s) => s.highlightedNodeId);

  if (links.length === 0) {
    return (
      <div style={{ padding: "16px", color: "#6b7280", fontSize: "13px" }}>
        No provenance spans. Open a .vaked file.
      </div>
    );
  }

  return (
    <div style={{ overflow: "auto", height: "100%" }}>
      <div style={{
        padding: "6px 10px",
        color: "#6b7280",
        fontSize: "11px",
        textTransform: "uppercase",
        letterSpacing: "0.05em",
        borderBottom: "1px solid #1f2937",
      }}>
        Declarations ({links.length})
      </div>
      {links.map((link) => (
        <SpanLink
          key={link.nodeId}
          link={link}
          isActive={link.nodeId === highlightedNodeId}
          onClick={navigateToNode}
        />
      ))}
    </div>
  );
}
