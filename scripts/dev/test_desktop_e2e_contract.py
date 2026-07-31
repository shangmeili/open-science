#!/usr/bin/env python3
"""Contract tests for the test-only native desktop WebDriver harness."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CARGO = ROOT / "apps/desktop/src-tauri/Cargo.toml"
LIB = ROOT / "apps/desktop/src-tauri/src/lib.rs"
VERIFY = ROOT / "scripts/e2e/verify_desktop_webdriver.py"
WORKFLOW = ROOT / ".github/workflows/build.yml"
LICENSE_GENERATOR = ROOT / "scripts/dev/generate_license_inventory.py"
LICENSE_INVENTORY = ROOT / "docs/legal/cargo-lock-components.json"
LICENSE_AUDIT = ROOT / "docs/legal/LICENSING_AUDIT.md"


class DesktopE2EContractTests(unittest.TestCase):
    def test_root_command_builds_and_runs_the_native_test_variant(self) -> None:
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        command = package["scripts"]["test:e2e:desktop"]
        self.assertIn("tauri build --debug --no-bundle", command)
        self.assertIn("--features desktop-e2e", command)
        self.assertIn("scripts/e2e/verify_desktop_webdriver.py", command)

    def test_webdriver_is_exactly_pinned_optional_and_feature_gated(self) -> None:
        cargo = CARGO.read_text(encoding="utf-8")
        self.assertRegex(
            cargo,
            r'desktop-e2e\s*=\s*\["dep:tauri-plugin-wdio-webdriver"\]',
        )
        self.assertRegex(
            cargo,
            r'tauri-plugin-wdio-webdriver\s*=\s*\{[^}]*version\s*=\s*"=1\.2\.0"[^}]*optional\s*=\s*true[^}]*\}',
        )
        lib = LIB.read_text(encoding="utf-8")
        self.assertIn('#[cfg(feature = "desktop-e2e")]', lib)
        self.assertIn("tauri_plugin_wdio_webdriver::init()", lib)
        self.assertNotIn("tauri-plugin-wdio-webdriver", json.dumps(
            json.loads((ROOT / "apps/desktop/package.json").read_text(encoding="utf-8"))
        ))

    def test_verifier_is_isolated_and_drives_real_elements(self) -> None:
        self.assertTrue(VERIFY.is_file())
        text = VERIFY.read_text(encoding="utf-8")
        for required in (
            "TAURI_WEBDRIVER_PORT",
            "TemporaryDirectory",
            '"HOME"',
            '"XDG_CONFIG_HOME"',
            '"/status"',
            '"/session"',
            '/element/{element_id}/click',
            'normalize-space()="新建任务"',
            'normalize-space()="插件与技能"',
            "window.__TAURI_INTERNALS__",
        ):
            self.assertIn(required, text)
        self.assertNotRegex(text, re.compile(r"api[_-]?key|sk-[A-Za-z0-9]", re.I))

    def test_macos_ci_runs_the_native_harness_before_packaging(self) -> None:
        workflow = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("Run native desktop E2E smoke", workflow)
        self.assertIn("pnpm test:e2e:desktop", workflow)
        self.assertLess(
            workflow.index("pnpm test:e2e:desktop"),
            workflow.index("Build the unsigned test app (Tauri)"),
        )

    def test_test_only_driver_is_still_present_in_the_source_license_inventory(self) -> None:
        generator = LICENSE_GENERATOR.read_text(encoding="utf-8")
        self.assertIn('"--all-features"', generator)
        inventory = json.loads(LICENSE_INVENTORY.read_text(encoding="utf-8"))
        drivers = [
            item
            for item in inventory["components"]
            if item["name"] == "tauri-plugin-wdio-webdriver"
        ]
        self.assertEqual(len(drivers), 1)
        self.assertEqual(drivers[0]["version"], "1.2.0")
        self.assertEqual(drivers[0]["license"], "MIT")
        audit = LICENSE_AUDIT.read_text(encoding="utf-8")
        self.assertIn("tauri-plugin-wdio-webdriver 1.2.0", audit)
        self.assertIn("不随产品分发", audit)


if __name__ == "__main__":
    unittest.main()
