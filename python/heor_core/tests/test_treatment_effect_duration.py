from __future__ import annotations

from contextlib import redirect_stdout
import copy
import hashlib
import importlib.util
from io import StringIO
import json
from math import exp, log
from pathlib import Path
import tempfile
import unittest

from heor_core.cli import main as cli_main
from heor_core.model import ModelValidationError
from heor_core.partitioned_survival import run_partitioned_survival
from heor_core.uncertainty import run_uncertainty
from test_partitioned_survival import valid_inputs as valid_psm_inputs
from test_partitioned_survival_uncertainty import valid_inputs as valid_partial_inputs
from test_joint_survival_uncertainty import (
    _draw_rows as joint_draw_rows,
    valid_inputs as valid_joint_inputs,
)


ROOT = Path(__file__).resolve().parents[3]
VALIDATOR_PATH = (
    ROOT
    / "runtime/skills/core/heor-treatment-effect-duration/scripts"
    / "validate_treatment_effect_duration.py"
)
SPEC = importlib.util.spec_from_file_location("portable_treatment_duration", VALIDATOR_PATH)
assert SPEC and SPEC.loader
PORTABLE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PORTABLE)


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


def _duration_payload(
    analysis: dict,
    analysis_raw: bytes,
    psm: dict,
    materializations_raw: bytes,
) -> dict:
    modes = (
        ("waning-base", "log_linear_waning", 2.0),
        ("sustained-effect", "sustained", None),
        ("immediate-stop", "immediate_stop", None),
    )
    return {
        "schema_version": "0.1.0",
        "duration_id": "psm-effect-duration",
        "analysis_id": analysis["analysis_id"],
        "psm_id": psm["psm_id"],
        "status": "ready_for_human_review",
        "base_analysis": {
            "path": "heor/analysis-plan.json",
            "content_sha256": hashlib.sha256(analysis_raw).hexdigest(),
        },
        "source_curve_materializations": {
            "path": "heor/survival-curve-materializations.json",
            "content_sha256": hashlib.sha256(materializations_raw).hexdigest(),
        },
        "comparison": {
            "comparator_strategy_id": "comparator",
            "intervention_strategy_id": "intervention",
            "endpoint_order": ["pfs", "os"],
        },
        "base_case_scenario_id": "waning-base",
        "scenarios": [
            {
                "scenario_id": scenario_id,
                "label": scenario_id.replace("-", " ").title(),
                "rationale": "Explicit duration scenario for Human review.",
                "basis_ids": [f"duration-basis-{scenario_id}"],
                "policies": [
                    {
                        "endpoint": endpoint,
                        "mode": mode,
                        "evidence_horizon_years": 0.0,
                        "hazard_ratio": {
                            "value": 0.5,
                            "basis_ids": [f"effect-{endpoint}"],
                        },
                        "waning_end_years": waning_end,
                        "rationale": "Apply the declared policy after the evidence horizon.",
                        "basis_ids": [f"duration-{endpoint}-{scenario_id}"],
                    }
                    for endpoint in ("pfs", "os")
                ],
            }
            for scenario_id, mode, waning_end in modes
        ],
        "limitations": [
            "The artifact explores duration structure but does not establish clinical validity."
        ],
    }


def _scenario_values(rate: float, mode: str) -> list[float]:
    values = [1.0]
    for interval_start in (0.0, 1.0):
        if mode == "sustained":
            ratio = 0.5
        elif mode == "immediate_stop":
            ratio = 1.0
        else:
            ratio = exp(log(0.5) * ((2.0 - interval_start) / 2.0))
        values.append(values[-1] * exp(-ratio * rate))
    return values


