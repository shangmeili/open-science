#!/usr/bin/env python3
"""Contract tests for the retained Open Science v0.2.4 foundation."""

from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "runtime/skills/external/ai4s-skills"
CORE = ROOT / "runtime/skills/core"
REGISTRY = ROOT / "runtime/assets/asset-admission-registry.json"
FOUNDATION_AUDIT = ROOT / "docs/RESEARCH_FOUNDATION_CAPABILITIES.zh-CN.md"
REVISION = "8fa2ab0523082c135598909b227ed8feb48263ad"
SKILLS = {
    "ai4s-agent": "592d07ea7843b019169a7eac07637534efcf6bb2295f18744557005615ae2235",
    "experiment-suite": "826ab1194626f6733e537a649e565118801e342422fe6a0b8fffdec97d90fc90",
    "integrity-auditor": "db4d137dd69ec7295aa6517238ae1f6817abc051395d0708d5283c687a1d5bb4",
    "literature-survey": "c1cec17462ae3ee880c349059fbe3a1801057f71fef6aa40b8387bfeeb3fccc9",
    "mindmap-render": "bf056dc8d77f26cadff1046baf6486b7cebd2ea7c3f9e1b6511405621a2e8e69",
    "paper-writer": "f4567fecfb5d88b65a26dad8834b2e6fb2c18bfa539917d5bfff1be063544bb2",
    "research-explorer": "52d8dc3058c489a0a2ef92e1391af0e921dc4e202c894d46f059cb27ced54dc6",
}


def tree_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    files = sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix(),
    )
    for path in files:
        relative = path.relative_to(root).as_posix().encode()
        content = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


