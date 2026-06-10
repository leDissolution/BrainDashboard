from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from braindashboard.collectors.service_status import ServiceHealth, ServiceStatus


class DockerCollector:
    def __init__(self, timeout_seconds: float = 2.0) -> None:
        self.timeout_seconds = timeout_seconds

    def collect(self) -> ServiceStatus:
        checked_at = datetime.now(UTC)
        start = perf_counter()

        try:
            version = self._docker_text("version", "--format", "{{.Server.Version}}")
            containers = self._docker_json_lines("ps", "--all", "--format", "{{json .}}")
        except DockerCommandError as error:
            return ServiceStatus(
                name="Docker",
                status="offline",
                detail=error.reason,
                checked_at=checked_at,
            )

        latency_ms = round((perf_counter() - start) * 1000, 2)
        running_count = _count_containers(containers, "running")
        stopped_count = len(containers) - running_count
        unhealthy_count = sum(1 for container in containers if _is_unhealthy(container))
        restarting_count = _count_containers(containers, "restarting")
        problem_count = unhealthy_count + restarting_count

        status: ServiceHealth = "degraded" if problem_count else "healthy"
        detail_parts = [f"{running_count} running"]
        if stopped_count:
            detail_parts.append(f"{stopped_count} stopped")
        if restarting_count:
            detail_parts.append(f"{restarting_count} restarting")
        if unhealthy_count:
            detail_parts.append(f"{unhealthy_count} unhealthy")

        return ServiceStatus(
            name="Docker",
            status=status,
            detail=" · ".join(detail_parts),
            checked_at=checked_at,
            latency_ms=latency_ms,
            version=version or None,
        )

    def _docker_text(self, *arguments: str) -> str:
        return self._run(*arguments).strip()

    def _docker_json_lines(self, *arguments: str) -> list[dict[str, Any]]:
        output = self._run(*arguments)
        containers: list[dict[str, Any]] = []
        for line in output.splitlines():
            if not line.strip():
                continue
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                containers.append(parsed)
        return containers

    def _run(self, *arguments: str) -> str:
        try:
            completed = subprocess.run(
                ["docker", *arguments],
                check=False,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as error:
            raise DockerCommandError("docker CLI missing") from error
        except subprocess.TimeoutExpired as error:
            raise DockerCommandError("docker command timed out") from error

        if completed.returncode != 0:
            reason = completed.stderr.strip() or completed.stdout.strip() or "docker command failed"
            raise DockerCommandError(reason)

        return completed.stdout


class DockerCommandError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def _count_containers(containers: list[dict[str, Any]], state: str) -> int:
    return sum(1 for container in containers if _read_state(container) == state)


def _is_unhealthy(container: dict[str, Any]) -> bool:
    status = container.get("Status")
    return isinstance(status, str) and "unhealthy" in status.lower()


def _read_state(container: dict[str, Any]) -> str:
    state = container.get("State")
    return state.lower() if isinstance(state, str) else "unknown"