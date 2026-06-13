import { useState, useRef, useEffect } from "react";
import { MessageBubble } from "./MessageBubble";
import { AgentBadge } from "./AgentBadge";
import { useSessionStore } from "@/store";
import { useSession } from "@/hooks/useSession";
import type { AgentRole } from "@/types/session";

interface GatewaySessionProps {
  sessionId: string;
}

const SUGGESTED_QUERIES = [
  "Why is this mesh delegation invalid?",
  "What fields is this fiber missing?",
  "How does this surface get materialized?",
  "Explain the capability attenuation in this workflow.",
];

export function GatewaySession({ sessionId }: GatewaySessionProps) {
  const [input, setInput] = useState("");
  const [routing, setRouting] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { gatewayRoute } = useSession();
  const session = useSessionStore((s) => s.sessions.get(sessionId));

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [session?.messages.length]);

  const handleRoute = async (query?: string) => {
    const text = (query ?? input).trim();
    if (!text || routing) return;
    setInput("");
    setRouting(true);
    try {
      await gatewayRoute(sessionId, text);
    } finally {
      setRouting(false);
    }
  };

  const lastRoute = session?.lastRoute;

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%" }}>
      {/* Route indicator */}
      {lastRoute && (
        <div style={{
          padding: "8px 12px",
          background: "#111827",
          borderBottom: "1px solid #1f2937",
          display: "flex",
          alignItems: "center",
          gap: "8px",
          fontSize: "11px",
        }}>
          <span style={{ color: "#6b7280" }}>Last route →</span>
          <AgentBadge role={lastRoute.routedTo as AgentRole} />
          <span style={{ color: "#4b5563" }}>{lastRoute.rationale}</span>
        </div>
      )}

      {/* Messages */}
      <div style={{ flex: 1, overflow: "auto", padding: "12px" }}>
        {!session?.messages.length && (
          <div>
            <div style={{ color: "#6b7280", fontSize: "13px", marginBottom: "12px", textAlign: "center" }}>
              Gateway routes your query to the best sub-agent.
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: "6px" }}>
              {SUGGESTED_QUERIES.map((q) => (
                <button
                  key={q}
                  onClick={() => handleRoute(q)}
                  style={{
                    background: "#111827",
                    border: "1px solid #1f2937",
                    borderRadius: "8px",
                    color: "#9ca3af",
                    padding: "8px 12px",
                    textAlign: "left",
                    cursor: "pointer",
                    fontSize: "12px",
                    fontFamily: "ui-sans-serif, system-ui, sans-serif",
                    transition: "border-color 0.1s",
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.borderColor = "#374151")}
                  onMouseLeave={(e) => (e.currentTarget.style.borderColor = "#1f2937")}
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}
        {session?.messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div style={{ padding: "10px", borderTop: "1px solid #1f2937", display: "flex", gap: "8px" }}>
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleRoute(); }}
          placeholder="Ask a Vaked question… (⌘+Enter)"
          disabled={routing}
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
          onClick={() => handleRoute()}
          disabled={routing || !input.trim()}
          style={{
            background: routing ? "#374151" : "#7c3aed",
            border: "none",
            borderRadius: "8px",
            color: "#fff",
            padding: "0 16px",
            cursor: routing || !input.trim() ? "not-allowed" : "pointer",
            fontSize: "18px",
            opacity: !input.trim() ? 0.4 : 1,
          }}
        >
          {routing ? "⟳" : "⇢"}
        </button>
      </div>
    </div>
  );
}
