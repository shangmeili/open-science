#!/usr/bin/env python3
"""Validate and replay one AI4HEOR decision-tree uncertainty result."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_core() -> object:
    script = Path(__file__).resolve()
    for parent in script.parents:
        for candidate in (parent / "python/heor_core/src", parent / "heor-core/src"):
            if (candidate / "heor_core/decision_tree_uncertainty.py").is_file():
                sys.path.insert(0, str(candidate))
                from heor_core import decision_tree_uncertainty

                return decision_tree_uncertainty
    raise RuntimeError("the bundled AI4HEOR decision-tree uncertainty core is unavailable")


def load_object(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value, raw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--uncertainty-plan", type=Path, required=True)
    parser.add_argument("--result", type=Path)
    arguments = parser.parse_args()

    core = load_core()
    plan, plan_raw = load_object(arguments.plan)
    uncertainty, uncertainty_raw = load_object(arguments.uncertainty_plan)
    expected = core.run_decision_tree_uncertainty(
        plan, plan_raw, uncertainty, uncertainty_raw
    )
    if arguments.result is not None:
        actual, _ = load_object(arguments.result)
        if actual != expected:
            raise ValueError(
                "result does not match deterministic replay of the exact decision-tree and uncertainty plans"
            )
    print(
        json.dumps(
            {
                "valid": True,
                "analysis_id": expected["analysis_id"],
                "uncertainty_id": expected["uncertainty_id"],
                "parameter_count": len(expected["deterministic_analysis"]),
                "iterations": expected["probabilistic_analysis"]["iterations"],
                "convergence_passed": expected["probabilistic_analysis"]["convergence"]["passed"],
                "analysis_input_sha256": expected["analysis_input_sha256"],
                "uncertainty_input_sha256": expected["uncertainty_input_sha256"],
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
        raise SystemExit(f"decision-tree uncertainty validation failed: {error}") from error
