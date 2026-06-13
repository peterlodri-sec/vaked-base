import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { AgentBadge } from "./AgentBadge";
import { MessageBubble } from "./MessageBubble";
import { useSessionStore } from "@/store";
import { useYjs } from "@/hooks/useYjs";

interface A2ASessionProps {
  sessionId: string;
}

export function A2ASession({ sessionId }: A2ASessionProps) {
  const yjsPort = useSessionStore((s) => s.yjsPort);
  const session = useSessionStore((s) => s.sessions.get(sessionId));
  const { doc, provider, yText } = useYjs(!!yjsPort);

  const [agentStatus, setAgentStatus] = useState<Record<string, "idle" | "editing">>(
    { "Agent-A": "idle", "Agent-B": "idle" }
  );
  const [launching, setLaunching] = useState(false);

  const launchAgents = async () => {
    if (!yjsPort || launching) return;
    setLaunching(true);

    // Launch two parallel agent sessions - each gets a separate session
    const [idA, idB] = await Promise.all([
      invoke<string>("create_session", { kind: "a2a", label: "Agent-A" }),
      invoke<string>("create_session", { kind: "a2a", label: "Agent-B" }),
    ]);

    setAgentStatus({ "Agent-A": "editing", "Agent-B": "editing" });

    await Promise.all([
      invoke("send_session_message", {
        sessionId: idA,
        content: "You are Agent-A in a collaborative Vaked editing session. Review the current graph and propose one structural improvement. Focus on the mesh/workflow topology.",
        graphContext: null,
      }),
      invoke("send_session_message", {
        sessionId: idB,
        content: "You are Agent-B in a collaborative Vaked editing session. Review the current graph and propose one capability improvement. Focus on the capability grants and POLA attenuation.",
        graphContext: null,
      }),
    ]);

    setAgentStatus({ "Agent-A": "idle", "Agent-B": "idle" });
    setLaunching(false);
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", padding: "12px" }}>
      {/* Agent status */}
      <div style={{
        display: "flex",
        gap: "8px",
        marginBottom: "12px",
        padding: "10px",
        background: "#111827",
        borderRadius: "8px",
        border: "1px solid #1f2937",
      }}>
        {Object.entries(agentStatus).map(([agent, status]) => (
          <div key={agent} style={{ display: "flex", alignItems: "center", gap: "6px" }}>
            <div style={{
              width: "8px",
              height: "8px",
              borderRadius: "50%",
              background: status === "editing" ? "#22c55e" : "#374151",
              boxShadow: status === "editing" ? "0 0 6px #22c55e" : "none",
              transition: "all 0.3s",
            }} />
            <span style={{ color: "#9ca3af", fontSize: "12px", fontFamily: "monospace" }}>
              {agent}
            </span>
            <span style={{ color: "#4b5563", fontSize: "11px" }}>
              {status === "editing" ? "editing…" : "idle"}
            </span>
          </div>
        ))}
      </div>

      {/* Yjs status */}
      <div style={{
        padding: "6px 10px",
        background: yjsPort ? "#052e16" : "#1c1917",
        border: `1px solid ${yjsPort ? "#16a34a" : "#44403c"}`,
        borderRadius: "6px",
        marginBottom: "12px",
        fontSize: "11px",
        fontFamily: "monospace",
        color: yjsPort ? "#86efac" : "#78716c",
      }}>
        {yjsPort
          ? `✓ Yjs relay · ws://localhost:${yjsPort} · CRDT syncing`
          : "Yjs relay starting…"}
      </div>

      {/* Session messages */}
      <div style={{ flex: 1, overflow: "auto", marginBottom: "12px" }}>
        {session?.messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
      </div>

      {/* Launch button */}
      <button
        onClick={launchAgents}
        disabled={!yjsPort || launching}
        style={{
          background: launching ? "#374151" : "#1e3a5f",
          border: "1px solid #1e40af",
          borderRadius: "8px",
          color: "#93c5fd",
          padding: "10px",
          cursor: !yjsPort || launching ? "not-allowed" : "pointer",
          fontSize: "13px",
          fontFamily: "monospace",
          opacity: !yjsPort ? 0.4 : 1,
        }}
      >
        {launching ? "⟳ Agents working…" : "⚡ Launch A2A agents (2× concurrent)"}
      </button>
    </div>
  );
}
