import type { TraceEvent } from "@dsa-viz/trace-schema";
import { intValue, topFrame, type PatternHit } from "./types";
import {
  countDistinctIncreases,
  frameRuns,
  isNonDecreasing,
} from "./utils";

const POINTER_NAMES = new Set([
  "l", "r", "left", "right", "start", "end", "i", "j", "lo", "hi", "low", "high",
]);

/**
 * A "sliding window" run has two int locals named like l/r (etc.) where both
 * are non-decreasing over the lifetime of one function invocation, and at
 * least one strictly advances at least twice. The pair brackets the window.
 */
export function detectSlidingWindow(events: TraceEvent[]): PatternHit[] {
  const out: PatternHit[] = [];

  for (const run of frameRuns(events)) {
    if (run.end - run.start < 2) continue;
    const startFrame = topFrame(events[run.start]);
    if (!startFrame) continue;

    const seenNames = new Set<string>();
    for (let k = run.start; k <= run.end; k++) {
      const f = topFrame(events[k]);
      if (!f || events[k].stack.length !== run.stackDepth) continue;
      for (const name of Object.keys(f.locals)) seenNames.add(name);
    }
    const candidates = Array.from(seenNames).filter((n) => POINTER_NAMES.has(n));
    if (candidates.length < 2) continue;

    const arrayLocalName = findArrayLocal(events, run, seenNames);

    let found = false;
    for (let i = 0; i < candidates.length && !found; i++) {
      for (let j = i + 1; j < candidates.length && !found; j++) {
        const a = candidates[i];
        const b = candidates[j];
        const aSeries: number[] = [];
        const bSeries: number[] = [];
        for (let k = run.start; k <= run.end; k++) {
          const frame = topFrame(events[k]);
          if (!frame || events[k].stack.length !== run.stackDepth) continue;
          const av = intValue(frame.locals[a]);
          const bv = intValue(frame.locals[b]);
          if (av == null || bv == null) continue;
          aSeries.push(av);
          bSeries.push(bv);
        }
        if (aSeries.length < 3) continue;
        if (!isNonDecreasing(aSeries) || !isNonDecreasing(bSeries)) continue;
        const aInc = countDistinctIncreases(aSeries);
        const bInc = countDistinctIncreases(bSeries);
        if (aInc + bInc < 2) continue;
        // Both monotonic advances suggest two pointers traversing one direction.
        out.push({
          kind: "sliding_window",
          startEvent: run.start,
          endEvent: run.end,
          stackDepth: run.stackDepth,
          pointerLocals: [a, b],
          arrayLocalName,
        });
        found = true;
      }
    }
  }
  return out;
}

function findArrayLocal(
  events: TraceEvent[],
  run: { start: number; end: number; stackDepth: number },
  seenNames: Set<string>,
): string | undefined {
  for (let k = run.start; k <= run.end; k++) {
    const f = topFrame(events[k]);
    if (!f || events[k].stack.length !== run.stackDepth) continue;
    for (const name of seenNames) {
      const value = f.locals[name];
      if (!value || value.kind !== "ref") continue;
      const obj = events[k].heap[value.id];
      if (obj && (obj.kind === "list" || obj.kind === "tuple" || obj.kind === "object")) {
        return name;
      }
    }
  }
  return undefined;
}
