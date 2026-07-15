"""Deterministic, evidence-linked event QALY losses.

The contract keeps event impacts separate from health-state utilities. It
reproduces per-cycle QALY losses from an absolute utility decrement, duration,
and either a one-time probability, recurrent expected count, or continuous
exposure fraction. It never selects events, incidence, duration, utility
decrements, or an overlap policy.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from math import isclose, isfinite
import re
from typing import Any

from .model import ModelValidationError
from .utility_inputs import validate_utility_inputs


SCHEMA_VERSION = "0.1.0"
ARTIFACT_PATH = "heor/event-disutilities.json"
ANALYSIS_PATH = "heor/analysis-plan.json"
UTILITY_INPUTS_PATH = "heor/utility-inputs.json"
ANALYSIS_SCHEMA_VERSION = "0.15.0"
TOLERANCE = 1e-9
SAFE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
EVENT_CATEGORIES = {
    "adverse_event",
    "treatment_process",
    "procedure",
    "diagnostic_consequence",
    "other",
}
MODES = {"one_time", "recurrent", "continuous_exposure"}
MEASURES = {
    "one_time": "probability",
    "recurrent": "expected_events",
    "continuous_exposure": "exposure_fraction",
}
UNCERTAINTY_STATUSES = {"fixed", "range_available", "distribution_available"}


@dataclass(frozen=True)
class EventDisutilitySummary:
    event_disutility_id: str
    item_count: int
    one_time_item_count: int
    recurrent_item_count: int
    continuous_exposure_item_count: int
    cycle_state_qaly_losses: dict[str, tuple[tuple[float, ...], ...]]


def validate_event_disutilities(
    analysis_plan: dict[str, Any],
    analysis_raw: bytes,
    utility_inputs: dict[str, Any],
    utility_inputs_raw: bytes,
    artifact: dict[str, Any],
    artifact_raw: bytes,
) -> EventDisutilitySummary:
    """Validate exact source bytes and reproduce all event QALY losses."""

    del artifact_raw  # The consuming PSM plan binds these exact bytes.
    plan = _object(analysis_plan, "analysis plan")
    if plan.get("schema_version") != ANALYSIS_SCHEMA_VERSION:
        raise ModelValidationError(
            f"event disutilities require analysis schema {ANALYSIS_SCHEMA_VERSION}"
        )
    utility_summary = validate_utility_inputs(
        plan, analysis_raw, utility_inputs, utility_inputs_raw
    )
    value = _object(artifact, "event-disutility artifact")
    _exact_keys(
        value,
        {
            "schema_version",
            "event_disutility_id",
            "analysis_id",
            "status",
            "base_analysis",
            "base_utility_inputs",
            "day_count_convention",
            "combination_rule",
            "item_order",
            "items",
            "cycle_state_qaly_losses",
            "limitations",
        },
        "event-disutility artifact",
    )
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ModelValidationError(
            f"event-disutility schema_version must be {SCHEMA_VERSION}"
        )
    event_disutility_id = _safe_id(
        value.get("event_disutility_id"), "event_disutility_id"
    )
    if value.get("analysis_id") != plan.get("analysis_id"):
        raise ModelValidationError(
            "event-disutility analysis_id does not match analysis plan"
        )
    if value.get("status") != "ready_for_human_review":
        raise ModelValidationError(
            "event-disutility status must be ready_for_human_review"
        )
    _binding(value.get("base_analysis"), ANALYSIS_PATH, analysis_raw, "base_analysis")
    _binding(
        value.get("base_utility_inputs"),
        UTILITY_INPUTS_PATH,
        utility_inputs_raw,
        "base_utility_inputs",
    )

    valid_basis_ids = _basis_ids(plan)
    day_count = _object(value.get("day_count_convention"), "day_count_convention")
    _exact_keys(
        day_count,
        {"days_per_year", "rationale", "basis_ids"},
        "day_count_convention",
    )
    days_per_year = _finite(day_count.get("days_per_year"), "days_per_year")
    if days_per_year not in {365.0, 365.25}:
        raise ModelValidationError("days_per_year must be exactly 365 or 365.25")
    _nonempty(day_count.get("rationale"), "day_count_convention.rationale")
    _linked_ids(
        day_count.get("basis_ids"), valid_basis_ids, "day_count_convention.basis_ids"
    )
    combination = _object(value.get("combination_rule"), "combination_rule")
    _exact_keys(
        combination,
        {"method", "rationale", "basis_ids"},
        "combination_rule",
    )
    if combination.get("method") != "additive_expected_qaly_loss":
        raise ModelValidationError(
            "combination_rule.method must be additive_expected_qaly_loss"
        )
    _nonempty(combination.get("rationale"), "combination_rule.rationale")
    _linked_ids(
        combination.get("basis_ids"), valid_basis_ids, "combination_rule.basis_ids"
    )

    cycles = _strict_int(plan.get("cycles"), "cycles")
    cycle_length = _positive(plan.get("cycle_length_years"), "cycle_length_years")
    cycle_days = cycle_length * days_per_year
    strategy_order = _safe_id_list(plan.get("strategy_order"), "strategy_order")
    states = _nonempty_string_list(plan.get("states"), "states")
    if "dead" not in states:
        raise ModelValidationError("event disutilities require an explicit dead state")

    utility_items = _object(utility_inputs.get("items"), "utility-input items")
    utility_by_pair: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
    for utility_item_id, raw_item in utility_items.items():
        utility_item = _object(raw_item, f"utility-input items.{utility_item_id}")
        pair = (utility_item.get("strategy_id"), utility_item.get("state_id"))
        utility_by_pair[pair] = (utility_item_id, utility_item)

    item_order = _safe_id_list(value.get("item_order"), "item_order")
    items = _object(value.get("items"), "items")
    if set(items) != set(item_order):
        raise ModelValidationError("items must contain exactly the item_order ids")
    computed = {
        strategy_id: [[0.0 for _ in states] for _ in range(cycles)]
        for strategy_id in strategy_order
    }
    observed_events: set[tuple[str, str]] = set()
    mode_counts = {mode: 0 for mode in MODES}
    for item_id in item_order:
        item = _object(items.get(item_id), f"items.{item_id}")
        _exact_keys(
            item,
            {
                "item_id",
                "event_id",
                "strategy_id",
                "label",
                "event",
                "application",
                "health_impact",
                "occurrence",
                "utility_overlap",
                "cycle_qaly_loss_per_eligible_person",
                "uncertainty",
            },
            f"items.{item_id}",
        )
        if item.get("item_id") != item_id:
            raise ModelValidationError(f"items.{item_id}.item_id must match its key")
        event_id = _safe_id(item.get("event_id"), f"items.{item_id}.event_id")
        strategy_id = item.get("strategy_id")
        if strategy_id not in strategy_order:
            raise ModelValidationError(f"items.{item_id}.strategy_id is not admitted")
        if (strategy_id, event_id) in observed_events:
            raise ModelValidationError("event items must not duplicate a strategy/event pair")
        observed_events.add((strategy_id, event_id))
        _nonempty(item.get("label"), f"items.{item_id}.label")

        event = _object(item.get("event"), f"items.{item_id}.event")
        _exact_keys(
            event,
            {"category", "terminology_system", "terminology_code", "severity"},
            f"items.{item_id}.event",
        )
        if event.get("category") not in EVENT_CATEGORIES:
            raise ModelValidationError(f"items.{item_id}.event.category is unsupported")
        _nonempty(event.get("terminology_system"), f"items.{item_id}.event.terminology_system")
        terminology_code = event.get("terminology_code")
        if terminology_code is not None:
            _nonempty(terminology_code, f"items.{item_id}.event.terminology_code")
        severity = _object(event.get("severity"), f"items.{item_id}.event.severity")
        _exact_keys(
            severity,
            {"system", "grade", "rationale"},
            f"items.{item_id}.event.severity",
        )
        for field in ("system", "grade", "rationale"):
            _nonempty(severity.get(field), f"items.{item_id}.event.severity.{field}")

        application = _object(item.get("application"), f"items.{item_id}.application")
        _exact_keys(
            application,
            {
                "mode",
                "eligible_states",
                "timing",
                "cost_handling",
                "rationale",
                "basis_ids",
            },
            f"items.{item_id}.application",
        )
        mode = application.get("mode")
        if mode not in MODES:
            raise ModelValidationError(f"items.{item_id}.application.mode is unsupported")
        mode_counts[mode] += 1
        eligible_states = _nonempty_string_list(
            application.get("eligible_states"),
            f"items.{item_id}.application.eligible_states",
        )
        if len(eligible_states) != len(set(eligible_states)) or any(
            state not in states or state == "dead" for state in eligible_states
        ):
            raise ModelValidationError(
                f"items.{item_id}.application.eligible_states must be unique non-dead analysis states"
            )
        if application.get("timing") != "cycle_average":
            raise ModelValidationError(f"items.{item_id}.application.timing must be cycle_average")
        if application.get("cost_handling") != "not_in_this_artifact":
            raise ModelValidationError(
                f"items.{item_id}.application.cost_handling must be not_in_this_artifact"
            )
        _nonempty(application.get("rationale"), f"items.{item_id}.application.rationale")
        _linked_ids(
            application.get("basis_ids"),
            valid_basis_ids,
            f"items.{item_id}.application.basis_ids",
        )

        impact = _object(item.get("health_impact"), f"items.{item_id}.health_impact")
        _exact_keys(
            impact,
            {
                "utility_decrement",
                "decrement_scale",
                "duration_days",
                "qaly_loss_per_occurrence",
                "instrument_or_method",
                "respondent",
                "source_population",
                "basis_ids",
            },
            f"items.{item_id}.health_impact",
        )
        decrement = _positive(
            impact.get("utility_decrement"),
            f"items.{item_id}.health_impact.utility_decrement",
        )
        if decrement > 2.0:
            raise ModelValidationError(
                f"items.{item_id}.health_impact.utility_decrement must not exceed 2"
            )
        if impact.get("decrement_scale") != "absolute_utility_decrement":
            raise ModelValidationError(
                f"items.{item_id}.health_impact.decrement_scale must be absolute_utility_decrement"
            )
        for field in ("instrument_or_method", "respondent", "source_population"):
            _nonempty(impact.get(field), f"items.{item_id}.health_impact.{field}")
        _linked_ids(
            impact.get("basis_ids"),
            valid_basis_ids,
            f"items.{item_id}.health_impact.basis_ids",
        )

        occurrence = _object(item.get("occurrence"), f"items.{item_id}.occurrence")
        _exact_keys(
            occurrence,
            {"measure", "schedule", "source_population", "observation_window", "basis_ids"},
            f"items.{item_id}.occurrence",
        )
        if occurrence.get("measure") != MEASURES[mode]:
            raise ModelValidationError(
                f"items.{item_id}.occurrence.measure does not match application mode"
            )
        schedule = _number_list(
            occurrence.get("schedule"), f"items.{item_id}.occurrence.schedule"
        )
        if len(schedule) != cycles or any(number < 0.0 for number in schedule):
            raise ModelValidationError(
                f"items.{item_id}.occurrence.schedule must contain one non-negative value per cycle"
            )
        if not any(number > 0.0 for number in schedule):
            raise ModelValidationError(f"items.{item_id}.occurrence.schedule must contain an impact")
        if mode == "one_time" and (
            sum(number > 0.0 for number in schedule) != 1
            or any(number > 1.0 for number in schedule)
        ):
            raise ModelValidationError(
                f"items.{item_id} one-time probability must be from 0 to 1 in exactly one cycle"
            )
        if mode == "continuous_exposure" and any(number > 1.0 for number in schedule):
            raise ModelValidationError(
                f"items.{item_id} exposure fractions must be from 0 to 1"
            )
        for field in ("source_population", "observation_window"):
            _nonempty(occurrence.get(field), f"items.{item_id}.occurrence.{field}")
        _linked_ids(
            occurrence.get("basis_ids"),
            valid_basis_ids,
            f"items.{item_id}.occurrence.basis_ids",
        )

        duration = impact.get("duration_days")
        qaly_per_occurrence = impact.get("qaly_loss_per_occurrence")
        if mode == "continuous_exposure":
            if duration is not None or qaly_per_occurrence is not None:
                raise ModelValidationError(
                    f"items.{item_id} continuous exposure must not claim per-occurrence duration or loss"
                )
            expected_cycle_losses = [
                fraction * decrement * cycle_length for fraction in schedule
            ]
        else:
            duration_days = _positive(
                duration, f"items.{item_id}.health_impact.duration_days"
            )
            if duration_days > cycle_days + TOLERANCE:
                raise ModelValidationError(
                    f"items.{item_id} duration exceeds one model cycle; use explicit health or tunnel states"
                )
            declared_qaly = _positive(
                qaly_per_occurrence,
                f"items.{item_id}.health_impact.qaly_loss_per_occurrence",
            )
            expected_qaly = decrement * duration_days / days_per_year
            _reproduces(
                expected_qaly,
                declared_qaly,
                f"items.{item_id}.health_impact.qaly_loss_per_occurrence",
            )
            expected_cycle_losses = [number * declared_qaly for number in schedule]

        declared_item_losses = _number_list(
            item.get("cycle_qaly_loss_per_eligible_person"),
            f"items.{item_id}.cycle_qaly_loss_per_eligible_person",
        )
        if len(declared_item_losses) != cycles or any(
            number < 0.0 for number in declared_item_losses
        ):
            raise ModelValidationError(
                f"items.{item_id}.cycle_qaly_loss_per_eligible_person must match model cycles"
            )
        for cycle, (expected, actual) in enumerate(
            zip(expected_cycle_losses, declared_item_losses)
        ):
            _reproduces(
                expected,
                actual,
                f"items.{item_id}.cycle_qaly_loss_per_eligible_person[{cycle}]",
            )

        overlap = _object(item.get("utility_overlap"), f"items.{item_id}.utility_overlap")
        _exact_keys(
            overlap,
            {"status", "reviewed_utility_item_ids", "rationale", "basis_ids"},
            f"items.{item_id}.utility_overlap",
        )
        if overlap.get("status") != "excluded_from_health_state_utility":
            raise ModelValidationError(
                f"items.{item_id}.utility_overlap.status must be excluded_from_health_state_utility"
            )
        reviewed_ids = _nonempty_string_list(
            overlap.get("reviewed_utility_item_ids"),
            f"items.{item_id}.utility_overlap.reviewed_utility_item_ids",
        )
        expected_utility_ids: set[str] = set()
        for state in eligible_states:
            utility_pair = utility_by_pair.get((strategy_id, state))
            if utility_pair is None:
                raise ModelValidationError(
                    f"items.{item_id} has no utility item for eligible state {state}"
                )
            utility_item_id, utility_item = utility_pair
            expected_utility_ids.add(utility_item_id)
            utility_application = _object(
                utility_item.get("application"), f"utility item {utility_item_id}.application"
            )
            captured = _nonempty_string_list(
                utility_application.get("captured_effects"),
                f"utility item {utility_item_id}.captured_effects",
            )
            excluded = _string_list(
                utility_application.get("excluded_effects"),
                f"utility item {utility_item_id}.excluded_effects",
            )
            if event_id in captured or event_id not in excluded:
                raise ModelValidationError(
                    f"utility item {utility_item_id} must explicitly exclude event {event_id}"
                )
        if set(reviewed_ids) != expected_utility_ids or len(reviewed_ids) != len(
            expected_utility_ids
        ):
            raise ModelValidationError(
                f"items.{item_id}.utility_overlap must name exactly the eligible utility items"
            )
        _nonempty(overlap.get("rationale"), f"items.{item_id}.utility_overlap.rationale")
        _linked_ids(
            overlap.get("basis_ids"),
            valid_basis_ids,
            f"items.{item_id}.utility_overlap.basis_ids",
        )
        _validate_uncertainty(item.get("uncertainty"), valid_basis_ids, item_id)
        for state in eligible_states:
            state_index = states.index(state)
            for cycle, cycle_loss in enumerate(declared_item_losses):
                computed[strategy_id][cycle][state_index] += cycle_loss

    declared = _object(value.get("cycle_state_qaly_losses"), "cycle_state_qaly_losses")
    if set(declared) != set(strategy_order):
        raise ModelValidationError(
            "cycle_state_qaly_losses must contain exactly strategy_order ids"
        )
    normalized: dict[str, tuple[tuple[float, ...], ...]] = {}
    for strategy_id in strategy_order:
        rows = declared.get(strategy_id)
        if not isinstance(rows, list) or len(rows) != cycles:
            raise ModelValidationError(
                f"cycle_state_qaly_losses.{strategy_id} must contain one row per cycle"
            )
        normalized_rows: list[tuple[float, ...]] = []
        for cycle, raw_row in enumerate(rows):
            row = _number_list(
                raw_row, f"cycle_state_qaly_losses.{strategy_id}[{cycle}]"
            )
            if len(row) != len(states) or any(number < 0.0 for number in row):
                raise ModelValidationError(
                    f"cycle_state_qaly_losses.{strategy_id}[{cycle}] must match state order"
                )
            for state_index, (expected, actual) in enumerate(
                zip(computed[strategy_id][cycle], row)
            ):
                _reproduces(
                    expected,
                    actual,
                    f"cycle_state_qaly_losses.{strategy_id}[{cycle}][{state_index}]",
                )
                base_utility = utility_summary.cycle_state_utilities[strategy_id][cycle][
                    state_index
                ]
                implied_utility = base_utility - actual / cycle_length
                if implied_utility < -1.0 - TOLERANCE:
                    raise ModelValidationError(
                        f"event losses imply utility below -1 for {strategy_id} cycle {cycle} state {states[state_index]}"
                    )
                if states[state_index] == "dead" and actual != 0.0:
                    raise ModelValidationError("dead-state event QALY loss must be zero")
            normalized_rows.append(tuple(row))
        normalized[strategy_id] = tuple(normalized_rows)

    if not _nonempty_string_list(value.get("limitations"), "limitations"):
        raise ModelValidationError("limitations must not be empty")
    return EventDisutilitySummary(
        event_disutility_id,
        len(item_order),
        mode_counts["one_time"],
        mode_counts["recurrent"],
        mode_counts["continuous_exposure"],
        normalized,
    )


def _validate_uncertainty(value: Any, valid_ids: set[str], item_id: str) -> None:
    label = f"items.{item_id}.uncertainty"
    uncertainty = _object(value, label)
    _exact_keys(uncertainty, {"status", "basis_ids", "limitations"}, label)
    if uncertainty.get("status") not in UNCERTAINTY_STATUSES:
        raise ModelValidationError(f"{label}.status is unsupported")
    _linked_ids(uncertainty.get("basis_ids"), valid_ids, f"{label}.basis_ids")
    _nonempty_string_list(uncertainty.get("limitations"), f"{label}.limitations")


def _basis_ids(plan: dict[str, Any]) -> set[str]:
    identifiers: set[str] = set()
    for source in plan.get("evidence_sources", []):
        if isinstance(source, dict) and isinstance(source.get("id"), str):
            identifiers.add(source["id"])
    for assumption in plan.get("assumptions", []):
        if (
            isinstance(assumption, dict)
            and assumption.get("status") == "proposed"
            and isinstance(assumption.get("id"), str)
        ):
            identifiers.add(assumption["id"])
    for mapping in plan.get("input_provenance", []):
        if isinstance(mapping, dict):
            for field in ("source_ids", "extraction_ids", "assumption_ids"):
                values = mapping.get(field)
                if isinstance(values, list):
                    identifiers.update(
                        item for item in values if isinstance(item, str) and item
                    )
    return identifiers


def _binding(value: Any, path: str, raw: bytes, name: str) -> None:
    binding = _object(value, name)
    _exact_keys(binding, {"path", "content_sha256"}, name)
    if binding.get("path") != path:
        raise ModelValidationError(f"{name}.path must be {path}")
    if binding.get("content_sha256") != hashlib.sha256(raw).hexdigest():
        raise ModelValidationError(f"{name}.content_sha256 does not match current bytes")


def _linked_ids(value: Any, valid: set[str], name: str) -> tuple[str, ...]:
    values = _nonempty_string_list(value, name)
    if len(values) != len(set(values)) or any(item not in valid for item in values):
        raise ModelValidationError(
            f"{name} must contain unique analysis evidence or proposed-assumption ids"
        )
    return tuple(values)


def _safe_id_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ModelValidationError(f"{name} must be a non-empty array")
    result = [_safe_id(item, f"{name}[{index}]") for index, item in enumerate(value)]
    if len(result) != len(set(result)):
        raise ModelValidationError(f"{name} must not contain duplicates")
    return result


def _nonempty_string_list(value: Any, name: str) -> list[str]:
    values = _string_list(value, name)
    if not values:
        raise ModelValidationError(f"{name} must not be empty")
    return values


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ModelValidationError(f"{name} must be an array of non-empty strings")
    return list(value)


def _number_list(value: Any, name: str) -> list[float]:
    if not isinstance(value, list):
        raise ModelValidationError(f"{name} must be an array")
    return [_finite(item, f"{name}[{index}]") for index, item in enumerate(value)]


def _strict_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ModelValidationError(f"{name} must be an integer")
    return value


def _positive(value: Any, name: str) -> float:
    number = _finite(value, name)
    if number <= 0.0:
        raise ModelValidationError(f"{name} must be positive")
    return number


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
        raise ModelValidationError(f"{name} must be finite")
    return float(value)


def _reproduces(expected: float, actual: float, name: str) -> None:
    if not isclose(expected, actual, rel_tol=TOLERANCE, abs_tol=TOLERANCE):
        raise ModelValidationError(f"{name} does not reproduce the declared QALY loss")


def _safe_id(value: Any, name: str) -> str:
    if not isinstance(value, str) or SAFE_ID.fullmatch(value) is None:
        raise ModelValidationError(f"{name} must be a safe lowercase id")
    return value


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelValidationError(f"{name} must not be empty")
    return value


def _object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ModelValidationError(f"{name} must be an object")
    return value


def _exact_keys(value: dict[str, Any], expected: set[str], name: str) -> None:
    if set(value) != expected:
        raise ModelValidationError(f"{name} fields must be exactly {sorted(expected)}")
