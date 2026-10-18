from sushef.bot import main_keyboard, profile_text


def test_main_keyboard_is_compact_with_deep_navigation():
    from sushef.bot import library_keyboard, more_keyboard
    markup = main_keyboard()
    assert len(markup.inline_keyboard) == 6
    assert sum(len(row) for row in markup.inline_keyboard) == 11
    data = {button.callback_data for row in markup.inline_keyboard for button in row}
    assert {"mode:recipe", "cook:start", "view:library", "view:more",
            "view:cuisines", "view:techniques", "view:profile",
            "view:guide", "support:new"} <= data
    library = {button.callback_data for row in library_keyboard().inline_keyboard for button in row}
    more = {button.callback_data for row in more_keyboard().inline_keyboard for button in row}
    assert {"view:pantry", "view:week", "view:archive", "view:memory"} <= library
    assert "view:ferment" in more
    assert {"view:subscription", "support:new", "view:guide"} <= more
    assert markup.inline_keyboard[0][0].style == "primary"


def test_profile_display_defaults():
    text = profile_text({"allergens": "орехи"})
    assert "орехи" in text
    assert "не указано" in text


def test_new_pantry_and_week_ui():
    from sushef.bot import pantry_keyboard, week_keyboard, cooking_keyboard
    p = {x.callback_data for row in pantry_keyboard().inline_keyboard for x in row}
    assert "pantry:add" in p and "pantry:remove" in p
    w = {x.callback_data for row in week_keyboard(0).inline_keyboard for x in row}
    assert "week:meal:0:0" in w and "week:day:6" in w
    active = {x.callback_data for row in cooking_keyboard().inline_keyboard for x in row}
    assert "cook:previous" in active


def test_fermentation_ui_exposes_all_safe_process_categories():
    from sushef.bot import fermentation_keyboard, fermentation_batch_keyboard
    from sushef.fermentation import PROCESS_LABELS
    data = {b.callback_data for row in fermentation_keyboard().inline_keyboard for b in row}
    for category in PROCESS_LABELS:
        assert f"ferment:guide:{category}" in data
    assert "ferment:list" in data
    active = {b.callback_data for row in fermentation_batch_keyboard(42, False).inline_keyboard for b in row}
    assert "ferment:observe:42" in active
    finished = {b.callback_data for row in fermentation_batch_keyboard(42, True).inline_keyboard for b in row}
    assert "ferment:observe:42" not in finished
    assert "ferment:remove:42" in finished


def test_documented_protocol_navigation_exists():
    from sushef.bot import fermentation_keyboard, fermentation_batch_keyboard
    from sushef.protocols import PROTOCOLS
    controls = {b.callback_data for row in fermentation_keyboard().inline_keyboard for b in row}
    assert "protocol:list" in controls
    assert "science:list" in controls
    assert len(PROTOCOLS) >= 4
    journal = {b.callback_data for row in fermentation_batch_keyboard(123, False).inline_keyboard for b in row}
    assert "protocol:check:123" in journal


def test_science_ids_fit_telegram_callback_limit():
    from sushef.science_library import CARDS
    for item in CARDS:
        assert len(("science:view:" + item.id).encode("utf-8")) <= 64
        assert len(("science:ask:" + item.id).encode("utf-8")) <= 64


def test_personal_profile_memory_and_archive_actions():
    from sushef.bot import memory_kind_keyboard, profile_keyboard
    from sushef.memory import PROFILE_FIELDS, MEMORY_KINDS
    profile = {b.callback_data for row in profile_keyboard().inline_keyboard for b in row}
    for field in PROFILE_FIELDS:
        assert "pref:" + field in profile
    memory = {b.callback_data for row in memory_kind_keyboard().inline_keyboard for b in row}
    for kind in MEMORY_KINDS:
        assert "memory:kind:" + kind in memory
    for value in memory | profile:
        assert len(value.encode("utf-8")) <= 64
