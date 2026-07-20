#!/usr/bin/env python3
"""Run a preflighted survHE MLE fit without shell interpolation or package install."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from survhe_execution_contract import (
    EVALUATOR,
    MANDATORY_FAMILIES,
    REQUIRED_CROSSCHECKS,
    RESULT_SCHEMA_VERSION,
    SCHEMA_VERSION,
    UNCERTAINTY_SCHEMA_VERSION,
    audit_result,
    digest,
    expected_curve,
    load_json,
    validate_request,
)


ADAPTER = Path(__file__).with_name("survhe_mle_adapter.R")
TIMEOUT_SECONDS = 30 * 60


def executable(value: str) -> Path:
    found = shutil.which(value)
    candidate = Path(found if found else value).expanduser().resolve()
    if not candidate.is_file():
        raise ValueError(f"Rscript executable not found: {value}")
    return candidate


def isolated_env(library: Path) -> dict[str, str]:
    keep = {name: os.environ[name] for name in ("HOME", "PATH", "TMPDIR", "TEMP", "TMP", "SystemRoot") if name in os.environ}
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
        message = result.stderr.strip() or result.stdout.strip() or f"Rscript exited {result.returncode}"
        raise RuntimeError(message)
    r_version = ""
    packages: dict[str, str] = {}
    for raw_line in result.stdout.splitlines():
        parts = raw_line.split("\t")
        if len(parts) == 2 and parts[0] == "r_version":
            r_version = parts[1]
        elif len(parts) == 3 and parts[0] == "package":
            packages[parts[1]] = parts[2]
    if not r_version or set(packages) != {"survHE", "flexsurv", "survival"}:
        raise RuntimeError("R runtime probe returned an incomplete package identity")
    return {
        "r_version": r_version,
        "rscript_path": str(rscript),
        "rscript_sha256": digest(rscript.read_bytes()),
        "package_versions": packages,
        "adapter_sha256": digest(ADAPTER.read_bytes()),
    }


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def optional_number(value: str) -> float | None:
    return None if value == "" else float(value)


def relative(workspace: Path, path: Path) -> str:
    return path.resolve().relative_to(workspace.resolve()).as_posix()


def write_json(path: Path, value: dict[str, Any]) -> str:
    raw = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return hashlib.sha256(raw).hexdigest()


def build_model_outputs(
    raw_dir: Path,
    final_dir: Path,
    final_relative: str,
    families: list[str],
    tolerance: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool, int]:
    model_rows = {row["family"]: row for row in read_tsv(raw_dir / "models.tsv")}
    parameter_rows = read_tsv(raw_dir / "parameters.tsv")
    prediction_rows = read_tsv(raw_dir / "predictions.tsv")
    models_dir = final_dir / "models"
    models_dir.mkdir()
    bindings: list[dict[str, Any]] = []
    checks: list[dict[str, Any]] = []
    cross_complete = True
    converged = 0
    for family in families:
        row = model_rows.get(family)
        if row is None:
            raise RuntimeError(f"R output omitted requested family {family}")
        status = row["status"]
        warnings = [item.strip() for item in row["warnings"].split(" | ") if item.strip()]
        model_path = models_dir / f"{family}.json"
        if status == "failed":
            model = {
                "schema_version": SCHEMA_VERSION,
                "family": family,
                "status": "failed",
                "fit_statistics": {"aic": None, "bic": None, "log_likelihood": None},
                "parameterization": "",
                "parameters": [],
                "landmarks": [],
                "warnings": warnings or ["The backend reported a failed fit without a diagnostic message."],
            }
            check_status = "fit_failed"
            max_survival_error = max_hazard_error = None
            if family in MANDATORY_FAMILIES:
                cross_complete = False
        elif status == "converged":
            converged += 1
            parameters = [
                {"name": item["name"], "estimate": float(item["estimate"])}
                for item in parameter_rows
                if item["family"] == family
            ]
            landmarks = [
                {
                    "time": float(item["time"]),
                    "survival": float(item["survival"]),
                    "hazard": optional_number(item["hazard"]),
                }
                for item in prediction_rows
                if item["family"] == family
            ]
            model = {
                "schema_version": SCHEMA_VERSION,
                "family": family,
                "status": "converged",
                "fit_statistics": {
                    "aic": float(row["aic"]),
                    "bic": float(row["bic"]),
                    "log_likelihood": float(row["log_likelihood"]),
                },
                "parameterization": row["parameterization"],
                "parameters": parameters,
                "landmarks": landmarks,
                "warnings": warnings,
            }
            parameter_map = {item["name"]: item["estimate"] for item in parameters}
            survival_errors: list[float] = []
            hazard_errors: list[float] = []
            evaluation_error: str | None = None
            try:
                for landmark in landmarks:
                    expected_survival, expected_hazard = expected_curve(family, parameter_map, landmark["time"])
                    survival_errors.append(abs(landmark["survival"] - expected_survival))
                    if expected_hazard is not None:
                        hazard_errors.append(abs(float(landmark["hazard"]) - expected_hazard))
            except (KeyError, TypeError, ValueError) as error:
                evaluation_error = str(error)
            if evaluation_error is None:
                max_survival_error = max(survival_errors, default=0.0)
                max_hazard_error = max(hazard_errors, default=0.0)
                check_status = "passed" if max(max_survival_error, max_hazard_error) <= tolerance else "failed"
            else:
                model["warnings"].append(f"Independent evaluator failed: {evaluation_error}")
                max_survival_error = max_hazard_error = None
                check_status = "failed"
            cross_complete = cross_complete and check_status == "passed"
        else:
            raise RuntimeError(f"R output returned unsupported status for {family}: {status}")
        model_sha = write_json(model_path, model)
        bindings.append(
            {
                "family": family,
                "status": status,
                "path": f"{final_relative}/models/{family}.json",
                "sha256": model_sha,
            }
        )
        checks.append(
            {
                "family": family,
                "status": check_status,
                "max_abs_survival_error": max_survival_error,
                "max_abs_hazard_error": max_hazard_error,
            }
        )
    return bindings, checks, cross_complete, converged


def build_parameter_uncertainty_outputs(
    raw_dir: Path,
    final_dir: Path,
    final_relative: str,
    families: list[str],
    model_bindings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    status_rows = {row["family"]: row for row in read_tsv(raw_dir / "uncertainty-status.tsv")}
    parameter_rows = read_tsv(raw_dir / "estimation-parameters.tsv")
    covariance_rows = read_tsv(raw_dir / "covariance.tsv")
    output_dir = final_dir / "parameter-uncertainty"
    output_dir.mkdir()
    bindings: list[dict[str, Any]] = []
    complete = True
    for family, model_binding in zip(families, model_bindings):
        if model_binding["status"] == "failed":
            bindings.append({"family": family, "status": "fit_failed", "path": None, "sha256": None})
            continue
        row = status_rows.get(family)
        if row is None or row.get("status") not in {"available", "unavailable"}:
            raise RuntimeError(f"R output omitted parameter uncertainty status for {family}")
        status = row["status"]
        artifact_path = output_dir / f"{family}.json"
        common = {
            "schema_version": UNCERTAINTY_SCHEMA_VERSION,
            "family": family,
            "status": status,
            "source_model": {"path": model_binding["path"], "sha256": model_binding["sha256"]},
            "sampling_scope": "within_one_absolute_curve_only",
            "limitations": [
                "The covariance is an asymptotic inverse-observed-Hessian estimate on the flexsurv estimation scale.",
                "It represents parameter dependence within this one fitted absolute curve only.",
                "It does not establish dependence between PFS and OS or between strategies and cannot authorize joint survival PSA rows.",
            ],
        }
        if status == "unavailable":
            complete = False
            artifact = {
                **common,
                "estimation_scale": None,
                "parameter_order": [],
                "estimates": [],
                "covariance_matrix": [],
                "inverse_transforms": [],
                "covariance_method": None,
                "sampling_distribution": None,
                "reason": row.get("reason") or "The backend did not expose an auditable covariance matrix.",
            }
        else:
            parameters = sorted(
                (item for item in parameter_rows if item["family"] == family),
                key=lambda item: int(item["position"]),
            )
            size = len(parameters)
            matrix = [[0.0] * size for _ in range(size)]
            entries = [item for item in covariance_rows if item["family"] == family]
            if len(entries) != size * size:
                raise RuntimeError(f"R covariance output has the wrong size for {family}")
            for item in entries:
                row_index = int(item["row_position"]) - 1
                column_index = int(item["column_position"]) - 1
                if not 0 <= row_index < size or not 0 <= column_index < size:
                    raise RuntimeError(f"R covariance position is invalid for {family}")
                matrix[row_index][column_index] = float(item["value"])
            artifact = {
                **common,
                "estimation_scale": "unconstrained_real_line",
                "parameter_order": [item["name"] for item in parameters],
                "estimates": [float(item["estimate"]) for item in parameters],
                "covariance_matrix": matrix,
                "inverse_transforms": [item["inverse_transform"] for item in parameters],
                "covariance_method": "inverse_observed_hessian",
                "sampling_distribution": "asymptotic_multivariate_normal",
                "reason": None,
            }
        artifact_sha = write_json(artifact_path, artifact)
        bindings.append(
            {
                "family": family,
                "status": status,
                "path": f"{final_relative}/parameter-uncertainty/{family}.json",
                "sha256": artifact_sha,
            }
        )
    return bindings, complete


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
    final_dir = workspace / final_relative
    if final_dir.exists():
        raise FileExistsError(f"output already exists: {final_relative}")
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = final_dir.parent / f".{request['execution_id']}.tmp-{os.getpid()}"
    if temporary.exists():
        raise FileExistsError(f"temporary output already exists: {temporary}")
    temporary.mkdir()
    try:
        command = [
            str(rscript),
            "--vanilla",
            str(ADAPTER),
            "run",
            str(facts["source_path"]),
            request["source_data"]["columns"]["time"],
            request["source_data"]["columns"]["event"],
            ",".join(facts["families"]),
            ",".join(format(item, ".17g") for item in facts["prediction_times"]),
            str(temporary),
            str(library),
        ]
        completed = invoke(command, library, temporary)
        log = (
            "AI4HEOR isolated survHE execution\n"
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

        shutil.copy2(ADAPTER, temporary / "survhe_mle_adapter.R")
        bindings, checks, cross_complete, converged = build_model_outputs(
            temporary,
            temporary,
            final_relative,
            facts["families"],
            float(request["fit"]["cross_implementation_tolerance"]),
        )
        uncertainty_bindings, uncertainty_complete = build_parameter_uncertainty_outputs(
            temporary,
            temporary,
            final_relative,
            facts["families"],
            bindings,
        )
        for raw_name in (
            "models.tsv",
            "parameters.tsv",
            "predictions.tsv",
            "runtime.tsv",
            "uncertainty-status.tsv",
            "estimation-parameters.tsv",
            "covariance.tsv",
        ):
            (temporary / raw_name).unlink()
        failed = len(facts["families"]) - converged
        numerical_cross_failure = any(check["status"] == "failed" for check in checks)
        status = (
            "cross_implementation_failed"
            if numerical_cross_failure
            else "execution_complete_with_model_failures"
            if failed
            else "execution_complete"
        )

        def bound(name: str) -> dict[str, str]:
            path = temporary / name
            return {"path": f"{final_relative}/{name}", "sha256": digest(path.read_bytes())}

        adapter_binding = bound("survhe_mle_adapter.R")
        session_binding = bound("session-info.txt")
        log_binding = bound("execution.log")
        km_binding = bound("km-overlay.png")
        log_hazard_binding = bound("log-cumulative-hazard.png")
        hazard_binding = bound("hazard.png")
        manifest = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "execution_id": request["execution_id"],
            "status": status,
            "request": {"path": relative(workspace, request_path), "sha256": digest(request_raw)},
            "source_data": {
                field: request["source_data"][field]
                for field in ("path", "sha256", "row_count", "event_count", "censor_count")
            },
            "runtime": {
                "backend": "survHE",
                "method": "maximum_likelihood",
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
            "model_order": facts["families"],
            "models": bindings,
            "parameter_uncertainty": {
                "artifact_schema_version": UNCERTAINTY_SCHEMA_VERSION,
                "scope": "within_model_curve_only",
                "joint_curve_draw_authority": False,
                "bindings": uncertainty_bindings,
                "complete": uncertainty_complete,
            },
            "diagnostics": {
                "km_overlay_path": km_binding["path"],
                "km_overlay_sha256": km_binding["sha256"],
                "log_cumulative_hazard_path": log_hazard_binding["path"],
                "log_cumulative_hazard_sha256": log_hazard_binding["sha256"],
                "hazard_plot_path": hazard_binding["path"],
                "hazard_plot_sha256": hazard_binding["sha256"],
            },
            "cross_implementation": {
                "evaluator": EVALUATOR,
                "tolerance": request["fit"]["cross_implementation_tolerance"],
                "checks": checks,
                "complete": cross_complete,
            },
            "limitations": request["limitations"]
            + [
                "Package output and numerical agreement do not establish internal, external, or clinical validity.",
                "The fixed adapter performs no package installation and does not claim operating-system network isolation.",
                "Every converged admitted family receives an independent first-party survival and hazard cross-check.",
                "Exported covariance represents parameter dependence within one fitted curve only and cannot supply joint PFS/OS or between-strategy dependence.",
            ],
            "human_gate": {
                "state": "awaiting_human_review",
                "required_action": "review_survival_extrapolation",
            },
        }
        write_json(temporary / "result-manifest.json", manifest)
        temporary.rename(final_dir)
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    result = audit_result(final_dir / "result-manifest.json", workspace)
    return final_dir / "result-manifest.json", result


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
    args = parser.parse_args()
    try:
        rscript = executable(args.rscript)
        library = args.library.expanduser().resolve()
        if not library.is_dir():
            raise ValueError(f"isolated R library is missing: {library}")
        if args.command == "probe":
            print(json.dumps(probe(rscript, library), indent=2, ensure_ascii=False))
            return 0
        manifest, result = run_request(args.request, args.workspace, rscript, library)
        print(json.dumps({"result_manifest": str(manifest), **result}, indent=2, ensure_ascii=False))
        return 0 if result["complete"] and result["eligible_for_review"] else 1
    except (OSError, UnicodeError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"complete": False, "errors": [str(error)]}, indent=2, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
