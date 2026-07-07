"""Дымовые тесты: приложение поднимается, OpenAPI генерируется, health отвечает.

БД не требуется — /health и построение схемы не ходят в базу.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_openapi_available() -> None:
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    schema = resp.json()
    assert schema["info"]["title"] == "Vendors API"
    # ключевые маршруты присутствуют
    assert "/listings" in schema["paths"]
    assert "/projects/{project_id}/summary" in schema["paths"]
