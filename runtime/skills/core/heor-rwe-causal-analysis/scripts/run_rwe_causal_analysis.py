#!/usr/bin/env python3
"""Execute one preflighted local RWE causal analysis with deterministic bootstrap."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from rwe_causal_contract import (
    EVALUATOR,
    REQUIRED_REVIEW_CHECKS,
    RESULT_SCHEMA_VERSION,
    audit_result,
    canonical_draw_bytes,
    current_python_identity,
    digest,
    execute_bootstrap,
    expected_analysis,
    expected_warnings,
    load_json,
    resolve_file,
    validate_request,
)


EVALUATOR_SOURCE = Path(__file__).with_name("rwe_causal_contract.py")


def relative(workspace: Path, path: Path) -> str:
    return path.resolve().relative_to(workspace.resolve()).as_posix()


def write_json(path: Path, value: dict[str, Any]) -> str:
    raw = (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return digest(raw)


def build_result(
    workspace: Path,
    request_path: Path,
    request_raw: bytes,
    request: dict[str, Any],
    facts: dict[str, Any],
    output: Path,
) -> dict[str, Any]:
    engine_dir = output / "engine"
    engine_dir.mkdir(parents=True)
    evaluator_copy = engine_dir / "rwe_causal_contract.py"
    shutil.copyfile(EVALUATOR_SOURCE, evaluator_copy)
    draws, successful = execute_bootstrap(request, facts)
    draw_raw = canonical_draw_bytes(draws)
    draws_path = output / "bootstrap-draws.csv"
    draws_path.write_bytes(draw_raw)
    analysis = expected_analysis(request, facts, draws, successful)
    output_relative = request["output"]["directory"]
    final_evaluator = f"{output_relative}/engine/rwe_causal_contract.py"
    final_draws = f"{output_relative}/bootstrap-draws.csv"
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "execution_id": request["execution_id"],
        "status": "awaiting_method_review" if analysis["complete"] else "incomplete_bootstrap",
        "request": {"path": relative(workspace, request_path), "sha256": digest(request_raw)},
        "source_data": {"path": request["source_data"]["path"], "sha256": request["source_data"]["sha256"]},
        "evidence_synthesis": {
            "path": request["evidence_synthesis"]["path"],
            "sha256": request["evidence_synthesis"]["sha256"],
        },
        "runtime": {
            "evaluator": EVALUATOR,
            **current_python_identity(),
            "evaluator_source": {"path": final_evaluator, "sha256": digest(evaluator_copy.read_bytes())},
        },
        "target_trial": request["target_trial"],
        "estimand": request["estimand"],
        "propensity_score": analysis["propensity_score"],
        "observation_model": analysis["observation_model"],
        "weighting": analysis["weighting"],
        "diagnostics": analysis["diagnostics"],
        "effects": analysis["effects"],
        "bootstrap": {
            **analysis["bootstrap"],
            "draws": {"path": final_draws, "sha256": digest(draw_raw)},
        },
        "cross_implementation": {
            "portable_replay": "complete_point_diagnostics_and_bootstrap",
            "native_replay": "point_estimate_and_diagnostics_only",
            "uncertainty_native_replay": False,
        },
        "warnings": expected_warnings(analysis),
        "limitations": request["limitations"],
        "human_gate": {
            "status": "awaiting_method_review",
            "required_checks": REQUIRED_REVIEW_CHECKS,
            "automatic_downstream_use": False,
            "causal_validity_determined": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.expanduser().resolve()
    request_path = resolve_file(workspace, args.request.as_posix())
    if request_path is None:
        raise SystemExit("request path is unsafe or missing")
    if relative(workspace, request_path) != "heor/rwe-causal-analysis-request.json":
        raise SystemExit("request must use the fixed heor/rwe-causal-analysis-request.json path")
    request, request_raw = load_json(request_path)
    errors, facts = validate_request(request, workspace)
    if errors:
        print(json.dumps({"complete": False, "errors": errors}, indent=2, ensure_ascii=False))
        return 1
    output = workspace / request["output"]["directory"]
    if output.exists():
        raise SystemExit("output directory already exists; execution IDs are immutable")
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    if staging.exists():
        raise SystemExit("staging directory already exists")
    staging.mkdir()
    try:
        result = build_result(workspace, request_path, request_raw, request, facts, staging)
        write_json(staging / "manifest.json", result)
        staging.rename(output)
        audit = audit_result(output / "manifest.json", workspace)
        if audit["errors"]:
            shutil.rmtree(output)
            print(json.dumps(audit, indent=2, ensure_ascii=False))
            return 1
        print(
            json.dumps(
                {
                    "complete": audit["complete"],
                    "reviewable": audit["reviewable"],
                    "result": relative(workspace, output / "manifest.json"),
                    "errors": [],
                },
                indent=2,
            )
        )
        return 0
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


if __name__ == "__main__":
    sys.exit(main())
