"use strict";
import { z } from "zod";
import { tool } from "@openrouter/agent";
import type { Tool } from "@openrouter/agent";
import { readFileSync, existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
function loadLocalCache(): any {
  try {
    const __dirname = dirname(fileURLToPath(import.meta.url));
    const cachePath = join(__dirname, "ctx7cache.json");
    if (existsSync(cachePath)) {
      return JSON.parse(readFileSync(cachePath, "utf-8"));
    }
  } catch {}
  return null;
}
const BASE_URL = "https://context7.com/api/v2";
function getApiKey(): string {
  const key = process.env["CONTEXT7_API_KEY"];
  if (!key) throw new Error("CONTEXT7_API_KEY not set. Get one at https://context7.com/dashboard");
  return key;
}
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
export type CodeExample = z.infer<typeof CodeExampleSchema>;
export type CodeSnippet = z.infer<typeof CodeSnippetSchema>;
export type InfoSnippet = z.infer<typeof InfoSnippetSchema>;
export type ContextResponse = z.infer<typeof ContextResponseSchema>;
export type Library = z.infer<typeof LibrarySchema>;
export type SearchResponse = z.infer<typeof SearchResponseSchema>;
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
    return result.results[0] ?? null;
  } catch {
    return null;
  }
}
export async function queryDocs(libraryName: string, query: string): Promise<ContextResponse> {
  const ck = libraryName + "::" + query;
  const localCache = loadLocalCache();
  if (localCache && Array.isArray(localCache)) {
    const entries = localCache as Array<any>;
    const match = entries.find((e: any) => e.library === libraryName && e.query === query);
    if (match) {
      console.error("[ctx7:local] " + libraryName + "/" + query.slice(0, 40));
      return { codeSnippets: [], infoSnippets: match.snippets.map((s: any) => ({ content: s.code ?? s.content ?? "" })) } as ContextResponse;
    }
  }
  const cached = ctx7cacheGet(ck);
  if (cached) { console.error("[ctx7:cache] " + libraryName); return cached; }
  if (_ctx7limited) throw new Context7Error("Rate limited (500/mo free tier). Cached exhausted.", 429);
  ctx7rateCheck();
  const lib = await resolveLibraryId(libraryName);
  if (!lib) throw new Context7Error("Could not resolve: " + libraryName, 404);
  const result = await getContext(lib.id, query, "json");
  if (typeof result === "string") throw new Context7Error("Unexpected text response");
  ctx7cacheSet(ck, result);
  return result;
}
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
const API_PATTERNS: Array<{ pattern: RegExp; library: string }> = [
  { pattern: /\b(std\.Build|zig build|zig\s+0\.\d+|@import\("std"\))/i, library: "zig" },
  { pattern: /\b(nixpkgs|nixos|nix develop|nix build|nix flake|buildRustPackage|mkDerivation)/i, library: "nixpkgs" },
  { pattern: /\b(tauri|@tauri-apps|tauri\.conf|tauri::)/i, library: "tauri" },
  { pattern: /\b(useState|useEffect|useCallback|JSX|React\.|react)/i, library: "react" },
  { pattern: /\b(cloudflare|wrangler|workers|DurableObject|DO\b|R2\b|KV store)/i, library: "cloudflare" },
  { pattern: /\b(node:fs|node:path|node:http|node\.js|Node\.js)/i, library: "nodejs" },
  { pattern: /\b(serde|tokio|async fn|cargo build|cargo\.toml)/i, library: "rust" },
  { pattern: /\b(eBPF|bpf\b|BPF_PROG|bpf_trace|XDP)/i, library: "ebpf" },
  { pattern: /(Monaco|monaco-editor|@monaco-editor)/i, library: "monaco" },
  { pattern: /(python|pip install|venv|pytest|asyncio|FastAPI|Django)/i, library: "python" },
  { pattern: /(golang|go mod|go build|goroutine|go\s+1\.\d+)/i, library: "go" },
  { pattern: /(docker|dockerfile|docker-compose|container|podman)/i, library: "docker" },
  { pattern: /(kubernetes|k8s|kubectl|pod|deployment\.yaml)/i, library: "kubernetes" },
  { pattern: /(typescript|tsconfig|\.ts|\.tsx|TypeScript)/i, library: "typescript" },
  { pattern: /(git|github|pull request|merge conflict|rebase)/i, library: "git" },
  { pattern: /(sql|postgres|mysql|sqlite|prisma|drizzle)/i, library: "sql" },
  { pattern: /(vite|esbuild|webpack|rollup|bundler)/i, library: "vite" },
  { pattern: /(llm|langchain|langfuse|prompt engineering|token)/i, library: "langchain" },
];
export interface PreScanResult {
  detected: boolean;
  libraries: string[];
  injected: string | null;
  tokenEstimate: number;
}
export async function context7PreScan(prompt: string): Promise<PreScanResult> {
  if (!prompt || prompt.trim().length === 0) {
    return { detected: false, libraries: [], injected: null, tokenEstimate: 0 };
  }
  const detectedLibs: string[] = [];
  for (const { pattern, library } of API_PATTERNS) {
    if (pattern.test(prompt) && !detectedLibs.includes(library)) {
      detectedLibs.push(library);
    }
  }
  if (detectedLibs.length === 0) {
    return { detected: false, libraries: [], injected: null, tokenEstimate: 0 };
  }
  const libs = detectedLibs.slice(0, 3);
  const injectParts: string[] = [];
  for (const lib of libs) {
    try {
      if (_ctx7limited) { console.error("[ctx7:prescan] skipped (rate limited): " + lib); continue; }
      const docs = await Promise.race([queryDocs(lib, prompt.slice(0, 300)), new Promise<never>((_, reject) => setTimeout(() => reject(new Error("timeout")), 5000))]);
      const formatted = formatContextForInjection(docs, lib);
      injectParts.push(formatted);
    } catch (err) {
      console.error("[ctx7:prescan] " + lib + ": " + (err instanceof Error ? err.message : String(err)));
    }
  }
  if (injectParts.length === 0) {
    return { detected: true, libraries: libs, injected: null, tokenEstimate: 0 };
  }
  const combined = injectParts.join("\n");
  const tokenEstimate = Math.ceil(combined.length / 4);
  const MAX_TOKENS = 2048;
  const MAX_CHARS = MAX_TOKENS * 4;
  const truncated = combined.length > MAX_CHARS
    ? combined.slice(0, MAX_CHARS) + "\n... [truncated at 2K tokens]"
    : combined;
  return {
    detected: true,
    libraries: libs,
    injected: truncated,
    tokenEstimate: Math.min(tokenEstimate, MAX_TOKENS),
  };
}
function formatContextForInjection(result: ContextResponse, libName: string): string {
  const parts: string[] = ["## Context7: " + libName + " (live docs - authoritative)\n"];
  for (const s of result.codeSnippets.slice(0, 3)) {
    if (s.codeListCodeExample) {
      for (const ex of s.codeListCodeExample.slice(0, 2)) {
        parts.push(ex.code + "\n");
      }
    }
  }
  for (const info of result.infoSnippets.slice(0, 2)) {
    const t = info.content.length > 500 ? info.content.slice(0, 500) + "..." : info.content;
    parts.push(t + "\n");
  }
  return parts.join("\n");
}
export function logPreScanInjection(result: PreScanResult): void {
  if (!result.detected || !result.injected) return;
  const libList = result.libraries.join(", ");
  const kbEstimate = (result.tokenEstimate / 250).toFixed(1);
  console.error(
    "[ctx7:prescan] detected: " + libList +
    " -> injected " + result.tokenEstimate + " tokens (~" + kbEstimate + "K)",
  );
}
let _ctx7reqs = 0;
let _ctx7limited = false;
const _ctx7cache = new Map<string, { data: ContextResponse; ts: number }>();
const CACHE_MAX = 100;
const CACHE_TTL = 3600_000;
const RATE_WARN = 450;
function ctx7cacheGet(key: string): ContextResponse | null {
  const e = _ctx7cache.get(key);
  if (!e) return null;
  if (Date.now() - e.ts > CACHE_TTL) { _ctx7cache.delete(key); return null; }
  return e.data;
}
function ctx7cacheSet(key: string, data: ContextResponse): void {
  if (_ctx7cache.size >= CACHE_MAX) { const first = _ctx7cache.keys().next().value; if (first !== undefined) _ctx7cache.delete(first); }
  _ctx7cache.set(key, { data, ts: Date.now() });
}
function ctx7rateCheck(): void {
  _ctx7reqs++;
  if (_ctx7reqs >= 500 && !_ctx7limited) { _ctx7limited = true; console.error("[ctx7:rate] Free tier exhausted (500/month). Cached only."); }
  else if (_ctx7reqs > RATE_WARN && !_ctx7limited) { console.error("[ctx7:rate] " + _ctx7reqs + " reqs — approaching free tier limit (500/month)."); }
}