#!/usr/bin/env python3
"""Validate AI4HEOR event disutilities using only the Python standard library."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from math import isclose, isfinite
from pathlib import Path
import re
import sys
from typing import Any


sys.dont_write_bytecode = True
SCHEMA_VERSION = "0.1.0"
ANALYSIS_SCHEMA_VERSION = "0.15.0"
ANALYSIS_PATH = "heor/analysis-plan.json"
UTILITY_PATH = "heor/utility-inputs.json"
TOLERANCE = 1e-9
SAFE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
EVENT_CATEGORIES = {
    "adverse_event", "treatment_process", "procedure",
    "diagnostic_consequence", "other",
}
MODES = {"one_time", "recurrent", "continuous_exposure"}
MEASURES = {
    "one_time": "probability",
    "recurrent": "expected_events",
    "continuous_exposure": "exposure_fraction",
}
UNCERTAINTY_STATUSES = {"fixed", "range_available", "distribution_available"}
TOP_KEYS = {
    "schema_version", "event_disutility_id", "analysis_id", "status",
    "base_analysis", "base_utility_inputs", "day_count_convention",
    "combination_rule", "item_order", "items", "cycle_state_qaly_losses",
    "limitations",
}
ITEM_KEYS = {
    "item_id", "event_id", "strategy_id", "label", "event", "application",
    "health_impact", "occurrence", "utility_overlap",
    "cycle_qaly_loss_per_eligible_person", "uncertainty",
}


class Invalid(ValueError):
    pass


def obj(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise Invalid(f"{name} must be an object")
    return value


def exact(value: dict[str, Any], keys: set[str], name: str) -> None:
    if set(value) != keys:
        raise Invalid(f"{name} fields must be exactly {sorted(keys)}")


def text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Invalid(f"{name} must not be empty")
    return value


def safe(value: Any, name: str) -> str:
    if not isinstance(value, str) or SAFE_ID.fullmatch(value) is None:
        raise Invalid(f"{name} must be a safe lowercase id")
    return value


def strings(value: Any, name: str, *, empty: bool = False) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise Invalid(f"{name} must be an array of non-empty strings")
    if not empty and not value:
        raise Invalid(f"{name} must not be empty")
    return list(value)


def unique_strings(value: Any, name: str, *, safe_ids: bool = False) -> list[str]:
    result = strings(value, name)
    if len(result) != len(set(result)):
        raise Invalid(f"{name} must not contain duplicates")
    if safe_ids:
        for index, item in enumerate(result):
            safe(item, f"{name}[{index}]")
    return result


def number(value: Any, name: str) -> float:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(float(value))
    ):
        raise Invalid(f"{name} must be finite")
    return float(value)


def positive(value: Any, name: str) -> float:
    result = number(value, name)
    if result <= 0:
        raise Invalid(f"{name} must be positive")
    return result


def numbers(value: Any, name: str) -> list[float]:
    if not isinstance(value, list):
        raise Invalid(f"{name} must be an array")
    return [number(item, f"{name}[{index}]") for index, item in enumerate(value)]


def linked(value: Any, valid: set[str], name: str) -> None:
    result = unique_strings(value, name)
    if any(item not in valid for item in result):
        raise Invalid(
            f"{name} must contain unique analysis evidence or proposed-assumption ids"
        )


def reproduces(expected: float, actual: float, name: str) -> None:
    if not isclose(expected, actual, rel_tol=TOLERANCE, abs_tol=TOLERANCE):
        raise Invalid(f"{name} does not reproduce the declared QALY loss")


def basis_ids(plan: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for source in plan.get("evidence_sources", []):
        if isinstance(source, dict) and isinstance(source.get("id"), str):
            result.add(source["id"])
    for assumption in plan.get("assumptions", []):
        if (
            isinstance(assumption, dict)
            and assumption.get("status") == "proposed"
            and isinstance(assumption.get("id"), str)
        ):
            result.add(assumption["id"])
    for mapping in plan.get("input_provenance", []):
        if isinstance(mapping, dict):
            for field in ("source_ids", "extraction_ids", "assumption_ids"):
                values = mapping.get(field)
                if isinstance(values, list):
                    result.update(
                        item for item in values if isinstance(item, str) and item
                    )
    return result


def bind(value: Any, path: str, raw: bytes, name: str) -> None:
    binding = obj(value, name)
    exact(binding, {"path", "content_sha256"}, name)
    if binding.get("path") != path:
        raise Invalid(f"{name}.path must be {path}")
    if binding.get("content_sha256") != hashlib.sha256(raw).hexdigest():
        raise Invalid(f"{name}.content_sha256 does not match current bytes")


def validate_utility(
    analysis: dict[str, Any], analysis_raw: bytes, utility: dict[str, Any]
) -> None:
    """Use the bundled strict utility validator before consuming its schedule."""

    validator_path = (
        Path(__file__).resolve().parents[2]
        / "heor-utility-inputs/scripts/validate_utility_inputs.py"
    )
    spec = importlib.util.spec_from_file_location(
        "ai4heor_event_utility_validator", validator_path
    )
    if spec is None or spec.loader is None:
        raise Invalid(f"cannot load utility validator at {validator_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    errors = module.validate(analysis, analysis_raw, utility)
    if errors:
        raise Invalid(f"utility inputs are invalid: {errors[0]}")


def validate(
    analysis: dict[str, Any],
    analysis_raw: bytes,
    utility: dict[str, Any],
    utility_raw: bytes,
    artifact: dict[str, Any],
) -> list[str]:
    try:
        plan = obj(analysis, "analysis plan")
        if plan.get("schema_version") != ANALYSIS_SCHEMA_VERSION:
            raise Invalid(
                f"event disutilities require analysis schema {ANALYSIS_SCHEMA_VERSION}"
            )
        validate_utility(plan, analysis_raw, utility)
        value = obj(artifact, "event-disutility artifact")
        exact(value, TOP_KEYS, "event-disutility artifact")
        if value.get("schema_version") != SCHEMA_VERSION:
            raise Invalid(f"event-disutility schema_version must be {SCHEMA_VERSION}")
        safe(value.get("event_disutility_id"), "event_disutility_id")
        if value.get("analysis_id") != plan.get("analysis_id"):
            raise Invalid("event-disutility analysis_id does not match analysis plan")
        if value.get("status") != "ready_for_human_review":
            raise Invalid("event-disutility status must be ready_for_human_review")
        bind(value.get("base_analysis"), ANALYSIS_PATH, analysis_raw, "base_analysis")
        bind(
            value.get("base_utility_inputs"),
            UTILITY_PATH,
            utility_raw,
            "base_utility_inputs",
        )

        valid_ids = basis_ids(plan)
        day_count = obj(value.get("day_count_convention"), "day_count_convention")
        exact(day_count, {"days_per_year", "rationale", "basis_ids"}, "day_count_convention")
        days_per_year = number(day_count.get("days_per_year"), "days_per_year")
        if days_per_year not in {365.0, 365.25}:
            raise Invalid("days_per_year must be exactly 365 or 365.25")
        text(day_count.get("rationale"), "day_count_convention.rationale")
        linked(day_count.get("basis_ids"), valid_ids, "day_count_convention.basis_ids")
        combination = obj(value.get("combination_rule"), "combination_rule")
        exact(combination, {"method", "rationale", "basis_ids"}, "combination_rule")
        if combination.get("method") != "additive_expected_qaly_loss":
            raise Invalid("combination_rule.method must be additive_expected_qaly_loss")
        text(combination.get("rationale"), "combination_rule.rationale")
        linked(combination.get("basis_ids"), valid_ids, "combination_rule.basis_ids")

        cycles = plan.get("cycles")
        if isinstance(cycles, bool) or not isinstance(cycles, int):
            raise Invalid("cycles must be an integer")
        cycle_length = positive(plan.get("cycle_length_years"), "cycle_length_years")
        cycle_days = cycle_length * days_per_year
        strategy_order = unique_strings(plan.get("strategy_order"), "strategy_order", safe_ids=True)
        states = strings(plan.get("states"), "states")
        if "dead" not in states:
            raise Invalid("event disutilities require an explicit dead state")

        utility_items = obj(utility.get("items"), "utility-input items")
        utility_pairs: dict[tuple[str, str], tuple[str, dict[str, Any]]] = {}
        for utility_item_id, raw_item in utility_items.items():
            utility_item = obj(raw_item, f"utility-input items.{utility_item_id}")
            utility_pairs[(utility_item.get("strategy_id"), utility_item.get("state_id"))] = (
                utility_item_id,
                utility_item,
            )
        utility_schedule = obj(utility.get("cycle_state_utilities"), "cycle_state_utilities")

        item_order = unique_strings(value.get("item_order"), "item_order", safe_ids=True)
        items = obj(value.get("items"), "items")
        if set(items) != set(item_order):
            raise Invalid("items must contain exactly the item_order ids")
        computed = {
            strategy: [[0.0 for _ in states] for _ in range(cycles)]
            for strategy in strategy_order
        }
        observed: set[tuple[str, str]] = set()
        for item_id in item_order:
            item = obj(items.get(item_id), f"items.{item_id}")
            exact(item, ITEM_KEYS, f"items.{item_id}")
            if item.get("item_id") != item_id:
                raise Invalid(f"items.{item_id}.item_id must match its key")
            event_id = safe(item.get("event_id"), f"items.{item_id}.event_id")
            strategy = item.get("strategy_id")
            if strategy not in strategy_order:
                raise Invalid(f"items.{item_id}.strategy_id is not admitted")
            if (strategy, event_id) in observed:
                raise Invalid("event items must not duplicate a strategy/event pair")
            observed.add((strategy, event_id))
            text(item.get("label"), f"items.{item_id}.label")

            event = obj(item.get("event"), f"items.{item_id}.event")
            exact(event, {"category", "terminology_system", "terminology_code", "severity"}, f"items.{item_id}.event")
            if event.get("category") not in EVENT_CATEGORIES:
                raise Invalid(f"items.{item_id}.event.category is unsupported")
            text(event.get("terminology_system"), f"items.{item_id}.event.terminology_system")
            if event.get("terminology_code") is not None:
                text(event.get("terminology_code"), f"items.{item_id}.event.terminology_code")
            severity = obj(event.get("severity"), f"items.{item_id}.event.severity")
            exact(severity, {"system", "grade", "rationale"}, f"items.{item_id}.event.severity")
            for field in ("system", "grade", "rationale"):
                text(severity.get(field), f"items.{item_id}.event.severity.{field}")

            application = obj(item.get("application"), f"items.{item_id}.application")
            exact(application, {"mode", "eligible_states", "timing", "cost_handling", "rationale", "basis_ids"}, f"items.{item_id}.application")
            mode = application.get("mode")
            if mode not in MODES:
                raise Invalid(f"items.{item_id}.application.mode is unsupported")
            eligible_states = strings(application.get("eligible_states"), f"items.{item_id}.application.eligible_states")
            if len(eligible_states) != len(set(eligible_states)) or any(
                state not in states or state == "dead" for state in eligible_states
            ):
                raise Invalid(f"items.{item_id}.application.eligible_states must be unique non-dead analysis states")
            if application.get("timing") != "cycle_average":
                raise Invalid(f"items.{item_id}.application.timing must be cycle_average")
            if application.get("cost_handling") != "not_in_this_artifact":
                raise Invalid(f"items.{item_id}.application.cost_handling must be not_in_this_artifact")
            text(application.get("rationale"), f"items.{item_id}.application.rationale")
            linked(application.get("basis_ids"), valid_ids, f"items.{item_id}.application.basis_ids")

            impact = obj(item.get("health_impact"), f"items.{item_id}.health_impact")
            exact(impact, {"utility_decrement", "decrement_scale", "duration_days", "qaly_loss_per_occurrence", "instrument_or_method", "respondent", "source_population", "basis_ids"}, f"items.{item_id}.health_impact")
            decrement = positive(impact.get("utility_decrement"), f"items.{item_id}.health_impact.utility_decrement")
            if decrement > 2:
                raise Invalid(f"items.{item_id}.health_impact.utility_decrement must not exceed 2")
            if impact.get("decrement_scale") != "absolute_utility_decrement":
                raise Invalid(f"items.{item_id}.health_impact.decrement_scale must be absolute_utility_decrement")
            for field in ("instrument_or_method", "respondent", "source_population"):
                text(impact.get(field), f"items.{item_id}.health_impact.{field}")
            linked(impact.get("basis_ids"), valid_ids, f"items.{item_id}.health_impact.basis_ids")

            occurrence = obj(item.get("occurrence"), f"items.{item_id}.occurrence")
            exact(occurrence, {"measure", "schedule", "source_population", "observation_window", "basis_ids"}, f"items.{item_id}.occurrence")
            if occurrence.get("measure") != MEASURES[mode]:
                raise Invalid(f"items.{item_id}.occurrence.measure does not match application mode")
            schedule = numbers(occurrence.get("schedule"), f"items.{item_id}.occurrence.schedule")
            if len(schedule) != cycles or any(item < 0 for item in schedule):
                raise Invalid(f"items.{item_id}.occurrence.schedule must contain one non-negative value per cycle")
            if not any(item > 0 for item in schedule):
                raise Invalid(f"items.{item_id}.occurrence.schedule must contain an impact")
            if mode == "one_time" and (
                sum(item > 0 for item in schedule) != 1 or any(item > 1 for item in schedule)
            ):
                raise Invalid(f"items.{item_id} one-time probability must be from 0 to 1 in exactly one cycle")
            if mode == "continuous_exposure" and any(item > 1 for item in schedule):
                raise Invalid(f"items.{item_id} exposure fractions must be from 0 to 1")
            for field in ("source_population", "observation_window"):
                text(occurrence.get(field), f"items.{item_id}.occurrence.{field}")
            linked(occurrence.get("basis_ids"), valid_ids, f"items.{item_id}.occurrence.basis_ids")

            duration = impact.get("duration_days")
            declared_per_occurrence = impact.get("qaly_loss_per_occurrence")
            if mode == "continuous_exposure":
                if duration is not None or declared_per_occurrence is not None:
                    raise Invalid(f"items.{item_id} continuous exposure must not claim per-occurrence duration or loss")
                expected_losses = [fraction * decrement * cycle_length for fraction in schedule]
            else:
                duration_days = positive(duration, f"items.{item_id}.health_impact.duration_days")
                if duration_days > cycle_days + TOLERANCE:
                    raise Invalid(f"items.{item_id} duration exceeds one model cycle; use explicit health or tunnel states")
                per_occurrence = positive(declared_per_occurrence, f"items.{item_id}.health_impact.qaly_loss_per_occurrence")
                reproduces(decrement * duration_days / days_per_year, per_occurrence, f"items.{item_id}.health_impact.qaly_loss_per_occurrence")
                expected_losses = [amount * per_occurrence for amount in schedule]
            declared_losses = numbers(item.get("cycle_qaly_loss_per_eligible_person"), f"items.{item_id}.cycle_qaly_loss_per_eligible_person")
            if len(declared_losses) != cycles or any(item < 0 for item in declared_losses):
                raise Invalid(f"items.{item_id}.cycle_qaly_loss_per_eligible_person must match model cycles")
            for cycle, (expected, actual) in enumerate(zip(expected_losses, declared_losses)):
                reproduces(expected, actual, f"items.{item_id}.cycle_qaly_loss_per_eligible_person[{cycle}]")

            overlap = obj(item.get("utility_overlap"), f"items.{item_id}.utility_overlap")
            exact(overlap, {"status", "reviewed_utility_item_ids", "rationale", "basis_ids"}, f"items.{item_id}.utility_overlap")
            if overlap.get("status") != "excluded_from_health_state_utility":
                raise Invalid(f"items.{item_id}.utility_overlap.status must be excluded_from_health_state_utility")
            reviewed = strings(overlap.get("reviewed_utility_item_ids"), f"items.{item_id}.utility_overlap.reviewed_utility_item_ids")
            expected_ids: set[str] = set()
            for state in eligible_states:
                pair = utility_pairs.get((strategy, state))
                if pair is None:
                    raise Invalid(f"items.{item_id} has no utility item for eligible state {state}")
                utility_item_id, utility_item = pair
                expected_ids.add(utility_item_id)
                utility_application = obj(utility_item.get("application"), f"utility item {utility_item_id}.application")
                captured = strings(utility_application.get("captured_effects"), f"utility item {utility_item_id}.captured_effects")
                excluded = strings(utility_application.get("excluded_effects"), f"utility item {utility_item_id}.excluded_effects", empty=True)
                if event_id in captured or event_id not in excluded:
                    raise Invalid(f"utility item {utility_item_id} must explicitly exclude event {event_id}")
            if set(reviewed) != expected_ids or len(reviewed) != len(expected_ids):
                raise Invalid(f"items.{item_id}.utility_overlap must name exactly the eligible utility items")
            text(overlap.get("rationale"), f"items.{item_id}.utility_overlap.rationale")
            linked(overlap.get("basis_ids"), valid_ids, f"items.{item_id}.utility_overlap.basis_ids")

            uncertainty = obj(item.get("uncertainty"), f"items.{item_id}.uncertainty")
            exact(uncertainty, {"status", "basis_ids", "limitations"}, f"items.{item_id}.uncertainty")
            if uncertainty.get("status") not in UNCERTAINTY_STATUSES:
                raise Invalid(f"items.{item_id}.uncertainty.status is unsupported")
            linked(uncertainty.get("basis_ids"), valid_ids, f"items.{item_id}.uncertainty.basis_ids")
            strings(uncertainty.get("limitations"), f"items.{item_id}.uncertainty.limitations")
            for state in eligible_states:
                state_index = states.index(state)
                for cycle, loss in enumerate(declared_losses):
                    computed[strategy][cycle][state_index] += loss

        declared = obj(value.get("cycle_state_qaly_losses"), "cycle_state_qaly_losses")
        if set(declared) != set(strategy_order):
            raise Invalid("cycle_state_qaly_losses must contain exactly strategy_order ids")
        for strategy in strategy_order:
            rows = declared.get(strategy)
            if not isinstance(rows, list) or len(rows) != cycles:
                raise Invalid(f"cycle_state_qaly_losses.{strategy} must contain one row per cycle")
            utility_rows = utility_schedule.get(strategy)
            for cycle, raw_row in enumerate(rows):
                row = numbers(raw_row, f"cycle_state_qaly_losses.{strategy}[{cycle}]")
                if len(row) != len(states) or any(item < 0 for item in row):
                    raise Invalid(f"cycle_state_qaly_losses.{strategy}[{cycle}] must match state order")
                for state_index, (expected, actual) in enumerate(zip(computed[strategy][cycle], row)):
                    reproduces(expected, actual, f"cycle_state_qaly_losses.{strategy}[{cycle}][{state_index}]")
                    base_utility = number(utility_rows[cycle][state_index], "utility schedule value")
                    if base_utility - actual / cycle_length < -1 - TOLERANCE:
                        raise Invalid(f"event losses imply utility below -1 for {strategy} cycle {cycle} state {states[state_index]}")
                    if states[state_index] == "dead" and actual != 0:
                        raise Invalid("dead-state event QALY loss must be zero")
        strings(value.get("limitations"), "limitations")
    except (Invalid, OSError, AttributeError) as error:
        return [str(error)]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis_plan", type=Path)
    parser.add_argument("utility_inputs", type=Path)
    parser.add_argument("event_disutilities", type=Path)
    args = parser.parse_args()
    try:
        analysis_raw = args.analysis_plan.read_bytes()
        utility_raw = args.utility_inputs.read_bytes()
        analysis = json.loads(analysis_raw)
        utility = json.loads(utility_raw)
        artifact = json.loads(args.event_disutilities.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        print(f"INVALID: {error}")
        return 1
    errors = validate(analysis, analysis_raw, utility, utility_raw, artifact)
    if errors:
        for error in errors:
            print(f"INVALID: {error}")
        return 1
    print("VALID: event disutilities 0.1.0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
