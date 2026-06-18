"use strict";
import { homedir } from "node:os";
import { join } from "node:path";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import type { BudgetState } from "./types.js";
const BUDGET_FILE = join(homedir(), ".orcli_budget");
const DEFAULT_BUDGET = 6.0;
export function readBudget(): BudgetState {
  try {
    if (existsSync(BUDGET_FILE)) {
      const remaining = parseFloat(readFileSync(BUDGET_FILE, "utf-8").trim());
      return {
        remaining,
        spent: DEFAULT_BUDGET - remaining,
        cap: DEFAULT_BUDGET,
      };
    }
  } catch {
  }
  return { remaining: DEFAULT_BUDGET, spent: 0, cap: DEFAULT_BUDGET };
}
export function writeBudget(remaining: number): void {
  writeFileSync(BUDGET_FILE, remaining.toFixed(4));
}
export function trackCost(
  promptTokens: number,
  completionTokens: number,
  promptCostPerM: number,
  completionCostPerM: number,
): BudgetState {
  const cost =
    (promptTokens * promptCostPerM) / 1_000_000 +
    (completionTokens * completionCostPerM) / 1_000_000;
  const current = readBudget();
  const remaining = current.remaining - cost;
  writeBudget(remaining);
  return {
    remaining,
    spent: current.spent + cost,
    cap: current.cap,
  };
}
export function formatBudget(state: BudgetState): string {
  return `$${state.remaining.toFixed(4)} remaining · $${state.spent.toFixed(4)} spent · cap $${state.cap.toFixed(2)}`;
}
export function affordableTokens(
  promptCostPerM: number,
  completionCostPerM: number,
): number {
  const { remaining } = readBudget();
  if (remaining <= 0) return 0;
  return Math.floor((remaining / completionCostPerM) * 1_000_000);
}