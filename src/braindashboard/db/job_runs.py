from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from braindashboard.db.models import JobEventRecord, JobRunRecord
from braindashboard.domain.enums import JobRunState
from braindashboard.executors.events import JobEvent

ACTIVE_RUN_STATES = {
    JobRunState.ADMITTED.value,
    JobRunState.STARTING.value,
    JobRunState.RUNNING.value,
    JobRunState.CANCEL_REQUESTED.value,
}
TERMINAL_RUN_STATES = {
    JobRunState.SUCCEEDED.value,
    JobRunState.FAILED.value,
    JobRunState.CANCELED.value,
    JobRunState.TIMED_OUT.value,
    JobRunState.LOST.value,
    JobRunState.NEEDS_REVIEW.value,
}


async def create_job_run_record(
    session: AsyncSession,
    *,
    run_id: str | None = None,
    definition_id: str,
    priority: str,
    effective_parameters: dict[str, object],
    effective_command: list[str],
    timeout_seconds: int | None,
    log_stdout_path: str,
    log_stderr_path: str,
) -> JobRunRecord:
    run = JobRunRecord(
        id=run_id or f"run-{uuid4().hex}",
        definition_id=definition_id,
        state=JobRunState.QUEUED.value,
        priority=priority,
        attempt=1,
        effective_parameters=effective_parameters,
        effective_command=effective_command,
        timeout_seconds=timeout_seconds,
        log_stdout_path=log_stdout_path,
        log_stderr_path=log_stderr_path,
    )
    session.add(run)
    await session.commit()
    return run


async def list_job_run_records(
    session: AsyncSession,
    *,
    state: str | None = None,
    definition_id: str | None = None,
    limit: int = 50,
    include_events: bool = False,
) -> list[JobRunRecord]:
    options = [
        selectinload(JobRunRecord.definition),
        selectinload(JobRunRecord.hardware_usage),
    ]
    if include_events:
        options.append(selectinload(JobRunRecord.events))

    statement = (
        select(JobRunRecord)
        .options(*options)
        .order_by(JobRunRecord.queued_at.desc(), JobRunRecord.id.desc())
        .limit(limit)
    )
    if state is not None:
        statement = statement.where(JobRunRecord.state == state)
    if definition_id is not None:
        statement = statement.where(JobRunRecord.definition_id == definition_id)

    result = await session.scalars(statement)
    return list(result.all())


SubjobSummary = dict[str, int]


async def list_job_subjob_summaries(
    session: AsyncSession,
    run_ids: Sequence[str],
) -> dict[str, SubjobSummary]:
    if not run_ids:
        return {}

    subjob_id = JobEventRecord.event_metadata["subjob_id"].as_string()
    result = await session.execute(
        select(
            JobEventRecord.run_id,
            subjob_id.label("subjob_id"),
            JobEventRecord.event_metadata["subjob_status"].as_string().label("subjob_status"),
            JobEventRecord.type,
        )
        .where(JobEventRecord.run_id.in_(run_ids), subjob_id.is_not(None))
        .order_by(JobEventRecord.run_id, JobEventRecord.created_at, JobEventRecord.id)
    )
    statuses: dict[str, dict[str, str]] = {}
    for run_id, subjob_id_value, subjob_status, event_type in result.all():
        if not isinstance(subjob_id_value, str) or not subjob_id_value:
            continue
        run_statuses = statuses.setdefault(str(run_id), {})
        run_statuses[subjob_id_value] = _subjob_status_from_event(
            status=subjob_status,
            event_type=str(event_type),
            previous=run_statuses.get(subjob_id_value),
        )

    return {
        run_id: {
            "finished": sum(1 for status in run_statuses.values() if _is_finished_subjob(status)),
            "failed": sum(1 for status in run_statuses.values() if _is_failed_subjob(status)),
            "total": len(run_statuses),
        }
        for run_id, run_statuses in statuses.items()
    }


def _subjob_status_from_event(
    *,
    status: object,
    event_type: str,
    previous: str | None,
) -> str:
    if isinstance(status, str) and status:
        return status
    if event_type == "completed":
        return "complete"
    if event_type == "failed":
        return "failed"
    if event_type in {"started", "phase_changed", "progress"}:
        return "running"
    return previous or "pending"


def _is_finished_subjob(status: str) -> bool:
    return status in {"complete", "completed", "succeeded"}


def _is_failed_subjob(status: str) -> bool:
    return status in {"failed", "timed_out", "lost", "needs_review"}


async def get_job_run_record(session: AsyncSession, run_id: str) -> JobRunRecord | None:
    return await session.get(
        JobRunRecord,
        run_id,
        options=[
            selectinload(JobRunRecord.definition),
            selectinload(JobRunRecord.events),
            selectinload(JobRunRecord.hardware_usage),
        ],
    )


async def list_job_event_records(
    session: AsyncSession,
    run_id: str,
    *,
    limit: int = 200,
) -> list[JobEventRecord]:
    result = await session.scalars(
        select(JobEventRecord)
        .where(JobEventRecord.run_id == run_id)
        .order_by(
            JobEventRecord.sequence.is_(None),
            JobEventRecord.sequence,
            JobEventRecord.created_at,
            JobEventRecord.id,
        )
        .limit(limit)
    )
    return list(result.all())


