"""Deterministic three-state partitioned survival analysis.

This calculation is structurally separate from the cohort state-transition
engine.  It derives state occupancy directly from aligned PFS and OS survival
curves: progression free = PFS, progressed = OS - PFS, and dead = 1 - OS.
The module never repairs curve crossings or increasing survival silently.
"""

from __future__ import annotations

import hashlib
from math import isclose, isfinite
from typing import Any

from .economic_inputs import EconomicSpecification
from .model import (
    ModelValidationError,
    StrategyResult,
    _fully_incremental_analysis,
    _incremental,
    _optimal_at_threshold,
)
from .survival_materialization import validate_survival_curve_materializations
from .treatment_effect_duration import validate_treatment_effect_duration


SCHEMA_VERSION = "0.4.0"
PREVIOUS_SCHEMA_VERSION = "0.3.0"
LEGACY_SCHEMA_VERSION = "0.2.0"
ENGINE_VERSION = "0.4.0"
PREVIOUS_ENGINE_VERSION = "0.3.0"
PLAN_PATH = "heor/partitioned-survival-plan.json"
ANALYSIS_PATH = "heor/analysis-plan.json"
STATE_ORDER = ("progression_free", "progressed", "dead")
TOLERANCE = 1e-9
SHA256_LENGTH = 64


def run_partitioned_survival(
    analysis_plan: dict[str, Any],
    analysis_raw: bytes,
    partitioned_plan: dict[str, Any],
    partitioned_raw: bytes,
    materializations: dict[str, Any],
    materializations_raw: bytes,
    treatment_effect_duration: dict[str, Any] | None = None,
    treatment_effect_duration_raw: bytes | None = None,
) -> dict[str, Any]:
    """Validate and execute a hash-bound partitioned survival plan."""

    plan_schema = partitioned_plan.get("schema_version")
    specification = (
        EconomicSpecification.from_analysis_plan(analysis_plan)
        if plan_schema in {PREVIOUS_SCHEMA_VERSION, SCHEMA_VERSION}
        else EconomicSpecification.from_legacy_markov_plan(analysis_plan)
    )
    _validate(partitioned_plan, analysis_plan, analysis_raw, specification)
    source_curves = validate_survival_curve_materializations(
        analysis_plan,
        analysis_raw,
        partitioned_plan,
        materializations,
        materializations_raw,
    )
    duration_scenarios = None
    if plan_schema == SCHEMA_VERSION:
        if treatment_effect_duration is None or treatment_effect_duration_raw is None:
            raise ModelValidationError(
                "partitioned-survival schema 0.4.0 requires treatment-effect duration artifacts"
            )
        duration_scenarios = validate_treatment_effect_duration(
            analysis_plan,
            analysis_raw,
            partitioned_plan,
            materializations_raw,
            source_curves,
            treatment_effect_duration,
            treatment_effect_duration_raw,
        )
    elif treatment_effect_duration is not None or treatment_effect_duration_raw is not None:
        raise ModelValidationError(
            "treatment-effect duration artifacts require partitioned-survival schema 0.4.0"
        )

    result = calculate_partitioned_survival(specification, partitioned_plan)
    return {
        "schema_version": (
            SCHEMA_VERSION if plan_schema == SCHEMA_VERSION else PREVIOUS_SCHEMA_VERSION
        ),
        "partitioned_survival_plan_schema_version": plan_schema,
        "engine_version": (
            ENGINE_VERSION if plan_schema == SCHEMA_VERSION else PREVIOUS_ENGINE_VERSION
        ),
        "analysis_id": specification.analysis_id,
        "psm_id": partitioned_plan["psm_id"],
        "analysis_plan_sha256": hashlib.sha256(analysis_raw).hexdigest(),
        "partitioned_survival_plan_sha256": hashlib.sha256(
            partitioned_raw
        ).hexdigest(),
        "survival_curve_materializations_sha256": hashlib.sha256(
            materializations_raw
        ).hexdigest(),
        **(
            {
                "treatment_effect_duration_sha256": hashlib.sha256(
                    treatment_effect_duration_raw
                ).hexdigest(),
                "treatment_effect_duration_scenarios": [
                    {
                        "scenario_id": scenario["scenario_id"],
                        "label": scenario["label"],
                        **_duration_scenario_summary(
                            calculate_partitioned_survival(
                                specification,
                                {"strategies": scenario["strategies"]},
                            )
                        ),
                    }
                    for scenario in duration_scenarios.values()
                ],
            }
            if duration_scenarios is not None
            else {}
        ),
        "calculation_classification": "calculation_only",
        "model_type": "partitioned_survival",
        "state_order": list(STATE_ORDER),
        "time_origin": partitioned_plan["time_origin"],
        **result,
        "limitations": list(partitioned_plan["limitations"]),
        "warnings": [
            *(
                [
                    "Treatment-effect duration was represented by explicit sustained, immediate-stop, and log-linear-waning scenarios; statistical and clinical validity remain Human review responsibilities."
                ]
                if duration_scenarios is not None
                else [
                    "PFS and OS were evaluated as independently supplied curves; their extrapolated dependency and treatment-effect duration are not estimated by this calculator."
                ]
            ),
            *(
                [
                    "Legacy schema 0.2.0 transition inputs were validated for "
                    "compatibility but were not used by this calculation."
                ]
                if plan_schema == LEGACY_SCHEMA_VERSION
                else []
            ),
            "Workflow authorization, evidence verification, and independent "
            "validation are app-owned human controls.",
        ],
    }


