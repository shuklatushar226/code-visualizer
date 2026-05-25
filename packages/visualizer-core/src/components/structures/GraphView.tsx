import React from "react";
import type { HeapObject, Value } from "@dsa-viz/trace-schema";

export interface GraphViewProps {
  rootId: string;
  heap: Record<string, HeapObject>;
  width?: number;
  height?: number;
}

interface GraphData {
  nodes: { id: string; label: string }[];
  edges: { from: string; to: string }[];
}

/**
 * Renders an adjacency-dict-style graph using a simple force-free circular
 * layout (deterministic, no animation cost). For richer rendering swap in
 * d3-force or cytoscape in the host app.
 *
 * Assumes the root is a `dict` whose entries map node-id (typically an int
 * or str primitive) to a `list` of neighbor primitives.
 */
export const GraphView: React.FC<GraphViewProps> = ({
  rootId,
  heap,
  width = 480,
  height = 320,
}) => {
  const g = buildAdjacencyGraph(rootId, heap);
  if (!g || g.nodes.length === 0) {
    return <em>(empty graph)</em>;
  }
  const cx = width / 2;
  const cy = height / 2;
  const radius = Math.min(width, height) / 2 - 30;
  const angleStep = (2 * Math.PI) / g.nodes.length;
  const positions: Record<string, { x: number; y: number }> = {};
  g.nodes.forEach((n, i) => {
    positions[n.id] = {
      x: cx + radius * Math.cos(i * angleStep - Math.PI / 2),
      y: cy + radius * Math.sin(i * angleStep - Math.PI / 2),
    };
  });

  return (
    <svg className="dsa-viz-graph" width={width} height={height}>
      {g.edges.map((e, i) => {
        const a = positions[e.from];
        const b = positions[e.to];
        if (!a || !b) return null;
        return (
          <line
            key={i}
            x1={a.x}
            y1={a.y}
            x2={b.x}
            y2={b.y}
            stroke="#888"
            className="dsa-viz-graph-edge"
          />
        );
      })}
      {g.nodes.map((n) => {
        const p = positions[n.id];
        return (
          <g key={n.id} transform={`translate(${p.x},${p.y})`}>
            <circle r={18} fill="#eef" stroke="#446" />
            <text textAnchor="middle" dy="0.35em">{n.label}</text>
          </g>
        );
      })}
    </svg>
  );
};

function buildAdjacencyGraph(
  rootId: string,
  heap: Record<string, HeapObject>,
): GraphData | null {
  const root = heap[rootId];
  if (!root || root.kind !== "dict") return null;

  const ids = new Set<string>();
  const labels: Record<string, string> = {};
  const edges: { from: string; to: string }[] = [];

  const key = (v: Value): string => {
    if (v.kind === "ref") return `r:${v.id}`;
    if (v.kind === "none") return "n:None";
    return `p:${(v as { v: unknown }).v}`;
  };
  const label = (v: Value): string => {
    if (v.kind === "ref") return v.id;
    if (v.kind === "none") return "None";
    return String((v as { v: unknown }).v);
  };

  for (const [k, neighbors] of root.entries) {
    const ks = key(k);
    ids.add(ks);
    labels[ks] = label(k);

    if (neighbors.kind !== "ref") continue;
    const nobj = heap[neighbors.id];
    if (!nobj || (nobj.kind !== "list" && nobj.kind !== "set")) continue;
    for (const n of nobj.items) {
      const ns = key(n);
      ids.add(ns);
      labels[ns] = label(n);
      edges.push({ from: ks, to: ns });
    }
  }

  return {
    nodes: Array.from(ids).map((id) => ({ id, label: labels[id] })),
    edges,
  };
}
