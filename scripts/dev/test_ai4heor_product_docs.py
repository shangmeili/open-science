#!/usr/bin/env python3
"""Keep localized public product docs aligned with the shipped AI4HEOR surface."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SKILLS_ROOT = ROOT / "runtime" / "skills" / "core"
LOCALES_ROOT = ROOT / "apps" / "desktop" / "src" / "i18n" / "locales"
README_BY_LOCALE = {
    "en": "README.md",
    "zh-Hans": "README.zh.md",
    "ja": "README.ja.md",
    "es": "README.es.md",
    "de": "README.de.md",
    "fr": "README.fr.md",
    "ko": "README.ko.md",
}
REPRESENTATIVE_SKILLS = {
    "heor-workbench",
    "heor-local-evidence",
    "heor-evidence-search",
    "heor-model-design",
    "heor-cohort-state-transition",
    "heor-partitioned-survival",
    "heor-uncertainty-analysis",
    "heor-advanced-value-of-information",
    "heor-budget-impact",
    "heor-dynamic-budget-impact",
    "heor-model-validation",
    "heor-reporting",
    "heor-reproducibility-package",
}
CURRENT_SCREENSHOTS = (
    "docs/audits/2026-07-17-first-use/06-skip-link-stable.png",
    "docs/audits/2026-07-17-first-use/07-heor-workspace-final.png",
    "docs/audits/2026-07-17-first-use/08-natural-language-draft-final.png",
)
RETIRED_PUBLIC_DEFAULTS = (
    "`ai4s-agent`",
    "`research-explorer`",
    "`literature-survey`",
    "`experiment-suite`",
    "`paper-writer`",
    "`mindmap-render`",
    "`integrity-auditor`",
    "Materials Project",
    "Open-Meteo",
    "USGS water data",
    "/Applications/Open Science.app",
    "docs/assets/showcase-workflow.webp",
    "scripts/dev/fetch-skills.sh",
)
BENCHMARK_BOUNDARY_BY_LOCALE = {
    "en": "not evidence",
    "zh-Hans": "不能证明",
    "ja": "証明するものではありません",
    "es": "no demuestra",
    "de": "belegt weder",
    "fr": "ne prouve ni",
    "ko": "증거가 아닙니다",
}


class AI4HEORProductDocsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill_names = {
            path.parent.name for path in SKILLS_ROOT.glob("*/SKILL.md")
        }
        if not cls.skill_names:
            raise AssertionError("no bundled first-party Skills found")

    def test_localized_skill_catalogs_match_the_bundled_runtime(self):
        self.assertEqual(len(self.skill_names), 47)
        for locale in README_BY_LOCALE:
            with self.subTest(locale=locale):
                payload = json.loads(
                    (LOCALES_ROOT / locale / "skills.json").read_text(encoding="utf-8")
                )
                self.assertEqual(set(payload["catalog"]), self.skill_names)

    def test_localized_readmes_present_current_heor_workflows(self):
        self.assertTrue(REPRESENTATIVE_SKILLS.issubset(self.skill_names))
        for locale, relative in README_BY_LOCALE.items():
            with self.subTest(locale=locale):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("AI4HEOR", text)
                self.assertIn("47", text)
                for skill in REPRESENTATIVE_SKILLS:
                    self.assertIn(f"`${skill}`", text)
                for screenshot in CURRENT_SCREENSHOTS:
                    self.assertIn(screenshot, text)
                    self.assertTrue((ROOT / screenshot).is_file())

    def test_localized_readmes_match_the_governed_connector_boundary(self):
        for locale, relative in README_BY_LOCALE.items():
            with self.subTest(locale=locale):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("PubMed", text)
                self.assertIn("ClinicalTrials.gov", text)
                self.assertIn("Jupyter", text)
                self.assertIn("docs/CONNECT_YOUR_TOOLS.md", text)

    def test_localized_readmes_do_not_advertise_retired_platform_defaults(self):
        for locale, relative in README_BY_LOCALE.items():
            with self.subTest(locale=locale):
                text = (ROOT / relative).read_text(encoding="utf-8")
                for retired in RETIRED_PUBLIC_DEFAULTS:
                    self.assertNotIn(retired, text)

    def test_upstream_benchmark_never_implies_agent_scientific_authority(self):
        for locale, relative in README_BY_LOCALE.items():
            with self.subTest(locale=locale):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("ResearchClawBench", text)
                self.assertIn(BENCHMARK_BOUNDARY_BY_LOCALE[locale], text)

    def test_default_heor_example_is_hash_bound_and_documented(self):
        example = ROOT / "examples/heor-cost-effectiveness"
        runner = example / "run_analysis.py"
        spec_path = example / "inputs/analysis-spec.json"
        inputs = example / "inputs/model-inputs.csv"
        expected_path = example / "expected/base-case-result.json"
        for path in (runner, spec_path, inputs, expected_path):
            self.assertTrue(path.is_file(), path)

        digest = lambda path: hashlib.sha256(path.read_bytes()).hexdigest()
        spec = json.loads(spec_path.read_text(encoding="utf-8"))
        expected = json.loads(expected_path.read_text(encoding="utf-8"))
        self.assertEqual(spec["input_sha256"], digest(inputs))
        self.assertEqual(expected["bindings"]["runner_sha256"], digest(runner))
        self.assertEqual(expected["bindings"]["analysis_spec_sha256"], digest(spec_path))
        self.assertEqual(expected["bindings"]["model_inputs_sha256"], digest(inputs))
        self.assertIsNone(
            expected["incremental_vs_comparator"]["cost_effectiveness_claim"]
        )

        for relative in ("README.md", "README.zh.md", "docs/PRD.md", "docs/HEOR_PRODUCT.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("run_analysis.py", text, relative)
            self.assertIn("expected/base-case-result.json", text, relative)

        product_contract = (ROOT / "docs/HEOR_PRODUCT.md").read_text(encoding="utf-8")
        for output in (
            "outputs/base-case-result.json",
            "outputs/stable-cost-low-result.json",
            "outputs/stable-cost-high-result.json",
        ):
            self.assertIn(output, product_contract)
        self.assertIn("sends no case content", product_contract)

        native = (ROOT / "apps/desktop/src-tauri/src/examples.rs").read_text(
            encoding="utf-8"
        )
        bridge = (ROOT / "apps/desktop/src/lib/tauri.ts").read_text(encoding="utf-8")
        surface = (ROOT / "apps/desktop/src/components/heor/HeorStarters.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("run_heor_teaching_example", native)
        self.assertIn('invoke<TeachingExampleRunResult>("run_heor_teaching_example"', bridge)
        self.assertIn("runHeorTeachingExample()", surface)

    def test_bundled_learning_library_is_a_dated_local_first_asset(self):
        root = ROOT / "runtime" / "knowledge-base" / "zh-Hans"
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(
            manifest["schemaVersion"], "ai4heor-bundled-knowledge-base/v1"
        )
        self.assertEqual(manifest["status"], "dated_learning_material")
        self.assertEqual(
            manifest["boundaries"]["scientificAuthority"], "human_researcher"
        )
        self.assertEqual(
            manifest["boundaries"]["policyStatus"],
            "verify_current_sources_before_use",
        )
        self.assertEqual(len(manifest["files"]), 25)
        for entry in manifest["files"]:
            source = root / entry["path"]
            self.assertTrue(source.is_file(), entry["path"])
            self.assertEqual(
                hashlib.sha256(source.read_bytes()).hexdigest(), entry["sha256"]
            )

        for relative in ("README.md", "docs/PRD.md", "docs/HEOR_PRODUCT.md"):
            text = (ROOT / relative).read_text(encoding="utf-8")
            self.assertIn("knowledge", text.lower(), relative)
        self.assertIn(
            "知识库", (ROOT / "README.zh.md").read_text(encoding="utf-8")
        )
        product_contract = (ROOT / "docs/HEOR_PRODUCT.md").read_text(encoding="utf-8")
        self.assertIn("25 Markdown sources", product_contract)
        self.assertIn("ai4heor-bundled-knowledge-base/v1", product_contract)
        self.assertIn("no model and no network call", product_contract)

        native = (ROOT / "apps/desktop/src-tauri/src/heor_library.rs").read_text(
            encoding="utf-8"
        )
        surface = (ROOT / "apps/desktop/src/components/heor/HeorReviewPane.tsx").read_text(
            encoding="utf-8"
        )
        self.assertIn("install_bundled_heor_knowledge_base", native)
        self.assertIn("installBundledHeorKnowledgeBase", surface)


if __name__ == "__main__":
    unittest.main()
