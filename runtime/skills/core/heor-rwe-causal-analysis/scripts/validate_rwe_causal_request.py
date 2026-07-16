#!/usr/bin/env python3
"""Validate one bounded local RWE causal-analysis request."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rwe_causal_contract import load_json, resolve_file, validate_request


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.expanduser().resolve()
    request_path = resolve_file(workspace, args.request.as_posix())
    if request_path is None:
        raise SystemExit("request path is unsafe or missing")
    if request_path.relative_to(workspace).as_posix() != "heor/rwe-causal-analysis-request.json":
        raise SystemExit("request must use the fixed heor/rwe-causal-analysis-request.json path")
    request, _ = load_json(request_path)
    errors, facts = validate_request(request, workspace)
    output = {
        "complete": not errors,
        "row_count": facts.get("source", {}).get("row_count", 0),
        "confounder_count": len(facts.get("confounder_ids", [])),
        "errors": errors,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
