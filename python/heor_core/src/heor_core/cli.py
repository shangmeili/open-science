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
    parser.add_argument(
        "--partitioned-survival-plan",
        type=Path,
        help="Optional path to a hash-bound partitioned survival plan",
    )
    parser.add_argument(
        "--survival-curve-materializations",
        type=Path,
        help="Required materialization manifest for partitioned survival",
    )
    parser.add_argument(
        "--treatment-effect-duration",
        type=Path,
        help="Required treatment-effect duration artifact for PSM schema 0.4.0 or 0.5.0",
    )
    parser.add_argument(
        "--cost-input-normalization",
        type=Path,
        help="Required cost-input normalization artifact for PSM schema 0.5.0",
    )
    parser.add_argument(
        "--joint-survival-uncertainty-manifest",
        type=Path,
        help="Required manifest for uncertainty schema 0.12.0",
    )
    parser.add_argument(
        "--joint-survival-draws",
        type=Path,
        help="Required JSONL joint PFS/OS draws for uncertainty schema 0.12.0",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.partitioned_survival_plan is not None and args.budget_impact_plan is not None:
            raise ModelValidationError(
                "--partitioned-survival-plan cannot be combined with --budget-impact-plan"
            )
        if args.survival_curve_materializations is not None and args.partitioned_survival_plan is None:
            raise ModelValidationError(
                "--survival-curve-materializations requires "
                "--partitioned-survival-plan"
            )
        if args.treatment_effect_duration is not None and args.partitioned_survival_plan is None:
            raise ModelValidationError(
                "--treatment-effect-duration requires --partitioned-survival-plan"
            )
        if args.cost_input_normalization is not None and args.partitioned_survival_plan is None:
            raise ModelValidationError(
                "--cost-input-normalization requires --partitioned-survival-plan"
            )
        joint_options = (
            args.joint_survival_uncertainty_manifest,
            args.joint_survival_draws,
        )
        if any(item is not None for item in joint_options) and not all(
            item is not None for item in joint_options
        ):
            raise ModelValidationError(
                "--joint-survival-uncertainty-manifest and --joint-survival-draws must be provided together"
            )
        if any(item is not None for item in joint_options) and args.uncertainty_plan is None:
            raise ModelValidationError(
                "joint survival artifacts require --uncertainty-plan"
            )
        raw = args.input.read_bytes()
        payload = json.loads(raw)
        if any(item is not None for item in joint_options) and payload.get("schema_version") != "0.12.0":
            raise ModelValidationError(
                "joint survival artifacts require analysis schema 0.12.0"
            )
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
            if payload.get("schema_version") == "0.12.0":
                if (
                    args.partitioned_survival_plan is None
                    or args.survival_curve_materializations is None
                ):
                    raise ModelValidationError(
                        "analysis schema 0.12.0 uncertainty requires both partitioned-survival artifact options"
                    )
                partitioned_raw = args.partitioned_survival_plan.read_bytes()
                partitioned_payload = json.loads(partitioned_raw)
                materializations_raw = args.survival_curve_materializations.read_bytes()
                materializations_payload = json.loads(materializations_raw)
                duration_required = partitioned_payload.get("schema_version") in {"0.4.0", "0.5.0"}
                if duration_required != (args.treatment_effect_duration is not None):
                    raise ModelValidationError(
                        "partitioned-survival schema 0.4.0 or 0.5.0 requires exactly one --treatment-effect-duration option"
                    )
                if args.cost_input_normalization is not None:
                    raise ModelValidationError(
                        "analysis schema 0.12.0 uncertainty does not admit cost-input normalization"
                    )
                duration_raw = (
                    args.treatment_effect_duration.read_bytes()
                    if duration_required
                    else None
                )
                duration_payload = (
                    json.loads(duration_raw) if duration_raw is not None else None
                )
                joint_schema = uncertainty_payload.get("schema_version") == "0.12.0"
                if joint_schema and not all(item is not None for item in joint_options):
                    raise ModelValidationError(
                        "uncertainty schema 0.12.0 requires both joint survival artifact options"
                    )
                if not joint_schema and any(item is not None for item in joint_options):
                    raise ModelValidationError(
                        "joint survival artifacts require uncertainty schema 0.12.0"
                    )
                joint_manifest_raw = (
                    args.joint_survival_uncertainty_manifest.read_bytes()
                    if joint_schema
                    else None
                )
                joint_manifest_payload = (
                    json.loads(joint_manifest_raw) if joint_manifest_raw is not None else None
                )
                joint_draws_raw = (
                    args.joint_survival_draws.read_bytes() if joint_schema else None
                )
                result = run_uncertainty(
                    payload,
                    raw,
                    uncertainty_payload,
                    uncertainty_raw,
                    partitioned_payload,
                    partitioned_raw,
                    materializations_payload,
                    materializations_raw,
                    joint_manifest_payload,
                    joint_manifest_raw,
                    joint_draws_raw,
                    duration_payload,
                    duration_raw,
                )
            else:
                if args.partitioned_survival_plan is not None:
                    raise ModelValidationError(
                        "partitioned-survival artifacts with uncertainty require analysis schema 0.12.0"
                    )
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
            duration_required = partitioned_payload.get("schema_version") in {"0.4.0", "0.5.0"}
            if duration_required != (args.treatment_effect_duration is not None):
                raise ModelValidationError(
                    "partitioned-survival schema 0.4.0 or 0.5.0 requires exactly one --treatment-effect-duration option"
                )
            cost_required = partitioned_payload.get("schema_version") == "0.5.0"
            if cost_required != (args.cost_input_normalization is not None):
                raise ModelValidationError(
                    "partitioned-survival schema 0.5.0 requires exactly one --cost-input-normalization option"
                )
            duration_raw = (
                args.treatment_effect_duration.read_bytes() if duration_required else None
            )
            duration_payload = json.loads(duration_raw) if duration_raw is not None else None
            cost_raw = args.cost_input_normalization.read_bytes() if cost_required else None
            cost_payload = json.loads(cost_raw) if cost_raw is not None else None
            result = run_partitioned_survival(
                payload,
                raw,
                partitioned_payload,
                partitioned_raw,
                materializations_payload,
                materializations_raw,
                duration_payload,
                duration_raw,
                cost_payload,
                cost_raw,
            )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    except (OSError, ArithmeticError, json.JSONDecodeError, ModelValidationError) as error:
        raise SystemExit(f"heor-core: {error}") from error
    return 0
