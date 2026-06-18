#!/usr/bin/env npx tsx
"use strict";

/**
 * RAG Ingestion — register core tech stack with Vaked Docs.
 * Reads from the swarm's own knowledge base.
 * GENESIS_SEAL: 7c242080
 */

const DOCS_URL = process.env["VAKED_DOCS_URL"] ?? "http://localhost:9845";

const STACK = [
  { id: "ziglang/zig", url: "https://github.com/ziglang/zig", desc: "Zig 0.16 — systems programming language" },
  { id: "nixos/nixpkgs", url: "https://github.com/NixOS/nixpkgs", desc: "Nix packages collection" },
  { id: "microsoft/TypeScript", url: "https://github.com/microsoft/TypeScript", desc: "TypeScript language" },
  { id: "rust-lang/rust", url: "https://github.com/rust-lang/rust", desc: "Rust language" },
  { id: "facebook/react", url: "https://github.com/facebook/react", desc: "React UI library" },
  { id: "tauri-apps/tauri", url: "https://github.com/tauri-apps/tauri", desc: "Tauri app framework" },
  { id: "oven-sh/bun", url: "https://github.com/oven-sh/bun", desc: "Bun runtime" },
  { id: "denoland/deno", url: "https://github.com/denoland/deno", desc: "Deno runtime" },
  { id: "cloudflare/workers-sdk", url: "https://github.com/cloudflare/workers-sdk", desc: "Cloudflare Workers" },
  { id: "torvalds/linux", url: "https://github.com/torvalds/linux", desc: "Linux kernel" },
  { id: "openbao/openbao", url: "https://github.com/openbao/openbao", desc: "OpenBao/Vault" },
  { id: "quickjs-ng/quickjs", url: "https://github.com/quickjs-ng/quickjs", desc: "QuickJS engine" },
  { id: "nullclaw/nullclaw", url: "https://github.com/nullclaw/nullclaw", desc: "NullClaw agent runtime" },
  { id: "oxc-project/oxc", url: "https://github.com/oxc-project/oxc", desc: "OXC compiler" },
  { id: "cube-js/cube", url: "https://github.com/cube-js/cube", desc: "Cube semantic layer" },
  { id: "microsoft/mimalloc", url: "https://github.com/microsoft/mimalloc", desc: "mimalloc allocator" },
  { id: "axboe/liburing", url: "https://github.com/axboe/liburing", desc: "io_uring library" },
  { id: "openrouter/team", url: "https://openrouter.ai", desc: "OpenRouter API" },
];

async function main() {
  console.log(`Vaked RAG Ingestion — ${STACK.length} packages → ${DOCS_URL}\n`);
  let ok = 0, fail = 0;

  for (const pkg of STACK) {
    try {
      const res = await fetch(`${DOCS_URL}/register`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: pkg.id, url: pkg.url, version: "latest" }),
      });
      if (res.ok) { ok++; console.log(`  ✅ ${pkg.id}`); }
      else { fail++; console.log(`  ⚠️ ${pkg.id}: HTTP ${res.status}`); }
    } catch (err) {
      fail++; console.log(`  ❌ ${pkg.id}: ${err instanceof Error ? err.message : String(err)}`);
    }
  }

  console.log(`\nDone: ${ok} registered, ${fail} failed`);
  console.log("GENESIS_SEAL: 7c242080");
}

main();
