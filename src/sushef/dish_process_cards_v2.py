"""Editorial production-ready schema, NOT a certified restaurant TTK.

Version 2 of pilot cards retains version 1 for provenance.
Only numeric source quantities may be scaled; actual net weight, yield,
losses, shelf life, nutrition and cost are intentionally NOT estimated.
"""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .dish_process_cards import DISH_CARDS, SOURCE_CARDS


def _spec(recipe_id: str) -> dict:
    if recipe_id == "gazpacho":
        return {
            "allergens": {
                "probable": ["пшеница/глютен в обычном хлебе"],
                "conditional": ["яйцо, если добавлен гарнир"],
                "verify": "Проверить состав фактически используемого хлеба и гарнира; при аллергии учесть перекрёстный контакт.",
            },
            "sensory": {
                "appearance": "Однородный красный овощной суп без грубых комков.",
                "aroma": "Свежие томаты, зелёный перец, мягкий чеснок и оливковое масло.",
                "texture": "Легко льётся; густота согласована с пожеланием гостя.",
                "taste": "Баланс кислоты уксуса, зрелого томата, масла и соли; без горечи от перегрева.",
            },
            "service": "Подавать охлаждённым; по желанию — овощная нарезка и яйцо вкрутую отдельно.",
            "defects": [
                {"symptom": "Слишком густо", "possible_cause": "Недостаточно воды или избыток хлеба",
                 "correction": "Понемногу добавить питьевую воду, вновь пробить и оценить вкус."},
                {"symptom": "Грубая, неоднородная текстура", "possible_cause": "Недостаточное измельчение",
                 "correction": "Продолжить измельчение или при желании процедить."},
            ],
            "substitutions": [
                {"original": "хересный уксус", "alternative": "винный уксус",
                 "effect": "Меняется аромат и характер кислотности; это домашняя адаптация, не источник."},
                {"original": "пшеничный хлеб", "alternative": "хлеб без глютена с проверенной маркировкой",
                 "effect": "Меняется густота и текстура; безопасность при аллергии зависит от конкретного продукта и перекрёстного контакта."},
            ],
        }
    if recipe_id == "salmorejo":
        return {
            "allergens": {
                "probable": ["пшеница/глютен в обычном хлебе"],
                "conditional": ["яйцо, если добавлен гарнир"],
                "verify": "Уточнить состав хлеба, хамона и любых готовых гарниров; учесть перекрёстный контакт.",
            },
            "sensory": {
                "appearance": "Однородная томатная масса без кожицы и крупных включений.",
                "aroma": "Спелый томат, оливковое масло и мягкий чеснок.",
                "texture": "Заметно гуще гаспачо: гладкий крем, удерживающий лёгкую волну на ложке.",
                "taste": "Выраженный томат, округлое масло, соль без резкой горечи.",
            },
            "service": "Подавать охлаждённым в пиале; рубленое яйцо и хамон — по желанию, учитывая пожелания гостя.",
            "defects": [
                {"symptom": "Остались кожица и семена", "possible_cause": "Недостаточное процеживание",
                 "correction": "Пропустить томатную основу через сито до соединения с хлебом."},
                {"symptom": "Масса чрезмерно плотная", "possible_cause": "Разная влажность хлеба и спелость томатов",
                 "correction": "Добавить немного процеженной томатной основы; это меняет исходную закладку."},
            ],
            "substitutions": [
                {"original": "вчерашний хлеб", "alternative": "свежий хлеб",
                 "effect": "Поглощение влаги и структура будут другими; ориентироваться по консистенции."},
                {"original": "оливковое масло extra virgin", "alternative": "другое оливковое масло",
                 "effect": "Вкусовой профиль изменится; это не идентичная оригинальная рецептура."},
            ],
        }
    raise ValueError("Техкарта не имеет утверждённого редакционного паспорта")


