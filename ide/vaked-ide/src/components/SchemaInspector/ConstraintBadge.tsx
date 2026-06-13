interface ConstraintBadgeProps {
  constraint: string;
}

const CONSTRAINT_COLORS: Record<string, string> = {
  required: "#ef4444",
  optional: "#6b7280",
  nonempty: "#f97316",
  default:  "#22c55e",
  oneof:    "#a78bfa",
  matches:  "#38bdf8",
  in:       "#fb923c",
};

export function ConstraintBadge({ constraint }: ConstraintBadgeProps) {
  const keyword = constraint.split(/[\s(]/)[0];
  const color = CONSTRAINT_COLORS[keyword] ?? "#6b7280";
  return (
    <span style={{
      display: "inline-block",
      background: `${color}22`,
      border: `1px solid ${color}66`,
      color,
      borderRadius: "4px",
      padding: "1px 6px",
      fontSize: "10px",
      fontFamily: "monospace",
      marginRight: "4px",
      marginTop: "2px",
    }}>
      {constraint}
    </span>
  );
}
