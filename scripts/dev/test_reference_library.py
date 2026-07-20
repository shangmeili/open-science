#!/usr/bin/env python3
"""Contract tests for the first-party local reference-library tool."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT
    / "runtime"
    / "skills"
    / "core"
    / "literature-review"
    / "scripts"
    / "reference_library.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location("reference_library", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load reference-library tool")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class ReferenceLibraryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.library = self.workspace / "references" / "library.json"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_cli(self, *args: str, expected: int = 0) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            [
                sys.executable,
                "-B",
                str(SCRIPT),
                "--workspace",
                str(self.workspace),
                *args,
            ],
            cwd=self.workspace,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            completed.returncode,
            expected,
            f"stdout={completed.stdout}\nstderr={completed.stderr}",
        )
        return completed

    def write(self, relative: str, content: str) -> Path:
        path = self.workspace / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def load_library(self) -> dict:
        return json.loads(self.library.read_text(encoding="utf-8"))

    def test_imports_ris_with_normalized_identity_and_source_binding(self):
        source = self.write(
            "imports/example.ris",
            """TY  - JOUR
AU  - Zhang, Wei
AU  - Li, Ming
TI  - A Cost-Effectiveness Analysis
JO  - Value in Health
PY  - 2025/04/01
VL  - 28
IS  - 4
SP  - 100
EP  - 109
DO  - https://doi.org/10.1000/ABC.12
UR  - https://example.test/article
ER  -
""",
        )

        result = self.run_cli(
            "import",
            "--library",
            "references/library.json",
            "--input",
            "imports/example.ris",
        )
        report = json.loads(result.stdout)
        payload = self.load_library()

        self.assertEqual(report["format"], "ris")
        self.assertEqual(report["records_added"], 1)
        self.assertEqual(payload["schema_version"], "ai4heor-reference-library/v1")
        self.assertEqual(len(payload["records"]), 1)
        record = payload["records"][0]
        self.assertEqual(record["id"], "doi:10.1000/abc.12")
        self.assertEqual(record["DOI"], "10.1000/abc.12")
        self.assertEqual(record["issued"], {"date-parts": [[2025, 4, 1]]})
        self.assertEqual(record["page"], "100-109")
        self.assertEqual(record["author"][0], {"family": "Zhang", "given": "Wei"})
        self.assertEqual(
            record["source_bindings"],
            [
                {
                    "format": "ris",
                    "path": "imports/example.ris",
                    "record_key": "1",
                    "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                }
            ],
        )

    def test_reimport_is_byte_idempotent(self):
        self.write(
            "imports/idempotent.ris",
            "TY  - JOUR\nTI  - Stable Record\nPY  - 2024\nDO  - 10.1000/stable\nER  -\n",
        )
        args = (
            "import",
            "--library",
            "references/library.json",
            "--input",
            "imports/idempotent.ris",
        )
        self.run_cli(*args)
        before = self.library.read_bytes()
        report = json.loads(self.run_cli(*args).stdout)
        self.assertEqual(self.library.read_bytes(), before)
        self.assertEqual(report["records_added"], 0)
        self.assertEqual(report["records_updated"], 0)

    def test_merges_bibtex_duplicate_and_preserves_both_sources(self):
        self.write(
            "imports/first.ris",
            "TY  - JOUR\nTI  - Economic Evaluation\nPY  - 2023\nDO  - doi:10.5555/HEOR\nER  -\n",
        )
        self.write(
            "imports/second.bib",
            """@article{smith2023,
  author = {Smith, Jane and {WHO Guideline Group}},
  title = {{Economic Evaluation}},
  journal = {Health Economics},
  year = {2023},
  doi = {10.5555/heor},
  pmid = {12345678}
}
""",
        )
        self.run_cli(
            "import",
            "--library",
            "references/library.json",
            "--input",
            "imports/first.ris",
        )
        report = json.loads(
            self.run_cli(
                "import",
                "--library",
                "references/library.json",
                "--input",
                "imports/second.bib",
            ).stdout
        )
        record = self.load_library()["records"][0]
        self.assertEqual(report["records_added"], 0)
        self.assertEqual(report["records_updated"], 1)
        self.assertEqual(record["PMID"], "12345678")
        self.assertEqual(record["title"], "Economic Evaluation")
        self.assertEqual(record["container-title"], "Health Economics")
        self.assertEqual(record["citation-key"], "smith2023")
        self.assertEqual(len(record["source_bindings"]), 2)
        self.assertEqual(record["author"][1], {"literal": "WHO Guideline Group"})

        self.run_cli(
            "export",
            "--library",
            "references/library.json",
            "--format",
            "bibtex",
            "--output",
            "exports/roundtrip.bib",
        )
        self.run_cli(
            "import",
            "--library",
            "references/library.json",
            "--input",
            "exports/roundtrip.bib",
        )
        roundtrip = self.load_library()["records"][0]
        self.assertEqual(roundtrip["author"][1], {"literal": "WHO Guideline Group"})
        self.assertFalse(any(conflict["field"] == "author" for conflict in roundtrip.get("conflicts", [])))

    def test_imports_csl_json_and_exports_all_exchange_formats(self):
        self.write(
            "imports/items.json",
            json.dumps(
                [
                    {
                        "id": "local-1",
                        "type": "report",
                        "title": "Budget impact guidance",
                        "author": [{"literal": "National HTA Agency"}],
                        "issued": {"date-parts": [[2026, 2]]},
                        "publisher": "Agency Press",
                        "DOI": "10.1000/GUIDANCE",
                        "URL": "https://example.test/guidance",
                    }
                ],
                ensure_ascii=False,
            ),
        )
        self.run_cli(
            "import",
            "--library",
            "references/library.json",
            "--input",
            "imports/items.json",
            "--format",
            "csl-json",
        )

        for format_name, suffix in (("ris", "ris"), ("bibtex", "bib"), ("csl-json", "json")):
            with self.subTest(format=format_name):
                output = f"exports/library.{suffix}"
                report = json.loads(
                    self.run_cli(
                        "export",
                        "--library",
                        "references/library.json",
                        "--format",
                        format_name,
                        "--output",
                        output,
                    ).stdout
                )
                self.assertEqual(report["records_exported"], 1)
                self.assertTrue((self.workspace / output).is_file())
        csl = json.loads((self.workspace / "exports/library.json").read_text(encoding="utf-8"))
        self.assertEqual(csl[0]["id"], "doi:10.1000/guidance")
        self.assertNotIn("source_bindings", csl[0])
        self.assertIn("TY  - RPRT", (self.workspace / "exports/library.ris").read_text())
        self.assertIn("@techreport{", (self.workspace / "exports/library.bib").read_text())

    def test_different_export_is_not_overwritten(self):
        self.write(
            "imports/one.ris",
            "TY  - JOUR\nTI  - One\nPY  - 2020\nER  -\n",
        )
        self.run_cli(
            "import",
            "--library",
            "references/library.json",
            "--input",
            "imports/one.ris",
        )
        output = self.write("exports/library.ris", "researcher-owned\n")
        result = self.run_cli(
            "export",
            "--library",
            "references/library.json",
            "--format",
            "ris",
            "--output",
            "exports/library.ris",
            expected=2,
        )
        self.assertIn("different existing output", result.stderr)
        self.assertEqual(output.read_text(), "researcher-owned\n")

    def test_rejects_malformed_ris_without_creating_library(self):
        self.write("imports/broken.ris", "TY  - JOUR\nTI  - No terminator\n")
        result = self.run_cli(
            "import",
            "--library",
            "references/library.json",
            "--input",
            "imports/broken.ris",
            expected=2,
        )
        self.assertIn("missing ER", result.stderr)
        self.assertFalse(self.library.exists())

    def test_rejects_bibtex_macros_and_concatenation(self):
        self.write(
            "imports/macro.bib",
            '@string{jhe = "Health Economics"}\n@article{x, title={A}, journal=jhe, year={2024}}\n',
        )
        result = self.run_cli(
            "import",
            "--library",
            "references/library.json",
            "--input",
            "imports/macro.bib",
            expected=2,
        )
        self.assertIn("@string", result.stderr.lower())
        self.assertFalse(self.library.exists())

    def test_rejects_csl_without_required_type_and_id(self):
        self.write("imports/invalid.json", '[{"title":"Missing identity"}]')
        result = self.run_cli(
            "import",
            "--library",
            "references/library.json",
            "--input",
            "imports/invalid.json",
            "--format",
            "csl-json",
            expected=2,
        )
        self.assertIn("requires id and type", result.stderr)

    def test_different_dois_do_not_deduplicate_on_title_and_year(self):
        self.write(
            "imports/conflict.ris",
            """TY  - JOUR
