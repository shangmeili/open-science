from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from heor_core.model import ModelValidationError
from heor_core.partitioned_survival import run_partitioned_survival


def analysis_payload() -> dict:
    return {
        "schema_version": "0.11.0",
        "analysis_id": "psm-example",
        "economic_basis": {"currency": "CNY", "price_year": 2026},
        "reference_case": {"id": "CN-2020-current", "status": "current"},
        "states": ["progression_free", "progressed", "dead"],
        "cycles": 2,
        "cycle_length_years": 1.0,
        "discount_rates": {"costs": 0.0, "outcomes": 0.0},
        "half_cycle_correction": True,
        "willingness_to_pay": 100000.0,
        "strategy_order": ["comparator", "intervention"],
        "baseline_strategy_id": "comparator",
        "partitioned_survival_analysis": {
            "path": "heor/partitioned-survival-plan.json"
        },
        "strategies": {
            "comparator": {
                "name": "Standard care",
                "initial_distribution": [1.0, 0.0, 0.0],
                "transition_matrix": [
                    [0.7, 0.2, 0.1],
                    [0.0, 0.7, 0.3],
                    [0.0, 0.0, 1.0],
                ],
                "state_costs": [1000.0, 3000.0, 0.0],
                "state_utilities": [0.8, 0.5, 0.0],
            },
            "intervention": {
                "name": "New treatment",
                "initial_distribution": [1.0, 0.0, 0.0],
                "transition_matrix": [
                    [0.8, 0.15, 0.05],
                    [0.0, 0.75, 0.25],
                    [0.0, 0.0, 1.0],
                ],
                "state_costs": [4000.0, 3000.0, 0.0],
                "state_utilities": [0.8, 0.5, 0.0],
            },
        },
    }


def psm_payload(analysis_raw: bytes) -> dict:
    binding_hash = "a" * 64
    basis = {
        "rationale": "Declared and reviewable conceptual basis.",
        "basis_ids": ["basis-1"],
    }
    rows = {
        "comparator": {
            "pfs": [1.0, 0.6, 0.3],
            "os": [1.0, 0.8, 0.5],
        },
        "intervention": {
            "pfs": [1.0, 0.7, 0.4],
            "os": [1.0, 0.9, 0.65],
        },
    }
    strategies = {}
    for strategy_id, curves in rows.items():
        strategies[strategy_id] = {
            endpoint: [
                {
                    "time_years": float(index),
                    "survival": survival,
                    "basis_ids": [f"{strategy_id}-{endpoint}-{index}"],
                }
                for index, survival in enumerate(values)
            ]
            for endpoint, values in curves.items()
        }
        strategies[strategy_id]["curve_review_bindings"] = {
            "pfs": {
                "path": f"heor/reviews/{strategy_id}-pfs.json",
                "content_sha256": binding_hash,
                "target_path": f"partitioned_survival.strategies.{strategy_id}.pfs",
                "selected_family": "weibull",
            },
            "os": {
                "path": f"heor/reviews/{strategy_id}-os.json",
                "content_sha256": binding_hash,
                "target_path": f"partitioned_survival.strategies.{strategy_id}.os",
                "selected_family": "weibull",
            },
        }
    return {
        "schema_version": "0.1.0",
        "psm_id": "psm-example-base-case",
        "analysis_id": "psm-example",
        "status": "ready_for_human_review",
        "base_analysis": {
            "path": "heor/analysis-plan.json",
            "content_sha256": hashlib.sha256(analysis_raw).hexdigest(),
        },
        "time_origin": "randomization",
        "model_structure": {
            "type": "partitioned_survival",
            "state_order": ["progression_free", "progressed", "dead"],
            "forward_only_disease_process": True,
        },
        "conceptual_basis": {
            "forward_only_process": dict(basis),
            "population_alignment": dict(basis),
            "endpoint_alignment": dict(basis),
            "time_origin_alignment": dict(basis),
            "independent_extrapolation": dict(basis),
        },
        "strategies": strategies,
        "validation_plan": {
            "face": ["Clinical review of state occupancy"],
            "internal": ["Recalculate occupancy and rewards"],
            "external": ["Compare with an independent implementation"],
        },
        "limitations": ["PFS and OS dependence is not modelled directly."],
    }


