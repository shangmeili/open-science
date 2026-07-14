from __future__ import annotations

import copy
import hashlib
import json
import unittest
from math import exp
from pathlib import Path

from heor_core.budget_impact import run_budget_impact
from heor_core.model import (
    MarkovSpecification,
    ModelValidationError,
    run_markov,
)
from heor_core.uncertainty import (
    Pcg32,
    UncertaintySpecification,
    _apply_parameter_values,
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


def budget_base_payload() -> dict:
    return json.loads(BUDGET_BASE_PATH.read_text())


def budget_impact_payload() -> dict:
    return json.loads(BUDGET_IMPACT_PATH.read_text())


class MarkovModelTests(unittest.TestCase):
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
            ModelValidationError, "transition_schedule requires schema_version 0.4.0 or 0.5.0"
        ):
            MarkovSpecification.from_dict(payload)

    def test_constant_rate_derivations_match_hand_calculation(self) -> None:
        result = run_markov(MarkovSpecification.from_dict(rate_derived_payload()))

        self.assertEqual(result.engine_version, "0.5.0")
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

        self.assertEqual(result["engine_version"], "0.4.0")
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
        self.assertEqual(first["engine_version"], "0.4.0")
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
        base["assumptions"] = [
            {
                "id": identifier,
                "statement": f"Use constant {identifier} in this bounded fixture.",
                "reason": "Competing-rate uncertainty regression test.",
                "status": "proposed",
            }
            for identifier in basis_ids
        ]
        base["input_provenance"] = [{
            "path": "strategies.intervention.transition_matrix",
            "source_ids": [],
            "extraction_ids": [],
            "assumption_ids": basis_ids,
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
                                {"target_index": 1, "rate_per_year": rates[0], "assumption_id": basis_ids[0]},
                                {"target_index": 2, "rate_per_year": rates[1], "assumption_id": basis_ids[1]},
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
        uncertainty["schema_version"] = "0.3.0"
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
                    "type": "gamma",
                    "shape": 4.0,
                    "scale": rates[index] / 4.0,
                    "basis_ids": [basis_ids[index]],
                    "rationale": "Positive rate distribution",
                },
            }
            for index, (low, high) in enumerate(((0.1, 0.3), (0.02, 0.1)))
        ]
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
        self.assertEqual(result["calculation_classification"], "calculation_only")

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
    def test_seeded_agent_cannot_self_approve_or_claim_independent_validation(
        self,
    ) -> None:
        rules = (REPOSITORY_ROOT / "runtime" / "harness" / "AGENTS.md").read_text()

        self.assertIn("Humans retain decision authority", rules)
        self.assertIn("self-review is\n  never independent model validation", rules)
        self.assertIn("may not approve a gate", rules)
        self.assertIn("Never create or modify approval records", rules)
        self.assertIn("app-owned canonical log", rules)
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
