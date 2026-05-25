import * as vscode from "vscode";

export function activate(context: vscode.ExtensionContext) {
  const disposable = vscode.commands.registerCommand("dsaViz.visualize", async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage("DSA Visualizer: no active editor.");
      return;
    }
    const cfg = vscode.workspace.getConfiguration("dsaViz");
    const backend = cfg.get<string>("backendUrl", "http://localhost:8000");
    const maxEvents = cfg.get<number>("maxEvents", 5000);

    const source = editor.document.getText();
    const lang = editor.document.languageId;
    const language = lang === "python" ? "python" : lang === "cpp" ? "cpp" : "python";

    const panel = vscode.window.createWebviewPanel(
      "dsaVizPanel",
      `DSA: ${editor.document.fileName.split(/[\\/]/).pop()}`,
      vscode.ViewColumn.Beside,
      { enableScripts: true, retainContextWhenHidden: true },
    );
    panel.webview.html = htmlShell();

    try {
      const trace = await postTrace(backend, { source, stdin: "", language, maxEvents });
      panel.webview.postMessage({ type: "DSA_VIZ_TRACE", trace });
    } catch (err) {
      vscode.window.showErrorMessage(`DSA Visualizer: ${String(err)}`);
    }
  });

  context.subscriptions.push(disposable);
}

export function deactivate() {
  // no-op
}

interface TraceRequest {
  source: string;
  stdin: string;
  language: "python" | "cpp";
  maxEvents: number;
}

async function postTrace(backend: string, req: TraceRequest): Promise<unknown> {
  const r = await fetch(`${backend}/trace`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!r.ok) throw new Error(`backend returned ${r.status}: ${await r.text()}`);
  return r.json();
}

function htmlShell(): string {
  return /* html */ `<!doctype html>
<html><head><meta charset="utf-8" /><title>DSA Visualizer</title>
<style>
  body { font: 13px ui-monospace, "JetBrains Mono", monospace; background: #1e1e1e; color: #d4d4d4; margin: 0; padding: 8px; }
  pre  { background: #111; padding: 8px; max-height: 70vh; overflow: auto; }
  button { background: #333; color: #fff; border: 1px solid #555; padding: 4px 10px; }
</style></head>
<body>
  <div id="header">Waiting for trace…</div>
  <div style="margin: 8px 0;">
    <button id="prev">◀</button>
    <button id="next">▶</button>
    <span id="counter"></span>
  </div>
  <pre id="event"></pre>
  <script>
    let events = [], i = 0;
    const header = document.getElementById("header");
    const counter = document.getElementById("counter");
    const eventBox = document.getElementById("event");
    function draw() {
      counter.textContent = "t = " + i + " / " + (events.length - 1);
      eventBox.textContent = JSON.stringify(events[i], null, 2);
    }
    document.getElementById("prev").onclick = () => { if (i > 0) { i--; draw(); } };
    document.getElementById("next").onclick = () => { if (i < events.length - 1) { i++; draw(); } };
    window.addEventListener("message", (e) => {
      if (e.data?.type !== "DSA_VIZ_TRACE") return;
      events = e.data.trace?.events ?? [];
      header.textContent = "events: " + events.length + ", language: " + e.data.trace.language;
      draw();
    });
  </script>
</body></html>`;
}
