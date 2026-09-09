"""La API arranca y responde el estado."""

from __future__ import annotations


def test_health_ok(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["mock_mode"] is True
    assert body["shadow_mode"] is False
    assert "chat" in body["models"]


def test_root_points_to_docs(client):
    body = client.get("/").json()
    assert body["docs"] == "/docs"


def test_openapi_describes_both_processes(client):
    schema = client.get("/openapi.json").json()
    assert "/api/v1/transactions/evaluate" in schema["paths"]
    assert "/api/v1/documents/validate" in schema["paths"]
    assert "/api/v1/feedback" in schema["paths"]
