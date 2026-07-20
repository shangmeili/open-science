#!/usr/bin/env python3
"""Run one preflighted netmeta analysis without shell interpolation or installs."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from nma_contract import (
    EVALUATOR,
    RESULT_SCHEMA_VERSION,
    TOLERANCE,
    audit_result,
    digest,
    expected_rows,
    load_json,
    natural_effect,
    resolve_file,
    validate_request,
)


ADAPTER = Path(__file__).with_name("netmeta_adapter.R")
TIMEOUT_SECONDS = 30 * 60
BACKEND_FILES = {
    "matrix": "matrix.tsv",
    "diagnostics": "diagnostics.tsv",
    "local_inconsistency": "local-inconsistency.tsv",
    "ranking": "ranking.tsv",
    "warnings": "warnings.txt",
}


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
    completed = invoke([str(rscript), "--vanilla", str(ADAPTER), "probe", str(library)], library)
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or f"Rscript exited {completed.returncode}"
        raise RuntimeError(message)
    r_version = ""
    packages: dict[str, str] = {}
    for raw_line in completed.stdout.splitlines():
        parts = raw_line.split("\t")
        if len(parts) == 2 and parts[0] == "r_version":
            r_version = parts[1]
        elif len(parts) == 3 and parts[0] == "package":
            packages[parts[1]] = parts[2]
    if not r_version or set(packages) != {"netmeta", "meta", "metafor"}:
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


def number(value: str, label: str) -> float:
    try:
        parsed = float(value)
    except ValueError as error:
        raise RuntimeError(f"backend {label} is not numeric") from error
    if not math.isfinite(parsed):
        raise RuntimeError(f"backend {label} must be finite")
    return parsed


def optional_number(value: str, label: str) -> float | None:
    return None if value == "" else number(value, label)


def integer(value: str, label: str) -> int:
    parsed = number(value, label)
    if parsed != int(parsed):
        raise RuntimeError(f"backend {label} must be an integer")
    return int(parsed)


def relative(workspace: Path, path: Path) -> str:
    return path.resolve().relative_to(workspace.resolve()).as_posix()


def write_json(path: Path, value: dict[str, Any]) -> str:
    raw = (json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return digest(raw)


def _raw_matrix(raw_dir: Path) -> dict[tuple[str, str], dict[str, float | None]]:
    rows = read_tsv(raw_dir / BACKEND_FILES["matrix"])
    matrix: dict[tuple[str, str], dict[str, float | None]] = {}
    required = {
        "row_treatment",
        "column_treatment",
        "effect",
        "se",
        "lower",
        "upper",
        "prediction_lower",
        "prediction_upper",
    }
    for index, row in enumerate(rows):
        if set(row) != required:
            raise RuntimeError(f"backend matrix row {index} fields changed")
        key = (row["row_treatment"], row["column_treatment"])
        if key in matrix or key[0] == key[1]:
            raise RuntimeError(f"backend matrix row {index} has a duplicate or diagonal key")
        matrix[key] = {
            "effect": number(row["effect"], "matrix.effect"),
            "se": number(row["se"], "matrix.se"),
            "lower": number(row["lower"], "matrix.lower"),
            "upper": number(row["upper"], "matrix.upper"),
            "prediction_lower": optional_number(row["prediction_lower"], "matrix.prediction_lower"),
            "prediction_upper": optional_number(row["prediction_upper"], "matrix.prediction_upper"),
        }
    return matrix


def _orientation_error(
    matrix: dict[tuple[str, str], dict[str, float | None]],
    expected: list[dict[str, Any]],
    reverse: bool,
) -> float:
    maximum = 0.0
    for row in expected:
        key = (row["treat2"], row["treat1"]) if reverse else (row["treat1"], row["treat2"])
        raw = matrix.get(key)
        if raw is None:
            return math.inf
        for field in ("effect", "se", "lower", "upper"):
            maximum = max(maximum, abs(float(raw[field]) - float(row[field])))
    return maximum


def normalize_matrix(
    request: dict[str, Any],
    facts: dict[str, Any],
    raw_dir: Path,
    tau: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], float, float, bool]:
    expected_reference, expected_league = expected_rows(request, facts, tau)
    matrix = _raw_matrix(raw_dir)
    direct_error = _orientation_error(matrix, expected_league, reverse=False)
    reverse_error = _orientation_error(matrix, expected_league, reverse=True)
    if min(direct_error, reverse_error) > TOLERANCE:
        raise RuntimeError(
            "backend treatment-matrix orientation cannot be reconciled with independent WLS "
            f"(direct={direct_error:.6g}, reverse={reverse_error:.6g})"
        )
    reverse = reverse_error < direct_error

    league: list[dict[str, Any]] = []
    league_map: dict[tuple[str, str], dict[str, Any]] = {}
    max_league_error = 0.0
    for expected in expected_league:
        key = (expected["treat2"], expected["treat1"]) if reverse else (expected["treat1"], expected["treat2"])
        raw = matrix[key]
        row = {
            "treat1": expected["treat1"],
            "treat2": expected["treat2"],
            "effect": float(raw["effect"]),
            "se": float(raw["se"]),
            "lower": float(raw["lower"]),
            "upper": float(raw["upper"]),
            "natural_effect": natural_effect(request["effect"]["measure"], float(raw["effect"])),
            "prediction_lower": raw["prediction_lower"],
            "prediction_upper": raw["prediction_upper"],
        }
        max_league_error = max(
            max_league_error,
            *(abs(float(row[field]) - float(expected[field])) for field in ("effect", "se", "lower", "upper", "natural_effect")),
        )
        league.append(row)
        league_map[(row["treat1"], row["treat2"])] = row

    reference = request["reference_treatment"]
    reference_rows: list[dict[str, Any]] = []
    max_reference_error = 0.0
    expected_reference_map = {row["treatment"]: row for row in expected_reference}
    for treatment in facts["treatment_order"]:
        if treatment == reference:
            continue
        source = league_map[(treatment, reference)]
        row = {
            "treatment": treatment,
            **{
                field: source[field]
                for field in (
                    "effect",
                    "se",
                    "lower",
                    "upper",
                    "natural_effect",
                    "prediction_lower",
                    "prediction_upper",
                )
            },
        }
        expected = expected_reference_map[treatment]
        max_reference_error = max(
            max_reference_error,
            *(abs(float(row[field]) - float(expected[field])) for field in ("effect", "se", "lower", "upper", "natural_effect")),
        )
        reference_rows.append(row)
    return reference_rows, league, max_reference_error, max_league_error, reverse


def normalize_local(raw_dir: Path, reverse: bool, comparisons: list[str]) -> list[dict[str, Any]]:
    expected = set(comparisons)
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    required = {
        "row_treatment",
        "column_treatment",
        "network_effect",
        "direct_effect",
        "indirect_effect",
        "difference",
        "se_difference",
        "p_value",
    }
    for index, row in enumerate(read_tsv(raw_dir / BACKEND_FILES["local_inconsistency"])):
        if set(row) != required:
            raise RuntimeError(f"backend local-inconsistency row {index} fields changed")
        raw_left, raw_right = row["row_treatment"], row["column_treatment"]
        represented_left, represented_right = (raw_right, raw_left) if reverse else (raw_left, raw_right)
        canonical_left, canonical_right = sorted((represented_left, represented_right))
        comparison = f"{canonical_left}:{canonical_right}"
        if comparison not in expected or comparison in seen:
            raise RuntimeError(f"backend local-inconsistency row {index} has an unknown or duplicate comparison")
        seen.add(comparison)
        sign = 1.0 if (represented_left, represented_right) == (canonical_left, canonical_right) else -1.0
        direct = sign * number(row["direct_effect"], "local.direct_effect")
        indirect = sign * number(row["indirect_effect"], "local.indirect_effect")
        normalized.append(
            {
                "comparison": comparison,
                "network_effect": sign * number(row["network_effect"], "local.network_effect"),
                "direct_effect": direct,
                "indirect_effect": indirect,
                "difference": direct - indirect,
                "se_difference": number(row["se_difference"], "local.se_difference"),
                "p_value": number(row["p_value"], "local.p_value"),
            }
        )
    return sorted(normalized, key=lambda item: item["comparison"])


def normalize_ranking(request: dict[str, Any], facts: dict[str, Any], raw_dir: Path) -> dict[str, Any]:
    method = request["diagnostics"]["ranking"]
    rows = read_tsv(raw_dir / BACKEND_FILES["ranking"])
    if method == "none":
        if rows:
            raise RuntimeError("backend returned ranking rows when ranking was disabled")
        return {"method": "none", "rows": []}
    values: dict[str, float] = {}
    for index, row in enumerate(rows):
        if set(row) != {"treatment", "p_score"} or row["treatment"] in values:
            raise RuntimeError(f"backend ranking row {index} fields or treatment are invalid")
        score = number(row["p_score"], "ranking.p_score")
        if not 0 <= score <= 1:
            raise RuntimeError(f"backend ranking row {index} P-score is outside [0,1]")
        values[row["treatment"]] = score
    if set(values) != set(facts["treatment_order"]):
        raise RuntimeError("backend ranking does not cover the declared treatments")
    return {
        "method": "p_score",
        "rows": [{"treatment": treatment, "p_score": values[treatment]} for treatment in facts["treatment_order"]],
    }


def parse_diagnostics(raw_dir: Path, cycle_rank: int) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = read_tsv(raw_dir / BACKEND_FILES["diagnostics"])
    if len(rows) != 1:
        raise RuntimeError("backend diagnostics must contain exactly one row")
    row = rows[0]
    required = {
        "tau",
        "q_total",
        "df_total",
        "p_total",
        "q_heterogeneity",
        "df_heterogeneity",
        "p_heterogeneity",
        "q_inconsistency",
        "df_inconsistency",
        "p_inconsistency",
    }
    if set(row) != required:
        raise RuntimeError("backend diagnostics fields changed")
    tau = number(row["tau"], "diagnostics.tau")
    heterogeneity = {
        "tau": tau,
        "tau_squared": tau * tau,
        "q_total": number(row["q_total"], "diagnostics.q_total"),
        "df_total": integer(row["df_total"], "diagnostics.df_total"),
        "p_total": optional_number(row["p_total"], "diagnostics.p_total"),
        "q_heterogeneity": number(row["q_heterogeneity"], "diagnostics.q_heterogeneity"),
        "df_heterogeneity": integer(row["df_heterogeneity"], "diagnostics.df_heterogeneity"),
        "p_heterogeneity": optional_number(row["p_heterogeneity"], "diagnostics.p_heterogeneity"),
    }
    if cycle_rank > 0:
        global_value = {
            "method": "design_decomposition",
            "status": "estimable",
            "q": number(row["q_inconsistency"], "diagnostics.q_inconsistency"),
            "df": integer(row["df_inconsistency"], "diagnostics.df_inconsistency"),
            "p_value": number(row["p_inconsistency"], "diagnostics.p_inconsistency"),
        }
    else:
        global_value = {
            "method": "design_decomposition",
            "status": "not_estimable_tree_network",
            "q": None,
            "df": None,
            "p_value": None,
        }
    return heterogeneity, global_value


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
    expected_runtime = request["runtime"]
    if any(
        (
            runtime["r_version"] != expected_runtime["r_version"],
            runtime["package_versions"] != expected_runtime["package_versions"],
            runtime["adapter_sha256"] != expected_runtime["adapter_sha256"],
        )
    ):
        raise ValueError("isolated R runtime identity does not match the request")

    source_path = resolve_file(workspace, request["source_data"]["path"])
    if source_path is None:
        raise ValueError("source data changed or became unavailable after preflight")
    final_relative = request["output"]["directory"]
    final_dir = workspace / final_relative
    if final_dir.exists():
        raise FileExistsError(f"output already exists: {final_relative}")
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    temporary = final_dir.parent / f".{request['execution_id']}.tmp-{os.getpid()}"
    if temporary.exists():
        raise FileExistsError(f"temporary output already exists: {temporary}")
    backend_dir = temporary / "backend"
    adapter_dir = temporary / "adapter"
    backend_dir.mkdir(parents=True)
    adapter_dir.mkdir()
    try:
        command = [
            str(rscript),
            "--vanilla",
            str(ADAPTER),
            "run",
            str(source_path),
            request["effect"]["measure"],
            request["model"]["type"],
            request["reference_treatment"],
            request["effect"]["favorable_direction"],
            request["diagnostics"]["ranking"],
            str(backend_dir),
            str(library),
        ]
        completed = invoke(command, library, temporary)
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip() or f"Rscript exited {completed.returncode}"
            raise RuntimeError(message)
        if completed.stdout.strip():
            raise RuntimeError("backend emitted unexpected standard output")
        for filename in BACKEND_FILES.values():
            if not (backend_dir / filename).is_file():
                raise RuntimeError(f"backend omitted required output {filename}")
        shutil.copy2(ADAPTER, adapter_dir / ADAPTER.name)

        heterogeneity, global_inconsistency = parse_diagnostics(backend_dir, int(facts["cycle_rank"]))
        tau = float(heterogeneity["tau"])
        if request["model"]["type"] == "common" and tau != 0:
            raise RuntimeError("backend reported non-zero tau for the common model")
        reference_rows, league_rows, reference_error, league_error, reverse = normalize_matrix(
            request, facts, backend_dir, tau
        )
        local_rows = normalize_local(backend_dir, reverse, facts["comparisons"])
        ranking = normalize_ranking(request, facts, backend_dir)
        warnings = [
            line.strip()
            for line in (backend_dir / BACKEND_FILES["warnings"]).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        def binding(path: Path) -> dict[str, str]:
            return {
                "path": f"{final_relative}/{path.relative_to(temporary).as_posix()}",
                "sha256": digest(path.read_bytes()),
            }

        adapter_binding = binding(adapter_dir / ADAPTER.name)
        backend_bindings = [
            {"id": identifier, **binding(backend_dir / filename)}
            for identifier, filename in BACKEND_FILES.items()
        ]
        manifest = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "execution_id": request["execution_id"],
            "status": "awaiting_model_review",
            "request": {"path": relative(workspace, request_path), "sha256": digest(request_raw)},
            "source_data": {"path": request["source_data"]["path"], "sha256": request["source_data"]["sha256"]},
            "evidence_synthesis": {
                "path": request["evidence_synthesis"]["path"],
                "sha256": request["evidence_synthesis"]["sha256"],
            },
            "runtime": {
                "r_version": runtime["r_version"],
                "rscript_path": runtime["rscript_path"],
                "rscript_sha256": runtime["rscript_sha256"],
                "package_versions": runtime["package_versions"],
                "adapter": adapter_binding,
            },
            "backend_outputs": backend_bindings,
            "network": {
                "treatments": facts["treatment_order"],
                "reference_treatment": request["reference_treatment"],
                "study_count": facts["study_count"],
                "direct_comparison_count": facts["direct_comparison_count"],
                "cycle_rank": facts["cycle_rank"],
                "connected": True,
            },
            "model": {
                "effect_measure": request["effect"]["measure"],
                "scale": request["effect"]["scale"],
                "likelihood": "normal",
                "link": "identity",
                "type": request["model"]["type"],
                "tau_method": request["model"]["tau_method"],
                "tau": tau,
                "tau_squared": tau * tau,
                "prediction_interval": request["model"]["prediction_interval"],
            },
            "estimates_vs_reference": reference_rows,
            "league_table": league_rows,
            "heterogeneity": heterogeneity,
            "inconsistency": {"global": global_inconsistency, "local": local_rows},
            "ranking": ranking,
            "cross_implementation": {
                "evaluator": EVALUATOR,
                "scope": "complete_common_effect"
                if request["model"]["type"] == "common"
                else "conditional_on_backend_tau",
                "max_abs_reference_error": reference_error,
                "max_abs_league_error": league_error,
                "tolerance": TOLERANCE,
                "passed": max(reference_error, league_error) <= TOLERANCE,
            },
            "warnings": warnings,
            "limitations": request["limitations"],
            "human_gate": request["human_gate"],
        }
        write_json(temporary / "manifest.json", manifest)
        temporary.rename(final_dir)
        audit = audit_result(final_dir / "manifest.json", workspace)
        if not audit["complete"]:
            shutil.rmtree(final_dir, ignore_errors=True)
            raise RuntimeError("generated result failed independent audit:\n- " + "\n- ".join(audit["errors"]))
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    return final_dir / "manifest.json", audit


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
            print(json.dumps(probe(rscript, library), indent=2, ensure_ascii=False, allow_nan=False))
            return 0
        manifest_path, audit = run_request(args.request, args.workspace, rscript, library)
        print(
            json.dumps(
                {"result_manifest": str(manifest_path), **audit},
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            )
        )
        return 0 if audit["complete"] and audit["eligible_for_review"] else 1
    except (OSError, UnicodeError, ValueError, RuntimeError, subprocess.TimeoutExpired) as error:
        print(json.dumps({"complete": False, "errors": [str(error)]}, indent=2, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
