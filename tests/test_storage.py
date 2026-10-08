import pytest

from sushef.storage import Storage


@pytest.fixture
async def storage(tmp_path):
    db = Storage(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.create_tables()
    yield db
    await db.close()


@pytest.mark.asyncio
async def test_profile_modes_and_clear(storage):
    user_id = 123456
    user = await storage.get_user(user_id)
    assert user["mode"] == "ask"
    await storage.set_preference(user_id, "allergens", "арахис")
    await storage.set_preference(user_id, "portions", "4")
    user = await storage.get_user(user_id)
    assert user["preferences"]["allergens"] == "арахис"
    await storage.set_mode(user_id, "rescue")
    assert (await storage.get_user(user_id))["mode"] == "rescue"
    await storage.add_exchange(user_id, "Вопрос", "Ответ")
    assert len(await storage.get_history(user_id)) == 2
    await storage.clear_chat(user_id)
    assert await storage.get_history(user_id) == []
    assert (await storage.get_user(user_id))["preferences"]["allergens"] == "арахис"


@pytest.mark.asyncio
async def test_recipe_favorite_cooking_and_delete(storage):
    uid = 989
    recipe = {
        "title": "Омлет", "time_minutes": 10, "servings": 1,
        "ingredients": [{"name": "Яйцо", "amount": "2 шт."}],
        "steps": ["Разбить яйца", "Приготовить"], "safety_notes": [],
    }
    assert not await storage.save_favorite(uid)
    await storage.set_recipe(uid, recipe)
    assert await storage.save_favorite(uid)
    items = await storage.favorites(uid)
    assert len(items) == 1
    assert await storage.select_favorite(uid + 1, items[0]["id"]) is None
    assert await storage.select_favorite(uid, items[0]["id"]) == recipe
    cooking = await storage.start_cooking(uid)
    assert cooking["step_index"] == 0
    assert (await storage.advance_cooking(uid))["step_index"] == 1
    assert (await storage.advance_cooking(uid))["step_index"] == 2
    assert await storage.current_cooking(uid) is None
    await storage.delete_user(uid)
    assert await storage.favorites(uid) == []
    assert (await storage.get_user(uid))["preferences"] == {}


@pytest.mark.asyncio
async def test_quota_day(storage):
    uid = 82
    assert await storage.use_quota(uid, 2)
    assert await storage.use_quota(uid, 2)
    assert not await storage.use_quota(uid, 2)


@pytest.mark.asyncio
async def test_history_bounded(storage):
    uid = 777
    for idx in range(25):
        await storage.add_exchange(uid, f"Вопрос {idx}", f"Ответ {idx}")
    history = await storage.get_history(uid, limit=100)
    assert len(history) == 40
    assert history[0]["content"] == "Вопрос 5"
