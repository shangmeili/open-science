#!/usr/bin/env python3
"""Dependency-free anchored MAIC contract, deterministic engine, and replay audit."""

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


REQUEST_SCHEMA_VERSION = "0.1.0"
AGGREGATE_SCHEMA_VERSION = "0.1.0"
RESULT_SCHEMA_VERSION = "0.1.0"
EVALUATOR = "ai4heor-anchored-maic@0.1.0"
RNG_ALGORITHM = "pcg32-xsh-rr"
RNG_VERSION = "1"
Z_95 = 1.959963984540054
TOLERANCE = 1e-9
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_SOURCE_BYTES = 64 * 1024 * 1024
MAX_SOURCE_ROWS = 5_000
MAX_MODIFIERS = 8
SAFE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SAFE_SUBJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ISO_UTC = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

EFFECTS = {
    "log_odds_ratio": "logit",
    "mean_difference": "identity",
}
REQUIRED_REVIEW_CHECKS = [
    "question_estimand_target_common_comparator",
    "randomized_connected_evidence_provenance",
    "effect_modifier_rationale_completeness",
    "ipd_integrity_privacy_missingness",
    "target_moments_overlap",
    "calibration_balance_weights_ess",
    "bootstrap_precision_failures",
    "residual_bias_transportability_downstream",
]
REQUEST_FIELDS = {
    "schema_version",
    "execution_id",
    "status",
    "method",
    "evidence_synthesis",
    "source_data",
    "aggregate_evidence",
    "effect_modifiers",
    "effect",
    "weighting",
    "uncertainty",
    "output",
    "study_provenance",
    "human_authorization",
    "limitations",
    "human_gate",
}
AGGREGATE_FIELDS = {
    "schema_version",
    "trial_id",
    "target_population",
    "common_comparator_id",
    "aggregate_treatment_id",
    "outcome",
    "timepoint",
    "effect",
    "target_moments",
    "source_ids",
    "limitations",
}
RESULT_FIELDS = {
    "schema_version",
    "execution_id",
    "status",
    "request",
    "source_data",
    "aggregate_evidence",
    "evidence_synthesis",
    "runtime",
    "method",
    "calibration",
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
    outcome: float
    modifiers: tuple[float, ...]


class Pcg32:
    """Fixed PCG-XSH-RR stream shared with the deterministic HEOR engine."""

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


def _quantile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = probability * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def _mean(values: list[float]) -> float:
    return math.fsum(values) / len(values)


def _sample_variance(values: list[float]) -> float:
    if len(values) < 2:
        raise ValueError("sample variance requires at least two values")
    center = _mean(values)
    return math.fsum((value - center) ** 2 for value in values) / (len(values) - 1)


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    augmented = [list(row) + [vector[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-14:
            raise ValueError("calibration Hessian is singular")
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
        raise ValueError("calibration linear solve produced a non-finite value")
    return result


def _normalized_weights(centered: list[tuple[float, ...]], alpha: list[float]) -> list[float]:
    logits = [math.fsum(a * z for a, z in zip(alpha, row)) for row in centered]
    if not all(math.isfinite(value) for value in logits):
        raise ValueError("calibration logits are non-finite")
    shift = max(logits)
    raw = [math.exp(value - shift) for value in logits]
    total = math.fsum(raw)
    if not math.isfinite(total) or total <= 0:
        raise ValueError("calibration weights are numerically invalid")
    scale = len(raw) / total
    weights = [value * scale for value in raw]
    if not all(math.isfinite(value) and value > 0 for value in weights):
        raise ValueError("calibration weights must be finite and positive")
    return weights


def _gradient(centered: list[tuple[float, ...]], weights: list[float]) -> list[float]:
    total = math.fsum(weights)
    return [math.fsum(weight * row[index] for weight, row in zip(weights, centered)) / total for index in range(len(centered[0]))]


def calibrate(
    rows: list[SourceRow],
    targets: list[float],
    tolerance: float,
    max_iterations: int,
) -> dict[str, Any]:
    centered = [tuple(value - target for value, target in zip(row.modifiers, targets)) for row in rows]
    alpha = [0.0] * len(targets)
    converged_at = 0
    for iteration in range(max_iterations + 1):
        weights = _normalized_weights(centered, alpha)
        gradient = _gradient(centered, weights)
        norm = max(abs(value) for value in gradient)
        if norm <= tolerance:
            converged_at = iteration
            break
        if iteration == max_iterations:
            raise ValueError("calibration did not converge within max_iterations")
        total = math.fsum(weights)
        hessian = [
            [
                math.fsum(weight * row[left] * row[right] for weight, row in zip(weights, centered)) / total
                - gradient[left] * gradient[right]
                for right in range(len(targets))
            ]
            for left in range(len(targets))
        ]
        delta = _solve(hessian, gradient)
        accepted = False
        step = 1.0
        for _ in range(40):
            candidate = [value - step * change for value, change in zip(alpha, delta)]
            candidate_weights = _normalized_weights(centered, candidate)
            candidate_gradient = _gradient(centered, candidate_weights)
            if max(abs(value) for value in candidate_gradient) < norm:
                alpha = candidate
                accepted = True
                break
            step *= 0.5
        if not accepted:
            raise ValueError("calibration line search could not reduce residual imbalance")
    else:  # pragma: no cover - loop always exits through break or exception
        raise ValueError("calibration failed")

    weights = _normalized_weights(centered, alpha)
    weighted_means = [
        math.fsum(weight * row.modifiers[index] for weight, row in zip(weights, rows)) / math.fsum(weights)
        for index in range(len(targets))
    ]
    errors = [value - target for value, target in zip(weighted_means, targets)]
    if max(abs(value) for value in errors) > max(tolerance * 10, 1e-9):
        raise ValueError("calibration residual balance exceeds tolerance")
    return {
        "alpha": alpha,
        "weights": weights,
        "iterations": converged_at,
        "weighted_means": weighted_means,
        "balance_errors": errors,
    }


def _ess(weights: list[float]) -> float:
    denominator = math.fsum(value * value for value in weights)
    return math.fsum(weights) ** 2 / denominator


def _coefficient_of_variation(weights: list[float]) -> float:
    mean = _mean(weights)
    variance = math.fsum((value - mean) ** 2 for value in weights) / len(weights)
    return math.sqrt(variance) / mean


def effect_estimate(
    rows: list[SourceRow],
    weights: list[float],
    common: str,
    treatment: str,
    measure: str,
) -> float:
    def arm_mean(arm: str) -> float:
        arm_values = [(row.outcome, weight) for row, weight in zip(rows, weights) if row.treatment == arm]
        total = math.fsum(weight for _, weight in arm_values)
        if total <= 0:
            raise ValueError(f"weighted arm {arm} has no mass")
        return math.fsum(value * weight for value, weight in arm_values) / total

    common_mean = arm_mean(common)
    treatment_mean = arm_mean(treatment)
    if measure == "mean_difference":
        estimate = treatment_mean - common_mean
    elif measure == "log_odds_ratio":
        if not 0 < common_mean < 1 or not 0 < treatment_mean < 1:
            raise ValueError("weighted binary arm risks must remain strictly between zero and one")
        estimate = math.log(treatment_mean / (1 - treatment_mean)) - math.log(common_mean / (1 - common_mean))
    else:  # pragma: no cover - request validation owns this boundary
        raise ValueError(f"unsupported effect measure: {measure}")
    if not math.isfinite(estimate) or abs(estimate) > 100:
        raise ValueError("effect estimate is non-finite or outside the numeric safety bound")
    return estimate


def natural_effect(measure: str, value: float) -> float:
    return math.exp(value) if measure == "log_odds_ratio" else value


def bootstrap_samples(rows: list[SourceRow], common: str, treatment: str, iterations: int, seed: int) -> Iterator[list[SourceRow]]:
    positions = {
        common: [index for index, row in enumerate(rows) if row.treatment == common],
        treatment: [index for index, row in enumerate(rows) if row.treatment == treatment],
    }
    rng = Pcg32(seed)
    for _ in range(iterations):
        sample: list[SourceRow] = []
        for arm in (common, treatment):
            arm_positions = positions[arm]
            sample.extend(rows[arm_positions[rng.bounded(len(arm_positions))]] for _ in arm_positions)
        yield sample


def inspect_source(
    path: Path,
    expected_columns: list[str],
    modifier_columns: list[str],
    common: str,
    treatment: str,
    measure: str,
) -> tuple[list[SourceRow], dict[str, Any], list[str]]:
    errors: list[str] = []
    rows: list[SourceRow] = []
    if path.stat().st_size > MAX_SOURCE_BYTES:
        return rows, {}, ["source_data exceeds 64 MB"]
    subjects: set[str] = set()
    counts = {common: 0, treatment: 0}
    binary_counts = {common: {0: 0, 1: 0}, treatment: {0: 0, 1: 0}}
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
                if len(raw) != len(expected_columns) or any(not value or value != value.strip() for value in raw):
                    errors.append(f"source_data row {line_number} contains an invalid, blank, or padded value")
                    continue
                subject_id, arm, outcome_raw, *modifier_raw = raw
                if SAFE_SUBJECT.fullmatch(subject_id) is None:
                    errors.append(f"source_data row {line_number} subject_id is not a safe pseudonym")
                elif subject_id in subjects:
                    errors.append(f"source_data row {line_number} repeats subject_id")
                subjects.add(subject_id)
                if arm not in counts:
                    errors.append(f"source_data row {line_number} treatment is outside the declared randomized arms")
                    continue
                try:
                    outcome = float(outcome_raw)
                    modifiers = tuple(float(value) for value in modifier_raw)
                except ValueError:
                    errors.append(f"source_data row {line_number} outcome and modifiers must be numeric")
                    continue
                if not math.isfinite(outcome) or abs(outcome) > 1e12:
                    errors.append(f"source_data row {line_number} outcome is non-finite or outside the safety bound")
                if len(modifiers) != len(modifier_columns) or not all(math.isfinite(value) and abs(value) <= 1e12 for value in modifiers):
                    errors.append(f"source_data row {line_number} modifier values are invalid")
                    continue
                if measure == "log_odds_ratio" and outcome not in {0.0, 1.0}:
                    errors.append(f"source_data row {line_number} binary outcome must be exactly 0 or 1")
                    continue
                row = SourceRow(subject_id, arm, outcome, modifiers)
                rows.append(row)
                counts[arm] += 1
                if measure == "log_odds_ratio":
                    binary_counts[arm][int(outcome)] += 1
                if len(rows) > MAX_SOURCE_ROWS:
                    errors.append(f"source_data exceeds {MAX_SOURCE_ROWS} rows")
                    break
    except (OSError, UnicodeError, csv.Error) as error:
        return rows, {}, [f"source_data CSV cannot be read: {error}"]
    for arm, count in counts.items():
        if count < 20:
            errors.append(f"source_data randomized arm {arm} must contain at least 20 rows")
        if measure == "log_odds_ratio" and (binary_counts[arm][0] < 2 or binary_counts[arm][1] < 2):
            errors.append(f"source_data randomized arm {arm} must contain at least two events and two non-events")
    if len(rows) != len(subjects):
        errors.append("source_data subject identifiers must be unique")
    return rows, {"row_count": len(rows), "arm_counts": counts, "binary_counts": binary_counts}, errors


def _validate_aggregate(value: Any, request: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if not exact(value, AGGREGATE_FIELDS):
        return {}, ["aggregate_evidence JSON fields do not match schema 0.1.0"]
    method = request["method"]
    effect = request["effect"]
    if value.get("schema_version") != AGGREGATE_SCHEMA_VERSION:
        errors.append("aggregate_evidence schema_version must be 0.1.0")
    expected = {
        "trial_id": method.get("aggregate_trial_id"),
        "target_population": method.get("target_population"),
        "common_comparator_id": method.get("common_comparator_id"),
        "aggregate_treatment_id": method.get("aggregate_treatment_id"),
        "outcome": method.get("outcome"),
        "timepoint": method.get("timepoint"),
    }
    for field, expected_value in expected.items():
        if value.get(field) != expected_value:
            errors.append(f"aggregate_evidence {field} does not match the request")
    aggregate_effect = value.get("effect")
    if not exact(aggregate_effect, {"measure", "scale", "estimate", "se"}):
        errors.append("aggregate_evidence effect fields are invalid")
    else:
        if aggregate_effect.get("measure") != effect.get("measure") or aggregate_effect.get("scale") != effect.get("scale"):
            errors.append("aggregate_evidence effect scale does not match the request")
        if not finite(aggregate_effect.get("estimate")) or abs(float(aggregate_effect["estimate"])) > 100:
            errors.append("aggregate_evidence effect estimate is invalid")
        if not finite(aggregate_effect.get("se")) or not 0 < float(aggregate_effect["se"]) <= 100:
            errors.append("aggregate_evidence effect se must be finite, positive, and bounded")
    moments = value.get("target_moments")
    modifiers = request.get("effect_modifiers")
    if not isinstance(moments, list) or not isinstance(modifiers, list) or len(moments) != len(modifiers):
        errors.append("aggregate_evidence target_moments must cover every declared effect modifier")
    else:
        for index, (moment, modifier) in enumerate(zip(moments, modifiers)):
            if not exact(moment, {"id", "mean"}) or moment.get("id") != modifier.get("id") or not finite(moment.get("mean")):
                errors.append(f"aggregate_evidence target_moments[{index}] is invalid or out of order")
            elif abs(float(moment["mean"])) > 1e12:
                errors.append(f"aggregate_evidence target_moments[{index}].mean is outside the safety bound")
    source_ids = value.get("source_ids")
    included = request.get("evidence_synthesis", {}).get("included_record_ids", [])
    if not isinstance(source_ids, list) or not source_ids or any(not safe_id(item) for item in source_ids):
        errors.append("aggregate_evidence source_ids must be non-empty safe IDs")
    elif any(item not in included for item in source_ids):
        errors.append("aggregate_evidence source_ids must belong to the bound evidence synthesis")
    if not isinstance(value.get("limitations"), list) or not value["limitations"] or any(not text(item) for item in value["limitations"]):
        errors.append("aggregate_evidence limitations must be non-empty text")
    return value if not errors else {}, errors


def validate_request(request: Any, workspace: Path) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    if not exact(request, REQUEST_FIELDS):
        return ["request fields do not match anchored MAIC schema 0.1.0"], {}
    if request.get("schema_version") != REQUEST_SCHEMA_VERSION:
        errors.append("schema_version must be 0.1.0")
    if not safe_id(request.get("execution_id")):
        errors.append("execution_id must be a safe lowercase identifier")
    if request.get("status") != "ready_for_execution":
        errors.append("status must be ready_for_execution")

    method = request.get("method")
    method_fields = {
        "family", "network", "trial_relationship", "ipd_trial_id", "aggregate_trial_id", "common_comparator_id",
        "ipd_treatment_id", "aggregate_treatment_id", "target_population", "outcome", "timepoint", "estimand",
    }
    if not exact(method, method_fields):
        errors.append("method fields are invalid")
        method = {}
    else:
        if method.get("family") != "anchored_maic" or method.get("network") != "connected_two_trial_common_comparator":
            errors.append("only connected two-trial anchored_maic is supported")
        if method.get("trial_relationship") != "independent_parallel_randomized_trials":
            errors.append("method requires two independent parallel randomized trials")
        ids = [method.get(field) for field in ("ipd_trial_id", "aggregate_trial_id", "common_comparator_id", "ipd_treatment_id", "aggregate_treatment_id")]
        if any(not safe_id(value) for value in ids) or len(set(ids[:2])) != 2 or len(set(ids[2:])) != 3:
            errors.append("method trial and treatment IDs must be safe and distinct in their roles")
        for field in ("target_population", "outcome", "timepoint", "estimand"):
            if not text(method.get(field)):
                errors.append(f"method.{field} must be non-empty text")

    evidence = request.get("evidence_synthesis")
    if not exact(evidence, {"path", "sha256", "included_record_ids"}):
        errors.append("evidence_synthesis fields are invalid")
        evidence = {}
    evidence_path = resolve_file(workspace, evidence.get("path"))
    if evidence_path is None or SHA256.fullmatch(str(evidence.get("sha256", ""))) is None:
        errors.append("evidence_synthesis path or sha256 is invalid")
    elif digest(evidence_path.read_bytes()) != evidence["sha256"]:
        errors.append("evidence_synthesis sha256 does not match current bytes")
    included_ids = evidence.get("included_record_ids")
    if not isinstance(included_ids, list) or len(included_ids) < 2 or len(set(included_ids)) != len(included_ids) or any(not safe_id(item) for item in included_ids):
        errors.append("evidence_synthesis included_record_ids must be unique safe IDs")

    effect = request.get("effect")
    if not exact(effect, {"measure", "scale", "confidence_level", "favorable_direction"}):
        errors.append("effect fields are invalid")
        effect = {}
    else:
        measure = effect.get("measure")
        if measure not in EFFECTS or effect.get("scale") != EFFECTS.get(measure):
            errors.append("effect measure and scale are unsupported or mismatched")
        if effect.get("confidence_level") != 0.95:
            errors.append("confidence_level must be exactly 0.95")
        if effect.get("favorable_direction") not in {"lower", "higher"}:
            errors.append("favorable_direction must be lower or higher")

    modifiers = request.get("effect_modifiers")
    if not isinstance(modifiers, list) or not 1 <= len(modifiers) <= MAX_MODIFIERS:
        errors.append(f"effect_modifiers must contain 1 to {MAX_MODIFIERS} entries")
        modifiers = []
    modifier_ids: list[str] = []
    modifier_columns: list[str] = []
    for index, modifier in enumerate(modifiers):
        if not exact(modifier, {"id", "column", "label", "rationale", "evidence_record_ids"}):
            errors.append(f"effect_modifiers[{index}] fields are invalid")
            continue
        modifier_ids.append(str(modifier.get("id")))
        modifier_columns.append(str(modifier.get("column")))
        if not safe_id(modifier.get("id")) or not safe_id(modifier.get("column")):
            errors.append(f"effect_modifiers[{index}] id and column must be safe")
        if modifier.get("column") in {"subject_id", "treatment", "outcome"}:
            errors.append(f"effect_modifiers[{index}] column is reserved")
        if not text(modifier.get("label")) or not text(modifier.get("rationale")):
            errors.append(f"effect_modifiers[{index}] label and rationale are required")
        record_ids = modifier.get("evidence_record_ids")
        if not isinstance(record_ids, list) or not record_ids or any(not safe_id(item) or item not in (included_ids or []) for item in record_ids):
            errors.append(f"effect_modifiers[{index}] evidence_record_ids must be bound evidence IDs")
    if len(set(modifier_ids)) != len(modifier_ids) or len(set(modifier_columns)) != len(modifier_columns):
        errors.append("effect modifier IDs and columns must be unique")

    source = request.get("source_data")
    source_fields = {
        "classification", "execution_boundary", "format", "path", "sha256", "columns", "row_count",
        "contains_direct_identifiers", "missing_policy", "treatment_assignment",
    }
    if not exact(source, source_fields):
        errors.append("source_data fields are invalid")
        source = {}
    else:
        if source.get("classification") not in {"public", "non_sensitive", "restricted"}:
            errors.append("source_data classification must be explicit and executable locally")
        if source.get("execution_boundary") != "local_only" or source.get("format") != "ipd_csv":
            errors.append("source_data must be local_only ipd_csv")
        if source.get("contains_direct_identifiers") is not False or source.get("missing_policy") != "reject":
            errors.append("source_data must reject missing values and direct identifiers")
        if source.get("treatment_assignment") != "randomized_parallel_two_arm":
            errors.append("source_data must come from a randomized parallel two-arm trial")
        expected_columns = ["subject_id", "treatment", "outcome", *modifier_columns]
        if source.get("columns") != expected_columns:
            errors.append("source_data.columns must be the fixed base columns followed by effect modifiers in request order")
        if isinstance(source.get("row_count"), bool) or not isinstance(source.get("row_count"), int) or not 40 <= source.get("row_count", 0) <= MAX_SOURCE_ROWS:
            errors.append("source_data row_count must be between 40 and 5,000")
    source_path = resolve_file(workspace, source.get("path"))
    if source_path is None or SHA256.fullmatch(str(source.get("sha256", ""))) is None:
        errors.append("source_data path or sha256 is invalid")
        rows: list[SourceRow] = []
        source_facts: dict[str, Any] = {}
    elif digest(source_path.read_bytes()) != source["sha256"]:
        errors.append("source_data sha256 does not match current bytes")
        rows, source_facts = [], {}
    else:
        rows, source_facts, source_errors = inspect_source(
            source_path,
            source.get("columns", []),
            modifier_columns,
            str(method.get("common_comparator_id", "")),
            str(method.get("ipd_treatment_id", "")),
            str(effect.get("measure", "")),
        )
        errors.extend(source_errors)
        if source_facts.get("row_count") != source.get("row_count"):
            errors.append("source_data row_count does not match current CSV bytes")

    aggregate_binding = request.get("aggregate_evidence")
    if not exact(aggregate_binding, {"path", "sha256"}):
        errors.append("aggregate_evidence binding fields are invalid")
        aggregate_binding = {}
    aggregate_path = resolve_file(workspace, aggregate_binding.get("path"))
    aggregate: dict[str, Any] = {}
    if aggregate_path is None or SHA256.fullmatch(str(aggregate_binding.get("sha256", ""))) is None:
        errors.append("aggregate_evidence path or sha256 is invalid")
    else:
        try:
            aggregate, aggregate_raw = load_json(aggregate_path)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(f"aggregate_evidence cannot be read: {error}")
        else:
            if digest(aggregate_raw) != aggregate_binding["sha256"]:
                errors.append("aggregate_evidence sha256 does not match current bytes")
            _, aggregate_errors = _validate_aggregate(aggregate, request)
            errors.extend(aggregate_errors)

    weighting = request.get("weighting")
    weighting_expected = {
        "method": "method_of_moments_exponential_tilting", "balance_moments": "means", "normalization": "mean_one",
        "weight_cap": "none", "trimming": "none",
    }
    if not exact(weighting, {"method", "balance_moments", "normalization", "convergence_tolerance", "max_iterations", "weight_cap", "trimming"}):
        errors.append("weighting fields are invalid")
        weighting = {}
    else:
        for field, expected_value in weighting_expected.items():
            if weighting.get(field) != expected_value:
                errors.append(f"weighting.{field} must be {expected_value}")
        if weighting.get("convergence_tolerance") != 1e-10 or weighting.get("max_iterations") != 200:
            errors.append("weighting numerical contract must use tolerance 1e-10 and 200 iterations")

    uncertainty = request.get("uncertainty")
    if not exact(uncertainty, {"method", "iterations", "seed", "prng", "failure_policy"}):
        errors.append("uncertainty fields are invalid")
        uncertainty = {}
    else:
        if uncertainty.get("method") != "stratified_nonparametric_bootstrap_refit" or uncertainty.get("failure_policy") != "retain_and_block_review":
            errors.append("uncertainty must use the fixed stratified bootstrap and retain failures")
        iterations = uncertainty.get("iterations")
        if isinstance(iterations, bool) or not isinstance(iterations, int) or not 1_000 <= iterations <= 5_000:
            errors.append("uncertainty iterations must be between 1,000 and 5,000")
        seed = uncertainty.get("seed")
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed < 2**63:
            errors.append("uncertainty seed must be an integer in [0, 2^63)")
        if uncertainty.get("prng") != {"algorithm": RNG_ALGORITHM, "version": RNG_VERSION}:
            errors.append("uncertainty prng must be pcg32-xsh-rr version 1")

    output = request.get("output")
    expected_output = f"heor/population-adjusted-comparison-runs/{request.get('execution_id', '')}"
    if not exact(output, {"directory"}) or output.get("directory") != expected_output or resolve_output_directory(workspace, output.get("directory")) is None:
        errors.append("output.directory must be the fixed safe execution path")

    provenance = request.get("study_provenance")
    expected_trials = [method.get("ipd_trial_id"), method.get("aggregate_trial_id")]
    if not isinstance(provenance, list) or len(provenance) != 2:
        errors.append("study_provenance must contain the two trials in method order")
    else:
        for index, (item, trial_id) in enumerate(zip(provenance, expected_trials)):
            if not exact(item, {"trial_id", "evidence_record_ids", "risk_of_bias"}) or item.get("trial_id") != trial_id:
                errors.append(f"study_provenance[{index}] fields or trial_id are invalid")
                continue
            record_ids = item.get("evidence_record_ids")
            if not isinstance(record_ids, list) or not record_ids or any(not safe_id(value) or value not in (included_ids or []) for value in record_ids):
                errors.append(f"study_provenance[{index}] evidence records are invalid")
            if item.get("risk_of_bias") not in {"low", "some_concerns", "high", "awaiting_human_review"}:
                errors.append(f"study_provenance[{index}] risk_of_bias is invalid")

    authorization = request.get("human_authorization")
    if not exact(authorization, {"actor", "authorized_at", "scope"}) or not text(authorization.get("actor")) or ISO_UTC.fullmatch(str(authorization.get("authorized_at", ""))) is None or authorization.get("scope") != "execute_local_anchored_maic":
        errors.append("human_authorization must bind an actor, UTC time, and exact local execution scope")
    if not isinstance(request.get("limitations"), list) or not request["limitations"] or any(not text(value) for value in request["limitations"]):
        errors.append("limitations must be non-empty text")
    gate = request.get("human_gate")
    if not exact(gate, {"status", "required_checks"}) or gate.get("status") != "awaiting_method_review" or gate.get("required_checks") != REQUIRED_REVIEW_CHECKS:
        errors.append("human_gate must contain the exact eight-check awaiting_method_review contract")

    targets = [float(item["mean"]) for item in aggregate.get("target_moments", [])] if aggregate and not errors else []
    calibration: dict[str, Any] = {}
    if not errors:
        try:
            calibration = calibrate(rows, targets, 1e-10, 200)
            effect_estimate(rows, calibration["weights"], method["common_comparator_id"], method["ipd_treatment_id"], effect["measure"])
        except ValueError as error:
            errors.append(f"anchored MAIC preflight failed: {error}")
    facts = {
        "rows": rows,
        "source": source_facts,
        "aggregate": aggregate,
        "targets": targets,
        "modifier_ids": modifier_ids,
        "modifier_columns": modifier_columns,
        "preflight_calibration": calibration,
        "evidence_path": evidence_path,
        "source_path": source_path,
        "aggregate_path": aggregate_path,
    }
    return errors, facts


def calibration_summary(request: dict[str, Any], facts: dict[str, Any], calibration: dict[str, Any]) -> dict[str, Any]:
    rows: list[SourceRow] = facts["rows"]
    weights: list[float] = calibration["weights"]
    targets: list[float] = facts["targets"]
    common = request["method"]["common_comparator_id"]
    treatment = request["method"]["ipd_treatment_id"]
    unweighted_means = [_mean([row.modifiers[index] for row in rows]) for index in range(len(targets))]
    arm_weights = {
        arm: [weight for row, weight in zip(rows, weights) if row.treatment == arm]
        for arm in (common, treatment)
    }
    return {
        "converged": True,
        "iterations": calibration["iterations"],
        "coefficients": [
            {"id": modifier_id, "value": value}
            for modifier_id, value in zip(facts["modifier_ids"], calibration["alpha"])
        ],
        "balance": [
            {
                "id": modifier_id,
                "target_mean": target,
                "unweighted_mean": unweighted,
                "weighted_mean": weighted,
                "weighted_minus_target": error,
            }
            for modifier_id, target, unweighted, weighted, error in zip(
                facts["modifier_ids"], targets, unweighted_means, calibration["weighted_means"], calibration["balance_errors"]
            )
        ],
        "max_abs_balance_error": max(abs(value) for value in calibration["balance_errors"]),
        "ess": {
            "overall": _ess(weights),
            "common_comparator": _ess(arm_weights[common]),
            "ipd_treatment": _ess(arm_weights[treatment]),
        },
        "weights": {
            "minimum": min(weights),
            "p01": _quantile(weights, 0.01),
            "p05": _quantile(weights, 0.05),
            "median": _quantile(weights, 0.5),
            "p95": _quantile(weights, 0.95),
            "p99": _quantile(weights, 0.99),
            "maximum": max(weights),
            "coefficient_of_variation": _coefficient_of_variation(weights),
        },
    }


def execute_bootstrap(request: dict[str, Any], facts: dict[str, Any]) -> tuple[list[dict[str, Any]], list[float]]:
    method = request["method"]
    uncertainty = request["uncertainty"]
    measure = request["effect"]["measure"]
    aggregate_effect = float(facts["aggregate"]["effect"]["estimate"])
    draws: list[dict[str, Any]] = []
    successful: list[float] = []
    for iteration, sample in enumerate(
        bootstrap_samples(
            facts["rows"],
            method["common_comparator_id"],
            method["ipd_treatment_id"],
            uncertainty["iterations"],
            uncertainty["seed"],
        ),
        start=1,
    ):
        try:
            calibration = calibrate(sample, facts["targets"], 1e-10, 200)
            ipd_effect = effect_estimate(
                sample,
                calibration["weights"],
                method["common_comparator_id"],
                method["ipd_treatment_id"],
                measure,
            )
            indirect = ipd_effect - aggregate_effect
            successful.append(ipd_effect)
            draws.append({"iteration": iteration, "status": "ok", "ipd_effect": ipd_effect, "indirect_effect": indirect, "error": ""})
        except ValueError as error:
            draws.append({"iteration": iteration, "status": "failed", "ipd_effect": None, "indirect_effect": None, "error": str(error)[:240]})
    return draws, successful


def canonical_draw_bytes(draws: list[dict[str, Any]]) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["iteration", "status", "ipd_effect", "indirect_effect", "error"])
    for draw in draws:
        writer.writerow([
            draw["iteration"],
            draw["status"],
            "" if draw["ipd_effect"] is None else format(float(draw["ipd_effect"]), ".17g"),
            "" if draw["indirect_effect"] is None else format(float(draw["indirect_effect"]), ".17g"),
            draw["error"],
        ])
    return output.getvalue().encode("utf-8")


def expected_analysis(request: dict[str, Any], facts: dict[str, Any], draws: list[dict[str, Any]], successful: list[float]) -> dict[str, Any]:
    method = request["method"]
    measure = request["effect"]["measure"]
    calibration = facts["preflight_calibration"]
    adjusted = effect_estimate(
        facts["rows"], calibration["weights"], method["common_comparator_id"], method["ipd_treatment_id"], measure
    )
    unadjusted = effect_estimate(
        facts["rows"], [1.0] * len(facts["rows"]), method["common_comparator_id"], method["ipd_treatment_id"], measure
    )
    aggregate = float(facts["aggregate"]["effect"]["estimate"])
    aggregate_se = float(facts["aggregate"]["effect"]["se"])
    if len(successful) < 2:
        ipd_se = None
        indirect_se = None
    else:
        ipd_se = math.sqrt(_sample_variance(successful))
        indirect_se = math.sqrt(ipd_se * ipd_se + aggregate_se * aggregate_se)
    indirect = adjusted - aggregate
    lower = None if indirect_se is None else indirect - Z_95 * indirect_se
    upper = None if indirect_se is None else indirect + Z_95 * indirect_se
    failed = len(draws) - len(successful)
    return {
        "calibration": calibration_summary(request, facts, calibration),
        "effects": {
            "unadjusted_ipd_vs_common": {"estimate": unadjusted, "natural_estimate": natural_effect(measure, unadjusted)},
            "adjusted_ipd_vs_common": {
                "estimate": adjusted,
                "bootstrap_se": ipd_se,
                "natural_estimate": natural_effect(measure, adjusted),
            },
            "aggregate_vs_common": {
                "estimate": aggregate,
                "se": aggregate_se,
                "natural_estimate": natural_effect(measure, aggregate),
            },
            "indirect_ipd_vs_aggregate": {
                "estimate": indirect,
                "se": indirect_se,
                "lower": lower,
                "upper": upper,
                "natural_estimate": natural_effect(measure, indirect),
                "natural_lower": None if lower is None else natural_effect(measure, lower),
                "natural_upper": None if upper is None else natural_effect(measure, upper),
            },
        },
        "bootstrap": {
            "method": "stratified_nonparametric_bootstrap_refit",
            "iterations": len(draws),
            "successful": len(successful),
            "failed": failed,
            "seed": request["uncertainty"]["seed"],
            "prng": {"algorithm": RNG_ALGORITHM, "version": RNG_VERSION},
            "failure_policy": "retain_and_block_review",
        },
        "complete": failed == 0 and len(successful) == len(draws),
    }


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
    for key, request_key in (("source_data", "source_data"), ("aggregate_evidence", "aggregate_evidence"), ("evidence_synthesis", "evidence_synthesis")):
        binding = result.get(key)
        expected = request.get(request_key, {}) if request else {}
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
    method_result = result.get("method")
    expected_method = {
        "family": "anchored_maic",
        "target_population": request.get("method", {}).get("target_population"),
        "ipd_trial_id": request.get("method", {}).get("ipd_trial_id"),
        "aggregate_trial_id": request.get("method", {}).get("aggregate_trial_id"),
        "common_comparator_id": request.get("method", {}).get("common_comparator_id"),
        "ipd_treatment_id": request.get("method", {}).get("ipd_treatment_id"),
        "aggregate_treatment_id": request.get("method", {}).get("aggregate_treatment_id"),
        "effect_measure": request.get("effect", {}).get("measure"),
        "scale": request.get("effect", {}).get("scale"),
    }
    if method_result != expected_method:
        errors.append("result method does not match the bound request")

    bootstrap = result.get("bootstrap")
    draws: list[dict[str, Any]] = []
    successful: list[float] = []
    if not exact(bootstrap, {"method", "iterations", "successful", "failed", "seed", "prng", "failure_policy", "draws"}):
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
        _deep_close(result.get("calibration"), expected["calibration"], "calibration", errors)
        _deep_close(result.get("effects"), expected["effects"], "effects", errors)
        expected_bootstrap = {**expected["bootstrap"], "draws": result["bootstrap"]["draws"]}
        _deep_close(result.get("bootstrap"), expected_bootstrap, "bootstrap", errors)
        expected_status = "awaiting_method_review" if expected["complete"] else "incomplete_bootstrap"
        if result.get("status") != expected_status:
            errors.append("result status does not match bootstrap completeness")
    cross = result.get("cross_implementation")
    if cross != {
        "portable_replay": "complete_calibration_point_and_bootstrap",
        "native_replay": "calibration_and_point_estimate_only",
        "uncertainty_native_replay": False,
    }:
        errors.append("result cross_implementation scope is invalid")
    if not isinstance(result.get("warnings"), list) or any(not text(value) for value in result["warnings"]):
        errors.append("result warnings must be text")
    elif request and facts and result.get("calibration") and result.get("bootstrap"):
        expected_warnings: list[str] = []
        if float(result["calibration"]["ess"]["overall"]) < 0.5 * len(facts["rows"]):
            expected_warnings.append("Overall effective sample size is below 50% of the original IPD sample; Human overlap review is required.")
        if float(result["calibration"]["weights"]["maximum"]) > 10:
            expected_warnings.append("At least one mean-one calibration weight exceeds 10; the estimate may be highly influential.")
        if result["bootstrap"]["failed"]:
            expected_warnings.append("One or more bootstrap refits failed; the result is incomplete and cannot enter Human method acceptance.")
        if result["warnings"] != expected_warnings:
            errors.append("result warnings do not match deterministic diagnostics")
    if result.get("limitations") != request.get("limitations"):
        errors.append("result limitations must exactly preserve the request")
    gate = result.get("human_gate")
    if gate != {"status": "awaiting_method_review", "required_checks": REQUIRED_REVIEW_CHECKS, "automatic_downstream_use": False}:
        errors.append("result human_gate is invalid")
    complete = not errors and result.get("status") == "awaiting_method_review" and result.get("bootstrap", {}).get("failed") == 0
    return {
        "complete": complete,
        "reviewable": complete,
        "result_sha256": digest(result_raw),
        "execution_id": result.get("execution_id") if safe_id(result.get("execution_id")) else None,
        "errors": errors,
    }


def parse_args(description: str) -> tuple[Path, Path]:
    import argparse

    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--request", type=Path)
    parser.add_argument("--result", type=Path)
    args = parser.parse_args()
    workspace = args.workspace.expanduser().resolve()
    path = args.request if args.request is not None else args.result
    if path is None:
        parser.error("one of --request or --result is required")
    return workspace, path


def current_python_identity() -> dict[str, str]:
    executable = Path(sys.executable).resolve()
    return {
        "python_version": sys.version.split()[0],
        "python_executable_sha256": digest(executable.read_bytes()),
    }
