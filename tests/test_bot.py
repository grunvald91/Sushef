from sushef.bot import main_keyboard, profile_text


def test_main_keyboard_has_eight_actions():
    markup = main_keyboard()
    assert len(markup.inline_keyboard) == 5
    assert sum(len(row) for row in markup.inline_keyboard) == 10
    data = {button.callback_data for row in markup.inline_keyboard for button in row}
    assert "mode:recipe" in data
    assert "cook:start" in data
    assert "view:pantry" in data
    assert "view:week" in data


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
