import { useCallback, useRef } from "react";
import { ReactFlowProvider } from "@xyflow/react";
import { TopBar } from "@/components/Layout/TopBar";
import { StatusBar } from "@/components/Layout/StatusBar";
import { Sidebar } from "@/components/Layout/Sidebar";
import { GraphCanvas } from "@/components/GraphCanvas";
import { Editor } from "@/components/Editor";
import { SessionPanel } from "@/components/SessionPanel";
import { Terminal } from "@/components/Terminal";
import { CommandPalette } from "@/components/CommandPalette";
import { useUIStore, useGraphStore } from "@/store";
import { useLsp } from "@/hooks/useLsp";
import { useSession } from "@/hooks/useSession";
import { useResizeDrag } from "@/hooks/useResizeDrag";
import { useCommandPalette } from "@/hooks/useCommandPalette";

export function App() {
  useLsp();
  useSession();
  useCommandPalette();

  const {
    sidebarOpen,
    sessionPanelOpen,
    terminalOpen,
    commandPaletteOpen,
    sidebarWidth,
    graphPaneHeight,
    terminalHeight,
    setGraphPaneHeight,
    setTerminalHeight,
    setSidebarWidth,
  } = useUIStore();
  const filePath = useGraphStore((s) => s.filePath);

  // Ref to the center column so graph-drag converts px → %
  const centerRef = useRef<HTMLDivElement>(null);

  const graphEdgeDrag = useResizeDrag(
    "y",
    useCallback((dy) => {
      const h = centerRef.current?.clientHeight ?? 600;
      setGraphPaneHeight(graphPaneHeight + (dy / h) * 100);
    }, [graphPaneHeight, setGraphPaneHeight]),
  );

  const terminalEdgeDrag = useResizeDrag(
    "y",
    useCallback((dy) => {
      setTerminalHeight(terminalHeight - dy);
    }, [terminalHeight, setTerminalHeight]),
  );

  const sidebarEdgeDrag = useResizeDrag(
    "x",
    useCallback((dx) => {
      setSidebarWidth(sidebarWidth + dx);
    }, [sidebarWidth, setSidebarWidth]),
  );

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      width: "100vw",
      height: "100vh",
      background: "#0d1117",
      color: "#e2e8f0",
      overflow: "hidden",
      userSelect: "none",
    }}>
      <TopBar />

      <div style={{ display: "flex", flex: 1, overflow: "hidden" }}>
        {/* Left sidebar */}
        {sidebarOpen && (
          <>
            <div style={{ width: `${sidebarWidth}px`, minWidth: "160px", flexShrink: 0, overflow: "hidden" }}>
              <Sidebar />
            </div>
            {/* Sidebar resize handle */}
            <div
              {...sidebarEdgeDrag}
              style={{
                width: "4px",
                cursor: "col-resize",
                background: "#1f2937",
                flexShrink: 0,
                transition: "background 0.1s",
              }}
              onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = "#6366f1"; }}
              onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = "#1f2937"; }}
            />
          </>
        )}

        {/* Center: graph + editor + terminal */}
        <div ref={centerRef} style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden", minWidth: 0 }}>
          {/* Graph canvas */}
          <div style={{ height: `${graphPaneHeight}%`, minHeight: "120px", overflow: "hidden", flexShrink: 0 }}>
            <ReactFlowProvider>
              <GraphCanvas />
            </ReactFlowProvider>
          </div>

          {/* Graph / editor resize handle */}
          <div
            {...graphEdgeDrag}
            style={{
              height: "4px",
              cursor: "row-resize",
              background: "#1f2937",
              flexShrink: 0,
              transition: "background 0.1s",
            }}
            onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = "#6366f1"; }}
            onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = "#1f2937"; }}
          />

          {/* Editor pane */}
          <div style={{ flex: 1, overflow: "hidden", minHeight: "80px" }}>
            <Editor filePath={filePath ?? undefined} />
          </div>

          {/* Terminal pane */}
          {terminalOpen && (
            <>
              <div
                {...terminalEdgeDrag}
                style={{
                  height: "4px",
                  cursor: "row-resize",
                  background: "#1f2937",
                  flexShrink: 0,
                  transition: "background 0.1s",
                }}
                onMouseEnter={(e) => { (e.currentTarget as HTMLDivElement).style.background = "#6366f1"; }}
                onMouseLeave={(e) => { (e.currentTarget as HTMLDivElement).style.background = "#1f2937"; }}
              />
              <div style={{ height: `${terminalHeight}px`, minHeight: "80px", overflow: "hidden", flexShrink: 0 }}>
                <Terminal />
              </div>
            </>
          )}
        </div>

        {/* Right: AI session panel */}
        {sessionPanelOpen && (
          <div style={{ width: "340px", minWidth: "260px", overflow: "hidden", flexShrink: 0 }}>
            <SessionPanel />
          </div>
        )}
      </div>

      <StatusBar />

      {/* Global command palette overlay */}
      {commandPaletteOpen && <CommandPalette />}
    </div>
  );
}
