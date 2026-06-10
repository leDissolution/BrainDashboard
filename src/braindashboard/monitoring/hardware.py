from __future__ import annotations

import asyncio
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from braindashboard.collectors.gpu import GpuSnapshot, NvidiaSmiCollector
from braindashboard.collectors.host import HostCollector, HostSnapshot
from braindashboard.core.config import Settings
from braindashboard.db.hardware import HardwareBucketCreate, record_hardware_buckets


@dataclass(frozen=True)
class HardwareSample:
    host: HostSnapshot
    gpus: list[GpuSnapshot]


@dataclass
class MetricRollup:
    total: float = 0.0
    minimum: float | None = None
    maximum: float | None = None
    count: int = 0

    def add(self, value: float | None) -> None:
        if value is None:
            return
        self.total += value
        self.minimum = value if self.minimum is None else min(self.minimum, value)
        self.maximum = value if self.maximum is None else max(self.maximum, value)
        self.count += 1

    @property
    def average(self) -> float | None:
        if self.count == 0:
            return None
        return self.total / self.count


@dataclass
class DeviceRollup:
    scope: str
    device_key: str
    device_name: str | None
    sample_count: int = 0
    cpu_percent: MetricRollup = field(default_factory=MetricRollup)
    memory_percent: MetricRollup = field(default_factory=MetricRollup)
    gpu_utilization_percent: MetricRollup = field(default_factory=MetricRollup)
    vram_used_mib: MetricRollup = field(default_factory=MetricRollup)
    vram_total_mib: MetricRollup = field(default_factory=MetricRollup)
    temperature_c: MetricRollup = field(default_factory=MetricRollup)
    power_draw_w: MetricRollup = field(default_factory=MetricRollup)

    def add_host(self, sample: HostSnapshot) -> None:
        self.sample_count += 1
        self.cpu_percent.add(sample.cpu_percent)
        self.memory_percent.add(sample.memory_percent)
        self.temperature_c.add(sample.cpu_temperature_c)

    def add_gpu(self, sample: GpuSnapshot) -> None:
        self.sample_count += 1
        self.gpu_utilization_percent.add(sample.utilization_gpu_percent)
        self.vram_used_mib.add(sample.memory_used_mib)
        self.vram_total_mib.add(sample.memory_total_mib)
        self.temperature_c.add(sample.temperature_c)
        self.power_draw_w.add(sample.power_draw_w)


@dataclass
class BucketRollup:
    bucket_start: datetime
    bucket_seconds: int
    sample_interval_seconds: float
    expected_samples: int
    devices: dict[tuple[str, str], DeviceRollup] = field(default_factory=dict)

    def add_sample(self, sample: HardwareSample) -> None:
        host = self._device("host", "host", "Host")
        host.add_host(sample.host)

        for gpu in sample.gpus:
            device = self._device("gpu", f"gpu:{gpu.index}", gpu.name)
            device.add_gpu(gpu)

    def to_records(self) -> list[HardwareBucketCreate]:
        records: list[HardwareBucketCreate] = []
        for device in self.devices.values():
            missing_samples = max(self.expected_samples - device.sample_count, 0)
            observed_seconds = min(
                self.bucket_seconds,
                device.sample_count * self.sample_interval_seconds,
            )
            power_draw_w_avg = device.power_draw_w.average
            energy_kwh = None
            if power_draw_w_avg is not None:
                energy_kwh = power_draw_w_avg * observed_seconds / 3_600_000

            records.append(
                HardwareBucketCreate(
                    bucket_start=self.bucket_start,
                    bucket_seconds=self.bucket_seconds,
                    scope=device.scope,
                    device_key=device.device_key,
                    device_name=device.device_name,
                    sample_count=device.sample_count,
                    missing_sample_count=missing_samples,
                    observed_seconds=observed_seconds,
                    cpu_percent_avg=device.cpu_percent.average,
                    cpu_percent_min=device.cpu_percent.minimum,
                    cpu_percent_max=device.cpu_percent.maximum,
                    memory_percent_avg=device.memory_percent.average,
                    memory_percent_min=device.memory_percent.minimum,
                    memory_percent_max=device.memory_percent.maximum,
                    gpu_utilization_percent_avg=device.gpu_utilization_percent.average,
                    gpu_utilization_percent_min=device.gpu_utilization_percent.minimum,
                    gpu_utilization_percent_max=device.gpu_utilization_percent.maximum,
                    vram_used_mib_avg=device.vram_used_mib.average,
                    vram_used_mib_min=device.vram_used_mib.minimum,
                    vram_used_mib_max=device.vram_used_mib.maximum,
                    vram_total_mib_avg=device.vram_total_mib.average,
                    temperature_c_avg=device.temperature_c.average,
                    temperature_c_min=device.temperature_c.minimum,
                    temperature_c_max=device.temperature_c.maximum,
                    power_draw_w_avg=power_draw_w_avg,
                    power_draw_w_min=device.power_draw_w.minimum,
                    power_draw_w_max=device.power_draw_w.maximum,
                    energy_kwh=energy_kwh,
                )
            )
        return records

    def _device(self, scope: str, device_key: str, device_name: str | None) -> DeviceRollup:
        key = (scope, device_key)
        if key not in self.devices:
            self.devices[key] = DeviceRollup(
                scope=scope,
                device_key=device_key,
                device_name=device_name,
            )
        return self.devices[key]


