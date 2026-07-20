from __future__ import annotations

from contextlib import redirect_stdout
import copy
import hashlib
import importlib.util
from io import StringIO
import json
from math import exp, log
from pathlib import Path
import tempfile
import unittest

from heor_core.cli import main as cli_main
from heor_core.model import ModelValidationError
from heor_core.economic_inputs import EconomicSpecification
from heor_core.partitioned_survival import calculate_partitioned_survival, run_partitioned_survival
from heor_core.uncertainty import run_uncertainty
from test_partitioned_survival import valid_inputs as valid_psm_inputs
from test_partitioned_survival_uncertainty import valid_inputs as valid_partial_inputs
from test_joint_survival_uncertainty import (
    _draw_rows as joint_draw_rows,
    valid_inputs as valid_joint_inputs,
)


ROOT = Path(__file__).resolve().parents[3]
VALIDATOR_PATH = (
    ROOT
    / "runtime/skills/core/heor-treatment-effect-duration/scripts"
    / "validate_treatment_effect_duration.py"
)
SPEC = importlib.util.spec_from_file_location("portable_treatment_duration", VALIDATOR_PATH)
assert SPEC and SPEC.loader
PORTABLE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PORTABLE)


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode()


def _duration_payload(
    analysis: dict,
    analysis_raw: bytes,
    psm: dict,
    materializations_raw: bytes,
) -> dict:
    modes = (
        ("waning-base", "log_linear_waning", 2.0),
        ("sustained-effect", "sustained", None),
        ("immediate-stop", "immediate_stop", None),
    )
    return {
        "schema_version": "0.1.0",
        "duration_id": "psm-effect-duration",
        "analysis_id": analysis["analysis_id"],
        "psm_id": psm["psm_id"],
        "status": "ready_for_human_review",
        "base_analysis": {
            "path": "heor/analysis-plan.json",
            "content_sha256": hashlib.sha256(analysis_raw).hexdigest(),
        },
        "source_curve_materializations": {
            "path": "heor/survival-curve-materializations.json",
            "content_sha256": hashlib.sha256(materializations_raw).hexdigest(),
        },
        "comparison": {
            "comparator_strategy_id": "comparator",
            "intervention_strategy_id": "intervention",
            "endpoint_order": ["pfs", "os"],
        },
        "base_case_scenario_id": "waning-base",
        "scenarios": [
            {
                "scenario_id": scenario_id,
                "label": scenario_id.replace("-", " ").title(),
                "rationale": "Explicit duration scenario for Human review.",
                "basis_ids": [f"duration-basis-{scenario_id}"],
                "policies": [
                    {
                        "endpoint": endpoint,
                        "mode": mode,
                        "evidence_horizon_years": 0.0,
                        "hazard_ratio": {
                            "value": 0.5,
                            "basis_ids": [f"effect-{endpoint}"],
                        },
                        "waning_end_years": waning_end,
                        "rationale": "Apply the declared policy after the evidence horizon.",
                        "basis_ids": [f"duration-{endpoint}-{scenario_id}"],
                    }
                    for endpoint in ("pfs", "os")
                ],
            }
            for scenario_id, mode, waning_end in modes
        ],
        "limitations": [
            "The artifact explores duration structure but does not establish clinical validity."
        ],
    }


def _scenario_values(rate: float, mode: str) -> list[float]:
    values = [1.0]
    for interval_start in (0.0, 1.0):
        if mode == "sustained":
            ratio = 0.5
        elif mode == "immediate_stop":
            ratio = 1.0
        else:
            ratio = exp(log(0.5) * ((2.0 - interval_start) / 2.0))
        values.append(values[-1] * exp(-ratio * rate))
    return values


def _apply_base_rows(psm: dict, duration_raw: bytes, materializations_raw: bytes) -> None:
    basis_ids = [
        f"source-materialization-sha256:{hashlib.sha256(materializations_raw).hexdigest()}",
        f"treatment-effect-duration-sha256:{hashlib.sha256(duration_raw).hexdigest()}",
        "duration-scenario:waning-base",
    ]
    rates = {
        ("comparator", "pfs"): 0.5,
        ("comparator", "os"): 0.2,
        ("intervention", "pfs"): None,
        ("intervention", "os"): None,
    }
    for strategy_id in ("comparator", "intervention"):
        for endpoint in ("pfs", "os"):
            comparator_rate = 0.5 if endpoint == "pfs" else 0.2
            rate = rates[(strategy_id, endpoint)]
            values = (
                [exp(-float(rate) * index) for index in range(3)]
                if rate is not None
                else _scenario_values(comparator_rate, "log_linear_waning")
            )
            psm["strategies"][strategy_id][endpoint] = [
                {
                    "time_years": float(index),
                    "survival": survival,
                    "basis_ids": list(basis_ids),
                }
                for index, survival in enumerate(values)
            ]


