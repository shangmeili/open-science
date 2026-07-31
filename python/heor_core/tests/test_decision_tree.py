from __future__ import annotations

import copy
import hashlib
import io
import json
import math
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from heor_core.cli import main
from heor_core.decision_tree import (
    DecisionTreeSpecification,
    run_decision_tree,
)
from heor_core.model import ModelValidationError


GOLDEN_PATH = (
    Path(__file__).parents[1]
    / "golden_cases"
    / "two_strategy_decision_tree.json"
)


def golden_payload() -> dict:
    return json.loads(GOLDEN_PATH.read_text())


class DecisionTreeTests(unittest.TestCase):
    def test_golden_case_matches_hand_calculation(self) -> None:
        payload = golden_payload()
        original = copy.deepcopy(payload)

        result = run_decision_tree(
            DecisionTreeSpecification.from_dict(payload)
        ).to_dict()

        self.assertEqual(payload, original)
        self.assertEqual(result["analysis_type"], "decision_tree")
        comparator = result["strategies"]["comparator"]
        intervention = result["strategies"]["intervention"]
        self.assertTrue(
            math.isclose(comparator["total_cost"], 1800.0, rel_tol=1e-12, abs_tol=1e-9)
        )
        self.assertTrue(
            math.isclose(comparator["total_qaly"], 0.68, rel_tol=1e-12, abs_tol=1e-9)
        )
        self.assertTrue(
            math.isclose(intervention["total_cost"], 2900.0, rel_tol=1e-12, abs_tol=1e-9)
        )
        self.assertTrue(
            math.isclose(intervention["total_qaly"], 0.7375, rel_tol=1e-12, abs_tol=1e-9)
        )
        incremental = result["pairwise_vs_baseline"]["intervention"]
        self.assertTrue(
            math.isclose(incremental["delta_cost"], 1100.0, rel_tol=1e-12, abs_tol=1e-9)
        )
        self.assertTrue(
            math.isclose(incremental["delta_qaly"], 0.0575, rel_tol=1e-12, abs_tol=1e-9)
        )
        self.assertTrue(
            math.isclose(
                incremental["icer"],
                19130.434782608696,
                rel_tol=1e-12,
                abs_tol=1e-9,
            )
        )
        self.assertTrue(
            math.isclose(
                incremental["incremental_net_monetary_benefit"],
                1775.0,
                rel_tol=1e-12,
                abs_tol=1e-9,
            )
        )
        self.assertEqual(
            result["optimal_at_primary_threshold"]["strategy_id"],
            "intervention",
        )
        self.assertEqual(len(comparator["calculation_trace"]), 3)
        chance_trace = comparator["calculation_trace"][0]
        self.assertEqual(
            chance_trace["branches"][0]["probability_provenance"][
                "assumption_ids"
            ],
            ["teaching-inputs"],
        )
        terminal_trace = next(
            row
            for row in comparator["calculation_trace"]
            if row["node_id"] == "comparator_success"
        )
        self.assertEqual(
            terminal_trace["cost_provenance"]["assumption_ids"],
            ["teaching-inputs"],
        )
        self.assertEqual(
            terminal_trace["qaly_provenance"]["assumption_ids"],
            ["teaching-inputs"],
        )
        terminal_probability = sum(
            row["reached_probability"]
            for row in comparator["calculation_trace"]
            if row["node_type"] == "terminal"
        )
        self.assertTrue(math.isclose(terminal_probability, 1.0, abs_tol=1e-9))

    def test_cli_replays_decision_tree_and_binds_input_hash(self) -> None:
        raw = GOLDEN_PATH.read_bytes()
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(main([str(GOLDEN_PATH)]), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["analysis_type"], "decision_tree")
        self.assertEqual(result["input_sha256"], hashlib.sha256(raw).hexdigest())

    def test_cli_rejects_decision_tree_with_markov_extension_option(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            other = Path(directory) / "other.json"
            other.write_text("{}")
            with self.assertRaisesRegex(
                SystemExit,
                "decision tree input cannot be combined",
            ):
                main([str(GOLDEN_PATH), "--uncertainty-plan", str(other)])

    def test_rejects_probability_outside_range_or_not_summing_to_one(self) -> None:
        for probabilities in ((1.1, -0.1), (0.6, 0.3)):
            with self.subTest(probabilities=probabilities):
                payload = golden_payload()
                branches = payload["strategies"]["comparator"]["nodes"][
                    "comparator_outcome"
                ]["branches"]
                branches[0]["probability"]["value"] = probabilities[0]
                branches[1]["probability"]["value"] = probabilities[1]
                with self.assertRaises(ModelValidationError):
                    DecisionTreeSpecification.from_dict(payload)

    def test_rejects_cycle_unreachable_node_and_multiple_parents(self) -> None:
        cases = []

        cycle = golden_payload()
        cycle["strategies"]["comparator"]["nodes"]["comparator_success"] = {
            "type": "chance",
            "branches": [
                {
                    "child_node_id": "comparator_outcome",
                    "probability": {
                        "value": 1.0,
                        "source_ids": [],
                        "assumption_ids": ["teaching-inputs"],
                    },
                }
            ],
        }
        cases.append(("cycle", cycle))

        unreachable = golden_payload()
        unreachable["strategies"]["comparator"]["nodes"]["orphan"] = {
            "type": "terminal",
            "cost": {
                "value": 0.0,
                "source_ids": [],
                "assumption_ids": ["teaching-inputs"],
            },
            "qaly": {
                "value": 0.0,
                "source_ids": [],
                "assumption_ids": ["teaching-inputs"],
            },
        }
        cases.append(("unreachable", unreachable))

        multiple = golden_payload()
        branches = multiple["strategies"]["comparator"]["nodes"][
            "comparator_outcome"
        ]["branches"]
        branches[1]["child_node_id"] = "comparator_success"
        cases.append(("multiple parents", multiple))

        for label, payload in cases:
            with self.subTest(label=label):
                with self.assertRaises(ModelValidationError):
                    DecisionTreeSpecification.from_dict(payload)

    def test_rejects_missing_provenance_and_unknown_assumption(self) -> None:
        for assumption_ids in ([], ["missing-assumption"]):
            with self.subTest(assumption_ids=assumption_ids):
                payload = golden_payload()
                value = payload["strategies"]["comparator"]["nodes"][
                    "comparator_success"
                ]["cost"]
                value["assumption_ids"] = assumption_ids
                with self.assertRaises(ModelValidationError):
                    DecisionTreeSpecification.from_dict(payload)

    def test_rejects_nonfinite_negative_cost_and_qaly_outside_one_year_bound(self) -> None:
        changes = (
            ("cost", float("nan")),
            ("cost", -1.0),
            ("qaly", 1.01),
            ("qaly", -1.01),
        )
        for field, value in changes:
            with self.subTest(field=field, value=value):
                payload = golden_payload()
                payload["strategies"]["comparator"]["nodes"][
                    "comparator_success"
                ][field]["value"] = value
                with self.assertRaises(ModelValidationError):
                    DecisionTreeSpecification.from_dict(payload)

    def test_rejects_long_horizon_discounting_and_half_cycle_correction(self) -> None:
        changes = (
            ("time_horizon_years", 1.01),
            ("half_cycle_correction", True),
            ("discount_rates", {"costs": 0.05, "outcomes": 0.0}),
        )
        for field, value in changes:
            with self.subTest(field=field):
                payload = golden_payload()
                payload[field] = value
                with self.assertRaises(ModelValidationError):
                    DecisionTreeSpecification.from_dict(payload)

    def test_rejects_unsupported_time_dependence_and_unknown_value_fields(self) -> None:
        cases = []
        recurrence = golden_payload()
        recurrence["recurrence"] = True
        cases.append(recurrence)

        intermediate_cost = golden_payload()
        intermediate_cost["strategies"]["comparator"]["nodes"][
            "comparator_outcome"
        ]["cost"] = {
            "value": 10.0,
            "source_ids": [],
            "assumption_ids": ["teaching-inputs"],
        }
        cases.append(intermediate_cost)

        time_dependent_branch = golden_payload()
        time_dependent_branch["strategies"]["comparator"]["nodes"][
            "comparator_outcome"
        ]["branches"][0]["cycle"] = 2
        cases.append(time_dependent_branch)

        unknown_value_field = golden_payload()
        unknown_value_field["strategies"]["comparator"]["nodes"][
            "comparator_success"
        ]["cost"]["unit"] = "CNY"
        cases.append(unknown_value_field)

        for index, payload in enumerate(cases):
            with self.subTest(case=index):
                with self.assertRaisesRegex(ModelValidationError, "unsupported field"):
                    DecisionTreeSpecification.from_dict(payload)

    def test_zero_incremental_effect_has_no_icer(self) -> None:
        payload = golden_payload()
        payload["strategies"]["intervention"] = copy.deepcopy(
            payload["strategies"]["comparator"]
        )
        payload["strategies"]["intervention"]["name"] = "same_effect"
        result = run_decision_tree(
            DecisionTreeSpecification.from_dict(payload)
        ).to_dict()
        incremental = result["pairwise_vs_baseline"]["intervention"]
        self.assertEqual(incremental["interpretation"], "equal_effect")
        self.assertIsNone(incremental["icer"])


if __name__ == "__main__":
    unittest.main()
