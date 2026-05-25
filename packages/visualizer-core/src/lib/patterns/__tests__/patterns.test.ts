import { describe, expect, it } from "vitest";
import type { Frame, HeapObject, TraceEvent, Value } from "@dsa-viz/trace-schema";
import { activePatternHit, detectPatterns } from "../index";
import { detectSlidingWindow } from "../slidingWindow";
import { detectTwoPointer } from "../twoPointer";
import { detectBinarySearch } from "../binarySearch";
import { detectDP } from "../dp";

const v = (n: number): Value => ({ kind: "int", v: n });

const frame = (func: string, locals: Record<string, Value> = {}): Frame => ({
  func,
  file: "main.py",
  line: 1,
  locals,
  args: Object.keys(locals),
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

/** Build a run of step events with the given top-frame locals at each step. */
function steps(func: string, perStep: Record<string, Value>[]): TraceEvent[] {
  const m = frame("<module>");
  const out: TraceEvent[] = [
    ev("call", [m]),
    ev("call", [m, frame(func, perStep[0])]),
  ];
  for (const locals of perStep) {
    out.push(ev("step", [m, frame(func, locals)]));
  }
  out.push(ev("return", [m, frame(func, perStep[perStep.length - 1])]));
  out.push(ev("return", [m]));
  return out;
}

describe("detectSlidingWindow", () => {
  it("fires on l/r both advancing forward", () => {
    const events = steps("solve", [
      { l: v(0), r: v(0) },
      { l: v(0), r: v(1) },
      { l: v(0), r: v(2) },
      { l: v(1), r: v(2) },
      { l: v(1), r: v(3) },
    ]);
    const hits = detectSlidingWindow(events);
    expect(hits).toHaveLength(1);
    expect(hits[0].pointerLocals.sort()).toEqual(["l", "r"]);
  });

  it("does not fire when r decreases", () => {
    const events = steps("solve", [
      { l: v(0), r: v(3) },
      { l: v(0), r: v(2) },
      { l: v(0), r: v(1) },
    ]);
    expect(detectSlidingWindow(events)).toHaveLength(0);
  });

  it("does not fire on a constant loop variable pair", () => {
    const events = steps("solve", [
      { l: v(0), r: v(0) },
      { l: v(0), r: v(0) },
      { l: v(0), r: v(0) },
    ]);
    expect(detectSlidingWindow(events)).toHaveLength(0);
  });
});

describe("detectTwoPointer", () => {
  it("fires on i moving forward, j moving backward", () => {
    const events = steps("solve", [
      { i: v(0), j: v(5) },
      { i: v(1), j: v(4) },
      { i: v(2), j: v(3) },
    ]);
    const hits = detectTwoPointer(events);
    expect(hits).toHaveLength(1);
    expect(hits[0].pointerLocals).toEqual(["i", "j"]);
  });

  it("does not fire when both move the same direction", () => {
    const events = steps("solve", [
      { i: v(0), j: v(0) },
      { i: v(1), j: v(1) },
      { i: v(2), j: v(2) },
    ]);
    expect(detectTwoPointer(events)).toHaveLength(0);
  });
});

describe("detectBinarySearch", () => {
  it("fires on classic lo/hi/mid with halving range", () => {
    const events = steps("solve", [
      { lo: v(0), hi: v(7), mid: v(3) },
      { lo: v(4), hi: v(7), mid: v(5) },
      { lo: v(4), hi: v(4), mid: v(4) },
    ]);
    const hits = detectBinarySearch(events);
    expect(hits).toHaveLength(1);
    expect(hits[0].pointerLocals).toEqual(["lo", "hi", "mid"]);
  });

  it("does not fire when mid does not equal floor((lo+hi)/2)", () => {
    const events = steps("solve", [
      { lo: v(0), hi: v(7), mid: v(0) },
      { lo: v(0), hi: v(7), mid: v(1) },
      { lo: v(0), hi: v(7), mid: v(2) },
    ]);
    expect(detectBinarySearch(events)).toHaveLength(0);
  });

  it("does not fire when the range does not shrink", () => {
    const events = steps("solve", [
      { lo: v(0), hi: v(7), mid: v(3) },
      { lo: v(0), hi: v(7), mid: v(3) },
      { lo: v(0), hi: v(7), mid: v(3) },
    ]);
    expect(detectBinarySearch(events)).toHaveLength(0);
  });
});

/** Build a steps trace where the heap contains a list at heap[h_arr] and each
 * step snapshots the list's items array.  Locals at each step include
 * `dp -> ref(h_arr)`. */
function stepsWithArray(func: string, perStep: Value[][]): TraceEvent[] {
  const m = frame("<module>");
  const out: TraceEvent[] = [
    ev("call", [m]),
    ev("call", [m, frame(func, { dp: { kind: "ref", id: "h_arr" } })]),
  ];
  for (const items of perStep) {
    const heap: Record<string, HeapObject> = { h_arr: { kind: "list", items } };
    out.push({
      t: 0,
      kind: "step",
      line: 1,
      file: "main.py",
      stack: [m, frame(func, { dp: { kind: "ref", id: "h_arr" } })],
      heap,
      stdout_delta: null,
      exception: null,
    });
  }
  out.push(ev("return", [m, frame(func, { dp: { kind: "ref", id: "h_arr" } })]));
  out.push(ev("return", [m]));
  return out;
}

describe("false-positive avoidance", () => {
  it("sliding window does not fire on a plain counter that never moves twice", () => {
    // Single advance — below the >=2 total-movements floor.
    const events = steps("solve", [
      { l: v(0), r: v(0) },
      { l: v(0), r: v(1) },
    ]);
    expect(detectSlidingWindow(events)).toHaveLength(0);
  });

  it("sliding window does not fire on a constant pair", () => {
    const events = steps("solve", [
      { l: v(3), r: v(7) },
      { l: v(3), r: v(7) },
      { l: v(3), r: v(7) },
      { l: v(3), r: v(7) },
    ]);
    expect(detectSlidingWindow(events)).toHaveLength(0);
  });

  it("two pointer does not fire on a simple nested-loop scan (both indices increase)", () => {
    const events = steps("solve", [
      { i: v(0), j: v(0) },
      { i: v(0), j: v(1) },
      { i: v(0), j: v(2) },
      { i: v(1), j: v(0) },
      { i: v(1), j: v(1) },
      { i: v(1), j: v(2) },
    ]);
    // j goes 0,1,2,0,1,2 — not monotone, so detector should bail.
    expect(detectTwoPointer(events)).toHaveLength(0);
  });

  it("two pointer does not fire when only one side moves", () => {
    const events = steps("solve", [
      { i: v(0), j: v(5) },
      { i: v(1), j: v(5) },
      { i: v(2), j: v(5) },
    ]);
    expect(detectTwoPointer(events)).toHaveLength(0);
  });

  it("binary search does not fire on a linear scan that happens to define lo/hi/mid", () => {
    // mid follows lo+1, not floor((lo+hi)/2). Range never halves.
    const events = steps("solve", [
      { lo: v(0), hi: v(10), mid: v(1) },
      { lo: v(1), hi: v(10), mid: v(2) },
      { lo: v(2), hi: v(10), mid: v(3) },
      { lo: v(3), hi: v(10), mid: v(4) },
    ]);
    expect(detectBinarySearch(events)).toHaveLength(0);
  });

  it("binary search does not fire when mid changes but the invariant breaks once", () => {
    // mid is right on the first iteration but wrong on the second.
    const events = steps("solve", [
      { lo: v(0), hi: v(7), mid: v(3) },
      { lo: v(4), hi: v(7), mid: v(99) }, // 99 != floor((4+7)/2)=5
      { lo: v(4), hi: v(4), mid: v(4) },
    ]);
    expect(detectBinarySearch(events)).toHaveLength(0);
  });
});

describe("detectDP", () => {
  it("fires on an array that fills cells in strict index order", () => {
    const INF: Value = { kind: "int", v: 999 };
    const events = stepsWithArray("solve", [
      [INF, INF, INF, INF, INF],
      [v(0), INF, INF, INF, INF],
      [v(0), v(1), INF, INF, INF],
      [v(0), v(1), v(2), INF, INF],
      [v(0), v(1), v(2), v(3), INF],
      [v(0), v(1), v(2), v(3), v(4)],
    ]);
    const hits = detectDP(events);
    expect(hits).toHaveLength(1);
    expect(hits[0].arrayLocalName).toBe("dp");
  });

  it("does not fire when the array changes in arbitrary order", () => {
    const INF: Value = { kind: "int", v: 999 };
    const events = stepsWithArray("solve", [
      [INF, INF, INF, INF],
      [INF, INF, INF, v(4)],   // cell 3 first
      [INF, v(1), INF, v(4)],  // then cell 1
      [v(0), v(1), INF, v(4)], // then cell 0 — out of order
    ]);
    expect(detectDP(events)).toHaveLength(0);
  });

  it("does not fire when fewer than 3 cells fill", () => {
    const INF: Value = { kind: "int", v: 999 };
    const events = stepsWithArray("solve", [
      [INF, INF, INF, INF],
      [v(0), INF, INF, INF],
      [v(0), v(1), INF, INF],
    ]);
    expect(detectDP(events)).toHaveLength(0);
  });
});

describe("detectPatterns orchestrator", () => {
  it("prefers binary search over sliding window when both could apply", () => {
    const events = steps("solve", [
      { lo: v(0), hi: v(7), mid: v(3) },
      { lo: v(4), hi: v(7), mid: v(5) },
      { lo: v(4), hi: v(4), mid: v(4) },
    ]);
    const hits = detectPatterns(events);
    expect(hits).toHaveLength(1);
    expect(hits[0].kind).toBe("binary_search");
  });

  it("returns empty for a constant trace", () => {
    const events = steps("solve", [{ x: v(1) }, { x: v(1) }, { x: v(1) }]);
    expect(detectPatterns(events)).toHaveLength(0);
  });
});

describe("activePatternHit", () => {
  it("returns the deepest hit covering t", () => {
    const events = steps("solve", [
      { i: v(0), j: v(5) },
      { i: v(1), j: v(4) },
      { i: v(2), j: v(3) },
    ]);
    const hits = detectPatterns(events);
    expect(hits).toHaveLength(1);
    const start = hits[0].startEvent;
    const end = hits[0].endEvent;
    expect(activePatternHit(hits, start)?.kind).toBe("two_pointer");
    expect(activePatternHit(hits, end)?.kind).toBe("two_pointer");
    expect(activePatternHit(hits, end + 99)).toBeNull();
  });
});
