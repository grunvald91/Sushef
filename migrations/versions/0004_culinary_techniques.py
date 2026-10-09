"""Source-based professional cooking techniques.

Revision ID: 0004_techniques
Revises: 0003_cuisines
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sushef.technique_catalog import TECHNIQUES, as_row, validate_techniques

revision = "0004_techniques"
down_revision = "0003_cuisines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    validate_techniques()
    conn = op.get_bind()
    if not sa.inspect(conn).has_table("culinary_techniques"):
        op.create_table(
            "culinary_techniques",
            sa.Column("id", sa.String(40), primary_key=True),
            sa.Column("revision", sa.String(20), nullable=False),
            sa.Column("title", sa.String(180), nullable=False),
            sa.Column("category", sa.String(30), nullable=False),
            sa.Column("cuisine_scope", sa.JSON, nullable=False),
            sa.Column("tags", sa.JSON, nullable=False),
            sa.Column("equipment", sa.JSON, nullable=False),
            sa.Column("outcome", sa.Text, nullable=False),
            sa.Column("mechanism", sa.Text, nullable=False),
            sa.Column("controls", sa.JSON, nullable=False),
            sa.Column("cues", sa.JSON, nullable=False),
            sa.Column("problems", sa.JSON, nullable=False),
            sa.Column("limits", sa.Text, nullable=False),
            sa.Column("source_publisher", sa.String(200), nullable=False),
            sa.Column("source_title", sa.String(200), nullable=False),
            sa.Column("source_url", sa.String(600), nullable=False),
            sa.Column("reviewed_on", sa.String(10), nullable=False),
            sa.Column("evidence", sa.String(40), nullable=False),
        )
        op.create_index(
            "ix_culinary_techniques_category", "culinary_techniques", ["category"]
        )

    technique_table = sa.table(
        "culinary_techniques",
        sa.column("id", sa.String),
        sa.column("revision", sa.String),
        sa.column("title", sa.String),
        sa.column("category", sa.String),
        sa.column("cuisine_scope", sa.JSON),
        sa.column("tags", sa.JSON),
        sa.column("equipment", sa.JSON),
        sa.column("outcome", sa.Text),
        sa.column("mechanism", sa.Text),
        sa.column("controls", sa.JSON),
        sa.column("cues", sa.JSON),
        sa.column("problems", sa.JSON),
        sa.column("limits", sa.Text),
        sa.column("source_publisher", sa.String),
        sa.column("source_title", sa.String),
        sa.column("source_url", sa.String),
        sa.column("reviewed_on", sa.String),
        sa.column("evidence", sa.String),
    )
    existing = set(conn.execute(sa.select(technique_table.c.id)).scalars())
    for item in TECHNIQUES:
        if item["id"] not in existing:
            conn.execute(technique_table.insert().values(**as_row(item)))


def downgrade() -> None:
    raise RuntimeError(
        "Схему и редакционные данные нельзя удалять автоматически. Используйте проверенный бэкап."
    )
