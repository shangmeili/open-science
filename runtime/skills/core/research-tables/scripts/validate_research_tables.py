#!/usr/bin/env python3
"""Portable fail-closed validator for AI4HEOR research-table manifests."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import re
import sys
from pathlib import Path, PurePosixPath

MANIFEST_CAP = 4 * 1024 * 1024
SOURCE_CAP = 20 * 1024 * 1024
SAFE_ID = re.compile(r"^[a-z][A-Za-z0-9_-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
TYPES = {"text", "integer", "number", "percent", "currency", "boolean", "date"}
NUMERIC = {"integer", "number", "percent", "currency"}
RESERVED = {
    "deliverables/research-tables.json",
    "deliverables/research-tables.xlsx",
    "deliverables/research-tables.audit.json",
}


def bounded(value: object, minimum: int, maximum: int) -> bool:
    return isinstance(value, str) and minimum <= len(value.strip()) <= maximum and not any(
        ord(char) < 32 and char not in "\t\n\r" for char in value
    )


def safe_path(value: object) -> str | None:
    if not bounded(value, 1, 240) or "\\" in value:
        return None
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        return None
    relative = path.as_posix()
    if relative in RESERVED or relative.startswith("deliverables/research-tables/"):
        return None
    return relative


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
    if not resolved.is_file() or resolved.stat().st_size > SOURCE_CAP:
        return None, f"{relative} is not a supported regular file"
    return resolved, None


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def valid_date(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        return False
    return len(value) == 10


def validate(manifest: object, workspace: Path | None = None) -> dict[str, object]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return {"valid": False, "table_count": 0, "row_count": 0, "source_count": 0, "errors": ["manifest must be a JSON object"]}
    expected_top = {"schema_version", "workbook_id", "title", "language", "prepared_on", "audience", "purpose", "sources", "tables", "human_review"}
    if set(manifest) != expected_top:
        errors.append("top-level fields do not exactly match the contract")
    if manifest.get("schema_version") != "ai4heor-research-tables/v1":
        errors.append("schema_version must be ai4heor-research-tables/v1")
    if not isinstance(manifest.get("workbook_id"), str) or not SAFE_ID.fullmatch(manifest["workbook_id"]):
        errors.append("workbook_id must be a safe lowercase ID")
    for field, minimum, maximum in (("title", 3, 160), ("audience", 2, 160), ("purpose", 8, 500)):
        if not bounded(manifest.get(field), minimum, maximum):
            errors.append(f"{field} is missing or outside its supported length")
    if manifest.get("language") not in {"zh-CN", "en"}:
        errors.append("language must be zh-CN or en")
    if not valid_date(manifest.get("prepared_on")):
        errors.append("prepared_on must be a valid YYYY-MM-DD date")
    if manifest.get("human_review") != {"status": "awaiting_human_review"}:
        errors.append("human_review must contain only status=awaiting_human_review")

    sources = manifest.get("sources")
    if not isinstance(sources, list) or not 1 <= len(sources) <= 32:
        errors.append("sources must contain 1-32 entries")
        sources = []
    source_ids: set[str] = set()
    source_paths: set[str] = set()
    for index, source in enumerate(sources):
        prefix = f"sources[{index}]"
        if not isinstance(source, dict) or set(source) != {"id", "path", "sha256"}:
            errors.append(f"{prefix} fields do not match the contract")
            continue
        source_id = source.get("id")
        if not isinstance(source_id, str) or not SAFE_ID.fullmatch(source_id) or source_id in source_ids:
            errors.append(f"{prefix}.id must be a unique safe ID")
        else:
            source_ids.add(source_id)
        relative = safe_path(source.get("path"))
        if relative is None or relative.lower() in source_paths:
            errors.append(f"{prefix}.path must be a unique safe source path")
        else:
            source_paths.add(relative.lower())
        expected = source.get("sha256")
        if not isinstance(expected, str) or not SHA256.fullmatch(expected):
            errors.append(f"{prefix}.sha256 must be a lowercase SHA-256")
        if workspace is not None and relative is not None:
            path, error = resolve_regular(workspace, relative)
            if error:
                errors.append(error)
            elif path is not None and isinstance(expected, str) and SHA256.fullmatch(expected) and digest(path) != expected:
                errors.append(f"{relative} does not match its declared SHA-256")

    tables = manifest.get("tables")
    if not isinstance(tables, list) or not 1 <= len(tables) <= 16:
        errors.append("tables must contain 1-16 entries")
        tables = []
    table_ids: set[str] = set()
    sheet_names: set[str] = {"readme 说明"}
    row_count = 0
    for table_index, table in enumerate(tables):
        prefix = f"tables[{table_index}]"
        if not isinstance(table, dict) or set(table) != {"id", "title", "sheet_name", "purpose", "columns", "rows"}:
            errors.append(f"{prefix} fields do not match the contract")
            continue
        table_id = table.get("id")
        if not isinstance(table_id, str) or not SAFE_ID.fullmatch(table_id) or table_id in table_ids:
            errors.append(f"{prefix}.id must be a unique safe ID")
        else:
            table_ids.add(table_id)
        sheet = table.get("sheet_name")
        if not bounded(sheet, 1, 31) or any(char in "[]:*?/\\" for char in sheet) or sheet.strip().lower() in sheet_names:
            errors.append(f"{prefix}.sheet_name is invalid or duplicated")
        else:
            sheet_names.add(sheet.strip().lower())
        if not bounded(table.get("title"), 2, 160) or not bounded(table.get("purpose"), 5, 300):
            errors.append(f"{prefix} needs a bounded title and purpose")
        columns = table.get("columns")
        if not isinstance(columns, list) or not 1 <= len(columns) <= 24:
            errors.append(f"{prefix}.columns must contain 1-24 entries")
            columns = []
        column_ids: set[str] = set()
        column_types: dict[str, tuple[str, bool]] = {}
        for column_index, column in enumerate(columns):
            cp = f"{prefix}.columns[{column_index}]"
            if not isinstance(column, dict) or not set(column).issubset({"id", "label", "value_type", "unit", "nullable", "width"}) or not {"id", "label", "value_type"}.issubset(column):
                errors.append(f"{cp} fields do not match the contract")
                continue
            column_id = column.get("id")
            value_type = column.get("value_type")
            if not isinstance(column_id, str) or not SAFE_ID.fullmatch(column_id) or column_id in column_ids:
                errors.append(f"{cp}.id must be a unique safe ID")
                continue
            column_ids.add(column_id)
            if value_type not in TYPES:
                errors.append(f"{cp}.value_type is unsupported")
                continue
            unit = column.get("unit", "")
            if (value_type in NUMERIC and not bounded(unit, 1, 40)) or (value_type not in NUMERIC and unit != ""):
                errors.append(f"{cp}.unit does not match the column type")
            if not bounded(column.get("label"), 1, 120):
                errors.append(f"{cp}.label is required")
            if "nullable" in column and not isinstance(column["nullable"], bool):
                errors.append(f"{cp}.nullable must be boolean")
            if "width" in column and (not isinstance(column["width"], (int, float)) or isinstance(column["width"], bool) or not 8 <= column["width"] <= 60):
                errors.append(f"{cp}.width must be from 8 to 60")
            column_types[column_id] = (value_type, bool(column.get("nullable", False)))
        rows = table.get("rows")
        if not isinstance(rows, list) or len(rows) > 10000:
            errors.append(f"{prefix}.rows must contain at most 10000 entries")
            rows = []
        row_count += len(rows)
        row_ids: set[str] = set()
        for row_index, row in enumerate(rows):
            rp = f"{prefix}.rows[{row_index}]"
            if not isinstance(row, dict) or not {"row_id", "values", "basis"}.issubset(row) or not set(row).issubset({"row_id", "values", "basis", "source_refs", "note"}):
                errors.append(f"{rp} fields do not match the contract")
                continue
            row_id = row.get("row_id")
            if not isinstance(row_id, str) or not SAFE_ID.fullmatch(row_id) or row_id in row_ids:
                errors.append(f"{rp}.row_id must be a unique safe ID")
            else:
                row_ids.add(row_id)
            values = row.get("values")
            if not isinstance(values, dict) or set(values) != column_ids:
                errors.append(f"{rp}.values must exactly match the column IDs")
                values = {}
            for column_id, (value_type, nullable) in column_types.items():
                value = values.get(column_id)
                valid = value is None and nullable
                if value is not None:
                    if value_type == "text": valid = isinstance(value, str) and bounded(value, 0, 32767)
                    elif value_type == "integer": valid = isinstance(value, int) and not isinstance(value, bool) and abs(value) <= 9007199254740991
                    elif value_type in {"number", "percent", "currency"}: valid = isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
                    elif value_type == "boolean": valid = isinstance(value, bool)
                    elif value_type == "date": valid = valid_date(value)
                if not valid:
                    errors.append(f"{rp}.values.{column_id} does not match {value_type}")
            basis = row.get("basis")
            refs = row.get("source_refs", [])
            note = row.get("note", "")
            if basis in {"evidence", "analysis_output"}:
                if not isinstance(refs, list) or not refs:
                    errors.append(f"{rp} requires source references")
            elif basis == "assumption":
                if refs != [] or not bounded(note, 5, 500):
                    errors.append(f"{rp} assumption needs a note and no source references")
            else:
                errors.append(f"{rp}.basis is unsupported")
            if isinstance(refs, list):
                for ref_index, ref in enumerate(refs):
                    if not isinstance(ref, dict) or set(ref) != {"source_id", "locator"} or ref.get("source_id") not in source_ids or not bounded(ref.get("locator"), 1, 240):
                        errors.append(f"{rp}.source_refs[{ref_index}] is invalid")
    if row_count > 50000:
        errors.append("all tables together exceed 50000 rows")
    return {"valid": not errors, "table_count": len(tables), "row_count": row_count, "source_count": len(sources), "errors": errors}


def main() -> int:
    if len(sys.argv) not in {2, 3}:
        print("usage: validate_research_tables.py MANIFEST [WORKSPACE]", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.is_file() or path.stat().st_size > MANIFEST_CAP:
        result = {"valid": False, "table_count": 0, "row_count": 0, "source_count": 0, "errors": ["manifest is missing or exceeds 4 MiB"]}
    else:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            result = {"valid": False, "table_count": 0, "row_count": 0, "source_count": 0, "errors": [f"manifest cannot be read: {error}"]}
        else:
            result = validate(payload, Path(sys.argv[2]) if len(sys.argv) == 3 else None)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
