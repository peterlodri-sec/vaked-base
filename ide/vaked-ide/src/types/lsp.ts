export interface LspPosition {
  line: number;       // 0-based
  character: number;  // 0-based
}

export interface LspRange {
  start: LspPosition;
  end: LspPosition;
}

export interface LspDiagnostic {
  range: LspRange;
  severity: 1 | 2 | 3 | 4;  // error | warning | info | hint
  code: string;
  source: string;
  message: string;
  relatedInformation?: Array<{
    location: { uri: string; range: LspRange };
    message: string;
  }>;
}

export interface LspPublishDiagnosticsParams {
  uri: string;
  diagnostics: LspDiagnostic[];
}

export interface LspCompletionItem {
  label: string;
  kind?: number;
  detail?: string;
  documentation?: string;
  insertText?: string;
}

export interface LspHoverResult {
  contents: { kind: "markdown" | "plaintext"; value: string } | null;
}

export interface LspLocation {
  uri: string;
  range: LspRange;
}

// JSON-RPC 2.0 wrapper
export interface LspMessage {
  jsonrpc: "2.0";
  id?: number | string;
  method?: string;
  params?: unknown;
  result?: unknown;
  error?: { code: number; message: string; data?: unknown };
}

let _lspMsgId = 0;
export function nextLspId(): number {
  return ++_lspMsgId;
}
