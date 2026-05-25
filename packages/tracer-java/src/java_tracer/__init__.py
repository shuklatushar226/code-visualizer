"""java_tracer — JDI-driven Java tracer (stretch goal, skeleton).

Architecture sketch (mirrors tracer-cpp):
  1. Compile user source with `javac -g`.
  2. Launch under JDB or via JDI directly (e.g. `com.sun.jdi`).
  3. Step one line at a time, decode locals using JDI's typed value
     interfaces (so we don't have to parse stringified output).
  4. Emit Trace Event Protocol JSON identical in shape to the Python
     and C++ tracers.

Implementation deferred — this file exists so the package is a real
workspace member and the route can dispatch to it later.
"""
from __future__ import annotations

from typing import Any, Dict

__version__ = "0.1.0"


def trace_source(source: str, stdin: str = "", max_events: int = 5000) -> Dict[str, Any]:
    return {
        "version": "0.1",
        "language": "java",
        "source": source,
        "stdin": stdin,
        "stdout": "",
        "stderr": "Java tracer not yet implemented.",
        "exit": {
            "status": "error",
            "message": "Java support is a stretch goal — see docs/ROADMAP.md.",
            "truncated": False,
        },
        "events": [],
    }
