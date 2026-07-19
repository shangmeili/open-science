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


class TauriHeorResourceTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
