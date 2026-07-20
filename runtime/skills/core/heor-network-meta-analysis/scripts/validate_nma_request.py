#!/usr/bin/env python3
"""Validate a bounded AI4HEOR NMA request."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from nma_contract import load_json, validate_request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    try:
        value, _ = load_json(args.request)
        errors, facts = validate_request(value, args.workspace)
    except Exception as error:  # explicit CLI boundary
        errors, facts = [str(error)], {}
    print(json.dumps({"valid": not errors, "facts": {key: value for key, value in facts.items() if key != "rows"}, "errors": errors}, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())

