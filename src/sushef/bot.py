"""Telegram-интерфейс MVP. Все пользовательские состояния хранятся в БД."""
from __future__ import annotations

import json
import logging
from decimal import Decimal
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .chef import Chef, RecipeFormatError, format_recipe
from .timers import TIMER_PRESETS, MAX_MINUTES, suggested_timer, timer_progress, timer_start_text
from .memory import MEMORY_KINDS, PROFILE_FIELDS, short_memory_context
from .personalization import STYLE_LABELS, communication_summary, example, style_comparison, welcome_back
from .fermentation import PROCESS_LABELS, fermentation_system_context, intake_text
from .fermentation_journal import SAFETY_REMINDER, observation_text, parse_observation
from .protocols import assess_process, get_protocol, list_protocols, protocol_context, protocol_summary
from .science_library import get_knowledge, knowledge_context, knowledge_text, list_knowledge
from .pantry import format_quantity, format_shopping_comparison, parse_product_line
from .weekly import DAY_NAMES, MEAL_NAMES, WeeklyPlanError, format_day, format_full_week
from .cuisine_catalog import CUISINES, CUISINE_GROUPS
from .technique_catalog import CATEGORIES, technique_context
from .dish_process_cards_v2 import scale_source_ingredients
from .config import Settings
from .telegram_format import telegram_chunks
from .storage import Storage

logger = logging.getLogger(__name__)
router = Router(name="telegram")

PREF_LABELS = PROFILE_FIELDS

MODE_PROMPTS = {
    "recipe": "🥘 Перечислите продукты, из которых хочется приготовить блюдо. Добавьте пожелания по времени или вкусу.",
    "rescue": "🆘 Расскажите, какое блюдо не удалось и что именно пошло не так. Вместе найдём честный способ исправить ситуацию!",
    "plan": "📅 Укажите количество человек, бюджет, ограничения и сколько времени готовы тратить на готовку. Я составлю меню из 21 блюда на семь дней.",
    "ask": "💬 Спрашивайте о чём угодно кулинарном. Я здесь, чтобы помогать и делать кухню чуточку веселее!",
}


def keyboard(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=label, callback_data=data) for label, data in row]
            for row in rows
        ]
    )


def main_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [("🥘 Что приготовить?", "mode:recipe"), ("🆘 Спасти блюдо", "mode:rescue")],
        [("📅 Меню на неделю", "mode:plan"), ("👨‍🍳 Готовим вместе", "cook:start")],
        [("❤️ Мои рецепты", "view:favorites"), ("🛒 Покупки", "view:shop")],
        [("📖 История рецептов", "view:archive"), ("🧠 Моя память", "view:memory")],
        [("📦 Мои продукты", "view:pantry"), ("📆 Моё меню", "view:week")],
        [("🥗 Мой профиль", "view:profile"), ("💬 Спросить шефа", "mode:ask")],
        [("🌍 Кухни мира и первоисточники", "view:cuisines")],
        [("🧪 Технология вкуса", "view:techniques")],
        [("🔬 Микробиология и ферментация", "view:ferment")],
    ])


def welcome_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [("🌷 Познакомимся", "hello:start")],
        [("🍳 Сразу к готовке", "hello:skip")],
    ])


def address_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [("На «вы»", "hello:address:вы"), ("На «ты»", "hello:address:ты")],
        [("🍳 Позже", "hello:skip")],
    ])


def style_keyboard() -> InlineKeyboardMarkup:
    return keyboard(
        [[(label, "hello:style:" + key)] for key, label in STYLE_LABELS.items()] +
        [[("🎨 Свой стиль или сочетание", "hello:custom")],
         [("🍳 Пока к готовке", "hello:skip")]]
    )


def communication_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [("✏️ Как обращаться", "hello:edit:name")],
        [("🤝 На «ты» или «вы»", "hello:edit:address")],
        [("🎭 Выбрать стиль с примерами", "hello:styles")],
        [("🥗 Мой профиль", "view:profile"), ("🏠 Меню", "view:main")],
    ])


def cuisines_keyboard() -> InlineKeyboardMarkup:
    buttons = [[(label, "cuisine:group:" + group)]
               for group, (label, _) in CUISINE_GROUPS.items()]
    buttons.extend([[("🌐 Все 12 национальных кухонь", "cuisine:group:all")],
                    [("🏠 Главное меню", "view:main")]])
    return keyboard(buttons)


def cuisines_group_keyboard(group: str) -> InlineKeyboardMarkup:
    if group == "all":
        keys = tuple(CUISINES)
    else:
        group_entry = CUISINE_GROUPS.get(group)
        keys = group_entry[1] if group_entry else ()
    rows = [[(CUISINES[key][0], "cuisine:list:" + key)] for key in keys]
    rows.append([("🌍 К группам кухонь", "view:cuisines")])
    return keyboard(rows)


def cuisine_recipe_text(row: dict) -> str:
    level = ("📐 В источнике есть пропорции" if row["kind"] == "quantified"
             else "📝 Описание традиции без полной количественной раскладки")
    amount = f" · {row['servings']} порций" if row.get("servings") else ""
    ingredients = "\n".join("• " + i for i in row["ingredients"])
    return (f"🌍 {row['title']} — {row['cuisine_label']} ({row['region']})\n"
            f"{level}{amount}\n\n"
            f"Продукты:\n{ingredients}\n\n"
            f"Технологическая идея:\n{row['method']}\n\n"
            f"Источник: {row['publisher']}\n{row['source_url']}\n"
            f"Сверено: {row['reviewed_on']}\n\n"
            "Если мы изменим состав или пропорции, это будет наша адаптация, а не оригинал источника.")


def source_reference(row: dict) -> str:
    """Compact source grounding without misrepresenting the author's published text."""
    measure_note = ("Пропорции приведены в первоисточнике."
                    if row["kind"] == "quantified"
                    else "Источник не приводит полную количественную рецептуру: числа нужно подбирать отдельно.")
    return (
        f"Подтверждённая справочная карточка: {row['title']} ({row['region']}).\n"
        f"Продукты из источника: {', '.join(row['ingredients'])}.\n"
        f"Краткое независимое изложение принципа: {row['method']}\n"
        f"{measure_note}\n"
        f"Первоначальный источник: {row['publisher']} — {row['source_url']}\n"
        "Не называй свои изменения аутентичным рецептом источника. "
        "Если возможны замены, объясни, что это адаптация. "
        "Не считай блюдо безопасным для аллергика без отдельной проверки."
    )


def technique_categories_keyboard() -> InlineKeyboardMarkup:
    rows = [[(label, "technique:category:" + key)] for key, label in CATEGORIES.items()]
    rows.append([("🏠 Главное меню", "view:main")])
    return keyboard(rows)


def technique_card_text(item: dict) -> str:
    lines = [
        f"🧪 {item['title']}", f"Цель: {item['outcome']}", "",
        "Почему это работает:", item["mechanism"], "",
        "Что контролируем:",
    ]
    lines.extend("• " + x for x in item["controls"])
    lines.extend(["", "Признаки хорошего результата:"])
    lines.extend("• " + x for x in item["cues"])
    lines.extend(["", "Если пошло не так:"])
    for p in item["problems"]:
        lines.append(f"• {p['symptom']} → {p['repair']}")
    lines.extend(["", "Границы применения: " + item["limits"], "",
                  f"Источник: {item['source_publisher']}",
                  item["source_url"], f"Сверено: {item['reviewed_on']}"])
    return "\n".join(lines)


def dish_process_card_text(row: dict) -> str:
    yield_text = (f"{row['yield_grams']} г" if row["yield_grams"] is not None
                  else "не указан в первоисточнике")
    lines = [
        "📋 Профессиональная техкарта блюда · редакция " + row["revision"],
        f"Порции: {row['servings']} · Выход: {yield_text}",
        "Инвентарь: " + ", ".join(row["equipment"]), "",
        "Сырьё и закладка:",
    ]
    lines.extend("• " + i["name"] + ": " + i["quantity"] + " " + i["unit"]
                 for i in row["ingredients"])
    lines.extend(["", "Технология и контроль:"])
    for index, stage in enumerate(row["stages"], 1):
        lines.extend([
            f"{index}. {stage['action']}",
            "   Почему: " + stage["why"],
            "   Признак: " + stage["cue"],
            "   Если не выходит: " + stage["fix"],
        ])
    lines.extend(["", "Примечание: " + row["source_note"], "",
                  "Источник раскладки: " + row["source_publisher"],
                  row["source_url"]])
    return "\n".join(lines)


def production_overview(row: dict) -> str:
    """Short editorial passport, avoids calling an untested card an approved TTK."""
    spec = row.get("production_spec")
    if not spec:
        return dish_process_card_text(row)
    meta = spec["measurement"]
    lines = [
        "📋 Техкарта блюда · редакция " + row["revision"],
        "📝 Проверен состав по источнику; производственные измерения ещё не выполнены.",
        f"Порций по источнику: {row['servings']}",
        "Выход блюда: " + (str(meta["net_yield_grams"]) + " г"
                           if meta["net_yield_grams"] is not None
                           else "не измерен"),
        "Нетто/потери сырья: не измерены",
        "Оборудование: " + ", ".join(row["equipment"]), "",
        "Закладка на исходное число порций:",
    ]
    for ingredient in spec["ingredients"]:
        amount = ingredient["source_amount"]
        lines.append("• " + ingredient["name"] + ": " +
                     amount["value"] + " " + amount["unit"])
    lines.extend([
        "", "По первоисточнику подтверждены ингредиенты и их исходные количества.",
        "Причины процессов, контрольные признаки, исправления и замены — "
        "редакционная интерпретация Сушефа.",
        "", "Источник: " + row["source_publisher"], row["source_url"],
    ])
    return "\n".join(lines)


def production_stage_text(row: dict, index: int) -> str:
    stages = row["stages"]
    if index < 0 or index >= len(stages):
        raise ValueError("Неизвестный этап технологической карты")
    step = stages[index]
    controls = (row.get("production_spec") or {}).get("process_controls", [])
    control = controls[index] if index < len(controls) else {}
    temperature = control.get("verified_temp_C")
    duration = control.get("verified_minutes")
    regimes = []
    if temperature is not None:
        regimes.append(f"температура {temperature} °C")
    if duration is not None:
        regimes.append(f"время {duration} мин")
    return "\n".join([
        f"👨‍🍳 {index + 1}/{len(stages)} — {step['action']}",
        "", "💡 Почему это работает:", step["why"],
        "", "👀 Контрольный признак:", step["cue"],
        "", "🛠 Если не получилось:", step["fix"],
        "",
        "Измеренные режимы: " +
        (", ".join(regimes) if regimes else
         "не заданы для этого этапа в проверенной техкарте."),
        "Контрольные признаки качества не подтверждают безопасность продукта.",
    ])


