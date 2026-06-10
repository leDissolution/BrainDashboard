from __future__ import annotations

from datetime import UTC, datetime

from fastapi.testclient import TestClient

from braindashboard.api.routes import services
from braindashboard.collectors.service_status import ServiceSnapshot, ServiceStatus
from braindashboard.collectors.vllm_metrics import VllmMetricsSample
from braindashboard.core.config import Settings
from braindashboard.main import create_app


def test_services_snapshot_endpoint(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    timestamp = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)

    async def collect() -> ServiceSnapshot:
        return ServiceSnapshot(
            checked_at=timestamp,
            services=[
                ServiceStatus(
                    name="llama-swap",
                    status="healthy",
                    detail="version 211 · 14 models",
                    checked_at=timestamp,
                    latency_ms=12.4,
                    version="211",
                    model_count=14,
                ),
                ServiceStatus(
                    name="vLLM",
                    status="degraded",
                    detail="3 configured · not loaded",
                    checked_at=timestamp,
                    parent_name="llama-swap",
                    is_active=False,
                    model_count=3,
                    active_model=None,
                    running_models=[],
                    recent_request_count=8,
                    recent_error_count=0,
                    recent_average_duration_ms=5400.0,
                ),
            ],
        )

    monkeypatch.setattr(services.llama_swap_collector, "collect", collect)
    monkeypatch.setattr(
        services.docker_collector,
        "collect",
        lambda: ServiceStatus(
            name="Docker",
            status="healthy",
            detail="3 running",
            checked_at=timestamp,
            latency_ms=18.0,
            version="28.1.1",
        ),
    )

    client = TestClient(
        create_app(Settings(scheduler_enabled=False, hardware_monitor_enabled=False))
    )

    response = client.get("/api/services/snapshot")

    assert response.status_code == 200
    body = response.json()
    assert body["services"][0]["name"] == "llama-swap"
    assert body["services"][0]["latency_ms"] == 12.4
    assert body["services"][1]["active_model"] is None
    assert body["services"][1]["parent_name"] == "llama-swap"
    assert body["services"][1]["is_active"] is False
    assert body["services"][1]["recent_request_count"] == 8
    assert body["services"][2]["name"] == "Docker"
    assert body["services"][2]["version"] == "28.1.1"


def test_llama_swap_unload_endpoint(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    called = False

    async def unload_models() -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(services.llama_swap_collector, "unload_models", unload_models)

    client = TestClient(
        create_app(Settings(scheduler_enabled=False, hardware_monitor_enabled=False))
    )

    response = client.post("/api/services/llama-swap/unload")

    assert response.status_code == 200
    assert response.json() == {
        "status": "unloaded",
        "detail": "llama-swap /api/models/unload accepted",
    }
    assert called is True


def test_vllm_metrics_endpoint_records_in_memory_samples(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    timestamp = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
    sample = VllmMetricsSample(
        timestamp=timestamp,
        status="online",
        detail="9 metric series",
        model_names=["model-a"],
        running_requests=1,
        waiting_requests=2,
        kv_cache_usage_percent=45.0,
        generation_tokens_per_second=12.0,
    )

    async def collect() -> VllmMetricsSample:
        services.vllm_metrics_store.add(sample)
        return sample

    monkeypatch.setattr(services.vllm_metrics_collector, "collect", collect)
    monkeypatch.setattr(services.vllm_metrics_collector, "base_url", "http://vllm.test")
    monkeypatch.setattr(services.vllm_metrics_collector, "_last_base_url", "http://vllm.test")

    client = TestClient(
        create_app(Settings(scheduler_enabled=False, hardware_monitor_enabled=False))
    )

    response = client.get("/api/services/vllm/metrics")

    assert response.status_code == 200
    body = response.json()
    assert body["endpoint"] == "http://vllm.test/metrics"
    assert body["latest"]["model_names"] == ["model-a"]
    assert body["latest"]["kv_cache_usage_percent"] == 45.0
    assert body["samples"][-1]["generation_tokens_per_second"] == 12.0
