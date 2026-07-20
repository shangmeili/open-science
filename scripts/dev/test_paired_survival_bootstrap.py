#!/usr/bin/env python3
"""Contract and tamper tests for paired survival bootstrap execution."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "runtime" / "skills" / "core" / "heor-paired-survival-bootstrap"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

from paired_bootstrap_contract import (  # noqa: E402
    ADAPTER_PATH,
    DRAW_FORMAT,
    EVALUATOR,
    EVALUATOR_PATH,
    PLAN_FORMAT,
    REPLICATE_FORMAT,
    RNG_ALGORITHM,
    RNG_VERSION,
    audit_result,
    bootstrap_frequencies,
    digest,
    inspect_source,
    validate_request,
)
from run_paired_survival_bootstrap import resolve_output_directory  # noqa: E402


def write_json(path: Path, value: dict) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, indent=2) + "\n").encode()
    path.write_bytes(raw)
    return raw


def binding(path: str, raw: bytes, identifier: str) -> dict:
    return {"path": path, "sha256": digest(raw), "id": identifier}


class PairedBootstrapContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temporary.name)
        heor = self.workspace / "heor"
        self.analysis = {
            "schema_version": "0.15.0",
            "analysis_id": "analysis-1",
            "strategy_order": ["baseline", "intervention"],
            "cycles": 2,
            "cycle_length_years": 1.0,
        }
        self.psm = {"schema_version": "0.7.0", "psm_id": "psm-1", "analysis_id": "analysis-1"}
        self.curves = [
            {
                "target_path": f"partitioned_survival.strategies.{strategy}.{endpoint}",
                "strategy_id": strategy,
                "endpoint": endpoint,
                "family": "exponential",
            }
            for strategy in self.analysis["strategy_order"]
            for endpoint in ("pfs", "os")
        ]
        self.materializations = {
            "schema_version": "0.2.0",
            "materialization_id": "materialization-1",
            "curves": self.curves,
        }
        analysis_raw = write_json(heor / "analysis-plan.json", self.analysis)
        psm_raw = write_json(heor / "partitioned-survival-plan.json", self.psm)
        material_raw = write_json(heor / "survival-curve-materializations.json", self.materializations)
        source_path = heor / "data" / "paired.csv"
        source_path.parent.mkdir(parents=True)
        source_raw = (
            "subject_id,strategy_id,pfs_time,pfs_event,os_time,os_event\n"
            "b1,baseline,1,1,2,1\n"
            "b2,baseline,1.5,0,2.5,0\n"
            "i1,intervention,1.2,1,2.2,1\n"
            "i2,intervention,1.7,0,2.7,0\n"
        ).encode()
        source_path.write_bytes(source_raw)
        self.request_path = heor / "paired-survival-bootstrap-request.json"
        self.request = {
            "schema_version": "0.1.0",
            "execution_id": "bootstrap-1",
            "status": "ready_for_execution",
            "analysis": binding("heor/analysis-plan.json", analysis_raw, "analysis-1"),
            "partitioned_survival": binding("heor/partitioned-survival-plan.json", psm_raw, "psm-1"),
            "curve_materializations": binding(
                "heor/survival-curve-materializations.json", material_raw, "materialization-1"
            ),
            "source_data": {
                "classification": "restricted",
                "execution_boundary": "local_only",
                "format": "csv",
                "path": "heor/data/paired.csv",
                "sha256": digest(source_raw),
                "columns": ["subject_id", "strategy_id", "pfs_time", "pfs_event", "os_time", "os_event"],
                "row_count": 4,
                "strategy_counts": {"baseline": 2, "intervention": 2},
                "contains_direct_identifiers": False,
                "subject_identifier": "pseudonymous_unique",
                "time_unit": "years",
                "missing_policy": "reject",
                "additional_columns": "reject",
            },
            "bootstrap": {
                "method": "ordinary_nonparametric_case_resampling",
                "iterations": 1000,
                "seed": 20260715,
                "rng": RNG_ALGORITHM,
                "rng_version": RNG_VERSION,
                "resampling_unit": "whole_subject_row",
                "strategy_resampling_design": "stratified_independent_parallel_arms",
                "preserve_strategy_sample_sizes": True,
                "endpoint_sampling": "same_subject_indices_for_pfs_and_os",
                "between_strategy_assumption": "conditional_independence_given_parallel_arm_design",
                "curves": self.curves,
                "time_grid_years": [0.0, 1.0, 2.0],
                "cross_implementation_tolerance": 1e-8,
            },
            "runtime": {"expected_packages": {"survHE": "2.0.51", "flexsurv": "2.3.2", "survival": "3.8.6"}},
            "output": {
                "directory": "heor/paired-survival-bootstrap-executions/bootstrap-1",
                "overwrite_policy": "fail_if_exists",
            },
            "limitations": ["Test fixture only."],
            "human_gate": {
                "state": "awaiting_execution_authorization",
                "required_action": "approve_local_paired_survival_bootstrap_command",
            },
        }
        self.request_raw = write_json(self.request_path, self.request)
        self.output = heor / "paired-survival-bootstrap-executions" / "bootstrap-1"
        self.output.mkdir(parents=True)
        self.manifest_path = self._write_complete_result()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _output_binding(self, name: str, format_name: str, row_count: int) -> dict:
        raw = (self.output / name).read_bytes()
        return {
            "path": f"heor/paired-survival-bootstrap-executions/bootstrap-1/{name}",
            "sha256": digest(raw),
            "format": format_name,
            "row_count": row_count,
        }

    def _write_complete_result(self) -> Path:
        facts, errors = inspect_source(self.workspace / "heor/data/paired.csv", self.analysis["strategy_order"])
        self.assertFalse(errors)
        plan_lines = ["replicate_index," + ",".join(f"row_{index}" for index in range(1, 5))]
        for index, frequencies in enumerate(
            bootstrap_frequencies(facts["strategy_positions"], 1000, self.request["bootstrap"]["seed"]), start=1
        ):
            plan_lines.append(f"{index}," + ",".join(str(value) for value in frequencies))
        (self.output / "bootstrap-plan.csv").write_text("\n".join(plan_lines) + "\n")

        rates = [0.3, 0.2, 0.25, 0.15]
        rows = []
        draws = []
        for replicate in range(1, 1001):
            normalized = []
            draw_curves = []
            for curve, rate in zip(self.curves, rates):
                survival = [math.exp(-rate * time) for time in (0.0, 1.0, 2.0)]
                normalized.append(
                    {
                        **curve,
                        "status": "converged",
                        "parameterization": "exponential_rate",
                        "parameters": [{"name": "rate", "estimate": rate}],
                        "survival": survival,
                        "warnings": [],
                        "crosscheck": {"status": "passed", "max_abs_survival_error": 0.0},
                    }
                )
                draw_curves.append(survival)
            rows.append({"replicate_index": replicate, "status": "complete", "curves": normalized, "failure_reasons": []})
            draws.append({"draw_index": replicate, "curves": draw_curves})
        (self.output / "replicate-results.jsonl").write_bytes(
            b"".join((json.dumps(row, separators=(",", ":")) + "\n").encode() for row in rows)
        )
        (self.output / "joint-survival-draws.candidate.jsonl").write_bytes(
            b"".join((json.dumps(row, separators=(",", ":")) + "\n").encode() for row in draws)
        )
        shutil.copy2(ADAPTER_PATH, self.output / ADAPTER_PATH.name)
        (self.output / "session-info.txt").write_text("R session")
        (self.output / "execution.log").write_text("exit_code: 0")
        adapter_raw = (self.output / ADAPTER_PATH.name).read_bytes()
        session_raw = (self.output / "session-info.txt").read_bytes()
        log_raw = (self.output / "execution.log").read_bytes()
        manifest = {
            "schema_version": "0.1.0",
            "execution_id": "bootstrap-1",
            "status": "complete",
            "request": {"path": "heor/paired-survival-bootstrap-request.json", "sha256": digest(self.request_raw)},
            "analysis": self.request["analysis"],
            "partitioned_survival": self.request["partitioned_survival"],
            "curve_materializations": self.request["curve_materializations"],
            "source_data": {
                field: self.request["source_data"][field]
                for field in ("path", "sha256", "row_count", "strategy_counts")
            },
            "runtime": {
                "backend": "survHE",
                "method": "paired_patient_bootstrap",
                "r_version": "R version 4.6.1",
                "rscript_sha256": "a" * 64,
                "package_versions": self.request["runtime"]["expected_packages"],
                "adapter_path": f"heor/paired-survival-bootstrap-executions/bootstrap-1/{ADAPTER_PATH.name}",
                "adapter_sha256": digest(adapter_raw),
                "session_info_path": "heor/paired-survival-bootstrap-executions/bootstrap-1/session-info.txt",
                "session_info_sha256": digest(session_raw),
                "execution_log_path": "heor/paired-survival-bootstrap-executions/bootstrap-1/execution.log",
                "execution_log_sha256": digest(log_raw),
            },
            "bootstrap": {
                field: self.request["bootstrap"][field]
                for field in (
                    "method",
                    "rng",
                    "rng_version",
                    "seed",
                    "iterations",
                    "resampling_unit",
                    "strategy_resampling_design",
                    "endpoint_sampling",
                    "between_strategy_assumption",
                    "time_grid_years",
                )
            }
            | {
                "evaluator": {"id": EVALUATOR, "sha256": digest(EVALUATOR_PATH.read_bytes())},
                "curve_order": [curve["target_path"] for curve in self.curves],
                "resampling_plan": self._output_binding("bootstrap-plan.csv", PLAN_FORMAT, 1000),
                "replicate_results": self._output_binding("replicate-results.jsonl", REPLICATE_FORMAT, 1000),
                "candidate_draws": self._output_binding("joint-survival-draws.candidate.jsonl", DRAW_FORMAT, 1000),
                "completed_replicates": 1000,
                "failed_replicates": 0,
                "cross_implementation_complete": True,
                "curve_coherence_complete": True,
                "eligible_for_joint_packaging": True,
            },
            "limitations": ["Test fixture only."],
            "human_gate": {
                "state": "awaiting_bootstrap_method_review",
                "required_action": "review_paired_bootstrap_before_joint_packaging",
            },
        }
        path = self.output / "result-manifest.json"
        write_json(path, manifest)
        return path

    def _manifest(self) -> dict:
        return json.loads(self.manifest_path.read_text())

    def test_complete_request_and_result_pass(self) -> None:
        request_errors, facts = validate_request(self.request, self.workspace)
        self.assertEqual(request_errors, [])
        self.assertEqual(facts["strategy_counts"], {"baseline": 2, "intervention": 2})
        errors, result = audit_result(self.manifest_path, self.workspace)
        self.assertEqual(errors, [])
        self.assertTrue(result["complete"])
        self.assertTrue(result["eligible_for_joint_packaging"])
        self.assertEqual(result["completed_replicates"], 1000)

    def test_request_rejects_independent_endpoint_sampling_and_family_drift(self) -> None:
        request = copy.deepcopy(self.request)
        request["bootstrap"]["endpoint_sampling"] = "independent"
        request["bootstrap"]["curves"][0]["family"] = "weibull"
        errors, _ = validate_request(request, self.workspace)
        self.assertTrue(any("reuse subject indices" in error for error in errors))
        self.assertTrue(any("selected materialized" in error for error in errors))

    def test_plan_tamper_fails_even_when_hash_is_updated(self) -> None:
        plan = self.output / "bootstrap-plan.csv"
        lines = plan.read_text().splitlines()
        cells = lines[1].split(",")
        cells[1], cells[2] = "2", "0"
        lines[1] = ",".join(cells)
        plan.write_text("\n".join(lines) + "\n")
        manifest = self._manifest()
        manifest["bootstrap"]["resampling_plan"]["sha256"] = digest(plan.read_bytes())
        write_json(self.manifest_path, manifest)
        errors, _ = audit_result(self.manifest_path, self.workspace)
        self.assertTrue(any("do not reproduce" in error for error in errors))

    def test_parameter_and_candidate_tamper_fail_closed(self) -> None:
        replicate_path = self.output / "replicate-results.jsonl"
        rows = replicate_path.read_text().splitlines()
        first = json.loads(rows[0])
        first["curves"][0]["parameters"][0]["estimate"] = 0.31
        rows[0] = json.dumps(first, separators=(",", ":"))
        replicate_path.write_text("\n".join(rows) + "\n")
        candidate_path = self.output / "joint-survival-draws.candidate.jsonl"
        candidate_rows = candidate_path.read_text().splitlines()
        candidate = json.loads(candidate_rows[0])
        candidate["curves"][0][1] += 0.01
        candidate_rows[0] = json.dumps(candidate, separators=(",", ":"))
        candidate_path.write_text("\n".join(candidate_rows) + "\n")
        manifest = self._manifest()
        manifest["bootstrap"]["replicate_results"]["sha256"] = digest(replicate_path.read_bytes())
        manifest["bootstrap"]["candidate_draws"]["sha256"] = digest(candidate_path.read_bytes())
        write_json(self.manifest_path, manifest)
        errors, _ = audit_result(self.manifest_path, self.workspace)
        self.assertTrue(any("crosscheck" in error for error in errors))
        self.assertTrue(any("candidate_draws" in error for error in errors))

    def test_adapter_tamper_fails_after_hash_update(self) -> None:
        adapter = self.output / ADAPTER_PATH.name
        adapter.write_bytes(adapter.read_bytes() + b"\n# tamper\n")
        manifest = self._manifest()
        manifest["runtime"]["adapter_sha256"] = digest(adapter.read_bytes())
        write_json(self.manifest_path, manifest)
        errors, _ = audit_result(self.manifest_path, self.workspace)
        self.assertTrue(any("current fixed adapter" in error for error in errors))

    def test_valid_incomplete_result_is_auditable_but_not_eligible(self) -> None:
        replicate_path = self.output / "replicate-results.jsonl"
        rows = replicate_path.read_text().splitlines()
        first = json.loads(rows[0])
        first["status"] = "failed"
        first["curves"][0] = {
            **self.curves[0],
            "status": "failed",
            "parameterization": "",
            "parameters": [],
            "survival": [],
            "warnings": ["fit failed"],
            "crosscheck": {"status": "fit_failed", "max_abs_survival_error": None},
        }
        first["failure_reasons"] = ["fit failed"]
        rows[0] = json.dumps(first, separators=(",", ":"))
        replicate_path.write_text("\n".join(rows) + "\n")
        manifest = self._manifest()
        manifest["status"] = "incomplete"
        manifest["bootstrap"]["replicate_results"]["sha256"] = digest(replicate_path.read_bytes())
        manifest["bootstrap"]["candidate_draws"] = None
        manifest["bootstrap"]["completed_replicates"] = 999
        manifest["bootstrap"]["failed_replicates"] = 1
        manifest["bootstrap"]["cross_implementation_complete"] = False
        manifest["bootstrap"]["eligible_for_joint_packaging"] = False
        write_json(self.manifest_path, manifest)
        errors, result = audit_result(self.manifest_path, self.workspace)
        self.assertEqual(errors, [])
        self.assertTrue(result["complete"])
        self.assertFalse(result["eligible_for_joint_packaging"])

    def test_pcg_plan_has_stable_first_replicates(self) -> None:
        rows = list(bootstrap_frequencies([[0, 1], [2, 3]], 3, 20260715))
        self.assertEqual(rows, [[1, 1, 1, 1], [1, 1, 2, 0], [0, 2, 1, 1]])

    def test_output_directory_rejects_a_symlinked_parent(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_name, tempfile.TemporaryDirectory() as outside_name:
            workspace = Path(workspace_name)
            (workspace / "heor").symlink_to(Path(outside_name), target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symlink"):
                resolve_output_directory(
                    workspace,
                    "heor/paired-survival-bootstrap-executions/escape",
                )
            self.assertEqual(list(Path(outside_name).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
