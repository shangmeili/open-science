from __future__ import annotations

import copy
import hashlib
import json
from math import log
from pathlib import Path
import unittest

from heor_core.model import MarkovSpecification, ModelValidationError, run_markov
from heor_core.relative_effect import (
    RelativeEffectError,
    derive_relative_effect_schedule,
)
from heor_core.uncertainty import (
    UncertaintySpecification,
    _apply_parameter_values,
    run_uncertainty,
)


ROOT = Path(__file__).parents[1]
UNCERTAINTY_PATH = ROOT / "golden_cases" / "two_strategy_uncertainty.json"


def transformation(measure: str = "risk_ratio") -> dict:
    return {
        "operation": "relative_effect_to_transition_schedule",
        "cycle_length_years": 1.0,
        "effect_interval_years": 1.0,
        "from_state_index": 0,
        "event_state_index": 1,
        "measure": measure,
        "baseline_cycle_probabilities": [
            {
                "cycle": 1,
                "probability": {
                    "value": 0.20,
                    "source_extraction_id": "baseline-1",
                    "source_pointer": "/risk",
                },
            },
            {
                "cycle": 2,
                "probability": {
                    "value": 0.0,
                    "source_extraction_id": "baseline-2",
                    "source_pointer": "/risk",
                },
            },
            {
                "cycle": 3,
                "probability": {
                    "value": 0.40,
                    "source_extraction_id": "baseline-3",
                    "source_pointer": "/risk",
                },
            },
        ],
        "relative_effect": {
            "value": 0.50,
            "source_extraction_id": "effect",
            "source_pointer": "/relative_effect",
        },
        "review_bases": {
            "endpoint_alignment": {"assumption_id": "endpoint-alignment"},
            "population_transportability": {
                "assumption_id": "population-transportability"
            },
            "effect_constancy_over_cycles": {
                "assumption_id": "effect-constancy"
            },
        },
    }


