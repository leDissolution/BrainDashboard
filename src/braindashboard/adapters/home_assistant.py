from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HomeAssistantPowerSignals:
    solar_power_w: float | None = None
    battery_percent: float | None = None
    grid_power_w: float | None = None
    allow_low_priority_compute: bool | None = None


class HomeAssistantAdapter:
    def __init__(self, base_url: str, token: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    async def fetch_power_signals(self) -> HomeAssistantPowerSignals:
        raise NotImplementedError("Home Assistant signal mapping is not implemented yet.")
