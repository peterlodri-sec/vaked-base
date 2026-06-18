"use strict";
import { OpenRouter } from "@openrouter/agent";
import type { CallModelInput, Tool, ToolWithExecute, StopCondition, TurnContext } from "@openrouter/agent";
import { createContext7Tools, context7SystemPrompt, context7PreScan, logPreScanInjection } from "./context7.js";
import { createVastaiTools, vastaiSystemPrompt } from "./vastai.js";
import { createCubeTools, cubeSystemPrompt } from "./cube.js";
import { createMemoryTools, memorySystemPrompt } from "./memory.js";
import { createBaoTools, baoSystemPrompt } from "./bao.js";
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
export {
  traceLlmCall,
  traceCallModelResult,
  flushLangfuse,
  isLangfuseEnabled,
} from "./langfuse.js";
export type { LlmCallTrace } from "./langfuse.js";
export type { ModelRouterConfig, ModelRoutingStrategy } from "./types.js";
function getClient(): OpenRouter {
  const apiKey = process.env["OPENROUTER_API_KEY"];
  if (!apiKey) {
    throw new Error("OPENROUTER_API_KEY not set");
  }
  return new OpenRouter({ apiKey });
}
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
  const response = await result.getResponse();
  trackCost(
    response.usage?.inputTokens ?? 0,
    response.usage?.outputTokens ?? 0,
    entry.promptCost,
    entry.completionCost,
  );
  return text;
}
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
export function budget(): string {
  return formatBudget(readBudget());
}
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
  const lower = prompt.toLowerCase();
  for (const [keyword, model] of Object.entries(TASK_MODEL_MAP)) {
    if (lower.includes(keyword)) {
      return model;
    }
  }
  return config.cheapModel ?? "deepseek/deepseek-v4-pro";
}
export function modelFallbackChain(primaryModel: string): string[] {
  if (primaryModel.includes("claude")) {
    return [primaryModel, "deepseek/deepseek-v4-pro", "google/gemini-2.5-flash"];
  }
  if (primaryModel.includes("deepseek")) {
    return [primaryModel, "google/gemini-2.5-flash", "anthropic/claude-haiku-4-5"];
  }
  return [primaryModel, "deepseek/deepseek-v4-pro", "google/gemini-2.5-flash"];
}
export interface VakedAgentOptions {
  apiKey?: string;
  defaultModel?: string;
  context7?: boolean;
  extraTools?: Tool[];
  defaultStopWhen?: StopCondition[];
  defaultMaxTokens?: number;
  modelRouting?: ModelRouterConfig;
}
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
  const baseTools: Tool[] = context7 ? [...createContext7Tools(), ...createVastaiTools(), ...createBaoTools(), ...createCubeTools(), ...createMemoryTools()] : [...createVastaiTools(), ...createBaoTools(), ...createCubeTools(), ...createMemoryTools(), ...createMilvusTools()];
  const allTools = [...baseTools, ...extraTools];
  const baseInstructions = (context7 ? context7SystemPrompt() + "\n\n" : "") + vastaiSystemPrompt() + "\n\n" + baoSystemPrompt() + "\n\n" + cubeSystemPrompt() + "\n\n" + memorySystemPrompt();
  const router = options.modelRouting ?? DEFAULT_ROUTER;
  return {
    client,
    router,
    tools: allTools,
    baseInstructions,
    callModel<TTools extends readonly Tool[] = readonly Tool[]>(
      input: CallModelInput<TTools> & { sharedContextSchema?: any },
      callOptions?: any,
    ) {
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
    async ask(prompt: string, model?: string, maxTokens?: number): Promise<string> {
      const selectedModel = model ?? routeModel(prompt, router);
      const entry = MODELS[selectedModel] ?? {
        id: selectedModel,
        label: model ?? "default",
        promptCost: 0,
        completionCost: 0,
      };
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
    async code(prompt: string, maxTokens?: number): Promise<string> {
      const selectedModel = routeModel(prompt, router);
      let enrichedPrompt = prompt;
      if (context7) {
        const scan = await context7PreScan(prompt);
        if (scan.injected) { logPreScanInjection(scan); enrichedPrompt = scan.injected + "\n\n---\n\nUser: " + prompt; }
      }
      const result = client.callModel({
        model: selectedModel,
        input: [{ role: "user", content: enrichedPrompt }],
        instructions: `${baseInstructions}\n\nZig 0.16 systems programmer. Write production code. No explanations, only code.`,
        tools: allTools.length > 0 ? allTools : undefined,
        maxOutputTokens: maxTokens ?? 2000,
        stopWhen: defaultStopWhen,
      } as any);
      return result.getText();
    },
    async review(prompt: string, maxTokens?: number): Promise<string> {
      const selectedModel = routeModel(prompt, router);
      let enrichedPrompt = prompt;
      if (context7) {
        const scan = await context7PreScan(prompt);
        if (scan.injected) { logPreScanInjection(scan); enrichedPrompt = scan.injected + "\n\n---\n\nUser: " + prompt; }
      }
      const result = client.callModel({
        model: selectedModel,
        input: [{ role: "user", content: enrichedPrompt }],
        instructions: `${baseInstructions}\n\nCritical reviewer. 3-5 specific suggestions. Be direct.`,
        tools: allTools.length > 0 ? allTools : undefined,
        maxOutputTokens: maxTokens ?? 600,
        stopWhen: defaultStopWhen,
      } as any);
      return result.getText();
    },
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
export type VakedAgent = ReturnType<typeof createVakedAgent>;
// ── Speculative RAG — race LLM vs Vaked Docs, fastest wins ────────────────

/**
export async function speculativeAsk(
  agent: VakedAgent,
  prompt: string,
  model?: string,
): Promise<{ response: string; ragUsed: boolean; ragResult?: string }> {
  // Fire both in parallel
  const llmPromise = agent.ask(prompt, model);
  const ragPromise = (async () => {
    try {
      const docsUrl = process.env["VAKED_DOCS_URL"] ?? "http://localhost:9845";
      const res = await fetch(`${docsUrl}/search?q=${encodeURIComponent(prompt.slice(0, 300))}`);
      if (!res.ok) return null;
      return res.json() as any;
    } catch { return null; }
  })();

  const result = await Promise.race([
    llmPromise.then(r => ({ type: "llm" as const, value: r })),
    ragPromise.then(r => ({ type: "rag" as const, value: r })),
  ]);

  if (result.type === "rag" && result.value?.results?.length) {
    // RAG won — inject docs, retry LLM with enriched prompt
    const ragContext = result.value.results
      .slice(0, 3)
      .map((e: any) => e.snippets?.map((s: any) => s.code ?? s.content).join("\n"))
      .join("\n\n");

    const enrichedPrompt = `## Vaked Docs (speculative RAG — fastest path)\n${ragContext.slice(0, 2048)}\n\n---\n\n${prompt}`;
    const llmResponse = await agent.ask(enrichedPrompt, model);

    return { response: llmResponse, ragUsed: true, ragResult: ragContext.slice(0, 500) };
  }

  // LLM won — return response, RAG result available for next turn
  const ragResult = await ragPromise;
  return {
    response: result.type === "llm" ? result.value : await llmPromise,
    ragUsed: false,
    ragResult: ragResult?.results?.length
      ? ragResult.results.slice(0, 1).map((e: any) => e.snippets?.[0]?.content).join("\n").slice(0, 500)
      : undefined,
  };
}
