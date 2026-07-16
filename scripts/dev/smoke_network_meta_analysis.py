#!/usr/bin/env python3
"""Run common and random NMA interface smokes against an installed netmeta library."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SKILL_SCRIPTS = ROOT / "runtime/skills/core/heor-network-meta-analysis/scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))
sys.path.insert(0, str(ROOT / "scripts/dev"))

from nma_contract import digest  # noqa: E402
from run_netmeta import executable, probe, run_request  # noqa: E402
from test_network_meta_analysis import build_workspace, write_json  # noqa: E402


def make_random_fixture_estimable(workspace: Path, request: dict[str, Any]) -> None:
    rows = [
        ("study1", "a", "b", 0.2),
        ("study2", "b", "c", 0.1),
        ("study3", "a", "c", 0.4),
        ("study4", "a", "b", 1.2),
        ("study5", "b", "c", -0.8),
        ("study6", "a", "c", 0.9),
        ("study7", "a", "b", -0.6),
        ("study8", "b", "c", 1.0),
        ("study9", "a", "c", -0.3),
    ]
    csv_path = workspace / "heor/nma-data/contrasts.csv"
    csv_path.write_text(
        "study_id,treat1,treat2,effect,se\n"
        + "".join(f"{study},{left},{right},{effect},0.15\n" for study, left, right, effect in rows),
        encoding="utf-8",
    )
    evidence_path = workspace / "heor/evidence-synthesis.json"
    record_ids = [f"rec{index}" for index in range(1, 10)]
    evidence_sha = write_json(evidence_path, {"schema_version": "test", "records": record_ids})
    request["evidence_synthesis"]["sha256"] = evidence_sha
    request["evidence_synthesis"]["included_record_ids"] = record_ids
    request["source_data"]["sha256"] = digest(csv_path.read_bytes())
    request["source_data"]["row_count"] = len(rows)
    request["source_data"]["study_count"] = len(rows)
    request["study_provenance"] = [
        {
            "study_id": study,
            "evidence_record_ids": [f"rec{index}"],
            "extraction_ids": [f"extract{index}"],
            "risk_of_bias": "some_concerns",
        }
        for index, (study, _, _, _) in enumerate(rows, start=1)
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--rscript", default="Rscript")
    parser.add_argument("--library", type=Path, required=True)
    args = parser.parse_args()
    rscript = executable(args.rscript)
    library = args.library.resolve()
    runtime = probe(rscript, library)
    summaries = []
    for model_type in ("common", "random"):
        with tempfile.TemporaryDirectory(prefix=f"ai4heor-nma-{model_type}-") as directory:
            workspace = Path(directory)
            request, _ = build_workspace(workspace, model_type=model_type)
            if model_type == "random":
                make_random_fixture_estimable(workspace, request)
            request["execution_id"] = f"nma-smoke-{model_type}"
            request["output"]["directory"] = f"heor/network-meta-analysis-runs/nma-smoke-{model_type}"
            request["runtime"] = {
                "r_version": runtime["r_version"],
                "package_versions": runtime["package_versions"],
                "adapter_sha256": runtime["adapter_sha256"],
            }
            request_path = workspace / "heor/network-meta-analysis-request.json"
            write_json(request_path, request)
            manifest, audit = run_request(request_path, workspace, rscript, library)
            summaries.append(
                {
                    "model": model_type,
                    "manifest": manifest.relative_to(workspace).as_posix(),
                    "complete": audit["complete"],
                    "reviewable": audit["eligible_for_review"],
                    "study_count": audit["study_count"],
                    "treatment_count": audit["treatment_count"],
                    "cycle_rank": audit["cycle_rank"],
                    "tau": audit["tau"],
                    "cross_implementation_scope": audit["cross_implementation_scope"],
                    "errors": audit["errors"],
                }
            )
    print(json.dumps({"runtime": runtime, "runs": summaries}, indent=2, ensure_ascii=False))
    return 0 if all(item["complete"] and item["reviewable"] for item in summaries) else 1


if __name__ == "__main__":
    raise SystemExit(main())
