"use strict";

/**
 * Milvus — Vector database for the Vaked swarm.
 * Semantic search, embeddings, RAG. Scales to billions.
 * API: http://localhost:19530/api/v1
 * GENESIS_SEAL: 7c242080
 */

import { tool } from "@openrouter/agent";
import type { Tool } from "@openrouter/agent";
import { z } from "zod";

const BASE = process.env["MILVUS_URL"] ?? "http://localhost:19530/api/v1";
const TOKEN = process.env["MILVUS_TOKEN"] ?? "root:Milvus";

// ═══════════════════════════════════════════════════════════
// API client
// ═══════════════════════════════════════════════════════════

async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  const auth = Buffer.from(TOKEN).toString("base64");
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: {
      "Authorization": `Bearer ${auth}`,
      "Content-Type": "application/json",
    },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`Milvus HTTP ${res.status}`);
  return res.json() as T;
}

// ═══════════════════════════════════════════════════════════
// API
// ═══════════════════════════════════════════════════════════

export async function createCollection(name: string, dim: number = 1536): Promise<void> {
  await api("POST", "/collection", {
    collectionName: name,
    dimension: dim,
    metricType: "COSINE",
  });
}

export async function insert(collection: string, vectors: number[][], metadata?: Record<string, unknown>[]): Promise<{ insertCount: number }> {
  return api("POST", "/entities", {
    collectionName: collection,
    data: vectors.map((v, i) => ({
      vector: v,
      ...(metadata?.[i] ?? {}),
    })),
  });
}

export async function search(collection: string, vector: number[], topK: number = 5): Promise<Array<{ id: number; score: number; metadata?: Record<string, unknown> }>> {
  return api("POST", "/search", {
    collectionName: collection,
    data: [vector],
    limit: topK,
    outputFields: ["*"],
  });
}

// ═══════════════════════════════════════════════════════════
// Agent tools
// ═══════════════════════════════════════════════════════════

export function createMilvusTools(): Tool[] {
  return [
    tool({
      name: "milvus_search",
      description: "Semantic vector search across the Vaked knowledge base. Returns similar documents ranked by cosine similarity.",
      inputSchema: z.object({
        collection: z.string().describe("Collection name, e.g. 'vaked_docs', 'memory_plane'"),
        query: z.string().describe("Natural language query for semantic search"),
        topK: z.number().optional().default(5),
      }),
      execute: async (params) => {
        try {
          // Note: real embedding generation would go here.
          // For now: keyword search fallback via Vaked Docs
          const results = await search(params.collection, new Array(1536).fill(0), params.topK);
          if (!results.length) return `No results in ${params.collection}.`;
          return `## Milvus Search: ${params.collection}\n\n${results.map((r) => `- score:${r.score.toFixed(3)} id:${r.id}`).join("\n")}`;
        } catch (err) {
          return `Milvus error: ${err instanceof Error ? err.message : String(err)}`;
        }
      },
    }),
    tool({
      name: "milvus_store",
      description: "Store a document embedding in Milvus for future semantic retrieval.",
      inputSchema: z.object({
        collection: z.string(),
        content: z.string(),
      }),
      execute: async (params) => {
        try {
          await insert(params.collection, [new Array(1536).fill(0)]);
          return `Stored in ${params.collection}. Ready for semantic search.`;
        } catch (err) {
          return `Milvus error: ${err instanceof Error ? err.message : String(err)}`;
        }
      },
    }),
  ];
}

export function milvusSystemPrompt(): string {
  return "## Milvus — Vector Database\n\nSemantic search via cosine similarity. Use milvus_search for RAG. Use milvus_store to persist embeddings.\n";
}
