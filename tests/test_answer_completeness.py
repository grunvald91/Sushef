"""Ответ не должен обрываться на полуслове; разговор держит тему и задаёт улучшающий вопрос."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from sushef.chef import (
    CONTINUE_PROMPT, Chef, join_continuation, trim_incomplete_tail,
)
from sushef.config import Settings
from sushef.prompts import build_system


def test_join_finishes_cut_word_and_adds_space_between_words():
    assert join_continuation("Дай", "те настояться") == "Дайте настояться"
    assert join_continuation("Дайте", " настояться") == "Дайте настояться"
    assert join_continuation("Дайте", "\n2. Шаг") == "Дайте\n2. Шаг"
    assert join_continuation("Готово", ". Приятного") == "Готово. Приятного"
    assert join_continuation("Солим,", "перчим") == "Солим, перчим"


def test_incomplete_tail_is_trimmed_to_last_sentence():
    assert trim_incomplete_tail("Раз. Два. Дайт") == "Раз. Два."
    assert trim_incomplete_tail("Всё готово!") == "Всё готово!"


class FakeStream:
    def __init__(self, chunks, stop_reason):
        self.chunks, self.stop_reason = chunks, stop_reason

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    @property
    def text_stream(self):
        async def gen():
            for chunk in self.chunks:
                yield chunk
        return gen()

    async def get_final_message(self):
        return SimpleNamespace(stop_reason=self.stop_reason)


def make_chef(streams=None, replies=None):
    chef = object.__new__(Chef)
    chef.model, chef.max_tokens = "test-model", 2600
    calls = []

    def stream(**kwargs):
        calls.append(kwargs)
        return streams.pop(0)

    async def create(**kwargs):
        calls.append(kwargs)
        text, reason = replies.pop(0)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)], stop_reason=reason)

    chef.client = SimpleNamespace(messages=SimpleNamespace(stream=stream, create=create))
    return chef, calls


@pytest.mark.asyncio
async def test_cut_stream_is_continued_and_joined_without_losing_text():
    chef, calls = make_chef(streams=[
        FakeStream(["## Приготовление\n1. Нарежьте. Дай"], "max_tokens"),
        FakeStream(["те настояться.\n2. Подавайте."], "end_turn"),
    ])
    seen = []

    async def on_partial(text):
        seen.append(text)

    answer = await chef.answer("ask", "Хочу яичницу", {}, [], on_partial=on_partial)
    assert answer == "## Приготовление\n1. Нарежьте. Дайте настояться.\n2. Подавайте."
    assert len(calls) == 2
    second = calls[1]["messages"]
    assert second[-2] == {"role": "assistant", "content": "## Приготовление\n1. Нарежьте. Дай"}
    assert second[-1] == {"role": "user", "content": CONTINUE_PROMPT}
    assert seen[-1] == answer  # человек видит дописанный текст и в черновике


@pytest.mark.asyncio
async def test_complete_stream_makes_a_single_request():
    chef, calls = make_chef(streams=[FakeStream(["Готово, приятного аппетита!"], "end_turn")])
    answer = await chef.answer("ask", "Привет", {}, [], on_partial=AsyncMock())
    assert answer == "Готово, приятного аппетита!"
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_continuation_is_limited_and_never_leaves_half_a_word():
    chef, calls = make_chef(streams=[
        FakeStream(["Раз. Два. Тр"], "max_tokens"),
        FakeStream(["и. Четы"], "max_tokens"),
        FakeStream(["ре. Пя"], "max_tokens"),
    ])
    answer = await chef.answer("ask", "Считаем", {}, [], on_partial=AsyncMock())
    assert len(calls) == 3  # первый запрос и не более двух продолжений
    assert answer == "Раз. Два. Три. Четыре."


@pytest.mark.asyncio
async def test_user_stop_during_continuation_is_not_swallowed():
    class Stopped(Exception):
        pass

    calls = {"n": 0}

    async def on_partial(text):
        calls["n"] += 1
        if calls["n"] == 2:
            raise Stopped()

    chef, _ = make_chef(streams=[
        FakeStream(["Начало и"], "max_tokens"), FakeStream([" продолжение"], "end_turn"),
    ])
    with pytest.raises(Stopped):
        await chef.answer("ask", "Вопрос", {}, [], on_partial=on_partial)


@pytest.mark.asyncio
async def test_non_stream_answer_is_continued_too():
    chef, calls = make_chef(replies=[("Первая часть. Втор", "max_tokens"), ("ая часть.", "end_turn")])
    answer = await chef.answer("ask", "Вопрос", {}, [])
    assert answer == "Первая часть. Вторая часть."
    assert len(calls) == 2


def test_default_answer_budget_fits_a_full_recipe():
    assert Settings.model_fields["max_output_tokens"].default >= 8000


def test_prompt_keeps_topic_and_asks_for_products_after_instant_recipe():
    text = build_system("ask", {"address_form": "вы"})
    assert "ПАМЯТЬ РАЗГОВОРА" in text and "ОСТАВАЙСЯ в этом блюде" in text
    assert "это ПРОДОЛЖЕНИЕ уже названного блюда" in text
    assert "рецепт дай сразу, без предварительного допроса" in text
    assert "какие продукты сейчас под рукой" in text
    assert "ДОЛЖЕН БЫТЬ ЗАКОНЧЕННЫЙ ОТВЕТ" in text
    assert "пиши компактно" not in text  # лишних ограничений длины в промпте нет
    # старое правило «без встречных вопросов» больше не отменяет вопрос к открытому запросу
    assert "Если ответ очевиден, ответь без встречных вопросов" not in text


# ---- богатые rich-ответы (Bot API 10.3) ----
from sushef.rich_blocks import buttons_block, markdown_to_blocks, needs_blocks
from sushef.telegram_dialogue import dialogue_shopping_items, send_dialogue
from sushef.telegram_format import telegram_html

RICH_ANSWER = (
    "Яичница с помидорами — маленькое солнце на сковороде, и сыр здесь играет первую скрипку.\n\n"
    "## 🥗 Продукты (на 2 порции)\n\n- яйца — 4 шт\n- помидор — 1 шт\n- сыр — 60 г\n\n"
    "## 👨‍🍳 Приготовление\n\n1. Разогрейте сковороду 2 минуты.\n2. Жарьте 3 минуты до белых краёв.\n\n"
    "> 👨‍🍳 Секрет шефа: снимайте с огня, пока желток чуть дрожит.\n\n"
    "| Замена | Вместо |\n|---|---|\n| брынза | сыр |\n\n"
    "## 🛒 Докупить\n\n- [ ] зелень — 1 пучок\n\n"
    "## 💡 Тонкости вкуса\n\n- Не солите белок заранее.\n- Подавайте сразу.\n\n"
    "Приятного аппетита! Какой сыр Вы любите?"
)


def kinds(blocks):
    return [type(block).__name__.replace("InputRichBlock", "") for block in blocks]


def test_tips_become_collapsible_and_closing_phrase_stays_visible():
    assert needs_blocks(RICH_ANSWER)
    names = kinds(markdown_to_blocks(RICH_ANSWER))
    assert "Details" in names and "ExpandableBlockQuotation" in names and "Table" in names
    assert names[-2:] == ["Details", "Paragraph"]  # вопрос после советов не спрятан


def test_checklist_and_quote_render_in_html_fallback():
    html = telegram_html("> 👨‍🍳 Секрет шефа: тихий огонь\n- [ ] зелень\n- [x] соль")
    assert "<blockquote>👨‍🍳 Секрет шефа: тихий огонь</blockquote>" in html
    assert "☐ зелень" in html and "☑ соль" in html


def test_shopping_items_come_only_from_products_section():
    assert dialogue_shopping_items(RICH_ANSWER) == ["яйца — 4 шт", "помидор — 1 шт", "сыр — 60 г"]
    assert dialogue_shopping_items("Просто совет без рецепта.") == []


@pytest.mark.asyncio
async def test_buttons_go_inside_message_before_tips_and_short_keyboard_below():
    bot = SimpleNamespace(send_rich_message=AsyncMock())
    message = SimpleNamespace(bot=bot, chat=SimpleNamespace(id=1, type="private"), answer=AsyncMock())
    full, compact = object(), object()
    buttons = [("🛒 Список покупок", "dialogue:shop:abc", "primary"),
               ("🧾 В карточку и готовить", "dialogue:recipe:abc", "primary")]
    assert await send_dialogue(message, RICH_ANSWER, full, inline_buttons=buttons,
                               rich_markup=compact) == "rich"
    call = bot.send_rich_message.await_args.kwargs
    names = kinds(call["rich_message"].blocks)
    assert names.index("Buttons") == names.index("Details") - 1
    assert call["reply_markup"] is compact
    sent = call["rich_message"].blocks[names.index("Buttons")].buttons
    assert [b.callback_data for b in sent] == ["dialogue:shop:abc", "dialogue:recipe:abc"]


@pytest.mark.asyncio
async def test_html_fallback_keeps_full_keyboard_with_every_action():
    import sushef.telegram_dialogue as dialogue

    class Unsupported(Exception):
        pass

    dialogue.TelegramBadRequest = Unsupported
    bot = SimpleNamespace(send_rich_message=AsyncMock(side_effect=Unsupported("no")))
    message = SimpleNamespace(bot=bot, chat=SimpleNamespace(id=1, type="private"), answer=AsyncMock())
    full, compact = object(), object()
    try:
        result = await send_dialogue(message, RICH_ANSWER, full,
                                     inline_buttons=[("a", "b", None)], rich_markup=compact)
    finally:
        from aiogram.exceptions import TelegramBadRequest
        dialogue.TelegramBadRequest = TelegramBadRequest
    assert result == "html"
    assert message.answer.await_args.kwargs["reply_markup"] is full


def test_prompt_asks_for_tables_shopping_checklist_and_chef_quote():
    text = build_system("ask", {"address_form": "вы"})
    assert "ОФОРМЛЯЙ это компактной Markdown-таблицей" in text
    assert "## 🛒 Докупить" in text and "- [ ] продукт — количество" in text
    assert "> 👨‍🍳 Секрет шефа" in text
    assert "бот сворачивает этот раздел" in text


@pytest.mark.asyncio
async def test_shopping_button_builds_checklist_without_ai_or_quota(monkeypatch):
    import sushef.bot as bot_module
    from sushef.bot import dialogue_shopping_list
    from sushef.telegram_dialogue import recipe_context_tag

    monkeypatch.setattr(bot_module, "Message", SimpleNamespace)
    question = "Хочу яичницу"
    sent = AsyncMock()
    monkeypatch.setattr(bot_module, "send_dialogue", sent)
    callback = SimpleNamespace(
        answer=AsyncMock(), from_user=SimpleNamespace(id=7, username=None),
        data="dialogue:shop:" + recipe_context_tag(question),
        message=SimpleNamespace(chat=SimpleNamespace(id=7, type="private"), answer=AsyncMock()),
    )
    storage = SimpleNamespace(
        get_history=AsyncMock(return_value=[
            {"role": "user", "content": question}, {"role": "assistant", "content": RICH_ANSWER}]),
        use_quota=AsyncMock(), use_ai_request=AsyncMock(),
    )
    await dialogue_shopping_list(callback, storage, SimpleNamespace(telegram_rich_recipe_cards=True))
    text = sent.await_args.args[1]
    assert "- [ ] яйца — 4 шт" in text and "- [ ] сыр — 60 г" in text
    storage.use_quota.assert_not_awaited()
    storage.use_ai_request.assert_not_awaited()
