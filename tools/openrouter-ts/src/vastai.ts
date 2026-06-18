"use strict";

/**
 * vastai — GPU cloud integration for the Vaked swarm.
 *
 * HTTP 200 → authoritative. VAST_API_KEY from CI secrets.
 * Agent tools: search offers, launch/stop/destroy instances, check status.
 *
 * API: https://console.vast.ai/api/v0/
 * Docs: https://cloud.vast.ai/cli/
 *
 * GENESIS_SEAL: 7c242080
 */

import { tool } from "@openrouter/agent";
import type { Tool } from "@openrouter/agent";
import { z } from "zod";

const BASE = "https://console.vast.ai/api/v0";

function getApiKey(): string {
  const key = process.env["VAST_API_KEY"];
  if (!key) throw new Error("VAST_API_KEY not set. Get one at https://cloud.vast.ai/manage-keys");
  return key;
}

// ═══════════════════════════════════════════════════════════════════
// HTTP client
// ═══════════════════════════════════════════════════════════════════

async function api<T>(method: string, path: string, body?: unknown): Promise<T> {
  const url = `${BASE}${path}`;
  const headers: Record<string, string> = {
    "Authorization": `Bearer ${getApiKey()}`,
    "Content-Type": "application/json",
    "User-Agent": "vaked-vastai/0.1",
  };

  const res = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });

  if (res.status >= 200 && res.status < 300) {
    const text = await res.text();
    if (!text.trim()) return {} as T;
    return JSON.parse(text) as T;
  }

  const errBody = await res.text().catch(() => "");
  throw new Error(`Vast.ai HTTP ${res.status}: ${errBody.slice(0, 300)}`);
}

// ═══════════════════════════════════════════════════════════════════
// Types
// ═══════════════════════════════════════════════════════════════════

export interface GpuOffer {
  id: number;
  gpu_name: string;
  num_gpus: number;
  gpu_ram: number;
  cpu_ram: number;
  disk_space: number;
  dph_total: number;   // dollars per hour
  dlperf: number;
  inet_up: number;
  inet_down: number;
  geolocation: string;
  verified: boolean;
}

export interface Instance {
  id: number;
  machine_id: number;
  gpu_name: string;
  actual_status: string;
  ssh_host: string;
  ssh_port: number;
  dph_total: number;
  image: string;
  disk_space: number;
}

export interface SearchResult {
  offers: GpuOffer[];
}

export interface InstancesResult {
  instances: Instance[];
}

// ═══════════════════════════════════════════════════════════════════
// Standalone API (mirrors Python SDK)
// ═══════════════════════════════════════════════════════════════════

export async function searchOffers(query: string, limit = 5): Promise<GpuOffer[]> {
  const result = await api<SearchResult>("GET", `/bundles/?q=${encodeURIComponent(query)}&limit=${limit}`);
  return result.offers ?? [];
}

export async function showInstances(): Promise<Instance[]> {
  const result = await api<InstancesResult>("GET", "/instances/");
  return result.instances ?? [];
}

export async function createInstance(offerId: number, opts: {
  image?: string;
  disk?: number;
  ssh?: boolean;
} = {}): Promise<{ instance_id: number }> {
  return api("POST", "/asks/", {
    client_id: "vaked-swarm",
    image: opts.image ?? "pytorch/pytorch",
    disk: opts.disk ?? 32,
    extra: opts.ssh !== false ? " -p 22:22" : "",
    ask_contract_id: offerId,
  });
}

export async function destroyInstance(id: number): Promise<void> {
  await api("DELETE", `/instances/${id}/`);
}

export async function startInstance(id: number): Promise<void> {
  await api("PUT", `/instances/${id}/`, { actual_status: "running" });
}

export async function stopInstance(id: number): Promise<void> {
  await api("PUT", `/instances/${id}/`, { actual_status: "stopped" });
}

// ═══════════════════════════════════════════════════════════════════
// Agent tools
// ═══════════════════════════════════════════════════════════════════

