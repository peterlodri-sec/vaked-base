import type { Node, Edge } from "@xyflow/react";
import type { VakedGraph, VakedNode, VakedEdge, RFNodeData, RFEdgeData } from "@/types/graph";
import { classifyEdgeSemantic, STRUCTURAL_EDGE_LABELS } from "./edgeConfig";

export interface AdapterResult {
  nodes: Node<RFNodeData>[];
  edges: Edge<RFEdgeData>[];
}

export function lpgToReactFlow(
  graph: VakedGraph,
  errorNodeIds: Set<string> = new Set()
): AdapterResult {
  const nodesById = new Map<string, VakedNode>(
    graph.nodes.map((n) => [n.id, n])
  );

  // Build parent map from `contains` edges
  const parentOf = new Map<string, string>();
  for (const edge of graph.edges) {
    if (edge.label === "contains") {
      parentOf.set(edge.to, edge.from);
    }
  }

  // Identify "root" nodes that have no parent (or parent is external)
  const rfNodes: Node<RFNodeData>[] = graph.nodes
    .filter((n) => n.kind !== "external")
    .map((vn, idx) => {
      const parent = parentOf.get(vn.id);
      // Stagger initial positions until ELK layout runs
      const x = (idx % 5) * 220;
      const y = Math.floor(idx / 5) * 140;

      const node: Node<RFNodeData> = {
        id: vn.id,
        type: "vakedNode",
        position: { x, y },
        data: {
          vakedNode: vn,
          highlighted: false,
          hasErrors: errorNodeIds.has(vn.id),
        },
        ...(parent && nodesById.has(parent) && nodesById.get(parent)?.kind !== "external"
          ? { parentId: parent, extent: "parent" as const }
          : {}),
      };
      return node;
    });

  const rfEdges: Edge<RFEdgeData>[] = graph.edges
    .filter((e) => !STRUCTURAL_EDGE_LABELS.has(e.label))
    .filter((e) => nodesById.has(e.from) && nodesById.has(e.to))
    .filter((e) => nodesById.get(e.from)?.kind !== "external" && nodesById.get(e.to)?.kind !== "external")
    .map((ve) => {
      const semantics = classifyEdgeSemantic(ve, nodesById);
      const edge: Edge<RFEdgeData> = {
        id: `${ve.from}→${ve.to}:${ve.label}`,
        source: ve.from,
        target: ve.to,
        type: "vakedEdge",
        label: ve.props?.label as string | undefined,
        data: { vakedEdge: ve, semantics },
      };
      return edge;
    });

  return { nodes: rfNodes, edges: rfEdges };
}

export function highlightNode(
  nodes: Node<RFNodeData>[],
  nodeId: string | null
): Node<RFNodeData>[] {
  return nodes.map((n) => ({
    ...n,
    data: { ...n.data, highlighted: n.id === nodeId },
  }));
}

export function markErrorNodes(
  nodes: Node<RFNodeData>[],
  errorNodeIds: Set<string>
): Node<RFNodeData>[] {
  return nodes.map((n) => ({
    ...n,
    data: { ...n.data, hasErrors: errorNodeIds.has(n.id) },
  }));
}
