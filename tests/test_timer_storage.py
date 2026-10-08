import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sushef.storage import Storage
from sushef.timer_worker import deliver_due_timers


@pytest.fixture
async def db(tmp_path):
    storage = Storage(f"sqlite+aiosqlite:///{tmp_path / 'timers.db'}")
    await storage.create_tables()
    yield storage
    await storage.close()


async def prepared(db, user_id=100, recipe=None):
    recipe = recipe or {
        "title": "Рагу", "steps": ["Подготовить", "Томить", "Подать"],
        "step_timers": [{"step_index": 1, "minutes": 10, "label": "Томление"}],
    }
    await db.set_recipe(user_id, recipe)
    return await db.start_cooking(user_id)


@pytest.mark.asyncio
async def test_explicit_start_rejects_invalid_input_and_no_session(db):
    with pytest.raises(ValueError, match="пошаговое"):
        await db.start_timer(100, 100, 5, "Варка", now_ts=1000)
    await prepared(db)
    for value in (0, 241, -5, True, 0.5):
        with pytest.raises(ValueError):
            await db.start_timer(100, 100, value, "Варка", now_ts=1000)
    with pytest.raises(ValueError, match="личном"):
        await db.start_timer(100, -100, 5, "Варка", now_ts=1000)
    assert await db.user_timers(100) == []


@pytest.mark.asyncio
async def test_guided_cooking_resumes_and_timer_survives_step_switch(db):
    await prepared(db)
    timer = await db.start_timer(100, 100, 5, "Картофель", now_ts=1000)
    await db.advance_cooking(100)
    resumed = await db.start_cooking(100)
    assert resumed["step_index"] == 1  # Do not reset to first step.
    assert (await db.user_timers(100))[0]["id"] == timer["id"]
    assert (await db.claim_due_timers(now_ts=1299)) == []
    claimed = await db.claim_due_timers(now_ts=1300)
    assert [x["id"] for x in claimed] == [timer["id"]]
    assert claimed[0]["step_index"] == 0  # Timer remains associated with original step.
    assert await db.claim_due_timers(now_ts=1301) == []
    assert await db.complete_timer_delivery(timer["id"], success=True, now_ts=1301)
    assert await db.user_timers(100) == []
    assert not await db.complete_timer_delivery(timer["id"], success=True)


@pytest.mark.asyncio
async def test_worker_sends_exact_private_chat_and_marks_delivered(db):
    await prepared(db)
    timer = await db.start_timer(100, 100, 1, "Перемешать", now_ts=1000)
    bot = SimpleNamespace(send_message=AsyncMock())
    report = await deliver_due_timers(bot, db, now_ts=1060)
    assert report == {"claimed": 1, "sent": 1, "retry": 0}
    assert bot.send_message.await_count == 1
    kwargs = bot.send_message.await_args.kwargs
    assert kwargs["chat_id"] == 100 and "не означает" in kwargs["text"]
    again = await deliver_due_timers(bot, db, now_ts=1070)
    assert again["claimed"] == 0
    assert await db.user_timers(100) == []


@pytest.mark.asyncio
async def test_failed_send_retries_after_backoff(db):
    await prepared(db)
    timer = await db.start_timer(100, 100, 1, "Помешать", now_ts=1000)
    fake = SimpleNamespace(send_message=AsyncMock(side_effect=RuntimeError("network")))
    report = await deliver_due_timers(fake, db, now_ts=1060)
    assert report == {"claimed": 1, "sent": 0, "retry": 1}
    assert await db.claim_due_timers(now_ts=1119) == []
    claimed = await db.claim_due_timers(now_ts=1120)
    assert len(claimed) == 1 and claimed[0]["attempts"] == 2
    assert await db.complete_timer_delivery(timer["id"], success=True, now_ts=1120)


@pytest.mark.asyncio
async def test_crash_recovery_after_expired_worker_lease(db):
    await prepared(db)
    await db.start_timer(100, 100, 1, "Кастрюля", now_ts=1000)
    first = await db.claim_due_timers(now_ts=1060)
    assert len(first) == 1
    assert await db.claim_due_timers(now_ts=1179) == []
    second = await db.claim_due_timers(now_ts=1180)
    assert len(second) == 1 and second[0]["attempts"] == 2
    await db.complete_timer_delivery(second[0]["id"], success=True, now_ts=1180)


