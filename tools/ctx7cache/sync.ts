#!/usr/bin/env node
"use strict";

/**
 * ctx7cache — pre-fetch Context7 docs at build time.
 * Downloads documentation for known libraries, stores locally.
 * Zero runtime API calls. Works offline. No rate limits.
 *
 * Usage:
 *   npx tsx tools/ctx7cache/sync.ts
 *   npx tsx tools/ctx7cache/sync.ts --library zig,nixpkgs,tauri
 *
 * Output: tools/openrouter-ts/src/ctx7cache.json (~2-5MB)
 *
 * GENESIS_SEAL: 7c242080
 */

import { writeFileSync, readFileSync, existsSync } from "fs";

const API = "https://context7.com/api/v2";
const CACHE_FILE = new URL("../openrouter-ts/src/ctx7cache.json", import.meta.url).pathname;
const API_KEY = process.env["CONTEXT7_API_KEY"];

const LIBRARIES = [
  // Vaked swarm core deps
  { name: "zig", queries: ["std.Build API", "std.http.Client", "std.mem.Allocator", "linux syscalls", "ArrayListUnmanaged"] },
  { name: "nixpkgs", queries: ["buildRustPackage", "mkDerivation", "stdenv", "fetchFromGitHub", "writeShellScriptBin"] },
  { name: "tauri", queries: ["plugin system", "command API", "window API", "file system access"] },
  { name: "rust", queries: ["serde derive", "tokio spawn", "async fn", "cargo build release", "Result type"] },
  { name: "typescript", queries: ["tsconfig strict", "ESM imports", "NodeNext module", "type inference"] },
  { name: "react", queries: ["useState", "useEffect", "useCallback", "JSX syntax"] },
  { name: "cloudflare", queries: ["workers fetch", "DurableObject", "R2 bucket", "KV namespace"] },
  { name: "nodejs", queries: ["http server", "fs readFile", "child_process spawn", "stream pipeline"] },
  { name: "python", queries: ["asyncio gather", "FastAPI router", "pydantic model", "subprocess run"] },
  { name: "go", queries: ["goroutine", "channel", "context WithTimeout", "net/http server"] },
  { name: "docker", queries: ["Dockerfile FROM", "docker build", "docker compose", "multi-stage build"] },
  { name: "kubernetes", queries: ["pod spec", "deployment yaml", "service type", "configmap"] },
  { name: "sql", queries: ["SELECT join", "CREATE TABLE", "index create", "migration"] },
  { name: "vite", queries: ["vite config", "plugin react", "build optimization", "dev server"] },
  { name: "ebpf", queries: ["BPF program type", "XDP hook", "tracepoint", "map operations"] },
  { name: "monaco", queries: ["editor create", "language registration", "theme customization"] },
  { name: "git", queries: ["merge conflict", "rebase interactive", "cherry-pick", "bisect"] },
  { name: "langchain", queries: ["chain compose", "tool definition", "agent executor", "memory"] },
  { name: "prisma", queries: ["schema model", "migrate dev", "client query", "relation"] },
];

interface DocEntry {
  library: string;
  query: string;
  snippets: Array<{ code?: string; content?: string }>;
  fetchedAt: string;
}