const searchInput = z.object({
  query: z.string().describe("Filter: e.g. 'gpu_name=RTX_4090 num_gpus=1'"),
  limit: z.number().optional().default(5).describe("Max results"),
});

const createInput = z.object({
  offerId: z.number().describe("Offer ID from search"),
  image: z.string().optional().default("pytorch/pytorch").describe("Docker image"),
  disk: z.number().optional().default(32).describe("Disk GB"),
});

const instanceInput = z.object({
  instanceId: z.number().describe("Instance ID"),
});

export function createVastaiTools(): Tool[] {
  return [
    tool({
      name: "vastai_search",
      description: "Search Vast.ai for GPU offers. Filter by GPU name, count, price. Returns cheapest offers first.",
      inputSchema: searchInput,
      execute: async (params) => {
        try {
          const offers = await searchOffers(params.query, params.limit);
          if (offers.length === 0) return "No GPU offers found.";
          return "## Vast.ai GPU Offers\n\n" + offers.map((o) =>
            `- **${o.gpu_name}** ×${o.num_gpus} — ${o.gpu_ram}GB VRAM · ${o.disk_space}GB disk · **$${o.dph_total.toFixed(2)}/hr** · ${o.geolocation} · id:${o.id}`
          ).join("\n");
        } catch (err) {
          return `Vast.ai error: ${err instanceof Error ? err.message : String(err)}`;
        }
      },
    }),

    tool({
      name: "vastai_launch",
      description: "Launch a GPU instance on Vast.ai. Returns instance ID for tracking.",
      inputSchema: createInput,
      execute: async (params) => {
        try {
          const result = await createInstance(params.offerId, { image: params.image, disk: params.disk });
          return `GPU instance launched. ID: ${result.instance_id}. Check status with vastai_status. Cost: ~$${params.disk ? "varies" : "see offer"}/hr.`;
        } catch (err) {
          return `Vast.ai error: ${err instanceof Error ? err.message : String(err)}`;
        }
      },
    }),

    tool({
      name: "vastai_status",
      description: "Check status of all Vast.ai GPU instances.",
      inputSchema: z.object({}),
      execute: async () => {
        try {
          const instances = await showInstances();
          if (instances.length === 0) return "No running GPU instances.";
          return "## Vast.ai Instances\n\n" + instances.map((i) =>
            `- **#${i.id}** — ${i.gpu_name} — ${i.actual_status} — $${i.dph_total.toFixed(2)}/hr — ${i.ssh_host}:${i.ssh_port}`
          ).join("\n");
        } catch (err) {
          return `Vast.ai error: ${err instanceof Error ? err.message : String(err)}`;
        }
      },
    }),

    tool({
      name: "vastai_destroy",
      description: "Destroy a Vast.ai GPU instance. Stops billing immediately.",
      inputSchema: instanceInput,
      execute: async (params) => {
        try {
          await destroyInstance(params.instanceId);
          return `Instance #${params.instanceId} destroyed. Billing stopped.`;
        } catch (err) {
          return `Vast.ai error: ${err instanceof Error ? err.message : String(err)}`;
        }
      },
    }),
  ];
}

// ═══════════════════════════════════════════════════════════════════
// System prompt fragment
// ═══════════════════════════════════════════════════════════════════

export function vastaiSystemPrompt(): string {
  return [
    "## Vast.ai — GPU Cloud",
    "",
    "You have access to Vast.ai GPU cloud tools:",
    "- **vastai_search**: Find GPU offers by name, count, price",
    "- **vastai_launch**: Start a GPU instance (starts billing!)",
    "- **vastai_status**: Check running instances",
    "- **vastai_destroy**: Stop and destroy an instance (stops billing)",
    "",
    "Always confirm with the user before launching or destroying instances.",
    "Default image: pytorch/pytorch. Default disk: 32GB.",
  ].join("\n");
}
