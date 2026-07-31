from __future__ import annotations

import copy
import hashlib
import json
import unittest
from math import exp, log, sqrt
from pathlib import Path
from types import SimpleNamespace

from heor_core.budget_impact import _required_provenance_paths, run_budget_impact
from heor_core.model import (
    MarkovSpecification,
    ModelValidationError,
    run_markov,
)
from heor_core.probability_time import (
    ProbabilityTimeError,
    _transition_path as probability_transition_path,
    derive_probability_time,
)
from heor_core.survival_curves import (
    SurvivalCurveError,
    _transition_schedule_path as survival_transition_schedule_path,
    derive_survival_schedule,
)
from heor_core.transition_rates import _transition_path as rate_transition_path
from heor_core.uncertainty import (
    Pcg32,
    UncertaintySpecification,
    _apply_parameter_values,
    _cholesky,
    _correlation_matrix,
    _multi_strategy_decision_uncertainty,
    _run_psa,
    _sample_parameter_values,
    run_uncertainty,
)


GOLDEN_PATH = Path(__file__).parents[1] / "golden_cases" / "two_strategy_markov.json"
TIME_VARYING_PATH = (
    Path(__file__).parents[1] / "golden_cases" / "two_strategy_time_varying.json"
)
RATE_DERIVED_PATH = (
    Path(__file__).parents[1] / "golden_cases" / "two_strategy_rate_derived.json"
)
UNCERTAINTY_PATH = (
    Path(__file__).parents[1] / "golden_cases" / "two_strategy_uncertainty.json"
)
BUDGET_BASE_PATH = (
    Path(__file__).parents[1] / "golden_cases" / "two_strategy_budget_base.json"
)
BUDGET_IMPACT_PATH = (
    Path(__file__).parents[1] / "golden_cases" / "two_strategy_budget_impact.json"
)
REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def golden_payload() -> dict:
    return json.loads(GOLDEN_PATH.read_text())


def uncertainty_payload() -> dict:
    return json.loads(UNCERTAINTY_PATH.read_text())


def time_varying_payload() -> dict:
    return json.loads(TIME_VARYING_PATH.read_text())


def rate_derived_payload() -> dict:
    return json.loads(RATE_DERIVED_PATH.read_text())


def survival_derived_payload() -> dict:
    value = rate_derived_payload()
    value["schema_version"] = "0.6.0"
    value["analysis_id"] = "golden-survival-derived"
    value["strategies"]["comparator"].pop("transition_matrix")
    value["strategies"]["intervention"].pop("transition_matrix")
    comparator_rate = -log(0.8)
    comparator_schedule = []
    intervention_schedule = []
    previous_hazard = 0.0
    for cycle in range(1, 4):
        comparator_event = 1.0 - exp(-comparator_rate)
        comparator_schedule.append({
            "start_cycle": cycle,
            "matrix": [[1.0 - comparator_event, comparator_event], [0.0, 1.0]],
        })
        cumulative_hazard = (cycle / 4.0) ** 2.0
        intervention_event = 1.0 - exp(-(cumulative_hazard - previous_hazard))
        intervention_schedule.append({
            "start_cycle": cycle,
            "matrix": [[1.0 - intervention_event, intervention_event], [0.0, 1.0]],
        })
        previous_hazard = cumulative_hazard
    value["strategies"]["comparator"]["transition_schedule"] = comparator_schedule
    value["strategies"]["intervention"]["transition_schedule"] = intervention_schedule
    value["assumptions"] = [
        {
            "id": "comparator-survival-rate",
            "statement": "Use the declared comparator exponential rate.",
            "reason": "Hand-checkable survival adapter fixture.",
            "status": "proposed",
        },
        {
            "id": "intervention-weibull-shape",
            "statement": "Use the declared intervention Weibull shape.",
            "reason": "Hand-checkable survival adapter fixture.",
            "status": "proposed",
        },
        {
            "id": "intervention-weibull-scale",
            "statement": "Use the declared intervention Weibull scale in years.",
            "reason": "Hand-checkable survival adapter fixture.",
            "status": "proposed",
        },
    ]
    value["input_provenance"] = [
        {
            "path": "strategies.comparator.transition_schedule",
            "source_ids": [],
            "extraction_ids": [],
            "assumption_ids": ["comparator-survival-rate"],
            "derivation": {
                "method": "deterministic_transformation",
                "model_value": copy.deepcopy(comparator_schedule),
                "transformation": {
                    "operation": "parametric_survival_to_transition_schedule",
                    "cycle_length_years": 1.0,
                    "from_state_index": 0,
                    "event_state_index": 1,
                    "distribution": "exponential",
                    "parameters": {
                        "rate_per_year": {
                            "value": comparator_rate,
                            "assumption_id": "comparator-survival-rate",
                        }
                    },
                },
            },
        },
        {
            "path": "strategies.intervention.transition_schedule",
            "source_ids": [],
            "extraction_ids": [],
            "assumption_ids": [
                "intervention-weibull-shape",
                "intervention-weibull-scale",
            ],
            "derivation": {
                "method": "deterministic_transformation",
                "model_value": copy.deepcopy(intervention_schedule),
                "transformation": {
                    "operation": "parametric_survival_to_transition_schedule",
                    "cycle_length_years": 1.0,
                    "from_state_index": 0,
                    "event_state_index": 1,
                    "distribution": "weibull",
                    "parameters": {
                        "shape": {
                            "value": 2.0,
                            "assumption_id": "intervention-weibull-shape",
                        },
                        "scale_years": {
                            "value": 4.0,
                            "assumption_id": "intervention-weibull-scale",
                        },
                    },
                },
            },
        },
    ]
    return value


def probability_time_payload() -> dict:
    value = rate_derived_payload()
    value["schema_version"] = "0.7.0"
    value["analysis_id"] = "golden-probability-time-derived"
    probability = 0.36
    converted = 1.0 - (1.0 - probability) ** 0.5
    comparator_matrix = [[0.8, 0.2], [0.0, 1.0]]
    intervention_matrix = [[1.0 - converted, converted], [0.0, 1.0]]
    value["strategies"]["comparator"]["transition_matrix"] = comparator_matrix
    value["strategies"]["intervention"]["transition_matrix"] = intervention_matrix
    value["assumptions"] = [
        {
            "id": "comparator-mortality-rate",
            "statement": "Use the declared comparator cycle probability.",
            "reason": "Hand-checkable probability-time conversion fixture.",
            "status": "proposed",
        },
        {
            "id": "intervention-two-year-event-probability",
            "statement": "Use the declared two-year single-event probability.",
            "reason": "Hand-checkable probability-time conversion fixture.",
            "status": "proposed",
        },
    ]
    value["input_provenance"] = [
        {
            "path": "strategies.comparator.transition_matrix",
            "source_ids": [],
            "extraction_ids": [],
            "assumption_ids": ["comparator-mortality-rate"],
            "derivation": {
                "method": "explicit_assumption",
                "model_value": comparator_matrix,
            },
        },
        {
            "path": "strategies.intervention.transition_matrix",
            "source_ids": [],
            "extraction_ids": [],
            "assumption_ids": ["intervention-two-year-event-probability"],
            "derivation": {
                "method": "deterministic_transformation",
                "model_value": intervention_matrix,
                "transformation": {
                    "operation": "single_event_probability_time_conversion",
                    "cycle_length_years": 1.0,
                    "phases": [{
                        "start_cycle": 1,
                        "rows": [
                            {
                                "self_index": 0,
                                "event": {
                                    "target_index": 1,
                                    "source_probability": probability,
                                    "source_interval_years": 2.0,
                                    "assumption_id": "intervention-two-year-event-probability",
                                },
                            },
                            {"self_index": 1, "event": None},
                        ],
                    }],
                },
            },
        },
    ]
    return value


def probability_uncertainty_payload(base: dict, base_raw: bytes) -> dict:
    value = uncertainty_payload()
    value["schema_version"] = "0.6.0"
    value["uncertainty_id"] = "golden-probability-time-uncertainty"
    value["analysis_id"] = base["analysis_id"]
    value["base_analysis"]["content_sha256"] = hashlib.sha256(base_raw).hexdigest()
    value["parameters"] = [{
        "id": "intervention-two-year-event-probability",
        "label": "Intervention two-year event probability",
        "target": "/input_provenance/1/derivation/transformation/phases/0/rows/0/event/source_probability",
        "provenance_path": "strategies.intervention.transition_matrix",
        "deterministic": {
            "low": 0.25,
            "high": 0.49,
            "rationale": "Evidence-bound probability range.",
        },
        "probabilistic": {
            "type": "beta",
            "alpha": 36.0,
            "beta": 64.0,
            "basis_ids": ["intervention-two-year-event-probability"],
            "rationale": "Beta distribution for the bounded source probability.",
        },
    }]
    value["probabilistic_analysis"]["correlation_handling"]["groups"] = []
    return value


def rate_uncertainty_payload(base_raw: bytes | None = None) -> dict:
    value = uncertainty_payload()
    raw = base_raw if base_raw is not None else RATE_DERIVED_PATH.read_bytes()
    value["schema_version"] = "0.3.0"
    value["uncertainty_id"] = "golden-rate-derived-uncertainty"
    value["analysis_id"] = "golden-rate-derived"
    value["base_analysis"]["content_sha256"] = hashlib.sha256(raw).hexdigest()
    value["parameters"] = [{
        "id": "intervention-mortality-rate",
        "label": "Intervention mortality event rate",
        "target": "/input_provenance/1/derivation/transformation/phases/0/rows/0/events/0/rate_per_year",
        "provenance_path": "strategies.intervention.transition_matrix",
        "deterministic": {
            "low": 0.05,
            "high": 0.2,
            "rationale": "Bounded rate-space sensitivity range for the golden test",
        },
        "probabilistic": {
            "type": "gamma",
            "shape": 4.0,
            "scale": 0.02634012891445657,
            "basis_ids": ["intervention-mortality-rate"],
            "rationale": "Positive event-rate distribution centered on the base rate",
        },
    }]
    return value


