"use strict";

/**
 * @vaked/openrouter-ts — OpenRouter Agent SDK toolkit for Vaked.
 *
 * Replaces hand-rolled Python `urllib.request` HTTP calls with the type-safe
 * `@openrouter/agent` SDK. Provides:
 *
 *   - `ask()` — cheap/fast single-turn queries
 *   - `code()` — code generation with Claude
 *   - `review()` — code review with Claude
 *   - `streamChat()` — streaming chat completion
 *   - `sweLoop()` — self-improvement reflection loop
 *   - `budget()` — budget status
 *
 * GENESIS_SEAL: 7c242080
 */

import { OpenRouter } from "@openrouter/agent";
import type { CallModelInput, Tool, ToolWithExecute, StopCondition, TurnContext } from "@openrouter/agent";
import { createContext7Tools, context7SystemPrompt, context7PreScan, logPreScanInjection } from "./context7.js";
import { traceCallModelResult, flushLangfuse, isLangfuseEnabled } from "./langfuse.js";
import {
  MODELS,
  DEFAULT_ROUTER,
  TASK_MODEL_MAP,
  type ChatOptions,
  type ChatResult,
  type ModelRouterConfig,
  type ModelRoutingStrategy,
} from "./types.js";
import { readBudget, formatBudget, trackCost } from "./budget.js";

// Re-export SDK types for consumers
export { OpenRouter } from "@openrouter/agent";
export type {
  CallModelInput,
  Tool,
  ToolWithExecute,
  StopCondition,
  TurnContext,
} from "@openrouter/agent";
export { stepCountIs, maxCost, maxTokensUsed, finishReasonIs } from "@openrouter/agent";
export { tool } from "@openrouter/agent";
export {
  MODELS,
  PANEL_MODELS,
  JUDGE_MODEL,
  type ModelEntry,
  type ChatOptions,
  type ChatResult,
  type BudgetState,
  type PanelModel,
} from "./types.js";
export {
  readBudget,
  writeBudget,
  trackCost as trackBudgetCost,
  formatBudget,
  affordableTokens,
} from "./budget.js";

// ── Langfuse observability (CI secrets, guarded) ────────────────────────

export {
  traceLlmCall,
  traceCallModelResult,
  flushLangfuse,
  isLangfuseEnabled,
} from "./langfuse.js";

export type { LlmCallTrace } from "./langfuse.js";
export type { ModelRouterConfig, ModelRoutingStrategy } from "./types.js";

// ── Client factory ──────────────────────────────────────────────────────────

function getClient(): OpenRouter {
  const apiKey = process.env["OPENROUTER_API_KEY"];
  if (!apiKey) {
    throw new Error("OPENROUTER_API_KEY not set");
  }
  return new OpenRouter({ apiKey });
}

// ── High-level convenience functions (port of tools/openrouter/qcall.py) ─────

/**
 * Quick question — cheap, fast. Default: DeepSeek V4 Pro.
 * Direct port of qcall.ask().
 */
export async function ask(
  prompt: string,
  model: string = "deepseek",
  maxOutputTokens: number = 500,
): Promise<string> {
  const entry = MODELS[model] ?? { id: model, label: model, promptCost: 0, completionCost: 0 };
  const client = getClient();

  const result = client.callModel({
    model: entry.id,
    input: [{ role: "user", content: prompt }],
    instructions: "You are a helpful assistant.",
    maxOutputTokens: maxOutputTokens,
  });

  const text = await result.getText();

  // Track cost from usage
  const response = await result.getResponse();
  trackCost(
    response.usage?.inputTokens ?? 0,
    response.usage?.outputTokens ?? 0,
    entry.promptCost,
    entry.completionCost,
  );

  return text;
}

/**
 * Generate code — direct call. Default: Claude Opus 4.8.
 * Direct port of qcall.code().
 */
export async function code(
  prompt: string,
  model: string = "claude",
  maxOutputTokens: number = 2000,
): Promise<string> {
  const entry = MODELS[model] ?? { id: model, label: model, promptCost: 0, completionCost: 0 };
  const client = getClient();

  const result = client.callModel({
    model: entry.id,
    input: [{ role: "user", content: prompt }],
    instructions: "Zig 0.16 systems programmer. Write production code. No explanations, only code.",
    maxOutputTokens: maxOutputTokens,
  });

  const startTime = Date.now();
  const text = await result.getText();
  const response = await result.getResponse();

  traceCallModelResult({
    model: entry.id,
    input: prompt,
    output: text,
    promptTokens: response.usage?.inputTokens ?? 0,
    completionTokens: response.usage?.outputTokens ?? 0,
    latencyMs: Date.now() - startTime,
    agentName: "vaked-agent-code",
  });

  trackCost(
    response.usage?.inputTokens ?? 0,
    response.usage?.outputTokens ?? 0,
    entry.promptCost,
    entry.completionCost,
  );

  return text;
}

