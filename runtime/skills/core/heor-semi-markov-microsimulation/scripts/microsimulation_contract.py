#!/usr/bin/env python3
"""Bounded deterministic individual-level state-transition microsimulation."""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


REQUEST_SCHEMA_VERSION = "0.1.0"
RESULT_SCHEMA_VERSION = "0.1.0"
EVALUATOR = "ai4heor-semi-markov-microsimulation@0.1.0"
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_STATES = 8
MAX_STRATEGIES = 4
MAX_TRACKERS = 3
MAX_CYCLES = 600
MAX_PATIENTS = 50_000
MAX_REPLICATES = 20
MAX_TRACE_PATIENTS = 20
MAX_SIMULATION_STEPS = 5_000_000
MAX_SEED = (1 << 53) - 1
FLOAT_TOLERANCE = 1e-10
MASK64 = (1 << 64) - 1
SAFE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
ISO_CURRENCY = re.compile(r"^[A-Z]{3}$")

REQUIRED_REVIEW_CHECKS = [
    "decision_problem_and_individual_model_justification",
    "states_horizon_timing_and_absorbing_death",
    "input_provenance_and_population_alignment",
    "time_in_state_rules_and_state_rewards",
    "history_trackers_and_transition_event_costs",
    "prng_seeds_common_random_numbers_and_traces",
    "monte_carlo_error_replicates_and_performance",
    "structural_parameter_uncertainty_and_downstream_limits",
]

REQUEST_FIELDS = {
    "schema_version", "simulation_id", "status", "question", "evidence_synthesis",
    "model", "strategies", "economics", "simulation", "output",
    "human_authorization", "limitations", "human_gate",
}
RESULT_FIELDS = {
    "schema_version", "simulation_id", "status", "request", "evidence_synthesis",
    "runtime", "method", "performance", "strategies", "comparisons",
    "monte_carlo_error", "trace", "warnings", "limitations", "human_gate",
}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def exact(value: Any, fields: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == fields


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value == value.strip()


def finite(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))


def safe_id(value: Any) -> bool:
    return isinstance(value, str) and SAFE_ID.fullmatch(value) is not None


def safe_relative(value: Any) -> bool:
    if not text(value):
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


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def canonical_trace_bytes(rows: list[dict[str, Any]]) -> bytes:
    return b"".join(canonical_json_bytes(row) for row in rows)


def _unique_text(values: Any, *, identifiers: bool = False, allow_empty: bool = False) -> bool:
    validator = safe_id if identifiers else text
    return (
        isinstance(values, list)
        and (allow_empty or bool(values))
        and all(validator(value) for value in values)
        and len(values) == len(set(values))
    )


def _validate_evidence(request: dict[str, Any], workspace: Path, errors: list[str], facts: dict[str, Any]) -> None:
    binding = request.get("evidence_synthesis")
    if not exact(binding, {"path", "sha256", "included_record_ids"}):
        errors.append("evidence_synthesis fields are invalid")
        return
    path = resolve_file(workspace, binding.get("path"))
    if path is None or SHA256.fullmatch(str(binding.get("sha256", ""))) is None:
        errors.append("evidence_synthesis path or sha256 is invalid")
        return
    try:
        evidence, raw = load_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        errors.append(f"evidence_synthesis cannot be read: {error}")
        return
    if digest(raw) != binding["sha256"]:
        errors.append("evidence_synthesis sha256 does not match current bytes")
    included = binding.get("included_record_ids")
    if not _unique_text(included, identifiers=True):
        errors.append("evidence_synthesis included_record_ids are invalid")
        included = []
    records = evidence.get("records")
    if not isinstance(records, list):
        errors.append("evidence_synthesis records must be a list")
    else:
        available = {
            record if isinstance(record, str) else record.get("id")
            for record in records if isinstance(record, (str, dict))
        }
        if not set(included).issubset(available):
            errors.append("evidence_synthesis does not contain every included record")
    facts["evidence_path"] = path
    facts["evidence_record_ids"] = set(included)


def _validate_evidence_ids(value: Any, prefix: str, available: set[str], errors: list[str]) -> None:
    if not _unique_text(value, identifiers=True):
        errors.append(f"{prefix} evidence_record_ids are invalid")
    elif not set(value).issubset(available):
        errors.append(f"{prefix} evidence_record_ids are not all present in the bound evidence set")


def _interval(value: Any, upper_bound: int, prefix: str, errors: list[str]) -> tuple[int, int] | None:
    if not exact(value, {"minimum", "maximum"}):
        errors.append(f"{prefix} interval fields are invalid")
        return None
    minimum, maximum = value.get("minimum"), value.get("maximum")
    if isinstance(minimum, bool) or not isinstance(minimum, int) or not 0 <= minimum <= upper_bound:
        errors.append(f"{prefix}.minimum is invalid")
        return None
    if maximum is None:
        maximum = upper_bound
    if isinstance(maximum, bool) or not isinstance(maximum, int) or not minimum <= maximum <= upper_bound:
        errors.append(f"{prefix}.maximum is invalid")
        return None
    return minimum, maximum


