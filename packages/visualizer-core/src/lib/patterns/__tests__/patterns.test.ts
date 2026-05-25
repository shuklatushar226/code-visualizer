import { describe, expect, it } from "vitest";
import type { Frame, TraceEvent, Value } from "@dsa-viz/trace-schema";
import { activePatternHit, detectPatterns } from "../index";
import { detectSlidingWindow } from "../slidingWindow";
import { detectTwoPointer } from "../twoPointer";
import { detectBinarySearch } from "../binarySearch";

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
