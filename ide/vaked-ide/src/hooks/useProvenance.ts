import { useCallback } from "react";
import type { VakedNode } from "@/types/graph";
import { useGraphStore } from "@/store";
import { useEditorStore } from "@/store";

export interface ProvenanceLink {
  nodeId: string;
  nodeName: string;
  nodeKind: string;
  line: number;  // 1-based
  col: number;   // 1-based
  byteStart: number;
  byteEnd: number;
}

export function useProvenance() {
  const graph = useGraphStore((s) => s.graph);
  const highlightNodeFn = useGraphStore((s) => s.highlightNode);
  const setCursor = useEditorStore((s) => s.setCursor);

  // All nodes that have provenance spans, sorted by line
  const links: ProvenanceLink[] = graph.nodes
    .filter((n) => n.provenance?.span != null)
    .map((n) => ({
      nodeId: n.id,
      nodeName: n.name,
      nodeKind: n.kind,
      line: n.provenance!.span.line,
      col: n.provenance!.span.col,
      byteStart: n.provenance!.span.byteStart,
      byteEnd: n.provenance!.span.byteEnd,
    }))
    .sort((a, b) => a.byteStart - b.byteStart);

  const navigateToNode = useCallback(
    (nodeId: string) => {
      const node = graph.nodes.find((n) => n.id === nodeId);
      if (!node?.provenance?.span) return;
      const { line, col } = node.provenance.span;
      setCursor(line, col);
      highlightNodeFn(nodeId);
    },
    [graph, setCursor, highlightNodeFn]
  );

  const nodeAtCursor = useCallback(
    (line: number, col: number): VakedNode | null => {
      // Find the node whose span contains the cursor position
      const byteTarget = links.find(
        (l) => l.line === line && l.col <= col
      );
      if (!byteTarget) return null;
      return graph.nodes.find((n) => n.id === byteTarget.nodeId) ?? null;
    },
    [graph, links]
  );

  return { links, navigateToNode, nodeAtCursor };
}
