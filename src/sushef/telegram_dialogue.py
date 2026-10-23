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

from .rich_blocks import buttons_block, markdown_to_blocks, needs_blocks
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
    inline_buttons: list[tuple[str, str, str | None]] | None = None,
    rich_markup: InlineKeyboardMarkup | None = None,
) -> str:
    """Use native rich layout on substantive AI replies and HTML otherwise.

    inline_buttons — кнопки внутри самого rich-сообщения (перед разделом советов).
    Если они реально вошли в сообщение, под ним показывается rich_markup (короче
    основной клавиатуры); в остальных случаях — полная клавиатура markup.
    """
    prepared = structure_culinary_answer(answer) or "Не удалось сформировать ответ. Попробуем ещё раз?"
    if rich_enabled and 120 <= len(prepared) <= 28000:
        try:
            # Таблицы, галочки, раскрывающиеся советы и цитаты — нативными блоками.
            rich = None
            under_markup = markup
            if inline_buttons or needs_blocks(prepared):
                try:
                    blocks = markdown_to_blocks(prepared)
                    if inline_buttons:
                        at = next((n for n, block in enumerate(blocks)
                                   if type(block).__name__ == "InputRichBlockDetails"), len(blocks))
                        blocks.insert(at, buttons_block(inline_buttons))
                        if rich_markup is not None:
                            under_markup = rich_markup
                    rich = InputRichMessage(blocks=blocks)
                except ValueError:
                    rich = None
                    under_markup = markup
            if rich is None:
                rich = InputRichMessage(markdown=rich_dialog_markdown(prepared))
            await message.bot.send_rich_message(
                chat_id=message.chat.id, rich_message=rich, reply_markup=under_markup,
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


_INGREDIENTS_HEADING = re.compile(r"^#{1,4}\s*(?:🥗\s*)?(?:продукты|ингредиенты)\b", re.IGNORECASE)


def dialogue_shopping_items(answer: str) -> list[str]:
    """Строки раздела «Продукты» из ответа шефа, без выдумывания и пересчёта."""
    items: list[str] = []
    inside = False
    for line in structure_culinary_answer(answer).split("\n"):
        line = line.strip()
        if line.startswith("#"):
            inside = bool(_INGREDIENTS_HEADING.match(line))
            continue
        if inside and line.startswith("- "):
            text = re.sub(r"^-\s*(?:\[[ xX]\]\s*)?", "", line).replace("**", "").strip()
            if text:
                items.append(text)
    return items[:40]


def recipe_context_tag(question: str) -> str:
    """Stable short digest prevents buttons on stale answers acting on new chat."""
    return hashlib.sha256(question.encode("utf-8")).hexdigest()[:12]


class GenerationStopped(Exception):
    """Пользователь нажал «стоп» на черновике (Update.stopped_message_generation)."""

    def __init__(self, partial: str):
        super().__init__("generation stopped by user")
        self.partial = partial


ACTIVE_STREAMS: dict[tuple[int, int], "DraftStreamer"] = {}


def stop_stream(chat_id: int, draft_id: int) -> bool:
    streamer = ACTIVE_STREAMS.get((chat_id, draft_id))
    if streamer is None:
        return False
    streamer.stopped = True
    return True


class DraftStreamer:
    """Показывает ответ ClaudeHub по мере генерации (sendRichMessageDraft, Bot API 10.3).

    Черновик временный: итоговый ответ всегда отправляется обычным сообщением.
    Любая ошибка черновика отключает его до конца ответа и не ломает генерацию.
    """

    def __init__(self, message: Message, *, interval: float = 1.2, clock=None):
        import time
        self.message = message
        self.interval = interval
        self.clock = clock or time.monotonic
        self.last = float("-inf")
        self.enabled = message.chat.type == "private" and type(getattr(message, "message_id", None)) is int
        self.sent = 0
        self.stopped = False

    def __enter__(self) -> "DraftStreamer":
        if self.enabled:
            ACTIVE_STREAMS[(self.message.chat.id, self.message.message_id)] = self
        return self

    def __exit__(self, *exc) -> None:
        ACTIVE_STREAMS.pop((self.message.chat.id, getattr(self.message, "message_id", 0)), None)

    async def __call__(self, partial: str) -> None:
        if self.stopped:
            raise GenerationStopped(partial)
        if not self.enabled or len(partial) < 40:
            return
        now = self.clock()
        if now - self.last < self.interval:
            return
        self.last = now
        try:
            await self.message.bot.send_rich_message_draft(
                chat_id=self.message.chat.id,
                draft_id=self.message.message_id,
                rich_message=InputRichMessage(
                    markdown=rich_dialog_markdown(structure_culinary_answer(partial[-6000:]))),
                can_stop=True,  # кнопка «стоп» → Update.stopped_message_generation
            )
            self.sent += 1
        except Exception as exc:  # черновик — украшение, не причина сбоя ответа
            # warning: иначе в проде не видно, что поток ответа не доходит до людей
            logger.warning("Streaming draft disabled: %s: %s", type(exc).__name__, exc)
            self.enabled = False
