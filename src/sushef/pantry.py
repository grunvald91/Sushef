"""Разбор количеств и консервативная сверка запасов без догадок о синонимах."""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

PRODUCT_LINE = re.compile(r"^(.{2,70}?)\s+(\d+(?:[.,]\d+)?)\s*(кг|г|л|мл|шт\.?|штук|штуки|штука)\s*$", re.IGNORECASE)
AMOUNT_LINE = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(кг|г|л|мл|шт\.?|штук|штуки|штука)\s*$", re.IGNORECASE)
UNITS = {"кг": ("г", Decimal("1000")), "г": ("г", Decimal(1)),
         "л": ("мл", Decimal("1000")), "мл": ("мл", Decimal(1)),
         "шт": ("шт", Decimal(1)), "шт.": ("шт", Decimal(1)),
         "штук": ("шт", Decimal(1)), "штуки": ("шт", Decimal(1)),
         "штука": ("шт", Decimal(1))}


@dataclass(frozen=True)
class Quantity:
    value: Decimal
    unit: str


def normalize_name(value: str) -> str:
    return " ".join(value.lower().replace("ё", "е").split()).strip(" .,;:—-")


def parse_quantity(raw: str) -> Quantity | None:
    m = AMOUNT_LINE.fullmatch(raw.strip())
    if not m:
        return None
    try:
        amount = Decimal(m.group(1).replace(",", "."))
    except InvalidOperation:
        return None
    if amount <= 0 or amount > Decimal("100000"):
        return None
    unit, factor = UNITS[m.group(2).lower()]
    return Quantity(amount * factor, unit)


def parse_product_line(line: str) -> tuple[str, str, Quantity]:
    m = PRODUCT_LINE.fullmatch(line.strip())
    if not m:
        raise ValueError("Используйте формат «картофель 500 г» или «яйца 4 шт».")
    display_name = m.group(1).strip(" :-—")
    key = normalize_name(display_name)
    if not key or key.isdigit() or len(key) > 70:
        raise ValueError("Укажите понятное название продукта.")
    quantity = parse_quantity(m.group(2) + " " + m.group(3))
    if quantity is None:
        raise ValueError("Некорректное количество продукта.")
    return display_name, key, quantity


def format_quantity(value: Decimal | str, unit: str) -> str:
    number = Decimal(str(value))
    normalized = format(number.normalize(), "f")
    return f"{normalized} {unit}"


def compare_recipe_with_pantry(recipe: dict, pantry_rows: list[dict]) -> list[dict]:
    """Точное совпадение имени и размерности, иначе только ручная проверка.

    Не смешиваем граммы, миллилитры и штуки и не угадываем синонимы.
    """
    stock = {(row["name_key"], row["unit"]): Decimal(str(row["quantity"])) for row in pantry_rows}
    by_name = {row["name_key"] for row in pantry_rows}
    result = []
    for entry in recipe.get("ingredients", []):
        name = entry["name"]
        amount = entry["amount"]
        key = normalize_name(name)
        required = parse_quantity(amount)
        if required is None:
            result.append({"name": name, "required": amount, "missing": None,
                           "status": "check", "reason": "Количество нужно проверить вручную"})
            continue
        available = stock.get((key, required.unit))
        if available is None:
            # При другом названии или единице измерения мы не можем уверенно
            # утверждать, что продукта нет. Пользователю нужен ручной контроль.
            if key in by_name:
                result.append({"name": name, "required": amount, "missing": None,
                               "status": "check", "reason": "Несовместимая единица измерения"})
            else:
                result.append({"name": name, "required": amount,
                               "missing": format_quantity(required.value, required.unit),
                               "status": "missing", "reason": "Точного совпадения в запасах нет"})
            continue
        missing = max(Decimal(0), required.value - available)
        result.append({"name": name, "required": amount,
                       "missing": format_quantity(missing, required.unit) if missing else None,
                       "status": "missing" if missing else "have", "reason": ""})
    return result


def format_shopping_comparison(recipe: dict, pantry_rows: list[dict]) -> str:
    compared = compare_recipe_with_pantry(recipe, pantry_rows)
    lines = ["🛒 Покупки для «" + recipe["title"] + "»:"]
    missing = [r for r in compared if r["status"] == "missing"]
    check = [r for r in compared if r["status"] == "check"]
    have = [r for r in compared if r["status"] == "have"]
    if missing:
        lines.append("\nНужно докупить (если названия указаны одинаково):")
        lines.extend(f"☐ {r['name']} — {r['missing']}" for r in missing)
    if check:
        lines.append("\nНужно проверить самостоятельно:")
        lines.extend(f"❔ {r['name']} — {r['required']} ({r['reason']})" for r in check)
    if have:
        lines.append("\nВ запасах достаточно:")
        lines.extend(f"✅ {r['name']}" for r in have)
    if not missing and not check:
        lines.append("\nВсё по количествам нашлось — проверьте свежесть и состояние продуктов.")
    lines.append("\nСовпадение по названию строгое: «яйцо» и «яйца» могут считаться разными. "
                 "Проверьте список перед покупками; бот не проверяет срок годности.")
    return "\n".join(lines)
