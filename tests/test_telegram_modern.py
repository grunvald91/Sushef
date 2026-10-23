"""Telegram Bot API 10.3 UX: safe rich recipes, drafts, colors and warm memory.

All tests run offline with mocks and never call Telegram/ClaudeHub.
"""
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from sushef.bot import cooking_keyboard, keyboard, recipe_keyboard
from sushef.personalization import welcome_back
from sushef.prompts import build_system
from sushef.telegram_modern import (
    recipe_rich_html, send_recipe_card, show_chef_thinking, configure_bot_commands,
)


def sample():
    return {
        "title": "Суп <с любовью> & картофель",
        "time_minutes": 30, "servings": 2,
        "chef_note": "Какая тонкая идея — **уважать** собственный вкус!",
        "ingredients": [
            {"name": "помидоры <script>", "amount": "400 г"},
            {"name": "вода", "amount": "по вкусу"},
        ],
        "steps": ["Осторожно сварить & оценить аромат.", "Проверить баланс вкуса."],
        "step_insights": [
            {"step_index": 0, "why": "Небольшой огонь бережёт аромат.",
             "cue": "Едва заметное кипение.", "fix": "Уменьшить нагрев."},
        ],
        "safety_notes": [],
    }


def test_rich_recipe_hierarchical_and_escape_safe():
    html = recipe_rich_html(sample())
    assert "<h2>🍽 Суп &lt;с любовью&gt; &amp; картофель</h2>" in html
    assert "<h3>🥗 Продукты</h3>" in html
    assert "<ul><li>" in html
    assert "<details><summary>💡 Секрет 1-го шага</summary>" in html
    assert "Небольшой огонь" in html
    assert "&lt;script&gt;" in html
    assert "<script>" not in html
    assert "<blockquote>" in html
    assert "</details>" in html
    assert html.count("<details>") == html.count("</details>")


@pytest.mark.asyncio
async def test_send_recipe_card_uses_native_rich_when_available():
    fake_bot = SimpleNamespace(send_rich_message=AsyncMock())
    fake_message = SimpleNamespace(
        bot=fake_bot, chat=SimpleNamespace(id=123, type="private"),
        answer=AsyncMock(),
    )
    markup = recipe_keyboard(sample())
    await send_recipe_card(fake_message, sample(), markup)
    fake_message.answer.assert_not_awaited()
    kwargs = fake_bot.send_rich_message.await_args.kwargs
    assert kwargs["chat_id"] == 123
    assert kwargs["reply_markup"] is markup
    assert "<h2>" in kwargs["rich_message"].html


@pytest.mark.asyncio
async def test_recipe_card_html_fallback_without_duplicate_or_unsafe_tags():
    bot = SimpleNamespace(send_rich_message=AsyncMock())
    message = SimpleNamespace(
        bot=bot, chat=SimpleNamespace(id=123, type="private"), answer=AsyncMock(),
    )
    markup = recipe_keyboard(sample())
    await send_recipe_card(message, sample(), markup, rich_enabled=False)
    bot.send_rich_message.assert_not_awaited()
    assert message.answer.await_count >= 1
    assert message.answer.await_args.kwargs["parse_mode"] == "HTML"
    assert message.answer.await_args.kwargs["reply_markup"] is markup



@pytest.mark.asyncio
async def test_rich_api_bad_request_falls_back_to_safe_html(monkeypatch):
    """Unsupported native rich method: exactly one standard Telegram fallback."""
    import sushef.telegram_modern as modern

    class UnsupportedRich(Exception):
        pass

    monkeypatch.setattr(modern, "TelegramBadRequest", UnsupportedRich)
    bot = SimpleNamespace(send_rich_message=AsyncMock(side_effect=UnsupportedRich("unsupported")))
    message = SimpleNamespace(
        bot=bot, chat=SimpleNamespace(id=222, type="private"), answer=AsyncMock())
    markup = recipe_keyboard(sample())
    await send_recipe_card(message, sample(), markup)
    assert bot.send_rich_message.await_count == 1
    assert message.answer.await_count >= 1
    rendered = message.answer.await_args.args[0]
    assert "&lt;с любовью&gt;" in rendered
    assert "<script>" not in rendered
    assert message.answer.await_args.kwargs["parse_mode"] == "HTML"



