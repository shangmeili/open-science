#!/usr/bin/env python3
"""Fail-closed validator for inactive, instruction-only AI4HEOR Skill candidates."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

MAX_FILE_BYTES = 128 * 1024
MAX_TOTAL_BYTES = 1024 * 1024
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
HEX_RE = re.compile(r"^[0-9a-f]{64}$")
SECRET_PATTERNS = (
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(rb"\b(?:api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*['\"]?[^\s,'\"]{12,}", re.I),
)
ROOT_KEYS = {
    "schema", "id", "status", "created_at", "request", "localized",
    "authoring", "source", "permissions", "files",
}


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def exact_keys(value: object, expected: set[str], label: str, errors: list[str]) -> dict:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return {}
    if set(value) != expected:
        errors.append(f"{label} fields must be exactly {sorted(expected)}")
    return value


def nonempty(value: object, limit: int = 4000) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def safe_files(root: Path, errors: list[str]) -> dict[str, bytes]:
    output: dict[str, bytes] = {}
    total = 0
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            errors.append(f"symlink is not allowed: {relative}")
            continue
        if path.is_dir():
            continue
        if any(part.startswith(".") for part in Path(relative).parts):
            errors.append(f"hidden file is not allowed: {relative}")
            continue
        allowed = relative == "candidate.json" or relative == "validation.json"
        allowed = allowed or relative == "skill/SKILL.md"
        allowed = allowed or (
            relative.startswith("skill/references/") and relative.endswith(".md")
        )
        if not allowed:
            errors.append(f"unexpected candidate file: {relative}")
            continue
        raw = path.read_bytes()
        if len(raw) > MAX_FILE_BYTES:
            errors.append(f"file exceeds {MAX_FILE_BYTES} bytes: {relative}")
        total += len(raw)
        if any(pattern.search(raw) for pattern in SECRET_PATTERNS):
            errors.append(f"possible secret detected in {relative}")
        output[relative] = raw
    if total > MAX_TOTAL_BYTES:
        errors.append(f"candidate exceeds {MAX_TOTAL_BYTES} bytes")
    return output


def validate(root: Path) -> tuple[dict, int]:
    errors: list[str] = []
    if not root.is_dir() or root.is_symlink():
        return {"valid": False, "errors": ["candidate path must be a real directory"]}, 1
    files = safe_files(root, errors)
    raw_manifest = files.get("candidate.json")
    if raw_manifest is None:
        return {"valid": False, "errors": errors + ["candidate.json is required"]}, 1
    try:
        manifest = json.loads(raw_manifest)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"valid": False, "errors": errors + [f"candidate.json is invalid: {exc}"]}, 1
    manifest = exact_keys(manifest, ROOT_KEYS, "candidate", errors)

    skill_id = manifest.get("id")
    if not isinstance(skill_id, str) or not ID_RE.fullmatch(skill_id) or len(skill_id) > 64:
        errors.append("id must be a lowercase hyphenated identifier of at most 64 characters")
    elif root.name != skill_id:
        errors.append("candidate directory name must equal id")
    if manifest.get("schema") != "ai4heor-skill-candidate/v2":
        errors.append("schema must be ai4heor-skill-candidate/v2")
    if manifest.get("status") != "candidate":
        errors.append("status must remain candidate")
    if not nonempty(manifest.get("created_at"), 64) or not str(manifest.get("created_at")).endswith("Z"):
        errors.append("created_at must be a UTC timestamp ending in Z")
    if not nonempty(manifest.get("request")):
        errors.append("request is required and must be at most 4000 characters")

    localized = manifest.get("localized")
    if not isinstance(localized, dict) or not {"en", "zh-Hans"}.issubset(localized):
        errors.append("localized must include en and zh-Hans")
    elif any(not isinstance(locale, str) or not locale for locale in localized):
        errors.append("localized locale identifiers must be non-empty strings")
    else:
        for locale, entry in localized.items():
            entry = exact_keys(
                entry,
                {"display_name", "description", "license_note", "limitations", "acceptance_checks"},
                f"localized.{locale}",
                errors,
            )
            if not nonempty(entry.get("display_name"), 120) or not nonempty(entry.get("description"), 600):
                errors.append(f"localized.{locale} requires bounded display_name and description")
            if not nonempty(entry.get("license_note"), 1000):
                errors.append(f"localized.{locale}.license_note is required")
            for field in ("limitations", "acceptance_checks"):
                values = entry.get(field)
                if not isinstance(values, list) or not values or any(not nonempty(value, 1000) for value in values):
                    errors.append(f"localized.{locale}.{field} must be a non-empty array of bounded text values")

    authoring = exact_keys(manifest.get("authoring"), {"provider", "model", "session_ref"}, "authoring", errors)
    for field in ("provider", "model", "session_ref"):
        if not nonempty(authoring.get(field), 300):
            errors.append(f"authoring.{field} is required")

    source = exact_keys(
        manifest.get("source"),
        {"kind", "copyright_holder", "rights_basis", "license_spdx", "license_note"},
        "source",
        errors,
    )
    for field in ("kind", "copyright_holder", "rights_basis", "license_spdx", "license_note"):
        if not nonempty(source.get(field), 1000):
            errors.append(f"source.{field} is required")

    permissions = exact_keys(
        manifest.get("permissions"),
        {"network", "secrets", "commands", "outside_workspace"},
        "permissions",
        errors,
    )
    if any(permissions.get(field) is not False for field in ("network", "secrets", "commands", "outside_workspace")):
        errors.append("instruction-only candidates must deny every declared permission")

    listed = manifest.get("files")
    expected_paths: set[str] = set()
    if not isinstance(listed, list) or not listed:
        errors.append("files must be a non-empty array")
    else:
        for index, record in enumerate(listed):
            record = exact_keys(record, {"path", "bytes", "sha256"}, f"files[{index}]", errors)
            path = record.get("path")
            if path == "skill/SKILL.md" or (
                isinstance(path, str) and path.startswith("skill/references/") and path.endswith(".md")
            ):
                if path in expected_paths:
                    errors.append(f"duplicate file record: {path}")
                expected_paths.add(path)
                actual = files.get(path)
                if actual is None:
                    errors.append(f"listed file is missing: {path}")
                else:
                    if record.get("bytes") != len(actual):
                        errors.append(f"byte size mismatch: {path}")
                    if not isinstance(record.get("sha256"), str) or not HEX_RE.fullmatch(record["sha256"]):
                        errors.append(f"invalid sha256: {path}")
                    elif record["sha256"] != sha256(actual):
                        errors.append(f"sha256 mismatch: {path}")
            else:
                errors.append(f"unsafe listed path: {path}")
        actual_paths = {path for path in files if path.startswith("skill/")}
        if expected_paths != actual_paths:
            errors.append("files must list every and only Skill content file")

    skill_raw = files.get("skill/SKILL.md", b"")
    try:
        skill_text = skill_raw.decode("utf-8")
    except UnicodeDecodeError:
        skill_text = ""
        errors.append("skill/SKILL.md must be UTF-8")
    frontmatter = re.match(r"^---\nname: ([^\n]+)\ndescription: ([^\n]+)\n---\n", skill_text)
    if not frontmatter:
        errors.append("skill/SKILL.md must begin with exact name and one-line description frontmatter")
    elif frontmatter.group(1).strip() != skill_id:
        errors.append("SKILL.md frontmatter name must equal candidate id")
    elif len(frontmatter.group(2).strip()) > 600:
        errors.append("SKILL.md description must be at most 600 characters")

    decision_inputs = [raw_manifest]
    decision_inputs.extend(files[path] for path in sorted(expected_paths) if path in files)
    decision_hash = sha256(b"\0".join(decision_inputs))
    report = {
        "schema": "ai4heor-skill-validation/v2",
        "candidate_id": skill_id if isinstance(skill_id, str) else "",
        "validated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "valid": not errors,
        "instruction_only": True,
        "decision_sha256": decision_hash,
        "checked_files": sorted(expected_paths),
        "errors": errors,
    }
    return report, 0 if not errors else 1


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_candidate.py <candidate-directory>", file=sys.stderr)
        return 2
    root = Path(sys.argv[1]).resolve()
    report, code = validate(root)
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    try:
        (root / "validation.json").write_text(output, encoding="utf-8")
    except OSError as exc:
        print(f"could not write validation.json: {exc}", file=sys.stderr)
        return 2
    print(output, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
