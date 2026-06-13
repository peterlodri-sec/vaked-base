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
export interface RFNodeData {
  vakedNode: VakedNode;
  highlighted: boolean;  // true when its provenance span is active in Editor
  hasErrors: boolean;
}

export interface RFEdgeData {
  vakedEdge: VakedEdge;
  semantics: EdgeSemantics;
}

export const EMPTY_GRAPH: VakedGraph = { nodes: [], edges: [] };
