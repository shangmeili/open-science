#!/usr/bin/env python3
"""Dependency-free bounded RWE causal contract, engine, and replay audit."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


REQUEST_SCHEMA_VERSION = "0.2.0"
RESULT_SCHEMA_VERSION = "0.2.0"
EVALUATOR = "ai4heor-rwe-causal@0.2.0"
RNG_ALGORITHM = "pcg32-xsh-rr"
RNG_VERSION = "1"
Z_95 = 1.959963984540054
TOLERANCE = 1e-9
PROPENSITY_BOUNDARY = 1e-12
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_SOURCE_ROWS = 5_000
MAX_CONFOUNDERS = 12
SAFE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SAFE_COLUMN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
SAFE_SUBJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
FORBIDDEN_COLUMNS = {
    "name",
    "full_name",
    "email",
    "phone",
    "address",
    "date_of_birth",
    "dob",
    "medical_record_number",
    "mrn",
}

REQUIRED_REVIEW_CHECKS = [
    "target_trial_estimand_time_zero",
    "data_provenance_eligibility_new_user_active_comparator",
    "confounder_causal_rationale_measurement",
    "missingness_follow_up_outcome_integrity",
    "propensity_overlap_weights_positivity",
    "balance_model_diagnostics",
    "bootstrap_precision_failures",
    "residual_bias_transportability_downstream",
]
REQUEST_FIELDS = {
    "schema_version",
    "execution_id",
    "status",
    "target_trial",
    "estimand",
    "evidence_synthesis",
    "source_data",
    "confounders",
    "propensity_score",
    "observation_model",
    "weighting",
    "diagnostics",
    "uncertainty",
    "output",
    "human_authorization",
    "limitations",
    "human_gate",
}
RESULT_FIELDS = {
    "schema_version",
    "execution_id",
    "status",
    "request",
    "source_data",
    "evidence_synthesis",
    "runtime",
    "target_trial",
    "estimand",
    "propensity_score",
    "observation_model",
    "weighting",
    "diagnostics",
    "effects",
    "bootstrap",
    "cross_implementation",
    "warnings",
    "limitations",
    "human_gate",
}


@dataclass(frozen=True)
class SourceRow:
    subject_id: str
    treatment: str
    outcome_observed: bool
    outcome: int | None
    confounders: tuple[float, ...]


class Pcg32:
    """Fixed PCG-XSH-RR stream shared with other deterministic HEOR engines."""

    MASK_64 = (1 << 64) - 1
    MASK_32 = (1 << 32) - 1

    def __init__(self, seed: int, stream: int = 54) -> None:
        self.state = 0
        self.increment = ((stream << 1) | 1) & self.MASK_64
        self.next_u32()
        self.state = (self.state + seed) & self.MASK_64
        self.next_u32()

    def next_u32(self) -> int:
        old_state = self.state
        self.state = (old_state * 6364136223846793005 + self.increment) & self.MASK_64
        xor_shifted = (((old_state >> 18) ^ old_state) >> 27) & self.MASK_32
        rotation = old_state >> 59
        return ((xor_shifted >> rotation) | (xor_shifted << ((-rotation) & 31))) & self.MASK_32

    def bounded(self, upper: int) -> int:
        if upper <= 0:
            raise ValueError("bounded PCG draw requires a positive upper bound")
        limit = (1 << 32) - ((1 << 32) % upper)
        while True:
            value = self.next_u32()
            if value < limit:
                return value % upper


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def exact(value: Any, fields: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == fields


def text(value: Any, maximum: int = 2_000) -> bool:
    return isinstance(value, str) and 0 < len(value) <= maximum and value == value.strip()


def finite(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))


def safe_id(value: Any) -> bool:
    return isinstance(value, str) and SAFE_ID.fullmatch(value) is not None


def safe_column(value: Any) -> bool:
    return isinstance(value, str) and SAFE_COLUMN.fullmatch(value) is not None and value not in FORBIDDEN_COLUMNS


def safe_relative(value: Any) -> bool:
    if not text(value, 500):
        return False
    path = Path(value)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


def resolve_file(workspace: Path, relative: Any) -> Path | None:
    if not safe_relative(relative):
        return None
    candidate = workspace / str(relative)
    if candidate.is_symlink():
        return None
    try:
        root = workspace.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
    except OSError:
        return None
    return resolved if resolved.is_relative_to(root) and resolved.is_file() else None


def resolve_output_directory(workspace: Path, relative: Any) -> Path | None:
    if not safe_relative(relative):
        return None
    root = workspace.resolve()
    candidate = workspace / str(relative)
    existing = candidate
    while not existing.exists() and existing != workspace:
        existing = existing.parent
    try:
        resolved = existing.resolve(strict=True)
    except OSError:
        return None
    return candidate if resolved.is_relative_to(root) and not existing.is_symlink() else None


def load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError(f"{path} exceeds the JSON size cap")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value, raw


def _mean(values: list[float]) -> float:
    if not values:
        raise ValueError("mean requires at least one value")
    return math.fsum(values) / len(values)


def _sample_variance(values: list[float]) -> float:
    if len(values) < 2:
        raise ValueError("sample variance requires at least two values")
    center = _mean(values)
    return math.fsum((value - center) ** 2 for value in values) / (len(values) - 1)


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("quantile requires at least one value")
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    augmented = [list(row) + [vector[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-14:
            raise ValueError("propensity information matrix is singular")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        pivot_row = augmented[column]
        for row_index, row in enumerate(augmented):
            if row_index == column:
                continue
            factor = row[column]
            for index in range(column, size + 1):
                row[index] -= factor * pivot_row[index]
    result = [augmented[index][-1] for index in range(size)]
    if not all(math.isfinite(value) for value in result):
        raise ValueError("propensity linear solve produced a non-finite value")
    return result


def _sigmoid(value: float) -> float:
    if value >= 0:
        inverse = math.exp(-value)
        return 1.0 / (1.0 + inverse)
    direct = math.exp(value)
    return direct / (1.0 + direct)


def _softplus(value: float) -> float:
    if value > 0:
        return value + math.log1p(math.exp(-value))
    return math.log1p(math.exp(value))


def _log_likelihood(design: list[list[float]], treatment: list[int], beta: list[float]) -> float:
    return math.fsum(
        observed * eta - _softplus(eta)
        for row, observed in zip(design, treatment)
        for eta in [math.fsum(coefficient * value for coefficient, value in zip(beta, row))]
    )


def standardize_design(
    rows: list[SourceRow],
    confounder_types: list[str],
) -> tuple[list[list[float]], list[dict[str, float | str]]]:
    design = [[1.0] for _ in rows]
    standardization: list[dict[str, float | str]] = []
    for index, kind in enumerate(confounder_types):
        values = [row.confounders[index] for row in rows]
        if kind == "continuous":
            mean = _mean(values)
            variance = _sample_variance(values)
            if not math.isfinite(variance) or variance <= 1e-14:
                raise ValueError(f"continuous confounder {index} has no usable variation")
            scale = math.sqrt(variance)
            transformed = [(value - mean) / scale for value in values]
            standardization.append({"type": kind, "mean": mean, "scale": scale})
        elif kind == "binary":
            if any(value not in {0.0, 1.0} for value in values):
                raise ValueError(f"binary confounder {index} must be exactly 0 or 1")
            if len(set(values)) < 2:
                raise ValueError(f"binary confounder {index} has no variation")
            transformed = values
            standardization.append({"type": kind, "mean": 0.0, "scale": 1.0})
        else:  # pragma: no cover - request validation owns the boundary
            raise ValueError(f"unsupported confounder type: {kind}")
        for row, value in zip(design, transformed):
            row.append(value)
    return design, standardization


def fit_propensity(
    rows: list[SourceRow],
    treatment_id: str,
    confounder_types: list[str],
    tolerance: float,
    max_iterations: int,
) -> dict[str, Any]:
    design, standardization = standardize_design(rows, confounder_types)
    observed = [1 if row.treatment == treatment_id else 0 for row in rows]
    marginal = math.fsum(observed) / len(observed)
    if not 0 < marginal < 1:
        raise ValueError("both treatment strategies must be present")
    beta = [math.log(marginal / (1 - marginal))] + [0.0] * (len(design[0]) - 1)
    converged_at: int | None = None
    for iteration in range(max_iterations + 1):
        eta = [math.fsum(coefficient * value for coefficient, value in zip(beta, row)) for row in design]
        probabilities = [_sigmoid(value) for value in eta]
        gradient = [
            math.fsum(row[column] * (outcome - probability) for row, outcome, probability in zip(design, observed, probabilities))
            for column in range(len(beta))
        ]
        if max(abs(value) for value in gradient) / len(rows) <= tolerance:
            converged_at = iteration
            break
        if iteration == max_iterations:
            raise ValueError("propensity model did not converge within max_iterations")
        information = [
            [
                math.fsum(
                    row[left] * row[right] * probability * (1 - probability)
                    for row, probability in zip(design, probabilities)
                )
                for right in range(len(beta))
            ]
            for left in range(len(beta))
        ]
        delta = _solve(information, gradient)
        current_likelihood = _log_likelihood(design, observed, beta)
        accepted = False
        step = 1.0
        for _ in range(50):
            candidate = [value + step * change for value, change in zip(beta, delta)]
            candidate_likelihood = _log_likelihood(design, observed, candidate)
            if math.isfinite(candidate_likelihood) and candidate_likelihood >= current_likelihood - 1e-12:
                beta = candidate
                accepted = True
                break
            step *= 0.5
        if not accepted:
            raise ValueError("propensity line search could not improve the likelihood")
    if converged_at is None:  # pragma: no cover - loop exits through break or exception
        raise ValueError("propensity model failed")
    eta = [math.fsum(coefficient * value for coefficient, value in zip(beta, row)) for row in design]
    probabilities = [_sigmoid(value) for value in eta]
    if any(
        not math.isfinite(value) or value <= PROPENSITY_BOUNDARY or value >= 1 - PROPENSITY_BOUNDARY
        for value in probabilities
    ):
        raise ValueError("fitted propensity reached the computational positivity boundary")
    return {
        "coefficients": beta,
        "probabilities": probabilities,
        "iterations": converged_at,
        "standardization": standardization,
        "marginal_treatment_probability": marginal,
        "log_likelihood": _log_likelihood(design, observed, beta),
    }


def fit_observation_model(
    rows: list[SourceRow],
    treatment_id: str,
    confounder_types: list[str],
    predictor_indices: list[int],
    tolerance: float,
    max_iterations: int,
) -> dict[str, Any]:
    design = [[1.0, 1.0 if row.treatment == treatment_id else 0.0] for row in rows]
    standardization: list[dict[str, float | str]] = []
    for index in predictor_indices:
        values = [row.confounders[index] for row in rows]
        kind = confounder_types[index]
        if kind == "continuous":
            mean = _mean(values)
            variance = _sample_variance(values)
            if not math.isfinite(variance) or variance <= 1e-14:
                raise ValueError(f"observation-model continuous predictor {index} has no usable variation")
            scale = math.sqrt(variance)
            transformed = [(value - mean) / scale for value in values]
            standardization.append({"type": kind, "mean": mean, "scale": scale})
        elif kind == "binary":
            if any(value not in {0.0, 1.0} for value in values) or len(set(values)) < 2:
                raise ValueError(f"observation-model binary predictor {index} has invalid variation")
            transformed = values
            standardization.append({"type": kind, "mean": 0.0, "scale": 1.0})
        else:  # pragma: no cover
            raise ValueError(f"unsupported observation predictor type: {kind}")
        for row_design, value in zip(design, transformed):
            row_design.append(value)

    observed = [1 if row.outcome_observed else 0 for row in rows]
    marginal = math.fsum(observed) / len(observed)
    if not 0 < marginal < 1:
        raise ValueError("observation model requires observed and not-observed outcomes")
    beta = [math.log(marginal / (1 - marginal))] + [0.0] * (len(design[0]) - 1)
    converged_at: int | None = None
    for iteration in range(max_iterations + 1):
        eta = [math.fsum(coefficient * value for coefficient, value in zip(beta, row)) for row in design]
        probabilities = [_sigmoid(value) for value in eta]
        gradient = [
            math.fsum(row[column] * (outcome - probability) for row, outcome, probability in zip(design, observed, probabilities))
            for column in range(len(beta))
        ]
        if max(abs(value) for value in gradient) / len(rows) <= tolerance:
            converged_at = iteration
            break
        if iteration == max_iterations:
            raise ValueError("observation model did not converge within max_iterations")
        information = [
            [
                math.fsum(
                    row[left] * row[right] * probability * (1 - probability)
                    for row, probability in zip(design, probabilities)
                )
                for right in range(len(beta))
            ]
            for left in range(len(beta))
        ]
        delta = _solve(information, gradient)
        current_likelihood = _log_likelihood(design, observed, beta)
        accepted = False
        step = 1.0
        for _ in range(50):
            candidate = [value + step * change for value, change in zip(beta, delta)]
            candidate_likelihood = _log_likelihood(design, observed, candidate)
            if math.isfinite(candidate_likelihood) and candidate_likelihood >= current_likelihood - 1e-12:
                beta = candidate
                accepted = True
                break
            step *= 0.5
        if not accepted:
            raise ValueError("observation-model line search could not improve the likelihood")
    if converged_at is None:  # pragma: no cover
        raise ValueError("observation model failed")
    eta = [math.fsum(coefficient * value for coefficient, value in zip(beta, row)) for row in design]
    probabilities = [_sigmoid(value) for value in eta]
    if any(
        not math.isfinite(value) or value <= PROPENSITY_BOUNDARY or value >= 1 - PROPENSITY_BOUNDARY
        for value in probabilities
    ):
        raise ValueError("fitted observation probability reached the computational positivity boundary")
    arm_marginals: dict[str, float] = {}
    for treatment in {row.treatment for row in rows}:
        arm_values = [1 if row.outcome_observed else 0 for row in rows if row.treatment == treatment]
        arm_marginal = math.fsum(arm_values) / len(arm_values)
        if not 0 < arm_marginal < 1:
            raise ValueError(f"treatment arm {treatment} requires observed and not-observed outcomes")
        arm_marginals[treatment] = arm_marginal
    return {
        "coefficients": beta,
        "probabilities": probabilities,
        "iterations": converged_at,
        "standardization": standardization,
        "marginal_observation_probability": marginal,
        "treatment_arm_observation_probabilities": arm_marginals,
        "log_likelihood": _log_likelihood(design, observed, beta),
    }


def stabilized_ate_weights(
    rows: list[SourceRow],
    treatment_id: str,
    probabilities: list[float],
    marginal: float,
) -> list[float]:
    weights = [
        marginal / probability
        if row.treatment == treatment_id
        else (1 - marginal) / (1 - probability)
        for row, probability in zip(rows, probabilities)
    ]
    if any(not math.isfinite(value) or value <= 0 for value in weights):
        raise ValueError("stabilized IPTW weights must be finite and positive")
    return weights


def stabilized_observation_weights(
    rows: list[SourceRow],
    probabilities: list[float],
    arm_marginals: dict[str, float],
) -> list[float]:
    weights = [
        arm_marginals[row.treatment] / probability if row.outcome_observed else 0.0
        for row, probability in zip(rows, probabilities)
    ]
    if any(not math.isfinite(value) or value < 0 for value in weights):
        raise ValueError("stabilized observation weights must be finite and non-negative")
    if any(row.outcome_observed and weight <= 0 for row, weight in zip(rows, weights)):
        raise ValueError("observed outcomes require positive observation weights")
    return weights


def _weighted_mean(values: list[float], weights: list[float]) -> float:
    total = math.fsum(weights)
    if not math.isfinite(total) or total <= 0:
        raise ValueError("weighted mean requires positive finite mass")
    return math.fsum(value * weight for value, weight in zip(values, weights)) / total


def _weighted_variance(values: list[float], weights: list[float]) -> float:
    mean = _weighted_mean(values, weights)
    total = math.fsum(weights)
    return math.fsum(weight * (value - mean) ** 2 for value, weight in zip(values, weights)) / total


def _ess(weights: list[float]) -> float:
    denominator = math.fsum(value * value for value in weights)
    if denominator <= 0:
        raise ValueError("ESS denominator must be positive")
    return math.fsum(weights) ** 2 / denominator


def _distribution(values: list[float]) -> dict[str, float]:
    return {
        "minimum": min(values),
        "p01": _quantile(values, 0.01),
        "p05": _quantile(values, 0.05),
        "median": _quantile(values, 0.5),
        "p95": _quantile(values, 0.95),
        "p99": _quantile(values, 0.99),
        "maximum": max(values),
        "mean": _mean(values),
    }


def _balance_state(
    rows: list[SourceRow],
    weights: list[float],
    treatment_id: str,
    comparator_id: str,
    confounder_ids: list[str],
) -> list[dict[str, float | str]]:
    result: list[dict[str, float | str]] = []
    for index, confounder_id in enumerate(confounder_ids):
        treatment_values = [row.confounders[index] for row in rows if row.treatment == treatment_id]
        comparator_values = [row.confounders[index] for row in rows if row.treatment == comparator_id]
        treatment_weights = [weight for row, weight in zip(rows, weights) if row.treatment == treatment_id]
        comparator_weights = [weight for row, weight in zip(rows, weights) if row.treatment == comparator_id]
        treatment_mean = _weighted_mean(treatment_values, treatment_weights)
        comparator_mean = _weighted_mean(comparator_values, comparator_weights)
        treatment_variance = _weighted_variance(treatment_values, treatment_weights)
        comparator_variance = _weighted_variance(comparator_values, comparator_weights)
        pooled = math.sqrt((treatment_variance + comparator_variance) / 2)
        if not math.isfinite(pooled) or pooled <= 1e-14:
            raise ValueError(f"confounder {confounder_id} has a zero pooled SMD denominator")
        smd = (treatment_mean - comparator_mean) / pooled
        result.append(
            {
                "id": confounder_id,
                "treatment_mean": treatment_mean,
                "comparator_mean": comparator_mean,
                "pooled_standard_deviation": pooled,
                "standardized_mean_difference": smd,
                "absolute_standardized_mean_difference": abs(smd),
            }
        )
    return result


def effect_summary(
    rows: list[SourceRow],
    weights: list[float],
    treatment_id: str,
    comparator_id: str,
) -> dict[str, Any]:
    treatment_pairs = [
        (float(row.outcome), weight)
        for row, weight in zip(rows, weights)
        if row.treatment == treatment_id and row.outcome is not None and weight > 0
    ]
    comparator_pairs = [
        (float(row.outcome), weight)
        for row, weight in zip(rows, weights)
        if row.treatment == comparator_id and row.outcome is not None and weight > 0
    ]
    treatment_outcomes = [value for value, _ in treatment_pairs]
    comparator_outcomes = [value for value, _ in comparator_pairs]
    treatment_weights = [weight for _, weight in treatment_pairs]
    comparator_weights = [weight for _, weight in comparator_pairs]
    treatment_risk = _weighted_mean(treatment_outcomes, treatment_weights)
    comparator_risk = _weighted_mean(comparator_outcomes, comparator_weights)
    risk_difference = treatment_risk - comparator_risk
    risk_ratio = treatment_risk / comparator_risk if comparator_risk > 0 else None
    odds_ratio = None
    if 0 < treatment_risk < 1 and 0 < comparator_risk < 1:
        odds_ratio = (treatment_risk / (1 - treatment_risk)) / (comparator_risk / (1 - comparator_risk))
    return {
        "treatment_risk": treatment_risk,
        "comparator_risk": comparator_risk,
        "risk_difference": risk_difference,
        "risk_ratio": risk_ratio,
        "odds_ratio": odds_ratio,
    }


def point_analysis(request: dict[str, Any], facts: dict[str, Any], rows: list[SourceRow] | None = None) -> dict[str, Any]:
    analysis_rows = facts["rows"] if rows is None else rows
    confounder_types = facts["confounder_types"]
    confounder_ids = facts["confounder_ids"]
    target = request["target_trial"]
    treatment_id = target["treatment_strategy"]["id"]
    comparator_id = target["comparator_strategy"]["id"]
    propensity = fit_propensity(
        analysis_rows,
        treatment_id,
        confounder_types,
        float(request["propensity_score"]["convergence_tolerance"]),
        int(request["propensity_score"]["max_iterations"]),
    )
    weights = stabilized_ate_weights(
        analysis_rows,
        treatment_id,
        propensity["probabilities"],
        propensity["marginal_treatment_probability"],
    )
    observation = fit_observation_model(
        analysis_rows,
        treatment_id,
        confounder_types,
        facts["observation_predictor_indices"],
        float(request["observation_model"]["convergence_tolerance"]),
        int(request["observation_model"]["max_iterations"]),
    )
    observation_weights = stabilized_observation_weights(
        analysis_rows,
        observation["probabilities"],
        observation["treatment_arm_observation_probabilities"],
    )
    combined_weights = [treatment * observed for treatment, observed in zip(weights, observation_weights)]
    observed_unit_weights = [1.0 if row.outcome_observed else 0.0 for row in analysis_rows]
    unit_weights = [1.0] * len(analysis_rows)
    pre_balance = _balance_state(analysis_rows, unit_weights, treatment_id, comparator_id, confounder_ids)
    treatment_weight_balance = _balance_state(analysis_rows, weights, treatment_id, comparator_id, confounder_ids)
    combined_weight_balance = _balance_state(analysis_rows, combined_weights, treatment_id, comparator_id, confounder_ids)
    treatment_propensities = [
        probability
        for row, probability in zip(analysis_rows, propensity["probabilities"])
        if row.treatment == treatment_id
    ]
    comparator_propensities = [
        probability
        for row, probability in zip(analysis_rows, propensity["probabilities"])
        if row.treatment == comparator_id
    ]
    treatment_weights = [weight for row, weight in zip(analysis_rows, weights) if row.treatment == treatment_id]
    comparator_weights = [weight for row, weight in zip(analysis_rows, weights) if row.treatment == comparator_id]
    positive_observation_weights = [weight for weight in observation_weights if weight > 0]
    positive_combined_weights = [weight for weight in combined_weights if weight > 0]
    combined_treatment_weights = [
        weight for row, weight in zip(analysis_rows, combined_weights)
        if row.treatment == treatment_id and weight > 0
    ]
    combined_comparator_weights = [
        weight for row, weight in zip(analysis_rows, combined_weights)
        if row.treatment == comparator_id and weight > 0
    ]
    overlap_lower = max(min(treatment_propensities), min(comparator_propensities))
    overlap_upper = min(max(treatment_propensities), max(comparator_propensities))
    return {
        "propensity": propensity,
        "observation_model": observation,
        "weights": weights,
        "observation_weights": observation_weights,
        "combined_weights": combined_weights,
        "propensity_summary": {
            "treatment": _distribution(treatment_propensities),
            "comparator": _distribution(comparator_propensities),
            "empirical_range_intersection": {
                "lower": overlap_lower,
                "upper": overlap_upper,
                "width": max(0.0, overlap_upper - overlap_lower),
                "exists": overlap_upper >= overlap_lower,
            },
        },
        "weight_summary": {
            "treatment": {
                "overall": _distribution(weights),
                "treatment": _distribution(treatment_weights),
                "comparator": _distribution(comparator_weights),
            },
            "observation_observed_rows": _distribution(positive_observation_weights),
            "combined_observed_rows": {
                "overall": _distribution(positive_combined_weights),
                "treatment": _distribution(combined_treatment_weights),
                "comparator": _distribution(combined_comparator_weights),
            },
            "effective_sample_size_observed": {
                "overall": _ess(positive_combined_weights),
                "treatment": _ess(combined_treatment_weights),
                "comparator": _ess(combined_comparator_weights),
            },
            "effective_sample_size_treatment": {
                "overall": _ess(weights),
                "treatment": _ess(treatment_weights),
                "comparator": _ess(comparator_weights),
            },
        },
        "observation_summary": {
            "observed": sum(row.outcome_observed for row in analysis_rows),
            "not_observed": sum(not row.outcome_observed for row in analysis_rows),
            "rates": observation["treatment_arm_observation_probabilities"],
            "probabilities": _distribution(observation["probabilities"]),
        },
        "pre_balance": pre_balance,
        "treatment_weight_balance": treatment_weight_balance,
        "combined_weight_balance": combined_weight_balance,
        "max_abs_pre_smd": max(float(item["absolute_standardized_mean_difference"]) for item in pre_balance),
        "max_abs_treatment_weight_smd": max(float(item["absolute_standardized_mean_difference"]) for item in treatment_weight_balance),
        "max_abs_combined_weight_smd": max(float(item["absolute_standardized_mean_difference"]) for item in combined_weight_balance),
        "unadjusted_effects": effect_summary(analysis_rows, observed_unit_weights, treatment_id, comparator_id),
        "treatment_weighted_effects": effect_summary(analysis_rows, [weight if row.outcome_observed else 0.0 for row, weight in zip(analysis_rows, weights)], treatment_id, comparator_id),
        "combined_weighted_effects": effect_summary(analysis_rows, combined_weights, treatment_id, comparator_id),
    }


def bootstrap_samples(
    rows: list[SourceRow],
    comparator_id: str,
    treatment_id: str,
    iterations: int,
    seed: int,
) -> Iterator[list[SourceRow]]:
    positions = {
        comparator_id: [index for index, row in enumerate(rows) if row.treatment == comparator_id],
        treatment_id: [index for index, row in enumerate(rows) if row.treatment == treatment_id],
    }
    rng = Pcg32(seed)
    for _ in range(iterations):
        sample: list[SourceRow] = []
        for arm in (comparator_id, treatment_id):
            arm_positions = positions[arm]
            sample.extend(rows[arm_positions[rng.bounded(len(arm_positions))]] for _ in arm_positions)
        yield sample


def execute_bootstrap(request: dict[str, Any], facts: dict[str, Any]) -> tuple[list[dict[str, Any]], list[float]]:
    target = request["target_trial"]
    uncertainty = request["uncertainty"]
    draws: list[dict[str, Any]] = []
    successful: list[float] = []
    for iteration, sample in enumerate(
        bootstrap_samples(
            facts["rows"],
            target["comparator_strategy"]["id"],
            target["treatment_strategy"]["id"],
            int(uncertainty["iterations"]),
            int(uncertainty["seed"]),
        ),
        start=1,
    ):
        try:
            analysis = point_analysis(request, facts, sample)
            effect = float(analysis["combined_weighted_effects"]["risk_difference"])
            successful.append(effect)
            draws.append(
                {
                    "iteration": iteration,
                    "status": "ok",
                    "risk_difference": effect,
                    "treatment_risk": analysis["combined_weighted_effects"]["treatment_risk"],
                    "comparator_risk": analysis["combined_weighted_effects"]["comparator_risk"],
                    "maximum_weight": analysis["weight_summary"]["combined_observed_rows"]["overall"]["maximum"],
                    "max_abs_post_smd": analysis["max_abs_combined_weight_smd"],
                    "error": "",
                }
            )
        except ValueError as error:
            draws.append(
                {
                    "iteration": iteration,
                    "status": "failed",
                    "risk_difference": None,
                    "treatment_risk": None,
                    "comparator_risk": None,
                    "maximum_weight": None,
                    "max_abs_post_smd": None,
                    "error": str(error)[:240],
                }
            )
    return draws, successful


def canonical_draw_bytes(draws: list[dict[str, Any]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    fields = [
        "iteration",
        "status",
        "risk_difference",
        "treatment_risk",
        "comparator_risk",
        "maximum_weight",
        "max_abs_post_smd",
        "error",
    ]
    writer.writerow(fields)
    for draw in draws:
        writer.writerow(
            [
                draw["iteration"],
                draw["status"],
                *[
                    "" if draw[field] is None else format(float(draw[field]), ".17g")
                    for field in fields[2:-1]
                ],
                draw["error"],
            ]
        )
    return output.getvalue().encode("utf-8")


def inspect_source(
    path: Path,
    expected_columns: list[str],
    confounder_types: list[str],
    treatment_id: str,
    comparator_id: str,
) -> tuple[list[SourceRow], dict[str, Any], list[str]]:
    rows: list[SourceRow] = []
    errors: list[str] = []
    if path.stat().st_size > MAX_SOURCE_BYTES:
        return rows, {}, ["source_data exceeds 64 MB"]
    subjects: set[str] = set()
    counts = {treatment_id: 0, comparator_id: 0}
    outcomes = {treatment_id: {0: 0, 1: 0}, comparator_id: {0: 0, 1: 0}}
    observation = {
        treatment_id: {False: 0, True: 0},
        comparator_id: {False: 0, True: 0},
    }
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            try:
                header = next(reader)
            except StopIteration:
                return rows, {}, ["source_data CSV is empty"]
            if header != expected_columns:
                return rows, {}, ["source_data CSV columns do not exactly match source_data.columns"]
            for line_number, raw in enumerate(reader, start=2):
                if len(raw) != len(expected_columns) or any(
                    value != value.strip() or (index != 3 and not value)
                    for index, value in enumerate(raw)
                ):
                    errors.append(f"source_data row {line_number} contains an invalid, disallowed blank, or padded value")
                    continue
                subject_id, treatment, observed_raw, outcome_raw, *confounder_raw = raw
                if SAFE_SUBJECT.fullmatch(subject_id) is None:
                    errors.append(f"source_data row {line_number} subject_id is not a safe pseudonym")
                elif subject_id in subjects:
                    errors.append(f"source_data row {line_number} repeats subject_id")
                subjects.add(subject_id)
                if treatment not in counts:
                    errors.append(f"source_data row {line_number} treatment is outside the two declared strategies")
                    continue
                try:
                    observed_value = float(observed_raw)
                    values = tuple(float(value) for value in confounder_raw)
                except ValueError:
                    errors.append(f"source_data row {line_number} observation indicator and confounders must be numeric")
                    continue
                if observed_value not in {0.0, 1.0}:
                    errors.append(f"source_data row {line_number} outcome_observed must be exactly 0 or 1")
                    continue
                outcome_observed = observed_value == 1.0
                if outcome_observed:
                    try:
                        outcome_value = float(outcome_raw)
                    except ValueError:
                        errors.append(f"source_data row {line_number} outcome must be 0 or 1 when observed")
                        continue
                    if outcome_value not in {0.0, 1.0}:
                        errors.append(f"source_data row {line_number} outcome must be exactly 0 or 1 when observed")
                        continue
                    outcome: int | None = int(outcome_value)
                else:
                    if outcome_raw:
                        errors.append(f"source_data row {line_number} outcome must be blank when outcome_observed is 0")
                        continue
                    outcome = None
                if len(values) != len(confounder_types) or any(
                    not math.isfinite(value) or abs(value) > 1e12 for value in values
                ):
                    errors.append(f"source_data row {line_number} confounder values are invalid")
                    continue
                for index, (value, kind) in enumerate(zip(values, confounder_types)):
                    if kind == "binary" and value not in {0.0, 1.0}:
                        errors.append(f"source_data row {line_number} binary confounder {index} must be 0 or 1")
                rows.append(SourceRow(subject_id, treatment, outcome_observed, outcome, values))
                counts[treatment] += 1
                observation[treatment][outcome_observed] += 1
                if outcome is not None:
                    outcomes[treatment][outcome] += 1
                if len(rows) > MAX_SOURCE_ROWS:
                    errors.append(f"source_data exceeds {MAX_SOURCE_ROWS} rows")
                    break
    except (OSError, UnicodeError, csv.Error) as error:
        return rows, {}, [f"source_data CSV cannot be read: {error}"]
    for arm, count in counts.items():
        if count < 20:
            errors.append(f"source_data treatment arm {arm} must contain at least 20 rows")
        if observation[arm][True] < 2 or observation[arm][False] < 2:
            errors.append(f"source_data treatment arm {arm} must contain at least two observed and two not-observed outcomes")
        if outcomes[arm][0] < 2 or outcomes[arm][1] < 2:
            errors.append(f"source_data treatment arm {arm} must contain at least two observed events and two observed non-events")
    if len(rows) != len(subjects):
        errors.append("source_data subject identifiers must be unique")
    return rows, {
        "row_count": len(rows),
        "arm_counts": counts,
        "outcome_counts": outcomes,
        "observation_counts": observation,
    }, errors


def _safe_text_list(value: Any, maximum_items: int = 100) -> bool:
    return (
        isinstance(value, list)
        and 0 < len(value) <= maximum_items
        and all(text(item) for item in value)
    )


def validate_request(request: dict[str, Any], workspace: Path) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    if not exact(request, REQUEST_FIELDS):
        return ["request fields do not match RWE causal schema 0.2.0"], {}
    if request.get("schema_version") != REQUEST_SCHEMA_VERSION:
        errors.append("schema_version must be 0.2.0")
    execution_id = request.get("execution_id")
    if not safe_id(execution_id):
        errors.append("execution_id must be a safe stable identifier")
    if request.get("status") != "ready_for_execution":
        errors.append("status must be ready_for_execution")

    target = request.get("target_trial")
    target_fields = {
        "design",
        "population",
        "eligibility_criteria",
        "treatment_strategy",
        "comparator_strategy",
        "assignment",
        "time_zero",
        "follow_up",
        "outcome",
        "causal_contrast",
    }
    treatment_id = ""
    comparator_id = ""
    if not exact(target, target_fields):
        errors.append("target_trial fields do not match the fixed target-trial contract")
        target = {}
    else:
        if target.get("design") != "active_comparator_new_user_observational_cohort":
            errors.append("target_trial design must be active_comparator_new_user_observational_cohort")
        for field in ("population", "time_zero", "follow_up", "outcome"):
            if not text(target.get(field)):
                errors.append(f"target_trial {field} must be Human-authored text")
        if not _safe_text_list(target.get("eligibility_criteria"), 50):
            errors.append("target_trial eligibility_criteria must be non-empty Human-authored text")
        for field in ("treatment_strategy", "comparator_strategy"):
            strategy = target.get(field)
            if not exact(strategy, {"id", "label"}) or not safe_id(strategy.get("id")) or not text(strategy.get("label"), 200):
                errors.append(f"target_trial {field} is invalid")
            else:
                if field == "treatment_strategy":
                    treatment_id = strategy["id"]
                else:
                    comparator_id = strategy["id"]
        if treatment_id and treatment_id == comparator_id:
            errors.append("target_trial treatment and comparator strategy IDs must differ")
        if target.get("assignment") != "observational_at_baseline":
            errors.append("target_trial assignment must be observational_at_baseline")
        if target.get("causal_contrast") != "intention_to_treat_analog":
            errors.append("target_trial causal_contrast must be intention_to_treat_analog")

    estimand = request.get("estimand")
    if estimand != {
        "population": "analyzed_source_cohort",
        "treatment_contrast": "treatment_vs_comparator",
        "measure": "risk_difference",
        "favorable_direction": estimand.get("favorable_direction") if isinstance(estimand, dict) else None,
    } or estimand.get("favorable_direction") not in {"higher", "lower"}:
        errors.append("estimand must be the source-cohort ATE risk difference with an explicit favorable direction")

    evidence = request.get("evidence_synthesis")
    evidence_path: Path | None = None
    if not exact(evidence, {"path", "sha256", "included_record_ids"}):
        errors.append("evidence_synthesis fields are invalid")
        evidence = {}
    else:
        records = evidence.get("included_record_ids")
        if not isinstance(records, list) or not records or len(set(records)) != len(records) or any(not safe_id(item) for item in records):
            errors.append("evidence_synthesis included_record_ids must be unique safe identifiers")
        evidence_path = resolve_file(workspace, evidence.get("path"))
        if evidence_path is None or SHA256.fullmatch(str(evidence.get("sha256", ""))) is None:
            errors.append("evidence_synthesis path or sha256 is unsafe")
        else:
            try:
                if digest(evidence_path.read_bytes()) != evidence["sha256"]:
                    errors.append("evidence_synthesis sha256 does not match current bytes")
                load_json(evidence_path)
            except (OSError, ValueError, json.JSONDecodeError) as error:
                errors.append(f"evidence_synthesis cannot be read: {error}")

    confounders = request.get("confounders")
    confounder_ids: list[str] = []
    confounder_columns: list[str] = []
    confounder_types: list[str] = []
    if not isinstance(confounders, list) or not 1 <= len(confounders) <= MAX_CONFOUNDERS:
        errors.append(f"confounders must contain 1 to {MAX_CONFOUNDERS} Human-prespecified baseline variables")
    else:
        included_records = set(evidence.get("included_record_ids", []))
        for index, item in enumerate(confounders):
            if not exact(item, {"id", "column", "label", "type", "timing", "roles", "rationale", "evidence_record_ids"}):
                errors.append(f"confounders[{index}] fields are invalid")
                continue
            record_ids = item.get("evidence_record_ids")
            if not safe_id(item.get("id")) or not safe_column(item.get("column")) or not text(item.get("label"), 200):
                errors.append(f"confounders[{index}] identity is invalid")
            if item.get("type") not in {"binary", "continuous"}:
                errors.append(f"confounders[{index}] type must be binary or continuous")
            roles = item.get("roles")
            if (
                item.get("timing") != "baseline_pre_treatment"
                or not isinstance(roles, list)
                or not roles
                or len(set(roles)) != len(roles)
                or any(role not in {"treatment_outcome_common_cause", "observation_outcome_common_cause"} for role in roles)
            ):
                errors.append(f"confounders[{index}] must declare Human-prespecified baseline common cause roles")
            elif "treatment_outcome_common_cause" not in roles:
                errors.append(f"confounders[{index}] must be a Human-prespecified treatment-outcome baseline common cause")
            if not text(item.get("rationale")):
                errors.append(f"confounders[{index}] requires a Human-authored causal rationale")
            if (
                not isinstance(record_ids, list)
                or not record_ids
                or len(set(record_ids)) != len(record_ids)
                or any(not safe_id(value) or value not in included_records for value in record_ids)
            ):
                errors.append(f"confounders[{index}] evidence_record_ids must bind included evidence")
            confounder_ids.append(str(item.get("id", "")))
            confounder_columns.append(str(item.get("column", "")))
            confounder_types.append(str(item.get("type", "")))
        if len(set(confounder_ids)) != len(confounder_ids) or len(set(confounder_columns)) != len(confounder_columns):
            errors.append("confounder IDs and columns must be unique")

    source = request.get("source_data")
    source_fields = {
        "classification",
        "execution_boundary",
        "format",
        "path",
        "sha256",
        "columns",
        "row_count",
        "contains_direct_identifiers",
        "missing_policy",
        "one_row_per_person",
        "baseline_covariates_only",
        "fixed_horizon_outcome",
        "outcome_observation",
        "treatment_assignment",
    }
    source_path: Path | None = None
    rows: list[SourceRow] = []
    source_facts: dict[str, Any] = {}
    if not exact(source, source_fields):
        errors.append("source_data fields are invalid")
        source = {}
    else:
        expected_columns = ["subject_id", "treatment", "outcome_observed", "outcome", *confounder_columns]
        if source.get("classification") not in {"restricted", "confidential"}:
            errors.append("source_data classification must be restricted or confidential")
        if source.get("execution_boundary") != "local_only" or source.get("format") != "one_row_per_person_csv":
            errors.append("source_data must be a local-only one-row-per-person CSV")
        if source.get("columns") != expected_columns or any(not safe_column(value) for value in source.get("columns", [])):
            errors.append("source_data columns must exactly match subject_id,treatment,outcome_observed,outcome and ordered confounders")
        if source.get("contains_direct_identifiers") is not False:
            errors.append("source_data must declare no direct identifiers")
        if (
            source.get("missing_policy") != "outcome_blank_only_when_not_observed"
            or source.get("one_row_per_person") is not True
            or source.get("baseline_covariates_only") is not True
            or source.get("fixed_horizon_outcome") is not True
            or source.get("outcome_observation") != {
                "indicator_column": "outcome_observed",
                "observed_value": 1,
                "not_observed_value": 0,
            }
            or source.get("treatment_assignment") != "observational_active_comparator_new_user"
        ):
            errors.append("source_data must bind the fixed-horizon observed-outcome active-comparator new-user cohort contract")
        if isinstance(source.get("row_count"), bool) or not isinstance(source.get("row_count"), int) or not 40 <= source.get("row_count", 0) <= MAX_SOURCE_ROWS:
            errors.append("source_data row_count is outside the supported range")
        source_path = resolve_file(workspace, source.get("path"))
        if source_path is None or SHA256.fullmatch(str(source.get("sha256", ""))) is None:
            errors.append("source_data path or sha256 is unsafe")
        else:
            if digest(source_path.read_bytes()) != source["sha256"]:
                errors.append("source_data sha256 does not match current bytes")
            elif treatment_id and comparator_id and len(confounder_types) == len(confounder_columns):
                rows, source_facts, source_errors = inspect_source(
                    source_path,
                    expected_columns,
                    confounder_types,
                    treatment_id,
                    comparator_id,
                )
                errors.extend(source_errors)
                if source_facts.get("row_count") != source.get("row_count"):
                    errors.append("source_data row_count does not match parsed rows")

    propensity = request.get("propensity_score")
    if propensity != {
        "model": "logistic_regression_main_effects",
        "treatment_encoding": "treatment_strategy_id_is_one",
        "intercept": True,
        "continuous_standardization": "sample_mean_standard_deviation",
        "nonlinear_terms": "none",
        "interactions": "none",
        "penalty": "none",
        "convergence_tolerance": propensity.get("convergence_tolerance") if isinstance(propensity, dict) else None,
        "max_iterations": propensity.get("max_iterations") if isinstance(propensity, dict) else None,
    }:
        errors.append("propensity_score must use the fixed unpenalized main-effects logistic model")
    else:
        tolerance = propensity.get("convergence_tolerance")
        iterations = propensity.get("max_iterations")
        if not finite(tolerance) or not 1e-12 <= float(tolerance) <= 1e-8:
            errors.append("propensity_score convergence_tolerance must be between 1e-12 and 1e-8")
        if isinstance(iterations, bool) or not isinstance(iterations, int) or not 20 <= iterations <= 500:
            errors.append("propensity_score max_iterations must be between 20 and 500")

    observation_model = request.get("observation_model")
    predictor_ids = observation_model.get("predictor_ids") if isinstance(observation_model, dict) else None
    observation_fixed = {
        "model": "logistic_regression_main_effects",
        "response_encoding": "outcome_observed_is_one",
        "predictor_ids": predictor_ids,
        "includes_treatment": True,
        "intercept": True,
        "continuous_standardization": "sample_mean_standard_deviation",
        "nonlinear_terms": "none",
        "interactions": "none",
        "penalty": "none",
        "convergence_tolerance": observation_model.get("convergence_tolerance") if isinstance(observation_model, dict) else None,
        "max_iterations": observation_model.get("max_iterations") if isinstance(observation_model, dict) else None,
    }
    observation_predictor_indices: list[int] = []
    if observation_model != observation_fixed:
        errors.append("observation_model must use the fixed Human-prespecified treatment-plus-baseline logistic model")
    else:
        if (
            not isinstance(predictor_ids, list)
            or not predictor_ids
            or len(set(predictor_ids)) != len(predictor_ids)
            or any(value not in confounder_ids for value in predictor_ids)
        ):
            errors.append("observation_model predictor_ids must be a unique non-empty subset of confounders")
        else:
            observation_predictor_indices = [confounder_ids.index(value) for value in predictor_ids]
            for predictor_id, index in zip(predictor_ids, observation_predictor_indices):
                roles = request["confounders"][index].get("roles", [])
                if "observation_outcome_common_cause" not in roles:
                    errors.append(
                        f"observation_model predictor {predictor_id} lacks a Human-prespecified observation-outcome causal role"
                    )
        tolerance = observation_model.get("convergence_tolerance")
        iterations = observation_model.get("max_iterations")
        if not finite(tolerance) or not 1e-12 <= float(tolerance) <= 1e-8:
            errors.append("observation_model convergence_tolerance must be between 1e-12 and 1e-8")
        if isinstance(iterations, bool) or not isinstance(iterations, int) or not 20 <= iterations <= 500:
            errors.append("observation_model max_iterations must be between 20 and 500")

    weighting = request.get("weighting")
    if weighting != {
        "estimand": "source_cohort_ate",
        "method": "stabilized_inverse_probability_of_treatment_and_observation_weighting",
        "treatment_numerator": "marginal_treatment_probability",
        "observation_numerator": "treatment_arm_observation_probability",
        "outcome_rows": "observed_only",
        "trimming": "none",
        "weight_cap": "none",
        "renormalization": "none",
    }:
        errors.append("weighting must use untrimmed, uncapped stabilized source-cohort ATE treatment-and-observation weighting")
    diagnostics = request.get("diagnostics")
    if diagnostics != {
        "balance_metric": "standardized_mean_difference",
        "balance_denominator": "state_specific_two_arm_pooled_standard_deviation",
        "overlap": "empirical_propensity_range_intersection",
        "automatic_acceptance_thresholds": "none",
    }:
        errors.append("diagnostics must use the fixed balance and overlap reporting contract")
    uncertainty = request.get("uncertainty")
    uncertainty_fixed = {
        "method": "arm_stratified_nonparametric_bootstrap_refit",
        "iterations": uncertainty.get("iterations") if isinstance(uncertainty, dict) else None,
        "seed": uncertainty.get("seed") if isinstance(uncertainty, dict) else None,
        "prng": {"algorithm": RNG_ALGORITHM, "version": RNG_VERSION},
        "interval": "normal_bootstrap_95_percent",
        "failure_policy": "retain_and_block_review",
    }
    if uncertainty != uncertainty_fixed:
        errors.append("uncertainty must use the fixed arm-stratified PCG32 bootstrap-refit contract")
    else:
        bootstrap_iterations = uncertainty.get("iterations")
        seed = uncertainty.get("seed")
        if isinstance(bootstrap_iterations, bool) or not isinstance(bootstrap_iterations, int) or not 1_000 <= bootstrap_iterations <= 5_000:
            errors.append("uncertainty iterations must be between 1000 and 5000")
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**63:
            errors.append("uncertainty seed must be a non-negative 63-bit integer")

    output = request.get("output")
    expected_output = f"heor/rwe-causal-analysis-runs/{execution_id}" if safe_id(execution_id) else None
    if not exact(output, {"directory"}) or output.get("directory") != expected_output or resolve_output_directory(workspace, output.get("directory")) is None:
        errors.append("output directory must be the fixed immutable path for execution_id")
    authorization = request.get("human_authorization")
    if (
        not exact(authorization, {"actor", "authorized_at", "scope"})
        or not text(authorization.get("actor"), 120)
        or ISO_UTC.fullmatch(str(authorization.get("authorized_at", ""))) is None
        or authorization.get("scope") != "execute_local_rwe_causal_analysis"
    ):
        errors.append("human_authorization must bind an actor, UTC time, and exact local RWE execution scope")
    if not _safe_text_list(request.get("limitations"), 50):
        errors.append("limitations must contain non-empty Human-authored text")
    gate = request.get("human_gate")
    if not exact(gate, {"status", "required_checks"}) or gate.get("status") != "awaiting_method_review" or gate.get("required_checks") != REQUIRED_REVIEW_CHECKS:
        errors.append("human_gate must contain the exact eight-check awaiting_method_review contract")

    preflight: dict[str, Any] = {}
    if not errors:
        try:
            preflight = point_analysis(
                request,
                {
                    "rows": rows,
                    "confounder_types": confounder_types,
                    "confounder_ids": confounder_ids,
                    "observation_predictor_indices": observation_predictor_indices,
                },
            )
        except ValueError as error:
            errors.append(f"RWE causal preflight failed: {error}")
    facts = {
        "rows": rows,
        "source": source_facts,
        "source_path": source_path,
        "evidence_path": evidence_path,
        "confounder_ids": confounder_ids,
        "confounder_columns": confounder_columns,
        "confounder_types": confounder_types,
        "observation_predictor_indices": observation_predictor_indices,
        "preflight": preflight,
    }
    return errors, facts


def propensity_result(request: dict[str, Any], facts: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    confounders = request["confounders"]
    propensity = analysis["propensity"]
    names = ["intercept", *[item["id"] for item in confounders]]
    return {
        "model": "logistic_regression_main_effects",
        "converged": True,
        "iterations": propensity["iterations"],
        "log_likelihood": propensity["log_likelihood"],
        "marginal_treatment_probability": propensity["marginal_treatment_probability"],
        "coefficients": [
            {"id": name, "value": value}
            for name, value in zip(names, propensity["coefficients"])
        ],
        "standardization": [
            {"id": item["id"], **standardization}
            for item, standardization in zip(confounders, propensity["standardization"])
        ],
    }


def observation_model_result(request: dict[str, Any], facts: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    model = analysis["observation_model"]
    predictor_ids = request["observation_model"]["predictor_ids"]
    return {
        "model": "logistic_regression_main_effects",
        "response": "outcome_observed",
        "converged": True,
        "iterations": model["iterations"],
        "log_likelihood": model["log_likelihood"],
        "marginal_observation_probability": model["marginal_observation_probability"],
        "treatment_arm_observation_probabilities": model["treatment_arm_observation_probabilities"],
        "coefficients": [
            {"id": name, "value": value}
            for name, value in zip(["intercept", "treatment", *predictor_ids], model["coefficients"])
        ],
        "standardization": [
            {"id": predictor_id, **standardization}
            for predictor_id, standardization in zip(predictor_ids, model["standardization"])
        ],
    }


def expected_analysis(
    request: dict[str, Any],
    facts: dict[str, Any],
    draws: list[dict[str, Any]],
    successful: list[float],
) -> dict[str, Any]:
    point = facts["preflight"]
    adjusted = dict(point["combined_weighted_effects"])
    if len(successful) < 2:
        standard_error = None
        lower = None
        upper = None
    else:
        standard_error = math.sqrt(_sample_variance(successful))
        lower = adjusted["risk_difference"] - Z_95 * standard_error
        upper = adjusted["risk_difference"] + Z_95 * standard_error
    adjusted["risk_difference_standard_error"] = standard_error
    adjusted["risk_difference_lower"] = lower
    adjusted["risk_difference_upper"] = upper
    failed = len(draws) - len(successful)
    return {
        "propensity_score": propensity_result(request, facts, point),
        "observation_model": observation_model_result(request, facts, point),
        "weighting": point["weight_summary"],
        "diagnostics": {
            "propensity": point["propensity_summary"],
            "observation": point["observation_summary"],
            "balance": [
                {
                    "id": pre["id"],
                    "pre_weight": pre,
                    "treatment_weight": treatment,
                    "combined_observed_weight": combined,
                }
                for pre, treatment, combined in zip(
                    point["pre_balance"],
                    point["treatment_weight_balance"],
                    point["combined_weight_balance"],
                )
            ],
            "max_abs_pre_smd": point["max_abs_pre_smd"],
            "max_abs_treatment_weight_smd": point["max_abs_treatment_weight_smd"],
            "max_abs_combined_observed_weight_smd": point["max_abs_combined_weight_smd"],
            "automatic_acceptance_thresholds": False,
        },
        "effects": {
            "primary_estimand": "source_cohort_ate_risk_difference_if_no_outcome_loss",
            "observed_complete_case_unadjusted": point["unadjusted_effects"],
            "observed_complete_case_stabilized_ate_iptw": point["treatment_weighted_effects"],
            "stabilized_ate_iptw_ipow": adjusted,
            "causal_validity_determined": False,
        },
        "bootstrap": {
            "method": "arm_stratified_nonparametric_bootstrap_refit",
            "iterations": len(draws),
            "successful": len(successful),
            "failed": failed,
            "seed": request["uncertainty"]["seed"],
            "prng": {"algorithm": RNG_ALGORITHM, "version": RNG_VERSION},
            "interval": "normal_bootstrap_95_percent",
            "failure_policy": "retain_and_block_review",
        },
        "complete": failed == 0 and len(successful) == len(draws),
    }


def expected_warnings(analysis: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    overlap = analysis["diagnostics"]["propensity"]["empirical_range_intersection"]
    if not overlap["exists"]:
        warnings.append("The two empirical propensity-score ranges do not intersect; Human positivity and target-population review is required.")
    if analysis["bootstrap"]["failed"]:
        warnings.append("One or more bootstrap refits failed; the result is incomplete and cannot enter Human method acceptance.")
    return warnings


def _close(left: Any, right: Any, tolerance: float = TOLERANCE) -> bool:
    if left is None or right is None:
        return left is right
    return finite(left) and finite(right) and abs(float(left) - float(right)) <= tolerance * max(1.0, abs(float(left)), abs(float(right)))


def _deep_close(left: Any, right: Any, path: str, errors: list[str]) -> None:
    if isinstance(right, dict):
        if not isinstance(left, dict) or set(left) != set(right):
            errors.append(f"{path} fields differ from deterministic replay")
            return
        for key in right:
            _deep_close(left[key], right[key], f"{path}.{key}", errors)
    elif isinstance(right, list):
        if not isinstance(left, list) or len(left) != len(right):
            errors.append(f"{path} length differs from deterministic replay")
            return
        for index, expected in enumerate(right):
            _deep_close(left[index], expected, f"{path}[{index}]", errors)
    elif finite(right):
        if not _close(left, right):
            errors.append(f"{path} differs from deterministic replay")
    elif left != right:
        errors.append(f"{path} differs from deterministic replay")


def current_python_identity() -> dict[str, str]:
    executable = Path(sys.executable).resolve()
    return {
        "python_version": sys.version.split()[0],
        "python_executable_sha256": digest(executable.read_bytes()),
    }


def audit_result(result_path: Path, workspace: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        if result_path.is_symlink() or not result_path.resolve(strict=True).is_relative_to(workspace.resolve(strict=True)):
            return {"complete": False, "reviewable": False, "errors": ["result path is unsafe or symlinked"]}
    except OSError:
        return {"complete": False, "reviewable": False, "errors": ["result path is missing"]}
    try:
        result, result_raw = load_json(result_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {"complete": False, "reviewable": False, "errors": [f"result cannot be read: {error}"]}
    if not exact(result, RESULT_FIELDS):
        return {"complete": False, "reviewable": False, "errors": ["result fields do not match schema 0.2.0"]}
    if result.get("schema_version") != RESULT_SCHEMA_VERSION or not safe_id(result.get("execution_id")):
        errors.append("result schema_version or execution_id is invalid")
    request_binding = result.get("request")
    if not exact(request_binding, {"path", "sha256"}):
        errors.append("result request binding fields are invalid")
        request_binding = {}
    request_path = resolve_file(workspace, request_binding.get("path"))
    request: dict[str, Any] = {}
    facts: dict[str, Any] = {}
    if request_path is None or SHA256.fullmatch(str(request_binding.get("sha256", ""))) is None:
        errors.append("result request binding is unsafe")
    else:
        try:
            request, request_raw = load_json(request_path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"bound request cannot be read: {error}")
        else:
            if digest(request_raw) != request_binding["sha256"]:
                errors.append("bound request sha256 does not match current bytes")
            request_errors, facts = validate_request(request, workspace)
            errors.extend(f"bound request: {error}" for error in request_errors)
            if request.get("execution_id") != result.get("execution_id"):
                errors.append("result execution_id does not match request")
    for key in ("source_data", "evidence_synthesis"):
        binding = result.get(key)
        expected = request.get(key, {}) if request else {}
        if not exact(binding, {"path", "sha256"}) or binding != {"path": expected.get("path"), "sha256": expected.get("sha256")}:
            errors.append(f"result {key} binding does not match the request")
    runtime = result.get("runtime")
    if not exact(runtime, {"evaluator", "python_version", "python_executable_sha256", "evaluator_source"}):
        errors.append("result runtime fields are invalid")
    else:
        if runtime.get("evaluator") != EVALUATOR or not text(runtime.get("python_version")) or SHA256.fullmatch(str(runtime.get("python_executable_sha256", ""))) is None:
            errors.append("result runtime identity is invalid")
        elif {
            "python_version": runtime.get("python_version"),
            "python_executable_sha256": runtime.get("python_executable_sha256"),
        } != current_python_identity():
            errors.append("result Python runtime does not match the current replay runtime")
        evaluator_source = runtime.get("evaluator_source")
        if not exact(evaluator_source, {"path", "sha256"}):
            errors.append("result evaluator_source binding is invalid")
        else:
            evaluator_path = resolve_file(workspace, evaluator_source.get("path"))
            if evaluator_path is None or digest(evaluator_path.read_bytes()) != evaluator_source.get("sha256"):
                errors.append("result evaluator_source bytes are stale or unsafe")
            elif evaluator_path.read_bytes() != Path(__file__).read_bytes():
                errors.append("result evaluator_source is not the current bundled evaluator")
    if result.get("target_trial") != request.get("target_trial"):
        errors.append("result target_trial does not match the bound request")
    if result.get("estimand") != request.get("estimand"):
        errors.append("result estimand does not match the bound request")
    bootstrap = result.get("bootstrap")
    if not exact(bootstrap, {"method", "iterations", "successful", "failed", "seed", "prng", "interval", "failure_policy", "draws"}):
        errors.append("result bootstrap fields are invalid")
    else:
        draws_binding = bootstrap.get("draws")
        if not exact(draws_binding, {"path", "sha256"}):
            errors.append("result bootstrap draws binding is invalid")
        else:
            draws_path = resolve_file(workspace, draws_binding.get("path"))
            if draws_path is None or SHA256.fullmatch(str(draws_binding.get("sha256", ""))) is None:
                errors.append("result bootstrap draws path or hash is invalid")
            elif digest(draws_path.read_bytes()) != draws_binding["sha256"]:
                errors.append("result bootstrap draws sha256 does not match current bytes")
    if not errors and request and facts:
        draws, successful = execute_bootstrap(request, facts)
        expected_draw_raw = canonical_draw_bytes(draws)
        draws_path = resolve_file(workspace, result["bootstrap"]["draws"]["path"])
        if draws_path is None or draws_path.read_bytes() != expected_draw_raw:
            errors.append("bootstrap draw bytes do not reproduce the complete fixed PCG32 replay")
        expected = expected_analysis(request, facts, draws, successful)
        _deep_close(result.get("propensity_score"), expected["propensity_score"], "propensity_score", errors)
        _deep_close(result.get("observation_model"), expected["observation_model"], "observation_model", errors)
        _deep_close(result.get("weighting"), expected["weighting"], "weighting", errors)
        _deep_close(result.get("diagnostics"), expected["diagnostics"], "diagnostics", errors)
        _deep_close(result.get("effects"), expected["effects"], "effects", errors)
        expected_bootstrap = {**expected["bootstrap"], "draws": result["bootstrap"]["draws"]}
        _deep_close(result.get("bootstrap"), expected_bootstrap, "bootstrap", errors)
        expected_status = "awaiting_method_review" if expected["complete"] else "incomplete_bootstrap"
        if result.get("status") != expected_status:
            errors.append("result status does not match bootstrap completeness")
        if result.get("warnings") != expected_warnings(expected):
            errors.append("result warnings do not match deterministic diagnostics")
    if result.get("cross_implementation") != {
        "portable_replay": "complete_point_diagnostics_and_bootstrap",
        "native_replay": "point_estimate_and_diagnostics_only",
        "uncertainty_native_replay": False,
    }:
        errors.append("result cross_implementation scope is invalid")
    if not isinstance(result.get("warnings"), list) or any(not text(value) for value in result["warnings"]):
        errors.append("result warnings must be text")
    if result.get("limitations") != request.get("limitations"):
        errors.append("result limitations must exactly preserve the request")
    if result.get("human_gate") != {
        "status": "awaiting_method_review",
        "required_checks": REQUIRED_REVIEW_CHECKS,
        "automatic_downstream_use": False,
        "causal_validity_determined": False,
    }:
        errors.append("result human_gate is invalid")
    complete = not errors and result.get("status") == "awaiting_method_review" and result.get("bootstrap", {}).get("failed") == 0
    return {
        "complete": complete,
        "reviewable": complete,
        "result_sha256": digest(result_raw),
        "execution_id": result.get("execution_id") if safe_id(result.get("execution_id")) else None,
        "errors": errors,
    }
