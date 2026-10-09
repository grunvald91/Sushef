"""Пилотные профессиональные карты конкретных блюд.

Основаны на оригинальных списках ингредиентов и приготовления TURESPAÑA.
Механизмы и способы исправления — редакционная кулинарная интерпретация,
не текст первоисточника и не независимо валидированная производственная SOP.
Неведомый фактический выход и температура НЕ выдуманы.
"""
from __future__ import annotations

from .cuisine_catalog import RECIPES
from .technique_catalog import TECHNIQUES

SOURCE_CARDS = {r["id"]: r for r in RECIPES}
TECHNIQUE_IDS = {t["id"] for t in TECHNIQUES}

DISH_CARDS = [
    {
        "id": "gazpacho-v1",
        "recipe_id": "gazpacho",
        "revision": "1",
        "yield_grams": None,
        "servings": 4,
        "equipment": ["нож", "доска", "миска", "блендер"],
        "ingredients": [
            {"name": "спелые помидоры", "quantity": "1000", "unit": "г"},
            {"name": "небольшой зелёный перец", "quantity": "2", "unit": "шт"},
            {"name": "чеснок", "quantity": "2", "unit": "зубчика"},
            {"name": "деревенский хлеб", "quantity": "100", "unit": "г"},
            {"name": "оливковое масло", "quantity": "4", "unit": "ст. л."},
            {"name": "хересный уксус", "quantity": "1", "unit": "ст. л."},
            {"name": "вода кипячёная", "quantity": "по консистенции", "unit": ""},
            {"name": "соль", "quantity": "по вкусу", "unit": ""},
            {"name": "яйцо вкрутую для подачи", "quantity": "по желанию", "unit": ""},
        ],
        "stages": [
            {"action": "Размочить хлеб в кипячёной воде",
             "why": "Размоченный хлеб легче равномерно распределить по овощной основе, помогая добиться плотности супа.",
             "cue": "Хлеб легко разминается без сухой сердцевины.",
             "fix": "Если остаются комочки, дайте хлебу увлажниться и пробейте смесь повторно.",
             "time": None, "temperature": None},
            {"action": "Нарезать овощи, измельчить блендером с размоченным хлебом",
             "why": "Измельчение создаёт общую жидкую основу из овощей и хлеба.",
             "cue": "Смесь без крупных кусочков, цвет равномерный.",
             "fix": "Если остались волокна — дайте блендеру поработать ещё; при желании процедите.",
             "time": None, "temperature": None},
            {"action": "Добавить оливковое масло, хересный уксус, соль и регулировать густоту кипячёной водой",
             "why": "Масло округляет текстуру, уксус добавляет кислотный контраст, вода регулирует плотность.",
             "cue": "Суп легко льётся, вкус сбалансирован, без резкой маслянистости.",
             "fix": "Слишком густо — добавить немного кипячёной воды; чрезмерно жидко — осторожно добавить размоченный хлеб или томатную основу, отмечая это как изменение исходной рецептуры. Кислоту балансировать постепенно.",
             "time": None, "temperature": None},
        ],
        "source_note": "Продукты и базовые этапы из официального Spain.info (включая кипячёную воду и возможную подачу с яйцом). Объяснения «почему» и устранение ошибок — редакция Сушефа; исходная страница не задаёт конечную температуру и измеренный выход.",
        "technique_ids": ["emulsion"],
    },
    {
        "id": "salmorejo-v1",
        "recipe_id": "salmorejo",
        "revision": "1",
        "yield_grams": None,
        "servings": 4,
        "equipment": ["нож", "блендер", "сито", "миска"],
        "ingredients": [
            {"name": "помидоры", "quantity": "1000", "unit": "г"},
            {"name": "чеснок", "quantity": "1", "unit": "зубчик"},
            {"name": "хлеб, предпочтительно вчерашний", "quantity": "200", "unit": "г"},
            {"name": "оливковое масло extra virgin", "quantity": "100", "unit": "г"},
            {"name": "соль", "quantity": "10", "unit": "г"},
            {"name": "варёные яйца и хамон", "quantity": "необязательно", "unit": ""},
        ],
        "stages": [
            {"action": "Пробить томаты блендером и процедить, удаляя кожицу и семена",
             "why": "Процеживание убирает грубые фрагменты, делая текстуру однороднее.",
             "cue": "Получена однородная томатная основа.",
             "fix": "Если есть заметные частички кожицы, повторно процедить.",
             "time": None, "temperature": None},
            {"action": "Размочить хлеб в томатной основе или воде, затем пробить снова",
             "why": "Хлеб участвует в формировании фирменной густой кремовой текстуры.",
             "cue": "Масса густая, но гладкая, без хлебных комков.",
             "fix": "Если слишком грубо — дополнительно увлажнить хлеб и снова пробить.",
             "time": None, "temperature": None},
            {"action": "Добавить масло, чеснок, соль и пробить до гладкости",
             "why": "Масло делает ощущение во рту мягче, а чеснок усиливает ароматический профиль.",
             "cue": "Густая, равномерная, мягкая текстура и сбалансированный вкус.",
             "fix": "Если масса чрезмерно густая, осторожно менять текстуру небольшими порциями томатной основы, обозначая это как адаптацию.",
             "time": None, "temperature": None},
        ],
        "source_note": "Количества и последовательность опираются на Spain.info. Объяснения механизмов и способы исправления — редакционные, а не дословные цитаты. Выход по массе и температура первоисточником не установлены.",
        "technique_ids": ["emulsion"],
    },
]


def validate_dish_cards() -> None:
    ids: set[str] = set()
    for card in DISH_CARDS:
        if card["id"] in ids:
            raise ValueError("Повторяющаяся техкарта блюда")
        ids.add(card["id"])
        recipe = SOURCE_CARDS.get(card["recipe_id"])
        if not recipe or recipe["kind"] != "quantified":
            raise ValueError("Техкарте требуется источник с количественным составом")
        if not card["stages"] or not card["ingredients"] or not card["source_note"]:
            raise ValueError("Неполная техкарта блюда")
        if any(t not in TECHNIQUE_IDS for t in card["technique_ids"]):
            raise ValueError("Техкарта использует неизвестную технологию")
        if any(not {"action", "why", "cue", "fix", "time", "temperature"} <= s.keys()
               for s in card["stages"]):
            raise ValueError("В техкарте отсутствуют диагностические поля")
        if card["yield_grams"] is not None and card["yield_grams"] < 0:
            raise ValueError("Отрицательный выход")
        if card["servings"] != recipe["servings"]:
            raise ValueError("Число порций не совпадает с первоисточником")


def as_row(item: dict) -> dict:
    source = SOURCE_CARDS[item["recipe_id"]]
    return {
        "id": item["id"], "recipe_id": item["recipe_id"],
        "revision": item["revision"], "servings": item["servings"],
        "yield_grams": item["yield_grams"], "equipment": item["equipment"],
        "ingredients": item["ingredients"], "stages": item["stages"],
        "source_url": source["source_url"], "source_publisher": source["publisher"],
        "source_note": item["source_note"], "technique_ids": item["technique_ids"],
        "reviewed_on": "2026-10-09",
    }
