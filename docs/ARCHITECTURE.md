# Architecture

## Design goals

1. **Universal.** A single visualizer panel should work on LeetCode, HackerRank,
   GfG, Codeforces, VS Code, and a standalone page. We achieve this by treating
   each integration as a thin **adapter** around a shared React component
   library.
2. **Language-pluggable.** Adding Java, JS, or Go later should not require
   re-writing the front-end. Each language ships a **tracer** that emits the
   same JSON event protocol.
3. **DSA-aware.** Most generic debuggers show raw memory or opaque objects.
   This project includes a **structure detector** that recognises arrays,
   linked lists, trees, graphs, stacks, queues, and heaps from the live
   variable snapshot and renders them with the right widget.
4. **Safe.** Student code runs in a sandboxed worker with CPU, memory, and
   wall-clock limits. The sandbox is the only component that ever executes
   untrusted code.

## Layered view

```
┌──────────────────────────────────────────────────────────────┐
│  Surface layer                                                │
│  ─ web-app (Vite + React)                                     │
│  ─ browser-extension (Chrome MV3)                             │
│  ─ vscode-extension                                           │
│  All import visualizer-core and call backend over HTTP.       │
├──────────────────────────────────────────────────────────────┤
│  Visualizer-core (shared React lib)                           │
│  ─ <VisualizerPanel/>   top-level orchestrator                │
│  ─ <CodePane/>          syntax-highlighted code w/ cursor     │
│  ─ <ControlBar/>        play / step fwd / step back / speed   │
│  ─ <CallStack/>         stack of frames with their locals     │
│  ─ <HeapView/>          heap objects keyed by id              │
│  ─ structures/*         ArrayView, LinkedListView, TreeView,  │
│                         GraphView, StackView, QueueView,      │
│                         HeapTreeView                          │
│  ─ hooks/usePlayback    step state machine                    │
│  ─ lib/detectStructure  infers DS kind from a value snapshot  │
├──────────────────────────────────────────────────────────────┤
│  Trace Event Protocol  (docs/TRACE_FORMAT.md)                 │
├──────────────────────────────────────────────────────────────┤
│  Backend (FastAPI)                                            │
│  ─ POST /trace { language, source, stdin } → trace JSON       │
│  ─ Spawns a sandboxed worker that invokes the right tracer.   │
├──────────────────────────────────────────────────────────────┤
│  Tracers                                                      │
│  ─ tracer-python:  sys.settrace based, in-process             │
│  ─ tracer-cpp:     drives g++ -g + GDB/MI via pygdbmi         │
└──────────────────────────────────────────────────────────────┘
```

## Why a "trace first" model

Other visualizers stream debugger events to the UI live. That's elegant but
brittle: any UI hiccup loses state, replay is impossible, and offline mode is
out of reach. We instead **run to completion, capture the entire trace as JSON,
then play it back in the UI**. Trade-offs:

| Pros                                  | Cons                                       |
|---------------------------------------|--------------------------------------------|
| Deterministic replay (scrubbing!)     | High-memory traces for very long programs  |
| UI is purely a function of state      | Cannot interact with `input()` mid-trace   |
| Easy to cache, share, embed in tests  | Programs with side-effects need stdin only |

For DSA practice these trade-offs are exactly right: programs are short, no
interactive I/O, and step-backward is a killer feature for debugging.

## Sandbox model

The backend never executes student code in-process. It:

1. Receives `{ language, source, stdin }`.
2. Writes source to a temp dir.
3. Spawns a subprocess with:
   * `ulimit -t SANDBOX_TIMEOUT_SECONDS` (CPU)
   * `ulimit -v 256M` (address space)
   * Network namespace removed (or `--network none` in Docker)
   * Read-only filesystem except `/tmp/work`
4. The subprocess imports the appropriate tracer, runs the user program,
   writes the trace to stdout.
5. Backend reads stdout, validates against the JSON schema, returns it.

For production, run this whole thing inside `gvisor` or Firecracker.

## Structure detection (the secret sauce)

`visualizer-core/src/lib/detectStructure.ts` looks at a heap object and decides
how to render it:

* **Array**: Python `list` / C++ `std::vector` → `ArrayView` with index labels
  and pointer markers from any int-valued local whose name matches `l|r|lo|hi|i|j|k|left|right|start|end|mid`.
* **Linked list**: object with fields `{ val|data|value, next }`, optionally
  `prev` → `LinkedListView` with arrows.
* **Tree**: object with fields `{ val, left, right }` or `{ val, children[] }` →
  `TreeView` with d3-hierarchy layout.
* **Graph**: dict mapping node→list or `{ nodes:[], edges:[] }` → `GraphView`
  with force-directed layout.
* **Stack**: locals named `stack|st` that are arrays → `StackView` rendered
  vertically with the top highlighted.
* **Queue**: `collections.deque`, or locals named `queue|q|dq` → `QueueView`.
* **Heap**: locals named `heap|pq|minheap|maxheap` or values produced by
  `heapq` calls → `HeapTreeView` showing the implicit binary tree.

Detection is best-effort and overridable: a `# @viz: tree` annotation in the
source forces a kind, and the user can switch widgets from the panel.

## Front-end ↔ trace contract

The UI never executes code. It only knows about events. The orchestrator
(`<VisualizerPanel/>`) keeps a cursor `t` and renders:

* The line highlighted in `<CodePane/>` from `events[t].line`.
* The frames in `<CallStack/>` from `events[t].stack`.
* The structures in `<HeapView/>` from `events[t].heap`.

Step forward = `t += 1`. Step backward = `t -= 1`. That is the whole state
machine. This is why the trace format below is the single most important file
in the repository.