def calculate_partitioned_survival(
    specification: EconomicSpecification,
    partitioned_plan: dict[str, Any],
) -> dict[str, Any]:
    """Evaluate already validated fixed curves against economic inputs.

    This narrow entry point exists so economic-input sensitivity analyses can
    reuse the deterministic PSM calculation after the fixed curve artifacts
    have been hash-validated once. Callers must not use it to bypass the
    public artifact-validation boundary.
    """

    strategy_results: list[tuple[str, StrategyResult]] = []
    curve_values = partitioned_plan["strategies"]
    for strategy_id in specification.strategy_order:
        strategy = specification.strategy_map[strategy_id]
        pfs = [float(row["survival"]) for row in curve_values[strategy_id]["pfs"]]
        overall = [float(row["survival"]) for row in curve_values[strategy_id]["os"]]
        occupancy = [
            (pfs_value, os_value - pfs_value, 1.0 - os_value)
            for pfs_value, os_value in zip(pfs, overall)
        ]
        total_cost = 0.0
        total_qaly = 0.0
        for cycle in range(specification.cycles):
            if specification.half_cycle_correction:
                reward_occupancy = tuple(
                    (start + end) / 2.0
                    for start, end in zip(occupancy[cycle], occupancy[cycle + 1])
                )
                discount_time = (cycle + 0.5) * specification.cycle_length_years
            else:
                reward_occupancy = occupancy[cycle]
                discount_time = cycle * specification.cycle_length_years
            cycle_cost = (
                sum(
                    probability * reward
                    for probability, reward in zip(
                        reward_occupancy, strategy.state_costs
                    )
                )
                * specification.cycle_length_years
            )
            cycle_qaly = (
                sum(
                    probability * reward
                    for probability, reward in zip(
                        reward_occupancy, strategy.state_utilities
                    )
                )
                * specification.cycle_length_years
            )
            total_cost += cycle_cost / (
                (1.0 + specification.cost_discount_rate) ** discount_time
            )
            total_qaly += cycle_qaly / (
                (1.0 + specification.outcome_discount_rate) ** discount_time
            )
        if not all(isfinite(value) for value in (total_cost, total_qaly)):
            raise ModelValidationError(
                f"partitioned survival strategy {strategy_id} produced a non-finite result"
            )
        net_monetary_benefit = (
            None
            if specification.willingness_to_pay is None
            else specification.willingness_to_pay * total_qaly - total_cost
        )
        result = StrategyResult(
            name=strategy.name,
            total_cost=total_cost,
            total_qaly=total_qaly,
            net_monetary_benefit=net_monetary_benefit,
            occupancy=tuple(occupancy),
            transition_mode="partitioned_survival",
            transition_schedule_start_cycles=(),
        )
        strategy_results.append((strategy_id, result))

    result_map = dict(strategy_results)
    baseline = result_map[specification.baseline_strategy_id]
    pairwise = {
        strategy_id: _incremental(
            baseline,
            result_map[strategy_id],
            specification.willingness_to_pay,
        ).to_dict()
        for strategy_id in specification.strategy_order
        if strategy_id != specification.baseline_strategy_id
    }
    return {
        "economic_basis": {
            "currency": specification.currency,
            "price_year": specification.price_year,
        },
        "strategy_order": list(specification.strategy_order),
        "baseline_strategy_id": specification.baseline_strategy_id,
        "strategies": {
            strategy_id: result.to_dict() for strategy_id, result in strategy_results
        },
        "pairwise_vs_baseline": pairwise,
        "fully_incremental_analysis": _fully_incremental_analysis(
            specification.strategy_order,
            result_map,
            specification.willingness_to_pay,
        ),
        "optimal_at_primary_threshold": _optimal_at_threshold(
            specification.strategy_order,
            result_map,
            specification.willingness_to_pay,
        ),
    }


