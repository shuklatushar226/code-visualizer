"""Deployment capability reporting stays aligned with installed toolchains."""

from fastapi.testclient import TestClient
from server.main import app

client = TestClient(app)


def test_capabilities_describe_every_ui_runtime():
    response = client.get("/capabilities")
    assert response.status_code == 200
    body = response.json()
    assert set(body["runtimes"]) == {"python", "cpp", "javascript", "java"}
    assert body["runtimes"]["python"]["available"] is True
    assert isinstance(body["ai_explain"]["available"], bool)
    assert body["isolation"] in {"process", "container"}
