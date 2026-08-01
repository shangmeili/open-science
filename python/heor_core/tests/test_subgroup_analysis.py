from __future__ import annotations

import copy
import hashlib
import io
import json
import math
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from heor_core.cli import main
from heor_core.model import ModelValidationError
from heor_core.subgroup_analysis import run_subgroup_analysis

def compact(value: dict) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def schema_02_payload() -> dict:
    golden = Path(__file__).parents[1] / "golden_cases/two_strategy_decision_tree.json"
    payload = json.loads(golden.read_text(encoding="utf-8"))
    payload["schema_version"] = "0.2.0"
    payload["economic_basis"] = {
        "currency": "CNY",
        "price_year": 2026,
        "jurisdiction": "中国大陆",
        "perspective": "中国医疗卫生系统",
    }
    return payload


def sourced_plan(probability: float, analysis_id: str) -> dict:
    plan = schema_02_payload()
    plan["analysis_id"] = analysis_id
    plan["reference_case"] = {"id": "CN-2020-current", "status": "current"}
    plan["assumptions"] = []
    for strategy in plan["strategies"].values():
        for node in strategy["nodes"].values():
            for branch in node.get("branches", []):
                branch["probability"] = {
                    "value": branch["probability"]["value"],
                    "source_ids": ["record-source"],
                    "assumption_ids": [],
                }
            for field in ("cost", "qaly"):
                if field in node:
                    node[field] = {
                        "value": node[field]["value"],
                        "source_ids": ["record-source"],
                        "assumption_ids": [],
                    }
    intervention = plan["strategies"]["intervention"]["nodes"]["intervention_outcome"]
    intervention["branches"][0]["probability"]["value"] = probability
    intervention["branches"][1]["probability"]["value"] = 1.0 - probability
    return plan


def fixture() -> tuple[dict, bytes, dict, bytes, dict[str, tuple[dict, bytes]], dict, bytes]:
    overall = sourced_plan(0.75, "subgroup-overall")
    group_a = sourced_plan(0.9, "subgroup-a-analysis")
    group_b = sourced_plan(0.6, "subgroup-b-analysis")
    overall_raw = compact(overall)
    group_a_raw = compact(group_a)
    group_b_raw = compact(group_b)
    evidence = {
        "records": [
            {
                "record_id": "record-1",
                "title": "Synthetic hand-checkable subgroup source",
                "source_type": "teaching_fixture",
                "locator": "local://subgroup-golden-case",
            }
        ],
        "extractions": [
            {
                "extraction_id": source_id,
                "record_id": "record-1",
                "source_location": f"fixture:{source_id}",
                "verification_status": "verified_for_teaching_fixture",
            }
            for source_id in ("record-source", "definition-source", "share-source")
        ],
    }
    evidence_raw = compact(evidence)
    plan = {
        "schema_version": "0.1.0",
        "analysis_type": "decision_tree_subgroup",
        "subgroup_analysis_id": "two-group-golden-case",
        "overall_analysis_input": {
            "path": "heor/decision-tree-plan.json",
            "content_sha256": hashlib.sha256(overall_raw).hexdigest(),
        },
        "evidence_synthesis_input": {
            "path": "heor/evidence-synthesis.json",
            "content_sha256": hashlib.sha256(evidence_raw).hexdigest(),
        },
        "grouping": {
            "id": "risk-stratum",
            "label": "Risk stratum",
            "prespecification": "prespecified",
            "mutually_exclusive": True,
            "exhaustive": True,
            "definition_source_ids": ["definition-source"],
            "heterogeneity_basis": {
                "status": "descriptive_only",
                "source_ids": [],
                "rationale": "This teaching fixture has no interaction estimate.",
            },
        },
        "subgroups": [
            {
                "id": "group-a",
                "label": "Group A",
                "population_share": {
                    "value": 0.5,
                    "source_ids": ["share-source"],
                    "assumption_ids": [],
                },
                "analysis_input": {
                    "path": "heor/subgroups/group-a.json",
                    "content_sha256": hashlib.sha256(group_a_raw).hexdigest(),
                },
            },
            {
                "id": "group-b",
                "label": "Group B",
                "population_share": {
                    "value": 0.5,
                    "source_ids": ["share-source"],
                    "assumption_ids": [],
                },
                "analysis_input": {
                    "path": "heor/subgroups/group-b.json",
                    "content_sha256": hashlib.sha256(group_b_raw).hexdigest(),
                },
            },
        ],
        "assumptions": [],
    }
    plan_raw = compact(plan)
    inputs = {
        "heor/subgroups/group-a.json": (group_a, group_a_raw),
        "heor/subgroups/group-b.json": (group_b, group_b_raw),
    }
    return overall, overall_raw, plan, plan_raw, inputs, evidence, evidence_raw


