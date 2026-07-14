from __future__ import annotations

import copy
import hashlib
import json
from math import exp, log1p
from pathlib import Path
import unittest

from heor_core.background_mortality import (
    BackgroundMortalityError,
    derive_background_mortality_schedule,
)
from heor_core.budget_impact import run_budget_impact
from heor_core.model import MarkovSpecification, ModelValidationError, run_markov
from heor_core.uncertainty import (
    UncertaintySpecification,
    _apply_parameter_values,
    run_uncertainty,
)


ROOT = Path(__file__).parents[1]
UNCERTAINTY_PATH = ROOT / "golden_cases" / "two_strategy_uncertainty.json"
BUDGET_IMPACT_PATH = ROOT / "golden_cases" / "two_strategy_budget_impact.json"


def transformation() -> dict:
    return {
        "operation": "background_plus_excess_mortality_to_transition_schedule",
        "cycle_length_years": 0.5,
        "from_state_index": 0,
        "death_state_index": 1,
        "life_table": {
            "jurisdiction": "Synthetic jurisdiction",
            "table_year": 2025,
            "population": "General population",
            "sex": "all",
            "start_age_years": 60.0,
            "cycle_probabilities": [
                {
                    "cycle": 1,
                    "attained_age_years": 60,
                    "annual_probability": {
                        "value": 0.10,
                        "source_extraction_id": "life-q-60-a",
                        "source_pointer": "/q",
                    },
                },
                {
                    "cycle": 2,
                    "attained_age_years": 60,
                    "annual_probability": {
                        "value": 0.10,
                        "source_extraction_id": "life-q-60-b",
                        "source_pointer": "/q",
                    },
                },
                {
                    "cycle": 3,
                    "attained_age_years": 61,
                    "annual_probability": {
                        "value": 0.20,
                        "source_extraction_id": "life-q-61",
                        "source_pointer": "/q",
                    },
                },
            ],
        },
        "excess_mortality_rate_per_year": {
            "value": 0.05,
            "assumption_id": "excess-rate",
        },
        "review_bases": {
            "population_exchangeability": {
                "assumption_id": "population-exchangeability",
            },
            "no_double_counting": {
                "assumption_id": "no-double-counting",
            },
        },
    }


