"use strict";

/**
 * Vaked Docs — our own documentation index.
 * Public. Deterministic. Self-hostable. No rate limits.
 *
 * Server: tools/vaked-docs/ (Go binary)
 * Default: http://localhost:9845
 *
 * GENESIS_SEAL: 7c242080
 */

import type { Tool } from "@openrouter/agent";
import { tool } from "@openrouter/agent";
import { z } from "zod";

const BASE = process.env["VAKED_DOCS_URL"] ?? "http://localhost:9845";

// ═══════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════

export interface DocSnippet {
  code?: string;
  content?: string;
  title?: string;
}

export interface DocEntry {
  package_id: string;
  query: string;
  snippets: DocSnippet[];
  fetched_at: string;
}

export interface SearchResult {
  query: string;
  results: DocEntry[];
  count: number;
}

// ═══════════════════════════════════════════════════════════════
// API client
// ═══════════════════════════════════════════════════════════════

async function api<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`Vaked Docs HTTP ${res.status}`);
  return res.json() as T;
}

export async function health(): Promise<{ status: string; genesis: string; packages: number; docs: number }> {
  return api("/health");
}

export async function registerPackage(id: string, url: string, version = "latest"): Promise<void> {
  const res = await fetch(`${BASE}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ id, url, version }),
  });
  if (!res.ok) throw new Error(`register failed: ${res.status}`);
}

export async function getDocs(pkg: string, query?: string): Promise<{ results: DocEntry[] }> {
  const qs = query ? `?q=${encodeURIComponent(query)}` : "";
  return api(`/docs/${pkg}${qs}`);
}

export async function searchDocs(query: string): Promise<SearchResult> {
  return api(`/search?q=${encodeURIComponent(query)}`);
}

export async function listPackages(): Promise<string[]> {
  const data = await api<{ packages: string[] }>("/list");
  return data.packages;
}

// ═══════════════════════════════════════════════════════════════
// Agent tools — drop-in Context7 replacement
// ═══════════════════════════════════════════════════════════════

export function createVakedDocsTools(): Tool[] {
  return [
    tool({
      name: "vaked_docs_search",
      description: "Search Vaked Docs for library documentation. Public, no rate limits. Drop-in Context7 replacement.",
      inputSchema: z.object({
        query: z.string().describe("What you need, e.g. 'std.Build API'"),
      }),
      execute: async (params) => {
        try {
          const result = await searchDocs(params.query);
          if (result.results.length === 0) return "No docs found. Register the package with /register first.";
          return "## Vaked Docs\n\n" + result.results.map((e) =>
            `### ${e.package_id}: ${e.query}\n${e.snippets.map((s) => s.code ? "```\n" + s.code + "\n```" : s.content).join("\n")}`
          ).join("\n\n");
        } catch (err) {
          return `Vaked Docs error: ${err instanceof Error ? err.message : String(err)}`;
        }
      },
    }),

    tool({
      name: "vaked_docs_register",
      description: "Register a new package for documentation indexing.",
      inputSchema: z.object({
        id: z.string().describe("Package ID, e.g. 'ziglang/zig'"),
        url: z.string().describe("Repository URL"),
      }),
      execute: async (params) => {
        try {
          await registerPackage(params.id, params.url);
          return `Package ${params.id} registered. Docs will be indexed shortly.`;
        } catch (err) {
          return `Register error: ${err instanceof Error ? err.message : String(err)}`;
        }
      },
    }),

    tool({
      name: "vaked_docs_list",
      description: "List all registered documentation packages.",
      inputSchema: z.object({}),
      execute: async () => {
        try {
          const pkgs = await listPackages();
          return `## Registered Packages (${pkgs.length})\n\n${pkgs.map((p) => `- ${p}`).join("\n")}`;
        } catch (err) {
          return `List error: ${err instanceof Error ? err.message : String(err)}`;
        }
      },
    }),
  ];
}

export function vakedDocsSystemPrompt(): string {
  return [
    "## Vaked Docs — Documentation Index",
    "",
    "Vaked Docs is our own documentation index. No rate limits. Public.",
    "Use vaked_docs_search to find documentation for any registered package.",
    "Use vaked_docs_register to add new packages.",
    "Use vaked_docs_list to see what's available.",
    "",
    "This is the primary documentation source for the Vaked swarm.",
    "Context7 is the fallback. Vaked Docs is the source of truth.",
  ].join("\n");
}
