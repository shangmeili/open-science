#!/usr/bin/env python3
"""Unit tests for hash-bound release evidence."""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).with_name("release_evidence.py")
SPEC = importlib.util.spec_from_file_location("release_evidence", SCRIPT)
assert SPEC and SPEC.loader
release_evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_evidence)


class ReleaseEvidenceTests(unittest.TestCase):
    @staticmethod
    def sidecars() -> list[dict[str, object]]:
        return [
            {"name": "opencode", "path": "opencode", "size": 1, "sha256": "a" * 64, "version_output": "1"},
            {"name": "uv", "path": "uv", "size": 1, "sha256": "b" * 64, "version_output": "1"},
        ]

    @staticmethod
    def runner(platform: str) -> dict[str, str]:
        runner_os = {"macos": "macOS", "windows": "Windows", "linux": "Linux"}[platform]
        return {
            "GITHUB_RUN_ATTEMPT": "1",
            "GITHUB_RUN_ID": "123",
            "GITHUB_WORKFLOW_REF": "ai4heor/build.yml@refs/heads/test",
            "ImageOS": f"test-{platform}",
            "ImageVersion": "1",
            "RUNNER_OS": runner_os,
        }

    def test_resource_inventory_is_stable_and_byte_bound(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_root = root / "apps/desktop/src-tauri"
            resource = root / "runtime/resource"
            config_root.mkdir(parents=True)
            resource.mkdir(parents=True)
            (resource / "alpha.txt").write_text("alpha\n", encoding="utf-8")
            (resource / "nested").mkdir()
            (resource / "nested/beta.txt").write_text("beta\n", encoding="utf-8")
            config = {"bundle": {"resources": {"../../../runtime/resource": "data/"}}}
            (config_root / "tauri.conf.json").write_text(json.dumps(config), encoding="utf-8")

            first = release_evidence.resource_inventory(root)
            second = release_evidence.resource_inventory(root)
            self.assertEqual(first, second)
            self.assertEqual(first["file_count"], 2)

            (resource / "alpha.txt").write_text("changed\n", encoding="utf-8")
            changed = release_evidence.resource_inventory(root)
            self.assertNotEqual(first["aggregate_sha256"], changed["aggregate_sha256"])

    def test_source_identity_requires_clean_tracked_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config = root / "apps/desktop/src-tauri/tauri.conf.json"
            config.parent.mkdir(parents=True)
            config.write_text('{"version":"1.2.3"}\n', encoding="utf-8")
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            subprocess.run(
                ["git", "-C", str(root), "config", "user.email", "test@ai4heor.local"],
                check=True,
            )
            subprocess.run(
                ["git", "-C", str(root), "config", "user.name", "AI4HEOR Test"],
                check=True,
            )
            subprocess.run(["git", "-C", str(root), "add", "."], check=True)
            subprocess.run(["git", "-C", str(root), "commit", "-qm", "fixture"], check=True)
            fixture_commit = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "HEAD"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            with mock.patch.dict(os.environ, {"GITHUB_SHA": fixture_commit}):
                commit, version = release_evidence.source_identity(root)
                self.assertEqual(len(commit), 40)
                self.assertEqual(version, "1.2.3")

                config.write_text('{"version":"9.9.9"}\n', encoding="utf-8")
                with self.assertRaisesRegex(AssertionError, "tracked source is dirty"):
                    release_evidence.source_identity(root)

    def test_resource_inventory_rejects_links_and_caches(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_root = root / "apps/desktop/src-tauri"
            resource = root / "runtime/resource"
            config_root.mkdir(parents=True)
            resource.mkdir(parents=True)
            (resource / "module.pyc").write_bytes(b"cache")
            config = {"bundle": {"resources": {"../../../runtime/resource": "data/"}}}
            (config_root / "tauri.conf.json").write_text(json.dumps(config), encoding="utf-8")
            with self.assertRaisesRegex(AssertionError, "Python cache"):
                release_evidence.resource_inventory(root)

    def test_validation_detects_changed_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            artifact = root / "AI4HEOR.msi"
            artifact.write_bytes(b"original")
            files: list[dict[str, object]] = []
            value = {
                "schema": release_evidence.EVIDENCE_SCHEMA,
                "source": {"commit": "a" * 40, "version": "0.1.0"},
                "platform": "windows",
                "target": "x86_64-pc-windows-msvc",
                "artifacts": [release_evidence.artifact_record("msi", artifact)],
                "checks": ["msi-payload"],
                "runner": self.runner("windows"),
                "sidecars": self.sidecars(),
                "verification": {"payload": "passed"},
                "resources": {
                    "aggregate_sha256": release_evidence.canonical_sha256(files),
                    "file_count": 0,
                    "files": files,
                    "total_bytes": 0,
                },
            }
            release_evidence.validate_evidence(value, root)
            artifact.write_bytes(b"tampered")
            with self.assertRaisesRegex(AssertionError, "bytes changed"):
                release_evidence.validate_evidence(value, root)

    def test_macos_verification_bundle_must_match_the_recorded_dmg(self) -> None:
        files: list[dict[str, object]] = []
        artifact = {
            "kind": "dmg",
            "filename": "AI4HEOR_1.0.0_x64.dmg",
            "size": 1,
            "sha256": "a" * 64,
        }
        value = {
            "schema": release_evidence.EVIDENCE_SCHEMA,
            "source": {"commit": "a" * 40, "version": "1.0.0"},
            "platform": "macos",
            "target": "x86_64-apple-darwin",
            "artifacts": [artifact],
            "checks": ["dmg-app-copy"],
            "runner": self.runner("macos"),
            "sidecars": self.sidecars(),
            "verification": {
                "bundle": {
                    "dmg_sha256": "a" * 64,
                    "filename": artifact["filename"],
                    "target": "x86_64-apple-darwin",
                }
            },
            "resources": {
                "aggregate_sha256": release_evidence.canonical_sha256(files),
                "file_count": 0,
                "files": files,
                "total_bytes": 0,
            },
        }
        release_evidence.validate_evidence(value)
        value["verification"]["bundle"]["dmg_sha256"] = "b" * 64
        with self.assertRaisesRegex(AssertionError, "DMG binding"):
            release_evidence.validate_evidence(value)

    def test_macos_core_package_checks_require_exact_verifier_proof(self) -> None:
        files: list[dict[str, object]] = []
        value = {
            "schema": release_evidence.EVIDENCE_SCHEMA,
            "source": {"commit": "a" * 40, "version": "1.0.0"},
            "platform": "macos",
            "target": "x86_64-apple-darwin",
            "artifacts": [
                {
                    "kind": "dmg",
                    "filename": "AI4HEOR_1.0.0_x64.dmg",
                    "size": 1,
                    "sha256": "a" * 64,
                }
            ],
            "checks": sorted(release_evidence.MACOS_CORE_PACKAGE_CHECKS),
            "runner": self.runner("macos"),
            "sidecars": self.sidecars(),
            "verification": {"payload": "passed"},
            "resources": {
                "aggregate_sha256": release_evidence.canonical_sha256(files),
                "file_count": 0,
                "files": files,
                "total_bytes": 0,
            },
        }
        with self.assertRaisesRegex(AssertionError, "core package proof"):
            release_evidence.validate_evidence(value)

        value["sidecars"][0]["version_output"] = "1.17.13-ai4heor.2"
        value["sidecars"][1]["version_output"] = "uv 0.11.26"
        value["verification"] = {
            "info_plist": {
                "CFBundleDisplayName": "AI4HEOR",
                "CFBundleExecutable": "ai4s-workbench",
                "CFBundleIdentifier": "com.ai4s.ai4heor",
                "CFBundleShortVersionString": "1.0.0",
                "CFBundleVersion": "1.0.0",
            },
            "payload": {
                "architecture": "x86_64",
                "opencode_version": "1.17.13-ai4heor.2",
                "resource_files": 0,
                "sidecar_version_verification": "executed_on_matching_architecture",
                "uv_version": "uv 0.11.26",
                "packaged_heor_tests": True,
            },
        }
        release_evidence.validate_evidence(value)
        value["verification"]["payload"]["resource_files"] = 1
        with self.assertRaisesRegex(AssertionError, "core package proof"):
            release_evidence.validate_evidence(value)

        value["checks"] = ["packaged-heor-tests"]
        with self.assertRaisesRegex(AssertionError, "paired checks"):
            release_evidence.validate_evidence(value)

    def test_validation_rejects_platform_target_mismatch(self) -> None:
        files: list[dict[str, object]] = []
        value = {
            "schema": release_evidence.EVIDENCE_SCHEMA,
            "source": {"commit": "a" * 40, "version": "0.1.0"},
            "platform": "windows",
            "target": "x86_64-apple-darwin",
            "artifacts": [
                {"kind": "msi", "filename": "AI4HEOR.msi", "size": 1, "sha256": "a" * 64}
            ],
            "checks": ["payload"],
            "sidecars": self.sidecars(),
            "verification": {"payload": "passed"},
            "resources": {
                "aggregate_sha256": release_evidence.canonical_sha256(files),
                "file_count": 0,
                "files": files,
                "total_bytes": 0,
            },
        }
        with self.assertRaisesRegex(AssertionError, "platform/target"):
            release_evidence.validate_evidence(value)

    def test_first_launch_checks_require_process_and_workspace_proof(self) -> None:
        self.assertEqual(
            release_evidence.FIRST_LAUNCH_CHECKS,
            {
                "first-launch-process",
                "frontend-bootstrap",
                "opencode-authenticated-http",
                "workspace-created",
            },
        )
        files: list[dict[str, object]] = []
        value = {
            "schema": release_evidence.EVIDENCE_SCHEMA,
            "source": {"commit": "a" * 40, "version": "0.1.0"},
            "platform": "macos",
            "target": "x86_64-apple-darwin",
            "artifacts": [
                {"kind": "dmg", "filename": "AI4HEOR.dmg", "size": 1, "sha256": "a" * 64}
            ],
            "checks": [
                "first-launch-process",
                "frontend-bootstrap",
                "opencode-authenticated-http",
                "workspace-created",
            ],
            "runner": self.runner("macos"),
            "sidecars": self.sidecars(),
            "verification": {"payload": "passed"},
            "resources": {
                "aggregate_sha256": release_evidence.canonical_sha256(files),
                "file_count": 0,
                "files": files,
                "total_bytes": 0,
            },
        }
        with self.assertRaisesRegex(AssertionError, "proof is incomplete"):
            release_evidence.validate_evidence(value)

        value["verification"]["first_launch"] = {
            "app_process_id": 101,
            "app_executable": "/tmp/AI4HEOR.app/Contents/MacOS/ai4s-workbench",
            "opencode_process_id": 102,
            "opencode_executable": "/tmp/AI4HEOR.app/Contents/MacOS/opencode",
            "opencode_http": {
                "authentication_enforced": True,
                "path": "/global/health",
                "unauthenticated_status": 401,
            },
            "frontend_bootstrap": {
                "app_shell_mounted": True,
                "javascript_executed": True,
                "tauri_runtime_command_returned": True,
            },
            "workspace": "/tmp/home/Documents/AI4HEOR",
        }
        release_evidence.validate_evidence(value)

        value["verification"]["first_launch"]["frontend_bootstrap"][
            "javascript_executed"
        ] = False
        with self.assertRaisesRegex(AssertionError, "proof is incomplete"):
            release_evidence.validate_evidence(value)
        value["verification"]["first_launch"]["frontend_bootstrap"][
            "javascript_executed"
        ] = True
        value["verification"]["first_launch"]["frontend_bootstrap"][
            "raw_log"
        ] = "must not be recorded"
        with self.assertRaisesRegex(AssertionError, "proof is incomplete"):
            release_evidence.validate_evidence(value)
        del value["verification"]["first_launch"]["frontend_bootstrap"]["raw_log"]

        value["checks"] = sorted([*value["checks"], "installed-task-ui"])
        with self.assertRaisesRegex(AssertionError, "installed task UI proof"):
            release_evidence.validate_evidence(value)
        value["verification"]["first_launch"]["installed_task_ui"] = {
            "window_visible": True,
            "new_task_navigation": True,
            "composer_editable": True,
            "task_files_navigation_available": True,
            "skills_navigation_available": True,
        }
        release_evidence.validate_evidence(value)

        value["checks"] = sorted([*value["checks"], "installed-task-reply"])
        with self.assertRaisesRegex(AssertionError, "installed task reply proof"):
            release_evidence.validate_evidence(value)
        value["verification"]["first_launch"]["installed_task_reply"] = {
            "new_task_conversation_created": True,
            "prompt_submitted": True,
            "provider_request_received": True,
            "assistant_reply_visible": True,
        }
        release_evidence.validate_evidence(value)

        value["checks"] = sorted(
            [
                *value["checks"],
                "opencode-system-context-audit",
                "opencode-permission-persistence",
            ]
        )
        with self.assertRaisesRegex(AssertionError, "packaged OpenCode proof"):
            release_evidence.validate_evidence(value)
        value["verification"]["packaged_opencode_fixture"] = {
            "assistant_reply_completed": True,
            "provider_streaming": True,
            "system_context": {
                "contract": "ai4heor.system-context/v1",
                "fingerprint_matched_provider_request": True,
            },
            "permission_persistence": {
                "exact_project_rule": True,
                "restart_reused": True,
                "revoked": True,
                "reprompted_after_revoke": True,
            },
        }
        release_evidence.validate_evidence(value)

        value["checks"] = sorted([*value["checks"], "workspace-isolated"])
        with self.assertRaisesRegex(AssertionError, "isolation proof is incomplete"):
            release_evidence.validate_evidence(value)
        value["verification"]["first_launch"]["workspace_isolation"] = {
            "app_process_id": 201,
            "opencode_process_id": 202,
            "workspace": "/tmp/coexistence-home/Documents/AI4HEOR",
            "open_science_workspace": "/tmp/coexistence-home/Documents/OpenScience",
            "open_science_workspace_preserved": True,
            "marker_preserved": "2026-07-17-open-science/marker.txt",
            "cleanup_verified": True,
        }
        release_evidence.validate_evidence(value)

        windows = json.loads(json.dumps(value))
        windows["platform"] = "windows"
        windows["target"] = "x86_64-pc-windows-msvc"
        windows["runner"] = self.runner("windows")
        windows["checks"].remove("installed-task-ui")
        del windows["verification"]["first_launch"]["installed_task_ui"]
        windows["checks"].remove("installed-task-reply")
        del windows["verification"]["first_launch"]["installed_task_reply"]
        windows["checks"].remove("opencode-system-context-audit")
        windows["checks"].remove("opencode-permission-persistence")
        del windows["verification"]["packaged_opencode_fixture"]
        windows["artifacts"] = [
            {"kind": "nsis", "filename": "AI4HEOR_1.0.0_x64-setup.exe", "size": 1, "sha256": "a" * 64}
        ]
        windows["verification"]["first_launch"]["workspace"] = r"C:\Users\test\Documents\AI4HEOR"
        windows["verification"]["first_launch"]["workspace_isolation"].update(
            {
                "workspace": r"C:\Users\test\Documents\AI4HEOR",
                "open_science_workspace": r"C:\Users\test\Documents\OpenScience",
            }
        )
        release_evidence.validate_evidence(windows)

        value["checks"] = ["first-launch-process"]
        with self.assertRaisesRegex(AssertionError, "paired checks"):
            release_evidence.validate_evidence(value)

        value["checks"] = ["installed-task-ui"]
        with self.assertRaisesRegex(AssertionError, "paired first-launch checks"):
            release_evidence.validate_evidence(value)

        value["checks"] = ["installed-task-reply"]
        with self.assertRaisesRegex(AssertionError, "missing paired checks"):
            release_evidence.validate_evidence(value)

        value["checks"] = ["opencode-system-context-audit"]
        with self.assertRaisesRegex(AssertionError, "missing paired checks"):
            release_evidence.validate_evidence(value)

    def test_tagged_macos_evidence_requires_distribution_trust(self) -> None:
        files: list[dict[str, object]] = []
        value = {
            "schema": release_evidence.EVIDENCE_SCHEMA,
            "source": {"commit": "a" * 40, "version": "0.1.0"},
            "platform": "macos",
            "target": "aarch64-apple-darwin",
            "artifacts": [
                {"kind": "dmg", "filename": "AI4HEOR.dmg", "size": 1, "sha256": "a" * 64}
            ],
            "checks": sorted(release_evidence.MACOS_CORE_PACKAGE_CHECKS),
            "runner": dict(self.runner("macos"), GITHUB_REF_TYPE="tag"),
            "sidecars": self.sidecars(),
            "verification": {
                "info_plist": {
                    "CFBundleDisplayName": "AI4HEOR",
                    "CFBundleExecutable": "ai4s-workbench",
                    "CFBundleIdentifier": "com.ai4s.ai4heor",
                    "CFBundleShortVersionString": "0.1.0",
                    "CFBundleVersion": "0.1.0",
                },
                "payload": {
                    "architecture": "arm64",
                    "opencode_version": "1",
                    "resource_files": 0,
                    "sidecar_version_verification": "executed_on_matching_architecture",
                    "uv_version": "1",
                    "packaged_heor_tests": True,
                },
            },
            "resources": {
                "aggregate_sha256": release_evidence.canonical_sha256(files),
                "file_count": 0,
                "files": files,
                "total_bytes": 0,
            },
        }
        with self.assertRaisesRegex(AssertionError, "missing trust checks"):
            release_evidence.validate_evidence(value)

        value["checks"] = sorted(
            {*release_evidence.MACOS_CORE_PACKAGE_CHECKS, *release_evidence.MACOS_DISTRIBUTION_CHECKS}
        )
        value["verification"]["distribution"] = {
            "developer_id": "Developer ID Application: Test (A1B2C3D4E5)",
            "gatekeeper": "accepted",
            "hardened_runtime": True,
            "mach_o_files": 3,
            "notarization_ticket": "stapled",
            "sealed_resources": True,
            "secure_timestamp": True,
            "team_identifier": "A1B2C3D4E5",
        }
        release_evidence.validate_evidence(value)

        value["verification"]["distribution"]["secure_timestamp"] = False
        with self.assertRaisesRegex(AssertionError, "incomplete"):
            release_evidence.validate_evidence(value)

        value["verification"]["distribution"]["secure_timestamp"] = True
        value["verification"]["distribution"]["developer_id"] = (
            "Developer ID Application: Other (Z9Y8X7W6V5)"
        )
        with self.assertRaisesRegex(AssertionError, "does not match"):
            release_evidence.validate_evidence(value)

    def test_manifest_rejects_mixed_source(self) -> None:
        base = {
            "schema": release_evidence.EVIDENCE_SCHEMA,
            "artifacts": [{"kind": "package", "filename": "a", "size": 1, "sha256": "a" * 64}],
            "checks": ["payload"],
            "sidecars": self.sidecars(),
            "verification": {"payload": "passed"},
            "resources": {
                "aggregate_sha256": release_evidence.canonical_sha256([]),
                "file_count": 0,
                "files": [],
                "total_bytes": 0,
            },
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            values = []
            inputs = (
                ("windows", "x86_64-pc-windows-msvc", "a" * 40),
                ("linux", "x86_64-unknown-linux-gnu", "b" * 40),
            )
            for platform, target, commit in inputs:
                value = dict(
                    base,
                    platform=platform,
                    runner=self.runner(platform),
                    target=target,
                    source={"commit": commit, "version": "1"},
                )
                path = root / f"{platform}.json"
                release_evidence.write_json(path, value)
                values.append(path)
            arguments = type(
                "Arguments",
                (),
                {
                    "evidence": values,
                    "require_platform": [],
                    "require_target": [],
                    "artifact_root": None,
                    "output": root / "manifest.json",
                },
            )()
            with self.assertRaisesRegex(AssertionError, "one source"):
                release_evidence.assemble(arguments)

    def test_manifest_accepts_consistent_platform_evidence(self) -> None:
        files: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = []
            inputs = (
                ("macos", "aarch64-apple-darwin"),
                ("macos", "x86_64-apple-darwin"),
                ("windows", "x86_64-pc-windows-msvc"),
                ("linux", "x86_64-unknown-linux-gnu"),
            )
            for platform, target in inputs:
                filename = f"{target}.pkg"
                (root / filename).write_bytes(b"a")
                value = {
                    "schema": release_evidence.EVIDENCE_SCHEMA,
                    "source": {"commit": "a" * 40, "version": "1"},
                    "platform": platform,
                    "target": target,
                    "artifacts": [
                        {"kind": "package", "filename": filename, "size": 1, "sha256": "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb"}
                    ],
                    "checks": ["payload"],
                    "runner": self.runner(platform),
                    "sidecars": self.sidecars(),
                    "verification": {"payload": "passed"},
                    "resources": {
                        "aggregate_sha256": release_evidence.canonical_sha256(files),
                        "file_count": 0,
                        "files": files,
                        "total_bytes": 0,
                    },
                }
                path = root / f"{target}.json"
                release_evidence.write_json(path, value)
                paths.append(path)
            output = root / "manifest.json"
            arguments = type(
                "Arguments",
                (),
                {
                    "evidence": paths,
                    "require_platform": ["macos", "windows", "linux"],
                    "require_target": [target for _, target in inputs],
                    "artifact_root": root,
                    "output": output,
                },
            )()
            release_evidence.assemble(arguments)
            manifest = release_evidence.read_json(output)
            self.assertEqual(manifest["schema"], release_evidence.MANIFEST_SCHEMA)
            self.assertEqual(
                [item["target"] for item in manifest["evidence"]],
                sorted(target for _, target in inputs),
            )
            self.assertTrue(all(item["artifacts"] for item in manifest["evidence"]))

            (root / "x86_64-unknown-linux-gnu.pkg").write_bytes(b"changed")
            with self.assertRaisesRegex(AssertionError, "downloaded artifact bytes changed"):
                release_evidence.assemble(arguments)

            (root / "x86_64-unknown-linux-gnu.pkg").write_bytes(b"a")
            changed_run = release_evidence.read_json(paths[0])
            changed_run["runner"]["GITHUB_RUN_ID"] = "different"
            release_evidence.write_json(paths[0], changed_run)
            with self.assertRaisesRegex(AssertionError, "one complete workflow run"):
                release_evidence.assemble(arguments)

    def test_manifest_allows_only_declared_platform_variant_resources(self) -> None:
        stable = {
            "destination": "knowledge-base/stable.md",
            "source": "runtime/knowledge-base/stable.md",
            "size": 6,
            "sha256": "a" * 64,
        }
        generated = {
            "destination": "goal-plugin/goal-plugin.server.js",
            "source": "runtime/goal-plugin/goal-plugin.server.js",
            "size": 10,
            "sha256": "b" * 64,
        }
        base = [stable, generated]
        values = []
        for platform in ("macos", "windows"):
            files = json.loads(json.dumps(base))
            if platform == "windows":
                files[1].update(size=11, sha256="c" * 64)
            values.append(
                {
                    "resources": {
                        "aggregate_sha256": release_evidence.canonical_sha256(files),
                        "files": files,
                    }
                }
            )
        digest = release_evidence.cross_platform_resource_digest(values)
        self.assertRegex(digest, r"^[0-9a-f]{64}$")

        values[1]["resources"]["files"][0]["sha256"] = "d" * 64
        with self.assertRaisesRegex(AssertionError, "undeclared platform-variant"):
            release_evidence.cross_platform_resource_digest(values)


if __name__ == "__main__":
    unittest.main()
