#!/usr/bin/env python3
"""Contract tests for first-party AI4HEOR research artifacts."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import math
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
survival_adapter = load(
    "validate_survival_curve",
    "runtime/skills/core/heor-survival-curve-adapter/scripts/validate_survival_curve.py",
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


class InputProvenanceContractTests(unittest.TestCase):
    def fixture(self):
        synthesis = evidence_fixture()
        paths = list(input_provenance.BASE_PATHS) + ["willingness_to_pay"]
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
