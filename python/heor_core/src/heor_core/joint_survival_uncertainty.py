"""Validate and stream backend-neutral joint PFS/OS survival draws."""

from __future__ import annotations

import hashlib
import json
from math import isclose, isfinite
from typing import Any, Iterator

from .model import ModelValidationError


SCHEMA_VERSION = "0.3.0"
PREVIOUS_SCHEMA_VERSION = "0.2.0"
LEGACY_SCHEMA_VERSION = "0.1.0"
MANIFEST_PATH = "heor/joint-survival-uncertainty.json"
DRAW_PATH = "heor/joint-survival-draws.jsonl"
DRAW_FORMAT = "ai4heor-joint-survival-draws-jsonl@0.1.0"
MAX_DRAW_BYTES = 128 * 1024 * 1024
MAX_DRAW_LINE_BYTES = 2 * 1024 * 1024
MAX_DRAW_CELLS = 5_000_000
TOLERANCE = 1e-9
ALLOWED_GENERATION_METHODS = {
    "joint_posterior",
    "paired_patient_bootstrap",
}
DEPENDENCE_SCOPE = [
    "within_strategy_pfs_os",
    "between_strategy_curves",
]


def validate_joint_survival_uncertainty(
    analysis_plan: dict[str, Any],
    analysis_raw: bytes,
    partitioned_plan: dict[str, Any],
    partitioned_raw: bytes,
    materializations: dict[str, Any],
    materializations_raw: bytes,
    manifest: dict[str, Any],
    manifest_raw: bytes,
    draws_raw: bytes,
    expected_iterations: int,
    treatment_effect_duration_raw: bytes | None = None,
) -> None:
    """Fail closed unless one JSONL row jointly covers every PFS/OS curve."""

    manifest = _object(manifest, "joint survival uncertainty manifest")
    psm_schema = partitioned_plan.get("schema_version")
    duration_required = psm_schema in {"0.4.0", "0.7.0"}
    expected_fields = {
        "schema_version",
        "survival_uncertainty_id",
        "analysis_id",
        "psm_id",
        "status",
        "base_analysis",
        "partitioned_survival_plan",
        "curve_materializations",
        "draw_file",
        "curve_order",
        "time_grid_years",
        "generation",
        "limitations",
    }
    if duration_required:
        expected_fields.add("treatment_effect_duration")
    _exact_keys(
        manifest,
        expected_fields,
        "joint survival uncertainty manifest",
    )
    expected_schema = (
        SCHEMA_VERSION
        if psm_schema == "0.7.0"
        else PREVIOUS_SCHEMA_VERSION
        if duration_required
        else LEGACY_SCHEMA_VERSION
    )
    if manifest.get("schema_version") != expected_schema:
        raise ModelValidationError(
            f"joint survival uncertainty schema_version must be {expected_schema} for the current PSM schema"
        )
    _nonempty(manifest.get("survival_uncertainty_id"), "survival_uncertainty_id")
    if manifest.get("status") != "ready_for_human_review":
        raise ModelValidationError(
            "joint survival uncertainty must be ready_for_human_review"
        )
    if manifest.get("analysis_id") != analysis_plan.get("analysis_id"):
        raise ModelValidationError(
            "joint survival uncertainty analysis_id does not match analysis plan"
        )
    if manifest.get("psm_id") != partitioned_plan.get("psm_id"):
        raise ModelValidationError(
            "joint survival uncertainty psm_id does not match partitioned plan"
        )
    for field, expected_path, expected_raw in (
        ("base_analysis", "heor/analysis-plan.json", analysis_raw),
        (
            "partitioned_survival_plan",
            "heor/partitioned-survival-plan.json",
            partitioned_raw,
        ),
        (
            "curve_materializations",
            "heor/survival-curve-materializations.json",
            materializations_raw,
        ),
    ):
        _validate_binding(manifest.get(field), field, expected_path, expected_raw)
    if duration_required:
        if treatment_effect_duration_raw is None:
            raise ModelValidationError(
                "joint survival uncertainty requires current treatment-effect duration bytes"
            )
        _validate_binding(
            manifest.get("treatment_effect_duration"),
            "treatment_effect_duration",
            "heor/treatment-effect-duration.json",
            treatment_effect_duration_raw,
        )
    elif treatment_effect_duration_raw is not None:
        raise ModelValidationError(
            "joint survival treatment-effect duration binding requires PSM schema 0.4.0 or 0.7.0"
        )

    strategy_order = analysis_plan.get("strategy_order")
    if not _nonempty_strings(strategy_order):
        raise ModelValidationError("analysis strategy_order is invalid")
    expected_curve_order = [
        f"partitioned_survival.strategies.{strategy_id}.{endpoint}"
        for strategy_id in strategy_order
        for endpoint in ("pfs", "os")
    ]
    if manifest.get("curve_order") != expected_curve_order:
        raise ModelValidationError(
            "joint survival uncertainty curve_order must contain every strategy PFS then OS"
        )

    cycles = analysis_plan.get("cycles")
    cycle_length = analysis_plan.get("cycle_length_years")
    if isinstance(cycles, bool) or not isinstance(cycles, int) or cycles < 1:
        raise ModelValidationError("analysis cycles is invalid")
    cycle_length = _positive(cycle_length, "analysis cycle_length_years")
    expected_grid = [index * cycle_length for index in range(cycles + 1)]
    observed_grid = manifest.get("time_grid_years")
    if not isinstance(observed_grid, list) or len(observed_grid) != len(expected_grid):
        raise ModelValidationError(
            "joint survival uncertainty time_grid_years does not cover the analysis cycle grid"
        )
    for index, expected in enumerate(expected_grid):
        observed = _number(observed_grid[index], f"time_grid_years[{index}]")
        if not isclose(observed, expected, rel_tol=TOLERANCE, abs_tol=TOLERANCE):
            raise ModelValidationError(
                f"time_grid_years[{index}] does not match the analysis cycle grid"
            )

    generation = _object(manifest.get("generation"), "generation")
    _exact_keys(
        generation,
        {
            "method",
            "sampling_unit",
            "independent_endpoint_sampling",
            "dependence_scope",
            "source_artifact_bindings",
            "rationale",
        },
        "generation",
    )
    if generation.get("method") not in ALLOWED_GENERATION_METHODS:
        raise ModelValidationError(
            "generation.method must be joint_posterior or paired_patient_bootstrap"
        )
    if generation.get("sampling_unit") != "joint_draw_across_all_curves":
        raise ModelValidationError(
            "generation.sampling_unit must be joint_draw_across_all_curves"
        )
    if generation.get("independent_endpoint_sampling") is not False:
        raise ModelValidationError("independent PFS/OS sampling is not admitted")
    if generation.get("dependence_scope") != DEPENDENCE_SCOPE:
        raise ModelValidationError(
            "generation.dependence_scope must preserve within-strategy and between-strategy curve dependence"
        )
    _nonempty(generation.get("rationale"), "generation.rationale")
    source_bindings = generation.get("source_artifact_bindings")
    if not isinstance(source_bindings, list) or not source_bindings:
        raise ModelValidationError(
            "generation.source_artifact_bindings must not be empty"
        )
    seen_paths: set[str] = set()
    for index, binding in enumerate(source_bindings):
        binding = _object(binding, f"source_artifact_bindings[{index}]")
        _exact_keys(
            binding,
            {"path", "content_sha256", "role"},
            f"source_artifact_bindings[{index}]",
        )
        path = _safe_relative_path(
            binding.get("path"), f"source_artifact_bindings[{index}].path"
        )
        if path in seen_paths:
            raise ModelValidationError("source artifact paths must be unique")
        seen_paths.add(path)
        _sha256(
            binding.get("content_sha256"),
            f"source_artifact_bindings[{index}].content_sha256",
        )
        _nonempty(binding.get("role"), f"source_artifact_bindings[{index}].role")

    draw_file = _object(manifest.get("draw_file"), "draw_file")
    _exact_keys(
        draw_file,
        {"path", "content_sha256", "format", "draw_count"},
        "draw_file",
    )
    if draw_file.get("path") != DRAW_PATH:
        raise ModelValidationError(f"draw_file.path must be {DRAW_PATH}")
    if draw_file.get("format") != DRAW_FORMAT:
        raise ModelValidationError(f"draw_file.format must be {DRAW_FORMAT}")
    if draw_file.get("content_sha256") != hashlib.sha256(draws_raw).hexdigest():
        raise ModelValidationError(
            "draw_file.content_sha256 does not match joint survival draw bytes"
        )
    draw_count = draw_file.get("draw_count")
    if (
        isinstance(draw_count, bool)
        or not isinstance(draw_count, int)
        or draw_count != expected_iterations
    ):
        raise ModelValidationError(
            "joint survival draw_count must equal probabilistic_analysis.iterations"
        )
    if not 1_000 <= draw_count <= 10_000:
        raise ModelValidationError("joint survival draw_count must be from 1000 to 10000")
    cell_count = draw_count * len(expected_curve_order) * len(expected_grid)
    if cell_count > MAX_DRAW_CELLS:
        raise ModelValidationError(
            f"joint survival draw artifact exceeds the {MAX_DRAW_CELLS} value limit"
        )
    if len(draws_raw) > MAX_DRAW_BYTES:
        raise ModelValidationError(
            f"joint survival draw artifact exceeds the {MAX_DRAW_BYTES // 1024 // 1024} MB limit"
        )
    _validate_draw_rows(
        draws_raw,
        draw_count,
        len(expected_curve_order),
        len(expected_grid),
        len(strategy_order),
    )

    if not _nonempty_strings(manifest.get("limitations")):
        raise ModelValidationError(
            "joint survival uncertainty limitations must be non-empty unique strings"
        )
    serialized = manifest_raw.lower()
    if any(
        field in serialized
        for field in (
            b'"approved":',
            b'"approval_timestamp":',
            b'"independently_validated":',
        )
    ):
        raise ModelValidationError(
            "joint survival uncertainty contains a forbidden authority field"
        )


