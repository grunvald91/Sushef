import pytest

from sushef.science_library import (
    CARDS, get_knowledge, knowledge_context, knowledge_text,
    list_knowledge, validate_knowledge,
)


def test_all_scientific_cards_have_traceable_primary_evidence():
    validate_knowledge()
    assert len(CARDS) == 5
    assert {p.evidence for p in CARDS} == {
        "research_review", "manufacturer_guidance", "scientific_consensus"
    }
    assert len({p.id for p in CARDS}) == len(CARDS)
    for p in CARDS:
        assert p.source_url.startswith("https://")
        assert p.revision == "2026.10.08-1"
        assert p.home_protocol_authorized is False
        rendered = knowledge_text(p)
        assert p.source_url in rendered
        assert "НЕ является" in rendered
        assert "Нельзя переносить" in rendered


def test_koji_is_research_review_not_unsafe_home_recipe():
    koji = get_knowledge("koji-rice-risk-review")
    assert koji.evidence == "research_review"
    assert "Bacillus cereus" in " ".join(koji.biology_or_chemistry for _ in [0])
    assert "30–40" in " ".join(koji.source_conditions)
    assert "не аттестованная" in koji.specific_application
    assert any("домашн" in s.lower() for s in koji.warnings)
    assert "НЕ разрешённый" in knowledge_context(koji.id)


def test_manufacturer_enzyme_doses_are_pinned_to_exact_product_form():
    pec = get_knowledge("scottzyme-pec5l")
    rapidase = get_knowledge("rapidase-clear-extreme-granular")
    assert "1,0–1,3 мл/гл" in " ".join(pec.source_conditions)
    assert "1 г/гл" in " ".join(rapidase.source_conditions)
    assert "3 г/гл" in " ".join(rapidase.source_conditions)
    assert "гранулированн" in rapidase.specific_application.lower()
    assert "жидкой" in " ".join(rapidase.warnings)
    assert "дозы жидкого и гранулированного" in knowledge_context(rapidase.id)


def test_cultures_not_automatically_probiotics():
    culture = get_knowledge("fermented-foods-vs-probiotics")
    assert culture.evidence == "scientific_consensus"
    assert "штамм" in " ".join(culture.required_controls)
    assert "польз" in culture.biology_or_chemistry


def test_category_listing_does_not_authorize_reference_as_recipe():
    assert len(list_knowledge("enzymes")) == 3
    assert len(list_knowledge("koji")) == 1
    assert len(list_knowledge("cultures")) == 1
    assert list_knowledge("none") == ()
    assert get_knowledge("unknown") is None
    with pytest.raises(ValueError):
        knowledge_context("unknown")


def test_amylase_card_is_not_pectinase_or_arbitrary_cooking_dose():
    amylase = get_knowledge("novonesis-amylase-ag-300-l")
    assert amylase.category == "enzymes"
    assert amylase.home_protocol_authorized is False
    conditions = " ".join(amylase.source_conditions)
    assert "300 AGU/мл" in conditions
    assert "20–60 мл на 1000 л" in conditions
    assert "50–55 °C" in conditions
    assert "1–2 часов" in conditions
    assert "Novonesis" in amylase.publisher
    assert "12 °Brix" in conditions
    assert "сок" in amylase.specific_application.lower()
    assert "АГУ" not in conditions  # Don't translate industry activity units.
