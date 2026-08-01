from __future__ import annotations

import copy
import hashlib
import json
import math
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from heor_core.decision_tree_uncertainty import run_decision_tree_uncertainty
from heor_core.cli import main
from heor_core.model import ModelValidationError


GOLDEN_PATH = (
    Path(__file__).parents[1]
    / "golden_cases"
    / "two_strategy_decision_tree.json"
)


def analysis_fixture() -> tuple[dict, bytes]:
    analysis = json.loads(GOLDEN_PATH.read_text())
    analysis["schema_version"] = "0.2.0"
    analysis["economic_basis"] = {
        "currency": "CNY",
        "price_year": 2026,
        "jurisdiction": "中国大陆",
        "perspective": "中国医疗卫生系统",
    }
    raw = json.dumps(analysis, ensure_ascii=False, separators=(",", ":")).encode()
    return analysis, raw


def uncertainty_fixture(analysis_raw: bytes) -> tuple[dict, bytes]:
    plan = {
        "schema_version": "0.1.0",
        "analysis_type": "decision_tree_uncertainty",
        "uncertainty_id": "golden-decision-tree-uncertainty",
        "analysis_input": {
            "path": "heor/decision-tree-plan.json",
            "content_sha256": hashlib.sha256(analysis_raw).hexdigest(),
        },
        "parameters": [
            {
                "id": "intervention-success-probability",
                "label": "Intervention success probability",
                "target": {
                    "kind": "branch_probability",
                    "strategy_id": "intervention",
                    "node_id": "intervention_outcome",
                    "branch_index": 0,
                    "complement_branch_index": 1,
                },
                "deterministic": {
                    "low": 0.5,
                    "high": 0.9,
                    "basis_ids": ["teaching-inputs"],
                    "rationale": "Synthetic teaching range.",
                },
                "probabilistic": {
                    "type": "uniform",
                    "low": 0.5,
                    "high": 0.9,
                    "basis_ids": ["teaching-inputs"],
                    "rationale": "Synthetic teaching distribution.",
                },
            }
        ],
        "probabilistic_analysis": {
            "iterations": 100,
            "seed": 20260731,
            "convergence": {
                "checkpoints": [50, 100],
                "max_probability_mcse": 0.1,
                "max_probability_drift": 0.1,
            },
            "independence_rationale": "Only one parameter is varied.",
            "omitted_uncertainties": [
                {
                    "item": "tree structure",
                    "rationale": "Structural alternatives are not represented by this PSA.",
                }
            ],
        },
    }
    raw = json.dumps(plan, ensure_ascii=False, separators=(",", ":")).encode()
    return plan, raw


