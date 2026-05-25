import { describe, expect, it } from "vitest";
import type { Frame, Trace, TraceEvent, Value } from "@dsa-viz/trace-schema";
import { diffTraces } from "../diffTraces";

const v = (n: number): Value => ({ kind: "int", v: n });

const frame = (func: string, locals: Record<string, Value> = {}): Frame => ({
  func,
  file: "main.py",
  line: 1,
  locals,
  args: [],
});

const ev = (kind: TraceEvent["kind"], line: number, locals: Record<string, Value>): TraceEvent => ({
  t: 0,
  kind,
  line,
  file: "main.py",
  stack: [frame("solve", locals)],
  heap: {},
  stdout_delta: null,
  exception: null,
});

const trace = (events: TraceEvent[]): Trace => ({
  version: "0.1",
  language: "python",
  source: "",
  stdin: "",
  stdout: "",
  stderr: "",
  exit: { status: "ok", message: null, truncated: false },
  events,
});

describe("diffTraces", () => {
  it("reports no divergence for identical traces", () => {
    const a = trace([ev("step", 1, { x: v(1) }), ev("step", 2, { x: v(2) })]);
    const b = trace([ev("step", 1, { x: v(1) }), ev("step", 2, { x: v(2) })]);
    const d = diffTraces(a, b);
    expect(d.diverged).toBe(false);
    expect(d.commonPrefix).toBe(2);
  });

  it("flags a differing local value at the first event that disagrees", () => {
    const a = trace([ev("step", 1, { x: v(1) }), ev("step", 2, { x: v(2) })]);
    const b = trace([ev("step", 1, { x: v(1) }), ev("step", 2, { x: v(99) })]);
    const d = diffTraces(a, b);
    expect(d.diverged).toBe(true);
    expect(d.divergence?.aIndex).toBe(1);
    expect(d.divergence?.reason).toContain("x");
    expect(d.divergence?.reason).toContain("2");
    expect(d.divergence?.reason).toContain("99");
  });

  it("flags a differing line", () => {
    const a = trace([ev("step", 1, { x: v(1) }), ev("step", 2, { x: v(1) })]);
    const b = trace([ev("step", 1, { x: v(1) }), ev("step", 7, { x: v(1) })]);
    const d = diffTraces(a, b);
    expect(d.diverged).toBe(true);
    expect(d.divergence?.reason).toContain("line");
  });

  it("flags a length mismatch when one trace continues past the other", () => {
    const a = trace([ev("step", 1, { x: v(1) }), ev("step", 2, { x: v(1) })]);
    const b = trace([ev("step", 1, { x: v(1) })]);
    const d = diffTraces(a, b);
    expect(d.diverged).toBe(true);
    expect(d.divergence?.reason).toContain("lengths differ");
  });
});
