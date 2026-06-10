from __future__ import annotations

import math
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import ParseResult, urlparse, urlunparse

import httpx

from braindashboard.core.config import Settings

VllmMetricsStatus = Literal["online", "offline"]

_METRIC_LINE_RE = re.compile(
    r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(?:\{([^}]*)\})?\s+([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?|[-+]?Inf|NaN)(?:\s+\d+)?$"
)
_LABEL_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:\\.|[^"\\])*)"')


@dataclass(frozen=True)
class PrometheusMetric:
    name: str
    labels: dict[str, str]
    value: float


@dataclass(frozen=True)
class VllmMetricsSample:
    timestamp: datetime
    status: VllmMetricsStatus
    detail: str
    model_names: list[str]
    running_requests: float | None = None
    waiting_requests: float | None = None
    kv_cache_usage_percent: float | None = None
    prompt_tokens_total: float | None = None
    prompt_compute_tokens_total: float | None = None
    prompt_cached_tokens_total: float | None = None
    generation_tokens_total: float | None = None
    request_success_total: float | None = None
    prefix_cache_hits_total: float | None = None
    prefix_cache_queries_total: float | None = None
    prefix_cache_hit_percent: float | None = None
    prompt_tokens_per_second: float | None = None
    prompt_compute_tokens_per_second: float | None = None
    prompt_cached_tokens_per_second: float | None = None
    generation_tokens_per_second: float | None = None
    requests_per_second: float | None = None
    ttft_seconds_p50: float | None = None
    ttft_seconds_p95: float | None = None
    e2e_latency_seconds_p50: float | None = None
    e2e_latency_seconds_p95: float | None = None
    queue_seconds_p50: float | None = None
    queue_seconds_p95: float | None = None
    _counters: dict[str, float] = field(default_factory=dict, repr=False, compare=False)
    _histograms: dict[str, dict[float, float]] = field(
        default_factory=dict,
        repr=False,
        compare=False,
    )


class VllmMetricsStore:
    def __init__(self, max_samples: int) -> None:
        self._samples: deque[VllmMetricsSample] = deque(maxlen=max(max_samples, 1))

    def add(self, sample: VllmMetricsSample) -> None:
        self._samples.append(sample)

    def latest_online(self) -> VllmMetricsSample | None:
        for sample in reversed(self._samples):
            if sample.status == "online":
                return sample
        return None

    def samples(self, limit: int | None = None) -> list[VllmMetricsSample]:
        values = list(self._samples)
        if limit is None:
            return values
        return values[-limit:]


class VllmMetricsCollector:
    def __init__(
        self,
        *,
        base_url: str | None,
        api_key: str | None,
        llama_swap_base_url: str,
        llama_swap_api_key: str | None,
        timeout_seconds: float,
        store: VllmMetricsStore,
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.api_key = api_key
        self.llama_swap_base_url = llama_swap_base_url.rstrip("/")
        self.llama_swap_api_key = llama_swap_api_key
        self.timeout_seconds = timeout_seconds
        self.store = store
        self._last_base_url: str | None = self.base_url

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        store: VllmMetricsStore | None = None,
    ) -> VllmMetricsCollector:
        metrics_store = store or VllmMetricsStore(settings.vllm_metrics_max_samples)
        return cls(
            base_url=settings.vllm_metrics_base_url,
            api_key=settings.vllm_metrics_api_key,
            llama_swap_base_url=settings.llama_swap_base_url,
            llama_swap_api_key=settings.llama_swap_api_key,
            timeout_seconds=settings.vllm_metrics_timeout_seconds,
            store=metrics_store,
        )

    @property
    def metrics_url(self) -> str:
        base_url = self._last_base_url or self.base_url
        if base_url:
            return f"{base_url}/metrics"
        return f"{self.llama_swap_base_url}/running"

    async def collect(self) -> VllmMetricsSample:
        timestamp = datetime.now(UTC)
        async with httpx.AsyncClient(timeout=self.timeout_seconds, trust_env=False) as client:
            try:
                base_url = await self._resolve_base_url(client)
            except VllmMetricsDiscoveryError as error:
                return self._record_offline(timestamp, error.reason)
            if base_url is None:
                return self._record_offline(timestamp, "no running vLLM backend discovered")

            headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else None
            try:
                response = await client.get(f"{base_url}/metrics", headers=headers)
                response.raise_for_status()
            except httpx.HTTPStatusError as error:
                return self._record_offline(timestamp, f"HTTP {error.response.status_code}")
            except httpx.RequestError as error:
                return self._record_offline(timestamp, error.__class__.__name__)

        self._last_base_url = base_url
        sample = build_vllm_metrics_sample(
            response.text,
            timestamp=timestamp,
            previous=self.store.latest_online(),
        )
        self.store.add(sample)
        return sample

    async def _resolve_base_url(self, client: httpx.AsyncClient) -> str | None:
        if self.base_url:
            return self.base_url

        headers = (
            {"Authorization": f"Bearer {self.llama_swap_api_key}"}
            if self.llama_swap_api_key
            else None
        )
        try:
            response = await client.get(f"{self.llama_swap_base_url}/running", headers=headers)
            response.raise_for_status()
        except httpx.HTTPStatusError as error:
            raise VllmMetricsDiscoveryError(
                f"llama-swap running API HTTP {error.response.status_code}"
            ) from error
        except httpx.RequestError as error:
            raise VllmMetricsDiscoveryError(
                f"llama-swap running API {error.__class__.__name__}"
            ) from error

        return _extract_vllm_proxy_base_url(response.json(), self.llama_swap_base_url)

    def _record_offline(self, timestamp: datetime, reason: str) -> VllmMetricsSample:
        sample = VllmMetricsSample(
            timestamp=timestamp,
            status="offline",
            detail=f"vLLM metrics unreachable: {reason}",
            model_names=[],
        )
        self.store.add(sample)
        return sample


class VllmMetricsDiscoveryError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def build_vllm_metrics_sample(
    metrics_text: str,
    *,
    timestamp: datetime,
    previous: VllmMetricsSample | None = None,
) -> VllmMetricsSample:
    metrics = parse_prometheus_metrics(metrics_text)
    counters = {
        "prompt_tokens": _sum_metric(metrics, ["vllm:prompt_tokens", "vllm:prompt_tokens_total"]),
        "prompt_compute_tokens": _prompt_compute_tokens(metrics),
        "prompt_cached_tokens": _prompt_cached_tokens(metrics),
        "generation_tokens": _sum_metric(
            metrics,
            ["vllm:generation_tokens", "vllm:generation_tokens_total"],
        ),
        "request_success": _sum_metric(
            metrics,
            ["vllm:request_success", "vllm:request_success_total"],
        ),
        "prefix_cache_hits": _sum_metric(
            metrics,
            ["vllm:prefix_cache_hits", "vllm:prefix_cache_hits_total"],
        ),
        "prefix_cache_queries": _sum_metric(
            metrics,
            ["vllm:prefix_cache_queries", "vllm:prefix_cache_queries_total"],
        ),
    }
    histograms = {
        "ttft": _histogram_buckets(metrics, "vllm:time_to_first_token_seconds"),
        "e2e": _histogram_buckets(metrics, "vllm:e2e_request_latency_seconds"),
        "queue": _histogram_buckets(metrics, "vllm:request_queue_time_seconds"),
    }
    interval_histograms = _interval_histograms(histograms, previous)
    return VllmMetricsSample(
        timestamp=timestamp,
        status="online",
        detail=f"{len(metrics)} metric series",
        model_names=_model_names(metrics),
        running_requests=_sum_metric(metrics, ["vllm:num_requests_running"]),
        waiting_requests=_sum_metric(metrics, ["vllm:num_requests_waiting"]),
        kv_cache_usage_percent=_scale_percent(_max_metric(metrics, ["vllm:kv_cache_usage_perc"])),
        prompt_tokens_total=counters["prompt_tokens"],
        prompt_compute_tokens_total=counters["prompt_compute_tokens"],
        prompt_cached_tokens_total=counters["prompt_cached_tokens"],
        generation_tokens_total=counters["generation_tokens"],
        request_success_total=counters["request_success"],
        prefix_cache_hits_total=counters["prefix_cache_hits"],
        prefix_cache_queries_total=counters["prefix_cache_queries"],
        prefix_cache_hit_percent=_counter_ratio_percent(
            numerator_name="prefix_cache_hits",
            denominator_name="prefix_cache_queries",
            counters=counters,
            previous=previous,
        ),
        prompt_tokens_per_second=_counter_rate("prompt_tokens", counters, timestamp, previous),
        prompt_compute_tokens_per_second=_counter_rate(
            "prompt_compute_tokens",
            counters,
            timestamp,
            previous,
        ),
        prompt_cached_tokens_per_second=_counter_rate(
            "prompt_cached_tokens",
            counters,
            timestamp,
            previous,
        ),
        generation_tokens_per_second=_counter_rate(
            "generation_tokens",
            counters,
            timestamp,
            previous,
        ),
        requests_per_second=_counter_rate("request_success", counters, timestamp, previous),
        ttft_seconds_p50=_histogram_quantile(0.5, interval_histograms["ttft"]),
        ttft_seconds_p95=_histogram_quantile(0.95, interval_histograms["ttft"]),
        e2e_latency_seconds_p50=_histogram_quantile(0.5, interval_histograms["e2e"]),
        e2e_latency_seconds_p95=_histogram_quantile(0.95, interval_histograms["e2e"]),
        queue_seconds_p50=_histogram_quantile(0.5, interval_histograms["queue"]),
        queue_seconds_p95=_histogram_quantile(0.95, interval_histograms["queue"]),
        _counters=counters,
        _histograms=histograms,
    )


def parse_prometheus_metrics(metrics_text: str) -> list[PrometheusMetric]:
    metrics: list[PrometheusMetric] = []
    for line in metrics_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        match = _METRIC_LINE_RE.match(stripped)
        if match is None:
            continue
        name, labels_text, value_text = match.groups()
        metrics.append(
            PrometheusMetric(
                name=name,
                labels=_parse_labels(labels_text or ""),
                value=_parse_prometheus_value(value_text),
            )
        )
    return metrics


def _parse_labels(labels_text: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    for match in _LABEL_RE.finditer(labels_text):
        labels[match.group(1)] = match.group(2).replace(r"\"", '"').replace(r"\\", "\\")
    return labels


def _parse_prometheus_value(value: str) -> float:
    if value in {"Inf", "+Inf"}:
        return math.inf
    if value == "-Inf":
        return -math.inf
    return float(value)


def _extract_vllm_proxy_base_url(payload: object, llama_swap_base_url: str) -> str | None:
    running = payload.get("running") if isinstance(payload, dict) else payload
    if not isinstance(running, list):
        return None

    for item in running:
        if not isinstance(item, dict) or not _is_vllm_running_item(item):
            continue
        proxy = item.get("proxy")
        if isinstance(proxy, str) and proxy:
            return _normalize_proxy_url(proxy, llama_swap_base_url)
        command_base_url = _base_url_from_command(item.get("cmd"), llama_swap_base_url)
        if command_base_url:
            return command_base_url
    return None


def _is_vllm_running_item(item: dict[str, object]) -> bool:
    searchable_values = [
        item.get("model"),
        item.get("name"),
        item.get("cmd"),
        item.get("proxy"),
    ]
    return any(isinstance(value, str) and "vllm" in value.lower() for value in searchable_values)


def _normalize_proxy_url(proxy: str, llama_swap_base_url: str) -> str:
    parsed_proxy = urlparse(proxy)
    parsed_llama_swap = urlparse(llama_swap_base_url)
    if parsed_proxy.hostname in {"127.0.0.1", "localhost", "0.0.0.0"} and parsed_proxy.port:
        host = parsed_llama_swap.hostname or parsed_proxy.hostname
        parsed_proxy = _replace_hostname(parsed_proxy, host)
    return urlunparse(parsed_proxy).rstrip("/")


def _base_url_from_command(command: object, llama_swap_base_url: str) -> str | None:
    if not isinstance(command, str):
        return None
    match = re.search(r"--port\s+(\d+)", command)
    if match is None:
        return None
    parsed_llama_swap = urlparse(llama_swap_base_url)
    scheme = parsed_llama_swap.scheme or "http"
    host = parsed_llama_swap.hostname or "127.0.0.1"
    return f"{scheme}://{host}:{match.group(1)}"


def _replace_hostname(parsed_url: ParseResult, hostname: str) -> ParseResult:
    port = f":{parsed_url.port}" if parsed_url.port else ""
    return parsed_url._replace(netloc=f"{hostname}{port}")


def _sum_metric(metrics: list[PrometheusMetric], names: list[str]) -> float | None:
    values = [metric.value for metric in metrics if metric.name in names]
    if not values:
        return None
    return sum(values)


def _max_metric(metrics: list[PrometheusMetric], names: list[str]) -> float | None:
    values = [metric.value for metric in metrics if metric.name in names]
    if not values:
        return None
    return max(values)


def _sum_metric_with_label(
    metrics: list[PrometheusMetric],
    names: list[str],
    label_name: str,
    label_value: str,
) -> float | None:
    values = [
        metric.value
        for metric in metrics
        if metric.name in names and metric.labels.get(label_name) == label_value
    ]
    if not values:
        return None
    return sum(values)


def _prompt_compute_tokens(metrics: list[PrometheusMetric]) -> float | None:
    by_source = _sum_metric_with_label(
        metrics,
        ["vllm:prompt_tokens_by_source", "vllm:prompt_tokens_by_source_total"],
        "source",
        "local_compute",
    )
    if by_source is not None:
        return by_source

    total = _sum_metric(metrics, ["vllm:prompt_tokens", "vllm:prompt_tokens_total"])
    cached = _prompt_cached_tokens(metrics)
    if total is None:
        return None
    if cached is None:
        return total
    return max(total - cached, 0)


def _prompt_cached_tokens(metrics: list[PrometheusMetric]) -> float | None:
    cached = _sum_metric(metrics, ["vllm:prompt_tokens_cached", "vllm:prompt_tokens_cached_total"])
    if cached is not None:
        return cached

    return _sum_metric_with_label(
        metrics,
        ["vllm:prompt_tokens_by_source", "vllm:prompt_tokens_by_source_total"],
        "source",
        "local_cache_hit",
    )


def _scale_percent(value: float | None) -> float | None:
    if value is None:
        return None
    return value * 100 if value <= 1 else value


def _model_names(metrics: list[PrometheusMetric]) -> list[str]:
    names: set[str] = set()
    for metric in metrics:
        for label_name in ("model_name", "model", "served_model_name"):
            model_name = metric.labels.get(label_name)
            if model_name:
                names.add(model_name)
    return sorted(names)


def _histogram_buckets(metrics: list[PrometheusMetric], base_name: str) -> dict[float, float]:
    bucket_name = f"{base_name}_bucket"
    buckets: dict[float, float] = {}
    for metric in metrics:
        if metric.name != bucket_name:
            continue
        le = metric.labels.get("le")
        if le is None:
            continue
        parsed_le = _parse_prometheus_value(le)
        buckets[parsed_le] = buckets.get(parsed_le, 0) + metric.value
    return buckets


def _interval_histograms(
    current: dict[str, dict[float, float]],
    previous: VllmMetricsSample | None,
) -> dict[str, dict[float, float]]:
    if previous is None:
        return current

    interval: dict[str, dict[float, float]] = {}
    for name, buckets in current.items():
        previous_buckets = previous._histograms.get(name, {})
        deltas: dict[float, float] = {}
        for le, value in buckets.items():
            previous_value = previous_buckets.get(le, 0)
            delta = value - previous_value
            if delta < 0:
                return current
            deltas[le] = delta
        interval[name] = deltas
    return interval


def _counter_rate(
    counter_name: str,
    counters: dict[str, float | None],
    timestamp: datetime,
    previous: VllmMetricsSample | None,
) -> float | None:
    current_value = counters.get(counter_name)
    if current_value is None or previous is None:
        return None
    previous_value = previous._counters.get(counter_name)
    elapsed_seconds = (timestamp - previous.timestamp).total_seconds()
    if previous_value is None or elapsed_seconds <= 0 or current_value < previous_value:
        return None
    return (current_value - previous_value) / elapsed_seconds


def _counter_ratio_percent(
    *,
    numerator_name: str,
    denominator_name: str,
    counters: dict[str, float | None],
    previous: VllmMetricsSample | None,
) -> float | None:
    numerator = counters.get(numerator_name)
    denominator = counters.get(denominator_name)
    if numerator is None or denominator is None:
        return None

    if previous is not None:
        previous_numerator = previous._counters.get(numerator_name)
        previous_denominator = previous._counters.get(denominator_name)
        if previous_numerator is not None and previous_denominator is not None:
            numerator_delta = numerator - previous_numerator
            denominator_delta = denominator - previous_denominator
            if numerator_delta >= 0 and denominator_delta > 0:
                return (numerator_delta / denominator_delta) * 100

    if denominator <= 0:
        return None
    return (numerator / denominator) * 100


def _histogram_quantile(quantile: float, buckets: dict[float, float]) -> float | None:
    finite_buckets = sorted((le, value) for le, value in buckets.items() if value >= 0)
    if not finite_buckets:
        return None

    total = finite_buckets[-1][1]
    if total <= 0:
        return None

    target = total * quantile
    previous_le = 0.0
    previous_count = 0.0
    for le, count in finite_buckets:
        if count >= target:
            if math.isinf(le):
                return previous_le
            bucket_count = count - previous_count
            if bucket_count <= 0:
                return le
            fraction = (target - previous_count) / bucket_count
            return previous_le + (le - previous_le) * fraction
        previous_le = 0.0 if math.isinf(le) else le
        previous_count = count
    return None
