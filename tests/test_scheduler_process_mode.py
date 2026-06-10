from __future__ import annotations

from braindashboard import main as main_module
from braindashboard.core.config import Settings


class FakeSchedulerService:
    starts = 0
    stops = 0

    def __init__(self, **_kwargs: object) -> None:
        pass

    async def start(self) -> None:
        type(self).starts += 1

    async def stop(self) -> None:
        type(self).stops += 1


async def test_api_lifespan_starts_scheduler_when_embedded(
    monkeypatch,
) -> None:
    FakeSchedulerService.starts = 0
    FakeSchedulerService.stops = 0
    monkeypatch.setattr(main_module, "SchedulerService", FakeSchedulerService)

    app = main_module.create_app(
        Settings(
            scheduler_enabled=True,
            scheduler_process_mode="embedded",
            hardware_monitor_enabled=False,
        )
    )

    async with app.router.lifespan_context(app):
        assert FakeSchedulerService.starts == 1

    assert FakeSchedulerService.stops == 1


async def test_api_lifespan_skips_scheduler_when_offprocess(
    monkeypatch,
) -> None:
    FakeSchedulerService.starts = 0
    FakeSchedulerService.stops = 0
    monkeypatch.setattr(main_module, "SchedulerService", FakeSchedulerService)

    app = main_module.create_app(
        Settings(
            scheduler_enabled=True,
            scheduler_process_mode="offprocess",
            hardware_monitor_enabled=False,
        )
    )

    async with app.router.lifespan_context(app):
        assert FakeSchedulerService.starts == 0

    assert FakeSchedulerService.stops == 0
