"""Evidence-bound binary relative-effect conversion.

The adapter applies one reviewed risk ratio or odds ratio to one baseline
binary-event probability for every model cycle and emits a complete two-state
transition schedule. It does not estimate relative effects, convert effect
measures, align endpoints, or establish population transportability.
"""

from __future__ import annotations

from math import isclose, isfinite
import re
from typing import Any


TRANSFORMATION_METHOD = "deterministic_transformation"
TRANSFORMATION_OPERATION = "relative_effect_to_transition_schedule"
ANALYSIS_SCHEMA_VERSION = "0.10.0"
STRATEGY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
TOLERANCE = 1e-12
MAX_CYCLES = 10_000


class RelativeEffectError(ValueError):
    """Raised when a binary relative-effect derivation violates the contract."""


def validate_relative_effect_mappings(
    plan: dict[str, Any],
    *,
    schema_version: str,
    state_count: int,
    cycles: int,
    cycle_length_years: float,
) -> None:
    """Recompute every declared binary relative-effect schedule."""

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
            raise RelativeEffectError(
                f"{label}: relative-effect transformations require schema_version "
                f"{ANALYSIS_SCHEMA_VERSION}"
            )
        path = mapping.get("path")
        if not isinstance(path, str) or not _transition_schedule_path(path, plan):
            raise RelativeEffectError(
                f"{label}: relative effects are allowed only for a declared "
                "strategy transition_schedule"
            )
        target = _model_value(plan, path)
        if target is None:
            raise RelativeEffectError(f"{label}: transformation target is missing")
        if not _json_equivalent(derivation.get("model_value"), target):
            raise RelativeEffectError(
                f"{label}: derivation.model_value does not match the current transition schedule"
            )
        output, used_extractions, used_assumptions = derive_relative_effect_schedule(
            transformation,
            state_count=state_count,
            cycles=cycles,
            cycle_length_years=cycle_length_years,
        )
        if not _json_equivalent(output, target):
            raise RelativeEffectError(
                f"{label}: relative-effect transformation does not reproduce "
                "the current transition schedule"
            )
        extraction_ids = _identifier_set(
            mapping.get("extraction_ids"), f"{label}.extraction_ids"
        )
        assumption_ids = _identifier_set(
            mapping.get("assumption_ids"), f"{label}.assumption_ids"
        )
        if used_extractions != extraction_ids:
            raise RelativeEffectError(
                f"{label}: transformation must use every selected extraction exactly as declared"
            )
        if used_assumptions != assumption_ids:
            raise RelativeEffectError(
                f"{label}: transformation must use every proposed assumption exactly as declared"
            )


def apply_relative_effect_mappings(
    plan: dict[str, Any], mapping_indices: set[int]
) -> None:
    """Recompute selected schedules after a relative-effect replacement."""

    mappings = plan.get("input_provenance")
    states = plan.get("states")
    cycles = plan.get("cycles")
    cycle_length = plan.get("cycle_length_years")
    if (
        not isinstance(mappings, list)
        or not isinstance(states, list)
        or isinstance(cycles, bool)
        or not isinstance(cycles, int)
        or not _is_number(cycle_length)
    ):
        raise RelativeEffectError("analysis dimensions are invalid")
    for mapping_index in sorted(mapping_indices):
        if not 0 <= mapping_index < len(mappings):
            raise RelativeEffectError("relative-effect mapping index is invalid")
        mapping = _object(mappings[mapping_index], f"input_provenance[{mapping_index}]")
        derivation = _object(
            mapping.get("derivation"), f"input_provenance[{mapping_index}].derivation"
        )
        transformation = derivation.get("transformation")
        if (
            derivation.get("method") != TRANSFORMATION_METHOD
            or not isinstance(transformation, dict)
            or transformation.get("operation") != TRANSFORMATION_OPERATION
        ):
            raise RelativeEffectError(
                "relative-effect target must bind an admitted relative-effect transformation"
            )
        output, _, _ = derive_relative_effect_schedule(
            transformation,
            state_count=len(states),
            cycles=cycles,
            cycle_length_years=float(cycle_length),
        )
        path = mapping.get("path")
        if not isinstance(path, str):
            raise RelativeEffectError("relative-effect mapping path is invalid")
        _set_model_value(plan, path, output)
        derivation["model_value"] = output


