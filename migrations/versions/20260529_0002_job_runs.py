"""Create job run and event tables.

Revision ID: 20260529_0002
Revises: 20260526_0001
Create Date: 2026-05-29
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260529_0002"
down_revision: str | None = "20260526_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_runs",
        sa.Column("id", sa.String(length=80), nullable=False),
        sa.Column("definition_id", sa.String(length=120), nullable=False),
        sa.Column("state", sa.String(length=40), nullable=False),
        sa.Column("priority", sa.String(length=20), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("effective_parameters", sa.JSON(), nullable=False),
        sa.Column("effective_command", sa.JSON(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=True),
        sa.Column("external_id", sa.String(length=200), nullable=True),
        sa.Column("log_stdout_path", sa.String(length=1000), nullable=True),
        sa.Column("log_stderr_path", sa.String(length=1000), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("failure_summary", sa.JSON(), nullable=True),
        sa.Column(
            "queued_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("admitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["definition_id"], ["job_definitions.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_runs_definition_id", "job_runs", ["definition_id"])
    op.create_index("ix_job_runs_priority", "job_runs", ["priority"])
    op.create_index("ix_job_runs_queued_at", "job_runs", ["queued_at"])
    op.create_index("ix_job_runs_state", "job_runs", ["state"])

    op.create_table(
        "job_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=80), nullable=False),
        sa.Column("event_id", sa.String(length=200), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=True),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stream", sa.String(length=20), nullable=False),
        sa.Column("line_number", sa.Integer(), nullable=False),
        sa.Column("phase", sa.String(length=200), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("progress", sa.JSON(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=False),
        sa.Column("artifacts", sa.JSON(), nullable=False),
        sa.Column("error", sa.JSON(), nullable=True),
        sa.Column("event_metadata", sa.JSON(), nullable=False),
        sa.Column("raw_payload", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["run_id"], ["job_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_job_events_created_at", "job_events", ["created_at"])
    op.create_index("ix_job_events_event_id", "job_events", ["event_id"])
    op.create_index("ix_job_events_run_id", "job_events", ["run_id"])
    op.create_index("ix_job_events_sequence", "job_events", ["sequence"])
    op.create_index("ix_job_events_type", "job_events", ["type"])


def downgrade() -> None:
    op.drop_index("ix_job_events_type", table_name="job_events")
    op.drop_index("ix_job_events_sequence", table_name="job_events")
    op.drop_index("ix_job_events_run_id", table_name="job_events")
    op.drop_index("ix_job_events_event_id", table_name="job_events")
    op.drop_index("ix_job_events_created_at", table_name="job_events")
    op.drop_table("job_events")
    op.drop_index("ix_job_runs_state", table_name="job_runs")
    op.drop_index("ix_job_runs_queued_at", table_name="job_runs")
    op.drop_index("ix_job_runs_priority", table_name="job_runs")
    op.drop_index("ix_job_runs_definition_id", table_name="job_runs")
    op.drop_table("job_runs")