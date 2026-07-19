#!/usr/bin/env python3
"""Exercise the portable research-presentation contract validator."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "runtime/skills/core/research-presentation/scripts/validate_research_presentation.py"


class ResearchPresentationContractTests(unittest.TestCase):
    def run_validator(self, manifest: dict[str, object], workspace: Path) -> tuple[int, dict[str, object]]:
        path = workspace / "deliverables/research-presentation.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        completed = subprocess.run(
            ["python3", str(VALIDATOR), str(path), str(workspace)],
            check=False,
            capture_output=True,
            text=True,
        )
        return completed.returncode, json.loads(completed.stdout)

    def valid_manifest(self, workspace: Path) -> dict[str, object]:
        report = workspace / "heor/report.md"
        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text("# 已复核报告\n\nICER：125,000 元/QALY。\n", encoding="utf-8")
        source_hash = hashlib.sha256(report.read_bytes()).hexdigest()
        return {
            "schema_version": "0.1.0",
            "deck_id": "project-readout",
            "title": "成本效果分析汇报",
            "subtitle": "研究者复核稿",
            "language": "zh-Hans",
            "prepared_on": "2026-07-19",
            "audience": "项目研究组",
            "purpose": "复核当前结果和局限",
            "theme": "ai4heor-paper",
            "sources": [{
                "source_id": "S1",
                "path": "heor/report.md",
                "sha256": source_hash,
                "label": "当前已复核报告",
            }],
            "slides": [
                {"slide_id": "title", "kind": "title", "title": "成本效果分析汇报", "subtitle": "研究者复核稿"},
                {"slide_id": "result", "kind": "content", "title": "当前结果", "bullets": ["报告中的 ICER 为 125,000 元/QALY。"], "source_refs": ["S1"]},
                {"slide_id": "limits", "kind": "limitations", "title": "局限", "bullets": ["解释仍取决于已复核输入假设。"], "source_refs": ["S1"]},
                {"slide_id": "close", "kind": "closing", "title": "下一步", "bullets": ["外部使用前逐页核对。"]},
            ],
            "human_review": {"status": "awaiting_human_review"},
        }

    def test_accepts_source_bound_human_review_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            code, result = self.run_validator(self.valid_manifest(workspace), workspace)
            self.assertEqual(code, 0)
            self.assertEqual(result, {"errors": [], "slide_count": 4, "source_count": 1, "valid": True})

    def test_fails_closed_on_source_drift_and_agent_claimed_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifest = self.valid_manifest(workspace)
            (workspace / "heor/report.md").write_text("changed", encoding="utf-8")
            manifest["human_review"] = {"status": "approved"}
            code, result = self.run_validator(manifest, workspace)
            self.assertEqual(code, 1)
            self.assertFalse(result["valid"])
            combined = "\n".join(result["errors"])
            self.assertIn("awaiting_human_review", combined)
            self.assertIn("SHA-256", combined)


if __name__ == "__main__":
    unittest.main()
