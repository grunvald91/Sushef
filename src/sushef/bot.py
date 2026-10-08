"""Telegram-интерфейс MVP. Все пользовательские состояния хранятся в БД."""
from __future__ import annotations

import logging
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from .chef import Chef, RecipeFormatError, format_recipe, shopping_list
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
    "plan": "📅 Для меню на неделю укажите количество человек, бюджет, предпочтения и ограничения. Если данных не хватит, я уточню.",
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
        [("🥗 Мой профиль", "view:profile"), ("💬 Спросить шефа", "mode:ask")],
    ])


def recipe_keyboard() -> InlineKeyboardMarkup:
    return keyboard([
        [("👨‍🍳 Готовим пошагово", "cook:start")],
        [("❤️ Сохранить рецепт", "recipe:save"), ("🛒 Список продуктов", "view:shop")],
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
        [("✅ Сделано, следующий шаг", "cook:next")],
        [("🥘 Показать рецепт", "recipe:show"), ("🏠 Меню", "view:main")],
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
        "Пока доступны текстовые запросы; фото и голос появятся позже.",
        main_keyboard(),
    )


@router.message(Command("menu", "help"))
async def help_menu(message: Message) -> None:
    if await private_only(message):
        await send_text(
            message,
            "👨‍🍳 Сушеф поможет придумать рецепт, спасти блюдо, составить меню "
            "и провести Вас по шагам приготовления.\n\n"
            "Команды: /start, /menu, /help, /profile, /reset, /privacy, /delete_me.",
            main_keyboard(),
        )


@router.message(Command("profile"))
async def show_profile(message: Message, storage: Storage) -> None:
    if not await private_only(message) or not message.from_user:
        return
    user = await storage.get_user(message.from_user.id)
    await send_text(message, profile_text(user["preferences"]), profile_keyboard())


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
            "до 40 последних реплик диалога, рецепты и шаги приготовления. "
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


@router.message(F.photo | F.voice | F.video | F.audio | F.document)
async def unsupported_media(message: Message) -> None:
    if await private_only(message):
        await send_text(
            message,
            "Я уже мечтаю разглядывать Ваши продукты и слушать рассказы о шедеврах! "
            "Но в этой версии понимаю только текст. Опишите продукты или задачу словами. 😊",
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

    if not await storage.use_quota(user_id, settings.daily_ai_limit):
        await send_text(message, "На сегодня лимит обращений к ИИ исчерпан. Завтра (по UTC) снова сможем творить вкусное! 🍲")
        return

    try:
        await message.bot.send_chat_action(message.chat.id, "typing")
        if mode == "recipe":
            recipe = await chef.recipe(text, user["preferences"])
            await storage.set_recipe(user_id, recipe)
            await send_text(message, "Ваше кулинарное приключение начинается! 🥘\n\n" + format_recipe(recipe), recipe_keyboard())
        else:
            history = await storage.get_history(user_id)
            context = ""
            if mode == "cook":
                cooking = await storage.current_cooking(user_id)
                if cooking:
                    context = cooking_text(cooking)
                else:
                    await storage.set_mode(user_id, "ask")
                    mode = "ask"
            answer = await chef.answer(mode, text, user["preferences"], history, context)
            await storage.add_exchange(user_id, text, answer)
            await send_text(message, answer, cooking_keyboard() if mode == "cook" else main_keyboard())
    except RecipeFormatError:
        logger.warning("Model returned invalid recipe JSON")
        await send_text(message, "Я пока не смог аккуратно оформить рецепт. Попробуйте уточнить продукты и повторить запрос.", main_keyboard())
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
        await send_text(message, shopping_list(recipe) if recipe else "🛒 Сначала создайте или выберите рецепт.", main_keyboard())
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
        recipe = await storage.select_favorite(user_id, favorite_id)
        await send_text(message, format_recipe(recipe), recipe_keyboard()) if recipe else await send_text(message, "Рецепт не найден.", main_keyboard())
        return

    if data == "cook:start":
        session = await storage.start_cooking(user_id)
        if session:
            await send_text(message, cooking_text(session), cooking_keyboard())
        else:
            await storage.set_mode(user_id, "recipe")
            await send_text(message, "👨‍🍳 Для начала выберем блюдо. Что у Вас есть из продуктов?")
        return

    if data == "cook:next":
        session = await storage.advance_cooking(user_id)
        if not session:
            await send_text(message, "Активного приготовления нет. Выберите рецепт.", main_keyboard())
        elif session["step_index"] >= len(session["recipe"]["steps"]):
            await send_text(message, cooking_text(session), main_keyboard())
        else:
            await send_text(message, cooking_text(session), cooking_keyboard())
        return

    if data == "delete:confirm":
        await storage.delete_user(user_id)
        await send_text(message, "🗑 Ваши данные удалены из базы Сушефа. Чтобы начать заново — /start.")
        return

    await send_text(message, "Неизвестная кнопка. Вернёмся к меню.", main_keyboard())
