"""Hash-bound deterministic and probabilistic uncertainty for decision trees."""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from math import exp, isfinite, sqrt
from typing import Any

from .decision_tree import (
    SCHEMA_VERSION as DECISION_TREE_SCHEMA_VERSION,
    DecisionTreeSpecification,
    run_decision_tree,
)
from .model import ModelValidationError, STRATEGY_ID_PATTERN
from .uncertainty import Pcg32, PRNG_ALGORITHM, PRNG_VERSION


SCHEMA_VERSION = "0.1.0"
ENGINE_VERSION = "0.1.0"
ANALYSIS_TYPE = "decision_tree_uncertainty"
MAX_PARAMETERS = 64
MIN_ITERATIONS = 100
MAX_ITERATIONS = 10_000


@dataclass(frozen=True)
class Parameter:
    identifier: str
    label: str
    target: dict[str, Any]
    mutation_keys: tuple[tuple[Any, ...], ...]
    base_value: float
    low: float
    high: float
    deterministic_basis_ids: tuple[str, ...]
    deterministic_rationale: str
    distribution: dict[str, Any]
    probabilistic_basis_ids: tuple[str, ...]
    probabilistic_rationale: str


def run_decision_tree_uncertainty(
    analysis: dict[str, Any],
    analysis_raw: bytes,
    uncertainty: dict[str, Any],
    uncertainty_raw: bytes,
) -> dict[str, Any]:
    """Validate and execute one exact decision-tree uncertainty plan."""

    base_specification = DecisionTreeSpecification.from_dict(analysis)
    if base_specification.schema_version != DECISION_TREE_SCHEMA_VERSION:
        raise ModelValidationError(
            "decision-tree uncertainty requires current decision tree schema 0.2.0"
        )
    if (
        base_specification.willingness_to_pay is None
        or base_specification.willingness_to_pay <= 0
    ):
        raise ModelValidationError(
            "decision-tree uncertainty requires a positive willingness_to_pay"
        )
    plan = _mapping(uncertainty, "uncertainty")
    _exact_fields(
        plan,
        {
            "schema_version",
            "analysis_type",
            "uncertainty_id",
            "analysis_input",
            "parameters",
            "probabilistic_analysis",
        },
        "uncertainty",
    )
    if plan.get("schema_version") != SCHEMA_VERSION:
        raise ModelValidationError(
            f"unsupported decision-tree uncertainty schema_version; expected {SCHEMA_VERSION}"
        )
    if plan.get("analysis_type") != ANALYSIS_TYPE:
        raise ModelValidationError(f"analysis_type must be {ANALYSIS_TYPE}")
    uncertainty_id = _identifier(plan.get("uncertainty_id"), "uncertainty_id")
    _validate_analysis_binding(plan.get("analysis_input"), analysis_raw)

    raw_parameters = _array(plan.get("parameters"), "parameters")
    if not 1 <= len(raw_parameters) <= MAX_PARAMETERS:
        raise ModelValidationError(
            f"parameters must contain from 1 to {MAX_PARAMETERS} entries"
        )
    parameters = tuple(
        _parameter(item, index, analysis, base_specification.time_horizon_years)
        for index, item in enumerate(raw_parameters)
    )
    if len({item.identifier for item in parameters}) != len(parameters):
        raise ModelValidationError("parameter ids must be unique")
    occupied: set[tuple[Any, ...]] = set()
    for parameter in parameters:
        overlap = occupied.intersection(parameter.mutation_keys)
        if overlap:
            raise ModelValidationError(
                f"parameter {parameter.identifier} overlaps another parameter target"
            )
        occupied.update(parameter.mutation_keys)

    psa = _mapping(plan.get("probabilistic_analysis"), "probabilistic_analysis")
    _exact_fields(
        psa,
        {
            "iterations",
            "seed",
            "convergence",
            "independence_rationale",
            "omitted_uncertainties",
        },
        "probabilistic_analysis",
    )
    iterations = _strict_int(psa.get("iterations"), "probabilistic_analysis.iterations")
    if not MIN_ITERATIONS <= iterations <= MAX_ITERATIONS:
        raise ModelValidationError(
            f"probabilistic_analysis.iterations must be from {MIN_ITERATIONS} to {MAX_ITERATIONS}"
        )
    seed = _strict_int(psa.get("seed"), "probabilistic_analysis.seed")
    if not 0 <= seed <= (1 << 53) - 1:
        raise ModelValidationError("probabilistic_analysis.seed must be a non-negative JSON-safe integer")
    convergence = _convergence(
        psa.get("convergence"), iterations, "probabilistic_analysis.convergence"
    )
    independence_rationale = _text(
        psa.get("independence_rationale"),
        "probabilistic_analysis.independence_rationale",
    )
    omitted = tuple(
        _omission(item, index)
        for index, item in enumerate(
            _array(psa.get("omitted_uncertainties"), "probabilistic_analysis.omitted_uncertainties")
        )
    )

    base_result = run_decision_tree(base_specification).to_dict()
    deterministic = [
        _run_dsa(analysis, parameter) for parameter in parameters
    ]
    probabilistic = _run_psa(
        analysis,
        parameters,
        iterations,
        seed,
        convergence,
        independence_rationale,
        omitted,
    )
    return {
        "analysis_id": base_specification.analysis_id,
        "analysis_type": ANALYSIS_TYPE,
        "uncertainty_id": uncertainty_id,
        "schema_version": SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "analysis_schema_version": base_specification.schema_version,
        "analysis_input_sha256": hashlib.sha256(analysis_raw).hexdigest(),
        "uncertainty_input_sha256": hashlib.sha256(uncertainty_raw).hexdigest(),
        "economic_basis": base_specification.economic_basis.to_dict(),
        "strategy_order": list(base_specification.strategy_order),
        "baseline_strategy_id": base_specification.baseline_strategy_id,
        "willingness_to_pay": base_specification.willingness_to_pay,
        "base_case": _summary(base_result),
        "deterministic_analysis": deterministic,
        "probabilistic_analysis": probabilistic,
        "warnings": [
            "Only the explicitly declared parameter uncertainty is represented.",
            "The PSA does not establish evidence fitness, structural validity, independent validation, or a research conclusion.",
            "Parameter independence is a researcher-supplied assumption and is not inferred by the engine.",
        ],
    }


