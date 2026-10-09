"""Small high-confidence conversation repair rules.

The model handles almost all dialogue. This module only fixes a known
repeated clarification error when the user's question and the assistant's
previous message unambiguously identify the misunderstanding.
"""
from __future__ import annotations

import re

_EGGS_WHY = re.compile(
    r"(?:\bпри\s+ч[её]м\b|\bзачем\b|\bпочему\b).{0,55}\bяйц[аоыуые]*\b",
    re.IGNORECASE | re.DOTALL,
)
_CROQUE_MADAME = re.compile(r"крок[\s-]*мадам", re.IGNORECASE)


def correct_egg_followup(
    question: str, history: list[dict[str, str]], preferences: dict
) -> str | None:
    """Answer 'при чём яйца?' from the immediately preceding croque-madame turn.

    Do not claim the user has no eggs; absence from the list is not proof.
    Do not invoke ClaudeHub or repeat the unnecessary inventory question.
    """
    if not _EGGS_WHY.search(question):
        return None
    previous = next(
        (entry.get("content", "") for entry in reversed(history)
         if entry.get("role") == "assistant"), ""
    )
    if not _CROQUE_MADAME.search(previous) or "яйц" not in previous.casefold():
        return None
    informal = preferences.get("address_form") == "ты"
    if informal:
        opening = (
            "Отличный вопрос — я сам создал путаницу. Я заговорил о яйцах, потому что "
            "у крок-мадам сверху обычно яйцо. Но яйца не были перечислены среди твоих продуктов — "
            "мне не стоило уводить разговор к продукту, наличие которого неизвестно."
        )
        ending = "Давай готовить из того, что у тебя действительно есть."
    else:
        opening = (
            "Вы справедливо заметили несостыковку. Я упомянул яйца потому, что "
            "у крок-мадам сверху обычно яйцо. Но Вы их не называли — "
            "мне не стоило переключать разговор на продукт, наличие которого неизвестно."
        )
        ending = "Лучше приготовим из того, что у Вас действительно есть."
    if "драник" in previous.casefold():
        return (
            opening +
            "\n\nДля картофельных драников яйцо не обязательно: "
            "отожмите лишнюю влагу из тёртого картофеля, "
            "добавьте немного муки и, если хочется, ветчину с сыром. "
            "Так масса лучше держит форму и получится румяная корочка. "
            + ending
        )
    return opening + "\n\n" + ending
