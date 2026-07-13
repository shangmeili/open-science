"""Command-line entry point for deterministic HEOR analyses."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

from .model import MarkovSpecification, ModelValidationError, run_markov


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Path to a Markov analysis JSON file")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        raw = args.input.read_bytes()
        payload = json.loads(raw)
        specification = MarkovSpecification.from_dict(payload)
        result = run_markov(specification).to_dict()
        result["input_sha256"] = hashlib.sha256(raw).hexdigest()
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    except (OSError, json.JSONDecodeError, ModelValidationError) as error:
        raise SystemExit(f"heor-core: {error}") from error
    return 0
