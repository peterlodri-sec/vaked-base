import { useEffect, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import type { SessionKind, AgentRole, GatewayRoute } from "@/types/session";
import { useSessionStore } from "@/store";
import { useGraphStore } from "@/store";
// Migrated from @/lib/anthropic → @/lib/openrouter
import { graphContextString } from "@/lib/openrouter";

export function useSession() {
  const {
    createSession: createSessionState,
    addMessage,
    appendChunk,
    finalizeStream,
    setLastRoute,
    setYjsPort,
  } = useSessionStore();
  const graph = useGraphStore((s) => s.graph);

  useEffect(() => {
    let unlistenChunk: (() => void) | undefined;
    let unlistenDone: (() => void) | undefined;
    let unlistenRoute: (() => void) | undefined;
    let unlistenYjsPort: (() => void) | undefined;

    const setup = async () => {
      unlistenChunk = await listen<{ session_id: string; agent_role: string; text: string }>(
        "session-stream-chunk",
        (e) => {
          appendChunk(e.payload.session_id, e.payload.agent_role as AgentRole, e.payload.text);
        }
      );
      unlistenDone = await listen<{ session_id: string; agent_role: string }>(
        "session-stream-done",
        (e) => {
          finalizeStream(e.payload.session_id, e.payload.agent_role as AgentRole);
        }
      );
      unlistenRoute = await listen<{ session_id: string; route: GatewayRoute }>(
        "session-gateway-route",
        (e) => {
          setLastRoute(e.payload.session_id, e.payload.route);
        }
      );
      unlistenYjsPort = await listen<number>("yjs-port", (e) => {
        setYjsPort(e.payload);
      });
    };
    setup();

    return () => {
      unlistenChunk?.();
      unlistenDone?.();
      unlistenRoute?.();
      unlistenYjsPort?.();
    };
  }, [appendChunk, finalizeStream, setLastRoute, setYjsPort]);

  const createSession = useCallback(
    async (kind: SessionKind, label: string): Promise<string> => {
      const sessionId = await invoke<string>("create_session", { kind, label });
      // Sync with Tauri-assigned ID (Tauri generates the UUID)
      createSessionState(kind, label);
      return sessionId;
    },
    [createSessionState]
  );

  const sendMessage = useCallback(
    async (sessionId: string, content: string) => {
      const graphCtx = graphContextString(graph);
      addMessage(sessionId, {
        id: crypto.randomUUID(),
        role: "user",
        content,
        timestamp: Date.now(),
      });
      await invoke("send_session_message", {
        sessionId,
        content,
        graphContext: graphCtx || null,
      });
    },
    [addMessage, graph]
  );

  const gatewayRoute = useCallback(
    async (sessionId: string, query: string) => {
      const graphCtx = graphContextString(graph);
      addMessage(sessionId, {
        id: crypto.randomUUID(),
        role: "user",
        content: query,
        timestamp: Date.now(),
      });
      await invoke("gateway_route", {
        sessionId,
        query,
        graphContext: graphCtx,
      });
    },
    [addMessage, graph]
  );

  return { createSession, sendMessage, gatewayRoute };
}
