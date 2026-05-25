# DSA Visualizer — Browser Extension

Manifest V3 extension that adds a "Visualize" panel to the major coding
platforms. The same UI (loaded from `visualizer-core`) runs everywhere; only
the **adapter** — the bit of glue that knows where the editor and test input
live in the page — differs per site.

## How it works

```
┌─ host page (e.g. leetcode.com/problems/two-sum) ────────────────────────┐
│                                                                         │
│  Monaco editor    ┌─ content script ──────────────────────────────────┐ │
│   (user code) ─►  │ adapters/leetcode.js                              │ │
│  testcase pane    │   • reads source from window.monaco               │ │
│   (stdin) ────►   │   • reads input from the "Testcase" tab           │ │
│                   │   • mounts <iframe src="panel/index.html"> ───────┼─┼─► visualizer-core
│                   │   • forwards { source, stdin, language }          │ │      │
│                   └───────────────────────────────────────────────────┘ │      ▼
└─────────────────────────────────────────────────────────────────────────┘   POST localhost:8000/trace
```

## Build

```bash
npm run build --workspace=@dsa-viz/browser-extension
```

Produces an unpacked extension under `dist/` containing:
- `manifest.json`
- `src/` (content scripts, panel HTML)
- `src/panel/standalone.{mjs,css}` (the bundled visualizer-core)
- `smoke.html`, `problems/two-sum/index.html` (test fixtures, harmless to ship)

`EXTENSION_TEST_MATCH=1 npm run build ...` adds `http://localhost/*`
matchers to every content_script entry — used by the Playwright
persistent-context test (`tests/extension.spec.ts`).

## Load in real Chrome (manual end-to-end)

1. Run the backend locally: `uvicorn server.main:app --port 8000 --app-dir packages/backend/src`
2. Open `chrome://extensions`, enable Developer Mode.
3. **Load unpacked** → select `packages/browser-extension/dist/`.
4. Visit `https://leetcode.com/problems/two-sum/` — a "Visualize" button
   appears bottom-right. Click it; the panel iframe loads, reads the
   Monaco source, and POSTs to localhost:8000.

The persistent-context Playwright test automates steps 1, 3, and 4
against a local Monaco-mock fixture; it doesn't cover real leetcode.com
because of DOM drift + rate limits.

## Adding a new platform

Drop a new file under `src/adapters/<host>.js` exporting:

```js
export default {
  match: () => location.host === "yoursite.com",
  readSource: () => "...",         // returns string
  readStdin:  () => "...",         // returns string
  detectLanguage: () => "python",  // or "cpp"
  // optional UI hook:
  mountButton: (onClick) => { /* place a button in the page chrome */ }
};
```

Add a `content_scripts` entry in `manifest.json` pointing at the new file.

## Status

Today's adapters are deliberately conservative — they read what is rendered
in the DOM and don't try to instrument the editor. The LeetCode adapter is
the most fleshed-out reference.
