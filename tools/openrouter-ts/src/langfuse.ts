"use strict";
import { Langfuse } from "langfuse";
import type { LangfuseTraceClient, LangfuseGenerationClient } from "langfuse";
interface LangfuseConfig {
  secretKey: string;
  publicKey: string;
  baseUrl: string;
}
function getConfig(): LangfuseConfig | null {
  const secretKey = process.env["LANGFUSE_SECRET_KEY"];
  const publicKey = process.env["LANGFUSE_PUBLIC_KEY"];
  if (!secretKey || !publicKey) return null;
  return {
    secretKey,
    publicKey,
    baseUrl: process.env["LANGFUSE_HOST"] ??
             process.env["LANGFUSE_BASE_URL"] ??
             "https://cloud.langfuse.com",
  };
}
let _client: Langfuse | null | undefined;
function getClient(): Langfuse | null {
  if (_client === undefined) {
    const config = getConfig();
    if (!config) {
      _client = null;
      return null;
    }
    try {
      _client = new Langfuse({
        secretKey: config.secretKey,
        publicKey: config.publicKey,
        baseUrl: config.baseUrl,
      });
    } catch {
      console.warn("[langfuse] Failed to initialize client — tracing disabled");
      _client = null;
      return null;
    }
  }
  return _client;
}
export interface LlmCallTrace {
  model: string;
  input: string;
  output: string;
  promptTokens: number;
  completionTokens: number;
  cost?: number;
  latencyMs?: number;
  provider?: string;
  agentName?: string;
  generationId?: string;
}
export function traceLlmCall(
  trace: LlmCallTrace,
): LangfuseGenerationClient | null {
  const client = getClient();
  if (!client) return null;
  try {
    const agent = trace.agentName ?? "vaked-openrouter-ts";
    const provider = trace.provider ?? "openrouter";
    const t: LangfuseTraceClient = client.trace({
      name: `${agent}-${trace.model.split("/").pop() ?? trace.model}`,
      input: trace.input.slice(0, 64_000),    // Langfuse caps at ~64KB
      output: trace.output.slice(0, 64_000),
      metadata: {
        provider,
        agent: agent,
        generationId: trace.generationId,
      },
    });
    const gen = t.generation({
      name: `${provider}-${trace.model}`,
      model: trace.model,
      input: trace.input.slice(0, 64_000),
      output: trace.output.slice(0, 64_000),
      usage: {
        promptTokens: trace.promptTokens,
        completionTokens: trace.completionTokens,
        totalTokens: trace.promptTokens + trace.completionTokens,
      },
      metadata: {
        cost: trace.cost,
        latencyMs: trace.latencyMs,
        generationId: trace.generationId,
      },
    });
    return gen;
  } catch (err) {
    console.warn(`[langfuse] Trace failed: ${err instanceof Error ? err.message : String(err)}`);
    return null;
  }
}
export async function flushLangfuse(): Promise<void> {
  const client = getClient();
  if (!client) return;
  try {
    await client.shutdownAsync();
  } catch {
  }
}
export function isLangfuseEnabled(): boolean {
  return getClient() !== null;
}
export function traceCallModelResult(params: {
  model: string;
  input: string;
  output: string;
  promptTokens: number;
  completionTokens: number;
  cost?: number;
  latencyMs?: number;
  agentName?: string;
  generationId?: string;
}): void {
  traceLlmCall({
    model: params.model,
    input: params.input,
    output: params.output,
    promptTokens: params.promptTokens,
    completionTokens: params.completionTokens,
    cost: params.cost,
    latencyMs: params.latencyMs,
    agentName: params.agentName,
    generationId: params.generationId,
    provider: "openrouter",
  });
}