import type { TraceEvent } from "@dsa-viz/trace-schema";
import { intValue, topFrame, type PatternHit } from "./types";
import { frameRuns } from "./utils";

const LO_NAMES = ["lo", "low", "left", "l"];
const HI_NAMES = ["hi", "high", "right", "r"];
const MID_NAMES = ["mid", "m", "middle"];

/**
 * Binary-search runs have three int locals (lo, hi, mid) where, at each
 * observed event, mid = floor((lo + hi) / 2) and the (hi - lo) range
 * trends downward (the search space halves).
 */
export function detectBinarySearch(events: TraceEvent[]): PatternHit[] {
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
    const lo = LO_NAMES.find((n) => seenNames.has(n));
    const hi = HI_NAMES.find((n) => seenNames.has(n));
    const mid = MID_NAMES.find((n) => seenNames.has(n));
    if (!lo || !hi || !mid) continue;

    const series: { lo: number; hi: number; mid: number }[] = [];
    for (let k = run.start; k <= run.end; k++) {
      const frame = topFrame(events[k]);
      if (!frame || events[k].stack.length !== run.stackDepth) continue;
      const loV = intValue(frame.locals[lo]);
      const hiV = intValue(frame.locals[hi]);
      const midV = intValue(frame.locals[mid]);
      if (loV == null || hiV == null || midV == null) continue;
      series.push({ lo: loV, hi: hiV, mid: midV });
    }

    if (series.length < 3) continue;

    // Only check the invariant at events where `mid` just changed — those
    // are the moments the assignment fired. Between iterations the loop
    // header sees stale lo/hi/mid (Python doesn't clear locals).
    const changeIdx: number[] = [];
    for (let k = 0; k < series.length; k++) {
      if (k === 0 || series[k].mid !== series[k - 1].mid) changeIdx.push(k);
    }
    if (changeIdx.length < 2) continue;

    const midOk = changeIdx.every(
      (k) => series[k].mid === Math.floor((series[k].lo + series[k].hi) / 2),
    );
    if (!midOk) continue;

    const firstRange = series[changeIdx[0]].hi - series[changeIdx[0]].lo;
    const lastRange =
      series[changeIdx[changeIdx.length - 1]].hi - series[changeIdx[changeIdx.length - 1]].lo;
    if (lastRange >= firstRange) continue;

    out.push({
      kind: "binary_search",
      startEvent: run.start,
      endEvent: run.end,
      stackDepth: run.stackDepth,
      pointerLocals: [lo, hi, mid],
      arrayLocalName: findArrayLocal(events, run, seenNames),
    });
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