def _run_dsa(analysis: dict[str, Any], parameter: Parameter) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for label, value in (("low", parameter.low), ("high", parameter.high)):
        payload = copy.deepcopy(analysis)
        _apply(payload, parameter, value)
        results[label] = _summary(
            run_decision_tree(DecisionTreeSpecification.from_dict(payload)).to_dict()
        )
    return {
        "parameter_id": parameter.identifier,
        "label": parameter.label,
        "target": parameter.target,
        "low_value": parameter.low,
        "high_value": parameter.high,
        "deterministic_basis_ids": list(parameter.deterministic_basis_ids),
        "deterministic_rationale": parameter.deterministic_rationale,
        "low_result": results["low"],
        "high_result": results["high"],
    }


def _run_psa(
    analysis: dict[str, Any],
    parameters: tuple[Parameter, ...],
    iterations: int,
    seed: int,
    convergence: dict[str, Any],
    independence_rationale: str,
    omitted: tuple[dict[str, str], ...],
) -> dict[str, Any]:
    rng = Pcg32(seed)
    strategy_order = tuple(str(item) for item in analysis["strategy_order"])
    optimal_counts = {strategy_id: 0 for strategy_id in strategy_order}
    tie_count = 0
    sums = {
        strategy_id: {"cost": 0.0, "qaly": 0.0, "nmb": 0.0}
        for strategy_id in strategy_order
    }
    samples: list[dict[str, Any]] = []
    checkpoints: list[dict[str, Any]] = []
    checkpoint_set = set(convergence["checkpoints"])
    for iteration in range(1, iterations + 1):
        payload = copy.deepcopy(analysis)
        values: dict[str, float] = {}
        for parameter in parameters:
            value = _sample(rng, parameter.distribution)
            _apply(payload, parameter, value)
            values[parameter.identifier] = value
        result = run_decision_tree(
            DecisionTreeSpecification.from_dict(payload)
        ).to_dict()
        strategies = {
            strategy_id: {
                "total_cost": result["strategies"][strategy_id]["total_cost"],
                "total_qaly": result["strategies"][strategy_id]["total_qaly"],
                "net_monetary_benefit": result["strategies"][strategy_id]["net_monetary_benefit"],
            }
            for strategy_id in strategy_order
        }
        for strategy_id, row in strategies.items():
            sums[strategy_id]["cost"] += row["total_cost"]
            sums[strategy_id]["qaly"] += row["total_qaly"]
            sums[strategy_id]["nmb"] += row["net_monetary_benefit"]
        optimum = result["optimal_at_primary_threshold"]
        if optimum["strategy_id"] is None:
            tie_count += 1
            optimal_ids = optimum["tied_strategy_ids"]
        else:
            optimal_counts[optimum["strategy_id"]] += 1
            optimal_ids = [optimum["strategy_id"]]
        samples.append(
            {
                "iteration": iteration,
                "parameter_values": values,
                "strategies": strategies,
                "optimal_strategy_ids": optimal_ids,
            }
        )
        if iteration in checkpoint_set:
            probabilities = {
                strategy_id: optimal_counts[strategy_id] / iteration
                for strategy_id in strategy_order
            }
            tie_probability = tie_count / iteration
            checkpoint_mcse = max(
                sqrt(probability * (1.0 - probability) / iteration)
                for probability in [*probabilities.values(), tie_probability]
            )
            checkpoints.append(
                {
                    "iterations": iteration,
                    "strategy_optimal_probabilities": probabilities,
                    "tie_probability": tie_probability,
                    "max_probability_mcse": checkpoint_mcse,
                }
            )
    final = checkpoints[-1]
    previous = checkpoints[-2]
    probability_drift = max(
        [
            abs(
                final["strategy_optimal_probabilities"][strategy_id]
                - previous["strategy_optimal_probabilities"][strategy_id]
            )
            for strategy_id in strategy_order
        ]
        + [abs(final["tie_probability"] - previous["tie_probability"])]
    )
    return {
        "iterations": iterations,
        "prng": {"algorithm": PRNG_ALGORITHM, "version": PRNG_VERSION, "seed": seed},
        "independence_rationale": independence_rationale,
        "omitted_uncertainties": list(omitted),
        "parameter_distributions": [
            {
                "parameter_id": parameter.identifier,
                "distribution": parameter.distribution,
                "basis_ids": list(parameter.probabilistic_basis_ids),
                "rationale": parameter.probabilistic_rationale,
            }
            for parameter in parameters
        ],
        "mean_outcomes": {
            strategy_id: {
                "total_cost": sums[strategy_id]["cost"] / iterations,
                "total_qaly": sums[strategy_id]["qaly"] / iterations,
                "net_monetary_benefit": sums[strategy_id]["nmb"] / iterations,
            }
            for strategy_id in strategy_order
        },
        "optimal_counts": optimal_counts,
        "tie_count": tie_count,
        "optimal_probabilities": {
            strategy_id: count / iterations
            for strategy_id, count in optimal_counts.items()
        },
        "tie_probability": tie_count / iterations,
        "convergence": {
            "passed": (
                final["max_probability_mcse"] <= convergence["max_probability_mcse"]
                and probability_drift <= convergence["max_probability_drift"]
            ),
            "probability_drift": probability_drift,
            "max_probability_mcse": convergence["max_probability_mcse"],
            "max_probability_drift": convergence["max_probability_drift"],
            "checkpoints": checkpoints,
        },
        "samples": samples,
    }


