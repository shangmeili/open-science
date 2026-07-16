#!/usr/bin/env python3
"""Portable structural validator for AI4HEOR dynamic budget impact schema 0.2.0."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path


HORIZON = 3
SHA256 = re.compile(r"^[a-f0-9]{64}$")
STRATEGY_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SCENARIOS = ("without_new_intervention", "with_new_intervention")


def load(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value, raw


def text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def finite(value: object, *, probability: bool = False) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(value)
        and value >= 0
        and (not probability or value <= 1)
    )


def annual(value: object, *, probability: bool = False) -> bool:
    return (
        isinstance(value, list)
        and len(value) == HORIZON
        and all(finite(item, probability=probability) for item in value)
    )


def objects(value: object) -> list[dict]:
    return (
        value
        if isinstance(value, list) and all(isinstance(item, dict) for item in value)
        else []
    )


def string_list(value: object, *, nonempty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (bool(value) or not nonempty)
        and all(text(item) for item in value)
        and len(value) == len(set(value))
    )


def unique(items: list[dict], field: str) -> bool:
    values = [item.get(field) for item in items]
    return all(text(value) for value in values) and len(values) == len(set(values))


def required_paths(value: dict) -> set[str]:
    paths = {"/population/initial_prevalent"}
    paths.update(f"/population/incident_by_year/{year}" for year in range(HORIZON))
    paths.update(f"/annual_mortality_probability/{year}" for year in range(HORIZON))
    for scenario in SCENARIOS:
        paths.add(f"/market_scenarios/{scenario}/initial_intervention_share")
        for field in (
            "incident_intervention_share_by_year",
            "comparator_displacement_share_by_year",
            "intervention_start_capacity_by_year",
        ):
            paths.update(
                f"/market_scenarios/{scenario}/{field}/{year}"
                for year in range(HORIZON)
            )
    for role in ("comparator", "intervention"):
        paths.update(
            f"/persistence/{role}_continuation_probability_by_year/{year}"
            for year in range(HORIZON)
        )
    for index, _ in enumerate(value.get("cost_categories") or []):
        for role in ("comparator", "intervention"):
            paths.update(
                f"/cost_categories/{index}/annual_per_patient/{role}/{year}"
                for year in range(HORIZON)
            )
    for index, _ in enumerate(value.get("non_patient_costs") or []):
        for scenario in SCENARIOS:
            paths.update(
                f"/non_patient_costs/{index}/annual_total/{scenario}/{year}"
                for year in range(HORIZON)
            )
    return paths


def resolve(value: object, pointer: str) -> object:
    current = value
    for token in pointer[1:].split("/"):
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def probability_target(path: str) -> bool:
    return (
        path.startswith("/annual_mortality_probability/")
        or path.startswith("/persistence/")
        or (
            path.startswith("/market_scenarios/")
            and "intervention_start_capacity_by_year" not in path
        )
    )


def validate(budget_path: Path, analysis_path: Path) -> list[str]:
    value, _ = load(budget_path)
    analysis, analysis_raw = load(analysis_path)
    errors: list[str] = []

    if value.get("schema_version") != "0.2.0":
        errors.append("schema_version must be 0.2.0")
    if value.get("status") != "ready_for_human_review":
        errors.append("status must be ready_for_human_review")
    for field in ("bia_id", "analysis_id"):
        if not text(value.get(field)):
            errors.append(f"{field} is required")
    if value.get("analysis_id") != analysis.get("analysis_id"):
        errors.append("analysis_id does not match the analysis plan")
    base = value.get("base_analysis") or {}
    digest = hashlib.sha256(analysis_raw).hexdigest()
    if base.get("path") != "heor/analysis-plan.json" or base.get("content_sha256") != digest:
        errors.append("base_analysis must bind the exact analysis-plan bytes")
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
    jurisdiction = (analysis.get("decision_problem") or {}).get("jurisdiction")
    if jurisdiction and perspective.get("jurisdiction") != jurisdiction:
        errors.append("jurisdiction does not match the analysis plan")
    if value.get("horizon_years") != HORIZON or isinstance(value.get("horizon_years"), bool):
        errors.append("horizon_years must be exactly 3")
    if value.get("discount_rate") != 0 or isinstance(value.get("discount_rate"), bool):
        errors.append("discount_rate must be 0")

    population = value.get("population") or {}
    if not text(population.get("label")) or not text(population.get("derivation")):
        errors.append("population requires label and derivation")
    if not finite(population.get("initial_prevalent")):
        errors.append("population.initial_prevalent must be non-negative")
    if not annual(population.get("incident_by_year")):
        errors.append("population.incident_by_year must contain three non-negative numbers")
    if not annual(value.get("annual_mortality_probability"), probability=True):
        errors.append("annual_mortality_probability must contain three probabilities")

    strategies = value.get("strategies") or {}
    plan_strategies = analysis.get("strategies") or {}
    strategy_order = analysis.get("strategy_order") or []
    multi = analysis.get("schema_version") in {
        "0.8.0", "0.9.0", "0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0"
    }
    ids: list[object] = []
    for role in ("comparator", "intervention"):
        strategy = strategies.get(role) or {}
        strategy_id = strategy.get("id")
        ids.append(strategy_id)
        if not text(strategy_id) or not text(strategy.get("label")):
            errors.append(f"strategies.{role} requires id and label")
        if multi and (
            not isinstance(strategy_id, str)
            or STRATEGY_ID.fullmatch(strategy_id) is None
            or strategy_id not in strategy_order
        ):
            errors.append(f"strategies.{role}.id must select an analysis strategy")
        if not multi and strategy_id != (plan_strategies.get(role) or {}).get("name"):
            errors.append(f"strategies.{role}.id must match the analysis plan")
    if len(set(item for item in ids if isinstance(item, str))) != 2:
        errors.append("strategy ids must be different")

    markets = value.get("market_scenarios") or {}
    for scenario_name in SCENARIOS:
        scenario = markets.get(scenario_name) or {}
        if not text(scenario.get("label")):
            errors.append(f"market_scenarios.{scenario_name}.label is required")
        if not finite(scenario.get("initial_intervention_share"), probability=True):
            errors.append(f"market_scenarios.{scenario_name}.initial_intervention_share is invalid")
        for field in ("incident_intervention_share_by_year", "comparator_displacement_share_by_year"):
            if not annual(scenario.get(field), probability=True):
                errors.append(f"market_scenarios.{scenario_name}.{field} is invalid")
        if not annual(scenario.get("intervention_start_capacity_by_year")):
            errors.append(f"market_scenarios.{scenario_name}.intervention_start_capacity_by_year is invalid")
    without = markets.get("without_new_intervention") or {}
    zero_fields = [without.get("initial_intervention_share")]
    for field in ("incident_intervention_share_by_year", "comparator_displacement_share_by_year", "intervention_start_capacity_by_year"):
        if isinstance(without.get(field), list):
            zero_fields.extend(without[field])
    if any(finite(item) and abs(float(item)) > 1e-9 for item in zero_fields):
        errors.append("without-new-intervention flow inputs must be zero")

    persistence = value.get("persistence") or {}
    for role in ("comparator", "intervention"):
        if not annual(persistence.get(f"{role}_continuation_probability_by_year"), probability=True):
            errors.append(f"persistence.{role} continuation is invalid")
    if persistence.get("comparator_discontinuation_destination") != "exit_treated_market":
        errors.append("comparator discontinuation destination must be exit_treated_market")
    if persistence.get("intervention_discontinuation_destination") != "comparator":
        errors.append("intervention discontinuation destination must be comparator")

    categories = objects(value.get("cost_categories"))
    if not 2 <= len(categories) <= 64 or not unique(categories, "id"):
        errors.append("cost_categories must contain 2-64 unique entries")
    types: set[object] = set()
    for index, category in enumerate(categories):
        types.add(category.get("type"))
        if category.get("type") not in {"intervention", "condition_related"} or category.get("included") is not True:
            errors.append(f"cost_categories[{index}] type or included state is invalid")
        if not text(category.get("label")) or not text(category.get("rationale")):
            errors.append(f"cost_categories[{index}] metadata is incomplete")
        annual_cost = category.get("annual_per_patient") or {}
        for role in ("comparator", "intervention"):
            if not annual(annual_cost.get(role)):
                errors.append(f"cost_categories[{index}] {role} costs are invalid")
    if types != {"intervention", "condition_related"}:
        errors.append("both intervention and condition-related costs are required")

    non_patient = objects(value.get("non_patient_costs"))
    if not isinstance(value.get("non_patient_costs"), list) or len(non_patient) > 32 or not unique(non_patient, "id"):
        errors.append("non_patient_costs must contain at most 32 unique entries")
    for index, item in enumerate(non_patient):
        if item.get("type") != "implementation" or item.get("included") is not True:
            errors.append(f"non_patient_costs[{index}] must be included implementation cost")
        for scenario in SCENARIOS:
            if not annual((item.get("annual_total") or {}).get(scenario)):
                errors.append(f"non_patient_costs[{index}] {scenario} totals are invalid")

    sources = objects(value.get("evidence_sources"))
    assumptions = objects(value.get("assumptions"))
    if not isinstance(value.get("evidence_sources"), list) or not unique(sources, "id"):
        errors.append("evidence_sources must have unique ids")
    if not isinstance(value.get("assumptions"), list) or not unique(assumptions, "id"):
        errors.append("assumptions must have unique ids")
    source_ids = {item.get("id") for item in sources if text(item.get("id"))}
    proposed_ids = {
        item.get("id") for item in assumptions
        if text(item.get("id")) and item.get("status") == "proposed"
    }
    for index, source in enumerate(sources):
        if not all(text(source.get(field)) for field in ("id", "title", "source_type", "accessed_on")):
            errors.append(f"evidence_sources[{index}] metadata is incomplete")
        if not text(source.get("url")) and not text(source.get("local_path")):
            errors.append(f"evidence_sources[{index}] requires url or local_path")
        if text(source.get("local_path")) and SHA256.fullmatch(str(source.get("content_sha256", ""))) is None:
            errors.append(f"evidence_sources[{index}] local hash is invalid")
    for index, item in enumerate(assumptions):
        if not all(text(item.get(field)) for field in ("id", "statement", "reason")):
            errors.append(f"assumptions[{index}] metadata is incomplete")
        if item.get("status") not in {"proposed", "rejected"}:
            errors.append(f"assumptions[{index}] status is invalid or unresolved")

    required = required_paths(value)
    provenance = objects(value.get("input_provenance"))
    seen: set[str] = set()
    for index, item in enumerate(provenance):
        path = item.get("path")
        if path not in required or path in seen:
            errors.append(f"input_provenance[{index}] path is invalid or duplicate")
            continue
        seen.add(path)
        if not all(text(item.get(field)) for field in ("unit", "jurisdiction", "selection_rationale")):
            errors.append(f"input_provenance[{index}] metadata is incomplete")
        if item.get("jurisdiction") != perspective.get("jurisdiction"):
            errors.append(f"input_provenance[{index}] jurisdiction does not match")
        if item.get("uncertainty_status") not in {"fixed", "range_available", "distribution_available"}:
            errors.append(f"input_provenance[{index}] uncertainty status is invalid")
        if path.startswith("/cost_categories/") or path.startswith("/non_patient_costs/"):
            year = item.get("price_year")
            if isinstance(year, bool) or not isinstance(year, int) or not 1900 <= year <= 2100:
                errors.append(f"input_provenance[{index}] price_year is invalid")
        linked_sources = item.get("source_ids") or []
        linked_assumptions = item.get("assumption_ids") or []
        if not string_list(linked_sources) or not string_list(linked_assumptions):
            errors.append(f"input_provenance[{index}] basis lists are invalid")
        if not linked_sources and not linked_assumptions:
            errors.append(f"input_provenance[{index}] requires evidence or assumption")
        if any(source not in source_ids for source in linked_sources) or any(assumption not in proposed_ids for assumption in linked_assumptions):
            errors.append(f"input_provenance[{index}] references an unknown basis")
    if required != seen:
        errors.append(f"input provenance coverage is incomplete: {len(required - seen)} missing")

    allowed_targets = {
        path
        for path in required
        if not path.startswith("/market_scenarios/without_new_intervention/")
    }
    sensitivities = objects(value.get("sensitivity_parameters"))
    if not 1 <= len(sensitivities) <= 128 or not unique(sensitivities, "id"):
        errors.append("sensitivity_parameters must contain 1-128 unique entries")
    for index, item in enumerate(sensitivities):
        target = item.get("target")
        try:
            base_value = resolve(value, target) if target in allowed_targets else None
        except (KeyError, IndexError, TypeError, ValueError):
            base_value = None
        low, high = item.get("low"), item.get("high")
        if not text(item.get("label")) or base_value is None:
            errors.append(f"sensitivity_parameters[{index}] target is invalid")
        elif not finite(low, probability=probability_target(target)) or not finite(high, probability=probability_target(target)) or low > base_value or high < base_value or low == high:
            errors.append(f"sensitivity_parameters[{index}] range is invalid")
        basis = item.get("basis_ids")
        if not string_list(basis, nonempty=True) or any(item_id not in source_ids | proposed_ids for item_id in (basis or [])):
            errors.append(f"sensitivity_parameters[{index}] basis is invalid")

    scenarios = objects(value.get("alternative_scenarios"))
    if not 1 <= len(scenarios) <= 32 or not unique(scenarios, "scenario_id"):
        errors.append("alternative_scenarios must contain 1-32 unique entries")
    for index, scenario in enumerate(scenarios):
        if not text(scenario.get("label")) or not text(scenario.get("rationale")):
            errors.append(f"alternative_scenarios[{index}] metadata is incomplete")
        overrides = objects(scenario.get("overrides"))
        targets: set[str] = set()
        if not overrides:
            errors.append(f"alternative_scenarios[{index}] overrides are required")
        for override in overrides:
            target = override.get("target")
            number = override.get("value")
            if target not in allowed_targets or target in targets or not finite(number, probability=probability_target(str(target))):
                errors.append(f"alternative_scenarios[{index}] override is invalid")
            targets.add(str(target))
        basis = scenario.get("basis_ids")
        if not string_list(basis, nonempty=True) or any(item_id not in source_ids | proposed_ids for item_id in (basis or [])):
            errors.append(f"alternative_scenarios[{index}] basis is invalid")

    validation = value.get("validation_plan") or {}
    for field in ("face", "internal", "external"):
        if not string_list(validation.get(field), nonempty=True):
            errors.append(f"validation_plan.{field} must not be empty")
    if not string_list(value.get("limitations"), nonempty=True):
        errors.append("limitations must not be empty")
    return errors


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: validate_dynamic_budget_impact_plan.py BUDGET_PLAN ANALYSIS_PLAN", file=sys.stderr)
        return 2
    try:
        errors = validate(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"dynamic budget impact validation failed: {error}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("dynamic budget impact plan is structurally valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