def test_short_ingredient_copy_button_not_truncated():
    kb = recipe_keyboard(sample())
    copy_button = next(
        b for row in kb.inline_keyboard for b in row if b.copy_text is not None
    )
    assert "помидоры <script>" in copy_button.copy_text.text
    assert "<= 256" not in copy_button.copy_text.text
    assert len(copy_button.copy_text.text) <= 256
    assert copy_button.callback_data is None
    long = {**sample(), "ingredients": [
        {"name": "Очень вкусная крупа " + "a" * 120, "amount": "1000 г"}
        for _ in range(5)
    ]}
    assert not any(b.copy_text is not None
                   for row in recipe_keyboard(long).inline_keyboard for b in row)


@pytest.mark.asyncio
async def test_native_draft_preview_is_only_temporary():
    fake_bot = SimpleNamespace(send_message_draft=AsyncMock(return_value=True))
    message = SimpleNamespace(
        bot=fake_bot, chat=SimpleNamespace(id=71, type="private"),
        message_id=153, message_thread_id=None,
    )
    assert await show_chef_thinking(message, enabled=True)
    fake_bot.send_message_draft.assert_awaited_once()
    kw = fake_bot.send_message_draft.await_args.kwargs
    assert kw["chat_id"] == 71
    assert kw["draft_id"] == 153
    assert kw["can_stop"] is False
    assert not await show_chef_thinking(message, enabled=False)
    fake_bot.send_message_draft.reset_mock()
    assert await show_chef_thinking(
        message, mode="recipe", preferences={"address_form": "ты"})
    assert "твой вкус" in fake_bot.send_message_draft.await_args.kwargs["text"]
    fake_bot.send_message_draft.reset_mock()
    assert await show_chef_thinking(
        message, mode="rescue", preferences={"address_form": "вы"})
    assert "помочь блюду" in fake_bot.send_message_draft.await_args.kwargs["text"]


@pytest.mark.asyncio
async def test_native_command_palette_without_botfather_overwrite():
    bot = SimpleNamespace(set_my_commands=AsyncMock())
    assert await configure_bot_commands(bot, {437862772})
    calls = bot.set_my_commands.await_args_list
    assert "language_code" not in calls[0].kwargs and "scope" not in calls[0].kwargs
    assert calls[1].kwargs["language_code"] == "ru"
    public = {cmd.command for cmd in calls[0].args[0]}
    assert {"start", "menu", "subscribe", "paysupport", "terms", "support"} <= public
    assert not {"tickets", "refund"} & public
    assert calls[2].kwargs["scope"].chat_id == 437862772
    assert {"tickets", "refund"} <= {cmd.command for cmd in calls[2].args[0]}


def test_every_menu_command_has_a_handler_and_valid_name():
    import re
    from aiogram.filters import Command, CommandStart
    from sushef import bot as bot_module, telegram_modern

    handled = set()
    for handler in bot_module.router.message.handlers:
        for flt in handler.filters or ():
            cb = flt.callback
            if isinstance(cb, CommandStart):
                handled.add("start")
            elif isinstance(cb, Command):
                handled.update(str(c) for c in cb.commands)
    listed = telegram_modern.PUBLIC_COMMANDS + telegram_modern.SUPPORT_COMMANDS
    for name, description in listed:
        assert re.fullmatch(r"[a-z0-9_]{1,32}", name) and 3 <= len(description) <= 256
        assert name in handled, name
    assert len({n for n, _ in listed}) == len(listed)


def test_main_menu_offers_subscription_purchase():
    from sushef.bot import main_keyboard
    data = [b.callback_data for row in main_keyboard().inline_keyboard for b in row]
    # Статус и оплата за одно нажатие; прямой счёт не навязывается оплатившим.
    assert "view:subscription" in data and "pay:buy" not in data


