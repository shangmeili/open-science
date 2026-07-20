#!/usr/bin/env python3
"""Exercise the portable target-journal submission-check contract."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = (
    ROOT
    / "runtime/skills/core/journal-submission-check/scripts/validate_journal_submission.py"
)


class JournalSubmissionContractTests(unittest.TestCase):
    def run_validator(
        self, manifest: dict[str, object], workspace: Path
    ) -> tuple[int, dict[str, object]]:
        path = workspace / "deliverables/journal-submission-check.json"
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
        guide = workspace / "references/target-journal-author-guide.pdf"
        manuscript = workspace / "heor/report.md"
        guide.parent.mkdir(parents=True, exist_ok=True)
        manuscript.parent.mkdir(parents=True, exist_ok=True)
        guide.write_bytes(b"local official-guide snapshot")
        manuscript.write_text("# 成本效果分析\n\n## 方法\n\n模型与参数由研究者审核。\n", encoding="utf-8")
        return {
            "schema_version": "ai4heor-journal-submission-check/v1",
            "check_id": "target-journal-check",
            "title": "目标期刊投稿前核对",
            "language": "zh-CN",
            "prepared_on": "2026-07-20",
            "journal": {
                "name": "Value in Health",
                "article_type": "Economic Evaluation",
                "guide_url": "https://www.ispor.org/publications/journals/value-in-health/for-authors/guide-for-authors",
                "accessed_on": "2026-07-20",
                "version_label": "accessed 2026-07-20",
                "source_path": "references/target-journal-author-guide.pdf",
                "source_sha256": hashlib.sha256(guide.read_bytes()).hexdigest(),
            },
            "files": [
                {
                    "role": "manuscript",
                    "label": "投稿正文 Markdown",
                    "path": "heor/report.md",
                    "sha256": hashlib.sha256(manuscript.read_bytes()).hexdigest(),
                }
            ],
            "rules": [
                {
                    "id": "manuscript-required",
                    "label": "提交正文",
                    "kind": "required_file",
                    "severity": "required",
                    "file_role": "manuscript",
                    "guide_locator": "Manuscript components",
                    "note": "",
                },
                {
                    "id": "methods-heading",
                    "label": "方法标题",
                    "kind": "required_heading",
                    "severity": "review",
                    "file_role": "manuscript",
                    "value": "方法",
                    "guide_locator": "Manuscript structure",
                    "note": "只核对 Markdown 标题。",
                },
            ],
            "human_review": {"status": "awaiting_human_review"},
        }

    def test_accepts_source_bound_human_review_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            code, result = self.run_validator(
                self.valid_manifest(workspace), workspace
            )
            self.assertEqual(code, 0)
            self.assertEqual(
                result,
                {"errors": [], "file_count": 1, "rule_count": 2, "valid": True},
            )

    def test_fails_closed_on_source_drift_unknown_fields_and_claimed_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifest = self.valid_manifest(workspace)
            (workspace / "references/target-journal-author-guide.pdf").write_bytes(
                b"changed"
            )
            manifest["rules"][0]["unsupported"] = True
            manifest["human_review"] = {"status": "approved"}
            code, result = self.run_validator(manifest, workspace)
            self.assertEqual(code, 1)
            self.assertFalse(result["valid"])
            combined = "\n".join(result["errors"])
            self.assertIn("guide snapshot", combined)
            self.assertIn("supported rule", combined)
            self.assertIn("awaiting_human_review", combined)


if __name__ == "__main__":
    unittest.main()
