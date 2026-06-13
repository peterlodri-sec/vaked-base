import { memo } from "react";
import { BaseEdge, EdgeLabelRenderer, getBezierPath, getStraightPath } from "@xyflow/react";
import type { EdgeProps } from "@xyflow/react";
import type { RFEdgeData } from "@/types/graph";
import { getEdgeStyle } from "@/graph/edgeConfig";

export const VakedEdge = memo(function VakedEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  label,
}: EdgeProps<RFEdgeData>) {
  const semantics = data?.semantics ?? "structural";
  const edge = data?.vakedEdge;
  const style = getEdgeStyle(semantics, edge!);

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const edgeLabel = label ?? edge?.props?.label;

  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={{
          stroke: style.stroke,
          strokeWidth: style.strokeWidth,
          strokeDasharray: style.strokeDasharray,
          opacity: 0.8,
        }}
        markerEnd={style.markerEnd}
        animated={style.animated}
      />
      {edgeLabel && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: "absolute",
              transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
              background: "rgba(15,15,20,0.8)",
              color: style.stroke,
              fontSize: "10px",
              fontFamily: "monospace",
              padding: "1px 5px",
              borderRadius: "4px",
              border: `1px solid ${style.stroke}`,
              pointerEvents: "none",
            }}
          >
            {String(edgeLabel)}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
});
