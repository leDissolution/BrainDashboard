from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import psutil

_EXCLUDED_DISK_MOUNTPOINTS = ("/boot", "/boot/")


@dataclass(frozen=True)
class DiskSnapshot:
    device: str
    mountpoint: str
    filesystem: str
    percent: float
    free_gib: float
    total_gib: float


@dataclass(frozen=True)
class HostSnapshot:
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
    disks: list[DiskSnapshot]


class HostCollector:
    def __init__(self, disk_path: str = "/") -> None:
        self.disk_path = disk_path

    def collect(self) -> HostSnapshot:
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage(self.disk_path)
        disks = self._collect_disks()

        return HostSnapshot(
            timestamp=datetime.now(UTC),
            cpu_percent=psutil.cpu_percent(interval=None),
            cpu_count=psutil.cpu_count() or 0,
            cpu_temperature_c=self._collect_cpu_temperature_c(),
            memory_percent=memory.percent,
            memory_used_gib=_bytes_to_gib(memory.used),
            memory_total_gib=_bytes_to_gib(memory.total),
            swap_percent=psutil.swap_memory().percent,
            disk_percent=disk.percent,
            disk_free_gib=_bytes_to_gib(disk.free),
            disk_total_gib=_bytes_to_gib(disk.total),
            disks=disks,
        )

    def _collect_disks(self) -> list[DiskSnapshot]:
        disks: list[DiskSnapshot] = []
        seen_mountpoints: set[str] = set()

        for partition in psutil.disk_partitions(all=False):
            if _is_excluded_disk_mountpoint(partition.mountpoint):
                continue
            if partition.mountpoint in seen_mountpoints:
                continue
            seen_mountpoints.add(partition.mountpoint)

            try:
                usage = psutil.disk_usage(partition.mountpoint)
            except OSError:
                continue

            disks.append(
                DiskSnapshot(
                    device=partition.device,
                    mountpoint=partition.mountpoint,
                    filesystem=partition.fstype,
                    percent=usage.percent,
                    free_gib=_bytes_to_gib(usage.free),
                    total_gib=_bytes_to_gib(usage.total),
                )
            )

        if disks:
            return sorted(disks, key=lambda disk: disk.mountpoint)

        usage = psutil.disk_usage(self.disk_path)
        return [
            DiskSnapshot(
                device=self.disk_path,
                mountpoint=self.disk_path,
                filesystem="unknown",
                percent=usage.percent,
                free_gib=_bytes_to_gib(usage.free),
                total_gib=_bytes_to_gib(usage.total),
            )
        ]

    def _collect_cpu_temperature_c(self) -> float | None:
        sensors_temperatures = getattr(psutil, "sensors_temperatures", None)
        if not callable(sensors_temperatures):
            return None

        try:
            sensor_groups = sensors_temperatures(fahrenheit=False)
        except (OSError, RuntimeError):
            return None

        preferred_groups = ("coretemp", "k10temp", "zenpower", "cpu_thermal", "acpitz")
        for group_name in preferred_groups:
            temperature = _highest_temperature(sensor_groups.get(group_name, []))
            if temperature is not None:
                return temperature

        return _highest_temperature(
            reading
            for readings in sensor_groups.values()
            for reading in readings
        )


def _bytes_to_gib(value: int) -> float:
    return round(value / 1024**3, 2)


def _is_excluded_disk_mountpoint(mountpoint: str) -> bool:
    return mountpoint == _EXCLUDED_DISK_MOUNTPOINTS[0] or mountpoint.startswith(
        _EXCLUDED_DISK_MOUNTPOINTS[1]
    )


def _highest_temperature(readings: Iterable[Any]) -> float | None:
    values: list[float] = []
    for reading in readings:
        current = getattr(reading, "current", None)
        if isinstance(current, int | float):
            values.append(float(current))

    return round(max(values), 1) if values else None
