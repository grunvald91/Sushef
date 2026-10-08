import json

import pytest

from sushef.weekly import WeeklyPlanError, format_day, format_full_week, normalize_weekly_plan


def sample():
    return {
        "days": [{"breakfast": f"Омлет {i}", "lunch": f"Суп {i}",
                  "dinner": f"Рагу {i}"} for i in range(7)],
        "notes": "Часть овощей можно использовать повторно.",
    }


def test_validate_and_format_seven_days():
    plan = normalize_weekly_plan(json.dumps(sample(), ensure_ascii=False))
    assert len(plan["days"]) == 7
    assert "Понедельник" in format_day(plan, 0)
    assert "Воскресенье" in format_day(plan, 6)
    assert "Рагу 5" in format_full_week(plan)


@pytest.mark.parametrize("value", [
    "ответ текстом", '{"days":[]}', '{"days":[{"breakfast":"каша"}]}',
    json.dumps({"days":[{"breakfast":"омлет", "lunch":"суп", "dinner":" "}]*7}),
])
def test_invalid_plan_fails_closed(value):
    with pytest.raises(WeeklyPlanError):
        normalize_weekly_plan(value)
