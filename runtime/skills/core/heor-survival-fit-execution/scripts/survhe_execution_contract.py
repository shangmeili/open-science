#!/usr/bin/env python3
"""Dependency-free contract and audit helpers for isolated survHE MLE runs."""

from __future__ import annotations

import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "0.1.0"
RESULT_SCHEMA_VERSION = "0.2.0"
LEGACY_RESULT_SCHEMA_VERSION = "0.1.0"
UNCERTAINTY_SCHEMA_VERSION = "0.1.0"
EVALUATOR = "ai4heor-survival-crosscheck@0.2.0"
SAFE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SAFE_COLUMN = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
VERSION = re.compile(r"^[0-9][0-9A-Za-z.+-]{0,63}$")
FAMILIES = {
    "exponential",
    "weibull",
    "gompertz",
    "gamma",
    "generalized_gamma",
    "generalized_f",
    "lognormal",
    "loglogistic",
}
REQUIRED_CROSSCHECKS = set(FAMILIES)
MANDATORY_FAMILIES = {"exponential", "weibull"}
PACKAGE_NAMES = {"survHE", "flexsurv", "survival"}
MAX_DATA_BYTES = 256 * 1024 * 1024
MAX_ROWS = 1_000_000

REQUEST_FIELDS = {
    "schema_version",
    "execution_id",
    "status",
    "analysis_target",
    "source_data",
    "fit",
    "runtime",
    "output",
    "limitations",
    "human_gate",
}
LEGACY_RESULT_FIELDS = {
    "schema_version",
    "execution_id",
    "status",
    "request",
    "source_data",
    "runtime",
    "model_order",
    "models",
    "diagnostics",
    "cross_implementation",
    "limitations",
    "human_gate",
}
RESULT_FIELDS = LEGACY_RESULT_FIELDS | {"parameter_uncertainty"}

PARAMETER_ORDERS = {
    "exponential": ("rate",),
    "weibull": ("shape", "scale"),
    "gompertz": ("shape", "rate"),
    "gamma": ("shape", "rate"),
    "generalized_gamma": ("mu", "sigma", "Q"),
    "generalized_f": ("mu", "sigma", "Q", "P"),
    "lognormal": ("meanlog", "sdlog"),
    "loglogistic": ("shape", "scale"),
}
INVERSE_TRANSFORMS = {
    "exponential": ("exp",),
    "weibull": ("exp", "exp"),
    "gompertz": ("identity", "exp"),
    "gamma": ("exp", "exp"),
    "generalized_gamma": ("identity", "exp", "identity"),
    "generalized_f": ("identity", "exp", "identity", "exp"),
    "lognormal": ("identity", "exp"),
    "loglogistic": ("exp", "exp"),
}


