import { create } from "zustand";

type SidebarTab = "schema" | "capability" | "provenance" | "surface";
type SessionTab = "human" | "a2a" | "gateway";

interface UIStore {
  sidebarOpen: boolean;
  sessionPanelOpen: boolean;
  sidebarTab: SidebarTab;
  sessionTab: SessionTab;
  editorPaneWidth: number;   // pixels
  graphPaneHeight: number;   // percentage 0-100

  toggleSidebar: () => void;
  toggleSessionPanel: () => void;
  setSidebarTab: (tab: SidebarTab) => void;
  setSessionTab: (tab: SessionTab) => void;
  setEditorPaneWidth: (w: number) => void;
  setGraphPaneHeight: (h: number) => void;
}

export const useUIStore = create<UIStore>((set) => ({
  sidebarOpen: true,
  sessionPanelOpen: true,
  sidebarTab: "schema",
  sessionTab: "human",
  editorPaneWidth: 480,
  graphPaneHeight: 60,

  toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
  toggleSessionPanel: () => set((s) => ({ sessionPanelOpen: !s.sessionPanelOpen })),
  setSidebarTab: (tab) => set({ sidebarTab: tab }),
  setSessionTab: (tab) => set({ sessionTab: tab }),
  setEditorPaneWidth: (w) => set({ editorPaneWidth: w }),
  setGraphPaneHeight: (h) => set({ graphPaneHeight: h }),
}));