def _validate_condition(
    condition: Any,
    prefix: str,
    cycles: int,
    tracker_caps: dict[str, int],
    errors: list[str],
) -> dict[str, tuple[int, int]] | None:
    if exact(condition, {"kind"}) and condition.get("kind") == "otherwise":
        return None
    if not exact(condition, {"kind", "time_in_state_cycles", "tracker_counts"}) or condition.get("kind") != "when":
        errors.append(f"{prefix} condition fields are invalid")
        return {}
    compiled: dict[str, tuple[int, int]] = {}
    time_interval = _interval(condition.get("time_in_state_cycles"), cycles, f"{prefix}.time_in_state_cycles", errors)
    if time_interval is not None:
        compiled["__time__"] = time_interval
    tracker_counts = condition.get("tracker_counts")
    if not isinstance(tracker_counts, list):
        errors.append(f"{prefix}.tracker_counts must be a list")
        tracker_counts = []
    seen: set[str] = set()
    for index, entry in enumerate(tracker_counts):
        item_prefix = f"{prefix}.tracker_counts[{index}]"
        if not exact(entry, {"tracker_id", "minimum", "maximum"}):
            errors.append(f"{item_prefix} fields are invalid")
            continue
        tracker_id = entry.get("tracker_id")
        if tracker_id not in tracker_caps or tracker_id in seen:
            errors.append(f"{item_prefix}.tracker_id is unknown or duplicated")
            continue
        seen.add(tracker_id)
        interval = _interval(
            {"minimum": entry.get("minimum"), "maximum": entry.get("maximum")},
            tracker_caps[tracker_id], item_prefix, errors,
        )
        if interval is not None:
            compiled[tracker_id] = interval
    if compiled.get("__time__") == (0, cycles) and not tracker_counts:
        errors.append(f"{prefix} when condition is unconstrained; use otherwise")
    return compiled


def _conditions_overlap(
    left: dict[str, tuple[int, int]],
    right: dict[str, tuple[int, int]],
    cycles: int,
    tracker_caps: dict[str, int],
) -> bool:
    dimensions = {"__time__": cycles, **tracker_caps}
    for dimension, cap in dimensions.items():
        left_interval = left.get(dimension, (0, cap))
        right_interval = right.get(dimension, (0, cap))
        if max(left_interval[0], right_interval[0]) > min(left_interval[1], right_interval[1]):
            return False
    return True


