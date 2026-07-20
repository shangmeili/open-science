#!/usr/bin/env python3
"""Adversarial tests for the bounded AI4HEOR anchored MAIC capability."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "runtime/skills/core/heor-population-adjusted-comparison"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

from pac_contract import (  # noqa: E402
    Pcg32,
    REQUIRED_REVIEW_CHECKS,
    audit_result,
    calibrate,
    digest,
    effect_estimate,
    load_json,
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


def build_workspace(root: Path, measure: str = "mean_difference") -> dict[str, Any]:
    evidence_sha = write_json(root / "heor/evidence-synthesis.json", {"records": ["trial-ab-record", "trial-ac-record", "modifier-record"]})
    rows = ["subject_id,treatment,outcome,baseline"]
    for arm_index, arm in enumerate(("a", "b")):
        for index in range(40):
            baseline = (index + arm_index * 0.25) / 20
            if measure == "mean_difference":
                outcome = 5 + 0.4 * baseline + (1.0 + 0.3 * baseline if arm == "b" else 0)
            else:
                outcome = 1 if (index + arm_index * 3) % 5 in {0, 1} else 0
            rows.append(f"{arm}{index + 1:03d},{arm},{outcome},{baseline:.12g}")
    source_sha = write_bytes(root / "heor/population-adjusted-data/trial-ab.csv", ("\n".join(rows) + "\n").encode())
    scale = "identity" if measure == "mean_difference" else "logit"
    aggregate = {
        "schema_version": "0.1.0",
        "trial_id": "trial-ac",
        "target_population": "Trial AC randomized population",
        "common_comparator_id": "a",
        "aggregate_treatment_id": "c",
        "outcome": "Response at week 12",
        "timepoint": "12 weeks",
        "effect": {"measure": measure, "scale": scale, "estimate": 0.35, "se": 0.12},
        "target_moments": [{"id": "baseline", "mean": 0.8}],
        "source_ids": ["trial-ac-record"],
        "limitations": ["Synthetic aggregate fixture."],
    }
    aggregate_sha = write_json(root / "heor/population-adjusted-data/trial-ac-aggregate.json", aggregate)
    request = {
        "schema_version": "0.1.0",
        "execution_id": "maic-test-001",
        "status": "ready_for_execution",
        "method": {
            "family": "anchored_maic",
            "network": "connected_two_trial_common_comparator",
            "trial_relationship": "independent_parallel_randomized_trials",
            "ipd_trial_id": "trial-ab",
            "aggregate_trial_id": "trial-ac",
            "common_comparator_id": "a",
            "ipd_treatment_id": "b",
            "aggregate_treatment_id": "c",
            "target_population": "Trial AC randomized population",
            "outcome": "Response at week 12",
            "timepoint": "12 weeks",
            "estimand": "Marginal B versus C effect in Trial AC",
        },
        "evidence_synthesis": {
            "path": "heor/evidence-synthesis.json",
            "sha256": evidence_sha,
            "included_record_ids": ["trial-ab-record", "trial-ac-record", "modifier-record"],
        },
        "source_data": {
            "classification": "restricted",
            "execution_boundary": "local_only",
            "format": "ipd_csv",
            "path": "heor/population-adjusted-data/trial-ab.csv",
            "sha256": source_sha,
            "columns": ["subject_id", "treatment", "outcome", "baseline"],
            "row_count": 80,
            "contains_direct_identifiers": False,
            "missing_policy": "reject",
            "treatment_assignment": "randomized_parallel_two_arm",
        },
        "aggregate_evidence": {
            "path": "heor/population-adjusted-data/trial-ac-aggregate.json",
            "sha256": aggregate_sha,
        },
        "effect_modifiers": [
            {
                "id": "baseline",
                "column": "baseline",
                "label": "Baseline measure",
                "rationale": "Prespecified scale-specific effect modifier for the synthetic fixture.",
                "evidence_record_ids": ["modifier-record"],
            }
        ],
        "effect": {"measure": measure, "scale": scale, "confidence_level": 0.95, "favorable_direction": "higher"},
        "weighting": {
            "method": "method_of_moments_exponential_tilting",
            "balance_moments": "means",
            "normalization": "mean_one",
            "convergence_tolerance": 1e-10,
            "max_iterations": 200,
            "weight_cap": "none",
            "trimming": "none",
        },
        "uncertainty": {
            "method": "stratified_nonparametric_bootstrap_refit",
            "iterations": 1000,
            "seed": 123456,
            "prng": {"algorithm": "pcg32-xsh-rr", "version": "1"},
            "failure_policy": "retain_and_block_review",
        },
        "output": {"directory": "heor/population-adjusted-comparison-runs/maic-test-001"},
        "study_provenance": [
            {"trial_id": "trial-ab", "evidence_record_ids": ["trial-ab-record"], "risk_of_bias": "low"},
            {"trial_id": "trial-ac", "evidence_record_ids": ["trial-ac-record"], "risk_of_bias": "some_concerns"},
        ],
        "human_authorization": {"actor": "test-researcher", "authorized_at": "2026-07-16T00:00:00Z", "scope": "execute_local_anchored_maic"},
        "limitations": ["Synthetic fixture; no scientific interpretation."],
        "human_gate": {"status": "awaiting_method_review", "required_checks": REQUIRED_REVIEW_CHECKS},
    }
    write_json(root / "heor/population-adjusted-comparison-request.json", request)
    return request


class PopulationAdjustedComparisonTests(unittest.TestCase):
    def test_valid_continuous_request_calibrates_and_changes_the_target_effect(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root)
            errors, facts = validate_request(request, root)
            self.assertEqual(errors, [])
            calibration = facts["preflight_calibration"]
            self.assertAlmostEqual(calibration["weighted_means"][0], 0.8, places=9)
            adjusted = effect_estimate(facts["rows"], calibration["weights"], "a", "b", "mean_difference")
            unadjusted = effect_estimate(facts["rows"], [1.0] * 80, "a", "b", "mean_difference")
            self.assertNotAlmostEqual(adjusted, unadjusted, places=6)

    def test_valid_binary_request_uses_marginal_weighted_log_odds(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root, "log_odds_ratio")
            errors, facts = validate_request(request, root)
            self.assertEqual(errors, [])
            estimate = effect_estimate(facts["rows"], facts["preflight_calibration"]["weights"], "a", "b", "log_odds_ratio")
            self.assertTrue(abs(estimate) < 100)

    def test_unanchored_and_automatic_trimming_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root)
            request["method"]["network"] = "disconnected"
            request["weighting"]["trimming"] = "automatic"
            errors, _ = validate_request(request, root)
            self.assertTrue(any("anchored_maic" in error for error in errors))
            self.assertTrue(any("trimming" in error for error in errors))

    def test_target_moment_must_cover_every_human_selected_modifier(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root)
            aggregate_path = root / request["aggregate_evidence"]["path"]
            aggregate, _ = load_json(aggregate_path)
            aggregate["target_moments"] = []
            request["aggregate_evidence"]["sha256"] = write_json(aggregate_path, aggregate)
            errors, _ = validate_request(request, root)
            self.assertTrue(any("target_moments" in error for error in errors))

    def test_stale_ipd_and_duplicate_subjects_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root)
            path = root / request["source_data"]["path"]
            path.write_bytes(path.read_bytes() + b"a001,a,1,0.2\n")
            errors, _ = validate_request(request, root)
            self.assertTrue(any("sha256" in error for error in errors))
            request["source_data"]["sha256"] = digest(path.read_bytes())
            request["source_data"]["row_count"] = 81
            errors, _ = validate_request(request, root)
            self.assertTrue(any("repeats subject_id" in error or "unique" in error for error in errors))

    def test_target_outside_ipd_support_fails_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root)
            aggregate_path = root / request["aggregate_evidence"]["path"]
            aggregate, _ = load_json(aggregate_path)
            aggregate["target_moments"][0]["mean"] = 100.0
            request["aggregate_evidence"]["sha256"] = write_json(aggregate_path, aggregate)
            errors, _ = validate_request(request, root)
            self.assertTrue(any("preflight" in error for error in errors))

    def test_pcg32_stream_is_version_stable(self) -> None:
        rng = Pcg32(42)
        self.assertEqual([rng.next_u32() for _ in range(5)], [2707161783, 2068313097, 3122475824, 2211639955, 3215226955])

    def test_runner_and_portable_replay_bind_every_result_byte(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_workspace(root)
            completed = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPTS / "run_anchored_maic.py"),
                    "--workspace",
                    str(root),
                    "--request",
                    "heor/population-adjusted-comparison-request.json",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=60,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr + completed.stdout)
            result_path = root / "heor/population-adjusted-comparison-runs/maic-test-001/manifest.json"
            audit = audit_result(result_path, root)
            self.assertEqual(audit["errors"], [])
            self.assertTrue(audit["reviewable"])
            result, _ = load_json(result_path)
            result["effects"]["indirect_ipd_vs_aggregate"]["estimate"] += 0.01
            write_json(result_path, result)
            audit = audit_result(result_path, root)
            self.assertTrue(any("effects" in error for error in audit["errors"]))

    def test_draw_tampering_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_workspace(root)
            subprocess.run(
                [sys.executable, "-B", str(SCRIPTS / "run_anchored_maic.py"), "--workspace", str(root), "--request", "heor/population-adjusted-comparison-request.json"],
                check=True,
                capture_output=True,
                text=True,
                timeout=60,
            )
            result_path = root / "heor/population-adjusted-comparison-runs/maic-test-001/manifest.json"
            result, _ = load_json(result_path)
            draws = root / result["bootstrap"]["draws"]["path"]
            draws.write_bytes(draws.read_bytes() + b"tamper\n")
            audit = audit_result(result_path, root)
            self.assertTrue(any("draws sha256" in error for error in audit["errors"]))


if __name__ == "__main__":
    unittest.main()
