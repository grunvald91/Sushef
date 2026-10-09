"""Персонализация без внешних AI-вызовов и изменения схемы."""
import pytest

from sushef.bot import communication_keyboard, profile_keyboard, style_keyboard, welcome_keyboard
from sushef.memory import validate_preference
from sushef.personalization import (
    STYLE_LABELS, communication_instructions, communication_summary,
    example, style_comparison, welcome_back,
)
from sushef.prompts import build_system
from sushef.storage import Storage


def callback_set(markup):
    return {button.callback_data for row in markup.inline_keyboard for button in row}


def test_onboarding_controls_and_full_style_previews():
    prefs = {"display_name": "Анна", "address_form": "ты"}
    text = style_comparison(prefs)
    assert "твой Сушеф" in text
    for style, title in STYLE_LABELS.items():
        assert title in text
        assert example(style, prefs) in text
        assert f"hello:style:{style}" in callback_set(style_keyboard())
    assert "hello:start" in callback_set(welcome_keyboard())
    assert "hello:skip" in callback_set(welcome_keyboard())
    assert "view:communication" in callback_set(profile_keyboard())
    assert "hello:styles" in callback_set(communication_keyboard())
    for markup in [style_keyboard(), communication_keyboard(), welcome_keyboard()]:
        assert all(len(value.encode("utf-8")) <= 64 for value in callback_set(markup))


def test_personalized_voice_has_respectful_fallback_and_no_invented_history():
    info = {"display_name": "Анна", "address_form": "ты", "conversation_style": "warm"}
    system = build_system("ask", info)
    assert "на «ты»" in system
    assert "Анна" in system
    assert "душевно" in system
    assert "воспоминания" in system
    assert "Анна" in welcome_back(info)
    assert "Стиль: 🌷" in communication_summary(info)
    assert "Форма: ты" in communication_summary(info)
    assert "Как будет звучать Ваш Сушеф?" in style_comparison({})
    assert "на «вы»" in communication_instructions({})


def test_custom_voice_and_preference_validation():
    prefs = {
        "display_name": "Зоя",
        "address_form": "вы",
        "conversation_style": "custom",
        "style_notes": "Галантно, с лёгким юмором.",
    }
    prompt = build_system("recipe", prefs)
    assert "Галантно, с лёгким юмором." in prompt
    assert "не команды к действию" in prompt
    for key, value in (
        ("display_name", "  Анна  "),
        ("address_form", "ТЫ"),
        ("conversation_style", "warm"),
        ("style_notes", "Нежно и кратко"),
        ("onboarding_skipped", "yes"),
    ):
        assert validate_preference(key, value)
    for key, value in (
        ("display_name", "x" * 61),
        ("display_name", "Аня\nнебезопасное"),
        ("address_form", "Вы, пожалуйста"),
        ("conversation_style", "unrecognized"),
        ("style_notes", "x" * 201),
        ("onboarding_skipped", "no"),
    ):
        with pytest.raises(ValueError):
            validate_preference(key, value)


@pytest.mark.asyncio
async def test_preferences_survive_restart_and_stay_private(tmp_path):
    path = tmp_path / "personal.db"
    url = f"sqlite+aiosqlite:///{path}"
    store = Storage(url)
    await store.create_tables()
    user, stranger = 555, 556
    try:
        await store.set_preference(user, "display_name", "Анна")
        await store.set_preference(user, "address_form", "ты")
        await store.set_preference(user, "conversation_style", "elegant")
        await store.set_preference(user, "style_notes", "Больше тёплых деталей")
        assert (await store.get_user(stranger))["preferences"] == {}
    finally:
        await store.close()

    reopened = Storage(url)
    try:
        prefs = (await reopened.get_user(user))["preferences"]
        assert prefs["display_name"] == "Анна"
        assert prefs["address_form"] == "ты"
        assert prefs["conversation_style"] == "elegant"
        assert (await reopened.get_user(stranger))["preferences"] == {}
        export = await reopened.export_user_data(user)
        assert export["profile"]["preferences"]["display_name"] == "Анна"
        await reopened.set_preference(user, "display_name", "-")
        assert "display_name" not in (await reopened.get_user(user))["preferences"]
        await reopened.delete_user(user)
        assert (await reopened.export_user_data(user))["profile"] is None
    finally:
        await reopened.close()


@pytest.mark.asyncio
async def test_confirmed_culinary_memory_and_story_stays_separate(tmp_path):
    store = Storage(f"sqlite+aiosqlite:///{tmp_path / 'facts.db'}")
    await store.create_tables()
    try:
        fact_id = await store.propose_memory(555, "dish_story", "Готовили ризотто с грибами")
        assert await store.personal_memories(555) == []
        assert await store.confirm_memory(555, fact_id)
        assert (await store.personal_memories(555))[0]["kind"] == "dish_story"
        assert await store.personal_memories(556) == []
    finally:
        await store.close()
