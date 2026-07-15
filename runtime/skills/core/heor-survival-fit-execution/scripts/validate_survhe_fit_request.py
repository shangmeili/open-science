#!/usr/bin/env python3
"""Preflight an AI4HEOR isolated survHE execution request without running R."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from survhe_execution_contract import load_json, validate_request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    path = args.request if args.request.is_absolute() else args.workspace / args.request
    try:
        request, _ = load_json(path)
        errors, facts = validate_request(request, args.workspace)
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
        errors, facts = [str(error)], {}
    result = {
        "complete": not errors,
        "errors": errors,
        "candidate_models": len(facts.get("families", [])),
        "row_count": facts.get("row_count", 0),
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
