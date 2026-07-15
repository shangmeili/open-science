from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from test_partitioned_survival import CURVES, curve_basis, valid_inputs


ROOT = Path(__file__).resolve().parents[3]
VALIDATOR_PATH = (
    ROOT
    / "runtime/skills/core/heor-survival-curve-materialization/scripts"
    / "validate_survival_curve_materializations.py"
)
SPEC = importlib.util.spec_from_file_location("portable_materialization", VALIDATOR_PATH)
assert SPEC and SPEC.loader
PORTABLE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PORTABLE)


def encoded(value: dict) -> bytes:
    return json.dumps(value, sort_keys=True).encode()


def workspace_fixture(root: Path) -> tuple[dict, bytes, dict, bytes, dict, bytes]:
    analysis, analysis_raw, psm, _, materializations, _ = valid_inputs()
    (root / "heor/reviews").mkdir(parents=True)
    (root / "heor/fits").mkdir(parents=True)
    for curve in materializations["curves"]:
        strategy_id = curve["strategy_id"]
        endpoint = curve["endpoint"]
        family, parameters = CURVES[(strategy_id, endpoint)]
        parameterization = (
            "exponential_rate"
            if family == "exponential"
            else "weibull_shape_scale_aft"
        )
        fit = {
            "schema_version": "0.1.0",
            "family": family,
            "parameterization": parameterization,
            "time_unit": "years",
            "parameters": parameters,
        }
        fit_raw = encoded(fit)
        fit_path = f"heor/fits/{strategy_id}-{endpoint}.json"
        (root / fit_path).write_bytes(fit_raw)
        fit_binding = {
            "path": fit_path,
            "content_sha256": hashlib.sha256(fit_raw).hexdigest(),
        }
        target = curve["target_path"]
        review = {
            "schema_version": "0.2.0",
            "status": "ready_for_human_review",
            "analysis_target": {"analysis_id": analysis["analysis_id"], "path": target},
            "context": {
                "endpoint": endpoint.upper(),
                "time_origin": psm["time_origin"],
                "time_unit": "years",
            },
            "models": [
                {
                    "family": family,
                    "status": "converged",
                    "parameterization": parameterization,
                    "fit_output_path": fit_path,
                    "fit_output_sha256": fit_binding["content_sha256"],
                }
            ],
        }
        review_raw = encoded(review)
        review_path = f"heor/reviews/{strategy_id}-{endpoint}.json"
        (root / review_path).write_bytes(review_raw)
        review_binding = {
            "path": review_path,
            "content_sha256": hashlib.sha256(review_raw).hexdigest(),
            "target_path": target,
            "selected_family": family,
        }
        curve["review_binding"] = review_binding
        curve["fit_output_binding"] = fit_binding
        curve["basis_ids"] = curve_basis(review_binding, fit_binding)
        psm_curve = psm["strategies"][strategy_id]
        psm_curve["curve_review_bindings"][endpoint] = review_binding
        for row in psm_curve[endpoint]:
            row["basis_ids"] = list(curve["basis_ids"])

    materializations_raw = encoded(materializations)
    psm["curve_materializations"] = {
        "path": "heor/survival-curve-materializations.json",
        "content_sha256": hashlib.sha256(materializations_raw).hexdigest(),
    }
    psm_raw = encoded(psm)
    (root / "heor/analysis-plan.json").write_bytes(analysis_raw)
    (root / "heor/partitioned-survival-plan.json").write_bytes(psm_raw)
    (root / "heor/survival-curve-materializations.json").write_bytes(
        materializations_raw
    )
    return analysis, analysis_raw, psm, psm_raw, materializations, materializations_raw


