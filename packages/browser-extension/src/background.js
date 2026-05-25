// Background service worker. Proxies trace requests so that the content
// script can hit the backend without running into mixed-origin issues.
//
// Future: cache the most recent trace per (tab, source-hash) so the panel
// reopens instantly when the user navigates within the same problem.

const DEFAULT_BACKEND = "http://localhost:8000";

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg?.type === "TRACE_REQUEST") {
    handleTrace(msg.payload, msg.backend ?? DEFAULT_BACKEND)
      .then((trace) => sendResponse({ ok: true, trace }))
      .catch((err) => sendResponse({ ok: false, error: String(err) }));
    return true; // keep channel open
  }
  return false;
});

async function handleTrace(payload, backend) {
  const r = await fetch(`${backend}/trace`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!r.ok) {
    const text = await r.text();
    throw new Error(`backend returned ${r.status}: ${text}`);
  }
  return r.json();
}
