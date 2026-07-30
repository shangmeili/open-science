#!/usr/bin/env python3
"""Contract tests for the first-party open-access full-text queue."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
SCRIPT_DIR = ROOT / "runtime" / "skills" / "core" / "literature-review" / "scripts"
SCRIPT = SCRIPT_DIR / "open_full_text.py"


def load_module():
    sys.path.insert(0, str(SCRIPT_DIR))
    spec = importlib.util.spec_from_file_location("open_full_text", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load open-full-text tool")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class OpenFullTextQueueTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name)
        self.library = self.workspace / "references" / "library.json"
        self.queue = self.workspace / "references" / "full-text-queue.json"
        self.library.parent.mkdir(parents=True)
        self.library.write_text(
            json.dumps(
                {
                    "schema_version": "ai4heor-reference-library/v1",
                    "records": [
                        {
                            "id": "doi:10.1000/example",
                            "type": "article-journal",
                            "title": "Example evaluation",
                            "DOI": "10.1000/example",
                            "PMID": "12345",
                            "source_bindings": [
                                {
                                    "format": "ris",
                                    "path": "imports/example.ris",
                                    "record_key": "1",
                                    "sha256": "a" * 64,
                                }
                            ],
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_prepare_creates_a_library_bound_queue_and_can_append(self):
        report = self.module.prepare_queue(
            self.workspace,
            self.library,
            self.queue,
            ["doi:10.1000/example"],
        )
        payload = json.loads(self.queue.read_text(encoding="utf-8"))
        self.assertEqual(report["queued"], 1)
        self.assertEqual(payload["schema_version"], "ai4heor-full-text-queue/v1")
        self.assertEqual(payload["library"]["sha256"], hashlib.sha256(self.library.read_bytes()).hexdigest())
        self.assertEqual(payload["items"][0]["status"], "queued")
        self.assertNotIn("email", json.dumps(payload))

        second = self.module.prepare_queue(
            self.workspace,
            self.library,
            self.queue,
            ["doi:10.1000/example"],
        )
        self.assertEqual(second["added"], 0)
        self.assertEqual(len(json.loads(self.queue.read_text())["items"]), 1)

    def test_run_downloads_europe_pmc_xml_and_records_provenance(self):
        self.module.prepare_queue(self.workspace, self.library, self.queue, ["doi:10.1000/example"])

        def json_fetch(url: str):
            self.assertIn("europepmc", url)
            return {
                "resultList": {
                    "result": [
                        {
                            "doi": "10.1000/example",
                            "pmid": "12345",
                            "pmcid": "PMC123",
                            "isOpenAccess": "Y",
                            "license": "CC BY",
                        }
                    ]
                }
            }

        def binary_fetch(url: str):
            self.assertTrue(url.endswith("/PMC123/fullTextXML"))
            return b"<?xml version='1.0'?><article><body>Open text</body></article>", url, "application/xml"

        report = self.module.run_queue(
            self.workspace,
            self.library,
            self.queue,
            unpaywall_email=None,
            json_fetch=json_fetch,
            binary_fetch=binary_fetch,
            now=lambda: "2026-07-24T00:00:00Z",
            url_validator=lambda url: url,
        )
        item = json.loads(self.queue.read_text())["items"][0]
        full_text = item["full_text"]
        self.assertEqual(report["downloaded"], 1)
        self.assertEqual(item["status"], "downloaded")
        self.assertEqual(full_text["provider"], "europe-pmc")
        self.assertEqual(full_text["license"], "CC BY")
        self.assertEqual(full_text["retrieved_at"], "2026-07-24T00:00:00Z")
        self.assertTrue((self.workspace / full_text["path"]).read_bytes().startswith(b"<?xml"))

    def test_unpaywall_fallback_downloads_pdf_without_persisting_email(self):
        self.module.prepare_queue(self.workspace, self.library, self.queue, ["doi:10.1000/example"])

        def json_fetch(url: str):
            if "europepmc" in url:
                return {"resultList": {"result": []}}
            self.assertIn("email=researcher%40example.org", url)
            return {
                "best_oa_location": {
                    "url_for_pdf": "https://repository.example.org/example.pdf",
                    "url": "https://repository.example.org/item",
                    "license": "cc-by",
                    "version": "acceptedVersion",
                    "host_type": "repository",
                }
            }

        def binary_fetch(url: str):
            return b"%PDF-1.7\nopen article", url, "application/pdf"

        report = self.module.run_queue(
            self.workspace,
            self.library,
            self.queue,
            unpaywall_email="researcher@example.org",
            json_fetch=json_fetch,
            binary_fetch=binary_fetch,
            url_validator=lambda url: url,
        )
        raw = self.queue.read_text()
        item = json.loads(raw)["items"][0]
        self.assertEqual(report["downloaded"], 1)
        self.assertEqual(item["full_text"]["provider"], "unpaywall")
        self.assertEqual(item["full_text"]["version"], "acceptedVersion")
        self.assertNotIn("researcher@example.org", raw)

    def test_missing_unpaywall_email_is_visible_and_retryable(self):
        self.module.prepare_queue(self.workspace, self.library, self.queue, ["doi:10.1000/example"])
        report = self.module.run_queue(
            self.workspace,
            self.library,
            self.queue,
            unpaywall_email=None,
            json_fetch=lambda _url: {"resultList": {"result": []}},
            binary_fetch=lambda _url: self.fail("binary fetch should not run"),
        )
        item = json.loads(self.queue.read_text())["items"][0]
        self.assertEqual(report["needs_input"], 1)
        self.assertEqual(item["status"], "needs_input")
        self.assertEqual(item["reason"], "unpaywall_email_required")

    def test_library_drift_stops_the_queue(self):
        self.module.prepare_queue(self.workspace, self.library, self.queue, ["doi:10.1000/example"])
        self.library.write_text(self.library.read_text() + " ", encoding="utf-8")
        with self.assertRaisesRegex(self.module.ContractError, "library has changed"):
            self.module.run_queue(
                self.workspace,
                self.library,
                self.queue,
                unpaywall_email=None,
            )

    def test_private_or_loopback_download_targets_are_rejected(self):
        for url in ("http://127.0.0.1/a.pdf", "http://10.0.0.8/a.pdf"):
            with self.subTest(url=url), self.assertRaisesRegex(self.module.ContractError, "public network"):
                self.module.validate_remote_url(url, resolver=lambda *_args: [(None, None, None, None, (url.split('/')[2], 80))])

    def test_archives_a_public_pdf_used_by_the_task_with_provenance(self):
        archive = self.workspace / "references" / "source-files.json"
        url = "https://procurement.example.org/public-price.pdf"
        raw = b"%PDF-1.7\npublic procurement evidence"

        first = self.module.archive_public_pdf(
            self.workspace,
            archive,
            url=url,
            title="Public procurement price notice",
            publisher="Public procurement authority",
            binary_fetch=lambda _url: (raw, url, "application/pdf"),
            now=lambda: "2026-07-25T00:00:00Z",
            url_validator=lambda value: value,
        )
        second = self.module.archive_public_pdf(
            self.workspace,
            archive,
            url=url,
            title="Public procurement price notice",
            publisher="Public procurement authority",
            binary_fetch=lambda _url: (raw, url, "application/pdf"),
            now=lambda: "2026-07-26T00:00:00Z",
            url_validator=lambda value: value,
        )

        payload = json.loads(archive.read_text(encoding="utf-8"))
        self.assertEqual(payload["schema_version"], "ai4heor-source-file-archive/v1")
        self.assertEqual(len(payload["items"]), 1)
        item = payload["items"][0]
        self.assertEqual(item["source_url"], url)
        self.assertEqual(item["retrieved_at"], "2026-07-25T00:00:00Z")
        self.assertEqual(item["rights_basis"], "public_direct_download")
        self.assertEqual(item["sha256"], hashlib.sha256(raw).hexdigest())
        self.assertTrue((self.workspace / item["path"]).is_file())
        self.assertFalse(first["already_archived"])
        self.assertTrue(second["already_archived"])

    def test_public_source_archiver_rejects_non_pdf_responses(self):
        archive = self.workspace / "references" / "source-files.json"
        with self.assertRaisesRegex(self.module.ContractError, "did not return a PDF"):
            self.module.archive_public_pdf(
                self.workspace,
                archive,
                url="https://example.org/not-a-pdf.pdf",
                title="Invalid response",
                binary_fetch=lambda url: (b"<html>not found</html>", url, "text/html"),
                url_validator=lambda value: value,
            )
        self.assertFalse(archive.exists())

    def test_public_source_archiver_rejects_a_symlinked_storage_directory(self):
        outside = self.workspace / "outside"
        outside.mkdir()
        references = self.workspace / "references"
        references.mkdir(exist_ok=True)
        (references / "source-files").symlink_to(outside, target_is_directory=True)

        with self.assertRaisesRegex(self.module.ContractError, "symbolic links are not allowed"):
            self.module.archive_public_pdf(
                self.workspace,
                references / "source-files.json",
                url="https://example.org/source.pdf",
                title="Public source",
                binary_fetch=lambda url: (b"%PDF-1.7\nsource", url, "application/pdf"),
                url_validator=lambda value: value,
            )
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
