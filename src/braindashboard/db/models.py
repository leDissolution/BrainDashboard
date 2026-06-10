from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from braindashboard.db.base import Base


class JobDefinitionRecord(Base):
    __tablename__ = "job_definitions"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    execution_mode: Mapped[str] = mapped_column(String(40), nullable=False)
    command: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    working_directory: Mapped[str | None] = mapped_column(String(500), nullable=True)
    image: Mapped[str | None] = mapped_column(String(500), nullable=True)
    default_priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    event_contract: Mapped[str] = mapped_column(
        String(40), nullable=False, default="structured_stdout"
    )
    resource_hints: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    retry_policy: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    parameters: Mapped[list[JobParameterRecord]] = relationship(
        back_populates="definition",
        cascade="all, delete-orphan",
        order_by="JobParameterRecord.position",
    )
    runs: Mapped[list[JobRunRecord]] = relationship(back_populates="definition")


class JobParameterRecord(Base):
    __tablename__ = "job_parameters"
    __table_args__ = (UniqueConstraint("definition_id", "name", name="uq_job_parameter_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    definition_id: Mapped[str] = mapped_column(
        ForeignKey("job_definitions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    value_type: Mapped[str] = mapped_column(String(40), nullable=False)
    cli_flag: Mapped[str] = mapped_column(String(120), nullable=False)
    default_value: Mapped[object | None] = mapped_column(JSON, nullable=True)
    required_at_queue: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    allow_queue_override: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    choices: Mapped[list[str]] = mapped_column(JSON, nullable=False)

    definition: Mapped[JobDefinitionRecord] = relationship(back_populates="parameters")


class JobRunRecord(Base):
    __tablename__ = "job_runs"

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    definition_id: Mapped[str] = mapped_column(
        ForeignKey("job_definitions.id"), nullable=False, index=True
    )
    state: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal", index=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    effective_parameters: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    effective_command: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    timeout_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    log_stdout_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    log_stderr_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    failure_summary: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )
    admitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    definition: Mapped[JobDefinitionRecord] = relationship(back_populates="runs")
    events: Mapped[list[JobEventRecord]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="JobEventRecord.created_at",
    )
    hardware_usage: Mapped[JobHardwareUsageRecord | None] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
    )


class JobEventRecord(Base):
    __tablename__ = "job_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("job_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    sequence: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stream: Mapped[str] = mapped_column(String(20), nullable=False)
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    phase: Mapped[str | None] = mapped_column(String(200), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    progress: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    metrics: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    artifacts: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False)
    error: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True)
    event_metadata: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    raw_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    run: Mapped[JobRunRecord] = relationship(back_populates="events")


class HardwareSampleBucketRecord(Base):
    __tablename__ = "hardware_sample_buckets"
    __table_args__ = (
        UniqueConstraint(
            "bucket_start",
            "bucket_seconds",
            "scope",
            "device_key",
            name="uq_hardware_sample_bucket_device",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    bucket_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=60, index=True)
    scope: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    device_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    device_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("job_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    missing_sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    observed_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    cpu_percent_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu_percent_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu_percent_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_percent_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_percent_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    memory_percent_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpu_utilization_percent_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpu_utilization_percent_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpu_utilization_percent_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    vram_used_mib_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    vram_used_mib_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    vram_used_mib_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    vram_total_mib_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_c_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_c_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    temperature_c_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    power_draw_w_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    power_draw_w_min: Mapped[float | None] = mapped_column(Float, nullable=True)
    power_draw_w_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    energy_kwh: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class JobHardwareUsageRecord(Base):
    __tablename__ = "job_hardware_usage"

    run_id: Mapped[str] = mapped_column(
        ForeignKey("job_runs.id", ondelete="CASCADE"), primary_key=True
    )
    bucket_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    host_sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gpu_sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gpu_energy_kwh: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    estimated_cost_amount: Mapped[float | None] = mapped_column(Float, nullable=True)
    cpu_percent_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpu_utilization_percent_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    gpu_power_draw_w_avg: Mapped[float | None] = mapped_column(Float, nullable=True)
    first_bucket_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_bucket_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    run: Mapped[JobRunRecord] = relationship(back_populates="hardware_usage")
