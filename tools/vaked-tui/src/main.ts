#!/usr/bin/env node
"use strict";

/**
 * vaked — cross-platform, battle-tested TUI agent.
 *
 * Zero GUI deps. Works over SSH, in tmux, on any terminal.
 * Uses @vaked/openrouter-ts under the hood.
 *
 * Modes:
 *   vaked                  — interactive TUI
 *   vaked --ci             — stdin→stdout, no interaction
 *   vaked --oneshot "..."  — single prompt, print + exit
 *
 * GENESIS_SEAL: 7c242080
 */

import * as readline from "node:readline";
import { readFileSync, existsSync } from "node:fs";
import { createVakedAgent, MODELS, formatBudget, readBudget, routeModel } from "@vaked/openrouter-ts";
import type { VakedAgent } from "@vaked/openrouter-ts";

// ── Arg parsing ─────────────────────────────────────────────────────────────

interface Args {
  ci: boolean;
  oneshot: string | null;
  model: string;
  file: string | null;
  prompt: string | null;
  stream: boolean;
  json: boolean;
  help: boolean;
  list: boolean;
  status: boolean;
}

function parseArgs(argv: string[]): Args {
  const args: Args = {
    ci: false,
    oneshot: null,
    model: "deepseek",
    file: null,
    prompt: null,
    stream: false,
    json: false,
    help: false,
    list: false,
    status: false,
  };

  const positional: string[] = [];
  let i = 2;
  while (i < argv.length) {
    const a = argv[i];
    if (a === undefined) break;
    switch (a) {
      case "--ci":           args.ci = true; break;
      case "--oneshot":      i++; const v = argv[i]; if (v) args.oneshot = v; break;
      case "--model": case "-m":  i++; const m = argv[i]; if (m) args.model = m; break;
      case "--file": case "-f":   i++; const f = argv[i]; if (f) args.file = f; break;
      case "--prompt": case "-p": i++; const p = argv[i]; if (p) args.prompt = p; break;
      case "--stream": case "-s":  args.stream = true; break;
      case "--json":             args.json = true; break;
      case "--help": case "-h":  args.help = true; break;
      case "--list": case "-l":  args.list = true; break;
      case "--status":           args.status = true; break;
      default:
        if (!a.startsWith("-")) positional.push(a);
        break;
    }
    i++;
  }

  if (!args.oneshot && positional.length > 0) {
    args.oneshot = positional.join(" ");
  }

  return args;
}

// ── Help ────────────────────────────────────────────────────────────────────

function showHelp(): void {
  console.log(`
vaked — cross-platform TUI agent powered by OpenRouter

USAGE
  vaked                    Interactive TUI
  vaked --ci               CI mode (stdin→stdout)
  vaked --oneshot "..."    Single prompt, print + exit

OPTIONS
  --model, -m <alias>      Model: deepseek, claude, gemini, qwen, llama, haiku, deepseek-flash
  --file, -f <path>        Include file as context
  --prompt, -p <text>      System prompt / instructions
  --stream, -s             Stream output
  --json                   JSON output (CI mode)
  --list, -l               List available models
  --status                 Show budget status
  --help, -h               This help

CI MODE
  cat file.txt | vaked --ci --model claude
  echo "review this" | vaked --ci --file main.zig --prompt "Code review"
  vaked --ci --json < input.json  (reads prompt from stdin, outputs JSON)

TUI SLASH COMMANDS
  /help          Show commands
  /model <name>  Switch model (deepseek, claude, gemini, etc.)
  /file <path>   Add file as context
  /context7      Toggle Context7 live docs
  /budget        Show budget
  /clear         Clear session
  /history       Show message history
  /stream        Toggle streaming
  /quit, /exit   Exit

EXAMPLES
  vaked
  vaked --oneshot "How do I use std.Build in Zig 0.16?"
  vaked --ci --model claude < prompt.txt
  cat src/main.zig | vaked --ci --stream --prompt "Review for bugs"
`);
}

// ── List models ─────────────────────────────────────────────────────────────

function listModels(): void {
  console.log("Available models:");
  for (const [alias, entry] of Object.entries(MODELS) as [string, typeof MODELS[string]][]) {
    console.log(
      `  ${alias.padEnd(16)} ${entry.id.padEnd(42)} $${entry.promptCost.toFixed(2)}/$${entry.completionCost.toFixed(2)} per 1M tok`
    );
  }
}

// ── CI mode ─────────────────────────────────────────────────────────────────

