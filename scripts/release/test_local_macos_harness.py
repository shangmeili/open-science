#!/usr/bin/env python3
"""Contract tests for the local AI4HEOR macOS build and install harness."""

from __future__ import annotations

import os
import subprocess
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BUILD_RUN = ROOT / "script" / "build_and_run.sh"
INSTALLER = ROOT / "scripts" / "release" / "install_macos_candidate.sh"
ENVIRONMENT = ROOT / ".codex" / "environments" / "environment.toml"


class BuildRunHarnessTests(unittest.TestCase):
    def test_scripts_are_executable_and_parse_as_bash(self) -> None:
        for script in (BUILD_RUN, INSTALLER):
            self.assertTrue(os.access(script, os.X_OK), script)
            subprocess.run(["bash", "-n", script], check=True)

    def test_codex_run_action_uses_the_single_project_entrypoint(self) -> None:
        config = tomllib.loads(ENVIRONMENT.read_text(encoding="utf-8"))
        self.assertEqual(config["name"], "AI4HEOR")
        self.assertEqual(
            config["actions"],
            [
                {
                    "name": "Run",
                    "icon": "run",
                    "command": "./script/build_and_run.sh",
                }
            ],
        )

    def test_build_harness_is_scoped_to_the_project_debug_app(self) -> None:
        script = BUILD_RUN.read_text(encoding="utf-8")
        self.assertIn("target/debug/ai4s-workbench", script)
        self.assertIn("lsof -a -p", script)
        self.assertIn("APP_WORKDIR", script)
        self.assertIn("tauri dev --no-watch", script)
        self.assertIn("tauri build --debug --no-bundle", script)
        self.assertNotIn("pkill -x", script)
        for mode in ("--stop", "--verify", "--logs", "--telemetry", "--debug"):
            self.assertIn(mode, script)


class InstallerHarnessTests(unittest.TestCase):
    def test_installer_fails_closed_before_replacing_the_app(self) -> None:
        script = INSTALLER.read_text(encoding="utf-8")
        self.assertLess(script.index("shasum -a 256"), script.index("mv \"$DESTINATION\""))
        self.assertLess(script.index("lipo -archs"), script.index("mv \"$DESTINATION\""))
        self.assertIn("install-backups", script)
        self.assertIn("the previous AI4HEOR app was restored", script)
        self.assertIn("main process and bundled OpenCode are running", script)
        self.assertIn("xattr -cr", script)

    def test_installer_rejects_a_nonexistent_dmg_without_touching_applications(self) -> None:
        result = subprocess.run(
            [
                str(INSTALLER),
                "--dmg",
                "/tmp/ai4heor-does-not-exist.dmg",
                "--sha256",
                "0" * 64,
            ],
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("DMG not found", result.stderr)


if __name__ == "__main__":
    unittest.main()
