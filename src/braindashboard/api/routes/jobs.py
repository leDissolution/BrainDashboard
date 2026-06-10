from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from starlette.concurrency import run_in_threadpool

from braindashboard.core.config import Settings, get_settings
from braindashboard.db.job_definitions import (
    delete_job_definition_record,
    ensure_seeded_job_definitions,
    list_job_definition_records,
    save_job_definition_record,
)
from braindashboard.db.job_runs import (
    create_job_run_record,
    event_records_to_payload,
    get_job_run_record,
    list_job_event_records,
    list_job_run_records,
    list_job_subjob_summaries,
    request_cancel_job_run,
)
from braindashboard.db.models import JobDefinitionRecord, JobParameterRecord, JobRunRecord
from braindashboard.db.session import get_db_session
from braindashboard.domain.enums import JobExecutionMode, JobRunState
from braindashboard.executors.events import JobEvent, build_subjob_states

router = APIRouter(prefix="/jobs", tags=["jobs"])


class ResourceHintsResponse(BaseModel):
    gpu_count: int = 0
    min_vram_gib: float | None = None
    exclusive_gpu: bool = False
    docker_required: bool = False


class RetryPolicyResponse(BaseModel):
    max_attempts: int = 1
    backoff_seconds: int = 0


ParameterValue = str | int | float | bool | None


class JobParameterResponse(BaseModel):
    name: str
    label: str
    description: str
    value_type: Literal["string", "integer", "float", "boolean", "path", "choice", "flag"]
    cli_flag: str
    default_value: ParameterValue = None
    required_at_queue: bool = False
    allow_queue_override: bool = True
    choices: list[str] = Field(default_factory=list)


class JobDefinitionResponse(BaseModel):
    id: str
    name: str
    description: str
    enabled: bool
    execution_mode: JobExecutionMode
    command: list[str]
    working_directory: str | None = None
    image: str | None = None
    default_priority: Literal["low", "normal", "high"] = "normal"
    timeout_seconds: int | None = None
    event_contract: Literal["structured_stdout", "none"] = "structured_stdout"
    resource_hints: ResourceHintsResponse
    retry_policy: RetryPolicyResponse
    parameters: list[JobParameterResponse] = Field(default_factory=list)


class JobDefinitionsResponse(BaseModel):
    definitions: list[JobDefinitionResponse]


class JobDefinitionWriteRequest(JobDefinitionResponse):
    pass


class JobQueueRequest(BaseModel):
    parameters: dict[str, ParameterValue] = Field(default_factory=dict)
    priority: Literal["low", "normal", "high"] | None = None


class JobProgressResponse(BaseModel):
    current: float | None = None
    total: float | None = None
    unit: str | None = None
    percent: float | None = None


class JobSubjobResponse(BaseModel):
    id: str
    type: str | None = None
    index: int | float | None = None
    total: int | float | None = None
    parent_id: str | None = None
    status: str
    label: str
    phase: str | None = None
    message: str | None = None
    latest_event_type: str
    progress: JobProgressResponse | None = None
    metrics: dict[str, object]
    error: dict[str, object] | None = None
    metadata: dict[str, object]


class JobHardwareUsageResponse(BaseModel):
    bucket_count: int
    host_sample_count: int
    gpu_sample_count: int
    gpu_energy_kwh: float
    estimated_cost_amount: float | None = None
    cpu_percent_avg: float | None = None
    gpu_utilization_percent_avg: float | None = None
    gpu_power_draw_w_avg: float | None = None
    first_bucket_start: datetime | None = None
    last_bucket_start: datetime | None = None


class JobSubjobSummaryResponse(BaseModel):
    finished: int = 0
    failed: int = 0
    total: int = 0


class JobRunResponse(BaseModel):
    id: str
    definition_id: str
    definition_name: str | None = None
    state: JobRunState
    priority: Literal["low", "normal", "high"]
    attempt: int
    effective_parameters: dict[str, object]
    effective_command: list[str]
    timeout_seconds: int | None = None
    external_id: str | None = None
    log_stdout_path: str | None = None
    log_stderr_path: str | None = None
    exit_code: int | None = None
    failure_summary: dict[str, object] | None = None
    queued_at: datetime
    admitted_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    cancel_requested_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    progress: JobProgressResponse | None = None
    subjob_count: int = 0
    subjob_summary: JobSubjobSummaryResponse = Field(default_factory=JobSubjobSummaryResponse)
    subjobs: list[JobSubjobResponse] = Field(default_factory=list)
    hardware_usage: JobHardwareUsageResponse | None = None


