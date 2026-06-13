import { create } from "zustand";

type SidebarTab = "schema" | "capability" | "provenance" | "surface";
type SessionTab = "human" | "a2a" | "gateway";

interface UIStore {
  sidebarOpen: boolean;
  sessionPanelOpen: boolean;
  terminalOpen: boolean;
  commandPaletteOpen: boolean;
  sidebarTab: SidebarTab;
  sessionTab: SessionTab;
  sidebarWidth: number;        // pixels
  editorPaneWidth: number;     // pixels (legacy; unused by layout)
  graphPaneHeight: number;     // percentage 0-100
  terminalHeight: number;      // pixels

  toggleSidebar: () => void;
  toggleSessionPanel: () => void;
  toggleTerminal: () => void;
  openCommandPalette: () => void;
  closeCommandPalette: () => void;
  setSidebarTab: (tab: SidebarTab) => void;
  setSessionTab: (tab: SessionTab) => void;
  setSidebarWidth: (w: number) => void;
  setEditorPaneWidth: (w: number) => void;
  setGraphPaneHeight: (h: number) => void;
  setTerminalHeight: (h: number) => void;
}

export const useUIStore = create<UIStore>((set) => ({
  sidebarOpen: true,
  sessionPanelOpen: true,
  terminalOpen: false,
  commandPaletteOpen: false,
  sidebarTab: "schema",
  sessionTab: "human",
  sidebarWidth: 280,
  editorPaneWidth: 480,
  graphPaneHeight: 60,
  terminalHeight: 240,

  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  toggleSessionPanel: () => set((s) => ({ sessionPanelOpen: !s.sessionPanelOpen })),
  toggleTerminal: () => set((s) => ({ terminalOpen: !s.terminalOpen })),
  openCommandPalette: () => set({ commandPaletteOpen: true }),
  closeCommandPalette: () => set({ commandPaletteOpen: false }),
  setSidebarTab: (tab) => set({ sidebarTab: tab }),
  setSessionTab: (tab) => set({ sessionTab: tab }),
  setSidebarWidth: (w) => set({ sidebarWidth: Math.max(160, Math.min(500, w)) }),
  setEditorPaneWidth: (w) => set({ editorPaneWidth: w }),
  setGraphPaneHeight: (h) => set({ graphPaneHeight: Math.max(20, Math.min(85, h)) }),
  setTerminalHeight: (h) => set({ terminalHeight: Math.max(80, Math.min(600, h)) }),
}));