def validate_request(request: Any, workspace: Path) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    facts: dict[str, Any] = {}
    if not isinstance(request, dict):
        return ["request must be a JSON object"], facts
    missing = REQUEST_FIELDS - set(request)
    unknown = set(request) - REQUEST_FIELDS
    if missing or unknown:
        errors.append("request fields do not match schema 0.1.0 or contain unknown authority fields")
    if missing:
        return errors, facts
    if request.get("schema_version") != REQUEST_SCHEMA_VERSION:
        errors.append("schema_version must be 0.1.0")
    simulation_id = request.get("simulation_id")
    if not safe_id(simulation_id):
        errors.append("simulation_id is invalid")
    if request.get("status") != "ready_for_execution":
        errors.append("status must be ready_for_execution")

    question_fields = {"population", "purpose", "time_origin", "perspective", "intended_use", "individual_model_justification"}
    question = request.get("question")
    if not exact(question, question_fields) or any(not text(question.get(key)) for key in question_fields):
        errors.append("question fields must be complete text")
    _validate_evidence(request, workspace, errors, facts)
    available_evidence = facts.get("evidence_record_ids", set())

    model_fields = {
        "type", "states", "initial_distribution", "cycle_length_years", "cycles",
        "transition_timing", "reward_timing", "interactions", "event_trackers",
    }
    model = request.get("model")
    if not exact(model, model_fields):
        errors.append("model fields are invalid")
        model = {}
    if model.get("type") != "discrete_time_individual_state_transition":
        errors.append("model type must be discrete_time_individual_state_transition")
    if model.get("transition_timing") != "one_transition_at_cycle_end":
        errors.append("transition_timing must be one_transition_at_cycle_end")
    if model.get("reward_timing") != "trapezoidal_state_rewards_transition_costs_at_cycle_end":
        errors.append("reward_timing must use the fixed trapezoidal contract")
    if model.get("interactions") != "none_closed_independent_cohort":
        errors.append("interactions must be none_closed_independent_cohort")

    states_raw = model.get("states")
    states: list[dict[str, Any]] = states_raw if isinstance(states_raw, list) else []
    if not 2 <= len(states) <= MAX_STATES:
        errors.append(f"model states must contain {2}-{MAX_STATES} entries")
    state_ids: list[str] = []
    death_ids: list[str] = []
    state_absorbing: dict[str, bool] = {}
    for index, state in enumerate(states):
        prefix = f"model.states[{index}]"
        if not exact(state, {"id", "label", "absorbing", "death"}):
            errors.append(f"{prefix} fields are invalid")
            continue
        state_id = state.get("id")
        if not safe_id(state_id) or not text(state.get("label")) or not isinstance(state.get("absorbing"), bool) or not isinstance(state.get("death"), bool):
            errors.append(f"{prefix} values are invalid")
            continue
        state_ids.append(state_id)
        state_absorbing[state_id] = state["absorbing"]
        if state["death"]:
            death_ids.append(state_id)
            if not state["absorbing"]:
                errors.append(f"{prefix} death state must be absorbing")
    if len(state_ids) != len(set(state_ids)):
        errors.append("state ids must be unique")
    if len(death_ids) != 1:
        errors.append("model must contain exactly one absorbing death state")
    death_id = death_ids[0] if len(death_ids) == 1 else None
    state_index = {state_id: index for index, state_id in enumerate(state_ids)}

    initial = model.get("initial_distribution")
    if not isinstance(initial, list) or len(initial) != len(state_ids) or any(not finite(value) or not 0 <= float(value) <= 1 for value in initial):
        errors.append("initial_distribution is invalid")
    elif abs(math.fsum(float(value) for value in initial) - 1.0) > 1e-10:
        errors.append("initial_distribution must sum to one")
    elif death_id is not None and float(initial[state_index[death_id]]) != 0.0:
        errors.append("initial_distribution must assign zero mass to death")
    cycle_length = model.get("cycle_length_years")
    if not finite(cycle_length) or not 0 < float(cycle_length) <= 5:
        errors.append("cycle_length_years must be in (0, 5]")
    cycles = model.get("cycles")
    if isinstance(cycles, bool) or not isinstance(cycles, int) or not 1 <= cycles <= MAX_CYCLES:
        errors.append(f"cycles must be an integer in [1, {MAX_CYCLES}]")
        cycles = 1

    trackers_raw = model.get("event_trackers")
    trackers: list[dict[str, Any]] = trackers_raw if isinstance(trackers_raw, list) else []
    if not 1 <= len(trackers) <= MAX_TRACKERS:
        errors.append(f"event_trackers must contain 1-{MAX_TRACKERS} entries")
    tracker_ids: list[str] = []
    tracker_caps: dict[str, int] = {}
    for index, tracker in enumerate(trackers):
        prefix = f"model.event_trackers[{index}]"
        fields = {"id", "label", "from_states", "to_state", "maximum_count", "rationale", "evidence_record_ids"}
        if not exact(tracker, fields):
            errors.append(f"{prefix} fields are invalid")
            continue
        tracker_id = tracker.get("id")
        from_states = tracker.get("from_states")
        maximum_count = tracker.get("maximum_count")
        if not safe_id(tracker_id) or not text(tracker.get("label")) or not text(tracker.get("rationale")):
            errors.append(f"{prefix} identifiers or descriptive fields are invalid")
        else:
            tracker_ids.append(tracker_id)
        if not _unique_text(from_states, identifiers=True) or not set(from_states).issubset(state_index):
            errors.append(f"{prefix}.from_states are invalid")
        if tracker.get("to_state") not in state_index or tracker.get("to_state") in (from_states if isinstance(from_states, list) else []):
            errors.append(f"{prefix}.to_state is invalid or included in from_states")
        if isinstance(maximum_count, bool) or not isinstance(maximum_count, int) or not 1 <= maximum_count <= cycles:
            errors.append(f"{prefix}.maximum_count must be in [1, cycles]")
        elif safe_id(tracker_id):
            tracker_caps[tracker_id] = maximum_count
        _validate_evidence_ids(tracker.get("evidence_record_ids"), prefix, available_evidence, errors)
    if len(tracker_ids) != len(set(tracker_ids)):
        errors.append("event tracker ids must be unique")

    strategies_raw = request.get("strategies")
    strategies: list[dict[str, Any]] = strategies_raw if isinstance(strategies_raw, list) else []
    if not 2 <= len(strategies) <= MAX_STRATEGIES:
        errors.append(f"strategies must contain 2-{MAX_STRATEGIES} entries")
    strategy_ids: list[str] = []
    compiled_strategies: list[dict[str, Any]] = []
    for strategy_index, strategy in enumerate(strategies):
        prefix = f"strategies[{strategy_index}]"
        if not exact(strategy, {"id", "label", "rationale", "evidence_record_ids", "state_rules", "transition_costs"}):
            errors.append(f"{prefix} fields are invalid")
            continue
        strategy_id = strategy.get("id")
        if not safe_id(strategy_id) or not text(strategy.get("label")) or not text(strategy.get("rationale")):
            errors.append(f"{prefix} identifiers or descriptive fields are invalid")
        else:
            strategy_ids.append(strategy_id)
        _validate_evidence_ids(strategy.get("evidence_record_ids"), prefix, available_evidence, errors)
        state_rules = strategy.get("state_rules")
        if not isinstance(state_rules, list) or len(state_rules) != len(state_ids):
            errors.append(f"{prefix}.state_rules must contain one entry per state")
            state_rules = []
        seen_states: list[str] = []
        compiled_by_state: dict[str, list[dict[str, Any]]] = {}
        rule_ids: list[str] = []
        for state_rule_index, state_rule in enumerate(state_rules):
            state_prefix = f"{prefix}.state_rules[{state_rule_index}]"
            if not exact(state_rule, {"state_id", "rules"}):
                errors.append(f"{state_prefix} fields are invalid")
                continue
            state_id = state_rule.get("state_id")
            seen_states.append(state_id)
            rules = state_rule.get("rules")
            if state_id not in state_index or not isinstance(rules, list) or not rules:
                errors.append(f"{state_prefix} state_id or rules are invalid")
                continue
            compiled_rules: list[dict[str, Any]] = []
            conditional_ranges: list[tuple[str, dict[str, tuple[int, int]]]] = []
            otherwise_count = 0
            for rule_index, rule in enumerate(rules):
                rule_prefix = f"{state_prefix}.rules[{rule_index}]"
                fields = {"id", "condition", "probabilities", "annual_cost", "utility", "rationale", "evidence_record_ids"}
                if not exact(rule, fields):
                    errors.append(f"{rule_prefix} fields are invalid")
                    continue
                rule_id = rule.get("id")
                if not safe_id(rule_id) or not text(rule.get("rationale")):
                    errors.append(f"{rule_prefix} id or rationale is invalid")
                else:
                    rule_ids.append(rule_id)
                condition = _validate_condition(rule.get("condition"), rule_prefix, cycles, tracker_caps, errors)
                if condition is None:
                    otherwise_count += 1
                    if rule_index != len(rules) - 1:
                        errors.append(f"{rule_prefix} otherwise rule must be last")
                else:
                    conditional_ranges.append((str(rule_id), condition))
                probabilities = rule.get("probabilities")
                if not isinstance(probabilities, list) or len(probabilities) != len(state_ids) or any(
                    not finite(value) or not 0 <= float(value) <= 1 for value in probabilities
                ):
                    errors.append(f"{rule_prefix}.probabilities are invalid")
                elif abs(math.fsum(float(value) for value in probabilities) - 1.0) > 1e-10:
                    errors.append(f"{rule_prefix}.probabilities must sum to one")
                elif state_absorbing.get(state_id) and any(
                    abs(float(value) - (1.0 if index == state_index[state_id] else 0.0)) > 1e-12
                    for index, value in enumerate(probabilities)
                ):
                    errors.append(f"{rule_prefix} absorbing-state row must remain in the same state")
                annual_cost, utility = rule.get("annual_cost"), rule.get("utility")
                if not finite(annual_cost) or float(annual_cost) < 0:
                    errors.append(f"{rule_prefix}.annual_cost must be finite and nonnegative")
                if not finite(utility) or not -1 <= float(utility) <= 1:
                    errors.append(f"{rule_prefix}.utility must be in [-1, 1]")
                if state_id == death_id and (annual_cost != 0 or utility != 0):
                    errors.append(f"{rule_prefix} death rewards must be zero")
                _validate_evidence_ids(rule.get("evidence_record_ids"), rule_prefix, available_evidence, errors)
                compiled_rules.append({"rule": rule, "condition": condition})
            if otherwise_count != 1:
                errors.append(f"{state_prefix} must contain exactly one final otherwise rule")
            for left_index, (left_id, left) in enumerate(conditional_ranges):
                for right_id, right in conditional_ranges[left_index + 1:]:
                    if _conditions_overlap(left, right, cycles, tracker_caps):
                        errors.append(f"{state_prefix} conditional rules {left_id} and {right_id} overlap")
            compiled_by_state[state_id] = compiled_rules
        if set(seen_states) != set(state_ids) or len(seen_states) != len(set(seen_states)):
            errors.append(f"{prefix}.state_rules state ids must exactly cover model states")
        if len(rule_ids) != len(set(rule_ids)):
            errors.append(f"{prefix} rule ids must be unique")

        transition_costs = strategy.get("transition_costs")
        if not isinstance(transition_costs, list):
            errors.append(f"{prefix}.transition_costs must be a list")
            transition_costs = []
        transition_cost_map: dict[tuple[str, str], float] = {}
        transition_cost_ids: list[str] = []
        for cost_index, entry in enumerate(transition_costs):
            item_prefix = f"{prefix}.transition_costs[{cost_index}]"
            fields = {"id", "from_state", "to_state", "cost", "rationale", "evidence_record_ids"}
            if not exact(entry, fields):
                errors.append(f"{item_prefix} fields are invalid")
                continue
            entry_id = entry.get("id")
            pair = (entry.get("from_state"), entry.get("to_state"))
            if not safe_id(entry_id) or not text(entry.get("rationale")):
                errors.append(f"{item_prefix} id or rationale is invalid")
            else:
                transition_cost_ids.append(entry_id)
            if pair[0] not in state_index or pair[1] not in state_index or pair[0] == pair[1] or pair in transition_cost_map:
                errors.append(f"{item_prefix} transition pair is invalid or duplicated")
            if not finite(entry.get("cost")) or float(entry.get("cost")) < 0:
                errors.append(f"{item_prefix}.cost must be finite and nonnegative")
            else:
                transition_cost_map[pair] = float(entry["cost"])
            _validate_evidence_ids(entry.get("evidence_record_ids"), item_prefix, available_evidence, errors)
        if len(transition_cost_ids) != len(set(transition_cost_ids)):
            errors.append(f"{prefix} transition cost ids must be unique")
        compiled_strategies.append({
            "strategy": strategy,
            "rules": compiled_by_state,
            "transition_costs": transition_cost_map,
        })
    if len(strategy_ids) != len(set(strategy_ids)):
        errors.append("strategy ids must be unique")

    economics = request.get("economics")
    economics_fields = {"currency", "price_year", "discount_rate_costs", "discount_rate_outcomes", "willingness_to_pay"}
    if not exact(economics, economics_fields):
        errors.append("economics fields are invalid")
        economics = {}
    if ISO_CURRENCY.fullmatch(str(economics.get("currency", ""))) is None:
        errors.append("economics.currency must be an ISO-style three-letter code")
    price_year = economics.get("price_year")
    if isinstance(price_year, bool) or not isinstance(price_year, int) or not 1900 <= price_year <= 2100:
        errors.append("economics.price_year is invalid")
    for key in ("discount_rate_costs", "discount_rate_outcomes"):
        if not finite(economics.get(key)) or not 0 <= float(economics[key]) <= 1:
            errors.append(f"economics.{key} must be in [0, 1]")
    if not finite(economics.get("willingness_to_pay")) or float(economics["willingness_to_pay"]) <= 0:
        errors.append("economics.willingness_to_pay must be positive")

    simulation = request.get("simulation")
    simulation_fields = {
        "patients_per_replicate", "replicates", "base_seed", "random_number_generator",
        "common_random_numbers", "trace_replicate", "trace_patient_indices", "maximum_simulation_steps",
    }
    if not exact(simulation, simulation_fields):
        errors.append("simulation fields are invalid")
        simulation = {}
    patients = simulation.get("patients_per_replicate")
    replicates = simulation.get("replicates")
    base_seed = simulation.get("base_seed")
    if isinstance(patients, bool) or not isinstance(patients, int) or not 100 <= patients <= MAX_PATIENTS:
        errors.append(f"patients_per_replicate must be an integer in [100, {MAX_PATIENTS}]")
        patients = 0
    if isinstance(replicates, bool) or not isinstance(replicates, int) or not 3 <= replicates <= MAX_REPLICATES:
        errors.append(f"replicates must be an integer in [3, {MAX_REPLICATES}]")
        replicates = 0
    if isinstance(base_seed, bool) or not isinstance(base_seed, int) or not 0 <= base_seed <= MAX_SEED:
        errors.append(f"base_seed must be an integer in [0, {MAX_SEED}]")
    if simulation.get("random_number_generator") != "splitmix64_counter_top53_v1":
        errors.append("random_number_generator must be splitmix64_counter_top53_v1")
    if simulation.get("common_random_numbers") != "synchronized_initial_and_cycle_transition_uniforms":
        errors.append("common_random_numbers must use the fixed synchronized contract")
    trace_replicate = simulation.get("trace_replicate")
    if isinstance(trace_replicate, bool) or not isinstance(trace_replicate, int) or not 0 <= trace_replicate < max(replicates, 1):
        errors.append("trace_replicate is invalid")
    trace_indices = simulation.get("trace_patient_indices")
    if not isinstance(trace_indices, list) or not 1 <= len(trace_indices) <= MAX_TRACE_PATIENTS or len(trace_indices) != len(set(trace_indices)) or any(
        isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < max(patients, 1) for index in trace_indices
    ):
        errors.append(f"trace_patient_indices must contain 1-{MAX_TRACE_PATIENTS} unique in-range indices")
    if simulation.get("maximum_simulation_steps") != MAX_SIMULATION_STEPS:
        errors.append(f"maximum_simulation_steps must equal the fixed cap {MAX_SIMULATION_STEPS}")
    steps = patients * replicates * cycles * len(strategies)
    if steps > MAX_SIMULATION_STEPS:
        errors.append(f"simulation requests {steps} patient-cycles, exceeding the cap {MAX_SIMULATION_STEPS}")

    output = request.get("output")
    expected_output = f"heor/semi-markov-microsimulation-runs/{simulation_id}" if safe_id(simulation_id) else None
    if not exact(output, {"directory"}) or output.get("directory") != expected_output or resolve_output_directory(workspace, output.get("directory")) is None:
        errors.append("output.directory must be the safe immutable simulation directory")
    authorization = request.get("human_authorization")
    if not exact(authorization, {"actor", "authorized_at", "scope"}) or not text(authorization.get("actor")) or ISO_UTC.fullmatch(str(authorization.get("authorized_at", ""))) is None or authorization.get("scope") != "execute_local_semi_markov_microsimulation":
        errors.append("human_authorization is invalid")
    limitations = request.get("limitations")
    if not _unique_text(limitations):
        errors.append("limitations must be a non-empty unique text list")
    gate = request.get("human_gate")
    if not exact(gate, {"status", "required_checks"}) or gate.get("status") != "awaiting_method_review" or gate.get("required_checks") != REQUIRED_REVIEW_CHECKS:
        errors.append("human_gate must contain the exact eight-check method review")

    facts.update({
        "state_ids": state_ids,
        "state_index": state_index,
        "death_id": death_id,
        "tracker_caps": tracker_caps,
        "trackers": trackers,
        "compiled_strategies": compiled_strategies,
        "steps": steps,
    })
    return errors, facts


