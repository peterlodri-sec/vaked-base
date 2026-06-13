import type * as Monaco from "monaco-editor";

const KIND_KEYWORDS = [
  "runtime", "input", "engine", "host", "network", "filesystem", "mcp", "ebpf",
  "budget", "observability", "runclass", "workflow", "index", "catalog", "stream",
  "fiber", "surface", "mesh", "device", "mediaPipeline", "parallel", "schema",
  "capability", "service", "secret", "hostResource", "ingress", "container", "memory",
];

const FIELD_KEYWORDS = [
  "field", "open", "grant", "order", "node", "use", "on", "inherit",
];

const REFINEMENT_KEYWORDS = [
  "required", "optional", "default", "oneof", "nonempty", "matches", "in",
];

const BOOL_KEYWORDS = ["true", "false"];

export function registerVakedLanguage(monaco: typeof Monaco): void {
  monaco.languages.register({ id: "vaked", extensions: [".vaked"] });

  monaco.languages.setMonarchTokensProvider("vaked", {
    keywords: KIND_KEYWORDS,
    fieldKeywords: FIELD_KEYWORDS,
    refinements: REFINEMENT_KEYWORDS,
    bools: BOOL_KEYWORDS,

    tokenizer: {
      root: [
        // Comments
        [/#.*$/, "comment"],

        // Strings
        [/"([^"\\]|\\.)*"/, "string"],
        [/'([^'\\]|\\.)*'/, "string"],

        // Regex literals in matches
        [/\/[^/]+\/[gimsuy]*/, "regexp"],

        // Numbers (duration, bytes, plain)
        [/\b\d+(\.\d+)?(ns|us|ms|s|m|h|d|w)\b/, "number.float"],
        [/\b\d+(\.\d+)?(B|KB|MB|GB|TB)\b/, "number.float"],
        [/\b\d+(\.\d+)?\b/, "number"],

        // Arrows and operators
        [/->/, "keyword.operator"],
        [/[:=<>!|&+\-*\/]/, "operators"],

        // Identifiers and keywords
        [
          /[a-zA-Z_][a-zA-Z0-9_]*/,
          {
            cases: {
              "@keywords": "keyword",
              "@fieldKeywords": "keyword.field",
              "@refinements": "keyword.refinement",
              "@bools": "constant.bool",
              "@default": "identifier",
            },
          },
        ],

        // Brackets
        [/[{}[\]()]/, "delimiter.bracket"],

        // Path literals (./... or /...)
        [/\.?\/[^\s,;)}\]]+/, "string.path"],
      ],
    },
  });

  monaco.languages.setLanguageConfiguration("vaked", {
    comments: { lineComment: "#" },
    brackets: [
      ["{", "}"],
      ["[", "]"],
      ["(", ")"],
    ],
    autoClosingPairs: [
      { open: "{", close: "}" },
      { open: "[", close: "]" },
      { open: "(", close: ")" },
      { open: '"', close: '"' },
    ],
    surroundingPairs: [
      { open: "{", close: "}" },
      { open: "[", close: "]" },
      { open: '"', close: '"' },
    ],
    indentationRules: {
      increaseIndentPattern: /\{[^}]*$/,
      decreaseIndentPattern: /^\s*\}/,
    },
  });

  monaco.editor.defineTheme("vaked-dark", {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "comment", foreground: "6b7280", fontStyle: "italic" },
      { token: "keyword", foreground: "a78bfa", fontStyle: "bold" },
      { token: "keyword.field", foreground: "34d399" },
      { token: "keyword.refinement", foreground: "fbbf24" },
      { token: "keyword.operator", foreground: "f97316", fontStyle: "bold" },
      { token: "string", foreground: "86efac" },
      { token: "string.path", foreground: "93c5fd" },
      { token: "number", foreground: "fb923c" },
      { token: "number.float", foreground: "fb923c" },
      { token: "constant.bool", foreground: "f472b6" },
      { token: "regexp", foreground: "f9a8d4" },
      { token: "identifier", foreground: "e2e8f0" },
      { token: "operators", foreground: "94a3b8" },
      { token: "delimiter.bracket", foreground: "64748b" },
    ],
    colors: {
      "editor.background": "#0d1117",
      "editor.foreground": "#e2e8f0",
      "editor.lineHighlightBackground": "#1f2937",
      "editorLineNumber.foreground": "#374151",
      "editorLineNumber.activeForeground": "#9ca3af",
      "editor.selectionBackground": "#1e3a5f",
      "editorCursor.foreground": "#f97316",
      "editorWidget.background": "#111827",
    },
  });
}
