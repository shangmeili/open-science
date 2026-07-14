#!/usr/bin/env python3
"""Deterministically audit the AI4HEOR evidence-synthesis JSON contract."""

from __future__ import annotations

import json
import sys
from datetime import date
from hashlib import sha256
from pathlib import Path
from typing import Any


DECISIONS = {"include", "exclude", "unclear", "not_assessed"}
VERIFICATION = {"agent_extracted", "human_checked", "conflict"}
CONFLICT_STATUS = {"unresolved", "proposed", "resolved_by_human"}
APPRAISAL_STATUS = {"agent_draft", "human_checked", "not_applicable"}
MAX_SEARCHES = 1_000
MAX_RECORDS = 50_000
MAX_EXTRACTIONS = 50_000
MAX_CONFLICTS = 10_000
ROOT_FIELDS = {
    "schema_version", "synthesis_id", "status", "research_question", "eligibility",
    "searches", "deduplication", "records", "extractions", "conflicts", "limitations",
}


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _text_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(_text(item) for item in value)


def _exact(value: dict[str, Any], allowed: set[str], label: str, errors: list[str]) -> None:
    errors.extend(f"{label} contains unsupported field: {key}" for key in value if key not in allowed)


def _date(value: Any) -> bool:
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        return False
    return 1900 <= parsed.year <= 3000 and parsed.isoformat() == value


def _sha(value: Any) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


