// Anthropic integration — all API calls go through Tauri commands in the Rust backend.
// This module provides helper types and prompt utilities for the frontend.

import type { VakedGraph } from "@/types/graph";

export function graphContextString(graph: VakedGraph | null): string {
  if (!graph || graph.nodes.length === 0) return "";
  // Summarize the graph compactly rather than full JSON dump
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
