from __future__ import annotations

from fastapi.testclient import TestClient

from braindashboard.api.routes import gpu
from braindashboard.collectors.gpu_profiles import (
    ClockRange,
    GpuProfileCommandResult,
    GpuProfileDefinition,
)
from braindashboard.core.config import Settings
from braindashboard.main import create_app


def app_with_scheduler_disabled() -> object:
    return create_app(Settings(scheduler_enabled=False, hardware_monitor_enabled=False))


class FakeGpuProfileManager:
    def __init__(self) -> None:
        self.applied_profile: str | None = None
        self.reset_called = False

    def list_profiles(self) -> list[GpuProfileDefinition]:
        return [
            GpuProfileDefinition(
                name="inference-quiet",
                label="Inference Quiet",
                description="Lower power inference profile",
                gpu_index=0,
                lact_device_id=None,
                power_limit_watts=190,
                persistence_mode=True,
                graphics_clocks_mhz=ClockRange(min=900, max=1500),
                reset_graphics_clocks=False,
                memory_clocks_mhz=None,
                reset_memory_clocks=False,
                gpu_clock_offsets={0: -100},
                mem_clock_offsets={0: 200},
            )
        ]

    def apply_profile(self, profile_name: str) -> GpuProfileCommandResult:
        self.applied_profile = profile_name
        return GpuProfileCommandResult(
            status="applied",
            profile_name=profile_name,
            detail=f"Applied {profile_name}",
            commands=["nvidia-smi -i 0 -pl 190"],
            warnings=[],
        )

    def reset(self) -> GpuProfileCommandResult:
        self.reset_called = True
        return GpuProfileCommandResult(
            status="reset",
            profile_name=None,
            detail="Reset clocks on GPU 0",
            commands=["nvidia-smi -i 0 -rgc", "nvidia-smi -i 0 -rmc"],
            warnings=[],
        )


def test_gpu_profiles_endpoint(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fake_manager = FakeGpuProfileManager()
    monkeypatch.setattr(gpu, "gpu_profile_manager", fake_manager)
    client = TestClient(app_with_scheduler_disabled())

    response = client.get("/api/gpu/profiles")

    assert response.status_code == 200
    body = response.json()
    assert body["profiles"][0]["name"] == "inference-quiet"
    assert body["profiles"][0]["power_limit_watts"] == 190
    assert body["profiles"][0]["graphics_clocks_mhz"] == {"min": 900, "max": 1500}
    assert body["profiles"][0]["gpu_clock_offsets"] == {"0": -100}
    assert body["profiles"][0]["mem_clock_offsets"] == {"0": 200}


def test_apply_gpu_profile_endpoint(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fake_manager = FakeGpuProfileManager()
    monkeypatch.setattr(gpu, "gpu_profile_manager", fake_manager)
    client = TestClient(app_with_scheduler_disabled())

    response = client.post("/api/gpu/profiles/inference-quiet/apply")

    assert response.status_code == 200
    assert fake_manager.applied_profile == "inference-quiet"
    assert response.json()["commands"] == ["nvidia-smi -i 0 -pl 190"]


def test_reset_gpu_profile_endpoint(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    fake_manager = FakeGpuProfileManager()
    monkeypatch.setattr(gpu, "gpu_profile_manager", fake_manager)
    client = TestClient(app_with_scheduler_disabled())

    response = client.post("/api/gpu/reset")

    assert response.status_code == 200
    assert fake_manager.reset_called is True
    assert response.json()["status"] == "reset"
