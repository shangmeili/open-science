#!/usr/bin/env python3
"""Validate AI4HEOR structure-neutral economic inputs without dependencies."""

from __future__ import annotations

import argparse
import json
from math import isfinite
from pathlib import Path
import re
from typing import Any


SAFE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
STATE_ORDER = ["progression_free", "progressed", "dead"]


def number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and isfinite(float(value))


def validate(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["analysis plan must be an object"]
    schema = plan.get("schema_version")
    if schema not in {"0.12.0", "0.13.0"}:
        errors.append("schema_version must be 0.12.0 or 0.13.0")
    if "approvals" in plan:
        errors.append("approvals are app-owned and forbidden in the analysis plan")
    if plan.get("partitioned_survival_analysis") != {"path": "heor/partitioned-survival-plan.json"}:
        errors.append("partitioned_survival_analysis must link only heor/partitioned-survival-plan.json")
    if schema == "0.13.0":
        if plan.get("cost_input_normalization") != {"path": "heor/cost-input-normalization.json"}:
            errors.append("analysis schema 0.13.0 must link only heor/cost-input-normalization.json")
    elif plan.get("cost_input_normalization") is not None:
        errors.append("cost_input_normalization is admitted only by analysis schema 0.13.0")
    if not isinstance(plan.get("analysis_id"), str) or not plan["analysis_id"].strip():
        errors.append("analysis_id must not be empty")
    basis = plan.get("economic_basis")
    if not isinstance(basis, dict) or set(basis) != {"currency", "price_year"}:
        errors.append("economic_basis fields must be exactly currency and price_year")
    else:
        if not isinstance(basis["currency"], str) or re.fullmatch(r"[A-Z]{3}", basis["currency"]) is None:
            errors.append("economic_basis.currency must be a three-letter uppercase code")
        if isinstance(basis["price_year"], bool) or not isinstance(basis["price_year"], int) or not 1900 <= basis["price_year"] <= 2100:
            errors.append("economic_basis.price_year must be an integer from 1900 to 2100")
    if plan.get("states") != STATE_ORDER:
        errors.append("states must be progression_free, progressed, dead in order")
    cycles = plan.get("cycles")
    if isinstance(cycles, bool) or not isinstance(cycles, int) or not 1 <= cycles <= 10_000:
        errors.append("cycles must be an integer from 1 to 10000")
    length = plan.get("cycle_length_years")
    if not number(length) or float(length) <= 0:
        errors.append("cycle_length_years must be positive and finite")
    discounts = plan.get("discount_rates")
    if not isinstance(discounts, dict) or set(discounts) != {"costs", "outcomes"}:
        errors.append("discount_rates fields must be exactly costs and outcomes")
    elif any(not number(discounts[key]) or float(discounts[key]) < 0 for key in ("costs", "outcomes")):
        errors.append("discount rates must be finite and non-negative")
    if not isinstance(plan.get("half_cycle_correction"), bool):
        errors.append("half_cycle_correction must be a boolean")
    threshold = plan.get("willingness_to_pay")
    if threshold is not None and (not number(threshold) or float(threshold) < 0):
        errors.append("willingness_to_pay must be finite and non-negative when present")
    order = plan.get("strategy_order")
    if not isinstance(order, list) or not 2 <= len(order) <= 16 or any(not isinstance(item, str) or SAFE_ID.fullmatch(item) is None for item in order) or len(set(order)) != len(order):
        errors.append("strategy_order must contain 2-16 unique safe strategy ids")
        order = []
    if order and plan.get("baseline_strategy_id") != order[0]:
        errors.append("baseline_strategy_id must be first in strategy_order")
    strategies = plan.get("strategies")
    if not isinstance(strategies, dict) or set(strategies) != set(order):
        errors.append("strategies must contain exactly the strategy_order ids")
        strategies = {}
    names: list[str] = []
    for strategy_id in order:
        strategy = strategies.get(strategy_id)
        path = f"strategies.{strategy_id}"
        if not isinstance(strategy, dict):
            errors.append(f"{path} must be an object")
            continue
        if set(strategy) != {"name", "state_costs", "state_utilities"}:
            errors.append(f"{path} must contain only name, state_costs, and state_utilities; transition structure is forbidden")
            continue
        if not isinstance(strategy["name"], str) or not strategy["name"].strip():
            errors.append(f"{path}.name must not be empty")
        else:
            names.append(strategy["name"])
        costs = strategy["state_costs"]
        utilities = strategy["state_utilities"]
        if not isinstance(costs, list) or len(costs) != 3 or any(not number(value) or float(value) < 0 for value in costs):
            errors.append(f"{path}.state_costs must contain three finite non-negative values")
        if not isinstance(utilities, list) or len(utilities) != 3 or any(not number(value) or not -1 <= float(value) <= 1 for value in utilities):
            errors.append(f"{path}.state_utilities must contain three finite values from -1 to 1")
    if len(names) != len(set(names)):
        errors.append("strategy names must be unique")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis_plan", type=Path)
    args = parser.parse_args()
    try:
        plan = json.loads(args.analysis_plan.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        print(f"INVALID: {error}")
        return 1
    errors = validate(plan)
    if errors:
        for error in errors:
            print(f"INVALID: {error}")
        return 1
    print(f"VALID: structure-neutral economic inputs {plan.get('schema_version')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
