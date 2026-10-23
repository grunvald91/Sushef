"""Markdown ответа → нативные блоки Rich Message (Bot API 10.3).

Используется, когда в ответе есть то, что Rich Markdown не гарантирует:
таблицы и списки с галочками. Весь текст передаётся как данные (RichText),
поэтому HTML/Markdown модели не интерпретируется.
"""
from __future__ import annotations

import re

from aiogram.types import (
    InputRichBlockButtons, InputRichBlockDetails, InputRichBlockDivider,
    InputRichBlockExpandableBlockQuotation, InputRichBlockList, InputRichBlockListItem,
    InputRichBlockParagraph, InputRichBlockPreformatted, InputRichBlockSectionHeading,
    InputRichBlockTable, RichBlockTableCell, RichMessageButton, RichTextBold, RichTextCode,
)

from .telegram_format import table_rows

_INLINE = re.compile(r"\*\*([^*\n]+)\*\*|`([^`\n]+)`")
_HEADING = re.compile(r"^(#{1,4})\s+(.+)$")
_BULLET = re.compile(r"^[-•*]\s+(.+)$")
_CHECK = re.compile(r"^[-*]\s+\[( |x|X)\]\s+(.+)$")
_ORDERED = re.compile(r"^(\d{1,2})[.)]\s+(.+)$")
_ROW = re.compile(r"^\s*\|.*\|\s*$")
_RULE = re.compile(r"^\s*-{3,}\s*$")
_QUOTE = re.compile(r"^>\s?(.*)$")
# Разделы с советами сворачиваются под заголовок: ответ короче, подробности по нажатию.
_TIPS = re.compile(r"^(?:#{1,4}\s*)(?:💡\s*)?(?:тонкости|секреты|хитрости|советы)\b", re.IGNORECASE)

MAX_BLOCKS = 120


def rich_text(text: str):
    """**жирный** и `код` (копируется нажатием) как типизированные фрагменты."""
    parts, pos = [], 0
    for match in _INLINE.finditer(text):
        if match.start() > pos:
            parts.append(text[pos:match.start()])
        if match.group(1) is not None:
            parts.append(RichTextBold(text=match.group(1)))
        else:
            parts.append(RichTextCode(text=match.group(2)))
        pos = match.end()
    if pos < len(text):
        parts.append(text[pos:])
    if not parts:
        return ""
    return parts[0] if len(parts) == 1 else parts


def table_block(rows: list[list[str]]) -> InputRichBlockTable:
    return InputRichBlockTable(
        cells=[[RichBlockTableCell(align="left", valign="middle", text=rich_text(cell),
                                   is_header=(r == 0) or None)
                for cell in row] for r, row in enumerate(rows)],
        is_bordered=True, is_striped=True, is_compact=True,
    )


def checklist_block(items: list[str]) -> InputRichBlockList:
    return InputRichBlockList(items=[
        InputRichBlockListItem(blocks=[InputRichBlockParagraph(text=rich_text(item))],
                               has_checkbox=True, is_checked=False)
        for item in items
    ])


def buttons_block(buttons: list[tuple[str, str, str | None]]) -> InputRichBlockButtons:
    """Кнопки внутри самого сообщения: (текст, callback_data, стиль)."""
    return InputRichBlockButtons(buttons=[
        RichMessageButton(text=text, callback_data=data, style=style) for text, data, style in buttons
    ])


def needs_blocks(markdown: str) -> bool:
    lines = markdown.split("\n")
    has_table = any(_ROW.match(lines[i]) and table_rows(lines[i:i + 2])
                    for i in range(len(lines) - 1))
    return has_table or any(
        _CHECK.match(line.strip()) or _QUOTE.match(line.strip()) or _TIPS.match(line.strip())
        for line in lines
    )


def markdown_to_blocks(markdown: str) -> list:
    lines = markdown.replace("\r\n", "\n").split("\n")
    blocks: list = []
    target = blocks  # сюда попадают новые блоки: корень или раскрывающийся раздел
    details: dict = {}
    paragraph: list[str] = []
    quote: list[str] = []
    items: list[tuple[str, str, int | None]] = []  # kind, text, number

    def flush_paragraph() -> None:
        if paragraph:
            target.append(InputRichBlockParagraph(text=rich_text(" ".join(paragraph))))
            paragraph.clear()

    def flush_quote() -> None:
        if quote:
            target.append(InputRichBlockExpandableBlockQuotation(text=rich_text(" ".join(quote))))
            quote.clear()

    def close_details() -> None:
        nonlocal target
        if details:
            blocks.append(InputRichBlockDetails(
                summary=details["summary"], blocks=details["blocks"] or [InputRichBlockParagraph(text=" ")],
                is_open=False))
            details.clear()
        target = blocks

    def flush_items() -> None:
        if not items:
            return
        list_items = []
        for kind, text, number in items:
            extra = ({"has_checkbox": True, "is_checked": number == 1} if kind == "check" else
                     {"type": "1", "value": number} if kind == "ordered" else {})
            list_items.append(InputRichBlockListItem(
                blocks=[InputRichBlockParagraph(text=rich_text(text))], **extra))
        target.append(InputRichBlockList(items=list_items))
        items.clear()

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("```"):
            flush_paragraph(); flush_items(); flush_quote()
            j = i + 1
            while j < len(lines) and not lines[j].strip().startswith("```"):
                j += 1
            target.append(InputRichBlockPreformatted(text="\n".join(lines[i + 1:j]) or " "))
            i = j + 1
            continue
        if _ROW.match(line):
            j = i
            while j < len(lines) and (_ROW.match(lines[j]) or
                                      (j == i + 1 and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[j]))):
                j += 1
            rows = table_rows(lines[i:j])
            if rows:
                flush_paragraph(); flush_items(); flush_quote()
                target.append(table_block(rows))
                i = j
                continue
        if not line:
            flush_paragraph(); flush_items(); flush_quote()
        elif heading := _HEADING.match(line):
            flush_paragraph(); flush_items(); flush_quote(); close_details()
            title = rich_text(heading.group(2).strip("* "))
            if _TIPS.match(line):
                details.update(summary=title, blocks=[])
                target = details["blocks"]
            else:
                target.append(InputRichBlockSectionHeading(
                    text=title, size=min(len(heading.group(1)) + 1, 4)))
        elif _RULE.match(line):
            flush_paragraph(); flush_items(); flush_quote()
            target.append(InputRichBlockDivider())
        elif quoted := _QUOTE.match(line):
            flush_paragraph(); flush_items()
            quote.append(quoted.group(1).strip())
        elif check := _CHECK.match(line):
            flush_paragraph(); flush_quote()
            items.append(("check", check.group(2), 1 if check.group(1) in "xX" else 0))
        elif ordered := _ORDERED.match(line):
            flush_paragraph(); flush_quote()
            if items and items[-1][0] != "ordered":
                flush_items()
            items.append(("ordered", ordered.group(2), int(ordered.group(1))))
        elif bullet := _BULLET.match(line):
            flush_paragraph(); flush_quote()
            if items and items[-1][0] != "bullet":
                flush_items()
            items.append(("bullet", bullet.group(1), None))
        else:
            flush_items(); flush_quote()
            if details and not paragraph and any(
                    isinstance(block, InputRichBlockList) for block in details["blocks"]):
                close_details()  # заключительная фраза после списка советов остаётся на виду
            paragraph.append(line)
        i += 1
    flush_paragraph(); flush_items(); flush_quote(); close_details()
    if len(blocks) > MAX_BLOCKS:
        raise ValueError("слишком много блоков для одного сообщения")
    return blocks
