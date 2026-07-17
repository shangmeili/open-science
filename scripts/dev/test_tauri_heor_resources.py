#!/usr/bin/env python3
"""Keep the bundled deterministic HEOR Python package complete."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TAURI_DIR = ROOT / "apps" / "desktop" / "src-tauri"
CONFIG_PATH = TAURI_DIR / "tauri.conf.json"
PACKAGE_DIR = ROOT / "python" / "heor_core" / "src" / "heor_core"


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


if __name__ == "__main__":
    unittest.main()
