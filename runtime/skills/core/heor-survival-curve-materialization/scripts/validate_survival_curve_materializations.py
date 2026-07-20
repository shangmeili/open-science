#!/usr/bin/env python3
"""Validate AI4HEOR survival curve materializations without dependencies."""

from __future__ import annotations

import argparse
import hashlib
import json
from math import isclose, isfinite
from pathlib import Path
import sys
from typing import Any

EXECUTION_SCRIPTS = Path(__file__).resolve().parents[2] / "heor-survival-fit-execution/scripts"
sys.path.insert(0, str(EXECUTION_SCRIPTS))
from parametric_survival import PARAMETERIZATIONS, curve as natural_curve  # noqa: E402


ANALYSIS_PATH = "heor/analysis-plan.json"
MATERIALIZATION_PATH = "heor/survival-curve-materializations.json"
EVALUATOR_ID = "ai4heor-parametric-survival"
TOLERANCE = 1e-12

TYPED_PARAMETERS = {
    "exponential": ("exponential_rate", ("rate_per_year",)),
    "weibull": ("weibull_shape_scale_aft", ("shape", "scale_years")),
    "gompertz": ("gompertz_shape_rate", ("shape_per_year", "rate_per_year")),
    "gamma": ("gamma_shape_rate", ("shape", "rate_per_year")),
    "generalized_gamma": ("generalized_gamma_prentice", ("mu_log_years", "sigma", "Q")),
    "generalized_f": ("generalized_f_prentice", ("mu_log_years", "sigma", "Q", "P")),
    "lognormal": ("lognormal_meanlog_sdlog", ("meanlog_years", "sdlog")),
    "loglogistic": ("loglogistic_shape_scale", ("shape", "scale_years")),
}
NATURAL_NAMES = {
    "exponential": ("rate",), "weibull": ("shape", "scale"),
    "gompertz": ("shape", "rate"), "gamma": ("shape", "rate"),
    "generalized_gamma": ("mu", "sigma", "Q"),
    "generalized_f": ("mu", "sigma", "Q", "P"),
    "lognormal": ("meanlog", "sdlog"), "loglogistic": ("shape", "scale"),
}


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def mapping(value: Any, name: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{name} must be an object")
        return {}
    return value


def valid_sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def nonempty_strings(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
        and len(value) == len(set(value))
    )


def positive(value: Any, name: str, errors: list[str]) -> float | None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(float(value))
        or float(value) <= 0.0
    ):
        errors.append(f"{name} must be positive and finite")
        return None
    return float(value)


def finite_number(value: Any, name: str, errors: list[str]) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
        errors.append(f"{name} must be finite")
        return None
    return float(value)


def exact_keys(
    value: dict[str, Any], expected: set[str], name: str, errors: list[str]
) -> None:
    observed = set(value)
    if observed != expected:
        errors.append(
            f"{name} fields must be exactly {sorted(expected)}; "
            f"observed {sorted(observed)}"
        )


