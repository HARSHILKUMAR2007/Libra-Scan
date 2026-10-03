"""Tests for health check endpoint."""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    """Ensure GET /health returns 200 and expected status payload."""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
