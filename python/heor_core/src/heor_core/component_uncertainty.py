"""Auditable cost, utility, and event-component uncertainty for current PSMs."""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass
from math import erf, exp, fsum, isfinite, sqrt
from typing import Any

from .economic_inputs import EconomicSpecification
from .joint_survival_uncertainty import (
    iter_joint_survival_curve_plans,
    validate_joint_survival_uncertainty,
)
from .model import ModelValidationError
from .partitioned_survival import calculate_partitioned_survival, run_partitioned_survival


SCHEMA_VERSION = "0.13.0"
JOINT_SCHEMA_VERSION = "0.14.0"
ENGINE_VERSION = "0.14.0"
JOINT_ENGINE_VERSION = "0.15.0"
ANALYSIS_SCHEMA_VERSION = "0.15.0"
PSM_SCHEMA_VERSION = "0.7.0"
MAX_PARAMETERS = 256
MAX_GROUPS = 64
MAX_GROUP_SIZE = 32

ARTIFACT_PATHS = {
    "partitioned_survival_plan": "heor/partitioned-survival-plan.json",
    "curve_materializations": "heor/survival-curve-materializations.json",
    "treatment_effect_duration": "heor/treatment-effect-duration.json",
    "cost_input_normalization": "heor/cost-input-normalization.json",
    "utility_inputs": "heor/utility-inputs.json",
    "event_disutilities": "heor/event-disutilities.json",
}
COMPONENT_ARTIFACTS = {
    "cost_input_normalization",
    "utility_inputs",
    "event_disutilities",
}


@dataclass(frozen=True)
class ComponentParameter:
    identifier: str
    label: str
    artifact: str
    target: str
    provenance_path: str
    low: float
    high: float
    distribution: dict[str, Any]
    basis_ids: tuple[str, ...]
    domain: str


@dataclass(frozen=True)
class CorrelationGroup:
    identifier: str
    parameter_ids: tuple[str, ...]
    matrix: tuple[tuple[float, ...], ...]
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
class ComponentSpecification:
    uncertainty_id: str
    analysis_id: str
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
    parameters: tuple[ComponentParameter, ...]
    correlation_groups: tuple[CorrelationGroup, ...]
    omitted_parameters: tuple[dict[str, str], ...]
    scenarios: tuple[Scenario, ...]


