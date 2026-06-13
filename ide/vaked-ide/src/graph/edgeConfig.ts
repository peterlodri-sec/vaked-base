import type { EdgeSemantics, VakedEdge, VakedNode } from "@/types/graph";

export interface EdgeStyle {
  stroke: string;
  strokeWidth: number;
  strokeDasharray?: string;
  animated: boolean;
  markerEnd: string;
  label?: string;
}

const DOMAIN_COLORS: Record<string, string> = {
  fs:      "#16a34a",
  network: "#2563eb",
  mcp:     "#7c3aed",
  ebpf:    "#dc2626",
  process: "#ea580c",
  mem:     "#0891b2",
};

export function classifyEdgeSemantic(
  edge: VakedEdge,
  nodesById: Map<string, VakedNode>
): EdgeSemantics {
  const { label } = edge;
  if (label === "routes_to") return "mesh_delegation";
  if (label === "contains" || label === "member_of") return "structural";
  if (label === "requires_capability") return "capability_req";

  // workflow ordering: both endpoints are workflowStep nodes
  const src = nodesById.get(edge.from);
  const tgt = nodesById.get(edge.to);
  if (
    label === "depends_on" &&
    src?.kind === "workflowStep" &&
    tgt?.kind === "workflowStep"
  ) {
    return "workflow_ordering";
  }

  return "data_flow";
}

export function getEdgeStyle(semantics: EdgeSemantics, edge: VakedEdge): EdgeStyle {
  switch (semantics) {
    case "mesh_delegation":
      return {
        stroke: "#f97316",
        strokeWidth: 2,
        animated: true,
        markerEnd: "url(#arrow-mesh)",
      };
    case "workflow_ordering":
      return {
        stroke: "#ca8a04",
        strokeWidth: 2,
        strokeDasharray: "6 3",
        animated: false,
        markerEnd: "url(#arrow-workflow)",
      };
    case "capability_req": {
      const domain = String(edge.props?.domain ?? "");
      const color = DOMAIN_COLORS[domain] ?? "#6b7280";
      return {
        stroke: color,
        strokeWidth: 1.5,
        strokeDasharray: "3 3",
        animated: false,
        markerEnd: "url(#arrow-cap)",
      };
    }
    case "data_flow":
      return {
        stroke: "#6b7280",
        strokeWidth: 1.5,
        strokeDasharray: "4 2",
        animated: false,
        markerEnd: "url(#arrow-data)",
      };
    case "structural":
    default:
      return {
        stroke: "#374151",
        strokeWidth: 1,
        animated: false,
        markerEnd: "url(#arrow-struct)",
      };
  }
}

// Edges that should NOT be rendered as visual edges (they drive grouping instead)
export const STRUCTURAL_EDGE_LABELS = new Set(["contains"]);
