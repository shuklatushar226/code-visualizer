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

This package is plain ES modules + an HTML iframe for the panel. No build
step required. To load in Chrome:

1. Run the backend locally: `docker-compose up backend` (default `:8000`).
2. Open `chrome://extensions`, enable Developer Mode.
3. **Load unpacked** → select this folder.
4. Visit `https://leetcode.com/problems/two-sum/` — a "Visualize" button
   appears in the bottom-right.

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