class JobRunsResponse(BaseModel):
    runs: list[JobRunResponse]


class JobEventResponse(BaseModel):
    id: int
    run_id: str
    event_id: str | None = None
    sequence: int | None = None
    type: str
    timestamp: datetime | None = None
    stream: str
    line_number: int
    phase: str | None = None
    message: str | None = None
    progress: dict[str, object] | None = None
    metrics: dict[str, object]
    artifacts: list[dict[str, object]]
    error: dict[str, object] | None = None
    metadata: dict[str, object]
    created_at: datetime


class JobEventsResponse(BaseModel):
    events: list[JobEventResponse]


class JobLogsResponse(BaseModel):
    run_id: str
    stream: Literal["stdout", "stderr"]
    path: str | None = None
    lines: list[str]


_SEEDED_JOB_DEFINITIONS = [
    JobDefinitionResponse(
        id="train-lora-native",
        name="LoRA training",
        description="Native training pipeline with structured BD_EVENT progress lines.",
        enabled=True,
        execution_mode=JobExecutionMode.NATIVE,
        command=["/opt/BrainDashboard/jobs/train-lora.sh"],
        working_directory="/srv/ml/training",
        default_priority="normal",
        timeout_seconds=43_200,
        event_contract="structured_stdout",
        resource_hints=ResourceHintsResponse(
            gpu_count=1,
            min_vram_gib=18.0,
            exclusive_gpu=True,
        ),
        retry_policy=RetryPolicyResponse(max_attempts=1),
        parameters=[
            JobParameterResponse(
                name="dataset_path",
                label="Dataset path",
                description="Training dataset directory on the host.",
                value_type="path",
                cli_flag="--dataset",
                required_at_queue=True,
            ),
            JobParameterResponse(
                name="base_model",
                label="Base model",
                description="Base model or checkpoint to fine tune.",
                value_type="string",
                cli_flag="--base-model",
                required_at_queue=True,
            ),
            JobParameterResponse(
                name="output_name",
                label="Output name",
                description="Run output folder and display name.",
                value_type="string",
                cli_flag="--output-name",
                required_at_queue=True,
            ),
            JobParameterResponse(
                name="max_steps",
                label="Max steps",
                description="Training step limit.",
                value_type="integer",
                cli_flag="--max-steps",
                default_value=1200,
            ),
            JobParameterResponse(
                name="learning_rate",
                label="Learning rate",
                description="Optimizer learning rate.",
                value_type="float",
                cli_flag="--learning-rate",
                default_value=0.00002,
            ),
        ],
    ),
    JobDefinitionResponse(
        id="dataset-caption-docker",
        name="Dataset caption pass",
        description="Containerized captioning pass for staged image datasets.",
        enabled=True,
        execution_mode=JobExecutionMode.DOCKER,
        command=["python", "-m", "pipeline.caption"],
        image="ghcr.io/local/caption-worker:latest",
        default_priority="low",
        timeout_seconds=21_600,
        event_contract="structured_stdout",
        resource_hints=ResourceHintsResponse(
            gpu_count=1,
            min_vram_gib=10.0,
            docker_required=True,
        ),
        retry_policy=RetryPolicyResponse(max_attempts=2, backoff_seconds=300),
        parameters=[
            JobParameterResponse(
                name="input_path",
                label="Input path",
                description="Dataset folder to caption.",
                value_type="path",
                cli_flag="--input",
                required_at_queue=True,
            ),
            JobParameterResponse(
                name="output_path",
                label="Output path",
                description="Folder for captions and metadata.",
                value_type="path",
                cli_flag="--output",
                required_at_queue=True,
            ),
            JobParameterResponse(
                name="batch_size",
                label="Batch size",
                description="Images processed per batch.",
                value_type="integer",
                cli_flag="--batch-size",
                default_value=8,
            ),
            JobParameterResponse(
                name="caption_model",
                label="Caption model",
                description="Caption model preset.",
                value_type="choice",
                cli_flag="--caption-model",
                default_value="joycaption",
                choices=["joycaption", "wd14", "florence2"],
            ),
        ],
    ),
    JobDefinitionResponse(
        id="model-eval-smoke",
        name="Model eval smoke test",
        description="Short validation run for a newly exported model artifact.",
        enabled=False,
        execution_mode=JobExecutionMode.NATIVE,
        command=["/opt/BrainDashboard/jobs/eval-smoke.sh"],
        working_directory="/srv/ml/evals",
        default_priority="high",
        timeout_seconds=3_600,
        event_contract="structured_stdout",
        resource_hints=ResourceHintsResponse(gpu_count=1, min_vram_gib=8.0),
        retry_policy=RetryPolicyResponse(max_attempts=1),
        parameters=[
            JobParameterResponse(
                name="model_path",
                label="Model path",
                description="Model artifact to validate.",
                value_type="path",
                cli_flag="--model",
                required_at_queue=True,
            ),
            JobParameterResponse(
                name="suite_path",
                label="Suite path",
                description="Evaluation prompt suite file.",
                value_type="path",
                cli_flag="--suite",
                default_value="/srv/ml/evals/smoke.json",
            ),
        ],
    ),
]


