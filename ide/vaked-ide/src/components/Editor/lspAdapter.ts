import type * as Monaco from "monaco-editor";
import type { LspDiagnostic } from "@/types/lsp";

const SEVERITY_MAP: Record<number, Monaco.MarkerSeverity> = {
  1: 8,  // error
  2: 4,  // warning
  3: 2,  // info
  4: 1,  // hint
};

export function applyDiagnostics(
  monaco: typeof Monaco,
  model: Monaco.editor.ITextModel,
  diagnostics: LspDiagnostic[]
): void {
  const markers: Monaco.editor.IMarkerData[] = diagnostics.map((d) => ({
    startLineNumber: d.range.start.line + 1,
    startColumn: d.range.start.character + 1,
    endLineNumber: d.range.end.line + 1,
    endColumn: d.range.end.character + 2,
    message: `[${d.code}] ${d.message}`,
    severity: (SEVERITY_MAP[d.severity] ?? 8) as Monaco.MarkerSeverity,
    source: d.source,
    code: d.code,
  }));

  monaco.editor.setModelMarkers(model, "vakedc", markers);
}

export function clearDiagnostics(
  monaco: typeof Monaco,
  model: Monaco.editor.ITextModel
): void {
  monaco.editor.setModelMarkers(model, "vakedc", []);
}