def survival_uncertainty_payload(base: dict, base_raw: bytes) -> dict:
    value = uncertainty_payload()
    value["schema_version"] = "0.5.0"
    value["uncertainty_id"] = "golden-survival-derived-uncertainty"
    value["analysis_id"] = base["analysis_id"]
    value["base_analysis"]["content_sha256"] = hashlib.sha256(base_raw).hexdigest()
    value["parameters"] = [
        {
            "id": "comparator-survival-rate",
            "label": "Comparator exponential survival rate",
            "target": "/input_provenance/0/derivation/transformation/parameters/rate_per_year/value",
            "provenance_path": "strategies.comparator.transition_schedule",
            "deterministic": {
                "low": 0.1,
                "high": 0.4,
                "rationale": "Positive bounded rate range for complete schedule recomputation",
            },
            "probabilistic": {
                "type": "gamma",
                "shape": 4.0,
                "scale": (-log(0.8)) / 4.0,
                "basis_ids": ["comparator-survival-rate"],
                "rationale": "Positive distribution centered on the declared exponential rate",
            },
        },
        {
            "id": "intervention-weibull-shape",
            "label": "Intervention Weibull shape",
            "target": "/input_provenance/1/derivation/transformation/parameters/shape/value",
            "provenance_path": "strategies.intervention.transition_schedule",
            "deterministic": {
                "low": 1.5,
                "high": 2.5,
                "rationale": "Positive bounded shape range for complete schedule recomputation",
            },
            "probabilistic": {
                "type": "lognormal",
                "mu_log": log(2.0),
                "sigma_log": 0.1,
                "basis_ids": ["intervention-weibull-shape"],
                "rationale": "Positive distribution centered on the declared Weibull shape",
            },
        },
        {
            "id": "intervention-weibull-scale",
            "label": "Intervention Weibull scale",
            "target": "/input_provenance/1/derivation/transformation/parameters/scale_years/value",
            "provenance_path": "strategies.intervention.transition_schedule",
            "deterministic": {
                "low": 3.0,
                "high": 5.0,
                "rationale": "Positive bounded scale range for complete schedule recomputation",
            },
            "probabilistic": {
                "type": "uniform",
                "low": 3.0,
                "high": 5.0,
                "basis_ids": ["intervention-weibull-scale"],
                "rationale": "Strictly positive bounded scale distribution",
            },
        },
    ]
    value["probabilistic_analysis"]["correlation_handling"]["groups"] = []
    value["structural_scenarios"] = [{
        "id": "alternate-cost-discount",
        "label": "Alternative cost discount rate",
        "rationale": "Keeps structural uncertainty separate from curve parameters",
        "replacements": [{"target": "/discount_rates/costs", "value": 0.02}],
    }]
    return value


def budget_base_payload() -> dict:
    return json.loads(BUDGET_BASE_PATH.read_text())


def budget_impact_payload() -> dict:
    return json.loads(BUDGET_IMPACT_PATH.read_text())


def dynamic_budget_impact_payload() -> dict:
    value = budget_impact_payload()
    value["schema_version"] = "0.2.0"
    value["bia_id"] = "golden-dynamic-budget-impact"
    value["population"] = {
        "label": "Treated prevalent and incident population",
        "initial_prevalent": 100.0,
        "incident_by_year": [20.0, 20.0, 20.0],
        "derivation": "Synthetic annual-boundary dynamic-cohort fixture.",
    }
    value["annual_mortality_probability"] = [0.1, 0.1, 0.1]
    value["market_scenarios"] = {
        "without_new_intervention": {
            "label": "Without access",
            "initial_intervention_share": 0.0,
            "incident_intervention_share_by_year": [0.0, 0.0, 0.0],
            "comparator_displacement_share_by_year": [0.0, 0.0, 0.0],
            "intervention_start_capacity_by_year": [0.0, 0.0, 0.0],
        },
        "with_new_intervention": {
            "label": "With access",
            "initial_intervention_share": 0.2,
            "incident_intervention_share_by_year": [0.5, 0.5, 0.5],
            "comparator_displacement_share_by_year": [0.1, 0.1, 0.1],
            "intervention_start_capacity_by_year": [30.0, 30.0, 30.0],
        },
    }
    value["persistence"] = {
        "comparator_continuation_probability_by_year": [0.9, 0.9, 0.9],
        "intervention_continuation_probability_by_year": [0.8, 0.8, 0.8],
        "comparator_discontinuation_destination": "exit_treated_market",
        "intervention_discontinuation_destination": "comparator",
    }
    value["cost_categories"][0]["annual_per_patient"] = {
        "comparator": [100.0, 100.0, 100.0],
        "intervention": [200.0, 200.0, 200.0],
    }
    value["cost_categories"][1]["annual_per_patient"] = {
        "comparator": [0.0, 0.0, 0.0],
        "intervention": [0.0, 0.0, 0.0],
    }
    value["non_patient_costs"] = []
    value["sensitivity_parameters"] = [{
        "id": "initial-prevalence",
        "label": "Initial prevalent population",
        "target": "/population/initial_prevalent",
        "low": 90.0,
        "high": 110.0,
        "basis_ids": ["golden-synthetic"],
    }]
    value["alternative_scenarios"] = [{
        "scenario_id": "lower-capacity",
        "label": "Lower start capacity",
        "rationale": "Synthetic capacity constraint.",
        "overrides": [{
            "target": "/market_scenarios/with_new_intervention/intervention_start_capacity_by_year/0",
            "value": 5.0,
        }],
        "basis_ids": ["golden-synthetic"],
    }]
    value["input_provenance"] = []
    for path in sorted(_required_provenance_paths(value)):
        mapping = {
            "path": path,
            "assumption_ids": ["golden-synthetic"],
            "unit": "synthetic input",
            "jurisdiction": "China",
            "selection_rationale": "Synthetic dynamic-cohort fixture.",
            "uncertainty_status": "fixed",
        }
        if path.startswith("/cost_categories/") or path.startswith("/non_patient_costs/"):
            mapping["price_year"] = 2026
        value["input_provenance"].append(mapping)
    value["limitations"] = [
        "Synthetic annual-boundary cohort fixture; it is not patient-level simulation."
    ]
    return value


def multi_strategy_payload() -> dict:
    value = golden_payload()
    value.update({
        "schema_version": "0.8.0",
        "analysis_id": "golden-multi-strategy",
        "states": ["alive"],
        "cycles": 2,
        "cycle_length_years": 1.0,
        "discount_rates": {"costs": 0.0, "outcomes": 0.0},
        "half_cycle_correction": False,
        "willingness_to_pay": 80.0,
        "baseline_strategy_id": "standard_care",
        "strategy_order": [
            "standard_care",
            "middle",
            "best",
            "dominated",
            "same_as_standard",
        ],
    })
    value["strategies"] = {
        "standard_care": {
            "name": "Standard care",
            "initial_distribution": [1.0],
            "transition_matrix": [[1.0]],
            "state_costs": [0.0],
            "state_utilities": [0.0],
        },
        "middle": {
            "name": "Middle option",
            "initial_distribution": [1.0],
            "transition_matrix": [[1.0]],
            "state_costs": [50.0],
            "state_utilities": [0.5],
        },
        "best": {
            "name": "Most effective option",
            "initial_distribution": [1.0],
            "transition_matrix": [[1.0]],
            "state_costs": [75.0],
            "state_utilities": [1.0],
        },
        "dominated": {
            "name": "Strictly dominated option",
            "initial_distribution": [1.0],
            "transition_matrix": [[1.0]],
            "state_costs": [100.0],
            "state_utilities": [0.75],
        },
        "same_as_standard": {
            "name": "Equivalent option",
            "initial_distribution": [1.0],
            "transition_matrix": [[1.0]],
            "state_costs": [0.0],
            "state_utilities": [0.0],
        },
    }
    value["input_provenance"] = []
    return value


def multi_strategy_uncertainty_payload(base: dict, base_raw: bytes) -> dict:
    value = uncertainty_payload()
    value.update({
        "schema_version": "0.7.0",
        "uncertainty_id": "golden-multi-strategy-uncertainty",
        "analysis_id": base["analysis_id"],
    })
    value["base_analysis"]["content_sha256"] = hashlib.sha256(base_raw).hexdigest()
    value["parameters"] = [{
        "id": "best-state-cost",
        "label": "Most effective option state cost",
        "target": "/strategies/best/state_costs/0",
        "provenance_path": "strategies.best.state_costs",
        "deterministic": {
            "low": 50.0,
            "high": 100.0,
            "rationale": "Hand-checkable deterministic range.",
        },
        "probabilistic": {
            "type": "gamma",
            "shape": 100.0,
            "scale": 0.75,
            "basis_ids": ["best-cost-source"],
            "rationale": "Positive distribution centered on the base cost.",
        },
    }]
    value["probabilistic_analysis"]["decision_thresholds"] = {
        "values": [0.0, 50.0, 80.0, 100.0, 200.0],
        "rationale": "Hand-checkable multi-strategy decision threshold grid.",
    }
    value["probabilistic_analysis"]["correlation_handling"] = {
        "independence_rationale": "Only one parameter is varied in this bounded fixture.",
        "known_omitted_correlations": [],
        "groups": [],
    }
    value["probabilistic_analysis"]["omitted_parameters"] = [{
        "provenance_path": "strategies.middle.state_costs",
        "rationale": "Held fixed for this bounded multi-strategy fixture.",
    }]
    value["structural_scenarios"] = [{
        "id": "cost-discounting",
        "label": "Cost discounting",
        "rationale": "Tests a structural replacement across all strategies.",
        "replacements": [{"target": "/discount_rates/costs", "value": 0.05}],
    }]
    return value


def multi_strategy_budget_base_payload() -> dict:
    value = multi_strategy_payload()
    value["budget_impact_analysis"] = {
        "path": "heor/budget-impact-plan.json",
    }
    value["decision_problem"] = {"jurisdiction": "China"}
    return value