class DecisionTreeUncertaintyTests(unittest.TestCase):
    def test_cli_runs_the_separate_hash_bound_contract(self) -> None:
        analysis, analysis_raw = analysis_fixture()
        plan, plan_raw = uncertainty_fixture(analysis_raw)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            analysis_path = root / "decision-tree-plan.json"
            uncertainty_path = root / "decision-tree-uncertainty-plan.json"
            analysis_path.write_bytes(analysis_raw)
            uncertainty_path.write_bytes(plan_raw)
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    main(
                        [
                            str(analysis_path),
                            "--decision-tree-uncertainty-plan",
                            str(uncertainty_path),
                        ]
                    ),
                    0,
                )
            result = json.loads(output.getvalue())
            self.assertEqual(result["analysis_type"], "decision_tree_uncertainty")
            self.assertEqual(result["analysis_input_sha256"], hashlib.sha256(analysis_raw).hexdigest())
            self.assertEqual(result["uncertainty_input_sha256"], hashlib.sha256(plan_raw).hexdigest())

    def test_dsa_matches_hand_calculation_and_psa_replays_exactly(self) -> None:
        analysis, analysis_raw = analysis_fixture()
        plan, plan_raw = uncertainty_fixture(analysis_raw)

        first = run_decision_tree_uncertainty(
            analysis, analysis_raw, plan, plan_raw
        )
        second = run_decision_tree_uncertainty(
            analysis, analysis_raw, plan, plan_raw
        )
        self.assertEqual(first, second)
        self.assertEqual(first["analysis_input_sha256"], hashlib.sha256(analysis_raw).hexdigest())
        self.assertEqual(first["uncertainty_input_sha256"], hashlib.sha256(plan_raw).hexdigest())

        dsa = first["deterministic_analysis"][0]
        low = dsa["low_result"]
        high = dsa["high_result"]
        self.assertTrue(math.isclose(low["strategies"]["intervention"]["total_cost"], 3600.0))
        self.assertTrue(math.isclose(low["strategies"]["intervention"]["total_qaly"], 0.625))
        self.assertTrue(math.isclose(high["strategies"]["intervention"]["total_cost"], 2480.0))
        self.assertTrue(math.isclose(high["strategies"]["intervention"]["total_qaly"], 0.805))
        self.assertTrue(math.isclose(high["pairwise_vs_baseline"]["intervention"]["icer"], 5440.0))

        psa = first["probabilistic_analysis"]
        self.assertEqual(psa["prng"], {"algorithm": "pcg32-xsh-rr", "version": "1", "seed": 20260731})
        self.assertEqual(len(psa["samples"]), 100)
        for sample in psa["samples"]:
            probability = sample["parameter_values"]["intervention-success-probability"]
            intervention = sample["strategies"]["intervention"]
            self.assertTrue(math.isclose(intervention["total_cost"], 5000.0 - 2800.0 * probability, abs_tol=1e-9))
            self.assertTrue(math.isclose(intervention["total_qaly"], 0.4 + 0.45 * probability, abs_tol=1e-12))
        counts = psa["optimal_counts"]
        self.assertEqual(sum(counts.values()) + psa["tie_count"], 100)
        self.assertTrue(math.isclose(sum(psa["optimal_probabilities"].values()) + psa["tie_probability"], 1.0))
        convergence = psa["convergence"]
        self.assertEqual(
            [checkpoint["iterations"] for checkpoint in convergence["checkpoints"]],
            [50, 100],
        )
        self.assertLessEqual(convergence["checkpoints"][-1]["max_probability_mcse"], 0.1)
        self.assertEqual(
            convergence["passed"],
            convergence["checkpoints"][-1]["max_probability_mcse"] <= 0.1
            and convergence["probability_drift"] <= 0.1,
        )

    def test_contract_fails_closed_for_stale_or_scientifically_unsafe_inputs(self) -> None:
        analysis, analysis_raw = analysis_fixture()
        plan, plan_raw = uncertainty_fixture(analysis_raw)

        cases: list[tuple[str, dict, bytes, dict]] = []
        stale = copy.deepcopy(plan)
        stale["analysis_input"]["content_sha256"] = "0" * 64
        cases.append(("stale", analysis, analysis_raw, stale))

        legacy = copy.deepcopy(analysis)
        legacy["schema_version"] = "0.1.0"
        legacy.pop("economic_basis")
        cases.append(("legacy", legacy, json.dumps(legacy).encode(), plan))

        bad_basis = copy.deepcopy(plan)
        bad_basis["parameters"][0]["probabilistic"]["basis_ids"] = ["missing"]
        cases.append(("basis", analysis, analysis_raw, bad_basis))

        bad_probability = copy.deepcopy(plan)
        bad_probability["parameters"][0]["deterministic"]["high"] = 1.1
        cases.append(("probability", analysis, analysis_raw, bad_probability))

        not_complementary = copy.deepcopy(plan)
        not_complementary["parameters"][0]["target"]["complement_branch_index"] = 0
        cases.append(("complement", analysis, analysis_raw, not_complementary))

        duplicate = copy.deepcopy(plan)
        duplicate["parameters"].append(copy.deepcopy(duplicate["parameters"][0]))
        duplicate["parameters"][1]["id"] = "duplicate-target"
        cases.append(("duplicate", analysis, analysis_raw, duplicate))

        missing_convergence = copy.deepcopy(plan)
        missing_convergence["probabilistic_analysis"].pop("convergence")
        cases.append(("missing-convergence", analysis, analysis_raw, missing_convergence))

        bad_checkpoints = copy.deepcopy(plan)
        bad_checkpoints["probabilistic_analysis"]["convergence"]["checkpoints"] = [100]
        cases.append(("bad-checkpoints", analysis, analysis_raw, bad_checkpoints))

        unsafe_seed = copy.deepcopy(plan)
        unsafe_seed["probabilistic_analysis"]["seed"] = 1 << 53
        cases.append(("unsafe-seed", analysis, analysis_raw, unsafe_seed))

        for label, current_analysis, current_raw, current_plan in cases:
            with self.subTest(label=label), self.assertRaises(ModelValidationError):
                run_decision_tree_uncertainty(
                    current_analysis,
                    current_raw,
                    current_plan,
                    json.dumps(current_plan, separators=(",", ":")).encode(),
                )

        changed_raw = analysis_raw + b"\n"
        with self.assertRaisesRegex(ModelValidationError, "content_sha256"):
            run_decision_tree_uncertainty(analysis, changed_raw, plan, plan_raw)


if __name__ == "__main__":
    unittest.main()
