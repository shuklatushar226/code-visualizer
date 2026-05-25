// Shared logic for every site adapter. Each platform-specific file imports
// `mountVisualizer(adapter)` and passes a small object that knows how to
// extract the source and stdin from that platform's DOM.

export function mountVisualizer(adapter) {
  if (!adapter.match()) return;

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

    // Wait for the iframe to mount, then post the payload.
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
