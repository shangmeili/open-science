#!/usr/bin/env python3
"""Contract tests for the agent-accessible deterministic HEOR runner."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "runtime/skills/core/heor-workbench/scripts/run_first_party_analysis.py"
CORE = ROOT / "python/heor_core/src"
FIXTURE_BUILDER = ROOT / "scripts/dev/create_heor_acceptance_fixture.py"


class FirstPartyRunnerTests(unittest.TestCase):
    def prepare_valid_workspace(self, workspace: Path) -> None:
        completed = subprocess.run(
            [sys.executable, "-B", str(FIXTURE_BUILDER), str(workspace)],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def run_runner(
        self,
        workspace: Path,
        plan: str = "heor/analysis-plan.json",
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["AI4HEOR_HEOR_CORE_PATH"] = str(CORE)
        return subprocess.run(
            [sys.executable, "-B", str(RUNNER), "--plan", plan],
            cwd=workspace,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_valid_plan_writes_hash_bound_base_case_atomically(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            self.prepare_valid_workspace(workspace)
            plan = workspace / "heor/analysis-plan.json"

            completed = self.run_runner(workspace)
            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = json.loads(completed.stdout)
            self.assertEqual(summary["status"], "calculation_only")
            self.assertEqual(summary["result"], "heor/results/base-case.json")

            result = json.loads((workspace / summary["result"]).read_text(encoding="utf-8"))
            self.assertEqual(result["input_sha256"], hashlib.sha256(plan.read_bytes()).hexdigest())
            self.assertEqual(result["engine_version"], summary["engine_version"])

    def test_valid_decision_tree_writes_a_separate_replayable_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            plan = workspace / "heor/decision-tree-plan.json"
            plan.parent.mkdir(parents=True)
            plan.write_bytes(
                (
                    ROOT
                    / "python/heor_core/golden_cases/two_strategy_decision_tree.json"
                ).read_bytes()
            )

            completed = self.run_runner(workspace, "heor/decision-tree-plan.json")
            self.assertEqual(completed.returncode, 0, completed.stderr)
            summary = json.loads(completed.stdout)
            self.assertEqual(summary["status"], "calculation_only")
            self.assertEqual(summary["analysis_type"], "decision_tree")
            self.assertEqual(summary["result"], "heor/results/decision-tree.json")

            result = json.loads(
                (workspace / summary["result"]).read_text(encoding="utf-8")
            )
            self.assertEqual(result["analysis_type"], "decision_tree")
            self.assertEqual(
                result["input_sha256"], hashlib.sha256(plan.read_bytes()).hexdigest()
            )
            self.assertAlmostEqual(
                result["strategies"]["comparator"]["total_cost"], 1800.0
            )
            self.assertAlmostEqual(
                result["strategies"]["intervention"]["total_cost"], 2900.0
            )

    def test_incompatible_provenance_field_does_not_create_a_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            self.prepare_valid_workspace(workspace)
            plan = workspace / "heor/analysis-plan.json"
            payload = json.loads(plan.read_text(encoding="utf-8"))
            payload["input_provenance"][0]["input_path"] = payload["input_provenance"][0].pop("path")
            plan.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

            completed = self.run_runner(workspace)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("legacy input_provenance.input_path contract", completed.stderr)
            self.assertFalse((workspace / "heor/results/base-case.json").exists())

    def test_invalid_plan_does_not_create_a_result(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            plan = workspace / "heor/analysis-plan.json"
            plan.parent.mkdir(parents=True)
            plan.write_text("{}\n", encoding="utf-8")

            completed = self.run_runner(workspace)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("deterministic run failed", completed.stderr)
            self.assertFalse((workspace / "heor/results/base-case.json").exists())


if __name__ == "__main__":
    unittest.main()
