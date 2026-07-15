#!/usr/bin/env python3
"""Audit portable evidence-to-input links; app-owned verification remains external."""

from __future__ import annotations

import json
import re
import sys
from hashlib import sha256
from math import expm1, floor, isclose, isfinite, log1p
from pathlib import Path
from typing import Any


BASE_PATHS = [
    "cycles", "cycle_length_years", "discount_rates.costs", "discount_rates.outcomes",
    "half_cycle_correction",
]
UNCERTAINTY = {"fixed", "range_available", "distribution_available"}
APPROVABLE_ANALYSIS_SCHEMAS = {
    "0.3.0", "0.4.0", "0.5.0", "0.6.0", "0.7.0", "0.8.0", "0.9.0", "0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0"
}
STRATEGY_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


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


def required_paths(plan: dict[str, Any]) -> list[str]:
    paths = list(BASE_PATHS)
    structure_neutral = plan.get("schema_version") in {"0.12.0", "0.13.0", "0.14.0", "0.15.0"}
    for role in strategy_ids(plan):
        strategy = (plan.get("strategies") or {}).get(role) or {}
        transition_field = (
            "transition_schedule"
            if isinstance(strategy, dict) and "transition_schedule" in strategy
            else "transition_matrix"
        )
        if not structure_neutral:
            paths.extend([
                f"strategies.{role}.initial_distribution",
                f"strategies.{role}.{transition_field}",
            ])
        paths.extend([
            f"strategies.{role}.state_costs",
            f"strategies.{role}.state_utilities",
        ])
    return paths


def strategy_ids(plan: dict[str, Any]) -> list[str]:
    if plan.get("schema_version") in {"0.8.0", "0.9.0", "0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0"}:
        order = plan.get("strategy_order")
        return order if isinstance(order, list) and all(isinstance(item, str) for item in order) else []
    return ["comparator", "intervention"]


def transition_path(path: str) -> bool:
    parts = path.split(".")
    return (
        len(parts) == 3 and parts[0] == "strategies"
        and STRATEGY_ID.fullmatch(parts[1]) is not None
        and parts[2] in {"transition_matrix", "transition_schedule"}
    )


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


def json_pointer(value: Any, pointer: str) -> Any:
    if pointer == "":
        return value
    if not isinstance(pointer, str) or not pointer.startswith("/"):
        raise ValueError("source_pointer must be empty or a JSON pointer")
    current = value
    for encoded in pointer[1:].split("/"):
        token = encoded.replace("~1", "/").replace("~0", "~")
        if isinstance(current, list):
            if not token.isdigit() or int(token) >= len(current):
                raise ValueError("source_pointer does not resolve")
            current = current[int(token)]
        elif isinstance(current, dict) and token in current:
            current = current[token]
        else:
            raise ValueError("source_pointer does not resolve")
    return current


