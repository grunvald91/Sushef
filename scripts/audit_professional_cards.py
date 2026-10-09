#!/usr/bin/env python3
"""Offline editorial audit of production cards. No DB, network, SSH, LLM or Actions."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sushef.cuisine_catalog import validate_seed
from sushef.dish_process_cards import DISH_CARDS, validate_dish_cards
from sushef.dish_process_cards_v2 import (
    V2_DISH_CARDS, validate_v2_cards, scale_source_ingredients,
)
from sushef.technique_catalog import TECHNIQUES, validate_techniques


def main() -> int:
    checks = []
    for name, fn in [
        ("curated_cuisine_seed", validate_seed),
        ("source_dish_cards_v1", validate_dish_cards),
        ("professional_techniques", validate_techniques),
        ("production_cards_v2", validate_v2_cards),
    ]:
        fn()
        checks.append(name)

    v1 = {card["id"] for card in DISH_CARDS}
    v2 = {card["id"] for card in V2_DISH_CARDS}
    if len(v1) != 2 or len(v2) != 2 or v1 & v2:
        raise ValueError("Versioned source cards were lost or duplicated")
    for row in V2_DISH_CARDS:
        spec = row["production_spec"]
        if spec["status"] != "source_checked_not_kitchen_tested":
            raise ValueError("An untested card was marked as validated")
        unknown = spec["measurement"]
        if any(value is not None for key, value in unknown.items() if key != "basis"):
            raise ValueError("Unknown production values were filled without evidence")
        scaled = scale_source_ingredients(row, 2)
        if len(scaled) != len(row["ingredients"]):
            raise ValueError("Scaling changed the ingredient count")
        source_amounts = [x["source_amount"] for x in spec["ingredients"]]
        for item, source in zip(scaled, source_amounts):
            if item["scaled"]:
                value = Decimal(item["quantity"])
                original = Decimal(source["value"])
                if abs(value - (original / 2)) > Decimal("0.005"):
                    raise ValueError("Scaled quantity diverges from published source")
            else:
                if item["quantity"] != source["value"]:
                    raise ValueError("Qualitative input was replaced by invented weight")
    checks.extend([
        "v1_immutable_ids_retained",
        "v2_source_provenance",
        "production_measurements_not_fabricated",
        "scaled_quantities_and_qualitative_inputs",
    ])
    print(json.dumps({
        "status": "editorial_static_checks_passed",
        "count": len(checks),
        "checks": checks,
        "general_techniques": len(TECHNIQUES),
        "pilot_v1_cards": len(DISH_CARDS),
        "pilot_v2_cards": len(V2_DISH_CARDS),
        "not_in_scope": ["pytest", "live_server", "kitchen_trial", "database_restore"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