def analysis_payload() -> dict:
    declaration = transformation()
    schedule, extraction_ids, assumption_ids = derive_background_mortality_schedule(
        declaration,
        state_count=2,
        cycles=3,
        cycle_length_years=0.5,
    )
    return {
        "schema_version": "0.9.0",
        "analysis_id": "background-mortality-analysis",
        "economic_basis": {"currency": "CNY", "price_year": 2026},
        "decision_problem": {
            "title": "Synthetic mortality analysis",
            "population": "Synthetic cohort",
            "intervention": "Higher excess mortality",
            "comparator": "No mortality",
            "perspective": "Healthcare system",
            "time_horizon_years": 1.5,
            "outcome": "QALY",
            "jurisdiction": "China",
        },
        "reference_case": {"id": "synthetic", "status": "custom"},
        "states": ["alive", "dead"],
        "cycles": 3,
        "cycle_length_years": 0.5,
        "discount_rates": {"costs": 0.0, "outcomes": 0.0},
        "half_cycle_correction": False,
        "willingness_to_pay": 100000.0,
        "baseline_strategy_id": "standard_care",
        "strategy_order": ["standard_care", "higher_risk"],
        "strategies": {
            "standard_care": {
                "name": "Standard care",
                "initial_distribution": [1.0, 0.0],
                "transition_matrix": [[1.0, 0.0], [0.0, 1.0]],
                "state_costs": [100.0, 0.0],
                "state_utilities": [1.0, 0.0],
            },
            "higher_risk": {
                "name": "Higher risk",
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
                "path": "strategies.higher_risk.transition_schedule",
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
            "schema_version": "0.8.0",
            "uncertainty_id": "background-mortality-uncertainty",
            "analysis_id": base["analysis_id"],
        }
    )
    value["base_analysis"]["content_sha256"] = hashlib.sha256(base_raw).hexdigest()
    value["parameters"] = [
        {
            "id": "excess-mortality",
            "label": "Excess mortality rate",
            "target": "/input_provenance/0/derivation/transformation/excess_mortality_rate_per_year/value",
            "provenance_path": "strategies.higher_risk.transition_schedule",
            "deterministic": {
                "low": 0.01,
                "high": 0.10,
                "rationale": "Strictly positive hand-checkable range.",
            },
            "probabilistic": {
                "type": "gamma",
                "shape": 25.0,
                "scale": 0.002,
                "basis_ids": ["excess-rate"],
                "rationale": "Strictly positive distribution centered on 0.05.",
            },
        }
    ]
    value["probabilistic_analysis"]["correlation_handling"] = {
        "independence_rationale": "Only one excess mortality parameter is varied.",
        "known_omitted_correlations": [],
        "groups": [],
    }
    value["probabilistic_analysis"]["omitted_parameters"] = [
        {
            "provenance_path": "strategies.higher_risk.transition_schedule",
            "rationale": "Life-table annual probabilities remain fixed in schema 0.8.0.",
        }
    ]
    value["structural_scenarios"] = [
        {
            "id": "alternative-cost-discount",
            "label": "Alternative cost discount rate",
            "rationale": "Keeps structural uncertainty separate from mortality inputs.",
            "replacements": [{"target": "/discount_rates/costs", "value": 0.02}],
        }
    ]
    return value


class BackgroundMortalityAnalysisTests(unittest.TestCase):
    def test_hand_calculation_and_age_progression(self) -> None:
        declaration = transformation()
        declaration["life_table"]["cycle_probabilities"][1]["attained_age_years"] = 60.0
        schedule, extraction_ids, assumption_ids = derive_background_mortality_schedule(
            declaration,
            state_count=2,
            cycles=3,
            cycle_length_years=0.5,
        )

        self.assertEqual(
            [item["attained_age_years"] for item in declaration["life_table"]["cycle_probabilities"]],
            [60, 60, 61],
        )
        for entry, q in zip(schedule, (0.10, 0.10, 0.20), strict=True):
            expected = 1.0 - exp(-(-log1p(-q) + 0.05) * 0.5)
            self.assertAlmostEqual(entry["matrix"][0][1], expected)
            self.assertEqual(entry["matrix"][1], [0.0, 1.0])
        self.assertEqual(extraction_ids, {"life-q-60-a", "life-q-60-b", "life-q-61"})
        self.assertEqual(
            assumption_ids,
            {"excess-rate", "population-exchangeability", "no-double-counting"},
        )

    def test_analysis_09_runs_with_engine_09_and_keeps_multi_strategy_shape(self) -> None:
        result = run_markov(MarkovSpecification.from_dict(analysis_payload())).to_dict()

        self.assertEqual(result["schema_version"], "0.9.0")
        self.assertEqual(result["engine_version"], "0.9.0")
        self.assertEqual(result["strategy_order"], ["standard_care", "higher_risk"])
        self.assertIn("fully_incremental_analysis", result)

    def test_stale_output_schema_and_semantic_review_bases_fail_closed(self) -> None:
        cases: list[tuple[dict, str]] = []
        stale = analysis_payload()
        stale["strategies"]["higher_risk"]["transition_schedule"][0]["matrix"][0] = [0.5, 0.5]
        cases.append((stale, "does not match the current transition schedule|does not reproduce"))
        old_schema = analysis_payload()
        old_schema["schema_version"] = "0.8.0"
        cases.append((old_schema, "require schema_version 0.9.0"))
        missing_review = analysis_payload()
        del missing_review["input_provenance"][0]["derivation"]["transformation"]["review_bases"]["no_double_counting"]
        cases.append((missing_review, "review_bases fields are invalid"))
        duplicate_basis = analysis_payload()
        duplicate_basis["input_provenance"][0]["derivation"]["transformation"]["review_bases"]["no_double_counting"] = {
            "source_extraction_id": "review-source",
            "assumption_id": "no-double-counting",
        }
        cases.append((duplicate_basis, "exactly one source_extraction_id or assumption_id"))
        incomplete_mapping = analysis_payload()
        incomplete_mapping["input_provenance"][0]["extraction_ids"].remove("life-q-61")
        cases.append((incomplete_mapping, "use every selected extraction exactly as declared"))

        for payload, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                ModelValidationError, message
            ):
                MarkovSpecification.from_dict(payload)

    def test_invalid_age_probability_excess_and_nonfinite_values_fail_closed(self) -> None:
        cases: list[tuple[dict, str]] = []
        wrong_age = transformation()
        wrong_age["life_table"]["cycle_probabilities"][1]["attained_age_years"] = 61
        cases.append((wrong_age, "attained_age_years must equal"))
        endpoint = transformation()
        endpoint["life_table"]["cycle_probabilities"][0]["annual_probability"]["value"] = 1.0
        cases.append((endpoint, "exclusive"))
        negative = transformation()
        negative["excess_mortality_rate_per_year"]["value"] = -0.01
        cases.append((negative, "at least 0.0"))
        nonfinite = transformation()
        nonfinite["excess_mortality_rate_per_year"]["value"] = float("inf")
        cases.append((nonfinite, "finite number"))
        saturated = transformation()
        saturated["excess_mortality_rate_per_year"]["value"] = 1e308
        cases.append((saturated, "invalid probability"))

        for declaration, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                BackgroundMortalityError, message
            ):
                derive_background_mortality_schedule(
                    declaration,
                    state_count=2,
                    cycles=3,
                    cycle_length_years=0.5,
                )

    def test_zero_background_and_excess_mortality_are_valid(self) -> None:
        declaration = transformation()
        declaration["excess_mortality_rate_per_year"]["value"] = 0.0
        for probability in declaration["life_table"]["cycle_probabilities"]:
            probability["annual_probability"]["value"] = 0.0

        schedule, _, _ = derive_background_mortality_schedule(
            declaration,
            state_count=2,
            cycles=3,
            cycle_length_years=0.5,
        )

        self.assertEqual(
            schedule,
            [
                {"start_cycle": cycle, "matrix": [[1.0, 0.0], [0.0, 1.0]]}
                for cycle in (1, 2, 3)
            ],
        )

    def test_finite_inputs_cannot_overflow_integrated_hazard_silently(self) -> None:
        declaration = transformation()
        declaration["cycle_length_years"] = 1e308
        declaration["excess_mortality_rate_per_year"]["value"] = 1e308
        declaration["life_table"]["cycle_probabilities"] = declaration["life_table"]["cycle_probabilities"][:1]

        with self.assertRaisesRegex(BackgroundMortalityError, "non-finite hazard"):
            derive_background_mortality_schedule(
                declaration,
                state_count=2,
                cycles=1,
                cycle_length_years=1e308,
            )

    def test_schema_09_analysis_can_bind_exact_budget_pair(self) -> None:
        base = analysis_payload()
        base["budget_impact_analysis"] = {"path": "heor/budget-impact-plan.json"}
        base_raw = json.dumps(base, separators=(",", ":"), sort_keys=True).encode()
        budget = json.loads(BUDGET_IMPACT_PATH.read_text())
        budget["analysis_id"] = base["analysis_id"]
        budget["base_analysis"]["content_sha256"] = hashlib.sha256(base_raw).hexdigest()
        budget["strategies"]["comparator"]["id"] = "standard_care"
        budget["strategies"]["intervention"]["id"] = "higher_risk"
        budget_raw = json.dumps(budget, separators=(",", ":"), sort_keys=True).encode()

        result = run_budget_impact(base, base_raw, budget, budget_raw)

        self.assertEqual(result["analysis_id"], base["analysis_id"])


