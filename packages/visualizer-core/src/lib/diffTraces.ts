import type { Trace, TraceEvent, Value } from "@dsa-viz/trace-schema";

export interface TraceDivergence {
  /** Event index in trace A where they first diverge. */
  aIndex: number;
  /** Event index in trace B where they first diverge. */
  bIndex: number;
  /** One-line reason. */
  reason: string;
}

export interface TraceDiff {
  diverged: boolean;
  divergence?: TraceDivergence;
  /** Length of the shared prefix (in events). */
  commonPrefix: number;
}

/**
 * Walk two traces in lockstep until they differ. Comparison is shape-only:
 * the line, top-of-stack function, and the locals (by name + simple value)
 * must agree. Cheap heuristic — designed for students comparing two near-
 * identical solutions, not for general program-equivalence.
 */
export function diffTraces(a: Trace, b: Trace): TraceDiff {
  const len = Math.min(a.events.length, b.events.length);
  for (let i = 0; i < len; i++) {
    const reason = compareEvents(a.events[i], b.events[i]);
    if (reason) {
      return { diverged: true, commonPrefix: i, divergence: { aIndex: i, bIndex: i, reason } };
    }
  }
  if (a.events.length !== b.events.length) {
    return {
      diverged: true,
      commonPrefix: len,
      divergence: {
        aIndex: len,
        bIndex: len,
        reason: `trace lengths differ (${a.events.length} vs ${b.events.length})`,
      },
    };
  }
  return { diverged: false, commonPrefix: len };
}

function compareEvents(a: TraceEvent, b: TraceEvent): string | null {
  if (a.kind !== b.kind) return `event kind ${a.kind} vs ${b.kind}`;
  if (a.line !== b.line) return `line ${a.line} vs ${b.line}`;
  if (a.stack.length !== b.stack.length) {
    return `stack depth ${a.stack.length} vs ${b.stack.length}`;
  }
  const topA = a.stack[a.stack.length - 1];
  const topB = b.stack[b.stack.length - 1];
  if (topA && topB && topA.func !== topB.func) {
    return `function ${topA.func} vs ${topB.func}`;
  }
  if (topA && topB) {
    const aLocals = topA.locals;
    const bLocals = topB.locals;
    const keys = new Set([...Object.keys(aLocals), ...Object.keys(bLocals)]);
    for (const key of keys) {
      const av = aLocals[key];
      const bv = bLocals[key];
      if (!av || !bv) {
        if (av || bv) return `local ${key} present in only one trace`;
        continue;
      }
      if (!sameValue(av, bv)) return `local ${key} differs (${describe(av)} vs ${describe(bv)})`;
    }
  }
  return null;
}

function sameValue(a: Value, b: Value): boolean {
  if (a.kind !== b.kind) return false;
  switch (a.kind) {
    case "int":
    case "float":
    case "str":
    case "bool":
      // SAFETY: discriminated on kind; b has the same shape.
      return (a as { v: unknown }).v === (b as { v: unknown }).v;
    case "none":
      return true;
    case "ref":
      // Two ref ids might point to the same logical shape — ignore for
      // the cheap diff so different runs don't always look different.
      return true;
  }
}

function describe(v: Value): string {
  switch (v.kind) {
    case "int":
    case "float":
      return String(v.v);
    case "bool":
      return v.v ? "true" : "false";
    case "str":
      return JSON.stringify(v.v);
    case "none":
      return "None";
    case "ref":
      return `ref(${v.id})`;
  }
}
