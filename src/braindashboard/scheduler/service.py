from __future__ import annotations

import asyncio
import codecs
from asyncio import StreamReader
from contextlib import suppress
from pathlib import Path
from shlex import join as shell_join
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from braindashboard.core.config import Settings
from braindashboard.db.job_runs import (
    append_job_event_record,
    claim_next_queued_run,
    count_active_job_runs,
    get_job_run_record,
    mark_active_runs_lost,
    mark_job_run_final,
    mark_job_run_running,
    mark_job_run_starting,
)
from braindashboard.domain.enums import JobRunState
from braindashboard.executors.base import ExecutionHandle, ExecutionRequest
from braindashboard.executors.events import (
    JobEvent,
    JobEventParseError,
    build_job_event_environment,
    parse_fallback_progress_line,
    parse_job_event_line,
)
from braindashboard.executors.native import NativeJobExecutor


class SchedulerService:
    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession],
        settings: Settings,
        native_executor: NativeJobExecutor | None = None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._settings = settings
        self._native_executor = native_executor or NativeJobExecutor(
            cancel_grace_seconds=settings.native_cancel_grace_seconds
        )
        self._stop_event = asyncio.Event()
        self._loop_task: asyncio.Task[None] | None = None
        self._supervision_tasks: dict[str, asyncio.Task[None]] = {}
        self._handles: dict[str, ExecutionHandle] = {}

    async def start(self) -> None:
        if self._loop_task is not None and not self._loop_task.done():
            return
        self._stop_event.clear()
        self._loop_task = asyncio.create_task(self._run_loop(), name="braindashboard-scheduler")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._loop_task is not None:
            await self._loop_task

    async def reconcile(self) -> None:
        async with self._sessionmaker() as session:
            await mark_active_runs_lost(session)

    async def tick(self) -> None:
        await self._cancel_requested_runs()
        async with self._sessionmaker() as session:
            active_count = await count_active_job_runs(session)
            if active_count >= self._settings.job_max_active_runs:
                return
            run = await claim_next_queued_run(session)

        if run is not None:
            await self._launch_run(run.id)

    async def _run_loop(self) -> None:
        await self.reconcile()
        while not self._stop_event.is_set():
            try:
                await self.tick()
            except Exception:
                pass
            with suppress(TimeoutError):
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._settings.scheduler_tick_interval_seconds,
                )

    async def _launch_run(self, run_id: str) -> None:
        async with self._sessionmaker() as session:
            run = await get_job_run_record(session, run_id)
            if run is None:
                return
            await mark_job_run_starting(session, run_id)
            definition = run.definition
            request = ExecutionRequest(
                job_run_id=run.id,
                command=list(run.effective_command),
                working_directory=Path(definition.working_directory)
                if definition is not None and definition.working_directory
                else None,
                environment=build_job_event_environment(run.id),
                stdout_log_path=Path(run.log_stdout_path) if run.log_stdout_path else None,
                stderr_log_path=Path(run.log_stderr_path) if run.log_stderr_path else None,
            )

        try:
            handle = await self._native_executor.start(request)
        except Exception as exc:
            failure_message = f"Failed to start native process: {exc}"
            await self._write_scheduler_failure_to_log(request, failure_message)
            async with self._sessionmaker() as session:
                await mark_job_run_final(
                    session,
                    run_id,
                    state=JobRunState.FAILED,
                    failure_summary={"message": failure_message},
                )
            return

        self._handles[run_id] = handle
        async with self._sessionmaker() as session:
            await mark_job_run_running(session, run_id, external_id=handle.external_id)

        task = asyncio.create_task(self._supervise_run(run_id, handle), name=f"job-run-{run_id}")
        self._supervision_tasks[run_id] = task

    async def _supervise_run(self, run_id: str, handle: ExecutionHandle) -> None:
        process = self._native_executor.process_for(run_id)
        if process is None:
            async with self._sessionmaker() as session:
                await mark_job_run_final(
                    session,
                    run_id,
                    state=JobRunState.LOST,
                    failure_summary={"message": "Native process handle was unavailable."},
                )
            return

        async with self._sessionmaker() as session:
            run = await get_job_run_record(session, run_id)
            stdout_path = Path(run.log_stdout_path) if run and run.log_stdout_path else None
            stderr_path = Path(run.log_stderr_path) if run and run.log_stderr_path else None
            timeout_seconds = run.timeout_seconds if run else None

        stream_tasks = [
            asyncio.create_task(
                self._capture_stream(run_id, "stdout", process.stdout, stdout_path),
                name=f"job-run-{run_id}-stdout",
            ),
            asyncio.create_task(
                self._capture_stream(run_id, "stderr", process.stderr, stderr_path),
                name=f"job-run-{run_id}-stderr",
            ),
        ]
        exit_code: int | None = None
        timed_out = False
        try:
            if timeout_seconds is None:
                exit_code = await process.wait()
            else:
                exit_code = await asyncio.wait_for(process.wait(), timeout=timeout_seconds)
        except TimeoutError:
            timed_out = True
            await self._native_executor.cancel(handle)
            exit_code = await process.wait()
        finally:
            await asyncio.gather(*stream_tasks, return_exceptions=True)
            await self._finalize_run(run_id, exit_code=exit_code, timed_out=timed_out)
            self._native_executor.forget(run_id)
            self._handles.pop(run_id, None)
            self._supervision_tasks.pop(run_id, None)

    async def _capture_stream(
        self,
        run_id: str,
        stream_name: str,
        reader: StreamReader | None,
        path: Path | None,
    ) -> None:
        if reader is None or path is None:
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        record_number = 0
        text_buffer = ""
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        last_fallback_progress_signature: tuple[Any, ...] | None = None
        with path.open("ab") as log_file:
            while True:
                chunk = await reader.read(4096)
                if not chunk:
                    break
                log_file.write(chunk)
                log_file.flush()
                text_buffer += decoder.decode(chunk)
                records, text_buffer = _split_completed_stream_records(text_buffer)
                for record in records:
                    record_number += 1
                    event = _parse_stream_event(record, run_id=run_id)
                    if event is None:
                        continue
                    signature = _fallback_progress_signature(event)
                    if signature is not None and signature == last_fallback_progress_signature:
                        continue
                    if signature is not None:
                        last_fallback_progress_signature = signature
                    async with self._sessionmaker() as session:
                        await append_job_event_record(
                            session,
                            run_id=run_id,
                            event=event,
                            stream=stream_name,
                            line_number=record_number,
                        )

            text_buffer += decoder.decode(b"", final=True)
            if text_buffer:
                record_number += 1
                event = _parse_stream_event(text_buffer, run_id=run_id)
                if event is not None:
                    async with self._sessionmaker() as session:
                        await append_job_event_record(
                            session,
                            run_id=run_id,
                            event=event,
                            stream=stream_name,
                            line_number=record_number,
                        )

    async def _cancel_requested_runs(self) -> None:
        for run_id, handle in list(self._handles.items()):
            async with self._sessionmaker() as session:
                run = await get_job_run_record(session, run_id)
                should_cancel = run is not None and run.state == JobRunState.CANCEL_REQUESTED.value
            if should_cancel:
                await self._native_executor.cancel(handle)

    async def _finalize_run(self, run_id: str, *, exit_code: int | None, timed_out: bool) -> None:
        async with self._sessionmaker() as session:
            run = await get_job_run_record(session, run_id)
            if run is None or run.state in {
                JobRunState.SUCCEEDED.value,
                JobRunState.FAILED.value,
                JobRunState.CANCELED.value,
                JobRunState.TIMED_OUT.value,
                JobRunState.LOST.value,
                JobRunState.NEEDS_REVIEW.value,
            }:
                return

            if timed_out:
                await mark_job_run_final(
                    session,
                    run_id,
                    state=JobRunState.TIMED_OUT,
                    exit_code=exit_code,
                    failure_summary={"message": "Job timed out."},
                )
            elif run.state == JobRunState.CANCEL_REQUESTED.value:
                await mark_job_run_final(
                    session,
                    run_id,
                    state=JobRunState.CANCELED,
                    exit_code=exit_code,
                )
            elif exit_code == 0:
                await mark_job_run_final(
                    session,
                    run_id,
                    state=JobRunState.SUCCEEDED,
                    exit_code=exit_code,
                )
            else:
                await mark_job_run_final(
                    session,
                    run_id,
                    state=JobRunState.FAILED,
                    exit_code=exit_code,
                    failure_summary={"message": f"Process exited with code {exit_code}."},
                )

    async def _write_scheduler_failure_to_log(
        self,
        request: ExecutionRequest,
        failure_message: str,
    ) -> None:
        if request.stderr_log_path is None:
            return

        command = shell_join(request.command)
        await asyncio.to_thread(
            _append_text_file,
            request.stderr_log_path,
            f"{failure_message}\nCommand: {command}\n",
        )


def _append_text_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as log_file:
        log_file.write(content)


def _parse_stream_event(record: str, *, run_id: str) -> JobEvent | None:
    try:
        event = parse_job_event_line(record)
    except JobEventParseError:
        return None
    if event is not None:
        return event
    return parse_fallback_progress_line(record, run_id=run_id)


def _split_completed_stream_records(buffer: str) -> tuple[list[str], str]:
    records: list[str] = []
    start = 0
    index = 0
    while index < len(buffer):
        character = buffer[index]
        if character in {"\r", "\n"}:
            records.append(buffer[start:index])
            if character == "\r" and index + 1 < len(buffer) and buffer[index + 1] == "\n":
                index += 1
            start = index + 1
        index += 1
    return records, buffer[start:]


def _fallback_progress_signature(event: JobEvent) -> tuple[Any, ...] | None:
    if event.metadata.get("source") != "tqdm" or event.progress is None:
        return None
    return (
        event.phase,
        event.progress.current,
        event.progress.total,
        event.progress.percent,
        event.progress.unit,
    )
