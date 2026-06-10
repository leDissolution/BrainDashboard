from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

ServiceHealth = Literal["healthy", "degraded", "offline"]


@dataclass(frozen=True)
class ServiceStatus:
    name: str
    status: ServiceHealth
    detail: str
    checked_at: datetime
    parent_name: str | None = None
    is_active: bool | None = None
    latency_ms: float | None = None
    version: str | None = None
    model_count: int | None = None
    active_model: str | None = None
    running_models: list[str] | None = None
    recent_request_count: int | None = None
    recent_error_count: int | None = None
    recent_average_duration_ms: float | None = None


@dataclass(frozen=True)
class ServiceSnapshot:
    checked_at: datetime
    services: list[ServiceStatus]