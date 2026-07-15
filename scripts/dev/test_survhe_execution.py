#!/usr/bin/env python3
"""Contract tests for the isolated AI4HEOR survHE execution bundle."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "runtime/skills/core/heor-survival-fit-execution/scripts"
sys.path.insert(0, str(SCRIPT_DIR))
from survhe_execution_contract import EVALUATOR, audit_result, digest, expected_curve, validate_request  # noqa: E402

REVIEW_VALIDATOR = ROOT / "runtime/skills/core/heor-survival-extrapolation-review/scripts/validate_survival_extrapolation_review.py"
review_spec = importlib.util.spec_from_file_location("ai4heor_survival_review", REVIEW_VALIDATOR)
assert review_spec is not None and review_spec.loader is not None
review_validator = importlib.util.module_from_spec(review_spec)
review_spec.loader.exec_module(review_validator)


def write_json(path: Path, value: dict) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, indent=2) + "\n").encode()
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


class SurvheExecutionContractTests(unittest.TestCase):
    @staticmethod
    def request_fixture(workspace: Path) -> tuple[dict, Path]:
        data_path = workspace / "data/survival.csv"
        data_path.parent.mkdir(parents=True)
        data_path.write_text("time,event\n0.5,1\n1,0\n2,1\n3,0\n", encoding="utf-8")
        request = {
            "schema_version": "0.1.0",
            "execution_id": "os-control",
            "status": "ready_for_execution",
            "analysis_target": {
                "analysis_id": "survival-analysis",
                "path": "strategies.comparator.transition_schedule",
            },
            "source_data": {
                "classification": "restricted",
                "execution_boundary": "local_only",
                "format": "csv",
                "path": "data/survival.csv",
                "sha256": digest(data_path.read_bytes()),
                "columns": {"time": "time", "event": "event"},
                "row_count": 4,
                "event_count": 2,
                "censor_count": 2,
                "contains_direct_identifiers": False,
                "missing_policy": "reject",
                "additional_columns": "reject",
            },
            "fit": {
                "method": "maximum_likelihood",
                "formula": "intercept_only",
                "candidate_models": [
                    {"family": "exponential", "rationale": "Constant hazard reference."},
                    {"family": "weibull", "rationale": "Monotone hazard alternative."},
                ],
                "prediction_times": [0, 1, 3, 5],
                "observed_follow_up": 3,
                "model_horizon": 5,
                "cross_implementation_tolerance": 1e-8,
            },
            "runtime": {
                "expected_packages": {
                    "survHE": "2.0.51",
                    "flexsurv": "2.3.2",
                    "survival": "3.8-3",
                }
            },
            "output": {
                "directory": "heor/survival-fit-executions/os-control",
                "overwrite_policy": "fail_if_exists",
            },
            "limitations": ["Clinical and external validity remain Human-review questions."],
            "human_gate": {
                "state": "awaiting_execution_authorization",
                "required_action": "approve_local_survival_fit_command",
            },
        }
        request_path = workspace / "heor/survival-fit-requests/os-control.json"
        write_json(request_path, request)
        return request, request_path

    @staticmethod
    def _model(family: str, parameters: dict[str, float], times: list[float]) -> dict:
        landmarks = []
        for time in times:
            survival, hazard = expected_curve(family, parameters, time)
            landmarks.append({"time": time, "survival": survival, "hazard": hazard})
        return {
            "schema_version": "0.1.0",
            "family": family,
            "status": "converged",
            "fit_statistics": {"aic": 10.0, "bic": 12.0, "log_likelihood": -4.0},
            "parameterization": "survHE/flexsurv",
            "parameters": [{"name": name, "estimate": value} for name, value in parameters.items()],
            "landmarks": landmarks,
            "warnings": [],
        }

    @classmethod
    def result_fixture(cls, workspace: Path) -> tuple[Path, dict]:
        request, request_path = cls.request_fixture(workspace)
        output = workspace / request["output"]["directory"]
        models_dir = output / "models"
        models_dir.mkdir(parents=True)
        exp_path = models_dir / "exponential.json"
        wei_path = models_dir / "weibull.json"
        exp_sha = write_json(exp_path, cls._model("exponential", {"rate": 0.2}, request["fit"]["prediction_times"]))
        wei_sha = write_json(wei_path, cls._model("weibull", {"shape": 1.5, "scale": 4.0}, request["fit"]["prediction_times"]))
        files = {}
        for name, content in {
            "survhe_mle_adapter.R": b"fixed adapter\n",
            "session-info.txt": b"R session\n",
            "execution.log": b"exit_code: 0\n",
            "km-overlay.png": b"km",
            "log-cumulative-hazard.png": b"cloglog",
            "hazard.png": b"hazard",
        }.items():
            path = output / name
            path.write_bytes(content)
            files[name] = digest(content)
        base = request["output"]["directory"]
        checks = [
            {
                "family": family,
                "status": "passed",
                "max_abs_survival_error": 0.0,
                "max_abs_hazard_error": 0.0,
            }
            for family in ("exponential", "weibull")
        ]
        manifest = {
            "schema_version": "0.1.0",
            "execution_id": request["execution_id"],
            "status": "execution_complete",
            "request": {
                "path": request_path.relative_to(workspace).as_posix(),
                "sha256": digest(request_path.read_bytes()),
            },
            "source_data": {
                field: request["source_data"][field]
                for field in ("path", "sha256", "row_count", "event_count", "censor_count")
            },
            "runtime": {
                "backend": "survHE",
                "method": "maximum_likelihood",
                "r_version": "R version 4.5.2",
                "rscript_sha256": "a" * 64,
                "package_versions": request["runtime"]["expected_packages"],
                "adapter_path": f"{base}/survhe_mle_adapter.R",
                "adapter_sha256": files["survhe_mle_adapter.R"],
                "session_info_path": f"{base}/session-info.txt",
                "session_info_sha256": files["session-info.txt"],
                "execution_log_path": f"{base}/execution.log",
                "execution_log_sha256": files["execution.log"],
            },
            "model_order": ["exponential", "weibull"],
            "models": [
                {
                    "family": "exponential",
                    "status": "converged",
                    "path": f"{base}/models/exponential.json",
                    "sha256": exp_sha,
                },
                {
                    "family": "weibull",
                    "status": "converged",
                    "path": f"{base}/models/weibull.json",
                    "sha256": wei_sha,
                },
            ],
            "diagnostics": {
                "km_overlay_path": f"{base}/km-overlay.png",
                "km_overlay_sha256": files["km-overlay.png"],
                "log_cumulative_hazard_path": f"{base}/log-cumulative-hazard.png",
                "log_cumulative_hazard_sha256": files["log-cumulative-hazard.png"],
                "hazard_plot_path": f"{base}/hazard.png",
                "hazard_plot_sha256": files["hazard.png"],
            },
            "cross_implementation": {
                "evaluator": EVALUATOR,
                "tolerance": request["fit"]["cross_implementation_tolerance"],
                "checks": checks,
                "complete": True,
            },
            "limitations": ["Numerical agreement is not scientific validity."],
            "human_gate": {
                "state": "awaiting_human_review",
                "required_action": "review_survival_extrapolation",
            },
        }
        manifest_path = output / "result-manifest.json"
        write_json(manifest_path, manifest)
        return manifest_path, manifest

    @staticmethod
    def review_fixture(workspace: Path, manifest_path: Path, manifest: dict) -> tuple[dict, dict]:
        request = json.loads((workspace / manifest["request"]["path"]).read_text())
        models = []
        for binding in manifest["models"]:
            model = json.loads((workspace / binding["path"]).read_text())
            statistics = model["fit_statistics"]
            models.append({
                "family": binding["family"],
                "status": binding["status"],
                "aic": statistics["aic"],
                "bic": statistics["bic"],
                "log_likelihood": statistics["log_likelihood"],
                "parameterization": model["parameterization"],
                "fit_output_path": binding["path"],
                "fit_output_sha256": binding["sha256"],
                "landmarks": model["landmarks"],
                "warnings": model["warnings"],
            })
        runtime = manifest["runtime"]
        diagnostics = manifest["diagnostics"] | {
            "internal_validity_assessment": "Statistical and graphical fit requires Human review.",
            "external_validity_assessment": "Unresolved pending external evidence.",
            "external_sources": [],
            "clinical_plausibility_assessment": "Long-term hazard shape requires Human review.",
        }
        review = {
            "schema_version": "0.3.0",
            "review_id": "os-control-review",
            "status": "ready_for_human_review",
            "analysis_target": request["analysis_target"],
            "context": {
                "endpoint": "OS",
                "population": "Example population",
                "curve_label": "Comparator OS",
                "time_origin": "randomisation",
                "time_unit": "years",
                "observed_follow_up": request["fit"]["observed_follow_up"],
                "model_horizon": request["fit"]["model_horizon"],
            },
            "source_data": {
                "classification": request["source_data"]["classification"],
                "execution_boundary": "local_only",
                "format": "precomputed_survival_fit_bundle",
                "path": manifest_path.relative_to(workspace).as_posix(),
                "sha256": digest(manifest_path.read_bytes()),
                "time_variable": request["source_data"]["columns"]["time"],
                "event_definition": "death",
                "censor_definition": "right censoring",
            },
            "pre_specification": {
                "fit_method": "maximum_likelihood",
                "candidate_models": request["fit"]["candidate_models"],
                "protocol_deviations": [],
            },
            "execution": {
                "backend": "survHE",
                "environment": "ai4heor_isolated_local_mle",
                "r_version": runtime["r_version"],
                "package_versions": runtime["package_versions"],
                "command_path": runtime["adapter_path"],
                "command_sha256": runtime["adapter_sha256"],
                "session_info_path": runtime["session_info_path"],
                "session_info_sha256": runtime["session_info_sha256"],
            },
            "models": models,
            "diagnostics": diagnostics,
            "structural_scenarios": ["exponential", "weibull"],
            "analyst_recommendation": {
                "family": "weibull",
                "rationale": "Example recommendation pending Human review.",
                "alternatives": ["exponential"],
            },
            "limitations": ["Numerical agreement is not scientific validity."],
            "human_gate": {
                "state": "awaiting_human_selection",
                "required_action": "select_curve_in_analysis_plan",
            },
        }
        plan = {
            "analysis_id": request["analysis_target"]["analysis_id"],
            "input_provenance": [{
                "path": request["analysis_target"]["path"],
                "derivation": {"transformation": {
                    "operation": "parametric_survival_to_transition_schedule",
                    "distribution": "weibull",
                }},
            }],
        }
        return review, plan

    def test_request_preflight_recalculates_csv_counts_and_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            request, _ = self.request_fixture(workspace)
            errors, facts = validate_request(request, workspace)
            self.assertEqual(errors, [])
            self.assertEqual(facts["row_count"], 4)
            request["source_data"]["contains_direct_identifiers"] = True
            request["source_data"]["row_count"] = 5
            errors, _ = validate_request(request, workspace)
            self.assertTrue(any("direct identifiers" in error for error in errors))
            self.assertTrue(any("row_count" in error for error in errors))

    def test_complete_result_is_hash_bound_and_independently_recalculated(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifest_path, _ = self.result_fixture(workspace)
            result = audit_result(manifest_path, workspace)
            self.assertTrue(result["complete"], result["errors"])
            self.assertTrue(result["eligible_for_review"])
            self.assertTrue(result["cross_implementation_complete"])

    def test_parameterization_drift_fails_even_when_attacker_updates_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifest_path, manifest = self.result_fixture(workspace)
            model_path = workspace / manifest["models"][1]["path"]
            model = json.loads(model_path.read_text())
            model["landmarks"][2]["survival"] += 0.01
            manifest["models"][1]["sha256"] = write_json(model_path, model)
            write_json(manifest_path, manifest)
            result = audit_result(manifest_path, workspace)
            self.assertFalse(result["complete"])
            self.assertTrue(any("cross-check tolerance" in error for error in result["errors"]))

    def test_stale_source_and_runtime_version_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifest_path, manifest = self.result_fixture(workspace)
            (workspace / manifest["source_data"]["path"]).write_text("time,event\n1,1\n", encoding="utf-8")
            manifest["runtime"]["package_versions"]["survHE"] = "2.0.52"
            write_json(manifest_path, manifest)
            result = audit_result(manifest_path, workspace)
            self.assertFalse(result["complete"])
            self.assertTrue(any("source_data.sha256" in error for error in result["errors"]))
            self.assertTrue(any("package_versions" in error for error in result["errors"]))

    def test_schema_0_3_review_is_transitively_bound_to_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifest_path, manifest = self.result_fixture(workspace)
            review, plan = self.review_fixture(workspace, manifest_path, manifest)
            result = review_validator.audit(review, workspace, plan)
            self.assertTrue(result["complete"], result["errors"])
            self.assertTrue(result["cross_implementation_complete"])
            review["models"][0]["aic"] += 1
            result = review_validator.audit(review, workspace, plan)
            self.assertFalse(result["complete"])
            self.assertTrue(any("exactly reproduce" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
