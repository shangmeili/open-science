#!/usr/bin/env python3
"""Portable validator for an AI4HEOR independent model-validation report."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath


CAP_BYTES = 5 * 1024 * 1024
SHA256 = re.compile(r"^[a-f0-9]{64}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
BINDINGS = {
    "analysis_plan": "heor/analysis-plan.json",
    "conceptual_model": "heor/conceptual-model.json",
    "uncertainty_plan": "heor/uncertainty-plan.json",
    "budget_impact_plan": "heor/budget-impact-plan.json",
}
SCOPES = {"cost_effectiveness", "budget_impact", "shared"}
DOMAINS = {
    "face_validity",
    "input_data",
    "technical_verification",
    "cross_validity",
    "external_validity",
    "predictive_validity",
}
COMPONENTS = {
    "conceptual_model",
    "input_calculations",
    "event_state_calculations",
    "result_calculations",
    "uncertainty_calculations",
    "overall_checks",
    "model_outcomes",
}
METHODS = {
    "expert_review",
    "source_reconciliation",
    "black_box",
    "white_box",
    "replication",
    "cross_model_comparison",
    "external_data_comparison",
    "prospective_comparison",
    "other",
}
EVIDENCE_TYPES = {
    "expert_review_minutes",
    "test_log",
    "replication_output",
    "cross_model_output",
    "external_dataset_extract",
    "search_record",
    "other",
}


def text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def objects(value: object) -> list[dict]:
    return value if isinstance(value, list) and all(isinstance(item, dict) for item in value) else []


def strings(value: object, *, nonempty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (bool(value) or not nonempty)
        and all(text(item) for item in value)
        and len(value) == len(set(value))
    )


def unique_ids(items: list[dict], field: str = "id") -> bool:
    values = [item.get(field) for item in items]
    return all(text(item) for item in values) and len(values) == len(set(values))


def load_object(path: Path) -> tuple[dict, bytes]:
    raw = path.read_bytes()
    if len(raw) > CAP_BYTES:
        raise ValueError(f"{path} exceeds the 5 MiB review cap")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value, raw


def workspace_file(workspace: Path, relative: str) -> Path:
    posix = PurePosixPath(relative)
    if (
        posix.is_absolute()
        or "\\" in relative
        or not posix.parts
        or any(part in {"", ".", ".."} for part in posix.parts)
    ):
        raise ValueError(f"unsafe workspace path: {relative}")
    root = workspace.resolve(strict=True)
    target = (root / Path(*posix.parts)).resolve(strict=True)
    if root not in target.parents:
        raise ValueError(f"workspace path escapes the project: {relative}")
    if not target.is_file() or target.stat().st_size > CAP_BYTES:
        raise ValueError(f"not a bounded validation artifact: {relative}")
    return target


def method_matches(domain: str, method: str) -> bool:
    expected = {
        "face_validity": {"expert_review"},
        "input_data": {"source_reconciliation", "replication"},
        "technical_verification": {"black_box", "white_box", "replication"},
        "cross_validity": {"cross_model_comparison"},
        "external_validity": {"external_data_comparison"},
        "predictive_validity": {"prospective_comparison"},
    }
    return method in expected.get(domain, set())


def required_coverage() -> list[tuple[str, str, str, str | None, set[str]]]:
    passed = {"passed"}
    documented = {"passed", "not_feasible"}
    result = [
        ("cost-effectiveness face validity", "cost_effectiveness", "face_validity", None, passed),
        ("cost-effectiveness input validation", "cost_effectiveness", "input_data", None, passed),
        ("cost-effectiveness external validity", "cost_effectiveness", "external_validity", None, passed),
        ("budget-impact face validity", "budget_impact", "face_validity", None, passed),
        ("budget-impact input validation", "budget_impact", "input_data", None, passed),
        ("budget-impact external validity", "budget_impact", "external_validity", None, passed),
    ]
    for component in (
        "input_calculations",
        "event_state_calculations",
        "result_calculations",
        "uncertainty_calculations",
        "overall_checks",
    ):
        result.append((f"cost-effectiveness technical {component}", "cost_effectiveness", "technical_verification", component, passed))
    for component in (
        "input_calculations",
        "result_calculations",
        "uncertainty_calculations",
        "overall_checks",
    ):
        result.append((f"budget-impact technical {component}", "budget_impact", "technical_verification", component, passed))
    result.extend([
        ("cost-effectiveness cross validity", "cost_effectiveness", "cross_validity", None, documented),
        ("cost-effectiveness predictive validity", "cost_effectiveness", "predictive_validity", None, documented),
        ("budget-impact predictive validity", "budget_impact", "predictive_validity", None, documented),
    ])
    return result


def audit(report_path: Path, workspace: Path) -> dict:
    report, report_raw = load_object(report_path)
    errors: list[str] = []
    invalid_evidence: list[str] = []

    if report.get("schema_version") != "0.1.0":
        errors.append("schema_version must be 0.1.0")
    for field in ("validation_id", "analysis_id", "intended_use", "developer_label"):
        if not text(report.get(field)):
            errors.append(f"{field} is required")
    if report.get("status") != "ready_for_independent_review":
        errors.append("status must be ready_for_independent_review")

    bindings = report.get("model_bindings") or {}
    binding_hashes: dict[str, str] = {}
    for key, expected_path in BINDINGS.items():
        binding = bindings.get(key) or {}
        if binding.get("path") != expected_path:
            errors.append(f"model_bindings.{key}.path must be {expected_path}")
            continue
        try:
            value, raw = load_object(workspace_file(workspace, expected_path))
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(str(error))
            continue
        expected_hash = hashlib.sha256(raw).hexdigest()
        binding_hashes[key] = expected_hash
        if binding.get("content_sha256") != expected_hash or not SHA256.fullmatch(str(binding.get("content_sha256", ""))):
            errors.append(f"model_bindings.{key}.content_sha256 does not match current bytes")
        if value.get("analysis_id") != report.get("analysis_id"):
            errors.append(f"{expected_path} analysis_id does not match the validation report")

    reviewer = report.get("reviewer") or {}
    for field in ("label", "organization", "independence_statement", "conflict_statement"):
        if not text(reviewer.get(field)):
            errors.append(f"reviewer.{field} is required")
    if reviewer.get("role") != "independent_reviewer":
        errors.append("reviewer.role must be independent_reviewer")
    if reviewer.get("declared_independent") is not True:
        errors.append("reviewer.declared_independent must be true")
    if not DATE.fullmatch(str(reviewer.get("reviewed_on", ""))):
        errors.append("reviewer.reviewed_on must be YYYY-MM-DD")
    if text(reviewer.get("label")) and text(report.get("developer_label")) and reviewer["label"].strip().casefold() == report["developer_label"].strip().casefold():
        errors.append("independent reviewer must differ from the developer")

    evidence = objects(report.get("evidence_artifacts"))
    if not 1 <= len(evidence) <= 128 or not unique_ids(evidence):
        errors.append("evidence_artifacts must contain 1-128 entries with unique ids")
    evidence_ids: set[str] = set()
    for index, item in enumerate(evidence):
        if not all(text(item.get(field)) for field in ("id", "path", "description")):
            invalid_evidence.append(f"evidence_artifacts[{index}] metadata is incomplete")
            continue
        evidence_ids.add(item["id"])
        if item.get("evidence_type") not in EVIDENCE_TYPES:
            invalid_evidence.append(f"evidence_artifacts[{index}].evidence_type is invalid")
        relative = item["path"]
        if not relative.startswith("heor/validation-evidence/"):
            invalid_evidence.append(f"evidence_artifacts[{index}].path must stay under heor/validation-evidence/")
            continue
        try:
            raw = workspace_file(workspace, relative).read_bytes()
        except (OSError, ValueError) as error:
            invalid_evidence.append(str(error))
            continue
        if item.get("content_sha256") != hashlib.sha256(raw).hexdigest() or not SHA256.fullmatch(str(item.get("content_sha256", ""))):
            invalid_evidence.append(f"evidence_artifacts[{index}].content_sha256 does not match current bytes")
    errors.extend(invalid_evidence)

    issues = objects(report.get("issues"))
    if not isinstance(report.get("issues"), list) or len(issues) > 128 or not unique_ids(issues):
        errors.append("issues must contain at most 128 entries with unique ids")
    issue_status: dict[str, str] = {}
    issue_severity: dict[str, str] = {}
    for index, issue in enumerate(issues):
        if not text(issue.get("description")) or issue.get("severity") not in {"blocker", "major", "minor"} or issue.get("status") not in {"open", "resolved"}:
            errors.append(f"issues[{index}] metadata is invalid")
        if not strings(issue.get("evidence_ids"), nonempty=True) or not set(issue.get("evidence_ids") or []).issubset(evidence_ids):
            errors.append(f"issues[{index}].evidence_ids are invalid")
        if issue.get("status") == "resolved" and (not text(issue.get("root_cause")) or not text(issue.get("resolution"))):
            errors.append(f"issues[{index}] resolved issue requires root_cause and resolution")
        if text(issue.get("id")):
            issue_status[issue["id"]] = issue.get("status", "")
            issue_severity[issue["id"]] = issue.get("severity", "")

    checks = objects(report.get("checks"))
    if not 1 <= len(checks) <= 256 or not unique_ids(checks):
        errors.append("checks must contain 1-256 entries with unique ids")
    for index, check in enumerate(checks):
        for field in ("description", "expected", "observed", "rationale"):
            if not text(check.get(field)):
                errors.append(f"checks[{index}].{field} is required")
        if check.get("scope") not in SCOPES or check.get("domain") not in DOMAINS or check.get("component") not in COMPONENTS:
            errors.append(f"checks[{index}] scope, domain, or component is invalid")
        if check.get("method") not in METHODS or not method_matches(str(check.get("domain")), str(check.get("method"))):
            errors.append(f"checks[{index}].method is inconsistent with its domain")
        if check.get("status") not in {"passed", "failed", "inconclusive", "not_feasible"}:
            errors.append(f"checks[{index}].status is invalid")
        if check.get("performed_by") not in {"independent_reviewer", "developer", "automated_test"}:
            errors.append(f"checks[{index}].performed_by is invalid")
        if not strings(check.get("evidence_ids"), nonempty=True) or not set(check.get("evidence_ids") or []).issubset(evidence_ids):
            errors.append(f"checks[{index}].evidence_ids are invalid")
        linked_issues = check.get("issue_ids") or []
        if not strings(linked_issues) or not set(linked_issues).issubset(issue_status):
            errors.append(f"checks[{index}].issue_ids are invalid")
        if check.get("status") in {"failed", "inconclusive"} and not linked_issues:
            errors.append(f"checks[{index}] failed or inconclusive check must link an issue")
        if check.get("status") == "not_feasible" and check.get("domain") not in {"cross_validity", "predictive_validity"}:
            errors.append(f"checks[{index}] not_feasible is allowed only for cross or predictive validity")

    missing_coverage: list[str] = []
    for label, scope, domain, component, statuses in required_coverage():
        covered = any(
            check.get("performed_by") == "independent_reviewer"
            and check.get("scope") in {scope, "shared"}
            and check.get("domain") == domain
            and (component is None or check.get("component") == component)
            and check.get("status") in statuses
            for check in checks
        )
        if not covered:
            missing_coverage.append(label)
    if missing_coverage:
        errors.append("missing independent validation coverage: " + ", ".join(missing_coverage))

    limitations = report.get("limitations")
    if not strings(limitations, nonempty=True):
        errors.append("limitations must be a non-empty unique string array")
    conclusion = report.get("conclusion") or {}
    recommendation = conclusion.get("recommendation")
    if recommendation not in {"approve_for_intended_use", "approve_with_limitations", "do_not_approve"}:
        errors.append("conclusion.recommendation must be a final reviewer recommendation")
    if not text(conclusion.get("rationale")) or not strings(conclusion.get("residual_uncertainty"), nonempty=True):
        errors.append("conclusion requires rationale and residual_uncertainty")

    open_blocking = sum(
        status == "open" and issue_severity.get(issue_id) in {"blocker", "major"}
        for issue_id, status in issue_status.items()
    )
    open_minor = sum(
        status == "open" and issue_severity.get(issue_id) == "minor"
        for issue_id, status in issue_status.items()
    )
    if recommendation == "approve_for_intended_use" and (open_blocking or open_minor):
        errors.append("approve_for_intended_use cannot retain open issues")
    if recommendation == "approve_with_limitations" and open_blocking:
        errors.append("approve_with_limitations cannot retain open blocker or major issues")

    complete = not errors
    approvable = complete and recommendation in {"approve_for_intended_use", "approve_with_limitations"}
    return {
        "complete": complete,
        "approvable": approvable,
        "status": "complete" if complete else "incomplete",
        "validation_id": str(report.get("validation_id", "")),
        "analysis_id": str(report.get("analysis_id", "")),
        "validation_sha256": hashlib.sha256(report_raw).hexdigest(),
        "reviewer_label": str(reviewer.get("label", "")),
        "recommendation": str(recommendation or "pending"),
        "evidence_count": len(evidence),
        "check_count": len(checks),
        "required_coverage_count": len(required_coverage()),
        "covered_requirement_count": len(required_coverage()) - len(missing_coverage),
        "issue_count": len(issues),
        "open_blocking_issue_count": open_blocking,
        "open_minor_issue_count": open_minor,
        "binding_hashes": binding_hashes,
        "invalid_evidence": invalid_evidence,
        "missing_coverage": missing_coverage,
        "errors": errors,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: validate_model_validation.py MODEL_VALIDATION_JSON WORKSPACE", file=sys.stderr)
        return 2
    try:
        result = audit(Path(argv[1]), Path(argv[2]))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"invalid: {error}", file=sys.stderr)
        return 1
    if not result["complete"]:
        for error in result["errors"]:
            print(f"invalid: {error}", file=sys.stderr)
        return 1
    suffix = "approvable" if result["approvable"] else "not approvable"
    print(f"valid ({suffix})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
