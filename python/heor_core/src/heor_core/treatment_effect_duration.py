"""Deterministic treatment-effect duration scenarios for two-strategy PSMs.

The contract keeps each reviewed source curve through an evidence horizon, then
rebuilds the intervention curve from comparator hazard increments and an
explicit sustained, immediate-stop, or log-linear-waning hazard-ratio policy.
It never infers a duration assumption from a point estimate or repairs crossing
PFS/OS curves.
"""

from __future__ import annotations

import hashlib
from math import exp, isclose, isfinite, log
from typing import Any

from .model import ModelValidationError


SCHEMA_VERSION = "0.1.0"
ARTIFACT_PATH = "heor/treatment-effect-duration.json"
ANALYSIS_PATH = "heor/analysis-plan.json"
MATERIALIZATION_PATH = "heor/survival-curve-materializations.json"
PSM_SCHEMA_VERSION = "0.4.0"
MAX_SCENARIOS = 5
TOLERANCE = 1e-9
MODES = (
    "sustained",
    "immediate_stop",
    "log_linear_waning",
)
ENDPOINTS = ("pfs", "os")


def validate_treatment_effect_duration(
    analysis_plan: dict[str, Any],
    analysis_raw: bytes,
    partitioned_plan: dict[str, Any],
    materializations_raw: bytes,
    source_curves: dict[str, list[dict[str, Any]]],
    duration: dict[str, Any],
    duration_raw: bytes,
) -> dict[str, dict[str, Any]]:
    """Validate the artifact and return complete curve plans by scenario id."""

    value = _object(duration, "treatment-effect duration artifact")
    _exact_keys(
        value,
        {
            "schema_version",
            "duration_id",
            "analysis_id",
            "psm_id",
            "status",
            "base_analysis",
            "source_curve_materializations",
            "comparison",
            "base_case_scenario_id",
            "scenarios",
            "limitations",
        },
        "treatment-effect duration artifact",
    )
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ModelValidationError(
            f"treatment-effect duration schema_version must be {SCHEMA_VERSION}"
        )
    if partitioned_plan.get("schema_version") != PSM_SCHEMA_VERSION:
        raise ModelValidationError(
            f"treatment-effect duration requires partitioned-survival schema {PSM_SCHEMA_VERSION}"
        )
    _nonempty(value.get("duration_id"), "duration_id")
    if value.get("status") != "ready_for_human_review":
        raise ModelValidationError(
            "treatment-effect duration status must be ready_for_human_review"
        )
    if value.get("analysis_id") != analysis_plan.get("analysis_id"):
        raise ModelValidationError(
            "treatment-effect duration analysis_id does not match analysis plan"
        )
    if value.get("psm_id") != partitioned_plan.get("psm_id"):
        raise ModelValidationError(
            "treatment-effect duration psm_id does not match partitioned plan"
        )
    _validate_binding(
        value.get("base_analysis"),
        "base_analysis",
        ANALYSIS_PATH,
        analysis_raw,
    )
    _validate_binding(
        value.get("source_curve_materializations"),
        "source_curve_materializations",
        MATERIALIZATION_PATH,
        materializations_raw,
    )
    psm_binding = _object(
        partitioned_plan.get("treatment_effect_duration"),
        "partitioned plan treatment_effect_duration",
    )
    _exact_keys(
        psm_binding,
        {"path", "content_sha256"},
        "partitioned plan treatment_effect_duration",
    )
    if psm_binding.get("path") != ARTIFACT_PATH:
        raise ModelValidationError(
            f"partitioned plan treatment_effect_duration.path must be {ARTIFACT_PATH}"
        )
    if psm_binding.get("content_sha256") != hashlib.sha256(duration_raw).hexdigest():
        raise ModelValidationError(
            "partitioned plan treatment_effect_duration.content_sha256 does not match current bytes"
        )

    strategy_order = analysis_plan.get("strategy_order")
    if (
        not isinstance(strategy_order, list)
        or len(strategy_order) != 2
        or not all(isinstance(item, str) and item for item in strategy_order)
        or len(set(strategy_order)) != 2
    ):
        raise ModelValidationError(
            "treatment-effect duration supports exactly two ordered strategies"
        )
    comparison = _object(value.get("comparison"), "comparison")
    _exact_keys(
        comparison,
        {
            "comparator_strategy_id",
            "intervention_strategy_id",
            "endpoint_order",
        },
        "comparison",
    )
    comparator_id = comparison.get("comparator_strategy_id")
    intervention_id = comparison.get("intervention_strategy_id")
    if comparator_id != analysis_plan.get("baseline_strategy_id"):
        raise ModelValidationError(
            "comparison comparator must equal analysis baseline_strategy_id"
        )
    if [comparator_id, intervention_id] != strategy_order:
        raise ModelValidationError(
            "comparison must follow the exact two-strategy analysis order"
        )
    if comparison.get("endpoint_order") != list(ENDPOINTS):
        raise ModelValidationError("comparison.endpoint_order must be pfs then os")

    cycles = _integer(analysis_plan.get("cycles"), "analysis cycles")
    if not 1 <= cycles <= 10_000:
        raise ModelValidationError("analysis cycles must be from 1 to 10000")
    cycle_length = _positive(
        analysis_plan.get("cycle_length_years"), "analysis cycle_length_years"
    )
    horizon = cycles * cycle_length
    expected_times = [index * cycle_length for index in range(cycles + 1)]

    source: dict[str, dict[str, list[float]]] = {}
    for strategy_id in strategy_order:
        source[strategy_id] = {}
        for endpoint in ENDPOINTS:
            target = f"partitioned_survival.strategies.{strategy_id}.{endpoint}"
            rows = source_curves.get(target)
            if not isinstance(rows, list) or len(rows) != cycles + 1:
                raise ModelValidationError(
                    f"source materializations do not cover {target}"
                )
            parsed: list[float] = []
            for index, row_value in enumerate(rows):
                row = _object(row_value, f"source {target}[{index}]")
                time = _number(row.get("time_years"), f"source {target}[{index}].time_years")
                survival = _number(row.get("survival"), f"source {target}[{index}].survival")
                if not isclose(time, expected_times[index], rel_tol=0.0, abs_tol=TOLERANCE):
                    raise ModelValidationError(f"source {target} does not match the cycle grid")
                if not 0.0 < survival <= 1.0:
                    raise ModelValidationError(
                        f"source {target} must remain strictly positive for hazard reconstruction"
                    )
                parsed.append(survival)
            source[strategy_id][endpoint] = parsed

    scenarios = value.get("scenarios")
    if (
        not isinstance(scenarios, list)
        or not 3 <= len(scenarios) <= MAX_SCENARIOS
    ):
        raise ModelValidationError(
            f"treatment-effect duration requires 3-{MAX_SCENARIOS} complete scenarios"
        )
    scenario_ids: list[str] = []
    mode_coverage = {endpoint: set() for endpoint in ENDPOINTS}
    shared_effects: dict[str, tuple[float, float, tuple[str, ...]]] = {}
    parsed_scenarios: list[tuple[str, str, dict[str, dict[str, Any]]]] = []
    for scenario_index, scenario_value in enumerate(scenarios):
        label = f"scenarios[{scenario_index}]"
        scenario = _object(scenario_value, label)
        _exact_keys(
            scenario,
            {"scenario_id", "label", "rationale", "basis_ids", "policies"},
            label,
        )
        scenario_id = _safe_id(scenario.get("scenario_id"), f"{label}.scenario_id")
        if scenario_id in scenario_ids:
            raise ModelValidationError("treatment-effect duration scenario ids must be unique")
        scenario_ids.append(scenario_id)
        scenario_label = _nonempty(scenario.get("label"), f"{label}.label")
        _nonempty(scenario.get("rationale"), f"{label}.rationale")
        _nonempty_strings(scenario.get("basis_ids"), f"{label}.basis_ids")
        policies = scenario.get("policies")
        if not isinstance(policies, list) or len(policies) != len(ENDPOINTS):
            raise ModelValidationError(f"{label}.policies must contain PFS then OS")
        parsed_policies: dict[str, dict[str, Any]] = {}
        for policy_index, endpoint in enumerate(ENDPOINTS):
            policy_label = f"{label}.policies[{policy_index}]"
            policy = _object(policies[policy_index], policy_label)
            _exact_keys(
                policy,
                {
                    "endpoint",
                    "mode",
                    "evidence_horizon_years",
                    "hazard_ratio",
                    "waning_end_years",
                    "rationale",
                    "basis_ids",
                },
                policy_label,
            )
            if policy.get("endpoint") != endpoint:
                raise ModelValidationError(f"{policy_label}.endpoint must be {endpoint}")
            mode = policy.get("mode")
            if mode not in MODES:
                raise ModelValidationError(
                    f"{policy_label}.mode must be sustained, immediate_stop, or log_linear_waning"
                )
            mode_coverage[endpoint].add(mode)
            evidence_horizon = _aligned_time(
                policy.get("evidence_horizon_years"),
                cycle_length,
                horizon,
                f"{policy_label}.evidence_horizon_years",
                allow_horizon=False,
            )
            hazard_ratio = _object(policy.get("hazard_ratio"), f"{policy_label}.hazard_ratio")
            _exact_keys(
                hazard_ratio,
                {"value", "basis_ids"},
                f"{policy_label}.hazard_ratio",
            )
            hazard_ratio_value = _positive(
                hazard_ratio.get("value"), f"{policy_label}.hazard_ratio.value"
            )
            if isclose(hazard_ratio_value, 1.0, rel_tol=0.0, abs_tol=TOLERANCE):
                raise ModelValidationError(
                    f"{policy_label}.hazard_ratio.value must represent a non-null relative effect"
                )
            hazard_ratio_basis = tuple(
                _nonempty_strings(
                    hazard_ratio.get("basis_ids"),
                    f"{policy_label}.hazard_ratio.basis_ids",
                )
            )
            _nonempty(policy.get("rationale"), f"{policy_label}.rationale")
            _nonempty_strings(policy.get("basis_ids"), f"{policy_label}.basis_ids")
            if mode == "log_linear_waning":
                waning_end = _aligned_time(
                    policy.get("waning_end_years"),
                    cycle_length,
                    horizon,
                    f"{policy_label}.waning_end_years",
                    allow_horizon=True,
                )
                if waning_end <= evidence_horizon + TOLERANCE:
                    raise ModelValidationError(
                        f"{policy_label}.waning_end_years must follow the evidence horizon"
                    )
            else:
                if policy.get("waning_end_years") is not None:
                    raise ModelValidationError(
                        f"{policy_label}.waning_end_years must be null outside log_linear_waning"
                    )
                waning_end = None
            shared = (evidence_horizon, hazard_ratio_value, hazard_ratio_basis)
            prior_shared = shared_effects.setdefault(endpoint, shared)
            if prior_shared != shared:
                raise ModelValidationError(
                    f"all {endpoint} scenarios must share one evidence horizon, hazard ratio, and evidence basis"
                )
            parsed_policies[endpoint] = {
                "mode": mode,
                "evidence_horizon": evidence_horizon,
                "hazard_ratio": hazard_ratio_value,
                "waning_end": waning_end,
            }
        parsed_scenarios.append((scenario_id, scenario_label, parsed_policies))

    base_case_id = value.get("base_case_scenario_id")
    if base_case_id not in scenario_ids:
        raise ModelValidationError(
            "base_case_scenario_id must identify one declared scenario"
        )
    for endpoint in ENDPOINTS:
        if mode_coverage[endpoint] != set(MODES):
            raise ModelValidationError(
                f"{endpoint} scenarios must cover sustained, immediate_stop, and log_linear_waning"
            )

    materialization_sha = hashlib.sha256(materializations_raw).hexdigest()
    duration_sha = hashlib.sha256(duration_raw).hexdigest()
    output: dict[str, dict[str, Any]] = {}
    for scenario_id, scenario_label, policies in parsed_scenarios:
        strategies: dict[str, dict[str, list[dict[str, Any]]]] = {
            comparator_id: {},
            intervention_id: {},
        }
        basis_ids = [
            f"source-materialization-sha256:{materialization_sha}",
            f"treatment-effect-duration-sha256:{duration_sha}",
            f"duration-scenario:{scenario_id}",
        ]
        for endpoint in ENDPOINTS:
            comparator_values = source[comparator_id][endpoint]
            intervention_values = _derive_curve(
                comparator_values,
                source[intervention_id][endpoint],
                expected_times,
                policies[endpoint],
                f"{scenario_id}.{endpoint}",
            )
            strategies[comparator_id][endpoint] = _curve_rows(
                expected_times, comparator_values, basis_ids
            )
            strategies[intervention_id][endpoint] = _curve_rows(
                expected_times, intervention_values, basis_ids
            )
        _validate_pfs_os(strategies, strategy_order, scenario_id)
        output[scenario_id] = {
            "scenario_id": scenario_id,
            "label": scenario_label,
            "strategies": strategies,
        }

    selected = output[str(base_case_id)]
    _compare_partitioned_plan(partitioned_plan, selected["strategies"])
    if not _nonempty_strings(value.get("limitations"), "limitations"):
        raise ModelValidationError(
            "treatment-effect duration limitations must be non-empty"
        )
    serialized = duration_raw.lower()
    if any(
        field in serialized
        for field in (
            b'"approved":',
            b'"approval_timestamp":',
            b'"independently_validated":',
        )
    ):
        raise ModelValidationError(
            "treatment-effect duration contains a forbidden authority field"
        )
    return output


