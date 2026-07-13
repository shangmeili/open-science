from __future__ import annotations

import copy
import hashlib
import json
import unittest
from pathlib import Path

from heor_core.model import (
    MarkovSpecification,
    ModelValidationError,
    run_markov,
)


GOLDEN_PATH = Path(__file__).parents[1] / "golden_cases" / "two_strategy_markov.json"
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def golden_payload() -> dict:
    return json.loads(GOLDEN_PATH.read_text())


class MarkovModelTests(unittest.TestCase):
    def test_golden_case_matches_independent_hand_calculation(self) -> None:
        result = run_markov(MarkovSpecification.from_dict(golden_payload()))

        self.assertAlmostEqual(result.comparator.total_cost, 3475.288593111165)
        self.assertAlmostEqual(result.comparator.total_qaly, 1.6883071262009621)
        self.assertAlmostEqual(result.intervention.total_cost, 9649.958833579347)
        self.assertAlmostEqual(result.intervention.total_qaly, 1.8826406968498461)
        self.assertAlmostEqual(result.incremental.delta_cost, 6174.670240468182)
        self.assertAlmostEqual(result.incremental.delta_qaly, 0.194333570648884)
        self.assertAlmostEqual(result.incremental.icer, 31773.564494548336)
        self.assertEqual(result.incremental.interpretation, "tradeoff")
        self.assertFalse(result.approval_gates_complete)
        self.assertEqual(result.run_classification, "exploratory")

    def test_cohort_mass_is_conserved_in_every_cycle(self) -> None:
        result = run_markov(MarkovSpecification.from_dict(golden_payload()))

        for strategy in (result.comparator, result.intervention):
            for occupancy in strategy.occupancy:
                self.assertAlmostEqual(sum(occupancy), 1.0)

    def test_invalid_transition_row_is_rejected(self) -> None:
        payload = golden_payload()
        payload["strategies"]["intervention"]["transition_matrix"][0] = [
            0.8,
            0.15,
            0.1,
        ]

        with self.assertRaisesRegex(ModelValidationError, "must sum to 1"):
            MarkovSpecification.from_dict(payload)

    def test_analysis_authorization_requires_all_human_approvals(self) -> None:
        specification = MarkovSpecification.from_dict(golden_payload())

        with self.assertRaisesRegex(ModelValidationError, "human approvals"):
            run_markov(specification, require_approved=True)

    def test_complete_human_approvals_authorize_the_analysis(self) -> None:
        payload = golden_payload()
        payload["approvals"] = [
            {
                "gate": gate,
                "approved_by": "human-reviewer",
                "approved_at": "2026-07-14T12:00:00+08:00",
                "artifact_sha256": hashlib.sha256(gate.encode()).hexdigest(),
            }
            for gate in ("decision_problem", "conceptual_model", "analysis_plan")
        ]
        specification = MarkovSpecification.from_dict(payload)

        result = run_markov(specification, require_approved=True)

        self.assertTrue(result.approval_gates_complete)
        self.assertEqual(result.run_classification, "analysis_authorized")
        self.assertNotIn("Exploratory result", " ".join(result.warnings))

    def test_draft_reference_case_cannot_authorize_decision_support(self) -> None:
        payload = golden_payload()
        payload["reference_case"] = {"id": "CN-2026-draft", "status": "draft"}
        payload["approvals"] = [
            {
                "gate": gate,
                "approved_by": "human-reviewer",
                "approved_at": "2026-07-14T12:00:00+08:00",
                "artifact_sha256": hashlib.sha256(gate.encode()).hexdigest(),
            }
            for gate in ("decision_problem", "conceptual_model", "analysis_plan")
        ]
        specification = MarkovSpecification.from_dict(payload)

        with self.assertRaisesRegex(ModelValidationError, "draft reference case"):
            run_markov(specification, require_approved=True)

        exploratory = run_markov(specification)
        self.assertEqual(exploratory.run_classification, "exploratory")
        self.assertIn("Draft reference case", " ".join(exploratory.warnings))

    def test_half_cycle_correction_must_be_a_real_boolean(self) -> None:
        payload = golden_payload()
        payload["half_cycle_correction"] = "false"

        with self.assertRaisesRegex(ModelValidationError, "must be a boolean"):
            MarkovSpecification.from_dict(payload)

    def test_dominant_intervention_is_not_reported_with_a_misleading_icer(self) -> None:
        payload = golden_payload()
        payload["cycles"] = 1
        payload["discount_rates"] = {"costs": 0.0, "outcomes": 0.0}
        payload["strategies"]["intervention"]["state_costs"] = [
            500.0,
            2000.0,
            0.0,
        ]
        specification = MarkovSpecification.from_dict(payload)

        result = run_markov(specification)

        self.assertEqual(result.incremental.interpretation, "dominant")
        self.assertIsNone(result.incremental.icer)

    def test_input_payload_is_not_mutated(self) -> None:
        payload = golden_payload()
        original = copy.deepcopy(payload)

        run_markov(MarkovSpecification.from_dict(payload))

        self.assertEqual(payload, original)


class HarnessContractTests(unittest.TestCase):
    def test_seeded_agent_cannot_self_approve_or_claim_independent_validation(
        self,
    ) -> None:
        rules = (REPOSITORY_ROOT / "runtime" / "harness" / "AGENTS.md").read_text()

        self.assertIn("Humans retain decision authority", rules)
        self.assertIn("self-review is\n  never independent model validation", rules)
        self.assertIn("may not approve a gate", rules)
        self.assertIn("Never modify `.openscience/approvals.jsonl`", rules)
        self.assertNotIn("serve your own goals independently", rules)

    def test_seeded_state_exposes_required_gates_and_data_classification(self) -> None:
        state = (
            REPOSITORY_ROOT / "runtime" / "harness" / "knowledge" / "current-state.md"
        ).read_text()

        for gate in (
            "decision_problem",
            "conceptual_model",
            "analysis_plan",
            "independent_validation",
            "release",
        ):
            self.assertIn(f"- {gate}: pending", state)
        self.assertIn("- Data classification: unknown.", state)


if __name__ == "__main__":
    unittest.main()
