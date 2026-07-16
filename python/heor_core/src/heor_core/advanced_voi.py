"""Bounded advanced value-of-information analysis for AI4HEOR.

The engine deliberately separates exact population extrapolation from nested
Monte Carlo. It supports current multi-strategy Markov uncertainty and fixed-
survival component uncertainty. Joint survival draws, correlated study targets,
regression EVPPI, and automatic study design are outside this first contract.
"""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from math import exp, fsum, isfinite, sqrt
from typing import Any, Callable

from .economic_inputs import EconomicSpecification
from .model import MarkovSpecification, ModelValidationError, run_markov
from .partitioned_survival import calculate_partitioned_survival, run_partitioned_survival
from .uncertainty import (
    Pcg32,
    UncertaintySpecification,
    _apply_parameter_values,
    _sample_parameter_values,
)


SCHEMA_VERSION = "0.1.0"
ENGINE_VERSION = "0.1.0"
REPLAY_SCHEMA_VERSION = "0.1.0"
PLAN_PATH = "heor/advanced-voi-plan.json"
RESULT_PATH = "heor/results/advanced-voi.json"
REPLAY_PATH = "heor/results/advanced-voi-replay.json"
SUPPORTED_STANDARD_UNCERTAINTY_SCHEMA = "0.9.0"
SUPPORTED_COMPONENT_UNCERTAINTY_SCHEMA = "0.13.0"
MAX_GROUPS = 8
MAX_GROUP_SIZE = 32
MAX_ANNUAL_POPULATIONS = 30
MAX_SAMPLE_SIZES = 8
MAX_NESTED_EVALUATIONS = 100_000


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ModelValidationError(f"{label} must be an object")
    return value


