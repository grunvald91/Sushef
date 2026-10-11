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


def normalize_step_overlaps(
    items: object, step_count: int, timers: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Keep only feasible references to an earlier step with a timer.

    This validates the metadata, not the physical feasibility of a recipe:
    ingredient prep times and cooking constraints still require a real plan.
    """
    if not isinstance(items, list):
        return []
    timer_indices = {timer["step_index"] for timer in timers}
    cleaned: list[dict[str, Any]] = []
    seen: set[int] = set()
    for item in items[:20]:
        if not isinstance(item, dict):
            continue
        index = item.get("step_index")
        earlier = item.get("while_step_index")
        label = item.get("label")
        if (type(index) is not int or type(earlier) is not int
                or not 0 <= earlier < index < step_count
                or earlier not in timer_indices or index in seen):
            continue
        if not isinstance(label, str) or not 1 <= len(label.strip()) <= 120:
            continue
        seen.add(index)
        cleaned.append({
            "step_index": index,
            "while_step_index": earlier,
            "label": label.strip(),
        })
    return cleaned


def suggested_overlap(recipe: dict, step_index: int) -> dict[str, Any] | None:
    steps = recipe.get("steps", [])
    if not isinstance(steps, list) or not 0 <= step_index < len(steps):
        return None
    timers = normalize_step_timers(recipe.get("step_timers", []), len(steps))
    for item in normalize_step_overlaps(recipe.get("step_overlaps", []), len(steps), timers):
        if item["step_index"] == step_index:
            return item
    return None


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
        "Проверьте вкус, текстуру и готовность блюда. "
        "Если готовите птицу или другое блюдо, где нужен контроль температуры, "
        "воспользуйтесь термометром. Следующий шаг — по Вашему решению."
    )


def timer_start_text(minutes: int, label: str) -> str:
    return (
        f"⏱ Таймер на {minutes} мин запущен: {label}\n"
        "Он сохранён в базе и должен сработать даже после перезапуска бота "
        "(если бот снова работает и может доставить Telegram-сообщение)."
    )
