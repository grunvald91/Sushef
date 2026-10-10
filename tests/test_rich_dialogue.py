"""Regression for the actual user-reported salmon answer in ordinary AI chat."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from sushef.bot import text_message
from sushef.telegram_dialogue import (
    rich_dialog_markdown, send_dialogue, structure_culinary_answer,
)


FISH_ANSWER = (
    "Здравствуйте, очень приятно познакомиться! Горбуша в духовке - прекрасный выбор.\n"
    "На 2-3 порции:\n"
    "Продукты:\n"
    "• Горбуша - 500-700 г\n"
    "• Лимон - 1 шт\n"
    "Как готовить:\n"
    "1. Подготовка рыбы. Нарежьте и обсушите. Оставьте на 15 минут."
    "2. Овощная подушка. Разложите овощи.\n"
    "3. Первое запекание. Готовьте картофель.\n"
    "4. Выкладываем рыбу. Добавьте лимон.\n"
    "5. Запекание рыбы. Проверьте готовность.\n"
    "6. Брокколи. Прогрейте отдельно.\n"
    "Пара хитростей, чтобы горбуша не была сухой:\n"
    "• Не передержите рыбу.\n"
    "* Если хотите корочку, выберите иной режим."
)


def test_production_fish_answer_is_structured_not_dense_wall():
    output = structure_culinary_answer(FISH_ANSWER)
    assert "## 🥗 Продукты" in output
    assert "## 👨‍🍳 Как приготовить" in output
    assert "## 💡 Секреты и советы" in output
    assert "**На 2-3 порции**" in output
    assert "\n\n2. Овощная подушка" in output
    assert "\n\n3. Первое запекание" in output
    assert "\n- Горбуша - 500-700 г" in output
    assert "\n- Если хотите корочку" in output
    assert "500-700 г" in output and "15 минут" in output
    assert output.count("2. Овощная") == 1


def test_escape_model_html_but_preserve_native_rich_markdown():
    markup = rich_dialog_markdown(
        "Продукты:\n• Рыба <script> & лимон\n"
        "Как готовить:\n1. Добавьте **немного масла**."
    )
    assert "## 🥗 Продукты" in markup
    assert "&lt;script&gt;" in markup and "<script>" not in markup
    assert "&amp;" in markup
    assert "**немного масла**" in markup


@pytest.mark.asyncio
async def test_regular_chat_uses_native_rich_message_not_old_plain_path():
    bot = SimpleNamespace(send_rich_message=AsyncMock())
    message = SimpleNamespace(
        bot=bot, chat=SimpleNamespace(id=456, type="private"),
        answer=AsyncMock(),
    )
    markup = object()
    result = await send_dialogue(message, FISH_ANSWER, markup)
    assert result == "rich"
    bot.send_rich_message.assert_awaited_once()
    call = bot.send_rich_message.await_args.kwargs
    assert call["reply_markup"] is markup
    assert call["chat_id"] == 456
    assert "## 👨‍🍳 Как приготовить" in call["rich_message"].markdown
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_unsupported_rich_falls_back_to_readable_html(monkeypatch):
    import sushef.telegram_dialogue as dialogue

    class RichUnsupported(Exception):
        pass

    monkeypatch.setattr(dialogue, "TelegramBadRequest", RichUnsupported)
    bot = SimpleNamespace(send_rich_message=AsyncMock(side_effect=RichUnsupported("invalid")))
    message = SimpleNamespace(
        bot=bot, chat=SimpleNamespace(id=456, type="private"),
        answer=AsyncMock(),
    )
    markup = object()
    result = await send_dialogue(message, FISH_ANSWER, markup)
    assert result == "html"
    bot.send_rich_message.assert_awaited_once()
    assert message.answer.await_count >= 1
    joined = "\n".join(c.args[0] for c in message.answer.await_args_list)
    assert "<b>👨‍🍳 Как приготовить</b>" in joined
    assert "2. Овощная подушка" in joined
    assert "**" not in joined
    assert message.answer.await_args.kwargs["reply_markup"] is markup


@pytest.mark.asyncio
async def test_ambiguous_rich_network_errors_never_auto_resend():
    bot = SimpleNamespace(send_rich_message=AsyncMock(side_effect=TimeoutError("unknown outcome")))
    message = SimpleNamespace(
        bot=bot, chat=SimpleNamespace(id=456, type="private"),
        answer=AsyncMock(),
    )
    with pytest.raises(TimeoutError):
        await send_dialogue(message, FISH_ANSWER)
    message.answer.assert_not_awaited()


@pytest.mark.asyncio
async def test_ai_question_in_ordinary_ask_mode_really_calls_rich_dialogue():
    bot = SimpleNamespace(
        send_chat_action=AsyncMock(), send_rich_message=AsyncMock(),
    )
    message = SimpleNamespace(
        text="У меня горбуша и овощи. Как вкусно запечь кусочками?",
        chat=SimpleNamespace(id=89, type="private"),
        from_user=SimpleNamespace(id=89),
        message_id=100,
        answer=AsyncMock(), bot=bot,
    )
    storage = SimpleNamespace(
        get_user=AsyncMock(return_value={
            "mode": "ask", "preferences": {"likes": "лимон", "address_form": "вы"},
        }),
        recent_feedback=AsyncMock(return_value=[]),
        feedback_patterns=AsyncMock(return_value={"repeated_issues": []}),
        personal_memories=AsyncMock(return_value=[]),
        get_history=AsyncMock(return_value=[]),
        technique_matches=AsyncMock(return_value=[]),
        use_quota=AsyncMock(return_value=True),
        add_exchange=AsyncMock(),
    )
    chef = SimpleNamespace(answer=AsyncMock(return_value=FISH_ANSWER))
    settings = SimpleNamespace(
        max_input_chars=3500, daily_ai_limit=25,
        telegram_draft_preview=False, telegram_rich_recipe_cards=True,
    )
    await text_message(message, storage, chef, settings)
    chef.answer.assert_awaited_once()
    bot.send_rich_message.assert_awaited_once()
    assert "Горбуша" in bot.send_rich_message.await_args.kwargs["rich_message"].markdown
    storage.add_exchange.assert_awaited_once()
