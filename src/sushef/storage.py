from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import Base, Conversation, CookingSession, Favorite, FermentationBatch, FermentationReading, PantryItem, RecipeFeedback, User, WeeklyPlan


class Storage:
    def __init__(self, database_url: str):
        self.engine = create_async_engine(database_url, pool_pre_ping=True)
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def create_tables(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()

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
            await db.execute(delete(Conversation).where(Conversation.user_id == user_id))
            await db.commit()

    async def set_preference(self, user_id: int, key: str, value: str) -> None:
        if key not in {"allergens", "excluded", "likes", "equipment", "portions"}:
            raise ValueError("Unknown preference")
        async with self.sessions() as db:
            user = await self._user(db, user_id)
            prefs = dict(user.preferences or {})
            previous = prefs.get(key)
            if value.strip() == "-":
                prefs.pop(key, None)
            else:
                prefs[key] = value.strip()[:500]
            user.preferences = prefs
            # При изменении аллергенов и исключений старый рецепт и текущая готовка
            # больше не считаются подходящими для профиля.
            if key in {"allergens", "excluded"} and previous != prefs.get(key):
                user.last_recipe = None
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
            else:
                cooking.recipe, cooking.step_index = recipe, 0
            user.mode = "cook"
            await db.commit()
            return {"recipe": recipe, "step_index": 0}

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
            user = await self._user(db, user_id)
            user.mode = "ask"
            await db.commit()

    async def delete_user(self, user_id: int) -> None:
        async with self.sessions() as db:
            await db.execute(delete(Conversation).where(Conversation.user_id == user_id))
            await db.execute(delete(CookingSession).where(CookingSession.user_id == user_id))
            await db.execute(delete(Favorite).where(Favorite.user_id == user_id))
            await db.execute(delete(PantryItem).where(PantryItem.user_id == user_id))
            await db.execute(delete(WeeklyPlan).where(WeeklyPlan.user_id == user_id))
            await db.execute(delete(FermentationReading).where(FermentationReading.user_id == user_id))
            await db.execute(delete(FermentationBatch).where(FermentationBatch.user_id == user_id))
            await db.execute(delete(RecipeFeedback).where(RecipeFeedback.user_id == user_id))
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


    async def create_fermentation_batch(self, user_id: int, category: str, name: str) -> int:
        from .fermentation import PROCESS_LABELS
        if category not in PROCESS_LABELS:
            raise ValueError("Неизвестная категория")
        if not 2 <= len(name.strip()) <= 120:
            raise ValueError("Название должно содержать 2–120 символов")
        async with self.sessions() as db:
            active = (await db.scalars(
                select(FermentationBatch.id).where(
                    FermentationBatch.user_id == user_id, FermentationBatch.finished.is_(False))
            )).all()
            if len(active) >= 10:
                raise ValueError("Одновременно можно вести не больше 10 партий")
            row = FermentationBatch(user_id=user_id, category=category,
                                    name=name.strip(), finished=False)
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
                     "finished": r.finished, "started_at": str(r.started_at)}
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
