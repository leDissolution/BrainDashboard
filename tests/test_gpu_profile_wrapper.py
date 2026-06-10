from __future__ import annotations

import runpy
from pathlib import Path
from typing import Any

import pytest

WRAPPER_PATH = (
    Path(__file__).resolve().parents[1] / "deploy" / "sbin" / "braindashboard-gpu-profile"
)


def load_wrapper() -> dict[str, Any]:
    return runpy.run_path(str(WRAPPER_PATH))


def patch_wrapper_global(wrapper: dict[str, Any], name: str, value: object) -> None:
    wrapper[name] = value
    for item in wrapper.values():
        if callable(item) and hasattr(item, "__globals__"):
            item.__globals__[name] = value


def test_lact_offset_failure_does_not_block_nvidia_profile_apply() -> None:
    wrapper = load_wrapper()
    nvidia_commands: list[list[str]] = []

    def fake_run_commands(commands: list[list[str]]) -> None:
        nvidia_commands.extend(commands)

    def fake_lact_request(command: str, args: dict[str, Any] | None = None) -> object:
        raise wrapper["ConfigError"]("daemon unavailable")

    patch_wrapper_global(wrapper, "run_commands", fake_run_commands)
    patch_wrapper_global(wrapper, "lact_request", fake_lact_request)

    result = wrapper["apply_profile"](
        {
            "profiles": {
                "training": {
                    "label": "Training",
                    "power_limit_watts": 300,
                    "gpu_clock_offsets": {"0": -100},
                    "mem_clock_offsets": {"0": 200},
                }
            }
        },
        "training",
    )

    assert nvidia_commands == [["nvidia-smi", "-i", "0", "-pl", "300"]]
    assert result["status"] == "applied"
    assert result["detail"] == "Applied Training with warnings"
    assert result["warnings"] == ["LACT offsets were not applied: daemon unavailable"]
    assert result["commands"] == [
        "nvidia-smi -i 0 -pl 300",
        "lact-api /run/lactd.sock batch-set-clocks gpu_index:0",
    ]


def test_lact_offsets_run_after_nvidia_clock_controls() -> None:
    wrapper = load_wrapper()
    events: list[str] = []

    def fake_run_commands(commands: list[list[str]]) -> None:
        events.extend(wrapper["format_command"](command) for command in commands)

    def fake_lact_request(command: str, args: dict[str, Any] | None = None) -> object:
        events.append(command)
        if command == "list_devices":
            return [{"id": "gpu0", "device_type": "Dedicated"}]
        return {}

    def fake_sleep(seconds: float) -> None:
        events.append(f"sleep {seconds:g}")

    patch_wrapper_global(wrapper, "run_commands", fake_run_commands)
    patch_wrapper_global(wrapper, "lact_request", fake_lact_request)
    patch_wrapper_global(wrapper, "time", type("FakeTime", (), {"sleep": fake_sleep}))

    wrapper["apply_profile"](
        {
            "profiles": {
                "training": {
                    "power_limit_watts": 300,
                    "graphics_clocks_mhz": {
                        "min": 0,
                        "max": 1800,
                    },
                    "gpu_clock_offsets": {"0": -100},
                }
            }
        },
        "training",
    )

    assert events == [
        "nvidia-smi -i 0 -pl 300",
        "nvidia-smi -i 0 -lgc 0,1800",
        "list_devices",
        "batch_set_clocks_value",
        "confirm_pending_config",
        "sleep 1",
        "nvidia-smi -i 0 -pl 300",
    ]


def test_nvidia_failure_stops_before_lact_offsets() -> None:
    wrapper = load_wrapper()
    lact_called = False

    def fake_run_commands(commands: list[list[str]]) -> None:
        raise wrapper["ConfigError"]("nvidia failed")

    def fake_lact_request(command: str, args: dict[str, Any] | None = None) -> object:
        nonlocal lact_called
        lact_called = True
        return {}

    patch_wrapper_global(wrapper, "run_commands", fake_run_commands)
    patch_wrapper_global(wrapper, "lact_request", fake_lact_request)

    with pytest.raises(wrapper["ConfigError"], match="nvidia failed"):
        wrapper["apply_profile"](
            {
                "profiles": {
                    "training": {
                        "power_limit_watts": 300,
                        "gpu_clock_offsets": {"0": -100},
                    }
                }
            },
            "training",
        )

    assert lact_called is False


def test_lact_offsets_use_batch_set_clocks_value() -> None:
    wrapper = load_wrapper()
    requests: list[tuple[str, dict[str, Any] | None]] = []

    def fake_lact_request(command: str, args: dict[str, Any] | None = None) -> object:
        requests.append((command, args))
        return None

    patch_wrapper_global(wrapper, "lact_request", fake_lact_request)

    warnings = wrapper["apply_lact_offsets"](
        {
            "gpu_index": 0,
            "lact_device_id": "10DE:2704-1462:5110-0000:09:00.0",
            "gpu_clock_offsets": {0: -100},
            "mem_clock_offsets": {0: 200},
        }
    )

    assert warnings == []
    assert requests == [
        (
            "batch_set_clocks_value",
            {
                "id": "10DE:2704-1462:5110-0000:09:00.0",
                "commands": [
                    {"type": {"gpu_clock_offset": 0}, "value": -100},
                    {"type": {"mem_clock_offset": 0}, "value": 200},
                ],
            },
        ),
        ("confirm_pending_config", {"command": "confirm"}),
    ]


def test_lact_device_resolution_prefers_dedicated_devices() -> None:
    wrapper = load_wrapper()

    def fake_lact_request(command: str, args: dict[str, Any] | None = None) -> object:
        assert command == "list_devices"
        return [
            {
                "id": "1002:13C0-1849:364E-0000:7a:00.0",
                "name": "Granite Ridge [Radeon Graphics]",
                "device_type": "Integrated",
            },
            {
                "id": "10DE:2BB1-10DE:204B-0000:01:00.0",
                "name": "NVIDIA RTX PRO 6000 Blackwell Workstation Edition",
                "device_type": "Dedicated",
            },
        ]

    patch_wrapper_global(wrapper, "lact_request", fake_lact_request)

    assert (
        wrapper["resolve_lact_device_id"]({"gpu_index": 0, "lact_device_id": None})
        == "10DE:2BB1-10DE:204B-0000:01:00.0"
    )
