#!/usr/bin/env python3
"""Adversarial tests for bounded AI4HEOR natural-history model calibration."""

from __future__ import annotations

import copy
import json
import math
import subprocess
import sys
import tempfile
import unittest
from itertools import product
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
SKILL = ROOT / "runtime/skills/core/heor-model-calibration"
SCRIPTS = SKILL / "scripts"
sys.path.insert(0, str(SCRIPTS))

from calibration_contract import (  # noqa: E402
    REQUIRED_REVIEW_CHECKS,
    audit_result,
    digest,
    execute_calibration,
    validate_request,
)


def write_json(path: Path, value: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return digest(raw)


def _matmul(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    return [
        [math.fsum(left[row][inner] * right[inner][column] for inner in range(len(right))) for column in range(len(right[0]))]
        for row in range(len(left))
    ]


def _uniformized_transition(rates: dict[tuple[int, int], float], state_count: int) -> list[list[float]]:
    generator = [[0.0] * state_count for _ in range(state_count)]
    for (source, destination), rate in rates.items():
        generator[source][destination] = rate
        generator[source][source] -= rate
    uniformization_rate = max(-generator[index][index] for index in range(state_count))
    if uniformization_rate == 0:
        return [[1.0 if row == column else 0.0 for column in range(state_count)] for row in range(state_count)]
    embedded = [
        [
            (1.0 if row == column else 0.0) + generator[row][column] / uniformization_rate
            for column in range(state_count)
        ]
        for row in range(state_count)
    ]
    power = [[1.0 if row == column else 0.0 for column in range(state_count)] for row in range(state_count)]
    probability = math.exp(-uniformization_rate)
    transition = [[probability * value for value in row] for row in power]
    for order in range(1, 512):
        power = _matmul(power, embedded)
        probability *= uniformization_rate / order
        for row, column in product(range(state_count), repeat=2):
            transition[row][column] += probability * power[row][column]
        if probability < 1e-16 and order > uniformization_rate:
            break
    return transition


def fixture_occupancy(incidence: float, case_fatality: float, background_death: float = 0.025) -> list[list[float]]:
    transition = _uniformized_transition(
        {(0, 1): incidence, (0, 2): background_death, (1, 2): case_fatality},
        3,
    )
    rows = [[1.0, 0.0, 0.0]]
    for _ in range(12):
        current = rows[-1]
        rows.append(
            [math.fsum(current[source] * transition[source][destination] for source in range(3)) for destination in range(3)]
        )
    return rows


def build_workspace(root: Path) -> dict[str, Any]:
    evidence_sha = write_json(
        root / "heor/evidence-synthesis.json",
        {"records": ["natural-history-source", "parameter-bound-source"]},
    )
    truth = fixture_occupancy(0.11, 0.18)
    target_specs = [
        ("disease-c3", "calibration", 3, "diseased"),
        ("healthy-c5", "calibration", 5, "healthy"),
        ("death-c7", "calibration", 7, "dead"),
        ("death-c10", "calibration", 10, "dead"),
        ("disease-c12-heldout", "validation", 12, "diseased"),
    ]
    state_index = {"healthy": 0, "diseased": 1, "dead": 2}
    request = {
        "schema_version": "0.1.0",
        "calibration_id": "calibration-test-001",
        "status": "ready_for_execution",
        "question": {
            "population": "Synthetic untreated natural-history cohort",
            "purpose": "Estimate two unobservable transition rates before economic evaluation",
            "time_origin": "Disease-free cohort entry",
            "intended_use": "Candidate natural-history parameters for later Human review",
        },
        "evidence_synthesis": {
            "path": "heor/evidence-synthesis.json",
            "sha256": evidence_sha,
            "included_record_ids": ["natural-history-source", "parameter-bound-source"],
        },
        "model": {
            "type": "homogeneous_continuous_time_cohort_state_transition",
            "states": ["healthy", "diseased", "dead"],
            "initial_distribution": [1.0, 0.0, 0.0],
            "cycle_length_years": 1.0,
            "cycles": 12,
            "matrix_exponential": {
                "method": "uniformization",
                "tail_tolerance": 1e-14,
                "maximum_terms": 512,
            },
            "transitions": [
                {
                    "id": "healthy-to-diseased",
                    "from_state": "healthy",
                    "to_state": "diseased",
                    "source": "calibrated_parameter",
                    "parameter_id": "incidence-rate",
                },
                {
                    "id": "healthy-to-dead",
                    "from_state": "healthy",
                    "to_state": "dead",
                    "source": "fixed_rate",
                    "rate_per_year": 0.025,
                    "rationale": "Synthetic fixed background mortality.",
                    "evidence_record_ids": ["natural-history-source"],
                },
                {
                    "id": "diseased-to-dead",
                    "from_state": "diseased",
                    "to_state": "dead",
                    "source": "calibrated_parameter",
                    "parameter_id": "case-fatality-rate",
                },
            ],
        },
        "parameters": [
            {
                "id": "incidence-rate",
                "label": "Annual disease incidence rate",
                "transition_id": "healthy-to-diseased",
                "unit": "per_year",
                "lower": 0.02,
                "upper": 0.25,
                "search_scale": "linear",
                "status": "unobservable_natural_history_parameter",
                "rationale": "Bound chosen before fitting from synthetic domain knowledge.",
                "evidence_record_ids": ["parameter-bound-source"],
            },
            {
                "id": "case-fatality-rate",
                "label": "Annual case-fatality rate",
                "transition_id": "diseased-to-dead",
                "unit": "per_year",
                "lower": 0.05,
                "upper": 0.4,
                "search_scale": "linear",
                "status": "unobservable_natural_history_parameter",
                "rationale": "Bound chosen before fitting from synthetic domain knowledge.",
                "evidence_record_ids": ["parameter-bound-source"],
            },
        ],
        "targets": [
            {
                "id": target_id,
                "role": role,
                "cycle": cycle,
                "state": state,
                "measure": "state_occupancy_proportion",
                "observed": truth[cycle][state_index[state]],
                "standard_error": 0.02,
                "population_alignment": "Exact synthetic target population and time origin.",
                "evidence_record_ids": ["natural-history-source"],
            }
            for target_id, role, cycle, state in target_specs
        ],
        "goodness_of_fit": {
            "training_loss": "sum_squared_standardized_residuals",
            "standard_error_use": "target_specific_scaling_only",
            "target_covariance": "not_modeled",
            "automatic_fit_thresholds": "none",
        },
        "search": {
            "method": "deterministic_grid_multistart_pattern_search",
            "grid_levels_per_parameter": 7,
            "local_start_count": 8,
            "minimum_normalized_step": 1e-7,
            "maximum_iterations_per_start": 500,
            "tie_break": "objective_then_lexicographic_normalized_parameters",
        },
        "identifiability": {
            "method": "finite_difference_scaled_target_jacobian",
            "normalized_derivative_step": 1e-5,
            "relative_rank_tolerance": 1e-8,
            "automatic_acceptance_thresholds": "none",
        },
        "output": {"directory": "heor/model-calibration-runs/calibration-test-001"},
        "human_authorization": {
            "actor": "test-researcher",
            "authorized_at": "2026-07-17T00:00:00Z",
            "scope": "execute_local_model_calibration",
        },
        "limitations": [
            "Synthetic fixture.",
            "Point calibration only; target dependence and calibrated-parameter uncertainty are not modeled.",
        ],
        "human_gate": {"status": "awaiting_method_review", "required_checks": REQUIRED_REVIEW_CHECKS},
    }
    write_json(root / "heor/model-calibration-request.json", request)
    return request


class ModelCalibrationTests(unittest.TestCase):
    def test_valid_request_recovers_rates_and_keeps_validation_held_out(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root)
            errors, facts = validate_request(request, root)
            self.assertEqual(errors, [])
            analysis = execute_calibration(request, facts)
            best = analysis["best_fit"]["parameters"]
            self.assertAlmostEqual(best["incidence-rate"], 0.11, delta=0.01)
            self.assertAlmostEqual(best["case-fatality-rate"], 0.18, delta=0.015)
            self.assertEqual(analysis["search"]["training_target_count"], 4)
            self.assertEqual(analysis["search"]["validation_target_count"], 1)
            self.assertTrue(analysis["identifiability"]["full_rank"])
            held_out = [target for target in analysis["target_fit"] if target["role"] == "validation"]
            self.assertEqual(len(held_out), 1)

    def test_runner_and_portable_audit_replay_complete_search(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_workspace(root)
            run = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPTS / "run_model_calibration.py"),
                    "--workspace",
                    str(root),
                    "--request",
                    "heor/model-calibration-request.json",
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            result = root / "heor/model-calibration-runs/calibration-test-001/manifest.json"
            audit = audit_result(result, root)
            self.assertTrue(audit["complete"], audit["errors"])
            manifest = json.loads(result.read_text())
            self.assertFalse(manifest["human_gate"]["automatic_model_input_update"])
            self.assertEqual(manifest["cross_implementation"]["portable_replay"], "complete_search_and_diagnostics")

    def test_requires_training_and_held_out_validation_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root)
            for target in request["targets"]:
                target["role"] = "calibration"
            errors, _ = validate_request(request, root)
            self.assertTrue(any("held-out validation" in error for error in errors))
            request = build_workspace(root)
            request["targets"] = request["targets"][:2]
            errors, _ = validate_request(request, root)
            self.assertTrue(any("more training targets than parameters" in error for error in errors))

    def test_rejects_automatic_thresholds_covariance_claims_and_unknown_authority(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root)
            request["goodness_of_fit"]["automatic_fit_thresholds"] = "rmse_below_1"
            request["goodness_of_fit"]["target_covariance"] = "implicitly_independent"
            request["human_approval"] = {"approved": True}
            errors, _ = validate_request(request, root)
            self.assertTrue(any("goodness_of_fit" in error for error in errors))
            self.assertTrue(any("fields" in error or "authority" in error for error in errors))

    def test_invalid_rate_bounds_and_transition_graph_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root)
            request["parameters"][0]["lower"] = request["parameters"][0]["upper"]
            request["model"]["transitions"].append(copy.deepcopy(request["model"]["transitions"][0]))
            errors, _ = validate_request(request, root)
            self.assertTrue(any("bounds" in error for error in errors))
            self.assertTrue(any("transition" in error and "unique" in error for error in errors))

    def test_every_parameter_and_target_evidence_reference_must_be_bound(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root)
            request["parameters"][0]["evidence_record_ids"] = ["unbound-parameter-source"]
            request["targets"][0]["evidence_record_ids"] = ["unbound-target-source"]
            errors, _ = validate_request(request, root)
            self.assertTrue(any("parameters[0]" in error and "bound evidence" in error for error in errors))
            self.assertTrue(any("targets[0]" in error and "bound evidence" in error for error in errors))

    def test_local_nonidentifiability_is_reported_not_silently_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root)
            request["model"]["transitions"][1] = {
                "id": "healthy-to-dead",
                "from_state": "healthy",
                "to_state": "dead",
                "source": "calibrated_parameter",
                "parameter_id": "background-death-rate",
            }
            request["model"]["transitions"][2] = {
                "id": "diseased-to-dead",
                "from_state": "diseased",
                "to_state": "dead",
                "source": "fixed_rate",
                "rate_per_year": 0.18,
                "rationale": "Synthetic fixed disease mortality.",
                "evidence_record_ids": ["natural-history-source"],
            }
            request["parameters"][1].update(
                {
                    "id": "background-death-rate",
                    "label": "Annual background death rate",
                    "transition_id": "healthy-to-dead",
                    "lower": 0.005,
                    "upper": 0.08,
                }
            )
            truth = fixture_occupancy(0.11, 0.18)
            for index, target in enumerate(request["targets"]):
                cycle = (2, 4, 6, 8, 10)[index]
                target.update(
                    {
                        "id": f"healthy-c{cycle}",
                        "role": "validation" if index == 4 else "calibration",
                        "cycle": cycle,
                        "state": "healthy",
                        "observed": truth[cycle][0],
                    }
                )
            errors, facts = validate_request(request, root)
            self.assertEqual(errors, [])
            analysis = execute_calibration(request, facts)
            self.assertFalse(analysis["identifiability"]["full_rank"])
            self.assertTrue(any("identifiability" in warning.lower() for warning in analysis["warnings"]))

    def test_tampered_manifest_and_search_trace_fail_replay(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_workspace(root)
            subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPTS / "run_model_calibration.py"),
                    "--workspace",
                    str(root),
                    "--request",
                    "heor/model-calibration-request.json",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            result = root / "heor/model-calibration-runs/calibration-test-001/manifest.json"
            manifest = json.loads(result.read_text())
            manifest["best_fit"]["objective"] += 0.5
            write_json(result, manifest)
            audit = audit_result(result, root)
            self.assertFalse(audit["complete"])
            self.assertTrue(any("deterministic replay" in error for error in audit["errors"]))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_workspace(root)
            subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(SCRIPTS / "run_model_calibration.py"),
                    "--workspace",
                    str(root),
                    "--request",
                    "heor/model-calibration-request.json",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            result = root / "heor/model-calibration-runs/calibration-test-001/manifest.json"
            trace = root / "heor/model-calibration-runs/calibration-test-001/search.csv"
            trace.write_bytes(trace.read_bytes() + b"tampered\n")
            audit = audit_result(result, root)
            self.assertFalse(audit["complete"])
            self.assertTrue(any("search" in error.lower() for error in audit["errors"]))


if __name__ == "__main__":
    unittest.main()
