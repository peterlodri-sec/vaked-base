import { memo } from "react";
import { Handle, Position } from "@xyflow/react";
import type { NodeProps } from "@xyflow/react";
import type { RFNodeData } from "@/types/graph";
import { getKindConfig } from "@/graph/kindConfig";

export const VakedNode = memo(function VakedNode({ data, selected }: NodeProps<RFNodeData>) {
  const { vakedNode, highlighted, hasErrors } = data;
  const cfg = getKindConfig(vakedNode.kind);

  const borderColor = hasErrors
    ? "#ef4444"
    : highlighted
    ? "#fbbf24"
    : selected
    ? "#60a5fa"
    : cfg.border;

  return (
    <div
      style={{
        background: cfg.bg,
        border: `2px solid ${borderColor}`,
        borderRadius: cfg.shape === "rounded" ? "12px" : "6px",
        padding: "6px 12px",
        minWidth: "160px",
        color: cfg.color,
        boxShadow: highlighted || selected ? "0 0 0 3px rgba(251,191,36,0.3)" : "0 2px 6px rgba(0,0,0,0.4)",
        transition: "box-shadow 0.15s ease",
        cursor: "pointer",
        userSelect: "none",
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: cfg.border }} />

      <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
        <span style={{ fontSize: "14px" }}>{cfg.icon}</span>
        <div>
          <div style={{ fontSize: "10px", opacity: 0.75, textTransform: "uppercase", letterSpacing: "0.05em" }}>
            {cfg.label}
          </div>
          <div style={{ fontSize: "13px", fontWeight: 600, fontFamily: "monospace" }}>
            {vakedNode.name}
          </div>
        </div>
        {hasErrors && (
          <span style={{ marginLeft: "auto", color: "#ef4444", fontSize: "14px" }} title="Has diagnostics">
            ⚠
          </span>
        )}
      </div>

      <Handle type="source" position={Position.Right} style={{ background: cfg.border }} />
    </div>
  );
});
