// OpenRouter Agent SDK integration — all API calls go through Tauri commands in the Rust backend.
// This module provides helper types, prompt utilities, and SDK type re-exports for the frontend.
//
// Migrated from anthropic.ts — the @anthropic-ai/sdk dependency has been replaced
// with @openrouter/agent for multi-model, multi-provider agent capabilities.

import type { VakedGraph } from "@/types/graph";

// ── Provider-agnostic utilities (kept from anthropic.ts) ────────────────────

export function graphContextString(graph: VakedGraph | null): string {
  if (!graph || graph.nodes.length === 0) return "";
  const nodes = graph.nodes.map((n) => `${n.kind} ${n.name}`).join(", ");
  const edges = graph.edges
    .filter((e) => e.label === "routes_to" || e.label === "depends_on")
    .map((e) => `${e.from} -[${e.label}]-> ${e.to}`)
    .slice(0, 20)
    .join("; ");
  return `nodes: [${nodes}]\nedges: [${edges}]`;
}

export function parseSuggestedEdit(text: string): {
  range: { startLine: number; startCol: number; endLine: number; endCol: number };
  newText: string;
  rationale: string;
} | null {
  const match = text.match(/<suggest_edit>([\s\S]*?)<\/suggest_edit>/);
  if (!match) return null;
  const body = match[1];

  try {
    const rangeMatch = body.match(/range:\s*(\{[\s\S]*?\})/);
    const newTextMatch = body.match(/newText:\s*\|\n([\s\S]*?)(?=rationale:|$)/);
    const rationaleMatch = body.match(/rationale:\s*(.+)/);

    if (!rangeMatch) return null;
    const range = JSON.parse(rangeMatch[1]);
    const newText = newTextMatch?.[1]?.trim() ?? "";
    const rationale = rationaleMatch?.[1]?.trim() ?? "";
    return { range, newText, rationale };
  } catch {
    return null;
  }
}

// ── OpenRouter Agent SDK types (re-exported for frontend use) ────────────────

// The @openrouter/agent package provides:
//   callModel(client, request) → ModelResult
//   ModelResult.getText() → Promise<string>
//   ModelResult.getResponse() → Promise<OpenResponsesResult> (with usage: { inputTokens, outputTokens })
//   ModelResult.getTextStream() → AsyncIterableIterator<string>

export { OpenRouter } from "@openrouter/agent";
export type {
  CallModelInput,
  Tool,
  ToolWithExecute,
  StopCondition,
  TurnContext,
} from "@openrouter/agent";
export { stepCountIs, maxCost, maxTokensUsed, finishReasonIs } from "@openrouter/agent";
export { tool } from "@openrouter/agent";

// ── OpenRouter model catalog ────────────────────────────────────────────────

export interface ModelEntry {
  id: string;
  label: string;
  promptCost: number;
  completionCost: number;
}

export const OPENROUTER_MODELS: Record<string, ModelEntry> = {
  deepseek: {
    id: "deepseek/deepseek-v4-pro",
    label: "DeepSeek V4 Pro",
    promptCost: 0.27,
    completionCost: 0.27,
  },
  claude: {
    id: "anthropic/claude-opus-4-8-fast",
    label: "Claude Opus 4.8",
    promptCost: 15.0,
    completionCost: 75.0,
  },
  gemini: {
    id: "google/gemini-2.5-flash",
    label: "Gemini 2.5 Flash",
    promptCost: 0.15,
    completionCost: 0.6,
  },
  qwen: {
    id: "qwen/qwen3-235b-a22b-thinking",
    label: "Qwen3 235B Thinking",
    promptCost: 2.5,
    completionCost: 5.0,
  },
  llama: {
    id: "meta-llama/llama-4-maverick",
    label: "Llama 4 Maverick",
    promptCost: 0.2,
    completionCost: 0.6,
  },
};

// ── Agent role → model mapping ──────────────────────────────────────────────

export const AGENT_MODEL_MAP: Record<string, string> = {
  "openrouter": "deepseek/deepseek-v4-pro",
  "deepseek": "deepseek/deepseek-v4-pro",
  "claude": "anthropic/claude-opus-4-8-fast",
  "gemini": "google/gemini-2.5-flash",
  "schema-advisor": "anthropic/claude-opus-4-8-fast",
  "capability-expert": "deepseek/deepseek-v4-pro",
  "lowering-guide": "anthropic/claude-opus-4-8-fast",
};
