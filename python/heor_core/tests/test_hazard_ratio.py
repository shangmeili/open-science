from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import unittest

from heor_core.hazard_ratio import HazardRatioError, derive_hazard_ratio_schedule
from heor_core.model import MarkovSpecification, run_markov
from heor_core.uncertainty import UncertaintySpecification, run_uncertainty


ROOT = Path(__file__).parents[1]
UNCERTAINTY_PATH = ROOT / "golden_cases" / "two_strategy_uncertainty.json"


def transformation() -> dict:
    return {
        "operation": "hazard_ratio_to_transition_schedule",
        "cycle_length_years": 1.0,
        "from_state_index": 0,
        "event_state_index": 1,
        "baseline_cumulative_hazards": [
            {"cycle": 1, "cumulative_hazard": {"value": 0.1, "source_extraction_id": "h1"}},
            {"cycle": 2, "cumulative_hazard": {"value": 0.3, "source_extraction_id": "h2"}},
            {"cycle": 3, "cumulative_hazard": {"value": 0.3, "source_extraction_id": "h3"}},
        ],
        "hazard_ratio": {"value": 0.5, "source_extraction_id": "hr"},
        "review_bases": {
            "endpoint_alignment": {"assumption_id": "endpoint"},
            "population_transportability": {"assumption_id": "population"},
            "proportional_hazards_assumption": {"assumption_id": "ph"},
            "effect_constancy_over_horizon": {"assumption_id": "constancy"},
            "treatment_switching_assessment": {"assumption_id": "switching"},
        },
    }


def analysis_payload() -> dict:
    declaration = transformation()
    schedule, extraction_ids, assumption_ids = derive_hazard_ratio_schedule(
        declaration, state_count=2, cycles=3, cycle_length_years=1.0
    )
    return {
        "schema_version": "0.11.0",
        "analysis_id": "hazard-ratio-analysis",
        "economic_basis": {"currency": "CNY", "price_year": 2026},
        "decision_problem": {
            "title": "Synthetic HR analysis",
            "population": "Synthetic cohort",
            "intervention": "Treatment",
            "comparator": "Standard care",
            "perspective": "Healthcare system",
            "time_horizon_years": 3.0,
            "outcome": "QALY",
            "jurisdiction": "China",
        },
        "reference_case": {"id": "synthetic", "status": "custom"},
        "states": ["event_free", "event"],
        "cycles": 3,
        "cycle_length_years": 1.0,
        "discount_rates": {"costs": 0.0, "outcomes": 0.0},
        "half_cycle_correction": False,
        "willingness_to_pay": 100000.0,
        "baseline_strategy_id": "standard_care",
        "strategy_order": ["standard_care", "treatment"],
        "strategies": {
            "standard_care": {
                "name": "Standard care",
                "initial_distribution": [1.0, 0.0],
                "transition_matrix": [[1.0, 0.0], [0.0, 1.0]],
                "state_costs": [100.0, 0.0],
                "state_utilities": [1.0, 0.0],
            },
            "treatment": {
                "name": "Treatment",
                "initial_distribution": [1.0, 0.0],
                "transition_schedule": schedule,
                "state_costs": [90.0, 0.0],
                "state_utilities": [1.0, 0.0],
            },
        },
        "assumptions": [
            {"id": item, "status": "proposed", "statement": item, "reason": item}
            for item in sorted(assumption_ids)
        ],
        "input_provenance": [
            {
                "path": "strategies.treatment.transition_schedule",
                "source_ids": [],
                "extraction_ids": sorted(extraction_ids),
                "assumption_ids": sorted(assumption_ids),
                "derivation": {
                    "method": "deterministic_transformation",
                    "model_value": copy.deepcopy(schedule),
                    "transformation": declaration,
                },
            }
        ],
    }


def uncertainty_payload(base: dict, base_raw: bytes) -> dict:
    value = json.loads(UNCERTAINTY_PATH.read_text())
    value.update(
        {
            "schema_version": "0.10.0",
            "uncertainty_id": "hazard-ratio-uncertainty",
            "analysis_id": base["analysis_id"],
        }
    )
    value["base_analysis"]["content_sha256"] = hashlib.sha256(base_raw).hexdigest()
    value["parameters"] = [
        {
            "id": "hazard-ratio",
            "label": "Hazard ratio",
            "target": "/input_provenance/0/derivation/transformation/hazard_ratio/value",
            "provenance_path": "strategies.treatment.transition_schedule",
            "deterministic": {
                "low": 0.3,
                "high": 0.8,
                "rationale": "Reviewed positive HR interval.",
            },
            "probabilistic": {
                "type": "uniform",
                "low": 0.3,
                "high": 0.8,
                "basis_ids": ["hr"],
                "rationale": "Bounded HR distribution.",
            },
        }
    ]
    value["probabilistic_analysis"]["correlation_handling"] = {
        "independence_rationale": "Only one hazard-ratio parameter varies.",
        "known_omitted_correlations": [],
        "groups": [],
    }
    value["probabilistic_analysis"]["omitted_parameters"] = [
        {
            "provenance_path": "strategies.treatment.transition_schedule",
            "rationale": "Baseline cumulative hazards remain fixed in schema 0.10.0.",
        }
    ]
    value["structural_scenarios"] = [
        {
            "id": "alternative-discount",
            "label": "Alternative discount rate",
            "rationale": "Keeps structural uncertainty separate.",
            "replacements": [{"target": "/discount_rates/costs", "value": 0.02}],
        }
    ]
    return value


