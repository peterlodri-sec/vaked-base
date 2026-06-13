import { useCallback, useRef } from "react";

type Axis = "x" | "y";

/**
 * Returns an `onMouseDown` handler that fires `onDelta` with incremental
 * pixel deltas as the user drags. Works for both horizontal and vertical
 * resize handles.
 */
export function useResizeDrag(
  axis: Axis,
  onDelta: (delta: number) => void,
): { onMouseDown: (e: React.MouseEvent) => void } {
  const lastPos = useRef(0);

  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      lastPos.current = axis === "y" ? e.clientY : e.clientX;

      const onMove = (ev: MouseEvent) => {
        const cur = axis === "y" ? ev.clientY : ev.clientX;
        const delta = cur - lastPos.current;
        lastPos.current = cur;
        if (delta !== 0) onDelta(delta);
      };
      const onUp = () => {
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
      };
      window.addEventListener("mousemove", onMove);
      window.addEventListener("mouseup", onUp);
    },
    [axis, onDelta],
  );

  return { onMouseDown };
}
