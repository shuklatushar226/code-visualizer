"""Regression tests for backend bugs found in the May-2026 audit.

Each test reproduces a confirmed defect; they fail on the pre-fix code.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from server import sandbox
from server.main import app
from server.routes import explain as explain_route
from server.routes import share as share_route
from server.sandbox import run_python_in_sandbox

client = TestClient(app)


# ───────────────────────── /share infinite loop ───────────────────────── #

def _reset_share():
    share_route._reset_connection_for_tests(":memory:")
    return share_route._connection()


def test_make_code_reuses_code_for_identical_trace():
    """Saving the SAME trace twice must reuse its code, not hang forever."""
    db = _reset_share()
    trace = {"version": "0.1", "hello": "world"}
    encoded = json.dumps(trace, sort_keys=True, separators=(",", ":"))
    c1 = share_route._make_code(encoded, db)
    db.execute(
        "INSERT INTO shared_traces VALUES (?, ?, ?, ?)",
        (c1, encoded, len(encoded), 0),
    )
    c2 = share_route._make_code(encoded, db)  # before fix: infinite loop
    assert c2 == c1


def test_make_code_resolves_distinct_trace_collision():
    """When a DIFFERENT trace already occupies the natural prefix, _make_code
    must return a different, terminating 8-char code."""
    db = _reset_share()
    trace = {"version": "0.1", "hello": "world"}
    encoded = json.dumps(trace, sort_keys=True, separators=(",", ":"))
    natural = share_route._make_code(encoded, db)
    other = json.dumps(
        {"version": "0.1", "something": "else"},
        sort_keys=True,
        separators=(",", ":"),
    )
    db.execute(
        "INSERT INTO shared_traces VALUES (?, ?, ?, ?)",
        (natural, other, len(other), 0),
    )
    new_code = share_route._make_code(encoded, db)  # before fix: infinite loop
    assert new_code != natural
    assert len(new_code) == 8


def test_share_same_trace_twice_over_http_reuses_code():
    _reset_share()
    trace = {
        "version": "0.1",
        "language": "python",
        "source": "x = 1",
        "events": [],
        "exit": {"status": "ok", "message": None, "truncated": False},
    }
    r1 = client.post("/share", json={"trace": trace})
    r2 = client.post("/share", json={"trace": trace})  # before fix: hangs
    assert r1.status_code == r2.status_code == 200
    assert r1.json()["code"] == r2.json()["code"]


# ───────────────────────── stdin forwarding ───────────────────────── #

def test_stdin_forwarded_to_traced_program():
    res = run_python_in_sandbox("x = input()\nprint('got', x)\n", stdin="hello\n")
    assert res["exit"]["status"] == "ok", res
    assert "hello" in (res["stdout"] or "")


def test_trace_route_forwards_stdin():
    r = client.post(
        "/trace",
        json={"language": "python", "source": "n = int(input())\nprint(n * 2)\n", "stdin": "21\n"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["exit"]["status"] == "ok", body
    assert "42" in (body["stdout"] or "")


# ───────────────────────── oversized source → 413 ───────────────────────── #

def test_oversized_source_between_limits_returns_413():
    # > MAX_SOURCE_BYTES (65536) but < pydantic max_length (200000)
    src = "x = 1\n" * 12000  # 72000 bytes
    r = client.post("/trace", json={"language": "python", "source": src, "stdin": ""})
    assert r.status_code == 413


# ───────────────────────── timeout message duration ───────────────────────── #

def test_timeout_trace_reports_overridden_duration():
    t = sandbox._timeout_trace("src", "javascript", timeout_seconds=15)
    assert "15s" in t["exit"]["message"]


def test_timeout_trace_defaults_to_config_duration():
    t = sandbox._timeout_trace("src", "python")
    assert f"{sandbox.config.sandbox_timeout_seconds}s" in t["exit"]["message"]


# ───────────────────────── CORS for chrome extensions ───────────────────────── #

def test_cors_allows_chrome_extension_origin():
    r = client.options(
        "/trace",
        headers={
            "Origin": "chrome-extension://abcdefghijklmnop",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert r.headers.get("access-control-allow-origin") == "chrome-extension://abcdefghijklmnop"


# ───────────────────────── /explain cache key includes locals ───────────────────────── #

def _explain_req(line, locals_):
    return explain_route.ExplainRequest(
        event={"line": line, "locals": locals_},
        source="total = 0\nfor i in range(3):\n    total += i\n",
        language="python",
    )


def test_explain_cache_key_distinguishes_different_locals():
    r0 = _explain_req(3, {"i": {"kind": "int", "v": 0}, "total": {"kind": "int", "v": 0}})
    r2 = _explain_req(3, {"i": {"kind": "int", "v": 2}, "total": {"kind": "int", "v": 1}})
    assert explain_route._cache_key(r0) != explain_route._cache_key(r2)


def test_explain_cache_key_stable_for_identical_state():
    a = _explain_req(3, {"i": {"kind": "int", "v": 1}})
    b = _explain_req(3, {"i": {"kind": "int", "v": 1}})
    assert explain_route._cache_key(a) == explain_route._cache_key(b)


# ───────────────────────── env-secret isolation ───────────────────────── #

def test_sandbox_child_cannot_read_parent_secret(monkeypatch):
    monkeypatch.setenv("DSA_VIZ_AI_KEY", "super-secret-value-123")
    res = run_python_in_sandbox(
        "import os\nprint(os.environ.get('DSA_VIZ_AI_KEY', 'ABSENT'))\n"
    )
    assert res["exit"]["status"] == "ok", res
    assert "super-secret-value-123" not in (res["stdout"] or "")


# ───────────────────────── unknown AI provider error is helpful ───────────────────────── #

def test_unknown_provider_error_lists_supported():
    from server.ai import AIProviderError, make_provider

    with pytest.raises(AIProviderError) as exc:
        make_provider("openai")
    msg = str(exc.value).lower()
    assert "anthropic" in msg and "fixture" in msg
