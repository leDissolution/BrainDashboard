from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime

_GPU_QUERY_FIELDS = ",".join(
    [
        "index",
        "name",
        "utilization.gpu",
        "memory.used",
        "memory.total",
        "temperature.gpu",
        "power.draw",
        "power.limit",
        "clocks.current.graphics",
        "clocks.current.memory",
    ]
)


@dataclass(frozen=True)
class GpuSnapshot:
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


class NvidiaSmiCollector:
    def __init__(self, nvidia_smi_path: str = "nvidia-smi") -> None:
        self.nvidia_smi_path = nvidia_smi_path

    def collect(self) -> list[GpuSnapshot]:
        if shutil.which(self.nvidia_smi_path) is None:
            return []

        command = [
            self.nvidia_smi_path,
            f"--query-gpu={_GPU_QUERY_FIELDS}",
            "--format=csv,noheader,nounits",
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                check=True,
                text=True,
                timeout=5,
            )
        except (FileNotFoundError, subprocess.SubprocessError):
            return []

        timestamp = datetime.now(UTC)
        snapshots: list[GpuSnapshot] = []

        for line in result.stdout.splitlines():
            values = [value.strip() for value in line.split(",")]
            if len(values) != 10:
                continue

            (
                index,
                name,
                utilization,
                memory_used,
                memory_total,
                temperature,
                power_draw,
                power_limit,
                clocks_graphics,
                clocks_memory,
            ) = values
            snapshots.append(
                GpuSnapshot(
                    timestamp=timestamp,
                    index=int(index),
                    name=name,
                    utilization_gpu_percent=_parse_float(utilization),
                    memory_used_mib=_parse_float(memory_used),
                    memory_total_mib=_parse_float(memory_total),
                    temperature_c=_parse_float(temperature),
                    power_draw_w=_parse_float(power_draw),
                    power_limit_w=_parse_float(power_limit),
                    clocks_graphics_mhz=_parse_float(clocks_graphics),
                    clocks_memory_mhz=_parse_float(clocks_memory),
                )
            )

        return snapshots


def _parse_float(value: str) -> float | None:
    if value.lower() in {"n/a", "not supported", ""}:
        return None
    return float(value)
