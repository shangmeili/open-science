#!/usr/bin/env python3
"""Fail-closed contracts for paired patient-row survival bootstrap execution."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, Iterator


REQUEST_SCHEMA_VERSION = "0.1.0"
RESULT_SCHEMA_VERSION = "0.1.0"
PLAN_FORMAT = "ai4heor-stratified-patient-bootstrap-frequencies-csv@0.1.0"
REPLICATE_FORMAT = "ai4heor-paired-survival-bootstrap-replicates-jsonl@0.1.0"
DRAW_FORMAT = "ai4heor-joint-survival-draws-jsonl@0.1.0"
RNG_ALGORITHM = "pcg32-xsh-rr"
RNG_VERSION = "1"
EVALUATOR = "ai4heor-parametric-survival@0.2.0"
EVALUATOR_PATH = Path(__file__).resolve().parents[2] / "heor-survival-fit-execution" / "scripts" / "parametric_survival.py"
ADAPTER_PATH = Path(__file__).with_name("paired_survival_bootstrap_adapter.R")
SAFE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SAFE_SUBJECT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
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
PACKAGE_NAMES = {"survHE", "flexsurv", "survival"}
SOURCE_COLUMNS = [
    "subject_id",
    "strategy_id",
    "pfs_time",
    "pfs_event",
    "os_time",
    "os_event",
]
MAX_SOURCE_BYTES = 256 * 1024 * 1024
MAX_SOURCE_ROWS = 100_000
MAX_BOOTSTRAP_SELECTIONS = 5_000_000
MAX_DRAW_CELLS = 5_000_000
MAX_RESULT_BYTES = 128 * 1024 * 1024
MAX_LINE_BYTES = 2 * 1024 * 1024
TOLERANCE = 1e-9


REQUEST_FIELDS = {
    "schema_version",
    "execution_id",
    "status",
    "analysis",
    "partitioned_survival",
    "curve_materializations",
    "source_data",
    "bootstrap",
    "runtime",
    "output",
    "limitations",
    "human_gate",
}
RESULT_FIELDS = {
    "schema_version",
    "execution_id",
    "status",
    "request",
    "analysis",
    "partitioned_survival",
    "curve_materializations",
    "source_data",
    "runtime",
    "bootstrap",
    "limitations",
    "human_gate",
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


def bootstrap_frequencies(strategy_positions: list[list[int]], iterations: int, seed: int) -> Iterator[list[int]]:
    """Yield one fixed-size stratified whole-row frequency vector per replicate."""

    row_count = sum(len(positions) for positions in strategy_positions)
    rng = Pcg32(seed)
    for _ in range(iterations):
        frequencies = [0] * row_count
        for positions in strategy_positions:
            for _ in positions:
                frequencies[positions[rng.bounded(len(positions))]] += 1
        yield frequencies


def inspect_source(path: Path, strategy_order: list[str]) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    if path.stat().st_size > MAX_SOURCE_BYTES:
        return {}, ["source_data exceeds 256 MB"]
    counts = {strategy: 0 for strategy in strategy_order}
    endpoint_counts = {
        strategy: {"pfs_events": 0, "pfs_censored": 0, "os_events": 0, "os_censored": 0}
        for strategy in strategy_order
    }
    positions = {strategy: [] for strategy in strategy_order}
    subjects: set[str] = set()
    row_count = 0
    maximum_time = 0.0
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            try:
                header = next(reader)
            except StopIteration:
                return {}, ["source_data CSV is empty"]
            if header != SOURCE_COLUMNS:
                return {}, ["source_data CSV must contain exactly the six fixed columns in order"]
            for line_number, row in enumerate(reader, start=2):
                if len(row) != len(SOURCE_COLUMNS) or any(not value or value != value.strip() for value in row):
                    errors.append(f"source_data row {line_number} must contain six non-empty unpadded values")
                    continue
                subject_id, strategy, pfs_raw, pfs_event, os_raw, os_event = row
                row_count += 1
                if row_count > MAX_SOURCE_ROWS:
                    errors.append("source_data exceeds 100,000 rows")
                    break
                if SAFE_SUBJECT.fullmatch(subject_id) is None:
                    errors.append(f"source_data row {line_number} subject_id is not a safe pseudonymous identifier")
                elif subject_id in subjects:
                    errors.append(f"source_data row {line_number} repeats subject_id")
                subjects.add(subject_id)
                if strategy not in counts:
                    errors.append(f"source_data row {line_number} strategy_id is outside strategy_order")
                    continue
                try:
                    pfs_time = float(pfs_raw)
                    os_time = float(os_raw)
                except ValueError:
                    errors.append(f"source_data row {line_number} times must be numeric")
                    continue
                if not all(math.isfinite(value) and value > 0 for value in (pfs_time, os_time)):
                    errors.append(f"source_data row {line_number} times must be finite and positive")
                if pfs_time > os_time + TOLERANCE:
                    errors.append(f"source_data row {line_number} has PFS time after OS time")
                if pfs_event not in {"0", "1"} or os_event not in {"0", "1"}:
                    errors.append(f"source_data row {line_number} event indicators must be exactly 0 or 1")
                    continue
                positions[strategy].append(row_count - 1)
                counts[strategy] += 1
                endpoint_counts[strategy]["pfs_events" if pfs_event == "1" else "pfs_censored"] += 1
                endpoint_counts[strategy]["os_events" if os_event == "1" else "os_censored"] += 1
                maximum_time = max(maximum_time, pfs_time, os_time)
    except (OSError, UnicodeError, csv.Error) as error:
        errors.append(f"source_data CSV cannot be read: {error}")
    if row_count < 2:
        errors.append("source_data must contain at least two subjects")
    for strategy in strategy_order:
        if counts[strategy] < 2:
            errors.append(f"source_data strategy {strategy} must contain at least two subjects")
        for endpoint in ("pfs", "os"):
            if endpoint_counts[strategy][f"{endpoint}_events"] < 1:
                errors.append(f"source_data strategy {strategy} {endpoint} must contain at least one event")
    return {
        "row_count": row_count,
        "strategy_counts": counts,
        "endpoint_counts": endpoint_counts,
        "strategy_positions": [positions[strategy] for strategy in strategy_order],
        "maximum_time": maximum_time,
    }, errors


def _bound_json(workspace: Path, binding: Any, expected_path: str, label: str, errors: list[str]) -> tuple[dict[str, Any], bytes] | None:
    if not exact(binding, {"path", "sha256", "id"}) or binding.get("path") != expected_path:
        errors.append(f"{label} binding fields or path are invalid")
        return None
    path = resolve_workspace_file(workspace, expected_path)
    if path is None:
        errors.append(f"{label} path is missing or unsafe")
        return None
    raw = path.read_bytes()
    if binding.get("sha256") != digest(raw):
        errors.append(f"{label} SHA-256 does not match current bytes")
        return None
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        errors.append(f"{label} is not valid JSON")
        return None
    if not isinstance(value, dict):
        errors.append(f"{label} must contain an object")
        return None
    return value, raw


def _materialized_curve_order(materializations: dict[str, Any], strategy_order: list[str]) -> tuple[list[dict[str, str]], list[str]]:
    errors: list[str] = []
    curves = materializations.get("curves")
    if not isinstance(curves, list):
        return [], ["curve materializations must contain a curves array"]
    by_target: dict[str, dict[str, Any]] = {}
    for curve in curves:
        if not isinstance(curve, dict) or not text(curve.get("target_path")):
            errors.append("curve materializations contain an invalid curve")
            continue
        by_target[curve["target_path"]] = curve
    result: list[dict[str, str]] = []
    for strategy in strategy_order:
        for endpoint in ("pfs", "os"):
            target = f"partitioned_survival.strategies.{strategy}.{endpoint}"
            curve = by_target.get(target)
            family = curve.get("family") if curve else None
            if curve is None or family not in FAMILIES or curve.get("strategy_id") != strategy or curve.get("endpoint") != endpoint:
                errors.append(f"curve materializations do not contain a valid selected curve for {target}")
                continue
            result.append({"target_path": target, "strategy_id": strategy, "endpoint": endpoint, "family": family})
    if len(by_target) != len(result):
        errors.append("curve materializations contain targets outside the exact strategy PFS/OS order")
    return result, errors


def validate_request(value: Any, workspace: Path) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    facts: dict[str, Any] = {}
    if not exact(value, REQUEST_FIELDS):
        return ["bootstrap request fields are not the exact supported contract"], facts
    if value["schema_version"] != REQUEST_SCHEMA_VERSION:
        errors.append(f"schema_version must be {REQUEST_SCHEMA_VERSION}")
    execution_id = value["execution_id"]
    if not isinstance(execution_id, str) or SAFE_ID.fullmatch(execution_id) is None:
        errors.append("execution_id must be a safe lowercase identifier")
    if value["status"] != "ready_for_execution":
        errors.append("status must be ready_for_execution")

    analysis_bound = _bound_json(workspace, value["analysis"], "heor/analysis-plan.json", "analysis", errors)
    psm_bound = _bound_json(
        workspace,
        value["partitioned_survival"],
        "heor/partitioned-survival-plan.json",
        "partitioned_survival",
        errors,
    )
    material_bound = _bound_json(
        workspace,
        value["curve_materializations"],
        "heor/survival-curve-materializations.json",
        "curve_materializations",
        errors,
    )
    strategy_order: list[str] = []
    grid: list[float] = []
    expected_curves: list[dict[str, str]] = []
    if analysis_bound:
        analysis, analysis_raw = analysis_bound
        strategy_order = analysis.get("strategy_order") if isinstance(analysis.get("strategy_order"), list) else []
        if analysis.get("schema_version") != "0.15.0" or not strategy_order or any(
            not isinstance(item, str) or SAFE_ID.fullmatch(item) is None for item in strategy_order
        ) or len(strategy_order) != len(set(strategy_order)):
            errors.append("analysis must be current schema 0.15.0 with a valid unique strategy_order")
        if value["analysis"].get("id") != analysis.get("analysis_id"):
            errors.append("analysis.id does not match current analysis_id")
        cycles = analysis.get("cycles")
        cycle_length = analysis.get("cycle_length_years")
        if isinstance(cycles, bool) or not isinstance(cycles, int) or cycles < 1 or not finite(cycle_length) or float(cycle_length) <= 0:
            errors.append("analysis cycle grid is invalid")
        else:
            grid = [index * float(cycle_length) for index in range(cycles + 1)]
        facts.update({"analysis": analysis, "analysis_raw": analysis_raw})
    if psm_bound:
        psm, psm_raw = psm_bound
        if psm.get("schema_version") != "0.7.0" or value["partitioned_survival"].get("id") != psm.get("psm_id"):
            errors.append("partitioned survival must be current schema 0.7.0 with a matching psm_id")
        if analysis_bound and psm.get("analysis_id") != analysis_bound[0].get("analysis_id"):
            errors.append("partitioned survival analysis_id does not match the current analysis")
        facts.update({"psm": psm, "psm_raw": psm_raw})
    if material_bound:
        materializations, material_raw = material_bound
        if materializations.get("schema_version") != "0.2.0" or value["curve_materializations"].get("id") != materializations.get("materialization_id"):
            errors.append("curve materializations must be schema 0.2.0 with a matching materialization_id")
        expected_curves, curve_errors = _materialized_curve_order(materializations, strategy_order)
        errors.extend(curve_errors)
        facts.update({"materializations": materializations, "materializations_raw": material_raw})

    source = value["source_data"]
    source_fields = {
        "classification",
        "execution_boundary",
        "format",
        "path",
        "sha256",
        "columns",
        "row_count",
        "strategy_counts",
        "contains_direct_identifiers",
        "subject_identifier",
        "time_unit",
        "missing_policy",
        "additional_columns",
    }
    if not exact(source, source_fields):
        errors.append("source_data fields are invalid")
    else:
        if source["classification"] not in {"public", "non_sensitive", "restricted"}:
            errors.append("source_data.classification is invalid")
        if source["execution_boundary"] != "local_only" or source["format"] != "csv":
            errors.append("source_data must be a local-only CSV")
        if source["columns"] != SOURCE_COLUMNS:
            errors.append("source_data.columns must contain the six fixed columns in order")
        if source["contains_direct_identifiers"] is not False or source["subject_identifier"] != "pseudonymous_unique":
            errors.append("source_data must use unique pseudonymous subject identifiers and contain no direct identifiers")
        if source["time_unit"] != "years" or source["missing_policy"] != "reject" or source["additional_columns"] != "reject":
            errors.append("source_data must use years and reject missing or additional columns")
        source_path = resolve_workspace_file(workspace, source["path"])
        if source_path is None:
            errors.append("source_data.path must be a regular file inside the workspace")
        else:
            raw = source_path.read_bytes()
            if source["sha256"] != digest(raw):
                errors.append("source_data.sha256 does not match current bytes")
            inspected, source_errors = inspect_source(source_path, strategy_order)
            errors.extend(source_errors)
            if source["row_count"] != inspected.get("row_count"):
                errors.append("source_data.row_count does not match current CSV")
            if source["strategy_counts"] != inspected.get("strategy_counts"):
                errors.append("source_data.strategy_counts do not match current CSV")
            facts.update({"source_path": source_path, "source_raw": raw, **inspected})

    bootstrap = value["bootstrap"]
    bootstrap_fields = {
        "method",
        "iterations",
        "seed",
        "rng",
        "rng_version",
        "resampling_unit",
        "strategy_resampling_design",
        "preserve_strategy_sample_sizes",
        "endpoint_sampling",
        "between_strategy_assumption",
        "curves",
        "time_grid_years",
        "cross_implementation_tolerance",
    }
    if not exact(bootstrap, bootstrap_fields):
        errors.append("bootstrap fields are invalid")
    else:
        if bootstrap["method"] != "ordinary_nonparametric_case_resampling":
            errors.append("bootstrap.method must be ordinary_nonparametric_case_resampling")
        iterations = bootstrap["iterations"]
        if isinstance(iterations, bool) or not isinstance(iterations, int) or not 1_000 <= iterations <= 10_000:
            errors.append("bootstrap.iterations must be from 1000 to 10000")
        seed = bootstrap["seed"]
        if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= (1 << 64) - 1:
            errors.append("bootstrap.seed must be an unsigned 64-bit integer")
        if bootstrap["rng"] != RNG_ALGORITHM or bootstrap["rng_version"] != RNG_VERSION:
            errors.append("bootstrap RNG identity is invalid")
        if bootstrap["resampling_unit"] != "whole_subject_row" or bootstrap["strategy_resampling_design"] != "stratified_independent_parallel_arms":
            errors.append("the first slice requires whole-subject resampling stratified across independent parallel arms")
        if bootstrap["preserve_strategy_sample_sizes"] is not True or bootstrap["endpoint_sampling"] != "same_subject_indices_for_pfs_and_os":
            errors.append("bootstrap must preserve arm sizes and reuse subject indices for PFS and OS")
        if bootstrap["between_strategy_assumption"] != "conditional_independence_given_parallel_arm_design":
            errors.append("between_strategy_assumption must explicitly declare conditional independence")
        if bootstrap["curves"] != expected_curves:
            errors.append("bootstrap.curves must exactly reproduce the selected materialized strategy PFS/OS families")
        if not isinstance(bootstrap["time_grid_years"], list) or len(bootstrap["time_grid_years"]) != len(grid) or any(
            not finite(observed) or not math.isclose(float(observed), expected, rel_tol=0, abs_tol=1e-12)
            for observed, expected in zip(bootstrap["time_grid_years"], grid)
        ):
            errors.append("bootstrap.time_grid_years must exactly reproduce the analysis cycle grid")
        tolerance = bootstrap["cross_implementation_tolerance"]
        if not finite(tolerance) or not 1e-12 <= float(tolerance) <= 1e-6:
            errors.append("cross_implementation_tolerance must be between 1e-12 and 1e-6")
        if isinstance(iterations, int) and isinstance(facts.get("row_count"), int) and iterations * facts["row_count"] > MAX_BOOTSTRAP_SELECTIONS:
            errors.append(f"bootstrap plan exceeds the {MAX_BOOTSTRAP_SELECTIONS} patient-selection limit")
        if isinstance(iterations, int) and grid and expected_curves and iterations * len(grid) * len(expected_curves) > MAX_DRAW_CELLS:
            errors.append(f"bootstrap output exceeds the {MAX_DRAW_CELLS} survival-value limit")
        facts.update({"iterations": iterations, "seed": seed, "curves": expected_curves, "time_grid": grid})

    runtime = value["runtime"]
    if not exact(runtime, {"expected_packages"}) or not exact(runtime.get("expected_packages"), PACKAGE_NAMES):
        errors.append("runtime.expected_packages must contain exactly survHE, flexsurv, and survival")
    elif any(not isinstance(version, str) or VERSION.fullmatch(version) is None for version in runtime["expected_packages"].values()):
        errors.append("runtime package versions are invalid")

    output = value["output"]
    expected_output = f"heor/paired-survival-bootstrap-executions/{execution_id}"
    if not exact(output, {"directory", "overwrite_policy"}) or output.get("directory") != expected_output or output.get("overwrite_policy") != "fail_if_exists":
        errors.append(f"output must be fail_if_exists at {expected_output}")
    if not isinstance(value["limitations"], list) or not value["limitations"] or any(not text(item) for item in value["limitations"]):
        errors.append("limitations must contain non-empty strings")
    if value["human_gate"] != {
        "state": "awaiting_execution_authorization",
        "required_action": "approve_local_paired_survival_bootstrap_command",
    }:
        errors.append("human_gate must remain awaiting local paired-bootstrap execution authorization")
    serialized = json.dumps(value, sort_keys=True)
    if re.search(r'"(?:approved|accepted|independently_validated|reviewer_signature|approval_timestamp)"\s*:', serialized):
        errors.append("bootstrap request contains a forbidden authority field")
    return errors, facts


def expected_curve(family: str, parameters: dict[str, float], time: float) -> tuple[float, float | None]:
    evaluator_directory = str(EVALUATOR_PATH.parent)
    if evaluator_directory not in sys.path:
        sys.path.insert(0, evaluator_directory)
    from parametric_survival import curve

    return curve(family, parameters, time)


def expected_parameterization(family: str) -> str:
    evaluator_directory = str(EVALUATOR_PATH.parent)
    if evaluator_directory not in sys.path:
        sys.path.insert(0, evaluator_directory)
    from parametric_survival import PARAMETERIZATIONS

    return PARAMETERIZATIONS[family]


def _read_jsonl(path: Path, limit: int) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    if path.stat().st_size > MAX_RESULT_BYTES:
        return [], [f"{path.name} exceeds 128 MB"]
    rows: list[dict[str, Any]] = []
    try:
        with path.open("rb") as handle:
            for line_number, raw in enumerate(handle, start=1):
                if len(raw) > MAX_LINE_BYTES:
                    errors.append(f"{path.name} row {line_number} exceeds 2 MB")
                    continue
                try:
                    value = json.loads(raw)
                except (UnicodeDecodeError, json.JSONDecodeError):
                    errors.append(f"{path.name} row {line_number} is invalid JSON")
                    continue
                if not isinstance(value, dict):
                    errors.append(f"{path.name} row {line_number} must be an object")
                    continue
                rows.append(value)
                if len(rows) > limit:
                    errors.append(f"{path.name} exceeds the requested row count")
                    break
    except OSError as error:
        errors.append(f"{path.name} cannot be read: {error}")
    return rows, errors


def _bound_output(workspace: Path, binding: Any, label: str, errors: list[str]) -> Path | None:
    if not exact(binding, {"path", "sha256", "format", "row_count"}) or not safe_relative(binding.get("path")) or not isinstance(binding.get("row_count"), int):
        errors.append(f"{label} binding fields are invalid")
        return None
    path = resolve_workspace_file(workspace, binding["path"])
    if path is None or binding["sha256"] != digest(path.read_bytes()):
        errors.append(f"{label} path or SHA-256 is invalid")
        return None
    return path


def audit_result(manifest_path: Path, workspace: Path) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    facts: dict[str, Any] = {}
    try:
        manifest, manifest_raw = load_json(manifest_path)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        return [f"result manifest cannot be read: {error}"], facts
    if not exact(manifest, RESULT_FIELDS):
        return ["result manifest fields are invalid"], facts
    if manifest["schema_version"] != RESULT_SCHEMA_VERSION:
        errors.append(f"result schema_version must be {RESULT_SCHEMA_VERSION}")
    execution_id = manifest["execution_id"]
    if not isinstance(execution_id, str) or SAFE_ID.fullmatch(execution_id) is None:
        errors.append("result execution_id is invalid")
    request_binding = manifest["request"]
    if not exact(request_binding, {"path", "sha256"}):
        errors.append("result request binding fields are invalid")
        return errors, facts
    request_path = resolve_workspace_file(workspace, request_binding["path"])
    if request_path is None:
        errors.append("result request path is missing or unsafe")
        return errors, facts
    request_raw = request_path.read_bytes()
    if request_binding["sha256"] != digest(request_raw):
        errors.append("result request SHA-256 does not match current bytes")
        return errors, facts
    try:
        request = json.loads(request_raw)
    except json.JSONDecodeError:
        errors.append("bound request is invalid JSON")
        return errors, facts
    request_errors, request_facts = validate_request(request, workspace)
    errors.extend(f"request: {error}" for error in request_errors)
    if request.get("execution_id") != execution_id:
        errors.append("result execution_id does not match request")
    for field in ("analysis", "partitioned_survival", "curve_materializations"):
        if manifest[field] != request[field]:
            errors.append(f"result {field} does not exactly copy request binding")
    source_expected = {
        "path": request.get("source_data", {}).get("path"),
        "sha256": request.get("source_data", {}).get("sha256"),
        "row_count": request.get("source_data", {}).get("row_count"),
        "strategy_counts": request.get("source_data", {}).get("strategy_counts"),
    }
    if manifest["source_data"] != source_expected:
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
    if not exact(runtime, runtime_fields) or runtime.get("package_versions") != request.get("runtime", {}).get("expected_packages"):
        errors.append("result runtime fields or package versions are invalid")
    else:
        if runtime["backend"] != "survHE" or runtime["method"] != "paired_patient_bootstrap":
            errors.append("result runtime backend or method is invalid")
        for field in ("rscript_sha256", "adapter_sha256"):
            if not isinstance(runtime[field], str) or SHA256.fullmatch(runtime[field]) is None:
                errors.append(f"result runtime.{field} is invalid")
        for prefix in ("adapter", "session_info", "execution_log"):
            path = resolve_workspace_file(workspace, runtime[f"{prefix}_path"])
            if path is None or runtime[f"{prefix}_sha256"] != digest(path.read_bytes()):
                errors.append(f"runtime {prefix} path or SHA-256 is invalid")
        if runtime["adapter_sha256"] != digest(ADAPTER_PATH.read_bytes()):
            errors.append("result runtime adapter does not match the current fixed adapter")

    bootstrap = manifest["bootstrap"]
    bootstrap_fields = {
        "method",
        "rng",
        "rng_version",
        "seed",
        "iterations",
        "resampling_unit",
        "strategy_resampling_design",
        "endpoint_sampling",
        "between_strategy_assumption",
        "evaluator",
        "curve_order",
        "time_grid_years",
        "resampling_plan",
        "replicate_results",
        "candidate_draws",
        "completed_replicates",
        "failed_replicates",
        "cross_implementation_complete",
        "curve_coherence_complete",
        "eligible_for_joint_packaging",
    }
    request_bootstrap = request.get("bootstrap", {})
    if not exact(bootstrap, bootstrap_fields):
        errors.append("result bootstrap fields are invalid")
        return errors, facts
    for field in (
        "method",
        "rng",
        "rng_version",
        "seed",
        "iterations",
        "resampling_unit",
        "strategy_resampling_design",
        "endpoint_sampling",
        "between_strategy_assumption",
        "time_grid_years",
    ):
        if bootstrap[field] != request_bootstrap.get(field):
            errors.append(f"result bootstrap.{field} does not match request")
    expected_evaluator = {"id": EVALUATOR, "sha256": digest(EVALUATOR_PATH.read_bytes())}
    if bootstrap["evaluator"] != expected_evaluator:
        errors.append("result bootstrap.evaluator does not bind the current independent evaluator")
    expected_curves = request_facts.get("curves", [])
    expected_order = [curve["target_path"] for curve in expected_curves]
    if bootstrap["curve_order"] != expected_order:
        errors.append("result bootstrap.curve_order does not match selected curves")
    iterations = request_facts.get("iterations")
    if not isinstance(iterations, int):
        return errors, facts

    plan = bootstrap["resampling_plan"]
    plan_path = _bound_output(workspace, plan, "resampling_plan", errors)
    if plan.get("format") != PLAN_FORMAT or plan.get("row_count") != iterations:
        errors.append("resampling_plan format or row_count is invalid")
    elif plan_path is not None:
        expected_lines = ["replicate_index," + ",".join(f"row_{index}" for index in range(1, request_facts["row_count"] + 1))]
        for replicate, frequencies in enumerate(
            bootstrap_frequencies(request_facts["strategy_positions"], iterations, request_facts["seed"]),
            start=1,
        ):
            expected_lines.append(f"{replicate}," + ",".join(str(value) for value in frequencies))
        expected_raw = ("\n".join(expected_lines) + "\n").encode("utf-8")
        if plan_path.read_bytes() != expected_raw:
            errors.append("resampling_plan bytes do not reproduce the declared PCG32 stratified design")

    replicate_binding = bootstrap["replicate_results"]
    replicate_path = _bound_output(workspace, replicate_binding, "replicate_results", errors)
    if replicate_binding.get("format") != REPLICATE_FORMAT or replicate_binding.get("row_count") != iterations:
        errors.append("replicate_results format or row_count is invalid")
    replicate_rows: list[dict[str, Any]] = []
    if replicate_path is not None:
        replicate_rows, row_errors = _read_jsonl(replicate_path, iterations)
        errors.extend(row_errors)
        if len(replicate_rows) != iterations:
            errors.append("replicate_results must contain exactly one row per requested replicate")

    tolerance = float(request_bootstrap.get("cross_implementation_tolerance", 0.0))
    grid = request_facts.get("time_grid", [])
    passed_curves: list[list[list[float]]] = []
    failed_count = 0
    cross_complete = True
    coherence_complete = True
    for replicate_index, row in enumerate(replicate_rows, start=1):
        row_fields = {"replicate_index", "status", "curves", "failure_reasons"}
        if not exact(row, row_fields) or row.get("replicate_index") != replicate_index:
            errors.append(f"replicate {replicate_index} fields or index are invalid")
            failed_count += 1
            cross_complete = coherence_complete = False
            continue
        reasons = row["failure_reasons"]
        if not isinstance(reasons, list) or any(not text(item) for item in reasons):
            errors.append(f"replicate {replicate_index} failure_reasons are invalid")
        curves = row["curves"]
        if not isinstance(curves, list) or len(curves) != len(expected_curves):
            errors.append(f"replicate {replicate_index} does not cover every selected curve")
            failed_count += 1
            cross_complete = coherence_complete = False
            continue
        values_for_row: list[list[float]] = []
        row_ok = True
        for curve_index, (curve, expected) in enumerate(zip(curves, expected_curves)):
            curve_fields = {"target_path", "strategy_id", "endpoint", "family", "status", "parameterization", "parameters", "survival", "warnings", "crosscheck"}
            if not exact(curve, curve_fields) or any(curve.get(field) != expected[field] for field in ("target_path", "strategy_id", "endpoint", "family")):
                errors.append(f"replicate {replicate_index} curve {curve_index} identity or fields are invalid")
                row_ok = cross_complete = False
                values_for_row.append([])
                continue
            if curve["status"] == "failed":
                if curve["parameterization"] != "" or curve["parameters"] != [] or curve["survival"] != [] or curve["crosscheck"] != {"status": "fit_failed", "max_abs_survival_error": None} or not isinstance(curve["warnings"], list) or not curve["warnings"]:
                    errors.append(f"replicate {replicate_index} failed curve payload is invalid")
                row_ok = cross_complete = False
                values_for_row.append([])
                continue
            if curve["status"] != "converged" or curve["parameterization"] != expected_parameterization(expected["family"]):
                errors.append(f"replicate {replicate_index} curve {curve_index} status or parameterization is invalid")
                row_ok = cross_complete = False
                values_for_row.append([])
                continue
            parameters = curve["parameters"]
            parameter_map: dict[str, float] = {}
            if not isinstance(parameters, list):
                errors.append(f"replicate {replicate_index} curve {curve_index} parameters are invalid")
                row_ok = cross_complete = False
                values_for_row.append([])
                continue
            for parameter in parameters:
                if not exact(parameter, {"name", "estimate"}) or not text(parameter.get("name")) or not finite(parameter.get("estimate")):
                    errors.append(f"replicate {replicate_index} curve {curve_index} contains an invalid parameter")
                    row_ok = cross_complete = False
                    continue
                parameter_map[parameter["name"]] = float(parameter["estimate"])
            survival = curve["survival"]
            if not isinstance(survival, list) or len(survival) != len(grid) or any(not finite(item) for item in survival):
                errors.append(f"replicate {replicate_index} curve {curve_index} survival grid is invalid")
                row_ok = cross_complete = False
                values_for_row.append([])
                continue
            observed_values = [float(item) for item in survival]
            try:
                expected_values = [expected_curve(expected["family"], parameter_map, time)[0] for time in grid]
            except (KeyError, TypeError, ValueError) as error:
                errors.append(f"replicate {replicate_index} curve {curve_index} independent evaluator failed: {error}")
                row_ok = cross_complete = False
                values_for_row.append(observed_values)
                continue
            maximum_error = max(abs(observed - calculated) for observed, calculated in zip(observed_values, expected_values))
            expected_check = {"status": "passed" if maximum_error <= tolerance else "failed", "max_abs_survival_error": maximum_error}
            check = curve["crosscheck"]
            if not exact(check, {"status", "max_abs_survival_error"}) or check.get("status") != expected_check["status"] or not finite(check.get("max_abs_survival_error")) or not math.isclose(float(check["max_abs_survival_error"]), maximum_error, rel_tol=1e-12, abs_tol=1e-15):
                errors.append(f"replicate {replicate_index} curve {curve_index} crosscheck is invalid")
            if maximum_error > tolerance:
                row_ok = cross_complete = False
            if not math.isclose(observed_values[0], 1.0, rel_tol=0, abs_tol=TOLERANCE) or any(value < 0 or value > 1 for value in observed_values) or any(right > left + TOLERANCE for left, right in zip(observed_values, observed_values[1:])):
                errors.append(f"replicate {replicate_index} curve {curve_index} is not a valid survival curve")
                row_ok = coherence_complete = False
            values_for_row.append(observed_values)
        for strategy_index in range(len(request_facts.get("analysis", {}).get("strategy_order", []))):
            pfs = values_for_row[strategy_index * 2] if len(values_for_row) > strategy_index * 2 else []
            overall = values_for_row[strategy_index * 2 + 1] if len(values_for_row) > strategy_index * 2 + 1 else []
            if pfs and overall and any(pfs_value > os_value + TOLERANCE for pfs_value, os_value in zip(pfs, overall)):
                row_ok = coherence_complete = False
        expected_status = "complete" if row_ok else "failed"
        if row["status"] != expected_status or (row_ok and reasons) or (not row_ok and not reasons):
            errors.append(f"replicate {replicate_index} status or failure reasons do not match audited curves")
        if row_ok:
            passed_curves.append(values_for_row)
        else:
            failed_count += 1

    completed = iterations - failed_count
    if bootstrap["completed_replicates"] != completed or bootstrap["failed_replicates"] != failed_count:
        errors.append("result bootstrap replicate counts do not match audited rows")
    if bootstrap["cross_implementation_complete"] is not cross_complete or bootstrap["curve_coherence_complete"] is not coherence_complete:
        errors.append("result bootstrap completion flags do not match audited rows")
    eligible = failed_count == 0 and cross_complete and coherence_complete and len(passed_curves) == iterations
    if bootstrap["eligible_for_joint_packaging"] is not eligible:
        errors.append("eligible_for_joint_packaging does not match audited replicate state")
    candidate = bootstrap["candidate_draws"]
    if not eligible:
        if candidate is not None:
            errors.append("candidate_draws must be null when any replicate is ineligible")
    else:
        candidate_path = _bound_output(workspace, candidate, "candidate_draws", errors)
        if candidate.get("format") != DRAW_FORMAT or candidate.get("row_count") != iterations:
            errors.append("candidate_draws format or row_count is invalid")
        elif candidate_path is not None:
            expected_raw = b"".join(
                (json.dumps({"draw_index": index, "curves": curves}, separators=(",", ":")) + "\n").encode("utf-8")
                for index, curves in enumerate(passed_curves, start=1)
            )
            if candidate_path.read_bytes() != expected_raw:
                errors.append("candidate_draws do not exactly reproduce the audited complete replicate rows")

    expected_status = "complete" if eligible else "incomplete"
    if manifest["status"] != expected_status:
        errors.append("result status does not match audited bootstrap eligibility")
    if not isinstance(manifest["limitations"], list) or not manifest["limitations"] or any(not text(item) for item in manifest["limitations"]):
        errors.append("result limitations must contain non-empty strings")
    if manifest["human_gate"] != {
        "state": "awaiting_bootstrap_method_review",
        "required_action": "review_paired_bootstrap_before_joint_packaging",
    }:
        errors.append("result human_gate must remain awaiting bootstrap method review")
    serialized = manifest_raw.lower()
    if any(field in serialized for field in (b'"approved":', b'"accepted":', b'"independently_validated":')):
        errors.append("result contains a forbidden authority field")
    facts.update(
        {
            "complete": not errors,
            "eligible_for_joint_packaging": eligible and not errors,
            "iterations": iterations,
            "completed_replicates": completed,
            "failed_replicates": failed_count,
            "curve_count": len(expected_curves),
            "request_sha256": digest(request_raw),
            "result_sha256": digest(manifest_raw),
        }
    )
    return errors, facts
