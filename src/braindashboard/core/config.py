from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "BrainDashboard"
    environment: str = "development"
    debug: bool = True
    host: str = "127.0.0.1"
    port: int = 9500
    database_url: str = Field(
        default="postgresql+asyncpg://braindashboard:braindashboard@localhost:5432/braindashboard"
    )
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:5175",
            "http://127.0.0.1:5175",
        ]
    )
    llama_swap_base_url: str = "http://127.0.0.1:9292"
    llama_swap_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LLAMA_SWAP_API_KEY", "BRAINDASHBOARD_LLAMA_SWAP_API_KEY"),
    )
    llama_swap_timeout_seconds: float = 3.0
    llama_swap_metrics_window_seconds: int = 300
    vllm_metrics_base_url: str | None = None
    vllm_metrics_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("VLLM_METRICS_API_KEY", "BRAINDASHBOARD_VLLM_METRICS_API_KEY"),
    )
    vllm_metrics_timeout_seconds: float = 3.0
    vllm_metrics_max_samples: int = 720
    gpu_profile_command: str = "sudo -n /usr/local/sbin/braindashboard-gpu-profile"
    gpu_profile_timeout_seconds: float = 15.0
    job_logs_dir: str = "./var/job-runs"
    scheduler_enabled: bool = True
    scheduler_process_mode: Literal["embedded", "offprocess"] = "embedded"
    scheduler_tick_interval_seconds: float = 2.0
    job_max_active_runs: int = 1
    native_cancel_grace_seconds: float = 10.0
    hardware_monitor_enabled: bool = True
    hardware_sample_interval_seconds: float = 1.0
    hardware_bucket_seconds: int = 60
    electricity_cost_per_kwh: float | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="BRAINDASHBOARD_",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
