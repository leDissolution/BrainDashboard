from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from braindashboard import __version__
from braindashboard.api.routes import gpu, hardware, health, jobs, services
from braindashboard.core.config import Settings, get_settings
from braindashboard.db.session import AsyncSessionMaker
from braindashboard.monitoring.hardware import HardwareMonitorService
from braindashboard.scheduler.service import SchedulerService


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        scheduler: SchedulerService | None = None
        hardware_monitor: HardwareMonitorService | None = None
        if (
            resolved_settings.scheduler_enabled
            and resolved_settings.scheduler_process_mode == "embedded"
        ):
            scheduler = SchedulerService(sessionmaker=AsyncSessionMaker, settings=resolved_settings)
            await scheduler.start()
        if resolved_settings.hardware_monitor_enabled:
            hardware_monitor = HardwareMonitorService(
                sessionmaker=AsyncSessionMaker,
                settings=resolved_settings,
            )
            await hardware_monitor.start()
        try:
            yield
        finally:
            if hardware_monitor is not None:
                await hardware_monitor.stop()
            if scheduler is not None:
                await scheduler.stop()

    app = FastAPI(
        title=resolved_settings.app_name,
        version=__version__,
        debug=resolved_settings.debug,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(hardware.router, prefix="/api")
    app.include_router(gpu.router, prefix="/api")
    app.include_router(health.router, prefix="/api")
    app.include_router(jobs.router, prefix="/api")
    app.include_router(services.router, prefix="/api")

    @app.get("/", include_in_schema=False)
    async def root() -> dict[str, str]:
        return {"service": "braindashboard", "status": "ok"}

    return app


app = create_app()
