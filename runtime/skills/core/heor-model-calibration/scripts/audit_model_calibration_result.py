#!/usr/bin/env python3
"""Replay and audit one bounded cohort-model calibration result."""

from __future__ import annotations

import json
import sys

from calibration_contract import audit_result, parse_args, resolve_file


def main() -> int:
    workspace, relative = parse_args(__doc__ or "Audit calibration result")
    path = resolve_file(workspace, relative.as_posix())
    if path is None:
        result = {"complete": False, "reviewable": False, "errors": ["result path is unsafe or missing"]}
    else:
        result = audit_result(path, workspace)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
