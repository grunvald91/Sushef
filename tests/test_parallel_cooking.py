"""Parallel guided cooking: overlapping timers without claiming automatic scheduling."""
import json

from sushef.bot import cooking_text
from sushef.chef import format_recipe, normalize_recipe
from sushef.prompts import RECIPE_JSON
from sushef.timers import normalize_step_overlaps, suggested_overlap


def fish_and_vegetables():
    return {
        "title": "Горбуша с овощами",
        "time_minutes": 55,  # e.g. 17 min prep + 20 min vegetables + 18 min fish
        "servings": 2,
        "ingredients": [
            {"name": "горбуша", "amount": "400 г"},
            {"name": "овощи", "amount": "400 г"},
        ],
        "steps": [
            "Подготовьте овощи и рыбу до запуска духовки, приправьте рыбу и уберите в холодильник.",
            "Поставьте овощи в духовку и запустите таймер на 20 минут. Рыба пока охлаждается.",
            "Пока запекаются овощи, подготовьте соус и посуду для подачи.",
            "Когда овощи запекались 20 минут и рыба отдохнула не менее 15 минут, "
            "добавьте рыбу и запекайте 18 минут. Проверьте готовность.",
        ],
        "step_timers": [
            {"step_index": 1, "minutes": 20, "label": "Запекание овощей"},
            {"step_index": 3, "minutes": 18, "label": "Запекание рыбы"},
        ],
        "step_overlaps": [
            {
                "step_index": 2,
                "while_step_index": 1,
                "label": "Подготовьте соус, пока овощи запекаются",
            }
        ],
        "safety_notes": [],
    }


def test_overlap_survives_validation_and_is_visible_in_recipe_and_steps():
    recipe = normalize_recipe(json.dumps(fish_and_vegetables(), ensure_ascii=False))
    assert recipe["step_overlaps"][0]["while_step_index"] == 1
    assert suggested_overlap(recipe, 2)["step_index"] == 2
    assert suggested_overlap(recipe, 1) is None
    assert "Параллельно с таймером шага 2" in format_recipe(recipe)
    step = cooking_text({"recipe": recipe, "step_index": 2})
    assert "Пока идёт таймер шага 2" in step
    assert "Таймер запускается по кнопке" in step


def test_invalid_or_impossible_step_references_are_discarded():
    timers = [{"step_index": 1, "minutes": 20, "label": "Запекание"}]
    candidates = [
        {"step_index": 0, "while_step_index": 1, "label": "future"},
        {"step_index": 2, "while_step_index": 0, "label": "no timer"},
        {"step_index": 2, "while_step_index": True, "label": "boolean"},
        {"step_index": 2, "while_step_index": 1, "label": "Пока идёт запекание"},
        {"step_index": 2, "while_step_index": 1, "label": "duplicate"},
        {"step_index": 3, "while_step_index": 1, "label": "outside steps"},
    ]
    assert normalize_step_overlaps(candidates, 3, timers) == [
        {"step_index": 2, "while_step_index": 1, "label": "Пока идёт запекание"}
    ]
    assert normalize_step_overlaps({}, 3, timers) == []


def test_old_recipes_work_without_parallel_metadata():
    payload = fish_and_vegetables()
    payload.pop("step_overlaps")
    recipe = normalize_recipe(json.dumps(payload, ensure_ascii=False))
    assert recipe["step_overlaps"] == []
    assert suggested_overlap(recipe, 2) is None


def test_prompt_requires_parallel_planning_and_real_dependencies():
    assert "ПЛАНИРОВАНИЕ ГОТОВКИ" in RECIPE_JSON
    assert "не требуй «подготовить рыбу за 5 минут»" in RECIPE_JSON
    assert "time_minutes — примерное общее время" in RECIPE_JSON
    assert "Сырую рыбу при ожидании держи охлаждённой" in RECIPE_JSON
