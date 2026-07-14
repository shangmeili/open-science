#!/usr/bin/env python3
"""Verify and search the app-owned AI4HEOR local evidence index."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path
from typing import NoReturn

MANIFEST = Path("heor/evidence-library.json")
INDEX = Path(".openscience/heor-library.sqlite")
PROJECT = Path(".openscience/project.json")
SCHEMA = "0.1.0"
EXTRACTOR = "ai4heor-native/pdf-extract-0.12.0"
DOCUMENT_FIELDS = {
    "path", "sha256", "bytes", "mediaType", "extractionStatus",
    "pageCount", "textSha256", "issue",
}


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def digest_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(64 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def fail(message: str) -> NoReturn:
    raise SystemExit(f"local evidence search blocked: {message}")


def reject_linked_path(root: Path, relative: Path, label: str) -> Path:
    current = root
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            fail(f"{label} contains a symbolic link: {relative}")
    return current


def safe_source(root: Path, value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or not value.startswith("heor/library/"):
        fail(f"unsafe source path in manifest: {value}")
    path = reject_linked_path(root, relative, "source path")
    if not path.is_file():
        fail(f"source is missing or not a file: {value}")
    resolved = path.resolve()
    if root != resolved and root not in resolved.parents:
        fail(f"source escaped the workspace: {value}")
    return resolved


def cjk(character: str) -> bool:
    code = ord(character)
    return 0x3400 <= code <= 0x4DBF or 0x4E00 <= code <= 0x9FFF or 0xF900 <= code <= 0xFAFF


def tokens(value: str) -> list[str]:
    output: list[str] = []
    word: list[str] = []
    han: list[str] = []

    def flush_word() -> None:
        if word:
            output.append("".join(word))
            word.clear()

    def flush_han() -> None:
        if len(han) == 1:
            output.append(han[0])
        elif han:
            output.extend("".join(han[index:index + 2]) for index in range(len(han) - 1))
        han.clear()

    for character in value.lower():
        if cjk(character):
            flush_word()
            han.append(character)
        elif character.isalnum():
            flush_han()
            word.append(character)
        else:
            flush_word()
            flush_han()
    flush_word()
    flush_han()
    return sorted(set(output))


def rank(text: str, query: str, terms: list[str]) -> int:
    lowered = text.lower()
    return lowered.count(query.lower()) * 1000 + sum(lowered.count(term) for term in terms)


def excerpt(text: str, terms: list[str]) -> str:
    lowered = text.lower()
    starts = [lowered.find(term) for term in terms if lowered.find(term) >= 0]
    start = max(0, min(starts, default=0) - 80)
    return " ".join(text[start:start + 440].split())


def load_verified(root: Path) -> tuple[dict, sqlite3.Connection, list[str]]:
    manifest_path = reject_linked_path(root, MANIFEST, "manifest path")
    if not manifest_path.is_file():
        fail("heor/evidence-library.json is missing")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"manifest is unreadable: {error}")
    required = {
        "schemaVersion", "projectId", "libraryPath", "indexPath", "indexSha256",
        "extractor", "documents",
    }
    if set(manifest) != required:
        fail("manifest fields do not match the supported contract")
    if (
        manifest["schemaVersion"] != SCHEMA
        or manifest["libraryPath"] != "heor/library"
        or manifest["indexPath"] != str(INDEX)
        or manifest["extractor"] != EXTRACTOR
        or not isinstance(manifest["documents"], list)
    ):
        fail("manifest contract is unsupported")
    project_path = reject_linked_path(root, PROJECT, "project metadata path")
    try:
        project = json.loads(project_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"project metadata is unreadable: {error}")
    if not isinstance(project, dict) or project.get("id") != manifest["projectId"]:
        fail("manifest belongs to another project")
    indexed: dict[str, dict] = {}
    issues: list[str] = []
    for document in manifest["documents"]:
        if not isinstance(document, dict) or set(document) != DOCUMENT_FIELDS:
            fail("manifest document fields do not match the supported contract")
        path = document.get("path", "")
        status = document.get("extractionStatus")
        issue = document.get("issue")
        if issue:
            issues.append(f"{path}: {issue}")
        if status != "indexed":
            continue
        source = safe_source(root, path)
        if source.stat().st_size != document.get("bytes") or digest_file(source) != document.get("sha256"):
            fail(f"source bytes changed after app sync: {path}")
        indexed[path] = document
    index_path = reject_linked_path(root, INDEX, "index path")
    if not index_path.is_file():
        fail("app-owned SQLite index is missing")
    if digest_file(index_path) != manifest["indexSha256"]:
        fail("app-owned SQLite index hash does not match the manifest")
    connection = sqlite3.connect(f"file:{index_path}?mode=ro", uri=True)
    rows = connection.execute(
        "SELECT path,source_sha256,bytes,media_type,extraction_status,page_count,text_sha256,issue "
        "FROM documents"
    ).fetchall()
    database_documents = {
        row[0]: {
            "path": row[0], "sha256": row[1], "bytes": row[2], "mediaType": row[3],
            "extractionStatus": row[4], "pageCount": row[5], "textSha256": row[6],
            "issue": row[7],
        }
        for row in rows
    }
    manifest_documents = {document["path"]: document for document in manifest["documents"]}
    if database_documents != manifest_documents:
        fail("SQLite document bindings do not match the manifest")
    return manifest, connection, issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    query = args.query.strip()
    if not query or len(query) > 500 or not 1 <= args.limit <= 50:
        fail("query must be 1-500 characters and limit must be 1-50")
    root = args.workspace.resolve()
    terms = tokens(query)
    if not terms:
        fail("query contains no searchable terms")
    manifest, connection, issues = load_verified(root)
    results = []
    verified_pages: dict[str, list[str]] = {}
    for path, source_hash, page, text, text_hash in connection.execute(
        "SELECT p.document_path,d.source_sha256,p.page_number,p.text,p.text_sha256 "
        "FROM pages p JOIN documents d ON d.path=p.document_path "
        "WHERE d.extraction_status='indexed'"
    ):
        if digest(text.encode()) != text_hash:
            fail(f"indexed text hash mismatch: {path} page {page}")
        pages = verified_pages.setdefault(path, [])
        if page != len(pages) + 1:
            fail(f"indexed page sequence is invalid: {path} page {page}")
        pages.append(text)
        score = rank(text, query, terms)
        if score:
            results.append({
                "path": path,
                "page": page,
                "sourceSha256": source_hash,
                "score": score,
                "snippet": excerpt(text, terms),
            })
    indexed_documents = {
        document["path"]: document
        for document in manifest["documents"]
        if document["extractionStatus"] == "indexed"
    }
    if set(verified_pages) != set(indexed_documents):
        fail("indexed page set does not match the manifest")
    for path, document in indexed_documents.items():
        pages = verified_pages[path]
        if len(pages) != document["pageCount"] or digest("\f".join(pages).encode()) != document["textSha256"]:
            fail(f"document text binding does not match the manifest: {path}")
    results.sort(key=lambda item: (-item["score"], item["path"], item["page"]))
    results = results[: args.limit]
    payload = {
        "schemaVersion": SCHEMA,
        "manifestSha256": digest((root / MANIFEST).read_bytes()),
        "query": query,
        "hits": results,
        "libraryIssues": issues,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    print(f"Manifest SHA-256: {payload['manifestSha256']}")
    print(f"Query: {query}")
    print(f"Hits: {len(results)}")
    for index, result in enumerate(results, 1):
        print(f"\n{index}. {result['path']} — page {result['page']} — SHA-256 {result['sourceSha256']}")
        print(f"   score {result['score']} · {result['snippet']}")
    if issues:
        print("\nExcluded library issues:", file=sys.stderr)
        for issue in issues:
            print(f"- {issue}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
