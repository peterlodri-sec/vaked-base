import { getKindConfig } from "@/graph/kindConfig";
import type { ProvenanceLink } from "@/hooks/useProvenance";

interface SpanLinkProps {
  link: ProvenanceLink;
  isActive: boolean;
  onClick: (nodeId: string) => void;
}

export function SpanLink({ link, isActive, onClick }: SpanLinkProps) {
  const cfg = getKindConfig(link.nodeKind);
  return (
    <div
      onClick={() => onClick(link.nodeId)}
      style={{
        display: "flex",
        alignItems: "center",
        gap: "8px",
        padding: "5px 10px",
        cursor: "pointer",
        background: isActive ? `${cfg.bg}22` : "transparent",
        borderLeft: isActive ? `2px solid ${cfg.bg}` : "2px solid transparent",
        transition: "background 0.1s",
      }}
    >
      <span style={{ fontSize: "12px" }}>{cfg.icon}</span>
      <div>
        <div style={{ color: isActive ? cfg.bg : "#e2e8f0", fontSize: "12px", fontFamily: "monospace" }}>
          {link.nodeName}
        </div>
        <div style={{ color: "#6b7280", fontSize: "10px" }}>
          {link.nodeKind} · L{link.line}:{link.col}
        </div>
      </div>
    </div>
  );
}