def valid_inputs() -> list:
    analysis, analysis_raw, psm, _, materializations, materializations_raw = (
        valid_psm_inputs()
    )
    psm = copy.deepcopy(psm)
    psm["schema_version"] = "0.4.0"
    duration = _duration_payload(
        analysis, analysis_raw, psm, materializations_raw
    )
    duration_raw = _json_bytes(duration)
    psm["treatment_effect_duration"] = {
        "path": "heor/treatment-effect-duration.json",
        "content_sha256": hashlib.sha256(duration_raw).hexdigest(),
    }
    _apply_base_rows(psm, duration_raw, materializations_raw)
    psm_raw = _json_bytes(psm)
    return [
        analysis,
        analysis_raw,
        psm,
        psm_raw,
        materializations,
        materializations_raw,
        duration,
        duration_raw,
    ]


def _rebind_duration(inputs: list, *, update_rows: bool = False) -> None:
    inputs[7] = _json_bytes(inputs[6])
    inputs[2]["treatment_effect_duration"]["content_sha256"] = hashlib.sha256(
        inputs[7]
    ).hexdigest()
    if update_rows:
        _apply_base_rows(inputs[2], inputs[7], inputs[5])
    inputs[3] = _json_bytes(inputs[2])


def cost_normalized_inputs() -> list:
    inputs = valid_inputs()
    analysis, _, psm, _, materializations, _, duration, _ = inputs
    analysis["schema_version"] = "0.13.0"
    analysis["cost_input_normalization"] = {
        "path": "heor/cost-input-normalization.json"
    }
    analysis["decision_problem"] = {
        "jurisdiction": "China",
        "population": "Adults with advanced disease",
        "perspective": "Healthcare system",
    }
    analysis["evidence_sources"] = [
        {"id": "quantity-source"},
        {"id": "price-source"},
        {"id": "scope-source"},
        {"id": "utility-source"},
        {"id": "value-set-source"},
        {"id": "population-norm-source"},
    ]
    analysis["assumptions"] = [
        {"id": "overlap-assessment", "status": "proposed"},
        {"id": "dead-anchor", "status": "proposed"},
    ]
    analysis["input_provenance"] = []
    analysis_raw = _json_bytes(analysis)

    psm["schema_version"] = "0.5.0"
    psm["base_analysis"]["content_sha256"] = hashlib.sha256(analysis_raw).hexdigest()
    materializations["base_analysis"]["content_sha256"] = hashlib.sha256(analysis_raw).hexdigest()
    materializations_raw = _json_bytes(materializations)
    psm["curve_materializations"]["content_sha256"] = hashlib.sha256(materializations_raw).hexdigest()
    duration["base_analysis"]["content_sha256"] = hashlib.sha256(analysis_raw).hexdigest()
    duration["source_curve_materializations"]["content_sha256"] = hashlib.sha256(materializations_raw).hexdigest()
    duration_raw = _json_bytes(duration)
    psm["treatment_effect_duration"]["content_sha256"] = hashlib.sha256(duration_raw).hexdigest()
    _apply_base_rows(psm, duration_raw, materializations_raw)

    cost = {
        "schema_version": "0.1.0",
        "normalization_id": "psm-cost-inputs",
        "analysis_id": analysis["analysis_id"],
        "status": "ready_for_human_review",
        "base_analysis": {
            "path": "heor/analysis-plan.json",
            "content_sha256": hashlib.sha256(analysis_raw).hexdigest(),
        },
        "target_basis": {
            "currency": "CNY",
            "price_year": 2026,
            "jurisdiction": "China",
            "perspective": "Healthcare system",
        },
        "item_order": ["comparator-pf", "comparator-pd", "intervention-pf", "intervention-pd"],
        "items": {},
        "annual_state_costs": {
            "comparator": [1000.0, 3000.0, 0.0],
            "intervention": [4000.0, 3000.0, 0.0],
        },
        "limitations": ["Event and time-varying costs are outside this annual-rate contract."],
    }
    for item_id, strategy_id, state_id, amount in (
        ("comparator-pf", "comparator", "progression_free", 1000.0),
        ("comparator-pd", "comparator", "progressed", 3000.0),
        ("intervention-pf", "intervention", "progression_free", 4000.0),
        ("intervention-pd", "intervention", "progressed", 3000.0),
    ):
        cost["items"][item_id] = {
            "item_id": item_id,
            "strategy_id": strategy_id,
            "state_id": state_id,
            "category": "healthcare_resource",
            "description": "Annual resource rate for deterministic test.",
            "scope_basis_ids": ["scope-source"],
            "annual_quantity": {"value": 1.0, "unit": "annual_bundle", "basis_ids": ["quantity-source"]},
            "unit_price": {
                "amount": amount,
                "per_unit": "annual_bundle",
                "currency": "CNY",
                "price_year": 2026,
                "jurisdiction": "China",
                "price_basis": "paid_price",
                "tax_status": "not_applicable",
                "basis_ids": ["price-source"],
            },
            "adjustments": [],
            "normalized_unit_price": amount,
            "normalized_annual_cost": amount,
        }
    cost_raw = _json_bytes(cost)
    psm["cost_input_normalization"] = {
        "path": "heor/cost-input-normalization.json",
        "content_sha256": hashlib.sha256(cost_raw).hexdigest(),
    }
    psm_raw = _json_bytes(psm)
    return [
        analysis,
        analysis_raw,
        psm,
        psm_raw,
        materializations,
        materializations_raw,
        duration,
        duration_raw,
        cost,
        cost_raw,
    ]


