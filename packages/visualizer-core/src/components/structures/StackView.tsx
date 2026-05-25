import React from "react";
import type { HeapObject, Value } from "@dsa-viz/trace-schema";

export interface StackViewProps {
  rootId: string;
  heap: Record<string, HeapObject>;
}

/**
 * Renders a Python list (or any list-backed structure tagged
 * `# @viz: stack`) as a vertical stack, top-of-stack on top, with the
 * push/pop end clearly marked.
 */
export const StackView: React.FC<StackViewProps> = ({ rootId, heap }) => {
  const obj = heap[rootId];
  if (!obj || obj.kind !== "list") return <em>(not stack-like)</em>;
  const top = obj.items.length - 1;
  return (
    <div className="dsa-viz-stack">
      <div className="dsa-viz-stack-label dsa-viz-stack-top">top →</div>
      {obj.items
        .slice()
        .reverse()
        .map((v, i) => (
          <div
            key={i}
            className={[
              "dsa-viz-stack-cell",
              i === 0 ? "is-top" : "",
            ].join(" ")}
          >
            <span>{renderValue(v)}</span>
            <span className="dsa-viz-stack-index">{top - i}</span>
          </div>
        ))}
      <div className="dsa-viz-stack-label dsa-viz-stack-bottom">bottom</div>
    </div>
  );
};

function renderValue(v: Value): string {
  if (v.kind === "int" || v.kind === "float" || v.kind === "str" || v.kind === "bool")
    return String((v as { v: unknown }).v);
  if (v.kind === "none") return "·";
  return `→${v.id}`;
}
