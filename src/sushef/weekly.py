"""Схема недельного меню и форматирование сохранённого плана."""
from __future__ import annotations

import json

DAY_NAMES = ("Понедельник", "Вторник", "Среда", "Четверг", "Пятница", "Суббота", "Воскресенье")
MEAL_NAMES = ("Завтрак", "Обед", "Ужин")

WEEKLY_JSON = """Составь недельное меню и ответь ТОЛЬКО одним JSON без пояснений:
{
  "days": [
    {"breakfast": "Название блюда", "lunch": "Название блюда", "dinner": "Название блюда"}
  ],
  "notes": "Краткие рекомендации по подготовке и повторному использованию продуктов"
}
Строго 7 объектов days по порядку с понедельника, в каждом breakfast/lunch/dinner.
Соблюдай ограничения пользователя (особенно аллергены), избегай опасных рекомендаций.
Не придумывай стоимость, нутриенты или гарантии отсутствия аллергенов.
Пиши по-русски. Все названия лаконичны, примерно до 65 символов.
Не включай детальные рецепты или подсчёт продуктов: по выбранному блюду
можно отдельно построить точный рецепт и список покупок.
"""


class WeeklyPlanError(ValueError):
    pass


def normalize_weekly_plan(text: str) -> dict:
    data = text.strip()
    if data.startswith("```"):
        data = "\n".join(data.splitlines()[1:-1]).strip()
    try:
        data = json.loads(data)
    except (ValueError, TypeError) as exc:
        raise WeeklyPlanError("Не удалось разобрать меню") from exc
    if not isinstance(data, dict) or not isinstance(data.get("days"), list) or len(data["days"]) != 7:
        raise WeeklyPlanError("Меню должно содержать 7 дней")
    days = []
    for row in data["days"]:
        if not isinstance(row, dict):
            raise WeeklyPlanError("Некорректный день")
        cleaned = {}
        for meal in ("breakfast", "lunch", "dinner"):
            value = row.get(meal)
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= 160:
                raise WeeklyPlanError("Не хватает блюда")
            cleaned[meal] = value.strip()
        days.append(cleaned)
    notes = data.get("notes", "")
    return {"days": days, "notes": notes[:700] if isinstance(notes, str) else ""}


def format_day(plan: dict, day_index: int) -> str:
    if not 0 <= day_index < 7:
        raise ValueError("Номер дня вне диапазона")
    day = plan["days"][day_index]
    return (f"📅 {DAY_NAMES[day_index]}\n\n"
            f"🌅 Завтрак: {day['breakfast']}\n"
            f"🍲 Обед: {day['lunch']}\n"
            f"🍽 Ужин: {day['dinner']}")


def format_full_week(plan: dict) -> str:
    lines = ["📅 Ваше меню на неделю"]
    for idx in range(7):
        lines.append("\n" + format_day(plan, idx))
    if plan.get("notes"):
        lines.append("\nСоветы Сушефа: " + plan["notes"])
    return "\n".join(lines)
