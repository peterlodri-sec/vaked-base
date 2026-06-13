import { useState } from "react";
import { AgentBadge } from "./AgentBadge";
import type { SessionMessage, SuggestedEdit } from "@/types/session";
import { useEditorStore } from "@/store";

interface MessageBubbleProps {
  message: SessionMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";
  const setPendingEdit = useEditorStore((s) => s.setPendingEdit);
  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      alignItems: isUser ? "flex-end" : "flex-start",
      marginBottom: "10px",
      gap: "4px",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
        <AgentBadge role={message.role} />
        <span style={{ color: "#4b5563", fontSize: "10px" }}>
          {new Date(message.timestamp).toLocaleTimeString()}
        </span>
      </div>
      <div style={{
        maxWidth: "90%",
        background: isUser ? "#1e3a5f" : "#111827",
        border: `1px solid ${isUser ? "#1e40af" : "#1f2937"}`,
        borderRadius: isUser ? "12px 12px 2px 12px" : "12px 12px 12px 2px",
        padding: "8px 12px",
        color: "#e2e8f0",
        fontSize: "13px",
        lineHeight: "1.5",
        fontFamily: "ui-sans-serif, system-ui, sans-serif",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
      }}>
        {message.content || (message.isStreaming ? (
          <span style={{ color: "#6b7280" }}>▋</span>
        ) : "")}
        {message.isStreaming && message.content && (
          <span style={{ color: "#6b7280" }}>▋</span>
        )}
      </div>
      {message.suggestedEdit && (
        <SuggestEditCard edit={message.suggestedEdit} onAccept={() => setPendingEdit(message.suggestedEdit!)} />
      )}
    </div>
  );
}

function SuggestEditCard({ edit, onAccept }: { edit: SuggestedEdit; onAccept: () => void }) {
  const [dismissed, setDismissed] = useState(false);
  const [accepted, setAccepted] = useState(false);

  if (dismissed) return null;

  return (
    <div style={{
      maxWidth: "90%",
      background: accepted ? "#052e16" : "#0d1117",
      border: `1px solid ${accepted ? "#16a34a" : "#374151"}`,
      borderRadius: "8px",
      overflow: "hidden",
      fontSize: "12px",
      fontFamily: "monospace",
      transition: "border-color 0.2s",
    }}>
      {/* Header */}
      <div style={{
        display: "flex",
        alignItems: "center",
        gap: "6px",
        padding: "6px 10px",
        background: "#111827",
        borderBottom: "1px solid #1f2937",
      }}>
        <span style={{ color: "#6366f1", fontSize: "11px" }}>✎</span>
        <span style={{ color: "#9ca3af", fontSize: "11px", flex: 1 }}>Suggested edit</span>
        <span style={{ color: "#4b5563", fontSize: "10px" }}>
          Ln {edit.range.startLine}–{edit.range.endLine}
        </span>
      </div>

      {/* Diff preview */}
      <pre style={{
        margin: 0,
        padding: "8px 10px",
        color: "#86efac",
        whiteSpace: "pre-wrap",
        wordBreak: "break-word",
        maxHeight: "120px",
        overflowY: "auto",
        borderBottom: "1px solid #1f2937",
      }}>
        {edit.newText}
      </pre>

      {/* Rationale */}
      {edit.rationale && (
        <div style={{ padding: "5px 10px", color: "#6b7280", fontFamily: "sans-serif", fontSize: "11px", borderBottom: "1px solid #1f2937" }}>
          {edit.rationale}
        </div>
      )}

      {/* Actions */}
      {!accepted ? (
        <div style={{ display: "flex", gap: "1px" }}>
          <button
            onClick={() => { setAccepted(true); onAccept(); }}
            style={{
              flex: 1,
              background: "#052e16",
              border: "none",
              color: "#4ade80",
              padding: "6px",
              cursor: "pointer",
              fontSize: "11px",
              fontFamily: "monospace",
              transition: "background 0.1s",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "#14532d")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "#052e16")}
          >
            ✓ Accept
          </button>
          <button
            onClick={() => setDismissed(true)}
            style={{
              flex: 1,
              background: "#1f1215",
              border: "none",
              color: "#f87171",
              padding: "6px",
              cursor: "pointer",
              fontSize: "11px",
              fontFamily: "monospace",
              transition: "background 0.1s",
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = "#2d1515")}
            onMouseLeave={(e) => (e.currentTarget.style.background = "#1f1215")}
          >
            ✕ Reject
          </button>
        </div>
      ) : (
        <div style={{ padding: "5px 10px", color: "#16a34a", fontSize: "11px", fontFamily: "sans-serif" }}>
          ✓ Applied to editor
        </div>
      )}
    </div>
  );
}