def _summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_order": result["strategy_order"],
        "baseline_strategy_id": result["baseline_strategy_id"],
        "strategies": {
            strategy_id: {
                "name": row["name"],
                "total_cost": row["total_cost"],
                "total_qaly": row["total_qaly"],
                "net_monetary_benefit": row["net_monetary_benefit"],
            }
            for strategy_id, row in result["strategies"].items()
        },
        "pairwise_vs_baseline": result["pairwise_vs_baseline"],
        "fully_incremental_analysis": result["fully_incremental_analysis"],
        "optimal_at_primary_threshold": result["optimal_at_primary_threshold"],
    }


def _parameter(
    raw: Any,
    index: int,
    analysis: dict[str, Any],
    horizon: float,
) -> Parameter:
    path = f"parameters[{index}]"
    value = _mapping(raw, path)
    _exact_fields(
        value,
        {"id", "label", "target", "deterministic", "probabilistic"},
        path,
    )
    target, mutation_keys, base, provenance, kind = _target(
        value.get("target"), path, analysis
    )
    deterministic = _mapping(value.get("deterministic"), f"{path}.deterministic")
    _exact_fields(
        deterministic,
        {"low", "high", "basis_ids", "rationale"},
        f"{path}.deterministic",
    )
    low = _finite(deterministic.get("low"), f"{path}.deterministic.low")
    high = _finite(deterministic.get("high"), f"{path}.deterministic.high")
    if low >= high or not low <= base <= high:
        raise ModelValidationError(f"{path} deterministic bounds must bracket the base value")
    _validate_domain(kind, low, high, horizon, f"{path}.deterministic")
    deterministic_basis = _basis_ids(
        deterministic.get("basis_ids"), f"{path}.deterministic.basis_ids", provenance
    )
    probabilistic = _mapping(value.get("probabilistic"), f"{path}.probabilistic")
    distribution, probabilistic_basis, probabilistic_rationale = _distribution(
        probabilistic, kind, horizon, provenance, f"{path}.probabilistic"
    )
    return Parameter(
        identifier=_identifier(value.get("id"), f"{path}.id"),
        label=_text(value.get("label"), f"{path}.label"),
        target=target,
        mutation_keys=mutation_keys,
        base_value=base,
        low=low,
        high=high,
        deterministic_basis_ids=deterministic_basis,
        deterministic_rationale=_text(
            deterministic.get("rationale"), f"{path}.deterministic.rationale"
        ),
        distribution=distribution,
        probabilistic_basis_ids=probabilistic_basis,
        probabilistic_rationale=probabilistic_rationale,
    )


