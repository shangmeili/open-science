#!/usr/bin/env python3
"""Keep the seeded AI4HEOR harness researcher-led and non-self-authorizing."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HARNESS_ROOT = ROOT / "runtime" / "harness"
TAURI_CONFIG = ROOT / "apps" / "desktop" / "src-tauri" / "tauri.conf.json"


class HeorHarnessContractTests(unittest.TestCase):
    def test_required_harness_files_are_complete(self):
        expected = {
            ".gitignore",
            "AGENTS.md",
            "KNOWLEDGE.md",
            "README.md",
            "knowledge/current-state.md",
            "knowledge/system.md",
            "notes/.gitkeep",
        }
        actual = {
            path.relative_to(HARNESS_ROOT).as_posix()
            for path in HARNESS_ROOT.rglob("*")
            if path.is_file()
        }
        self.assertEqual(actual, expected)
        for relative in expected - {"notes/.gitkeep"}:
            self.assertTrue((HARNESS_ROOT / relative).read_text(encoding="utf-8").strip())

    def test_runtime_contract_makes_the_researcher_the_scientific_lead(self):
        agents = (HARNESS_ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("The human researcher leads the scientific work", agents)
        self.assertIn("Natural-language conversation is the primary interface", agents)
        self.assertIn(
            "not a final approval appended to an Agent-led research process",
            agents,
        )
        self.assertIn("researcher-selected plan", agents)

    def test_inherited_agent_led_and_self_rewriting_contracts_are_absent(self):
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in sorted(HARNESS_ROOT.rglob("*.md"))
        )
        for forbidden in (
            "single research execution agent",
            "single AI research agent",
            "Complete the current goal.",
            "It delivers work, reviews itself, and revises itself",
            "by editing this file",
            "edit this file directly",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, combined)
        self.assertIn("Do not edit `AGENTS.md`", combined)

    def test_current_state_keeps_scientific_and_execution_roles_distinct(self):
        system = (HARNESS_ROOT / "knowledge/system.md").read_text(encoding="utf-8")
        state = (HARNESS_ROOT / "knowledge/current-state.md").read_text(encoding="utf-8")
        self.assertIn("Scientific lead: human researcher", system)
        self.assertIn("Assistant role: bounded", system)
        self.assertIn("Research lead: human researcher", state)
        self.assertIn("Delegated assistant task: undefined", state)

    def test_exact_harness_tree_is_declared_as_a_packaged_resource(self):
        config = json.loads(TAURI_CONFIG.read_text(encoding="utf-8"))
        resources = config["bundle"]["resources"]
        self.assertEqual(resources.get("../../../runtime/harness"), "harness/")


if __name__ == "__main__":
    unittest.main()