def _apply_base_rows(psm: dict, duration_raw: bytes, materializations_raw: bytes) -> None:
    basis_ids = [
        f"source-materialization-sha256:{hashlib.sha256(materializations_raw).hexdigest()}",
        f"treatment-effect-duration-sha256:{hashlib.sha256(duration_raw).hexdigest()}",
        "duration-scenario:waning-base",
    ]
    rates = {
        ("comparator", "pfs"): 0.5,
        ("comparator", "os"): 0.2,
        ("intervention", "pfs"): None,
        ("intervention", "os"): None,
    }
    for strategy_id in ("comparator", "intervention"):
        for endpoint in ("pfs", "os"):
            comparator_rate = 0.5 if endpoint == "pfs" else 0.2
            rate = rates[(strategy_id, endpoint)]
            values = (
                [exp(-float(rate) * index) for index in range(3)]
                if rate is not None
                else _scenario_values(comparator_rate, "log_linear_waning")
            )
            psm["strategies"][strategy_id][endpoint] = [
                {
                    "time_years": float(index),
                    "survival": survival,
                    "basis_ids": list(basis_ids),
                }
                for index, survival in enumerate(values)
            ]


def valid_inputs() -> list:
    analysis, analysis_raw, psm, _, materializations, materializations_raw = (
        valid_psm_inputs()
    )
    psm = copy.deepcopy(psm)
    psm["schema_version"] = "0.4.0"
    duration = _duration_payload(
        analysis, analysis_raw, psm, materializations_raw
    )
    duration_raw = _json_bytes(duration)
    psm["treatment_effect_duration"] = {
        "path": "heor/treatment-effect-duration.json",
        "content_sha256": hashlib.sha256(duration_raw).hexdigest(),
    }
    _apply_base_rows(psm, duration_raw, materializations_raw)
    psm_raw = _json_bytes(psm)
    return [
        analysis,
        analysis_raw,
        psm,
        psm_raw,
        materializations,
        materializations_raw,
        duration,
        duration_raw,
    ]


def _rebind_duration(inputs: list, *, update_rows: bool = False) -> None:
    inputs[7] = _json_bytes(inputs[6])
    inputs[2]["treatment_effect_duration"]["content_sha256"] = hashlib.sha256(
        inputs[7]
    ).hexdigest()
    if update_rows:
        _apply_base_rows(inputs[2], inputs[7], inputs[5])
    inputs[3] = _json_bytes(inputs[2])


