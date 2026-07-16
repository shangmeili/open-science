#!/usr/bin/env python3
"""Validate an AI4HEOR advanced VOI plan and optional replay/result pair."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value, raw


def load_core() -> object:
    script = Path(__file__).resolve()
    candidates = []
    for parent in script.parents:
        candidates.extend(
            [parent / "python/heor_core/src", parent / "heor-core/src"]
        )
    for candidate in candidates:
        if (candidate / "heor_core/advanced_voi.py").is_file():
            sys.path.insert(0, str(candidate))
            from heor_core import advanced_voi

            return advanced_voi
    raise RuntimeError("the bundled AI4HEOR deterministic core is unavailable")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--uncertainty", type=Path, required=True)
    parser.add_argument("--uncertainty-result", type=Path, required=True)
    parser.add_argument("--partitioned-survival-plan", type=Path)
    parser.add_argument("--survival-curve-materializations", type=Path)
    parser.add_argument("--treatment-effect-duration", type=Path)
    parser.add_argument("--cost-input-normalization", type=Path)
    parser.add_argument("--utility-inputs", type=Path)
    parser.add_argument("--event-disutilities", type=Path)
    parser.add_argument("--result", type=Path)
    parser.add_argument("--replay", type=Path)
    arguments = parser.parse_args()
    if (arguments.result is None) != (arguments.replay is None):
        raise SystemExit("--result and --replay must be provided together")
    core = load_core()
    plan, plan_raw = load(arguments.plan)
    analysis, analysis_raw = load(arguments.analysis)
    uncertainty, uncertainty_raw = load(arguments.uncertainty)
    uncertainty_result, uncertainty_result_raw = load(arguments.uncertainty_result)
    specification = core.parse_plan(
        plan,
        plan_raw,
        analysis,
        analysis_raw,
        uncertainty,
        uncertainty_raw,
        uncertainty_result,
        uncertainty_result_raw,
    )
    component_paths = (
        arguments.partitioned_survival_plan,
        arguments.survival_curve_materializations,
        arguments.treatment_effect_duration,
        arguments.cost_input_normalization,
        arguments.utility_inputs,
        arguments.event_disutilities,
    )
    if uncertainty.get("schema_version") == "0.9.0":
        if any(path is not None for path in component_paths):
            raise ValueError("standard advanced VOI forbids PSM component artifacts")
        context = core.standard_context(analysis, analysis_raw, uncertainty, uncertainty_raw)
    elif uncertainty.get("schema_version") == "0.13.0":
        if any(path is None for path in component_paths):
            raise ValueError("component advanced VOI requires all six PSM component artifacts")
        loaded = [load(path) for path in component_paths]
        context = core.component_context(
            analysis,
            analysis_raw,
            uncertainty,
            uncertainty_raw,
            *(item for pair in loaded for item in pair),
        )
    else:
        raise ValueError("unsupported uncertainty schema for advanced VOI")
    core.validate_context(specification, context)
    if arguments.result is not None:
        result, _ = load(arguments.result)
        replay, replay_raw = load(arguments.replay)
        core.verify_result_from_replay(plan, result, replay, replay_raw)
    print(
        json.dumps(
            {
                "valid": True,
                "schema_version": core.SCHEMA_VERSION,
                "voi_id": specification.voi_id,
                "evppi_group_count": len(specification.evppi.groups),
                "evsi_design_count": len(specification.evsi.sample_sizes),
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
        raise SystemExit(f"advanced VOI validation failed: {error}") from error
