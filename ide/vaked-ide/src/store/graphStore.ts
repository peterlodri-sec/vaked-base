import { create } from "zustand";
import type { Node, Edge } from "@xyflow/react";
import type { VakedGraph, RFNodeData, RFEdgeData } from "@/types/graph";
import { EMPTY_GRAPH } from "@/types/graph";
import { lpgToReactFlow, highlightNode } from "@/graph/adapter";

interface GraphStore {
  graph: VakedGraph;
  rfNodes: Node<RFNodeData>[];
  rfEdges: Edge<RFEdgeData>[];
  selectedNodeId: string | null;
  highlightedNodeId: string | null;
  errorNodeIds: Set<string>;
  filePath: string | null;

  setGraph: (g: VakedGraph) => void;
  setRfNodes: (nodes: Node<RFNodeData>[]) => void;
  setRfEdges: (edges: Edge<RFEdgeData>[]) => void;
  selectNode: (id: string | null) => void;
  highlightNode: (id: string | null) => void;
  setErrorNodeIds: (ids: Set<string>) => void;
  setFilePath: (path: string | null) => void;
}

export const useGraphStore = create<GraphStore>((set, get) => ({
  graph: EMPTY_GRAPH,
  rfNodes: [],
  rfEdges: [],
  selectedNodeId: null,
  highlightedNodeId: null,
  errorNodeIds: new Set(),
  filePath: null,

  setGraph: (g) => {
    const { rfNodes, rfEdges } = lpgToReactFlow(g, get().errorNodeIds);
    set({ graph: g, rfNodes, rfEdges });
  },

  setRfNodes: (nodes) => set({ rfNodes: nodes }),
  setRfEdges: (edges) => set({ rfEdges: edges }),

  selectNode: (id) => set({ selectedNodeId: id }),

  highlightNode: (id) => {
    const nodes = highlightNode(get().rfNodes, id);
    set({ highlightedNodeId: id, rfNodes: nodes });
  },

  setErrorNodeIds: (ids) => {
    // Re-apply error markers to current RF nodes
    const nodes = get().rfNodes.map((n) => ({
      ...n,
      data: { ...n.data, hasErrors: ids.has(n.id) },
    }));
    set({ errorNodeIds: ids, rfNodes: nodes });
  },

  setFilePath: (path) => set({ filePath: path }),
}));
