from __future__ import annotations

from fastapi.testclient import TestClient

from braindashboard.core.config import Settings
from braindashboard.main import create_app


def test_health_endpoint() -> None:
    client = TestClient(
        create_app(Settings(scheduler_enabled=False, hardware_monitor_enabled=False))
    )

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "braindashboard"}
