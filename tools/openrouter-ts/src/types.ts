import type { Tool } from "@openrouter/agent";

/** Model catalog — mirrors tools/openrouter/cli.py MODELS + COSTS */
export interface ModelEntry {
  id: string;
  label: string;
  /** USD per 1M prompt tokens */
  promptCost: number;
  /** USD per 1M completion tokens */
  completionCost: number;
}

export const MODELS: Record<string, ModelEntry> = {
  deepseek: {
    id: "deepseek/deepseek-v4-pro",
    label: "DeepSeek V4 Pro",
    promptCost: 0.27,
    completionCost: 0.27,
  },
  claude: {
    id: "anthropic/claude-opus-4-8-fast",
    label: "Claude Opus 4.8",
    promptCost: 15.0,
    completionCost: 75.0,
  },
  gemini: {
    id: "google/gemini-2.5-flash",
    label: "Gemini 2.5 Flash",
    promptCost: 0.15,
    completionCost: 0.6,
  },
  qwen: {
    id: "qwen/qwen3-235b-a22b-thinking",
    label: "Qwen3 235B Thinking",
    promptCost: 2.5,
    completionCost: 5.0,
  },
  llama: {
    id: "meta-llama/llama-4-maverick",
    label: "Llama 4 Maverick",
    promptCost: 0.2,
    completionCost: 0.6,
  },
  haiku: {
    id: "anthropic/claude-haiku-4-5",
    label: "Claude Haiku 4.5",
    promptCost: 0.25,
    completionCost: 1.25,
  },
};

export interface ChatOptions {
  model?: string;
  system?: string;
  maxTokens?: number;
  stream?: boolean;
  tools?: Tool[];
  maxToolRounds?: number;
}

export interface ChatResult {
  content: string;
  model: string;
  promptTokens: number;
  completionTokens: number;
  cost: number;
  reasoningContent?: string;
}

export interface BudgetState {
  remaining: number;
  spent: number;
  cap: number;
}

/** Deliberation panel model — 20-model spectrum */
export interface PanelModel {
  id: string;
  name: string;
  promptCost: number;
  completionCost: number;
}

export const PANEL_MODELS: PanelModel[] = [
  { id: "anthropic/claude-opus-4-8-fast", name: "Claude Opus 4.8", promptCost: 15, completionCost: 75 },
  { id: "google/gemini-2.5-pro", name: "Gemini 2.5 Pro", promptCost: 1.25, completionCost: 5 },
  { id: "anthropic/claude-sonnet-4-6", name: "Claude Sonnet 4.6", promptCost: 3, completionCost: 15 },
  { id: "google/gemini-2.5-flash", name: "Gemini 2.5 Flash", promptCost: 0.15, completionCost: 0.6 },
  { id: "deepseek/deepseek-v4-pro", name: "DeepSeek V4", promptCost: 0.27, completionCost: 0.27 },
  { id: "qwen/qwen3-235b-a22b-thinking", name: "Qwen3 235B", promptCost: 2.5, completionCost: 5 },
  { id: "meta-llama/llama-4-maverick", name: "Llama 4 Maverick", promptCost: 0.2, completionCost: 0.6 },
  { id: "anthropic/claude-opus-4-7-fast", name: "Claude Opus 4.7", promptCost: 15, completionCost: 75 },
  { id: "anthropic/claude-haiku-4-5", name: "Claude Haiku 4.5", promptCost: 0.25, completionCost: 1.25 },
  { id: "google/gemini-2.0-flash", name: "Gemini 2.0 Flash", promptCost: 0.15, completionCost: 0.6 },
  { id: "mistralai/mistral-large", name: "Mistral Large", promptCost: 2, completionCost: 6 },
  { id: "cohere/command-r-plus", name: "Command R+", promptCost: 2.5, completionCost: 10 },
  { id: "deepseek/deepseek-chat", name: "DeepSeek Chat", promptCost: 0.14, completionCost: 0.28 },
  { id: "google/gemma-3-27b", name: "Gemma 3 27B", promptCost: 0.15, completionCost: 0.15 },
  { id: "meta-llama/llama-4-scout", name: "Llama 4 Scout", promptCost: 0.1, completionCost: 0.3 },
  { id: "qwen/qwen-2.5-72b", name: "Qwen 2.5 72B", promptCost: 0.35, completionCost: 0.4 },
  { id: "mistralai/mistral-small", name: "Mistral Small", promptCost: 1, completionCost: 3 },
  { id: "anthropic/claude-haiku-3-5", name: "Claude Haiku 3.5", promptCost: 0.8, completionCost: 4 },
  { id: "openai/gpt-4.1-mini", name: "GPT-4.1 Mini", promptCost: 0.15, completionCost: 0.6 },
  { id: "google/gemini-flash-1.5", name: "Gemini Flash 1.5", promptCost: 0.075, completionCost: 0.3 },
];

export const JUDGE_MODEL = "anthropic/claude-opus-4-8-fast";
