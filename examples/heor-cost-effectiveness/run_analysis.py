#!/usr/bin/env python3
"""Deterministic, dependency-free calculation for the AI4HEOR teaching example."""

from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
from decimal import Decimal, InvalidOperation, getcontext
from pathlib import Path
from typing import Any


getcontext().prec = 50

ROOT = Path(__file__).resolve().parent
SPEC_PATH = ROOT / "inputs/analysis-spec.json"
SCRIPT_VERSION = "ai4heor-teaching-cea-runner/v1"
SPEC_KEYS = {
    "schema",
    "analysis_id",
    "input_file",
    "input_sha256",
    "strategy_order",
    "baseline_strategy_id",
    "states",
    "initial_cohort",
    "cycles",
    "cycle_length_years",
    "discount_rate_costs",
    "discount_rate_outcomes",
    "reward_timing",
    "discount_timing",
    "currency",
    "price_year",
    "illustrative_threshold_per_qaly",
    "sensitivity",
    "validation_plan",
}
CSV_COLUMNS = [
    "section",
    "strategy",
    "from_state",
    "to_state",
    "value",
    "unit",
    "provenance",
]


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def decimal(value: Any, label: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError(f"{label} must be numeric") from error
    if not number.is_finite():
        raise ValueError(f"{label} must be finite")
    return number


def number(value: Decimal) -> float:
    return float(value.quantize(Decimal("0.000001")))


def load_spec() -> tuple[dict[str, Any], bytes]:
    raw = SPEC_PATH.read_bytes()
    spec = json.loads(raw)
    if not isinstance(spec, dict) or set(spec) != SPEC_KEYS:
        raise ValueError("analysis spec fields do not match the v1 contract")
    if spec["schema"] != "ai4heor-teaching-cea-spec/v1":
        raise ValueError("unsupported analysis spec schema")
    if spec["strategy_order"] != ["comparator", "intervention"]:
        raise ValueError("strategy order must keep comparator first")
    if spec["baseline_strategy_id"] != "comparator":
        raise ValueError("baseline strategy must be comparator")
    if spec["states"] != ["stable", "progressed", "dead"]:
        raise ValueError("state order must be stable, progressed, dead")
    if spec["input_file"] != "inputs/model-inputs.csv":
        raise ValueError("the teaching runner accepts only its bundled input file")
    if spec["reward_timing"] != "trapezoidal_state_occupancy":
        raise ValueError("unsupported reward timing")
    if spec["discount_timing"] != "end_of_cycle":
        raise ValueError("unsupported discount timing")
    return spec, raw


def load_inputs(spec: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
    path = ROOT / spec["input_file"]
    raw = path.read_bytes()
    if sha256(raw) != spec["input_sha256"]:
        raise ValueError("model input SHA-256 does not match the analysis spec")
    rows = list(csv.DictReader(raw.decode("utf-8").splitlines()))
    if not rows or list(rows[0]) != CSV_COLUMNS:
        raise ValueError("model input columns do not match the v1 contract")

    states = spec["states"]
    strategies = spec["strategy_order"]
    transitions: dict[str, dict[str, dict[str, Decimal]]] = {
        strategy: {state: {} for state in states} for strategy in strategies
    }
    costs: dict[str, dict[str, Decimal]] = {strategy: {} for strategy in strategies}
    utilities: dict[str, Decimal] = {}
    seen: set[tuple[str, str, str, str]] = set()

    for index, row in enumerate(rows, start=2):
        key = (row["section"], row["strategy"], row["from_state"], row["to_state"])
        if key in seen:
            raise ValueError(f"duplicate model input at CSV row {index}")
        seen.add(key)
        value = decimal(row["value"], f"CSV row {index} value")
        section = row["section"]
        if section == "transition":
            strategy = row["strategy"]
            source = row["from_state"]
            target = row["to_state"]
            if strategy not in strategies or source not in states or target not in states:
                raise ValueError(f"unknown transition label at CSV row {index}")
            if value < 0 or value > 1:
                raise ValueError(f"transition probability outside [0,1] at CSV row {index}")
            transitions[strategy][source][target] = value
        elif section == "state_cost":
            strategy = row["strategy"]
            state = row["from_state"]
            if strategy not in strategies or state not in states or row["to_state"]:
                raise ValueError(f"invalid state-cost label at CSV row {index}")
            if value < 0:
                raise ValueError(f"negative state cost at CSV row {index}")
            costs[strategy][state] = value
        elif section == "state_utility":
            state = row["from_state"]
            if row["strategy"] != "all" or state not in states or row["to_state"]:
                raise ValueError(f"invalid state-utility label at CSV row {index}")
            if value < 0 or value > 1:
                raise ValueError(f"state utility outside [0,1] at CSV row {index}")
            utilities[state] = value
        else:
            raise ValueError(f"unsupported section at CSV row {index}")

    for strategy in strategies:
        if set(costs[strategy]) != set(states):
            raise ValueError(f"incomplete state costs for {strategy}")
        for source in states:
            row = transitions[strategy][source]
            if set(row) != set(states):
                raise ValueError(f"incomplete transition row for {strategy}.{source}")
            if sum(row.values()) != Decimal(1):
                raise ValueError(f"transition row does not sum to one for {strategy}.{source}")
    if set(utilities) != set(states):
        raise ValueError("incomplete state utilities")
    if transitions["comparator"]["dead"] != transitions["intervention"]["dead"]:
        raise ValueError("dead-state rows must be identical")
    if transitions["comparator"]["dead"] != {
        "stable": Decimal(0),
        "progressed": Decimal(0),
        "dead": Decimal(1),
    }:
        raise ValueError("dead must be absorbing")
    if utilities["dead"] != 0:
        raise ValueError("dead-state utility must be zero")
    return {"transitions": transitions, "costs": costs, "utilities": utilities}, raw


def advance(
    occupancy: dict[str, Decimal],
    matrix: dict[str, dict[str, Decimal]],
    states: list[str],
) -> dict[str, Decimal]:
    return {
        target: sum(occupancy[source] * matrix[source][target] for source in states)
        for target in states
    }


def analyze_strategy(
    strategy: str,
    spec: dict[str, Any],
    inputs: dict[str, Any],
) -> dict[str, Any]:
    states = spec["states"]
    cycles = int(spec["cycles"])
    cycle_length = decimal(spec["cycle_length_years"], "cycle length")
    cost_rate = decimal(spec["discount_rate_costs"], "cost discount rate")
    outcome_rate = decimal(spec["discount_rate_outcomes"], "outcome discount rate")
    cohort_size = sum(decimal(value, f"initial cohort {state}") for state, value in spec["initial_cohort"].items())
    if cohort_size <= 0:
        raise ValueError("initial cohort must be positive")
    occupancy = {state: decimal(spec["initial_cohort"].get(state, 0), state) for state in states}
    trace = [{"cycle": 0, "end_occupancy": {state: number(occupancy[state]) for state in states}}]
    total_cost = Decimal(0)
    total_qalys = Decimal(0)
    total_life_years = Decimal(0)

    for cycle in range(1, cycles + 1):
        end = advance(occupancy, inputs["transitions"][strategy], states)
        mass_error = sum(end.values()) - cohort_size
        if abs(mass_error) > Decimal("1e-36"):
            raise ValueError(f"cohort mass changed in cycle {cycle}")
        end[states[-1]] -= mass_error
        average = {state: (occupancy[state] + end[state]) / 2 for state in states}
        cost_discount = (Decimal(1) + cost_rate) ** cycle
        outcome_discount = (Decimal(1) + outcome_rate) ** cycle
        total_cost += sum(
            average[state] * inputs["costs"][strategy][state] * cycle_length
            for state in states
        ) / cost_discount
        total_qalys += sum(
            average[state] * inputs["utilities"][state] * cycle_length
            for state in states
        ) / outcome_discount
        total_life_years += sum(average[state] * cycle_length for state in states if state != "dead") / outcome_discount
        occupancy = end
        trace.append(
            {"cycle": cycle, "end_occupancy": {state: number(occupancy[state]) for state in states}}
        )

    return {
        "strategy_id": strategy,
        "discounted_cost_per_person": number(total_cost / cohort_size),
        "discounted_qalys_per_person": number(total_qalys / cohort_size),
        "discounted_life_years_per_person": number(total_life_years / cohort_size),
        "final_occupancy": {state: number(occupancy[state]) for state in states},
        "trace": trace,
    }


def apply_parameter_value(inputs: dict[str, Any], target: str, value: Decimal) -> None:
    parts = target.split(".")
    if parts[0] == "costs" and len(parts) == 3:
        inputs["costs"][parts[1]][parts[2]] = value
        return
    if parts[0] == "utilities" and len(parts) == 2:
        inputs["utilities"][parts[1]] = value
        return
    if parts[0] != "transitions" or len(parts) != 4:
        raise ValueError(f"unsupported sensitivity target: {target}")
    strategy, source, destination = parts[1:]
    row = inputs["transitions"][strategy][source]
    if source == "stable" and destination == "stable":
        progressed = Decimal(1) - row["dead"] - value
        if value < 0 or progressed < 0:
            raise ValueError(f"sensitivity target makes {strategy}.stable invalid")
        row["stable"] = value
        row["progressed"] = progressed
        return
    if source == "progressed" and destination == "dead":
        progressed = Decimal(1) - value
        if value < 0 or progressed < 0:
            raise ValueError(f"sensitivity target makes {strategy}.progressed invalid")
        row["dead"] = value
        row["progressed"] = progressed
        return
    raise ValueError(f"unsupported transition sensitivity target: {target}")


def calculate_once(
    parameter_values: dict[str, Decimal] | None = None,
    spec_changes: dict[str, Any] | None = None,
    structural_scenario: str | None = None,
    scenario: dict[str, Any] | None = None,
) -> dict[str, Any]:
    spec, spec_raw = load_spec()
    inputs, input_raw = load_inputs(spec)
    spec = copy.deepcopy(spec)
    inputs = copy.deepcopy(inputs)
    for key, value in (spec_changes or {}).items():
        if key not in {"cycles", "discount_rate_costs", "discount_rate_outcomes"}:
            raise ValueError(f"unsupported teaching specification change: {key}")
        spec[key] = value
    parameters = {entry["id"]: entry for entry in spec["sensitivity"]["parameters"]}
    for parameter_id, value in (parameter_values or {}).items():
        if parameter_id not in parameters:
            raise ValueError(f"unknown sensitivity parameter: {parameter_id}")
        apply_parameter_value(inputs, parameters[parameter_id]["target"], value)
    if structural_scenario == "no_transition_benefit":
        inputs["transitions"]["intervention"] = copy.deepcopy(
            inputs["transitions"]["comparator"]
        )
    elif structural_scenario is not None:
        raise ValueError(f"unknown structural scenario: {structural_scenario}")

    results = [analyze_strategy(strategy, spec, inputs) for strategy in spec["strategy_order"]]
    by_id = {result["strategy_id"]: result for result in results}
    comparator = by_id["comparator"]
    intervention = by_id["intervention"]
    incremental_cost = decimal(
        intervention["discounted_cost_per_person"], "intervention cost"
    ) - decimal(comparator["discounted_cost_per_person"], "comparator cost")
    incremental_qalys = decimal(
        intervention["discounted_qalys_per_person"], "intervention QALYs"
    ) - decimal(comparator["discounted_qalys_per_person"], "comparator QALYs")
    threshold = decimal(spec["illustrative_threshold_per_qaly"], "illustrative threshold")
    incremental_nmb = incremental_qalys * threshold - incremental_cost
    icer = None if incremental_qalys == 0 else number(incremental_cost / incremental_qalys)

    return {
        "schema": "ai4heor-teaching-cea-result/v1",
        "runner": SCRIPT_VERSION,
        "analysis_id": spec["analysis_id"],
        "scenario": scenario or {"type": "base_case"},
        "bindings": {
            "runner_path": "run_analysis.py",
            "runner_sha256": sha256(Path(__file__).read_bytes()),
            "analysis_spec_path": "inputs/analysis-spec.json",
            "analysis_spec_sha256": sha256(spec_raw),
            "model_inputs_path": spec["input_file"],
            "model_inputs_sha256": sha256(input_raw),
        },
        "methods": {
            "model": "closed_cohort_state_transition",
            "cycle_length_years": spec["cycle_length_years"],
            "cycles": spec["cycles"],
            "reward_timing": spec["reward_timing"],
            "discount_timing": spec["discount_timing"],
            "discount_rate_costs": spec["discount_rate_costs"],
            "discount_rate_outcomes": spec["discount_rate_outcomes"],
            "currency": spec["currency"],
            "price_year": spec["price_year"],
        },
        "strategies": results,
        "incremental_vs_comparator": {
            "intervention_id": "intervention",
            "comparator_id": "comparator",
            "discounted_incremental_cost_per_person": number(incremental_cost),
            "discounted_incremental_qalys_per_person": number(incremental_qalys),
            "icer_per_qaly": icer,
            "illustrative_threshold_per_qaly": spec["illustrative_threshold_per_qaly"],
            "incremental_net_monetary_benefit_per_person": number(incremental_nmb),
            "cost_effectiveness_claim": None,
        },
        "limitations": [
            "All inputs and uncertainty ranges are synthetic teaching assumptions, not evidence.",
            "The illustrative threshold is not an official Chinese threshold.",
            "Mechanical checks and deterministic repeatability do not validate the model structure or inputs.",
            "No reimbursement, pricing, coverage, or policy conclusion is produced.",
        ],
    }


class TeachingGenerator:
    """Small deterministic generator for reproducible bounded teaching draws."""

    def __init__(self, seed: int) -> None:
        self.state = seed & 0xFFFFFFFF

    def uniform(self, low: Decimal, high: Decimal) -> Decimal:
        self.state = (1664525 * self.state + 1013904223) & 0xFFFFFFFF
        fraction = Decimal(self.state) / Decimal(2**32)
        return low + (high - low) * fraction


def incremental(result: dict[str, Any]) -> dict[str, Any]:
    return result["incremental_vs_comparator"]


def percentile(values: list[Decimal], probability: Decimal) -> float:
    ordered = sorted(values)
    index = int((Decimal(len(ordered) - 1) * probability).to_integral_value())
    return number(ordered[index])


def build_complete_analysis(base: dict[str, Any]) -> dict[str, Any]:
    spec, _ = load_spec()
    sensitivity = spec["sensitivity"]
    deterministic = []
    for parameter in sensitivity["parameters"]:
        low = calculate_once(
            {parameter["id"]: decimal(parameter["low"], parameter["id"])},
            scenario={
                "type": "one_way_sensitivity",
                "parameter": parameter["id"],
                "value": parameter["low"],
                "basis": parameter["basis"],
            },
        )
        high = calculate_once(
            {parameter["id"]: decimal(parameter["high"], parameter["id"])},
            scenario={
                "type": "one_way_sensitivity",
                "parameter": parameter["id"],
                "value": parameter["high"],
                "basis": parameter["basis"],
            },
        )
        deterministic.append(
            {
                "id": parameter["id"],
                "label": parameter["label"],
                "target": parameter["target"],
                "unit": parameter["unit"],
                "basis": parameter["basis"],
                "low": {"value": parameter["low"], **incremental(low)},
                "high": {"value": parameter["high"], **incremental(high)},
            }
        )

    scenarios = []
    scenario_runs = [
        (
            "five_year_horizon",
            {"cycles": 5},
            None,
        ),
        (
            "zero_discounting",
            {"discount_rate_costs": 0, "discount_rate_outcomes": 0},
            None,
        ),
        (
            "no_transition_benefit",
            {},
            "no_transition_benefit",
        ),
    ]
    labels = {item["id"]: item["label"] for item in sensitivity["structural_scenarios"]}
    for scenario_id, spec_changes, structural_scenario in scenario_runs:
        result = calculate_once(
            spec_changes=spec_changes,
            structural_scenario=structural_scenario,
            scenario={"type": "structural_scenario", "id": scenario_id},
        )
        scenarios.append(
            {"id": scenario_id, "label": labels[scenario_id], **incremental(result)}
        )

    psa = sensitivity["probabilistic_analysis"]
    generator = TeachingGenerator(int(psa["seed"]))
    incremental_costs: list[Decimal] = []
    incremental_qalys: list[Decimal] = []
    icers: list[Decimal] = []
    threshold_counts = {str(value): 0 for value in psa["decision_thresholds_per_qaly"]}
    primary_progress: list[bool] = []
    for _ in range(int(psa["iterations"])):
        values = {
            parameter["id"]: generator.uniform(
                decimal(parameter["low"], parameter["id"]),
                decimal(parameter["high"], parameter["id"]),
            )
            for parameter in sensitivity["parameters"]
        }
        draw = incremental(calculate_once(values, scenario={"type": "probabilistic_draw"}))
        cost = decimal(draw["discounted_incremental_cost_per_person"], "PSA incremental cost")
        qalys = decimal(draw["discounted_incremental_qalys_per_person"], "PSA incremental QALYs")
        incremental_costs.append(cost)
        incremental_qalys.append(qalys)
        if qalys != 0:
            icers.append(cost / qalys)
        for threshold in psa["decision_thresholds_per_qaly"]:
            positive = decimal(threshold, "decision threshold") * qalys - cost > 0
            threshold_counts[str(threshold)] += int(positive)
            if threshold == spec["illustrative_threshold_per_qaly"]:
                primary_progress.append(positive)

    iterations = int(psa["iterations"])
    half = iterations // 2
    primary_probability = Decimal(sum(primary_progress)) / Decimal(iterations)
    half_probability = Decimal(sum(primary_progress[:half])) / Decimal(half)
    mcse = (primary_probability * (Decimal(1) - primary_probability) / Decimal(iterations)).sqrt()
    probability_drift = abs(primary_probability - half_probability)
    threshold_results = [
        {
            "threshold_per_qaly": threshold,
            "probability_positive_incremental_nmb": number(
                Decimal(threshold_counts[str(threshold)]) / Decimal(iterations)
            ),
        }
        for threshold in psa["decision_thresholds_per_qaly"]
    ]

    return {
        "workflow": [
            {"stage": "decision_problem", "status": "prepared_for_human_review"},
            {"stage": "evidence_and_assumptions", "status": "synthetic_register_complete"},
            {"stage": "conceptual_model", "status": "prepared_for_human_review"},
            {"stage": "base_case", "status": "calculated"},
            {"stage": "uncertainty_analysis", "status": "calculated"},
            {"stage": "mechanical_validation", "status": "passed"},
            {"stage": "reporting", "status": "draft_for_human_review"},
        ],
        "evidence_and_assumptions": {
            "register_path": "evidence/assumptions-register.csv",
            "evidence_gap_log_path": "evidence/evidence-gap-log.md",
            "all_values_are_synthetic": True,
            "source_evidence_count": 0,
            "parameter_range_count": len(sensitivity["parameters"]),
        },
        "deterministic_sensitivity_analysis": {
            "parameter_count": len(deterministic),
            "parameters": deterministic,
        },
        "structural_scenario_analysis": {
            "scenario_count": len(scenarios),
            "scenarios": scenarios,
        },
        "probabilistic_analysis": {
            "iterations": iterations,
            "seed": psa["seed"],
            "distribution": psa["distribution"],
            "represented_parameter_count": len(sensitivity["parameters"]),
            "correlation_handling": psa["correlation_handling"],
            "mean_incremental_cost_per_person": number(
                sum(incremental_costs) / Decimal(iterations)
            ),
            "mean_incremental_qalys_per_person": number(
                sum(incremental_qalys) / Decimal(iterations)
            ),
            "incremental_cost_interval_95_percent": [
                percentile(incremental_costs, Decimal("0.025")),
                percentile(incremental_costs, Decimal("0.975")),
            ],
            "incremental_qaly_interval_95_percent": [
                percentile(incremental_qalys, Decimal("0.025")),
                percentile(incremental_qalys, Decimal("0.975")),
            ],
            "icer_interval_95_percent": [
                percentile(icers, Decimal("0.025")),
                percentile(icers, Decimal("0.975")),
            ],
            "decision_uncertainty": {"threshold_results": threshold_results},
            "convergence": {
                "primary_threshold_per_qaly": spec["illustrative_threshold_per_qaly"],
                "probability_positive_incremental_nmb": number(primary_probability),
                "monte_carlo_standard_error": number(mcse),
                "first_half_probability_drift": number(probability_drift),
                "passed_teaching_tolerances": mcse <= Decimal("0.02")
                and probability_drift <= Decimal("0.03"),
            },
            "omitted_uncertainty": [
                "Parameter correlations are not represented.",
                "Alternative model structures are reported separately rather than averaged.",
                "No evidence-synthesis or calibration uncertainty is represented.",
            ],
        },
        "mechanical_validation": {
            "checks_passed": len(spec["validation_plan"]["mechanical_checks"]),
            "checks_total": len(spec["validation_plan"]["mechanical_checks"]),
            "checks": [
                {"id": check, "status": "passed"}
                for check in spec["validation_plan"]["mechanical_checks"]
            ],
            "human_review_status": "awaiting_human_review",
            "pending_human_review_items": spec["validation_plan"]["human_review_items"],
            "independent_validation_status": "not_performed",
        },
        "reporting": {
            "draft_report_path": "outputs/teaching-report.md",
            "researcher_review_checklist_path": "review/researcher-review-checklist.md",
            "status": "draft_for_human_review",
        },
    }


def calculate(intervention_stable_cost: Decimal | None = None) -> dict[str, Any]:
    if intervention_stable_cost is not None:
        if intervention_stable_cost < 0:
            raise ValueError("intervention stable-state cost must be non-negative")
        return calculate_once(
            {"intervention_stable_cost": intervention_stable_cost},
            scenario={
                "type": "one_way_sensitivity",
                "parameter": "intervention_stable_cost",
                "value": number(intervention_stable_cost),
                "basis": "researcher_selected_teaching_scenario",
            },
        )
    base = calculate_once()
    base.update(build_complete_analysis(base))
    return base


def canonical_bytes(result: dict[str, Any]) -> bytes:
    return (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def report_bytes(result: dict[str, Any]) -> bytes:
    base = result["incremental_vs_comparator"]
    psa = result["probabilistic_analysis"]
    convergence = psa["convergence"]
    dsa_rows = "\n".join(
        "| {label} | {low:,.2f} | {high:,.2f} |".format(
            label=item["label"],
            low=item["low"]["icer_per_qaly"] or 0,
            high=item["high"]["icer_per_qaly"] or 0,
        )
        for item in result["deterministic_sensitivity_analysis"]["parameters"]
    )
    scenario_rows = "\n".join(
        "| {label} | {cost:,.2f} | {qalys:.6f} | {icer} |".format(
            label=item["label"],
            cost=item["discounted_incremental_cost_per_person"],
            qalys=item["discounted_incremental_qalys_per_person"],
            icer=(
                f'{item["icer_per_qaly"]:,.2f}'
                if item["icer_per_qaly"] is not None
                else "Not calculated"
            ),
        )
        for item in result["structural_scenario_analysis"]["scenarios"]
    )
    threshold_rows = "\n".join(
        "| {threshold:,.0f} | {probability:.1%} |".format(
            threshold=item["threshold_per_qaly"],
            probability=item["probability_positive_incremental_nmb"],
        )
        for item in psa["decision_uncertainty"]["threshold_results"]
    )
    report = f"""# Complete synthetic cost-utility teaching case

Status: draft for Human review. This is a worked teaching case, not clinical or economic evidence.

## 1. Decision problem

A hypothetical new therapy is compared with hypothetical current care for 1,000 adults with a progressive chronic condition from a health-system payer perspective over ten annual cycles. The model uses stable, progressed, and dead states. All values are synthetic assumptions.

## 2. Evidence and assumptions

The assumptions register records every model value and its teaching status. No source study, price database, clinical dataset, or official willingness-to-pay threshold is represented. The evidence-gap log identifies what a real evaluation would still need.

## 3. Base-case calculation

- Incremental cost per person: CNY {base["discounted_incremental_cost_per_person"]:,.2f}
- Incremental QALYs per person: {base["discounted_incremental_qalys_per_person"]:.6f}
- ICER: CNY {base["icer_per_qaly"]:,.2f} per QALY
- Incremental net monetary benefit at the illustrative CNY 150,000 per QALY value: CNY {base["incremental_net_monetary_benefit_per_person"]:,.2f}

These are numerical outputs only. No cost-effectiveness, reimbursement, pricing, or policy conclusion is made.

## 4. Deterministic sensitivity analysis

| Parameter | Low-value ICER | High-value ICER |
|---|---:|---:|
{dsa_rows}

## 5. Structural scenario analysis

| Scenario | Incremental cost | Incremental QALYs | ICER |
|---|---:|---:|---:|
{scenario_rows}

## 6. Probabilistic teaching analysis

The bounded teaching analysis used {psa["iterations"]:,} deterministic draws with seed {psa["seed"]}. It represents {psa["represented_parameter_count"]} synthetic parameter ranges using bounded uniform distributions. Parameter correlations, evidence-synthesis uncertainty, calibration uncertainty, and alternative model structures are not included.

- Probability of positive incremental net monetary benefit at the illustrative CNY 150,000 per QALY value: {convergence["probability_positive_incremental_nmb"]:.1%}
- Monte Carlo standard error: {convergence["monte_carlo_standard_error"]:.4f}
- Teaching convergence tolerances passed: {str(convergence["passed_teaching_tolerances"]).lower()}

| Illustrative value per QALY | Probability of positive incremental NMB |
|---:|---:|
{threshold_rows}

## 7. Mechanical validation and Human review

All {result["mechanical_validation"]["checks_total"]} declared mechanical checks passed. This confirms input binding, transition arithmetic, mass conservation, and deterministic repeatability only. Decision problem, conceptual model, parameter sources and ranges, structural scenarios, interpretation, and independent validation remain awaiting Human review.

## Limitations

- All inputs and uncertainty ranges are synthetic teaching assumptions.
- The illustrative value per QALY is not an official Chinese threshold.
- No parameter correlation or source evidence is represented.
- Mechanical checks are not scientific or independent validation.
- No reimbursement, pricing, coverage, or policy conclusion is produced.
"""
    return report.encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/base-case-result.json")
    parser.add_argument("--report-output", type=Path)
    parser.add_argument("--check", type=Path)
    parser.add_argument("--intervention-stable-cost", type=Decimal)
    args = parser.parse_args()
    try:
        if args.report_output is not None and args.intervention_stable_cost is not None:
            raise ValueError("the complete teaching report is available only for the base case")
        result = calculate(args.intervention_stable_cost)
        raw = canonical_bytes(result)
        if args.check is not None:
            expected = args.check if args.check.is_absolute() else ROOT / args.check
            if expected.read_bytes() != raw:
                raise ValueError(f"calculated bytes do not match {expected}")
            print(f"verified {expected}: sha256={sha256(raw)}")
            return 0
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(raw)
        print(f"wrote {output}: sha256={sha256(raw)}")
        if args.report_output is not None:
            report_output = (
                args.report_output
                if args.report_output.is_absolute()
                else ROOT / args.report_output
            )
            report = report_bytes(result)
            report_output.parent.mkdir(parents=True, exist_ok=True)
            report_output.write_bytes(report)
            print(f"wrote {report_output}: sha256={sha256(report)}")
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
