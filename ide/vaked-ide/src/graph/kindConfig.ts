export interface KindConfig {
  color: string;
  bg: string;
  border: string;
  label: string;
  icon: string;
  shape: "default" | "diamond" | "rounded";
}

const cfg = (color: string, bg: string, border: string, label: string, icon: string, shape: KindConfig["shape"] = "default"): KindConfig =>
  ({ color, bg, border, label, icon, shape });

export const KIND_CONFIG: Record<string, KindConfig> = {
  runtime:       cfg("#fff", "#7c3aed", "#6d28d9", "Runtime",        "⚡", "rounded"),
  index:         cfg("#fff", "#0d9488", "#0f766e", "Index",           "📚"),
  catalog:       cfg("#fff", "#0891b2", "#0e7490", "Catalog",         "📂"),
  stream:        cfg("#fff", "#2563eb", "#1d4ed8", "Stream",          "〰"),
  fiber:         cfg("#fff", "#ea580c", "#c2410c", "Fiber",           "🔧"),
  surface:       cfg("#fff", "#16a34a", "#15803d", "Surface",         "🖥", "rounded"),
  mesh:          cfg("#fff", "#dc2626", "#b91c1c", "Mesh",            "🕸", "rounded"),
  workflow:      cfg("#fff", "#ca8a04", "#a16207", "Workflow",        "🔀", "rounded"),
  parallel:      cfg("#fff", "#d97706", "#b45309", "Parallel",        "⧖"),
  schema:        cfg("#fff", "#7c3aed", "#6d28d9", "Schema",          "📋"),
  capability:    cfg("#fff", "#db2777", "#be185d", "Capability",      "🔑"),
  memory:        cfg("#fff", "#4f46e5", "#4338ca", "Memory",          "🧠"),
  device:        cfg("#fff", "#6b7280", "#4b5563", "Device",          "💾"),
  mediaPipeline: cfg("#fff", "#65a30d", "#4d7c0f", "MediaPipeline",  "🎬"),
  budget:        cfg("#fff", "#0284c7", "#0369a1", "Budget",          "💰"),
  runclass:      cfg("#fff", "#6d28d9", "#5b21b6", "RunClass",        "🏷"),
  service:       cfg("#fff", "#059669", "#047857", "Service",         "⚙"),
  secret:        cfg("#fff", "#9f1239", "#881337", "Secret",          "🔐"),
  hostResource:  cfg("#fff", "#7c2d12", "#6c2310", "HostResource",    "🗄"),
  ingress:       cfg("#fff", "#1e40af", "#1e3a8a", "Ingress",         "🚪"),
  container:     cfg("#fff", "#075985", "#0c4a6e", "Container",       "📦"),
  engine:        cfg("#fff", "#831843", "#701a75", "Engine",          "🔩"),
  input:         cfg("#fff", "#134e4a", "#042f2e", "Input",           "📥"),
  host:          cfg("#fff", "#1c1917", "#0c0a09", "Host",            "🖧"),
  network:       cfg("#fff", "#0f172a", "#020617", "Network",         "🌐"),
  filesystem:    cfg("#fff", "#1a2e05", "#1a2e05", "Filesystem",      "📁"),
  mcp:           cfg("#fff", "#2e1065", "#1e0a5c", "MCP",             "🔌"),
  ebpf:          cfg("#fff", "#1e3a5f", "#142742", "eBPF",            "🔎"),
  observability: cfg("#fff", "#052e16", "#071a0e", "Observability",   "📊"),
  // External/stub nodes
  external:      cfg("#fff", "#374151", "#1f2937", "External",        "◇"),
};

export const DEFAULT_KIND_CONFIG: KindConfig = cfg(
  "#fff", "#374151", "#1f2937", "Node", "◆"
);

export function getKindConfig(kind: string): KindConfig {
  return KIND_CONFIG[kind] ?? DEFAULT_KIND_CONFIG;
}
