from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict

from braindashboard.collectors.docker import DockerCollector
from braindashboard.collectors.llama_swap import LlamaSwapCollector, LlamaSwapRequestError
from braindashboard.collectors.service_status import ServiceHealth
from braindashboard.collectors.vllm_metrics import (
    VllmMetricsCollector,
    VllmMetricsSample,
    VllmMetricsStatus,
    VllmMetricsStore,
)
from braindashboard.core.config import get_settings

router = APIRouter(prefix="/services", tags=["services"])

settings = get_settings()
llama_swap_collector = LlamaSwapCollector.from_settings(settings)
docker_collector = DockerCollector()
vllm_metrics_store = VllmMetricsStore(settings.vllm_metrics_max_samples)
vllm_metrics_collector = VllmMetricsCollector.from_settings(settings, store=vllm_metrics_store)


class ServiceStatusResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    status: ServiceHealth
    detail: str
    checked_at: datetime
    parent_name: str | None
    is_active: bool | None
    latency_ms: float | None
    version: str | None
    model_count: int | None
    active_model: str | None
    running_models: list[str] | None
    recent_request_count: int | None
    recent_error_count: int | None
    recent_average_duration_ms: float | None


class ServiceSnapshotResponse(BaseModel):
    checked_at: datetime
    services: list[ServiceStatusResponse]


class LlamaSwapUnloadResponse(BaseModel):
    status: str
    detail: str


class VllmMetricsSampleResponse(BaseModel):
    timestamp: datetime
    status: VllmMetricsStatus
    detail: str
    model_names: list[str]
    running_requests: float | None
    waiting_requests: float | None
    kv_cache_usage_percent: float | None
    prompt_tokens_total: float | None
    prompt_compute_tokens_total: float | None
    prompt_cached_tokens_total: float | None
    generation_tokens_total: float | None
    request_success_total: float | None
    prefix_cache_hits_total: float | None
    prefix_cache_queries_total: float | None
    prefix_cache_hit_percent: float | None
    prompt_tokens_per_second: float | None
    prompt_compute_tokens_per_second: float | None
    prompt_cached_tokens_per_second: float | None
    generation_tokens_per_second: float | None
    requests_per_second: float | None
    ttft_seconds_p50: float | None
    ttft_seconds_p95: float | None
    e2e_latency_seconds_p50: float | None
    e2e_latency_seconds_p95: float | None
    queue_seconds_p50: float | None
    queue_seconds_p95: float | None


class VllmMetricsHistoryResponse(BaseModel):
    checked_at: datetime
    endpoint: str
    latest: VllmMetricsSampleResponse | None
    samples: list[VllmMetricsSampleResponse]


@router.get("/snapshot")
async def services_snapshot() -> ServiceSnapshotResponse:
    snapshot, docker_status = await asyncio.gather(
        llama_swap_collector.collect(),
        asyncio.to_thread(docker_collector.collect),
    )
    return ServiceSnapshotResponse(
        checked_at=snapshot.checked_at,
        services=[
            ServiceStatusResponse.model_validate(service)
            for service in [*snapshot.services, docker_status]
        ],
    )


@router.post("/llama-swap/unload")
async def unload_llama_swap_models() -> LlamaSwapUnloadResponse:
    try:
        await llama_swap_collector.unload_models()
    except LlamaSwapRequestError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"llama-swap unload failed: {error.reason}",
        ) from error

    return LlamaSwapUnloadResponse(
        status="unloaded",
        detail="llama-swap /api/models/unload accepted",
    )


@router.get("/vllm/metrics")
async def vllm_metrics_history(
    refresh: bool = True,
    limit: int = Query(default=240, ge=1, le=5000),
) -> VllmMetricsHistoryResponse:
    latest = await vllm_metrics_collector.collect() if refresh else _latest_sample()
    samples = vllm_metrics_store.samples(limit=limit)
    return VllmMetricsHistoryResponse(
        checked_at=datetime.now(UTC),
        endpoint=vllm_metrics_collector.metrics_url,
        latest=_vllm_sample_response(latest) if latest is not None else None,
        samples=[_vllm_sample_response(sample) for sample in samples],
    )


def _latest_sample() -> VllmMetricsSample | None:
    samples = vllm_metrics_store.samples(limit=1)
    return samples[0] if samples else None


def _vllm_sample_response(sample: VllmMetricsSample) -> VllmMetricsSampleResponse:
    return VllmMetricsSampleResponse(
        timestamp=sample.timestamp,
        status=sample.status,
        detail=sample.detail,
        model_names=sample.model_names,
        running_requests=sample.running_requests,
        waiting_requests=sample.waiting_requests,
        kv_cache_usage_percent=sample.kv_cache_usage_percent,
        prompt_tokens_total=sample.prompt_tokens_total,
        prompt_compute_tokens_total=sample.prompt_compute_tokens_total,
        prompt_cached_tokens_total=sample.prompt_cached_tokens_total,
        generation_tokens_total=sample.generation_tokens_total,
        request_success_total=sample.request_success_total,
        prefix_cache_hits_total=sample.prefix_cache_hits_total,
        prefix_cache_queries_total=sample.prefix_cache_queries_total,
        prefix_cache_hit_percent=sample.prefix_cache_hit_percent,
        prompt_tokens_per_second=sample.prompt_tokens_per_second,
        prompt_compute_tokens_per_second=sample.prompt_compute_tokens_per_second,
        prompt_cached_tokens_per_second=sample.prompt_cached_tokens_per_second,
        generation_tokens_per_second=sample.generation_tokens_per_second,
        requests_per_second=sample.requests_per_second,
        ttft_seconds_p50=sample.ttft_seconds_p50,
        ttft_seconds_p95=sample.ttft_seconds_p95,
        e2e_latency_seconds_p50=sample.e2e_latency_seconds_p50,
        e2e_latency_seconds_p95=sample.e2e_latency_seconds_p95,
        queue_seconds_p50=sample.queue_seconds_p50,
        queue_seconds_p95=sample.queue_seconds_p95,
    )
