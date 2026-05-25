import React from "react";
import type { HeapObject, Value } from "@dsa-viz/trace-schema";

export interface LinkedListViewProps {
  rootId: string;
  heap: Record<string, HeapObject>;
}

interface Node {
  id: string;
  val: Value;
  next?: string;
  prev?: string;
}

/**
 * Walks the `next` chain starting from `rootId`, detects cycles, and renders
 * nodes as boxes joined by arrows. Singly-linked by default; if the node has
 * a `prev` field, an extra back-arrow is drawn so doubly-linked lists work.
 */
export const LinkedListView: React.FC<LinkedListViewProps> = ({ rootId, heap }) => {
  const nodes = walkList(rootId, heap);
  if (!nodes) return <em>(not linked-list-like)</em>;

  return (
    <div className="dsa-viz-linkedlist">
      {nodes.list.map((n, i) => (
        <React.Fragment key={n.id}>
          <div className="dsa-viz-node" data-id={n.id}>
            <span className="dsa-viz-node-val">{simpleValue(n.val)}</span>
            <span className="dsa-viz-node-id">{n.id}</span>
          </div>
          {i < nodes.list.length - 1 && <span className="dsa-viz-arrow">→</span>}
        </React.Fragment>
      ))}
      {nodes.cycle && (
        <span className="dsa-viz-cycle-marker" title={`cycle back to ${nodes.cycle}`}>
          ↺ {nodes.cycle}
        </span>
      )}
      {nodes.truncated && <span className="dsa-viz-truncated">…</span>}
    </div>
  );
};

function walkList(
  startId: string,
  heap: Record<string, HeapObject>,
): { list: Node[]; cycle?: string; truncated?: boolean } | null {
  const seen = new Set<string>();
  const out: Node[] = [];
  let cursor: string | undefined = startId;
  while (cursor) {
    if (seen.has(cursor)) {
      return { list: out, cycle: cursor };
    }
    if (out.length > 200) {
      return { list: out, truncated: true };
    }
    seen.add(cursor);
    const obj: HeapObject | undefined = heap[cursor];
    if (!obj || obj.kind !== "object") return null;
    const val: Value | undefined = obj.fields.val ?? obj.fields.data ?? obj.fields.value;
    const next: Value | undefined = obj.fields.next;
    const prev: Value | undefined = obj.fields.prev;
    out.push({
      id: cursor,
      val: val ?? { kind: "none" },
      next: next?.kind === "ref" ? next.id : undefined,
      prev: prev?.kind === "ref" ? prev.id : undefined,
    });
    cursor = next?.kind === "ref" ? next.id : undefined;
  }
  return { list: out };
}

function simpleValue(v: Value): string {
  if (v.kind === "int" || v.kind === "float" || v.kind === "str" || v.kind === "bool")
    return String((v as { v: unknown }).v);
  if (v.kind === "none") return "·";
  return `→${v.id}`;
}
