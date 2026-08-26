#!/usr/bin/env python3
"""Unit tests for fail-closed AI4HEOR macOS distribution gates."""

from __future__ import annotations

import importlib.util
import json
import plistlib
import socket
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


ROOT = Path(__file__).resolve().parents[2]


def load_script(name: str):
    path = Path(__file__).with_name(name)
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


credentials = load_script("check_macos_release_credentials.py")
verifier = load_script("verify_macos_package.py")


SIGNED_DETAILS = """Executable=/tmp/AI4HEOR.app/Contents/MacOS/ai4s-workbench
Identifier=com.ai4s.ai4heor
Format=app bundle with Mach-O thin (x86_64)
CodeDirectory v=20500 size=100 flags=0x10000(runtime) hashes=1+7 location=embedded
Signature size=9000
Authority=Developer ID Application: AI4HEOR Test (A1B2C3D4E5)
Authority=Developer ID Certification Authority
Authority=Apple Root CA
Timestamp=Jul 17, 2026 at 2:30:00 AM
Info.plist entries=20
TeamIdentifier=A1B2C3D4E5
Runtime Version=15.0.0
Sealed Resources version=2 rules=13 files=265
Internal requirements count=1 size=200
"""


class CredentialPreflightTests(unittest.TestCase):
    def test_missing_credentials_fail_without_echoing_values(self) -> None:
        with self.assertRaisesRegex(AssertionError, "APPLE_CERTIFICATE"):
            credentials.inspect_environment({})

    def test_identity_and_team_must_be_distribution_values(self) -> None:
        environment = {
            name: "present" for name in credentials.REQUIRED_ENVIRONMENT
        }
        environment["APPLE_SIGNING_IDENTITY"] = "Apple Development: Test"
        environment["APPLE_TEAM_ID"] = "A1B2C3D4E5"
        with self.assertRaisesRegex(AssertionError, "Developer ID Application"):
            credentials.inspect_environment(environment)

    def test_complete_distribution_credentials_pass(self) -> None:
        environment = {
            name: "present" for name in credentials.REQUIRED_ENVIRONMENT
        }
        environment["APPLE_SIGNING_IDENTITY"] = (
            "Developer ID Application: AI4HEOR Test (A1B2C3D4E5)"
        )
        environment["APPLE_TEAM_ID"] = "A1B2C3D4E5"
        self.assertEqual(
            credentials.inspect_environment(environment),
            {
                "authentication": "apple-id-app-password",
                "certificate": "present",
                "signing_identity": "developer-id-application",
                "team_id": "present",
            },
        )

        environment["APPLE_TEAM_ID"] = "Z9Y8X7W6V5"
        with self.assertRaisesRegex(AssertionError, "does not match"):
            credentials.inspect_environment(environment)