def _splitmix64(value: int) -> int:
    value = (value + 0x9E3779B97F4A7C15) & MASK64
    value = ((value ^ (value >> 30)) * 0xBF58476D1CE4E5B9) & MASK64
    value = ((value ^ (value >> 27)) * 0x94D049BB133111EB) & MASK64
    return (value ^ (value >> 31)) & MASK64


def counter_uniform(seed: int, replicate: int, patient: int, cycle: int, stream: int) -> float:
    value = seed & MASK64
    value ^= ((replicate + 1) * 0xD2B74407B1CE6E93) & MASK64
    value ^= ((patient + 1) * 0xCA5A826395121157) & MASK64
    value ^= ((cycle + 1) * 0x9E3779B185EBCA87) & MASK64
    value ^= ((stream + 1) * 0xA24BAED4963EE407) & MASK64
    return float(_splitmix64(value) >> 11) * (1.0 / float(1 << 53))


def _draw(probabilities: list[Any], uniform: float) -> int:
    cumulative = 0.0
    for index, probability in enumerate(probabilities):
        cumulative += float(probability)
        if uniform < cumulative or index == len(probabilities) - 1:
            return index
    raise AssertionError("unreachable probability draw")


def _matches(condition: dict[str, tuple[int, int]] | None, dwell: int, trackers: dict[str, int]) -> bool:
    if condition is None:
        return True
    low, high = condition.get("__time__", (0, MAX_CYCLES))
    if not low <= dwell <= high:
        return False
    return all(low <= trackers.get(key, 0) <= high for key, (low, high) in condition.items() if key != "__time__")


