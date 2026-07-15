"""Model-structure-neutral economic inputs for deterministic HEOR analyses."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
import re
from typing import Any

from .model import MarkovSpecification, ModelValidationError


SCHEMA_VERSION = "0.14.0"
PREVIOUS_SCHEMA_VERSION = "0.13.0"
EARLIER_SCHEMA_VERSION = "0.12.0"
PSM_PLAN_PATH = "heor/partitioned-survival-plan.json"
COST_NORMALIZATION_PATH = "heor/cost-input-normalization.json"
UTILITY_INPUTS_PATH = "heor/utility-inputs.json"
MAX_STRATEGIES = 16
STRATEGY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class EconomicStrategy:
    name: str
    state_costs: tuple[float, ...]
    state_utilities: tuple[float, ...]


@dataclass(frozen=True)
class EconomicSpecification:
    schema_version: str
    analysis_id: str
    currency: str
    price_year: int
    states: tuple[str, ...]
    cycles: int
    cycle_length_years: float
    cost_discount_rate: float
    outcome_discount_rate: float
    half_cycle_correction: bool
    willingness_to_pay: float | None
    strategy_order: tuple[str, ...]
    baseline_strategy_id: str
    strategies: tuple[tuple[str, EconomicStrategy], ...]

    @property
    def strategy_map(self) -> dict[str, EconomicStrategy]:
        return dict(self.strategies)

    @classmethod
    def from_analysis_plan(cls, value: dict[str, Any]) -> "EconomicSpecification":
        value = _mapping(value, "analysis plan")
        schema_version = value.get("schema_version")
        if schema_version not in {
            EARLIER_SCHEMA_VERSION,
            PREVIOUS_SCHEMA_VERSION,
            SCHEMA_VERSION,
        }:
            raise ModelValidationError(
                "structure-neutral economic inputs require analysis schema_version 0.12.0 through 0.14.0"
            )
        if "approvals" in value:
            raise ModelValidationError(
                "approvals are not analysis inputs; desktop workflow authorization is app-owned"
            )
        linked = _mapping(value.get("partitioned_survival_analysis"), "partitioned_survival_analysis")
        if linked != {"path": PSM_PLAN_PATH}:
            raise ModelValidationError(
                f"analysis schema {SCHEMA_VERSION} must link only {PSM_PLAN_PATH}"
            )
        cost_link = value.get("cost_input_normalization")
        if schema_version in {PREVIOUS_SCHEMA_VERSION, SCHEMA_VERSION}:
            if cost_link != {"path": COST_NORMALIZATION_PATH}:
                raise ModelValidationError(
                    f"analysis schema {schema_version} must link only {COST_NORMALIZATION_PATH}"
                )
        elif cost_link is not None:
            raise ModelValidationError(
                "cost_input_normalization is admitted only by analysis schema 0.13.0 or 0.14.0"
            )
        utility_link = value.get("utility_inputs")
        if schema_version == SCHEMA_VERSION:
            if utility_link != {"path": UTILITY_INPUTS_PATH}:
                raise ModelValidationError(
                    f"analysis schema {SCHEMA_VERSION} must link only {UTILITY_INPUTS_PATH}"
                )
        elif utility_link is not None:
            raise ModelValidationError(
                "utility_inputs is admitted only by analysis schema 0.14.0"
            )
        economic_basis = _mapping(value.get("economic_basis"), "economic_basis")
        if set(economic_basis) != {"currency", "price_year"}:
            raise ModelValidationError("economic_basis fields must be exactly currency and price_year")
        currency = economic_basis.get("currency")
        if not isinstance(currency, str) or not re.fullmatch(r"[A-Z]{3}", currency):
            raise ModelValidationError("economic_basis.currency must be a three-letter uppercase code")
        price_year = _strict_int(economic_basis.get("price_year"), "economic_basis.price_year")
        if not 1900 <= price_year <= 2100:
            raise ModelValidationError("economic_basis.price_year must be from 1900 to 2100")
        analysis_id = _nonempty(value.get("analysis_id"), "analysis_id")
        states_raw = value.get("states")
        if (
            not isinstance(states_raw, list)
            or not states_raw
            or any(not isinstance(state, str) or not state.strip() for state in states_raw)
            or len(states_raw) != len(set(states_raw))
        ):
            raise ModelValidationError("states must be non-empty unique strings")
        states = tuple(states_raw)
        cycles = _strict_int(value.get("cycles"), "cycles")
        if not 1 <= cycles <= 10_000:
            raise ModelValidationError("cycles must be from 1 to 10000")
        cycle_length = _strict_float(value.get("cycle_length_years"), "cycle_length_years")
        if cycle_length <= 0:
            raise ModelValidationError("cycle_length_years must be positive")
        discounts = _mapping(value.get("discount_rates"), "discount_rates")
        if set(discounts) != {"costs", "outcomes"}:
            raise ModelValidationError("discount_rates fields must be exactly costs and outcomes")
        cost_discount = _strict_float(discounts.get("costs"), "discount_rates.costs")
        outcome_discount = _strict_float(discounts.get("outcomes"), "discount_rates.outcomes")
        if cost_discount < 0 or outcome_discount < 0:
            raise ModelValidationError("discount rates must be non-negative")
        half_cycle = value.get("half_cycle_correction")
        if not isinstance(half_cycle, bool):
            raise ModelValidationError("half_cycle_correction must be a boolean")
        willingness_to_pay = (
            None
            if value.get("willingness_to_pay") is None
            else _strict_float(value.get("willingness_to_pay"), "willingness_to_pay")
        )
        if willingness_to_pay is not None and willingness_to_pay < 0:
            raise ModelValidationError("willingness_to_pay must be non-negative")
        order_raw = value.get("strategy_order")
        if (
            not isinstance(order_raw, list)
            or not 2 <= len(order_raw) <= MAX_STRATEGIES
            or any(
                not isinstance(item, str) or not STRATEGY_ID_PATTERN.fullmatch(item)
                for item in order_raw
            )
            or len(order_raw) != len(set(order_raw))
        ):
            raise ModelValidationError("strategy_order must contain 2-16 unique safe strategy ids")
        order = tuple(order_raw)
        baseline = value.get("baseline_strategy_id")
        if baseline != order[0]:
            raise ModelValidationError("baseline_strategy_id must be the first strategy_order entry")
        strategies_raw = _mapping(value.get("strategies"), "strategies")
        if set(strategies_raw) != set(order):
            raise ModelValidationError("strategies must contain exactly the strategy_order ids")
        strategies: list[tuple[str, EconomicStrategy]] = []
        for strategy_id in order:
            raw = _mapping(strategies_raw.get(strategy_id), f"strategies.{strategy_id}")
            if set(raw) != {"name", "state_costs", "state_utilities"}:
                raise ModelValidationError(
                    f"strategies.{strategy_id} must contain only name, state_costs, and state_utilities; transition structure is forbidden for partitioned survival"
                )
            name = _nonempty(raw.get("name"), f"strategies.{strategy_id}.name")
            costs = _numeric_tuple(raw.get("state_costs"), f"strategies.{strategy_id}.state_costs")
            utilities = _numeric_tuple(
                raw.get("state_utilities"), f"strategies.{strategy_id}.state_utilities"
            )
            if len(costs) != len(states) or len(utilities) != len(states):
                raise ModelValidationError(
                    f"strategies.{strategy_id} state rewards must match the {len(states)} analysis states"
                )
            if any(cost < 0 for cost in costs):
                raise ModelValidationError(f"strategies.{strategy_id}.state_costs must be non-negative")
            if any(utility < -1 or utility > 1 for utility in utilities):
                raise ModelValidationError(
                    f"strategies.{strategy_id}.state_utilities must be from -1 to 1"
                )
            strategies.append((strategy_id, EconomicStrategy(name, costs, utilities)))
        if len({strategy.name for _, strategy in strategies}) != len(strategies):
            raise ModelValidationError("strategy names must be unique")
        return cls(
            schema_version=schema_version,
            analysis_id=analysis_id,
            currency=currency,
            price_year=price_year,
            states=states,
            cycles=cycles,
            cycle_length_years=cycle_length,
            cost_discount_rate=cost_discount,
            outcome_discount_rate=outcome_discount,
            half_cycle_correction=half_cycle,
            willingness_to_pay=willingness_to_pay,
            strategy_order=order,
            baseline_strategy_id=baseline,
            strategies=tuple(strategies),
        )

    @classmethod
    def from_legacy_markov_plan(cls, value: dict[str, Any]) -> "EconomicSpecification":
        legacy = MarkovSpecification.from_dict(value)
        return cls(
            schema_version=legacy.schema_version,
            analysis_id=legacy.analysis_id,
            currency=legacy.currency or "",
            price_year=legacy.price_year or 0,
            states=legacy.states,
            cycles=legacy.cycles,
            cycle_length_years=legacy.cycle_length_years,
            cost_discount_rate=legacy.cost_discount_rate,
            outcome_discount_rate=legacy.outcome_discount_rate,
            half_cycle_correction=legacy.half_cycle_correction,
            willingness_to_pay=legacy.willingness_to_pay,
            strategy_order=legacy.strategy_order,
            baseline_strategy_id=legacy.baseline_strategy_id,
            strategies=tuple(
                (
                    strategy_id,
                    EconomicStrategy(strategy.name, strategy.state_costs, strategy.state_utilities),
                )
                for strategy_id, strategy in legacy.strategies
            ),
        )


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ModelValidationError(f"{name} must be an object")
    return value


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelValidationError(f"{name} must not be empty")
    return value


def _strict_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ModelValidationError(f"{name} must be an integer")
    return value


def _strict_float(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelValidationError(f"{name} must be a number")
    result = float(value)
    if not isfinite(result):
        raise ModelValidationError(f"{name} must be finite")
    return result


def _numeric_tuple(value: Any, name: str) -> tuple[float, ...]:
    if not isinstance(value, list):
        raise ModelValidationError(f"{name} must be an array")
    return tuple(
        _strict_float(item, f"{name}[{index}]") for index, item in enumerate(value)
    )