def run_component_uncertainty(
    analysis: dict[str, Any],
    analysis_raw: bytes,
    plan: dict[str, Any],
    plan_raw: bytes,
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
    joint_survival_manifest: dict[str, Any] | None = None,
    joint_survival_manifest_raw: bytes | None = None,
    joint_survival_draws_raw: bytes | None = None,
) -> dict[str, Any]:
    """Validate fixed bytes once, then recompute every affected component per run."""

    if analysis.get("schema_version") != ANALYSIS_SCHEMA_VERSION:
        raise ModelValidationError("uncertainty schema 0.13.0 requires analysis schema 0.15.0")
    if partitioned_plan.get("schema_version") != PSM_SCHEMA_VERSION:
        raise ModelValidationError("uncertainty schema 0.13.0 requires partitioned-survival schema 0.7.0")
    base_result = run_partitioned_survival(
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
    joint = plan.get("schema_version") == JOINT_SCHEMA_VERSION
    specification = _parse(plan, analysis, analysis_raw, artifacts, raw_inputs)
    joint_curve_plans = None
    if joint:
        if (
            joint_survival_manifest is None
            or joint_survival_manifest_raw is None
            or joint_survival_draws_raw is None
        ):
            raise ModelValidationError(
                "uncertainty schema 0.14.0 requires joint survival manifest and draw bytes"
            )
        validate_joint_survival_uncertainty(
            analysis,
            analysis_raw,
            partitioned_plan,
            partitioned_raw,
            materializations,
            materializations_raw,
            joint_survival_manifest,
            joint_survival_manifest_raw,
            joint_survival_draws_raw,
            specification.iterations,
            treatment_duration_raw,
        )
        joint_curve_plans = iter_joint_survival_curve_plans(
            joint_survival_draws_raw,
            analysis["strategy_order"],
            joint_survival_manifest["time_grid_years"],
        )

    def evaluate(
        values: tuple[tuple[ComponentParameter, float], ...],
        analysis_replacements: tuple[tuple[str, Any], ...] = (),
        curve_plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        sampled_analysis = copy.deepcopy(analysis)
        sampled_artifacts = {key: copy.deepcopy(value) for key, value in artifacts.items()}
        for parameter, value in values:
            _replace(sampled_artifacts[parameter.artifact], parameter.target, value)
        for target, value in analysis_replacements:
            _replace(sampled_analysis, target, value)
        utility_schedule, event_schedule = _recompute(
            sampled_analysis,
            sampled_artifacts["cost_input_normalization"],
            sampled_artifacts["utility_inputs"],
            sampled_artifacts["event_disutilities"],
        )
        return calculate_partitioned_survival(
            EconomicSpecification.from_analysis_plan(sampled_analysis),
            partitioned_plan if curve_plan is None else curve_plan,
            utility_schedule,
            event_schedule,
        )

    deterministic = []
    for parameter in specification.parameters:
        low_result = evaluate(((parameter, parameter.low),))
        high_result = evaluate(((parameter, parameter.high),))
        low_summary = _decision_summary(low_result)
        high_summary = _decision_summary(high_result)
        deterministic.append(
            {
                "parameter_id": parameter.identifier,
                "label": parameter.label,
                "artifact": parameter.artifact,
                "target": parameter.target,
                "low_value": parameter.low,
                "high_value": parameter.high,
                "low_result": low_summary,
                "high_result": high_summary,
                "net_monetary_benefit_span_by_strategy": {
                    strategy_id: abs(
                        high_summary["strategies"][strategy_id]["net_monetary_benefit"]
                        - low_summary["strategies"][strategy_id]["net_monetary_benefit"]
                    )
                    for strategy_id in analysis["strategy_order"]
                },
            }
        )
    scenarios = [
        {
            "scenario_id": scenario.identifier,
            "label": scenario.label,
            "rationale": scenario.rationale,
            "replacements": [
                {"target": target, "value": value}
                for target, value in scenario.replacements
            ],
            "result": _decision_summary(evaluate((), scenario.replacements)),
        }
        for scenario in specification.scenarios
    ]
    probabilistic = _run_psa(
        specification, analysis["strategy_order"], evaluate, joint_curve_plans
    )
    return {
        "analysis_id": specification.analysis_id,
        "uncertainty_id": specification.uncertainty_id,
        "schema_version": JOINT_SCHEMA_VERSION if joint else SCHEMA_VERSION,
        "engine_version": JOINT_ENGINE_VERSION if joint else ENGINE_VERSION,
        "base_analysis_sha256": hashlib.sha256(analysis_raw).hexdigest(),
        "uncertainty_plan_sha256": hashlib.sha256(plan_raw).hexdigest(),
        "partitioned_survival_plan_sha256": hashlib.sha256(partitioned_raw).hexdigest(),
        "survival_curve_materializations_sha256": hashlib.sha256(materializations_raw).hexdigest(),
        "treatment_effect_duration_sha256": hashlib.sha256(treatment_duration_raw).hexdigest(),
        "cost_input_normalization_sha256": hashlib.sha256(cost_inputs_raw).hexdigest(),
        "utility_inputs_sha256": hashlib.sha256(utility_inputs_raw).hexdigest(),
        "event_disutilities_sha256": hashlib.sha256(event_inputs_raw).hexdigest(),
        **(
            {
                "joint_survival_uncertainty_sha256": hashlib.sha256(
                    joint_survival_manifest_raw
                ).hexdigest(),
                "joint_survival_draws_sha256": hashlib.sha256(
                    joint_survival_draws_raw
                ).hexdigest(),
            }
            if joint
            else {}
        ),
        "prng": {"algorithm": "pcg32-xsh-rr", "version": "1"},
        "seed": str(specification.seed),
        "calculation_classification": (
            "joint_curve_and_component_parameter_uncertainty"
            if joint
            else "component_parameter_uncertainty"
        ),
        "uncertainty_scope": (
            "joint_survival_curves_and_cost_utility_event_components"
            if joint
            else "cost_utility_event_components_only"
        ),
        "economic_basis": base_result["economic_basis"],
        "base_case": _decision_summary(base_result),
        "deterministic_analysis": deterministic,
        "probabilistic_analysis": probabilistic,
        "structural_scenarios": scenarios,
        "treatment_effect_duration_scenarios": base_result["treatment_effect_duration_scenarios"],
        "limitations": [
            (
                "Each PSA iteration combines one complete hash-bound joint survival row with the declared cost, health-state utility, and event-disutility component draws."
                if joint
                else "Only declared cost, health-state utility, and event-disutility components are sampled; survival curves remain fixed."
            ),
            *(
                [
                    "The engine verifies joint-row and component-artifact coherence but does not establish that the source posterior, paired bootstrap, component distributions, or dependence assumptions are statistically or clinically appropriate.",
                    "Dependence between the joint survival rows and component draws is not represented; the Human must justify cross-domain independence or preserve unsupported dependence as a blocker.",
                    "Curve-family selection, extrapolation assumptions, source-model validity, and treatment-effect-duration alternatives remain structural uncertainty outside this composed PSA.",
                ]
                if joint
                else []
            ),
            "Gaussian-copula matrices are Human-supplied latent-standard-normal correlations and are not inferred or converted from observed-scale correlations.",
            "Beta, Gamma, empirical joint draws, perfect correlation, and structural model averaging are not admitted in mixed component correlation groups.",
            "Per-person EVPI is conditional on represented parameter uncertainty and selected structural assumptions; it is not population EVPI or EVPPI.",
        ],
    }


def _parse(
    value: dict[str, Any],
    analysis: dict[str, Any],
    analysis_raw: bytes,
    artifacts: dict[str, dict[str, Any]],
    raw_inputs: dict[str, bytes],
) -> ComponentSpecification:
    schema_version = value.get("schema_version")
    if schema_version not in {SCHEMA_VERSION, JOINT_SCHEMA_VERSION}:
        raise ModelValidationError("component uncertainty schema_version must be 0.13.0 or 0.14.0")
    if schema_version == SCHEMA_VERSION and "joint_survival_inputs" in value:
        raise ModelValidationError(
            "joint_survival_inputs requires component uncertainty schema 0.14.0"
        )
    if value.get("status") != "ready_for_human_review":
        raise ModelValidationError("component uncertainty must be ready_for_human_review")
    if value.get("analysis_id") != analysis.get("analysis_id"):
        raise ModelValidationError("component uncertainty analysis_id does not match")
    if analysis.get("uncertainty_analysis") != {"path": "heor/uncertainty-plan.json"}:
        raise ModelValidationError("analysis plan must link heor/uncertainty-plan.json")
    _binding(value.get("base_analysis"), "heor/analysis-plan.json", analysis_raw, "base_analysis")
    bindings = _object(value.get("partitioned_survival_inputs"), "partitioned_survival_inputs")
    if set(bindings) != set(ARTIFACT_PATHS):
        raise ModelValidationError("partitioned_survival_inputs must bind all six current artifacts")
    for key, path in ARTIFACT_PATHS.items():
        _binding(bindings.get(key), path, raw_inputs[key], f"partitioned_survival_inputs.{key}")
    raw_parameters = _array(value.get("parameters"), "parameters")
    if not 1 <= len(raw_parameters) <= MAX_PARAMETERS:
        raise ModelValidationError("parameters must contain 1 to 256 entries")
    parameters = tuple(
        _parameter(raw, index, artifacts) for index, raw in enumerate(raw_parameters)
    )
    if len({parameter.identifier for parameter in parameters}) != len(parameters):
        raise ModelValidationError("component parameter ids must be unique")
    if len({(parameter.artifact, parameter.target) for parameter in parameters}) != len(parameters):
        raise ModelValidationError("component parameter artifact targets must be unique")
    psa = _object(value.get("probabilistic_analysis"), "probabilistic_analysis")
    iterations = _integer(psa.get("iterations"), "probabilistic_analysis.iterations")
    if not 1000 <= iterations <= 10000:
        raise ModelValidationError("probabilistic_analysis.iterations must be 1000 to 10000")
    threshold = _positive(analysis.get("willingness_to_pay"), "willingness_to_pay")
    threshold_config = _object(psa.get("decision_thresholds"), "decision_thresholds")
    thresholds = tuple(_nonnegative(item, "decision threshold") for item in _array(threshold_config.get("values"), "decision_thresholds.values"))
    if not 2 <= len(thresholds) <= 101 or tuple(sorted(set(thresholds))) != thresholds or threshold not in thresholds:
        raise ModelValidationError("decision thresholds must be 2-101 unique increasing values including willingness_to_pay")
    threshold_rationale = _text(
        threshold_config.get("rationale"), "decision_thresholds.rationale"
    )
    convergence = _object(psa.get("convergence"), "convergence")
    checkpoints = tuple(_integer(item, "checkpoint") for item in _array(convergence.get("checkpoints"), "checkpoints"))
    if len(checkpoints) < 2 or tuple(sorted(set(checkpoints))) != checkpoints or checkpoints[-1] != iterations or checkpoints[0] < 100:
        raise ModelValidationError("convergence checkpoints must be increasing and end at iterations")
    max_mcse = _positive(convergence.get("max_probability_mcse"), "max_probability_mcse")
    max_drift = _positive(convergence.get("max_probability_drift"), "max_probability_drift")
    if max_mcse > 0.1 or max_drift > 0.1:
        raise ModelValidationError("probability convergence thresholds must not exceed 0.1")
    correlation = _object(psa.get("correlation_handling"), "correlation_handling")
    if _array(correlation.get("known_omitted_correlations"), "known_omitted_correlations"):
        raise ModelValidationError("known omitted correlations must be resolved before review")
    groups = _correlation_groups(correlation.get("groups"), parameters)
    omitted = tuple(
        {
            "provenance_path": _text(_object(item, "omitted parameter").get("provenance_path"), "omitted provenance_path"),
            "rationale": _text(_object(item, "omitted parameter").get("rationale"), "omitted rationale"),
        }
        for item in _array(psa.get("omitted_parameters"), "omitted_parameters")
    )
    omission_paths = {item["provenance_path"] for item in omitted}
    represented_curves = {
        f"partitioned_survival.strategies.{strategy_id}.{endpoint}"
        for strategy_id in analysis["strategy_order"]
        for endpoint in ("pfs", "os")
    }
    if schema_version == SCHEMA_VERSION and not represented_curves.issubset(omission_paths):
        raise ModelValidationError("component uncertainty must explicitly omit every fixed PFS and OS curve")
    if schema_version == JOINT_SCHEMA_VERSION:
        if represented_curves & omission_paths:
            raise ModelValidationError("joint component uncertainty must not list represented PFS or OS curves as omitted")
        required_structural = {
            "partitioned_survival.structural.curve_family_selection",
            "partitioned_survival.structural.extrapolation_assumptions",
            "partitioned_survival.structural.source_model_validity",
        }
        if not required_structural.issubset(omission_paths):
            raise ModelValidationError("joint component uncertainty must declare all required structural omissions")
    scenarios = tuple(_scenario(item, index, analysis) for index, item in enumerate(_array(value.get("structural_scenarios"), "structural_scenarios")))
    if not scenarios:
        raise ModelValidationError("at least one structural scenario is required")
    seed = _integer(value.get("seed"), "seed")
    if not 0 <= seed <= (1 << 64) - 1:
        raise ModelValidationError("seed must be an unsigned 64-bit integer")
    return ComponentSpecification(
        _text(value.get("uncertainty_id"), "uncertainty_id"),
        analysis["analysis_id"], seed, iterations, threshold, thresholds,
        threshold_rationale, "declared_grid", checkpoints,
        max_mcse, max_drift,
        _text(correlation.get("independence_rationale"), "independence_rationale"),
        parameters, groups, omitted, scenarios,
    )


def _parameter(raw: Any, index: int, artifacts: dict[str, dict[str, Any]]) -> ComponentParameter:
    value = _object(raw, f"parameters[{index}]")
    if set(value) != {"id", "label", "artifact", "target", "provenance_path", "deterministic", "probabilistic"}:
        raise ModelValidationError(f"parameters[{index}] fields are invalid")
    artifact = _text(value.get("artifact"), f"parameters[{index}].artifact")
    if artifact not in COMPONENT_ARTIFACTS:
        raise ModelValidationError(f"parameters[{index}].artifact is unsupported")
    target = _text(value.get("target"), f"parameters[{index}].target")
    base, basis_ids, domain = _component_target(artifact, target, artifacts[artifact])
    provenance = _text(value.get("provenance_path"), f"parameters[{index}].provenance_path")
    expected_provenance = artifact + "." + ".".join(_tokens(target))
    if provenance != expected_provenance:
        raise ModelValidationError(f"parameters[{index}].provenance_path must equal {expected_provenance}")
    dsa = _object(value.get("deterministic"), "deterministic")
    low = _finite(dsa.get("low"), "deterministic.low")
    high = _finite(dsa.get("high"), "deterministic.high")
    _text(dsa.get("rationale"), "deterministic.rationale")
    if not low < high or not low <= base <= high:
        raise ModelValidationError(f"parameters[{index}] DSA bounds must bracket the base")
    _domain(low, domain, "DSA low")
    _domain(high, domain, "DSA high")
    distribution = _object(value.get("probabilistic"), "probabilistic")
    declared_basis = tuple(_text(item, "basis id") for item in _array(distribution.get("basis_ids"), "basis_ids"))
    if not declared_basis or len(set(declared_basis)) != len(declared_basis) or not set(declared_basis).issubset(set(basis_ids)):
        raise ModelValidationError(f"parameters[{index}] distribution basis_ids are not target-linked")
    _text(distribution.get("rationale"), "distribution.rationale")
    _validate_distribution(distribution, domain)
    return ComponentParameter(
        _text(value.get("id"), f"parameters[{index}].id"),
        _text(value.get("label"), f"parameters[{index}].label"),
        artifact, target, provenance, low, high, copy.deepcopy(distribution), declared_basis, domain,
    )


def _component_target(artifact: str, target: str, value: dict[str, Any]) -> tuple[float, tuple[str, ...], str]:
    tokens = _tokens(target)
    if len(tokens) < 4 or tokens[0] != "items" or tokens[1] not in value.get("items", {}):
        raise ModelValidationError("component target must name an existing item")
    item = value["items"][tokens[1]]
    domain: str | None = None
    basis: Any = None
    if artifact == "cost_input_normalization":
        if tokens[2:] == ["annual_quantity", "value"]:
            domain, basis = "nonnegative", item["annual_quantity"].get("basis_ids")
        elif tokens[2:] == ["unit_price", "amount"]:
            domain, basis = "nonnegative", item["unit_price"].get("basis_ids")
        elif len(tokens) == 5 and tokens[2] == "adjustments" and tokens[3].isdigit() and tokens[4] == "factor":
            adjustment = item["adjustments"][int(tokens[3])]
            domain, basis = "positive", adjustment.get("basis_ids")
    elif artifact == "utility_inputs":
        if tokens[2:] == ["source_utility", "value"] and item.get("state_id") != "dead":
            domain, basis = "utility", item["source_utility"].get("basis_ids")
        elif len(tokens) == 6 and tokens[2] == "adjustments" and tokens[3].isdigit() and tokens[4] == "factors" and tokens[5].isdigit():
            adjustment = item["adjustments"][int(tokens[3])]
            domain, basis = "positive", adjustment.get("basis_ids")
    else:
        mode = item["application"]["mode"]
        if len(tokens) == 5 and tokens[2:4] == ["occurrence", "schedule"] and tokens[4].isdigit():
            domain = "unit_interval" if mode in {"one_time", "continuous_exposure"} else "nonnegative"
            basis = item["occurrence"].get("basis_ids")
        elif tokens[2:] == ["health_impact", "utility_decrement"]:
            domain, basis = "nonnegative", item["health_impact"].get("basis_ids")
        elif tokens[2:] == ["health_impact", "duration_days"] and mode != "continuous_exposure":
            domain, basis = "positive", item["health_impact"].get("basis_ids")
    if domain is None:
        raise ModelValidationError("component target is not on the allowlist")
    base = _finite(_resolve(value, target), "component base value")
    _domain(base, domain, "component base value")
    return base, tuple(_text(item, "basis id") for item in _array(basis, "target basis_ids")), domain


def _validate_distribution(value: dict[str, Any], domain: str) -> None:
    kind = value.get("type")
    if kind == "uniform":
        low = _finite(value.get("low"), "uniform.low")
        high = _finite(value.get("high"), "uniform.high")
        if not low < high:
            raise ModelValidationError("uniform bounds must increase")
        _domain(low, domain, "uniform.low")
        _domain(high, domain, "uniform.high")
    elif kind == "lognormal":
        _finite(value.get("mu_log"), "lognormal.mu_log")
        if _positive(value.get("sigma_log"), "lognormal.sigma_log") <= 0:
            raise ModelValidationError("lognormal sigma must be positive")
        if domain not in {"positive", "nonnegative"}:
            raise ModelValidationError("lognormal is incompatible with this component domain")
    elif kind == "gamma":
        _positive(value.get("shape"), "gamma.shape")
        _positive(value.get("scale"), "gamma.scale")
        if domain not in {"positive", "nonnegative"}:
            raise ModelValidationError("gamma is incompatible with this component domain")
    else:
        raise ModelValidationError("component uncertainty supports uniform, lognormal, or gamma")


def _correlation_groups(raw: Any, parameters: tuple[ComponentParameter, ...]) -> tuple[CorrelationGroup, ...]:
    values = _array(raw, "correlation groups")
    if len(values) > MAX_GROUPS:
        raise ModelValidationError("too many correlation groups")
    by_id = {parameter.identifier: parameter for parameter in parameters}
    used: set[str] = set()
    groups = []
    for index, raw_group in enumerate(values):
        group = _object(raw_group, f"correlation group {index}")
        ids = tuple(_text(item, "parameter id") for item in _array(group.get("parameter_ids"), "parameter_ids"))
        if not 2 <= len(ids) <= MAX_GROUP_SIZE or len(set(ids)) != len(ids) or any(item not in by_id or item in used for item in ids):
            raise ModelValidationError("correlation parameter_ids must be 2-32 unique ungrouped ids")
        if any(by_id[item].distribution.get("type") not in {"uniform", "lognormal"} for item in ids):
            raise ModelValidationError("mixed component correlation supports only Uniform and Lognormal marginals")
        if group.get("scale") != "latent_standard_normal" or group.get("method") != "gaussian_copula_cholesky":
            raise ModelValidationError("component correlation requires latent_standard_normal Gaussian-copula Cholesky")
        matrix = _matrix(group.get("correlation_matrix"), len(ids))
        basis = tuple(_text(item, "group basis id") for item in _array(group.get("basis_ids"), "group basis_ids"))
        if not basis or not all(set(basis).issubset(set(by_id[item].basis_ids)) for item in ids):
            raise ModelValidationError("correlation basis_ids must be linked by every member")
        groups.append(CorrelationGroup(_text(group.get("id"), "group id"), ids, matrix, _cholesky(matrix), basis, _text(group.get("rationale"), "group rationale")))
        used.update(ids)
    if len({group.identifier for group in groups}) != len(groups):
        raise ModelValidationError("correlation group ids must be unique")
    return tuple(groups)


def _scenario(raw: Any, index: int, analysis: dict[str, Any]) -> Scenario:
    value = _object(raw, f"scenario {index}")
    replacements = []
    for raw_replacement in _array(value.get("replacements"), "scenario replacements"):
        replacement = _object(raw_replacement, "scenario replacement")
        target = _text(replacement.get("target"), "scenario target")
        if target not in {"/discount_rates/costs", "/discount_rates/outcomes", "/half_cycle_correction"}:
            raise ModelValidationError("component uncertainty scenarios permit only discount rates or half-cycle correction")
        base = _resolve(analysis, target)
        proposed = replacement.get("value")
        if isinstance(base, bool):
            if not isinstance(proposed, bool):
                raise ModelValidationError("half-cycle scenario must be boolean")
        else:
            _nonnegative(proposed, "scenario discount rate")
        replacements.append((target, copy.deepcopy(proposed)))
    if not replacements:
        raise ModelValidationError("scenario replacements must not be empty")
    return Scenario(_text(value.get("id"), "scenario id"), _text(value.get("label"), "scenario label"), _text(value.get("rationale"), "scenario rationale"), tuple(replacements))


def _recompute(analysis: dict[str, Any], cost: dict[str, Any], utility: dict[str, Any], event: dict[str, Any]) -> tuple[dict[str, tuple[tuple[float, ...], ...]], dict[str, tuple[tuple[float, ...], ...]]]:
    states = analysis["states"]
    strategies = analysis["strategy_order"]
    cycles = analysis["cycles"]
    cost_totals = {strategy: [0.0] * len(states) for strategy in strategies}
    for item_id in cost["item_order"]:
        item = cost["items"][item_id]
        amount = _nonnegative(item["unit_price"]["amount"], "unit price")
        factor = 1.0
        for adjustment in item["adjustments"]:
            factor *= _positive(adjustment["factor"], "cost adjustment factor")
        normalized = amount * factor
        annual = _nonnegative(item["annual_quantity"]["value"], "annual quantity") * normalized
        if not isfinite(annual):
            raise ModelValidationError("component cost recomputation is non-finite")
        item["normalized_unit_price"] = normalized
        item["normalized_annual_cost"] = annual
        cost_totals[item["strategy_id"]][states.index(item["state_id"])] += annual
    cost["annual_state_costs"] = cost_totals
    for strategy in strategies:
        analysis["strategies"][strategy]["state_costs"] = cost_totals[strategy]

    utility_rows = {strategy: [[0.0] * len(states) for _ in range(cycles)] for strategy in strategies}
    for item_id in utility["item_order"]:
        item = utility["items"][item_id]
        source = _finite(item["source_utility"]["value"], "source utility")
        _domain(source, "utility", "source utility")
        factors = [1.0] * cycles
        for adjustment in item["adjustments"]:
            for cycle, value in enumerate(adjustment["factors"]):
                factors[cycle] *= _positive(value, "utility adjustment factor")
        values = [source * factor for factor in factors]
        for value in values:
            _domain(value, "utility", "adjusted utility")
        item["cycle_values"] = values
        state_index = states.index(item["state_id"])
        for cycle, value in enumerate(values):
            utility_rows[item["strategy_id"]][cycle][state_index] = value
    utility["cycle_state_utilities"] = utility_rows
    for strategy in strategies:
        analysis["strategies"][strategy]["state_utilities"] = utility_rows[strategy][0]

    losses = {strategy: [[0.0] * len(states) for _ in range(cycles)] for strategy in strategies}
    days_per_year = _positive(event["day_count_convention"]["days_per_year"], "days_per_year")
    cycle_length = _positive(analysis["cycle_length_years"], "cycle_length_years")
    cycle_days = days_per_year * cycle_length
    for item_id in event["item_order"]:
        item = event["items"][item_id]
        mode = item["application"]["mode"]
        decrement = _nonnegative(item["health_impact"]["utility_decrement"], "utility decrement")
        schedule = [_nonnegative(value, "event schedule") for value in item["occurrence"]["schedule"]]
        if len(schedule) != cycles or not any(value > 0 for value in schedule):
            raise ModelValidationError("event schedule must retain one impact per model cycle array")
        if mode == "one_time" and (sum(value > 0 for value in schedule) != 1 or any(value > 1 for value in schedule)):
            raise ModelValidationError("one-time event uncertainty must retain one probability cycle")
        if mode == "continuous_exposure":
            if any(value > 1 for value in schedule):
                raise ModelValidationError("continuous exposure uncertainty exceeds one")
            item_losses = [value * decrement * cycle_length for value in schedule]
        else:
            duration = _positive(item["health_impact"]["duration_days"], "event duration")
            if duration > cycle_days + 1e-9:
                raise ModelValidationError("event duration uncertainty exceeds one model cycle")
            qaly = decrement * duration / days_per_year
            if qaly <= 0 or not isfinite(qaly):
                raise ModelValidationError("event QALY loss is invalid")
            item["health_impact"]["qaly_loss_per_occurrence"] = qaly
            item_losses = [value * qaly for value in schedule]
        item["cycle_qaly_loss_per_eligible_person"] = item_losses
        for state in item["application"]["eligible_states"]:
            state_index = states.index(state)
            for cycle, loss in enumerate(item_losses):
                losses[item["strategy_id"]][cycle][state_index] += loss
    for strategy in strategies:
        for cycle in range(cycles):
            for state_index, loss in enumerate(losses[strategy][cycle]):
                if utility_rows[strategy][cycle][state_index] - loss / cycle_length < -1.0 - 1e-9:
                    raise ModelValidationError("sampled event losses imply utility below -1")
                if states[state_index] == "dead" and loss != 0.0:
                    raise ModelValidationError("dead-state event loss must remain zero")
    event["cycle_state_qaly_losses"] = losses
    return (
        {key: tuple(tuple(row) for row in value) for key, value in utility_rows.items()},
        {key: tuple(tuple(row) for row in value) for key, value in losses.items()},
    )


def _run_psa(
    specification: ComponentSpecification,
    strategy_order: list[str],
    evaluate: Any,
    joint_curve_plans: Any = None,
) -> dict[str, Any]:
    from .uncertainty import Pcg32, _multi_strategy_decision_uncertainty

    rng = Pcg32(specification.seed)
    samples = []
    counts = {strategy: 0 for strategy in strategy_order}
    ties = 0
    nmb = {strategy: [] for strategy in strategy_order}
    checkpoints = []
    for iteration in range(1, specification.iterations + 1):
        curve_plan = next(joint_curve_plans) if joint_curve_plans is not None else None
        result = evaluate(_sample_values(rng, specification), curve_plan=curve_plan)
        costs = [result["strategies"][strategy]["total_cost"] for strategy in strategy_order]
        qalys = [result["strategies"][strategy]["total_qaly"] for strategy in strategy_order]
        values = [specification.primary_threshold * qaly - cost for cost, qaly in zip(costs, qalys)]
        best = max(values)
        tolerance = max(1e-9, max(abs(value) for value in values) * 1e-12)
        optimal = [index for index, value in enumerate(values) if abs(value - best) <= tolerance]
        if len(optimal) == 1:
            counts[strategy_order[optimal[0]]] += 1
        else:
            ties += 1
        for index, strategy in enumerate(strategy_order):
            nmb[strategy].append(values[index])
        samples.append({"iteration": iteration, "strategy_costs": costs, "strategy_qalys": qalys})
        if iteration in specification.checkpoints:
            probabilities = {strategy: counts[strategy] / iteration for strategy in strategy_order}
            tie_probability = ties / iteration
            checkpoints.append({
                "iterations": iteration,
                "strategy_optimal_probabilities": probabilities,
                "tie_probability": tie_probability,
                "max_probability_mcse": max(sqrt(value * (1 - value) / iteration) for value in [*probabilities.values(), tie_probability]),
            })
    final, previous = checkpoints[-1], checkpoints[-2]
    drift = max([abs(final["strategy_optimal_probabilities"][strategy] - previous["strategy_optimal_probabilities"][strategy]) for strategy in strategy_order] + [abs(final["tie_probability"] - previous["tie_probability"])])
    means = {strategy: fsum(values) / len(values) for strategy, values in nmb.items()}
    mean_mcse = {
        strategy: sqrt(fsum((value - means[strategy]) ** 2 for value in values) / (len(values) - 1) / len(values))
        for strategy, values in nmb.items()
    }
    decision = _multi_strategy_decision_uncertainty(samples, tuple(strategy_order), specification)
    return {
        "iterations": specification.iterations,
        "strategy_order": strategy_order,
        "primary_threshold_strategy_optimal_probabilities": final["strategy_optimal_probabilities"],
        "primary_threshold_tie_probability": final["tie_probability"],
        "mean_net_monetary_benefit_by_strategy": means,
        "net_monetary_benefit_mcse_by_strategy": mean_mcse,
        "convergence": {
            "passed": final["max_probability_mcse"] <= specification.max_probability_mcse and drift <= specification.max_probability_drift,
            "probability_drift": drift,
            "max_probability_mcse": specification.max_probability_mcse,
            "max_probability_drift": specification.max_probability_drift,
            "checkpoints": checkpoints,
        },
        "independence_rationale": specification.independence_rationale,
        "correlation_groups": [{
            "id": group.identifier,
            "parameter_ids": list(group.parameter_ids),
            "scale": "latent_standard_normal",
            "method": "gaussian_copula_cholesky",
            "correlation_matrix": [list(row) for row in group.matrix],
            "basis_ids": list(group.basis_ids),
            "rationale": group.rationale,
        } for group in specification.correlation_groups],
        "omitted_parameters": list(specification.omitted_parameters),
        "decision_uncertainty": decision,
        "sample_encoding": {"strategy_order": strategy_order, "cost_field": "strategy_costs", "qaly_field": "strategy_qalys"},
        "samples": samples,
    }


def _sample_values(rng: Any, specification: ComponentSpecification) -> tuple[tuple[ComponentParameter, float], ...]:
    by_id = {parameter.identifier: parameter for parameter in specification.parameters}
    correlated: dict[str, float] = {}
    for group in specification.correlation_groups:
        independent = [rng.normal() for _ in group.parameter_ids]
        latent = [sum(group.cholesky[row][column] * independent[column] for column in range(row + 1)) for row in range(len(group.parameter_ids))]
        for identifier, normal in zip(group.parameter_ids, latent):
            correlated[identifier] = _from_latent(by_id[identifier].distribution, normal)
    values = []
    for parameter in specification.parameters:
        sampled = (
            correlated[parameter.identifier]
            if parameter.identifier in correlated
            else _sample(rng, parameter.distribution)
        )
        sampled = _finite(sampled, f"sampled value for {parameter.identifier}")
        _domain(sampled, parameter.domain, f"sampled value for {parameter.identifier}")
        values.append((parameter, sampled))
    return tuple(values)


def _sample(rng: Any, distribution: dict[str, Any]) -> float:
    kind = distribution["type"]
    if kind == "uniform":
        return distribution["low"] + (distribution["high"] - distribution["low"]) * rng.uniform_open()
    if kind == "lognormal":
        return _safe_exp(distribution["mu_log"] + distribution["sigma_log"] * rng.normal())
    if kind == "gamma":
        return rng.gamma(distribution["shape"], distribution["scale"])
    raise ModelValidationError("unsupported component distribution")


def _from_latent(distribution: dict[str, Any], normal: float) -> float:
    if distribution["type"] == "lognormal":
        return _safe_exp(distribution["mu_log"] + distribution["sigma_log"] * normal)
    probability = 0.5 * (1.0 + erf(normal / sqrt(2.0)))
    return distribution["low"] + (distribution["high"] - distribution["low"]) * probability


def _safe_exp(value: float) -> float:
    try:
        result = exp(value)
    except OverflowError as error:
        raise ModelValidationError("sampled component value is non-finite") from error
    if not isfinite(result):
        raise ModelValidationError("sampled component value is non-finite")
    return result


def _decision_summary(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "strategy_order": result["strategy_order"],
        "baseline_strategy_id": result["baseline_strategy_id"],
        "strategies": {strategy: {key: value[key] for key in ("name", "total_cost", "total_qaly", "net_monetary_benefit")} for strategy, value in result["strategies"].items()},
        "pairwise_vs_baseline": result["pairwise_vs_baseline"],
        "fully_incremental_analysis": result["fully_incremental_analysis"],
        "optimal_at_primary_threshold": result["optimal_at_primary_threshold"],
    }


def _binding(value: Any, path: str, raw: bytes, label: str) -> None:
    binding = _object(value, label)
    if set(binding) != {"path", "content_sha256"} or binding.get("path") != path or binding.get("content_sha256") != hashlib.sha256(raw).hexdigest():
        raise ModelValidationError(f"{label} does not bind the current {path} bytes")


def _matrix(value: Any, size: int) -> tuple[tuple[float, ...], ...]:
    rows = _array(value, "correlation_matrix")
    if len(rows) != size:
        raise ModelValidationError("correlation matrix has the wrong size")
    matrix = tuple(tuple(_finite(item, "correlation") for item in _array(row, "correlation row")) for row in rows)
    if any(len(row) != size for row in matrix):
        raise ModelValidationError("correlation matrix has the wrong size")
    for row in range(size):
        if abs(matrix[row][row] - 1.0) > 1e-12:
            raise ModelValidationError("correlation matrix diagonal must equal one")
        for column in range(row):
            if not -1 < matrix[row][column] < 1 or abs(matrix[row][column] - matrix[column][row]) > 1e-12:
                raise ModelValidationError("correlation matrix must be symmetric with non-perfect correlations")
    return matrix


def _cholesky(matrix: tuple[tuple[float, ...], ...]) -> tuple[tuple[float, ...], ...]:
    size = len(matrix)
    lower = [[0.0] * size for _ in range(size)]
    for row in range(size):
        for column in range(row + 1):
            remainder = matrix[row][column] - sum(lower[row][item] * lower[column][item] for item in range(column))
            if row == column:
                if remainder <= 1e-12:
                    raise ModelValidationError("correlation matrix must be strictly positive definite")
                lower[row][column] = sqrt(remainder)
            else:
                lower[row][column] = remainder / lower[column][column]
    return tuple(tuple(row) for row in lower)


def _domain(value: float, domain: str, label: str) -> None:
    valid = {
        "nonnegative": value >= 0,
        "positive": value > 0,
        "utility": -1 <= value <= 1,
        "unit_interval": 0 <= value <= 1,
    }[domain]
    if not valid:
        raise ModelValidationError(f"{label} is outside the {domain} domain")


def _tokens(pointer: str) -> list[str]:
    if not pointer.startswith("/"):
        raise ModelValidationError("component target must be a JSON Pointer")
    return [token.replace("~1", "/").replace("~0", "~") for token in pointer[1:].split("/")]


def _resolve(value: Any, pointer: str) -> Any:
    current = value
    for token in _tokens(pointer):
        current = current[int(token)] if isinstance(current, list) else current[token]
    return current


def _replace(value: Any, pointer: str, replacement: Any) -> None:
    tokens = _tokens(pointer)
    current = value
    for token in tokens[:-1]:
        current = current[int(token)] if isinstance(current, list) else current[token]
    if isinstance(current, list):
        current[int(tokens[-1])] = copy.deepcopy(replacement)
    else:
        current[tokens[-1]] = copy.deepcopy(replacement)


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


def _integer(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ModelValidationError(f"{label} must be an integer")
    return value


def _finite(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(float(value)):
        raise ModelValidationError(f"{label} must be finite")
    return float(value)


def _nonnegative(value: Any, label: str) -> float:
    number = _finite(value, label)
    if number < 0:
        raise ModelValidationError(f"{label} must be non-negative")
    return number


def _positive(value: Any, label: str) -> float:
    number = _finite(value, label)
    if number <= 0:
        raise ModelValidationError(f"{label} must be positive")
    return number
