#!/usr/bin/env python3
"""Keep the bundled deterministic HEOR Python package complete."""

from __future__ import annotations

import hashlib
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TAURI_DIR = ROOT / "apps" / "desktop" / "src-tauri"
CONFIG_PATH = TAURI_DIR / "tauri.conf.json"
PACKAGE_DIR = ROOT / "python" / "heor_core" / "src" / "heor_core"
KNOWLEDGE_BASE_DIR = ROOT / "runtime" / "knowledge-base" / "zh-Hans"
LEGAL_DIR = ROOT / "docs" / "legal"


class TauriHeorResourceTests(unittest.TestCase):
    def test_tauri_build_runs_the_resource_preflight_after_frontend_build(self):
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        command = config["build"]["beforeBuildCommand"]
        self.assertEqual(
            command,
            "pnpm --filter @ai4s/desktop build && node ../../scripts/release/preflight_resources.mjs",
        )
        self.assertTrue((ROOT / "scripts/release/preflight_resources.mjs").is_file())

    def test_heor_test_entrypoints_disable_python_bytecode_caches(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        self.assertIn("python -B -m unittest", package["scripts"]["test:heor"])
        workflow = (ROOT / ".github/workflows/heor-core.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("run: python -B -m unittest", workflow)
        macos_verifier = (ROOT / "scripts/release/verify_macos_package.py").read_text(
            encoding="utf-8"
        )
        linux_verifier = (ROOT / "scripts/dev/verify_linux_packages.py").read_text(
            encoding="utf-8"
        )
        windows_verifier = (
            ROOT / "scripts/release/verify-windows-package.ps1"
        ).read_text(encoding="utf-8")
        self.assertRegex(macos_verifier, r'sys\.executable,\s+"-B",\s+"-m"')
        self.assertRegex(linux_verifier, r'"python3",\s+"-B",\s+"-m"')
        self.assertIn("& python -B -m unittest", windows_verifier)

    def test_every_python_module_is_bundled_once_at_the_expected_path(self):
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        resources = config["bundle"]["resources"]
        expected = {path.resolve() for path in PACKAGE_DIR.glob("*.py")}
        bundled: dict[Path, str] = {}
        for source, destination in resources.items():
            resolved = (TAURI_DIR / source).resolve()
            if resolved.parent == PACKAGE_DIR.resolve() and resolved.suffix == ".py":
                self.assertNotIn(resolved, bundled, f"duplicate bundled module: {resolved.name}")
                bundled[resolved] = destination
        self.assertEqual(set(bundled), expected)
        for source, destination in bundled.items():
            self.assertEqual(destination, f"heor-core/src/heor_core/{source.name}")

    def test_declared_heor_resources_exist(self):
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        for source, destination in config["bundle"]["resources"].items():
            if destination.startswith(("heor-core/", "reference-cases/", "skills-core/")):
                self.assertTrue((TAURI_DIR / source).resolve().exists(), source)

    def test_bundled_delivery_examples_are_heor_specific(self):
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        resources = config["bundle"]["resources"]
        example_destinations = {
            destination
            for destination in resources.values()
            if destination.startswith("examples/")
        }
        self.assertEqual(example_destinations, {"examples/heor-cost-effectiveness/"})
        self.assertNotIn("../../../examples/climate-trends", resources)

    def test_bundled_pharmacoeconomics_learning_library_is_exact_and_dated(self):
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        resources = config["bundle"]["resources"]
        self.assertEqual(
            resources.get("../../../runtime/knowledge-base/zh-Hans"),
            "knowledge-base/zh-Hans/",
        )
        manifest_path = KNOWLEDGE_BASE_DIR / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(
            set(manifest),
            {
                "schemaVersion",
                "bundleId",
                "title",
                "locale",
                "updated",
                "status",
                "boundaries",
                "files",
            },
        )
        self.assertEqual(manifest["schemaVersion"], "ai4heor-bundled-knowledge-base/v1")
        self.assertEqual(manifest["locale"], "zh-Hans")
        self.assertEqual(manifest["updated"], "2026-07-14")
        self.assertEqual(manifest["status"], "dated_learning_material")
        self.assertEqual(manifest["boundaries"]["scientificAuthority"], "human_researcher")
        self.assertEqual(
            manifest["boundaries"]["policyStatus"],
            "verify_current_sources_before_use",
        )
        declared = []
        for entry in manifest["files"]:
            relative = Path(entry["path"])
            self.assertFalse(relative.is_absolute())
            self.assertNotIn("..", relative.parts)
            source = KNOWLEDGE_BASE_DIR / relative
            self.assertTrue(source.is_file(), entry["path"])
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), entry["sha256"])
            declared.append(entry["path"])
        self.assertEqual(declared, sorted(set(declared)))
        actual = sorted(
            path.relative_to(KNOWLEDGE_BASE_DIR).as_posix()
            for path in KNOWLEDGE_BASE_DIR.rglob("*")
            if path.is_file() and path.name != "manifest.json"
        )
        self.assertEqual(declared, actual)
        self.assertIn("01-基础理论/01-稀缺性、效率与机会成本.md", declared)
        self.assertIn("04-最新进展/截至2026-07的方法学与政策进展.md", declared)

        wikilink_count = 0
        for source in KNOWLEDGE_BASE_DIR.rglob("*.md"):
            for raw_target in re.findall(
                r"\[\[([^\]|#]+)", source.read_text(encoding="utf-8")
            ):
                wikilink_count += 1
                target = Path(raw_target)
                if target.suffix != ".md":
                    target = target.with_suffix(".md")
                self.assertTrue(
                    (KNOWLEDGE_BASE_DIR / target).is_file()
                    or (source.parent / target).is_file(),
                    f"broken bundled knowledge-base link in {source}: {raw_target}",
                )
        self.assertGreater(wikilink_count, 0)

    def test_legal_boundary_and_inventories_are_packaged(self):
        config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        resources = config["bundle"]["resources"]
        expected = {
            "../../../LICENSE": "legal/LICENSE.txt",
            "../../../THIRD_PARTY_NOTICES.md": "legal/THIRD_PARTY_NOTICES.md",
            "../../../docs/legal/LICENSING_AUDIT.md": "legal/LICENSING_AUDIT.md",
            "../../../docs/legal/BRAND_ASSET_PROVENANCE.md": "legal/BRAND_ASSET_PROVENANCE.md",
            "../../../docs/legal/REPORT_RENDERER_ASSETS.md": "legal/REPORT_RENDERER_ASSETS.md",
            "../../../docs/legal/npm-production-components.json": "legal/npm-production-components.json",
            "../../../docs/legal/cargo-lock-components.json": "legal/cargo-lock-components.json",
            "../../../runtime/assets/fonts/source-han-sans-2.005R/LICENSE.txt": "legal/fonts/SourceHanSansCN-OFL-1.1.txt",
        }
        for source, destination in expected.items():
            self.assertEqual(resources.get(source), destination)
            self.assertTrue((TAURI_DIR / source).resolve().is_file(), source)

        npm = json.loads(
            (LEGAL_DIR / "npm-production-components.json").read_text(encoding="utf-8")
        )
        cargo = json.loads(
            (LEGAL_DIR / "cargo-lock-components.json").read_text(encoding="utf-8")
        )
        self.assertEqual(npm["lockfile_sha256"], hashlib.sha256((ROOT / "pnpm-lock.yaml").read_bytes()).hexdigest())
        self.assertEqual(
            cargo["lockfile_sha256"],
            hashlib.sha256((TAURI_DIR / "Cargo.lock").read_bytes()).hexdigest(),
        )
        unresolved_npm = [
            component for component in npm["components"] if component["license"] == "Unknown"
        ]
        self.assertEqual(
            [(component["name"], component["versions"]) for component in unresolved_npm],
            [("buffers", ["0.1.1"])],
        )
        self.assertFalse(
            [component for component in cargo["components"] if component["license"] == "Unknown"]
        )
        destinations = set(resources.values())
        self.assertFalse(any("skills-external" in value for value in destinations))
        self.assertFalse(any(value.startswith("mcp/") for value in destinations))

        report_assets = (LEGAL_DIR / "REPORT_RENDERER_ASSETS.md").read_text(
            encoding="utf-8"
        )
        report_font = (
            ROOT
            / "runtime"
            / "assets"
            / "fonts"
            / "source-han-sans-2.005R"
            / "SourceHanSansCN-Regular.otf"
        )
        report_font_license = report_font.with_name("LICENSE.txt")
        self.assertIn(hashlib.sha256(report_font.read_bytes()).hexdigest(), report_assets)
        self.assertIn(
            hashlib.sha256(report_font_license.read_bytes()).hexdigest(), report_assets
        )
        printpdf = [
            component
            for component in cargo["components"]
            if component["name"] == "printpdf" and component["version"] == "0.11.3"
        ]
        self.assertEqual(len(printpdf), 1)
        self.assertEqual(printpdf[0]["license"], "MIT")

    def test_supplied_ai4heor_logo_provenance_matches_normalized_assets(self):
        ui_logo = ROOT / "apps" / "desktop" / "src" / "assets" / "logo.webp"
        icon_source = ROOT / "apps" / "desktop" / "src" / "assets" / "ai4heor-app-icon.png"
        provenance = (LEGAL_DIR / "BRAND_ASSET_PROVENANCE.md").read_text(encoding="utf-8")
        self.assertIn(hashlib.sha256(ui_logo.read_bytes()).hexdigest(), provenance)
        self.assertIn(hashlib.sha256(icon_source.read_bytes()).hexdigest(), provenance)
        self.assertIn("public redistribution not yet cleared", provenance)


if __name__ == "__main__":
    unittest.main()
