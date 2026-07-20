#!/usr/bin/env python3
"""Audit an AI4HEOR isolated survHE result without executing R."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from survhe_execution_contract import audit_result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result_manifest", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    path = args.result_manifest if args.result_manifest.is_absolute() else args.workspace / args.result_manifest
    result = audit_result(path, args.workspace)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["complete"] and result["eligible_for_review"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
