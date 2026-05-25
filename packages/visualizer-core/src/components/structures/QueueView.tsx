import React from "react";
import type { HeapObject, Value } from "@dsa-viz/trace-schema";

export interface QueueViewProps {
  rootId: string;
  heap: Record<string, HeapObject>;
}

/**
 * Renders a deque / list tagged `# @viz: queue` as a horizontal pipe with
 * the head (dequeue end) on the left and the tail (enqueue end) on the right.
 */
export const QueueView: React.FC<QueueViewProps> = ({ rootId, heap }) => {
  const obj = heap[rootId];
  if (!obj || obj.kind !== "list") return <em>(not queue-like)</em>;
  return (
    <div className="dsa-viz-queue">
      <span className="dsa-viz-queue-label">head →</span>
      <div className="dsa-viz-queue-cells">
        {obj.items.map((v, i) => (
          <div key={i} className="dsa-viz-queue-cell">
            <span>{renderValue(v)}</span>
            <span className="dsa-viz-queue-index">{i}</span>
          </div>
        ))}
      </div>
      <span className="dsa-viz-queue-label">→ tail</span>
    </div>
  );
};

function renderValue(v: Value): string {
  if (v.kind === "int" || v.kind === "float" || v.kind === "str" || v.kind === "bool")
    return String((v as { v: unknown }).v);
  if (v.kind === "none") return "·";
  return `→${v.id}`;
}
