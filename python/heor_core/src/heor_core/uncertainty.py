"""Reproducible uncertainty analysis for the narrow cohort Markov core.

The module deliberately avoids Python's process-global random state and third-
party numerical libraries. A versioned PCG32 stream makes integer draws bit-
stable; explicit transforms make runs repeatable on one runtime. Supported
platforms must still pass golden tolerance tests because system libm functions
are not promised to be bit-identical.
"""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from math import cos, exp, isclose, isfinite, log, pi, sqrt
from typing import Any

from .model import MarkovSpecification, ModelValidationError, run_markov
from .probability_time import (
    ANALYSIS_SCHEMA_VERSION as PROBABILITY_TIME_ANALYSIS_SCHEMA_VERSION,
    TRANSFORMATION_METHOD as PROBABILITY_TIME_TRANSFORMATION_METHOD,
    TRANSFORMATION_OPERATION as PROBABILITY_TIME_TRANSFORMATION_OPERATION,
    ProbabilityTimeError,
    apply_probability_time_mappings,
)
from .survival_curves import (
    ANALYSIS_SCHEMA_VERSION as SURVIVAL_ANALYSIS_SCHEMA_VERSION,
    TRANSFORMATION_METHOD as SURVIVAL_TRANSFORMATION_METHOD,
    TRANSFORMATION_OPERATION as SURVIVAL_TRANSFORMATION_OPERATION,
    SurvivalCurveError,
    apply_survival_curve_mappings,
)
from .transition_rates import (
    TRANSFORMATION_METHOD,
    TRANSFORMATION_OPERATION,
    TransitionRateError,
    derive_competing_rates,
)


UNCERTAINTY_SCHEMA_VERSION = "0.6.0"
SURVIVAL_UNCERTAINTY_SCHEMA_VERSION = "0.5.0"
CORRELATION_UNCERTAINTY_SCHEMA_VERSION = "0.4.0"
RATE_UNCERTAINTY_SCHEMA_VERSION = "0.3.0"
PRIOR_UNCERTAINTY_SCHEMA_VERSION = "0.2.0"
LEGACY_UNCERTAINTY_SCHEMA_VERSION = "0.1.0"
UNCERTAINTY_ENGINE_VERSION = "0.7.0"
PRNG_ALGORITHM = "pcg32-xsh-rr"
PRNG_VERSION = "1"
MAX_ITERATIONS = 10_000
MAX_PARAMETERS = 256
MAX_CORRELATION_GROUPS = 64
MAX_CORRELATION_GROUP_SIZE = 32
MAX_SCENARIOS = 64
MAX_DECISION_THRESHOLDS = 101
MAX_REJECTION_ATTEMPTS = 10_000


class Pcg32:
    """Small, fixed PCG-XSH-RR implementation with deterministic transforms."""

    _MASK_64 = (1 << 64) - 1
    _MASK_32 = (1 << 32) - 1

    def __init__(self, seed: int, stream: int = 54) -> None:
        self.state = 0
        self.increment = ((stream << 1) | 1) & self._MASK_64
        self._normal_cache: float | None = None
        self.next_u32()
        self.state = (self.state + seed) & self._MASK_64
        self.next_u32()

    def next_u32(self) -> int:
        old_state = self.state
        self.state = (
            old_state * 6364136223846793005 + self.increment
        ) & self._MASK_64
        xor_shifted = (((old_state >> 18) ^ old_state) >> 27) & self._MASK_32
        rotation = old_state >> 59
        return (
            (xor_shifted >> rotation) | (xor_shifted << ((-rotation) & 31))
        ) & self._MASK_32

    def uniform_open(self) -> float:
        return (self.next_u32() + 0.5) / (1 << 32)

    def normal(self) -> float:
        if self._normal_cache is not None:
            value = self._normal_cache
            self._normal_cache = None
            return value
        radius = sqrt(-2.0 * log(self.uniform_open()))
        angle = 2.0 * pi * self.uniform_open()
        self._normal_cache = radius * cos(angle + pi / 2.0)
        return radius * cos(angle)

    def gamma(self, shape: float, scale: float = 1.0) -> float:
        if shape <= 0 or scale <= 0:
            raise ModelValidationError("gamma shape and scale must be positive")
        if shape < 1.0:
            return (
                self.gamma(shape + 1.0, 1.0)
                * self.uniform_open() ** (1.0 / shape)
                * scale
            )
        d = shape - 1.0 / 3.0
        c = 1.0 / sqrt(9.0 * d)
        for _ in range(MAX_REJECTION_ATTEMPTS):
            x = self.normal()
            factor = 1.0 + c * x
            if factor <= 0:
                continue
            v = factor**3
            u = self.uniform_open()
            if u < 1.0 - 0.0331 * x**4 or log(u) < 0.5 * x * x + d * (1 - v + log(v)):
                return d * v * scale
        raise ModelValidationError("gamma sampler exceeded its bounded rejection limit")

    def beta(self, alpha: float, beta: float) -> float:
        left = self.gamma(alpha)
        right = self.gamma(beta)
        return left / (left + right)

    def dirichlet(self, alpha: list[float]) -> list[float]:
        draws = [self.gamma(value) for value in alpha]
        total = sum(draws)
        return [value / total for value in draws]


@dataclass(frozen=True)
class Parameter:
    identifier: str
    label: str
    target: str
    provenance_path: str
    dsa_low: Any
    dsa_high: Any
    dsa_rationale: str
    distribution: dict[str, Any]
    distribution_rationale: str
    basis_ids: tuple[str, ...]
    rate_mapping_index: int | None
    survival_mapping_index: int | None
    probability_mapping_index: int | None


@dataclass(frozen=True)
class CorrelationGroup:
    identifier: str
    parameter_ids: tuple[str, ...]
    scale: str
    method: str
    correlation_matrix: tuple[tuple[float, ...], ...]
    cholesky: tuple[tuple[float, ...], ...]
    basis_ids: tuple[str, ...]
    rationale: str


@dataclass(frozen=True)
class Scenario:
    identifier: str
    label: str
    rationale: str
    replacements: tuple[tuple[str, Any], ...]