/**
 * Review code — direct call. Default: Claude Opus 4.8.
 * Direct port of qcall.review().
 */
export async function review(
  prompt: string,
  model: string = "claude",
  maxOutputTokens: number = 600,
): Promise<string> {
  const entry = MODELS[model] ?? { id: model, label: model, promptCost: 0, completionCost: 0 };
  const client = getClient();

  const result = client.callModel({
    model: entry.id,
    input: [{ role: "user", content: prompt }],
    instructions: "Critical reviewer. 3-5 specific suggestions. Be direct.",
    maxOutputTokens: maxOutputTokens,
  });

  const startTime = Date.now();
  const text = await result.getText();
  const response = await result.getResponse();

  traceCallModelResult({
    model: entry.id,
    input: prompt,
    output: text,
    promptTokens: response.usage?.inputTokens ?? 0,
    completionTokens: response.usage?.outputTokens ?? 0,
    latencyMs: Date.now() - startTime,
    agentName: "vaked-agent-review",
  });

  trackCost(
    response.usage?.inputTokens ?? 0,
    response.usage?.outputTokens ?? 0,
    entry.promptCost,
    entry.completionCost,
  );

  return text;
}

/**
 * Full chat completion with all options.
 * Direct port of openrouter/cli.py call().
 */
export async function chat(options: ChatOptions): Promise<ChatResult> {
  const {
    model = "deepseek",
    system,
    maxTokens = 1000,
  } = options;

  const entry = MODELS[model] ?? {
    id: model,
    label: model,
    promptCost: 0,
    completionCost: 0,
  };
  const client = getClient();

  const result = client.callModel({
    model: entry.id,
    input: [{ role: "user", content: "" }],
    instructions: system,
    maxOutputTokens: maxTokens,
  });

  const text = await result.getText();
  const response = await result.getResponse();

  const budget = trackCost(
    response.usage?.inputTokens ?? 0,
    response.usage?.outputTokens ?? 0,
    entry.promptCost,
    entry.completionCost,
  );

  return {
    content: text,
    model: entry.id,
    promptTokens: response.usage?.inputTokens ?? 0,
    completionTokens: response.usage?.outputTokens ?? 0,
    cost: budget.spent,
  };
}

/**
 * Return budget status string.
 */
export function budget(): string {
  return formatBudget(readBudget());
}

// ── Streaming helper ────────────────────────────────────────────────────────

/**
 * Stream a chat completion, yielding text chunks.
 * Returns an async iterable of content strings.
 */
export async function* streamChat(
  prompt: string,
  options: ChatOptions = {},
): AsyncGenerator<string> {
  const { model = "deepseek", system = "You are a helpful assistant.", maxTokens = 1000 } = options;

  const entry = MODELS[model] ?? {
    id: model,
    label: model,
    promptCost: 0,
    completionCost: 0,
  };
  const client = getClient();

  const result = client.callModel({
    model: entry.id,
    input: [{ role: "user", content: prompt }],
    instructions: system,
    maxOutputTokens: maxTokens,
  });

  for await (const delta of result.getTextStream()) {
    yield delta;
  }
}

// ── Agent loop helper ───────────────────────────────────────────────────────

/**
 * Run a self-improvement loop (SWE reflection pattern).
 * The agent generates, then critiques its own output until PASS or maxIterations.
 */
export async function sweLoop(
  prompt: string,
  options: {
    model?: string;
    maxIterations?: number;
    instructions?: string;
  } = {},
): Promise<{ finalResponse: string; reflections: string[]; iterations: number }> {
  const {
    model = "deepseek",
    maxIterations = 3,
    instructions = "You are a senior software engineer. Generate a solution, then critique it.",
  } = options;

  const entry = MODELS[model] ?? {
    id: model,
    label: model,
    promptCost: 0,
    completionCost: 0,
  };
  const client = getClient();

  const reflections: string[] = [];
  let finalResponse = "";

  for (let i = 0; i < maxIterations; i++) {
    const userContent = i === 0
      ? prompt
      : `${prompt}\n\nPrevious attempt:\n${finalResponse}\n\nCritique and improve.`;

    const result = client.callModel({
      model: entry.id,
      input: [{ role: "user", content: userContent }],
      instructions,
      maxOutputTokens: 2000,
    });

    const content = await result.getText();
    finalResponse = content;
    reflections.push(content);

    if (content.includes("PASS") || content.includes("[DONE]")) {
      break;
    }
  }

  return { finalResponse, reflections, iterations: reflections.length };
}

// ── Context7 — first-class native library documentation ─────────────────────

