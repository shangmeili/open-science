#!/usr/bin/env python3
"""Audit portable evidence-to-input links; app-owned verification remains external."""

from __future__ import annotations

import json
import sys
from hashlib import sha256
from math import expm1, isclose, isfinite
from pathlib import Path
from typing import Any


BASE_PATHS = [
    "cycles", "cycle_length_years", "discount_rates.costs", "discount_rates.outcomes",
    "half_cycle_correction", "strategies.comparator.initial_distribution",
    "strategies.comparator.transition_matrix", "strategies.comparator.state_costs",
    "strategies.comparator.state_utilities", "strategies.intervention.initial_distribution",
    "strategies.intervention.transition_matrix", "strategies.intervention.state_costs",
    "strategies.intervention.state_utilities",
]
UNCERTAINTY = {"fixed", "range_available", "distribution_available"}
APPROVABLE_ANALYSIS_SCHEMAS = {"0.3.0", "0.4.0", "0.5.0"}
TRANSITION_PATHS = {
    "strategies.comparator.transition_matrix",
    "strategies.intervention.transition_matrix",
    "strategies.comparator.transition_schedule",
    "strategies.intervention.transition_schedule",
}


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def texts(value: Any) -> list[str] | None:
    if not isinstance(value, list) or any(not text(item) for item in value):
        return None
    return value


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def currency_code(value: Any) -> bool:
    return (
        isinstance(value, str) and len(value) == 3 and value.isascii()
        and value.isalpha() and value.isupper()
    )


def finite_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and isfinite(value)


def model_value(plan: dict[str, Any], path: str) -> Any:
    current: Any = plan
    for token in path.split("."):
        if not isinstance(current, dict) or token not in current:
            return None
        current = current[token]
    return current


def required_paths(plan: dict[str, Any]) -> list[str]:
    paths = [path for path in BASE_PATHS if not path.endswith(".transition_matrix")]
    for role in ("comparator", "intervention"):
        strategy = (plan.get("strategies") or {}).get(role) or {}
        transition_field = (
            "transition_schedule"
            if isinstance(strategy, dict) and "transition_schedule" in strategy
            else "transition_matrix"
        )
        insert_after = paths.index(f"strategies.{role}.initial_distribution") + 1
        paths.insert(insert_after, f"strategies.{role}.{transition_field}")
    return paths


def strict_json(value: Any) -> Any:
    if not isinstance(value, str):
        raise ValueError("extracted_value is not text")

    def reject_constant(constant: str) -> None:
        raise ValueError(f"non-standard JSON constant {constant}")

    return json.loads(value, parse_constant=reject_constant)