class HazardRatioAnalysisTests(unittest.TestCase):
    def test_formula_uses_cumulative_hazard_increments(self) -> None:
        schedule, extractions, assumptions = derive_hazard_ratio_schedule(
            transformation(), state_count=2, cycles=3, cycle_length_years=1.0
        )
        probabilities = [row["matrix"][0][1] for row in schedule]
        self.assertAlmostEqual(probabilities[0], 1.0 - __import__("math").exp(-0.05))
        self.assertAlmostEqual(probabilities[1], 1.0 - __import__("math").exp(-0.10))
        self.assertEqual(probabilities[2], 0.0)
        self.assertEqual(extractions, {"h1", "h2", "h3", "hr"})
        self.assertEqual(assumptions, {"endpoint", "population", "ph", "constancy", "switching"})

    def test_analysis_011_runs_with_engine_011(self) -> None:
        result = run_markov(MarkovSpecification.from_dict(analysis_payload())).to_dict()
        self.assertEqual(result["schema_version"], "0.11.0")
        self.assertEqual(result["engine_version"], "0.11.0")

    def test_non_monotone_all_zero_wrong_schema_and_saturation_fail_closed(self) -> None:
        non_monotone = transformation()
        non_monotone["baseline_cumulative_hazards"][1]["cumulative_hazard"]["value"] = 0.05
        all_zero = transformation()
        for item in all_zero["baseline_cumulative_hazards"]:
            item["cumulative_hazard"]["value"] = 0.0
        saturated = transformation()
        saturated["hazard_ratio"]["value"] = 1e308
        for value, message in (
            (non_monotone, "non-decreasing"),
            (all_zero, "positive increment"),
            (saturated, "invalid probability"),
        ):
            with self.subTest(message=message), self.assertRaisesRegex(HazardRatioError, message):
                derive_hazard_ratio_schedule(value, state_count=2, cycles=3, cycle_length_years=1.0)
        wrong_schema = analysis_payload()
        wrong_schema["schema_version"] = "0.10.0"
        with self.assertRaisesRegex(ValueError, "require schema_version 0.11.0"):
            MarkovSpecification.from_dict(wrong_schema)

    def test_exact_review_contract_and_output_tampering_fail(self) -> None:
        invalid = transformation()
        del invalid["review_bases"]["treatment_switching_assessment"]
        with self.assertRaisesRegex(HazardRatioError, "missing treatment_switching_assessment"):
            derive_hazard_ratio_schedule(invalid, state_count=2, cycles=3, cycle_length_years=1.0)
        payload = analysis_payload()
        payload["strategies"]["treatment"]["transition_schedule"][0]["matrix"][0][1] += 0.01
        payload["strategies"]["treatment"]["transition_schedule"][0]["matrix"][0][0] -= 0.01
        with self.assertRaisesRegex(ValueError, "model_value does not match"):
            MarkovSpecification.from_dict(payload)

    def test_uncertainty_010_recomputes_the_complete_schedule(self) -> None:
        base = analysis_payload()
        base_raw = json.dumps(base, sort_keys=True).encode()
        uncertainty = uncertainty_payload(base, base_raw)
        uncertainty_raw = json.dumps(uncertainty, sort_keys=True).encode()
        result = run_uncertainty(base, base_raw, uncertainty, uncertainty_raw)
        self.assertEqual(result["schema_version"], "0.10.0")
        self.assertEqual(result["engine_version"], "0.11.0")
        self.assertEqual(result["probabilistic_analysis"]["iterations"], 1000)

    def test_uncertainty_rejects_unbounded_wrong_target_basis_and_saturated_high(self) -> None:
        base = analysis_payload()
        base_raw = json.dumps(base, sort_keys=True).encode()
        cases: list[tuple[dict, str]] = []
        lognormal = uncertainty_payload(base, base_raw)
        lognormal["parameters"][0]["probabilistic"] = {
            "type": "lognormal",
            "mu_log": -0.7,
            "sigma_log": 0.1,
            "basis_ids": ["hr"],
            "rationale": "Unbounded.",
        }
        cases.append((lognormal, "bounded uniform"))
        wrong_target = uncertainty_payload(base, base_raw)
        wrong_target["parameters"][0]["target"] = "/willingness_to_pay"
        cases.append((wrong_target, "only the exact hazard_ratio.value"))
        wrong_basis = uncertainty_payload(base, base_raw)
        wrong_basis["parameters"][0]["probabilistic"]["basis_ids"] = ["h1"]
        cases.append((wrong_basis, "exactly the hazard-ratio"))
        saturated = uncertainty_payload(base, base_raw)
        saturated["parameters"][0]["deterministic"]["high"] = 1e308
        saturated["parameters"][0]["probabilistic"]["high"] = 1e308
        cases.append((saturated, "valid complete transition schedule"))
        for payload, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                UncertaintySpecification.from_dict(payload, base, hashlib.sha256(base_raw).hexdigest())


if __name__ == "__main__":
    unittest.main()
