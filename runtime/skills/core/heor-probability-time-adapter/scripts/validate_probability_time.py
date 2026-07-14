#!/usr/bin/env python3
"""Recompute a bounded AI4HEOR probability-time transition input."""

from __future__ import annotations

import argparse
import json
from math import expm1, isclose, isfinite, log1p
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


def derive(value: Any, state_count: int, cycles: int, cycle_length_years: float, schedule: bool) -> Any:
    if not isinstance(value, dict) or set(value) != {"operation", "cycle_length_years", "phases"}:
        raise ValueError("transformation fields are not the exact supported contract")
    if value["operation"] != "single_event_probability_time_conversion":
        raise ValueError("unsupported operation")
    declared_cycle = value["cycle_length_years"]
    if not finite_number(declared_cycle) or declared_cycle <= 0 or not isclose(
        float(declared_cycle), cycle_length_years, rel_tol=0.0, abs_tol=1e-12
    ):
        raise ValueError("declared cycle length must equal the positive model cycle length")
    phases = value["phases"]
    if not isinstance(phases, list) or not 1 <= len(phases) <= cycles:
        raise ValueError("phase count is invalid")
    starts: list[int] = []
    matrices: list[list[list[float]]] = []
    for phase_index, phase in enumerate(phases):
        if not isinstance(phase, dict) or set(phase) != {"start_cycle", "rows"}:
            raise ValueError(f"phase {phase_index} fields are invalid")
        start = phase["start_cycle"]
        if isinstance(start, bool) or not isinstance(start, int) or not 1 <= start <= cycles:
            raise ValueError(f"phase {phase_index} start_cycle is invalid")
        starts.append(start)
        rows = phase["rows"]
        if not isinstance(rows, list) or len(rows) != state_count:
            raise ValueError(f"phase {phase_index} rows must match state_count")
        matrix: list[list[float]] = []
        for row_index, row in enumerate(rows):
            if not isinstance(row, dict) or set(row) != {"self_index", "event"} or row["self_index"] != row_index:
                raise ValueError(f"phase {phase_index} row {row_index} is invalid")
            output = [0.0] * state_count
            output[row_index] = 1.0
            event = row["event"]
            if event is not None:
                allowed = {
                    "target_index", "source_probability", "source_interval_years",
                    "source_extraction_id", "source_pointer", "assumption_id",
                }
                if not isinstance(event, dict) or set(event) - allowed:
                    raise ValueError(f"phase {phase_index} row {row_index} event is invalid")
                target = event.get("target_index")
                probability = event.get("source_probability")
                interval = event.get("source_interval_years")
                if isinstance(target, bool) or not isinstance(target, int) or not 0 <= target < state_count or target == row_index:
                    raise ValueError("event target_index is invalid")
                if not finite_number(probability) or not 0 < probability < 1:
                    raise ValueError("source_probability must be strictly between 0 and 1")
                if not finite_number(interval) or interval <= 0:
                    raise ValueError("source_interval_years must be positive")
                source = isinstance(event.get("source_extraction_id"), str) and bool(event["source_extraction_id"].strip())
                assumption = isinstance(event.get("assumption_id"), str) and bool(event["assumption_id"].strip())
                if source == assumption:
                    raise ValueError("event must declare exactly one extraction or assumption basis")
                pointer = event.get("source_pointer")
                if pointer is not None and (not source or not isinstance(pointer, str) or (pointer and not pointer.startswith("/"))):
                    raise ValueError("event source_pointer is invalid")
                converted = -expm1(log1p(-float(probability)) * cycle_length_years / float(interval))
                if not isfinite(converted) or not 0 < converted < 1:
                    raise ValueError("conversion produced an invalid probability")
                output[row_index] = 1.0 - converted
                output[target] = converted
            matrix.append(output)
        matrices.append(matrix)
    if starts[0] != 1 or any(a >= b for a, b in zip(starts, starts[1:])):
        raise ValueError("phase starts must begin at 1 and strictly increase")
    if schedule:
        return [{"start_cycle": start, "matrix": matrix} for start, matrix in zip(starts, matrices)]
    if len(matrices) != 1:
        raise ValueError("a static matrix requires exactly one phase")
    return matrices[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("transformation", type=Path)
    parser.add_argument("--states", type=int, required=True)
    parser.add_argument("--cycles", type=int, required=True)
    parser.add_argument("--cycle-length-years", type=float, required=True)
    parser.add_argument("--schedule", action="store_true")
    parser.add_argument("--expected", type=Path)
    args = parser.parse_args()
    output = derive(
        json.loads(args.transformation.read_text()),
        args.states,
        args.cycles,
        args.cycle_length_years,
        args.schedule,
    )
    if args.expected is not None and not equivalent(output, json.loads(args.expected.read_text())):
        raise SystemExit("expected transition input does not match deterministic recomputation")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
