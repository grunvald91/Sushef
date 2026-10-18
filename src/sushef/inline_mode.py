"""Inline-режим: Сушеф отвечает в любом чате через `@бот вопрос`. Только по подписке.

Ответ ИИ не генерируется на каждое нажатие клавиши: в выдаче лишь заготовка
«Спросить Сушефа». Запрос к ClaudeHub выполняется после выбора результата
(chosen_inline_result, нужен /setinlinefeedback в BotFather), затем
отправленное сообщение редактируется готовым ответом.
"""
from __future__ import annotations

import hashlib
import logging
from html import escape
from time import time

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import (
    ChosenInlineResult, InlineKeyboardButton, InlineKeyboardMarkup, InlineQuery,
    InlineQueryResultArticle, InlineQueryResultsButton, InputRichMessage, InputTextMessageContent,
)

from .chef import Chef, format_recipe
from .config import Settings
from .storage import Storage
from .telegram_dialogue import rich_dialog_markdown, structure_culinary_answer
from .telegram_format import telegram_chunks

logger = logging.getLogger(__name__)
router = Router(name="inline")

MIN_QUESTION = 3
INLINE_INSTRUCTION = (
    "\n\nОтвет будет опубликован в общем чате Telegram, где его увидят другие люди. "
    "Ответь компактно, до 1500 символов, без обращения по имени и без вопросов в конце."
)


def question_id(query: str) -> str:
    return "ask:" + hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]


async def inline_allowed(user, storage: Storage, settings: Settings) -> bool:
    """Inline — только для оплативших (пробные запросы не действуют) и освобождённых."""
    from .bot import payment_exempt
    if not settings.payments_enabled or await payment_exempt(user, storage, settings):
        return True
    return (await storage.subscription(user.id))["paid_until_ts"] > int(time())


async def bot_link(bot, payload: str) -> str:
    me = await bot.me()
    return f"https://t.me/{me.username}?start={payload}"


@router.inline_query()
async def inline_query(query: InlineQuery, storage: Storage, settings: Settings) -> None:
    text = (query.query or "").strip()
    if not await inline_allowed(query.from_user, storage, settings):
        await query.answer(
            [], cache_time=10, is_personal=True,
            button=InlineQueryResultsButton(
                text=f"⭐ Сушеф в любом чате — по подписке {settings.stars_price} ⭐",
                start_parameter="subscribe"),
        )
        return
    results = []
    if len(text) >= MIN_QUESTION:
        open_bot = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="👨‍🍳 Открыть Сушефа", url=await bot_link(query.bot, "inline"))]])
        results.append(InlineQueryResultArticle(
            id=question_id(text),
            title="👨‍🍳 Спросить Сушефа",
            description=text[:120],
            input_message_content=InputTextMessageContent(
                message_text="👨‍🍳 <b>Сушеф обдумывает вопрос:</b>\n«" + escape(text[:300]) + "»…",
                parse_mode="HTML"),
            reply_markup=open_bot,  # без клавиатуры Telegram не передаст inline_message_id
        ))
    # Поделиться своими сохранёнными рецептами — мгновенно, без ИИ.
    needle = text.casefold()
    saved = await storage.archived_recipes(query.from_user.id, limit=50)
    for item in saved:
        recipe = item["recipe"]
        title = str(recipe.get("title") or "Рецепт")
        if needle and needle not in title.casefold():
            continue
        results.append(InlineQueryResultArticle(
            id=f"rec:{item['id']}",
            title="📖 " + title[:60],
            description="Поделиться рецептом из «Моих рецептов»",
            input_message_content=InputTextMessageContent(
                message_text=telegram_chunks(format_recipe(recipe))[0], parse_mode="HTML"),
        ))
        if len(results) >= 20:
            break
    await query.answer(
        results, cache_time=0, is_personal=True,
        button=None if results else InlineQueryResultsButton(
            text="📖 Как пользоваться Сушефом в чатах", start_parameter="inline"),
    )


@router.chosen_inline_result(F.result_id.startswith("ask:"))
async def chosen_question(result: ChosenInlineResult, storage: Storage, chef: Chef,
                          settings: Settings) -> None:
    if not result.inline_message_id:
        return
    bot = result.bot
    question = (result.query or "").strip()

    async def show(text: str, *, rich: bool = False) -> None:
        markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
            text="👨‍🍳 Спросить Сушефа самому", url=await bot_link(bot, "inline"))]])
        if rich and settings.telegram_rich_recipe_cards and len(text) >= 120:
            try:
                await bot.edit_message_text(
                    inline_message_id=result.inline_message_id, reply_markup=markup,
                    rich_message=InputRichMessage(markdown=rich_dialog_markdown(text)))
                return
            except TelegramBadRequest as exc:
                logger.info("Inline rich edit unavailable: %s", type(exc).__name__)
        chunks = telegram_chunks(text)
        body = chunks[0] + ("\n\n<i>Полный ответ — в чате с Сушефом.</i>" if len(chunks) > 1 else "")
        await bot.edit_message_text(inline_message_id=result.inline_message_id, text=body,
                                    parse_mode="HTML", reply_markup=markup)

    # Повторная проверка: выдачу могли получить до окончания подписки.
    if len(question) < MIN_QUESTION or not await inline_allowed(result.from_user, storage, settings):
        await show("⭐ Ответы Сушефа в чатах доступны по подписке. Оформить — в боте: /subscribe")
        return
    if not await storage.use_quota(result.from_user.id, settings.daily_ai_limit):
        await show("На сегодня лимит вопросов к Сушефу исчерпан. Завтра продолжим! 🍲")
        return
    try:
        prefs = (await storage.get_user(result.from_user.id))["preferences"]
        answer = await chef.answer("ask", question[:1000] + INLINE_INSTRUCTION, prefs, [])
        await show(structure_culinary_answer(answer), rich=True)
    except Exception as exc:
        logger.warning("Inline answer failed: %s", type(exc).__name__)
        try:
            await show("Сушеф сейчас не смог ответить. Попробуйте ещё раз чуть позже.")
        except Exception:
            pass
