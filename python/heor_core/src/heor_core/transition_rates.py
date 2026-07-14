"""Deterministic conversion of bounded constant competing rates.

This adapter converts annual cause-specific rates for mutually exclusive first
events into one discrete-time transition row per model cycle. It deliberately
does not implement general continuous-time matrix exponentiation or permit
multiple state changes within a cycle.
"""

from __future__ import annotations

from math import expm1, isclose, isfinite
import re
from typing import Any


TRANSFORMATION_METHOD = "deterministic_transformation"
TRANSFORMATION_OPERATION = "constant_competing_rates"
TOLERANCE = 1e-12
MULTI_STRATEGY_SCHEMA_VERSION = "0.8.0"
PREVIOUS_MULTI_STRATEGY_SCHEMA_VERSION = "0.9.0"
CURRENT_MULTI_STRATEGY_SCHEMA_VERSION = "0.10.0"
MULTI_STRATEGY_SCHEMA_VERSIONS = {
    MULTI_STRATEGY_SCHEMA_VERSION,
    PREVIOUS_MULTI_STRATEGY_SCHEMA_VERSION,
    CURRENT_MULTI_STRATEGY_SCHEMA_VERSION,
}
STRATEGY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class TransitionRateError(ValueError):
    """Raised when a transition-rate derivation violates the bounded contract."""


def validate_transition_rate_mappings(
    plan: dict[str, Any],
    *,
    schema_version: str,
    state_count: int,
    cycles: int,
    cycle_length_years: float,
) -> None:
    """Recompute every declared rate derivation and compare it with its target."""

    mappings = plan.get("input_provenance")
    if not isinstance(mappings, list):
        return
    for position, mapping in enumerate(mappings):
        if not isinstance(mapping, dict):
            continue
        derivation = mapping.get("derivation")
        transformation = (
            derivation.get("transformation") if isinstance(derivation, dict) else None
        )
        if (
            not isinstance(derivation, dict)
            or derivation.get("method") != TRANSFORMATION_METHOD
            or not isinstance(transformation, dict)
            or transformation.get("operation") != TRANSFORMATION_OPERATION
        ):
            continue
        label = f"input_provenance[{position}]"
        if schema_version not in {"0.5.0", *MULTI_STRATEGY_SCHEMA_VERSIONS}:
            raise TransitionRateError(
                f"{label}: deterministic transition-rate transformations require schema_version 0.5.0, {MULTI_STRATEGY_SCHEMA_VERSION}, {PREVIOUS_MULTI_STRATEGY_SCHEMA_VERSION}, or {CURRENT_MULTI_STRATEGY_SCHEMA_VERSION}"
            )
        path = mapping.get("path")
        if not isinstance(path, str) or not _transition_path(
            path, plan, schema_version
        ):
            raise TransitionRateError(
                f"{label}: deterministic transformation is allowed only for a transition matrix or schedule"
            )
        target = _model_value(plan, path)
        if target is None:
            raise TransitionRateError(f"{label}: transformation target is missing")
        if not _json_equivalent(derivation.get("model_value"), target):
            raise TransitionRateError(
                f"{label}: derivation.model_value does not match the current transition input"
            )
        output, used_extractions, used_assumptions = derive_competing_rates(
            transformation,
            target_path=path,
            state_count=state_count,
            cycles=cycles,
            cycle_length_years=cycle_length_years,
        )
        if not _json_equivalent(output, target):
            raise TransitionRateError(
                f"{label}: constant competing rates do not reproduce the current transition input"
            )
        extraction_ids = _identifier_set(mapping.get("extraction_ids"), f"{label}.extraction_ids")
        assumption_ids = _identifier_set(mapping.get("assumption_ids"), f"{label}.assumption_ids")
        if used_extractions != extraction_ids:
            raise TransitionRateError(
                f"{label}: transformation must use every selected extraction exactly as declared"
            )
        if used_assumptions != assumption_ids:
            raise TransitionRateError(
                f"{label}: transformation must use every proposed assumption exactly as declared"
            )


