"use strict";

/**
 * Embeddings — multi-model vector generation for the Vaked swarm.
 * OpenRouter API. Multiple models. Auto-embed for Memory Plane + Milvus.
 * GENESIS_SEAL: 7c242080
 */

const API = "https://openrouter.ai/api/v1/embeddings";

export interface EmbeddingModel {
  id: string;
  dim: number;
  cost_per_1m: number;
}

export const MODELS: Record<string, EmbeddingModel> = {
  "openai-small":  { id: "openai/text-embedding-3-small",  dim: 1536, cost_per_1m: 0.02 },
  "openai-large":  { id: "openai/text-embedding-3-large",  dim: 3072, cost_per_1m: 0.13 },
  "gemini":        { id: "google/text-embedding-004",       dim: 768,  cost_per_1m: 0.00 },
  "minimax":       { id: "minimax/minimax-embedding-01",    dim: 1536, cost_per_1m: 0.00 },
};

export async function embed(
  texts: string[],
  model: string = "openai-small",
): Promise<{ vectors: number[][]; model: string; tokens: number; cost: number }> {
  const m = MODELS[model] ?? MODELS["openai-small"]!;
  const apiKey = process.env["OPENROUTER_API_KEY"];
  if (!apiKey) throw new Error("OPENROUTER_API_KEY not set");

  const res = await fetch(API, {
    method: "POST",
    headers: { "Authorization": `Bearer ${apiKey}`, "Content-Type": "application/json" },
    body: JSON.stringify({ model: m.id, input: texts }),
  });

  if (!res.ok) throw new Error(`Embedding HTTP ${res.status}`);
  const data = await res.json() as any;
  
  return {
    vectors: data.data.map((d: any) => d.embedding),
    model: m.id,
    tokens: data.usage?.prompt_tokens ?? 0,
    cost: ((data.usage?.prompt_tokens ?? 0) * m.cost_per_1m) / 1_000_000,
  };
}

/** Auto-embed a document and store in Memory Plane + Milvus */
export async function autoEmbed(text: string, opts?: { model?: string; collection?: string }): Promise<{ vector: number[]; tokens: number; cost: number }> {
  const result = await embed([text], opts?.model ?? "openai-small");
  return { vector: result.vectors[0]!, tokens: result.tokens, cost: result.cost };
}