@dataclass(frozen=True)
class UncertaintySpecification:
    schema_version: str
    uncertainty_id: str
    analysis_id: str
    status: str
    base_path: str
    base_sha256: str
    seed: int
    iterations: int
    primary_threshold: float
    decision_thresholds: tuple[float, ...]
    threshold_rationale: str
    threshold_source: str
    checkpoints: tuple[int, ...]
    max_probability_mcse: float
    max_probability_drift: float
    independence_rationale: str
    known_omitted_correlations: tuple[str, ...]
    correlation_groups: tuple[CorrelationGroup, ...]
    omitted_parameters: tuple[dict[str, str], ...]
    parameters: tuple[Parameter, ...]
    scenarios: tuple[Scenario, ...]

    @classmethod
    def from_dict(
        cls,
        value: dict[str, Any],
        base_payload: dict[str, Any],
        base_sha256: str,
    ) -> "UncertaintySpecification":
        value = _mapping(value, "uncertainty plan")
        schema_version = str(value.get("schema_version", ""))
        if schema_version not in {
            LEGACY_UNCERTAINTY_SCHEMA_VERSION,
            PRIOR_UNCERTAINTY_SCHEMA_VERSION,
            RATE_UNCERTAINTY_SCHEMA_VERSION,
            CORRELATION_UNCERTAINTY_SCHEMA_VERSION,
            SURVIVAL_UNCERTAINTY_SCHEMA_VERSION,
            UNCERTAINTY_SCHEMA_VERSION,
        }:
            raise ModelValidationError(
                "uncertainty schema_version must be 0.1.0, 0.2.0, 0.3.0, 0.4.0, 0.5.0, or 0.6.0"
            )
        base = _mapping(value.get("base_analysis", {}), "base_analysis")
        psa = _mapping(value.get("probabilistic_analysis", {}), "probabilistic_analysis")
        convergence = _mapping(psa.get("convergence", {}), "probabilistic_analysis.convergence")
        correlation = _mapping(psa.get("correlation_handling", {}), "probabilistic_analysis.correlation_handling")
        primary_threshold = _positive_float(
            base_payload.get("willingness_to_pay"), "willingness_to_pay"
        )
        if schema_version in {
            PRIOR_UNCERTAINTY_SCHEMA_VERSION,
            RATE_UNCERTAINTY_SCHEMA_VERSION,
            CORRELATION_UNCERTAINTY_SCHEMA_VERSION,
            SURVIVAL_UNCERTAINTY_SCHEMA_VERSION,
            UNCERTAINTY_SCHEMA_VERSION,
        }:
            threshold_config = _mapping(
                psa.get("decision_thresholds", {}),
                "probabilistic_analysis.decision_thresholds",
            )
            decision_thresholds = tuple(
                _finite_float(item, "probabilistic_analysis.decision_thresholds.values")
                for item in _array(
                    threshold_config.get("values"),
                    "probabilistic_analysis.decision_thresholds.values",
                )
            )
            threshold_rationale = _nonempty(
                threshold_config.get("rationale"),
                "probabilistic_analysis.decision_thresholds.rationale",
            )
            threshold_source = "declared_grid"
        else:
            if "decision_thresholds" in psa:
                raise ModelValidationError(
                    "decision thresholds require uncertainty schema_version 0.2.0 through 0.6.0"
                )
            decision_thresholds = (primary_threshold,)
            threshold_rationale = (
                "Legacy uncertainty schema: only the analysis-plan primary threshold is evaluated."
            )
            threshold_source = "legacy_primary_only"
        parameters = tuple(
            _parameter(item, index, base_payload, schema_version)
            for index, item in enumerate(_array(value.get("parameters"), "parameters"))
        )
        correlation_groups = _correlation_groups(
            correlation,
            parameters,
            schema_version,
        )
        scenarios = tuple(
            _scenario(item, index, base_payload)
            for index, item in enumerate(
                _array(value.get("structural_scenarios"), "structural_scenarios")
            )
        )
        omitted = tuple(
            {
                "provenance_path": _nonempty(item.get("provenance_path"), "omitted parameter provenance_path"),
                "rationale": _nonempty(item.get("rationale"), "omitted parameter rationale"),
            }
            for item in (
                _mapping(entry, "omitted parameter")
                for entry in _array(psa.get("omitted_parameters"), "probabilistic_analysis.omitted_parameters")
            )
        )
        specification = cls(
            schema_version=schema_version,
            uncertainty_id=_nonempty(value.get("uncertainty_id"), "uncertainty_id"),
            analysis_id=_nonempty(value.get("analysis_id"), "analysis_id"),
            status=_nonempty(value.get("status"), "status"),
            base_path=_nonempty(base.get("path"), "base_analysis.path"),
            base_sha256=_nonempty(base.get("content_sha256"), "base_analysis.content_sha256"),
            seed=_strict_int(value.get("seed"), "seed"),
            iterations=_strict_int(psa.get("iterations"), "probabilistic_analysis.iterations"),
            primary_threshold=primary_threshold,
            decision_thresholds=decision_thresholds,
            threshold_rationale=threshold_rationale,
            threshold_source=threshold_source,
            checkpoints=tuple(
                _strict_int(item, "probabilistic_analysis.convergence.checkpoint")
                for item in _array(convergence.get("checkpoints"), "probabilistic_analysis.convergence.checkpoints")
            ),
            max_probability_mcse=_positive_float(
                convergence.get("max_probability_mcse"),
                "probabilistic_analysis.convergence.max_probability_mcse",
            ),
            max_probability_drift=_positive_float(
                convergence.get("max_probability_drift"),
                "probabilistic_analysis.convergence.max_probability_drift",
            ),
            independence_rationale=_nonempty(
                correlation.get("independence_rationale"),
                "probabilistic_analysis.correlation_handling.independence_rationale",
            ),
            known_omitted_correlations=tuple(
                _nonempty(item, "known omitted correlation")
                for item in _array(
                    correlation.get("known_omitted_correlations"),
                    "probabilistic_analysis.correlation_handling.known_omitted_correlations",
                )
            ),
            correlation_groups=correlation_groups,
            omitted_parameters=omitted,
            parameters=parameters,
            scenarios=scenarios,
        )
        specification.validate(base_payload, base_sha256)
        return specification

    def validate(self, base_payload: dict[str, Any], base_sha256: str) -> None:
        if self.status != "ready_for_human_review":
            raise ModelValidationError("uncertainty plan must be ready_for_human_review")
        if self.analysis_id != base_payload.get("analysis_id"):
            raise ModelValidationError("uncertainty analysis_id does not match the base analysis")
        if self.base_path != "heor/analysis-plan.json":
            raise ModelValidationError("base_analysis.path must be heor/analysis-plan.json")
        if self.base_sha256 != base_sha256:
            raise ModelValidationError("base_analysis hash does not match the current analysis plan")
        if self.seed < 0 or self.seed > (1 << 64) - 1:
            raise ModelValidationError("seed must be an unsigned 64-bit integer")
        if not 1_000 <= self.iterations <= MAX_ITERATIONS:
            raise ModelValidationError(
                f"probabilistic_analysis.iterations must be from 1000 to {MAX_ITERATIONS}"
            )
        if (
            len(self.checkpoints) < 2
            or tuple(sorted(set(self.checkpoints))) != self.checkpoints
            or self.checkpoints[-1] != self.iterations
            or self.checkpoints[0] < 100
        ):
            raise ModelValidationError(
                "convergence checkpoints must be unique increasing values ending at iterations"
            )
        if self.max_probability_mcse > 0.1 or self.max_probability_drift > 0.1:
            raise ModelValidationError("probability convergence thresholds must not exceed 0.1")
        if self.known_omitted_correlations:
            raise ModelValidationError(
                "known omitted parameter correlations must be resolved before review"
            )
        if not self.parameters or len(self.parameters) > MAX_PARAMETERS:
            raise ModelValidationError(
                f"parameters must contain from 1 to {MAX_PARAMETERS} entries"
            )
        if len(self.scenarios) > MAX_SCENARIOS:
            raise ModelValidationError(
                f"structural_scenarios must contain no more than {MAX_SCENARIOS} entries"
            )
        if not self.scenarios:
            raise ModelValidationError("at least one structural scenario is required")
        if len({item.identifier for item in self.parameters}) != len(self.parameters):
            raise ModelValidationError("uncertainty parameter ids must be unique")
        if len({item.target for item in self.parameters}) != len(self.parameters):
            raise ModelValidationError("uncertainty parameter targets must be unique")
        if len({item.identifier for item in self.scenarios}) != len(self.scenarios):
            raise ModelValidationError("structural scenario ids must be unique")
        if base_payload.get("willingness_to_pay") is None:
            raise ModelValidationError(
                "willingness_to_pay is required to estimate cost-effectiveness probability"
            )
        primary_threshold = _positive_float(
            base_payload.get("willingness_to_pay"), "willingness_to_pay"
        )
        expected_count = (
            (2, MAX_DECISION_THRESHOLDS)
            if self.schema_version
            in {
                PRIOR_UNCERTAINTY_SCHEMA_VERSION,
                RATE_UNCERTAINTY_SCHEMA_VERSION,
                CORRELATION_UNCERTAINTY_SCHEMA_VERSION,
                SURVIVAL_UNCERTAINTY_SCHEMA_VERSION,
                UNCERTAINTY_SCHEMA_VERSION,
            }
            else (1, 1)
        )
        if not expected_count[0] <= len(self.decision_thresholds) <= expected_count[1]:
            raise ModelValidationError(
                "decision thresholds must contain from "
                f"{expected_count[0]} to {expected_count[1]} values"
            )
        if any(value < 0.0 for value in self.decision_thresholds):
            raise ModelValidationError("decision thresholds must be non-negative")
        if tuple(sorted(set(self.decision_thresholds))) != self.decision_thresholds:
            raise ModelValidationError("decision thresholds must be unique and strictly increasing")
        if not any(
            isclose(value, primary_threshold, rel_tol=0.0, abs_tol=1e-9)
            for value in self.decision_thresholds
        ):
            raise ModelValidationError(
                "decision thresholds must include the primary willingness_to_pay"
            )