def utility_normalized_inputs() -> list:
    inputs = cost_normalized_inputs()
    analysis, _, psm = inputs[0], inputs[1], inputs[2]
    analysis["schema_version"] = "0.14.0"
    analysis["utility_inputs"] = {"path": "heor/utility-inputs.json"}
    analysis_raw = _json_bytes(analysis)

    inputs[4]["base_analysis"]["content_sha256"] = hashlib.sha256(analysis_raw).hexdigest()
    materializations_raw = _json_bytes(inputs[4])
    psm["curve_materializations"]["content_sha256"] = hashlib.sha256(materializations_raw).hexdigest()
    inputs[6]["base_analysis"]["content_sha256"] = hashlib.sha256(analysis_raw).hexdigest()
    inputs[6]["source_curve_materializations"]["content_sha256"] = hashlib.sha256(materializations_raw).hexdigest()
    duration_raw = _json_bytes(inputs[6])
    psm["treatment_effect_duration"]["content_sha256"] = hashlib.sha256(duration_raw).hexdigest()
    _apply_base_rows(psm, duration_raw, materializations_raw)
    inputs[8]["base_analysis"]["content_sha256"] = hashlib.sha256(analysis_raw).hexdigest()
    cost_raw = _json_bytes(inputs[8])
    psm["cost_input_normalization"]["content_sha256"] = hashlib.sha256(cost_raw).hexdigest()

    utility = {
        "schema_version": "0.1.0",
        "utility_input_id": "psm-utility-inputs",
        "analysis_id": analysis["analysis_id"],
        "status": "ready_for_human_review",
        "base_analysis": {
            "path": "heor/analysis-plan.json",
            "content_sha256": hashlib.sha256(analysis_raw).hexdigest(),
        },
        "target_context": {
            "jurisdiction": "China",
            "population": "Adults with advanced disease",
            "outcome": "QALY",
        },
        "cycle_value_timing": "cycle_average",
        "item_order": [],
        "items": {},
        "cycle_state_utilities": {},
        "limitations": ["Event disutilities and component uncertainty are outside this contract."],
    }
    for strategy_id in analysis["strategy_order"]:
        source_values = analysis["strategies"][strategy_id]["state_utilities"]
        rows = []
        for cycle in range(analysis["cycles"]):
            rows.append([
                source_values[0] * (0.5 if strategy_id == "comparator" and cycle == 1 else 1.0),
                source_values[1],
                0.0,
            ])
        utility["cycle_state_utilities"][strategy_id] = rows
        for state_index, state_id in enumerate(analysis["states"]):
            dead = state_id == "dead"
            adjusted = strategy_id == "comparator" and state_id == "progression_free"
            factors = [1.0, 0.5] if adjusted else [1.0, 1.0]
            item_id = f"{strategy_id}-{state_id.replace('_', '-')}"
            utility["item_order"].append(item_id)
            utility["items"][item_id] = {
                "item_id": item_id,
                "strategy_id": strategy_id,
                "state_id": state_id,
                "description": "QALY dead anchor" if dead else "Cycle-average health-state utility",
                "application": {
                    "type": "health_state_utility",
                    "timing": "cycle_average_while_in_state",
                    "captured_effects": ["health_state"],
                    "excluded_effects": ["acute_adverse_events"],
                    "overlap_assessment": {
                        "rationale": "No separate event disutility is applied.",
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
                    "assessment_timing": "not_applicable" if dead else "Scheduled visits",
                    "basis_ids": ["dead-anchor" if dead else "utility-source"],
                },
                "valuation": {
                    "value_origin": "anchor" if dead else "value_set",
                    "value_set_id": None if dead else "reviewed-value-set",
                    "value_set_jurisdiction": None if dead else "China",
                    "preference_population": "not_applicable" if dead else "General population",
                    "valuation_method": "anchor" if dead else "time_trade_off",
                    "anchor": "dead_0_full_health_1",
                    "license_status": "not_applicable" if dead else "link_only",
                    "basis_ids": ["dead-anchor" if dead else "value-set-source"],
                },
                "mapping": None,
                "source_utility": {
                    "value": source_values[state_index],
                    "basis_ids": ["dead-anchor" if dead else "utility-source"],
                },
                "adjustments": ([{
                    "kind": "age_adjustment",
                    "operation": "multiply",
                    "method": "Test-only reviewed multiplicative factor",
                    "factors": factors,
                    "basis_ids": ["population-norm-source"],
                }] if adjusted else []),
                "cycle_values": [source_values[state_index] * factor for factor in factors],
                "uncertainty": {
                    "status": "fixed",
                    "basis_ids": ["dead-anchor" if dead else "utility-source"],
                    "limitations": ["Component uncertainty is not executed."],
                },
            }
    utility_raw = _json_bytes(utility)
    psm["schema_version"] = "0.6.0"
    psm["base_analysis"]["content_sha256"] = hashlib.sha256(analysis_raw).hexdigest()
    psm["utility_inputs"] = {
        "path": "heor/utility-inputs.json",
        "content_sha256": hashlib.sha256(utility_raw).hexdigest(),
    }
    psm_raw = _json_bytes(psm)
    return [
        analysis,
        analysis_raw,
        psm,
        psm_raw,
        inputs[4],
        materializations_raw,
        inputs[6],
        duration_raw,
        inputs[8],
        cost_raw,
        utility,
        utility_raw,
    ]


def event_disutility_inputs() -> list:
    inputs = utility_normalized_inputs()
    analysis, psm, materializations, duration, cost, utility = (
        inputs[0], inputs[2], inputs[4], inputs[6], inputs[8], inputs[10]
    )
    analysis["schema_version"] = "0.15.0"
    analysis["event_disutilities"] = {"path": "heor/event-disutilities.json"}
    analysis["evidence_sources"].extend(
        [
            {"id": "event-frequency-source"},
            {"id": "event-impact-source"},
            {"id": "event-method-source"},
        ]
    )
    analysis_raw = _json_bytes(analysis)

    materializations["base_analysis"]["content_sha256"] = hashlib.sha256(
        analysis_raw
    ).hexdigest()
    materializations_raw = _json_bytes(materializations)
    psm["curve_materializations"]["content_sha256"] = hashlib.sha256(
        materializations_raw
    ).hexdigest()
    duration["base_analysis"]["content_sha256"] = hashlib.sha256(
        analysis_raw
    ).hexdigest()
    duration["source_curve_materializations"]["content_sha256"] = hashlib.sha256(
        materializations_raw
    ).hexdigest()
    duration_raw = _json_bytes(duration)
    psm["treatment_effect_duration"]["content_sha256"] = hashlib.sha256(
        duration_raw
    ).hexdigest()
    _apply_base_rows(psm, duration_raw, materializations_raw)
    cost["base_analysis"]["content_sha256"] = hashlib.sha256(analysis_raw).hexdigest()
    cost_raw = _json_bytes(cost)
    psm["cost_input_normalization"]["content_sha256"] = hashlib.sha256(
        cost_raw
    ).hexdigest()

    utility["base_analysis"]["content_sha256"] = hashlib.sha256(analysis_raw).hexdigest()
    utility["items"]["intervention-progression-free"]["application"][
        "excluded_effects"
    ] = ["infusion-reaction", "recurrent-fatigue", "treatment-burden"]
    utility["items"]["intervention-progressed"]["application"][
        "excluded_effects"
    ] = ["recurrent-fatigue"]
    utility_raw = _json_bytes(utility)
    psm["utility_inputs"]["content_sha256"] = hashlib.sha256(utility_raw).hexdigest()

    days_per_year = 365.25
    one_time_qaly = 0.2 * 7.0 / days_per_year
    recurrent_qaly = 0.05 * 14.0 / days_per_year
    event = {
        "schema_version": "0.1.0",
        "event_disutility_id": "psm-event-disutilities",
        "analysis_id": analysis["analysis_id"],
        "status": "ready_for_human_review",
        "base_analysis": {
            "path": "heor/analysis-plan.json",
            "content_sha256": hashlib.sha256(analysis_raw).hexdigest(),
        },
        "base_utility_inputs": {
            "path": "heor/utility-inputs.json",
            "content_sha256": hashlib.sha256(utility_raw).hexdigest(),
        },
        "day_count_convention": {
            "days_per_year": days_per_year,
            "rationale": "Use the reviewed day-count convention consistently.",
            "basis_ids": ["event-method-source"],
        },
        "combination_rule": {
            "method": "additive_expected_qaly_loss",
            "rationale": "Add separately excluded expected event losses.",
            "basis_ids": ["event-method-source"],
        },
        "item_order": [
            "intervention-infusion-reaction",
            "intervention-recurrent-fatigue",
            "intervention-treatment-burden",
        ],
        "items": {},
        "cycle_state_qaly_losses": {
            "comparator": [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0]],
            "intervention": [
                [0.2 * one_time_qaly + 0.5 * recurrent_qaly + 0.02, 0.5 * recurrent_qaly, 0.0],
                [0.25 * recurrent_qaly + 0.01, 0.25 * recurrent_qaly, 0.0],
            ],
        },
        "limitations": [
            "Long-lasting sequelae, event costs, interactions, and component uncertainty are outside this contract."
        ],
    }

    def item(
        item_id: str,
        event_id: str,
        label: str,
        category: str,
        mode: str,
        eligible_states: list[str],
        decrement: float,
        duration_days: float | None,
        qaly_loss: float | None,
        measure: str,
        schedule: list[float],
        reviewed_ids: list[str],
        cycle_losses: list[float],
    ) -> dict:
        return {
            "item_id": item_id,
            "event_id": event_id,
            "strategy_id": "intervention",
            "label": label,
            "event": {
                "category": category,
                "terminology_system": "Test terminology",
                "terminology_code": event_id,
                "severity": {
                    "system": "Test severity",
                    "grade": "reviewed",
                    "rationale": "Severity is explicit for Human review.",
                },
            },
            "application": {
                "mode": mode,
                "eligible_states": eligible_states,
                "timing": "cycle_average",
                "cost_handling": "not_in_this_artifact",
                "rationale": "Apply only to the declared at-risk states.",
                "basis_ids": ["event-method-source"],
            },
            "health_impact": {
                "utility_decrement": decrement,
                "decrement_scale": "absolute_utility_decrement",
                "duration_days": duration_days,
                "qaly_loss_per_occurrence": qaly_loss,
                "instrument_or_method": "Reviewed utility decrement",
                "respondent": "patient",
                "source_population": "Trial population",
                "basis_ids": ["event-impact-source"],
            },
            "occurrence": {
                "measure": measure,
                "schedule": schedule,
                "source_population": "Trial safety population",
                "observation_window": "Model-cycle aligned",
                "basis_ids": ["event-frequency-source"],
            },
            "utility_overlap": {
                "status": "excluded_from_health_state_utility",
                "reviewed_utility_item_ids": reviewed_ids,
                "rationale": "The named utility items explicitly exclude this event.",
                "basis_ids": ["overlap-assessment"],
            },
            "cycle_qaly_loss_per_eligible_person": cycle_losses,
            "uncertainty": {
                "status": "fixed",
                "basis_ids": ["event-impact-source"],
                "limitations": ["Component uncertainty is not executed."],
            },
        }

    event["items"]["intervention-infusion-reaction"] = item(
        "intervention-infusion-reaction",
        "infusion-reaction",
        "Infusion reaction",
        "adverse_event",
        "one_time",
        ["progression_free"],
        0.2,
        7.0,
        one_time_qaly,
        "probability",
        [0.2, 0.0],
        ["intervention-progression-free"],
        [0.2 * one_time_qaly, 0.0],
    )
    event["items"]["intervention-recurrent-fatigue"] = item(
        "intervention-recurrent-fatigue",
        "recurrent-fatigue",
        "Recurrent fatigue",
        "adverse_event",
        "recurrent",
        ["progression_free", "progressed"],
        0.05,
        14.0,
        recurrent_qaly,
        "expected_events",
        [0.5, 0.25],
        ["intervention-progression-free", "intervention-progressed"],
        [0.5 * recurrent_qaly, 0.25 * recurrent_qaly],
    )
    event["items"]["intervention-treatment-burden"] = item(
        "intervention-treatment-burden",
        "treatment-burden",
        "Continuous treatment burden",
        "treatment_process",
        "continuous_exposure",
        ["progression_free"],
        0.02,
        None,
        None,
        "exposure_fraction",
        [1.0, 0.5],
        ["intervention-progression-free"],
        [0.02, 0.01],
    )
    event_raw = _json_bytes(event)
    psm["schema_version"] = "0.7.0"
    psm["base_analysis"]["content_sha256"] = hashlib.sha256(analysis_raw).hexdigest()
    psm["event_disutilities"] = {
        "path": "heor/event-disutilities.json",
        "content_sha256": hashlib.sha256(event_raw).hexdigest(),
    }
    psm_raw = _json_bytes(psm)
    return [
        analysis,
        analysis_raw,
        psm,
        psm_raw,
        materializations,
        materializations_raw,
        duration,
        duration_raw,
        cost,
        cost_raw,
        utility,
        utility_raw,
        event,
        event_raw,
    ]


