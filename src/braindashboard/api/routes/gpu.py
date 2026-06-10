from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict

from braindashboard.collectors.gpu_profiles import (
    GpuProfileCommandError,
    GpuProfileCommandStatus,
    GpuProfileManager,
)
from braindashboard.core.config import get_settings

router = APIRouter(prefix="/gpu", tags=["gpu"])

gpu_profile_manager = GpuProfileManager.from_settings(get_settings())


class ClockRangeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    min: int
    max: int


class GpuProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    label: str
    description: str
    gpu_index: int
    lact_device_id: str | None
    power_limit_watts: int | None
    persistence_mode: bool | None
    graphics_clocks_mhz: ClockRangeResponse | None
    reset_graphics_clocks: bool
    memory_clocks_mhz: ClockRangeResponse | None
    reset_memory_clocks: bool
    gpu_clock_offsets: dict[int, int] | None
    mem_clock_offsets: dict[int, int] | None


class GpuProfilesResponse(BaseModel):
    profiles: list[GpuProfileResponse]


class GpuProfileCommandResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: GpuProfileCommandStatus
    profile_name: str | None
    detail: str
    commands: list[str]
    warnings: list[str]


@router.get("/profiles")
async def gpu_profiles() -> GpuProfilesResponse:
    try:
        profiles = gpu_profile_manager.list_profiles()
    except GpuProfileCommandError as error:
        raise HTTPException(status_code=503, detail=error.reason) from error

    return GpuProfilesResponse(
        profiles=[GpuProfileResponse.model_validate(profile) for profile in profiles]
    )


@router.post("/profiles/{profile_name}/apply")
async def apply_gpu_profile(profile_name: str) -> GpuProfileCommandResponse:
    try:
        result = gpu_profile_manager.apply_profile(profile_name)
    except GpuProfileCommandError as error:
        raise HTTPException(status_code=400, detail=error.reason) from error

    return GpuProfileCommandResponse.model_validate(result)


@router.post("/reset")
async def reset_gpu_clocks() -> GpuProfileCommandResponse:
    try:
        result = gpu_profile_manager.reset()
    except GpuProfileCommandError as error:
        raise HTTPException(status_code=400, detail=error.reason) from error

    return GpuProfileCommandResponse.model_validate(result)