def _select_rule(compiled_rules: list[dict[str, Any]], dwell: int, trackers: dict[str, int]) -> dict[str, Any]:
    fallback: dict[str, Any] | None = None
    matches: list[dict[str, Any]] = []
    for entry in compiled_rules:
        if entry["condition"] is None:
            fallback = entry["rule"]
        elif _matches(entry["condition"], dwell, trackers):
            matches.append(entry["rule"])
    if len(matches) > 1:
        raise ValueError(f"runtime rule selection matched {len(matches)} conditional rules")
    if matches:
        return matches[0]
    if fallback is None:
        raise ValueError("runtime rule selection has no otherwise rule")
    return fallback


def _increment_trackers(trackers: dict[str, int], definitions: list[dict[str, Any]], from_state: str, to_state: str) -> dict[str, int]:
    updated = dict(trackers)
    for definition in definitions:
        if from_state in definition["from_states"] and to_state == definition["to_state"]:
            updated[definition["id"]] = min(updated[definition["id"]] + 1, definition["maximum_count"])
    return updated


def _mean_se(values: list[float]) -> tuple[float, float]:
    mean = math.fsum(values) / len(values)
    if len(values) == 1:
        return mean, 0.0
    variance = math.fsum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return mean, math.sqrt(variance / len(values))


