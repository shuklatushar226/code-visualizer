# @dsa-viz/visualizer-core

Reusable React widgets that render a Trace Event Protocol document. Lives
at the centre of the architecture: every surface (the standalone web app,
the Chrome MV3 extension, the VS Code webview, any future Jupyter or
Obsidian widget) imports from here and gets the same playback experience.

There are **two ways** to consume the package, depending on whether the
host already has a bundler.

---

## 1. As an npm dependency (the web app's path)

```ts
import {
  VisualizerPanel,        // top-level orchestrator
  CodePane,               // source view with active-line highlight
  ControlBar,             // ⏮ ◀ ▶ ▶ slider + speed
  CallStack,              // frames + locals
  HeapView,               // dispatches to a structure renderer
  detectStructure,        // value -> {kind: "linked_list" | "tree" | ...}
  detectPatterns,         // events -> PatternHit[] (sliding window, dp, ...)
  buildRecursionTree,     // events -> CallNode tree (M5)
  diffTraces,             // (a, b) -> first divergence (stretch)
  usePlayback,            // hook backing ControlBar's state
  useTrace,               // hook that wraps a fetched Trace + patterns
  traceClient,            // (baseUrl) -> { trace, health }
} from "@dsa-viz/visualizer-core";
import "@dsa-viz/visualizer-core/dist/standalone.css"; // or build your own CSS
```

Drop `<VisualizerPanel trace={trace}/>` anywhere in your tree. React 18
peer-dep required.

`packages/web-app/src/App.tsx` is the reference consumer.

---

## 2. As a standalone bundle (extensions' path)

For surfaces that don't run a bundler — a Chrome extension iframe, a
VS Code webview, a CodePen — the package ships a single-file ES module
that inlines React.

```bash
npm run build:standalone --workspace=@dsa-viz/visualizer-core
# produces dist/standalone.mjs + dist/standalone.css
```

The bundle exports one function, `mountVisualizer`, with this contract:

```ts
function mountVisualizer(container: HTMLElement, trace: Trace): MountHandle;

interface MountHandle {
  /** Replace the rendered trace without remounting. */
  update(trace: Trace): void;
  /** Tear down React + free DOM. */
  unmount(): void;
}
```

Usage:

```html
<link rel="stylesheet" href="./standalone.css" />
<div id="root"></div>
<script type="module">
  import { mountVisualizer } from "./standalone.mjs";
  const handle = mountVisualizer(document.getElementById("root"), trace);
  // later, when a new trace lands:
  handle.update(newTrace);
  // on teardown:
  handle.unmount();
</script>
```

### Lifecycle invariants

- `mountVisualizer` always returns a fresh `MountHandle`. Don't call it
  twice on the same container — call `update` on the existing handle.
- `update(trace)` is cheap: it rerenders with the new prop. Playback
  state (current `t`, speed) resets to the new trace's `initialT=0`.
- `unmount` clears the container's children.

### Bundle properties

- ~240 KB minified (~60 KB gzipped) with React inlined.
- `process.env.NODE_ENV` is statically replaced with `"production"` at
  build time, so React's dev-only branches are tree-shaken.
- No external dependencies at runtime. Safe to load behind strict CSPs
  (the VS Code webview uses `script-src 'nonce-...'`).

`packages/browser-extension/src/panel/index.js` and
`packages/vscode-extension/src/extension.ts` are the reference consumers.

---

## Architecture cheat-sheet

`<VisualizerPanel/>` lays out four regions:

```
┌────────────────────────────────────────────────────────────┐
│ CodePane                       │ CallStack                  │
│ (current line highlight)       │ (frames + locals)          │
├────────────────────────────────┴────────────────────────────┤
│ Tabs:  Heap  | Recursion (N)                                │
│ HeapView (per-local structure)  OR  RecursionTreeView       │
├─────────────────────────────────────────────────────────────┤
│ ControlBar  ⏮  ▶  ▶  ◀▶ ─────────●─── t = 17 / 134  speed   │
└─────────────────────────────────────────────────────────────┘
```

- The **Recursion tab** auto-selects when the trace has more than five
  `call` events (a heuristic that says "this program is non-trivial").
- The **Heap tab** consults `detectStructure` per local; pattern hits
  from `detectPatterns` are overlaid on `<ArrayView/>`.

---

## Tests

- `npm test` (vitest) — covers `detectStructure`, `detectPatterns` (all
  four families incl. DP), `buildRecursionTree` (incl. `maxNodes` cap),
  and `diffTraces`.
- For end-to-end behaviour, see `packages/web-app/tests/e2e.spec.ts`
  (Playwright) and `packages/browser-extension/tests/smoke.spec.ts`.

---

## Layout

```
src/
├── components/                # React widgets
│   ├── VisualizerPanel.tsx    # the orchestrator
│   ├── CodePane.tsx
│   ├── ControlBar.tsx
│   ├── CallStack.tsx
│   ├── HeapView.tsx
│   ├── RecursionTreeView.tsx
│   └── structures/            # ArrayView, LinkedListView, TreeView, ...
├── lib/
│   ├── detectStructure.ts     # value snapshot -> renderer kind
│   ├── recursionTree.ts       # events -> CallNode tree (M5)
│   ├── diffTraces.ts          # two traces -> first divergence
│   ├── traceClient.ts         # tiny fetch wrapper for the backend
│   └── patterns/              # M4 detectors
│       ├── slidingWindow.ts
│       ├── twoPointer.ts
│       ├── binarySearch.ts
│       └── dp.ts
├── hooks/
│   ├── usePlayback.ts
│   └── useTrace.ts
├── standalone.tsx             # the bundle's entry point
└── styles.css
```
