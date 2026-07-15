#!/usr/bin/env python3
"""Portable validator for AI4HEOR joint PFS/OS uncertainty artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
from pathlib import Path


SHA256 = re.compile(r"^[a-f0-9]{64}$")
LEGACY_SCHEMA_VERSION = "0.1.0"
DURATION_SCHEMA_VERSION = "0.2.0"
CURRENT_SCHEMA_VERSION = "0.3.0"
DRAW_FORMAT = "ai4heor-joint-survival-draws-jsonl@0.1.0"
DRAW_PATH = "heor/joint-survival-draws.jsonl"
MAX_DRAW_BYTES = 128 * 1024 * 1024
MAX_LINE_BYTES = 2 * 1024 * 1024
MAX_CELLS = 5_000_000
TOLERANCE = 1e-9
MANIFEST_FIELDS = {
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
STRUCTURAL_OMISSIONS = {
    "partitioned_survival.structural.curve_family_selection",
    "partitioned_survival.structural.extrapolation_assumptions",
}


def load_object(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value, raw


def text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def finite(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def string_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(text(item) for item in value)
        and len(value) == len(set(value))
    )


def safe_relative(value: object) -> bool:
    if not text(value) or not str(value).startswith("heor/") or str(value).startswith("/"):
        return False
    return all(segment not in {"", ".", ".."} for segment in str(value).split("/"))


def exact_binding(
    value: object,
    path: str,
    raw: bytes,
    label: str,
    errors: list[str],
) -> None:
    if not isinstance(value, dict) or set(value) != {"path", "content_sha256"}:
        errors.append(f"{label} must contain only path and content_sha256")
        return
    if value.get("path") != path:
        errors.append(f"{label}.path must be {path}")
    if value.get("content_sha256") != hashlib.sha256(raw).hexdigest():
        errors.append(f"{label}.content_sha256 does not match current bytes")


def validate_rows(
    draws_raw: bytes,
    draw_count: int,
    curve_count: int,
    grid_count: int,
    strategy_count: int,
) -> list[str]:
    errors: list[str] = []
    if len(draws_raw) > MAX_DRAW_BYTES:
        return ["draw file exceeds 128 MB"]
    lines = draws_raw.splitlines()
    if len(lines) != draw_count or any(not line.strip() for line in lines):
        return ["draw file must contain exactly draw_count non-empty JSONL rows"]
    for row_index, raw_line in enumerate(lines, start=1):
        label = f"draw row {row_index}"
        if len(raw_line) > MAX_LINE_BYTES:
            errors.append(f"{label} exceeds 2 MB")
            continue
        try:
            row = json.loads(raw_line)
        except (UnicodeDecodeError, json.JSONDecodeError):
            errors.append(f"{label} is invalid JSON")
            continue
        if not isinstance(row, dict) or set(row) != {"draw_index", "curves"}:
            errors.append(f"{label} must contain only draw_index and curves")
            continue
        if row.get("draw_index") != row_index:
            errors.append(f"{label} draw_index must be sequential")
        curves = row.get("curves")
        if not isinstance(curves, list) or len(curves) != curve_count:
            errors.append(f"{label} must cover every curve_order entry")
            continue
        checked: list[list[float]] = []
        for curve_index, curve in enumerate(curves):
            curve_label = f"{label} curve {curve_index}"
            if not isinstance(curve, list) or len(curve) != grid_count:
                errors.append(f"{curve_label} must cover the complete time grid")
                continue
            if not all(finite(item) for item in curve):
                errors.append(f"{curve_label} values must be finite numbers")
                continue
            values = [float(item) for item in curve]
            if not math.isclose(values[0], 1.0, rel_tol=TOLERANCE, abs_tol=TOLERANCE):
                errors.append(f"{curve_label} must start at 1")
            if any(item < 0 or item > 1 for item in values):
                errors.append(f"{curve_label} must stay inside [0,1]")
            if any(current > previous + TOLERANCE for previous, current in zip(values, values[1:])):
                errors.append(f"{curve_label} must be non-increasing")
            checked.append(values)
        if len(checked) == curve_count:
            for strategy_index in range(strategy_count):
                pfs = checked[strategy_index * 2]
                overall = checked[strategy_index * 2 + 1]
                if any(left > right + TOLERANCE for left, right in zip(pfs, overall)):
                    errors.append(f"{label} has PFS above OS")
        if len(errors) >= 100:
            errors.append("validation stopped after 100 errors")
            break
    return errors


def validate(
    analysis_path: Path,
    psm_path: Path,
    materializations_path: Path,
    uncertainty_path: Path,
    manifest_path: Path,
    draws_path: Path,
    workspace_root: Path,
    duration_path: Path | None = None,
) -> list[str]:
    analysis, analysis_raw = load_object(analysis_path)
    psm, psm_raw = load_object(psm_path)
    materializations, materializations_raw = load_object(materializations_path)
    uncertainty, uncertainty_raw = load_object(uncertainty_path)
    manifest, manifest_raw = load_object(manifest_path)
    draws_raw = draws_path.read_bytes()
    psm_schema = psm.get("schema_version")
    duration_required = psm_schema in {"0.4.0", "0.7.0"}
    duration_raw = duration_path.read_bytes() if duration_path is not None else None
    errors: list[str] = []

    expected_fields = MANIFEST_FIELDS | ({"treatment_effect_duration"} if duration_required else set())
    expected_schema = CURRENT_SCHEMA_VERSION if psm_schema == "0.7.0" else DURATION_SCHEMA_VERSION if duration_required else LEGACY_SCHEMA_VERSION
    if set(manifest) != expected_fields:
        errors.append(f"manifest fields do not match schema {expected_schema} exactly")
    if manifest.get("schema_version") != expected_schema:
        errors.append(f"manifest schema_version must be {expected_schema}")
    if not text(manifest.get("survival_uncertainty_id")):
        errors.append("survival_uncertainty_id must not be empty")
    if manifest.get("status") != "ready_for_human_review":
        errors.append("manifest status must be ready_for_human_review")
    expected_pair = (
        ("0.15.0", "0.7.0", "0.14.0")
        if psm_schema == "0.7.0"
        else ("0.12.0", "0.4.0", "0.12.0")
        if psm_schema == "0.4.0"
        else ("0.12.0", "0.3.0", "0.12.0")
    )
    if (analysis.get("schema_version"), psm_schema, uncertainty.get("schema_version")) != expected_pair:
        errors.append("analysis, PSM, and uncertainty schemas do not match an admitted joint-survival pairing")
    if manifest.get("analysis_id") != analysis.get("analysis_id") or psm.get("analysis_id") != analysis.get("analysis_id"):
        errors.append("analysis_id must match across analysis, PSM, and manifest")
    if manifest.get("psm_id") != psm.get("psm_id"):
        errors.append("psm_id must match the partitioned-survival plan")

    exact_binding(manifest.get("base_analysis"), "heor/analysis-plan.json", analysis_raw, "base_analysis", errors)
    exact_binding(manifest.get("partitioned_survival_plan"), "heor/partitioned-survival-plan.json", psm_raw, "partitioned_survival_plan", errors)
    exact_binding(manifest.get("curve_materializations"), "heor/survival-curve-materializations.json", materializations_raw, "curve_materializations", errors)
    if duration_required:
        if duration_raw is None:
            errors.append("PSM schema 0.4.0 or 0.7.0 requires --treatment-effect-duration")
        else:
            exact_binding(manifest.get("treatment_effect_duration"), "heor/treatment-effect-duration.json", duration_raw, "treatment_effect_duration", errors)
    elif duration_raw is not None or "treatment_effect_duration" in manifest:
        errors.append("treatment-effect duration requires PSM schema 0.4.0 or 0.7.0")

    order = analysis.get("strategy_order")
    if not string_list(order):
        errors.append("analysis strategy_order must be a non-empty unique string list")
        order = []
    expected_curve_order = [
        f"partitioned_survival.strategies.{strategy_id}.{endpoint}"
        for strategy_id in order
        for endpoint in ("pfs", "os")
    ]
    if manifest.get("curve_order") != expected_curve_order:
        errors.append("curve_order must list every strategy PFS then OS")

    cycles = analysis.get("cycles")
    cycle_length = analysis.get("cycle_length_years")
    expected_grid: list[float] = []
    if isinstance(cycles, bool) or not isinstance(cycles, int) or cycles < 1 or not finite(cycle_length) or cycle_length <= 0:
        errors.append("analysis cycles and cycle_length_years are invalid")
    else:
        expected_grid = [index * float(cycle_length) for index in range(cycles + 1)]
    grid = manifest.get("time_grid_years")
    if not isinstance(grid, list) or len(grid) != len(expected_grid) or not all(finite(item) for item in grid):
        errors.append("time_grid_years must cover the finite analysis grid")
    elif any(not math.isclose(float(item), expected, rel_tol=TOLERANCE, abs_tol=TOLERANCE) for item, expected in zip(grid, expected_grid)):
        errors.append("time_grid_years does not match the analysis grid")

    generation = manifest.get("generation")
    generation_fields = {"method", "sampling_unit", "independent_endpoint_sampling", "dependence_scope", "source_artifact_bindings", "rationale"}
    if not isinstance(generation, dict) or set(generation) != generation_fields:
        errors.append("generation fields do not match the contract exactly")
        generation = {}
    if generation.get("method") not in {"joint_posterior", "paired_patient_bootstrap"}:
        errors.append("generation.method is not admitted")
    if generation.get("sampling_unit") != "joint_draw_across_all_curves":
        errors.append("sampling_unit must be joint_draw_across_all_curves")
    if generation.get("independent_endpoint_sampling") is not False:
        errors.append("independent PFS/OS sampling is not admitted")
    if generation.get("dependence_scope") != ["within_strategy_pfs_os", "between_strategy_curves"]:
        errors.append("dependence_scope must preserve within- and between-strategy curve dependence")
    if not text(generation.get("rationale")):
        errors.append("generation.rationale must not be empty")

    source_bindings = generation.get("source_artifact_bindings")
    if not isinstance(source_bindings, list) or not source_bindings:
        errors.append("source_artifact_bindings must not be empty")
    else:
        seen: set[str] = set()
        root = workspace_root.resolve()
        for index, binding in enumerate(source_bindings):
            label = f"source_artifact_bindings[{index}]"
            if not isinstance(binding, dict) or set(binding) != {"path", "content_sha256", "role"}:
                errors.append(f"{label} fields are invalid")
                continue
            relative = binding.get("path")
            if not safe_relative(relative) or relative in seen:
                errors.append(f"{label}.path must be unique and safely under heor/")
                continue
            seen.add(str(relative))
            expected_hash = binding.get("content_sha256")
            if not isinstance(expected_hash, str) or not SHA256.fullmatch(expected_hash):
                errors.append(f"{label}.content_sha256 must be lowercase SHA-256")
            if not text(binding.get("role")):
                errors.append(f"{label}.role must not be empty")
            candidate = (root / str(relative)).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                errors.append(f"{label}.path escapes workspace root")
                continue
            if not candidate.is_file():
                errors.append(f"{label}.path does not exist")
            elif hashlib.sha256(candidate.read_bytes()).hexdigest() != expected_hash:
                errors.append(f"{label}.content_sha256 does not match current bytes")

    draw_file = manifest.get("draw_file")
    draw_count = 0
    if not isinstance(draw_file, dict) or set(draw_file) != {"path", "content_sha256", "format", "draw_count"}:
        errors.append("draw_file fields are invalid")
    else:
        if draw_file.get("path") != DRAW_PATH:
            errors.append(f"draw_file.path must be {DRAW_PATH}")
        if draw_file.get("format") != DRAW_FORMAT:
            errors.append(f"draw_file.format must be {DRAW_FORMAT}")
        if draw_file.get("content_sha256") != hashlib.sha256(draws_raw).hexdigest():
            errors.append("draw_file.content_sha256 does not match current bytes")
        draw_count = draw_file.get("draw_count")
        if isinstance(draw_count, bool) or not isinstance(draw_count, int) or not 1000 <= draw_count <= 10000:
            errors.append("draw_count must be an integer from 1000 to 10000")
            draw_count = 0

    psa = uncertainty.get("probabilistic_analysis")
    iterations = psa.get("iterations") if isinstance(psa, dict) else None
    if draw_count and draw_count != iterations:
        errors.append("draw_count must equal probabilistic_analysis.iterations")
    joint_inputs = uncertainty.get("joint_survival_inputs")
    if not isinstance(joint_inputs, dict) or set(joint_inputs) != {"manifest", "draws"}:
        errors.append("uncertainty joint_survival_inputs fields are invalid")
    else:
        exact_binding(joint_inputs.get("manifest"), "heor/joint-survival-uncertainty.json", manifest_raw, "joint_survival_inputs.manifest", errors)
        exact_binding(joint_inputs.get("draws"), DRAW_PATH, draws_raw, "joint_survival_inputs.draws", errors)
    omissions = psa.get("omitted_parameters") if isinstance(psa, dict) else None
    omission_paths = {
        item.get("provenance_path")
        for item in omissions or []
        if isinstance(item, dict)
    }
    represented = set(expected_curve_order)
    if represented & omission_paths:
        errors.append("represented PFS/OS curves must not be listed as omitted")
    if not STRUCTURAL_OMISSIONS.issubset(omission_paths):
        errors.append("all required structural survival omissions must be declared")
    duration_omitted = "partitioned_survival.structural.treatment_effect_duration" in omission_paths
    if duration_required == duration_omitted:
        errors.append(
            "modeled treatment-effect duration must not be omitted"
            if duration_required
            else "unmodeled treatment-effect duration must be explicitly omitted"
        )

    if draw_count and expected_grid and order:
        cells = draw_count * len(expected_curve_order) * len(expected_grid)
        if cells > MAX_CELLS:
            errors.append(f"draw artifact exceeds the {MAX_CELLS} value limit")
        else:
            errors.extend(validate_rows(draws_raw, draw_count, len(expected_curve_order), len(expected_grid), len(order)))
    if not string_list(manifest.get("limitations")):
        errors.append("limitations must be non-empty unique strings")
    lowered = manifest_raw.lower()
    if any(field in lowered for field in (b'"approved":', b'"approval_timestamp":', b'"independently_validated":')):
        errors.append("manifest contains a forbidden authority field")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("analysis", type=Path)
    parser.add_argument("partitioned_survival", type=Path)
    parser.add_argument("materializations", type=Path)
    parser.add_argument("uncertainty", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("draws", type=Path)
    parser.add_argument("--workspace-root", type=Path, default=Path("."))
    parser.add_argument("--treatment-effect-duration", type=Path)
    args = parser.parse_args()
    try:
        errors = validate(
            args.analysis,
            args.partitioned_survival,
            args.materializations,
            args.uncertainty,
            args.manifest,
            args.draws,
            args.workspace_root,
            args.treatment_effect_duration,
        )
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"FAIL: {error}", file=sys.stderr)
        return 1
    print("PASS: joint survival uncertainty artifacts are structurally valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
