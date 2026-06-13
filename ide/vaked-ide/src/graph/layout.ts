import type { Node, Edge } from "@xyflow/react";
import type { RFNodeData } from "@/types/graph";
import ELK from "elkjs/lib/elk.bundled.js";

const elk = new ELK();

const ELK_OPTIONS = {
  "elk.algorithm": "layered",
  "elk.direction": "RIGHT",
  "elk.layered.spacing.nodeNodeBetweenLayers": "100",
  "elk.spacing.nodeNode": "60",
  "elk.padding": "[top=40, left=40, bottom=40, right=40]",
};

export async function applyElkLayout(
  nodes: Node<RFNodeData>[],
  edges: Edge[]
): Promise<Node<RFNodeData>[]> {
  const elkNodes = nodes.map((n) => ({
    id: n.id,
    width: 180,
    height: 60,
    ...(n.parentId ? { parent: n.parentId } : {}),
  }));

  const elkEdges = edges.map((e) => ({
    id: e.id,
    sources: [e.source],
    targets: [e.target],
  }));

  try {
    const graph = await elk.layout({
      id: "root",
      layoutOptions: ELK_OPTIONS,
      children: elkNodes,
      edges: elkEdges,
    });

    const posMap = new Map<string, { x: number; y: number }>();
    for (const child of graph.children ?? []) {
      posMap.set(child.id, { x: child.x ?? 0, y: child.y ?? 0 });
    }

    return nodes.map((n) => ({
      ...n,
      position: posMap.get(n.id) ?? n.position,
    }));
  } catch {
    return nodes;
  }
}
