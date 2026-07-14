"""Bounded parametric survival-to-transition conversion.

The adapter evaluates declared exponential or Weibull parameters and creates a
complete two-state model-cycle transition schedule. It does not fit curves,
select distributions, combine endpoints, or infer treatment effects.
"""

from __future__ import annotations

from math import expm1, isclose, isfinite
from typing import Any


TRANSFORMATION_METHOD = "deterministic_transformation"
TRANSFORMATION_OPERATION = "parametric_survival_to_transition_schedule"
ANALYSIS_SCHEMA_VERSION = "0.6.0"
MAX_SURVIVAL_CYCLES = 10_000
TOLERANCE = 1e-12


class SurvivalCurveError(ValueError):
    """Raised when a survival-curve derivation violates the bounded contract."""


def validate_survival_curve_mappings(
    plan: dict[str, Any],
    *,
    schema_version: str,
    state_count: int,
    cycles: int,
    cycle_length_years: float,
) -> None:
    """Recompute every declared survival derivation and compare its target."""

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
        if schema_version != ANALYSIS_SCHEMA_VERSION:
            raise SurvivalCurveError(
                f"{label}: parametric survival transformations require schema_version {ANALYSIS_SCHEMA_VERSION}"
            )
        path = mapping.get("path")
        if path not in {
            "strategies.comparator.transition_schedule",
            "strategies.intervention.transition_schedule",
        }:
            raise SurvivalCurveError(
                f"{label}: parametric survival transformation is allowed only for a transition schedule"
            )
        target = _model_value(plan, path)
        if target is None:
            raise SurvivalCurveError(f"{label}: transformation target is missing")
        if not _json_equivalent(derivation.get("model_value"), target):
            raise SurvivalCurveError(
                f"{label}: derivation.model_value does not match the current transition input"
            )
        output, used_extractions, used_assumptions = derive_survival_schedule(
            transformation,
            state_count=state_count,
            cycles=cycles,
            cycle_length_years=cycle_length_years,
        )
        if not _json_equivalent(output, target):
            raise SurvivalCurveError(
                f"{label}: parametric survival curve does not reproduce the current transition schedule"
            )
        extraction_ids = _identifier_set(
            mapping.get("extraction_ids"), f"{label}.extraction_ids"
        )
        assumption_ids = _identifier_set(
            mapping.get("assumption_ids"), f"{label}.assumption_ids"
        )
        if used_extractions != extraction_ids:
            raise SurvivalCurveError(
                f"{label}: transformation must use every selected extraction exactly as declared"
            )
        if used_assumptions != assumption_ids:
            raise SurvivalCurveError(
                f"{label}: transformation must use every proposed assumption exactly as declared"
            )


def apply_survival_curve_mappings(
    plan: dict[str, Any], mapping_indices: set[int]
) -> None:
    """Recompute selected survival schedules after parameter replacement."""

    mappings = plan.get("input_provenance")
    if not isinstance(mappings, list):
        raise SurvivalCurveError("input_provenance must be an array")
    states = plan.get("states")
    cycles = plan.get("cycles")
    cycle_length = plan.get("cycle_length_years")
    if (
        not isinstance(states, list)
        or isinstance(cycles, bool)
        or not isinstance(cycles, int)
        or not _is_number(cycle_length)
    ):
        raise SurvivalCurveError("analysis dimensions are invalid")
    for mapping_index in sorted(mapping_indices):
        if not 0 <= mapping_index < len(mappings):
            raise SurvivalCurveError("survival mapping index is invalid")
        mapping = _object(mappings[mapping_index], f"input_provenance[{mapping_index}]")
        derivation = _object(
            mapping.get("derivation"),
            f"input_provenance[{mapping_index}].derivation",
        )
        transformation = derivation.get("transformation")
        if (
            derivation.get("method") != TRANSFORMATION_METHOD
            or not isinstance(transformation, dict)
            or transformation.get("operation") != TRANSFORMATION_OPERATION
        ):
            raise SurvivalCurveError(
                "survival parameter target must bind a parametric survival transformation"
            )
        output, _, _ = derive_survival_schedule(
            transformation,
            state_count=len(states),
            cycles=cycles,
            cycle_length_years=float(cycle_length),
        )
        path = mapping.get("path")
        if not isinstance(path, str):
            raise SurvivalCurveError("survival transformation path is invalid")
        _set_model_value(plan, path, output)
        derivation["model_value"] = output


