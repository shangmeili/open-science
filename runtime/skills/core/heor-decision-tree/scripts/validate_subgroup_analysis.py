#!/usr/bin/env python3
"""Validate and optionally replay one bounded decision-tree subgroup analysis."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_core() -> object:
    script = Path(__file__).resolve()
    for parent in script.parents:
        for candidate in (parent / "python/heor_core/src", parent / "heor-core/src"):
            if (candidate / "heor_core/subgroup_analysis.py").is_file():
                sys.path.insert(0, str(candidate))
                from heor_core import subgroup_analysis

                return subgroup_analysis
    raise RuntimeError("the bundled AI4HEOR deterministic subgroup core is unavailable")


def load_object(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value, raw


def inside(workspace: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"path must stay inside the workspace: {relative}")
    resolved = (workspace / path).resolve()
    if resolved != workspace and workspace not in resolved.parents:
        raise ValueError(f"path must stay inside the workspace: {relative}")
    return resolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--subgroup-plan", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--result", type=Path)
    arguments = parser.parse_args()
    workspace = arguments.subgroup_plan.resolve().parent.parent
    if arguments.subgroup_plan.resolve() != workspace / "heor/subgroup-analysis-plan.json":
        raise ValueError("subgroup plan must be heor/subgroup-analysis-plan.json")
    overall, overall_raw = load_object(arguments.plan)
    subgroup, subgroup_raw = load_object(arguments.subgroup_plan)
    evidence, evidence_raw = load_object(arguments.evidence)
    inputs = {}
    for index, group in enumerate(subgroup.get("subgroups", [])):
        if not isinstance(group, dict) or not isinstance(group.get("analysis_input"), dict):
            raise ValueError(f"subgroups[{index}].analysis_input is required")
        relative = group["analysis_input"].get("path")
        if not isinstance(relative, str):
            raise ValueError(f"subgroups[{index}].analysis_input.path is required")
        inputs[relative] = load_object(inside(workspace, relative))
    core = load_core()
    expected = core.run_subgroup_analysis(
        overall,
        overall_raw,
        subgroup,
        subgroup_raw,
        inputs,
        evidence,
        evidence_raw,
    )
    if arguments.result is not None:
        actual, _ = load_object(arguments.result)
        if actual != expected:
            raise ValueError("result does not match deterministic replay of the exact subgroup graph")
    print(
        json.dumps(
            {
                "valid": True,
                "subgroup_analysis_id": expected["subgroup_analysis_id"],
                "subgroup_count": len(expected["subgroups"]),
                "source_count": len(expected["source_register"]),
                "overall_consistency_passed": expected["overall_consistency"]["passed"],
                "result_verified": arguments.result is not None,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, KeyError, TypeError) as error:
        raise SystemExit(f"subgroup validation failed: {error}") from error
