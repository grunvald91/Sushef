from sushef.chef import normalize_recipe, format_recipe
from sushef.timers import (
    normalize_step_timers, suggested_timer, timer_progress, timer_alert,
    TIMER_PRESETS, MIN_MINUTES, MAX_MINUTES,
)
import json


def base_recipe():
    return {
        "title": "Картофель", "servings": 2, "time_minutes": 25,
        "ingredients": [{"name": "Картофель", "amount": "500 г"}],
        "steps": ["Почистить", "Варить", "Слить воду"],
        "step_timers": [{"step_index": 1, "minutes": 15, "label": "Варка в кастрюле"}],
        "safety_notes": [],
    }


def test_model_step_suggestion_survives_validation_and_is_0_indexed():
    result = normalize_recipe(json.dumps(base_recipe(), ensure_ascii=False))
    assert result["step_timers"] == [
        {"step_index": 1, "minutes": 15, "label": "Варка в кастрюле"}
    ]
    assert suggested_timer(result, 0) is None
    assert suggested_timer(result, 1)["minutes"] == 15
    assert "⏱ Можно поставить таймер на 15 мин" in format_recipe(result)


def test_bad_optional_suggestions_do_not_break_recipe_or_start_timers():
    bad = [
        {"step_index": 4, "minutes": 1, "label": "bad step"},
        {"step_index": 1, "minutes": -5, "label": "bad minutes"},
        {"step_index": 1, "minutes": True, "label": "bool is not int"},
        {"step_index": 1, "minutes": 12, "label": "Дождаться кипения"},
        {"step_index": 1, "minutes": 99, "label": "duplicate"},
        {"step_index": 2, "minutes": 241, "label": "too long"},
        {"step_index": 2, "minutes": 1, "label": ""},
    ]
    result = normalize_step_timers(bad, 3)
    assert result == [{"step_index": 1, "minutes": 12, "label": "Дождаться кипения"}]
    recipe = base_recipe()
    recipe["step_timers"] = "unstructured"
    assert normalize_recipe(json.dumps(recipe))["step_timers"] == []
    assert normalize_recipe(json.dumps(base_recipe()))["step_timers"]


def test_notifications_distinguish_reminder_from_food_safety():
    row = {"due_at_ts": 1060, "minutes": 1, "step_index": 0,
           "recipe_title": "Рагу", "label": "Тушить"}
    assert timer_progress(row, now_ts=1000) == "ещё 1 мин"
    assert "время вышло" in timer_progress(row, now_ts=1060)
    alert = timer_alert(row)
    assert "⏰" in alert and "Рагу" in alert
    assert "не означает" in alert and "термометром" in alert
    assert MIN_MINUTES == 1 and MAX_MINUTES == 240
    assert TIMER_PRESETS == (1, 5, 10, 15, 30)


def test_cooking_ui_proposes_timer_without_starting():
    from sushef.bot import cooking_text, cooking_keyboard, timer_choice_keyboard
    session = {"recipe": base_recipe(), "step_index": 1}
    text = cooking_text(session)
    assert "Рекомендуемый таймер" in text and "15 мин" in text
    buttons = {b.callback_data for row in timer_choice_keyboard(session).inline_keyboard
               for b in row}
    assert "timer:start:hint" in buttons
    assert "timer:start:15" in buttons
    assert "timer:custom" in buttons
    active = {b.callback_data for row in cooking_keyboard().inline_keyboard for b in row}
    assert {"cook:timer", "view:timers", "cook:next"}.issubset(active)
    assert "безопасную температуру" in cooking_text({"recipe": base_recipe(), "step_index": 3})