def derive_survival_schedule(
    value: Any,
    *,
    state_count: int,
    cycles: int,
    cycle_length_years: float,
) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    """Return a complete per-cycle schedule and exact declared bases used."""

    transformation = _object(value, "transformation")
    _exact_keys(
        transformation,
        {
            "operation",
            "cycle_length_years",
            "from_state_index",
            "event_state_index",
            "distribution",
            "parameters",
        },
        "transformation",
    )
    if transformation.get("operation") != TRANSFORMATION_OPERATION:
        raise SurvivalCurveError(
            f"transformation.operation must be {TRANSFORMATION_OPERATION}"
        )
    if state_count != 2:
        raise SurvivalCurveError(
            "parametric survival transformation requires exactly two states"
        )
    if not 1 <= cycles <= MAX_SURVIVAL_CYCLES:
        raise SurvivalCurveError(
            f"parametric survival transformation supports 1-{MAX_SURVIVAL_CYCLES} cycles"
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
        raise SurvivalCurveError(
            "transformation.cycle_length_years must equal the analysis cycle length"
        )
    from_index = _integer(
        transformation.get("from_state_index"),
        "transformation.from_state_index",
    )
    event_index = _integer(
        transformation.get("event_state_index"),
        "transformation.event_state_index",
    )
    if {from_index, event_index} != {0, 1}:
        raise SurvivalCurveError(
            "from_state_index and event_state_index must be the two distinct state indices"
        )
    distribution = transformation.get("distribution")
    expected_parameters = {
        "exponential": {"rate_per_year"},
        "weibull": {"shape", "scale_years"},
    }.get(distribution)
    if expected_parameters is None:
        raise SurvivalCurveError(
            "transformation.distribution must be exponential or weibull"
        )
    raw_parameters = _object(transformation.get("parameters"), "transformation.parameters")
    _exact_keys(raw_parameters, expected_parameters, "transformation.parameters")
    parameters: dict[str, float] = {}
    used_extractions: set[str] = set()
    used_assumptions: set[str] = set()
    for name in sorted(expected_parameters):
        parameter, extraction_id, assumption_id = _survival_parameter(
            raw_parameters.get(name), f"transformation.parameters.{name}"
        )
        parameters[name] = parameter
        if extraction_id is not None:
            used_extractions.add(extraction_id)
        if assumption_id is not None:
            used_assumptions.add(assumption_id)

    schedule: list[dict[str, Any]] = []
    previous_hazard = 0.0
    for cycle in range(1, cycles + 1):
        time_years = cycle * declared_cycle
        cumulative_hazard = _cumulative_hazard(
            distribution, parameters, time_years
        )
        hazard_increment = cumulative_hazard - previous_hazard
        if not isfinite(hazard_increment) or hazard_increment < -TOLERANCE:
            raise SurvivalCurveError(
                "parametric survival cumulative hazard must be finite and non-decreasing"
            )
        event_probability = -expm1(-max(0.0, hazard_increment))
        if not isfinite(event_probability) or not 0.0 <= event_probability <= 1.0:
            raise SurvivalCurveError(
                "parametric survival interval probability is invalid"
            )
        matrix = [[0.0, 0.0], [0.0, 0.0]]
        matrix[from_index][from_index] = 1.0 - event_probability
        matrix[from_index][event_index] = event_probability
        matrix[event_index][event_index] = 1.0
        schedule.append({"start_cycle": cycle, "matrix": matrix})
        previous_hazard = cumulative_hazard
    return schedule, used_extractions, used_assumptions


def _survival_parameter(
    value: Any, label: str
) -> tuple[float, str | None, str | None]:
    parameter = _object(value, label)
    allowed = {"value", "source_extraction_id", "source_pointer", "assumption_id"}
    unknown = set(parameter) - allowed
    if unknown:
        raise SurvivalCurveError(
            f"{label} contains unsupported fields: {', '.join(sorted(unknown))}"
        )
    number = _number(parameter.get("value"), f"{label}.value")
    if number <= 0:
        raise SurvivalCurveError(f"{label}.value must be positive")
    source_id = parameter.get("source_extraction_id")
    assumption_id = parameter.get("assumption_id")
    has_source = isinstance(source_id, str) and bool(source_id.strip())
    has_assumption = isinstance(assumption_id, str) and bool(assumption_id.strip())
    if has_source == has_assumption:
        raise SurvivalCurveError(
            f"{label} must declare exactly one source_extraction_id or assumption_id"
        )
    if has_source:
        pointer = parameter.get("source_pointer", "")
        if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
            raise SurvivalCurveError(
                f"{label}.source_pointer must be empty or a JSON pointer"
            )
    elif "source_pointer" in parameter:
        raise SurvivalCurveError(
            f"{label}.source_pointer requires source_extraction_id"
        )
    return (
        number,
        source_id if has_source else None,
        assumption_id if has_assumption else None,
    )


def _cumulative_hazard(
    distribution: str, parameters: dict[str, float], time_years: float
) -> float:
    try:
        if distribution == "exponential":
            result = parameters["rate_per_year"] * time_years
        else:
            result = (time_years / parameters["scale_years"]) ** parameters["shape"]
    except (ArithmeticError, OverflowError) as error:
        raise SurvivalCurveError(
            "parametric survival cumulative hazard overflowed"
        ) from error
    if not isfinite(result) or result < 0:
        raise SurvivalCurveError(
            "parametric survival cumulative hazard must be finite and non-negative"
        )
    return result


def _model_value(plan: dict[str, Any], path: str) -> Any:
    current: Any = plan
    for token in path.split("."):
        if not isinstance(current, dict) or token not in current:
            return None
        current = current[token]
    return current


def _set_model_value(plan: dict[str, Any], path: str, value: Any) -> None:
    tokens = path.split(".")
    current: Any = plan
    for token in tokens[:-1]:
        if not isinstance(current, dict) or token not in current:
            raise SurvivalCurveError(f"survival target path {path!r} does not exist")
        current = current[token]
    if not isinstance(current, dict) or tokens[-1] not in current:
        raise SurvivalCurveError(f"survival target path {path!r} does not exist")
    current[tokens[-1]] = value


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
        raise SurvivalCurveError(f"{label} must be an array of non-empty strings")
    if len(value) != len(set(value)):
        raise SurvivalCurveError(f"{label} must not contain duplicates")
    return set(value)


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise SurvivalCurveError(f"{label} must be an object")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise SurvivalCurveError(
            f"{label} fields must be exactly {', '.join(sorted(expected))}"
        )


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise SurvivalCurveError(f"{label} must be an integer")
    return value


def _number(value: Any, label: str) -> float:
    if not _is_number(value):
        raise SurvivalCurveError(f"{label} must be finite")
    return float(value)


def _is_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and isfinite(value)
    )
