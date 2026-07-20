#!/usr/bin/env python3
"""Validate an AI4HEOR utility-input artifact without third-party packages."""

from __future__ import annotations

import argparse
import hashlib
import json
from math import isclose, isfinite
from pathlib import Path
import re
from typing import Any


SAFE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
ANALYSIS_PATH = "heor/analysis-plan.json"
TOP_KEYS = {
    "schema_version", "utility_input_id", "analysis_id", "status",
    "base_analysis", "target_context", "cycle_value_timing", "item_order",
    "items", "cycle_state_utilities", "limitations",
}
ITEM_KEYS = {
    "item_id", "strategy_id", "state_id", "description", "application",
    "measurement", "valuation", "mapping", "source_utility", "adjustments",
    "cycle_values", "uncertainty",
}
SOURCE_DESIGNS = {
    "randomized_trial", "observational_study", "systematic_review",
    "published_model", "elicitation_study", "anchor", "other",
}
INSTRUMENT_CLASSES = {
    "generic_preference_based", "condition_specific_preference_based",
    "direct_valuation", "mapped_non_preference_measure", "qaly_anchor", "other",
}
RESPONDENTS = {"patient", "proxy", "carer", "general_public", "mixed", "not_applicable"}
VALUE_ORIGINS = {"value_set", "direct_valuation", "mapped", "anchor"}
VALUATION_METHODS = {
    "time_trade_off", "standard_gamble", "discrete_choice_experiment", "hybrid",
    "algorithmic_mapping", "anchor", "other",
}
LICENSES = {"public", "registered_noncommercial", "licensed_local", "link_only", "not_applicable"}
ADJUSTMENTS = {"age_adjustment", "comorbidity_adjustment", "population_alignment"}


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
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise Invalid(f"{name} must be an array of non-empty strings")
    if not empty and not value:
        raise Invalid(f"{name} must not be empty")
    if len(value) != len(set(value)):
        raise Invalid(f"{name} must not contain duplicates")
    return value


def number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
        raise Invalid(f"{name} must be finite")
    return float(value)


def utility(value: Any, name: str) -> float:
    result = number(value, name)
    if not -1 <= result <= 1:
        raise Invalid(f"{name} must be from -1 to 1")
    return result


def linked(value: Any, valid: set[str], name: str) -> None:
    values = strings(value, name)
    if any(item not in valid for item in values):
        raise Invalid(f"{name} must contain analysis evidence or proposed-assumption ids")


