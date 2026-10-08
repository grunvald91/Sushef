from decimal import Decimal

import pytest

from sushef.fermentation import (
    PROCESS_LABELS, ProtocolInputs, describe_process,
    fermentation_system_context, intake_text, screen_protocol,
)
from sushef.fermentation_journal import (
    SAFETY_REMINDER, observation_text, parse_observation,
)


@pytest.mark.parametrize("category", list(PROCESS_LABELS))
def test_every_category_has_guided_scientific_context(category):
    assert category in describe_process(category)
    prompt = fermentation_system_context(category)
    assert "не" in prompt.lower()
    assert "pH" in prompt
    assert "https://" in prompt
    assert "пробиотик" in prompt.lower()
    assert "пищ" in intake_text(category).lower()


@pytest.mark.parametrize("category", ["fake", "", "home_lab"])
def test_unsupported_categories_rejected(category):
    with pytest.raises(ValueError):
        describe_process(category)
    with pytest.raises(ValueError):
        screen_protocol(ProtocolInputs(
            category=category, substrate="капуста", verified_recipe=False))


def test_unsafe_raw_fish_requires_stop():
    result = screen_protocol(ProtocolInputs(
        category="other", substrate="сырая рыба", verified_recipe=False))
    assert result.status == "STOP"


def test_unpasteurized_dairy_requires_stop():
    result = screen_protocol(ProtocolInputs(
        category="dairy", substrate="молоко", verified_recipe=True,
        starter_food_grade=True, uses_pasteurized_milk=False,
        measured_temperature_c=Decimal("42")))
    assert result.status == "STOP"
    assert "пастеризован" in " ".join(result.reasons)


def test_non_food_grade_enzyme_requires_stop():
    result = screen_protocol(ProtocolInputs(
        category="enzymes", substrate="яблоко", verified_recipe=False,
        starter_food_grade=False))
    assert result.status == "STOP"


def test_even_complete_measurements_never_auto_approve():
    result = screen_protocol(ProtocolInputs(
        category="vegetables", substrate="капуста", verified_recipe=True,
        measured_temperature_c=Decimal("22"),
        measured_ph=Decimal("3.8"), finished=True))
    assert result.status == "NEEDS_INFORMATION"
    assert "не подтверждает" in " ".join(result.reasons)


def test_fermented_vegetables_with_high_ph_need_review():
    result = screen_protocol(ProtocolInputs(
        category="vegetables", substrate="капуста", verified_recipe=True,
        measured_temperature_c=Decimal("22"), measured_ph=Decimal("5.0"),
        finished=True))
    assert result.status == "NEEDS_INFORMATION"
    assert "кислотность" in " ".join(result.reasons)


def test_cold_hot_not_hardcoded_as_universal():
    context = fermentation_system_context("koji")
    assert "не универсальные" in context
    assert "Bacillus cereus" in context
    assert "ферментацией" in fermentation_system_context("enzymes")


def test_parse_manual_measurements_with_comma_and_notes():
    parsed = parse_observation("t=22,5; ph=4.2; note=Появились пузырьки")
    assert parsed.temperature_c == Decimal("22.5")
    assert parsed.ph == Decimal("4.2")
    assert parsed.note == "Появились пузырьки"
    assert "22.5 °C" in observation_text({
        "temperature_c": str(parsed.temperature_c), "ph": str(parsed.ph),
        "note": parsed.note,
    })
    assert "НЕ подтверждение" in SAFETY_REMINDER


@pytest.mark.parametrize("message", [
    "", "t=прохладно", "pH=15", "t=130", "t=NaN", "foo=bar",
    "t=22; t=23", "note=", "t=20; pH=2; note=hi; extra=bad",
])
def test_invalid_measurements_rejected(message):
    with pytest.raises(ValueError):
        parse_observation(message)


def test_log_accepts_only_note():
    parsed = parse_observation("note=пахнет кисло")
    assert parsed.ph is None and parsed.temperature_c is None
    assert parsed.note
