"""Служба поддержки и подписка Telegram Stars: хранилище и обработчики без сети."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from sushef.billing import checkout_error, invoice_payload, parse_payload
from sushef.config import Settings
from sushef.storage import Storage
from sushef.support import ticket_for_admin, ticket_from_admin_message
from sushef.telegram_format import telegram_html

ADMIN, GUEST = 1001, 2002
DAY = 86400


@pytest.fixture
async def storage(tmp_path):
    db = Storage(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    await db.create_tables()
    yield db
    await db.close()


def settings(**overrides):
    values = dict(telegram_bot_token="123456:test-token", claudehub_api_key="sk-test-key",
                  support_admin_ids="", payment_exempt_ids="719076753")
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_defaults_price_and_exempt_owner_ids():
    s = settings()
    assert s.stars_price == 100 and s.subscription_days == 30
    assert 719076753 in s.payment_exempt_id_set
    assert s.support_admin_username == "grunvald"
    assert settings(support_admin_ids="1, 2 x3").support_admin_id_set == {1, 2}


def test_invoice_payload_is_bound_to_user_price_and_period():
    payload = invoice_payload(GUEST, 30)
    assert parse_payload(payload) == (30, GUEST)
    ok = dict(user_id=GUEST, price=100, days=30)
    assert checkout_error(payload, "XTR", 100, **ok) is None
    assert checkout_error(payload, "XTR", 1, **ok)
    assert checkout_error(payload, "RUB", 100, **ok)
    assert checkout_error(payload, "XTR", 100, user_id=ADMIN, price=100, days=30)
    assert checkout_error("foreign:payload", "XTR", 100, **ok)


def test_ticket_number_survives_telegram_rendering():
    card = ticket_for_admin(42, GUEST, "Анна", "anna", "Не приходит **таймер** <b>")
    rendered = telegram_html(card)
    assert "&lt;b&gt;" in rendered  # пользовательский HTML экранирован
    plain = rendered.replace("<b>", "").replace("</b>", "")
    assert ticket_from_admin_message(plain) == 42
    assert ticket_from_admin_message("Обычное сообщение") is None


@pytest.mark.asyncio
async def test_trial_then_paywall_then_paid_access(storage):
    kw = dict(daily_limit=25, trial_limit=2, exempt=False, payments_enabled=True, now_ts=1000)
    assert await storage.use_ai_request(GUEST, **kw) == "ok"
    assert await storage.use_ai_request(GUEST, **kw) == "ok"
    assert await storage.use_ai_request(GUEST, **kw) == "payment_required"
    assert (await storage.subscription(GUEST))["trial_used"] == 2
    paid = await storage.record_star_payment(GUEST, "charge-1", "", 100, "XTR", 30, now_ts=1000)
    assert paid == {"paid_until_ts": 1000 + 30 * DAY, "duplicate": False}
    assert await storage.use_ai_request(GUEST, **kw) == "ok"
    assert (await storage.subscription(GUEST))["trial_used"] == 2
    expired = {**kw, "now_ts": 1000 + 30 * DAY + 1}
    assert await storage.use_ai_request(GUEST, **expired) == "payment_required"


@pytest.mark.asyncio
async def test_exempt_and_disabled_payments_skip_paywall_but_keep_daily_limit(storage):
    kw = dict(daily_limit=1, trial_limit=0, payments_enabled=True)
    assert await storage.use_ai_request(719076753, exempt=True, **kw) == "ok"
    assert await storage.use_ai_request(719076753, exempt=True, **kw) == "daily_limit"
    assert await storage.use_ai_request(GUEST, exempt=False, **kw) == "payment_required"
    assert await storage.use_ai_request(GUEST, exempt=False, daily_limit=1, trial_limit=0,
                                        payments_enabled=False) == "ok"


@pytest.mark.asyncio
async def test_daily_limit_does_not_burn_trial(storage):
    kw = dict(daily_limit=1, trial_limit=5, exempt=False, payments_enabled=True)
    assert await storage.use_ai_request(GUEST, **kw) == "ok"
    assert await storage.use_ai_request(GUEST, **kw) == "daily_limit"
    assert (await storage.subscription(GUEST))["trial_used"] == 1


@pytest.mark.asyncio
async def test_star_payment_is_idempotent_extends_and_refunds(storage):
    await storage.record_star_payment(GUEST, "c1", "", 100, "XTR", 30, now_ts=0)
    again = await storage.record_star_payment(GUEST, "c1", "", 100, "XTR", 30, now_ts=0)
    assert again == {"paid_until_ts": 30 * DAY, "duplicate": True}
    longer = await storage.record_star_payment(GUEST, "c2", "", 100, "XTR", 30, now_ts=DAY)
    assert longer["paid_until_ts"] == 60 * DAY  # продлевает, а не сгорает
    assert await storage.mark_star_refunded("c2")
    assert not await storage.mark_star_refunded("c2")
    assert (await storage.subscription(GUEST))["paid_until_ts"] == 30 * DAY
    assert (await storage.star_payment("c2"))["status"] == "refunded"


@pytest.mark.asyncio
async def test_support_thread_reply_close_limits_and_privacy(storage):
    first = await storage.add_support_message(GUEST, GUEST, "Помогите", daily_limit=2)
    second = await storage.add_support_message(GUEST, GUEST, "Ещё деталь", daily_limit=2)
    assert first == second
    with pytest.raises(ValueError):
        await storage.add_support_message(GUEST, GUEST, "третье", daily_limit=2)
    assert (await storage.open_support_tickets())[0]["last_text"] == "Ещё деталь"
    target = await storage.add_support_reply(first, "Уже чиним")
    assert target == {"ticket_id": first, "user_id": GUEST, "chat_id": GUEST}
    assert await storage.add_support_reply(999, "нет такого") is None
    assert await storage.close_support_ticket(first)
    assert await storage.close_support_ticket(first) is None
    assert await storage.open_support_tickets() == []
    exported = await storage.export_user_data(GUEST)
    assert [m["sender"] for m in exported["support_messages"]] == ["user", "user", "support"]
    await storage.record_star_payment(GUEST, "keep", "", 100, "XTR", 30, now_ts=0)
    await storage.delete_user(GUEST)
    exported = await storage.export_user_data(GUEST)
    assert exported["support_messages"] == []
    assert exported["star_payments"]  # платёжные записи сохраняются для возвратов


@pytest.mark.asyncio
async def test_admin_username_is_claimed_once(storage):
    assert await storage.register_support_admin(ADMIN, "grunvald")
    assert await storage.register_support_admin(ADMIN, "grunvald")
    assert not await storage.register_support_admin(3003, "grunvald")
    assert await storage.support_admin_ids() == {ADMIN}


def fake_message(user_id, text, *, username=None, bot=None, reply_to=None):
    return SimpleNamespace(
        text=text, chat=SimpleNamespace(id=user_id, type="private"),
        from_user=SimpleNamespace(id=user_id, username=username, full_name="Гость"),
        answer=AsyncMock(), reply_to_message=reply_to,
        bot=bot or SimpleNamespace(id=777, send_message=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_support_message_reaches_admin_and_reply_reaches_user(storage):
    from sushef.bot import text_message
    s = settings()
    await storage.register_support_admin(ADMIN, "grunvald")
    await storage.set_mode(GUEST, "support:write")
    bot = SimpleNamespace(id=777, send_message=AsyncMock())
    await text_message(fake_message(GUEST, "Не открывается меню", bot=bot), storage, object(), s)
    admin_call = bot.send_message.await_args
    assert admin_call.args[0] == ADMIN
    assert "Обращение №1" in admin_call.args[1] and "Не открывается меню" in admin_call.args[1]
    assert (await storage.get_user(GUEST))["mode"] == "ask"

    card = SimpleNamespace(text="🛟 Обращение №1\nОт: Гость", from_user=SimpleNamespace(id=777))
    reply_bot = SimpleNamespace(id=777, send_message=AsyncMock())
    admin_msg = fake_message(ADMIN, "Попробуйте /menu", username="grunvald",
                             bot=reply_bot, reply_to=card)
    await text_message(admin_msg, storage, object(), s)
    delivered = reply_bot.send_message.await_args
    assert delivered.args[0] == GUEST and "Попробуйте /menu" in delivered.args[1]


@pytest.mark.asyncio
async def test_non_admin_cannot_answer_tickets(storage):
    from sushef.bot import text_message
    s = settings()
    await storage.register_support_admin(ADMIN, "grunvald")  # настоящий владелец закреплён
    await storage.add_support_message(GUEST, GUEST, "Вопрос", daily_limit=5)
    await storage.set_mode(3003, "support:reply:1")
    bot = SimpleNamespace(id=777, send_message=AsyncMock())
    chef = SimpleNamespace(answer=AsyncMock(side_effect=RuntimeError("no network")))
    bot.send_chat_action = AsyncMock()
    await text_message(fake_message(3003, "Я не админ", username="grunvald", bot=bot),
                       storage, chef, s)
    bot.send_message.assert_not_awaited()
    assert (await storage.get_user(3003))["mode"] == "ask"


@pytest.mark.asyncio
async def test_pre_checkout_and_successful_payment_handlers(storage):
    from sushef.bot import pre_checkout, successful_payment
    s = settings()
    query = SimpleNamespace(invoice_payload=invoice_payload(GUEST, 30), currency="XTR",
                            total_amount=100, from_user=SimpleNamespace(id=GUEST),
                            answer=AsyncMock())
    await pre_checkout(query, s)
    assert query.answer.await_args.kwargs == {"ok": True, "error_message": None}
    query.total_amount = 5
    await pre_checkout(query, s)
    assert query.answer.await_args.kwargs["ok"] is False

    message = fake_message(GUEST, None)
    message.successful_payment = SimpleNamespace(
        currency="XTR", total_amount=100, invoice_payload=invoice_payload(GUEST, 30),
        telegram_payment_charge_id="tg-charge", provider_payment_charge_id="")
    await successful_payment(message, storage, s)
    await successful_payment(message, storage, s)  # повторная доставка
    sub = await storage.subscription(GUEST)
    assert sub["paid_until_ts"] > 0
    assert "Подписка активна" in message.answer.await_args.args[0]
    exported = await storage.export_user_data(GUEST)
    assert len(exported["star_payments"]) == 1


@pytest.mark.asyncio
async def test_paywall_is_shown_instead_of_calling_ai(storage):
    from sushef.bot import text_message
    s = settings(free_trial_requests=0)
    chef = SimpleNamespace(answer=AsyncMock(side_effect=AssertionError("AI must not run")))
    message = fake_message(GUEST, "Что приготовить из гречки?")
    await text_message(message, storage, chef, s)
    sent = message.answer.await_args
    assert "100 ⭐" in sent.args[0]
    buttons = {b.callback_data for row in sent.kwargs["reply_markup"].inline_keyboard for b in row}
    assert "pay:buy" in buttons