class BackgroundMortalityUncertaintyTests(unittest.TestCase):
    def test_excess_rate_supports_dsa_and_seeded_psa_with_complete_recomputation(self) -> None:
        base = analysis_payload()
        base_raw = json.dumps(base, separators=(",", ":"), sort_keys=True).encode()
        uncertainty = uncertainty_payload(base, base_raw)
        uncertainty_raw = json.dumps(
            uncertainty, separators=(",", ":"), sort_keys=True
        ).encode()

        first = run_uncertainty(base, base_raw, uncertainty, uncertainty_raw)
        second = run_uncertainty(base, base_raw, uncertainty, uncertainty_raw)

        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], "0.8.0")
        self.assertEqual(first["engine_version"], "0.9.0")
        self.assertEqual(len(first["probabilistic_analysis"]["samples"]), 1000)
        specification = UncertaintySpecification.from_dict(
            uncertainty, base, hashlib.sha256(base_raw).hexdigest()
        )
        recomputed = _apply_parameter_values(
            base, ((specification.parameters[0], 0.10),)
        )
        mapping = recomputed["input_provenance"][0]
        expected, _, _ = derive_background_mortality_schedule(
            mapping["derivation"]["transformation"],
            state_count=2,
            cycles=3,
            cycle_length_years=0.5,
        )
        self.assertEqual(
            recomputed["strategies"]["higher_risk"]["transition_schedule"], expected
        )
        self.assertEqual(mapping["derivation"]["model_value"], expected)

    def test_schema_pairing_is_exact_and_old_08_07_pair_remains_supported(self) -> None:
        base09 = analysis_payload()
        raw09 = json.dumps(base09, sort_keys=True).encode()
        wrong08 = uncertainty_payload(base09, raw09)
        wrong08["schema_version"] = "0.7.0"
        with self.assertRaisesRegex(ModelValidationError, "0.9.0 requires uncertainty schema_version 0.8.0"):
            run_uncertainty(base09, raw09, wrong08, json.dumps(wrong08).encode())

        base08 = copy.deepcopy(base09)
        base08["schema_version"] = "0.8.0"
        base08["input_provenance"] = []
        base08["strategies"]["higher_risk"].pop("transition_schedule")
        base08["strategies"]["higher_risk"]["transition_matrix"] = [[0.9, 0.1], [0.0, 1.0]]
        raw08 = json.dumps(base08, sort_keys=True).encode()
        wrong09 = uncertainty_payload(base08, raw08)
        with self.assertRaisesRegex(ModelValidationError, "0.8.0 requires uncertainty schema_version 0.7.0"):
            run_uncertainty(base08, raw08, wrong09, json.dumps(wrong09).encode())

    def test_only_strictly_positive_excess_value_may_vary_and_life_table_stays_fixed(self) -> None:
        base = analysis_payload()
        base_raw = json.dumps(base, sort_keys=True).encode()
        cases: list[tuple[dict, str]] = []
        q_target = uncertainty_payload(base, base_raw)
        q_target["parameters"][0]["target"] = "/input_provenance/0/derivation/transformation/life_table/cycle_probabilities/0/annual_probability/value"
        cases.append((q_target, "only the exact excess"))
        zero_low = uncertainty_payload(base, base_raw)
        zero_low["parameters"][0]["deterministic"]["low"] = 0.0
        cases.append((zero_low, "must be positive"))
        zero_uniform = uncertainty_payload(base, base_raw)
        zero_uniform["parameters"][0]["probabilistic"] = {
            "type": "uniform",
            "low": 0.0,
            "high": 0.1,
            "basis_ids": ["excess-rate"],
            "rationale": "Invalid non-positive lower bound.",
        }
        cases.append((zero_uniform, "must be positive"))
        scenario = uncertainty_payload(base, base_raw)
        scenario["structural_scenarios"][0]["replacements"] = [
            {
                "target": "/input_provenance/0/derivation/transformation/life_table/cycle_probabilities/0/annual_probability/value",
                "value": 0.2,
            }
        ]
        cases.append((scenario, "outside the allowlist"))
        cycle_scenario = uncertainty_payload(base, base_raw)
        cycle_scenario["structural_scenarios"][0]["replacements"] = [
            {"target": "/cycle_length_years", "value": 1.0}
        ]
        cases.append((cycle_scenario, "outside the allowlist"))

        for uncertainty, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                ModelValidationError, message
            ):
                run_uncertainty(
                    base, base_raw, uncertainty, json.dumps(uncertainty).encode()
                )

        zero_base = analysis_payload()
        zero_base["input_provenance"][0]["derivation"]["transformation"]["excess_mortality_rate_per_year"]["value"] = 0.0
        schedule, _, _ = derive_background_mortality_schedule(
            zero_base["input_provenance"][0]["derivation"]["transformation"],
            state_count=2,
            cycles=3,
            cycle_length_years=0.5,
        )
        zero_base["strategies"]["higher_risk"]["transition_schedule"] = schedule
        zero_base["input_provenance"][0]["derivation"]["model_value"] = copy.deepcopy(schedule)
        zero_raw = json.dumps(zero_base, sort_keys=True).encode()
        zero_uncertainty = uncertainty_payload(zero_base, zero_raw)
        with self.assertRaisesRegex(ModelValidationError, "base value must be strictly positive"):
            run_uncertainty(
                zero_base,
                zero_raw,
                zero_uncertainty,
                json.dumps(zero_uncertainty).encode(),
            )


if __name__ == "__main__":
    unittest.main()
