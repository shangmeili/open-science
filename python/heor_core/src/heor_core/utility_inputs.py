"""Deterministic, evidence-linked health-state utility schedules.

The contract records how one utility input is selected for every strategy and
state, then applies only explicit multiplicative cycle factors. It validates
arithmetic and provenance identifiers; it never chooses an instrument, value
set, mapping algorithm, respondent, population adjustment, or overlap policy.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from math import isclose, isfinite
import re
from typing import Any

from .model import ModelValidationError


SCHEMA_VERSION = "0.1.0"
ARTIFACT_PATH = "heor/utility-inputs.json"
ANALYSIS_PATH = "heor/analysis-plan.json"
SUPPORTED_ANALYSIS_SCHEMAS = {"0.14.0"}
TOLERANCE = 1e-9
SAFE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SOURCE_DESIGNS = {
    "randomized_trial",
    "observational_study",
    "systematic_review",
    "published_model",
    "elicitation_study",
    "anchor",
    "other",
}
INSTRUMENT_CLASSES = {
    "generic_preference_based",
    "condition_specific_preference_based",
    "direct_valuation",
    "mapped_non_preference_measure",
    "qaly_anchor",
    "other",
}
RESPONDENTS = {"patient", "proxy", "carer", "general_public", "mixed", "not_applicable"}
VALUE_ORIGINS = {"value_set", "direct_valuation", "mapped", "anchor"}
VALUATION_METHODS = {
    "time_trade_off",
    "standard_gamble",
    "discrete_choice_experiment",
    "hybrid",
    "algorithmic_mapping",
    "anchor",
    "other",
}
LICENSE_STATUSES = {
    "public",
    "registered_noncommercial",
    "licensed_local",
    "link_only",
    "not_applicable",
}
MAPPING_VALIDATION = {"internal", "external", "both"}
ADJUSTMENT_KINDS = {"age_adjustment", "comorbidity_adjustment", "population_alignment"}
UNCERTAINTY_STATUSES = {"fixed", "range_available", "distribution_available"}


@dataclass(frozen=True)
class UtilityInputSummary:
    utility_input_id: str
    item_count: int
    mapped_item_count: int
    adjusted_item_count: int
    cycle_state_utilities: dict[str, tuple[tuple[float, ...], ...]]


def validate_utility_inputs(
    analysis_plan: dict[str, Any],
    analysis_raw: bytes,
    artifact: dict[str, Any],
    artifact_raw: bytes,
) -> UtilityInputSummary:
    """Validate exact analysis bytes and reproduce every cycle utility."""

    del artifact_raw  # The caller binds these exact bytes from the consuming plan.
    plan = _object(analysis_plan, "analysis plan")
    if plan.get("schema_version") not in SUPPORTED_ANALYSIS_SCHEMAS:
        raise ModelValidationError(
            "utility inputs require analysis schema 0.14.0"
        )
    value = _object(artifact, "utility-input artifact")
    _exact_keys(
        value,
        {
            "schema_version",
            "utility_input_id",
            "analysis_id",
            "status",
            "base_analysis",
            "target_context",
            "cycle_value_timing",
            "item_order",
            "items",
            "cycle_state_utilities",
            "limitations",
        },
        "utility-input artifact",
    )
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ModelValidationError(f"utility-input schema_version must be {SCHEMA_VERSION}")
    utility_input_id = _safe_id(value.get("utility_input_id"), "utility_input_id")
    if value.get("analysis_id") != plan.get("analysis_id"):
        raise ModelValidationError("utility-input analysis_id does not match analysis plan")
    if value.get("status") != "ready_for_human_review":
        raise ModelValidationError("utility-input status must be ready_for_human_review")
    _binding(value.get("base_analysis"), analysis_raw)

    decision = _object(plan.get("decision_problem"), "decision_problem")
    target = _object(value.get("target_context"), "target_context")
    _exact_keys(target, {"jurisdiction", "population", "outcome"}, "target_context")
    if target.get("jurisdiction") != _nonempty(
        decision.get("jurisdiction"), "decision_problem.jurisdiction"
    ):
        raise ModelValidationError("target_context.jurisdiction must match decision problem")
    if target.get("population") != _nonempty(
        decision.get("population"), "decision_problem.population"
    ):
        raise ModelValidationError("target_context.population must match decision problem")
    if target.get("outcome") != "QALY":
        raise ModelValidationError("target_context.outcome must be QALY")
    if value.get("cycle_value_timing") != "cycle_average":
        raise ModelValidationError("cycle_value_timing must be cycle_average")

    cycles = _strict_int(plan.get("cycles"), "cycles")
    if not 1 <= cycles <= 10_000:
        raise ModelValidationError("cycles must be from 1 to 10000")
    strategy_order = _safe_id_list(plan.get("strategy_order"), "strategy_order")
    states = _nonempty_string_list(plan.get("states"), "states")
    strategies = _object(plan.get("strategies"), "strategies")
    if set(strategies) != set(strategy_order):
        raise ModelValidationError("analysis strategies must match strategy_order")
    valid_basis_ids = _basis_ids(plan)

    item_order = _safe_id_list(value.get("item_order"), "item_order")
    expected_items = len(strategy_order) * len(states)
    if len(item_order) != expected_items:
        raise ModelValidationError(
            "item_order must contain exactly one utility item per strategy and state"
        )
    items = _object(value.get("items"), "items")
    if set(items) != set(item_order):
        raise ModelValidationError("items must contain exactly the item_order ids")

    schedules = {
        strategy_id: [[0.0 for _ in states] for _ in range(cycles)]
        for strategy_id in strategy_order
    }
    observed_pairs: set[tuple[str, str]] = set()
    mapped_count = 0
    adjusted_count = 0
    for item_id in item_order:
        item = _object(items.get(item_id), f"items.{item_id}")
        _exact_keys(
            item,
            {
                "item_id",
                "strategy_id",
                "state_id",
                "description",
                "application",
                "measurement",
                "valuation",
                "mapping",
                "source_utility",
                "adjustments",
                "cycle_values",
                "uncertainty",
            },
            f"items.{item_id}",
        )
        if item.get("item_id") != item_id:
            raise ModelValidationError(f"items.{item_id}.item_id must match its object key")
        strategy_id = item.get("strategy_id")
        state_id = item.get("state_id")
        if strategy_id not in strategy_order or state_id not in states:
            raise ModelValidationError(f"items.{item_id} strategy_id or state_id is not admitted")
        pair = (strategy_id, state_id)
        if pair in observed_pairs:
            raise ModelValidationError("utility items must not duplicate a strategy/state pair")
        observed_pairs.add(pair)
        _nonempty(item.get("description"), f"items.{item_id}.description")

        _validate_application(item.get("application"), valid_basis_ids, item_id)
        _validate_measurement(item.get("measurement"), valid_basis_ids, item_id, state_id)
        value_origin = _validate_valuation(
            item.get("valuation"), valid_basis_ids, item_id, state_id
        )
        if value_origin == "mapped" and item["valuation"].get("valuation_method") != "algorithmic_mapping":
            raise ModelValidationError(
                f"items.{item_id}.valuation.valuation_method must be algorithmic_mapping for mapped values"
            )
        _validate_mapping(item.get("mapping"), valid_basis_ids, item_id, value_origin)
        if value_origin == "mapped":
            mapped_count += 1

        source = _object(item.get("source_utility"), f"items.{item_id}.source_utility")
        _exact_keys(source, {"value", "basis_ids"}, f"items.{item_id}.source_utility")
        source_value = _utility(source.get("value"), f"items.{item_id}.source_utility.value")
        _linked_ids(
            source.get("basis_ids"), valid_basis_ids, f"items.{item_id}.source_utility.basis_ids"
        )

        factors = [1.0 for _ in range(cycles)]
        adjustments = item.get("adjustments")
        if not isinstance(adjustments, list) or len(adjustments) > len(ADJUSTMENT_KINDS):
            raise ModelValidationError(
                f"items.{item_id}.adjustments must contain at most one of each supported kind"
            )
        seen_kinds: set[str] = set()
        for index, raw_adjustment in enumerate(adjustments):
            label = f"items.{item_id}.adjustments[{index}]"
            adjustment = _object(raw_adjustment, label)
            _exact_keys(
                adjustment,
                {"kind", "operation", "method", "factors", "basis_ids"},
                label,
            )
            kind = adjustment.get("kind")
            if kind not in ADJUSTMENT_KINDS or kind in seen_kinds:
                raise ModelValidationError(f"{label}.kind is unsupported or duplicated")
            seen_kinds.add(kind)
            if adjustment.get("operation") != "multiply":
                raise ModelValidationError(f"{label}.operation must be multiply")
            _nonempty(adjustment.get("method"), f"{label}.method")
            _linked_ids(adjustment.get("basis_ids"), valid_basis_ids, f"{label}.basis_ids")
            adjustment_factors = _number_list(adjustment.get("factors"), f"{label}.factors")
            if len(adjustment_factors) != cycles or any(factor <= 0 for factor in adjustment_factors):
                raise ModelValidationError(
                    f"{label}.factors must contain one positive value per model cycle"
                )
            factors = [left * right for left, right in zip(factors, adjustment_factors)]
        if adjustments:
            adjusted_count += 1

        cycle_values = _number_list(item.get("cycle_values"), f"items.{item_id}.cycle_values")
        if len(cycle_values) != cycles:
            raise ModelValidationError(
                f"items.{item_id}.cycle_values must contain one value per model cycle"
            )
        for cycle, (actual, factor) in enumerate(zip(cycle_values, factors)):
            _utility(actual, f"items.{item_id}.cycle_values[{cycle}]")
            _reproduces(
                source_value * factor,
                actual,
                f"items.{item_id}.cycle_values[{cycle}]",
            )
        if state_id == "dead" and (
            source_value != 0.0
            or adjustments
            or any(cycle_value != 0.0 for cycle_value in cycle_values)
            or value_origin != "anchor"
        ):
            raise ModelValidationError(
                f"items.{item_id} dead-state utility must be the unadjusted QALY anchor zero"
            )
        _validate_uncertainty(item.get("uncertainty"), valid_basis_ids, item_id)
        state_index = states.index(state_id)
        for cycle, cycle_value in enumerate(cycle_values):
            schedules[strategy_id][cycle][state_index] = cycle_value

    if len(observed_pairs) != expected_items:
        raise ModelValidationError("utility items must cover every strategy/state pair exactly once")

    declared = _object(value.get("cycle_state_utilities"), "cycle_state_utilities")
    if set(declared) != set(strategy_order):
        raise ModelValidationError(
            "cycle_state_utilities must contain exactly strategy_order ids"
        )
    normalized: dict[str, tuple[tuple[float, ...], ...]] = {}
    for strategy_id in strategy_order:
        rows = declared.get(strategy_id)
        if not isinstance(rows, list) or len(rows) != cycles:
            raise ModelValidationError(
                f"cycle_state_utilities.{strategy_id} must contain one row per model cycle"
            )
        parsed_rows: list[tuple[float, ...]] = []
        for cycle, row in enumerate(rows):
            values = _number_list(row, f"cycle_state_utilities.{strategy_id}[{cycle}]")
            if len(values) != len(states):
                raise ModelValidationError(
                    f"cycle_state_utilities.{strategy_id}[{cycle}] must match state order"
                )
            for state_index, (expected, actual) in enumerate(
                zip(schedules[strategy_id][cycle], values)
            ):
                _utility(
                    actual,
                    f"cycle_state_utilities.{strategy_id}[{cycle}][{state_index}]",
                )
                _reproduces(
                    expected,
                    actual,
                    f"cycle_state_utilities.{strategy_id}[{cycle}][{state_index}]",
                )
            parsed_rows.append(tuple(values))
        analysis_utilities = _number_list(
            _object(strategies.get(strategy_id), f"strategies.{strategy_id}").get(
                "state_utilities"
            ),
            f"strategies.{strategy_id}.state_utilities",
        )
        if len(analysis_utilities) != len(states):
            raise ModelValidationError(
                f"strategies.{strategy_id}.state_utilities must match state order"
            )
        for state_index, (first_cycle, analysis_value) in enumerate(
            zip(parsed_rows[0], analysis_utilities)
        ):
            _reproduces(
                first_cycle,
                analysis_value,
                f"strategies.{strategy_id}.state_utilities[{state_index}]",
            )
        normalized[strategy_id] = tuple(parsed_rows)

    limitations = _nonempty_string_list(value.get("limitations"), "limitations")
    if not limitations:
        raise ModelValidationError("limitations must contain at least one unresolved boundary")
    return UtilityInputSummary(
        utility_input_id,
        len(item_order),
        mapped_count,
        adjusted_count,
        normalized,
    )


def artifact_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _validate_application(value: Any, valid_ids: set[str], item_id: str) -> None:
    label = f"items.{item_id}.application"
    application = _object(value, label)
    _exact_keys(
        application,
        {"type", "timing", "captured_effects", "excluded_effects", "overlap_assessment"},
        label,
    )
    if application.get("type") != "health_state_utility":
        raise ModelValidationError(f"{label}.type must be health_state_utility")
    if application.get("timing") != "cycle_average_while_in_state":
        raise ModelValidationError(f"{label}.timing must be cycle_average_while_in_state")
    if not _nonempty_string_list(application.get("captured_effects"), f"{label}.captured_effects"):
        raise ModelValidationError(f"{label}.captured_effects must not be empty")
    _string_list(application.get("excluded_effects"), f"{label}.excluded_effects")
    overlap = _object(application.get("overlap_assessment"), f"{label}.overlap_assessment")
    _exact_keys(overlap, {"rationale", "basis_ids"}, f"{label}.overlap_assessment")
    _nonempty(overlap.get("rationale"), f"{label}.overlap_assessment.rationale")
    _linked_ids(overlap.get("basis_ids"), valid_ids, f"{label}.overlap_assessment.basis_ids")


def _validate_measurement(
    value: Any, valid_ids: set[str], item_id: str, state_id: str
) -> None:
    label = f"items.{item_id}.measurement"
    measurement = _object(value, label)
    _exact_keys(
        measurement,
        {
            "source_design",
            "instrument_name",
            "instrument_version",
            "instrument_class",
            "respondent",
            "source_population",
            "sample_size",
            "assessment_timing",
            "basis_ids",
        },
        label,
    )
    if measurement.get("source_design") not in SOURCE_DESIGNS:
        raise ModelValidationError(f"{label}.source_design is unsupported")
    for field in ("instrument_name", "instrument_version", "source_population", "assessment_timing"):
        _nonempty(measurement.get(field), f"{label}.{field}")
    if measurement.get("instrument_class") not in INSTRUMENT_CLASSES:
        raise ModelValidationError(f"{label}.instrument_class is unsupported")
    if measurement.get("respondent") not in RESPONDENTS:
        raise ModelValidationError(f"{label}.respondent is unsupported")
    sample_size = measurement.get("sample_size")
    if sample_size is not None and _strict_int(sample_size, f"{label}.sample_size") <= 0:
        raise ModelValidationError(f"{label}.sample_size must be positive when present")
    _linked_ids(measurement.get("basis_ids"), valid_ids, f"{label}.basis_ids")
    if state_id == "dead" and (
        measurement.get("source_design") != "anchor"
        or measurement.get("instrument_class") != "qaly_anchor"
        or measurement.get("respondent") != "not_applicable"
        or sample_size is not None
    ):
        raise ModelValidationError(f"{label} dead state must use the QALY anchor metadata")


def _validate_valuation(
    value: Any, valid_ids: set[str], item_id: str, state_id: str
) -> str:
    label = f"items.{item_id}.valuation"
    valuation = _object(value, label)
    _exact_keys(
        valuation,
        {
            "value_origin",
            "value_set_id",
            "value_set_jurisdiction",
            "preference_population",
            "valuation_method",
            "anchor",
            "license_status",
            "basis_ids",
        },
        label,
    )
    origin = valuation.get("value_origin")
    if origin not in VALUE_ORIGINS:
        raise ModelValidationError(f"{label}.value_origin is unsupported")
    if valuation.get("valuation_method") not in VALUATION_METHODS:
        raise ModelValidationError(f"{label}.valuation_method is unsupported")
    if valuation.get("anchor") != "dead_0_full_health_1":
        raise ModelValidationError(f"{label}.anchor must be dead_0_full_health_1")
    if valuation.get("license_status") not in LICENSE_STATUSES:
        raise ModelValidationError(f"{label}.license_status is unsupported")
    _nonempty(valuation.get("preference_population"), f"{label}.preference_population")
    _linked_ids(valuation.get("basis_ids"), valid_ids, f"{label}.basis_ids")
    if origin in {"value_set", "mapped"}:
        _nonempty(valuation.get("value_set_id"), f"{label}.value_set_id")
        _nonempty(
            valuation.get("value_set_jurisdiction"), f"{label}.value_set_jurisdiction"
        )
    elif valuation.get("value_set_id") is not None or valuation.get("value_set_jurisdiction") is not None:
        raise ModelValidationError(
            f"{label} direct valuation or anchor must not claim a value set"
        )
    if state_id == "dead" and (
        origin != "anchor"
        or valuation.get("valuation_method") != "anchor"
        or valuation.get("license_status") != "not_applicable"
    ):
        raise ModelValidationError(f"{label} dead state must use the QALY anchor")
    if state_id != "dead" and origin == "anchor":
        raise ModelValidationError(f"{label} anchor origin is reserved for the dead state")
    return origin


def _validate_mapping(
    value: Any, valid_ids: set[str], item_id: str, value_origin: str
) -> None:
    label = f"items.{item_id}.mapping"
    if value_origin != "mapped":
        if value is not None:
            raise ModelValidationError(f"{label} must be null unless value_origin is mapped")
        return
    mapping = _object(value, label)
    _exact_keys(
        mapping,
        {
            "source_measure",
            "target_measure",
            "algorithm_id",
            "estimation_population",
            "validation_status",
            "performance_basis_ids",
            "license_status",
        },
        label,
    )
    for field in ("source_measure", "target_measure", "algorithm_id", "estimation_population"):
        _nonempty(mapping.get(field), f"{label}.{field}")
    if mapping.get("validation_status") not in MAPPING_VALIDATION:
        raise ModelValidationError(f"{label}.validation_status is unsupported")
    if mapping.get("license_status") not in LICENSE_STATUSES - {"not_applicable"}:
        raise ModelValidationError(f"{label}.license_status is unsupported")
    _linked_ids(
        mapping.get("performance_basis_ids"),
        valid_ids,
        f"{label}.performance_basis_ids",
    )


def _validate_uncertainty(value: Any, valid_ids: set[str], item_id: str) -> None:
    label = f"items.{item_id}.uncertainty"
    uncertainty = _object(value, label)
    _exact_keys(uncertainty, {"status", "basis_ids", "limitations"}, label)
    if uncertainty.get("status") not in UNCERTAINTY_STATUSES:
        raise ModelValidationError(f"{label}.status is unsupported")
    _linked_ids(uncertainty.get("basis_ids"), valid_ids, f"{label}.basis_ids")
    if not _nonempty_string_list(uncertainty.get("limitations"), f"{label}.limitations"):
        raise ModelValidationError(f"{label}.limitations must not be empty")


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
        if not isinstance(mapping, dict):
            continue
        for field in ("source_ids", "extraction_ids", "assumption_ids"):
            values = mapping.get(field)
            if isinstance(values, list):
                identifiers.update(item for item in values if isinstance(item, str) and item)
    return identifiers


def _binding(value: Any, expected_raw: bytes) -> None:
    binding = _object(value, "base_analysis")
    _exact_keys(binding, {"path", "content_sha256"}, "base_analysis")
    if binding.get("path") != ANALYSIS_PATH:
        raise ModelValidationError(f"base_analysis.path must be {ANALYSIS_PATH}")
    if binding.get("content_sha256") != hashlib.sha256(expected_raw).hexdigest():
        raise ModelValidationError("base_analysis.content_sha256 does not match current bytes")


def _linked_ids(value: Any, valid: set[str], name: str) -> tuple[str, ...]:
    values = _nonempty_string_list(value, name)
    if not values or len(values) != len(set(values)) or any(item not in valid for item in values):
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


def _utility(value: Any, name: str) -> float:
    result = _finite(value, name)
    if not -1.0 <= result <= 1.0:
        raise ModelValidationError(f"{name} must be from -1 to 1")
    return result


def _strict_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ModelValidationError(f"{name} must be an integer")
    return value


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
        raise ModelValidationError(f"{name} must be finite")
    return float(value)


def _reproduces(expected: float, actual: float, name: str) -> None:
    if not isclose(expected, actual, rel_tol=TOLERANCE, abs_tol=1e-9):
        raise ModelValidationError(f"{name} does not reproduce the declared value")


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
