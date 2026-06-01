import React from "react";
import type { HeapObject, Value } from "@dsa-viz/trace-schema";
import { formatScalar } from "../../lib/formatScalar";

export interface LinkedListViewProps {
  rootId: string;
  heap: Record<string, HeapObject>;
}

export interface LinkedListNode {
  id: string;
  val: Value;
  next?: string;
  /** Value of the node `next` points to — shown so the chain reads in values. */
  nextVal?: Value;
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
            <span className="dsa-viz-node-id dsa-viz-node-next" title="next pointer target">
              next → {nextLabel(n)}
            </span>
          </div>
          {i < nodes.list.length - 1 &&
            (nodes.list[i + 1].prev === n.id ? (
              // doubly-linked: the next node points back to this one
              <span className="dsa-viz-arrow dsa-viz-arrow-double" title="doubly linked">⇄</span>
            ) : (
              <span className="dsa-viz-arrow">→</span>
            ))}
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

export function walkList(
  startId: string,
  heap: Record<string, HeapObject>,
): { list: LinkedListNode[]; cycle?: string; truncated?: boolean } | null {
  const seen = new Set<string>();
  const out: LinkedListNode[] = [];
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
    const nextId: string | undefined = next?.kind === "ref" ? next.id : undefined;
    // Resolve the value the `next` pointer targets so the UI can show the
    // chain in values (e.g. "next → 2") instead of a raw heap address. Works
    // across cycles too, since it reads the target straight from the heap.
    let nextVal: Value | undefined;
    if (nextId) {
      const target = heap[nextId];
      if (target && target.kind === "object") {
        nextVal = target.fields.val ?? target.fields.data ?? target.fields.value;
      }
    }
    out.push({
      id: cursor,
      val: val ?? { kind: "none" },
      next: nextId,
      nextVal,
      prev: prev?.kind === "ref" ? prev.id : undefined,
    });
    cursor = nextId;
  }
  return { list: out };
}

function simpleValue(v: Value): string {
  if (v.kind === "int" || v.kind === "float" || v.kind === "str" || v.kind === "bool")
    return formatScalar(v);
  if (v.kind === "none") return "·";
  return `→${v.id}`;
}

/** Label for a node's `next` pointer: the target node's value, "∅" when the
 *  next is None, or the raw id as a last resort if the target has no scalar. */
function nextLabel(n: LinkedListNode): string {
  if (!n.next) return "∅";
  return n.nextVal ? simpleValue(n.nextVal) : n.next;
}
