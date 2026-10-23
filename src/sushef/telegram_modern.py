"""Bot API 10.3 culinary UI with safe rich-message/HTML fallback.

Rich messages are not sent until all data is escaped. Older Telegram clients or
API installations can reject this method; only explicit API validation errors
trigger fallback to the existing HTML text UI. Network ambiguity does not
retry automatically, avoiding duplicate recipes.
"""
from __future__ import annotations

import asyncio
from html import escape
import logging

from aiogram.exceptions import TelegramAPIError, TelegramBadRequest
from aiogram.types import BotCommand, InputRichMessage, InlineKeyboardMarkup, Message, ReactionTypeEmoji

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
        # warning, а не debug: иначе в проде не видно, что «думаю…» не доходит до людей
        logger.warning("Temporary draft unavailable: %s: %s", type(exc).__name__, exc)
        return False


class ChefWorking:
    """Видимый сигнал «Сушеф услышал и работает» на всё время ожидания ИИ.

    Три независимых сигнала, любой из них может не сработать, ответ от этого
    не страдает (это украшение, а не часть ответа):
    * реакция 👀 на сообщение пользователя — мгновенно, снимается, когда ответ готов;
    * черновик «Обдумываю ответ…» (его потом подхватывает потоковый черновик
      с тем же draft_id, если ClaudeHub отдаёт поток);
    * «печатает…», которое поддерживается заново, пока ИИ не ответил: Telegram
      гасит его через несколько секунд, а рецепты и меню готовятся дольше.
    Ничего не повторяется автоматически с отправкой сообщений — только статусы.
    """

    def __init__(self, message: Message, *, mode: str = "ask", preferences: dict | None = None,
                 draft_enabled: bool = True, reaction_enabled: bool = True,
                 typing_interval: float = 4.0):
        self.message = message
        self.mode = mode
        self.preferences = preferences
        self.draft_enabled = draft_enabled
        self.reaction_enabled = reaction_enabled
        self.typing_interval = typing_interval
        self._typing_task: asyncio.Task | None = None
        self._reacted = False

    async def start(self) -> None:
        self._typing_task = asyncio.create_task(self._keep_typing())
        await asyncio.gather(self._react(), self._draft())

    async def stop(self) -> None:
        task, self._typing_task = self._typing_task, None
        if task is not None:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if self._reacted:
            self._reacted = False
            try:
                await self.message.bot.set_message_reaction(
                    chat_id=self.message.chat.id, message_id=self.message.message_id, reaction=[])
            except Exception as exc:
                logger.warning("Seen reaction was not cleared: %s: %s", type(exc).__name__, exc)

    async def _keep_typing(self) -> None:
        try:
            while True:
                await self.message.bot.send_chat_action(self.message.chat.id, "typing")
                await asyncio.sleep(self.typing_interval)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Typing status stopped: %s: %s", type(exc).__name__, exc)

    async def _react(self) -> None:
        sender = getattr(self.message, "from_user", None)
        # Реагируем только на сообщение человека, а не на собственное сообщение бота с кнопкой.
        if not self.reaction_enabled or sender is None or getattr(sender, "is_bot", False):
            return
        try:
            if self.message.chat.type != "private":
                return
            await self.message.bot.set_message_reaction(
                chat_id=self.message.chat.id, message_id=self.message.message_id,
                reaction=[ReactionTypeEmoji(emoji="👀")])
            self._reacted = True
        except Exception as exc:
            logger.warning("Seen reaction unavailable: %s: %s", type(exc).__name__, exc)

    async def _draft(self) -> None:
        try:
            await show_chef_thinking(self.message, enabled=self.draft_enabled,
                                     mode=self.mode, preferences=self.preferences)
        except Exception as exc:
            logger.warning("Thinking draft failed: %s: %s", type(exc).__name__, exc)


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
