import { describe, expect, it } from "vitest";
import type { HeapObject, Value } from "@dsa-viz/trace-schema";
import { detectStructure } from "../detectStructure";

const ref = (id: string): Value => ({ kind: "ref", id });

describe("detectStructure", () => {
  it("returns scalar for non-ref values", () => {
    expect(detectStructure({ kind: "int", v: 42 }, {})).toEqual({ kind: "scalar" });
    expect(detectStructure({ kind: "none" }, {})).toEqual({ kind: "scalar" });
  });

  it("returns scalar when the referenced heap object is missing", () => {
    expect(detectStructure(ref("h_missing"), {})).toEqual({ kind: "scalar" });
  });

  it("classifies a python list as an array", () => {
    const heap: Record<string, HeapObject> = {
      h_1: { kind: "list", items: [{ kind: "int", v: 1 }] },
    };
    expect(detectStructure(ref("h_1"), heap)).toEqual({ kind: "array", rootId: "h_1" });
  });

  it("classifies a tuple as an array with hint", () => {
    const heap: Record<string, HeapObject> = {
      h_1: { kind: "tuple", items: [{ kind: "int", v: 1 }, { kind: "int", v: 2 }] },
    };
    expect(detectStructure(ref("h_1"), heap)).toEqual({
      kind: "array",
      rootId: "h_1",
      hint: "tuple",
    });
  });

  it("classifies a set", () => {
    const heap: Record<string, HeapObject> = {
      h_1: { kind: "set", items: [] },
    };
    expect(detectStructure(ref("h_1"), heap)).toEqual({ kind: "set", rootId: "h_1" });
  });

  it("classifies an adjacency-style dict as a graph", () => {
    const heap: Record<string, HeapObject> = {
      h_root: {
        kind: "dict",
        entries: [
          [{ kind: "str", v: "A" }, ref("h_a")],
          [{ kind: "str", v: "B" }, ref("h_b")],
        ],
      },
      h_a: { kind: "list", items: [{ kind: "str", v: "B" }] },
      h_b: { kind: "list", items: [{ kind: "str", v: "A" }] },
    };
    expect(detectStructure(ref("h_root"), heap)).toEqual({
      kind: "graph",
      rootId: "h_root",
      hint: "adjacency-dict",
    });
  });

  it("classifies a plain dict (non-adjacency) as dict", () => {
    const heap: Record<string, HeapObject> = {
      h_1: {
        kind: "dict",
        entries: [[{ kind: "str", v: "k" }, { kind: "int", v: 1 }]],
      },
    };
    expect(detectStructure(ref("h_1"), heap)).toEqual({ kind: "dict", rootId: "h_1" });
  });

  it("classifies an empty dict as dict (not graph)", () => {
    const heap: Record<string, HeapObject> = {
      h_1: { kind: "dict", entries: [] },
    };
    expect(detectStructure(ref("h_1"), heap)).toEqual({ kind: "dict", rootId: "h_1" });
  });

  it("classifies a ListNode object as a linked list (by class name)", () => {
    const heap: Record<string, HeapObject> = {
      h_1: {
        kind: "object",
        type: "ListNode",
        fields: { val: { kind: "int", v: 1 }, next: { kind: "none" } },
      },
    };
    expect(detectStructure(ref("h_1"), heap)).toEqual({ kind: "linked_list", rootId: "h_1" });
  });

  it("classifies a TreeNode object as a tree (by class name)", () => {
    const heap: Record<string, HeapObject> = {
      h_1: {
        kind: "object",
        type: "TreeNode",
        fields: { val: { kind: "int", v: 1 }, left: { kind: "none" }, right: { kind: "none" } },
      },
    };
    expect(detectStructure(ref("h_1"), heap)).toEqual({ kind: "tree", rootId: "h_1" });
  });

  it("classifies an object with left+right fields as a tree even without a known class name", () => {
    const heap: Record<string, HeapObject> = {
      h_1: {
        kind: "object",
        type: "MyCustom",
        fields: { val: { kind: "int", v: 1 }, left: { kind: "none" }, right: { kind: "none" } },
      },
    };
    expect(detectStructure(ref("h_1"), heap)).toEqual({ kind: "tree", rootId: "h_1" });
  });

  it("infers linked-list shape from a single self-pointer field", () => {
    const heap: Record<string, HeapObject> = {
      h_1: {
        kind: "object",
        type: "Cell",
        fields: { v: { kind: "int", v: 1 }, link: ref("h_2") },
      },
      h_2: { kind: "object", type: "Cell", fields: { v: { kind: "int", v: 2 } } },
    };
    expect(detectStructure(ref("h_1"), heap)).toEqual({ kind: "linked_list", rootId: "h_1" });
  });

  it("infers tree shape from exactly two self-pointer fields", () => {
    const heap: Record<string, HeapObject> = {
      h_1: {
        kind: "object",
        type: "TwoPtr",
        fields: { v: { kind: "int", v: 1 }, a: ref("h_2"), b: ref("h_3") },
      },
      h_2: { kind: "object", type: "TwoPtr", fields: {} },
      h_3: { kind: "object", type: "TwoPtr", fields: {} },
    };
    expect(detectStructure(ref("h_1"), heap)).toEqual({ kind: "tree", rootId: "h_1" });
  });

  it("infers graph shape from three or more self-pointer fields", () => {
    const heap: Record<string, HeapObject> = {
      h_1: {
        kind: "object",
        type: "Knot",
        fields: { a: ref("h_2"), b: ref("h_3"), c: ref("h_4") },
      },
      h_2: { kind: "object", type: "Knot", fields: {} },
      h_3: { kind: "object", type: "Knot", fields: {} },
      h_4: { kind: "object", type: "Knot", fields: {} },
    };
    expect(detectStructure(ref("h_1"), heap)).toEqual({ kind: "graph", rootId: "h_1" });
  });

  it("falls back to object kind for plain structs with no self-pointers", () => {
    const heap: Record<string, HeapObject> = {
      h_1: {
        kind: "object",
        type: "Point",
        fields: { x: { kind: "int", v: 1 }, y: { kind: "int", v: 2 } },
      },
    };
    expect(detectStructure(ref("h_1"), heap)).toEqual({ kind: "object", rootId: "h_1" });
  });

  it("honors an explicit annotation, overriding inference", () => {
    const heap: Record<string, HeapObject> = {
      h_1: { kind: "list", items: [] },
    };
    expect(detectStructure(ref("h_1"), heap, "linked-list")).toEqual({
      kind: "linked_list",
      rootId: "h_1",
    });
  });
});
