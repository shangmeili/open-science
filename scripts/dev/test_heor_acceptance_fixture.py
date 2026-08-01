#!/usr/bin/env python3
"""Regression checks for the complete synthetic HEOR acceptance fixture."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


sys.dont_write_bytecode = True  # never pollute packaged Skill sources during fixture validation


ROOT = Path(__file__).resolve().parents[2]
GENERATOR_PATH = ROOT / "scripts/dev/create_heor_acceptance_fixture.py"


def load(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {relative}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generator = load("create_heor_acceptance_fixture", "scripts/dev/create_heor_acceptance_fixture.py")
input_provenance = load(
    "acceptance_input_provenance",
    "runtime/skills/core/heor-input-provenance/scripts/validate_input_provenance.py",
)
reference_case = load(
    "acceptance_reference_case",
    "runtime/skills/core/heor-reference-case/scripts/validate_reference_case_assessment.py",
)
uncertainty = load(
    "acceptance_uncertainty",
    "runtime/skills/core/heor-uncertainty-analysis/scripts/validate_uncertainty_plan.py",
)
budget_impact = load(
    "acceptance_budget_impact",
    "runtime/skills/core/heor-budget-impact/scripts/validate_budget_impact_plan.py",
)


class AcceptanceFixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self.directory.name) / "fixture"
        self.summary = generator.build(self.workspace)
        self.heor = self.workspace / "heor"

    def tearDown(self) -> None:
        self.directory.cleanup()

    def test_every_review_contract_is_complete(self) -> None:
        plan_path = self.heor / "analysis-plan.json"
        plan = json.loads(plan_path.read_bytes())
        provenance = input_provenance.audit(plan, {}, hashlib.sha256(b"{}").hexdigest())
        self.assertTrue(provenance["complete"], provenance)
        self.assertEqual(provenance["required_inputs"], 14)
        self.assertEqual(provenance["covered_inputs"], 14)

        self.assertEqual(
            reference_case.validate(
                self.heor / "reference-case-assessment.json",
                plan_path,
                generator.PROFILE,
            ),
            [],
        )
        self.assertEqual(
            uncertainty.validate(self.heor / "uncertainty-plan.json", plan_path),
            [],
        )
        self.assertEqual(
            budget_impact.validate(self.heor / "budget-impact-plan.json", plan_path),
            [],
        )

    def test_deterministic_engine_repeats_exactly_and_binds_input_hash(self) -> None:
        plan_path = self.heor / "analysis-plan.json"
        env = {
            **os.environ,
            "PYTHONPATH": str(ROOT / "python/heor_core/src"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
        }
        command = [sys.executable, "-B", "-m", "heor_core", str(plan_path)]
        first = subprocess.run(command, cwd=self.workspace, env=env, check=True, capture_output=True)
        second = subprocess.run(command, cwd=self.workspace, env=env, check=True, capture_output=True)
        self.assertEqual(first.stdout, second.stdout)
        result = json.loads(first.stdout)
        self.assertEqual(
            result["input_sha256"], hashlib.sha256(plan_path.read_bytes()).hexdigest()
        )
        self.assertEqual(result["calculation_classification"], "calculation_only")
        self.assertFalse(result["reference_case"]["compliance_assessed"])

    def test_generator_refuses_to_overwrite_nonempty_workspace(self) -> None:
        with self.assertRaises(FileExistsError):
            generator.build(self.workspace)


if __name__ == "__main__":
    unittest.main()
