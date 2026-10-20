"""Inline-режим: доступ только по подписке, ответ после выбора результата."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from sushef.config import Settings
from sushef.inline_mode import chosen_question, inline_query, question_id
from sushef.storage import Storage

UID = 5151


@pytest.fixture
async def storage(tmp_path):
    db = Storage(f"sqlite+aiosqlite:///{tmp_path / 'i.db'}")
    await db.create_tables()
    yield db
    await db.close()


def settings(**kw):
    values = dict(telegram_bot_token="123456:test-token", claudehub_api_key="sk-test-key",
                  payment_exempt_ids="719076753", support_admin_username="",
                  telegram_rich_recipe_cards=False)
    values.update(kw)
    return Settings(_env_file=None, **values)


def fake_bot():
    return SimpleNamespace(me=AsyncMock(return_value=SimpleNamespace(username="sushef_bot")),
                           edit_message_text=AsyncMock())


def query(text, user_id=UID):
    return SimpleNamespace(query=text, from_user=SimpleNamespace(id=user_id, username=None),
                           answer=AsyncMock(), bot=fake_bot())


@pytest.mark.asyncio
async def test_inline_requires_paid_subscription_even_during_trial(storage):
    q = query("как спасти суп")
    await inline_query(q, storage, settings())
    results = q.answer.await_args.args[0]
    button = q.answer.await_args.kwargs["button"]
    assert results == [] and button.start_parameter == "subscribe"


@pytest.mark.asyncio
async def test_paid_user_gets_ask_result_and_own_recipes(storage):
    await storage.record_star_payment(UID, "c1", "", 100, "XTR", 30)
    await storage.set_recipe(UID, {"title": "Борщ", "ingredients": [{"name": "свёкла", "amount": "1 шт"}],
                                   "steps": ["Сварить."], "servings": 4, "time_minutes": 90})
    q = query("борщ")
    await inline_query(q, storage, settings())
    results = q.answer.await_args.args[0]
    assert results[0].id == question_id("борщ") and results[0].reply_markup is not None
    assert results[1].id.startswith("rec:") and "Борщ" in results[1].title
    assert q.answer.await_args.kwargs["is_personal"] is True


@pytest.mark.asyncio
async def test_exempt_owner_ids_can_use_inline(storage):
    q = query("что приготовить", user_id=719076753)
    await inline_query(q, storage, settings())
    assert q.answer.await_args.args[0][0].title == "👨‍🍳 Спросить Сушефа"


@pytest.mark.asyncio
async def test_chosen_question_is_answered_by_editing_inline_message(storage):
    await storage.record_star_payment(UID, "c1", "", 100, "XTR", 30)
    bot = fake_bot()
    result = SimpleNamespace(result_id=question_id("как спасти суп"), query="как спасти суп",
                             inline_message_id="IM1", bot=bot,
                             from_user=SimpleNamespace(id=UID, username=None))
    chef = SimpleNamespace(answer=AsyncMock(return_value="Добавьте **картофель** и воды."))
    await chosen_question(result, storage, chef, settings())
    assert "общем чате" in chef.answer.await_args.args[1]
    edit = bot.edit_message_text.await_args.kwargs
    assert edit["inline_message_id"] == "IM1" and "<b>картофель</b>" in edit["text"]


@pytest.mark.asyncio
async def test_chosen_question_without_subscription_does_not_call_ai(storage):
    bot = fake_bot()
    result = SimpleNamespace(result_id="ask:x", query="как спасти суп", inline_message_id="IM2",
                             bot=bot, from_user=SimpleNamespace(id=UID, username=None))
    chef = SimpleNamespace(answer=AsyncMock(side_effect=AssertionError("no AI without payment")))
    await chosen_question(result, storage, chef, settings())
    assert "по подписке" in bot.edit_message_text.await_args.kwargs["text"]


def guest(text, user_id=UID):
    bot = fake_bot()
    bot.answer_guest_query = AsyncMock(return_value=SimpleNamespace(inline_message_id="G1"))
    return SimpleNamespace(guest_query_id="gq1", text=text, caption=None, bot=bot,
                           from_user=SimpleNamespace(id=user_id, username=None))


@pytest.mark.asyncio
async def test_guest_mode_answers_paid_users_in_foreign_chat(storage):
    from sushef.inline_mode import guest_message
    await storage.record_star_payment(UID, "c1", "", 100, "XTR", 30)
    message = guest("@sushef_bot как спасти пересоленный суп")
    chef = SimpleNamespace(answer=AsyncMock(return_value="Добавьте картофель."))
    await guest_message(message, storage, chef, settings())
    placeholder = message.bot.answer_guest_query.await_args.kwargs["result"]
    assert "обдумывает" in placeholder.input_message_content.message_text
    assert chef.answer.await_args.args[1].startswith("как спасти пересоленный суп")
    assert message.bot.edit_message_text.await_args.kwargs["inline_message_id"] == "G1"


@pytest.mark.asyncio
async def test_guest_mode_without_subscription_offers_it_and_skips_ai(storage):
    from sushef.inline_mode import guest_message
    message = guest("@sushef_bot что приготовить")
    chef = SimpleNamespace(answer=AsyncMock(side_effect=AssertionError("no AI")))
    await guest_message(message, storage, chef, settings())
    text = message.bot.answer_guest_query.await_args.kwargs["result"].input_message_content.message_text
    assert "по подписке" in text
    message.bot.edit_message_text.assert_not_awaited()


@pytest.mark.asyncio
async def test_stop_button_keeps_partial_answer():
    from sushef.telegram_dialogue import DraftStreamer, GenerationStopped, stop_stream
    message = SimpleNamespace(chat=SimpleNamespace(id=1, type="private"), message_id=7,
                              bot=SimpleNamespace(send_rich_message_draft=AsyncMock()))
    text = "Сначала обжарьте лук до золотистого цвета на среднем огне, помешивая. "
    with DraftStreamer(message, interval=0) as streamer:
        await streamer(text)
        assert message.bot.send_rich_message_draft.await_args.kwargs["can_stop"] is True
        assert stop_stream(1, 7)
        with pytest.raises(GenerationStopped) as stopped:
            await streamer(text * 2)
    assert stopped.value.partial == text * 2
    assert not stop_stream(1, 7)  # поток снят с учёта после выхода
