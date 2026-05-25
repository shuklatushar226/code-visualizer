# Roadmap

## M1 – Python MVP  *(scaffolded in this commit)*

Goal: a student can paste a Python solution on the standalone web app and step
through it.

Deliverables:

* `tracer-python` package with CLI: `dsa-trace file.py -o trace.json`
* `backend` with `POST /trace` returning a valid trace
* `visualizer-core` with `CodePane`, `ControlBar`, `CallStack`, `ArrayView`,
  `LinkedListView`, `TreeView`
* `web-app` wiring it all together

Acceptance: stepping through `examples/python/two_sum.py` shows the dictionary
growing entry by entry, with the current line highlighted.

## M2 – Browser extension

Goal: visualization without leaving LeetCode.

Deliverables:

* Manifest V3 extension with a content script that detects the Monaco editor.
* Adapter for LeetCode that:
  - reads the code from Monaco
  - reads sample input from the testcases panel
  - injects a side panel hosting `<VisualizerPanel/>`
* Adapter stubs for HackerRank, GfG, Codeforces.

Acceptance: on `leetcode.com/problems/two-sum/`, clicking the extension's
"Visualize" button opens a panel and steps through the user's current code.

## M3 – C++ support

Goal: same UX, but for C++.

Approach: drive `g++ -g -O0 user.cpp` and step the resulting binary via GDB's
machine interface (GDB/MI). Use `pygdbmi` from the backend sandbox.

Hard parts:

* Reconstructing `std::vector`, `std::list`, `std::map`, `std::set`, user
  `struct`s from GDB's `-data-evaluate-expression`.
* Detecting the "interesting" struct fields for linked lists / trees without
  pretty-printers.

Mitigation: ship a tiny header `<viz.hpp>` students can `#include` to declare
"this struct is a tree node"; without the include, fall back to GDB Python
pretty-printers shipped with libstdc++.

## M4 – Pattern detection

Auto-recognise common DSA patterns and overlay hints:

* **Sliding window** — locals `l`, `r` (or `left`, `right`) moving monotonically.
* **Two pointer** — two pointers moving from opposite ends.
* **Binary search** — locals `lo`, `hi`, `mid` updating in a halving pattern.
* **DP** — a 1D or 2D array whose cells fill in a regular order.

The UI renders extra annotations (window highlight, search range overlay)
without the student having to ask.

## M5 – Recursion tree view

For backtracking and DP problems, render the recursion as a tree whose nodes
are call frames. Useful for problems like N-Queens, Permutations, Combination
Sum, and any DP-with-memo problem.

## Stretch goals

* **AI explainer**: send the current frame + line to an LLM and show a one-line
  explanation in the panel.
* **Shareable links**: persist traces to short URLs (`viz.dev/t/abc123`) for
  teachers to share examples.
* **Diff view**: paste two versions of code, see where their traces diverge.
* **Java + JS**: JDI for Java; debugger protocol + V8 inspector for JS.
