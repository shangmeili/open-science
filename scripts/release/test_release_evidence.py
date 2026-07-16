#!/usr/bin/env python3
"""Unit tests for hash-bound release evidence."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


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
                "sidecars": self.sidecars(),
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

    def test_manifest_rejects_mixed_source(self) -> None:
        base = {
            "schema": release_evidence.EVIDENCE_SCHEMA,
            "target": "x86_64",
            "artifacts": [{"kind": "package", "filename": "a", "size": 1, "sha256": "a" * 64}],
            "checks": ["payload"],
            "sidecars": self.sidecars(),
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
            for platform, commit in (("windows", "a" * 40), ("linux", "b" * 40)):
                value = dict(base, platform=platform, source={"commit": commit, "version": "1"})
                path = root / f"{platform}.json"
                release_evidence.write_json(path, value)
                values.append(path)
            arguments = type(
                "Arguments",
                (),
                {"evidence": values, "require_platform": [], "output": root / "manifest.json"},
            )()
            with self.assertRaisesRegex(AssertionError, "one source"):
                release_evidence.assemble(arguments)

    def test_manifest_accepts_consistent_platform_evidence(self) -> None:
        files: list[dict[str, object]] = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = []
            for platform in ("windows", "linux"):
                value = {
                    "schema": release_evidence.EVIDENCE_SCHEMA,
                    "source": {"commit": "a" * 40, "version": "1"},
                    "platform": platform,
                    "target": "x86_64",
                    "artifacts": [
                        {"kind": "package", "filename": f"{platform}.pkg", "size": 1, "sha256": "a" * 64}
                    ],
                    "checks": ["payload"],
                    "sidecars": self.sidecars(),
                    "resources": {
                        "aggregate_sha256": release_evidence.canonical_sha256(files),
                        "file_count": 0,
                        "files": files,
                        "total_bytes": 0,
                    },
                }
                path = root / f"{platform}.json"
                release_evidence.write_json(path, value)
                paths.append(path)
            output = root / "manifest.json"
            arguments = type(
                "Arguments",
                (),
                {"evidence": paths, "require_platform": ["windows"], "output": output},
            )()
            release_evidence.assemble(arguments)
            manifest = release_evidence.read_json(output)
            self.assertEqual(manifest["schema"], release_evidence.MANIFEST_SCHEMA)
            self.assertEqual([item["platform"] for item in manifest["evidence"]], ["linux", "windows"])


if __name__ == "__main__":
    unittest.main()
