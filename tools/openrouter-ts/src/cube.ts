"use strict";
/**
import { tool } from "@openrouter/agent";
import type { Tool } from "@openrouter/agent";
import { z } from "zod";
const CUBE_URL = process.env["CUBE_API_URL"] ?? "http://localhost:4000/cubejs-api/v1";
interface CubeQueryResult {
  query: Record<string, unknown>;
  data: Array<Record<string, unknown>>;
  annotation: Record<string, unknown>;
}
async function cubeQuery(auth: string, measures: string[], dimensions: string[], filters?: Array<{ member: string; operator: string; values: string[] }>): Promise<CubeQueryResult> {
  const body = {
    measures,
    dimensions,
    filters: filters ?? [],
    limit: 100,
  };
  const res = await fetch(`${CUBE_URL}/load`, {
    method: "POST",
    headers: {
      "Authorization": auth,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`Cube HTTP ${res.status}`);
  return res.json() as Promise<CubeQueryResult>;
}
const queryInput = z.object({
  measures: z.array(z.string()).describe("Metrics to query, e.g. ['Orders.count', 'Orders.totalAmount']"),
  dimensions: z.array(z.string()).describe("Dimensions to group by, e.g. ['Orders.status', 'Orders.createdAt']"),
  filter: z.string().optional().describe("Optional filter as JSON array"),
});
export function createCubeTools(): Tool[] {
  return [
    tool({
      name: "cube_query",
      description: "Query the Cube semantic layer for deterministic, version-controlled metrics. Agents should use this instead of querying raw databases. Returns pre-aggregated, governed data.",
      inputSchema: queryInput,
      execute: async (params) => {
        try {
          const auth = `Bearer ${process.env["CUBE_API_SECRET"] ?? ""}`;
          const filter = params.filter ? JSON.parse(params.filter) : undefined;
          const result = await cubeQuery(auth, params.measures, params.dimensions, filter);
          if (result.data.length === 0) return "No data returned from Cube semantic layer.";
          return `## Cube Semantic Query\n\nMeasures: ${params.measures.join(", ")}\nDimensions: ${params.dimensions.join(", ")}\nRows: ${result.data.length}\n\n${JSON.stringify(result.data.slice(0, 10), null, 2)}\n\n> Data from Cube — deterministic, version-controlled, governed.`;
        } catch (err) {
          return `Cube error: ${err instanceof Error ? err.message : String(err)}`;
        }
      },
    }),
    tool({
      name: "cube_meta",
      description: "List available Cube measures and dimensions — discover what data the agents can query.",
      inputSchema: z.object({}),
      execute: async () => {
        try {
          const res = await fetch(`${CUBE_URL}/meta`, {
            headers: { "Authorization": `Bearer ${process.env["CUBE_API_SECRET"] ?? ""}` },
          });
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          const data = await res.json();
          const cubes = (data as any).cubes ?? [];
          return `## Cube Data Model\n\n${cubes.map((c: any) => `### ${c.name}\nMeasures: ${(c.measures ?? []).map((m: any) => m.name).join(", ")}\nDimensions: ${(c.dimensions ?? []).map((d: any) => d.name).join(", ")}`).join("\n\n")}`;
        } catch (err) {
          return `Cube error: ${err instanceof Error ? err.message : String(err)}`;
        }
      },
    }),
  ];
}
export function cubeSystemPrompt(): string {
  return [
    "## Cube — Semantic Layer (World Model)",
    "",
    "When making data-driven decisions, query Cube instead of raw databases.",
    "Cube provides deterministic, version-controlled, governed metrics.",
    "Use cube_meta to discover available data. Use cube_query to fetch metrics.",
    "Cube handles pre-aggregation, caching, and access control.",
    "Never query raw DBs directly — go through Cube for audited data.",
  ].join("\n");
}