class OpenScienceFoundationTests(unittest.TestCase):
    def test_missing_open_science_foundation_is_a_documented_release_blocker(self):
        audit = FOUNDATION_AUDIT.read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
        first_party = [path for path in CORE.iterdir() if (path / "SKILL.md").is_file()]
        self.assertEqual(len(first_party), 52)
        self.assertIn("严重失误", audit)
        self.assertIn("release blocker（发布阻断项）", audit)
        self.assertIn("总数少于 59 时不得构建安装包", audit)
        self.assertIn("不能删除或降级 Open Science 的通用科研能力", audit)
        self.assertIn("python scripts/dev/test_open_science_foundation.py -v", workflow)

    def test_pinned_skill_pack_is_complete_licensed_and_hash_locked(self):
        self.assertEqual((PACK / ".commit").read_text().strip(), REVISION)
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        assets = {asset["distribution"]["entry"]: asset for asset in registry["assets"]}
        self.assertEqual(set(assets), set(SKILLS))
        for name, expected_hash in SKILLS.items():
            skill = PACK / name
            self.assertTrue((skill / "SKILL.md").is_file(), name)
            license_text = (skill / "LICENSE.txt").read_text(encoding="utf-8")
            self.assertIn("MIT License", license_text)
            self.assertIn("Permission is hereby granted", license_text)
            self.assertFalse(any(path.is_symlink() for path in skill.rglob("*")), name)
            self.assertEqual(tree_sha256(skill), expected_hash, name)
            self.assertEqual(assets[name]["distribution"]["content_sha256"], expected_hash)
            self.assertEqual(assets[name]["source"]["revision"], REVISION)
            self.assertEqual(assets[name]["source"]["license_spdx"], "MIT")

    def test_all_shipped_languages_expose_the_exact_52_plus_7_skill_catalog(self):
        first_party = {
            path.name for path in CORE.iterdir() if (path / "SKILL.md").is_file()
        }
        expected = first_party | set(SKILLS)
        self.assertEqual(len(first_party), 52)
        self.assertEqual(len(expected), 59)
        locale_root = ROOT / "apps/desktop/src/i18n/locales"
        for locale in ("de", "en", "es", "fr", "ja", "ko", "zh-Hans"):
            catalog = json.loads(
                (locale_root / locale / "skills.json").read_text(encoding="utf-8")
            )["catalog"]
            self.assertEqual(set(catalog), expected, locale)
            for name in SKILLS:
                self.assertTrue(catalog[name]["displayName"].strip(), f"{locale}:{name}")
                self.assertTrue(catalog[name]["description"].strip(), f"{locale}:{name}")

    def test_release_fetches_and_packages_only_the_admitted_open_science_pack(self):
        fetcher = (ROOT / "scripts/dev/fetch-skills.sh").read_text(encoding="utf-8")
        workflow = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
        config = json.loads(
            (ROOT / "apps/desktop/src-tauri/tauri.conf.json").read_text(encoding="utf-8")
        )
        self.assertIn(REVISION, fetcher)
        self.assertIn('cp "$SRC/LICENSE" "$skill_dir/LICENSE.txt"', fetcher)
        self.assertNotIn("anthropics/skills", fetcher)
        self.assertIn("bash scripts/dev/fetch-skills.sh", workflow)
        self.assertIn("python scripts/dev/test_open_science_foundation.py -v", workflow)
        self.assertEqual(
            config["bundle"]["resources"]["../../../runtime/skills/external/ai4s-skills"],
            "skills-admitted-ai4s/",
        )

    def test_heor_harness_keeps_general_skills_without_weakening_heor_contracts(self):
        harness = (ROOT / "runtime/harness/AGENTS.md").read_text(encoding="utf-8")
        for name in SKILLS:
            self.assertIn(f"`{name}`", harness)
        self.assertIn("use the matching first-party HEOR Skill", harness)
        self.assertIn("Simulated or illustrative values", harness)
        self.assertIn("not eligible HEOR evidence", harness)
        self.assertIn("do not verify a source", harness)
        self.assertIn("do not", harness)

    def test_seven_curated_science_connectors_are_present(self):
        source = (ROOT / "apps/desktop/src/lib/scienceConnectors.ts").read_text(encoding="utf-8")
        settings = (ROOT / "apps/desktop/src/app/routes/SettingsPage.tsx").read_text(encoding="utf-8")
        tauri_bridge = (ROOT / "apps/desktop/src/lib/tauri.ts").read_text(encoding="utf-8")
        tauri_lib = (ROOT / "apps/desktop/src-tauri/src/lib.rs").read_text(encoding="utf-8")
        installer = (ROOT / "apps/desktop/src-tauri/src/science_mcp.rs").read_text(encoding="utf-8")
        ids = re.findall(r'^\s+id: "([a-z0-9-]+)",$', source, flags=re.MULTILINE)
        self.assertEqual(
            ids,
            ["paper-search", "biomcp", "materials-project", "fred", "spaceweather", "open-meteo", "usgs-water"],
        )
        self.assertIn('import { SCIENCE_CONNECTORS } from "@/lib/scienceConnectors"', settings)
        self.assertIn("SCIENCE_CONNECTORS.filter(", settings)
        self.assertIn("enableConnector(", settings)
        self.assertIn('invoke<string>("setup_science_mcp"', tauri_bridge)
        self.assertIn("science_mcp::setup_science_mcp", tauri_lib)
        self.assertIn('join("science-mcp-env")', installer)
        self.assertIn("is_safe_package(&package)", installer)
        self.assertIn("current task", (ROOT / "runtime/harness/AGENTS.md").read_text(encoding="utf-8"))

    def test_shared_domain_types_and_chart_palette_are_wired_and_do_not_drift(self):
        shared = (ROOT / "packages/shared/src/index.ts").read_text(encoding="utf-8")
        desktop_package = json.loads(
            (ROOT / "apps/desktop/package.json").read_text(encoding="utf-8")
        )
        sdk_package = json.loads((ROOT / "packages/sdk/package.json").read_text(encoding="utf-8"))
        self.assertIn("@ai4s/shared", desktop_package["dependencies"])
        self.assertIn("@ai4s/shared", sdk_package["dependencies"])
        for exported in ("RuntimeStatus", "Project", "Session", "ThreadBlock", "ChartPalette"):
            self.assertRegex(shared, rf"export (?:type|interface) {exported}\b")
        match = re.search(
            r"CHART_PALETTE_LIGHT: ChartPalette = \{\s*categorical: \[([^\]]+)\]",
            shared,
            flags=re.DOTALL,
        )
        self.assertIsNotNone(match)
        palette = re.findall(r'"(#[0-9a-f]{6})"', match.group(1))
        css = (ROOT / "apps/desktop/src/index.css").read_text(encoding="utf-8")
        css_palette = re.findall(r"--series-[1-8]: (#[0-9a-f]{6});", css)[:8]
        mpl = (
            ROOT / "runtime/skills/core/publication-figures/openscience.mplstyle"
        ).read_text(encoding="utf-8")
        mpl_palette = [f"#{value}" for value in re.findall(r"'([0-9a-f]{6})'", mpl.splitlines()[7])]
        self.assertEqual(css_palette, palette)
        self.assertEqual(mpl_palette, palette)


if __name__ == "__main__":
    unittest.main()
