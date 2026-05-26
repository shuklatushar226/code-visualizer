import { describe, expect, it } from "vitest";
import type { Frame, TraceEvent, Value } from "@dsa-viz/trace-schema";
import {
  buildRecursionTree,
  countCalls,
  findActiveCall,
  formatArgs,
  formatArgValue,
} from "../recursionTree";

const frame = (func: string, locals: Record<string, number> = {}, args: string[] = []): Frame => ({
  func,
  file: "main.py",
  line: 1,
  locals: Object.fromEntries(
    Object.entries(locals).map(([k, v]) => [k, { kind: "int", v }]),
  ),
  args,
});

const ev = (kind: TraceEvent["kind"], stack: Frame[]): TraceEvent => ({
  t: 0,
  kind,
  line: 1,
  file: "main.py",
  stack,
  heap: {},
  stdout_delta: null,
  exception: null,
});

describe("buildRecursionTree", () => {
  it("handles an empty trace", () => {
    const root = buildRecursionTree([]);
    expect(root.id).toBe("root");
    expect(root.children).toEqual([]);
    expect(countCalls(root)).toBe(0);
  });

  it("captures push/pop of a single nested call", () => {
    const m = frame("<module>");
    const inner = frame("inner", { x: 1 }, ["x"]);
    const events: TraceEvent[] = [
      ev("call", [m]),
      ev("step", [m]),
      ev("call", [m, inner]),
      ev("step", [m, inner]),
      ev("return", [m, inner]),
      ev("step", [m]),
      ev("return", [m]),
    ];
    const root = buildRecursionTree(events);
    expect(countCalls(root)).toBe(2); // <module> + inner
    const module = root.children[0];
    expect(module.func).toBe("<module>");
    expect(module.endEvent).toBe(6);
    const innerNode = module.children[0];
    expect(innerNode.func).toBe("inner");
    expect(innerNode.startEvent).toBe(2);
    expect(innerNode.endEvent).toBe(4);
    expect(innerNode.args).toEqual({ x: { kind: "int", v: 1 } });
  });

  it("captures a fibonacci-shaped tree (fib(3) = 5 calls)", () => {
    const m = frame("<module>");
    const f3 = frame("fib", { n: 3 }, ["n"]);
    const f2 = frame("fib", { n: 2 }, ["n"]);
    const f1 = frame("fib", { n: 1 }, ["n"]);
    const f0 = frame("fib", { n: 0 }, ["n"]);
    const f1b = frame("fib", { n: 1 }, ["n"]);

    const events: TraceEvent[] = [
      ev("call", [m]),
      ev("call", [m, f3]),
      ev("call", [m, f3, f2]),
      ev("call", [m, f3, f2, f1]),
      ev("return", [m, f3, f2, f1]),
      // fib(1) returned, now fib(2) calls fib(0) — same total depth (4) but a new call
      ev("call", [m, f3, f2, f0]),
      ev("return", [m, f3, f2, f0]),
      ev("return", [m, f3, f2]),
      ev("call", [m, f3, f1b]),
      ev("return", [m, f3, f1b]),
      ev("return", [m, f3]),
      ev("return", [m]),
    ];
    const root = buildRecursionTree(events);
    expect(countCalls(root)).toBe(6); // <module> + 5 fib

    const module = root.children[0];
    const fib3 = module.children[0];
    expect(fib3.func).toBe("fib");
    expect(fib3.children).toHaveLength(2); // fib(2) and second fib(1)
    const fib2 = fib3.children[0];
    expect(fib2.children).toHaveLength(2); // fib(1) and fib(0)
    expect(fib2.children[0].args).toEqual({ n: { kind: "int", v: 1 } });
    expect(fib2.children[1].args).toEqual({ n: { kind: "int", v: 0 } });
  });

  it("ignores step / exception / stdout kinds (tree only changes on call/return)", () => {
    const m = frame("<module>");
    const events: TraceEvent[] = [
      ev("call", [m]),
      ev("step", [m]),
      ev("exception", [m]),
      ev("stdout", [m]),
      ev("step", [m]),
      ev("return", [m]),
    ];
    const root = buildRecursionTree(events);
    expect(countCalls(root)).toBe(1);
  });
});

