#!/usr/bin/env python3
"""Portable and adversarial checks for the bounded microsimulation Skill."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / "runtime/skills/core/heor-semi-markov-microsimulation/scripts"
sys.path.insert(0, str(SCRIPTS))

from microsimulation_contract import (  # noqa: E402
    REQUIRED_REVIEW_CHECKS,
    audit_result,
    canonical_json_bytes,
    counter_uniform,
    digest,
    execute_simulation,
    validate_request,
)


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def make_rules(strategy_id: str, *, improved: bool) -> list[dict[str, object]]:
    stable_after = [0.75, 0.17, 0.08] if improved else [0.65, 0.25, 0.10]
    stable_default = [0.84, 0.12, 0.04] if improved else [0.80, 0.15, 0.05]
    return [
        {
            "state_id": "stable",
            "rules": [
                {
                    "id": f"{strategy_id}-stable-after-event",
                    "condition": {
                        "kind": "when",
                        "time_in_state_cycles": {"minimum": 0, "maximum": None},
                        "tracker_counts": [{"tracker_id": "event-count", "minimum": 1, "maximum": None}],
                    },
                    "probabilities": stable_after,
                    "annual_cost": 850.0 if improved else 700.0,
                    "utility": 0.80,
                    "rationale": "Synthetic history-dependent stable-state rule.",
                    "evidence_record_ids": ["model-source", "cost-source"],
                },
                {
                    "id": f"{strategy_id}-stable-default",
                    "condition": {"kind": "otherwise"},
                    "probabilities": stable_default,
                    "annual_cost": 800.0 if improved else 600.0,
                    "utility": 0.84,
                    "rationale": "Synthetic default stable-state rule.",
                    "evidence_record_ids": ["model-source", "cost-source"],
                },
            ],
        },
        {
            "state_id": "event",
            "rules": [
                {
                    "id": f"{strategy_id}-event-early",
                    "condition": {
                        "kind": "when",
                        "time_in_state_cycles": {"minimum": 0, "maximum": 1},
                        "tracker_counts": [],
                    },
                    "probabilities": [0.40, 0.45, 0.15],
                    "annual_cost": 6000.0,
                    "utility": 0.45,
                    "rationale": "Synthetic early time-in-event rule.",
                    "evidence_record_ids": ["model-source", "cost-source"],
                },
                {
                    "id": f"{strategy_id}-event-late",
                    "condition": {
                        "kind": "when",
                        "time_in_state_cycles": {"minimum": 2, "maximum": None},
                        "tracker_counts": [],
                    },
                    "probabilities": [0.25, 0.62, 0.13],
                    "annual_cost": 3500.0,
                    "utility": 0.58,
                    "rationale": "Synthetic later time-in-event rule.",
                    "evidence_record_ids": ["model-source", "cost-source"],
                },
                {
                    "id": f"{strategy_id}-event-fallback",
                    "condition": {"kind": "otherwise"},
                    "probabilities": [0.40, 0.45, 0.15],
                    "annual_cost": 6000.0,
                    "utility": 0.45,
                    "rationale": "Explicit fallback rule.",
                    "evidence_record_ids": ["model-source", "cost-source"],
                },
            ],
        },
        {
            "state_id": "dead",
            "rules": [
                {
                    "id": f"{strategy_id}-dead",
                    "condition": {"kind": "otherwise"},
                    "probabilities": [0.0, 0.0, 1.0],
                    "annual_cost": 0.0,
                    "utility": 0.0,
                    "rationale": "Absorbing death state.",
                    "evidence_record_ids": ["model-source"],
                }
            ],
        },
    ]


def make_strategy(strategy_id: str, *, improved: bool) -> dict[str, object]:
    return {
        "id": strategy_id,
        "label": strategy_id.title(),
        "rationale": "Synthetic strategy fixture.",
        "evidence_record_ids": ["model-source", "cost-source"],
        "state_rules": make_rules(strategy_id, improved=improved),
        "transition_costs": [
            {
                "id": f"{strategy_id}-event-entry",
                "from_state": "stable",
                "to_state": "event",
                "cost": 2200.0,
                "rationale": "Synthetic event-entry cost.",
                "evidence_record_ids": ["cost-source"],
            }
        ],
    }


def build_workspace(root: Path, *, identical: bool = False) -> dict[str, object]:
    evidence = {
        "schema_version": "0.1.0",
        "records": [
            {"id": "model-source", "title": "Synthetic model evidence"},
            {"id": "cost-source", "title": "Synthetic economic evidence"},
        ],
    }
    write_json(root / "heor/evidence-synthesis.json", evidence)
    evidence_raw = (root / "heor/evidence-synthesis.json").read_bytes()
    request: dict[str, object] = {
        "schema_version": "0.1.0",
        "simulation_id": "microsim-test-001",
        "status": "ready_for_execution",
        "question": {
            "population": "Synthetic closed cohort.",
            "purpose": "Compare two synthetic strategies.",
            "time_origin": "Synthetic index date.",
            "perspective": "Synthetic payer perspective.",
            "intended_use": "Engine verification only.",
            "individual_model_justification": "Time in event and prior event count affect transitions and rewards.",
        },
        "evidence_synthesis": {
            "path": "heor/evidence-synthesis.json",
            "sha256": digest(evidence_raw),
            "included_record_ids": ["model-source", "cost-source"],
        },
        "model": {
            "type": "discrete_time_individual_state_transition",
            "states": [
                {"id": "stable", "label": "Stable", "absorbing": False, "death": False},
                {"id": "event", "label": "Event", "absorbing": False, "death": False},
                {"id": "dead", "label": "Dead", "absorbing": True, "death": True},
            ],
            "initial_distribution": [1.0, 0.0, 0.0],
            "cycle_length_years": 1.0,
            "cycles": 8,
            "transition_timing": "one_transition_at_cycle_end",
            "reward_timing": "trapezoidal_state_rewards_transition_costs_at_cycle_end",
            "interactions": "none_closed_independent_cohort",
            "event_trackers": [
                {
                    "id": "event-count",
                    "label": "Event entries",
                    "from_states": ["stable"],
                    "to_state": "event",
                    "maximum_count": 3,
                    "rationale": "Synthetic recurrence tracker.",
                    "evidence_record_ids": ["model-source"],
                }
            ],
        },
        "strategies": [
            make_strategy("comparator", improved=False),
            make_strategy("intervention", improved=False if identical else True),
        ],
        "economics": {
            "currency": "CNY",
            "price_year": 2026,
            "discount_rate_costs": 0.05,
            "discount_rate_outcomes": 0.05,
            "willingness_to_pay": 100000.0,
        },
        "simulation": {
            "patients_per_replicate": 100,
            "replicates": 3,
            "base_seed": 20260717,
            "random_number_generator": "splitmix64_counter_top53_v1",
            "common_random_numbers": "synchronized_initial_and_cycle_transition_uniforms",
            "trace_replicate": 0,
            "trace_patient_indices": list(range(10)),
            "maximum_simulation_steps": 5000000,
        },
        "output": {"directory": "heor/semi-markov-microsimulation-runs/microsim-test-001"},
        "human_authorization": {
            "actor": "test-researcher",
            "authorized_at": "2026-07-17T00:00:00Z",
            "scope": "execute_local_semi_markov_microsimulation",
        },
        "limitations": [
            "Synthetic fixture only.",
            "Parameter and structural uncertainty are not modeled.",
        ],
        "human_gate": {"status": "awaiting_method_review", "required_checks": REQUIRED_REVIEW_CHECKS},
    }
    write_json(root / "heor/semi-markov-microsimulation-request.json", request)
    return request


class SemiMarkovMicrosimulationTests(unittest.TestCase):
    def test_counter_prng_has_stable_reference_vectors(self) -> None:
        self.assertEqual(counter_uniform(0, 0, 0, 0, 0), 0.14496552426123632)
        self.assertEqual(counter_uniform(20260717, 0, 0, 1, 1), 0.51127505946552265)
        self.assertEqual(counter_uniform(20260717, 2, 99, 8, 1), 0.28400037087347296)

    def test_valid_model_executes_time_in_state_and_history_rules(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root)
            errors, facts = validate_request(request, root)
            self.assertEqual(errors, [])
            result = execute_simulation(request, facts)
            self.assertEqual(result["performance"]["simulation_steps"], 4800)
            self.assertGreater(result["strategies"][0]["tracker_summary"]["event-count"]["proportion_with_any"], 0)
            rule_ids = {row["rule_id"] for row in result["_trace_rows"]}
            self.assertTrue(any("event-early" in rule_id for rule_id in rule_ids))
            self.assertEqual(len(result["strategies"][0]["state_occupancy"]), 9)

    def test_execution_is_byte_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root)
            errors, facts = validate_request(request, root)
            self.assertEqual(errors, [])
            first = execute_simulation(request, facts)
            second = execute_simulation(request, facts)
            self.assertEqual(canonical_json_bytes(first), canonical_json_bytes(second))

    def test_common_random_numbers_cancel_identical_strategies(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root, identical=True)
            errors, facts = validate_request(request, root)
            self.assertEqual(errors, [])
            result = execute_simulation(request, facts)
            comparison = result["comparisons"][0]
            self.assertEqual(comparison["incremental_cost"], 0.0)
            self.assertEqual(comparison["incremental_qaly"], 0.0)
            self.assertEqual(comparison["standard_error_incremental_net_monetary_benefit"], 0.0)

    def test_runner_and_portable_audit_replay_every_step(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_workspace(root)
            run = subprocess.run([
                sys.executable,
                "-B",
                str(SCRIPTS / "run_microsimulation.py"),
                "--workspace", str(root),
                "--request", "heor/semi-markov-microsimulation-request.json",
            ], capture_output=True, text=True, check=False)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            result_path = root / "heor/semi-markov-microsimulation-runs/microsim-test-001/manifest.json"
            audit = audit_result(result_path, root)
            self.assertTrue(audit["complete"], audit["errors"])
            self.assertEqual(audit["simulation_steps"], 4800)
            self.assertEqual(audit["trace_rows"], 160)

    def test_overlapping_rules_and_unknown_authority_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root)
            duplicate = copy.deepcopy(request["strategies"][0]["state_rules"][0]["rules"][0])
            duplicate["id"] = "overlapping-history-rule"
            request["strategies"][0]["state_rules"][0]["rules"].insert(1, duplicate)
            request["agent_selected_strategy"] = "intervention"
            errors, _ = validate_request(request, root)
            self.assertTrue(any("overlap" in error for error in errors))
            self.assertTrue(any("unknown authority" in error for error in errors))

    def test_missing_evidence_and_excessive_steps_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request = build_workspace(root)
            request["strategies"][0]["state_rules"][0]["rules"][0]["evidence_record_ids"] = ["not-bound"]
            request["simulation"]["patients_per_replicate"] = 50000
            request["simulation"]["replicates"] = 20
            errors, _ = validate_request(request, root)
            self.assertTrue(any("not all present" in error for error in errors))
            self.assertTrue(any("exceeding the cap" in error for error in errors))

    def test_trace_and_manifest_tampering_are_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            build_workspace(root)
            run = subprocess.run([
                sys.executable,
                "-B",
                str(SCRIPTS / "run_microsimulation.py"),
                "--workspace", str(root),
                "--request", "heor/semi-markov-microsimulation-request.json",
            ], capture_output=True, text=True, check=False)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            output = root / "heor/semi-markov-microsimulation-runs/microsim-test-001"
            trace = output / "traces.jsonl"
            trace.write_bytes(trace.read_bytes() + b"{}\n")
            audit = audit_result(output / "manifest.json", root)
            self.assertFalse(audit["complete"])
            self.assertTrue(any("trace sha256" in error for error in audit["errors"]))


if __name__ == "__main__":
    unittest.main()
