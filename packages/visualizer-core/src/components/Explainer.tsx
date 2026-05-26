import React, { useEffect, useRef, useState } from "react";
import type { Trace } from "@dsa-viz/trace-schema";

export interface ExplainerProps {
  trace: Trace;
  t: number;
  /** Base URL of the backend; reused from the surrounding host (web app, ext, etc). */
  backend: string;
  /** When true (default), debounce re-requests during fast scrubbing. */
  debounceMs?: number;
}

/**
 * Sends the current event + source to `POST /explain` and streams the
 * one-sentence explanation back via Server-Sent Events. Cancels in
 * flight requests when `t` changes; debounces by `debounceMs` so a
 * dragged slider doesn't fire one request per frame.
 *
 * The route returns 501 if `DSA_VIZ_AI_KEY` isn't configured backend-
 * side — we render a muted hint then. Errors during a streamed response
 * surface as a short message; we never silently swallow.
 */
export const Explainer: React.FC<ExplainerProps> = ({
  trace,
  t,
  backend,
  debounceMs = 500,
}) => {
  const [text, setText] = useState<string>("");
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error" | "disabled">("idle");
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    // Cancel any in-flight request when t changes.
    if (abortRef.current) {
      abortRef.current.abort();
      abortRef.current = null;
    }
    if (timerRef.current != null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }

    const event = trace.events[t];
    if (!event) return;

    setStatus("loading");
    setText("");

    timerRef.current = window.setTimeout(() => {
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      const topFrame = event.stack[event.stack.length - 1];

      void streamExplain({
        backend,
        signal: ctrl.signal,
        body: {
          event: {
            line: event.line,
            func: topFrame?.func ?? "",
            locals: topFrame?.locals ?? {},
          },
          source: trace.source,
          language: trace.language,
        },
        onToken: (delta) => setText((prev) => prev + delta),
        onDone: () => setStatus("ready"),
        onError: (msg, code) => {
          if (code === 501) {
            setStatus("disabled");
          } else {
            setStatus("error");
            setText(msg);
          }
        },
      });
    }, debounceMs) as unknown as number;

    return () => {
      if (timerRef.current != null) window.clearTimeout(timerRef.current);
      if (abortRef.current) abortRef.current.abort();
    };
  }, [trace, t, backend, debounceMs]);

  return (
    <div className="dsa-viz-explainer" data-status={status}>
      <div className="dsa-viz-explainer-label">✦ EXPLAIN</div>
      <div className="dsa-viz-explainer-body">
        {status === "disabled" && (
          <span className="dsa-viz-explainer-muted">
            AI explainer not configured. Set DSA_VIZ_AI_KEY on the backend.
          </span>
        )}
        {status === "loading" && !text && (
          <span className="dsa-viz-explainer-muted">…</span>
        )}
        {text && <span className="dsa-viz-explainer-text">{text}</span>}
      </div>
    </div>
  );
};


interface StreamArgs {
  backend: string;
  body: unknown;
  signal: AbortSignal;
  onToken: (delta: string) => void;
  onDone: (full: string) => void;
  onError: (msg: string, code?: number) => void;
}

async function streamExplain(args: StreamArgs): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${args.backend}/explain`, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
      body: JSON.stringify(args.body),
      signal: args.signal,
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") return;
    args.onError(String(e));
    return;
  }
  if (!response.ok) {
    args.onError(`backend returned ${response.status}`, response.status);
    return;
  }
  if (!response.body) {
    args.onError("no response body");
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let assembled = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      // Process each fully-terminated SSE event (blank line separator).
      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) >= 0) {
        const block = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);
        const { event, data } = parseSseBlock(block);
        if (event === "token") {
          const restored = data.replace(/\\n/g, "\n");
          assembled += restored;
          args.onToken(restored);
        } else if (event === "done") {
          args.onDone(assembled);
        } else if (event === "error") {
          args.onError(data);
        }
      }
    }
  } catch (e) {
    if ((e as Error).name !== "AbortError") args.onError(String(e));
  }
}

function parseSseBlock(block: string): { event: string; data: string } {
  let event = "message";
  const data: string[] = [];
  for (const line of block.split("\n")) {
    if (line.startsWith("event: ")) event = line.slice(7).trim();
    else if (line.startsWith("data: ")) data.push(line.slice(6));
  }
  return { event, data: data.join("\n") };
}
