import { useEffect, useRef, useCallback } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import type { LspMessage, LspDiagnostic } from "@/types/lsp";
import { nextLspId } from "@/types/lsp";
import { useEditorStore } from "@/store";

export function useLsp() {
  const setDiagnostics = useEditorStore((s) => s.setDiagnostics);
  const setLspReady = useEditorStore((s) => s.setLspReady);
  const initializedRef = useRef(false);

  useEffect(() => {
    let unlisten: (() => void) | undefined;

    const setup = async () => {
      // Start LSP process
      try {
        await invoke("start_lsp");
      } catch (e) {
        console.error("Failed to start LSP:", e);
        return;
      }

      // Listen for LSP messages
      unlisten = await listen<string>("lsp-message", (event) => {
        try {
          const msg: LspMessage = JSON.parse(event.payload);
          handleLspMessage(msg);
        } catch {}
      });

      // Send initialize
      if (!initializedRef.current) {
        initializedRef.current = true;
        await sendLspRequest({
          jsonrpc: "2.0",
          id: nextLspId(),
          method: "initialize",
          params: {
            processId: null,
            clientInfo: { name: "vaked-ide", version: "0.1.0" },
            capabilities: {
              textDocument: {
                publishDiagnostics: { relatedInformation: true },
                completion: { completionItem: { snippetSupport: false } },
                hover: { contentFormat: ["markdown"] },
              },
            },
            rootUri: null,
          },
        });
      }
    };

    const handleLspMessage = (msg: LspMessage) => {
      if (msg.method === "textDocument/publishDiagnostics") {
        const params = msg.params as { uri: string; diagnostics: LspDiagnostic[] };
        setDiagnostics(params.diagnostics);
      }
      if (msg.id && !msg.method) {
        // Response to initialize
        setLspReady(true);
        invoke("lsp_send", {
          message: JSON.stringify({ jsonrpc: "2.0", method: "initialized", params: {} }),
        });
      }
    };

    setup();
    return () => unlisten?.();
  }, [setDiagnostics, setLspReady]);

  const sendLspRequest = useCallback(async (msg: object) => {
    try {
      await invoke("lsp_send", { message: JSON.stringify(msg) });
    } catch (e) {
      console.error("lsp_send failed:", e);
    }
  }, []);

  const notifyOpen = useCallback((uri: string, text: string) => {
    sendLspRequest({
      jsonrpc: "2.0",
      method: "textDocument/didOpen",
      params: {
        textDocument: { uri, languageId: "vaked", version: 1, text },
      },
    });
  }, [sendLspRequest]);

  const notifyChange = useCallback((uri: string, text: string, version: number) => {
    sendLspRequest({
      jsonrpc: "2.0",
      method: "textDocument/didChange",
      params: {
        textDocument: { uri, version },
        contentChanges: [{ text }],
      },
    });
  }, [sendLspRequest]);

  const notifyClose = useCallback((uri: string) => {
    sendLspRequest({
      jsonrpc: "2.0",
      method: "textDocument/didClose",
      params: { textDocument: { uri } },
    });
  }, [sendLspRequest]);

  return { notifyOpen, notifyChange, notifyClose, sendLspRequest };
}
