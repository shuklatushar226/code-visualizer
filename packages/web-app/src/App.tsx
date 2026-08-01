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

const DEFAULT_JAVASCRIPT = `// DSA Visualizer demo (JavaScript): naive recursive Fibonacci.
function fib(n) {
    if (n < 2) return n;
    return fib(n - 1) + fib(n - 2);
}

console.log(fib(5));
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

const DEFAULT_JAVA = `// DSA Visualizer demo (Java): reverse a singly linked list.
public class Main {
    static class ListNode {
        int val;
        ListNode next;
        ListNode(int val) { this.val = val; }
    }

    static ListNode reverse(ListNode head) {
        ListNode prev = null;
        ListNode cur = head;
        while (cur != null) {
            ListNode nxt = cur.next;
            cur.next = prev;
            prev = cur;
            cur = nxt;
        }
        return prev;
    }

    public static void main(String[] args) {
        // Build 1 -> 2 -> 3 -> 4 and reverse it.
        ListNode head = new ListNode(1);
        head.next = new ListNode(2);
        head.next.next = new ListNode(3);
        head.next.next.next = new ListNode(4);
        ListNode result = reverse(head);
    }
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

type Lang = "python" | "cpp" | "javascript" | "java";
type Mode = "single" | "compare";

const LANGUAGE_META: Record<Lang, { label: string; file: string; tone: string }> = {
  python: { label: "Python", file: "main.py", tone: "PY" },
  cpp: { label: "C++", file: "main.cpp", tone: "C++" },
  javascript: { label: "JavaScript", file: "main.js", tone: "JS" },
  java: { label: "Java", file: "Main.java", tone: "JV" },
};

export const App: React.FC = () => {
  const [mode, setMode] = useState<Mode>("single");
  const [language, setLanguage] = useState<Lang>("python");
  const [source, setSource] = useState<string>(DEFAULT_PYTHON);
  const [sourceB, setSourceB] = useState<string>(DIFF_RIGHT);
  const [stdin, setStdin] = useState<string>("");
  const [backend, setBackend] = useState<string>(
    () =>
      // 1. explicit user override (Settings field) wins;
      // 2. then a build-time VITE_API_URL (split-deploy: point at a remote backend);
      // 3. in dev, fall back to the local backend;
      // 4. in a production build with no override, use same-origin ("" → "/trace"),
      //    which is exactly the combined-service deploy where FastAPI serves this SPA.
      localStorage.getItem("dsaViz.backend") ??
      (import.meta.env.VITE_API_URL as string | undefined) ??
      (import.meta.env.DEV ? "http://localhost:8000" : ""),
  );
  const [trace, setTrace] = useState<Trace | null>(null);
  const [traceB, setTraceB] = useState<Trace | null>(null);
  const [diff, setDiff] = useState<TraceDiff | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [explain, setExplain] = useState<boolean>(
    () => localStorage.getItem("dsaViz.explain") === "1",
  );

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
    // Swap in the new language's default ONLY if the editor still
    // contains one of the OTHER languages' defaults — preserves any
    // edits the user made.
    const isAnyDefault =
      source.trim() === DEFAULT_PYTHON.trim() ||
      source.trim() === DEFAULT_CPP.trim() ||
      source.trim() === DEFAULT_JAVASCRIPT.trim() ||
      source.trim() === DEFAULT_JAVA.trim();
    if (!isAnyDefault) return;
    if (next === "python") setSource(DEFAULT_PYTHON);
    else if (next === "cpp") setSource(DEFAULT_CPP);
    else if (next === "javascript") setSource(DEFAULT_JAVASCRIPT);
    else if (next === "java") setSource(DEFAULT_JAVA);
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
      // visible immediately. They are Python, so reset the language too —
      // otherwise a JS/C++ selection from Single mode would trace this Python
      // source through the wrong pipeline and the comparison would be empty.
      setLanguage("python");
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
        <div className="masthead-top">
          <div className="brand-lockup">
            <div className="brand-mark" aria-hidden="true">
              <span className="brand-core">D</span>
              <span className="brand-orbit orbit-one" />
              <span className="brand-orbit orbit-two" />
            </div>
            <div>
              <h1>
                <span className="mono">DSV</span>
                <span className="brand-name">Code Visualizer</span>
              </h1>
              <p className="brand-subtitle">Runtime intelligence for curious minds</p>
            </div>
          </div>

          <div className="header-actions">
            <span className="engine-status"><i /> Engine live</span>
            <label className="mode-control">
              <span className="control-label">Workspace</span>
              <select value={mode} onChange={(e) => onModeChange(e.target.value as Mode)}>
                <option value="single">Visualize</option>
                <option value="compare">Compare</option>
              </select>
            </label>
            <label className="explain-toggle">
              <input
                type="checkbox"
                checked={explain}
                onChange={(e) => {
                  setExplain(e.target.checked);
                  try {
                    localStorage.setItem("dsaViz.explain", e.target.checked ? "1" : "0");
                  } catch {
                    /* private mode */
                  }
                }}
              />
              <span className="toggle-track" aria-hidden="true"><i /></span>
              AI explain
            </label>
            <details className="settings-menu">
              <summary aria-label="Backend settings">•••</summary>
              <div className="settings-popover">
                <label>
                  Backend endpoint
                  <input
                    type="text"
                    value={backend}
                    onChange={(e) => onBackendChange(e.target.value)}
                    placeholder="Same-origin"
                  />
                </label>
                <small>Leave blank to use the deployed runtime.</small>
              </div>
            </details>
          </div>
        </div>
        <div className="hero-line">
          <p className="tagline">
            <span className="eyebrow">SEE THE INVISIBLE</span>
            <strong>Turn every line of code into a living system.</strong>
            Trace variables, call stacks and data structures as they evolve.
          </p>
          <div className="capability-list" aria-label="Supported visualizations">
            <span><i className="spark violet" /> Line-by-line</span>
            <span><i className="spark cyan" /> Live memory</span>
            <span><i className="spark green" /> Pattern-aware</span>
          </div>
        </div>
      </header>

      {mode === "single" ? (
        <div className="app-body">
          <section className="editor-pane">
            <div className="pane-heading">
              <div>
                <span className="pane-index">01</span>
                <strong>Write your algorithm</strong>
              </div>
              <span className="file-pill"><i /> {LANGUAGE_META[language].file}</span>
            </div>
            <div className="editor-toolbar">
              <label className="language-control">
                <span className="language-glyph">{LANGUAGE_META[language].tone}</span>
                <select
                  value={language}
                  onChange={(e) => onLanguageChange(e.target.value as Lang)}
                >
                  <option value="python">Python</option>
                  <option value="cpp">C++</option>
                  <option value="javascript">JavaScript</option>
                  <option value="java">Java</option>
                </select>
              </label>
              <label className="stdin">
                <span>Input</span>
                <input
                  type="text"
                  value={stdin}
                  onChange={(e) => setStdin(e.target.value)}
                  placeholder="Optional stdin…"
                />
              </label>
              <button className="run-button" onClick={run} disabled={busy}>
                <span className="run-icon">{busy ? "◌" : "▶"}</span>
                {busy ? "Tracing…" : "Run & Visualize"}
              </button>
              <button
                className="share-button"
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
              onKeyDown={(e) => {
                if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
                  e.preventDefault();
                  void run();
                }
              }}
              spellCheck={false}
              aria-label="Source code editor"
            />
            <div className="editor-statusbar">
              <span>{source.split("\n").length} lines</span>
              <span>UTF-8</span>
              <span className="shortcut"><kbd>⌘</kbd><kbd>↵</kbd> to run</span>
            </div>
          </section>

          <section className="viz-pane">
            <div className="pane-heading result-heading">
              <div>
                <span className="pane-index">02</span>
                <strong>Watch it execute</strong>
              </div>
              <span className={trace ? "trace-state is-ready" : "trace-state"}>
                <i /> {trace ? `${trace.events.length} events captured` : "Awaiting trace"}
              </span>
            </div>
            {err && <div className="viz-error">Error: {err}</div>}
            {!err && !trace && (
              <div className="viz-empty">
                <div className="empty-plate">
                  <div className="execution-orbit" aria-hidden="true">
                    <span className="orbit-ring ring-one" />
                    <span className="orbit-ring ring-two" />
                    <span className="orbit-node node-a" />
                    <span className="orbit-node node-b" />
                    <span className="orbit-node node-c" />
                    <span className="orbit-center">▶</span>
                  </div>
                  <span className="empty-kicker">Your algorithm, illuminated</span>
                  <h2>Ready to see your code <span className="accent">think?</span></h2>
                  <p>
                    Run the sample or paste your own algorithm. We’ll transform its
                    execution into an interactive timeline you can explore step by step.
                  </p>
                  <div className="empty-steps" aria-hidden="true">
                    <span><b>1</b> Run</span><i />
                    <span><b>2</b> Scrub</span><i />
                    <span><b>3</b> Understand</span>
                  </div>
                </div>
              </div>
            )}
            {trace && (
              <VisualizerPanel
                trace={trace}
                showExplainer={explain}
                explainerBackend={backend}
              />
            )}
          </section>
        </div>
      ) : (
        <div className="app-body compare-body">
          <section className="editor-pane">
            <div className="pane-heading">
              <div><span className="pane-index">A/B</span><strong>Compare implementations</strong></div>
              <span className="file-pill"><i /> divergence lab</span>
            </div>
            <div className="editor-toolbar">
              <label>
                language{" "}
                <select
                  value={language}
                  onChange={(e) => onLanguageChange(e.target.value as Lang)}
                >
                  <option value="python">Python</option>
                  <option value="cpp">C++</option>
                  <option value="javascript">JavaScript</option>
                  <option value="java">Java</option>
                </select>
              </label>
              <button className="run-button" onClick={compare} disabled={busy}>
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
            <div className="pane-heading result-heading">
              <div><span className="pane-index">Δ</span><strong>Trace difference</strong></div>
              <span className="trace-state"><i /> synchronized</span>
            </div>
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
