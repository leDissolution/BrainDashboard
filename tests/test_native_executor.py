from __future__ import annotations

from pathlib import Path

import pytest

from braindashboard.executors.base import ExecutionRequest
from braindashboard.executors.native import NativeExecutionStartError, NativeJobExecutor


async def test_native_executor_reports_missing_working_directory(tmp_path: Path) -> None:
    executor = NativeJobExecutor()

    with pytest.raises(NativeExecutionStartError, match="Working directory does not exist"):
        await executor.start(
            ExecutionRequest(
                job_run_id="run-1",
                command=["python", "-c", "print('hello')"],
                working_directory=tmp_path / "missing",
            )
        )


async def test_native_executor_reports_missing_path_executable(tmp_path: Path) -> None:
    executor = NativeJobExecutor()

    with pytest.raises(NativeExecutionStartError, match="Executable path does not exist"):
        await executor.start(
            ExecutionRequest(
                job_run_id="run-1",
                command=["./missing-python", "-m", "example"],
                working_directory=tmp_path,
            )
        )


async def test_native_executor_hints_when_command_line_is_single_argv(tmp_path: Path) -> None:
    executor = NativeJobExecutor()

    with pytest.raises(NativeExecutionStartError, match="split it into executable and arguments"):
        await executor.start(
            ExecutionRequest(
                job_run_id="run-1",
                command=["./missing-python -m example"],
                working_directory=tmp_path,
            )
        )