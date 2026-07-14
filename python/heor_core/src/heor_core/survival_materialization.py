"""Deterministic materialization of selected parametric survival curves.

The contract is deliberately narrow: exponential rate or Weibull accelerated-
failure-time shape/scale parameters are evaluated on the analysis cycle grid.
It does not fit, select, transform, or clinically validate a survival model.
"""

from __future__ import annotations

import hashlib
import json
from math import exp, isclose, isfinite
from typing import Any

from .model import ModelValidationError


SCHEMA_VERSION = "0.1.0"
EVALUATOR_ID = "ai4heor-parametric-survival"
EVALUATOR_VERSION = "0.1.0"
MATERIALIZATION_PATH = "heor/survival-curve-materializations.json"
ANALYSIS_PATH = "heor/analysis-plan.json"
TOLERANCE = 1e-12


def validate_survival_curve_materializations(
    analysis_plan: dict[str, Any],
    analysis_raw: bytes,
    partitioned_plan: dict[str, Any],
    materializations: dict[str, Any],
    materializations_raw: bytes,
) -> dict[str, list[dict[str, Any]]]:
    """Validate and return exact target-ordered curve values."""

    value = _object(materializations, "survival curve materializations")
    _exact_keys(
        value,
        {
            "schema_version",
            "materialization_id",
            "analysis_id",
            "psm_id",
            "status",
            "base_analysis",
            "time_origin",
            "time_unit",
            "evaluator",
            "curves",
            "limitations",
        },
        "survival curve materializations",
    )
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ModelValidationError(
            f"survival materialization schema_version must be {SCHEMA_VERSION}"
        )
    for field in ("materialization_id", "analysis_id", "psm_id", "time_origin"):
        _nonempty(value.get(field), field)
    if value.get("status") != "ready_for_human_review":
        raise ModelValidationError(
            "survival materializations must be ready_for_human_review"
        )
    if value.get("analysis_id") != analysis_plan.get("analysis_id"):
        raise ModelValidationError(
            "survival materialization analysis_id does not match analysis plan"
        )
    if value.get("psm_id") != partitioned_plan.get("psm_id"):
        raise ModelValidationError(
            "survival materialization psm_id does not match partitioned plan"
        )
    if value.get("time_origin") != partitioned_plan.get("time_origin"):
        raise ModelValidationError(
            "survival materialization time_origin does not match partitioned plan"
        )
    if value.get("time_unit") != "years":
        raise ModelValidationError("survival materialization time_unit must be years")

    base = _object(value.get("base_analysis"), "base_analysis")
    _exact_keys(base, {"path", "content_sha256"}, "base_analysis")
    if base.get("path") != ANALYSIS_PATH:
        raise ModelValidationError(f"base_analysis.path must be {ANALYSIS_PATH}")
    if base.get("content_sha256") != hashlib.sha256(analysis_raw).hexdigest():
        raise ModelValidationError(
            "base_analysis.content_sha256 does not match analysis bytes"
        )
    link = _object(
        partitioned_plan.get("curve_materializations"),
        "curve_materializations",
    )
    _exact_keys(link, {"path", "content_sha256"}, "curve_materializations")
    if link.get("path") != MATERIALIZATION_PATH:
        raise ModelValidationError(
            f"curve_materializations.path must be {MATERIALIZATION_PATH}"
        )
    if link.get("content_sha256") != hashlib.sha256(materializations_raw).hexdigest():
        raise ModelValidationError(
            "curve_materializations.content_sha256 does not match materialization bytes"
        )
    evaluator = _object(value.get("evaluator"), "evaluator")
    if evaluator != {"id": EVALUATOR_ID, "version": EVALUATOR_VERSION}:
        raise ModelValidationError("survival materialization evaluator is unsupported")

    strategy_order = analysis_plan.get("strategy_order")
    cycles = analysis_plan.get("cycles")
    cycle_length = analysis_plan.get("cycle_length_years")
    if not _nonempty_strings(strategy_order):
        raise ModelValidationError("analysis strategy_order is invalid")
    if isinstance(cycles, bool) or not isinstance(cycles, int) or not 1 <= cycles <= 10_000:
        raise ModelValidationError("analysis cycles must be from 1 to 10000")
    cycle_length_years = _positive(cycle_length, "analysis cycle_length_years")
    expected_targets = [
        (strategy_id, endpoint)
        for strategy_id in strategy_order
        for endpoint in ("pfs", "os")
    ]
    curves = value.get("curves")
    if not isinstance(curves, list) or len(curves) != len(expected_targets):
        raise ModelValidationError(
            "survival materializations must contain every strategy PFS/OS curve"
        )

    output: dict[str, list[dict[str, Any]]] = {}
    psm_strategies = _object(partitioned_plan.get("strategies"), "PSM strategies")
    for index, (strategy_id, endpoint) in enumerate(expected_targets):
        curve = _object(curves[index], f"curves[{index}]")
        _exact_keys(
            curve,
            {
                "target_path",
                "strategy_id",
                "endpoint",
                "review_binding",
                "fit_output_binding",
                "family",
                "parameterization",
                "parameters",
                "basis_ids",
                "values",
            },
            f"curves[{index}]",
        )
        target = f"partitioned_survival.strategies.{strategy_id}.{endpoint}"
        if (
            curve.get("target_path") != target
            or curve.get("strategy_id") != strategy_id
            or curve.get("endpoint") != endpoint
        ):
            raise ModelValidationError(
                f"curves[{index}] does not match required target order {target}"
            )
        psm_strategy = _object(psm_strategies.get(strategy_id), strategy_id)
        psm_bindings = _object(
            psm_strategy.get("curve_review_bindings"),
            f"{strategy_id}.curve_review_bindings",
        )
        expected_review = _object(psm_bindings.get(endpoint), target)
        review_binding = _object(curve.get("review_binding"), "review_binding")
        if review_binding != expected_review:
            raise ModelValidationError(
                f"{target} review_binding does not match partitioned plan"
            )
        family = curve.get("family")
        if family not in {"exponential", "weibull"}:
            raise ModelValidationError(f"{target} family is unsupported")
        if review_binding.get("selected_family") != family:
            raise ModelValidationError(
                f"{target} family does not match Human-selected review family"
            )
        fit_binding = _object(curve.get("fit_output_binding"), "fit_output_binding")
        _exact_keys(
            fit_binding,
            {"path", "content_sha256"},
            "fit_output_binding",
        )
        _nonempty(fit_binding.get("path"), "fit_output_binding.path")
        if not _valid_sha256(fit_binding.get("content_sha256")):
            raise ModelValidationError(
                f"{target} fit_output_binding.content_sha256 is invalid"
            )
        parameterization, parameters = _parameters(curve, family, target)
        if curve.get("parameterization") != parameterization:
            raise ModelValidationError(f"{target} parameterization is unsupported")
        basis_ids = [
            f"review-sha256:{review_binding.get('content_sha256')}",
            f"fit-output-sha256:{fit_binding.get('content_sha256')}",
            f"evaluator:{EVALUATOR_ID}@{EVALUATOR_VERSION}",
        ]
        if curve.get("basis_ids") != basis_ids:
            raise ModelValidationError(f"{target} basis_ids do not match exact inputs")
        expected_values = _evaluate(
            family,
            parameters,
            cycles,
            cycle_length_years,
            target,
        )
        observed_values = curve.get("values")
        _compare_values(observed_values, expected_values, f"{target} materialization")
        psm_values = psm_strategy.get(endpoint)
        _compare_psm_values(psm_values, expected_values, basis_ids, target)
        output[target] = expected_values

    if not _nonempty_strings(value.get("limitations")):
        raise ModelValidationError(
            "survival materialization limitations must be non-empty unique strings"
        )
    serialized = json.dumps(value, ensure_ascii=False).lower()
    if any(
        field in serialized
        for field in ('"approved":', '"approval_timestamp":', '"independently_validated":')
    ):
        raise ModelValidationError(
            "survival materializations contain a forbidden authority field"
        )
    return output


