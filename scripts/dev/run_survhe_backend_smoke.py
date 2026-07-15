#!/usr/bin/env python3
"""Run the real optional survHE backend against a synthetic local dataset."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "runtime/skills/core/heor-survival-fit-execution/scripts"
sys.path.insert(0, str(SCRIPT_DIR))
from run_survhe_mle import executable, probe, run_request  # noqa: E402


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rscript", default="Rscript")
    parser.add_argument("--library", type=Path, required=True)
    args = parser.parse_args()
    rscript = executable(args.rscript)
    library = args.library.resolve()
    runtime = probe(rscript, library)
    with tempfile.TemporaryDirectory(prefix="ai4heor-survhe-smoke-") as directory:
        workspace = Path(directory)
        source = workspace / "data/synthetic-survival.csv"
        source.parent.mkdir(parents=True)
        source.write_text(
            "time,event\n0.25,1\n0.5,0\n0.75,1\n1,1\n1.5,0\n2,1\n2.5,0\n3,1\n4,0\n5,1\n",
            encoding="utf-8",
        )
        request = {
            "schema_version": "0.1.0",
            "execution_id": "real-backend-smoke",
            "status": "ready_for_execution",
            "analysis_target": {
                "analysis_id": "synthetic-survival-smoke",
                "path": "strategies.comparator.transition_schedule",
            },
            "source_data": {
                "classification": "non_sensitive",
                "execution_boundary": "local_only",
                "format": "csv",
                "path": "data/synthetic-survival.csv",
                "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "columns": {"time": "time", "event": "event"},
                "row_count": 10,
                "event_count": 6,
                "censor_count": 4,
                "contains_direct_identifiers": False,
                "missing_policy": "reject",
                "additional_columns": "reject",
            },
            "fit": {
                "method": "maximum_likelihood",
                "formula": "intercept_only",
                "candidate_models": [
                    {"family": "exponential", "rationale": "Fixed constant-hazard cross-check."},
                    {"family": "weibull", "rationale": "Fixed monotone-hazard cross-check."},
                    {"family": "gompertz", "rationale": "Challenge a log-linear hazard."},
                    {"family": "gamma", "rationale": "Challenge a gamma event-time distribution."},
                    {"family": "generalized_gamma", "rationale": "Challenge the Prentice generalized gamma interface."},
                    {"family": "generalized_f", "rationale": "Challenge the Prentice generalized F interface."},
                    {"family": "lognormal", "rationale": "Challenge a non-monotone lognormal hazard."},
                    {"family": "loglogistic", "rationale": "Challenge a non-monotone loglogistic hazard."},
                ],
                "prediction_times": [0, 1, 3, 5, 5.1],
                "observed_follow_up": 5,
                "model_horizon": 5.1,
                "cross_implementation_tolerance": 1e-8,
            },
            "runtime": {"expected_packages": runtime["package_versions"]},
            "output": {
                "directory": "heor/survival-fit-executions/real-backend-smoke",
                "overwrite_policy": "fail_if_exists",
            },
            "limitations": ["Synthetic execution proves interface integrity, not evidence validity."],
            "human_gate": {
                "state": "awaiting_execution_authorization",
                "required_action": "approve_local_survival_fit_command",
            },
        }
        request_path = workspace / "heor/survival-fit-requests/real-backend-smoke.json"
        write_json(request_path, request)
        manifest_path, result = run_request(request_path, workspace, rscript, library)
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        print(
            json.dumps(
                {
                    "runtime": runtime,
                    "result": result,
                    "manifest": manifest,
                    "models": {
                        binding["family"]: json.loads((workspace / binding["path"]).read_text(encoding="utf-8"))
                        for binding in manifest["models"]
                    },
                },
                indent=2,
            )
        )
        return 0 if result["complete"] and result["eligible_for_review"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
