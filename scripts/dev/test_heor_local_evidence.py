import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SEARCH = ROOT / "runtime/skills/core/heor-local-evidence/scripts/search_library.py"


class LocalEvidenceSearchTest(unittest.TestCase):
    def fixture(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        (root / "heor/library").mkdir(parents=True)
        (root / ".openscience").mkdir()
        source = root / "heor/library/evidence.txt"
        source.write_text("成本效果分析 compares incremental cost and QALY.", encoding="utf-8")
        raw = source.read_bytes()
        source_hash = hashlib.sha256(raw).hexdigest()
        text = source.read_text(encoding="utf-8")
        text_hash = hashlib.sha256(text.encode()).hexdigest()
        index = root / ".openscience/heor-library.sqlite"
        connection = sqlite3.connect(index)
        connection.executescript("""
            CREATE TABLE documents (
              path TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL, bytes INTEGER NOT NULL,
              media_type TEXT NOT NULL, extraction_status TEXT NOT NULL,
              page_count INTEGER NOT NULL, text_sha256 TEXT, issue TEXT
            );
            CREATE TABLE pages (
              document_path TEXT NOT NULL, page_number INTEGER NOT NULL,
              text TEXT NOT NULL, text_sha256 TEXT NOT NULL,
              PRIMARY KEY(document_path, page_number)
            );
        """)
        connection.execute(
            "INSERT INTO documents VALUES (?,?,?,?,?,?,?,?)",
            ("heor/library/evidence.txt", source_hash, len(raw), "text/plain", "indexed", 1, text_hash, None),
        )
        connection.execute(
            "INSERT INTO pages VALUES (?,?,?,?)",
            ("heor/library/evidence.txt", 1, text, text_hash),
        )
        connection.commit()
        connection.close()
        manifest = {
            "schemaVersion": "0.1.0",
            "projectId": "test-project",
            "libraryPath": "heor/library",
            "indexPath": ".openscience/heor-library.sqlite",
            "indexSha256": hashlib.sha256(index.read_bytes()).hexdigest(),
            "extractor": "ai4heor-native/pdf-extract-0.12.0",
            "documents": [{
                "path": "heor/library/evidence.txt",
                "sha256": source_hash,
                "bytes": len(raw),
                "mediaType": "text/plain",
                "extractionStatus": "indexed",
                "pageCount": 1,
                "textSha256": text_hash,
                "issue": None,
            }],
        }
        (root / "heor/evidence-library.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        (root / ".openscience/project.json").write_text(
            json.dumps({"id": "test-project"}),
            encoding="utf-8",
        )
        return temporary, root

    def run_search(self, root, query="成本效果"):
        return subprocess.run(
            [sys.executable, str(SEARCH), "--workspace", str(root), "--query", query, "--json"],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_search_returns_hash_bound_page_citation(self):
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        result = self.run_search(root)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(len(payload["hits"]), 1)
        self.assertEqual(payload["hits"][0]["path"], "heor/library/evidence.txt")
        self.assertEqual(payload["hits"][0]["page"], 1)
        self.assertEqual(len(payload["hits"][0]["sourceSha256"]), 64)

    def test_changed_source_hash_fails_closed(self):
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        (root / "heor/library/evidence.txt").write_text("tampered", encoding="utf-8")
        result = self.run_search(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("source bytes changed", result.stderr)

    def test_changed_index_hash_fails_closed(self):
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        with (root / ".openscience/heor-library.sqlite").open("ab") as index:
            index.write(b"tampered")
        result = self.run_search(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("index hash does not match", result.stderr)

    def test_project_mismatch_fails_closed(self):
        temporary, root = self.fixture()
        self.addCleanup(temporary.cleanup)
        (root / ".openscience/project.json").write_text(
            json.dumps({"id": "another-project"}),
            encoding="utf-8",
        )
        result = self.run_search(root)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("another project", result.stderr)


if __name__ == "__main__":
    unittest.main()
