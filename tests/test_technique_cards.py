"""Проверка профессиональных технологических карт без LLM и GitHub Actions."""
from copy import deepcopy

import pytest

from sushef.bot import (
    cooking_insight_text, cooking_keyboard, dish_process_card_text,
    technique_categories_keyboard, technique_card_text,
)
from sushef.chef import format_recipe, normalize_recipe
from sushef.dish_process_cards import DISH_CARDS, validate_dish_cards
from sushef.storage import Storage
from sushef.technique_catalog import (
    TECHNIQUES, CATEGORIES, technique_context, validate_techniques,
)


def callbacks(markup):
    return {b.callback_data for line in markup.inline_keyboard for b in line}


def test_all_techniques_are_sourced_and_structurally_valid():
    validate_techniques()
    assert len(TECHNIQUES) == 8
    assert len(CATEGORIES) == 7
    assert len({t["id"] for t in TECHNIQUES}) == len(TECHNIQUES)
    for item in TECHNIQUES:
        assert item["source_url"].startswith("https://")
        assert item["controls"] and item["cues"] and item["problems"]
        assert "Почему это работает" in technique_card_text({
            **item, "reviewed_on": "2026-10-09"
        })
        assert len(("technique:open:" + item["id"]).encode()) <= 64
    assert all("technique:category:" + cat in callbacks(technique_categories_keyboard())
               for cat in CATEGORIES)
    assert {"cook:why", "cook:fix"} <= callbacks(cooking_keyboard())


def test_techniques_reject_invalid_sources_and_duplicate_ids(monkeypatch):
    import sushef.technique_catalog as catalog
    monkeypatch.setattr(catalog, "TECHNIQUES", TECHNIQUES + [deepcopy(TECHNIQUES[0])])
    with pytest.raises(ValueError, match="Дублирующийся"):
        catalog.validate_techniques()
    invalid = deepcopy(TECHNIQUES[0])
    invalid["id"] = "invalid-source"
    invalid["source_url"] = "http://untrusted.example"
    monkeypatch.setattr(catalog, "TECHNIQUES", TECHNIQUES + [invalid])
    with pytest.raises(ValueError, match="ссылка"):
        catalog.validate_techniques()


def test_dish_cards_have_quantities_and_dont_invent_yields():
    validate_dish_cards()
    assert {c["recipe_id"] for c in DISH_CARDS} == {"gazpacho", "salmorejo"}
    assert all(card["yield_grams"] is None for card in DISH_CARDS)
    rows = [{
        **card, "source_url": "https://www.spain.info/en/recipe/gazpacho/",
        "source_publisher": "TURESPAÑA",
    } for card in DISH_CARDS]
    for row in rows:
        shown = dish_process_card_text(row)
        assert "Выход: не указан" in shown
        assert "Почему:" in shown and "Признак:" in shown
        assert "Технология и контроль" in shown
        assert row["stages"][0]["why"] in shown


def test_old_and_new_recipes_coexist_with_explanations():
    import json
    data = {
        "title": "Яйца и овощи", "time_minutes": 12, "servings": 2,
        "ingredients": [{"name": "яйца", "amount": "2 шт."}],
        "steps": ["Осторожно нагреть яйца.", "Подать."],
        "safety_notes": [],
        "step_insights": [
            {"step_index": 0, "why": "Избыток тепла уплотняет яичный белок.",
             "cue": "Белок нежный, не резиновый.", "fix": "Убавить огонь."},
            {"step_index": 15, "why": "Bad", "cue": "", "fix": ""},
            {"step_index": 0, "why": "Duplicate", "cue": "", "fix": ""},
        ],
    }
    new = normalize_recipe(json.dumps(data, ensure_ascii=False))
    assert len(new["step_insights"]) == 1
    assert "Почему: Избыток тепла" in format_recipe(new)
    session = {"recipe": new, "step_index": 0}
    assert "Избыток тепла" in cooking_insight_text(session, "why")
    assert "Убавить огонь." in cooking_insight_text(session, "fix")
    session["step_index"] = 1
    assert "нет отдельной" in cooking_insight_text(session, "why")

    old = dict(data)
    old.pop("step_insights")
    legacy = normalize_recipe(json.dumps(old, ensure_ascii=False))
    assert legacy["step_insights"] == []
    assert "яйца" in format_recipe(legacy)
    invalid = dict(data, step_insights={"bad": "shape"})
    assert normalize_recipe(json.dumps(invalid, ensure_ascii=False))["step_insights"] == []


def test_technique_context_explicitly_marks_reference_limitations():
    item = {**TECHNIQUES[0], "revision": "1", "reviewed_on": "2026-10-09",
            "evidence": "source_based_explanation"}
    text = technique_context([item])
    assert "Источник:" in text
    assert "не подтверждают" not in text or "справочный" in text
    assert "Не выдавай справочный источник" in text


@pytest.mark.asyncio
async def test_technique_library_is_persistent_isolated_from_user_memory(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'tech.db'}"
    db = Storage(url)
    await db.create_tables()
    try:
        assert len(await db.technique_cards()) == 8
        assert await db.seed_techniques() == 0
        assert await db.seed_dish_cards() == 0
        assert (await db.technique_card("brown-butter"))["category"] == "fat"
        assert len(await db.technique_cards("dough")) == 2
        assert await db.technique_card("not-there") is None
        assert await db.technique_cards("unknown") == []
        matches = await db.technique_matches("Хочу корочку, подрумянить грибы")
        assert matches and matches[0]["id"] == "maillard"
        assert await db.technique_matches("тут нет рецепта") == []
        card = await db.dish_process_card("gazpacho")
        assert card and len(card["stages"]) == 3
        assert card["yield_grams"] is None
        assert await db.dish_process_card("not-there") is None

        await db.set_preference(11, "likes", "овощи")
        assert (await db.get_user(12))["preferences"] == {}
        await db.delete_user(11)
        assert len(await db.technique_cards()) == 8
        assert await db.dish_process_card("gazpacho") is not None
    finally:
        await db.close()

    reopened = Storage(url)
    try:
        assert (await reopened.technique_card("brown-butter"))["id"] == "brown-butter"
        assert await reopened.dish_process_card("salmorejo") is not None
    finally:
        await reopened.close()