describe("maxNodes cap", () => {
  it("stops growing the tree once maxNodes real frames exist and marks the parent as truncated", () => {
    // Synthesize 10 nested calls; cap at 3.
    const stack: Frame[] = [];
    const events: TraceEvent[] = [];
    for (let i = 0; i < 10; i++) {
      stack.push(frame(`f${i}`, { n: i }, ["n"]));
      events.push(ev("call", stack.slice()));
    }
    while (stack.length > 0) {
      events.push(ev("return", stack.slice()));
      stack.pop();
    }

    const root = buildRecursionTree(events, { maxNodes: 3 });
    expect(countCalls(root)).toBe(3); // only 3 real nodes
    // Walk to the deepest real frame; it should have a single +more child.
    let cur = root.children[0];
    while (cur && !cur.truncated) {
      const next = cur.children.find((c) => !c.truncated);
      if (!next) break;
      cur = next;
    }
    // At the cap boundary the last real node has a +more sibling.
    const reachedSomeTruncated = JSON.stringify(root).includes('"truncated":true');
    expect(reachedSomeTruncated).toBe(true);
  });
});

describe("formatArgValue", () => {
  it("renders primitives as Python-style literals", () => {
    expect(formatArgValue({ kind: "int", v: 42 })).toBe("42");
    expect(formatArgValue({ kind: "float", v: 3.14 })).toBe("3.14");
    expect(formatArgValue({ kind: "bool", v: true })).toBe("True");
    expect(formatArgValue({ kind: "bool", v: false })).toBe("False");
    expect(formatArgValue({ kind: "none" })).toBe("None");
  });

  it("shortens heap refs to the last 4 digits with an arrow", () => {
    expect(formatArgValue({ kind: "ref", id: "h_4344566304" })).toBe("→6304");
    // Even for short ids the arrow + last-up-to-4 holds.
    expect(formatArgValue({ kind: "ref", id: "h_7" })).toBe("→7");
  });

  it("truncates long strings with an ellipsis", () => {
    const short = formatArgValue({ kind: "str", v: "hi" });
    expect(short).toBe('"hi"');
    const long = formatArgValue({ kind: "str", v: "a very long string indeed" });
    expect(long.length).toBeLessThanOrEqual(14);
    expect(long.endsWith("…")).toBe(true);
  });
});

describe("formatArgs", () => {
  const ref = (id: string): Value => ({ kind: "ref", id });
  const num = (v: number): Value => ({ kind: "int", v });

  it("drops Python's implicit self so the distinguishing val survives", () => {
    expect(formatArgs({ self: ref("h_4430016736"), val: num(1) })).toBe("val=1");
  });

  it("renders simple integer args verbatim", () => {
    expect(formatArgs({ n: num(6) })).toBe("n=6");
  });

  it("shortens ref args to the last-4 form", () => {
    expect(formatArgs({ head: ref("h_4344566304") })).toBe("head=→6304");
  });

  it("caps the joined label at 32 chars with a trailing ellipsis", () => {
    const args: Record<string, Value> = {};
    "abcdefghijklmnopqrstuvwxyz".split("").forEach((letter, i) => {
      args[letter] = num(i);
    });
    const out = formatArgs(args);
    expect(out.length).toBeLessThanOrEqual(32);
    expect(out.endsWith("…")).toBe(true);
  });

  it("renders None and True without quoting", () => {
    expect(formatArgs({ x: { kind: "none" }, y: { kind: "bool", v: true } })).toBe(
      "x=None, y=True",
    );
  });

  it("regression: four Node(N) calls produce visually distinct labels", () => {
    // This is the exact bug the user spotted in the screenshot — before the
    // fix all four __init__ nodes rendered as `self=h_xxxx, val=…` and
    // looked identical. After the fix they must each show their unique val.
    const sharedSelf = ref("h_4430016736");
    const labels = [1, 2, 3, 4].map((n) =>
      formatArgs({ self: sharedSelf, val: num(n) }),
    );
    expect(labels).toEqual(["val=1", "val=2", "val=3", "val=4"]);
    expect(new Set(labels).size).toBe(4); // explicit uniqueness check
  });
});

describe("findActiveCall", () => {
  it("returns null for a t that falls outside every call", () => {
    expect(findActiveCall(buildRecursionTree([]), 0, 0)).toBeNull();
  });

  it("returns the deepest open frame at t", () => {
    const m = frame("<module>");
    const a = frame("a");
    const b = frame("b");
    const events: TraceEvent[] = [
      ev("call", [m]),
      ev("call", [m, a]),
      ev("call", [m, a, b]),
      ev("return", [m, a, b]),
      ev("return", [m, a]),
      ev("return", [m]),
    ];
    const root = buildRecursionTree(events);
    const last = events.length - 1;
    // At t=2 (during b's life): expect b.
    expect(findActiveCall(root, 2, last)?.func).toBe("b");
    // At t=4 (b returned, in a): expect a.
    expect(findActiveCall(root, 4, last)?.func).toBe("a");
    // At t=5 (a returned, in <module>): expect <module>.
    expect(findActiveCall(root, 5, last)?.func).toBe("<module>");
  });
});
