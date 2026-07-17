#!/usr/bin/env python3
"""Fully replay one AI4HEOR semi-Markov microsimulation result."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from microsimulation_contract import audit_result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    arguments = parser.parse_args()
    workspace = arguments.workspace.resolve(strict=True)
    path = arguments.result if arguments.result.is_absolute() else workspace / arguments.result
    audit = audit_result(path, workspace)
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    raise SystemExit(0 if audit["complete"] else 1)


if __name__ == "__main__":
    main()
