import type { AgentRole } from "@/types/session";
import { AGENT_LABELS, AGENT_COLORS } from "@/types/session";

interface AgentBadgeProps {
  role: AgentRole;
  size?: "sm" | "md";
}

export function AgentBadge({ role, size = "sm" }: AgentBadgeProps) {
  const color = AGENT_COLORS[role] ?? "#6b7280";
  const label = AGENT_LABELS[role] ?? role;
  const fontSize = size === "sm" ? "10px" : "12px";
  return (
    <span style={{
      display: "inline-flex",
      alignItems: "center",
      gap: "4px",
      background: `${color}22`,
      border: `1px solid ${color}66`,
      color,
      borderRadius: "12px",
      padding: size === "sm" ? "1px 7px" : "2px 10px",
      fontSize,
      fontFamily: "monospace",
      fontWeight: 600,
      letterSpacing: "0.03em",
    }}>
      <span style={{
        width: size === "sm" ? "6px" : "8px",
        height: size === "sm" ? "6px" : "8px",
        borderRadius: "50%",
        background: color,
        display: "inline-block",
        flexShrink: 0,
      }} />
      {label}
    </span>
  );
}
