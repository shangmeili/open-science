"""Validated deterministic cohort state-transition analysis.

The engine supports two or more strategies, static or model-cycle-dependent
transition matrices, state rewards, and optional half-cycle correction. It has
no network or language-model dependency. Time in state and patient history
remain outside this cohort-model boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import isclose, isfinite
import re
from typing import Any

from .background_mortality import (
    BackgroundMortalityError,
    validate_background_mortality_mappings,
)
from .probability_time import (
    ProbabilityTimeError,
    validate_probability_time_mappings,
)
from .relative_effect import RelativeEffectError, validate_relative_effect_mappings
from .survival_curves import SurvivalCurveError, validate_survival_curve_mappings
from .transition_rates import TransitionRateError, validate_transition_rate_mappings


SCHEMA_VERSION = "0.10.0"
PREVIOUS_MULTI_STRATEGY_SCHEMA_VERSION = "0.9.0"
PRIOR_MULTI_STRATEGY_SCHEMA_VERSION = "0.8.0"
MULTI_STRATEGY_SCHEMA_VERSIONS = {
    PRIOR_MULTI_STRATEGY_SCHEMA_VERSION,
    PREVIOUS_MULTI_STRATEGY_SCHEMA_VERSION,
    SCHEMA_VERSION,
}
PROBABILITY_TIME_SCHEMA_VERSION = "0.7.0"
SURVIVAL_SCHEMA_VERSION = "0.6.0"
TRANSITION_RATE_SCHEMA_VERSION = "0.5.0"
TRANSITION_SCHEDULE_SCHEMA_VERSION = "0.4.0"
DERIVATION_SCHEMA_VERSION = "0.3.0"
ECONOMIC_BASIS_SCHEMA_VERSION = "0.2.0"
LEGACY_SCHEMA_VERSION = "0.1.0"
SUPPORTED_SCHEMA_VERSIONS = (
    LEGACY_SCHEMA_VERSION,
    ECONOMIC_BASIS_SCHEMA_VERSION,
    DERIVATION_SCHEMA_VERSION,
    TRANSITION_SCHEDULE_SCHEMA_VERSION,
    TRANSITION_RATE_SCHEMA_VERSION,
    SURVIVAL_SCHEMA_VERSION,
    PROBABILITY_TIME_SCHEMA_VERSION,
    PRIOR_MULTI_STRATEGY_SCHEMA_VERSION,
    PREVIOUS_MULTI_STRATEGY_SCHEMA_VERSION,
    SCHEMA_VERSION,
)
ENGINE_VERSION = "0.10.0"
PREVIOUS_MULTI_STRATEGY_ENGINE_VERSION = "0.9.0"
PRIOR_MULTI_STRATEGY_ENGINE_VERSION = "0.8.0"
TOLERANCE = 1e-9
MAX_STRATEGIES = 16
STRATEGY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


class ModelValidationError(ValueError):
    """Raised when an analysis specification violates an explicit contract."""


@dataclass(frozen=True)
class TransitionPhase:
    start_cycle: int
    matrix: tuple[tuple[float, ...], ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any], index: int) -> "TransitionPhase":
        value = _mapping(value, f"transition_schedule[{index}]")
        matrix = value.get("matrix")
        if not isinstance(matrix, (list, tuple)):
            raise ModelValidationError(
                f"transition_schedule[{index}].matrix must be an array"
            )
        return cls(
            start_cycle=_strict_int(
                value.get("start_cycle"),
                f"transition_schedule[{index}].start_cycle",
            ),
            matrix=tuple(_float_tuple(row) for row in matrix),
        )


@dataclass(frozen=True)
class Strategy:
    name: str
    initial_distribution: tuple[float, ...]
    transition_matrix: tuple[tuple[float, ...], ...] | None
    transition_schedule: tuple[TransitionPhase, ...] | None
    state_costs: tuple[float, ...]
    state_utilities: tuple[float, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Strategy":
        value = _mapping(value, "strategy")
        raw_matrix = value.get("transition_matrix")
        raw_schedule = value.get("transition_schedule")
        if raw_matrix is not None and not isinstance(raw_matrix, (list, tuple)):
            raise ModelValidationError("transition_matrix must be an array")
        if raw_schedule is not None and not isinstance(raw_schedule, (list, tuple)):
            raise ModelValidationError("transition_schedule must be an array")
        return cls(
            name=str(value.get("name", "")),
            initial_distribution=_float_tuple(value.get("initial_distribution", [])),
            transition_matrix=(
                None
                if raw_matrix is None
                else tuple(_float_tuple(row) for row in raw_matrix)
            ),
            transition_schedule=(
                None
                if raw_schedule is None
                else tuple(
                    TransitionPhase.from_dict(phase, index)
                    for index, phase in enumerate(raw_schedule)
                )
            ),
            state_costs=_float_tuple(value.get("state_costs", [])),
            state_utilities=_float_tuple(value.get("state_utilities", [])),
        )


@dataclass(frozen=True)
class MarkovSpecification:
    schema_version: str
    analysis_id: str
    reference_case_id: str
    reference_case_status: str
    currency: str | None
    price_year: int | None
    states: tuple[str, ...]
    cycles: int
    cycle_length_years: float
    cost_discount_rate: float
    outcome_discount_rate: float
    half_cycle_correction: bool
    willingness_to_pay: float | None
    strategy_order: tuple[str, ...]
    baseline_strategy_id: str
    strategies: tuple[tuple[str, Strategy], ...]

    @property
    def strategy_map(self) -> dict[str, Strategy]:
        return dict(self.strategies)

    @property
    def comparator(self) -> Strategy:
        """Legacy two-strategy accessor retained for schema 0.1-0.7 callers."""

        return self.strategy_map["comparator"]

    @property
    def intervention(self) -> Strategy:
        """Legacy two-strategy accessor retained for schema 0.1-0.7 callers."""

        return self.strategy_map["intervention"]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MarkovSpecification":
        value = _mapping(value, "analysis")
        if "approvals" in value:
            raise ModelValidationError(
                "approvals are not analysis inputs; desktop workflow authorization is app-owned"
            )
        reference_case = _mapping(value.get("reference_case", {}), "reference_case")
        schema_version = str(value.get("schema_version", ""))
        economic_basis = value.get("economic_basis")
        if schema_version in {
            ECONOMIC_BASIS_SCHEMA_VERSION,
            DERIVATION_SCHEMA_VERSION,
            TRANSITION_SCHEDULE_SCHEMA_VERSION,
            TRANSITION_RATE_SCHEMA_VERSION,
            SURVIVAL_SCHEMA_VERSION,
            PROBABILITY_TIME_SCHEMA_VERSION,
            PRIOR_MULTI_STRATEGY_SCHEMA_VERSION,
            PREVIOUS_MULTI_STRATEGY_SCHEMA_VERSION,
            SCHEMA_VERSION,
        }:
            economic_basis = _mapping(economic_basis, "economic_basis")
            currency = str(economic_basis.get("currency", ""))
            price_year = _strict_int(
                economic_basis.get("price_year"), "economic_basis.price_year"
            )
        else:
            currency = None
            price_year = None
        discount_rates = _mapping(value.get("discount_rates", {}), "discount_rates")
        strategies = _mapping(value.get("strategies", {}), "strategies")
        if schema_version in MULTI_STRATEGY_SCHEMA_VERSIONS:
            raw_order = value.get("strategy_order")
            if not isinstance(raw_order, (list, tuple)):
                raise ModelValidationError("strategy_order must be an array")
            strategy_order = tuple(str(item) for item in raw_order)
            baseline_strategy_id = str(value.get("baseline_strategy_id", ""))
            if set(strategies) != set(strategy_order):
                raise ModelValidationError(
                    "strategies must contain exactly the ids declared by strategy_order"
                )
            parsed_strategies = tuple(
                (strategy_id, Strategy.from_dict(strategies.get(strategy_id, {})))
                for strategy_id in strategy_order
            )
        else:
            if set(strategies) != {"comparator", "intervention"}:
                raise ModelValidationError(
                    "legacy strategies must contain exactly comparator and intervention"
                )
            strategy_order = ("comparator", "intervention")
            baseline_strategy_id = "comparator"
            parsed_strategies = (
                ("comparator", Strategy.from_dict(strategies.get("comparator", {}))),
                ("intervention", Strategy.from_dict(strategies.get("intervention", {}))),
            )
        specification = cls(
            schema_version=schema_version,
            analysis_id=str(value.get("analysis_id", "")),
            reference_case_id=str(reference_case.get("id", "")),
            reference_case_status=str(reference_case.get("status", "")),
            currency=currency,
            price_year=price_year,
            states=tuple(str(state) for state in value.get("states", [])),
            cycles=_strict_int(value.get("cycles"), "cycles"),
            cycle_length_years=_strict_float(
                value.get("cycle_length_years"), "cycle_length_years"
            ),
            cost_discount_rate=_strict_float(
                discount_rates.get("costs"),
                "discount_rates.costs",
            ),
            outcome_discount_rate=_strict_float(
                discount_rates.get("outcomes"),
                "discount_rates.outcomes",
            ),
            half_cycle_correction=_strict_bool(
                value.get("half_cycle_correction"), "half_cycle_correction"
            ),
            willingness_to_pay=(
                None
                if value.get("willingness_to_pay") is None
                else _strict_float(
                    value.get("willingness_to_pay"), "willingness_to_pay"
                )
            ),
            strategy_order=strategy_order,
            baseline_strategy_id=baseline_strategy_id,
            strategies=parsed_strategies,
        )
        specification.validate()
        try:
            validate_transition_rate_mappings(
                value,
                schema_version=schema_version,
                state_count=len(specification.states),
                cycles=specification.cycles,
                cycle_length_years=specification.cycle_length_years,
            )
            validate_survival_curve_mappings(
                value,
                schema_version=schema_version,
                state_count=len(specification.states),
                cycles=specification.cycles,
                cycle_length_years=specification.cycle_length_years,
            )
            validate_probability_time_mappings(
                value,
                schema_version=schema_version,
                state_count=len(specification.states),
                cycles=specification.cycles,
                cycle_length_years=specification.cycle_length_years,
            )
            validate_background_mortality_mappings(
                value,
                schema_version=schema_version,
                state_count=len(specification.states),
                cycles=specification.cycles,
                cycle_length_years=specification.cycle_length_years,
            )
            validate_relative_effect_mappings(
                value,
                schema_version=schema_version,
                state_count=len(specification.states),
                cycles=specification.cycles,
                cycle_length_years=specification.cycle_length_years,
            )
        except (
            TransitionRateError,
            SurvivalCurveError,
            ProbabilityTimeError,
            BackgroundMortalityError,
            RelativeEffectError,
        ) as error:
            raise ModelValidationError(str(error)) from error
        return specification

    def validate(self) -> None:
        if self.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise ModelValidationError(
                "unsupported schema_version "
                f"{self.schema_version!r}; expected one of "
                f"{', '.join(repr(item) for item in SUPPORTED_SCHEMA_VERSIONS)}"
            )
        if self.schema_version != LEGACY_SCHEMA_VERSION:
            if self.currency is None or not (
                len(self.currency) == 3 and self.currency.isascii() and self.currency.isalpha()
                and self.currency.isupper()
            ):
                raise ModelValidationError(
                    "economic_basis.currency must be a three-letter uppercase ISO 4217 code"
                )
            if self.price_year is None or not 1900 <= self.price_year <= 2100:
                raise ModelValidationError(
                    "economic_basis.price_year must be from 1900 to 2100"
                )
        if not self.analysis_id.strip():
            raise ModelValidationError("analysis_id must not be empty")
        if not self.reference_case_id.strip():
            raise ModelValidationError("reference_case.id must not be empty")
        if self.reference_case_status not in {"current", "draft", "custom"}:
            raise ModelValidationError(
                "reference_case.status must be current, draft, or custom"
            )
        if not self.states or len(set(self.states)) != len(self.states):
            raise ModelValidationError("states must be non-empty and unique")
        if self.cycles <= 0:
            raise ModelValidationError("cycles must be greater than zero")
        if self.cycle_length_years <= 0:
            raise ModelValidationError("cycle_length_years must be greater than zero")
        for name, rate in (
            ("cost_discount_rate", self.cost_discount_rate),
            ("outcome_discount_rate", self.outcome_discount_rate),
        ):
            if rate < 0:
                raise ModelValidationError(f"{name} must not be negative")
        if self.willingness_to_pay is not None and self.willingness_to_pay < 0:
            raise ModelValidationError("willingness_to_pay must not be negative")
        strategy_ids = tuple(strategy_id for strategy_id, _ in self.strategies)
        if self.schema_version in MULTI_STRATEGY_SCHEMA_VERSIONS:
            if not 2 <= len(self.strategy_order) <= MAX_STRATEGIES:
                raise ModelValidationError(
                    f"strategy_order must contain from 2 to {MAX_STRATEGIES} strategy ids"
                )
            if len(set(self.strategy_order)) != len(self.strategy_order):
                raise ModelValidationError("strategy_order ids must be unique")
            if any(not STRATEGY_ID_PATTERN.fullmatch(item) for item in self.strategy_order):
                raise ModelValidationError(
                    "strategy ids must start with a lowercase letter and contain only lowercase letters, digits, underscores, or hyphens"
                )
            if self.baseline_strategy_id not in self.strategy_order:
                raise ModelValidationError(
                    "baseline_strategy_id must identify a declared strategy"
                )
            if self.strategy_order[0] != self.baseline_strategy_id:
                raise ModelValidationError(
                    "baseline_strategy_id must be the first strategy_order entry"
                )
            if strategy_ids != self.strategy_order:
                raise ModelValidationError(
                    "strategies must contain exactly the ids declared by strategy_order"
                )
        for role, strategy in self.strategies:
            _validate_strategy(
                role,
                strategy,
                len(self.states),
                self.schema_version,
                self.cycles,
            )
        names = tuple(strategy.name for _, strategy in self.strategies)
        if len(set(names)) != len(names):
            raise ModelValidationError("strategy names must be unique")


@dataclass(frozen=True)
class StrategyResult:
    name: str
    total_cost: float
    total_qaly: float
    net_monetary_benefit: float | None
    occupancy: tuple[tuple[float, ...], ...]
    transition_mode: str
    transition_schedule_start_cycles: tuple[int, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "total_cost": self.total_cost,
            "total_qaly": self.total_qaly,
            "net_monetary_benefit": self.net_monetary_benefit,
            "occupancy": [list(row) for row in self.occupancy],
            "transition_mode": self.transition_mode,
            "transition_schedule_start_cycles": list(
                self.transition_schedule_start_cycles
            ),
        }


@dataclass(frozen=True)
class IncrementalResult:
    delta_cost: float
    delta_qaly: float
    icer: float | None
    incremental_net_monetary_benefit: float | None
    interpretation: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "delta_cost": self.delta_cost,
            "delta_qaly": self.delta_qaly,
            "icer": self.icer,
            "incremental_net_monetary_benefit": self.incremental_net_monetary_benefit,
            "interpretation": self.interpretation,
        }


@dataclass(frozen=True)
class AnalysisResult:
    analysis_id: str
    engine_version: str
    schema_version: str
    reference_case_id: str
    reference_case_status: str
    economic_basis: dict[str, Any] | None
    calculation_classification: str
    warnings: tuple[str, ...]
    strategy_order: tuple[str, ...]
    baseline_strategy_id: str
    strategy_results: tuple[tuple[str, StrategyResult], ...]
    pairwise_vs_baseline: tuple[tuple[str, IncrementalResult], ...]
    fully_incremental_analysis: tuple[dict[str, Any], ...]
    optimal_at_primary_threshold: dict[str, Any] | None

    @property
    def strategy_result_map(self) -> dict[str, StrategyResult]:
        return dict(self.strategy_results)

    @property
    def comparator(self) -> StrategyResult:
        return self.strategy_result_map["comparator"]

    @property
    def intervention(self) -> StrategyResult:
        return self.strategy_result_map["intervention"]

    @property
    def incremental(self) -> IncrementalResult:
        return dict(self.pairwise_vs_baseline)["intervention"]

    def to_dict(self) -> dict[str, Any]:
        common = {
            "analysis_id": self.analysis_id,
            "engine_version": self.engine_version,
            "schema_version": self.schema_version,
            "reference_case": {
                "id": self.reference_case_id,
                "status": self.reference_case_status,
                "compliance_assessed": False,
            },
            "economic_basis": self.economic_basis,
            "calculation_classification": self.calculation_classification,
            "warnings": list(self.warnings),
            "strategies": {
                strategy_id: result.to_dict()
                for strategy_id, result in self.strategy_results
            },
        }
        if self.schema_version not in MULTI_STRATEGY_SCHEMA_VERSIONS:
            common["incremental"] = self.incremental.to_dict()
            return common
        common.update(
            {
                "strategy_order": list(self.strategy_order),
                "baseline_strategy_id": self.baseline_strategy_id,
                "pairwise_vs_baseline": {
                    strategy_id: result.to_dict()
                    for strategy_id, result in self.pairwise_vs_baseline
                },
                "fully_incremental_analysis": [
                    dict(row) for row in self.fully_incremental_analysis
                ],
                "optimal_at_primary_threshold": self.optimal_at_primary_threshold,
            }
        )
        return common


def run_markov(specification: MarkovSpecification) -> AnalysisResult:
    """Run a validated deterministic model.

    Rewards use start-of-cycle occupancy without half-cycle correction. With
    half-cycle correction, rewards use the mean of start- and end-of-cycle
    occupancy and are discounted at the cycle midpoint.
    """

    specification.validate()
    strategy_results = tuple(
        (strategy_id, _run_strategy(specification, strategy))
        for strategy_id, strategy in specification.strategies
    )
    result_map = dict(strategy_results)
    baseline = result_map[specification.baseline_strategy_id]
    pairwise_vs_baseline = tuple(
        (
            strategy_id,
            _incremental(
                baseline,
                result_map[strategy_id],
                specification.willingness_to_pay,
            ),
        )
        for strategy_id in specification.strategy_order
        if strategy_id != specification.baseline_strategy_id
    )
    fully_incremental = _fully_incremental_analysis(
        specification.strategy_order,
        result_map,
        specification.willingness_to_pay,
    )
    optimal = _optimal_at_threshold(
        specification.strategy_order,
        result_map,
        specification.willingness_to_pay,
    )
    warnings = [
        "Workflow authorization is not a calculation-engine responsibility; the desktop must apply verified approval state."
    ]
    if specification.reference_case_status == "draft":
        warnings.append(
            "Draft reference case: this result must not be presented as compliance with current guidance."
        )
    warnings.append(
        "Reference-case compliance has not been assessed by the deterministic engine."
    )
    if specification.schema_version == LEGACY_SCHEMA_VERSION:
        warnings.append(
            "Legacy analysis schema: currency and price-year basis are absent, so monetary results are exploratory and must not be presented with a claimed currency."
        )
    elif specification.schema_version == ECONOMIC_BASIS_SCHEMA_VERSION:
        warnings.append(
            "Prior analysis schema: the economic basis is retained, but evidence-to-model value derivations are not executable, so the desktop must not approve this plan."
        )
    return AnalysisResult(
        analysis_id=specification.analysis_id,
        engine_version=(
            ENGINE_VERSION
            if specification.schema_version == SCHEMA_VERSION
            else PREVIOUS_MULTI_STRATEGY_ENGINE_VERSION
            if specification.schema_version == PREVIOUS_MULTI_STRATEGY_SCHEMA_VERSION
            else PRIOR_MULTI_STRATEGY_ENGINE_VERSION
            if specification.schema_version == PRIOR_MULTI_STRATEGY_SCHEMA_VERSION
            else "0.7.0"
        ),
        schema_version=specification.schema_version,
        reference_case_id=specification.reference_case_id,
        reference_case_status=specification.reference_case_status,
        economic_basis=(
            None
            if specification.currency is None or specification.price_year is None
            else {
                "currency": specification.currency,
                "price_year": specification.price_year,
            }
        ),
        calculation_classification="calculation_only",
        warnings=tuple(warnings),
        strategy_order=specification.strategy_order,
        baseline_strategy_id=specification.baseline_strategy_id,
        strategy_results=strategy_results,
        pairwise_vs_baseline=pairwise_vs_baseline,
        fully_incremental_analysis=fully_incremental,
        optimal_at_primary_threshold=optimal,
    )


def _run_strategy(
    specification: MarkovSpecification, strategy: Strategy
) -> StrategyResult:
    current = strategy.initial_distribution
    occupancy = [current]
    total_cost = 0.0
    total_qaly = 0.0
    for cycle in range(specification.cycles):
        matrix = _transition_matrix_for_cycle(strategy, cycle + 1)
        following = _advance(current, matrix)
        if not isclose(sum(following), 1.0, rel_tol=0.0, abs_tol=TOLERANCE):
            raise ModelValidationError(
                f"{strategy.name}: cohort mass was not conserved in cycle {cycle + 1}"
            )
        if specification.half_cycle_correction:
            reward_occupancy = tuple(
                (start + end) / 2.0 for start, end in zip(current, following)
            )
            discount_time = (cycle + 0.5) * specification.cycle_length_years
        else:
            reward_occupancy = current
            discount_time = cycle * specification.cycle_length_years
        try:
            cycle_cost = (
                sum(
                    probability * reward
                    for probability, reward in zip(
                        reward_occupancy, strategy.state_costs
                    )
                )
                * specification.cycle_length_years
            )
            cycle_qaly = (
                sum(
                    probability * reward
                    for probability, reward in zip(
                        reward_occupancy, strategy.state_utilities
                    )
                )
                * specification.cycle_length_years
            )
            cost_discount = (
                1.0 + specification.cost_discount_rate
            ) ** discount_time
            outcome_discount = (
                1.0 + specification.outcome_discount_rate
            ) ** discount_time
            discounted_cost = cycle_cost / cost_discount
            discounted_qaly = cycle_qaly / outcome_discount
            total_cost += discounted_cost
            total_qaly += discounted_qaly
        except ArithmeticError as error:
            raise ModelValidationError(
                f"{strategy.name}: cycle {cycle + 1} arithmetic overflowed"
            ) from error
        if any(
            not isfinite(value)
            for value in (
                cycle_cost,
                cycle_qaly,
                discount_time,
                cost_discount,
                outcome_discount,
                discounted_cost,
                discounted_qaly,
                total_cost,
                total_qaly,
            )
        ):
            raise ModelValidationError(
                f"{strategy.name}: cycle {cycle + 1} produced a non-finite result"
            )
        current = following
        occupancy.append(current)

    net_monetary_benefit = (
        None
        if specification.willingness_to_pay is None
        else specification.willingness_to_pay * total_qaly - total_cost
    )
    if net_monetary_benefit is not None and not isfinite(net_monetary_benefit):
        raise ModelValidationError(
            f"{strategy.name}: net monetary benefit is not finite"
        )
    return StrategyResult(
        name=strategy.name,
        total_cost=total_cost,
        total_qaly=total_qaly,
        net_monetary_benefit=net_monetary_benefit,
        occupancy=tuple(occupancy),
        transition_mode=(
            "static"
            if strategy.transition_matrix is not None
            else "piecewise_by_model_cycle"
        ),
        transition_schedule_start_cycles=(
            (1,)
            if strategy.transition_schedule is None
            else tuple(phase.start_cycle for phase in strategy.transition_schedule)
        ),
    )


def _incremental(
    comparator: StrategyResult,
    intervention: StrategyResult,
    willingness_to_pay: float | None,
) -> IncrementalResult:
    delta_cost = intervention.total_cost - comparator.total_cost
    delta_qaly = intervention.total_qaly - comparator.total_qaly
    if not isfinite(delta_cost) or not isfinite(delta_qaly):
        raise ModelValidationError("incremental cost and QALY results must be finite")
    if delta_cost < -TOLERANCE and delta_qaly > TOLERANCE:
        interpretation = "dominant"
        icer = None
    elif delta_cost > TOLERANCE and delta_qaly < -TOLERANCE:
        interpretation = "dominated"
        icer = None
    elif abs(delta_qaly) <= TOLERANCE:
        interpretation = "equal_effect"
        icer = None
    else:
        interpretation = "tradeoff"
        icer = delta_cost / delta_qaly
    incremental_nmb = (
        None
        if willingness_to_pay is None
        else willingness_to_pay * delta_qaly - delta_cost
    )
    if icer is not None and not isfinite(icer):
        raise ModelValidationError("the incremental cost-effectiveness ratio is not finite")
    if incremental_nmb is not None and not isfinite(incremental_nmb):
        raise ModelValidationError("incremental net monetary benefit is not finite")
    return IncrementalResult(
        delta_cost=delta_cost,
        delta_qaly=delta_qaly,
        icer=icer,
        incremental_net_monetary_benefit=incremental_nmb,
        interpretation=interpretation,
    )


def _comparison_tolerance(*values: float) -> float:
    return max(TOLERANCE, max((abs(value) for value in values), default=0.0) * 1e-12)


def _fully_incremental_analysis(
    strategy_order: tuple[str, ...],
    results: dict[str, StrategyResult],
    willingness_to_pay: float | None,
) -> tuple[dict[str, Any], ...]:
    """Build a complete incremental cost-effectiveness frontier.

    Strict dominance is evaluated against every strategy. Remaining strategies
    are sorted by effect and iteratively screened for decreasing sequential
    ICERs (extended dominance). Identical points are reported as equivalent and
    the earliest declared strategy is retained, so output does not depend on
    JSON object iteration order.
    """

    declaration_rank = {strategy_id: index for index, strategy_id in enumerate(strategy_order)}
    ordered = sorted(
        strategy_order,
        key=lambda strategy_id: (
            results[strategy_id].total_qaly,
            results[strategy_id].total_cost,
            declaration_rank[strategy_id],
        ),
    )
    status: dict[str, str] = {}
    dominated_by: dict[str, tuple[str, ...]] = {}
    representatives: list[str] = []
    for strategy_id in ordered:
        current = results[strategy_id]
        equivalent = next(
            (
                prior
                for prior in representatives
                if abs(results[prior].total_cost - current.total_cost)
                <= _comparison_tolerance(results[prior].total_cost, current.total_cost)
                and abs(results[prior].total_qaly - current.total_qaly)
                <= _comparison_tolerance(results[prior].total_qaly, current.total_qaly)
            ),
            None,
        )
        if equivalent is not None:
            status[strategy_id] = "equivalent"
            dominated_by[strategy_id] = (equivalent,)
            continue
        representatives.append(strategy_id)

    candidates: list[str] = []
    for strategy_id in representatives:
        current = results[strategy_id]
        dominators: list[str] = []
        for other_id in representatives:
            if other_id == strategy_id:
                continue
            other = results[other_id]
            cost_tolerance = _comparison_tolerance(current.total_cost, other.total_cost)
            qaly_tolerance = _comparison_tolerance(current.total_qaly, other.total_qaly)
            no_more_costly = other.total_cost <= current.total_cost + cost_tolerance
            no_less_effective = other.total_qaly >= current.total_qaly - qaly_tolerance
            strictly_better = (
                other.total_cost < current.total_cost - cost_tolerance
                or other.total_qaly > current.total_qaly + qaly_tolerance
            )
            if no_more_costly and no_less_effective and strictly_better:
                dominators.append(other_id)
        if dominators:
            status[strategy_id] = "strictly_dominated"
            dominated_by[strategy_id] = tuple(
                sorted(dominators, key=declaration_rank.__getitem__)
            )
        else:
            candidates.append(strategy_id)

    frontier: list[str] = []
    for strategy_id in candidates:
        frontier.append(strategy_id)
        while len(frontier) >= 3:
            left_id, middle_id, right_id = frontier[-3:]
            left = results[left_id]
            middle = results[middle_id]
            right = results[right_id]
            left_delta_qaly = middle.total_qaly - left.total_qaly
            right_delta_qaly = right.total_qaly - middle.total_qaly
            if left_delta_qaly <= TOLERANCE or right_delta_qaly <= TOLERANCE:
                raise ModelValidationError(
                    "fully incremental analysis could not establish a strictly increasing effectiveness order"
                )
            left_icer = (middle.total_cost - left.total_cost) / left_delta_qaly
            right_icer = (right.total_cost - middle.total_cost) / right_delta_qaly
            if not isfinite(left_icer) or not isfinite(right_icer):
                raise ModelValidationError(
                    "fully incremental analysis produced a non-finite ICER"
                )
            tolerance = _comparison_tolerance(left_icer, right_icer)
            if left_icer <= right_icer + tolerance:
                break
            status[middle_id] = "extendedly_dominated"
            frontier.pop(-2)

    frontier_set = set(frontier)
    for strategy_id in candidates:
        if strategy_id in frontier_set:
            status[strategy_id] = "frontier"
            continue
        if status.get(strategy_id) != "extendedly_dominated":
            continue
        current_qaly = results[strategy_id].total_qaly
        lower = [
            item for item in frontier if results[item].total_qaly < current_qaly
        ]
        upper = [
            item for item in frontier if results[item].total_qaly > current_qaly
        ]
        if lower and upper:
            dominated_by[strategy_id] = (lower[-1], upper[0])

    frontier_previous = {
        strategy_id: (None if index == 0 else frontier[index - 1])
        for index, strategy_id in enumerate(frontier)
    }
    rows: list[dict[str, Any]] = []
    for rank, strategy_id in enumerate(ordered, start=1):
        result = results[strategy_id]
        compared_with = frontier_previous.get(strategy_id)
        incremental = (
            None
            if compared_with is None
            else _incremental(
                results[compared_with], result, willingness_to_pay
            )
        )
        rows.append(
            {
                "rank_by_effect": rank,
                "strategy_id": strategy_id,
                "strategy_name": result.name,
                "total_cost": result.total_cost,
                "total_qaly": result.total_qaly,
                "net_monetary_benefit": result.net_monetary_benefit,
                "status": status[strategy_id],
                "dominated_by_strategy_ids": list(dominated_by.get(strategy_id, ())),
                "compared_with_strategy_id": compared_with,
                "delta_cost": None if incremental is None else incremental.delta_cost,
                "delta_qaly": None if incremental is None else incremental.delta_qaly,
                "icer": None if incremental is None else incremental.icer,
                "incremental_net_monetary_benefit": (
                    None
                    if incremental is None
                    else incremental.incremental_net_monetary_benefit
                ),
            }
        )
    return tuple(rows)


def _optimal_at_threshold(
    strategy_order: tuple[str, ...],
    results: dict[str, StrategyResult],
    willingness_to_pay: float | None,
) -> dict[str, Any] | None:
    if willingness_to_pay is None:
        return None
    values = {
        strategy_id: willingness_to_pay * result.total_qaly - result.total_cost
        for strategy_id, result in results.items()
    }
    if any(not isfinite(value) for value in values.values()):
        raise ModelValidationError(
            "the primary threshold produced a non-finite net monetary benefit"
        )
    best = max(values.values())
    tolerance = _comparison_tolerance(*values.values())
    optimal = tuple(
        strategy_id
        for strategy_id in strategy_order
        if abs(values[strategy_id] - best) <= tolerance
    )
    return {
        "threshold": willingness_to_pay,
        "strategy_id": optimal[0] if len(optimal) == 1 else None,
        "tied_strategy_ids": list(optimal) if len(optimal) > 1 else [],
        "net_monetary_benefit": best,
    }


def _advance(
    current: tuple[float, ...], matrix: tuple[tuple[float, ...], ...]
) -> tuple[float, ...]:
    return tuple(
        sum(current[row] * matrix[row][column] for row in range(len(current)))
        for column in range(len(current))
    )


def _transition_matrix_for_cycle(
    strategy: Strategy, cycle: int
) -> tuple[tuple[float, ...], ...]:
    if strategy.transition_matrix is not None:
        return strategy.transition_matrix
    if strategy.transition_schedule is None:
        raise ModelValidationError(f"{strategy.name}: no transition definition")
    selected = strategy.transition_schedule[0].matrix
    for phase in strategy.transition_schedule[1:]:
        if phase.start_cycle > cycle:
            break
        selected = phase.matrix
    return selected


def _validate_strategy(
    role: str,
    strategy: Strategy,
    state_count: int,
    schema_version: str,
    cycles: int,
) -> None:
    if not strategy.name.strip():
        raise ModelValidationError(f"{role}.name must not be empty")
    for field_name, values in (
        ("initial_distribution", strategy.initial_distribution),
        ("state_costs", strategy.state_costs),
        ("state_utilities", strategy.state_utilities),
    ):
        if len(values) != state_count:
            raise ModelValidationError(
                f"{role}.{field_name} must contain {state_count} values"
            )
    if schema_version not in {
        TRANSITION_SCHEDULE_SCHEMA_VERSION,
        TRANSITION_RATE_SCHEMA_VERSION,
        SURVIVAL_SCHEMA_VERSION,
        PROBABILITY_TIME_SCHEMA_VERSION,
        PRIOR_MULTI_STRATEGY_SCHEMA_VERSION,
        PREVIOUS_MULTI_STRATEGY_SCHEMA_VERSION,
        SCHEMA_VERSION,
    } and strategy.transition_schedule is not None:
        raise ModelValidationError(
            f"{role}.transition_schedule requires schema_version "
            f"{TRANSITION_SCHEDULE_SCHEMA_VERSION}, {TRANSITION_RATE_SCHEMA_VERSION}, {SURVIVAL_SCHEMA_VERSION}, or {PROBABILITY_TIME_SCHEMA_VERSION}; schema_versions {PRIOR_MULTI_STRATEGY_SCHEMA_VERSION}, {PREVIOUS_MULTI_STRATEGY_SCHEMA_VERSION}, and {SCHEMA_VERSION} are also supported"
        )
    if strategy.transition_matrix is None and strategy.transition_schedule is None:
        raise ModelValidationError(
            f"{role} must define transition_matrix or transition_schedule"
        )
    if strategy.transition_matrix is not None and strategy.transition_schedule is not None:
        raise ModelValidationError(
            f"{role} must define exactly one of transition_matrix or transition_schedule"
        )
    _validate_probability_vector(
        f"{role}.initial_distribution", strategy.initial_distribution
    )
    if strategy.transition_matrix is not None:
        _validate_transition_matrix(
            f"{role}.transition_matrix", strategy.transition_matrix, state_count
        )
    else:
        schedule = strategy.transition_schedule or ()
        if not schedule or len(schedule) > cycles:
            raise ModelValidationError(
                f"{role}.transition_schedule must contain from 1 to {cycles} phases"
            )
        start_cycles = tuple(phase.start_cycle for phase in schedule)
        if start_cycles[0] != 1:
            raise ModelValidationError(
                f"{role}.transition_schedule must start at cycle 1"
            )
        if start_cycles != tuple(sorted(set(start_cycles))):
            raise ModelValidationError(
                f"{role}.transition_schedule start_cycle values must be unique and strictly increasing"
            )
        if start_cycles[-1] > cycles:
            raise ModelValidationError(
                f"{role}.transition_schedule start_cycle must not exceed cycles"
            )
        for index, phase in enumerate(schedule):
            _validate_transition_matrix(
                f"{role}.transition_schedule[{index}].matrix",
                phase.matrix,
                state_count,
            )
    if any(cost < 0 or not isfinite(cost) for cost in strategy.state_costs):
        raise ModelValidationError(
            f"{role}.state_costs must be finite and non-negative"
        )
    if any(
        utility < -1 or utility > 1 or not isfinite(utility)
        for utility in strategy.state_utilities
    ):
        raise ModelValidationError(
            f"{role}.state_utilities must be finite values from -1 to 1"
        )


def _validate_transition_matrix(
    name: str,
    matrix: tuple[tuple[float, ...], ...],
    state_count: int,
) -> None:
    if len(matrix) != state_count:
        raise ModelValidationError(f"{name} must contain {state_count} rows")
    if any(len(row) != state_count for row in matrix):
        raise ModelValidationError(f"{name} rows must contain {state_count} values")
    for row_index, row in enumerate(matrix):
        _validate_probability_vector(f"{name}[{row_index}]", row)


def _validate_probability_vector(name: str, values: tuple[float, ...]) -> None:
    if any(value < 0 or value > 1 or not isfinite(value) for value in values):
        raise ModelValidationError(
            f"{name} must contain finite probabilities from 0 to 1"
        )
    if not isclose(sum(values), 1.0, rel_tol=0.0, abs_tol=TOLERANCE):
        raise ModelValidationError(f"{name} must sum to 1")


def _float_tuple(value: Any) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)):
        raise ModelValidationError("expected an array of numbers")
    return tuple(_strict_float(item, "array item") for item in value)


def _strict_float(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelValidationError(f"{name} must be a number")
    number = float(value)
    if not isfinite(number):
        raise ModelValidationError(f"{name} must be finite")
    return number


def _strict_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ModelValidationError(f"{name} must be an integer")
    return value


def _strict_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ModelValidationError(f"{name} must be a boolean")
    return value


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ModelValidationError(f"{name} must be an object")
    return value
