import React, { useMemo, useState } from "react";
import type { Trace } from "@dsa-viz/trace-schema";
import { usePlayback } from "../hooks/usePlayback";
import { CodePane } from "./CodePane";
import { ControlBar } from "./ControlBar";
import { CallStack } from "./CallStack";
import { HeapView } from "./HeapView";
import { RecursionTreeView } from "./RecursionTreeView";

export interface VisualizerPanelProps {
  trace: Trace;
  /** Optional initial event index. */
  initialT?: number;
  /** Optional className for the outer container. */
  className?: string;
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
          />
        ) : (
          <RecursionTreeView trace={trace} t={playback.t} />
        )}
      </div>
      <div className="dsa-viz-row dsa-viz-controls">
        <ControlBar {...playback} stdout={trace.stdout ?? ""} />
      </div>
    </div>
  );
};
