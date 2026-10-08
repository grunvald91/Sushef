from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from .models import Base, Conversation, CookingSession, Favorite, User


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
            if value.strip() == "-":
                prefs.pop(key, None)
            else:
                prefs[key] = value.strip()[:500]
            user.preferences = prefs
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
        today = datetime.now(timezone.utc).date().isoformat()
        async with self.sessions() as db:
            user = await self._user(db, user_id)
            if user.usage_day != today:
                user.usage_day, user.usage_count = today, 0
            if user.usage_count >= daily_limit:
                await db.commit()
                return False
            user.usage_count += 1
            await db.commit()
            return True

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

    async def select_favorite(self, user_id: int, favorite_id: int) -> dict[str, Any] | None:
        async with self.sessions() as db:
            favorite = await db.get(Favorite, favorite_id)
            if not favorite or favorite.user_id != user_id:
                return None
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
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()