def derive_competing_rates(
    value: Any,
    *,
    target_path: str,
    state_count: int,
    cycles: int,
    cycle_length_years: float,
) -> tuple[Any, set[str], set[str]]:
    """Return the derived matrix or schedule and the exact declared bases used."""

    transformation = _object(value, "transformation")
    _exact_keys(
        transformation,
        {"operation", "cycle_length_years", "phases"},
        "transformation",
    )
    if transformation.get("operation") != TRANSFORMATION_OPERATION:
        raise TransitionRateError(
            f"transformation.operation must be {TRANSFORMATION_OPERATION}"
        )
    declared_cycle = _number(
        transformation.get("cycle_length_years"),
        "transformation.cycle_length_years",
    )
    if declared_cycle <= 0 or not isclose(
        declared_cycle,
        cycle_length_years,
        rel_tol=0.0,
        abs_tol=TOLERANCE,
    ):
        raise TransitionRateError(
            "transformation.cycle_length_years must equal the analysis cycle length"
        )
    phases = transformation.get("phases")
    if not isinstance(phases, list) or not 1 <= len(phases) <= cycles:
        raise TransitionRateError(
            f"transformation.phases must contain from 1 to {cycles} phases"
        )
    starts: list[int] = []
    matrices: list[list[list[float]]] = []
    used_extractions: set[str] = set()
    used_assumptions: set[str] = set()
    for phase_index, raw_phase in enumerate(phases):
        phase_label = f"transformation.phases[{phase_index}]"
        phase = _object(raw_phase, phase_label)
        _exact_keys(phase, {"start_cycle", "rows"}, phase_label)
        start_cycle = _integer(phase.get("start_cycle"), f"{phase_label}.start_cycle")
        if start_cycle < 1 or start_cycle > cycles:
            raise TransitionRateError(f"{phase_label}.start_cycle is outside the horizon")
        starts.append(start_cycle)
        rows = phase.get("rows")
        if not isinstance(rows, list) or len(rows) != state_count:
            raise TransitionRateError(
                f"{phase_label}.rows must contain {state_count} rows"
            )
        matrix: list[list[float]] = []
        for row_index, raw_row in enumerate(rows):
            row_label = f"{phase_label}.rows[{row_index}]"
            row = _object(raw_row, row_label)
            _exact_keys(row, {"self_index", "events"}, row_label)
            self_index = _integer(row.get("self_index"), f"{row_label}.self_index")
            if self_index != row_index:
                raise TransitionRateError(
                    f"{row_label}.self_index must equal its zero-based row position"
                )
            events = row.get("events")
            if not isinstance(events, list) or len(events) > state_count - 1:
                raise TransitionRateError(
                    f"{row_label}.events must contain at most {state_count - 1} events"
                )
            targets: set[int] = set()
            parsed_events: list[tuple[int, float]] = []
            total_rate = 0.0
            for event_index, raw_event in enumerate(events):
                event_label = f"{row_label}.events[{event_index}]"
                event = _object(raw_event, event_label)
                allowed = {
                    "target_index",
                    "rate_per_year",
                    "source_extraction_id",
                    "source_pointer",
                    "assumption_id",
                }
                _allowed_keys(event, allowed, event_label)
                target_index = _integer(
                    event.get("target_index"), f"{event_label}.target_index"
                )
                if not 0 <= target_index < state_count or target_index == self_index:
                    raise TransitionRateError(f"{event_label}.target_index is invalid")
                if target_index in targets:
                    raise TransitionRateError(f"{event_label}.target_index is duplicated")
                targets.add(target_index)
                rate = _number(event.get("rate_per_year"), f"{event_label}.rate_per_year")
                if rate <= 0:
                    raise TransitionRateError(
                        f"{event_label}.rate_per_year must be positive; omit structural zeros"
                    )
                source_id = event.get("source_extraction_id")
                assumption_id = event.get("assumption_id")
                has_source = isinstance(source_id, str) and bool(source_id.strip())
                has_assumption = isinstance(assumption_id, str) and bool(assumption_id.strip())
                if has_source == has_assumption:
                    raise TransitionRateError(
                        f"{event_label} must declare exactly one source_extraction_id or assumption_id"
                    )
                if has_source:
                    pointer = event.get("source_pointer", "")
                    if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
                        raise TransitionRateError(
                            f"{event_label}.source_pointer must be empty or a JSON pointer"
                        )
                    used_extractions.add(source_id)
                else:
                    if "source_pointer" in event:
                        raise TransitionRateError(
                            f"{event_label}.source_pointer requires source_extraction_id"
                        )
                    used_assumptions.add(assumption_id)
                total_rate += rate
                if not isfinite(total_rate * declared_cycle):
                    raise TransitionRateError(f"{row_label} integrated rate is non-finite")
                parsed_events.append((target_index, rate))
            output_row = [0.0] * state_count
            if total_rate == 0:
                output_row[self_index] = 1.0
            else:
                event_mass = -expm1(-total_rate * declared_cycle)
                output_row[self_index] = 1.0 - event_mass
                for target_index, rate in parsed_events:
                    output_row[target_index] = event_mass * rate / total_rate
            matrix.append(output_row)
        matrices.append(matrix)
    if starts[0] != 1 or any(left >= right for left, right in zip(starts, starts[1:])):
        raise TransitionRateError(
            "transformation phase start_cycle values must start at 1 and strictly increase"
        )
    if target_path.endswith(".transition_matrix"):
        if len(phases) != 1:
            raise TransitionRateError(
                "a static transition_matrix transformation must contain exactly one phase"
            )
        output: Any = matrices[0]
    elif target_path.endswith(".transition_schedule"):
        output = [
            {"start_cycle": start, "matrix": matrix}
            for start, matrix in zip(starts, matrices)
        ]
    else:
        raise TransitionRateError("transformation target path is not supported")
    return output, used_extractions, used_assumptions


