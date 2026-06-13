import { useEffect, useRef } from "react";
import * as Y from "yjs";
import { WebsocketProvider } from "y-websocket";
import { useSessionStore } from "@/store";

export function useYjs(enabled: boolean) {
  const yjsPort = useSessionStore((s) => s.yjsPort);
  const docRef = useRef<Y.Doc | null>(null);
  const providerRef = useRef<WebsocketProvider | null>(null);

  useEffect(() => {
    if (!enabled || !yjsPort) return;

    // Create a fresh Y.Doc for this A2A session
    const doc = new Y.Doc();
    docRef.current = doc;

    const provider = new WebsocketProvider(
      `ws://localhost:${yjsPort}`,
      "vaked-source",
      doc,
      { connect: true }
    );
    providerRef.current = provider;

    return () => {
      provider.destroy();
      doc.destroy();
      docRef.current = null;
      providerRef.current = null;
    };
  }, [enabled, yjsPort]);

  return {
    doc: docRef.current,
    provider: providerRef.current,
    yText: docRef.current?.getText("vaked-source") ?? null,
  };
}
