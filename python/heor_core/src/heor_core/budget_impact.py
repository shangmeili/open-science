"""Deterministic three-year budget impact calculators.

The first-party engine intentionally implements a narrow, inspectable budget
holder models: the legacy static eligible-population calculator and a bounded
dynamic annual-cohort calculator. Both retain one comparator, one new
intervention, itemized per-patient costs, and optional scenario-level costs.
They have no network, model-provider, or third-party runtime dependency.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
from math import isfinite
from typing import Any

from .model import MarkovSpecification, ModelValidationError


STATIC_SCHEMA_VERSION = "0.1.0"
DYNAMIC_SCHEMA_VERSION = "0.2.0"
SCHEMA_VERSIONS = {STATIC_SCHEMA_VERSION, DYNAMIC_SCHEMA_VERSION}
ENGINE_VERSION = "0.3.0"
HORIZON_YEARS = 3
MAX_COST_CATEGORIES = 64
MAX_NON_PATIENT_COSTS = 32
MAX_SENSITIVITY_PARAMETERS = 128
MAX_ALTERNATIVE_SCENARIOS = 32
TOLERANCE = 1e-9


@dataclass(frozen=True)
class BudgetImpactSpecification:
    value: dict[str, Any]

    @classmethod
    def from_dict(
        cls,
        value: dict[str, Any],
        analysis_plan: dict[str, Any],
        analysis_raw: bytes,
    ) -> "BudgetImpactSpecification":
        value = _mapping(value, "budget impact plan")
        _validate(value, analysis_plan, analysis_raw)
        return cls(value=value)


def run_budget_impact(
    analysis_plan: dict[str, Any],
    analysis_raw: bytes,
    budget_plan: dict[str, Any],
    budget_raw: bytes,
) -> dict[str, Any]:
    """Validate and execute a hash-bound budget impact plan."""

    specification = BudgetImpactSpecification.from_dict(
        budget_plan, analysis_plan, analysis_raw
    )
    value = specification.value
    base_case = _calculate(value)

    sensitivity_results: list[dict[str, Any]] = []
    for parameter in value["sensitivity_parameters"]:
        low_plan = deepcopy(value)
        high_plan = deepcopy(value)
        _set_target(low_plan, parameter["target"], parameter["low"])
        _set_target(high_plan, parameter["target"], parameter["high"])
        low = _calculate(low_plan)
        high = _calculate(high_plan)
        sensitivity_results.append(
            {
                "parameter_id": parameter["id"],
                "label": parameter["label"],
                "target": parameter["target"],
                "low": {
                    "value": parameter["low"],
                    "annual_net_budget_impact": low["annual_net_budget_impact"],
                    "cumulative_net_budget_impact": low[
                        "cumulative_net_budget_impact"
                    ],
                },
                "high": {
                    "value": parameter["high"],
                    "annual_net_budget_impact": high["annual_net_budget_impact"],
                    "cumulative_net_budget_impact": high[
                        "cumulative_net_budget_impact"
                    ],
                },
                "cumulative_span": abs(
                    high["cumulative_net_budget_impact"]
                    - low["cumulative_net_budget_impact"]
                ),
                "basis_ids": list(parameter["basis_ids"]),
            }
        )

    scenario_results: list[dict[str, Any]] = []
    for scenario in value["alternative_scenarios"]:
        scenario_plan = deepcopy(value)
        for override in scenario["overrides"]:
            _set_target(scenario_plan, override["target"], override["value"])
        calculated = _calculate(scenario_plan)
        scenario_results.append(
            {
                "scenario_id": scenario["scenario_id"],
                "label": scenario["label"],
                "rationale": scenario["rationale"],
                "annual_net_budget_impact": calculated[
                    "annual_net_budget_impact"
                ],
                "cumulative_net_budget_impact": calculated[
                    "cumulative_net_budget_impact"
                ],
                "basis_ids": list(scenario["basis_ids"]),
            }
        )

    return {
        "schema_version": value["schema_version"],
        "engine_version": ENGINE_VERSION,
        "analysis_id": value["analysis_id"],
        "bia_id": value["bia_id"],
        "analysis_plan_sha256": hashlib.sha256(analysis_raw).hexdigest(),
        "budget_impact_plan_sha256": hashlib.sha256(budget_raw).hexdigest(),
        "calculation_classification": "calculation_only",
        "horizon_years": HORIZON_YEARS,
        "discount_rate": 0,
        "currency": value["perspective"]["currency"],
        "price_year": value["perspective"]["price_year"],
        "base_case": base_case,
        "one_way_sensitivity": sensitivity_results,
        "alternative_scenarios": scenario_results,
        "limitations": list(value["limitations"]),
        "warnings": [
            "Budget impact is an accounting calculation, not a cost-effectiveness or reimbursement conclusion.",
            "Workflow authorization and independent validation are app-owned human controls.",
        ],
    }


def _validate(
    value: dict[str, Any], analysis_plan: dict[str, Any], analysis_raw: bytes
) -> None:
    validated_analysis = MarkovSpecification.from_dict(analysis_plan)
    schema_version = value.get("schema_version")
    if schema_version not in SCHEMA_VERSIONS:
        raise ModelValidationError(
            "budget impact schema_version must be 0.1.0 or 0.2.0"
        )
    for field in ("bia_id", "analysis_id"):
        _nonempty(value.get(field), field)
    if value.get("status") != "ready_for_human_review":
        raise ModelValidationError(
            "budget impact status must be ready_for_human_review"
        )
    if value["analysis_id"] != analysis_plan.get("analysis_id"):
        raise ModelValidationError(
            "budget impact analysis_id does not match the analysis plan"
        )
    base = _mapping(value.get("base_analysis"), "base_analysis")
    if base.get("path") != "heor/analysis-plan.json":
        raise ModelValidationError(
            "base_analysis.path must be heor/analysis-plan.json"
        )
    if base.get("content_sha256") != hashlib.sha256(analysis_raw).hexdigest():
        raise ModelValidationError(
            "base_analysis.content_sha256 does not match the analysis plan bytes"
        )
    linked_path = _mapping(
        analysis_plan.get("budget_impact_analysis"), "budget_impact_analysis"
    ).get("path")
    if linked_path != "heor/budget-impact-plan.json":
        raise ModelValidationError(
            "analysis plan must link heor/budget-impact-plan.json"
        )

    perspective = _mapping(value.get("perspective"), "perspective")
    if perspective.get("type") != "budget_holder":
        raise ModelValidationError("perspective.type must be budget_holder")
    for field in ("budget_holder", "jurisdiction", "currency", "alignment_rationale"):
        _nonempty(perspective.get(field), f"perspective.{field}")
    price_year = _strict_int(perspective.get("price_year"), "perspective.price_year")
    if price_year < 1900 or price_year > 2100:
        raise ModelValidationError("perspective.price_year must be from 1900 to 2100")
    plan_jurisdiction = _mapping(
        analysis_plan.get("decision_problem"), "decision_problem"
    ).get("jurisdiction")
    if plan_jurisdiction and perspective["jurisdiction"] != plan_jurisdiction:
        raise ModelValidationError(
            "budget impact jurisdiction does not match the analysis plan"
        )
    if _strict_int(value.get("horizon_years"), "horizon_years") != HORIZON_YEARS:
        raise ModelValidationError("the MVP budget impact horizon must be exactly 3 years")
    discount_rate = _strict_float(value.get("discount_rate"), "discount_rate")
    if discount_rate != 0:
        raise ModelValidationError("budget impact discount_rate must be 0")

    population = _mapping(value.get("population"), "population")
    _nonempty(population.get("label"), "population.label")
    _nonempty(population.get("derivation"), "population.derivation")
    if schema_version == STATIC_SCHEMA_VERSION:
        annual_population = _number_array(
            population.get("annual_eligible"), "population.annual_eligible"
        )
        _horizon_array(annual_population, "population.annual_eligible")
        if any(number < 0 for number in annual_population):
            raise ModelValidationError("annual eligible population must be non-negative")
    else:
        initial_prevalent = _strict_float(
            population.get("initial_prevalent"), "population.initial_prevalent"
        )
        if initial_prevalent < 0:
            raise ModelValidationError("initial prevalent population must be non-negative")
        incident = _number_array(
            population.get("incident_by_year"), "population.incident_by_year"
        )
        _horizon_array(incident, "population.incident_by_year")
        if any(number < 0 for number in incident):
            raise ModelValidationError("incident population must be non-negative")
        mortality = _number_array(
            value.get("annual_mortality_probability"),
            "annual_mortality_probability",
        )
        _horizon_array(mortality, "annual_mortality_probability")
        if any(number < 0 or number > 1 for number in mortality):
            raise ModelValidationError(
                "annual mortality probabilities must be from 0 to 1"
            )

    strategies = _mapping(value.get("strategies"), "strategies")
    plan_strategies = validated_analysis.strategy_map
    multi_strategy_plan = validated_analysis.schema_version in {
        "0.8.0",
        "0.9.0",
        "0.10.0",
        "0.11.0",
        "0.12.0",
        "0.13.0",
        "0.14.0",
        "0.15.0",
    }
    strategy_ids: list[str] = []
    for role in ("comparator", "intervention"):
        strategy = _mapping(strategies.get(role), f"strategies.{role}")
        _nonempty(strategy.get("id"), f"strategies.{role}.id")
        _nonempty(strategy.get("label"), f"strategies.{role}.label")
        if multi_strategy_plan:
            if strategy["id"] not in validated_analysis.strategy_order:
                raise ModelValidationError(
                    f"strategies.{role}.id must identify an analysis plan strategy"
                )
        else:
            plan_name = plan_strategies[role].name
            if strategy["id"] != plan_name:
                raise ModelValidationError(
                    f"strategies.{role}.id must match the analysis plan strategy name"
                )
        strategy_ids.append(strategy["id"])
    if strategy_ids[0] == strategy_ids[1]:
        raise ModelValidationError("budget impact strategy ids must be different")

    market_scenarios = _mapping(value.get("market_scenarios"), "market_scenarios")
    if schema_version == STATIC_SCHEMA_VERSION:
        _validate_static_market_scenarios(market_scenarios)
    else:
        _validate_dynamic_market_scenarios(market_scenarios)
        persistence = _mapping(value.get("persistence"), "persistence")
        if persistence.get("intervention_discontinuation_destination") != "comparator":
            raise ModelValidationError(
                "intervention discontinuation destination must be comparator"
            )
        if persistence.get("comparator_discontinuation_destination") != "exit_treated_market":
            raise ModelValidationError(
                "comparator discontinuation destination must be exit_treated_market"
            )
        for role in ("comparator", "intervention"):
            field = f"{role}_continuation_probability_by_year"
            probabilities = _number_array(persistence.get(field), f"persistence.{field}")
            _horizon_array(probabilities, f"persistence.{field}")
            if any(number < 0 or number > 1 for number in probabilities):
                raise ModelValidationError(
                    f"persistence.{field} must contain probabilities"
                )

    categories = _array(value.get("cost_categories"), "cost_categories")
    if not 2 <= len(categories) <= MAX_COST_CATEGORIES:
        raise ModelValidationError(
            f"cost_categories must contain 2 to {MAX_COST_CATEGORIES} entries"
        )
    _unique_ids(categories, "id", "cost_categories")
    category_types: set[str] = set()
    for index, category_value in enumerate(categories):
        category = _mapping(category_value, f"cost_categories[{index}]")
        for field in ("id", "label", "rationale"):
            _nonempty(category.get(field), f"cost_categories[{index}].{field}")
        category_type = category.get("type")
        if category_type not in {"intervention", "condition_related"}:
            raise ModelValidationError(
                "cost category type must be intervention or condition_related"
            )
        category_types.add(str(category_type))
        if category.get("included") is not True:
            raise ModelValidationError("cost_categories entries must be included")
        annual = _mapping(
            category.get("annual_per_patient"),
            f"cost_categories[{index}].annual_per_patient",
        )
        for role in ("comparator", "intervention"):
            costs = _number_array(
                annual.get(role),
                f"cost_categories[{index}].annual_per_patient.{role}",
            )
            _horizon_array(costs, f"cost_categories[{index}].annual_per_patient.{role}")
            if any(cost < 0 for cost in costs):
                raise ModelValidationError("per-patient costs must be non-negative")
    if category_types != {"intervention", "condition_related"}:
        raise ModelValidationError(
            "cost_categories must include intervention and condition_related costs"
        )

    exclusions = _array(
        value.get("excluded_cost_categories"), "excluded_cost_categories"
    )
    for index, exclusion_value in enumerate(exclusions):
        exclusion = _mapping(exclusion_value, f"excluded_cost_categories[{index}]")
        _nonempty(exclusion.get("category"), f"excluded_cost_categories[{index}].category")
        _nonempty(exclusion.get("rationale"), f"excluded_cost_categories[{index}].rationale")

    non_patient_costs = _array(value.get("non_patient_costs"), "non_patient_costs")
    if len(non_patient_costs) > MAX_NON_PATIENT_COSTS:
        raise ModelValidationError(
            f"non_patient_costs may contain at most {MAX_NON_PATIENT_COSTS} entries"
        )
    _unique_ids(non_patient_costs, "id", "non_patient_costs")
    for index, item_value in enumerate(non_patient_costs):
        item = _mapping(item_value, f"non_patient_costs[{index}]")
        for field in ("id", "label", "rationale"):
            _nonempty(item.get(field), f"non_patient_costs[{index}].{field}")
        if item.get("type") != "implementation":
            raise ModelValidationError("non-patient cost type must be implementation")
        if item.get("included") is not True:
            raise ModelValidationError("non_patient_costs entries must be included")
        annual = _mapping(item.get("annual_total"), f"non_patient_costs[{index}].annual_total")
        for scenario_name in ("without_new_intervention", "with_new_intervention"):
            totals = _number_array(
                annual.get(scenario_name),
                f"non_patient_costs[{index}].annual_total.{scenario_name}",
            )
            _horizon_array(
                totals,
                f"non_patient_costs[{index}].annual_total.{scenario_name}",
            )
            if any(total < 0 for total in totals):
                raise ModelValidationError("non-patient costs must be non-negative")

    source_ids, assumption_status = _validate_evidence_metadata(value)
    required_paths = _required_provenance_paths(value)
    _validate_input_provenance(
        value, required_paths, source_ids, assumption_status, perspective["jurisdiction"]
    )
    _validate_sensitivity(value, source_ids, assumption_status)
    _validate_alternative_scenarios(value, source_ids, assumption_status)

    validation = _mapping(value.get("validation_plan"), "validation_plan")
    for field in ("face", "internal", "external"):
        checks = _string_array(validation.get(field), f"validation_plan.{field}")
        if not checks:
            raise ModelValidationError(f"validation_plan.{field} must not be empty")
    limitations = _string_array(value.get("limitations"), "limitations")
    if not limitations:
        raise ModelValidationError("limitations must not be empty")


def _validate_evidence_metadata(
    value: dict[str, Any],
) -> tuple[set[str], dict[str, str]]:
    sources = _array(value.get("evidence_sources"), "evidence_sources")
    _unique_ids(sources, "id", "evidence_sources")
    source_ids: set[str] = set()
    for index, source_value in enumerate(sources):
        source = _mapping(source_value, f"evidence_sources[{index}]")
        for field in ("id", "title", "source_type", "accessed_on"):
            _nonempty(source.get(field), f"evidence_sources[{index}].{field}")
        if not _is_nonempty(source.get("url")) and not _is_nonempty(source.get("local_path")):
            raise ModelValidationError(
                f"evidence_sources[{index}] requires url or local_path"
            )
        if _is_nonempty(source.get("local_path")) and not _is_sha256(
            source.get("content_sha256")
        ):
            raise ModelValidationError(
                f"evidence_sources[{index}].content_sha256 is required for local files"
            )
        source_ids.add(source["id"])

    assumptions = _array(value.get("assumptions"), "assumptions")
    _unique_ids(assumptions, "id", "assumptions")
    assumption_status: dict[str, str] = {}
    for index, item_value in enumerate(assumptions):
        item = _mapping(item_value, f"assumptions[{index}]")
        for field in ("id", "statement", "reason"):
            _nonempty(item.get(field), f"assumptions[{index}].{field}")
        status = item.get("status")
        if status not in {"unresolved", "proposed", "rejected"}:
            raise ModelValidationError(f"assumptions[{index}].status is invalid")
        if status == "unresolved":
            raise ModelValidationError(
                f"unresolved budget impact assumption: {item['id']}"
            )
        assumption_status[item["id"]] = status
    return source_ids, assumption_status


def _validate_static_market_scenarios(
    market_scenarios: dict[str, Any],
) -> None:
    for name in ("without_new_intervention", "with_new_intervention"):
        scenario = _mapping(market_scenarios.get(name), f"market_scenarios.{name}")
        _nonempty(scenario.get("label"), f"market_scenarios.{name}.label")
        shares = _number_array(
            scenario.get("intervention_share_by_year"),
            f"market_scenarios.{name}.intervention_share_by_year",
        )
        _horizon_array(shares, f"market_scenarios.{name}.intervention_share_by_year")
        if any(share < 0 or share > 1 for share in shares):
            raise ModelValidationError("market shares must be from 0 to 1")
    without_shares = market_scenarios["without_new_intervention"][
        "intervention_share_by_year"
    ]
    if any(abs(float(share)) > TOLERANCE for share in without_shares):
        raise ModelValidationError(
            "without_new_intervention shares must be zero in the two-strategy MVP"
        )


def _validate_dynamic_market_scenarios(
    market_scenarios: dict[str, Any],
) -> None:
    for name in ("without_new_intervention", "with_new_intervention"):
        scenario = _mapping(market_scenarios.get(name), f"market_scenarios.{name}")
        _nonempty(scenario.get("label"), f"market_scenarios.{name}.label")
        initial_share = _strict_float(
            scenario.get("initial_intervention_share"),
            f"market_scenarios.{name}.initial_intervention_share",
        )
        if initial_share < 0 or initial_share > 1:
            raise ModelValidationError("initial intervention shares must be from 0 to 1")
        for field in (
            "incident_intervention_share_by_year",
            "comparator_displacement_share_by_year",
        ):
            probabilities = _number_array(
                scenario.get(field), f"market_scenarios.{name}.{field}"
            )
            _horizon_array(probabilities, f"market_scenarios.{name}.{field}")
            if any(number < 0 or number > 1 for number in probabilities):
                raise ModelValidationError(
                    f"market_scenarios.{name}.{field} must contain probabilities"
                )
        capacity = _number_array(
            scenario.get("intervention_start_capacity_by_year"),
            f"market_scenarios.{name}.intervention_start_capacity_by_year",
        )
        _horizon_array(
            capacity,
            f"market_scenarios.{name}.intervention_start_capacity_by_year",
        )
        if any(number < 0 for number in capacity):
            raise ModelValidationError("intervention start capacity must be non-negative")

    without = market_scenarios["without_new_intervention"]
    if abs(float(without["initial_intervention_share"])) > TOLERANCE:
        raise ModelValidationError(
            "without-new-intervention initial intervention share must be zero"
        )
    for field in (
        "incident_intervention_share_by_year",
        "comparator_displacement_share_by_year",
        "intervention_start_capacity_by_year",
    ):
        if any(abs(float(number)) > TOLERANCE for number in without[field]):
            raise ModelValidationError(
                f"without-new-intervention {field} must contain only zeroes"
            )


def _required_provenance_paths(value: dict[str, Any]) -> set[str]:
    if value["schema_version"] == STATIC_SCHEMA_VERSION:
        paths = {
            f"/population/annual_eligible/{year}" for year in range(HORIZON_YEARS)
        }
        paths.update(
            f"/market_scenarios/with_new_intervention/intervention_share_by_year/{year}"
            for year in range(HORIZON_YEARS)
        )
    else:
        paths = {"/population/initial_prevalent"}
        paths.update(
            f"/population/incident_by_year/{year}" for year in range(HORIZON_YEARS)
        )
        paths.update(
            f"/annual_mortality_probability/{year}" for year in range(HORIZON_YEARS)
        )
        for scenario in ("without_new_intervention", "with_new_intervention"):
            paths.add(
                f"/market_scenarios/{scenario}/initial_intervention_share"
            )
            for field in (
                "incident_intervention_share_by_year",
                "comparator_displacement_share_by_year",
                "intervention_start_capacity_by_year",
            ):
                paths.update(
                    f"/market_scenarios/{scenario}/{field}/{year}"
                    for year in range(HORIZON_YEARS)
                )
        for role in ("comparator", "intervention"):
            paths.update(
                f"/persistence/{role}_continuation_probability_by_year/{year}"
                for year in range(HORIZON_YEARS)
            )
    for category_index, _ in enumerate(value["cost_categories"]):
        for role in ("comparator", "intervention"):
            paths.update(
                f"/cost_categories/{category_index}/annual_per_patient/{role}/{year}"
                for year in range(HORIZON_YEARS)
            )
    for item_index, _ in enumerate(value["non_patient_costs"]):
        for scenario in ("without_new_intervention", "with_new_intervention"):
            paths.update(
                f"/non_patient_costs/{item_index}/annual_total/{scenario}/{year}"
                for year in range(HORIZON_YEARS)
            )
    return paths


def _validate_input_provenance(
    value: dict[str, Any],
    required_paths: set[str],
    source_ids: set[str],
    assumption_status: dict[str, str],
    jurisdiction: str,
) -> None:
    mappings = _array(value.get("input_provenance"), "input_provenance")
    seen: set[str] = set()
    for index, mapping_value in enumerate(mappings):
        mapping = _mapping(mapping_value, f"input_provenance[{index}]")
        path = mapping.get("path")
        if path not in required_paths:
            raise ModelValidationError(
                f"input_provenance[{index}].path is not a required budget input"
            )
        if path in seen:
            raise ModelValidationError(f"duplicate input provenance path: {path}")
        seen.add(path)
        for field in ("unit", "jurisdiction", "selection_rationale"):
            _nonempty(mapping.get(field), f"input_provenance[{index}].{field}")
        if mapping["jurisdiction"] != jurisdiction:
            raise ModelValidationError(
                f"input_provenance[{index}].jurisdiction does not match the BIA"
            )
        if mapping.get("uncertainty_status") not in {
            "fixed",
            "range_available",
            "distribution_available",
        }:
            raise ModelValidationError(
                f"input_provenance[{index}].uncertainty_status is invalid"
            )
        if path.startswith("/cost_categories/") or path.startswith(
            "/non_patient_costs/"
        ):
            price_year = _strict_int(
                mapping.get("price_year"), f"input_provenance[{index}].price_year"
            )
            if price_year < 1900 or price_year > 2100:
                raise ModelValidationError("input provenance price_year is invalid")
        linked_sources = _string_array(
            mapping.get("source_ids", []), f"input_provenance[{index}].source_ids"
        )
        linked_assumptions = _string_array(
            mapping.get("assumption_ids", []),
            f"input_provenance[{index}].assumption_ids",
        )
        if not linked_sources and not linked_assumptions:
            raise ModelValidationError(
                f"input_provenance[{index}] requires evidence or an assumption"
            )
        if any(source not in source_ids for source in linked_sources):
            raise ModelValidationError(
                f"input_provenance[{index}] references an unknown source"
            )
        if any(assumption_status.get(item) != "proposed" for item in linked_assumptions):
            raise ModelValidationError(
                f"input_provenance[{index}] references a non-proposed assumption"
            )
    missing = sorted(required_paths - seen)
    if missing:
        raise ModelValidationError(
            f"budget impact inputs lack provenance: {', '.join(missing[:5])}"
        )


def _validate_sensitivity(
    value: dict[str, Any], source_ids: set[str], assumption_status: dict[str, str]
) -> None:
    parameters = _array(value.get("sensitivity_parameters"), "sensitivity_parameters")
    if not 1 <= len(parameters) <= MAX_SENSITIVITY_PARAMETERS:
        raise ModelValidationError(
            f"sensitivity_parameters must contain 1 to {MAX_SENSITIVITY_PARAMETERS} entries"
        )
    _unique_ids(parameters, "id", "sensitivity_parameters")
    seen_targets: set[str] = set()
    for index, parameter_value in enumerate(parameters):
        parameter = _mapping(parameter_value, f"sensitivity_parameters[{index}]")
        for field in ("id", "label", "target"):
            _nonempty(parameter.get(field), f"sensitivity_parameters[{index}].{field}")
        target = parameter["target"]
        if target in seen_targets:
            raise ModelValidationError(f"duplicate sensitivity target: {target}")
        seen_targets.add(target)
        base_value = _target_value(value, target)
        low = _strict_float(parameter.get("low"), f"sensitivity_parameters[{index}].low")
        high = _strict_float(parameter.get("high"), f"sensitivity_parameters[{index}].high")
        if low > base_value or high < base_value or low == high:
            raise ModelValidationError(
                f"sensitivity_parameters[{index}] must bracket the base value"
            )
        _validate_target_number(target, low)
        _validate_target_number(target, high)
        _validate_basis_ids(parameter, source_ids, assumption_status, f"sensitivity_parameters[{index}]")


def _validate_alternative_scenarios(
    value: dict[str, Any], source_ids: set[str], assumption_status: dict[str, str]
) -> None:
    scenarios = _array(value.get("alternative_scenarios"), "alternative_scenarios")
    if not 1 <= len(scenarios) <= MAX_ALTERNATIVE_SCENARIOS:
        raise ModelValidationError(
            f"alternative_scenarios must contain 1 to {MAX_ALTERNATIVE_SCENARIOS} entries"
        )
    _unique_ids(scenarios, "scenario_id", "alternative_scenarios")
    for index, scenario_value in enumerate(scenarios):
        scenario = _mapping(scenario_value, f"alternative_scenarios[{index}]")
        for field in ("scenario_id", "label", "rationale"):
            _nonempty(scenario.get(field), f"alternative_scenarios[{index}].{field}")
        overrides = _array(
            scenario.get("overrides"), f"alternative_scenarios[{index}].overrides"
        )
        if not overrides:
            raise ModelValidationError("alternative scenario overrides must not be empty")
        seen: set[str] = set()
        for override_index, override_value in enumerate(overrides):
            override = _mapping(
                override_value,
                f"alternative_scenarios[{index}].overrides[{override_index}]",
            )
            _nonempty(override.get("target"), "scenario override target")
            target = override["target"]
            if target in seen:
                raise ModelValidationError("scenario override targets must be unique")
            seen.add(target)
            _target_value(value, target)
            number = _strict_float(override.get("value"), "scenario override value")
            _validate_target_number(target, number)
        _validate_basis_ids(
            scenario, source_ids, assumption_status, f"alternative_scenarios[{index}]"
        )


def _validate_basis_ids(
    value: dict[str, Any],
    source_ids: set[str],
    assumption_status: dict[str, str],
    name: str,
) -> None:
    basis_ids = _string_array(value.get("basis_ids"), f"{name}.basis_ids")
    if not basis_ids:
        raise ModelValidationError(f"{name}.basis_ids must not be empty")
    for basis_id in basis_ids:
        if basis_id not in source_ids and assumption_status.get(basis_id) != "proposed":
            raise ModelValidationError(f"{name} references an unknown basis id")


def _calculate(value: dict[str, Any]) -> dict[str, Any]:
    if value["schema_version"] == DYNAMIC_SCHEMA_VERSION:
        return _calculate_dynamic(value)

    populations = value["population"]["annual_eligible"]
    market = value["market_scenarios"]
    annual_results: list[dict[str, Any]] = []
    cumulative = 0.0
    for year_index in range(HORIZON_YEARS):
        population = float(populations[year_index])
        without_share = float(
            market["without_new_intervention"]["intervention_share_by_year"][year_index]
        )
        with_share = float(
            market["with_new_intervention"]["intervention_share_by_year"][year_index]
        )
        category_breakdown: list[dict[str, Any]] = []
        without_total = 0.0
        with_total = 0.0
        for category in value["cost_categories"]:
            comparator_cost = float(category["annual_per_patient"]["comparator"][year_index])
            intervention_cost = float(category["annual_per_patient"]["intervention"][year_index])
            without_cost = population * (
                (1.0 - without_share) * comparator_cost
                + without_share * intervention_cost
            )
            with_cost = population * (
                (1.0 - with_share) * comparator_cost
                + with_share * intervention_cost
            )
            _finite_result(without_cost, "without-access category cost")
            _finite_result(with_cost, "with-access category cost")
            without_total += without_cost
            with_total += with_cost
            category_breakdown.append(
                {
                    "category_id": category["id"],
                    "type": category["type"],
                    "without_new_intervention": without_cost,
                    "with_new_intervention": with_cost,
                    "net_budget_impact": with_cost - without_cost,
                }
            )
        for item in value["non_patient_costs"]:
            without_cost = float(
                item["annual_total"]["without_new_intervention"][year_index]
            )
            with_cost = float(item["annual_total"]["with_new_intervention"][year_index])
            without_total += without_cost
            with_total += with_cost
            category_breakdown.append(
                {
                    "category_id": item["id"],
                    "type": item["type"],
                    "without_new_intervention": without_cost,
                    "with_new_intervention": with_cost,
                    "net_budget_impact": with_cost - without_cost,
                }
            )
        _finite_result(without_total, "without-access total")
        _finite_result(with_total, "with-access total")
        net = with_total - without_total
        cumulative += net
        _finite_result(cumulative, "cumulative net budget impact")
        annual_results.append(
            {
                "year": year_index + 1,
                "eligible_population": population,
                "without_new_intervention_share": without_share,
                "with_new_intervention_share": with_share,
                "without_new_intervention_cost": without_total,
                "with_new_intervention_cost": with_total,
                "net_budget_impact": net,
                "category_breakdown": category_breakdown,
            }
        )
    return {
        "annual_results": annual_results,
        "annual_net_budget_impact": [row["net_budget_impact"] for row in annual_results],
        "cumulative_net_budget_impact": cumulative,
    }


def _calculate_dynamic(value: dict[str, Any]) -> dict[str, Any]:
    scenario_results = {
        name: _calculate_dynamic_scenario(value, name)
        for name in ("without_new_intervention", "with_new_intervention")
    }
    annual_results: list[dict[str, Any]] = []
    cumulative = 0.0
    for year_index in range(HORIZON_YEARS):
        without = scenario_results["without_new_intervention"][year_index]
        with_access = scenario_results["with_new_intervention"][year_index]
        net = with_access["total_cost"] - without["total_cost"]
        cumulative += net
        _finite_result(cumulative, "dynamic cumulative net budget impact")
        annual_results.append(
            {
                "year": year_index + 1,
                "eligible_population": with_access["treated_population"],
                "without_new_intervention_share": without["intervention_share"],
                "with_new_intervention_share": with_access["intervention_share"],
                "without_new_intervention_cost": without["total_cost"],
                "with_new_intervention_cost": with_access["total_cost"],
                "net_budget_impact": net,
                "without_new_intervention_flow": without,
                "with_new_intervention_flow": with_access,
                "category_breakdown": _dynamic_category_breakdown(
                    without, with_access
                ),
            }
        )
    return {
        "model_type": "dynamic_annual_cohort",
        "event_order": [
            "open_stock",
            "add_incident_cohort",
            "allocate_incident_intervention_starts_before_displacement_within_capacity",
            "apply_full_year_costs",
            "apply_mortality",
            "apply_persistence_and_boundary_discontinuation",
        ],
        "annual_results": annual_results,
        "annual_net_budget_impact": [row["net_budget_impact"] for row in annual_results],
        "cumulative_net_budget_impact": cumulative,
    }


def _calculate_dynamic_scenario(
    value: dict[str, Any], scenario_name: str
) -> list[dict[str, Any]]:
    scenario = value["market_scenarios"][scenario_name]
    population = value["population"]
    persistence = value["persistence"]
    initial = float(population["initial_prevalent"])
    intervention_open = initial * float(scenario["initial_intervention_share"])
    comparator_open = initial - intervention_open
    rows: list[dict[str, Any]] = []

    for year_index in range(HORIZON_YEARS):
        incident = float(population["incident_by_year"][year_index])
        requested_incident_starts = incident * float(
            scenario["incident_intervention_share_by_year"][year_index]
        )
        capacity = float(
            scenario["intervention_start_capacity_by_year"][year_index]
        )
        incident_starts = min(requested_incident_starts, capacity)
        incident_to_comparator = incident - incident_starts
        comparator_before_displacement = comparator_open + incident_to_comparator
        requested_displacement = comparator_before_displacement * float(
            scenario["comparator_displacement_share_by_year"][year_index]
        )
        displacement_starts = min(
            requested_displacement, max(0.0, capacity - incident_starts)
        )
        intervention_treated = intervention_open + incident_starts + displacement_starts
        comparator_treated = comparator_before_displacement - displacement_starts
        treated_population = intervention_treated + comparator_treated
        total_cost, category_costs = _dynamic_scenario_costs(
            value,
            scenario_name,
            year_index,
            comparator_treated,
            intervention_treated,
        )

        mortality = float(value["annual_mortality_probability"][year_index])
        comparator_alive = comparator_treated * (1.0 - mortality)
        intervention_alive = intervention_treated * (1.0 - mortality)
        comparator_continuers = comparator_alive * float(
            persistence["comparator_continuation_probability_by_year"][year_index]
        )
        intervention_continuers = intervention_alive * float(
            persistence["intervention_continuation_probability_by_year"][year_index]
        )
        intervention_discontinuers = intervention_alive - intervention_continuers
        comparator_discontinuers = comparator_alive - comparator_continuers
        comparator_close = comparator_continuers + intervention_discontinuers
        intervention_close = intervention_continuers
        deaths = treated_population * mortality

        row = {
            "opening_comparator": comparator_open,
            "opening_intervention": intervention_open,
            "incident_population": incident,
            "requested_incident_intervention_starts": requested_incident_starts,
            "incident_intervention_starts": incident_starts,
            "requested_comparator_displacement_starts": requested_displacement,
            "comparator_displacement_starts": displacement_starts,
            "capacity": capacity,
            "capacity_unmet_starts": (
                requested_incident_starts + requested_displacement
                - incident_starts
                - displacement_starts
            ),
            "comparator_treated": comparator_treated,
            "intervention_treated": intervention_treated,
            "treated_population": treated_population,
            "intervention_share": (
                intervention_treated / treated_population
                if treated_population > 0
                else 0.0
            ),
            "deaths": deaths,
            "intervention_discontinuers_to_comparator": intervention_discontinuers,
            "comparator_discontinuers_exiting": comparator_discontinuers,
            "closing_comparator": comparator_close,
            "closing_intervention": intervention_close,
            "total_cost": total_cost,
            "category_costs": category_costs,
        }
        for key, number in row.items():
            if isinstance(number, float):
                _finite_result(number, f"dynamic flow {key}")
                if number < -TOLERANCE:
                    raise ModelValidationError(f"dynamic flow {key} became negative")
        rows.append(row)
        comparator_open = comparator_close
        intervention_open = intervention_close
    return rows


def _dynamic_scenario_costs(
    value: dict[str, Any],
    scenario_name: str,
    year_index: int,
    comparator_treated: float,
    intervention_treated: float,
) -> tuple[float, dict[str, float]]:
    category_costs: dict[str, float] = {}
    total = 0.0
    for category in value["cost_categories"]:
        cost = (
            comparator_treated
            * float(category["annual_per_patient"]["comparator"][year_index])
            + intervention_treated
            * float(category["annual_per_patient"]["intervention"][year_index])
        )
        _finite_result(cost, "dynamic category cost")
        category_costs[category["id"]] = cost
        total += cost
    for item in value["non_patient_costs"]:
        cost = float(item["annual_total"][scenario_name][year_index])
        category_costs[item["id"]] = cost
        total += cost
    _finite_result(total, "dynamic scenario total")
    return total, category_costs


def _dynamic_category_breakdown(
    without: dict[str, Any], with_access: dict[str, Any]
) -> list[dict[str, Any]]:
    return [
        {
            "category_id": category_id,
            "without_new_intervention": without["category_costs"][category_id],
            "with_new_intervention": with_access["category_costs"][category_id],
            "net_budget_impact": (
                with_access["category_costs"][category_id]
                - without["category_costs"][category_id]
            ),
        }
        for category_id in without["category_costs"]
    ]


def _target_value(value: dict[str, Any], target: str) -> float:
    if not _target_allowed(target):
        raise ModelValidationError(f"unsupported budget impact target: {target}")
    current: Any = value
    for token in target.lstrip("/").split("/"):
        if isinstance(current, list):
            try:
                index = int(token)
            except ValueError as error:
                raise ModelValidationError(f"invalid array index in target: {target}") from error
            if index < 0 or index >= len(current):
                raise ModelValidationError(f"target index is out of range: {target}")
            current = current[index]
        elif isinstance(current, dict) and token in current:
            current = current[token]
        else:
            raise ModelValidationError(f"target does not exist: {target}")
    return _strict_float(current, f"target {target}")


def _set_target(value: dict[str, Any], target: str, replacement: Any) -> None:
    number = _strict_float(replacement, f"replacement for {target}")
    _validate_target_number(target, number)
    tokens = target.lstrip("/").split("/")
    current: Any = value
    for token in tokens[:-1]:
        current = current[int(token)] if isinstance(current, list) else current[token]
    final = tokens[-1]
    if isinstance(current, list):
        current[int(final)] = number
    else:
        current[final] = number


def _target_allowed(target: str) -> bool:
    tokens = target.lstrip("/").split("/")
    if tokens == ["population", "initial_prevalent"]:
        return True
    if (
        len(tokens) == 3
        and tokens[:2] in (
            ["population", "incident_by_year"],
            ["persistence", "comparator_continuation_probability_by_year"],
            ["persistence", "intervention_continuation_probability_by_year"],
        )
    ):
        return tokens[2].isdigit() and int(tokens[2]) < HORIZON_YEARS
    if len(tokens) == 2 and tokens[0] == "annual_mortality_probability":
        return tokens[1].isdigit() and int(tokens[1]) < HORIZON_YEARS
    if (
        len(tokens) == 4
        and tokens[0] == "market_scenarios"
        and tokens[1] == "with_new_intervention"
        and tokens[2]
        in {
            "incident_intervention_share_by_year",
            "comparator_displacement_share_by_year",
            "intervention_start_capacity_by_year",
        }
    ):
        return tokens[3].isdigit() and int(tokens[3]) < HORIZON_YEARS
    if (
        len(tokens) == 3
        and tokens[0] == "market_scenarios"
        and tokens[1] == "with_new_intervention"
        and tokens[2] == "initial_intervention_share"
    ):
        return True
    if len(tokens) == 3 and tokens[:2] == ["population", "annual_eligible"]:
        return tokens[2].isdigit() and int(tokens[2]) < HORIZON_YEARS
    if (
        len(tokens) == 4
        and tokens[:3]
        == [
            "market_scenarios",
            "with_new_intervention",
            "intervention_share_by_year",
        ]
    ):
        return tokens[3].isdigit() and int(tokens[3]) < HORIZON_YEARS
    if (
        len(tokens) == 5
        and tokens[0] == "cost_categories"
        and tokens[2] == "annual_per_patient"
        and tokens[3] in {"comparator", "intervention"}
    ):
        return tokens[1].isdigit() and tokens[4].isdigit() and int(tokens[4]) < HORIZON_YEARS
    if (
        len(tokens) == 5
        and tokens[0] == "non_patient_costs"
        and tokens[2] == "annual_total"
        and tokens[3] in {"without_new_intervention", "with_new_intervention"}
    ):
        return tokens[1].isdigit() and tokens[4].isdigit() and int(tokens[4]) < HORIZON_YEARS
    return False


def _validate_target_number(target: str, number: float) -> None:
    probability_target = (
        target.startswith("/annual_mortality_probability/")
        or target.startswith("/persistence/")
        or (
            target.startswith("/market_scenarios/")
            and "intervention_start_capacity_by_year" not in target
        )
    )
    if probability_target:
        if number < 0 or number > 1:
            raise ModelValidationError("probability target values must be from 0 to 1")
    elif number < 0:
        raise ModelValidationError("budget impact target values must be non-negative")


def _finite_result(value: float, name: str) -> None:
    if not isfinite(value):
        raise ModelValidationError(f"{name} is not finite")


def _horizon_array(values: list[float], name: str) -> None:
    if len(values) != HORIZON_YEARS:
        raise ModelValidationError(f"{name} must contain exactly {HORIZON_YEARS} values")


def _unique_ids(values: list[Any], field: str, name: str) -> None:
    ids: list[str] = []
    for index, value in enumerate(values):
        item = _mapping(value, f"{name}[{index}]")
        _nonempty(item.get(field), f"{name}[{index}].{field}")
        ids.append(item[field])
    if len(ids) != len(set(ids)):
        raise ModelValidationError(f"{name}.{field} values must be unique")


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _is_nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _nonempty(value: Any, name: str) -> str:
    if not _is_nonempty(value):
        raise ModelValidationError(f"{name} must not be empty")
    return value


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ModelValidationError(f"{name} must be an object")
    return value


def _array(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ModelValidationError(f"{name} must be an array")
    return value


def _number_array(value: Any, name: str) -> list[float]:
    return [_strict_float(item, f"{name} item") for item in _array(value, name)]


def _string_array(value: Any, name: str) -> list[str]:
    result = _array(value, name)
    for item in result:
        _nonempty(item, f"{name} item")
    return result


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
