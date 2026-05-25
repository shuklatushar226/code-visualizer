import type { TraceEvent } from "@dsa-viz/trace-schema";
import { intValue, topFrame, type PatternHit } from "./types";
import {
  countDistinctDecreases,
  countDistinctIncreases,
  frameRuns,
  isNonDecreasing,
  isNonIncreasing,
} from "./utils";

const POINTER_NAMES = new Set([
  "l", "r", "left", "right", "i", "j", "lo", "hi", "low", "high", "start", "end",
]);

/**
 * A "two pointer" run has two int locals where one is non-decreasing and the
 * other is non-increasing over a function invocation. The pointers move
 * toward each other (or away, but inward is the common case).
 */
export function detectTwoPointer(events: TraceEvent[]): PatternHit[] {
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

        const aIncs = countDistinctIncreases(aSeries);
        const aDecs = countDistinctDecreases(aSeries);
        const bIncs = countDistinctIncreases(bSeries);
        const bDecs = countDistinctDecreases(bSeries);

        const aUpBDown =
          isNonDecreasing(aSeries) && isNonIncreasing(bSeries) &&
          aIncs >= 1 && bDecs >= 1 && aIncs + bDecs >= 2;
        const aDownBUp =
          isNonIncreasing(aSeries) && isNonDecreasing(bSeries) &&
          aDecs >= 1 && bIncs >= 1 && aDecs + bIncs >= 2;

        if (aUpBDown || aDownBUp) {
          // Order pointers so [0] is the one that increases (acts as `lo`).
          const orderedPair = aUpBDown ? [a, b] : [b, a];
          out.push({
            kind: "two_pointer",
            startEvent: run.start,
            endEvent: run.end,
            stackDepth: run.stackDepth,
            pointerLocals: orderedPair,
            arrayLocalName: findArrayLocal(events, run, seenNames),
          });
          found = true;
        }
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
