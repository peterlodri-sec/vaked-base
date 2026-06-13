import { useEffect, useState } from "react";
import { GraphCanvas } from "@/components/GraphCanvas";
import { useGraphStore } from "@/store";
import { useVakedc } from "@/hooks/useVakedc";

export function SurfaceView() {
  const [surfaceName, setSurfaceName] = useState("");
  const [vakedFile, setVakedFile] = useState("");
  const { parseFile } = useVakedc();
  const graph = useGraphStore((s) => s.graph);

  useEffect(() => {
    // Parse surface name + file from URL search params
    const params = new URLSearchParams(window.location.search);
    const name = params.get("name") ?? "";
    const file = params.get("file") ?? "";
    setSurfaceName(name);
    setVakedFile(file);
    if (file) parseFile(file);
  }, [parseFile]);

  // Find the surface node in the graph
  const surfaceNode = graph.nodes.find(
    (n) => n.kind === "surface" && n.name === surfaceName
  );

  const views = (surfaceNode?.props?.views as string[] | undefined) ?? [];
  const fps = (surfaceNode?.props?.fps as number | undefined) ?? 60;

  return (
    <div style={{
      width: "100vw",
      height: "100vh",
      background: "#080c10",
      display: "flex",
      flexDirection: "column",
      color: "#e2e8f0",
    }}>
      {/* Surface header */}
      <div style={{
        padding: "8px 16px",
        background: "#0d1117",
        borderBottom: "1px solid #1f2937",
        display: "flex",
        alignItems: "center",
        gap: "12px",
      }}>
        <span style={{ color: "#16a34a", fontSize: "14px" }}>🖥</span>
        <span style={{ fontFamily: "monospace", fontSize: "13px", color: "#86efac" }}>
          surface {surfaceName}
        </span>
        <span style={{ color: "#4b5563", fontSize: "12px" }}>
          {fps} fps · {views.length} views
        </span>
        <span style={{ marginLeft: "auto", color: "#16a34a", fontSize: "11px" }}>
          ● live
        </span>
      </div>

      {/* Views */}
      {views.length > 0 ? (
        <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
          {views.map((view, i) => (
            <div key={i} style={{
              flex: 1,
              borderRight: i < views.length - 1 ? "1px solid #1f2937" : "none",
              overflow: "hidden",
              position: "relative",
            }}>
              <div style={{
                position: "absolute",
                top: "8px",
                left: "8px",
                background: "rgba(0,0,0,0.6)",
                border: "1px solid #1f2937",
                borderRadius: "4px",
                padding: "2px 8px",
                fontSize: "11px",
                color: "#6b7280",
                fontFamily: "monospace",
                zIndex: 10,
              }}>
                {view}
              </div>
              {view.includes("graph") || view.includes("topology") || view.includes("dag") ? (
                <GraphCanvas />
              ) : (
                <div style={{
                  width: "100%",
                  height: "100%",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "#374151",
                  fontFamily: "monospace",
                  fontSize: "13px",
                }}>
                  {view}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div style={{
          flex: 1,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          color: "#374151",
        }}>
          <GraphCanvas />
        </div>
      )}
    </div>
  );
}
