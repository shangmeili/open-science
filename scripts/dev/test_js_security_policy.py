#!/usr/bin/env python3
"""Fail-closed checks for reviewed JavaScript dependency security pins."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACKAGE_PATH = ROOT / "package.json"
LOCK_PATH = ROOT / "pnpm-lock.yaml"

# GHSA-3jxr-9vmj-r5cp / CVE-2026-13149. Keep each transitive dependency
# within its existing major version while requiring the maintainer's patch.
REQUIRED_OVERRIDES = {
    "brace-expansion@1.1.15": "1.1.16",
    "brace-expansion@2.1.1": "2.1.2",
}
FORBIDDEN_LOCK_ENTRIES = {
    "brace-expansion@1.1.15:",
    "brace-expansion@2.1.1:",
}


class JavaScriptSecurityPolicyTests(unittest.TestCase):
    def test_reviewed_brace_expansion_patches_are_pinned(self) -> None:
        package = json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))
        overrides = package.get("pnpm", {}).get("overrides", {})
        self.assertEqual(
            {key: overrides.get(key) for key in REQUIRED_OVERRIDES},
            REQUIRED_OVERRIDES,
        )

    def test_lockfile_excludes_cpu_dos_affected_versions(self) -> None:
        lock = LOCK_PATH.read_text(encoding="utf-8")
        for entry in FORBIDDEN_LOCK_ENTRIES:
            self.assertFalse(
                re.search(rf"^  {re.escape(entry)}$", lock, flags=re.MULTILINE),
                f"GHSA-3jxr-9vmj-r5cp affected lock entry remains: {entry}",
            )


if __name__ == "__main__":
    unittest.main()