def safe_read(
    workspace: Path | None,
    path: Any,
    digest: Any,
    name: str,
    errors: list[str],
) -> tuple[bytes, dict[str, Any]] | None:
    if workspace is None:
        errors.append(f"{name} cannot be checked without --workspace-root")
        return None
    if not isinstance(path, str) or not path.strip():
        errors.append(f"{name}.path must not be empty")
        return None
    if not valid_sha(digest):
        errors.append(f"{name}.content_sha256 must be lowercase SHA-256")
        return None
    root = workspace.resolve()
    candidate = (root / path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        errors.append(f"{name}.path escapes the workspace")
        return None
    try:
        raw = candidate.read_bytes()
    except OSError as error:
        errors.append(f"{name}.path cannot be read: {error}")
        return None
    if sha256(raw) != digest:
        errors.append(f"{name}.content_sha256 does not match artifact bytes")
        return None
    try:
        parsed = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        errors.append(f"{name}.path is not valid JSON: {error}")
        return None
    if not isinstance(parsed, dict):
        errors.append(f"{name}.path must contain a JSON object")
        return None
    return raw, parsed


def evaluate(
    family: str,
    parameters: dict[str, float],
    time_years: float,
) -> float:
    natural = dict(zip(NATURAL_NAMES[family], parameters.values()))
    return natural_curve(family, natural, time_years)[0]


def validate(
    analysis: dict[str, Any],
    analysis_raw: bytes,
    psm: dict[str, Any],
    materializations: dict[str, Any],
    materializations_raw: bytes,
    workspace: Path | None,
) -> list[str]:
    errors: list[str] = []
    schema_version = materializations.get("schema_version")
    if schema_version not in {"0.1.0", "0.2.0"}:
        errors.append("materialization schema_version must be 0.1.0 or 0.2.0")
    evaluator_version = "0.1.0" if schema_version == "0.1.0" else "0.2.0"
    for field in ("materialization_id", "analysis_id", "psm_id", "time_origin"):
        if not isinstance(materializations.get(field), str) or not materializations[field].strip():
            errors.append(f"materialization {field} must not be empty")
    if materializations.get("status") != "ready_for_human_review":
        errors.append("materialization status must be ready_for_human_review")
    if materializations.get("analysis_id") != analysis.get("analysis_id"):
        errors.append("materialization analysis_id does not match analysis plan")
    if materializations.get("psm_id") != psm.get("psm_id"):
        errors.append("materialization psm_id does not match partitioned plan")
    if materializations.get("time_origin") != psm.get("time_origin"):
        errors.append("materialization time_origin does not match partitioned plan")
    if materializations.get("time_unit") != "years":
        errors.append("materialization time_unit must be years")
    if materializations.get("evaluator") != {
        "id": EVALUATOR_ID,
        "version": evaluator_version,
    }:
        errors.append("materialization evaluator is unsupported")
    base = mapping(materializations.get("base_analysis"), "base_analysis", errors)
    if base.get("path") != ANALYSIS_PATH:
        errors.append(f"base_analysis.path must be {ANALYSIS_PATH}")
    if base.get("content_sha256") != sha256(analysis_raw):
        errors.append("base_analysis.content_sha256 does not match analysis bytes")
    link = mapping(psm.get("curve_materializations"), "curve_materializations", errors)
    if link.get("path") != MATERIALIZATION_PATH:
        errors.append(f"curve_materializations.path must be {MATERIALIZATION_PATH}")
    if link.get("content_sha256") != sha256(materializations_raw):
        errors.append("curve_materializations.content_sha256 does not match manifest bytes")

    cycles = analysis.get("cycles")
    if isinstance(cycles, bool) or not isinstance(cycles, int) or not 1 <= cycles <= 10_000:
        errors.append("analysis cycles must be from 1 to 10000")
        cycles = 0
    cycle_length = positive(
        analysis.get("cycle_length_years"), "analysis cycle_length_years", errors
    ) or 1.0
    strategy_order = analysis.get("strategy_order")
    if not nonempty_strings(strategy_order):
        errors.append("analysis strategy_order is invalid")
        strategy_order = []
    expected_targets = [
        (strategy_id, endpoint)
        for strategy_id in strategy_order
        for endpoint in ("pfs", "os")
    ]
    curves = materializations.get("curves")
    if not isinstance(curves, list) or len(curves) != len(expected_targets):
        errors.append("manifest must contain every strategy PFS/OS curve in order")
        curves = []
    psm_strategies = mapping(psm.get("strategies"), "PSM strategies", errors)

    for index, (strategy_id, endpoint) in enumerate(expected_targets):
        if index >= len(curves):
            break
        name = f"curves[{index}]"
        curve = mapping(curves[index], name, errors)
        exact_keys(
            curve,
            {
                "target_path", "strategy_id", "endpoint", "review_binding",
                "fit_output_binding", "family", "parameterization", "parameters",
                "basis_ids", "values",
            },
            name,
            errors,
        )
        target = f"partitioned_survival.strategies.{strategy_id}.{endpoint}"
        if (
            curve.get("target_path") != target
            or curve.get("strategy_id") != strategy_id
            or curve.get("endpoint") != endpoint
        ):
            errors.append(f"{name} does not match required target {target}")
        psm_strategy = mapping(psm_strategies.get(strategy_id), strategy_id, errors)
        psm_bindings = mapping(
            psm_strategy.get("curve_review_bindings"),
            f"{strategy_id}.curve_review_bindings",
            errors,
        )
        expected_review = mapping(psm_bindings.get(endpoint), target, errors)
        review_binding = mapping(curve.get("review_binding"), f"{name}.review_binding", errors)
        if review_binding != expected_review:
            errors.append(f"{target} review binding does not match partitioned plan")
        if review_binding.get("target_path") != target:
            errors.append(f"{target} review target_path does not match")

        family = curve.get("family")
        admitted = {"exponential", "weibull"} if schema_version == "0.1.0" else set(TYPED_PARAMETERS)
        if family not in admitted:
            errors.append(f"{target} family is unsupported")
            family = ""
        if review_binding.get("selected_family") != family:
            errors.append(f"{target} family does not match Human-selected family")
        fit_binding = mapping(
            curve.get("fit_output_binding"), f"{name}.fit_output_binding", errors
        )
        exact_keys(fit_binding, {"path", "content_sha256"}, f"{name}.fit_output_binding", errors)

        review_loaded = safe_read(
            workspace,
            review_binding.get("path"),
            review_binding.get("content_sha256"),
            f"{target} review",
            errors,
        )
        selected_model: dict[str, Any] = {}
        if review_loaded:
            review = review_loaded[1]
            expected_review_schema = "0.2.0" if schema_version == "0.1.0" else "0.3.0"
            if review.get("schema_version") != expected_review_schema:
                errors.append(f"{target} review schema_version must be {expected_review_schema}")
            if review.get("status") != "ready_for_human_review":
                errors.append(f"{target} review must be ready_for_human_review")
            if review.get("analysis_target") != {
                "analysis_id": analysis.get("analysis_id"),
                "path": target,
            }:
                errors.append(f"{target} review analysis_target does not match")
            context = mapping(review.get("context"), f"{target} review context", errors)
            if context.get("endpoint") != endpoint.upper():
                errors.append(f"{target} review endpoint does not match")
            if context.get("time_origin") != psm.get("time_origin"):
                errors.append(f"{target} review time_origin does not match")
            if context.get("time_unit") != "years":
                errors.append(f"{target} review time_unit must be years")
            models = review.get("models")
            matches = (
                [model for model in models if isinstance(model, dict) and model.get("family") == family]
                if isinstance(models, list)
                else []
            )
            if len(matches) != 1:
                errors.append(f"{target} review must contain exactly one selected family model")
            else:
                selected_model = matches[0]
                if selected_model.get("status") != "converged":
                    errors.append(f"{target} selected review model must be converged")
                if selected_model.get("parameterization") != curve.get("parameterization"):
                    errors.append(f"{target} selected review parameterization does not match")
                if (
                    selected_model.get("fit_output_path") != fit_binding.get("path")
                    or selected_model.get("fit_output_sha256") != fit_binding.get("content_sha256")
                ):
                    errors.append(f"{target} selected review fit-output binding does not match")

        fit_loaded = safe_read(
            workspace,
            fit_binding.get("path"),
            fit_binding.get("content_sha256"),
            f"{target} fit output",
            errors,
        )
        expected_parameterization, parameter_order = TYPED_PARAMETERS.get(family, ("", ()))
        expected_parameter_names = set(parameter_order)
        parameters_raw = mapping(curve.get("parameters"), f"{target} parameters", errors)
        if set(parameters_raw) != expected_parameter_names:
            errors.append(f"{target} parameter fields are unsupported")
        parameters: dict[str, float] = {}
        for key in sorted(expected_parameter_names):
            label = f"{target} parameters.{key}"
            if key == "P":
                value = finite_number(parameters_raw.get(key), label, errors)
                if value is not None and value < 0:
                    errors.append(f"{label} must be non-negative")
                    value = None
            elif key in {"shape_per_year", "mu_log_years", "meanlog_years", "Q"}:
                value = finite_number(parameters_raw.get(key), label, errors)
            else:
                value = positive(parameters_raw.get(key), label, errors)
            if value is not None:
                parameters[key] = value
        if curve.get("parameterization") != expected_parameterization:
            errors.append(f"{target} parameterization is unsupported")
        if fit_loaded and schema_version == "0.1.0":
            fit = fit_loaded[1]
            exact_keys(
                fit,
                {"schema_version", "family", "parameterization", "time_unit", "parameters"},
                f"{target} fit output",
                errors,
            )
            if fit.get("schema_version") != "0.1.0":
                errors.append(f"{target} fit-output schema_version must be 0.1.0")
            if fit.get("family") != family:
                errors.append(f"{target} fit-output family does not match")
            if fit.get("parameterization") != expected_parameterization:
                errors.append(f"{target} fit-output parameterization does not match")
            if fit.get("time_unit") != "years":
                errors.append(f"{target} fit-output time_unit must be years")
            if fit.get("parameters") != curve.get("parameters"):
                errors.append(f"{target} manifest parameters do not match fit-output bytes")
        elif fit_loaded:
            fit = fit_loaded[1]
            exact_keys(
                fit,
                {"schema_version", "family", "status", "fit_statistics", "parameterization", "parameters", "landmarks", "warnings"},
                f"{target} normalized fit output",
                errors,
            )
            if fit.get("schema_version") != "0.1.0" or fit.get("family") != family or fit.get("status") != "converged":
                errors.append(f"{target} normalized fit output identity is invalid")
            if fit.get("parameterization") != expected_parameterization:
                errors.append(f"{target} normalized fit parameterization does not match")
            rows = fit.get("parameters")
            natural_names = NATURAL_NAMES.get(family, ())
            natural: dict[str, float] = {}
            if not isinstance(rows, list) or len(rows) != len(natural_names):
                errors.append(f"{target} normalized fit parameters are incomplete")
            else:
                for row, expected_name in zip(rows, natural_names):
                    item = mapping(row, f"{target} normalized parameter", errors)
                    exact_keys(item, {"name", "estimate"}, f"{target} normalized parameter", errors)
                    estimate = finite_number(item.get("estimate"), f"{target} normalized parameter estimate", errors)
                    if item.get("name") != expected_name:
                        errors.append(f"{target} normalized parameter order does not match")
                    elif estimate is not None:
                        natural[expected_name] = estimate
            typed_as_natural = dict(zip(natural_names, (parameters.get(name) for name in parameter_order)))
            if natural != typed_as_natural:
                errors.append(f"{target} manifest parameters do not match normalized fit-output bytes")

        basis = [
            f"review-sha256:{review_binding.get('content_sha256')}",
            f"fit-output-sha256:{fit_binding.get('content_sha256')}",
            f"evaluator:{EVALUATOR_ID}@{evaluator_version}",
        ]
        if curve.get("basis_ids") != basis:
            errors.append(f"{target} basis_ids do not match exact inputs")
        values = curve.get("values")
        if not isinstance(values, list) or len(values) != cycles + 1:
            errors.append(f"{target} values must contain cycles + 1 rows")
            values = []
        psm_values = psm_strategy.get(endpoint)
        duration_derived = psm.get("schema_version") in {"0.4.0", "0.5.0", "0.6.0", "0.7.0"}
        if not duration_derived and (not isinstance(psm_values, list) or len(psm_values) != cycles + 1):
            errors.append(f"{target} PSM values must contain cycles + 1 rows")
            psm_values = []
        if len(parameters) == len(expected_parameter_names):
            for value_index in range(cycles + 1):
                expected_time = value_index * cycle_length
                ordered_parameters = {name: parameters[name] for name in parameter_order}
                expected_survival = evaluate(family, ordered_parameters, expected_time)
                rows_to_check = [(values, "materialization", False)]
                if not duration_derived:
                    rows_to_check.append((psm_values, "PSM", True))
                for rows, row_name, needs_basis in rows_to_check:
                    if value_index >= len(rows):
                        continue
                    row = mapping(rows[value_index], f"{target} {row_name}[{value_index}]", errors)
                    time = row.get("time_years")
                    observed = row.get("survival")
                    if (
                        isinstance(time, bool)
                        or not isinstance(time, (int, float))
                        or not isclose(float(time), expected_time, rel_tol=0.0, abs_tol=TOLERANCE)
                    ):
                        errors.append(f"{target} {row_name}[{value_index}] time grid mismatch")
                    if (
                        isinstance(observed, bool)
                        or not isinstance(observed, (int, float))
                        or not isfinite(float(observed))
                        or not isclose(
                            float(observed), expected_survival,
                            rel_tol=TOLERANCE, abs_tol=TOLERANCE,
                        )
                    ):
                        errors.append(
                            f"{target} {row_name}[{value_index}] does not match deterministic evaluation"
                        )
                    if needs_basis and row.get("basis_ids") != basis:
                        errors.append(f"{target} PSM[{value_index}] basis_ids do not match")

    if not nonempty_strings(materializations.get("limitations")):
        errors.append("materialization limitations must be non-empty unique strings")
    forbidden = json.dumps(materializations, ensure_ascii=False).lower()
    for phrase in ('"approved":', '"approval_timestamp":', '"independently_validated":'):
        if phrase in forbidden:
            errors.append(f"manifest contains forbidden authority field {phrase[:-1]}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis_plan", type=Path)
    parser.add_argument("partitioned_survival_plan", type=Path)
    parser.add_argument("materializations", type=Path)
    parser.add_argument("--workspace-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        analysis_raw = args.analysis_plan.read_bytes()
        psm_raw = args.partitioned_survival_plan.read_bytes()
        materializations_raw = args.materializations.read_bytes()
        analysis = json.loads(analysis_raw)
        psm = json.loads(psm_raw)
        materializations = json.loads(materializations_raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        print(f"INVALID: {error}")
        return 1
    errors = validate(
        analysis, analysis_raw, psm, materializations, materializations_raw,
        args.workspace_root,
    )
    if errors:
        for error in errors:
            print(f"INVALID: {error}")
        return 1
    print(
        f"VALID: survival curve materializations {materializations.get('schema_version')}; "
        f"analysis_sha256={sha256(analysis_raw)}; "
        f"psm_sha256={sha256(psm_raw)}; "
        f"materializations_sha256={sha256(materializations_raw)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