def _validate(
    value: dict[str, Any],
    analysis_plan: dict[str, Any],
    analysis_raw: bytes,
    specification: EconomicSpecification,
) -> None:
    value = _mapping(value, "partitioned survival plan")
    plan_schema = value.get("schema_version")
    if plan_schema not in {
        LEGACY_SCHEMA_VERSION,
        PREVIOUS_SCHEMA_VERSION,
        SCHEMA_VERSION,
    }:
        raise ModelValidationError(
            "partitioned survival schema_version must be "
            f"{LEGACY_SCHEMA_VERSION}, {PREVIOUS_SCHEMA_VERSION}, or {SCHEMA_VERSION}"
        )
    analysis_schema = analysis_plan.get("schema_version")
    if plan_schema in {PREVIOUS_SCHEMA_VERSION, SCHEMA_VERSION} and analysis_schema != "0.12.0":
        raise ModelValidationError(
            "partitioned survival schema 0.3.0 or 0.4.0 requires analysis schema 0.12.0"
        )
    if plan_schema == LEGACY_SCHEMA_VERSION and analysis_schema == "0.12.0":
        raise ModelValidationError(
            "analysis schema 0.12.0 requires partitioned survival schema 0.3.0 or 0.4.0"
        )
    for field in ("psm_id", "analysis_id", "time_origin"):
        _nonempty(value.get(field), field)
    if value.get("status") != "ready_for_human_review":
        raise ModelValidationError(
            "partitioned survival status must be ready_for_human_review"
        )
    if value["analysis_id"] != specification.analysis_id:
        raise ModelValidationError(
            "partitioned survival analysis_id does not match the analysis plan"
        )
    base = _mapping(value.get("base_analysis"), "base_analysis")
    if base.get("path") != ANALYSIS_PATH:
        raise ModelValidationError(
            f"base_analysis.path must be {ANALYSIS_PATH}"
        )
    if base.get("content_sha256") != hashlib.sha256(analysis_raw).hexdigest():
        raise ModelValidationError(
            "base_analysis.content_sha256 does not match the analysis plan bytes"
        )
    linked = _mapping(
        analysis_plan.get("partitioned_survival_analysis"),
        "partitioned_survival_analysis",
    )
    if linked.get("path") != PLAN_PATH:
        raise ModelValidationError(f"analysis plan must link {PLAN_PATH}")
    duration_link = value.get("treatment_effect_duration")
    if plan_schema == SCHEMA_VERSION:
        duration_link = _mapping(duration_link, "treatment_effect_duration")
        if duration_link.get("path") != "heor/treatment-effect-duration.json":
            raise ModelValidationError(
                "treatment_effect_duration.path must be heor/treatment-effect-duration.json"
            )
        if not _valid_sha256(duration_link.get("content_sha256")):
            raise ModelValidationError(
                "treatment_effect_duration.content_sha256 must be lowercase SHA-256"
            )
    elif duration_link is not None:
        raise ModelValidationError(
            "treatment_effect_duration is admitted only by partitioned-survival schema 0.4.0"
        )
    if specification.states != STATE_ORDER:
        raise ModelValidationError(
            "partitioned survival requires analysis states progression_free, "
            "progressed, dead in that order"
        )

    structure = _mapping(value.get("model_structure"), "model_structure")
    if structure.get("type") != "partitioned_survival":
        raise ModelValidationError(
            "model_structure.type must be partitioned_survival"
        )
    if tuple(structure.get("state_order", [])) != STATE_ORDER:
        raise ModelValidationError(
            "model_structure.state_order must be progression_free, progressed, dead"
        )
    if structure.get("forward_only_disease_process") is not True:
        raise ModelValidationError(
            "model_structure.forward_only_disease_process must be true"
        )

    basis = _mapping(value.get("conceptual_basis"), "conceptual_basis")
    for field in (
        "forward_only_process",
        "population_alignment",
        "endpoint_alignment",
        "time_origin_alignment",
        "independent_extrapolation",
    ):
        item = _mapping(basis.get(field), f"conceptual_basis.{field}")
        _nonempty(item.get("rationale"), f"conceptual_basis.{field}.rationale")
        _nonempty_strings(
            item.get("basis_ids"), f"conceptual_basis.{field}.basis_ids"
        )

    strategies = _mapping(value.get("strategies"), "strategies")
    if set(strategies) != set(specification.strategy_order):
        raise ModelValidationError(
            "partitioned survival strategies must match analysis strategy_order exactly"
        )
    expected_times = [
        cycle * specification.cycle_length_years
        for cycle in range(specification.cycles + 1)
    ]
    for strategy_id in specification.strategy_order:
        curves = _mapping(strategies.get(strategy_id), f"strategies.{strategy_id}")
        parsed: dict[str, list[float]] = {}
        for endpoint in ("pfs", "os"):
            rows = curves.get(endpoint)
            if not isinstance(rows, list) or len(rows) != len(expected_times):
                raise ModelValidationError(
                    f"strategies.{strategy_id}.{endpoint} must contain one value "
                    "for time zero and each cycle endpoint"
                )
            values: list[float] = []
            prior = 1.0
            for index, (row_value, expected_time) in enumerate(
                zip(rows, expected_times)
            ):
                row = _mapping(
                    row_value, f"strategies.{strategy_id}.{endpoint}[{index}]"
                )
                time = _strict_float(
                    row.get("time_years"),
                    f"strategies.{strategy_id}.{endpoint}[{index}].time_years",
                )
                survival = _strict_float(
                    row.get("survival"),
                    f"strategies.{strategy_id}.{endpoint}[{index}].survival",
                )
                if not isclose(time, expected_time, rel_tol=0.0, abs_tol=TOLERANCE):
                    raise ModelValidationError(
                        f"strategies.{strategy_id}.{endpoint}[{index}].time_years "
                        "does not match the analysis cycle grid"
                    )
                if survival < 0.0 or survival > 1.0:
                    raise ModelValidationError("survival values must be from 0 to 1")
                if survival > prior + TOLERANCE:
                    raise ModelValidationError(
                        f"strategies.{strategy_id}.{endpoint} survival must be non-increasing"
                    )
                if index == 0 and not isclose(
                    survival, 1.0, rel_tol=0.0, abs_tol=TOLERANCE
                ):
                    raise ModelValidationError(
                        f"strategies.{strategy_id}.{endpoint} survival at time zero must be 1"
                    )
                _nonempty_strings(
                    row.get("basis_ids"),
                    f"strategies.{strategy_id}.{endpoint}[{index}].basis_ids",
                )
                values.append(survival)
                prior = survival
            parsed[endpoint] = values

        for index, (pfs_value, os_value) in enumerate(
            zip(parsed["pfs"], parsed["os"])
        ):
            if pfs_value > os_value + TOLERANCE:
                raise ModelValidationError(
                    f"strategies.{strategy_id} PFS exceeds OS at cycle endpoint "
                    f"{index}; curve crossing must be resolved explicitly"
                )
            occupancy = (pfs_value, os_value - pfs_value, 1.0 - os_value)
            if any(value < -TOLERANCE for value in occupancy) or not isclose(
                sum(occupancy), 1.0, rel_tol=0.0, abs_tol=TOLERANCE
            ):
                raise ModelValidationError(
                    f"strategies.{strategy_id} occupancy is incoherent at cycle endpoint {index}"
                )

        bindings = _mapping(
            curves.get("curve_review_bindings"),
            f"strategies.{strategy_id}.curve_review_bindings",
        )
        for endpoint in ("pfs", "os"):
            binding = _mapping(
                bindings.get(endpoint),
                f"strategies.{strategy_id}.curve_review_bindings.{endpoint}",
            )
            _nonempty(
                binding.get("path"),
                f"strategies.{strategy_id}.curve_review_bindings.{endpoint}.path",
            )
            expected_target = (
                f"partitioned_survival.strategies.{strategy_id}.{endpoint}"
            )
            if binding.get("target_path") != expected_target:
                raise ModelValidationError(
                    f"strategies.{strategy_id}.curve_review_bindings.{endpoint}."
                    f"target_path must be {expected_target}"
                )
            _nonempty(
                binding.get("selected_family"),
                f"strategies.{strategy_id}.curve_review_bindings.{endpoint}.selected_family",
            )
            if not _valid_sha256(binding.get("content_sha256")):
                raise ModelValidationError(
                    f"strategies.{strategy_id}.curve_review_bindings.{endpoint}."
                    "content_sha256 must be lowercase SHA-256"
                )

    validation = _mapping(value.get("validation_plan"), "validation_plan")
    for field in ("face", "internal", "external"):
        _nonempty_strings(validation.get(field), f"validation_plan.{field}")
    _nonempty_strings(value.get("limitations"), "limitations")


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ModelValidationError(f"{name} must be an object")
    return value