def iter_joint_survival_curve_plans(
    draws_raw: bytes,
    strategy_order: list[str] | tuple[str, ...],
    time_grid_years: list[float],
) -> Iterator[dict[str, Any]]:
    """Yield compact curve plans after validation has succeeded."""

    for raw_line in draws_raw.splitlines():
        row = json.loads(raw_line)
        curves = row["curves"]
        strategies: dict[str, Any] = {}
        for strategy_index, strategy_id in enumerate(strategy_order):
            strategies[strategy_id] = {}
            for endpoint_index, endpoint in enumerate(("pfs", "os")):
                values = curves[strategy_index * 2 + endpoint_index]
                strategies[strategy_id][endpoint] = [
                    {"time_years": time_grid_years[index], "survival": survival}
                    for index, survival in enumerate(values)
                ]
        yield {"strategies": strategies}


def _validate_draw_rows(
    draws_raw: bytes,
    draw_count: int,
    curve_count: int,
    grid_count: int,
    strategy_count: int,
) -> None:
    lines = draws_raw.splitlines()
    if len(lines) != draw_count or any(not line.strip() for line in lines):
        raise ModelValidationError(
            "joint survival draw file must contain exactly draw_count non-empty JSONL rows"
        )
    for row_index, raw_line in enumerate(lines, start=1):
        if len(raw_line) > MAX_DRAW_LINE_BYTES:
            raise ModelValidationError(
                f"joint survival draw row {row_index} exceeds the line-size limit"
            )
        try:
            row = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ModelValidationError(
                f"joint survival draw row {row_index} is invalid JSON"
            ) from error
        row = _object(row, f"joint survival draw row {row_index}")
        _exact_keys(row, {"draw_index", "curves"}, f"joint survival draw row {row_index}")
        if row.get("draw_index") != row_index:
            raise ModelValidationError(
                f"joint survival draw row {row_index} has a non-sequential draw_index"
            )
        curves = row.get("curves")
        if not isinstance(curves, list) or len(curves) != curve_count:
            raise ModelValidationError(
                f"joint survival draw row {row_index} does not cover curve_order"
            )
        numeric_curves: list[list[float]] = []
        for curve_index, curve in enumerate(curves):
            if not isinstance(curve, list) or len(curve) != grid_count:
                raise ModelValidationError(
                    f"joint survival draw row {row_index} curve {curve_index} does not cover the time grid"
                )
            values = [
                _number(value, f"draw {row_index} curve {curve_index}[{time_index}]")
                for time_index, value in enumerate(curve)
            ]
            if not isclose(values[0], 1.0, rel_tol=TOLERANCE, abs_tol=TOLERANCE):
                raise ModelValidationError(
                    f"joint survival draw row {row_index} curve {curve_index} must start at 1"
                )
            if any(value < 0.0 or value > 1.0 for value in values):
                raise ModelValidationError(
                    f"joint survival draw row {row_index} curve {curve_index} leaves [0,1]"
                )
            if any(
                current > previous + TOLERANCE
                for previous, current in zip(values, values[1:])
            ):
                raise ModelValidationError(
                    f"joint survival draw row {row_index} curve {curve_index} increases"
                )
            numeric_curves.append(values)
        for strategy_index in range(strategy_count):
            pfs = numeric_curves[strategy_index * 2]
            overall = numeric_curves[strategy_index * 2 + 1]
            if any(
                pfs_value > os_value + TOLERANCE
                for pfs_value, os_value in zip(pfs, overall)
            ):
                raise ModelValidationError(
                    f"joint survival draw row {row_index} has PFS above OS"
                )