class PortableSurvivalMaterializationTests(unittest.TestCase):
    def test_checks_exact_review_and_fit_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            analysis, analysis_raw, psm, _, manifest, manifest_raw = workspace_fixture(root)
            self.assertEqual(
                PORTABLE.validate(
                    analysis, analysis_raw, psm, manifest, manifest_raw, root
                ),
                [],
            )

            fit_path = root / "heor/fits/comparator-pfs.json"
            fit = json.loads(fit_path.read_bytes())
            fit["parameters"]["rate_per_year"] = 0.6
            fit_path.write_bytes(encoded(fit))
            errors = PORTABLE.validate(
                analysis, analysis_raw, psm, manifest, manifest_raw, root
            )
            self.assertTrue(
                any("fit output.content_sha256 does not match" in error for error in errors),
                errors,
            )

    def test_rejects_manifest_parameter_drift_even_with_updated_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            analysis, analysis_raw, psm, _, manifest, _ = workspace_fixture(root)
            manifest["curves"][0]["parameters"]["rate_per_year"] = 0.6
            manifest_raw = encoded(manifest)
            psm["curve_materializations"]["content_sha256"] = hashlib.sha256(
                manifest_raw
            ).hexdigest()
            errors = PORTABLE.validate(
                analysis, analysis_raw, psm, manifest, manifest_raw, root
            )
            self.assertTrue(
                any("do not match fit-output bytes" in error for error in errors),
                errors,
            )

    def test_schema_0_2_binds_normalized_additional_family_outputs(self) -> None:
        families = [
            ("gompertz", "gompertz_shape_rate", {"shape_per_year": -0.05, "rate_per_year": 0.2}, [("shape", -0.05), ("rate", 0.2)]),
            ("gamma", "gamma_shape_rate", {"shape": 2.5, "rate_per_year": 0.7}, [("shape", 2.5), ("rate", 0.7)]),
            ("generalized_gamma", "generalized_gamma_prentice", {"mu_log_years": 1.0, "sigma": 0.7, "Q": -0.6}, [("mu", 1.0), ("sigma", 0.7), ("Q", -0.6)]),
            ("generalized_f", "generalized_f_prentice", {"mu_log_years": 1.0, "sigma": 0.8, "Q": -0.3, "P": 0.9}, [("mu", 1.0), ("sigma", 0.8), ("Q", -0.3), ("P", 0.9)]),
        ]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            analysis, analysis_raw, psm, _, manifest, _ = workspace_fixture(root)
            manifest["schema_version"] = "0.2.0"
            manifest["evaluator"]["version"] = "0.2.0"
            cycle_length = analysis["cycle_length_years"]
            for curve, (family, parameterization, parameters, natural_rows) in zip(manifest["curves"], families):
                strategy_id, endpoint, target = curve["strategy_id"], curve["endpoint"], curve["target_path"]
                fit = {
                    "schema_version": "0.1.0", "family": family, "status": "converged",
                    "fit_statistics": {"aic": 10.0, "bic": 11.0, "log_likelihood": -4.0},
                    "parameterization": parameterization,
                    "parameters": [{"name": name, "estimate": value} for name, value in natural_rows],
                    "landmarks": [], "warnings": [],
                }
                fit_raw = encoded(fit)
                fit_path = f"heor/fits/{strategy_id}-{endpoint}-normalized.json"
                (root / fit_path).write_bytes(fit_raw)
                fit_binding = {"path": fit_path, "content_sha256": hashlib.sha256(fit_raw).hexdigest()}
                review_path = Path(root / curve["review_binding"]["path"])
                review = json.loads(review_path.read_bytes())
                review["schema_version"] = "0.3.0"
                review["models"] = [{
                    "family": family, "status": "converged", "parameterization": parameterization,
                    "fit_output_path": fit_path, "fit_output_sha256": fit_binding["content_sha256"],
                }]
                review_raw = encoded(review)
                review_path.write_bytes(review_raw)
                review_binding = {
                    "path": curve["review_binding"]["path"],
                    "content_sha256": hashlib.sha256(review_raw).hexdigest(),
                    "target_path": target, "selected_family": family,
                }
                curve.update({
                    "family": family, "parameterization": parameterization,
                    "parameters": parameters, "fit_output_binding": fit_binding,
                    "review_binding": review_binding,
                    "basis_ids": [
                        f"review-sha256:{review_binding['content_sha256']}",
                        f"fit-output-sha256:{fit_binding['content_sha256']}",
                        "evaluator:ai4heor-parametric-survival@0.2.0",
                    ],
                    "values": [
                        {
                            "time_years": index * cycle_length,
                            "survival": PORTABLE.evaluate(
                                family,
                                {name: parameters[name] for name in PORTABLE.TYPED_PARAMETERS[family][1]},
                                index * cycle_length,
                            ),
                        }
                        for index in range(analysis["cycles"] + 1)
                    ],
                })
                psm["strategies"][strategy_id]["curve_review_bindings"][endpoint] = review_binding
                psm["strategies"][strategy_id][endpoint] = [
                    {**row, "basis_ids": list(curve["basis_ids"])} for row in curve["values"]
                ]
            manifest_raw = encoded(manifest)
            psm["curve_materializations"]["content_sha256"] = hashlib.sha256(manifest_raw).hexdigest()
            self.assertEqual(PORTABLE.validate(analysis, analysis_raw, psm, manifest, manifest_raw, root), [])


if __name__ == "__main__":
    unittest.main()
