#!/usr/bin/env python3
"""Portable structural validator for an AI4HEOR budget impact plan."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path


HORIZON = 3
SHA256 = re.compile(r"^[a-f0-9]{64}$")
TARGET = re.compile(
    r"^/population/annual_eligible/[0-2]$"
    r"|^/market_scenarios/with_new_intervention/intervention_share_by_year/[0-2]$"
    r"|^/cost_categories/[0-9]+/annual_per_patient/(comparator|intervention)/[0-2]$"
    r"|^/non_patient_costs/[0-9]+/annual_total/(without_new_intervention|with_new_intervention)/[0-2]$"
)


def load(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value, raw


def text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def finite(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
    )


def finite_array(value: object, *, share: bool = False) -> bool:
    return (
        isinstance(value, list)
        and len(value) == HORIZON
        and all(
            finite(item) and item >= 0 and (not share or item <= 1)
            for item in value
        )
    )


def string_list(value: object, *, nonempty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (bool(value) or not nonempty)
        and all(text(item) for item in value)
        and len(value) == len(set(value))
    )


def objects(value: object) -> list[dict]:
    return value if isinstance(value, list) and all(isinstance(item, dict) for item in value) else []


def unique_ids(items: list[dict], field: str) -> bool:
    values = [item.get(field) for item in items]
    return all(text(value) for value in values) and len(values) == len(set(values))


def resolve_pointer(value: object, pointer: str) -> object:
    current = value
    for token in pointer[1:].split("/"):
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def required_paths(value: dict) -> set[str]:
    result = {f"/population/annual_eligible/{year}" for year in range(HORIZON)}
    result.update(
        f"/market_scenarios/with_new_intervention/intervention_share_by_year/{year}"
        for year in range(HORIZON)
    )
    for category_index, _ in enumerate(value.get("cost_categories") or []):
        for role in ("comparator", "intervention"):
            result.update(
                f"/cost_categories/{category_index}/annual_per_patient/{role}/{year}"
                for year in range(HORIZON)
            )
    for item_index, _ in enumerate(value.get("non_patient_costs") or []):
        for scenario in ("without_new_intervention", "with_new_intervention"):
            result.update(
                f"/non_patient_costs/{item_index}/annual_total/{scenario}/{year}"
                for year in range(HORIZON)
            )
    return result


def validate(budget_path: Path, analysis_path: Path) -> list[str]:
    value, _ = load(budget_path)
    analysis, analysis_raw = load(analysis_path)
    errors: list[str] = []

    if value.get("schema_version") != "0.1.0":
        errors.append("schema_version must be 0.1.0")
    for field in ("bia_id", "analysis_id"):
        if not text(value.get(field)):
            errors.append(f"{field} is required")
    if value.get("status") != "ready_for_human_review":
        errors.append("status must be ready_for_human_review")
    if value.get("analysis_id") != analysis.get("analysis_id"):
        errors.append("analysis_id does not match the analysis plan")
    base = value.get("base_analysis") or {}
    expected_hash = hashlib.sha256(analysis_raw).hexdigest()
    if base.get("path") != "heor/analysis-plan.json":
        errors.append("base_analysis.path must be heor/analysis-plan.json")
    if base.get("content_sha256") != expected_hash or not SHA256.fullmatch(
        str(base.get("content_sha256", ""))
    ):
        errors.append("base_analysis.content_sha256 does not match the plan bytes")
    if (analysis.get("budget_impact_analysis") or {}).get("path") != "heor/budget-impact-plan.json":
        errors.append("analysis plan must link heor/budget-impact-plan.json")

    perspective = value.get("perspective") or {}
    if perspective.get("type") != "budget_holder":
        errors.append("perspective.type must be budget_holder")
    for field in ("budget_holder", "jurisdiction", "currency", "alignment_rationale"):
        if not text(perspective.get(field)):
            errors.append(f"perspective.{field} is required")
    price_year = perspective.get("price_year")
    if isinstance(price_year, bool) or not isinstance(price_year, int) or not 1900 <= price_year <= 2100:
        errors.append("perspective.price_year must be from 1900 to 2100")
    plan_jurisdiction = (analysis.get("decision_problem") or {}).get("jurisdiction")
    if plan_jurisdiction and perspective.get("jurisdiction") != plan_jurisdiction:
        errors.append("jurisdiction does not match the analysis plan")
    if value.get("horizon_years") != HORIZON:
        errors.append("horizon_years must be exactly 3")
    if value.get("discount_rate") != 0 or isinstance(value.get("discount_rate"), bool):
        errors.append("discount_rate must be 0")

    population = value.get("population") or {}
    if not text(population.get("label")) or not text(population.get("derivation")):
        errors.append("population requires label and derivation")
    if not finite_array(population.get("annual_eligible")):
        errors.append("population.annual_eligible must contain three non-negative numbers")

    strategies = value.get("strategies") or {}
    analysis_strategies = analysis.get("strategies") or {}
    strategy_ids: list[object] = []
    for role in ("comparator", "intervention"):
        strategy = strategies.get(role) or {}
        strategy_ids.append(strategy.get("id"))
        if not text(strategy.get("id")) or not text(strategy.get("label")):
            errors.append(f"strategies.{role} requires id and label")
        if strategy.get("id") != (analysis_strategies.get(role) or {}).get("name"):
            errors.append(f"strategies.{role}.id must match the analysis plan")
    if len(set(strategy_ids)) != 2:
        errors.append("strategy ids must be different")

    markets = value.get("market_scenarios") or {}
    for name in ("without_new_intervention", "with_new_intervention"):
        market = markets.get(name) or {}
        if not text(market.get("label")):
            errors.append(f"market_scenarios.{name}.label is required")
        if not finite_array(market.get("intervention_share_by_year"), share=True):
            errors.append(f"market_scenarios.{name} shares must contain three probabilities")
    without = (markets.get("without_new_intervention") or {}).get("intervention_share_by_year")
    if isinstance(without, list) and any(abs(item) > 1e-9 for item in without if finite(item)):
        errors.append("without-new-intervention shares must be zero")

    categories = objects(value.get("cost_categories"))
    if not 2 <= len(categories) <= 64 or not unique_ids(categories, "id"):
        errors.append("cost_categories must contain 2-64 entries with unique ids")
    types: set[object] = set()
    for index, category in enumerate(categories):
        types.add(category.get("type"))
        if not text(category.get("label")) or not text(category.get("rationale")):
            errors.append(f"cost_categories[{index}] requires label and rationale")
        if category.get("type") not in {"intervention", "condition_related"}:
            errors.append(f"cost_categories[{index}].type is invalid")
        if category.get("included") is not True:
            errors.append(f"cost_categories[{index}] must be included")
        annual = category.get("annual_per_patient") or {}
        for role in ("comparator", "intervention"):
            if not finite_array(annual.get(role)):
                errors.append(f"cost_categories[{index}] {role} costs are invalid")
    if types != {"intervention", "condition_related"}:
        errors.append("both intervention and condition-related costs are required")

    exclusions = objects(value.get("excluded_cost_categories"))
    if value.get("excluded_cost_categories") is not None and not isinstance(value.get("excluded_cost_categories"), list):
        errors.append("excluded_cost_categories must be an array")
    for index, item in enumerate(exclusions):
        if not text(item.get("category")) or not text(item.get("rationale")):
            errors.append(f"excluded_cost_categories[{index}] is incomplete")

    non_patient = objects(value.get("non_patient_costs"))
    if not isinstance(value.get("non_patient_costs"), list) or len(non_patient) > 32 or not unique_ids(non_patient, "id"):
        errors.append("non_patient_costs must contain at most 32 entries with unique ids")
    for index, item in enumerate(non_patient):
        if item.get("type") != "implementation" or item.get("included") is not True:
            errors.append(f"non_patient_costs[{index}] must be an included implementation cost")
        if not text(item.get("label")) or not text(item.get("rationale")):
            errors.append(f"non_patient_costs[{index}] requires label and rationale")
        annual = item.get("annual_total") or {}
        for scenario in ("without_new_intervention", "with_new_intervention"):
            if not finite_array(annual.get(scenario)):
                errors.append(f"non_patient_costs[{index}] {scenario} totals are invalid")

    sources = objects(value.get("evidence_sources"))
    if not isinstance(value.get("evidence_sources"), list) or not unique_ids(sources, "id"):
        errors.append("evidence_sources must have unique ids")
    source_ids: set[str] = set()
    for index, source in enumerate(sources):
        if not all(text(source.get(field)) for field in ("id", "title", "source_type", "accessed_on")):
            errors.append(f"evidence_sources[{index}] metadata is incomplete")
        if not text(source.get("url")) and not text(source.get("local_path")):
            errors.append(f"evidence_sources[{index}] requires a locator")
        if text(source.get("local_path")) and not SHA256.fullmatch(str(source.get("content_sha256", ""))):
            errors.append(f"evidence_sources[{index}] local snapshot hash is invalid")
        if text(source.get("id")):
            source_ids.add(source["id"])

    assumptions = objects(value.get("assumptions"))
    if not isinstance(value.get("assumptions"), list) or not unique_ids(assumptions, "id"):
        errors.append("assumptions must have unique ids")
    assumption_status: dict[str, object] = {}
    for index, item in enumerate(assumptions):
        if not all(text(item.get(field)) for field in ("id", "statement", "reason")):
            errors.append(f"assumptions[{index}] metadata is incomplete")
        if item.get("status") not in {"unresolved", "proposed", "rejected"}:
            errors.append(f"assumptions[{index}].status is invalid")
        if item.get("status") == "unresolved":
            errors.append(f"assumptions[{index}] remains unresolved")
        if text(item.get("id")):
            assumption_status[item["id"]] = item.get("status")

    required = required_paths(value)
    mappings = objects(value.get("input_provenance"))
    seen: set[str] = set()
    for index, mapping in enumerate(mappings):
        path = mapping.get("path")
        reasons: list[str] = []
        if path not in required:
            reasons.append("path is not required")
        if path in seen:
            reasons.append("path is duplicated")
        if isinstance(path, str):
            seen.add(path)
        if not all(text(mapping.get(field)) for field in ("unit", "jurisdiction", "selection_rationale")):
            reasons.append("metadata is incomplete")
        if mapping.get("jurisdiction") != perspective.get("jurisdiction"):
            reasons.append("jurisdiction differs")
        if mapping.get("uncertainty_status") not in {"fixed", "range_available", "distribution_available"}:
            reasons.append("uncertainty status is invalid")
        if isinstance(path, str) and (path.startswith("/cost_categories/") or path.startswith("/non_patient_costs/")):
            year = mapping.get("price_year")
            if isinstance(year, bool) or not isinstance(year, int) or not 1900 <= year <= 2100:
                reasons.append("price year is invalid")
        linked_sources = mapping.get("source_ids") or []
        linked_assumptions = mapping.get("assumption_ids") or []
        if not string_list(linked_sources) or not string_list(linked_assumptions):
            reasons.append("basis id arrays are invalid")
        if not linked_sources and not linked_assumptions:
            reasons.append("no evidence or assumption is linked")
        if any(item not in source_ids for item in linked_sources):
            reasons.append("unknown source")
        if any(assumption_status.get(item) != "proposed" for item in linked_assumptions):
            reasons.append("assumption is not proposed")
        if reasons:
            errors.append(f"input_provenance[{index}]: {'; '.join(reasons)}")
    missing = sorted(required - seen)
    if missing:
        errors.append(f"required inputs lack provenance: {', '.join(missing[:5])}")

    allowed_basis = source_ids | {
        item for item, status in assumption_status.items() if status == "proposed"
    }
    sensitivity = objects(value.get("sensitivity_parameters"))
    if not 1 <= len(sensitivity) <= 128 or not unique_ids(sensitivity, "id"):
        errors.append("sensitivity_parameters must contain 1-128 entries with unique ids")
    sensitivity_targets: set[str] = set()
    for index, parameter in enumerate(sensitivity):
        target = parameter.get("target")
        if not text(parameter.get("label")) or not text(target) or not TARGET.fullmatch(target):
            errors.append(f"sensitivity_parameters[{index}] metadata or target is invalid")
            continue
        if target in sensitivity_targets:
            errors.append(f"sensitivity_parameters[{index}].target is duplicated")
        sensitivity_targets.add(target)
        try:
            base_value = resolve_pointer(value, target)
        except (KeyError, IndexError, TypeError, ValueError):
            errors.append(f"sensitivity_parameters[{index}].target does not exist")
            continue
        low, high = parameter.get("low"), parameter.get("high")
        if not finite(base_value) or not finite(low) or not finite(high) or low > base_value or high < base_value or low == high:
            errors.append(f"sensitivity_parameters[{index}] must bracket the base value")
        if "share_by_year" in target and (low < 0 or high > 1):
            errors.append(f"sensitivity_parameters[{index}] share range is invalid")
        if not string_list(parameter.get("basis_ids"), nonempty=True) or not set(parameter.get("basis_ids") or []).issubset(allowed_basis):
            errors.append(f"sensitivity_parameters[{index}].basis_ids are invalid")

    scenarios = objects(value.get("alternative_scenarios"))
    if not 1 <= len(scenarios) <= 32 or not unique_ids(scenarios, "scenario_id"):
        errors.append("alternative_scenarios must contain 1-32 entries with unique ids")
    for index, scenario in enumerate(scenarios):
        if not text(scenario.get("label")) or not text(scenario.get("rationale")):
            errors.append(f"alternative_scenarios[{index}] metadata is incomplete")
        if not string_list(scenario.get("basis_ids"), nonempty=True) or not set(scenario.get("basis_ids") or []).issubset(allowed_basis):
            errors.append(f"alternative_scenarios[{index}].basis_ids are invalid")
        overrides = objects(scenario.get("overrides"))
        targets: set[str] = set()
        if not overrides:
            errors.append(f"alternative_scenarios[{index}].overrides must not be empty")
        for override_index, override in enumerate(overrides):
            target = override.get("target")
            replacement = override.get("value")
            if not text(target) or not TARGET.fullmatch(target) or target in targets:
                errors.append(f"alternative_scenarios[{index}].overrides[{override_index}] target is invalid")
                continue
            targets.add(target)
            try:
                resolve_pointer(value, target)
            except (KeyError, IndexError, TypeError, ValueError):
                errors.append(f"alternative_scenarios[{index}].overrides[{override_index}] target does not exist")
            if not finite(replacement) or replacement < 0 or ("share_by_year" in target and replacement > 1):
                errors.append(f"alternative_scenarios[{index}].overrides[{override_index}] value is invalid")

    validation = value.get("validation_plan") or {}
    for field in ("face", "internal", "external"):
        if not string_list(validation.get(field), nonempty=True):
            errors.append(f"validation_plan.{field} must be a non-empty string array")
    if not string_list(value.get("limitations"), nonempty=True):
        errors.append("limitations must be a non-empty string array")
    return errors


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(
            "usage: validate_budget_impact_plan.py BUDGET_IMPACT_PLAN ANALYSIS_PLAN",
            file=sys.stderr,
        )
        return 2
    try:
        errors = validate(Path(argv[1]), Path(argv[2]))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"invalid: {error}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"invalid: {error}", file=sys.stderr)
        return 1
    print("valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
