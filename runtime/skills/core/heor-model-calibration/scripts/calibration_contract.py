#!/usr/bin/env python3
"""Bounded deterministic cohort-model calibration contract and replay audit."""

from __future__ import annotations

import csv
import hashlib
import io
import itertools
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


REQUEST_SCHEMA_VERSION = "0.1.0"
RESULT_SCHEMA_VERSION = "0.1.0"
EVALUATOR = "ai4heor-cohort-model-calibration@0.1.0"
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_STATES = 6
MAX_PARAMETERS = 4
MAX_TARGETS = 100
MAX_CYCLES = 2_000
MAX_UNIFORMIZATION_INTENSITY = 30.0
FLOAT_TOLERANCE = 1e-9
SAFE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

REQUIRED_REVIEW_CHECKS = [
    "question_model_purpose_time_origin",
    "target_provenance_population_alignment_roles",
    "parameter_meaning_bounds_evidence",
    "goodness_of_fit_scaling_covariance_omission",
    "search_convergence_multistart_diagnostics",
    "local_identifiability_alternative_fits",
    "held_out_predictive_validation",
    "uncertainty_structure_and_downstream_limitations",
]

REQUEST_FIELDS = {
    "schema_version", "calibration_id", "status", "question", "evidence_synthesis",
    "model", "parameters", "targets", "goodness_of_fit", "search", "identifiability",
    "output", "human_authorization", "limitations", "human_gate",
}
RESULT_FIELDS = {
    "schema_version", "calibration_id", "status", "request", "evidence_synthesis",
    "runtime", "method", "best_fit", "target_fit", "search", "identifiability",
    "validation", "cross_implementation", "warnings", "limitations", "human_gate",
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


def _unique_text(values: Any, *, identifiers: bool = False) -> bool:
    validator = safe_id if identifiers else text
    return isinstance(values, list) and bool(values) and all(validator(value) for value in values) and len(values) == len(set(values))


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
    records = evidence.get("records")
    if not isinstance(records, list):
        errors.append("evidence_synthesis records must be a list")
    else:
        available = {record if isinstance(record, str) else record.get("id") for record in records if isinstance(record, (str, dict))}
        if isinstance(included, list) and not set(included).issubset(available):
            errors.append("evidence_synthesis does not contain every included record")
    facts["evidence_path"] = path
    facts["evidence_record_ids"] = set(included) if isinstance(included, list) else set()


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
    calibration_id = request.get("calibration_id")
    if not safe_id(calibration_id):
        errors.append("calibration_id is invalid")
    if request.get("status") != "ready_for_execution":
        errors.append("status must be ready_for_execution")

    question = request.get("question")
    if not exact(question, {"population", "purpose", "time_origin", "intended_use"}) or any(not text(question.get(key)) for key in question or {}):
        errors.append("question fields must be complete text")
    _validate_evidence(request, workspace, errors, facts)

    model = request.get("model")
    model_fields = {"type", "states", "initial_distribution", "cycle_length_years", "cycles", "matrix_exponential", "transitions"}
    if not exact(model, model_fields):
        errors.append("model fields are invalid")
        model = {}
    if model.get("type") != "homogeneous_continuous_time_cohort_state_transition":
        errors.append("model type is outside the bounded continuous-time cohort contract")
    states = model.get("states")
    if not _unique_text(states, identifiers=True) or not (2 <= len(states) <= MAX_STATES):
        errors.append(f"model states must contain 2-{MAX_STATES} unique safe identifiers")
        states = []
    initial = model.get("initial_distribution")
    if not isinstance(initial, list) or len(initial) != len(states) or any(not finite(value) or not 0 <= float(value) <= 1 for value in initial):
        errors.append("initial_distribution is invalid")
    elif abs(math.fsum(float(value) for value in initial) - 1.0) > 1e-10:
        errors.append("initial_distribution must sum to one")
    cycle_length = model.get("cycle_length_years")
    if not finite(cycle_length) or not 0 < float(cycle_length) <= 10:
        errors.append("cycle_length_years must be in (0, 10]")
    cycles = model.get("cycles")
    if isinstance(cycles, bool) or not isinstance(cycles, int) or not 1 <= cycles <= MAX_CYCLES:
        errors.append(f"cycles must be an integer in [1, {MAX_CYCLES}]")
    exponential = model.get("matrix_exponential")
    if not exact(exponential, {"method", "tail_tolerance", "maximum_terms"}) or exponential != {
        "method": "uniformization", "tail_tolerance": 1e-14, "maximum_terms": 512,
    }:
        errors.append("matrix_exponential must use the fixed uniformization contract")

    parameters = request.get("parameters")
    parameter_fields = {"id", "label", "transition_id", "unit", "lower", "upper", "search_scale", "status", "rationale", "evidence_record_ids"}
    if not isinstance(parameters, list) or not 1 <= len(parameters) <= MAX_PARAMETERS:
        errors.append(f"parameters must contain 1-{MAX_PARAMETERS} entries")
        parameters = []
    parameter_ids: list[str] = []
    transition_parameter_ids: list[str] = []
    for index, parameter in enumerate(parameters):
        prefix = f"parameters[{index}]"
        if not exact(parameter, parameter_fields):
            errors.append(f"{prefix} fields are invalid")
            continue
        parameter_ids.append(parameter.get("id"))
        transition_parameter_ids.append(parameter.get("transition_id"))
        if not safe_id(parameter.get("id")) or not safe_id(parameter.get("transition_id")):
            errors.append(f"{prefix} identifiers are invalid")
        if any(not text(parameter.get(key)) for key in ("label", "unit", "rationale")):
            errors.append(f"{prefix} descriptive fields are invalid")
        if parameter.get("status") != "unobservable_natural_history_parameter":
            errors.append(f"{prefix} status is invalid")
        if parameter.get("search_scale") not in {"linear", "log"}:
            errors.append(f"{prefix} search_scale is invalid")
        lower, upper = parameter.get("lower"), parameter.get("upper")
        if not finite(lower) or not finite(upper) or not 0 <= float(lower) < float(upper):
            errors.append(f"{prefix} bounds must be finite nonnegative and strictly ordered")
        elif parameter.get("search_scale") == "log" and float(lower) <= 0:
            errors.append(f"{prefix} log-scale lower bound must be positive")
        if not _unique_text(parameter.get("evidence_record_ids"), identifiers=True):
            errors.append(f"{prefix} evidence_record_ids are invalid")
        elif not set(parameter["evidence_record_ids"]).issubset(facts.get("evidence_record_ids", set())):
            errors.append(f"{prefix} evidence_record_ids are not all present in the bound evidence set")
    if len(parameter_ids) != len(set(parameter_ids)):
        errors.append("parameter ids must be unique")
    if len(transition_parameter_ids) != len(set(transition_parameter_ids)):
        errors.append("each calibrated transition must be unique across parameters")

    transitions = model.get("transitions")
    if not isinstance(transitions, list) or not transitions:
        errors.append("model transitions must be a non-empty list")
        transitions = []
    transition_ids: list[str] = []
    transition_pairs: list[tuple[Any, Any]] = []
    calibrated_bindings: dict[str, str] = {}
    for index, transition in enumerate(transitions):
        prefix = f"model.transitions[{index}]"
        source = transition.get("source") if isinstance(transition, dict) else None
        required = {"id", "from_state", "to_state", "source", "parameter_id"} if source == "calibrated_parameter" else {
            "id", "from_state", "to_state", "source", "rate_per_year", "rationale", "evidence_record_ids"
        }
        if not exact(transition, required):
            errors.append(f"{prefix} fields are invalid")
            continue
        transition_ids.append(transition["id"])
        transition_pairs.append((transition["from_state"], transition["to_state"]))
        if not safe_id(transition["id"]) or transition["from_state"] not in states or transition["to_state"] not in states or transition["from_state"] == transition["to_state"]:
            errors.append(f"{prefix} identifiers or states are invalid")
        if source == "calibrated_parameter":
            if not safe_id(transition.get("parameter_id")):
                errors.append(f"{prefix} parameter_id is invalid")
            else:
                calibrated_bindings[transition["id"]] = transition["parameter_id"]
        elif source == "fixed_rate":
            if not finite(transition.get("rate_per_year")) or float(transition["rate_per_year"]) < 0:
                errors.append(f"{prefix} fixed rate is invalid")
            if not text(transition.get("rationale")) or not _unique_text(transition.get("evidence_record_ids"), identifiers=True):
                errors.append(f"{prefix} fixed-rate evidence is invalid")
            elif not set(transition["evidence_record_ids"]).issubset(facts.get("evidence_record_ids", set())):
                errors.append(f"{prefix} evidence_record_ids are not all present in the bound evidence set")
        else:
            errors.append(f"{prefix} source is invalid")
    if len(transition_ids) != len(set(transition_ids)) or len(transition_pairs) != len(set(transition_pairs)):
        errors.append("transition ids and directed state pairs must be unique")
    for parameter in parameters:
        if not isinstance(parameter, dict):
            continue
        if calibrated_bindings.get(parameter.get("transition_id")) != parameter.get("id"):
            errors.append(f"parameter {parameter.get('id')} must bind exactly one calibrated transition")
    if set(calibrated_bindings.values()) != set(parameter_ids):
        errors.append("calibrated transitions and parameters must form a one-to-one binding")

    if states and finite(cycle_length):
        max_exit: dict[str, float] = {state: 0.0 for state in states}
        parameter_by_id = {parameter.get("id"): parameter for parameter in parameters if isinstance(parameter, dict)}
        for transition in transitions:
            if not isinstance(transition, dict) or transition.get("from_state") not in max_exit:
                continue
            if transition.get("source") == "fixed_rate" and finite(transition.get("rate_per_year")):
                upper_rate = float(transition["rate_per_year"])
            else:
                parameter = parameter_by_id.get(transition.get("parameter_id"), {})
                upper_rate = float(parameter.get("upper", math.inf)) if finite(parameter.get("upper")) else math.inf
            max_exit[transition["from_state"]] += upper_rate
        if max(max_exit.values(), default=0.0) * float(cycle_length) > MAX_UNIFORMIZATION_INTENSITY:
            errors.append("maximum exit rate times cycle length exceeds the bounded uniformization intensity")

    targets = request.get("targets")
    target_fields = {"id", "role", "cycle", "state", "measure", "observed", "standard_error", "population_alignment", "evidence_record_ids"}
    if not isinstance(targets, list) or not 2 <= len(targets) <= MAX_TARGETS:
        errors.append(f"targets must contain 2-{MAX_TARGETS} entries")
        targets = []
    target_ids: list[str] = []
    training = 0
    validation = 0
    for index, target in enumerate(targets):
        prefix = f"targets[{index}]"
        if not exact(target, target_fields):
            errors.append(f"{prefix} fields are invalid")
            continue
        target_ids.append(target.get("id"))
        if not safe_id(target.get("id")) or target.get("state") not in states:
            errors.append(f"{prefix} id or state is invalid")
        role = target.get("role")
        if role == "calibration":
            training += 1
        elif role == "validation":
            validation += 1
        else:
            errors.append(f"{prefix} role is invalid")
        if target.get("measure") != "state_occupancy_proportion":
            errors.append(f"{prefix} measure is outside the bounded contract")
        target_cycle = target.get("cycle")
        if isinstance(target_cycle, bool) or not isinstance(target_cycle, int) or not isinstance(cycles, int) or not 1 <= target_cycle <= cycles:
            errors.append(f"{prefix} cycle is invalid")
        if not finite(target.get("observed")) or not 0 <= float(target["observed"]) <= 1:
            errors.append(f"{prefix} observed proportion is invalid")
        if not finite(target.get("standard_error")) or float(target["standard_error"]) <= 0:
            errors.append(f"{prefix} standard_error must be positive")
        if not text(target.get("population_alignment")) or not _unique_text(target.get("evidence_record_ids"), identifiers=True):
            errors.append(f"{prefix} target evidence and population alignment are invalid")
        elif not set(target["evidence_record_ids"]).issubset(facts.get("evidence_record_ids", set())):
            errors.append(f"{prefix} evidence_record_ids are not all present in the bound evidence set")
    if len(target_ids) != len(set(target_ids)):
        errors.append("target ids must be unique")
    if training <= len(parameters):
        errors.append("the request requires more training targets than parameters")
    if validation < 1:
        errors.append("the request requires at least one held-out validation target")

    goodness = request.get("goodness_of_fit")
    if goodness != {
        "training_loss": "sum_squared_standardized_residuals",
        "standard_error_use": "target_specific_scaling_only",
        "target_covariance": "not_modeled",
        "automatic_fit_thresholds": "none",
    }:
        errors.append("goodness_of_fit must use the fixed scaled-loss contract without covariance or automatic thresholds")
    search = request.get("search")
    if search != {
        "method": "deterministic_grid_multistart_pattern_search",
        "grid_levels_per_parameter": 7,
        "local_start_count": 8,
        "minimum_normalized_step": 1e-7,
        "maximum_iterations_per_start": 500,
        "tie_break": "objective_then_lexicographic_normalized_parameters",
    }:
        errors.append("search must use the fixed deterministic multistart contract")
    identifiability = request.get("identifiability")
    if identifiability != {
        "method": "finite_difference_scaled_target_jacobian",
        "normalized_derivative_step": 1e-5,
        "relative_rank_tolerance": 1e-8,
        "automatic_acceptance_thresholds": "none",
    }:
        errors.append("identifiability must use the fixed local diagnostic without automatic thresholds")

    output = request.get("output")
    expected_output = f"heor/model-calibration-runs/{calibration_id}" if safe_id(calibration_id) else None
    if not exact(output, {"directory"}) or output.get("directory") != expected_output or resolve_output_directory(workspace, output.get("directory")) is None:
        errors.append("output directory is invalid or does not bind calibration_id")
    authorization = request.get("human_authorization")
    if not exact(authorization, {"actor", "authorized_at", "scope"}) or not text(authorization.get("actor") if isinstance(authorization, dict) else None) or ISO_UTC.fullmatch(str(authorization.get("authorized_at", "") if isinstance(authorization, dict) else "")) is None or authorization.get("scope") != "execute_local_model_calibration":
        errors.append("human_authorization is invalid")
    limitations = request.get("limitations")
    if not isinstance(limitations, list) or len(limitations) < 2 or any(not text(value) for value in limitations):
        errors.append("limitations must contain at least two explicit statements")
    gate = request.get("human_gate")
    if gate != {"status": "awaiting_method_review", "required_checks": REQUIRED_REVIEW_CHECKS}:
        errors.append("human_gate must preserve all researcher-owned method review checks")

    facts.update({"states": states, "state_index": {state: index for index, state in enumerate(states)}})
    return errors, facts


def _matmul(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    return [[math.fsum(left[row][inner] * right[inner][column] for inner in range(len(right))) for column in range(len(right[0]))] for row in range(len(left))]


def _transition_matrix(request: dict[str, Any], values: dict[str, float], facts: dict[str, Any]) -> list[list[float]]:
    count = len(facts["states"])
    generator = [[0.0] * count for _ in range(count)]
    for transition in request["model"]["transitions"]:
        source = facts["state_index"][transition["from_state"]]
        destination = facts["state_index"][transition["to_state"]]
        rate = values[transition["parameter_id"]] if transition["source"] == "calibrated_parameter" else float(transition["rate_per_year"])
        generator[source][destination] += rate
        generator[source][source] -= rate
    maximum_exit = max(-generator[index][index] for index in range(count))
    identity = [[1.0 if row == column else 0.0 for column in range(count)] for row in range(count)]
    if maximum_exit == 0:
        return identity
    embedded = [[identity[row][column] + generator[row][column] / maximum_exit for column in range(count)] for row in range(count)]
    intensity = maximum_exit * float(request["model"]["cycle_length_years"])
    probability = math.exp(-intensity)
    cumulative = probability
    power = identity
    result = [[probability * value for value in row] for row in power]
    tolerance = float(request["model"]["matrix_exponential"]["tail_tolerance"])
    maximum_terms = int(request["model"]["matrix_exponential"]["maximum_terms"])
    for order in range(1, maximum_terms):
        power = _matmul(power, embedded)
        probability *= intensity / order
        cumulative += probability
        for row, column in itertools.product(range(count), repeat=2):
            result[row][column] += probability * power[row][column]
        if 1.0 - cumulative <= tolerance:
            break
    else:
        raise ValueError("uniformization did not reach the declared tail tolerance")
    for row in result:
        total = math.fsum(row)
        if total <= 0 or any(value < -1e-12 or not math.isfinite(value) for value in row):
            raise ValueError("uniformization produced an invalid transition matrix")
        for column, value in enumerate(row):
            row[column] = max(0.0, value) / total
    return result


def _simulate(request: dict[str, Any], values: dict[str, float], facts: dict[str, Any]) -> list[list[float]]:
    transition = _transition_matrix(request, values, facts)
    rows = [[float(value) for value in request["model"]["initial_distribution"]]]
    count = len(facts["states"])
    for _ in range(request["model"]["cycles"]):
        current = rows[-1]
        next_row = [math.fsum(current[source] * transition[source][destination] for source in range(count)) for destination in range(count)]
        total = math.fsum(next_row)
        rows.append([max(0.0, value) / total for value in next_row])
    return rows


def _actual_values(request: dict[str, Any], normalized: tuple[float, ...]) -> dict[str, float]:
    result: dict[str, float] = {}
    for parameter, coordinate in zip(request["parameters"], normalized):
        lower, upper = float(parameter["lower"]), float(parameter["upper"])
        if parameter["search_scale"] == "linear":
            value = lower + coordinate * (upper - lower)
        else:
            value = math.exp(math.log(lower) + coordinate * (math.log(upper) - math.log(lower)))
        result[parameter["id"]] = value
    return result


def _predictions(request: dict[str, Any], normalized: tuple[float, ...], facts: dict[str, Any]) -> tuple[dict[str, float], dict[str, float]]:
    values = _actual_values(request, normalized)
    occupancy = _simulate(request, values, facts)
    predictions = {target["id"]: occupancy[target["cycle"]][facts["state_index"][target["state"]]] for target in request["targets"]}
    return values, predictions


def _objective(request: dict[str, Any], normalized: tuple[float, ...], facts: dict[str, Any]) -> tuple[float, dict[str, float], dict[str, float]]:
    values, predictions = _predictions(request, normalized, facts)
    loss = math.fsum(((predictions[target["id"]] - float(target["observed"])) / float(target["standard_error"])) ** 2 for target in request["targets"] if target["role"] == "calibration")
    return loss, values, predictions


def _candidate_key(candidate: tuple[float, tuple[float, ...]]) -> tuple[float, tuple[float, ...]]:
    return candidate


def _search(request: dict[str, Any], facts: dict[str, Any]) -> tuple[tuple[float, ...], float, list[dict[str, Any]], list[dict[str, Any]]]:
    dimension = len(request["parameters"])
    levels = request["search"]["grid_levels_per_parameter"]
    trace: list[dict[str, Any]] = []
    grid: list[tuple[float, tuple[float, ...]]] = []
    evaluation = 0
    for coordinates in itertools.product(range(levels), repeat=dimension):
        normalized = tuple(value / (levels - 1) for value in coordinates)
        objective, _, _ = _objective(request, normalized, facts)
        evaluation += 1
        trace.append({"phase": "grid", "start": 0, "iteration": 0, "evaluation": evaluation, "normalized": normalized, "objective": objective})
        grid.append((objective, normalized))
    starts = sorted(grid, key=_candidate_key)[: request["search"]["local_start_count"]]
    solutions: list[dict[str, Any]] = []
    minimum_step = request["search"]["minimum_normalized_step"]
    maximum_iterations = request["search"]["maximum_iterations_per_start"]
    for start_index, (start_objective, start_point) in enumerate(starts, start=1):
        current = start_point
        current_objective = start_objective
        step = 1.0 / (levels - 1)
        iteration = 0
        while iteration < maximum_iterations and step >= minimum_step:
            iteration += 1
            candidates: list[tuple[float, tuple[float, ...]]] = [(current_objective, current)]
            seen = {current}
            for parameter_index in range(dimension):
                for direction in (-1.0, 1.0):
                    neighbor = list(current)
                    neighbor[parameter_index] = min(1.0, max(0.0, neighbor[parameter_index] + direction * step))
                    point = tuple(neighbor)
                    if point in seen:
                        continue
                    seen.add(point)
                    objective, _, _ = _objective(request, point, facts)
                    evaluation += 1
                    trace.append({"phase": "local", "start": start_index, "iteration": iteration, "evaluation": evaluation, "normalized": point, "objective": objective})
                    candidates.append((objective, point))
            best_objective, best_point = min(candidates, key=_candidate_key)
            if best_point == current:
                step /= 2.0
            else:
                current, current_objective = best_point, best_objective
        values = _actual_values(request, current)
        solutions.append({
            "start_index": start_index,
            "start_normalized_parameters": list(start_point),
            "start_objective": start_objective,
            "final_normalized_parameters": list(current),
            "final_parameters": values,
            "final_objective": current_objective,
            "iterations": iteration,
            "final_step": step,
            "converged": step < minimum_step,
        })
    best_solution = min(solutions, key=lambda item: (item["final_objective"], tuple(item["final_normalized_parameters"])))
    return tuple(best_solution["final_normalized_parameters"]), float(best_solution["final_objective"]), solutions, trace


def _jacobi_eigenvalues(matrix: list[list[float]]) -> list[float]:
    values = [row[:] for row in matrix]
    size = len(values)
    for _ in range(100 * max(1, size * size)):
        if size < 2:
            break
        row, column = max(((r, c) for r in range(size) for c in range(r + 1, size)), key=lambda pair: abs(values[pair[0]][pair[1]]))
        if abs(values[row][column]) <= 1e-15:
            break
        angle = 0.5 * math.atan2(2.0 * values[row][column], values[column][column] - values[row][row])
        sine, cosine = math.sin(angle), math.cos(angle)
        for index in range(size):
            if index in {row, column}:
                continue
            left, right = values[index][row], values[index][column]
            values[index][row] = values[row][index] = cosine * left - sine * right
            values[index][column] = values[column][index] = sine * left + cosine * right
        a, b, d = values[row][row], values[row][column], values[column][column]
        values[row][row] = cosine * cosine * a - 2 * sine * cosine * b + sine * sine * d
        values[column][column] = sine * sine * a + 2 * sine * cosine * b + cosine * cosine * d
        values[row][column] = values[column][row] = 0.0
    return sorted((max(0.0, values[index][index]) for index in range(size)), reverse=True)


def _identifiability(request: dict[str, Any], best: tuple[float, ...], facts: dict[str, Any]) -> dict[str, Any]:
    training = [target for target in request["targets"] if target["role"] == "calibration"]
    step = request["identifiability"]["normalized_derivative_step"]
    columns: list[list[float]] = []
    for parameter_index in range(len(best)):
        lower = list(best)
        upper = list(best)
        lower[parameter_index] = max(0.0, lower[parameter_index] - step)
        upper[parameter_index] = min(1.0, upper[parameter_index] + step)
        denominator = upper[parameter_index] - lower[parameter_index]
        _, low_predictions = _predictions(request, tuple(lower), facts)
        _, high_predictions = _predictions(request, tuple(upper), facts)
        columns.append([(high_predictions[target["id"]] - low_predictions[target["id"]]) / denominator / float(target["standard_error"]) for target in training])
    size = len(best)
    information = [[math.fsum(columns[left][row] * columns[right][row] for row in range(len(training))) for right in range(size)] for left in range(size)]
    eigenvalues = _jacobi_eigenvalues(information)
    maximum = eigenvalues[0] if eigenvalues else 0.0
    tolerance = request["identifiability"]["relative_rank_tolerance"]
    rank = sum(value > maximum * tolerance * tolerance for value in eigenvalues) if maximum > 0 else 0
    positive = [value for value in eigenvalues if value > maximum * tolerance * tolerance]
    condition = math.sqrt(maximum / min(positive)) if positive else None
    return {
        "method": request["identifiability"]["method"],
        "scope": "local_scaled_training_target_jacobian_only",
        "numerical_rank": rank,
        "parameter_count": size,
        "full_rank": rank == size,
        "information_eigenvalues": eigenvalues,
        "condition_index_identifiable_subspace": condition,
        "relative_rank_tolerance": tolerance,
        "automatic_acceptance_thresholds": "none",
    }


def execute_calibration(request: dict[str, Any], facts: dict[str, Any]) -> dict[str, Any]:
    best, objective, solutions, trace = _search(request, facts)
    values, predictions = _predictions(request, best, facts)
    target_fit = []
    validation_residuals: list[float] = []
    for target in request["targets"]:
        residual = predictions[target["id"]] - float(target["observed"])
        target_fit.append({
            "id": target["id"], "role": target["role"], "cycle": target["cycle"], "state": target["state"],
            "observed": float(target["observed"]), "predicted": predictions[target["id"]], "residual": residual,
            "standard_error": float(target["standard_error"]), "standardized_residual": residual / float(target["standard_error"]),
        })
        if target["role"] == "validation":
            validation_residuals.append(residual)
    identifiability = _identifiability(request, best, facts)
    warnings: list[str] = []
    if not identifiability["full_rank"]:
        warnings.append("Local identifiability is incomplete at the selected fit; alternative parameter sets must not be silently resolved or adopted.")
    if any(not solution["converged"] for solution in solutions):
        warnings.append("At least one local search reached its iteration cap before the fixed step stopping rule.")
    return {
        "best_fit": {"objective": objective, "normalized_parameters": list(best), "parameters": values},
        "target_fit": target_fit,
        "search": {
            "method": request["search"]["method"],
            "grid_evaluations": request["search"]["grid_levels_per_parameter"] ** len(request["parameters"]),
            "total_evaluations": len(trace),
            "training_target_count": sum(target["role"] == "calibration" for target in request["targets"]),
            "validation_target_count": sum(target["role"] == "validation" for target in request["targets"]),
            "local_solutions": solutions,
            "stopping_rule": {"minimum_normalized_step": request["search"]["minimum_normalized_step"], "maximum_iterations_per_start": request["search"]["maximum_iterations_per_start"]},
            "automatic_fit_thresholds": "none",
        },
        "identifiability": identifiability,
        "validation": {
            "held_out_target_count": len(validation_residuals),
            "rmse": math.sqrt(math.fsum(value * value for value in validation_residuals) / len(validation_residuals)),
            "maximum_absolute_residual": max(abs(value) for value in validation_residuals),
            "automatic_acceptance_thresholds": "none",
        },
        "warnings": warnings,
        "_search_trace": trace,
    }


def canonical_trace_bytes(trace: list[dict[str, Any]], parameter_ids: list[str]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["phase", "start", "iteration", "evaluation", *[f"normalized_{value}" for value in parameter_ids], "objective"])
    for row in trace:
        writer.writerow([row["phase"], row["start"], row["iteration"], row["evaluation"], *[format(value, ".17g") for value in row["normalized"]], format(row["objective"], ".17g")])
    return output.getvalue().encode("utf-8")


def current_python_identity() -> dict[str, str]:
    executable = Path(sys.executable).resolve()
    return {"python_version": sys.version.split()[0], "python_executable_sha256": digest(executable.read_bytes())}


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
    if result.get("schema_version") != RESULT_SCHEMA_VERSION or not safe_id(result.get("calibration_id")):
        errors.append("result schema_version or calibration_id is invalid")
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
            if request.get("calibration_id") != result.get("calibration_id"):
                errors.append("result calibration_id does not match request")
    expected_evidence = request.get("evidence_synthesis", {}) if request else {}
    if result.get("evidence_synthesis") != {"path": expected_evidence.get("path"), "sha256": expected_evidence.get("sha256")}:
        errors.append("result evidence_synthesis binding does not match request")
    runtime = result.get("runtime")
    if not exact(runtime, {"evaluator", "python_version", "python_executable_sha256", "evaluator_source"}):
        errors.append("result runtime fields are invalid")
    else:
        if runtime.get("evaluator") != EVALUATOR or {"python_version": runtime.get("python_version"), "python_executable_sha256": runtime.get("python_executable_sha256")} != current_python_identity():
            errors.append("result runtime identity does not match replay runtime")
        evaluator = runtime.get("evaluator_source")
        evaluator_path = resolve_file(workspace, evaluator.get("path") if isinstance(evaluator, dict) else None)
        if not exact(evaluator, {"path", "sha256"}) or evaluator_path is None or digest(evaluator_path.read_bytes()) != evaluator.get("sha256") or evaluator_path.read_bytes() != Path(__file__).read_bytes():
            errors.append("result evaluator source is stale, unsafe, or not current")
    trace_binding = result.get("search", {}).get("trace") if isinstance(result.get("search"), dict) else None
    trace_path = resolve_file(workspace, trace_binding.get("path") if isinstance(trace_binding, dict) else None)
    if not exact(trace_binding, {"path", "sha256"}) or trace_path is None or SHA256.fullmatch(str(trace_binding.get("sha256", "") if isinstance(trace_binding, dict) else "")) is None:
        errors.append("result search trace binding is invalid")
    elif digest(trace_path.read_bytes()) != trace_binding["sha256"]:
        errors.append("result search trace sha256 does not match current bytes")
    if not errors and request and facts:
        replay = execute_calibration(request, facts)
        expected_trace = canonical_trace_bytes(replay.pop("_search_trace"), [parameter["id"] for parameter in request["parameters"]])
        if trace_path is None or trace_path.read_bytes() != expected_trace:
            errors.append("search trace bytes do not reproduce the complete deterministic replay")
        _deep_close(result.get("best_fit"), replay["best_fit"], "best_fit", errors)
        _deep_close(result.get("target_fit"), replay["target_fit"], "target_fit", errors)
        expected_search = {**replay["search"], "trace": trace_binding}
        _deep_close(result.get("search"), expected_search, "search", errors)
        _deep_close(result.get("identifiability"), replay["identifiability"], "identifiability", errors)
        _deep_close(result.get("validation"), replay["validation"], "validation", errors)
        if result.get("warnings") != replay["warnings"]:
            errors.append("warnings differ from deterministic replay")
    expected_method = {
        "family": "bounded_continuous_time_cohort_natural_history_point_calibration",
        "training_loss": "sum_squared_standardized_residuals",
        "target_covariance": "not_modeled",
        "parameter_uncertainty": "not_propagated",
    }
    if result.get("method") != expected_method:
        errors.append("result method scope is invalid")
    if result.get("cross_implementation") != {
        "portable_replay": "complete_search_and_diagnostics",
        "native_replay": "selected_point_model_and_local_identifiability_only",
    }:
        errors.append("result cross_implementation scope is invalid")
    if result.get("limitations") != request.get("limitations"):
        errors.append("result limitations must exactly preserve request limitations")
    if result.get("human_gate") != {"status": "awaiting_method_review", "required_checks": REQUIRED_REVIEW_CHECKS, "automatic_model_input_update": False}:
        errors.append("result human_gate is invalid")
    if result.get("status") != "awaiting_method_review":
        errors.append("result status is invalid")
    complete = not errors
    return {
        "complete": complete,
        "reviewable": complete,
        "result_sha256": digest(result_raw),
        "calibration_id": result.get("calibration_id") if safe_id(result.get("calibration_id")) else None,
        "errors": errors,
    }


def parse_args(description: str) -> tuple[Path, Path]:
    import argparse
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    path = args.request if args.request is not None else args.result
    if path is None:
        parser.error("one of --request or --result is required")
    return args.workspace.expanduser().resolve(), path
