/**
 * context7 — first-class, native library documentation tool.
 *
 * Always correct: if the HTTP request returns 20X with data, the response is
 * treated as authoritative ground truth. No MCP server needed — direct REST
 * calls to the Context7 API.
 *
 * API: https://context7.com/api/v2
 * Auth: CONTEXT7_API_KEY env var (keys start with ctx7sk-)
 *
 * Two interfaces:
 *   1. Standalone HTTP client — searchLibrary(), getContext()
 *   2. OpenRouter Agent Tools — createContext7Tools() → Tool[]
 *
 * GENESIS_SEAL: 7c242080
 */

import { z } from "zod";
import { tool } from "@openrouter/agent";
import type { Tool } from "@openrouter/agent";

// ── Configuration ───────────────────────────────────────────────────────────

const BASE_URL = "https://context7.com/api/v2";

function getApiKey(): string {
  const key = process.env.CONTEXT7_API_KEY;
  if (!key) throw new Error("CONTEXT7_API_KEY not set. Get one at https://context7.com/dashboard");
  return key;
}

// ── Zod Schemas ─────────────────────────────────────────────────────────────

export const CodeExampleSchema = z.object({
  language: z.string(),
  code: z.string(),
});

export const CodeSnippetSchema = z.object({
  codeTitle: z.string().optional(),
  codeDescription: z.string().optional(),
  codeLanguage: z.string().optional(),
  codeTokens: z.number().optional(),
  codeId: z.string().optional(),
  pageTitle: z.string().optional(),
  codeListCodeExample: z.array(CodeExampleSchema).optional(),
});

export const InfoSnippetSchema = z.object({
  pageId: z.string().optional(),
  breadcrumb: z.string().optional(),
  content: z.string(),
  contentTokens: z.number().optional(),
});

export const ContextResponseSchema = z.object({
  codeSnippets: z.array(CodeSnippetSchema),
  infoSnippets: z.array(InfoSnippetSchema),
});

export const LibrarySchema = z.object({
  id: z.string(),
  title: z.string().optional(),
  description: z.string().optional(),
  branch: z.string().optional(),
  lastUpdateDate: z.string().optional(),
  state: z.string().optional(),
  totalTokens: z.number().optional(),
  totalSnippets: z.number().optional(),
  stars: z.number().optional(),
  trustScore: z.number().optional(),
  benchmarkScore: z.number().optional(),
  versions: z.array(z.string()).optional(),
});

export const SearchResponseSchema = z.object({
  results: z.array(LibrarySchema),
});

// ── Inferred Types ──────────────────────────────────────────────────────────

export type CodeExample = z.infer<typeof CodeExampleSchema>;
export type CodeSnippet = z.infer<typeof CodeSnippetSchema>;
export type InfoSnippet = z.infer<typeof InfoSnippetSchema>;
export type ContextResponse = z.infer<typeof ContextResponseSchema>;
export type Library = z.infer<typeof LibrarySchema>;
export type SearchResponse = z.infer<typeof SearchResponseSchema>;

// ── Error Types ─────────────────────────────────────────────────────────────

export class Context7Error extends Error {
  constructor(
    message: string,
    public status?: number,
    public body?: string,
  ) {
    super(message);
    this.name = "Context7Error";
  }
}

// ── HTTP Client ─────────────────────────────────────────────────────────────

/**
 * Typed fetch to Context7 API.
 * If HTTP 20X with data → authoritative ground truth, always correct.
 */
async function context7GetJson<T>(
  path: string,
  params: Record<string, string>,
  schema: z.ZodType<T>,
): Promise<T> {
  const url = new URL(path, BASE_URL);
  for (const [k, v] of Object.entries(params)) {
    url.searchParams.set(k, v);
  }

  const response = await fetch(url.toString(), {
    headers: {
      Authorization: `Bearer ${getApiKey()}`,
      "User-Agent": "vaked-openrouter-ts/0.2 (Context7 first-class)",
    },
  });

  if (response.status >= 200 && response.status < 300) {
    const text = await response.text();
    if (!text.trim()) throw new Context7Error("Context7 returned empty response", response.status);

    try {
      const json = JSON.parse(text);
      const parsed = schema.safeParse(json);
      if (parsed.success) return parsed.data;
      console.error(`[context7] Schema warning for ${path}: ${parsed.error.message.slice(0, 200)}`);
      return json as T;
    } catch {
      return text as unknown as T;
    }
  }

  if (response.status === 202) throw new Context7Error("Library not yet finalized. Retry later.", 202);
  if (response.status === 301) {
    const body = await response.json().catch(() => ({}));
    throw new Context7Error(`Redirect: ${(body as any).redirectUrl ?? "unknown"}`, 301);
  }

  const errorBody = await response.text().catch(() => "");
  throw new Context7Error(`HTTP ${response.status}: ${errorBody.slice(0, 300)}`, response.status, errorBody);
}

