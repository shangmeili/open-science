#!/usr/bin/env python3
"""Contract tests for first-party AI4HEOR research artifacts."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import math
import re
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
evidence_search = load(
    "validate_evidence_search_request",
    "runtime/skills/core/heor-evidence-search/scripts/validate_evidence_search_request.py",
)
input_provenance = load(
    "validate_input_provenance",
    "runtime/skills/core/heor-input-provenance/scripts/validate_input_provenance.py",
)
economic_inputs = load(
    "validate_economic_inputs",
    "runtime/skills/core/heor-economic-inputs/scripts/validate_economic_inputs.py",
)
survival_adapter = load(
    "validate_survival_curve",
    "runtime/skills/core/heor-survival-curve-adapter/scripts/validate_survival_curve.py",
)
probability_time_adapter = load(
    "validate_probability_time",
    "runtime/skills/core/heor-probability-time-adapter/scripts/validate_probability_time.py",
)
background_mortality_adapter = load(
    "validate_background_mortality",
    "runtime/skills/core/heor-background-mortality/scripts/validate_background_mortality.py",
)
relative_effect_adapter = load(
    "validate_relative_effect",
    "runtime/skills/core/heor-relative-effect-adapter/scripts/validate_relative_effect.py",
)
hazard_ratio_adapter = load(
    "validate_hazard_ratio",
    "runtime/skills/core/heor-hazard-ratio-adapter/scripts/validate_hazard_ratio.py",
)
survival_extrapolation_review = load(
    "validate_survival_extrapolation_review",
    "runtime/skills/core/heor-survival-extrapolation-review/scripts/validate_survival_extrapolation_review.py",
)
survival_extrapolation_collection = load(
    "validate_survival_extrapolation_collection",
    "runtime/skills/core/heor-survival-extrapolation-review/scripts/validate_survival_extrapolation_collection.py",
)


class MultiStrategyTemplateContractTests(unittest.TestCase):
    ANALYSIS_TEMPLATE = ROOT / (
        "runtime/skills/core/heor-workbench/assets/"
        "multi-strategy-analysis-plan.template.json"
    )
    UNCERTAINTY_TEMPLATE = ROOT / (
        "runtime/skills/core/heor-uncertainty-analysis/assets/"
        "multi-strategy-uncertainty-plan.template.json"
    )

    def test_analysis_template_declares_an_exact_safe_strategy_inventory(self):
        plan = json.loads(self.ANALYSIS_TEMPLATE.read_text())
        order = plan["strategy_order"]
        self.assertEqual(plan["schema_version"], "0.8.0")
        self.assertTrue(2 <= len(order) <= 16)
        self.assertEqual(len(order), len(set(order)))
        self.assertTrue(all(re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", item) for item in order))
        self.assertEqual(set(plan["strategies"]), set(order))
        self.assertEqual(plan["baseline_strategy_id"], order[0])
        self.assertEqual(
            plan["uncertainty_analysis"]["path"], "heor/uncertainty-plan.json"
        )
        self.assertEqual(
            plan["budget_impact_analysis"]["path"], "heor/budget-impact-plan.json"
        )
        audit = input_provenance.audit(plan, {}, hashlib.sha256(b"{}").hexdigest())
        self.assertFalse(audit["complete"])
        self.assertEqual(audit["required_inputs"], 17)

    def test_uncertainty_template_is_exactly_paired_and_targets_a_declared_strategy(self):
        plan = json.loads(self.ANALYSIS_TEMPLATE.read_text())
        uncertainty_plan = json.loads(self.UNCERTAINTY_TEMPLATE.read_text())
        self.assertEqual(uncertainty_plan["schema_version"], "0.7.0")
        self.assertEqual(
            uncertainty_plan["base_analysis"]["path"], "heor/analysis-plan.json"
        )
        target = uncertainty_plan["parameters"][0]["target"]
        provenance_path = uncertainty_plan["parameters"][0]["provenance_path"]
        target_strategy = target.split("/")[2]
        self.assertIn(target_strategy, plan["strategy_order"])
        self.assertEqual(provenance_path.split(".")[1], target_strategy)
        self.assertIsInstance(
            uncertainty_plan["probabilistic_analysis"]["correlation_handling"]["groups"],
            list,
        )


def evidence_search_fixture():
    return {
        "schema_version": "0.1.0",
        "request_id": "semaglutide-t2d",
        "status": "ready_for_human_review",
        "purpose": "Find candidate trial and bibliographic metadata for an HEOR evidence review.",
        "query": "semaglutide AND type 2 diabetes AND cost effectiveness",
        "sources": ["pubmed", "clinicaltrials"],
        "max_results_per_source": 10,
        "date_from": "2020-01-01",
        "date_to": "2026-07-14",
        "data_egress": {
            "contains_sensitive_data": False,
            "fields": ["query", "date_from", "date_to"],
            "justification": "Search public metadata sources for candidate evidence.",
        },
        "limitations": [
            "Metadata retrieval is not screening, critical appraisal, or full-text verification."
        ],
    }


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


class EvidenceSearchRequestContractTests(unittest.TestCase):
    def test_complete_request_passes(self):
        result = evidence_search.audit(evidence_search_fixture())
        self.assertTrue(result["complete"])
        self.assertEqual(result["sources"], ["pubmed", "clinicaltrials"])

    def test_sensitive_egress_and_dynamic_source_fail_closed(self):
        value = evidence_search_fixture()
        value["sources"] = ["https://example.test/search"]
        value["data_egress"]["contains_sensitive_data"] = True
        result = evidence_search.audit(value)
        self.assertFalse(result["complete"])
        self.assertTrue(any("sources" in error for error in result["errors"]))
        self.assertTrue(any("sensitive" in error for error in result["errors"]))

    def test_unknown_fields_and_invalid_date_fail_closed(self):
        value = evidence_search_fixture()
        value["endpoint"] = "https://example.test"
        value["date_from"] = "2026-02-30"
        result = evidence_search.audit(value)
        self.assertFalse(result["complete"])
        self.assertTrue(any("unsupported top-level field" in error for error in result["errors"]))
        self.assertTrue(any("date_from" in error for error in result["errors"]))


class SurvivalCurveAdapterContractTests(unittest.TestCase):
    def test_template_recomputes_hand_checkable_exponential_schedule(self):
        transformation = json.loads(
            (ROOT / "runtime/skills/core/heor-survival-curve-adapter/assets/survival-transformation.template.json").read_text()
        )
        schedule = survival_adapter.derive(transformation, 3, 1.0)
        self.assertEqual(len(schedule), 3)
        for phase in schedule:
            self.assertAlmostEqual(phase["matrix"][0][0], 0.8)
            self.assertAlmostEqual(phase["matrix"][0][1], 0.2)
            self.assertEqual(phase["matrix"][1], [0.0, 1.0])

    def test_standalone_adapter_rejects_ambiguous_weibull_parameterization(self):
        transformation = json.loads(
            (ROOT / "runtime/skills/core/heor-survival-curve-adapter/assets/survival-transformation.template.json").read_text()
        )
        transformation["distribution"] = "weibull"
        with self.assertRaisesRegex(ValueError, "parameters do not match"):
            survival_adapter.derive(transformation, 3, 1.0)


class SurvivalExtrapolationReviewContractTests(unittest.TestCase):
    @staticmethod
    def _plan():
        return {
            "analysis_id": "survival-analysis",
            "input_provenance": [{
                "path": "strategies.comparator.transition_schedule",
                "derivation": {"transformation": {
                    "operation": "parametric_survival_to_transition_schedule",
                    "distribution": "weibull",
                }},
            }],
        }

    @staticmethod
    def _write(workspace: Path, relative: str, content: str) -> str:
        path = workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return hashlib.sha256(path.read_bytes()).hexdigest()

    def _fixture(self, workspace: Path):
        hashes = {
            name: self._write(workspace, name, f"auditable {name}\n")
            for name in (
                "data/survival-fit-bundle.json",
                "scripts/fit.R",
                "runs/session-info.txt",
                "runs/exponential.json",
                "runs/weibull.json",
                "figures/km-overlay.png",
                "figures/log-cumulative-hazard.png",
                "figures/hazard.png",
            )
        }
        landmarks = [
            {"time": 0.0, "survival": 1.0, "hazard": 0.1},
            {"time": 2.0, "survival": 0.8, "hazard": 0.12},
            {"time": 10.0, "survival": 0.3, "hazard": 0.15},
        ]
        return {
            "schema_version": "0.2.0",
            "review_id": "overall-survival-control",
            "status": "ready_for_human_review",
            "analysis_target": {
                "analysis_id": "survival-analysis",
                "path": "strategies.comparator.transition_schedule",
            },
            "context": {
                "endpoint": "Overall survival",
                "population": "Trial intention-to-treat population",
                "curve_label": "Control arm overall survival",
                "time_origin": "Randomization",
                "time_unit": "years",
                "observed_follow_up": 5.0,
                "model_horizon": 20.0,
            },
            "source_data": {
                "classification": "restricted",
                "execution_boundary": "local_only",
                "format": "precomputed_survival_fit_bundle",
                "path": "data/survival-fit-bundle.json",
                "sha256": hashes["data/survival-fit-bundle.json"],
                "time_variable": "time",
                "event_definition": "status equals 1",
                "censor_definition": "status equals 0",
            },
            "pre_specification": {
                "fit_method": "maximum_likelihood",
                "candidate_models": [
                    {"family": "exponential", "rationale": "Constant hazard reference."},
                    {"family": "weibull", "rationale": "Monotone hazard alternative."},
                ],
                "protocol_deviations": [],
            },
            "execution": {
                "backend": "survHE",
                "environment": "external_local_fit_import",
                "r_version": "R 4.4.2",
                "package_versions": {
                    "survHE": "2.0.1",
                    "flexsurv": "2.3.2",
                    "survival": "3.8-3",
                },
                "command_path": "scripts/fit.R",
                "command_sha256": hashes["scripts/fit.R"],
                "session_info_path": "runs/session-info.txt",
                "session_info_sha256": hashes["runs/session-info.txt"],
            },
            "models": [
                {
                    "family": "exponential",
                    "status": "converged",
                    "aic": 102.0,
                    "bic": 105.0,
                    "log_likelihood": -50.0,
                    "parameterization": "survHE/flexsurv exponential rate",
                    "fit_output_path": "runs/exponential.json",
                    "fit_output_sha256": hashes["runs/exponential.json"],
                    "landmarks": landmarks,
                    "warnings": [],
                },
                {
                    "family": "weibull",
                    "status": "converged",
                    "aic": 100.0,
                    "bic": 106.0,
                    "log_likelihood": -48.0,
                    "parameterization": "survHE/flexsurv Weibull shape and scale",
                    "fit_output_path": "runs/weibull.json",
                    "fit_output_sha256": hashes["runs/weibull.json"],
                    "landmarks": [dict(item) for item in landmarks],
                    "warnings": [],
                },
            ],
            "diagnostics": {
                "km_overlay_path": "figures/km-overlay.png",
                "km_overlay_sha256": hashes["figures/km-overlay.png"],
                "log_cumulative_hazard_path": "figures/log-cumulative-hazard.png",
                "log_cumulative_hazard_sha256": hashes["figures/log-cumulative-hazard.png"],
                "hazard_plot_path": "figures/hazard.png",
                "hazard_plot_sha256": hashes["figures/hazard.png"],
                "internal_validity_assessment": "Both candidates are retained; fit statistics are not treated as validity thresholds.",
                "external_validity_assessment": "Long-term external comparison remains unresolved pending registry alignment.",
                "external_sources": [],
                "clinical_plausibility_assessment": "Human clinical review of hazard shape is still required.",
            },
            "structural_scenarios": ["weibull", "exponential"],
            "analyst_recommendation": {
                "family": "weibull",
                "rationale": "Proposed for Human review using fit and hazard-shape evidence, not AIC alone.",
                "alternatives": ["exponential"],
            },
            "limitations": ["External validity remains unresolved."],
            "human_gate": {
                "state": "awaiting_human_selection",
                "required_action": "select_curve_in_analysis_plan",
            },
        }

    def test_complete_review_binds_files_and_keeps_selection_human_owned(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            review = self._fixture(workspace)
            result = survival_extrapolation_review.audit(review, workspace, self._plan())
            self.assertTrue(result["complete"], result["errors"])
            self.assertEqual(result["candidate_models"], 2)
            self.assertEqual(result["converged_models"], 2)
            self.assertEqual(result["human_gate"], "awaiting_human_selection")

    def test_hash_drift_post_hoc_results_and_approval_fields_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            review = self._fixture(workspace)
            review["models"].reverse()
            review["diagnostics"]["km_overlay_sha256"] = "0" * 64
            review["execution"]["approved_local_execution"] = True
            review["human_gate"]["approved"] = True
            result = survival_extrapolation_review.audit(review, workspace, self._plan())
            self.assertFalse(result["complete"])
            self.assertTrue(any("pre-specified candidate order" in error for error in result["errors"]))
            self.assertTrue(any("KM overlay SHA-256" in error for error in result["errors"]))
            self.assertTrue(any("execution fields" in error for error in result["errors"]))
            self.assertTrue(any("forbidden approval" in error for error in result["errors"]))

    def test_nonmonotone_or_incomparable_landmarks_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            review = self._fixture(workspace)
            review["models"][0]["landmarks"][2]["survival"] = 0.9
            review["models"][1]["landmarks"][2]["time"] = 12.0
            result = survival_extrapolation_review.audit(review, workspace, self._plan())
            self.assertFalse(result["complete"])
            self.assertTrue(any("non-increasing" in error for error in result["errors"]))
            self.assertTrue(any("identical landmark times" in error for error in result["errors"]))

    def test_target_drift_multiple_curves_and_unconverged_selection_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            review = self._fixture(workspace)
            review["analysis_target"]["path"] = "strategies.intervention.transition_schedule"
            result = survival_extrapolation_review.audit(review, workspace, self._plan())
            self.assertFalse(result["complete"])
            self.assertTrue(any("analysis_target" in error for error in result["errors"]))

            review = self._fixture(workspace)
            plan = self._plan()
            plan["input_provenance"].append(deepcopy(plan["input_provenance"][0]))
            result = survival_extrapolation_review.audit(review, workspace, plan)
            self.assertTrue(any("exactly one" in error for error in result["errors"]))

            plan = self._plan()
            del plan["input_provenance"][0]["derivation"]["transformation"]["distribution"]
            result = survival_extrapolation_review.audit(review, workspace, plan)
            self.assertFalse(result["complete"])
            self.assertTrue(any("selected distribution" in error for error in result["errors"]))

            plan = self._plan()
            review["models"][1]["status"] = "failed"
            review["models"][1]["aic"] = None
            review["models"][1]["bic"] = None
            review["models"][1]["log_likelihood"] = None
            review["models"][1]["landmarks"] = []
            result = survival_extrapolation_review.audit(review, workspace, plan)
            self.assertTrue(any("selected distribution" in error for error in result["errors"]))

    def test_complete_collection_binds_every_curve_in_plan_order(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            plan = self._plan()
            second = deepcopy(plan["input_provenance"][0])
            second["path"] = "strategies.intervention.transition_schedule"
            plan["input_provenance"].append(second)
            entries = []
            for index, mapping in enumerate(plan["input_provenance"]):
                review = self._fixture(workspace)
                review["review_id"] = f"overall-survival-{index}"
                review["analysis_target"]["path"] = mapping["path"]
                relative = f"heor/survival-extrapolation-reviews/review-{index}.json"
                raw = json.dumps(review, indent=2).encode()
                path = workspace / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
                entries.append({
                    "target_path": mapping["path"],
                    "review_path": relative,
                    "review_sha256": hashlib.sha256(raw).hexdigest(),
                })
            collection = {
                "schema_version": "0.1.0",
                "analysis_id": "survival-analysis",
                "reviews": entries,
            }
            result = survival_extrapolation_collection.audit(collection, workspace, plan)
            self.assertTrue(result["complete"], result["errors"])
            self.assertEqual(result["target_count"], 2)
            self.assertEqual(len(result["artifact_bindings"]), 2)

    def test_collection_order_hash_and_path_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            plan = self._plan()
            second = deepcopy(plan["input_provenance"][0])
            second["path"] = "strategies.intervention.transition_schedule"
            plan["input_provenance"].append(second)
            review = self._fixture(workspace)
            raw = json.dumps(review).encode()
            path = workspace / "heor/survival-extrapolation-reviews/review-0.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
            collection = {
                "schema_version": "0.1.0",
                "analysis_id": "survival-analysis",
                "reviews": [
                    {
                        "target_path": second["path"],
                        "review_path": "heor/survival-extrapolation-reviews/review-0.json",
                        "review_sha256": "0" * 64,
                    },
                    {
                        "target_path": plan["input_provenance"][0]["path"],
                        "review_path": "../review-1.json",
                        "review_sha256": hashlib.sha256(raw).hexdigest(),
                    },
                ],
            }
            result = survival_extrapolation_collection.audit(collection, workspace, plan)
            self.assertFalse(result["complete"])
            self.assertTrue(any("plan-target order" in error for error in result["errors"]))
            self.assertTrue(any("does not match" in error for error in result["errors"]))
            self.assertTrue(any("one safe JSON file" in error for error in result["errors"]))


class ProbabilityTimeAdapterContractTests(unittest.TestCase):
    def test_template_recomputes_hand_checkable_probability(self):
        transformation = json.loads(
            (ROOT / "runtime/skills/core/heor-probability-time-adapter/assets/probability-time-transformation.template.json").read_text()
        )
        matrix = probability_time_adapter.derive(transformation, 2, 10, 1.0, False)
        self.assertAlmostEqual(matrix[0][0], 0.8)
        self.assertAlmostEqual(matrix[0][1], 0.2)
        self.assertEqual(matrix[1], [0.0, 1.0])

    def test_standalone_adapter_rejects_endpoint_probability(self):
        transformation = json.loads(
            (ROOT / "runtime/skills/core/heor-probability-time-adapter/assets/probability-time-transformation.template.json").read_text()
        )
        transformation["phases"][0]["rows"][0]["event"]["source_probability"] = 1.0
        with self.assertRaisesRegex(ValueError, "strictly between 0 and 1"):
            probability_time_adapter.derive(transformation, 2, 10, 1.0, False)


class BackgroundMortalityAdapterContractTests(unittest.TestCase):
    TEMPLATE = ROOT / (
        "runtime/skills/core/heor-background-mortality/assets/"
        "background-mortality-transformation.template.json"
    )

    def test_template_recomputes_age_aligned_additive_excess_schedule(self):
        transformation = json.loads(self.TEMPLATE.read_text())
        schedule = background_mortality_adapter.derive(transformation, 3, 0.5)
        self.assertEqual([item["start_cycle"] for item in schedule], [1, 2, 3])
        self.assertAlmostEqual(schedule[0]["matrix"][0][0], 0.9 ** 0.5 * math.exp(-0.025))
        self.assertAlmostEqual(schedule[2]["matrix"][0][0], 0.8 ** 0.5 * math.exp(-0.025))
        self.assertEqual(schedule[0]["matrix"][1], [0.0, 1.0])

    def test_zero_mortality_is_valid_but_floating_point_saturation_is_not(self):
        transformation = json.loads(self.TEMPLATE.read_text())
        transformation["excess_mortality_rate_per_year"]["value"] = 0.0
        for probability in transformation["life_table"]["cycle_probabilities"]:
            probability["annual_probability"]["value"] = 0.0
        schedule = background_mortality_adapter.derive(transformation, 3, 0.5)
        self.assertEqual(
            schedule,
            [
                {"start_cycle": cycle, "matrix": [[1.0, 0.0], [0.0, 1.0]]}
                for cycle in (1, 2, 3)
            ],
        )

        transformation["excess_mortality_rate_per_year"]["value"] = 1e308
        with self.assertRaisesRegex(ValueError, "invalid probability"):
            background_mortality_adapter.derive(transformation, 3, 0.5)

    def test_adapter_rejects_age_drift_nonadditive_input_and_review_authority(self):
        transformation = json.loads(self.TEMPLATE.read_text())
        transformation["life_table"]["cycle_probabilities"][1]["attained_age_years"] = 61
        with self.assertRaisesRegex(ValueError, "ages must align"):
            background_mortality_adapter.derive(transformation, 3, 0.5)

        transformation = json.loads(self.TEMPLATE.read_text())
        transformation["excess_mortality_rate_per_year"]["measure"] = "all_cause_hazard_per_year"
        with self.assertRaisesRegex(ValueError, "exactly one evidence or assumption basis"):
            background_mortality_adapter.derive(transformation, 3, 0.5)

        transformation = json.loads(self.TEMPLATE.read_text())
        transformation["review_bases"]["no_double_counting"]["approved"] = True
        with self.assertRaisesRegex(ValueError, "review basis"):
            background_mortality_adapter.derive(transformation, 3, 0.5)


class RelativeEffectAdapterContractTests(unittest.TestCase):
    TEMPLATE = ROOT / (
        "runtime/skills/core/heor-relative-effect-adapter/assets/"
        "relative-effect-transformation.template.json"
    )

    def test_template_recomputes_complete_risk_ratio_schedule(self):
        transformation = json.loads(self.TEMPLATE.read_text())
        schedule = relative_effect_adapter.derive(transformation, 3, 1.0)
        self.assertEqual([item["start_cycle"] for item in schedule], [1, 2, 3])
        self.assertAlmostEqual(schedule[0]["matrix"][0][1], 0.075)
        self.assertAlmostEqual(schedule[1]["matrix"][0][1], 0.15)
        self.assertEqual(schedule[2]["matrix"], [[1.0, 0.0], [0.0, 1.0]])

    def test_odds_ratio_uses_odds_not_probability_multiplication(self):
        transformation = json.loads(self.TEMPLATE.read_text())
        transformation["measure"] = "odds_ratio"
        transformation["relative_effect"]["value"] = 2.0
        schedule = relative_effect_adapter.derive(transformation, 3, 1.0)
        self.assertAlmostEqual(schedule[0]["matrix"][0][1], 0.2 / 1.1)
        self.assertAlmostEqual(schedule[1]["matrix"][0][1], 0.4 / 1.2)

    def test_all_zero_baseline_and_unsafe_risk_ratio_fail_closed(self):
        transformation = json.loads(self.TEMPLATE.read_text())
        for item in transformation["baseline_cycle_probabilities"]:
            item["probability"]["value"] = 0.0
        with self.assertRaisesRegex(ValueError, "at least one baseline"):
            relative_effect_adapter.derive(transformation, 3, 1.0)

        transformation = json.loads(self.TEMPLATE.read_text())
        transformation["relative_effect"]["value"] = 5.0
        with self.assertRaisesRegex(ValueError, "invalid probability|strictly below"):
            relative_effect_adapter.derive(transformation, 3, 1.0)


class HazardRatioAdapterContractTests(unittest.TestCase):
    TEMPLATE = ROOT / (
        "runtime/skills/core/heor-hazard-ratio-adapter/assets/"
        "hazard-ratio-transformation.template.json"
    )

    def test_template_recomputes_cumulative_hazard_increments(self):
        transformation = json.loads(self.TEMPLATE.read_text())
        schedule = hazard_ratio_adapter.derive(transformation)
        self.assertEqual([item["start_cycle"] for item in schedule], [1, 2, 3])
        self.assertAlmostEqual(schedule[0]["matrix"][0][1], -math.expm1(-0.075))
        self.assertAlmostEqual(schedule[1]["matrix"][0][1], -math.expm1(-0.15))
        self.assertEqual(schedule[2]["matrix"], [[1.0, 0.0], [0.0, 1.0]])

    def test_nonmonotone_baseline_and_saturated_probability_fail_closed(self):
        transformation = json.loads(self.TEMPLATE.read_text())
        transformation["baseline_cumulative_hazards"][1]["cumulative_hazard"][
            "value"
        ] = 0.05
        with self.assertRaisesRegex(ValueError, "non-decreasing"):
            hazard_ratio_adapter.derive(transformation)

        transformation = json.loads(self.TEMPLATE.read_text())
        transformation["hazard_ratio"]["value"] = 1e308
        with self.assertRaisesRegex(ValueError, "invalid probability"):
            hazard_ratio_adapter.derive(transformation)


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
        self.assertFalse(result["app_review_checked"])
        self.assertEqual(result["required_app_reviewers_per_extraction"], 2)

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

    def test_empty_prepared_ledger_is_importable_but_not_complete(self):
        value = evidence_fixture()
        value["searches"] = []
        value["records"] = []
        value["extractions"] = []
        result = evidence.audit(value)
        self.assertFalse(result["complete"])
        self.assertTrue(result["importable"])

    def test_imported_candidate_is_safe_to_extend_but_not_research_complete(self):
        value = evidence_fixture()
        value["records"][0]["screening"] = {
            "title_abstract": "not_assessed",
            "full_text": "not_assessed",
        }
        del value["records"][0]["critical_appraisal"]
        value["extractions"] = []
        result = evidence.audit(value)
        self.assertFalse(result["complete"])
        self.assertTrue(result["importable"])
        self.assertEqual(result["not_assessed_count"], 1)

    def test_complete_app_search_binding_passes_as_an_indivisible_unit(self):
        value = evidence_fixture()
        value["searches"][0].update({
            "source": "pubmed",
            "authorization_event_id": "a" * 32,
            "request_sha256": "b" * 64,
            "run_path": "heor/evidence-search-runs/request-event.json",
            "run_sha256": "c" * 64,
            "endpoint": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
            "response_sha256": ["d" * 64],
        })
        self.assertTrue(evidence.audit(value)["complete"])
        del value["searches"][0]["run_sha256"]
        result = evidence.audit(value)
        self.assertFalse(result["complete"])
        self.assertTrue(any("incomplete app-search binding" in error for error in result["errors"]))

    def test_unknown_fields_and_invalid_dates_fail_closed(self):
        value = evidence_fixture()
        value["unreviewed_claim"] = True
        value["searches"][0]["searched_on"] = "2026-02-30"
        result = evidence.audit(value)
        self.assertFalse(result["complete"])
        self.assertTrue(any("unsupported field" in error for error in result["errors"]))
        self.assertTrue(any("searched_on" in error for error in result["errors"]))

    def test_reported_digest_can_bind_exact_file_bytes(self):
        value = evidence_fixture()
        raw = json.dumps(value, ensure_ascii=False, indent=2).encode() + b"\n"
        result = evidence.audit(value, raw_sha256=hashlib.sha256(raw).hexdigest())
        self.assertEqual(result["synthesis_sha256"], hashlib.sha256(raw).hexdigest())


class EconomicInputsContractTests(unittest.TestCase):
    def fixture(self):
        return {
            "schema_version": "0.12.0",
            "analysis_id": "economic-contract-test",
            "economic_basis": {"currency": "GBP", "price_year": 2026},
            "partitioned_survival_analysis": {"path": "heor/partitioned-survival-plan.json"},
            "states": ["progression_free", "progressed", "dead"],
            "cycles": 120,
            "cycle_length_years": 1 / 12,
            "discount_rates": {"costs": 0.035, "outcomes": 0.035},
            "half_cycle_correction": True,
            "willingness_to_pay": None,
            "strategy_order": ["usual_care", "new_treatment"],
            "baseline_strategy_id": "usual_care",
            "strategies": {
                "usual_care": {"name": "Usual care", "state_costs": [1, 2, 0], "state_utilities": [0.8, 0.5, 0]},
                "new_treatment": {"name": "New treatment", "state_costs": [3, 2, 0], "state_utilities": [0.82, 0.5, 0]},
            },
        }

    def test_structure_neutral_contract_rejects_markov_fields(self):
        plan = self.fixture()
        self.assertEqual(economic_inputs.validate(plan), [])
        plan["strategies"]["usual_care"]["initial_distribution"] = [1, 0, 0]
        errors = economic_inputs.validate(plan)
        self.assertTrue(any("transition structure is forbidden" in error for error in errors))


class InputProvenanceContractTests(unittest.TestCase):
    def fixture(self):
        synthesis = evidence_fixture()
        paths = list(input_provenance.BASE_PATHS) + [
            f"strategies.{role}.{field}"
            for role in ("comparator", "intervention")
            for field in (
                "initial_distribution",
                "transition_matrix",
                "state_costs",
                "state_utilities",
            )
        ] + ["willingness_to_pay"]
        model_values = {
            "cycles": 3,
            "cycle_length_years": 1.0,
            "discount_rates.costs": 0.05,
            "discount_rates.outcomes": 0.05,
            "half_cycle_correction": True,
            "strategies.comparator.initial_distribution": [1.0, 0.0, 0.0],
            "strategies.comparator.transition_matrix": [
                [0.7, 0.2, 0.1], [0.0, 0.7, 0.3], [0.0, 0.0, 1.0]
            ],
            "strategies.comparator.state_costs": [1000.0, 3000.0, 0.0],
            "strategies.comparator.state_utilities": [0.8, 0.5, 0.0],
            "strategies.intervention.initial_distribution": [1.0, 0.0, 0.0],
            "strategies.intervention.transition_matrix": [
                [0.8, 0.15, 0.05], [0.0, 0.75, 0.25], [0.0, 0.0, 1.0]
            ],
            "strategies.intervention.state_costs": [4000.0, 3000.0, 0.0],
            "strategies.intervention.state_utilities": [0.8, 0.5, 0.0],
            "willingness_to_pay": 100000.0,
        }
        synthesis["extractions"] = [
            {
                "extraction_id": f"extract-{index}",
                "record_id": "trial-1",
                "target": path,
                "extracted_value": json.dumps(model_values[path], separators=(",", ":")),
                "source_location": f"Table {index + 1}",
                "applicability": "Contract-test fixture",
                "verification_status": "agent_extracted",
            }
            for index, path in enumerate(paths)
        ]
        synthesis_raw = json.dumps(synthesis, ensure_ascii=False, indent=2).encode() + b"\n"
        monetary_values = {
            path: (value if isinstance(value, list) else [value])
            for path, value in model_values.items()
            if path.endswith("state_costs") or path == "willingness_to_pay"
        }
        plan = {
            "schema_version": "0.3.0",
            "economic_basis": {"currency": "CNY", "price_year": 2026},
            "states": ["stable", "progressed", "dead"],
            "willingness_to_pay": 100000,
            "cycles": model_values["cycles"],
            "cycle_length_years": model_values["cycle_length_years"],
            "discount_rates": {
                "costs": model_values["discount_rates.costs"],
                "outcomes": model_values["discount_rates.outcomes"],
            },
            "half_cycle_correction": model_values["half_cycle_correction"],
            "strategies": {
                role: {
                    field: model_values[f"strategies.{role}.{field}"]
                    for field in (
                        "initial_distribution", "transition_matrix", "state_costs", "state_utilities"
                    )
                }
                for role in ("comparator", "intervention")
            },
            "evidence_synthesis": {
                "path": "heor/evidence-synthesis.json",
                "content_sha256": hashlib.sha256(synthesis_raw).hexdigest(),
            },
            "evidence_sources": [{
                "id": "trial-1",
                "title": "Treatment A randomized trial",
                "source_type": "randomized_trial",
                "url": "https://example.test/trial-1",
                "accessed_on": "2026-07-14",
            }],
            "assumptions": [],
            "input_provenance": [
                {
                    "path": path,
                    "source_ids": ["trial-1"],
                    "extraction_ids": [f"extract-{index}"],
                    "assumption_ids": [],
                    "unit": "model-specific",
                    "jurisdiction": "China",
                    "derivation": {
                        "method": (
                            "monetary_adjustment" if path in monetary_values else "direct_evidence"
                        ),
                        "model_value": model_values[path],
                    },
                    **({
                        "currency": "CNY",
                        "price_year": 2026,
                        "monetary_adjustments": [
                            {
                                **({"target_index": target_index}
                                   if path.endswith("state_costs") else {}),
                                "source_value": source_value,
                                "source_currency": "CNY",
                                "source_price_year": 2026,
                                "factor": 1.0,
                                "method": "none",
                                "basis_ids": [],
                                "source_extraction_id": f"extract-{index}",
                                **({"source_index": target_index}
                                   if path.endswith("state_costs") else {}),
                            }
                            for target_index, source_value in enumerate(monetary_values[path])
                        ],
                    } if path in monetary_values else {}),
                    "selection_rationale": "Direct contract-test extraction",
                    "uncertainty_status": "fixed",
                }
                for index, path in enumerate(paths)
            ],
        }
        return plan, synthesis, hashlib.sha256(synthesis_raw).hexdigest()

    def test_exact_synthesis_and_extraction_links_pass_structural_review(self):
        plan, synthesis, digest = self.fixture()
        result = input_provenance.audit(plan, synthesis, digest)
        self.assertTrue(result["complete"], result)
        self.assertFalse(result["human_verification_checked"])
        self.assertEqual(result["required_app_reviewers_per_extraction"], 2)
        self.assertEqual(len(result["selected_extraction_ids"]), 14)

    def test_schema_012_requires_only_common_economic_inputs_and_forbids_transitions(self):
        plan, synthesis, digest = self.fixture()
        plan["schema_version"] = "0.12.0"
        plan["strategy_order"] = ["comparator", "intervention"]
        plan["baseline_strategy_id"] = "comparator"
        plan["partitioned_survival_analysis"] = {
            "path": "heor/partitioned-survival-plan.json"
        }
        excluded = {
            f"strategies.{role}.{field}"
            for role in ("comparator", "intervention")
            for field in ("initial_distribution", "transition_matrix")
        }
        for strategy in plan["strategies"].values():
            strategy.pop("initial_distribution")
            strategy.pop("transition_matrix")
        plan["input_provenance"] = [
            item for item in plan["input_provenance"] if item["path"] not in excluded
        ]

        result = input_provenance.audit(plan, synthesis, digest)

        self.assertTrue(result["complete"], result)
        self.assertEqual(result["required_inputs"], 10)
        plan["strategies"]["intervention"]["transition_matrix"] = [[1.0]]
        rejected = input_provenance.audit(plan, synthesis, digest)
        self.assertFalse(rejected["complete"])
        self.assertTrue(
            any("transition structure is forbidden" in error for error in rejected["errors"]),
            rejected,
        )

    def test_schema_04_schedule_replaces_static_matrix_provenance(self):
        plan, synthesis, _ = self.fixture()
        plan["schema_version"] = "0.4.0"
        schedule = [
            {"start_cycle": 1, "matrix": [[0.8, 0.15, 0.05], [0, 0.75, 0.25], [0, 0, 1]]},
            {"start_cycle": 2, "matrix": [[0.75, 0.17, 0.08], [0, 0.7, 0.3], [0, 0, 1]]},
        ]
        del plan["strategies"]["intervention"]["transition_matrix"]
        plan["strategies"]["intervention"]["transition_schedule"] = schedule
        mapping = next(
            item for item in plan["input_provenance"]
            if item["path"] == "strategies.intervention.transition_matrix"
        )
        extraction_id = mapping["extraction_ids"][0]
        mapping["path"] = "strategies.intervention.transition_schedule"
        mapping["derivation"]["model_value"] = schedule
        extraction = next(
            item for item in synthesis["extractions"]
            if item["extraction_id"] == extraction_id
        )
        extraction["target"] = mapping["path"]
        extraction["extracted_value"] = json.dumps(schedule, separators=(",", ":"))
        synthesis_raw = json.dumps(synthesis, ensure_ascii=False, indent=2).encode() + b"\n"
        digest = hashlib.sha256(synthesis_raw).hexdigest()
        plan["evidence_synthesis"]["content_sha256"] = digest

        result = input_provenance.audit(plan, synthesis, digest)

        self.assertTrue(result["complete"], result)
        self.assertEqual(result["required_inputs"], 14)
        self.assertIn(extraction_id, result["selected_extraction_ids"])

    def test_schema_08_requires_provenance_for_every_declared_strategy(self):
        plan, synthesis, _ = self.fixture()
        plan["schema_version"] = "0.8.0"
        plan["baseline_strategy_id"] = "comparator"
        plan["strategy_order"] = ["comparator", "intervention", "alternative"]
        plan["strategies"]["alternative"] = deepcopy(
            plan["strategies"]["intervention"]
        )
        for strategy_id, label in (
            ("comparator", "Standard care"),
            ("intervention", "Treatment A"),
            ("alternative", "Treatment B"),
        ):
            plan["strategies"][strategy_id]["name"] = label

        intervention_mappings = [
            item for item in plan["input_provenance"]
            if item["path"].startswith("strategies.intervention.")
        ]
        for offset, source_mapping in enumerate(intervention_mappings):
            mapping = deepcopy(source_mapping)
            old_extraction_id = mapping["extraction_ids"][0]
            new_extraction_id = f"extract-alternative-{offset}"
            mapping["path"] = mapping["path"].replace(
                "strategies.intervention.", "strategies.alternative."
            )
            mapping["extraction_ids"] = [new_extraction_id]
            if "monetary_adjustments" in mapping:
                for adjustment in mapping["monetary_adjustments"]:
                    adjustment["source_extraction_id"] = new_extraction_id
            plan["input_provenance"].append(mapping)
            extraction = deepcopy(next(
                item for item in synthesis["extractions"]
                if item["extraction_id"] == old_extraction_id
            ))
            extraction["extraction_id"] = new_extraction_id
            extraction["target"] = mapping["path"]
            synthesis["extractions"].append(extraction)

        synthesis_raw = json.dumps(
            synthesis, ensure_ascii=False, indent=2
        ).encode() + b"\n"
        digest = hashlib.sha256(synthesis_raw).hexdigest()
        plan["evidence_synthesis"]["content_sha256"] = digest
        result = input_provenance.audit(plan, synthesis, digest)
        self.assertTrue(result["complete"], result)
        self.assertEqual(result["required_inputs"], 18)

        plan["input_provenance"] = [
            mapping for mapping in plan["input_provenance"]
            if mapping["path"] != "strategies.alternative.state_utilities"
        ]
        incomplete = input_provenance.audit(plan, synthesis, digest)
        self.assertFalse(incomplete["complete"])
        self.assertIn(
            "strategies.alternative.state_utilities",
            incomplete["unsupported_inputs"],
        )

    def test_schema_05_competing_rates_reproduce_a_complete_matrix(self):
        plan, synthesis, _ = self.fixture()
        plan["schema_version"] = "0.5.0"
        mapping = next(
            item for item in plan["input_provenance"]
            if item["path"] == "strategies.intervention.transition_matrix"
        )
        extraction_id = mapping["extraction_ids"][0]
        rates = [
            0.1673576634856573,
            0.05578588782855244,
            0.2876820724517809,
        ]
        mapping["derivation"] = {
            "method": "deterministic_transformation",
            "model_value": plan["strategies"]["intervention"]["transition_matrix"],
            "transformation": {
                "operation": "constant_competing_rates",
                "cycle_length_years": 1.0,
                "phases": [{
                    "start_cycle": 1,
                    "rows": [
                        {
                            "self_index": 0,
                            "events": [
                                {
                                    "target_index": 1,
                                    "rate_per_year": rates[0],
                                    "source_extraction_id": extraction_id,
                                    "source_pointer": "/0",
                                },
                                {
                                    "target_index": 2,
                                    "rate_per_year": rates[1],
                                    "source_extraction_id": extraction_id,
                                    "source_pointer": "/1",
                                },
                            ],
                        },
                        {
                            "self_index": 1,
                            "events": [{
                                "target_index": 2,
                                "rate_per_year": rates[2],
                                "source_extraction_id": extraction_id,
                                "source_pointer": "/2",
                            }],
                        },
                        {"self_index": 2, "events": []},
                    ],
                }],
            },
        }
        extraction = next(
            item for item in synthesis["extractions"]
            if item["extraction_id"] == extraction_id
        )
        extraction["extracted_value"] = json.dumps(rates, separators=(",", ":"))
        synthesis_raw = json.dumps(synthesis, ensure_ascii=False, indent=2).encode() + b"\n"
        digest = hashlib.sha256(synthesis_raw).hexdigest()
        plan["evidence_synthesis"]["content_sha256"] = digest

        result = input_provenance.audit(plan, synthesis, digest)

        self.assertTrue(result["complete"], result)

        mapping["derivation"]["transformation"]["phases"][0]["rows"][0]["events"][0][
            "rate_per_year"
        ] = rates[0] + 0.01
        changed = input_provenance.audit(plan, synthesis, digest)
        self.assertFalse(changed["complete"])
        combined = "; ".join(changed["invalid_mappings"])
        self.assertIn("does not match the bound extraction", combined)
        self.assertIn("do not reproduce", combined)

    def test_schema_06_survival_curve_reproduces_complete_schedule(self):
        rate = 0.22314355131420976
        schedule = [
            {
                "start_cycle": cycle,
                "matrix": [[0.8, 0.2], [0.0, 1.0]],
            }
            for cycle in range(1, 4)
        ]
        plan = {
            "schema_version": "0.6.0",
            "states": ["alive", "dead"],
            "cycles": 3,
            "cycle_length_years": 1.0,
            "strategies": {"intervention": {"transition_schedule": schedule}},
        }
        mapping = {
            "path": "strategies.intervention.transition_schedule",
            "extraction_ids": ["survival-rate"],
            "assumption_ids": [],
            "derivation": {
                "method": "deterministic_transformation",
                "model_value": schedule,
                "transformation": {
                    "operation": "parametric_survival_to_transition_schedule",
                    "cycle_length_years": 1.0,
                    "from_state_index": 0,
                    "event_state_index": 1,
                    "distribution": "exponential",
                    "parameters": {
                        "rate_per_year": {
                            "value": rate,
                            "source_extraction_id": "survival-rate",
                        }
                    },
                },
            },
        }
        extraction_index = {"survival-rate": {"extracted_value": json.dumps(rate)}}

        self.assertEqual(
            input_provenance.survival_curve_reasons(
                plan, mapping["path"], mapping, mapping["derivation"], extraction_index
            ),
            [],
        )

        mapping["derivation"]["transformation"]["parameters"]["rate_per_year"][
            "value"
        ] = rate + 0.01
        errors = input_provenance.survival_curve_reasons(
            plan, mapping["path"], mapping, mapping["derivation"], extraction_index
        )
        self.assertTrue(any("bound extraction" in error for error in errors))
        self.assertTrue(any("does not reproduce" in error for error in errors))

    def test_schema_07_probability_time_reproduces_complete_matrix(self):
        matrix = [[0.8, 0.2], [0.0, 1.0]]
        plan = {
            "schema_version": "0.7.0",
            "states": ["alive", "dead"],
            "cycles": 3,
            "cycle_length_years": 1.0,
            "strategies": {"intervention": {"transition_matrix": matrix}},
        }
        mapping = {
            "path": "strategies.intervention.transition_matrix",
            "extraction_ids": ["two-year-event-probability"],
            "assumption_ids": [],
            "derivation": {
                "method": "deterministic_transformation",
                "model_value": matrix,
                "transformation": {
                    "operation": "single_event_probability_time_conversion",
                    "cycle_length_years": 1.0,
                    "phases": [{
                        "start_cycle": 1,
                        "rows": [
                            {
                                "self_index": 0,
                                "event": {
                                    "target_index": 1,
                                    "source_probability": 0.36,
                                    "source_interval_years": 2.0,
                                    "source_extraction_id": "two-year-event-probability",
                                },
                            },
                            {"self_index": 1, "event": None},
                        ],
                    }],
                },
            },
        }
        extraction_index = {
            "two-year-event-probability": {"extracted_value": "0.36"}
        }

        self.assertEqual(
            input_provenance.probability_time_reasons(
                plan, mapping["path"], mapping, mapping["derivation"], extraction_index
            ),
            [],
        )

        mapping["derivation"]["transformation"]["phases"][0]["rows"][0]["event"][
            "source_probability"
        ] = 0.35
        errors = input_provenance.probability_time_reasons(
            plan, mapping["path"], mapping, mapping["derivation"], extraction_index
        )
        self.assertTrue(any("bound extraction" in error for error in errors))
        self.assertTrue(any("do not reproduce" in error for error in errors))

    def test_schema_09_background_mortality_is_age_aligned_and_basis_bound(self):
        transformation = json.loads(
            BackgroundMortalityAdapterContractTests.TEMPLATE.read_text()
        )
        schedule = background_mortality_adapter.derive(transformation, 3, 0.5)
        plan = {
            "schema_version": "0.9.0",
            "states": ["alive", "dead"],
            "cycles": 3,
            "cycle_length_years": 0.5,
            "strategies": {"intervention": {"transition_schedule": schedule}},
        }
        mapping = {
            "path": "strategies.intervention.transition_schedule",
            "jurisdiction": "replace-with-life-table-jurisdiction",
            "extraction_ids": [
                "replace-with-cycle-1-life-table-extraction-id",
                "replace-with-cycle-2-life-table-extraction-id",
                "replace-with-cycle-3-life-table-extraction-id",
            ],
            "assumption_ids": [
                "replace-with-proposed-excess-mortality-assumption-id",
                "replace-with-proposed-population-exchangeability-assumption-id",
                "replace-with-proposed-no-double-counting-assumption-id",
            ],
            "derivation": {
                "method": "deterministic_transformation",
                "model_value": schedule,
                "transformation": transformation,
            },
        }
        extraction_index = {
            "replace-with-cycle-1-life-table-extraction-id": {
                "extracted_value": json.dumps({"q": 0.1})
            },
            "replace-with-cycle-2-life-table-extraction-id": {
                "extracted_value": json.dumps({"q": 0.1})
            },
            "replace-with-cycle-3-life-table-extraction-id": {
                "extracted_value": json.dumps({"q": 0.2})
            },
        }

        self.assertEqual(
            input_provenance.background_mortality_reasons(
                plan, mapping["path"], mapping, mapping["derivation"], extraction_index
            ),
            [],
        )

        transformation["life_table"]["cycle_probabilities"][1]["attained_age_years"] = 60.0
        self.assertEqual(
            input_provenance.background_mortality_reasons(
                plan, mapping["path"], mapping, mapping["derivation"], extraction_index
            ),
            [],
        )

        saturated_transformation = deepcopy(transformation)
        saturated_transformation["excess_mortality_rate_per_year"]["value"] = 1e308
        saturated_schedule = [
            {"start_cycle": cycle, "matrix": [[0.0, 1.0], [0.0, 1.0]]}
            for cycle in (1, 2, 3)
        ]
        saturated_plan = deepcopy(plan)
        saturated_plan["strategies"]["intervention"]["transition_schedule"] = saturated_schedule
        saturated_mapping = deepcopy(mapping)
        saturated_mapping["derivation"]["model_value"] = saturated_schedule
        saturated_mapping["derivation"]["transformation"] = saturated_transformation
        errors = input_provenance.background_mortality_reasons(
            saturated_plan,
            saturated_mapping["path"],
            saturated_mapping,
            saturated_mapping["derivation"],
            extraction_index,
        )
        self.assertTrue(any("invalid death probability" in error for error in errors), errors)

        transformation["review_bases"]["no_double_counting"]["approved"] = True
        errors = input_provenance.background_mortality_reasons(
            plan, mapping["path"], mapping, mapping["derivation"], extraction_index
        )
        self.assertTrue(any("fields are invalid" in error for error in errors), errors)

        transformation["review_bases"]["no_double_counting"].pop("approved")
        transformation["life_table"]["cycle_probabilities"][1]["attained_age_years"] = 61
        errors = input_provenance.background_mortality_reasons(
            plan, mapping["path"], mapping, mapping["derivation"], extraction_index
        )
        self.assertTrue(any("cycle-aligned" in error for error in errors), errors)

    def test_schema_010_relative_effect_is_recomputed_and_basis_bound(self):
        transformation = json.loads(
            RelativeEffectAdapterContractTests.TEMPLATE.read_text()
        )
        schedule = relative_effect_adapter.derive(transformation, 3, 1.0)
        plan = {
            "schema_version": "0.10.0",
            "states": ["event-free", "event"],
            "cycles": 3,
            "cycle_length_years": 1.0,
            "strategies": {"intervention": {"transition_schedule": schedule}},
        }
        mapping = {
            "path": "strategies.intervention.transition_schedule",
            "extraction_ids": [
                "replace-with-cycle-1-baseline-risk-extraction-id",
                "replace-with-cycle-2-baseline-risk-extraction-id",
                "replace-with-risk-ratio-extraction-id",
            ],
            "assumption_ids": [
                "replace-with-proposed-cycle-3-structural-zero-assumption-id",
                "replace-with-proposed-endpoint-alignment-assumption-id",
                "replace-with-proposed-population-transportability-assumption-id",
                "replace-with-proposed-effect-constancy-assumption-id",
            ],
            "derivation": {
                "method": "deterministic_transformation",
                "model_value": schedule,
                "transformation": transformation,
            },
        }
        extraction_index = {
            "replace-with-cycle-1-baseline-risk-extraction-id": {
                "extracted_value": json.dumps({"probability": 0.1})
            },
            "replace-with-cycle-2-baseline-risk-extraction-id": {
                "extracted_value": json.dumps({"probability": 0.2})
            },
            "replace-with-risk-ratio-extraction-id": {
                "extracted_value": json.dumps({"risk_ratio": 0.75})
            },
        }
        self.assertEqual(
            input_provenance.relative_effect_reasons(
                plan, mapping["path"], mapping, mapping["derivation"], extraction_index
            ),
            [],
        )

        transformation["relative_effect"]["value"] = 5.0
        errors = input_provenance.relative_effect_reasons(
            plan, mapping["path"], mapping, mapping["derivation"], extraction_index
        )
        self.assertTrue(any("invalid treated probability" in error for error in errors), errors)
        self.assertTrue(any("strictly below" in error for error in errors), errors)

        transformation["relative_effect"]["value"] = 0.75
        transformation["measure"] = "hazard_ratio"
        errors = input_provenance.relative_effect_reasons(
            plan, mapping["path"], mapping, mapping["derivation"], extraction_index
        )
        self.assertTrue(any("risk_ratio or odds_ratio" in error for error in errors), errors)

    def test_schema_011_hazard_ratio_is_recomputed_and_basis_bound(self):
        transformation = json.loads(HazardRatioAdapterContractTests.TEMPLATE.read_text())
        schedule = hazard_ratio_adapter.derive(transformation)
        plan = {
            "schema_version": "0.11.0",
            "states": ["event-free", "event"],
            "cycles": 3,
            "cycle_length_years": 1.0,
            "strategies": {"intervention": {"transition_schedule": schedule}},
        }
        mapping = {
            "path": "strategies.intervention.transition_schedule",
            "extraction_ids": ["baseline-h-1", "baseline-h-2", "baseline-h-3", "treatment-hr"],
            "assumption_ids": [
                "endpoint-alignment",
                "population-transportability",
                "proportional-hazards",
                "effect-constancy",
                "treatment-switching",
            ],
            "derivation": {
                "method": "deterministic_transformation",
                "model_value": schedule,
                "transformation": transformation,
            },
        }
        extraction_index = {
            "baseline-h-1": {"extracted_value": json.dumps({"cumulative_hazard": 0.1})},
            "baseline-h-2": {"extracted_value": json.dumps({"cumulative_hazard": 0.3})},
            "baseline-h-3": {"extracted_value": json.dumps({"cumulative_hazard": 0.3})},
            "treatment-hr": {"extracted_value": json.dumps({"hazard_ratio": 0.75})},
        }
        self.assertEqual(
            input_provenance.hazard_ratio_reasons(
                plan, mapping["path"], mapping, mapping["derivation"], extraction_index
            ),
            [],
        )

        transformation["baseline_cumulative_hazards"][1]["cumulative_hazard"][
            "value"
        ] = 0.05
        errors = input_provenance.hazard_ratio_reasons(
            plan, mapping["path"], mapping, mapping["derivation"], extraction_index
        )
        self.assertTrue(any("non-decreasing" in error for error in errors), errors)
        self.assertTrue(any("bound extraction" in error for error in errors), errors)

    def test_schedule_requires_schema_04_and_exactly_one_transition_mechanism(self):
        plan, synthesis, digest = self.fixture()
        plan["strategies"]["intervention"]["transition_schedule"] = [{
            "start_cycle": 1,
            "matrix": plan["strategies"]["intervention"]["transition_matrix"],
        }]

        result = input_provenance.audit(plan, synthesis, digest)

        self.assertFalse(result["complete"])
        combined = "; ".join(result["errors"] + result["invalid_mappings"])
        self.assertIn("exactly one", combined)
        self.assertIn("requires schema_version 0.4.0", combined)

    def test_stale_hash_wrong_target_and_unlinked_record_fail_closed(self):
        plan, synthesis, digest = self.fixture()
        plan["evidence_synthesis"]["content_sha256"] = "0" * 64
        synthesis["extractions"][0]["target"] = "another.path"
        synthesis["extractions"][1]["record_id"] = "another-record"
        result = input_provenance.audit(plan, synthesis, digest)
        self.assertFalse(result["complete"])
        combined = "; ".join(result["errors"] + result["invalid_mappings"])
        self.assertIn("does not match", combined)
        self.assertIn("targets another.path", combined)
        self.assertIn("absent, conflicting, or ineligible", combined)

    def test_monetary_adjustments_must_recompute_every_model_value(self):
        plan, synthesis, digest = self.fixture()
        mapping = next(
            item for item in plan["input_provenance"]
            if item["path"] == "strategies.intervention.state_costs"
        )
        mapping["monetary_adjustments"][0]["source_value"] = 3999.0

        result = input_provenance.audit(plan, synthesis, digest)

        self.assertFalse(result["complete"])
        self.assertIn("does not reproduce model value", "; ".join(result["invalid_mappings"]))

    def test_direct_evidence_value_must_equal_the_model_input(self):
        plan, synthesis, digest = self.fixture()
        synthesis["extractions"][0]["extracted_value"] = "4"

        result = input_provenance.audit(plan, synthesis, digest)

        self.assertFalse(result["complete"])
        self.assertIn("does not equal the model input", "; ".join(result["invalid_mappings"]))

    def test_non_json_extraction_cannot_enter_an_approvable_model(self):
        plan, synthesis, digest = self.fixture()
        synthesis["extractions"][0]["extracted_value"] = "three cycles"

        result = input_provenance.audit(plan, synthesis, digest)

        self.assertFalse(result["complete"])
        self.assertIn("must be strict JSON", "; ".join(result["invalid_mappings"]))

    def test_missing_model_value_cannot_be_approved_as_json_null(self):
        plan, synthesis, digest = self.fixture()
        del plan["cycles"]
        plan["input_provenance"][0]["derivation"]["model_value"] = None
        synthesis["extractions"][0]["extracted_value"] = "null"

        result = input_provenance.audit(plan, synthesis, digest)

        self.assertFalse(result["complete"])
        self.assertIn("current model input is missing or null", "; ".join(result["invalid_mappings"]))

    def test_assumption_only_derivation_has_no_fabricated_extraction(self):
        plan, synthesis, digest = self.fixture()
        mapping = plan["input_provenance"][0]
        mapping["source_ids"] = []
        mapping["extraction_ids"] = []
        mapping["assumption_ids"] = ["cycles-assumption"]
        mapping["derivation"]["method"] = "explicit_assumption"
        plan["assumptions"] = [{
            "id": "cycles-assumption",
            "statement": "Use three annual cycles",
            "reason": "Explicit modeling assumption for the contract test",
            "status": "proposed",
        }]

        result = input_provenance.audit(plan, synthesis, digest)

        self.assertTrue(result["complete"], result)

    def test_monetary_source_value_must_match_its_bound_extraction(self):
        plan, synthesis, digest = self.fixture()
        mapping = next(
            item for item in plan["input_provenance"]
            if item["path"] == "strategies.intervention.state_costs"
        )
        mapping["monetary_adjustments"][0]["source_value"] = 3999.0
        mapping["monetary_adjustments"][0]["factor"] = 4000.0 / 3999.0

        result = input_provenance.audit(plan, synthesis, digest)

        self.assertFalse(result["complete"])
        self.assertIn("does not match the bound extraction", "; ".join(result["invalid_mappings"]))

    def test_documented_cross_basis_adjustment_can_be_recomputed(self):
        plan, synthesis, digest = self.fixture()
        mapping = next(
            item for item in plan["input_provenance"]
            if item["path"] == "willingness_to_pay"
        )
        mapping["monetary_adjustments"] = [{
            "source_value": 12500.0,
            "source_currency": "USD",
            "source_price_year": 2024,
            "factor": 8.0,
            "method": "Documented inflation and exchange-rate composite factor",
            "basis_ids": ["trial-1"],
            "source_extraction_id": mapping["extraction_ids"][0],
        }]
        selected = int(mapping["extraction_ids"][0].split("-")[-1])
        synthesis["extractions"][selected]["extracted_value"] = "12500"

        result = input_provenance.audit(plan, synthesis, digest)

        self.assertTrue(result["complete"], result)


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
    def test_profile_inventory_matches_packaged_resources(self):
        profile_dir = ROOT / "runtime/skills/core/heor-reference-case/assets/profiles"
        profile_paths = sorted(profile_dir.glob("*.json"))
        self.assertGreaterEqual(len(profile_paths), 3)
        tauri = json.loads((ROOT / "apps/desktop/src-tauri/tauri.conf.json").read_text())
        resources = tauri["bundle"]["resources"]
        ids: set[str] = set()
        for profile_path in profile_paths:
            profile = json.loads(profile_path.read_text())
            self.assertNotIn(profile["id"], ids)
            ids.add(profile["id"])
            relative = profile_path.relative_to(ROOT).as_posix()
            self.assertEqual(
                resources.get(f"../../../{relative}"),
                f"reference-cases/{profile_path.name}",
            )

    def test_nice_2026_profile_is_current_source_bound_and_packaged(self):
        relative = (
            "runtime/skills/core/heor-reference-case/assets/profiles/"
            "NICE-PMG36-2026-current.json"
        )
        profile_path = ROOT / relative
        self.assertTrue(profile_path.is_file())
        profile = json.loads(profile_path.read_text())
        self.assertEqual(profile["schema_version"], "0.2.0")
        self.assertEqual(profile["id"], "NICE-PMG36-2026-current")
        self.assertEqual(profile["status"], "current")
        self.assertEqual(profile["effective_on"], "2026-03-31")
        self.assertEqual(
            profile["source_sha256"],
            "b2c39677825d2b954a247086cac7bb355bb91d21aebce4274af744f827d103a7",
        )
        checks = {item["app_check"] for item in profile["requirements"]}
        self.assertTrue({
            "jurisdiction_england",
            "nice_nhs_pss_perspective",
            "discount_0_035",
        }.issubset(checks))
        tauri = json.loads((ROOT / "apps/desktop/src-tauri/tauri.conf.json").read_text())
        resources = tauri["bundle"]["resources"]
        self.assertEqual(
            resources[f"../../../{relative}"],
            "reference-cases/NICE-PMG36-2026-current.json",
        )

    def fixture(self, root: Path, profile_name: str = "CN-2020-current.json"):
        profile_path = ROOT / (
            "runtime/skills/core/heor-reference-case/assets/profiles/" + profile_name
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

    def test_nice_matrix_passes_portable_profile_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.fixture(Path(directory), "NICE-PMG36-2026-current.json")
            self.assertEqual(reference_case.validate(*paths), [])

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

    def test_profile_source_and_app_check_contract_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            assessment_path, plan_path, profile_path = self.fixture(root)
            profile = json.loads(profile_path.read_text())
            profile["source_url"] = "http://example.test/profile.pdf"
            profile["source_sha256"] = "not-a-sha256"
            profile["checked_on"] = "2026-02-31"
            profile["effective_on"] = "2026-04-31"
            profile["requirements"][0]["app_check"] = "unknown_check"
            changed_profile = root / "profile.json"
            changed_profile.write_text(json.dumps(profile, indent=2))
            errors = reference_case.validate(assessment_path, plan_path, changed_profile)
            self.assertIn("profile source_url must use HTTPS", errors)
            self.assertIn("profile source_sha256 is invalid", errors)
            self.assertIn("profile checked_on must be an ISO date", errors)
            self.assertIn("current profile effective_on must be an ISO date", errors)
            self.assertIn("profile requirements[0].app_check is unsupported", errors)


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

    def test_schema_07_accepts_dynamic_multi_strategy_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            uncertainty_path, plan_path = self.fixture(root)
            plan = json.loads(plan_path.read_text())
            plan["schema_version"] = "0.8.0"
            plan["baseline_strategy_id"] = "comparator"
            plan["strategy_order"] = ["comparator", "intervention", "alternative"]
            plan["strategies"]["alternative"] = deepcopy(
                plan["strategies"]["intervention"]
            )
            plan["strategies"]["alternative"]["name"] = "Alternative treatment"
            plan_raw = json.dumps(plan, ensure_ascii=False, indent=2).encode()
            plan_path.write_bytes(plan_raw)

            value = json.loads(uncertainty_path.read_text())
            value["schema_version"] = "0.7.0"
            value["probabilistic_analysis"]["correlation_handling"]["groups"] = []
            value["base_analysis"]["content_sha256"] = hashlib.sha256(
                plan_raw
            ).hexdigest()
            value["parameters"][0]["target"] = "/strategies/alternative/state_costs/0"
            value["parameters"][0]["provenance_path"] = (
                "strategies.alternative.state_costs"
            )
            plan["input_provenance"].append({
                "path": "strategies.alternative.state_costs",
                "source_ids": ["golden-cost-source"],
                "assumption_ids": [],
                "uncertainty_status": "distribution_available",
            })
            input_paths = plan["methodology"]["uncertainty_analysis"]
            input_paths["deterministic"]["input_paths"].append(
                "strategies.alternative.state_costs"
            )
            input_paths["probabilistic"]["input_paths"].append(
                "strategies.alternative.state_costs"
            )
            plan_raw = json.dumps(plan, ensure_ascii=False, indent=2).encode()
            plan_path.write_bytes(plan_raw)
            value["base_analysis"]["content_sha256"] = hashlib.sha256(
                plan_raw
            ).hexdigest()
            uncertainty_path.write_text(json.dumps(value, ensure_ascii=False, indent=2))

            self.assertEqual(uncertainty.validate(uncertainty_path, plan_path), [])

            value["parameters"][0]["target"] = "/strategies/missing/state_costs/0"
            uncertainty_path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
            errors = uncertainty.validate(uncertainty_path, plan_path)
            self.assertTrue(any("allowlisted" in error for error in errors), errors)

    def test_legacy_plan_rejects_parameters_and_scenarios_for_an_extra_strategy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            uncertainty_path, plan_path = self.fixture(root)
            plan = json.loads(plan_path.read_text())
            plan["strategies"]["alternative"] = deepcopy(
                plan["strategies"]["intervention"]
            )
            plan["input_provenance"].append({
                "path": "strategies.alternative.state_costs",
                "source_ids": ["golden-cost-source"],
                "assumption_ids": [],
                "uncertainty_status": "distribution_available",
            })
            methodology = plan["methodology"]["uncertainty_analysis"]
            methodology["deterministic"]["input_paths"].append(
                "strategies.alternative.state_costs"
            )
            methodology["probabilistic"]["input_paths"].append(
                "strategies.alternative.state_costs"
            )
            plan_raw = json.dumps(plan, ensure_ascii=False, indent=2).encode()
            plan_path.write_bytes(plan_raw)

            value = json.loads(uncertainty_path.read_text())
            value["base_analysis"]["content_sha256"] = hashlib.sha256(
                plan_raw
            ).hexdigest()
            value["parameters"][0]["target"] = (
                "/strategies/alternative/state_costs/0"
            )
            value["parameters"][0]["provenance_path"] = (
                "strategies.alternative.state_costs"
            )
            value["structural_scenarios"][0]["replacements"] = [{
                "target": "/strategies/alternative/state_costs/1",
                "value": 2500.0,
            }]
            uncertainty_path.write_text(json.dumps(value, ensure_ascii=False, indent=2))

            errors = uncertainty.validate(uncertainty_path, plan_path)
            self.assertTrue(any("target must be unique and allowlisted" in error for error in errors), errors)
            self.assertTrue(any("provenance_path strategy is not declared" in error for error in errors), errors)
            self.assertTrue(any("replacement outside the allowlist" in error for error in errors), errors)

    def test_time_varying_rows_and_change_point_scenarios_are_allowlisted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = json.loads(
                (ROOT / "python/heor_core/golden_cases/two_strategy_time_varying.json").read_text()
            )
            plan["uncertainty_analysis"] = {"path": "heor/uncertainty-plan.json"}
            paths = [
                "strategies.intervention.state_costs",
                "strategies.intervention.transition_schedule",
            ]
            plan["input_provenance"] = [
                {
                    "path": paths[0],
                    "source_ids": ["golden-cost-source"],
                    "assumption_ids": [],
                    "uncertainty_status": "distribution_available",
                },
                {
                    "path": paths[1],
                    "source_ids": ["golden-transition-source"],
                    "assumption_ids": [],
                    "uncertainty_status": "distribution_available",
                },
            ]
            plan["methodology"] = {"uncertainty_analysis": {
                "deterministic": {"planned": True, "input_paths": paths},
                "probabilistic": {"planned": True, "input_paths": paths, "iterations": 1000},
                "structural_scenarios": ["waning-change-point"],
            }}
            plan_path = root / "heor" / "analysis-plan.json"
            plan_path.parent.mkdir(parents=True)
            plan_raw = json.dumps(plan, ensure_ascii=False, indent=2).encode()
            plan_path.write_bytes(plan_raw)
            value = json.loads(
                (ROOT / "python/heor_core/golden_cases/two_strategy_uncertainty.json").read_text()
            )
            value["analysis_id"] = plan["analysis_id"]
            value["base_analysis"]["content_sha256"] = hashlib.sha256(plan_raw).hexdigest()
            value["probabilistic_analysis"]["decision_thresholds"]["values"] = [
                0, 5000, 10000, 15000, 20000
            ]
            cost = value["parameters"][0]
            cost["deterministic"].update({"low": 50, "high": 150})
            cost["probabilistic"].update({"shape": 100, "scale": 1})
            transition = value["parameters"][1]
            transition["target"] = "/strategies/intervention/transition_schedule/0/matrix/0"
            transition["provenance_path"] = paths[1]
            transition["deterministic"].update({"low": [0.9, 0.1], "high": [0.99, 0.01]})
            transition["probabilistic"]["alpha"] = [95, 5]
            value["structural_scenarios"] = [{
                "id": "waning-change-point",
                "label": "Later waning",
                "rationale": "Tests the declared treatment-waning change point",
                "replacements": [{
                    "target": "/strategies/intervention/transition_schedule/2/start_cycle",
                    "value": 4,
                }],
            }]
            uncertainty_path = root / "heor" / "uncertainty-plan.json"
            uncertainty_path.write_text(json.dumps(value, ensure_ascii=False, indent=2))

            self.assertEqual(uncertainty.validate(uncertainty_path, plan_path), [])

    def test_rate_space_parameter_is_exactly_bound_and_positive(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = json.loads(
                (ROOT / "python/heor_core/golden_cases/two_strategy_rate_derived.json").read_text()
            )
            path = "strategies.intervention.transition_matrix"
            plan["uncertainty_analysis"] = {"path": "heor/uncertainty-plan.json"}
            plan["input_provenance"][1]["uncertainty_status"] = "distribution_available"
            plan["methodology"] = {"uncertainty_analysis": {
                "deterministic": {"planned": True, "input_paths": [path]},
                "probabilistic": {"planned": True, "input_paths": [path], "iterations": 1000},
                "structural_scenarios": ["five-year-horizon"],
            }}
            plan_path = root / "heor" / "analysis-plan.json"
            plan_path.parent.mkdir(parents=True)
            plan_raw = json.dumps(plan, ensure_ascii=False, indent=2).encode()
            plan_path.write_bytes(plan_raw)
            value = json.loads(
                (ROOT / "python/heor_core/golden_cases/two_strategy_uncertainty.json").read_text()
            )
            value["schema_version"] = "0.3.0"
            value["analysis_id"] = plan["analysis_id"]
            value["base_analysis"]["content_sha256"] = hashlib.sha256(plan_raw).hexdigest()
            value["parameters"] = [{
                "id": "intervention-mortality-rate",
                "label": "Intervention mortality event rate",
                "target": "/input_provenance/1/derivation/transformation/phases/0/rows/0/events/0/rate_per_year",
                "provenance_path": path,
                "deterministic": {"low": 0.05, "high": 0.2, "rationale": "Evidence-bounded rate range"},
                "probabilistic": {
                    "type": "gamma", "shape": 4.0, "scale": 0.02634012891445657,
                    "basis_ids": ["intervention-mortality-rate"],
                    "rationale": "Positive rate distribution",
                },
            }]
            uncertainty_path = root / "heor" / "uncertainty-plan.json"
            uncertainty_path.write_text(json.dumps(value, ensure_ascii=False, indent=2))

            self.assertEqual(uncertainty.validate(uncertainty_path, plan_path), [])

            value["parameters"][0]["probabilistic"]["basis_ids"] = ["unlinked"]
            value["parameters"][0]["probabilistic"]["type"] = "beta"
            value["parameters"][0]["probabilistic"].update({"alpha": 2, "beta": 8})
            uncertainty_path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
            errors = uncertainty.validate(uncertainty_path, plan_path)
            self.assertTrue(any("exactly the event source" in error for error in errors))
            self.assertTrue(any("distribution parameters are invalid" in error for error in errors))

    def test_survival_parameter_is_exactly_bound_and_recomputable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = json.loads(
                (ROOT / "python/heor_core/golden_cases/two_strategy_rate_derived.json").read_text()
            )
            plan["schema_version"] = "0.6.0"
            plan["analysis_id"] = "portable-survival-uncertainty"
            path = "strategies.intervention.transition_schedule"
            transformation = {
                "operation": "parametric_survival_to_transition_schedule",
                "cycle_length_years": 1.0,
                "from_state_index": 0,
                "event_state_index": 1,
                "distribution": "weibull",
                "parameters": {
                    "shape": {"value": 2.0, "assumption_id": "weibull-shape"},
                    "scale_years": {"value": 4.0, "assumption_id": "weibull-scale"},
                },
            }
            plan["strategies"]["intervention"].pop("transition_matrix")
            schedule = survival_adapter.derive(transformation, plan["cycles"], 1.0)
            plan["strategies"]["intervention"]["transition_schedule"] = schedule
            plan["input_provenance"][1] = {
                "path": path,
                "source_ids": [],
                "extraction_ids": [],
                "assumption_ids": ["weibull-shape", "weibull-scale"],
                "uncertainty_status": "distribution_available",
                "derivation": {
                    "method": "deterministic_transformation",
                    "model_value": schedule,
                    "transformation": transformation,
                },
            }
            plan["uncertainty_analysis"] = {"path": "heor/uncertainty-plan.json"}
            plan["methodology"] = {"uncertainty_analysis": {
                "deterministic": {"planned": True, "input_paths": [path]},
                "probabilistic": {"planned": True, "input_paths": [path], "iterations": 1000},
                "structural_scenarios": ["five-year-horizon"],
            }}
            plan_path = root / "heor" / "analysis-plan.json"
            plan_path.parent.mkdir(parents=True)
            plan_raw = json.dumps(plan, ensure_ascii=False, indent=2).encode()
            plan_path.write_bytes(plan_raw)
            value = json.loads(
                (ROOT / "python/heor_core/golden_cases/two_strategy_uncertainty.json").read_text()
            )
            value["schema_version"] = "0.5.0"
            value["analysis_id"] = plan["analysis_id"]
            value["base_analysis"]["content_sha256"] = hashlib.sha256(plan_raw).hexdigest()
            value["parameters"] = [{
                "id": "weibull-shape",
                "label": "Intervention Weibull shape",
                "target": "/input_provenance/1/derivation/transformation/parameters/shape/value",
                "provenance_path": path,
                "deterministic": {"low": 1.5, "high": 2.5, "rationale": "Evidence-bounded shape range"},
                "probabilistic": {
                    "type": "lognormal", "mu_log": math.log(2.0), "sigma_log": 0.1,
                    "basis_ids": ["weibull-shape"],
                    "rationale": "Positive shape distribution",
                },
            }]
            value["probabilistic_analysis"]["correlation_handling"]["groups"] = []
            uncertainty_path = root / "heor" / "uncertainty-plan.json"
            uncertainty_path.write_text(json.dumps(value, ensure_ascii=False, indent=2))

            self.assertEqual(uncertainty.validate(uncertainty_path, plan_path), [])

            value["schema_version"] = "0.4.0"
            value["parameters"][0]["probabilistic"]["basis_ids"] = ["unlinked"]
            uncertainty_path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
            errors = uncertainty.validate(uncertainty_path, plan_path)
            self.assertTrue(any("schema_version 0.5.0" in error for error in errors))
            self.assertTrue(any("exactly the survival parameter" in error for error in errors))

    def test_probability_source_is_exactly_bound_and_bounded(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = json.loads(
                (ROOT / "python/heor_core/golden_cases/two_strategy_rate_derived.json").read_text()
            )
            plan["schema_version"] = "0.7.0"
            plan["analysis_id"] = "portable-probability-time-uncertainty"
            source_probabilities = [0.36, 0.19]
            roles = ["comparator", "intervention"]
            for index, (role, probability) in enumerate(zip(roles, source_probabilities)):
                assumption_id = plan["input_provenance"][index]["assumption_ids"][0]
                transformation = {
                    "operation": "single_event_probability_time_conversion",
                    "cycle_length_years": 1.0,
                    "phases": [{
                        "start_cycle": 1,
                        "rows": [
                            {
                                "self_index": 0,
                                "event": {
                                    "target_index": 1,
                                    "source_probability": probability,
                                    "source_interval_years": 2.0,
                                    "assumption_id": assumption_id,
                                },
                            },
                            {"self_index": 1, "event": None},
                        ],
                    }],
                }
                matrix = probability_time_adapter.derive(transformation, 2, 3, 1.0, False)
                plan["strategies"][role]["transition_matrix"] = matrix
                plan["input_provenance"][index]["derivation"] = {
                    "method": "deterministic_transformation",
                    "model_value": matrix,
                    "transformation": transformation,
                }
            path = "strategies.intervention.transition_matrix"
            plan["input_provenance"][1]["uncertainty_status"] = "distribution_available"
            plan["uncertainty_analysis"] = {"path": "heor/uncertainty-plan.json"}
            plan["methodology"] = {"uncertainty_analysis": {
                "deterministic": {"planned": True, "input_paths": [path]},
                "probabilistic": {"planned": True, "input_paths": [path], "iterations": 1000},
                "structural_scenarios": ["five-year-horizon"],
            }}
            plan_path = root / "heor" / "analysis-plan.json"
            plan_path.parent.mkdir(parents=True)
            plan_raw = json.dumps(plan, ensure_ascii=False, indent=2).encode()
            plan_path.write_bytes(plan_raw)

            value = json.loads(
                (ROOT / "python/heor_core/golden_cases/two_strategy_uncertainty.json").read_text()
            )
            value["schema_version"] = "0.6.0"
            value["analysis_id"] = plan["analysis_id"]
            value["base_analysis"]["content_sha256"] = hashlib.sha256(plan_raw).hexdigest()
            value["parameters"] = [{
                "id": "intervention-two-year-event-probability",
                "label": "Intervention two-year event probability",
                "target": "/input_provenance/1/derivation/transformation/phases/0/rows/0/event/source_probability",
                "provenance_path": path,
                "deterministic": {
                    "low": 0.1,
                    "high": 0.3,
                    "rationale": "Evidence-bounded probability range",
                },
                "probabilistic": {
                    "type": "beta",
                    "alpha": 19.0,
                    "beta": 81.0,
                    "basis_ids": ["intervention-mortality-rate"],
                    "rationale": "Bounded source-probability distribution",
                },
            }]
            value["probabilistic_analysis"]["correlation_handling"]["groups"] = []
            uncertainty_path = root / "heor" / "uncertainty-plan.json"
            uncertainty_path.write_text(json.dumps(value, ensure_ascii=False, indent=2))

            self.assertEqual(uncertainty.validate(uncertainty_path, plan_path), [])

            value["parameters"][0]["probabilistic"] = {
                "type": "gamma",
                "shape": 2.0,
                "scale": 0.1,
                "basis_ids": ["unlinked"],
                "rationale": "Invalid source-probability distribution",
            }
            uncertainty_path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
            errors = uncertainty.validate(uncertainty_path, plan_path)
            self.assertTrue(any("exactly the probability source" in error for error in errors))
            self.assertTrue(any("distribution parameters are invalid" in error for error in errors))

    def test_schema_08_varies_only_excess_rate_and_keeps_life_table_fixed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = json.loads(
                (ROOT / "python/heor_core/golden_cases/two_strategy_markov.json").read_text()
            )
            plan.update({
                "schema_version": "0.9.0",
                "analysis_id": "portable-background-mortality-uncertainty",
                "states": ["alive", "dead"],
                "cycles": 3,
                "cycle_length_years": 0.5,
                "strategy_order": ["comparator", "intervention"],
                "baseline_strategy_id": "comparator",
                "uncertainty_analysis": {"path": "heor/uncertainty-plan.json"},
            })
            for role in plan["strategy_order"]:
                strategy = plan["strategies"][role]
                strategy["initial_distribution"] = [1.0, 0.0]
                strategy["state_costs"] = [strategy["state_costs"][0], 0.0]
                strategy["state_utilities"] = [strategy["state_utilities"][0], 0.0]
                strategy["transition_matrix"] = [[0.9, 0.1], [0.0, 1.0]]
            transformation = json.loads(
                BackgroundMortalityAdapterContractTests.TEMPLATE.read_text()
            )
            schedule = background_mortality_adapter.derive(transformation, 3, 0.5)
            plan["strategies"]["intervention"].pop("transition_matrix")
            plan["strategies"]["intervention"]["transition_schedule"] = schedule
            path = "strategies.intervention.transition_schedule"
            plan["input_provenance"] = [{
                "path": path,
                "source_ids": ["life-table-source"],
                "extraction_ids": [
                    "replace-with-cycle-1-life-table-extraction-id",
                    "replace-with-cycle-2-life-table-extraction-id",
                    "replace-with-cycle-3-life-table-extraction-id",
                ],
                "assumption_ids": [
                    "replace-with-proposed-excess-mortality-assumption-id",
                    "replace-with-proposed-population-exchangeability-assumption-id",
                    "replace-with-proposed-no-double-counting-assumption-id",
                ],
                "uncertainty_status": "distribution_available",
                "derivation": {
                    "method": "deterministic_transformation",
                    "model_value": schedule,
                    "transformation": transformation,
                },
            }]
            plan["methodology"] = {"uncertainty_analysis": {
                "deterministic": {"planned": True, "input_paths": [path]},
                "probabilistic": {
                    "planned": True, "input_paths": [path], "iterations": 1000
                },
                "structural_scenarios": ["cost-discount"],
            }}
            plan_path = root / "heor" / "analysis-plan.json"
            plan_path.parent.mkdir(parents=True)
            plan_raw = json.dumps(plan, ensure_ascii=False, indent=2).encode()
            plan_path.write_bytes(plan_raw)

            value = json.loads(
                (ROOT / "python/heor_core/golden_cases/two_strategy_uncertainty.json").read_text()
            )
            value.update({
                "schema_version": "0.8.0",
                "analysis_id": plan["analysis_id"],
                "parameters": [{
                    "id": "disease-excess-mortality",
                    "label": "Disease excess mortality rate",
                    "target": (
                        "/input_provenance/0/derivation/transformation/"
                        "excess_mortality_rate_per_year/value"
                    ),
                    "provenance_path": path,
                    "deterministic": {
                        "low": 0.02,
                        "high": 0.08,
                        "rationale": "Evidence-bounded positive excess-hazard range",
                    },
                    "probabilistic": {
                        "type": "gamma",
                        "shape": 4.0,
                        "scale": 0.0125,
                        "basis_ids": [
                            "replace-with-proposed-excess-mortality-assumption-id"
                        ],
                        "rationale": "Positive excess-hazard distribution",
                    },
                }],
                "structural_scenarios": [{
                    "id": "cost-discount",
                    "label": "Alternative cost discount rate",
                    "rationale": "Checks a non-mortality structural input",
                    "replacements": [{"target": "/discount_rates/costs", "value": 0.03}],
                }],
            })
            value["base_analysis"]["content_sha256"] = hashlib.sha256(plan_raw).hexdigest()
            value["probabilistic_analysis"]["correlation_handling"]["groups"] = []
            value["probabilistic_analysis"]["omitted_parameters"] = [{
                "provenance_path": path,
                "rationale": "General-population life-table q values are fixed in version 0.8.0",
            }]
            uncertainty_path = root / "heor" / "uncertainty-plan.json"
            uncertainty_path.write_text(json.dumps(value, ensure_ascii=False, indent=2))

            self.assertEqual(uncertainty.validate(uncertainty_path, plan_path), [])

            value["parameters"][0]["target"] = (
                "/input_provenance/0/derivation/transformation/"
                "life_table/cycle_probabilities/0/annual_probability/value"
            )
            uncertainty_path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
            errors = uncertainty.validate(uncertainty_path, plan_path)
            self.assertTrue(any("allowlisted" in error for error in errors), errors)

            value["parameters"][0]["target"] = (
                "/input_provenance/0/derivation/transformation/"
                "excess_mortality_rate_per_year/value"
            )
            value["structural_scenarios"][0]["replacements"] = [
                {"target": "/cycle_length_years", "value": 1.0}
            ]
            uncertainty_path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
            errors = uncertainty.validate(uncertainty_path, plan_path)
            self.assertTrue(any("allowlist" in error for error in errors), errors)

            value["schema_version"] = "0.7.0"
            uncertainty_path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
            errors = uncertainty.validate(uncertainty_path, plan_path)
            self.assertTrue(any("0.9.0" in error and "0.8.0" in error for error in errors), errors)

    def test_schema_09_relative_effect_uncertainty_is_measure_specific(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = json.loads(
                (ROOT / "python/heor_core/golden_cases/two_strategy_markov.json").read_text()
            )
            plan.update({
                "schema_version": "0.10.0",
                "analysis_id": "portable-relative-effect-uncertainty",
                "states": ["event-free", "event"],
                "cycles": 3,
                "cycle_length_years": 1.0,
                "strategy_order": ["comparator", "intervention"],
                "baseline_strategy_id": "comparator",
                "uncertainty_analysis": {"path": "heor/uncertainty-plan.json"},
            })
            for role in plan["strategy_order"]:
                strategy = plan["strategies"][role]
                strategy["initial_distribution"] = [1.0, 0.0]
                strategy["state_costs"] = [strategy["state_costs"][0], 0.0]
                strategy["state_utilities"] = [strategy["state_utilities"][0], 0.0]
                strategy["transition_matrix"] = [[0.9, 0.1], [0.0, 1.0]]
            transformation = json.loads(
                RelativeEffectAdapterContractTests.TEMPLATE.read_text()
            )
            schedule = relative_effect_adapter.derive(transformation, 3, 1.0)
            plan["strategies"]["intervention"].pop("transition_matrix")
            plan["strategies"]["intervention"]["transition_schedule"] = schedule
            path = "strategies.intervention.transition_schedule"
            mapping = {
                "path": path,
                "source_ids": ["baseline-risk-source", "relative-effect-source"],
                "extraction_ids": [
                    "replace-with-cycle-1-baseline-risk-extraction-id",
                    "replace-with-cycle-2-baseline-risk-extraction-id",
                    "replace-with-risk-ratio-extraction-id",
                ],
                "assumption_ids": [
                    "replace-with-proposed-cycle-3-structural-zero-assumption-id",
                    "replace-with-proposed-endpoint-alignment-assumption-id",
                    "replace-with-proposed-population-transportability-assumption-id",
                    "replace-with-proposed-effect-constancy-assumption-id",
                ],
                "uncertainty_status": "distribution_available",
                "derivation": {
                    "method": "deterministic_transformation",
                    "model_value": schedule,
                    "transformation": transformation,
                },
            }
            plan["input_provenance"] = [mapping]
            plan["methodology"] = {"uncertainty_analysis": {
                "deterministic": {"planned": True, "input_paths": [path]},
                "probabilistic": {
                    "planned": True, "input_paths": [path], "iterations": 1000
                },
                "structural_scenarios": ["cost-discount"],
            }}
            plan_path = root / "heor" / "analysis-plan.json"
            plan_path.parent.mkdir(parents=True)

            value = json.loads(
                (ROOT / "python/heor_core/golden_cases/two_strategy_uncertainty.json").read_text()
            )
            value.update({
                "schema_version": "0.9.0",
                "analysis_id": plan["analysis_id"],
                "parameters": [{
                    "id": "relative-effect",
                    "label": "Risk ratio",
                    "target": "/input_provenance/0/derivation/transformation/relative_effect/value",
                    "provenance_path": path,
                    "deterministic": {
                        "low": 0.5, "high": 1.5,
                        "rationale": "Bounded RR that cannot produce probability one",
                    },
                    "probabilistic": {
                        "type": "uniform", "low": 0.5, "high": 1.5,
                        "basis_ids": ["replace-with-risk-ratio-extraction-id"],
                        "rationale": "Bounded RR support",
                    },
                }],
                "structural_scenarios": [{
                    "id": "cost-discount",
                    "label": "Alternative cost discount rate",
                    "rationale": "External non-transition scenario",
                    "replacements": [{"target": "/discount_rates/costs", "value": 0.03}],
                }],
            })
            value["probabilistic_analysis"]["correlation_handling"]["groups"] = []
            value["probabilistic_analysis"]["omitted_parameters"] = [{
                "provenance_path": path,
                "rationale": "Baseline cycle risks remain fixed in uncertainty schema 0.9.0",
            }]

            plan_raw = json.dumps(plan, ensure_ascii=False, indent=2).encode()
            plan_path.write_bytes(plan_raw)
            value["base_analysis"]["content_sha256"] = hashlib.sha256(plan_raw).hexdigest()
            uncertainty_path = root / "heor" / "uncertainty-plan.json"
            uncertainty_path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
            self.assertEqual(uncertainty.validate(uncertainty_path, plan_path), [])

            value["parameters"][0]["deterministic"]["high"] = 5.0
            value["parameters"][0]["probabilistic"] = {
                "type": "lognormal", "mu_log": math.log(0.75), "sigma_log": 0.1,
                "basis_ids": ["replace-with-risk-ratio-extraction-id"],
                "rationale": "Invalid unbounded RR",
            }
            uncertainty_path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
            errors = uncertainty.validate(uncertainty_path, plan_path)
            self.assertTrue(any("deterministic high" in error for error in errors), errors)
            self.assertTrue(any("bounded Uniform" in error for error in errors), errors)

            transformation["measure"] = "odds_ratio"
            transformation["relative_effect"]["value"] = 2.0
            transformation["relative_effect"]["source_pointer"] = "/odds_ratio"
            schedule = relative_effect_adapter.derive(transformation, 3, 1.0)
            plan["strategies"]["intervention"]["transition_schedule"] = schedule
            mapping["derivation"]["model_value"] = schedule
            plan_raw = json.dumps(plan, ensure_ascii=False, indent=2).encode()
            plan_path.write_bytes(plan_raw)
            value["base_analysis"]["content_sha256"] = hashlib.sha256(plan_raw).hexdigest()
            value["parameters"][0]["label"] = "Odds ratio"
            value["parameters"][0]["deterministic"] = {
                "low": 1.0, "high": 3.0, "rationale": "Positive OR range"
            }
            value["parameters"][0]["probabilistic"] = {
                "type": "lognormal", "mu_log": math.log(2.0), "sigma_log": 0.1,
                "basis_ids": ["replace-with-risk-ratio-extraction-id"],
                "rationale": "Positive OR distribution",
            }
            uncertainty_path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
            self.assertEqual(uncertainty.validate(uncertainty_path, plan_path), [])

    def test_schema_010_hazard_ratio_uncertainty_is_bounded_and_recomputable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            plan = json.loads(
                (ROOT / "python/heor_core/golden_cases/two_strategy_markov.json").read_text()
            )
            plan.update({
                "schema_version": "0.11.0",
                "analysis_id": "portable-hazard-ratio-uncertainty",
                "states": ["event-free", "event"],
                "cycles": 3,
                "cycle_length_years": 1.0,
                "strategy_order": ["comparator", "intervention"],
                "baseline_strategy_id": "comparator",
                "uncertainty_analysis": {"path": "heor/uncertainty-plan.json"},
            })
            for role in plan["strategy_order"]:
                strategy = plan["strategies"][role]
                strategy["initial_distribution"] = [1.0, 0.0]
                strategy["state_costs"] = [strategy["state_costs"][0], 0.0]
                strategy["state_utilities"] = [strategy["state_utilities"][0], 0.0]
                strategy["transition_matrix"] = [[0.9, 0.1], [0.0, 1.0]]
            transformation = json.loads(
                HazardRatioAdapterContractTests.TEMPLATE.read_text()
            )
            schedule = hazard_ratio_adapter.derive(transformation)
            plan["strategies"]["intervention"].pop("transition_matrix")
            plan["strategies"]["intervention"]["transition_schedule"] = schedule
            path = "strategies.intervention.transition_schedule"
            plan["input_provenance"] = [{
                "path": path,
                "source_ids": ["baseline-hazard-source", "hazard-ratio-source"],
                "extraction_ids": [
                    "baseline-h-1", "baseline-h-2", "baseline-h-3", "treatment-hr"
                ],
                "assumption_ids": [
                    "endpoint-alignment",
                    "population-transportability",
                    "proportional-hazards",
                    "effect-constancy",
                    "treatment-switching",
                ],
                "uncertainty_status": "distribution_available",
                "derivation": {
                    "method": "deterministic_transformation",
                    "model_value": schedule,
                    "transformation": transformation,
                },
            }]
            plan["methodology"] = {"uncertainty_analysis": {
                "deterministic": {"planned": True, "input_paths": [path]},
                "probabilistic": {
                    "planned": True, "input_paths": [path], "iterations": 1000
                },
                "structural_scenarios": ["cost-discount"],
            }}
            plan_path = root / "heor" / "analysis-plan.json"
            plan_path.parent.mkdir(parents=True)

            value = json.loads(
                (ROOT / "python/heor_core/golden_cases/two_strategy_uncertainty.json").read_text()
            )
            value.update({
                "schema_version": "0.10.0",
                "analysis_id": plan["analysis_id"],
                "parameters": [{
                    "id": "hazard-ratio",
                    "label": "Hazard ratio",
                    "target": "/input_provenance/0/derivation/transformation/hazard_ratio/value",
                    "provenance_path": path,
                    "deterministic": {
                        "low": 0.5, "high": 1.0,
                        "rationale": "Reviewed positive HR interval",
                    },
                    "probabilistic": {
                        "type": "uniform", "low": 0.5, "high": 1.0,
                        "basis_ids": ["treatment-hr"],
                        "rationale": "Bounded HR support",
                    },
                }],
                "structural_scenarios": [{
                    "id": "cost-discount",
                    "label": "Alternative cost discount rate",
                    "rationale": "External non-transition scenario",
                    "replacements": [{"target": "/discount_rates/costs", "value": 0.03}],
                }],
            })
            value["probabilistic_analysis"]["correlation_handling"]["groups"] = []
            value["probabilistic_analysis"]["omitted_parameters"] = [{
                "provenance_path": path,
                "rationale": "Baseline cumulative hazards remain fixed",
            }]
            plan_raw = json.dumps(plan, ensure_ascii=False, indent=2).encode()
            plan_path.write_bytes(plan_raw)
            value["base_analysis"]["content_sha256"] = hashlib.sha256(plan_raw).hexdigest()
            uncertainty_path = root / "heor" / "uncertainty-plan.json"
            uncertainty_path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
            self.assertEqual(uncertainty.validate(uncertainty_path, plan_path), [])

            value["parameters"][0]["probabilistic"] = {
                "type": "lognormal", "mu_log": math.log(0.75), "sigma_log": 0.1,
                "basis_ids": ["treatment-hr"], "rationale": "Invalid unbounded HR",
            }
            uncertainty_path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
            errors = uncertainty.validate(uncertainty_path, plan_path)
            self.assertTrue(any("bounded Uniform" in error for error in errors), errors)

    def test_schema_011_partitioned_survival_uncertainty_is_explicitly_partial(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "heor"
            root.mkdir(parents=True)
            plan = json.loads((
                ROOT / "runtime/skills/core/heor-economic-inputs/assets/partitioned-survival-analysis-plan.template.json"
            ).read_text())
            plan.update({
                "analysis_id": "portable-psm-economic-uncertainty",
                "willingness_to_pay": 100000,
                "uncertainty_analysis": {"path": "heor/uncertainty-plan.json"},
                "input_provenance": [{
                    "path": "strategies.intervention.state_costs",
                    "uncertainty_status": "distribution_available",
                    "source_ids": [],
                    "extraction_ids": [],
                    "assumption_ids": ["cost-basis"],
                }],
                "methodology": {"uncertainty_analysis": {
                    "deterministic": {"planned": True, "input_paths": ["strategies.intervention.state_costs"]},
                    "probabilistic": {"planned": True, "input_paths": ["strategies.intervention.state_costs"], "iterations": 1000},
                    "structural_scenarios": ["cost-discount"],
                }},
            })
            plan["economic_basis"] = {"currency": "CNY", "price_year": 2026}
            plan["strategies"]["comparator"]["name"] = "Comparator"
            plan["strategies"]["intervention"]["name"] = "Intervention"
            plan_path = root / "analysis-plan.json"
            plan_raw = json.dumps(plan, sort_keys=True).encode()
            plan_path.write_bytes(plan_raw)

            psm = {"schema_version": "0.3.0", "analysis_id": plan["analysis_id"]}
            materializations = {"schema_version": "0.1.0", "analysis_id": plan["analysis_id"]}
            psm_raw = json.dumps(psm, sort_keys=True).encode()
            materializations_raw = json.dumps(materializations, sort_keys=True).encode()
            psm_path = root / "partitioned-survival-plan.json"
            materializations_path = root / "survival-curve-materializations.json"
            psm_path.write_bytes(psm_raw)
            materializations_path.write_bytes(materializations_raw)

            value = json.loads((
                ROOT / "runtime/skills/core/heor-uncertainty-analysis/assets/partitioned-survival-economic-uncertainty.template.json"
            ).read_text())
            value.update({
                "uncertainty_id": "portable-psm-economic-only",
                "analysis_id": plan["analysis_id"],
            })
            value["base_analysis"]["content_sha256"] = hashlib.sha256(plan_raw).hexdigest()
            value["partitioned_survival_inputs"]["plan"]["content_sha256"] = hashlib.sha256(psm_raw).hexdigest()
            value["partitioned_survival_inputs"]["curve_materializations"]["content_sha256"] = hashlib.sha256(materializations_raw).hexdigest()
            value["parameters"][0]["id"] = "intervention-pf-cost"
            value["parameters"][0]["label"] = "Intervention PF cost"
            value["parameters"][0]["probabilistic"]["basis_ids"] = ["cost-basis"]
            value["probabilistic_analysis"]["decision_thresholds"]["values"] = [50000, 100000]
            value["structural_scenarios"][0].update({
                "id": "cost-discount", "label": "Cost discount", "rationale": "Reviewable alternative"
            })
            uncertainty_path = root / "uncertainty-plan.json"
            uncertainty_path.write_text(json.dumps(value, indent=2))

            self.assertEqual(
                uncertainty.validate(
                    uncertainty_path, plan_path, psm_path, materializations_path
                ),
                [],
            )
            value["probabilistic_analysis"]["omitted_parameters"].pop()
            uncertainty_path.write_text(json.dumps(value, indent=2))
            errors = uncertainty.validate(
                uncertainty_path, plan_path, psm_path, materializations_path
            )
            self.assertTrue(any("explicitly omit every fixed PFS and OS curve" in error for error in errors), errors)

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

    def test_lognormal_correlation_group_is_evidence_bound_and_positive_definite(self):
        self.assertTrue(any(
            "strictly between" in error
            for error in uncertainty.correlation_matrix_errors(
                [[1.0, 1.0], [1.0, 1.0]], 2, "matrix"
            )
        ))
        self.assertTrue(any(
            "strictly positive definite" in error
            for error in uncertainty.correlation_matrix_errors(
                [[1.0, 0.9, 0.9], [0.9, 1.0, -0.9], [0.9, -0.9, 1.0]],
                3,
                "matrix",
            )
        ))
        with tempfile.TemporaryDirectory() as directory:
            uncertainty_path, plan_path = self.fixture(Path(directory))
            value = json.loads(uncertainty_path.read_text())
            value["schema_version"] = "0.4.0"
            first = value["parameters"][0]
            first["probabilistic"] = {
                "type": "lognormal",
                "mu_log": math.log(4000.0),
                "sigma_log": 0.2,
                "basis_ids": ["golden-cost-source"],
                "rationale": "Joint log-scale estimate",
            }
            second = deepcopy(first)
            second.update({
                "id": "intervention-progressed-cost",
                "label": "Intervention progressed-state cost",
                "target": "/strategies/intervention/state_costs/1",
            })
            second["deterministic"] = {
                "low": 2000.0,
                "high": 4000.0,
                "rationale": "Joint evidence interval",
            }
            second["probabilistic"].update({"mu_log": math.log(3000.0), "sigma_log": 0.3})
            value["parameters"] = [first, second]
            value["probabilistic_analysis"]["correlation_handling"]["groups"] = [{
                "id": "joint-costs",
                "parameter_ids": [first["id"], second["id"]],
                "scale": "log_standard_normal",
                "method": "cholesky",
                "correlation_matrix": [[1.0, 0.6], [0.6, 1.0]],
                "basis_ids": ["golden-cost-source"],
                "rationale": "The source reports a joint log-scale covariance estimate.",
            }]
            uncertainty_path.write_text(json.dumps(value, indent=2))
            self.assertEqual(uncertainty.validate(uncertainty_path, plan_path), [])

            invalid_cases = []
            legacy = deepcopy(value)
            legacy["schema_version"] = "0.3.0"
            invalid_cases.append((legacy, "correlation groups require schema_version 0.4.0"))
            asymmetric = deepcopy(value)
            asymmetric["probabilistic_analysis"]["correlation_handling"]["groups"][0]["correlation_matrix"] = [[1.0, 0.6], [0.5, 1.0]]
            invalid_cases.append((asymmetric, "must be symmetric"))
            unlinked = deepcopy(value)
            unlinked["probabilistic_analysis"]["correlation_handling"]["groups"][0]["basis_ids"] = ["unlinked"]
            invalid_cases.append((unlinked, "must be linked by every member parameter distribution"))
            reused = deepcopy(value)
            duplicate = deepcopy(
                reused["probabilistic_analysis"]["correlation_handling"]["groups"][0]
            )
            duplicate["id"] = "duplicate-members"
            reused["probabilistic_analysis"]["correlation_handling"]["groups"].append(duplicate)
            invalid_cases.append((reused, "only one correlation group"))

            for payload, message in invalid_cases:
                with self.subTest(message=message):
                    uncertainty_path.write_text(json.dumps(payload, indent=2))
                    self.assertTrue(
                        any(message in error for error in uncertainty.validate(uncertainty_path, plan_path))
                    )

    def test_decision_thresholds_reject_duplicates_and_missing_primary(self):
        with tempfile.TemporaryDirectory() as directory:
            uncertainty_path, plan_path = self.fixture(Path(directory))
            for values in ([0, 100000, 100000], [0, 50000, 150000]):
                value = json.loads(uncertainty_path.read_text())
                value["probabilistic_analysis"]["decision_thresholds"]["values"] = values
                uncertainty_path.write_text(json.dumps(value, indent=2))
                errors = uncertainty.validate(uncertainty_path, plan_path)
                self.assertTrue(any("decision threshold" in error for error in errors))


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

    def test_schema_08_selects_two_distinct_safe_strategy_order_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            budget_path, plan_path = self.fixture(Path(directory))
            plan = json.loads(plan_path.read_text())
            comparator = plan["strategies"].pop("comparator")
            intervention = plan["strategies"].pop("intervention")
            plan["schema_version"] = "0.8.0"
            plan["strategy_order"] = [
                "standard_care", "new_treatment", "alternative"
            ]
            plan["baseline_strategy_id"] = "standard_care"
            plan["strategies"] = {
                "standard_care": comparator,
                "new_treatment": intervention,
                "alternative": deepcopy(intervention),
            }
            plan_raw = json.dumps(plan, ensure_ascii=False, indent=2).encode()
            plan_path.write_bytes(plan_raw)

            value = json.loads(budget_path.read_text())
            value["strategies"]["comparator"]["id"] = "standard_care"
            value["strategies"]["intervention"]["id"] = "new_treatment"
            value["base_analysis"]["content_sha256"] = hashlib.sha256(
                plan_raw
            ).hexdigest()
            budget_path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
            self.assertEqual(budget_impact.validate(budget_path, plan_path), [])

            value["strategies"]["intervention"]["id"] = "Unknown Strategy"
            budget_path.write_text(json.dumps(value, ensure_ascii=False, indent=2))
            errors = budget_impact.validate(budget_path, plan_path)
            self.assertTrue(any("safe id from analysis strategy_order" in error for error in errors), errors)

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
                "economic_basis": {"currency": "CNY", "price_year": 2026},
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
                    "decision_uncertainty": {
                        "method": "net_monetary_benefit",
                        "primary_threshold": 100000.0,
                        "threshold_source": "declared_grid",
                        "threshold_rationale": "Decision-context presentation range.",
                        "threshold_results": [
                            {
                                "threshold": 100000.0,
                                "expected_incremental_net_monetary_benefit": 61000.0,
                                "intervention_optimal_probability": 0.82,
                                "comparator_optimal_probability": 0.18,
                                "tie_probability": 0.0,
                                "probability_mcse": 0.012,
                                "strategy_with_highest_expected_net_benefit": "intervention",
                                "ceaf_probability": 0.82,
                                "per_person_evpi": 125.0,
                                "per_person_evpi_mcse": 8.0,
                            }
                        ],
                        "population_evpi": None,
                        "evppi": None,
                    },
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
                "cost_effectiveness": {
                    "economic_basis": deepcopy(result_values["base_case_result"]["economic_basis"]),
                    **deepcopy(result_values["base_case_result"]["incremental"]),
                },
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

    def test_multi_strategy_summary_preserves_frontier_without_occupancy(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package_path, package, paths = self.fixture(root)
            base_case = json.loads(paths["base_case_result"].read_text())
            base_case.pop("incremental")
            base_case.update({
                "strategy_order": ["standard", "treatment"],
                "baseline_strategy_id": "standard",
                "strategies": {
                    "standard": {
                        "name": "Standard care", "total_cost": 0.0,
                        "total_qaly": 1.0, "net_monetary_benefit": 100000.0,
                        "occupancy": [[1.0]],
                    },
                    "treatment": {
                        "name": "Treatment", "total_cost": 50000.0,
                        "total_qaly": 2.0, "net_monetary_benefit": 150000.0,
                        "occupancy": [[1.0]],
                    },
                },
                "pairwise_vs_baseline": {"treatment": {"delta_cost": 50000.0}},
                "fully_incremental_analysis": [
                    {"strategy_id": "standard", "status": "frontier", "icer": None},
                    {"strategy_id": "treatment", "status": "frontier", "icer": 50000.0},
                ],
                "optimal_at_primary_threshold": {"strategy_id": "treatment"},
            })
            paths["base_case_result"].write_text(json.dumps(base_case, indent=2))

            uncertainty_result = json.loads(paths["uncertainty_result"].read_text())
            probabilistic = uncertainty_result["probabilistic_analysis"]
            probabilistic.update({
                "strategy_order": ["standard", "treatment"],
                "primary_threshold_strategy_optimal_probabilities": {
                    "standard": 0.25, "treatment": 0.75,
                },
                "primary_threshold_tie_probability": 0.0,
                "mean_net_monetary_benefit_by_strategy": {
                    "standard": 100000.0, "treatment": 150000.0,
                },
                "net_monetary_benefit_mcse_by_strategy": {
                    "standard": 10.0, "treatment": 12.0,
                },
            })
            paths["uncertainty_result"].write_text(
                json.dumps(uncertainty_result, indent=2)
            )

            package["bindings"]["base_case_result"]["content_sha256"] = hashlib.sha256(
                paths["base_case_result"].read_bytes()
            ).hexdigest()
            package["bindings"]["uncertainty_result"]["content_sha256"] = hashlib.sha256(
                paths["uncertainty_result"].read_bytes()
            ).hexdigest()
            loaded = {
                "base_case_result": base_case,
                "uncertainty_result": uncertainty_result,
                "budget_impact_result": json.loads(
                    paths["budget_impact_result"].read_text()
                ),
            }
            package["result_summary"] = reporting.expected_result_summary(loaded)
            package_path.write_text(json.dumps(package, indent=2))

            result = reporting.audit(package_path, root)
            self.assertTrue(result["complete"], result)
            strategies = package["result_summary"]["cost_effectiveness"]["strategies"]
            self.assertNotIn("occupancy", strategies["standard"])
            self.assertNotIn("delta_cost", package["result_summary"]["cost_effectiveness"])

    def test_malformed_multi_strategy_result_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package_path, package, paths = self.fixture(root)
            base_case = json.loads(paths["base_case_result"].read_text())
            base_case.pop("incremental")
            base_case.update({
                "fully_incremental_analysis": [],
                "strategies": {"malformed": "not-an-object"},
            })
            paths["base_case_result"].write_text(json.dumps(base_case, indent=2))
            package["bindings"]["base_case_result"]["content_sha256"] = hashlib.sha256(
                paths["base_case_result"].read_bytes()
            ).hexdigest()
            package_path.write_text(json.dumps(package, indent=2))

            result = reporting.audit(package_path, root)
            self.assertFalse(result["complete"])
            self.assertTrue(any(
                "multi-strategy base-case strategies" in error
                for error in result["errors"]
            ), result)

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

    def test_copied_decision_uncertainty_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package_path, package, _ = self.fixture(root)
            package["result_summary"]["uncertainty"]["decision_uncertainty"][
                "threshold_results"
            ][0]["per_person_evpi"] = 1.0
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