def _validate_binding(
    value: Any,
    label: str,
    expected_path: str,
    expected_raw: bytes,
) -> None:
    value = _object(value, label)
    _exact_keys(value, {"path", "content_sha256"}, label)
    if value.get("path") != expected_path:
        raise ModelValidationError(f"{label}.path must be {expected_path}")
    if value.get("content_sha256") != hashlib.sha256(expected_raw).hexdigest():
        raise ModelValidationError(f"{label}.content_sha256 does not match current bytes")


def _exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ModelValidationError(
            f"{label} fields must be exactly {', '.join(sorted(expected))}"
        )


def _object(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ModelValidationError(f"{label} must be an object")
    return value


def _nonempty(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelValidationError(f"{label} must not be empty")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelValidationError(f"{label} must be a number")
    result = float(value)
    if not isfinite(result):
        raise ModelValidationError(f"{label} must be finite")
    return result


def _positive(value: Any, label: str) -> float:
    result = _number(value, label)
    if result <= 0.0:
        raise ModelValidationError(f"{label} must be positive")
    return result


def _sha256(value: Any, label: str) -> str:
    value = _nonempty(value, label)
    if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
        raise ModelValidationError(f"{label} must be a lowercase SHA-256")
    return value


def _safe_relative_path(value: Any, label: str) -> str:
    value = _nonempty(value, label)
    segments = value.split("/")
    if value.startswith("/") or any(segment in {"", ".", ".."} for segment in segments):
        raise ModelValidationError(f"{label} must be a safe relative path")
    if not value.startswith("heor/"):
        raise ModelValidationError(f"{label} must stay under heor/")
    return value


def _nonempty_strings(value: Any) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(isinstance(item, str) and item.strip() for item in value)
        and len(value) == len(set(value))
    )
