import React, { useEffect, useState } from "react";
import type { Trace } from "@dsa-viz/trace-schema";
import {
  VisualizerPanel,
  diffTraces,
  traceClient,
  type TraceDiff,
} from "@dsa-viz/visualizer-core";

const DEFAULT_PYTHON = `# DSA Visualizer demo: reverse a singly linked list.
class Node:
    def __init__(self, val, next=None):
        self.val = val
        self.next = next

def reverse(head):
    prev = None
    cur = head
    while cur is not None:
        nxt = cur.next
        cur.next = prev
        prev = cur
        cur = nxt
    return prev

# Build 1 -> 2 -> 3 -> 4 and reverse it.
head = Node(1, Node(2, Node(3, Node(4))))
result = reverse(head)
`;

const DEFAULT_CPP = `// DSA Visualizer demo (C++): in-place array reversal.
#include <vector>
#include <iostream>

void reverse_in_place(std::vector<int>& a) {
    int i = 0, j = (int)a.size() - 1;
    while (i < j) {
        std::swap(a[i], a[j]);
        ++i;
        --j;
    }
}

int main() {
    std::vector<int> a = {1, 2, 3, 4, 5};
    reverse_in_place(a);
    for (int x : a) std::cout << x << " ";
    return 0;
}
`;

// Two near-identical programs that diverge at one local value, used as the
// initial state of Compare mode so the divergence visibly highlights.
const DIFF_LEFT = `def solve(n):
    total = 0
    for i in range(n):
        total += i
    return total

solve(5)
`;
const DIFF_RIGHT = `def solve(n):
    total = 0
    for i in range(n):
        total += i + 1
    return total

solve(5)
`;

type Lang = "python" | "cpp";
type Mode = "single" | "compare";

