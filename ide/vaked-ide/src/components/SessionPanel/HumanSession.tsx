import { useState, useRef, useEffect } from "react";
import { MessageBubble } from "./MessageBubble";
import { useSessionStore } from "@/store";
import { useSession } from "@/hooks/useSession";

interface HumanSessionProps {
  sessionId: string;
}

export function HumanSession({ sessionId }: HumanSessionProps) {
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { sendMessage } = useSession();
  const session = useSessionStore((s) => s.sessions.get(sessionId));

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.messages.length]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || sending) return;
    setInput("");
    setSending(true);
    try {
      await sendMessage(sessionId, text);
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      handleSend();
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Messages */}
      <div style={{ flex: 1, overflow: "auto", padding: "12px" }}>
        {!session?.messages.length && (
          <div style={{ color: "#6b7280", fontSize: "13px", textAlign: "center", marginTop: "20px" }}>
            Ask Claude about your .vaked file.<br />
            <span style={{ fontSize: "11px", opacity: 0.6 }}>
              The current graph is automatically included as context.
            </span>
          </div>
        )}
        {session?.messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div style={{
        padding: "10px",
        borderTop: "1px solid #1f2937",
        display: "flex",
        gap: "8px",
      }}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask about the graph… (⌘+Enter to send)"
          disabled={sending}
          style={{
            flex: 1,
            background: "#111827",
            border: "1px solid #374151",
            borderRadius: "8px",
            color: "#e2e8f0",
            fontSize: "13px",
            padding: "8px 10px",
            resize: "none",
            minHeight: "60px",
            fontFamily: "ui-sans-serif, system-ui, sans-serif",
            outline: "none",
          }}
        />
        <button
          onClick={handleSend}
          disabled={sending || !input.trim()}
          style={{
            background: sending ? "#374151" : "#f97316",
            border: "none",
            borderRadius: "8px",
            color: "#fff",
            padding: "0 16px",
            cursor: sending || !input.trim() ? "not-allowed" : "pointer",
            fontSize: "18px",
            opacity: !input.trim() ? 0.4 : 1,
            transition: "opacity 0.1s",
          }}
        >
          {sending ? "⟳" : "↑"}
        </button>
      </div>
    </div>
  );
}
