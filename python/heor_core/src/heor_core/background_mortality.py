"""Evidence-bound background plus excess mortality conversion.

The adapter converts one annual life-table probability per model cycle to an
annual background hazard, adds one constant excess mortality rate, and emits a
complete two-state transition schedule. It does not choose a life table,
establish population exchangeability, or infer whether mortality has already
been counted elsewhere in the model.
"""

from __future__ import annotations

from math import expm1, floor, isclose, isfinite, log1p
import re
from typing import Any


TRANSFORMATION_METHOD = "deterministic_transformation"
TRANSFORMATION_OPERATION = "background_plus_excess_mortality_to_transition_schedule"
ANALYSIS_SCHEMA_VERSION = "0.9.0"
CURRENT_ANALYSIS_SCHEMA_VERSION = "0.10.0"
LATEST_ANALYSIS_SCHEMA_VERSION = "0.11.0"
ANALYSIS_SCHEMA_VERSIONS = {
    ANALYSIS_SCHEMA_VERSION,
    CURRENT_ANALYSIS_SCHEMA_VERSION,
    LATEST_ANALYSIS_SCHEMA_VERSION,
}
STRATEGY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
TOLERANCE = 1e-12
MAX_CYCLES = 10_000


class BackgroundMortalityError(ValueError):
    """Raised when a background-mortality derivation violates the contract."""


def validate_background_mortality_mappings(
    plan: dict[str, Any],
    *,
    schema_version: str,
    state_count: int,
    cycles: int,
    cycle_length_years: float,
) -> None:
    """Recompute every declared background-plus-excess mortality schedule."""

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
        if schema_version not in ANALYSIS_SCHEMA_VERSIONS:
            raise BackgroundMortalityError(
                f"{label}: background-plus-excess mortality transformations require schema_version {ANALYSIS_SCHEMA_VERSION} through {LATEST_ANALYSIS_SCHEMA_VERSION}"
            )
        path = mapping.get("path")
        if not isinstance(path, str) or not _transition_schedule_path(path, plan):
            raise BackgroundMortalityError(
                f"{label}: background-plus-excess mortality is allowed only for a declared strategy transition_schedule"
            )
        target = _model_value(plan, path)
        if target is None:
            raise BackgroundMortalityError(f"{label}: transformation target is missing")
        if not _json_equivalent(derivation.get("model_value"), target):
            raise BackgroundMortalityError(
                f"{label}: derivation.model_value does not match the current transition schedule"
            )
        output, used_extractions, used_assumptions = derive_background_mortality_schedule(
            transformation,
            state_count=state_count,
            cycles=cycles,
            cycle_length_years=cycle_length_years,
        )
        if not _json_equivalent(output, target):
            raise BackgroundMortalityError(
                f"{label}: background-plus-excess mortality does not reproduce the current transition schedule"
            )
        extraction_ids = _identifier_set(
            mapping.get("extraction_ids"), f"{label}.extraction_ids"
        )
        assumption_ids = _identifier_set(
            mapping.get("assumption_ids"), f"{label}.assumption_ids"
        )
        if used_extractions != extraction_ids:
            raise BackgroundMortalityError(
                f"{label}: transformation must use every selected extraction exactly as declared"
            )
        if used_assumptions != assumption_ids:
            raise BackgroundMortalityError(
                f"{label}: transformation must use every proposed assumption exactly as declared"
            )


def apply_background_mortality_mappings(
    plan: dict[str, Any], mapping_indices: set[int]
) -> None:
    """Recompute selected schedules after an excess-rate replacement."""

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
        raise BackgroundMortalityError("analysis dimensions are invalid")
    for mapping_index in sorted(mapping_indices):
        if not 0 <= mapping_index < len(mappings):
            raise BackgroundMortalityError("background mortality mapping index is invalid")
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
            raise BackgroundMortalityError(
                "excess mortality target must bind a background-plus-excess mortality transformation"
            )
        output, _, _ = derive_background_mortality_schedule(
            transformation,
            state_count=len(states),
            cycles=cycles,
            cycle_length_years=float(cycle_length),
        )
        path = mapping.get("path")
        if not isinstance(path, str):
            raise BackgroundMortalityError("background mortality mapping path is invalid")
        _set_model_value(plan, path, output)
        derivation["model_value"] = output


