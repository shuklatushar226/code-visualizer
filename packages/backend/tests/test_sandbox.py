"""Sandbox-level tests for the Python tracer subprocess."""

from __future__ import annotations

from dataclasses import replace

import pytest

from server import sandbox
from server.sandbox import run_python_in_sandbox


def test_ok_trace_simple_assignment():
    res = run_python_in_sandbox("a = 1\nb = 2\nc = a + b\n")
    assert res["exit"]["status"] == "ok"
    assert len(res["events"]) >= 3
    names = {k for f in res["events"][-1]["stack"] for k in f["locals"]}
    assert {"a", "b", "c"} <= names


def test_runtime_error_surfaces_exit_status():
    res = run_python_in_sandbox("a = 1\nb = 1 / 0\n")
    assert res["exit"]["status"] == "error"
    kinds = [e["kind"] for e in res["events"]]
    assert "exception" in kinds


def test_syntax_error_surfaces_in_stderr():
    res = run_python_in_sandbox("def broken(:\n    pass\n")
    assert res["exit"]["status"] == "error"
    assert "SyntaxError" in (res.get("stderr") or "") or "Syntax" in res["exit"].get("message", "")


def test_source_too_large_rejected():
    big = "a = 1\n" * 20000
    with pytest.raises(ValueError, match="MAX_SOURCE_BYTES"):
        run_python_in_sandbox(big)


def test_timeout_returns_timeout_status(monkeypatch):
    """Wall-clock timeout in the parent should produce a timeout exit."""
    monkeypatch.setattr(sandbox, "config", replace(sandbox.config, sandbox_timeout_seconds=1))
    res = run_python_in_sandbox("while True:\n    pass\n")
    assert res["exit"]["status"] == "timeout"
    assert res["exit"]["truncated"] is True


def test_json_roundtrips():
    import json

    res = run_python_in_sandbox("x = {'k': [1, 2, 3]}\n")
    json.dumps(res)


def test_network_access_returns_error_under_tight_timeout(monkeypatch):
    """A program that tries to make a TCP connection shouldn't hang the
    parent. The wall-clock timeout in the parent is the floor that
    catches everything else.
    """
    monkeypatch.setattr(sandbox, "config", replace(sandbox.config, sandbox_timeout_seconds=2))
    src = "import socket\ns = socket.socket()\ns.settimeout(5)\ntry:\n    s.connect(('10.255.255.1', 80))\nexcept Exception as e:\n    pass\n"
    res = run_python_in_sandbox(src)
    # Either ok (connection refused fast) or timeout — never hangs the parent.
    assert res["exit"]["status"] in {"ok", "timeout", "error"}
