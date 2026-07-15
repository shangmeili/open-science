#!/usr/bin/env python3
"""Validate and recalculate AI4HEOR cost-input normalization 0.1.0."""

from __future__ import annotations

import argparse
import hashlib
import json
from math import isclose, isfinite
from pathlib import Path
import re
from typing import Any


SAFE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
ADJUSTMENTS = {"inflation", "currency_conversion", "price_adjustment"}
PRICE_BASES = {"list_price", "net_price", "tariff", "paid_price", "negotiated_price", "microcost", "opportunity_cost", "other"}


def exact_fields(value: Any, expected: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == expected


def nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def currency(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[A-Z]{3}", value) is not None


def year(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 1900 <= value <= 2100


def number(value: Any, *, positive: bool = False, nonnegative: bool = False) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
        return False
    return (not positive or float(value) > 0) and (not nonnegative or float(value) >= 0)


def strings(value: Any) -> list[str] | None:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        return None
    return value


def basis_ids(plan: dict[str, Any]) -> set[str]:
    values = {
        item["id"] for item in plan.get("evidence_sources", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    values.update(
        item["id"] for item in plan.get("assumptions", [])
        if isinstance(item, dict) and item.get("status") == "proposed" and isinstance(item.get("id"), str)
    )
    for mapping in plan.get("input_provenance", []):
        if isinstance(mapping, dict):
            for field in ("source_ids", "extraction_ids", "assumption_ids"):
                if isinstance(mapping.get(field), list):
                    values.update(item for item in mapping[field] if isinstance(item, str) and item)
    return values


def validate(plan: dict[str, Any], raw: bytes, artifact: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not exact_fields(artifact, {
        "schema_version", "normalization_id", "analysis_id", "status",
        "base_analysis", "target_basis", "item_order", "items",
        "annual_state_costs", "limitations",
    }):
        errors.append("cost-input normalization fields are not the exact contract")
    if plan.get("schema_version") not in {"0.12.0", "0.13.0", "0.14.0"}:
        errors.append("analysis schema_version must be 0.12.0 through 0.14.0")
    if artifact.get("schema_version") != "0.1.0":
        errors.append("cost-input normalization schema_version must be 0.1.0")
    if not isinstance(artifact.get("normalization_id"), str) or SAFE_ID.fullmatch(artifact["normalization_id"]) is None:
        errors.append("normalization_id must be a safe lowercase id")
    if artifact.get("analysis_id") != plan.get("analysis_id"):
        errors.append("analysis_id does not match the analysis plan")
    if artifact.get("status") != "ready_for_human_review":
        errors.append("status must be ready_for_human_review")
    binding = artifact.get("base_analysis")
    if not isinstance(binding, dict) or binding.get("path") != "heor/analysis-plan.json" or binding.get("content_sha256") != hashlib.sha256(raw).hexdigest():
        errors.append("base_analysis must bind the exact current analysis bytes")
    target = artifact.get("target_basis")
    decision = plan.get("decision_problem", {})
    economic = plan.get("economic_basis", {})
    if not exact_fields(target, {"currency", "price_year", "jurisdiction", "perspective"}) or target != {
        "currency": economic.get("currency"),
        "price_year": economic.get("price_year"),
        "jurisdiction": decision.get("jurisdiction"),
        "perspective": decision.get("perspective"),
    } or not currency(target.get("currency")) or not year(target.get("price_year")) or not nonempty(target.get("jurisdiction")) or not nonempty(target.get("perspective")):
        errors.append("target_basis must exactly match economic_basis and decision problem")
    order = strings(plan.get("strategy_order")) or []
    states = strings(plan.get("states")) or []
    strategies = plan.get("strategies", {})
    if not order or not states or not isinstance(strategies, dict) or set(strategies) != set(order):
        errors.append("analysis strategy_order, states, and strategies are inconsistent")
    item_order = strings(artifact.get("item_order")) or []
    if not 1 <= len(item_order) <= 1000 or len(item_order) != len(set(item_order)) or any(SAFE_ID.fullmatch(item) is None for item in item_order):
        errors.append("item_order must contain 1-1000 unique safe ids")
        item_order = []
    items = artifact.get("items")
    if not isinstance(items, dict) or set(items) != set(item_order):
        errors.append("items must contain exactly item_order ids")
        items = {}
    valid_ids = basis_ids(plan)
    totals = {strategy: [0.0] * len(states) for strategy in order}
    for item_id in item_order:
        item = items.get(item_id)
        label = f"items.{item_id}"
        if not exact_fields(item, {
            "item_id", "strategy_id", "state_id", "category", "description",
            "scope_basis_ids", "annual_quantity", "unit_price", "adjustments",
            "normalized_unit_price", "normalized_annual_cost",
        }) or item.get("item_id") != item_id:
            errors.append(f"{label} must contain the exact fields and a matching item_id")
            continue
        strategy = item.get("strategy_id")
        state = item.get("state_id")
        if strategy not in order or state not in states or not isinstance(item.get("category"), str) or SAFE_ID.fullmatch(item["category"]) is None or not nonempty(item.get("description")):
            errors.append(f"{label} strategy_id or state_id is not admitted")
            continue
        for field in ("scope_basis_ids",):
            ids = strings(item.get(field))
            if not ids or len(ids) != len(set(ids)) or any(value not in valid_ids for value in ids):
                errors.append(f"{label}.{field} must link analysis evidence or proposed assumptions")
        quantity = item.get("annual_quantity")
        price = item.get("unit_price")
        if not exact_fields(quantity, {"value", "unit", "basis_ids"}) or not number(quantity.get("value"), positive=True) or not nonempty(quantity.get("unit")):
            errors.append(f"{label}.annual_quantity is invalid")
            continue
        if not exact_fields(price, {"amount", "per_unit", "currency", "price_year", "jurisdiction", "price_basis", "tax_status", "basis_ids"}) or not number(price.get("amount"), nonnegative=True) or price.get("per_unit") != quantity.get("unit") or not currency(price.get("currency")) or not year(price.get("price_year")) or not nonempty(price.get("jurisdiction")):
            errors.append(f"{label}.unit_price is invalid or its unit does not match quantity")
            continue
        for field, owner in (("basis_ids", quantity), ("basis_ids", price)):
            ids = strings(owner.get(field))
            if not ids or len(ids) != len(set(ids)) or any(value not in valid_ids for value in ids):
                errors.append(f"{label} quantity/price basis_ids are invalid")
        if price.get("price_basis") not in PRICE_BASES or price.get("tax_status") not in {"included", "excluded", "not_applicable"}:
            errors.append(f"{label}.unit_price price_basis or tax_status is unsupported")
        source_currency = price.get("currency")
        source_year = price.get("price_year")
        adjustments = item.get("adjustments")
        if not isinstance(adjustments, list) or len(adjustments) > 3:
            errors.append(f"{label}.adjustments is invalid")
            continue
        seen: set[str] = set()
        factor = 1.0
        for adjustment in adjustments:
            if not exact_fields(adjustment, {"kind", "factor", "method", "basis_ids"}) or adjustment.get("kind") not in ADJUSTMENTS or adjustment.get("kind") in seen or not number(adjustment.get("factor"), positive=True) or not nonempty(adjustment.get("method")):
                errors.append(f"{label} has an invalid or duplicated adjustment")
                continue
            seen.add(adjustment["kind"])
            factor *= float(adjustment["factor"])
            ids = strings(adjustment.get("basis_ids"))
            if not ids or len(ids) != len(set(ids)) or any(value not in valid_ids for value in ids):
                errors.append(f"{label} adjustment basis_ids are invalid")
        if (source_year != economic.get("price_year")) != ("inflation" in seen):
            errors.append(f"{label} must use inflation exactly when price years differ")
        if (source_currency != economic.get("currency")) != ("currency_conversion" in seen):
            errors.append(f"{label} must use currency_conversion exactly when currencies differ")
        unit = item.get("normalized_unit_price")
        annual = item.get("normalized_annual_cost")
        if not number(unit, nonnegative=True) or not isclose(float(unit), float(price["amount"]) * factor, rel_tol=1e-9, abs_tol=1e-6):
            errors.append(f"{label}.normalized_unit_price does not reproduce")
            continue
        if not number(annual, nonnegative=True) or not isclose(float(annual), float(quantity["value"]) * float(unit), rel_tol=1e-9, abs_tol=1e-6):
            errors.append(f"{label}.normalized_annual_cost does not reproduce")
            continue
        totals[strategy][states.index(state)] += float(annual)
    declared = artifact.get("annual_state_costs")
    if not isinstance(declared, dict) or set(declared) != set(order):
        errors.append("annual_state_costs must contain exactly strategy_order ids")
    else:
        for strategy in order:
            values = declared.get(strategy)
            model = strategies.get(strategy, {}).get("state_costs") if isinstance(strategies, dict) else None
            if not isinstance(values, list) or not isinstance(model, list) or len(values) != len(states) or len(model) != len(states):
                errors.append(f"annual_state_costs.{strategy} must match state order")
                continue
            for index, expected in enumerate(totals[strategy]):
                if not number(values[index], nonnegative=True) or not number(model[index], nonnegative=True) or not isclose(expected, float(values[index]), rel_tol=1e-9, abs_tol=1e-6) or not isclose(float(values[index]), float(model[index]), rel_tol=1e-9, abs_tol=1e-6):
                    errors.append(f"annual_state_costs.{strategy}[{index}] does not reproduce item totals and analysis state_costs")
    if not strings(artifact.get("limitations")):
        errors.append("limitations must contain at least one boundary")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis_plan", type=Path)
    parser.add_argument("cost_input_normalization", type=Path)
    args = parser.parse_args()
    try:
        raw = args.analysis_plan.read_bytes()
        plan = json.loads(raw)
        artifact = json.loads(args.cost_input_normalization.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        print(f"INVALID: {error}")
        return 1
    errors = validate(plan, raw, artifact)
    if errors:
        for error in errors:
            print(f"INVALID: {error}")
        return 1
    print("VALID: cost-input normalization 0.1.0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
