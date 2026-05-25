import type { TraceEvent } from "@dsa-viz/trace-schema";

export interface FrameRun {
  start: number;
  end: number;
  stackDepth: number;
  func: string;
}

/**
 * Partition events into call-bounded runs. Each `call` opens a new run at
 * the current stack depth; the matching `return` (or end of trace) closes
 * it. Step/exception/stdout events extend the open run at their depth.
 *
 * Two recursive calls of the same function produce two separate runs, so
 * pattern detection scoped to a single function invocation can iterate
 * over these runs independently.
 */
export function frameRuns(events: TraceEvent[]): FrameRun[] {
  const runs: FrameRun[] = [];
  const open: { runIdx: number; depth: number }[] = [];

  events.forEach((ev, i) => {
    if (ev.kind === "call") {
      const top = ev.stack[ev.stack.length - 1];
      if (!top) return;
      const depth = ev.stack.length;
      while (open.length > 0 && open[open.length - 1].depth >= depth) {
        const last = open.pop()!;
        runs[last.runIdx].end = i - 1;
      }
      runs.push({ start: i, end: i, stackDepth: depth, func: top.func });
      open.push({ runIdx: runs.length - 1, depth });
    } else if (ev.kind === "return") {
      if (open.length > 0) {
        const last = open.pop()!;
        runs[last.runIdx].end = i;
      }
    } else if (open.length > 0) {
      const last = open[open.length - 1];
      runs[last.runIdx].end = i;
    }
  });

  // Close any still-open runs.
  const lastIdx = events.length - 1;
  while (open.length > 0) {
    const last = open.pop()!;
    if (runs[last.runIdx].end < lastIdx) runs[last.runIdx].end = lastIdx;
  }

  return runs;
}

export function isStrictlyIncreasing(xs: number[]): boolean {
  for (let i = 1; i < xs.length; i++) if (xs[i] <= xs[i - 1]) return false;
  return xs.length >= 2;
}

export function isNonDecreasing(xs: number[]): boolean {
  for (let i = 1; i < xs.length; i++) if (xs[i] < xs[i - 1]) return false;
  return true;
}

export function isNonIncreasing(xs: number[]): boolean {
  for (let i = 1; i < xs.length; i++) if (xs[i] > xs[i - 1]) return false;
  return true;
}

export function countDistinctIncreases(xs: number[]): number {
  let n = 0;
  for (let i = 1; i < xs.length; i++) if (xs[i] > xs[i - 1]) n++;
  return n;
}

export function countDistinctDecreases(xs: number[]): number {
  let n = 0;
  for (let i = 1; i < xs.length; i++) if (xs[i] < xs[i - 1]) n++;
  return n;
}
