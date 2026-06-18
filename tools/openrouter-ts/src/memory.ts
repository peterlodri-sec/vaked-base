"use strict";
/**
import { tool } from "@openrouter/agent";
import type { Tool } from "@openrouter/agent";
import { z } from "zod";
const MEM_URL = process.env["MEMORYD_URL"] ?? "http://localhost:8420";
interface MemoryEntry {
  key: string;
  content: string;
  agent: string;
  scope: string;
  hash: string;
  timestamp: string;
}
async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${MEM_URL}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`Memoryd HTTP ${res.status}`);
  return res.json() as T;
}
export async function storeMemory(key: string, content: string, agent = "vaked-agent", scope = "default"): Promise<MemoryEntry> {
  return api("POST", "/store", { key, content, agent, scope });
}
export async function recallMemories(agent?: string, scope?: string, keyPrefix?: string): Promise<MemoryEntry[]> {
  const params = new URLSearchParams();
  if (agent) params.set("agent", agent);
  if (scope) params.set("scope", scope);
  if (keyPrefix) params.set("key-prefix", keyPrefix);
  return api("GET", `/recall?${params.toString()}`);
}
export async function forgetMemory(hash: string, agent: string): Promise<void> {
  await api("POST", "/forget", { hash, agent });
}
export async function verifyMemory(): Promise<{ intact: boolean; entries: number }> {
  return api("GET", "/verify");
}
const storeInput = z.object({
  key: z.string().describe("Memory key — unique identifier"),
  content: z.string().describe("Content to store"),
  scope: z.string().optional().default("default"),
});
const recallInput = z.object({
  agent: z.string().optional().describe("Filter by agent name"),
  scope: z.string().optional().describe("Filter by scope"),
  keyPrefix: z.string().optional().describe("Filter by key prefix"),
});
const forgetInput = z.object({
  hash: z.string().describe("Content hash from recall results"),
});
export function createMemoryTools(): Tool[] {
  return [
    tool({
      name: "memory_store",
      description: "Store a fact in the Vaked memory plane. Event-sourced, deterministic, hash-chained. Survives restarts.",
      inputSchema: storeInput,
      execute: async (params) => {
        try {
          const entry = await storeMemory(params.key, params.content, "vaked-agent", params.scope);
          return `Stored: ${entry.key} (hash: ${entry.hash.slice(0, 12)}, scope: ${entry.scope})`;
        } catch (err) {
          return `Memory error: ${err instanceof Error ? err.message : String(err)}`;
        }
      },
    }),
    tool({
      name: "memory_recall",
      description: "Recall facts from the Vaked memory plane. Query by agent, scope, or key prefix.",
      inputSchema: recallInput,
      execute: async (params) => {
        try {
          const entries = await recallMemories(params.agent, params.scope, params.keyPrefix);
          if (entries.length === 0) return "No memories found.";
          return `## Memory Recall (${entries.length} entries)\n\n${entries.map((e) => `- **${e.key}** \`${e.hash.slice(0, 12)}\` [${e.scope}] ${e.timestamp}\n  ${e.content.slice(0, 200)}`).join("\n")}`;
        } catch (err) {
          return `Memory error: ${err instanceof Error ? err.message : String(err)}`;
        }
      },
    }),
    tool({
      name: "memory_forget",
      description: "Remove a fact from the Vaked memory plane by content hash. Audit-logged.",
      inputSchema: forgetInput,
      execute: async (params) => {
        try {
          await forgetMemory(params.hash, "vaked-agent");
          return `Forgotten: ${params.hash.slice(0, 12)}`;
        } catch (err) {
          return `Memory error: ${err instanceof Error ? err.message : String(err)}`;
        }
      },
    }),
    tool({
      name: "memory_verify",
      description: "Verify the memory plane event chain integrity.",
      inputSchema: z.object({}),
      execute: async () => {
        try {
          const result = await verifyMemory();
          return `Memory plane: ${result.intact ? "✅ intact" : "❌ corrupted"} · ${result.entries} entries`;
        } catch (err) {
          return `Memory error: ${err instanceof Error ? err.message : String(err)}`;
        }
      },
    }),
  ];
}
export function memorySystemPrompt(): string {
  return [
    "## Vaked Memory Plane",
    "",
    "You have access to the Vaked memory plane. Use it to:",
    "- **memory_store**: Remember facts across sessions (event-sourced)",
    "- **memory_recall**: Recall facts by agent, scope, or key",
    "- **memory_forget**: Remove outdated facts (audit-logged)",
    "- **memory_verify**: Check event chain integrity",
    "",
    "The memory plane is deterministic, hash-chained, and survives restarts.",
    "Store important findings, decisions, and context for future recall.",
  ].join("\n");
}