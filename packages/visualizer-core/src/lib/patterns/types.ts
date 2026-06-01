import type { Frame, TraceEvent, Value } from "@dsa-viz/trace-schema";

export type PatternKind = "sliding_window" | "two_pointer" | "binary_search" | "dp";

export interface PatternHit {
  kind: PatternKind;
  startEvent: number;
  endEvent: number;
  stackDepth: number;
  /** Ordered names of the relevant int locals. */
  pointerLocals: string[];
  /** Optional: name of an array-typed local in the same frame. */
  arrayLocalName?: string;
}

export function topFrame(ev: TraceEvent): Frame | undefined {
  return ev.stack[ev.stack.length - 1];
}

export function intValue(v: Value | undefined): number | null {
  // `v.v` may be a string for ints beyond 2**53; pattern indices are always
  // small array positions, so coercing to a number here is safe.
  return v?.kind === "int" ? Number(v.v) : null;
}
