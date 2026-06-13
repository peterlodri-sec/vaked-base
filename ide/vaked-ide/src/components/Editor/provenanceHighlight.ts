import type * as Monaco from "monaco-editor";
import type { VakedNode } from "@/types/graph";

let _decorations: string[] = [];

export function highlightNodeProvenance(
  editor: Monaco.editor.IStandaloneCodeEditor,
  node: VakedNode | null
): void {
  _decorations = editor.deltaDecorations(_decorations, []);

  if (!node?.provenance?.span) return;

  const { line, col, byteStart, byteEnd } = node.provenance.span;
  const source = editor.getModel()?.getValue() ?? "";

  // Compute end line/col from byteEnd
  let endLine = line;
  let endCol = col;
  let byteCount = 0;
  const lines = source.split("\n");
  for (let i = 0; i < lines.length; i++) {
    const lineLen = lines[i].length + 1; // +1 for newline
    if (byteCount + lineLen > byteEnd) {
      endLine = i + 1;
      endCol = byteEnd - byteCount + 1;
      break;
    }
    byteCount += lineLen;
  }

  _decorations = editor.deltaDecorations([], [
    {
      range: {
        startLineNumber: line,
        startColumn: col,
        endLineNumber: endLine,
        endColumn: endCol,
      },
      options: {
        isWholeLine: false,
        className: "vaked-provenance-highlight",
        glyphMarginClassName: "vaked-provenance-glyph",
        overviewRuler: {
          color: "#fbbf24",
          position: 4, // Center
        },
      },
    },
  ]);

  // Reveal the line
  editor.revealLineInCenterIfOutsideViewport(line);
}
