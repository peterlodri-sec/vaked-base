"use strict";

/**
 * bao — OpenBao/Vault secrets integration for the Vaked swarm.
 *
 * Secrets never touch the filesystem. Dynamic secrets. Audit logging.
 * Graceful fallback to env vars if Vault is unavailable.
 *
 * API: https://bao.crabcc.app/v1/
 * Auth: VAULT_TOKEN env var (or BAO_TOKEN)
 *
 * GENESIS_SEAL: 7c242080
 */

import { tool } from "@openrouter/agent";
import type { Tool } from "@openrouter/agent";
import { z } from "zod";

const BASE = "https://bao.crabcc.app/v1";

function getToken(): string | null {
  return process.env["VAULT_TOKEN"] ?? process.env["BAO_TOKEN"] ?? null;
}

// ═══════════════════════════════════════════════════════════════════
// HTTP client
// ═══════════════════════════════════════════════════════════════════

async function api<T>(path: string): Promise<T> {
  const token = getToken();
  if (!token) throw new Error("VAULT_TOKEN or BAO_TOKEN not set");

  const res = await fetch(`${BASE}${path}`, {
    headers: {
      "X-Vault-Token": token,
      "User-Agent": "vaked-bao/0.1",
    },
  });

  if (res.status >= 200 && res.status < 300) {
    const json = await res.json();
    return json as T;
  }

  if (res.status === 403) throw new Error("Vault: permission denied");
  if (res.status === 404) throw new Error("Vault: secret not found");
  throw new Error(`Vault HTTP ${res.status}`);
}

// ═══════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════

interface VaultData<T = Record<string, unknown>> {
  data: T;
}

interface VaultList {
  data: { keys: string[] };
}

interface VaultHealth {
  initialized: boolean;
  sealed: boolean;
  standby: boolean;
  version: string;
  cluster_name: string;
}

// ═══════════════════════════════════════════════════════════════════
// API — mirrors vault CLI
// ═══════════════════════════════════════════════════════════════════

export async function health(): Promise<VaultHealth> {
  return api<VaultHealth>("/sys/health");
}

export async function getSecret<T = Record<string, string>>(path: string): Promise<T> {
  const result = await api<VaultData<{ data: T }>>(`/secret/data/${path}`);
  return result.data.data;
}

export async function listSecrets(path: string): Promise<string[]> {
  const result = await api<{ data: { keys: string[] } }>(`/secret/metadata/${path}?list=true`);
  return result.data.keys;
}

/**
 * Resolve a secret — tries Vault first, falls back to env var.
 * This is THE preferred way to get secrets in the Vaked swarm.
 *
 * Priority:
 *   1. OpenBao/Vault (bao.crabcc.app)
 *   2. Environment variable (fallback)
 */
export async function resolveSecret(name: string, envVar: string): Promise<string> {
  try {
    const secret = await getSecret<Record<string, string>>(name);
    const value = secret[name] ?? secret[envVar] ?? secret["value"];
    if (value) return value;
  } catch {
    // Vault unavailable — fall through to env
  }

  const env = process.env[envVar];
  if (env) return env;

  throw new Error(`Secret "${name}" not found in Vault or env var ${envVar}`);
}

// ═══════════════════════════════════════════════════════════════════
// Agent tools
// ═══════════════════════════════════════════════════════════════════

export function createBaoTools(): Tool[] {
  return [
    tool({
      name: "bao_get_secret",
      description: "Fetch a secret from OpenBao/Vault. Returns key-value pairs. Secrets never touch disk.",
      inputSchema: z.object({
        path: z.string().describe("Secret path, e.g. 'openrouter/api-key'"),
      }),
      execute: async (params) => {
        try {
          const data = await getSecret(params.path);
          const keys = Object.keys(data);
          return `## Vault Secret: ${params.path}\n\nKeys: ${keys.join(", ")}\n\nValues hidden for security. Use specific key names to access.`;
        } catch (err) {
          return `Vault error: ${err instanceof Error ? err.message : String(err)}`;
        }
      },
    }),

    tool({
      name: "bao_list_secrets",
      description: "List available secrets at a Vault path.",
      inputSchema: z.object({
        path: z.string().describe("Path prefix, e.g. 'openrouter'"),
      }),
      execute: async (params) => {
        try {
          const keys = await listSecrets(params.path);
          if (keys.length === 0) return `No secrets at ${params.path}.`;
          return `## Vault Secrets: ${params.path}\n\n${keys.map((k) => `- ${k}`).join("\n")}`;
        } catch (err) {
          return `Vault error: ${err instanceof Error ? err.message : String(err)}`;
        }
      },
    }),

    tool({
      name: "bao_health",
      description: "Check OpenBao/Vault health status.",
      inputSchema: z.object({}),
      execute: async () => {
        try {
          const h = await health();
          return `## Vault Health\n\nInitialized: ${h.initialized}\nSealed: ${h.sealed}\nStandby: ${h.standby}\nVersion: ${h.version}\nCluster: ${h.cluster_name}`;
        } catch (err) {
          return `Vault error: ${err instanceof Error ? err.message : String(err)}`;
        }
      },
    }),
  ];
}

// ═══════════════════════════════════════════════════════════════════
// System prompt
// ═══════════════════════════════════════════════════════════════════

export function baoSystemPrompt(): string {
  return [
    "## OpenBao/Vault — Secrets Management",
    "",
    "Secrets are stored in OpenBao at bao.crabcc.app.",
    "The Vaked swarm resolves secrets in this priority order:",
    "  1. Vault (bao.crabcc.app) — dynamic, audited, never touches disk",
    "  2. Environment variable — CI secrets, fallback",
    "",
    "Available tools:",
    "- **bao_get_secret** — Fetch a secret by path",
    "- **bao_list_secrets** — List secrets at a path",
    "- **bao_health** — Check Vault status",
    "",
    "Never log or expose secret values. Keys only in responses.",
  ].join("\n");
}