def exact(value: Any, fields: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == fields


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def finite(value: Any) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(float(value))


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def safe_relative(value: Any) -> bool:
    if not text(value):
        return False
    path = Path(value)
    return not path.is_absolute() and all(part not in {"", ".", ".."} for part in path.parts)


def resolve_workspace_file(workspace: Path, value: Any) -> Path | None:
    if not safe_relative(value):
        return None
    candidate = workspace / str(value)
    if candidate.is_symlink():
        return None
    resolved = candidate.resolve()
    root = workspace.resolve()
    return resolved if resolved.is_relative_to(root) and resolved.is_file() else None


def load_json(path: Path) -> tuple[dict[str, Any], bytes]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value, raw


def inspect_csv(path: Path, time_column: str, event_column: str) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if path.stat().st_size > MAX_DATA_BYTES:
        return {}, ["source_data file exceeds 256 MB"]
    row_count = event_count = censor_count = 0
    maximum_time = 0.0
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        if not lines or lines[0] != f"{time_column},{event_column}":
            return {}, ["source_data CSV must contain exactly the declared time and event columns in order"]
        for row_index, raw_line in enumerate(lines[1:], start=2):
            parts = raw_line.split(",")
            if len(parts) != 2 or any(part != part.strip() or not part for part in parts):
                errors.append(f"source_data row {row_index} must contain exactly two unquoted values")
                continue
            time_raw, event = parts
            row_count += 1
            if row_count > MAX_ROWS:
                errors.append("source_data CSV exceeds 1,000,000 rows")
                break
            try:
                time = float(time_raw)
            except (TypeError, ValueError):
                errors.append(f"source_data row {row_index} time must be numeric")
                continue
            if not math.isfinite(time) or time <= 0:
                errors.append(f"source_data row {row_index} time must be finite and positive")
            maximum_time = max(maximum_time, time)
            if event == "1":
                event_count += 1
            elif event == "0":
                censor_count += 1
            else:
                errors.append(f"source_data row {row_index} event must be exactly 0 or 1")
    except (OSError, UnicodeError) as error:
        errors.append(f"source_data CSV cannot be read: {error}")
    if row_count < 2:
        errors.append("source_data CSV must contain at least two observations")
    if event_count < 1:
        errors.append("source_data CSV must contain at least one event")
    return {
        "row_count": row_count,
        "event_count": event_count,
        "censor_count": censor_count,
        "maximum_time": maximum_time,
    }, errors


def validate_request(value: Any, workspace: Path) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    facts: dict[str, Any] = {}
    if not exact(value, REQUEST_FIELDS):
        return ["execution request fields are not the exact supported contract"], facts
    if value["schema_version"] != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    execution_id = value["execution_id"]
    if not isinstance(execution_id, str) or SAFE_ID.fullmatch(execution_id) is None:
        errors.append("execution_id must be a safe lowercase identifier")
    if value["status"] != "ready_for_execution":
        errors.append("status must be ready_for_execution")

    target = value["analysis_target"]
    if not exact(target, {"analysis_id", "path"}) or not all(text(target.get(field)) for field in ("analysis_id", "path")):
        errors.append("analysis_target must contain only non-empty analysis_id and path")

    source = value["source_data"]
    source_fields = {
        "classification",
        "execution_boundary",
        "format",
        "path",
        "sha256",
        "columns",
        "row_count",
        "event_count",
        "censor_count",
        "contains_direct_identifiers",
        "missing_policy",
        "additional_columns",
    }
    if not exact(source, source_fields):
        errors.append("source_data fields are invalid")
    else:
        if source["classification"] not in {"public", "non_sensitive", "restricted"}:
            errors.append("source_data.classification must be public, non_sensitive, or restricted")
        if source["execution_boundary"] != "local_only" or source["format"] != "csv":
            errors.append("source_data must be a local-only CSV")
        if source["contains_direct_identifiers"] is not False:
            errors.append("source_data containing direct identifiers is outside this contract")
        if source["missing_policy"] != "reject" or source["additional_columns"] != "reject":
            errors.append("source_data must reject missing values and additional columns")
        columns = source["columns"]
        if not exact(columns, {"time", "event"}) or any(
            not isinstance(columns.get(field), str) or SAFE_COLUMN.fullmatch(columns[field]) is None
            for field in ("time", "event")
        ) or columns.get("time") == columns.get("event"):
            errors.append("source_data.columns must name two distinct safe columns")
        path = resolve_workspace_file(workspace, source["path"])
        if path is None:
            errors.append("source_data.path must be a regular file inside the workspace")
        elif not isinstance(source["sha256"], str) or source["sha256"] != digest(path.read_bytes()):
            errors.append("source_data.sha256 does not match current bytes")
        elif exact(columns, {"time", "event"}):
            inspected, csv_errors = inspect_csv(path, columns["time"], columns["event"])
            errors.extend(csv_errors)
            facts.update(inspected)
            for field in ("row_count", "event_count", "censor_count"):
                if source[field] != inspected.get(field):
                    errors.append(f"source_data.{field} does not match the current CSV")
            facts["source_path"] = path

    fit = value["fit"]
    fit_fields = {
        "method",
        "formula",
        "candidate_models",
        "prediction_times",
        "observed_follow_up",
        "model_horizon",
        "cross_implementation_tolerance",
    }
    families: list[str] = []
    times: list[float] = []
    if not exact(fit, fit_fields):
        errors.append("fit fields are invalid")
    else:
        if fit["method"] != "maximum_likelihood" or fit["formula"] != "intercept_only":
            errors.append("the first slice supports only intercept-only maximum-likelihood fitting")
        candidates = fit["candidate_models"]
        if not isinstance(candidates, list) or not 2 <= len(candidates) <= 8:
            errors.append("candidate_models must contain 2-8 entries")
        else:
            for index, item in enumerate(candidates):
                if not exact(item, {"family", "rationale"}):
                    errors.append(f"candidate_models[{index}] fields are invalid")
                    continue
                family = item["family"]
                if family not in FAMILIES:
                    errors.append(f"candidate_models[{index}].family is unsupported")
                else:
                    families.append(family)
                if not text(item["rationale"]):
                    errors.append(f"candidate_models[{index}].rationale must be non-empty")
            if len(families) != len(set(families)):
                errors.append("candidate model families must be unique")
            if not MANDATORY_FAMILIES.issubset(families):
                errors.append("candidate_models must include exponential and weibull for independent cross-checking")
        raw_times = fit["prediction_times"]
        if not isinstance(raw_times, list) or not 3 <= len(raw_times) <= 256 or any(not finite(item) for item in raw_times):
            errors.append("prediction_times must contain 3-256 finite values")
        else:
            times = [float(item) for item in raw_times]
            if times[0] != 0 or any(right <= left for left, right in zip(times, times[1:])):
                errors.append("prediction_times must start at zero and be strictly increasing")
        observed = fit["observed_follow_up"]
        horizon = fit["model_horizon"]
        if not finite(observed) or float(observed) <= 0:
            errors.append("observed_follow_up must be positive")
        if not finite(horizon) or not finite(observed) or float(horizon) <= float(observed):
            errors.append("model_horizon must exceed observed_follow_up")
        if times and finite(observed) and finite(horizon):
            if not math.isclose(times[-1], float(horizon), rel_tol=0, abs_tol=1e-12):
                errors.append("prediction_times must end at model_horizon")
            if not any(0 < item <= float(observed) for item in times) or not any(
                float(observed) < item <= float(horizon) for item in times
            ):
                errors.append("prediction_times must cover observed and extrapolated periods")
        if finite(observed) and finite(facts.get("maximum_time")) and not math.isclose(
            float(observed), float(facts["maximum_time"]), rel_tol=0, abs_tol=1e-12
        ):
            errors.append("observed_follow_up must equal the maximum observed source time")
        tolerance = fit["cross_implementation_tolerance"]
        if not finite(tolerance) or not 1e-12 <= float(tolerance) <= 1e-6:
            errors.append("cross_implementation_tolerance must be between 1e-12 and 1e-6")

    runtime = value["runtime"]
    if not exact(runtime, {"expected_packages"}) or not exact(runtime.get("expected_packages"), PACKAGE_NAMES):
        errors.append("runtime.expected_packages must contain exactly survHE, flexsurv, and survival")
    elif any(not isinstance(version, str) or VERSION.fullmatch(version) is None for version in runtime["expected_packages"].values()):
        errors.append("runtime.expected_packages must declare exact non-empty versions")

    output = value["output"]
    expected_directory = f"heor/survival-fit-executions/{execution_id}"
    if not exact(output, {"directory", "overwrite_policy"}) or output.get("directory") != expected_directory:
        errors.append(f"output.directory must be {expected_directory}")
    elif output.get("overwrite_policy") != "fail_if_exists":
        errors.append("output.overwrite_policy must be fail_if_exists")

    limitations = value["limitations"]
    if not isinstance(limitations, list) or not limitations or any(not text(item) for item in limitations):
        errors.append("limitations must contain non-empty strings")
    gate = value["human_gate"]
    expected_gate = {
        "state": "awaiting_execution_authorization",
        "required_action": "approve_local_survival_fit_command",
    }
    if gate != expected_gate:
        errors.append("human_gate must remain awaiting local execution authorization")

    forbidden = re.compile(r'"(?:approved|accepted|selected|reviewer_signature|approval_timestamp)"\s*:')
    if forbidden.search(json.dumps(value, sort_keys=True)):
        errors.append("execution request contains a forbidden authority field")
    facts.update({"families": families, "prediction_times": times})
    return errors, facts


def _parameter_map(model: dict[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    for item in model.get("parameters", []):
        if exact(item, {"name", "estimate"}) and text(item["name"]) and finite(item["estimate"]):
            result[item["name"]] = float(item["estimate"])
    return result


def expected_curve(family: str, parameters: dict[str, float], time: float) -> tuple[float, float | None]:
    from parametric_survival import curve

    return curve(family, parameters, time)


def expected_parameterization(family: str) -> str:
    from parametric_survival import PARAMETERIZATIONS

    return PARAMETERIZATIONS[family]


def _bound_file(workspace: Path, path: Any, sha256: Any, label: str, errors: list[str]) -> Path | None:
    candidate = resolve_workspace_file(workspace, path)
    if candidate is None:
        errors.append(f"{label} path is missing or outside the workspace")
        return None
    if not isinstance(sha256, str) or sha256 != digest(candidate.read_bytes()):
        errors.append(f"{label} SHA-256 does not match current bytes")
        return None
    return candidate


def _positive_definite(matrix: list[list[float]]) -> bool:
    """Dependency-free Cholesky check for a finite symmetric matrix."""
    size = len(matrix)
    lower = [[0.0] * size for _ in range(size)]
    for row in range(size):
        for column in range(row + 1):
            subtotal = sum(lower[row][index] * lower[column][index] for index in range(column))
            if row == column:
                diagonal = matrix[row][row] - subtotal
                if not math.isfinite(diagonal) or diagonal <= 0:
                    return False
                lower[row][column] = math.sqrt(diagonal)
            else:
                divisor = lower[column][column]
                if divisor <= 0:
                    return False
                lower[row][column] = (matrix[row][column] - subtotal) / divisor
    return True


def audit_parameter_uncertainty_artifact(
    artifact: Any,
    family: str,
    source_path: str,
    source_sha256: str,
    source_model: dict[str, Any],
    errors: list[str],
    label: str,
) -> bool:
    fields = {
        "schema_version",
        "family",
        "status",
        "source_model",
        "estimation_scale",
        "parameter_order",
        "estimates",
        "covariance_matrix",
        "inverse_transforms",
        "covariance_method",
        "sampling_distribution",
        "sampling_scope",
        "reason",
        "limitations",
    }
    if not exact(artifact, fields):
        errors.append(f"{label} fields are invalid")
        return False
    if artifact["schema_version"] != UNCERTAINTY_SCHEMA_VERSION or artifact["family"] != family:
        errors.append(f"{label} schema or family is invalid")
        return False
    if artifact["source_model"] != {"path": source_path, "sha256": source_sha256}:
        errors.append(f"{label} source_model binding is invalid")
    if artifact["sampling_scope"] != "within_one_absolute_curve_only":
        errors.append(f"{label} sampling_scope must remain within one absolute curve")
    limitations = artifact["limitations"]
    if not isinstance(limitations, list) or not limitations or any(not text(item) for item in limitations):
        errors.append(f"{label} limitations must contain non-empty strings")

    status = artifact["status"]
    if status == "unavailable":
        expected_empty = {
            "estimation_scale": None,
            "parameter_order": [],
            "estimates": [],
            "covariance_matrix": [],
            "inverse_transforms": [],
            "covariance_method": None,
            "sampling_distribution": None,
        }
        if any(artifact[field] != value for field, value in expected_empty.items()) or not text(artifact["reason"]):
            errors.append(f"{label} unavailable payload is invalid")
        return False
    if status != "available":
        errors.append(f"{label} status is invalid")
        return False
    if artifact["reason"] is not None:
        errors.append(f"{label} available artifact must have null reason")
    if artifact["estimation_scale"] != "unconstrained_real_line":
        errors.append(f"{label} estimation_scale is invalid")
    if artifact["covariance_method"] != "inverse_observed_hessian":
        errors.append(f"{label} covariance_method is invalid")
    if artifact["sampling_distribution"] != "asymptotic_multivariate_normal":
        errors.append(f"{label} sampling_distribution is invalid")

    order = artifact["parameter_order"]
    estimates = artifact["estimates"]
    transforms = artifact["inverse_transforms"]
    matrix = artifact["covariance_matrix"]
    expected_order = list(PARAMETER_ORDERS[family])
    expected_transforms = list(INVERSE_TRANSFORMS[family])
    if order != expected_order or transforms != expected_transforms:
        errors.append(f"{label} parameter order or inverse transforms do not match the admitted family")
        return False
    size = len(expected_order)
    if not isinstance(estimates, list) or len(estimates) != size or any(not finite(value) for value in estimates):
        errors.append(f"{label} estimates are invalid")
        return False
    if (
        not isinstance(matrix, list)
        or len(matrix) != size
        or any(not isinstance(row, list) or len(row) != size or any(not finite(value) for value in row) for row in matrix)
    ):
        errors.append(f"{label} covariance_matrix is invalid")
        return False
    numeric_matrix = [[float(value) for value in row] for row in matrix]
    if any(abs(numeric_matrix[row][column] - numeric_matrix[column][row]) > 1e-10 for row in range(size) for column in range(size)):
        errors.append(f"{label} covariance_matrix is not symmetric")
    elif not _positive_definite(numeric_matrix):
        errors.append(f"{label} covariance_matrix is not positive definite")

    natural = _parameter_map(source_model)
    if list(natural) != expected_order:
        errors.append(f"{label} source model parameter order is invalid")
    else:
        for name, estimate, transform in zip(expected_order, estimates, transforms):
            transformed = math.exp(float(estimate)) if transform == "exp" else float(estimate)
            if not math.isclose(transformed, natural[name], rel_tol=1e-10, abs_tol=1e-12):
                errors.append(f"{label} inverse transform does not reproduce source model parameter {name}")
    return not any(item.startswith(label) for item in errors)


def audit_result(manifest_path: Path, workspace: Path) -> dict[str, Any]:
    errors: list[str] = []
    try:
        manifest, _ = load_json(manifest_path)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        return {"complete": False, "eligible_for_review": False, "errors": [str(error)]}
    result_schema = manifest.get("schema_version")
    expected_result_fields = RESULT_FIELDS if result_schema == RESULT_SCHEMA_VERSION else LEGACY_RESULT_FIELDS
    if not exact(manifest, expected_result_fields):
        return {"complete": False, "eligible_for_review": False, "errors": ["result fields are not the exact contract"]}
    if result_schema not in {LEGACY_RESULT_SCHEMA_VERSION, RESULT_SCHEMA_VERSION}:
        errors.append(
            f"result schema_version must be {LEGACY_RESULT_SCHEMA_VERSION} or {RESULT_SCHEMA_VERSION}"
        )
    execution_id = manifest["execution_id"]
    if not isinstance(execution_id, str) or SAFE_ID.fullmatch(execution_id) is None:
        errors.append("result execution_id is invalid")
    if manifest["status"] not in {"execution_complete", "execution_complete_with_model_failures", "cross_implementation_failed"}:
        errors.append("result status is not an admitted completed execution state")

    request_binding = manifest["request"]
    request: dict[str, Any] = {}
    request_facts: dict[str, Any] = {}
    request_path: Path | None = None
    if not exact(request_binding, {"path", "sha256"}):
        errors.append("request binding fields are invalid")
    else:
        request_path = _bound_file(workspace, request_binding["path"], request_binding["sha256"], "request", errors)
    if request_path is not None:
        try:
            request, _ = load_json(request_path)
            request_errors, request_facts = validate_request(request, workspace)
            errors.extend(f"request: {item}" for item in request_errors)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
            errors.append(f"request cannot be loaded: {error}")
    if request and manifest["execution_id"] != request.get("execution_id"):
        errors.append("result execution_id does not match request")

    source = manifest["source_data"]
    if not exact(source, {"path", "sha256", "row_count", "event_count", "censor_count"}):
        errors.append("result source_data fields are invalid")
    elif request:
        requested_source = request["source_data"]
        if source != {field: requested_source[field] for field in source}:
            errors.append("result source_data does not exactly copy the request binding and counts")

    runtime = manifest["runtime"]
    runtime_fields = {
        "backend",
        "method",
        "r_version",
        "rscript_sha256",
        "package_versions",
        "adapter_path",
        "adapter_sha256",
        "session_info_path",
        "session_info_sha256",
        "execution_log_path",
        "execution_log_sha256",
    }
    if not exact(runtime, runtime_fields):
        errors.append("result runtime fields are invalid")
    else:
        if runtime["backend"] != "survHE" or runtime["method"] != "maximum_likelihood":
            errors.append("result runtime must be survHE maximum_likelihood")
        if not text(runtime["r_version"]) or not isinstance(runtime["rscript_sha256"], str) or SHA256.fullmatch(runtime["rscript_sha256"]) is None:
            errors.append("result runtime must record R version and Rscript SHA-256")
        if request and runtime["package_versions"] != request["runtime"]["expected_packages"]:
            errors.append("result package_versions do not match the pre-specified request")
        _bound_file(workspace, runtime["adapter_path"], runtime["adapter_sha256"], "adapter", errors)
        _bound_file(workspace, runtime["session_info_path"], runtime["session_info_sha256"], "session info", errors)
        _bound_file(workspace, runtime["execution_log_path"], runtime["execution_log_sha256"], "execution log", errors)

    model_order = manifest["model_order"]
    expected_order = request_facts.get("families", [])
    if not isinstance(model_order, list) or model_order != expected_order:
        errors.append("model_order must exactly match the request candidate order")
        model_order = []
    model_bindings = manifest["models"]
    models: dict[str, dict[str, Any]] = {}
    converged = 0
    if not isinstance(model_bindings, list) or len(model_bindings) != len(model_order):
        errors.append("models must bind exactly one output per requested family")
    else:
        for index, binding in enumerate(model_bindings):
            label = f"models[{index}]"
            if not exact(binding, {"family", "status", "path", "sha256"}) or binding["family"] != model_order[index]:
                errors.append(f"{label} binding is invalid or out of order")
                continue
            path = _bound_file(workspace, binding["path"], binding["sha256"], label, errors)
            if path is None:
                continue
            try:
                model, _ = load_json(path)
            except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
                errors.append(f"{label} cannot be loaded: {error}")
                continue
            model_fields = {
                "schema_version",
                "family",
                "status",
                "fit_statistics",
                "parameterization",
                "parameters",
                "landmarks",
                "warnings",
            }
            if not exact(model, model_fields) or model.get("schema_version") != SCHEMA_VERSION or model.get("family") != binding["family"] or model.get("status") != binding["status"]:
                errors.append(f"{label} model fields or identity are invalid")
                continue
            if not isinstance(model["warnings"], list) or any(not text(item) for item in model["warnings"]):
                errors.append(f"{label}.warnings must contain only non-empty strings")
            if model["status"] == "failed":
                if model["fit_statistics"] != {"aic": None, "bic": None, "log_likelihood": None} or model["parameters"] != [] or model["landmarks"] != []:
                    errors.append(f"{label} failed model must not contain fit values")
                models[binding["family"]] = model
                continue
            if model["status"] != "converged":
                errors.append(f"{label}.status must be converged or failed")
                continue
            converged += 1
            statistics = model["fit_statistics"]
            if not exact(statistics, {"aic", "bic", "log_likelihood"}) or any(not finite(statistics.get(field)) for field in statistics):
                errors.append(f"{label}.fit_statistics must be finite")
            if model["parameterization"] != expected_parameterization(binding["family"]):
                errors.append(f"{label}.parameterization does not match the admitted natural scale")
            parameters = _parameter_map(model)
            if len(parameters) != len(model["parameters"]):
                errors.append(f"{label}.parameters must contain unique finite named estimates")
            landmarks = model["landmarks"]
            expected_times = request_facts.get("prediction_times", [])
            if not isinstance(landmarks, list) or len(landmarks) != len(expected_times):
                errors.append(f"{label}.landmarks must cover every requested prediction time")
            else:
                previous_survival = 1.0
                for landmark_index, (landmark, expected_time) in enumerate(zip(landmarks, expected_times)):
                    landmark_label = f"{label}.landmarks[{landmark_index}]"
                    if not exact(landmark, {"time", "survival", "hazard"}) or not finite(landmark["time"]) or not math.isclose(float(landmark["time"]), expected_time, rel_tol=0, abs_tol=1e-12):
                        errors.append(f"{landmark_label}.time does not match the request")
                        continue
                    survival = landmark["survival"]
                    hazard = landmark["hazard"]
                    if not finite(survival) or not 0 <= float(survival) <= previous_survival + 1e-12:
                        errors.append(f"{landmark_label}.survival is invalid")
                    if expected_time == 0:
                        if survival != 1 or hazard is not None:
                            errors.append(f"{landmark_label} must start at survival 1 with null hazard")
                    elif not finite(hazard) or float(hazard) < 0:
                        errors.append(f"{landmark_label}.hazard must be finite and non-negative after time zero")
                    if finite(survival):
                        previous_survival = float(survival)
                if binding["family"] in REQUIRED_CROSSCHECKS:
                    try:
                        tolerance = float(request["fit"]["cross_implementation_tolerance"])
                        for landmark in landmarks:
                            expected_survival, expected_hazard = expected_curve(binding["family"], parameters, float(landmark["time"]))
                            if abs(float(landmark["survival"]) - expected_survival) > tolerance:
                                errors.append(f"{label} survival exceeds independent cross-check tolerance")
                                break
                            if expected_hazard is not None and abs(float(landmark["hazard"]) - expected_hazard) > tolerance:
                                errors.append(f"{label} hazard exceeds independent cross-check tolerance")
                                break
                    except (KeyError, TypeError, ValueError) as error:
                        errors.append(f"{label} cannot be independently evaluated: {error}")
            models[binding["family"]] = model

    parameter_uncertainty_complete = False
    if result_schema == RESULT_SCHEMA_VERSION:
        uncertainty = manifest["parameter_uncertainty"]
        uncertainty_fields = {
            "artifact_schema_version",
            "scope",
            "joint_curve_draw_authority",
            "bindings",
            "complete",
        }
        available_families: set[str] = set()
        if not exact(uncertainty, uncertainty_fields):
            errors.append("parameter_uncertainty fields are invalid")
        else:
            if uncertainty["artifact_schema_version"] != UNCERTAINTY_SCHEMA_VERSION:
                errors.append("parameter_uncertainty artifact_schema_version is invalid")
            if uncertainty["scope"] != "within_model_curve_only" or uncertainty["joint_curve_draw_authority"] is not False:
                errors.append("parameter_uncertainty scope or joint authority is invalid")
            bindings = uncertainty["bindings"]
            if not isinstance(bindings, list) or len(bindings) != len(model_order):
                errors.append("parameter_uncertainty must bind every requested family in order")
            else:
                for index, (binding, family) in enumerate(zip(bindings, model_order)):
                    label = f"parameter_uncertainty.bindings[{index}]"
                    model = models.get(family, {})
                    model_binding = model_bindings[index] if isinstance(model_bindings, list) and index < len(model_bindings) else {}
                    if not exact(binding, {"family", "status", "path", "sha256"}) or binding.get("family") != family:
                        errors.append(f"{label} is invalid or out of order")
                        continue
                    if model.get("status") == "failed":
                        if binding != {"family": family, "status": "fit_failed", "path": None, "sha256": None}:
                            errors.append(f"{label} must record the failed fit without an artifact")
                        continue
                    if binding.get("status") not in {"available", "unavailable"}:
                        errors.append(f"{label} status is invalid")
                        continue
                    path = _bound_file(workspace, binding.get("path"), binding.get("sha256"), label, errors)
                    if path is None:
                        continue
                    try:
                        artifact, _ = load_json(path)
                    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
                        errors.append(f"{label} cannot be loaded: {error}")
                        continue
                    if artifact.get("status") != binding.get("status"):
                        errors.append(f"{label} status does not match the artifact")
                        continue
                    if audit_parameter_uncertainty_artifact(
                        artifact,
                        family,
                        str(model_binding.get("path", "")),
                        str(model_binding.get("sha256", "")),
                        model,
                        errors,
                        label,
                    ):
                        available_families.add(family)
            converged_families = {family for family, model in models.items() if model.get("status") == "converged"}
            parameter_uncertainty_complete = bool(converged_families) and available_families == converged_families
            if uncertainty.get("complete") is not parameter_uncertainty_complete:
                errors.append("parameter_uncertainty.complete does not match audited artifacts")

    diagnostics = manifest["diagnostics"]
    diagnostic_fields = {
        "km_overlay_path",
        "km_overlay_sha256",
        "log_cumulative_hazard_path",
        "log_cumulative_hazard_sha256",
        "hazard_plot_path",
        "hazard_plot_sha256",
    }
    if not exact(diagnostics, diagnostic_fields):
        errors.append("diagnostics fields are invalid")
    else:
        for path_field, hash_field, label in (
            ("km_overlay_path", "km_overlay_sha256", "KM overlay"),
            ("log_cumulative_hazard_path", "log_cumulative_hazard_sha256", "log-cumulative-hazard plot"),
            ("hazard_plot_path", "hazard_plot_sha256", "hazard plot"),
        ):
            _bound_file(workspace, diagnostics[path_field], diagnostics[hash_field], label, errors)

    cross = manifest["cross_implementation"]
    cross_complete = False
    if not exact(cross, {"evaluator", "tolerance", "checks", "complete"}):
        errors.append("cross_implementation fields are invalid")
    else:
        if cross["evaluator"] != EVALUATOR or not finite(cross["tolerance"]):
            errors.append("cross_implementation evaluator or tolerance is invalid")
        elif request and float(cross["tolerance"]) != float(request["fit"]["cross_implementation_tolerance"]):
            errors.append("cross_implementation tolerance does not match request")
        checks = cross["checks"]
        if not isinstance(checks, list) or len(checks) != len(model_order):
            errors.append("cross_implementation must contain one ordered check per model")
        else:
            expected_statuses: list[str] = []
            for family in model_order:
                model = models.get(family, {})
                if model.get("status") == "failed":
                    expected_statuses.append("fit_failed")
                else:
                    expected_statuses.append("passed")
            for index, (check, family, expected_status) in enumerate(zip(checks, model_order, expected_statuses)):
                if expected_status == "passed" and check.get("status") == "failed":
                    expected_status = "failed"
                if not exact(check, {"family", "status", "max_abs_survival_error", "max_abs_hazard_error"}) or check.get("family") != family or check.get("status") != expected_status:
                    errors.append(f"cross_implementation.checks[{index}] is invalid")
                    continue
                if expected_status == "passed" and any(not finite(check[field]) for field in ("max_abs_survival_error", "max_abs_hazard_error")):
                    errors.append(f"cross_implementation.checks[{index}] errors must be finite")
                if expected_status == "fit_failed" and any(check[field] is not None for field in ("max_abs_survival_error", "max_abs_hazard_error")):
                    errors.append(f"cross_implementation.checks[{index}] fit-failed errors must be null")
                if expected_status == "failed":
                    failed_values = [check[field] for field in ("max_abs_survival_error", "max_abs_hazard_error")]
                    if not (all(value is None for value in failed_values) or all(finite(value) for value in failed_values)):
                        errors.append(f"cross_implementation.checks[{index}] failed errors must be both finite or both null")
            passed_families = {
                family
                for family, check in zip(model_order, checks)
                if check.get("status") == "passed"
                and finite(check.get("max_abs_survival_error"))
                and finite(check.get("max_abs_hazard_error"))
                and float(check["max_abs_survival_error"]) <= float(cross["tolerance"])
                and float(check["max_abs_hazard_error"]) <= float(cross["tolerance"])
            }
            cross_complete = MANDATORY_FAMILIES.issubset(passed_families) and all(
                models.get(family, {}).get("status") == "failed" or family in passed_families
                for family in model_order
            )
        if cross.get("complete") is not cross_complete:
            errors.append("cross_implementation.complete does not match the audited checks")

    failed_models = len(model_order) - converged
    expected_result_status = "cross_implementation_failed" if not cross_complete else (
        "execution_complete_with_model_failures" if failed_models else "execution_complete"
    )
    if manifest["status"] != expected_result_status:
        errors.append("result status does not match model convergence")

    if not isinstance(manifest["limitations"], list) or not manifest["limitations"] or any(not text(item) for item in manifest["limitations"]):
        errors.append("result limitations must contain non-empty strings")
    expected_gate = {"state": "awaiting_human_review", "required_action": "review_survival_extrapolation"}
    if manifest["human_gate"] != expected_gate:
        errors.append("result human_gate must remain awaiting survival extrapolation review")
    forbidden = re.compile(r'"(?:approved|accepted|selected|reviewer_signature|approval_timestamp)"\s*:')
    if forbidden.search(json.dumps(manifest, sort_keys=True)):
        errors.append("result contains a forbidden authority field")

    eligible = not errors and cross_complete and converged >= 2
    return {
        "complete": not errors,
        "eligible_for_review": eligible,
        "errors": errors,
        "candidate_models": len(model_order),
        "converged_models": converged,
        "cross_implementation_complete": cross_complete,
        "parameter_uncertainty_complete": parameter_uncertainty_complete,
    }
