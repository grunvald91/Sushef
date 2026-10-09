"""Safe Telegram HTML for both model text and bot UI copy.

All user/model content is escaped *before* converting a small supported
Markdown subset. Formatting is applied separately to each <=3000-char chunk,
so a message never splits an HTML tag across Telegram API calls.
"""
from __future__ import annotations

from html import escape
import re

CHUNK_SIZE = 3000

_BOLD = re.compile(r"\*\*([^\n*][^\n]*?)\*\*")
_ITALIC = re.compile(r"(?<!\*)\*([^\n*]+?)\*(?!\*)")
_HEADERS = re.compile(r"(?m)^[ \t]{0,3}#{1,4}[ \t]+(.+?)$")
_BULLETS = re.compile(r"(?m)^[ \t]*[*-][ \t]+")
_RUN_ON_SENTENCES = re.compile(r"([.!?])(?=[А-ЯЁ])")
_INLINE_NUMBERED_BOLD = re.compile(r"(?<=[^\\n])(?=\\*\\*\\d{1,2}\\.\\s)")


def telegram_html(text: str) -> str:
    """Escape arbitrary text; convert **bold**, *italics*, headings, and bullets.

    Deliberately not a full Markdown parser: never trust user/model HTML.
    """
    safe = escape(text, quote=False)
    safe = _HEADERS.sub(r"<b>\1</b>", safe)
    safe = _BULLETS.sub("• ", safe)
    safe = _BOLD.sub(r"<b>\1</b>", safe)
    safe = _ITALIC.sub(r"<i>\1</i>", safe)
    return safe


def telegram_chunks(text: str, limit: int = CHUNK_SIZE) -> list[str]:
    """Split raw text on readable boundaries; no generated HTML spans messages."""
    if limit < 60:
        raise ValueError("Минимальная длина части — 60 символов")
    remaining = text.strip()
    # Models sometimes concatenate finished sentences or numbered alternatives
    # without a space/line break. Restore readability before splitting.
    remaining = _RUN_ON_SENTENCES.sub(r"\\1 ", remaining)
    remaining = _INLINE_NUMBERED_BOLD.sub("\\n\\n", remaining)
    if not remaining:
        return ["(пустой ответ)"]
    result = []
    while len(remaining) > limit:
        # Prefer natural boundaries without dropping characters.
        window = remaining[:limit]
        split = window.rfind("\n\n")
        if split < limit // 3:
            split = window.rfind("\n")
        if split < limit // 3:
            split = window.rfind(" ")
        if split < limit // 3:
            split = limit
        result.append(remaining[:split].rstrip())
        remaining = remaining[split:].lstrip("\n ")
    if remaining:
        result.append(remaining)
    return [telegram_html(part) for part in result]
