#!/usr/bin/env python3
"""Replay and audit one bounded anchored MAIC result."""

from __future__ import annotations

import json
import sys

from pac_contract import audit_result, parse_args, resolve_file


def main() -> int:
    workspace, relative = parse_args("Audit an AI4HEOR anchored MAIC result")
    path = resolve_file(workspace, relative.as_posix())
    if path is None:
        print(json.dumps({"complete": False, "reviewable": False, "errors": ["result path is unsafe or missing"]}, indent=2))
        return 1
    audit = audit_result(path, workspace)
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 0 if not audit["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
