#!/usr/bin/env python3
"""Validate one bounded anchored MAIC request without executing it."""

from __future__ import annotations

import json
import sys

from pac_contract import load_json, parse_args, resolve_file, validate_request


def main() -> int:
    workspace, relative = parse_args("Validate an AI4HEOR anchored MAIC request")
    path = resolve_file(workspace, relative.as_posix())
    if path is None:
        print(json.dumps({"valid": False, "errors": ["request path is unsafe or missing"]}, indent=2))
        return 1
    try:
        request, _ = load_json(path)
    except Exception as error:  # noqa: BLE001 - CLI must return structured failure
        print(json.dumps({"valid": False, "errors": [f"request cannot be read: {error}"]}, indent=2))
        return 1
    errors, facts = validate_request(request, workspace)
    output = {
        "valid": not errors,
        "execution_id": request.get("execution_id"),
        "row_count": facts.get("source", {}).get("row_count"),
        "effect_modifier_count": len(facts.get("modifier_ids", [])),
        "errors": errors,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