def analysis_payload(measure: str = "risk_ratio") -> dict:
    declaration = transformation(measure)
    schedule, extraction_ids, assumption_ids = derive_relative_effect_schedule(
        declaration,
        state_count=2,
        cycles=3,
        cycle_length_years=1.0,
    )
    return {
        "schema_version": "0.10.0",
        "analysis_id": f"relative-effect-{measure}",
        "economic_basis": {"currency": "CNY", "price_year": 2026},
        "decision_problem": {
            "title": "Synthetic relative-effect analysis",
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


def uncertainty_payload(base: dict, base_raw: bytes, measure: str) -> dict:
    value = json.loads(UNCERTAINTY_PATH.read_text())
    value.update(
        {
            "schema_version": "0.9.0",
            "uncertainty_id": f"relative-effect-{measure}-uncertainty",
            "analysis_id": base["analysis_id"],
        }
    )
    value["base_analysis"]["content_sha256"] = hashlib.sha256(base_raw).hexdigest()
    probabilistic = (
        {
            "type": "uniform",
            "low": 0.30,
            "high": 0.80,
            "basis_ids": ["effect"],
            "rationale": "Bounded risk-ratio range.",
        }
        if measure == "risk_ratio"
        else {
            "type": "lognormal",
            "mu_log": log(0.50),
            "sigma_log": 0.10,
            "basis_ids": ["effect"],
            "rationale": "Positive odds-ratio distribution.",
        }
    )
    value["parameters"] = [
        {
            "id": "relative-effect",
            "label": "Relative effect",
            "target": "/input_provenance/0/derivation/transformation/relative_effect/value",
            "provenance_path": "strategies.treatment.transition_schedule",
            "deterministic": {
                "low": 0.30,
                "high": 0.80,
                "rationale": "Strictly positive reviewed range.",
            },
            "probabilistic": probabilistic,
        }
    ]
    value["probabilistic_analysis"]["correlation_handling"] = {
        "independence_rationale": "Only one relative-effect parameter varies.",
        "known_omitted_correlations": [],
        "groups": [],
    }
    value["probabilistic_analysis"]["omitted_parameters"] = [
        {
            "provenance_path": "strategies.treatment.transition_schedule",
            "rationale": "Baseline probabilities remain fixed in schema 0.9.0.",
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


class RelativeEffectAnalysisTests(unittest.TestCase):
    def test_risk_ratio_and_odds_ratio_match_hand_calculation(self) -> None:
        rr, extractions, assumptions = derive_relative_effect_schedule(
            transformation("risk_ratio"),
            state_count=2,
            cycles=3,
            cycle_length_years=1.0,
        )
        self.assertEqual([row["matrix"][0][1] for row in rr], [0.10, 0.0, 0.20])
        self.assertEqual(rr[0]["matrix"][1], [0.0, 1.0])
        self.assertEqual(extractions, {"baseline-1", "baseline-2", "baseline-3", "effect"})
        self.assertEqual(
            assumptions,
            {"endpoint-alignment", "population-transportability", "effect-constancy"},
        )

        odds, _, _ = derive_relative_effect_schedule(
            transformation("odds_ratio"),
            state_count=2,
            cycles=3,
            cycle_length_years=1.0,
        )
        self.assertAlmostEqual(odds[0]["matrix"][0][1], 0.10 / 0.90)
        self.assertAlmostEqual(odds[2]["matrix"][0][1], 0.20 / 0.80)

    def test_analysis_010_runs_with_engine_010(self) -> None:
        result = run_markov(MarkovSpecification.from_dict(analysis_payload())).to_dict()
        self.assertEqual(result["schema_version"], "0.10.0")
        self.assertEqual(result["engine_version"], "0.10.0")

    def test_invalid_measure_interval_basis_output_and_numeric_boundaries_fail(self) -> None:
        cases: list[tuple[dict, str]] = []
        invalid_measure = transformation()
        invalid_measure["measure"] = "hazard_ratio"
        cases.append((invalid_measure, "risk_ratio or odds_ratio"))
        interval = transformation()
        interval["effect_interval_years"] = 2.0
        cases.append((interval, "must equal the model cycle length"))
        all_zero = transformation()
        for entry in all_zero["baseline_cycle_probabilities"]:
            entry["probability"]["value"] = 0.0
        cases.append((all_zero, "at least one probability greater than zero"))
        endpoint = transformation()
        endpoint["baseline_cycle_probabilities"][0]["probability"]["value"] = 1.0
        cases.append((endpoint, "less than 1.0"))
        zero_effect = transformation()
        zero_effect["relative_effect"]["value"] = 0.0
        cases.append((zero_effect, "greater than 0.0"))
        saturated = transformation()
        saturated["relative_effect"]["value"] = 2.5
        cases.append((saturated, "invalid probability"))
        duplicate_basis = transformation()
        duplicate_basis["relative_effect"]["assumption_id"] = "duplicate"
        cases.append((duplicate_basis, "exactly one"))
        missing_review = transformation()
        del missing_review["review_bases"]["endpoint_alignment"]
        cases.append((missing_review, "review_bases fields are invalid"))
        for declaration, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                RelativeEffectError, message
            ):
                derive_relative_effect_schedule(
                    declaration,
                    state_count=2,
                    cycles=3,
                    cycle_length_years=1.0,
                )

        stale = analysis_payload()
        stale["strategies"]["treatment"]["transition_schedule"][0]["matrix"][0] = [0.5, 0.5]
        with self.assertRaisesRegex(ModelValidationError, "does not match|does not reproduce"):
            MarkovSpecification.from_dict(stale)


class RelativeEffectUncertaintyTests(unittest.TestCase):
    def test_rr_uncertainty_recomputes_complete_schedule(self) -> None:
        base = analysis_payload("risk_ratio")
        base_raw = json.dumps(base, sort_keys=True).encode()
        plan = uncertainty_payload(base, base_raw, "risk_ratio")
        specification = UncertaintySpecification.from_dict(
            plan, base, hashlib.sha256(base_raw).hexdigest()
        )
        changed = _apply_parameter_values(
            base, ((specification.parameters[0], 0.80),)
        )
        self.assertAlmostEqual(
            changed["strategies"]["treatment"]["transition_schedule"][2]["matrix"][0][1],
            0.32,
        )
        self.assertEqual(
            changed["input_provenance"][0]["derivation"]["model_value"],
            changed["strategies"]["treatment"]["transition_schedule"],
        )
        result = run_uncertainty(
            base, base_raw, plan, json.dumps(plan, sort_keys=True).encode()
        )
        self.assertEqual(result["schema_version"], "0.9.0")
        self.assertEqual(result["engine_version"], "0.10.0")

    def test_rr_invalid_distribution_and_joint_upper_bounds_fail_preflight(self) -> None:
        base = analysis_payload("risk_ratio")
        base_raw = json.dumps(base, sort_keys=True).encode()
        cases: list[tuple[dict, str]] = []
        unbounded = uncertainty_payload(base, base_raw, "risk_ratio")
        unbounded["parameters"][0]["probabilistic"] = {
            "type": "lognormal",
            "mu_log": log(0.5),
            "sigma_log": 0.1,
            "basis_ids": ["effect"],
            "rationale": "Invalid unbounded RR.",
        }
        cases.append((unbounded, "bounded uniform"))
        dsa_boundary = uncertainty_payload(base, base_raw, "risk_ratio")
        dsa_boundary["parameters"][0]["deterministic"]["high"] = 2.5
        cases.append((dsa_boundary, "deterministic high must be strictly below"))
        psa_boundary = uncertainty_payload(base, base_raw, "risk_ratio")
        psa_boundary["parameters"][0]["probabilistic"]["high"] = 2.5
        cases.append((psa_boundary, "uniform high must be strictly below"))
        for plan, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                ModelValidationError, message
            ):
                UncertaintySpecification.from_dict(
                    plan, base, hashlib.sha256(base_raw).hexdigest()
                )

    def test_or_allows_lognormal_but_only_relative_effect_target(self) -> None:
        base = analysis_payload("odds_ratio")
        base_raw = json.dumps(base, sort_keys=True).encode()
        plan = uncertainty_payload(base, base_raw, "odds_ratio")
        UncertaintySpecification.from_dict(
            plan, base, hashlib.sha256(base_raw).hexdigest()
        )

        plan["parameters"][0]["target"] = (
            "/input_provenance/0/derivation/transformation/"
            "baseline_cycle_probabilities/0/probability/value"
        )
        with self.assertRaisesRegex(ModelValidationError, "only the exact relative_effect.value"):
            UncertaintySpecification.from_dict(
                plan, base, hashlib.sha256(base_raw).hexdigest()
            )


if __name__ == "__main__":
    unittest.main()