class TreatmentEffectDurationTests(unittest.TestCase):
    def test_runs_three_complete_structural_scenarios(self) -> None:
        inputs = valid_inputs()
        result = run_partitioned_survival(*inputs)
        self.assertEqual(result["schema_version"], "0.4.0")
        self.assertEqual(result["engine_version"], "0.4.0")
        self.assertEqual(result["partitioned_survival_plan_schema_version"], "0.4.0")
        self.assertEqual(
            result["treatment_effect_duration_sha256"],
            hashlib.sha256(inputs[7]).hexdigest(),
        )
        scenarios = {
            item["scenario_id"]: item
            for item in result["treatment_effect_duration_scenarios"]
        }
        self.assertEqual(
            set(scenarios), {"waning-base", "sustained-effect", "immediate-stop"}
        )
        observed = result["strategies"]["intervention"]["occupancy"][1][0]
        self.assertAlmostEqual(observed, exp(-0.25))
        sustained_qaly = scenarios["sustained-effect"]["strategies"]["intervention"][
            "total_qaly"
        ]
        immediate_qaly = scenarios["immediate-stop"]["strategies"]["intervention"][
            "total_qaly"
        ]
        self.assertGreater(sustained_qaly, immediate_qaly)
        self.assertTrue(any("explicit sustained" in item for item in result["warnings"]))

    def test_rejects_missing_required_mode_coverage(self) -> None:
        inputs = valid_inputs()
        for policy in inputs[6]["scenarios"][2]["policies"]:
            policy["mode"] = "sustained"
        _rebind_duration(inputs)
        with self.assertRaisesRegex(ModelValidationError, "must cover sustained"):
            run_partitioned_survival(*inputs)

    def test_rejects_stale_duration_binding(self) -> None:
        inputs = valid_inputs()
        inputs[2]["treatment_effect_duration"]["content_sha256"] = "0" * 64
        inputs[3] = _json_bytes(inputs[2])
        with self.assertRaisesRegex(ModelValidationError, "does not match current bytes"):
            run_partitioned_survival(*inputs)

    def test_rejects_crossing_duration_scenario_without_repair(self) -> None:
        inputs = valid_inputs()
        for scenario in inputs[6]["scenarios"]:
            scenario["policies"][0]["hazard_ratio"]["value"] = 0.01
        _rebind_duration(inputs)
        with self.assertRaisesRegex(ModelValidationError, "PFS above OS"):
            run_partitioned_survival(*inputs)

    def test_rejects_more_than_two_strategies(self) -> None:
        inputs = valid_inputs()
        inputs[0]["strategy_order"].append("third")
        inputs[0]["strategies"]["third"] = copy.deepcopy(
            inputs[0]["strategies"]["comparator"]
        )
        inputs[0]["strategies"]["third"]["name"] = "Third strategy"
        inputs[1] = _json_bytes(inputs[0])
        inputs[2]["base_analysis"]["content_sha256"] = hashlib.sha256(
            inputs[1]
        ).hexdigest()
        inputs[4]["base_analysis"]["content_sha256"] = hashlib.sha256(
            inputs[1]
        ).hexdigest()
        inputs[6]["base_analysis"]["content_sha256"] = hashlib.sha256(
            inputs[1]
        ).hexdigest()
        inputs[5] = _json_bytes(inputs[4])
        inputs[2]["curve_materializations"]["content_sha256"] = hashlib.sha256(
            inputs[5]
        ).hexdigest()
        inputs[6]["source_curve_materializations"]["content_sha256"] = hashlib.sha256(
            inputs[5]
        ).hexdigest()
        _rebind_duration(inputs, update_rows=True)
        with self.assertRaisesRegex(
            ModelValidationError,
            "must match analysis strategy_order|every strategy|exactly two ordered strategies",
        ):
            run_partitioned_survival(*inputs)

    def test_cli_requires_and_consumes_duration_artifact(self) -> None:
        inputs = valid_inputs()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = (
                "heor/analysis-plan.json",
                "heor/partitioned-survival-plan.json",
                "heor/survival-curve-materializations.json",
                "heor/treatment-effect-duration.json",
            )
            for relative, raw in zip(paths, (inputs[1], inputs[3], inputs[5], inputs[7])):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    cli_main(
                        [
                            str(root / paths[0]),
                            "--partitioned-survival-plan",
                            str(root / paths[1]),
                            "--survival-curve-materializations",
                            str(root / paths[2]),
                            "--treatment-effect-duration",
                            str(root / paths[3]),
                        ]
                    ),
                    0,
                )
            self.assertEqual(json.loads(output.getvalue())["schema_version"], "0.4.0")

    def test_portable_validator_recalculates_and_binds_current_bytes(self) -> None:
        inputs = valid_inputs()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [
                root / "heor/treatment-effect-duration.json",
                root / "heor/analysis-plan.json",
                root / "heor/partitioned-survival-plan.json",
                root / "heor/survival-curve-materializations.json",
            ]
            for destination, raw in zip(paths, (inputs[7], inputs[1], inputs[3], inputs[5])):
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
            self.assertEqual(PORTABLE.validate(*paths), [])
            materializations = json.loads(paths[3].read_bytes())
            materializations["curves"][0]["values"][1]["survival"] = 0.9
            paths[3].write_bytes(_json_bytes(materializations))
            errors = PORTABLE.validate(*paths)
            self.assertTrue(
                any(
                    "source_curve_materializations" in item
                    or "not reproduced by parameters" in item
                    for item in errors
                ),
                errors,
            )

    def test_economic_uncertainty_binds_and_reports_duration_scenarios(self) -> None:
        inputs = list(valid_partial_inputs())
        analysis, analysis_raw, uncertainty = inputs[0], inputs[1], inputs[2]
        psm, materializations_raw = inputs[4], inputs[7]
        psm["schema_version"] = "0.4.0"
        duration = _duration_payload(
            analysis, analysis_raw, psm, materializations_raw
        )
        duration_raw = _json_bytes(duration)
        psm["treatment_effect_duration"] = {
            "path": "heor/treatment-effect-duration.json",
            "content_sha256": hashlib.sha256(duration_raw).hexdigest(),
        }
        _apply_base_rows(psm, duration_raw, materializations_raw)
        psm_raw = _json_bytes(psm)
        inputs[4], inputs[5] = psm, psm_raw
        uncertainty["partitioned_survival_inputs"]["plan"][
            "content_sha256"
        ] = hashlib.sha256(psm_raw).hexdigest()
        uncertainty["partitioned_survival_inputs"]["treatment_effect_duration"] = {
            "path": "heor/treatment-effect-duration.json",
            "content_sha256": hashlib.sha256(duration_raw).hexdigest(),
        }
        inputs[2] = uncertainty
        inputs[3] = _json_bytes(uncertainty)
        result = run_uncertainty(
            *inputs,
            None,
            None,
            None,
            duration,
            duration_raw,
        )
        self.assertEqual(
            result["treatment_effect_duration_sha256"],
            hashlib.sha256(duration_raw).hexdigest(),
        )
        self.assertEqual(len(result["treatment_effect_duration_scenarios"]), 3)

    def test_joint_uncertainty_binds_the_selected_duration_structure(self) -> None:
        inputs = valid_joint_inputs(vary=False)
        analysis, analysis_raw, uncertainty = inputs[0], inputs[1], inputs[2]
        psm, materializations_raw, manifest = inputs[4], inputs[7], inputs[8]
        psm["schema_version"] = "0.4.0"
        duration = _duration_payload(
            analysis, analysis_raw, psm, materializations_raw
        )
        duration_raw = _json_bytes(duration)
        psm["treatment_effect_duration"] = {
            "path": "heor/treatment-effect-duration.json",
            "content_sha256": hashlib.sha256(duration_raw).hexdigest(),
        }
        _apply_base_rows(psm, duration_raw, materializations_raw)
        psm_raw = _json_bytes(psm)
        inputs[4], inputs[5] = psm, psm_raw
        draws_raw = joint_draw_rows(psm, vary=False)
        inputs[10] = draws_raw
        manifest["schema_version"] = "0.2.0"
        manifest["partitioned_survival_plan"]["content_sha256"] = hashlib.sha256(
            psm_raw
        ).hexdigest()
        manifest["treatment_effect_duration"] = {
            "path": "heor/treatment-effect-duration.json",
            "content_sha256": hashlib.sha256(duration_raw).hexdigest(),
        }
        manifest["draw_file"]["content_sha256"] = hashlib.sha256(
            draws_raw
        ).hexdigest()
        inputs[9] = _json_bytes(manifest)
        uncertainty["partitioned_survival_inputs"]["plan"][
            "content_sha256"
        ] = hashlib.sha256(psm_raw).hexdigest()
        uncertainty["partitioned_survival_inputs"]["treatment_effect_duration"] = {
            "path": "heor/treatment-effect-duration.json",
            "content_sha256": hashlib.sha256(duration_raw).hexdigest(),
        }
        uncertainty["joint_survival_inputs"]["manifest"][
            "content_sha256"
        ] = hashlib.sha256(inputs[9]).hexdigest()
        uncertainty["joint_survival_inputs"]["draws"][
            "content_sha256"
        ] = hashlib.sha256(draws_raw).hexdigest()
        uncertainty["probabilistic_analysis"]["omitted_parameters"] = [
            item
            for item in uncertainty["probabilistic_analysis"]["omitted_parameters"]
            if item["provenance_path"]
            != "partitioned_survival.structural.treatment_effect_duration"
        ]
        inputs[2] = uncertainty
        inputs[3] = _json_bytes(uncertainty)
        result = run_uncertainty(*inputs, duration, duration_raw)
        self.assertEqual(
            result["treatment_effect_duration_sha256"],
            hashlib.sha256(duration_raw).hexdigest(),
        )
        self.assertTrue(
            any(
                "reported separately" in limitation
                for limitation in result["limitations"]
            )
        )


if __name__ == "__main__":
    unittest.main()
