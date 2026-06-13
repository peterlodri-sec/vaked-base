import { useEffect, useRef, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { useGraphStore } from "@/store";

interface Availability {
  embedded: boolean;
  reason: string;
}

interface Bounds {
  x: number;
  y: number;
  width: number;
  height: number;
  scale: number;
}

function rectOf(el: HTMLElement): Bounds {
  const r = el.getBoundingClientRect();
  return {
    x: r.left,
    y: r.top,
    width: r.width,
    height: r.height,
    scale: window.devicePixelRatio || 1,
  };
}

/**
 * Reserves a transparent rectangle. On macOS (`--features ghostty`) the Rust
 * backend floats a native libghostty NSView over this exact rectangle; we just
 * keep reporting its screen bounds. Elsewhere we render a fallback that can
 * launch an external Ghostty window. See docs/terminal-embedding.md.
 */
export function Terminal() {
  const hostRef = useRef<HTMLDivElement>(null);
  const [avail, setAvail] = useState<Availability | null>(null);
  const filePath = useGraphStore((s) => s.filePath);
  const cwd = filePath ? filePath.replace(/\/[^/]*$/, "") : undefined;

  // Probe whether this build has the embedded surface.
  useEffect(() => {
    invoke<Availability>("terminal_available")
      .then(setAvail)
      .catch(() => setAvail({ embedded: false, reason: "terminal unavailable" }));
  }, []);

  // Embedded path: open the native surface and keep its frame glued to ours.
  useEffect(() => {
    if (!avail?.embedded || !hostRef.current) return;
    const host = hostRef.current;
    let alive = true;

    invoke("terminal_open", { bounds: rectOf(host), cwd }).catch(console.error);

    const push = () => {
      if (alive && hostRef.current) {
        invoke("terminal_set_bounds", { bounds: rectOf(hostRef.current) }).catch(() => {});
      }
    };
    const ro = new ResizeObserver(push);
    ro.observe(host);
    window.addEventListener("resize", push);
    // Layout settles a frame after mount; also catches scroll-driven shifts.
    const iv = window.setInterval(push, 500);

    return () => {
      alive = false;
      ro.disconnect();
      window.removeEventListener("resize", push);
      window.clearInterval(iv);
      invoke("terminal_close").catch(() => {});
    };
  }, [avail?.embedded, cwd]);

  // Embedded: transparent host the native surface draws over.
  if (avail?.embedded) {
    return <div ref={hostRef} style={{ width: "100%", height: "100%", background: "#000" }} />;
  }

  // Fallback: external Ghostty launcher.
  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        gap: "10px",
        background: "#0b0e14",
        color: "#6b7280",
        fontFamily: "monospace",
        fontSize: "12px",
        padding: "16px",
        textAlign: "center",
      }}
    >
      <div style={{ fontSize: "20px" }}>👻</div>
      <div style={{ color: "#9ca3af" }}>Embedded Ghostty isn't available in this build.</div>
      {avail && <div style={{ fontSize: "11px", opacity: 0.7 }}>{avail.reason}</div>}
      <button
        onClick={() => invoke("terminal_open_external", { cwd }).catch(console.error)}
        style={{
          background: "#052e16",
          border: "1px solid #16a34a",
          borderRadius: "5px",
          color: "#4ade80",
          padding: "5px 14px",
          cursor: "pointer",
          fontFamily: "monospace",
          fontSize: "12px",
        }}
      >
        ▸ Open in Ghostty
      </button>
    </div>
  );
}
