#!/usr/bin/env python3
"""Audit portable evidence-to-input links; app-owned verification remains external."""

from __future__ import annotations

import json
import sys
from hashlib import sha256
from math import isclose, isfinite
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
CURRENT_ANALYSIS_SCHEMA = "0.3.0"


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
    if plan.get("schema_version") != CURRENT_ANALYSIS_SCHEMA:
        errors.append(f"schema_version must be {CURRENT_ANALYSIS_SCHEMA} for approval review")
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
    required = list(BASE_PATHS)
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