def _transition_path(
    path: str, plan: dict[str, Any], schema_version: str
) -> bool:
    parts = path.split(".")
    return (
        len(parts) == 3
        and parts[0] == "strategies"
        and _strategy_id_allowed(parts[1], plan, schema_version)
        and parts[2] in {"transition_matrix", "transition_schedule"}
    )


def _strategy_id_allowed(
    strategy_id: str, plan: dict[str, Any], schema_version: str
) -> bool:
    if schema_version not in MULTI_STRATEGY_SCHEMA_VERSIONS:
        return strategy_id in {"comparator", "intervention"}
    order = plan.get("strategy_order")
    strategies = plan.get("strategies")
    return (
        STRATEGY_ID_PATTERN.fullmatch(strategy_id) is not None
        and isinstance(order, (list, tuple))
        and all(isinstance(item, str) for item in order)
        and isinstance(strategies, dict)
        and set(strategies) == set(order)
        and strategy_id in order
    )


def _model_value(plan: dict[str, Any], path: str) -> Any:
    current: Any = plan
    for token in path.split("."):
        if not isinstance(current, dict) or token not in current:
            return None
        current = current[token]
    return current


def _json_equivalent(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if _is_number(left) or _is_number(right):
        return _is_number(left) and _is_number(right) and isclose(
            float(left), float(right), rel_tol=TOLERANCE, abs_tol=TOLERANCE
        )
    if isinstance(left, list) or isinstance(right, list):
        return (
            isinstance(left, list)
            and isinstance(right, list)
            and len(left) == len(right)
            and all(_json_equivalent(a, b) for a, b in zip(left, right))
        )
    if isinstance(left, dict) or isinstance(right, dict):
        return (
            isinstance(left, dict)
            and isinstance(right, dict)
            and left.keys() == right.keys()
            and all(_json_equivalent(left[key], right[key]) for key in left)
        )
    return left == right


def _identifier_set(value: Any, label: str) -> set[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise TransitionRateError(f"{label} must be an array of non-empty strings")
    if len(value) != len(set(value)):
        raise TransitionRateError(f"{label} must not contain duplicates")
    return set(value)


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise TransitionRateError(f"{label} must be an object")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise TransitionRateError(
            f"{label} fields must be exactly {', '.join(sorted(expected))}"
        )


def _allowed_keys(value: dict[str, Any], allowed: set[str], label: str) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise TransitionRateError(
            f"{label} contains unsupported fields: {', '.join(sorted(unknown))}"
        )


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TransitionRateError(f"{label} must be an integer")
    return value


def _number(value: Any, label: str) -> float:
    if not _is_number(value):
        raise TransitionRateError(f"{label} must be finite")
    return float(value)


def _is_number(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and isfinite(value)
