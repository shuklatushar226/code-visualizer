import { describe, expect, it } from "vitest";
import type { Frame, TraceEvent } from "@dsa-viz/trace-schema";
import { buildRecursionTree, countCalls, findActiveCall } from "../recursionTree";

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
