from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from braindashboard.collectors.vllm_metrics import (
    _extract_vllm_proxy_base_url,
    build_vllm_metrics_sample,
)


def test_build_vllm_metrics_sample_parses_core_metrics() -> None:
    timestamp = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
    metrics_text = """
# HELP vllm:num_requests_running Number of requests in model execution batches.
vllm:num_requests_running{model_name="model-a"} 2
vllm:num_requests_waiting{model_name="model-a"} 1
vllm:kv_cache_usage_perc{model_name="model-a"} 0.42
vllm:prompt_tokens_total{model_name="model-a"} 100
vllm:prompt_tokens_by_source_total{model_name="model-a",source="local_compute"} 35
vllm:prompt_tokens_by_source_total{model_name="model-a",source="local_cache_hit"} 65
vllm:prompt_tokens_cached_total{model_name="model-a"} 65
vllm:generation_tokens_total{model_name="model-a"} 40
vllm:request_success_total{model_name="model-a"} 5
vllm:prefix_cache_hits_total{model_name="model-a"} 20
vllm:prefix_cache_queries_total{model_name="model-a"} 80
vllm:time_to_first_token_seconds_bucket{model_name="model-a",le="0.1"} 2
vllm:time_to_first_token_seconds_bucket{model_name="model-a",le="0.5"} 4
vllm:time_to_first_token_seconds_bucket{model_name="model-a",le="+Inf"} 5
vllm:e2e_request_latency_seconds_bucket{model_name="model-a",le="1"} 1
vllm:e2e_request_latency_seconds_bucket{model_name="model-a",le="5"} 5
vllm:e2e_request_latency_seconds_bucket{model_name="model-a",le="+Inf"} 5
"""

    sample = build_vllm_metrics_sample(metrics_text, timestamp=timestamp)

    assert sample.status == "online"
    assert sample.model_names == ["model-a"]
    assert sample.running_requests == 2
    assert sample.waiting_requests == 1
    assert sample.kv_cache_usage_percent == 42
    assert sample.prompt_tokens_total == 100
    assert sample.prompt_compute_tokens_total == 35
    assert sample.prompt_cached_tokens_total == 65
    assert sample.generation_tokens_total == 40
    assert sample.request_success_total == 5
    assert sample.prefix_cache_hits_total == 20
    assert sample.prefix_cache_queries_total == 80
    assert sample.prefix_cache_hit_percent == 25
    assert sample.ttft_seconds_p50 == 0.2
    assert sample.e2e_latency_seconds_p95 == 4.75


def test_build_vllm_metrics_sample_calculates_interval_rates() -> None:
    first_timestamp = datetime(2026, 6, 10, 12, 0, tzinfo=UTC)
    first = build_vllm_metrics_sample(
        """
vllm:prompt_tokens_total 100
vllm:prompt_tokens_by_source_total{source="local_compute"} 30
vllm:prompt_tokens_cached_total 70
vllm:generation_tokens_total 40
vllm:request_success_total 5
vllm:prefix_cache_hits_total 20
vllm:prefix_cache_queries_total 80
vllm:request_queue_time_seconds_bucket{le="0.1"} 1
vllm:request_queue_time_seconds_bucket{le="0.5"} 2
vllm:request_queue_time_seconds_bucket{le="+Inf"} 2
""",
        timestamp=first_timestamp,
    )

    second = build_vllm_metrics_sample(
        """
vllm:prompt_tokens_total 160
vllm:prompt_tokens_by_source_total{source="local_compute"} 80
vllm:prompt_tokens_cached_total 80
vllm:generation_tokens_total 100
vllm:request_success_total 11
vllm:prefix_cache_hits_total 50
vllm:prefix_cache_queries_total 120
vllm:request_queue_time_seconds_bucket{le="0.1"} 1
vllm:request_queue_time_seconds_bucket{le="0.5"} 5
vllm:request_queue_time_seconds_bucket{le="+Inf"} 6
""",
        timestamp=first_timestamp + timedelta(seconds=30),
        previous=first,
    )

    assert second.prompt_tokens_per_second == 2
    assert second.prompt_compute_tokens_per_second == pytest.approx(1.6667, abs=0.0001)
    assert second.prompt_cached_tokens_per_second == pytest.approx(0.3333, abs=0.0001)
    assert second.generation_tokens_per_second == 2
    assert second.requests_per_second == 0.2
    assert second.prefix_cache_hit_percent == 75
    assert second.queue_seconds_p50 == pytest.approx(0.3667, abs=0.0001)


def test_extract_vllm_proxy_base_url_rewrites_localhost_proxy() -> None:
    payload = {
        "running": [
            {
                "cmd": "/opt/vllm/venv/bin/vllm serve model --port 18012",
                "model": "vllm-gemma-31",
                "proxy": "http://127.0.0.1:18012",
                "state": "ready",
            }
        ]
    }

    base_url = _extract_vllm_proxy_base_url(payload, "http://brainsrv:9292")

    assert base_url == "http://brainsrv:18012"