def production_quality_text(row: dict) -> str:
    spec = row.get("production_spec")
    if not spec:
        return "Полный паспорт качества пока не заполнен."
    sensory = spec["sensory"]
    allergies = spec["allergens"]
    lines = [
        "🔎 Контроль качества · " + row["recipe_id"],
        "Вид: " + sensory["appearance"],
        "Аромат: " + sensory["aroma"],
        "Текстура: " + sensory["texture"],
        "Вкус: " + sensory["taste"],
        "", "Возможные аллергены: " + "; ".join(allergies["probable"]),
        "Зависят от подачи: " + "; ".join(allergies["conditional"]),
        allergies["verify"],
        "", "Подача: " + spec["service"],
        "Обращение и хранение: " + spec["handling"],
        "Срок хранения: не валидирован для конкретной рецептуры.",
        "", "Замены и их последствия:",
    ]
    for change in spec["substitutions"]:
        lines.append("• " + change["original"] + " → " + change["alternative"] +
                     ": " + change["effect"])
    lines.append("\nТипичные дефекты и исправления:")
    for defect in spec["defects"]:
        lines.append("• " + defect["symptom"] + " — " + defect["possible_cause"] +
                     "; исправление: " + defect["correction"])
    return "\n".join(lines)


def production_scale_text(row: dict, portions: int) -> str:
    ingredients = scale_source_ingredients(row, portions)
    lines = [
        f"⚖️ {row['recipe_id']} — закладка на {portions} порц.",
        "Математический пересчёт с исходных " + str(row["servings"]) + " порций.",
        "Он не подтверждает автоматически нужную густоту, количество соли или технологический режим.",
        "",
    ]
    for ing in ingredients:
        lines.append("• " + ing["name"] + ": " + ing["quantity"] + " " + ing["unit"] +
                     ("" if ing["scaled"] else " (уточнить вручную)"))
    lines.append("\nНужно заново проверить вкус, текстуру и фактический выход после приготовления.")
    return "\n".join(lines)


def production_keyboard(slug: str, stage: int = 0) -> InlineKeyboardMarkup:
    return keyboard([
        [("💡 Этапы и почему", f"cuisine:tcstage:{slug}:{stage}")],
        [("👀 Качество и аллергены", "cuisine:tcquality:" + slug)],
        [("⚖️ На 2 порции", f"cuisine:tcscale:{slug}:2"),
         ("На 6 порций", f"cuisine:tcscale:{slug}:6")],
        [("👨‍🍳 Приготовить по мотивам", "cuisine:make:" + slug)],
        [("↩️ К блюду", "cuisine:open:" + slug)],
    ])


def dish_process_context(row: dict) -> str:
    """Source quantities vs. editorial interpretations are explicitly separated."""
    stages = []
    for stage in row["stages"]:
        stages.append(stage["action"] + " → " + stage["why"] +
                      " Признак: " + stage["cue"])
    spec = row.get("production_spec") or {}
    sensory = spec.get("sensory") or {}
    editorial = (
        " Дополнительные редакторские критерии: консистенция — " +
        sensory.get("texture", "") + "; вкус — " + sensory.get("taste", "") + "."
        if sensory else ""
    )
    return (
        f"Карта исходного блюда {row['recipe_id']} версии {row['revision']} "
        f"на {row['servings']} порций. "
        "Проверенная закладка из первоисточника (не автоматически брутто/нетто): " +
        "; ".join(i["name"] + " " + i["quantity"] + " " + i["unit"]
                  for i in row["ingredients"]) + ". " +
        "Технологические пояснения редакции: " + "; ".join(stages) + "." +
        editorial +
        " Все замены и пересчитанные порции обозначай адаптацией. "
        "Не называй карту утверждённой ресторанной ТТК: лабораторной/производственной "
        "валидации нет. Не выдумывай массу выхода, закупочный вес, срок хранения "
        "или температуру без достоверных измерений и источников."
    )


def cooking_insight_text(session: dict, focus: str = "why") -> str:
    index = session["step_index"]
    insights = session["recipe"].get("step_insights", [])
    data = next((entry for entry in insights
                 if isinstance(entry, dict) and entry.get("step_index") == index), None)
    if not data:
        return ("Для этого шага ещё нет отдельной технологической заметки. "
                "Задайте вопрос обычным сообщением — разберёмся вместе.")
    if focus == "fix":
        problem = data.get("fix") or ""
        return ("🛠 Если что-то пошло не так:\n\n" + problem if problem
                else "Опишите, что именно не получилось — подберу способ исправления.")
    return ("💡 Почему этот шаг важен:\n\n" + data["why"] +
            ("\n\n👀 На что смотреть:\n" + data["cue"] if data.get("cue") else ""))


def recipe_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [("👨‍🍳 Готовим пошагово", "cook:start")],
        [("❤️ Сохранить рецепт", "recipe:save"), ("🛒 Список продуктов", "view:shop")],
        [("😋 Оценить результат", "view:rating")],
        [("🏠 Главное меню", "view:main")],
    ])


def fermentation_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [("❄️ Холодная ферментация", "ferment:guide:cold")],
        [("🌡 Тёплая/горячая ферментация", "ferment:guide:warm")],
        [("🥬 Молочнокислые овощи", "ferment:guide:vegetables")],
        [("🥛 Йогурт и молочные", "ferment:guide:dairy")],
        [("🍞 Закваски и тесто", "ferment:guide:sourdough")],
        [("🍄 Кодзи и пищевые грибные культуры", "ferment:guide:koji")],
        [("🧪 Внешние пищевые ферменты", "ferment:guide:enzymes")],
        [("🦠 Полезные пищевые культуры", "ferment:guide:cultures")],
        [("🔬 Другие процессы", "ferment:guide:other")],
        [("📚 Каталог протоколов", "protocol:list")],
        [("🧬 Наука: кодзи, ферменты и культуры", "science:list")],
        [("📓 Журнал ферментации", "ferment:list")],
        [("🏠 Главное меню", "view:main")],
    ])


def fermentation_batch_keyboard(batch_id: int, finished: bool) -> InlineKeyboardMarkup:
    buttons = []
    if not finished:
        buttons += [[("📝 Записать замер", f"ferment:observe:{batch_id}")],
                    [("🏁 Завершить наблюдение", f"ferment:finish:{batch_id}")]]
    buttons += [[("🔎 Проверить контрольные условия", f"protocol:check:{batch_id}")],
                [("🗑 Удалить партию", f"ferment:remove:{batch_id}")],
                [("📓 Все партии", "ferment:list"), ("🔬 Раздел", "view:ferment")]]
    return keyboard(buttons)


def fermentation_batch_text(batch: dict) -> str:
    label = PROCESS_LABELS.get(batch["category"], "Неизвестный процесс")
    state = "завершено наблюдение" if batch["finished"] else "наблюдение продолжается"
    lines = [f"📓 {batch['name']}", label, f"Статус: {state}"]
    if batch.get("protocol_id"):
        lines.append("📚 Протокол " + batch["protocol_id"] + " v" + batch["protocol_revision"])
        lines.append("Опубликованный источник (не сертификат партии): " + batch["protocol_source"])
    elif batch.get("protocol_source"):
        lines.append("Источник по словам пользователя (не проверен): " + batch["protocol_source"])
    else:
        lines.append("⚠️ Проверенный источник технологии не указан.")
    lines.append("")
    for observation in batch["readings"]:
        lines.append(f"• {observation['observed_at'][:16]}: {observation_text(observation)}")
    if not batch["readings"]:
        lines.append("Измерений пока нет.")
    return "\n".join(lines) + "\n\n" + SAFETY_REMINDER


def memory_kind_keyboard() -> InlineKeyboardMarkup:
    return keyboard(
        [[(label[:50], "memory:kind:" + kind)]
         for kind, label in MEMORY_KINDS.items()] +
        [[("🧠 Просмотреть память", "view:memory"), ("🏠 Меню", "view:main")]]
    )


async def show_archive(message: Message, storage: Storage, user_id: int,
                       page: int = 0) -> None:
    if not 0 <= page <= 10000:
        return
    recipes = await storage.archived_recipes(user_id, limit=15, offset=page * 15)
    if not recipes:
        await send_text(message, "📖 Пока нет приготовленных или придуманных рецептов. "
                        "Новые рецепты будут сохраняться автоматически.", main_keyboard())
        return
    buttons = [[(item["recipe"].get("title", "Без названия")[:46],
                 f"archive:open:{item['id']}")] for item in recipes]
    navigation = []
    if page:
        navigation.append(("⬅️ Ранее", f"archive:page:{page - 1}"))
    if len(recipes) == 15:
        navigation.append(("➡️ Далее", f"archive:page:{page + 1}"))
    if navigation:
        buttons.append(navigation)
    buttons.append([("❤️ Избранное", "view:favorites"), ("🏠 Меню", "view:main")])
    await send_text(message, f"📖 Архив рецептов · страница {page + 1} (сохраняются автоматически):",
                    keyboard(buttons))


async def show_memory(message: Message, storage: Storage, user_id: int) -> None:
    items = await storage.personal_memories(user_id, include_pending=True)
    if not items:
        await send_text(message, "🧠 Здесь пока пусто. Я сохраняю долговременные заметки "
                        "только после Вашего явного подтверждения.", memory_kind_keyboard())
        return
    active = [x for x in items if x["status"] == "active"]
    pending = [x for x in items if x["status"] == "pending"]
    lines = ["🧠 Подтверждённая кулинарная память:"]
    lines.extend(f"• {MEMORY_KINDS.get(x['kind'], x['kind'])}: {x['value']}"
                 for x in active[:15])
    if pending:
        lines.append("\nОжидают подтверждения: " + str(len(pending)))
    buttons = []
    for item in pending[:5]:
        buttons.append([("✅ Запомнить: " + item["value"][:25],
                         f"memory:confirm:{item['id']}"),
                        ("❌ Отмена", f"memory:remove:{item['id']}")])
    buttons.extend([[("💬 Как ко мне обращаться", "view:communication")],
                    [("📝 Добавить заметку", "memory:choose")],
                    [("🧹 Удалить отдельную запись", "memory:forget")],
                    [("🏠 Главное меню", "view:main")]])
    await send_text(message, "\n".join(lines), keyboard(buttons))


def rating_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [("😍 Великолепно", "rate:great"), ("👍 Вкусно", "rate:good")],
        [("🧂 Пересолено", "rate:salty"), ("🥩 Суховато", "rate:dry")],
        [("🌶 Слишком остро", "rate:spicy"), ("😕 Не понравилось", "rate:disliked")],
        [("🏠 Главное меню", "view:main")],
    ])


def profile_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [("⚠️ Аллергены", "pref:allergens"), ("🚫 Исключить", "pref:excluded")],
        [("🥑 Люблю", "pref:likes"), ("🍳 Оборудование", "pref:equipment")],
        [("👥 Порции", "pref:portions"), ("🌎 Кухни", "pref:cuisines")],
        [("🌶 Острота", "pref:spice"), ("🥗 Текстуры", "pref:textures")],
        [("💰 Бюджет", "pref:budget"), ("⏱ Время", "pref:cook_time")],
        [("🎓 Уровень", "pref:skill"), ("🧠 Память", "view:memory")],
        [("💬 Стиль общения", "view:communication")],
        [("🏠 Главное меню", "view:main")],
    ])


