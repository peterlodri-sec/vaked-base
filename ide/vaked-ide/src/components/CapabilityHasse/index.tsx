import { DomainPanel } from "./DomainPanel";
import { useGraphStore } from "@/store";

// Hardcoded domain lattices (from vaked/schema/parallel-types.md + builtins.vaked)
const DOMAINS = [
  {
    name: "fs",
    color: "#16a34a",
    grants: [
      { id: "fs.none", label: "none", parents: [] },
      { id: "fs.repo_ro", label: "repo_ro", parents: ["fs.none"] },
      { id: "fs.repo_rw", label: "repo_rw", parents: ["fs.repo_ro"] },
      { id: "fs.host_ro", label: "host_ro", parents: ["fs.repo_ro"] },
      { id: "fs.host_rw", label: "host_rw", parents: ["fs.repo_rw", "fs.host_ro"] },
    ],
  },
  {
    name: "network",
    color: "#2563eb",
    grants: [
      { id: "network.none", label: "none", parents: [] },
      { id: "network.loopback", label: "loopback", parents: ["network.none"] },
      { id: "network.lan", label: "lan", parents: ["network.loopback"] },
      { id: "network.egress", label: "egress", parents: ["network.lan"] },
    ],
  },
  {
    name: "mcp",
    color: "#7c3aed",
    grants: [
      { id: "mcp.none", label: "none", parents: [] },
      { id: "mcp.github_read", label: "github_read", parents: ["mcp.none"] },
      { id: "mcp.github_write", label: "github_write", parents: ["mcp.github_read"] },
      { id: "mcp.broker_admin", label: "broker_admin", parents: ["mcp.github_write"] },
    ],
  },
  {
    name: "ebpf",
    color: "#dc2626",
    grants: [
      { id: "ebpf.none", label: "none", parents: [] },
      { id: "ebpf.observe", label: "observe", parents: ["ebpf.none"] },
      { id: "ebpf.attach_ro", label: "attach_ro", parents: ["ebpf.observe"] },
      { id: "ebpf.attach_rw", label: "attach_rw", parents: ["ebpf.attach_ro"] },
    ],
  },
  {
    name: "process",
    color: "#ea580c",
    grants: [
      { id: "process.none", label: "none", parents: [] },
      { id: "process.spawn_sandboxed", label: "spawn_sandboxed", parents: ["process.none"] },
      { id: "process.spawn", label: "spawn", parents: ["process.spawn_sandboxed"] },
      { id: "process.exec_host", label: "exec_host", parents: ["process.spawn"] },
    ],
  },
  {
    name: "mem",
    color: "#0891b2",
    grants: [
      { id: "mem.none", label: "none", parents: [] },
      { id: "mem.recall", label: "recall", parents: ["mem.none"] },
      { id: "mem.append", label: "append", parents: ["mem.recall"] },
      { id: "mem.admin", label: "admin", parents: ["mem.append"] },
    ],
  },
];

export function CapabilityHasse() {
  const graph = useGraphStore((s) => s.graph);

  // Collect which grants are used in the current graph
  const usedGrants = new Set<string>();
  for (const node of graph.nodes) {
    if (node.kind === "capability") {
      // Extract grants from props
      const grantList = node.props.grants as string[] | undefined;
      if (grantList) {
        for (const g of grantList) usedGrants.add(g);
      }
    }
    // Also check requires_capability edges target node ids
  }
  for (const edge of graph.edges) {
    if (edge.label === "requires_capability") {
      const domain = String(edge.props?.domain ?? "");
      const grant = String(edge.props?.grant ?? "");
      if (domain && grant) usedGrants.add(`${domain}.${grant}`);
    }
  }

  return (
    <div style={{ padding: "10px", overflow: "auto", height: "100%" }}>
      <div style={{
        color: "#6b7280",
        fontSize: "11px",
        textTransform: "uppercase",
        letterSpacing: "0.05em",
        marginBottom: "10px",
      }}>
        Capability Domains
      </div>
      {DOMAINS.map((domain) => (
        <DomainPanel
          key={domain.name}
          domain={domain.name}
          color={domain.color}
          grants={domain.grants}
          usedGrants={usedGrants}
        />
      ))}
    </div>
  );
}
