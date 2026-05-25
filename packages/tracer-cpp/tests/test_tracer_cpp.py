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
def test_simple_program_produces_events():
    src = "int main() { int x = 3; int y = x + 4; return y; }"
    res = trace_source(src)
    assert res["language"] == "cpp"
    assert res["exit"]["status"] == "ok"
    assert len(res["events"]) >= 1
    # At some point we should see x with value 3.
    saw_x = False
    for ev in res["events"]:
        for frame in ev["stack"]:
            x = frame["locals"].get("x")
            if x and x.get("kind") == "int" and x.get("v") == 3:
                saw_x = True
                break
    assert saw_x, "expected to observe x=3 in at least one event"