class SubgroupAnalysisTests(unittest.TestCase):
    def test_cli_loads_only_the_hash_bound_workspace_inputs(self) -> None:
        overall, overall_raw, plan, plan_raw, inputs, evidence, evidence_raw = fixture()
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            (workspace / "heor/subgroups").mkdir(parents=True)
            (workspace / "heor/decision-tree-plan.json").write_bytes(overall_raw)
            (workspace / "heor/subgroup-analysis-plan.json").write_bytes(plan_raw)
            (workspace / "heor/evidence-synthesis.json").write_bytes(evidence_raw)
            for relative, (_, raw) in inputs.items():
                (workspace / relative).write_bytes(raw)
            output = io.StringIO()
            prior = Path.cwd()
            try:
                os.chdir(workspace)
                with redirect_stdout(output):
                    self.assertEqual(
                        main(
                            [
                                "heor/decision-tree-plan.json",
                                "--subgroup-plan",
                                "heor/subgroup-analysis-plan.json",
                            ]
                        ),
                        0,
                    )
            finally:
                os.chdir(prior)
            result = json.loads(output.getvalue())
            self.assertEqual(result["subgroup_input_sha256"], hashlib.sha256(plan_raw).hexdigest())
            self.assertEqual(len(result["subgroups"]), 2)

    def test_two_group_case_matches_independent_hand_calculation(self) -> None:
        overall, overall_raw, plan, plan_raw, inputs, evidence, evidence_raw = fixture()
        untouched = copy.deepcopy((overall, plan, inputs, evidence))

        result = run_subgroup_analysis(
            overall, overall_raw, plan, plan_raw, inputs, evidence, evidence_raw
        )

        self.assertEqual((overall, plan, inputs, evidence), untouched)
        self.assertEqual(result["calculation_classification"], "deterministic_subgroup_analysis")
        self.assertEqual(result["scientific_review"]["status"], "awaiting_researcher_review")
        group_a, group_b = result["subgroups"]
        self.assertEqual(group_a["source_ids"], ["record-source", "share-source"])
        self.assertEqual(group_b["source_ids"], ["record-source", "share-source"])
        a = group_a["pairwise_vs_baseline"]["intervention"]
        b = group_b["pairwise_vs_baseline"]["intervention"]
        self.assertTrue(math.isclose(a["delta_cost"], 680.0, abs_tol=1e-9))
        self.assertTrue(math.isclose(a["delta_qaly"], 0.125, abs_tol=1e-12))
        self.assertTrue(math.isclose(a["incremental_net_monetary_benefit"], 5570.0, abs_tol=1e-9))
        self.assertTrue(math.isclose(b["delta_cost"], 1520.0, abs_tol=1e-9))
        self.assertTrue(math.isclose(b["delta_qaly"], -0.01, abs_tol=1e-12))
        self.assertTrue(math.isclose(b["incremental_net_monetary_benefit"], -2020.0, abs_tol=1e-9))
        weighted = result["weighted_pairwise_vs_baseline"]["intervention"]
        self.assertTrue(math.isclose(weighted["delta_cost"], 1100.0, abs_tol=1e-9))
        self.assertTrue(math.isclose(weighted["delta_qaly"], 0.0575, abs_tol=1e-12))
        self.assertTrue(math.isclose(weighted["incremental_net_monetary_benefit"], 1775.0, abs_tol=1e-9))
        self.assertTrue(result["overall_consistency"]["passed"])
        contrast = result["descriptive_heterogeneity"][0]
        self.assertTrue(math.isclose(contrast["delta_cost_difference"], -840.0, abs_tol=1e-9))
        self.assertTrue(math.isclose(contrast["delta_qaly_difference"], 0.135, abs_tol=1e-12))
        self.assertTrue(math.isclose(contrast["incremental_nmb_difference"], 7590.0, abs_tol=1e-9))
        self.assertTrue(any("does not establish interaction" in item for item in result["warnings"]))

    def test_weights_structure_sources_and_comparability_fail_closed(self) -> None:
        cases = []
        values = fixture()
        invalid = copy.deepcopy(values)
        invalid[2]["subgroups"][0]["population_share"]["value"] = 0.4
        cases.append(invalid)

        invalid = copy.deepcopy(values)
        invalid[2]["grouping"]["mutually_exclusive"] = False
        cases.append(invalid)

        invalid = copy.deepcopy(values)
        invalid[5]["extractions"] = [
            row for row in invalid[5]["extractions"] if row["extraction_id"] != "share-source"
        ]
        invalid = (*invalid[:6], compact(invalid[5]))
        invalid[2]["evidence_synthesis_input"]["content_sha256"] = hashlib.sha256(invalid[6]).hexdigest()
        cases.append(invalid)

        invalid = copy.deepcopy(values)
        subgroup = invalid[4]["heor/subgroups/group-a.json"][0]
        subgroup["economic_basis"]["price_year"] = 2025
        subgroup_raw = compact(subgroup)
        invalid[4]["heor/subgroups/group-a.json"] = (subgroup, subgroup_raw)
        invalid[2]["subgroups"][0]["analysis_input"]["content_sha256"] = hashlib.sha256(subgroup_raw).hexdigest()
        cases.append(invalid)

        for overall, overall_raw, plan, plan_raw, inputs, evidence, evidence_raw in cases:
            with self.subTest(plan=plan):
                with self.assertRaises(ModelValidationError):
                    run_subgroup_analysis(
                        overall, overall_raw, plan, compact(plan), inputs, evidence, evidence_raw
                    )

    def test_post_hoc_grouping_remains_explicit_and_cannot_imply_effect_modification(self) -> None:
        overall, overall_raw, plan, _, inputs, evidence, evidence_raw = fixture()
        plan["grouping"]["prespecification"] = "post_hoc"
        result = run_subgroup_analysis(
            overall, overall_raw, plan, compact(plan), inputs, evidence, evidence_raw
        )
        self.assertEqual(result["grouping"]["prespecification"], "post_hoc")
        self.assertTrue(any("post hoc" in item.lower() for item in result["warnings"]))
        self.assertTrue(any("does not establish interaction" in item for item in result["warnings"]))


if __name__ == "__main__":
    unittest.main()