export const App: React.FC = () => {
  const [mode, setMode] = useState<Mode>("single");
  const [language, setLanguage] = useState<Lang>("python");
  const [source, setSource] = useState<string>(DEFAULT_PYTHON);
  const [sourceB, setSourceB] = useState<string>(DIFF_RIGHT);
  const [stdin, setStdin] = useState<string>("");
  const [backend, setBackend] = useState<string>(
    () => localStorage.getItem("dsaViz.backend") ?? "http://localhost:8000",
  );
  const [trace, setTrace] = useState<Trace | null>(null);
  const [traceB, setTraceB] = useState<Trace | null>(null);
  const [diff, setDiff] = useState<TraceDiff | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [shareUrl, setShareUrl] = useState<string | null>(null);

  useEffect(() => {
    const code = new URLSearchParams(location.search).get("t");
    if (!code) return;
    void (async () => {
      try {
        const r = await fetch(`${backend}/t/${encodeURIComponent(code)}`);
        if (!r.ok) throw new Error(`backend returned ${r.status}`);
        const loaded = (await r.json()) as Trace;
        setTrace(loaded);
        setSource(loaded.source);
        setLanguage(loaded.language as Lang);
      } catch (e) {
        setErr(`Failed to load shared trace: ${String(e)}`);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function onLanguageChange(next: Lang) {
    setLanguage(next);
    if (next === "python" && source.trim() === DEFAULT_CPP.trim()) {
      setSource(DEFAULT_PYTHON);
    } else if (next === "cpp" && source.trim() === DEFAULT_PYTHON.trim()) {
      setSource(DEFAULT_CPP);
    }
  }

  function onBackendChange(next: string) {
    setBackend(next);
    try {
      localStorage.setItem("dsaViz.backend", next);
    } catch {
      /* private mode etc. */
    }
  }

  function onModeChange(next: Mode) {
    setMode(next);
    setErr(null);
    setShareUrl(null);
    if (next === "compare") {
      // Seed Compare with two near-identical programs so the divergence is
      // visible immediately.
      setSource(DIFF_LEFT);
      setSourceB(DIFF_RIGHT);
      setTrace(null);
      setTraceB(null);
      setDiff(null);
    }
  }

  async function run() {
    setBusy(true);
    setErr(null);
    setTrace(null);
    setShareUrl(null);
    try {
      const client = traceClient(backend);
      const t = await client.trace({ source, stdin, language });
      setTrace(t);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function compare() {
    setBusy(true);
    setErr(null);
    setTrace(null);
    setTraceB(null);
    setDiff(null);
    try {
      const client = traceClient(backend);
      const [a, b] = await Promise.all([
        client.trace({ source, stdin, language }),
        client.trace({ source: sourceB, stdin, language }),
      ]);
      setTrace(a);
      setTraceB(b);
      setDiff(diffTraces(a, b));
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  async function share() {
    if (!trace) return;
    try {
      const r = await fetch(`${backend}/share`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ trace }),
      });
      if (!r.ok) throw new Error(`backend returned ${r.status}`);
      const body = (await r.json()) as { code: string; url: string };
      const fullUrl = `${location.origin}${location.pathname}?t=${body.code}`;
      setShareUrl(fullUrl);
      try {
        await navigator.clipboard?.writeText(fullUrl);
      } catch {
        /* clipboard denied in some contexts */
      }
    } catch (e) {
      setErr(`Share failed: ${String(e)}`);
    }
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <h1>DSA Visualizer · standalone</h1>
        <span className="meta" style={{ display: "flex", gap: 12, alignItems: "center" }}>
          <label>
            mode{" "}
            <select value={mode} onChange={(e) => onModeChange(e.target.value as Mode)}>
              <option value="single">Single</option>
              <option value="compare">Compare</option>
            </select>
          </label>
          backend:{" "}
          <input
            type="text"
            value={backend}
            onChange={(e) => onBackendChange(e.target.value)}
            style={{ width: 220 }}
          />
        </span>
      </header>

      {mode === "single" ? (
        <div className="app-body">
          <section className="editor-pane">
            <div className="editor-toolbar">
              <label>
                language{" "}
                <select
                  value={language}
                  onChange={(e) => onLanguageChange(e.target.value as Lang)}
                >
                  <option value="python">Python</option>
                  <option value="cpp">C++</option>
                </select>
              </label>
              <label style={{ flex: 1 }}>
                stdin{" "}
                <input
                  type="text"
                  value={stdin}
                  onChange={(e) => setStdin(e.target.value)}
                  placeholder="(optional)"
                  style={{ width: "100%" }}
                />
              </label>
              <button onClick={run} disabled={busy}>
                {busy ? "Tracing…" : "Run & Visualize"}
              </button>
              <button
                onClick={share}
                disabled={!trace}
                title="Save and copy a shareable link (ephemeral: lost on backend restart)"
              >
                Share
              </button>
              {shareUrl && (
                <a className="share-link" href={shareUrl} title="Link copied">
                  copied ✓
                </a>
              )}
            </div>
            <textarea
              className="editor-textarea"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              spellCheck={false}
            />
          </section>

          <section className="viz-pane">
            {err && <div className="viz-error">Error: {err}</div>}
            {!err && !trace && (
              <div className="viz-empty">
                Edit the program on the left and press <strong>Run &amp; Visualize</strong>.
                Make sure the FastAPI backend is reachable at <code>{backend}</code>.
              </div>
            )}
            {trace && <VisualizerPanel trace={trace} />}
          </section>
        </div>
      ) : (
        <div className="app-body compare-body">
          <section className="editor-pane">
            <div className="editor-toolbar">
              <label>
                language{" "}
                <select
                  value={language}
                  onChange={(e) => onLanguageChange(e.target.value as Lang)}
                >
                  <option value="python">Python</option>
                  <option value="cpp">C++</option>
                </select>
              </label>
              <button onClick={compare} disabled={busy}>
                {busy ? "Tracing both…" : "Compare"}
              </button>
            </div>
            <div className="compare-editors">
              <textarea
                className="editor-textarea"
                value={source}
                onChange={(e) => setSource(e.target.value)}
                spellCheck={false}
                aria-label="program A"
              />
              <textarea
                className="editor-textarea"
                value={sourceB}
                onChange={(e) => setSourceB(e.target.value)}
                spellCheck={false}
                aria-label="program B"
              />
            </div>
            {diff && (
              <div className="diff-summary" data-diverged={String(diff.diverged)}>
                {diff.diverged ? (
                  <>
                    <strong>Diverged at event {diff.divergence!.aIndex}</strong> —{" "}
                    {diff.divergence!.reason}. Common prefix:{" "}
                    {diff.commonPrefix} event(s).
                  </>
                ) : (
                  <strong>Traces are identical ({diff.commonPrefix} events).</strong>
                )}
              </div>
            )}
          </section>

          <section className="viz-pane viz-pane-split">
            {err && <div className="viz-error">Error: {err}</div>}
            {!err && (!trace || !traceB) && (
              <div className="viz-empty">
                Edit the two programs and press <strong>Compare</strong>.
              </div>
            )}
            {trace && traceB && (
              <div className="compare-panels">
                <div className="compare-panel">
                  <h3 className="compare-panel-title">Program A</h3>
                  <VisualizerPanel
                    trace={trace}
                    initialT={diff?.divergence?.aIndex ?? 0}
                  />
                </div>
                <div className="compare-panel">
                  <h3 className="compare-panel-title">Program B</h3>
                  <VisualizerPanel
                    trace={traceB}
                    initialT={diff?.divergence?.bIndex ?? 0}
                  />
                </div>
              </div>
            )}
          </section>
        </div>
      )}
    </div>
  );
};
