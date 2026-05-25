import type { HeapObject, Value } from "@dsa-viz/trace-schema";

export type StructureKind =
  | "array"
  | "linked_list"
  | "tree"
  | "graph"
  | "stack"
  | "queue"
  | "heap"
  | "dict"
  | "set"
  | "object"
  | "scalar";

export interface DetectedStructure {
  kind: StructureKind;
  rootId?: string;
  hint?: string;
}

/**
 * Inspect a Value (possibly a reference into the heap) and infer what DSA
 * structure it most likely represents. The result drives which renderer the
 * HeapView mounts. This is intentionally heuristic; the trace can also carry
 * an explicit `# @viz: linked-list` annotation that overrides detection.
 */
export function detectStructure(
  value: Value,
  heap: Record<string, HeapObject>,
  annotation?: string,
): DetectedStructure {
  if (annotation) {
    const k = annotation.replace(/-/g, "_") as StructureKind;
    return { kind: k, rootId: value.kind === "ref" ? value.id : undefined };
  }

  if (value.kind !== "ref") {
    return { kind: "scalar" };
  }

  const obj = heap[value.id];
  if (!obj) return { kind: "scalar" };

  if (obj.kind === "list") {
    return { kind: "array", rootId: value.id };
  }
  if (obj.kind === "dict") {
    // adjacency list?  values are all lists/sets of refs -> graph
    if (looksLikeAdjacency(obj, heap)) {
      return { kind: "graph", rootId: value.id, hint: "adjacency-dict" };
    }
    return { kind: "dict", rootId: value.id };
  }
  if (obj.kind === "set") {
    return { kind: "set", rootId: value.id };
  }
  if (obj.kind === "object") {
    const cls = obj.type.toLowerCase();
    const fields = Object.keys(obj.fields);

    // explicit naming wins
    if (/listnode|node/.test(cls) && fields.includes("next")) {
      return { kind: "linked_list", rootId: value.id };
    }
    if (/treenode/.test(cls) || (fields.includes("left") && fields.includes("right"))) {
      return { kind: "tree", rootId: value.id };
    }

    // single self-pointer => linked list
    const selfPtrs = fields.filter((f) => {
      const v = obj.fields[f];
      return v.kind === "ref" && (heap[v.id]?.kind === "object");
    });
    if (selfPtrs.length === 1) return { kind: "linked_list", rootId: value.id };
    if (selfPtrs.length === 2) return { kind: "tree", rootId: value.id };
    if (selfPtrs.length >= 3) return { kind: "graph", rootId: value.id };

    return { kind: "object", rootId: value.id };
  }
  if (obj.kind === "tuple") {
    return { kind: "array", rootId: value.id, hint: "tuple" };
  }

  return { kind: "scalar" };
}

function looksLikeAdjacency(
  obj: HeapObject & { kind: "dict" },
  heap: Record<string, HeapObject>,
): boolean {
  if (obj.entries.length === 0) return false;
  for (const [, v] of obj.entries) {
    if (v.kind !== "ref") return false;
    const inner = heap[v.id];
    if (!inner) return false;
    if (inner.kind !== "list" && inner.kind !== "set") return false;
  }
  return true;
}
