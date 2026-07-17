#!/usr/bin/env python3
"""Execute one immutable AI4HEOR semi-Markov microsimulation run."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from microsimulation_contract import (
    EVALUATOR,
    RESULT_SCHEMA_VERSION,
    canonical_json_bytes,
    canonical_trace_bytes,
    current_python_identity,
    digest,
    execute_simulation,
    load_json,
    validate_request,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--request", type=Path, required=True)
    arguments = parser.parse_args()
    workspace = arguments.workspace.resolve(strict=True)
    request_path = arguments.request if arguments.request.is_absolute() else workspace / arguments.request
    request_path = request_path.resolve(strict=True)
    if not request_path.is_relative_to(workspace) or request_path.is_symlink():
        print(json.dumps({"complete": False, "errors": ["request path is outside the workspace or symlinked"]}, indent=2))
        raise SystemExit(1)
    request, request_raw = load_json(request_path)
    errors, facts = validate_request(request, workspace)
    if errors:
        print(json.dumps({"complete": False, "errors": errors}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    output = workspace / request["output"]["directory"]
    if output.exists():
        print(json.dumps({"complete": False, "errors": ["immutable output directory already exists"]}, indent=2))
        raise SystemExit(1)
    temporary = output.with_name(f".{output.name}.tmp-{os.getpid()}")
    temporary.mkdir(parents=True)
    try:
        evaluator_destination = temporary / "evaluator" / "microsimulation_contract.py"
        evaluator_destination.parent.mkdir()
        evaluator_raw = Path(__file__).with_name("microsimulation_contract.py").read_bytes()
        evaluator_destination.write_bytes(evaluator_raw)
        analysis = execute_simulation(request, facts)
        trace_rows = analysis.pop("_trace_rows")
        trace_raw = canonical_trace_bytes(trace_rows)
        (temporary / "traces.jsonl").write_bytes(trace_raw)
        relative_output = request["output"]["directory"]
        runtime_identity = current_python_identity()
        result = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "simulation_id": request["simulation_id"],
            "status": "awaiting_method_review",
            "request": {"path": str(request_path.relative_to(workspace)), "sha256": digest(request_raw)},
            "evidence_synthesis": {
                "path": request["evidence_synthesis"]["path"],
                "sha256": request["evidence_synthesis"]["sha256"],
            },
            "runtime": {
                "evaluator": EVALUATOR,
                **runtime_identity,
                "evaluator_source": {
                    "path": f"{relative_output}/evaluator/microsimulation_contract.py",
                    "sha256": digest(evaluator_raw),
                },
            },
            "method": analysis["method"],
            "performance": analysis["performance"],
            "strategies": analysis["strategies"],
            "comparisons": analysis["comparisons"],
            "monte_carlo_error": analysis["monte_carlo_error"],
            "trace": {
                "path": f"{relative_output}/traces.jsonl",
                "sha256": digest(trace_raw),
                "row_count": len(trace_rows),
                "replicate": request["simulation"]["trace_replicate"],
                "patient_indices": request["simulation"]["trace_patient_indices"],
            },
            "warnings": analysis["warnings"],
            "limitations": request["limitations"],
            "human_gate": request["human_gate"],
        }
        (temporary / "manifest.json").write_bytes(canonical_json_bytes(result))
        temporary.rename(output)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    print(json.dumps({
        "complete": True,
        "result": f"{request['output']['directory']}/manifest.json",
        "trace_rows": len(trace_rows),
        "simulation_steps": analysis["performance"]["simulation_steps"],
    }, indent=2))


if __name__ == "__main__":
    main()