TI  - Same title
PY  - 2024
DO  - 10.1000/a
ER  -
TY  - JOUR
TI  - Same title
PY  - 2024
DO  - 10.1000/b
ER  -
""",
        )
        self.run_cli(
            "import",
            "--library",
            "references/library.json",
            "--input",
            "imports/conflict.ris",
        )
        self.assertEqual(len(self.load_library()["records"]), 2)

    def test_rejects_symlink_input_and_path_outside_workspace(self):
        target = self.write(
            "imports/target.ris",
            "TY  - JOUR\nTI  - Linked\nPY  - 2024\nER  -\n",
        )
        link = self.workspace / "imports/link.ris"
        link.symlink_to(target)
        linked = self.run_cli(
            "import",
            "--library",
            "references/library.json",
            "--input",
            "imports/link.ris",
            expected=2,
        )
        self.assertIn("symbolic links", linked.stderr)

        outside = Path(self.temp.name).parent / "outside-ai4heor.ris"
        outside.write_text("TY  - JOUR\nTI  - Outside\nPY  - 2024\nER  -\n")
        try:
            escaped = self.run_cli(
                "import",
                "--library",
                "references/library.json",
                "--input",
                str(outside),
                expected=2,
            )
            self.assertIn("inside the workspace", escaped.stderr)
        finally:
            outside.unlink()

    def test_validate_fails_closed_on_manual_corruption(self):
        self.write(
            "references/library.json",
            '{"schema_version":"ai4heor-reference-library/v1","records":[{"id":"x"}]}',
        )
        result = self.run_cli(
            "validate",
            "--library",
            "references/library.json",
            expected=2,
        )
        self.assertIn("record type", result.stderr)


if __name__ == "__main__":
    unittest.main()
