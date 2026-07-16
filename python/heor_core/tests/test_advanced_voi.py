from __future__ import annotations

import copy
import hashlib
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from dataclasses import dataclass
from unittest.mock import patch

from heor_core.advanced_voi import (
    AdvancedVoiSpecification,
    EvaluationContext,
    _evppi,
    _evsi,
    _population,
    json_bytes,
    run_advanced_voi,
    standard_context,
    validate_context,
    verify_result_from_replay,
)
from heor_core.model import ModelValidationError
from heor_core.cli import main as cli_main
from heor_core.uncertainty import Pcg32, run_uncertainty
from test_relative_effect import analysis_payload, uncertainty_payload


@dataclass(frozen=True)
class FakeParameter:
    identifier: str
    distribution: dict[str, float | str]


class AdvancedVoiTests(unittest.TestCase):
    def inputs(self) -> tuple[dict, bytes, dict, bytes, dict, bytes, dict, bytes, EvaluationContext]:
        analysis = {
            "schema_version": "0.11.0",
            "analysis_id": "analysis-1",
            "willingness_to_pay": 100.0,
            "strategy_order": ["current", "new"],
        }
        analysis_raw = json_bytes(analysis)
        uncertainty = {
            "schema_version": "0.9.0",
            "uncertainty_id": "uncertainty-1",
        }
        uncertainty_raw = json_bytes(uncertainty)
        uncertainty_result = {
            "analysis_id": "analysis-1",
            "base_analysis_sha256": hashlib.sha256(analysis_raw).hexdigest(),
            "uncertainty_plan_sha256": hashlib.sha256(uncertainty_raw).hexdigest(),
            "probabilistic_analysis": {
                "convergence": {"passed": True},
                "decision_uncertainty": {
                    "threshold_results": [
                        {
                            "threshold": 100.0,
                            "per_person_evpi": 12.0,
                            "per_person_evpi_mcse": 0.5,
                        }
                    ]
                },
            },
        }
        uncertainty_result_raw = json_bytes(uncertainty_result)
        plan = {
            "schema_version": "0.1.0",
            "voi_id": "voi-1",
            "analysis_id": "analysis-1",
            "uncertainty_id": "uncertainty-1",
            "status": "ready_for_human_review",
            "bindings": {
                "analysis_plan": {
                    "path": "heor/analysis-plan.json",
                    "content_sha256": hashlib.sha256(analysis_raw).hexdigest(),
                },
                "uncertainty_plan": {
                    "path": "heor/uncertainty-plan.json",
                    "content_sha256": hashlib.sha256(uncertainty_raw).hexdigest(),
                },
                "uncertainty_result": {
                    "path": "heor/results/uncertainty.json",
                    "content_sha256": hashlib.sha256(uncertainty_result_raw).hexdigest(),
                },
            },
            "decision_threshold": 100.0,
            "population": {
                "annual_affected_population": [1000.0, 800.0, 600.0],
                "discount_rate": 0.03,
                "basis_ids": ["population-source"],
                "rationale": "Human-specified affected population and technology lifetime.",
            },
            "evppi": {
                "method": "nested_monte_carlo",
                "seed": 41,
                "outer_iterations": 100,
                "inner_iterations": 20,
                "parameter_groups": [
                    {
                        "id": "effect-group",
                        "label": "Treatment effect",
                        "parameter_ids": ["effect"],
                        "basis_ids": ["effect-source"],
                        "rationale": "Researchable effect parameter selected by the Human.",
                    },
                    {
                        "id": "cost-group",
                        "label": "Cost",
                        "parameter_ids": ["cost"],
                        "basis_ids": ["cost-source"],
                        "rationale": "Researchable cost parameter selected by the Human.",
                    },
                ],
            },
            "evsi": {
                "method": "normal_normal_nested_monte_carlo",
                "seed": 73,
                "target_group_id": "effect-group",
                "target_parameter_id": "effect",
                "sampling_standard_deviation": 0.4,
                "sample_sizes": [20, 50],
                "outer_iterations": 100,
                "inner_iterations": 20,
                "study_delay_years": 1,
                "study_cost": {
                    "fixed": 1000.0,
                    "per_participant": 25.0,
                    "currency": "CNY",
                    "price_year": 2026,
                    "basis_ids": ["study-cost-source"],
                    "rationale": "Human-specified study cost basis.",
                },
                "basis_ids": ["study-design-source"],
                "rationale": "One proposed Normal sample-mean study on the log-effect scale.",
            },
            "limitations": [
                "model_and_parameter_scope",
                "population_and_implementation_scope",
                "evppi_nested_monte_carlo_error",
                "evsi_normal_normal_study_model",
                "decision_authority_remains_human",
            ],
        }
        plan_raw = json_bytes(plan)
        effect = FakeParameter(
            "effect", {"type": "lognormal", "mu_log": 0.0, "sigma_log": 0.3}
        )
        cost = FakeParameter(
            "cost", {"type": "uniform", "low": -0.5, "high": 0.5}
        )

        def sample(rng: Pcg32):
            return (
                ((effect), pow(2.718281828459045, 0.3 * rng.normal())),
                ((cost), -0.5 + rng.uniform_open()),
            )

        def evaluate(values):
            by_id = {parameter.identifier: value for parameter, value in values}
            incremental_nmb = 20.0 * (by_id["effect"] - 1.0) - 8.0 * by_id["cost"]
            return [0.0, -incremental_nmb], [0.0, 0.0]

        context = EvaluationContext(
            ("current", "new"),
            (effect, cost),
            (),
            sample,
            evaluate,
            {
                "analysis_plan": hashlib.sha256(analysis_raw).hexdigest(),
                "uncertainty_plan": hashlib.sha256(uncertainty_raw).hexdigest(),
            },
        )
        return (
            plan,
            plan_raw,
            analysis,
            analysis_raw,
            uncertainty,
            uncertainty_raw,
            uncertainty_result,
            uncertainty_result_raw,
            context,
        )

    def run_case(self):
        return run_advanced_voi(*self.inputs())

    def test_deterministic_population_evpi_evppi_evsi_and_enbs(self) -> None:
        first = self.run_case()
        second = self.run_case()
        self.assertEqual(first, second)
        result = first["result"]
        self.assertAlmostEqual(
            result["population_evpi"]["population_evpi"],
            12.0 * result["population"]["effective_population"],
        )
        self.assertEqual([row["group_id"] for row in result["evppi"]], ["effect-group", "cost-group"])
        self.assertEqual([row["sample_size"] for row in result["evsi"]["designs"]], [20, 50])
        for row in result["evppi"]:
            self.assertGreaterEqual(row["per_person_evppi"], 0.0)
        for row in result["evsi"]["designs"]:
            self.assertAlmostEqual(
                row["expected_net_benefit_of_sampling"],
                row["population_evsi"] - row["study_cost"],
            )
        replay_raw = json_bytes(first["replay"])
        verify_result_from_replay(
            self.inputs()[0], result, first["replay"], replay_raw
        )

    def test_tampered_replay_result_fails_closed(self) -> None:
        output = self.run_case()
        output["result"]["evsi"]["designs"][0]["population_evsi"] += 1.0
        with self.assertRaisesRegex(ModelValidationError, "population_evsi"):
            verify_result_from_replay(
                self.inputs()[0],
                output["result"],
                output["replay"],
                json_bytes(output["replay"]),
            )

    def test_split_correlation_group_fails_closed(self) -> None:
        inputs = list(self.inputs())
        context = inputs[-1]
        context.correlation_parameter_groups = (frozenset({"effect", "cost"}),)
        with self.assertRaisesRegex(ModelValidationError, "splits a declared correlation group"):
            run_advanced_voi(*inputs)

    def test_unconverged_uncertainty_result_fails_closed(self) -> None:
        inputs = list(self.inputs())
        result = copy.deepcopy(inputs[6])
        result["probabilistic_analysis"]["convergence"]["passed"] = False
        result_raw = json_bytes(result)
        plan = copy.deepcopy(inputs[0])
        plan["bindings"]["uncertainty_result"]["content_sha256"] = hashlib.sha256(result_raw).hexdigest()
        inputs[0] = plan
        inputs[1] = json_bytes(plan)
        inputs[6] = result
        inputs[7] = result_raw
        with self.assertRaisesRegex(ModelValidationError, "requires a converged"):
            run_advanced_voi(*inputs)

    def test_standard_context_is_reachable_for_odds_ratio_lognormal_uncertainty(self) -> None:
        analysis = analysis_payload("odds_ratio")
        analysis_raw = json.dumps(analysis, sort_keys=True).encode()
        uncertainty = uncertainty_payload(analysis, analysis_raw, "odds_ratio")
        uncertainty_raw = json_bytes(uncertainty)
        context = standard_context(
            analysis,
            analysis_raw,
            uncertainty,
            uncertainty_raw,
        )
        self.assertEqual(context.parameters[0].identifier, "relative-effect")
        self.assertEqual(context.parameters[0].distribution["type"], "lognormal")

    def test_portable_context_validation_rejects_uniform_evsi_target(self) -> None:
        analysis = analysis_payload("odds_ratio")
        analysis_raw = json.dumps(analysis, sort_keys=True).encode()
        uncertainty = uncertainty_payload(analysis, analysis_raw, "odds_ratio")
        uncertainty["parameters"][0]["probabilistic"] = {
            "type": "uniform",
            "low": 0.3,
            "high": 0.8,
            "basis_ids": ["effect"],
            "rationale": "Valid OR uncertainty but invalid for this EVSI contract.",
        }
        uncertainty_raw = json_bytes(uncertainty)
        context = standard_context(analysis, analysis_raw, uncertainty, uncertainty_raw)
        plan = self.inputs()[0]
        plan["evppi"]["parameter_groups"] = [
            {
                "id": "effect-group",
                "label": "Treatment effect",
                "parameter_ids": ["relative-effect"],
                "basis_ids": ["effect-source"],
                "rationale": "Human-selected researchable parameter.",
            }
        ]
        plan["evsi"]["target_group_id"] = "effect-group"
        plan["evsi"]["target_parameter_id"] = "relative-effect"
        specification = AdvancedVoiSpecification(
            "voi-1",
            analysis["analysis_id"],
            uncertainty["uncertainty_id"],
            100000.0,
            _population(plan["population"]),
            _evppi(plan["evppi"]),
            _evsi(
                plan["evsi"], len(plan["population"]["annual_affected_population"])
            ),
        )
        with self.assertRaisesRegex(ModelValidationError, "Lognormal"):
            validate_context(specification, context)

    def test_cli_emits_exact_replay_bytes_and_result_for_standard_context(self) -> None:
        analysis = analysis_payload("odds_ratio")
        analysis_raw = json.dumps(analysis, sort_keys=True).encode()
        uncertainty = uncertainty_payload(analysis, analysis_raw, "odds_ratio")
        uncertainty_raw = json_bytes(uncertainty)
        uncertainty_result = run_uncertainty(
            analysis,
            analysis_raw,
            uncertainty,
            uncertainty_raw,
        )
        uncertainty_result_raw = json_bytes(uncertainty_result)
        plan = self.inputs()[0]
        plan["analysis_id"] = analysis["analysis_id"]
        plan["uncertainty_id"] = uncertainty["uncertainty_id"]
        plan["decision_threshold"] = analysis["willingness_to_pay"]
        plan["bindings"] = {
            "analysis_plan": {
                "path": "heor/analysis-plan.json",
                "content_sha256": hashlib.sha256(analysis_raw).hexdigest(),
            },
            "uncertainty_plan": {
                "path": "heor/uncertainty-plan.json",
                "content_sha256": hashlib.sha256(uncertainty_raw).hexdigest(),
            },
            "uncertainty_result": {
                "path": "heor/results/uncertainty.json",
                "content_sha256": hashlib.sha256(uncertainty_result_raw).hexdigest(),
            },
        }
        plan["evppi"]["parameter_groups"] = [{
            "id": "effect-group",
            "label": "Treatment effect",
            "parameter_ids": ["relative-effect"],
            "basis_ids": ["effect-source"],
            "rationale": "Human-selected researchable parameter.",
        }]
        plan["evsi"]["target_group_id"] = "effect-group"
        plan["evsi"]["target_parameter_id"] = "relative-effect"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = {
                "analysis": root / "analysis.json",
                "uncertainty": root / "uncertainty.json",
                "uncertainty_result": root / "uncertainty-result.json",
                "voi": root / "voi.json",
            }
            for key, raw in {
                "analysis": analysis_raw,
                "uncertainty": uncertainty_raw,
                "uncertainty_result": uncertainty_result_raw,
                "voi": json_bytes(plan),
            }.items():
                paths[key].write_bytes(raw)
            output = StringIO()
            with patch("sys.stdout", output):
                self.assertEqual(cli_main([
                    str(paths["analysis"]),
                    "--uncertainty-plan", str(paths["uncertainty"]),
                    "--advanced-voi-plan", str(paths["voi"]),
                    "--uncertainty-result", str(paths["uncertainty_result"]),
                ]), 0)
            wrapper = json.loads(output.getvalue())
            replay_raw = wrapper["replay_json"].encode()
            self.assertEqual(
                wrapper["result"]["replay_sha256"],
                hashlib.sha256(replay_raw).hexdigest(),
            )
            self.assertEqual(wrapper["result"]["evsi"]["target_parameter_id"], "relative-effect")


if __name__ == "__main__":
    unittest.main()
