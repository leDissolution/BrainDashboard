from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class ExecutionRequest:
    job_run_id: str
    command: list[str]
    working_directory: Path | None = None
    environment: dict[str, str] = field(default_factory=dict)
    stdout_log_path: Path | None = None
    stderr_log_path: Path | None = None


@dataclass(frozen=True)
class ExecutionHandle:
    job_run_id: str
    external_id: str


class JobExecutor(Protocol):
    async def start(self, request: ExecutionRequest) -> ExecutionHandle:
        ...

    async def cancel(self, handle: ExecutionHandle) -> None:
        ...