def test_highly_personal_respect_without_false_memory():
    preferred = {
        "address_form": "вы", "display_name": "Анастасия",
        "cuisines": "средиземноморская",
        "confirmed_kitchen_memory": [{"kind": "taste", "fact": "люблю лимонные нотки"}],
    }
    greeting = welcome_back(preferred)
    assert "Анастасия" in greeting and "средиземноморская" in greeting
    # Respectful address includes declined pronouns, not only the nominative.
    assert re.search(r"\b(?:Вы|Вас|Вам|Вами|Ваш\w*)\b", greeting)
    assert not re.search(r"\b(?:ты|тебя|тебе|тобой|твой|твоя|твои)\b", greeting, re.I)
    unconfirmed = welcome_back({})
    assert "средиземноморская" not in unconfirmed
    system = build_system("ask", preferred)
    assert "ИЗЫСКАННЫХ КОМПЛИМЕНТОВ" in system
    assert "подтверждённом профиле" in system
    assert "люблю лимонные нотки" in system
    assert "не выдумывай" in system.lower()



def test_bot_api_10_3_disabled_previous_step_and_force_reply():
    first = cooking_keyboard({"step_index": 0})
    assert first.inline_keyboard[0][0].disabled is not None
    assert first.inline_keyboard[0][0].callback_data is None
    later = cooking_keyboard({"step_index": 1})
    assert later.inline_keyboard[0][0].callback_data == "cook:previous"
    custom = keyboard([[("Посмотреть примеры", "hello:styles")]], force_reply=True)
    assert custom.force_reply is True


def working_message(*, sender_is_bot=False, **bot_methods):
    bot = SimpleNamespace(
        send_chat_action=AsyncMock(), set_message_reaction=AsyncMock(),
        send_message_draft=AsyncMock(return_value=True),
    )
    for name, value in bot_methods.items():
        setattr(bot, name, value)
    return SimpleNamespace(
        bot=bot, chat=SimpleNamespace(id=71, type="private"), message_id=153,
        message_thread_id=None, from_user=SimpleNamespace(id=5, is_bot=sender_is_bot),
    )


@pytest.mark.asyncio
async def test_working_indicator_shows_all_three_signals_and_cleans_up():
    import asyncio
    from sushef.telegram_modern import ChefWorking

    message = working_message()
    working = ChefWorking(message, mode="recipe", typing_interval=0.01)
    await working.start()
    await asyncio.sleep(0.08)
    # «печатает…» повторяется, пока ИИ не ответил, а не один раз
    assert message.bot.send_chat_action.await_count >= 3
    reaction = message.bot.set_message_reaction.await_args.kwargs
    assert reaction["chat_id"] == 71 and reaction["message_id"] == 153
    assert reaction["reaction"][0].emoji == "👀"
    assert message.bot.send_message_draft.await_args.kwargs["draft_id"] == 153
    await working.stop()
    # реакция снята, «печатает…» больше не обновляется
    assert message.bot.set_message_reaction.await_args.kwargs["reaction"] == []
    calls = message.bot.send_chat_action.await_count
    await asyncio.sleep(0.05)
    assert message.bot.send_chat_action.await_count == calls


@pytest.mark.asyncio
async def test_working_indicator_does_not_react_to_bots_own_message_or_when_disabled():
    from sushef.telegram_modern import ChefWorking

    own = working_message(sender_is_bot=True)
    working = ChefWorking(own, typing_interval=0.01)
    await working.start()
    await working.stop()
    own.bot.set_message_reaction.assert_not_awaited()
    own.bot.send_message_draft.assert_awaited()  # «думаю…» всё равно показан

    off = working_message()
    working = ChefWorking(off, draft_enabled=False, reaction_enabled=False, typing_interval=0.01)
    await working.start()
    await working.stop()
    off.bot.set_message_reaction.assert_not_awaited()
    off.bot.send_message_draft.assert_not_awaited()
    off.bot.send_chat_action.assert_awaited()


@pytest.mark.asyncio
async def test_working_indicator_failures_never_break_the_answer():
    from sushef.telegram_modern import ChefWorking

    boom = AsyncMock(side_effect=RuntimeError("telegram is down"))
    message = working_message(send_chat_action=boom, set_message_reaction=boom,
                              send_message_draft=boom)
    working = ChefWorking(message, typing_interval=0.01)
    await working.start()   # не бросает
    await working.stop()    # не бросает


def test_default_model_is_haiku_and_seen_reaction_is_on():
    from sushef.config import Settings

    settings = Settings(telegram_bot_token="1234567890:token", claudehub_api_key="12345678",
                        _env_file=None)
    assert settings.claudehub_model == "claude-haiku-5-5"
    assert settings.telegram_seen_reaction is True