def _target(
    raw: Any, path: str, analysis: dict[str, Any]
) -> tuple[dict[str, Any], tuple[tuple[Any, ...], ...], float, set[str], str]:
    target = _mapping(raw, f"{path}.target")
    kind = target.get("kind")
    expected = {"kind", "strategy_id", "node_id"}
    if kind == "branch_probability":
        expected.update({"branch_index", "complement_branch_index"})
    _exact_fields(target, expected, f"{path}.target")
    if kind not in {"branch_probability", "terminal_cost", "terminal_qaly"}:
        raise ModelValidationError(f"{path}.target.kind is unsupported")
    strategy_id = _identifier(target.get("strategy_id"), f"{path}.target.strategy_id")
    node_id = _identifier(target.get("node_id"), f"{path}.target.node_id")
    try:
        node = analysis["strategies"][strategy_id]["nodes"][node_id]
    except (KeyError, TypeError) as error:
        raise ModelValidationError(f"{path}.target does not identify a decision-tree node") from error
    if kind == "branch_probability":
        branches = node.get("branches") if isinstance(node, dict) else None
        if not isinstance(branches, list) or len(branches) != 2:
            raise ModelValidationError("branch-probability uncertainty requires exactly two branches")
        branch_index = _strict_int(target.get("branch_index"), f"{path}.target.branch_index")
        complement_index = _strict_int(
            target.get("complement_branch_index"), f"{path}.target.complement_branch_index"
        )
        if {branch_index, complement_index} != {0, 1}:
            raise ModelValidationError("branch and complement indices must identify the two different branches")
        sourced = _mapping(branches[branch_index].get("probability"), f"{path}.target.probability")
        base = _finite(sourced.get("value"), f"{path}.target.probability.value")
        keys = (
            (strategy_id, node_id, "probability", branch_index),
            (strategy_id, node_id, "probability", complement_index),
        )
    else:
        if not isinstance(node, dict) or node.get("type") != "terminal":
            raise ModelValidationError(f"{kind} uncertainty requires a terminal node")
        field = "cost" if kind == "terminal_cost" else "qaly"
        sourced = _mapping(node.get(field), f"{path}.target.{field}")
        base = _finite(sourced.get("value"), f"{path}.target.{field}.value")
        keys = ((strategy_id, node_id, field),)
    provenance = {
        item
        for field in ("source_ids", "assumption_ids")
        for item in sourced.get(field, [])
        if isinstance(item, str) and item.strip()
    }
    return dict(target), keys, base, provenance, str(kind)


