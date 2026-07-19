#!/usr/bin/env python3
"""Portable fail-closed validator for AI4HEOR research presentations."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath

MANIFEST_CAP = 1024 * 1024
SOURCE_CAP = 25 * 1024 * 1024
IMAGE_CAP = 10 * 1024 * 1024
SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
LANGUAGE = re.compile(r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{2,8}){0,2}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
KINDS = {"title", "section", "content", "table", "figure", "limitations", "closing"}
GENERATED = {
    "deliverables/research-presentation.pptx",
    "deliverables/research-presentation.audit.json",
}


def text(value: object, maximum: int, *, minimum: int = 1) -> str | None:
    if not isinstance(value, str) or not (minimum <= len(value.strip()) <= maximum):
        return None
    if any(ord(char) < 32 and char not in "\t\n\r" for char in value):
        return None
    return value.strip()


def safe_path(value: object) -> str | None:
    candidate = text(value, 240)
    if not candidate or "\\" in candidate:
        return None
    path = PurePosixPath(candidate)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        return None
    normalized = path.as_posix()
    return None if normalized in GENERATED else normalized


def bounded_strings(value: object, minimum: int, maximum: int, length: int) -> list[str] | None:
    if not isinstance(value, list) or not (minimum <= len(value) <= maximum):
        return None
    result: list[str] = []
    for item in value:
        parsed = text(item, length)
        if parsed is None:
            return None
        result.append(parsed)
    return result if len(set(result)) == len(result) else None


def resolve_regular(workspace: Path, relative: str, cap: int) -> tuple[Path | None, str | None]:
    candidate = workspace.joinpath(*PurePosixPath(relative).parts)
    try:
        root = workspace.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
    except OSError as error:
        return None, f"{relative} cannot be resolved: {error}"
    if root != resolved and root not in resolved.parents:
        return None, f"{relative} resolves outside the workspace"
    current = root
    for part in PurePosixPath(relative).parts:
        current = current / part
        if current.is_symlink():
            return None, f"{relative} traverses a symlink"
    if not resolved.is_file():
        return None, f"{relative} is not a regular file"
    if resolved.stat().st_size > cap:
        return None, f"{relative} exceeds the {cap // (1024 * 1024)} MiB cap"
    return resolved, None


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def validate(manifest: object, workspace: Path | None = None) -> dict[str, object]:
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return {"valid": False, "slide_count": 0, "source_count": 0, "errors": ["manifest must be a JSON object"]}
    if manifest.get("schema_version") != "0.1.0":
        errors.append("schema_version must be 0.1.0")
    if (
        not isinstance(manifest.get("deck_id"), str)
        or not SAFE_ID.fullmatch(manifest["deck_id"])
        or not manifest["deck_id"][0].islower()
    ):
        errors.append("deck_id must be a lowercase safe 1-64 character ID")
    for field, maximum in (("title", 120), ("audience", 160), ("purpose", 240)):
        if text(manifest.get(field), maximum) is None:
            errors.append(f"{field} is required and must be at most {maximum} characters")
    if text(manifest.get("subtitle", ""), 200, minimum=0) is None:
        errors.append("subtitle must be at most 200 characters")
    if not isinstance(manifest.get("language"), str) or not LANGUAGE.fullmatch(manifest["language"]):
        errors.append("language must be a compact BCP-47 language tag")
    if not isinstance(manifest.get("prepared_on"), str) or not DATE.fullmatch(manifest["prepared_on"]):
        errors.append("prepared_on must be YYYY-MM-DD")
    if manifest.get("theme") != "ai4heor-paper":
        errors.append("theme must be ai4heor-paper")
    if manifest.get("human_review") != {"status": "awaiting_human_review"}:
        errors.append("human_review must contain only status=awaiting_human_review")

    sources = manifest.get("sources")
    source_ids: set[str] = set()
    source_paths: set[str] = set()
    if not isinstance(sources, list) or not (1 <= len(sources) <= 30):
        errors.append("sources must contain 1-30 entries")
        sources = []
    for index, source in enumerate(sources):
        prefix = f"sources[{index}]"
        if not isinstance(source, dict):
            errors.append(f"{prefix} must be an object")
            continue
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not SAFE_ID.fullmatch(source_id) or source_id in source_ids:
            errors.append(f"{prefix}.source_id must be a unique safe ID")
        else:
            source_ids.add(source_id)
        relative = safe_path(source.get("path"))
        if relative is None or relative in source_paths:
            errors.append(f"{prefix}.path must be a unique safe workspace-relative path")
        else:
            source_paths.add(relative)
        expected = source.get("sha256")
        if not isinstance(expected, str) or not SHA256.fullmatch(expected):
            errors.append(f"{prefix}.sha256 must be a lowercase SHA-256")
        if text(source.get("label"), 160) is None:
            errors.append(f"{prefix}.label is required and must be at most 160 characters")
        if workspace is not None and relative is not None:
            path, error = resolve_regular(workspace, relative, SOURCE_CAP)
            if error:
                errors.append(error)
            elif path is not None and isinstance(expected, str) and SHA256.fullmatch(expected) and digest(path) != expected:
                errors.append(f"{relative} does not match its declared SHA-256")

    slides = manifest.get("slides")
    slide_ids: set[str] = set()
    limitations = 0
    if not isinstance(slides, list) or not (3 <= len(slides) <= 30):
        errors.append("slides must contain 3-30 authored slides")
        slides = []
    if slides and (not isinstance(slides[0], dict) or slides[0].get("kind") != "title"):
        errors.append("the first slide must have kind=title")
    if slides and (not isinstance(slides[-1], dict) or slides[-1].get("kind") != "closing"):
        errors.append("the last slide must have kind=closing")
    for index, slide in enumerate(slides):
        prefix = f"slides[{index}]"
        if not isinstance(slide, dict):
            errors.append(f"{prefix} must be an object")
            continue
        slide_id = slide.get("slide_id")
        if not isinstance(slide_id, str) or not SAFE_ID.fullmatch(slide_id) or slide_id in slide_ids:
            errors.append(f"{prefix}.slide_id must be a unique safe ID")
        else:
            slide_ids.add(slide_id)
        kind = slide.get("kind")
        if kind not in KINDS:
            errors.append(f"{prefix}.kind is not supported")
            continue
        if text(slide.get("title"), 120) is None:
            errors.append(f"{prefix}.title is required and must be at most 120 characters")
        refs = slide.get("source_refs")
        if kind in {"content", "table", "figure", "limitations"}:
            parsed_refs = bounded_strings(refs, 1, 8, 64)
            if parsed_refs is None or any(ref not in source_ids for ref in parsed_refs):
                errors.append(f"{prefix}.source_refs must contain 1-8 unique declared source IDs")
        elif refs not in (None, []):
            errors.append(f"{prefix}.source_refs is not allowed for {kind} slides")
        if kind in {"title", "section"}:
            if text(slide.get("subtitle", ""), 200, minimum=0) is None:
                errors.append(f"{prefix}.subtitle must be at most 200 characters")
        if kind in {"content", "limitations", "closing"}:
            maximum = 5 if kind == "closing" else 8
            if bounded_strings(slide.get("bullets"), 1, maximum, 240) is None:
                errors.append(f"{prefix}.bullets must contain 1-{maximum} unique entries of at most 240 characters")
        if kind == "limitations":
            limitations += 1
        if kind == "table":
            columns = bounded_strings(slide.get("columns"), 2, 8, 80)
            rows = slide.get("rows")
            if columns is None:
                errors.append(f"{prefix}.columns must contain 2-8 unique labels")
            if not isinstance(rows, list) or not (1 <= len(rows) <= 20):
                errors.append(f"{prefix}.rows must contain 1-20 rows")
            else:
                for row_index, row in enumerate(rows):
                    if not isinstance(row, list) or columns is None or len(row) != len(columns) or any(text(cell, 120, minimum=0) is None for cell in row):
                        errors.append(f"{prefix}.rows[{row_index}] must match the columns and contain cells of at most 120 characters")
            if text(slide.get("caption", ""), 300, minimum=0) is None:
                errors.append(f"{prefix}.caption must be at most 300 characters")
        if kind == "figure":
            relative = safe_path(slide.get("image_path"))
            expected = slide.get("image_sha256")
            if relative is None or Path(relative).suffix.lower() not in {".png", ".jpg", ".jpeg"}:
                errors.append(f"{prefix}.image_path must be a safe local PNG or JPEG path")
            if not isinstance(expected, str) or not SHA256.fullmatch(expected):
                errors.append(f"{prefix}.image_sha256 must be a lowercase SHA-256")
            if text(slide.get("alt_text"), 400, minimum=10) is None:
                errors.append(f"{prefix}.alt_text must contain 10-400 characters")
            if text(slide.get("caption", ""), 300, minimum=0) is None:
                errors.append(f"{prefix}.caption must be at most 300 characters")
            if workspace is not None and relative is not None:
                path, error = resolve_regular(workspace, relative, IMAGE_CAP)
                if error:
                    errors.append(error)
                elif path is not None and isinstance(expected, str) and SHA256.fullmatch(expected) and digest(path) != expected:
                    errors.append(f"{relative} does not match its declared image SHA-256")
    if limitations == 0:
        errors.append("at least one limitations slide is required")
    return {
        "valid": not errors,
        "slide_count": len(slides),
        "source_count": len(sources),
        "errors": errors,
    }


def main() -> int:
    if len(sys.argv) not in {2, 3}:
        print("usage: validate_research_presentation.py MANIFEST [WORKSPACE]", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.is_file() or path.stat().st_size > MANIFEST_CAP:
        result = {"valid": False, "slide_count": 0, "source_count": 0, "errors": ["manifest is missing or exceeds 1 MiB"]}
    else:
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            result = {"valid": False, "slide_count": 0, "source_count": 0, "errors": [f"manifest cannot be read: {error}"]}
        else:
            workspace = Path(sys.argv[2]) if len(sys.argv) == 3 else None
            result = validate(manifest, workspace)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