def derive_relative_effect_schedule(
    value: Any,
    *,
    state_count: int,
    cycles: int,
    cycle_length_years: float,
) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    """Return a complete schedule and the exact evidence/assumption bases used."""

    transformation = _object(value, "transformation")
    _exact_keys(
        transformation,
        {
            "operation",
            "cycle_length_years",
            "effect_interval_years",
            "from_state_index",
            "event_state_index",
            "measure",
            "baseline_cycle_probabilities",
            "relative_effect",
            "review_bases",
        },
        "transformation",
    )
    if transformation.get("operation") != TRANSFORMATION_OPERATION:
        raise RelativeEffectError(
            f"transformation.operation must be {TRANSFORMATION_OPERATION}"
        )
    if state_count != 2:
        raise RelativeEffectError("relative-effect conversion requires exactly two states")
    if isinstance(cycles, bool) or not isinstance(cycles, int) or not 1 <= cycles <= MAX_CYCLES:
        raise RelativeEffectError(
            f"relative-effect conversion supports 1-{MAX_CYCLES} cycles"
        )
    declared_cycle = _number(
        transformation.get("cycle_length_years"),
        "transformation.cycle_length_years",
    )
    effect_interval = _number(
        transformation.get("effect_interval_years"),
        "transformation.effect_interval_years",
    )
    if declared_cycle <= 0 or not isclose(
        declared_cycle, cycle_length_years, rel_tol=0.0, abs_tol=TOLERANCE
    ):
        raise RelativeEffectError(
            "transformation.cycle_length_years must equal the analysis cycle length"
        )
    if effect_interval <= 0 or not isclose(
        effect_interval, declared_cycle, rel_tol=0.0, abs_tol=TOLERANCE
    ):
        raise RelativeEffectError(
            "transformation.effect_interval_years must equal the model cycle length"
        )
    from_index = _integer(
        transformation.get("from_state_index"), "transformation.from_state_index"
    )
    event_index = _integer(
        transformation.get("event_state_index"), "transformation.event_state_index"
    )
    if {from_index, event_index} != {0, 1}:
        raise RelativeEffectError(
            "from_state_index and event_state_index must be the two distinct state indices"
        )
    measure = transformation.get("measure")
    if measure not in {"risk_ratio", "odds_ratio"}:
        raise RelativeEffectError(
            "transformation.measure must be risk_ratio or odds_ratio"
        )

    used_extractions: set[str] = set()
    used_assumptions: set[str] = set()
    effect, extraction_id, assumption_id = _value_parameter(
        transformation.get("relative_effect"),
        "transformation.relative_effect",
        minimum_exclusive=0.0,
        upper_exclusive=None,
    )
    _record_basis(extraction_id, assumption_id, used_extractions, used_assumptions)

    review_bases = _object(
        transformation.get("review_bases"), "transformation.review_bases"
    )
    _exact_keys(
        review_bases,
        {
            "endpoint_alignment",
            "population_transportability",
            "effect_constancy_over_cycles",
        },
        "transformation.review_bases",
    )
    for field in (
        "endpoint_alignment",
        "population_transportability",
        "effect_constancy_over_cycles",
    ):
        extraction_id, assumption_id = _basis(
            review_bases.get(field), f"transformation.review_bases.{field}"
        )
        _record_basis(extraction_id, assumption_id, used_extractions, used_assumptions)

    probabilities = transformation.get("baseline_cycle_probabilities")
    if not isinstance(probabilities, list) or len(probabilities) != cycles:
        raise RelativeEffectError(
            "transformation.baseline_cycle_probabilities length must equal cycles"
        )
    schedule: list[dict[str, Any]] = []
    has_positive_baseline = False
    for index, raw_entry in enumerate(probabilities):
        cycle = index + 1
        label = f"transformation.baseline_cycle_probabilities[{index}]"
        entry = _object(raw_entry, label)
        _exact_keys(entry, {"cycle", "probability"}, label)
        if _integer(entry.get("cycle"), f"{label}.cycle") != cycle:
            raise RelativeEffectError(
                f"{label}.cycle must equal its one-based model cycle"
            )
        baseline, extraction_id, assumption_id = _value_parameter(
            entry.get("probability"),
            f"{label}.probability",
            minimum_exclusive=None,
            upper_exclusive=1.0,
        )
        _record_basis(extraction_id, assumption_id, used_extractions, used_assumptions)
        has_positive_baseline = has_positive_baseline or baseline > 0.0
        try:
            if measure == "risk_ratio":
                event_probability = baseline * effect
            else:
                numerator = effect * baseline
                event_probability = numerator / (1.0 - baseline + numerator)
        except (ArithmeticError, OverflowError, ZeroDivisionError) as error:
            raise RelativeEffectError(
                f"{label}: relative-effect conversion failed"
            ) from error
        if not isfinite(event_probability) or not 0.0 <= event_probability < 1.0:
            raise RelativeEffectError(
                f"{label}: relative-effect conversion produced a non-finite or invalid probability"
            )
        matrix = [[0.0, 0.0], [0.0, 0.0]]
        matrix[from_index][from_index] = 1.0 - event_probability
        matrix[from_index][event_index] = event_probability
        matrix[event_index][event_index] = 1.0
        schedule.append({"start_cycle": cycle, "matrix": matrix})
    if not has_positive_baseline:
        raise RelativeEffectError(
            "baseline_cycle_probabilities must contain at least one probability greater than zero"
        )
    return schedule, used_extractions, used_assumptions


