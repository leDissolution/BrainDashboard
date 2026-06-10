from __future__ import annotations

from braindashboard.executors.base import ExecutionHandle, ExecutionRequest


class DockerJobExecutor:
    async def start(self, request: ExecutionRequest) -> ExecutionHandle:
        raise NotImplementedError("Docker execution has not been implemented yet.")

    async def cancel(self, handle: ExecutionHandle) -> None:
        raise NotImplementedError("Docker cancellation has not been implemented yet.")
