#!/usr/bin/env python3
"""Validate one bounded cohort-model calibration request."""

from __future__ import annotations

import json
import sys

from calibration_contract import load_json, parse_args, resolve_file, validate_request


def main() -> int:
    workspace, relative = parse_args(__doc__ or "Validate calibration request")
    path = resolve_file(workspace, relative.as_posix())
    if path is None:
        result = {"complete": False, "errors": ["request path is unsafe or missing"]}
    else:
        request, _ = load_json(path)
        errors, _ = validate_request(request, workspace)
        result = {"complete": not errors, "errors": errors}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
