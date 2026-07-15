from __future__ import annotations

import copy
from contextlib import redirect_stdout
import hashlib
import importlib.util
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from heor_core.model import ModelValidationError
from heor_core.cli import main as cli_main
from heor_core.uncertainty import run_uncertainty
from test_treatment_effect_duration import _apply_base_rows, event_disutility_inputs


ROOT = Path(__file__).resolve().parents[3]
PORTABLE_PATH = ROOT / "runtime/skills/core/heor-uncertainty-analysis/scripts/validate_uncertainty_plan.py"
PORTABLE_SPEC = importlib.util.spec_from_file_location("portable_component_uncertainty", PORTABLE_PATH)
assert PORTABLE_SPEC is not None and PORTABLE_SPEC.loader is not None
PORTABLE = importlib.util.module_from_spec(PORTABLE_SPEC)
PORTABLE_SPEC.loader.exec_module(PORTABLE)


def raw(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def valid_inputs() -> list:
    inputs = event_disutility_inputs()
    analysis, _, psm, _, curves, _, duration, _, cost, _, utility, _, event, _ = inputs
    analysis["uncertainty_analysis"] = {"path": "heor/uncertainty-plan.json"}
    analysis_raw = raw(analysis)
    psm["base_analysis"]["content_sha256"] = hashlib.sha256(analysis_raw).hexdigest()
    curves["base_analysis"]["content_sha256"] = hashlib.sha256(analysis_raw).hexdigest()
    curves_raw = raw(curves)
    psm["curve_materializations"]["content_sha256"] = hashlib.sha256(curves_raw).hexdigest()
    duration["base_analysis"]["content_sha256"] = hashlib.sha256(analysis_raw).hexdigest()
    duration["source_curve_materializations"]["content_sha256"] = hashlib.sha256(curves_raw).hexdigest()
    duration_raw = raw(duration)
    psm["treatment_effect_duration"]["content_sha256"] = hashlib.sha256(duration_raw).hexdigest()
    _apply_base_rows(psm, duration_raw, curves_raw)
    for artifact in (cost, utility, event):
        artifact["base_analysis"]["content_sha256"] = hashlib.sha256(analysis_raw).hexdigest()
    shared_basis = "quantity-source"
    cost["items"]["intervention-pf"]["unit_price"]["basis_ids"].append(shared_basis)
    cost_raw = raw(cost)
    psm["cost_input_normalization"]["content_sha256"] = hashlib.sha256(cost_raw).hexdigest()
    utility["items"]["intervention-progression-free"]["source_utility"]["basis_ids"].append(shared_basis)
    utility_raw = raw(utility)
    psm["utility_inputs"]["content_sha256"] = hashlib.sha256(utility_raw).hexdigest()
    event["base_utility_inputs"]["content_sha256"] = hashlib.sha256(utility_raw).hexdigest()
    event["items"]["intervention-infusion-reaction"]["occurrence"]["basis_ids"].append(shared_basis)
    event_raw = raw(event)
    psm["event_disutilities"]["content_sha256"] = hashlib.sha256(event_raw).hexdigest()
    psm_raw = raw(psm)
    bindings = {
        "partitioned_survival_plan": ("heor/partitioned-survival-plan.json", psm_raw),
        "curve_materializations": ("heor/survival-curve-materializations.json", curves_raw),
        "treatment_effect_duration": ("heor/treatment-effect-duration.json", duration_raw),
        "cost_input_normalization": ("heor/cost-input-normalization.json", cost_raw),
        "utility_inputs": ("heor/utility-inputs.json", utility_raw),
        "event_disutilities": ("heor/event-disutilities.json", event_raw),
    }
    parameters = [
        {
            "id": "drug-price",
            "label": "Intervention drug unit price",
            "artifact": "cost_input_normalization",
            "target": "/items/intervention-pf/unit_price/amount",
            "provenance_path": "cost_input_normalization.items.intervention-pf.unit_price.amount",
            "deterministic": {"low": 3000.0, "high": 5000.0, "rationale": "Reviewed price range."},
            "probabilistic": {"type": "uniform", "low": 3000.0, "high": 5000.0, "basis_ids": [shared_basis], "rationale": "Bounded reviewed price uncertainty."},
        },
        {
            "id": "pf-utility",
            "label": "Intervention progression-free utility",
            "artifact": "utility_inputs",
            "target": "/items/intervention-progression-free/source_utility/value",
            "provenance_path": "utility_inputs.items.intervention-progression-free.source_utility.value",
            "deterministic": {"low": 0.7, "high": 0.9, "rationale": "Reviewed utility range."},
            "probabilistic": {"type": "uniform", "low": 0.7, "high": 0.9, "basis_ids": [shared_basis], "rationale": "Bounded reviewed utility uncertainty."},
        },
        {
            "id": "infusion-frequency",
            "label": "Infusion reaction probability",
            "artifact": "event_disutilities",
            "target": "/items/intervention-infusion-reaction/occurrence/schedule/0",
            "provenance_path": "event_disutilities.items.intervention-infusion-reaction.occurrence.schedule.0",
            "deterministic": {"low": 0.1, "high": 0.3, "rationale": "Reviewed event-frequency range."},
            "probabilistic": {"type": "uniform", "low": 0.1, "high": 0.3, "basis_ids": [shared_basis], "rationale": "Bounded reviewed event-frequency uncertainty."},
        },
    ]
    uncertainty = {
        "schema_version": "0.13.0",
        "uncertainty_id": "component-uncertainty",
        "analysis_id": analysis["analysis_id"],
        "status": "ready_for_human_review",
        "base_analysis": {"path": "heor/analysis-plan.json", "content_sha256": hashlib.sha256(analysis_raw).hexdigest()},
        "partitioned_survival_inputs": {
            key: {"path": path, "content_sha256": hashlib.sha256(content).hexdigest()}
            for key, (path, content) in bindings.items()
        },
        "seed": 20260715,
        "parameters": parameters,
        "probabilistic_analysis": {
            "iterations": 1000,
            "decision_thresholds": {"values": [0.0, 100000.0], "rationale": "Primary decision range."},
            "convergence": {"checkpoints": [500, 1000], "max_probability_mcse": 0.1, "max_probability_drift": 0.1},
            "correlation_handling": {
                "groups": [{
                    "id": "shared-study-components",
                    "parameter_ids": ["drug-price", "pf-utility", "infusion-frequency"],
                    "scale": "latent_standard_normal",
                    "method": "gaussian_copula_cholesky",
                    "correlation_matrix": [[1.0, 0.25, 0.1], [0.25, 1.0, -0.1], [0.1, -0.1, 1.0]],
                    "basis_ids": [shared_basis],
                    "rationale": "Human-reviewed latent dependence from the linked joint evidence basis.",
                }],
                "independence_rationale": "All remaining component parameters are fixed or independently evidenced.",
                "known_omitted_correlations": [],
            },
            "omitted_parameters": [
                {"provenance_path": f"partitioned_survival.strategies.{strategy}.{endpoint}", "rationale": "Fixed curve outside component uncertainty."}
                for strategy in analysis["strategy_order"]
                for endpoint in ("pfs", "os")
            ],
        },
        "structural_scenarios": [{
            "id": "outcome-discount",
            "label": "Outcome discount scenario",
            "rationale": "Reviewed reference-case alternative.",
            "replacements": [{"target": "/discount_rates/outcomes", "value": 0.03}],
        }],
    }
    return [analysis, analysis_raw, uncertainty, raw(uncertainty), psm, psm_raw, curves, curves_raw, duration, duration_raw, cost, cost_raw, utility, utility_raw, event, event_raw]


class ComponentUncertaintyTests(unittest.TestCase):
    @staticmethod
    def execute(inputs: list) -> dict:
        return run_uncertainty(
            *inputs[:8],
            treatment_effect_duration=inputs[8],
            treatment_effect_duration_raw=inputs[9],
            cost_input_normalization=inputs[10],
            cost_input_normalization_raw=inputs[11],
            utility_inputs=inputs[12],
            utility_inputs_raw=inputs[13],
            event_disutilities=inputs[14],
            event_disutilities_raw=inputs[15],
        )

    def test_runs_reproducible_correlated_component_uncertainty(self) -> None:
        inputs = valid_inputs()
        result = self.execute(inputs)
        self.assertEqual(result, self.execute(inputs))
        self.assertEqual(result["schema_version"], "0.13.0")
        self.assertEqual(result["engine_version"], "0.14.0")
        self.assertEqual(result["calculation_classification"], "component_parameter_uncertainty")
        self.assertEqual(result["uncertainty_scope"], "cost_utility_event_components_only")
        self.assertEqual(len(result["probabilistic_analysis"]["samples"]), 1000)
        self.assertEqual(len(result["probabilistic_analysis"]["correlation_groups"]), 1)

    def test_rejects_stale_component_binding(self) -> None:
        inputs = valid_inputs()
        inputs[2]["partitioned_survival_inputs"]["event_disutilities"]["content_sha256"] = "0" * 64
        inputs[3] = raw(inputs[2])
        with self.assertRaisesRegex(ModelValidationError, "does not bind"):
            self.execute(inputs)

    def test_portable_validator_matches_component_boundary(self) -> None:
        inputs = valid_inputs()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            names = [
                "analysis.json", "uncertainty.json", "psm.json", "curves.json",
                "duration.json", "cost.json", "utility.json", "event.json",
            ]
            raws = [inputs[index] for index in (1, 3, 5, 7, 9, 11, 13, 15)]
            paths = [root / name for name in names]
            for path, content in zip(paths, raws):
                path.write_bytes(content)
            self.assertEqual(
                PORTABLE.validate(
                    paths[1], paths[0], paths[2], paths[3], None, None,
                    paths[4], paths[5], paths[6], paths[7],
                ),
                [],
            )
            invalid = copy.deepcopy(inputs[2])
            invalid["structural_scenarios"][0]["replacements"] = ["not-an-object"]
            paths[1].write_bytes(raw(invalid))
            self.assertIn(
                "component structural scenarios are invalid",
                PORTABLE.validate(
                    paths[1], paths[0], paths[2], paths[3], None, None,
                    paths[4], paths[5], paths[6], paths[7],
                ),
            )

    def test_cli_executes_component_contract(self) -> None:
        inputs = valid_inputs()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            names = [
                "analysis.json", "uncertainty.json", "psm.json", "curves.json",
                "duration.json", "cost.json", "utility.json", "event.json",
            ]
            raws = [inputs[index] for index in (1, 3, 5, 7, 9, 11, 13, 15)]
            paths = [root / name for name in names]
            for path, content in zip(paths, raws):
                path.write_bytes(content)
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    cli_main([
                        str(paths[0]),
                        "--uncertainty-plan", str(paths[1]),
                        "--partitioned-survival-plan", str(paths[2]),
                        "--survival-curve-materializations", str(paths[3]),
                        "--treatment-effect-duration", str(paths[4]),
                        "--cost-input-normalization", str(paths[5]),
                        "--utility-inputs", str(paths[6]),
                        "--event-disutilities", str(paths[7]),
                    ]),
                    0,
                )
            self.assertEqual(json.loads(output.getvalue())["schema_version"], "0.13.0")

    def test_extreme_lognormal_draw_fails_closed(self) -> None:
        inputs = valid_inputs()
        inputs[2]["parameters"][0]["probabilistic"] = {
            "type": "lognormal",
            "mu_log": 1000.0,
            "sigma_log": 0.1,
            "basis_ids": ["quantity-source"],
            "rationale": "Deliberately non-finite stress case.",
        }
        inputs[3] = raw(inputs[2])
        with self.assertRaisesRegex(ModelValidationError, "non-finite"):
            self.execute(inputs)

    def test_rejects_aggregate_or_out_of_domain_targets(self) -> None:
        for mutation in ("aggregate", "utility"):
            with self.subTest(mutation=mutation):
                inputs = valid_inputs()
                uncertainty = copy.deepcopy(inputs[2])
                parameter = uncertainty["parameters"][1]
                if mutation == "aggregate":
                    parameter["target"] = "/cycle_state_utilities/intervention/0/0"
                else:
                    parameter["deterministic"]["high"] = 1.1
                inputs[2] = uncertainty
                inputs[3] = raw(uncertainty)
                with self.assertRaises(ModelValidationError):
                    self.execute(inputs)


if __name__ == "__main__":
    unittest.main()
