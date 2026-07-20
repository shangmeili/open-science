from __future__ import annotations

import copy
import hashlib
import json
import unittest

from heor_core.model import ModelValidationError
from heor_core.uncertainty import run_uncertainty
from test_partitioned_survival import (
    analysis_payload,
    materialization_payload,
    psm_payload,
)


def valid_inputs() -> tuple[dict, bytes, dict, bytes, dict, bytes, dict, bytes]:
    analysis = analysis_payload()
    analysis["uncertainty_analysis"] = {"path": "heor/uncertainty-plan.json"}
    paths = [
        "strategies.intervention.state_costs",
        "strategies.comparator.state_utilities",
    ]
    analysis["methodology"] = {
        "uncertainty_analysis": {
            "deterministic": {"planned": True, "input_paths": paths},
            "probabilistic": {
                "planned": True,
                "input_paths": paths,
                "iterations": 1000,
            },
            "structural_scenarios": ["discount-costs"],
        }
    }
    analysis["input_provenance"] = [
        {
            "path": paths[0],
            "uncertainty_status": "distribution_available",
            "source_ids": [],
            "extraction_ids": [],
            "assumption_ids": ["assumption-cost"],
        },
        {
            "path": paths[1],
            "uncertainty_status": "distribution_available",
            "source_ids": [],
            "extraction_ids": [],
            "assumption_ids": ["assumption-utility"],
        },
    ]
    analysis_raw = json.dumps(analysis, sort_keys=True).encode()
    psm = psm_payload(analysis_raw)
    materializations = materialization_payload(analysis_raw, psm)
    materializations_raw = json.dumps(materializations, sort_keys=True).encode()
    psm["curve_materializations"] = {
        "path": "heor/survival-curve-materializations.json",
        "content_sha256": hashlib.sha256(materializations_raw).hexdigest(),
    }
    psm_raw = json.dumps(psm, sort_keys=True).encode()
    uncertainty = {
        "schema_version": "0.11.0",
        "uncertainty_id": "psm-economic-only",
        "analysis_id": analysis["analysis_id"],
        "status": "ready_for_human_review",
        "base_analysis": {
            "path": "heor/analysis-plan.json",
            "content_sha256": hashlib.sha256(analysis_raw).hexdigest(),
        },
        "partitioned_survival_inputs": {
            "plan": {
                "path": "heor/partitioned-survival-plan.json",
                "content_sha256": hashlib.sha256(psm_raw).hexdigest(),
            },
            "curve_materializations": {
                "path": "heor/survival-curve-materializations.json",
                "content_sha256": hashlib.sha256(materializations_raw).hexdigest(),
            },
        },
        "seed": 20260715,
        "parameters": [
            {
                "id": "intervention-pf-cost",
                "label": "Intervention progression-free cost",
                "target": "/strategies/intervention/state_costs/0",
                "provenance_path": paths[0],
                "deterministic": {
                    "low": 3000.0,
                    "high": 5000.0,
                    "rationale": "Reviewable range.",
                },
                "probabilistic": {
                    "type": "gamma",
                    "shape": 16.0,
                    "scale": 250.0,
                    "basis_ids": ["assumption-cost"],
                    "rationale": "Positive cost distribution.",
                },
            },
            {
                "id": "comparator-pf-utility",
                "label": "Comparator progression-free utility",
                "target": "/strategies/comparator/state_utilities/0",
                "provenance_path": paths[1],
                "deterministic": {
                    "low": 0.7,
                    "high": 0.9,
                    "rationale": "Reviewable range.",
                },
                "probabilistic": {
                    "type": "beta",
                    "alpha": 80.0,
                    "beta": 20.0,
                    "basis_ids": ["assumption-utility"],
                    "rationale": "Bounded utility distribution.",
                },
            },
        ],
        "probabilistic_analysis": {
            "iterations": 1000,
            "decision_thresholds": {
                "values": [50000.0, 100000.0],
                "rationale": "Includes the primary threshold.",
            },
            "convergence": {
                "checkpoints": [500, 1000],
                "max_probability_mcse": 0.1,
                "max_probability_drift": 0.1,
            },
            "correlation_handling": {
                "groups": [],
                "independence_rationale": "No supported dependence evidence is available for these two economic inputs.",
                "known_omitted_correlations": [],
            },
            "omitted_parameters": [
                {
                    "provenance_path": f"partitioned_survival.strategies.{strategy_id}.{endpoint}",
                    "rationale": "Fixed curve; joint survival uncertainty is not represented in this partial analysis.",
                }
                for strategy_id in analysis["strategy_order"]
                for endpoint in ("pfs", "os")
            ],
        },
        "structural_scenarios": [
            {
                "id": "discount-costs",
                "label": "Cost discount scenario",
                "rationale": "Review an alternative cost discount rate.",
                "replacements": [
                    {"target": "/discount_rates/costs", "value": 0.03}
                ],
            }
        ],
    }
    uncertainty_raw = json.dumps(uncertainty, sort_keys=True).encode()
    return (
        analysis,
        analysis_raw,
        uncertainty,
        uncertainty_raw,
        psm,
        psm_raw,
        materializations,
        materializations_raw,
    )


