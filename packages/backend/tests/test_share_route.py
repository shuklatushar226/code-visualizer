"""Tests for the shareable-trace route."""
from __future__ import annotations

from fastapi.testclient import TestClient

from server.main import app
from server.routes import share as share_route


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


def test_repeated_identical_saves_do_not_evict_the_trace():
    share_route._STORE.clear()
    share_route._ORDER.clear()
    payload = {"trace": {"version": "0.1", "events": []}}
    code = None
    for _ in range(share_route._MAX_ENTRIES + 1):
        response = client.post("/share", json=payload)
        assert response.status_code == 200
        code = response.json()["code"]

    assert len(share_route._STORE) == 1
    assert share_route._ORDER == [code]
    assert client.get(f"/t/{code}").status_code == 200


def test_oversized_shared_trace_is_rejected():
    response = client.post(
        "/share",
        json={"trace": {"blob": "x" * (share_route._MAX_TRACE_BYTES + 1)}},
    )
    assert response.status_code == 413
