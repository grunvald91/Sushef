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


@pytest.mark.asyncio
async def test_new_allergy_invalidates_active_recipe(storage):
    uid = 456
    recipe = {
        "title": "Салат", "time_minutes": 5, "servings": 1,
        "ingredients": [{"name": "Арахис", "amount": "20 г"}],
        "steps": ["Смешать"], "safety_notes": [],
    }
    await storage.set_recipe(uid, recipe)
    assert await storage.start_cooking(uid)
    await storage.set_preference(uid, "allergens", "арахис")
    assert (await storage.get_user(uid))["last_recipe"] is None
    assert await storage.current_cooking(uid) is None


@pytest.mark.asyncio
async def test_pantry_isolation_and_full_data_erasure(storage):
    from decimal import Decimal
    first, second = 2001, 2002
    assert await storage.change_pantry(first, "Молоко", "молоко", Decimal("1000"), "мл")
    assert await storage.change_pantry(second, "Мука", "мука", Decimal("500"), "г")
    assert len(await storage.pantry(first)) == 1
    assert len(await storage.pantry(second)) == 1
    assert await storage.change_pantry(first, "Молоко", "молоко", Decimal("200"), "мл", remove=True)
    assert (await storage.pantry(first))[0]["quantity"] == "800"
    assert not await storage.change_pantry(second, "Молоко", "молоко", Decimal("200"), "мл", remove=True)
    plan = {"days": [{"breakfast": "Каша", "lunch": "Суп", "dinner": "Рис"} for _ in range(7)]}
    await storage.save_weekly_plan(first, plan)
    assert await storage.get_weekly_plan(first) == plan
    assert await storage.get_weekly_plan(second) is None
    await storage.delete_user(first)
    assert await storage.pantry(first) == []
    assert await storage.get_weekly_plan(first) is None
    assert len(await storage.pantry(second)) == 1


@pytest.mark.asyncio
async def test_pantry_unit_normalization_and_cooking_previous(storage):
    from decimal import Decimal
    uid = 3003
    assert await storage.change_pantry(uid, "Картофель", "картофель", Decimal("500"), "г")
    assert await storage.change_pantry(uid, "Картофель", "картофель", Decimal("500"), "г")
    assert (await storage.pantry(uid))[0]["quantity"] == "1000"
    recipe = {"title": "Жаркое", "steps": ["A", "B", "C"]}
    await storage.set_recipe(uid, recipe)
    assert await storage.start_cooking(uid)
    assert (await storage.advance_cooking(uid))["step_index"] == 1
    assert (await storage.set_cooking_step(uid, 0))["step_index"] == 0


@pytest.mark.asyncio
async def test_allergen_change_invalidates_weekly_plan(storage):
    uid = 4004
    plan = {"days": [{"breakfast": "Яйца", "lunch": "Суп", "dinner": "Каша"} for _ in range(7)]}
    await storage.save_weekly_plan(uid, plan)
    await storage.set_preference(uid, "allergens", "яйца")
    assert await storage.get_weekly_plan(uid) is None
