"""Bot API 10.3 culinary UI with safe rich-message/HTML fallback.

Rich messages are not sent until all data is escaped. Older Telegram clients or
API installations can reject this method; only explicit API validation errors
trigger fallback to the existing HTML text UI. Network ambiguity does not
retry automatically, avoiding duplicate recipes.
"""
from __future__ import annotations

from html import escape
import logging

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import BotCommand, InputRichMessage, InlineKeyboardMarkup, Message

from .chef import format_recipe
from .telegram_format import telegram_chunks

logger = logging.getLogger(__name__)


def recipe_rich_html(recipe: dict) -> str:
    """Native Rich Message layout. Never interpolate unescaped LLM content."""
    e = lambda value: escape(str(value), quote=True)
    title = e(recipe.get("title") or "Ваш рецепт")
    minutes = recipe.get("time_minutes")
    servings = recipe.get("servings")
    blocks = [f"<h2>🍽 {title}</h2>"]
    if type(minutes) is int and type(servings) is int:
        blocks.append(f"<p>⏱ {minutes} мин · 👥 {servings} порц.</p>")
    chef_note = recipe.get("chef_note")
    if isinstance(chef_note, str) and chef_note.strip():
        blocks.append(f"<blockquote>👨‍🍳 {e(chef_note[:220])}</blockquote>")
    blocks.append("<h3>🥗 Продукты</h3>")
    items = [
        f"<li><b>{e(row.get('name', 'Ингредиент'))}</b> — {e(row.get('amount', 'по вкусу'))}</li>"
        for row in recipe.get("ingredients", []) if isinstance(row, dict)
    ]
    if items:
        blocks.append("<ul>" + "".join(items) + "</ul>")
    blocks.append("<h3>👨‍🍳 Как приготовить</h3>")
    explanations = {entry["step_index"]: entry for entry in recipe.get("step_insights", [])
                    if isinstance(entry, dict) and type(entry.get("step_index")) is int}
    for i, step in enumerate(recipe.get("steps", [])):
        blocks.append(f"<p><b>{i + 1}.</b> {e(step)}</p>")
        detail = explanations.get(i) or {}
        why = detail.get("why")
        if isinstance(why, str) and why:
            body = f"<p><b>Почему:</b> {e(why)}</p>"
            for key, label in (("cue", "Признак"), ("fix", "Если не получилось")):
                if isinstance(detail.get(key), str) and detail[key]:
                    body += f"<p><b>{label}:</b> {e(detail[key])}</p>"
            blocks.append(f"<details><summary>💡 Секрет {i + 1}-го шага</summary>{body}</details>")
    notes = recipe.get("safety_notes")
    if isinstance(notes, list) and notes:
        blocks.append("<h3>🔍 Важно учесть</h3>")
        blocks.append("<ul>" + "".join(f"<li>{e(note)}</li>" for note in notes[:5]) + "</ul>")
    reference = recipe.get("catalog_reference")
    if isinstance(reference, dict):
        url = reference.get("source_url", "")
        if isinstance(url, str) and url.startswith("https://"):
            blocks.append(f"<footer>Адаптация по мотивам: {e(reference.get('publisher', 'кулинарный источник'))}. "
                          f"<a href=\"{e(url)}\">Первоисточник</a></footer>")
    # Never render excessively large experimental payloads; caller falls back.
    return "\n".join(blocks)


async def send_recipe_card(
    message: Message,
    recipe: dict,
    markup: InlineKeyboardMarkup | None,
    *,
    rich_enabled: bool = True,
) -> None:
    """Use Bot API 10.3 Rich Message, preserving a readable safe HTML fallback."""
    rich_html = recipe_rich_html(recipe)
    if rich_enabled and len(rich_html) <= 10500:
        try:
            await message.bot.send_rich_message(
                chat_id=message.chat.id,
                rich_message=InputRichMessage(html=rich_html),
                reply_markup=markup,
            )
            return
        except TelegramBadRequest as exc:
            logger.info("Rich recipe card unavailable; using standard HTML: %s", type(exc).__name__)
    chunks = telegram_chunks(format_recipe(recipe))
    for index, chunk in enumerate(chunks):
        await message.answer(
            chunk, parse_mode="HTML",
            reply_markup=markup if index == len(chunks) - 1 else None,
        )