def profile_text(prefs: dict[str, str]) -> str:
    lines = ["🥗 Твои настройки кухни:" if prefs.get("address_form") == "ты" else "🥗 Ваши настройки кухни:"]
    lines.extend(f"• {label}: {prefs.get(key) or 'не указано'}" for key, label in PREF_LABELS.items())
    lines.append("\n" + communication_summary(prefs))
    lines.append("\nДля очистки отдельного поля отправьте «-». Острота: без острого/лёгкая/средняя/острая; уровень: начинающий/уверенный/опытный.")
    return "\n".join(lines)


def cooking_text(session: dict[str, Any]) -> str:
    recipe = session["recipe"]
    index = session["step_index"]
    steps = recipe.get("steps", [])
    if index >= len(steps):
        return ("🎉 Мы дошли до подачи! Оцените аромат, вкус и готовность блюда. "
                "Самое приятное — теперь можно собирать всех за столом.")
    hint = suggested_timer(recipe, index)
    timer_note = (f"\n\n⏱ Рекомендуемый таймер: {hint['minutes']} мин — {hint['label']}."
                  if hint else
                  "\n\n⏱ При необходимости поставьте таймер вручную.")
    return (f"👨‍🍳 {recipe['title']}\nШаг {index + 1}/{len(steps)}:"
            f"\n\n{steps[index]}" + timer_note +
            "\nТаймер запускается по кнопке.\n\n"
            "Если нужна подсказка, просто напишите.")


def cooking_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [("⬅️ Предыдущий", "cook:previous"), ("✅ Следующий", "cook:next")],
        [("⏱ Поставить таймер", "cook:timer"), ("🔔 Мои таймеры", "view:timers")],
        [("💡 Почему так?", "cook:why"), ("🛠 Как исправить?", "cook:fix")],
        [("🥘 Показать рецепт", "recipe:show"), ("🏠 Меню", "view:main")],
    ])


def timer_choice_keyboard(session: dict) -> InlineKeyboardMarkup:
    rows = []
    hint = suggested_timer(session["recipe"], session["step_index"])
    if hint:
        rows.append([(f"⏱ Рекомендовано {hint['minutes']} мин", "timer:start:hint")])
    for i in range(0, len(TIMER_PRESETS), 3):
        rows.append([(f"{n} мин", f"timer:start:{n}") for n in TIMER_PRESETS[i:i+3]])
    rows.append([("✏️ Своё время", "timer:custom"), ("🔔 Активные", "view:timers")])
    rows.append([("👨‍🍳 Вернуться к шагу", "cook:show")])
    return keyboard(rows)


async def show_timers(message: Message, storage: Storage, user_id: int) -> None:
    timers = await storage.user_timers(user_id)
    if not timers:
        await send_text(
            message, "🔔 Активных таймеров нет. "
            "Откройте готовку и нажмите «Поставить таймер».",
            keyboard([[("👨‍🍳 К приготовлению", "cook:show"), ("🏠 Меню", "view:main")]])
        )
        return
    buttons = []
    lines = ["🔔 Ваши действующие таймеры:"]
    for t in timers:
        lines.append(
            f"• №{t['id']}: {t['recipe_title']}, шаг {t['step_index'] + 1}. "
            f"{t['minutes']} мин · {timer_progress(t)}\n  {t['label']}"
        )
        buttons.append([(f"🛑 Отменить №{t['id']}", f"timer:cancel:{t['id']}")])
    buttons.append([("👨‍🍳 К приготовлению", "cook:show"), ("🏠 Меню", "view:main")])
    await send_text(message, "\n".join(lines), keyboard(buttons))


def pantry_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [("➕ Добавить", "pantry:add"), ("➖ Убрать", "pantry:remove")],
        [("🥘 Приготовить из запасов", "pantry:recipe")],
        [("🧹 Очистить запасы", "pantry:confirm_clear"), ("🏠 Меню", "view:main")],
    ])


def pantry_text(rows: list[dict]) -> str:
    if not rows:
        return "📦 Ваши запасы пока пусты. Добавьте продукты, например «картофель 500 г» и «яйца 4 шт»."
    return ("📦 В Вашей кухне записано:\n" +
            "\n".join(f"• {r['display_name']} — {format_quantity(r['quantity'], r['unit'])}" for r in rows) +
            "\n\nЭто записанные Вами остатки, а не сведения о свежести продуктов.")


def week_keyboard(day_index: int) -> InlineKeyboardMarkup:
    previous = (day_index - 1) % 7
    following = (day_index + 1) % 7
    return keyboard([
        [("⬅️ " + DAY_NAMES[previous][:2], f"week:day:{previous}"),
         ("➡️ " + DAY_NAMES[following][:2], f"week:day:{following}")],
        [("🌅 Рецепт завтрака", f"week:meal:{day_index}:0")],
        [("🍲 Рецепт обеда", f"week:meal:{day_index}:1"),
         ("🍽 Рецепт ужина", f"week:meal:{day_index}:2")],
        [("📜 Вся неделя", "week:all"), ("🔄 Новое меню", "mode:plan")],
        [("🏠 Главное меню", "view:main")],
    ])


async def send_text(message: Message, text: str, markup: InlineKeyboardMarkup | None = None) -> None:
    # Escape model/user HTML, then render supported Markdown safely. Format each
    # chunk separately: no broken Telegram HTML tags and no visible **stars**.
    chunks = telegram_chunks(text)
    for i, chunk in enumerate(chunks):
        await message.answer(
            chunk, parse_mode="HTML",
            reply_markup=markup if i == len(chunks) - 1 else None,
        )


async def private_only(message: Message) -> bool:
    if message.chat.type == "private":
        return True
    await message.answer("Я работаю в личных сообщениях — там удобнее хранить Ваши рецепты и настройки.")
    return False


@router.message(CommandStart())
async def start(message: Message, storage: Storage) -> None:
    if not await private_only(message) or not message.from_user:
        return
    user = await storage.get_user(message.from_user.id)
    prefs = user["preferences"]
    if not prefs.get("conversation_style") and not prefs.get("onboarding_skipped"):
        await send_text(
            message,
            "👨‍🍳 Как приятно познакомиться! Добро пожаловать на кухню Сушефа. 🌷\n\n"
            "Мне хочется, чтобы Вам здесь было не только вкусно, но и по-настоящему уютно. "
            "Расскажете, как к Вам лучше обращаться и какой тон общения Вам ближе? "
            "Это займёт всего пару шагов, а можно сразу перейти к рецептам.",
            welcome_keyboard(),
        )
    else:
        await send_text(message, welcome_back(prefs), main_keyboard())


@router.message(Command("menu", "help"))
async def help_menu(message: Message) -> None:
    if await private_only(message):
        await send_text(
            message,
            "👨‍🍳 Сушеф поможет придумать рецепт, спасти блюдо, составить меню "
            "и провести Вас по шагам приготовления.\n\n"
            "Команды: /start, /menu, /help, /profile, /recipes, /memory, /remember, /export_my_data, /timers, /pantry, /week, /ferment, /reset, /privacy, /delete_me.",
            main_keyboard(),
        )


@router.message(Command("profile"))
async def show_profile(message: Message, storage: Storage) -> None:
    if not await private_only(message) or not message.from_user:
        return
    user = await storage.get_user(message.from_user.id)
    await send_text(message, profile_text(user["preferences"]), profile_keyboard())


@router.message(Command("pantry"))
async def show_pantry_command(message: Message, storage: Storage) -> None:
    if not await private_only(message) or not message.from_user:
        return
    rows = await storage.pantry(message.from_user.id)
    await send_text(message, pantry_text(rows), pantry_keyboard())


@router.message(Command("week"))
async def show_week_command(message: Message, storage: Storage) -> None:
    if not await private_only(message) or not message.from_user:
        return
    plan = await storage.get_weekly_plan(message.from_user.id)
    await send_text(message, format_day(plan, 0), week_keyboard(0)) if plan else await send_text(
        message, "📅 Сохранённого меню пока нет. Составим?", keyboard([[("Создать меню", "mode:plan")]]))


@router.message(Command("timers"))
async def list_timers_command(message: Message, storage: Storage) -> None:
    if await private_only(message) and message.from_user:
        await show_timers(message, storage, message.from_user.id)


@router.message(Command("recipes"))
async def recipe_archive_command(message: Message, storage: Storage) -> None:
    if await private_only(message) and message.from_user:
        await show_archive(message, storage, message.from_user.id)


@router.message(Command("memory"))
async def personal_memory_command(message: Message, storage: Storage) -> None:
    if await private_only(message) and message.from_user:
        await show_memory(message, storage, message.from_user.id)


@router.message(Command("remember"))
async def remember_command(message: Message) -> None:
    if await private_only(message):
        await send_text(message, "🧠 Что хотите сохранить на будущее? "
                        "Выберите тип записи. Перед сохранением я попрошу подтверждение.",
                        memory_kind_keyboard())


@router.message(Command("export_my_data"))
async def export_my_data_command(message: Message, storage: Storage) -> None:
    if not await private_only(message) or not message.from_user:
        return
    data = await storage.export_user_data(message.from_user.id)
    payload = json.dumps(data, ensure_ascii=False, indent=2, default=str).encode("utf-8")
    await message.answer_document(
        BufferedInputFile(payload, filename="sushef-my-data.json"),
        caption="🔐 Полный экспорт Ваших записей в JSON. "
                "Файл содержит личные сведения — храните его в защищённом месте.",
    )


@router.message(Command("ferment"))
async def fermentation_command(message: Message) -> None:
    if await private_only(message):
        await send_text(
            message,
            "🔬 Лаборатория вкуса: ферментация, полезные пищевые культуры и ферменты.\n"
            "Тёплый процесс — не значит безопасный для любого продукта. "
            "Температура, культура и срок зависят от конкретного протокола.\n\n"
            "Выберите направление:",
            fermentation_keyboard(),
        )


@router.message(Command("cancel"))
async def cancel_input(message: Message, storage: Storage) -> None:
    if not await private_only(message) or not message.from_user:
        return
    uid = message.from_user.id
    cooking = await storage.current_cooking(uid)
    await storage.set_mode(uid, "cook" if cooking else "ask")
    await send_text(
        message,
        "↩️ Отменён только ввод. История, рецепт и работающие таймеры сохранены.",
        cooking_keyboard() if cooking else main_keyboard()
    )


@router.message(Command("reset"))
async def reset_dialog(message: Message, storage: Storage) -> None:
    if not await private_only(message) or not message.from_user:
        return
    await storage.clear_chat(message.from_user.id)
    await send_text(
        message,
        "Диалог и активная готовка очищены, действующие таймеры отменены. "
        "Ваш профиль и любимые рецепты сохранены. 🧑‍🍳", main_keyboard()
    )


