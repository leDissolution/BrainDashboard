from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class ServiceHealth:
    name: str
    status: str
    details: dict[str, object] = field(default_factory=dict)


class ServiceDetailAdapter(Protocol):
    async def collect(self) -> ServiceHealth:
        ...