def json_equivalent(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if finite_number(left) or finite_number(right):
        return finite_number(left) and finite_number(right) and isclose(
            float(left), float(right), rel_tol=1e-12, abs_tol=1e-12
        )
    if isinstance(left, list) or isinstance(right, list):
        return (
            isinstance(left, list)
            and isinstance(right, list)
            and len(left) == len(right)
            and all(json_equivalent(a, b) for a, b in zip(left, right))
        )
    if isinstance(left, dict) or isinstance(right, dict):
        return (
            isinstance(left, dict)
            and isinstance(right, dict)
            and left.keys() == right.keys()
            and all(json_equivalent(left[key], right[key]) for key in left)
        )
    return left == right


def json_pointer(value: Any, pointer: str) -> Any:
    if pointer == "":
        return value
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("source_pointer must be empty or a JSON pointer")
    current = value
    for encoded in pointer[1:].split("/"):
        token = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not token.isdigit() or int(token) >= len(current):
                raise ValueError("source_pointer does not resolve")
            current = current[int(token)]
        elif isinstance(current, dict) and token in current:
            current = current[token]
        else:
            raise ValueError("source_pointer does not resolve")
    return current


def transition_rate_reasons(
    plan: dict[str, Any],
    path: str,
    mapping: dict[str, Any],
    derivation: dict[str, Any],
    extraction_index: dict[str, dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if plan.get("schema_version") != "0.5.0":
        return ["deterministic transition-rate transformations require schema_version 0.5.0"]
    if path not in TRANSITION_PATHS:
        return ["deterministic transformation is allowed only for transition inputs"]
    transformation = derivation.get("transformation")
    if not isinstance(transformation, dict):
        return ["derivation.transformation must be an object"]
    expected_keys = {"operation", "cycle_length_years", "phases"}
    if set(transformation) != expected_keys:
        reasons.append("transformation fields are not the exact supported contract")
    if transformation.get("operation") != "constant_competing_rates":
        reasons.append("transformation.operation must be constant_competing_rates")
    cycle_length = transformation.get("cycle_length_years")
    cycle_valid = (
        finite_number(cycle_length)
        and cycle_length > 0
        and finite_number(plan.get("cycle_length_years"))
        and isclose(
            float(cycle_length),
            float(plan["cycle_length_years"]),
            rel_tol=0.0,
            abs_tol=1e-12,
        )
    )
    if not cycle_valid:
        reasons.append("transformation cycle length must equal the analysis cycle length")
    declared_cycle = float(cycle_length) if finite_number(cycle_length) else 0.0
    states = plan.get("states")
    state_count = len(states) if isinstance(states, list) else 0
    cycles = plan.get("cycles")
    phases = transformation.get("phases")
    if (
        not isinstance(cycles, int)
        or isinstance(cycles, bool)
        or not isinstance(phases, list)
        or not 1 <= len(phases) <= cycles
    ):
        return reasons + ["transformation.phases count is invalid"]
    starts: list[int] = []
    matrices: list[list[list[float]]] = []
    used_extractions: set[str] = set()
    used_assumptions: set[str] = set()
    for phase_index, phase in enumerate(phases):
        phase_label = f"transformation.phases[{phase_index}]"
        if not isinstance(phase, dict) or set(phase) != {"start_cycle", "rows"}:
            reasons.append(f"{phase_label} fields are invalid")
            continue
        start = phase.get("start_cycle")
        if isinstance(start, bool) or not isinstance(start, int) or not 1 <= start <= cycles:
            reasons.append(f"{phase_label}.start_cycle is invalid")
            continue
        starts.append(start)
        rows = phase.get("rows")
        if not isinstance(rows, list) or len(rows) != state_count:
            reasons.append(f"{phase_label}.rows must contain {state_count} rows")
            continue
        matrix: list[list[float]] = []
        for row_index, row in enumerate(rows):
            row_label = f"{phase_label}.rows[{row_index}]"
            if not isinstance(row, dict) or set(row) != {"self_index", "events"}:
                reasons.append(f"{row_label} fields are invalid")
                continue
            if row.get("self_index") != row_index:
                reasons.append(f"{row_label}.self_index must equal the row position")
            events = row.get("events")
            if not isinstance(events, list) or len(events) > max(0, state_count - 1):
                reasons.append(f"{row_label}.events count is invalid")
                continue
            targets: set[int] = set()
            parsed: list[tuple[int, float]] = []
            total_rate = 0.0
            for event_index, event in enumerate(events):
                event_label = f"{row_label}.events[{event_index}]"
                allowed = {
                    "target_index", "rate_per_year", "source_extraction_id",
                    "source_pointer", "assumption_id",
                }
                if not isinstance(event, dict) or set(event) - allowed:
                    reasons.append(f"{event_label} contains unsupported fields")
                    continue
                target_index = event.get("target_index")
                if (
                    isinstance(target_index, bool)
                    or not isinstance(target_index, int)
                    or not 0 <= target_index < state_count
                    or target_index == row_index
                    or target_index in targets
                ):
                    reasons.append(f"{event_label}.target_index is invalid or duplicated")
                    continue
                targets.add(target_index)
                rate = event.get("rate_per_year")
                if not finite_number(rate) or rate <= 0:
                    reasons.append(f"{event_label}.rate_per_year must be positive")
                    continue
                source_id = event.get("source_extraction_id")
                assumption_id = event.get("assumption_id")
                has_source = text(source_id)
                has_assumption = text(assumption_id)
                if has_source == has_assumption:
                    reasons.append(
                        f"{event_label} must declare one extraction or assumption basis"
                    )
                elif has_source:
                    used_extractions.add(source_id)
                    extraction = extraction_index.get(source_id)
                    if extraction is not None:
                        try:
                            extracted = strict_json(extraction.get("extracted_value"))
                            extracted = json_pointer(extracted, event.get("source_pointer", ""))
                        except (TypeError, ValueError, json.JSONDecodeError) as error:
                            reasons.append(f"{event_label}: {error}")
                        else:
                            if not json_equivalent(extracted, rate):
                                reasons.append(
                                    f"{event_label}.rate_per_year does not match the bound extraction"
                                )
                else:
                    used_assumptions.add(assumption_id)
                    if "source_pointer" in event:
                        reasons.append(f"{event_label}.source_pointer requires an extraction")
                total_rate += float(rate)
                parsed.append((target_index, float(rate)))
            output_row = [0.0] * state_count
            if total_rate == 0:
                if state_count:
                    output_row[row_index] = 1.0
            else:
                event_mass = -expm1(-total_rate * declared_cycle)
                output_row[row_index] = 1.0 - event_mass
                for target_index, rate in parsed:
                    output_row[target_index] = event_mass * rate / total_rate
            matrix.append(output_row)
        if len(matrix) == state_count:
            matrices.append(matrix)
    if not starts or starts[0] != 1 or any(a >= b for a, b in zip(starts, starts[1:])):
        reasons.append("transformation phases must start at cycle 1 and strictly increase")
    output: Any = None
    if path.endswith(".transition_matrix"):
        if len(phases) != 1:
            reasons.append("a static matrix transformation requires exactly one phase")
        elif matrices:
            output = matrices[0]
    elif len(matrices) == len(starts):
        output = [
            {"start_cycle": start, "matrix": matrix}
            for start, matrix in zip(starts, matrices)
        ]
    target = model_value(plan, path)
    if output is None or not json_equivalent(output, target):
        reasons.append("constant competing rates do not reproduce the current transition input")
    selected_extractions = set(texts(mapping.get("extraction_ids")) or [])
    selected_assumptions = set(texts(mapping.get("assumption_ids")) or [])
    if used_extractions != selected_extractions:
        reasons.append("transformation must use every selected extraction")
    if used_assumptions != selected_assumptions:
        reasons.append("transformation must use every proposed assumption")
    return reasons


def derivation_reasons(
    plan: dict[str, Any],
    path: str,
    mapping: dict[str, Any],
    extraction_index: dict[str, dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    derivation = mapping.get("derivation")
    if not isinstance(derivation, dict):
        return ["derivation must be an object"]
    target = model_value(plan, path)
    if target is None:
        reasons.append("current model input is missing or null")
    if target is None or "model_value" not in derivation or not json_equivalent(
        derivation.get("model_value"), target
    ):
        reasons.append("derivation.model_value does not match the current model input")
    source_ids = texts(mapping.get("source_ids")) or []
    extraction_ids = texts(mapping.get("extraction_ids")) or []
    assumption_ids = texts(mapping.get("assumption_ids")) or []
    method = derivation.get("method")
    if method == "deterministic_transformation":
        reasons.extend(
            transition_rate_reasons(plan, path, mapping, derivation, extraction_index)
        )
        return reasons
    if not source_ids:
        if method != "explicit_assumption":
            reasons.append("assumption-only input must use derivation method explicit_assumption")
        if extraction_ids:
            reasons.append("explicit_assumption derivation must not claim extraction IDs")
        if not assumption_ids:
            reasons.append("explicit_assumption derivation requires a proposed assumption")
        return reasons
    expected_method = "monetary_adjustment" if (
        path.endswith("state_costs") or path == "willingness_to_pay"
    ) else "direct_evidence"
    if method != expected_method:
        reasons.append(f"source-based input must use derivation method {expected_method}")
        return reasons
    if method == "direct_evidence":
        if len(extraction_ids) != 1:
            reasons.append("direct_evidence requires exactly one extraction")
        else:
            extraction = extraction_index.get(extraction_ids[0])
            if extraction is not None:
                try:
                    extracted = strict_json(extraction.get("extracted_value"))
                except (TypeError, ValueError, json.JSONDecodeError):
                    reasons.append(
                        f"{extraction_ids[0]}.extracted_value must be strict JSON"
                    )
                else:
                    if not json_equivalent(extracted, target):
                        reasons.append(
                            f"{extraction_ids[0]}.extracted_value does not equal the model input"
                        )
    return reasons


def monetary_reasons(
    plan: dict[str, Any],
    path: str,
    mapping: dict[str, Any],
    economic_basis: dict[str, Any] | None,
    valid_basis_ids: set[str],
    extraction_index: dict[str, dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if economic_basis is None:
        return ["current economic_basis is missing or invalid"]
    currency = economic_basis["currency"]
    price_year = economic_basis["price_year"]
    if mapping.get("currency") != currency:
        reasons.append("currency does not match economic_basis.currency")
    if mapping.get("price_year") != price_year:
        reasons.append("price_year does not match economic_basis.price_year")

    target = model_value(plan, path)
    target_values = target if isinstance(target, list) else [target]
    if not target_values or any(not finite_number(value) or value < 0 for value in target_values):
        return reasons + ["model monetary value is missing, non-finite, or negative"]
    adjustments = mapping.get("monetary_adjustments")
    if not isinstance(adjustments, list) or len(adjustments) != len(target_values):
        return reasons + ["monetary_adjustments must cover every model value exactly once"]

    seen: set[int] = set()
    source_based = bool(texts(mapping.get("source_ids")) or [])
    extraction_ids = set(texts(mapping.get("extraction_ids")) or [])
    used_extractions: set[str] = set()
    for position, adjustment in enumerate(adjustments):
        label = f"monetary_adjustments[{position}]"
        if not isinstance(adjustment, dict):
            reasons.append(f"{label} must be an object")
            continue
        if isinstance(target, list):
            target_index = adjustment.get("target_index")
            if (isinstance(target_index, bool) or not isinstance(target_index, int)
                    or not 0 <= target_index < len(target_values)):
                reasons.append(f"{label}.target_index is invalid")
                continue
        else:
            if "target_index" in adjustment:
                reasons.append(f"{label}.target_index must be omitted for a scalar")
            target_index = 0
        if target_index in seen:
            reasons.append(f"{label}.target_index is duplicated")
            continue
        seen.add(target_index)
        source_value = adjustment.get("source_value")
        factor = adjustment.get("factor")
        if not finite_number(source_value) or source_value < 0:
            reasons.append(f"{label}.source_value must be finite and non-negative")
            continue
        if not finite_number(factor) or factor <= 0:
            reasons.append(f"{label}.factor must be finite and positive")
            continue
        source_extraction_id = adjustment.get("source_extraction_id")
        source_index = adjustment.get("source_index")
        if source_based:
            if not text(source_extraction_id) or source_extraction_id not in extraction_ids:
                reasons.append(f"{label}.source_extraction_id must reference a selected extraction")
            else:
                used_extractions.add(source_extraction_id)
                extraction = extraction_index.get(source_extraction_id)
                if extraction is not None:
                    try:
                        extracted = strict_json(extraction.get("extracted_value"))
                    except (TypeError, ValueError, json.JSONDecodeError):
                        reasons.append(
                            f"{label} source extraction must contain strict JSON"
                        )
                    else:
                        if isinstance(extracted, list):
                            if (
                                isinstance(source_index, bool)
                                or not isinstance(source_index, int)
                                or not 0 <= source_index < len(extracted)
                            ):
                                reasons.append(f"{label}.source_index is invalid")
                                extracted_source = None
                            else:
                                extracted_source = extracted[source_index]
                        else:
                            if "source_index" in adjustment:
                                reasons.append(
                                    f"{label}.source_index must be omitted for a scalar extraction"
                                )
                            extracted_source = extracted
                        if extracted_source is not None and not json_equivalent(
                            extracted_source, source_value
                        ):
                            reasons.append(
                                f"{label}.source_value does not match the bound extraction"
                            )
        elif "source_extraction_id" in adjustment or "source_index" in adjustment:
            reasons.append(
                f"{label} must not bind an extraction for an assumption-only input"
            )
        if not currency_code(adjustment.get("source_currency")):
            reasons.append(f"{label}.source_currency must be an ISO 4217-format code")
        source_year = adjustment.get("source_price_year")
        if (isinstance(source_year, bool) or not isinstance(source_year, int)
                or not 1900 <= source_year <= 2100):
            reasons.append(f"{label}.source_price_year must be from 1900 to 2100")
        if not isclose(source_value * factor, target_values[target_index], rel_tol=1e-9, abs_tol=1e-6):
            reasons.append(f"{label} does not reproduce model value")
        same_basis = adjustment.get("source_currency") == currency and source_year == price_year
        method = adjustment.get("method")
        basis_ids = texts(adjustment.get("basis_ids"))
        if basis_ids is None:
            reasons.append(f"{label}.basis_ids must be an array")
            basis_ids = []
        if same_basis and isclose(float(factor), 1.0, rel_tol=0.0, abs_tol=1e-12):
            if method != "none" or basis_ids:
                reasons.append(f"{label} must use method none and no basis_ids when no adjustment is needed")
        else:
            if not text(method) or str(method).strip().lower() == "none":
                reasons.append(f"{label}.method must explain the applied adjustment")
            if not basis_ids or any(item not in valid_basis_ids for item in basis_ids):
                reasons.append(f"{label}.basis_ids must link valid evidence or proposed assumptions")
    if seen != set(range(len(target_values))):
        reasons.append("monetary_adjustments do not cover every target index")
    if source_based and used_extractions != extraction_ids:
        reasons.append("monetary_adjustments must use every selected extraction")
    return reasons


def audit(plan: Any, synthesis: Any, synthesis_sha256: str) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(plan, dict) or not isinstance(synthesis, dict):
        return {"complete": False, "errors": ["plan and synthesis must be JSON objects"]}
    if plan.get("schema_version") not in APPROVABLE_ANALYSIS_SCHEMAS:
        errors.append("schema_version must be 0.3.0, 0.4.0, or 0.5.0 for approval review")
    for role in ("comparator", "intervention"):
        strategy = (plan.get("strategies") or {}).get(role) or {}
        has_matrix = isinstance(strategy, dict) and strategy.get("transition_matrix") is not None
        has_schedule = isinstance(strategy, dict) and strategy.get("transition_schedule") is not None
        if has_matrix == has_schedule:
            errors.append(
                f"strategies.{role} must define exactly one of transition_matrix or transition_schedule"
            )
        if has_schedule and plan.get("schema_version") not in {"0.4.0", "0.5.0"}:
            errors.append(
                f"strategies.{role}.transition_schedule requires schema_version 0.4.0 or 0.5.0"
            )
    basis_value = plan.get("economic_basis")
    economic_basis = basis_value if isinstance(basis_value, dict) else None
    if economic_basis is None or not currency_code(economic_basis.get("currency")):
        errors.append("economic_basis.currency must be an ISO 4217-format code")
        economic_basis = None
    elif (isinstance(economic_basis.get("price_year"), bool)
            or not isinstance(economic_basis.get("price_year"), int)
            or not 1900 <= economic_basis["price_year"] <= 2100):
        errors.append("economic_basis.price_year must be from 1900 to 2100")
        economic_basis = None
    required = required_paths(plan)
    if plan.get("willingness_to_pay") is not None:
        required.append("willingness_to_pay")
    required_set = set(required)

    mappings_value = plan.get("input_provenance")
    source_based = any(
        isinstance(mapping, dict) and bool(texts(mapping.get("source_ids")) or [])
        for mapping in (mappings_value if isinstance(mappings_value, list) else [])
    )
    if source_based:
        binding = plan.get("evidence_synthesis")
        if not isinstance(binding, dict) or binding.get("path") != "heor/evidence-synthesis.json":
            errors.append("evidence_synthesis.path must be heor/evidence-synthesis.json")
        elif binding.get("content_sha256") != synthesis_sha256:
            errors.append("evidence_synthesis.content_sha256 does not match exact synthesis bytes")

    sources = plan.get("evidence_sources")
    if not isinstance(sources, list):
        sources = []
        errors.append("evidence_sources must be an array")
    source_counts: dict[str, int] = {}
    valid_sources: set[str] = set()
    for source in sources:
        if isinstance(source, dict) and text(source.get("id")):
            source_counts[source["id"]] = source_counts.get(source["id"], 0) + 1
    for source in sources:
        if not isinstance(source, dict) or not text(source.get("id")):
            continue
        locator = text(source.get("url")) or text(source.get("local_path"))
        snapshot = not source.get("local_path") or (
            isinstance(source.get("content_sha256"), str)
            and len(source["content_sha256"]) == 64
            and all(char in "0123456789abcdef" for char in source["content_sha256"])
        )
        if (source_counts[source["id"]] == 1 and text(source.get("title"))
                and text(source.get("source_type")) and text(source.get("accessed_on"))
                and locator and snapshot):
            valid_sources.add(source["id"])

    assumptions = plan.get("assumptions") if isinstance(plan.get("assumptions"), list) else []
    assumption_status = {
        item["id"]: item.get("status") for item in assumptions
        if isinstance(item, dict) and text(item.get("id"))
        and text(item.get("statement")) and text(item.get("reason"))
    }
    unresolved = sorted(
        item.get("id", "unknown") for item in assumptions
        if isinstance(item, dict) and item.get("status") == "unresolved"
    )
    valid_basis_ids = valid_sources | {
        identifier for identifier, status in assumption_status.items() if status == "proposed"
    }

    records = synthesis.get("records") if isinstance(synthesis.get("records"), list) else []
    included = {
        item.get("record_id") for item in records if isinstance(item, dict)
        and isinstance(item.get("screening"), dict)
        and item["screening"].get("full_text") == "include"
    }
    extraction_index: dict[str, dict[str, Any]] = {}
    for item in synthesis.get("extractions", []):
        if (isinstance(item, dict) and text(item.get("extraction_id"))
                and item.get("record_id") in included
                and item.get("verification_status") != "conflict"):
            extraction_index[item["extraction_id"]] = item

    mappings = plan.get("input_provenance")
    if not isinstance(mappings, list):
        mappings = []
        errors.append("input_provenance must be an array")
    seen: set[str] = set()
    covered: set[str] = set()
    selected: set[str] = set()
    invalid: list[str] = []
    for mapping in mappings:
        if not isinstance(mapping, dict) or not text(mapping.get("path")):
            invalid.append("mapping omitted path")
            continue
        path = mapping["path"]
        reasons: list[str] = []
        if path not in required_set:
            reasons.append("path is not required")
        if path in seen:
            reasons.append("path is duplicated")
        seen.add(path)
        for field in ("unit", "jurisdiction", "selection_rationale"):
            if not text(mapping.get(field)):
                reasons.append(f"{field} is missing")
        if mapping.get("uncertainty_status") not in UNCERTAINTY:
            reasons.append("uncertainty_status is invalid")
        if path.endswith("state_costs") or path == "willingness_to_pay":
            reasons.extend(monetary_reasons(
                plan, path, mapping, economic_basis, valid_basis_ids, extraction_index
            ))
        source_ids = texts(mapping.get("source_ids")) or []
        assumption_ids = texts(mapping.get("assumption_ids")) or []
        extraction_ids = texts(mapping.get("extraction_ids")) or []
        if not source_ids and not assumption_ids:
            reasons.append("no evidence source or proposed assumption is linked")
        if any(source_id not in valid_sources for source_id in source_ids):
            reasons.append("source metadata is incomplete")
        if any(assumption_status.get(item) != "proposed" for item in assumption_ids):
            reasons.append("assumption is absent or not proposed")
        if source_ids:
            if not extraction_ids:
                reasons.append("source-based input has no extraction_ids")
            if len(extraction_ids) != len(set(extraction_ids)):
                reasons.append("extraction_ids are duplicated")
            for extraction_id in extraction_ids:
                selected.add(extraction_id)
                extraction = extraction_index.get(extraction_id)
                if not extraction:
                    reasons.append(f"{extraction_id} is absent, conflicting, or ineligible")
                elif extraction.get("target") != path:
                    reasons.append(f"{extraction_id} targets {extraction.get('target')}")
                elif extraction.get("record_id") not in source_ids:
                    reasons.append(f"{extraction_id} record_id is not a linked source")
        elif extraction_ids:
            reasons.append("assumption-only mapping must not claim extraction_ids")
        reasons.extend(derivation_reasons(plan, path, mapping, extraction_index))
        if reasons:
            invalid.append(f"{path}: {'; '.join(reasons)}")
        else:
            covered.add(path)

    unsupported = [path for path in required if path not in covered]
    complete = not errors and not invalid and not unresolved and not unsupported
    return {
        "complete": complete,
        "status": "structurally_ready_for_app_review" if complete else "incomplete",
        "required_inputs": len(required),
        "covered_inputs": len(covered),
        "selected_extraction_ids": sorted(selected),
        "unsupported_inputs": unsupported,
        "unresolved_assumptions": unresolved,
        "invalid_mappings": invalid,
        "errors": errors,
        "human_verification_checked": False,
        "required_app_reviewers_per_extraction": 2,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: validate_input_provenance.py ANALYSIS_PLAN.json EVIDENCE_SYNTHESIS.json", file=sys.stderr)
        return 2
    try:
        plan_path, synthesis_path = Path(argv[1]), Path(argv[2])
        plan = json.loads(plan_path.read_bytes())
        synthesis = json.loads(synthesis_path.read_bytes())
        result = audit(plan, synthesis, digest(synthesis_path))
    except (OSError, json.JSONDecodeError) as error:
        result = {"complete": False, "status": "incomplete", "errors": [str(error)]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("complete") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
