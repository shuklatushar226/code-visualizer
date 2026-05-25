import * as vscode from "vscode";
import * as crypto from "node:crypto";

export function activate(context: vscode.ExtensionContext) {
  const disposable = vscode.commands.registerCommand("dsaViz.visualize", async () => {
    const editor = vscode.window.activeTextEditor;
    if (!editor) {
      vscode.window.showWarningMessage("DSA Visualizer: no active editor.");
      return;
    }
    const cfg = vscode.workspace.getConfiguration("dsaViz");
    const backend = cfg.get<string>("backendUrl", "http://localhost:8000");

    const source = editor.document.getText();
    const lang = editor.document.languageId;
    const language: "python" | "cpp" =
      lang === "python" ? "python" : lang === "cpp" ? "cpp" : "python";

    const panel = vscode.window.createWebviewPanel(
      "dsaVizPanel",
      `DSA: ${editor.document.fileName.split(/[\\/]/).pop()}`,
      vscode.ViewColumn.Beside,
      {
        enableScripts: true,
        retainContextWhenHidden: true,
        localResourceRoots: [vscode.Uri.joinPath(context.extensionUri, "media")],
      },
    );

    const nonce = crypto.randomBytes(16).toString("base64");
    const scriptUri = panel.webview.asWebviewUri(
      vscode.Uri.joinPath(context.extensionUri, "media", "standalone.mjs"),
    );
    const cssUri = panel.webview.asWebviewUri(
      vscode.Uri.joinPath(context.extensionUri, "media", "standalone.css"),
    );
    panel.webview.html = htmlShell(panel.webview.cspSource, nonce, scriptUri, cssUri);

    try {
      const trace = await postTrace(backend, { source, stdin: "", language });
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

function htmlShell(
  cspSource: string,
  nonce: string,
  scriptUri: vscode.Uri,
  cssUri: vscode.Uri,
): string {
  return /* html */ `<!doctype html>
<html><head>
<meta charset="utf-8" />
<meta http-equiv="Content-Security-Policy"
  content="default-src 'none'; style-src ${cspSource} 'unsafe-inline'; script-src 'nonce-${nonce}'; img-src ${cspSource} data:;" />
<title>DSA Visualizer</title>
<link rel="stylesheet" href="${cssUri}" />
<style>
  html, body, #root { margin: 0; height: 100vh; background: #1e1e1e; color: #d4d4d4; }
</style>
</head>
<body>
  <div id="root">
    <div style="padding:12px;font:13px ui-monospace, 'JetBrains Mono', monospace;">
      Waiting for trace…
    </div>
  </div>
  <script type="module" nonce="${nonce}">
    const root = document.getElementById("root");
    let handle = null;
    window.addEventListener("message", async (e) => {
      if (e.data?.type !== "DSA_VIZ_TRACE") return;
      const trace = e.data.trace;
      if (handle) {
        handle.update(trace);
      } else {
        const mod = await import("${scriptUri}");
        root.innerHTML = "";
        handle = mod.mountVisualizer(root, trace);
      }
    });
  </script>
</body></html>`;
}