async def request_cancel_job_run(session: AsyncSession, run_id: str) -> JobRunRecord | None:
    run = await session.get(
        JobRunRecord,
        run_id,
        options=[
            selectinload(JobRunRecord.definition),
            selectinload(JobRunRecord.events),
            selectinload(JobRunRecord.hardware_usage),
        ],
    )
    if run is None:
        return None

    now = datetime.now(UTC)
    if run.state == JobRunState.QUEUED.value:
        run.state = JobRunState.CANCELED.value
        run.cancel_requested_at = now
        run.finished_at = now
    elif run.state in ACTIVE_RUN_STATES:
        run.state = JobRunState.CANCEL_REQUESTED.value
        run.cancel_requested_at = now
    await session.commit()
    return run


async def count_active_job_runs(session: AsyncSession) -> int:
    value = await session.scalar(
        select(func.count()).select_from(JobRunRecord).where(JobRunRecord.state.in_(ACTIVE_RUN_STATES))
    )
    return int(value or 0)


async def claim_next_queued_run(session: AsyncSession) -> JobRunRecord | None:
    priority_order = case(
        (JobRunRecord.priority == "high", 0),
        (JobRunRecord.priority == "normal", 1),
        (JobRunRecord.priority == "low", 2),
        else_=3,
    )
    statement = (
        select(JobRunRecord)
        .where(JobRunRecord.state == JobRunState.QUEUED.value)
        .order_by(priority_order, JobRunRecord.queued_at, JobRunRecord.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    run = await session.scalar(statement)
    if run is None:
        return None

    now = datetime.now(UTC)
    run.state = JobRunState.ADMITTED.value
    run.admitted_at = now
    await session.commit()
    return run


async def mark_job_run_starting(
    session: AsyncSession,
    run_id: str,
    *,
    external_id: str | None = None,
) -> JobRunRecord | None:
    run = await session.get(JobRunRecord, run_id)
    if run is None:
        return None
    now = datetime.now(UTC)
    run.state = JobRunState.STARTING.value
    run.started_at = now
    run.external_id = external_id
    await session.commit()
    return run


async def mark_job_run_running(
    session: AsyncSession,
    run_id: str,
    *,
    external_id: str,
) -> JobRunRecord | None:
    run = await session.get(JobRunRecord, run_id)
    if run is None:
        return None
    if run.started_at is None:
        run.started_at = datetime.now(UTC)
    run.state = JobRunState.RUNNING.value
    run.external_id = external_id
    await session.commit()
    return run


async def mark_job_run_final(
    session: AsyncSession,
    run_id: str,
    *,
    state: JobRunState,
    exit_code: int | None = None,
    failure_summary: dict[str, object] | None = None,
) -> JobRunRecord | None:
    run = await session.get(JobRunRecord, run_id)
    if run is None:
        return None

    run.state = state.value
    run.exit_code = exit_code
    run.failure_summary = failure_summary
    run.finished_at = datetime.now(UTC)
    await session.commit()
    return run


async def mark_active_runs_lost(session: AsyncSession) -> int:
    result = await session.scalars(
        select(JobRunRecord).where(JobRunRecord.state.in_(ACTIVE_RUN_STATES))
    )
    runs = list(result.all())
    now = datetime.now(UTC)
    for run in runs:
        run.state = JobRunState.LOST.value
        run.finished_at = now
        run.failure_summary = {"message": "Scheduler restarted and could not reattach to the run."}
    await session.commit()
    return len(runs)


async def append_job_event_record(
    session: AsyncSession,
    *,
    run_id: str,
    event: JobEvent,
    stream: str,
    line_number: int,
) -> JobEventRecord:
    payload = event.model_dump(mode="json", exclude_none=True)
    record = JobEventRecord(
        run_id=run_id,
        event_id=event.event_id,
        sequence=event.sequence,
        type=event.type.value,
        timestamp=event.timestamp,
        stream=stream,
        line_number=line_number,
        phase=event.phase,
        message=event.message,
        progress=_model_to_dict(event.progress),
        metrics=dict(event.metrics),
        artifacts=[artifact.model_dump(mode="json") for artifact in event.artifacts],
        error=_model_to_dict(event.error),
        event_metadata=dict(event.metadata),
        raw_payload=payload,
    )
    session.add(record)
    await session.commit()
    return record


def event_records_to_payload(records: Sequence[JobEventRecord]) -> list[dict[str, Any]]:
    return [
        {
            "id": record.id,
            "run_id": record.run_id,
            "event_id": record.event_id,
            "sequence": record.sequence,
            "type": record.type,
            "timestamp": record.timestamp,
            "stream": record.stream,
            "line_number": record.line_number,
            "phase": record.phase,
            "message": record.message,
            "progress": record.progress,
            "metrics": record.metrics,
            "artifacts": record.artifacts,
            "error": record.error,
            "metadata": record.event_metadata,
            "created_at": record.created_at,
        }
        for record in records
    ]


def _model_to_dict(model: Any) -> dict[str, object] | None:
    if model is None:
        return None
    return dict(model.model_dump(mode="json"))
