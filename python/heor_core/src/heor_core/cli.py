"""Command-line entry point for deterministic HEOR analyses."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Sequence

from .budget_impact import run_budget_impact
from .model import MarkovSpecification, ModelValidationError, run_markov
from .partitioned_survival import run_partitioned_survival
from .uncertainty import run_uncertainty


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Path to an HEOR analysis plan")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--uncertainty-plan",
        type=Path,
        help="Optional path to a hash-bound uncertainty analysis plan",
    )
    mode.add_argument(
        "--budget-impact-plan",
        type=Path,
        help="Optional path to a hash-bound budget impact plan",
    )
    mode.add_argument(
        "--partitioned-survival-plan",
        type=Path,
        help="Optional path to a hash-bound partitioned survival plan",
    )
    parser.add_argument(
        "--survival-curve-materializations",
        type=Path,
        help="Required materialization manifest for partitioned survival",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if (
            args.survival_curve_materializations is not None
            and args.partitioned_survival_plan is None
        ):
            raise ModelValidationError(
                "--survival-curve-materializations requires "
                "--partitioned-survival-plan"
            )
        raw = args.input.read_bytes()
        payload = json.loads(raw)
        if (
            args.uncertainty_plan is None
            and args.budget_impact_plan is None
            and args.partitioned_survival_plan is None
        ):
            specification = MarkovSpecification.from_dict(payload)
            result = run_markov(specification).to_dict()
            result["input_sha256"] = hashlib.sha256(raw).hexdigest()
        elif args.uncertainty_plan is not None:
            uncertainty_raw = args.uncertainty_plan.read_bytes()
            uncertainty_payload = json.loads(uncertainty_raw)
            result = run_uncertainty(
                payload, raw, uncertainty_payload, uncertainty_raw
            )
        elif args.budget_impact_plan is not None:
            budget_raw = args.budget_impact_plan.read_bytes()
            budget_payload = json.loads(budget_raw)
            result = run_budget_impact(payload, raw, budget_payload, budget_raw)
        else:
            if args.survival_curve_materializations is None:
                raise ModelValidationError(
                    "partitioned survival requires --survival-curve-materializations"
                )
            partitioned_raw = args.partitioned_survival_plan.read_bytes()
            partitioned_payload = json.loads(partitioned_raw)
            materializations_raw = args.survival_curve_materializations.read_bytes()
            materializations_payload = json.loads(materializations_raw)
            result = run_partitioned_survival(
                payload,
                raw,
                partitioned_payload,
                partitioned_raw,
                materializations_payload,
                materializations_raw,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    except (OSError, ArithmeticError, json.JSONDecodeError, ModelValidationError) as error:
        raise SystemExit(f"heor-core: {error}") from error
    return 0
