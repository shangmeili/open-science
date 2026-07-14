#!/usr/bin/env python3
"""Fail-closed checks for AI4HEOR's reviewed RustSec exceptions."""

from __future__ import annotations

import subprocess
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LOCK_PATH = ROOT / "apps/desktop/src-tauri/Cargo.lock"
MANIFEST_PATH = ROOT / "apps/desktop/src-tauri/Cargo.toml"
AUDIT_PATH = ROOT / ".cargo/audit.toml"
REVIEWED_EXCEPTIONS = {"RUSTSEC-2026-0194", "RUSTSEC-2026-0195"}


def packages_named(name: str) -> list[dict]:
    lock = tomllib.loads(LOCK_PATH.read_text(encoding="utf-8"))
    return [package for package in lock["package"] if package["name"] == name]


def version_tuple(version: str) -> tuple[int, int, int]:
    core = version.split("-", 1)[0]
    major, minor, patch = core.split(".")
    return int(major), int(minor), int(patch)


class RustSecurityPolicyTests(unittest.TestCase):
    def test_pdf_parser_uses_the_rustsec_fixed_lopdf_baseline(self) -> None:
        lopdf = packages_named("lopdf")
        self.assertEqual(len(lopdf), 1)
        self.assertGreaterEqual(version_tuple(lopdf[0]["version"]), (0, 42, 0))
        self.assertTrue(lopdf[0].get("checksum"))

    def test_plist_runtime_path_uses_patched_quick_xml(self) -> None:
        plist = packages_named("plist")
        self.assertEqual(len(plist), 1)
        self.assertGreaterEqual(version_tuple(plist[0]["version"]), (1, 10, 0))
        self.assertIn("quick-xml 0.41.0", plist[0]["dependencies"])

    def test_audit_exceptions_are_exactly_the_reviewed_pair(self) -> None:
        config = tomllib.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        self.assertEqual(set(config["advisories"]["ignore"]), REVIEWED_EXCEPTIONS)
        self.assertFalse(config["database"]["stale"])

    def test_ignored_quick_xml_has_only_wayland_scanner_as_direct_consumer(self) -> None:
        result = subprocess.run(
            [
                "cargo",
                "tree",
                "--manifest-path",
                str(MANIFEST_PATH),
                "--target",
                "all",
                "--edges",
                "normal,build",
                "--invert",
                "quick-xml@0.39.4",
                "--prefix",
                "depth",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        direct_consumers = [
            line for line in result.stdout.splitlines() if line.startswith("1")
        ]
        self.assertEqual(len(direct_consumers), 1)
        self.assertTrue(direct_consumers[0].startswith("1wayland-scanner v0.31.10"))


if __name__ == "__main__":
    unittest.main()
