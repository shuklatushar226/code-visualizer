import { describe, expect, it } from "vitest";
import type { HeapObject } from "@dsa-viz/trace-schema";
import { walkList } from "../LinkedListView";

const node = (val: number, nextId?: string): HeapObject => ({
  kind: "object",
  type: "Node",
  fields: {
    val: { kind: "int", v: val },
    next: nextId ? { kind: "ref", id: nextId } : { kind: "none" },
  },
});

describe("walkList nextVal", () => {
  it("exposes the value of the node each `next` points to", () => {
    const heap: Record<string, HeapObject> = {
      h_1: node(1, "h_2"),
      h_2: node(2, "h_3"),
      h_3: node(3), // tail: next = None
    };
    const res = walkList("h_1", heap);
    expect(res).not.toBeNull();
    const vals = res!.list.map((n) => n.val);
    // sanity: the chain values themselves are still correct
    expect(vals.map((v) => (v as { v: number }).v)).toEqual([1, 2, 3]);
    // the fix: each node knows the *value* it points to, not just a raw id
    expect((res!.list[0].nextVal as { v: number } | undefined)?.v).toBe(2);
    expect((res!.list[1].nextVal as { v: number } | undefined)?.v).toBe(3);
    // tail points at nothing
    expect(res!.list[2].nextVal).toBeUndefined();
  });

  it("resolves nextVal across a cycle (tail points back to an earlier node)", () => {
    const heap: Record<string, HeapObject> = {
      h_1: node(1, "h_2"),
      h_2: node(2, "h_1"), // cycle back to h_1 (value 1)
    };
    const res = walkList("h_1", heap);
    expect(res!.cycle).toBe("h_1");
    expect((res!.list[1].nextVal as { v: number } | undefined)?.v).toBe(1);
  });
});
