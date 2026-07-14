#!/usr/bin/env python3
"""Recompute the bounded AI4HEOR RR/OR relative-effect schedule."""

from __future__ import annotations

import argparse
import json
from math import isclose, isfinite
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
        "operation", "cycle_length_years", "effect_interval_years",
        "from_state_index", "event_state_index", "measure",
        "baseline_cycle_probabilities", "relative_effect", "review_bases",
    }
    if set(value) != fields:
        raise ValueError("transformation fields are not the exact supported contract")
    if value["operation"] != "relative_effect_to_transition_schedule":
        raise ValueError("unsupported operation")
    if isinstance(cycles, bool) or not isinstance(cycles, int) or not 1 <= cycles <= 10_000:
        raise ValueError("cycles must be from 1 to 10000")
    declared_cycle = value["cycle_length_years"]
    effect_interval = value["effect_interval_years"]
    if (
        not finite_number(declared_cycle)
        or not finite_number(effect_interval)
        or not finite_number(cycle_length_years)
        or declared_cycle <= 0
        or effect_interval <= 0
        or not isclose(float(declared_cycle), float(cycle_length_years), rel_tol=0.0, abs_tol=1e-12)
        or not isclose(float(effect_interval), float(declared_cycle), rel_tol=0.0, abs_tol=1e-12)
    ):
        raise ValueError("cycle and effect intervals must be positive and equal the analysis cycle length")
    from_index = value["from_state_index"]
    event_index = value["event_state_index"]
    if (
        isinstance(from_index, bool) or isinstance(event_index, bool)
        or not isinstance(from_index, int) or not isinstance(event_index, int)
        or {from_index, event_index} != {0, 1}
    ):
        raise ValueError("state indices must be the two distinct indices 0 and 1")
    measure = value["measure"]
    if measure not in {"risk_ratio", "odds_ratio"}:
        raise ValueError("measure must be risk_ratio or odds_ratio")
    effect = value["relative_effect"]
    if not basis_valid(effect, with_value=True):
        raise ValueError("relative_effect must declare one value and exactly one basis")
    effect_value = effect["value"]
    if not finite_number(effect_value) or effect_value <= 0:
        raise ValueError("relative_effect.value must be finite and positive")
    review_bases = value["review_bases"]
    required_reviews = {
        "endpoint_alignment", "population_transportability", "effect_constancy_over_cycles"
    }
    if not isinstance(review_bases, dict) or set(review_bases) != required_reviews:
        raise ValueError("review_bases must contain exactly the three required review questions")
    if any(not basis_valid(review_bases[name], with_value=False) for name in required_reviews):
        raise ValueError("each review basis needs exactly one evidence or assumption basis")
    entries = value["baseline_cycle_probabilities"]
    if not isinstance(entries, list) or len(entries) != cycles:
        raise ValueError("baseline_cycle_probabilities must cover every model cycle")

    output: list[dict[str, Any]] = []
    positive_baselines: list[float] = []
    for index, entry in enumerate(entries):
        label = f"baseline cycle probability {index}"
        if not isinstance(entry, dict) or set(entry) != {"cycle", "probability"}:
            raise ValueError(f"{label} fields are invalid")
        cycle = entry["cycle"]
        if isinstance(cycle, bool) or not isinstance(cycle, int) or cycle != index + 1:
            raise ValueError("baseline cycles must be one-based and contiguous")
        probability = entry["probability"]
        if not basis_valid(probability, with_value=True):
            raise ValueError(f"{label} must declare one value and exactly one basis")
        baseline = probability["value"]
        if not finite_number(baseline) or not 0 <= baseline < 1:
            raise ValueError("baseline probability must be from 0 inclusive to 1 exclusive")
        baseline = float(baseline)
        if baseline > 0:
            positive_baselines.append(baseline)
        if measure == "risk_ratio":
            treated = baseline * float(effect_value)
        else:
            numerator = float(effect_value) * baseline
            denominator = 1.0 - baseline + numerator
            if not isfinite(numerator) or not isfinite(denominator) or denominator <= 0:
                raise ValueError("odds-ratio conversion produced non-finite arithmetic")
            treated = numerator / denominator
        if not isfinite(treated) or not 0 <= treated < 1:
            raise ValueError("relative-effect conversion produced an invalid probability")
        matrix = [[0.0, 0.0], [0.0, 0.0]]
        matrix[from_index][from_index] = 1.0 - treated
        matrix[from_index][event_index] = treated
        matrix[event_index][event_index] = 1.0
        output.append({"start_cycle": index + 1, "matrix": matrix})
    if not positive_baselines:
        raise ValueError("at least one baseline probability must be positive")
    if measure == "risk_ratio" and not float(effect_value) < 1.0 / max(positive_baselines):
        raise ValueError("risk ratio must be strictly below 1 / max positive baseline probability")
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
