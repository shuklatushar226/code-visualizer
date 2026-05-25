// Panel bootstrap. Listens for postMessage from the content script, runs the
// trace via the background service worker, then mounts <VisualizerPanel/>.
//
// This file is intentionally written as a single ES module that will be
// replaced at build time by a bundled version of @dsa-viz/visualizer-core +
// the web-app's panel mount. The stub here exists so the extension can be
// loaded unpacked without a build step for early development.

const root = document.getElementById("root");

function setStatus(msg) {
  root.innerHTML = `<div style="padding:12px;font:13px system-ui;">${msg}</div>`;
}

window.addEventListener("message", async (e) => {
  if (e.data?.type !== "DSA_VIZ_RUN") return;
  const { source, stdin, language } = e.data;
  if (!source) {
    setStatus("No source code detected on the page.");
    return;
  }
  setStatus("Tracing…");

  const { backend } = await chrome.storage.local.get(["backend"]);
  const url = backend || "http://localhost:8000";

  try {
    const resp = await chrome.runtime.sendMessage({
      type: "TRACE_REQUEST",
      backend: url,
      payload: { source, stdin, language },
    });
    if (!resp?.ok) throw new Error(resp?.error ?? "unknown error");
    renderTrace(resp.trace);
  } catch (err) {
    setStatus(`Trace failed: ${err.message}`);
  }
});

function renderTrace(trace) {
  // Minimal interim renderer until the bundled visualizer-core ships. Shows
  // events as a scrollable list — enough to confirm end-to-end plumbing.
  const events = trace.events ?? [];
  let i = 0;
  root.innerHTML = `
    <div style="padding:8px;font:13px ui-monospace,monospace;">
      <div>events: ${events.length}, language: ${trace.language}</div>
      <div style="margin:8px 0;">
        <button id="prev">◀</button>
        <button id="next">▶</button>
        <span id="t"></span>
      </div>
      <pre id="frame" style="background:#161616;padding:8px;max-height:60vh;overflow:auto;"></pre>
    </div>`;
  const draw = () => {
    document.getElementById("t").textContent = `t = ${i} / ${events.length - 1}`;
    document.getElementById("frame").textContent = JSON.stringify(events[i], null, 2);
  };
  document.getElementById("prev").onclick = () => { if (i > 0) { i--; draw(); } };
  document.getElementById("next").onclick = () => { if (i < events.length - 1) { i++; draw(); } };
  draw();
}
