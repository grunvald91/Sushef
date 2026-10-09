"""Persistent cooking timers with delivery leases.

Revision ID: 0002_timers
Revises: 0001_memory
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002_timers"
down_revision = "0001_memory"
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # Existing local installations may already have created the table through
    # Base.metadata.create_all; do not touch or wipe such user-owned records.
    if sa.inspect(conn).has_table("cooking_timers"):
        return
    op.create_table(
        "cooking_timers",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger, nullable=False),
        sa.Column("chat_id", sa.BigInteger, nullable=False),
        sa.Column("recipe_title", sa.String(180), nullable=False),
        sa.Column("step_index", sa.Integer, nullable=False),
        sa.Column("label", sa.String(120), nullable=False),
        sa.Column("minutes", sa.Integer, nullable=False),
        sa.Column("due_at_ts", sa.BigInteger, nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("lease_until_ts", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("retry_at_ts", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.current_timestamp()),
    )
    op.create_index("ix_cooking_timers_user_id", "cooking_timers", ["user_id"])
    op.create_index("ix_cooking_timers_due_at_ts", "cooking_timers", ["due_at_ts"])
    op.create_index("ix_cooking_timers_status", "cooking_timers", ["status"])


def downgrade() -> None:
    raise RuntimeError("Не удаляйте живые таймеры: восстановите резервную копию при откате")
