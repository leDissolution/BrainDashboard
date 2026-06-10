from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from braindashboard.db.job_runs import ACTIVE_RUN_STATES
from braindashboard.db.models import (
    HardwareSampleBucketRecord,
    JobHardwareUsageRecord,
    JobRunRecord,
)


@dataclass(frozen=True)
class HardwareBucketCreate:
    bucket_start: datetime
    bucket_seconds: int
    scope: str
    device_key: str
    device_name: str | None
    sample_count: int
    missing_sample_count: int
    observed_seconds: float
    cpu_percent_avg: float | None = None
    cpu_percent_min: float | None = None
    cpu_percent_max: float | None = None
    memory_percent_avg: float | None = None
    memory_percent_min: float | None = None
    memory_percent_max: float | None = None
    gpu_utilization_percent_avg: float | None = None
    gpu_utilization_percent_min: float | None = None
    gpu_utilization_percent_max: float | None = None
    vram_used_mib_avg: float | None = None
    vram_used_mib_min: float | None = None
    vram_used_mib_max: float | None = None
    vram_total_mib_avg: float | None = None
    temperature_c_avg: float | None = None
    temperature_c_min: float | None = None
    temperature_c_max: float | None = None
    power_draw_w_avg: float | None = None
    power_draw_w_min: float | None = None
    power_draw_w_max: float | None = None
    energy_kwh: float | None = None


async def record_hardware_buckets(
    session: AsyncSession,
    buckets: Sequence[HardwareBucketCreate],
    *,
    cost_per_kwh: float | None,
) -> list[HardwareSampleBucketRecord]:
    run_id = await _single_active_run_id(session)
    records = [
        _bucket_record_from_create(bucket, run_id=run_id, cost_per_kwh=cost_per_kwh)
        for bucket in buckets
    ]
    session.add_all(records)
    if run_id is not None:
        await _update_job_usage_summary(session, run_id, buckets, cost_per_kwh=cost_per_kwh)
    await session.commit()
    return records


async def list_hardware_bucket_records(
    session: AsyncSession,
    *,
    start: datetime,
    end: datetime | None = None,
    scope: str | None = None,
    device_key: str | None = None,
    bucket_seconds: int | None = None,
    limit: int = 5000,
) -> list[HardwareSampleBucketRecord]:
    statement = (
        select(HardwareSampleBucketRecord)
        .where(HardwareSampleBucketRecord.bucket_start >= start)
        .order_by(
            HardwareSampleBucketRecord.bucket_start,
            HardwareSampleBucketRecord.scope,
            HardwareSampleBucketRecord.device_key,
        )
        .limit(limit)
    )
    if end is not None:
        statement = statement.where(HardwareSampleBucketRecord.bucket_start < end)
    if scope is not None:
        statement = statement.where(HardwareSampleBucketRecord.scope == scope)
    if device_key is not None:
        statement = statement.where(HardwareSampleBucketRecord.device_key == device_key)
    if bucket_seconds is not None:
        statement = statement.where(HardwareSampleBucketRecord.bucket_seconds == bucket_seconds)

    result = await session.scalars(statement)
    return list(result.all())