async def show_chef_thinking(message: Message, *, enabled: bool = True, mode: str = "ask", preferences: dict | None = None) -> bool:
    """Temporary Telegram draft while ClaudeHub prepares a full final answer.

    Does NOT claim token-by-token streaming. A real, persistent answer always
    follows through send_text/send_recipe_card. Draft failures don't fail AI.
    """
    if not enabled or message.chat.type != "private":
        return False
    draft_id = getattr(message, "message_id", None)
    if type(draft_id) is not int or draft_id <= 0:
        return False
    prefs = preferences or {}
    informal = prefs.get("address_form") == "ты"
    possessive = "твой" if informal else "Ваш"
    if mode in {"recipe", "pantry_recipe"} or mode.startswith(("catalog:", "weekly:")):
        preview = f"👨‍🍳 Бережно подбираю рецепт под {possessive} вкус…"
    elif mode == "plan":
        preview = f"📅 Составляю меню с учётом {('твоих' if informal else 'Ваших')} пожеланий…"
    elif mode.startswith(("ferment:", "science:", "protocol:")):
        preview = "🔬 Проверяю технологические детали…"
    elif mode == "rescue":
        preview = "🛠 Ищу способ помочь блюду…"
    else:
        preview = "👨‍🍳 Обдумываю ответ с вниманием к деталям…"
    try:
        await message.bot.send_message_draft(
            chat_id=message.chat.id,
            message_thread_id=getattr(message, "message_thread_id", None),
            draft_id=draft_id,
            text=preview,
            can_stop=False,
        )
        return True
    except (TelegramAPIError, AttributeError) as exc:
        logger.debug("Temporary draft unavailable: %s", type(exc).__name__)
        return False


PUBLIC_COMMANDS = (
    ("start", "Добро пожаловать на кухню"),
    ("menu", "Главное меню Сушефа"),
    ("recipes", "Моя коллекция блюд"),
    ("pantry", "Продукты, которые есть дома"),
    ("week", "Моё меню на неделю"),
    ("timers", "Мои кухонные таймеры"),
    ("profile", "Мои вкусы и стиль общения"),
    ("memory", "Кулинарная память"),
    ("remember", "Запомнить факт о моей кухне"),
    ("ferment", "Ферментация и протоколы"),
    ("subscribe", "Купить подписку за Telegram Stars"),
    ("inline", "Сушеф в любом чате"),
    ("help", "Инструкция: как пользоваться"),
    ("support", "Написать в службу поддержки"),
    ("paysupport", "Вопрос об оплате или возврате"),
    ("terms", "Условия подписки"),
    ("cancel", "Отменить текущий ввод"),
    ("reset", "Очистить диалог и готовку"),
    ("privacy", "Мои данные и приватность"),
    ("export_my_data", "Выгрузить мои данные"),
    ("delete_me", "Удалить все мои данные"),
    ("myid", "Мой Telegram ID"),
)
SUPPORT_COMMANDS = (
    ("tickets", "Поддержка: открытые обращения"),
    ("refund", "Поддержка: возврат Stars по номеру платежа"),
)


async def configure_bot_commands(bot, support_admin_ids=()) -> bool:
    """Native command menu for every client language; staff also see support commands.

    Does not touch the BotFather menu button / Mini App.
    """
    from aiogram.types import BotCommandScopeChat

    public = [BotCommand(command=c, description=d) for c, d in PUBLIC_COMMANDS]
    staff = public + [BotCommand(command=c, description=d) for c, d in SUPPORT_COMMANDS]
    try:
        # Без language_code — для клиентов на любом языке, иначе меню видно только «ru».
        await bot.set_my_commands(public)
        await bot.set_my_commands(public, language_code="ru")
    except (TelegramAPIError, AttributeError) as exc:
        logger.info("Bot commands were not updated: %s", type(exc).__name__)
        return False
    for admin_id in sorted(support_admin_ids):
        try:
            await bot.set_my_commands(staff, scope=BotCommandScopeChat(chat_id=admin_id))
        except (TelegramAPIError, AttributeError) as exc:
            # Сотрудник ещё не открыл бота: команды поддержки всё равно работают вручную.
            logger.info("Support commands were not set: %s", type(exc).__name__)
    return True
