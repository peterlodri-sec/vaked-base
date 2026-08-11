import { useEffect } from "react";

interface CheatsheetModalProps {
  onClose: () => void;
}

export function CheatsheetModal({ onClose }: CheatsheetModalProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  const shortcuts = [
    { key: "⌘ K / Ctrl+K", desc: "Open Command Palette & Slash Commands" },
    { key: "⌘ P / Ctrl+P", desc: "Quick Open .vaked files" },
    { key: "⌘ B / Ctrl+B", desc: "Toggle Left Sidebar" },
    { key: "⌘ J / Ctrl+J", desc: "Toggle AI Session & Cogito Panel" },
    { key: "⌘ \\ / Ctrl+\\", desc: "Toggle Integrated Terminal" },
    { key: "⌘ ? / Ctrl+?", desc: "Toggle Keyboard Shortcut Cheatsheet" },
    { key: "/telemetry", desc: "View BitNet b1.58 SIMD & GPU stream" },
    { key: "/audit", desc: "Run AST & neural weight energy audit" },
    { key: "/bench", desc: "Run BitNet b1.58 matrix contraction benchmark" },
  ];

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(3, 7, 18, 0.8)",
        backdropFilter: "blur(8px)",
        zIndex: 9999,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "20px",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: "480px",
          maxWidth: "90vw",
          background: "#0d1117",
          border: "1px solid #374151",
          borderRadius: "12px",
          boxShadow: "0 25px 50px -12px rgba(124, 58, 237, 0.25)",
          padding: "24px",
          color: "#e2e8f0",
          fontFamily: "monospace",
        }}
      >
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "20px" }}>
          <h3 style={{ margin: 0, fontSize: "16px", color: "#a78bfa", display: "flex", alignItems: "center", gap: "8px" }}>
            <span>⚡</span> Vaked IDE Keyboard Shortcuts
          </h3>
          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: "none",
              color: "#6b7280",
              cursor: "pointer",
              fontSize: "16px",
            }}
          >
            ✕
          </button>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: "10px" }}>
          {shortcuts.map((s, idx) => (
            <div
              key={idx}
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                padding: "8px 12px",
                background: "#161b22",
                borderRadius: "6px",
                border: "1px solid #1f2937",
              }}
            >
              <span style={{ fontSize: "12px", color: "#94a3b8" }}>{s.desc}</span>
              <kbd
                style={{
                  background: "#1f2937",
                  border: "1px solid #4b5563",
                  borderRadius: "4px",
                  padding: "2px 8px",
                  fontSize: "11px",
                  color: "#38bdf8",
                  fontWeight: 600,
                }}
              >
                {s.key}
              </kbd>
            </div>
          ))}
        </div>

        <div style={{ marginTop: "20px", textAlign: "center", fontSize: "11px", color: "#475569" }}>
          Press <kbd style={{ background: "#1e293b", padding: "1px 4px", borderRadius: "3px" }}>Esc</kbd> to close
        </div>
      </div>
    </div>
  );
}
