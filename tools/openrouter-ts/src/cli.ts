#!/usr/bin/env node
"use strict";
/**
 * orcli — OpenRouter CLI. Port of tools/openrouter/cli.py.
 *
 * Usage:
 *   orcli "your prompt"
 *   orcli --model claude "your prompt"
 *   orcli --model gemini "your prompt"
 *   orcli --file input.txt "system prompt"
 *   orcli --budget 0.50 "prompt"
 *   orcli --stream "prompt"
 *   orcli --list
 *   orcli --status
 *   orcli --deliberate "your question"
 */

import { readFileSync } from "node:fs";
import { OpenRouter } from "@openrouter/agent";
import { MODELS, type ModelEntry } from "./types.js";
import { readBudget, writeBudget, trackCost } from "./budget.js";
import { deliberate } from "./deliberate.js";

function resolveModel(name: string): ModelEntry {
  return MODELS[name] ?? {
    id: name,
    label: name,
    promptCost: 0,
    completionCost: 0,
  };
}

function parseArgs(args: string[]): {
  prompt: string;
  model: string;
  system: string;
  maxTokens: number;
  stream: boolean;
  list: boolean;
  status: boolean;
  deliberate_mode: boolean;
  file?: string;
  budgetCap?: number;
} {
  let model = "deepseek";
  let system = "You are a helpful assistant.";
  let maxTokens = 1000;
  let stream = false;
  let list = false;
  let status = false;
  let file: string | undefined;
  let budgetCap: number | undefined;
  let deliberate_mode = false;
  const promptParts: string[] = [];

  let i = 2;
  while (i < args.length) {
    const arg = args[i];
    switch (arg) {
      case "--model":
      case "-m": {
        i++;
        if (i < args.length) model = args[i];
        break;
      }
      case "--system":
      case "-s": {
        i++;
        if (i < args.length) system = args[i];
        break;
      }
      case "--file":
      case "-f": {
        i++;
        if (i < args.length) file = args[i];
        break;
      }
      case "--max-tokens":
      case "-t": {
        i++;
        if (i < args.length) maxTokens = parseInt(args[i], 10);
        break;
      }
      case "--stream":
        stream = true;
        break;
      case "--budget":
      case "-b": {
        i++;
        if (i < args.length) budgetCap = parseFloat(args[i]);
        break;
      }
      case "--list":
      case "-l":
        list = true;
        break;
      case "--status":
        status = true;
        break;
      case "--deliberate":
      case "-d":
        deliberate_mode = true;
        break;
      default:
        promptParts.push(arg);
        break;
    }
    i++;
  }

  const prompt = promptParts.join(" ");
  return { prompt, model, system, maxTokens, stream, list, status, file, budgetCap, deliberate_mode };
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv);

  if (args.list) {
    console.log("Available models:");
    for (const [name, entry] of Object.entries(MODELS)) {
      console.log(
        `  ${name.padEnd(12)} ${entry.id.padEnd(45)} $${entry.promptCost.toFixed(2)}/$${entry.completionCost.toFixed(2)} per 1M tok`,
      );
    }
    return;
  }

  if (args.status) {
    console.log(`Budget remaining: $${readBudget().remaining.toFixed(4)}`);
    return;
  }

  // Get prompt
  let userPrompt: string;
  if (args.file) {
    userPrompt = readFileSync(args.file, "utf-8");
  } else if (args.prompt) {
    userPrompt = args.prompt;
  } else {
    // Read from stdin
    const chunks: Buffer[] = [];
    for await (const chunk of process.stdin) {
      chunks.push(typeof chunk === "string" ? Buffer.from(chunk) : chunk);
    }
    userPrompt = Buffer.concat(chunks).toString("utf-8");
  }

  if (!userPrompt.trim()) {
    console.error("Error: no prompt provided");
    process.exit(1);
  }

  // --deliberate mode
  if (args.deliberate_mode) {
    const result = await deliberate(userPrompt, args.budgetCap);
    console.log("\n" + "=".repeat(60));
    console.log("JUDGE CONSENSUS:");
    console.log("=".repeat(60));
    console.log(result.consensus);
    return;
  }

  // Set budget cap if provided
  if (args.budgetCap !== undefined) {
    writeBudget(args.budgetCap);
  }

  const entry = resolveModel(args.model);
  const apiKey = process.env.OPENROUTER_API_KEY;
  if (!apiKey) {
    console.error("Error: OPENROUTER_API_KEY not set");
    process.exit(1);
  }

  const client = new OpenRouter({ apiKey });

  const result = client.callModel({
    model: entry.id,
    input: [{ role: "user", content: userPrompt }],
    instructions: args.system,
    maxOutputTokens: args.maxTokens,
  });

  if (args.stream) {
    for await (const delta of result.getTextStream()) {
      process.stdout.write(delta);
    }
    process.stdout.write("\n");
  } else {
    const [text, response] = await Promise.all([
      result.getText(),
      result.getResponse(),
    ]);

    const usage = response.usage ?? { inputTokens: 0, outputTokens: 0 };
    const budget = trackCost(
      usage.inputTokens,
      usage.outputTokens,
      entry.promptCost,
      entry.completionCost,
    );

    console.log(text);
    console.error(
      `\n── ${entry.id} · ${usage.inputTokens}→${usage.outputTokens} tok · $${budget.spent.toFixed(4)} · $${budget.remaining.toFixed(2)} left`,
    );
  }
}

main().catch((err) => {
  console.error(`Error: ${err.message ?? err}`);
  process.exit(1);
});
