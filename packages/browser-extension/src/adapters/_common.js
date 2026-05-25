// Shared mountVisualizer logic for every site adapter. Exposed on `window`
// because Manifest V3 content scripts don't run as ES modules by default —
// the manifest lists this file first in `js: [...]` so it loads before the
// per-platform adapter that consumes it.

(function () {
  function mountVisualizer(adapter) {
    if (!adapter.match()) return;
    // Dedup: if another adapter already mounted a FAB (e.g. /problems/*
    // matches both the LeetCode and GfG patterns), skip silently. The
    // first adapter to fire wins.
    if (document.querySelector(".dsa-viz-fab")) return;

    const btn = document.createElement("button");
    btn.className = "dsa-viz-fab";
    btn.textContent = "Visualize";

    const host = document.createElement("div");
    host.className = "dsa-viz-frame-host";

    const iframe = document.createElement("iframe");
    iframe.src = chrome.runtime.getURL("src/panel/index.html");
    host.appendChild(iframe);

    document.body.appendChild(btn);
    document.body.appendChild(host);

    btn.addEventListener("click", async () => {
      host.classList.toggle("is-open");
      if (!host.classList.contains("is-open")) return;

      const source = adapter.readSource();
      const stdin = adapter.readStdin?.() ?? "";
      const language = adapter.detectLanguage();

      await new Promise((res) => {
        if (iframe.contentWindow) return res();
        iframe.addEventListener("load", res, { once: true });
      });

      iframe.contentWindow?.postMessage(
        { type: "DSA_VIZ_RUN", source, stdin, language },
        "*",
      );
    });
  }

  // Surface to per-platform adapters.
  window.__dsaMountVisualizer = mountVisualizer;
})();