class HardwareMonitorService:
    def __init__(
        self,
        *,
        sessionmaker: async_sessionmaker[AsyncSession],
        settings: Settings,
        host_collector: HostCollector | None = None,
        gpu_collector: NvidiaSmiCollector | None = None,
    ) -> None:
        self._sessionmaker = sessionmaker
        self._settings = settings
        self._host_collector = host_collector or HostCollector()
        self._gpu_collector = gpu_collector or NvidiaSmiCollector()
        self._stop_event = asyncio.Event()
        self._loop_task: asyncio.Task[None] | None = None
        self._current_bucket: BucketRollup | None = None

    async def start(self) -> None:
        if self._loop_task is not None and not self._loop_task.done():
            return
        self._stop_event.clear()
        self._loop_task = asyncio.create_task(
            self._run_loop(),
            name="braindashboard-hardware-monitor",
        )

    async def stop(self) -> None:
        self._stop_event.set()
        if self._loop_task is not None:
            await self._loop_task
        self._current_bucket = None

    async def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                await self.tick()
            except Exception:
                pass
            with suppress(TimeoutError):
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._settings.hardware_sample_interval_seconds,
                )

    async def tick(self) -> None:
        sample = await asyncio.to_thread(self._collect)
        bucket_start = _floor_datetime(
            sample.host.timestamp,
            self._settings.hardware_bucket_seconds,
        )
        if self._current_bucket is None:
            self._current_bucket = self._new_bucket(bucket_start)
        elif self._current_bucket.bucket_start != bucket_start:
            await self._flush_current_bucket()
            self._current_bucket = self._new_bucket(bucket_start)

        self._current_bucket.add_sample(sample)

    async def _flush_current_bucket(self) -> None:
        if self._current_bucket is None:
            return
        records = self._current_bucket.to_records()
        self._current_bucket = None
        if not records:
            return

        try:
            async with self._sessionmaker() as session:
                await record_hardware_buckets(
                    session,
                    records,
                    cost_per_kwh=self._settings.electricity_cost_per_kwh,
                )
        except SQLAlchemyError:
            return

    def _collect(self) -> HardwareSample:
        return HardwareSample(
            host=self._host_collector.collect(),
            gpus=self._gpu_collector.collect(),
        )

    def _new_bucket(self, bucket_start: datetime) -> BucketRollup:
        return BucketRollup(
            bucket_start=bucket_start,
            bucket_seconds=self._settings.hardware_bucket_seconds,
            sample_interval_seconds=self._settings.hardware_sample_interval_seconds,
            expected_samples=max(
                int(
                    self._settings.hardware_bucket_seconds
                    / self._settings.hardware_sample_interval_seconds
                ),
                1,
            ),
        )


def _floor_datetime(value: datetime, bucket_seconds: int) -> datetime:
    timestamp = int(value.timestamp())
    bucket_timestamp = timestamp - (timestamp % bucket_seconds)
    return datetime.fromtimestamp(bucket_timestamp, tz=UTC)


def total_energy_kwh(buckets: Iterable[HardwareBucketCreate]) -> float:
    return sum(bucket.energy_kwh or 0.0 for bucket in buckets)