@router.get("/definitions")
async def job_definitions(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JobDefinitionsResponse:
    try:
        records = await list_job_definition_records(session)
    except SQLAlchemyError:
        await session.rollback()
        return JobDefinitionsResponse(definitions=_SEEDED_JOB_DEFINITIONS)

    if not records:
        try:
            await ensure_seeded_job_definitions(
                session,
                [definition.model_dump(mode="json") for definition in _SEEDED_JOB_DEFINITIONS],
            )
        except SQLAlchemyError:
            await session.rollback()
        return JobDefinitionsResponse(definitions=_SEEDED_JOB_DEFINITIONS)

    return JobDefinitionsResponse(
        definitions=[_job_definition_from_record(record) for record in records]
    )


@router.post("/definitions", status_code=status.HTTP_201_CREATED)
async def create_job_definition(
    definition: JobDefinitionWriteRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JobDefinitionResponse:
    return await _save_job_definition(definition, session)


@router.post("/definitions/{definition_id}/queue", status_code=status.HTTP_201_CREATED)
async def queue_job_definition(
    definition_id: str,
    request: JobQueueRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> JobRunResponse:
    definition_record = await session.get(
        JobDefinitionRecord,
        definition_id,
        options=[selectinload(JobDefinitionRecord.parameters)],
    )
    if definition_record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job definition not found.",
        )

    definition = _job_definition_from_record(definition_record)
    if not definition.enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Job definition is disabled.",
        )
    if definition.execution_mode != JobExecutionMode.NATIVE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only native job execution is supported in this release.",
        )

    effective_parameters = _build_effective_parameters(definition, request.parameters)
    effective_command = _build_effective_command(definition, effective_parameters)
    run_id = f"run-{uuid4().hex}"
    run_directory = await run_in_threadpool(_build_run_directory, settings.job_logs_dir, run_id)
    await run_in_threadpool(run_directory.mkdir, parents=True, exist_ok=True)
    stdout_path = str(run_directory / "stdout.log")
    stderr_path = str(run_directory / "stderr.log")

    try:
        run = await create_job_run_record(
            session,
            run_id=run_id,
            definition_id=definition.id,
            priority=request.priority or definition.default_priority,
            effective_parameters=effective_parameters,
            effective_command=effective_command,
            timeout_seconds=definition.timeout_seconds,
            log_stdout_path=stdout_path,
            log_stderr_path=stderr_path,
        )
    except SQLAlchemyError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Job run database is unavailable.",
        ) from exc

    run.definition = definition_record
    return _job_run_from_record(run)


@router.put("/definitions/{definition_id}")
async def update_job_definition(
    definition_id: str,
    definition: JobDefinitionWriteRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JobDefinitionResponse:
    if definition.id != definition_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Definition id in path and body must match.",
        )

    return await _save_job_definition(definition, session)


