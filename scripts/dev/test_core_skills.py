#!/usr/bin/env python3
"""Fail closed on malformed or placeholder first-party core Skills."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = ROOT / "runtime" / "skills" / "core"
LOCALES_ROOT = ROOT / "apps" / "desktop" / "src" / "i18n" / "locales"
SHIPPED_LOCALES = ("en", "zh-Hans", "ja", "ko", "de", "es", "fr")
NAME_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def parse_frontmatter(path: Path) -> dict[str, str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("SKILL.md must start with YAML frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError("SKILL.md frontmatter is not closed") from error
    values: dict[str, str] = {}
    for line in lines[1:end]:
        if not line.strip() or ":" not in line:
            raise ValueError("frontmatter must use one-line key: value fields")
        key, raw_value = line.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if key in values:
            raise ValueError(f"duplicate frontmatter field: {key}")
        if raw_value.startswith(("'", '"')):
            try:
                value = ast.literal_eval(raw_value)
            except (SyntaxError, ValueError) as error:
                raise ValueError(f"invalid quoted {key}") from error
            if not isinstance(value, str):
                raise ValueError(f"{key} must be a string")
        else:
            value = raw_value
        values[key] = value
    return values


class CoreSkillContractTests(unittest.TestCase):
    def test_every_discoverable_core_skill_is_complete(self):
        skill_paths = sorted(SKILLS_ROOT.glob("*/SKILL.md"))
        self.assertTrue(skill_paths)
        for skill_path in skill_paths:
            skill_dir = skill_path.parent
            with self.subTest(skill=skill_dir.name):
                text = skill_path.read_text(encoding="utf-8")
                self.assertNotRegex(text, r"(?i)\[(?:todo|placeholder)[:\]]")
                fields = parse_frontmatter(skill_path)
                self.assertEqual(set(fields), {"name", "description"})
                self.assertRegex(fields["name"], NAME_PATTERN)
                self.assertEqual(fields["name"], skill_dir.name)
                self.assertLessEqual(len(fields["name"]), 64)
                self.assertGreaterEqual(len(fields["description"].strip()), 25)
                self.assertLessEqual(len(fields["description"]), 1024)
                self.assertNotRegex(fields["description"], r"[<>]")

    def test_markdown_relative_links_resolve_inside_each_skill(self):
        link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
        for skill_path in sorted(SKILLS_ROOT.glob("*/SKILL.md")):
            with self.subTest(skill=skill_path.parent.name):
                for target in link_pattern.findall(skill_path.read_text(encoding="utf-8")):
                    if "://" in target or target.startswith("#"):
                        continue
                    relative = target.split("#", 1)[0]
                    resolved = (skill_path.parent / relative).resolve()
                    self.assertTrue(
                        resolved.is_relative_to(skill_path.parent.resolve()),
                        f"relative link escapes skill directory: {target}",
                    )
                    self.assertTrue(resolved.exists(), f"missing linked resource: {target}")

    def test_every_core_skill_has_complete_shipped_locale_metadata(self):
        skill_names = {path.parent.name for path in SKILLS_ROOT.glob("*/SKILL.md")}
        self.assertTrue(skill_names)
        english: dict[str, dict[str, str]] | None = None
        for locale in SHIPPED_LOCALES:
            with self.subTest(locale=locale):
                path = LOCALES_ROOT / locale / "skills.json"
                payload = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(set(payload), {"catalog"})
                catalog = payload["catalog"]
                # The shipped catalog also contains separately admitted Open
                # Science Skills. This core contract owns the 53 first-party
                # entries; the exact 53+7 union is checked by the foundation
                # and product-documentation contracts.
                self.assertTrue(skill_names.issubset(set(catalog)))
                for name, entry in catalog.items():
                    self.assertEqual(set(entry), {"displayName", "description"})
                    self.assertTrue(entry["displayName"].strip(), name)
                    self.assertGreaterEqual(len(entry["description"].strip()), 12, name)
                if locale == "en":
                    english = catalog
                else:
                    assert english is not None
                    self.assertTrue(
                        any(catalog[name]["description"] != english[name]["description"] for name in skill_names),
                        f"{locale} catalog is an untranslated English copy",
                    )

    def test_heor_workbench_keeps_scientific_leadership_human(self):
        text = (SKILLS_ROOT / "heor-workbench" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("Treat the human researcher as the scientific lead", text)
        self.assertIn("Natural-language conversation is the primary interface", text)
        self.assertIn(
            "not a final approval appended to an Agent-led research process",
            text,
        )
        self.assertIn("researcher-selected plan", text)
        self.assertIn("Preserve the full Open Science baseline", text)
        self.assertIn("do not add a second scientific-approval prompt", text)
        self.assertIn("language of the researcher's latest request", text)
        self.assertIn("reserved machine contract", text)
        self.assertIn("Never invent a schema at that path", text)
        self.assertIn("heor/analysis-plan.md", text)
        self.assertNotIn("Complete the current goal.", text)

    def test_evidence_search_does_not_block_the_open_science_baseline(self):
        text = (SKILLS_ROOT / "heor-evidence-search" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Ordinary public evidence retrieval", text)
        self.assertIn("current task permission mode", text)
        self.assertIn("Do not ask the researcher to find or open a panel", text)
        self.assertNotIn("Ask the researcher to open the AI4HEOR review pane", text)

    def test_capability_growth_skills_use_the_loaded_install_directory(self):
        for name in ("ai4heor-skill-authoring", "ai4heor-preference-learning"):
            with self.subTest(skill=name):
                text = (SKILLS_ROOT / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn("Base directory for this skill", text)
                self.assertIn("<skill-base-directory>/scripts/", text)
                self.assertIn("source checkout", text)
                self.assertNotIn(f"runtime/skills/core/{name}/scripts/", text)

    def test_heor_reporting_owns_a_source_bound_docx_pdf_contract(self):
        skill_dir = SKILLS_ROOT / "heor-reporting"
        skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        contract = (skill_dir / "references" / "report-export-contract.md").read_text(
            encoding="utf-8"
        )
        template = json.loads(
            (skill_dir / "assets" / "report-export.template.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("references/report-export-contract.md", skill)
        self.assertIn("deliverables/heor-report-export.json", skill)
        self.assertEqual(
            set(template),
            {
                "schema_version",
                "document_id",
                "title",
                "subtitle",
                "language",
                "prepared_on",
                "audience",
                "purpose",
                "style",
                "report_package",
                "report_document",
                "human_review",
            },
        )
        self.assertEqual(template["schema_version"], "0.1.0")
        self.assertEqual(template["style"], "ai4heor-formal-report")
        self.assertEqual(template["report_package"]["path"], "heor/report-package.json")
        self.assertEqual(template["report_document"]["path"], "heor/report.md")
        self.assertEqual(
            template["human_review"], {"status": "awaiting_human_review"}
        )
        for required in (
            "deliverables/heor-report.docx",
            "deliverables/heor-report.pdf",
            "deliverables/heor-report.audit.json",
            "source-hash drift",
            "does not establish",
        ):
            self.assertIn(required, contract)

    def test_heor_reporting_has_a_decision_tree_specific_draft_contract(self):
        skill_dir = SKILLS_ROOT / "heor-reporting"
        skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        contract = (skill_dir / "references" / "report-package-contract.md").read_text(
            encoding="utf-8"
        )
        template = json.loads(
            (skill_dir / "assets" / "decision-tree-report-package.template.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(template["schema_version"], "0.3.0")
        self.assertEqual(template["analysis_type"], "decision_tree")
        self.assertEqual(template["status"], "draft")
        self.assertEqual(
            set(template["bindings"]),
            {
                "report_document",
                "evidence_synthesis",
                "decision_tree_plan",
                "decision_tree_uncertainty_plan",
                "decision_tree_result",
                "decision_tree_uncertainty_result",
            },
        )
        self.assertEqual(
            template["reporting_profiles"],
            [{"id": "CHEERS-2022", "status": "current", "scope": "cost_effectiveness"}],
        )

    def test_reproducibility_skill_has_a_decision_tree_specific_contract(self):
        skill_dir = SKILLS_ROOT / "heor-reproducibility-package"
        skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        contract = (skill_dir / "references" / "reproducibility-contract.md").read_text(
            encoding="utf-8"
        )
        template = json.loads(
            (skill_dir / "assets" / "decision-tree-reproducibility-package.template.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(template["schema_version"], "0.2.0")
        self.assertEqual(template["analysis_type"], "decision_tree")
        self.assertEqual(template["status"], "draft")
        self.assertIn("decision-tree-reproducibility-package.template.json", skill)
        self.assertIn("exactly two", contract)
        self.assertIn("exactly three", contract)
        self.assertIn("does not become release-ready", contract)
        self.assertIn("decision-tree-report-package.template.json", skill)
        self.assertIn("must remain `draft`", skill)
        self.assertIn("schema `0.3.0`", contract)
        self.assertIn("proposed assumptions", contract)
        self.assertIn("convergence", contract)

    def test_model_validation_skill_has_a_decision_tree_specific_contract(self):
        skill_dir = SKILLS_ROOT / "heor-model-validation"
        skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        contract = (skill_dir / "references" / "model-validation-contract.md").read_text(
            encoding="utf-8"
        )
        template = json.loads(
            (skill_dir / "assets" / "decision-tree-model-validation.template.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(template["schema_version"], "0.3.0")
        self.assertEqual(template["analysis_type"], "decision_tree")
        self.assertEqual(template["status"], "draft")
        self.assertEqual(
            set(template["model_bindings"]),
            {
                "evidence_synthesis",
                "decision_tree_plan",
                "decision_tree_uncertainty_plan",
                "decision_tree_result",
                "decision_tree_uncertainty_result",
            },
        )
        self.assertIn("decision-tree-model-validation.template.json", skill)
        self.assertIn("schema `0.3.0`", contract)
        self.assertIn("cost-effectiveness only", contract)
        self.assertIn("does not require a budget-impact validation path", contract)

    def test_heor_model_design_owns_a_source_bound_diagram_contract(self):
        skill_dir = SKILLS_ROOT / "heor-model-design"
        skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        contract = (skill_dir / "references" / "diagram-export-contract.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("references/diagram-export-contract.md", skill)
        for required in (
            "deliverables/conceptual-model.svg",
            "deliverables/conceptual-model.graphml",
            "heor/conceptual-model.json",
            "coordinates only",
            "awaiting_human_review",
            "never overwrites",
        ):
            self.assertIn(required, contract)

    def test_decision_tree_skill_has_a_bounded_subgroup_contract(self):
        skill_dir = SKILLS_ROOT / "heor-decision-tree"
        skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        contract = (skill_dir / "references/subgroup-analysis-contract.md").read_text(
            encoding="utf-8"
        )
        template = json.loads(
            (skill_dir / "assets/subgroup-analysis-plan.template.json").read_text(
                encoding="utf-8"
            )
        )
        validator = skill_dir / "scripts/validate_subgroup_analysis.py"
        self.assertEqual(template["schema_version"], "0.1.0")
        self.assertEqual(template["analysis_type"], "decision_tree_subgroup")
        self.assertEqual(template["grouping"]["prespecification"], None)
        self.assertFalse(template["grouping"]["mutually_exclusive"])
        self.assertFalse(template["grouping"]["exhaustive"])
        self.assertTrue(validator.is_file())
        for required in (
            "subgroup-analysis-plan.template.json",
            "validate_subgroup_analysis.py",
            "descriptive",
            "interaction",
            "researcher review",
        ):
            self.assertIn(required, skill)
        for required in (
            "mutually exclusive",
            "sum to one",
            "evidence extraction",
            "multiplicity",
            "does not establish",
        ):
            self.assertIn(required, contract)

    def test_decision_tree_skill_replays_the_first_party_golden_case(self):
        skill_dir = SKILLS_ROOT / "heor-decision-tree"
        skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        workbench = (SKILLS_ROOT / "heor-workbench" / "SKILL.md").read_text(
            encoding="utf-8"
        )
        startup_audit = (
            ROOT / "apps/desktop/src-tauri/src/startup_audit.rs"
        ).read_text(encoding="utf-8")
        contract = (skill_dir / "references" / "decision-tree-contract.md").read_text(
            encoding="utf-8"
        )
        template = json.loads(
            (skill_dir / "assets" / "decision-tree-plan.template.json").read_text(
                encoding="utf-8"
            )
        )
        uncertainty_template = json.loads(
            (skill_dir / "assets" / "decision-tree-uncertainty-plan.template.json").read_text(
                encoding="utf-8"
            )
        )
        validator = skill_dir / "scripts" / "validate_decision_tree.py"
        uncertainty_validator = skill_dir / "scripts" / "validate_decision_tree_uncertainty.py"
        golden = ROOT / "python/heor_core/golden_cases/two_strategy_decision_tree.json"
        self.assertEqual(template["analysis_type"], "decision_tree")
        self.assertEqual(template["schema_version"], "0.2.0")
        self.assertEqual(
            set(template["economic_basis"]),
            {"currency", "price_year", "jurisdiction", "perspective"},
        )
        self.assertEqual(uncertainty_template["analysis_type"], "decision_tree_uncertainty")
        self.assertEqual(
            uncertainty_template["analysis_input"]["path"],
            "heor/decision-tree-plan.json",
        )
        self.assertEqual(
            set(uncertainty_template["probabilistic_analysis"]["convergence"]),
            {"checkpoints", "max_probability_mcse", "max_probability_drift"},
        )
        self.assertTrue(uncertainty_validator.is_file())
        for required in (
            "references/decision-tree-contract.md",
            "../heor-workbench/scripts/run_first_party_analysis.py",
            "heor/decision-tree-plan.json",
            "calculation-only",
            "decision-tree-uncertainty-plan.template.json",
            "100–10,000 iterations",
        ):
            self.assertIn(required, skill)
        for required in (
            "one year",
            "source_ids",
            "assumption_ids",
            "probabilities must sum to one",
            "Human",
        ):
            self.assertIn(required, contract)
        self.assertIn("$heor-decision-tree", workbench)
        self.assertIn('"heor-decision-tree"', startup_audit)
        self.assertIn('"decision_tree.py"', startup_audit)
        self.assertIn('"decision_tree_uncertainty.py"', startup_audit)

        environment = dict(os.environ)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONPATH"] = str(ROOT / "python/heor_core/src")
        checked = subprocess.run(
            [sys.executable, "-B", str(validator), "--plan", str(golden)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=True,
        )
        summary = json.loads(checked.stdout)
        self.assertTrue(summary["valid"])
        self.assertEqual(summary["schema_version"], "0.1.0")
        self.assertEqual(summary["strategy_count"], 2)
        self.assertEqual(summary["analysis_id"], "golden-two-strategy-decision-tree")

        with tempfile.TemporaryDirectory() as directory:
            result = Path(directory) / "result.json"
            executed = subprocess.run(
                [sys.executable, "-B", "-m", "heor_core", str(golden)],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=True,
            )
            result.write_text(executed.stdout, encoding="utf-8")
            verified = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(validator),
                    "--plan",
                    str(golden),
                    "--result",
                    str(result),
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
            )
            self.assertEqual(verified.returncode, 0, verified.stderr)
            payload = json.loads(result.read_text(encoding="utf-8"))
            payload["strategies"]["comparator"]["total_cost"] += 1
            result.write_text(json.dumps(payload), encoding="utf-8")
            rejected = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(validator),
                    "--plan",
                    str(golden),
                    "--result",
                    str(result),
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("does not match deterministic replay", rejected.stderr)

            current_plan = Path(directory) / "decision-tree-plan-0.2.json"
            current_payload = json.loads(golden.read_text(encoding="utf-8"))
            current_payload["schema_version"] = "0.2.0"
            current_payload["economic_basis"] = {
                "currency": "CNY",
                "price_year": 2026,
                "jurisdiction": "中国大陆",
                "perspective": "中国医疗卫生系统",
            }
            current_plan.write_text(
                json.dumps(current_payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8",
            )
            uncertainty_plan = Path(directory) / "decision-tree-uncertainty-plan.json"
            uncertainty_payload = {
                "schema_version": "0.1.0",
                "analysis_type": "decision_tree_uncertainty",
                "uncertainty_id": "validator-replay",
                "analysis_input": {
                    "path": "heor/decision-tree-plan.json",
                    "content_sha256": hashlib.sha256(current_plan.read_bytes()).hexdigest(),
                },
                "parameters": [{
                    "id": "intervention-success-probability",
                    "label": "Intervention success probability",
                    "target": {
                        "kind": "branch_probability",
                        "strategy_id": "intervention",
                        "node_id": "intervention_outcome",
                        "branch_index": 0,
                        "complement_branch_index": 1,
                    },
                    "deterministic": {
                        "low": 0.5,
                        "high": 0.9,
                        "basis_ids": ["teaching-inputs"],
                        "rationale": "Synthetic test range.",
                    },
                    "probabilistic": {
                        "type": "uniform",
                        "low": 0.5,
                        "high": 0.9,
                        "basis_ids": ["teaching-inputs"],
                        "rationale": "Synthetic test distribution.",
                    },
                }],
                "probabilistic_analysis": {
                    "iterations": 100,
                    "seed": 7,
                    "convergence": {
                        "checkpoints": [50, 100],
                        "max_probability_mcse": 0.1,
                        "max_probability_drift": 0.1,
                    },
                    "independence_rationale": "Only one parameter is varied.",
                    "omitted_uncertainties": [{
                        "item": "structure",
                        "rationale": "Not represented by this synthetic test.",
                    }],
                },
            }
            uncertainty_plan.write_text(
                json.dumps(uncertainty_payload, separators=(",", ":")),
                encoding="utf-8",
            )
            uncertainty_result = Path(directory) / "decision-tree-uncertainty-result.json"
            executed_uncertainty = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    "-m",
                    "heor_core",
                    str(current_plan),
                    "--decision-tree-uncertainty-plan",
                    str(uncertainty_plan),
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=True,
            )
            uncertainty_result.write_text(executed_uncertainty.stdout, encoding="utf-8")
            verified_uncertainty = subprocess.run(
                [
                    sys.executable,
                    "-B",
                    str(uncertainty_validator),
                    "--plan",
                    str(current_plan),
                    "--uncertainty-plan",
                    str(uncertainty_plan),
                    "--result",
                    str(uncertainty_result),
                ],
                cwd=ROOT,
                env=environment,
                capture_output=True,
                text=True,
            )
            self.assertEqual(verified_uncertainty.returncode, 0, verified_uncertainty.stderr)
            uncertainty_summary = json.loads(verified_uncertainty.stdout)
            self.assertTrue(uncertainty_summary["result_verified"])
            self.assertEqual(uncertainty_summary["iterations"], 100)
            self.assertIsInstance(uncertainty_summary["convergence_passed"], bool)

    def test_research_tables_owns_typed_source_bound_xlsx_and_csv_contract(self):
        skill_dir = SKILLS_ROOT / "research-tables"
        skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        contract = (skill_dir / "references" / "research-tables-contract.md").read_text(
            encoding="utf-8"
        )
        template = json.loads(
            (skill_dir / "assets" / "research-tables.template.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn("references/research-tables-contract.md", skill)
        self.assertIn("deliverables/research-tables.json", skill)
        self.assertEqual(template["schema_version"], "ai4heor-research-tables/v1")
        self.assertEqual(
            template["human_review"], {"status": "awaiting_human_review"}
        )
        self.assertEqual(
            set(template["tables"][0]["columns"][1]),
            {"id", "label", "value_type", "unit"},
        )
        for required in (
            "deliverables/research-tables.xlsx",
            "deliverables/research-tables/<table-id>.csv",
            "source reference",
            "Formula-like text",
            "does not establish",
        ):
            self.assertIn(required, contract)

    def test_journal_submission_check_owns_source_bound_mechanical_rules(self):
        skill_dir = SKILLS_ROOT / "journal-submission-check"
        skill = (skill_dir / "SKILL.md").read_text(encoding="utf-8")
        contract = (
            skill_dir / "references" / "submission-check-contract.md"
        ).read_text(encoding="utf-8")
        template = json.loads(
            (
                skill_dir
                / "assets"
                / "journal-submission-check.template.json"
            ).read_text(encoding="utf-8")
        )
        self.assertIn("references/submission-check-contract.md", skill)
        self.assertIn("deliverables/journal-submission-check.json", skill)
        self.assertEqual(
            template["schema_version"],
            "ai4heor-journal-submission-check/v1",
        )
        self.assertEqual(
            template["human_review"], {"status": "awaiting_human_review"}
        )
        for required in (
            "official author-guide snapshot",
            "guide_locator",
            "does not establish journal compliance",
            "never bundled",
            "fail closed",
        ):
            self.assertIn(required, contract)


if __name__ == "__main__":
    unittest.main()
