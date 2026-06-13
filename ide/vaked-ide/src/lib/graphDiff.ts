import type { VakedGraph } from "@/types/graph";
import type { GraphPatch } from "@/types/session";

export function diffGraphs(prev: VakedGraph, next: VakedGraph): GraphPatch {
  const prevNodeIds = new Set(prev.nodes.map((n) => n.id));
  const nextNodeIds = new Set(next.nodes.map((n) => n.id));

  const addedNodes = next.nodes
    .filter((n) => !prevNodeIds.has(n.id))
    .map((n) => n.id);
  const removedNodes = prev.nodes
    .filter((n) => !nextNodeIds.has(n.id))
    .map((n) => n.id);

  const edgeKey = (e: { from: string; to: string; label: string }) =>
    `${e.from}→${e.to}:${e.label}`;
  const prevEdgeKeys = new Set(prev.edges.map(edgeKey));
  const nextEdgeKeys = new Set(next.edges.map(edgeKey));

  const addedEdges = next.edges
    .filter((e) => !prevEdgeKeys.has(edgeKey(e)))
    .map((e) => ({ from: e.from, to: e.to, label: e.label }));
  const removedEdges = prev.edges
    .filter((e) => !nextEdgeKeys.has(edgeKey(e)))
    .map((e) => ({ from: e.from, to: e.to, label: e.label }));

  // Detect modified props
  const prevPropsMap = new Map(prev.nodes.map((n) => [n.id, n.props]));
  const modifiedNodeProps = next.nodes
    .filter((n) => {
      const prevProps = prevPropsMap.get(n.id);
      return prevProps && JSON.stringify(prevProps) !== JSON.stringify(n.props);
    })
    .map((n) => ({ id: n.id, props: n.props }));

  return { addedNodes, removedNodes, addedEdges, removedEdges, modifiedNodeProps };
}