def audit(value: Any, allow_empty_searches: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return {"complete": False, "importable": False, "errors": ["artifact must be a JSON object"]}
    _exact(value, ROOT_FIELDS, "artifact", errors)
    if value.get("schema_version") != "0.1.0":
        errors.append("schema_version must be 0.1.0")
    if not _text(value.get("synthesis_id")):
        errors.append("synthesis_id is required")
    if value.get("status") not in {"draft", "ready_for_human_review"}:
        errors.append("status is invalid")

    question = value.get("research_question")
    if not isinstance(question, dict):
        errors.append("research_question is required")
    else:
        _exact(question, {"population", "intervention", "comparator", "outcomes", "study_designs"}, "research_question", errors)
        for field in ("population", "intervention", "comparator"):
            if not _text(question.get(field)):
                errors.append(f"research_question.{field} is required")
        for field in ("outcomes", "study_designs"):
            if not _text_list(question.get(field)):
                errors.append(f"research_question.{field} must be a non-empty string array")

    eligibility = value.get("eligibility")
    if not isinstance(eligibility, dict):
        errors.append("eligibility is required")
    else:
        _exact(eligibility, {"inclusion", "exclusion"}, "eligibility", errors)
        for field in ("inclusion", "exclusion"):
            if not _text_list(eligibility.get(field)):
                errors.append(f"eligibility.{field} must be a non-empty string array")

    searches = value.get("searches")
    if not isinstance(searches, list):
        errors.append("searches must be an array")
        searches = []
    elif len(searches) > MAX_SEARCHES:
        errors.append(f"searches exceeds the cap of {MAX_SEARCHES}")
        searches = []
    elif not searches and not allow_empty_searches:
        errors.append("at least one documented search is required")
    search_ids: set[str] = set()
    for index, search in enumerate(searches):
        label = f"searches[{index}]"
        if not isinstance(search, dict):
            errors.append(f"{label} must be an object")
            continue
        _exact(search, {
            "id", "source", "query", "searched_on", "result_count", "access",
            "authorization_event_id", "request_sha256", "run_path", "run_sha256",
            "endpoint", "response_sha256",
        }, label, errors)
        search_id = search.get("id")
        if not _text(search_id) or search_id in search_ids:
            errors.append(f"{label}.id must be non-empty and unique")
        else:
            search_ids.add(search_id)
        for field in ("source", "query"):
            if not _text(search.get(field)):
                errors.append(f"{label}.{field} is required")
        if not _date(search.get("searched_on")):
            errors.append(f"{label}.searched_on must be a valid YYYY-MM-DD date")
        if search.get("access") not in {"network", "local"}:
            errors.append(f"{label}.access is invalid")
        count = search.get("result_count")
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            errors.append(f"{label}.result_count must be a non-negative integer")
        binding_fields = {
            "authorization_event_id", "request_sha256", "run_path", "run_sha256",
            "endpoint", "response_sha256",
        }
        present = binding_fields.intersection(search)
        if present and present != binding_fields:
            errors.append(f"{label} has an incomplete app-search binding")
        elif present and (
            not isinstance(search.get("authorization_event_id"), str)
            or len(search["authorization_event_id"]) != 32
            or any(ch not in "0123456789abcdef" for ch in search["authorization_event_id"])
            or not _sha(search.get("request_sha256"))
            or not isinstance(search.get("run_path"), str)
            or Path(search["run_path"]).is_absolute()
            or not search["run_path"].startswith("heor/evidence-search-runs/")
            or ".." in Path(search["run_path"]).parts
            or not _sha(search.get("run_sha256"))
            or (search.get("source"), search.get("endpoint")) not in {
                ("pubmed", "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"),
                ("clinicaltrials", "https://clinicaltrials.gov/api/v2/studies"),
            }
            or not _text_list(search.get("response_sha256"))
            or any(not _sha(item) for item in search.get("response_sha256", []))
        ):
            errors.append(f"{label} has an invalid app-search binding")

    deduplication = value.get("deduplication")
    if not isinstance(deduplication, dict):
        errors.append("deduplication is required")
    else:
        _exact(deduplication, {"method", "duplicate_records_removed"}, "deduplication", errors)
        if not _text(deduplication.get("method")):
            errors.append("deduplication.method is required")
        duplicate_count = deduplication.get("duplicate_records_removed")
        if not isinstance(duplicate_count, int) or isinstance(duplicate_count, bool) or duplicate_count < 0:
            errors.append("deduplication.duplicate_records_removed must be a non-negative integer")

    records = value.get("records")
    if not isinstance(records, list):
        errors.append("records must be an array")
        records = []
    elif len(records) > MAX_RECORDS:
        errors.append(f"records exceeds the cap of {MAX_RECORDS}")
        records = []
    record_ids: set[str] = set()
    included_records: set[str] = set()
    for index, record in enumerate(records):
        label = f"records[{index}]"
        if not isinstance(record, dict):
            errors.append(f"{label} must be an object")
            continue
        _exact(record, {
            "record_id", "title", "locator", "source_type", "search_ids", "screening",
            "critical_appraisal", "published_on", "authors", "doi", "retrieval_metadata",
        }, label, errors)
        record_id = record.get("record_id")
        if not _text(record_id) or record_id in record_ids:
            errors.append(f"{label}.record_id must be non-empty and unique")
        else:
            record_ids.add(record_id)
        for field in ("title", "locator", "source_type"):
            if not _text(record.get(field)):
                errors.append(f"{label}.{field} is required")
        linked_searches = record.get("search_ids")
        if not _text_list(linked_searches) or any(item not in search_ids for item in linked_searches):
            errors.append(f"{label}.search_ids must reference documented searches")
        screening = record.get("screening")
        if not isinstance(screening, dict):
            errors.append(f"{label}.screening is required")
            continue
        _exact(screening, {"title_abstract", "full_text", "full_text_reason"}, f"{label}.screening", errors)
        if "published_on" in record and not _date(record.get("published_on")):
            errors.append(f"{label}.published_on must be a valid YYYY-MM-DD date")
        if "authors" in record and (
            not isinstance(record["authors"], list) or any(not _text(item) for item in record["authors"])
        ):
            errors.append(f"{label}.authors must be a string array")
        if "doi" in record and not _text(record.get("doi")):
            errors.append(f"{label}.doi is invalid")
        if "retrieval_metadata" in record and not isinstance(record["retrieval_metadata"], dict):
            errors.append(f"{label}.retrieval_metadata must be an object")
        title_decision = screening.get("title_abstract")
        full_decision = screening.get("full_text")
        if title_decision not in DECISIONS or full_decision not in DECISIONS:
            errors.append(f"{label}.screening decisions are invalid")
        if full_decision == "exclude" and not _text(screening.get("full_text_reason")):
            errors.append(f"{label}.screening.full_text_reason is required for exclusion")
        if full_decision == "include" and _text(record_id):
            included_records.add(record_id)
            appraisal = record.get("critical_appraisal")
            if not isinstance(appraisal, dict):
                errors.append(f"{label}.critical_appraisal is required for included records")
            else:
                _exact(appraisal, {"status", "tool", "findings", "rationale", "checked_by"}, f"{label}.critical_appraisal", errors)
                status = appraisal.get("status")
                if status not in APPRAISAL_STATUS:
                    errors.append(f"{label}.critical_appraisal.status is invalid")
                for field in ("tool", "rationale"):
                    if not _text(appraisal.get(field)):
                        errors.append(f"{label}.critical_appraisal.{field} is required")
                if not _text_list(appraisal.get("findings")):
                    errors.append(f"{label}.critical_appraisal.findings must be non-empty")
                if status == "human_checked" and not _text(appraisal.get("checked_by")):
                    errors.append(f"{label}.critical_appraisal.checked_by is required when human_checked")

    extractions = value.get("extractions")
    if not isinstance(extractions, list):
        errors.append("extractions must be an array")
        extractions = []
    elif len(extractions) > MAX_EXTRACTIONS:
        errors.append(f"extractions exceeds the cap of {MAX_EXTRACTIONS}")
        extractions = []
    extraction_ids: set[str] = set()
    extracted_records: set[str] = set()
    for index, extraction in enumerate(extractions):
        label = f"extractions[{index}]"
        if not isinstance(extraction, dict):
            errors.append(f"{label} must be an object")
            continue
        _exact(extraction, {
            "extraction_id", "record_id", "target", "extracted_value", "source_location",
            "applicability", "verification_status", "verified_by",
        }, label, errors)
        extraction_id = extraction.get("extraction_id")
        if not _text(extraction_id) or extraction_id in extraction_ids:
            errors.append(f"{label}.extraction_id must be non-empty and unique")
        else:
            extraction_ids.add(extraction_id)
        record_id = extraction.get("record_id")
        if record_id not in included_records:
            errors.append(f"{label}.record_id must reference an included full-text record")
        elif _text(record_id):
            extracted_records.add(record_id)
        for field in ("target", "extracted_value", "source_location", "applicability"):
            if not _text(extraction.get(field)):
                errors.append(f"{label}.{field} is required")
        status = extraction.get("verification_status")
        if status not in VERIFICATION:
            errors.append(f"{label}.verification_status is invalid")
        if status == "human_checked" and not _text(extraction.get("verified_by")):
            errors.append(f"{label}.verified_by is required when human_checked")

    missing_extractions = sorted(included_records - extracted_records)
    if missing_extractions:
        errors.append("included records without extraction: " + ", ".join(missing_extractions))

    conflicts = value.get("conflicts")
    if not isinstance(conflicts, list):
        errors.append("conflicts must be an array")
        conflicts = []
    elif len(conflicts) > MAX_CONFLICTS:
        errors.append(f"conflicts exceeds the cap of {MAX_CONFLICTS}")
        conflicts = []
    conflict_ids: set[str] = set()
    unresolved_conflicts: list[str] = []
    for index, conflict in enumerate(conflicts):
        label = f"conflicts[{index}]"
        if not isinstance(conflict, dict):
            errors.append(f"{label} must be an object")
            continue
        _exact(conflict, {"id", "topic", "record_ids", "status", "rationale"}, label, errors)
        conflict_id = conflict.get("id")
        if not _text(conflict_id) or conflict_id in conflict_ids:
            errors.append(f"{label}.id must be non-empty and unique")
        else:
            conflict_ids.add(conflict_id)
        if not _text(conflict.get("topic")) or not _text(conflict.get("rationale")):
            errors.append(f"{label} requires topic and rationale")
        linked_records = conflict.get("record_ids")
        if not isinstance(linked_records, list) or len(linked_records) < 2 or any(
            item not in record_ids for item in linked_records
        ):
            errors.append(f"{label}.record_ids must reference at least two records")
        status = conflict.get("status")
        if status not in CONFLICT_STATUS:
            errors.append(f"{label}.status is invalid")
        elif status == "unresolved" and _text(conflict_id):
            unresolved_conflicts.append(conflict_id)

    if not _text_list(value.get("limitations")):
        errors.append("limitations must be a non-empty string array")

    not_assessed_count = sum(
        1 for record in records if isinstance(record, dict)
        and isinstance(record.get("screening"), dict)
        and (record["screening"].get("title_abstract") == "not_assessed"
             or record["screening"].get("full_text") == "not_assessed")
    )
    unclear_count = sum(
        1 for record in records if isinstance(record, dict)
        and isinstance(record.get("screening"), dict)
        and (record["screening"].get("title_abstract") == "unclear"
             or record["screening"].get("full_text") == "unclear")
    )
    if allow_empty_searches:
        import_blockers = list(errors)
    else:
        import_blockers = audit(value, allow_empty_searches=True)["import_blockers"]
    if not_assessed_count:
        errors.append(f"{not_assessed_count} records remain not_assessed")
    if unclear_count:
        errors.append(f"{unclear_count} records have unclear screening decisions")
    if unresolved_conflicts:
        errors.append("unresolved conflicts: " + ", ".join(unresolved_conflicts))
    complete = not errors
    return {
        "complete": complete,
        "importable": not import_blockers,
        "status": "complete" if complete else "incomplete",
        "synthesis_sha256": sha256(json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()).hexdigest(),
        "errors": errors,
        "import_blockers": import_blockers,
        "search_count": len(searches),
        "record_count": len(records),
        "not_assessed_count": not_assessed_count,
        "included_count": len(included_records),
        "extraction_count": len(extractions),
        "unresolved_conflicts": unresolved_conflicts,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: validate_evidence_synthesis.py ARTIFACT.json", file=sys.stderr)
        return 2
    try:
        value = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        result = audit(value)
    except (OSError, json.JSONDecodeError) as error:
        result = {"complete": False, "status": "incomplete", "errors": [str(error)]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("complete") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