def run_uncertainty(
    base_payload: dict[str, Any],
    base_raw: bytes,
    uncertainty_payload: dict[str, Any],
    uncertainty_raw: bytes,
) -> dict[str, Any]:
    base_sha256 = hashlib.sha256(base_raw).hexdigest()
    uncertainty_sha256 = hashlib.sha256(uncertainty_raw).hexdigest()
    specification = UncertaintySpecification.from_dict(
        uncertainty_payload, base_payload, base_sha256
    )
    base_result = run_markov(MarkovSpecification.from_dict(base_payload))
    deterministic = [_run_dsa(base_payload, item) for item in specification.parameters]
    scenarios = [_run_scenario(base_payload, item) for item in specification.scenarios]
    probabilistic = _run_psa(base_payload, specification)
    return {
        "analysis_id": specification.analysis_id,
        "uncertainty_id": specification.uncertainty_id,
        "engine_version": UNCERTAINTY_ENGINE_VERSION,
        "schema_version": specification.schema_version,
        "base_analysis_sha256": base_sha256,
        "uncertainty_plan_sha256": uncertainty_sha256,
        "prng": {"algorithm": PRNG_ALGORITHM, "version": PRNG_VERSION},
        # JSON consumers such as the desktop webview cannot represent every
        # uint64 exactly as a JavaScript number. Preserve the audit value as text.
        "seed": str(specification.seed),
        "calculation_classification": "calculation_only",
        "economic_basis": base_result.economic_basis,
        "base_case": base_result.incremental.to_dict(),
        "deterministic_analysis": deterministic,
        "probabilistic_analysis": probabilistic,
        "structural_scenarios": scenarios,
        "limitations": [
            "Only parameter uncertainty represented by the declared distributions is sampled.",
            "Declared event-rate parameters are sampled in rate space and deterministically transformed into complete transition inputs for each run.",
            "Declared exponential or Weibull parameters are sampled on their positive parameter scale and the complete survival-derived transition schedule is recomputed for each run.",
            "Cross-parameter dependence is limited to declared Dirichlet simplex rows and evidence-bound lognormal correlation groups; the remaining independence rationale is a human-review item.",
            "A convergence diagnostic describes Monte Carlo error for this run and is not independent model validation.",
            "Per-person EVPI covers only the uncertainty represented in this PSA; "
            "it is not population EVPI, EVPPI, a research-funding recommendation, "
            "or a reimbursement recommendation.",
        ],
    }


def _run_dsa(base_payload: dict[str, Any], parameter: Parameter) -> dict[str, Any]:
    outcomes: dict[str, Any] = {}
    for label, value in (("low", parameter.dsa_low), ("high", parameter.dsa_high)):
        payload = _apply_parameter_values(base_payload, ((parameter, value),))
        result = run_markov(MarkovSpecification.from_dict(payload)).incremental
        outcomes[label] = result.to_dict()
    low_inmb = outcomes["low"]["incremental_net_monetary_benefit"]
    high_inmb = outcomes["high"]["incremental_net_monetary_benefit"]
    return {
        "parameter_id": parameter.identifier,
        "label": parameter.label,
        "target": parameter.target,
        "low_value": parameter.dsa_low,
        "high_value": parameter.dsa_high,
        "low_result": outcomes["low"],
        "high_result": outcomes["high"],
        "incremental_nmb_span": abs(high_inmb - low_inmb),
    }


def _run_scenario(base_payload: dict[str, Any], scenario: Scenario) -> dict[str, Any]:
    payload = copy.deepcopy(base_payload)
    for target, value in scenario.replacements:
        _replace(payload, target, value)
    result = run_markov(MarkovSpecification.from_dict(payload)).incremental
    return {
        "scenario_id": scenario.identifier,
        "label": scenario.label,
        "rationale": scenario.rationale,
        "replacements": [
            {"target": target, "value": value} for target, value in scenario.replacements
        ],
        "result": result.to_dict(),
    }


def _run_psa(
    base_payload: dict[str, Any], specification: UncertaintySpecification
) -> dict[str, Any]:
    rng = Pcg32(specification.seed)
    samples: list[dict[str, Any]] = []
    inmb_values: list[float] = []
    cost_effective = 0
    checkpoints: list[dict[str, Any]] = []
    checkpoint_set = set(specification.checkpoints)
    for iteration in range(1, specification.iterations + 1):
        payload = _apply_parameter_values(
            base_payload,
            _sample_parameter_values(rng, specification),
        )
        result = run_markov(MarkovSpecification.from_dict(payload)).incremental
        inmb = result.incremental_net_monetary_benefit
        if inmb is None:
            raise ModelValidationError("PSA requires incremental net monetary benefit")
        inmb_values.append(inmb)
        if inmb >= 0:
            cost_effective += 1
        samples.append(
            {
                "iteration": iteration,
                "delta_cost": result.delta_cost,
                "delta_qaly": result.delta_qaly,
                "incremental_net_monetary_benefit": inmb,
            }
        )
        if iteration in checkpoint_set:
            probability = cost_effective / iteration
            checkpoints.append(
                {
                    "iterations": iteration,
                    "cost_effective_probability": probability,
                    "probability_mcse": sqrt(probability * (1.0 - probability) / iteration),
                }
            )
    mean_inmb = sum(inmb_values) / len(inmb_values)
    variance = sum((value - mean_inmb) ** 2 for value in inmb_values) / (
        len(inmb_values) - 1
    )
    final = checkpoints[-1]
    probability_drift = abs(
        checkpoints[-1]["cost_effective_probability"]
        - checkpoints[-2]["cost_effective_probability"]
    )
    convergence_passed = (
        final["probability_mcse"] <= specification.max_probability_mcse
        and probability_drift <= specification.max_probability_drift
    )
    decision_uncertainty = _decision_uncertainty(samples, specification)
    return {
        "iterations": specification.iterations,
        "cost_effective_probability": final["cost_effective_probability"],
        "mean_incremental_net_monetary_benefit": mean_inmb,
        "incremental_net_monetary_benefit_mcse": sqrt(variance / len(inmb_values)),
        "convergence": {
            "passed": convergence_passed,
            "probability_drift": probability_drift,
            "max_probability_mcse": specification.max_probability_mcse,
            "max_probability_drift": specification.max_probability_drift,
            "checkpoints": checkpoints,
        },
        "independence_rationale": specification.independence_rationale,
        "correlation_groups": [
            {
                "id": group.identifier,
                "parameter_ids": list(group.parameter_ids),
                "scale": group.scale,
                "method": group.method,
                "correlation_matrix": [list(row) for row in group.correlation_matrix],
                "basis_ids": list(group.basis_ids),
                "rationale": group.rationale,
            }
            for group in specification.correlation_groups
        ],
        "omitted_parameters": list(specification.omitted_parameters),
        "decision_uncertainty": decision_uncertainty,
        "samples": samples,
    }


