import { useState } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import { readTextFile } from "@tauri-apps/plugin-fs";
import { useGraphStore, useEditorStore, useUIStore } from "@/store";
import { useVakedc } from "@/hooks/useVakedc";

export function TopBar() {
  const [opening, setOpening] = useState(false);
  const [lowering, setLowering] = useState(false);
  const filePath = useGraphStore((s) => s.filePath);
  const diagnostics = useEditorStore((s) => s.diagnostics);
  const lspReady = useEditorStore((s) => s.lspReady);
  const setSource = useEditorStore((s) => s.setSource);
  const setFilePath = useGraphStore((s) => s.setFilePath);
  const { parseFile, lowerFile } = useVakedc();
  const { toggleSidebar, toggleSessionPanel, toggleTerminal, openCommandPalette } = useUIStore();

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
    <div style={{
      display: "flex",
      alignItems: "center",
      gap: "8px",
      padding: "6px 12px",
      background: "#0d1117",
      borderBottom: "1px solid #1f2937",
      height: "42px",
      flexShrink: 0,
    }}>
      {/* Logo */}
      <span style={{
        fontFamily: "monospace",
        fontWeight: 700,
        fontSize: "14px",
        color: "#7c3aed",
        marginRight: "8px",
        letterSpacing: "-0.02em",
      }}>
        ⚡ vaked-ide
      </span>

      {/* File actions */}
      <button onClick={handleOpen} disabled={opening} style={btnStyle("#1f2937", "#9ca3af")}>
        {opening ? "Opening…" : "Open .vaked"}
      </button>

      {filePath && (
        <>
          <span style={{
            color: "#4b5563",
            fontSize: "11px",
            fontFamily: "monospace",
            maxWidth: "300px",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}>
            {filePath.split("/").slice(-2).join("/")}
          </span>

          <button
            onClick={handleLower}
            disabled={lowering || errorCount > 0}
            title={errorCount > 0 ? "Fix errors before lowering" : "Lower to artifacts"}
            style={btnStyle(errorCount > 0 ? "#1f2937" : "#052e16", errorCount > 0 ? "#4b5563" : "#16a34a")}
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
            padding: "1px 7px",
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
            padding: "1px 7px",
            fontFamily: "monospace",
          }}>
            ⚠ {warnCount}
          </span>
        )}
        {errorCount === 0 && warnCount === 0 && filePath && (
          <span style={{ color: "#16a34a", fontSize: "11px" }}>✓ clean</span>
        )}
      </div>

      {/* Panel toggles */}
      <button onClick={toggleSidebar} style={btnStyle("#1f2937", "#6b7280")} title="Toggle sidebar">
        ◧
      </button>
      <button onClick={toggleSessionPanel} style={btnStyle("#1f2937", "#6b7280")} title="Toggle AI session">
        💬
      </button>
      <button onClick={toggleTerminal} style={btnStyle("#1f2937", "#6b7280")} title="Toggle terminal (Ghostty)">
        ▦
      </button>

      {/* Command palette trigger */}
      <button
        onClick={openCommandPalette}
        title="Command palette (⌘K)"
        style={{
          ...btnStyle("#1f2937", "#9ca3af"),
          display: "flex",
          alignItems: "center",
          gap: "5px",
        }}
      >
        <span>⌘K</span>
        <kbd style={{
          background: "#0d1117",
          border: "1px solid #374151",
          borderRadius: "3px",
          color: "#4b5563",
          fontSize: "9px",
          padding: "1px 4px",
          fontFamily: "monospace",
        }}>
          ctrl+k
        </kbd>
      </button>
    </div>
  );
}

function btnStyle(bg: string, color: string) {
  return {
    background: bg,
    border: "1px solid #374151",
    borderRadius: "5px",
    color,
    padding: "3px 10px",
    cursor: "pointer",
    fontSize: "12px",
    fontFamily: "monospace",
    transition: "opacity 0.1s",
  };
}
