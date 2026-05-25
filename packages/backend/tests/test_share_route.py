"""Tests for the shareable-trace route."""
from __future__ import annotations

from fastapi.testclient import TestClient

from server.main import app


client = TestClient(app)


def test_save_then_fetch_roundtrips():
    trace = {
        "version": "0.1",
        "language": "python",
        "source": "x = 1",
        "events": [{"t": 0, "kind": "step", "line": 1, "file": "main.py", "stack": [], "heap": {}, "stdout_delta": None, "exception": None}],
        "exit": {"status": "ok", "message": None, "truncated": False},
    }
    r = client.post("/share", json={"trace": trace})
    assert r.status_code == 200
    body = r.json()
    code = body["code"]
    assert len(code) == 8
    assert body["url"] == f"/t/{code}"

    r2 = client.get(f"/t/{code}")
    assert r2.status_code == 200
    assert r2.json()["source"] == "x = 1"


def test_fetch_unknown_returns_404():
    r = client.get("/t/nosuch00")
    assert r.status_code == 404
