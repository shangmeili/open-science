#!/usr/bin/env python3
"""Deterministic, dependency-free calculation for the AI4HEOR teaching example."""

from __future__ import annotations

import argparse
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
        if sum(end.values()) != cohort_size:
            raise ValueError(f"cohort mass changed in cycle {cycle}")
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


def calculate(intervention_stable_cost: Decimal | None = None) -> dict[str, Any]:
    spec, spec_raw = load_spec()
    inputs, input_raw = load_inputs(spec)
    runner_raw = Path(__file__).read_bytes()
    scenario: dict[str, Any] = {"type": "base_case"}
    if intervention_stable_cost is not None:
        if intervention_stable_cost < 0:
            raise ValueError("intervention stable-state cost must be non-negative")
        inputs["costs"]["intervention"]["stable"] = intervention_stable_cost
        scenario = {
            "type": "one_way_sensitivity",
            "parameter": "intervention.stable.state_cost",
            "value": number(intervention_stable_cost),
            "basis": "researcher_selected_teaching_scenario",
        }

    results = [analyze_strategy(strategy, spec, inputs) for strategy in spec["strategy_order"]]
    by_id = {result["strategy_id"]: result for result in results}
    comparator = by_id["comparator"]
    intervention = by_id["intervention"]
    incremental_cost = decimal(
        intervention["discounted_cost_per_person"], "intervention cost"
    ) - decimal(
        comparator["discounted_cost_per_person"], "comparator cost"
    )
    incremental_qalys = decimal(
        intervention["discounted_qalys_per_person"], "intervention QALYs"
    ) - decimal(
        comparator["discounted_qalys_per_person"], "comparator QALYs"
    )
    threshold = decimal(spec["illustrative_threshold_per_qaly"], "illustrative threshold")
    incremental_nmb = incremental_qalys * threshold - incremental_cost
    icer = None if incremental_qalys == 0 else number(incremental_cost / incremental_qalys)

    return {
        "schema": "ai4heor-teaching-cea-result/v1",
        "runner": SCRIPT_VERSION,
        "analysis_id": spec["analysis_id"],
        "scenario": scenario,
        "bindings": {
            "runner_path": "run_analysis.py",
            "runner_sha256": sha256(runner_raw),
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
            "All inputs are synthetic teaching assumptions, not evidence.",
            "The illustrative threshold is not an official Chinese threshold.",
            "This deterministic calculation does not validate the model structure or inputs.",
            "No reimbursement, pricing, coverage, or policy conclusion is produced.",
        ],
    }


def canonical_bytes(result: dict[str, Any]) -> bytes:
    return (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "outputs/base-case-result.json")
    parser.add_argument("--check", type=Path)
    parser.add_argument("--intervention-stable-cost", type=Decimal)
    args = parser.parse_args()
    try:
        raw = canonical_bytes(calculate(args.intervention_stable_cost))
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
        return 0
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(1, f"error: {error}\n")


if __name__ == "__main__":
    raise SystemExit(main())
