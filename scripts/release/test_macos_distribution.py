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
from unittest.mock import patch


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
Identifier=com.ai4s.workbench
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
        self.assertIn("--check workspace-created", workflow)
        self.assertIn("--check workspace-migrated", workflow)
        self.assertIn("APPLE_SIGNING_IDENTITY", workflow)
        self.assertIn("developer-id-signature", workflow)
        self.assertIn("notarization-ticket", workflow)
        self.assertIn("gatekeeper-assessment", workflow)
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
        self.assertIn("GetValue('DisplayName')", verifier)
        self.assertNotIn("Where-Object DisplayName", verifier)


if __name__ == "__main__":
    unittest.main()
