interface Grant {
  id: string;
  label: string;
  parents: string[];  // ids of weaker grants (a < b means a is parent of b in the Hasse)
}

interface DomainPanelProps {
  domain: string;
  color: string;
  grants: Grant[];
  usedGrants: Set<string>;
}

// Layered layout: compute y-level based on longest path from root
function computeLayers(grants: Grant[]): Map<string, number> {
  const layers = new Map<string, number>();
  const byId = new Map(grants.map((g) => [g.id, g]));

  function getLayer(id: string): number {
    if (layers.has(id)) return layers.get(id)!;
    const g = byId.get(id);
    if (!g || g.parents.length === 0) {
      layers.set(id, 0);
      return 0;
    }
    const l = Math.max(...g.parents.map((p) => getLayer(p) + 1));
    layers.set(id, l);
    return l;
  }
  grants.forEach((g) => getLayer(g.id));
  return layers;
}

export function DomainPanel({ domain, color, grants, usedGrants }: DomainPanelProps) {
  const layers = computeLayers(grants);
  const maxLayer = Math.max(...Array.from(layers.values()));
  const nodeH = 26;
  const nodeW = 90;
  const layerGap = 40;
  const nodeGap = 32;
  const padding = 8;

  // Group grants by layer
  const byLayer = new Map<number, Grant[]>();
  for (const g of grants) {
    const l = layers.get(g.id) ?? 0;
    if (!byLayer.has(l)) byLayer.set(l, []);
    byLayer.get(l)!.push(g);
  }

  // Compute positions
  const pos = new Map<string, { x: number; y: number }>();
  for (const [layer, layerGrants] of byLayer) {
    const totalH = layerGrants.length * nodeH + (layerGrants.length - 1) * nodeGap;
    layerGrants.forEach((g, i) => {
      pos.set(g.id, {
        x: padding + layer * (nodeW + layerGap),
        y: padding + i * (nodeH + nodeGap),
      });
    });
  }

  const totalW = padding * 2 + (maxLayer + 1) * (nodeW + layerGap);
  const totalH = padding * 2 + Math.max(...Array.from(byLayer.values()).map((lg) =>
    lg.length * nodeH + (lg.length - 1) * nodeGap
  ));

  return (
    <div style={{ marginBottom: "12px" }}>
      <div style={{
        fontSize: "11px",
        textTransform: "uppercase",
        color,
        fontFamily: "monospace",
        fontWeight: 700,
        letterSpacing: "0.08em",
        padding: "0 4px 4px",
        borderBottom: `1px solid ${color}44`,
        marginBottom: "6px",
      }}>
        {domain}
      </div>
      <svg width={totalW} height={totalH + 8} style={{ overflow: "visible" }}>
        {/* Draw edges */}
        {grants.map((g) =>
          g.parents.map((pId) => {
            const from = pos.get(pId);
            const to = pos.get(g.id);
            if (!from || !to) return null;
            return (
              <line
                key={`${pId}-${g.id}`}
                x1={from.x + nodeW}
                y1={from.y + nodeH / 2}
                x2={to.x}
                y2={to.y + nodeH / 2}
                stroke={color}
                strokeWidth={1}
                strokeOpacity={0.4}
              />
            );
          })
        )}

        {/* Draw nodes */}
        {grants.map((g) => {
          const p = pos.get(g.id)!;
          const isUsed = usedGrants.has(g.id);
          return (
            <g key={g.id} transform={`translate(${p.x}, ${p.y})`}>
              <rect
                width={nodeW}
                height={nodeH}
                rx={4}
                fill={isUsed ? `${color}33` : "#111827"}
                stroke={isUsed ? color : `${color}44`}
                strokeWidth={isUsed ? 1.5 : 1}
              />
              <text
                x={nodeW / 2}
                y={nodeH / 2 + 4}
                textAnchor="middle"
                fontSize={10}
                fontFamily="monospace"
                fill={isUsed ? color : "#6b7280"}
              >
                {g.label}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}
