"""Contracts for the bundled model-provider-independent HEOR teaching example."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "examples/heor-cost-effectiveness"
RUNNER = EXAMPLE / "run_analysis.py"
EXPECTED = EXAMPLE / "expected/base-case-result.json"


def run(*arguments: str, cwd: Path = EXAMPLE) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-B", str(cwd / "run_analysis.py"), *arguments],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


class HeorTeachingExampleTests(unittest.TestCase):
    def test_base_case_matches_the_exact_expected_result(self) -> None:
        completed = run("--check", "expected/base-case-result.json")
        self.assertEqual(completed.returncode, 0, completed.stderr)
        result = json.loads(EXPECTED.read_text(encoding="utf-8"))
        self.assertEqual(result["schema"], "ai4heor-teaching-cea-result/v1")
        self.assertEqual(result["scenario"], {"type": "base_case"})
        self.assertIsNone(
            result["incremental_vs_comparator"]["cost_effectiveness_claim"]
        )

    def test_two_runs_are_byte_identical(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai4heor-teaching-output-") as temporary:
            first = Path(temporary) / "first.json"
            second = Path(temporary) / "second.json"
            for output in (first, second):
                completed = run("--output", str(output))
                self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(first.read_bytes(), second.read_bytes())
            self.assertEqual(first.read_bytes(), EXPECTED.read_bytes())

    def test_declared_cost_sensitivity_changes_cost_but_not_qalys(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai4heor-teaching-sensitivity-") as temporary:
            output = Path(temporary) / "low.json"
            completed = run(
                "--intervention-stable-cost",
                "14400",
                "--output",
                str(output),
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            base = json.loads(EXPECTED.read_text(encoding="utf-8"))
            low = json.loads(output.read_text(encoding="utf-8"))
            base_incremental = base["incremental_vs_comparator"]
            low_incremental = low["incremental_vs_comparator"]
            self.assertLess(
                low_incremental["discounted_incremental_cost_per_person"],
                base_incremental["discounted_incremental_cost_per_person"],
            )
            self.assertEqual(
                low_incremental["discounted_incremental_qalys_per_person"],
                base_incremental["discounted_incremental_qalys_per_person"],
            )
            self.assertEqual(low["scenario"]["basis"], "researcher_selected_teaching_scenario")

    def test_changed_source_inputs_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai4heor-teaching-tamper-") as temporary:
            copied = Path(temporary) / "example"
            shutil.copytree(EXAMPLE, copied)
            inputs = copied / "inputs/model-inputs.csv"
            inputs.write_text(
                inputs.read_text(encoding="utf-8").replace(
                    "stable,stable,0.70", "stable,stable,0.71", 1
                ),
                encoding="utf-8",
            )
            completed = run("--output", str(copied / "result.json"), cwd=copied)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("SHA-256 does not match", completed.stderr)

    def test_changed_runner_no_longer_matches_the_expected_result(self) -> None:
        with tempfile.TemporaryDirectory(prefix="ai4heor-teaching-runner-") as temporary:
            copied = Path(temporary) / "example"
            shutil.copytree(EXAMPLE, copied)
            runner = copied / "run_analysis.py"
            runner.write_text(
                runner.read_text(encoding="utf-8") + "\n# changed after installation\n",
                encoding="utf-8",
            )
            completed = run("--check", "expected/base-case-result.json", cwd=copied)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("calculated bytes do not match", completed.stderr)


if __name__ == "__main__":
    unittest.main()