@router.delete("/definitions/{definition_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_job_definition(
    definition_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> Response:
    try:
        was_deleted = await delete_job_definition_record(session, definition_id)
    except SQLAlchemyError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Job definition database is unavailable.",
        ) from exc

    if not was_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job definition not found.",
        )

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/runs")
async def job_runs(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    state: Annotated[JobRunState | None, Query()] = None,
    definition_id: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    include_subjobs: Annotated[bool, Query()] = False,
) -> JobRunsResponse:
    try:
        records = await list_job_run_records(
            session,
            state=state.value if state is not None else None,
            definition_id=definition_id,
            limit=limit,
            include_events=True,
        )
        subjob_summaries = await list_job_subjob_summaries(
            session,
            [record.id for record in records],
        )
    except SQLAlchemyError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Job run database is unavailable.",
        ) from exc

    return JobRunsResponse(
        runs=[
            _job_run_from_record(
                record,
                include_details=include_subjobs,
                subjob_summary=subjob_summaries.get(record.id),
            )
            for record in records
        ]
    )


@router.get("/runs/{run_id}")
async def job_run(
    run_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JobRunResponse:
    record = await _get_existing_job_run(session, run_id)
    return _job_run_from_record(record)


@router.get("/runs/{run_id}/events")
async def job_run_events(
    run_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> JobEventsResponse:
    await _get_existing_job_run(session, run_id)
    try:
        records = await list_job_event_records(session, run_id, limit=limit)
    except SQLAlchemyError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Job event database is unavailable.",
        ) from exc

    return JobEventsResponse(
        events=[JobEventResponse.model_validate(item) for item in event_records_to_payload(records)]
    )


@router.get("/runs/{run_id}/logs")
async def job_run_logs(
    run_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    stream: Annotated[Literal["stdout", "stderr"], Query()] = "stdout",
    tail: Annotated[int, Query(ge=1, le=5000)] = 200,
) -> JobLogsResponse:
    record = await _get_existing_job_run(session, run_id)
    path = record.log_stdout_path if stream == "stdout" else record.log_stderr_path
    if path is None:
        return JobLogsResponse(run_id=run_id, stream=stream, path=None, lines=[])

    lines = await run_in_threadpool(_read_tail_lines, Path(path), tail)
    return JobLogsResponse(run_id=run_id, stream=stream, path=path, lines=lines)


@router.post("/runs/{run_id}/cancel")
async def cancel_job_run(
    run_id: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> JobRunResponse:
    try:
        record = await request_cancel_job_run(session, run_id)
    except SQLAlchemyError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Job run database is unavailable.",
        ) from exc

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job run not found.",
        )
    return _job_run_from_record(record)


async def _save_job_definition(
    definition: JobDefinitionWriteRequest,
    session: AsyncSession,
) -> JobDefinitionResponse:
    try:
        record = await save_job_definition_record(session, definition.model_dump(mode="json"))
    except SQLAlchemyError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Job definition database is unavailable.",
        ) from exc

    return _job_definition_from_record(record)


def _job_definition_from_record(record: JobDefinitionRecord) -> JobDefinitionResponse:
    return JobDefinitionResponse(
        id=record.id,
        name=record.name,
        description=record.description,
        enabled=record.enabled,
        execution_mode=JobExecutionMode(record.execution_mode),
        command=list(record.command),
        working_directory=record.working_directory,
        image=record.image,
        default_priority=cast(Literal["low", "normal", "high"], record.default_priority),
        timeout_seconds=record.timeout_seconds,
        event_contract=cast(Literal["structured_stdout", "none"], record.event_contract),
        resource_hints=ResourceHintsResponse.model_validate(record.resource_hints),
        retry_policy=RetryPolicyResponse.model_validate(record.retry_policy),
        parameters=[_job_parameter_from_record(parameter) for parameter in record.parameters],
    )


