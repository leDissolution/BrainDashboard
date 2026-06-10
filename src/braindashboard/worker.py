from __future__ import annotations

import asyncio
import signal
from contextlib import suppress

from braindashboard.core.config import get_settings
from braindashboard.db.session import AsyncSessionMaker
from braindashboard.scheduler.service import SchedulerService


async def run_scheduler_worker() -> None:
    settings = get_settings()
    if not settings.scheduler_enabled or settings.scheduler_process_mode != "offprocess":
        return

    scheduler = SchedulerService(sessionmaker=AsyncSessionMaker, settings=settings)
    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for signal_number in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError):
            loop.add_signal_handler(signal_number, stop_event.set)

    await scheduler.start()
    try:
        await stop_event.wait()
    finally:
        await scheduler.stop()


def main() -> None:
    asyncio.run(run_scheduler_worker())


if __name__ == "__main__":
    main()
