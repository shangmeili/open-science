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
    "literature-review",
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
    "research-presentation",
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
        self.assertEqual(len(self.skill_names), 49)
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
                self.assertIn("49", text)
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

    def test_external_release_inventory_has_no_unfinished_or_excluded_options(self):
        registry = json.loads(
            (ROOT / "runtime/assets/asset-admission-registry.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(registry["schema_version"], "1.1.0")
        self.assertEqual(
            registry["purpose"], "release-eligible-external-adapters-only"
        )
        self.assertEqual(registry["assets"], [])
        self.assertFalse((ROOT / "runtime/skills/external").exists())

        surface = (ROOT / "apps/desktop/src/app/routes/SkillsPage.tsx").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("quarantinedCount", surface)
        self.assertNotIn("rejectedCount", surface)
        for locale in README_BY_LOCALE:
            pages = json.loads(
                (LOCALES_ROOT / locale / "pages.json").read_text(encoding="utf-8")
            )
            admission = pages["skills"]["assetAdmission"]
            for retired_key in (
                "quarantined",
                "rejected",
                "thirdPartyQuarantined",
                "thirdPartyRejected",
                "groupQuarantined",
                "groupRejected",
                "actionCleanRoom",
            ):
                self.assertNotIn(retired_key, admission, (locale, retired_key))
            self.assertTrue(admission["adapterBoundary"])

        trail = (
            ROOT / "docs/THIRD_PARTY_ADMISSION_REVIEW.zh-CN.md"
        ).read_text(encoding="utf-8")
        for source in (
            "AI4S Agent",
            "AI4S Experiment Suite",
            "AI4S Integrity Auditor",
            "AI4S Literature Survey",
            "AI4S Mindmap Renderer",
            "AI4S Paper Writer",
            "AI4S Research Explorer",
            "HEORAgent MCP",
            "Paper Search MCP",
            "BioMCP",
            "DOCX",
            "PDF",
            "PPTX",
            "XLSX",
        ):
            self.assertIn(source, trail)

    def test_conceptual_model_diagram_is_first_party_source_bound_and_layout_only(self):
        native = (
            ROOT / "apps/desktop/src-tauri/src/conceptual_model_diagram.rs"
        ).read_text(encoding="utf-8")
        surface = (
            ROOT
            / "apps/desktop/src/components/heor/ConceptualModelDiagramAssessment.tsx"
        ).read_text(encoding="utf-8")
        skill = (
            SKILLS_ROOT / "heor-model-design" / "SKILL.md"
        ).read_text(encoding="utf-8")
        for output in (
            "deliverables/conceptual-model-layout.json",
            "deliverables/conceptual-model.svg",
            "deliverables/conceptual-model.graphml",
            "deliverables/conceptual-model.audit.json",
        ):
            self.assertIn(output, native)
        self.assertIn("existing_outputs_replaceable", native)
        self.assertIn("data-state-id", native)
        self.assertIn("data-transition-id", native)
        self.assertIn("ConceptualModelDiagramAssessment", surface)
        self.assertIn("onGenerate", surface)
        self.assertNotIn("setModel", surface)
        self.assertIn("SVG and editable GraphML", skill)
        self.assertIn("Never encode a semantic model change as a drawing-only edit", skill)

    def test_general_research_foundation_has_an_explicit_acceptance_matrix(self):
        relative = "docs/RESEARCH_FOUNDATION_CAPABILITIES.zh-CN.md"
        matrix = (ROOT / relative).read_text(encoding="utf-8")
        chinese_readme = (ROOT / "README.zh.md").read_text(encoding="utf-8")
        self.assertIn(relative, chinese_readme)
        for required in (
            "已交付",
            "部分交付",
            "待建设",
            "研究汇报幻灯",
            "RIS、受控 BibTeX 与 CSL-JSON",
            "DOCX/PDF/XLSX",
            "五张工作表",
            "不在表格中重算模型",
            "不能因为“会写报告”或“会生成表格”",
        ):
            self.assertIn(required, matrix)

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

    def test_intel_macos_acceptance_handoff_is_current_and_explicit(self):
        version = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["version"]
        english = (ROOT / "README.md").read_text(encoding="utf-8")
        chinese = (ROOT / "README.zh.md").read_text(encoding="utf-8")
        self.assertIn(f"Current source is {version}", english)
        self.assertIn(f"当前源码为 `{version}`", chinese)
        self.assertIn("Intel macOS product-owner acceptance", english)
        self.assertIn("Intel macOS 产品负责人验收", chinese)
        for text in (english, chinese):
            self.assertIn("AI4HEOR_0.1.41_x64.dmg", text)
            self.assertIn(
                "9fc18e035748a2aa67e06443409dce9ffbd2aed83496ab9f1003138391c18ee6",
                text,
            )
            self.assertIn("capabilities/candidates/", text)
            self.assertIn("learning/preferences.json", text)
            self.assertIn("AI4HEOR_0.1.45_x64.dmg", text)
            self.assertIn(
                "876f37346edd9d99bc39428f23c0abe9be3d332a811a9a0123cc6b1251e733db",
                text,
            )
            self.assertIn("0fc4056", text)
        self.assertIn("not the macOS Keychain", english)
        self.assertIn("不是 macOS 钥匙串", chinese)
        self.assertNotIn("current verified x64 macOS package remains\n0.1.35", english)
        self.assertNotIn("当前已验证的 x64 macOS 安装包仍为 `0.1.35`", chinese)

    def test_project_skill_activation_is_app_owned_hash_bound_and_reversible(self):
        native = (ROOT / "apps/desktop/src-tauri/src/capability_review.rs").read_text(
            encoding="utf-8"
        )
        surface = (ROOT / "apps/desktop/src/app/routes/SkillsPage.tsx").read_text(
            encoding="utf-8"
        )
        technical = (ROOT / "docs/TECHNICAL_DESIGN.md").read_text(encoding="utf-8")
        product = (ROOT / "docs/HEOR_PRODUCT.md").read_text(encoding="utf-8")
        for command in ("audit_skill_candidates", "append_skill_candidate_review"):
            self.assertIn(command, native)
        self.assertIn("validation.json does not approve the exact current candidate bytes", native)
        self.assertIn("will not overwrite it", native)
        self.assertIn("will not delete changed content", native)
        self.assertIn("verified_unanchored_sha256_chain", native)
        self.assertIn("appendSkillCandidateReview", surface)
        self.assertIn("CandidateReviewDialog", surface)
        for text in (technical, product):
            self.assertIn("`.opencode/skills/", text)
            self.assertIn("Revocation", text)
            self.assertIn("exact", text)
        for locale in ("en", "zh-Hans", "ja", "es", "de", "fr", "ko"):
            pages = json.loads(
                (ROOT / f"apps/desktop/src/i18n/locales/{locale}/pages.json").read_text(
                    encoding="utf-8"
                )
            )
            candidates = pages["skills"]["candidates"]
            self.assertTrue(candidates["sectionTitle"])
            self.assertTrue(candidates["dialog"]["confirm"]["activate"])

    def test_local_preference_review_is_human_owned_reversible_and_non_scientific(self):
        native = (ROOT / "apps/desktop/src-tauri/src/preference_review.rs").read_text(
            encoding="utf-8"
        )
        surface = (
            ROOT
            / "apps/desktop/src/components/skills/PreferenceLearningSection.tsx"
        ).read_text(encoding="utf-8")
        technical = (ROOT / "docs/TECHNICAL_DESIGN.md").read_text(encoding="utf-8")
        product = (ROOT / "docs/HEOR_PRODUCT.md").read_text(encoding="utf-8")
        for command in ("audit_local_preferences", "append_local_preference_review"):
            self.assertIn(command, native)
        for boundary in (
            "ALLOWED_SCOPES",
            "contains_sensitive_data",
            "changes_scientific_authority",
            "preference review must target the exact current preference store",
            "verified_unanchored_sha256_chain",
        ):
            self.assertIn(boundary, native)
        self.assertIn("appendLocalPreferenceReview", surface)
        self.assertIn("PreferenceReviewDialog", surface)
        for action in ("Accept", "Update", "Enable", "Disable", "Delete"):
            self.assertIn(f"PreferenceReviewAction::{action}", native)
        for text in (technical, product):
            self.assertIn("`learning/preferences.json`", text)
            self.assertIn("exact proposal", text)
            self.assertIn("hash-linked", text)
        for locale in ("en", "zh-Hans", "ja", "es", "de", "fr", "ko"):
            pages = json.loads(
                (ROOT / f"apps/desktop/src/i18n/locales/{locale}/pages.json").read_text(
                    encoding="utf-8"
                )
            )
            preferences = pages["skills"]["preferences"]
            self.assertTrue(preferences["sectionTitle"])
            self.assertTrue(preferences["dialog"]["confirm"]["accept"])
            self.assertTrue(preferences["dialog"]["confirm"]["delete"])

    def test_startup_readiness_is_local_recoverable_and_not_a_scientific_gate(self):
        native = (
            ROOT / "apps/desktop/src-tauri/src/startup_audit.rs"
        ).read_text(encoding="utf-8")
        runtime = (ROOT / "apps/desktop/src-tauri/src/runtime.rs").read_text(
            encoding="utf-8"
        )
        commands = (ROOT / "apps/desktop/src-tauri/src/lib.rs").read_text(
            encoding="utf-8"
        )
        surface = (
            ROOT
            / "apps/desktop/src/components/settings/StartupReadiness.tsx"
        ).read_text(encoding="utf-8")
        for marker in (
            '"workspace"',
            '"skills"',
            '"heorCore"',
            '"harness"',
            "MIN_FIRST_PARTY_SKILLS",
            "write_probe",
        ):
            self.assertIn(marker, native)
        self.assertNotIn("reqwest", native)
        self.assertNotIn("http://", native)
        self.assertNotIn("https://", native)
        self.assertIn("pub fn restart_runtime", runtime)
        self.assertIn("runtime::restart_runtime", commands)
        self.assertIn("startup_audit::audit_startup_environment", commands)
        self.assertIn("restartLocalRuntime", surface)
        self.assertIn("optional={true}", surface)

        for locale in ("en", "zh-Hans", "ja", "es", "de", "fr", "ko"):
            settings = json.loads(
                (
                    ROOT
                    / f"apps/desktop/src/i18n/locales/{locale}/settings.json"
                ).read_text(encoding="utf-8")
            )
            readiness = settings["readiness"]
            self.assertTrue(readiness["readyTitle"])
            self.assertTrue(readiness["actions"]["restart"])
            self.assertTrue(readiness["checks"]["model"]["optional"])
            self.assertTrue(readiness["scope"])

        english = (ROOT / "README.md").read_text(encoding="utf-8")
        chinese = (ROOT / "README.zh.md").read_text(encoding="utf-8")
        self.assertIn("makes no scientific-validity claim", english)
        self.assertIn("不代表方法适用或科学有效", chinese)


if __name__ == "__main__":
    unittest.main()