class MarkovModelTests(unittest.TestCase):
    def test_multi_strategy_analysis_builds_complete_incremental_frontier(self) -> None:
        result = run_markov(MarkovSpecification.from_dict(multi_strategy_payload()))
        payload = result.to_dict()

        self.assertEqual(result.engine_version, "0.8.0")
        self.assertEqual(payload["baseline_strategy_id"], "standard_care")
        self.assertEqual(
            list(payload["pairwise_vs_baseline"]),
            ["middle", "best", "dominated", "same_as_standard"],
        )
        rows = {
            row["strategy_id"]: row
            for row in payload["fully_incremental_analysis"]
        }
        self.assertEqual(rows["standard_care"]["status"], "frontier")
        self.assertEqual(rows["same_as_standard"]["status"], "equivalent")
        self.assertEqual(
            rows["same_as_standard"]["dominated_by_strategy_ids"],
            ["standard_care"],
        )
        self.assertEqual(rows["middle"]["status"], "extendedly_dominated")
        self.assertEqual(
            rows["middle"]["dominated_by_strategy_ids"],
            ["standard_care", "best"],
        )
        self.assertEqual(rows["dominated"]["status"], "strictly_dominated")
        self.assertIn("best", rows["dominated"]["dominated_by_strategy_ids"])
        self.assertEqual(rows["best"]["compared_with_strategy_id"], "standard_care")
        self.assertAlmostEqual(rows["best"]["icer"], 75.0)
        self.assertEqual(
            payload["optimal_at_primary_threshold"],
            {
                "threshold": 80.0,
                "strategy_id": "best",
                "tied_strategy_ids": [],
                "net_monetary_benefit": 10.0,
            },
        )

    def test_multi_strategy_contract_rejects_ambiguous_or_extra_ids(self) -> None:
        payload = multi_strategy_payload()
        payload["baseline_strategy_id"] = "best"
        with self.assertRaisesRegex(ModelValidationError, "must be the first"):
            MarkovSpecification.from_dict(payload)

        payload = multi_strategy_payload()
        payload["strategies"]["undeclared"] = payload["strategies"]["best"]
        with self.assertRaisesRegex(ModelValidationError, "exactly the ids"):
            MarkovSpecification.from_dict(payload)

        payload = multi_strategy_payload()
        payload["strategy_order"][1] = "Middle Option"
        payload["strategies"]["Middle Option"] = payload["strategies"].pop("middle")
        with self.assertRaisesRegex(ModelValidationError, "lowercase letter"):
            MarkovSpecification.from_dict(payload)

    def test_legacy_contract_rejects_extra_ignored_strategy_keys(self) -> None:
        payload = golden_payload()
        payload["strategies"]["ignored"] = copy.deepcopy(
            payload["strategies"]["intervention"]
        )
        payload["strategies"]["ignored"]["name"] = "ignored"

        with self.assertRaisesRegex(
            ModelValidationError, "exactly comparator and intervention"
        ):
            MarkovSpecification.from_dict(payload)

    def test_dynamic_mapping_paths_use_schema_specific_strategy_membership(self) -> None:
        multi = multi_strategy_payload()
        self.assertTrue(
            rate_transition_path(
                "strategies.best.transition_matrix", multi, "0.8.0"
            )
        )
        self.assertTrue(
            survival_transition_schedule_path(
                "strategies.best.transition_schedule", multi, "0.8.0"
            )
        )
        self.assertTrue(
            probability_transition_path(
                "strategies.best.transition_matrix", multi, "0.8.0"
            )
        )
        for validator, path in (
            (rate_transition_path, "strategies.ignored.transition_matrix"),
            (
                survival_transition_schedule_path,
                "strategies.ignored.transition_schedule",
            ),
            (probability_transition_path, "strategies.ignored.transition_matrix"),
        ):
            self.assertFalse(validator(path, multi, "0.8.0"))
            self.assertFalse(validator(path, golden_payload(), "0.7.0"))

    def test_equivalent_points_are_grouped_before_strict_dominance(self) -> None:
        payload = multi_strategy_payload()
        payload["strategy_order"] = ["duplicate_a", "duplicate_b", "dominant"]
        payload["baseline_strategy_id"] = "duplicate_a"
        payload["strategies"] = {
            "duplicate_a": {
                "name": "Duplicate A",
                "initial_distribution": [1.0],
                "transition_matrix": [[1.0]],
                "state_costs": [10.0],
                "state_utilities": [0.5],
            },
            "duplicate_b": {
                "name": "Duplicate B",
                "initial_distribution": [1.0],
                "transition_matrix": [[1.0]],
                "state_costs": [10.0],
                "state_utilities": [0.5],
            },
            "dominant": {
                "name": "Dominant",
                "initial_distribution": [1.0],
                "transition_matrix": [[1.0]],
                "state_costs": [0.0],
                "state_utilities": [1.0],
            },
        }

        result = run_markov(MarkovSpecification.from_dict(payload)).to_dict()
        rows = {
            row["strategy_id"]: row
            for row in result["fully_incremental_analysis"]
        }

        self.assertEqual(rows["duplicate_a"]["status"], "strictly_dominated")
        self.assertEqual(rows["duplicate_b"]["status"], "equivalent")
        self.assertEqual(
            rows["duplicate_b"]["dominated_by_strategy_ids"], ["duplicate_a"]
        )
        self.assertEqual(rows["dominant"]["status"], "frontier")

    def test_finite_inputs_cannot_produce_non_finite_outputs(self) -> None:
        payload = multi_strategy_payload()
        payload["cycles"] = 1
        payload["cycle_length_years"] = 1e308
        payload["strategy_order"] = ["first", "second"]
        payload["baseline_strategy_id"] = "first"
        payload["strategies"] = {
            strategy_id: {
                "name": strategy_id.title(),
                "initial_distribution": [1.0],
                "transition_matrix": [[1.0]],
                "state_costs": [1e308],
                "state_utilities": [1.0],
            }
            for strategy_id in payload["strategy_order"]
        }

        with self.assertRaisesRegex(ModelValidationError, "non-finite"):
            run_markov(MarkovSpecification.from_dict(payload))

    def test_golden_case_matches_independent_hand_calculation(self) -> None:
        result = run_markov(MarkovSpecification.from_dict(golden_payload()))

        self.assertAlmostEqual(result.comparator.total_cost, 3475.288593111165)
        self.assertAlmostEqual(result.comparator.total_qaly, 1.6883071262009621)
        self.assertAlmostEqual(result.intervention.total_cost, 9649.958833579347)
        self.assertAlmostEqual(result.intervention.total_qaly, 1.8826406968498461)
        self.assertAlmostEqual(result.incremental.delta_cost, 6174.670240468182)
        self.assertAlmostEqual(result.incremental.delta_qaly, 0.194333570648884)
        self.assertAlmostEqual(result.incremental.icer, 31773.564494548336)
        self.assertEqual(result.incremental.interpretation, "tradeoff")
        self.assertEqual(result.calculation_classification, "calculation_only")
        self.assertEqual(
            result.economic_basis,
            {"currency": "CNY", "price_year": 2026},
        )

    def test_invalid_iso_currency_is_rejected(self) -> None:
        payload = golden_payload()
        payload["economic_basis"]["currency"] = "cny"

        with self.assertRaisesRegex(ModelValidationError, "ISO 4217"):
            MarkovSpecification.from_dict(payload)

    def test_legacy_plan_remains_calculable_but_has_no_claimed_basis(self) -> None:
        payload = golden_payload()
        payload["schema_version"] = "0.1.0"
        del payload["economic_basis"]

        result = run_markov(MarkovSpecification.from_dict(payload))

        self.assertIsNone(result.economic_basis)
        self.assertIn("Legacy analysis schema", " ".join(result.warnings))

    def test_prior_plan_keeps_basis_but_warns_that_derivations_are_not_approvable(self) -> None:
        payload = golden_payload()
        payload["schema_version"] = "0.2.0"

        result = run_markov(MarkovSpecification.from_dict(payload))

        self.assertEqual(result.economic_basis, {"currency": "CNY", "price_year": 2026})
        self.assertIn("derivations are not executable", " ".join(result.warnings))

    def test_cohort_mass_is_conserved_in_every_cycle(self) -> None:
        result = run_markov(MarkovSpecification.from_dict(golden_payload()))

        for strategy in (result.comparator, result.intervention):
            for occupancy in strategy.occupancy:
                self.assertAlmostEqual(sum(occupancy), 1.0)

    def test_invalid_transition_row_is_rejected(self) -> None:
        payload = golden_payload()
        payload["strategies"]["intervention"]["transition_matrix"][0] = [
            0.8,
            0.15,
            0.1,
        ]

        with self.assertRaisesRegex(ModelValidationError, "must sum to 1"):
            MarkovSpecification.from_dict(payload)

    def test_piecewise_transition_schedule_matches_hand_calculation(self) -> None:
        result = run_markov(MarkovSpecification.from_dict(time_varying_payload()))

        self.assertEqual(result.comparator.transition_mode, "static")
        self.assertEqual(result.comparator.transition_schedule_start_cycles, (1,))
        self.assertEqual(
            result.intervention.transition_mode,
            "piecewise_by_model_cycle",
        )
        self.assertEqual(
            result.intervention.transition_schedule_start_cycles,
            (1, 2, 3),
        )
        self.assertAlmostEqual(result.comparator.total_qaly, 3.439)
        self.assertAlmostEqual(result.intervention.total_qaly, 3.489)
        self.assertAlmostEqual(result.intervention.total_cost, 348.9)
        self.assertAlmostEqual(result.incremental.delta_qaly, 0.05)
        self.assertAlmostEqual(result.incremental.icer, 6978.0)
        expected_occupancy = (
            (1.0, 0.0),
            (0.95, 0.05),
            (0.855, 0.145),
            (0.684, 0.316),
            (0.5472, 0.4528),
        )
        for actual, expected in zip(
            result.intervention.occupancy, expected_occupancy
        ):
            for actual_value, expected_value in zip(actual, expected):
                self.assertAlmostEqual(actual_value, expected_value)

    def test_transition_schedule_requires_current_schema(self) -> None:
        payload = time_varying_payload()
        payload["schema_version"] = "0.3.0"

        with self.assertRaisesRegex(
            ModelValidationError,
            "transition_schedule requires schema_version 0.4.0, 0.5.0, 0.6.0, or 0.7.0",
        ):
            MarkovSpecification.from_dict(payload)

    def test_constant_rate_derivations_match_hand_calculation(self) -> None:
        result = run_markov(MarkovSpecification.from_dict(rate_derived_payload()))

        self.assertEqual(result.engine_version, "0.7.0")
        self.assertEqual(result.schema_version, "0.5.0")
        self.assertAlmostEqual(result.comparator.total_qaly, 2.44)
        self.assertAlmostEqual(result.intervention.total_qaly, 2.71)
        self.assertAlmostEqual(result.intervention.total_cost, 271.0)
        self.assertAlmostEqual(result.incremental.delta_qaly, 0.27)
        self.assertAlmostEqual(result.incremental.icer, 271.0 / 0.27)

    def test_rate_derivation_must_reproduce_the_current_matrix(self) -> None:
        payload = rate_derived_payload()
        payload["strategies"]["intervention"]["transition_matrix"][0] = [0.85, 0.15]
        payload["input_provenance"][1]["derivation"]["model_value"][0] = [0.85, 0.15]

        with self.assertRaisesRegex(
            ModelValidationError, "rates do not reproduce"
        ):
            MarkovSpecification.from_dict(payload)

    def test_rate_derivation_must_bind_every_declared_basis(self) -> None:
        payload = rate_derived_payload()
        payload["input_provenance"][1]["assumption_ids"].append("unused-rate")

        with self.assertRaisesRegex(
            ModelValidationError, "use every proposed assumption"
        ):
            MarkovSpecification.from_dict(payload)

    def test_rate_derivation_supports_piecewise_model_cycle_phases(self) -> None:
        payload = rate_derived_payload()
        payload["assumptions"].append({
            "id": "later-intervention-rate",
            "statement": "Later intervention mortality rate",
            "reason": "Schedule adapter test",
            "status": "proposed",
        })
        strategy = payload["strategies"]["intervention"]
        del strategy["transition_matrix"]
        strategy["transition_schedule"] = [
            {"start_cycle": 1, "matrix": [[0.9, 0.1], [0.0, 1.0]]},
            {"start_cycle": 2, "matrix": [[0.8, 0.2], [0.0, 1.0]]},
        ]
        mapping = payload["input_provenance"][1]
        mapping["path"] = "strategies.intervention.transition_schedule"
        mapping["assumption_ids"].append("later-intervention-rate")
        mapping["derivation"]["model_value"] = copy.deepcopy(
            strategy["transition_schedule"]
        )
        mapping["derivation"]["transformation"]["phases"].append({
            "start_cycle": 2,
            "rows": [
                {
                    "self_index": 0,
                    "events": [{
                        "target_index": 1,
                        "rate_per_year": 0.22314355131420976,
                        "assumption_id": "later-intervention-rate",
                    }],
                },
                {"self_index": 1, "events": []},
            ],
        })

        result = run_markov(MarkovSpecification.from_dict(payload))

        self.assertEqual(result.intervention.transition_mode, "piecewise_by_model_cycle")
        self.assertEqual(result.intervention.transition_schedule_start_cycles, (1, 2))
        self.assertAlmostEqual(result.intervention.total_qaly, 2.62)

    def test_parametric_survival_schedule_matches_hand_calculation(self) -> None:
        payload = survival_derived_payload()
        result = run_markov(MarkovSpecification.from_dict(payload))

        self.assertEqual(result.engine_version, "0.7.0")
        self.assertEqual(result.schema_version, "0.6.0")
        self.assertEqual(
            result.intervention.transition_schedule_start_cycles,
            (1, 2, 3),
        )
        self.assertAlmostEqual(result.comparator.total_qaly, 1.0 + 0.8 + 0.64)
        expected_qaly = 1.0 + exp(-((1.0 / 4.0) ** 2.0)) + exp(-((2.0 / 4.0) ** 2.0))
        self.assertAlmostEqual(result.intervention.total_qaly, expected_qaly)
        self.assertAlmostEqual(result.intervention.total_cost, expected_qaly * 100.0)
        for cycle, occupancy in enumerate(result.intervention.occupancy):
            self.assertAlmostEqual(occupancy[0], exp(-((cycle / 4.0) ** 2.0)))
            self.assertAlmostEqual(sum(occupancy), 1.0)

    def test_survival_adapter_uses_cumulative_hazard_differences(self) -> None:
        schedule, extraction_ids, assumption_ids = derive_survival_schedule(
            {
                "operation": "parametric_survival_to_transition_schedule",
                "cycle_length_years": 0.5,
                "from_state_index": 0,
                "event_state_index": 1,
                "distribution": "weibull",
                "parameters": {
                    "shape": {"value": 2.0, "assumption_id": "shape"},
                    "scale_years": {"value": 2.0, "assumption_id": "scale"},
                },
            },
            state_count=2,
            cycles=2,
            cycle_length_years=0.5,
        )

        self.assertEqual(extraction_ids, set())
        self.assertEqual(assumption_ids, {"shape", "scale"})
        self.assertAlmostEqual(schedule[0]["matrix"][0][1], 1.0 - exp(-0.0625))
        self.assertAlmostEqual(schedule[1]["matrix"][0][1], 1.0 - exp(-0.1875))
        self.assertEqual(schedule[1]["matrix"][1], [0.0, 1.0])

    def test_single_event_probability_time_conversion_matches_hand_calculation(self) -> None:
        payload = probability_time_payload()
        result = run_markov(MarkovSpecification.from_dict(payload))

        converted = 1.0 - (1.0 - 0.36) ** 0.5
        self.assertEqual(result.engine_version, "0.7.0")
        self.assertEqual(result.schema_version, "0.7.0")
        self.assertAlmostEqual(
            payload["strategies"]["intervention"]["transition_matrix"][0][1],
            converted,
        )
        self.assertAlmostEqual(result.intervention.occupancy[1][0], 1.0 - converted)

        output, extraction_ids, assumption_ids = derive_probability_time(
            payload["input_provenance"][1]["derivation"]["transformation"],
            target_path="strategies.intervention.transition_matrix",
            state_count=2,
            cycles=3,
            cycle_length_years=1.0,
        )
        self.assertAlmostEqual(output[0][1], converted)
        self.assertEqual(extraction_ids, set())
        self.assertEqual(
            assumption_ids, {"intervention-two-year-event-probability"}
        )

    def test_probability_time_conversion_fails_closed_outside_contract(self) -> None:
        valid = probability_time_payload()
        cases: list[tuple[dict, str]] = []

        stale = copy.deepcopy(valid)
        stale["strategies"]["intervention"]["transition_matrix"][0] = [0.7, 0.3]
        stale["input_provenance"][1]["derivation"]["model_value"] = copy.deepcopy(
            stale["strategies"]["intervention"]["transition_matrix"]
        )
        cases.append((stale, "do not reproduce"))

        wrong_schema = copy.deepcopy(valid)
        wrong_schema["schema_version"] = "0.6.0"
        cases.append((wrong_schema, "require schema_version 0.7.0"))

        certain = copy.deepcopy(valid)
        certain["input_provenance"][1]["derivation"]["transformation"]["phases"][0]["rows"][0]["event"]["source_probability"] = 1.0
        cases.append((certain, "strictly between 0 and 1"))

        for payload, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                ModelValidationError, message
            ):
                MarkovSpecification.from_dict(payload)

        transformation = copy.deepcopy(
            valid["input_provenance"][1]["derivation"]["transformation"]
        )
        transformation["phases"][0]["rows"][0]["events"] = []
        with self.assertRaisesRegex(ProbabilityTimeError, "fields must be exactly"):
            derive_probability_time(
                transformation,
                target_path="strategies.intervention.transition_matrix",
                state_count=2,
                cycles=3,
                cycle_length_years=1.0,
            )

    def test_survival_derivation_fails_closed_outside_the_bounded_contract(self) -> None:
        valid = survival_derived_payload()
        cases: list[tuple[dict, str]] = []

        stale = copy.deepcopy(valid)
        stale["strategies"]["intervention"]["transition_schedule"][0]["matrix"][0] = [0.5, 0.5]
        stale["input_provenance"][1]["derivation"]["model_value"] = copy.deepcopy(
            stale["strategies"]["intervention"]["transition_schedule"]
        )
        cases.append((stale, "does not reproduce"))

        legacy = copy.deepcopy(valid)
        legacy["schema_version"] = "0.5.0"
        cases.append((legacy, "require schema_version 0.6.0"))

        unsupported = copy.deepcopy(valid)
        unsupported["input_provenance"][1]["derivation"]["transformation"]["distribution"] = "lognormal"
        cases.append((unsupported, "must be exponential or weibull"))

        missing_basis = copy.deepcopy(valid)
        parameter = missing_basis["input_provenance"][1]["derivation"]["transformation"]["parameters"]["shape"]
        del parameter["assumption_id"]
        cases.append((missing_basis, "exactly one source_extraction_id or assumption_id"))

        for payload, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                ModelValidationError,
                message,
            ):
                MarkovSpecification.from_dict(payload)

        transformation = valid["input_provenance"][1]["derivation"][
            "transformation"
        ]
        with self.assertRaisesRegex(SurvivalCurveError, "requires exactly two states"):
            derive_survival_schedule(
                transformation,
                state_count=3,
                cycles=valid["cycles"],
                cycle_length_years=valid["cycle_length_years"],
            )

    def test_strategy_cannot_mix_static_and_scheduled_transitions(self) -> None:
        payload = time_varying_payload()
        payload["strategies"]["intervention"]["transition_matrix"] = [
            [0.95, 0.05],
            [0.0, 1.0],
        ]

        with self.assertRaisesRegex(ModelValidationError, "exactly one"):
            MarkovSpecification.from_dict(payload)

    def test_transition_schedule_must_start_at_cycle_one_and_be_ordered(self) -> None:
        payload = time_varying_payload()
        payload["strategies"]["intervention"]["transition_schedule"][0][
            "start_cycle"
        ] = 2

        with self.assertRaisesRegex(ModelValidationError, "start at cycle 1"):
            MarkovSpecification.from_dict(payload)

        payload = time_varying_payload()
        payload["strategies"]["intervention"]["transition_schedule"][2][
            "start_cycle"
        ] = 2
        with self.assertRaisesRegex(ModelValidationError, "unique and strictly increasing"):
            MarkovSpecification.from_dict(payload)

    def test_analysis_input_cannot_self_authorize(self) -> None:
        payload = golden_payload()
        payload["approvals"] = [
            {
                "gate": "analysis_plan",
                "approved_by": "human-reviewer",
                "approved_at": "2026-07-14T12:00:00+08:00",
                "artifact_sha256": "a" * 64,
            }
        ]

        with self.assertRaisesRegex(ModelValidationError, "app-owned"):
            MarkovSpecification.from_dict(payload)

    def test_draft_reference_case_is_explicitly_warned(self) -> None:
        payload = golden_payload()
        payload["reference_case"] = {"id": "CN-2026-draft", "status": "draft"}
        specification = MarkovSpecification.from_dict(payload)

        exploratory = run_markov(specification)
        self.assertEqual(exploratory.calculation_classification, "calculation_only")
        self.assertIn("Draft reference case", " ".join(exploratory.warnings))

    def test_half_cycle_correction_must_be_a_real_boolean(self) -> None:
        payload = golden_payload()
        payload["half_cycle_correction"] = "false"

        with self.assertRaisesRegex(ModelValidationError, "must be a boolean"):
            MarkovSpecification.from_dict(payload)

    def test_dominant_intervention_is_not_reported_with_a_misleading_icer(self) -> None:
        payload = golden_payload()
        payload["cycles"] = 1
        payload["discount_rates"] = {"costs": 0.0, "outcomes": 0.0}
        payload["strategies"]["intervention"]["state_costs"] = [
            500.0,
            2000.0,
            0.0,
        ]
        specification = MarkovSpecification.from_dict(payload)

        result = run_markov(specification)

        self.assertEqual(result.incremental.interpretation, "dominant")
        self.assertIsNone(result.incremental.icer)

    def test_input_payload_is_not_mutated(self) -> None:
        payload = golden_payload()
        original = copy.deepcopy(payload)

        run_markov(MarkovSpecification.from_dict(payload))

        self.assertEqual(payload, original)