def _decision_uncertainty(
    samples: list[dict[str, Any]], specification: UncertaintySpecification
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    sample_count = len(samples)
    for threshold in specification.decision_thresholds:
        values = [
            threshold * sample["delta_qaly"] - sample["delta_cost"]
            for sample in samples
        ]
        if any(not isfinite(value) for value in values):
            raise ModelValidationError(
                f"decision threshold {threshold} produced a non-finite net monetary benefit"
            )
        mean = sum(values) / sample_count
        positive = sum(value > 0.0 for value in values)
        negative = sum(value < 0.0 for value in values)
        ties = sample_count - positive - negative
        if mean > 0.0:
            selected_strategy = "intervention"
            ceaf_probability: float | None = positive / sample_count
            losses = [max(0.0, value) - value for value in values]
        elif mean < 0.0:
            selected_strategy = "comparator"
            ceaf_probability = negative / sample_count
            losses = [max(0.0, value) for value in values]
        else:
            selected_strategy = "tie"
            ceaf_probability = None
            losses = [max(0.0, value) for value in values]
        evpi = sum(losses) / sample_count
        loss_variance = sum((value - evpi) ** 2 for value in losses) / (
            sample_count - 1
        )
        intervention_probability = positive / sample_count
        rows.append(
            {
                "threshold": threshold,
                "expected_incremental_net_monetary_benefit": mean,
                "intervention_optimal_probability": intervention_probability,
                "comparator_optimal_probability": negative / sample_count,
                "tie_probability": ties / sample_count,
                "probability_mcse": sqrt(
                    intervention_probability
                    * (1.0 - intervention_probability)
                    / sample_count
                ),
                "strategy_with_highest_expected_net_benefit": selected_strategy,
                "ceaf_probability": ceaf_probability,
                "per_person_evpi": evpi,
                "per_person_evpi_mcse": sqrt(loss_variance / sample_count),
            }
        )
    return {
        "method": "net_monetary_benefit",
        "primary_threshold": specification.primary_threshold,
        "threshold_source": specification.threshold_source,
        "threshold_rationale": specification.threshold_rationale,
        "threshold_results": rows,
        "population_evpi": None,
        "evppi": None,
    }


def _sample(rng: Pcg32, distribution: dict[str, Any]) -> Any:
    kind = distribution["type"]
    try:
        if kind == "beta":
            result: Any = rng.beta(distribution["alpha"], distribution["beta"])
        elif kind == "gamma":
            result = rng.gamma(distribution["shape"], distribution["scale"])
        elif kind == "lognormal":
            result = _lognormal_from_normal(distribution, rng.normal())
        elif kind == "uniform":
            result = distribution["low"] + (
                distribution["high"] - distribution["low"]
            ) * rng.uniform_open()
        elif kind == "dirichlet":
            result = rng.dirichlet(distribution["alpha"])
        else:
            raise ModelValidationError(f"unsupported distribution {kind!r}")
    except ArithmeticError as error:
        raise ModelValidationError(
            f"{kind} sampler encountered a numerical overflow or division failure"
        ) from error
    if isinstance(result, list):
        if (
            not result
            or any(not isfinite(item) or item < 0.0 or item > 1.0 for item in result)
            or abs(sum(result) - 1.0) > 1e-9
        ):
            raise ModelValidationError(f"{kind} sampler returned an invalid simplex")
    elif not isfinite(result):
        raise ModelValidationError(f"{kind} sampler returned a non-finite value")
    return result


def _sample_parameter_values(
    rng: Pcg32,
    specification: UncertaintySpecification,
) -> tuple[tuple[Parameter, Any], ...]:
    parameters = {parameter.identifier: parameter for parameter in specification.parameters}
    correlated_values: dict[str, float] = {}
    for group in specification.correlation_groups:
        independent = [rng.normal() for _ in group.parameter_ids]
        correlated = [
            sum(group.cholesky[row][column] * independent[column] for column in range(row + 1))
            for row in range(len(group.parameter_ids))
        ]
        for parameter_id, normal_value in zip(group.parameter_ids, correlated, strict=True):
            correlated_values[parameter_id] = _lognormal_from_normal(
                parameters[parameter_id].distribution,
                normal_value,
            )
    return tuple(
        (
            parameter,
            correlated_values.get(parameter.identifier)
            if parameter.identifier in correlated_values
            else _sample(rng, parameter.distribution),
        )
        for parameter in specification.parameters
    )


def _lognormal_from_normal(distribution: dict[str, Any], normal_value: float) -> float:
    try:
        result = exp(
            distribution["mu_log"] + distribution["sigma_log"] * normal_value
        )
    except ArithmeticError as error:
        raise ModelValidationError(
            "lognormal sampler encountered a numerical overflow or division failure"
        ) from error
    if not isfinite(result) or result <= 0.0:
        raise ModelValidationError("lognormal sampler returned a non-positive or non-finite value")
    return result


def _correlation_groups(
    correlation: dict[str, Any],
    parameters: tuple[Parameter, ...],
    schema_version: str,
) -> tuple[CorrelationGroup, ...]:
    if schema_version not in {
        CORRELATION_UNCERTAINTY_SCHEMA_VERSION,
        SURVIVAL_UNCERTAINTY_SCHEMA_VERSION,
        UNCERTAINTY_SCHEMA_VERSION,
    }:
        if "groups" in correlation:
            raise ModelValidationError(
                "correlation groups require uncertainty schema_version 0.4.0, 0.5.0, or 0.6.0"
            )
        return ()
    raw_groups = _array(
        correlation.get("groups"),
        "probabilistic_analysis.correlation_handling.groups",
    )
    if len(raw_groups) > MAX_CORRELATION_GROUPS:
        raise ModelValidationError(
            f"correlation groups must contain no more than {MAX_CORRELATION_GROUPS} entries"
        )
    by_id = {parameter.identifier: parameter for parameter in parameters}
    group_ids: set[str] = set()
    grouped_parameters: set[str] = set()
    groups: list[CorrelationGroup] = []
    for index, raw in enumerate(raw_groups):
        label = f"probabilistic_analysis.correlation_handling.groups[{index}]"
        value = _mapping(raw, label)
        allowed_fields = {
            "id",
            "parameter_ids",
            "scale",
            "method",
            "correlation_matrix",
            "basis_ids",
            "rationale",
        }
        unknown = set(value) - allowed_fields
        if unknown:
            raise ModelValidationError(
                f"{label} contains unsupported fields: {', '.join(sorted(unknown))}"
            )
        identifier = _nonempty(value.get("id"), f"{label}.id")
        if identifier in group_ids:
            raise ModelValidationError("correlation group ids must be unique")
        group_ids.add(identifier)
        parameter_ids = tuple(
            _nonempty(item, f"{label}.parameter_ids")
            for item in _array(value.get("parameter_ids"), f"{label}.parameter_ids")
        )
        if (
            not 2 <= len(parameter_ids) <= MAX_CORRELATION_GROUP_SIZE
            or len(set(parameter_ids)) != len(parameter_ids)
        ):
            raise ModelValidationError(
                f"{label}.parameter_ids must contain 2-{MAX_CORRELATION_GROUP_SIZE} unique ids"
            )
        if any(parameter_id not in by_id for parameter_id in parameter_ids):
            raise ModelValidationError(f"{label} references an unknown parameter id")
        if grouped_parameters.intersection(parameter_ids):
            raise ModelValidationError("an uncertainty parameter may belong to only one correlation group")
        grouped_parameters.update(parameter_ids)
        if any(
            by_id[parameter_id].distribution.get("type") != "lognormal"
            for parameter_id in parameter_ids
        ):
            raise ModelValidationError(
                f"{label} supports only scalar lognormal parameter members"
            )
        scale = _nonempty(value.get("scale"), f"{label}.scale")
        method = _nonempty(value.get("method"), f"{label}.method")
        if scale != "log_standard_normal" or method != "cholesky":
            raise ModelValidationError(
                f"{label} requires log_standard_normal scale and cholesky method"
            )
        matrix = _correlation_matrix(
            value.get("correlation_matrix"),
            len(parameter_ids),
            f"{label}.correlation_matrix",
        )
        basis_ids = tuple(
            _nonempty(item, f"{label}.basis_ids")
            for item in _array(value.get("basis_ids"), f"{label}.basis_ids")
        )
        if not basis_ids or len(set(basis_ids)) != len(basis_ids):
            raise ModelValidationError(f"{label}.basis_ids must be non-empty and unique")
        if not all(
            set(basis_ids).issubset(set(by_id[parameter_id].basis_ids))
            for parameter_id in parameter_ids
        ):
            raise ModelValidationError(
                f"{label}.basis_ids must be linked by every member parameter distribution"
            )
        groups.append(
            CorrelationGroup(
                identifier=identifier,
                parameter_ids=parameter_ids,
                scale=scale,
                method=method,
                correlation_matrix=matrix,
                cholesky=_cholesky(matrix, f"{label}.correlation_matrix"),
                basis_ids=basis_ids,
                rationale=_nonempty(value.get("rationale"), f"{label}.rationale"),
            )
        )
    return tuple(groups)


def _correlation_matrix(
    value: Any,
    size: int,
    label: str,
) -> tuple[tuple[float, ...], ...]:
    rows = _array(value, label)
    if len(rows) != size:
        raise ModelValidationError(f"{label} must be a {size} by {size} matrix")
    matrix = tuple(
        tuple(
            _finite_float(item, label)
            for item in _array(row, f"{label}[{row_index}]")
        )
        for row_index, row in enumerate(rows)
    )
    if any(len(row) != size for row in matrix):
        raise ModelValidationError(f"{label} must be a {size} by {size} matrix")
    for row in range(size):
        if not isclose(matrix[row][row], 1.0, rel_tol=0.0, abs_tol=1e-12):
            raise ModelValidationError(f"{label} diagonal must equal 1")
        for column in range(row):
            if not -1.0 < matrix[row][column] < 1.0:
                raise ModelValidationError(
                    f"{label} off-diagonal correlations must be strictly between -1 and 1"
                )
            if not isclose(
                matrix[row][column],
                matrix[column][row],
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                raise ModelValidationError(f"{label} must be symmetric")
    return matrix


def _cholesky(
    matrix: tuple[tuple[float, ...], ...],
    label: str,
) -> tuple[tuple[float, ...], ...]:
    size = len(matrix)
    lower = [[0.0] * size for _ in range(size)]
    for row in range(size):
        for column in range(row + 1):
            remainder = matrix[row][column] - sum(
                lower[row][item] * lower[column][item]
                for item in range(column)
            )
            if row == column:
                if remainder <= 1e-12:
                    raise ModelValidationError(f"{label} must be strictly positive definite")
                lower[row][column] = sqrt(remainder)
            else:
                lower[row][column] = remainder / lower[column][column]
    return tuple(tuple(row) for row in lower)


def _parameter(
    value: Any,
    index: int,
    base_payload: dict[str, Any],
    schema_version: str,
) -> Parameter:
    value = _mapping(value, f"parameters[{index}]")
    dsa = _mapping(value.get("deterministic"), f"parameters[{index}].deterministic")
    psa = _mapping(value.get("probabilistic"), f"parameters[{index}].probabilistic")
    target = _nonempty(value.get("target"), f"parameters[{index}].target")
    base = _resolve(base_payload, target)
    low = copy.deepcopy(dsa.get("low"))
    high = copy.deepcopy(dsa.get("high"))
    rate_mapping_index = _rate_mapping_index(target)
    survival_target = _survival_mapping_parameter(target)
    survival_mapping_index = survival_target[0] if survival_target is not None else None
    probability_mapping_index = _probability_mapping_index(target)
    if rate_mapping_index is not None and schema_version not in {
        RATE_UNCERTAINTY_SCHEMA_VERSION,
        CORRELATION_UNCERTAINTY_SCHEMA_VERSION,
        SURVIVAL_UNCERTAINTY_SCHEMA_VERSION,
        UNCERTAINTY_SCHEMA_VERSION,
    }:
        raise ModelValidationError(
            "event-rate uncertainty requires uncertainty schema_version 0.3.0, 0.4.0, 0.5.0, or 0.6.0"
        )
    if survival_mapping_index is not None and schema_version not in {
        SURVIVAL_UNCERTAINTY_SCHEMA_VERSION,
        UNCERTAINTY_SCHEMA_VERSION,
    }:
        raise ModelValidationError(
            "survival-parameter uncertainty requires uncertainty schema_version 0.5.0 or 0.6.0"
        )
    if probability_mapping_index is not None and schema_version != UNCERTAINTY_SCHEMA_VERSION:
        raise ModelValidationError(
            "probability-time uncertainty requires uncertainty schema_version 0.6.0"
        )
    positive_parameter = rate_mapping_index is not None or survival_mapping_index is not None
    bounded_probability = probability_mapping_index is not None
    _validate_replacement(
        target,
        low,
        base,
        rate_parameter=positive_parameter,
        probability_parameter=bounded_probability,
    )
    _validate_replacement(
        target,
        high,
        base,
        rate_parameter=positive_parameter,
        probability_parameter=bounded_probability,
    )
    distribution = _distribution(
        psa,
        base,
        f"parameters[{index}].probabilistic",
        rate_parameter=positive_parameter,
        probability_parameter=bounded_probability,
    )
    basis_ids = tuple(
        _nonempty(item, f"parameters[{index}].probabilistic.basis_ids")
        for item in _array(
            psa.get("basis_ids"), f"parameters[{index}].probabilistic.basis_ids"
        )
    )
    if not basis_ids:
        raise ModelValidationError(
            f"parameters[{index}].probabilistic.basis_ids must not be empty"
        )
    provenance_path = _nonempty(
        value.get("provenance_path"), f"parameters[{index}].provenance_path"
    )
    if rate_mapping_index is not None:
        _validate_rate_parameter(
            base_payload,
            rate_mapping_index,
            target,
            provenance_path,
            basis_ids,
        )
    elif survival_target is not None:
        _validate_survival_parameter(
            base_payload,
            survival_target[0],
            survival_target[1],
            target,
            provenance_path,
            basis_ids,
        )
    elif probability_mapping_index is not None:
        _validate_probability_parameter(
            base_payload,
            probability_mapping_index,
            target,
            provenance_path,
            basis_ids,
        )
    elif _deterministic_mapping(base_payload, provenance_path):
        raise ModelValidationError(
            f"parameters[{index}] targets a derived transition input; vary an admitted event rate instead"
        )
    if isinstance(base, (int, float)) and not isinstance(base, bool):
        low_number = _finite_float(low, f"parameters[{index}].deterministic.low")
        high_number = _finite_float(high, f"parameters[{index}].deterministic.high")
        if low_number >= high_number or not low_number <= float(base) <= high_number:
            raise ModelValidationError(
                f"parameters[{index}] deterministic bounds must bracket the base value"
            )
    return Parameter(
        identifier=_nonempty(value.get("id"), f"parameters[{index}].id"),
        label=_nonempty(value.get("label"), f"parameters[{index}].label"),
        target=target,
        provenance_path=provenance_path,
        dsa_low=low,
        dsa_high=high,
        dsa_rationale=_nonempty(
            dsa.get("rationale"), f"parameters[{index}].deterministic.rationale"
        ),
        distribution=distribution,
        distribution_rationale=_nonempty(
            psa.get("rationale"), f"parameters[{index}].probabilistic.rationale"
        ),
        basis_ids=basis_ids,
        rate_mapping_index=rate_mapping_index,
        survival_mapping_index=survival_mapping_index,
        probability_mapping_index=probability_mapping_index,
    )


def _distribution(
    value: dict[str, Any],
    base: Any,
    label: str,
    *,
    rate_parameter: bool = False,
    probability_parameter: bool = False,
) -> dict[str, Any]:
    kind = _nonempty(value.get("type"), f"{label}.type")
    if kind == "beta":
        result = {
            "type": kind,
            "alpha": _positive_float(value.get("alpha"), f"{label}.alpha"),
            "beta": _positive_float(value.get("beta"), f"{label}.beta"),
        }
    elif kind == "gamma":
        result = {
            "type": kind,
            "shape": _positive_float(value.get("shape"), f"{label}.shape"),
            "scale": _positive_float(value.get("scale"), f"{label}.scale"),
        }
    elif kind == "lognormal":
        result = {
            "type": kind,
            "mu_log": _finite_float(value.get("mu_log"), f"{label}.mu_log"),
            "sigma_log": _positive_float(value.get("sigma_log"), f"{label}.sigma_log"),
        }
    elif kind == "uniform":
        low = _finite_float(value.get("low"), f"{label}.low")
        high = _finite_float(value.get("high"), f"{label}.high")
        if low >= high:
            raise ModelValidationError(f"{label}.low must be less than high")
        result = {"type": kind, "low": low, "high": high}
    elif kind == "dirichlet":
        alpha = [
            _positive_float(item, f"{label}.alpha")
            for item in _array(value.get("alpha"), f"{label}.alpha")
        ]
        if not isinstance(base, list) or len(alpha) != len(base):
            raise ModelValidationError(
                f"{label}.alpha must match the target simplex length"
            )
        result = {"type": kind, "alpha": alpha}
    else:
        raise ModelValidationError(f"{label}.type is unsupported")
    if isinstance(base, list) != (kind == "dirichlet"):
        raise ModelValidationError(
            f"{label} must use dirichlet for a simplex row and a scalar distribution otherwise"
        )
    if rate_parameter:
        if kind not in {"gamma", "lognormal", "uniform"}:
            raise ModelValidationError(
                f"{label} must use gamma, lognormal, or positive uniform for an event rate"
            )
        if kind == "uniform" and result["low"] <= 0:
            raise ModelValidationError(f"{label}.low must be positive for an event rate")
    if probability_parameter:
        if kind not in {"beta", "uniform"}:
            raise ModelValidationError(
                f"{label} must use beta or bounded uniform for a source probability"
            )
        if kind == "uniform" and not 0 < result["low"] < result["high"] < 1:
            raise ModelValidationError(
                f"{label}.uniform bounds must be strictly between 0 and 1 for a source probability"
            )
    return result


def _apply_parameter_values(
    base_payload: dict[str, Any],
    values: tuple[tuple[Parameter, Any], ...],
) -> dict[str, Any]:
    payload = copy.deepcopy(base_payload)
    affected_rate_mappings: set[int] = set()
    affected_survival_mappings: set[int] = set()
    affected_probability_mappings: set[int] = set()
    for parameter, value in values:
        _replace(payload, parameter.target, value)
        if parameter.rate_mapping_index is not None:
            affected_rate_mappings.add(parameter.rate_mapping_index)
        if parameter.survival_mapping_index is not None:
            affected_survival_mappings.add(parameter.survival_mapping_index)
        if parameter.probability_mapping_index is not None:
            affected_probability_mappings.add(parameter.probability_mapping_index)
    for mapping_index in sorted(affected_rate_mappings):
        mapping = payload["input_provenance"][mapping_index]
        derivation = mapping["derivation"]
        try:
            output, _, _ = derive_competing_rates(
                derivation["transformation"],
                target_path=mapping["path"],
                state_count=len(payload["states"]),
                cycles=payload["cycles"],
                cycle_length_years=payload["cycle_length_years"],
            )
        except (KeyError, TypeError, TransitionRateError) as error:
            raise ModelValidationError(
                f"rate-space uncertainty could not recompute input_provenance[{mapping_index}]"
            ) from error
        _replace_dot_path(payload, mapping["path"], output)
        derivation["model_value"] = copy.deepcopy(output)
    if affected_survival_mappings:
        try:
            apply_survival_curve_mappings(payload, affected_survival_mappings)
        except (KeyError, TypeError, SurvivalCurveError) as error:
            raise ModelValidationError(
                "survival-parameter uncertainty could not recompute the affected transition schedule"
            ) from error
    if affected_probability_mappings:
        try:
            apply_probability_time_mappings(payload, affected_probability_mappings)
        except (KeyError, TypeError, ProbabilityTimeError) as error:
            raise ModelValidationError(
                "probability-time uncertainty could not recompute the affected transition input"
            ) from error
    return payload


def _rate_mapping_index(target: str) -> int | None:
    tokens = _pointer_tokens(target)
    if (
        len(tokens) == 11
        and tokens[0] == "input_provenance"
        and tokens[1].isdigit()
        and tokens[2:5] == ["derivation", "transformation", "phases"]
        and tokens[5].isdigit()
        and tokens[6] == "rows"
        and tokens[7].isdigit()
        and tokens[8] == "events"
        and tokens[9].isdigit()
        and tokens[10] == "rate_per_year"
    ):
        return int(tokens[1])
    return None


def _survival_mapping_parameter(target: str) -> tuple[int, str] | None:
    tokens = _pointer_tokens(target)
    if (
        len(tokens) == 7
        and tokens[0] == "input_provenance"
        and tokens[1].isdigit()
        and tokens[2:5] == ["derivation", "transformation", "parameters"]
        and tokens[5] in {"rate_per_year", "shape", "scale_years"}
        and tokens[6] == "value"
    ):
        return int(tokens[1]), tokens[5]
    return None


def _probability_mapping_index(target: str) -> int | None:
    tokens = _pointer_tokens(target)
    if (
        len(tokens) == 10
        and tokens[0] == "input_provenance"
        and tokens[1].isdigit()
        and tokens[2:5] == ["derivation", "transformation", "phases"]
        and tokens[5].isdigit()
        and tokens[6] == "rows"
        and tokens[7].isdigit()
        and tokens[8] == "event"
        and tokens[9] == "source_probability"
    ):
        return int(tokens[1])
    return None


def _validate_probability_parameter(
    base_payload: dict[str, Any],
    mapping_index: int,
    target: str,
    provenance_path: str,
    basis_ids: tuple[str, ...],
) -> None:
    if base_payload.get("schema_version") != PROBABILITY_TIME_ANALYSIS_SCHEMA_VERSION:
        raise ModelValidationError(
            f"probability-time uncertainty requires analysis schema_version {PROBABILITY_TIME_ANALYSIS_SCHEMA_VERSION}"
        )
    mappings = base_payload.get("input_provenance")
    if not isinstance(mappings, list) or mapping_index >= len(mappings):
        raise ModelValidationError(f"uncertainty target {target!r} does not exist")
    mapping = mappings[mapping_index]
    if not isinstance(mapping, dict) or mapping.get("path") != provenance_path:
        raise ModelValidationError(
            "probability-time uncertainty provenance_path must equal its transformation mapping path"
        )
    derivation = mapping.get("derivation")
    transformation = (
        derivation.get("transformation") if isinstance(derivation, dict) else None
    )
    if (
        not isinstance(derivation, dict)
        or derivation.get("method") != PROBABILITY_TIME_TRANSFORMATION_METHOD
        or not isinstance(transformation, dict)
        or transformation.get("operation") != PROBABILITY_TIME_TRANSFORMATION_OPERATION
    ):
        raise ModelValidationError(
            "probability-time uncertainty requires an admitted single-event transformation"
        )
    event = _resolve(base_payload, target.rsplit("/", 1)[0])
    if not isinstance(event, dict):
        raise ModelValidationError(
            "probability-time uncertainty target must belong to an event"
        )
    source_id = event.get("source_extraction_id")
    assumption_id = event.get("assumption_id")
    expected_basis = (
        source_id
        if isinstance(source_id, str) and source_id.strip()
        else assumption_id
    )
    if not isinstance(expected_basis, str) or tuple(basis_ids) != (expected_basis,):
        raise ModelValidationError(
            "probability-time uncertainty basis_ids must contain exactly the event source extraction or assumption id"
        )


def _validate_survival_parameter(
    base_payload: dict[str, Any],
    mapping_index: int,
    parameter_name: str,
    target: str,
    provenance_path: str,
    basis_ids: tuple[str, ...],
) -> None:
    if base_payload.get("schema_version") != SURVIVAL_ANALYSIS_SCHEMA_VERSION:
        raise ModelValidationError(
            f"survival-parameter uncertainty requires analysis schema_version {SURVIVAL_ANALYSIS_SCHEMA_VERSION}"
        )
    mappings = base_payload.get("input_provenance")
    if not isinstance(mappings, list) or mapping_index >= len(mappings):
        raise ModelValidationError(f"uncertainty target {target!r} does not exist")
    mapping = mappings[mapping_index]
    if not isinstance(mapping, dict) or mapping.get("path") != provenance_path:
        raise ModelValidationError(
            "survival-parameter uncertainty provenance_path must equal its transformation mapping path"
        )
    derivation = mapping.get("derivation")
    transformation = derivation.get("transformation") if isinstance(derivation, dict) else None
    if (
        not isinstance(derivation, dict)
        or derivation.get("method") != SURVIVAL_TRANSFORMATION_METHOD
        or not isinstance(transformation, dict)
        or transformation.get("operation") != SURVIVAL_TRANSFORMATION_OPERATION
    ):
        raise ModelValidationError(
            "survival-parameter uncertainty requires an admitted parametric survival transformation"
        )
    expected = {
        "exponential": {"rate_per_year"},
        "weibull": {"shape", "scale_years"},
    }.get(transformation.get("distribution"))
    if expected is None or parameter_name not in expected:
        raise ModelValidationError(
            "survival-parameter uncertainty target does not match the declared distribution"
        )
    parameter = _resolve(base_payload, target.rsplit("/", 1)[0])
    if not isinstance(parameter, dict):
        raise ModelValidationError("survival-parameter uncertainty target is invalid")
    source_id = parameter.get("source_extraction_id")
    assumption_id = parameter.get("assumption_id")
    expected_basis = source_id if isinstance(source_id, str) and source_id.strip() else assumption_id
    if not isinstance(expected_basis, str) or tuple(basis_ids) != (expected_basis,):
        raise ModelValidationError(
            "survival-parameter uncertainty basis_ids must contain exactly the parameter source extraction or assumption id"
        )


def _validate_rate_parameter(
    base_payload: dict[str, Any],
    mapping_index: int,
    target: str,
    provenance_path: str,
    basis_ids: tuple[str, ...],
) -> None:
    if base_payload.get("schema_version") != "0.5.0":
        raise ModelValidationError(
            "event-rate uncertainty requires analysis schema_version 0.5.0"
        )
    mappings = base_payload.get("input_provenance")
    if not isinstance(mappings, list) or mapping_index >= len(mappings):
        raise ModelValidationError(f"uncertainty target {target!r} does not exist")
    mapping = mappings[mapping_index]
    if not isinstance(mapping, dict) or mapping.get("path") != provenance_path:
        raise ModelValidationError(
            "event-rate uncertainty provenance_path must equal its transformation mapping path"
        )
    derivation = mapping.get("derivation")
    transformation = derivation.get("transformation") if isinstance(derivation, dict) else None
    if (
        not isinstance(derivation, dict)
        or derivation.get("method") != TRANSFORMATION_METHOD
        or not isinstance(transformation, dict)
        or transformation.get("operation") != TRANSFORMATION_OPERATION
    ):
        raise ModelValidationError(
            "event-rate uncertainty requires an admitted constant competing-rate transformation"
        )
    event_pointer = target.rsplit("/", 1)[0]
    event = _resolve(base_payload, event_pointer)
    if not isinstance(event, dict):
        raise ModelValidationError("event-rate uncertainty target must belong to an event")
    source_id = event.get("source_extraction_id")
    assumption_id = event.get("assumption_id")
    expected_basis = (
        source_id
        if isinstance(source_id, str) and source_id.strip()
        else assumption_id
    )
    if not isinstance(expected_basis, str) or tuple(basis_ids) != (expected_basis,):
        raise ModelValidationError(
            "event-rate uncertainty basis_ids must contain exactly the event source extraction or assumption id"
        )


def _deterministic_mapping(base_payload: dict[str, Any], provenance_path: str) -> bool:
    mappings = base_payload.get("input_provenance")
    if not isinstance(mappings, list):
        return False
    return any(
        isinstance(mapping, dict)
        and mapping.get("path") == provenance_path
        and isinstance(mapping.get("derivation"), dict)
        and mapping["derivation"].get("method") == TRANSFORMATION_METHOD
        for mapping in mappings
    )


def _scenario(value: Any, index: int, base_payload: dict[str, Any]) -> Scenario:
    value = _mapping(value, f"structural_scenarios[{index}]")
    replacements: list[tuple[str, Any]] = []
    seen: set[str] = set()
    for replacement_index, raw in enumerate(
        _array(value.get("replacements"), f"structural_scenarios[{index}].replacements")
    ):
        replacement = _mapping(
            raw, f"structural_scenarios[{index}].replacements[{replacement_index}]"
        )
        target = _nonempty(replacement.get("target"), "scenario replacement target")
        if target in seen:
            raise ModelValidationError("scenario replacement targets must be unique")
        seen.add(target)
        base = _resolve(base_payload, target)
        new_value = copy.deepcopy(replacement.get("value"))
        _validate_replacement(target, new_value, base, structural=True)
        replacements.append((target, new_value))
    if not replacements:
        raise ModelValidationError("each structural scenario needs at least one replacement")
    return Scenario(
        identifier=_nonempty(value.get("id"), f"structural_scenarios[{index}].id"),
        label=_nonempty(value.get("label"), f"structural_scenarios[{index}].label"),
        rationale=_nonempty(
            value.get("rationale"), f"structural_scenarios[{index}].rationale"
        ),
        replacements=tuple(replacements),
    )


def _validate_replacement(
    target: str,
    value: Any,
    base: Any,
    structural: bool = False,
    rate_parameter: bool = False,
    probability_parameter: bool = False,
) -> None:
    scalar_prefixes = (
        "/strategies/comparator/state_costs/",
        "/strategies/intervention/state_costs/",
        "/strategies/comparator/state_utilities/",
        "/strategies/intervention/state_utilities/",
    )
    simplex_prefixes = (
        "/strategies/comparator/transition_matrix/",
        "/strategies/intervention/transition_matrix/",
    )
    structural_targets = {
        "/cycles",
        "/cycle_length_years",
        "/discount_rates/costs",
        "/discount_rates/outcomes",
        "/half_cycle_correction",
    }
    scheduled_row = _scheduled_transition_row_target(target)
    scheduled_start = _scheduled_transition_start_target(target)
    allowed = (
        target.startswith(scalar_prefixes + simplex_prefixes)
        or scheduled_row
        or rate_parameter
        or probability_parameter
    )
    if structural:
        allowed = allowed or target in structural_targets or scheduled_start
    if not allowed:
        raise ModelValidationError(f"uncertainty target {target!r} is outside the allowlist")
    if isinstance(base, bool):
        if not isinstance(value, bool):
            raise ModelValidationError(f"replacement for {target} must be a boolean")
    elif isinstance(base, int) and not isinstance(base, bool):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ModelValidationError(f"replacement for {target} must be an integer")
    elif isinstance(base, (int, float)):
        number = _finite_float(value, f"replacement for {target}")
        if rate_parameter and number <= 0:
            raise ModelValidationError(f"replacement for {target} must be positive")
        if probability_parameter and not 0 < number < 1:
            raise ModelValidationError(
                f"replacement for {target} must be strictly between 0 and 1"
            )
    elif isinstance(base, list):
        if not isinstance(value, list) or len(value) != len(base):
            raise ModelValidationError(f"replacement for {target} must match the array length")
        numeric = [_finite_float(item, f"replacement for {target}") for item in value]
        if any(item < 0 or item > 1 for item in numeric) or abs(sum(numeric) - 1.0) > 1e-9:
            raise ModelValidationError(f"replacement for {target} must be a probability simplex")
    else:
        raise ModelValidationError(f"replacement for {target} has an unsupported type")


def _scheduled_transition_row_target(target: str) -> bool:
    tokens = _pointer_tokens(target)
    return (
        len(tokens) == 6
        and tokens[0] == "strategies"
        and tokens[1] in {"comparator", "intervention"}
        and tokens[2] == "transition_schedule"
        and tokens[3].isdigit()
        and tokens[4] == "matrix"
        and tokens[5].isdigit()
    )


def _scheduled_transition_start_target(target: str) -> bool:
    tokens = _pointer_tokens(target)
    return (
        len(tokens) == 5
        and tokens[0] == "strategies"
        and tokens[1] in {"comparator", "intervention"}
        and tokens[2] == "transition_schedule"
        and tokens[3].isdigit()
        and tokens[4] == "start_cycle"
    )


def _replace(value: dict[str, Any], pointer: str, replacement: Any) -> None:
    tokens = _pointer_tokens(pointer)
    current: Any = value
    for token in tokens[:-1]:
        current = current[int(token)] if isinstance(current, list) else current[token]
    last = tokens[-1]
    if isinstance(current, list):
        current[int(last)] = copy.deepcopy(replacement)
    else:
        current[last] = copy.deepcopy(replacement)


def _replace_dot_path(value: dict[str, Any], path: str, replacement: Any) -> None:
    tokens = path.split(".")
    if not tokens or any(not token for token in tokens):
        raise ModelValidationError("rate transformation mapping path is invalid")
    current: Any = value
    try:
        for token in tokens[:-1]:
            current = current[token]
        current[tokens[-1]] = copy.deepcopy(replacement)
    except (KeyError, TypeError) as error:
        raise ModelValidationError(
            f"rate transformation mapping path {path!r} does not exist"
        ) from error


def _resolve(value: dict[str, Any], pointer: str) -> Any:
    current: Any = value
    for token in _pointer_tokens(pointer):
        try:
            current = current[int(token)] if isinstance(current, list) else current[token]
        except (KeyError, IndexError, ValueError, TypeError) as error:
            raise ModelValidationError(f"uncertainty target {pointer!r} does not exist") from error
    return current


def _pointer_tokens(pointer: str) -> list[str]:
    if not pointer.startswith("/") or pointer == "/":
        raise ModelValidationError("uncertainty targets must be non-root JSON Pointers")
    return [token.replace("~1", "/").replace("~0", "~") for token in pointer[1:].split("/")]


def _array(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ModelValidationError(f"{name} must be an array")
    return value


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ModelValidationError(f"{name} must be an object")
    return value


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelValidationError(f"{name} must be a non-empty string")
    return value


def _strict_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ModelValidationError(f"{name} must be an integer")
    return value


def _finite_float(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelValidationError(f"{name} must be a number")
    result = float(value)
    if not isfinite(result):
        raise ModelValidationError(f"{name} must be finite")
    return result


def _positive_float(value: Any, name: str) -> float:
    result = _finite_float(value, name)
    if result <= 0:
        raise ModelValidationError(f"{name} must be positive")
    return result
