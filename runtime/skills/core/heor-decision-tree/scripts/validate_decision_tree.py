#!/usr/bin/env python3
"""Validate and optionally replay-verify one AI4HEOR decision tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def load_core() -> object:
    script = Path(__file__).resolve()
    candidates: list[Path] = []
    for parent in script.parents:
        candidates.extend((parent / "python/heor_core/src", parent / "heor-core/src"))
    for candidate in candidates:
        if (candidate / "heor_core/decision_tree.py").is_file():
            sys.path.insert(0, str(candidate))
            from heor_core import decision_tree

            return decision_tree
    raise RuntimeError("the bundled AI4HEOR deterministic core is unavailable")


def load_object(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value, raw


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--result", type=Path)
    arguments = parser.parse_args()

    core = load_core()
    plan, raw = load_object(arguments.plan)
    specification = core.DecisionTreeSpecification.from_dict(plan)
    expected = core.run_decision_tree(specification).to_dict()
    expected["input_sha256"] = hashlib.sha256(raw).hexdigest()

    if arguments.result is not None:
        actual, _ = load_object(arguments.result)
        if actual != expected:
            raise ValueError("result does not match deterministic replay of the exact plan")

    print(
        json.dumps(
            {
                "valid": True,
                "schema_version": core.SCHEMA_VERSION,
                "analysis_id": specification.analysis_id,
                "strategy_count": len(specification.strategy_order),
                "input_sha256": expected["input_sha256"],
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
        raise SystemExit(f"decision-tree validation failed: {error}") from error
