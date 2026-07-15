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
    duration_raw: bytes | None = None,
    cost_raw: bytes | None = None,
    utility_raw: bytes | None = None,
    event_raw: bytes | None = None,
) -> list[str]:
    errors: list[str] = []
    psm_schema = plan.get("schema_version")
    analysis_schema = analysis.get("schema_version")
    if psm_schema not in {"0.2.0", "0.3.0", "0.4.0", "0.5.0", "0.6.0", "0.7.0"}:
        errors.append("schema_version must be 0.2.0 through 0.7.0")
    if psm_schema in {"0.3.0", "0.4.0"} and analysis_schema != "0.12.0":
        errors.append("partitioned survival schema 0.3.0 or 0.4.0 requires analysis schema 0.12.0")
    if analysis_schema == "0.12.0" and psm_schema not in {"0.3.0", "0.4.0"}:
        errors.append("analysis schema 0.12.0 requires partitioned survival schema 0.3.0 or 0.4.0")
    if psm_schema == "0.5.0" and analysis_schema != "0.13.0":
        errors.append("partitioned survival schema 0.5.0 requires analysis schema 0.13.0")
    if analysis_schema == "0.13.0" and psm_schema != "0.5.0":
        errors.append("analysis schema 0.13.0 requires partitioned survival schema 0.5.0")
    if psm_schema == "0.6.0" and analysis_schema != "0.14.0":
        errors.append("partitioned survival schema 0.6.0 requires analysis schema 0.14.0")
    if analysis_schema == "0.14.0" and psm_schema != "0.6.0":
        errors.append("analysis schema 0.14.0 requires partitioned survival schema 0.6.0")
    if psm_schema == "0.7.0" and analysis_schema != "0.15.0":
        errors.append("partitioned survival schema 0.7.0 requires analysis schema 0.15.0")
    if analysis_schema == "0.15.0" and psm_schema != "0.7.0":
        errors.append("analysis schema 0.15.0 requires partitioned survival schema 0.7.0")
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
    duration_binding = plan.get("treatment_effect_duration")
    if psm_schema in {"0.4.0", "0.5.0", "0.6.0", "0.7.0"}:
        if duration_raw is None:
            errors.append("schema 0.4.0 through 0.7.0 requires --treatment-effect-duration")
        elif not isinstance(duration_binding, dict) or set(duration_binding) != {"path", "content_sha256"}:
            errors.append("treatment_effect_duration must contain only path and content_sha256")
        elif duration_binding.get("path") != "heor/treatment-effect-duration.json" or duration_binding.get("content_sha256") != sha256(duration_raw):
            errors.append("treatment_effect_duration does not bind the current artifact bytes")
    elif duration_binding is not None or duration_raw is not None:
        errors.append("treatment-effect duration requires partitioned survival schema 0.4.0 through 0.7.0")
    cost_binding = plan.get("cost_input_normalization")
    if psm_schema in {"0.5.0", "0.6.0", "0.7.0"}:
        if cost_raw is None:
            errors.append("schema 0.5.0 through 0.7.0 requires --cost-input-normalization")
        elif not isinstance(cost_binding, dict) or set(cost_binding) != {"path", "content_sha256"}:
            errors.append("cost_input_normalization must contain only path and content_sha256")
        elif cost_binding.get("path") != "heor/cost-input-normalization.json" or cost_binding.get("content_sha256") != sha256(cost_raw):
            errors.append("cost_input_normalization does not bind the current artifact bytes")
    elif cost_binding is not None or cost_raw is not None:
        errors.append("cost-input normalization requires partitioned survival schema 0.5.0 through 0.7.0")
    utility_binding = plan.get("utility_inputs")
    if psm_schema in {"0.6.0", "0.7.0"}:
        if utility_raw is None:
            errors.append("schema 0.6.0 or 0.7.0 requires --utility-inputs")
        elif not isinstance(utility_binding, dict) or set(utility_binding) != {"path", "content_sha256"}:
            errors.append("utility_inputs must contain only path and content_sha256")
        elif utility_binding.get("path") != "heor/utility-inputs.json" or utility_binding.get("content_sha256") != sha256(utility_raw):
            errors.append("utility_inputs does not bind the current artifact bytes")
    elif utility_binding is not None or utility_raw is not None:
        errors.append("utility inputs require partitioned survival schema 0.6.0 or 0.7.0")
    event_binding = plan.get("event_disutilities")
    if psm_schema == "0.7.0":
        if event_raw is None:
            errors.append("schema 0.7.0 requires --event-disutilities")
        elif not isinstance(event_binding, dict) or set(event_binding) != {"path", "content_sha256"}:
            errors.append("event_disutilities must contain only path and content_sha256")
        elif event_binding.get("path") != "heor/event-disutilities.json" or event_binding.get("content_sha256") != sha256(event_raw):
            errors.append("event_disutilities does not bind the current artifact bytes")
    elif event_binding is not None or event_raw is not None:
        errors.append("event disutilities require partitioned survival schema 0.7.0")
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
    parser.add_argument("--treatment-effect-duration", type=Path)
    parser.add_argument("--cost-input-normalization", type=Path)
    parser.add_argument("--utility-inputs", type=Path)
    parser.add_argument("--event-disutilities", type=Path)
    parser.add_argument("--workspace-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        analysis_raw = args.analysis_plan.read_bytes()
        plan_raw = args.partitioned_survival_plan.read_bytes()
        materializations_raw = args.materializations.read_bytes()
        analysis = json.loads(analysis_raw)
        plan = json.loads(plan_raw)
        materializations = json.loads(materializations_raw)
        duration_raw = (
            args.treatment_effect_duration.read_bytes()
            if args.treatment_effect_duration is not None
            else None
        )
        cost_raw = (
            args.cost_input_normalization.read_bytes()
            if args.cost_input_normalization is not None
            else None
        )
        utility_raw = (
            args.utility_inputs.read_bytes()
            if args.utility_inputs is not None
            else None
        )
        event_raw = (
            args.event_disutilities.read_bytes()
            if args.event_disutilities is not None
            else None
        )
    except (OSError, json.JSONDecodeError) as error:
        print(f"INVALID: {error}")
        return 1
    errors = validate(
        analysis, analysis_raw, plan, args.workspace_root, duration_raw, cost_raw, utility_raw, event_raw
    )
    if analysis.get("schema_version") in {"0.12.0", "0.13.0", "0.14.0", "0.15.0"}:
        economic_validator_path = (
            Path(__file__).resolve().parents[2]
            / "heor-economic-inputs/scripts"
            / "validate_economic_inputs.py"
        )
        economic_spec = importlib.util.spec_from_file_location(
            "ai4heor_economic_input_validator", economic_validator_path
        )
        if economic_spec is None or economic_spec.loader is None:
            errors.append("economic input validator cannot be loaded")
        else:
            economic_module = importlib.util.module_from_spec(economic_spec)
            economic_spec.loader.exec_module(economic_module)
            errors.extend(economic_module.validate(analysis))
    if analysis.get("schema_version") in {"0.13.0", "0.14.0", "0.15.0"} and cost_raw is not None:
        cost_validator_path = (
            Path(__file__).resolve().parents[2]
            / "heor-cost-input-normalization/scripts"
            / "validate_cost_input_normalization.py"
        )
        cost_spec = importlib.util.spec_from_file_location(
            "ai4heor_cost_input_validator", cost_validator_path
        )
        if cost_spec is None or cost_spec.loader is None:
            errors.append("cost-input normalization validator cannot be loaded")
        else:
            cost_module = importlib.util.module_from_spec(cost_spec)
            cost_spec.loader.exec_module(cost_module)
            try:
                cost_value = json.loads(cost_raw)
            except json.JSONDecodeError as error:
                errors.append(f"cost-input normalization is invalid JSON: {error}")
            else:
                errors.extend(cost_module.validate(analysis, analysis_raw, cost_value))
    if analysis.get("schema_version") in {"0.14.0", "0.15.0"} and utility_raw is not None:
        utility_validator_path = (
            Path(__file__).resolve().parents[2]
            / "heor-utility-inputs/scripts"
            / "validate_utility_inputs.py"
        )
        utility_spec = importlib.util.spec_from_file_location(
            "ai4heor_utility_input_validator", utility_validator_path
        )
        if utility_spec is None or utility_spec.loader is None:
            errors.append("utility-input validator cannot be loaded")
        else:
            utility_module = importlib.util.module_from_spec(utility_spec)
            utility_spec.loader.exec_module(utility_module)
            try:
                utility_value = json.loads(utility_raw)
            except json.JSONDecodeError as error:
                errors.append(f"utility inputs are invalid JSON: {error}")
            else:
                errors.extend(utility_module.validate(analysis, analysis_raw, utility_value))
    if analysis.get("schema_version") == "0.15.0" and utility_raw is not None and event_raw is not None:
        event_validator_path = (
            Path(__file__).resolve().parents[2]
            / "heor-event-disutilities/scripts"
            / "validate_event_disutilities.py"
        )
        event_spec = importlib.util.spec_from_file_location(
            "ai4heor_event_disutility_validator", event_validator_path
        )
        if event_spec is None or event_spec.loader is None:
            errors.append("event-disutility validator cannot be loaded")
        else:
            event_module = importlib.util.module_from_spec(event_spec)
            event_spec.loader.exec_module(event_module)
            try:
                utility_value = json.loads(utility_raw)
                event_value = json.loads(event_raw)
            except json.JSONDecodeError as error:
                errors.append(f"event-disutility dependency is invalid JSON: {error}")
            else:
                errors.extend(
                    event_module.validate(
                        analysis,
                        analysis_raw,
                        utility_value,
                        utility_raw,
                        event_value,
                    )
                )
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
        f"VALID: partitioned survival plan {plan.get('schema_version')}; "
        f"analysis_sha256={sha256(analysis_raw)}; "
        f"plan_sha256={sha256(plan_raw)}; "
        f"materializations_sha256={sha256(materializations_raw)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
