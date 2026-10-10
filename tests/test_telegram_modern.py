"""Telegram Bot API 10.3 UX: safe rich recipes, drafts, colors and warm memory.

All tests run offline with mocks and never call Telegram/ClaudeHub.
"""
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
    assert await configure_bot_commands(bot)
    kwargs = bot.set_my_commands.await_args.kwargs
    commands = {cmd.command for cmd in bot.set_my_commands.await_args.args[0]}
    assert kwargs["language_code"] == "ru"
    assert {"start", "menu", "profile", "memory", "recipes"} <= commands


def test_highly_personal_respect_without_false_memory():
    preferred = {
        "address_form": "вы", "display_name": "Анастасия",
        "cuisines": "средиземноморская",
        "confirmed_kitchen_memory": [{"kind": "taste", "fact": "люблю лимонные нотки"}],
    }
    greeting = welcome_back(preferred)
    assert "Анастасия" in greeting and "средиземноморская" in greeting
    assert "Вы" in greeting
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