def _derive_curve(
    comparator: list[float],
    intervention_source: list[float],
    times: list[float],
    policy: dict[str, Any],
    label: str,
) -> list[float]:
    evidence_index = next(
        index
        for index, time in enumerate(times)
        if isclose(
            time,
            policy["evidence_horizon"],
            rel_tol=0.0,
            abs_tol=TOLERANCE,
        )
    )
    result = list(intervention_source[: evidence_index + 1])
    previous = result[-1]
    for index in range(evidence_index + 1, len(times)):
        comparator_previous = comparator[index - 1]
        comparator_current = comparator[index]
        try:
            baseline_increment = -log(comparator_current / comparator_previous)
        except (ArithmeticError, ValueError, ZeroDivisionError) as error:
            raise ModelValidationError(
                f"{label}: comparator hazard increment is undefined"
            ) from error
        if not isfinite(baseline_increment) or baseline_increment < -TOLERANCE:
            raise ModelValidationError(
                f"{label}: comparator cumulative hazard must be non-decreasing"
            )
        baseline_increment = max(0.0, baseline_increment)
        ratio = _cycle_hazard_ratio(policy, times[index - 1])
        try:
            current = previous * exp(-ratio * baseline_increment)
        except (ArithmeticError, OverflowError) as error:
            raise ModelValidationError(f"{label}: curve evaluation overflowed") from error
        if not isfinite(current) or current <= 0.0 or current > previous + TOLERANCE:
            raise ModelValidationError(
                f"{label}: derived survival is non-finite, zero, or increasing"
            )
        result.append(current)
        previous = current
    return result


