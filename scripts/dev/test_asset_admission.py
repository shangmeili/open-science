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

    @staticmethod
    def unfinished_asset(status: str = "validated-adapter") -> dict:
        return {
            "asset_id": "example/tool",
            "display_name": "Example Tool",
            "kind": "skill",
            "status": status,
            "release_eligible": status == "validated-adapter",
            "source": {
                "repository": "https://example.test/tool",
                "revision": "0123456789abcdef0123456789abcdef01234567",
                "license_spdx": "MIT",
                "license_evidence_url": "https://example.test/tool/LICENSE",
                "license_compatible": True,
            },
            "capability_boundary": {
                "workspace_access": "current-workspace-required",
                "network_egress": "none-by-default",
                "execution": "human-approved",
                "authority": "no-approval-or-decision-authority",
            },
            "industrialization": {
                "adaptation_mode": "rewrite-required",
                "delta_record": "docs/audit.md",
                "contract_tests": [],
                "adversarial_tests": [],
                "platforms": [],
                "security_review": "pending",
                "methods_review": "pending",
                "kill_switch": False,
                "upstream_evidence": ["Pinned source"],
            },
            "distribution": None,
            "blockers": ["Not production ready"],
        }

    def test_registry_is_valid_and_contains_only_release_eligible_adapters(self) -> None:
        self.assertEqual(validate_registry(self.registry), [])
        self.assertEqual(len(self.registry["assets"]), 7)
        self.assertEqual(
            {asset["distribution"]["entry"] for asset in self.registry["assets"]},
            {
                "ai4s-agent",
                "experiment-suite",
                "integrity-auditor",
                "literature-survey",
                "mindmap-render",
                "paper-writer",
                "research-explorer",
            },
        )
        self.assertTrue(all(asset["release_eligible"] for asset in self.registry["assets"]))

    def test_unresolved_or_excluded_source_cannot_enter_release_registry(self) -> None:
        registry = self.changed()
        registry["assets"] = [self.unfinished_asset("quarantined")]
        errors = validate_registry(registry)
        self.assertTrue(any("do not belong in the release registry" in error for error in errors))

    def test_status_edit_cannot_promote_an_unfinished_asset(self) -> None:
        registry = self.changed()
        registry["assets"] = [self.unfinished_asset()]
        errors = validate_registry(registry)
        self.assertTrue(any("industrially complete" in error for error in errors))
        self.assertTrue(any("distribution" in error for error in errors))

    def test_compatible_license_flag_is_required_for_release(self) -> None:
        registry = self.changed()
        asset = self.unfinished_asset()
        asset["source"]["license_compatible"] = False
        registry["assets"] = [asset]
        errors = validate_registry(registry)
        self.assertTrue(any("industrially complete" in error for error in errors))

    def test_duplicate_identity_fails_closed(self) -> None:
        registry = self.changed()
        asset = self.unfinished_asset()
        registry["assets"] = [asset, copy.deepcopy(asset)]
        errors = validate_registry(registry)
        self.assertTrue(any("duplicated" in error for error in errors))

    def test_mutable_branch_is_not_a_source_revision(self) -> None:
        registry = self.changed()
        asset = self.unfinished_asset()
        asset["source"]["revision"] = "main"
        registry["assets"] = [asset]
        errors = validate_registry(registry)
        self.assertTrue(any("full commit" in error for error in errors))

    def test_authority_cannot_be_delegated_to_an_asset(self) -> None:
        registry = self.changed()
        asset = self.unfinished_asset()
        asset["capability_boundary"]["authority"] = "may-approve"
        registry["assets"] = [asset]
        errors = validate_registry(registry)
        self.assertTrue(any("authority" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
