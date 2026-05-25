"""js_tracer — V8 inspector-driven JavaScript tracer (stretch, skeleton).

Architecture sketch:
  1. Spawn node with --inspect-brk on a unix-domain socket.
  2. Drive via the V8 Inspector Protocol (chrome-remote-interface
     equivalent in Python — see pychrome).
  3. Each Debugger.paused event reports current frame + scope; decode
     RemoteObjects into the trace's Value/HeapObject shape.
  4. Source-map support so TypeScript inputs map to their .ts lines.

Implementation deferred. JS is friendlier than C++ for value
encoding because RemoteObject is already typed.
"""
from __future__ import annotations

from typing import Any, Dict

__version__ = "0.1.0"


def trace_source(source: str, stdin: str = "", max_events: int = 5000) -> Dict[str, Any]:
    return {
        "version": "0.1",
        "language": "javascript",
        "source": source,
        "stdin": stdin,
        "stdout": "",
        "stderr": "JavaScript tracer not yet implemented.",
        "exit": {
            "status": "error",
            "message": "JS support is a stretch goal — see docs/ROADMAP.md.",
            "truncated": False,
        },
        "events": [],
    }