export {
  searchLibrary,
  getContext,
  resolveLibraryId,
  queryDocs,
  createContext7Tools,
  context7SystemPrompt,
  Context7Error,
  CodeExampleSchema,
  CodeSnippetSchema,
  InfoSnippetSchema,
  ContextResponseSchema,
  LibrarySchema,
  SearchResponseSchema,
} from "./context7.js";

export type {
  CodeExample,
  CodeSnippet,
  InfoSnippet,
  ContextResponse,
  Library,
  SearchResponse,
} from "./context7.js";

// ── Vaked Agent — OpenRouter + Context7, auto-wired ─────────────────────────



// ── Conductor — model self-selection, models choose their own ───────────────

/**
 * Route a prompt to the best model based on task analysis.
 * Heuristic: keyword matching for instant routing (no API call needed).
 * Falls back to default model if no match.
 */
export function routeModel(
  prompt: string,
  config: ModelRouterConfig = DEFAULT_ROUTER,
): string {
  if (config.strategy === "fixed") {
    return config.fixedModel ?? config.qualityModel ?? "deepseek/deepseek-v4-pro";
  }

  if (config.strategy === "quality") {
    return config.qualityModel ?? "anthropic/claude-opus-4-8-fast";
  }

  if (config.strategy === "cost-optimized") {
    return config.cheapModel ?? "deepseek/deepseek-v4-pro";
  }

  // "auto" — keyword-based task routing
  const lower = prompt.toLowerCase();
  for (const [keyword, model] of Object.entries(TASK_MODEL_MAP)) {
    if (lower.includes(keyword)) {
      return model;
    }
  }

  // Default: cheap model for unknown tasks
  return config.cheapModel ?? "deepseek/deepseek-v4-pro";
}

/**
 * Get the model fallback array for OpenRouter's `models` parameter.
 * OpenRouter will try models in order if the primary fails.
 */
export function modelFallbackChain(primaryModel: string): string[] {
  // If primary is Claude, fallback to DeepSeek → Gemini
  if (primaryModel.includes("claude")) {
    return [primaryModel, "deepseek/deepseek-v4-pro", "google/gemini-2.5-flash"];
  }
  // If primary is DeepSeek, fallback to Gemini → Claude
  if (primaryModel.includes("deepseek")) {
    return [primaryModel, "google/gemini-2.5-flash", "anthropic/claude-haiku-4-5"];
  }
  // Generic fallback
  return [primaryModel, "deepseek/deepseek-v4-pro", "google/gemini-2.5-flash"];
}

/**
 * Pre-configured Vaked agent options.
 * OpenRouter is the go-to provider. Context7 is auto-wired.
 */
export interface VakedAgentOptions {
  /** OpenRouter API key (default: OPENROUTER_API_KEY env) */
  apiKey?: string;
  /** Default model (default: deepseek-v4-pro for cheap/fast) */
  defaultModel?: string;
  /** Whether to auto-include Context7 tools (default: true) */
  context7?: boolean;
  /** Extra tools beyond Context7 */
  extraTools?: Tool[];
  /** Default stop conditions */
  defaultStopWhen?: StopCondition[];
  /** Max output tokens default (default: 2000) */
  defaultMaxTokens?: number;
  /** Model routing strategy (default: "auto") */
  modelRouting?: ModelRouterConfig;
}

/**
 * A Vaked agent — OpenRouter client with Context7 auto-wired.
 *
 * OpenRouter is the go-to LLM provider. Context7 provides authoritative
 * live documentation. This function wires them together so every agent
 * gets up-to-date library docs by default.
 *
 * @example
 * ```typescript
 * import { createVakedAgent } from "@vaked/openrouter-ts";
 *
 * const agent = createVakedAgent();
 *
 * // Quick question — Context7 auto-available
 * const answer = await agent.ask("How do I use std.Build in Zig 0.16?");
 *
 * // Full agent loop with Context7
 * const result = agent.callModel({
 *   model: "anthropic/claude-opus-4-8-fast",
 *   input: [{ role: "user", content: "Write a Nix flake for a Zig project" }],
 * });
 * ```
 */
