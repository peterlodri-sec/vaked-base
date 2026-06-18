"use strict";

/**
 * langfuse — LLM observability for the Vaked swarm.
 *
 * Secrets come from the GitHub CI Environment `ci`:
 *   LANGFUSE_SECRET_KEY  — required for tracing
 *   LANGFUSE_PUBLIC_KEY  — required for tracing
 *   LANGFUSE_HOST        — optional (default: https://cloud.langfuse.com)
 *
 * Conventions (matching the Rust agents):
 *   - Guard on secrets — no-op cleanly when LANGFUSE_SECRET_KEY is unset
 *   - Never throw — warnings only, agent continues without tracing
 *   - Advisory — tracing failure does not block the agent
 *
 * GENESIS_SEAL: 7c242080
 */

import { Langfuse } from "langfuse";
import type { LangfuseTraceClient, LangfuseGenerationClient } from "langfuse";

// ── Configuration ───────────────────────────────────────────────────────────

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

// ── Lazy client (created once, guarded) ─────────────────────────────────────

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

// ── Tracing API ─────────────────────────────────────────────────────────────

export interface LlmCallTrace {
  /** Model ID (e.g. "anthropic/claude-opus-4-8-fast") */
  model: string;
  /** User/agent prompt */
  input: string;
  /** Model response */
  output: string;
  /** Input tokens */
  promptTokens: number;
  /** Output tokens */
  completionTokens: number;
  /** USD cost */
  cost?: number;
  /** Latency in ms */
  latencyMs?: number;
  /** Provider (always "openrouter") */
  provider?: string;
  /** Agent name (e.g. "vaked-orcli", "pr-review") */
  agentName?: string;
  /** OpenRouter generation ID (for trace linking) */
  generationId?: string;
}

/**
 * Trace a single LLM call to Langfuse.
 *
 * Guards on LANGFUSE_SECRET_KEY — no-op when unset.
 * Never throws — failure logs a warning and returns null.
 *
 * @returns The generation client if tracing succeeded, null otherwise.
 */
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

/**
 * Flush pending traces. Call before process exit for short-lived agents.
 * Guards — no-op when tracing is disabled.
 */
export async function flushLangfuse(): Promise<void> {
  const client = getClient();
  if (!client) return;
  try {
    await client.shutdownAsync();
  } catch {
    // Silently ignore — best-effort flush
  }
}

/**
 * Check if Langfuse tracing is active.
 */
export function isLangfuseEnabled(): boolean {
  return getClient() !== null;
}

// ── Higher-level: trace a callModel result ──────────────────────────────────

/**
 * Trace an OpenRouter callModel response.
 * Extracts model, usage, and content from the SDK response shape.
 */
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
