import React from "react";
import type { HeapObject, Value } from "@dsa-viz/trace-schema";

export interface HeapTreeViewProps {
  rootId: string;
  heap: Record<string, HeapObject>;
  width?: number;
  height?: number;
}

/**
 * Renders an array-backed binary heap (e.g. Python's `heapq`) as a complete
 * binary tree using array-index math (`2i+1`, `2i+2`). The lay-out is fully
 * computed up front so there's no dependency on d3.
 */
export const HeapTreeView: React.FC<HeapTreeViewProps> = ({
  rootId,
  heap,
  width = 480,
  height = 280,
}) => {
  const obj = heap[rootId];
  if (!obj || obj.kind !== "list") return <em>(not heap-like)</em>;
  const items = obj.items;
  if (items.length === 0) return <em>(empty heap)</em>;
  const depth = Math.floor(Math.log2(items.length)) + 1;
  const levelH = (height - 40) / depth;
  const positions: { x: number; y: number; v: Value; i: number }[] = items.map((v, i) => {
    const level = Math.floor(Math.log2(i + 1));
    const idxInLevel = i - (Math.pow(2, level) - 1);
    const slots = Math.pow(2, level);
    const x = ((idxInLevel + 0.5) * (width - 40)) / slots + 20;
    const y = 20 + level * levelH + levelH / 2;
    return { x, y, v, i };
  });

  const edges = items.flatMap((_, i) => {
    const out: { from: number; to: number }[] = [];
    const l = 2 * i + 1;
    const r = 2 * i + 2;
    if (l < items.length) out.push({ from: i, to: l });
    if (r < items.length) out.push({ from: i, to: r });
    return out;
  });

  return (
    <svg className="dsa-viz-heaptree" width={width} height={height}>
      {edges.map((e, j) => (
        <line
          key={j}
          x1={positions[e.from].x}
          y1={positions[e.from].y}
          x2={positions[e.to].x}
          y2={positions[e.to].y}
          stroke="#888"
        />
      ))}
      {positions.map((p) => (
        <g key={p.i} transform={`translate(${p.x},${p.y})`}>
          <circle r={18} fill="#ffe7c4" stroke="#a06000" />
          <text textAnchor="middle" dy="0.35em">{labelValue(p.v)}</text>
          <text textAnchor="middle" dy="2em" fontSize={10} fill="#666">[{p.i}]</text>
        </g>
      ))}
    </svg>
  );
};

function labelValue(v: Value): string {
  if (v.kind === "int" || v.kind === "float" || v.kind === "str" || v.kind === "bool")
    return String((v as { v: unknown }).v);
  if (v.kind === "none") return "·";
  return "→";
}
