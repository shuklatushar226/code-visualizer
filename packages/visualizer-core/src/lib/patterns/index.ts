import type { Trace, TraceEvent } from "@dsa-viz/trace-schema";
import type { PatternHit, PatternKind } from "./types";
import { detectSlidingWindow } from "./slidingWindow";
import { detectTwoPointer } from "./twoPointer";
import { detectBinarySearch } from "./binarySearch";
import { detectDP } from "./dp";

export type { PatternHit, PatternKind } from "./types";

/**
 * Run every detector and return the union of hits. Specificity ordering:
 * binary_search > dp > two_pointer > sliding_window. The more specific
 * signature wins on shared runs.
 */
export function detectPatterns(trace: Trace | TraceEvent[]): PatternHit[] {
  const events = Array.isArray(trace) ? trace : trace.events;
  const bin = detectBinarySearch(events);
  const dp = detectDP(events);
  const tp = detectTwoPointer(events);
  const sw = detectSlidingWindow(events);

  const taken = new Set<string>(bin.map(runKey));
  const dpFiltered = dp.filter((h) => !taken.has(runKey(h)));
  dpFiltered.forEach((h) => taken.add(runKey(h)));
  const tpFiltered = tp.filter((h) => !taken.has(runKey(h)));
  tpFiltered.forEach((h) => taken.add(runKey(h)));
  const swFiltered = sw.filter((h) => !taken.has(runKey(h)));
  return [...bin, ...dpFiltered, ...tpFiltered, ...swFiltered];
}

function runKey(hit: PatternHit): string {
  return `${hit.startEvent}:${hit.endEvent}:${hit.stackDepth}`;
}

/**
 * The deepest active hit at event index t. Returns null if none applies.
 */
export function activePatternHit(hits: PatternHit[], t: number): PatternHit | null {
  let best: PatternHit | null = null;
  for (const h of hits) {
    if (t < h.startEvent || t > h.endEvent) continue;
    if (!best || h.stackDepth > best.stackDepth) best = h;
  }
  return best;
}