def _distribution(
    value: dict[str, Any],
    target_kind: str,
    horizon: float,
    provenance: set[str],
    path: str,
) -> tuple[dict[str, Any], tuple[str, ...], str]:
    kind = value.get("type")
    common = {"type", "basis_ids", "rationale"}
    if kind == "uniform":
        _exact_fields(value, common | {"low", "high"}, path)
        low = _finite(value.get("low"), f"{path}.low")
        high = _finite(value.get("high"), f"{path}.high")
        if low >= high:
            raise ModelValidationError(f"{path}.low must be less than high")
        _validate_domain(target_kind, low, high, horizon, path)
        distribution = {"type": "uniform", "low": low, "high": high}
    elif kind == "beta" and target_kind == "branch_probability":
        _exact_fields(value, common | {"alpha", "beta"}, path)
        distribution = {
            "type": "beta",
            "alpha": _positive(value.get("alpha"), f"{path}.alpha"),
            "beta": _positive(value.get("beta"), f"{path}.beta"),
        }
    elif kind == "gamma" and target_kind == "terminal_cost":
        _exact_fields(value, common | {"shape", "scale"}, path)
        distribution = {
            "type": "gamma",
            "shape": _positive(value.get("shape"), f"{path}.shape"),
            "scale": _positive(value.get("scale"), f"{path}.scale"),
        }
    elif kind == "lognormal" and target_kind == "terminal_cost":
        _exact_fields(value, common | {"mu_log", "sigma_log"}, path)
        distribution = {
            "type": "lognormal",
            "mu_log": _finite(value.get("mu_log"), f"{path}.mu_log"),
            "sigma_log": _positive(value.get("sigma_log"), f"{path}.sigma_log"),
        }
    else:
        raise ModelValidationError(
            f"{path}.type is not admitted for {target_kind}"
        )
    return (
        distribution,
        _basis_ids(value.get("basis_ids"), f"{path}.basis_ids", provenance),
        _text(value.get("rationale"), f"{path}.rationale"),
    )


def _apply(payload: dict[str, Any], parameter: Parameter, value: float) -> None:
    target = parameter.target
    node = payload["strategies"][target["strategy_id"]]["nodes"][target["node_id"]]
    kind = target["kind"]
    if kind == "branch_probability":
        node["branches"][target["branch_index"]]["probability"]["value"] = value
        node["branches"][target["complement_branch_index"]]["probability"]["value"] = 1.0 - value
    elif kind == "terminal_cost":
        node["cost"]["value"] = value
    else:
        node["qaly"]["value"] = value


def _sample(rng: Pcg32, distribution: dict[str, Any]) -> float:
    kind = distribution["type"]
    if kind == "uniform":
        return distribution["low"] + (distribution["high"] - distribution["low"]) * rng.uniform_open()
    if kind == "beta":
        return rng.beta(distribution["alpha"], distribution["beta"])
    if kind == "gamma":
        return rng.gamma(distribution["shape"], distribution["scale"])
    if kind == "lognormal":
        value = exp(distribution["mu_log"] + distribution["sigma_log"] * rng.normal())
        if not isfinite(value):
            raise ModelValidationError("lognormal sample is not finite")
        return value
    raise ModelValidationError(f"unsupported distribution {kind}")


def _validate_analysis_binding(raw: Any, analysis_raw: bytes) -> None:
    binding = _mapping(raw, "analysis_input")
    _exact_fields(binding, {"path", "content_sha256"}, "analysis_input")
    if binding.get("path") != "heor/decision-tree-plan.json":
        raise ModelValidationError("analysis_input.path must be heor/decision-tree-plan.json")
    expected = hashlib.sha256(analysis_raw).hexdigest()
    if binding.get("content_sha256") != expected:
        raise ModelValidationError("analysis_input.content_sha256 does not match the current analysis bytes")