async function ciMode(args: Args, agent: VakedAgent): Promise<void> {
  // Read stdin
  const chunks: Buffer[] = [];
  for await (const chunk of process.stdin) {
    chunks.push(typeof chunk === "string" ? Buffer.from(chunk, "utf-8") : chunk);
  }
  let input = Buffer.concat(chunks).toString("utf-8").trim();

  // Load file context
  if (args.file) {
    if (existsSync(args.file)) {
      const fileContent = readFileSync(args.file, "utf-8");
      input = `File: ${args.file}\n\`\`\`\n${fileContent}\n\`\`\`\n\n${input || args.prompt || ""}`;
    }
  }

  if (!input && !args.prompt) {
    if (!args.json) {
      console.error("Error: no input on stdin and no --prompt");
      process.exit(1);
    }
  }

  const prompt = input || args.prompt || "";
  if (!prompt.trim()) {
    console.error("Error: empty prompt");
    process.exit(1);
  }

  if (args.stream) {
    for await (const chunk of agent.streamChat(prompt, args.model)) {
      process.stdout.write(chunk);
    }
    process.stdout.write("\n");
  } else {
    const text = await agent.ask(prompt, args.model);
    if (args.json) {
      console.log(JSON.stringify({ output: text, model: MODELS[args.model]?.id ?? args.model }));
    } else {
      console.log(text);
    }
  }
}

// ── Interactive TUI ─────────────────────────────────────────────────────────

interface TuiState {
  model: string;
  stream: boolean;
  context7: boolean;
  files: string[];
  history: string[];
  running: boolean;
}

async function tuiMode(args: Args, agent: VakedAgent): Promise<void> {
  const state: TuiState = {
    model: args.model,
    stream: true,
    context7: true,
    files: args.file ? [args.file] : [],
    history: [],
    running: true,
  };

  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: true,
    history: state.history,
    prompt: "",
  });

  // Load initial file context
  for (const f of state.files) {
    if (existsSync(f)) {
      console.log(`[file] loaded ${f} (${readFileSync(f, "utf-8").length} bytes)`);
    }
  }

  function header(): string {
    const model = state.model === "auto" ? null : MODELS[state.model];
    const modelName = state.model === "auto" ? "auto-routing" : (model?.id ?? state.model);
    const budget = formatBudget(readBudget());
    const ctx7 = state.context7 ? "ctx7" : "";
    const str = state.stream ? "stream" : "";
    const flags = [ctx7, str].filter(Boolean).join("·");
    const flagStr = flags ? ` · ${flags}` : "";
    return `\x1b[1;36m${modelName}\x1b[0m · \x1b[33m${budget}\x1b[0m${flagStr}`;
  }

  function printHeader(): void {
    console.log(`\n${header()}`);
    console.log("");
  }

  printHeader();

  // Welcome
  console.log('Type a prompt. /help for commands. /quit to exit.\n');

  rl.on("line", async (line: string) => {
    const trimmed = line.trim();
    if (!trimmed) return;

    // Slash commands
    if (trimmed.startsWith("/")) {
      const parts = trimmed.split(/\s+/);
      const cmd = parts[0];
      const arg = parts.slice(1).join(" ");

      switch (cmd) {
        case "/help":
          console.log("\n/help · /model <name|auto> · /file <path> · /context7 · /budget · /clear · /history · /stream · /quit\n");
          break;
        case "/model":
          if (arg === "auto") {
            state.model = "auto";
            console.log("[model] auto — models choose their own based on task");
            console.log(`  code/review/debug → claude · explain/summarize → deepseek · creative → gemini`);
          } else if (arg && MODELS[arg]) {
            state.model = arg;
            console.log(`[model] switched to ${MODELS[arg]?.label ?? arg} (${MODELS[arg]?.id})`);
          } else {
            console.log("[model] available: auto, " + Object.keys(MODELS).join(", "));
          }
          break;
        case "/file":
          if (arg && existsSync(arg)) {
            state.files.push(arg);
            const content = readFileSync(arg, "utf-8");
            console.log(`[file] loaded ${arg} (${content.length} bytes)`);
          } else if (arg) {
            console.log(`[file] not found: ${arg}`);
          } else {
            console.log("[file] loaded: " + (state.files.length > 0 ? state.files.join(", ") : "(none)"));
          }
          break;
        case "/context7":
          state.context7 = !state.context7;
          console.log(`[context7] ${state.context7 ? "ON" : "OFF"}`);
          break;
        case "/budget":
          console.log(`[budget] ${formatBudget(readBudget())}`);
          break;
        case "/clear":
          state.files = [];
          console.log("[clear] session reset");
          break;
        case "/history":
          console.log(state.history.length > 0
            ? state.history.map((h, i) => `  ${i + 1}. ${h.slice(0, 100)}`).join("\n")
            : "  (empty)");
          break;
        case "/stream":
          state.stream = !state.stream;
          console.log(`[stream] ${state.stream ? "ON" : "OFF"}`);
          break;
        case "/quit":
        case "/exit":
          state.running = false;
          rl.close();
          return;
        default:
          console.log(`[?] unknown: ${cmd}. /help for commands.`);
          break;
      }
      return;
    }

    // Build prompt with file context
    let prompt = trimmed;
    if (state.files.length > 0) {
      const fileContexts = state.files
        .map((f) => {
          if (!existsSync(f)) return null;
          const content = readFileSync(f, "utf-8");
          return `File: ${f}\n\`\`\`\n${content}\n\`\`\``;
        })
        .filter(Boolean)
        .join("\n\n");
      if (fileContexts) {
        prompt = `${fileContexts}\n\n${trimmed}`;
      }
    }

    // Add system prompt override if --prompt was provided
    // (handled by the agent's instructions)

    state.history.push(trimmed);
    const startTime = Date.now();

    process.stdout.write("\n");

    try {
      if (state.stream) {
        let firstChunk = true;
        const routedModel = state.model === "auto" ? routeModel(trimmed) : state.model;
          if (state.context7) process.stdout.write("\x1b[90m[ctx7] scanning...\x1b[0m\r");
          for await (const chunk of agent.streamChat(prompt, routedModel)) {
          if (firstChunk) {
            process.stdout.write("\x1b[K\x1b[90m──\x1b[0m\n");
            firstChunk = false;
          }
          process.stdout.write(chunk);
        }
        const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
        const routedLabel = state.model === "auto" ? "auto→" + routedModel.split("/").pop() : "";
          process.stdout.write(`\n\x1b[90m── ${elapsed}s ${routedLabel ? "· " + routedLabel + " · " : "· "}${formatBudget(readBudget())}\x1b[0m\n\n`);
      } else {
        process.stdout.write("\x1b[90m── thinking...\x1b[0m\r");
        const routedModel = state.model === "auto" ? routeModel(trimmed) : state.model;
        const response = await agent.ask(prompt, routedModel);
        const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
        process.stdout.write("\x1b[K"); // clear "thinking..."
        console.log(response);
        console.log(`\x1b[90m── ${elapsed}s · ${formatBudget(readBudget())}\x1b[0m\n`);
      }
    } catch (err) {
      console.error(`\x1b[31m[error]\x1b[0m ${err instanceof Error ? err.message : String(err)}\n`);
    }
  });

  rl.on("close", () => {
    console.log("\nbye.\n");
  });

  // Wait for close
  await new Promise<void>((resolve) => {
    rl.on("close", resolve);
  });
}

