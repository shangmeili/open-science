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
PPTX_PREVIEW_GLOB = (
    "pptx-preview@*/node_modules/pptx-preview/dist/pptx-preview.es.js"
)

# GHSA-mh99-v99m-4gvg / CVE-2026-14257. Keep each transitive dependency
# on its compatible maintenance line while requiring the maintainer's
# length-bounded expansion implementation.
REQUIRED_OVERRIDES = {
    "brace-expansion@<1.1.17": "1.1.18",
    "brace-expansion@>=2.0.0 <2.1.3": "2.1.4",
    "brace-expansion@>=4.0.0 <5.0.8": "5.0.9",
}


def oom_affected(version: tuple[int, int, int]) -> bool:
    return (
        version < (1, 1, 17)
        or (2, 0, 0) <= version < (2, 1, 3)
        or (4, 0, 0) <= version < (5, 0, 8)
    )


class JavaScriptSecurityPolicyTests(unittest.TestCase):
    def test_reviewed_brace_expansion_patches_are_pinned(self) -> None:
        package = json.loads(PACKAGE_PATH.read_text(encoding="utf-8"))
        overrides = package.get("pnpm", {}).get("overrides", {})
        self.assertEqual(
            {key: overrides.get(key) for key in REQUIRED_OVERRIDES},
            REQUIRED_OVERRIDES,
        )

    def test_lockfile_excludes_oom_dos_affected_versions(self) -> None:
        lock = LOCK_PATH.read_text(encoding="utf-8")
        versions = {
            tuple(int(part) for part in match.groups())
            for match in re.finditer(
                r"^  brace-expansion@(\d+)\.(\d+)\.(\d+):$",
                lock,
                flags=re.MULTILINE,
            )
        }
        self.assertTrue(versions, "lockfile contains no brace-expansion resolution")
        self.assertEqual(
            sorted(version for version in versions if oom_affected(version)),
            [],
            "GHSA-mh99-v99m-4gvg affected brace-expansion version remains",
        )

    def test_pptx_preview_cannot_construct_affected_echarts_lines_series(self) -> None:
        # GHSA-fgmj-fm8m-jvvx requires the ECharts `lines` series. The locked
        # PPTX adapter currently emits only `line`, `bar`, and `pie`; fail closed
        # when that adapter changes so its untrusted-input reachability is reviewed.
        candidates = list((ROOT / "node_modules" / ".pnpm").glob(PPTX_PREVIEW_GLOB))
        self.assertEqual(len(candidates), 1, "expected one installed pptx-preview module")
        source = candidates[0].read_text(encoding="utf-8")
        chart_types = set(re.findall(r'type:"(line|lines|bar|pie)"', source))

        self.assertEqual(chart_types, {"line", "bar", "pie"})
        self.assertNotIn('type:"lines"', source)


if __name__ == "__main__":
    unittest.main()