def _array(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ModelValidationError(f"{label} must be an array")
    return value


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelValidationError(f"{label} must be non-empty text")
    return value


def _number(value: Any, label: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelValidationError(f"{label} must be a number")
    result = float(value)
    if not isfinite(result) or (minimum is not None and result < minimum):
        raise ModelValidationError(f"{label} is outside its supported range")
    return result


def _integer(
    value: Any,
    label: str,
    *,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ModelValidationError(f"{label} must be an integer")
    if not minimum <= value <= maximum:
        raise ModelValidationError(
            f"{label} must be from {minimum} to {maximum}"
        )
    return value


def _binding(value: Any, path: str, raw: bytes, label: str) -> None:
    binding = _object(value, label)
    if set(binding) != {"path", "content_sha256"}:
        raise ModelValidationError(f"{label} must contain only path and content_sha256")
    if binding.get("path") != path:
        raise ModelValidationError(f"{label}.path must be {path}")
    if binding.get("content_sha256") != hashlib.sha256(raw).hexdigest():
        raise ModelValidationError(f"{label} does not bind the current {path} bytes")


def _unique_texts(value: Any, label: str, minimum: int, maximum: int) -> tuple[str, ...]:
    result = tuple(_text(item, label) for item in _array(value, label))
    if not minimum <= len(result) <= maximum or len(set(result)) != len(result):
        raise ModelValidationError(
            f"{label} must contain {minimum} to {maximum} unique values"
        )
    return result


@dataclass(frozen=True)
class PopulationSpecification:
    annual_affected_population: tuple[float, ...]
    discount_rate: float
    basis_ids: tuple[str, ...]
    rationale: str

    @property
    def effective_population(self) -> float:
        return fsum(
            value / ((1.0 + self.discount_rate) ** year)
            for year, value in enumerate(self.annual_affected_population)
        )

    def effective_after_delay(self, delay_years: int) -> float:
        return fsum(
            value / ((1.0 + self.discount_rate) ** year)
            for year, value in enumerate(self.annual_affected_population)
            if year >= delay_years
        )


@dataclass(frozen=True)
class ParameterGroup:
    identifier: str
    label: str
    parameter_ids: tuple[str, ...]
    basis_ids: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class EvppiSpecification:
    seed: int
    outer_iterations: int
    inner_iterations: int
    groups: tuple[ParameterGroup, ...]


@dataclass(frozen=True)
class StudyCost:
    fixed: float
    per_participant: float
    currency: str
    price_year: int
    basis_ids: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class EvsiSpecification:
    seed: int
    target_group_id: str
    target_parameter_id: str
    sampling_standard_deviation: float
    sample_sizes: tuple[int, ...]
    outer_iterations: int
    inner_iterations: int
    study_delay_years: int
    study_cost: StudyCost
    basis_ids: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class AdvancedVoiSpecification:
    voi_id: str
    analysis_id: str
    uncertainty_id: str
    threshold: float
    population: PopulationSpecification
    evppi: EvppiSpecification
    evsi: EvsiSpecification


@dataclass
class EvaluationContext:
    strategy_order: tuple[str, ...]
    parameters: tuple[Any, ...]
    correlation_parameter_groups: tuple[frozenset[str], ...]
    sample: Callable[[Pcg32], tuple[tuple[Any, Any], ...]]
    evaluate: Callable[[tuple[tuple[Any, Any], ...]], tuple[list[float], list[float]]]
    model_input_hashes: dict[str, str]


def _population(value: Any) -> PopulationSpecification:
    population = _object(value, "population")
    if set(population) != {
        "annual_affected_population",
        "discount_rate",
        "basis_ids",
        "rationale",
    }:
        raise ModelValidationError("population fields are invalid")
    annual = tuple(
        _number(item, "annual affected population", minimum=0.0)
        for item in _array(
            population.get("annual_affected_population"),
            "annual_affected_population",
        )
    )
    if not 1 <= len(annual) <= MAX_ANNUAL_POPULATIONS or not any(annual):
        raise ModelValidationError(
            "annual_affected_population must contain 1 to 30 years and at least one affected person"
        )
    discount = _number(population.get("discount_rate"), "population.discount_rate", minimum=0.0)
    if discount > 0.2:
        raise ModelValidationError("population.discount_rate must not exceed 0.2")
    return PopulationSpecification(
        annual,
        discount,
        _unique_texts(population.get("basis_ids"), "population basis_ids", 1, 64),
        _text(population.get("rationale"), "population.rationale"),
    )


def _groups(value: Any) -> tuple[ParameterGroup, ...]:
    groups: list[ParameterGroup] = []
    for index, raw in enumerate(_array(value, "evppi.parameter_groups")):
        group = _object(raw, f"evppi.parameter_groups[{index}]")
        if set(group) != {"id", "label", "parameter_ids", "basis_ids", "rationale"}:
            raise ModelValidationError(f"evppi.parameter_groups[{index}] fields are invalid")
        groups.append(
            ParameterGroup(
                _text(group.get("id"), f"evppi.parameter_groups[{index}].id"),
                _text(group.get("label"), f"evppi.parameter_groups[{index}].label"),
                _unique_texts(
                    group.get("parameter_ids"),
                    f"evppi.parameter_groups[{index}].parameter_ids",
                    1,
                    MAX_GROUP_SIZE,
                ),
                _unique_texts(
                    group.get("basis_ids"),
                    f"evppi.parameter_groups[{index}].basis_ids",
                    1,
                    64,
                ),
                _text(group.get("rationale"), f"evppi.parameter_groups[{index}].rationale"),
            )
        )
    if not 1 <= len(groups) <= MAX_GROUPS:
        raise ModelValidationError("evppi.parameter_groups must contain 1 to 8 groups")
    if len({group.identifier for group in groups}) != len(groups):
        raise ModelValidationError("EVPPI group ids must be unique")
    return tuple(groups)


def _evppi(value: Any) -> EvppiSpecification:
    evppi = _object(value, "evppi")
    if set(evppi) != {"method", "seed", "outer_iterations", "inner_iterations", "parameter_groups"}:
        raise ModelValidationError("evppi fields are invalid")
    if evppi.get("method") != "nested_monte_carlo":
        raise ModelValidationError("evppi.method must be nested_monte_carlo")
    outer = _integer(evppi.get("outer_iterations"), "evppi.outer_iterations", minimum=100, maximum=1_000)
    inner = _integer(evppi.get("inner_iterations"), "evppi.inner_iterations", minimum=20, maximum=500)
    groups = _groups(evppi.get("parameter_groups"))
    if outer * inner * len(groups) > MAX_NESTED_EVALUATIONS:
        raise ModelValidationError("EVPPI nested evaluation budget exceeds 100000 model runs")
    return EvppiSpecification(
        _integer(evppi.get("seed"), "evppi.seed", minimum=0, maximum=(1 << 63) - 1),
        outer,
        inner,
        groups,
    )


def _study_cost(value: Any) -> StudyCost:
    cost = _object(value, "evsi.study_cost")
    if set(cost) != {"fixed", "per_participant", "currency", "price_year", "basis_ids", "rationale"}:
        raise ModelValidationError("evsi.study_cost fields are invalid")
    currency = _text(cost.get("currency"), "evsi.study_cost.currency")
    if len(currency) != 3 or not currency.isalpha() or currency.upper() != currency:
        raise ModelValidationError("evsi.study_cost.currency must be a three-letter uppercase code")
    return StudyCost(
        _number(cost.get("fixed"), "evsi.study_cost.fixed", minimum=0.0),
        _number(cost.get("per_participant"), "evsi.study_cost.per_participant", minimum=0.0),
        currency,
        _integer(cost.get("price_year"), "evsi.study_cost.price_year", minimum=1900, maximum=2200),
        _unique_texts(cost.get("basis_ids"), "evsi.study_cost.basis_ids", 1, 64),
        _text(cost.get("rationale"), "evsi.study_cost.rationale"),
    )


def _evsi(value: Any, population_years: int) -> EvsiSpecification:
    evsi = _object(value, "evsi")
    if set(evsi) != {
        "method",
        "seed",
        "target_group_id",
        "target_parameter_id",
        "sampling_standard_deviation",
        "sample_sizes",
        "outer_iterations",
        "inner_iterations",
        "study_delay_years",
        "study_cost",
        "basis_ids",
        "rationale",
    }:
        raise ModelValidationError("evsi fields are invalid")
    if evsi.get("method") != "normal_normal_nested_monte_carlo":
        raise ModelValidationError("evsi.method must be normal_normal_nested_monte_carlo")
    sample_sizes = tuple(
        _integer(item, "evsi sample size", minimum=2, maximum=100_000)
        for item in _array(evsi.get("sample_sizes"), "evsi.sample_sizes")
    )
    if not 1 <= len(sample_sizes) <= MAX_SAMPLE_SIZES or tuple(sorted(set(sample_sizes))) != sample_sizes:
        raise ModelValidationError("evsi.sample_sizes must contain 1 to 8 unique increasing values")
    outer = _integer(evsi.get("outer_iterations"), "evsi.outer_iterations", minimum=100, maximum=1_000)
    inner = _integer(evsi.get("inner_iterations"), "evsi.inner_iterations", minimum=20, maximum=500)
    if outer * inner * len(sample_sizes) > MAX_NESTED_EVALUATIONS:
        raise ModelValidationError("EVSI nested evaluation budget exceeds 100000 model runs")
    return EvsiSpecification(
        _integer(evsi.get("seed"), "evsi.seed", minimum=0, maximum=(1 << 63) - 1),
        _text(evsi.get("target_group_id"), "evsi.target_group_id"),
        _text(evsi.get("target_parameter_id"), "evsi.target_parameter_id"),
        _number(
            evsi.get("sampling_standard_deviation"),
            "evsi.sampling_standard_deviation",
            minimum=0.0,
        ),
        sample_sizes,
        outer,
        inner,
        _integer(
            evsi.get("study_delay_years"),
            "evsi.study_delay_years",
            minimum=0,
            maximum=population_years - 1,
        ),
        _study_cost(evsi.get("study_cost")),
        _unique_texts(evsi.get("basis_ids"), "evsi.basis_ids", 1, 64),
        _text(evsi.get("rationale"), "evsi.rationale"),
    )


def parse_plan(
    plan: dict[str, Any],
    plan_raw: bytes,
    analysis: dict[str, Any],
    analysis_raw: bytes,
    uncertainty: dict[str, Any],
    uncertainty_raw: bytes,
    uncertainty_result: dict[str, Any],
    uncertainty_result_raw: bytes,
) -> AdvancedVoiSpecification:
    value = _object(plan, "advanced VOI plan")
    if set(value) != {
        "schema_version",
        "voi_id",
        "analysis_id",
        "uncertainty_id",
        "status",
        "bindings",
        "decision_threshold",
        "population",
        "evppi",
        "evsi",
        "limitations",
    }:
        raise ModelValidationError("advanced VOI plan fields are invalid")
    if value.get("schema_version") != SCHEMA_VERSION:
        raise ModelValidationError(f"advanced VOI schema_version must be {SCHEMA_VERSION}")
    if value.get("status") != "ready_for_human_review":
        raise ModelValidationError("advanced VOI plan must be ready_for_human_review")
    if value.get("analysis_id") != analysis.get("analysis_id"):
        raise ModelValidationError("advanced VOI analysis_id does not match the analysis plan")
    if value.get("uncertainty_id") != uncertainty.get("uncertainty_id"):
        raise ModelValidationError("advanced VOI uncertainty_id does not match the uncertainty plan")
    bindings = _object(value.get("bindings"), "bindings")
    if set(bindings) != {"analysis_plan", "uncertainty_plan", "uncertainty_result"}:
        raise ModelValidationError("advanced VOI bindings are invalid")
    _binding(bindings.get("analysis_plan"), "heor/analysis-plan.json", analysis_raw, "analysis_plan binding")
    _binding(bindings.get("uncertainty_plan"), "heor/uncertainty-plan.json", uncertainty_raw, "uncertainty_plan binding")
    _binding(bindings.get("uncertainty_result"), "heor/results/uncertainty.json", uncertainty_result_raw, "uncertainty_result binding")
    if uncertainty_result.get("base_analysis_sha256") != hashlib.sha256(analysis_raw).hexdigest():
        raise ModelValidationError("uncertainty result does not bind the current analysis plan")
    if uncertainty_result.get("uncertainty_plan_sha256") != hashlib.sha256(uncertainty_raw).hexdigest():
        raise ModelValidationError("uncertainty result does not bind the current uncertainty plan")
    if uncertainty_result.get("analysis_id") != analysis.get("analysis_id"):
        raise ModelValidationError("uncertainty result analysis_id does not match")
    probabilistic = _object(uncertainty_result.get("probabilistic_analysis"), "uncertainty result probabilistic_analysis")
    convergence = _object(probabilistic.get("convergence"), "uncertainty result convergence")
    if convergence.get("passed") is not True:
        raise ModelValidationError("advanced VOI requires a converged uncertainty result")
    threshold = _number(value.get("decision_threshold"), "decision_threshold", minimum=0.0)
    if threshold != _number(analysis.get("willingness_to_pay"), "analysis willingness_to_pay", minimum=0.0):
        raise ModelValidationError("advanced VOI decision_threshold must equal the analysis primary threshold")
    decision = _object(probabilistic.get("decision_uncertainty"), "decision_uncertainty")
    primary_rows = [
        row
        for row in _array(decision.get("threshold_results"), "decision threshold_results")
        if isinstance(row, dict) and row.get("threshold") == threshold
    ]
    if len(primary_rows) != 1 or _number(primary_rows[0].get("per_person_evpi"), "primary per_person_evpi", minimum=0.0) < 0:
        raise ModelValidationError("uncertainty result must contain one valid primary-threshold EVPI row")
    limitations = _unique_texts(value.get("limitations"), "limitations", 1, 64)
    required_limitations = {
        "model_and_parameter_scope",
        "population_and_implementation_scope",
        "evppi_nested_monte_carlo_error",
        "evsi_normal_normal_study_model",
        "decision_authority_remains_human",
    }
    if not required_limitations.issubset(set(limitations)):
        raise ModelValidationError("advanced VOI limitations omit required boundary labels")
    population = _population(value.get("population"))
    evppi = _evppi(value.get("evppi"))
    evsi = _evsi(value.get("evsi"), len(population.annual_affected_population))
    group = next((item for item in evppi.groups if item.identifier == evsi.target_group_id), None)
    if group is None or group.parameter_ids != (evsi.target_parameter_id,):
        raise ModelValidationError("EVSI target group must be an EVPPI group containing exactly the target parameter")
    if evsi.sampling_standard_deviation <= 0:
        raise ModelValidationError("EVSI sampling_standard_deviation must be positive")
    return AdvancedVoiSpecification(
        _text(value.get("voi_id"), "voi_id"),
        _text(value.get("analysis_id"), "analysis_id"),
        _text(value.get("uncertainty_id"), "uncertainty_id"),
        threshold,
        population,
        evppi,
        evsi,
    )


def _correlation_closure(
    groups: tuple[ParameterGroup, ...],
    correlation_groups: tuple[frozenset[str], ...],
    parameter_ids: set[str],
) -> None:
    for group in groups:
        selected = set(group.parameter_ids)
        if not selected.issubset(parameter_ids):
            raise ModelValidationError(f"EVPPI group {group.identifier} contains an unknown parameter")
        for correlation in correlation_groups:
            if selected & correlation and not correlation.issubset(selected):
                raise ModelValidationError(
                    f"EVPPI group {group.identifier} splits a declared correlation group"
                )


def standard_context(
    analysis: dict[str, Any],
    analysis_raw: bytes,
    uncertainty: dict[str, Any],
    uncertainty_raw: bytes,
) -> EvaluationContext:
    if uncertainty.get("schema_version") != SUPPORTED_STANDARD_UNCERTAINTY_SCHEMA:
        raise ModelValidationError("advanced VOI standard context requires uncertainty schema 0.9.0")
    specification = UncertaintySpecification.from_dict(
        uncertainty,
        analysis,
        hashlib.sha256(analysis_raw).hexdigest(),
    )
    strategy_order = tuple(analysis.get("strategy_order", ()))
    if len(strategy_order) < 2:
        raise ModelValidationError("advanced VOI requires at least two strategies")

    def sample(rng: Pcg32) -> tuple[tuple[Any, Any], ...]:
        return _sample_parameter_values(rng, specification)

    def evaluate(values: tuple[tuple[Any, Any], ...]) -> tuple[list[float], list[float]]:
        payload = _apply_parameter_values(analysis, values)
        result = run_markov(MarkovSpecification.from_dict(payload)).strategy_result_map
        return (
            [result[strategy].total_cost for strategy in strategy_order],
            [result[strategy].total_qaly for strategy in strategy_order],
        )

    return EvaluationContext(
        strategy_order,
        tuple(specification.parameters),
        tuple(frozenset(group.parameter_ids) for group in specification.correlation_groups),
        sample,
        evaluate,
        {
            "analysis_plan": hashlib.sha256(analysis_raw).hexdigest(),
            "uncertainty_plan": hashlib.sha256(uncertainty_raw).hexdigest(),
        },
    )


def component_context(
    analysis: dict[str, Any],
    analysis_raw: bytes,
    uncertainty: dict[str, Any],
    uncertainty_raw: bytes,
    partitioned_plan: dict[str, Any],
    partitioned_raw: bytes,
    materializations: dict[str, Any],
    materializations_raw: bytes,
    treatment_duration: dict[str, Any],
    treatment_duration_raw: bytes,
    cost_inputs: dict[str, Any],
    cost_inputs_raw: bytes,
    utility_inputs: dict[str, Any],
    utility_inputs_raw: bytes,
    event_inputs: dict[str, Any],
    event_inputs_raw: bytes,
) -> EvaluationContext:
    if uncertainty.get("schema_version") != SUPPORTED_COMPONENT_UNCERTAINTY_SCHEMA:
        raise ModelValidationError("advanced VOI component context requires uncertainty schema 0.13.0")
    from .component_uncertainty import _parse, _recompute, _replace, _sample_values

    artifacts = {
        "cost_input_normalization": cost_inputs,
        "utility_inputs": utility_inputs,
        "event_disutilities": event_inputs,
    }
    raw_inputs = {
        "partitioned_survival_plan": partitioned_raw,
        "curve_materializations": materializations_raw,
        "treatment_effect_duration": treatment_duration_raw,
        "cost_input_normalization": cost_inputs_raw,
        "utility_inputs": utility_inputs_raw,
        "event_disutilities": event_inputs_raw,
    }
    specification = _parse(uncertainty, analysis, analysis_raw, artifacts, raw_inputs)
    run_partitioned_survival(
        analysis,
        analysis_raw,
        partitioned_plan,
        partitioned_raw,
        materializations,
        materializations_raw,
        treatment_duration,
        treatment_duration_raw,
        cost_inputs,
        cost_inputs_raw,
        utility_inputs,
        utility_inputs_raw,
        event_inputs,
        event_inputs_raw,
    )
    strategy_order = tuple(analysis["strategy_order"])

    def sample(rng: Pcg32) -> tuple[tuple[Any, Any], ...]:
        return _sample_values(rng, specification)

    def evaluate(values: tuple[tuple[Any, Any], ...]) -> tuple[list[float], list[float]]:
        sampled_analysis = copy.deepcopy(analysis)
        sampled_artifacts = {key: copy.deepcopy(value) for key, value in artifacts.items()}
        for parameter, parameter_value in values:
            _replace(sampled_artifacts[parameter.artifact], parameter.target, parameter_value)
        utility_schedule, event_schedule = _recompute(
            sampled_analysis,
            sampled_artifacts["cost_input_normalization"],
            sampled_artifacts["utility_inputs"],
            sampled_artifacts["event_disutilities"],
        )
        result = calculate_partitioned_survival(
            EconomicSpecification.from_analysis_plan(sampled_analysis),
            partitioned_plan,
            utility_schedule,
            event_schedule,
        )
        return (
            [result["strategies"][strategy]["total_cost"] for strategy in strategy_order],
            [result["strategies"][strategy]["total_qaly"] for strategy in strategy_order],
        )

    return EvaluationContext(
        strategy_order,
        tuple(specification.parameters),
        tuple(frozenset(group.parameter_ids) for group in specification.correlation_groups),
        sample,
        evaluate,
        {
            "analysis_plan": hashlib.sha256(analysis_raw).hexdigest(),
            "uncertainty_plan": hashlib.sha256(uncertainty_raw).hexdigest(),
            "partitioned_survival_plan": hashlib.sha256(partitioned_raw).hexdigest(),
            "curve_materializations": hashlib.sha256(materializations_raw).hexdigest(),
            "treatment_effect_duration": hashlib.sha256(treatment_duration_raw).hexdigest(),
            "cost_input_normalization": hashlib.sha256(cost_inputs_raw).hexdigest(),
            "utility_inputs": hashlib.sha256(utility_inputs_raw).hexdigest(),
            "event_disutilities": hashlib.sha256(event_inputs_raw).hexdigest(),
        },
    )


def _nmb(costs: list[float], qalys: list[float], threshold: float) -> list[float]:
    values = [threshold * qaly - cost for cost, qaly in zip(costs, qalys)]
    if not values or any(not isfinite(value) for value in values):
        raise ModelValidationError("advanced VOI model evaluation produced invalid net benefit")
    return values


def _combine_values(
    outer: tuple[tuple[Any, Any], ...],
    inner: tuple[tuple[Any, Any], ...],
    frozen_ids: set[str],
) -> tuple[tuple[Any, Any], ...]:
    outer_values = {parameter.identifier: value for parameter, value in outer}
    return tuple(
        (parameter, outer_values[parameter.identifier] if parameter.identifier in frozen_ids else value)
        for parameter, value in inner
    )


def _conditional_rows(
    context: EvaluationContext,
    threshold: float,
    seed: int,
    stream: int,
    outer_iterations: int,
    inner_iterations: int,
    frozen_ids: set[str],
) -> list[dict[str, Any]]:
    rng = Pcg32(seed, stream=stream)
    rows: list[dict[str, Any]] = []
    for outer_iteration in range(1, outer_iterations + 1):
        outer = context.sample(rng)
        totals = [0.0] * len(context.strategy_order)
        for _ in range(inner_iterations):
            values = _combine_values(outer, context.sample(rng), frozen_ids)
            costs, qalys = context.evaluate(values)
            for index, value in enumerate(_nmb(costs, qalys, threshold)):
                totals[index] += value
        rows.append(
            {
                "iteration": outer_iteration,
                "expected_nmb_by_strategy": {
                    strategy: totals[index] / inner_iterations
                    for index, strategy in enumerate(context.strategy_order)
                },
            }
        )
    return rows


def summarize_conditional_rows(
    rows: list[dict[str, Any]], strategy_order: tuple[str, ...]
) -> dict[str, Any]:
    if len(rows) < 2:
        raise ModelValidationError("advanced VOI replay requires at least two outer rows")
    expected = {
        strategy: fsum(row["expected_nmb_by_strategy"][strategy] for row in rows) / len(rows)
        for strategy in strategy_order
    }
    current = max(strategy_order, key=expected.__getitem__)
    gains = [
        max(row["expected_nmb_by_strategy"].values())
        - row["expected_nmb_by_strategy"][current]
        for row in rows
    ]
    mean = fsum(gains) / len(gains)
    variance = fsum((value - mean) ** 2 for value in gains) / (len(gains) - 1)
    return {
        "current_strategy": current,
        "expected_nmb_by_strategy": expected,
        "per_person_value": mean,
        "per_person_value_mcse": sqrt(variance / len(gains)),
    }


def _lognormal_prior(parameter: Any) -> tuple[float, float]:
    distribution = parameter.distribution
    if distribution.get("type") != "lognormal":
        raise ModelValidationError("EVSI target parameter must use a Lognormal PSA distribution")
    return (
        _number(distribution.get("mu_log"), "EVSI target mu_log"),
        _number(distribution.get("sigma_log"), "EVSI target sigma_log", minimum=0.0),
    )


def _evsi_rows(
    context: EvaluationContext,
    specification: AdvancedVoiSpecification,
    target_parameter: Any,
    sample_size: int,
    stream: int,
) -> list[dict[str, Any]]:
    prior_mean, prior_sd = _lognormal_prior(target_parameter)
    if prior_sd <= 0:
        raise ModelValidationError("EVSI target sigma_log must be positive")
    observation_sd = specification.evsi.sampling_standard_deviation
    posterior_variance = 1.0 / (1.0 / (prior_sd * prior_sd) + sample_size / (observation_sd * observation_sd))
    posterior_sd = sqrt(posterior_variance)
    rng = Pcg32(specification.evsi.seed, stream=stream)
    rows: list[dict[str, Any]] = []
    for outer_iteration in range(1, specification.evsi.outer_iterations + 1):
        true_log = prior_mean + prior_sd * rng.normal()
        sample_mean = true_log + observation_sd / sqrt(sample_size) * rng.normal()
        posterior_mean = posterior_variance * (
            prior_mean / (prior_sd * prior_sd)
            + sample_size * sample_mean / (observation_sd * observation_sd)
        )
        totals = [0.0] * len(context.strategy_order)
        for _ in range(specification.evsi.inner_iterations):
            prior_values = context.sample(rng)
            values = tuple(
                (
                    parameter,
                    exp(posterior_mean + posterior_sd * rng.normal())
                    if parameter.identifier == target_parameter.identifier
                    else value,
                )
                for parameter, value in prior_values
            )
            costs, qalys = context.evaluate(values)
            for index, value in enumerate(_nmb(costs, qalys, specification.threshold)):
                totals[index] += value
        rows.append(
            {
                "iteration": outer_iteration,
                "expected_nmb_by_strategy": {
                    strategy: totals[index] / specification.evsi.inner_iterations
                    for index, strategy in enumerate(context.strategy_order)
                },
            }
        )
    return rows


def _primary_evpi(result: dict[str, Any], threshold: float) -> tuple[float, float]:
    rows = result["probabilistic_analysis"]["decision_uncertainty"]["threshold_results"]
    row = next(item for item in rows if item["threshold"] == threshold)
    return float(row["per_person_evpi"]), float(row["per_person_evpi_mcse"])


def validate_context(
    specification: AdvancedVoiSpecification,
    context: EvaluationContext,
) -> Any:
    """Validate parameter identities, correlation closure, and EVSI target scope."""
    parameter_ids = {parameter.identifier for parameter in context.parameters}
    _correlation_closure(
        specification.evppi.groups,
        context.correlation_parameter_groups,
        parameter_ids,
    )
    target = next(
        (
            parameter
            for parameter in context.parameters
            if parameter.identifier == specification.evsi.target_parameter_id
        ),
        None,
    )
    if target is None:
        raise ModelValidationError("EVSI target parameter is absent from the uncertainty plan")
    if any(target.identifier in group for group in context.correlation_parameter_groups):
        raise ModelValidationError("EVSI target parameter must be independent of declared correlation groups")
    _lognormal_prior(target)
    return target


def run_advanced_voi(
    plan: dict[str, Any],
    plan_raw: bytes,
    analysis: dict[str, Any],
    analysis_raw: bytes,
    uncertainty: dict[str, Any],
    uncertainty_raw: bytes,
    uncertainty_result: dict[str, Any],
    uncertainty_result_raw: bytes,
    context: EvaluationContext,
) -> dict[str, Any]:
    specification = parse_plan(
        plan,
        plan_raw,
        analysis,
        analysis_raw,
        uncertainty,
        uncertainty_raw,
        uncertainty_result,
        uncertainty_result_raw,
    )
    target = validate_context(specification, context)

    evppi_replay = []
    evppi_results = []
    for index, group in enumerate(specification.evppi.groups, start=1):
        rows = _conditional_rows(
            context,
            specification.threshold,
            specification.evppi.seed,
            100 + index,
            specification.evppi.outer_iterations,
            specification.evppi.inner_iterations,
            set(group.parameter_ids),
        )
        summary = summarize_conditional_rows(rows, context.strategy_order)
        evppi_replay.append(
            {
                "group_id": group.identifier,
                "parameter_ids": list(group.parameter_ids),
                "stream": 100 + index,
                "rows": rows,
            }
        )
        evppi_results.append(
            {
                "group_id": group.identifier,
                "label": group.label,
                "parameter_ids": list(group.parameter_ids),
                "per_person_evppi": summary["per_person_value"],
                "per_person_evppi_mcse": summary["per_person_value_mcse"],
                "population_evppi": summary["per_person_value"]
                * specification.population.effective_population,
            }
        )

    research_population = specification.population.effective_after_delay(
        specification.evsi.study_delay_years
    )
    evsi_replay = []
    evsi_results = []
    for index, sample_size in enumerate(specification.evsi.sample_sizes, start=1):
        rows = _evsi_rows(context, specification, target, sample_size, 200 + index)
        summary = summarize_conditional_rows(rows, context.strategy_order)
        population_evsi = summary["per_person_value"] * research_population
        study_cost = (
            specification.evsi.study_cost.fixed
            + specification.evsi.study_cost.per_participant * sample_size
        )
        evsi_replay.append(
            {
                "sample_size": sample_size,
                "stream": 200 + index,
                "posterior_sigma_log": sqrt(
                    1.0
                    / (
                        1.0 / (_lognormal_prior(target)[1] ** 2)
                        + sample_size
                        / (specification.evsi.sampling_standard_deviation**2)
                    )
                ),
                "rows": rows,
            }
        )
        evsi_results.append(
            {
                "sample_size": sample_size,
                "per_person_evsi": summary["per_person_value"],
                "per_person_evsi_mcse": summary["per_person_value_mcse"],
                "research_effective_population": research_population,
                "population_evsi": population_evsi,
                "study_cost": study_cost,
                "expected_net_benefit_of_sampling": population_evsi - study_cost,
            }
        )

    evpi, evpi_mcse = _primary_evpi(uncertainty_result, specification.threshold)
    replay = {
        "schema_version": REPLAY_SCHEMA_VERSION,
        "voi_id": specification.voi_id,
        "advanced_voi_plan_sha256": hashlib.sha256(plan_raw).hexdigest(),
        "model_input_hashes": context.model_input_hashes,
        "strategy_order": list(context.strategy_order),
        "decision_threshold": specification.threshold,
        "evppi": {
            "method": "nested_monte_carlo",
            "seed": specification.evppi.seed,
            "outer_iterations": specification.evppi.outer_iterations,
            "inner_iterations": specification.evppi.inner_iterations,
            "groups": evppi_replay,
        },
        "evsi": {
            "method": "normal_normal_nested_monte_carlo",
            "seed": specification.evsi.seed,
            "target_parameter_id": target.identifier,
            "prior_mu_log": _lognormal_prior(target)[0],
            "prior_sigma_log": _lognormal_prior(target)[1],
            "sampling_standard_deviation": specification.evsi.sampling_standard_deviation,
            "outer_iterations": specification.evsi.outer_iterations,
            "inner_iterations": specification.evsi.inner_iterations,
            "designs": evsi_replay,
        },
    }
    result = {
        "schema_version": SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "voi_id": specification.voi_id,
        "analysis_id": specification.analysis_id,
        "uncertainty_id": specification.uncertainty_id,
        "advanced_voi_plan_sha256": hashlib.sha256(plan_raw).hexdigest(),
        "uncertainty_result_sha256": hashlib.sha256(uncertainty_result_raw).hexdigest(),
        "replay_sha256": "",
        "decision_threshold": specification.threshold,
        "strategy_order": list(context.strategy_order),
        "population": {
            "annual_affected_population": list(specification.population.annual_affected_population),
            "discount_rate": specification.population.discount_rate,
            "effective_population": specification.population.effective_population,
        },
        "population_evpi": {
            "per_person_evpi": evpi,
            "per_person_evpi_mcse": evpi_mcse,
            "population_evpi": evpi * specification.population.effective_population,
            "population_evpi_mcse": evpi_mcse * specification.population.effective_population,
        },
        "evppi": evppi_results,
        "evsi": {
            "target_group_id": specification.evsi.target_group_id,
            "target_parameter_id": specification.evsi.target_parameter_id,
            "study_delay_years": specification.evsi.study_delay_years,
            "study_cost_basis": {
                "currency": specification.evsi.study_cost.currency,
                "price_year": specification.evsi.study_cost.price_year,
            },
            "designs": evsi_results,
        },
        "classification": "research_priority_calculation_for_human_review",
        "limitations": [
            "Values are conditional on the bound model, PSA distributions, represented parameters, and current structural assumptions.",
            "Nested Monte Carlo error is reported but does not establish convergence or unbiased EVPPI/EVSI.",
            "EVSI uses only the declared Normal sampling model for one independent Lognormal parameter on its log scale.",
            "ENBS is not a funding decision, optimal design, reimbursement recommendation, or scientific-validity judgment.",
        ],
    }
    replay_raw = (json_bytes(replay))
    result["replay_sha256"] = hashlib.sha256(replay_raw).hexdigest()
    return {"replay": replay, "result": result}


def json_bytes(value: Any) -> bytes:
    import json

    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def verify_result_from_replay(
    plan: dict[str, Any],
    result: dict[str, Any],
    replay: dict[str, Any],
    replay_raw: bytes,
) -> None:
    if result.get("replay_sha256") != hashlib.sha256(replay_raw).hexdigest():
        raise ModelValidationError("advanced VOI result does not bind the replay bytes")
    strategy_order = tuple(_unique_texts(replay.get("strategy_order"), "replay strategy_order", 2, 32))
    population = _population(plan.get("population"))
    expected_evppi = []
    replay_evppi = _object(replay.get("evppi"), "replay.evppi")
    for group in _array(replay_evppi.get("groups"), "replay EVPPI groups"):
        group = _object(group, "replay EVPPI group")
        summary = summarize_conditional_rows(_array(group.get("rows"), "EVPPI rows"), strategy_order)
        expected_evppi.append(
            {
                "group_id": group["group_id"],
                "parameter_ids": group["parameter_ids"],
                "per_person_evppi": summary["per_person_value"],
                "per_person_evppi_mcse": summary["per_person_value_mcse"],
                "population_evppi": summary["per_person_value"] * population.effective_population,
            }
        )
    actual_by_group = {row["group_id"]: row for row in result.get("evppi", [])}
    for expected in expected_evppi:
        actual = actual_by_group.get(expected["group_id"])
        if actual is None or actual.get("parameter_ids") != expected["parameter_ids"]:
            raise ModelValidationError("advanced VOI EVPPI result/replay identity differs")
        for field in ("per_person_evppi", "per_person_evppi_mcse", "population_evppi"):
            if abs(float(actual[field]) - float(expected[field])) > 1e-9 * max(1.0, abs(float(expected[field]))):
                raise ModelValidationError(f"advanced VOI EVPPI {field} differs from replay")
    evsi_plan = _evsi(plan.get("evsi"), len(population.annual_affected_population))
    research_population = population.effective_after_delay(evsi_plan.study_delay_years)
    actual_by_size = {row["sample_size"]: row for row in result["evsi"]["designs"]}
    for design in _array(_object(replay.get("evsi"), "replay.evsi").get("designs"), "replay EVSI designs"):
        design = _object(design, "replay EVSI design")
        sample_size = design["sample_size"]
        summary = summarize_conditional_rows(_array(design.get("rows"), "EVSI rows"), strategy_order)
        actual = actual_by_size.get(sample_size)
        if actual is None:
            raise ModelValidationError("advanced VOI EVSI result omits a replay design")
        population_evsi = summary["per_person_value"] * research_population
        study_cost = evsi_plan.study_cost.fixed + evsi_plan.study_cost.per_participant * sample_size
        expected = {
            "per_person_evsi": summary["per_person_value"],
            "per_person_evsi_mcse": summary["per_person_value_mcse"],
            "research_effective_population": research_population,
            "population_evsi": population_evsi,
            "study_cost": study_cost,
            "expected_net_benefit_of_sampling": population_evsi - study_cost,
        }
        for field, value in expected.items():
            if abs(float(actual[field]) - value) > 1e-9 * max(1.0, abs(value)):
                raise ModelValidationError(f"advanced VOI EVSI {field} differs from replay")
