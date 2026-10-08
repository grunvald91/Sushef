import pytest

from sushef.memory import (
    PROFILE_FIELDS, MEMORY_KINDS, validate_memory,
    validate_preference, short_memory_context,
)
from sushef.storage import Storage


@pytest.fixture
async def store(tmp_path):
    db = Storage(f"sqlite+aiosqlite:///{tmp_path / 'memory.db'}")
    await db.create_tables()
    yield db
    await db.close()


def test_new_profile_fields_are_explicit_and_bounded():
    assert {"cuisines", "spice", "textures", "budget", "cook_time",
            "skill"}.issubset(PROFILE_FIELDS)
    assert validate_preference("spice", "Средняя") == "средняя"
    assert validate_preference("skill", "Уверенный") == "уверенный"
    assert validate_preference("cook_time", "45") == "45"
    for field, value in (
        ("spice", "неизвестно"), ("skill", "шеф 999"),
        ("cook_time", "10000"), ("portions", "0"), ("likes", ""),
        ("unregistered", "hello"),
    ):
        with pytest.raises(ValueError):
            validate_preference(field, value)


def test_memory_never_treats_pending_as_personalized_fact():
    facts = [
        {"kind": "taste", "value": "Слишком острое не люблю", "status": "pending"},
        {"kind": "technique", "value": "Люблю долго томить мясо", "status": "active"},
    ]
    assert short_memory_context(facts) == [
        {"kind": "technique", "fact": "Люблю долго томить мясо"}
    ]
    assert validate_memory("taste", "Люблю кислинку") == "Люблю кислинку"
    with pytest.raises(ValueError):
        validate_memory("taste", "x")


@pytest.mark.asyncio
async def test_mode_switch_retains_chat_but_reset_clears_it(store):
    uid = 100
    await store.add_exchange(uid, "Привет", "Добрый день")
    await store.set_mode(uid, "recipe")
    await store.set_mode(uid, "ferment:sourdough")
    assert len(await store.get_history(uid)) == 2
    await store.clear_chat(uid)
    assert await store.get_history(uid) == []


@pytest.mark.asyncio
async def test_generated_recipes_auto_archive_and_restore(store):
    first, other = 310, 311
    recipe1 = {"title": "Борщ", "ingredients": [], "steps": ["Шаг"]}
    recipe2 = {"title": "Салат", "ingredients": [], "steps": ["Шаг"]}
    await store.set_recipe(first, recipe1)
    await store.set_recipe(first, recipe2)
    archived = await store.archived_recipes(first)
    assert [r["recipe"]["title"] for r in archived] == ["Салат", "Борщ"]
    assert await store.archived_recipes(other) == []
    assert await store.select_archived_recipe(other, archived[0]["id"]) is None
    assert await store.select_archived_recipe(first, archived[1]["id"]) == recipe1
    assert (await store.get_user(first))["last_recipe"] == recipe1
    assert await store.remove_archived_recipe(other, archived[0]["id"]) is False
    assert await store.remove_archived_recipe(first, archived[0]["id"]) is True
    assert len(await store.archived_recipes(first)) == 1


@pytest.mark.asyncio
async def test_allergen_restrictions_block_archive_activation(store):
    uid = 21
    recipe = {"title": "Ореховый торт", "ingredients": [], "steps": ["Шаг"]}
    await store.set_recipe(uid, recipe)
    record = (await store.archived_recipes(uid))[0]
    await store.set_preference(uid, "allergens", "арахис")
    assert await store.select_archived_recipe(uid, record["id"], activate=True) is None
    assert await store.select_archived_recipe(uid, record["id"], activate=False) == recipe
    assert (await store.get_user(uid))["last_recipe"] is None


@pytest.mark.asyncio
async def test_explicit_memory_requires_confirmation_and_is_user_private(store):
    user, other = 911, 912
    pending_id = await store.propose_memory(user, "taste", "Люблю терпкие соусы")
    assert await store.personal_memories(user) == []
    all_entries = await store.personal_memories(user, include_pending=True)
    assert all_entries[0]["status"] == "pending"
    assert not await store.confirm_memory(other, pending_id)
    assert await store.confirm_memory(user, pending_id)
    active = await store.personal_memories(user)
    assert active[0]["value"] == "Люблю терпкие соусы"
    assert await store.personal_memories(other) == []
    assert not await store.remove_memory(other, pending_id)
    assert await store.remove_memory(user, pending_id)
    assert await store.personal_memories(user) == []


@pytest.mark.asyncio
async def test_export_contains_only_owners_records_and_delete_me_erases(store):
    user, other = 7, 8
    await store.set_preference(user, "cuisines", "Грузинская")
    await store.set_recipe(user, {"title": "Хачапури", "steps": ["Испечь"]})
    await store.add_exchange(user, "Сыр?", "Да")
    await store.add_exchange(other, "Чужой секрет", "Ответ")
    record = await store.propose_memory(user, "habit", "Пеку по субботам")
    await store.confirm_memory(user, record)
    export = await store.export_user_data(user)
    assert export["profile"]["preferences"]["cuisines"] == "Грузинская"
    assert export["recipes"][0]["recipe"]["title"] == "Хачапури"
    assert export["memories"][0]["status"] == "active"
    assert all("Чужой" not in str(x) for x in export.values())
    await store.delete_user(user)
    erased = await store.export_user_data(user)
    assert erased["profile"] is None
    assert erased["recipes"] == []
    assert erased["memories"] == []
    assert erased["conversation"] == []
    assert len((await store.export_user_data(other))["conversation"]) == 2


@pytest.mark.asyncio
async def test_repeated_reviews_are_observations_not_new_preferences(store):
    user = 81
    await store.set_recipe(user, {"title": "Гуляш", "steps": ["Готовить"]})
    assert await store.rate_last_recipe(user, "dry")
    assert await store.rate_last_recipe(user, "dry")
    info = await store.feedback_patterns(user)
    assert info["repeated_issues"] == {"dry": 2}
    assert (await store.get_user(user))["preferences"] == {}
