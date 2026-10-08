from decimal import Decimal

import pytest

from sushef.protocols import (
    PENDING_TOPICS, PROTOCOLS, assess_process, get_protocol,
    list_protocols, protocol_context, protocol_summary, validate_catalog,
)


def test_versioned_catalog_has_three_traceable_source_documents():
    validate_catalog()
    assert len(PROTOCOLS) >= 3
    assert {p.id for p in PROTOCOLS} == {
        "nchfp-sauerkraut", "nchfp-dill-pickles", "usu-yogurt"
    }
    assert len({p.id for p in PROTOCOLS}) == len(PROTOCOLS)
    for p in PROTOCOLS:
        assert p.revision and p.source_url.startswith("https://")
        assert p.publisher and p.status == "source_documented"
        assert p.checked_on == "2026-10-08"
        assert len(p.critical_limits) >= 1 and len(p.stop_rules) >= 1
        assert len(p.stages) >= 3
        assert p.source_url in protocol_summary(p)
        assert p.id in protocol_context(p.id)


def test_cabbage_and_pickles_formula_exact_without_imagined_percentages():
    cabbage = get_protocol("nchfp-sauerkraut")
    assert any("25 фунтов" in s and "3/4 чашки" in s for s in cabbage.ingredients)
    assert any("5 фунтов" in s and "3 столовые ложки" in s for s in cabbage.ingredients)
    pickles = get_protocol("nchfp-dill-pickles")
    assert any("1/2 чашки" in s and "5%-го" in s for s in pickles.ingredients)
    assert get_protocol("nchfp-invalid") is None
    assert len(list_protocols("vegetables")) == 2


def test_stage_boundaries_are_specific_to_each_process():
    cabbage = get_protocol("nchfp-sauerkraut")
    ferment = next(s for s in cabbage.stages if s.code == "ferment")
    assert Decimal(ferment.temperature_min_f) == 70
    assert Decimal(ferment.temperature_max_f) == 75
    yogurt = get_protocol("usu-yogurt")
    warm = next(s for s in yogurt.stages if s.code == "heat")
    assert Decimal(warm.temperature_min_f) == 185
    assert Decimal(warm.temperature_max_f) == 200
    ferment_yogurt = next(s for s in yogurt.stages if s.code == "ferment")
    assert ferment_yogurt.temperature_min_f is None  # Don't fabricate incubation temp.


def test_never_returns_safe_status_even_with_good_inputs():
    for protocol in PROTOCOLS:
        stage = next(s for s in protocol.stages if s.code == "ferment")
        temp = Decimal("72") if protocol.category == "vegetables" else None
        assessment = assess_process(
            protocol.id, stage.code, temp, recipe_unchanged=True,
            signs_of_spoilage=False, known_starter=True,
            ph=Decimal("4.3"),
        )
        assert assessment.status in {"STOP", "NEEDS_DATA", "CHECK_SOURCE"}
        assert assessment.status != "SAFE"


def test_modified_recipe_is_always_stop():
    assessment = assess_process(
        "nchfp-sauerkraut", "ferment", Decimal("72"),
        recipe_unchanged=False, signs_of_spoilage=False
    )
    assert assessment.status == "STOP"
    assert "пропорции" in " ".join(assessment.notes).lower()


def test_temperature_outside_exact_stage_is_stop():
    result = assess_process(
        "nchfp-dill-pickles", "ferment", Decimal("95"),
        recipe_unchanged=True, signs_of_spoilage=False
    )
    assert result.status == "STOP"
    assert "температура" in " ".join(result.notes).lower()


def test_spoilage_or_unknown_dairy_starter():
    spoilt = assess_process(
        "usu-yogurt", "ferment", None, recipe_unchanged=True,
        signs_of_spoilage=True, known_starter=True
    )
    assert spoilt.status == "STOP"
    no_starter = assess_process(
        "usu-yogurt", "ferment", None, recipe_unchanged=True,
        signs_of_spoilage=False, known_starter=False
    )
    assert no_starter.status == "STOP"


@pytest.mark.parametrize("invalid", [
    ("nchfp-sauerkraut", "ferment", Decimal("NaN"), None),
    ("nchfp-sauerkraut", "ferment", Decimal("999"), None),
    ("nchfp-sauerkraut", "ferment", Decimal("72"), Decimal("15")),
    ("nchfp-sauerkraut", "unknown", Decimal("72"), None),
    ("unknown", "ferment", Decimal("72"), None),
])
def test_bad_protocol_or_sensor_input_rejected(invalid):
    pid, stage, temp, ph = invalid
    with pytest.raises(ValueError):
        assess_process(pid, stage, temp, recipe_unchanged=True, ph=ph)


def test_sensitive_topics_remain_pending_until_specific_source():
    assert {"koji", "natto", "enzymes", "cold", "warm"}.issubset(PENDING_TOPICS)
    assert not any(p.category == "enzymes" for p in list_protocols())
