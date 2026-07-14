#!/usr/bin/env python3
"""Recompute a bounded AI4HEOR survival-derived transition schedule."""

from __future__ import annotations

import argparse
import json
from math import expm1, isclose, isfinite
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


def derive(value: Any, cycles: int, cycle_length_years: float) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        raise ValueError("transformation must be an object")
    fields = {
        "operation", "cycle_length_years", "from_state_index", "event_state_index",
        "distribution", "parameters",
    }
    if set(value) != fields:
        raise ValueError("transformation fields are not the exact supported contract")
    if value["operation"] != "parametric_survival_to_transition_schedule":
        raise ValueError("unsupported operation")
    if not 1 <= cycles <= 10_000:
        raise ValueError("cycles must be from 1 to 10000")
    declared_cycle = value["cycle_length_years"]
    if not finite_number(declared_cycle) or declared_cycle <= 0 or not isclose(
        float(declared_cycle), cycle_length_years, rel_tol=0.0, abs_tol=1e-12
    ):
        raise ValueError("declared cycle length must equal the positive requested cycle length")
    from_index = value["from_state_index"]
    event_index = value["event_state_index"]
    if (
        isinstance(from_index, bool) or isinstance(event_index, bool)
        or not isinstance(from_index, int) or not isinstance(event_index, int)
        or {from_index, event_index} != {0, 1}
    ):
        raise ValueError("state indices must be the two distinct indices 0 and 1")
    distribution = value["distribution"]
    expected = {"exponential": {"rate_per_year"}, "weibull": {"shape", "scale_years"}}.get(distribution)
    parameters = value["parameters"]
    if expected is None or not isinstance(parameters, dict) or set(parameters) != expected:
        raise ValueError("parameters do not match exponential or Weibull scale/shape")
    parsed: dict[str, float] = {}
    for name in expected:
        parameter = parameters[name]
        if not isinstance(parameter, dict) or set(parameter) - {
            "value", "source_extraction_id", "source_pointer", "assumption_id"
        }:
            raise ValueError(f"parameter {name} has unsupported fields")
        number = parameter.get("value")
        if not finite_number(number) or number <= 0:
            raise ValueError(f"parameter {name} must be positive")
        source = isinstance(parameter.get("source_extraction_id"), str) and bool(
            parameter["source_extraction_id"].strip()
        )
        assumption = isinstance(parameter.get("assumption_id"), str) and bool(
            parameter["assumption_id"].strip()
        )
        if source == assumption:
            raise ValueError(f"parameter {name} must declare exactly one extraction or assumption basis")
        pointer = parameter.get("source_pointer")
        if pointer is not None and (
            not source or not isinstance(pointer, str) or (pointer and not pointer.startswith("/"))
        ):
            raise ValueError(f"parameter {name} has an invalid source_pointer")
        parsed[name] = float(number)
    output = []
    previous_hazard = 0.0
    for cycle in range(1, cycles + 1):
        time_years = cycle * cycle_length_years
        try:
            cumulative_hazard = (
                parsed["rate_per_year"] * time_years
                if distribution == "exponential"
                else (time_years / parsed["scale_years"]) ** parsed["shape"]
            )
        except OverflowError as error:
            raise ValueError("cumulative hazard is non-finite") from error
        increment = cumulative_hazard - previous_hazard
        if not isfinite(increment) or increment < -1e-12:
            raise ValueError("cumulative hazard must be finite and non-decreasing")
        probability = -expm1(-max(0.0, increment))
        matrix = [[0.0, 0.0], [0.0, 0.0]]
        matrix[from_index][from_index] = 1.0 - probability
        matrix[from_index][event_index] = probability
        matrix[event_index][event_index] = 1.0
        output.append({"start_cycle": cycle, "matrix": matrix})
        previous_hazard = cumulative_hazard
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
