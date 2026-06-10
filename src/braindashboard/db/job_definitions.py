from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from braindashboard.db.models import JobDefinitionRecord, JobParameterRecord

JobDefinitionSeed = Mapping[str, Any]


async def list_job_definition_records(session: AsyncSession) -> list[JobDefinitionRecord]:
    result = await session.scalars(
        select(JobDefinitionRecord)
        .options(selectinload(JobDefinitionRecord.parameters))
        .order_by(JobDefinitionRecord.position, JobDefinitionRecord.id)
    )
    return list(result.all())


async def save_job_definition_record(
    session: AsyncSession,
    definition: JobDefinitionSeed,
) -> JobDefinitionRecord:
    existing_record = await session.get(
        JobDefinitionRecord,
        definition["id"],
        options=[selectinload(JobDefinitionRecord.parameters)],
    )
    if existing_record is None:
        position = await _next_definition_position(session)
        record = _record_from_seed(definition, position)
        session.add(record)
    else:
        existing_record.parameters.clear()
        await session.flush()
        _apply_definition(existing_record, definition)
        record = existing_record

    await session.commit()
    return record


async def delete_job_definition_record(session: AsyncSession, definition_id: str) -> bool:
    existing_record = await session.get(JobDefinitionRecord, definition_id)
    if existing_record is None:
        return False

    await session.delete(existing_record)
    await session.commit()
    return True


async def ensure_seeded_job_definitions(
    session: AsyncSession,
    definitions: Sequence[JobDefinitionSeed],
) -> None:
    definition_count = await session.scalar(select(func.count()).select_from(JobDefinitionRecord))
    if definition_count:
        return

    for position, definition in enumerate(definitions):
        session.add(_record_from_seed(definition, position))

    await session.commit()


def _record_from_seed(definition: JobDefinitionSeed, position: int) -> JobDefinitionRecord:
    parameters = definition.get("parameters", [])
    return JobDefinitionRecord(
        id=definition["id"],
        position=position,
        name=definition["name"],
        description=definition["description"],
        enabled=definition["enabled"],
        execution_mode=definition["execution_mode"],
        command=definition["command"],
        working_directory=definition.get("working_directory"),
        image=definition.get("image"),
        default_priority=definition["default_priority"],
        timeout_seconds=definition.get("timeout_seconds"),
        event_contract=definition["event_contract"],
        resource_hints=definition["resource_hints"],
        retry_policy=definition["retry_policy"],
        parameters=[
            _parameter_record_from_seed(parameter, parameter_position)
            for parameter_position, parameter in enumerate(parameters)
        ],
    )


def _apply_definition(record: JobDefinitionRecord, definition: JobDefinitionSeed) -> None:
    parameters = definition.get("parameters", [])
    record.name = definition["name"]
    record.description = definition["description"]
    record.enabled = definition["enabled"]
    record.execution_mode = definition["execution_mode"]
    record.command = definition["command"]
    record.working_directory = definition.get("working_directory")
    record.image = definition.get("image")
    record.default_priority = definition["default_priority"]
    record.timeout_seconds = definition.get("timeout_seconds")
    record.event_contract = definition["event_contract"]
    record.resource_hints = definition["resource_hints"]
    record.retry_policy = definition["retry_policy"]
    record.parameters = [
        _parameter_record_from_seed(parameter, parameter_position)
        for parameter_position, parameter in enumerate(parameters)
    ]


def _parameter_record_from_seed(
    parameter: Mapping[str, Any],
    position: int,
) -> JobParameterRecord:
    return JobParameterRecord(
        position=position,
        name=parameter["name"],
        label=parameter["label"],
        description=parameter["description"],
        value_type=parameter["value_type"],
        cli_flag=parameter["cli_flag"],
        default_value=parameter.get("default_value"),
        required_at_queue=parameter["required_at_queue"],
        allow_queue_override=parameter["allow_queue_override"],
        choices=parameter["choices"],
    )


async def _next_definition_position(session: AsyncSession) -> int:
    current_max = await session.scalar(select(func.max(JobDefinitionRecord.position)))
    return 0 if current_max is None else current_max + 1