def _cycle_hazard_ratio(policy: dict[str, Any], interval_start: float) -> float:
    mode = policy["mode"]
    if mode == "sustained":
        return float(policy["hazard_ratio"])
    if mode == "immediate_stop":
        return 1.0
    start = float(policy["evidence_horizon"])
    end = float(policy["waning_end"])
    if interval_start >= end - TOLERANCE:
        return 1.0
    fraction_remaining = max(0.0, min(1.0, (end - interval_start) / (end - start)))
    return exp(log(float(policy["hazard_ratio"])) * fraction_remaining)


def _curve_rows(
    times: list[float], values: list[float], basis_ids: list[str]
) -> list[dict[str, Any]]:
    return [
        {
            "time_years": time,
            "survival": value,
            "basis_ids": list(basis_ids),
        }
        for time, value in zip(times, values)
    ]


def _validate_pfs_os(
    strategies: dict[str, dict[str, list[dict[str, Any]]]],
    strategy_order: list[str],
    scenario_id: str,
) -> None:
    for strategy_id in strategy_order:
        pfs = strategies[strategy_id]["pfs"]
        overall = strategies[strategy_id]["os"]
        for index, (pfs_row, os_row) in enumerate(zip(pfs, overall)):
            if float(pfs_row["survival"]) > float(os_row["survival"]) + TOLERANCE:
                raise ModelValidationError(
                    f"treatment-effect duration scenario {scenario_id} has PFS above OS for {strategy_id} at cycle {index}"
                )


