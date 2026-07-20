#!/usr/bin/env python3
"""Contract tests for the cross-platform Tauri resource preflight gate."""

from __future__ import annotations

import ast
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/release/preflight_resources.mjs"
REAL_CONFIG = ROOT / "apps/desktop/src-tauri/tauri.conf.json"


class ResourcePreflightTests(unittest.TestCase):
    def run_preflight(self, config: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["node", str(SCRIPT), "--config", str(config)],
            check=False,
            capture_output=True,
            text=True,
        )

    def fixture(self, root: Path, resources: dict[str, str]) -> Path:
        config = root / "apps/desktop/src-tauri/tauri.conf.json"
        config.parent.mkdir(parents=True)
        config.write_text(
            json.dumps({"bundle": {"resources": resources}}),
            encoding="utf-8",
        )
        return config

    def test_current_release_resources_pass_before_packaging(self) -> None:
        completed = self.run_preflight(REAL_CONFIG)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertRegex(
            completed.stdout,
            r"Release resource preflight passed: sources=\d+, files=\d+",
        )

    def test_development_python_subprocesses_disable_bytecode_caches(self) -> None:
        failures = []
        for source in sorted((ROOT / "scripts/dev").glob("test_*.py")):
            tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
            for node in ast.walk(tree):
                if not isinstance(node, (ast.List, ast.Tuple)) or not node.elts:
                    continue
                first = node.elts[0]
                if not (
                    isinstance(first, ast.Attribute)
                    and isinstance(first.value, ast.Name)
                    and first.value.id == "sys"
                    and first.attr == "executable"
                ):
                    continue
                second = node.elts[1] if len(node.elts) > 1 else None
                if not isinstance(second, ast.Constant) or second.value != "-B":
                    failures.append(f"{source.relative_to(ROOT)}:{node.lineno}")
        self.assertEqual(failures, [], "Python test subprocesses missing -B")

    def test_generated_python_cache_fails_before_packaging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            resource = root / "runtime/skills"
            cache = resource / "method/scripts/__pycache__"
            cache.mkdir(parents=True)
            (cache / "runner.cpython-312.pyc").write_bytes(b"cache")
            config = self.fixture(
                root,
                {"../../../runtime/skills": "skills-core/"},
            )
            completed = self.run_preflight(config)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("generated cache directory", completed.stderr)

    def test_missing_source_and_destination_collision_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "runtime/first"
            second = root / "runtime/second.txt"
            first.mkdir(parents=True)
            (first / "same.txt").write_text("first", encoding="utf-8")
            second.write_text("second", encoding="utf-8")
            config = self.fixture(
                root,
                {
                    "../../../runtime/first": "data/",
                    "../../../runtime/second.txt": "data/same.txt",
                    "../../../runtime/missing": "missing/",
                },
            )
            completed = self.run_preflight(config)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("configured resource does not exist", completed.stderr)
            self.assertIn("resource destination collision", completed.stderr)

    @unittest.skipIf(os.name == "nt", "ordinary Windows users may not create symlinks")
    def test_symbolic_link_fails_before_packaging(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            resource = root / "runtime/resource"
            resource.mkdir(parents=True)
            target = resource / "target.txt"
            target.write_text("target", encoding="utf-8")
            (resource / "alias.txt").symlink_to(target)
            config = self.fixture(
                root,
                {"../../../runtime/resource": "data/"},
            )
            completed = self.run_preflight(config)
            self.assertEqual(completed.returncode, 1)
            self.assertIn("resource contains a symbolic link", completed.stderr)


if __name__ == "__main__":
    unittest.main()
