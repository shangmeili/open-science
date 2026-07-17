#!/usr/bin/env python3
"""Adversarial contract tests for the AI4HEOR asset admission registry."""

from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from validate_asset_admission import validate_registry  # noqa: E402


class AssetAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = json.loads(
            (ROOT / "runtime/assets/asset-admission-registry.json").read_text(encoding="utf-8")
        )

    def changed(self) -> dict:
        return copy.deepcopy(self.registry)

    def test_registry_is_valid_and_has_no_external_release_asset(self) -> None:
        self.assertEqual(validate_registry(self.registry), [])
        statuses = [asset["status"] for asset in self.registry["assets"]]
        self.assertEqual(len(statuses), 14)
        self.assertEqual(statuses.count("validated-adapter"), 0)
        self.assertEqual(statuses.count("quarantined"), 10)
        self.assertEqual(statuses.count("rejected"), 4)

    def test_inherited_generic_mcp_candidates_remain_quarantined(self) -> None:
        by_id = {asset["asset_id"]: asset for asset in self.registry["assets"]}
        for asset_id in ("paper-search-mcp", "biomcp"):
            asset = by_id[asset_id]
            self.assertEqual(asset["status"], "quarantined")
            self.assertFalse(asset["release_eligible"])
            self.assertIsNone(asset["distribution"])
            self.assertTrue(asset["blockers"])

    def test_status_edit_cannot_promote_an_unfinished_asset(self) -> None:
        registry = self.changed()
        registry["assets"][0]["status"] = "validated-adapter"
        registry["assets"][0]["release_eligible"] = True
        errors = validate_registry(registry)
        self.assertTrue(any("industrially complete" in error for error in errors))
        self.assertTrue(any("distribution" in error for error in errors))

    def test_compatible_license_flag_is_required_for_release(self) -> None:
        registry = self.changed()
        asset = registry["assets"][7]
        asset["status"] = "validated-adapter"
        asset["release_eligible"] = True
        errors = validate_registry(registry)
        self.assertTrue(any("industrially complete" in error for error in errors))

    def test_non_admitted_asset_cannot_have_a_distribution(self) -> None:
        registry = self.changed()
        registry["assets"][0]["distribution"] = {
            "resource_pack": "skills-admitted-test",
            "entry": "candidate",
            "content_sha256": "0" * 64,
        }
        errors = validate_registry(registry)
        self.assertTrue(any("non-distributed" in error for error in errors))

    def test_duplicate_identity_fails_closed(self) -> None:
        registry = self.changed()
        registry["assets"][1]["asset_id"] = registry["assets"][0]["asset_id"]
        errors = validate_registry(registry)
        self.assertTrue(any("duplicated" in error for error in errors))

    def test_mutable_branch_is_not_a_source_revision(self) -> None:
        registry = self.changed()
        registry["assets"][0]["source"]["revision"] = "main"
        errors = validate_registry(registry)
        self.assertTrue(any("full commit" in error for error in errors))

    def test_authority_cannot_be_delegated_to_an_asset(self) -> None:
        registry = self.changed()
        registry["assets"][0]["capability_boundary"]["authority"] = "may-approve"
        errors = validate_registry(registry)
        self.assertTrue(any("authority" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
