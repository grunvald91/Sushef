"""Add optional audited-production metadata and immutable version 2 cards.

Revision ID: 0005_prod_cards
Revises: 0004_techniques
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from sushef.dish_process_cards_v2 import V2_DISH_CARDS, as_row_v2, validate_v2_cards

revision = "0005_prod_cards"
down_revision = "0004_techniques"
branch_labels = None
depends_on = None


def upgrade() -> None:
    validate_v2_cards()
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if not insp.has_table("dish_process_cards"):
        raise RuntimeError("Отсутствует базовая таблица dish_process_cards")
    existing_columns = {col["name"] for col in insp.get_columns("dish_process_cards")}
    if "production_spec" not in existing_columns:
        op.add_column(
            "dish_process_cards", sa.Column("production_spec", sa.JSON(), nullable=True)
        )
    table = sa.table(
        "dish_process_cards",
        sa.column("id", sa.String(40)),
        sa.column("recipe_id", sa.String(40)),
        sa.column("revision", sa.String(20)),
        sa.column("servings", sa.Integer()),
        sa.column("yield_grams", sa.Integer()),
        sa.column("equipment", sa.JSON()),
        sa.column("ingredients", sa.JSON()),
        sa.column("stages", sa.JSON()),
        sa.column("source_url", sa.String(600)),
        sa.column("source_publisher", sa.String(200)),
        sa.column("source_note", sa.Text()),
        sa.column("technique_ids", sa.JSON()),
        sa.column("reviewed_on", sa.String(10)),
        sa.column("production_spec", sa.JSON()),
    )
    existing_ids = set(conn.execute(sa.select(table.c.id)).scalars())
    for item in V2_DISH_CARDS:
        if item["id"] not in existing_ids:
            conn.execute(table.insert().values(**as_row_v2(item)))


def downgrade() -> None:
    raise RuntimeError(
        "Versioned production cards must not be deleted automatically. "
        "Restore a validated backup if a rollback is required."
    )
