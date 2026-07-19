#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from validate_candidate import validate


class CandidateValidationTests(unittest.TestCase):
    def candidate(self, root: Path, *, secret: bool = False) -> Path:
        candidate = root / "local-review-helper"
        skill = candidate / "skill"
        skill.mkdir(parents=True)
        body = (
            "---\n"
            "name: local-review-helper\n"
            "description: Prepare a bounded local review checklist without making scientific decisions.\n"
            "---\n\n"
            "# Local review helper\n\nPrepare a checklist for Human review.\n"
        )
        if secret:
            body += "credential: " + "sk" + "-" + ("x" * 24) + "\n"
        raw = body.encode()
        (skill / "SKILL.md").write_bytes(raw)
        manifest = {
            "schema": "ai4heor-skill-candidate/v1",
            "id": "local-review-helper",
            "status": "candidate",
            "created_at": "2026-07-19T00:00:00Z",
            "request": "Create a reusable local review checklist.",
            "localized": {
                "en": {"display_name": "Local review helper", "description": "Prepare a local checklist."},
                "zh-Hans": {"display_name": "本地复核清单", "description": "整理可复核的本地检查清单。"},
            },
            "authoring": {"provider": "local-test", "model": "fixture", "session_ref": "test-session"},
            "source": {
                "kind": "user-requested-original",
                "copyright_holder": "test fixture",
                "rights_basis": "test fixture",
                "license_spdx": "MIT",
                "license_note": "test fixture only",
            },
            "permissions": {"network": False, "secrets": False, "commands": False, "outside_workspace": False},
            "files": [{"path": "skill/SKILL.md", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}],
            "limitations": ["Instruction-only test fixture."],
            "acceptance_checks": ["Researcher can inspect the checklist."],
        }
        (candidate / "candidate.json").write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
        return candidate

    def test_valid_bilingual_instruction_only_candidate_passes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report, code = validate(self.candidate(Path(directory)))
        self.assertEqual(code, 0)
        self.assertTrue(report["valid"])
        self.assertEqual(report["checked_files"], ["skill/SKILL.md"])
        self.assertEqual(len(report["decision_sha256"]), 64)

    def test_secret_like_content_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            report, code = validate(self.candidate(Path(directory), secret=True))
        self.assertEqual(code, 1)
        self.assertFalse(report["valid"])
        self.assertIn("possible secret detected in skill/SKILL.md", report["errors"])


if __name__ == "__main__":
    unittest.main()
