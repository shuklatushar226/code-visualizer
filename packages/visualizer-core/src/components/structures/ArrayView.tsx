import React from "react";
import type { HeapObject, Value } from "@dsa-viz/trace-schema";

export interface ArrayViewProps {
  rootId: string;
  heap: Record<string, HeapObject>;
  /** Render as a generic fallback (e.g. for unknown structures). */
  fallback?: boolean;
}

/**
 * Renders a Python list / C++ vector / tuple as a horizontal sequence of
 * boxes with their index underneath. Suitable for arrays, strings (post-
 * char-split), DP tables (1-D), and as a fallback for unknown structures.
 */
export const ArrayView: React.FC<ArrayViewProps> = ({ rootId, heap, fallback }) => {
  const obj = heap[rootId];
  if (!obj) return <em>(missing object {rootId})</em>;
  if (obj.kind !== "list" && obj.kind !== "tuple") {
    return <em>(not array-like: {obj.kind})</em>;
  }
  return (
    <div className={["dsa-viz-array", fallback ? "is-fallback" : ""].join(" ")}>
      <div className="dsa-viz-array-cells">
        {obj.items.map((v, i) => (
          <div key={i} className="dsa-viz-cell">
            <span className="dsa-viz-cell-value">{renderValue(v)}</span>
            <span className="dsa-viz-cell-index">{i}</span>
          </div>
        ))}
      </div>
    </div>
  );
};

function renderValue(v: Value): string {
  switch (v.kind) {
    case "int":
    case "float":
      return String(v.v);
    case "bool":
      return v.v ? "T" : "F";
    case "str":
      return `"${v.v}"`;
    case "none":
      return "·";
    case "ref":
      return `→${v.id}`;
  }
}
