import { useState, useEffect } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { readTextFile } from "@tauri-apps/plugin-fs";
import { useGraphStore, useEditorStore, useUIStore } from "@/store";
import { useVakedc } from "@/hooks/useVakedc";
import { CheatsheetModal } from "@/components/CheatsheetModal";

export function TopBar() {
  const [opening, setOpening] = useState(false);
  const [lowering, setLowering] = useState(false);
  const [showCheatsheet, setShowCheatsheet] = useState(false);

  const filePath = useGraphStore((s) => s.filePath);
  const diagnostics = useEditorStore((s) => s.diagnostics);
  const setSource = useEditorStore((s) => s.setSource);
  const setFilePath = useGraphStore((s) => s.setFilePath);
  const { parseFile, lowerFile } = useVakedc();
  const { toggleSidebar, toggleSessionPanel, toggleTerminal, openCommandPalette } = useUIStore();

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "?") {
        e.preventDefault();
        setShowCheatsheet((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  const handleOpen = async () => {
    if (opening) return;
    setOpening(true);
    try {
      const selected = await open({
        filters: [{ name: "Vaked", extensions: ["vaked"] }],
        multiple: false,
      });
      if (typeof selected === "string") {
        const text = await readTextFile(selected);
        setSource(text);
        setFilePath(selected);
        await parseFile(selected);
      }
    } catch (e) {
      console.error("open failed:", e);
    } finally {
      setOpening(false);
    }
  };

  const handleLower = async () => {
    if (!filePath || lowering) return;
    setLowering(true);
    try {
      const outDir = filePath.replace(/\.vaked$/, "/.vaked/lower");
      await lowerFile(filePath, outDir);
    } catch (e) {
      console.error("lower failed:", e);
    } finally {
      setLowering(false);
    }
  };

  const errorCount = diagnostics.filter((d) => d.severity === 1).length;
  const warnCount = diagnostics.filter((d) => d.severity === 2).length;

  return (
    <>
      <div
        data-tauri-drag-region
        style={{
          display: "flex",
          alignItems: "center",
          gap: "10px",
          padding: "6px 14px",
          background: "rgba(13, 17, 23, 0.95)",
          backdropFilter: "blur(10px)",
          borderBottom: "1px solid #1f2937",
          height: "44px",
          flexShrink: 0,
        }}
      >
        {/* Logo & macOS Traffic Light Spacer */}
        <div style={{ display: "flex", alignItems: "center", gap: "8px", marginRight: "6px" }}>
          <span style={{
            fontFamily: "monospace",
            fontWeight: 800,
            fontSize: "14px",
            background: "linear-gradient(135deg, #a78bfa 0%, #38bdf8 100%)",
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            letterSpacing: "-0.02em",
            display: "flex",
            alignItems: "center",
            gap: "6px",
          }}>
            <span>👁️</span> vaked-ide
          </span>
        </div>

        {/* File actions */}
        <button onClick={handleOpen} disabled={opening} style={btnStyle("#161b22", "#38bdf8")}>
          {opening ? "Opening…" : "Open .vaked"}
        </button>

        {filePath && (
          <>
            <span style={{
              color: "#64748b",
              fontSize: "11px",
              fontFamily: "monospace",
              maxWidth: "280px",
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              background: "#161b22",
              padding: "2px 8px",
              borderRadius: "4px",
              border: "1px solid #1e293b",
            }}>
              {filePath.split("/").slice(-2).join("/")}
            </span>

            <button
              onClick={handleLower}
              disabled={lowering || errorCount > 0}
              title={errorCount > 0 ? "Fix errors before lowering" : "Lower to artifacts"}
              style={btnStyle(errorCount > 0 ? "#161b22" : "#052e16", errorCount > 0 ? "#475569" : "#4ade80")}
            >
              {lowering ? "Lowering…" : "⬇ Lower"}
            </button>
          </>
        )}

        {/* Diagnostics summary */}
        <div style={{ marginLeft: "auto", display: "flex", gap: "6px", alignItems: "center" }}>
          {errorCount > 0 && (
            <span style={{
              background: "#450a0a",
              border: "1px solid #ef4444",
              borderRadius: "4px",
              color: "#fca5a5",
              fontSize: "11px",
              padding: "2px 8px",
              fontFamily: "monospace",
            }}>
              ✕ {errorCount} error{errorCount !== 1 ? "s" : ""}
            </span>
          )}
          {warnCount > 0 && (
            <span style={{
              background: "#422006",
              border: "1px solid #f97316",
              borderRadius: "4px",
              color: "#fed7aa",
              fontSize: "11px",
              padding: "2px 8px",
              fontFamily: "monospace",
            }}>
              ⚠ {warnCount}
            </span>
          )}
          {errorCount === 0 && warnCount === 0 && filePath && (
            <span style={{ color: "#4ade80", fontSize: "11px", fontFamily: "monospace" }}>✓ clean</span>
          )}
        </div>

        {/* Panel toggles */}
        <button onClick={toggleSidebar} style={btnStyle("#161b22", "#94a3b8")} title="Toggle sidebar (⌘B)">
          ◧
        </button>
        <button onClick={toggleSessionPanel} style={btnStyle("#161b22", "#94a3b8")} title="Toggle AI session (⌘J)">
          💬
        </button>
        <button onClick={toggleTerminal} style={btnStyle("#161b22", "#94a3b8")} title="Toggle terminal (⌘\)">
          ▦
        </button>

        {/* Cheatsheet trigger */}
        <button
          onClick={() => setShowCheatsheet(true)}
          title="Keyboard shortcuts (⌘?)"
          style={btnStyle("#161b22", "#a78bfa")}
        >
          ?
        </button>

        {/* Command palette trigger */}
        <button
          onClick={openCommandPalette}
          title="Command palette (⌘K)"
          style={{
            ...btnStyle("#1e1b4b", "#c084fc"),
            display: "flex",
            alignItems: "center",
            gap: "5px",
            border: "1px solid #6b21a8",
          }}
        >
          <span>⌘K</span>
        </button>
      </div>

      {showCheatsheet && <CheatsheetModal onClose={() => setShowCheatsheet(false)} />}
    </>
  );
}

function btnStyle(bg: string, color: string) {
  return {
    background: bg,
    border: "1px solid #1e293b",
    borderRadius: "6px",
    color,
    padding: "4px 10px",
    cursor: "pointer",
    fontSize: "12px",
    fontFamily: "monospace",
    fontWeight: 600,
    transition: "all 0.15s ease",
  };
}

