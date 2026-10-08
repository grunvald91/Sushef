"""Telegram-интерфейс MVP. Все пользовательские состояния хранятся в БД."""
from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .chef import Chef, RecipeFormatError, format_recipe
from .fermentation import PROCESS_LABELS, fermentation_system_context, intake_text
from .fermentation_journal import SAFETY_REMINDER, observation_text, parse_observation
from .pantry import format_quantity, format_shopping_comparison, parse_product_line
from .weekly import DAY_NAMES, MEAL_NAMES, WeeklyPlanError, format_day, format_full_week
from .config import Settings
from .storage import Storage

logger = logging.getLogger(__name__)
router = Router(name="telegram")

PREF_LABELS = {
    "allergens": "Аллергены (если есть)",
    "excluded": "Не ем",
    "likes": "Любимые продукты",
    "equipment": "Кухонная техника",
    "portions": "Количество порций",
}

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
        [("📦 Мои продукты", "view:pantry"), ("📆 Моё меню", "view:week")],
        [("🥗 Мой профиль", "view:profile"), ("💬 Спросить шефа", "mode:ask")],
        [("🔬 Микробиология и ферментация", "view:ferment")],
    ])


def recipe_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [("👨‍🍳 Готовим пошагово", "cook:start")],
        [("❤️ Сохранить рецепт", "recipe:save"), ("🛒 Список продуктов", "view:shop")],
        [("😋 Оценить результат", "view:rating")],
        [("🏠 Главное меню", "view:main")],
    ])


def fermentation_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [("🥬 Молочнокислые овощи", "ferment:guide:vegetables")],
        [("🥛 Йогурт и молочные", "ferment:guide:dairy")],
        [("🍞 Закваски и тесто", "ferment:guide:sourdough")],
        [("🍄 Кодзи и пищевые грибные культуры", "ferment:guide:koji")],
        [("🧪 Внешние пищевые ферменты", "ferment:guide:enzymes")],
        [("🔬 Другие процессы", "ferment:guide:other")],
        [("📓 Журнал ферментации", "ferment:list")],
        [("🏠 Главное меню", "view:main")],
    ])


def fermentation_batch_keyboard(batch_id: int, finished: bool) -> InlineKeyboardMarkup:
    buttons = []
    if not finished:
        buttons += [[("📝 Записать замер", f"ferment:observe:{batch_id}")],
                    [("🏁 Завершить наблюдение", f"ferment:finish:{batch_id}")]]
    buttons += [[("🗑 Удалить партию", f"ferment:remove:{batch_id}")],
                [("📓 Все партии", "ferment:list"), ("🔬 Раздел", "view:ferment")]]
    return keyboard(buttons)


def fermentation_batch_text(batch: dict) -> str:
    label = PROCESS_LABELS.get(batch["category"], "Неизвестный процесс")
    state = "завершено наблюдение" if batch["finished"] else "наблюдение продолжается"
    lines = [f"📓 {batch['name']}", label, f"Статус: {state}", ""]
    for observation in batch["readings"]:
        lines.append(f"• {observation['observed_at'][:16]}: {observation_text(observation)}")
    if not batch["readings"]:
        lines.append("Измерений пока нет.")
    return "\n".join(lines) + "\n\n" + SAFETY_REMINDER


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
        [("👥 Порции", "pref:portions")],
        [("🏠 Главное меню", "view:main")],
    ])


def profile_text(prefs: dict[str, str]) -> str:
    lines = ["🥗 Ваши настройки кухни:"]
    lines.extend(f"• {label}: {prefs.get(key) or 'не указано'}" for key, label in PREF_LABELS.items())
    lines.append("\nВыбирайте параметр кнопкой. Чтобы очистить значение, отправьте один символ «-».")
    return "\n".join(lines)


def cooking_text(session: dict[str, Any]) -> str:
    recipe = session["recipe"]
    index = session["step_index"]
    steps = recipe.get("steps", [])
    if index >= len(steps):
        return "🎉 Готово! Вы прекрасно потрудились. Приятного аппетита!"
    return f"👨‍🍳 {recipe['title']}\nШаг {index + 1}/{len(steps)}:\n\n{steps[index]}\n\nНапишите вопрос, если что-то непонятно."


def cooking_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [("⬅️ Предыдущий", "cook:previous"), ("✅ Следующий", "cook:next")],
        [("🥘 Показать рецепт", "recipe:show"), ("🏠 Меню", "view:main")],
    ])


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
    # Ограничение Telegram — 4096 символов; используем запас.
    chunks = [text[i:i + 3400] for i in range(0, len(text), 3400)] or ["(пустой ответ)"]
    for i, chunk in enumerate(chunks):
        await message.answer(chunk, reply_markup=markup if i == len(chunks) - 1 else None)