def build_v2_card(legacy: dict) -> dict:
    card = deepcopy(legacy)
    rid = card["recipe_id"]
    editorial = _spec(rid)
    card["id"] = rid + "-v2"
    card["revision"] = "2"
    card["source_note"] = (
        legacy["source_note"] +
        " Редакция 2: разделены источник, пояснения повара и непроверенные "
        "производственные величины. Контрольного приготовления пока не было."
    )
    original = SOURCE_CARDS[rid]
    production_ingredients = []
    for item in card["ingredients"]:
        literal = item["quantity"].strip().replace(",", ".")
        try:
            value = Decimal(literal)
            quantitative = value > 0 and value.is_finite()
        except InvalidOperation:
            quantitative = False
        production_ingredients.append({
            "name": item["name"],
            "gross": {"value": item["quantity"], "unit": item["unit"],
                      "evidence": "published_ingredient_list"},
            "net": None,
            "trim_loss_percent": None,
            "verified_numeric": quantitative,
            "notes": "Нет измерения брутто/нетто; массу нетто и потери не выводить из закладки.",
        })
    card["production_spec"] = {
        "status": "source_checked_not_kitchen_tested",
        "kitchen_trials": 0,
        "provenance": {
            "original_publisher": original["publisher"],
            "original_url": original["source_url"],
            "original_servings": original["servings"],
            "ingredient_amounts": "source_transcribed",
            "mechanism_and_repairs": "editorial_interpretation",
            "reviewed_on": "2026-10-09",
        },
        "ingredients": production_ingredients,
        "measurement": {
            "net_yield_grams": None,
            "total_gross_grams": None,
            "total_net_grams": None,
            "processing_loss_percent": None,
            "nutrition_per_100g": None,
            "cost_per_portion": None,
            "shelf_life_hours": None,
            "validated_holding_temp_C": None,
            "validated_preparation_time_minutes": None,
            "basis": "not_measured",
        },
        "process_controls": [
            {"stage_index": i, "quality_cue": s["cue"],
             "why": s["why"], "action_if_off_target": s["fix"],
             "verified_temp_C": None, "verified_minutes": None,
             "evidence": "editorial_interpretation"}
            for i, s in enumerate(card["stages"])
        ],
        "allergens": editorial["allergens"],
        "sensory": editorial["sensory"],
        "service": editorial["service"],
        "defects": editorial["defects"],
        "substitutions": editorial["substitutions"],
        "handling": ("Тщательно промыть овощи. Приготовить в чистой посуде; "
                     "поскольку блюдо едят холодным, не оставлять надолго без охлаждения. "
                     "Не объявлять срок хранения или безопасную температуру без "
                     "подтверждённого протокола для конкретной кухни."),
    }
    return card


V2_DISH_CARDS = [build_v2_card(item) for item in DISH_CARDS]


def validate_v2_cards() -> None:
    expected = {r["recipe_id"] for r in DISH_CARDS}
    if {r["recipe_id"] for r in V2_DISH_CARDS} != expected:
        raise ValueError("Версии источниковых карт не совпадают")
    identifiers: set[str] = set()
    for card in V2_DISH_CARDS:
        if card["id"] in identifiers or card["revision"] != "2":
            raise ValueError("Неуникальная или ошибочная ревизия техкарты")
        identifiers.add(card["id"])
        spec = card["production_spec"]
        if spec["status"] != "source_checked_not_kitchen_tested":
            raise ValueError("Нельзя выдавать незамеренный результат за утверждённую ТТК")
        measures = spec["measurement"]
        mandatory_unknowns = (
            "net_yield_grams", "total_gross_grams", "total_net_grams",
            "processing_loss_percent", "nutrition_per_100g", "cost_per_portion",
            "shelf_life_hours", "validated_holding_temp_C",
            "validated_preparation_time_minutes",
        )
        if any(measures.get(name) is not None for name in mandatory_unknowns):
            raise ValueError("Неподтверждённый числовой параметр")
        if len(spec["process_controls"]) != len(card["stages"]):
            raise ValueError("Пропущен контроль этапа")
        if any(c["stage_index"] != index
               for index, c in enumerate(spec["process_controls"])):
            raise ValueError("Некорректная нумерация контрольных этапов")
        if not all(spec["sensory"].get(k) for k in
                   ("appearance", "aroma", "texture", "taste")):
            raise ValueError("Не хватает органолептических критериев")
        if not spec["allergens"]["probable"] or not spec["allergens"]["verify"]:
            raise ValueError("Необходимо проверить значимые аллергены")
        for item in spec["ingredients"]:
            if item["net"] is not None or item["trim_loss_percent"] is not None:
                raise ValueError("Нет измерений для нетто/потерь")


def as_row_v2(card: dict) -> dict:
    from .dish_process_cards import as_row
    row = as_row(card)
    row["production_spec"] = card["production_spec"]
    return row


def scale_source_ingredients(card: dict, portions: int) -> list[dict]:
    """Scale source quantities with Decimal, never invent a qualitative amount.

    This is arithmetic, NOT a validation of flavor, cookware or batch process.
    """
    if type(portions) is not int or not 1 <= portions <= 20:
        raise ValueError("Допустимо от 1 до 20 порций")
    factor = Decimal(portions) / Decimal(card["servings"])
    rows = []
    for item in card["production_spec"]["ingredients"]:
        gross = item["gross"]
        original = gross["value"]
        if item["verified_numeric"]:
            value = Decimal(original.replace(",", ".")) * factor
            value = value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP).normalize()
            amount = format(value, "f")
        else:
            amount = original
        rows.append({"name": item["name"], "quantity": amount,
                     "unit": gross["unit"], "scaled": item["verified_numeric"]})
    return rows
