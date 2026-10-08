from datetime import datetime, timezone
from typing import Any

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    mode: Mapped[str] = mapped_column(String(32), default="ask", nullable=False)
    preferences: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    last_recipe: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    usage_day: Mapped[str] = mapped_column(String(10), default="", nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Favorite(Base):
    __tablename__ = "favorites"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    recipe: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CookingSession(Base):
    __tablename__ = "cooking_sessions"
    user_id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    recipe: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PantryItem(Base):
    __tablename__ = "pantry_items"
    __table_args__ = (UniqueConstraint("user_id", "name_key", "unit"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    name_key: Mapped[str] = mapped_column(String(90), nullable=False)
    display_name: Mapped[str] = mapped_column(String(90), nullable=False)
    unit: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[str] = mapped_column(String(40), nullable=False)


class WeeklyPlan(Base):
    __tablename__ = "weekly_plans"
    user_id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    plan: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class RecipeFeedback(Base):
    __tablename__ = "recipe_feedback"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    recipe_title: Mapped[str] = mapped_column(String(180), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FermentationBatch(Base):
    __tablename__ = "fermentation_batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    category: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    protocol_source: Mapped[str] = mapped_column(String(240), default="", nullable=False)
    protocol_id: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    protocol_revision: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    finished: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FermentationReading(Base):
    __tablename__ = "fermentation_readings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    batch_id: Mapped[int] = mapped_column(Integer, ForeignKey("fermentation_batches.id"), index=True, nullable=False)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    temperature_c: Mapped[str | None] = mapped_column(String(16), nullable=True)
    ph: Mapped[str | None] = mapped_column(String(16), nullable=True)
    note: Mapped[str] = mapped_column(String(500), default="", nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
