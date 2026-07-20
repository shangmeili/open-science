#!/usr/bin/env python3
"""Run an isolated, preflighted paired patient-row survival bootstrap."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from paired_bootstrap_contract import (
    DRAW_FORMAT,
    EVALUATOR,
    EVALUATOR_PATH,
    PLAN_FORMAT,
    REPLICATE_FORMAT,
    RESULT_SCHEMA_VERSION,
    RNG_ALGORITHM,
    RNG_VERSION,
    TOLERANCE,
    audit_result,
    bootstrap_frequencies,
    digest,
    expected_curve,
    expected_parameterization,
    load_json,
    validate_request,
)


ADAPTER = Path(__file__).with_name("paired_survival_bootstrap_adapter.R")
TIMEOUT_SECONDS = 6 * 60 * 60


def executable(value: str) -> Path:
    found = shutil.which(value)
    candidate = Path(found if found else value).expanduser().resolve()
    if not candidate.is_file():
        raise ValueError(f"Rscript executable not found: {value}")
    return candidate


def isolated_env(library: Path) -> dict[str, str]:
    keep = {
        name: os.environ[name]
        for name in ("HOME", "PATH", "TMPDIR", "TEMP", "TMP", "SystemRoot")
        if name in os.environ
    }
    keep.update(
        {
            "R_LIBS_USER": str(library),
            "R_LIBS_SITE": "",
            "R_ENVIRON_USER": "",
            "R_PROFILE_USER": "",
            "http_proxy": "http://127.0.0.1:9",
            "https_proxy": "http://127.0.0.1:9",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "",
            "no_proxy": "",
        }
    )
    return keep


def invoke(command: list[str], library: Path, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        env=isolated_env(library),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=TIMEOUT_SECONDS,
        check=False,
    )


def probe(rscript: Path, library: Path) -> dict[str, Any]:
    result = invoke([str(rscript), "--vanilla", str(ADAPTER), "probe", str(library)], library)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip() or f"Rscript exited {result.returncode}")
    r_version = ""
    packages: dict[str, str] = {}
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) == 2 and parts[0] == "r_version":
            r_version = parts[1]
        elif len(parts) == 3 and parts[0] == "package":
            packages[parts[1]] = parts[2]
    if not r_version or set(packages) != {"survHE", "flexsurv", "survival"}:
        raise RuntimeError("R runtime probe returned an incomplete package identity")
    return {
        "r_version": r_version,
        "rscript_sha256": digest(rscript.read_bytes()),
        "package_versions": packages,
    }


def relative(workspace: Path, path: Path) -> str:
    return path.resolve().relative_to(workspace.resolve()).as_posix()


def resolve_output_directory(workspace: Path, relative_path: str) -> Path:
    """Create only real workspace parents and reject any existing output."""

    if not relative_path or not Path(relative_path).parts:
        raise ValueError("output directory is invalid")
    root = workspace.resolve()
    parent = root
    for part in Path(relative_path).parent.parts:
        parent /= part
        if parent.is_symlink():
            raise ValueError("output directory cannot traverse a symlink")
        if parent.exists():
            if not parent.is_dir():
                raise ValueError("output directory parent must be a directory")
        else:
            parent.mkdir()
        if not parent.resolve().is_relative_to(root):
            raise ValueError("output directory must remain inside the workspace")
    final = root / relative_path
    if final.is_symlink() or final.exists():
        raise FileExistsError(f"output already exists: {relative_path}")
    return final


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_json(path: Path, value: dict[str, Any]) -> str:
    raw = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return digest(raw)


def write_jsonl(path: Path, values: list[dict[str, Any]]) -> str:
    raw = b"".join(
        (json.dumps(value, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")
        for value in values
    )
    path.write_bytes(raw)
    return digest(raw)


def write_plan(path: Path, strategy_positions: list[list[int]], iterations: int, seed: int) -> str:
    row_count = sum(len(positions) for positions in strategy_positions)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["replicate_index", *(f"row_{index}" for index in range(1, row_count + 1))])
        for replicate, frequencies in enumerate(bootstrap_frequencies(strategy_positions, iterations, seed), start=1):
            writer.writerow([replicate, *frequencies])
    return digest(path.read_bytes())


def normalized_replicates(
    raw_dir: Path,
    curves: list[dict[str, str]],
    time_grid: list[float],
    iterations: int,
    tolerance: float,
) -> tuple[list[dict[str, Any]], bool, bool, int]:
    replicate_rows = {int(row["replicate_index"]): row for row in read_tsv(raw_dir / "replicates.tsv")}
    model_rows = {
        (int(row["replicate_index"]), int(row["curve_position"])): row
        for row in read_tsv(raw_dir / "models.tsv")
    }
    parameter_rows = read_tsv(raw_dir / "parameters.tsv")
    prediction_rows = read_tsv(raw_dir / "predictions.tsv")
    results: list[dict[str, Any]] = []
    cross_complete = True
    coherence_complete = True
    failed_replicates = 0
    for replicate_index in range(1, iterations + 1):
        backend = replicate_rows.get(replicate_index)
        reasons = [] if backend is None else [item.strip() for item in backend["failure_reasons"].split(" | ") if item.strip()]
        if backend is None:
            reasons.append("The backend omitted this replicate.")
        normalized_curves: list[dict[str, Any]] = []
        survival_curves: list[list[float]] = []
        row_complete = True
        for curve_position, curve in enumerate(curves, start=1):
            model = model_rows.get((replicate_index, curve_position))
            warnings = [] if model is None else [item.strip() for item in model["warnings"].split(" | ") if item.strip()]
            common = {
                "target_path": curve["target_path"],
                "strategy_id": curve["strategy_id"],
                "endpoint": curve["endpoint"],
                "family": curve["family"],
            }
            if model is None or model["status"] != "converged":
                row_complete = cross_complete = False
                failure = warnings or ["The backend omitted or failed this selected curve."]
                reasons.extend(failure)
                normalized_curves.append(
                    {
                        **common,
                        "status": "failed",
                        "parameterization": "",
                        "parameters": [],
                        "survival": [],
                        "warnings": failure,
                        "crosscheck": {"status": "fit_failed", "max_abs_survival_error": None},
                    }
                )
                survival_curves.append([])
                continue
            parameters = [
                {"name": row["name"], "estimate": float(row["estimate"])}
                for row in parameter_rows
                if int(row["replicate_index"]) == replicate_index and int(row["curve_position"]) == curve_position
            ]
            predictions = [
                (float(row["time"]), float(row["survival"]))
                for row in prediction_rows
                if int(row["replicate_index"]) == replicate_index and int(row["curve_position"]) == curve_position
            ]
            prediction_times = [item[0] for item in predictions]
            observed = [item[1] for item in predictions]
            parameter_map = {item["name"]: item["estimate"] for item in parameters}
            evaluation_error: str | None = None
            maximum_error: float | None = None
            if len(predictions) != len(time_grid) or any(
                abs(observed_time - expected_time) > 1e-12
                for observed_time, expected_time in zip(prediction_times, time_grid)
            ):
                evaluation_error = "The backend prediction grid does not match the analysis grid."
            elif model["parameterization"] != expected_parameterization(curve["family"]):
                evaluation_error = "The backend parameterization does not match the selected family contract."
            else:
                try:
                    calculated = [expected_curve(curve["family"], parameter_map, time)[0] for time in time_grid]
                    maximum_error = max(abs(left - right) for left, right in zip(observed, calculated))
                except (KeyError, TypeError, ValueError) as error:
                    evaluation_error = f"Independent evaluator failed: {error}"
            check_status = "passed" if evaluation_error is None and maximum_error is not None and maximum_error <= tolerance else "failed"
            if check_status != "passed":
                row_complete = cross_complete = False
                reasons.append(evaluation_error or "The independent survival cross-check exceeded tolerance.")
            normalized_curves.append(
                {
                    **common,
                    "status": "converged",
                    "parameterization": model["parameterization"],
                    "parameters": parameters,
                    "survival": observed,
                    "warnings": warnings,
                    "crosscheck": {"status": check_status, "max_abs_survival_error": maximum_error},
                }
            )
            survival_curves.append(observed)
        for strategy_index in range(len(curves) // 2):
            pfs = survival_curves[strategy_index * 2]
            overall = survival_curves[strategy_index * 2 + 1]
            if pfs and overall and any(pfs_value > os_value + TOLERANCE for pfs_value, os_value in zip(pfs, overall)):
                row_complete = coherence_complete = False
                reasons.append(f"Strategy {curves[strategy_index * 2]['strategy_id']} has PFS above OS on the analysis grid.")
        unique_reasons = list(dict.fromkeys(reasons))
        if not row_complete:
            failed_replicates += 1
        results.append(
            {
                "replicate_index": replicate_index,
                "status": "complete" if row_complete else "failed",
                "curves": normalized_curves,
                "failure_reasons": [] if row_complete else unique_reasons or ["The replicate did not satisfy the complete joint-curve contract."],
            }
        )
    return results, cross_complete, coherence_complete, failed_replicates


def run_request(request_path: Path, workspace: Path, rscript: Path, library: Path) -> tuple[Path, dict[str, Any]]:
    workspace = workspace.resolve()
    request_path = request_path.resolve()
    if not request_path.is_relative_to(workspace) or request_path.is_symlink():
        raise ValueError("request must be a regular file inside the workspace")
    request, request_raw = load_json(request_path)
    errors, facts = validate_request(request, workspace)
    if errors:
        raise ValueError("request failed preflight:\n- " + "\n- ".join(errors))
    runtime = probe(rscript, library)
    if runtime["package_versions"] != request["runtime"]["expected_packages"]:
        raise ValueError(
            "isolated runtime package versions do not match request: "
            + json.dumps(runtime["package_versions"], sort_keys=True)
        )

    final_relative = request["output"]["directory"]
    final_dir = resolve_output_directory(workspace, final_relative)
    temporary = final_dir.parent / f".{request['execution_id']}.tmp-{os.getpid()}"
    if temporary.exists():
        raise FileExistsError(f"temporary output already exists: {temporary}")
    temporary.mkdir()
    try:
        plan_path = temporary / "bootstrap-plan.csv"
        write_plan(plan_path, facts["strategy_positions"], facts["iterations"], facts["seed"])
        curve_specs = ";".join(
            f"{curve['strategy_id']}|{curve['endpoint']}|{curve['family']}" for curve in facts["curves"]
        )
        command = [
            str(rscript),
            "--vanilla",
            str(ADAPTER),
            "run",
            str(facts["source_path"]),
            str(plan_path),
            curve_specs,
            ",".join(format(time, ".17g") for time in facts["time_grid"]),
            str(temporary),
            str(library),
        ]
        completed = invoke(command, library, temporary)
        log = (
            "AI4HEOR isolated paired survival bootstrap\n"
            f"exit_code: {completed.returncode}\n"
            "stdout:\n"
            + completed.stdout[-1_000_000:]
            + "\nstderr:\n"
            + completed.stderr[-1_000_000:]
        )
        (temporary / "execution.log").write_text(log, encoding="utf-8")
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or f"Rscript exited {completed.returncode}")
        runtime_rows = {row["package"]: row["version"] for row in read_tsv(temporary / "runtime.tsv")}
        if runtime_rows != runtime["package_versions"]:
            raise RuntimeError("R execution package versions drifted after preflight")
        shutil.copy2(ADAPTER, temporary / ADAPTER.name)

        replicates, cross_complete, coherence_complete, failed = normalized_replicates(
            temporary,
            facts["curves"],
            facts["time_grid"],
            facts["iterations"],
            float(request["bootstrap"]["cross_implementation_tolerance"]),
        )
        replicate_path = temporary / "replicate-results.jsonl"
        write_jsonl(replicate_path, replicates)
        eligible = failed == 0 and cross_complete and coherence_complete
        candidate_path = temporary / "joint-survival-draws.candidate.jsonl"
        if eligible:
            write_jsonl(
                candidate_path,
                [
                    {
                        "draw_index": row["replicate_index"],
                        "curves": [curve["survival"] for curve in row["curves"]],
                    }
                    for row in replicates
                ],
            )

        for raw_name in ("replicates.tsv", "models.tsv", "parameters.tsv", "predictions.tsv", "runtime.tsv"):
            (temporary / raw_name).unlink()

        def bound(name: str) -> dict[str, str]:
            path = temporary / name
            return {"path": f"{final_relative}/{name}", "sha256": digest(path.read_bytes())}

        plan_binding = bound("bootstrap-plan.csv")
        replicate_binding = bound("replicate-results.jsonl")
        candidate_binding = bound("joint-survival-draws.candidate.jsonl") if eligible else None
        adapter_binding = bound(ADAPTER.name)
        session_binding = bound("session-info.txt")
        log_binding = bound("execution.log")
        manifest = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "execution_id": request["execution_id"],
            "status": "complete" if eligible else "incomplete",
            "request": {"path": relative(workspace, request_path), "sha256": digest(request_raw)},
            "analysis": request["analysis"],
            "partitioned_survival": request["partitioned_survival"],
            "curve_materializations": request["curve_materializations"],
            "source_data": {
                field: request["source_data"][field]
                for field in ("path", "sha256", "row_count", "strategy_counts")
            },
            "runtime": {
                "backend": "survHE",
                "method": "paired_patient_bootstrap",
                "r_version": runtime["r_version"],
                "rscript_sha256": runtime["rscript_sha256"],
                "package_versions": runtime["package_versions"],
                "adapter_path": adapter_binding["path"],
                "adapter_sha256": adapter_binding["sha256"],
                "session_info_path": session_binding["path"],
                "session_info_sha256": session_binding["sha256"],
                "execution_log_path": log_binding["path"],
                "execution_log_sha256": log_binding["sha256"],
            },
            "bootstrap": {
                field: request["bootstrap"][field]
                for field in (
                    "method",
                    "rng",
                    "rng_version",
                    "seed",
                    "iterations",
                    "resampling_unit",
                    "strategy_resampling_design",
                    "endpoint_sampling",
                    "between_strategy_assumption",
                    "time_grid_years",
                )
            }
            | {
                "evaluator": {"id": EVALUATOR, "sha256": digest(EVALUATOR_PATH.read_bytes())},
                "curve_order": [curve["target_path"] for curve in facts["curves"]],
                "resampling_plan": {**plan_binding, "format": PLAN_FORMAT, "row_count": facts["iterations"]},
                "replicate_results": {**replicate_binding, "format": REPLICATE_FORMAT, "row_count": facts["iterations"]},
                "candidate_draws": (
                    {**candidate_binding, "format": DRAW_FORMAT, "row_count": facts["iterations"]}
                    if candidate_binding is not None
                    else None
                ),
                "completed_replicates": facts["iterations"] - failed,
                "failed_replicates": failed,
                "cross_implementation_complete": cross_complete,
                "curve_coherence_complete": coherence_complete,
                "eligible_for_joint_packaging": eligible,
            },
            "limitations": request["limitations"]
            + [
                "Whole-subject row resampling preserves observed within-subject PFS/OS dependence but does not establish that censoring or endpoint definitions are appropriate.",
                "Parallel treatment arms are resampled independently within arm; between-strategy dependence is a declared conditional-independence design assumption, not an observed correlation.",
                "Numerical reproduction and complete non-crossing rows do not establish statistical, clinical, external, or extrapolation validity.",
                "Candidate draws require separate Human method review and canonical joint-survival packaging before deterministic PSA use.",
            ],
            "human_gate": {
                "state": "awaiting_bootstrap_method_review",
                "required_action": "review_paired_bootstrap_before_joint_packaging",
            },
        }
        write_json(temporary / "result-manifest.json", manifest)
        temporary.rename(final_dir)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    result_errors, result_facts = audit_result(final_dir / "result-manifest.json", workspace)
    return final_dir / "result-manifest.json", {"complete": not result_errors, "errors": result_errors, **result_facts}


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    probe_parser = subparsers.add_parser("probe")
    probe_parser.add_argument("--rscript", default="Rscript")
    probe_parser.add_argument("--library", type=Path, required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("request", type=Path)
    run_parser.add_argument("--workspace", type=Path, required=True)
    run_parser.add_argument("--rscript", default="Rscript")
    run_parser.add_argument("--library", type=Path, required=True)
    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("manifest", type=Path)
    audit_parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "audit":
            errors, facts = audit_result(args.manifest, args.workspace.resolve())
            print(json.dumps({"complete": not errors, "errors": errors, **facts}, indent=2, ensure_ascii=False))
            return 0 if not errors else 1
        rscript = executable(args.rscript)
        library = args.library.expanduser().resolve()
        if not library.is_dir():
            raise ValueError(f"isolated R library is missing: {library}")
        if args.command == "probe":
            print(json.dumps(probe(rscript, library), indent=2, ensure_ascii=False))
            return 0
        manifest, result = run_request(args.request, args.workspace, rscript, library)
        print(json.dumps({"result_manifest": str(manifest), **result}, indent=2, ensure_ascii=False))
        return 0 if result.get("complete") and result.get("eligible_for_joint_packaging") else 1
    except (OSError, UnicodeError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"complete": False, "errors": [str(error)]}, indent=2, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
