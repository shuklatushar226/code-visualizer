import React from "react";
import type { HeapObject, Value } from "@dsa-viz/trace-schema";
import type { PatternKind } from "../../lib/patterns";

export interface ArrayOverlay {
  /** Inclusive lower index. */
  lo: number;
  /** Inclusive upper index. */
  hi: number;
  kind: PatternKind;
  /** Binary-search "mid" index, highlighted separately. */
  midIndex?: number;
}

export interface ArrayViewProps {
  rootId: string;
  heap: Record<string, HeapObject>;
  /** Render as a generic fallback (e.g. for unknown structures). */
  fallback?: boolean;
  /** Pattern overlay: a highlighted [lo..hi] range and optional `mid`. */
  overlay?: ArrayOverlay | null;
}

/**
 * Renders a Python list / C++ vector / tuple as a horizontal sequence of
 * boxes with their index underneath. Suitable for arrays, strings (post-
 * char-split), DP tables (1-D), and as a fallback for unknown structures.
 */
export const ArrayView: React.FC<ArrayViewProps> = ({ rootId, heap, fallback, overlay }) => {
  const obj = heap[rootId];
  if (!obj) return <em>(missing object {rootId})</em>;
  if (obj.kind !== "list" && obj.kind !== "tuple") {
    return <em>(not array-like: {obj.kind})</em>;
  }

  // Clamp the overlay to the array's actual length (DP detector spans the
  // whole array via Number.MAX_SAFE_INTEGER; binary search etc. provide
  // real bounds).
  const lastIdx = obj.items.length - 1;
  const clampedLo = overlay ? Math.max(0, overlay.lo) : 0;
  const clampedHi = overlay ? Math.min(lastIdx, overlay.hi) : -1;
  const overlayActive = !!overlay && clampedLo <= clampedHi && obj.items.length > 0;

  return (
    <div
      className={[
        "dsa-viz-array",
        fallback ? "is-fallback" : "",
        overlayActive ? `has-overlay overlay-${overlay.kind}` : "",
      ].join(" ")}
    >
      {overlayActive && (
        <div className="dsa-viz-array-overlay-label">
          {labelFor(overlay.kind)} [{clampedLo}…{clampedHi}]
        </div>
      )}
      <div className="dsa-viz-array-cells">
        {obj.items.map((v, i) => {
          const inWindow = overlayActive && i >= clampedLo && i <= clampedHi;
          const isMid = overlayActive && overlay.midIndex === i;
          const cls = [
            "dsa-viz-cell",
            inWindow ? "is-in-window" : "",
            isMid ? "is-mid" : "",
          ].join(" ");
          return (
            <div key={i} className={cls}>
              <span className="dsa-viz-cell-value">{renderValue(v)}</span>
              <span className="dsa-viz-cell-index">{i}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
};

function labelFor(kind: PatternKind): string {
  switch (kind) {
    case "sliding_window":
      return "sliding window";
    case "two_pointer":
      return "two pointers";
    case "binary_search":
      return "binary search";
    case "dp":
      return "dp tabulation";
  }
}

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
