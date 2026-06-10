from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import psutil
from fastapi.testclient import TestClient

from braindashboard.api.routes import hardware
from braindashboard.collectors import host
from braindashboard.collectors.gpu import GpuSnapshot
from braindashboard.collectors.host import DiskSnapshot, HostSnapshot
from braindashboard.collectors.network import NetworkSnapshot
from braindashboard.core.config import Settings
from braindashboard.main import create_app


def app_with_scheduler_disabled() -> object:
    return create_app(Settings(scheduler_enabled=False, hardware_monitor_enabled=False))


def test_hardware_snapshot_endpoint(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    timestamp = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)

    monkeypatch.setattr(
        hardware.host_collector,
        "collect",
        lambda: HostSnapshot(
            timestamp=timestamp,
            cpu_percent=12.5,
            cpu_count=16,
            cpu_temperature_c=61.4,
            memory_percent=42.0,
            memory_used_gib=26.75,
            memory_total_gib=64.0,
            swap_percent=0.0,
            disk_percent=63.2,
            disk_free_gib=512.25,
            disk_total_gib=1397.0,
            disks=[
                DiskSnapshot(
                    device="/dev/nvme0n1p2",
                    mountpoint="/",
                    filesystem="ext4",
                    percent=63.2,
                    free_gib=512.25,
                    total_gib=1397.0,
                ),
                DiskSnapshot(
                    device="/dev/sda1",
                    mountpoint="/mnt/archive",
                    filesystem="xfs",
                    percent=78.4,
                    free_gib=2048.0,
                    total_gib=9312.0,
                ),
            ],
        ),
    )
    monkeypatch.setattr(
        hardware.gpu_collector,
        "collect",
        lambda: [
            GpuSnapshot(
                timestamp=timestamp,
                index=0,
                name="NVIDIA Test GPU",
                utilization_gpu_percent=68.0,
                memory_used_mib=12000.0,
                memory_total_mib=24576.0,
                temperature_c=54.0,
                power_draw_w=188.5,
                power_limit_w=190.0,
                clocks_graphics_mhz=1410.0,
                clocks_memory_mhz=10501.0,
            )
        ],
    )
    monkeypatch.setattr(
        hardware.network_collector,
        "collect",
        lambda: NetworkSnapshot(
            timestamp=timestamp,
            interface_name="eth0",
            bytes_sent_per_second=1024.0,
            bytes_recv_per_second=2048.0,
            packets_sent_per_second=12.0,
            packets_recv_per_second=24.0,
            internet_reachable=True,
            internet_latency_ms=8.5,
        ),
    )

    client = TestClient(app_with_scheduler_disabled())

    response = client.get("/api/hardware/snapshot")

    assert response.status_code == 200
    body = response.json()
    assert body["host"]["cpu_percent"] == 12.5
    assert body["host"]["cpu_count"] == 16
    assert body["host"]["cpu_temperature_c"] == 61.4
    assert body["host"]["memory_total_gib"] == 64.0
    assert body["host"]["disks"][0]["mountpoint"] == "/"
    assert body["host"]["disks"][1]["device"] == "/dev/sda1"
    assert body["gpus"][0]["name"] == "NVIDIA Test GPU"
    assert body["gpus"][0]["memory_total_mib"] == 24576.0
    assert body["gpus"][0]["power_limit_w"] == 190.0
    assert body["gpus"][0]["clocks_graphics_mhz"] == 1410.0
    assert body["network"]["interface_name"] == "eth0"
    assert body["network"]["internet_reachable"] is True


def test_hardware_snapshot_allows_empty_gpu_list(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    timestamp = datetime(2026, 5, 24, 12, 0, tzinfo=UTC)

    monkeypatch.setattr(
        hardware.host_collector,
        "collect",
        lambda: HostSnapshot(
            timestamp=timestamp,
            cpu_percent=10.0,
            cpu_count=8,
            cpu_temperature_c=None,
            memory_percent=20.0,
            memory_used_gib=6.0,
            memory_total_gib=32.0,
            swap_percent=0.0,
            disk_percent=50.0,
            disk_free_gib=256.0,
            disk_total_gib=512.0,
            disks=[],
        ),
    )
    monkeypatch.setattr(hardware.gpu_collector, "collect", lambda: [])
    monkeypatch.setattr(
        hardware.network_collector,
        "collect",
        lambda: NetworkSnapshot(
            timestamp=timestamp,
            interface_name="eth0",
            bytes_sent_per_second=0.0,
            bytes_recv_per_second=0.0,
            packets_sent_per_second=0.0,
            packets_recv_per_second=0.0,
            internet_reachable=False,
            internet_latency_ms=None,
        ),
    )

    client = TestClient(app_with_scheduler_disabled())

    response = client.get("/api/hardware/snapshot")

    assert response.status_code == 200
    assert response.json()["gpus"] == []


def test_host_collector_skips_boot_mounts(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    partitions = [
        SimpleNamespace(device="/dev/root", mountpoint="/", fstype="ext4"),
        SimpleNamespace(device="/dev/nvme0n1p2", mountpoint="/boot", fstype="ext4"),
        SimpleNamespace(device="/dev/nvme0n1p1", mountpoint="/boot/efi", fstype="vfat"),
        SimpleNamespace(device="/dev/nvme0n1p3", mountpoint="/mnt/models", fstype="ext4"),
    ]

    def disk_usage(path: str) -> SimpleNamespace:
        return SimpleNamespace(percent=51.0, free=1024**3, total=2 * 1024**3)

    monkeypatch.setattr(psutil, "disk_partitions", lambda all: partitions)
    monkeypatch.setattr(psutil, "disk_usage", disk_usage)

    disks = host.HostCollector()._collect_disks()

    assert [disk.mountpoint for disk in disks] == ["/", "/mnt/models"]