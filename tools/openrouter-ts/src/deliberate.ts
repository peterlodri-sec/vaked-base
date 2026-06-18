"use strict";

/**
 * deliberate — 20-model autonomous deliberation panel.
 *
 * Port of tools/openrouter/deliberate.py.
 * Broadcasts a single prompt to 20 models, synthesizes consensus via a Judge.
 * Budget-capped at $10/session. All costs logged.
 *
 * GENESIS_SEAL: 7c242080
 */

import { OpenRouter } from "@openrouter/agent";
import { PANEL_MODELS, JUDGE_MODEL, type PanelModel } from "./types.js";

const BUDGET_CAP = 10.0;
const CONCURRENCY = 8;

export interface ModelResponse {
  model: string;
  name: string;
  output: string;
  promptTokens: number;
  completionTokens: number;
  cost: number;
  error?: string;
}

export interface DeliberationResult {
  prompt: string;
  modelsQueried: number;
  totalCost: number;
  consensus: string;
  responses: Array<{ model: string; cost: number; preview: string }>;
}

function getClient(): OpenRouter {
  const apiKey = process.env["OPENROUTER_API_KEY"];
  if (!apiKey) throw new Error("OPENROUTER_API_KEY not set");
  return new OpenRouter({ apiKey });
}

async function callSingleModel(
  client: OpenRouter,
  entry: PanelModel,
  prompt: string,
  maxOutputTokens: number = 300,
): Promise<ModelResponse> {
  try {
    const result = client.callModel({
      model: entry.id,
      input: [{ role: "user", content: prompt }],
      maxOutputTokens: maxOutputTokens,
    });

    const text = await result.getText();
    const response = await result.getResponse();
    const usage = response.usage ?? { inputTokens: 0, outputTokens: 0 };

    const cost =
      (usage.inputTokens * entry.promptCost + usage.outputTokens * entry.completionCost) /
      1_000_000;

    return {
      model: entry.id,
      name: entry.name,
      output: text,
      promptTokens: usage.inputTokens,
      completionTokens: usage.outputTokens,
      cost,
    };
  } catch (err) {
    return {
      model: entry.id,
      name: entry.name,
      output: "",
      promptTokens: 0,
      completionTokens: 0,
      cost: 0,
      error: String(err),
    };
  }
}

async function synthesize(
  client: OpenRouter,
  prompt: string,
  responses: ModelResponse[],
): Promise<string> {
  const summaries = responses
    .filter((r) => r.output)
    .map(
      (r) => `[${r.model.split("/").pop()?.slice(0, 15) ?? r.model}]: ${r.output.slice(0, 300)}`,
    )
    .join("\n\n---\n\n");

  const judgePrompt = `You are the Judge. Synthesize consensus from a 20-model deliberation panel.

ORIGINAL QUESTION: ${prompt}

MODEL RESPONSES:
${summaries}

Synthesize a single, concise answer that:
1. Identifies areas of strong consensus (>70% agreement)
2. Highlights unique insights from any dissenting models
3. Gives the final answer with confidence level (HIGH/MEDIUM/LOW)
4. Lists the top 3 models that contributed most to the consensus

Format as a clear, structured response. Be direct. No filler.`;

  const result = client.callModel({
    model: JUDGE_MODEL,
    input: [{ role: "user", content: judgePrompt }],
    maxOutputTokens: 800,
  });

  return result.getText();
}

/**
 * Run the 20-model deliberation panel.
 * Port of deliberate.deliberate().
 */
export async function deliberate(
  prompt: string,
  budgetCap: number = BUDGET_CAP,
): Promise<DeliberationResult> {
  const client = getClient();

  console.error(`Deliberation: ${PANEL_MODELS.length} models · Budget cap: $${budgetCap.toFixed(2)}`);
  console.error(`Question: ${prompt.slice(0, 100)}...\n`);

  let totalCost = 0;
  const responses: ModelResponse[] = [];
  const panel = [...PANEL_MODELS];

  // Process in batches of CONCURRENCY
  for (let batch = 0; batch < panel.length; batch += CONCURRENCY) {
    const batchModels = panel.slice(batch, batch + CONCURRENCY);

    const batchResults = await Promise.all(
      batchModels.map((entry) => callSingleModel(client, entry, prompt)),
    );

    for (const result of batchResults) {
      responses.push(result);
      totalCost += result.cost;
      const status = result.output ? "✅" : "❌";
      console.error(
        `  ${status} ${result.name.padEnd(25)} $${result.cost.toFixed(4)}  ${result.output.slice(0, 60)}...`,
      );

      if (totalCost > budgetCap) {
        console.error(`  ⚠️ Budget cap reached ($${totalCost.toFixed(2)}). Stopping.`);
        break;
      }
    }

    if (totalCost > budgetCap) break;
  }

  console.error(`\nTotal cost: $${totalCost.toFixed(4)}`);
  console.error("Synthesizing consensus via Judge...");

  const consensus = await synthesize(client, prompt, responses);

  return {
    prompt,
    modelsQueried: responses.length,
    totalCost,
    consensus,
    responses: responses.map((r) => ({
      model: r.model,
      cost: r.cost,
      preview: r.output.slice(0, 100),
    })),
  };
}
