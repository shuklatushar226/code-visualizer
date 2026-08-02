# DSV · Code Visualizer

[![Live demo](https://img.shields.io/badge/Live_demo-Open_visualizer-d7ff49?style=for-the-badge&logo=render&logoColor=050605)](https://code-visualizer-pr4n.onrender.com/)
[![CI](https://github.com/shuklatushar226/code-visualizer/actions/workflows/ci.yml/badge.svg)](https://github.com/shuklatushar226/code-visualizer/actions/workflows/ci.yml)
[![MIT](https://img.shields.io/badge/license-MIT-55e8ff.svg)](LICENSE)

![Code Visualizer preview](packages/web-app/public/og-v3.png)

A polyglot, line-by-line runtime visualizer for understanding algorithms—not just
running them. Paste Python, C++, or JavaScript and watch variables, call stacks,
linked lists, trees, arrays, and recursion evolve one event at a time. A Java/JDI
tracer is also included for local environments with JDK 17+.

**[Try the deployed visualizer →](https://code-visualizer-pr4n.onrender.com/)**

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
            │ backend (FastAPI, isolated subprocesses) │
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
    ├── tracer-python/         Python tracer via sys.settrace
    ├── tracer-cpp/            C++ tracer via GDB/MI
    ├── tracer-js/             JavaScript tracer via V8 Inspector
    ├── tracer-java/           Java tracer via JDI (local JDK required)
    ├── backend/               FastAPI execution and sharing API
    ├── visualizer-core/       React components: CodePane, ArrayView, TreeView…
    ├── web-app/               Standalone web app (paste code, see trace)
    ├── browser-extension/     Chrome MV3 extension with platform adapters
    └── vscode-extension/      VS Code webview integration
```

---

## Quick start

### Standalone web app

```bash
# Backend (FastAPI on :8000)
python3 -m venv .venv && source .venv/bin/activate
pip install -e packages/tracer-python -e packages/tracer-cpp -e packages/tracer-js -e packages/tracer-java -e 'packages/backend[dev]'
uvicorn server.main:app --port 8000 --app-dir packages/backend/src &

# Web app (Vite on :5173)
npm install
npm run dev:web
```

Open http://localhost:5173 and press **Run & Visualize**. Example cards launch
complete visual stories in one click.

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
npm run test:soak # 1,000 HTTP cases against a local production container
npm run lint      # ESLint + Ruff
```

See [`docs/RELIABILITY.md`](docs/RELIABILITY.md) for the deterministic coverage
matrix, trace invariants, reproduction steps, and latest verified result.

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

**Quality floor**: 210 automated checks on this release — 121 passing pytest
tests (plus 3 platform-gated skips), 78 Vitest tests, 8 real web journeys, and
3 extension tests. GitHub Actions also builds and smoke-tests the same
production container used by Render.

**Stretch goals** (`docs/ROADMAP.md` "Stretch"):
* Shareable links ✅ — SQLite-backed `POST /share` + `GET /t/{code}` + UI button;
  set `SHARE_DB_PATH` to a mounted volume for persistence across redeploys
* Diff view ✅ — `diffTraces(a, b)` walks two traces in lockstep,
  reports the first divergence
* AI explainer — streaming `POST /explain`; the UI enables it only when the
  selected deployment reports a configured provider
* Java tracer ✅ — `packages/tracer-java` drives the user's program through a
  JDI helper (`helper/dsaviz/Tracer.java`): line-by-line stepping, call stack,
  recursion, exceptions, arrays, user objects (ListNode/TreeNode → linked
  list/tree), and `java.util` collections (Map/Set/Collection). Needs a JDK
  17+ on PATH; the route returns 501 otherwise.
* JS tracer — V8 Inspector driver in `packages/tracer-js`; needs `node` on PATH

## Execution security

The public Render demo uses an unprivileged subprocess boundary, process-group
cleanup, timeouts, resource limits, admission limits, and per-client rate
limits. It is appropriate for a controlled portfolio demo, but it is **not a
hard multi-tenant sandbox**. `docs/SANDBOX.md` documents the stronger
per-execution Docker/seccomp path and recommends gVisor or microVM isolation for
hostile public workloads.

## Engineering highlights

* One versioned Trace Event Protocol connects four very different debugger
  mechanisms to a single React renderer.
* Content-aware views distinguish actual recursion from ordinary calls and
  render object references as semantic labels instead of process-specific IDs.
* Deployment capabilities are discovered at runtime, so the UI never presents
  an unavailable compiler or AI provider as a working hosted feature.
* Trace links use bounded, collision-safe SQLite storage and remain stable
  across backend restarts.

---

## Licence

MIT — free for students and educators.
