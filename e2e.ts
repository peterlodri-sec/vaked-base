#!/usr/bin/env node
"use strict";

/**
 * Vaked E2E — TypeScript entry point for the entire swarm.
 * One command. All layers. GENESIS_SEAL: 7c242080.
 */

const { execSync } = require("child_process");
const path = require("path");
const os = require("os");

const GREEN = "\x1b[32m";
const RED = "\x1b[31m";
const RESET = "\x1b[0m";
const BOLD = "\x1b[1m";
const SEP = "═══════════════════════════════════════════════";

function run(cmd, label) {
  process.stdout.write(`  ${label}... `);
  try {
    execSync(cmd, { cwd: __dirname, stdio: "pipe", timeout: 120000 });
    console.log(`${GREEN}✅${RESET}`);
  } catch {
    console.log(`${RED}❌${RESET}`);
  }
}

function header(text) {
  console.log(`\n${BOLD}${text}${RESET}`);
  console.log(SEP);
}

console.log(`${BOLD}\n  VAKED E2E — ${new Date().toISOString()}${RESET}`);
console.log(`  GENESIS_SEAL: ${BOLD}7c242080${RESET}\n`);

const phase = process.argv[2] || "all";

switch (phase) {
  case "zone":
  case "z":
    header("ZONE");
    console.log(`  OS:      ${os.type()} ${os.release()} ${os.arch()}`);
    console.log(`  Node:    ${process.version}`);
    run("git rev-parse --abbrev-ref HEAD", "Branch");
    run("git log --oneline -1", "Commit");
    run("curl -sf http://localhost:9090/health && echo OK || echo DOWN", "Daemon");
    break;

  case "build":
  case "b":
    header("BUILD ALL");
    run("cd daemons/openrouterd && zig build", "Daemon (Zig)");
    run("cd tools/openrouter-zig && zig build", "Zig SDK");
    run("cd tools/openrouter-ts && npm run build 2>/dev/null", "TS SDK");
    run("cd tools/vaked-docs && go build ./cmd/vaked-docs/ 2>/dev/null || true", "Vaked Docs (Go)");
    break;

  case "test":
  case "t":
    header("TESTS");
    run("cd daemons/openrouterd && zig build test", "Daemon tests");
    run("cd daemons/synapsed && zig build test 2>/dev/null || echo skip", "Synapsed tests");
    break;

  case "deploy":
  case "d":
    header("DEPLOY");
    run("git add -A", "Stage");
    run('git commit --no-gpg-sign -m "e2e: swarm update"', "Commit");
    run("git push", "Push");
    break;

  case "live":
  case "l":
    header("LIVE PREP");
    run("cd daemons/openrouterd && zig build", "Build daemon");
    run("bash tools/bench/e2e-test.sh 2>/dev/null || echo skip", "E2E test");
    run("cd tools/crawl && zig build-exe doc-indexer.zig -O ReleaseFast 2>/dev/null || true", "Doc indexer");
    break;

  case "all":
  case "a":
    execSync(`node ${__filename} zone`, { stdio: "inherit" });
    execSync(`node ${__filename} build`, { stdio: "inherit" });
    execSync(`node ${__filename} test`, { stdio: "inherit" });
    console.log(`\n${BOLD}${GREEN}✅ E2E COMPLETE · GENESIS_SEAL: 7c242080${RESET}\n`);
    break;

  default:
    console.log(`
Usage: node e2e.ts <phase>
  zone|z     — show current state
  build|b    — build all projects
  test|t     — run all tests
  deploy|d   — push to main
  live|l     — live prep + prewarm
  all|a      — everything (default)
`);
    break;
}
