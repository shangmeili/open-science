#!/usr/bin/env python3
"""Portable fail-closed validator for AI4HEOR journal-submission manifests."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

MANIFEST_CAP = 4 * 1024 * 1024
FILE_CAP = 50 * 1024 * 1024
SAFE_ID = re.compile(r"^[a-z][A-Za-z0-9_-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
KINDS = {
    "required_file",
    "file_extension_in",
    "file_size_max_bytes",
    "title_characters_max",
    "document_words_max",
    "document_characters_max",
    "section_words_max",
    "section_characters_max",
    "table_count_max",
    "figure_count_max",
    "required_heading",
}
BASE_RULE_FIELDS = {"id", "label", "kind", "severity", "guide_locator", "note"}
RULE_FIELDS = {
    "required_file": {"file_role"},
    "file_extension_in": {"file_role", "allowed"},
    "file_size_max_bytes": {"file_role", "limit"},
    "title_characters_max": {"file_role", "limit"},
    "document_words_max": {"file_role", "limit"},
    "document_characters_max": {"file_role", "limit"},
    "section_words_max": {"file_role", "value", "limit"},
    "section_characters_max": {"file_role", "value", "limit"},
    "table_count_max": {"file_role", "limit"},
    "figure_count_max": {"file_role", "limit"},
    "required_heading": {"file_role", "value"},
}
RESERVED = {
    "deliverables/journal-submission-check.json",
    "deliverables/journal-submission-check.md",
    "deliverables/journal-submission-check.results.json",
    "deliverables/journal-submission-check.audit.json",
}


def bounded(value: object, minimum: int, maximum: int) -> bool:
    return isinstance(value, str) and minimum <= len(value.strip()) <= maximum and not any(
        ord(char) < 32 and char not in "\t\n\r" for char in value
    )


def valid_date(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        return False
    return True


def valid_https(value: object) -> bool:
    if not bounded(value, 12, 500):
        return False
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc) and not parsed.username and not parsed.password


def safe_path(value: object) -> str | None:
    if not bounded(value, 1, 240) or "\\" in value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    relative = path.as_posix()
    return None if relative in RESERVED else relative


def resolve_regular(workspace: Path, relative: str) -> tuple[Path | None, str | None]:
    try:
        root = workspace.resolve(strict=True)
        current = root
        for part in PurePosixPath(relative).parts:
            current /= part
            if current.is_symlink():
                return None, f"{relative} traverses a symlink"
        resolved = current.resolve(strict=True)
    except OSError as error:
        return None, f"{relative} cannot be resolved: {error}"
    if root != resolved and root not in resolved.parents:
        return None, f"{relative} resolves outside the workspace"
    if not resolved.is_file() or resolved.stat().st_size > FILE_CAP:
        return None, f"{relative} is not a supported regular file"
    return resolved, None


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def validate(payload: object, workspace: Path | None = None) -> dict[str, object]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return {"valid": False, "file_count": 0, "rule_count": 0, "errors": ["manifest must be a JSON object"]}
    expected_top = {"schema_version", "check_id", "title", "language", "prepared_on", "journal", "files", "rules", "human_review"}
    if set(payload) != expected_top:
        errors.append("top-level fields do not exactly match the contract")
    if payload.get("schema_version") != "ai4heor-journal-submission-check/v1":
        errors.append("schema_version must be ai4heor-journal-submission-check/v1")
    check_id = payload.get("check_id")
    if not isinstance(check_id, str) or not SAFE_ID.fullmatch(check_id):
        errors.append("check_id must be a safe lowercase ID")
    if not bounded(payload.get("title"), 3, 160):
        errors.append("title is missing or outside its supported length")
    if payload.get("language") not in {"zh-CN", "en"}:
        errors.append("language must be zh-CN or en")
    if not valid_date(payload.get("prepared_on")):
        errors.append("prepared_on must be YYYY-MM-DD")
    if payload.get("human_review") != {"status": "awaiting_human_review"}:
        errors.append("human_review must contain only status=awaiting_human_review")

    journal = payload.get("journal")
    journal_fields = {"name", "article_type", "guide_url", "accessed_on", "version_label", "source_path", "source_sha256"}
    guide_relative: str | None = None
    if not isinstance(journal, dict) or set(journal) != journal_fields:
        errors.append("journal fields do not exactly match the contract")
        journal = {}
    for field, minimum, maximum in (("name", 2, 160), ("article_type", 2, 160), ("version_label", 1, 160)):
        if not bounded(journal.get(field), minimum, maximum):
            errors.append(f"journal.{field} is missing or outside its supported length")
    if not valid_https(journal.get("guide_url")):
        errors.append("journal.guide_url must be an official HTTPS URL without credentials")
    if not valid_date(journal.get("accessed_on")):
        errors.append("journal.accessed_on must be YYYY-MM-DD")
    guide_relative = safe_path(journal.get("source_path"))
    if guide_relative is None:
        errors.append("journal.source_path must be a safe non-output path")
    guide_hash = journal.get("source_sha256")
    if not isinstance(guide_hash, str) or not SHA256.fullmatch(guide_hash):
        errors.append("journal.source_sha256 must be a lowercase SHA-256")
    if workspace is not None and guide_relative is not None:
        guide_path, error = resolve_regular(workspace, guide_relative)
        if error:
            errors.append(error)
        elif guide_path is not None and isinstance(guide_hash, str) and SHA256.fullmatch(guide_hash) and digest(guide_path) != guide_hash:
            errors.append("journal guide snapshot does not match its declared SHA-256")

    files = payload.get("files")
    if not isinstance(files, list) or not 1 <= len(files) <= 32:
        errors.append("files must contain 1-32 entries")
        files = []
    roles: set[str] = set()
    role_paths: dict[str, str] = {}
    paths: set[str] = set()
    for index, item in enumerate(files):
        prefix = f"files[{index}]"
        if not isinstance(item, dict) or set(item) != {"role", "label", "path", "sha256"}:
            errors.append(f"{prefix} fields do not exactly match the contract")
            continue
        role = item.get("role")
        if not isinstance(role, str) or not SAFE_ID.fullmatch(role) or role in roles:
            errors.append(f"{prefix}.role must be a unique safe ID")
        else:
            roles.add(role)
        if not bounded(item.get("label"), 1, 160):
            errors.append(f"{prefix}.label is required")
        relative = safe_path(item.get("path"))
        if relative is None or relative.lower() in paths or relative == guide_relative:
            errors.append(f"{prefix}.path must be a unique safe non-guide path")
        else:
            paths.add(relative.lower())
            if isinstance(role, str):
                role_paths[role] = relative
        expected_hash = item.get("sha256")
        if not isinstance(expected_hash, str) or not SHA256.fullmatch(expected_hash):
            errors.append(f"{prefix}.sha256 must be a lowercase SHA-256")
        if workspace is not None and relative is not None:
            path, error = resolve_regular(workspace, relative)
            if error:
                errors.append(error)
            elif path is not None and isinstance(expected_hash, str) and SHA256.fullmatch(expected_hash) and digest(path) != expected_hash:
                errors.append(f"{relative} does not match its declared SHA-256")
    if "manuscript" not in roles:
        errors.append("files must contain exactly one manuscript role")
    else:
        manuscript = next((item for item in files if isinstance(item, dict) and item.get("role") == "manuscript"), {})
        if not str(manuscript.get("path", "")).lower().endswith(".md"):
            errors.append("the manuscript file must be Markdown (.md)")

    rules = payload.get("rules")
    if not isinstance(rules, list) or not 1 <= len(rules) <= 64:
        errors.append("rules must contain 1-64 entries")
        rules = []
    rule_ids: set[str] = set()
    for index, rule in enumerate(rules):
        prefix = f"rules[{index}]"
        if not isinstance(rule, dict):
            errors.append(f"{prefix} must be an object")
            continue
        kind = rule.get("kind")
        expected_fields = BASE_RULE_FIELDS | RULE_FIELDS.get(kind, set())
        if kind not in KINDS or set(rule) != expected_fields:
            errors.append(f"{prefix} fields do not exactly match a supported rule")
            continue
        rule_id = rule.get("id")
        if not isinstance(rule_id, str) or not SAFE_ID.fullmatch(rule_id) or rule_id in rule_ids:
            errors.append(f"{prefix}.id must be a unique safe ID")
        else:
            rule_ids.add(rule_id)
        if not bounded(rule.get("label"), 2, 160):
            errors.append(f"{prefix}.label is required")
        if rule.get("severity") not in {"required", "review"}:
            errors.append(f"{prefix}.severity must be required or review")
        if not bounded(rule.get("guide_locator"), 1, 240):
            errors.append(f"{prefix}.guide_locator is required")
        if not bounded(rule.get("note"), 0, 500):
            errors.append(f"{prefix}.note is outside the supported length")
        if rule.get("file_role") not in roles:
            errors.append(f"{prefix}.file_role is unknown")
        elif kind not in {"required_file", "file_extension_in", "file_size_max_bytes"} and not role_paths.get(rule["file_role"], "").lower().endswith(".md"):
            errors.append(f"{prefix} requires a Markdown file role")
        if "limit" in rule and (not isinstance(rule["limit"], int) or isinstance(rule["limit"], bool) or not 0 <= rule["limit"] <= 1_000_000_000):
            errors.append(f"{prefix}.limit is outside the supported range")
        if "value" in rule and not bounded(rule["value"], 1, 160):
            errors.append(f"{prefix}.value is required")
        if "allowed" in rule:
            allowed = rule["allowed"]
            if not isinstance(allowed, list) or not 1 <= len(allowed) <= 16 or len(set(allowed)) != len(allowed) or any(not isinstance(ext, str) or not re.fullmatch(r"\.[a-z0-9]{1,10}", ext) for ext in allowed):
                errors.append(f"{prefix}.allowed must contain unique lowercase extensions such as .docx")

    return {"valid": not errors, "file_count": len(files), "rule_count": len(rules), "errors": errors}


def main() -> int:
    if len(sys.argv) not in {2, 3}:
        print("usage: validate_journal_submission.py MANIFEST [WORKSPACE]", file=sys.stderr)
        return 2
    manifest_path = Path(sys.argv[1])
    if not manifest_path.is_file() or manifest_path.stat().st_size > MANIFEST_CAP:
        result = {"valid": False, "file_count": 0, "rule_count": 0, "errors": ["manifest is missing or exceeds 4 MiB"]}
    else:
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            result = {"valid": False, "file_count": 0, "rule_count": 0, "errors": [f"manifest cannot be read: {error}"]}
        else:
            result = validate(payload, Path(sys.argv[2]) if len(sys.argv) == 3 else None)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