class TreatmentEffectDurationTests(unittest.TestCase):
    def test_psm_0_7_binds_and_applies_event_qaly_losses(self) -> None:
        inputs = event_disutility_inputs()
        result = run_partitioned_survival(*inputs)
        intervention = result["strategies"]["intervention"]
        self.assertEqual(result["schema_version"], "0.7.0")
        self.assertEqual(result["engine_version"], "0.7.0")
        self.assertEqual(result["event_disutilities_summary"]["item_count"], 3)
        self.assertEqual(result["event_disutilities_summary"]["one_time_item_count"], 1)
        self.assertGreater(intervention["event_disutility_qaly_loss"], 0.0)
        occupancy = intervention["occupancy"]
        schedule = inputs[12]["cycle_state_qaly_losses"]["intervention"]
        expected_loss = 0.0
        for cycle in range(inputs[0]["cycles"]):
            reward_occupancy = [
                (start + end) / 2.0
                for start, end in zip(occupancy[cycle], occupancy[cycle + 1])
            ]
            undiscounted = sum(
                probability * loss
                for probability, loss in zip(reward_occupancy, schedule[cycle])
            )
            discount_time = (cycle + 0.5) * inputs[0]["cycle_length_years"]
            expected_loss += undiscounted / (
                (1.0 + inputs[0]["discount_rates"]["outcomes"]) ** discount_time
            )
        self.assertAlmostEqual(intervention["event_disutility_qaly_loss"], expected_loss)
        self.assertAlmostEqual(
            intervention["pre_event_total_qaly"]
            - intervention["event_disutility_qaly_loss"],
            intervention["total_qaly"],
        )

    def test_psm_0_7_rejects_stale_event_binding(self) -> None:
        inputs = event_disutility_inputs()
        inputs[2]["event_disutilities"]["content_sha256"] = "0" * 64
        inputs[3] = _json_bytes(inputs[2])
        with self.assertRaisesRegex(ModelValidationError, "event_disutilities.content_sha256"):
            run_partitioned_survival(*inputs)

    def test_psm_0_6_binds_and_uses_cycle_specific_utility_inputs(self) -> None:
        inputs = utility_normalized_inputs()
        result = run_partitioned_survival(*inputs)
        fixed = calculate_partitioned_survival(
            EconomicSpecification.from_analysis_plan(inputs[0]), inputs[2]
        )
        self.assertEqual(result["schema_version"], "0.6.0")
        self.assertEqual(result["engine_version"], "0.6.0")
        self.assertEqual(result["utility_inputs_summary"]["item_count"], 6)
        self.assertEqual(result["utility_inputs_summary"]["adjusted_item_count"], 1)
        self.assertLess(
            result["strategies"]["comparator"]["total_qaly"],
            fixed["strategies"]["comparator"]["total_qaly"],
        )

    def test_psm_0_6_rejects_stale_utility_binding(self) -> None:
        inputs = utility_normalized_inputs()
        inputs[2]["utility_inputs"]["content_sha256"] = "0" * 64
        inputs[3] = _json_bytes(inputs[2])
        with self.assertRaisesRegex(ModelValidationError, "utility_inputs.content_sha256"):
            run_partitioned_survival(*inputs)

    def test_psm_0_5_binds_and_reports_normalized_cost_inputs(self) -> None:
        inputs = cost_normalized_inputs()
        result = run_partitioned_survival(*inputs)
        self.assertEqual(result["schema_version"], "0.5.0")
        self.assertEqual(result["engine_version"], "0.5.0")
        self.assertEqual(result["cost_input_normalization_summary"]["item_count"], 4)
        self.assertEqual(
            result["cost_input_normalization_sha256"],
            hashlib.sha256(inputs[9]).hexdigest(),
        )

    def test_runs_three_complete_structural_scenarios(self) -> None:
        inputs = valid_inputs()
        result = run_partitioned_survival(*inputs)
        self.assertEqual(result["schema_version"], "0.4.0")
        self.assertEqual(result["engine_version"], "0.4.0")
        self.assertEqual(result["partitioned_survival_plan_schema_version"], "0.4.0")
        self.assertEqual(
            result["treatment_effect_duration_sha256"],
            hashlib.sha256(inputs[7]).hexdigest(),
        )
        scenarios = {
            item["scenario_id"]: item
            for item in result["treatment_effect_duration_scenarios"]
        }
        self.assertEqual(
            set(scenarios), {"waning-base", "sustained-effect", "immediate-stop"}
        )
        observed = result["strategies"]["intervention"]["occupancy"][1][0]
        self.assertAlmostEqual(observed, exp(-0.25))
        sustained_qaly = scenarios["sustained-effect"]["strategies"]["intervention"][
            "total_qaly"
        ]
        immediate_qaly = scenarios["immediate-stop"]["strategies"]["intervention"][
            "total_qaly"
        ]
        self.assertGreater(sustained_qaly, immediate_qaly)
        self.assertTrue(any("explicit sustained" in item for item in result["warnings"]))

    def test_rejects_missing_required_mode_coverage(self) -> None:
        inputs = valid_inputs()
        for policy in inputs[6]["scenarios"][2]["policies"]:
            policy["mode"] = "sustained"
        _rebind_duration(inputs)
        with self.assertRaisesRegex(ModelValidationError, "must cover sustained"):
            run_partitioned_survival(*inputs)

    def test_rejects_stale_duration_binding(self) -> None:
        inputs = valid_inputs()
        inputs[2]["treatment_effect_duration"]["content_sha256"] = "0" * 64
        inputs[3] = _json_bytes(inputs[2])
        with self.assertRaisesRegex(ModelValidationError, "does not match current bytes"):
            run_partitioned_survival(*inputs)

    def test_rejects_crossing_duration_scenario_without_repair(self) -> None:
        inputs = valid_inputs()
        for scenario in inputs[6]["scenarios"]:
            scenario["policies"][0]["hazard_ratio"]["value"] = 0.01
        _rebind_duration(inputs)
        with self.assertRaisesRegex(ModelValidationError, "PFS above OS"):
            run_partitioned_survival(*inputs)

    def test_rejects_more_than_two_strategies(self) -> None:
        inputs = valid_inputs()
        inputs[0]["strategy_order"].append("third")
        inputs[0]["strategies"]["third"] = copy.deepcopy(
            inputs[0]["strategies"]["comparator"]
        )
        inputs[0]["strategies"]["third"]["name"] = "Third strategy"
        inputs[1] = _json_bytes(inputs[0])
        inputs[2]["base_analysis"]["content_sha256"] = hashlib.sha256(
            inputs[1]
        ).hexdigest()
        inputs[4]["base_analysis"]["content_sha256"] = hashlib.sha256(
            inputs[1]
        ).hexdigest()
        inputs[6]["base_analysis"]["content_sha256"] = hashlib.sha256(
            inputs[1]
        ).hexdigest()
        inputs[5] = _json_bytes(inputs[4])
        inputs[2]["curve_materializations"]["content_sha256"] = hashlib.sha256(
            inputs[5]
        ).hexdigest()
        inputs[6]["source_curve_materializations"]["content_sha256"] = hashlib.sha256(
            inputs[5]
        ).hexdigest()
        _rebind_duration(inputs, update_rows=True)
        with self.assertRaisesRegex(
            ModelValidationError,
            "must match analysis strategy_order|every strategy|exactly two ordered strategies",
        ):
            run_partitioned_survival(*inputs)

    def test_cli_requires_and_consumes_duration_artifact(self) -> None:
        inputs = valid_inputs()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = (
                "heor/analysis-plan.json",
                "heor/partitioned-survival-plan.json",
                "heor/survival-curve-materializations.json",
                "heor/treatment-effect-duration.json",
            )
            for relative, raw in zip(paths, (inputs[1], inputs[3], inputs[5], inputs[7])):
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
            output = StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    cli_main(
                        [
                            str(root / paths[0]),
                            "--partitioned-survival-plan",
                            str(root / paths[1]),
                            "--survival-curve-materializations",
                            str(root / paths[2]),
                            "--treatment-effect-duration",
                            str(root / paths[3]),
                        ]
                    ),
                    0,
                )
            self.assertEqual(json.loads(output.getvalue())["schema_version"], "0.4.0")

    def test_portable_validator_recalculates_and_binds_current_bytes(self) -> None:
        inputs = valid_inputs()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = [
                root / "heor/treatment-effect-duration.json",
                root / "heor/analysis-plan.json",
                root / "heor/partitioned-survival-plan.json",
                root / "heor/survival-curve-materializations.json",
            ]
            for destination, raw in zip(paths, (inputs[7], inputs[1], inputs[3], inputs[5])):
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(raw)
            self.assertEqual(PORTABLE.validate(*paths), [])
            materializations = json.loads(paths[3].read_bytes())
            materializations["curves"][0]["values"][1]["survival"] = 0.9
            paths[3].write_bytes(_json_bytes(materializations))
            errors = PORTABLE.validate(*paths)
            self.assertTrue(
                any(
                    "source_curve_materializations" in item
                    or "not reproduced by parameters" in item
                    for item in errors
                ),
                errors,
            )

    def test_economic_uncertainty_binds_and_reports_duration_scenarios(self) -> None:
        inputs = list(valid_partial_inputs())
        analysis, analysis_raw, uncertainty = inputs[0], inputs[1], inputs[2]
        psm, materializations_raw = inputs[4], inputs[7]
        psm["schema_version"] = "0.4.0"
        duration = _duration_payload(
            analysis, analysis_raw, psm, materializations_raw
        )
        duration_raw = _json_bytes(duration)
        psm["treatment_effect_duration"] = {
            "path": "heor/treatment-effect-duration.json",
            "content_sha256": hashlib.sha256(duration_raw).hexdigest(),
        }
        _apply_base_rows(psm, duration_raw, materializations_raw)
        psm_raw = _json_bytes(psm)
        inputs[4], inputs[5] = psm, psm_raw
        uncertainty["partitioned_survival_inputs"]["plan"][
            "content_sha256"
        ] = hashlib.sha256(psm_raw).hexdigest()
        uncertainty["partitioned_survival_inputs"]["treatment_effect_duration"] = {
            "path": "heor/treatment-effect-duration.json",
            "content_sha256": hashlib.sha256(duration_raw).hexdigest(),
        }
        inputs[2] = uncertainty
        inputs[3] = _json_bytes(uncertainty)
        result = run_uncertainty(
            *inputs,
            None,
            None,
            None,
            duration,
            duration_raw,
        )
        self.assertEqual(
            result["treatment_effect_duration_sha256"],
            hashlib.sha256(duration_raw).hexdigest(),
        )
        self.assertEqual(len(result["treatment_effect_duration_scenarios"]), 3)

    def test_joint_uncertainty_binds_the_selected_duration_structure(self) -> None:
        inputs = valid_joint_inputs(vary=False)
        analysis, analysis_raw, uncertainty = inputs[0], inputs[1], inputs[2]
        psm, materializations_raw, manifest = inputs[4], inputs[7], inputs[8]
        psm["schema_version"] = "0.4.0"
        duration = _duration_payload(
            analysis, analysis_raw, psm, materializations_raw
        )
        duration_raw = _json_bytes(duration)
        psm["treatment_effect_duration"] = {
            "path": "heor/treatment-effect-duration.json",
            "content_sha256": hashlib.sha256(duration_raw).hexdigest(),
        }
        _apply_base_rows(psm, duration_raw, materializations_raw)
        psm_raw = _json_bytes(psm)
        inputs[4], inputs[5] = psm, psm_raw
        draws_raw = joint_draw_rows(psm, vary=False)
        inputs[10] = draws_raw
        manifest["schema_version"] = "0.2.0"
        manifest["partitioned_survival_plan"]["content_sha256"] = hashlib.sha256(
            psm_raw
        ).hexdigest()
        manifest["treatment_effect_duration"] = {
            "path": "heor/treatment-effect-duration.json",
            "content_sha256": hashlib.sha256(duration_raw).hexdigest(),
        }
        manifest["draw_file"]["content_sha256"] = hashlib.sha256(
            draws_raw
        ).hexdigest()
        inputs[9] = _json_bytes(manifest)
        uncertainty["partitioned_survival_inputs"]["plan"][
            "content_sha256"
        ] = hashlib.sha256(psm_raw).hexdigest()
        uncertainty["partitioned_survival_inputs"]["treatment_effect_duration"] = {
            "path": "heor/treatment-effect-duration.json",
            "content_sha256": hashlib.sha256(duration_raw).hexdigest(),
        }
        uncertainty["joint_survival_inputs"]["manifest"][
            "content_sha256"
        ] = hashlib.sha256(inputs[9]).hexdigest()
        uncertainty["joint_survival_inputs"]["draws"][
            "content_sha256"
        ] = hashlib.sha256(draws_raw).hexdigest()
        uncertainty["probabilistic_analysis"]["omitted_parameters"] = [
            item
            for item in uncertainty["probabilistic_analysis"]["omitted_parameters"]
            if item["provenance_path"]
            != "partitioned_survival.structural.treatment_effect_duration"
        ]
        inputs[2] = uncertainty
        inputs[3] = _json_bytes(uncertainty)
        result = run_uncertainty(*inputs, duration, duration_raw)
        self.assertEqual(
            result["treatment_effect_duration_sha256"],
            hashlib.sha256(duration_raw).hexdigest(),
        )
        self.assertTrue(
            any(
                "reported separately" in limitation
                for limitation in result["limitations"]
            )
        )


if __name__ == "__main__":
    unittest.main()
