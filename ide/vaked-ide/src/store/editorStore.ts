import { create } from "zustand";
import type { LspDiagnostic } from "@/types/lsp";
import type { SuggestedEdit } from "@/types/session";

interface EditorStore {
  source: string;
  cursorLine: number;  // 1-based
  cursorCol: number;   // 1-based
  diagnostics: LspDiagnostic[];
  lspReady: boolean;
  pendingEdit: SuggestedEdit | null;

  setSource: (src: string) => void;
  setCursor: (line: number, col: number) => void;
  setDiagnostics: (diags: LspDiagnostic[]) => void;
  setLspReady: (ready: boolean) => void;
  setPendingEdit: (edit: SuggestedEdit) => void;
  clearPendingEdit: () => void;
}

export const useEditorStore = create<EditorStore>((set) => ({
  source: "",
  cursorLine: 1,
  cursorCol: 1,
  diagnostics: [],
  lspReady: false,
  pendingEdit: null,

  setSource: (src) => set({ source: src }),
  setCursor: (line, col) => set({ cursorLine: line, cursorCol: col }),
  setDiagnostics: (diags) => set({ diagnostics: diags }),
  setLspReady: (ready) => set({ lspReady: ready }),
  setPendingEdit: (edit) => set({ pendingEdit: edit }),
  clearPendingEdit: () => set({ pendingEdit: null }),
}));