def basis_ids(plan: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for source in plan.get("evidence_sources", []):
        if isinstance(source, dict) and isinstance(source.get("id"), str):
            result.add(source["id"])
    for assumption in plan.get("assumptions", []):
        if isinstance(assumption, dict) and assumption.get("status") == "proposed" and isinstance(assumption.get("id"), str):
            result.add(assumption["id"])
    for mapping in plan.get("input_provenance", []):
        if isinstance(mapping, dict):
            for field in ("source_ids", "extraction_ids", "assumption_ids"):
                if isinstance(mapping.get(field), list):
                    result.update(item for item in mapping[field] if isinstance(item, str) and item)
    return result


def validate(analysis: dict[str, Any], analysis_raw: bytes, artifact: dict[str, Any]) -> list[str]:
    try:
        plan = obj(analysis, "analysis plan")
        if plan.get("schema_version") not in {"0.14.0", "0.15.0"}:
            raise Invalid("utility inputs require analysis schema 0.14.0 or 0.15.0")
        value = obj(artifact, "utility-input artifact")
        exact(value, TOP_KEYS, "utility-input artifact")
        if value.get("schema_version") != "0.1.0":
            raise Invalid("utility-input schema_version must be 0.1.0")
        safe(value.get("utility_input_id"), "utility_input_id")
        if value.get("analysis_id") != plan.get("analysis_id"):
            raise Invalid("utility-input analysis_id does not match analysis plan")
        if value.get("status") != "ready_for_human_review":
            raise Invalid("utility-input status must be ready_for_human_review")
        binding = obj(value.get("base_analysis"), "base_analysis")
        exact(binding, {"path", "content_sha256"}, "base_analysis")
        if binding.get("path") != ANALYSIS_PATH or binding.get("content_sha256") != hashlib.sha256(analysis_raw).hexdigest():
            raise Invalid("base_analysis does not bind the current analysis bytes")

        decision = obj(plan.get("decision_problem"), "decision_problem")
        target = obj(value.get("target_context"), "target_context")
        exact(target, {"jurisdiction", "population", "outcome"}, "target_context")
        if target.get("jurisdiction") != text(decision.get("jurisdiction"), "decision_problem.jurisdiction"):
            raise Invalid("target jurisdiction does not match the analysis")
        if target.get("population") != text(decision.get("population"), "decision_problem.population"):
            raise Invalid("target population does not match the analysis")
        if target.get("outcome") != "QALY" or value.get("cycle_value_timing") != "cycle_average":
            raise Invalid("target outcome must be QALY and timing must be cycle_average")
        cycles = plan.get("cycles")
        if isinstance(cycles, bool) or not isinstance(cycles, int) or not 1 <= cycles <= 10_000:
            raise Invalid("analysis cycles must be an integer from 1 to 10000")
        order = strings(plan.get("strategy_order"), "strategy_order")
        states = strings(plan.get("states"), "states")
        strategies = obj(plan.get("strategies"), "strategies")
        if set(strategies) != set(order):
            raise Invalid("analysis strategies must match strategy_order")
        valid_ids = basis_ids(plan)
        item_order = strings(value.get("item_order"), "item_order")
        if any(SAFE_ID.fullmatch(item) is None for item in item_order) or len(item_order) != len(order) * len(states):
            raise Invalid("item_order must contain one safe id per strategy and state")
        items = obj(value.get("items"), "items")
        if set(items) != set(item_order):
            raise Invalid("items must match item_order exactly")

        computed = {strategy: [[0.0] * len(states) for _ in range(cycles)] for strategy in order}
        pairs: set[tuple[str, str]] = set()
        for item_id in item_order:
            item = obj(items[item_id], f"items.{item_id}")
            exact(item, ITEM_KEYS, f"items.{item_id}")
            if item.get("item_id") != item_id:
                raise Invalid(f"items.{item_id}.item_id does not match its key")
            strategy_id, state_id = item.get("strategy_id"), item.get("state_id")
            if strategy_id not in order or state_id not in states or (strategy_id, state_id) in pairs:
                raise Invalid(f"items.{item_id} has an invalid or duplicated strategy/state pair")
            pairs.add((strategy_id, state_id))
            text(item.get("description"), f"items.{item_id}.description")

            application = obj(item.get("application"), f"items.{item_id}.application")
            exact(application, {"type", "timing", "captured_effects", "excluded_effects", "overlap_assessment"}, f"items.{item_id}.application")
            if application.get("type") != "health_state_utility" or application.get("timing") != "cycle_average_while_in_state":
                raise Invalid(f"items.{item_id}.application has unsupported type or timing")
            strings(application.get("captured_effects"), f"items.{item_id}.application.captured_effects")
            strings(application.get("excluded_effects"), f"items.{item_id}.application.excluded_effects", empty=True)
            overlap = obj(application.get("overlap_assessment"), f"items.{item_id}.application.overlap_assessment")
            exact(overlap, {"rationale", "basis_ids"}, f"items.{item_id}.application.overlap_assessment")
            text(overlap.get("rationale"), f"items.{item_id}.application.overlap_assessment.rationale")
            linked(overlap.get("basis_ids"), valid_ids, f"items.{item_id}.application.overlap_assessment.basis_ids")

            measurement = obj(item.get("measurement"), f"items.{item_id}.measurement")
            exact(measurement, {"source_design", "instrument_name", "instrument_version", "instrument_class", "respondent", "source_population", "sample_size", "assessment_timing", "basis_ids"}, f"items.{item_id}.measurement")
            if measurement.get("source_design") not in SOURCE_DESIGNS or measurement.get("instrument_class") not in INSTRUMENT_CLASSES or measurement.get("respondent") not in RESPONDENTS:
                raise Invalid(f"items.{item_id}.measurement contains an unsupported enum")
            for field in ("instrument_name", "instrument_version", "source_population", "assessment_timing"):
                text(measurement.get(field), f"items.{item_id}.measurement.{field}")
            sample = measurement.get("sample_size")
            if sample is not None and (isinstance(sample, bool) or not isinstance(sample, int) or sample <= 0):
                raise Invalid(f"items.{item_id}.measurement.sample_size must be positive or null")
            linked(measurement.get("basis_ids"), valid_ids, f"items.{item_id}.measurement.basis_ids")

            valuation = obj(item.get("valuation"), f"items.{item_id}.valuation")
            exact(valuation, {"value_origin", "value_set_id", "value_set_jurisdiction", "preference_population", "valuation_method", "anchor", "license_status", "basis_ids"}, f"items.{item_id}.valuation")
            origin = valuation.get("value_origin")
            if origin not in VALUE_ORIGINS or valuation.get("valuation_method") not in VALUATION_METHODS or valuation.get("license_status") not in LICENSES:
                raise Invalid(f"items.{item_id}.valuation contains an unsupported enum")
            if valuation.get("anchor") != "dead_0_full_health_1":
                raise Invalid(f"items.{item_id}.valuation.anchor is invalid")
            text(valuation.get("preference_population"), f"items.{item_id}.valuation.preference_population")
            linked(valuation.get("basis_ids"), valid_ids, f"items.{item_id}.valuation.basis_ids")
            if origin in {"value_set", "mapped"}:
                text(valuation.get("value_set_id"), f"items.{item_id}.valuation.value_set_id")
                text(valuation.get("value_set_jurisdiction"), f"items.{item_id}.valuation.value_set_jurisdiction")
            elif valuation.get("value_set_id") is not None or valuation.get("value_set_jurisdiction") is not None:
                raise Invalid(f"items.{item_id}.valuation must not claim a value set")
            if state_id != "dead" and origin == "anchor":
                raise Invalid(f"items.{item_id}.valuation anchor origin is reserved for the dead state")

            mapping = item.get("mapping")
            if origin == "mapped":
                if valuation.get("valuation_method") != "algorithmic_mapping":
                    raise Invalid(f"items.{item_id} mapped value requires algorithmic_mapping")
                mapping = obj(mapping, f"items.{item_id}.mapping")
                exact(mapping, {"source_measure", "target_measure", "algorithm_id", "estimation_population", "validation_status", "performance_basis_ids", "license_status"}, f"items.{item_id}.mapping")
                for field in ("source_measure", "target_measure", "algorithm_id", "estimation_population"):
                    text(mapping.get(field), f"items.{item_id}.mapping.{field}")
                if mapping.get("validation_status") not in {"internal", "external", "both"} or mapping.get("license_status") not in LICENSES - {"not_applicable"}:
                    raise Invalid(f"items.{item_id}.mapping contains an unsupported enum")
                linked(mapping.get("performance_basis_ids"), valid_ids, f"items.{item_id}.mapping.performance_basis_ids")
            elif mapping is not None:
                raise Invalid(f"items.{item_id}.mapping must be null unless mapped")

            source = obj(item.get("source_utility"), f"items.{item_id}.source_utility")
            exact(source, {"value", "basis_ids"}, f"items.{item_id}.source_utility")
            source_value = utility(source.get("value"), f"items.{item_id}.source_utility.value")
            linked(source.get("basis_ids"), valid_ids, f"items.{item_id}.source_utility.basis_ids")
            factors = [1.0] * cycles
            adjustments = item.get("adjustments")
            if not isinstance(adjustments, list) or len(adjustments) > len(ADJUSTMENTS):
                raise Invalid(f"items.{item_id}.adjustments is invalid")
            seen: set[str] = set()
            for index, raw_adjustment in enumerate(adjustments):
                adjustment = obj(raw_adjustment, f"items.{item_id}.adjustments[{index}]")
                exact(adjustment, {"kind", "operation", "method", "factors", "basis_ids"}, f"items.{item_id}.adjustments[{index}]")
                kind = adjustment.get("kind")
                if kind not in ADJUSTMENTS or kind in seen or adjustment.get("operation") != "multiply":
                    raise Invalid(f"items.{item_id}.adjustments[{index}] is unsupported or duplicated")
                seen.add(kind)
                text(adjustment.get("method"), f"items.{item_id}.adjustments[{index}].method")
                linked(adjustment.get("basis_ids"), valid_ids, f"items.{item_id}.adjustments[{index}].basis_ids")
                values = adjustment.get("factors")
                if not isinstance(values, list) or len(values) != cycles:
                    raise Invalid(f"items.{item_id}.adjustments[{index}].factors must match cycles")
                for cycle, raw_factor in enumerate(values):
                    factor = number(raw_factor, f"items.{item_id}.adjustments[{index}].factors[{cycle}]")
                    if factor <= 0:
                        raise Invalid(f"items.{item_id}.adjustments[{index}].factors must be positive")
                    factors[cycle] *= factor
            cycle_values = item.get("cycle_values")
            if not isinstance(cycle_values, list) or len(cycle_values) != cycles:
                raise Invalid(f"items.{item_id}.cycle_values must match cycles")
            for cycle, raw_value in enumerate(cycle_values):
                actual = utility(raw_value, f"items.{item_id}.cycle_values[{cycle}]")
                if not isclose(actual, source_value * factors[cycle], rel_tol=1e-9, abs_tol=1e-9):
                    raise Invalid(f"items.{item_id}.cycle_values[{cycle}] does not reproduce source and factors")
                computed[strategy_id][cycle][states.index(state_id)] = actual
            if state_id == "dead" and (
                source_value != 0
                or adjustments
                or any(cycle_values)
                or origin != "anchor"
                or measurement.get("source_design") != "anchor"
                or measurement.get("instrument_class") != "qaly_anchor"
                or measurement.get("respondent") != "not_applicable"
                or measurement.get("sample_size") is not None
                or valuation.get("valuation_method") != "anchor"
                or valuation.get("license_status") != "not_applicable"
            ):
                raise Invalid(f"items.{item_id} dead state must be the unadjusted QALY anchor zero")
            uncertainty = obj(item.get("uncertainty"), f"items.{item_id}.uncertainty")
            exact(uncertainty, {"status", "basis_ids", "limitations"}, f"items.{item_id}.uncertainty")
            if uncertainty.get("status") not in {"fixed", "range_available", "distribution_available"}:
                raise Invalid(f"items.{item_id}.uncertainty.status is unsupported")
            linked(uncertainty.get("basis_ids"), valid_ids, f"items.{item_id}.uncertainty.basis_ids")
            strings(uncertainty.get("limitations"), f"items.{item_id}.uncertainty.limitations")

        declared = obj(value.get("cycle_state_utilities"), "cycle_state_utilities")
        if set(declared) != set(order):
            raise Invalid("cycle_state_utilities must match strategy_order")
        for strategy_id in order:
            rows = declared[strategy_id]
            if not isinstance(rows, list) or len(rows) != cycles:
                raise Invalid(f"cycle_state_utilities.{strategy_id} must match cycles")
            for cycle, row in enumerate(rows):
                if not isinstance(row, list) or len(row) != len(states):
                    raise Invalid(f"cycle_state_utilities.{strategy_id}[{cycle}] must match states")
                for state_index, raw_value in enumerate(row):
                    actual = utility(raw_value, f"cycle_state_utilities.{strategy_id}[{cycle}][{state_index}]")
                    if not isclose(actual, computed[strategy_id][cycle][state_index], rel_tol=1e-9, abs_tol=1e-9):
                        raise Invalid(f"cycle_state_utilities.{strategy_id}[{cycle}][{state_index}] is not reproduced")
            aggregate = obj(strategies.get(strategy_id), f"strategies.{strategy_id}").get("state_utilities")
            if not isinstance(aggregate, list) or len(aggregate) != len(states):
                raise Invalid(f"strategies.{strategy_id}.state_utilities must match states")
            for index, raw_value in enumerate(aggregate):
                if not isclose(number(raw_value, f"strategies.{strategy_id}.state_utilities[{index}]"), number(rows[0][index], "first cycle"), rel_tol=1e-9, abs_tol=1e-9):
                    raise Invalid(f"strategies.{strategy_id}.state_utilities[{index}] must match first cycle")
        strings(value.get("limitations"), "limitations")
    except Invalid as error:
        return [str(error)]
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis_plan", type=Path)
    parser.add_argument("utility_inputs", type=Path)
    args = parser.parse_args()
    try:
        analysis_raw = args.analysis_plan.read_bytes()
        analysis = json.loads(analysis_raw)
        artifact = json.loads(args.utility_inputs.read_bytes())
    except (OSError, json.JSONDecodeError) as error:
        print(f"INVALID: {error}")
        return 1
    errors = validate(analysis, analysis_raw, artifact)
    if errors:
        for error in errors:
            print(f"INVALID: {error}")
        return 1
    print("VALID: utility inputs 0.1.0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
