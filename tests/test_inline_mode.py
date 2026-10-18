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
