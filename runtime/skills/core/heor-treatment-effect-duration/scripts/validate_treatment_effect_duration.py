#!/usr/bin/env python3
"""Standalone validator for AI4HEOR treatment-effect duration artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from math import exp, isclose, isfinite, log
from pathlib import Path
from typing import Any


MAX_BYTES = 4 * 1024 * 1024
TOLERANCE = 1e-9
MODES = {"sustained", "immediate_stop", "log_linear_waning"}
ENDPOINTS = ("pfs", "os")


class ContractError(ValueError):
    pass


def validate(
    duration_path: Path,
    analysis_path: Path,
    psm_path: Path,
    materializations_path: Path,
) -> list[str]:
    try:
        duration_raw, duration = _read_json(duration_path, "duration artifact")
        analysis_raw, analysis = _read_json(analysis_path, "analysis plan")
        _, psm = _read_json(psm_path, "partitioned-survival plan")
        materializations_raw, materializations = _read_json(
            materializations_path, "survival materializations"
        )
        _validate(
            duration,
            duration_raw,
            analysis,
            analysis_raw,
            psm,
            materializations,
            materializations_raw,
        )
        return []
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ContractError) as error:
        return [str(error)]


def _validate(
    duration: dict[str, Any],
    duration_raw: bytes,
    analysis: dict[str, Any],
    analysis_raw: bytes,
    psm: dict[str, Any],
    materializations: dict[str, Any],
    materializations_raw: bytes,
) -> None:
    if analysis.get("schema_version") not in {"0.12.0", "0.13.0"}:
        raise ContractError("analysis schema_version must be 0.12.0 or 0.13.0")
    if psm.get("schema_version") not in {"0.4.0", "0.5.0"}:
        raise ContractError("partitioned-survival schema_version must be 0.4.0 or 0.5.0")
    strategy_order = analysis.get("strategy_order")
    if (
        not isinstance(strategy_order, list)
        or len(strategy_order) != 2
        or not all(isinstance(item, str) and item for item in strategy_order)
        or len(set(strategy_order)) != 2
    ):
        raise ContractError("analysis must contain exactly two ordered strategies")
    cycles = _integer(analysis.get("cycles"), "analysis cycles")
    if not 1 <= cycles <= 10_000:
        raise ContractError("analysis cycles must be from 1 to 10000")
    cycle_length = _positive(
        analysis.get("cycle_length_years"), "analysis cycle_length_years"
    )
    times = [index * cycle_length for index in range(cycles + 1)]
    source = _source_curves(
        materializations,
        analysis,
        psm,
        analysis_raw,
        times,
    )

    _exact(
        duration,
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
        "duration artifact",
    )
    if duration.get("schema_version") != "0.1.0":
        raise ContractError("duration schema_version must be 0.1.0")
    _text(duration.get("duration_id"), "duration_id")
    if duration.get("status") != "ready_for_human_review":
        raise ContractError("duration status must be ready_for_human_review")
    if duration.get("analysis_id") != analysis.get("analysis_id"):
        raise ContractError("duration analysis_id does not match analysis")
    if duration.get("psm_id") != psm.get("psm_id"):
        raise ContractError("duration psm_id does not match PSM")
    _binding(
        duration.get("base_analysis"),
        "base_analysis",
        "heor/analysis-plan.json",
        analysis_raw,
    )
    _binding(
        duration.get("source_curve_materializations"),
        "source_curve_materializations",
        "heor/survival-curve-materializations.json",
        materializations_raw,
    )
    _binding(
        psm.get("treatment_effect_duration"),
        "PSM treatment_effect_duration",
        "heor/treatment-effect-duration.json",
        duration_raw,
    )
    comparison = _object(duration.get("comparison"), "comparison")
    _exact(
        comparison,
        {"comparator_strategy_id", "intervention_strategy_id", "endpoint_order"},
        "comparison",
    )
    comparator = comparison.get("comparator_strategy_id")
    intervention = comparison.get("intervention_strategy_id")
    if comparator != analysis.get("baseline_strategy_id"):
        raise ContractError("duration comparator must equal baseline_strategy_id")
    if [comparator, intervention] != strategy_order:
        raise ContractError("duration comparison must follow strategy_order")
    if comparison.get("endpoint_order") != list(ENDPOINTS):
        raise ContractError("duration endpoint_order must be pfs then os")

    scenarios = duration.get("scenarios")
    if not isinstance(scenarios, list) or not 3 <= len(scenarios) <= 5:
        raise ContractError("duration requires 3-5 complete scenarios")
    coverage = {endpoint: set() for endpoint in ENDPOINTS}
    common: dict[str, tuple[float, float, tuple[str, ...]]] = {}
    parsed: list[tuple[str, str, dict[str, dict[str, Any]]]] = []
    ids: set[str] = set()
    horizon = cycles * cycle_length
    for scenario_index, scenario_value in enumerate(scenarios):
        label = f"scenarios[{scenario_index}]"
        scenario = _object(scenario_value, label)
        _exact(
            scenario,
            {"scenario_id", "label", "rationale", "basis_ids", "policies"},
            label,
        )
        scenario_id = _safe_id(scenario.get("scenario_id"), f"{label}.scenario_id")
        if scenario_id in ids:
            raise ContractError("scenario ids must be unique")
        ids.add(scenario_id)
        scenario_label = _text(scenario.get("label"), f"{label}.label")
        _text(scenario.get("rationale"), f"{label}.rationale")
        _strings(scenario.get("basis_ids"), f"{label}.basis_ids")
        policies = scenario.get("policies")
        if not isinstance(policies, list) or len(policies) != 2:
            raise ContractError(f"{label}.policies must contain PFS then OS")
        parsed_policies: dict[str, dict[str, Any]] = {}
        for policy_index, endpoint in enumerate(ENDPOINTS):
            policy_label = f"{label}.policies[{policy_index}]"
            policy = _object(policies[policy_index], policy_label)
            _exact(
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
                raise ContractError(f"{policy_label}.endpoint must be {endpoint}")
            mode = policy.get("mode")
            if mode not in MODES:
                raise ContractError(f"{policy_label}.mode is unsupported")
            coverage[endpoint].add(mode)
            evidence = _aligned(
                policy.get("evidence_horizon_years"),
                cycle_length,
                horizon,
                f"{policy_label}.evidence_horizon_years",
                False,
            )
            hr = _object(policy.get("hazard_ratio"), f"{policy_label}.hazard_ratio")
            _exact(hr, {"value", "basis_ids"}, f"{policy_label}.hazard_ratio")
            hr_value = _positive(hr.get("value"), f"{policy_label}.hazard_ratio.value")
            if isclose(hr_value, 1.0, rel_tol=0.0, abs_tol=TOLERANCE):
                raise ContractError(f"{policy_label}.hazard_ratio cannot equal one")
            hr_basis = tuple(_strings(hr.get("basis_ids"), f"{policy_label}.hazard_ratio.basis_ids"))
            _text(policy.get("rationale"), f"{policy_label}.rationale")
            _strings(policy.get("basis_ids"), f"{policy_label}.basis_ids")
            if mode == "log_linear_waning":
                waning_end = _aligned(
                    policy.get("waning_end_years"),
                    cycle_length,
                    horizon,
                    f"{policy_label}.waning_end_years",
                    True,
                )
                if waning_end <= evidence + TOLERANCE:
                    raise ContractError(f"{policy_label}.waning_end_years must follow evidence")
            else:
                if policy.get("waning_end_years") is not None:
                    raise ContractError(f"{policy_label}.waning_end_years must be null")
                waning_end = None
            signature = (evidence, hr_value, hr_basis)
            if endpoint in common and common[endpoint] != signature:
                raise ContractError(f"all {endpoint} policies must share evidence and HR")
            common[endpoint] = signature
            parsed_policies[endpoint] = {
                "mode": mode,
                "evidence": evidence,
                "hr": hr_value,
                "end": waning_end,
            }
        parsed.append((scenario_id, scenario_label, parsed_policies))
    if duration.get("base_case_scenario_id") not in ids:
        raise ContractError("base_case_scenario_id is not declared")
    for endpoint in ENDPOINTS:
        if coverage[endpoint] != MODES:
            raise ContractError(f"{endpoint} must cover all three duration modes")

    material_sha = hashlib.sha256(materializations_raw).hexdigest()
    duration_sha = hashlib.sha256(duration_raw).hexdigest()
    selected: dict[str, Any] | None = None
    for scenario_id, _, policies in parsed:
        basis = [
            f"source-materialization-sha256:{material_sha}",
            f"treatment-effect-duration-sha256:{duration_sha}",
            f"duration-scenario:{scenario_id}",
        ]
        strategies: dict[str, Any] = {comparator: {}, intervention: {}}
        for endpoint in ENDPOINTS:
            comparator_values = source[comparator][endpoint]
            intervention_values = _derive(
                comparator_values,
                source[intervention][endpoint],
                times,
                policies[endpoint],
            )
            strategies[comparator][endpoint] = _rows(times, comparator_values, basis)
            strategies[intervention][endpoint] = _rows(times, intervention_values, basis)
        _coherence(strategies, strategy_order, scenario_id)
        if scenario_id == duration.get("base_case_scenario_id"):
            selected = strategies
    assert selected is not None
    _compare_psm(psm, selected)
    _strings(duration.get("limitations"), "limitations")
    lowered = duration_raw.lower()
    if any(token in lowered for token in (b'"approved":', b'"approval_timestamp":', b'"independently_validated":')):
        raise ContractError("duration artifact contains a forbidden authority field")


def _source_curves(
    materializations: dict[str, Any],
    analysis: dict[str, Any],
    psm: dict[str, Any],
    analysis_raw: bytes,
    times: list[float],
) -> dict[str, dict[str, list[float]]]:
    if materializations.get("schema_version") != "0.1.0":
        raise ContractError("source materialization schema_version must be 0.1.0")
    if materializations.get("analysis_id") != analysis.get("analysis_id") or materializations.get("psm_id") != psm.get("psm_id"):
        raise ContractError("source materialization identity does not match")
    _binding(
        materializations.get("base_analysis"),
        "materializations.base_analysis",
        "heor/analysis-plan.json",
        analysis_raw,
    )
    if materializations.get("evaluator") != {"id": "ai4heor-parametric-survival", "version": "0.1.0"}:
        raise ContractError("source materialization evaluator is unsupported")
    curves = materializations.get("curves")
    strategy_order = analysis["strategy_order"]
    if not isinstance(curves, list) or len(curves) != len(strategy_order) * 2:
        raise ContractError("source materializations must contain every PFS/OS curve")
    output: dict[str, dict[str, list[float]]] = {item: {} for item in strategy_order}
    for index, (strategy_id, endpoint) in enumerate(
        (pair for strategy_id in strategy_order for pair in ((strategy_id, "pfs"), (strategy_id, "os")))
    ):
        curve = _object(curves[index], f"curves[{index}]")
        target = f"partitioned_survival.strategies.{strategy_id}.{endpoint}"
        if curve.get("target_path") != target or curve.get("strategy_id") != strategy_id or curve.get("endpoint") != endpoint:
            raise ContractError(f"curves[{index}] does not match {target}")
        family = curve.get("family")
        parameters = _object(curve.get("parameters"), f"{target}.parameters")
        if family == "exponential" and set(parameters) == {"rate_per_year"}:
            rate = _positive(parameters["rate_per_year"], f"{target}.rate_per_year")
            expected = [exp(-rate * time) for time in times]
        elif family == "weibull" and set(parameters) == {"shape", "scale_years"}:
            shape = _positive(parameters["shape"], f"{target}.shape")
            scale = _positive(parameters["scale_years"], f"{target}.scale_years")
            expected = [exp(-((time / scale) ** shape)) for time in times]
        else:
            raise ContractError(f"{target} family or parameters are unsupported")
        observed = curve.get("values")
        if not isinstance(observed, list) or len(observed) != len(expected):
            raise ContractError(f"{target} values do not cover the grid")
        for row_index, expected_value in enumerate(expected):
            row = _object(observed[row_index], f"{target}[{row_index}]")
            if not isclose(_number(row.get("time_years"), "time_years"), times[row_index], rel_tol=TOLERANCE, abs_tol=TOLERANCE) or not isclose(_number(row.get("survival"), "survival"), expected_value, rel_tol=TOLERANCE, abs_tol=TOLERANCE):
                raise ContractError(f"{target}[{row_index}] is not reproduced by parameters")
        output[strategy_id][endpoint] = expected
    return output


def _derive(comparator: list[float], source: list[float], times: list[float], policy: dict[str, Any]) -> list[float]:
    index = next(i for i, time in enumerate(times) if isclose(time, policy["evidence"], rel_tol=0.0, abs_tol=TOLERANCE))
    result = list(source[: index + 1])
    for current_index in range(index + 1, len(times)):
        increment = -log(comparator[current_index] / comparator[current_index - 1])
        if increment < -TOLERANCE or not isfinite(increment):
            raise ContractError("comparator hazard increment is invalid")
        start = times[current_index - 1]
        if policy["mode"] == "sustained":
            ratio = policy["hr"]
        elif policy["mode"] == "immediate_stop":
            ratio = 1.0
        elif start >= policy["end"] - TOLERANCE:
            ratio = 1.0
        else:
            fraction = (policy["end"] - start) / (policy["end"] - policy["evidence"])
            ratio = exp(log(policy["hr"]) * max(0.0, min(1.0, fraction)))
        current = result[-1] * exp(-ratio * max(0.0, increment))
        if not isfinite(current) or current <= 0.0 or current > result[-1] + TOLERANCE:
            raise ContractError("derived survival is invalid")
        result.append(current)
    return result


def _rows(times: list[float], values: list[float], basis: list[str]) -> list[dict[str, Any]]:
    return [{"time_years": time, "survival": value, "basis_ids": list(basis)} for time, value in zip(times, values)]


def _coherence(strategies: dict[str, Any], order: list[str], scenario_id: str) -> None:
    for strategy_id in order:
        for index, (pfs, overall) in enumerate(zip(strategies[strategy_id]["pfs"], strategies[strategy_id]["os"])):
            if pfs["survival"] > overall["survival"] + TOLERANCE:
                raise ContractError(f"scenario {scenario_id} has PFS above OS at cycle {index}")


def _compare_psm(psm: dict[str, Any], expected: dict[str, Any]) -> None:
    observed = _object(psm.get("strategies"), "PSM strategies")
    for strategy_id, endpoints in expected.items():
        strategy = _object(observed.get(strategy_id), f"PSM {strategy_id}")
        for endpoint, rows in endpoints.items():
            values = strategy.get(endpoint)
            if not isinstance(values, list) or len(values) != len(rows):
                raise ContractError(f"PSM {strategy_id}.{endpoint} does not cover the grid")
            for index, expected_row in enumerate(rows):
                row = _object(values[index], f"PSM {strategy_id}.{endpoint}[{index}]")
                if row.get("basis_ids") != expected_row["basis_ids"]:
                    raise ContractError(f"PSM {strategy_id}.{endpoint}[{index}] basis_ids do not match")
                for field in ("time_years", "survival"):
                    if not isclose(_number(row.get(field), field), expected_row[field], rel_tol=TOLERANCE, abs_tol=TOLERANCE):
                        raise ContractError(f"PSM {strategy_id}.{endpoint}[{index}].{field} does not match")


def _read_json(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise ContractError(f"{label} exceeds {MAX_BYTES} bytes")
    value = json.loads(raw)
    return raw, _object(value, label)


def _binding(value: Any, label: str, path: str, raw: bytes) -> None:
    binding = _object(value, label)
    _exact(binding, {"path", "content_sha256"}, label)
    if binding.get("path") != path or binding.get("content_sha256") != hashlib.sha256(raw).hexdigest():
        raise ContractError(f"{label} does not bind the current {path} bytes")


def _aligned(value: Any, cycle: float, horizon: float, label: str, allow_horizon: bool) -> float:
    result = _number(value, label)
    if result < 0.0 or (result > horizon + TOLERANCE if allow_horizon else result >= horizon - TOLERANCE):
        raise ContractError(f"{label} is outside the supported horizon")
    if not isclose(result / cycle, round(result / cycle), rel_tol=0.0, abs_tol=TOLERANCE):
        raise ContractError(f"{label} is not cycle aligned")
    return result


def _exact(value: dict[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise ContractError(f"{label} fields are not the exact supported contract")


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(f"{label} must be an object")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{label} must be a number")
    result = float(value)
    if not isfinite(result):
        raise ContractError(f"{label} must be finite")
    return result


def _positive(value: Any, label: str) -> float:
    result = _number(value, label)
    if result <= 0.0:
        raise ContractError(f"{label} must be positive")
    return result


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractError(f"{label} must be an integer")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ContractError(f"{label} must not be empty")
    return value


def _safe_id(value: Any, label: str) -> str:
    result = _text(value, label)
    if len(result) > 80 or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in result):
        raise ContractError(f"{label} is not a safe id")
    return result


def _strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value or any(not isinstance(item, str) or not item.strip() for item in value) or len(value) != len(set(value)):
        raise ContractError(f"{label} must be non-empty unique strings")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("duration", type=Path)
    parser.add_argument("analysis", type=Path)
    parser.add_argument("partitioned_survival", type=Path)
    parser.add_argument("materializations", type=Path)
    args = parser.parse_args()
    errors = validate(
        args.duration,
        args.analysis,
        args.partitioned_survival,
        args.materializations,
    )
    if errors:
        for error in errors:
            print(f"invalid: {error}")
        return 1
    print("valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
