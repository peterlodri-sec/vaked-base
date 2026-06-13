import { useEffect } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import { TopBar } from "@/components/Layout/TopBar";
import { StatusBar } from "@/components/Layout/StatusBar";
import { Sidebar } from "@/components/Layout/Sidebar";
import { GraphCanvas } from "@/components/GraphCanvas";
import { Editor } from "@/components/Editor";
import { SessionPanel } from "@/components/SessionPanel";
import { useUIStore, useGraphStore } from "@/store";
import { useLsp } from "@/hooks/useLsp";
import { useSession } from "@/hooks/useSession";

export function App() {
  // Initialize hooks that set up global listeners
  useLsp();
  useSession();

  const { sidebarOpen, sessionPanelOpen, graphPaneHeight, editorPaneWidth } = useUIStore();
  const filePath = useGraphStore((s) => s.filePath);

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      width: "100vw",
      height: "100vh",
      background: "#0d1117",
      color: "#e2e8f0",
      overflow: "hidden",
    }}>
      <TopBar />

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Left sidebar */}
        {sidebarOpen && <Sidebar />}

        {/* Center: graph + editor split */}
        <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minWidth: 0 }}>
          {/* Graph canvas */}
          <div style={{ height: `${graphPaneHeight}%`, minHeight: "200px", overflow: "hidden" }}>
            <ReactFlowProvider>
              <GraphCanvas />
            </ReactFlowProvider>
          </div>

          {/* Resize handle */}
          <div style={{
            height: "4px",
            background: "#1f2937",
            cursor: "row-resize",
            flexShrink: 0,
          }} />

          {/* Editor pane */}
          <div style={{ flex: 1, overflow: "hidden", minHeight: "100px" }}>
            <Editor filePath={filePath ?? undefined} />
          </div>
        </div>

        {/* Right: AI session panel */}
        {sessionPanelOpen && (
          <div style={{ width: "340px", minWidth: "280px", overflow: "hidden", flexShrink: 0 }}>
            <SessionPanel />
          </div>
        )}
      </div>

      <StatusBar />
    </div>
  );
}
