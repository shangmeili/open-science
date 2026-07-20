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

from heor_core.cli import main as cli_main
from heor_core.model import ModelValidationError
from heor_core.uncertainty import run_uncertainty
from test_partitioned_survival_uncertainty import valid_inputs as valid_partial_inputs


ROOT = Path(__file__).resolve().parents[3]
VALIDATOR_PATH = (
    ROOT
    / "runtime/skills/core/heor-joint-survival-uncertainty/scripts"
    / "validate_joint_survival_uncertainty.py"
)
SPEC = importlib.util.spec_from_file_location("portable_joint_survival", VALIDATOR_PATH)
assert SPEC and SPEC.loader
PORTABLE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PORTABLE)
UNCERTAINTY_VALIDATOR_PATH = (
    ROOT
    / "runtime/skills/core/heor-uncertainty-analysis/scripts"
    / "validate_uncertainty_plan.py"
)
UNCERTAINTY_SPEC = importlib.util.spec_from_file_location(
    "portable_uncertainty", UNCERTAINTY_VALIDATOR_PATH
)
assert UNCERTAINTY_SPEC and UNCERTAINTY_SPEC.loader
UNCERTAINTY_PORTABLE = importlib.util.module_from_spec(UNCERTAINTY_SPEC)
UNCERTAINTY_SPEC.loader.exec_module(UNCERTAINTY_PORTABLE)


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


def _draw_rows(psm: dict, draw_count: int = 1000, vary: bool = True) -> bytes:
    curve_order = [
        (strategy_id, endpoint)
        for strategy_id in ("comparator", "intervention")
        for endpoint in ("pfs", "os")
    ]
    rows = []
    for draw_index in range(1, draw_count + 1):
        shared_factor = 1.0 + (((draw_index - 1) % 21) - 10) / 200.0 if vary else 1.0
        curves = []
        for strategy_id, endpoint in curve_order:
            values = [
                point["survival"]
                for point in psm["strategies"][strategy_id][endpoint]
            ]
            factor = shared_factor + (0.05 if endpoint == "pfs" else 0.0)
            curves.append([value**factor for value in values])
        rows.append(
            json.dumps(
                {"draw_index": draw_index, "curves": curves},
                separators=(",", ":"),
            )
        )
    return ("\n".join(rows) + "\n").encode()


