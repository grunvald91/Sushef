"""Кнопки-действия, сохранение выжимки, пробная реклама, копируемый текст и rich-блоки."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.types import InputRichBlockTable

from sushef.config import Settings
from sushef.rich_blocks import markdown_to_blocks, needs_blocks
from sushef.storage import Storage
from sushef.telegram_dialogue import DraftStreamer, recipe_context_tag, send_dialogue
from sushef.telegram_format import telegram_html

UID = 4242
RECIPE = {
    "title": "Паста с томатами", "chef_note": "Главное — не переварить пасту.",
    "time_minutes": 20, "servings": 2,
    "ingredients": [{"name": "паста", "amount": "200 г"}, {"name": "томаты", "amount": "3 шт"}],
    "steps": ["Отварите пасту.", "Прогрейте томаты.", "Смешайте."],
    "step_timers": [], "step_insights": [], "safety_notes": [],
}
ANSWER = ("Сделаем пасту!\n\nПродукты:\n- паста 200 г\n- томаты 3 шт\n\n"
          "Как готовить:\n1. Отварите пасту.\n2. Прогрейте томаты.\n3. Смешайте.")


@pytest.fixture
async def storage(tmp_path):
    db = Storage(f"sqlite+aiosqlite:///{tmp_path / 'b.db'}")
    await db.create_tables()
    yield db
    await db.close()


def settings(**kw):
    values = dict(telegram_bot_token="123456:test-token", claudehub_api_key="sk-test-key",
                  payment_exempt_ids="", support_admin_username="",
                  telegram_rich_recipe_cards=False, telegram_draft_preview=False,
                  telegram_stream_answers=False, telegram_seen_reaction=False)
    values.update(kw)
    return Settings(_env_file=None, **values)


def bot_message(chat_id=UID):
    return SimpleNamespace(
        chat=SimpleNamespace(id=chat_id, type="private"), message_id=10,
        answer=AsyncMock(), answer_invoice=AsyncMock(),
        bot=SimpleNamespace(id=777, send_chat_action=AsyncMock(), send_message=AsyncMock(),
                            send_rich_message=AsyncMock()),
    )


def callback(data, message):
    return SimpleNamespace(data=data, message=message, answer=AsyncMock(),
                           from_user=SimpleNamespace(id=UID, username=None, full_name="Гость"))


def buttons(markup):
    return {b.callback_data for row in markup.inline_keyboard for b in row if b.callback_data}


def test_copyable_text_and_tables_in_plain_html():
    html = telegram_html("Купить: `мука 200 г`\n```\nt=22; ph=4.1\n```\n"
                         "| Вариант | Время |\n|---|---|\n| Паста | 20 мин |")
    assert "<code>мука 200 г</code>" in html
    assert "<pre>t=22; ph=4.1</pre>" in html
    assert "<pre>Вариант │ Время" in html and "|---|" not in html
    assert "<code>&lt;b&gt;</code>" in telegram_html("`<b>`")  # код тоже экранирован


def test_markdown_tables_and_checklists_become_native_blocks():
    md = "## Сравнение\n| Вариант | Время |\n|---|---|\n| **Паста** | 20 мин |\n\n- [ ] мука\n- [x] соль"
    assert needs_blocks(md) and not needs_blocks("## Заголовок\n- пункт\n1. шаг")
    blocks = markdown_to_blocks(md)
    table = next(b for b in blocks if isinstance(b, InputRichBlockTable))
    assert table.cells[0][0].is_header and table.cells[1][0].text.text == "Паста"
    checks = blocks[-1].items
    assert [i.has_checkbox for i in checks] == [True, True]
    assert [i.is_checked for i in checks] == [False, True]


@pytest.mark.asyncio
async def test_dialogue_with_table_is_sent_as_rich_blocks():
    message = bot_message()
    answer = ("Вот сравнение двух вариантов ужина, чтобы было проще выбрать под настроение:\n\n"
              "| Вариант | Время | Вкус |\n|---|---|---|\n| Паста | 20 мин | нежный |\n| Рис | 30 мин | пряный |")
    assert await send_dialogue(message, answer, None, rich_enabled=True) == "rich"
    rich = message.bot.send_rich_message.await_args.kwargs["rich_message"]
    assert rich.blocks and rich.markdown is None


@pytest.mark.asyncio
async def test_draft_streamer_throttles_and_disables_on_error():
    clock = iter([0.0, 0.5, 2.0, 4.0]).__next__
    message = bot_message()
    message.bot.send_rich_message_draft = AsyncMock()
    stream = DraftStreamer(message, interval=1.0, clock=clock)
    text = "Сначала разогрейте сковороду и подготовьте все продукты заранее. "
    await stream(text)          # t=0 → отправлено
    await stream(text * 2)      # t=0.5 → пропущено
    await stream(text * 3)      # t=2 → отправлено
    assert message.bot.send_rich_message_draft.await_count == 2
    message.bot.send_rich_message_draft.side_effect = RuntimeError("draft unsupported")
    await stream(text * 4)
    assert stream.enabled is False


@pytest.mark.asyncio
async def test_chef_stream_falls_back_when_stream_unavailable():
    from sushef.chef import Chef
    chef = Chef(settings())
    chef.client = SimpleNamespace(messages=SimpleNamespace(
        stream=lambda **kw: (_ for _ in ()).throw(RuntimeError("no streaming")),
        create=AsyncMock(return_value=SimpleNamespace(content=[SimpleNamespace(type="text", text="Ответ")])),
    ))
    partial = AsyncMock()
    assert await chef.answer("ask", "вопрос", {}, [], on_partial=partial) == "Ответ"
    partial.assert_not_awaited()


@pytest.mark.asyncio
async def test_every_trial_answer_ends_with_monthly_offer(storage):
    from sushef.bot import text_message
    s = settings(free_trial_requests=10)
    message = bot_message()
    message.text, message.reply_to_message = "Как сварить рис рассыпчатым?", None
    message.from_user = SimpleNamespace(id=UID, username=None, full_name="Гость")
    chef = SimpleNamespace(answer=AsyncMock(return_value="Промойте рис и варите под крышкой."))
    await text_message(message, storage, chef, s)
    last = message.answer.await_args_list[-1]
    assert "осталось" in last.args[0] and "9 из 10" in last.args[0] and "100 ⭐" in last.args[0]
    assert "pay:buy" in buttons(last.kwargs["reply_markup"])


@pytest.mark.asyncio
async def test_paid_users_get_no_trial_offer(storage):
    from sushef.bot import text_message
    await storage.record_star_payment(UID, "c", "", 100, "XTR", 30)
    message = bot_message()
    message.text, message.reply_to_message = "Как сварить рис?", None
    message.from_user = SimpleNamespace(id=UID, username=None, full_name="Гость")
    chef = SimpleNamespace(answer=AsyncMock(return_value="Промойте рис."))
    await text_message(message, storage, chef, settings())
    assert all("pay:buy" not in buttons(c.kwargs["reply_markup"])
               for c in message.answer.await_args_list if c.kwargs.get("reply_markup"))


@pytest.mark.asyncio
async def test_dialogue_recipe_offers_save_buttons_and_saves_summary_once(storage, monkeypatch):
    import sushef.bot as bot_module
    from sushef.bot import save_dialogue_recipe, text_message
    monkeypatch.setattr(bot_module, "Message", SimpleNamespace)
    s = settings(payments_enabled=False)
    message = bot_message()
    question = "Что сделать из пасты и томатов?"
    message.text, message.reply_to_message = question, None
    message.from_user = SimpleNamespace(id=UID, username=None, full_name="Гость")
    chef = SimpleNamespace(answer=AsyncMock(return_value=ANSWER),
                           recipe=AsyncMock(return_value=dict(RECIPE)))
    await text_message(message, storage, chef, s)
    tag = recipe_context_tag(question)
    assert {"dialogue:fav:" + tag, "dialogue:save:" + tag} <= buttons(
        message.answer.await_args.kwargs["reply_markup"])

    await save_dialogue_recipe(callback("dialogue:fav:" + tag, message), storage, chef, s)
    assert "выжимку" in chef.recipe.await_args.args[0].lower() or "ВЫЖИМКУ" in chef.recipe.await_args.args[0]
    assert [f["recipe"]["title"] for f in await storage.favorites(UID)] == ["Паста с томатами"]
    archive = await storage.archived_recipes(UID)
    assert archive[0]["origin"] == "dialogue"

    await save_dialogue_recipe(callback("dialogue:save:" + tag, message), storage, chef, s)
    await save_dialogue_recipe(callback("dialogue:fav:" + tag, message), storage, chef, s)
    assert chef.recipe.await_count == 1  # повторно модель не вызывается
    assert len(await storage.favorites(UID)) == 1
    assert len(await storage.archived_recipes(UID)) == 1


@pytest.mark.asyncio
async def test_card_save_buttons_target_their_own_recipe(storage, monkeypatch):
    import sushef.bot as bot_module
    from sushef.bot import button_clicked, recipe_keyboard
    monkeypatch.setattr(bot_module, "Message", SimpleNamespace)
    first = await storage.set_recipe(UID, dict(RECIPE))
    await storage.set_recipe(UID, {**RECIPE, "title": "Другое блюдо"})
    assert {f"archive:fav:{first}", f"archive:saved:{first}"} <= buttons(recipe_keyboard(RECIPE, first))
    message = bot_message()
    await button_clicked(callback(f"archive:fav:{first}", message), storage, settings())
    await button_clicked(callback(f"archive:fav:{first}", message), storage, settings())
    assert [f["recipe"]["title"] for f in await storage.favorites(UID)] == ["Паста с томатами"]
    assert "уже в избранном" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_mode_buttons_offer_one_tap_actions(storage, monkeypatch):
    import sushef.bot as bot_module
    from sushef.bot import QUICK_MENUS, button_clicked
    monkeypatch.setattr(bot_module, "Message", SimpleNamespace)
    for mode in ("recipe", "ask", "rescue", "plan"):
        message = bot_message()
        await button_clicked(callback("mode:" + mode, message), storage, settings())
        assert any(d.startswith("quick:") for d in buttons(message.answer.await_args.kwargs["reply_markup"]))
    for rows in QUICK_MENUS.values():
        for _, data in (b for row in rows for b in row):
            assert len(data.encode()) <= 64


@pytest.mark.asyncio
async def test_quick_button_runs_request_immediately(storage, monkeypatch):
    import sushef.bot as bot_module
    from sushef.bot import quick_action
    monkeypatch.setattr(bot_module, "Message", SimpleNamespace)
    message = bot_message()
    chef = SimpleNamespace(answer=AsyncMock(return_value="Добавьте картофель и сливки."))
    await quick_action(callback("quick:rescue:salt", message), storage, chef, settings(payments_enabled=False))
    mode, text = chef.answer.await_args.args[:2]
    assert mode == "rescue" and "пересолил" in text.lower()
    assert "картофель" in message.answer.await_args.args[0]


@pytest.mark.asyncio
async def test_archive_cook_button_starts_cooking_at_once(storage, monkeypatch):
    import sushef.bot as bot_module
    from sushef.bot import button_clicked
    monkeypatch.setattr(bot_module, "Message", SimpleNamespace)
    archive_id = await storage.set_recipe(UID, dict(RECIPE))
    message = bot_message()
    await button_clicked(callback(f"archive:cook:{archive_id}", message), storage, settings())
    assert "Отварите пасту" in message.answer.await_args.args[0]
    assert (await storage.current_cooking(UID))["step_index"] == 0
