from __future__ import annotations

import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

JOB_EVENT_PREFIX = "BD_EVENT "
JOB_RUN_ID_ENV = "BRAINDASHBOARD_RUN_ID"
JOB_EVENT_PREFIX_ENV = "BRAINDASHBOARD_EVENT_PREFIX"
TQDM_PROGRESS_SOURCE = "tqdm"

_TQDM_BAR_PATTERN = re.compile(
    r"""
    ^\s*
    (?:(?P<label>[^|\r\n]*?):\s*)?
    (?P<percent>\d{1,3}(?:\.\d+)?)%\|
    (?P<bar>[^|\r\n]*)\|
    \s*
    (?P<current>\d[\d,]*(?:\.\d+)?)\s*/\s*(?P<total>\d[\d,]*(?:\.\d+)?)
    (?P<suffix>\s+\[[^\]\r\n]*\].*)?
    \s*$
    """,
    re.VERBOSE,
)

_TQDM_COUNTER_PATTERN = re.compile(
    r"""
    ^\s*
    (?:(?P<label>[^:\[\r\n]*?):\s*)?
    (?P<current>\d[\d,]*(?:\.\d+)?)\s*
    (?P<unit>[A-Za-z][\w/-]*)
    \s+\[[^\]\r\n]*\]
    .*
    \s*$
    """,
    re.VERBOSE,
)


class JobEventType(StrEnum):
    STARTED = "started"
    HEARTBEAT = "heartbeat"
    PHASE_CHANGED = "phase_changed"
    PROGRESS = "progress"
    METRIC = "metric"
    CHECKPOINT = "checkpoint"
    ARTIFACT = "artifact"
    WARNING = "warning"
    COMPLETED = "completed"
    FAILED = "failed"


class JobEventParseError(ValueError):
    def __init__(self, message: str, line: str) -> None:
        super().__init__(message)
        self.line = line


class JobProgress(BaseModel):
    model_config = ConfigDict(extra="forbid")

    current: float | None = None
    total: float | None = None
    unit: str | None = None
    percent: float | None = Field(default=None, ge=0, le=100)


class JobArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    uri: str
    kind: str | None = None
    name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class JobError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str | None = None
    message: str
    retryable: bool | None = None


class JobEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    type: JobEventType
    run_id: str | None = None
    event_id: str | None = None
    sequence: int | None = Field(default=None, ge=0)
    timestamp: datetime | None = None
    phase: str | None = None
    message: str | None = None
    progress: JobProgress | None = None
    metrics: dict[str, int | float | str | bool | None] = Field(default_factory=dict)
    artifacts: list[JobArtifact] = Field(default_factory=list)
    error: JobError | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def subjob_id(self) -> str | None:
        value = self.metadata.get("subjob_id")
        return value if isinstance(value, str) and value else None


class JobSubjobState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: str | None = None
    index: int | float | None = None
    total: int | float | None = None
    parent_id: str | None = None
    status: str
    label: str
    phase: str | None = None
    message: str | None = None
    latest_event_type: JobEventType
    progress: JobProgress | None = None
    metrics: dict[str, int | float | str | bool | None] = Field(default_factory=dict)
    error: JobError | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def build_subjob_states(events: list[JobEvent]) -> list[JobSubjobState]:
    states: dict[str, JobSubjobState] = {}

    for event in events:
        subjob_id = event.subjob_id
        if subjob_id is None:
            continue

        previous = states.get(subjob_id)
        metadata = {**(previous.metadata if previous else {}), **event.metadata}
        status = _subjob_status(event, metadata, previous)
        label = _string_metadata(metadata, "subjob_label") or (
            previous.label if previous else subjob_id
        )
        index = _numeric_metadata(metadata, "subjob_index")
        total = _numeric_metadata(metadata, "subjob_total")
        states[subjob_id] = JobSubjobState(
            id=subjob_id,
            type=_string_metadata(metadata, "subjob_type") or (previous.type if previous else None),
            index=index if index is not None else (previous.index if previous else None),
            total=total if total is not None else (previous.total if previous else None),
            parent_id=_string_metadata(metadata, "parent_subjob_id")
            or (previous.parent_id if previous else None),
            status=status,
            label=label,
            phase=event.phase or (previous.phase if previous else None),
            message=event.message or (previous.message if previous else None),
            latest_event_type=event.type,
            progress=event.progress or (previous.progress if previous else None),
            metrics={**(previous.metrics if previous else {}), **event.metrics},
            error=event.error or (previous.error if previous else None),
            metadata=metadata,
        )

    return sorted(states.values(), key=_subjob_sort_key)


