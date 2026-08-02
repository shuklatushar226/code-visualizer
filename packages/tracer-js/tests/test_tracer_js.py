"""End-to-end smoke for the JS tracer.

Gated on `node` being on PATH; macOS dev boxes usually have it via
Homebrew, but the test asserts schema-shape only (no step-specific
value assertions) for the same reason the C++ tracer's smoke does:
V8 stepping cadence varies across Node versions.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from js_tracer import trace_source

node_available = shutil.which("node") is not None
needs_node = pytest.mark.skipif(not node_available, reason="requires node on PATH")


def test_returns_error_when_node_missing(monkeypatch):
    """Without `node` on PATH, the tracer returns an error trace rather
    than crashing — same shape as the M3 cpp gdb-missing path."""
    monkeypatch.setattr("shutil.which", lambda name: None if name == "node" else "/usr/local/bin/" + name)
    res = trace_source("console.log(1);")
    assert res["exit"]["status"] == "error"
    assert "node" in res["exit"]["message"].lower()


def test_syntax_error_surfaces_in_stderr_or_error_status():
    """A program that fails to parse shouldn't hang the parent. Node
    will likely refuse to start (Inspector handshake never completes);
    we accept either an error trace or an ok-but-empty trace."""
    if not node_available:
        pytest.skip("requires node on PATH")
    res = trace_source("this is not javascript {{{", max_events=20)
    assert res["language"] == "javascript"
    # Either we time out parsing the Inspector URL (error) or Node sends
    # an immediate exception event before we can step. Both fine.
    assert res["exit"]["status"] in {"error", "ok"}


@needs_node
def test_uncaught_runtime_error_is_reported_as_error_trace():
    res = trace_source("const value = 7;\nthrow new Error('expected-7');\n", max_events=50)
    assert res["exit"]["status"] == "error"
    assert "expected-7" in res["exit"]["message"]
    assert any(event["kind"] == "exception" for event in res["events"])


@needs_node
def test_builtin_helpers_do_not_emit_node_internal_steps():
    source = (
        "const values = [1, 2, 3];\n"
        "const total = values.reduce((a, b) => a + b, 0);\n"
        "console.log(total);\n"
    )
    res = trace_source(source, max_events=500)
    assert res["exit"]["status"] == "ok"
    assert 1 <= len(res["events"]) < 100


@needs_node
def test_simple_program_produces_valid_trace():
    """Trace examples/js/fib.js, assert the schema holds on every
    event. No value-specific assertions for the reasons above."""
    src_path = Path(__file__).resolve().parent.parent.parent.parent / "examples" / "js" / "fib.js"
    if not src_path.exists():
        pytest.skip(f"example missing: {src_path}")
    res = trace_source(src_path.read_text(), max_events=200)
    assert res["language"] == "javascript"
    assert res["version"] == "0.1"
    assert res["exit"]["status"] in {"ok", "error"}
    assert isinstance(res["events"], list)
    for ev in res["events"]:
        assert {"t", "kind", "line", "file", "stack", "heap"} <= set(ev)
        assert ev["kind"] in {"step", "call", "return", "exception", "stdout"}
        # Every heap object carries a recognised kind — silently bad
        # encoders regress here.
        for obj in ev.get("heap", {}).values():
            assert obj.get("kind") in {"list", "dict", "set", "tuple", "object", "str"}
