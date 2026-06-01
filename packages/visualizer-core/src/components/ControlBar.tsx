import React from "react";
import type { PlaybackState } from "../hooks/usePlayback";

export interface ControlBarProps extends PlaybackState {
  stdout?: string;
}

// usePlayback's `speed` is milliseconds-per-step. The dropdown offers playback
// MULTIPLIERS, so convert: 1× == BASE_MS, 2× is twice as fast (half the ms),
// 0.5× is half as fast. BASE_MS matches usePlayback's default so the initial
// selection reads "1×".
const BASE_MS = 400;

export const ControlBar: React.FC<ControlBarProps> = ({
  t,
  total,
  playing,
  speed,
  prev,
  next,
  play,
  pause,
  reset,
  jumpTo,
  setSpeed,
  stdout,
}) => {
  return (
    <div className="dsa-viz-controlbar">
      <div className="dsa-viz-buttons">
        <button onClick={reset} title="Restart">⏮</button>
        <button onClick={prev} title="Step back" disabled={t === 0}>◀</button>
        <button onClick={playing ? pause : play} title={playing ? "Pause" : "Play"}>
          {playing ? "⏸" : "▶"}
        </button>
        <button onClick={next} title="Step forward" disabled={t >= total - 1}>▶</button>
      </div>
      <div className="dsa-viz-scrub">
        <input
          type="range"
          min={0}
          max={Math.max(0, total - 1)}
          value={t}
          onChange={(e) => jumpTo(Number(e.target.value))}
        />
        <span className="dsa-viz-tcounter">
          t = {t} / {Math.max(0, total - 1)}
        </span>
      </div>
      <div className="dsa-viz-speed">
        <label>
          speed
          <select
            value={String(BASE_MS / speed)}
            onChange={(e) => setSpeed(BASE_MS / Number(e.target.value))}
          >
            <option value="0.5">0.5×</option>
            <option value="1">1×</option>
            <option value="2">2×</option>
            <option value="4">4×</option>
          </select>
        </label>
      </div>
      {stdout && (
        <details className="dsa-viz-stdout">
          <summary>stdout ({stdout.length} chars)</summary>
          <pre>{stdout}</pre>
        </details>
      )}
    </div>
  );
};
