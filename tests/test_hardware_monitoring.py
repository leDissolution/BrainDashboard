from __future__ import annotations

from collections.abc import AsyncGenerator
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from braindashboard.api.routes import hardware
from braindashboard.collectors.gpu import GpuSnapshot
from braindashboard.collectors.host import HostSnapshot
from braindashboard.core.config import Settings
from braindashboard.db.models import HardwareSampleBucketRecord
from braindashboard.db.session import get_db_session
from braindashboard.main import create_app
from braindashboard.monitoring.hardware import BucketRollup, HardwareSample


def test_bucket_rollup_averages_samples_and_calculates_energy() -> None:
    bucket_start = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)
    rollup = BucketRollup(
        bucket_start=bucket_start,
        bucket_seconds=60,
        sample_interval_seconds=1.0,
        expected_samples=60,
    )

    rollup.add_sample(_sample(bucket_start, cpu_percent=10.0, gpu_load=50.0, gpu_power=100.0))
    rollup.add_sample(_sample(bucket_start, cpu_percent=20.0, gpu_load=70.0, gpu_power=200.0))

    records = rollup.to_records()
    host_record = next(record for record in records if record.scope == "host")
    gpu_record = next(record for record in records if record.scope == "gpu")

    assert host_record.cpu_percent_avg == 15.0
    assert host_record.sample_count == 2
    assert host_record.missing_sample_count == 58
    assert gpu_record.gpu_utilization_percent_avg == 60.0
    assert gpu_record.power_draw_w_avg == 150.0
    assert gpu_record.energy_kwh == 150.0 * 2.0 / 3_600_000


def test_hardware_history_endpoint_returns_persisted_buckets(monkeypatch: MonkeyPatch) -> None:
    bucket_start = datetime(2026, 5, 29, 12, 0, tzinfo=UTC)

    async def list_records(_session: object, **kwargs: object) -> list[HardwareSampleBucketRecord]:
        assert kwargs["scope"] == "gpu"
        assert kwargs["bucket_seconds"] == 60
        return [
            HardwareSampleBucketRecord(
                bucket_start=bucket_start,
                bucket_seconds=60,
                scope="gpu",
                device_key="gpu:0",
                device_name="NVIDIA Test GPU",
                run_id="run-123",
                sample_count=60,
                missing_sample_count=0,
                observed_seconds=60.0,
                gpu_utilization_percent_avg=72.0,
                gpu_utilization_percent_min=50.0,
                gpu_utilization_percent_max=90.0,
                power_draw_w_avg=180.0,
                power_draw_w_min=120.0,
                power_draw_w_max=220.0,
                energy_kwh=0.003,
                cost_amount=0.0006,
            )
        ]

    monkeypatch.setattr(hardware, "list_hardware_bucket_records", list_records)

    app = create_app(Settings(scheduler_enabled=False, hardware_monitor_enabled=False))
    app.dependency_overrides[get_db_session] = _fake_session
    client = TestClient(app)

    response = client.get("/api/hardware/history?scope=gpu&bucket_seconds=60")

    assert response.status_code == 200
    body = response.json()
    assert body["buckets"][0]["device_key"] == "gpu:0"
    assert body["buckets"][0]["gpu_utilization_percent_avg"] == 72.0
    assert body["buckets"][0]["run_id"] == "run-123"
    assert body["buckets"][0]["cost_amount"] == 0.0006


def _sample(
    timestamp: datetime,
    *,
    cpu_percent: float,
    gpu_load: float,
    gpu_power: float,
) -> HardwareSample:
    return HardwareSample(
        host=HostSnapshot(
            timestamp=timestamp,
            cpu_percent=cpu_percent,
            cpu_count=16,
            cpu_temperature_c=61.0,
            memory_percent=40.0,
            memory_used_gib=24.0,
            memory_total_gib=64.0,
            swap_percent=0.0,
            disk_percent=50.0,
            disk_free_gib=100.0,
            disk_total_gib=200.0,
            disks=[],
        ),
        gpus=[
            GpuSnapshot(
                timestamp=timestamp,
                index=0,
                name="NVIDIA Test GPU",
                utilization_gpu_percent=gpu_load,
                memory_used_mib=1024.0,
                memory_total_mib=4096.0,
                temperature_c=55.0,
                power_draw_w=gpu_power,
                power_limit_w=250.0,
                clocks_graphics_mhz=1500.0,
                clocks_memory_mhz=7000.0,
            )
        ],
    )


async def _fake_session() -> AsyncGenerator[object, None]:
    yield object()
