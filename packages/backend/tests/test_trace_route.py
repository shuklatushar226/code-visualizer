"""HTTP-level tests for the FastAPI app."""

from __future__ import annotations

from fastapi.testclient import TestClient

from server.main import app


client = TestClient(app)


def test_healthz_ok():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_version_advertises_protocol():
    r = client.get("/version")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "0.1.0"
    assert body["protocol"] == "0.1"


def test_trace_python_returns_events():
    r = client.post("/trace", json={"language": "python", "source": "x = 1\ny = x + 1\n", "stdin": ""})
    assert r.status_code == 200
    body = r.json()
    assert body["language"] == "python"
    assert body["exit"]["status"] == "ok"
    assert len(body["events"]) >= 2


def test_trace_cpp_returns_501():
    r = client.post("/trace", json={"language": "cpp", "source": "int main(){}", "stdin": ""})
    assert r.status_code == 501
    assert "M3" in r.json()["detail"]


def test_trace_unsupported_language_rejected():
    r = client.post("/trace", json={"language": "rust", "source": "fn main() {}", "stdin": ""})
    assert r.status_code == 400


def test_trace_oversized_source_rejected_by_pydantic():
    # source max_length is 200_000 per the TraceRequest model.
    huge = "x = 1\n" * 50_000  # 300_000 bytes
    r = client.post("/trace", json={"language": "python", "source": huge, "stdin": ""})
    assert r.status_code == 422


def test_trace_java_returns_501_with_skeleton_message():
    r = client.post("/trace", json={"language": "java", "source": "class A {}", "stdin": ""})
    assert r.status_code == 501
    assert "stretch" in r.json()["detail"].lower()


def test_trace_javascript_returns_501():
    r = client.post("/trace", json={"language": "javascript", "source": "const x=1;", "stdin": ""})
    assert r.status_code == 501


def test_explain_returns_501_without_api_key(monkeypatch):
    monkeypatch.delenv("DSA_VIZ_AI_KEY", raising=False)
    r = client.post("/explain", json={"event": {"line": 1}, "source": "x = 1"})
    assert r.status_code == 501
    assert "stretch-goal" in r.json()["detail"].lower() or "key" in r.json()["detail"].lower()
