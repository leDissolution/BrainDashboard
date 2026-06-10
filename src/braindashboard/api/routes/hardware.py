from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from braindashboard.collectors.gpu import NvidiaSmiCollector
from braindashboard.collectors.host import HostCollector
from braindashboard.collectors.network import NetworkCollector
from braindashboard.db.hardware import list_hardware_bucket_records
from braindashboard.db.models import HardwareSampleBucketRecord
from braindashboard.db.session import get_db_session

router = APIRouter(prefix="/hardware", tags=["hardware"])

host_collector = HostCollector()
gpu_collector = NvidiaSmiCollector()
network_collector = NetworkCollector()


class DiskSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device: str
    mountpoint: str
    filesystem: str
    percent: float
    free_gib: float
    total_gib: float


class HostSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    cpu_percent: float
    cpu_count: int
    cpu_temperature_c: float | None
    memory_percent: float
    memory_used_gib: float
    memory_total_gib: float
    swap_percent: float
    disk_percent: float
    disk_free_gib: float
    disk_total_gib: float
    disks: list[DiskSnapshotResponse]


class GpuSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    index: int
    name: str
    utilization_gpu_percent: float | None
    memory_used_mib: float | None
    memory_total_mib: float | None
    temperature_c: float | None
    power_draw_w: float | None
    power_limit_w: float | None
    clocks_graphics_mhz: float | None
    clocks_memory_mhz: float | None


class NetworkSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    timestamp: datetime
    interface_name: str
    bytes_sent_per_second: float
    bytes_recv_per_second: float
    packets_sent_per_second: float
    packets_recv_per_second: float
    internet_reachable: bool
    internet_latency_ms: float | None


class HardwareSnapshotResponse(BaseModel):
    host: HostSnapshotResponse
    gpus: list[GpuSnapshotResponse]
    network: NetworkSnapshotResponse


class HardwareBucketResponse(BaseModel):
    bucket_start: datetime
    bucket_seconds: int
    scope: str
    device_key: str
    device_name: str | None
    run_id: str | None
    sample_count: int
    missing_sample_count: int
    observed_seconds: float
    cpu_percent_avg: float | None
    cpu_percent_min: float | None
    cpu_percent_max: float | None
    memory_percent_avg: float | None
    memory_percent_min: float | None
    memory_percent_max: float | None
    gpu_utilization_percent_avg: float | None
    gpu_utilization_percent_min: float | None
    gpu_utilization_percent_max: float | None
    vram_used_mib_avg: float | None
    vram_used_mib_min: float | None
    vram_used_mib_max: float | None
    vram_total_mib_avg: float | None
    temperature_c_avg: float | None
    temperature_c_min: float | None
    temperature_c_max: float | None
    power_draw_w_avg: float | None
    power_draw_w_min: float | None
    power_draw_w_max: float | None
    energy_kwh: float | None
    cost_amount: float | None


class HardwareHistoryResponse(BaseModel):
    buckets: list[HardwareBucketResponse]


@router.get("/snapshot")
async def hardware_snapshot() -> HardwareSnapshotResponse:
    return HardwareSnapshotResponse(
        host=HostSnapshotResponse.model_validate(host_collector.collect()),
        gpus=[GpuSnapshotResponse.model_validate(snapshot) for snapshot in gpu_collector.collect()],
        network=NetworkSnapshotResponse.model_validate(network_collector.collect()),
    )


@router.get("/history")
async def hardware_history(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    range_hours: Annotated[float, Query(gt=0, le=24 * 30)] = 6,
    scope: Annotated[str | None, Query(pattern="^(host|gpu)$")] = None,
    device_key: Annotated[str | None, Query(max_length=80)] = None,
    bucket_seconds: Annotated[int | None, Query(ge=60, le=86_400)] = None,
    limit: Annotated[int, Query(ge=1, le=100_000)] = 5000,
) -> HardwareHistoryResponse:
    start = datetime.now(UTC) - timedelta(hours=range_hours)
    try:
        records = await list_hardware_bucket_records(
            session,
            start=start,
            scope=scope,
            device_key=device_key,
            bucket_seconds=bucket_seconds,
            limit=limit,
        )
    except SQLAlchemyError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Hardware telemetry database is unavailable.",
        ) from exc

    return HardwareHistoryResponse(buckets=[_bucket_from_record(record) for record in records])


def _bucket_from_record(record: HardwareSampleBucketRecord) -> HardwareBucketResponse:
    return HardwareBucketResponse(
        bucket_start=record.bucket_start,
        bucket_seconds=record.bucket_seconds,
        scope=record.scope,
        device_key=record.device_key,
        device_name=record.device_name,
        run_id=record.run_id,
        sample_count=record.sample_count,
        missing_sample_count=record.missing_sample_count,
        observed_seconds=record.observed_seconds,
        cpu_percent_avg=record.cpu_percent_avg,
        cpu_percent_min=record.cpu_percent_min,
        cpu_percent_max=record.cpu_percent_max,
        memory_percent_avg=record.memory_percent_avg,
        memory_percent_min=record.memory_percent_min,
        memory_percent_max=record.memory_percent_max,
        gpu_utilization_percent_avg=record.gpu_utilization_percent_avg,
        gpu_utilization_percent_min=record.gpu_utilization_percent_min,
        gpu_utilization_percent_max=record.gpu_utilization_percent_max,
        vram_used_mib_avg=record.vram_used_mib_avg,
        vram_used_mib_min=record.vram_used_mib_min,
        vram_used_mib_max=record.vram_used_mib_max,
        vram_total_mib_avg=record.vram_total_mib_avg,
        temperature_c_avg=record.temperature_c_avg,
        temperature_c_min=record.temperature_c_min,
        temperature_c_max=record.temperature_c_max,
        power_draw_w_avg=record.power_draw_w_avg,
        power_draw_w_min=record.power_draw_w_min,
        power_draw_w_max=record.power_draw_w_max,
        energy_kwh=record.energy_kwh,
        cost_amount=record.cost_amount,
    )
