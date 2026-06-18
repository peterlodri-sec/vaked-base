#!/usr/bin/env node
"use strict";
/**
import * as readline from "node:readline";
import { readFileSync, existsSync, statSync } from "node:fs";
import { createVakedAgent, MODELS, formatBudget, readBudget, routeModel } from "@vaked/openrouter-ts";
import type { VakedAgent } from "@vaked/openrouter-ts";
interface ChatFile {
  path: string;
  size: number;
  addedAt: number;
}
interface TuiState {
  model: string;
  stream: boolean;
  context7: boolean;
  files: ChatFile[];
  history: string[];
  running: boolean;
  totalTokens: number;
  totalCost: number;
  messageCount: number;
}
function tokenEstimate(text: string): number {
  return Math.ceil(text.length / 4);
}
function header(state: TuiState): string {
  const model = state.model === "auto" ? "auto-routing" : (MODELS[state.model]?.id ?? state.model);
  const budget = readBudget();
  const tokens = state.totalTokens >= 1000
    ? `${(state.totalTokens / 1000).toFixed(1)}k`
    : `${state.totalTokens}`;
  const cost = `$${budget.remaining.toFixed(2)}`;
  let bar = `\x1b[1;36m${model}\x1b[0m`;
  bar += ` · ${tokens} tok`;
  bar += ` · ${cost}`;
  if (state.files.length > 0) bar += ` · \x1b[33m${state.files.length}f\x1b[0m`;
  if (state.context7) bar += ` · ctx7`;
  bar += ` · genesis:7c24`;
  return bar;
}
function fileContext(files: ChatFile[]): string {
  if (files.length === 0) return "";
  return files
    .map((f) => {
      if (!existsSync(f.path)) return null;
      const content = readFileSync(f.path, "utf-8");
      const lang = f.path.split(".").pop() ?? "";
      return `\`\`\`${lang}\n${content}\n\`\`\``;
    })
    .filter(Boolean)
    .join("\n\n");
}
function parseArgs(argv: string[]): { oneshot: string | null; model: string; files: string[]; ci: boolean; help: boolean } {
  const args = { oneshot: null as string | null, model: "deepseek" as string, files: [] as string[], ci: false, help: false };
  let i = 2;
  while (i < argv.length) {
    const a = argv[i];
    if (!a) break;
    if (a === "--oneshot" || a === "-o") { i++; const v = argv[i]; if (v) args.oneshot = v; }
    else if (a === "--model" || a === "-m") { i++; const v = argv[i]; if (v) args.model = v; }
    else if (a === "--file" || a === "-f") { i++; const v = argv[i]; if (v) args.files.push(v); }
    else if (a === "--ci") { args.ci = true; }
    else if (a === "--help" || a === "-h") { args.help = true; }
    else if (!a.startsWith("-")) { args.oneshot = (args.oneshot ?? "") + " " + a; }
    i++;
  }
  if (args.oneshot) args.oneshot = args.oneshot.trim();
  return args;
}
async function main() {
  const args = parseArgs(process.argv);
  if (args.help) {
    console.log(`
\x1b[1;36mvaked\x1b[0m — Aider-style TUI for the Vaked swarm
  In honor of the Aider project (aider.chat).
USAGE
  vaked                          Interactive TUI
  vaked --oneshot "prompt"      Single prompt
  vaked --ci                     CI mode (stdin → stdout)
SLASH COMMANDS
  /add <path>     Add files to chat context
  /drop <path>    Remove files from context
  /model <name>   Switch model (auto, deepseek, claude, gemini, ...)
  /code           Architect mode — code generation
  /ask            Chat mode — questions
  /context7       Toggle Context7 pre-scan
  /clear          Clear chat history
  /tokens         Show token usage
  /budget         Show remaining budget
  /diff           Show current context files
  /undo           Remove last message
  /stream         Toggle streaming
  /quit           Exit
  In his honor — Aider.
`);
    return;
  }
  let agent: VakedAgent;
  try {
    agent = createVakedAgent({ context7: true });
  } catch (err) {
    console.error(`\x1b[31mfatal:\x1b[0m ${err instanceof Error ? err.message : String(err)}`);
    process.exit(1);
  }
  if (args.ci) {
    const chunks: Buffer[] = [];
    for await (const chunk of process.stdin) chunks.push(typeof chunk === "string" ? Buffer.from(chunk) : chunk);
    const input = Buffer.concat(chunks).toString("utf-8").trim();
    if (!input) { console.error("no input"); process.exit(1); }
    const answer = await agent.ask(input, args.model);
    console.log(answer);
    return;
  }
  if (args.oneshot) {
    const answer = await agent.ask(args.oneshot.trim(), args.model);
    console.log(answer);
    return;
  }
  const state: TuiState = {
    model: args.model,
    stream: true,
    context7: true,
    files: args.files.map((f) => ({ path: f, size: existsSync(f) ? statSync(f).size : 0, addedAt: Date.now() })),
    history: [],
    running: true,
    totalTokens: 0,
    totalCost: 0,
    messageCount: 0,
  };
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout, terminal: true, history: state.history });
  console.log(`\n\x1b[1;36m╭──────────────────────────────────────────────────╮\x1b[0m`);
  console.log(`\x1b[1;36m│\x1b[0m  \x1b[1mvaked\x1b[0m — Aider-style TUI · In his honor           \x1b[1;36m│\x1b[0m`);
  console.log(`\x1b[1;36m│\x1b[0m  ${header(state).padEnd(48)}\x1b[1;36m│\x1b[0m`);
  console.log(`\x1b[1;36m╰──────────────────────────────────────────────────╯\x1b[0m\n`);
  if (state.files.length > 0) {
    console.log(`\x1b[90mFiles in chat:\x1b[0m`);
    for (const f of state.files) {
      const kb = (f.size / 1024).toFixed(1);
      console.log(`  \x1b[33m${f.path}\x1b[0m \x1b[90m(${kb}KB)\x1b[0m`);
    }
    console.log();
  }
  console.log(`\x1b[90mType a prompt. /help for commands. /quit to exit.\x1b[0m\n`);
  rl.on("line", async (line: string) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    if (trimmed.startsWith("/")) {
      const [cmd, ...rest] = trimmed.split(/\s+/);
      const arg = rest.join(" ");
      switch (cmd) {
        case "/help":
          console.log(`\n\x1b[1mCommands:\x1b[0m`);
          console.log(`  \x1b[36m/add <path>\x1b[0m     Add files to chat context`);
          console.log(`  \x1b[36m/drop <path>\x1b[0m    Remove files`);
          console.log(`  \x1b[36m/model <name>\x1b[0m   Switch model (auto, deepseek, claude, gemini)`);
          console.log(`  \x1b[36m/code\x1b[0m           Architect mode — code generation`);
          console.log(`  \x1b[36m/ask\x1b[0m            Chat mode — questions`);
          console.log(`  \x1b[36m/context7\x1b[0m       Toggle Context7 pre-scan`);
          console.log(`  \x1b[36m/clear\x1b[0m          Clear chat`);
          console.log(`  \x1b[36m/tokens\x1b[0m         Token usage`);
          console.log(`  \x1b[36m/budget\x1b[0m         Budget`);
          console.log(`  \x1b[36m/diff\x1b[0m           Show context files`);
          console.log(`  \x1b[36m/undo\x1b[0m           Remove last message`);
          console.log(`  \x1b[36m/stream\x1b[0m         Toggle streaming`);
          console.log(`  \x1b[36m/quit\x1b[0m           Exit\n`);
          break;
        case "/add":
          if (arg && existsSync(arg)) {
            state.files.push({ path: arg, size: statSync(arg).size, addedAt: Date.now() });
            const kb = (statSync(arg).size / 1024).toFixed(1);
            console.log(`  \x1b[90mAdded\x1b[0m \x1b[33m${arg}\x1b[0m \x1b[90m(${kb}KB) · ${state.files.length} files in chat\x1b[0m`);
          } else if (arg) {
            console.log(`  \x1b[31mNot found:\x1b[0m ${arg}`);
          } else {
            console.log(`  \x1b[90mUsage: /add <file>\x1b[0m`);
          }
          break;
        case "/drop":
          if (arg) {
            const before = state.files.length;
            state.files = state.files.filter((f) => f.path !== arg);
            if (state.files.length < before) console.log(`  \x1b[90mDropped\x1b[0m ${arg}`);
            else console.log(`  \x1b[90mNot in chat:\x1b[0m ${arg}`);
          }
          break;
        case "/model":
          if (arg === "auto") {
            state.model = "auto";
            console.log(`  \x1b[90mModel:\x1b[0m auto-routing \x1b[90m(code→claude, explain→deepseek, creative→gemini)\x1b[0m`);
          } else if (arg && MODELS[arg]) {
            state.model = arg;
            console.log(`  \x1b[90mModel:\x1b[0m ${MODELS[arg]?.label} \x1b[90m(${MODELS[arg]?.id})\x1b[0m`);
          } else {
            console.log(`  \x1b[90mAvailable: auto, ${Object.keys(MODELS).join(", ")}\x1b[0m`);
          }
          break;
        case "/code": state.model = "claude"; console.log(`  \x1b[90mCode mode — Claude Opus\x1b[0m`); break;
        case "/ask": state.model = "deepseek"; console.log(`  \x1b[90mChat mode — DeepSeek V4\x1b[0m`); break;
        case "/context7":
          state.context7 = !state.context7;
          console.log(`  \x1b[90mContext7:\x1b[0m ${state.context7 ? "ON" : "OFF"}`);
          break;
        case "/clear":
          state.files = [];
          state.history = [];
          state.totalTokens = 0;
          state.messageCount = 0;
          console.log(`  \x1b[90mChat cleared.\x1b[0m`);
          break;
        case "/tokens":
          console.log(`  \x1b[90m${state.totalTokens} tokens · ${state.messageCount} messages · ~${(state.totalTokens / state.messageCount || 0).toFixed(0)} tok/msg\x1b[0m`);
          break;
        case "/budget":
          console.log(`  \x1b[90m${formatBudget(readBudget())}\x1b[0m`);
          break;
        case "/diff":
          if (state.files.length === 0) console.log(`  \x1b[90mNo files in chat. Use /add <file>.\x1b[0m`);
          else state.files.forEach((f) => console.log(`  \x1b[33m${f.path}\x1b[0m \x1b[90m(${(f.size / 1024).toFixed(1)}KB)\x1b[0m`));
          break;
        case "/undo":
          if (state.history.length > 0) {
            state.history.pop();
            state.messageCount = Math.max(0, state.messageCount - 1);
            console.log(`  \x1b[90mLast message undone.\x1b[0m`);
          }
          break;
        case "/stream":
          state.stream = !state.stream;
          console.log(`  \x1b[90mStreaming:\x1b[0m ${state.stream ? "ON" : "OFF"}`);
          break;
        case "/quit": case "/exit":
          state.running = false;
          rl.close();
          console.log(`\n\x1b[90mIn his honor — Aider.\x1b[0m\n`);
          return;
        default:
          console.log(`  \x1b[90mUnknown: ${cmd}. /help\x1b[0m`);
          break;
      }
      return;
    }
    let prompt = trimmed;
    const ctx = fileContext(state.files);
    if (ctx) prompt = `${ctx}\n\n${trimmed}`;
    const startTime = Date.now();
    state.history.push(trimmed);
    state.messageCount++;
    const tokensIn = tokenEstimate(prompt);
    state.totalTokens += tokensIn;
    try {
      const effectiveModel = state.model === "auto" ? routeModel(trimmed) : (MODELS[state.model]?.id ?? state.model);
      const modelLabel = state.model === "auto" ? `auto→${effectiveModel.split("/").pop()}` : effectiveModel.split("/").pop();
      process.stdout.write(`\n\x1b[1;36m${modelLabel}\x1b[0m `);
      if (state.stream) {
        let charCount = 0;
        for await (const chunk of agent.streamChat(prompt, effectiveModel)) {
          process.stdout.write(chunk);
          charCount += chunk.length;
        }
        const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
        const tokOut = tokenEstimate(" ".repeat(charCount)) || 1;
        state.totalTokens += tokOut;
        console.log(`\n\x1b[90m── ${elapsed}s · ${tokOut} tok · ${formatBudget(readBudget())}\x1b[0m\n`);
      } else {
        const response = await agent.ask(prompt, effectiveModel);
        const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
        const tokOut = tokenEstimate(response);
        state.totalTokens += tokOut;
        console.log(response);
        console.log(`\n\x1b[90m── ${elapsed}s · ${tokOut} tok · ${formatBudget(readBudget())}\x1b[0m\n`);
      }
    } catch (err) {
      console.error(`\x1b[31m[error]\x1b[0m ${err instanceof Error ? err.message : String(err)}\n`);
    }
  });
}
main().catch((err) => { console.error(`\x1b[31mfatal:\x1b[0m ${err.message}`); process.exit(1); });