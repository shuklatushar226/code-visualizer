/**
 * usePlayback — drives the playback cursor (t) over a list of trace events.
 *
 * Exposes:
 *  - t              : current event index
 *  - playing        : true when auto-advancing
 *  - speed          : ms per step
 *  - prev / next    : step backward / forward
 *  - play / pause   : toggle auto-advance
 *  - reset          : jump to t = 0
 *  - jumpTo(t)      : seek to a specific event
 */

import { useCallback, useEffect, useRef, useState } from "react";

export interface PlaybackState {
  t: number;
  playing: boolean;
  speed: number;
  total: number;
  prev: () => void;
  next: () => void;
  play: () => void;
  pause: () => void;
  reset: () => void;
  jumpTo: (t: number) => void;
  setSpeed: (ms: number) => void;
}

export function usePlayback(total: number, initialSpeed = 400): PlaybackState {
  const [t, setT] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(initialSpeed);
  const timer = useRef<number | null>(null);

  const next = useCallback(
    () => setT((cur) => Math.min(total - 1, cur + 1)),
    [total]
  );
  const prev = useCallback(() => setT((cur) => Math.max(0, cur - 1)), []);
  const play = useCallback(() => setPlaying(true), []);
  const pause = useCallback(() => setPlaying(false), []);
  const reset = useCallback(() => setT(0), []);
  const jumpTo = useCallback(
    (target: number) => setT(Math.max(0, Math.min(total - 1, target))),
    [total]
  );

  useEffect(() => {
    if (!playing) return;
    timer.current = window.setInterval(() => {
      setT((cur) => {
        if (cur >= total - 1) {
          setPlaying(false);
          return cur;
        }
        return cur + 1;
      });
    }, speed);
    return () => {
      if (timer.current != null) window.clearInterval(timer.current);
    };
  }, [playing, speed, total]);

  return { t, playing, speed, total, prev, next, play, pause, reset, jumpTo, setSpeed };
}