def _bucket_record_from_create(
    bucket: HardwareBucketCreate,
    *,
    run_id: str | None,
    cost_per_kwh: float | None,
) -> HardwareSampleBucketRecord:
    cost_amount = None
    if cost_per_kwh is not None and bucket.energy_kwh is not None:
        cost_amount = bucket.energy_kwh * cost_per_kwh

    return HardwareSampleBucketRecord(
        bucket_start=bucket.bucket_start,
        bucket_seconds=bucket.bucket_seconds,
        scope=bucket.scope,
        device_key=bucket.device_key,
        device_name=bucket.device_name,
        run_id=run_id,
        sample_count=bucket.sample_count,
        missing_sample_count=bucket.missing_sample_count,
        observed_seconds=bucket.observed_seconds,
        cpu_percent_avg=bucket.cpu_percent_avg,
        cpu_percent_min=bucket.cpu_percent_min,
        cpu_percent_max=bucket.cpu_percent_max,
        memory_percent_avg=bucket.memory_percent_avg,
        memory_percent_min=bucket.memory_percent_min,
        memory_percent_max=bucket.memory_percent_max,
        gpu_utilization_percent_avg=bucket.gpu_utilization_percent_avg,
        gpu_utilization_percent_min=bucket.gpu_utilization_percent_min,
        gpu_utilization_percent_max=bucket.gpu_utilization_percent_max,
        vram_used_mib_avg=bucket.vram_used_mib_avg,
        vram_used_mib_min=bucket.vram_used_mib_min,
        vram_used_mib_max=bucket.vram_used_mib_max,
        vram_total_mib_avg=bucket.vram_total_mib_avg,
        temperature_c_avg=bucket.temperature_c_avg,
        temperature_c_min=bucket.temperature_c_min,
        temperature_c_max=bucket.temperature_c_max,
        power_draw_w_avg=bucket.power_draw_w_avg,
        power_draw_w_min=bucket.power_draw_w_min,
        power_draw_w_max=bucket.power_draw_w_max,
        energy_kwh=bucket.energy_kwh,
        cost_amount=cost_amount,
    )


async def _single_active_run_id(session: AsyncSession) -> str | None:
    result = await session.scalars(
        select(JobRunRecord.id)
        .where(JobRunRecord.state.in_(ACTIVE_RUN_STATES))
        .order_by(JobRunRecord.started_at.desc().nullslast(), JobRunRecord.id)
        .limit(2)
    )
    run_ids = list(result.all())
    # TODO: When concurrent jobs arrive, attribute usage through scheduler GPU locks/mutexes.
    return run_ids[0] if len(run_ids) == 1 else None


async def _update_job_usage_summary(
    session: AsyncSession,
    run_id: str,
    buckets: Sequence[HardwareBucketCreate],
    *,
    cost_per_kwh: float | None,
) -> None:
    usage = await session.get(JobHardwareUsageRecord, run_id)
    if usage is None:
        usage = JobHardwareUsageRecord(
            run_id=run_id,
            bucket_count=0,
            host_sample_count=0,
            gpu_sample_count=0,
            gpu_energy_kwh=0.0,
        )
        session.add(usage)

    usage.bucket_count += len(buckets)
    bucket_starts = [bucket.bucket_start for bucket in buckets]
    if bucket_starts:
        first_bucket_start = min(bucket_starts)
        last_bucket_start = max(bucket_starts)
        usage.first_bucket_start = (
            first_bucket_start
            if usage.first_bucket_start is None
            else min(usage.first_bucket_start, first_bucket_start)
        )
        usage.last_bucket_start = (
            last_bucket_start
            if usage.last_bucket_start is None
            else max(usage.last_bucket_start, last_bucket_start)
        )

    for bucket in buckets:
        if bucket.scope == "host":
            usage.cpu_percent_avg = _merge_average(
                usage.cpu_percent_avg,
                usage.host_sample_count,
                bucket.cpu_percent_avg,
                bucket.sample_count,
            )
            usage.host_sample_count += bucket.sample_count
        elif bucket.scope == "gpu":
            usage.gpu_utilization_percent_avg = _merge_average(
                usage.gpu_utilization_percent_avg,
                usage.gpu_sample_count,
                bucket.gpu_utilization_percent_avg,
                bucket.sample_count,
            )
            usage.gpu_power_draw_w_avg = _merge_average(
                usage.gpu_power_draw_w_avg,
                usage.gpu_sample_count,
                bucket.power_draw_w_avg,
                bucket.sample_count,
            )
            usage.gpu_sample_count += bucket.sample_count
            usage.gpu_energy_kwh += bucket.energy_kwh or 0.0

    if cost_per_kwh is not None:
        usage.estimated_cost_amount = usage.gpu_energy_kwh * cost_per_kwh


def _merge_average(
    current_average: float | None,
    current_count: int,
    new_average: float | None,
    new_count: int,
) -> float | None:
    if new_average is None or new_count == 0:
        return current_average
    if current_average is None or current_count == 0:
        return new_average
    return ((current_average * current_count) + (new_average * new_count)) / (
        current_count + new_count
    )
