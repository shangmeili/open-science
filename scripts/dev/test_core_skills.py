#!/usr/bin/env python3
"""Fail closed on malformed or placeholder first-party core Skills."""

from __future__ import annotations

import ast
import json
import re
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
                self.assertEqual(set(catalog), skill_names)
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
        self.assertNotIn("Complete the current goal.", text)

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


if __name__ == "__main__":
    unittest.main()