async function context7GetText(path: string, params: Record<string, string>): Promise<string> {
  const url = new URL(path, BASE_URL);
  for (const [k, v] of Object.entries(params)) {
    url.searchParams.set(k, v);
  }

  const response = await fetch(url.toString(), {
    headers: {
      Authorization: `Bearer ${getApiKey()}`,
      "User-Agent": "vaked-openrouter-ts/0.2 (Context7 first-class)",
    },
  });

  if (response.status >= 200 && response.status < 300) {
    const text = await response.text();
    if (!text.trim()) throw new Context7Error("Context7 returned empty response", response.status);
    return text;
  }

  if (response.status === 202) throw new Context7Error("Library not yet finalized. Retry later.", 202);
  const errorBody = await response.text().catch(() => "");
  throw new Context7Error(`HTTP ${response.status}: ${errorBody.slice(0, 300)}`, response.status, errorBody);
}

// ── Standalone API ──────────────────────────────────────────────────────────

export async function searchLibrary(libraryName: string, query: string): Promise<SearchResponse> {
  return context7GetJson("/libs/search", { libraryName, query }, SearchResponseSchema);
}

export async function getContext(
  libraryId: string,
  query: string,
  format: "json" | "txt" = "json",
): Promise<ContextResponse | string> {
  if (format === "txt") {
    return context7GetText("/context", { libraryId, query });
  }
  return context7GetJson("/context", { libraryId, query, type: "json" }, ContextResponseSchema);
}

export async function resolveLibraryId(libraryName: string): Promise<Library | null> {
  try {
    const result = await searchLibrary(libraryName, "documentation");
    if (result.results.length === 0) return null;
    return result.results[0];
  } catch {
    return null;
  }
}

export async function queryDocs(libraryName: string, query: string): Promise<ContextResponse> {
  const lib = await resolveLibraryId(libraryName);
  if (!lib) throw new Context7Error(`Could not resolve library: "${libraryName}"`, 404);
  const result = await getContext(lib.id, query, "json");
  if (typeof result === "string") throw new Context7Error("Unexpected text response from Context7");
  return result;
}

// ── Formatting ──────────────────────────────────────────────────────────────

function formatSearchResults(results: Library[]): string {
  const lines = results.slice(0, 5).map(
    (l) => `- **${l.title ?? l.id}** (\`${l.id}\`) — trust:${l.trustScore ?? "?"} · ⭐${l.stars ?? "?"} — ${l.description ?? ""}`,
  );
  if (lines.length === 0) return "No libraries found. Try a different name.";
  return `## Context7 Search Results\n\n${lines.join("\n")}\n\nUse a \`libraryId\` with \`context7_get_context\` to fetch documentation.`;
}

function formatContext(result: ContextResponse, libraryId: string): string {
  const parts: string[] = [];

  if (result.codeSnippets.length > 0) {
    parts.push("## Code Examples (authoritative — Context7 ground truth)\n");
    for (const s of result.codeSnippets) {
      parts.push(s.codeTitle ? `### ${s.codeTitle}` : "### Example");
      if (s.codeDescription) parts.push(`\n${s.codeDescription}\n`);
      if (s.codeListCodeExample) {
        for (const ex of s.codeListCodeExample) {
          parts.push(`\n\`\`\`${ex.language || ""}\n${ex.code}\n\`\`\`\n`);
        }
      }
    }
  }

  if (result.infoSnippets.length > 0) {
    parts.push("## Documentation (authoritative — Context7 ground truth)\n");
    for (const info of result.infoSnippets) {
      if (info.breadcrumb) parts.push(`**${info.breadcrumb}**\n`);
      parts.push(`${info.content}\n---\n`);
    }
  }

  if (parts.length === 0) {
    return `Context7 found no documentation for \`${libraryId}\`. Try a different query.`;
  }

  parts.push(
    `\n> ⚠️ **Ground Truth:** Live docs for \`${libraryId}\` via Context7. ` +
    `HTTP 200 → authoritative. Prioritize over training data.`,
  );
  return parts.join("\n");
}