def _compare_partitioned_plan(
    partitioned_plan: dict[str, Any],
    expected: dict[str, dict[str, list[dict[str, Any]]]],
) -> None:
    strategies = _object(partitioned_plan.get("strategies"), "PSM strategies")
    for strategy_id, endpoints in expected.items():
        observed_strategy = _object(strategies.get(strategy_id), f"strategies.{strategy_id}")
        for endpoint, rows in endpoints.items():
            observed = observed_strategy.get(endpoint)
            if not isinstance(observed, list) or len(observed) != len(rows):
                raise ModelValidationError(
                    f"partitioned plan {strategy_id}.{endpoint} does not cover the duration base-case grid"
                )
            for index, expected_row in enumerate(rows):
                row = _object(observed[index], f"strategies.{strategy_id}.{endpoint}[{index}]")
                if row.get("basis_ids") != expected_row["basis_ids"]:
                    raise ModelValidationError(
                        f"partitioned plan {strategy_id}.{endpoint}[{index}] basis_ids do not match the duration base case"
                    )
                for field in ("time_years", "survival"):
                    observed_value = _number(
                        row.get(field),
                        f"strategies.{strategy_id}.{endpoint}[{index}].{field}",
                    )
                    if not isclose(
                        observed_value,
                        float(expected_row[field]),
                        rel_tol=TOLERANCE,
                        abs_tol=TOLERANCE,
                    ):
                        raise ModelValidationError(
                            f"partitioned plan {strategy_id}.{endpoint}[{index}].{field} does not match the duration base case"
                        )


