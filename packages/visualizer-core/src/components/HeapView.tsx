import React from "react";
import type { Frame, HeapObject } from "@dsa-viz/trace-schema";
import { detectStructure } from "../lib/detectStructure";
import { ArrayView } from "./structures/ArrayView";
import { LinkedListView } from "./structures/LinkedListView";
import { TreeView } from "./structures/TreeView";
import { GraphView } from "./structures/GraphView";
import { StackView } from "./structures/StackView";
import { QueueView } from "./structures/QueueView";
import { HeapTreeView } from "./structures/HeapTreeView";

export interface HeapViewProps {
  heap: Record<string, HeapObject>;
  frame?: Frame;
  /** local-name -> annotation (`linked-list`, `tree`, `graph`, `stack`, ...) */
  annotations: Record<string, string>;
}

/**
 * Picks the right structure renderer for each named local that points into the
 * heap. Scalars are rendered in the CallStack already, so this view focuses on
 * heap objects worth visualizing as a 2-D structure.
 */
export const HeapView: React.FC<HeapViewProps> = ({ heap, frame, annotations }) => {
  if (!frame) return null;
  const entries = Object.entries(frame.locals);

  const visible = entries.filter(([, v]) => v.kind === "ref");
  if (visible.length === 0) {
    return (
      <div className="dsa-viz-heapview is-empty">
        <em>No structured locals at this step.</em>
      </div>
    );
  }

  return (
    <div className="dsa-viz-heapview">
      {visible.map(([name, value]) => {
        const det = detectStructure(value, heap, annotations[name]);
        return (
          <section key={name} className="dsa-viz-heap-card" data-kind={det.kind}>
            <header>
              <strong>{name}</strong>
              <span className="dsa-viz-heap-kind">{det.kind}</span>
            </header>
            <Renderer kind={det.kind} rootId={det.rootId} heap={heap} />
          </section>
        );
      })}
    </div>
  );
};

const Renderer: React.FC<{
  kind: string;
  rootId?: string;
  heap: Record<string, HeapObject>;
}> = ({ kind, rootId, heap }) => {
  if (!rootId) return null;
  switch (kind) {
    case "array":
      return <ArrayView rootId={rootId} heap={heap} />;
    case "linked_list":
      return <LinkedListView rootId={rootId} heap={heap} />;
    case "tree":
      return <TreeView rootId={rootId} heap={heap} />;
    case "graph":
      return <GraphView rootId={rootId} heap={heap} />;
    case "stack":
      return <StackView rootId={rootId} heap={heap} />;
    case "queue":
      return <QueueView rootId={rootId} heap={heap} />;
    case "heap":
      return <HeapTreeView rootId={rootId} heap={heap} />;
    default:
      return <ArrayView rootId={rootId} heap={heap} fallback />;
  }
};
