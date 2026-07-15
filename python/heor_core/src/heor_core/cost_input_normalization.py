"""Deterministic normalization of evidence-linked annual state-cost inputs.

The bounded contract decomposes each annual state-cost rate into a resource
quantity and unit price, then applies explicit multiplicative price-basis
adjustments.  It validates arithmetic and provenance identifiers; it never
chooses the cost scope, price source, index, exchange rate, or tax treatment.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from math import isclose, isfinite
import re
from typing import Any

from .model import ModelValidationError


SCHEMA_VERSION = "0.1.0"
ARTIFACT_PATH = "heor/cost-input-normalization.json"
ANALYSIS_PATH = "heor/analysis-plan.json"
SUPPORTED_ANALYSIS_SCHEMAS = {"0.12.0", "0.13.0"}
MAX_ITEMS = 1_000
TOLERANCE = 1e-9
SAFE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
PRICE_BASES = {
    "list_price",
    "net_price",
    "tariff",
    "paid_price",
    "negotiated_price",
    "microcost",
    "opportunity_cost",
    "other",
}
TAX_STATUSES = {"included", "excluded", "not_applicable"}
ADJUSTMENT_KINDS = {"inflation", "currency_conversion", "price_adjustment"}


@dataclass(frozen=True)
class CostNormalizationSummary:
    normalization_id: str
    item_count: int
    annual_state_costs: dict[str, tuple[float, ...]]


def validate_cost_input_normalization(
    analysis_plan: dict[str, Any],
    analysis_raw: bytes,
    artifact: dict[str, Any],
    artifact_raw: bytes,
) -> CostNormalizationSummary:
    """Validate exact bytes and reproduce every annual state-cost rate."""

    plan = _object(analysis_plan, "analysis plan")
    if plan.get("schema_version") not in SUPPORTED_ANALYSIS_SCHEMAS:
        raise ModelValidationError(
            "cost-input normalization requires analysis schema 0.12.0 or 0.13.0"
        )
    value = _object(artifact, "cost-input normalization artifact")
    _exact_keys(
        value,
        {
            "schema_version",
            "normalization_id",
            "analysis_id",
            "status",
            "base_analysis",
            "target_basis",
            "item_order",
            "items",
            "annual_state_costs",
            "limitations",
        },
        "cost-input normalization artifact",
    )
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ModelValidationError(
            f"cost-input normalization schema_version must be {SCHEMA_VERSION}"
        )
    normalization_id = _safe_id(value.get("normalization_id"), "normalization_id")
    if value.get("analysis_id") != plan.get("analysis_id"):
        raise ModelValidationError(
            "cost-input normalization analysis_id does not match analysis plan"
        )
    if value.get("status") != "ready_for_human_review":
        raise ModelValidationError(
            "cost-input normalization status must be ready_for_human_review"
        )
    _binding(value.get("base_analysis"), ANALYSIS_PATH, analysis_raw)

    economic_basis = _object(plan.get("economic_basis"), "economic_basis")
    decision_problem = _object(plan.get("decision_problem"), "decision_problem")
    target = _object(value.get("target_basis"), "target_basis")
    _exact_keys(
        target,
        {"currency", "price_year", "jurisdiction", "perspective"},
        "target_basis",
    )
    currency = _currency(economic_basis.get("currency"), "economic_basis.currency")
    price_year = _year(economic_basis.get("price_year"), "economic_basis.price_year")
    if target.get("currency") != currency or target.get("price_year") != price_year:
        raise ModelValidationError("target_basis must match analysis economic_basis")
    if target.get("jurisdiction") != _nonempty(
        decision_problem.get("jurisdiction"), "decision_problem.jurisdiction"
    ):
        raise ModelValidationError(
            "target_basis.jurisdiction must match decision_problem.jurisdiction"
        )
    if target.get("perspective") != _nonempty(
        decision_problem.get("perspective"), "decision_problem.perspective"
    ):
        raise ModelValidationError(
            "target_basis.perspective must match decision_problem.perspective"
        )

    strategy_order = _safe_id_list(plan.get("strategy_order"), "strategy_order")
    states = _string_list(plan.get("states"), "states")
    strategies = _object(plan.get("strategies"), "strategies")
    if set(strategies) != set(strategy_order):
        raise ModelValidationError("analysis strategies must match strategy_order")
    valid_basis_ids = _basis_ids(plan)

    item_order = _safe_id_list(value.get("item_order"), "item_order")
    if not 1 <= len(item_order) <= MAX_ITEMS:
        raise ModelValidationError(f"item_order must contain 1-{MAX_ITEMS} items")
    items = _object(value.get("items"), "items")
    if set(items) != set(item_order):
        raise ModelValidationError("items must contain exactly the item_order ids")

    totals = {
        strategy_id: [0.0 for _ in states] for strategy_id in strategy_order
    }
    for item_id in item_order:
        item = _object(items.get(item_id), f"items.{item_id}")
        _exact_keys(
            item,
            {
                "item_id",
                "strategy_id",
                "state_id",
                "category",
                "description",
                "scope_basis_ids",
                "annual_quantity",
                "unit_price",
                "adjustments",
                "normalized_unit_price",
                "normalized_annual_cost",
            },
            f"items.{item_id}",
        )
        if item.get("item_id") != item_id:
            raise ModelValidationError(f"items.{item_id}.item_id must match its object key")
        strategy_id = item.get("strategy_id")
        if strategy_id not in strategy_order:
            raise ModelValidationError(f"items.{item_id}.strategy_id is not admitted")
        state_id = item.get("state_id")
        if state_id not in states:
            raise ModelValidationError(f"items.{item_id}.state_id is not admitted")
        _safe_id(item.get("category"), f"items.{item_id}.category")
        _nonempty(item.get("description"), f"items.{item_id}.description")
        _linked_ids(
            item.get("scope_basis_ids"),
            valid_basis_ids,
            f"items.{item_id}.scope_basis_ids",
        )

        quantity = _object(item.get("annual_quantity"), f"items.{item_id}.annual_quantity")
        _exact_keys(
            quantity,
            {"value", "unit", "basis_ids"},
            f"items.{item_id}.annual_quantity",
        )
        quantity_value = _positive(quantity.get("value"), f"items.{item_id}.annual_quantity.value")
        quantity_unit = _nonempty(quantity.get("unit"), f"items.{item_id}.annual_quantity.unit")
        _linked_ids(
            quantity.get("basis_ids"),
            valid_basis_ids,
            f"items.{item_id}.annual_quantity.basis_ids",
        )

        unit_price = _object(item.get("unit_price"), f"items.{item_id}.unit_price")
        _exact_keys(
            unit_price,
            {
                "amount",
                "per_unit",
                "currency",
                "price_year",
                "jurisdiction",
                "price_basis",
                "tax_status",
                "basis_ids",
            },
            f"items.{item_id}.unit_price",
        )
        amount = _nonnegative(unit_price.get("amount"), f"items.{item_id}.unit_price.amount")
        if unit_price.get("per_unit") != quantity_unit:
            raise ModelValidationError(
                f"items.{item_id}.unit_price.per_unit must match annual_quantity.unit"
            )
        source_currency = _currency(
            unit_price.get("currency"), f"items.{item_id}.unit_price.currency"
        )
        source_year = _year(
            unit_price.get("price_year"), f"items.{item_id}.unit_price.price_year"
        )
        _nonempty(unit_price.get("jurisdiction"), f"items.{item_id}.unit_price.jurisdiction")
        if unit_price.get("price_basis") not in PRICE_BASES:
            raise ModelValidationError(f"items.{item_id}.unit_price.price_basis is unsupported")
        if unit_price.get("tax_status") not in TAX_STATUSES:
            raise ModelValidationError(f"items.{item_id}.unit_price.tax_status is unsupported")
        _linked_ids(
            unit_price.get("basis_ids"),
            valid_basis_ids,
            f"items.{item_id}.unit_price.basis_ids",
        )

        adjustments = item.get("adjustments")
        if not isinstance(adjustments, list) or len(adjustments) > len(ADJUSTMENT_KINDS):
            raise ModelValidationError(
                f"items.{item_id}.adjustments must contain at most one of each supported kind"
            )
        seen_kinds: set[str] = set()
        factor = 1.0
        for index, raw_adjustment in enumerate(adjustments):
            label = f"items.{item_id}.adjustments[{index}]"
            adjustment = _object(raw_adjustment, label)
            _exact_keys(adjustment, {"kind", "factor", "method", "basis_ids"}, label)
            kind = adjustment.get("kind")
            if kind not in ADJUSTMENT_KINDS or kind in seen_kinds:
                raise ModelValidationError(f"{label}.kind is unsupported or duplicated")
            seen_kinds.add(kind)
            factor *= _positive(adjustment.get("factor"), f"{label}.factor")
            _nonempty(adjustment.get("method"), f"{label}.method")
            _linked_ids(adjustment.get("basis_ids"), valid_basis_ids, f"{label}.basis_ids")
        if (source_year != price_year) != ("inflation" in seen_kinds):
            raise ModelValidationError(
                f"items.{item_id} must use inflation exactly when source and target price years differ"
            )
        if (source_currency != currency) != ("currency_conversion" in seen_kinds):
            raise ModelValidationError(
                f"items.{item_id} must use currency_conversion exactly when source and target currencies differ"
            )

        normalized_unit_price = _nonnegative(
            item.get("normalized_unit_price"), f"items.{item_id}.normalized_unit_price"
        )
        expected_unit_price = amount * factor
        _reproduces(expected_unit_price, normalized_unit_price, f"items.{item_id}.normalized_unit_price")
        normalized_annual_cost = _nonnegative(
            item.get("normalized_annual_cost"), f"items.{item_id}.normalized_annual_cost"
        )
        expected_annual_cost = quantity_value * normalized_unit_price
        _reproduces(expected_annual_cost, normalized_annual_cost, f"items.{item_id}.normalized_annual_cost")
        totals[strategy_id][states.index(state_id)] += normalized_annual_cost

    declared = _object(value.get("annual_state_costs"), "annual_state_costs")
    if set(declared) != set(strategy_order):
        raise ModelValidationError("annual_state_costs must contain exactly strategy_order ids")
    normalized: dict[str, tuple[float, ...]] = {}
    for strategy_id in strategy_order:
        costs = _number_list(declared.get(strategy_id), f"annual_state_costs.{strategy_id}")
        if len(costs) != len(states) or any(cost < 0 for cost in costs):
            raise ModelValidationError(
                f"annual_state_costs.{strategy_id} must match the state order with non-negative values"
            )
        plan_costs = _number_list(
            _object(strategies.get(strategy_id), f"strategies.{strategy_id}").get("state_costs"),
            f"strategies.{strategy_id}.state_costs",
        )
        if len(plan_costs) != len(states):
            raise ModelValidationError(f"strategies.{strategy_id}.state_costs must match states")
        for state_index, (calculated, stated, model_value) in enumerate(
            zip(totals[strategy_id], costs, plan_costs)
        ):
            label = f"annual_state_costs.{strategy_id}[{state_index}]"
            _reproduces(calculated, stated, label)
            _reproduces(stated, model_value, f"{label} against analysis plan")
        normalized[strategy_id] = tuple(costs)

    limitations = _string_list(value.get("limitations"), "limitations")
    if not limitations:
        raise ModelValidationError("limitations must contain at least one unresolved boundary")
    return CostNormalizationSummary(normalization_id, len(item_order), normalized)


def artifact_sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


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


def _binding(value: Any, expected_path: str, expected_raw: bytes) -> None:
    binding = _object(value, "base_analysis")
    _exact_keys(binding, {"path", "content_sha256"}, "base_analysis")
    if binding.get("path") != expected_path:
        raise ModelValidationError(f"base_analysis.path must be {expected_path}")
    if binding.get("content_sha256") != hashlib.sha256(expected_raw).hexdigest():
        raise ModelValidationError("base_analysis.content_sha256 does not match current bytes")


def _linked_ids(value: Any, valid: set[str], name: str) -> tuple[str, ...]:
    values = _string_list(value, name)
    if not values or len(values) != len(set(values)) or any(item not in valid for item in values):
        raise ModelValidationError(f"{name} must contain unique analysis evidence or proposed-assumption ids")
    return tuple(values)


def _safe_id_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ModelValidationError(f"{name} must be a non-empty array")
    result = [_safe_id(item, f"{name}[{index}]") for index, item in enumerate(value)]
    if len(result) != len(set(result)):
        raise ModelValidationError(f"{name} must not contain duplicates")
    return result


def _string_list(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ModelValidationError(f"{name} must be an array of non-empty strings")
    return list(value)


def _number_list(value: Any, name: str) -> list[float]:
    if not isinstance(value, list):
        raise ModelValidationError(f"{name} must be an array")
    return [_finite(item, f"{name}[{index}]") for index, item in enumerate(value)]


def _currency(value: Any, name: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[A-Z]{3}", value) is None:
        raise ModelValidationError(f"{name} must be a three-letter uppercase code")
    return value


def _year(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 1900 <= value <= 2100:
        raise ModelValidationError(f"{name} must be an integer from 1900 to 2100")
    return value


def _positive(value: Any, name: str) -> float:
    result = _finite(value, name)
    if result <= 0:
        raise ModelValidationError(f"{name} must be positive")
    return result


def _nonnegative(value: Any, name: str) -> float:
    result = _finite(value, name)
    if result < 0:
        raise ModelValidationError(f"{name} must be non-negative")
    return result


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
        raise ModelValidationError(f"{name} must be finite")
    return float(value)


def _reproduces(expected: float, actual: float, name: str) -> None:
    if not isclose(expected, actual, rel_tol=TOLERANCE, abs_tol=1e-6):
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