def _sample_sd(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = math.fsum(values) / len(values)
    return math.sqrt(math.fsum((value - mean) ** 2 for value in values) / (len(values) - 1))


def execute_simulation(request: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    model = request["model"]
    economics = request["economics"]
    simulation = request["simulation"]
    states = facts["state_ids"]
    state_index = facts["state_index"]
    death_index = state_index[facts["death_id"]]
    trackers_def = facts["trackers"]
    tracker_ids = [tracker["id"] for tracker in trackers_def]
    cycles = model["cycles"]
    cycle_length = float(model["cycle_length_years"])
    patients = simulation["patients_per_replicate"]
    replicates = simulation["replicates"]
    seed = simulation["base_seed"]
    trace_replicate = simulation["trace_replicate"]
    trace_patients = set(simulation["trace_patient_indices"])
    cost_rate = float(economics["discount_rate_costs"])
    outcome_rate = float(economics["discount_rate_outcomes"])
    wtp = float(economics["willingness_to_pay"])
    initial = model["initial_distribution"]
    trace_rows: list[dict[str, Any]] = []
    strategy_patient_results: dict[str, list[dict[str, Any]]] = {}
    strategy_replicates: dict[str, list[dict[str, Any]]] = {}
    strategy_outputs: list[dict[str, Any]] = []

    for compiled in facts["compiled_strategies"]:
        strategy = compiled["strategy"]
        strategy_id = strategy["id"]
        rules_by_state = compiled["rules"]
        transition_costs = compiled["transition_costs"]
        patient_results: list[dict[str, Any]] = []
        replicate_results: list[dict[str, Any]] = []
        occupancy = [[0 for _ in states] for _ in range(cycles + 1)]
        for replicate in range(replicates):
            replicate_start = len(patient_results)
            for patient in range(patients):
                initial_uniform = counter_uniform(seed, replicate, patient, 0, 0)
                current_index = _draw(initial, initial_uniform)
                current_state = states[current_index]
                dwell = 0
                tracker_counts = {tracker_id: 0 for tracker_id in tracker_ids}
                total_cost = 0.0
                total_qaly = 0.0
                total_life_years = 0.0
                occupancy[0][current_index] += 1
                for cycle in range(1, cycles + 1):
                    start_state = current_state
                    start_index = state_index[start_state]
                    start_dwell = dwell
                    start_trackers = dict(tracker_counts)
                    start_rule = _select_rule(rules_by_state[start_state], start_dwell, start_trackers)
                    transition_uniform = counter_uniform(seed, replicate, patient, cycle, 1)
                    end_index = _draw(start_rule["probabilities"], transition_uniform)
                    end_state = states[end_index]
                    end_trackers = _increment_trackers(start_trackers, trackers_def, start_state, end_state)
                    end_dwell = start_dwell + 1 if end_state == start_state else 0
                    end_rule = _select_rule(rules_by_state[end_state], end_dwell, end_trackers)
                    start_time = (cycle - 1) * cycle_length
                    end_time = cycle * cycle_length
                    start_cost = 0.5 * float(start_rule["annual_cost"]) * cycle_length / ((1.0 + cost_rate) ** start_time)
                    end_cost = 0.5 * float(end_rule["annual_cost"]) * cycle_length / ((1.0 + cost_rate) ** end_time)
                    transition_cost = transition_costs.get((start_state, end_state), 0.0) / ((1.0 + cost_rate) ** end_time)
                    qaly = 0.5 * float(start_rule["utility"]) * cycle_length / ((1.0 + outcome_rate) ** start_time)
                    qaly += 0.5 * float(end_rule["utility"]) * cycle_length / ((1.0 + outcome_rate) ** end_time)
                    life_years = 0.5 * (1.0 if start_index != death_index else 0.0) * cycle_length / ((1.0 + outcome_rate) ** start_time)
                    life_years += 0.5 * (1.0 if end_index != death_index else 0.0) * cycle_length / ((1.0 + outcome_rate) ** end_time)
                    cycle_cost = start_cost + end_cost + transition_cost
                    total_cost += cycle_cost
                    total_qaly += qaly
                    total_life_years += life_years
                    if replicate == trace_replicate and patient in trace_patients:
                        trace_rows.append({
                            "simulation_id": request["simulation_id"],
                            "strategy_id": strategy_id,
                            "replicate": replicate,
                            "patient_index": patient,
                            "cycle": cycle,
                            "initial_uniform": initial_uniform if cycle == 1 else None,
                            "transition_uniform": transition_uniform,
                            "start_state": start_state,
                            "start_time_in_state_cycles": start_dwell,
                            "start_tracker_counts": start_trackers,
                            "rule_id": start_rule["id"],
                            "end_state": end_state,
                            "end_time_in_state_cycles": end_dwell,
                            "end_tracker_counts": end_trackers,
                            "state_cost": start_cost + end_cost,
                            "transition_cost": transition_cost,
                            "discounted_qaly": qaly,
                            "discounted_life_years": life_years,
                            "cumulative_cost": total_cost,
                            "cumulative_qaly": total_qaly,
                        })
                    current_state = end_state
                    dwell = end_dwell
                    tracker_counts = end_trackers
                    occupancy[cycle][end_index] += 1
                patient_results.append({
                    "replicate": replicate,
                    "patient_index": patient,
                    "total_cost": total_cost,
                    "total_qaly": total_qaly,
                    "total_life_years": total_life_years,
                    "final_state": current_state,
                    "tracker_counts": tracker_counts,
                })
            replicate_slice = patient_results[replicate_start:]
            replicate_results.append({
                "replicate": replicate,
                "mean_cost": math.fsum(row["total_cost"] for row in replicate_slice) / patients,
                "mean_qaly": math.fsum(row["total_qaly"] for row in replicate_slice) / patients,
                "mean_life_years": math.fsum(row["total_life_years"] for row in replicate_slice) / patients,
            })
        total_people = patients * replicates
        costs = [row["total_cost"] for row in patient_results]
        qalys = [row["total_qaly"] for row in patient_results]
        life_years = [row["total_life_years"] for row in patient_results]
        mean_cost, se_cost = _mean_se(costs)
        mean_qaly, se_qaly = _mean_se(qalys)
        mean_life, se_life = _mean_se(life_years)
        tracker_summary = {}
        for tracker_id in tracker_ids:
            values = [float(row["tracker_counts"][tracker_id]) for row in patient_results]
            tracker_summary[tracker_id] = {
                "mean_final_count": math.fsum(values) / len(values),
                "proportion_with_any": math.fsum(value > 0 for value in values) / len(values),
                "proportion_at_cap": math.fsum(value >= facts["tracker_caps"][tracker_id] for value in values) / len(values),
            }
        occupancy_output = [
            {
                "cycle": cycle,
                "proportions": {
                    state: occupancy[cycle][index] / total_people for index, state in enumerate(states)
                },
            }
            for cycle in range(cycles + 1)
        ]
        strategy_outputs.append({
            "id": strategy_id,
            "label": strategy["label"],
            "mean_cost": mean_cost,
            "standard_error_cost": se_cost,
            "mean_qaly": mean_qaly,
            "standard_error_qaly": se_qaly,
            "mean_life_years": mean_life,
            "standard_error_life_years": se_life,
            "tracker_summary": tracker_summary,
            "state_occupancy": occupancy_output,
            "replicate_estimates": replicate_results,
        })
        strategy_patient_results[strategy_id] = patient_results
        strategy_replicates[strategy_id] = replicate_results

    baseline_id = request["strategies"][0]["id"]
    baseline_rows = strategy_patient_results[baseline_id]
    comparisons: list[dict[str, Any]] = []
    for strategy in request["strategies"][1:]:
        strategy_id = strategy["id"]
        comparison_rows = strategy_patient_results[strategy_id]
        delta_costs = [right["total_cost"] - left["total_cost"] for left, right in zip(baseline_rows, comparison_rows)]
        delta_qalys = [right["total_qaly"] - left["total_qaly"] for left, right in zip(baseline_rows, comparison_rows)]
        delta_nmbs = [wtp * qaly - cost for cost, qaly in zip(delta_costs, delta_qalys)]
        delta_cost, se_delta_cost = _mean_se(delta_costs)
        delta_qaly, se_delta_qaly = _mean_se(delta_qalys)
        delta_nmb, se_delta_nmb = _mean_se(delta_nmbs)
        if delta_qaly > 0 and delta_cost < 0:
            classification, icer = "dominant_arithmetic_pattern", None
        elif delta_qaly < 0 and delta_cost > 0:
            classification, icer = "dominated_arithmetic_pattern", None
        elif abs(delta_qaly) <= 1e-15:
            classification, icer = "incremental_qaly_near_zero", None
        else:
            classification, icer = "ratio_reported_without_decision_rule", delta_cost / delta_qaly
        replicate_deltas = []
        for replicate in range(replicates):
            base = strategy_replicates[baseline_id][replicate]
            other = strategy_replicates[strategy_id][replicate]
            dc = other["mean_cost"] - base["mean_cost"]
            dq = other["mean_qaly"] - base["mean_qaly"]
            replicate_deltas.append({
                "replicate": replicate,
                "incremental_cost": dc,
                "incremental_qaly": dq,
                "incremental_net_monetary_benefit": wtp * dq - dc,
            })
        comparisons.append({
            "baseline_strategy_id": baseline_id,
            "strategy_id": strategy_id,
            "incremental_cost": delta_cost,
            "standard_error_incremental_cost": se_delta_cost,
            "incremental_qaly": delta_qaly,
            "standard_error_incremental_qaly": se_delta_qaly,
            "incremental_net_monetary_benefit": delta_nmb,
            "standard_error_incremental_net_monetary_benefit": se_delta_nmb,
            "icer": icer,
            "icer_classification": classification,
            "replicate_estimates": replicate_deltas,
            "replicate_sd_incremental_net_monetary_benefit": _sample_sd([
                row["incremental_net_monetary_benefit"] for row in replicate_deltas
            ]),
        })

    warnings = [
        "First-order Monte Carlo error remains; inspect paired standard errors and replicate variation before interpretation.",
        "Parameter uncertainty and structural uncertainty are not propagated by this bounded engine.",
        "Arithmetic dominance labels and ICER ratios are descriptive and do not authorize a cost-effectiveness or reimbursement conclusion.",
    ]
    return {
        "method": {
            "model_type": model["type"],
            "random_number_generator": simulation["random_number_generator"],
            "common_random_numbers": simulation["common_random_numbers"],
            "transition_timing": model["transition_timing"],
            "reward_timing": model["reward_timing"],
            "parameter_uncertainty": "not_modeled",
            "automatic_strategy_selection": "none",
        },
        "performance": {
            "patients_per_replicate": patients,
            "replicates": replicates,
            "strategy_count": len(request["strategies"]),
            "cycles": cycles,
            "simulation_steps": facts["steps"],
            "maximum_simulation_steps": MAX_SIMULATION_STEPS,
        },
        "strategies": strategy_outputs,
        "comparisons": comparisons,
        "monte_carlo_error": {
            "patient_level_method": "sample_standard_error_with_paired_strategy_differences",
            "replicate_method": "independent_counter_replicates_with_common_random_numbers_within_replicate",
            "automatic_stability_thresholds": "none",
        },
        "warnings": warnings,
        "_trace_rows": trace_rows,
    }


def current_python_identity() -> dict[str, str]:
    executable = Path(sys.executable).resolve()
    return {
        "python_version": sys.version.split()[0],
        "python_executable_sha256": digest(executable.read_bytes()),
    }


def _close(left: Any, right: Any) -> bool:
    if left is None or right is None:
        return left is right
    return finite(left) and finite(right) and abs(float(left) - float(right)) <= FLOAT_TOLERANCE * max(1.0, abs(float(left)), abs(float(right)))


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
        for index, value in enumerate(right):
            _deep_close(left[index], value, f"{path}[{index}]", errors)
    elif finite(right):
        if not _close(left, right):
            errors.append(f"{path} differs from deterministic replay")
    elif left != right:
        errors.append(f"{path} differs from deterministic replay")


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
        return {"complete": False, "reviewable": False, "errors": ["result fields do not match schema 0.1.0"]}
    if result.get("schema_version") != RESULT_SCHEMA_VERSION or not safe_id(result.get("simulation_id")):
        errors.append("result schema_version or simulation_id is invalid")
    if result.get("status") != "awaiting_method_review":
        errors.append("result status must be awaiting_method_review")
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
            if request.get("simulation_id") != result.get("simulation_id"):
                errors.append("result simulation_id does not match request")
    expected_evidence = request.get("evidence_synthesis", {}) if request else {}
    if result.get("evidence_synthesis") != {"path": expected_evidence.get("path"), "sha256": expected_evidence.get("sha256")}:
        errors.append("result evidence_synthesis binding does not match request")
    runtime = result.get("runtime")
    if not exact(runtime, {"evaluator", "python_version", "python_executable_sha256", "evaluator_source"}):
        errors.append("result runtime fields are invalid")
    else:
        if runtime.get("evaluator") != EVALUATOR or not text(runtime.get("python_version")) or SHA256.fullmatch(str(runtime.get("python_executable_sha256", ""))) is None:
            errors.append("result runtime identity is invalid")
        evaluator = runtime.get("evaluator_source")
        evaluator_path = resolve_file(workspace, evaluator.get("path") if isinstance(evaluator, dict) else None)
        if not exact(evaluator, {"path", "sha256"}) or evaluator_path is None:
            errors.append("result evaluator source binding is unsafe")
        else:
            evaluator_raw = evaluator_path.read_bytes()
            if digest(evaluator_raw) != evaluator.get("sha256") or evaluator_raw != Path(__file__).read_bytes():
                errors.append("result evaluator source differs from the active audited evaluator")
    trace = result.get("trace")
    trace_path = resolve_file(workspace, trace.get("path") if isinstance(trace, dict) else None)
    if not exact(trace, {"path", "sha256", "row_count", "replicate", "patient_indices"}) or trace_path is None:
        errors.append("result trace binding is unsafe")
    elif digest(trace_path.read_bytes()) != trace.get("sha256"):
        errors.append("trace sha256 does not match current bytes")
    if request and not errors:
        replay = execute_simulation(request, facts)
        replay_trace = canonical_trace_bytes(replay.pop("_trace_rows"))
        expected_trace = {
            "path": trace["path"],
            "sha256": digest(replay_trace),
            "row_count": len(replay_trace.splitlines()),
            "replicate": request["simulation"]["trace_replicate"],
            "patient_indices": request["simulation"]["trace_patient_indices"],
        }
        _deep_close(trace, expected_trace, "trace", errors)
        for field in ("method", "performance", "strategies", "comparisons", "monte_carlo_error", "warnings"):
            _deep_close(result.get(field), replay[field], field, errors)
        if result.get("limitations") != request.get("limitations"):
            errors.append("result limitations do not match request")
        if result.get("human_gate") != request.get("human_gate"):
            errors.append("result human_gate does not match request")
    complete = not errors
    return {
        "complete": complete,
        "reviewable": complete,
        "status": "complete" if complete else "incomplete",
        "simulation_id": result.get("simulation_id", ""),
        "result_path": str(result_path.relative_to(workspace)) if result_path.is_relative_to(workspace) else str(result_path),
        "result_sha256": digest(result_raw),
        "strategy_count": len(result.get("strategies", [])) if isinstance(result.get("strategies"), list) else 0,
        "patients_per_replicate": result.get("performance", {}).get("patients_per_replicate", 0),
        "replicates": result.get("performance", {}).get("replicates", 0),
        "cycles": result.get("performance", {}).get("cycles", 0),
        "simulation_steps": result.get("performance", {}).get("simulation_steps", 0),
        "trace_rows": result.get("trace", {}).get("row_count", 0),
        "errors": errors,
    }
