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
DESKTOP_SOURCE = ROOT / "apps" / "desktop" / "src"
PPTX_PREVIEW_GLOB = (
    "pptx-preview@*/node_modules/pptx-preview/dist/pptx-preview.es.js"
)
EXCELJS_GLOB = "exceljs@*/node_modules/exceljs"

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
    def test_desktop_router_has_no_ssr_hydration_or_data_redirect_surface(self) -> None:
        # GHSA-337j-9hxr-rhxg requires manual SSR hydration. GHSA-jjmj-jmhj-qwj2
        # requires an application open-redirect surface. AI4HEOR uses a local
        # client router with static route objects and no loaders/actions.
        router = (DESKTOP_SOURCE / "app" / "router.tsx").read_text(encoding="utf-8")
        main = (DESKTOP_SOURCE / "main.tsx").read_text(encoding="utf-8")
        self.assertIn("createBrowserRouter(routes)", router)
        for token in (
            "createStaticRouter",
            "StaticRouterProvider",
            "hydrationData",
            "hydrateRoot",
            "deserializeErrors",
            "redirect(",
            "loader:",
            "action:",
        ):
            self.assertNotIn(token, router + main)

    def test_dynamic_application_routes_use_the_internal_encoder(self) -> None:
        raw_dynamic_route = re.compile(r"`/(?:heor|live)/\$\{|`/runs\?run=\$\{")
        violations = []
        for path in DESKTOP_SOURCE.rglob("*"):
            if path.suffix not in {".ts", ".tsx"} or ".test." in path.name:
                continue
            if path.name == "internalRoute.ts":
                continue
            source = path.read_text(encoding="utf-8")
            if raw_dynamic_route.search(source):
                violations.append(str(path.relative_to(ROOT)))
        self.assertEqual(
            violations,
            [],
            "dynamic task/run route bypasses the internal route encoder",
        )

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

    def test_uuid_buffer_apis_are_unreachable_from_packaged_consumers(self) -> None:
        # GHSA-w5hq-g745-h8pq requires a caller-controlled output buffer passed
        # to uuid v3/v5/v6. The two production consumers currently import only
        # v4; fail closed if either dependency changes its UUID API usage.
        pnpm_root = ROOT / "node_modules" / ".pnpm"

        excel_candidates = list(pnpm_root.glob(EXCELJS_GLOB))
        self.assertEqual(len(excel_candidates), 1, "expected one installed exceljs module")
        excel_imports = []
        for path in excel_candidates[0].rglob("*.js"):
            source = path.read_text(encoding="utf-8")
            if re.search(r"require\(['\"]uuid['\"]\)", source):
                excel_imports.append((path, source))
        expected_excel_paths = {
            "dist/es5/xlsx/xform/sheet/cf-ext/cf-rule-ext-xform.js",
            "dist/exceljs.bare.js",
            "dist/exceljs.js",
            "lib/xlsx/xform/sheet/cf-ext/cf-rule-ext-xform.js",
        }
        self.assertEqual(
            {path.relative_to(excel_candidates[0]).as_posix() for path, _ in excel_imports},
            expected_excel_paths,
            "exceljs UUID call sites changed; review GHSA-w5hq-g745-h8pq reachability",
        )
        uuid_require = re.compile(
            r"const\s*\{\s*([^}]*?)\s*\}\s*=\s*require\(['\"]uuid['\"]\)"
        )
        for path, excel_source in excel_imports:
            imports = [
                re.sub(r"\s+", " ", imported).strip()
                for imported in uuid_require.findall(excel_source)
            ]
            self.assertEqual(imports, ["v4: uuidv4"], f"unexpected UUID API in {path}")
            self.assertEqual(
                re.findall(r"\buuidv4\(([^)]*)\)", excel_source),
                ["", ""],
                f"unexpected UUID arguments in {path}",
            )

        pptx_candidates = list(pnpm_root.glob(PPTX_PREVIEW_GLOB))
        self.assertEqual(len(pptx_candidates), 1, "expected one installed pptx-preview module")
        pptx_source = pptx_candidates[0].read_text(encoding="utf-8")
        uuid_imports = re.findall(r'import\{([^}]*)\}from"uuid"', pptx_source)
        self.assertEqual(
            uuid_imports,
            ["v4 as s"],
            "pptx-preview UUID imports changed; review GHSA-w5hq-g745-h8pq reachability",
        )


if __name__ == "__main__":
    unittest.main()
