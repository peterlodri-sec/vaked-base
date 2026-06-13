import { SchemaInspector } from "@/components/SchemaInspector";
import { CapabilityHasse } from "@/components/CapabilityHasse";
import { ProvenancePanel } from "@/components/ProvenancePanel";
import { SurfaceLauncher } from "@/components/SurfaceLauncher";
import { useUIStore } from "@/store";

type SidebarTab = "schema" | "capability" | "provenance" | "surface";

const TABS: { id: SidebarTab; label: string; icon: string }[] = [
  { id: "schema",      label: "Schema",     icon: "📋" },
  { id: "capability",  label: "Caps",       icon: "🔑" },
  { id: "provenance",  label: "Provenance", icon: "🔗" },
  { id: "surface",     label: "Surface",    icon: "🖥" },
];

export function Sidebar() {
  const { sidebarTab, setSidebarTab } = useUIStore((s) => ({
    sidebarTab: s.sidebarTab,
    setSidebarTab: s.setSidebarTab,
  }));

  return (
    <div style={{
      display: "flex",
      flexDirection: "column",
      width: "280px",
      minWidth: "220px",
      background: "#0d1117",
      borderRight: "1px solid #1f2937",
      overflow: "hidden",
    }}>
      {/* Tab bar */}
      <div style={{
        display: "flex",
        background: "#111827",
        borderBottom: "1px solid #1f2937",
        flexShrink: 0,
      }}>
        {TABS.map((tab) => {
          const isActive = sidebarTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setSidebarTab(tab.id)}
              title={tab.label}
              style={{
                flex: 1,
                background: "transparent",
                border: "none",
                borderBottom: isActive ? "2px solid #6366f1" : "2px solid transparent",
                color: isActive ? "#a5b4fc" : "#4b5563",
                padding: "8px 4px",
                cursor: "pointer",
                fontSize: "14px",
                transition: "color 0.1s",
              }}
            >
              {tab.icon}
            </button>
          );
        })}
      </div>

      {/* Content */}
      <div style={{ flex: 1, overflow: "auto" }}>
        {sidebarTab === "schema" && <SchemaInspector />}
        {sidebarTab === "capability" && <CapabilityHasse />}
        {sidebarTab === "provenance" && <ProvenancePanel />}
        {(sidebarTab as string) === "surface" && <SurfaceLauncher />}
      </div>
    </div>
  );
}
