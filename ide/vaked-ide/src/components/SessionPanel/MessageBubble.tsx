import { AgentBadge } from "./AgentBadge";
import type { SessionMessage } from "@/types/session";

interface MessageBubbleProps {
  message: SessionMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";
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
        <div style={{
          maxWidth: "90%",
          background: "#052e16",
          border: "1px solid #16a34a",
          borderRadius: "8px",
          padding: "8px 12px",
          fontSize: "12px",
          color: "#86efac",
          fontFamily: "monospace",
        }}>
          <div style={{ color: "#16a34a", marginBottom: "4px", fontSize: "11px" }}>
            ✎ Suggested edit
          </div>
          <pre style={{ margin: 0, whiteSpace: "pre-wrap" }}>
            {message.suggestedEdit.newText}
          </pre>
          <div style={{ color: "#6b7280", marginTop: "4px", fontFamily: "sans-serif", fontSize: "11px" }}>
            {message.suggestedEdit.rationale}
          </div>
        </div>
      )}
    </div>
  );
}
