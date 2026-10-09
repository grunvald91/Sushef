"""Regression tests for the exact reported Telegram conversation-quality failure."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from sushef.bot import send_text, text_message
from sushef.conversation_quality import correct_egg_followup
from sushef.personalization import communication_instructions
from sushef.prompts import build_system
from sushef.telegram_format import telegram_chunks, telegram_html


REPORTED_BOT_REPLY = (
    "Доброе утро! Отличный набор, из него получится замечательный завтрак."
    "**1. Крок-мадам** - французский горячий бутерброд с ветчиной, сыром "
    "и яйцом сверху. Если бы у Вас были яйца - это был бы мой первый выбор."
    "**2. Картофельные драники с ветчиной и сыром** - яйца не нужны."
    "Яйца в холодильнике найдутся?"
)


def test_reported_formatting_becomes_readable_telegram_html():
    rendered = telegram_html(REPORTED_BOT_REPLY)
    assert "<b>1. Крок-мадам</b>" in rendered
    assert "<b>2. Картофельные драники с ветчиной и сыром</b>" in rendered
    assert "**" not in rendered
    readable = telegram_chunks(REPORTED_BOT_REPLY)[0]
    assert "\n\n<b>1. Крок-мадам</b>" in readable
    assert "\n\n<b>2. Картофельные драники с ветчиной и сыром</b>" in readable
    assert telegram_chunks("Вкусно.Предложу два варианта.")[0] == "Вкусно. Предложу два варианта."


def test_html_escapes_untrusted_model_and_user_markup():
    raw = "<script>hello</script> & **полезный совет**\n* делайте спокойно"
    result = telegram_html(raw)
    assert "&lt;script&gt;" in result
    assert "<script>" not in result
    assert "&amp;" in result
    assert "<b>полезный совет</b>" in result
    assert "\n• делайте спокойно" in result


def test_long_response_has_separately_valid_balanced_html_chunks():
    answer = ("**Почему так?**\n" + "Хороший приём для овощей. " * 170 + "\n\n") * 4
    chunks = telegram_chunks(answer)
    assert len(chunks) >= 2
    assert all(len(part) <= 4096 for part in chunks)
    for part in chunks:
        assert part.count("<b>") == part.count("</b>")
        assert part.count("<i>") == part.count("</i>")


@pytest.mark.asyncio
async def test_telegram_send_uses_html_and_keeps_keyboard_on_last_chunk():
    message = SimpleNamespace(answer=AsyncMock())
    markup = object()
    await send_text(message, REPORTED_BOT_REPLY, markup)
    message.answer.assert_awaited_once()
    args, kwargs = message.answer.call_args
    assert "<b>1. Крок-мадам</b>" in args[0]
    assert kwargs["parse_mode"] == "HTML"
    assert kwargs["reply_markup"] is markup

    message.answer.reset_mock()
    await send_text(message, "Очень полезный совет.\n\n" * 400, markup)
    calls = message.answer.await_args_list
    assert len(calls) > 1
    assert all(call.kwargs["parse_mode"] == "HTML" for call in calls)
    assert all(call.kwargs["reply_markup"] is None for call in calls[:-1])
    assert calls[-1].kwargs["reply_markup"] is markup


def test_egg_followup_is_answered_directly_without_repeat_question():
    history = [
        {"role": "user", "content": "Есть картофель, ветчина, сыр, сметана. Что на завтрак?"},
        {"role": "assistant", "content": REPORTED_BOT_REPLY},
    ]
    result = correct_egg_followup(
        "А при чём здесь яйца?", history, {"address_form": "вы"}
    )
    assert result is not None
    assert "крок-мадам" in result
    assert "сверху обычно яйцо" in result
    assert "картофельных драников яйцо не обязательно" in result
    assert "не стоило" in result
    assert "Яйца в холодильнике найдутся" not in result


def test_gender_neutral_informal_and_no_context_no_invention():
    history = [{"role": "assistant", "content": REPORTED_BOT_REPLY}]
    result = correct_egg_followup(
        "Зачем тут яйца?", history, {"address_form": "ты"}
    )
    assert result and "не стоило отвлекать тебя" in result
    assert correct_egg_followup("При чём здесь яйца?", [], {}) is None
    assert correct_egg_followup(
        "При чём здесь яйца?",
        [{"role": "assistant", "content": "В яйца добавьте сахар."}],
        {}
    ) is None
    assert correct_egg_followup("Хочу яйца на завтрак", history, {}) is None


def test_prompt_prioritizes_direct_answers_and_doesnt_assume_ingredients():
    system = build_system("ask", {"display_name": "Лада", "address_form": "вы"})
    assert "ПОСЛЕДНЕМ сообщении" in system
    assert "НЕ значит «точно нет»" in system
    assert "не задавай уже заданный вопрос" in system
    assert "крок-мадам" not in system or "при чём" in system
    assert "Лада" in system
    assert "Манера общения" in system
    assert "душевн" in communication_instructions({})


@pytest.mark.asyncio
async def test_telegram_handler_answers_egg_question_without_charging_ai_quota():
    previous = [
        {"role": "user", "content": "Есть картошка, ветчина, сыр, сметана. Что приготовить?"},
        {"role": "assistant", "content": REPORTED_BOT_REPLY},
    ]
    storage = SimpleNamespace(
        get_user=AsyncMock(return_value={"mode": "ask", "preferences": {"address_form": "вы"}}),
        recent_feedback=AsyncMock(return_value=[]),
        feedback_patterns=AsyncMock(return_value={"repeated_issues": []}),
        personal_memories=AsyncMock(return_value=[]),
        get_history=AsyncMock(return_value=previous),
        add_exchange=AsyncMock(),
        use_quota=AsyncMock(side_effect=AssertionError("Direct repair must not call ClaudeHub")),
    )
    message = SimpleNamespace(
        text="А при чём здесь яйца?",
        from_user=SimpleNamespace(id=71),
        chat=SimpleNamespace(id=71, type="private"),
        answer=AsyncMock(),
    )
    settings = SimpleNamespace(max_input_chars=3500, daily_ai_limit=25)
    await text_message(message, storage, object(), settings)
    storage.use_quota.assert_not_awaited()
    storage.add_exchange.assert_awaited_once()
    answer_sent = message.answer.await_args.args[0]
    assert "крок-мадам" in answer_sent
    assert "картофельных драников" in answer_sent
    assert "Яйца в холодильнике найдутся?" not in answer_sent
    assert message.answer.await_args.kwargs["parse_mode"] == "HTML"
