"""Introduce versioned baseline and user's explicit culinary memory.

Migration supports an existing pre-Alembic SQLite/PostgreSQL database
(with tables created by Base.metadata.create_all). No old user data is dropped.

Revision ID: 0001_memory
Revises:
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

from sushef.models import Base

revision = "0001_memory"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # On a fresh DB create the entire schema. Existing tables are kept as-is.
    # New recipe_archive and personal_memories are created if missing.
    Base.metadata.create_all(bind=conn, checkfirst=True)

    # Existing pre-Alembic fermentation_batches tables lacked these two columns.
    inspector = sa.inspect(conn)
    if inspector.has_table("fermentation_batches"):
        columns = {x["name"] for x in inspector.get_columns("fermentation_batches")}
        if "protocol_id" not in columns:
            op.add_column(
                "fermentation_batches",
                sa.Column("protocol_id", sa.String(64), nullable=False,
                          server_default=""),
            )
        if "protocol_revision" not in columns:
            op.add_column(
                "fermentation_batches",
                sa.Column("protocol_revision", sa.String(32), nullable=False,
                          server_default=""),
            )

    # Preserve the current unsaved recipe from an existing v0.x profile.
    # Favorites remain independent; new generations auto-archive in storage.py.
    users = sa.table("users", sa.column("id", sa.BigInteger),
                     sa.column("last_recipe", sa.JSON))
    archive = sa.table(
        "recipe_archive", sa.column("user_id", sa.BigInteger),
        sa.column("recipe", sa.JSON), sa.column("origin", sa.String(32)),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    rows = conn.execute(
        sa.select(users.c.id, users.c.last_recipe).where(users.c.last_recipe.is_not(None))
    )
    for owner, recipe in rows:
        if isinstance(recipe, dict):
            conn.execute(archive.insert().values(
                user_id=owner, recipe=recipe, origin="legacy_last",
                created_at=sa.func.now()
            ))


def downgrade() -> None:
    # Destructive downgrade is intentionally disabled to preserve personal data.
    raise RuntimeError("Downgrade запрещён: сохраните данные и используйте восстановление бэкапа")