def valid_inputs(vary: bool = True) -> list:
    inputs = list(valid_partial_inputs())
    analysis, analysis_raw, uncertainty, _, psm, psm_raw, materializations, materializations_raw = inputs
    uncertainty = copy.deepcopy(uncertainty)
    uncertainty["schema_version"] = "0.12.0"
    uncertainty["uncertainty_id"] = "psm-joint-survival"
    uncertainty["probabilistic_analysis"]["omitted_parameters"] = [
        {
            "provenance_path": path,
            "rationale": "Explicit structural uncertainty outside the admitted joint curve draws.",
        }
        for path in (
            "partitioned_survival.structural.curve_family_selection",
            "partitioned_survival.structural.extrapolation_assumptions",
            "partitioned_survival.structural.treatment_effect_duration",
        )
    ]
    draws_raw = _draw_rows(psm, vary=vary)
    manifest = {
        "schema_version": "0.1.0",
        "survival_uncertainty_id": "joint-survival-draws",
        "analysis_id": analysis["analysis_id"],
        "psm_id": psm["psm_id"],
        "status": "ready_for_human_review",
        "base_analysis": {
            "path": "heor/analysis-plan.json",
            "content_sha256": hashlib.sha256(analysis_raw).hexdigest(),
        },
        "partitioned_survival_plan": {
            "path": "heor/partitioned-survival-plan.json",
            "content_sha256": hashlib.sha256(psm_raw).hexdigest(),
        },
        "curve_materializations": {
            "path": "heor/survival-curve-materializations.json",
            "content_sha256": hashlib.sha256(materializations_raw).hexdigest(),
        },
        "draw_file": {
            "path": "heor/joint-survival-draws.jsonl",
            "content_sha256": hashlib.sha256(draws_raw).hexdigest(),
            "format": "ai4heor-joint-survival-draws-jsonl@0.1.0",
            "draw_count": 1000,
        },
        "curve_order": [
            f"partitioned_survival.strategies.{strategy_id}.{endpoint}"
            for strategy_id in analysis["strategy_order"]
            for endpoint in ("pfs", "os")
        ],
        "time_grid_years": [0.0, 1.0, 2.0],
        "generation": {
            "method": "joint_posterior",
            "sampling_unit": "joint_draw_across_all_curves",
            "independent_endpoint_sampling": False,
            "dependence_scope": [
                "within_strategy_pfs_os",
                "between_strategy_curves",
            ],
            "source_artifact_bindings": [
                {
                    "path": "heor/fits/joint-posterior.json",
                    "content_sha256": hashlib.sha256(b"joint posterior").hexdigest(),
                    "role": "Joint posterior draws preserving all curve dependence.",
                }
            ],
            "rationale": "One posterior row jointly supplies all strategy PFS and OS curves.",
        },
        "limitations": [
            "Curve-family selection and extrapolation assumptions remain structural uncertainty."
        ],
    }
    manifest_raw = _json_bytes(manifest)
    uncertainty["joint_survival_inputs"] = {
        "manifest": {
            "path": "heor/joint-survival-uncertainty.json",
            "content_sha256": hashlib.sha256(manifest_raw).hexdigest(),
        },
        "draws": {
            "path": "heor/joint-survival-draws.jsonl",
            "content_sha256": hashlib.sha256(draws_raw).hexdigest(),
        },
    }
    uncertainty_raw = _json_bytes(uncertainty)
    return [
        analysis,
        analysis_raw,
        uncertainty,
        uncertainty_raw,
        psm,
        psm_raw,
        materializations,
        materializations_raw,
        manifest,
        manifest_raw,
        draws_raw,
    ]


def _rebind_manifest_and_uncertainty(inputs: list) -> None:
    manifest_raw = _json_bytes(inputs[8])
    inputs[9] = manifest_raw
    inputs[2]["joint_survival_inputs"]["manifest"]["content_sha256"] = hashlib.sha256(
        manifest_raw
    ).hexdigest()
    inputs[2]["joint_survival_inputs"]["draws"]["content_sha256"] = hashlib.sha256(
        inputs[10]
    ).hexdigest()
    inputs[3] = _json_bytes(inputs[2])


