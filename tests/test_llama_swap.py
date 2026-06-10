from __future__ import annotations

from datetime import UTC, datetime, timedelta

from braindashboard.collectors.llama_swap import (
    LlamaSwapCollector,
    MetricSample,
    _build_llama_swap_backend_statuses,
    _extract_running_models,
)


def test_vllm_status_does_not_mark_historical_metrics_active() -> None:
    checked_at = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)

    statuses = _build_llama_swap_backend_statuses(
        checked_at=checked_at,
        model_ids=["vllm-gemma-31", "vllm-granite4-1b"],
        running_models=[],
        metrics=[
            MetricSample(
                timestamp=checked_at - timedelta(hours=1),
                model="vllm-gemma-31",
                status_code=200,
                duration_ms=5000.0,
            )
        ],
        metrics_window=timedelta(minutes=5),
    )
    status = statuses[0]

    assert status.status == "degraded"
    assert status.parent_name == "llama-swap"
    assert status.is_active is False
    assert status.active_model is None
    assert status.recent_request_count == 0
    assert status.detail == "2 configured · not loaded"


def test_vllm_status_reports_recent_traffic_without_calling_it_active() -> None:
    checked_at = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)

    statuses = _build_llama_swap_backend_statuses(
        checked_at=checked_at,
        model_ids=["vllm-gemma-31"],
        running_models=[],
        metrics=[
            MetricSample(
                timestamp=checked_at - timedelta(seconds=30),
                model="vllm-gemma-31",
                status_code=200,
                duration_ms=2500.0,
            )
        ],
        metrics_window=timedelta(minutes=5),
    )
    status = statuses[0]

    assert status.status == "degraded"
    assert status.is_active is False
    assert status.active_model is None
    assert status.recent_request_count == 1
    assert status.detail == "1 configured · recent traffic on vllm-gemma-31"


def test_vllm_status_uses_running_endpoint_for_loaded_model() -> None:
    checked_at = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)

    statuses = _build_llama_swap_backend_statuses(
        checked_at=checked_at,
        model_ids=["vllm-gemma-31", "qwen-3.6-27b-q8-24k"],
        running_models=["vllm-gemma-31", "qwen-3.6-27b-q8-24k"],
        metrics=[],
        metrics_window=timedelta(minutes=5),
    )

    vllm_status = statuses[0]
    llamacpp_status = statuses[1]
    assert vllm_status.status == "healthy"
    assert vllm_status.is_active is True
    assert vllm_status.active_model == "vllm-gemma-31"
    assert vllm_status.running_models == ["vllm-gemma-31"]
    assert llamacpp_status.status == "healthy"
    assert llamacpp_status.is_active is True
    assert llamacpp_status.active_model == "qwen-3.6-27b-q8-24k"


def test_extract_running_models_accepts_common_shapes() -> None:
    assert _extract_running_models({"running": []}) == []
    assert _extract_running_models({"running": ["vllm-gemma-31"]}) == ["vllm-gemma-31"]
    assert _extract_running_models({"running": [{"model": "qwen"}, {"id": "vllm-a"}]}) == [
        "qwen",
        "vllm-a",
    ]


async def test_unload_models_posts_to_llama_swap_unload_endpoint(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls: list[tuple[str, dict[str, str]]] = []
    collector = LlamaSwapCollector(
        base_url="http://llama-swap.local",
        api_key="secret",
        timeout_seconds=3.0,
        metrics_window_seconds=300,
    )

    async def post(_client, path: str, headers: dict[str, str]) -> None:  # type: ignore[no-untyped-def]
        calls.append((path, headers))

    monkeypatch.setattr(collector, "_post", post)

    await collector.unload_models()

    assert calls == [
        (
            "/api/models/unload",
            {"Authorization": "Bearer secret"},
        )
    ]
