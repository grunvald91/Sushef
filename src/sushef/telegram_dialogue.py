"""Structured native Telegram Rich Markdown for ordinary ClaudeHub dialogue.

Previously only JSON recipe mode used Rich Messages; ordinary answers were
sent as simple text. Cover free chat, cooking Q&A, rescue and explanations.

Fallback occurs only on explicit TelegramBadRequest, never ambiguous network
errors where a message might already have been delivered.
"""
from __future__ import annotations

import hashlib
import logging
import re
from html import escape

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, InputRichMessage, Message

from .telegram_format import telegram_chunks

logger = logging.getLogger(__name__)

_JOINED_STEPS = re.compile(r"(?<=[.!?])(?=(?:[1-9]|1\d)\.\s+[А-ЯЁ])")
_JOINED_SENTENCES = re.compile(r"([.!?])(?=[А-ЯЁ][а-яё])")
_SECTION = re.compile(
    r"^(?:(?:продукты|ингредиенты)|(?:как готовить|приготовление|способ приготовления)"
    r"|(?:пара хитростей[^:]*|советы[^:]*|секреты[^:]*))\s*:\s*$",
    re.IGNORECASE,
)
_BULLET = re.compile(r"^(\s*)[•*]\s+(.*)$")
_NUMBERED = re.compile(r"^(\d{1,2})[.)]\s+(.+)$")
_SERVINGS = re.compile(r"^на\s+\d+(?:\s*[-–]\s*\d+)?\s+порци[юий]:\s*$", re.IGNORECASE)


def structure_culinary_answer(text: str) -> str:
    """Improve visual layout without changing any amounts or inventing foods."""
    if not isinstance(text, str):
        raise TypeError("Expected AI answer text")
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return ""
    text = _JOINED_STEPS.sub("\n\n", text)
    text = _JOINED_SENTENCES.sub(r"\1 ", text)
    result: list[str] = []
    in_code = False
    for original in text.split("\n"):
        line = original.strip()
        if line.startswith(chr(96) * 3):
            in_code = not in_code
            result.append(original)
            continue
        if in_code:
            result.append(original)
            continue
        if not line:
            if result and result[-1] != "":
                result.append("")
            continue
        if _SECTION.fullmatch(line):
            plain = line.casefold()
            if plain.startswith(("продукты", "ингредиенты")):
                result.extend(["", "## 🥗 Продукты", ""])
            elif plain.startswith(("как готовить", "приготовление", "способ")):
                result.extend(["", "## 👨‍🍳 Как приготовить", ""])
            else:
                result.extend(["", "## 💡 Секреты и советы", ""])
            continue
        if _SERVINGS.fullmatch(line):
            result.extend(["", "**" + line.rstrip(":") + "**", ""])
            continue
        bullet = _BULLET.match(line)
        if bullet:
            line = bullet.group(1) + "- " + bullet.group(2)
        if _NUMBERED.match(line):
            if result and result[-1] != "":
                result.append("")
            result.append(line)
            continue
        result.append(line)
    result = "\n".join(result)
    return re.sub(r"\n{3,}", "\n\n", result).strip()


def rich_dialog_markdown(text: str) -> str:
    """Escape raw HTML but preserve valid Rich Markdown headings and lists."""
    return escape(structure_culinary_answer(text), quote=False)


async def send_dialogue(
    message: Message,
    answer: str,
    markup: InlineKeyboardMarkup | None = None,
    *,
    rich_enabled: bool = True,
) -> str:
    """Use native rich layout on substantive AI replies and HTML otherwise."""
    prepared = structure_culinary_answer(answer) or "Не удалось сформировать ответ. Попробуем ещё раз?"
    if rich_enabled and 120 <= len(prepared) <= 28000:
        try:
            await message.bot.send_rich_message(
                chat_id=message.chat.id,
                rich_message=InputRichMessage(markdown=rich_dialog_markdown(prepared)),
                reply_markup=markup,
            )
            return "rich"
        except TelegramBadRequest as exc:
            logger.info("Rich dialogue unavailable, falling back to HTML: %s", type(exc).__name__)
    chunks = telegram_chunks(prepared)
    for i, chunk in enumerate(chunks):
        await message.answer(
            chunk, parse_mode="HTML",
            reply_markup=markup if i == len(chunks) - 1 else None,
        )
    return "html"



def culinary_answer_has_recipe(text: str) -> bool:
    """Show conversion CTA only when a complete-ish recipe is actually present."""
    normal = structure_culinary_answer(text)
    ingredients = bool(re.search(r"(?im)^(?:#{1,4}\s*)?(?:🥗\s*)?(?:продукты|ингредиенты)\b", normal))
    steps = len(re.findall(r"(?m)^\d{1,2}[.)]\s+", normal))
    return ingredients and steps >= 2


def recipe_context_tag(question: str) -> str:
    """Stable short digest prevents buttons on stale answers acting on new chat."""
    return hashlib.sha256(question.encode("utf-8")).hexdigest()[:12]
