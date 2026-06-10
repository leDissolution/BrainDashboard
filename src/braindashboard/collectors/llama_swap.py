from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import perf_counter
from typing import Any

import httpx

from braindashboard.collectors.service_status import ServiceHealth, ServiceSnapshot, ServiceStatus
from braindashboard.core.config import Settings


@dataclass(frozen=True)
class MetricSample:
    timestamp: datetime | None
    model: str
    status_code: int | None
    duration_ms: float | None


class LlamaSwapCollector:
    def __init__(
        self,
        base_url: str,
        api_key: str | None,
        timeout_seconds: float,
        metrics_window_seconds: int,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.metrics_window = timedelta(seconds=metrics_window_seconds)

    @classmethod
    def from_settings(cls, settings: Settings) -> LlamaSwapCollector:
        return cls(
            base_url=settings.llama_swap_base_url,
            api_key=settings.llama_swap_api_key,
            timeout_seconds=settings.llama_swap_timeout_seconds,
            metrics_window_seconds=settings.llama_swap_metrics_window_seconds,
        )

    async def collect(self) -> ServiceSnapshot:
        checked_at = datetime.now(UTC)

        async with httpx.AsyncClient(timeout=self.timeout_seconds, trust_env=False) as client:
            try:
                _, health_latency_ms = await self._get_text(client, "/health", headers=None)
            except LlamaSwapRequestError as error:
                return ServiceSnapshot(
                    checked_at=checked_at,
                    services=[
                        ServiceStatus(
                            name="llama-swap",
                            status="offline",
                            detail=f"unreachable: {error.reason}",
                            checked_at=checked_at,
                        ),
                        ServiceStatus(
                            name="vLLM",
                            status="offline",
                            detail="llama-swap unreachable",
                            checked_at=checked_at,
                            parent_name="llama-swap",
                            is_active=False,
                            running_models=[],
                        ),
                        ServiceStatus(
                            name="llama.cpp",
                            status="offline",
                            detail="llama-swap unreachable",
                            checked_at=checked_at,
                            parent_name="llama-swap",
                            is_active=False,
                            running_models=[],
                        ),
                    ],
                )

            if not self.api_key:
                return ServiceSnapshot(
                    checked_at=checked_at,
                    services=[
                        ServiceStatus(
                            name="llama-swap",
                            status="degraded",
                            detail="health OK, API key missing",
                            checked_at=checked_at,
                            latency_ms=health_latency_ms,
                        ),
                        ServiceStatus(
                            name="vLLM",
                            status="degraded",
                            detail="waiting for llama-swap API key",
                            checked_at=checked_at,
                            parent_name="llama-swap",
                            is_active=False,
                            running_models=[],
                        ),
                        ServiceStatus(
                            name="llama.cpp",
                            status="degraded",
                            detail="waiting for llama-swap API key",
                            checked_at=checked_at,
                            parent_name="llama-swap",
                            is_active=False,
                            running_models=[],
                        ),
                    ],
                )

            headers = {"Authorization": f"Bearer {self.api_key}"}
            version: str | None = None
            model_ids: list[str] = []
            running_models: list[str] = []
            metrics: list[MetricSample] = []
            errors: list[str] = []

            try:
                version_payload, _ = await self._get_json(client, "/api/version", headers=headers)
                version = _read_string(version_payload, "version")
            except LlamaSwapRequestError as error:
                errors.append(f"version {error.reason}")

            try:
                models_payload, _ = await self._get_json(client, "/v1/models", headers=headers)
                model_ids = _extract_model_ids(models_payload)
            except LlamaSwapRequestError as error:
                errors.append(f"models {error.reason}")

            try:
                running_payload, _ = await self._get_json(client, "/running", headers=headers)
                running_models = _extract_running_models(running_payload)
            except LlamaSwapRequestError as error:
                errors.append(f"running {error.reason}")

            try:
                metrics_payload, _ = await self._get_json(client, "/api/metrics", headers=headers)
                metrics = _extract_metrics(metrics_payload)
            except LlamaSwapRequestError as error:
                errors.append(f"metrics {error.reason}")

            return ServiceSnapshot(
                checked_at=checked_at,
                services=[
                    _build_llama_swap_status(
                        checked_at=checked_at,
                        health_latency_ms=health_latency_ms,
                        version=version,
                        model_count=len(model_ids),
                        running_model_count=len(running_models),
                        errors=errors,
                    ),
                    *_build_llama_swap_backend_statuses(
                        checked_at=checked_at,
                        model_ids=model_ids,
                        running_models=running_models,
                        metrics=metrics,
                        metrics_window=self.metrics_window,
                    ),
                ],
            )

    async def _get_text(
        self,
        client: httpx.AsyncClient,
        path: str,
        headers: dict[str, str] | None,
    ) -> tuple[str, float]:
        response, latency_ms = await self._get(client, path, headers)
        return response.text, latency_ms

    async def _get_json(
        self,
        client: httpx.AsyncClient,
        path: str,
        headers: dict[str, str],
    ) -> tuple[object, float]:
        response, latency_ms = await self._get(client, path, headers)
        return response.json(), latency_ms

    async def unload_models(self) -> None:
        if not self.api_key:
            raise LlamaSwapRequestError("API key missing")

        headers = {"Authorization": f"Bearer {self.api_key}"}
        async with httpx.AsyncClient(timeout=self.timeout_seconds, trust_env=False) as client:
            await self._post(client, "/api/models/unload", headers=headers)

    async def _get(
        self,
        client: httpx.AsyncClient,
        path: str,
        headers: dict[str, str] | None,
    ) -> tuple[httpx.Response, float]:
        start = perf_counter()
        try:
            response = await client.get(f"{self.base_url}{path}", headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise LlamaSwapRequestError(f"HTTP {error.response.status_code}") from error
        except httpx.RequestError as error:
            raise LlamaSwapRequestError(error.__class__.__name__) from error

        return response, (perf_counter() - start) * 1000

    async def _post(
        self,
        client: httpx.AsyncClient,
        path: str,
        headers: dict[str, str],
    ) -> tuple[httpx.Response, float]:
        start = perf_counter()
        try:
            response = await client.post(f"{self.base_url}{path}", headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise LlamaSwapRequestError(f"HTTP {error.response.status_code}") from error
        except httpx.RequestError as error:
            raise LlamaSwapRequestError(error.__class__.__name__) from error

        return response, (perf_counter() - start) * 1000


class LlamaSwapRequestError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _build_llama_swap_status(
    checked_at: datetime,
    health_latency_ms: float,
    version: str | None,
    model_count: int,
    running_model_count: int,
    errors: list[str],
) -> ServiceStatus:
    if errors and not model_count:
        return ServiceStatus(
            name="llama-swap",
            status="degraded",
            detail="health OK, rich API unavailable",
            checked_at=checked_at,
            latency_ms=health_latency_ms,
            version=version,
            model_count=model_count,
        )

    detail_parts = [f"{model_count} models", f"{running_model_count} running"]
    if version:
        detail_parts.insert(0, f"version {version}")
    if errors:
        detail_parts.append("partial telemetry")

    return ServiceStatus(
        name="llama-swap",
        status="degraded" if errors else "healthy",
        detail=" · ".join(detail_parts),
        checked_at=checked_at,
        latency_ms=health_latency_ms,
        version=version,
        model_count=model_count,
        is_active=running_model_count > 0,
    )


def _build_llama_swap_backend_statuses(
    checked_at: datetime,
    model_ids: list[str],
    running_models: list[str],
    metrics: list[MetricSample],
    metrics_window: timedelta,
) -> list[ServiceStatus]:
    return [
        _build_backend_status(
            name="vLLM",
            checked_at=checked_at,
            configured_models=[model_id for model_id in model_ids if _is_vllm_model(model_id)],
            running_models=[model_id for model_id in running_models if _is_vllm_model(model_id)],
            metrics=[metric for metric in metrics if _is_vllm_model(metric.model)],
            metrics_window=metrics_window,
        ),
        _build_backend_status(
            name="llama.cpp",
            checked_at=checked_at,
            configured_models=[model_id for model_id in model_ids if not _is_vllm_model(model_id)],
            running_models=[
                model_id for model_id in running_models if not _is_vllm_model(model_id)
            ],
            metrics=[metric for metric in metrics if not _is_vllm_model(metric.model)],
            metrics_window=metrics_window,
        ),
    ]


def _build_backend_status(
    name: str,
    checked_at: datetime,
    configured_models: list[str],
    running_models: list[str],
    metrics: list[MetricSample],
    metrics_window: timedelta,
) -> ServiceStatus:
    recent_cutoff = checked_at - metrics_window
    recent_metrics = [
        metric
        for metric in metrics
        if metric.timestamp is None or metric.timestamp >= recent_cutoff
    ]
    selected_metrics = recent_metrics
    error_count = sum(
        1
        for metric in selected_metrics
        if metric.status_code is not None and metric.status_code >= 500
    )
    durations = [
        metric.duration_ms for metric in selected_metrics if metric.duration_ms is not None
    ]
    average_duration_ms = sum(durations) / len(durations) if durations else None
    last_recent_model = selected_metrics[-1].model if selected_metrics else None
    running_model = running_models[0] if running_models else None

    if not configured_models and not running_models:
        return ServiceStatus(
            name=name,
            status="offline",
            detail="no models exposed by llama-swap",
            checked_at=checked_at,
            model_count=0,
            parent_name="llama-swap",
            is_active=False,
            running_models=[],
            recent_request_count=len(selected_metrics),
            recent_error_count=error_count,
            recent_average_duration_ms=average_duration_ms,
        )

    detail_parts = [f"{len(configured_models)} configured"]
    if running_models:
        detail_parts.append(_format_running_models(running_models))
    elif last_recent_model:
        detail_parts.append(f"recent traffic on {last_recent_model}")
    else:
        detail_parts.append("not loaded")
    if error_count:
        detail_parts.append(f"{error_count} recent errors")

    status: ServiceHealth = "healthy" if running_models and not error_count else "degraded"

    return ServiceStatus(
        name=name,
        status=status,
        detail=" · ".join(detail_parts),
        checked_at=checked_at,
        parent_name="llama-swap",
        is_active=bool(running_models),
        model_count=len(configured_models),
        active_model=running_model,
        running_models=running_models,
        recent_request_count=len(selected_metrics),
        recent_error_count=error_count,
        recent_average_duration_ms=average_duration_ms,
    )


def _extract_model_ids(payload: object) -> list[str]:
    if not isinstance(payload, dict):
        return []

    data = payload.get("data")
    if not isinstance(data, list):
        return []

    model_ids: list[str] = []
    for item in data:
        if isinstance(item, dict):
            model_id = item.get("id")
            if isinstance(model_id, str):
                model_ids.append(model_id)

    return model_ids


def _extract_running_models(payload: object) -> list[str]:
    if isinstance(payload, dict):
        value = payload.get("running")
    else:
        value = payload

    if not isinstance(value, list):
        return []

    model_ids: list[str] = []
    for item in value:
        model_id = _read_model_name(item)
        if model_id:
            model_ids.append(model_id)

    return model_ids


def _extract_metrics(payload: object) -> list[MetricSample]:
    if not isinstance(payload, list):
        return []

    metrics: list[MetricSample] = []
    for item in payload:
        if not isinstance(item, dict):
            continue

        model = item.get("model")
        if not isinstance(model, str):
            continue

        metrics.append(
            MetricSample(
                timestamp=_parse_timestamp(item.get("timestamp")),
                model=model,
                status_code=_read_int(item, "resp_status_code"),
                duration_ms=_read_float(item, "duration_ms"),
            )
        )

    return metrics


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None

    normalized = value.removesuffix("Z")
    if "." in normalized:
        prefix, suffix = normalized.split(".", 1)
        normalized = f"{prefix}.{suffix[:6]}"

    try:
        return datetime.fromisoformat(normalized).replace(tzinfo=UTC)
    except ValueError:
        return None


def _read_string(payload: object, key: str) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    return value if isinstance(value, str) else None


def _read_model_name(value: object) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("id", "model", "name"):
            model_id = value.get(key)
            if isinstance(model_id, str):
                return model_id
    return None


def _is_vllm_model(model_id: str) -> bool:
    return "vllm" in model_id.lower()


def _format_running_models(running_models: list[str]) -> str:
    if len(running_models) == 1:
        return f"loaded {running_models[0]}"
    return f"{len(running_models)} loaded"


def _read_int(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    return value if isinstance(value, int) else None


def _read_float(payload: dict[str, Any], key: str) -> float | None:
    value = payload.get(key)
    return float(value) if isinstance(value, int | float) else None
