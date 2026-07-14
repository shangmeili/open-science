from __future__ import annotations

import hashlib
import json
from math import exp
import unittest

from heor_core.model import ModelValidationError
from heor_core.partitioned_survival import run_partitioned_survival


CURVES = {
    ("comparator", "pfs"): ("exponential", {"rate_per_year": 0.5}),
    ("comparator", "os"): ("exponential", {"rate_per_year": 0.2}),
    ("intervention", "pfs"): (
        "weibull",
        {"shape": 1.2, "scale_years": 3.5},
    ),
    ("intervention", "os"): ("exponential", {"rate_per_year": 0.1}),
}


def analysis_payload() -> dict:
    return {
        "schema_version": "0.12.0",
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
                "state_costs": [1000.0, 3000.0, 0.0],
                "state_utilities": [0.8, 0.5, 0.0],
            },
            "intervention": {
                "name": "New treatment",
                "state_costs": [4000.0, 3000.0, 0.0],
                "state_utilities": [0.8, 0.5, 0.0],
            },
        },
    }


def survival(family: str, parameters: dict[str, float], time_years: float) -> float:
    cumulative_hazard = (
        parameters["rate_per_year"] * time_years
        if family == "exponential"
        else (time_years / parameters["scale_years"]) ** parameters["shape"]
    )
    return exp(-cumulative_hazard)


def review_binding(strategy_id: str, endpoint: str, family: str) -> dict:
    return {
        "path": f"heor/reviews/{strategy_id}-{endpoint}.json",
        "content_sha256": hashlib.sha256(
            f"review:{strategy_id}:{endpoint}".encode()
        ).hexdigest(),
        "target_path": f"partitioned_survival.strategies.{strategy_id}.{endpoint}",
        "selected_family": family,
    }


def fit_binding(strategy_id: str, endpoint: str) -> dict:
    return {
        "path": f"heor/fits/{strategy_id}-{endpoint}.json",
        "content_sha256": hashlib.sha256(
            f"fit:{strategy_id}:{endpoint}".encode()
        ).hexdigest(),
    }


def curve_basis(review: dict, fit: dict) -> list[str]:
    return [
        f"review-sha256:{review['content_sha256']}",
        f"fit-output-sha256:{fit['content_sha256']}",
        "evaluator:ai4heor-parametric-survival@0.1.0",
    ]


def psm_payload(analysis_raw: bytes) -> dict:
    conceptual_basis = {
        "rationale": "Declared and reviewable conceptual basis.",
        "basis_ids": ["basis-1"],
    }
    strategies: dict[str, dict] = {}
    for strategy_id in ("comparator", "intervention"):
        strategies[strategy_id] = {"curve_review_bindings": {}}
        for endpoint in ("pfs", "os"):
            family, parameters = CURVES[(strategy_id, endpoint)]
            review = review_binding(strategy_id, endpoint, family)
            fit = fit_binding(strategy_id, endpoint)
            basis_ids = curve_basis(review, fit)
            strategies[strategy_id]["curve_review_bindings"][endpoint] = review
            strategies[strategy_id][endpoint] = [
                {
                    "time_years": float(index),
                    "survival": survival(family, parameters, float(index)),
                    "basis_ids": basis_ids,
                }
                for index in range(3)
            ]
    return {
        "schema_version": "0.3.0",
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
            "forward_only_process": dict(conceptual_basis),
            "population_alignment": dict(conceptual_basis),
            "endpoint_alignment": dict(conceptual_basis),
            "time_origin_alignment": dict(conceptual_basis),
            "independent_extrapolation": dict(conceptual_basis),
        },
        "strategies": strategies,
        "validation_plan": {
            "face": ["Clinical review of state occupancy"],
            "internal": ["Recalculate occupancy and rewards"],
            "external": ["Compare with an independent implementation"],
        },
        "limitations": ["PFS and OS dependence is not modelled directly."],
    }


def materialization_payload(analysis_raw: bytes, plan: dict) -> dict:
    curves = []
    for strategy_id in ("comparator", "intervention"):
        for endpoint in ("pfs", "os"):
            family, parameters = CURVES[(strategy_id, endpoint)]
            review = plan["strategies"][strategy_id]["curve_review_bindings"][endpoint]
            fit = fit_binding(strategy_id, endpoint)
            curves.append(
                {
                    "target_path": review["target_path"],
                    "strategy_id": strategy_id,
                    "endpoint": endpoint,
                    "review_binding": review,
                    "fit_output_binding": fit,
                    "family": family,
                    "parameterization": (
                        "exponential_rate"
                        if family == "exponential"
                        else "weibull_shape_scale_aft"
                    ),
                    "parameters": parameters,
                    "basis_ids": curve_basis(review, fit),
                    "values": [
                        {
                            "time_years": float(index),
                            "survival": survival(
                                family, parameters, float(index)
                            ),
                        }
                        for index in range(3)
                    ],
                }
            )
    return {
        "schema_version": "0.1.0",
        "materialization_id": "psm-example-curves",
        "analysis_id": "psm-example",
        "psm_id": "psm-example-base-case",
        "status": "ready_for_human_review",
        "base_analysis": {
            "path": "heor/analysis-plan.json",
            "content_sha256": hashlib.sha256(analysis_raw).hexdigest(),
        },
        "time_origin": "randomization",
        "time_unit": "years",
        "evaluator": {
            "id": "ai4heor-parametric-survival",
            "version": "0.1.0",
        },
        "curves": curves,
        "limitations": [
            "Only exponential rate and Weibull AFT shape/scale are admitted."
        ],
    }