def _duration_scenario_summary(result: dict[str, Any]) -> dict[str, Any]:
    """Keep structural scenario output bounded while preserving decisions."""

    return {
        "strategy_order": result["strategy_order"],
        "baseline_strategy_id": result["baseline_strategy_id"],
        "strategies": {
            strategy_id: {
                "name": strategy["name"],
                "total_cost": strategy["total_cost"],
                "total_qaly": strategy["total_qaly"],
                "net_monetary_benefit": strategy["net_monetary_benefit"],
            }
            for strategy_id, strategy in result["strategies"].items()
        },
        "pairwise_vs_baseline": result["pairwise_vs_baseline"],
        "fully_incremental_analysis": result["fully_incremental_analysis"],
        "optimal_at_primary_threshold": result["optimal_at_primary_threshold"],
    }


def _nonempty(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ModelValidationError(f"{name} must not be empty")


def _nonempty_strings(value: Any, name: str) -> None:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
        or len(set(value)) != len(value)
    ):
        raise ModelValidationError(f"{name} must be a non-empty array of unique strings")


def _strict_float(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelValidationError(f"{name} must be a number")
    result = float(value)
    if not isfinite(result):
        raise ModelValidationError(f"{name} must be finite")
    return result


def _valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == SHA256_LENGTH
        and all(char in "0123456789abcdef" for char in value)
    )