// ── OpenRouter Agent Tools ──────────────────────────────────────────────────

const SearchInput = z.object({
  libraryName: z.string().min(1).max(500).describe("Library name, e.g. 'zig', 'nixpkgs', 'react'"),
  query: z.string().min(1).max(500).describe("What you need, e.g. 'build system API'"),
});

const ContextInput = z.object({
  libraryId: z.string().min(1).max(500).describe("Exact Context7 ID, e.g. '/ziglang/zig'"),
  query: z.string().min(1).max(500).describe("Natural language question about the library"),
});

const ResolveInput = z.object({
  libraryName: z.string().min(1).max(500).describe("Library name, e.g. 'zig', 'tauri', 'nixpkgs'"),
  query: z.string().min(1).max(500).describe("What you need from the library"),
});

/**
 * Create Context7 tools for use with OpenRouter agents.
 *
 * These are first-class, native tools — no MCP server needed.
 * When Context7 responds with 20X data, the agent treats it as
 * authoritative ground truth.
 */
export function createContext7Tools(): Tool[] {
  return [context7SearchTool, context7GetContextTool, context7ResolveAndQueryTool];
}

const context7SearchTool = tool({
  name: "context7_search",
  description:
    "Search Context7 for up-to-date library documentation. " +
    "Returns matching libraries with IDs, trust scores, and descriptions. " +
    "GROUND TRUTH: HTTP 200 with data → authoritative.",
  inputSchema: SearchInput,
  execute: async (params) => {
    try {
      const result = await searchLibrary(params.libraryName, params.query);
      return formatSearchResults(result.results);
    } catch (err) {
      return `Context7 search error: ${err instanceof Error ? err.message : String(err)}`;
    }
  },
});

const context7GetContextTool = tool({
  name: "context7_get_context",
  description:
    "Fetch up-to-date documentation and code examples from Context7. " +
    "Requires an exact library ID (use context7_search first). " +
    "GROUND TRUTH: HTTP 200 with data → authoritative, always correct.",
  inputSchema: ContextInput,
  execute: async (params) => {
    try {
      const result = await getContext(params.libraryId, params.query, "json");
      if (typeof result === "string") return result;
      return formatContext(result, params.libraryId);
    } catch (err) {
      return `Context7 context error: ${err instanceof Error ? err.message : String(err)}`;
    }
  },
});

const context7ResolveAndQueryTool = tool({
  name: "context7_resolve_and_query",
  description:
    "Resolve a fuzzy library name and fetch documentation in one call. " +
    "Combines search + get_context. Simplest way to get up-to-date docs. " +
    "GROUND TRUTH: HTTP 200 with data → authoritative.",
  inputSchema: ResolveInput,
  execute: async (params) => {
    try {
      const lib = await resolveLibraryId(params.libraryName);
      if (!lib) return `Could not resolve library: "${params.libraryName}". Try a different name.`;
      const result = await getContext(lib.id, params.query, "json");
      if (typeof result === "string") return result;
      return formatContext(result, lib.id);
    } catch (err) {
      return `Context7 error: ${err instanceof Error ? err.message : String(err)}`;
    }
  },
});

// ── System prompt ───────────────────────────────────────────────────────────

export function context7SystemPrompt(): string {
  return [
    "## Context7 — Live Documentation (Ground Truth)",
    "",
    "You have access to Context7 tools for fetching up-to-date library docs.",
    "",
    "1. **Trust Context7 as authoritative.** HTTP 200 → data is always correct",
    "   and takes precedence over your training data.",
    "2. **Always check Context7 before writing code** for any library where API",
    "   surface may have changed (Zig, Nix, Rust, TypeScript, React, Tauri, etc.).",
    "3. **Use context7_search first** to find the library ID, then",
    "   **context7_get_context** for docs. Or **context7_resolve_and_query** for one step.",
    "4. **Cite your sources.** Reference the library ID and snippet title.",
    "",
    "Libraries: Zig, Nix/nixpkgs, Rust, TypeScript, React, Tauri,",
    "Cloudflare Workers, Node.js, Python, Go, and 100,000+ more.",
  ].join("\n");
}