def _job_parameter_from_record(record: JobParameterRecord) -> JobParameterResponse:
    return JobParameterResponse(
        name=record.name,
        label=record.label,
        description=record.description,
        value_type=cast(
            Literal["string", "integer", "float", "boolean", "path", "choice", "flag"],
            record.value_type,
        ),
        cli_flag=record.cli_flag,
        default_value=cast(ParameterValue, record.default_value),
        required_at_queue=record.required_at_queue,
        allow_queue_override=record.allow_queue_override,
        choices=list(record.choices),
    )


async def _get_existing_job_run(session: AsyncSession, run_id: str) -> JobRunRecord:
    try:
        record = await get_job_run_record(session, run_id)
    except SQLAlchemyError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Job run database is unavailable.",
        ) from exc
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job run not found.",
        )
    return record


def _job_run_from_record(
    run: JobRunRecord,
    *,
    include_details: bool = True,
    subjob_summary: dict[str, int] | None = None,
) -> JobRunResponse:
    definition_name = run.definition.name if run.definition is not None else None
    subjobs = _subjobs_from_record(run) if include_details else []
    resolved_subjob_summary = (
        JobSubjobSummaryResponse.model_validate(subjob_summary)
        if subjob_summary is not None
        else _subjob_summary_from_subjobs(subjobs)
    )
    return JobRunResponse(
        id=run.id,
        definition_id=run.definition_id,
        definition_name=definition_name,
        state=JobRunState(run.state),
        priority=cast(Literal["low", "normal", "high"], run.priority),
        attempt=run.attempt,
        effective_parameters=run.effective_parameters,
        effective_command=list(run.effective_command),
        timeout_seconds=run.timeout_seconds,
        external_id=run.external_id,
        log_stdout_path=run.log_stdout_path,
        log_stderr_path=run.log_stderr_path,
        exit_code=run.exit_code,
        failure_summary=run.failure_summary,
        queued_at=run.queued_at,
        admitted_at=run.admitted_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        cancel_requested_at=run.cancel_requested_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
        progress=_latest_run_progress_from_record(run),
        subjob_count=resolved_subjob_summary.total,
        subjob_summary=resolved_subjob_summary,
        subjobs=subjobs,
        hardware_usage=_hardware_usage_from_record(run),
    )


def _subjob_summary_from_subjobs(subjobs: list[JobSubjobResponse]) -> JobSubjobSummaryResponse:
    return JobSubjobSummaryResponse(
        finished=sum(1 for subjob in subjobs if _is_finished_subjob_status(subjob.status)),
        failed=sum(1 for subjob in subjobs if _is_failed_subjob_status(subjob.status)),
        total=len(subjobs),
    )


def _is_finished_subjob_status(status: str) -> bool:
    return status in {"complete", "completed", "succeeded"}


def _is_failed_subjob_status(status: str) -> bool:
    return status in {"failed", "timed_out", "lost", "needs_review"}


def _hardware_usage_from_record(run: JobRunRecord) -> JobHardwareUsageResponse | None:
    if "hardware_usage" not in run.__dict__ or run.hardware_usage is None:
        return None

    usage = run.hardware_usage
    return JobHardwareUsageResponse(
        bucket_count=usage.bucket_count,
        host_sample_count=usage.host_sample_count,
        gpu_sample_count=usage.gpu_sample_count,
        gpu_energy_kwh=usage.gpu_energy_kwh,
        estimated_cost_amount=usage.estimated_cost_amount,
        cpu_percent_avg=usage.cpu_percent_avg,
        gpu_utilization_percent_avg=usage.gpu_utilization_percent_avg,
        gpu_power_draw_w_avg=usage.gpu_power_draw_w_avg,
        first_bucket_start=usage.first_bucket_start,
        last_bucket_start=usage.last_bucket_start,
    )


def _latest_run_progress_from_record(run: JobRunRecord) -> JobProgressResponse | None:
    if "events" not in run.__dict__:
        return None

    for event_record in sorted(
        run.events,
        key=lambda record: (
            record.sequence is None,
            record.sequence if record.sequence is not None else 0,
            record.created_at,
            record.id,
        ),
        reverse=True,
    ):
        if (
            event_record.progress is None
            or event_record.event_metadata.get("subjob_id") is not None
        ):
            continue
        return JobProgressResponse.model_validate(event_record.progress)

    return None


