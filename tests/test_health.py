"""Tests for the health check endpoint."""

from fastapi.testclient import TestClient


def test_health_check(client: TestClient) -> None:
    """Test that the health check endpoint returns healthy status."""
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    assert data["status"] == "healthy"
    assert "auth_mode" in data


def test_health_check_shows_auth_mode(client: TestClient) -> None:
    """Test that the health check endpoint shows the correct auth mode."""
    response = client.get("/health")
    assert response.status_code == 200

    data = response.json()
    # Default auth mode is "local"
    assert data["auth_mode"] == "local"