@router.message(Command("privacy"))
async def privacy(message: Message) -> None:
    if await private_only(message):
        await send_text(
            message,
            "🔒 Для работы сохраняются Ваш Telegram ID, выбранные настройки, "
            "до 40 последних реплик диалога, автоматический архив рецептов, избранное, "
            "подтверждённые и ожидающие подтверждения заметки, оценки блюд, продукты, "
            "недельное меню, таймеры и время их срабатывания, партии ферментации, их замеры и шаги приготовления. "
            "Запросы, история диалога и указанные предпочтения передаются провайдеру ClaudeHub "
            "для генерации ответа. Никаких сторонних рекламных рассылок бот не делает.\n\n"
            "/reset — очистить только диалог; рецепты, профиль и память останутся.\n"
            "/memory — просмотр и удаление подтверждённых заметок.\n"
            "/export_my_data — скачать все личные записи.\n"
            "/delete_me — удалить данные из рабочей базы (резервные копии имеют отдельный срок хранения).\n"
            "Не отправляйте в чат пароли и другую чувствительную информацию.",
        )


@router.message(Command("delete_me"))
async def delete_me(message: Message) -> None:
    if await private_only(message):
        await send_text(
            message, "Удалить ВСЕ сохранённые рецепты, историю и настройки без восстановления?",
            keyboard([[("🗑 Да, удалить", "delete:confirm"), ("Отмена", "view:main")]]),
        )


@router.message(F.photo)
async def inspect_photo(message: Message, storage: Storage, chef: Chef, settings: Settings) -> None:
    if not await private_only(message) or not message.from_user:
        return
    if not settings.vision_enabled:
        await send_text(message, "📷 Фотоанализ подготовлен, но пока не включён: мы ещё "
                        "не подтвердили поддержку изображений в выбранной модели ClaudeHub. "
                        "Опишите продукты текстом — я сразу помогу!", main_keyboard())
        return
    size = message.photo[-1]
    if size.file_size and size.file_size > settings.max_photo_bytes:
        await send_text(message, "Фотография слишком большая. Пришлите снимок меньшего размера.")
        return
    if not await storage.use_quota(message.from_user.id, settings.daily_ai_limit):
        await send_text(message, "На сегодня лимит запросов к ИИ исчерпан.")
        return
    try:
        await message.bot.send_chat_action(message.chat.id, "typing")
        stream = await message.bot.download(size)
        if stream is None or not hasattr(stream, "getvalue"):
            raise RuntimeError("Telegram не предоставил изображение")
        data = stream.getvalue()
        if not data or len(data) > settings.max_photo_bytes:
            await send_text(message, "Снимок превышает допустимый размер или недоступен.")
            return
        user = await storage.get_user(message.from_user.id)
        result = await chef.inspect_photo(data, message.caption or "", user["preferences"])
        await send_text(message, "📷 Посмотрим, что у нас на фотографии! "
                        "Проверьте распознанные продукты: я пока ничего не добавлял в запасы.\n\n"
                        + result,
                        keyboard([[("➕ Записать продукты вручную", "pantry:add")],
                                  [("🥘 Подобрать рецепт", "mode:recipe"), ("🏠 Меню", "view:main")]]))
    except Exception as exc:
        logger.warning("Optional vision request failed: %s", type(exc).__name__)
        await send_text(message, "📷 Пока не удалось разобрать фото. Возможно, модель "
                        "ClaudeHub не поддерживает изображения. Опишите продукты текстом.", main_keyboard())


@router.message(F.voice | F.video | F.audio | F.document)
async def unsupported_media(message: Message) -> None:
    if await private_only(message):
        await send_text(
            message,
            "Я уже мечтаю разглядывать Ваши продукты и слушать рассказы о шедеврах! "
            "Пока голос ещё не включён. Опишите продукты или задачу словами. 😊",
            main_keyboard(),
        )


@router.message(F.text)
async def text_message(message: Message, storage: Storage, chef: Chef, settings: Settings) -> None:
    if not await private_only(message) or not message.from_user:
        return
    user_id = message.from_user.id
    text = (message.text or "").strip()
    if not text:
        return
    if len(text) > settings.max_input_chars:
        await send_text(message, f"Сообщение слишком длинное. Пожалуйста, сократите до {settings.max_input_chars} символов.")
        return

    user = await storage.get_user(user_id)
    mode = user["mode"]
    preferences = dict(user["preferences"])
    feedback = await storage.recent_feedback(user_id)
    if feedback:
        preferences["recent_cooking_feedback"] = feedback
    patterns = await storage.feedback_patterns(user_id)
    if patterns["repeated_issues"]:
        preferences["feedback_patterns_not_confirmed_preferences"] = patterns
    memories = await storage.personal_memories(user_id, limit=10)
    if memories:
        preferences["confirmed_kitchen_memory"] = short_memory_context(memories)

    if mode == "onboard:name":
        try:
            await storage.set_preference(user_id, "display_name", text)
        except ValueError as exc:
            await send_text(message, "Мне хочется обращаться к Вам правильно. " +
                            str(exc) + "\nПопробуйте другое имя или нажмите «Без имени».",
                            keyboard([[("Без имени", "hello:name:skip")]]))
            return
        await storage.set_mode(user_id, "ask")
        await send_text(
            message, "Как приятно! А теперь маленький вопрос: Вам уютнее на «вы» или на «ты»?",
            address_keyboard(),
        )
        return

    if mode == "onboard:custom":
        try:
            await storage.set_preference(user_id, "style_notes", text)
            await storage.set_preference(user_id, "conversation_style", "custom")
        except ValueError as exc:
            await send_text(message, "Пожелание пока не удалось сохранить: " +
                            str(exc) + "\nНапишите чуть короче или /cancel.")
            return
        await storage.set_mode(user_id, "ask")
        updated = (await storage.get_user(user_id))["preferences"]
        await send_text(message,
                        "С удовольствием подстроюсь под Вас! 💛\n\n" +
                        communication_summary(updated),
                        communication_keyboard())
        return

    if mode == "timer:custom":
        if not text.isdecimal() or not 1 <= int(text) <= MAX_MINUTES:
            await send_text(
                message,
                f"Укажите целое число минут от 1 до {MAX_MINUTES} или /cancel."
            )
            return
        cooking = await storage.current_cooking(user_id)
        if cooking is None:
            await storage.set_mode(user_id, "ask")
            await send_text(message, "Приготовление уже завершено.", main_keyboard())
            return
        try:
            timer = await storage.start_timer(
                user_id, message.chat.id, int(text),
                f"Шаг {cooking['step_index'] + 1}: "
                + cooking["recipe"]["steps"][cooking["step_index"]][:95],
            )
        except ValueError as exc:
            await send_text(message, "⏱ Не удалось запустить таймер: " + str(exc),
                            cooking_keyboard())
            return
        await storage.set_mode(user_id, "cook")
        await send_text(message, timer_start_text(timer["minutes"], timer["label"]),
                        cooking_keyboard())
        return

    if mode.startswith("pref:"):
        key = mode.split(":", 1)[1]
        if key not in PREF_LABELS:
            await storage.set_mode(user_id, "ask")
            await send_text(message, "Параметр не найден. Вернёмся к меню.", main_keyboard())
            return
        try:
            await storage.set_preference(user_id, key, text)
        except ValueError as exc:
            await send_text(message, "Не удалось обновить профиль: " + str(exc) +
                            "\nОтправьте правильное значение или /cancel.")
            return
        await storage.set_mode(user_id, "ask")
        updated = await storage.get_user(user_id)
        await send_text(message, "Прекрасно! Настройки обновлены.\n\n" + profile_text(updated["preferences"]), profile_keyboard())
        return

    if mode.startswith("memory:write:"):
        kind = mode.split(":", 2)[2]
        try:
            pending_id = await storage.propose_memory(user_id, kind, text)
        except ValueError as exc:
            await send_text(message, "Не удалось записать заметку: " + str(exc) +
                            "\nУточните её или воспользуйтесь /cancel.")
            return
        await storage.set_mode(user_id, "ask")
        await send_text(
            message,
            "🧠 Вы предлагаете запомнить:\n«" + text + "»\n\n"
            "Это постоянная запись или пожелание только на сегодня?",
            keyboard([[("✅ Запомнить", f"memory:confirm:{pending_id}"),
                       ("❌ Не сохранять", f"memory:remove:{pending_id}")]]),
        )
        return

    if mode.startswith("pnew:"):
        pid = mode.split(":", 1)[1]
        p = get_protocol(pid)
        if not p:
            await storage.set_mode(user_id, "ask")
            await send_text(message, "Рецептура не найдена.", fermentation_keyboard())
            return
        try:
            batch_id = await storage.create_fermentation_batch(
                user_id, p.category, text, p.source_url, p.id, p.revision
            )
        except ValueError as exc:
            await send_text(message, "Не удалось создать журнал: " + str(exc))
            return
        await storage.set_mode(user_id, "ask")
        batch = await storage.fermentation_batch(user_id, batch_id)
        await send_text(
            message,
            "📓 Журнал привязан к исходному протоколу, но Сушеф не удостоверяет "
            "безопасность Вашей партии.\n\n" + fermentation_batch_text(batch),
            fermentation_batch_keyboard(batch_id, False),
        )
        return

    if mode.startswith("fnew:"):
        category = mode.split(":", 1)[1]
        try:
            name, delimiter, source = text.partition("|")
            batch_id = await storage.create_fermentation_batch(
                user_id, category, name.strip(), source.strip() if delimiter else "")
        except ValueError as exc:
            await send_text(message, "Не получилось создать партию: " + str(exc))
            return
        await storage.set_mode(user_id, "ask")
        batch = await storage.fermentation_batch(user_id, batch_id)
        await send_text(message, "📓 Партия записана для наблюдений, но это НЕ проверка "
                        "безопасности технологии.\n\n" +
                        fermentation_batch_text(batch),
                        fermentation_batch_keyboard(batch_id, False))
        return

    if mode.startswith("flog:"):
        try:
            batch_id = int(mode.split(":", 1)[1])
            obs = parse_observation(text)
            saved = await storage.log_fermentation(
                user_id, batch_id,
                str(obs.temperature_c) if obs.temperature_c is not None else None,
                str(obs.ph) if obs.ph is not None else None,
                obs.note,
            )
        except ValueError as exc:
            await send_text(message, "Замер не записан: " + str(exc) +
                            "\nПример: t=22; ph=4.1; note=появились пузырьки")
            return
        await storage.set_mode(user_id, "ask")
        if not saved:
            await send_text(message, "Партия недоступна или уже завершена.", fermentation_keyboard())
            return
        batch = await storage.fermentation_batch(user_id, batch_id)
        await send_text(message, "📝 Наблюдение записано.\n\n" +
                        fermentation_batch_text(batch),
                        fermentation_batch_keyboard(batch_id, batch["finished"]))
        return

    if mode.startswith("pantry:"):
        action = mode.split(":", 1)[1]
        if action not in {"add", "remove"}:
            await storage.set_mode(user_id, "ask")
            await send_text(message, "Режим продуктов не распознан. Вернёмся к меню.", main_keyboard())
            return
        lines = [item.strip() for item in text.replace(";", "\n").splitlines() if item.strip()]
        if len(lines) > 15:
            await send_text(message, "За одно сообщение можно изменить не больше 15 продуктов.")
            return
        applied, errors = [], []
        for line in lines:
            try:
                name, key, quantity = parse_product_line(line)
                changed = await storage.change_pantry(
                    user_id, name, key, quantity.value, quantity.unit, remove=(action == "remove"))
                if changed:
                    applied.append(f"{name}: {format_quantity(quantity.value, quantity.unit)}")
                else:
                    errors.append(f"{name}: такого запаса нет")
            except ValueError as exc:
                errors.append(f"{line[:60]}: {str(exc)}")
        await storage.set_mode(user_id, "ask")
        report = "✅ Изменено: " + (", ".join(applied) if applied else "нет")
        if errors:
            report += "\n\nНужно исправить:\n" + "\n".join("• " + e for e in errors)
        await send_text(message, report + "\n\n" + pantry_text(await storage.pantry(user_id)), pantry_keyboard())
        return

    if not await storage.use_quota(user_id, settings.daily_ai_limit):
        await send_text(message, "На сегодня лимит обращений к ИИ исчерпан. Завтра (по UTC) снова сможем творить вкусное! 🍲")
        return

    try:
        await message.bot.send_chat_action(message.chat.id, "typing")
        if mode in {"recipe", "pantry_recipe"} or mode.startswith(("weekly:", "catalog:")):
            reference = None
            if mode.startswith("catalog:"):
                reference = await storage.cuisine_recipe(mode.split(":", 1)[1])
                if not reference:
                    await storage.set_mode(user_id, "ask")
                    await send_text(message, "Эта карточка больше недоступна. Выберем другую?", cuisines_keyboard())
                    return
                dish_tech = await storage.dish_process_card(reference["id"])
                query = (
                    "Создай удобную домашнюю адаптацию следующего блюда. "
                    "Не называй адаптированные количества каноническим оригиналом.\n"
                    + source_reference(reference) + "\n"
                    + (dish_process_context(dish_tech) + "\n" if dish_tech else "")
                    + "Доступные продукты и пожелания пользователя: " + text
                )
            elif mode == "pantry_recipe":
                rows = await storage.pantry(user_id)
                products = ", ".join(
                    f"{r['display_name']}: {r['quantity']} {r['unit']}" for r in rows)
                query = ("Доступные продукты (данные пользователя): " + products +
                         "\nЗапрос: " + text +
                         "\nПри нехватке продукта пометь необходимость докупить в списке ингредиентов.")
            elif mode.startswith("weekly:"):
                plan = await storage.get_weekly_plan(user_id)
                if not plan:
                    await storage.set_mode(user_id, "ask")
                    await send_text(message, "Это меню уже неактуально. Создайте новое.", main_keyboard())
                    return
                _, day_raw, meal = mode.split(":")
                selected = plan["days"][int(day_raw)][meal]
                query = f"Полный подробный рецепт для блюда «{selected}». Пожелания пользователя: {text}"
            else:
                references = await storage.cuisine_matches(text, limit=2)
                query = text
                if references:
                    query += ("\n\nДля кулинарной ориентации доступны СПРАВОЧНЫЕ карточки "
                              "(они не обязаны подходить запросу и не заменяют ограничения):\n" +
                              "\n\n".join(source_reference(r) for r in references))
            matching_techniques = await storage.technique_matches(
                text + ((" " + reference["title"] + " " + reference["method"])
                        if reference else ""), limit=2
            )
            if matching_techniques:
                query += ("\n\nТехнологические справки (объясняют принципы, "
                          "но не подтверждают весь новый рецепт):\n" +
                          technique_context(matching_techniques))
            recipe = await chef.recipe(query, preferences)
            if matching_techniques:
                top = matching_techniques[0]
                recipe["technique_reference"] = {
                    "id": top["id"], "title": top["title"],
                    "revision": top["revision"],
                    "source_url": top["source_url"],
                }
            if reference:
                recipe["catalog_reference"] = {
                    "id": reference["id"], "title": reference["title"],
                    "source_url": reference["source_url"],
                    "publisher": reference["publisher"], "adapted": True,
                }
            await storage.set_recipe(user_id, recipe)
            await storage.add_exchange(
                user_id, text, "Создан рецепт: " + recipe["title"] +
                ". Рецепт сохранён автоматически в личном архиве."
            )
            await storage.set_mode(user_id, "ask")
            await send_text(message, "🥘 Рецепт добавлен в Вашу личную коллекцию.\n\n" +
                            format_recipe(recipe), recipe_keyboard())
        elif mode == "plan":
            plan = await chef.weekly_plan(text, preferences, await storage.pantry(user_id))
            await storage.save_weekly_plan(user_id, plan)
            await storage.add_exchange(
                user_id, text, "Составлено недельное меню на 7 дней. "
                "Оно сохранено в личном разделе «Моё меню»."
            )
            await storage.set_mode(user_id, "ask")
            await send_text(message, "📅 Меню на неделю готово! Начнём с понедельника.\n\n" +
                            format_day(plan, 0), week_keyboard(0))
        else:
            history = await storage.get_history(user_id)
            context = ""
            if mode.startswith("science:"):
                cid = mode.split(":", 1)[1]
                card = get_knowledge(cid)
                if card:
                    context = knowledge_context(cid)
                    mode = "ferment"
                else:
                    await storage.set_mode(user_id, "ask")
                    mode = "ask"
            if mode.startswith("protocol:"):
                pid = mode.split(":", 1)[1]
                p = get_protocol(pid)
                if p:
                    context = protocol_context(pid)
                    mode = "ferment"
                else:
                    await storage.set_mode(user_id, "ask")
                    mode = "ask"
            if mode.startswith("ferment:"):
                category = mode.split(":", 1)[1]
                if category in PROCESS_LABELS:
                    context = fermentation_system_context(category)
                    mode = "ferment"
                else:
                    await storage.set_mode(user_id, "ask")
                    mode = "ask"
            if mode == "cook":
                cooking = await storage.current_cooking(user_id)
                if cooking:
                    context = cooking_text(cooking)
                else:
                    await storage.set_mode(user_id, "ask")
                    mode = "ask"
            ai_text = text
            if mode.startswith("technique:"):
                item = await storage.technique_card(mode.split(":", 1)[1])
                await storage.set_mode(user_id, "ask")
                mode = "ask"
                if item:
                    ai_text += "\n\nСправка для ответа:\n" + technique_context([item])
            elif mode in {"ask", "rescue"}:
                related = await storage.technique_matches(text, limit=2)
                if related:
                    ai_text += "\n\nТехнологические справки:\n" + technique_context(related)
            answer = await chef.answer(mode, ai_text, preferences, history, context)
            await storage.add_exchange(user_id, text, answer)
            await send_text(message, answer,
                            cooking_keyboard() if mode == "cook" else
                            fermentation_keyboard() if mode == "ferment" else main_keyboard())
    except (RecipeFormatError, WeeklyPlanError):
        logger.warning("Model returned malformed structured culinary response")
        await send_text(message, "Не удалось оформить рецепт или меню без ошибок. Попробуйте переформулировать запрос.", main_keyboard())
    except Exception as exc:
        logger.warning("AI request failed: %s", type(exc).__name__)
        await send_text(
            message, "Плита фантазии временно отдыхает: сейчас нет ответа от ИИ. Попробуйте ещё раз немного позже. "
            "Ваши настройки сохранены.",
            main_keyboard(),
        )


