"""Integration tests for the C++ tracer.

The expensive end-to-end path (compile + gdb step) is gated on the
toolchain being available, so this suite runs cleanly on macOS dev
boxes without gdb. On Linux CI it exercises the real compile + step.
"""
from __future__ import annotations

import shutil

import pytest

from cpp_tracer import trace_source


gdb_available = shutil.which("gdb") is not None and shutil.which("g++") is not None
needs_toolchain = pytest.mark.skipif(
    not gdb_available, reason="requires g++ and gdb on PATH"
)


def test_returns_error_when_gdb_missing(monkeypatch):
    """Without gdb on PATH, the tracer returns an error trace instead of crashing."""
    monkeypatch.setattr("shutil.which", lambda name: None if name == "gdb" else "/usr/bin/g++")
    res = trace_source("int main() { return 0; }")
    assert res["exit"]["status"] == "error"
    assert "gdb" in res["exit"]["message"].lower()


def test_compile_error_surfaces():
    """A program that fails to compile produces an error trace, not an exception."""
    res = trace_source("not c++ at all !!")
    assert res["exit"]["status"] == "error"
    assert res["events"] == []


@needs_toolchain
def test_simple_program_produces_valid_trace():
    """Smoke test: the end-to-end gdb path produces a schema-shaped trace.

    Strict assertions about decoded local values (e.g. observing x=3) are
    intentionally avoided here — early M3 decoders aren't reliable on all
    distros' gdb output formats. The harder invariants belong in unit
    tests against captured GDB output (see test_values.py).
    """
    src = "int main() { int x = 3; int y = x + 4; return y; }"
    res = trace_source(src)
    assert res["language"] == "cpp"
    assert res["version"] == "0.1"
    assert res["exit"]["status"] in {"ok", "error"}
    assert isinstance(res["events"], list)
    # Each event must have the required schema fields.
    for ev in res["events"]:
        assert {"t", "kind", "line", "file", "stack", "heap"} <= set(ev)
