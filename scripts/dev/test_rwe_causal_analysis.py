#!/usr/bin/env python3
"""Adversarial tests for the bounded AI4HEOR RWE causal-analysis capability."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "runtime/skills/core/heor-rwe-causal-analysis"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

from rwe_causal_contract import (  # noqa: E402
    Pcg32,
    REQUIRED_REVIEW_CHECKS,
    audit_result,
    digest,
    execute_bootstrap,
    point_analysis,
    validate_request,
)


def write_json(path: Path, value: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return digest(raw)


def write_bytes(path: Path, raw: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return digest(raw)


def build_workspace(root: Path, row_count: int = 160) -> dict[str, Any]:
    evidence_sha = write_json(
        root / "heor/evidence-synthesis.json",
        {"records": ["rwe-source-record", "confounder-record"]},
    )
    csv_rows = ["subject_id,treatment,outcome,age,baseline_risk"]
    for index in range(row_count):
        age = 35 + (index * 7) % 45
        baseline_risk = 1 if index % 5 in {0, 1} else 0
        treatment_threshold = 28 + int((age - 35) * 0.55) + 15 * baseline_risk
        treatment = "treatment" if (index * 37 + 11) % 100 < treatment_threshold else "comparator"
        outcome_threshold = 13 + int((age - 35) * 0.28) + 18 * baseline_risk - (5 if treatment == "treatment" else 0)
        outcome = 1 if (index * 53 + 7) % 100 < outcome_threshold else 0
        csv_rows.append(f"p{index + 1:04d},{treatment},{outcome},{age},{baseline_risk}")
    source_sha = write_bytes(root / "heor/rwe-causal-data/cohort.csv", ("\n".join(csv_rows) + "\n").encode())
    request = {
        "schema_version": "0.1.0",
        "execution_id": "rwe-test-001",
        "status": "ready_for_execution",
        "target_trial": {
            "design": "active_comparator_new_user_observational_cohort",
            "population": "Synthetic eligible new-user cohort",
            "eligibility_criteria": ["Eligible at treatment initiation", "No prior use during washout"],
            "treatment_strategy": {"id": "treatment", "label": "Treatment initiators"},
            "comparator_strategy": {"id": "comparator", "label": "Active-comparator initiators"},
            "assignment": "observational_at_baseline",
            "time_zero": "Eligible treatment initiation",
            "follow_up": "Fixed complete 180-day follow-up",
            "outcome": "Binary synthetic event by day 180",
            "causal_contrast": "intention_to_treat_analog",
        },
        "estimand": {
            "population": "analyzed_source_cohort",
            "treatment_contrast": "treatment_vs_comparator",
            "measure": "risk_difference",
            "favorable_direction": "lower",
        },
        "evidence_synthesis": {
            "path": "heor/evidence-synthesis.json",
            "sha256": evidence_sha,
            "included_record_ids": ["rwe-source-record", "confounder-record"],
        },
        "source_data": {
            "classification": "restricted",
            "execution_boundary": "local_only",
            "format": "one_row_per_person_csv",
            "path": "heor/rwe-causal-data/cohort.csv",
            "sha256": source_sha,
            "columns": ["subject_id", "treatment", "outcome", "age", "baseline_risk"],
            "row_count": row_count,
            "contains_direct_identifiers": False,
            "missing_policy": "reject",
            "one_row_per_person": True,
            "baseline_covariates_only": True,
            "fixed_complete_follow_up": True,
            "treatment_assignment": "observational_active_comparator_new_user",
        },
        "confounders": [
            {
                "id": "age",
                "column": "age",
                "label": "Age at initiation",
                "type": "continuous",
                "timing": "baseline_pre_treatment",
                "role": "human_prespecified_common_cause",
                "rationale": "Synthetic baseline common cause chosen before analysis.",
                "evidence_record_ids": ["confounder-record"],
            },
            {
                "id": "baseline-risk",
                "column": "baseline_risk",
                "label": "Baseline risk",
                "type": "binary",
                "timing": "baseline_pre_treatment",
                "role": "human_prespecified_common_cause",
                "rationale": "Synthetic baseline common cause chosen before analysis.",
                "evidence_record_ids": ["confounder-record"],
            },
        ],
        "propensity_score": {
            "model": "logistic_regression_main_effects",
            "treatment_encoding": "treatment_strategy_id_is_one",
            "intercept": True,
            "continuous_standardization": "sample_mean_standard_deviation",
            "nonlinear_terms": "none",
            "interactions": "none",
            "penalty": "none",
            "convergence_tolerance": 1e-10,
            "max_iterations": 100,
        },
        "weighting": {
            "estimand": "source_cohort_ate",
            "method": "stabilized_inverse_probability_of_treatment_weighting",
            "numerator": "marginal_treatment_probability",
            "trimming": "none",
            "weight_cap": "none",
            "renormalization": "none",
        },
        "diagnostics": {
            "balance_metric": "standardized_mean_difference",
            "balance_denominator": "state_specific_two_arm_pooled_standard_deviation",
            "overlap": "empirical_propensity_range_intersection",
            "automatic_acceptance_thresholds": "none",
        },
        "uncertainty": {
            "method": "arm_stratified_nonparametric_bootstrap_refit",
            "iterations": 1000,
            "seed": 123456,
            "prng": {"algorithm": "pcg32-xsh-rr", "version": "1"},
            "interval": "normal_bootstrap_95_percent",
            "failure_policy": "retain_and_block_review",
        },
        "output": {"directory": "heor/rwe-causal-analysis-runs/rwe-test-001"},
        "human_authorization": {
            "actor": "test-researcher",
            "authorized_at": "2026-07-16T00:00:00Z",
            "scope": "execute_local_rwe_causal_analysis",
        },
        "limitations": ["Synthetic fixture; no causal or scientific interpretation."],
        "human_gate": {"status": "awaiting_method_review", "required_checks": REQUIRED_REVIEW_CHECKS},
    }
    write_json(root / "heor/rwe-causal-analysis-request.json", request)
    return request


class RweCausalAnalysisTests(unittest.TestCase):
    def test_valid_request_fits_stabilized_ate_weights_and_changes_balance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root)
            errors, facts = validate_request(request, root)
            self.assertEqual(errors, [])
            analysis = point_analysis(request, facts)
            self.assertLess(analysis["max_abs_post_smd"], analysis["max_abs_pre_smd"])
            self.assertAlmostEqual(analysis["weight_summary"]["overall"]["mean"], 1.0, delta=0.05)
            self.assertTrue(-1 <= analysis["weighted_effects"]["risk_difference"] <= 1)

    def test_runner_and_portable_audit_bind_complete_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_workspace(root)
            run = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "run_rwe_causal_analysis.py"),
                    "--workspace",
                    str(root),
                    "--request",
                    "heor/rwe-causal-analysis-request.json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            result = root / "heor/rwe-causal-analysis-runs/rwe-test-001/manifest.json"
            audit = audit_result(result, root)
            self.assertTrue(audit["complete"], audit["errors"])
            manifest = json.loads(result.read_text())
            self.assertFalse(manifest["effects"]["causal_validity_determined"])
            self.assertFalse(manifest["human_gate"]["automatic_downstream_use"])

    def test_automatic_design_choices_and_weight_trimming_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root)
            request["target_trial"]["design"] = "automatically_selected_design"
            request["weighting"]["trimming"] = "automatic"
            errors, _ = validate_request(request, root)
            self.assertTrue(any("active_comparator_new_user" in error for error in errors))
            self.assertTrue(any("untrimmed" in error for error in errors))

    def test_post_treatment_or_missing_data_contract_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root)
            request["confounders"][0]["timing"] = "post_treatment"
            request["source_data"]["missing_policy"] = "complete_case"
            errors, _ = validate_request(request, root)
            self.assertTrue(any("baseline common cause" in error for error in errors))
            self.assertTrue(any("complete-case active-comparator" in error for error in errors))

    def test_stale_source_and_duplicate_subjects_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root)
            path = root / request["source_data"]["path"]
            path.write_bytes(path.read_bytes() + b"p0001,treatment,0,50,0\n")
            errors, _ = validate_request(request, root)
            self.assertTrue(any("sha256" in error for error in errors))
            request["source_data"]["sha256"] = digest(path.read_bytes())
            request["source_data"]["row_count"] += 1
            errors, _ = validate_request(request, root)
            self.assertTrue(any("repeats subject_id" in error or "unique" in error for error in errors))

    def test_direct_identifier_column_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root)
            request["confounders"][0]["column"] = "email"
            request["source_data"]["columns"][3] = "email"
            errors, _ = validate_request(request, root)
            self.assertTrue(any("identity" in error or "columns" in error for error in errors))

    def test_tampered_manifest_fails_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_workspace(root)
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "run_rwe_causal_analysis.py"),
                    "--workspace",
                    str(root),
                    "--request",
                    "heor/rwe-causal-analysis-request.json",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            result = root / "heor/rwe-causal-analysis-runs/rwe-test-001/manifest.json"
            manifest = json.loads(result.read_text())
            manifest["effects"]["stabilized_ate_iptw"]["risk_difference"] += 0.01
            write_json(result, manifest)
            audit = audit_result(result, root)
            self.assertFalse(audit["complete"])
            self.assertTrue(any("deterministic replay" in error for error in audit["errors"]))

    def test_bootstrap_refit_failures_are_retained(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root, row_count=80)
            path = root / request["source_data"]["path"]
            raw_rows = path.read_text().splitlines()
            rebuilt = [raw_rows[0]]
            for index, row in enumerate(raw_rows[1:]):
                fields = row.split(",")
                fields[-1] = "1" if index == 0 else "0"
                rebuilt.append(",".join(fields))
            request["source_data"]["sha256"] = write_bytes(path, ("\n".join(rebuilt) + "\n").encode())
            write_json(root / "heor/rwe-causal-analysis-request.json", request)
            errors, facts = validate_request(request, root)
            self.assertEqual(errors, [])
            draws, successful = execute_bootstrap(request, facts)
            self.assertLess(len(successful), len(draws))
            self.assertTrue(any(draw["status"] == "failed" for draw in draws))

    def test_pcg32_stream_is_version_stable(self) -> None:
        rng = Pcg32(42)
        self.assertEqual(
            [rng.next_u32() for _ in range(5)],
            [2707161783, 2068313097, 3122475824, 2211639955, 3215226955],
        )


if __name__ == "__main__":
    unittest.main()
