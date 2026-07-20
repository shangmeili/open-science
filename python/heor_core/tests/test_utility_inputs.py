from __future__ import annotations

from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import unittest

from heor_core.model import ModelValidationError
from heor_core.utility_inputs import validate_utility_inputs


ROOT = Path(__file__).resolve().parents[3]
VALIDATOR_PATH = ROOT / "runtime/skills/core/heor-utility-inputs/scripts/validate_utility_inputs.py"
SPEC = importlib.util.spec_from_file_location("portable_utility_inputs", VALIDATOR_PATH)
assert SPEC and SPEC.loader
PORTABLE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PORTABLE)


def plan() -> dict:
    return {
        "schema_version": "0.14.0",
        "analysis_id": "utility-test",
        "decision_problem": {
            "jurisdiction": "England",
            "population": "Adults with advanced disease",
        },
        "states": ["progression_free", "progressed", "dead"],
        "cycles": 2,
        "strategy_order": ["comparator", "intervention"],
        "strategies": {
            "comparator": {"state_utilities": [0.8, 0.6, 0.0]},
            "intervention": {"state_utilities": [0.82, 0.62, 0.0]},
        },
        "evidence_sources": [
            {"id": "utility-source"},
            {"id": "value-set-source"},
            {"id": "mapping-source"},
            {"id": "population-norm-source"},
        ],
        "assumptions": [
            {"id": "overlap-assessment", "status": "proposed"},
            {"id": "dead-anchor", "status": "proposed"},
        ],
        "input_provenance": [],
    }


def artifact(analysis: dict) -> tuple[dict, bytes]:
    raw = json.dumps(analysis, separators=(",", ":")).encode()
    source_values = {
        "comparator": [0.8, 0.6, 0.0],
        "intervention": [0.82, 0.62, 0.0],
    }
    value = {
        "schema_version": "0.1.0",
        "utility_input_id": "utility-inputs",
        "analysis_id": analysis["analysis_id"],
        "status": "ready_for_human_review",
        "base_analysis": {
            "path": "heor/analysis-plan.json",
            "content_sha256": hashlib.sha256(raw).hexdigest(),
        },
        "target_context": {
            "jurisdiction": "England",
            "population": "Adults with advanced disease",
            "outcome": "QALY",
        },
        "cycle_value_timing": "cycle_average",
        "item_order": [],
        "items": {},
        "cycle_state_utilities": {
            "comparator": [[0.8, 0.6, 0.0], [0.72, 0.6, 0.0]],
            "intervention": [[0.82, 0.62, 0.0], [0.82, 0.62, 0.0]],
        },
        "limitations": [
            "Event disutilities and component-level probabilistic uncertainty are outside this contract."
        ],
    }
    for strategy_id in analysis["strategy_order"]:
        for state_index, state_id in enumerate(analysis["states"]):
            item_id = f"{strategy_id}-{state_id.replace('_', '-')}"
            source = source_values[strategy_id][state_index]
            dead = state_id == "dead"
            mapped = strategy_id == "intervention" and state_id == "progression_free"
            adjusted = strategy_id == "comparator" and state_id == "progression_free"
            factors = [1.0, 0.9] if adjusted else [1.0, 1.0]
            origin = "anchor" if dead else "mapped" if mapped else "value_set"
            value["item_order"].append(item_id)
            value["items"][item_id] = {
                "item_id": item_id,
                "strategy_id": strategy_id,
                "state_id": state_id,
                "description": "Dead anchor" if dead else "Cycle-average health-state utility.",
                "application": {
                    "type": "health_state_utility",
                    "timing": "cycle_average_while_in_state",
                    "captured_effects": ["health_state"],
                    "excluded_effects": ["acute_adverse_events"],
                    "overlap_assessment": {
                        "rationale": "Acute event disutilities are not separately applied.",
                        "basis_ids": ["dead-anchor" if dead else "overlap-assessment"],
                    },
                },
                "measurement": {
                    "source_design": "anchor" if dead else "randomized_trial",
                    "instrument_name": "QALY anchor" if dead else "EQ-5D",
                    "instrument_version": "not_applicable" if dead else "5L",
                    "instrument_class": "qaly_anchor" if dead else "generic_preference_based",
                    "respondent": "not_applicable" if dead else "patient",
                    "source_population": "QALY definition" if dead else "Trial population",
                    "sample_size": None if dead else 200,
                    "assessment_timing": "not_applicable" if dead else "Scheduled trial visits",
                    "basis_ids": ["dead-anchor" if dead else "utility-source"],
                },
                "valuation": {
                    "value_origin": origin,
                    "value_set_id": None if dead else "uk-eq5d-3l",
                    "value_set_jurisdiction": None if dead else "United Kingdom",
                    "preference_population": "not_applicable" if dead else "UK general population",
                    "valuation_method": "anchor" if dead else "algorithmic_mapping" if mapped else "time_trade_off",
                    "anchor": "dead_0_full_health_1",
                    "license_status": "not_applicable" if dead else "registered_noncommercial",
                    "basis_ids": ["dead-anchor" if dead else "value-set-source"],
                },
                "mapping": (
                    {
                        "source_measure": "EQ-5D-5L",
                        "target_measure": "EQ-5D-3L index",
                        "algorithm_id": "reviewed-crosswalk",
                        "estimation_population": "Paired descriptive-system sample",
                        "validation_status": "external",
                        "performance_basis_ids": ["mapping-source"],
                        "license_status": "link_only",
                    }
                    if mapped
                    else None
                ),
                "source_utility": {
                    "value": source,
                    "basis_ids": ["dead-anchor" if dead else "utility-source"],
                },
                "adjustments": (
                    [
                        {
                            "kind": "age_adjustment",
                            "operation": "multiply",
                            "method": "Reviewed multiplicative population-norm ratio",
                            "factors": factors,
                            "basis_ids": ["population-norm-source"],
                        }
                    ]
                    if adjusted
                    else []
                ),
                "cycle_values": [source * factor for factor in factors],
                "uncertainty": {
                    "status": "fixed",
                    "basis_ids": ["dead-anchor" if dead else "utility-source"],
                    "limitations": ["Component uncertainty is not executed by this alpha."],
                },
            }
    return value, raw


