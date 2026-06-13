import { ConstraintBadge } from "./ConstraintBadge";

export interface FieldSpec {
  name: string;
  type: string;
  constraints: string[];
  value?: unknown;
}

interface FieldRowProps {
  field: FieldSpec;
  hasError?: boolean;
}

export function FieldRow({ field, hasError }: FieldRowProps) {
  return (
    <div style={{
      padding: "6px 10px",
      borderBottom: "1px solid #1f2937",
      background: hasError ? "rgba(239,68,68,0.05)" : "transparent",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={{
          color: hasError ? "#ef4444" : "#34d399",
          fontFamily: "monospace",
          fontSize: "12px",
          fontWeight: 600,
        }}>
          {field.name}
        </span>
        <span style={{ color: "#94a3b8", fontFamily: "monospace", fontSize: "11px" }}>
          {field.type}
        </span>
      </div>
      <div style={{ marginTop: "3px" }}>
        {field.constraints.map((c, i) => (
          <ConstraintBadge key={i} constraint={c} />
        ))}
      </div>
      {field.value !== undefined && (
        <div style={{
          marginTop: "3px",
          color: "#86efac",
          fontFamily: "monospace",
          fontSize: "11px",
          opacity: 0.8,
        }}>
          = {JSON.stringify(field.value)}
        </div>
      )}
    </div>
  );
}