class UncertaintyAnalysisTests(unittest.TestCase):
    def run_golden(self) -> dict:
        return run_uncertainty(
            golden_payload(),
            GOLDEN_PATH.read_bytes(),
            uncertainty_payload(),
            UNCERTAINTY_PATH.read_bytes(),
        )

    def test_versioned_prng_has_a_stable_known_sequence(self) -> None:
        rng = Pcg32(42)

        self.assertEqual(
            [rng.next_u32() for _ in range(5)],
            [2707161783, 2068313097, 3122475824, 2211639955, 3215226955],
        )

    def test_multi_strategy_psa_competes_all_strategies_and_reports_evpi(self) -> None:
        base = multi_strategy_payload()
        base_raw = json.dumps(base, separators=(",", ":"), sort_keys=True).encode()
        uncertainty = multi_strategy_uncertainty_payload(base, base_raw)
        uncertainty_raw = json.dumps(
            uncertainty, separators=(",", ":"), sort_keys=True
        ).encode()

        result = run_uncertainty(base, base_raw, uncertainty, uncertainty_raw)

        self.assertEqual(result["engine_version"], "0.8.0")
        self.assertEqual(result["schema_version"], "0.7.0")
        self.assertEqual(
            result["base_case"]["strategy_order"], base["strategy_order"]
        )
        psa = result["probabilistic_analysis"]
        self.assertEqual(psa["strategy_order"], base["strategy_order"])
        self.assertEqual(len(psa["samples"]), 1000)
        self.assertNotIn("cost_effective_probability", psa)
        primary_probabilities = psa[
            "primary_threshold_strategy_optimal_probabilities"
        ]
        self.assertAlmostEqual(
            sum(primary_probabilities.values())
            + psa["primary_threshold_tie_probability"],
            1.0,
        )
        decision = psa["decision_uncertainty"]
        self.assertEqual(
            decision["tie_handling"],
            "ties_reported_separately_without_fractional_allocation",
        )
        samples = psa["samples"]
        for row in decision["threshold_results"]:
            self.assertAlmostEqual(
                sum(row["strategy_optimal_probabilities"].values())
                + row["tie_probability"],
                1.0,
            )
            expected_by_strategy = []
            maxima = []
            for sample in samples:
                values = [
                    row["threshold"] * qaly - cost
                    for cost, qaly in zip(
                        sample["strategy_costs"], sample["strategy_qalys"]
                    )
                ]
                maxima.append(max(values))
                if not expected_by_strategy:
                    expected_by_strategy = [[] for _ in values]
                for index, value in enumerate(values):
                    expected_by_strategy[index].append(value)
            means = [sum(values) / len(values) for values in expected_by_strategy]
            expected_evpi = sum(maxima) / len(maxima) - max(means)
            self.assertAlmostEqual(row["per_person_evpi"], expected_evpi)
            self.assertGreaterEqual(row["per_person_evpi"], -1e-12)
        self.assertIn(
            "net_monetary_benefit_span_by_strategy",
            result["deterministic_analysis"][0],
        )
        self.assertIn(
            "fully_incremental_analysis",
            result["structural_scenarios"][0]["result"],
        )

    def test_multi_strategy_uncertainty_versions_fail_closed(self) -> None:
        base = multi_strategy_payload()
        base_raw = json.dumps(base, sort_keys=True).encode()
        uncertainty = multi_strategy_uncertainty_payload(base, base_raw)
        uncertainty["schema_version"] = "0.6.0"
        with self.assertRaisesRegex(ModelValidationError, "requires uncertainty"):
            run_uncertainty(
                base,
                base_raw,
                uncertainty,
                json.dumps(uncertainty, sort_keys=True).encode(),
            )

    def test_legacy_uncertainty_rejects_an_ignored_strategy_target(self) -> None:
        base = golden_payload()
        base["strategies"]["ignored"] = copy.deepcopy(
            base["strategies"]["intervention"]
        )
        base["strategies"]["ignored"]["name"] = "ignored"
        base_raw = json.dumps(base, separators=(",", ":"), sort_keys=True).encode()
        uncertainty = uncertainty_payload()
        uncertainty["base_analysis"]["content_sha256"] = hashlib.sha256(
            base_raw
        ).hexdigest()
        uncertainty["parameters"][0]["target"] = (
            "/strategies/ignored/state_costs/0"
        )
        uncertainty["parameters"][0]["provenance_path"] = (
            "strategies.ignored.state_costs"
        )

        with self.assertRaisesRegex(ModelValidationError, "outside the allowlist"):
            run_uncertainty(
                base,
                base_raw,
                uncertainty,
                json.dumps(
                    uncertainty, separators=(",", ":"), sort_keys=True
                ).encode(),
            )

    def test_multi_strategy_evpi_uses_exact_expected_nmb_maximum(self) -> None:
        samples = [
            {
                "strategy_costs": [0.0, 0.0],
                "strategy_qalys": [1e12, 1e12 + 0.5],
            }
            for _ in range(1_000)
        ]
        specification = SimpleNamespace(
            decision_thresholds=(1.0,),
            primary_threshold=1.0,
            threshold_source="adversarial_test",
            threshold_rationale="Separates display ties from the EVPI maximizer.",
        )

        decision = _multi_strategy_decision_uncertainty(
            samples, ("first", "second"), specification
        )
        row = decision["threshold_results"][0]

        self.assertEqual(
            row["expected_net_benefit_tied_strategy_ids"], ["first", "second"]
        )
        self.assertIsNone(row["strategy_with_highest_expected_net_benefit"])
        self.assertIsNone(row["ceaf_probability"])
        self.assertEqual(row["per_person_evpi"], 0.0)
        self.assertEqual(row["per_person_evpi_mcse"], 0.0)

    def test_two_strategy_psa_reports_exact_ties_separately(self) -> None:
        base = golden_payload()
        base["strategies"]["intervention"] = copy.deepcopy(
            base["strategies"]["comparator"]
        )
        base["strategies"]["intervention"]["name"] = "identical_intervention"
        specification = SimpleNamespace(
            seed=42,
            iterations=4,
            checkpoints=(2, 4),
            max_probability_mcse=1.0,
            max_probability_drift=1.0,
            parameters=(),
            correlation_groups=(),
            independence_rationale="No sampled parameters in the exact-tie fixture.",
            omitted_parameters=(),
            decision_thresholds=(base["willingness_to_pay"],),
            primary_threshold=base["willingness_to_pay"],
            threshold_source="fixed_case",
            threshold_rationale="Exact equality must be reported as a tie.",
        )

        result = _run_psa(base, specification)

        self.assertEqual(result["cost_effective_probability"], 0.0)
        self.assertEqual(
            [
                checkpoint["cost_effective_probability"]
                for checkpoint in result["convergence"]["checkpoints"]
            ],
            [0.0, 0.0],
        )
        decision = result["decision_uncertainty"]["threshold_results"][0]
        self.assertEqual(decision["intervention_optimal_probability"], 0.0)
        self.assertEqual(decision["comparator_optimal_probability"], 0.0)
        self.assertEqual(decision["tie_probability"], 1.0)

    def test_golden_uncertainty_run_is_reproducible(self) -> None:
        first = self.run_golden()
        second = self.run_golden()

        self.assertEqual(first, second)
        self.assertEqual(first["prng"], {"algorithm": "pcg32-xsh-rr", "version": "1"})
        self.assertEqual(first["seed"], "20260714")
        self.assertEqual(first["economic_basis"], {"currency": "CNY", "price_year": 2026})
        self.assertEqual(first["probabilistic_analysis"]["iterations"], 1000)
        self.assertEqual(len(first["probabilistic_analysis"]["samples"]), 1000)
        self.assertEqual(
            first["probabilistic_analysis"]["cost_effective_probability"],
            0.974,
        )
        self.assertAlmostEqual(
            first["probabilistic_analysis"]["mean_incremental_net_monetary_benefit"],
            13346.646129556426,
        )
        self.assertEqual(len(first["deterministic_analysis"]), 2)
        self.assertEqual(len(first["structural_scenarios"]), 1)

        decision = first["probabilistic_analysis"]["decision_uncertainty"]
        self.assertEqual(decision["primary_threshold"], 100000.0)
        self.assertEqual(
            [row["threshold"] for row in decision["threshold_results"]],
            [0.0, 50000.0, 100000.0, 150000.0, 200000.0],
        )
        samples = first["probabilistic_analysis"]["samples"]
        for row in decision["threshold_results"]:
            incremental_nmb = [
                row["threshold"] * sample["delta_qaly"] - sample["delta_cost"]
                for sample in samples
            ]
            expected_mean = sum(incremental_nmb) / len(incremental_nmb)
            expected_evpi = (
                sum(max(0.0, value) for value in incremental_nmb)
                / len(incremental_nmb)
                - max(0.0, expected_mean)
            )
            self.assertAlmostEqual(row["expected_incremental_net_monetary_benefit"], expected_mean)
            self.assertAlmostEqual(row["per_person_evpi"], expected_evpi)
            self.assertGreaterEqual(row["per_person_evpi"], 0.0)
            self.assertAlmostEqual(
                row["intervention_optimal_probability"]
                + row["comparator_optimal_probability"]
                + row["tie_probability"],
                1.0,
            )

    def test_legacy_uncertainty_plan_retains_single_threshold_output(self) -> None:
        uncertainty = uncertainty_payload()
        uncertainty["schema_version"] = "0.1.0"
        del uncertainty["probabilistic_analysis"]["decision_thresholds"]

        result = run_uncertainty(
            golden_payload(),
            GOLDEN_PATH.read_bytes(),
            uncertainty,
            json.dumps(uncertainty).encode(),
        )

        decision = result["probabilistic_analysis"]["decision_uncertainty"]
        self.assertEqual(decision["threshold_source"], "legacy_primary_only")
        self.assertEqual(len(decision["threshold_results"]), 1)
        self.assertEqual(decision["threshold_results"][0]["threshold"], 100000.0)

    def test_time_varying_transition_row_supports_dsa_and_psa(self) -> None:
        base = time_varying_payload()
        base_raw = json.dumps(base, separators=(",", ":")).encode()
        uncertainty = uncertainty_payload()
        uncertainty["analysis_id"] = base["analysis_id"]
        uncertainty["base_analysis"]["content_sha256"] = hashlib.sha256(
            base_raw
        ).hexdigest()
        uncertainty["probabilistic_analysis"]["decision_thresholds"]["values"] = [
            0.0,
            5000.0,
            10000.0,
            15000.0,
            20000.0,
        ]
        cost_parameter = uncertainty["parameters"][0]
        cost_parameter["deterministic"]["low"] = 50.0
        cost_parameter["deterministic"]["high"] = 150.0
        cost_parameter["probabilistic"]["shape"] = 100.0
        cost_parameter["probabilistic"]["scale"] = 1.0
        transition_parameter = uncertainty["parameters"][1]
        transition_parameter["target"] = (
            "/strategies/intervention/transition_schedule/0/matrix/0"
        )
        transition_parameter["provenance_path"] = (
            "strategies.intervention.transition_schedule"
        )
        transition_parameter["deterministic"]["low"] = [0.9, 0.1]
        transition_parameter["deterministic"]["high"] = [0.99, 0.01]
        transition_parameter["probabilistic"]["alpha"] = [95.0, 5.0]
        uncertainty["structural_scenarios"][0]["replacements"] = [{
            "target": "/strategies/intervention/transition_schedule/2/start_cycle",
            "value": 4,
        }]

        result = run_uncertainty(
            base,
            base_raw,
            uncertainty,
            json.dumps(uncertainty, separators=(",", ":")).encode(),
        )

        self.assertEqual(result["engine_version"], "0.7.0")
        self.assertEqual(
            result["deterministic_analysis"][1]["target"],
            "/strategies/intervention/transition_schedule/0/matrix/0",
        )
        self.assertEqual(len(result["probabilistic_analysis"]["samples"]), 1000)
        self.assertEqual(
            result["structural_scenarios"][0]["replacements"][0]["target"],
            "/strategies/intervention/transition_schedule/2/start_cycle",
        )

    def test_event_rate_supports_dsa_and_seeded_psa_via_complete_recomputation(self) -> None:
        base = rate_derived_payload()
        uncertainty = rate_uncertainty_payload()

        first = run_uncertainty(
            base,
            RATE_DERIVED_PATH.read_bytes(),
            uncertainty,
            json.dumps(uncertainty, separators=(",", ":")).encode(),
        )
        second = run_uncertainty(
            base,
            RATE_DERIVED_PATH.read_bytes(),
            uncertainty,
            json.dumps(uncertainty, separators=(",", ":")).encode(),
        )

        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], "0.3.0")
        self.assertEqual(first["engine_version"], "0.7.0")
        self.assertEqual(len(first["probabilistic_analysis"]["samples"]), 1000)
        dsa = first["deterministic_analysis"][0]
        for bound, rate in (("low", 0.05), ("high", 0.2)):
            expected_plan = copy.deepcopy(base)
            probability = 1.0 - exp(-rate)
            expected_matrix = [[1.0 - probability, probability], [0.0, 1.0]]
            expected_plan["strategies"]["intervention"]["transition_matrix"] = expected_matrix
            expected_plan["input_provenance"][1]["derivation"]["transformation"]["phases"][0]["rows"][0]["events"][0]["rate_per_year"] = rate
            expected_plan["input_provenance"][1]["derivation"]["model_value"] = expected_matrix
            expected = run_markov(MarkovSpecification.from_dict(expected_plan)).incremental
            self.assertAlmostEqual(
                dsa[f"{bound}_result"]["incremental_net_monetary_benefit"],
                expected.incremental_net_monetary_benefit,
            )

    def test_survival_parameters_support_dsa_and_seeded_psa_via_complete_recomputation(self) -> None:
        base = survival_derived_payload()
        base_raw = json.dumps(base, separators=(",", ":")).encode()
        uncertainty = survival_uncertainty_payload(base, base_raw)

        first = run_uncertainty(
            base,
            base_raw,
            uncertainty,
            json.dumps(uncertainty, separators=(",", ":")).encode(),
        )
        second = run_uncertainty(
            base,
            base_raw,
            uncertainty,
            json.dumps(uncertainty, separators=(",", ":")).encode(),
        )

        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], "0.5.0")
        self.assertEqual(first["engine_version"], "0.7.0")
        self.assertEqual(len(first["deterministic_analysis"]), 3)
        self.assertEqual(len(first["probabilistic_analysis"]["samples"]), 1000)

        specification = UncertaintySpecification.from_dict(
            uncertainty, base, hashlib.sha256(base_raw).hexdigest()
        )
        shape = next(
            parameter
            for parameter in specification.parameters
            if parameter.identifier == "intervention-weibull-shape"
        )
        scale = next(
            parameter
            for parameter in specification.parameters
            if parameter.identifier == "intervention-weibull-scale"
        )
        recomputed = _apply_parameter_values(base, ((shape, 1.5), (scale, 3.0)))
        schedule = recomputed["strategies"]["intervention"]["transition_schedule"]
        transformation = recomputed["input_provenance"][1]["derivation"]
        expected, _, _ = derive_survival_schedule(
            transformation["transformation"],
            state_count=2,
            cycles=base["cycles"],
            cycle_length_years=base["cycle_length_years"],
        )
        self.assertEqual(schedule, expected)
        self.assertEqual(transformation["model_value"], expected)

    def test_survival_parameter_uncertainty_fails_closed_outside_its_bounded_contract(self) -> None:
        base = survival_derived_payload()
        base_raw = json.dumps(base, separators=(",", ":")).encode()
        cases = []
        legacy = survival_uncertainty_payload(base, base_raw)
        legacy["schema_version"] = "0.4.0"
        cases.append((legacy, "schema_version 0.5.0"))
        wrong_basis = survival_uncertainty_payload(base, base_raw)
        wrong_basis["parameters"][1]["probabilistic"]["basis_ids"] = ["unlinked"]
        cases.append((wrong_basis, "exactly the parameter source"))
        beta = survival_uncertainty_payload(base, base_raw)
        beta["parameters"][1]["probabilistic"] = {
            "type": "beta",
            "alpha": 2.0,
            "beta": 8.0,
            "basis_ids": ["intervention-weibull-shape"],
            "rationale": "Deliberately invalid positive-parameter distribution",
        }
        cases.append((beta, "must use gamma, lognormal, or positive uniform"))
        nonpositive = survival_uncertainty_payload(base, base_raw)
        nonpositive["parameters"][2]["deterministic"]["low"] = 0.0
        cases.append((nonpositive, "must be positive"))
        wrong_parameter = survival_uncertainty_payload(base, base_raw)
        wrong_parameter["parameters"][1]["target"] = (
            "/input_provenance/0/derivation/transformation/parameters/shape/value"
        )
        cases.append((wrong_parameter, "does not exist"))

        for uncertainty, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                ModelValidationError, message
            ):
                run_uncertainty(
                    base,
                    base_raw,
                    uncertainty,
                    json.dumps(uncertainty).encode(),
                )

    def test_probability_time_uncertainty_recomputes_complete_matrix(self) -> None:
        base = probability_time_payload()
        base_raw = json.dumps(base, separators=(",", ":")).encode()
        uncertainty = probability_uncertainty_payload(base, base_raw)

        first = run_uncertainty(
            base,
            base_raw,
            uncertainty,
            json.dumps(uncertainty, separators=(",", ":")).encode(),
        )
        second = run_uncertainty(
            base,
            base_raw,
            uncertainty,
            json.dumps(uncertainty, separators=(",", ":")).encode(),
        )

        self.assertEqual(first, second)
        self.assertEqual(first["schema_version"], "0.6.0")
        self.assertEqual(first["engine_version"], "0.7.0")
        specification = UncertaintySpecification.from_dict(
            uncertainty, base, hashlib.sha256(base_raw).hexdigest()
        )
        parameter = specification.parameters[0]
        recomputed = _apply_parameter_values(base, ((parameter, 0.49),))
        expected = 1.0 - (1.0 - 0.49) ** 0.5
        matrix = recomputed["strategies"]["intervention"]["transition_matrix"]
        self.assertAlmostEqual(matrix[0][1], expected)
        self.assertEqual(
            recomputed["input_provenance"][1]["derivation"]["model_value"],
            matrix,
        )

    def test_probability_time_uncertainty_rejects_invalid_distribution_and_basis(self) -> None:
        base = probability_time_payload()
        base_raw = json.dumps(base, separators=(",", ":")).encode()
        cases = []

        legacy = probability_uncertainty_payload(base, base_raw)
        legacy["schema_version"] = "0.5.0"
        cases.append((legacy, "schema_version 0.6.0"))

        gamma = probability_uncertainty_payload(base, base_raw)
        gamma["parameters"][0]["probabilistic"] = {
            "type": "gamma",
            "shape": 4.0,
            "scale": 0.09,
            "basis_ids": ["intervention-two-year-event-probability"],
            "rationale": "Deliberately invalid unbounded probability distribution.",
        }
        cases.append((gamma, "must use beta or bounded uniform"))

        wrong_basis = probability_uncertainty_payload(base, base_raw)
        wrong_basis["parameters"][0]["probabilistic"]["basis_ids"] = ["unlinked"]
        cases.append((wrong_basis, "exactly the event source"))

        invalid_bound = probability_uncertainty_payload(base, base_raw)
        invalid_bound["parameters"][0]["deterministic"]["high"] = 1.0
        cases.append((invalid_bound, "strictly between 0 and 1"))

        for uncertainty, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                ModelValidationError, message
            ):
                run_uncertainty(
                    base,
                    base_raw,
                    uncertainty,
                    json.dumps(uncertainty).encode(),
                )

    def test_event_rate_uncertainty_fails_closed_outside_its_bounded_contract(self) -> None:
        base = rate_derived_payload()
        cases = []
        legacy = rate_uncertainty_payload()
        legacy["schema_version"] = "0.2.0"
        cases.append((legacy, "schema_version 0.3.0"))
        wrong_basis = rate_uncertainty_payload()
        wrong_basis["parameters"][0]["probabilistic"]["basis_ids"] = ["unlinked"]
        cases.append((wrong_basis, "exactly the event source"))
        beta = rate_uncertainty_payload()
        beta["parameters"][0]["probabilistic"] = {
            "type": "beta",
            "alpha": 2.0,
            "beta": 8.0,
            "basis_ids": ["intervention-mortality-rate"],
            "rationale": "Deliberately invalid rate distribution",
        }
        cases.append((beta, "must use gamma, lognormal, or positive uniform"))
        nonpositive = rate_uncertainty_payload()
        nonpositive["parameters"][0]["deterministic"]["low"] = 0.0
        cases.append((nonpositive, "must be positive"))
        derived_row = rate_uncertainty_payload()
        parameter = derived_row["parameters"][0]
        parameter["target"] = "/strategies/intervention/transition_matrix/0"
        parameter["deterministic"]["low"] = [0.85, 0.15]
        parameter["deterministic"]["high"] = [0.95, 0.05]
        parameter["probabilistic"] = {
            "type": "dirichlet",
            "alpha": [9.0, 1.0],
            "basis_ids": ["intervention-mortality-rate"],
            "rationale": "Deliberately targets a derived row",
        }
        cases.append((derived_row, "vary an admitted event rate"))

        for uncertainty, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                ModelValidationError, message
            ):
                run_uncertainty(
                    base,
                    RATE_DERIVED_PATH.read_bytes(),
                    uncertainty,
                    json.dumps(uncertainty).encode(),
                )

    def test_multiple_competing_rates_are_applied_before_one_complete_row_recomputation(self) -> None:
        base = golden_payload()
        base["schema_version"] = "0.5.0"
        base["analysis_id"] = "competing-rate-uncertainty"
        rates = [0.1673576634856573, 0.05578588782855244, 0.2876820724517809]
        basis_ids = ["progression-rate", "stable-death-rate", "progressed-death-rate"]
        joint_basis_id = "joint-stable-event-rate-estimate"
        base["assumptions"] = [
            {
                "id": identifier,
                "statement": f"Use constant {identifier} in this bounded fixture.",
                "reason": "Competing-rate uncertainty regression test.",
                "status": "proposed",
            }
            for identifier in basis_ids
        ]
        base["assumptions"].append({
            "id": joint_basis_id,
            "statement": "Use the reported joint log-rate estimate for stable-state events.",
            "reason": "Correlated competing-rate uncertainty regression test.",
            "status": "proposed",
        })
        base["input_provenance"] = [{
            "path": "strategies.intervention.transition_matrix",
            "source_ids": [],
            "extraction_ids": [],
            "assumption_ids": [*basis_ids, joint_basis_id],
            "derivation": {
                "method": "deterministic_transformation",
                "model_value": copy.deepcopy(base["strategies"]["intervention"]["transition_matrix"]),
                "transformation": {
                    "operation": "constant_competing_rates",
                    "cycle_length_years": 1.0,
                    "phases": [{
                        "start_cycle": 1,
                        "rows": [{
                            "self_index": 0,
                            "events": [
                                {"target_index": 1, "rate_per_year": rates[0], "assumption_id": joint_basis_id},
                                {"target_index": 2, "rate_per_year": rates[1], "assumption_id": joint_basis_id},
                            ],
                        }, {
                            "self_index": 1,
                            "events": [{"target_index": 2, "rate_per_year": rates[2], "assumption_id": basis_ids[2]}],
                        }, {"self_index": 2, "events": []}],
                    }],
                },
            },
        }]
        base_raw = json.dumps(base, separators=(",", ":")).encode()
        uncertainty = uncertainty_payload()
        uncertainty["schema_version"] = "0.4.0"
        uncertainty["analysis_id"] = base["analysis_id"]
        uncertainty["base_analysis"]["content_sha256"] = hashlib.sha256(base_raw).hexdigest()
        target_prefix = "/input_provenance/0/derivation/transformation/phases/0/rows/0/events"
        uncertainty["parameters"] = [
            {
                "id": basis_ids[index],
                "label": basis_ids[index],
                "target": f"{target_prefix}/{index}/rate_per_year",
                "provenance_path": "strategies.intervention.transition_matrix",
                "deterministic": {
                    "low": low,
                    "high": high,
                    "rationale": "Bounded positive range",
                },
                "probabilistic": {
                    "type": "lognormal",
                    "mu_log": log(rates[index]),
                    "sigma_log": 0.2,
                    "basis_ids": [joint_basis_id],
                    "rationale": "Joint positive log-rate estimate",
                },
            }
            for index, (low, high) in enumerate(((0.1, 0.3), (0.02, 0.1)))
        ]
        uncertainty["probabilistic_analysis"]["correlation_handling"]["groups"] = [{
            "id": "joint-stable-event-rates",
            "parameter_ids": basis_ids[:2],
            "scale": "log_standard_normal",
            "method": "cholesky",
            "correlation_matrix": [[1.0, 0.4], [0.4, 1.0]],
            "basis_ids": [joint_basis_id],
            "rationale": "The bounded fixture supplies a joint log-rate estimate.",
        }]
        specification = UncertaintySpecification.from_dict(
            uncertainty, base, hashlib.sha256(base_raw).hexdigest()
        )

        changed = _apply_parameter_values(
            base,
            ((specification.parameters[0], 0.1), (specification.parameters[1], 0.2)),
        )

        event_mass = 1.0 - exp(-0.3)
        row = changed["strategies"]["intervention"]["transition_matrix"][0]
        self.assertAlmostEqual(row[0], exp(-0.3))
        self.assertAlmostEqual(row[1], event_mass / 3.0)
        self.assertAlmostEqual(row[2], event_mass * 2.0 / 3.0)
        self.assertEqual(
            changed["input_provenance"][0]["derivation"]["model_value"],
            changed["strategies"]["intervention"]["transition_matrix"],
        )

    def test_correlation_matrix_rejects_perfect_and_non_positive_definite_inputs(self) -> None:
        with self.assertRaisesRegex(
            ModelValidationError,
            "off-diagonal correlations must be strictly between",
        ):
            _correlation_matrix([[1.0, 1.0], [1.0, 1.0]], 2, "matrix")

        matrix = _correlation_matrix(
            [[1.0, 0.9, 0.9], [0.9, 1.0, -0.9], [0.9, -0.9, 1.0]],
            3,
            "matrix",
        )
        with self.assertRaisesRegex(ModelValidationError, "strictly positive definite"):
            _cholesky(matrix, "matrix")

    def test_legacy_uncertainty_plan_rejects_a_silently_ignored_grid(self) -> None:
        uncertainty = uncertainty_payload()
        uncertainty["schema_version"] = "0.1.0"
        with self.assertRaisesRegex(ModelValidationError, "schema_version 0.2.0"):
            run_uncertainty(
                golden_payload(),
                GOLDEN_PATH.read_bytes(),
                uncertainty,
                json.dumps(uncertainty).encode(),
            )

    def test_decision_threshold_grid_must_be_increasing_and_include_primary(self) -> None:
        for values, message in (
            ([0.0, 100000.0, 100000.0], "strictly increasing"),
            ([0.0, 50000.0, 150000.0], "primary willingness_to_pay"),
        ):
            uncertainty = uncertainty_payload()
            uncertainty["probabilistic_analysis"]["decision_thresholds"]["values"] = values
            with self.subTest(values=values), self.assertRaisesRegex(
                ModelValidationError, message
            ):
                run_uncertainty(
                    golden_payload(),
                    GOLDEN_PATH.read_bytes(),
                    uncertainty,
                    json.dumps(uncertainty).encode(),
                )

    def test_changed_base_plan_hash_fails_closed(self) -> None:
        payload = golden_payload()
        payload["cycles"] = 4
        changed_raw = json.dumps(payload).encode()

        with self.assertRaisesRegex(ModelValidationError, "base_analysis hash"):
            run_uncertainty(
                payload,
                changed_raw,
                uncertainty_payload(),
                UNCERTAINTY_PATH.read_bytes(),
            )

    def test_known_omitted_correlation_blocks_review(self) -> None:
        uncertainty = uncertainty_payload()
        uncertainty["probabilistic_analysis"]["correlation_handling"][
            "known_omitted_correlations"
        ] = ["Treatment cost and adverse-event probability share a data source"]

        with self.assertRaisesRegex(ModelValidationError, "must be resolved"):
            run_uncertainty(
                golden_payload(),
                GOLDEN_PATH.read_bytes(),
                uncertainty,
                json.dumps(uncertainty).encode(),
            )

    def test_evidence_bound_lognormal_group_uses_declared_cholesky_correlation(self) -> None:
        base = golden_payload()
        uncertainty = uncertainty_payload()
        uncertainty["schema_version"] = "0.4.0"
        first = uncertainty["parameters"][0]
        first["probabilistic"] = {
            "type": "lognormal",
            "mu_log": log(4000.0),
            "sigma_log": 0.2,
            "basis_ids": ["golden-cost-source"],
            "rationale": "Joint log-scale estimate from one evidence source",
        }
        second = copy.deepcopy(first)
        second.update({
            "id": "intervention-progressed-cost",
            "label": "Intervention progressed-state cost",
            "target": "/strategies/intervention/state_costs/1",
        })
        second["deterministic"] = {
            "low": 2000.0,
            "high": 4000.0,
            "rationale": "Evidence interval for the second jointly estimated cost",
        }
        second["probabilistic"].update({"mu_log": log(3000.0), "sigma_log": 0.3})
        uncertainty["parameters"] = [first, second]
        uncertainty["probabilistic_analysis"]["correlation_handling"]["groups"] = [{
            "id": "joint-costs",
            "parameter_ids": [first["id"], second["id"]],
            "scale": "log_standard_normal",
            "method": "cholesky",
            "correlation_matrix": [[1.0, 0.6], [0.6, 1.0]],
            "basis_ids": ["golden-cost-source"],
            "rationale": "The source reports a joint log-scale covariance estimate.",
        }]
        specification = UncertaintySpecification.from_dict(
            uncertainty,
            base,
            hashlib.sha256(GOLDEN_PATH.read_bytes()).hexdigest(),
        )

        expected_rng = Pcg32(uncertainty["seed"])
        first_normal = expected_rng.normal()
        second_normal = expected_rng.normal()
        expected = (
            exp(log(4000.0) + 0.2 * first_normal),
            exp(log(3000.0) + 0.3 * (0.6 * first_normal + sqrt(1.0 - 0.6**2) * second_normal)),
        )
        sampled = _sample_parameter_values(Pcg32(uncertainty["seed"]), specification)
        self.assertAlmostEqual(sampled[0][1], expected[0])
        self.assertAlmostEqual(sampled[1][1], expected[1])

        result = run_uncertainty(
            base,
            GOLDEN_PATH.read_bytes(),
            uncertainty,
            json.dumps(uncertainty).encode(),
        )
        self.assertEqual(result["schema_version"], "0.4.0")
        self.assertEqual(result["engine_version"], "0.7.0")
        self.assertEqual(
            result["probabilistic_analysis"]["correlation_groups"][0]["parameter_ids"],
            [first["id"], second["id"]],
        )

    def test_correlation_groups_fail_closed_outside_the_bounded_contract(self) -> None:
        base = golden_payload()
        valid = uncertainty_payload()
        valid["schema_version"] = "0.4.0"
        first = valid["parameters"][0]
        first["probabilistic"] = {
            "type": "lognormal",
            "mu_log": log(4000.0),
            "sigma_log": 0.2,
            "basis_ids": ["golden-cost-source"],
            "rationale": "Joint log-scale estimate",
        }
        second = copy.deepcopy(first)
        second.update({
            "id": "intervention-progressed-cost",
            "label": "Intervention progressed-state cost",
            "target": "/strategies/intervention/state_costs/1",
        })
        second["deterministic"] = {
            "low": 2000.0,
            "high": 4000.0,
            "rationale": "Evidence interval",
        }
        second["probabilistic"]["mu_log"] = log(3000.0)
        valid["parameters"] = [first, second]
        valid["probabilistic_analysis"]["correlation_handling"]["groups"] = [{
            "id": "joint-costs",
            "parameter_ids": [first["id"], second["id"]],
            "scale": "log_standard_normal",
            "method": "cholesky",
            "correlation_matrix": [[1.0, 0.5], [0.5, 1.0]],
            "basis_ids": ["golden-cost-source"],
            "rationale": "Joint evidence estimate",
        }]
        cases: list[tuple[dict, str]] = []

        legacy = copy.deepcopy(valid)
        legacy["schema_version"] = "0.3.0"
        cases.append((legacy, "require uncertainty schema_version 0.4.0"))

        asymmetric = copy.deepcopy(valid)
        asymmetric["probabilistic_analysis"]["correlation_handling"]["groups"][0]["correlation_matrix"] = [[1.0, 0.5], [0.4, 1.0]]
        cases.append((asymmetric, "must be symmetric"))

        wrong_distribution = copy.deepcopy(valid)
        wrong_distribution["parameters"][1]["probabilistic"] = {
            "type": "gamma",
            "shape": 9.0,
            "scale": 333.3333333333,
            "basis_ids": ["golden-cost-source"],
            "rationale": "Deliberately unsupported group member",
        }
        cases.append((wrong_distribution, "supports only scalar lognormal"))

        unlinked_basis = copy.deepcopy(valid)
        unlinked_basis["probabilistic_analysis"]["correlation_handling"]["groups"][0]["basis_ids"] = ["not-linked"]
        cases.append((unlinked_basis, "must be linked"))

        reused = copy.deepcopy(valid)
        duplicate_group = copy.deepcopy(
            reused["probabilistic_analysis"]["correlation_handling"]["groups"][0]
        )
        duplicate_group["id"] = "duplicate-members"
        reused["probabilistic_analysis"]["correlation_handling"]["groups"].append(duplicate_group)
        cases.append((reused, "only one correlation group"))

        for payload, message in cases:
            with self.subTest(message=message), self.assertRaisesRegex(
                ModelValidationError,
                message,
            ):
                UncertaintySpecification.from_dict(
                    payload,
                    base,
                    hashlib.sha256(GOLDEN_PATH.read_bytes()).hexdigest(),
                )

    def test_parameter_cannot_change_an_authority_field(self) -> None:
        uncertainty = uncertainty_payload()
        uncertainty["parameters"][0]["target"] = "/reference_case/status"

        with self.assertRaisesRegex(ModelValidationError, "outside the allowlist"):
            run_uncertainty(
                golden_payload(),
                GOLDEN_PATH.read_bytes(),
                uncertainty,
                json.dumps(uncertainty).encode(),
            )

    def test_overflowing_distribution_fails_explicitly(self) -> None:
        uncertainty = uncertainty_payload()
        uncertainty["parameters"][0]["probabilistic"] = {
            "type": "lognormal",
            "mu_log": 1_000.0,
            "sigma_log": 1.0,
            "basis_ids": ["golden-cost-source"],
            "rationale": "Deliberate overflow regression fixture",
        }

        with self.assertRaisesRegex(ModelValidationError, "numerical overflow"):
            run_uncertainty(
                golden_payload(),
                GOLDEN_PATH.read_bytes(),
                uncertainty,
                json.dumps(uncertainty).encode(),
            )


