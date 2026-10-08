"""Кулинарная персонализация: явное согласие, структурированные настройки.

Никогда не превращать случайную просьбу «сегодня хочу острое»
в постоянное предпочтение без отдельного подтверждения.
"""
from __future__ import annotations

import re

PROFILE_FIELDS = {
    "allergens": "⚠️ Аллергены",
    "excluded": "🚫 Исключённые продукты",
    "likes": "🥑 Любимые продукты",
    "equipment": "🍳 Техника",
    "portions": "👥 Порции",
    "cuisines": "🌎 Любимые кухни",
    "spice": "🌶 Острота",
    "textures": "🥗 Текстуры",
    "budget": "💰 Бюджет",
    "cook_time": "⏱ Время готовки, мин",
    "skill": "🎓 Кулинарный уровень",
}

MEMORY_KINDS = {
    "taste": "Вкус и сочетания",
    "technique": "Приёмы и навыки",
    "habit": "Кухонные привычки",
    "recipe_tip": "Моя доработка блюда",
}

CHOICES = {
    "spice": {"без острого", "лёгкая", "средняя", "острая"},
    "skill": {"начинающий", "уверенный", "опытный"},
}


def validate_preference(key: str, value: str) -> str:
    if key not in PROFILE_FIELDS:
        raise ValueError("Неизвестный параметр профиля")
    cleaned = value.strip()
    if cleaned == "-":
        return cleaned
    if not cleaned or len(cleaned) > 500:
        raise ValueError("Значение должно содержать от 1 до 500 символов")
    if key == "portions" and (not cleaned.isdigit() or not 1 <= int(cleaned) <= 50):
        raise ValueError("Порции: целое число от 1 до 50")
    if key == "cook_time" and (not cleaned.isdigit() or not 5 <= int(cleaned) <= 720):
        raise ValueError("Время: число минут от 5 до 720")
    if key in CHOICES:
        cleaned = cleaned.casefold()
        if cleaned not in CHOICES[key]:
            raise ValueError(key + ": выберите " + ", ".join(sorted(CHOICES[key])))
    return cleaned


def validate_memory(kind: str, value: str) -> str:
    if kind not in MEMORY_KINDS:
        raise ValueError("Неизвестный тип памяти")
    cleaned = value.strip()
    if not 3 <= len(cleaned) <= 500:
        raise ValueError("Запись должна содержать 3–500 символов")
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", cleaned):
        raise ValueError("Недопустимые символы")
    return cleaned


def short_memory_context(rows: list[dict]) -> list[dict[str, str]]:
    """В системный prompt отправляем только подтверждённые факты, как данные."""
    return [{"kind": r["kind"], "fact": r["value"]}
            for r in rows if r.get("status") == "active"][:20]
