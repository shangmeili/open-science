#!/usr/bin/env python3
"""Recompute the bounded AI4HEOR background-plus-excess mortality schedule."""

from __future__ import annotations

import argparse
import json
from math import expm1, floor, isclose, isfinite, log1p
from pathlib import Path
from typing import Any


def finite_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and isfinite(value)


def equivalent(left: Any, right: Any) -> bool:
    if finite_number(left) or finite_number(right):
        return finite_number(left) and finite_number(right) and isclose(
            float(left), float(right), rel_tol=1e-12, abs_tol=1e-12
        )
    if isinstance(left, list) or isinstance(right, list):
        return isinstance(left, list) and isinstance(right, list) and len(left) == len(right) and all(
            equivalent(a, b) for a, b in zip(left, right)
        )
    if isinstance(left, dict) or isinstance(right, dict):
        return isinstance(left, dict) and isinstance(right, dict) and left.keys() == right.keys() and all(
            equivalent(left[key], right[key]) for key in left
        )
    return left == right


def basis_valid(value: Any, *, with_value: bool) -> bool:
    if not isinstance(value, dict):
        return False
    allowed = {"source_extraction_id", "source_pointer", "assumption_id"}
    if with_value:
        allowed.add("value")
    if set(value) - allowed or (with_value and "value" not in value):
        return False
    source = isinstance(value.get("source_extraction_id"), str) and bool(
        value["source_extraction_id"].strip()
    )
    assumption = isinstance(value.get("assumption_id"), str) and bool(
        value["assumption_id"].strip()
    )
    if source == assumption:
        return False
    pointer = value.get("source_pointer")
    return pointer is None or (
        source and isinstance(pointer, str) and (not pointer or pointer.startswith("/"))
    )


def derive(value: Any, cycles: int, cycle_length_years: float) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        raise ValueError("transformation must be an object")
    fields = {
        "operation", "cycle_length_years", "from_state_index", "death_state_index",
        "life_table", "excess_mortality_rate_per_year", "review_bases",
    }
    if set(value) != fields:
        raise ValueError("transformation fields are not the exact supported contract")
    if value["operation"] != "background_plus_excess_mortality_to_transition_schedule":
        raise ValueError("unsupported operation")
    if isinstance(cycles, bool) or not isinstance(cycles, int) or not 1 <= cycles <= 10_000:
        raise ValueError("cycles must be from 1 to 10000")
    declared_cycle = value["cycle_length_years"]
    if (
        not finite_number(declared_cycle)
        or declared_cycle <= 0
        or not finite_number(cycle_length_years)
        or not isclose(float(declared_cycle), float(cycle_length_years), rel_tol=0.0, abs_tol=1e-12)
    ):
        raise ValueError("cycle length must be positive and equal the analysis cycle length")
    from_index = value["from_state_index"]
    death_index = value["death_state_index"]
    if (
        isinstance(from_index, bool) or isinstance(death_index, bool)
        or not isinstance(from_index, int) or not isinstance(death_index, int)
        or {from_index, death_index} != {0, 1}
    ):
        raise ValueError("state indices must be the two distinct indices 0 and 1")

    life_table = value["life_table"]
    life_fields = {
        "jurisdiction", "table_year", "population", "sex", "start_age_years",
        "cycle_probabilities",
    }
    if not isinstance(life_table, dict) or set(life_table) != life_fields:
        raise ValueError("life_table fields are not the exact supported contract")
    if any(
        not isinstance(life_table[field], str) or not life_table[field].strip()
        for field in ("jurisdiction", "population", "sex")
    ):
        raise ValueError("life-table jurisdiction, population, and sex are required")
    table_year = life_table["table_year"]
    if isinstance(table_year, bool) or not isinstance(table_year, int) or not 1900 <= table_year <= 2100:
        raise ValueError("life-table year must be from 1900 to 2100")
    start_age = life_table["start_age_years"]
    if not finite_number(start_age) or start_age < 0:
        raise ValueError("life-table start age must be finite and non-negative")
    entries = life_table["cycle_probabilities"]
    if not isinstance(entries, list) or len(entries) != cycles:
        raise ValueError("life-table cycle probabilities must cover every model cycle")

    excess = value["excess_mortality_rate_per_year"]
    if not basis_valid(excess, with_value=True):
        raise ValueError("excess mortality rate must declare exactly one evidence or assumption basis")
    rate = excess["value"]
    if not finite_number(rate) or rate < 0:
        raise ValueError("excess mortality rate must be finite and non-negative")

    review_bases = value["review_bases"]
    required_reviews = {"population_exchangeability", "no_double_counting"}
    if not isinstance(review_bases, dict) or set(review_bases) != required_reviews:
        raise ValueError("review_bases must contain only the two required review questions")
    if any(not basis_valid(review_bases[name], with_value=False) for name in required_reviews):
        raise ValueError("each review basis needs exactly one evidence or assumption basis")

    output: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        label = f"life-table cycle probability {index}"
        if not isinstance(entry, dict) or set(entry) != {
            "cycle", "attained_age_years", "annual_probability"
        }:
            raise ValueError(f"{label} fields are invalid")
        if (
            isinstance(entry["cycle"], bool)
            or not isinstance(entry["cycle"], int)
            or entry["cycle"] != index + 1
        ):
            raise ValueError("life-table cycles must be one-based and contiguous")
        expected_age = floor(float(start_age) + index * float(declared_cycle))
        attained_age = entry["attained_age_years"]
        if (
            isinstance(attained_age, bool)
            or not finite_number(attained_age)
            or not float(attained_age).is_integer()
            or int(attained_age) != expected_age
        ):
            raise ValueError("life-table attained ages must align with elapsed model time")
        parameter = entry["annual_probability"]
        if not basis_valid(parameter, with_value=True):
            raise ValueError(f"{label} needs a value and exactly one basis")
        probability = parameter["value"]
        if not finite_number(probability) or not 0 <= probability < 1:
            raise ValueError("annual life-table probability must be from 0 inclusive to 1 exclusive")
        integrated_hazard = (-log1p(-float(probability)) + float(rate)) * float(declared_cycle)
        if not isfinite(integrated_hazard):
            raise ValueError("mortality conversion produced a non-finite hazard")
        death_probability = -expm1(-integrated_hazard)
        if not isfinite(death_probability) or not 0 <= death_probability < 1:
            raise ValueError("combined mortality produced an invalid probability")
        matrix = [[0.0, 0.0], [0.0, 0.0]]
        matrix[from_index][from_index] = 1.0 - death_probability
        matrix[from_index][death_index] = death_probability
        matrix[death_index][death_index] = 1.0
        output.append({"start_cycle": index + 1, "matrix": matrix})
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("transformation", type=Path)
    parser.add_argument("--cycles", type=int, required=True)
    parser.add_argument("--cycle-length-years", type=float, required=True)
    parser.add_argument("--expected-schedule", type=Path)
    args = parser.parse_args()
    transformation = json.loads(args.transformation.read_text())
    schedule = derive(transformation, args.cycles, args.cycle_length_years)
    if args.expected_schedule is not None:
        expected = json.loads(args.expected_schedule.read_text())
        if not equivalent(schedule, expected):
            raise SystemExit("expected schedule does not match deterministic recomputation")
    print(json.dumps(schedule, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
