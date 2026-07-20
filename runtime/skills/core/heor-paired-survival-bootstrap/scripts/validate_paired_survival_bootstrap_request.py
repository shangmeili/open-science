#!/usr/bin/env python3
"""Validate one paired survival bootstrap request against current workspace bytes."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from paired_bootstrap_contract import load_json, validate_request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    try:
        value, _ = load_json(args.request)
        errors, facts = validate_request(value, args.workspace.resolve())
        output = {
            "complete": not errors,
            "errors": errors,
            "execution_id": value.get("execution_id"),
            "row_count": facts.get("row_count"),
            "strategy_counts": facts.get("strategy_counts"),
            "iterations": facts.get("iterations"),
            "curve_count": len(facts.get("curves", [])),
        }
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        output = {"complete": False, "errors": [str(error)]}
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if output["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
