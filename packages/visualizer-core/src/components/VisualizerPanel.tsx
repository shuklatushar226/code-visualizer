import React, { useMemo, useState } from "react";
import type { Frame, Trace } from "@dsa-viz/trace-schema";
import { usePlayback } from "../hooks/usePlayback";
import {
  activePatternHit,
  detectPatterns,
  type PatternHit,
} from "../lib/patterns";
import { CodePane } from "./CodePane";
import { ControlBar } from "./ControlBar";
import { CallStack } from "./CallStack";
import { Explainer } from "./Explainer";
import { HeapView, type PatternOverlayState } from "./HeapView";
import { RecursionTreeView } from "./RecursionTreeView";

export interface VisualizerPanelProps {
  trace: Trace;
  /** Optional initial event index. */
  initialT?: number;
  /** Optional className for the outer container. */
  className?: string;
  /** When true, mount the AI Explainer panel below the controls. */
  showExplainer?: boolean;
  /** Backend URL the Explainer streams from. Required when showExplainer is true. */
  explainerBackend?: string;
}

/**
 * Top-level orchestrator. Owns the playback head and lays out the four
 * primary regions:
 *
 *   ┌──────────────────────────────────────────────────────────┐
 *   │ CodePane                       │ CallStack               │
 *   │ (current line highlight)       │ (frames + locals)       │
 *   ├────────────────────────────────┴─────────────────────────┤
 *   │ HeapView                                                 │
 *   │ (arrays / linked lists / trees / etc., chosen per-value) │
 *   ├──────────────────────────────────────────────────────────┤
 *   │ ControlBar  ⏮  ⏯  ⏭   speed   t = 17 / 134               │
 *   └──────────────────────────────────────────────────────────┘
 */
const RECURSION_TAB_THRESHOLD = 5;

export const VisualizerPanel: React.FC<VisualizerPanelProps> = ({
  trace,
  initialT = 0,
  className,
  showExplainer = false,
  explainerBackend,
}) => {
  const playback = usePlayback(trace.events.length, initialT);
  const event = trace.events[playback.t];

  const callCount = useMemo(
    () => trace.events.reduce((acc, e) => acc + (e.kind === "call" ? 1 : 0), 0),
    [trace.events],
  );
  const [view, setView] = useState<"heap" | "recursion">(
    callCount > RECURSION_TAB_THRESHOLD ? "recursion" : "heap",
  );

  const patternHits = useMemo(() => detectPatterns(trace), [trace]);
  const overlay = useMemo(
    () => computeOverlay(activePatternHit(patternHits, playback.t), event?.stack[event.stack.length - 1]),
    [patternHits, playback.t, event],
  );

  return (
    <div className={["dsa-viz-panel", className].filter(Boolean).join(" ")}>
      <div className="dsa-viz-row dsa-viz-top">
        <div className="dsa-viz-codecol">
          <CodePane
            source={trace.source}
            language={trace.language}
            currentLine={event?.line}
          />
        </div>
        <div className="dsa-viz-stackcol">
          <CallStack frames={event?.stack ?? []} />
        </div>
      </div>
      <div className="dsa-viz-tabs" role="tablist">
        <button
          role="tab"
          aria-selected={view === "heap"}
          className={view === "heap" ? "is-active" : ""}
          onClick={() => setView("heap")}
        >
          Heap
        </button>
        <button
          role="tab"
          aria-selected={view === "recursion"}
          className={view === "recursion" ? "is-active" : ""}
          onClick={() => setView("recursion")}
        >
          Recursion {callCount > 0 ? `(${callCount})` : ""}
        </button>
      </div>
      <div className="dsa-viz-row dsa-viz-heap">
        {view === "heap" ? (
          <HeapView
            heap={event?.heap ?? {}}
            frame={event?.stack[event.stack.length - 1]}
            annotations={trace.annotations ?? {}}
            patternOverlay={overlay}
          />
        ) : (
          <RecursionTreeView trace={trace} t={playback.t} />
        )}
      </div>
      <div className="dsa-viz-row dsa-viz-controls">
        <ControlBar {...playback} stdout={trace.stdout ?? ""} />
      </div>
      {showExplainer && explainerBackend && (
        <div className="dsa-viz-row dsa-viz-explainer-row">
          <Explainer trace={trace} t={playback.t} backend={explainerBackend} />
        </div>
      )}
    </div>
  );
};

function computeOverlay(hit: PatternHit | null, frame: Frame | undefined): PatternOverlayState | null {
  if (!hit || !frame || !hit.arrayLocalName) return null;
  if (hit.kind === "binary_search") {
    const lo = frame.locals[hit.pointerLocals[0]];
    const hi = frame.locals[hit.pointerLocals[1]];
    const mid = frame.locals[hit.pointerLocals[2]];
    if (lo?.kind !== "int" || hi?.kind !== "int" || mid?.kind !== "int") return null;
    return {
      kind: hit.kind,
      arrayLocalName: hit.arrayLocalName,
      lo: lo.v,
      hi: hi.v,
      midIndex: mid.v,
    };
  }
  if (hit.kind === "dp") {
    // DP overlay highlights every filled cell of the array. Without
    // per-cell book-keeping we fall back to spanning the whole array; the
    // ArrayView clamps to its own length.
    return {
      kind: hit.kind,
      arrayLocalName: hit.arrayLocalName,
      lo: 0,
      hi: Number.MAX_SAFE_INTEGER,
    };
  }
  const a = frame.locals[hit.pointerLocals[0]];
  const b = frame.locals[hit.pointerLocals[1]];
  if (a?.kind !== "int" || b?.kind !== "int") return null;
  return {
    kind: hit.kind,
    arrayLocalName: hit.arrayLocalName,
    lo: Math.min(a.v, b.v),
    hi: Math.max(a.v, b.v),
  };
}
