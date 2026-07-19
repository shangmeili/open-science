#!/usr/bin/env python3
"""Validate an inactive, non-sensitive AI4HEOR preference proposal."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
SECRET_PATTERNS = (
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:api[_-]?key|access[_-]?token|client[_-]?secret)\s*[:=]\s*['\"]?[^\s,'\"]{12,}", re.I),
)
ROOT_KEYS = {
    "schema", "id", "status", "created_at", "scope", "proposed_rule",
    "evidence", "counterexamples", "review_condition", "expires_at",
    "contains_sensitive_data", "changes_scientific_authority",
}
EVIDENCE_KEYS = {"interaction_ref", "observed_at", "summary"}
SCOPES = {"language", "presentation", "workflow", "audit"}


def nonempty(value: object, limit: int) -> bool:
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def validate(value: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["proposal must be a JSON object"]
    if set(value) != ROOT_KEYS:
        errors.append(f"proposal fields must be exactly {sorted(ROOT_KEYS)}")
    if value.get("schema") != "ai4heor-preference-proposal/v1":
        errors.append("schema must be ai4heor-preference-proposal/v1")
    proposal_id = value.get("id")
    if not isinstance(proposal_id, str) or not ID_RE.fullmatch(proposal_id) or len(proposal_id) > 64:
        errors.append("id must be a lowercase hyphenated identifier of at most 64 characters")
    if value.get("status") != "proposal":
        errors.append("status must remain proposal")
    if not nonempty(value.get("created_at"), 64) or not str(value.get("created_at")).endswith("Z"):
        errors.append("created_at must be a UTC timestamp ending in Z")
    if value.get("scope") not in SCOPES:
        errors.append(f"scope must be one of {sorted(SCOPES)}")
    if not nonempty(value.get("proposed_rule"), 600):
        errors.append("proposed_rule is required and must be at most 600 characters")
    if not nonempty(value.get("review_condition"), 600):
        errors.append("review_condition is required and must be at most 600 characters")
    expiry = value.get("expires_at")
    if expiry is not None and (not nonempty(expiry, 64) or not str(expiry).endswith("Z")):
        errors.append("expires_at must be null or a UTC timestamp ending in Z")
    if value.get("contains_sensitive_data") is not False:
        errors.append("contains_sensitive_data must be false")
    if value.get("changes_scientific_authority") is not False:
        errors.append("changes_scientific_authority must be false")

    evidence = value.get("evidence")
    references: set[str] = set()
    if not isinstance(evidence, list) or len(evidence) < 2:
        errors.append("evidence must contain at least two independent interactions")
    else:
        for index, item in enumerate(evidence):
            if not isinstance(item, dict) or set(item) != EVIDENCE_KEYS:
                errors.append(f"evidence[{index}] fields must be exactly {sorted(EVIDENCE_KEYS)}")
                continue
            reference = item.get("interaction_ref")
            if not nonempty(reference, 300):
                errors.append(f"evidence[{index}].interaction_ref is required")
            elif reference in references:
                errors.append("evidence interaction references must be unique")
            else:
                references.add(reference)
            if not nonempty(item.get("observed_at"), 64) or not str(item.get("observed_at")).endswith("Z"):
                errors.append(f"evidence[{index}].observed_at must end in Z")
            if not nonempty(item.get("summary"), 600):
                errors.append(f"evidence[{index}].summary is required")

    counterexamples = value.get("counterexamples")
    if not isinstance(counterexamples, list) or any(not nonempty(item, 600) for item in counterexamples):
        errors.append("counterexamples must be an array of bounded text values")

    text = json.dumps(value, ensure_ascii=False)
    if any(pattern.search(text) for pattern in SECRET_PATTERNS):
        errors.append("possible secret detected in proposal")
    return errors


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: validate_preference_proposal.py <proposal.json>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    if not path.is_file() or path.is_symlink() or path.suffix != ".json":
        print(json.dumps({"valid": False, "errors": ["proposal path must be a real JSON file"]}))
        return 1
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"valid": False, "errors": [f"proposal is invalid: {exc}"]}))
        return 1
    errors = validate(value)
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