def _validate_binding(
    value: Any,
    label: str,
    expected_path: str,
    expected_raw: bytes,
) -> None:
    binding = _object(value, label)
    _exact_keys(binding, {"path", "content_sha256"}, label)
    if binding.get("path") != expected_path:
        raise ModelValidationError(f"{label}.path must be {expected_path}")
    if binding.get("content_sha256") != hashlib.sha256(expected_raw).hexdigest():
        raise ModelValidationError(f"{label}.content_sha256 does not match current bytes")


def _aligned_time(
    value: Any,
    cycle_length: float,
    horizon: float,
    label: str,
    *,
    allow_horizon: bool,
) -> float:
    result = _number(value, label)
    upper_ok = result <= horizon + TOLERANCE if allow_horizon else result < horizon - TOLERANCE
    if result < 0.0 or not upper_ok:
        comparator = "at or before" if allow_horizon else "before"
        raise ModelValidationError(f"{label} must be non-negative and {comparator} the model horizon")
    cycles = result / cycle_length
    if not isclose(cycles, round(cycles), rel_tol=0.0, abs_tol=TOLERANCE):
        raise ModelValidationError(f"{label} must align to a model-cycle boundary")
    return result


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ModelValidationError(
            f"{label} fields must be exactly {', '.join(sorted(expected))}"
        )


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ModelValidationError(f"{label} must be an object")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelValidationError(f"{label} must be a number")
    result = float(value)
    if not isfinite(result):
        raise ModelValidationError(f"{label} must be finite")
    return result


def _positive(value: Any, label: str) -> float:
    result = _number(value, label)
    if result <= 0.0:
        raise ModelValidationError(f"{label} must be positive")
    return result


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ModelValidationError(f"{label} must be an integer")
    return value


def _safe_id(value: Any, label: str) -> str:
    result = _nonempty(value, label)
    if len(result) > 80 or any(
        character not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for character in result
    ):
        raise ModelValidationError(
            f"{label} must use lowercase letters, digits, hyphen, or underscore"
        )
    return result


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelValidationError(f"{label} must not be empty")
    return value


def _nonempty_strings(value: Any, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
        or len(value) != len(set(value))
    ):
        raise ModelValidationError(
            f"{label} must be a non-empty array of unique strings"
        )
    return value
