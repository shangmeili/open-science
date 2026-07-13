#!/usr/bin/env python3
"""Portable structural validator for an AI4HEOR uncertainty plan."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path


SHA256 = re.compile(r"^[a-f0-9]{64}$")
PARAMETER_TARGET = re.compile(
    r"^/strategies/(comparator|intervention)/(state_costs|state_utilities)/[0-9]+$"
    r"|^/strategies/(comparator|intervention)/transition_matrix/[0-9]+$"
)
SCENARIO_TARGETS = {
    "/cycles",
    "/cycle_length_years",
    "/discount_rates/costs",
    "/discount_rates/outcomes",
    "/half_cycle_correction",
}
SUPPORTED_DISTRIBUTIONS = {"beta", "gamma", "lognormal", "uniform", "dirichlet"}


def load(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value, raw


def text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def string_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(text(item) for item in value)
        and len(set(value)) == len(value)
    )


def finite_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def positive_number(value: object) -> bool:
    return finite_number(value) and value > 0


def resolve_pointer(value: object, pointer: str) -> object:
    current = value
    for token in pointer[1:].split("/"):
        token = token.replace("~1", "/").replace("~0", "~")
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def simplex(value: object, length: int) -> bool:
    return (
        isinstance(value, list)
        and len(value) == length
        and all(finite_number(item) and 0 <= item <= 1 for item in value)
        and abs(sum(value) - 1) <= 1e-9
    )


def replacement_compatible(base: object, replacement: object) -> bool:
    if isinstance(base, bool):
        return isinstance(replacement, bool)
    if isinstance(base, int):
        return isinstance(replacement, int) and not isinstance(replacement, bool)
    if finite_number(base):
        return finite_number(replacement)
    if isinstance(base, list):
        return simplex(replacement, len(base))
    return False


def distribution_valid(value: object, base: object) -> bool:
    if not isinstance(value, dict):
        return False
    kind = value.get("type")
    if kind == "beta":
        return not isinstance(base, list) and positive_number(value.get("alpha")) and positive_number(value.get("beta"))
    if kind == "gamma":
        return not isinstance(base, list) and positive_number(value.get("shape")) and positive_number(value.get("scale"))
    if kind == "lognormal":
        return not isinstance(base, list) and finite_number(value.get("mu_log")) and positive_number(value.get("sigma_log"))
    if kind == "uniform":
        return not isinstance(base, list) and finite_number(value.get("low")) and finite_number(value.get("high")) and value["low"] < value["high"]
    if kind == "dirichlet":
        alpha = value.get("alpha")
        return isinstance(base, list) and isinstance(alpha, list) and len(alpha) == len(base) and all(positive_number(item) for item in alpha)
    return False


def validate(uncertainty_path: Path, plan_path: Path) -> list[str]:
    value, _ = load(uncertainty_path)
    plan, plan_raw = load(plan_path)
    errors: list[str] = []
    if value.get("schema_version") != "0.1.0":
        errors.append("schema_version must be 0.1.0")
    for field in ("uncertainty_id", "analysis_id"):
        if not text(value.get(field)):
            errors.append(f"{field} is required")
    if value.get("status") != "ready_for_human_review":
        errors.append("status must be ready_for_human_review")
    if value.get("analysis_id") != plan.get("analysis_id"):
        errors.append("analysis_id does not match the plan")
    base = value.get("base_analysis") or {}
    if base.get("path") != "heor/analysis-plan.json":
        errors.append("base_analysis.path must be heor/analysis-plan.json")
    expected_hash = hashlib.sha256(plan_raw).hexdigest()
    if base.get("content_sha256") != expected_hash or not SHA256.fullmatch(
        str(base.get("content_sha256", ""))
    ):
        errors.append("base_analysis.content_sha256 does not match the plan bytes")
    link = plan.get("uncertainty_analysis") or {}
    if link.get("path") != "heor/uncertainty-plan.json":
        errors.append("plan must link heor/uncertainty-plan.json")
    seed = value.get("seed")
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**64:
        errors.append("seed must be an unsigned 64-bit integer")
    if not positive_number(plan.get("willingness_to_pay")):
        errors.append("plan willingness_to_pay must be positive")

    mappings = {
        item.get("path"): item
        for item in plan.get("input_provenance", [])
        if isinstance(item, dict) and text(item.get("path"))
    }
    methodology = ((plan.get("methodology") or {}).get("uncertainty_analysis") or {})
    dsa_paths = set(((methodology.get("deterministic") or {}).get("input_paths") or []))
    psa_paths = set(((methodology.get("probabilistic") or {}).get("input_paths") or []))
    if (methodology.get("deterministic") or {}).get("planned") is not True:
        errors.append("plan deterministic uncertainty analysis must be planned")
    if (methodology.get("probabilistic") or {}).get("planned") is not True:
        errors.append("plan probabilistic uncertainty analysis must be planned")
    parameters = value.get("parameters")
    if not isinstance(parameters, list) or not 1 <= len(parameters) <= 256:
        errors.append("parameters must contain from 1 to 256 entries")
        parameters = []
    ids: set[str] = set()
    targets: set[str] = set()
    for index, parameter in enumerate(parameters):
        label = f"parameters[{index}]"
        if not isinstance(parameter, dict):
            errors.append(f"{label} must be an object")
            continue
        identifier = parameter.get("id")
        target = parameter.get("target")
        if not text(identifier) or identifier in ids:
            errors.append(f"{label}.id must be non-empty and unique")
        else:
            ids.add(identifier)
        if not text(target) or not PARAMETER_TARGET.fullmatch(target) or target in targets:
            errors.append(f"{label}.target must be unique and allowlisted")
            base_value = None
        else:
            targets.add(target)
            try:
                base_value = resolve_pointer(plan, target)
            except (KeyError, IndexError, TypeError, ValueError):
                base_value = None
                errors.append(f"{label}.target does not exist in the plan")
        provenance_path = parameter.get("provenance_path")
        mapping = mappings.get(provenance_path)
        if not isinstance(mapping, dict) or mapping.get("uncertainty_status") != "distribution_available":
            errors.append(f"{label}.provenance_path needs a distribution_available mapping")
        if provenance_path not in dsa_paths or provenance_path not in psa_paths:
            errors.append(f"{label}.provenance_path must appear in both plan input lists")
        deterministic = parameter.get("deterministic") or {}
        if "low" not in deterministic or "high" not in deterministic or not text(deterministic.get("rationale")):
            errors.append(f"{label}.deterministic needs low, high, and rationale")
        elif isinstance(base_value, list):
            if not simplex(deterministic["low"], len(base_value)) or not simplex(deterministic["high"], len(base_value)):
                errors.append(f"{label}.deterministic bounds must be coherent simplexes")
        elif not (
            finite_number(base_value)
            and finite_number(deterministic["low"])
            and finite_number(deterministic["high"])
            and deterministic["low"] < deterministic["high"]
            and deterministic["low"] <= base_value <= deterministic["high"]
        ):
            errors.append(f"{label}.deterministic bounds must bracket the base value")
        probabilistic = parameter.get("probabilistic") or {}
        if probabilistic.get("type") not in SUPPORTED_DISTRIBUTIONS:
            errors.append(f"{label}.probabilistic.type is unsupported")
        if not string_list(probabilistic.get("basis_ids")) or not text(
            probabilistic.get("rationale")
        ):
            errors.append(f"{label}.probabilistic needs basis_ids and rationale")
        elif isinstance(mapping, dict):
            allowed = set(mapping.get("source_ids") or []) | set(mapping.get("assumption_ids") or [])
            if not set(probabilistic["basis_ids"]).issubset(allowed):
                errors.append(f"{label}.probabilistic basis_ids are not linked by provenance")
        if base_value is not None and not distribution_valid(probabilistic, base_value):
            errors.append(f"{label}.probabilistic distribution parameters are invalid")

    psa = value.get("probabilistic_analysis") or {}
    iterations = psa.get("iterations")
    if isinstance(iterations, bool) or not isinstance(iterations, int) or not 1000 <= iterations <= 10000:
        errors.append("probabilistic_analysis.iterations must be from 1000 to 10000")
    if ((methodology.get("probabilistic") or {}).get("iterations")) != iterations:
        errors.append("plan and uncertainty iteration counts do not match")
    convergence = psa.get("convergence") or {}
    checkpoints = convergence.get("checkpoints")
    if not (
        isinstance(checkpoints, list)
        and len(checkpoints) >= 2
        and all(isinstance(item, int) and not isinstance(item, bool) for item in checkpoints)
        and checkpoints == sorted(set(checkpoints))
        and checkpoints[-1] == iterations
        and checkpoints[0] >= 100
    ):
        errors.append("convergence checkpoints must be increasing and end at iterations")
    for field in ("max_probability_mcse", "max_probability_drift"):
        threshold = convergence.get(field)
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0 < threshold <= 0.1:
            errors.append(f"convergence.{field} must be greater than 0 and no more than 0.1")
    correlation = psa.get("correlation_handling") or {}
    if not text(correlation.get("independence_rationale")):
        errors.append("correlation_handling.independence_rationale is required")
    if correlation.get("known_omitted_correlations") != []:
        errors.append("known_omitted_correlations must be resolved before review")
    omitted = psa.get("omitted_parameters")
    if not isinstance(omitted, list) or any(
        not isinstance(item, dict)
        or not text(item.get("provenance_path"))
        or not text(item.get("rationale"))
        for item in omitted
    ):
        errors.append("omitted_parameters must contain provenance_path and rationale")

    scenarios = value.get("structural_scenarios")
    if not isinstance(scenarios, list) or not 1 <= len(scenarios) <= 64:
        errors.append("structural_scenarios must contain from 1 to 64 entries")
        scenarios = []
    scenario_ids: set[str] = set()
    for index, scenario in enumerate(scenarios):
        label = f"structural_scenarios[{index}]"
        if not isinstance(scenario, dict):
            errors.append(f"{label} must be an object")
            continue
        identifier = scenario.get("id")
        if not text(identifier) or identifier in scenario_ids:
            errors.append(f"{label}.id must be non-empty and unique")
        else:
            scenario_ids.add(identifier)
        if not text(scenario.get("label")) or not text(scenario.get("rationale")):
            errors.append(f"{label} needs label and rationale")
        replacements = scenario.get("replacements")
        if not isinstance(replacements, list) or not replacements:
            errors.append(f"{label}.replacements must be non-empty")
            continue
        replacement_targets: set[str] = set()
        for replacement in replacements:
            target = replacement.get("target") if isinstance(replacement, dict) else None
            if not text(target) or not (
                target in SCENARIO_TARGETS or PARAMETER_TARGET.fullmatch(target)
            ) or target in replacement_targets:
                errors.append(f"{label} has a replacement outside the allowlist")
                continue
            replacement_targets.add(target)
            try:
                base_value = resolve_pointer(plan, target)
            except (KeyError, IndexError, TypeError, ValueError):
                errors.append(f"{label} replacement target does not exist in the plan")
                continue
            if not replacement_compatible(base_value, replacement.get("value")):
                errors.append(f"{label} replacement is incompatible with the target")
    if set(methodology.get("structural_scenarios") or []) != scenario_ids:
        errors.append("plan structural_scenarios must match uncertainty scenario ids")
    return errors


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: validate_uncertainty_plan.py UNCERTAINTY.json ANALYSIS_PLAN.json", file=sys.stderr)
        return 2
    try:
        errors = validate(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"INVALID: {error}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"INVALID: {error}", file=sys.stderr)
        return 1
    print("VALID: uncertainty plan contract is complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
