#!/usr/bin/env python3
"""Audit portable evidence-to-input links; app-owned verification remains external."""

from __future__ import annotations

import json
import sys
from hashlib import sha256
from pathlib import Path
from typing import Any


BASE_PATHS = [
    "cycles", "cycle_length_years", "discount_rates.costs", "discount_rates.outcomes",
    "half_cycle_correction", "strategies.comparator.initial_distribution",
    "strategies.comparator.transition_matrix", "strategies.comparator.state_costs",
    "strategies.comparator.state_utilities", "strategies.intervention.initial_distribution",
    "strategies.intervention.transition_matrix", "strategies.intervention.state_costs",
    "strategies.intervention.state_utilities",
]
UNCERTAINTY = {"fixed", "range_available", "distribution_available"}


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def texts(value: Any) -> list[str] | None:
    if not isinstance(value, list) or any(not text(item) for item in value):
        return None
    return value


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def audit(plan: Any, synthesis: Any, synthesis_sha256: str) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(plan, dict) or not isinstance(synthesis, dict):
        return {"complete": False, "errors": ["plan and synthesis must be JSON objects"]}
    required = list(BASE_PATHS)
    if plan.get("willingness_to_pay") is not None:
        required.append("willingness_to_pay")
    required_set = set(required)

    mappings_value = plan.get("input_provenance")
    source_based = any(
        isinstance(mapping, dict) and bool(texts(mapping.get("source_ids")) or [])
        for mapping in (mappings_value if isinstance(mappings_value, list) else [])
    )
    if source_based:
        binding = plan.get("evidence_synthesis")
        if not isinstance(binding, dict) or binding.get("path") != "heor/evidence-synthesis.json":
            errors.append("evidence_synthesis.path must be heor/evidence-synthesis.json")
        elif binding.get("content_sha256") != synthesis_sha256:
            errors.append("evidence_synthesis.content_sha256 does not match exact synthesis bytes")

    sources = plan.get("evidence_sources")
    if not isinstance(sources, list):
        sources = []
        errors.append("evidence_sources must be an array")
    source_counts: dict[str, int] = {}
    valid_sources: set[str] = set()
    for source in sources:
        if isinstance(source, dict) and text(source.get("id")):
            source_counts[source["id"]] = source_counts.get(source["id"], 0) + 1
    for source in sources:
        if not isinstance(source, dict) or not text(source.get("id")):
            continue
        locator = text(source.get("url")) or text(source.get("local_path"))
        snapshot = not source.get("local_path") or (
            isinstance(source.get("content_sha256"), str)
            and len(source["content_sha256"]) == 64
            and all(char in "0123456789abcdef" for char in source["content_sha256"])
        )
        if (source_counts[source["id"]] == 1 and text(source.get("title"))
                and text(source.get("source_type")) and text(source.get("accessed_on"))
                and locator and snapshot):
            valid_sources.add(source["id"])

    assumptions = plan.get("assumptions") if isinstance(plan.get("assumptions"), list) else []
    assumption_status = {
        item["id"]: item.get("status") for item in assumptions
        if isinstance(item, dict) and text(item.get("id"))
        and text(item.get("statement")) and text(item.get("reason"))
    }
    unresolved = sorted(
        item.get("id", "unknown") for item in assumptions
        if isinstance(item, dict) and item.get("status") == "unresolved"
    )

    records = synthesis.get("records") if isinstance(synthesis.get("records"), list) else []
    included = {
        item.get("record_id") for item in records if isinstance(item, dict)
        and isinstance(item.get("screening"), dict)
        and item["screening"].get("full_text") == "include"
    }
    extraction_index: dict[str, dict[str, Any]] = {}
    for item in synthesis.get("extractions", []):
        if (isinstance(item, dict) and text(item.get("extraction_id"))
                and item.get("record_id") in included
                and item.get("verification_status") != "conflict"):
            extraction_index[item["extraction_id"]] = item

    mappings = plan.get("input_provenance")
    if not isinstance(mappings, list):
        mappings = []
        errors.append("input_provenance must be an array")
    seen: set[str] = set()
    covered: set[str] = set()
    selected: set[str] = set()
    invalid: list[str] = []
    for mapping in mappings:
        if not isinstance(mapping, dict) or not text(mapping.get("path")):
            invalid.append("mapping omitted path")
            continue
        path = mapping["path"]
        reasons: list[str] = []
        if path not in required_set:
            reasons.append("path is not required")
        if path in seen:
            reasons.append("path is duplicated")
        seen.add(path)
        for field in ("unit", "jurisdiction", "selection_rationale"):
            if not text(mapping.get(field)):
                reasons.append(f"{field} is missing")
        if mapping.get("uncertainty_status") not in UNCERTAINTY:
            reasons.append("uncertainty_status is invalid")
        if (path.endswith("state_costs") or path == "willingness_to_pay") and not (
            isinstance(mapping.get("price_year"), int) and 1900 <= mapping["price_year"] <= 3000
        ):
            reasons.append("price_year is missing")
        source_ids = texts(mapping.get("source_ids")) or []
        assumption_ids = texts(mapping.get("assumption_ids")) or []
        extraction_ids = texts(mapping.get("extraction_ids")) or []
        if not source_ids and not assumption_ids:
            reasons.append("no evidence source or proposed assumption is linked")
        if any(source_id not in valid_sources for source_id in source_ids):
            reasons.append("source metadata is incomplete")
        if any(assumption_status.get(item) != "proposed" for item in assumption_ids):
            reasons.append("assumption is absent or not proposed")
        if source_ids:
            if not extraction_ids:
                reasons.append("source-based input has no extraction_ids")
            if len(extraction_ids) != len(set(extraction_ids)):
                reasons.append("extraction_ids are duplicated")
            for extraction_id in extraction_ids:
                selected.add(extraction_id)
                extraction = extraction_index.get(extraction_id)
                if not extraction:
                    reasons.append(f"{extraction_id} is absent, conflicting, or ineligible")
                elif extraction.get("target") != path:
                    reasons.append(f"{extraction_id} targets {extraction.get('target')}")
                elif extraction.get("record_id") not in source_ids:
                    reasons.append(f"{extraction_id} record_id is not a linked source")
        elif extraction_ids:
            reasons.append("assumption-only mapping must not claim extraction_ids")
        if reasons:
            invalid.append(f"{path}: {'; '.join(reasons)}")
        else:
            covered.add(path)

    unsupported = [path for path in required if path not in covered]
    complete = not errors and not invalid and not unresolved and not unsupported
    return {
        "complete": complete,
        "status": "structurally_ready_for_app_review" if complete else "incomplete",
        "required_inputs": len(required),
        "covered_inputs": len(covered),
        "selected_extraction_ids": sorted(selected),
        "unsupported_inputs": unsupported,
        "unresolved_assumptions": unresolved,
        "invalid_mappings": invalid,
        "errors": errors,
        "human_verification_checked": False,
        "required_app_reviewers_per_extraction": 2,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: validate_input_provenance.py ANALYSIS_PLAN.json EVIDENCE_SYNTHESIS.json", file=sys.stderr)
        return 2
    try:
        plan_path, synthesis_path = Path(argv[1]), Path(argv[2])
        plan = json.loads(plan_path.read_bytes())
        synthesis = json.loads(synthesis_path.read_bytes())
        result = audit(plan, synthesis, digest(synthesis_path))
    except (OSError, json.JSONDecodeError) as error:
        result = {"complete": False, "status": "incomplete", "errors": [str(error)]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("complete") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
