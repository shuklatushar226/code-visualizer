// Panel bootstrap. Listens for postMessage from the content script, asks
// the background service worker to fetch the trace, then mounts the
// shared VisualizerPanel via the standalone bundle.
//
// The bundle (standalone.mjs + standalone.css) is copied into this
// directory at build time by ../../scripts/build.mjs.

const root = document.getElementById("root");
let handle = null;

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
    await mount(resp.trace);
  } catch (err) {
    setStatus(`Trace failed: ${err.message}`);
  }
});

async function mount(trace) {
  if (handle) {
    handle.update(trace);
    return;
  }
  const mod = await import("./standalone.mjs");
  root.innerHTML = "";
  handle = mod.mountVisualizer(root, trace);
}