def _value_parameter(
    value: Any,
    label: str,
    *,
    minimum_exclusive: float | None,
    upper_exclusive: float | None,
) -> tuple[float, str | None, str | None]:
    parameter = _object(value, label)
    allowed = {"value", "source_extraction_id", "source_pointer", "assumption_id"}
    unknown = set(parameter) - allowed
    if unknown:
        raise RelativeEffectError(
            f"{label} contains unsupported fields: {', '.join(sorted(unknown))}"
        )
    number = _number(parameter.get("value"), f"{label}.value")
    if minimum_exclusive is not None and number <= minimum_exclusive:
        raise RelativeEffectError(
            f"{label}.value must be greater than {minimum_exclusive}"
        )
    if upper_exclusive is not None and number >= upper_exclusive:
        raise RelativeEffectError(
            f"{label}.value must be less than {upper_exclusive}"
        )
    if minimum_exclusive is None and number < 0.0:
        raise RelativeEffectError(f"{label}.value must be at least 0.0")
    extraction_id, assumption_id = _basis(parameter, label, allow_value=True)
    return number, extraction_id, assumption_id


def _basis(value: Any, label: str, *, allow_value: bool = False) -> tuple[str | None, str | None]:
    basis = _object(value, label)
    allowed = {"source_extraction_id", "source_pointer", "assumption_id"}
    if allow_value:
        allowed.add("value")
    unknown = set(basis) - allowed
    if unknown:
        raise RelativeEffectError(
            f"{label} contains unsupported fields: {', '.join(sorted(unknown))}"
        )
    source_id = basis.get("source_extraction_id")
    assumption_id = basis.get("assumption_id")
    has_source = isinstance(source_id, str) and bool(source_id.strip())
    has_assumption = isinstance(assumption_id, str) and bool(assumption_id.strip())
    if has_source == has_assumption:
        raise RelativeEffectError(
            f"{label} must declare exactly one source_extraction_id or assumption_id"
        )
    if has_source:
        pointer = basis.get("source_pointer", "")
        if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
            raise RelativeEffectError(
                f"{label}.source_pointer must be empty or a JSON pointer"
            )
    elif "source_pointer" in basis:
        raise RelativeEffectError(
            f"{label}.source_pointer requires source_extraction_id"
        )
    return source_id if has_source else None, assumption_id if has_assumption else None


def _record_basis(
    extraction_id: str | None,
    assumption_id: str | None,
    used_extractions: set[str],
    used_assumptions: set[str],
) -> None:
    if extraction_id is not None:
        used_extractions.add(extraction_id)
    if assumption_id is not None:
        used_assumptions.add(assumption_id)


def _transition_schedule_path(path: str, plan: dict[str, Any]) -> bool:
    parts = path.split(".")
    order = plan.get("strategy_order")
    strategies = plan.get("strategies")
    return (
        len(parts) == 3
        and parts[0] == "strategies"
        and STRATEGY_ID_PATTERN.fullmatch(parts[1]) is not None
        and parts[2] == "transition_schedule"
        and isinstance(order, (list, tuple))
        and all(isinstance(item, str) for item in order)
        and isinstance(strategies, dict)
        and set(strategies) == set(order)
        and parts[1] in order
    )


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
            raise RelativeEffectError(f"mapping path {path!r} does not exist")
        current = current[token]
    if not isinstance(current, dict) or tokens[-1] not in current:
        raise RelativeEffectError(f"mapping path {path!r} does not exist")
    current[tokens[-1]] = value


def _identifier_set(value: Any, label: str) -> set[str]:
    if not isinstance(value, list):
        raise RelativeEffectError(f"{label} must be an array")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise RelativeEffectError(f"{label} must contain non-empty strings")
        result.append(item)
    if len(set(result)) != len(result):
        raise RelativeEffectError(f"{label} must not contain duplicates")
    return set(result)


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        missing = sorted(expected - set(value))
        extra = sorted(set(value) - expected)
        details = []
        if missing:
            details.append(f"missing {', '.join(missing)}")
        if extra:
            details.append(f"unsupported {', '.join(extra)}")
        raise RelativeEffectError(f"{label} fields are invalid: {'; '.join(details)}")


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RelativeEffectError(f"{label} must be an object")
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise RelativeEffectError(f"{label} must be an integer")
    return value


def _number(value: Any, label: str) -> float:
    if not _is_number(value):
        raise RelativeEffectError(f"{label} must be a finite number")
    return float(value)


def _is_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and isfinite(float(value))
    )


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
            and set(left) == set(right)
            and all(_json_equivalent(left[key], right[key]) for key in left)
        )
    return left == right
