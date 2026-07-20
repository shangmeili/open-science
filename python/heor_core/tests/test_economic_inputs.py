from __future__ import annotations

from copy import deepcopy
import unittest

from heor_core.economic_inputs import EconomicSpecification
from heor_core.model import ModelValidationError


def valid_plan() -> dict:
    return {
        "schema_version": "0.12.0",
        "analysis_id": "economic-input-test",
        "economic_basis": {"currency": "GBP", "price_year": 2026},
        "partitioned_survival_analysis": {"path": "heor/partitioned-survival-plan.json"},
        "states": ["progression_free", "progressed", "dead"],
        "cycles": 120,
        "cycle_length_years": 1 / 12,
        "discount_rates": {"costs": 0.035, "outcomes": 0.035},
        "half_cycle_correction": True,
        "willingness_to_pay": None,
        "strategy_order": ["usual_care", "new_treatment"],
        "baseline_strategy_id": "usual_care",
        "strategies": {
            "usual_care": {
                "name": "Usual care",
                "state_costs": [100.0, 500.0, 0.0],
                "state_utilities": [0.8, 0.5, 0.0],
            },
            "new_treatment": {
                "name": "New treatment",
                "state_costs": [300.0, 500.0, 0.0],
                "state_utilities": [0.82, 0.5, 0.0],
            },
        },
    }


class EconomicSpecificationTests(unittest.TestCase):
    def test_accepts_only_common_economic_inputs(self):
        specification = EconomicSpecification.from_analysis_plan(valid_plan())
        self.assertEqual(specification.strategy_order, ("usual_care", "new_treatment"))
        self.assertEqual(specification.strategy_map["new_treatment"].state_costs[0], 300.0)

    def test_rejects_markov_transition_structure(self):
        plan = deepcopy(valid_plan())
        plan["strategies"]["usual_care"]["transition_matrix"] = [
            [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]
        ]
        with self.assertRaisesRegex(ModelValidationError, "transition structure is forbidden"):
            EconomicSpecification.from_analysis_plan(plan)

    def test_rejects_non_finite_or_misaligned_rewards(self):
        for field, value in (("state_costs", [1.0, float("inf"), 0.0]), ("state_utilities", [0.8, 0.5])):
            with self.subTest(field=field):
                plan = deepcopy(valid_plan())
                plan["strategies"]["new_treatment"][field] = value
                with self.assertRaises(ModelValidationError):
                    EconomicSpecification.from_analysis_plan(plan)


if __name__ == "__main__":
    unittest.main()