def _parameters(
    curve: dict[str, Any], family: str, target: str
) -> tuple[str, dict[str, float]]:
    raw = _object(curve.get("parameters"), f"{target} parameters")
    if family == "exponential":
        expected = {"rate_per_year"}
        parameterization = "exponential_rate"
    else:
        expected = {"shape", "scale_years"}
        parameterization = "weibull_shape_scale_aft"
    _exact_keys(raw, expected, f"{target} parameters")
    return parameterization, {
        key: _positive(raw.get(key), f"{target} parameters.{key}")
        for key in sorted(expected)
    }


def _evaluate(
    family: str,
    parameters: dict[str, float],
    cycles: int,
    cycle_length_years: float,
    target: str,
) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    prior = 1.0
    for index in range(cycles + 1):
        time_years = index * cycle_length_years
        try:
            cumulative_hazard = (
                parameters["rate_per_year"] * time_years
                if family == "exponential"
                else (time_years / parameters["scale_years"]) ** parameters["shape"]
            )
            survival = exp(-cumulative_hazard)
        except (ArithmeticError, OverflowError) as error:
            raise ModelValidationError(f"{target} evaluation overflowed") from error
        if not isfinite(cumulative_hazard) or not isfinite(survival):
            raise ModelValidationError(f"{target} evaluation is non-finite")
        if survival > prior + TOLERANCE:
            raise ModelValidationError(f"{target} survival increased")
        values.append({"time_years": time_years, "survival": survival})
        prior = survival
    return values


