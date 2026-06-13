import { create } from "zustand";

type SidebarTab = "schema" | "capability" | "provenance" | "surface";
type SessionTab = "human" | "a2a" | "gateway";

interface UIStore {
  sidebarOpen: boolean;
  sessionPanelOpen: boolean;
  terminalOpen: boolean;
  sidebarTab: SidebarTab;
  sessionTab: SessionTab;
  editorPaneWidth: number;   // pixels
  graphPaneHeight: number;   // percentage 0-100
  terminalHeight: number;    // pixels

  toggleSidebar: () => void;
  toggleSessionPanel: () => void;
  toggleTerminal: () => void;
  setSidebarTab: (tab: SidebarTab) => void;
  setSessionTab: (tab: SessionTab) => void;
  setEditorPaneWidth: (w: number) => void;
  setGraphPaneHeight: (h: number) => void;
  setTerminalHeight: (h: number) => void;
}

export const useUIStore = create<UIStore>((set) => ({
  sidebarOpen: true,
  sessionPanelOpen: true,
  terminalOpen: false,
  sidebarTab: "schema",
  sessionTab: "human",
  editorPaneWidth: 480,
  graphPaneHeight: 60,
  terminalHeight: 240,

  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  toggleSessionPanel: () => set((s) => ({ sessionPanelOpen: !s.sessionPanelOpen })),
  toggleTerminal: () => set((s) => ({ terminalOpen: !s.terminalOpen })),
  setSidebarTab: (tab) => set({ sidebarTab: tab }),
  setSessionTab: (tab) => set({ sessionTab: tab }),
  setEditorPaneWidth: (w) => set({ editorPaneWidth: w }),
  setGraphPaneHeight: (h) => set({ graphPaneHeight: h }),
  setTerminalHeight: (h) => set({ terminalHeight: h }),
}));