class DistributionVerifierTests(unittest.TestCase):
    def test_installed_task_ui_probe_is_semantic_and_bounded(self) -> None:
        probe = ROOT / "scripts/release/verify_macos_accessibility.swift"
        self.assertTrue(probe.is_file())
        source = probe.read_text(encoding="utf-8")
        self.assertIn("AXUIElementCreateApplication", source)
        self.assertIn("AXPress", source)
        self.assertIn("AXTextArea", source)
        self.assertNotIn("CGEvent", source)
        self.assertNotIn("mouseLocation", source)
        for locale in ("zh-Hans", "en"):
            locale_root = ROOT / "apps/desktop/src/i18n/locales" / locale
            heor = json.loads((locale_root / "heor.json").read_text(encoding="utf-8"))
            nav = json.loads((locale_root / "nav.json").read_text(encoding="utf-8"))
            for current_label in (
                heor["placeholder"],
                nav["items"]["new"],
                nav["items"]["files"],
                nav["items"]["skills"],
            ):
                self.assertIn(current_label, source)

        complete = subprocess.CompletedProcess(
            ["swift", str(probe), "101"],
            0,
            stdout=json.dumps(
                {
                    "window_visible": True,
                    "new_task_navigation": True,
                    "composer_editable": True,
                    "task_files_navigation_available": True,
                    "skills_navigation_available": True,
                }
            ),
            stderr="",
        )
        with patch.object(verifier.subprocess, "run", return_value=complete):
            self.assertEqual(
                verifier.verify_installed_task_ui(101),
                {
                    "window_visible": True,
                    "new_task_navigation": True,
                    "composer_editable": True,
                    "task_files_navigation_available": True,
                    "skills_navigation_available": True,
                },
            )

        incomplete = subprocess.CompletedProcess(
            ["swift", str(probe), "101"],
            0,
            stdout=json.dumps({"window_visible": True}),
            stderr="",
        )
        with patch.object(verifier.subprocess, "run", return_value=incomplete):
            with self.assertRaisesRegex(AssertionError, "installed task UI proof"):
                verifier.verify_installed_task_ui(101)

    def test_verification_payload_records_successful_packaged_heor_tests(self) -> None:
        source = (
            ROOT / "scripts/release/verify_macos_package.py"
        ).read_text(encoding="utf-8")
        self.assertIn('"packaged_heor_tests": True', source)

    def test_installed_task_reply_records_cleanup_proof(self) -> None:
        source = (
            ROOT / "scripts/release/verify_macos_package.py"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '"cleanup_verified": reply_launch.get("cleanup_verified") is True',
            source,
        )

    def test_installed_task_reply_uses_the_semantic_ui_and_local_fixture(self) -> None:
        probe = ROOT / "scripts/release/verify_macos_accessibility.swift"
        source = probe.read_text(encoding="utf-8")
        session_zh = json.loads(
            (ROOT / "apps/desktop/src/i18n/locales/zh-Hans/session.json").read_text(
                encoding="utf-8"
            )
        )
        session_en = json.loads(
            (ROOT / "apps/desktop/src/i18n/locales/en/session.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn(session_zh["composer"]["send"]["aria"], source)
        self.assertIn(session_en["composer"]["send"]["aria"], source)
        self.assertIn("assistant_reply_visible", source)
        self.assertIn("prepare_installed_task_reply_runtime", dir(verifier))
        self.assertIn("local_installed_task_reply_fixture", dir(verifier))

        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            verifier.prepare_installed_task_reply_runtime(
                home,
                "com.ai4s.ai4heor",
                "http://127.0.0.1:43210/anthropic/v1",
                "fixture-provider",
                "fixture-model",
                "fixture-credential",
            )
            runtime = (
                home
                / "Library/Application Support/com.ai4s.ai4heor/runtime"
            )
            config = runtime / "xdg-config/opencode/opencode.json"
            auth = runtime / "xdg-data/opencode/auth.json"
            self.assertEqual(stat.S_IMODE(config.stat().st_mode), 0o600)
            self.assertEqual(stat.S_IMODE(auth.stat().st_mode), 0o600)
            self.assertEqual(
                json.loads(config.read_text(encoding="utf-8"))["model"],
                "fixture-provider/fixture-model",
            )
            self.assertEqual(
                json.loads(auth.read_text(encoding="utf-8"))["fixture-provider"]["key"],
                "fixture-credential",
            )

        complete = subprocess.CompletedProcess(
            ["swift", str(probe), "101", "prompt", "marker"],
            0,
            stdout=json.dumps(
                {
                    "new_task_conversation_created": True,
                    "prompt_submitted": True,
                    "assistant_reply_visible": True,
                }
            ),
            stderr="",
        )
        with patch.object(verifier.subprocess, "run", return_value=complete):
            self.assertEqual(
                verifier.verify_installed_task_reply(101, "prompt", "marker"),
                {
                    "new_task_conversation_created": True,
                    "prompt_submitted": True,
                    "assistant_reply_visible": True,
                },
            )

    def test_foreign_architecture_sidecars_are_hash_checked_without_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            app_bin = root / "AI4HEOR.app/Contents/MacOS"
            source_bin = root / "apps/desktop/src-tauri/binaries"
            app_bin.mkdir(parents=True)
            source_bin.mkdir(parents=True)
            for name, payload in (
                ("ai4s-workbench", b"main-arm64"),
                ("opencode", b"opencode-arm64"),
                ("uv", b"uv-arm64"),
            ):
                path = app_bin / name
                path.write_bytes(payload)
                path.chmod(0o755)
            for name in ("opencode", "uv"):
                source = source_bin / f"{name}-aarch64-apple-darwin"
                source.write_bytes((app_bin / name).read_bytes())
                source.chmod(0o755)

            def lipo_only(command: list[str], **_: object):
                self.assertEqual(command[:2], ["lipo", "-archs"])
                return subprocess.CompletedProcess(
                    command, 0, stdout="arm64\n", stderr=""
                )

            with patch.object(verifier, "run", side_effect=lipo_only), patch.object(
                verifier.platform, "machine", return_value="x86_64"
            ):
                versions = verifier.verify_binaries(
                    root / "AI4HEOR.app",
                    "arm64",
                    "aarch64-apple-darwin",
                    root,
                )
            self.assertEqual(versions["opencode"], "1.17.13-ai4heor.2")
            self.assertEqual(versions["uv"], "0.11.26")
            self.assertEqual(
                versions["verification"],
                "static_sha256_against_reviewed_target_sidecars",
            )

    def test_existing_single_instance_socket_is_restored_around_verification(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "com_ai4s_workbench_si.sock"
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(str(path))
            listener.listen(1)
            try:
                with verifier.isolate_single_instance_socket(path) as isolated:
                    self.assertTrue(isolated)
                    self.assertFalse(path.exists())
                    candidate = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    try:
                        candidate.bind(str(path))
                    finally:
                        candidate.close()
                self.assertTrue(path.exists())
                client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                try:
                    client.connect(str(path))
                finally:
                    client.close()
            finally:
                listener.close()

    def test_unexpected_single_instance_file_does_not_prevent_socket_restore(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "com_ai4s_workbench_si.sock"
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(str(path))
            try:
                with self.assertRaisesRegex(AssertionError, "unexpected non-socket"):
                    with verifier.isolate_single_instance_socket(path):
                        path.write_text("preserve for audit", encoding="utf-8")
                self.assertTrue(path.exists())
                self.assertTrue(stat.S_ISSOCK(path.lstat().st_mode))
                preserved = list(Path(temporary).glob("*.unexpected"))
                self.assertEqual(len(preserved), 1)
                self.assertEqual(
                    preserved[0].read_text(encoding="utf-8"), "preserve for audit"
                )
            finally:
                listener.close()

    def test_first_launch_classifier_requires_exact_packaged_processes(self) -> None:
        main = Path("/tmp/install/AI4HEOR.app/Contents/MacOS/ai4s-workbench")
        opencode = Path("/tmp/install/AI4HEOR.app/Contents/MacOS/opencode")
        rows = verifier.parse_process_table(
            """
              101 1 /tmp/install/AI4HEOR.app/Contents/MacOS/ai4s-workbench
              102 101 /tmp/install/AI4HEOR.app/Contents/MacOS/opencode serve --port 43123
              201 1 /Applications/AI4HEOR.app/Contents/MacOS/ai4s-workbench
              202 201 /Applications/AI4HEOR.app/Contents/MacOS/opencode serve --port 9999
            """
        )
        proof = verifier.classify_first_launch_processes(rows, main, opencode, 101)
        self.assertIsNotNone(proof)
        assert proof is not None
        self.assertEqual(proof["app_process_id"], 101)
        self.assertEqual(proof["opencode_process_id"], 102)
        self.assertEqual(proof["opencode_parent_process_id"], 101)
        self.assertEqual(
            [
                row["pid"]
                for row in verifier.matching_processes(
                    rows, {str(main), str(opencode)}
                )
            ],
            [101, 102],
        )
        self.assertIsNone(
            verifier.classify_first_launch_processes(rows, main, opencode, 999)
        )

    def test_open_code_readiness_requires_authenticated_http_response(self) -> None:
        command = "/tmp/opencode serve --hostname 127.0.0.1 --port 43123"
        self.assertEqual(verifier.opencode_server_port(command), 43123)
        self.assertIsNone(verifier.opencode_server_port("/tmp/opencode serve --port nope"))

        response = MagicMock()
        response.status = 401
        response.read.return_value = b""
        connection = MagicMock()
        connection.getresponse.return_value = response
        with patch("http.client.HTTPConnection", return_value=connection):
            proof = verifier.probe_authenticated_opencode_http(43123)
        self.assertEqual(
            proof,
            {
                "authentication_enforced": True,
                "path": "/global/health",
                "unauthenticated_status": 401,
            },
        )
        connection.request.assert_called_once_with("GET", "/global/health")
        connection.close.assert_called_once()

        response.status = 200
        with patch("http.client.HTTPConnection", return_value=connection):
            self.assertIsNone(verifier.probe_authenticated_opencode_http(43123))

    def test_frontend_bootstrap_requires_app_shell_and_tauri_ipc_log(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "debug.log"
            self.assertIsNone(verifier.frontend_bootstrap_proof(log))

            log.write_text(
                "100 bootstrap: starting bundled runtime\n",
                encoding="utf-8",
            )
            self.assertIsNone(verifier.frontend_bootstrap_proof(log))

            log.write_text(
                "100 bootstrap: starting bundled runtime\n"
                "101 bootstrap: runtime at http://127.0.0.1:43123\n",
                encoding="utf-8",
            )
            self.assertEqual(
                verifier.frontend_bootstrap_proof(log),
                {
                    "app_shell_mounted": True,
                    "javascript_executed": True,
                    "tauri_runtime_command_returned": True,
                },
            )

            log.write_text(
                "100 bootstrap: starting bundled runtime\n"
                "101 bootstrap: runtime at http://127.0.0.1:99999\n",
                encoding="utf-8",
            )
            self.assertIsNone(verifier.frontend_bootstrap_proof(log))

            log.write_text(
                "100 bootstrap: starting bundled runtime\n"
                "101 bootstrap FAILED: unavailable\n",
                encoding="utf-8",
            )
            self.assertIsNone(verifier.frontend_bootstrap_proof(log))

    def test_signature_parser_and_validator_require_distribution_properties(self) -> None:
        details = verifier.parse_codesign_details(SIGNED_DETAILS)
        team, authority = verifier.validate_signature_details(
            details, "AI4HEOR.app", require_runtime=True, require_resources=True
        )
        self.assertEqual(team, "A1B2C3D4E5")
        self.assertEqual(
            authority, "Developer ID Application: AI4HEOR Test (A1B2C3D4E5)"
        )

        adhoc = SIGNED_DETAILS.replace(
            "Signature size=9000", "Signature=adhoc"
        ).replace(
            "Authority=Developer ID Application: AI4HEOR Test (A1B2C3D4E5)\n",
            "",
        )
        with self.assertRaisesRegex(AssertionError, "Developer ID Application"):
            verifier.validate_signature_details(
                verifier.parse_codesign_details(adhoc),
                "AI4HEOR.app",
                require_runtime=True,
                require_resources=True,
            )

    def test_get_task_allow_entitlement_is_rejected(self) -> None:
        payload = (
            b"Executable=test\n"
            + plistlib.dumps({"com.apple.security.get-task-allow": True})
            + b"\nwarning after plist"
        )
        with self.assertRaisesRegex(AssertionError, "get-task-allow"):
            verifier.validate_entitlements(payload, "main")

    def test_complete_app_trust_is_verified_for_every_macho(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            app = Path(temporary) / "AI4HEOR.app"
            executable_root = app / "Contents/MacOS"
            executable_root.mkdir(parents=True)
            for name in ("ai4s-workbench", "opencode", "uv"):
                (executable_root / name).write_bytes(b"binary")

            def completed(command: list[str], **_: object):
                if command[:2] == ["file", "-b"]:
                    return subprocess.CompletedProcess(
                        command, 0, stdout="Mach-O 64-bit executable x86_64\n", stderr=""
                    )
                if command[:2] == ["codesign", "-dv"]:
                    return subprocess.CompletedProcess(
                        command, 0, stdout="", stderr=SIGNED_DETAILS
                    )
                if command[:3] == ["codesign", "-d", "--entitlements"]:
                    return subprocess.CompletedProcess(
                        command, 0, stdout=b"", stderr=b"Executable=test\n"
                    )
                if command[:2] == ["spctl", "--assess"]:
                    return subprocess.CompletedProcess(
                        command,
                        0,
                        stdout="",
                        stderr="accepted\nsource=Notarized Developer ID\n",
                    )
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            with patch.object(verifier, "run", side_effect=completed):
                result = verifier.verify_distribution_trust(app, "A1B2C3D4E5")

            self.assertEqual(result["gatekeeper"], "accepted")
            self.assertEqual(result["hardened_runtime"], True)
            self.assertEqual(result["mach_o_files"], 3)
            self.assertEqual(result["notarization_ticket"], "stapled")
            self.assertEqual(result["team_identifier"], "A1B2C3D4E5")

            with patch.object(verifier, "run", side_effect=completed):
                with self.assertRaisesRegex(AssertionError, "expected Apple team"):
                    verifier.verify_distribution_trust(app, "Z9Y8X7W6V5")

    def test_gatekeeper_output_must_name_notarized_developer_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            app = Path(temporary) / "AI4HEOR.app"
            executable_root = app / "Contents/MacOS"
            executable_root.mkdir(parents=True)
            for name in ("ai4s-workbench", "opencode", "uv"):
                (executable_root / name).write_bytes(b"binary")

            def completed(command: list[str], **_: object):
                if command[:2] == ["file", "-b"]:
                    return subprocess.CompletedProcess(
                        command, 0, stdout="Mach-O 64-bit executable x86_64\n", stderr=""
                    )
                if command[:2] == ["codesign", "-dv"]:
                    return subprocess.CompletedProcess(
                        command, 0, stdout="", stderr=SIGNED_DETAILS
                    )
                if command[:3] == ["codesign", "-d", "--entitlements"]:
                    return subprocess.CompletedProcess(
                        command, 0, stdout=b"", stderr=b"Executable=test\n"
                    )
                if command[:2] == ["spctl", "--assess"]:
                    return subprocess.CompletedProcess(
                        command, 0, stdout="", stderr="accepted\nsource=Developer ID\n"
                    )
                return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

            with patch.object(verifier, "run", side_effect=completed):
                with self.assertRaisesRegex(AssertionError, "Notarized Developer ID"):
                    verifier.verify_distribution_trust(app, "A1B2C3D4E5")


class WorkflowContractTests(unittest.TestCase):
    def test_tag_builds_require_credentials_and_distribution_trust(self) -> None:
        workflow = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
        self.assertIn("check_macos_release_credentials.py", workflow)
        self.assertIn("--require-distribution-trust", workflow)
        self.assertIn("--expected-team-id", workflow)
        self.assertIn("--verify-first-launch", workflow)
        self.assertIn("--check first-launch-process", workflow)
        self.assertIn("--check opencode-authenticated-http", workflow)
        self.assertIn("--check frontend-bootstrap", workflow)
        self.assertIn("--check workspace-created", workflow)
        self.assertIn("--check workspace-isolated", workflow)
        self.assertIn("--check installed-task-ui", workflow)
        self.assertIn("--check installed-task-reply", workflow)
        self.assertIn("APPLE_SIGNING_IDENTITY", workflow)
        self.assertIn("developer-id-signature", workflow)
        self.assertIn("notarization-ticket", workflow)
        self.assertIn("gatekeeper-assessment", workflow)
        self.assertIn("verify_packaged_opencode_fixture.py", workflow)
        fixture_call = workflow.split(
            "python scripts/release/verify_packaged_opencode_fixture.py", 1
        )[1].split("python scripts/release/release_evidence.py record", 1)[0]
        self.assertIn('--verification-json "$verification"', fixture_call)
        self.assertIn("opencode-system-context-audit", workflow)
        self.assertIn("opencode-permission-persistence", workflow)
        self.assertNotIn("tagName:", workflow)
        self.assertIn("gh release create", workflow)
        self.assertIn("--verify-tag", workflow)
        self.assertLess(
            workflow.index("Verify artifacts and assemble one source-bound manifest"),
            workflow.index("gh release create"),
        )
        config = json.loads(
            (ROOT / "apps/desktop/src-tauri/tauri.conf.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIs(config["bundle"]["macOS"]["hardenedRuntime"], True)
        self.assertIs(config["app"]["macOSPrivateApi"], True)
        mac_config = json.loads(
            (ROOT / "apps/desktop/src-tauri/tauri.macos.conf.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertNotIn("macOSPrivateApi", mac_config["app"])

    def test_test_builds_do_not_expose_empty_apple_signing_environment(self) -> None:
        workflow = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
        unsigned = workflow.split(
            "- name: Build the unsigned test app (Tauri)", 1
        )[1].split("- name: Build the signed macOS release app (Tauri)", 1)[0]
        self.assertIn("if: github.ref_type != 'tag'", unsigned)
        self.assertNotIn("APPLE_CERTIFICATE", unsigned)
        self.assertNotIn("APPLE_SIGNING_IDENTITY", unsigned)

    def test_windows_delivery_is_one_verified_nsis_installer(self) -> None:
        workflow = (ROOT / ".github/workflows/build.yml").read_text(encoding="utf-8")
        verifier = (ROOT / "scripts/release/verify-windows-package.ps1").read_text(
            encoding="utf-8"
        )
        self.assertIn("--bundles nsis", workflow)
        self.assertNotIn("*.msi", workflow)
        self.assertNotIn("MsiPath", verifier)
        self.assertIn("--check nsis-installed-payload", verifier)
        self.assertIn("--check workspace-isolated", verifier)
        self.assertIn("--check embedded-local-history", verifier)
        self.assertIn("-EmbeddedLocalHistoryTested", workflow)
        self.assertIn("git_snapshot::tests", workflow)
        self.assertIn("requires_system_git = $false", verifier)
        self.assertIn("no_system_git_tested = $true", verifier)
        self.assertIn("legal/libgit2/COPYING", verifier)
        self.assertIn("--check opencode-authenticated-http", verifier)
        self.assertIn("opencode_http", verifier)
        self.assertIn("frontend_bootstrap", verifier)
        self.assertIn("frontend-bootstrap", verifier)
        self.assertIn("open_science_workspace_preserved", verifier)
        self.assertIn("Packaged AI4HEOR processes were not cleaned up", verifier)
        self.assertIn(
            "$verification.first_launch.cleanup_verified = $true",
            verifier,
        )
        self.assertLess(
            verifier.index("Packaged AI4HEOR processes were not cleaned up"),
            verifier.index("$verification.first_launch.cleanup_verified = $true"),
        )
        self.assertIn("GetValue('DisplayName')", verifier)
        self.assertIn("missing=[$($missing -join ', ')]", verifier)
        self.assertIn("extra=[$($extra -join ', ')]", verifier)
        self.assertNotIn("Where-Object DisplayName", verifier)


if __name__ == "__main__":
    unittest.main()