class UtilityInputTests(unittest.TestCase):
    def test_reproduces_cycle_state_utility_schedule(self) -> None:
        analysis = plan()
        value, raw = artifact(analysis)
        summary = validate_utility_inputs(analysis, raw, value, json.dumps(value).encode())
        self.assertEqual(summary.item_count, 6)
        self.assertEqual(summary.mapped_item_count, 1)
        self.assertEqual(summary.adjusted_item_count, 1)
        self.assertEqual(summary.cycle_state_utilities["comparator"][1][0], 0.72)

    def test_rejects_arithmetic_drift_and_unknown_authority_field(self) -> None:
        for mutation in ("arithmetic", "authority"):
            with self.subTest(mutation=mutation):
                analysis = plan()
                value, raw = artifact(analysis)
                item = value["items"]["comparator-progression-free"]
                if mutation == "arithmetic":
                    item["cycle_values"][1] = 0.73
                else:
                    item["approved"] = True
                with self.assertRaises(ModelValidationError):
                    validate_utility_inputs(analysis, raw, value, json.dumps(value).encode())

    def test_requires_complete_mapping_metadata_and_license_status(self) -> None:
        for mutation in ("mapping", "license"):
            with self.subTest(mutation=mutation):
                analysis = plan()
                value, raw = artifact(analysis)
                item = value["items"]["intervention-progression-free"]
                if mutation == "mapping":
                    item["mapping"] = None
                else:
                    item["valuation"]["license_status"] = "unknown"
                with self.assertRaises(ModelValidationError):
                    validate_utility_inputs(analysis, raw, value, json.dumps(value).encode())

    def test_dead_state_is_only_the_unadjusted_zero_anchor(self) -> None:
        analysis = plan()
        value, raw = artifact(analysis)
        value["items"]["comparator-dead"]["cycle_values"][1] = -0.1
        with self.assertRaisesRegex(ModelValidationError, "does not reproduce|dead-state"):
            validate_utility_inputs(analysis, raw, value, json.dumps(value).encode())

    def test_first_cycle_must_match_analysis_state_utilities(self) -> None:
        analysis = plan()
        value, raw = artifact(analysis)
        analysis["strategies"]["comparator"]["state_utilities"][0] = 0.79
        raw = json.dumps(analysis, separators=(",", ":")).encode()
        value["base_analysis"]["content_sha256"] = hashlib.sha256(raw).hexdigest()
        with self.assertRaisesRegex(ModelValidationError, "state_utilities"):
            validate_utility_inputs(analysis, raw, value, json.dumps(value).encode())

    def test_portable_validator_matches_core_boundary(self) -> None:
        analysis = plan()
        value, raw = artifact(analysis)
        self.assertEqual(PORTABLE.validate(analysis, raw, value), [])
        value["items"]["comparator-progression-free"]["cycle_values"][1] = 0.73
        self.assertTrue(PORTABLE.validate(analysis, raw, value))

    def test_rejects_legacy_schema_and_dead_metadata_drift_portably(self) -> None:
        for mutation in ("legacy_schema", "dead_metadata"):
            with self.subTest(mutation=mutation):
                analysis = plan()
                value, raw = artifact(analysis)
                if mutation == "legacy_schema":
                    analysis["schema_version"] = "0.13.0"
                    raw = json.dumps(analysis, separators=(",", ":")).encode()
                    value["base_analysis"]["content_sha256"] = hashlib.sha256(raw).hexdigest()
                else:
                    value["items"]["comparator-dead"]["measurement"]["respondent"] = "patient"
                with self.assertRaises(ModelValidationError):
                    validate_utility_inputs(analysis, raw, value, json.dumps(value).encode())
                self.assertTrue(PORTABLE.validate(analysis, raw, value))


if __name__ == "__main__":
    unittest.main()
