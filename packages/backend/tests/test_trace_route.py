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


def test_trace_cpp_returns_501_or_traces():
    """Without a toolchain (e.g. macOS dev) the route returns 501. With g++
    and gdb on PATH (Linux CI) it dispatches and returns a real trace."""
    import shutil

    r = client.post("/trace", json={"language": "cpp", "source": "int main(){}", "stdin": ""})
    if shutil.which("gdb") and shutil.which("g++"):
        assert r.status_code == 200
        body = r.json()
        assert body["language"] == "cpp"
        assert body["exit"]["status"] in {"ok", "error"}
    else:
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


def test_trace_java_returns_501_or_traces():
    """Mirror of the cpp/js tests: with a JDK (javac + java) on PATH the Java
    tracer dispatches and returns a real trace; otherwise the route returns 501
    with an instructive message."""
    import shutil

    src = (
        "public class Main {\n"
        "  public static void main(String[] a){\n"
        "    int x = 1;\n"
        "    int y = x + 1;\n"
        "    System.out.println(y);\n"
        "  }\n"
        "}\n"
    )
    r = client.post("/trace", json={"language": "java", "source": src, "stdin": ""})
    if shutil.which("javac") and shutil.which("java"):
        assert r.status_code == 200
        body = r.json()
        assert body["language"] == "java"
        assert body["exit"]["status"] in {"ok", "error"}
    else:
        assert r.status_code == 501
        assert "jdk" in r.json()["detail"].lower() or "javac" in r.json()["detail"].lower()


def test_trace_javascript_returns_501_or_traces():
    """Mirror of the cpp test: when `node` is on PATH the JS tracer
    dispatches and returns a real trace; otherwise the route returns
    501 with an instructive message. Both branches must validate."""
    import shutil

    r = client.post(
        "/trace",
        json={"language": "javascript", "source": "const x=1;\nconst y=2;\n", "stdin": ""},
    )
    if shutil.which("node"):
        assert r.status_code == 200
        body = r.json()
        assert body["language"] == "javascript"
        assert body["exit"]["status"] in {"ok", "error"}
    else:
        assert r.status_code == 501
        assert "node" in r.json()["detail"].lower()


def test_explain_returns_501_without_api_key(monkeypatch):
    monkeypatch.delenv("DSA_VIZ_AI_KEY", raising=False)
    r = client.post("/explain", json={"event": {"line": 1}, "source": "x = 1"})
    assert r.status_code == 501
    assert "stretch-goal" in r.json()["detail"].lower() or "key" in r.json()["detail"].lower()
