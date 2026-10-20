"""Support tickets and Telegram Stars access: additive tables only.

Revision ID: 0006_support_billing
Revises: 0005_prod_cards
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0006_support_billing"
down_revision = "0005_prod_cards"
branch_labels = None
depends_on = None


def _created_at() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                     server_default=sa.func.current_timestamp())


def upgrade() -> None:
    # Existing tables are not modified; local create_all installations may
    # already have some of these tables, so every step is skip-if-present.
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "support_admins" not in existing:
        op.create_table(
            "support_admins",
            sa.Column("user_id", sa.BigInteger, primary_key=True, autoincrement=False),
            sa.Column("username", sa.String(64), nullable=False),
            sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.current_timestamp()),
        )
    if "support_tickets" not in existing:
        op.create_table(
            "support_tickets",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.BigInteger, nullable=False),
            sa.Column("chat_id", sa.BigInteger, nullable=False),
            sa.Column("status", sa.String(12), nullable=False, server_default="open"),
            _created_at(),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.current_timestamp()),
        )
        op.create_index("ix_support_tickets_user_id", "support_tickets", ["user_id"])
        op.create_index("ix_support_tickets_status", "support_tickets", ["status"])
    if "support_messages" not in existing:
        op.create_table(
            "support_messages",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("ticket_id", sa.Integer,
                      sa.ForeignKey("support_tickets.id", ondelete="CASCADE"), nullable=False),
            sa.Column("user_id", sa.BigInteger, nullable=False),
            sa.Column("sender", sa.String(12), nullable=False),
            sa.Column("text", sa.Text, nullable=False),
            _created_at(),
        )
        op.create_index("ix_support_messages_ticket_id", "support_messages", ["ticket_id"])
        op.create_index("ix_support_messages_user_id", "support_messages", ["user_id"])
    if "subscriptions" not in existing:
        op.create_table(
            "subscriptions",
            sa.Column("user_id", sa.BigInteger, primary_key=True, autoincrement=False),
            sa.Column("paid_until_ts", sa.BigInteger, nullable=False, server_default="0"),
            sa.Column("trial_used", sa.Integer, nullable=False, server_default="0"),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                      server_default=sa.func.current_timestamp()),
        )
    if "star_payments" not in existing:
        op.create_table(
            "star_payments",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("user_id", sa.BigInteger, nullable=False),
            sa.Column("charge_id", sa.String(200), nullable=False, unique=True),
            sa.Column("provider_charge_id", sa.String(200), nullable=False, server_default=""),
            sa.Column("amount", sa.Integer, nullable=False),
            sa.Column("currency", sa.String(8), nullable=False),
            sa.Column("days", sa.Integer, nullable=False),
            sa.Column("status", sa.String(12), nullable=False, server_default="paid"),
            _created_at(),
        )
        op.create_index("ix_star_payments_user_id", "star_payments", ["user_id"])


def downgrade() -> None:
    raise RuntimeError(
        "Не удаляйте платежи и обращения: для отката кода выполните "
        "`alembic stamp 0005_prod_cards` (таблицы аддитивные) или восстановите резервную копию"
    )