def _omission(raw: Any, index: int) -> dict[str, str]:
    path = f"probabilistic_analysis.omitted_uncertainties[{index}]"
    value = _mapping(raw, path)
    _exact_fields(value, {"item", "rationale"}, path)
    return {
        "item": _text(value.get("item"), f"{path}.item"),
        "rationale": _text(value.get("rationale"), f"{path}.rationale"),
    }


def _convergence(raw: Any, iterations: int, path: str) -> dict[str, Any]:
    value = _mapping(raw, path)
    _exact_fields(
        value,
        {"checkpoints", "max_probability_mcse", "max_probability_drift"},
        path,
    )
    checkpoints = tuple(
        _strict_int(item, f"{path}.checkpoints")
        for item in _array(value.get("checkpoints"), f"{path}.checkpoints")
    )
    if (
        len(checkpoints) < 2
        or tuple(sorted(set(checkpoints))) != checkpoints
        or checkpoints[0] < 1
        or checkpoints[-1] != iterations
    ):
        raise ModelValidationError(
            f"{path}.checkpoints must contain at least two unique increasing values ending at iterations"
        )
    max_mcse = _positive(value.get("max_probability_mcse"), f"{path}.max_probability_mcse")
    max_drift = _positive(value.get("max_probability_drift"), f"{path}.max_probability_drift")
    if max_mcse > 0.1 or max_drift > 0.1:
        raise ModelValidationError(f"{path} probability thresholds must not exceed 0.1")
    return {
        "checkpoints": checkpoints,
        "max_probability_mcse": max_mcse,
        "max_probability_drift": max_drift,
    }


def _basis_ids(raw: Any, path: str, allowed: set[str]) -> tuple[str, ...]:
    values = tuple(_text(item, path) for item in _array(raw, path))
    if not values or len(set(values)) != len(values):
        raise ModelValidationError(f"{path} must contain unique evidence or assumption ids")
    if not set(values).issubset(allowed):
        raise ModelValidationError(f"{path} must be linked by the targeted decision-tree input")
    return values


def _validate_domain(kind: str, low: float, high: float, horizon: float, path: str) -> None:
    if kind == "branch_probability" and not 0.0 <= low < high <= 1.0:
        raise ModelValidationError(f"{path} probability values must stay from zero to one")
    if kind == "terminal_cost" and low < 0.0:
        raise ModelValidationError(f"{path} cost values must not be negative")
    if kind == "terminal_qaly" and not -horizon <= low < high <= horizon:
        raise ModelValidationError(f"{path} QALY values must stay within the declared horizon")


def _mapping(raw: Any, path: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ModelValidationError(f"{path} must be an object")
    return raw


def _array(raw: Any, path: str) -> list[Any]:
    if not isinstance(raw, list):
        raise ModelValidationError(f"{path} must be an array")
    return raw


def _exact_fields(value: dict[str, Any], expected: set[str], path: str) -> None:
    if set(value) != expected:
        raise ModelValidationError(f"{path} fields do not match the admitted contract")


def _strict_int(raw: Any, path: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ModelValidationError(f"{path} must be an integer")
    return raw


def _finite(raw: Any, path: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)) or not isfinite(float(raw)):
        raise ModelValidationError(f"{path} must be a finite number")
    return float(raw)


def _positive(raw: Any, path: str) -> float:
    value = _finite(raw, path)
    if value <= 0:
        raise ModelValidationError(f"{path} must be positive")
    return value


def _text(raw: Any, path: str) -> str:
    if not isinstance(raw, str) or not raw or raw != raw.strip():
        raise ModelValidationError(f"{path} must be a non-empty trimmed string")
    if len(raw) > 500 or any(ord(character) < 32 or ord(character) == 127 for character in raw):
        raise ModelValidationError(f"{path} is too long or contains control characters")
    return raw


def _identifier(raw: Any, path: str) -> str:
    value = _text(raw, path)
    if not STRATEGY_ID_PATTERN.fullmatch(value):
        raise ModelValidationError(f"{path} must use a lowercase identifier")
    return value
