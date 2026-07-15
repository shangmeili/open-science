from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import unittest

from heor_core.cost_input_normalization import validate_cost_input_normalization
from heor_core.model import ModelValidationError


def plan() -> dict:
    return {
        "schema_version": "0.12.0",
        "analysis_id": "cost-test",
        "decision_problem": {"jurisdiction": "England", "perspective": "NHS and PSS"},
        "economic_basis": {"currency": "GBP", "price_year": 2026},
        "states": ["progression_free", "progressed", "dead"],
        "strategy_order": ["usual_care", "new_treatment"],
        "strategies": {
            "usual_care": {"state_costs": [120.0, 0.0, 0.0]},
            "new_treatment": {"state_costs": [240.0, 0.0, 0.0]},
        },
        "evidence_sources": [{"id": "price-source"}, {"id": "quantity-source"}],
        "assumptions": [{"id": "scope-basis", "status": "proposed"}],
        "input_provenance": [],
    }


def artifact(analysis: dict) -> tuple[dict, bytes]:
    raw = json.dumps(analysis, separators=(",", ":")).encode()
    value = {
        "schema_version": "0.1.0",
        "normalization_id": "cost-inputs",
        "analysis_id": "cost-test",
        "status": "ready_for_human_review",
        "base_analysis": {
            "path": "heor/analysis-plan.json",
            "content_sha256": hashlib.sha256(raw).hexdigest(),
        },
        "target_basis": {
            "currency": "GBP",
            "price_year": 2026,
            "jurisdiction": "England",
            "perspective": "NHS and PSS",
        },
        "item_order": ["usual-care-drug", "new-treatment-drug"],
        "items": {},
        "annual_state_costs": {
            "usual_care": [120.0, 0.0, 0.0],
            "new_treatment": [240.0, 0.0, 0.0],
        },
        "limitations": ["Event and one-time costs are outside this annual state-cost contract."],
    }
    for item_id, strategy_id, price in (
        ("usual-care-drug", "usual_care", 10.0),
        ("new-treatment-drug", "new_treatment", 20.0),
    ):
        value["items"][item_id] = {
            "item_id": item_id,
            "strategy_id": strategy_id,
            "state_id": "progression_free",
            "category": "drug_acquisition",
            "description": "One monthly dose represented as an annual state-cost rate.",
            "scope_basis_ids": ["scope-basis"],
            "annual_quantity": {"value": 12.0, "unit": "dose", "basis_ids": ["quantity-source"]},
            "unit_price": {
                "amount": price,
                "per_unit": "dose",
                "currency": "GBP",
                "price_year": 2026,
                "jurisdiction": "England",
                "price_basis": "paid_price",
                "tax_status": "excluded",
                "basis_ids": ["price-source"],
            },
            "adjustments": [],
            "normalized_unit_price": price,
            "normalized_annual_cost": price * 12.0,
        }
    return value, raw


class CostInputNormalizationTests(unittest.TestCase):
    def test_reproduces_all_annual_state_costs(self):
        analysis = plan()
        value, raw = artifact(analysis)
        summary = validate_cost_input_normalization(
            analysis, raw, value, json.dumps(value).encode()
        )
        self.assertEqual(summary.item_count, 2)
        self.assertEqual(summary.annual_state_costs["new_treatment"], (240.0, 0.0, 0.0))

    def test_requires_inflation_and_currency_factors_only_when_needed(self):
        analysis = plan()
        value, raw = artifact(analysis)
        item = value["items"]["new-treatment-drug"]
        item["unit_price"]["currency"] = "USD"
        item["unit_price"]["price_year"] = 2024
        item["unit_price"]["amount"] = 10.0
        item["adjustments"] = [
            {"kind": "inflation", "factor": 1.2, "method": "selected index", "basis_ids": ["price-source"]},
            {"kind": "currency_conversion", "factor": 2.0, "method": "selected exchange rate", "basis_ids": ["price-source"]},
        ]
        item["normalized_unit_price"] = 24.0
        item["normalized_annual_cost"] = 288.0
        value["annual_state_costs"]["new_treatment"][0] = 288.0
        analysis["strategies"]["new_treatment"]["state_costs"][0] = 288.0
        raw = json.dumps(analysis, separators=(",", ":")).encode()
        value["base_analysis"]["content_sha256"] = hashlib.sha256(raw).hexdigest()
        validate_cost_input_normalization(analysis, raw, value, json.dumps(value).encode())

    def test_rejects_stale_arithmetic_unknown_basis_and_silent_tax_status(self):
        for mutation in ("arithmetic", "basis", "tax"):
            with self.subTest(mutation=mutation):
                analysis = plan()
                value, raw = artifact(analysis)
                item = value["items"]["new-treatment-drug"]
                if mutation == "arithmetic":
                    item["normalized_annual_cost"] = 239.0
                elif mutation == "basis":
                    item["annual_quantity"]["basis_ids"] = ["invented"]
                else:
                    item["unit_price"]["tax_status"] = "unknown"
                with self.assertRaises(ModelValidationError):
                    validate_cost_input_normalization(
                        analysis, raw, value, json.dumps(value).encode()
                    )

    def test_rejects_aggregate_cost_drift(self):
        analysis = plan()
        value, raw = artifact(analysis)
        value["annual_state_costs"]["new_treatment"][0] = 241.0
        with self.assertRaisesRegex(ModelValidationError, "does not reproduce"):
            validate_cost_input_normalization(analysis, raw, value, json.dumps(value).encode())


if __name__ == "__main__":
    unittest.main()
