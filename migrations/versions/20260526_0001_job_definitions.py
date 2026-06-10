"""Create job definition tables.

Revision ID: 20260526_0001
Revises:
Create Date: 2026-05-26
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260526_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "job_definitions",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("execution_mode", sa.String(length=40), nullable=False),
        sa.Column("command", sa.JSON(), nullable=False),
        sa.Column("working_directory", sa.String(length=500), nullable=True),
        sa.Column("image", sa.String(length=500), nullable=True),
        sa.Column("default_priority", sa.String(length=20), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=True),
        sa.Column("event_contract", sa.String(length=40), nullable=False),
        sa.Column("resource_hints", sa.JSON(), nullable=False),
        sa.Column("retry_policy", sa.JSON(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "job_parameters",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("definition_id", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("label", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("value_type", sa.String(length=40), nullable=False),
        sa.Column("cli_flag", sa.String(length=120), nullable=False),
        sa.Column("default_value", sa.JSON(), nullable=True),
        sa.Column("required_at_queue", sa.Boolean(), nullable=False),
        sa.Column("allow_queue_override", sa.Boolean(), nullable=False),
        sa.Column("choices", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["definition_id"], ["job_definitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("definition_id", "name", name="uq_job_parameter_name"),
    )
    op.create_index("ix_job_parameters_definition_id", "job_parameters", ["definition_id"])


def downgrade() -> None:
    op.drop_index("ix_job_parameters_definition_id", table_name="job_parameters")
    op.drop_table("job_parameters")
    op.drop_table("job_definitions")
