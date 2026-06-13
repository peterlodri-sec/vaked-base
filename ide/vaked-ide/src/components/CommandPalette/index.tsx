import { useCallback, useEffect, useRef, useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { readTextFile } from "@tauri-apps/plugin-fs";
import { useUIStore, useGraphStore, useEditorStore } from "@/store";
import { useVakedc } from "@/hooks/useVakedc";

// ---------- command registry --------------------------------------------------

type CommandId = string;

interface Command {
  id: CommandId;
  label: string;
  description?: string;
  icon?: string;
  keywords?: string;
  action: () => void;
}

function fuzzyScore(query: string, target: string): number {
  if (!query) return 1;
  const q = query.toLowerCase();
  const t = target.toLowerCase();
  if (t.includes(q)) return 2; // substring — higher priority
  let qi = 0;
  for (let ti = 0; ti < t.length && qi < q.length; ti++) {
    if (t[ti] === q[qi]) qi++;
  }
  return qi === q.length ? 1 : 0;
}

function highlight(text: string, query: string): JSX.Element {
  if (!query) return <>{text}</>;
  const q = query.toLowerCase();
  const t = text.toLowerCase();
  const idx = t.indexOf(q);
  if (idx === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, idx)}
      <mark style={{ background: "#6366f1", color: "#fff", borderRadius: "2px", padding: "0 1px" }}>
        {text.slice(idx, idx + q.length)}
      </mark>
      {text.slice(idx + q.length)}
    </>
  );
}

// ---------- component ---------------------------------------------------------