def derive_background_mortality_schedule(
    value: Any,
    *,
    state_count: int,
    cycles: int,
    cycle_length_years: float,
) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    """Return the complete schedule and the exact evidence/assumption bases used."""

    transformation = _object(value, "transformation")
    _exact_keys(
        transformation,
        {
            "operation",
            "cycle_length_years",
            "from_state_index",
            "death_state_index",
            "life_table",
            "excess_mortality_rate_per_year",
            "review_bases",
        },
        "transformation",
    )
    if transformation.get("operation") != TRANSFORMATION_OPERATION:
        raise BackgroundMortalityError(
            f"transformation.operation must be {TRANSFORMATION_OPERATION}"
        )
    if state_count != 2:
        raise BackgroundMortalityError(
            "background-plus-excess mortality requires exactly two states"
        )
    if (
        isinstance(cycles, bool)
        or not isinstance(cycles, int)
        or not 1 <= cycles <= MAX_CYCLES
    ):
        raise BackgroundMortalityError(
            f"background-plus-excess mortality supports 1-{MAX_CYCLES} cycles"
        )
    declared_cycle = _number(
        transformation.get("cycle_length_years"),
        "transformation.cycle_length_years",
    )
    if declared_cycle <= 0 or not isclose(
        declared_cycle, cycle_length_years, rel_tol=0.0, abs_tol=TOLERANCE
    ):
        raise BackgroundMortalityError(
            "transformation.cycle_length_years must equal the analysis cycle length"
        )
    from_index = _integer(
        transformation.get("from_state_index"), "transformation.from_state_index"
    )
    death_index = _integer(
        transformation.get("death_state_index"), "transformation.death_state_index"
    )
    if {from_index, death_index} != {0, 1}:
        raise BackgroundMortalityError(
            "from_state_index and death_state_index must be the two distinct state indices"
        )

    life_table = _object(transformation.get("life_table"), "transformation.life_table")
    _exact_keys(
        life_table,
        {
            "jurisdiction",
            "table_year",
            "population",
            "sex",
            "start_age_years",
            "cycle_probabilities",
        },
        "transformation.life_table",
    )
    for field in ("jurisdiction", "population", "sex"):
        _nonempty(life_table.get(field), f"transformation.life_table.{field}")
    table_year = _integer(
        life_table.get("table_year"), "transformation.life_table.table_year"
    )
    if not 1900 <= table_year <= 2100:
        raise BackgroundMortalityError(
            "transformation.life_table.table_year must be from 1900 to 2100"
        )
    start_age = _number(
        life_table.get("start_age_years"),
        "transformation.life_table.start_age_years",
    )
    if start_age < 0:
        raise BackgroundMortalityError(
            "transformation.life_table.start_age_years must be non-negative"
        )
    probabilities = life_table.get("cycle_probabilities")
    if not isinstance(probabilities, list) or len(probabilities) != cycles:
        raise BackgroundMortalityError(
            "transformation.life_table.cycle_probabilities length must equal cycles"
        )

    used_extractions: set[str] = set()
    used_assumptions: set[str] = set()
    excess, extraction_id, assumption_id = _value_parameter(
        transformation.get("excess_mortality_rate_per_year"),
        "transformation.excess_mortality_rate_per_year",
        minimum=0.0,
        upper_exclusive=None,
    )
    _record_basis(extraction_id, assumption_id, used_extractions, used_assumptions)

    review_bases = _object(
        transformation.get("review_bases"), "transformation.review_bases"
    )
    _exact_keys(
        review_bases,
        {"population_exchangeability", "no_double_counting"},
        "transformation.review_bases",
    )
    for field in ("population_exchangeability", "no_double_counting"):
        extraction_id, assumption_id = _basis(
            review_bases.get(field), f"transformation.review_bases.{field}"
        )
        _record_basis(extraction_id, assumption_id, used_extractions, used_assumptions)

    schedule: list[dict[str, Any]] = []
    for index, raw_entry in enumerate(probabilities):
        cycle = index + 1
        label = f"transformation.life_table.cycle_probabilities[{index}]"
        entry = _object(raw_entry, label)
        _exact_keys(
            entry, {"cycle", "attained_age_years", "annual_probability"}, label
        )
        if _integer(entry.get("cycle"), f"{label}.cycle") != cycle:
            raise BackgroundMortalityError(
                f"{label}.cycle must equal its one-based model cycle"
            )
        try:
            attained_age_value = start_age + index * declared_cycle
        except (ArithmeticError, OverflowError) as error:
            raise BackgroundMortalityError(
                f"{label}: attained-age calculation overflowed"
            ) from error
        if not isfinite(attained_age_value):
            raise BackgroundMortalityError(
                f"{label}: attained-age calculation must remain finite"
            )
        expected_age = floor(attained_age_value)
        attained_age_number = _number(
            entry.get("attained_age_years"), f"{label}.attained_age_years"
        )
        if not attained_age_number.is_integer():
            raise BackgroundMortalityError(
                f"{label}.attained_age_years must be integer-valued"
            )
        attained_age = int(attained_age_number)
        if attained_age != expected_age:
            raise BackgroundMortalityError(
                f"{label}.attained_age_years must equal floor(start_age_years + (cycle - 1) * cycle_length_years)"
            )
        annual_probability, extraction_id, assumption_id = _value_parameter(
            entry.get("annual_probability"),
            f"{label}.annual_probability",
            minimum=0.0,
            upper_exclusive=1.0,
        )
        _record_basis(extraction_id, assumption_id, used_extractions, used_assumptions)
        try:
            background_hazard = -log1p(-annual_probability)
            all_cause_hazard = background_hazard + excess
            integrated_hazard = all_cause_hazard * declared_cycle
        except (ArithmeticError, OverflowError) as error:
            raise BackgroundMortalityError(
                f"{label}: mortality conversion overflowed"
            ) from error
        if (
            not isfinite(background_hazard)
            or not isfinite(all_cause_hazard)
            or not isfinite(integrated_hazard)
        ):
            raise BackgroundMortalityError(
                f"{label}: mortality conversion produced a non-finite hazard"
            )
        death_probability = -expm1(-integrated_hazard)
        if not isfinite(death_probability) or not 0.0 <= death_probability < 1.0:
            raise BackgroundMortalityError(
                f"{label}: mortality conversion produced a non-finite or invalid probability"
            )
        matrix = [[0.0, 0.0], [0.0, 0.0]]
        matrix[from_index][from_index] = 1.0 - death_probability
        matrix[from_index][death_index] = death_probability
        matrix[death_index][death_index] = 1.0
        schedule.append({"start_cycle": cycle, "matrix": matrix})
    return schedule, used_extractions, used_assumptions


