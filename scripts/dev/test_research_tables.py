#!/usr/bin/env python3
"""Exercise the portable research-table contract validator."""

from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "runtime/skills/core/research-tables/scripts/validate_research_tables.py"


class ResearchTablesContractTests(unittest.TestCase):
    def run_validator(self, manifest: dict[str, object], workspace: Path) -> tuple[int, dict[str, object]]:
        path = workspace / "deliverables/research-tables.json"
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
        result = workspace / "heor/results/base-case.json"
        result.parent.mkdir(parents=True, exist_ok=True)
        result.write_text('{"cost":112000,"qaly":1.62}', encoding="utf-8")
        source_hash = hashlib.sha256(result.read_bytes()).hexdigest()
        return {
            "schema_version": "ai4heor-research-tables/v1",
            "workbook_id": "base-case-tables",
            "title": "成本效果分析表",
            "language": "zh-CN",
            "prepared_on": "2026-07-20",
            "audience": "项目研究团队",
            "purpose": "整理已审计结果，供研究团队逐表核对。",
            "sources": [{"id": "base-case", "path": "heor/results/base-case.json", "sha256": source_hash}],
            "tables": [{
                "id": "base_case",
                "title": "基线分析",
                "sheet_name": "基线分析",
                "purpose": "呈现已审计的成本和健康产出。",
                "columns": [
                    {"id": "strategy", "label": "策略", "value_type": "text"},
                    {"id": "cost", "label": "总成本", "value_type": "currency", "unit": "CNY 2026"},
                    {"id": "qaly", "label": "QALY", "value_type": "number", "unit": "QALY"},
                ],
                "rows": [{
                    "row_id": "intervention",
                    "values": {"strategy": "干预", "cost": 112000, "qaly": 1.62},
                    "basis": "analysis_output",
                    "source_refs": [{"source_id": "base-case", "locator": "cost, qaly"}],
                    "note": "",
                }],
            }],
            "human_review": {"status": "awaiting_human_review"},
        }

    def test_accepts_typed_source_bound_human_review_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            code, result = self.run_validator(self.valid_manifest(workspace), workspace)
            self.assertEqual(code, 0)
            self.assertEqual(result, {"errors": [], "row_count": 1, "source_count": 1, "table_count": 1, "valid": True})

    def test_fails_closed_on_source_drift_unit_loss_and_agent_claimed_approval(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            manifest = self.valid_manifest(workspace)
            (workspace / "heor/results/base-case.json").write_text("changed", encoding="utf-8")
            manifest["tables"][0]["columns"][1]["unit"] = ""
            manifest["human_review"] = {"status": "approved"}
            code, result = self.run_validator(manifest, workspace)
            self.assertEqual(code, 1)
            self.assertFalse(result["valid"])
            combined = "\n".join(result["errors"])
            self.assertIn("SHA-256", combined)
            self.assertIn("unit", combined)
            self.assertIn("awaiting_human_review", combined)


if __name__ == "__main__":
    unittest.main()