@router.callback_query()
async def button_clicked(callback: CallbackQuery, storage: Storage) -> None:
    if not callback.from_user or not isinstance(callback.message, Message):
        await callback.answer()
        return
    message = callback.message
    if message.chat.type != "private":
        await callback.answer("Откройте личный чат с ботом", show_alert=True)
        return
    await callback.answer()
    user_id = callback.from_user.id
    data = callback.data or ""

    if data == "view:main":
        prefs = (await storage.get_user(user_id))["preferences"]
        await send_text(message, welcome_back(prefs), main_keyboard())
        return

    if data in {"hello:start", "hello:edit:name"}:
        await storage.set_mode(user_id, "onboard:name")
        await send_text(
            message,
            "🌷 Как Вам приятно, чтобы я к Вам обращался? "
            "Напишите имя или любое любимое обращение. "
            "Необязательно настоящее имя — главное, чтобы Вам нравилось.",
            keyboard([[("⏭ Без имени", "hello:name:skip"),
                       ("🍳 Позже", "hello:skip")]]),
        )
        return

    if data in {"hello:name:skip", "hello:edit:address"}:
        if data == "hello:name:skip":
            await storage.set_preference(user_id, "display_name", "-")
        await storage.set_mode(user_id, "ask")
        await send_text(message, "С удовольствием! Как лучше общаться — на «вы» или на «ты»?",
                        address_keyboard())
        return

    if data.startswith("hello:address:"):
        form = data.rsplit(":", 1)[1]
        if form not in {"вы", "ты"}:
            return
        await storage.set_preference(user_id, "address_form", form)
        await storage.set_mode(user_id, "ask")
        prefs = (await storage.get_user(user_id))["preferences"]
        await send_text(message, style_comparison(prefs), style_keyboard())
        return

    if data == "hello:styles":
        await storage.set_mode(user_id, "ask")
        prefs = (await storage.get_user(user_id))["preferences"]
        await send_text(message, style_comparison(prefs), style_keyboard())
        return

    if data.startswith("hello:style:"):
        style = data.rsplit(":", 1)[1]
        if style not in STYLE_LABELS:
            return
        prefs = (await storage.get_user(user_id))["preferences"]
        await send_text(
            message,
            STYLE_LABELS[style] + "\n\n«" + example(style, prefs) + "»\n\n" +
            ("Хочешь общаться именно так?" if prefs.get("address_form") == "ты" else
             "Хотите, чтобы именно так я с Вами разговаривал?"),
            keyboard([[("💛 Да, это мой стиль", "hello:save:" + style)],
                      [("🎭 Сравнить остальные", "hello:styles")],
                      [("🎨 Смешать стили по-своему", "hello:custom")]]),
        )
        return

    if data.startswith("hello:save:"):
        style = data.rsplit(":", 1)[1]
        if style not in STYLE_LABELS:
            return
        await storage.set_preference(user_id, "conversation_style", style)
        await storage.set_mode(user_id, "ask")
        prefs = (await storage.get_user(user_id))["preferences"]
        await send_text(
            message,
            "Какая приятная тонкость — мы нашли наш общий язык! 💛\n\n"
            + welcome_back(prefs),
            main_keyboard(),
        )
        return

    if data == "hello:custom":
        await storage.set_mode(user_id, "onboard:custom")
        await send_text(
            message,
            "🎨 Можно соединить стили. Например: «Галантно, с лёгким юмором; коротко, но душевно». "
            "Расскажите о желаемом тоне одной фразой (до 200 символов).",
            keyboard([[("🎭 Посмотреть примеры", "hello:styles"),
                       ("🍳 Позже", "hello:skip")]]),
        )
        return

    if data == "hello:skip":
        await storage.set_preference(user_id, "onboarding_skipped", "yes")
        await storage.set_mode(user_id, "ask")
        await send_text(
            message,
            "С радостью! Знакомиться ближе можно и за приготовлением. "
            "А пока — что вкусного хочется сегодня? 🌷",
            main_keyboard(),
        )
        return

    if data == "view:communication":
        prefs = (await storage.get_user(user_id))["preferences"]
        await send_text(message, communication_summary(prefs), communication_keyboard())
        return

    if data == "view:techniques":
        await send_text(
            message,
            "🧪 Здесь не просто рецепты — секреты, которые делают вкус выразительным. "
            "Выберите процесс, и я покажу, почему он работает, как его контролировать "
            "и как спасти результат, если что-то пошло не так.",
            technique_categories_keyboard(),
        )
        return

    if data.startswith("technique:category:"):
        category = data.rsplit(":", 1)[1]
        if category not in CATEGORIES:
            return
        items = await storage.technique_cards(category)
        rows = [[(entry["title"][:52], "technique:open:" + entry["id"])] for entry in items]
        rows.append([("🧪 Все технологии", "view:techniques")])
        await send_text(message, CATEGORIES[category] + "\nВыберите технологическую карту:", keyboard(rows))
        return

    if data.startswith("technique:open:"):
        tid = data.rsplit(":", 1)[1]
        item = await storage.technique_card(tid)
        if not item:
            await send_text(message, "Технологическая карта не найдена.", technique_categories_keyboard())
            return
        await send_text(
            message, technique_card_text(item),
            keyboard([[("💬 Спросить о технике", "technique:ask:" + tid)],
                      [("↩️ К этой категории", "technique:category:" + item["category"])],
                      [("🏠 Меню", "view:main")]]),
        )
        return

    if data.startswith("technique:ask:"):
        tid = data.rsplit(":", 1)[1]
        item = await storage.technique_card(tid)
        if item is None:
            return
        await storage.set_mode(user_id, "technique:" + tid)
        await send_text(message, "С удовольствием разберём тонкости «" + item["title"] +
                        "». Что именно хочется понять или попробовать?")
        return

    if data in {"cook:why", "cook:fix"}:
        session = await storage.current_cooking(user_id)
        if not session:
            await send_text(message, "Сначала выберите блюдо и запустите готовку.", main_keyboard())
            return
        await send_text(message, cooking_insight_text(
            session, "why" if data == "cook:why" else "fix"), cooking_keyboard())
        return

    if data == "view:cuisines":
        await send_text(
            message,
            "🌍 Приглашаю Вас в маленькое гастрономическое путешествие! "
            "Здесь собраны блюда из опубликованных кулинарных источников. "
            "У каждой карточки есть ссылка и пометка о наличии точных пропорций. "
            "Какую кухню исследуем?",
            cuisines_keyboard(),
        )
        return

    if data.startswith("cuisine:group:"):
        group = data.rsplit(":", 1)[1]
        if group != "all" and group not in CUISINE_GROUPS:
            return
        label = "🌐 Все кухни" if group == "all" else CUISINE_GROUPS[group][0]
        await send_text(message, label + "\n\nВыберем направление, которое сегодня вдохновляет?",
                        cuisines_group_keyboard(group))
        return

    if data.startswith("cuisine:list:"):
        cuisine = data.rsplit(":", 1)[1]
        if cuisine not in CUISINES:
            return
        entries = await storage.cuisine_recipes(cuisine)
        rows = [[(r["title"][:55], "cuisine:open:" + r["id"])] for r in entries]
        rows.append([("🌍 Другие кухни", "view:cuisines")])
        await send_text(
            message, CUISINES[cuisine][0] + "\n\nВыберите блюдо и откройте его источник:",
            keyboard(rows),
        )
        return

    if data.startswith("cuisine:open:"):
        slug = data.rsplit(":", 1)[1]
        row = await storage.cuisine_recipe(slug)
        if not row:
            await send_text(message, "Карточка не найдена.", cuisines_keyboard())
            return
        techcard = await storage.dish_process_card(slug)
        buttons = [[("👨‍🍳 Приготовить по мотивам", "cuisine:make:" + slug)]]
        if techcard:
            buttons.append([("📋 Профессиональная техкарта", "cuisine:tech:" + slug)])
        buttons.extend([[("📚 Другие блюда этой кухни", "cuisine:list:" + row["cuisine"])],
                        [("🌍 Все кухни", "view:cuisines")]])
        await send_text(message, cuisine_recipe_text(row), keyboard(buttons))
        return

    if data.startswith("cuisine:tech:"):
        rid = data.rsplit(":", 1)[1]
        card = await storage.dish_process_card(rid)
        if not card:
            await send_text(message, "Для этого блюда ещё нет полной технологической карты.", cuisines_keyboard())
            return
        await send_text(message, production_overview(card),
                        production_keyboard(rid))
        return

    if data.startswith("cuisine:tcstage:"):
        parts = data.split(":")
        if len(parts) != 4 or not parts[3].isdigit():
            return
        rid, step_index = parts[2], int(parts[3])
        card = await storage.dish_process_card(rid)
        if not card or step_index >= len(card["stages"]):
            return
        next_step = (step_index + 1) % len(card["stages"])
        await send_text(
            message, production_stage_text(card, step_index),
            keyboard([[("➡️ Следующий этап", f"cuisine:tcstage:{rid}:{next_step}")],
                      [("📋 Паспорт", "cuisine:tech:" + rid),
                       ("👀 Качество", "cuisine:tcquality:" + rid)]]),
        )
        return

    if data.startswith("cuisine:tcquality:"):
        rid = data.rsplit(":", 1)[1]
        card = await storage.dish_process_card(rid)
        if not card:
            return
        await send_text(message, production_quality_text(card),
                        production_keyboard(rid))
        return

    if data.startswith("cuisine:tcscale:"):
        parts = data.split(":")
        if len(parts) != 4 or not parts[3].isdigit():
            return
        rid, portions = parts[2], int(parts[3])
        card = await storage.dish_process_card(rid)
        if not card or not card.get("production_spec"):
            return
        try:
            formatted = production_scale_text(card, portions)
        except ValueError:
            return
        await send_text(message, formatted, production_keyboard(rid))
        return

    if data.startswith("cuisine:make:"):
        slug = data.rsplit(":", 1)[1]
        row = await storage.cuisine_recipe(slug)
        if not row or len("catalog:" + slug) > 32:
            await send_text(message, "Карточка недоступна.", cuisines_keyboard())
            return
        await storage.set_mode(user_id, "catalog:" + slug)
        await send_text(
            message,
            f"👨‍🍳 {row['title']} — прекрасный выбор!\n"
            "Какие продукты есть под рукой, на сколько человек готовим и нужно ли "
            "что-нибудь исключить? На основе источника подготовлю удобную домашнюю версию.",
        )
        return

    if data == "view:archive":
        await show_archive(message, storage, user_id)
        return

    if data.startswith("archive:page:"):
        try:
            page = int(data.rsplit(":", 1)[1])
        except ValueError:
            return
        await show_archive(message, storage, user_id, page)
        return

    if data.startswith("archive:open:"):
        try:
            recipe_id = int(data.rsplit(":", 1)[1])
        except ValueError:
            return
        user = await storage.get_user(user_id)
        restricted = bool(user["preferences"].get("allergens") or
                          user["preferences"].get("excluded"))
        recipe = await storage.select_archived_recipe(user_id, recipe_id,
                                                     activate=not restricted)
        if not recipe:
            await send_text(message, "Рецепт недоступен.", main_keyboard())
        elif restricted:
            await send_text(
                message,
                "⚠️ Рецепт из архива не проверен на Ваши текущие пищевые ограничения. "
                "Для готовки сформируйте новую адаптированную версию.\n\n"
                + format_recipe(recipe), main_keyboard()
            )
        else:
            await send_text(message, "📖 Восстановленный рецепт:\n\n" +
                            format_recipe(recipe), recipe_keyboard())
        return

    if data == "view:memory":
        await show_memory(message, storage, user_id)
        return

    if data == "memory:choose":
        await send_text(message, "🧠 Что хотите добавить в долговременную память?",
                        memory_kind_keyboard())
        return

    if data.startswith("memory:kind:"):
        kind = data.split(":", 2)[2]
        if kind not in MEMORY_KINDS:
            return
        await storage.set_mode(user_id, "memory:write:" + kind)
        await send_text(message, "📝 Напишите одну постоянную кулинарную "
                        "привычку или наблюдение. Например: "
                        "«Я люблю соусы с лёгкой кислинкой». "
                        "Запись будет предложена для подтверждения, а не сохранена тайно.")
        return

    if data.startswith("memory:confirm:"):
        try:
            fact_id = int(data.rsplit(":", 1)[1])
            result = await storage.confirm_memory(user_id, fact_id)
        except ValueError as exc:
            await send_text(message, "Не удалось подтвердить запись: " + str(exc),
                            memory_kind_keyboard())
            return
        await send_text(
            message,
            "🧠 Отлично, эту особенность Вашего вкуса теперь буду учитывать."
            if result else "Заметка не найдена или уже обработана.",
            memory_kind_keyboard(),
        )
        return

    if data == "memory:forget":
        facts = await storage.personal_memories(user_id, limit=50)
        if not facts:
            await send_text(message, "Активных заметок нет.", memory_kind_keyboard())
            return
        rows = [[("🗑 " + f["value"][:40], f"memory:askremove:{f['id']}")]
                for f in facts]
        rows.append([("↩️ К моей памяти", "view:memory")])
        await send_text(message, "Выберите конкретную запись для удаления:", keyboard(rows))
        return

    if data.startswith("memory:askremove:"):
        try:
            fact_id = int(data.rsplit(":", 1)[1])
        except ValueError:
            return
        found = next((x for x in await storage.personal_memories(user_id, limit=50)
                      if x["id"] == fact_id), None)
        if not found:
            await send_text(message, "Заметка уже удалена.", memory_kind_keyboard())
            return
        await send_text(
            message,
            "Удалить из долговременной памяти:\n«" + found["value"] + "»?",
            keyboard([[("✅ Да, удалить", f"memory:remove:{fact_id}"),
                       ("↩️ Отмена", "view:memory")]]),
        )
        return

    if data.startswith("memory:remove:"):
        try:
            fact_id = int(data.rsplit(":", 1)[1])
        except ValueError:
            return
        deleted = await storage.remove_memory(user_id, fact_id)
        await send_text(message, "🗑 Заметка удалена."
                        if deleted else "Заметка не найдена.", memory_kind_keyboard())
        return

    if data == "view:timers":
        await show_timers(message, storage, user_id)
        return

    if data == "cook:show":
        cooking = await storage.current_cooking(user_id)
        if cooking:
            await storage.set_mode(user_id, "cook")
            await send_text(message, cooking_text(cooking), cooking_keyboard())
        else:
            await send_text(
                message, "👨‍🍳 Пошаговая готовка не запущена. Выберите рецепт.",
                main_keyboard()
            )
        return

    if data == "cook:timer":
        cooking = await storage.current_cooking(user_id)
        if not cooking:
            await send_text(message, "Сначала начните готовить пошагово.", main_keyboard())
            return
        await send_text(
            message,
            f"⏱ Шаг {cooking['step_index'] + 1}: выберите длительность таймера. "
            "Можно оставить несколько таймеров на разных шагах.",
            timer_choice_keyboard(cooking)
        )
        return

    if data == "timer:custom":
        cooking = await storage.current_cooking(user_id)
        if not cooking:
            await send_text(message, "Приготовление не запущено.", main_keyboard())
            return
        await storage.set_mode(user_id, "timer:custom")
        await send_text(message, "⏱ На сколько минут поставить таймер? "
                        f"Укажите число от 1 до {MAX_MINUTES}. Для отмены /cancel.")
        return

    if data.startswith("timer:start:"):
        cooking = await storage.current_cooking(user_id)
        if not cooking:
            await send_text(message, "Сначала запустите пошаговую готовку.", main_keyboard())
            return
        selected = data.split(":", 2)[2]
        hint = suggested_timer(cooking["recipe"], cooking["step_index"])
        if selected == "hint":
            if not hint:
                await send_text(message, "Для этого шага нет рекомендованного таймера.",
                                timer_choice_keyboard(cooking))
                return
            minutes, label = hint["minutes"], hint["label"]
        else:
            try:
                minutes = int(selected)
            except ValueError:
                return
            label = ("Шаг " + str(cooking["step_index"] + 1) + ": "
                     + cooking["recipe"]["steps"][cooking["step_index"]][:95])
        try:
            timer = await storage.start_timer(user_id, message.chat.id, minutes, label)
        except ValueError as exc:
            await send_text(message, "⏱ Не удалось запустить таймер: " + str(exc),
                            cooking_keyboard())
            return
        await storage.set_mode(user_id, "cook")
        await send_text(message, timer_start_text(timer["minutes"], timer["label"]),
                        cooking_keyboard())
        return

    if data.startswith("timer:cancel:"):
        try:
            timer_id = int(data.rsplit(":", 1)[1])
        except ValueError:
            return
        removed = await storage.cancel_timer(user_id, timer_id)
        await send_text(
            message,
            "🛑 Таймер отменён." if removed
            else "Этот таймер уже сработал, отменён или недоступен. "
                 "Если уведомление уже отправляется, оно может прийти.",
            keyboard([[("🔔 Мои таймеры", "view:timers"),
                       ("👨‍🍳 Готовка", "cook:show")]]),
        )
        return

    if data.startswith("mode:"):
        mode = data.split(":", 1)[1]
        if mode in MODE_PROMPTS:
            await storage.set_mode(user_id, mode)
            await send_text(message, MODE_PROMPTS[mode])
        return

    if data == "view:ferment":
        await send_text(
            message,
            "🔬 Лаборатория Сушефа. Мы разбираем не только вкус, но и биохимию. "
            "Выбирайте культурный процесс, пищевой фермент или журнал партии. "
            "При неопределённости лучше остановиться и проверить протокол.",
            fermentation_keyboard(),
        )
        return

    if data == "science:list":
        cards = list_knowledge()
        buttons = [[(card.title[:49], f"science:view:{card.id}")] for card in cards]
        buttons.append([("📚 К протоколам", "protocol:list"), ("🔬 Лаборатория", "view:ferment")])
        await send_text(
            message, "🧬 Справочные материалы с научными источниками и "
            "документацией конкретных ферментных препаратов.\n\n"
            "⚠️ Эти карточки НЕ являются автоматически разрешёнными домашними "
            "процедурами. В частности параметры исследования кодзи и дозы "
            "для винодельческого сока нельзя переносить на другую еду.",
            keyboard(buttons),
        )
        return

    if data.startswith("science:view:"):
        cid = data.split(":", 2)[2]
        card = get_knowledge(cid)
        if not card:
            await send_text(message, "Карточка не найдена.", fermentation_keyboard())
            return
        await send_text(
            message, knowledge_text(card),
            keyboard([[("❓ Спросить об источнике", f"science:ask:{card.id}")],
                      [("🧬 Ко всем материалам", "science:list"),
                       ("🔬 Лаборатория", "view:ferment")]]),
        )
        return

    if data.startswith("science:ask:"):
        cid = data.split(":", 2)[2]
        card = get_knowledge(cid)
        if not card:
            return
        await storage.set_mode(user_id, f"science:{card.id}")
        await send_text(
            message,
            f"🧬 Вы изучаете «{card.title}». "
            "Спросите о микроорганизмах, механизме ферментов, ограничениях "
            "или конкретной публикации. Я не стану придумывать домашнюю "
            "инструкцию вместо полноценного протокола.",
            keyboard([[("📖 Показать карточку", f"science:view:{card.id}")],
                      [("🧬 Научная библиотека", "science:list")]]),
        )
        return

    if data == "protocol:list":
        protocols = list_protocols()
        rows = [[(p.title[:50], f"protocol:view:{p.id}")] for p in protocols]
        rows.append([("🔬 Лаборатория", "view:ferment")])
        await send_text(
            message, "📚 Каталог протоколов с проверенным источником. "
            "Это не сертификат безопасности Вашей партии. "
            "Кодзи, натто, закваски и внешние ферменты пока не имеют "
            "готового универсального рецепта.", keyboard(rows)
        )
        return

    if data.startswith("protocol:view:"):
        pid = data.split(":", 2)[2]
        p = get_protocol(pid)
        if not p:
            await send_text(message, "Рецептура не найдена.", fermentation_keyboard())
            return
        await send_text(
            message, protocol_summary(p),
            keyboard([
                [("❓ Спросить о технологии", f"protocol:ask:{p.id}")],
                [("📓 Журнал по этой версии", f"protocol:prepare:{p.id}")],
                [("📚 Все протоколы", "protocol:list")],
            ])
        )
        return

    if data.startswith("protocol:ask:"):
        pid = data.split(":", 2)[2]
        p = get_protocol(pid)
        if not p:
            return
        await storage.set_mode(user_id, f"protocol:{p.id}")
        await send_text(
            message, f"📖 Выбрана рецептура «{p.title}», версия {p.revision}. "
            "Спросите об этапах, условиях, рисках или отличиях. "
            "Я не стану выдавать изменённую технологию за ту же проверенную рецептуру.",
            keyboard([[("📗 Показать протокол", f"protocol:view:{p.id}")],
                      [("🔬 Лаборатория", "view:ferment")]])
        )
        return

    if data.startswith("protocol:prepare:"):
        pid = data.split(":", 2)[2]
        p = get_protocol(pid)
        if not p:
            return
        await send_text(
            message,
            "📓 Откройте полный первоисточник и убедитесь, что все условия "
            "и меры подходят именно к Вашим продуктам.\n"
            f"Ссылка: {p.source_url}\n\n"
            "Вы прочитали исходный рецепт? "
            "Журнал не является автоматической оценкой пищевой безопасности.",
            keyboard([[("✅ Ознакомился, создать журнал", f"protocol:ack:{p.id}")],
                      [("↩️ Вернуться к рецепту", f"protocol:view:{p.id}")]])
        )
        return

    if data.startswith("protocol:ack:"):
        pid = data.split(":", 2)[2]
        p = get_protocol(pid)
        if not p:
            return
        await storage.set_mode(user_id, f"pnew:{p.id}")
        await send_text(
            message, "📓 Введите название партии (от 2 до 120 символов). "
            "Сушеф сохранит ID и версию источника рядом с журналом. "
            "Это не подтверждение соблюдения технологии или пригодности продукта."
        )
        return

    if data.startswith("protocol:check:"):
        try:
            batch_id = int(data.rsplit(":", 1)[1])
        except ValueError:
            return
        batch = await storage.fermentation_batch(user_id, batch_id)
        if not batch:
            await send_text(message, "Партия недоступна.", fermentation_keyboard())
            return
        p = get_protocol(batch["protocol_id"]) if batch.get("protocol_id") else None
        if not p:
            await send_text(
                message, "Для этой партии нет привязки к опубликованной версии "
                "протокола. Сравнивать показатели автоматически нельзя.",
                fermentation_batch_keyboard(batch_id, batch["finished"])
            )
            return
        if batch["protocol_revision"] != p.revision:
            await send_text(
                message, "Каталог изменился с момента записи этой партии. "
                "Автоматическое сравнение по другой версии запрещено.",
                fermentation_batch_keyboard(batch_id, batch["finished"])
            )
            return
        last = batch["readings"][-1] if batch["readings"] else {}
        celsius = Decimal(str(last["temperature_c"])) if last.get("temperature_c") is not None else None
        fahrenheit = (celsius * Decimal("9") / Decimal("5") + Decimal("32")) if celsius is not None else None
        acidity = Decimal(str(last["ph"])) if last.get("ph") is not None else None
        stage = next((s.code for s in p.stages if s.code == "ferment"), p.stages[0].code)
        assessment = assess_process(
            p.id, stage, fahrenheit, recipe_unchanged=None,
            signs_of_spoilage=None, known_starter=None, ph=acidity
        )
        await send_text(
            message,
            "🔎 Предварительный скрининг (без гарантии безопасности)\n"
            f"Рецептура: {p.id} / {p.revision}\n"
            f"Статус: {assessment.status}\n"
            + "\n".join("• " + reason for reason in assessment.notes)
            + "\n\n❗ Это не разрешение пробовать или есть продукт. "
              "Фактические пропорции, свежесть, санитария, культура и вся история "
              "температур требуют самостоятельной проверки по источнику.",
            fermentation_batch_keyboard(batch_id, batch["finished"])
        )
        return

    if data.startswith("ferment:guide:"):
        category = data.split(":", 2)[2]
        if category not in PROCESS_LABELS:
            return
        await storage.set_mode(user_id, f"ferment:{category}")
        await send_text(message, intake_text(category),
                        keyboard([[("📓 Записать новую партию", f"ferment:new:{category}")],
                                  [("🔬 Все направления", "view:ferment")]]))
        return

    if data.startswith("ferment:new:"):
        category = data.split(":", 2)[2]
        if category not in PROCESS_LABELS:
            return
        await storage.set_mode(user_id, f"fnew:{category}")
        await send_text(message, "📓 Введите название и, если есть, проверенный источник:\n"
                        "Капуста 08.10 | NCHFP sauerkraut\n\n"
                        "После знака «|» пишите название или ссылку на конкретный протокол. "
                        "Сушеф сохранит эту информацию, но не будет автоматически считать "
                        "источник или продукт безопасным.")
        return

    if data == "ferment:list":
        batches = await storage.list_fermentation_batches(user_id)
        if not batches:
            await send_text(message, "📓 Наблюдаемых партий пока нет. "
                            "Выберите тип ферментации и создайте первую.",
                            fermentation_keyboard())
            return
        buttons = [[("📓 " + row["name"][:40], f"fbat:{row['id']}")] for row in batches]
        buttons += [[("🔬 К направлениям", "view:ferment")]]
        await send_text(message, "📓 Ваши партии (последние 20):", keyboard(buttons))
        return

    if data.startswith("fbat:"):
        try:
            batch_id = int(data.split(":", 1)[1])
        except ValueError:
            return
        batch = await storage.fermentation_batch(user_id, batch_id)
        if batch:
            await send_text(message, fermentation_batch_text(batch),
                            fermentation_batch_keyboard(batch_id, batch["finished"]))
        else:
            await send_text(message, "Партия не найдена.", fermentation_keyboard())
        return

    if data.startswith("ferment:observe:"):
        try:
            batch_id = int(data.rsplit(":", 1)[1])
        except ValueError:
            return
        batch = await storage.fermentation_batch(user_id, batch_id)
        if not batch or batch["finished"]:
            await send_text(message, "Партия недоступна или завершена.", fermentation_keyboard())
            return
        await storage.set_mode(user_id, f"flog:{batch_id}")
        await send_text(message, "📝 Введите замер (градусы Цельсия):\n"
                        "t=22; ph=4.1; note=появились пузырьки\n\n"
                        "Можно указать только одно или два поля. "
                        "Запись измерения НЕ подтверждает безопасность продукта.")
        return

    if data.startswith("ferment:finish:"):
        try:
            batch_id = int(data.rsplit(":", 1)[1])
        except ValueError:
            return
        batch = await storage.fermentation_batch(user_id, batch_id)
        if not batch:
            return
        await send_text(
            message, "🏁 Завершить ведение журнала этой партии? "
            "Статус «завершено» не означает, что продукт можно употреблять.",
            keyboard([[("Завершить журнал", f"ferment:confirmfinish:{batch_id}")],
                      [("Отмена", f"fbat:{batch_id}")]]),
        )
        return

    if data.startswith("ferment:confirmfinish:"):
        try:
            batch_id = int(data.rsplit(":", 1)[1])
        except ValueError:
            return
        result = await storage.finish_fermentation_batch(user_id, batch_id)
        await storage.set_mode(user_id, "ask")
        await send_text(message, "🏁 Журнал закрыт. Это не подтверждение пищевой безопасности."
                        if result else "Партия не найдена.", fermentation_keyboard())
        return

    if data.startswith("ferment:remove:"):
        try:
            batch_id = int(data.rsplit(":", 1)[1])
        except ValueError:
            return
        batch = await storage.fermentation_batch(user_id, batch_id)
        if not batch:
            return
        await send_text(message, "Удалить партию «" + batch["name"] + "» вместе со всеми замерами?",
                        keyboard([[("🗑 Да, удалить", f"ferment:confirmremove:{batch_id}")],
                                  [("Отмена", f"fbat:{batch_id}")]]))
        return

    if data.startswith("ferment:confirmremove:"):
        try:
            batch_id = int(data.rsplit(":", 1)[1])
        except ValueError:
            return
        result = await storage.delete_fermentation_batch(user_id, batch_id)
        await storage.set_mode(user_id, "ask")
        await send_text(message, "🗑 Партия удалена." if result else "Партия не найдена.",
                        fermentation_keyboard())
        return

    if data == "view:pantry":
        await send_text(message, pantry_text(await storage.pantry(user_id)), pantry_keyboard())
        return

    if data in {"pantry:add", "pantry:remove"}:
        await storage.set_mode(user_id, data)
        await send_text(message, ("➕ Напишите продукты для добавления:" if data.endswith("add") else
                            "➖ Укажите количество, которое нужно убрать:") +
                        "\nКаждый с новой строки. Например:\nкартофель 500 г\nмолоко 1 л\nяйца 4 шт")
        return

    if data == "pantry:recipe":
        rows = await storage.pantry(user_id)
        if not rows:
            await send_text(message, "Сначала запишем продукты, которыми Вы располагаете.", pantry_keyboard())
            return
        await storage.set_mode(user_id, "pantry_recipe")
        await send_text(message, "🥘 Отлично, продукты я вижу. Что предпочитаете: быстрое, сытное, лёгкое? "
                        "Напишите пожелания, и я составлю рецепт из Ваших запасов.")
        return

    if data == "pantry:confirm_clear":
        await send_text(message, "Удалить все записанные продукты? Это действие нельзя отменить.",
                        keyboard([[("🧹 Да, удалить продукты", "pantry:clear"), ("Отмена", "view:pantry")]]))
        return

    if data == "pantry:clear":
        await storage.clear_pantry(user_id)
        await send_text(message, "📦 Запасы очищены. Когда появятся новые продукты, запишем их!", pantry_keyboard())
        return

    if data == "view:week":
        plan = await storage.get_weekly_plan(user_id)
        await send_text(message, format_day(plan, 0), week_keyboard(0)) if plan else await send_text(
            message, "📅 Пока нет недельного меню.", keyboard([[("Создать меню", "mode:plan")]]))
        return

    if data.startswith("week:day:"):
        plan = await storage.get_weekly_plan(user_id)
        if not plan:
            await send_text(message, "Сначала создайте меню.", main_keyboard())
            return
        try:
            index = int(data.rsplit(":", 1)[1])
            text = format_day(plan, index)
        except (ValueError, IndexError):
            return
        await send_text(message, text, week_keyboard(index))
        return

    if data == "week:all":
        plan = await storage.get_weekly_plan(user_id)
        if plan:
            await send_text(message, format_full_week(plan), week_keyboard(0))
        return

    if data.startswith("week:meal:"):
        plan = await storage.get_weekly_plan(user_id)
        if not plan:
            await send_text(message, "Меню больше нет. Составим новое?", main_keyboard())
            return
        try:
            _, _, day_raw, meal_raw = data.split(":")
            day_index, meal_index = int(day_raw), int(meal_raw)
            if not 0 <= day_index < 7 or not 0 <= meal_index < 3:
                return
        except (ValueError, IndexError):
            return
        meal_key = ("breakfast", "lunch", "dinner")[meal_index]
        dish = plan["days"][day_index][meal_key]
        await storage.set_mode(user_id, f"weekly:{day_index}:{meal_key}")
        await send_text(message, f"👨‍🍳 {MEAL_NAMES[meal_index]}: {dish}\n"
                        "Укажите порции и пожелания, например «на троих, без острого».")
        return

    if data == "view:rating":
        user = await storage.get_user(user_id)
        if user["last_recipe"]:
            await send_text(message, "👨‍🍳 Ну как получилось? Ваш отзыв поможет мне точнее "
                            "подбирать следующие блюда.", rating_keyboard())
        else:
            await send_text(message, "Сначала выберите и приготовьте блюдо.", main_keyboard())
        return

    if data.startswith("rate:"):
        outcome = data.split(":", 1)[1]
        explanations = {
            "great": "Какой триумф! Ваше мастерство сегодня блистает! 🌟",
            "good": "Прекрасный результат! Я учту Вашу оценку. 😋",
            "salty": "Учту, что соли получилось многовато. Следующие рецепты проверим особенно внимательно. 🧂",
            "dry": "Запомню, что блюдо вышло суховатым. Поработаем над сочностью. 🍗",
            "spicy": "Понял: степень остроты нужно уменьшить. 🌶",
            "disliked": "Спасибо за честный отзыв! Подберём вкусы, которые понравятся больше. 💛",
        }
        if outcome not in explanations:
            return
        saved = await storage.rate_last_recipe(user_id, outcome)
        await send_text(message, explanations[outcome] if saved else
                        "Нет последнего рецепта для оценки.", main_keyboard())
        return

    if data == "view:profile":
        user = await storage.get_user(user_id)
        await send_text(message, profile_text(user["preferences"]), profile_keyboard())
        return

    if data.startswith("pref:"):
        key = data.split(":", 1)[1]
        if key in PREF_LABELS:
            await storage.set_mode(user_id, "pref:" + key)
            await send_text(message, f"Введите значение для «{PREF_LABELS[key]}».\nДля очистки отправьте «-».")
        return

    if data == "recipe:show":
        user = await storage.get_user(user_id)
        recipe = user["last_recipe"]
        await send_text(message, format_recipe(recipe), recipe_keyboard()) if recipe else await send_text(message, "Сначала выберите блюдо.", main_keyboard())
        return

    if data == "recipe:save":
        saved = await storage.save_favorite(user_id)
        await send_text(message, "❤️ Рецепт сохранён! Ваш вкус достоин собственной кулинарной книги." if saved else "Сначала создайте рецепт.", main_keyboard())
        return

    if data == "view:shop":
        user = await storage.get_user(user_id)
        recipe = user["last_recipe"]
        await send_text(message,
                        format_shopping_comparison(recipe, await storage.pantry(user_id)) if recipe else
                        "🛒 Сначала создайте или выберите рецепт.", main_keyboard())
        return

    if data == "view:favorites":
        items = await storage.favorites(user_id)
        if not items:
            await send_text(message, "❤️ Здесь пока пусто. Лучшие кулинарные истории ещё впереди!", main_keyboard())
            return
        rows = [[(item["recipe"]["title"][:48], f"fav:{item['id']}")] for item in items]
        rows.append([("🏠 Главное меню", "view:main")])
        await send_text(message, "❤️ Избранные рецепты (10 последних):", keyboard(rows))
        return

    if data.startswith("fav:"):
        try:
            favorite_id = int(data.split(":", 1)[1])
        except ValueError:
            return
        user = await storage.get_user(user_id)
        restricted = bool(user["preferences"].get("allergens") or user["preferences"].get("excluded"))
        recipe = await storage.select_favorite(user_id, favorite_id, activate=not restricted)
        if recipe and restricted:
            await send_text(message,
                            "⚠️ Этот сохранённый рецепт НЕ проверен с учётом Ваших текущих ограничений. "
                            "Я не активировал его для готовки. Составьте новый адаптированный рецепт.\n\n" +
                            format_recipe(recipe), main_keyboard())
        elif recipe:
            await send_text(message, format_recipe(recipe), recipe_keyboard())
        else:
            await send_text(message, "Рецепт не найден.", main_keyboard())
        return

    if data == "cook:start":
        session = await storage.start_cooking(user_id)
        if session:
            await send_text(message, cooking_text(session), cooking_keyboard())
        else:
            await storage.set_mode(user_id, "recipe")
            await send_text(message, "👨‍🍳 Для начала выберем блюдо. Что у Вас есть из продуктов?")
        return

    if data == "cook:previous":
        session = await storage.current_cooking(user_id)
        if not session:
            await send_text(message, "Активной готовки нет.", main_keyboard())
        else:
            previous = await storage.set_cooking_step(user_id, session["step_index"] - 1)
            await send_text(message, cooking_text(previous), cooking_keyboard())
        return

    if data == "cook:next":
        session = await storage.advance_cooking(user_id)
        if not session:
            await send_text(message, "Активного приготовления нет. Выберите рецепт.", main_keyboard())
        elif session["step_index"] >= len(session["recipe"]["steps"]):
            await send_text(message, cooking_text(session) + "\n\nХотите оценить результат?", rating_keyboard())
        else:
            await send_text(message, cooking_text(session), cooking_keyboard())
        return

    if data == "delete:confirm":
        await storage.delete_user(user_id)
        await send_text(message, "🗑 Ваши данные удалены из базы Сушефа. Чтобы начать заново — /start.")
        return

    await send_text(message, "Неизвестная кнопка. Вернёмся к меню.", main_keyboard())
