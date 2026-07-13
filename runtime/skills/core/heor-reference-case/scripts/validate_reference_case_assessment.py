#!/usr/bin/env python3
"""Validate the portable reference-case matrix contract.

The desktop performs the authoritative workspace and automatic-method checks.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path


SHA256 = re.compile(r"^[a-f0-9]{64}$")
STATUSES = {"met", "gap", "not_applicable", "unresolved"}


def load(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value, raw


def nonempty(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def validate(assessment_path: Path, plan_path: Path, profile_path: Path) -> list[str]:
    assessment, assessment_raw = load(assessment_path)
    plan, _ = load(plan_path)
    profile, profile_raw = load(profile_path)
    errors: list[str] = []

    if assessment.get("schema_version") != "0.1.0":
        errors.append("assessment schema_version must be 0.1.0")
    for field in ("assessment_id", "analysis_id", "assessed_on"):
        if not nonempty(assessment.get(field)):
            errors.append(f"assessment {field} is required")
    if assessment.get("status") != "ready_for_human_review":
        errors.append("assessment status must be ready_for_human_review")
    if assessment.get("analysis_id") != plan.get("analysis_id"):
        errors.append("assessment analysis_id does not match the plan")

    selected = plan.get("reference_case") or {}
    linked = assessment.get("profile") or {}
    profile_hash = hashlib.sha256(profile_raw).hexdigest()
    for field in ("id", "status"):
        if selected.get(field) != profile.get(field):
            errors.append(f"plan reference_case.{field} does not match the profile")
        if linked.get(field) != profile.get(field):
            errors.append(f"assessment profile.{field} does not match the profile")
    if linked.get("revision") != profile.get("revision"):
        errors.append("assessment profile.revision does not match the profile")
    if linked.get("content_sha256") != profile_hash:
        errors.append("assessment profile.content_sha256 does not match the profile bytes")

    assessment_link = plan.get("reference_case_assessment") or {}
    if assessment_link.get("path") != "heor/reference-case-assessment.json":
        errors.append("plan must link heor/reference-case-assessment.json")
    assessment_hash = hashlib.sha256(assessment_raw).hexdigest()
    if assessment_link.get("content_sha256") != assessment_hash:
        errors.append("plan assessment hash does not match the assessment bytes")

    profile_requirements = profile.get("requirements")
    rows = assessment.get("requirements")
    if not isinstance(profile_requirements, list) or not profile_requirements:
        errors.append("profile requirements must be a non-empty array")
        return errors
    if not isinstance(rows, list):
        errors.append("assessment requirements must be an array")
        return errors

    expected = {item.get("id"): item for item in profile_requirements if isinstance(item, dict)}
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            errors.append(f"requirements[{index}] must be an object")
            continue
        requirement_id = row.get("requirement_id")
        if requirement_id not in expected:
            errors.append(f"requirements[{index}] references an unknown requirement")
            continue
        if requirement_id in seen:
            errors.append(f"requirements[{index}] duplicates {requirement_id}")
        seen.add(requirement_id)
        status = row.get("status")
        if status not in STATUSES:
            errors.append(f"requirements[{index}].status is invalid")
        if not nonempty(row.get("rationale")):
            errors.append(f"requirements[{index}].rationale is required")
        paths = row.get("evidence_paths")
        if not isinstance(paths, list) or not all(nonempty(path) for path in paths):
            errors.append(f"requirements[{index}].evidence_paths must be a string array")
        elif status == "met" and not paths:
            errors.append(f"requirements[{index}] marked met needs evidence_paths")
        if status == "gap" and expected[requirement_id].get("level") == "required":
            errors.append(f"required gap: {requirement_id}")
        if status == "unresolved":
            errors.append(f"unresolved requirement: {requirement_id}")

    missing = sorted(set(expected) - seen)
    if missing:
        errors.append("missing requirements: " + ", ".join(missing))
    return errors


def main() -> int:
    if len(sys.argv) != 4:
        print(
            "usage: validate_reference_case_assessment.py ASSESSMENT PLAN PROFILE",
            file=sys.stderr,
        )
        return 2
    try:
        errors = validate(*(Path(value) for value in sys.argv[1:]))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"INVALID: {error}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"INVALID: {error}", file=sys.stderr)
        return 1
    print("VALID: reference-case assessment contract is complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