export function createVakedAgent(options: VakedAgentOptions = {}) {
  const {
    apiKey = process.env["OPENROUTER_API_KEY"],
    defaultModel = MODELS["deepseek"]?.id ?? "deepseek/deepseek-v4-pro",
    context7 = true,
    extraTools = [],
    defaultStopWhen,
    defaultMaxTokens = 2000,
  } = options;

  if (!apiKey) {
    throw new Error(
      "OPENROUTER_API_KEY required. Pass apiKey option or set env var.\n" +
      "Get a key at https://openrouter.ai/settings/keys",
    );
  }

  const client = new OpenRouter({ apiKey });

  // Auto-wire Context7 tools
  const baseTools: Tool[] = context7 ? createContext7Tools() : [];
  const allTools = [...baseTools, ...extraTools];

  // Base instructions with Context7 awareness
  const baseInstructions = context7
    ? context7SystemPrompt()
    : "You are a helpful assistant.";

  const router = options.modelRouting ?? DEFAULT_ROUTER;

  return {
    /** The underlying OpenRouter client */
    client,

    /** Model router config */
    router,

    /** All auto-wired tools (Context7 + extras) */
    tools: allTools,

    /** Base instructions (includes Context7 ground-truth prompt) */
    baseInstructions,

    /**
     * Call a model — Context7 tools and instructions auto-included.
     * Override tools/instructions per-call if needed.
     */
    callModel<TTools extends readonly Tool[] = readonly Tool[]>(
      input: CallModelInput<TTools> & { sharedContextSchema?: any },
      callOptions?: any,
    ) {
      // Merge defaults: Context7 instructions prepended, tools merged
      const mergedInstructions = input.instructions
        ? `${baseInstructions}\n\n${input.instructions}`
        : baseInstructions;

      const mergedTools = input.tools
        ? [...allTools, ...(input.tools as unknown as Tool[])]
        : (allTools as any);

      return client.callModel(
        {
          ...input,
          instructions: mergedInstructions,
          tools: mergedTools.length > 0 ? mergedTools : undefined,
          maxOutputTokens: input.maxOutputTokens ?? defaultMaxTokens,
          stopWhen: input.stopWhen ?? defaultStopWhen,
        } as any,
        callOptions,
      );
    },

    /**
     * Quick ask — cheap model, Context7 available.
     * Direct port of qcall.ask() but with Context7 auto-wired.
     */
    async ask(prompt: string, model?: string, maxTokens?: number): Promise<string> {
      const selectedModel = model ?? routeModel(prompt, router);
      const entry = MODELS[selectedModel] ?? {
        id: selectedModel,
        label: model ?? "default",
        promptCost: 0,
        completionCost: 0,
      };

      // Conductor: Context7 pre-scan injection
      let enrichedPrompt = prompt;
      if (context7) {
        const scan = await context7PreScan(prompt);
        if (scan.injected) {
          logPreScanInjection(scan);
          enrichedPrompt = scan.injected + "\n\n---\n\nUser: " + prompt;
        }
      }

      const result = client.callModel({
        model: entry.id,
        input: [{ role: "user", content: enrichedPrompt }],
        instructions: baseInstructions,
        tools: allTools.length > 0 ? allTools : undefined,
        maxOutputTokens: maxTokens ?? 500,
        stopWhen: defaultStopWhen,
      } as any);

      return result.getText();
    },

    /**
     * Generate code — Claude Opus, Context7 auto-available for library docs.
     */
    async code(prompt: string, maxTokens?: number): Promise<string> {
      const result = client.callModel({
        model: MODELS["claude"]?.id ?? "anthropic/claude-opus-4-8-fast",
        input: [{ role: "user", content: prompt }],
        instructions: `${baseInstructions}\n\nZig 0.16 systems programmer. Write production code. No explanations, only code.`,
        tools: allTools.length > 0 ? allTools : undefined,
        maxOutputTokens: maxTokens ?? 2000,
        stopWhen: defaultStopWhen,
      } as any);

      return result.getText();
    },

    /**
     * Review code — Claude Opus.
     */
    async review(prompt: string, maxTokens?: number): Promise<string> {
      const result = client.callModel({
        model: MODELS["claude"]?.id ?? "anthropic/claude-opus-4-8-fast",
        input: [{ role: "user", content: prompt }],
        instructions: `${baseInstructions}\n\nCritical reviewer. 3-5 specific suggestions. Be direct.`,
        tools: allTools.length > 0 ? allTools : undefined,
        maxOutputTokens: maxTokens ?? 600,
        stopWhen: defaultStopWhen,
      } as any);

      return result.getText();
    },

    /**
     * Stream a response — Context7 auto-available.
     */
    streamChat(prompt: string, model?: string, maxTokens?: number) {
      const selectedModel = model ?? routeModel(prompt, router);
      const entry = MODELS[selectedModel] ?? {
        id: selectedModel,
        label: model ?? "default",
        promptCost: 0,
        completionCost: 0,
      };

      const result = client.callModel({
        model: entry.id,
        input: [{ role: "user", content: prompt }],
        instructions: baseInstructions,
        tools: allTools.length > 0 ? allTools : undefined,
        maxOutputTokens: maxTokens ?? 1000,
        stopWhen: defaultStopWhen,
      } as any);

      return result.getTextStream();
    },
  };
}

/** Type for the return value of createVakedAgent() */
export type VakedAgent = ReturnType<typeof createVakedAgent>;
