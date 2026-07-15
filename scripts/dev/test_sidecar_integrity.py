#!/usr/bin/env python3
"""Fail closed when a bundled sidecar archive is unpinned or changed."""

from __future__ import annotations

import hashlib
import re
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CHECKSUMS = ROOT / "scripts/dev/sidecar-checksums.sha256"
VERIFY = ROOT / "scripts/dev/verify-sidecar-checksum.sh"


def manifest() -> dict[str, str]:
    entries: dict[str, str] = {}
    for raw in CHECKSUMS.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        digest, key = line.split()
        if key in entries:
            raise AssertionError(f"duplicate checksum key: {key}")
        entries[key] = digest
    return entries


class SidecarIntegrityTests(unittest.TestCase):
    def test_every_supported_archive_has_one_pinned_digest(self) -> None:
        entries = manifest()
        expected = {
            "opencode/1.17.13/opencode-darwin-arm64.zip",
            "opencode/1.17.13/opencode-darwin-x64.zip",
            "opencode/1.17.13/opencode-linux-arm64.tar.gz",
            "opencode/1.17.13/opencode-linux-x64.tar.gz",
            "opencode/1.17.13/opencode-windows-arm64.zip",
            "opencode/1.17.13/opencode-windows-x64.zip",
            "uv/0.11.26/uv-aarch64-apple-darwin.tar.gz",
            "uv/0.11.26/uv-x86_64-apple-darwin.tar.gz",
            "uv/0.11.26/uv-aarch64-pc-windows-msvc.zip",
            "uv/0.11.26/uv-x86_64-pc-windows-msvc.zip",
            "uv/0.11.26/uv-aarch64-unknown-linux-gnu.tar.gz",
            "uv/0.11.26/uv-x86_64-unknown-linux-gnu.tar.gz",
        }
        self.assertEqual(set(entries), expected)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{64}", value) for value in entries.values()))

    def test_verifier_accepts_exact_bytes_and_rejects_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "fixture.bin"
            archive.write_bytes(b"ai4heor sidecar verifier fixture\n")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            checksums = root / "checksums.sha256"
            checksums.write_text(f"{digest}  test/1.0/fixture.bin\n", encoding="utf-8")
            command = [
                "bash",
                str(VERIFY),
                str(archive),
                "test",
                "1.0",
                "fixture.bin",
                str(checksums),
            ]
            accepted = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(accepted.returncode, 0, accepted.stderr)
            archive.write_bytes(b"changed\n")
            rejected = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("SHA-256 mismatch", rejected.stderr)

    def test_missing_or_duplicate_pin_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            archive = root / "fixture.bin"
            archive.write_bytes(b"fixture")
            digest = hashlib.sha256(archive.read_bytes()).hexdigest()
            for body in ("", f"{digest}  test/1.0/fixture.bin\n{digest}  test/1.0/fixture.bin\n"):
                checksums = root / "checksums.sha256"
                checksums.write_text(body, encoding="utf-8")
                result = subprocess.run(
                    [
                        "bash",
                        str(VERIFY),
                        str(archive),
                        "test",
                        "1.0",
                        "fixture.bin",
                        str(checksums),
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("No unique pinned SHA-256", result.stderr)


if __name__ == "__main__":
    unittest.main()
