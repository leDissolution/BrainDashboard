from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GpuPowerProfile:
    name: str
    power_limit_w: int | None = None
    application_clocks: tuple[int, int] | None = None
    persistence_mode: bool | None = None


class NvidiaControlAdapter:
    def __init__(self, nvidia_smi_path: str = "nvidia-smi") -> None:
        self.nvidia_smi_path = nvidia_smi_path

    def build_apply_commands(self, profile: GpuPowerProfile) -> list[list[str]]:
        commands: list[list[str]] = []

        if profile.persistence_mode is not None:
            value = "1" if profile.persistence_mode else "0"
            commands.append([self.nvidia_smi_path, "--persistence-mode", value])

        if profile.power_limit_w is not None:
            commands.append([self.nvidia_smi_path, "--power-limit", str(profile.power_limit_w)])

        if profile.application_clocks is not None:
            memory_clock_mhz, graphics_clock_mhz = profile.application_clocks
            commands.append(
                [
                    self.nvidia_smi_path,
                    "--applications-clocks",
                    f"{memory_clock_mhz},{graphics_clock_mhz}",
                ]
            )

        return commands

    async def apply_profile(self, profile: GpuPowerProfile) -> None:
        raise NotImplementedError("GPU writes need a constrained privilege boundary first.")