def _value_parameter(
    value: Any,
    label: str,
    *,
    minimum: float,
    upper_exclusive: float | None,
) -> tuple[float, str | None, str | None]:
    parameter = _object(value, label)
    allowed = {"value", "source_extraction_id", "source_pointer", "assumption_id"}
    unknown = set(parameter) - allowed
    if unknown:
        raise BackgroundMortalityError(
            f"{label} contains unsupported fields: {', '.join(sorted(unknown))}"
        )
    number = _number(parameter.get("value"), f"{label}.value")
    if number < minimum or (upper_exclusive is not None and number >= upper_exclusive):
        bound = (
            f"from {minimum} (inclusive) to {upper_exclusive} (exclusive)"
            if upper_exclusive is not None
            else f"at least {minimum}"
        )
        raise BackgroundMortalityError(f"{label}.value must be {bound}")
    extraction_id, assumption_id = _basis(parameter, label, allow_value=True)
    return number, extraction_id, assumption_id


def _basis(
    value: Any, label: str, *, allow_value: bool = False
) -> tuple[str | None, str | None]:
    basis = _object(value, label)
    allowed = {"source_extraction_id", "source_pointer", "assumption_id"}
    if allow_value:
        allowed.add("value")
    unknown = set(basis) - allowed
    if unknown:
        raise BackgroundMortalityError(
            f"{label} contains unsupported fields: {', '.join(sorted(unknown))}"
        )
    source_id = basis.get("source_extraction_id")
    assumption_id = basis.get("assumption_id")
    has_source = isinstance(source_id, str) and bool(source_id.strip())
    has_assumption = isinstance(assumption_id, str) and bool(assumption_id.strip())
    if has_source == has_assumption:
        raise BackgroundMortalityError(
            f"{label} must declare exactly one source_extraction_id or assumption_id"
        )
    if has_source:
        pointer = basis.get("source_pointer", "")
        if not isinstance(pointer, str) or (pointer and not pointer.startswith("/")):
            raise BackgroundMortalityError(
                f"{label}.source_pointer must be empty or a JSON pointer"
            )
    elif "source_pointer" in basis:
        raise BackgroundMortalityError(
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
            raise BackgroundMortalityError(f"mapping path {path!r} does not exist")
        current = current[token]
    if not isinstance(current, dict) or tokens[-1] not in current:
        raise BackgroundMortalityError(f"mapping path {path!r} does not exist")
    current[tokens[-1]] = value


def _identifier_set(value: Any, label: str) -> set[str]:
    if not isinstance(value, list):
        raise BackgroundMortalityError(f"{label} must be an array")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise BackgroundMortalityError(f"{label} must contain non-empty strings")
        result.append(item)
    if len(set(result)) != len(result):
        raise BackgroundMortalityError(f"{label} must not contain duplicates")
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
        raise BackgroundMortalityError(f"{label} fields are invalid: {'; '.join(details)}")


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise BackgroundMortalityError(f"{label} must be an object")
    return value


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise BackgroundMortalityError(f"{label} must be a non-empty string")
    return value


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise BackgroundMortalityError(f"{label} must be an integer")
    return value


def _number(value: Any, label: str) -> float:
    if not _is_number(value):
        raise BackgroundMortalityError(f"{label} must be a finite number")
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