export function CommandPalette() {
  const { closeCommandPalette, toggleSidebar, toggleSessionPanel, toggleTerminal,
          setSidebarTab, setSessionTab } = useUIStore();
  const { nodes, filePath, setFilePath } = useGraphStore((s) => ({
    nodes: s.graph?.nodes ?? [],
    filePath: s.filePath,
    setFilePath: s.setFilePath,
  }));
  const setSource = useEditorStore((s) => s.setSource);
  const selectNode = useGraphStore((s) => s.selectNode);
  const { parseFile, lowerFile } = useVakedc();

  const diagnostics = useEditorStore((s) => s.diagnostics);
  const errorCount = diagnostics.filter((d) => d.severity === 1).length;

  const [query, setQuery] = useState("");
  const [activeIdx, setActiveIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Close on Escape / click-outside
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeCommandPalette();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [closeCommandPalette]);

  // Build command list (static + dynamic graph nodes)
  const buildCommands = useCallback((): Command[] => {
    const cmds: Command[] = [
      {
        id: "open-file",
        label: "Open .vaked file…",
        icon: "📂",
        keywords: "open file load",
        action: async () => {
          closeCommandPalette();
          const selected = await open({ filters: [{ name: "Vaked", extensions: ["vaked"] }], multiple: false });
          if (typeof selected === "string") {
            const text = await readTextFile(selected);
            setSource(text);
            setFilePath(selected);
            await parseFile(selected);
          }
        },
      },
      {
        id: "lower",
        label: "Lower to artifacts",
        icon: "⬇",
        description: errorCount > 0 ? "fix errors first" : filePath ? filePath.split("/").slice(-1)[0] : "no file open",
        keywords: "lower compile output nix flake",
        action: async () => {
          if (!filePath || errorCount > 0) return;
          closeCommandPalette();
          await lowerFile(filePath, filePath.replace(/\.vaked$/, "/.vaked/lower"));
        },
      },
      {
        id: "toggle-sidebar",
        label: "Toggle sidebar",
        icon: "◧",
        keywords: "sidebar panel schema caps capability provenance surface",
        action: () => { closeCommandPalette(); toggleSidebar(); },
      },
      {
        id: "toggle-session",
        label: "Toggle AI session panel",
        icon: "💬",
        keywords: "ai session human a2a gateway chat",
        action: () => { closeCommandPalette(); toggleSessionPanel(); },
      },
      {
        id: "toggle-terminal",
        label: "Toggle terminal (Ghostty)",
        icon: "▦",
        keywords: "terminal ghostty shell",
        action: () => { closeCommandPalette(); toggleTerminal(); },
      },
      {
        id: "tab-schema",
        label: "Sidebar → Schema Inspector",
        icon: "📋",
        keywords: "schema kind fields inspect",
        action: () => { closeCommandPalette(); setSidebarTab("schema"); },
      },
      {
        id: "tab-caps",
        label: "Sidebar → Capability Hasse",
        icon: "🔑",
        keywords: "capability caps domain fs network ebpf process mem mcp hasse",
        action: () => { closeCommandPalette(); setSidebarTab("capability"); },
      },
      {
        id: "tab-provenance",
        label: "Sidebar → Provenance Panel",
        icon: "🔗",
        keywords: "provenance span source location link",
        action: () => { closeCommandPalette(); setSidebarTab("provenance"); },
      },
      {
        id: "tab-surface",
        label: "Sidebar → Surface Launcher",
        icon: "🖥",
        keywords: "surface launcher view raylib register open",
        action: () => { closeCommandPalette(); setSidebarTab("surface"); },
      },
      {
        id: "session-human",
        label: "Session → Human chat",
        icon: "👤",
        keywords: "session human chat ask claude ai",
        action: () => { closeCommandPalette(); toggleSessionPanel(); setSessionTab("human"); },
      },
      {
        id: "session-a2a",
        label: "Session → A2A agents",
        icon: "🤝",
        keywords: "session a2a agent crdt yjs multi collaborative",
        action: () => { closeCommandPalette(); toggleSessionPanel(); setSessionTab("a2a"); },
      },
      {
        id: "session-gateway",
        label: "Session → Gateway router",
        icon: "⇢",
        keywords: "session gateway router opus routing sub-agent",
        action: () => { closeCommandPalette(); toggleSessionPanel(); setSessionTab("gateway"); },
      },
    ];

    // Dynamic: one command per graph node
    for (const node of nodes) {
      cmds.push({
        id: `node:${node.id}`,
        label: node.name,
        icon: "◈",
        description: node.kind,
        keywords: `${node.kind} ${node.name} ${node.id} graph node jump select`,
        action: () => { closeCommandPalette(); selectNode(node.id); },
      });
    }

    return cmds;
  }, [
    closeCommandPalette, filePath, errorCount, nodes,
    parseFile, lowerFile, selectNode, setFilePath, setSource,
    setSidebarTab, setSessionTab, toggleSidebar, toggleSessionPanel, toggleTerminal,
  ]);

  const allCommands = buildCommands();

  const filtered = query
    ? allCommands
        .map((c) => ({
          c,
          score: fuzzyScore(query, c.label + " " + (c.keywords ?? "") + " " + (c.description ?? "")),
        }))
        .filter(({ score }) => score > 0)
        .sort((a, b) => b.score - a.score)
        .map(({ c }) => c)
    : allCommands;

  const execute = (cmd: Command) => cmd.action();

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActiveIdx((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActiveIdx((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (filtered[activeIdx]) execute(filtered[activeIdx]);
    }
  };

  // Scroll active item into view
  useEffect(() => {
    setActiveIdx(0);
  }, [query]);

  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const active = list.querySelector<HTMLElement>(`[data-idx="${activeIdx}"]`);
    active?.scrollIntoView({ block: "nearest" });
  }, [activeIdx]);

  return (
    // Backdrop
    <div
      onClick={closeCommandPalette}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,0.6)",
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "center",
        paddingTop: "120px",
        zIndex: 9999,
      }}
    >
      {/* Panel */}
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "min(580px, 90vw)",
          background: "#111827",
          border: "1px solid #374151",
          borderRadius: "10px",
          overflow: "hidden",
          boxShadow: "0 25px 60px rgba(0,0,0,0.7)",
          display: "flex",
          flexDirection: "column",
        }}
      >
        {/* Search input */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px", padding: "12px 14px", borderBottom: "1px solid #1f2937" }}>
          <span style={{ color: "#4b5563", fontSize: "14px" }}>⌘</span>
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Type a command or search nodes…"
            style={{
              flex: 1,
              background: "transparent",
              border: "none",
              outline: "none",
              color: "#e2e8f0",
              fontSize: "14px",
              fontFamily: "monospace",
            }}
          />
          <kbd style={{
            background: "#1f2937",
            border: "1px solid #374151",
            borderRadius: "4px",
            color: "#6b7280",
            fontSize: "10px",
            padding: "2px 6px",
          }}>
            esc
          </kbd>
        </div>

        {/* Results */}
        <div ref={listRef} style={{ maxHeight: "360px", overflowY: "auto" }}>
          {filtered.length === 0 ? (
            <div style={{ padding: "24px", textAlign: "center", color: "#4b5563", fontSize: "13px", fontFamily: "monospace" }}>
              No commands match "{query}"
            </div>
          ) : (
            filtered.map((cmd, idx) => {
              const isActive = idx === activeIdx;
              return (
                <div
                  key={cmd.id}
                  data-idx={idx}
                  onClick={() => execute(cmd)}
                  onMouseEnter={() => setActiveIdx(idx)}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "10px",
                    padding: "9px 14px",
                    cursor: "pointer",
                    background: isActive ? "#1f2937" : "transparent",
                    borderLeft: isActive ? "2px solid #6366f1" : "2px solid transparent",
                    transition: "background 0.05s",
                  }}
                >
                  {cmd.icon && (
                    <span style={{ fontSize: "14px", flexShrink: 0, width: "20px", textAlign: "center" }}>
                      {cmd.icon}
                    </span>
                  )}
                  <span style={{ flex: 1, fontSize: "13px", fontFamily: "monospace", color: "#e2e8f0" }}>
                    {highlight(cmd.label, query)}
                  </span>
                  {cmd.description && (
                    <span style={{ fontSize: "11px", color: "#4b5563", fontFamily: "monospace", flexShrink: 0 }}>
                      {cmd.description}
                    </span>
                  )}
                </div>
              );
            })
          )}
        </div>

        {/* Footer */}
        <div style={{ padding: "6px 14px", borderTop: "1px solid #1f2937", display: "flex", gap: "12px" }}>
          {[["↑↓", "navigate"], ["↵", "run"], ["esc", "close"]].map(([k, v]) => (
            <span key={k} style={{ fontSize: "10px", color: "#4b5563", fontFamily: "monospace" }}>
              <kbd style={{ background: "#1f2937", borderRadius: "3px", padding: "1px 4px", marginRight: "3px", border: "1px solid #374151" }}>{k}</kbd>
              {v}
            </span>
          ))}
          <span style={{ marginLeft: "auto", fontSize: "10px", color: "#374151" }}>
            {filtered.length} result{filtered.length !== 1 ? "s" : ""}
          </span>
        </div>
      </div>
    </div>
  );
}
