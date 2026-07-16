#!/usr/bin/env python3
"""Validate and audit a local AI4HEOR methods watchlist."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

SCHEMA_VERSION = "0.1.0"
MAX_ARTIFACT_BYTES = 5 * 1024 * 1024
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
ROOT_KEYS = {
    "schema_version", "watchlist_id", "status", "as_of_date", "source_order",
    "sources", "change_order", "changes", "limitations",
}
SOURCE_KEYS = {
    "source_id", "title", "organization", "jurisdiction", "source_type",
    "publication_status", "canonical_url", "access_mode", "rights_status",
    "rights_note", "revision", "snapshot", "affected_contracts",
    "monitoring_notes",
}
REVISION_KEYS = {"label", "published_on", "last_checked_on", "next_check_due"}
SNAPSHOT_KEYS = {"path", "content_sha256", "media_type"}
CHANGE_KEYS = {
    "change_id", "source_id", "detected_on", "change_status",
    "previous_revision", "current_revision", "changed_sections", "summary",
    "affected_contracts", "required_actions", "revalidation_status",
    "human_disposition", "evidence_paths",
}
SOURCE_TYPES = {
    "reference_case", "reporting_standard", "method_guideline", "regulation",
    "consultation_draft", "technical_standard",
}
PUBLICATION_STATUSES = {"current", "draft", "superseded", "withdrawn", "unknown"}
RIGHTS_STATUSES = {"link_only", "permission_confirmed", "open_licence", "personal_research"}
MEDIA_TYPES = {
    "application/pdf", "text/html", "text/markdown", "text/plain",
    "application/json",
}


def exact_keys(value: object, expected: set[str], label: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return False
    missing = expected - set(value)
    unknown = set(value) - expected
    if missing:
        errors.append(f"{label} missing fields: {', '.join(sorted(missing))}")
    if unknown:
        errors.append(f"{label} unknown fields: {', '.join(sorted(unknown))}")
    return not missing and not unknown


def nonempty(value: object, label: str, errors: list[str], maximum: int = 2000) -> bool:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        errors.append(f"{label} must be a non-empty string of at most {maximum} characters")
        return False
    return True


def parse_date(value: object, label: str, errors: list[str]) -> date | None:
    if not isinstance(value, str):
        errors.append(f"{label} must be an ISO date")
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        errors.append(f"{label} must be an ISO date")
        return None
    if parsed.isoformat() != value:
        errors.append(f"{label} must use YYYY-MM-DD")
        return None
    return parsed


def string_list(value: object, label: str, errors: list[str], *, required: bool = False) -> list[str]:
    if not isinstance(value, list) or len(value) > 256:
        errors.append(f"{label} must be a list of at most 256 strings")
        return []
    if required and not value:
        errors.append(f"{label} must not be empty")
    if any(not isinstance(item, str) or not item.strip() or len(item) > 500 for item in value):
        errors.append(f"{label} contains an invalid string")
        return []
    if len(set(value)) != len(value):
        errors.append(f"{label} must not contain duplicates")
    return value


def safe_local_path(raw: object, workspace: Path, label: str, errors: list[str]) -> Path | None:
    if not isinstance(raw, str) or not raw.startswith("heor/method-sources/"):
        errors.append(f"{label} must be below heor/method-sources/")
        return None
    candidate = Path(raw)
    if candidate.is_absolute() or ".." in candidate.parts:
        errors.append(f"{label} must be a safe relative path")
        return None
    path = workspace / candidate
    if not path.exists() or not path.is_file() or path.is_symlink():
        errors.append(f"{label} must identify an existing regular non-symlink file")
        return None
    try:
        path.resolve().relative_to(workspace.resolve())
    except ValueError:
        errors.append(f"{label} escapes the workspace")
        return None
    return path


def validate_order(order: object, records: object, label: str, errors: list[str]) -> list[str]:
    values = string_list(order, f"{label}_order", errors)
    if not isinstance(records, dict):
        errors.append(f"{label}s must be an object")
        return values
    if len(records) > 256:
        errors.append(f"{label}s must contain at most 256 records")
    if len(values) == len(set(values)) and set(values) != set(records):
        errors.append(f"{label}_order must contain every {label}s key exactly once")
    return values


def audit(artifact: object, workspace: Path) -> dict:
    errors: list[str] = []
    overdue: list[str] = []
    unresolved: list[str] = []
    current_count = draft_count = unknown_count = 0
    affected_contracts: set[str] = set()

    if not exact_keys(artifact, ROOT_KEYS, "watchlist", errors):
        root = artifact if isinstance(artifact, dict) else {}
    else:
        root = artifact
    if root.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    watchlist_id = root.get("watchlist_id", "")
    if not isinstance(watchlist_id, str) or not SAFE_ID.fullmatch(watchlist_id):
        errors.append("watchlist_id must be a safe lowercase identifier")
    status = root.get("status", "invalid")
    if status not in {"draft", "ready_for_human_review"}:
        errors.append("status must be draft or ready_for_human_review")
    as_of = parse_date(root.get("as_of_date"), "as_of_date", errors)
    sources = root.get("sources", {})
    source_order = validate_order(root.get("source_order"), sources, "source", errors)

    if isinstance(sources, dict):
        for source_id in source_order:
            source = sources.get(source_id)
            label = f"sources.{source_id}"
            if not exact_keys(source, SOURCE_KEYS, label, errors):
                continue
            if not SAFE_ID.fullmatch(source_id) or source["source_id"] != source_id:
                errors.append(f"{label}.source_id must equal its safe map key")
            for field in ("title", "organization", "jurisdiction", "rights_note", "monitoring_notes"):
                nonempty(source[field], f"{label}.{field}", errors)
            if source["source_type"] not in SOURCE_TYPES:
                errors.append(f"{label}.source_type is unsupported")
            publication = source["publication_status"]
            if publication not in PUBLICATION_STATUSES:
                errors.append(f"{label}.publication_status is unsupported")
            elif publication == "current":
                current_count += 1
            elif publication == "draft":
                draft_count += 1
            elif publication == "unknown":
                unknown_count += 1
            url = source["canonical_url"]
            if not isinstance(url, str) or urlparse(url).scheme != "https" or not urlparse(url).netloc:
                errors.append(f"{label}.canonical_url must be an HTTPS URL")
            contracts = string_list(source["affected_contracts"], f"{label}.affected_contracts", errors, required=True)
            affected_contracts.update(contracts)

            revision = source["revision"]
            if exact_keys(revision, REVISION_KEYS, f"{label}.revision", errors):
                nonempty(revision["label"], f"{label}.revision.label", errors)
                published = None if revision["published_on"] is None else parse_date(
                    revision["published_on"], f"{label}.revision.published_on", errors
                )
                checked = parse_date(revision["last_checked_on"], f"{label}.revision.last_checked_on", errors)
                due = parse_date(revision["next_check_due"], f"{label}.revision.next_check_due", errors)
                if published and checked and published > checked:
                    errors.append(f"{label}.revision.published_on cannot follow last_checked_on")
                if checked and as_of and checked > as_of:
                    errors.append(f"{label}.revision.last_checked_on cannot follow as_of_date")
                if due and checked and due < checked:
                    errors.append(f"{label}.revision.next_check_due cannot precede last_checked_on")
                if due and as_of and due < as_of:
                    overdue.append(source_id)

            access = source["access_mode"]
            rights = source["rights_status"]
            snapshot = source["snapshot"]
            if access == "link_only":
                if rights != "link_only" or snapshot is not None:
                    errors.append(f"{label} link_only requires link_only rights and null snapshot")
            elif access == "local_snapshot":
                if rights not in RIGHTS_STATUSES - {"link_only"}:
                    errors.append(f"{label} local_snapshot requires a non-link-only rights status")
                if exact_keys(snapshot, SNAPSHOT_KEYS, f"{label}.snapshot", errors):
                    path = safe_local_path(snapshot["path"], workspace, f"{label}.snapshot.path", errors)
                    digest = snapshot["content_sha256"]
                    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
                        errors.append(f"{label}.snapshot.content_sha256 must be lowercase SHA-256")
                    elif path and hashlib.sha256(path.read_bytes()).hexdigest() != digest:
                        errors.append(f"{label}.snapshot.content_sha256 does not match the file")
                    if snapshot["media_type"] not in MEDIA_TYPES:
                        errors.append(f"{label}.snapshot.media_type is unsupported")
            else:
                errors.append(f"{label}.access_mode is unsupported")

    changes = root.get("changes", {})
    change_order = validate_order(root.get("change_order"), changes, "change", errors)
    if isinstance(changes, dict):
        for change_id in change_order:
            change = changes.get(change_id)
            label = f"changes.{change_id}"
            if not exact_keys(change, CHANGE_KEYS, label, errors):
                continue
            if not SAFE_ID.fullmatch(change_id) or change["change_id"] != change_id:
                errors.append(f"{label}.change_id must equal its safe map key")
            if not isinstance(sources, dict) or change["source_id"] not in sources:
                errors.append(f"{label}.source_id must identify a declared source")
            detected = parse_date(change["detected_on"], f"{label}.detected_on", errors)
            if detected and as_of and detected > as_of:
                errors.append(f"{label}.detected_on cannot follow as_of_date")
            for field in ("previous_revision", "current_revision", "summary"):
                nonempty(change[field], f"{label}.{field}", errors)
            string_list(change["changed_sections"], f"{label}.changed_sections", errors, required=True)
            contracts = string_list(change["affected_contracts"], f"{label}.affected_contracts", errors, required=True)
            affected_contracts.update(contracts)
            string_list(change["required_actions"], f"{label}.required_actions", errors, required=True)
            evidence_paths = string_list(change["evidence_paths"], f"{label}.evidence_paths", errors)
            for index, evidence_path in enumerate(evidence_paths):
                safe_local_path(evidence_path, workspace, f"{label}.evidence_paths[{index}]", errors)
            change_status = change["change_status"]
            revalidation = change["revalidation_status"]
            disposition = change["human_disposition"]
            if change_status not in {"suspected", "confirmed", "dismissed"}:
                errors.append(f"{label}.change_status is unsupported")
            if revalidation not in {"not_started", "in_progress", "complete", "not_required"}:
                errors.append(f"{label}.revalidation_status is unsupported")
            if disposition not in {"pending", "accepted", "rejected"}:
                errors.append(f"{label}.human_disposition is unsupported")
            if change_status == "dismissed" and (disposition != "rejected" or revalidation != "not_required"):
                errors.append(f"{label} dismissed changes require rejected/not_required")
            if change_status in {"suspected", "confirmed"} and (
                disposition == "pending" or revalidation not in {"complete", "not_required"}
            ):
                unresolved.append(change_id)

    string_list(root.get("limitations"), "limitations", errors, required=True)
    complete = (
        not errors and status == "ready_for_human_review" and bool(sources)
        and not overdue and not unresolved
    )
    return {
        "complete": complete,
        "status": status,
        "watchlist_id": watchlist_id,
        "as_of_date": root.get("as_of_date", ""),
        "source_count": len(sources) if isinstance(sources, dict) else 0,
        "current_count": current_count,
        "draft_count": draft_count,
        "unknown_count": unknown_count,
        "overdue_count": len(overdue),
        "change_count": len(changes) if isinstance(changes, dict) else 0,
        "unresolved_change_count": len(unresolved),
        "affected_contract_count": len(affected_contracts),
        "overdue_sources": overdue,
        "unresolved_changes": unresolved,
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("artifact", type=Path)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    args = parser.parse_args()
    if args.artifact.is_symlink() or not args.artifact.is_file():
        print(json.dumps({"errors": ["artifact must be a regular non-symlink file"]}))
        return 1
    if args.artifact.stat().st_size > MAX_ARTIFACT_BYTES:
        print(json.dumps({"errors": ["artifact exceeds 5 MiB"]}))
        return 1
    try:
        artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        print(json.dumps({"errors": [f"cannot read artifact: {error}"]}))
        return 1
    result = audit(artifact, args.workspace)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    sys.exit(main())
