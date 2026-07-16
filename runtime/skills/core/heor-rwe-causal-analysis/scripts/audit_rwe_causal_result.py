#!/usr/bin/env python3
"""Replay and audit one bounded local RWE causal-analysis result."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rwe_causal_contract import audit_result, resolve_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.expanduser().resolve()
    result_path = resolve_file(workspace, args.result.as_posix())
    if result_path is None:
        raise SystemExit("result path is unsafe or missing")
    audit = audit_result(result_path, workspace)
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    return 0 if audit["complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