class PartitionedSurvivalUncertaintyTests(unittest.TestCase):
    def test_runs_reproducible_economic_only_partial_uncertainty(self) -> None:
        inputs = valid_inputs()
        result = run_uncertainty(*inputs)
        repeated = run_uncertainty(*inputs)
        self.assertEqual(result, repeated)
        self.assertEqual(result["schema_version"], "0.11.0")
        self.assertEqual(
            result["calculation_classification"], "partial_parameter_uncertainty"
        )
        self.assertEqual(result["uncertainty_scope"], "economic_inputs_only")
        self.assertEqual(result["probabilistic_analysis"]["iterations"], 1000)
        self.assertEqual(len(result["probabilistic_analysis"]["samples"]), 1000)
        self.assertIn("partitioned_survival_plan_sha256", result)
        self.assertTrue(any("block release-ready" in item for item in result["limitations"]))
        self.assertFalse(
            any("event-rate parameters" in item for item in result["limitations"])
        )

    def test_rejects_a_non_economic_parameter_target(self) -> None:
        inputs = list(valid_inputs())
        uncertainty = copy.deepcopy(inputs[2])
        uncertainty["parameters"][0]["target"] = "/cycles"
        inputs[2] = uncertainty
        inputs[3] = json.dumps(uncertainty, sort_keys=True).encode()
        with self.assertRaisesRegex(ModelValidationError, "only exact state_costs"):
            run_uncertainty(*inputs)

    def test_rejects_an_unbounded_utility_distribution(self) -> None:
        inputs = list(valid_inputs())
        uncertainty = copy.deepcopy(inputs[2])
        parameter = uncertainty["parameters"][1]
        parameter["probabilistic"] = {
            "type": "gamma",
            "shape": 10.0,
            "scale": 0.08,
            "basis_ids": ["assumption-utility"],
            "rationale": "Invalid because gamma can exceed one.",
        }
        inputs[2] = uncertainty
        inputs[3] = json.dumps(uncertainty, sort_keys=True).encode()
        with self.assertRaisesRegex(ModelValidationError, "must use beta or bounded uniform"):
            run_uncertainty(*inputs)

    def test_rejects_missing_survival_curve_omission(self) -> None:
        inputs = list(valid_inputs())
        uncertainty = copy.deepcopy(inputs[2])
        uncertainty["probabilistic_analysis"]["omitted_parameters"].pop()
        inputs[2] = uncertainty
        inputs[3] = json.dumps(uncertainty, sort_keys=True).encode()
        with self.assertRaisesRegex(ModelValidationError, "explicitly omit every fixed curve"):
            run_uncertainty(*inputs)

    def test_rejects_stale_partitioned_survival_binding(self) -> None:
        inputs = list(valid_inputs())
        uncertainty = copy.deepcopy(inputs[2])
        uncertainty["partitioned_survival_inputs"]["plan"]["content_sha256"] = "0" * 64
        inputs[2] = uncertainty
        inputs[3] = json.dumps(uncertainty, sort_keys=True).encode()
        with self.assertRaisesRegex(ModelValidationError, "does not match the current bytes"):
            run_uncertainty(*inputs)


if __name__ == "__main__":
    unittest.main()
