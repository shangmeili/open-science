#!/usr/bin/env python3
"""Portable preflight for the AI4HEOR evidence-search request contract."""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path
from typing import Any


TOP_LEVEL = {
    "schema_version",
    "request_id",
    "status",
    "purpose",
    "query",
    "sources",
    "max_results_per_source",
    "date_from",
    "date_to",
    "data_egress",
    "limitations",
}
EGRESS_FIELDS = {"contains_sensitive_data", "fields", "justification"}
SOURCES = {"pubmed", "clinicaltrials"}
DISCLOSED_FIELDS = {"query", "date_from", "date_to"}


def _text(value: Any, *, limit: int | None = None) -> bool:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        return False
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        return False
    return limit is None or len(value) <= limit


def _date(value: Any) -> dt.date | None:
    if value is None:
        return None
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError
    return dt.date.fromisoformat(value)


def audit(value: Any) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return {"complete": False, "status": "incomplete", "errors": ["request must be a JSON object"]}
    unknown = sorted(set(value) - TOP_LEVEL)
    errors.extend(f"unsupported top-level field: {field}" for field in unknown)
    if value.get("schema_version") != "0.1.0":
        errors.append("schema_version must be 0.1.0")
    request_id = value.get("request_id")
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", request_id):
        errors.append("request_id is invalid")
    if value.get("status") != "ready_for_human_review":
        errors.append("status must be ready_for_human_review")
    if not _text(value.get("purpose")):
        errors.append("purpose is required")
    if not _text(value.get("query"), limit=500):
        errors.append("query must contain 1-500 characters without control characters")
    sources = value.get("sources")
    if (
        not isinstance(sources, list)
        or not sources
        or not all(isinstance(source, str) for source in sources)
        or len(set(sources)) != len(sources)
        or not set(sources).issubset(SOURCES)
    ):
        errors.append("sources must be a unique non-empty public-source subset")
        sources = []
    maximum = value.get("max_results_per_source")
    if not isinstance(maximum, int) or isinstance(maximum, bool) or not 1 <= maximum <= 50:
        errors.append("max_results_per_source must be an integer from 1 to 50")
    parsed_dates: dict[str, dt.date | None] = {}
    for field in ("date_from", "date_to"):
        try:
            parsed_dates[field] = _date(value.get(field))
        except (TypeError, ValueError):
            parsed_dates[field] = None
            errors.append(f"{field} must be a valid YYYY-MM-DD date or null")
    if (
        parsed_dates.get("date_from") is not None
        and parsed_dates.get("date_to") is not None
        and parsed_dates["date_from"] > parsed_dates["date_to"]
    ):
        errors.append("date_from must not be after date_to")
    egress = value.get("data_egress")
    if not isinstance(egress, dict):
        errors.append("data_egress declaration is required")
    else:
        errors.extend(
            f"unsupported data_egress field: {field}"
            for field in sorted(set(egress) - EGRESS_FIELDS)
        )
        if egress.get("contains_sensitive_data") is not False:
            errors.append("data_egress.contains_sensitive_data must be false")
        fields = egress.get("fields")
        if (
            not isinstance(fields, list)
            or not all(isinstance(field, str) for field in fields)
            or set(fields) != DISCLOSED_FIELDS
            or len(fields) != len(DISCLOSED_FIELDS)
        ):
            errors.append("data_egress.fields must disclose query, date_from, and date_to")
        if not _text(egress.get("justification")):
            errors.append("data_egress.justification is required")
    limitations = value.get("limitations")
    if not isinstance(limitations, list) or not limitations or not all(_text(item) for item in limitations):
        errors.append("limitations must be a non-empty string array")
    return {
        "complete": not errors,
        "status": "complete" if not errors else "incomplete",
        "request_id": request_id if isinstance(request_id, str) else "",
        "sources": sources,
        "errors": errors,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: validate_evidence_search_request.py REQUEST.json", file=sys.stderr)
        return 2
    path = Path(argv[1])
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        print(json.dumps({"complete": False, "errors": [str(error)]}, ensure_ascii=False, indent=2))
        return 1
    result = audit(value)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
