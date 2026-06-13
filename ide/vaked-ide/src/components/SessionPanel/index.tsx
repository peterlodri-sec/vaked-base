import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { HumanSession } from "./HumanSession";
import { A2ASession } from "./A2ASession";
import { GatewaySession } from "./GatewaySession";
import { useSessionStore } from "@/store";
import type { SessionKind } from "@/types/session";

const TABS: { kind: SessionKind; label: string; icon: string; color: string }[] = [
  { kind: "human",   label: "Human",   icon: "👤", color: "#6366f1" },
  { kind: "a2a",     label: "A2A",     icon: "🤝", color: "#22c55e" },
  { kind: "gateway", label: "Gateway", icon: "⇢",  color: "#7c3aed" },
];

export function SessionPanel() {
  const [activeTab, setActiveTab] = useState<SessionKind>("human");
  const {
    sessions,
    createSession: createInStore,
    activeSessionId,
    setActiveSession,
  } = useSessionStore();

  const ensureSession = async (kind: SessionKind): Promise<string> => {
    // Find existing session of this kind
    for (const [id, s] of sessions) {
      if (s.kind === kind) {
        setActiveSession(id);
        return id;
      }
    }
    // Create new via Tauri then sync
    try {
      const id = await invoke<string>("create_session", { kind, label: `${kind} session` });
      createInStore(kind, `${kind} session`);
      return id;
    } catch {
      const id = createInStore(kind, `${kind} session`);
      return id;
    }
  };

  const [sessionIds, setSessionIds] = useState<Partial<Record<SessionKind, string>>>({});

  const handleTabClick = async (kind: SessionKind) => {
    setActiveTab(kind);
    if (!sessionIds[kind]) {
      const id = await ensureSession(kind);
      setSessionIds((prev) => ({ ...prev, [kind]: id }));
    }
  };

  // Initialize default human session
  useState(() => {
    handleTabClick("human");
  });

  const currentSessionId = sessionIds[activeTab];

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      height: "100%",
      background: "#0d1117",
      borderLeft: "1px solid #1f2937",
    }}>
      {/* Tab bar */}
      <div style={{
        display: "flex",
        borderBottom: "1px solid #1f2937",
        background: "#111827",
      }}>
        {TABS.map((tab) => {
          const isActive = activeTab === tab.kind;
          return (
            <button
              key={tab.kind}
              onClick={() => handleTabClick(tab.kind)}
              style={{
                flex: 1,
                background: "transparent",
                border: "none",
                borderBottom: isActive ? `2px solid ${tab.color}` : "2px solid transparent",
                color: isActive ? tab.color : "#6b7280",
                padding: "8px 4px",
                cursor: "pointer",
                fontSize: "11px",
                fontFamily: "monospace",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                gap: "4px",
                transition: "color 0.1s",
              }}
            >
              <span>{tab.icon}</span>
              <span>{tab.label}</span>
            </button>
          );
        })}
      </div>

      {/* Session content */}
      <div style={{ flex: 1, overflow: "hidden" }}>
        {currentSessionId ? (
          activeTab === "human" ? (
            <HumanSession sessionId={currentSessionId} />
          ) : activeTab === "a2a" ? (
            <A2ASession sessionId={currentSessionId} />
          ) : (
            <GatewaySession sessionId={currentSessionId} />
          )
        ) : (
          <div style={{ padding: "16px", color: "#6b7280", fontSize: "13px" }}>
            Initializing session…
          </div>
        )}
      </div>
    </div>
  );
}
