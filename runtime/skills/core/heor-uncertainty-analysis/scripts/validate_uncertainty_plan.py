#!/usr/bin/env python3
"""Portable structural validator for an AI4HEOR uncertainty plan."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path


SHA256 = re.compile(r"^[a-f0-9]{64}$")
STRATEGY_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
PARAMETER_TARGET = re.compile(
    r"^/strategies/[a-z][a-z0-9_-]{0,63}/(state_costs|state_utilities)/[0-9]+$"
    r"|^/strategies/[a-z][a-z0-9_-]{0,63}/transition_matrix/[0-9]+$"
    r"|^/strategies/[a-z][a-z0-9_-]{0,63}/transition_schedule/[0-9]+/matrix/[0-9]+$"
)
RATE_TARGET = re.compile(
    r"^/input_provenance/([0-9]+)/derivation/transformation/phases/([0-9]+)/rows/([0-9]+)/events/([0-9]+)/rate_per_year$"
)
SURVIVAL_TARGET = re.compile(
    r"^/input_provenance/([0-9]+)/derivation/transformation/parameters/(rate_per_year|shape|scale_years)/value$"
)
PROBABILITY_TARGET = re.compile(
    r"^/input_provenance/([0-9]+)/derivation/transformation/phases/([0-9]+)/rows/([0-9]+)/event/source_probability$"
)
BACKGROUND_EXCESS_TARGET = re.compile(
    r"^/input_provenance/([0-9]+)/derivation/transformation/excess_mortality_rate_per_year/value$"
)
RELATIVE_EFFECT_TARGET = re.compile(
    r"^/input_provenance/([0-9]+)/derivation/transformation/relative_effect/value$"
)
HAZARD_RATIO_TARGET = re.compile(
    r"^/input_provenance/([0-9]+)/derivation/transformation/hazard_ratio/value$"
)
SCHEDULE_START_TARGET = re.compile(
    r"^/strategies/[a-z][a-z0-9_-]{0,63}/transition_schedule/[0-9]+/start_cycle$"
)
SCENARIO_TARGETS = {
    "/cycles",
    "/cycle_length_years",
    "/discount_rates/costs",
    "/discount_rates/outcomes",
    "/half_cycle_correction",
}
SUPPORTED_DISTRIBUTIONS = {"beta", "gamma", "lognormal", "uniform", "dirichlet"}
HAZARD_RATIO_SCHEMA_VERSION = "0.10.0"
PARTITIONED_SURVIVAL_SCHEMA_VERSION = "0.11.0"
JOINT_SURVIVAL_SCHEMA_VERSION = "0.12.0"
PARTITIONED_SURVIVAL_SCHEMA_VERSIONS = {
    PARTITIONED_SURVIVAL_SCHEMA_VERSION,
    JOINT_SURVIVAL_SCHEMA_VERSION,
}
RELATIVE_EFFECT_SCHEMA_VERSION = "0.9.0"
BACKGROUND_SCHEMA_VERSION = "0.8.0"
CURRENT_SCHEMA_VERSION = "0.7.0"
PROBABILITY_SCHEMA_VERSION = "0.6.0"
SURVIVAL_SCHEMA_VERSION = "0.5.0"
CORRELATION_SCHEMA_VERSION = "0.4.0"
RATE_SCHEMA_VERSION = "0.3.0"
PRIOR_SCHEMA_VERSION = "0.2.0"
LEGACY_SCHEMA_VERSION = "0.1.0"
MAX_DECISION_THRESHOLDS = 101
MAX_CORRELATION_GROUPS = 64
MAX_CORRELATION_GROUP_SIZE = 32


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


def allowed_strategy_ids(plan: dict) -> set[str]:
    if plan.get("schema_version") not in {"0.8.0", "0.9.0", "0.10.0", "0.11.0", "0.12.0"}:
        return {"comparator", "intervention"}
    order = plan.get("strategy_order")
    strategies = plan.get("strategies")
    if not (
        isinstance(order, list)
        and 2 <= len(order) <= 16
        and all(isinstance(item, str) and STRATEGY_ID.fullmatch(item) for item in order)
        and len(set(order)) == len(order)
        and isinstance(strategies, dict)
        and set(strategies) == set(order)
        and plan.get("baseline_strategy_id") == order[0]
    ):
        return set()
    return set(order)


def target_strategy_id(target: object) -> str | None:
    if not text(target):
        return None
    parts = str(target).split("/")
    return parts[2] if len(parts) > 2 and parts[1] == "strategies" else None


def provenance_strategy_id(path: object) -> str | None:
    if not text(path):
        return None
    parts = str(path).split(".")
    return parts[1] if len(parts) > 1 and parts[0] == "strategies" else None


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


def distribution_valid(
    value: object,
    base: object,
    *,
    positive_parameter: bool = False,
    bounded_probability: bool = False,
) -> bool:
    if not isinstance(value, dict):
        return False
    kind = value.get("type")
    if positive_parameter and kind not in {"gamma", "lognormal", "uniform"}:
        return False
    if bounded_probability and kind not in {"beta", "uniform"}:
        return False
    if kind == "beta":
        return not isinstance(base, list) and positive_number(value.get("alpha")) and positive_number(value.get("beta"))
    if kind == "gamma":
        return not isinstance(base, list) and positive_number(value.get("shape")) and positive_number(value.get("scale"))
    if kind == "lognormal":
        return not isinstance(base, list) and finite_number(value.get("mu_log")) and positive_number(value.get("sigma_log"))
    if kind == "uniform":
        return (
            not isinstance(base, list)
            and finite_number(value.get("low"))
            and finite_number(value.get("high"))
            and value["low"] < value["high"]
            and (not positive_parameter or value["low"] > 0)
            and (
                not bounded_probability
                or 0 < value["low"] < value["high"] < 1
            )
        )
    if kind == "dirichlet":
        alpha = value.get("alpha")
        return isinstance(base, list) and isinstance(alpha, list) and len(alpha) == len(base) and all(positive_number(item) for item in alpha)
    return False


def correlation_matrix_errors(value: object, size: int, label: str) -> list[str]:
    if (
        not isinstance(value, list)
        or len(value) != size
        or any(not isinstance(row, list) or len(row) != size for row in value)
        or any(not finite_number(item) for row in value for item in row)
    ):
        return [f"{label} must be a finite {size} by {size} matrix"]
    matrix = value
    for row in range(size):
        if abs(matrix[row][row] - 1.0) > 1e-12:
            return [f"{label} diagonal must equal 1"]
        for column in range(row):
            if not -1.0 < matrix[row][column] < 1.0:
                return [f"{label} off-diagonal correlations must be strictly between -1 and 1"]
            if abs(matrix[row][column] - matrix[column][row]) > 1e-12:
                return [f"{label} must be symmetric"]
    lower = [[0.0] * size for _ in range(size)]
    for row in range(size):
        for column in range(row + 1):
            remainder = matrix[row][column] - sum(
                lower[row][item] * lower[column][item]
                for item in range(column)
            )
            if row == column:
                if remainder <= 1e-12:
                    return [f"{label} must be strictly positive definite"]
                lower[row][column] = math.sqrt(remainder)
            else:
                lower[row][column] = remainder / lower[column][column]
    return []


def validate(
    uncertainty_path: Path,
    plan_path: Path,
    partitioned_path: Path | None = None,
    materializations_path: Path | None = None,
    joint_manifest_path: Path | None = None,
    joint_draws_path: Path | None = None,
) -> list[str]:
    value, _ = load(uncertainty_path)
    plan, plan_raw = load(plan_path)
    errors: list[str] = []
    schema_version = value.get("schema_version")
    if schema_version not in {
        LEGACY_SCHEMA_VERSION,
        PRIOR_SCHEMA_VERSION,
        RATE_SCHEMA_VERSION,
        CORRELATION_SCHEMA_VERSION,
        SURVIVAL_SCHEMA_VERSION,
        PROBABILITY_SCHEMA_VERSION,
        CURRENT_SCHEMA_VERSION,
        BACKGROUND_SCHEMA_VERSION,
        RELATIVE_EFFECT_SCHEMA_VERSION,
        HAZARD_RATIO_SCHEMA_VERSION,
        PARTITIONED_SURVIVAL_SCHEMA_VERSION,
        JOINT_SURVIVAL_SCHEMA_VERSION,
    }:
        errors.append("schema_version must be 0.1.0 through 0.12.0")
    analysis_schema = plan.get("schema_version")
    if (analysis_schema == "0.8.0") != (schema_version == CURRENT_SCHEMA_VERSION):
        errors.append(
            "analysis schema_version 0.8.0 and uncertainty schema_version 0.7.0 must be used together"
        )
    if (analysis_schema == "0.9.0") != (schema_version == BACKGROUND_SCHEMA_VERSION):
        errors.append(
            "analysis schema_version 0.9.0 and uncertainty schema_version 0.8.0 must be used together"
        )
    if (analysis_schema == "0.10.0") != (schema_version == RELATIVE_EFFECT_SCHEMA_VERSION):
        errors.append(
            "analysis schema_version 0.10.0 and uncertainty schema_version 0.9.0 must be used together"
        )
    if (analysis_schema == "0.11.0") != (schema_version == HAZARD_RATIO_SCHEMA_VERSION):
        errors.append(
            "analysis schema_version 0.11.0 and uncertainty schema_version 0.10.0 must be used together"
        )
    if (analysis_schema == "0.12.0") != (
        schema_version in PARTITIONED_SURVIVAL_SCHEMA_VERSIONS
    ):
        errors.append(
            "analysis schema_version 0.12.0 requires uncertainty schema_version 0.11.0 or 0.12.0"
        )
    multi_strategy_base = analysis_schema in {"0.8.0", "0.9.0", "0.10.0", "0.11.0", "0.12.0"}
    strategy_ids = allowed_strategy_ids(plan)
    if multi_strategy_base and not strategy_ids:
        errors.append(
            "analysis schema 0.8.0 through 0.12.0 strategy_order, strategies, and baseline_strategy_id are invalid"
        )
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
    if schema_version in PARTITIONED_SURVIVAL_SCHEMA_VERSIONS:
        if partitioned_path is None or materializations_path is None:
            errors.append(
                "partitioned-survival uncertainty requires --partitioned-survival-plan and --survival-curve-materializations"
            )
        else:
            try:
                partitioned, partitioned_raw = load(partitioned_path)
                materializations, materializations_raw = load(materializations_path)
            except (OSError, ValueError, json.JSONDecodeError) as error:
                errors.append(f"partitioned-survival artifact is invalid: {error}")
            else:
                inputs = value.get("partitioned_survival_inputs")
                if not isinstance(inputs, dict) or set(inputs) != {"plan", "curve_materializations"}:
                    errors.append("partitioned_survival_inputs must contain only plan and curve_materializations")
                else:
                    for field, path, raw in (
                        ("plan", "heor/partitioned-survival-plan.json", partitioned_raw),
                        ("curve_materializations", "heor/survival-curve-materializations.json", materializations_raw),
                    ):
                        binding = inputs.get(field)
                        if not isinstance(binding, dict) or set(binding) != {"path", "content_sha256"} or binding.get("path") != path or binding.get("content_sha256") != hashlib.sha256(raw).hexdigest():
                            errors.append(f"partitioned_survival_inputs.{field} does not bind the current artifact bytes")
                if partitioned.get("schema_version") != "0.3.0" or partitioned.get("analysis_id") != plan.get("analysis_id"):
                    errors.append("partitioned-survival plan must be schema 0.3.0 for the current analysis")
                if materializations.get("schema_version") != "0.1.0" or materializations.get("analysis_id") != plan.get("analysis_id"):
                    errors.append("survival-curve materializations must be schema 0.1.0 for the current analysis")
        if schema_version == JOINT_SURVIVAL_SCHEMA_VERSION:
            if joint_manifest_path is None or joint_draws_path is None:
                errors.append(
                    "schema 0.12.0 requires --joint-survival-uncertainty-manifest and --joint-survival-draws"
                )
            else:
                try:
                    joint_manifest_raw = joint_manifest_path.read_bytes()
                    joint_draws_raw = joint_draws_path.read_bytes()
                except OSError as error:
                    errors.append(f"joint-survival artifact is invalid: {error}")
                else:
                    joint_inputs = value.get("joint_survival_inputs")
                    if not isinstance(joint_inputs, dict) or set(joint_inputs) != {"manifest", "draws"}:
                        errors.append("joint_survival_inputs must contain only manifest and draws")
                    else:
                        for field, path, raw in (
                            ("manifest", "heor/joint-survival-uncertainty.json", joint_manifest_raw),
                            ("draws", "heor/joint-survival-draws.jsonl", joint_draws_raw),
                        ):
                            binding = joint_inputs.get(field)
                            if not isinstance(binding, dict) or set(binding) != {"path", "content_sha256"} or binding.get("path") != path or binding.get("content_sha256") != hashlib.sha256(raw).hexdigest():
                                errors.append(f"joint_survival_inputs.{field} does not bind the current artifact bytes")
        elif joint_manifest_path is not None or joint_draws_path is not None or "joint_survival_inputs" in value:
            errors.append("joint-survival artifacts require uncertainty schema_version 0.12.0")
    elif partitioned_path is not None or materializations_path is not None or "partitioned_survival_inputs" in value:
        errors.append("partitioned-survival artifacts require uncertainty schema_version 0.11.0 or 0.12.0")
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
    parameters_by_id: dict[str, dict] = {}
    targets: set[str] = set()
    for index, parameter in enumerate(parameters):
        label = f"parameters[{index}]"
        if not isinstance(parameter, dict):
            errors.append(f"{label} must be an object")
            continue
        identifier = parameter.get("id")
        target = parameter.get("target")
        rate_match = RATE_TARGET.fullmatch(target) if text(target) else None
        survival_match = SURVIVAL_TARGET.fullmatch(target) if text(target) else None
        probability_match = PROBABILITY_TARGET.fullmatch(target) if text(target) else None
        background_match = BACKGROUND_EXCESS_TARGET.fullmatch(target) if text(target) else None
        relative_match = RELATIVE_EFFECT_TARGET.fullmatch(target) if text(target) else None
        hazard_match = HAZARD_RATIO_TARGET.fullmatch(target) if text(target) else None
        direct_target = bool(PARAMETER_TARGET.fullmatch(target)) if text(target) else False
        direct_strategy_id = target_strategy_id(target) if direct_target else None
        target_allowed = direct_target and direct_strategy_id in strategy_ids
        if rate_match and schema_version in {RATE_SCHEMA_VERSION, CORRELATION_SCHEMA_VERSION, SURVIVAL_SCHEMA_VERSION, PROBABILITY_SCHEMA_VERSION, CURRENT_SCHEMA_VERSION, BACKGROUND_SCHEMA_VERSION}:
            target_allowed = True
        if survival_match and schema_version in {SURVIVAL_SCHEMA_VERSION, PROBABILITY_SCHEMA_VERSION, CURRENT_SCHEMA_VERSION, BACKGROUND_SCHEMA_VERSION}:
            target_allowed = True
        if probability_match and schema_version in {PROBABILITY_SCHEMA_VERSION, CURRENT_SCHEMA_VERSION, BACKGROUND_SCHEMA_VERSION}:
            target_allowed = True
        if background_match and schema_version == BACKGROUND_SCHEMA_VERSION:
            target_allowed = True
        if schema_version == BACKGROUND_SCHEMA_VERSION and not background_match:
            target_allowed = False
        if relative_match and schema_version == RELATIVE_EFFECT_SCHEMA_VERSION:
            target_allowed = True
        if schema_version == RELATIVE_EFFECT_SCHEMA_VERSION and not relative_match:
            target_allowed = False
        if hazard_match and schema_version == HAZARD_RATIO_SCHEMA_VERSION:
            target_allowed = True
        if schema_version == HAZARD_RATIO_SCHEMA_VERSION and not hazard_match:
            target_allowed = False
        if schema_version in PARTITIONED_SURVIVAL_SCHEMA_VERSIONS:
            target_allowed = bool(
                direct_target
                and direct_strategy_id in strategy_ids
                and ("/state_costs/" in target or "/state_utilities/" in target)
            )
        if not text(identifier) or identifier in ids:
            errors.append(f"{label}.id must be non-empty and unique")
        else:
            ids.add(identifier)
            parameters_by_id[identifier] = parameter
        if not text(target) or not target_allowed or target in targets:
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
        if schema_version in PARTITIONED_SURVIVAL_SCHEMA_VERSIONS and text(target):
            expected_path = target.rsplit("/", 1)[0].removeprefix("/").replace("/", ".")
            if provenance_path != expected_path:
                errors.append(f"{label}.provenance_path must exactly match the economic reward-vector path")
        mapping_strategy_id = provenance_strategy_id(provenance_path)
        if mapping_strategy_id is not None and mapping_strategy_id not in strategy_ids:
            errors.append(
                f"{label}.provenance_path strategy is not declared by the analysis plan"
            )
        event_basis: str | None = None
        survival_basis: str | None = None
        probability_basis: str | None = None
        background_basis: str | None = None
        relative_basis: str | None = None
        relative_measure: str | None = None
        relative_rr_ceiling: float | None = None
        hazard_basis: str | None = None
        hazard_max_increment: float | None = None
        if rate_match:
            if schema_version not in {RATE_SCHEMA_VERSION, CORRELATION_SCHEMA_VERSION, SURVIVAL_SCHEMA_VERSION, PROBABILITY_SCHEMA_VERSION, CURRENT_SCHEMA_VERSION, BACKGROUND_SCHEMA_VERSION}:
                errors.append(f"{label}.target requires schema_version 0.3.0 through 0.8.0")
            try:
                mapping_index, phase_index, row_index, event_index = (
                    int(item) for item in rate_match.groups()
                )
                indexed_mapping = plan["input_provenance"][mapping_index]
                event = indexed_mapping["derivation"]["transformation"]["phases"][phase_index]["rows"][row_index]["events"][event_index]
            except (KeyError, IndexError, TypeError, ValueError):
                indexed_mapping = None
                event = None
                errors.append(f"{label}.target does not identify an existing event rate")
            if not isinstance(indexed_mapping, dict) or indexed_mapping.get("path") != provenance_path:
                errors.append(f"{label}.provenance_path must equal the rate transformation mapping path")
            else:
                mapping = indexed_mapping
                derivation = mapping.get("derivation") or {}
                transformation = derivation.get("transformation") or {}
                if (
                    plan.get("schema_version") not in {"0.5.0", "0.8.0", "0.9.0"}
                    or derivation.get("method") != "deterministic_transformation"
                    or transformation.get("operation") != "constant_competing_rates"
                ):
                    errors.append(f"{label}.target requires an admitted constant competing-rate transformation")
            if isinstance(event, dict):
                source_id = event.get("source_extraction_id")
                assumption_id = event.get("assumption_id")
                event_basis = source_id if text(source_id) else assumption_id
        elif survival_match:
            if schema_version not in {SURVIVAL_SCHEMA_VERSION, PROBABILITY_SCHEMA_VERSION, CURRENT_SCHEMA_VERSION, BACKGROUND_SCHEMA_VERSION}:
                errors.append(f"{label}.target requires schema_version 0.5.0 through 0.8.0")
            try:
                mapping_index = int(survival_match.group(1))
                parameter_name = survival_match.group(2)
                indexed_mapping = plan["input_provenance"][mapping_index]
                transformation = indexed_mapping["derivation"]["transformation"]
                parameter_value = transformation["parameters"][parameter_name]
            except (KeyError, IndexError, TypeError, ValueError):
                indexed_mapping = None
                transformation = None
                parameter_value = None
                errors.append(f"{label}.target does not identify an existing survival parameter")
            if not isinstance(indexed_mapping, dict) or indexed_mapping.get("path") != provenance_path:
                errors.append(f"{label}.provenance_path must equal the survival transformation mapping path")
            else:
                mapping = indexed_mapping
                derivation = mapping.get("derivation") or {}
                expected_parameters = {
                    "exponential": {"rate_per_year"},
                    "weibull": {"shape", "scale_years"},
                }.get(transformation.get("distribution") if isinstance(transformation, dict) else None)
                if (
                    plan.get("schema_version") not in {"0.6.0", "0.8.0", "0.9.0"}
                    or derivation.get("method") != "deterministic_transformation"
                    or not isinstance(transformation, dict)
                    or transformation.get("operation") != "parametric_survival_to_transition_schedule"
                    or expected_parameters is None
                    or parameter_name not in expected_parameters
                ):
                    errors.append(f"{label}.target requires an admitted parametric survival transformation")
            if isinstance(parameter_value, dict):
                source_id = parameter_value.get("source_extraction_id")
                assumption_id = parameter_value.get("assumption_id")
                survival_basis = source_id if text(source_id) else assumption_id
        elif probability_match:
            if schema_version not in {PROBABILITY_SCHEMA_VERSION, CURRENT_SCHEMA_VERSION, BACKGROUND_SCHEMA_VERSION}:
                errors.append(f"{label}.target requires schema_version 0.6.0 through 0.8.0")
            try:
                mapping_index, phase_index, row_index = (
                    int(item) for item in probability_match.groups()
                )
                indexed_mapping = plan["input_provenance"][mapping_index]
                transformation = indexed_mapping["derivation"]["transformation"]
                event = transformation["phases"][phase_index]["rows"][row_index]["event"]
            except (KeyError, IndexError, TypeError, ValueError):
                indexed_mapping = None
                transformation = None
                event = None
                errors.append(f"{label}.target does not identify an existing source probability")
            if not isinstance(indexed_mapping, dict) or indexed_mapping.get("path") != provenance_path:
                errors.append(f"{label}.provenance_path must equal the probability-time transformation mapping path")
            else:
                mapping = indexed_mapping
                derivation = mapping.get("derivation") or {}
                if (
                    plan.get("schema_version") not in {"0.7.0", "0.8.0", "0.9.0"}
                    or derivation.get("method") != "deterministic_transformation"
                    or not isinstance(transformation, dict)
                    or transformation.get("operation") != "single_event_probability_time_conversion"
                ):
                    errors.append(f"{label}.target requires an admitted probability-time transformation")
            if isinstance(event, dict):
                source_id = event.get("source_extraction_id")
                assumption_id = event.get("assumption_id")
                probability_basis = source_id if text(source_id) else assumption_id
        elif background_match:
            if schema_version != BACKGROUND_SCHEMA_VERSION:
                errors.append(f"{label}.target requires schema_version 0.8.0")
            try:
                mapping_index = int(background_match.group(1))
                indexed_mapping = plan["input_provenance"][mapping_index]
                transformation = indexed_mapping["derivation"]["transformation"]
                rate = transformation["excess_mortality_rate_per_year"]
            except (KeyError, IndexError, TypeError, ValueError):
                indexed_mapping = None
                transformation = None
                rate = None
                errors.append(f"{label}.target does not identify an existing disease excess rate")
            if not isinstance(indexed_mapping, dict) or indexed_mapping.get("path") != provenance_path:
                errors.append(f"{label}.provenance_path must equal the background mortality transformation mapping path")
            else:
                mapping = indexed_mapping
                derivation = mapping.get("derivation") or {}
                if (
                    plan.get("schema_version") != "0.9.0"
                    or derivation.get("method") != "deterministic_transformation"
                    or not isinstance(transformation, dict)
                    or transformation.get("operation") != "background_plus_excess_mortality_to_transition_schedule"
                ):
                    errors.append(f"{label}.target requires an admitted background mortality transformation")
            if isinstance(rate, dict):
                source_id = rate.get("source_extraction_id")
                assumption_id = rate.get("assumption_id")
                background_basis = source_id if text(source_id) else assumption_id
        elif relative_match:
            if schema_version != RELATIVE_EFFECT_SCHEMA_VERSION:
                errors.append(f"{label}.target requires schema_version 0.9.0")
            try:
                mapping_index = int(relative_match.group(1))
                indexed_mapping = plan["input_provenance"][mapping_index]
                transformation = indexed_mapping["derivation"]["transformation"]
                effect = transformation["relative_effect"]
                baseline_entries = transformation["baseline_cycle_probabilities"]
            except (KeyError, IndexError, TypeError, ValueError):
                indexed_mapping = None
                transformation = None
                effect = None
                baseline_entries = None
                errors.append(f"{label}.target does not identify an existing relative effect")
            if not isinstance(indexed_mapping, dict) or indexed_mapping.get("path") != provenance_path:
                errors.append(f"{label}.provenance_path must equal the relative-effect transformation mapping path")
            else:
                mapping = indexed_mapping
                derivation = mapping.get("derivation") or {}
                if (
                    plan.get("schema_version") != "0.10.0"
                    or derivation.get("method") != "deterministic_transformation"
                    or not isinstance(transformation, dict)
                    or transformation.get("operation") != "relative_effect_to_transition_schedule"
                    or transformation.get("measure") not in {"risk_ratio", "odds_ratio"}
                ):
                    errors.append(f"{label}.target requires an admitted RR/OR relative-effect transformation")
                else:
                    relative_measure = transformation["measure"]
            if isinstance(effect, dict):
                source_id = effect.get("source_extraction_id")
                assumption_id = effect.get("assumption_id")
                relative_basis = source_id if text(source_id) else assumption_id
                if not positive_number(effect.get("value")):
                    errors.append(f"{label}.relative_effect base value must be strictly positive")
            if isinstance(baseline_entries, list):
                positive_baselines = [
                    item.get("probability", {}).get("value")
                    for item in baseline_entries
                    if isinstance(item, dict)
                    and isinstance(item.get("probability"), dict)
                    and positive_number(item["probability"].get("value"))
                ]
                if not positive_baselines:
                    errors.append(f"{label}.relative-effect transformation needs at least one positive baseline probability")
                else:
                    relative_rr_ceiling = 1.0 / max(positive_baselines)
        elif hazard_match:
            if schema_version != HAZARD_RATIO_SCHEMA_VERSION:
                errors.append(f"{label}.target requires schema_version 0.10.0")
            try:
                mapping_index = int(hazard_match.group(1))
                indexed_mapping = plan["input_provenance"][mapping_index]
                transformation = indexed_mapping["derivation"]["transformation"]
                effect = transformation["hazard_ratio"]
                baseline_entries = transformation["baseline_cumulative_hazards"]
            except (KeyError, IndexError, TypeError, ValueError):
                indexed_mapping = None
                transformation = None
                effect = None
                baseline_entries = None
                errors.append(f"{label}.target does not identify an existing hazard ratio")
            if not isinstance(indexed_mapping, dict) or indexed_mapping.get("path") != provenance_path:
                errors.append(f"{label}.provenance_path must equal the hazard-ratio transformation mapping path")
            else:
                mapping = indexed_mapping
                derivation = mapping.get("derivation") or {}
                if (
                    plan.get("schema_version") != "0.11.0"
                    or derivation.get("method") != "deterministic_transformation"
                    or not isinstance(transformation, dict)
                    or transformation.get("operation") != "hazard_ratio_to_transition_schedule"
                ):
                    errors.append(f"{label}.target requires an admitted hazard-ratio transformation")
            if isinstance(effect, dict):
                source_id = effect.get("source_extraction_id")
                assumption_id = effect.get("assumption_id")
                hazard_basis = source_id if text(source_id) else assumption_id
                if not positive_number(effect.get("value")):
                    errors.append(f"{label}.hazard_ratio base value must be strictly positive")
            if isinstance(baseline_entries, list):
                previous = 0.0
                increments: list[float] = []
                valid_hazards = True
                for item in baseline_entries:
                    cumulative = (
                        item.get("cumulative_hazard", {}).get("value")
                        if isinstance(item, dict)
                        and isinstance(item.get("cumulative_hazard"), dict)
                        else None
                    )
                    if not finite_number(cumulative) or cumulative < previous:
                        valid_hazards = False
                        break
                    increments.append(cumulative - previous)
                    previous = cumulative
                if valid_hazards and increments and max(increments) > 0:
                    hazard_max_increment = max(increments)
                else:
                    errors.append(f"{label}.hazard-ratio transformation needs non-decreasing hazards with a positive increment")
        if not isinstance(mapping, dict) or mapping.get("uncertainty_status") != "distribution_available":
            errors.append(f"{label}.provenance_path needs a distribution_available mapping")
        if (
            not rate_match
            and not survival_match
            and not probability_match
            and not background_match
            and not relative_match
            and not hazard_match
            and isinstance(mapping, dict)
            and (mapping.get("derivation") or {}).get("method") == "deterministic_transformation"
        ):
            errors.append(f"{label}.target must vary an admitted transformation parameter, not a derived transition row")
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
            and (not (rate_match or survival_match or background_match or relative_match or hazard_match) or deterministic["low"] > 0)
            and (
                not probability_match
                or 0 < deterministic["low"] < deterministic["high"] < 1
            )
        ):
            errors.append(f"{label}.deterministic bounds must bracket the base value")
        if schema_version in PARTITIONED_SURVIVAL_SCHEMA_VERSIONS:
            if "/state_costs/" in str(target) and finite_number(deterministic.get("low")) and deterministic["low"] < 0:
                errors.append(f"{label}.state-cost deterministic bounds must be non-negative")
            if "/state_utilities/" in str(target) and not (
                finite_number(deterministic.get("low"))
                and finite_number(deterministic.get("high"))
                and -1 <= deterministic["low"] < deterministic["high"] <= 1
            ):
                errors.append(f"{label}.state-utility deterministic bounds must stay within -1 and 1")
        if (
            relative_match
            and relative_measure == "risk_ratio"
            and relative_rr_ceiling is not None
            and finite_number(deterministic.get("high"))
            and not deterministic["high"] < relative_rr_ceiling
        ):
            errors.append(
                f"{label}.risk-ratio deterministic high must be strictly below 1 / max positive baseline probability"
            )
        if (
            hazard_match
            and hazard_max_increment is not None
            and finite_number(deterministic.get("high"))
            and (
                not math.isfinite(deterministic["high"] * hazard_max_increment)
                or -math.expm1(-deterministic["high"] * hazard_max_increment) >= 1
            )
        ):
            errors.append(f"{label}.hazard-ratio deterministic high must reproduce a valid schedule")
        probabilistic = parameter.get("probabilistic") or {}
        if probabilistic.get("type") not in SUPPORTED_DISTRIBUTIONS:
            errors.append(f"{label}.probabilistic.type is unsupported")
        if not string_list(probabilistic.get("basis_ids")) or not text(
            probabilistic.get("rationale")
        ):
            errors.append(f"{label}.probabilistic needs basis_ids and rationale")
        elif rate_match:
            if probabilistic["basis_ids"] != [event_basis]:
                errors.append(f"{label}.probabilistic basis_ids must contain exactly the event source extraction or assumption id")
        elif survival_match:
            if probabilistic["basis_ids"] != [survival_basis]:
                errors.append(f"{label}.probabilistic basis_ids must contain exactly the survival parameter source extraction or assumption id")
        elif probability_match:
            if probabilistic["basis_ids"] != [probability_basis]:
                errors.append(f"{label}.probabilistic basis_ids must contain exactly the probability source extraction or assumption id")
        elif background_match:
            if probabilistic["basis_ids"] != [background_basis]:
                errors.append(f"{label}.probabilistic basis_ids must contain exactly the disease excess rate source extraction or assumption id")
        elif relative_match:
            if probabilistic["basis_ids"] != [relative_basis]:
                errors.append(f"{label}.probabilistic basis_ids must contain exactly the relative-effect extraction or assumption id")
        elif hazard_match:
            if probabilistic["basis_ids"] != [hazard_basis]:
                errors.append(f"{label}.probabilistic basis_ids must contain exactly the hazard-ratio extraction or assumption id")
        elif isinstance(mapping, dict):
            allowed = set(mapping.get("source_ids") or []) | set(mapping.get("extraction_ids") or []) | set(mapping.get("assumption_ids") or [])
            if not set(probabilistic["basis_ids"]).issubset(allowed):
                errors.append(f"{label}.probabilistic basis_ids are not linked by provenance")
        if base_value is not None and not distribution_valid(
            probabilistic,
            base_value,
            positive_parameter=bool(rate_match or survival_match or background_match or relative_match or hazard_match),
            bounded_probability=bool(probability_match),
        ):
            errors.append(f"{label}.probabilistic distribution parameters are invalid")
        if schema_version in PARTITIONED_SURVIVAL_SCHEMA_VERSIONS:
            if "/state_costs/" in str(target):
                if probabilistic.get("type") not in {"gamma", "lognormal", "uniform"}:
                    errors.append(f"{label}.state-cost PSA must use Gamma, Lognormal, or Uniform")
                if probabilistic.get("type") == "uniform" and (
                    not finite_number(probabilistic.get("low")) or probabilistic["low"] < 0
                ):
                    errors.append(f"{label}.state-cost Uniform low must be non-negative")
            elif "/state_utilities/" in str(target):
                if probabilistic.get("type") == "uniform":
                    if not (
                        finite_number(probabilistic.get("low"))
                        and finite_number(probabilistic.get("high"))
                        and -1 <= probabilistic["low"] < probabilistic["high"] <= 1
                    ):
                        errors.append(f"{label}.state-utility Uniform bounds must stay within -1 and 1")
                elif probabilistic.get("type") != "beta":
                    errors.append(f"{label}.state-utility PSA must use Beta or bounded Uniform")
        if relative_match and relative_measure == "risk_ratio":
            if probabilistic.get("type") != "uniform":
                errors.append(
                    f"{label}.risk-ratio PSA must use bounded Uniform; unbounded positive distributions can produce invalid absolute risks"
                )
            elif (
                relative_rr_ceiling is None
                or not finite_number(probabilistic.get("high"))
                or not probabilistic["high"] < relative_rr_ceiling
            ):
                errors.append(
                    f"{label}.risk-ratio Uniform high must be strictly below 1 / max positive baseline probability"
                )
        elif relative_match and relative_measure == "odds_ratio" and probabilistic.get("type") not in {"lognormal", "uniform"}:
            errors.append(f"{label}.odds-ratio PSA must use Lognormal or strictly positive Uniform")
        elif hazard_match:
            high = probabilistic.get("high")
            if probabilistic.get("type") != "uniform":
                errors.append(f"{label}.hazard-ratio PSA must use strictly positive bounded Uniform")
            elif (
                hazard_max_increment is None
                or not finite_number(high)
                or not math.isfinite(high * hazard_max_increment)
                or -math.expm1(-high * hazard_max_increment) >= 1
            ):
                errors.append(f"{label}.hazard-ratio Uniform high must reproduce a valid schedule")

    psa = value.get("probabilistic_analysis") or {}
    iterations = psa.get("iterations")
    if isinstance(iterations, bool) or not isinstance(iterations, int) or not 1000 <= iterations <= 10000:
        errors.append("probabilistic_analysis.iterations must be from 1000 to 10000")
    if ((methodology.get("probabilistic") or {}).get("iterations")) != iterations:
        errors.append("plan and uncertainty iteration counts do not match")
    threshold_config = psa.get("decision_thresholds")
    primary_threshold = plan.get("willingness_to_pay")
    if schema_version in {
        PRIOR_SCHEMA_VERSION,
        RATE_SCHEMA_VERSION,
        CORRELATION_SCHEMA_VERSION,
        SURVIVAL_SCHEMA_VERSION,
        PROBABILITY_SCHEMA_VERSION,
        CURRENT_SCHEMA_VERSION,
        BACKGROUND_SCHEMA_VERSION,
        RELATIVE_EFFECT_SCHEMA_VERSION,
        HAZARD_RATIO_SCHEMA_VERSION,
        PARTITIONED_SURVIVAL_SCHEMA_VERSION,
        JOINT_SURVIVAL_SCHEMA_VERSION,
    }:
        threshold_config = threshold_config if isinstance(threshold_config, dict) else {}
        thresholds = threshold_config.get("values")
        valid_thresholds = (
            isinstance(thresholds, list)
            and 2 <= len(thresholds) <= MAX_DECISION_THRESHOLDS
            and all(finite_number(item) and item >= 0 for item in thresholds)
            and thresholds == sorted(set(thresholds))
        )
        if not valid_thresholds:
            errors.append(
                "decision thresholds must be 2-101 unique, non-negative, strictly increasing values"
            )
        elif not any(abs(item - primary_threshold) <= 1e-9 for item in thresholds):
            errors.append("decision thresholds must include the primary willingness_to_pay")
        if not text(threshold_config.get("rationale")):
            errors.append("decision thresholds rationale is required")
    elif threshold_config is not None:
        errors.append("decision thresholds require schema_version 0.2.0 through 0.12.0")
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
    if schema_version in {CORRELATION_SCHEMA_VERSION, SURVIVAL_SCHEMA_VERSION, PROBABILITY_SCHEMA_VERSION, CURRENT_SCHEMA_VERSION, BACKGROUND_SCHEMA_VERSION, RELATIVE_EFFECT_SCHEMA_VERSION, HAZARD_RATIO_SCHEMA_VERSION, PARTITIONED_SURVIVAL_SCHEMA_VERSION, JOINT_SURVIVAL_SCHEMA_VERSION}:
        groups = correlation.get("groups")
        if not isinstance(groups, list) or len(groups) > MAX_CORRELATION_GROUPS:
            errors.append(
                f"correlation_handling.groups must contain no more than {MAX_CORRELATION_GROUPS} entries"
            )
            groups = []
        group_ids: set[str] = set()
        grouped_parameters: set[str] = set()
        allowed_fields = {
            "id", "parameter_ids", "scale", "method", "correlation_matrix",
            "basis_ids", "rationale",
        }
        for index, group in enumerate(groups):
            label = f"correlation_handling.groups[{index}]"
            if not isinstance(group, dict):
                errors.append(f"{label} must be an object")
                continue
            unknown = set(group) - allowed_fields
            if unknown:
                errors.append(f"{label} contains unsupported fields: {', '.join(sorted(unknown))}")
            identifier = group.get("id")
            if not text(identifier) or identifier in group_ids:
                errors.append(f"{label}.id must be non-empty and unique")
            else:
                group_ids.add(identifier)
            parameter_ids = group.get("parameter_ids")
            members_valid = (
                isinstance(parameter_ids, list)
                and 2 <= len(parameter_ids) <= MAX_CORRELATION_GROUP_SIZE
                and all(text(item) for item in parameter_ids)
                and len(set(parameter_ids)) == len(parameter_ids)
            )
            if not members_valid:
                errors.append(
                    f"{label}.parameter_ids must contain 2-{MAX_CORRELATION_GROUP_SIZE} unique ids"
                )
                parameter_ids = []
            if any(item not in parameters_by_id for item in parameter_ids):
                errors.append(f"{label} references an unknown parameter id")
            if grouped_parameters.intersection(parameter_ids):
                errors.append("an uncertainty parameter may belong to only one correlation group")
            grouped_parameters.update(parameter_ids)
            if any(
                (parameters_by_id.get(item, {}).get("probabilistic") or {}).get("type") != "lognormal"
                for item in parameter_ids
            ):
                errors.append(f"{label} supports only scalar lognormal parameter members")
            if group.get("scale") != "log_standard_normal" or group.get("method") != "cholesky":
                errors.append(f"{label} requires log_standard_normal scale and cholesky method")
            errors.extend(
                correlation_matrix_errors(
                    group.get("correlation_matrix"),
                    len(parameter_ids),
                    f"{label}.correlation_matrix",
                )
            )
            basis_ids = group.get("basis_ids")
            if not string_list(basis_ids):
                errors.append(f"{label}.basis_ids must be non-empty and unique")
            else:
                if not all(
                    set(basis_ids).issubset(set(
                        (parameters_by_id.get(item, {}).get("probabilistic") or {}).get("basis_ids") or []
                    ))
                    for item in parameter_ids
                ):
                    errors.append(
                        f"{label}.basis_ids must be linked by every member parameter distribution"
                    )
            if not text(group.get("rationale")):
                errors.append(f"{label}.rationale is required")
    elif "groups" in correlation:
        errors.append("correlation groups require schema_version 0.4.0 through 0.12.0")
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
    elif schema_version in PARTITIONED_SURVIVAL_SCHEMA_VERSIONS:
        expected_omissions = {
            f"partitioned_survival.strategies.{strategy_id}.{endpoint}"
            for strategy_id in strategy_ids
            for endpoint in ("pfs", "os")
        }
        declared_omissions = {item["provenance_path"] for item in omitted}
        if schema_version == PARTITIONED_SURVIVAL_SCHEMA_VERSION and not expected_omissions.issubset(declared_omissions):
            errors.append("schema 0.11.0 must explicitly omit every fixed PFS and OS curve")
        if schema_version == JOINT_SURVIVAL_SCHEMA_VERSION:
            if expected_omissions.intersection(declared_omissions):
                errors.append("schema 0.12.0 must not omit represented PFS or OS curves")
            required = {
                "partitioned_survival.structural.curve_family_selection",
                "partitioned_survival.structural.extrapolation_assumptions",
                "partitioned_survival.structural.treatment_effect_duration",
            }
            if not required.issubset(declared_omissions):
                errors.append("schema 0.12.0 must explicitly omit unresolved structural survival uncertainty")

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
            replacement_strategy_id = target_strategy_id(target)
            ordinary_allowed = target in SCENARIO_TARGETS or (
                (
                    PARAMETER_TARGET.fullmatch(target)
                    or SCHEDULE_START_TARGET.fullmatch(target)
                )
                and replacement_strategy_id in strategy_ids
            ) if text(target) else False
            background_allowed = (
                target in {
                    "/discount_rates/costs",
                    "/discount_rates/outcomes",
                    "/half_cycle_correction",
                }
                or (
                    bool(PARAMETER_TARGET.fullmatch(target))
                    and replacement_strategy_id in strategy_ids
                    and ("/state_costs/" in target or "/state_utilities/" in target)
                )
            ) if text(target) else False
            target_allowed = (
                background_allowed
                if schema_version in {BACKGROUND_SCHEMA_VERSION, RELATIVE_EFFECT_SCHEMA_VERSION, HAZARD_RATIO_SCHEMA_VERSION, PARTITIONED_SURVIVAL_SCHEMA_VERSION, JOINT_SURVIVAL_SCHEMA_VERSION}
                else ordinary_allowed
            )
            if not text(target) or not target_allowed or target in replacement_targets:
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
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("uncertainty_plan", type=Path)
    parser.add_argument("analysis_plan", type=Path)
    parser.add_argument("--partitioned-survival-plan", type=Path)
    parser.add_argument("--survival-curve-materializations", type=Path)
    parser.add_argument("--joint-survival-uncertainty-manifest", type=Path)
    parser.add_argument("--joint-survival-draws", type=Path)
    args = parser.parse_args()
    try:
        errors = validate(
            args.uncertainty_plan,
            args.analysis_plan,
            args.partitioned_survival_plan,
            args.survival_curve_materializations,
            args.joint_survival_uncertainty_manifest,
            args.joint_survival_draws,
        )
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