def _subjob_status(
    event: JobEvent,
    metadata: dict[str, Any],
    previous: JobSubjobState | None,
) -> str:
    status = _string_metadata(metadata, "subjob_status")
    if status:
        return status
    if event.type is JobEventType.COMPLETED:
        return "complete"
    if event.type is JobEventType.FAILED:
        return "failed"
    if event.type in {JobEventType.STARTED, JobEventType.PHASE_CHANGED, JobEventType.PROGRESS}:
        return "running"
    return previous.status if previous else "pending"


def _string_metadata(metadata: dict[str, Any], key: str) -> str | None:
    value = metadata.get(key)
    return value if isinstance(value, str) and value else None


def _numeric_metadata(metadata: dict[str, Any], key: str) -> int | float | None:
    value = metadata.get(key)
    return value if isinstance(value, int | float) and not isinstance(value, bool) else None


def _subjob_sort_key(state: JobSubjobState) -> tuple[bool, int | float | str, str]:
    return (state.index is None, state.index if state.index is not None else state.label, state.id)


def build_job_event_environment(job_run_id: str) -> dict[str, str]:
    return {
        JOB_RUN_ID_ENV: job_run_id,
        JOB_EVENT_PREFIX_ENV: JOB_EVENT_PREFIX.strip(),
    }


def parse_job_event_line(line: str, prefix: str = JOB_EVENT_PREFIX) -> JobEvent | None:
    normalized_line = line.rstrip("\r\n")
    if not normalized_line.startswith(prefix):
        return None

    payload = normalized_line[len(prefix) :]
    try:
        data = json.loads(payload)
    except json.JSONDecodeError as error:
        raise JobEventParseError(f"Invalid job event JSON: {error.msg}", line) from error

    if not isinstance(data, dict):
        raise JobEventParseError("Job event payload must be a JSON object", line)

    try:
        return JobEvent.model_validate(data)
    except ValidationError as error:
        raise JobEventParseError(f"Invalid job event payload: {error}", line) from error


def parse_tqdm_progress_line(line: str, *, run_id: str | None = None) -> JobEvent | None:
    normalized_line = line.strip("\r\n")
    match = _TQDM_BAR_PATTERN.match(normalized_line)
    if match is not None:
        current = _parse_progress_number(match.group("current"))
        total = _parse_progress_number(match.group("total"))
        percent = _parse_percent(match.group("percent"))
        if current is None or total is None or percent is None:
            return None

        label = _normalize_tqdm_label(match.group("label"))
        return JobEvent(
            type=JobEventType.PROGRESS,
            run_id=run_id,
            phase=label,
            message=_normalize_tqdm_message(normalized_line),
            progress=JobProgress(current=current, total=total, unit="it", percent=percent),
            metadata={"source": TQDM_PROGRESS_SOURCE},
        )

    match = _TQDM_COUNTER_PATTERN.match(normalized_line)
    if match is None:
        return None

    current = _parse_progress_number(match.group("current"))
    if current is None:
        return None

    label = _normalize_tqdm_label(match.group("label"))
    unit = match.group("unit")
    return JobEvent(
        type=JobEventType.PROGRESS,
        run_id=run_id,
        phase=label,
        message=_normalize_tqdm_message(normalized_line),
        progress=JobProgress(current=current, unit=unit),
        metadata={"source": TQDM_PROGRESS_SOURCE},
    )


def parse_fallback_progress_line(line: str, *, run_id: str | None = None) -> JobEvent | None:
    return parse_tqdm_progress_line(line, run_id=run_id)


def _parse_progress_number(value: str) -> float | None:
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def _parse_percent(value: str) -> float | None:
    number = _parse_progress_number(value)
    if number is None:
        return None
    return max(0.0, min(100.0, number))


def _normalize_tqdm_label(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _normalize_tqdm_message(value: str) -> str:
    return " ".join(value.strip().split())
