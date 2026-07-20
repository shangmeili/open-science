#!/usr/bin/env python3
"""Validate and recompute an AI4HEOR hazard-ratio transformation."""

from __future__ import annotations

import argparse
import json
from math import expm1, isfinite
from pathlib import Path
from typing import Any


def fail(message: str) -> None:
    raise ValueError(message)


def basis(value: Any, label: str, *, with_value: bool = False) -> float | None:
    if not isinstance(value, dict):
        fail(f"{label} must be an object")
    allowed = {"source_extraction_id", "source_pointer", "assumption_id"}
    if with_value:
        allowed.add("value")
    if set(value) - allowed:
        fail(f"{label} contains unsupported fields")
    source = isinstance(value.get("source_extraction_id"), str) and bool(
        value["source_extraction_id"].strip()
    )
    assumption = isinstance(value.get("assumption_id"), str) and bool(
        value["assumption_id"].strip()
    )
    if source == assumption:
        fail(f"{label} must declare exactly one source_extraction_id or assumption_id")
    if source and "source_pointer" in value and (
        not isinstance(value["source_pointer"], str)
        or (value["source_pointer"] and not value["source_pointer"].startswith("/"))
    ):
        fail(f"{label}.source_pointer must be empty or a JSON pointer")
    if assumption and "source_pointer" in value:
        fail(f"{label}.source_pointer requires source_extraction_id")
    if not with_value:
        return None
    number = value.get("value")
    if (
        isinstance(number, bool)
        or not isinstance(number, (int, float))
        or not isfinite(float(number))
    ):
        fail(f"{label}.value must be finite")
    return float(number)


def derive(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        fail("transformation must be an object")
    fields = {
        "operation",
        "cycle_length_years",
        "from_state_index",
        "event_state_index",
        "baseline_cumulative_hazards",
        "hazard_ratio",
        "review_bases",
    }
    if set(value) != fields:
        fail("transformation fields are not the exact supported contract")
    if value["operation"] != "hazard_ratio_to_transition_schedule":
        fail("operation must be hazard_ratio_to_transition_schedule")
    cycle_length = value["cycle_length_years"]
    if (
        isinstance(cycle_length, bool)
        or not isinstance(cycle_length, (int, float))
        or not isfinite(float(cycle_length))
        or cycle_length <= 0
    ):
        fail("cycle_length_years must be finite and positive")
    origin, event = value["from_state_index"], value["event_state_index"]
    if {origin, event} != {0, 1}:
        fail("state indices must be the two distinct indices")
    hr = basis(value["hazard_ratio"], "hazard_ratio", with_value=True)
    if hr is None or hr <= 0:
        fail("hazard_ratio.value must be positive")
    review = value["review_bases"]
    review_names = {
        "endpoint_alignment",
        "population_transportability",
        "proportional_hazards_assumption",
        "effect_constancy_over_horizon",
        "treatment_switching_assessment",
    }
    if not isinstance(review, dict) or set(review) != review_names:
        fail("review_bases fields are not the exact supported contract")
    for name in review_names:
        basis(review[name], f"review_bases.{name}")
    hazards = value["baseline_cumulative_hazards"]
    if not isinstance(hazards, list) or not 1 <= len(hazards) <= 10_000:
        fail("baseline_cumulative_hazards must contain 1-10000 cycles")
    output = []
    previous = 0.0
    positive = False
    for index, entry in enumerate(hazards):
        label = f"baseline_cumulative_hazards[{index}]"
        if (
            not isinstance(entry, dict)
            or set(entry) != {"cycle", "cumulative_hazard"}
            or entry["cycle"] != index + 1
        ):
            fail(f"{label} must contain its one-based cycle and cumulative_hazard")
        cumulative = basis(
            entry["cumulative_hazard"],
            f"{label}.cumulative_hazard",
            with_value=True,
        )
        if cumulative is None or cumulative < 0 or cumulative + 1e-12 < previous:
            fail(
                "baseline cumulative hazards must be finite, non-negative, and non-decreasing"
            )
        increment = max(0.0, cumulative - previous)
        positive = positive or increment > 1e-12
        probability = -expm1(-hr * increment)
        if not isfinite(probability) or not 0 <= probability < 1:
            fail(f"{label} produced an invalid probability")
        matrix = [[0.0, 0.0], [0.0, 0.0]]
        matrix[origin][origin] = 1.0 - probability
        matrix[origin][event] = probability
        matrix[event][event] = 1.0
        output.append({"start_cycle": index + 1, "matrix": matrix})
        previous = cumulative
    if not positive:
        fail("baseline cumulative hazards require at least one positive increment")
    return output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("transformation", type=Path)
    parser.add_argument("--expected", type=Path)
    args = parser.parse_args()
    output = derive(json.loads(args.transformation.read_text(encoding="utf-8")))
    if args.expected is not None and output != json.loads(
        args.expected.read_text(encoding="utf-8")
    ):
        fail("derived schedule does not match --expected")
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