def _compare_values(observed: Any, expected: list[dict[str, Any]], label: str) -> None:
    if not isinstance(observed, list) or len(observed) != len(expected):
        raise ModelValidationError(f"{label} values do not cover the cycle grid")
    for index, expected_row in enumerate(expected):
        row = _object(observed[index], f"{label}[{index}]")
        _exact_keys(row, {"time_years", "survival"}, f"{label}[{index}]")
        for field in ("time_years", "survival"):
            number = _number(row.get(field), f"{label}[{index}].{field}")
            if not isclose(
                number,
                float(expected_row[field]),
                rel_tol=TOLERANCE,
                abs_tol=TOLERANCE,
            ):
                raise ModelValidationError(
                    f"{label}[{index}].{field} does not match deterministic evaluation"
                )


def _compare_psm_values(
    observed: Any,
    expected: list[dict[str, Any]],
    basis_ids: list[str],
    target: str,
) -> None:
    if not isinstance(observed, list) or len(observed) != len(expected):
        raise ModelValidationError(f"{target} PSM values do not cover the cycle grid")
    for index, expected_row in enumerate(expected):
        row = _object(observed[index], f"{target} PSM[{index}]")
        if row.get("basis_ids") != basis_ids:
            raise ModelValidationError(f"{target} PSM[{index}] basis_ids do not match")
        for field in ("time_years", "survival"):
            number = _number(row.get(field), f"{target} PSM[{index}].{field}")
            if not isclose(
                number,
                float(expected_row[field]),
                rel_tol=TOLERANCE,
                abs_tol=TOLERANCE,
            ):
                raise ModelValidationError(
                    f"{target} PSM[{index}].{field} does not match materialization"
                )


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ModelValidationError(f"{label} must be an object")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ModelValidationError(f"{label} fields are not the exact supported contract")


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelValidationError(f"{label} must be a number")
    result = float(value)
    if not isfinite(result):
        raise ModelValidationError(f"{label} must be finite")
    return result


def _positive(value: Any, label: str) -> float:
    result = _number(value, label)
    if result <= 0:
        raise ModelValidationError(f"{label} must be positive")
    return result


def _nonempty(value: Any, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ModelValidationError(f"{label} must not be empty")


def _nonempty_strings(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
        and len(set(value)) == len(value)
    )


def _valid_sha256(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )
