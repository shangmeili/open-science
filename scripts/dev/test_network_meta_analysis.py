#!/usr/bin/env python3
"""Adversarial contract tests for the bounded AI4HEOR NMA capability."""

from __future__ import annotations

import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SKILL_SCRIPTS = ROOT / "runtime/skills/core/heor-network-meta-analysis/scripts"
sys.path.insert(0, str(SKILL_SCRIPTS))

from nma_contract import (  # noqa: E402
    EVALUATOR,
    REQUIRED_REVIEW_CHECKS,
    TOLERANCE,
    Z_95,
    audit_result,
    digest,
    expected_rows,
    validate_request,
)


def write_json(path: Path, value: dict[str, Any]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return digest(raw)


def write_bytes(path: Path, raw: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return digest(raw)


def build_workspace(root: Path, model_type: str = "common") -> tuple[dict[str, Any], dict[str, Any]]:
    evidence = {"schema_version": "test", "records": ["rec1", "rec2", "rec3"]}
    evidence_sha = write_json(root / "heor/evidence-synthesis.json", evidence)
    csv_raw = (
        "study_id,treat1,treat2,effect,se\n"
        "study1,a,b,0.20,0.10\n"
        "study2,b,c,0.10,0.12\n"
        "study3,a,c,0.40,0.15\n"
    ).encode("utf-8")
    csv_sha = write_bytes(root / "heor/nma-data/contrasts.csv", csv_raw)
    adapter_raw = b"bounded test adapter\n"
    adapter_sha = digest(adapter_raw)
    comparisons = ["a:b", "a:c", "b:c"]
    request = {
        "schema_version": "0.1.0",
        "execution_id": "nma-test-001",
        "status": "ready_for_execution",
        "question": {
            "population": "Adults with the test condition",
            "intervention_network": "A, B, and C",
            "outcome": "Binary response",
            "timepoint": "Twelve weeks",
            "estimand": "Randomized intention-to-treat contrast",
            "study_design": "randomized_parallel_two_arm",
        },
        "evidence_synthesis": {
            "path": "heor/evidence-synthesis.json",
            "sha256": evidence_sha,
            "included_record_ids": ["rec1", "rec2", "rec3"],
        },
        "source_data": {
            "classification": "public",
            "execution_boundary": "local_only",
            "format": "contrast_csv",
            "path": "heor/nma-data/contrasts.csv",
            "sha256": csv_sha,
            "columns": ["study_id", "treat1", "treat2", "effect", "se"],
            "row_count": 3,
            "study_count": 3,
            "contains_direct_identifiers": False,
            "missing_policy": "reject",
            "multiarm_policy": "reject",
        },
        "treatments": [
            {"id": treatment, "label": treatment.upper(), "node_definition": f"Node {treatment}", "merging_rationale": "No merging."}
            for treatment in ("a", "b", "c")
        ],
        "reference_treatment": "a",
        "effect": {
            "measure": "log_odds_ratio",
            "scale": "log",
            "likelihood": "normal",
            "link": "identity",
            "confidence_level": 0.95,
            "favorable_direction": "lower",
        },
        "model": {
            "type": model_type,
            "heterogeneity_variance": "none" if model_type == "common" else "common_tau_squared",
            "tau_method": "none" if model_type == "common" else "REML",
            "prediction_interval": model_type == "random",
        },
        "transitivity": {
            "status": "awaiting_human_review",
            "joint_randomizability_rationale": "All treatments could in principle be randomized together.",
            "effect_modifiers": [
                {
                    "id": "baseline-risk",
                    "label": "Baseline risk",
                    "rationale": "Prespecified clinical effect modifier.",
                    "comparison_summaries": [
                        {"comparison": comparison, "summary": "Distribution recorded for review.", "source_ids": [f"rec{index + 1}"]}
                        for index, comparison in enumerate(comparisons)
                    ],
                }
            ],
            "concerns": [],
        },
        "diagnostics": {
            "global_inconsistency": "design_decomposition",
            "local_inconsistency": "node_splitting",
            "ranking": "none",
        },
        "runtime": {
            "r_version": "4.6.1",
            "package_versions": {"netmeta": "3.6-1", "meta": "8.2-1", "metafor": "4.8-0"},
            "adapter_sha256": adapter_sha,
        },
        "output": {"directory": "heor/network-meta-analysis-runs/nma-test-001"},
        "study_provenance": [
            {
                "study_id": f"study{index}",
                "evidence_record_ids": [f"rec{index}"],
                "extraction_ids": [f"extract{index}"],
                "risk_of_bias": "some_concerns",
            }
            for index in range(1, 4)
        ],
        "limitations": ["Synthetic contract fixture; no substantive scientific inference."],
        "human_gate": {"status": "awaiting_model_review", "required_checks": REQUIRED_REVIEW_CHECKS},
    }
    facts = validate_request(request, root)[1]
    return request, facts


def build_result(root: Path, request: dict[str, Any], facts: dict[str, Any], tau: float) -> Path:
    request_path = root / "heor/network-meta-analysis-request.json"
    request_sha = write_json(request_path, request)
    output = root / request["output"]["directory"]
    adapter_path = output / "adapter/netmeta_adapter.R"
    write_bytes(adapter_path, b"bounded test adapter\n")
    reference_rows, league_rows = expected_rows(request, facts, tau)
    prediction_extra = Z_95 * math.sqrt(tau * tau + 0.01) if request["model"]["type"] == "random" else None
    for row in reference_rows + league_rows:
        if prediction_extra is None:
            row["prediction_lower"] = None
            row["prediction_upper"] = None
        else:
            row["prediction_lower"] = float(row["effect"]) - prediction_extra
            row["prediction_upper"] = float(row["effect"]) + prediction_extra
    matrix_lines = [
        "row_treatment\tcolumn_treatment\teffect\tse\tlower\tupper\tprediction_lower\tprediction_upper"
    ]
    for row in league_rows:
        values = [
            row["treat1"],
            row["treat2"],
            *[format(float(row[field]), ".17g") for field in ("effect", "se", "lower", "upper")],
            "" if row["prediction_lower"] is None else format(float(row["prediction_lower"]), ".17g"),
            "" if row["prediction_upper"] is None else format(float(row["prediction_upper"]), ".17g"),
        ]
        matrix_lines.append("\t".join(values))
    backend_files = {
        "matrix": ("\n".join(matrix_lines) + "\n").encode(),
        "diagnostics": (
            "tau\tq_total\tdf_total\tp_total\tq_heterogeneity\tdf_heterogeneity\tp_heterogeneity\tq_inconsistency\tdf_inconsistency\tp_inconsistency\n"
            f"{tau}\t2\t2\t0.3\t1\t1\t0.4\t1\t1\t0.4\n"
        ).encode(),
        "local_inconsistency": (
            "row_treatment\tcolumn_treatment\tnetwork_effect\tdirect_effect\tindirect_effect\tdifference\tse_difference\tp_value\n"
        ).encode(),
        "ranking": b"treatment\tp_score\n",
        "warnings": b"",
    }
    backend_bindings = []
    for identifier, raw in backend_files.items():
        suffix = "warnings.txt" if identifier == "warnings" else f"{identifier.replace('_', '-')}.tsv"
        path = output / "backend" / suffix
        sha = write_bytes(path, raw)
        backend_bindings.append({"id": identifier, "path": path.relative_to(root).as_posix(), "sha256": sha})
    manifest = {
        "schema_version": "0.1.0",
        "execution_id": request["execution_id"],
        "status": "awaiting_model_review",
        "request": {"path": request_path.relative_to(root).as_posix(), "sha256": request_sha},
        "source_data": {"path": request["source_data"]["path"], "sha256": request["source_data"]["sha256"]},
        "evidence_synthesis": {
            "path": request["evidence_synthesis"]["path"],
            "sha256": request["evidence_synthesis"]["sha256"],
        },
        "runtime": {
            "r_version": request["runtime"]["r_version"],
            "rscript_path": "/test/Rscript",
            "rscript_sha256": "1" * 64,
            "package_versions": request["runtime"]["package_versions"],
            "adapter": {"path": adapter_path.relative_to(root).as_posix(), "sha256": request["runtime"]["adapter_sha256"]},
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
        "heterogeneity": {
            "tau": tau,
            "tau_squared": tau * tau,
            "q_total": 2.0,
            "df_total": 2,
            "p_total": 0.3,
            "q_heterogeneity": 1.0,
            "df_heterogeneity": 1,
            "p_heterogeneity": 0.4,
        },
        "inconsistency": {
            "global": {"method": "design_decomposition", "status": "estimable", "q": 1.0, "df": 1, "p_value": 0.4},
            "local": [],
        },
        "ranking": {"method": "none", "rows": []},
        "cross_implementation": {
            "evaluator": EVALUATOR,
            "scope": "complete_common_effect" if request["model"]["type"] == "common" else "conditional_on_backend_tau",
            "max_abs_reference_error": 0.0,
            "max_abs_league_error": 0.0,
            "tolerance": TOLERANCE,
            "passed": True,
        },
        "warnings": [],
        "limitations": request["limitations"],
        "human_gate": request["human_gate"],
    }
    manifest_path = output / "manifest.json"
    write_json(manifest_path, manifest)
    return manifest_path


class NetworkMetaAnalysisContractTests(unittest.TestCase):
    def test_valid_common_request_and_result_are_review_eligible(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request, facts = build_workspace(root)
            errors, checked = validate_request(request, root)
            self.assertEqual(errors, [])
            self.assertEqual(checked["cycle_rank"], 1)
            audit = audit_result(build_result(root, request, facts, 0.0), root)
            self.assertTrue(audit["complete"], audit["errors"])
            self.assertTrue(audit["eligible_for_review"])

    def test_random_result_is_only_reproduced_conditional_on_backend_tau(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request, facts = build_workspace(root, model_type="random")
            audit = audit_result(build_result(root, request, facts, 0.12), root)
            self.assertTrue(audit["complete"], audit["errors"])
            self.assertEqual(audit["cross_implementation_scope"], "conditional_on_backend_tau")

    def test_duplicate_study_id_is_rejected_as_multiarm_or_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request, _ = build_workspace(root)
            source = root / request["source_data"]["path"]
            source.write_text(
                "study_id,treat1,treat2,effect,se\nstudy1,a,b,0.2,0.1\nstudy1,b,c,0.1,0.12\nstudy3,a,c,0.4,0.15\n",
                encoding="utf-8",
            )
            request["source_data"]["sha256"] = digest(source.read_bytes())
            errors, _ = validate_request(request, root)
            self.assertTrue(any("every study_id must occur exactly once" in error for error in errors))

    def test_disconnected_network_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request, _ = build_workspace(root)
            source = root / request["source_data"]["path"]
            source.write_text(
                "study_id,treat1,treat2,effect,se\nstudy1,a,b,0.2,0.1\nstudy2,a,b,0.1,0.12\nstudy3,c,d,0.4,0.15\n",
                encoding="utf-8",
            )
            request["source_data"]["sha256"] = digest(source.read_bytes())
            request["treatments"] = [
                {"id": treatment, "label": treatment, "node_definition": treatment, "merging_rationale": "No merging."}
                for treatment in ("a", "b", "c", "d")
            ]
            errors, _ = validate_request(request, root)
            self.assertIn("treatment network must be connected", errors)

    def test_effect_modifier_must_cover_every_direct_comparison(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request, _ = build_workspace(root)
            request["transitivity"]["effect_modifiers"][0]["comparison_summaries"].pop()
            errors, _ = validate_request(request, root)
            self.assertTrue(any("must summarize every direct comparison" in error for error in errors))

    def test_request_fails_after_source_bytes_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request, _ = build_workspace(root)
            (root / request["source_data"]["path"]).write_text("changed\n", encoding="utf-8")
            errors, _ = validate_request(request, root)
            self.assertTrue(any("sha256 does not match" in error for error in errors))

    def test_result_fails_after_backend_output_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request, facts = build_workspace(root)
            manifest_path = build_result(root, request, facts, 0.0)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            path = root / manifest["backend_outputs"][0]["path"]
            path.write_text("tampered\n", encoding="utf-8")
            audit = audit_result(manifest_path, root)
            self.assertFalse(audit["complete"])
            self.assertTrue(any("bytes are unavailable or changed" in error for error in audit["errors"]))

    def test_result_cannot_diverge_from_bound_backend_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request, facts = build_workspace(root)
            manifest_path = build_result(root, request, facts, 0.0)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["league_table"][0]["prediction_lower"] = -1.0
            write_json(manifest_path, manifest)
            audit = audit_result(manifest_path, root)
            self.assertFalse(audit["complete"])
            self.assertTrue(any("does not match backend matrix" in error for error in audit["errors"]), audit["errors"])

    def test_random_result_cannot_claim_common_effect_crosscheck_scope(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            request, facts = build_workspace(root, model_type="random")
            manifest_path = build_result(root, request, facts, 0.12)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["cross_implementation"]["scope"] = "complete_common_effect"
            write_json(manifest_path, manifest)
            audit = audit_result(manifest_path, root)
            self.assertFalse(audit["complete"])
            self.assertIn("cross_implementation contract is invalid", audit["errors"])


if __name__ == "__main__":
    unittest.main()
