"use strict";

import { create } from "zustand";
import type { Session, SessionKind, SessionMessage, AgentRole, GatewayRoute } from "@/types/session";

// Minimal uuid without the import (using crypto)
function genId(): string {
  return crypto.randomUUID();
}

interface SessionStore {
  sessions: Map<string, Session>;
  activeSessionId: string | null;
  yjsPort: number | null;

  createSession: (kind: SessionKind, label: string) => string;
  setActiveSession: (id: string | null) => void;
  addMessage: (sessionId: string, msg: SessionMessage) => void;
  appendChunk: (sessionId: string, role: AgentRole, text: string) => void;
  finalizeStream: (sessionId: string, role: AgentRole) => void;
  setLastRoute: (sessionId: string, route: GatewayRoute) => void;
  setYjsPort: (port: number) => void;
}

export const useSessionStore = create<SessionStore>((set, get) => ({
  sessions: new Map(),
  activeSessionId: null,
  yjsPort: null,

  createSession: (kind, label) => {
    const id = genId();
    const session: Session = {
      id,
      kind,
      label,
      messages: [],
      activeAgents: kind === "human" ? ["user", "openrouter"] :
                    kind === "a2a"   ? ["a2a-peer"] :
                                       ["user", "openrouter"],
      createdAt: Date.now(),
    };
    const sessions = new Map(get().sessions);
    sessions.set(id, session);
    set({ sessions, activeSessionId: id });
    return id;
  },

  setActiveSession: (id) => set({ activeSessionId: id }),

  addMessage: (sessionId, msg) => {
    const sessions = new Map(get().sessions);
    const session = sessions.get(sessionId);
    if (!session) return;
    sessions.set(sessionId, {
      ...session,
      messages: [...session.messages, msg],
    });
    set({ sessions });
  },

  appendChunk: (sessionId, role, text) => {
    const sessions = new Map(get().sessions);
    const session = sessions.get(sessionId);
    if (!session) return;
    const messages = [...session.messages];
    const last = messages[messages.length - 1];
    if (last?.role === role && last.isStreaming) {
      messages[messages.length - 1] = {
        ...last,
        content: last.content + text,
      };
    } else {
      messages.push({
        id: genId(),
        role,
        content: text,
        timestamp: Date.now(),
        isStreaming: true,
      });
    }
    sessions.set(sessionId, { ...session, messages });
    set({ sessions });
  },

  finalizeStream: (sessionId, role) => {
    const sessions = new Map(get().sessions);
    const session = sessions.get(sessionId);
    if (!session) return;
    const messages = session.messages.map((m) =>
      m.role === role && m.isStreaming ? { ...m, isStreaming: false } : m
    );
    sessions.set(sessionId, { ...session, messages });
    set({ sessions });
  },

  setLastRoute: (sessionId, route) => {
    const sessions = new Map(get().sessions);
    const session = sessions.get(sessionId);
    if (!session) return;
    sessions.set(sessionId, { ...session, lastRoute: route });
    set({ sessions });
  },

  setYjsPort: (port) => set({ yjsPort: port }),
}));
