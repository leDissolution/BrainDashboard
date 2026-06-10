from __future__ import annotations

from enum import StrEnum


class JobExecutionMode(StrEnum):
    NATIVE = "native"
    DOCKER = "docker"
    API = "api"


class JobRunState(StrEnum):
    QUEUED = "queued"
    BLOCKED_BY_POLICY = "blocked_by_policy"
    BLOCKED_BY_RESOURCES = "blocked_by_resources"
    HELD = "held"
    ADMITTED = "admitted"
    STARTING = "starting"
    RUNNING = "running"
    CANCEL_REQUESTED = "cancel_requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELED = "canceled"
    TIMED_OUT = "timed_out"
    LOST = "lost"
    NEEDS_REVIEW = "needs_review"


class ServiceStatus(StrEnum):
    UNKNOWN = "unknown"
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
