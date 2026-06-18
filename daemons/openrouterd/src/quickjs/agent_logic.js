// ═══════════════════════════════════════════════════════════════
// Vaked Agent Logic — runs in QuickJS, called from Zig daemon
// Pure logic only — no network I/O (Zig handles all HTTP/TLS)
// ═══════════════════════════════════════════════════════════════

// ── Conductor: model self-selection ──────────────────────────

const CODE_KEYWORDS = ["code", "write", "implement", "fix", "debug", "test", "refactor", "optimize", "review"];
const CREATIVE_KEYWORDS = ["creative", "brainstorm", "design", "story"];
const DEFAULT_MODEL = "deepseek/deepseek-v4-pro";
const CODE_MODEL = "anthropic/claude-opus-4-8-fast";
const CREATIVE_MODEL = "google/gemini-2.5-flash";

function routeModel(prompt) {
  if (!prompt) return DEFAULT_MODEL;
  const lower = prompt.toLowerCase();
  for (const kw of CODE_KEYWORDS) {
    if (lower.includes(kw)) return CODE_MODEL;
  }
  for (const kw of CREATIVE_KEYWORDS) {
    if (lower.includes(kw)) return CREATIVE_MODEL;
  }
  return DEFAULT_MODEL;
}

// ── Context7: API pattern detection ──────────────────────────

const API_PATTERNS = [
  [/\b(std\.Build|zig build|zig\s+0\.\d+)/i, "zig"],
  [/\b(nixpkgs|nixos|nix develop|nix build|nix flake)/i, "nixpkgs"],
  [/\b(tauri|@tauri-apps)/i, "tauri"],
  [/\b(useState|useEffect|JSX|React\.)/i, "react"],
  [/\b(cloudflare|wrangler|workers|DurableObject)/i, "cloudflare"],
  [/\b(node:fs|node:path|node\.js)/i, "nodejs"],
  [/\b(serde|tokio|cargo build)/i, "rust"],
  [/\b(eBPF|bpf\b|XDP)/i, "ebpf"],
];

function detectLibraries(prompt) {
  const found = [];
  for (const [pattern, lib] of API_PATTERNS) {
    if (pattern.test(prompt) && !found.includes(lib)) {
      found.push(lib);
    }
  }
  return found.slice(0, 3);
}

// ── Budget: in-memory tracking ──────────────────────────────

let budget_remaining = 6.00;

function trackCost(promptTokens, completionTokens, promptCostPerM, completionCostPerM) {
  const cost = (promptTokens * promptCostPerM + completionTokens * completionCostPerM) / 1_000_000;
  budget_remaining -= cost;
  return budget_remaining;
}

function getBudget() { return budget_remaining; }

// ── Model catalog ───────────────────────────────────────────

const MODELS = {
  "deepseek":      { id: "deepseek/deepseek-v4-pro",        prompt: 0.27, comp: 0.27 },
  "claude":        { id: "anthropic/claude-opus-4-8-fast",   prompt: 15.0, comp: 75.0 },
  "gemini":        { id: "google/gemini-2.5-flash",           prompt: 0.15, comp: 0.60 },
  "qwen":          { id: "qwen/qwen3-235b-a22b-thinking",    prompt: 2.50, comp: 5.00 },
  "llama":         { id: "meta-llama/llama-4-maverick",       prompt: 0.20, comp: 0.60 },
  "haiku":         { id: "anthropic/claude-haiku-4-5",        prompt: 0.25, comp: 1.25 },
};

// ── Export for Zig FFI ──────────────────────────────────────

// These functions are called from Zig via QuickJS C API
// Each returns a JSON string that Zig parses

globalThis._routeModel = function(prompt) {
  return JSON.stringify({ model: routeModel(prompt) });
};

globalThis._detectLibraries = function(prompt) {
  return JSON.stringify({ libraries: detectLibraries(prompt) });
};

globalThis._trackCost = function(promptTokens, completionTokens, modelAlias) {
  const m = MODELS[modelAlias] || { prompt: 0, comp: 0 };
  const remaining = trackCost(promptTokens, completionTokens, m.prompt, m.comp);
  return JSON.stringify({ remaining: remaining.toFixed(4) });
};

globalThis._getBudget = function() {
  return JSON.stringify({ remaining: budget_remaining.toFixed(4) });
};

globalThis._resolveModel = function(alias) {
  const m = MODELS[alias];
  return m ? JSON.stringify(m) : JSON.stringify({ id: alias, prompt: 0, comp: 0 });
};

globalThis._listModels = function() {
  return JSON.stringify(Object.entries(MODELS).map(([k, v]) => ({ alias: k, ...v })));
};