def transition_rate_reasons(
    plan: dict[str, Any],
    path: str,
    mapping: dict[str, Any],
    derivation: dict[str, Any],
    extraction_index: dict[str, dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if plan.get("schema_version") not in {"0.5.0", "0.8.0", "0.9.0", "0.10.0", "0.11.0"}:
        return ["deterministic transition-rate transformations require schema_version 0.5.0 through 0.11.0"]
    if not transition_path(path):
        return ["deterministic transformation is allowed only for transition inputs"]
    transformation = derivation.get("transformation")
    if not isinstance(transformation, dict):
        return ["derivation.transformation must be an object"]
    expected_keys = {"operation", "cycle_length_years", "phases"}
    if set(transformation) != expected_keys:
        reasons.append("transformation fields are not the exact supported contract")
    if transformation.get("operation") != "constant_competing_rates":
        reasons.append("transformation.operation must be constant_competing_rates")
    cycle_length = transformation.get("cycle_length_years")
    cycle_valid = (
        finite_number(cycle_length)
        and cycle_length > 0
        and finite_number(plan.get("cycle_length_years"))
        and isclose(
            float(cycle_length),
            float(plan["cycle_length_years"]),
            rel_tol=0.0,
            abs_tol=1e-12,
        )
    )
    if not cycle_valid:
        reasons.append("transformation cycle length must equal the analysis cycle length")
    declared_cycle = float(cycle_length) if finite_number(cycle_length) else 0.0
    states = plan.get("states")
    state_count = len(states) if isinstance(states, list) else 0
    cycles = plan.get("cycles")
    phases = transformation.get("phases")
    if (
        not isinstance(cycles, int)
        or isinstance(cycles, bool)
        or not isinstance(phases, list)
        or not 1 <= len(phases) <= cycles
    ):
        return reasons + ["transformation.phases count is invalid"]
    starts: list[int] = []
    matrices: list[list[list[float]]] = []
    used_extractions: set[str] = set()
    used_assumptions: set[str] = set()
    for phase_index, phase in enumerate(phases):
        phase_label = f"transformation.phases[{phase_index}]"
        if not isinstance(phase, dict) or set(phase) != {"start_cycle", "rows"}:
            reasons.append(f"{phase_label} fields are invalid")
            continue
        start = phase.get("start_cycle")
        if isinstance(start, bool) or not isinstance(start, int) or not 1 <= start <= cycles:
            reasons.append(f"{phase_label}.start_cycle is invalid")
            continue
        starts.append(start)
        rows = phase.get("rows")
        if not isinstance(rows, list) or len(rows) != state_count:
            reasons.append(f"{phase_label}.rows must contain {state_count} rows")
            continue
        matrix: list[list[float]] = []
        for row_index, row in enumerate(rows):
            row_label = f"{phase_label}.rows[{row_index}]"
            if not isinstance(row, dict) or set(row) != {"self_index", "events"}:
                reasons.append(f"{row_label} fields are invalid")
                continue
            if row.get("self_index") != row_index:
                reasons.append(f"{row_label}.self_index must equal the row position")
            events = row.get("events")
            if not isinstance(events, list) or len(events) > max(0, state_count - 1):
                reasons.append(f"{row_label}.events count is invalid")
                continue
            targets: set[int] = set()
            parsed: list[tuple[int, float]] = []
            total_rate = 0.0
            for event_index, event in enumerate(events):
                event_label = f"{row_label}.events[{event_index}]"
                allowed = {
                    "target_index", "rate_per_year", "source_extraction_id",
                    "source_pointer", "assumption_id",
                }
                if not isinstance(event, dict) or set(event) - allowed:
                    reasons.append(f"{event_label} contains unsupported fields")
                    continue
                target_index = event.get("target_index")
                if (
                    isinstance(target_index, bool)
                    or not isinstance(target_index, int)
                    or not 0 <= target_index < state_count
                    or target_index == row_index
                    or target_index in targets
                ):
                    reasons.append(f"{event_label}.target_index is invalid or duplicated")
                    continue
                targets.add(target_index)
                rate = event.get("rate_per_year")
                if not finite_number(rate) or rate <= 0:
                    reasons.append(f"{event_label}.rate_per_year must be positive")
                    continue
                source_id = event.get("source_extraction_id")
                assumption_id = event.get("assumption_id")
                has_source = text(source_id)
                has_assumption = text(assumption_id)
                if has_source == has_assumption:
                    reasons.append(
                        f"{event_label} must declare one extraction or assumption basis"
                    )
                elif has_source:
                    used_extractions.add(source_id)
                    extraction = extraction_index.get(source_id)
                    if extraction is not None:
                        try:
                            extracted = strict_json(extraction.get("extracted_value"))
                            extracted = json_pointer(extracted, event.get("source_pointer", ""))
                        except (TypeError, ValueError, json.JSONDecodeError) as error:
                            reasons.append(f"{event_label}: {error}")
                        else:
                            if not json_equivalent(extracted, rate):
                                reasons.append(
                                    f"{event_label}.rate_per_year does not match the bound extraction"
                                )
                else:
                    used_assumptions.add(assumption_id)
                    if "source_pointer" in event:
                        reasons.append(f"{event_label}.source_pointer requires an extraction")
                total_rate += float(rate)
                parsed.append((target_index, float(rate)))
            output_row = [0.0] * state_count
            if total_rate == 0:
                if state_count:
                    output_row[row_index] = 1.0
            else:
                event_mass = -expm1(-total_rate * declared_cycle)
                output_row[row_index] = 1.0 - event_mass
                for target_index, rate in parsed:
                    output_row[target_index] = event_mass * rate / total_rate
            matrix.append(output_row)
        if len(matrix) == state_count:
            matrices.append(matrix)
    if not starts or starts[0] != 1 or any(a >= b for a, b in zip(starts, starts[1:])):
        reasons.append("transformation phases must start at cycle 1 and strictly increase")
    output: Any = None
    if path.endswith(".transition_matrix"):
        if len(phases) != 1:
            reasons.append("a static matrix transformation requires exactly one phase")
        elif matrices:
            output = matrices[0]
    elif len(matrices) == len(starts):
        output = [
            {"start_cycle": start, "matrix": matrix}
            for start, matrix in zip(starts, matrices)
        ]
    target = model_value(plan, path)
    if output is None or not json_equivalent(output, target):
        reasons.append("constant competing rates do not reproduce the current transition input")
    selected_extractions = set(texts(mapping.get("extraction_ids")) or [])
    selected_assumptions = set(texts(mapping.get("assumption_ids")) or [])
    if used_extractions != selected_extractions:
        reasons.append("transformation must use every selected extraction")
    if used_assumptions != selected_assumptions:
        reasons.append("transformation must use every proposed assumption")
    return reasons


def survival_curve_reasons(
    plan: dict[str, Any],
    path: str,
    mapping: dict[str, Any],
    derivation: dict[str, Any],
    extraction_index: dict[str, dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if plan.get("schema_version") not in {"0.6.0", "0.8.0", "0.9.0", "0.10.0", "0.11.0"}:
        return ["parametric survival transformations require schema_version 0.6.0 through 0.11.0"]
    if not transition_path(path) or not path.endswith(".transition_schedule"):
        return ["parametric survival transformation is allowed only for a transition schedule"]
    transformation = derivation.get("transformation")
    if not isinstance(transformation, dict):
        return ["derivation.transformation must be an object"]
    expected_keys = {
        "operation", "cycle_length_years", "from_state_index", "event_state_index",
        "distribution", "parameters",
    }
    if set(transformation) != expected_keys:
        reasons.append("survival transformation fields are not the exact supported contract")
    states = plan.get("states")
    if not isinstance(states, list) or len(states) != 2:
        reasons.append("parametric survival transformation requires exactly two states")
    cycles = plan.get("cycles")
    if isinstance(cycles, bool) or not isinstance(cycles, int) or not 1 <= cycles <= 10_000:
        reasons.append("parametric survival transformation supports 1-10000 cycles")
        cycles = 0
    declared_cycle = transformation.get("cycle_length_years")
    if (
        not finite_number(declared_cycle) or declared_cycle <= 0
        or not finite_number(plan.get("cycle_length_years"))
        or not isclose(
            float(declared_cycle), float(plan["cycle_length_years"]),
            rel_tol=0.0, abs_tol=1e-12,
        )
    ):
        reasons.append("transformation.cycle_length_years must equal the analysis cycle length")
    from_index = transformation.get("from_state_index")
    event_index = transformation.get("event_state_index")
    if (
        isinstance(from_index, bool) or not isinstance(from_index, int)
        or isinstance(event_index, bool) or not isinstance(event_index, int)
        or {from_index, event_index} != {0, 1}
    ):
        reasons.append(
            "from_state_index and event_state_index must be the two distinct state indices"
        )
    distribution = transformation.get("distribution")
    expected_parameters = {
        "exponential": {"rate_per_year"},
        "weibull": {"shape", "scale_years"},
    }.get(distribution)
    raw_parameters = transformation.get("parameters")
    if expected_parameters is None:
        reasons.append("transformation.distribution must be exponential or weibull")
        expected_parameters = set()
    if not isinstance(raw_parameters, dict) or set(raw_parameters) != expected_parameters:
        reasons.append("transformation.parameters fields do not match the distribution")
        raw_parameters = {}
    parameters: dict[str, float] = {}
    used_extractions: set[str] = set()
    used_assumptions: set[str] = set()
    for name in sorted(expected_parameters):
        label = f"transformation.parameters.{name}"
        parameter = raw_parameters.get(name)
        allowed = {"value", "source_extraction_id", "source_pointer", "assumption_id"}
        if not isinstance(parameter, dict) or set(parameter) - allowed:
            reasons.append(f"{label} contains unsupported fields")
            continue
        value = parameter.get("value")
        if not finite_number(value) or value <= 0:
            reasons.append(f"{label}.value must be positive")
            continue
        parameters[name] = float(value)
        source_id = parameter.get("source_extraction_id")
        assumption_id = parameter.get("assumption_id")
        has_source = text(source_id)
        has_assumption = text(assumption_id)
        if has_source == has_assumption:
            reasons.append(f"{label} must declare exactly one extraction or assumption basis")
        elif has_source:
            used_extractions.add(source_id)
            extraction = extraction_index.get(source_id)
            if extraction is not None:
                try:
                    extracted = strict_json(extraction.get("extracted_value"))
                    extracted = json_pointer(extracted, parameter.get("source_pointer", ""))
                except (TypeError, ValueError, json.JSONDecodeError) as error:
                    reasons.append(f"{label}: {error}")
                else:
                    if not json_equivalent(extracted, value):
                        reasons.append(f"{label}.value does not match the bound extraction")
        else:
            used_assumptions.add(assumption_id)
            if "source_pointer" in parameter:
                reasons.append(f"{label}.source_pointer requires an extraction")
    output: list[dict[str, Any]] = []
    if (
        cycles > 0 and finite_number(declared_cycle) and declared_cycle > 0
        and from_index in {0, 1} and event_index in {0, 1}
        and from_index != event_index and set(parameters) == expected_parameters
    ):
        previous_hazard = 0.0
        for cycle in range(1, cycles + 1):
            time_years = cycle * float(declared_cycle)
            try:
                cumulative_hazard = (
                    parameters["rate_per_year"] * time_years
                    if distribution == "exponential"
                    else (time_years / parameters["scale_years"]) ** parameters["shape"]
                )
            except OverflowError:
                cumulative_hazard = float("inf")
            increment = cumulative_hazard - previous_hazard
            if not isfinite(increment) or increment < -1e-12:
                reasons.append("parametric survival cumulative hazard must be finite and non-decreasing")
                output = []
                break
            event_probability = -expm1(-max(0.0, increment))
            matrix = [[0.0, 0.0], [0.0, 0.0]]
            matrix[from_index][from_index] = 1.0 - event_probability
            matrix[from_index][event_index] = event_probability
            matrix[event_index][event_index] = 1.0
            output.append({"start_cycle": cycle, "matrix": matrix})
            previous_hazard = cumulative_hazard
    if not output or not json_equivalent(output, model_value(plan, path)):
        reasons.append("parametric survival curve does not reproduce the current transition schedule")
    selected_extractions = set(texts(mapping.get("extraction_ids")) or [])
    selected_assumptions = set(texts(mapping.get("assumption_ids")) or [])
    if used_extractions != selected_extractions:
        reasons.append("transformation must use every selected extraction")
    if used_assumptions != selected_assumptions:
        reasons.append("transformation must use every proposed assumption")
    return reasons


def probability_time_reasons(
    plan: dict[str, Any],
    path: str,
    mapping: dict[str, Any],
    derivation: dict[str, Any],
    extraction_index: dict[str, dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if plan.get("schema_version") not in {"0.7.0", "0.8.0", "0.9.0", "0.10.0", "0.11.0"}:
        return ["probability-time transformations require schema_version 0.7.0 through 0.11.0"]
    if not transition_path(path):
        return ["probability-time transformation is allowed only for transition inputs"]
    transformation = derivation.get("transformation")
    if not isinstance(transformation, dict):
        return ["derivation.transformation must be an object"]
    if set(transformation) != {"operation", "cycle_length_years", "phases"}:
        reasons.append("probability-time transformation fields are not the exact supported contract")
    if transformation.get("operation") != "single_event_probability_time_conversion":
        reasons.append("transformation.operation must be single_event_probability_time_conversion")
    cycle_length = transformation.get("cycle_length_years")
    if (
        not finite_number(cycle_length)
        or cycle_length <= 0
        or not finite_number(plan.get("cycle_length_years"))
        or not isclose(float(cycle_length), float(plan["cycle_length_years"]), rel_tol=0.0, abs_tol=1e-12)
    ):
        reasons.append("transformation cycle length must equal the analysis cycle length")
    declared_cycle = float(cycle_length) if finite_number(cycle_length) else 0.0
    states = plan.get("states")
    state_count = len(states) if isinstance(states, list) else 0
    cycles = plan.get("cycles")
    phases = transformation.get("phases")
    if (
        isinstance(cycles, bool)
        or not isinstance(cycles, int)
        or not isinstance(phases, list)
        or not 1 <= len(phases) <= cycles
    ):
        return reasons + ["transformation.phases count is invalid"]
    starts: list[int] = []
    matrices: list[list[list[float]]] = []
    used_extractions: set[str] = set()
    used_assumptions: set[str] = set()
    for phase_index, phase in enumerate(phases):
        phase_label = f"transformation.phases[{phase_index}]"
        if not isinstance(phase, dict) or set(phase) != {"start_cycle", "rows"}:
            reasons.append(f"{phase_label} fields are invalid")
            continue
        start = phase.get("start_cycle")
        if isinstance(start, bool) or not isinstance(start, int) or not 1 <= start <= cycles:
            reasons.append(f"{phase_label}.start_cycle is invalid")
            continue
        starts.append(start)
        rows = phase.get("rows")
        if not isinstance(rows, list) or len(rows) != state_count:
            reasons.append(f"{phase_label}.rows must contain {state_count} rows")
            continue
        matrix: list[list[float]] = []
        for row_index, row in enumerate(rows):
            row_label = f"{phase_label}.rows[{row_index}]"
            if not isinstance(row, dict) or set(row) != {"self_index", "event"}:
                reasons.append(f"{row_label} fields are invalid")
                continue
            if row.get("self_index") != row_index:
                reasons.append(f"{row_label}.self_index must equal the row position")
            output_row = [0.0] * state_count
            if state_count:
                output_row[row_index] = 1.0
            event = row.get("event")
            if event is not None:
                event_label = f"{row_label}.event"
                allowed = {
                    "target_index", "source_probability", "source_interval_years",
                    "source_extraction_id", "source_pointer", "assumption_id",
                }
                if not isinstance(event, dict) or set(event) - allowed:
                    reasons.append(f"{event_label} contains unsupported fields")
                    continue
                target_index = event.get("target_index")
                probability = event.get("source_probability")
                source_interval = event.get("source_interval_years")
                if (
                    isinstance(target_index, bool)
                    or not isinstance(target_index, int)
                    or not 0 <= target_index < state_count
                    or target_index == row_index
                ):
                    reasons.append(f"{event_label}.target_index is invalid")
                    continue
                if not finite_number(probability) or not 0 < probability < 1:
                    reasons.append(f"{event_label}.source_probability must be strictly between 0 and 1")
                    continue
                if not finite_number(source_interval) or source_interval <= 0:
                    reasons.append(f"{event_label}.source_interval_years must be positive")
                    continue
                source_id = event.get("source_extraction_id")
                assumption_id = event.get("assumption_id")
                has_source = text(source_id)
                has_assumption = text(assumption_id)
                if has_source == has_assumption:
                    reasons.append(f"{event_label} must declare one extraction or assumption basis")
                elif has_source:
                    used_extractions.add(source_id)
                    extraction = extraction_index.get(source_id)
                    if extraction is not None:
                        try:
                            extracted = strict_json(extraction.get("extracted_value"))
                            extracted = json_pointer(extracted, event.get("source_pointer", ""))
                        except (TypeError, ValueError, json.JSONDecodeError) as error:
                            reasons.append(f"{event_label}: {error}")
                        else:
                            if not json_equivalent(extracted, probability):
                                reasons.append(f"{event_label}.source_probability does not match the bound extraction")
                else:
                    used_assumptions.add(assumption_id)
                    if "source_pointer" in event:
                        reasons.append(f"{event_label}.source_pointer requires an extraction")
                converted = -expm1(log1p(-float(probability)) * declared_cycle / float(source_interval))
                if not isfinite(converted) or not 0 < converted < 1:
                    reasons.append(f"{event_label} conversion produced an invalid probability")
                    continue
                output_row[row_index] = 1.0 - converted
                output_row[target_index] = converted
            matrix.append(output_row)
        if len(matrix) == state_count:
            matrices.append(matrix)
    if not starts or starts[0] != 1 or any(a >= b for a, b in zip(starts, starts[1:])):
        reasons.append("transformation phases must start at cycle 1 and strictly increase")
    output: Any = None
    if path.endswith(".transition_matrix"):
        if len(phases) != 1:
            reasons.append("a static matrix transformation requires exactly one phase")
        elif matrices:
            output = matrices[0]
    elif len(matrices) == len(starts):
        output = [
            {"start_cycle": start, "matrix": matrix}
            for start, matrix in zip(starts, matrices)
        ]
    if output is None or not json_equivalent(output, model_value(plan, path)):
        reasons.append("source probabilities do not reproduce the current transition input")
    if used_extractions != set(texts(mapping.get("extraction_ids")) or []):
        reasons.append("transformation must use every selected extraction")
    if used_assumptions != set(texts(mapping.get("assumption_ids")) or []):
        reasons.append("transformation must use every proposed assumption")
    return reasons


def relative_effect_reasons(
    plan: dict[str, Any],
    path: str,
    mapping: dict[str, Any],
    derivation: dict[str, Any],
    extraction_index: dict[str, dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if plan.get("schema_version") not in {"0.10.0", "0.11.0"}:
        return ["relative-effect transformations require schema_version 0.10.0 or 0.11.0"]
    if not transition_path(path) or not path.endswith(".transition_schedule"):
        return ["relative-effect transformation is allowed only for a transition schedule"]
    transformation = derivation.get("transformation")
    if not isinstance(transformation, dict):
        return ["derivation.transformation must be an object"]
    expected_fields = {
        "operation", "cycle_length_years", "effect_interval_years",
        "from_state_index", "event_state_index", "measure",
        "baseline_cycle_probabilities", "relative_effect", "review_bases",
    }
    if set(transformation) != expected_fields:
        reasons.append("relative-effect fields are not the exact supported contract")
    if transformation.get("operation") != "relative_effect_to_transition_schedule":
        reasons.append("transformation.operation must be relative_effect_to_transition_schedule")
    states = plan.get("states")
    if not isinstance(states, list) or len(states) != 2:
        reasons.append("relative-effect transformation requires exactly two states")
    cycles = plan.get("cycles")
    if isinstance(cycles, bool) or not isinstance(cycles, int) or not 1 <= cycles <= 10_000:
        reasons.append("relative-effect transformation supports 1-10000 cycles")
        cycles = 0
    cycle_length = transformation.get("cycle_length_years")
    effect_interval = transformation.get("effect_interval_years")
    intervals_valid = (
        finite_number(cycle_length)
        and finite_number(effect_interval)
        and finite_number(plan.get("cycle_length_years"))
        and cycle_length > 0
        and effect_interval > 0
        and isclose(float(cycle_length), float(plan["cycle_length_years"]), rel_tol=0.0, abs_tol=1e-12)
        and isclose(float(effect_interval), float(cycle_length), rel_tol=0.0, abs_tol=1e-12)
    )
    if not intervals_valid:
        reasons.append("cycle and effect intervals must be positive and equal the analysis cycle length")
    from_index = transformation.get("from_state_index")
    event_index = transformation.get("event_state_index")
    if (
        isinstance(from_index, bool) or not isinstance(from_index, int)
        or isinstance(event_index, bool) or not isinstance(event_index, int)
        or {from_index, event_index} != {0, 1}
    ):
        reasons.append("from_state_index and event_state_index must be the two distinct state indices")
    measure = transformation.get("measure")
    if measure not in {"risk_ratio", "odds_ratio"}:
        reasons.append("relative-effect measure must be risk_ratio or odds_ratio")

    used_extractions: set[str] = set()
    used_assumptions: set[str] = set()

    def parameter_value(value: Any, label: str) -> float | None:
        allowed = {"value", "source_extraction_id", "source_pointer", "assumption_id"}
        if not isinstance(value, dict) or set(value) - allowed:
            reasons.append(f"{label} contains unsupported fields")
            return None
        number = value.get("value")
        if not finite_number(number):
            reasons.append(f"{label}.value must be finite")
            return None
        source_id = value.get("source_extraction_id")
        assumption_id = value.get("assumption_id")
        has_source = text(source_id)
        has_assumption = text(assumption_id)
        if has_source == has_assumption:
            reasons.append(f"{label} must declare exactly one extraction or assumption basis")
        elif has_source:
            used_extractions.add(source_id)
            extraction = extraction_index.get(source_id)
            if extraction is not None:
                try:
                    extracted = strict_json(extraction.get("extracted_value"))
                    extracted = json_pointer(extracted, value.get("source_pointer", ""))
                except (TypeError, ValueError, json.JSONDecodeError) as error:
                    reasons.append(f"{label}: {error}")
                else:
                    if not json_equivalent(extracted, number):
                        reasons.append(f"{label}.value does not match the bound extraction")
        else:
            used_assumptions.add(assumption_id)
            if "source_pointer" in value:
                reasons.append(f"{label}.source_pointer requires an extraction")
        return float(number)

    relative_effect = parameter_value(transformation.get("relative_effect"), "relative_effect")
    if relative_effect is None or relative_effect <= 0:
        reasons.append("relative_effect.value must be positive")
    entries = transformation.get("baseline_cycle_probabilities")
    if not isinstance(entries, list) or len(entries) != cycles:
        reasons.append("baseline_cycle_probabilities must cover every model cycle")
        entries = []
    baselines: list[float] = []
    for index, entry in enumerate(entries):
        label = f"baseline_cycle_probabilities[{index}]"
        if not isinstance(entry, dict) or set(entry) != {"cycle", "probability"}:
            reasons.append(f"{label} fields are invalid")
            continue
        cycle = entry.get("cycle")
        if isinstance(cycle, bool) or not isinstance(cycle, int) or cycle != index + 1:
            reasons.append(f"{label}.cycle must equal its one-based position")
        probability = parameter_value(entry.get("probability"), f"{label}.probability")
        if probability is None or not 0 <= probability < 1:
            reasons.append(f"{label}.probability.value must be from 0 inclusive to 1 exclusive")
        else:
            baselines.append(probability)
    positive_baselines = [value for value in baselines if value > 0]
    if not positive_baselines:
        reasons.append("at least one baseline probability must be positive")

    review_bases = transformation.get("review_bases")
    required_reviews = {
        "endpoint_alignment", "population_transportability", "effect_constancy_over_cycles"
    }
    if not isinstance(review_bases, dict) or set(review_bases) != required_reviews:
        reasons.append("review_bases must contain exactly the three required review questions")
    else:
        for name in sorted(required_reviews):
            label = f"review_bases.{name}"
            basis = review_bases[name]
            allowed = {"source_extraction_id", "source_pointer", "assumption_id"}
            if not isinstance(basis, dict) or set(basis) - allowed:
                reasons.append(f"{label} fields are invalid")
                continue
            source_id = basis.get("source_extraction_id")
            assumption_id = basis.get("assumption_id")
            has_source = text(source_id)
            has_assumption = text(assumption_id)
            if has_source == has_assumption:
                reasons.append(f"{label} must declare exactly one extraction or assumption basis")
            elif has_source:
                used_extractions.add(source_id)
                pointer = basis.get("source_pointer")
                if pointer is not None and (
                    not isinstance(pointer, str) or (pointer and not pointer.startswith("/"))
                ):
                    reasons.append(f"{label}.source_pointer is invalid")
            else:
                used_assumptions.add(assumption_id)
                if "source_pointer" in basis:
                    reasons.append(f"{label}.source_pointer requires an extraction")

    output: list[dict[str, Any]] = []
    if (
        len(baselines) == cycles
        and relative_effect is not None
        and relative_effect > 0
        and measure in {"risk_ratio", "odds_ratio"}
        and intervals_valid
        and from_index in {0, 1}
        and event_index in {0, 1}
        and from_index != event_index
    ):
        for index, baseline in enumerate(baselines):
            if measure == "risk_ratio":
                treated = baseline * relative_effect
            else:
                numerator = relative_effect * baseline
                denominator = 1.0 - baseline + numerator
                if not isfinite(numerator) or not isfinite(denominator) or denominator <= 0:
                    reasons.append(f"baseline_cycle_probabilities[{index}] produced non-finite OR arithmetic")
                    continue
                treated = numerator / denominator
            if not isfinite(treated) or not 0 <= treated < 1:
                reasons.append(f"baseline_cycle_probabilities[{index}] produced an invalid treated probability")
                continue
            matrix = [[0.0, 0.0], [0.0, 0.0]]
            matrix[from_index][from_index] = 1.0 - treated
            matrix[from_index][event_index] = treated
            matrix[event_index][event_index] = 1.0
            output.append({"start_cycle": index + 1, "matrix": matrix})
    if (
        measure == "risk_ratio"
        and relative_effect is not None
        and positive_baselines
        and not relative_effect < 1.0 / max(positive_baselines)
    ):
        reasons.append("risk ratio must be strictly below 1 / max positive baseline probability")
    if not output or not json_equivalent(output, model_value(plan, path)):
        reasons.append("relative effect does not reproduce the current transition schedule")
    if used_extractions != set(texts(mapping.get("extraction_ids")) or []):
        reasons.append("transformation must use every selected extraction")
    if used_assumptions != set(texts(mapping.get("assumption_ids")) or []):
        reasons.append("transformation must use every proposed assumption")
    return reasons


def hazard_ratio_reasons(
    plan: dict[str, Any],
    path: str,
    mapping: dict[str, Any],
    derivation: dict[str, Any],
    extraction_index: dict[str, dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if plan.get("schema_version") != "0.11.0":
        return ["hazard-ratio transformations require schema_version 0.11.0"]
    if not transition_path(path) or not path.endswith(".transition_schedule"):
        return ["hazard-ratio transformation is allowed only for a transition schedule"]
    transformation = derivation.get("transformation")
    if not isinstance(transformation, dict):
        return ["derivation.transformation must be an object"]
    expected_fields = {
        "operation", "cycle_length_years", "from_state_index", "event_state_index",
        "baseline_cumulative_hazards", "hazard_ratio", "review_bases",
    }
    if set(transformation) != expected_fields:
        reasons.append("hazard-ratio fields are not the exact supported contract")
    if transformation.get("operation") != "hazard_ratio_to_transition_schedule":
        reasons.append("transformation.operation must be hazard_ratio_to_transition_schedule")
    states = plan.get("states")
    if not isinstance(states, list) or len(states) != 2:
        reasons.append("hazard-ratio transformation requires exactly two states")
    cycles = plan.get("cycles")
    if isinstance(cycles, bool) or not isinstance(cycles, int) or not 1 <= cycles <= 10_000:
        reasons.append("hazard-ratio transformation supports 1-10000 cycles")
        cycles = 0
    cycle_length = transformation.get("cycle_length_years")
    if (
        not finite_number(cycle_length)
        or cycle_length <= 0
        or not finite_number(plan.get("cycle_length_years"))
        or not isclose(float(cycle_length), float(plan["cycle_length_years"]), rel_tol=0.0, abs_tol=1e-12)
    ):
        reasons.append("cycle_length_years must equal the positive analysis cycle length")
    from_index = transformation.get("from_state_index")
    event_index = transformation.get("event_state_index")
    valid_indices = (
        isinstance(from_index, int) and not isinstance(from_index, bool)
        and isinstance(event_index, int) and not isinstance(event_index, bool)
        and {from_index, event_index} == {0, 1}
    )
    if not valid_indices:
        reasons.append("from_state_index and event_state_index must be the two distinct state indices")
    used_extractions: set[str] = set()
    used_assumptions: set[str] = set()

    def value_with_basis(value: Any, label: str) -> float | None:
        allowed = {"value", "source_extraction_id", "source_pointer", "assumption_id"}
        if not isinstance(value, dict) or set(value) - allowed:
            reasons.append(f"{label} contains unsupported fields")
            return None
        number = value.get("value")
        if not finite_number(number):
            reasons.append(f"{label}.value must be finite")
            return None
        source_id = value.get("source_extraction_id")
        assumption_id = value.get("assumption_id")
        if text(source_id) == text(assumption_id):
            reasons.append(f"{label} must declare exactly one extraction or assumption basis")
        elif text(source_id):
            used_extractions.add(source_id)
            extraction = extraction_index.get(source_id)
            if extraction is not None:
                try:
                    extracted = strict_json(extraction.get("extracted_value"))
                    extracted = json_pointer(extracted, value.get("source_pointer", ""))
                except (TypeError, ValueError, json.JSONDecodeError) as error:
                    reasons.append(f"{label}: {error}")
                else:
                    if not json_equivalent(extracted, number):
                        reasons.append(f"{label}.value does not match the bound extraction")
        else:
            used_assumptions.add(assumption_id)
            if "source_pointer" in value:
                reasons.append(f"{label}.source_pointer requires an extraction")
        return float(number)

    def review_basis(value: Any, label: str) -> None:
        allowed = {"source_extraction_id", "source_pointer", "assumption_id"}
        if not isinstance(value, dict) or set(value) - allowed:
            reasons.append(f"{label} fields are invalid")
            return
        source_id = value.get("source_extraction_id")
        assumption_id = value.get("assumption_id")
        if text(source_id) == text(assumption_id):
            reasons.append(f"{label} must declare exactly one extraction or assumption basis")
        elif text(source_id):
            used_extractions.add(source_id)
            pointer = value.get("source_pointer")
            if pointer is not None and (
                not isinstance(pointer, str) or (pointer and not pointer.startswith("/"))
            ):
                reasons.append(f"{label}.source_pointer is invalid")
        else:
            used_assumptions.add(assumption_id)
            if "source_pointer" in value:
                reasons.append(f"{label}.source_pointer requires an extraction")

    hazard_ratio = value_with_basis(transformation.get("hazard_ratio"), "hazard_ratio")
    if hazard_ratio is None or hazard_ratio <= 0:
        reasons.append("hazard_ratio.value must be positive")
    review_bases = transformation.get("review_bases")
    required_reviews = {
        "endpoint_alignment", "population_transportability",
        "proportional_hazards_assumption", "effect_constancy_over_horizon",
        "treatment_switching_assessment",
    }
    if not isinstance(review_bases, dict) or set(review_bases) != required_reviews:
        reasons.append("review_bases must contain exactly the five required review questions")
    else:
        for name in sorted(required_reviews):
            review_basis(review_bases[name], f"review_bases.{name}")
    entries = transformation.get("baseline_cumulative_hazards")
    if not isinstance(entries, list) or len(entries) != cycles:
        reasons.append("baseline_cumulative_hazards must cover every model cycle")
        entries = []
    previous = 0.0
    any_positive = False
    output: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        label = f"baseline_cumulative_hazards[{index}]"
        if not isinstance(entry, dict) or set(entry) != {"cycle", "cumulative_hazard"}:
            reasons.append(f"{label} fields are invalid")
            continue
        if entry.get("cycle") != index + 1:
            reasons.append(f"{label}.cycle must equal its one-based position")
        cumulative = value_with_basis(entry.get("cumulative_hazard"), f"{label}.cumulative_hazard")
        if cumulative is None or cumulative < 0:
            reasons.append(f"{label}.cumulative_hazard.value must be non-negative")
            continue
        if cumulative + 1e-12 < previous:
            reasons.append("baseline_cumulative_hazards must be non-decreasing across cycles")
            continue
        increment = max(0.0, cumulative - previous)
        any_positive = any_positive or increment > 1e-12
        previous = cumulative
        if hazard_ratio is None or hazard_ratio <= 0 or not valid_indices:
            continue
        probability = -expm1(-hazard_ratio * increment)
        if not isfinite(probability) or not 0 <= probability < 1:
            reasons.append(f"{label} produced a non-finite or invalid event probability")
            continue
        matrix = [[0.0, 0.0], [0.0, 0.0]]
        matrix[from_index][from_index] = 1.0 - probability
        matrix[from_index][event_index] = probability
        matrix[event_index][event_index] = 1.0
        output.append({"start_cycle": index + 1, "matrix": matrix})
    if not any_positive:
        reasons.append("baseline_cumulative_hazards must contain at least one positive increment")
    if not output or not json_equivalent(output, model_value(plan, path)):
        reasons.append("hazard ratio does not reproduce the current transition schedule")
    if used_extractions != set(texts(mapping.get("extraction_ids")) or []):
        reasons.append("transformation must use every selected extraction")
    if used_assumptions != set(texts(mapping.get("assumption_ids")) or []):
        reasons.append("transformation must use every proposed assumption")
    return reasons


def background_mortality_reasons(
    plan: dict[str, Any],
    path: str,
    mapping: dict[str, Any],
    derivation: dict[str, Any],
    extraction_index: dict[str, dict[str, Any]],
) -> list[str]:
    reasons: list[str] = []
    if plan.get("schema_version") not in {"0.9.0", "0.10.0", "0.11.0"}:
        return ["background-plus-excess mortality requires schema_version 0.9.0 through 0.11.0"]
    if not transition_path(path) or not path.endswith(".transition_schedule"):
        return ["background mortality transformation is allowed only for a transition schedule"]
    transformation = derivation.get("transformation")
    if not isinstance(transformation, dict):
        return ["derivation.transformation must be an object"]
    expected_fields = {
        "operation", "cycle_length_years", "from_state_index", "death_state_index",
        "life_table", "excess_mortality_rate_per_year", "review_bases",
    }
    if set(transformation) != expected_fields:
        reasons.append("background mortality fields are not the exact supported contract")
    if transformation.get("operation") != "background_plus_excess_mortality_to_transition_schedule":
        reasons.append("transformation.operation must be background_plus_excess_mortality_to_transition_schedule")
    states = plan.get("states")
    if not isinstance(states, list) or len(states) != 2:
        reasons.append("background mortality transformation requires exactly two states")
    cycles = plan.get("cycles")
    if isinstance(cycles, bool) or not isinstance(cycles, int) or not 1 <= cycles <= 10_000:
        reasons.append("background mortality transformation supports 1-10000 cycles")
        cycles = 0
    cycle_length = transformation.get("cycle_length_years")
    valid_cycle_length = finite_number(cycle_length) and cycle_length > 0
    if (
        not finite_number(cycle_length)
        or cycle_length <= 0
        or not finite_number(plan.get("cycle_length_years"))
        or not isclose(
            float(cycle_length), float(plan["cycle_length_years"]),
            rel_tol=0.0, abs_tol=1e-12,
        )
    ):
        reasons.append("background mortality requires a positive cycle length equal to the analysis")
    from_index = transformation.get("from_state_index")
    death_index = transformation.get("death_state_index")
    if (
        isinstance(from_index, bool) or not isinstance(from_index, int)
        or isinstance(death_index, bool) or not isinstance(death_index, int)
        or {from_index, death_index} != {0, 1}
    ):
        reasons.append("from_state_index and death_state_index must be the two distinct state indices")

    used_extractions: set[str] = set()
    used_assumptions: set[str] = set()

    def parameter_value(value: Any, label: str, *, integer: bool = False) -> float | int | None:
        allowed = {"value", "source_extraction_id", "source_pointer", "assumption_id"}
        if not isinstance(value, dict) or set(value) - allowed:
            reasons.append(f"{label} contains unsupported fields")
            return None
        number = value.get("value")
        if integer:
            valid_number = isinstance(number, int) and not isinstance(number, bool) and number >= 0
        else:
            valid_number = finite_number(number)
        if not valid_number:
            reasons.append(f"{label}.value is invalid")
            return None
        source_id = value.get("source_extraction_id")
        assumption_id = value.get("assumption_id")
        has_source = text(source_id)
        has_assumption = text(assumption_id)
        if has_source == has_assumption:
            reasons.append(f"{label} must declare exactly one extraction or assumption basis")
        elif has_source:
            used_extractions.add(source_id)
            extraction = extraction_index.get(source_id)
            if extraction is not None:
                try:
                    extracted = strict_json(extraction.get("extracted_value"))
                    extracted = json_pointer(extracted, value.get("source_pointer", ""))
                except (TypeError, ValueError, json.JSONDecodeError) as error:
                    reasons.append(f"{label}: {error}")
                else:
                    if not json_equivalent(extracted, number):
                        reasons.append(f"{label}.value does not match the bound extraction")
        else:
            used_assumptions.add(assumption_id)
            if "source_pointer" in value:
                reasons.append(f"{label}.source_pointer requires an extraction")
        return number

    life_table = transformation.get("life_table")
    life_fields = {
        "jurisdiction", "table_year", "population", "sex", "start_age_years",
        "cycle_probabilities",
    }
    if not isinstance(life_table, dict) or set(life_table) != life_fields:
        reasons.append("life_table fields are not the exact supported contract")
        life_table = {}
    for field in ("jurisdiction", "population", "sex"):
        if not text(life_table.get(field)):
            reasons.append(f"life_table.{field} is required")
    if text(life_table.get("jurisdiction")) and mapping.get("jurisdiction") != life_table.get("jurisdiction"):
        reasons.append("mapping jurisdiction must equal life_table.jurisdiction")
    table_year = life_table.get("table_year")
    if isinstance(table_year, bool) or not isinstance(table_year, int) or not 1900 <= table_year <= 2100:
        reasons.append("life_table.table_year must be from 1900 to 2100")
    start_age = life_table.get("start_age_years")
    if not finite_number(start_age) or start_age < 0:
        reasons.append("life_table.start_age_years must be finite and non-negative")
        start_age = None
    entries = life_table.get("cycle_probabilities")
    if not isinstance(entries, list) or len(entries) != cycles:
        reasons.append("life_table.cycle_probabilities must cover every model cycle")
        entries = []

    probabilities: list[float] = []
    for index, entry in enumerate(entries):
        label = f"life_table.cycle_probabilities[{index}]"
        if not isinstance(entry, dict) or set(entry) != {
            "cycle", "attained_age_years", "annual_probability"
        }:
            reasons.append(f"{label} fields are invalid")
            continue
        cycle_number = entry.get("cycle")
        if (
            isinstance(cycle_number, bool)
            or not isinstance(cycle_number, int)
            or cycle_number != index + 1
        ):
            reasons.append(f"{label}.cycle must equal its one-based position")
        attained_age = entry.get("attained_age_years")
        expected_age = (
            floor(float(start_age) + index * float(cycle_length))
            if finite_number(start_age) and valid_cycle_length
            else None
        )
        if (
            isinstance(attained_age, bool)
            or not finite_number(attained_age)
            or not float(attained_age).is_integer()
            or (expected_age is not None and int(attained_age) != expected_age)
        ):
            reasons.append(f"{label}.attained_age_years is not cycle-aligned")
        probability = parameter_value(entry.get("annual_probability"), f"{label}.annual_probability")
        if probability is None or not 0 <= probability < 1:
            reasons.append(f"{label}.annual_probability.value must be from 0 inclusive to 1 exclusive")
        else:
            probabilities.append(float(probability))

    excess_rate = parameter_value(
        transformation.get("excess_mortality_rate_per_year"),
        "excess_mortality_rate_per_year",
    )
    if excess_rate is None or excess_rate < 0:
        reasons.append("excess_mortality_rate_per_year.value must be non-negative")

    review_bases = transformation.get("review_bases")
    required_reviews = {"population_exchangeability", "no_double_counting"}
    if not isinstance(review_bases, dict) or set(review_bases) != required_reviews:
        reasons.append("review_bases must contain exactly the two required review questions")
    else:
        for name in sorted(required_reviews):
            label = f"review_bases.{name}"
            basis = review_bases[name]
            allowed = {"source_extraction_id", "source_pointer", "assumption_id"}
            if not isinstance(basis, dict) or set(basis) - allowed:
                reasons.append(f"{label} fields are invalid")
                continue
            source_id = basis.get("source_extraction_id")
            assumption_id = basis.get("assumption_id")
            has_source = text(source_id)
            has_assumption = text(assumption_id)
            if has_source == has_assumption:
                reasons.append(f"{label} must declare exactly one extraction or assumption basis")
            elif has_source:
                used_extractions.add(source_id)
                pointer = basis.get("source_pointer")
                if pointer is not None and (
                    not isinstance(pointer, str) or (pointer and not pointer.startswith("/"))
                ):
                    reasons.append(f"{label}.source_pointer is invalid")
            else:
                used_assumptions.add(assumption_id)
                if "source_pointer" in basis:
                    reasons.append(f"{label}.source_pointer requires an extraction")

    output: list[dict[str, Any]] = []
    if (
        cycles > 0
        and len(probabilities) == cycles
        and valid_cycle_length
        and finite_number(excess_rate)
        and excess_rate >= 0
        and from_index in {0, 1}
        and death_index in {0, 1}
        and from_index != death_index
    ):
        for index, probability in enumerate(probabilities):
            integrated_hazard = (
                -log1p(-probability) + float(excess_rate)
            ) * float(cycle_length)
            if not isfinite(integrated_hazard):
                reasons.append(
                    f"life_table.cycle_probabilities[{index}] produced a non-finite integrated hazard"
                )
                continue
            death_probability = -expm1(-integrated_hazard)
            if not isfinite(death_probability) or not 0 <= death_probability < 1:
                reasons.append(
                    f"life_table.cycle_probabilities[{index}] produced an invalid death probability"
                )
                continue
            matrix = [[0.0, 0.0], [0.0, 0.0]]
            matrix[from_index][from_index] = 1.0 - death_probability
            matrix[from_index][death_index] = death_probability
            matrix[death_index][death_index] = 1.0
            output.append({"start_cycle": index + 1, "matrix": matrix})
    if not output or not json_equivalent(output, model_value(plan, path)):
        reasons.append("background plus excess mortality does not reproduce the current transition schedule")
    if used_extractions != set(texts(mapping.get("extraction_ids")) or []):
        reasons.append("transformation must use every selected extraction")
    if used_assumptions != set(texts(mapping.get("assumption_ids")) or []):
        reasons.append("transformation must use every proposed assumption")
    return reasons


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
    if method == "deterministic_transformation":
        transformation = derivation.get("transformation")
        operation = transformation.get("operation") if isinstance(transformation, dict) else None
        if operation == "constant_competing_rates":
            reasons.extend(
                transition_rate_reasons(plan, path, mapping, derivation, extraction_index)
            )
        elif operation == "parametric_survival_to_transition_schedule":
            reasons.extend(
                survival_curve_reasons(plan, path, mapping, derivation, extraction_index)
            )
        elif operation == "single_event_probability_time_conversion":
            reasons.extend(
                probability_time_reasons(plan, path, mapping, derivation, extraction_index)
            )
        elif operation == "background_plus_excess_mortality_to_transition_schedule":
            reasons.extend(
                background_mortality_reasons(
                    plan, path, mapping, derivation, extraction_index
                )
            )
        elif operation == "relative_effect_to_transition_schedule":
            reasons.extend(
                relative_effect_reasons(
                    plan, path, mapping, derivation, extraction_index
                )
            )
        elif operation == "hazard_ratio_to_transition_schedule":
            reasons.extend(
                hazard_ratio_reasons(
                    plan, path, mapping, derivation, extraction_index
                )
            )
        else:
            reasons.append("deterministic transformation operation is unsupported")
        return reasons
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
    if plan.get("schema_version") not in APPROVABLE_ANALYSIS_SCHEMAS:
        errors.append("schema_version must be 0.3.0 through 0.15.0 for approval review")
    roles = strategy_ids(plan)
    if plan.get("schema_version") in {"0.8.0", "0.9.0", "0.10.0", "0.11.0", "0.12.0", "0.13.0", "0.14.0", "0.15.0"}:
        strategies = plan.get("strategies")
        if (
            not 2 <= len(roles) <= 16 or len(set(roles)) != len(roles)
            or any(STRATEGY_ID.fullmatch(role) is None for role in roles)
            or plan.get("baseline_strategy_id") != (roles[0] if roles else None)
            or not isinstance(strategies, dict) or set(strategies) != set(roles)
        ):
            errors.append(
                "schema 0.8.0 through 0.15.0 requires 2-16 unique safe strategy ids, an exact strategies object, and baseline_strategy_id first"
            )
    for role in roles:
        strategy = (plan.get("strategies") or {}).get(role) or {}
        has_matrix = isinstance(strategy, dict) and strategy.get("transition_matrix") is not None
        has_schedule = isinstance(strategy, dict) and strategy.get("transition_schedule") is not None
        if plan.get("schema_version") in {"0.12.0", "0.13.0", "0.14.0", "0.15.0"} and (has_matrix or has_schedule):
            errors.append(
                f"strategies.{role} transition structure is forbidden for partitioned survival"
            )
        elif plan.get("schema_version") not in {"0.12.0", "0.13.0", "0.14.0", "0.15.0"} and has_matrix == has_schedule:
            errors.append(
                f"strategies.{role} must define exactly one of transition_matrix or transition_schedule"
            )
        if has_schedule and plan.get("schema_version") not in {"0.4.0", "0.5.0", "0.6.0", "0.7.0", "0.8.0", "0.9.0", "0.10.0", "0.11.0"}:
            errors.append(
                f"strategies.{role}.transition_schedule requires schema_version 0.4.0 through 0.11.0"
            )
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
    required = required_paths(plan)
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
