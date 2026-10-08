"""Source-neutral step timers: recipe advice is not a food-safety clearance.

LLM may propose one *optional* countdown per step, but only explicit user
action starts it. Never confuse elapsed minutes with safe food temperatures.
"""
from __future__ import annotations

from math import ceil
from time import time
from typing import Any

MIN_MINUTES = 1
MAX_MINUTES = 240
MAX_ACTIVE_TIMERS = 5
TIMER_PRESETS = (1, 5, 10, 15, 30)


def normalize_step_timers(items: object, step_count: int) -> list[dict[str, Any]]:
    """Validate suggestions without rejecting a valid recipe on bad optional hints."""
    if not isinstance(items, list):
        return []
    cleaned: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in items[:20]:
        if not isinstance(item, dict):
            continue
        index, minutes, label = item.get("step_index"), item.get("minutes"), item.get("label")
        if type(index) is not int or not 0 <= index < step_count or index in seen:
            continue
        if type(minutes) is not int or not MIN_MINUTES <= minutes <= MAX_MINUTES:
            continue
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 120:
            continue
        seen.add(index)
        cleaned.append({"step_index": index, "minutes": minutes, "label": label.strip()})
    return cleaned


def suggested_timer(recipe: dict, step_index: int) -> dict[str, Any] | None:
    steps = recipe.get("steps", [])
    if not isinstance(steps, list) or not 0 <= step_index < len(steps):
        return None
    for timer in normalize_step_timers(recipe.get("step_timers", []), len(steps)):
        if timer["step_index"] == step_index:
            return timer
    return None


def timer_progress(record: dict, now_ts: int | None = None) -> str:
    now_ts = int(time()) if now_ts is None else now_ts
    seconds = record["due_at_ts"] - now_ts
    if seconds <= 0:
        return "время вышло — уведомление будет отправлено ботом"
    return f"ещё {ceil(seconds / 60)} мин"


def timer_alert(record: dict) -> str:
    return (
        f"⏰ Сушеф: таймер завершён!\n"
        f"🍲 {record['recipe_title']} · шаг {record['step_index'] + 1}\n"
        f"⏱ {record['minutes']} мин: {record['label']}\n\n"
        "Проверьте блюдо. Истечение времени не означает, что продукты "
        "достигли безопасной температуры или нужной готовности. "
        "При необходимости измерьте температуру пищевым термометром. "
        "Переход к следующему шагу — только по Вашему решению."
    )


def timer_start_text(minutes: int, label: str) -> str:
    return (
        f"⏱ Таймер на {minutes} мин запущен: {label}\n"
        "Он сохранён в базе и должен сработать даже после перезапуска бота "
        "(если бот снова работает и может доставить Telegram-сообщение)."
    )
