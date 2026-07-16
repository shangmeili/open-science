#!/usr/bin/env python3
"""Portable contract tests for the HEOR methods watchlist."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / (
    "runtime/skills/core/heor-methods-watchlist/scripts/"
    "validate_methods_watchlist.py"
)


def load_validator():
    spec = importlib.util.spec_from_file_location("validate_methods_watchlist", VALIDATOR)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def fixture() -> dict:
    return {
        "schema_version": "0.2.0",
        "watchlist_id": "core-methods-2026-07",
        "status": "ready_for_human_review",
        "as_of_date": "2026-07-17",
        "source_order": ["nice-reference-case"],
        "sources": {
            "nice-reference-case": {
                "source_id": "nice-reference-case",
                "title": "NICE health technology evaluations manual",
                "organization": "NICE",
                "jurisdiction": "England",
                "source_type": "method_guideline",
                "publication_status": "current",
                "canonical_url": "https://www.nice.org.uk/process/pmg36",
                "access_mode": "link_only",
                "rights_status": "link_only",
                "rights_note": "Link only; no content is redistributed.",
                "revision": {
                    "label": "PMG36",
                    "published_on": "2025-06-12",
                    "last_checked_on": "2026-07-17",
                    "next_check_due": "2026-10-17",
                },
                "snapshot": None,
                "affected_contracts": ["heor-reference-case"],
                "monitoring_notes": "A Human checks the official landing page.",
            }
        },
        "change_order": [],
        "changes": {},
        "limitations": [
            "Currency status records a dated Human check, not regulatory approval."
        ],
    }


class MethodsWatchlistContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = load_validator()

    def test_link_only_watchlist_is_complete_without_fetching_content(self):
        with tempfile.TemporaryDirectory() as directory:
            audit = self.validator.audit(fixture(), Path(directory))
        self.assertEqual(audit["errors"], [])
        self.assertTrue(audit["complete"])
        self.assertEqual(audit["current_count"], 1)

    def test_local_snapshot_requires_safe_path_and_exact_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            snapshot = workspace / "heor/method-sources/nice-pmg36.pdf"
            snapshot.parent.mkdir(parents=True)
            snapshot.write_bytes(b"licensed local research copy")
            artifact = fixture()
            source = artifact["sources"]["nice-reference-case"]
            source["access_mode"] = "local_snapshot"
            source["rights_status"] = "permission_confirmed"
            source["snapshot"] = {
                "path": "heor/method-sources/nice-pmg36.pdf",
                "content_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
                "media_type": "application/pdf",
            }
            self.assertEqual(self.validator.audit(artifact, workspace)["errors"], [])
            snapshot.write_bytes(b"changed")
            self.assertTrue(self.validator.audit(artifact, workspace)["errors"])

    def test_overdue_source_and_unresolved_change_keep_snapshot_incomplete(self):
        artifact = fixture()
        artifact["sources"]["nice-reference-case"]["revision"]["next_check_due"] = "2026-07-16"
        artifact["change_order"] = ["nice-pmg36-update"]
        artifact["changes"] = {
            "nice-pmg36-update": {
                "change_id": "nice-pmg36-update",
                "source_id": "nice-reference-case",
                "detected_on": "2026-07-17",
                "change_status": "confirmed",
                "previous_revision": "PMG36",
                "current_revision": "PMG36 update",
                "changed_sections": ["discounting"],
                "summary": "The source changed; impact has not yet been resolved.",
                "affected_contracts": ["heor-reference-case"],
                "required_actions": ["Review the reference-case contract."],
                "revalidation_status": "ready_for_human_review",
                "evidence_paths": [],
            }
        }
        with tempfile.TemporaryDirectory() as directory:
            audit = self.validator.audit(artifact, Path(directory))
        self.assertFalse(audit["complete"])
        self.assertEqual(audit["overdue_count"], 1)
        self.assertEqual(audit["unresolved_change_count"], 1)

    def test_rejects_unknown_fields_order_drift_and_path_escape(self):
        mutations = []
        unknown = fixture()
        unknown["approval"] = True
        mutations.append(unknown)
        order = fixture()
        order["source_order"] = []
        mutations.append(order)
        escaped = fixture()
        source = escaped["sources"]["nice-reference-case"]
        source["access_mode"] = "local_snapshot"
        source["rights_status"] = "permission_confirmed"
        source["snapshot"] = {
            "path": "../outside.pdf",
            "content_sha256": "0" * 64,
            "media_type": "application/pdf",
        }
        mutations.append(escaped)
        forged_human = fixture()
        forged_human["change_order"] = ["forged"]
        forged_human["changes"] = {
            "forged": {
                "change_id": "forged",
                "source_id": "nice-reference-case",
                "detected_on": "2026-07-17",
                "change_status": "confirmed",
                "previous_revision": "PMG36",
                "current_revision": "PMG36 update",
                "changed_sections": ["methods"],
                "summary": "Agent-authored Human status must be rejected.",
                "affected_contracts": ["heor-reference-case"],
                "required_actions": ["Review the changed method."],
                "revalidation_status": "ready_for_human_review",
                "human_disposition": "accepted",
                "evidence_paths": [],
            }
        }
        mutations.append(forged_human)
        with tempfile.TemporaryDirectory() as directory:
            for artifact in mutations:
                with self.subTest(artifact=artifact):
                    self.assertTrue(
                        self.validator.audit(deepcopy(artifact), Path(directory))["errors"]
                    )

    def test_template_is_draft_and_contains_no_approval_authority(self):
        template = json.loads((
            ROOT / "runtime/skills/core/heor-methods-watchlist/assets/"
            "methods-watchlist.template.json"
        ).read_text())
        self.assertEqual(template["schema_version"], "0.2.0")
        self.assertEqual(template["status"], "draft")
        self.assertFalse(any("approv" in key.lower() for key in template))
        self.assertNotIn("human_disposition", json.dumps(template))


if __name__ == "__main__":
    unittest.main()