async def private_only(message: Message) -> bool:
    if message.chat.type == "private":
        return True
    await message.answer("Я работаю в личных сообщениях — там удобнее хранить Ваши рецепты и настройки.")
    return False


@router.message(CommandStart())
async def start(message: Message, storage: Storage) -> None:
    if not await private_only(message) or not message.from_user:
        return
    await storage.get_user(message.from_user.id)
    await send_text(
        message,
        "👨‍🍳 Добро пожаловать на кухню Сушефа!\n\n"
        "Великолепно, что Вы заглянули! Здесь даже картошка чувствует себя звездой ресторана. "
        "Выбирайте, чем займёмся.\n\n"
        "Основной режим — текстовый; фото включается отдельно после проверки ClaudeHub, голос пока недоступен.",
        main_keyboard(),
    )


@router.message(Command("menu", "help"))
async def help_menu(message: Message) -> None:
    if await private_only(message):
        await send_text(
            message,
            "👨‍🍳 Сушеф поможет придумать рецепт, спасти блюдо, составить меню "
            "и провести Вас по шагам приготовления.\n\n"
            "Команды: /start, /menu, /help, /profile, /pantry, /week, /ferment, /reset, /privacy, /delete_me.",
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


@router.message(Command("reset", "cancel"))
async def reset_dialog(message: Message, storage: Storage) -> None:
    if not await private_only(message) or not message.from_user:
        return
    await storage.clear_chat(message.from_user.id)
    await send_text(message, "Диалог очищен. Ваш профиль и любимые рецепты сохранены. 🧑‍🍳", main_keyboard())


@router.message(Command("privacy"))
async def privacy(message: Message) -> None:
    if await private_only(message):
        await send_text(
            message,
            "🔒 Для работы сохраняются Ваш Telegram ID, выбранные настройки, "
            "до 40 последних реплик диалога, рецепты, оценки блюд, записи о продуктах, недельное меню, партии ферментации, их замеры и шаги приготовления. "
            "Запросы, история диалога и указанные предпочтения передаются провайдеру ClaudeHub "
            "для генерации ответа. Никаких сторонних рекламных рассылок бот не делает.\n\n"
            "/reset — очистить диалог.\n/delete_me — полностью удалить сохранённые данные.\n"
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

    if mode.startswith("pref:"):
        key = mode.split(":", 1)[1]
        if key not in PREF_LABELS:
            await storage.set_mode(user_id, "ask")
            await send_text(message, "Параметр не найден. Вернёмся к меню.", main_keyboard())
            return
        if key == "portions" and text != "-":
            if not text.isdigit() or not 1 <= int(text) <= 50:
                await send_text(message, "Укажите количество порций целым числом от 1 до 50 (или «-», чтобы очистить).")
                return
        await storage.set_preference(user_id, key, text)
        await storage.set_mode(user_id, "ask")
        updated = await storage.get_user(user_id)
        await send_text(message, "Прекрасно! Настройки обновлены.\n\n" + profile_text(updated["preferences"]), profile_keyboard())
        return

    if mode.startswith("fnew:"):
        category = mode.split(":", 1)[1]
        try:
            batch_id = await storage.create_fermentation_batch(user_id, category, text)
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
        if mode in {"recipe", "pantry_recipe"} or mode.startswith("weekly:"):
            if mode == "pantry_recipe":
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
                query = text
            recipe = await chef.recipe(query, preferences)
            await storage.set_recipe(user_id, recipe)
            await storage.set_mode(user_id, "ask")
            await send_text(message, "Ваше кулинарное приключение начинается! 🥘\n\n" + format_recipe(recipe), recipe_keyboard())
        elif mode == "plan":
            plan = await chef.weekly_plan(text, preferences, await storage.pantry(user_id))
            await storage.save_weekly_plan(user_id, plan)
            await storage.set_mode(user_id, "ask")
            await send_text(message, "📅 Меню на неделю готово! Начнём с понедельника.\n\n" +
                            format_day(plan, 0), week_keyboard(0))
        else:
            history = await storage.get_history(user_id)
            context = ""
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
            answer = await chef.answer(mode, text, preferences, history, context)
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
        await send_text(message, "Какой прекрасный день, чтобы приготовить что-нибудь вкусное! 👨‍🍳", main_keyboard())
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
        await send_text(message, "📓 Как назвать партию? Например: «Капуста 08.10». "
                        "Партия — только журнал наблюдений, а не удостоверение безопасности.")
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
