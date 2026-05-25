import type { HeapObject, TraceEvent, Value } from "@dsa-viz/trace-schema";
import { topFrame, type PatternHit } from "./types";
import { frameRuns } from "./utils";

/**
 * DP detector — looks for an array (list) local that fills in monotone
 * order over the run. Specifically: each cell transitions from its
 * initial value to a final value at most once, the transitions happen
 * in strictly increasing index order, and at least 3 cells get filled.
 *
 * This catches the common "tabulation" shape (coin change, climbing
 * stairs, edit distance row, LIS) without firing on incidental loops
 * that overwrite the same cell repeatedly.
 */
export function detectDP(events: TraceEvent[]): PatternHit[] {
  const out: PatternHit[] = [];

  for (const run of frameRuns(events)) {
    if (run.end - run.start < 4) continue;
    const startFrame = topFrame(events[run.start]);
    if (!startFrame) continue;

    // Find names of local references that point at a list at any point.
    const arrayNames = new Set<string>();
    for (let k = run.start; k <= run.end; k++) {
      const f = topFrame(events[k]);
      if (!f || events[k].stack.length !== run.stackDepth) continue;
      for (const [name, value] of Object.entries(f.locals)) {
        if (value.kind !== "ref") continue;
        const obj = events[k].heap[value.id];
        if (obj && obj.kind === "list") arrayNames.add(name);
      }
    }
    if (arrayNames.size === 0) continue;

    for (const name of arrayNames) {
      const trail = collectTrail(events, run, name);
      if (!trail) continue;
      const fillOrder = monotoneFillOrder(trail);
      if (fillOrder == null) continue;

      out.push({
        kind: "dp",
        startEvent: run.start,
        endEvent: run.end,
        stackDepth: run.stackDepth,
        pointerLocals: [],
        arrayLocalName: name,
      });
      break;
    }
  }
  return out;
}

interface Snapshot {
  eventIdx: number;
  items: Value[];
}

function collectTrail(
  events: TraceEvent[],
  run: { start: number; end: number; stackDepth: number },
  name: string,
): Snapshot[] | null {
  const snaps: Snapshot[] = [];
  for (let k = run.start; k <= run.end; k++) {
    const f = topFrame(events[k]);
    if (!f || events[k].stack.length !== run.stackDepth) continue;
    const value = f.locals[name];
    if (!value || value.kind !== "ref") continue;
    const obj: HeapObject | undefined = events[k].heap[value.id];
    if (!obj || obj.kind !== "list") continue;
    if (snaps.length > 0) {
      // Skip duplicates so an unchanged array doesn't pollute the trail.
      const prev = snaps[snaps.length - 1];
      if (sameItems(prev.items, obj.items)) continue;
    }
    snaps.push({ eventIdx: k, items: obj.items });
  }
  return snaps.length >= 2 ? snaps : null;
}

function monotoneFillOrder(trail: Snapshot[]): number | null {
  // Initial state: the first snapshot. Each subsequent snapshot must
  // change strictly one OR-more cells whose indices are >= every cell
  // we've already finalized, and never revisit a finalized cell.
  const baseline = trail[0].items;
  const finalized = new Set<number>();
  let maxIdxSeen = -1;
  let fills = 0;

  for (let s = 1; s < trail.length; s++) {
    const cur = trail[s].items;
    if (cur.length !== baseline.length) return null;
    let changedHere = -1;
    for (let i = 0; i < cur.length; i++) {
      if (!sameValue(baseline[i], cur[i])) {
        if (finalized.has(i)) {
          // The array changed back / changed an already-final cell —
          // not a clean tabulation.
          if (!sameValue(cur[i], lastValue(trail, s - 1, i))) return null;
          continue;
        }
        if (changedHere === -1) {
          changedHere = i;
        }
        // Multiple cells filled in one step is OK (e.g. dp[i] +
        // dp[i-1] update), but they all need to be in monotone order.
      }
    }
    if (changedHere === -1) continue;
    if (changedHere < maxIdxSeen) return null;
    maxIdxSeen = Math.max(maxIdxSeen, changedHere);
    finalized.add(changedHere);
    fills++;
  }
  return fills >= 3 ? fills : null;
}

function lastValue(trail: Snapshot[], s: number, i: number): Value {
  return trail[s].items[i];
}

function sameItems(a: Value[], b: Value[]): boolean {
  if (a.length !== b.length) return false;
  for (let i = 0; i < a.length; i++) if (!sameValue(a[i], b[i])) return false;
  return true;
}

function sameValue(a: Value, b: Value): boolean {
  if (a.kind !== b.kind) return false;
  switch (a.kind) {
    case "int":
    case "float":
    case "str":
    case "bool":
      return (a as { v: unknown }).v === (b as { v: unknown }).v;
    case "none":
      return true;
    case "ref":
      return a.id === (b as { id: string }).id;
  }
}