// ── Main ────────────────────────────────────────────────────────────────────

async function main(): Promise<void> {
  const args = parseArgs(process.argv);

  if (args.help) { showHelp(); return; }
  if (args.list) { listModels(); return; }
  if (args.status) { console.log(formatBudget(readBudget())); return; }

  // Create agent (guards on OPENROUTER_API_KEY)
  let agent: VakedAgent;
  try {
    agent = createVakedAgent({ context7: true });
  } catch (err) {
    console.error(`\x1b[31mfatal:\x1b[0m ${err instanceof Error ? err.message : String(err)}`);
    process.exit(1);
  }

  // Override default model from --model
  if (args.model !== "deepseek" && MODELS[args.model]) {
    // Model will be passed per-call, not via createVakedAgent option
  }

  if (args.ci) {
    await ciMode(args, agent);
  } else if (args.oneshot) {
    // Oneshot: same as CI but no stdin read
    let prompt = args.oneshot;
    if (args.file && existsSync(args.file)) {
      const fileContent = readFileSync(args.file, "utf-8");
      prompt = `File: ${args.file}\n\`\`\`\n${fileContent}\n\`\`\`\n\n${prompt}`;
    }
    if (args.stream) {
      for await (const chunk of agent.streamChat(prompt, args.model)) {
        process.stdout.write(chunk);
      }
      process.stdout.write("\n");
    } else {
      const response = await agent.ask(prompt, args.model);
      console.log(response);
    }
  } else {
    await tuiMode(args, agent);
  }
}

main().catch((err) => {
  console.error(`\x1b[31mfatal:\x1b[0m ${err instanceof Error ? err.message : String(err)}`);
  process.exit(1);
});
