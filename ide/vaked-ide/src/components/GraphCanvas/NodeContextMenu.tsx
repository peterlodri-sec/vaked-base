import { useEffect, useRef } from "react";
import type { VakedNode } from "@/types/graph";
import { useGraphStore, useUIStore, useEditorStore } from "@/store";
import { getKindConfig } from "@/graph/kindConfig";

interface NodeContextMenuProps {
  node: VakedNode;
  x: number;
  y: number;
  onClose: () => void;
}

export function NodeContextMenu({ node, x, y, onClose }: NodeContextMenuProps) {
  const cfg = getKindConfig(node.kind);
  const highlightNode = useGraphStore((s) => s.highlightNode);
  const selectNode = useGraphStore((s) => s.selectNode);
  const { setSidebarTab } = useUIStore();

  const ref = useRef<HTMLDivElement>(null);

  // Close on click-outside or Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("mousedown", onDown);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("mousedown", onDown);
    };
  }, [onClose]);

  // Keep menu inside viewport
  const menuW = 200;
  const menuH = 180;
  const left = Math.min(x, window.innerWidth - menuW - 8);
  const top = Math.min(y, window.innerHeight - menuH - 8);

  const items: { label: string; icon: string; action: () => void }[] = [
    {
      label: "Jump to source",
      icon: "↗",
      action: () => {
        highlightNode(node.id);
        setSidebarTab("provenance");
        onClose();
      },
    },
    {
      label: "Inspect schema",
      icon: "📋",
      action: () => {
        selectNode(node.id);
        setSidebarTab("schema");
        onClose();
      },
    },
    {
      label: "Copy node ID",
      icon: "⎘",
      action: () => {
        navigator.clipboard.writeText(node.id).catch(() => {});
        onClose();
      },
    },
    {
      label: "Copy node name",
      icon: "⎘",
      action: () => {
        navigator.clipboard.writeText(node.name).catch(() => {});
        onClose();
      },
    },
  ];

  return (
    <div
      ref={ref}
      style={{
        position: "fixed",
        left,
        top,
        zIndex: 8000,
        background: "#111827",
        border: "1px solid #374151",
        borderRadius: "8px",
        overflow: "hidden",
        boxShadow: "0 8px 24px rgba(0,0,0,0.6)",
        minWidth: `${menuW}px`,
      }}
    >
      {/* Header */}
      <div style={{
        padding: "8px 12px",
        borderBottom: "1px solid #1f2937",
        display: "flex",
        alignItems: "center",
        gap: "6px",
        background: "#0d1117",
      }}>
        <span style={{ fontSize: "13px" }}>{cfg.icon}</span>
        <div>
          <div style={{ fontSize: "10px", color: "#4b5563", textTransform: "uppercase", letterSpacing: "0.05em" }}>{node.kind}</div>
          <div style={{ fontSize: "13px", color: cfg.color, fontFamily: "monospace", fontWeight: 600 }}>{node.name}</div>
        </div>
      </div>
      {/* Items */}
      {items.map((item) => (
        <button
          key={item.label}
          onClick={item.action}
          style={{
            display: "flex",
            alignItems: "center",
            gap: "8px",
            width: "100%",
            background: "transparent",
            border: "none",
            borderBottom: "1px solid #1f2937",
            color: "#e2e8f0",
            padding: "8px 12px",
            cursor: "pointer",
            fontSize: "12px",
            fontFamily: "monospace",
            textAlign: "left",
            transition: "background 0.05s",
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = "#1f2937")}
          onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
        >
          <span style={{ width: "14px", textAlign: "center", opacity: 0.6 }}>{item.icon}</span>
          {item.label}
        </button>
      ))}
    </div>
  );
}
