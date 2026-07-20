#!/usr/bin/env python3
"""Validate one AI4HEOR semi-Markov microsimulation request."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from microsimulation_contract import load_json, validate_request


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    arguments = parser.parse_args()
    workspace = arguments.workspace.resolve(strict=True)
    path = arguments.request if arguments.request.is_absolute() else workspace / arguments.request
    request, _ = load_json(path)
    errors, facts = validate_request(request, workspace)
    output = {"valid": not errors, "errors": errors, "simulation_steps": facts.get("steps", 0)}
    print(json.dumps(output, ensure_ascii=False, indent=2))
    raise SystemExit(0 if not errors else 1)


if __name__ == "__main__":
    main()
