#!/usr/bin/env node
"use strict";

/**
 * Vaked E2E — wired into the TUI. One command, all layers.
 * GENESIS_SEAL: 7c242080
 */

import { execSync } from "child_process";
import { createVakedAgent, formatBudget, readBudget } from "@vaked/openrouter-ts";

const ROOT = execSync("git rev-parse --show-toplevel 2>/dev/null || echo .").toString().trim();

function run(cmd: string): string {
  try {
    return execSync(cmd, { cwd: ROOT, timeout: 120000, stdio: "pipe" }).toString();
  } catch (e: any) {
    return `❌ ${e.stderr?.toString().slice(0, 200) || e.message}`;
  }
}

function header(label: string): void {
  console.log(`\n\x1b[1m  ${label}\x1b[0m`);
  console.log("─".repeat(50));
}

async function main() {
  const phase = process.argv[2] || "all";

  if (phase === "zone" || phase === "z") {
    header("ZONE");
    console.log(`  Branch: ${run("git rev-parse --abbrev-ref HEAD").trim()}`);
    console.log(`  Commit: ${run("git log --oneline -1").trim()}`);
    const daemon = run("curl -sf http://localhost:9090/health && echo OK || echo DOWN").trim();
    console.log(`  Daemon: ${daemon}`);
    console.log(`  Budget: ${formatBudget(readBudget())}`);
    return;
  }

  if (phase === "build" || phase === "b") {
    header("BUILD");
    console.log(run("cd daemons/openrouterd && zig build && echo ✅ daemon || echo ❌ daemon"));
    console.log(run("cd tools/openrouter-zig && zig build && echo ✅ zig-sdk || echo ❌ zig-sdk"));
    console.log(run("cd tools/openrouter-ts && npm run build 2>/dev/null && echo ✅ ts-sdk || echo ❌ ts-sdk"));
    return;
  }

  if (phase === "test" || phase === "t") {
    header("TESTS");
    console.log(run("cd daemons/openrouterd && zig build test && echo ✅ daemon-tests || echo ❌ daemon-tests"));
    console.log(run("cd daemons/synapsed && zig build test 2>/dev/null && echo ✅ synapsed || echo ❌ synapsed"));
    return;
  }

  if (phase === "deploy" || phase === "d") {
    header("DEPLOY");
    const msg = process.argv[3] || "e2e: swarm update";
    console.log(run(`git add -A && git commit --no-gpg-sign -m "${msg}"`));
    console.log(run("git push"));
    return;
  }

  // All (default)
  await mainZone();
  await mainBuild();
  await mainTest();
  console.log(`\n\x1b[32m  ✅ E2E COMPLETE · GENESIS_SEAL: 7c242080\x1b[0m\n`);
}

async function mainZone() { await Promise.resolve(main()); }
async function mainBuild() { await Promise.resolve(main()); }
async function mainTest() { await Promise.resolve(main()); }

main().catch((err) => console.error(`\x1b[31mfatal:\x1b[0m ${err.message}`));