class JointSurvivalUncertaintyTests(unittest.TestCase):
    def test_runs_reproducibly_and_consumes_joint_curve_rows(self) -> None:
        inputs = valid_inputs()
        result = run_uncertainty(*inputs)
        self.assertEqual(result, run_uncertainty(*inputs))
        self.assertEqual(result["schema_version"], "0.12.0")
        self.assertEqual(result["engine_version"], "0.13.0")
        self.assertEqual(
            result["calculation_classification"],
            "joint_curve_draw_parameter_uncertainty",
        )
        self.assertEqual(
            result["uncertainty_scope"],
            "joint_survival_curves_and_economic_inputs",
        )
        fixed = run_uncertainty(*valid_inputs(vary=False))
        self.assertNotEqual(
            result["probabilistic_analysis"]["samples"],
            fixed["probabilistic_analysis"]["samples"],
        )
        self.assertTrue(any("source posterior" in item for item in result["limitations"]))

    def test_rejects_independent_endpoint_sampling(self) -> None:
        inputs = valid_inputs()
        inputs[8]["generation"]["independent_endpoint_sampling"] = True
        _rebind_manifest_and_uncertainty(inputs)
        with self.assertRaisesRegex(ModelValidationError, "independent PFS/OS sampling"):
            run_uncertainty(*inputs)

    def test_rejects_pfs_above_os(self) -> None:
        inputs = valid_inputs()
        rows = inputs[10].splitlines()
        first = json.loads(rows[0])
        first["curves"][0][1] = 0.99
        rows[0] = json.dumps(first, separators=(",", ":")).encode()
        inputs[10] = b"\n".join(rows) + b"\n"
        inputs[8]["draw_file"]["content_sha256"] = hashlib.sha256(inputs[10]).hexdigest()
        _rebind_manifest_and_uncertainty(inputs)
        with self.assertRaisesRegex(ModelValidationError, "PFS above OS"):
            run_uncertainty(*inputs)

    def test_rejects_stale_draw_binding(self) -> None:
        inputs = valid_inputs()
        inputs[2]["joint_survival_inputs"]["draws"]["content_sha256"] = "0" * 64
        inputs[3] = _json_bytes(inputs[2])
        with self.assertRaisesRegex(ModelValidationError, "does not match the current bytes"):
            run_uncertainty(*inputs)

    def test_rejects_a_represented_curve_as_omitted(self) -> None:
        inputs = valid_inputs()
        inputs[2]["probabilistic_analysis"]["omitted_parameters"].append(
            {
                "provenance_path": "partitioned_survival.strategies.comparator.pfs",
                "rationale": "Invalid because this curve is represented by every row.",
            }
        )
        inputs[3] = _json_bytes(inputs[2])
        with self.assertRaisesRegex(ModelValidationError, "must not list represented"):
            run_uncertainty(*inputs)

    def test_portable_validator_checks_source_artifact_bytes(self) -> None:
        inputs = valid_inputs()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "heor/fits").mkdir(parents=True)
            paths_and_bytes = {
                "heor/analysis-plan.json": inputs[1],
                "heor/uncertainty-plan.json": inputs[3],
                "heor/partitioned-survival-plan.json": inputs[5],
                "heor/survival-curve-materializations.json": inputs[7],
                "heor/joint-survival-uncertainty.json": inputs[9],
                "heor/joint-survival-draws.jsonl": inputs[10],
                "heor/fits/joint-posterior.json": b"joint posterior",
            }
            for relative, raw in paths_and_bytes.items():
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
            validator_args = (
                root / "heor/analysis-plan.json",
                root / "heor/partitioned-survival-plan.json",
                root / "heor/survival-curve-materializations.json",
                root / "heor/uncertainty-plan.json",
                root / "heor/joint-survival-uncertainty.json",
                root / "heor/joint-survival-draws.jsonl",
                root,
            )
            self.assertEqual(PORTABLE.validate(*validator_args), [])
            self.assertEqual(
                UNCERTAINTY_PORTABLE.validate(
                    root / "heor/uncertainty-plan.json",
                    root / "heor/analysis-plan.json",
                    root / "heor/partitioned-survival-plan.json",
                    root / "heor/survival-curve-materializations.json",
                    root / "heor/joint-survival-uncertainty.json",
                    root / "heor/joint-survival-draws.jsonl",
                ),
                [],
            )
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    cli_main([
                        str(root / "heor/analysis-plan.json"),
                        "--uncertainty-plan",
                        str(root / "heor/uncertainty-plan.json"),
                        "--partitioned-survival-plan",
                        str(root / "heor/partitioned-survival-plan.json"),
                        "--survival-curve-materializations",
                        str(root / "heor/survival-curve-materializations.json"),
                        "--joint-survival-uncertainty-manifest",
                        str(root / "heor/joint-survival-uncertainty.json"),
                        "--joint-survival-draws",
                        str(root / "heor/joint-survival-draws.jsonl"),
                    ]),
                    0,
                )
            self.assertEqual(
                json.loads(output.getvalue())["calculation_classification"],
                "joint_curve_draw_parameter_uncertainty",
            )
            (root / "heor/fits/joint-posterior.json").write_bytes(b"changed")
            errors = PORTABLE.validate(*validator_args)
            self.assertTrue(any("source_artifact_bindings[0].content_sha256" in item for item in errors), errors)


if __name__ == "__main__":
    unittest.main()
