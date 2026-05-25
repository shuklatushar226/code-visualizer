# DSA Code Visualizer

A universal, line-by-line code visualizer aimed at students preparing for placements.
Write code in Python or C++, see every step animated: variables changing, the call
stack growing, linked lists rewiring, trees being traversed, heaps re-balancing.

Designed to **attach to any editor or coding platform** — LeetCode, HackerRank,
GeeksforGeeks, Codeforces, VS Code, or a standalone web app — through a shared
**Trace Event Protocol**.

---

## What problem it solves

Students preparing for placements struggle with three recurring pain points:

1. **Debugging blindness.** `print` debugging hides the *shape* of data
   (especially trees, graphs, linked lists). Students cannot "see" what their
   code is doing.
2. **Editor lock-in.** Existing visualizers (PythonTutor, AlgoExpert) require
   leaving the platform where the student practices.
3. **C++ gap.** Most visualizers only support Python. Indian placement
   interviews are dominated by C++.

This project tackles all three by separating **tracing** from **rendering**, so a
single visualizer panel can plug into many surfaces.

---

## High-level architecture

```
            ┌─────────────────┐         ┌─────────────────┐
   code ──▶│ tracer-python   │         │ tracer-cpp      │── code
            │ (sys.settrace)  │         │ (GDB/MI driver) │
            └────────┬────────┘         └────────┬────────┘
                     │                           │
                     ▼                           ▼
            ┌──────────────────────────────────────────┐
            │      Trace Event Protocol (JSON)         │
            │   one event per executed source line     │
            └────────┬─────────────────────────────────┘
                     │
                     ▼
            ┌──────────────────────────────────────────┐
            │      backend (FastAPI, sandboxed)        │
            │      POST /trace  →  trace JSON          │
            └────────┬─────────────────────────────────┘
                     │
        ┌────────────┼────────────────────┬────────────┐
        ▼            ▼                    ▼            ▼
 ┌────────────┐ ┌────────────┐  ┌──────────────────┐ ┌────────────┐
 │ web-app    │ │ vscode-ext │  │ browser-extension│ │ embeddable │
 │ (standalone│ │            │  │ (LeetCode, GfG,  │ │ JS widget  │
 │  paste &   │ │            │  │  HackerRank ...) │ │            │
 │  trace)    │ │            │  │                  │ │            │
 └─────┬──────┘ └─────┬──────┘  └─────────┬────────┘ └─────┬──────┘
       │              │                   │                │
       └──────────────┴───────────────────┴────────────────┘
                              │
                              ▼
                  ┌─────────────────────────┐
                  │   visualizer-core       │
                  │  (shared React lib)     │
                  │  CodePane • CallStack   │
                  │  ArrayView • TreeView   │
                  │  LinkedListView • Graph │
                  │  StackView • HeapView   │
                  └─────────────────────────┘
```

The **Trace Event Protocol** is the contract. Anything that can produce it is a
valid tracer; anything that can consume it is a valid front-end.

See `docs/ARCHITECTURE.md` and `docs/TRACE_FORMAT.md` for details.

---

## Repository layout

```
code-visualizer/
├── docs/                      Architecture, trace format, roadmap
├── examples/                  Sample DSA programs (Python & C++)
└── packages/
    ├── trace-schema/          Shared JSON schema + TypeScript types
    ├── tracer-python/         Python tracer (working MVP)
    ├── tracer-cpp/            C++ tracer via GDB/MI (skeleton)
    ├── backend/               FastAPI server that runs tracers in a sandbox
    ├── visualizer-core/       React components: CodePane, ArrayView, TreeView…
    ├── web-app/               Standalone web app (paste code, see trace)
    ├── browser-extension/     Chrome MV3 extension with platform adapters
    └── vscode-extension/      VS Code extension stub
```

---

## Quick start (Python tracer)

The Python tracer is fully working in this scaffold. Try it now:

```bash
cd packages/tracer-python
python -m pip install -e .
dsa-trace ../../examples/python/two_sum.py --output trace.json
```

You'll get a `trace.json` file conforming to the Trace Event Protocol. Feed this
to any front-end (web-app, browser extension, etc.) to render the visualization.

---

## Roadmap

See `docs/ROADMAP.md`. The short version:

* **M1 – Python MVP** *(scaffolded)*: tracer + backend + standalone web app
* **M2 – Browser extension**: LeetCode adapter first, then HackerRank, GfG
* **M3 – C++ support**: GDB/MI driver, struct-aware heap snapshots
* **M4 – Pattern detection**: auto-recognize sliding window, two-pointer, DP
* **M5 – Recursion tree view**: backtracking and DP problems

---

## Licence

MIT — free for students and educators.
