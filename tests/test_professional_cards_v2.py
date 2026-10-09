"""V2 pilot professional cards: measured vs unmeasured facts, provenance and UX."""
from copy import deepcopy

import pytest

from sushef.bot import (
    production_overview, production_stage_text, production_quality_text,
    production_scale_text, production_keyboard,
)
from sushef.dish_process_cards import DISH_CARDS
from sushef.dish_process_cards_v2 import (
    V2_DISH_CARDS, validate_v2_cards, scale_source_ingredients,
)
from sushef.storage import Storage


def test_second_versions_are_preserved_and_explicitly_unvalidated():
    validate_v2_cards()
    assert {c["id"] for c in V2_DISH_CARDS} == {"gazpacho-v2", "salmorejo-v2"}
    assert {c["id"] for c in DISH_CARDS} == {"gazpacho-v1", "salmorejo-v1"}
    for card in V2_DISH_CARDS:
        spec = card["production_spec"]
        assert spec["kitchen_trials"] == 0
        assert spec["status"] == "source_checked_not_kitchen_tested"
        assert spec["gross_net_convention"] == "unknown_in_original_recipe"
        assert spec["provenance"]["original_url"] == card.get("source_url", spec["provenance"]["original_url"]) or spec["provenance"]["original_url"]
        assert spec["provenance"]["ingredient_amounts"] == "source_transcribed"
        assert spec["provenance"]["mechanism_and_repairs"] == "editorial_interpretation"
        for x in spec["ingredients"]:
            assert x["gross"] is None and x["net"] is None
            assert x["trim_loss_percent"] is None
            assert x["source_amount"]["value"]
        assert all(value is None for k, value in spec["measurement"].items()
                   if k != "basis")
        assert "пшеница/глютен" in " ".join(spec["allergens"]["probable"])
        assert "яйцо" in " ".join(spec["allergens"]["conditional"])


def test_source_quantities_can_be_scaled_but_unknowns_cannot():
    gaz = next(c for c in V2_DISH_CARDS if c["recipe_id"] == "gazpacho")
    half = scale_source_ingredients(gaz, 2)
    tomato = next(i for i in half if "помидоры" in i["name"])
    assert tomato["quantity"] == "500" and tomato["unit"] == "г"
    water = next(i for i in half if "вода" in i["name"])
    assert water["quantity"] == "по консистенции" and not water["scaled"]
    eggs = next(i for i in half if "яйцо" in i["name"])
    assert eggs["quantity"] == "по желанию" and not eggs["scaled"]
    full = scale_source_ingredients(gaz, 4)
    assert next(i for i in full if "помидоры" in i["name"])["quantity"] == "1000"
    for bad in (0, 21, 2.5, True, "4"):
        with pytest.raises(ValueError):
            scale_source_ingredients(gaz, bad)


def test_v2_quality_and_navigation_are_honest_and_easy_to_read():
    card = deepcopy(V2_DISH_CARDS[1])
    from sushef.dish_process_cards_v2 import as_row_v2
    row = as_row_v2(card)
    overview = production_overview(row)
    assert "Выход блюда: не измерен" in overview
    assert "Нетто/потери сырья: не измерены" in overview
    assert "не выполнены" in overview
    assert row["source_url"] in overview
    assert "1000 г" in overview
    assert "не измерен" not in production_stage_text(row, 0)  # only relevant local controls
    step = production_stage_text(row, 1)
    assert "Почему это работает:" in step
    assert "Контрольный признак:" in step
    assert "Если не получилось:" in step
    assert "не заданы для этого этапа" in step
    with pytest.raises(ValueError):
        production_stage_text(row, 20)
    quality = production_quality_text(row)
    for word in ("Аромат:", "Текстура:", "Вкус:", "аллергены", "замены", "Срок хранения"):
        assert word.casefold() in quality.casefold()
    scale = production_scale_text(row, 2)
    assert "500 г" in scale
    assert "Математический пересчёт" in scale
    controls = [button.callback_data for line in production_keyboard("salmorejo").inline_keyboard
                for button in line]
    assert "cuisine:tcstage:salmorejo:0" in controls
    assert "cuisine:tcquality:salmorejo" in controls
    assert "cuisine:tcscale:salmorejo:2" in controls
    assert all(len(a.encode("utf-8")) <= 64 for a in controls)


def test_validation_rejects_fictitious_measured_yields(monkeypatch):
    import sushef.dish_process_cards_v2 as module
    altered = deepcopy(V2_DISH_CARDS)
    altered[0]["production_spec"]["measurement"]["net_yield_grams"] = 1350
    monkeypatch.setattr(module, "V2_DISH_CARDS", altered)
    with pytest.raises(ValueError, match="Неподтверждённый"):
        module.validate_v2_cards()


@pytest.mark.asyncio
async def test_database_versions_remain_independent_and_persist(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'v2.db'}"
    db = Storage(url)
    await db.create_tables()
    try:
        assert await db.seed_dish_cards() == 0
        card = await db.dish_process_card("gazpacho")
        assert card and card["revision"] == "2"
        assert card["production_spec"]["measurement"]["net_yield_grams"] is None
        assert card["production_spec"]["status"] == "source_checked_not_kitchen_tested"
        await db.set_preference(77, "likes", "помидоры")
        assert (await db.get_user(77))["preferences"]["likes"] == "помидоры"
        assert (await db.get_user(78))["preferences"] == {}
    finally:
        await db.close()

    from sqlalchemy import text
    db = Storage(url)
    try:
        async with db.sessions() as session:
            rows = (await session.execute(text(
                "SELECT id, revision, production_spec FROM dish_process_cards ORDER BY id"
            ))).all()
        assert len(rows) == 4
        assert sorted(r[0] for r in rows) == [
            "gazpacho-v1", "gazpacho-v2", "salmorejo-v1", "salmorejo-v2"
        ]
    finally:
        await db.close()
