import { useCallback, useEffect } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  BackgroundVariant,
  useNodesState,
  useEdgesState,
  Panel,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

import type { Node, Edge, NodeMouseHandler } from "@xyflow/react";
import type { RFNodeData, RFEdgeData } from "@/types/graph";
import { VakedNode } from "./VakedNode";
import { VakedEdge } from "./VakedEdge";
import { useGraphStore } from "@/store";
import { applyElkLayout } from "@/graph/layout";
import { getKindConfig } from "@/graph/kindConfig";

const nodeTypes = { vakedNode: VakedNode };
const edgeTypes = { vakedEdge: VakedEdge };

export function GraphCanvas() {
  const rfNodesFromStore = useGraphStore((s) => s.rfNodes);
  const rfEdgesFromStore = useGraphStore((s) => s.rfEdges);
  const selectNode = useGraphStore((s) => s.selectNode);
  const setRfNodes = useGraphStore((s) => s.setRfNodes);

  const [nodes, setNodes, onNodesChange] = useNodesState<RFNodeData>(rfNodesFromStore);
  const [edges, setEdges, onEdgesChange] = useEdgesState<RFEdgeData>(rfEdgesFromStore);

  // Sync from store + apply ELK layout when graph changes
  useEffect(() => {
    if (rfNodesFromStore.length === 0) {
      setNodes([]);
      setEdges([]);
      return;
    }

    applyElkLayout(rfNodesFromStore, rfEdgesFromStore).then((laidOut) => {
      setNodes(laidOut);
      setRfNodes(laidOut);
      setEdges(rfEdgesFromStore);
    });
  }, [rfNodesFromStore, rfEdgesFromStore]); // eslint-disable-line react-hooks/exhaustive-deps

  const onNodeClick: NodeMouseHandler<RFNodeData> = useCallback(
    (_evt, node) => {
      selectNode(node.id);
    },
    [selectNode]
  );

  const onPaneClick = useCallback(() => {
    selectNode(null);
  }, [selectNode]);

  return (
    <div style={{ width: "100%", height: "100%", background: "#0f1117" }}>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={onNodeClick}
        onPaneClick={onPaneClick}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        fitView
        fitViewOptions={{ padding: 0.15 }}
        minZoom={0.1}
        maxZoom={3}
        colorMode="dark"
      >
        <Background
          variant={BackgroundVariant.Dots}
          gap={20}
          size={1}
          color="#1f2937"
        />
        <Controls style={{ background: "#1f2937", border: "1px solid #374151" }} />
        <MiniMap
          nodeColor={(node) => {
            const data = node.data as RFNodeData | undefined;
            return data ? getKindConfig(data.vakedNode.kind).bg : "#374151";
          }}
          style={{ background: "#111827", border: "1px solid #374151" }}
          maskColor="rgba(0,0,0,0.5)"
        />
        {nodes.length === 0 && (
          <Panel position="top-center">
            <div style={{
              color: "#6b7280",
              fontSize: "13px",
              marginTop: "40px",
              fontFamily: "monospace",
            }}>
              Open a .vaked file to see the graph
            </div>
          </Panel>
        )}
      </ReactFlow>
    </div>
  );
}