class BudgetImpactAnalysisTests(unittest.TestCase):
    def run_golden(self) -> dict:
        return run_budget_impact(
            budget_base_payload(),
            BUDGET_BASE_PATH.read_bytes(),
            budget_impact_payload(),
            BUDGET_IMPACT_PATH.read_bytes(),
        )

    def test_golden_budget_impact_matches_hand_calculation(self) -> None:
        result = self.run_golden()

        self.assertEqual(
            result["base_case"]["annual_net_budget_impact"],
            [550000.0, 1120000.0, 1810000.0],
        )
        self.assertEqual(
            result["base_case"]["cumulative_net_budget_impact"], 3480000.0
        )
        self.assertEqual(result["one_way_sensitivity"][0]["cumulative_span"], 100000.0)
        self.assertEqual(
            result["alternative_scenarios"][0]["cumulative_net_budget_impact"],
            4305000.0,
        )
        self.assertEqual(result["discount_rate"], 0)

    def test_dynamic_cohort_budget_impact_matches_hand_calculation(self) -> None:
        plan = budget_base_payload()
        plan_raw = BUDGET_BASE_PATH.read_bytes()
        budget = dynamic_budget_impact_payload()
        budget_raw = json.dumps(budget, separators=(",", ":"), sort_keys=True).encode()

        result = run_budget_impact(plan, plan_raw, budget, budget_raw)

        self.assertEqual(result["schema_version"], "0.2.0")
        self.assertEqual(result["engine_version"], "0.3.0")
        self.assertEqual(result["base_case"]["model_type"], "dynamic_annual_cohort")
        for actual, expected in zip(
            result["base_case"]["annual_net_budget_impact"],
            [3900.0, 4985.3, 5823.8831],
            strict=True,
        ):
            self.assertAlmostEqual(actual, expected)
        self.assertAlmostEqual(
            result["base_case"]["cumulative_net_budget_impact"], 14709.1831
        )
        year_one = result["base_case"]["annual_results"][0]
        self.assertEqual(
            year_one["with_new_intervention_flow"]["incident_intervention_starts"],
            10.0,
        )
        self.assertEqual(
            year_one["with_new_intervention_flow"]["comparator_displacement_starts"],
            9.0,
        )
        self.assertAlmostEqual(
            year_one["with_new_intervention_flow"][
                "intervention_discontinuers_to_comparator"
            ],
            7.02,
        )

    def test_dynamic_capacity_prioritizes_incident_starts_and_preserves_unmet_demand(self) -> None:
        plan = budget_base_payload()
        budget = dynamic_budget_impact_payload()
        budget["market_scenarios"]["with_new_intervention"][
            "intervention_start_capacity_by_year"
        ][0] = 5.0
        budget["sensitivity_parameters"][0]["low"] = 90.0
        result = run_budget_impact(
            plan,
            BUDGET_BASE_PATH.read_bytes(),
            budget,
            json.dumps(budget, separators=(",", ":"), sort_keys=True).encode(),
        )

        flow = result["base_case"]["annual_results"][0][
            "with_new_intervention_flow"
        ]
        self.assertEqual(flow["incident_intervention_starts"], 5.0)
        self.assertEqual(flow["comparator_displacement_starts"], 0.0)
        self.assertEqual(flow["capacity_unmet_starts"], 14.5)

    def test_dynamic_without_access_cannot_contain_intervention_flow(self) -> None:
        plan = budget_base_payload()
        budget = dynamic_budget_impact_payload()
        budget["market_scenarios"]["without_new_intervention"][
            "incident_intervention_share_by_year"
        ][1] = 0.1

        with self.assertRaisesRegex(ModelValidationError, "must contain only zeroes"):
            run_budget_impact(
                plan,
                BUDGET_BASE_PATH.read_bytes(),
                budget,
                json.dumps(budget).encode(),
            )

    def test_dynamic_scenario_cannot_mutate_without_access_intervention_flow(self) -> None:
        plan = budget_base_payload()
        budget = dynamic_budget_impact_payload()
        budget["alternative_scenarios"][0]["overrides"][0] = {
            "target": "/market_scenarios/without_new_intervention/incident_intervention_share_by_year/0",
            "value": 0.1,
        }

        with self.assertRaisesRegex(ModelValidationError, "unsupported budget impact target"):
            run_budget_impact(
                plan,
                BUDGET_BASE_PATH.read_bytes(),
                budget,
                json.dumps(budget).encode(),
            )

    def test_dynamic_probability_target_fails_outside_unit_interval(self) -> None:
        plan = budget_base_payload()
        budget = dynamic_budget_impact_payload()
        budget["sensitivity_parameters"][0] = {
            "id": "mortality",
            "label": "Year one mortality",
            "target": "/annual_mortality_probability/0",
            "low": 0.05,
            "high": 1.1,
            "basis_ids": ["golden-synthetic"],
        }

        with self.assertRaisesRegex(ModelValidationError, "probability target"):
            run_budget_impact(
                plan,
                BUDGET_BASE_PATH.read_bytes(),
                budget,
                json.dumps(budget).encode(),
            )

    def test_multi_strategy_plan_can_bind_an_explicit_budget_pair(self) -> None:
        base = multi_strategy_budget_base_payload()
        base_raw = json.dumps(base, separators=(",", ":"), sort_keys=True).encode()
        budget = budget_impact_payload()
        budget["analysis_id"] = base["analysis_id"]
        budget["base_analysis"]["content_sha256"] = hashlib.sha256(base_raw).hexdigest()
        budget["strategies"]["comparator"] = {
            "id": "standard_care", "label": "Standard care"
        }
        budget["strategies"]["intervention"] = {
            "id": "best", "label": "Most effective option"
        }
        budget_raw = json.dumps(budget, separators=(",", ":"), sort_keys=True).encode()

        result = run_budget_impact(base, base_raw, budget, budget_raw)

        self.assertEqual(result["analysis_id"], base["analysis_id"])
        self.assertEqual(
            result["base_case"]["annual_net_budget_impact"],
            [550000.0, 1120000.0, 1810000.0],
        )
        self.assertEqual(result["calculation_classification"], "calculation_only")

    def test_multi_strategy_budget_pair_must_be_declared_in_strategy_order(self) -> None:
        base = multi_strategy_budget_base_payload()
        base["strategies"]["undeclared"] = copy.deepcopy(
            base["strategies"]["best"]
        )
        base["strategies"]["undeclared"]["name"] = "Undeclared option"
        base_raw = json.dumps(base, separators=(",", ":"), sort_keys=True).encode()
        budget = budget_impact_payload()
        budget["analysis_id"] = base["analysis_id"]
        budget["base_analysis"]["content_sha256"] = hashlib.sha256(
            base_raw
        ).hexdigest()
        budget["strategies"]["comparator"] = {
            "id": "standard_care",
            "label": "Standard care",
        }
        budget["strategies"]["intervention"] = {
            "id": "undeclared",
            "label": "Undeclared option",
        }

        with self.assertRaisesRegex(ModelValidationError, "exactly the ids"):
            run_budget_impact(
                base,
                base_raw,
                budget,
                json.dumps(
                    budget, separators=(",", ":"), sort_keys=True
                ).encode(),
            )

    def test_changed_analysis_plan_hash_fails_closed(self) -> None:
        plan = budget_base_payload()
        plan["cycles"] = 4
        changed_raw = json.dumps(plan).encode()

        with self.assertRaisesRegex(ModelValidationError, "does not match"):
            run_budget_impact(
                plan,
                changed_raw,
                budget_impact_payload(),
                BUDGET_IMPACT_PATH.read_bytes(),
            )

    def test_discounting_is_rejected(self) -> None:
        budget = budget_impact_payload()
        budget["discount_rate"] = 0.05

        with self.assertRaisesRegex(ModelValidationError, "must be 0"):
            run_budget_impact(
                budget_base_payload(),
                BUDGET_BASE_PATH.read_bytes(),
                budget,
                json.dumps(budget).encode(),
            )

    def test_missing_cost_provenance_fails_closed(self) -> None:
        budget = budget_impact_payload()
        budget["input_provenance"] = budget["input_provenance"][:-1]

        with self.assertRaisesRegex(ModelValidationError, "lack provenance"):
            run_budget_impact(
                budget_base_payload(),
                BUDGET_BASE_PATH.read_bytes(),
                budget,
                json.dumps(budget).encode(),
            )

    def test_sensitivity_cannot_target_authority_or_metadata(self) -> None:
        budget = budget_impact_payload()
        budget["sensitivity_parameters"][0]["target"] = "/perspective/price_year"

        with self.assertRaisesRegex(ModelValidationError, "unsupported budget impact target"):
            run_budget_impact(
                budget_base_payload(),
                BUDGET_BASE_PATH.read_bytes(),
                budget,
                json.dumps(budget).encode(),
            )

    def test_non_finite_calculation_fails_explicitly(self) -> None:
        budget = budget_impact_payload()
        budget["population"]["annual_eligible"][0] = 1e308
        provenance = next(
            mapping
            for mapping in budget["input_provenance"]
            if mapping["path"] == "/population/annual_eligible/0"
        )
        provenance["uncertainty_status"] = "fixed"
        budget["sensitivity_parameters"] = budget["sensitivity_parameters"][1:]

        with self.assertRaisesRegex(ModelValidationError, "not finite"):
            run_budget_impact(
                budget_base_payload(),
                BUDGET_BASE_PATH.read_bytes(),
                budget,
                json.dumps(budget).encode(),
            )


class HarnessContractTests(unittest.TestCase):
    def test_seeded_assistant_is_researcher_led_and_cannot_self_approve(
        self,
    ) -> None:
        rules = (REPOSITORY_ROOT / "runtime" / "harness" / "AGENTS.md").read_text()

        self.assertIn("The human researcher leads the scientific work", rules)
        self.assertIn("Self-checking is quality control, never independent", rules)
        self.assertIn("may not approve a gate", rules)
        self.assertIn("Never create or modify an app-owned approval", rules)
        self.assertIn("Canonical gate evidence is app-owned", rules)
        self.assertIn("Do not edit `AGENTS.md`", rules)
        self.assertNotIn("serve your own goals independently", rules)

    def test_seeded_state_exposes_required_gates_and_data_classification(self) -> None:
        state = (
            REPOSITORY_ROOT / "runtime" / "harness" / "knowledge" / "current-state.md"
        ).read_text()

        for gate in (
            "decision_problem",
            "conceptual_model",
            "analysis_plan",
            "independent_validation",
            "release",
        ):
            self.assertIn(f"- {gate}: pending", state)
        self.assertIn("- Data classification: unknown.", state)


if __name__ == "__main__":
    unittest.main()
