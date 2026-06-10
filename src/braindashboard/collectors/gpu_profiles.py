from __future__ import annotations

import json
import re
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any, Literal

from braindashboard.core.config import Settings

GpuProfileCommandStatus = Literal["applied", "reset"]

_PROFILE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+$")


@dataclass(frozen=True)
class ClockRange:
    min: int
    max: int


@dataclass(frozen=True)
class GpuProfileDefinition:
    name: str
    label: str
    description: str
    gpu_index: int
    lact_device_id: str | None
    power_limit_watts: int | None
    persistence_mode: bool | None
    graphics_clocks_mhz: ClockRange | None
    reset_graphics_clocks: bool
    memory_clocks_mhz: ClockRange | None
    reset_memory_clocks: bool
    gpu_clock_offsets: dict[int, int] | None
    mem_clock_offsets: dict[int, int] | None


@dataclass(frozen=True)
class GpuProfileCommandResult:
    status: GpuProfileCommandStatus
    profile_name: str | None
    detail: str
    commands: list[str]
    warnings: list[str]


class GpuProfileCommandError(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class GpuProfileManager:
    def __init__(self, command: str, timeout_seconds: float) -> None:
        self.command = shlex.split(command)
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_settings(cls, settings: Settings) -> GpuProfileManager:
        return cls(
            command=settings.gpu_profile_command,
            timeout_seconds=settings.gpu_profile_timeout_seconds,
        )

    def list_profiles(self) -> list[GpuProfileDefinition]:
        payload = self._run(["list", "--json"])
        profiles = payload.get("profiles")
        if not isinstance(profiles, list):
            return []

        return [_read_profile(profile) for profile in profiles if isinstance(profile, dict)]

    def apply_profile(self, profile_name: str) -> GpuProfileCommandResult:
        _validate_profile_name(profile_name)
        return _read_command_result(self._run(["apply", profile_name, "--json"]))

    def reset(self) -> GpuProfileCommandResult:
        return _read_command_result(self._run(["reset", "--json"]))

    def _run(self, args: list[str]) -> dict[str, Any]:
        if not self.command:
            raise GpuProfileCommandError("GPU profile command is not configured")

        try:
            result = subprocess.run(
                [*self.command, *args],
                capture_output=True,
                check=True,
                text=True,
                timeout=self.timeout_seconds,
            )
        except FileNotFoundError as error:
            raise GpuProfileCommandError("GPU profile wrapper was not found") from error
        except subprocess.TimeoutExpired as error:
            raise GpuProfileCommandError("GPU profile command timed out") from error
        except subprocess.CalledProcessError as error:
            reason = (error.stderr or error.stdout or "GPU profile command failed").strip()
            raise GpuProfileCommandError(reason) from error
        except subprocess.SubprocessError as error:
            raise GpuProfileCommandError(error.__class__.__name__) from error

        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise GpuProfileCommandError("GPU profile wrapper returned invalid JSON") from error

        if not isinstance(payload, dict):
            raise GpuProfileCommandError("GPU profile wrapper returned an invalid payload")
        return payload


def _validate_profile_name(profile_name: str) -> None:
    if not _PROFILE_NAME_PATTERN.fullmatch(profile_name):
        raise GpuProfileCommandError("GPU profile name contains unsupported characters")


def _read_profile(payload: dict[str, Any]) -> GpuProfileDefinition:
    name = _read_string(payload, "name")
    if name is None:
        raise GpuProfileCommandError("GPU profile payload is missing a name")
    _validate_profile_name(name)

    return GpuProfileDefinition(
        name=name,
        label=_read_string(payload, "label") or name,
        description=_read_string(payload, "description") or "",
        gpu_index=_read_int(payload, "gpu_index") or 0,
        lact_device_id=_read_string(payload, "lact_device_id"),
        power_limit_watts=_read_int(payload, "power_limit_watts"),
        persistence_mode=_read_bool(payload, "persistence_mode"),
        graphics_clocks_mhz=_read_clock_range(payload.get("graphics_clocks_mhz")),
        reset_graphics_clocks=_read_bool(payload, "reset_graphics_clocks") is True,
        memory_clocks_mhz=_read_clock_range(payload.get("memory_clocks_mhz")),
        reset_memory_clocks=_read_bool(payload, "reset_memory_clocks") is True,
        gpu_clock_offsets=_read_offset_map(payload.get("gpu_clock_offsets")),
        mem_clock_offsets=_read_offset_map(payload.get("mem_clock_offsets")),
    )


def _read_command_result(payload: dict[str, Any]) -> GpuProfileCommandResult:
    status = payload.get("status")
    if status not in {"applied", "reset"}:
        raise GpuProfileCommandError("GPU profile wrapper returned an invalid command status")

    commands = payload.get("commands")
    warnings = payload.get("warnings")
    return GpuProfileCommandResult(
        status=status,
        profile_name=_read_string(payload, "profile_name"),
        detail=_read_string(payload, "detail") or status,
        commands=[command for command in commands if isinstance(command, str)]
        if isinstance(commands, list)
        else [],
        warnings=[warning for warning in warnings if isinstance(warning, str)]
        if isinstance(warnings, list)
        else [],
    )


def _read_clock_range(value: object) -> ClockRange | None:
    if not isinstance(value, dict):
        return None

    min_mhz = _read_int(value, "min")
    max_mhz = _read_int(value, "max")
    if min_mhz is None or max_mhz is None:
        return None
    return ClockRange(min=min_mhz, max=max_mhz)


def _read_offset_map(value: object) -> dict[int, int] | None:
    if not isinstance(value, dict):
        return None

    offsets: dict[int, int] = {}
    for raw_pstate, raw_offset in value.items():
        try:
            pstate = int(raw_pstate)
        except (TypeError, ValueError):
            return None
        if isinstance(raw_offset, bool) or not isinstance(raw_offset, int):
            return None
        offsets[pstate] = raw_offset
    return offsets


def _read_string(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    return value if isinstance(value, str) else None


def _read_int(payload: dict[str, Any], key: str) -> int | None:
    value = payload.get(key)
    if isinstance(value, bool):
        return None
    return value if isinstance(value, int) else None


def _read_bool(payload: dict[str, Any], key: str) -> bool | None:
    value = payload.get(key)
    return value if isinstance(value, bool) else None
