#!/usr/bin/env python3
"""Contract tests for first-party AI4HEOR research artifacts."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import sys
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


evidence = load(
    "validate_evidence_synthesis",
    "runtime/skills/core/heor-evidence-synthesis/scripts/validate_evidence_synthesis.py",
)
conceptual = load(
    "validate_conceptual_model",
    "runtime/skills/core/heor-model-design/scripts/validate_conceptual_model.py",
)
reference_case = load(
    "validate_reference_case_assessment",
    "runtime/skills/core/heor-reference-case/scripts/validate_reference_case_assessment.py",
)
uncertainty = load(
    "validate_uncertainty_plan",
    "runtime/skills/core/heor-uncertainty-analysis/scripts/validate_uncertainty_plan.py",
)
budget_impact = load(
    "validate_budget_impact_plan",
    "runtime/skills/core/heor-budget-impact/scripts/validate_budget_impact_plan.py",
)
model_validation = load(
    "validate_model_validation",
    "runtime/skills/core/heor-model-validation/scripts/validate_model_validation.py",
)
reporting = load(
    "validate_report_package",
    "runtime/skills/core/heor-reporting/scripts/validate_report_package.py",
)


def evidence_fixture():
    return {
        "schema_version": "0.1.0",
        "synthesis_id": "nsclc-evidence",
        "status": "ready_for_human_review",
        "research_question": {
            "population": "Adults with advanced NSCLC",
            "intervention": "Treatment A",
            "comparator": "Standard care",
            "outcomes": ["overall survival", "resource use"],
            "study_designs": ["randomized trial", "cost study"],
        },
        "eligibility": {
            "inclusion": ["Directly applicable population"],
            "exclusion": ["No relevant comparator"],
        },
        "searches": [{
            "id": "pubmed-2026-07-14",
            "source": "PubMed",
            "query": "NSCLC AND Treatment A",
            "searched_on": "2026-07-14",
            "result_count": 1,
            "access": "network",
        }],
        "deduplication": {
            "method": "DOI then normalized title",
            "duplicate_records_removed": 0,
        },
        "records": [{
            "record_id": "trial-1",
            "title": "Treatment A randomized trial",
            "locator": "https://example.test/trial-1",
            "source_type": "randomized_trial",
            "search_ids": ["pubmed-2026-07-14"],
            "screening": {"title_abstract": "include", "full_text": "include"},
            "critical_appraisal": {
                "status": "agent_draft",
                "tool": "RoB 2",
                "findings": ["Randomization process requires human confirmation"],
                "rationale": "Randomized trial",
            },
        }],
        "extractions": [{
            "extraction_id": "os-1",
            "record_id": "trial-1",
            "target": "overall survival",
            "extracted_value": "HR 0.80",
            "source_location": "Table 2",
            "applicability": "Direct trial population match",
            "verification_status": "agent_extracted",
        }],
        "conflicts": [],
        "limitations": ["Single database search in this fixture"],
    }


def conceptual_fixture():
    return {
        "schema_version": "0.1.0",
        "model_id": "nsclc-conceptual",
        "analysis_id": "nsclc-analysis",
        "status": "ready_for_human_review",
        "objective": "Estimate incremental costs and QALYs",
        "scope": {
            "population": "Adults with advanced NSCLC",
            "intervention": "Treatment A",
            "comparator": "Standard care",
            "perspective": "Chinese healthcare system",
            "time_horizon": "Lifetime",
            "outcomes": ["cost", "QALY"],
            "jurisdiction": "China",
            "decision_context": "Reimbursement assessment",
        },
        "care_pathway": ["Start first-line treatment", "Progress or remain stable", "Death"],
        "model_type": {
            "proposed": "cohort_state_transition",
            "rationale": "Three mutually exclusive disease states represent the decision problem",
        },
        "states": [
            {"id": "stable", "label": "Stable", "definition": "No progression", "absorbing": False},
            {"id": "progressed", "label": "Progressed", "definition": "Progressed disease", "absorbing": False},
            {"id": "dead", "label": "Dead", "definition": "All-cause death", "absorbing": True},
        ],
        "transitions": [
            {"id": "stable-stable", "from": "stable", "to": "stable", "trigger": "No progression"},
            {"id": "stable-progressed", "from": "stable", "to": "progressed", "trigger": "Progression"},
            {"id": "progressed-progressed", "from": "progressed", "to": "progressed", "trigger": "Remain progressed"},
            {"id": "progressed-dead", "from": "progressed", "to": "dead", "trigger": "Death"},
            {"id": "dead-dead", "from": "dead", "to": "dead", "trigger": "Absorbing"},
        ],
        "structural_assumptions": [{
            "id": "memoryless",
            "statement": "Transition risk depends only on current state",
            "rationale": "Required by the proposed cohort structure",
            "status": "proposed",
        }],
        "structural_alternatives": [{
            "id": "partitioned-survival",
            "description": "Partitioned survival model",
            "rationale": "Directly use survival curves",
            "expected_impact": "May change extrapolation and state occupancy",
        }],
        "evidence_links": [{"claim": "Disease pathway", "source_ids": ["trial-1"]}],
        "validation_plan": {
            "face": ["Clinical expert pathway review"],
            "internal": ["Formula and boundary-condition checks"],
            "external": ["Independent outcome comparison"],
        },
        "validation_questions": ["Are the states clinically exhaustive and mutually exclusive?"],
    }


class EvidenceSynthesisContractTests(unittest.TestCase):
    def test_complete_synthesis_passes(self):
        result = evidence.audit(evidence_fixture())
        self.assertTrue(result["complete"])
        self.assertEqual(result["included_count"], 1)

    def test_included_record_requires_extraction(self):
        value = evidence_fixture()
        value["extractions"] = []
        result = evidence.audit(value)
        self.assertFalse(result["complete"])
        self.assertIn("included records without extraction: trial-1", result["errors"])

    def test_search_and_record_links_fail_closed(self):
        value = evidence_fixture()
        value["records"][0]["search_ids"] = ["missing-search"]
        self.assertFalse(evidence.audit(value)["complete"])

    def test_included_record_requires_critical_appraisal(self):
        value = evidence_fixture()
        del value["records"][0]["critical_appraisal"]
        result = evidence.audit(value)
        self.assertFalse(result["complete"])
        self.assertTrue(any("critical_appraisal" in error for error in result["errors"]))


class ConceptualModelContractTests(unittest.TestCase):
    def test_complete_conceptual_model_passes(self):
        result = conceptual.audit(conceptual_fixture())
        self.assertTrue(result["complete"])
        self.assertEqual(result["state_count"], 3)

    def test_unknown_state_and_absorbing_exit_fail_closed(self):
        value = conceptual_fixture()
        value["transitions"].append({
            "id": "dead-unknown", "from": "dead", "to": "unknown", "trigger": "Invalid"
        })
        result = conceptual.audit(value)
        self.assertFalse(result["complete"])
        self.assertTrue(any("unknown state" in error for error in result["errors"]))

    def test_unresolved_assumption_blocks_review_readiness(self):
        value = deepcopy(conceptual_fixture())
        value["structural_assumptions"][0]["status"] = "unresolved"
        result = conceptual.audit(value)
        self.assertFalse(result["complete"])
        self.assertEqual(result["unresolved_assumptions"], ["memoryless"])

    def test_analysis_link_mismatch_fails_closed(self):
        result = conceptual.audit(conceptual_fixture(), "another-analysis")
        self.assertFalse(result["complete"])
        self.assertTrue(any("does not match" in error for error in result["errors"]))


class ReferenceCaseContractTests(unittest.TestCase):
    def fixture(self, root: Path):
        profile_path = ROOT / (
            "runtime/skills/core/heor-reference-case/assets/profiles/CN-2020-current.json"
        )
        profile_raw = profile_path.read_bytes()
        profile = json.loads(profile_raw)
        assessment = {
            "schema_version": "0.1.0",
            "assessment_id": "nsclc-cn-2020",
            "analysis_id": "nsclc-analysis",
            "status": "ready_for_human_review",
            "assessed_on": "2026-07-14",
            "profile": {
                "id": profile["id"],
                "revision": profile["revision"],
                "status": profile["status"],
                "content_sha256": hashlib.sha256(profile_raw).hexdigest(),
            },
            "requirements": [{
                "requirement_id": item["id"],
                "status": "met",
                "rationale": "Covered by the analysis plan fixture",
                "evidence_paths": ["heor/analysis-plan.json"],
            } for item in profile["requirements"]],
            "limitations": [],
        }
        assessment_path = root / "heor" / "reference-case-assessment.json"
        assessment_path.parent.mkdir(parents=True)
        assessment_raw = json.dumps(assessment, ensure_ascii=False, indent=2).encode()
        assessment_path.write_bytes(assessment_raw)
        plan = {
            "analysis_id": "nsclc-analysis",
            "reference_case": {"id": profile["id"], "status": profile["status"]},
            "reference_case_assessment": {
                "path": "heor/reference-case-assessment.json",
                "content_sha256": hashlib.sha256(assessment_raw).hexdigest(),
            },
        }
        plan_path = root / "heor" / "analysis-plan.json"
        plan_path.write_text(json.dumps(plan, indent=2))
        return assessment_path, plan_path, profile_path

    def test_complete_hash_bound_matrix_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.fixture(Path(directory))
            self.assertEqual(reference_case.validate(*paths), [])

    def test_changed_assessment_hash_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            assessment_path, plan_path, profile_path = self.fixture(Path(directory))
            plan = json.loads(plan_path.read_text())
            plan["reference_case_assessment"]["content_sha256"] = "0" * 64
            plan_path.write_text(json.dumps(plan, indent=2))
            errors = reference_case.validate(assessment_path, plan_path, profile_path)
            self.assertIn("plan assessment hash does not match the assessment bytes", errors)


class UncertaintyContractTests(unittest.TestCase):
    def fixture(self, root: Path):
        plan = json.loads(
            (ROOT / "python/heor_core/golden_cases/two_strategy_markov.json").read_text()
        )
        plan["uncertainty_analysis"] = {"path": "heor/uncertainty-plan.json"}
        plan["input_provenance"] = [
            {
                "path": "strategies.intervention.state_costs",
                "source_ids": ["golden-cost-source"],
                "assumption_ids": [],
                "uncertainty_status": "distribution_available",
            },
            {
                "path": "strategies.intervention.transition_matrix",
                "source_ids": ["golden-transition-source"],
                "assumption_ids": [],
                "uncertainty_status": "distribution_available",
            },
        ]
        paths = [item["path"] for item in plan["input_provenance"]]
        plan["methodology"] = {
            "uncertainty_analysis": {
                "deterministic": {"planned": True, "input_paths": paths},
                "probabilistic": {
                    "planned": True,
                    "input_paths": paths,
                    "iterations": 1000,
                },
                "structural_scenarios": ["five-year-horizon"],
            }
        }
        plan_path = root / "heor" / "analysis-plan.json"
        plan_path.parent.mkdir(parents=True)
        plan_raw = json.dumps(plan, ensure_ascii=False, indent=2).encode()
        plan_path.write_bytes(plan_raw)

        value = json.loads(
            (ROOT / "python/heor_core/golden_cases/two_strategy_uncertainty.json").read_text()
        )
        value["base_analysis"]["content_sha256"] = hashlib.sha256(plan_raw).hexdigest()
        uncertainty_path = root / "heor" / "uncertainty-plan.json"
        uncertainty_path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
        return uncertainty_path, plan_path

    def test_complete_hash_bound_uncertainty_plan_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.fixture(Path(directory))
            self.assertEqual(uncertainty.validate(*paths), [])

    def test_changed_base_hash_and_unlinked_distribution_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            uncertainty_path, plan_path = self.fixture(Path(directory))
            value = json.loads(uncertainty_path.read_text())
            value["base_analysis"]["content_sha256"] = "0" * 64
            value["parameters"][0]["probabilistic"]["basis_ids"] = ["unlinked"]
            uncertainty_path.write_text(json.dumps(value, indent=2))
            errors = uncertainty.validate(uncertainty_path, plan_path)
            self.assertIn("base_analysis.content_sha256 does not match the plan bytes", errors)
            self.assertTrue(any("basis_ids" in error for error in errors))

    def test_known_omitted_correlation_blocks_review(self):
        with tempfile.TemporaryDirectory() as directory:
            uncertainty_path, plan_path = self.fixture(Path(directory))
            value = json.loads(uncertainty_path.read_text())
            value["probabilistic_analysis"]["correlation_handling"][
                "known_omitted_correlations"
            ] = ["Shared evidence source"]
            uncertainty_path.write_text(json.dumps(value, indent=2))
            self.assertIn(
                "known_omitted_correlations must be resolved before review",
                uncertainty.validate(uncertainty_path, plan_path),
            )


class BudgetImpactContractTests(unittest.TestCase):
    def fixture(self, root: Path):
        plan_path = root / "heor" / "analysis-plan.json"
        budget_path = root / "heor" / "budget-impact-plan.json"
        plan_path.parent.mkdir(parents=True)
        plan_path.write_bytes(
            (ROOT / "python/heor_core/golden_cases/two_strategy_budget_base.json").read_bytes()
        )
        budget_path.write_bytes(
            (ROOT / "python/heor_core/golden_cases/two_strategy_budget_impact.json").read_bytes()
        )
        return budget_path, plan_path

    def test_complete_hash_bound_budget_impact_plan_passes(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.fixture(Path(directory))
            self.assertEqual(budget_impact.validate(*paths), [])

    def test_changed_hash_and_missing_cost_provenance_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            budget_path, plan_path = self.fixture(Path(directory))
            value = json.loads(budget_path.read_text())
            value["base_analysis"]["content_sha256"] = "0" * 64
            value["input_provenance"] = value["input_provenance"][:-1]
            budget_path.write_text(json.dumps(value, indent=2))
            errors = budget_impact.validate(budget_path, plan_path)
            self.assertIn(
                "base_analysis.content_sha256 does not match the plan bytes",
                errors,
            )
            self.assertTrue(any("lack provenance" in error for error in errors))

    def test_budget_impact_rejects_discounting_and_authority_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            budget_path, plan_path = self.fixture(Path(directory))
            value = json.loads(budget_path.read_text())
            value["discount_rate"] = 0.05
            value["sensitivity_parameters"][0]["target"] = "/perspective/price_year"
            budget_path.write_text(json.dumps(value, indent=2))
            errors = budget_impact.validate(budget_path, plan_path)
            self.assertIn("discount_rate must be 0", errors)
            self.assertTrue(any("target is invalid" in error for error in errors))


class ModelValidationContractTests(unittest.TestCase):
    @staticmethod
    def method(domain: str) -> str:
        return {
            "face_validity": "expert_review",
            "input_data": "source_reconciliation",
            "technical_verification": "black_box",
            "cross_validity": "cross_model_comparison",
            "external_validity": "external_data_comparison",
            "predictive_validity": "prospective_comparison",
        }[domain]

    def fixture(self, root: Path):
        heor = root / "heor"
        evidence_dir = heor / "validation-evidence"
        evidence_dir.mkdir(parents=True)
        analysis_id = "nsclc-analysis"
        bindings = {}
        for key, relative in model_validation.BINDINGS.items():
            raw = json.dumps(
                {"analysis_id": analysis_id, "artifact": key},
                separators=(",", ":"),
            ).encode()
            path = root / relative
            path.write_bytes(raw)
            bindings[key] = {
                "path": relative,
                "content_sha256": hashlib.sha256(raw).hexdigest(),
            }

        evidence_raw = b"independent review evidence\n"
        evidence_path = evidence_dir / "review.txt"
        evidence_path.write_bytes(evidence_raw)
        checks = []
        for index, (label, scope, domain, component, _statuses) in enumerate(
            model_validation.required_coverage()
        ):
            checks.append({
                "id": f"check-{index}",
                "scope": scope,
                "domain": domain,
                "component": component or (
                    "conceptual_model" if domain == "face_validity" else "model_outcomes"
                ),
                "method": self.method(domain),
                "status": "passed",
                "performed_by": "independent_reviewer",
                "description": label,
                "expected": "Criterion is met",
                "observed": "Evidence supports the criterion",
                "rationale": "Reviewed against the intended use",
                "evidence_ids": ["review-evidence"],
                "issue_ids": [],
            })
        report = {
            "schema_version": "0.1.0",
            "validation_id": "validation-1",
            "analysis_id": analysis_id,
            "status": "ready_for_independent_review",
            "intended_use": "Local reimbursement research",
            "model_bindings": bindings,
            "developer_label": "Model developer",
            "reviewer": {
                "label": "Independent reviewer",
                "organization": "Independent methods unit",
                "role": "independent_reviewer",
                "reviewed_on": "2026-07-14",
                "declared_independent": True,
                "independence_statement": "No role in model development",
                "conflict_statement": "No conflicts declared",
            },
            "evidence_artifacts": [{
                "id": "review-evidence",
                "path": "heor/validation-evidence/review.txt",
                "content_sha256": hashlib.sha256(evidence_raw).hexdigest(),
                "evidence_type": "test_log",
                "description": "Independent review evidence",
            }],
            "checks": checks,
            "issues": [],
            "limitations": ["Predictive observations remain time-limited"],
            "conclusion": {
                "recommendation": "approve_for_intended_use",
                "rationale": "All required checks passed",
                "residual_uncertainty": ["Future evidence may change conclusions"],
            },
        }
        report_path = heor / "model-validation.json"
        report_path.write_text(json.dumps(report, indent=2))
        return report_path, report, evidence_path

    def test_complete_hash_bound_validation_package_is_approvable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path, _, _ = self.fixture(root)
            result = model_validation.audit(report_path, root)
            self.assertTrue(result["complete"])
            self.assertTrue(result["approvable"])
            self.assertEqual(result["covered_requirement_count"], 18)

    def test_stale_evidence_hash_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path, _, evidence_path = self.fixture(root)
            evidence_path.write_text("changed evidence\n")
            result = model_validation.audit(report_path, root)
            self.assertFalse(result["complete"])
            self.assertTrue(any("content_sha256" in error for error in result["errors"]))

    def test_missing_external_coverage_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path, report, _ = self.fixture(root)
            report["checks"] = [
                check for check in report["checks"]
                if not (
                    check["scope"] == "budget_impact"
                    and check["domain"] == "external_validity"
                )
            ]
            report_path.write_text(json.dumps(report, indent=2))
            result = model_validation.audit(report_path, root)
            self.assertFalse(result["complete"])
            self.assertIn("budget-impact external validity", result["missing_coverage"])

    def test_self_review_and_open_major_issue_block_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report_path, report, _ = self.fixture(root)
            report["reviewer"]["label"] = report["developer_label"]
            report["issues"] = [{
                "id": "major-1",
                "severity": "major",
                "status": "open",
                "description": "External result mismatch",
                "evidence_ids": ["review-evidence"],
            }]
            report["checks"][0]["issue_ids"] = ["major-1"]
            report["conclusion"]["recommendation"] = "approve_with_limitations"
            report_path.write_text(json.dumps(report, indent=2))
            result = model_validation.audit(report_path, root)
            self.assertFalse(result["complete"])
            self.assertFalse(result["approvable"])
            self.assertEqual(result["open_blocking_issue_count"], 1)
            self.assertIn("independent reviewer must differ from the developer", result["errors"])


class ReportingContractTests(unittest.TestCase):
    def fixture(self, root: Path):
        analysis_id = "nsclc-analysis"
        heor = root / "heor"
        results = heor / "results"
        results.mkdir(parents=True)
        values = {
            "analysis_plan": {"analysis_id": analysis_id},
            "conceptual_model": {"analysis_id": analysis_id},
            "uncertainty_plan": {"analysis_id": analysis_id},
            "budget_impact_plan": {"analysis_id": analysis_id},
            "model_validation": {"analysis_id": analysis_id},
        }
        paths = {
            key: heor / reporting.BINDINGS[key].split("/")[-1]
            for key in values
        }
        for key, value in values.items():
            paths[key].write_text(json.dumps(value, indent=2))
        analysis_hash = hashlib.sha256(paths["analysis_plan"].read_bytes()).hexdigest()
        uncertainty_hash = hashlib.sha256(paths["uncertainty_plan"].read_bytes()).hexdigest()
        bia_hash = hashlib.sha256(paths["budget_impact_plan"].read_bytes()).hexdigest()
        result_values = {
            "base_case_result": {
                "analysis_id": analysis_id,
                "input_sha256": analysis_hash,
                "incremental": {
                    "delta_cost": 12000.0,
                    "delta_qaly": 0.5,
                    "icer": 24000.0,
                    "incremental_net_monetary_benefit": 63000.0,
                },
            },
            "uncertainty_result": {
                "analysis_id": analysis_id,
                "base_analysis_sha256": analysis_hash,
                "uncertainty_plan_sha256": uncertainty_hash,
                "probabilistic_analysis": {
                    "iterations": 1000,
                    "cost_effective_probability": 0.82,
                    "mean_incremental_net_monetary_benefit": 61000.0,
                },
            },
            "budget_impact_result": {
                "analysis_id": analysis_id,
                "analysis_plan_sha256": analysis_hash,
                "budget_impact_plan_sha256": bia_hash,
                "base_case": {
                    "annual_net_budget_impact": [100.0, 200.0, 300.0],
                    "cumulative_net_budget_impact": 600.0,
                },
            },
        }
        for key, value in result_values.items():
            relative = reporting.BINDINGS[key]
            path = root / relative
            path.write_text(json.dumps(value, indent=2))
            paths[key] = path

        report_text = "# Report\n\n" + "\n".join(
            f"<!-- report-section:section-{index} -->\nSubstantive reporting text."
            for index in range(len(reporting.REQUIRED_ITEMS))
        )
        report_path = heor / "report.md"
        report_path.write_text(report_text)
        paths["report_document"] = report_path

        bindings = {
            key: {
                "path": relative,
                "content_sha256": hashlib.sha256((root / relative).read_bytes()).hexdigest(),
            }
            for key, relative in reporting.BINDINGS.items()
        }
        items = [
            {
                "profile_id": profile_id,
                "item_id": item_id,
                "status": "reported",
                "section_id": f"section-{index}",
                "rationale": "The bound report section and artifacts address this item.",
                "artifact_paths": ["heor/report.md", "heor/analysis-plan.json"],
            }
            for index, (profile_id, item_id) in enumerate(reporting.REQUIRED_ITEMS)
        ]
        package = {
            "schema_version": "0.1.0",
            "package_id": "report-1",
            "analysis_id": analysis_id,
            "status": "ready_for_release_review",
            "version": "1.0.0",
            "prepared_on": "2026-07-14",
            "intended_audience": "Reimbursement decision analysts",
            "release_owner_label": "Human release owner",
            "bindings": bindings,
            "reporting_profiles": deepcopy(reporting.PROFILES),
            "items": items,
            "result_summary": {
                "cost_effectiveness": deepcopy(result_values["base_case_result"]["incremental"]),
                "uncertainty": deepcopy(result_values["uncertainty_result"]["probabilistic_analysis"]),
                "budget_impact": deepcopy(result_values["budget_impact_result"]["base_case"]),
            },
            "disclosures": {key: "Explicitly disclosed in the report." for key in reporting.DISCLOSURES},
            "limitations": ["This fixture is illustrative."],
            "release_notes": ["Prepared for explicit human release review."],
        }
        package_path = heor / "report-package.json"
        package_path.write_text(json.dumps(package, indent=2))
        return package_path, package, paths

    def test_complete_bound_report_package_is_releasable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package_path, _, _ = self.fixture(root)
            result = reporting.audit(package_path, root)
            self.assertTrue(result["complete"])
            self.assertTrue(result["releasable"])
            self.assertEqual(result["covered_item_count"], 40)

    def test_stale_result_hash_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package_path, _, paths = self.fixture(root)
            paths["base_case_result"].write_text("{\"analysis_id\": \"changed\"}")
            result = reporting.audit(package_path, root)
            self.assertFalse(result["complete"])
            self.assertTrue(any("content_sha256" in error for error in result["errors"]))

    def test_missing_report_marker_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package_path, package, paths = self.fixture(root)
            paths["report_document"].write_text("# Incomplete report\n")
            package["bindings"]["report_document"]["content_sha256"] = hashlib.sha256(
                paths["report_document"].read_bytes()
            ).hexdigest()
            package_path.write_text(json.dumps(package, indent=2))
            result = reporting.audit(package_path, root)
            self.assertFalse(result["complete"])
            self.assertTrue(any("report marker" in error for error in result["errors"]))

    def test_copied_result_summary_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package_path, package, _ = self.fixture(root)
            package["result_summary"]["cost_effectiveness"]["icer"] = 1.0
            package_path.write_text(json.dumps(package, indent=2))
            result = reporting.audit(package_path, root)
            self.assertFalse(result["complete"])
            self.assertIn(
                "result_summary must exactly match the bound deterministic result artifacts",
                result["errors"],
            )

    def test_profile_scope_substitution_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package_path, package, _ = self.fixture(root)
            package["reporting_profiles"][0]["scope"] = "budget_impact"
            package_path.write_text(json.dumps(package, indent=2))
            result = reporting.audit(package_path, root)
            self.assertFalse(result["complete"])
            self.assertTrue(any("reporting_profiles" in error for error in result["errors"]))


if __name__ == "__main__":
    unittest.main()
