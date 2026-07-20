#!/usr/bin/env python3
"""Execute one preflighted bounded cohort natural-history model calibration."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

from calibration_contract import (
    EVALUATOR,
    REQUIRED_REVIEW_CHECKS,
    RESULT_SCHEMA_VERSION,
    audit_result,
    canonical_trace_bytes,
    current_python_identity,
    digest,
    execute_calibration,
    load_json,
    resolve_file,
    validate_request,
)


EVALUATOR_SOURCE = Path(__file__).with_name("calibration_contract.py")


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
    engine = output / "engine"
    engine.mkdir(parents=True)
    evaluator_copy = engine / "calibration_contract.py"
    shutil.copyfile(EVALUATOR_SOURCE, evaluator_copy)
    analysis = execute_calibration(request, facts)
    trace = analysis.pop("_search_trace")
    trace_raw = canonical_trace_bytes(trace, [parameter["id"] for parameter in request["parameters"]])
    trace_path = output / "search.csv"
    trace_path.write_bytes(trace_raw)
    final_directory = request["output"]["directory"]
    return {
        "schema_version": RESULT_SCHEMA_VERSION,
        "calibration_id": request["calibration_id"],
        "status": "awaiting_method_review",
        "request": {"path": relative(workspace, request_path), "sha256": digest(request_raw)},
        "evidence_synthesis": {
            "path": request["evidence_synthesis"]["path"],
            "sha256": request["evidence_synthesis"]["sha256"],
        },
        "runtime": {
            "evaluator": EVALUATOR,
            **current_python_identity(),
            "evaluator_source": {
                "path": f"{final_directory}/engine/calibration_contract.py",
                "sha256": digest(evaluator_copy.read_bytes()),
            },
        },
        "method": {
            "family": "bounded_continuous_time_cohort_natural_history_point_calibration",
            "training_loss": "sum_squared_standardized_residuals",
            "target_covariance": "not_modeled",
            "parameter_uncertainty": "not_propagated",
        },
        "best_fit": analysis["best_fit"],
        "target_fit": analysis["target_fit"],
        "search": {
            **analysis["search"],
            "trace": {"path": f"{final_directory}/search.csv", "sha256": digest(trace_raw)},
        },
        "identifiability": analysis["identifiability"],
        "validation": analysis["validation"],
        "cross_implementation": {
            "portable_replay": "complete_search_and_diagnostics",
            "native_replay": "selected_point_model_and_local_identifiability_only",
        },
        "warnings": analysis["warnings"],
        "limitations": request["limitations"],
        "human_gate": {
            "status": "awaiting_method_review",
            "required_checks": REQUIRED_REVIEW_CHECKS,
            "automatic_model_input_update": False,
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
    if relative(workspace, request_path) != "heor/model-calibration-request.json":
        raise SystemExit("request must use the fixed heor/model-calibration-request.json path")
    request, request_raw = load_json(request_path)
    errors, facts = validate_request(request, workspace)
    if errors:
        print(json.dumps({"complete": False, "errors": errors}, indent=2, ensure_ascii=False))
        return 1
    output = workspace / request["output"]["directory"]
    if output.exists():
        raise SystemExit("output directory already exists; calibration IDs are immutable")
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
        print(json.dumps({
            "complete": audit["complete"],
            "reviewable": audit["reviewable"],
            "result": relative(workspace, output / "manifest.json"),
            "errors": [],
        }, indent=2, ensure_ascii=False))
        return 0
    except Exception:
        if staging.exists():
            shutil.rmtree(staging)
        raise


if __name__ == "__main__":
    sys.exit(main())
