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

## Quick start

### Standalone web app

```bash
# Backend (FastAPI on :8000)
python3 -m venv .venv && source .venv/bin/activate
pip install -e packages/tracer-python -e packages/tracer-cpp -e 'packages/backend[dev]'
uvicorn server.main:app --port 8000 --app-dir packages/backend/src &

# Web app (Vite on :5173)
npm install
npm run dev:web
```

Open http://localhost:5173, paste Python, press **Run & Visualize**.

### CLI

```bash
dsa-trace examples/python/two_sum.py --output trace.json
```

Produces a `trace.json` conforming to the Trace Event Protocol; feed it
to any of the front-ends.

### Tests

```bash
npm test          # py + js unit suites (fast)
npm run test:e2e  # Playwright e2e (slow, launches both servers)
```

---

## Roadmap status

See `docs/ROADMAP.md` for the full plan. Where things stand:

* **M1 – Python MVP** ✅ — tracer + backend + web app, end-to-end
* **M2 – Browser + VS Code extensions** ✅ — shared standalone bundle of
  `visualizer-core` (React inlined) loads in the iframe / webview
* **M3 – C++ support** ✅ — value decoders for primitives + annotated
  structs (`<viz.hpp>` macros), gdb/MI driver, heap reconstruction by
  pointer address; graceful 501 when gdb isn't on PATH
* **M4 – Pattern detection** ✅ — sliding window, two pointer, binary
  search overlays on the array view
* **M5 – Recursion tree view** ✅ — d3-hierarchy layout of call/return
  events, active-frame highlight

**Quality floor**: 84 tests on `main` (42 pytest + 37 vitest + 5
Playwright). GitHub Actions runs three job lanes (python matrix +
node unit + e2e + extension bundles) on every push.

**Stretch goals** (`docs/ROADMAP.md` "Stretch"):
* Shareable links ✅ — `POST /share` + `GET /t/{code}` + UI button
* Diff view ✅ — `diffTraces(a, b)` walks two traces in lockstep,
  reports the first divergence
* AI explainer — `POST /explain` route stub; wire `DSA_VIZ_AI_KEY` and a
  provider to enable
* Java / JS tracers — package skeletons in `packages/tracer-java`,
  `packages/tracer-js`; route returns 501

**Sandbox hardening**: `docs/SANDBOX.md` documents the production
docker invocation; `packages/backend/Dockerfile.sandbox` and
`sandbox.seccomp.json` are the production-ready artefacts.

---

## Licence

MIT — free for students and educators.
