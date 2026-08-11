// Mirrors vakedc/graph.py — the canonical LPG types from vakedc parse --print

export interface VakedSpan {
  byteStart: number;
  byteEnd: number;
  line: number;   // 1-based
  col: number;    // 1-based
}

export interface VakedProvenance {
  file: string;
  decl: string;  // "<kind> <name>"
  span: VakedSpan;
}

export type EdgeLabel =
  | "contains"
  | "imports"
  | "depends_on"
  | "requires_capability"
  | "routes_to"
  | "member_of";

export type EdgeSemantics =
  | "mesh_delegation"    // routes_to between non-workflowStep nodes
  | "workflow_ordering"  // depends_on between workflowStep nodes
  | "structural"         // contains, member_of
  | "data_flow"          // imports, depends_on (non-workflow)
  | "capability_req";    // requires_capability

export interface VakedNode {
  id: string;
  kind: string;
  name: string;
  labels: string[];
  props: Record<string, unknown>;
  provenance: VakedProvenance | null;
}

export interface VakedEdge {
  from: string;
  to: string;
  label: EdgeLabel;
  props: Record<string, unknown>;
}

export interface VakedGraph {
  version?: number;
  source?: string;
  nodes: VakedNode[];
  edges: VakedEdge[];
}

// ReactFlow-adapted data shapes (produced by graph/adapter.ts)
export interface RFNodeData extends Record<string, unknown> {
  vakedNode: VakedNode;
  highlighted: boolean;  // true when its provenance span is active in Editor
  hasErrors: boolean;
}

export interface RFEdgeData extends Record<string, unknown> {
  vakedEdge: VakedEdge;
  semantics: EdgeSemantics;
}

export const EMPTY_GRAPH: VakedGraph = { nodes: [], edges: [] };

export const CONSTELLATION_GRAPH: VakedGraph = {
  version: 1,
  source: "vaked.dev constellation network",
  nodes: [
    { id: "art", kind: "service", name: "art.vaked.dev", labels: ["constellation", "gallery"], props: { url: "https://art.vaked.dev/" }, provenance: null },
    { id: "vision", kind: "service", name: "vision-gallery (23)", labels: ["constellation", "artworks"], props: { url: "https://art.vaked.dev/vision-gallery.html" }, provenance: null },
    { id: "music", kind: "service", name: "music.vaked.dev", labels: ["constellation", "audio-node"], props: { url: "https://music.vaked.dev/" }, provenance: null },
    { id: "quant-love", kind: "service", name: "mlxquantlovefrom.com", labels: ["constellation", "bitnet-b158"], props: { url: "https://mlxquantlovefrom.com/" }, provenance: null },
    { id: "proposal", kind: "service", name: "proposal.vaked.dev", labels: ["constellation", "a2a-router"], props: { url: "https://proposal.vaked.dev/" }, provenance: null },
    { id: "pocoo", kind: "service", name: "pocoo.vaked.dev", labels: ["constellation", "ai-engine"], props: { url: "https://pocoo.vaked.dev/" }, provenance: null },
    { id: "axiomquant", kind: "service", name: "axiomquant.org", labels: ["constellation", "monographs"], props: { url: "https://axiomquant.org/" }, provenance: null },
    { id: "portail", kind: "gateway", name: "portail.vaked.dev", labels: ["constellation", "rust-gateway"], props: { url: "https://portail.vaked.dev/" }, provenance: null },
  ],
  edges: [
    { from: "portail", to: "art", label: "routes_to", props: {} },
    { from: "portail", to: "music", label: "routes_to", props: {} },
    { from: "portail", to: "quant-love", label: "routes_to", props: {} },
    { from: "portail", to: "proposal", label: "routes_to", props: {} },
    { from: "portail", to: "pocoo", label: "routes_to", props: {} },
    { from: "portail", to: "axiomquant", label: "routes_to", props: {} },
    { from: "art", to: "vision", label: "contains", props: {} },
    { from: "quant-love", to: "axiomquant", label: "depends_on", props: {} },
  ]
};
