"""Create hardware telemetry tables.

Revision ID: 20260529_0003
Revises: 20260529_0002
Create Date: 2026-05-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260529_0003"
down_revision: str | None = "20260529_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hardware_sample_buckets",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bucket_seconds", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("device_key", sa.String(length=80), nullable=False),
        sa.Column("device_name", sa.String(length=200), nullable=True),
        sa.Column("run_id", sa.String(length=80), nullable=True),
        sa.Column("sample_count", sa.Integer(), nullable=False),
        sa.Column("missing_sample_count", sa.Integer(), nullable=False),
        sa.Column("observed_seconds", sa.Float(), nullable=False),
        sa.Column("cpu_percent_avg", sa.Float(), nullable=True),
        sa.Column("cpu_percent_min", sa.Float(), nullable=True),
        sa.Column("cpu_percent_max", sa.Float(), nullable=True),
        sa.Column("memory_percent_avg", sa.Float(), nullable=True),
        sa.Column("memory_percent_min", sa.Float(), nullable=True),
        sa.Column("memory_percent_max", sa.Float(), nullable=True),
        sa.Column("gpu_utilization_percent_avg", sa.Float(), nullable=True),
        sa.Column("gpu_utilization_percent_min", sa.Float(), nullable=True),
        sa.Column("gpu_utilization_percent_max", sa.Float(), nullable=True),
        sa.Column("vram_used_mib_avg", sa.Float(), nullable=True),
        sa.Column("vram_used_mib_min", sa.Float(), nullable=True),
        sa.Column("vram_used_mib_max", sa.Float(), nullable=True),
        sa.Column("vram_total_mib_avg", sa.Float(), nullable=True),
        sa.Column("temperature_c_avg", sa.Float(), nullable=True),
        sa.Column("temperature_c_min", sa.Float(), nullable=True),
        sa.Column("temperature_c_max", sa.Float(), nullable=True),
        sa.Column("power_draw_w_avg", sa.Float(), nullable=True),
        sa.Column("power_draw_w_min", sa.Float(), nullable=True),
        sa.Column("power_draw_w_max", sa.Float(), nullable=True),
        sa.Column("energy_kwh", sa.Float(), nullable=True),
        sa.Column("cost_amount", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["job_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "bucket_start",
            "bucket_seconds",
            "scope",
            "device_key",
            name="uq_hardware_sample_bucket_device",
        ),
    )
    op.create_index(
        "ix_hardware_sample_buckets_bucket_seconds",
        "hardware_sample_buckets",
        ["bucket_seconds"],
    )
    op.create_index(
        "ix_hardware_sample_buckets_bucket_start",
        "hardware_sample_buckets",
        ["bucket_start"],
    )
    op.create_index(
        "ix_hardware_sample_buckets_device_key",
        "hardware_sample_buckets",
        ["device_key"],
    )
    op.create_index("ix_hardware_sample_buckets_run_id", "hardware_sample_buckets", ["run_id"])
    op.create_index("ix_hardware_sample_buckets_scope", "hardware_sample_buckets", ["scope"])

    op.create_table(
        "job_hardware_usage",
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("bucket_count", sa.Integer(), nullable=False),
        sa.Column("host_sample_count", sa.Integer(), nullable=False),
        sa.Column("gpu_sample_count", sa.Integer(), nullable=False),
        sa.Column("gpu_energy_kwh", sa.Float(), nullable=False),
        sa.Column("estimated_cost_amount", sa.Float(), nullable=True),
        sa.Column("cpu_percent_avg", sa.Float(), nullable=True),
        sa.Column("gpu_utilization_percent_avg", sa.Float(), nullable=True),
        sa.Column("gpu_power_draw_w_avg", sa.Float(), nullable=True),
        sa.Column("first_bucket_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_bucket_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["job_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id"),
    )


def downgrade() -> None:
    op.drop_table("job_hardware_usage")
    op.drop_index("ix_hardware_sample_buckets_scope", table_name="hardware_sample_buckets")
    op.drop_index("ix_hardware_sample_buckets_run_id", table_name="hardware_sample_buckets")
    op.drop_index("ix_hardware_sample_buckets_device_key", table_name="hardware_sample_buckets")
    op.drop_index("ix_hardware_sample_buckets_bucket_start", table_name="hardware_sample_buckets")
    op.drop_index("ix_hardware_sample_buckets_bucket_seconds", table_name="hardware_sample_buckets")
    op.drop_table("hardware_sample_buckets")
