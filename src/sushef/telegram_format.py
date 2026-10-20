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
_INLINE_NUMBERED_BOLD = re.compile(r"(?<!^)(?<!\n)(?=\*\*\d{1,2}\.\s)")


_FENCE = re.compile(r"```[a-zA-Z0-9_-]*\n?(.*?)```", re.DOTALL)
_INLINE_CODE = re.compile(r"`([^`\n]{1,500})`")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def table_rows(lines: list[str]) -> list[list[str]] | None:
    """Ячейки Markdown-таблицы `| a | b |` (строка-разделитель отбрасывается)."""
    if len(lines) < 2 or not _TABLE_RULE.match(lines[1]):
        return None
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")]
            for i, line in enumerate(lines) if i != 1]
    return rows if rows and all(len(r) == len(rows[0]) for r in rows) else None


def plain_table(rows: list[list[str]]) -> str:
    """Таблица для обычного Telegram HTML: выровненный моноширинный текст."""
    clean = [[cell.replace("**", "") for cell in row] for row in rows]
    widths = [max(len(row[i]) for row in clean) for i in range(len(clean[0]))]
    lines = [" │ ".join(cell.ljust(widths[i]) for i, cell in enumerate(row)).rstrip()
             for row in clean]
    lines.insert(1, "─┼─".join("─" * w for w in widths))
    return "\n".join(lines)


def _tables_to_fences(text: str) -> str:
    lines, out, i = text.split("\n"), [], 0
    while i < len(lines):
        if _TABLE_ROW.match(lines[i]):
            j = i
            while j < len(lines) and _TABLE_ROW.match(lines[j]) or (
                    j == i + 1 and j < len(lines) and _TABLE_RULE.match(lines[j])):
                j += 1
            rows = table_rows(lines[i:j])
            if rows:
                out.extend(["```", plain_table(rows), "```"])
                i = j
                continue
        out.append(lines[i])
        i += 1
    return "\n".join(out)


def telegram_html(text: str) -> str:
    """Escape arbitrary text; convert **bold**, *italics*, headings, bullets and code.

    `код` и ```блоки``` становятся <code>/<pre>: в Telegram такой текст
    копируется одним нажатием. Таблицы Markdown выводятся моноширинным блоком.
    Deliberately not a full Markdown parser: never trust user/model HTML.
    """
    code: list[str] = []

    def keep(html: str) -> str:
        code.append(html)
        return f"\x00{len(code) - 1}\x00"

    safe = escape(_tables_to_fences(text), quote=False)
    safe = _FENCE.sub(lambda m: keep("<pre>" + m.group(1).strip("\n") + "</pre>"), safe)
    safe = _INLINE_CODE.sub(lambda m: keep("<code>" + m.group(1) + "</code>"), safe)
    safe = _HEADERS.sub(r"<b>\1</b>", safe)
    safe = _BULLETS.sub("• ", safe)
    safe = _BOLD.sub(r"<b>\1</b>", safe)
    safe = _ITALIC.sub(r"<i>\1</i>", safe)
    return re.sub("\x00(\\d+)\x00", lambda m: code[int(m.group(1))], safe)


def telegram_chunks(text: str, limit: int = CHUNK_SIZE) -> list[str]:
    """Split raw text on readable boundaries; no generated HTML spans messages."""
    if limit < 60:
        raise ValueError("Минимальная длина части — 60 символов")
    remaining = text.strip()
    # Models sometimes concatenate finished sentences or numbered alternatives
    # without a space/line break. Restore readability before splitting.
    remaining = _RUN_ON_SENTENCES.sub(r"\1 ", remaining)
    remaining = _INLINE_NUMBERED_BOLD.sub("\n\n", remaining)
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
