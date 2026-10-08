from __future__ import annotations

from datetime import datetime, timezone
from time import time
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import Base, Conversation, CookingSession, CookingTimer, Favorite, FermentationBatch, FermentationReading, PantryItem, PersonalMemory, RecipeArchive, RecipeFeedback, User, WeeklyPlan
from .timers import MAX_ACTIVE_TIMERS, MAX_MINUTES, MIN_MINUTES
from .memory import PROFILE_FIELDS, validate_memory, validate_preference


class Storage:
    def __init__(self, database_url: str):
        self.engine = create_async_engine(database_url, pool_pre_ping=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_tables(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()

    async def verify_schema_revision(self, required: str = "0002_timers") -> None:
        """Fail closed when migrations were skipped or the DB is incompatible."""
        try:
            async with self.engine.connect() as conn:
                current = await conn.scalar(text("SELECT version_num FROM alembic_version"))
        except SQLAlchemyError as exc:
            raise RuntimeError(
                "База не подготовлена. Перед запуском выполните alembic upgrade head."
            ) from exc
        if current != required:
            raise RuntimeError(
                f"Несовместимая схема базы: {current!r}. "
                f"Требуется версия {required}. Выполните alembic upgrade head "
                "после создания резервной копии."
            )

    @staticmethod
    async def _user(db: AsyncSession, user_id: int) -> User:
        user = await db.get(User, user_id)
        if user is None:
            user = User(id=user_id, mode="ask", preferences={}, usage_day="", usage_count=0)
            db.add(user)
            await db.flush()
        return user

    async def get_user(self, user_id: int) -> dict[str, Any]:
        async with self.sessions() as db:
            user = await self._user(db, user_id)
            data = {"mode": user.mode, "preferences": dict(user.preferences or {}), "last_recipe": user.last_recipe}
            await db.commit()
            return data

    async def set_mode(self, user_id: int, mode: str) -> None:
        async with self.sessions() as db:
            user = await self._user(db, user_id)
            user.mode = mode
            # Переключение режима НЕ удаляет историю; очистка только через /reset.
            await db.commit()

    async def set_preference(self, user_id: int, key: str, value: str) -> None:
        value = validate_preference(key, value)
        async with self.sessions() as db:
            user = await self._user(db, user_id)
            prefs = dict(user.preferences or {})
            previous = prefs.get(key)
            if value == "-":
                prefs.pop(key, None)
            else:
                prefs[key] = value
            user.preferences = prefs
            # При изменении аллергенов и исключений старый рецепт и текущая готовка
            # больше не считаются подходящими для профиля.
            if key in {"allergens", "excluded"} and previous != prefs.get(key):
                user.last_recipe = None
                await db.execute(update(CookingTimer).where(
                    CookingTimer.user_id == user_id,
                    CookingTimer.status.in_(("active", "sending"))
                ).values(status="cancelled"))
                await db.execute(delete(CookingSession).where(CookingSession.user_id == user_id))
                await db.execute(delete(WeeklyPlan).where(WeeklyPlan.user_id == user_id))
            await db.commit()

    async def get_history(self, user_id: int, limit: int = 10) -> list[dict[str, str]]:
        async with self.sessions() as db:
            result = await db.execute(select(Conversation).where(Conversation.user_id == user_id).order_by(Conversation.id.desc()).limit(limit))
            return [{"role": row.role, "content": row.content} for row in reversed(result.scalars().all())]

    async def add_exchange(self, user_id: int, question: str, reply: str) -> None:
        async with self.sessions() as db:
            db.add_all([Conversation(user_id=user_id, role="user", content=question[:3500]), Conversation(user_id=user_id, role="assistant", content=reply[:6000])])
            await db.flush()
            stale = await db.scalars(select(Conversation.id).where(Conversation.user_id == user_id).order_by(Conversation.id.desc()).offset(40))
            old_ids = list(stale)
            if old_ids:
                await db.execute(delete(Conversation).where(Conversation.id.in_(old_ids)))
            await db.commit()

    async def use_quota(self, user_id: int, daily_limit: int) -> bool:
        """Атомарное резервирование одного запроса к ИИ на календарный день UTC.

        При сбое модели резервирование не возвращается: консервативный контроль
        расходов. SQLite рассчитан на один бот; в PostgreSQL UPDATE выполняется
        атомарно даже при конкурентных задачах.
        """
        today = datetime.now(timezone.utc).date().isoformat()
        async with self.sessions() as db:
            user = await self._user(db, user_id)
            if user.usage_day != today:
                user.usage_day, user.usage_count = today, 0
            await db.flush()
            result = await db.execute(
                update(User)
                .where(User.id == user_id, User.usage_day == today,
                       User.usage_count < daily_limit)
                .values(usage_count=User.usage_count + 1)
                .execution_options(synchronize_session=False)
            )
            allowed = result.rowcount == 1
            await db.commit()
            return allowed

    async def set_recipe(self, user_id: int, recipe: dict[str, Any]) -> None:
        async with self.sessions() as db:
            user = await self._user(db, user_id)
            user.last_recipe = recipe
            await db.execute(delete(CookingSession).where(CookingSession.user_id == user_id))
            # Previous timers belong to the old recipe; stop reminders for it.
            await db.execute(update(CookingTimer).where(
                CookingTimer.user_id == user_id,
                CookingTimer.status.in_(("active", "sending"))
            ).values(status="cancelled"))
            db.add(RecipeArchive(user_id=user_id, recipe=recipe, origin="generated"))
            await db.commit()

    async def save_favorite(self, user_id: int) -> bool:
        async with self.sessions() as db:
            user = await self._user(db, user_id)
            if not user.last_recipe:
                return False
            db.add(Favorite(user_id=user_id, recipe=user.last_recipe))
            await db.commit()
            return True

    async def favorites(self, user_id: int) -> list[dict[str, Any]]:
        async with self.sessions() as db:
            rows = await db.scalars(select(Favorite).where(Favorite.user_id == user_id).order_by(Favorite.id.desc()).limit(10))
            return [{"id": item.id, "recipe": item.recipe} for item in rows]

    async def select_favorite(self, user_id: int, favorite_id: int, activate: bool = True) -> dict[str, Any] | None:
        async with self.sessions() as db:
            favorite = await db.get(Favorite, favorite_id)
            if not favorite or favorite.user_id != user_id:
                return None
            if activate:
                user = await self._user(db, user_id)
                user.last_recipe = favorite.recipe
                await db.execute(update(CookingTimer).where(
                    CookingTimer.user_id == user_id,
                    CookingTimer.status.in_(("active", "sending"))
                ).values(status="cancelled"))
                await db.execute(delete(CookingSession).where(CookingSession.user_id == user_id))
            await db.commit()
            return favorite.recipe

    async def start_cooking(self, user_id: int) -> dict[str, Any] | None:
        async with self.sessions() as db:
            user = await self._user(db, user_id)
            recipe = user.last_recipe
            if not recipe or not recipe.get("steps"):
                return None
            cooking = await db.get(CookingSession, user_id)
            if cooking is None:
                cooking = CookingSession(user_id=user_id, recipe=recipe, step_index=0)
                db.add(cooking)
            elif cooking.recipe != recipe:
                cooking.recipe, cooking.step_index = recipe, 0
                await db.execute(update(CookingTimer).where(
                    CookingTimer.user_id == user_id,
                    CookingTimer.status.in_(("active", "sending"))
                ).values(status="cancelled"))
            # Re-entering cooking for the SAME recipe resumes the last step.
            user.mode = "cook"
            await db.commit()
            return {"recipe": recipe, "step_index": cooking.step_index}

    async def advance_cooking(self, user_id: int) -> dict[str, Any] | None:
        async with self.sessions() as db:
            cooking = await db.get(CookingSession, user_id)
            if not cooking:
                return None
            steps = cooking.recipe.get("steps", [])
            cooking.step_index = min(cooking.step_index + 1, len(steps))
            result = {"recipe": cooking.recipe, "step_index": cooking.step_index}
            if cooking.step_index >= len(steps):
                user = await self._user(db, user_id)
                user.mode = "ask"
                await db.delete(cooking)
            await db.commit()
            return result

    async def current_cooking(self, user_id: int) -> dict[str, Any] | None:
        async with self.sessions() as db:
            cooking = await db.get(CookingSession, user_id)
            return {"recipe": cooking.recipe, "step_index": cooking.step_index} if cooking else None

    async def clear_chat(self, user_id: int) -> None:
        async with self.sessions() as db:
            await db.execute(delete(Conversation).where(Conversation.user_id == user_id))
            await db.execute(delete(CookingSession).where(CookingSession.user_id == user_id))
            await db.execute(update(CookingTimer).where(
                CookingTimer.user_id == user_id,
                CookingTimer.status.in_(("active", "sending"))
            ).values(status="cancelled"))
            user = await self._user(db, user_id)
            user.mode = "ask"
            await db.commit()

    async def delete_user(self, user_id: int) -> None:
        async with self.sessions() as db:
            await db.execute(delete(Conversation).where(Conversation.user_id == user_id))
            await db.execute(delete(CookingSession).where(CookingSession.user_id == user_id))
            await db.execute(delete(CookingTimer).where(CookingTimer.user_id == user_id))
            await db.execute(delete(Favorite).where(Favorite.user_id == user_id))
            await db.execute(delete(PantryItem).where(PantryItem.user_id == user_id))
            await db.execute(delete(WeeklyPlan).where(WeeklyPlan.user_id == user_id))
            await db.execute(delete(FermentationReading).where(FermentationReading.user_id == user_id))
            await db.execute(delete(FermentationBatch).where(FermentationBatch.user_id == user_id))
            await db.execute(delete(RecipeFeedback).where(RecipeFeedback.user_id == user_id))
            await db.execute(delete(RecipeArchive).where(RecipeArchive.user_id == user_id))
            await db.execute(delete(PersonalMemory).where(PersonalMemory.user_id == user_id))
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()


    async def pantry(self, user_id: int) -> list[dict[str, str]]:
        async with self.sessions() as db:
            rows = await db.scalars(select(PantryItem).where(PantryItem.user_id == user_id).order_by(PantryItem.name_key, PantryItem.unit))
            return [{"name_key": item.name_key, "display_name": item.display_name,
                     "unit": item.unit, "quantity": item.quantity} for item in rows]

    async def change_pantry(self, user_id: int, name: str, name_key: str,
                            amount: Decimal, unit: str, remove: bool = False) -> bool:
        """Обновить количество конкретного продукта в одной транзакции.

        Возвращает False, если при удалении такой запас отсутствует.
        Для SQLite одного процесса достаточно; для конкурентной записи на
        PostgreSQL потребуется UPSERT/row locking перед масштабированием.
        """
        if amount <= 0 or amount > Decimal("100000000"):
            raise ValueError("Неверное количество")
        if unit not in {"г", "мл", "шт"}:
            raise ValueError("Неизвестная единица")
        async with self.sessions() as db:
            result = await db.execute(select(PantryItem).where(
                PantryItem.user_id == user_id,
                PantryItem.name_key == name_key,
                PantryItem.unit == unit,
            ))
            row = result.scalar_one_or_none()
            if row is None:
                if remove:
                    return False
                count = await db.scalars(select(PantryItem.id).where(PantryItem.user_id == user_id))
                if len(list(count)) >= 100:
                    raise ValueError("Можно хранить не больше 100 позиций")
                db.add(PantryItem(user_id=user_id, name_key=name_key, display_name=name,
                                  quantity=str(amount), unit=unit))
            else:
                result_amount = Decimal(row.quantity) + (-amount if remove else amount)
                if result_amount <= 0:
                    await db.delete(row)
                else:
                    row.quantity = str(result_amount)
                    row.display_name = name
            await db.commit()
            return True

    async def clear_pantry(self, user_id: int) -> None:
        async with self.sessions() as db:
            await db.execute(delete(PantryItem).where(PantryItem.user_id == user_id))
            await db.commit()

    async def save_weekly_plan(self, user_id: int, plan: dict[str, Any]) -> None:
        async with self.sessions() as db:
            row = await db.get(WeeklyPlan, user_id)
            if row:
                row.plan = plan
                row.created_at = datetime.now(timezone.utc)
            else:
                db.add(WeeklyPlan(user_id=user_id, plan=plan))
            await db.commit()

    async def get_weekly_plan(self, user_id: int) -> dict[str, Any] | None:
        async with self.sessions() as db:
            row = await db.get(WeeklyPlan, user_id)
            return row.plan if row else None

    async def set_cooking_step(self, user_id: int, step_index: int) -> dict[str, Any] | None:
        async with self.sessions() as db:
            row = await db.get(CookingSession, user_id)
            if not row:
                return None
            steps = row.recipe.get("steps", [])
            row.step_index = max(0, min(step_index, max(0, len(steps) - 1)))
            state = {"recipe": row.recipe, "step_index": row.step_index}
            await db.commit()
            return state


    async def rate_last_recipe(self, user_id: int, outcome: str) -> bool:
        allowed = {"great", "good", "salty", "dry", "spicy", "disliked"}
        if outcome not in allowed:
            raise ValueError("Неизвестная оценка")
        async with self.sessions() as db:
            user = await self._user(db, user_id)
            recipe = user.last_recipe
            if not isinstance(recipe, dict) or not recipe.get("title"):
                return False
            db.add(RecipeFeedback(user_id=user_id, recipe_title=recipe["title"][:180],
                                  outcome=outcome))
            await db.flush()
            extra = await db.scalars(select(RecipeFeedback.id)
                                     .where(RecipeFeedback.user_id == user_id)
                                     .order_by(RecipeFeedback.id.desc()).offset(50))
            old_ids = list(extra)
            if old_ids:
                await db.execute(delete(RecipeFeedback).where(RecipeFeedback.id.in_(old_ids)))
            await db.commit()
            return True

    async def recent_feedback(self, user_id: int) -> list[dict[str, str]]:
        async with self.sessions() as db:
            rows = await db.scalars(
                select(RecipeFeedback)
                .where(RecipeFeedback.user_id == user_id)
                .order_by(RecipeFeedback.id.desc()).limit(10)
            )
            return [{"dish": row.recipe_title, "outcome": row.outcome} for row in rows]


    async def feedback_patterns(self, user_id: int) -> dict[str, Any]:
        """Только наблюдаемые повторения в оценках, не выдуманные вкусы."""
        async with self.sessions() as db:
            rows = (await db.scalars(
                select(RecipeFeedback).where(RecipeFeedback.user_id == user_id)
                .order_by(RecipeFeedback.id.desc()).limit(50)
            )).all()
        issues: dict[str, int] = {}
        for row in rows:
            if row.outcome in {"salty", "dry", "spicy", "disliked"}:
                issues[row.outcome] = issues.get(row.outcome, 0) + 1
        return {
            "observations": len(rows),
            "repeated_issues": {name: n for name, n in issues.items() if n >= 2},
            "note": "Это повторения оценок блюд, НЕ подтверждённые постоянные предпочтения.",
        }


    async def create_fermentation_batch(
        self, user_id: int, category: str, name: str, protocol_source: str = "",
        protocol_id: str = "", protocol_revision: str = ""
    ) -> int:
        from .fermentation import PROCESS_LABELS
        if category not in PROCESS_LABELS:
            raise ValueError("Неизвестная категория")
        if not 2 <= len(name.strip()) <= 120:
            raise ValueError("Название должно содержать 2–120 символов")
        if len(protocol_source) > 240:
            raise ValueError("Источник должен содержать не более 240 символов")
        if protocol_id or protocol_revision:
            from .protocols import get_protocol
            p = get_protocol(protocol_id)
            if not p or p.revision != protocol_revision or p.category != category:
                raise ValueError("Неизвестная или устаревшая версия протокола")
            if protocol_source != p.source_url:
                raise ValueError("Нельзя заменять первоисточник выбранного протокола")
        async with self.sessions() as db:
            active = (await db.scalars(
                select(FermentationBatch.id).where(
                    FermentationBatch.user_id == user_id, FermentationBatch.finished.is_(False))
            )).all()
            if len(active) >= 10:
                raise ValueError("Одновременно можно вести не больше 10 партий")
            row = FermentationBatch(user_id=user_id, category=category,
                                    name=name.strip(), protocol_source=protocol_source.strip(),
                                    protocol_id=protocol_id, protocol_revision=protocol_revision,
                                    finished=False)
            db.add(row)
            await db.commit()
            return row.id

    async def list_fermentation_batches(self, user_id: int) -> list[dict[str, Any]]:
        async with self.sessions() as db:
            items = (await db.scalars(
                select(FermentationBatch)
                .where(FermentationBatch.user_id == user_id)
                .order_by(FermentationBatch.id.desc()).limit(20)
            )).all()
            return [{"id": r.id, "name": r.name, "category": r.category,
                     "finished": r.finished, "started_at": str(r.started_at),
                     "protocol_source": r.protocol_source,
                     "protocol_id": r.protocol_id, "protocol_revision": r.protocol_revision}
                    for r in items]

    async def fermentation_batch(self, user_id: int, batch_id: int) -> dict[str, Any] | None:
        async with self.sessions() as db:
            row = await db.get(FermentationBatch, batch_id)
            if row is None or row.user_id != user_id:
                return None
            readings = (await db.scalars(
                select(FermentationReading)
                .where(FermentationReading.batch_id == batch_id,
                       FermentationReading.user_id == user_id)
                .order_by(FermentationReading.id.desc()).limit(10)
            )).all()
            return {
                "id": row.id, "name": row.name, "category": row.category,
                "finished": row.finished, "started_at": str(row.started_at),
                "protocol_source": row.protocol_source,
                "protocol_id": row.protocol_id, "protocol_revision": row.protocol_revision,
                "readings": [{"temperature_c": r.temperature_c, "ph": r.ph,
                              "note": r.note, "observed_at": str(r.observed_at)}
                             for r in reversed(readings)]
            }

    async def log_fermentation(self, user_id: int, batch_id: int,
                               temperature_c: str | None, ph: str | None, note: str) -> bool:
        async with self.sessions() as db:
            row = await db.get(FermentationBatch, batch_id)
            if row is None or row.user_id != user_id or row.finished:
                return False
            ids = (await db.scalars(
                select(FermentationReading.id).where(
                    FermentationReading.user_id == user_id,
                    FermentationReading.batch_id == batch_id
                )
            )).all()
            if len(ids) >= 100:
                raise ValueError("В партии уже 100 измерений. Сохраните архив перед новой партией.")
            db.add(FermentationReading(
                batch_id=batch_id, user_id=user_id,
                temperature_c=temperature_c, ph=ph, note=note[:500]
            ))
            await db.commit()
            return True

    async def finish_fermentation_batch(self, user_id: int, batch_id: int) -> bool:
        async with self.sessions() as db:
            row = await db.get(FermentationBatch, batch_id)
            if row is None or row.user_id != user_id:
                return False
            row.finished = True
            await db.commit()
            return True

    async def delete_fermentation_batch(self, user_id: int, batch_id: int) -> bool:
        async with self.sessions() as db:
            row = await db.get(FermentationBatch, batch_id)
            if row is None or row.user_id != user_id:
                return False
            await db.execute(delete(FermentationReading).where(
                FermentationReading.batch_id == batch_id, FermentationReading.user_id == user_id
            ))
            await db.delete(row)
            await db.commit()
            return True


    async def start_timer(self, user_id: int, chat_id: int, minutes: int,
                          label: str, now_ts: int | None = None) -> dict[str, Any]:
        """Explicitly start a reminder for the current cooking step.

        Multiple reminders can run while a user advances through steps.
        Does not require or call an LLM, and is bounded per account.
        """
        if type(minutes) is not int or not MIN_MINUTES <= minutes <= MAX_MINUTES:
            raise ValueError(f"Таймер должен длиться {MIN_MINUTES}–{MAX_MINUTES} минут")
        if chat_id != user_id:
            raise ValueError("Таймер можно запускать только в личном чате")
        if not label or len(label) > 120:
            raise ValueError("Неверная подпись таймера")
        now_ts = int(time()) if now_ts is None else now_ts
        async with self.sessions() as db:
            cooking = await db.get(CookingSession, user_id)
            if cooking is None or cooking.step_index >= len(cooking.recipe.get("steps", [])):
                raise ValueError("Для запуска таймера начните пошаговое приготовление")
            current = (await db.scalars(select(CookingTimer.id).where(
                CookingTimer.user_id == user_id,
                CookingTimer.status.in_(("active", "sending")),
            ))).all()
            if len(current) >= MAX_ACTIVE_TIMERS:
                raise ValueError(f"Одновременно разрешено не больше {MAX_ACTIVE_TIMERS} таймеров")
            record = CookingTimer(
                user_id=user_id, chat_id=chat_id,
                recipe_title=str(cooking.recipe.get("title", "Блюдо"))[:180],
                step_index=cooking.step_index, label=label.strip(),
                minutes=minutes, due_at_ts=now_ts + minutes * 60,
                retry_at_ts=0, lease_until_ts=0, attempts=0, status="active",
            )
            db.add(record)
            await db.commit()
            return self._timer_dict(record)

    @staticmethod
    def _timer_dict(row: CookingTimer) -> dict[str, Any]:
        return {
            "id": row.id, "user_id": row.user_id, "chat_id": row.chat_id,
            "recipe_title": row.recipe_title, "step_index": row.step_index,
            "label": row.label, "minutes": row.minutes,
            "due_at_ts": row.due_at_ts, "status": row.status,
            "attempts": row.attempts,
        }

    async def user_timers(self, user_id: int) -> list[dict[str, Any]]:
        async with self.sessions() as db:
            rows = (await db.scalars(
                select(CookingTimer).where(
                    CookingTimer.user_id == user_id,
                    CookingTimer.status.in_(("active", "sending")),
                ).order_by(CookingTimer.due_at_ts, CookingTimer.id)
            )).all()
            return [self._timer_dict(row) for row in rows]

    async def cancel_timer(self, user_id: int, timer_id: int) -> bool:
        async with self.sessions() as db:
            changed = await db.execute(
                update(CookingTimer)
                .where(CookingTimer.id == timer_id,
                       CookingTimer.user_id == user_id,
                       CookingTimer.status.in_(("active", "sending")))
                .values(status="cancelled", lease_until_ts=0)
            )
            await db.commit()
            return changed.rowcount == 1

    async def claim_due_timers(self, *, now_ts: int | None = None,
                               limit: int = 20) -> list[dict[str, Any]]:
        """Transactional CAS claim of due rows, incl. expired send leases.

        A claim is persisted BEFORE Telegram send. An unexpected process crash
        after Telegram accepts the message may cause a duplicate on recovery.
        """
        now_ts = int(time()) if now_ts is None else now_ts
        async with self.sessions() as db:
            # Exhausted leases must not remain eternally stuck in "sending".
            await db.execute(update(CookingTimer).where(
                CookingTimer.status == "sending",
                CookingTimer.lease_until_ts <= now_ts,
                CookingTimer.attempts >= 5,
            ).values(status="failed", lease_until_ts=0))
            pending = (await db.scalars(
                select(CookingTimer.id).where(
                    CookingTimer.due_at_ts <= now_ts,
                    CookingTimer.attempts < 5,
                    (
                        ((CookingTimer.status == "active") &
                         (CookingTimer.retry_at_ts <= now_ts))
                        | ((CookingTimer.status == "sending") &
                           (CookingTimer.lease_until_ts <= now_ts))
                    ),
                ).order_by(CookingTimer.due_at_ts, CookingTimer.id)
                .limit(max(1, min(limit, 100)))
            )).all()
            claimed = []
            for timer_id in pending:
                result = await db.execute(
                    update(CookingTimer).where(
                        CookingTimer.id == timer_id,
                        CookingTimer.due_at_ts <= now_ts,
                        CookingTimer.attempts < 5,
                        (
                            ((CookingTimer.status == "active") &
                             (CookingTimer.retry_at_ts <= now_ts))
                            | ((CookingTimer.status == "sending") &
                               (CookingTimer.lease_until_ts <= now_ts))
                        ),
                    ).values(status="sending",
                             lease_until_ts=now_ts + 120,
                             attempts=CookingTimer.attempts + 1)
                )
                if result.rowcount == 1:
                    row = await db.get(CookingTimer, timer_id)
                    claimed.append(self._timer_dict(row))
            await db.commit()
            return claimed

    async def timer_still_sending(self, timer_id: int) -> bool:
        """Avoid dispatching a timer cancelled after it was claimed."""
        async with self.sessions() as db:
            status = await db.scalar(
                select(CookingTimer.status).where(CookingTimer.id == timer_id)
            )
            return status == "sending"

    async def complete_timer_delivery(self, timer_id: int, *, success: bool,
                                      now_ts: int | None = None) -> bool:
        """Mark sent, or retry with backoff; never retry a cancelled timer."""
        now_ts = int(time()) if now_ts is None else now_ts
        async with self.sessions() as db:
            row = await db.get(CookingTimer, timer_id)
            if not row or row.status != "sending":
                return False
            if success:
                row.status = "delivered"
                row.lease_until_ts = 0
            else:
                row.status = "failed" if row.attempts >= 5 else "active"
                row.lease_until_ts = 0
                row.retry_at_ts = now_ts + min(60 * (2 ** max(0, row.attempts - 1)), 900)
            await db.commit()
            return True

    async def archived_recipes(self, user_id: int, limit: int = 15, offset: int = 0) -> list[dict[str, Any]]:
        """Рецепты сохраняются автоматически; избранное — отдельная коллекция."""
        async with self.sessions() as db:
            rows = (await db.scalars(
                select(RecipeArchive).where(RecipeArchive.user_id == user_id)
                .order_by(RecipeArchive.id.desc()).offset(max(0, offset))
                .limit(min(max(limit, 1), 100))
            )).all()
            return [{"id": row.id, "recipe": row.recipe, "origin": row.origin,
                     "created_at": str(row.created_at)} for row in rows]

    async def select_archived_recipe(self, user_id: int, recipe_id: int,
                                     activate: bool = True) -> dict[str, Any] | None:
        async with self.sessions() as db:
            row = await db.get(RecipeArchive, recipe_id)
            if not row or row.user_id != user_id:
                return None
            if activate:
                user = await self._user(db, user_id)
                # Нельзя активировать старый рецепт при действующих аллергенных
                # или иных продуктовых ограничениях без ручной проверки.
                prefs = user.preferences or {}
                if prefs.get("allergens") or prefs.get("excluded"):
                    return None
                user.last_recipe = row.recipe
                await db.execute(update(CookingTimer).where(
                    CookingTimer.user_id == user_id,
                    CookingTimer.status.in_(("active", "sending"))
                ).values(status="cancelled"))
                await db.execute(delete(CookingSession).where(CookingSession.user_id == user_id))
            await db.commit()
            return row.recipe

    async def remove_archived_recipe(self, user_id: int, recipe_id: int) -> bool:
        async with self.sessions() as db:
            row = await db.get(RecipeArchive, recipe_id)
            if not row or row.user_id != user_id:
                return False
            await db.delete(row)
            await db.commit()
            return True

    async def propose_memory(self, user_id: int, kind: str, value: str) -> int:
        value = validate_memory(kind, value)
        async with self.sessions() as db:
            # Подтверждение нужно в явном виде: pending-факты не участвуют
            # в персонализации и не передаются модели.
            pending = (await db.scalars(
                select(PersonalMemory.id).where(
                    PersonalMemory.user_id == user_id,
                    PersonalMemory.status == "pending")
            )).all()
            if len(pending) >= 5:
                raise ValueError("Сначала подтвердите или отклоните ожидающие записи")
            row = PersonalMemory(user_id=user_id, kind=kind, value=value,
                                 status="pending", source="explicit_user")
            db.add(row)
            await db.commit()
            return row.id

    async def confirm_memory(self, user_id: int, memory_id: int) -> bool:
        async with self.sessions() as db:
            row = await db.get(PersonalMemory, memory_id)
            if not row or row.user_id != user_id or row.status != "pending":
                return False
            confirmed = (await db.scalars(
                select(PersonalMemory.id).where(
                    PersonalMemory.user_id == user_id,
                    PersonalMemory.status == "active")
            )).all()
            if len(confirmed) >= 50:
                raise ValueError("Лимит 50 фактов: удалите неактуальные записи")
            row.status = "active"
            await db.commit()
            return True

    async def personal_memories(self, user_id: int, *, include_pending: bool = False,
                                limit: int = 50) -> list[dict[str, Any]]:
        async with self.sessions() as db:
            stmt = select(PersonalMemory).where(PersonalMemory.user_id == user_id)
            if not include_pending:
                stmt = stmt.where(PersonalMemory.status == "active")
            rows = (await db.scalars(
                stmt.order_by(PersonalMemory.id.desc()).limit(min(max(limit, 1), 100))
            )).all()
            return [{"id": row.id, "kind": row.kind, "value": row.value,
                     "status": row.status, "source": row.source}
                    for row in rows]

    async def remove_memory(self, user_id: int, memory_id: int) -> bool:
        async with self.sessions() as db:
            row = await db.get(PersonalMemory, memory_id)
            if not row or row.user_id != user_id:
                return False
            await db.delete(row)
            await db.commit()
            return True

    async def export_user_data(self, user_id: int) -> dict[str, Any]:
        """Полный JSON-экспорт личных записей. Не включает чужие сведения."""
        async with self.sessions() as db:
            user = await db.get(User, user_id)

            async def rows_for(model):
                result = await db.scalars(select(model).where(model.user_id == user_id))
                return result.all()

            conversations = await rows_for(Conversation)
            favorites = await rows_for(Favorite)
            archive = await rows_for(RecipeArchive)
            feedback = await rows_for(RecipeFeedback)
            pantry = await rows_for(PantryItem)
            notes = await rows_for(PersonalMemory)
            batches = await rows_for(FermentationBatch)
            readings = await rows_for(FermentationReading)
            timers = await rows_for(CookingTimer)
            cooking = await db.get(CookingSession, user_id)
            weekly = await db.get(WeeklyPlan, user_id)
            return {
                "exported_at_utc": datetime.now(timezone.utc).isoformat(),
                "user_id": user_id,
                "profile": {"mode": user.mode, "preferences": user.preferences,
                            "last_recipe": user.last_recipe} if user else None,
                "conversation": [{"role": c.role, "content": c.content,
                                  "created_at": str(c.created_at)}
                                 for c in conversations],
                "recipes": [{"id": r.id, "recipe": r.recipe, "origin": r.origin,
                             "created_at": str(r.created_at)} for r in archive],
                "favorites": [{"id": r.id, "recipe": r.recipe,
                               "created_at": str(r.created_at)} for r in favorites],
                "recipe_feedback": [{"dish": r.recipe_title, "outcome": r.outcome,
                                     "created_at": str(r.created_at)} for r in feedback],
                "pantry": [{"product": r.display_name, "quantity": r.quantity,
                            "unit": r.unit} for r in pantry],
                "memories": [{"kind": r.kind, "value": r.value, "status": r.status,
                              "source": r.source} for r in notes],
                "weekly_plan": weekly.plan if weekly else None,
                "cooking": {"recipe": cooking.recipe, "step_index": cooking.step_index}
                           if cooking else None,
                "fermentation_batches": [
                    {"id": b.id, "category": b.category, "name": b.name,
                     "protocol_id": b.protocol_id, "protocol_revision": b.protocol_revision,
                     "protocol_source": b.protocol_source, "finished": b.finished,
                     "started_at": str(b.started_at)} for b in batches
                ],
                "cooking_timers": [
                    {**self._timer_dict(t), "created_at": str(t.created_at)}
                    for t in timers
                ],
                "fermentation_readings": [
                    {"batch_id": r.batch_id, "temperature_c": r.temperature_c,
                     "ph": r.ph, "note": r.note, "observed_at": str(r.observed_at)}
                    for r in readings
                ],
            }
