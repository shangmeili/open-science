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


UNCERTAINTY_SCHEMA_VERSION = "0.2.0"
LEGACY_UNCERTAINTY_SCHEMA_VERSION = "0.1.0"
UNCERTAINTY_ENGINE_VERSION = "0.2.0"
PRNG_ALGORITHM = "pcg32-xsh-rr"
PRNG_VERSION = "1"
MAX_ITERATIONS = 10_000
MAX_PARAMETERS = 256
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
            UNCERTAINTY_SCHEMA_VERSION,
        }:
            raise ModelValidationError(
                "uncertainty schema_version must be 0.1.0 or 0.2.0"
            )
        base = _mapping(value.get("base_analysis", {}), "base_analysis")
        psa = _mapping(value.get("probabilistic_analysis", {}), "probabilistic_analysis")
        convergence = _mapping(psa.get("convergence", {}), "probabilistic_analysis.convergence")
        correlation = _mapping(psa.get("correlation_handling", {}), "probabilistic_analysis.correlation_handling")
        primary_threshold = _positive_float(
            base_payload.get("willingness_to_pay"), "willingness_to_pay"
        )
        if schema_version == UNCERTAINTY_SCHEMA_VERSION:
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
                    "decision thresholds require uncertainty schema_version 0.2.0"
                )
            decision_thresholds = (primary_threshold,)
            threshold_rationale = (
                "Legacy uncertainty schema: only the analysis-plan primary threshold is evaluated."
            )
            threshold_source = "legacy_primary_only"
        parameters = tuple(
            _parameter(item, index, base_payload)
            for index, item in enumerate(_array(value.get("parameters"), "parameters"))
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
            if self.schema_version == UNCERTAINTY_SCHEMA_VERSION
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
            "Cross-parameter dependence is limited to declared Dirichlet simplex rows; the recorded independence rationale remains a human-review item.",
            "A convergence diagnostic describes Monte Carlo error for this run and is not independent model validation.",
            "Per-person EVPI covers only the uncertainty represented in this PSA; "
            "it is not population EVPI, EVPPI, a research-funding recommendation, "
            "or a reimbursement recommendation.",
        ],
    }


def _run_dsa(base_payload: dict[str, Any], parameter: Parameter) -> dict[str, Any]:
    outcomes: dict[str, Any] = {}
    for label, value in (("low", parameter.dsa_low), ("high", parameter.dsa_high)):
        payload = copy.deepcopy(base_payload)
        _replace(payload, parameter.target, value)
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
        payload = copy.deepcopy(base_payload)
        for parameter in specification.parameters:
            _replace(payload, parameter.target, _sample(rng, parameter.distribution))
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
            result = exp(
                distribution["mu_log"] + distribution["sigma_log"] * rng.normal()
            )
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


def _parameter(value: Any, index: int, base_payload: dict[str, Any]) -> Parameter:
    value = _mapping(value, f"parameters[{index}]")
    dsa = _mapping(value.get("deterministic"), f"parameters[{index}].deterministic")
    psa = _mapping(value.get("probabilistic"), f"parameters[{index}].probabilistic")
    target = _nonempty(value.get("target"), f"parameters[{index}].target")
    base = _resolve(base_payload, target)
    low = copy.deepcopy(dsa.get("low"))
    high = copy.deepcopy(dsa.get("high"))
    _validate_replacement(target, low, base)
    _validate_replacement(target, high, base)
    distribution = _distribution(psa, base, f"parameters[{index}].probabilistic")
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
        provenance_path=_nonempty(
            value.get("provenance_path"), f"parameters[{index}].provenance_path"
        ),
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
    )


def _distribution(value: dict[str, Any], base: Any, label: str) -> dict[str, Any]:
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
    return result


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
    target: str, value: Any, base: Any, structural: bool = False
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
    allowed = target.startswith(scalar_prefixes + simplex_prefixes)
    if structural:
        allowed = allowed or target in structural_targets
    if not allowed:
        raise ModelValidationError(f"uncertainty target {target!r} is outside the allowlist")
    if isinstance(base, bool):
        if not isinstance(value, bool):
            raise ModelValidationError(f"replacement for {target} must be a boolean")
    elif isinstance(base, int) and not isinstance(base, bool):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ModelValidationError(f"replacement for {target} must be an integer")
    elif isinstance(base, (int, float)):
        _finite_float(value, f"replacement for {target}")
    elif isinstance(base, list):
        if not isinstance(value, list) or len(value) != len(base):
            raise ModelValidationError(f"replacement for {target} must match the array length")
        numeric = [_finite_float(item, f"replacement for {target}") for item in value]
        if any(item < 0 or item > 1 for item in numeric) or abs(sum(numeric) - 1.0) > 1e-9:
            raise ModelValidationError(f"replacement for {target} must be a probability simplex")
    else:
        raise ModelValidationError(f"replacement for {target} has an unsupported type")


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