async function fetchDocs(libraryName: string, query: string): Promise<DocEntry | null> {
  if (!API_KEY) {
    console.error("CONTEXT7_API_KEY not set — skipping API calls");
    return null;
  }

  const url = `${API}/context?libraryId=/websites/${libraryName}_docs&query=${encodeURIComponent(query)}&type=json`;
  
  try {
    const res = await fetch(url, {
      headers: { Authorization: `Bearer ${API_KEY}`, "User-Agent": "vaked-ctx7cache/0.1" },
    });

    if (res.status === 429) {
      console.error(`  ⚠️  rate limited — stopping (${libraryName}/${query})`);
      return null;
    }

    if (!res.ok) {
      // Try resolving library ID first
      const searchUrl = `${API}/libs/search?libraryName=${encodeURIComponent(libraryName)}&query=${encodeURIComponent(query)}`;
      const searchRes = await fetch(searchUrl, {
        headers: { Authorization: `Bearer ${API_KEY}` },
      });
      
      if (!searchRes.ok) {
        console.error(`  ❌ ${libraryName}/${query}: HTTP ${res.status}`);
        return null;
      }

      const searchData = await searchRes.json();
      if (!searchData.results?.length) {
        console.error(`  ❌ ${libraryName}: not found`);
        return null;
      }

      const libId = searchData.results[0].id;
      const ctxUrl = `${API}/context?libraryId=${encodeURIComponent(libId)}&query=${encodeURIComponent(query)}&type=json`;
      const ctxRes = await fetch(ctxUrl, {
        headers: { Authorization: `Bearer ${API_KEY}` },
      });

      if (!ctxRes.ok) {
        console.error(`  ❌ ${libraryName}/${query}: HTTP ${ctxRes.status} (after resolve)`);
        return null;
      }

      const ctxData = await ctxRes.json();
      return {
        library: libraryName,
        query,
        snippets: extractSnippets(ctxData),
        fetchedAt: new Date().toISOString(),
      };
    }

    const data = await res.json();
    return {
      library: libraryName,
      query,
      snippets: extractSnippets(data),
      fetchedAt: new Date().toISOString(),
    };
  } catch (err) {
    console.error(`  ❌ ${libraryName}/${query}: ${err instanceof Error ? err.message : String(err)}`);
    return null;
  }
}

function extractSnippets(data: any): Array<{ code?: string; content?: string }> {
  const snippets: Array<{ code?: string; content?: string }> = [];
  
  for (const cs of data.codeSnippets ?? []) {
    if (cs.codeListCodeExample) {
      for (const ex of cs.codeListCodeExample) {
        snippets.push({ code: ex.code, content: cs.codeDescription });
      }
    }
  }
  
  for (const info of data.infoSnippets ?? []) {
    snippets.push({ content: info.content?.slice(0, 1000) });
  }

  return snippets.slice(0, 10); // cap per query
}

async function main() {
  const args = process.argv.slice(2);
  const filter = args.find(a => a.startsWith("--library="))?.split("=")[1]?.split(",");

  const toFetch = filter
    ? LIBRARIES.filter(l => filter.includes(l.name))
    : LIBRARIES;

  console.log(`ctx7cache: ${toFetch.length} libraries, ${toFetch.reduce((s, l) => s + l.queries.length, 0)} queries\n`);

  // Load existing cache
  let cache: DocEntry[] = [];
  if (existsSync(CACHE_FILE)) {
    cache = JSON.parse(readFileSync(CACHE_FILE, "utf-8"));
    console.log(`Loaded ${cache.length} cached entries\n`);
  }

  let added = 0;
  let skipped = 0;
  let errors = 0;

  for (const lib of toFetch) {
    for (const query of lib.queries) {
      const key = `${lib.name}::${query}`;
      const exists = cache.some(e => e.library === lib.name && e.query === query);
      if (exists) { skipped++; continue; }

      process.stdout.write(`  ${lib.name}/${query.slice(0, 40)}... `);
      const entry = await fetchDocs(lib.name, query);
      
      if (entry) {
        cache.push(entry);
        added++;
        console.log("✅");
      } else {
        errors++;
        console.log("❌");
      }

      // Rate limit ourselves (1 req/sec)
      await new Promise(r => setTimeout(r, 1000));
    }
  }

  // Write cache
  writeFileSync(CACHE_FILE, JSON.stringify(cache, null, 2));
  
  const sizeMB = (Buffer.byteLength(JSON.stringify(cache)) / 1024 / 1024).toFixed(1);
  console.log(`\nDone: +${added} new, ${skipped} cached, ${errors} errors`);
  console.log(`Cache: ${CACHE_FILE} (${sizeMB}MB, ${cache.length} entries)`);
  console.log("GENESIS_SEAL: 7c242080");
}

main().catch(err => { console.error(err); process.exit(1); });
