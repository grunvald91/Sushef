"""Source-provenance, catalogue seed, privacy and recipe lookup tests."""
from urllib.parse import urlparse

import pytest

from sushef.bot import cuisine_recipe_text, cuisines_keyboard, cuisines_group_keyboard, source_reference
from sushef.cuisine_catalog import CUISINES, CUISINE_GROUPS, RECIPES, CHECKED_ON, as_row, validate_seed
from sushef.storage import Storage
from sushef.chef import format_recipe


def test_sources_are_explicit_and_have_distinct_evidence_levels():
    validate_seed()
    assert len(RECIPES) >= 23
    assert len(CUISINES) >= 12
    assert len({row["id"] for row in RECIPES}) == len(RECIPES)
    assert any(row.get("source_type") == "public_domain_book" for row in RECIPES)
    assert {row["kind"] for row in RECIPES} == {"quantified", "reference"}
    for record in RECIPES:
        assert record["id"] and len("catalog:" + record["id"]) <= 32
        assert record["publisher"]
        url = urlparse(record["source_url"])
        assert url.scheme == "https"
        assert as_row(record)["reviewed_on"] == CHECKED_ON
        assert len(("cuisine:make:" + record["id"]).encode("utf-8")) <= 64


def test_invalid_editorial_seed_is_rejected_even_without_asserts(monkeypatch):
    import sushef.cuisine_catalog as catalog
    duplicate = dict(RECIPES[0])
    monkeypatch.setattr(catalog, "RECIPES", RECIPES + [duplicate])
    with pytest.raises(ValueError, match="ID"):
        catalog.validate_seed()
    broken = dict(RECIPES[0], id="bad-source", source_url="http://not-https.example")
    monkeypatch.setattr(catalog, "RECIPES", RECIPES + [broken])
    with pytest.raises(ValueError, match="ссылка"):
        catalog.validate_seed()



def test_cuisine_ui_does_not_claim_every_recipe_is_quantified():
    controls = {b.callback_data for line in cuisines_keyboard().inline_keyboard for b in line}
    assert "cuisine:group:mediterranean" in controls
    assert "cuisine:group:eastern" in controls
    assert "cuisine:list:japanese" in {
        b.callback_data for line in cuisines_group_keyboard("eastern").inline_keyboard
        for b in line
    }
    assert "cuisine:list:spanish" in {
        b.callback_data for line in cuisines_group_keyboard("mediterranean").inline_keyboard
        for b in line
    }
    assert all(key in CUISINES for _, keys in CUISINE_GROUPS.values() for key in keys)
    full = next(row for row in RECIPES if row["id"] == "gazpacho")
    cultural = next(row for row in RECIPES if row["id"] == "pesto")
    assert "есть пропорции" in cuisine_recipe_text(as_row(full))
    assert "без полной количественной" in cuisine_recipe_text(as_row(cultural))
    assert full["source_url"] in source_reference(as_row(full))
    assert "адаптация" in source_reference(as_row(full)).casefold()
    assert "не приводит" in source_reference(as_row(cultural))


def test_adapted_output_displays_its_origin():
    result = {
        "title": "Домашний гаспачо",
        "ingredients": [{"name": "помидоры", "amount": "500 г"}],
        "steps": ["Взбить овощи."],
        "time_minutes": 15, "servings": 2, "safety_notes": [],
        "catalog_reference": {"publisher": "TURESPAÑA · Spain.info",
                              "source_url": "https://www.spain.info/en/recipe/gazpacho/",
                              "adapted": True},
    }
    displayed = format_recipe(result)
    assert "По мотивам источника" in displayed
    assert "Это адаптация" in displayed
    assert "www.spain.info" in displayed


@pytest.mark.asyncio
async def test_catalog_persists_and_does_not_interfere_with_personal_data(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'catalog.db'}"
    db = Storage(url)
    await db.create_tables()
    try:
        spanish = await db.cuisine_recipes("spanish")
        japanese = await db.cuisine_recipes("japanese")
        assert len(spanish) >= 4 and len(japanese) >= 3
        assert await db.cuisine_recipe("not-real") is None
        assert await db.cuisine_recipes("not-a-cuisine") == []
        assert (await db.cuisine_recipe("gazpacho"))["source_url"].startswith("https://")
        assert await db.seed_cuisines() == 0

        await db.set_preference(501, "allergens", "орехи")
        assert (await db.get_user(502))["preferences"] == {}
        suggestions = await db.cuisine_matches("хочу гаспачо с помидорами")
        assert suggestions and suggestions[0]["id"] == "gazpacho"
        assert await db.cuisine_matches("абстрактная ситуация без еды") == []
        await db.delete_user(501)
        assert len(await db.cuisine_recipes("spanish")) == len(spanish)
    finally:
        await db.close()

    second = Storage(url)
    try:
        assert (await second.cuisine_recipe("gazpacho"))["kind"] == "quantified"
    finally:
        await second.close()
