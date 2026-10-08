from __future__ import annotations

import json
from typing import Any

from anthropic import AsyncAnthropic

from .config import Settings
from .prompts import RECIPE_JSON, build_system


class RecipeFormatError(ValueError):
    pass


def normalize_recipe(text: str) -> dict[str, Any]:
    """Проверить форму ответа модели до его использования в UI и сохранения."""
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(text.splitlines()[1:-1]).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise RecipeFormatError("Нет JSON-объекта")
    try:
        data = json.loads(text[start:end + 1])
    except (ValueError, TypeError) as exc:
        raise RecipeFormatError("Некорректный JSON") from exc
    if not isinstance(data, dict):
        raise RecipeFormatError("Ожидался объект")
    title, ingredients, steps = data.get("title"), data.get("ingredients"), data.get("steps")
    if not isinstance(title, str) or not title.strip() or len(title) > 180:
        raise RecipeFormatError("Некорректное название")
    if not isinstance(ingredients, list) or not 1 <= len(ingredients) <= 15:
        raise RecipeFormatError("Некорректные ингредиенты")
    clean_ingredients = []
    for item in ingredients:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"].strip() or not isinstance(item.get("amount"), str):
            raise RecipeFormatError("Ингредиент без названия или количества")
        clean_ingredients.append({"name": item["name"][:120], "amount": item["amount"][:100]})
    if not isinstance(steps, list) or not 1 <= len(steps) <= 10 or any(not isinstance(s, str) or not s.strip() for s in steps):
        raise RecipeFormatError("Некорректные шаги")
    minutes, servings = data.get("time_minutes"), data.get("servings")
    if type(minutes) is not int or not 1 <= minutes <= 1000 or type(servings) is not int or not 1 <= servings <= 50:
        raise RecipeFormatError("Некорректные время или порции")
    notes = data.get("safety_notes", [])
    if not isinstance(notes, list) or any(not isinstance(n, str) for n in notes):
        notes = []
    return {
        "title": title.strip(), "time_minutes": minutes, "servings": servings,
        "ingredients": clean_ingredients,
        "steps": [s[:1200] for s in steps],
        "safety_notes": [n[:400] for n in notes[:5]],
    }


def format_recipe(recipe: dict[str, Any]) -> str:
    lines = [f"🍽 {recipe['title']}", f"⏱ {recipe['time_minutes']} мин • 👥 {recipe['servings']} порц.", "", "Продукты:"]
    lines.extend(f"• {item['name']} — {item['amount']}" for item in recipe["ingredients"])
    lines.append("\nКак готовить:")
    lines.extend(f"{i}. {step}" for i, step in enumerate(recipe["steps"], 1))
    if recipe["safety_notes"]:
        lines.extend(["\nБезопасность:"] + [f"• {n}" for n in recipe["safety_notes"]])
    return "\n".join(lines)


def shopping_list(recipe: dict[str, Any]) -> str:
    return "🛒 Продукты для «" + recipe["title"] + "»:\n" + "\n".join(
        f"☐ {row['name']} — {row['amount']}" for row in recipe["ingredients"]
    ) + "\n\nЭто полный список ингредиентов, а не автоматически рассчитанный список недостающих продуктов."


class Chef:
    def __init__(self, settings: Settings):
        self.model = settings.claudehub_model
        self.max_tokens = settings.max_output_tokens
        self.client = AsyncAnthropic(
            api_key=settings.claudehub_api_key,
            base_url=settings.claudehub_base_url,
            timeout=35.0,
            max_retries=1,
        )

    async def close(self) -> None:
        await self.client.close()

    async def _request(self, system: str, messages: list[dict[str, str]]) -> str:
        result = await self.client.messages.create(
            model=self.model, system=system, max_tokens=self.max_tokens, messages=messages,
        )
        parts = [block.text for block in result.content if getattr(block, "type", None) == "text"]
        answer = "\n".join(parts).strip()
        if not answer:
            raise RuntimeError("Модель вернула пустой ответ")
        return answer

    async def answer(self, mode: str, text: str, preferences: dict, history: list[dict[str, str]], cooking_context: str = "") -> str:
        return await self._request(
            build_system(mode, preferences, cooking_context),
            history[-10:] + [{"role": "user", "content": text}],
        )

    async def recipe(self, text: str, preferences: dict) -> dict[str, Any]:
        output = await self._request(
            build_system("recipe", preferences) + "\n\n" + RECIPE_JSON,
            [{"role": "user", "content": text}],
        )
        return normalize_recipe(output)
