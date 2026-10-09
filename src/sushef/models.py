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


class RecipeArchive(Base):
    """Каждый созданный рецепт; избранное остаётся отдельной пользовательской коллекцией."""
    __tablename__ = "recipe_archive"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    recipe: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    origin: Mapped[str] = mapped_column(String(32), default="generated", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PersonalMemory(Base):
    """Подтверждённые пользователем долгосрочные факты и ожидающие подтверждения."""
    __tablename__ = "personal_memories"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="pending")
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="explicit_user")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)



class CuisineRecipe(Base):
    """Shared editorial catalog, not owned by or inferred from a user."""
    __tablename__ = "cuisine_recipes"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    cuisine: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    cuisine_label: Mapped[str] = mapped_column(String(80), nullable=False)
    region: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    servings: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ingredients: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    method: Mapped[str] = mapped_column(Text, nullable=False)
    publisher: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str] = mapped_column(String(600), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    reviewed_on: Mapped[str] = mapped_column(String(10), nullable=False)
    tags: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)



class CulinaryTechnique(Base):
    """Editorial culinary technique: source, mechanism, cues, troubleshooting."""
    __tablename__ = "culinary_techniques"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    revision: Mapped[str] = mapped_column(String(20), nullable=False)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    category: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    cuisine_scope: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    equipment: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    mechanism: Mapped[str] = mapped_column(Text, nullable=False)
    controls: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    cues: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    problems: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False)
    limits: Mapped[str] = mapped_column(Text, nullable=False)
    source_publisher: Mapped[str] = mapped_column(String(200), nullable=False)
    source_title: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str] = mapped_column(String(600), nullable=False)
    reviewed_on: Mapped[str] = mapped_column(String(10), nullable=False)
    evidence: Mapped[str] = mapped_column(String(40), nullable=False)



class DishProcessCard(Base):
    """Quantified recipe plan linked to a separately sourced cuisine recipe."""
    __tablename__ = "dish_process_cards"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    recipe_id: Mapped[str] = mapped_column(String(40), ForeignKey("cuisine_recipes.id"), index=True, nullable=False)
    revision: Mapped[str] = mapped_column(String(20), nullable=False)
    servings: Mapped[int] = mapped_column(Integer, nullable=False)
    yield_grams: Mapped[int | None] = mapped_column(Integer, nullable=True)
    equipment: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    ingredients: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False)
    stages: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    source_url: Mapped[str] = mapped_column(String(600), nullable=False)
    source_publisher: Mapped[str] = mapped_column(String(200), nullable=False)
    source_note: Mapped[str] = mapped_column(Text, nullable=False)
    technique_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    reviewed_on: Mapped[str] = mapped_column(String(10), nullable=False)


class CookingTimer(Base):
    """Persistent Telegram timer. Background worker resumes after process restarts.

    The lease-based dispatcher is at-least-once: a crash between Telegram send
    and status update can result in a duplicate notification, not a lost timer.
    """
    __tablename__ = "cooking_timers"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    recipe_title: Mapped[str] = mapped_column(String(180), nullable=False)
    step_index: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    due_at_ts: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(16), index=True, default="active", nullable=False)
    lease_until_ts: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    retry_at_ts: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
