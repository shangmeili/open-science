#!/usr/bin/env python3
"""Validate an ordered collection of AI4HEOR survival reviews."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any


SCHEMA_FIELDS = {"schema_version", "analysis_id", "reviews"}
ENTRY_FIELDS = {"target_path", "review_path", "review_sha256"}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REVIEW_PATH = re.compile(
    r"^heor/survival-extrapolation-reviews/[a-z][a-z0-9_-]{0,63}\.json$"
)
MAX_REVIEW_BYTES = 10 * 1024 * 1024
COLLECTION_PATH = "heor/survival-extrapolation-reviews.json"


def _load_review_validator():
    path = Path(__file__).with_name("validate_survival_extrapolation_review.py")
    spec = importlib.util.spec_from_file_location(
        "ai4heor_validate_survival_extrapolation_review", path
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("survival review validator is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


single_review = _load_review_validator()


def exact_object(value: Any, fields: set[str], label: str, errors: list[str]) -> bool:
    if not isinstance(value, dict) or set(value) != fields:
        errors.append(f"{label} fields are not the exact supported contract")
        return False
    return True


def read_capped(path: Path, label: str, errors: list[str]) -> bytes | None:
    try:
        if not path.is_file() or path.stat().st_size > MAX_REVIEW_BYTES:
            errors.append(f"{label} is not a reviewable artifact")
            return None
        return path.read_bytes()
    except OSError as error:
        errors.append(f"{label} is unavailable: {error}")
        return None


def audit(
    value: Any,
    workspace: Path,
    analysis_plan: Any,
    collection_path: Path | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    targets = single_review.survival_targets(analysis_plan)
    bindings: list[dict[str, str]] = []
    target_results: list[dict[str, Any]] = []
    root = workspace.resolve()

    if not exact_object(value, SCHEMA_FIELDS, "collection", errors):
        return {
            "complete": False,
            "errors": errors,
            "target_count": len(targets),
            "review_count": 0,
            "artifact_bindings": bindings,
            "targets": target_results,
        }
    if value["schema_version"] != "0.1.0":
        errors.append("schema_version must be 0.1.0")
    if value["analysis_id"] != analysis_plan.get("analysis_id"):
        errors.append("analysis_id must match the current analysis plan")
    if not 2 <= len(targets) <= 32:
        errors.append("the collection requires 2-32 parametric survival targets")

    reviews = value["reviews"]
    if not isinstance(reviews, list):
        errors.append("reviews must be an array")
        reviews = []
    if len(reviews) != len(targets):
        errors.append(
            f"reviews must contain exactly {len(targets)} entries in plan-target order"
        )

    if collection_path is not None:
        try:
            resolved_collection = collection_path.resolve()
            if resolved_collection.is_relative_to(root) and resolved_collection.is_file():
                relative_collection = resolved_collection.relative_to(root).as_posix()
                if relative_collection != COLLECTION_PATH:
                    errors.append(f"collection path must be {COLLECTION_PATH}")
                bindings.append({
                    "path": relative_collection,
                    "sha256": hashlib.sha256(resolved_collection.read_bytes()).hexdigest(),
                })
            else:
                errors.append("collection path must be a file inside the workspace")
        except OSError as error:
            errors.append(f"collection path is unavailable: {error}")

    seen_targets: set[str] = set()
    seen_paths: set[str] = set()
    for index, (target_path, selected_family) in enumerate(targets):
        if index >= len(reviews):
            errors.append(f"missing collection review for target {target_path}")
            continue
        entry = reviews[index]
        label = f"reviews[{index}]"
        if not exact_object(entry, ENTRY_FIELDS, label, errors):
            continue
        declared_target = entry["target_path"]
        review_path = entry["review_path"]
        declared_hash = entry["review_sha256"]
        if declared_target != target_path:
            errors.append(
                f"{label}.target_path must equal {target_path} in plan-target order"
            )
        if not isinstance(declared_target, str) or declared_target in seen_targets:
            errors.append(f"{label}.target_path must be unique")
        elif declared_target:
            seen_targets.add(declared_target)
        if not isinstance(review_path, str) or not REVIEW_PATH.fullmatch(review_path):
            errors.append(
                f"{label}.review_path must be one safe JSON file in "
                "heor/survival-extrapolation-reviews"
            )
            continue
        if review_path in seen_paths:
            errors.append(f"{label}.review_path must be unique")
            continue
        seen_paths.add(review_path)
        if not isinstance(declared_hash, str) or not SHA256.fullmatch(declared_hash):
            errors.append(f"{label}.review_sha256 must be lowercase SHA-256")
            continue

        resolved = (root / review_path).resolve()
        if not resolved.is_relative_to(root):
            errors.append(f"{label}.review_path must stay inside the workspace")
            continue
        raw = read_capped(resolved, review_path, errors)
        if raw is None:
            continue
        actual_hash = hashlib.sha256(raw).hexdigest()
        bindings.append({"path": review_path, "sha256": actual_hash})
        if actual_hash != declared_hash:
            errors.append(f"{label}.review_sha256 does not match {review_path}")
        try:
            review = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            errors.append(f"{review_path} is invalid JSON: {error}")
            continue

        target_plan = {
            "analysis_id": analysis_plan.get("analysis_id"),
            "input_provenance": [{
                "path": target_path,
                "derivation": {"transformation": {
                    "operation": "parametric_survival_to_transition_schedule",
                    "distribution": selected_family,
                }},
            }],
        }
        result = single_review.audit(review, root, target_plan)
        target_results.append({
            "target_path": target_path,
            "review_path": review_path,
            "complete": result["complete"],
            "errors": result["errors"],
        })
        errors.extend(f"{target_path}: {error}" for error in result["errors"])

    if len(reviews) > len(targets):
        errors.append("collection contains reviews for undeclared targets")
    return {
        "complete": not errors and len(target_results) == len(targets),
        "errors": errors,
        "target_count": len(targets),
        "review_count": len(reviews),
        "artifact_bindings": bindings,
        "targets": target_results,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("collection", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--analysis-plan", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace.resolve()
    collection_path = args.collection if args.collection.is_absolute() else root / args.collection
    plan_path = args.analysis_plan if args.analysis_plan.is_absolute() else root / args.analysis_plan
    value = json.loads(collection_path.read_text(encoding="utf-8"))
    analysis_plan = json.loads(plan_path.read_text(encoding="utf-8"))
    result = audit(value, root, analysis_plan, collection_path)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
