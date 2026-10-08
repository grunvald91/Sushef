from sushef.bot import main_keyboard, profile_text


def test_main_keyboard_has_eight_actions():
    markup = main_keyboard()
    assert len(markup.inline_keyboard) == 4
    assert sum(len(row) for row in markup.inline_keyboard) == 8
    data = {button.callback_data for row in markup.inline_keyboard for button in row}
    assert "mode:recipe" in data
    assert "cook:start" in data


def test_profile_display_defaults():
    text = profile_text({"allergens": "орехи"})
    assert "орехи" in text
    assert "не указано" in text
