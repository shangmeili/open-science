#!/usr/bin/env python3
"""Validate an AI4HEOR partitioned survival plan without dependencies."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from math import isclose, isfinite
from pathlib import Path
from typing import Any


TOLERANCE = 1e-9
PLAN_PATH = "heor/partitioned-survival-plan.json"
ANALYSIS_PATH = "heor/analysis-plan.json"
STATE_ORDER = ["progression_free", "progressed", "dead"]


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def mapping(value: Any, name: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{name} must be an object")
        return {}
    return value


def nonempty_strings(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
        and len(set(value)) == len(value)
    )


def valid_sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


def review_binding_valid(
    binding: dict[str, Any],
    workspace: Path | None,
    name: str,
    analysis_id: str,
    expected_target: str,
    expected_endpoint: str,
    expected_time_origin: str,
    errors: list[str],
) -> None:
    path = binding.get("path")
    digest = binding.get("content_sha256")
    target_path = binding.get("target_path")
    selected_family = binding.get("selected_family")
    if not isinstance(path, str) or not path.strip():
        errors.append(f"{name}.path must not be empty")
        return
    if not valid_sha(digest):
        errors.append(f"{name}.content_sha256 must be lowercase SHA-256")
        return
    if target_path != expected_target:
        errors.append(f"{name}.target_path must be {expected_target}")
    if not isinstance(selected_family, str) or not selected_family.strip():
        errors.append(f"{name}.selected_family must not be empty")
    if workspace is None:
        return
    root = workspace.resolve()
    candidate = (root / path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        errors.append(f"{name}.path escapes the workspace")
        return
    try:
        raw = candidate.read_bytes()
    except OSError as error:
        errors.append(f"{name}.path cannot be read: {error}")
        return
    if sha256(raw) != digest:
        errors.append(f"{name}.content_sha256 does not match the artifact bytes")
        return
    try:
        review = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        errors.append(f"{name}.path is not valid JSON: {error}")
        return
    if review.get("schema_version") != "0.2.0":
        errors.append(f"{name} review schema_version must be 0.2.0")
    if review.get("status") != "ready_for_human_review":
        errors.append(f"{name} review status must be ready_for_human_review")
    if review.get("analysis_target") != {
        "analysis_id": analysis_id,
        "path": expected_target,
    }:
        errors.append(f"{name} review analysis_target does not match")
    if (review.get("context") or {}).get("endpoint") != expected_endpoint:
        errors.append(f"{name} review endpoint does not match {expected_endpoint}")
    if (review.get("context") or {}).get("time_origin") != expected_time_origin:
        errors.append(f"{name} review time_origin does not match")
    if (review.get("context") or {}).get("time_unit") != "years":
        errors.append(f"{name} review time_unit must be years")


def validate(
    analysis: dict[str, Any],
    analysis_raw: bytes,
    plan: dict[str, Any],
    workspace: Path | None,
) -> list[str]:
    errors: list[str] = []
    if plan.get("schema_version") != "0.2.0":
        errors.append("schema_version must be 0.2.0")
    for field in ("psm_id", "analysis_id", "time_origin"):
        if not isinstance(plan.get(field), str) or not plan[field].strip():
            errors.append(f"{field} must not be empty")
    if plan.get("status") != "ready_for_human_review":
        errors.append("status must be ready_for_human_review")
    if plan.get("analysis_id") != analysis.get("analysis_id"):
        errors.append("analysis_id does not match analysis plan")
    base = mapping(plan.get("base_analysis"), "base_analysis", errors)
    if base.get("path") != ANALYSIS_PATH:
        errors.append(f"base_analysis.path must be {ANALYSIS_PATH}")
    if base.get("content_sha256") != sha256(analysis_raw):
        errors.append("base_analysis.content_sha256 does not match analysis bytes")
    if (analysis.get("partitioned_survival_analysis") or {}).get("path") != PLAN_PATH:
        errors.append(f"analysis plan must link {PLAN_PATH}")
    if analysis.get("states") != STATE_ORDER:
        errors.append("analysis states must be progression_free, progressed, dead")

    structure = mapping(plan.get("model_structure"), "model_structure", errors)
    if structure.get("type") != "partitioned_survival":
        errors.append("model_structure.type must be partitioned_survival")
    if structure.get("state_order") != STATE_ORDER:
        errors.append("model_structure.state_order is invalid")
    if structure.get("forward_only_disease_process") is not True:
        errors.append("forward_only_disease_process must be true")

    conceptual = mapping(plan.get("conceptual_basis"), "conceptual_basis", errors)
    for field in (
        "forward_only_process",
        "population_alignment",
        "endpoint_alignment",
        "time_origin_alignment",
        "independent_extrapolation",
    ):
        item = mapping(conceptual.get(field), f"conceptual_basis.{field}", errors)
        if not isinstance(item.get("rationale"), str) or not item["rationale"].strip():
            errors.append(f"conceptual_basis.{field}.rationale must not be empty")
        if not nonempty_strings(item.get("basis_ids")):
            errors.append(f"conceptual_basis.{field}.basis_ids is invalid")

    cycles = analysis.get("cycles")
    cycle_length = analysis.get("cycle_length_years")
    if isinstance(cycles, bool) or not isinstance(cycles, int) or cycles <= 0:
        errors.append("analysis cycles must be a positive integer")
        cycles = 0
    if (
        isinstance(cycle_length, bool)
        or not isinstance(cycle_length, (int, float))
        or not isfinite(float(cycle_length))
        or cycle_length <= 0
    ):
        errors.append("analysis cycle_length_years must be positive and finite")
        cycle_length = 1.0
    strategy_order = analysis.get("strategy_order")
    if not nonempty_strings(strategy_order):
        strategy_order = ["comparator", "intervention"]
    strategies = mapping(plan.get("strategies"), "strategies", errors)
    if set(strategies) != set(strategy_order):
        errors.append("strategies must match analysis strategy_order exactly")
    for strategy_id in strategy_order:
        curves = mapping(strategies.get(strategy_id), f"strategies.{strategy_id}", errors)
        observed: dict[str, list[float]] = {}
        for endpoint in ("pfs", "os"):
            rows = curves.get(endpoint)
            if not isinstance(rows, list) or len(rows) != cycles + 1:
                errors.append(
                    f"strategies.{strategy_id}.{endpoint} must contain cycles + 1 rows"
                )
                continue
            values: list[float] = []
            prior = 1.0
            for index, raw_row in enumerate(rows):
                row = mapping(
                    raw_row, f"strategies.{strategy_id}.{endpoint}[{index}]", errors
                )
                time = row.get("time_years")
                survival = row.get("survival")
                if (
                    isinstance(time, bool)
                    or not isinstance(time, (int, float))
                    or not isfinite(float(time))
                    or not isclose(
                        float(time),
                        index * float(cycle_length),
                        rel_tol=0.0,
                        abs_tol=TOLERANCE,
                    )
                ):
                    errors.append(
                        f"strategies.{strategy_id}.{endpoint}[{index}] time grid mismatch"
                    )
                if (
                    isinstance(survival, bool)
                    or not isinstance(survival, (int, float))
                    or not isfinite(float(survival))
                    or not 0.0 <= float(survival) <= 1.0
                ):
                    errors.append(
                        f"strategies.{strategy_id}.{endpoint}[{index}] survival is invalid"
                    )
                    continue
                value = float(survival)
                if index == 0 and not isclose(value, 1.0, abs_tol=TOLERANCE):
                    errors.append(
                        f"strategies.{strategy_id}.{endpoint} must equal 1 at time zero"
                    )
                if value > prior + TOLERANCE:
                    errors.append(
                        f"strategies.{strategy_id}.{endpoint} must be non-increasing"
                    )
                if not nonempty_strings(row.get("basis_ids")):
                    errors.append(
                        f"strategies.{strategy_id}.{endpoint}[{index}].basis_ids is invalid"
                    )
                prior = value
                values.append(value)
            observed[endpoint] = values
        if set(observed) == {"pfs", "os"}:
            for index, (pfs, overall) in enumerate(
                zip(observed["pfs"], observed["os"])
            ):
                if pfs > overall + TOLERANCE:
                    errors.append(
                        f"strategies.{strategy_id} PFS exceeds OS at endpoint {index}"
                    )
        bindings = mapping(
            curves.get("curve_review_bindings"),
            f"strategies.{strategy_id}.curve_review_bindings",
            errors,
        )
        for endpoint in ("pfs", "os"):
            binding = mapping(
                bindings.get(endpoint),
                f"strategies.{strategy_id}.curve_review_bindings.{endpoint}",
                errors,
            )
            review_binding_valid(
                binding,
                workspace,
                f"strategies.{strategy_id}.curve_review_bindings.{endpoint}",
                str(plan.get("analysis_id", "")),
                f"partitioned_survival.strategies.{strategy_id}.{endpoint}",
                endpoint.upper(),
                str(plan.get("time_origin", "")),
                errors,
            )

    validation = mapping(plan.get("validation_plan"), "validation_plan", errors)
    for field in ("face", "internal", "external"):
        if not nonempty_strings(validation.get(field)):
            errors.append(f"validation_plan.{field} is invalid")
    if not nonempty_strings(plan.get("limitations")):
        errors.append("limitations must be a non-empty array of unique strings")
    forbidden = json.dumps(plan, ensure_ascii=False).lower()
    for phrase in ('"approved":', '"approval_timestamp":', '"independently_validated":'):
        if phrase in forbidden:
            errors.append(f"plan contains forbidden authority field {phrase[:-1]}")
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
        plan_raw = args.partitioned_survival_plan.read_bytes()
        materializations_raw = args.materializations.read_bytes()
        analysis = json.loads(analysis_raw)
        plan = json.loads(plan_raw)
        materializations = json.loads(materializations_raw)
    except (OSError, json.JSONDecodeError) as error:
        print(f"INVALID: {error}")
        return 1
    errors = validate(analysis, analysis_raw, plan, args.workspace_root)
    validator_path = (
        Path(__file__).resolve().parents[2]
        / "heor-survival-curve-materialization/scripts"
        / "validate_survival_curve_materializations.py"
    )
    spec = importlib.util.spec_from_file_location(
        "ai4heor_survival_materialization_validator", validator_path
    )
    if spec is None or spec.loader is None:
        errors.append("survival materialization validator cannot be loaded")
    else:
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        errors.extend(
            module.validate(
                analysis,
                analysis_raw,
                plan,
                materializations,
                materializations_raw,
                args.workspace_root,
            )
        )
    if errors:
        for error in errors:
            print(f"INVALID: {error}")
        return 1
    print(
        "VALID: partitioned survival plan 0.2.0; "
        f"analysis_sha256={sha256(analysis_raw)}; "
        f"plan_sha256={sha256(plan_raw)}; "
        f"materializations_sha256={sha256(materializations_raw)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
