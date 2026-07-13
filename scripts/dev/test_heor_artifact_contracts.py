#!/usr/bin/env python3
"""Contract tests for first-party AI4HEOR research artifacts."""

from __future__ import annotations

import importlib.util
import sys
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


if __name__ == "__main__":
    unittest.main()