def valid_inputs() -> tuple[dict, bytes, dict, bytes, dict, bytes]:
    analysis = analysis_payload()
    analysis_raw = json.dumps(analysis, sort_keys=True).encode()
    plan = psm_payload(analysis_raw)
    materializations = materialization_payload(analysis_raw, plan)
    materializations_raw = json.dumps(materializations, sort_keys=True).encode()
    plan["curve_materializations"] = {
        "path": "heor/survival-curve-materializations.json",
        "content_sha256": hashlib.sha256(materializations_raw).hexdigest(),
    }
    plan_raw = json.dumps(plan, sort_keys=True).encode()
    return (
        analysis,
        analysis_raw,
        plan,
        plan_raw,
        materializations,
        materializations_raw,
    )


class PartitionedSurvivalTests(unittest.TestCase):
    def run_valid(self) -> dict:
        return run_partitioned_survival(*valid_inputs())

    def test_calculates_materialized_occupancy_and_economic_results(self) -> None:
        result = self.run_valid()
        self.assertEqual(result["schema_version"], "0.3.0")
        self.assertEqual(result["partitioned_survival_plan_schema_version"], "0.3.0")
        self.assertEqual(result["model_type"], "partitioned_survival")
        expected = [
            [1.0, 0.0, 0.0],
            [exp(-0.5), exp(-0.2) - exp(-0.5), 1.0 - exp(-0.2)],
            [exp(-1.0), exp(-0.4) - exp(-1.0), 1.0 - exp(-0.4)],
        ]
        for observed_row, expected_row in zip(
            result["strategies"]["comparator"]["occupancy"], expected
        ):
            for observed, expected_value in zip(observed_row, expected_row):
                self.assertAlmostEqual(observed, expected_value)
        expected_cost = 0.0
        expected_qaly = 0.0
        for start, end in zip(expected, expected[1:]):
            occupancy = [(left + right) / 2.0 for left, right in zip(start, end)]
            expected_cost += occupancy[0] * 1000.0 + occupancy[1] * 3000.0
            expected_qaly += occupancy[0] * 0.8 + occupancy[1] * 0.5
        self.assertAlmostEqual(
            result["strategies"]["comparator"]["total_cost"], expected_cost
        )
        self.assertAlmostEqual(
            result["strategies"]["comparator"]["total_qaly"], expected_qaly
        )
        self.assertIn("intervention", result["pairwise_vs_baseline"])

    def test_rejects_pfs_above_os_without_repair(self) -> None:
        inputs = list(valid_inputs())
        inputs[2]["strategies"]["intervention"]["pfs"][1]["survival"] = 0.95
        with self.assertRaisesRegex(ModelValidationError, "PFS exceeds OS"):
            run_partitioned_survival(*inputs)

    def test_rejects_increasing_survival(self) -> None:
        inputs = list(valid_inputs())
        inputs[2]["strategies"]["comparator"]["os"][2]["survival"] = 0.9
        with self.assertRaisesRegex(ModelValidationError, "non-increasing"):
            run_partitioned_survival(*inputs)

    def test_rejects_time_grid_mismatch(self) -> None:
        inputs = list(valid_inputs())
        inputs[2]["strategies"]["comparator"]["pfs"][1]["time_years"] = 0.5
        with self.assertRaisesRegex(ModelValidationError, "cycle grid"):
            run_partitioned_survival(*inputs)

    def test_rejects_stale_analysis_hash(self) -> None:
        inputs = list(valid_inputs())
        inputs[2]["base_analysis"]["content_sha256"] = "0" * 64
        with self.assertRaisesRegex(ModelValidationError, "does not match"):
            run_partitioned_survival(*inputs)

    def test_rejects_materialized_value_not_reproduced_by_parameters(self) -> None:
        inputs = list(valid_inputs())
        inputs[4]["curves"][0]["values"][1]["survival"] = 0.7
        inputs[5] = json.dumps(inputs[4], sort_keys=True).encode()
        inputs[2]["curve_materializations"]["content_sha256"] = hashlib.sha256(
            inputs[5]
        ).hexdigest()
        with self.assertRaisesRegex(ModelValidationError, "deterministic evaluation"):
            run_partitioned_survival(*inputs)

    def test_rejects_stale_materialization_hash(self) -> None:
        inputs = list(valid_inputs())
        inputs[4]["limitations"].append("changed")
        inputs[5] = json.dumps(inputs[4], sort_keys=True).encode()
        with self.assertRaisesRegex(ModelValidationError, "does not match"):
            run_partitioned_survival(*inputs)

    def test_rejects_wrong_parameterization_and_basis(self) -> None:
        inputs = list(valid_inputs())
        inputs[4]["curves"][0]["parameterization"] = "weibull_shape_scale_aft"
        inputs[5] = json.dumps(inputs[4], sort_keys=True).encode()
        inputs[2]["curve_materializations"]["content_sha256"] = hashlib.sha256(
            inputs[5]
        ).hexdigest()
        with self.assertRaisesRegex(ModelValidationError, "parameterization"):
            run_partitioned_survival(*inputs)

        inputs = list(valid_inputs())
        inputs[2]["strategies"]["comparator"]["pfs"][0]["basis_ids"] = ["free-text"]
        with self.assertRaisesRegex(ModelValidationError, "basis_ids"):
            run_partitioned_survival(*inputs)

    def test_rejects_curve_order_and_review_family_drift(self) -> None:
        inputs = list(valid_inputs())
        inputs[4]["curves"][0], inputs[4]["curves"][1] = (
            inputs[4]["curves"][1],
            inputs[4]["curves"][0],
        )
        inputs[5] = json.dumps(inputs[4], sort_keys=True).encode()
        inputs[2]["curve_materializations"]["content_sha256"] = hashlib.sha256(
            inputs[5]
        ).hexdigest()
        with self.assertRaisesRegex(ModelValidationError, "required target order"):
            run_partitioned_survival(*inputs)

        inputs = list(valid_inputs())
        inputs[2]["strategies"]["comparator"]["curve_review_bindings"]["pfs"][
            "selected_family"
        ] = "weibull"
        with self.assertRaisesRegex(ModelValidationError, "Human-selected"):
            run_partitioned_survival(*inputs)

    def test_rejects_transition_inputs_in_structure_neutral_plan(self) -> None:
        inputs = list(valid_inputs())
        inputs[0]["strategies"]["comparator"]["transition_matrix"] = [
            [1.0, 0.0, 0.0],
            [0.0, 1.0, 0.0],
            [0.0, 0.0, 1.0],
        ]
        inputs[1] = json.dumps(inputs[0], sort_keys=True).encode()
        with self.assertRaisesRegex(ModelValidationError, "transition structure is forbidden"):
            run_partitioned_survival(*inputs)

    def test_rejects_missing_or_invalid_economic_rewards(self) -> None:
        inputs = list(valid_inputs())
        inputs[0]["strategies"]["intervention"]["state_costs"] = [4000.0, -1.0, 0.0]
        inputs[1] = json.dumps(inputs[0], sort_keys=True).encode()
        with self.assertRaisesRegex(ModelValidationError, "state_costs must be non-negative"):
            run_partitioned_survival(*inputs)

    def test_legacy_schema_02_remains_calculable(self) -> None:
        analysis, _, plan, _, materializations, _ = valid_inputs()
        analysis["schema_version"] = "0.11.0"
        for strategy in analysis["strategies"].values():
            strategy["initial_distribution"] = [1.0, 0.0, 0.0]
            strategy["transition_matrix"] = [
                [0.8, 0.15, 0.05],
                [0.0, 0.75, 0.25],
                [0.0, 0.0, 1.0],
            ]
        analysis_raw = json.dumps(analysis, sort_keys=True).encode()
        analysis_hash = hashlib.sha256(analysis_raw).hexdigest()
        plan["schema_version"] = "0.2.0"
        plan["base_analysis"]["content_sha256"] = analysis_hash
        materializations["base_analysis"]["content_sha256"] = analysis_hash
        materializations_raw = json.dumps(materializations, sort_keys=True).encode()
        plan["curve_materializations"]["content_sha256"] = hashlib.sha256(
            materializations_raw
        ).hexdigest()
        plan_raw = json.dumps(plan, sort_keys=True).encode()
        result = run_partitioned_survival(
            analysis,
            analysis_raw,
            plan,
            plan_raw,
            materializations,
            materializations_raw,
        )
        self.assertEqual(result["partitioned_survival_plan_schema_version"], "0.2.0")
        self.assertTrue(any("Legacy schema 0.2.0" in item for item in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