@pytest.mark.asyncio
async def test_cancels_only_own_timer_and_reset_blocks_old_notifications(db):
    await prepared(db, 100)
    await prepared(db, 200)
    first = await db.start_timer(100, 100, 5, "Кастрюля", now_ts=1000)
    other = await db.start_timer(200, 200, 5, "Сковорода", now_ts=1000)
    assert not await db.cancel_timer(200, first["id"])
    assert await db.cancel_timer(100, first["id"])
    assert not await db.cancel_timer(100, first["id"])
    await db.clear_chat(200)
    assert await db.user_timers(100) == []
    assert await db.user_timers(200) == []
    assert await db.claim_due_timers(now_ts=1400) == []


@pytest.mark.asyncio
async def test_new_recipe_allergens_and_delete_me_cancel_timers(db):
    await prepared(db)
    await db.start_timer(100, 100, 2, "Рагу", now_ts=1000)
    await db.set_recipe(100, {"title": "Другое", "steps": ["Сварить"]})
    assert await db.user_timers(100) == []
    await db.start_cooking(100)
    await db.start_timer(100, 100, 2, "Другое", now_ts=1000)
    await db.set_preference(100, "allergens", "орехи")
    assert await db.user_timers(100) == []
    await db.delete_user(100)
    assert (await db.export_user_data(100))["cooking_timers"] == []


@pytest.mark.asyncio
async def test_timer_limit_and_export_scope(db):
    await prepared(db)
    for i in range(5):
        await db.start_timer(100, 100, 3, f"Таймер {i}", now_ts=1000)
    with pytest.raises(ValueError, match="не больше"):
        await db.start_timer(100, 100, 3, "Шестой", now_ts=1000)
    assert len((await db.export_user_data(100))["cooking_timers"]) == 5
    assert (await db.export_user_data(200))["cooking_timers"] == []


@pytest.mark.asyncio
async def test_timer_is_persistent_across_storage_restart(tmp_path):
    url = f"sqlite+aiosqlite:///{tmp_path / 'persistent.db'}"
    first = Storage(url)
    await first.create_tables()
    await prepared(first)
    await first.start_timer(100, 100, 1, "Проверить духовку", now_ts=1000)
    await first.close()
    second = Storage(url)
    assert len(await second.user_timers(100)) == 1
    sent = await deliver_due_timers(SimpleNamespace(send_message=AsyncMock()), second,
                                    now_ts=1060)
    assert sent["sent"] == 1
    await second.close()


@pytest.mark.asyncio
async def test_double_tap_does_not_schedule_duplicate(db):
    await prepared(db)
    a = await db.start_timer(100, 100, 5, "Кастрюля", now_ts=1000)
    b = await db.start_timer(100, 100, 5, "Кастрюля", now_ts=1001)
    assert a["id"] == b["id"]
    assert len(await db.user_timers(100)) == 1


@pytest.mark.asyncio
async def test_no_auto_advance_after_delivery(db):
    await prepared(db)
    await db.start_timer(100, 100, 1, "Помешать", now_ts=1000)
    sent = await deliver_due_timers(SimpleNamespace(send_message=AsyncMock()),
                                    db, now_ts=1060)
    assert sent["sent"] == 1
    assert (await db.current_cooking(100))["step_index"] == 0


@pytest.mark.asyncio
async def test_cancelled_claim_cannot_be_sent(db):
    await prepared(db)
    timer = await db.start_timer(100, 100, 1, "Духовка", now_ts=1000)
    await db.claim_due_timers(now_ts=1060)
    assert await db.cancel_timer(100, timer["id"])
    fake = SimpleNamespace(send_message=AsyncMock())
    result = await deliver_due_timers(fake, db, now_ts=1180)
    assert result["claimed"] == 0
    fake.send_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_exhausted_delivery_leases_do_not_remain_sending(db):
    await prepared(db)
    await db.start_timer(100, 100, 1, "Повтор", now_ts=1000)
    for now in (1060, 1180, 1300, 1420, 1540):
        claims = await db.claim_due_timers(now_ts=now)
        assert len(claims) == 1
    assert await db.claim_due_timers(now_ts=1660) == []
    assert await db.user_timers(100) == []
    rows = (await db.export_user_data(100))["cooking_timers"]
    assert rows[0]["status"] == "failed" and rows[0]["attempts"] == 5
