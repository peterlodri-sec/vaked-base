import { useEffect, useRef, useCallback } from "react";
import MonacoEditor, { OnMount } from "@monaco-editor/react";
import type * as Monaco from "monaco-editor";
import { registerVakedLanguage } from "./vakedLanguage";
import { applyDiagnostics } from "./lspAdapter";
import { highlightNodeProvenance } from "./provenanceHighlight";
import { useEditorStore, useGraphStore } from "@/store";
import { useLsp } from "@/hooks/useLsp";
import { useVakedc } from "@/hooks/useVakedc";

interface EditorProps {
  filePath?: string;
}

export function Editor({ filePath }: EditorProps) {
  const editorRef = useRef<Monaco.editor.IStandaloneCodeEditor | null>(null);
  const monacoRef = useRef<typeof Monaco | null>(null);
  const versionRef = useRef(1);

  const { source, setSource, diagnostics } = useEditorStore((s) => ({
    source: s.source,
    setSource: s.setSource,
    diagnostics: s.diagnostics,
  }));

  const highlightedNodeId = useGraphStore((s) => s.highlightedNodeId);
  const graph = useGraphStore((s) => s.graph);
  const { notifyOpen, notifyChange } = useLsp();
  const { parseFileDebounced } = useVakedc();

  const handleMount: OnMount = useCallback((editor, monaco) => {
    editorRef.current = editor;
    monacoRef.current = monaco;
    registerVakedLanguage(monaco);
    monaco.editor.setTheme("vaked-dark");
  }, []);

  // Apply LSP diagnostics to Monaco markers
  useEffect(() => {
    const editor = editorRef.current;
    const monaco = monacoRef.current;
    if (!editor || !monaco) return;
    const model = editor.getModel();
    if (!model) return;
    applyDiagnostics(monaco, model, diagnostics);
  }, [diagnostics]);

  // Highlight provenance span when a node is selected in the graph
  useEffect(() => {
    const editor = editorRef.current;
    if (!editor) return;
    const node = highlightedNodeId
      ? graph.nodes.find((n) => n.id === highlightedNodeId) ?? null
      : null;
    highlightNodeProvenance(editor, node);
  }, [highlightedNodeId, graph]);

  // Notify LSP when file opens
  useEffect(() => {
    if (!filePath || !source) return;
    const uri = `file://${filePath}`;
    notifyOpen(uri, source);
  }, [filePath]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleChange = useCallback(
    (value: string | undefined) => {
      const text = value ?? "";
      setSource(text);
      versionRef.current++;

      if (filePath) {
        const uri = `file://${filePath}`;
        notifyChange(uri, text, versionRef.current);
        parseFileDebounced(filePath);
      }
    },
    [setSource, filePath, notifyChange, parseFileDebounced]
  );

  return (
    <div style={{ width: "100%", height: "100%", overflow: "hidden" }}>
      <style>{`
        .vaked-provenance-highlight {
          background: rgba(251, 191, 36, 0.12);
          border-left: 3px solid #fbbf24;
        }
        .vaked-provenance-glyph::before {
          content: "►";
          color: #fbbf24;
          font-size: 10px;
        }
      `}</style>
      <MonacoEditor
        height="100%"
        language="vaked"
        theme="vaked-dark"
        value={source}
        onChange={handleChange}
        onMount={handleMount}
        options={{
          fontSize: 13,
          fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
          fontLigatures: true,
          lineNumbers: "on",
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          wordWrap: "on",
          tabSize: 2,
          insertSpaces: true,
          renderWhitespace: "none",
          bracketPairColorization: { enabled: true },
          glyphMargin: true,
          folding: true,
          renderLineHighlight: "all",
          smoothScrolling: true,
          cursorBlinking: "phase",
        }}
      />
    </div>
  );
}
