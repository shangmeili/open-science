#!/usr/bin/env python3
"""Dependency-free contract and independent WLS audit for bounded NMA runs."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any


REQUEST_SCHEMA_VERSION = "0.1.0"
RESULT_SCHEMA_VERSION = "0.1.0"
EVALUATOR = "ai4heor-nma-wls@0.1.0"
SAFE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
VERSION = re.compile(r"^[0-9][0-9A-Za-z.+-]{0,63}$")
CSV_COLUMNS = ["study_id", "treat1", "treat2", "effect", "se"]
EFFECT_MEASURES = {
    "log_odds_ratio": ("OR", "log"),
    "log_risk_ratio": ("RR", "log"),
    "log_hazard_ratio": ("HR", "log"),
    "mean_difference": ("MD", "identity"),
    "standardized_mean_difference": ("SMD", "identity"),
}
PACKAGE_NAMES = {"netmeta", "meta", "metafor"}
REQUIRED_REVIEW_CHECKS = [
    "question_outcome_estimand",
    "nodes_connectivity_two_arm_boundary",
    "study_contrasts_provenance_risk_of_bias",
    "transitivity_effect_modifiers",
    "model_tau_method",
    "heterogeneity_prediction",
    "global_local_inconsistency",
    "ranking_transportability_limitations",
]
REQUEST_FIELDS = {
    "schema_version",
    "execution_id",
    "status",
    "question",
    "evidence_synthesis",
    "source_data",
    "treatments",
    "reference_treatment",
    "effect",
    "model",
    "transitivity",
    "diagnostics",
    "runtime",
    "output",
    "study_provenance",
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
    "backend_outputs",
    "network",
    "model",
    "estimates_vs_reference",
    "league_table",
    "heterogeneity",
    "inconsistency",
    "ranking",
    "cross_implementation",
    "warnings",
    "limitations",
    "human_gate",
}
MAX_JSON_BYTES = 16 * 1024 * 1024
MAX_CSV_BYTES = 64 * 1024 * 1024
MAX_STUDIES = 5_000
MAX_TREATMENTS = 32
TOLERANCE = 1e-8
Z_95 = 1.959963984540054


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def exact(value: Any, fields: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == fields


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


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
        existing_resolved = existing.resolve(strict=True)
    except OSError:
        return None
    if not existing_resolved.is_relative_to(root) or existing.is_symlink():
        return None
    return candidate


def load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError(f"{path} exceeds the JSON size cap")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value, raw


def _comparison(left: str, right: str) -> str:
    return ":".join(sorted((left, right)))


def inspect_contrast_csv(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any], list[str]]:
    errors: list[str] = []
    rows: list[dict[str, Any]] = []
    if path.stat().st_size > MAX_CSV_BYTES:
        return rows, {}, ["source_data CSV exceeds 64 MB"]
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames != CSV_COLUMNS:
                return rows, {}, ["source_data CSV columns must be exactly study_id,treat1,treat2,effect,se"]
            for line_number, raw in enumerate(reader, start=2):
                if None in raw or any(raw.get(column) is None for column in CSV_COLUMNS):
                    errors.append(f"source_data row {line_number} has an invalid column count")
                    continue
                values = [raw[column] for column in CSV_COLUMNS]
                if any(value != value.strip() or not value for value in values):
                    errors.append(f"source_data row {line_number} contains blank or padded values")
                    continue
                study_id, treat1, treat2, effect_raw, se_raw = values
                if not safe_id(study_id):
                    errors.append(f"source_data row {line_number} study_id is unsafe")
                if not safe_id(treat1) or not safe_id(treat2) or treat1 == treat2:
                    errors.append(f"source_data row {line_number} treatment IDs are invalid")
                try:
                    effect = float(effect_raw)
                    se = float(se_raw)
                except ValueError:
                    errors.append(f"source_data row {line_number} effect and se must be numeric")
                    continue
                if not math.isfinite(effect) or abs(effect) > 100:
                    errors.append(f"source_data row {line_number} effect must be finite and bounded")
                if not math.isfinite(se) or se <= 0 or se > 100:
                    errors.append(f"source_data row {line_number} se must be finite, positive, and bounded")
                rows.append({"study_id": study_id, "treat1": treat1, "treat2": treat2, "effect": effect, "se": se})
    except (OSError, UnicodeError, csv.Error) as error:
        return rows, {}, [f"source_data CSV cannot be read: {error}"]

    study_ids = [row["study_id"] for row in rows]
    if len(study_ids) != len(set(study_ids)):
        errors.append("every study_id must occur exactly once; multi-arm or duplicate studies are rejected")
    if not 3 <= len(rows) <= MAX_STUDIES:
        errors.append(f"source_data must contain 3 to {MAX_STUDIES} studies")
    treatment_ids = sorted({row["treat1"] for row in rows} | {row["treat2"] for row in rows})
    comparisons = sorted({_comparison(row["treat1"], row["treat2"]) for row in rows})
    adjacency = {treatment: set() for treatment in treatment_ids}
    for row in rows:
        adjacency[row["treat1"]].add(row["treat2"])
        adjacency[row["treat2"]].add(row["treat1"])
    visited: set[str] = set()
    if treatment_ids:
        stack = [treatment_ids[0]]
        while stack:
            current = stack.pop()
            if current in visited:
                continue
            visited.add(current)
            stack.extend(adjacency[current] - visited)
    connected = bool(treatment_ids) and len(visited) == len(treatment_ids)
    if not 3 <= len(treatment_ids) <= MAX_TREATMENTS:
        errors.append(f"network must contain 3 to {MAX_TREATMENTS} treatments")
    if not connected:
        errors.append("treatment network must be connected")
    facts = {
        "row_count": len(rows),
        "study_count": len(set(study_ids)),
        "treatments": treatment_ids,
        "comparisons": comparisons,
        "direct_comparison_count": len(comparisons),
        "cycle_rank": max(0, len(comparisons) - len(treatment_ids) + 1) if connected else 0,
        "connected": connected,
    }
    return rows, facts, errors


def _bound_json(workspace: Path, binding: Any, label: str, errors: list[str]) -> tuple[Path | None, dict[str, Any] | None, bytes | None]:
    if not exact(binding, {"path", "sha256"}) or not isinstance(binding.get("sha256"), str) or SHA256.fullmatch(binding["sha256"]) is None:
        errors.append(f"{label} binding must contain only a safe path and lowercase SHA-256")
        return None, None, None
    path = resolve_file(workspace, binding["path"])
    if path is None:
        errors.append(f"{label} path is unavailable or unsafe")
        return None, None, None
    try:
        value, raw = load_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        errors.append(f"{label} is invalid: {error}")
        return path, None, None
    if digest(raw) != binding["sha256"]:
        errors.append(f"{label} SHA-256 does not match current bytes")
    return path, value, raw


def validate_request(value: Any, workspace: Path) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    facts: dict[str, Any] = {}
    if not exact(value, REQUEST_FIELDS):
        return ["NMA request fields are not the exact supported contract"], facts
    if value["schema_version"] != REQUEST_SCHEMA_VERSION:
        errors.append(f"schema_version must be {REQUEST_SCHEMA_VERSION}")
    execution_id = value["execution_id"]
    if not safe_id(execution_id):
        errors.append("execution_id must be a safe lowercase identifier")
    if value["status"] != "ready_for_execution":
        errors.append("status must be ready_for_execution")

    question = value["question"]
    question_fields = {"population", "intervention_network", "outcome", "timepoint", "estimand", "study_design"}
    if not exact(question, question_fields) or any(not text(question.get(field)) for field in question_fields - {"study_design"}):
        errors.append("question fields are incomplete")
    elif question["study_design"] != "randomized_parallel_two_arm":
        errors.append("only randomized_parallel_two_arm studies are admitted")

    evidence = value["evidence_synthesis"]
    evidence_fields = {"path", "sha256", "included_record_ids"}
    if not exact(evidence, evidence_fields):
        errors.append("evidence_synthesis fields are invalid")
        included_record_ids: list[str] = []
    else:
        included_record_ids = evidence["included_record_ids"] if isinstance(evidence["included_record_ids"], list) else []
        if not included_record_ids or any(not safe_id(item) for item in included_record_ids) or len(included_record_ids) != len(set(included_record_ids)):
            errors.append("evidence_synthesis.included_record_ids must be unique safe IDs")
        _bound_json(workspace, {"path": evidence.get("path"), "sha256": evidence.get("sha256")}, "evidence_synthesis", errors)

    source = value["source_data"]
    source_fields = {
        "classification", "execution_boundary", "format", "path", "sha256", "columns",
        "row_count", "study_count", "contains_direct_identifiers", "missing_policy", "multiarm_policy",
    }
    rows: list[dict[str, Any]] = []
    csv_facts: dict[str, Any] = {}
    if not exact(source, source_fields):
        errors.append("source_data fields are invalid")
    else:
        if source["classification"] not in {"public", "non_sensitive"}:
            errors.append("source_data classification must be public or non_sensitive")
        if source["execution_boundary"] != "local_only" or source["format"] != "contrast_csv":
            errors.append("source_data must be a local-only contrast_csv")
        if source["columns"] != CSV_COLUMNS:
            errors.append("source_data.columns must match the fixed contrast contract")
        if source["contains_direct_identifiers"] is not False:
            errors.append("source_data containing direct identifiers is rejected")
        if source["missing_policy"] != "reject" or source["multiarm_policy"] != "reject":
            errors.append("source_data must reject missing values and multi-arm studies")
        if not isinstance(source["sha256"], str) or SHA256.fullmatch(source["sha256"]) is None:
            errors.append("source_data.sha256 must be lowercase SHA-256")
        source_path = resolve_file(workspace, source["path"])
        if source_path is None:
            errors.append("source_data.path is unavailable or unsafe")
        else:
            raw = source_path.read_bytes()
            if digest(raw) != source["sha256"]:
                errors.append("source_data.sha256 does not match current bytes")
            rows, csv_facts, csv_errors = inspect_contrast_csv(source_path)
            errors.extend(csv_errors)
            for field in ("row_count", "study_count"):
                if source[field] != csv_facts.get(field):
                    errors.append(f"source_data.{field} does not match current CSV")
    facts.update(csv_facts)
    facts["rows"] = rows

    treatments = value["treatments"]
    treatment_ids: list[str] = []
    if not isinstance(treatments, list) or not 3 <= len(treatments) <= MAX_TREATMENTS:
        errors.append(f"treatments must contain 3 to {MAX_TREATMENTS} nodes")
    else:
        for index, treatment in enumerate(treatments):
            if not exact(treatment, {"id", "label", "node_definition", "merging_rationale"}):
                errors.append(f"treatments[{index}] fields are invalid")
                continue
            if not safe_id(treatment["id"]) or any(not text(treatment[field]) for field in ("label", "node_definition", "merging_rationale")):
                errors.append(f"treatments[{index}] is incomplete")
            treatment_ids.append(treatment["id"])
        if len(treatment_ids) != len(set(treatment_ids)):
            errors.append("treatment IDs must be unique")
        if set(treatment_ids) != set(csv_facts.get("treatments", [])):
            errors.append("declared treatments must exactly match the current CSV network")
    if value["reference_treatment"] not in treatment_ids:
        errors.append("reference_treatment must be a declared treatment")
    facts["treatment_order"] = treatment_ids

    effect = value["effect"]
    effect_fields = {"measure", "scale", "likelihood", "link", "confidence_level", "favorable_direction"}
    if not exact(effect, effect_fields) or effect.get("measure") not in EFFECT_MEASURES:
        errors.append("effect fields or measure are invalid")
    else:
        _, expected_scale = EFFECT_MEASURES[effect["measure"]]
        if effect["scale"] != expected_scale or effect["likelihood"] != "normal" or effect["link"] != "identity":
            errors.append("effect scale, likelihood, and link do not match the admitted contrast model")
        if effect["confidence_level"] != 0.95:
            errors.append("confidence_level must be exactly 0.95")
        if effect["favorable_direction"] not in {"lower", "higher"}:
            errors.append("favorable_direction must be lower or higher")

    model = value["model"]
    model_fields = {"type", "heterogeneity_variance", "tau_method", "prediction_interval"}
    if not exact(model, model_fields) or model.get("type") not in {"common", "random"}:
        errors.append("model fields or type are invalid")
    elif model["type"] == "common":
        if model["heterogeneity_variance"] != "none" or model["tau_method"] != "none" or model["prediction_interval"] is not False:
            errors.append("common model must disable heterogeneity variance, tau estimation, and prediction intervals")
    elif model["heterogeneity_variance"] != "common_tau_squared" or model["tau_method"] != "REML" or model["prediction_interval"] is not True:
        errors.append("random model must use common_tau_squared, REML, and prediction intervals")

    transitivity = value["transitivity"]
    trans_fields = {"status", "joint_randomizability_rationale", "effect_modifiers", "concerns"}
    if not exact(transitivity, trans_fields):
        errors.append("transitivity fields are invalid")
    else:
        if transitivity["status"] != "awaiting_human_review" or not text(transitivity["joint_randomizability_rationale"]):
            errors.append("transitivity must await Human review and include joint-randomizability rationale")
        concerns = transitivity["concerns"]
        if not isinstance(concerns, list) or any(not text(item) for item in concerns):
            errors.append("transitivity.concerns must be a string array")
        modifiers = transitivity["effect_modifiers"]
        if not isinstance(modifiers, list) or not modifiers:
            errors.append("at least one effect modifier must be assessed")
        else:
            modifier_ids: list[str] = []
            expected_comparisons = set(csv_facts.get("comparisons", []))
            for index, modifier in enumerate(modifiers):
                if not exact(modifier, {"id", "label", "rationale", "comparison_summaries"}):
                    errors.append(f"effect_modifiers[{index}] fields are invalid")
                    continue
                if not safe_id(modifier["id"]) or not text(modifier["label"]) or not text(modifier["rationale"]):
                    errors.append(f"effect_modifiers[{index}] is incomplete")
                modifier_ids.append(modifier["id"])
                summaries = modifier["comparison_summaries"]
                seen: set[str] = set()
                if not isinstance(summaries, list):
                    errors.append(f"effect_modifiers[{index}].comparison_summaries must be an array")
                    continue
                for summary_index, summary in enumerate(summaries):
                    if not exact(summary, {"comparison", "summary", "source_ids"}) or not text(summary.get("summary")):
                        errors.append(f"effect_modifiers[{index}].comparison_summaries[{summary_index}] is invalid")
                        continue
                    comparison = summary["comparison"]
                    if comparison not in expected_comparisons or comparison in seen:
                        errors.append(f"effect_modifiers[{index}] has an unknown or duplicate comparison")
                    seen.add(comparison)
                    source_ids = summary["source_ids"]
                    if not isinstance(source_ids, list) or not source_ids or any(item not in included_record_ids for item in source_ids):
                        errors.append(f"effect_modifiers[{index}] comparison sources must be included evidence records")
                if seen != expected_comparisons:
                    errors.append(f"effect_modifiers[{index}] must summarize every direct comparison")
            if len(modifier_ids) != len(set(modifier_ids)):
                errors.append("effect modifier IDs must be unique")

    diagnostics = value["diagnostics"]
    if not exact(diagnostics, {"global_inconsistency", "local_inconsistency", "ranking"}):
        errors.append("diagnostics fields are invalid")
    elif diagnostics["global_inconsistency"] != "design_decomposition" or diagnostics["local_inconsistency"] != "node_splitting" or diagnostics["ranking"] not in {"none", "p_score"}:
        errors.append("diagnostics methods are outside the admitted contract")

    runtime = value["runtime"]
    if not exact(runtime, {"r_version", "package_versions", "adapter_sha256"}):
        errors.append("runtime fields are invalid")
    else:
        if not isinstance(runtime["r_version"], str) or VERSION.fullmatch(runtime["r_version"]) is None:
            errors.append("runtime.r_version is invalid")
        packages = runtime["package_versions"]
        if not isinstance(packages, dict) or set(packages) != PACKAGE_NAMES or any(not isinstance(version, str) or VERSION.fullmatch(version) is None for version in packages.values()):
            errors.append("runtime.package_versions must identify netmeta, meta, and metafor exactly")
        if not isinstance(runtime["adapter_sha256"], str) or SHA256.fullmatch(runtime["adapter_sha256"]) is None:
            errors.append("runtime.adapter_sha256 must be lowercase SHA-256")

    output = value["output"]
    expected_output = f"heor/network-meta-analysis-runs/{execution_id}" if safe_id(execution_id) else ""
    if not exact(output, {"directory"}) or output.get("directory") != expected_output or resolve_output_directory(workspace, output.get("directory")) is None:
        errors.append("output.directory must be the safe execution-specific NMA directory")

    provenance = value["study_provenance"]
    seen_studies: set[str] = set()
    csv_study_ids = {row["study_id"] for row in rows}
    if not isinstance(provenance, list):
        errors.append("study_provenance must be an array")
    else:
        for index, item in enumerate(provenance):
            if not exact(item, {"study_id", "evidence_record_ids", "extraction_ids", "risk_of_bias"}):
                errors.append(f"study_provenance[{index}] fields are invalid")
                continue
            study_id = item["study_id"]
            if study_id in seen_studies or study_id not in csv_study_ids:
                errors.append(f"study_provenance[{index}] has an unknown or duplicate study_id")
            seen_studies.add(study_id)
            record_ids = item["evidence_record_ids"]
            extraction_ids = item["extraction_ids"]
            if not isinstance(record_ids, list) or not record_ids or any(record not in included_record_ids for record in record_ids):
                errors.append(f"study_provenance[{index}] evidence_record_ids are invalid")
            if not isinstance(extraction_ids, list) or not extraction_ids or any(not safe_id(extraction) for extraction in extraction_ids):
                errors.append(f"study_provenance[{index}] extraction_ids are invalid")
            if item["risk_of_bias"] not in {"low", "some_concerns", "high", "not_assessed"}:
                errors.append(f"study_provenance[{index}].risk_of_bias is invalid")
        if seen_studies != csv_study_ids:
            errors.append("study_provenance must cover every current CSV study exactly once")

    limitations = value["limitations"]
    if not isinstance(limitations, list) or not limitations or any(not text(item) for item in limitations):
        errors.append("limitations must contain at least one non-empty statement")
    gate = value["human_gate"]
    if not exact(gate, {"status", "required_checks"}) or gate.get("status") != "awaiting_model_review" or gate.get("required_checks") != REQUIRED_REVIEW_CHECKS:
        errors.append("human_gate must contain the exact awaiting-model-review checklist")
    return errors, facts


def _invert(matrix: list[list[float]]) -> list[list[float]]:
    size = len(matrix)
    augmented = [row[:] + [1.0 if i == j else 0.0 for j in range(size)] for i, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-14:
            raise ValueError("network design matrix is singular")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        scale = augmented[column][column]
        augmented[column] = [value / scale for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [left - factor * right for left, right in zip(augmented[row], augmented[column])]
    return [row[size:] for row in augmented]


def weighted_network(rows: list[dict[str, Any]], treatment_order: list[str], reference: str, tau: float) -> tuple[dict[str, float], list[list[float]], list[str]]:
    non_reference = [treatment for treatment in treatment_order if treatment != reference]
    positions = {treatment: index for index, treatment in enumerate(non_reference)}
    size = len(non_reference)
    information = [[0.0 for _ in range(size)] for _ in range(size)]
    rhs = [0.0 for _ in range(size)]
    for row in rows:
        design = [0.0 for _ in range(size)]
        if row["treat1"] != reference:
            design[positions[row["treat1"]]] += 1.0
        if row["treat2"] != reference:
            design[positions[row["treat2"]]] -= 1.0
        weight = 1.0 / (float(row["se"]) ** 2 + tau**2)
        for i in range(size):
            rhs[i] += weight * design[i] * float(row["effect"])
            for j in range(size):
                information[i][j] += weight * design[i] * design[j]
    covariance = _invert(information)
    beta = [sum(covariance[i][j] * rhs[j] for j in range(size)) for i in range(size)]
    effects = {reference: 0.0, **{treatment: beta[index] for index, treatment in enumerate(non_reference)}}
    return effects, covariance, non_reference


def _pair_expected(left: str, right: str, effects: dict[str, float], covariance: list[list[float]], non_reference: list[str]) -> tuple[float, float]:
    effect = effects[left] - effects[right]
    positions = {treatment: index for index, treatment in enumerate(non_reference)}
    variance = 0.0
    if left in positions:
        variance += covariance[positions[left]][positions[left]]
    if right in positions:
        variance += covariance[positions[right]][positions[right]]
    if left in positions and right in positions:
        variance -= 2.0 * covariance[positions[left]][positions[right]]
    if variance < -1e-12:
        raise ValueError("network covariance produced a negative contrast variance")
    return effect, math.sqrt(max(0.0, variance))


def natural_effect(measure: str, effect: float) -> float:
    return math.exp(effect) if EFFECT_MEASURES[measure][1] == "log" else effect


def expected_rows(request: dict[str, Any], facts: dict[str, Any], tau: float) -> tuple[list[dict[str, float | str]], list[dict[str, float | str]]]:
    effects, covariance, non_reference = weighted_network(
        facts["rows"], facts["treatment_order"], request["reference_treatment"], tau
    )
    reference_rows: list[dict[str, float | str]] = []
    for treatment in facts["treatment_order"]:
        if treatment == request["reference_treatment"]:
            continue
        estimate, se = _pair_expected(treatment, request["reference_treatment"], effects, covariance, non_reference)
        reference_rows.append({
            "treatment": treatment,
            "effect": estimate,
            "se": se,
            "lower": estimate - Z_95 * se,
            "upper": estimate + Z_95 * se,
            "natural_effect": natural_effect(request["effect"]["measure"], estimate),
        })
    league: list[dict[str, float | str]] = []
    for left in facts["treatment_order"]:
        for right in facts["treatment_order"]:
            if left == right:
                continue
            estimate, se = _pair_expected(left, right, effects, covariance, non_reference)
            league.append({
                "treat1": left,
                "treat2": right,
                "effect": estimate,
                "se": se,
                "lower": estimate - Z_95 * se,
                "upper": estimate + Z_95 * se,
                "natural_effect": natural_effect(request["effect"]["measure"], estimate),
            })
    return reference_rows, league


def _number_close(observed: Any, expected: float, tolerance: float = TOLERANCE) -> bool:
    return finite(observed) and abs(float(observed) - expected) <= tolerance * max(1.0, abs(expected))


def _audit_estimate_rows(observed: Any, expected: list[dict[str, Any]], key_fields: tuple[str, ...], errors: list[str], label: str) -> float:
    if not isinstance(observed, list) or len(observed) != len(expected):
        errors.append(f"{label} must contain exactly {len(expected)} rows")
        return math.inf
    expected_map = {tuple(row[field] for field in key_fields): row for row in expected}
    seen: set[tuple[Any, ...]] = set()
    max_error = 0.0
    numeric_fields = ("effect", "se", "lower", "upper", "natural_effect")
    allowed = set(key_fields) | set(numeric_fields) | {"prediction_lower", "prediction_upper"}
    for index, row in enumerate(observed):
        if not isinstance(row, dict) or set(row) != allowed:
            errors.append(f"{label}[{index}] fields are invalid")
            continue
        key = tuple(row.get(field) for field in key_fields)
        if key in seen or key not in expected_map:
            errors.append(f"{label}[{index}] has an unknown or duplicate key")
            continue
        seen.add(key)
        expected_row = expected_map[key]
        for field in numeric_fields:
            if not _number_close(row[field], float(expected_row[field])):
                errors.append(f"{label}[{index}].{field} does not match independent WLS")
            elif finite(row[field]):
                max_error = max(max_error, abs(float(row[field]) - float(expected_row[field])))
    if seen != set(expected_map):
        errors.append(f"{label} does not cover the complete expected network")
    return max_error


def _read_tsv(path: Path, expected_columns: list[str], label: str, errors: list[str]) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t")
            if reader.fieldnames != expected_columns:
                errors.append(f"{label} columns do not match the fixed backend contract")
                return []
            return list(reader)
    except (OSError, UnicodeError, csv.Error) as error:
        errors.append(f"{label} cannot be parsed: {error}")
        return []


def _raw_number(value: Any, label: str, errors: list[str], optional: bool = False) -> float | None:
    if optional and value == "":
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        errors.append(f"{label} must be numeric")
        return None
    if not math.isfinite(parsed):
        errors.append(f"{label} must be finite")
        return None
    return parsed


def _audit_backend_matrix(
    path: Path,
    result: dict[str, Any],
    expected_league: list[dict[str, Any]],
    reference: str,
    prediction_required: bool,
    errors: list[str],
) -> bool | None:
    columns = [
        "row_treatment", "column_treatment", "effect", "se", "lower", "upper",
        "prediction_lower", "prediction_upper",
    ]
    rows = _read_tsv(path, columns, "backend matrix", errors)
    raw: dict[tuple[str, str], dict[str, float | None]] = {}
    for index, row in enumerate(rows):
        key = (row["row_treatment"], row["column_treatment"])
        if key in raw or key[0] == key[1]:
            errors.append(f"backend matrix row {index} has a duplicate or diagonal key")
            continue
        values = {
            field: _raw_number(row[field], f"backend matrix row {index} {field}", errors, field.startswith("prediction_"))
            for field in ("effect", "se", "lower", "upper", "prediction_lower", "prediction_upper")
        }
        raw[key] = values
    if len(raw) != len(expected_league):
        errors.append("backend matrix does not contain the complete ordered treatment network")
        return None

    def orientation_error(reverse: bool) -> float:
        maximum = 0.0
        for expected in expected_league:
            key = (expected["treat2"], expected["treat1"]) if reverse else (expected["treat1"], expected["treat2"])
            values = raw.get(key)
            if values is None or any(values[field] is None for field in ("effect", "se", "lower", "upper")):
                return math.inf
            maximum = max(
                maximum,
                *(abs(float(values[field]) - float(expected[field])) for field in ("effect", "se", "lower", "upper")),
            )
        return maximum

    direct_error = orientation_error(False)
    reverse_error = orientation_error(True)
    if min(direct_error, reverse_error) > TOLERANCE:
        errors.append("backend matrix cannot be reconciled with independent WLS in either orientation")
        return None
    reverse = reverse_error < direct_error
    observed_league = {
        (row.get("treat1"), row.get("treat2")): row
        for row in result.get("league_table", [])
        if isinstance(row, dict)
    }
    for expected in expected_league:
        desired_key = (expected["treat1"], expected["treat2"])
        raw_key = (desired_key[1], desired_key[0]) if reverse else desired_key
        raw_row = raw.get(raw_key, {})
        observed = observed_league.get(desired_key)
        if observed is None:
            continue
        for field in ("effect", "se", "lower", "upper", "prediction_lower", "prediction_upper"):
            raw_value = raw_row.get(field)
            observed_value = observed.get(field)
            if raw_value is None or observed_value is None:
                if raw_value is not None or observed_value is not None:
                    errors.append(f"league_table {desired_key[0]}:{desired_key[1]} {field} does not match backend matrix")
            elif not _number_close(observed_value, float(raw_value)):
                errors.append(f"league_table {desired_key[0]}:{desired_key[1]} {field} does not match backend matrix")
        if prediction_required and (raw_row.get("prediction_lower") is None or raw_row.get("prediction_upper") is None):
            errors.append(f"backend matrix {desired_key[0]}:{desired_key[1]} omitted the required prediction interval")

    league_by_treatment = {
        row.get("treat1"): row
        for row in result.get("league_table", [])
        if isinstance(row, dict) and row.get("treat2") == reference
    }
    for index, observed in enumerate(result.get("estimates_vs_reference", [])):
        if not isinstance(observed, dict):
            continue
        league_row = league_by_treatment.get(observed.get("treatment"))
        if league_row is None:
            continue
        for field in ("effect", "se", "lower", "upper", "natural_effect", "prediction_lower", "prediction_upper"):
            left, right = observed.get(field), league_row.get(field)
            if left is None or right is None:
                if left is not None or right is not None:
                    errors.append(f"estimates_vs_reference[{index}].{field} does not match the league table")
            elif not _number_close(left, float(right)):
                errors.append(f"estimates_vs_reference[{index}].{field} does not match the league table")
    return reverse


def _audit_backend_diagnostics(
    path: Path,
    result: dict[str, Any],
    cycle_rank: int,
    errors: list[str],
) -> None:
    columns = [
        "tau", "q_total", "df_total", "p_total", "q_heterogeneity", "df_heterogeneity",
        "p_heterogeneity", "q_inconsistency", "df_inconsistency", "p_inconsistency",
    ]
    rows = _read_tsv(path, columns, "backend diagnostics", errors)
    if len(rows) != 1:
        errors.append("backend diagnostics must contain exactly one row")
        return
    row = rows[0]
    heterogeneity = result.get("heterogeneity", {})
    mapping = {
        "tau": "tau",
        "q_total": "q_total",
        "df_total": "df_total",
        "p_total": "p_total",
        "q_heterogeneity": "q_heterogeneity",
        "df_heterogeneity": "df_heterogeneity",
        "p_heterogeneity": "p_heterogeneity",
    }
    for raw_field, result_field in mapping.items():
        raw_value = _raw_number(row[raw_field], f"backend diagnostics {raw_field}", errors, raw_field.startswith("p_"))
        result_value = heterogeneity.get(result_field)
        if raw_value is None or result_value is None:
            if raw_value is not None or result_value is not None:
                errors.append(f"heterogeneity.{result_field} does not match backend diagnostics")
        elif not _number_close(result_value, raw_value):
            errors.append(f"heterogeneity.{result_field} does not match backend diagnostics")
    if cycle_rank > 0:
        global_value = result.get("inconsistency", {}).get("global", {})
        for raw_field, result_field in (("q_inconsistency", "q"), ("df_inconsistency", "df"), ("p_inconsistency", "p_value")):
            raw_value = _raw_number(row[raw_field], f"backend diagnostics {raw_field}", errors)
            if raw_value is not None and not _number_close(global_value.get(result_field), raw_value):
                errors.append(f"global inconsistency {result_field} does not match backend diagnostics")


def _audit_backend_local(
    path: Path,
    result: dict[str, Any],
    reverse: bool | None,
    comparisons: list[str],
    errors: list[str],
) -> None:
    columns = [
        "row_treatment", "column_treatment", "network_effect", "direct_effect",
        "indirect_effect", "difference", "se_difference", "p_value",
    ]
    rows = _read_tsv(path, columns, "backend local inconsistency", errors)
    if reverse is None:
        return
    normalized: dict[str, dict[str, float]] = {}
    for index, row in enumerate(rows):
        raw_left, raw_right = row["row_treatment"], row["column_treatment"]
        represented_left, represented_right = (raw_right, raw_left) if reverse else (raw_left, raw_right)
        canonical_left, canonical_right = sorted((represented_left, represented_right))
        comparison = f"{canonical_left}:{canonical_right}"
        if comparison not in comparisons or comparison in normalized:
            errors.append(f"backend local inconsistency row {index} has an unknown or duplicate comparison")
            continue
        sign = 1.0 if (represented_left, represented_right) == (canonical_left, canonical_right) else -1.0
        values: dict[str, float] = {}
        for field in ("network_effect", "direct_effect", "indirect_effect", "difference", "se_difference", "p_value"):
            raw_value = _raw_number(row[field], f"backend local inconsistency row {index} {field}", errors)
            if raw_value is not None:
                values[field] = raw_value * sign if field in {"network_effect", "direct_effect", "indirect_effect", "difference"} else raw_value
        normalized[comparison] = values
    observed = {
        row.get("comparison"): row
        for row in result.get("inconsistency", {}).get("local", [])
        if isinstance(row, dict)
    }
    if set(observed) != set(normalized):
        errors.append("local inconsistency rows do not match the estimable backend comparisons")
        return
    for comparison, raw_row in normalized.items():
        for field, raw_value in raw_row.items():
            if not _number_close(observed[comparison].get(field), raw_value):
                errors.append(f"local inconsistency {comparison} {field} does not match backend output")


def _audit_backend_ranking(path: Path, result: dict[str, Any], errors: list[str]) -> None:
    rows = _read_tsv(path, ["treatment", "p_score"], "backend ranking", errors)
    observed_rows = result.get("ranking", {}).get("rows", [])
    observed = {
        row.get("treatment"): row.get("p_score")
        for row in observed_rows
        if isinstance(row, dict)
    }
    raw: dict[str, float] = {}
    for index, row in enumerate(rows):
        score = _raw_number(row["p_score"], f"backend ranking row {index} p_score", errors)
        if row["treatment"] in raw:
            errors.append(f"backend ranking row {index} duplicates a treatment")
        elif score is not None:
            raw[row["treatment"]] = score
    if set(observed) != set(raw):
        errors.append("ranking rows do not match the backend ranking output")
    else:
        for treatment, score in raw.items():
            if not _number_close(observed[treatment], score):
                errors.append(f"ranking score for {treatment} does not match backend output")


def audit_result(manifest_path: Path, workspace: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        result, result_raw = load_json(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return {"complete": False, "eligible_for_review": False, "errors": [f"result manifest is invalid: {error}"]}
    if not exact(result, RESULT_FIELDS):
        return {"complete": False, "eligible_for_review": False, "errors": ["result manifest fields are not the exact supported contract"]}
    if result["schema_version"] != RESULT_SCHEMA_VERSION:
        errors.append(f"result schema_version must be {RESULT_SCHEMA_VERSION}")
    if result["status"] != "awaiting_model_review":
        errors.append("result status must be awaiting_model_review")
    request_binding = result["request"]
    request_path, request, request_raw = _bound_json(workspace, request_binding, "request", errors)
    request_facts: dict[str, Any] = {}
    if request is not None:
        request_errors, request_facts = validate_request(request, workspace)
        errors.extend(f"request: {error}" for error in request_errors)
        if result["execution_id"] != request.get("execution_id"):
            errors.append("result execution_id does not match request")
    else:
        request = {}

    for label in ("source_data", "evidence_synthesis"):
        result_binding = result[label]
        request_binding_value = request.get(label, {})
        if not exact(result_binding, {"path", "sha256"}) or result_binding.get("path") != request_binding_value.get("path") or result_binding.get("sha256") != request_binding_value.get("sha256"):
            errors.append(f"result {label} binding does not match request")

    runtime = result["runtime"]
    runtime_fields = {"r_version", "rscript_path", "rscript_sha256", "package_versions", "adapter"}
    if not exact(runtime, runtime_fields):
        errors.append("result runtime fields are invalid")
    else:
        if runtime["r_version"] != request.get("runtime", {}).get("r_version") or runtime["package_versions"] != request.get("runtime", {}).get("package_versions"):
            errors.append("result runtime versions do not match request")
        if not text(runtime["rscript_path"]) or not isinstance(runtime["rscript_sha256"], str) or SHA256.fullmatch(runtime["rscript_sha256"]) is None:
            errors.append("result Rscript identity is invalid")
        adapter = runtime["adapter"]
        if not exact(adapter, {"path", "sha256"}) or adapter.get("sha256") != request.get("runtime", {}).get("adapter_sha256"):
            errors.append("result adapter binding does not match request")
        else:
            adapter_path = resolve_file(workspace, adapter["path"])
            if adapter_path is None or digest(adapter_path.read_bytes()) != adapter["sha256"]:
                errors.append("result adapter bytes are unavailable or changed")

    backend_outputs = result["backend_outputs"]
    required_backend_ids = {"matrix", "diagnostics", "local_inconsistency", "ranking", "warnings"}
    seen_backend_ids: set[str] = set()
    backend_paths: dict[str, Path] = {}
    if not isinstance(backend_outputs, list) or len(backend_outputs) != len(required_backend_ids):
        errors.append("backend_outputs must contain the exact fixed output set")
    else:
        for index, binding in enumerate(backend_outputs):
            if not exact(binding, {"id", "path", "sha256"}) or binding.get("id") not in required_backend_ids or binding.get("id") in seen_backend_ids:
                errors.append(f"backend_outputs[{index}] fields or ID are invalid")
                continue
            seen_backend_ids.add(binding["id"])
            path = resolve_file(workspace, binding["path"])
            if path is None or not isinstance(binding["sha256"], str) or SHA256.fullmatch(binding["sha256"]) is None or digest(path.read_bytes()) != binding["sha256"]:
                errors.append(f"backend_outputs[{index}] bytes are unavailable or changed")
            else:
                backend_paths[binding["id"]] = path
        if seen_backend_ids != required_backend_ids:
            errors.append("backend_outputs do not cover the exact fixed output set")

    network = result["network"]
    network_fields = {"treatments", "reference_treatment", "study_count", "direct_comparison_count", "cycle_rank", "connected"}
    if not exact(network, network_fields):
        errors.append("result network fields are invalid")
    else:
        expected_network = {
            "treatments": request_facts.get("treatment_order", []),
            "reference_treatment": request.get("reference_treatment"),
            "study_count": request_facts.get("study_count"),
            "direct_comparison_count": request_facts.get("direct_comparison_count"),
            "cycle_rank": request_facts.get("cycle_rank"),
            "connected": True,
        }
        if network != expected_network:
            errors.append("result network does not match current request and CSV")

    model = result["model"]
    model_fields = {"effect_measure", "scale", "likelihood", "link", "type", "tau_method", "tau", "tau_squared", "prediction_interval"}
    tau = 0.0
    if not exact(model, model_fields):
        errors.append("result model fields are invalid")
    else:
        requested_effect = request.get("effect", {})
        requested_model = request.get("model", {})
        if any((
            model["effect_measure"] != requested_effect.get("measure"),
            model["scale"] != requested_effect.get("scale"),
            model["likelihood"] != "normal",
            model["link"] != "identity",
            model["type"] != requested_model.get("type"),
            model["tau_method"] != requested_model.get("tau_method"),
            model["prediction_interval"] != requested_model.get("prediction_interval"),
        )):
            errors.append("result model does not match request")
        if not finite(model["tau"]) or float(model["tau"]) < 0 or not finite(model["tau_squared"]):
            errors.append("result tau must be finite and non-negative")
        else:
            tau = float(model["tau"])
            if not _number_close(model["tau_squared"], tau * tau):
                errors.append("result tau_squared does not equal tau squared")
            if requested_model.get("type") == "common" and tau != 0:
                errors.append("common model tau must be zero")

    try:
        expected_reference, expected_league = expected_rows(request, request_facts, tau)
    except (KeyError, TypeError, ValueError, OverflowError) as error:
        expected_reference, expected_league = [], []
        errors.append(f"independent WLS could not be evaluated: {error}")
    max_reference_error = _audit_estimate_rows(result["estimates_vs_reference"], expected_reference, ("treatment",), errors, "estimates_vs_reference")
    max_league_error = _audit_estimate_rows(result["league_table"], expected_league, ("treat1", "treat2"), errors, "league_table")

    prediction_required = request.get("model", {}).get("type") == "random"
    backend_reverse = None
    if "matrix" in backend_paths:
        backend_reverse = _audit_backend_matrix(
            backend_paths["matrix"],
            result,
            expected_league,
            str(request.get("reference_treatment", "")),
            prediction_required,
            errors,
        )
    for label in ("estimates_vs_reference", "league_table"):
        if isinstance(result[label], list):
            for index, row in enumerate(result[label]):
                if not isinstance(row, dict):
                    continue
                lower, upper = row.get("prediction_lower"), row.get("prediction_upper")
                if prediction_required:
                    if not finite(lower) or not finite(upper) or float(lower) > float(upper) or float(lower) > float(row.get("effect", math.nan)) or float(upper) < float(row.get("effect", math.nan)):
                        errors.append(f"{label}[{index}] requires a finite prediction interval containing the estimate")
                elif lower is not None or upper is not None:
                    errors.append(f"{label}[{index}] common model prediction interval must be null")

    heterogeneity = result["heterogeneity"]
    heterogeneity_fields = {"tau", "tau_squared", "q_total", "df_total", "p_total", "q_heterogeneity", "df_heterogeneity", "p_heterogeneity"}
    if not exact(heterogeneity, heterogeneity_fields) or heterogeneity.get("tau") != model.get("tau") or heterogeneity.get("tau_squared") != model.get("tau_squared"):
        errors.append("heterogeneity fields or tau binding are invalid")
    else:
        for field in ("q_total", "q_heterogeneity"):
            if not finite(heterogeneity[field]) or float(heterogeneity[field]) < 0:
                errors.append(f"heterogeneity.{field} must be finite and non-negative")
        for field in ("df_total", "df_heterogeneity"):
            if not isinstance(heterogeneity[field], int) or isinstance(heterogeneity[field], bool) or heterogeneity[field] < 0:
                errors.append(f"heterogeneity.{field} must be a non-negative integer")
        for field in ("p_total", "p_heterogeneity"):
            if heterogeneity[field] is not None and (not finite(heterogeneity[field]) or not 0 <= float(heterogeneity[field]) <= 1):
                errors.append(f"heterogeneity.{field} must be null or a probability")
    if "diagnostics" in backend_paths:
        _audit_backend_diagnostics(
            backend_paths["diagnostics"],
            result,
            int(request_facts.get("cycle_rank", 0)),
            errors,
        )

    inconsistency = result["inconsistency"]
    inconsistency_fields = {"global", "local"}
    if not exact(inconsistency, inconsistency_fields):
        errors.append("inconsistency fields are invalid")
    else:
        global_value = inconsistency["global"]
        global_fields = {"method", "status", "q", "df", "p_value"}
        cycle_rank = request_facts.get("cycle_rank", 0)
        expected_status = "estimable" if cycle_rank > 0 else "not_estimable_tree_network"
        if not exact(global_value, global_fields) or global_value.get("method") != "design_decomposition" or global_value.get("status") != expected_status:
            errors.append("global inconsistency diagnostic does not match network geometry")
        elif expected_status == "estimable":
            if not finite(global_value["q"]) or float(global_value["q"]) < 0 or not isinstance(global_value["df"], int) or global_value["df"] < 1 or not finite(global_value["p_value"]) or not 0 <= float(global_value["p_value"]) <= 1:
                errors.append("estimable global inconsistency values are invalid")
        elif any(global_value[field] is not None for field in ("q", "df", "p_value")):
            errors.append("tree-network global inconsistency values must be null")
        local = inconsistency["local"]
        if not isinstance(local, list):
            errors.append("local inconsistency must be an array")
        else:
            seen_comparisons: set[str] = set()
            for index, row in enumerate(local):
                fields = {"comparison", "network_effect", "direct_effect", "indirect_effect", "difference", "se_difference", "p_value"}
                if not exact(row, fields) or row["comparison"] not in request_facts.get("comparisons", []) or row["comparison"] in seen_comparisons:
                    errors.append(f"local inconsistency row {index} fields or comparison are invalid")
                    continue
                seen_comparisons.add(row["comparison"])
                if any(not finite(row[field]) for field in fields - {"comparison"}) or float(row["se_difference"]) <= 0 or not 0 <= float(row["p_value"]) <= 1:
                    errors.append(f"local inconsistency row {index} values are invalid")
                elif not _number_close(row["difference"], float(row["direct_effect"]) - float(row["indirect_effect"])):
                    errors.append(f"local inconsistency row {index} difference is not reproduced")
    if "local_inconsistency" in backend_paths:
        _audit_backend_local(
            backend_paths["local_inconsistency"],
            result,
            backend_reverse,
            list(request_facts.get("comparisons", [])),
            errors,
        )

    ranking = result["ranking"]
    if not exact(ranking, {"method", "rows"}) or ranking.get("method") != request.get("diagnostics", {}).get("ranking"):
        errors.append("ranking fields or method do not match request")
    elif ranking["method"] == "none":
        if ranking["rows"] != []:
            errors.append("ranking rows must be empty when ranking is none")
    else:
        rows_value = ranking["rows"]
        if not isinstance(rows_value, list) or len(rows_value) != len(request_facts.get("treatment_order", [])):
            errors.append("P-score ranking must cover every treatment")
        else:
            seen = set()
            for index, row in enumerate(rows_value):
                if not exact(row, {"treatment", "p_score"}) or row["treatment"] not in request_facts.get("treatment_order", []) or row["treatment"] in seen or not finite(row["p_score"]) or not 0 <= float(row["p_score"]) <= 1:
                    errors.append(f"ranking row {index} is invalid")
                    continue
                seen.add(row["treatment"])
    if "ranking" in backend_paths:
        _audit_backend_ranking(backend_paths["ranking"], result, errors)

    cross = result["cross_implementation"]
    expected_scope = "complete_common_effect" if request.get("model", {}).get("type") == "common" else "conditional_on_backend_tau"
    cross_fields = {"evaluator", "scope", "max_abs_reference_error", "max_abs_league_error", "tolerance", "passed"}
    if not exact(cross, cross_fields) or cross.get("evaluator") != EVALUATOR or cross.get("scope") != expected_scope or cross.get("tolerance") != TOLERANCE:
        errors.append("cross_implementation contract is invalid")
    else:
        if not _number_close(cross["max_abs_reference_error"], max_reference_error) or not _number_close(cross["max_abs_league_error"], max_league_error):
            errors.append("cross_implementation errors do not match independent WLS")
        expected_passed = max(max_reference_error, max_league_error) <= TOLERANCE
        if cross["passed"] is not expected_passed:
            errors.append("cross_implementation passed state is incorrect")

    if not isinstance(result["warnings"], list) or any(not text(item) for item in result["warnings"]):
        errors.append("warnings must be a string array")
    elif "warnings" in backend_paths:
        try:
            backend_warnings = [
                line.strip()
                for line in backend_paths["warnings"].read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (OSError, UnicodeError) as error:
            errors.append(f"backend warnings cannot be parsed: {error}")
        else:
            if result["warnings"] != backend_warnings:
                errors.append("warnings do not exactly preserve backend warnings")
    if result["limitations"] != request.get("limitations"):
        errors.append("result limitations must exactly preserve request limitations")
    if result["human_gate"] != request.get("human_gate"):
        errors.append("result human_gate must exactly preserve the request gate")

    complete = not errors
    return {
        "complete": complete,
        "eligible_for_review": complete and result.get("status") == "awaiting_model_review",
        "execution_id": result.get("execution_id", ""),
        "result_sha256": digest(result_raw),
        "request_sha256": digest(request_raw) if request_raw is not None else None,
        "treatment_count": len(request_facts.get("treatment_order", [])),
        "study_count": request_facts.get("study_count", 0),
        "cycle_rank": request_facts.get("cycle_rank", 0),
        "model_type": request.get("model", {}).get("type", ""),
        "tau": tau,
        "cross_implementation_scope": expected_scope,
        "errors": errors,
    }
