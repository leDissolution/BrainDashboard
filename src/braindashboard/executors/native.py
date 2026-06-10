from __future__ import annotations

import asyncio
import os
from asyncio.subprocess import Process
from pathlib import Path
from shutil import which

from braindashboard.executors.base import ExecutionHandle, ExecutionRequest


class NativeExecutionStartError(RuntimeError):
    pass


class NativeJobExecutor:
    def __init__(self, *, cancel_grace_seconds: float = 10.0) -> None:
        self._cancel_grace_seconds = cancel_grace_seconds
        self._processes: dict[str, Process] = {}

    async def start(self, request: ExecutionRequest) -> ExecutionHandle:
        environment = {**os.environ, **request.environment}
        _validate_execution_request(request, environment)
        process = await asyncio.create_subprocess_exec(
            *request.command,
            cwd=str(request.working_directory) if request.working_directory is not None else None,
            env=environment,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        self._processes[request.job_run_id] = process
        return ExecutionHandle(job_run_id=request.job_run_id, external_id=str(process.pid))

    async def cancel(self, handle: ExecutionHandle) -> None:
        process = self._processes.get(handle.job_run_id)
        if process is None or process.returncode is not None:
            return

        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=self._cancel_grace_seconds)
        except TimeoutError:
            process.kill()
            await process.wait()

    def process_for(self, job_run_id: str) -> Process | None:
        return self._processes.get(job_run_id)

    def forget(self, job_run_id: str) -> None:
        self._processes.pop(job_run_id, None)


def _validate_execution_request(request: ExecutionRequest, environment: dict[str, str]) -> None:
    if not request.command:
        raise NativeExecutionStartError("Native command is empty.")

    if request.working_directory is not None:
        working_directory = request.working_directory.expanduser()
        if not working_directory.exists():
            raise NativeExecutionStartError(
                f"Working directory does not exist: {working_directory}"
            )
        if not working_directory.is_dir():
            raise NativeExecutionStartError(
                f"Working directory is not a directory: {working_directory}"
            )

    executable = request.command[0]
    if _looks_like_path(executable):
        executable_path = _resolve_executable_path(executable, request.working_directory)
        if not executable_path.exists():
            hint = (
                " If this is a full command line, split it into executable and arguments."
                if any(character.isspace() for character in executable)
                else ""
            )
            raise NativeExecutionStartError(
                f"Executable path does not exist: {executable} "
                f"(resolved to {executable_path}).{hint}"
            )
        if executable_path.is_dir():
            raise NativeExecutionStartError(f"Executable path is a directory: {executable_path}")
        return

    resolved_executable = which(executable, path=environment.get("PATH"))
    if resolved_executable is None:
        raise NativeExecutionStartError(
            f"Executable was not found on PATH: {executable}. "
            f"Use an absolute path or update BRAINDASHBOARD job/service PATH."
        )


def _looks_like_path(executable: str) -> bool:
    return any(separator in executable for separator in ("/", "\\")) or Path(
        executable
    ).is_absolute()


def _resolve_executable_path(executable: str, working_directory: Path | None) -> Path:
    executable_path = Path(executable).expanduser()
    if executable_path.is_absolute() or working_directory is None:
        return executable_path
    return working_directory.expanduser() / executable_path
