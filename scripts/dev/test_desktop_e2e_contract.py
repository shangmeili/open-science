#!/usr/bin/env python3
"""Contract tests for the test-only native desktop WebDriver harness."""

from __future__ import annotations

import json
import importlib.util
import re
import tempfile
import threading
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
BUILD_RS = ROOT / "apps/desktop/src-tauri/build.rs"
STAGING_HELPER = ROOT / "apps/desktop/src-tauri/resource_staging.rs"
STAGING_TRIGGER = ROOT / "apps/desktop/src-tauri/resource-staging.trigger"
TRIGGER_SCRIPT = ROOT / "scripts/release/trigger_resource_staging.mjs"
TAURI_CONFIG = ROOT / "apps/desktop/src-tauri/tauri.conf.json"


def load_verifier():
    spec = importlib.util.spec_from_file_location("ai4heor_desktop_e2e", VERIFY)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load native desktop E2E verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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

    def test_verifier_drives_passive_html_preview_in_real_webview(self) -> None:
        text = VERIFY.read_text(encoding="utf-8")
        for required in (
            "untrusted-e2e.html",
            'normalize-space()="任务文件"',
            'normalize-space()="Task files"',
            "passive-preview-sentinel",
            "local_request_observer",
            "should-not-load.js",
            '"Content-Security-Policy"',
            "script-src 'none'",
            "connect-src 'none'",
            "data-ai4heor-script-executed",
            "__ai4heorE2EHtmlLoaded",
            "find_stable_element",
        ):
            self.assertIn(required, text)

    def test_build_recreates_the_admitted_skill_staging_tree(self) -> None:
        build = BUILD_RS.read_text(encoding="utf-8")
        config = json.loads(TAURI_CONFIG.read_text(encoding="utf-8"))
        before_build = config["build"]["beforeBuildCommand"]
        self.assertTrue(STAGING_HELPER.is_file())
        self.assertTrue(STAGING_TRIGGER.is_file())
        self.assertTrue(TRIGGER_SCRIPT.is_file())
        self.assertIn("mod resource_staging", build)
        self.assertIn("cargo:rerun-if-changed=resource-staging.trigger", build)
        self.assertIn("clean_staged_admitted_skills", build)
        self.assertIn("trigger_resource_staging.mjs", before_build)
        self.assertLess(
            before_build.index("trigger_resource_staging.mjs"),
            before_build.index("preflight_resources.mjs"),
        )

    def test_verifier_fails_closed_on_admitted_asset_deployment_errors(self) -> None:
        verifier = load_verifier()
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "desktop-e2e.log"
            log.write_text(
                "failed to deploy admitted asset skills-admitted-ai4s/integrity-auditor: "
                "content hash mismatch\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(AssertionError, "admitted asset deployment failed"):
                verifier.assert_no_admitted_asset_deployment_errors(log)

    def test_native_driver_uses_a_local_provider_for_a_real_standalone_task(self) -> None:
        verifier = load_verifier()
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            runtime_root = verifier.prepare_local_fixture_runtime(
                home,
                "http://127.0.0.1:54321/anthropic/v1",
            )
            config = json.loads(
                (runtime_root / "xdg-config/opencode/opencode.json").read_text(
                    encoding="utf-8"
                )
            )
            auth = json.loads(
                (runtime_root / "xdg-data/opencode/auth.json").read_text(
                    encoding="utf-8"
                )
            )
        self.assertEqual(
            config["model"],
            "ai4heor-local-fixture/fixture-model",
        )
        self.assertEqual(
            auth["ai4heor-local-fixture"],
            {"type": "api", "key": "fixture-credential-not-a-secret"},
        )
        source = VERIFY.read_text(encoding="utf-8")
        for required in (
            "AI4HEOR E2E project",
            "AI4HEOR E2E standalone task",
            "OPENCODE_CONFIG_CONTENT",
            "fill_composer",
            "choose_fixture_model_if_required",
            "data-project-id",
            "task_row_xpath",
            "active-workspace.txt",
            "question_next_main_reply",
            "QUESTION_QUEUED_PROMPT",
            "bash_next_main_reply",
            "PERMISSION_QUEUED_PROMPT",
            "FIXTURE_BASH_COMMAND",
            "assert_prompt_not_sent",
        ):
            self.assertIn(required, source)

    def test_native_driver_distinguishes_the_main_reply_from_auxiliary_requests(self) -> None:
        verifier = load_verifier()
        main = {
            "messages": [{"role": "user", "content": verifier.TASK_PROMPT}],
            "tools": [{"name": "read"}],
        }
        auxiliary = {
            "messages": [{"role": "user", "content": verifier.TASK_PROMPT}],
            "tools": [],
        }
        self.assertTrue(verifier.is_main_task_request(main))
        self.assertFalse(verifier.is_main_task_request(auxiliary))
        block_content = {
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": "older"}]},
                {
                    "role": "user",
                    "content": [{"type": "text", "text": verifier.QUEUE_PROMPTS[1]}],
                },
            ],
            "tools": [{"name": "read"}],
        }
        self.assertEqual(
            verifier.latest_user_text(block_content),
            verifier.QUEUE_PROMPTS[1],
        )

    def test_local_provider_can_pause_one_main_reply_for_queue_interaction(self) -> None:
        verifier = load_verifier()
        state = verifier.FixtureState()
        waiting, release = state.pause_next_main_reply()
        finished = threading.Event()

        def wait_for_release() -> None:
            state.wait_before_reply(True, {"tools": [{"name": "read"}]})
            finished.set()

        thread = threading.Thread(target=wait_for_release)
        thread.start()
        self.assertTrue(waiting.wait(timeout=1.0))
        self.assertFalse(finished.is_set())
        release.set()
        thread.join(timeout=1.0)
        self.assertTrue(finished.is_set())

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
