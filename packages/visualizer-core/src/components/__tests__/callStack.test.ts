import { describe, expect, it } from "vitest";
import type { HeapObject, Value } from "@dsa-viz/trace-schema";
import { describeReference } from "../../lib/describeReference";

const ref = (id: string): Extract<Value, { kind: "ref" }> => ({ kind: "ref", id });

describe("describeReference", () => {
  it("shows a linked-list node's value instead of its runtime heap id", () => {
    const heap: Record<string, HeapObject> = {
      h_124736813953104: {
        kind: "object",
        type: "Node",
        fields: {
          val: { kind: "int", v: 4 },
          next: { kind: "none" },
        },
      },
    };

    expect(describeReference(ref("h_124736813953104"), heap)).toBe("Node(4)");
  });

  it("summarizes collections by type and size", () => {
    const heap: Record<string, HeapObject> = {
      h_items: {
        kind: "list",
        items: [{ kind: "int", v: 1 }, { kind: "int", v: 2 }],
      },
    };

    expect(describeReference(ref("h_items"), heap)).toBe("list[2]");
  });

  it("uses a stable fallback when a reference is not in the snapshot", () => {
    expect(describeReference(ref("h_missing"), {})).toBe("reference");
  });
});
