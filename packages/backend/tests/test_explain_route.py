"""Tests for the AI-explainer route.

The route's structure (prompt construction, cache, rate limit, SSE
streaming, 501 fallback) is verified with a FixtureProvider so no API
key is needed and no real network call happens.
"""
from __future__ import annotations

import os
from typing import AsyncIterator

import pytest
from fastapi.testclient import TestClient

from server import ai
from server.main import app
from server.routes import explain as explain_route


client = TestClient(app)


# ────────────────────────────────────────────────────────────────────
# Setup / teardown — reset the route's lazy provider + cache between
# tests so isolation holds.
# ────────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _reset_state(monkeypatch):
    explain_route._reset_provider()
    explain_route._CACHE.clear()
    explain_route._BUCKETS.clear()
    # Force the fixture provider unless a test overrides.
    monkeypatch.setenv("DSA_VIZ_AI_PROVIDER", "fixture")
    yield
    explain_route._reset_provider()
    explain_route._CACHE.clear()
    explain_route._BUCKETS.clear()


SAMPLE_REQ = {
    "event": {"line": 2, "func": "<module>", "locals": {"x": {"kind": "int", "v": 5}}},
    "source": "x = 1\nx = x + 4\n",
    "language": "python",
}


def _read_sse(resp) -> list[tuple[str, str]]:
    """Parse the SSE stream into (event, data) tuples."""
    out: list[tuple[str, str]] = []
    block: list[str] = []
    for line in resp.iter_lines():
        if not line:
            if block:
                ev = "message"
                data: list[str] = []
                for ln in block:
                    if ln.startswith("event: "):
                        ev = ln[7:]
                    elif ln.startswith("data: "):
                        data.append(ln[6:])
                out.append((ev, "\n".join(data)))
                block = []
            continue
        block.append(line)
    if block:
        ev = "message"
        data = []
        for ln in block:
            if ln.startswith("event: "):
                ev = ln[7:]
            elif ln.startswith("data: "):
                data.append(ln[6:])
        out.append((ev, "\n".join(data)))
    return out


# ────────────────────────────────────────────────────────────────────
# Happy path
# ────────────────────────────────────────────────────────────────────


def test_explain_streams_tokens_and_done():
    """The FixtureProvider yields the canned sentence in three chunks;
    the route surfaces them as `event: token` SSE messages followed by
    a single `event: done` containing the full text."""
    with client.stream("POST", "/explain", json=SAMPLE_REQ) as resp:
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = _read_sse(resp)
    tokens = [data for ev, data in events if ev == "token"]
    done = [data for ev, data in events if ev == "done"]
    assert tokens, "expected at least one token chunk"
    assert len(done) == 1, "expected exactly one done event"
    assert "".join(tokens).strip() == done[0]


def test_explain_caches_repeat_requests():
    """Second call with identical (source, line, language) hits the cache
    and emits one token + one done (no re-streaming from the provider)."""
    # Prime the cache.
    with client.stream("POST", "/explain", json=SAMPLE_REQ) as r1:
        _ = _read_sse(r1)
    # Replace provider with one that raises if invoked — proves the
    # second request didn't touch it.
    class ExplodingProvider(ai.AIProvider):
        async def stream_explain(self, *a, **kw):  # type: ignore[override]
            raise AssertionError("provider should not be called on cache hit")
            yield  # pragma: no cover
    explain_route._PROVIDER = ExplodingProvider()  # type: ignore[assignment]

    with client.stream("POST", "/explain", json=SAMPLE_REQ) as r2:
        assert r2.status_code == 200
        events = _read_sse(r2)
    kinds = [ev for ev, _ in events]
    assert "token" in kinds and "done" in kinds


def test_prompt_includes_active_line_and_locals(monkeypatch):
    """The system + user prompts handed to the provider must mention
    the line number, the active source line, and the locals summary."""
    captured: dict = {}

    class CapturingProvider(ai.AIProvider):
        async def stream_explain(self, system_prompt, user_prompt, *, max_tokens=80):  # type: ignore[override]
            captured["system"] = system_prompt
            captured["user"] = user_prompt
            yield "ok"

    explain_route._PROVIDER = CapturingProvider()  # type: ignore[assignment]
    with client.stream("POST", "/explain", json=SAMPLE_REQ) as resp:
        list(_read_sse(resp))
    assert "system" in captured
    assert "Currently executing line 2" in captured["user"]
    assert "x = x + 4" in captured["user"]
    assert "x=5" in captured["user"]


# ────────────────────────────────────────────────────────────────────
# Failure paths
# ────────────────────────────────────────────────────────────────────


def test_returns_501_when_provider_init_fails(monkeypatch):
    """If make_provider raises AIProviderError, the route surfaces 501
    (same shape as the pre-implementation stub)."""
    def _broken_factory():
        raise ai.AIProviderError("no key configured")
    monkeypatch.setattr(ai, "make_provider", _broken_factory)
    monkeypatch.setattr(explain_route, "make_provider", _broken_factory)
    # Force re-init.
    explain_route._reset_provider()

    r = client.post("/explain", json=SAMPLE_REQ)
    assert r.status_code == 501
    assert "no key" in r.json()["detail"].lower()


def test_provider_runtime_error_surfaces_as_error_event(monkeypatch):
    """An exception during streaming yields an `event: error` SSE message,
    not a hard 500."""
    class ExplodingProvider(ai.AIProvider):
        async def stream_explain(self, *a, **kw):  # type: ignore[override]
            yield "starting up"
            raise ai.AIProviderError("rate limited")
    explain_route._PROVIDER = ExplodingProvider()  # type: ignore[assignment]
    with client.stream("POST", "/explain", json=SAMPLE_REQ) as resp:
        assert resp.status_code == 200
        events = _read_sse(resp)
    kinds = [ev for ev, _ in events]
    assert "error" in kinds


def test_rate_limit_returns_429():
    """Exhaust the per-IP token bucket, then the next request 429s."""
    # The bucket starts full (30 tokens); blast 31 to exhaust + overflow.
    overage_seen = False
    for _ in range(31):
        r = client.post("/explain", json=SAMPLE_REQ)
        if r.status_code == 429:
            overage_seen = True
            break
        # Drain the response body to release the connection.
        if r.headers.get("content-type", "").startswith("text/event-stream"):
            r.read()
    assert overage_seen, "expected at least one 429 after 31 requests"
