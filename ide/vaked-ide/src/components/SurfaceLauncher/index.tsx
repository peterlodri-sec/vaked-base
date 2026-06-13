import { useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useGraphStore } from "@/store";
import { getKindConfig } from "@/graph/kindConfig";

export function SurfaceLauncher() {
  const graph = useGraphStore((s) => s.graph);
  const filePath = useGraphStore((s) => s.filePath);
  const [registering, setRegistering] = useState(false);
  const [opening, setOpening] = useState<string | null>(null);
  const [registered, setRegistered] = useState<Set<string>>(new Set());

  const surfaceNodes = graph.nodes.filter((n) => n.kind === "surface");

  if (surfaceNodes.length === 0) {
    return (
      <div style={{ padding: "12px", color: "#6b7280", fontSize: "12px" }}>
        No <code style={{ color: "#a78bfa" }}>surface</code> declarations in this file.
      </div>
    );
  }

  const cfg = getKindConfig("surface");

  const handleRegister = async (surfaceName: string) => {
    if (!filePath || registering) return;
    setRegistering(true);
    try {
      await invoke("register_surface_launcher", { surfaceName, vakedFile: filePath });
      setRegistered((prev) => new Set([...prev, surfaceName]));
    } catch (e) {
      console.error("register_surface_launcher failed:", e);
    } finally {
      setRegistering(false);
    }
  };

  const handleOpen = async (surfaceName: string) => {
    if (!filePath) return;
    setOpening(surfaceName);
    try {
      await invoke("open_surface_view", { surfaceName, vakedFile: filePath });
    } catch (e) {
      console.error("open_surface_view failed:", e);
    } finally {
      setOpening(null);
    }
  };

  return (
    <div style={{ padding: "10px" }}>
      <div style={{
        color: "#6b7280",
        fontSize: "11px",
        textTransform: "uppercase",
        letterSpacing: "0.05em",
        marginBottom: "8px",
      }}>
        Surface Launcher
      </div>
      {surfaceNodes.map((node) => {
        const isRegistered = registered.has(node.name);
        const views = (node.props.views as string[] | undefined) ?? [];
        const mode = (node.props.mode as string | undefined) ?? "raylib";
        return (
          <div key={node.id} style={{
            background: "#111827",
            border: `1px solid ${cfg.border}55`,
            borderRadius: "8px",
            padding: "10px",
            marginBottom: "8px",
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "8px" }}>
              <span style={{ fontSize: "16px" }}>{cfg.icon}</span>
              <div>
                <div style={{ color: "#86efac", fontFamily: "monospace", fontSize: "13px", fontWeight: 600 }}>
                  {node.name}
                </div>
                <div style={{ color: "#4b5563", fontSize: "11px" }}>
                  mode: {mode} · {views.length} views
                </div>
              </div>
            </div>

            {views.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", gap: "4px", marginBottom: "8px" }}>
                {views.map((v, i) => (
                  <span key={i} style={{
                    background: "#1f2937",
                    borderRadius: "4px",
                    padding: "1px 6px",
                    fontSize: "10px",
                    color: "#9ca3af",
                    fontFamily: "monospace",
                  }}>
                    {v}
                  </span>
                ))}
              </div>
            )}

            <div style={{ display: "flex", gap: "6px" }}>
              {!isRegistered ? (
                <button
                  onClick={() => handleRegister(node.name)}
                  disabled={registering || !filePath}
                  style={{
                    background: "#1e3a5f",
                    border: "1px solid #1e40af",
                    borderRadius: "6px",
                    color: "#93c5fd",
                    padding: "5px 10px",
                    fontSize: "11px",
                    cursor: registering ? "not-allowed" : "pointer",
                    fontFamily: "monospace",
                  }}
                >
                  {registering ? "Registering…" : "Register as launcher"}
                </button>
              ) : (
                <span style={{ color: "#16a34a", fontSize: "11px", padding: "5px 0" }}>
                  ✓ Registered
                </span>
              )}

              <button
                onClick={() => handleOpen(node.name)}
                disabled={opening === node.name || !filePath}
                style={{
                  background: opening === node.name ? "#374151" : cfg.bg,
                  border: `1px solid ${cfg.border}`,
                  borderRadius: "6px",
                  color: "#fff",
                  padding: "5px 10px",
                  fontSize: "11px",
                  cursor: !filePath ? "not-allowed" : "pointer",
                  fontFamily: "monospace",
                }}
              >
                {opening === node.name ? "Opening…" : "▶ Open surface"}
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}
