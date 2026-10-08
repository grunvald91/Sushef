from decimal import Decimal

import pytest

from sushef.pantry import (
    compare_recipe_with_pantry, format_quantity, format_shopping_comparison,
    normalize_name, parse_product_line, parse_quantity,
)


def test_units_convert_without_float_rounding():
    assert parse_quantity("1,5 кг").value == Decimal("1500")
    assert parse_quantity("0.75 л").value == Decimal("750")
    assert parse_quantity("2 шт.").unit == "шт"
    assert format_quantity(Decimal("1000"), "г") == "1000 г"


def test_parse_pantry_and_normalize():
    label, key, q = parse_product_line("Картофель 1,25 кг")
    assert label == "Картофель"
    assert key == normalize_name("картофель")
    assert q.value == Decimal("1250")
    assert q.unit == "г"


@pytest.mark.parametrize("line", ["молоко", "яйца -3 шт", "картофель 0 г", "крупа 100 ведер", "123 4 шт"])
def test_invalid_pantry_entries_rejected(line):
    with pytest.raises(ValueError):
        parse_product_line(line)


def test_compare_stock_and_remainder():
    recipe = {"title": "Пюре", "ingredients": [
        {"name": "Картофель", "amount": "1,5 кг"},
        {"name": "Молоко", "amount": "200 мл"},
        {"name": "Соль", "amount": "по вкусу"},
    ]}
    stock = [
        {"name_key": "картофель", "unit": "г", "quantity": "700"},
        {"name_key": "молоко", "unit": "мл", "quantity": "300"},
    ]
    rows = compare_recipe_with_pantry(recipe, stock)
    assert rows[0]["status"] == "missing"
    assert rows[0]["missing"] == "800 г"
    assert rows[1]["status"] == "have"
    assert rows[2]["status"] == "check"
    assert "800 г" in format_shopping_comparison(recipe, stock)


def test_conservative_matching_avoids_false_equivalence():
    recipe = {"title": "Яичница", "ingredients": [
        {"name": "яйцо", "amount": "2 шт"},
        {"name": "вода", "amount": "500 мл"},
    ]}
    stock = [
        {"name_key": "яйца", "unit": "шт", "quantity": "4"},
        {"name_key": "вода", "unit": "г", "quantity": "500"},
    ]
    rows = compare_recipe_with_pantry(recipe, stock)
    assert rows[0]["status"] == "missing"
    assert rows[1]["status"] == "check"