def _subjobs_from_record(run: JobRunRecord) -> list[JobSubjobResponse]:
    if "events" not in run.__dict__:
        return []

    events: list[JobEvent] = []
    for event_record in run.events:
        try:
            events.append(JobEvent.model_validate(event_record.raw_payload))
        except ValueError:
            continue

    return [
        JobSubjobResponse(
            id=subjob.id,
            type=subjob.type,
            index=subjob.index,
            total=subjob.total,
            parent_id=subjob.parent_id,
            status=subjob.status,
            label=subjob.label,
            phase=subjob.phase,
            message=subjob.message,
            latest_event_type=subjob.latest_event_type.value,
            progress=JobProgressResponse.model_validate(subjob.progress.model_dump())
            if subjob.progress is not None
            else None,
            metrics=dict(subjob.metrics),
            error=subjob.error.model_dump(mode="json") if subjob.error is not None else None,
            metadata=dict(subjob.metadata),
        )
        for subjob in build_subjob_states(events)
    ]


def _build_effective_parameters(
    definition: JobDefinitionResponse,
    submitted_parameters: dict[str, ParameterValue],
) -> dict[str, object]:
    known_names = {parameter.name for parameter in definition.parameters}
    unknown_names = sorted(set(submitted_parameters) - known_names)
    if unknown_names:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown queue parameters: {', '.join(unknown_names)}.",
        )

    effective_parameters: dict[str, object] = {}
    for parameter in definition.parameters:
        was_submitted = parameter.name in submitted_parameters
        if was_submitted and not parameter.allow_queue_override:
            raise HTTPException(
                status_code=422,
                detail=f"Parameter {parameter.name} cannot be overridden at queue time.",
            )

        value = (
            submitted_parameters.get(parameter.name) if was_submitted else parameter.default_value
        )
        if value is None and parameter.required_at_queue:
            raise HTTPException(
                status_code=422,
                detail=f"Parameter {parameter.name} is required when queueing this job.",
            )

        coerced_value = _coerce_parameter_value(parameter, value)
        if (
            parameter.choices
            and coerced_value is not None
            and str(coerced_value) not in parameter.choices
        ):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Parameter {parameter.name} must be one of: "
                    f"{', '.join(parameter.choices)}."
                ),
            )
        effective_parameters[parameter.name] = coerced_value

    return effective_parameters


def _coerce_parameter_value(parameter: JobParameterResponse, value: ParameterValue) -> object:
    if value is None:
        return None
    if parameter.value_type in {"string", "path", "choice"}:
        return str(value)
    if parameter.value_type == "integer":
        if isinstance(value, bool):
            raise _parameter_type_error(parameter, "integer")
        try:
            return int(value)
        except (TypeError, ValueError) as exc:
            raise _parameter_type_error(parameter, "integer") from exc
    if parameter.value_type == "float":
        if isinstance(value, bool):
            raise _parameter_type_error(parameter, "float")
        try:
            return float(value)
        except (TypeError, ValueError) as exc:
            raise _parameter_type_error(parameter, "float") from exc
    if parameter.value_type in {"boolean", "flag"}:
        return _coerce_bool(parameter, value)
    return value


def _coerce_bool(parameter: JobParameterResponse, value: ParameterValue) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
    raise _parameter_type_error(parameter, "boolean")


def _parameter_type_error(parameter: JobParameterResponse, expected_type: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail=f"Parameter {parameter.name} must be a valid {expected_type}.",
    )


def _build_effective_command(
    definition: JobDefinitionResponse,
    effective_parameters: dict[str, object],
) -> list[str]:
    command = list(definition.command)
    for parameter in definition.parameters:
        value = effective_parameters.get(parameter.name)
        if value is None:
            continue
        if parameter.value_type == "flag":
            if value is True:
                command.append(parameter.cli_flag)
            continue
        command.extend([parameter.cli_flag, _parameter_cli_value(value)])
    return command


def _parameter_cli_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _build_run_directory(logs_dir: str, run_id: str) -> Path:
    return Path(logs_dir).expanduser() / run_id


def _read_tail_lines(path: Path, tail: int) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()[-tail:]