class PartitionedSurvivalTests(unittest.TestCase):
    def run_valid(self) -> dict:
        analysis = analysis_payload()
        analysis_raw = json.dumps(analysis, sort_keys=True).encode()
        plan = psm_payload(analysis_raw)
        plan_raw = json.dumps(plan, sort_keys=True).encode()
        return run_partitioned_survival(analysis, analysis_raw, plan, plan_raw)

    def test_calculates_coherent_occupancy_and_economic_results(self) -> None:
        result = self.run_valid()
        self.assertEqual(result["model_type"], "partitioned_survival")
        expected = [[1.0, 0.0, 0.0], [0.6, 0.2, 0.2], [0.3, 0.2, 0.5]]
        for observed_row, expected_row in zip(
            result["strategies"]["comparator"]["occupancy"], expected
        ):
            for observed, expected_value in zip(observed_row, expected_row):
                self.assertAlmostEqual(observed, expected_value)
        self.assertAlmostEqual(
            result["strategies"]["comparator"]["total_cost"], 2150.0
        )
        self.assertAlmostEqual(
            result["strategies"]["comparator"]["total_qaly"], 1.15
        )
        self.assertEqual(
            result["strategies"]["comparator"]["transition_mode"],
            "partitioned_survival",
        )
        self.assertIn("intervention", result["pairwise_vs_baseline"])

    def test_rejects_pfs_above_os_without_repair(self) -> None:
        analysis = analysis_payload()
        analysis_raw = json.dumps(analysis, sort_keys=True).encode()
        plan = psm_payload(analysis_raw)
        plan["strategies"]["intervention"]["pfs"][2]["survival"] = 0.7
        with self.assertRaisesRegex(ModelValidationError, "PFS exceeds OS"):
            run_partitioned_survival(analysis, analysis_raw, plan, b"{}")

    def test_rejects_increasing_survival(self) -> None:
        analysis = analysis_payload()
        analysis_raw = json.dumps(analysis, sort_keys=True).encode()
        plan = psm_payload(analysis_raw)
        plan["strategies"]["comparator"]["os"][2]["survival"] = 0.9
        with self.assertRaisesRegex(ModelValidationError, "non-increasing"):
            run_partitioned_survival(analysis, analysis_raw, plan, b"{}")

    def test_rejects_time_grid_mismatch(self) -> None:
        analysis = analysis_payload()
        analysis_raw = json.dumps(analysis, sort_keys=True).encode()
        plan = psm_payload(analysis_raw)
        plan["strategies"]["comparator"]["pfs"][1]["time_years"] = 0.5
        with self.assertRaisesRegex(ModelValidationError, "cycle grid"):
            run_partitioned_survival(analysis, analysis_raw, plan, b"{}")

    def test_rejects_stale_analysis_hash(self) -> None:
        analysis = analysis_payload()
        analysis_raw = json.dumps(analysis, sort_keys=True).encode()
        plan = psm_payload(analysis_raw)
        plan["base_analysis"]["content_sha256"] = "0" * 64
        with self.assertRaisesRegex(ModelValidationError, "does not match"):
            run_partitioned_survival(analysis, analysis_raw, plan, b"{}")

    def test_portable_skill_validator_checks_exact_review_bytes(self) -> None:
        analysis = analysis_payload()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "heor" / "reviews").mkdir(parents=True)
            for strategy_id in ("comparator", "intervention"):
                for endpoint in ("pfs", "os"):
                    review_raw = json.dumps(
                        {
                            "schema_version": "0.2.0",
                            "status": "ready_for_human_review",
                            "analysis_target": {
                                "analysis_id": "psm-example",
                                "path": f"partitioned_survival.strategies.{strategy_id}.{endpoint}",
                            },
                            "context": {
                                "endpoint": endpoint.upper(),
                                "time_origin": "randomization",
                                "time_unit": "years",
                            },
                        },
                        sort_keys=True,
                    ).encode()
                    review_path = (
                        root / "heor" / "reviews" / f"{strategy_id}-{endpoint}.json"
                    )
                    review_path.write_bytes(review_raw)
            analysis_raw = json.dumps(analysis, sort_keys=True).encode()
            plan = psm_payload(analysis_raw)
            for strategy in plan["strategies"].values():
                for binding in strategy["curve_review_bindings"].values():
                    binding["content_sha256"] = hashlib.sha256(
                        (root / binding["path"]).read_bytes()
                    ).hexdigest()
            analysis_path = root / "heor" / "analysis-plan.json"
            plan_path = root / "heor" / "partitioned-survival-plan.json"
            analysis_path.write_bytes(analysis_raw)
            plan_path.write_text(json.dumps(plan, sort_keys=True))
            validator = (
                Path(__file__).resolve().parents[3]
                / "runtime"
                / "skills"
                / "core"
                / "heor-partitioned-survival"
                / "scripts"
                / "validate_partitioned_survival.py"
            )
            valid = subprocess.run(
                [
                    sys.executable,
                    str(validator),
                    str(analysis_path),
                    str(plan_path),
                    "--workspace-root",
                    str(root),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(valid.returncode, 0, valid.stdout + valid.stderr)
            (root / "heor" / "reviews" / "comparator-pfs.json").write_bytes(b"changed")
            stale = subprocess.run(
                [
                    sys.executable,
                    str(validator),
                    str(analysis_path),
                    str(plan_path),
                    "--workspace-root",
                    str(root),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(stale.returncode, 0)
            self.assertIn("does not match the artifact bytes", stale.stdout)

            binding = plan["strategies"]["comparator"]["curve_review_bindings"][
                "pfs"
            ]
            review_path = root / binding["path"]
            mismatched_review = {
                "schema_version": "0.2.0",
                "status": "ready_for_human_review",
                "analysis_target": {
                    "analysis_id": "psm-example",
                    "path": binding["target_path"],
                },
                "context": {
                    "endpoint": "OS",
                    "time_origin": "randomization",
                    "time_unit": "years",
                },
            }
            review_path.write_text(json.dumps(mismatched_review, sort_keys=True))
            binding["content_sha256"] = hashlib.sha256(review_path.read_bytes()).hexdigest()
            plan_path.write_text(json.dumps(plan, sort_keys=True))
            semantic_mismatch = subprocess.run(
                [
                    sys.executable,
                    str(validator),
                    str(analysis_path),
                    str(plan_path),
                    "--workspace-root",
                    str(root),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(semantic_mismatch.returncode, 0)
            self.assertIn("review endpoint does not match PFS", semantic_mismatch.stdout)


if __name__ == "__main__":
    unittest.main()
