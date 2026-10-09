"""Add curated cuisine reference cards without touching personal tables.

Revision ID: 0003_cuisines
Revises: 0002_timers
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from sushef.cuisine_catalog import RECIPES, as_row, validate_seed

revision = "0003_cuisines"
down_revision = "0002_timers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    validate_seed()
    conn = op.get_bind()
    if not sa.inspect(conn).has_table("cuisine_recipes"):
        op.create_table(
            "cuisine_recipes",
            sa.Column("id", sa.String(40), primary_key=True),
            sa.Column("cuisine", sa.String(40), nullable=False),
            sa.Column("cuisine_label", sa.String(80), nullable=False),
            sa.Column("region", sa.String(100), nullable=False),
            sa.Column("title", sa.String(180), nullable=False),
            sa.Column("kind", sa.String(20), nullable=False),
            sa.Column("servings", sa.Integer, nullable=True),
            sa.Column("ingredients", sa.JSON, nullable=False),
            sa.Column("method", sa.Text, nullable=False),
            sa.Column("publisher", sa.String(200), nullable=False),
            sa.Column("source_url", sa.String(600), nullable=False),
            sa.Column("source_type", sa.String(40), nullable=False),
            sa.Column("reviewed_on", sa.String(10), nullable=False),
            sa.Column("tags", sa.JSON, nullable=False),
        )
        op.create_index("ix_cuisine_recipes_cuisine", "cuisine_recipes", ["cuisine"])
    table = sa.table(
        "cuisine_recipes",
        sa.column("id", sa.String),
        sa.column("cuisine", sa.String),
        sa.column("cuisine_label", sa.String),
        sa.column("region", sa.String),
        sa.column("title", sa.String),
        sa.column("kind", sa.String),
        sa.column("servings", sa.Integer),
        sa.column("ingredients", sa.JSON),
        sa.column("method", sa.Text),
        sa.column("publisher", sa.String),
        sa.column("source_url", sa.String),
        sa.column("source_type", sa.String),
        sa.column("reviewed_on", sa.String),
        sa.column("tags", sa.JSON),
    )
    # Insert only missing IDs: no destructive overwrite of editorial corrections.
    existing = set(conn.execute(sa.select(table.c.id)).scalars())
    for item in RECIPES:
        if item["id"] not in existing:
            conn.execute(table.insert().values(**as_row(item)))


def downgrade() -> None:
    raise RuntimeError("Не удаляйте каталог автоматически: откат схемы только из проверенного бэкапа")
