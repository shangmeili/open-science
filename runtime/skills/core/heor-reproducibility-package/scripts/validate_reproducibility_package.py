#!/usr/bin/env python3
"""Portable fail-closed validator for an AI4HEOR reproducibility package."""

from __future__ import annotations

import hashlib
import json
import platform
import re
import sys
from pathlib import Path, PurePosixPath


CAP_BYTES = 25 * 1024 * 1024
SHA256 = re.compile(r"^[a-f0-9]{64}$")
SAFE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
AVAILABILITY_ID = re.compile(r"^[a-z][a-z0-9_-]{0,76}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
REPORT_PATH = "heor/report-package.json"
REPRO_PATH = "heor/reproducibility-package.json"
MARKOV_REQUIRED_CLAIMS = {
    ("CHEERS-2022", "23-summary-results"): "cost_effectiveness",
    ("CHEERS-2022", "24-uncertainty-effects"): "uncertainty",
    ("CHEERS-2022", "26-findings-limitations-generalisability"): "cost_effectiveness",
    ("ISPOR-BIA-GP-II-2014", "bia-8-period-disaggregated-results"): "budget_impact",
    ("ISPOR-BIA-GP-II-2014", "bia-9-cumulative-impact"): "budget_impact",
    ("ISPOR-BIA-GP-II-2014", "bia-10-uncertainty-scenarios"): "budget_impact",
    ("ISPOR-BIA-GP-II-2014", "bia-12-limitations-reproducibility"): "budget_impact",
}
DECISION_TREE_REQUIRED_CLAIMS = {
    ("CHEERS-2022", "23-summary-results"): "cost_effectiveness",
    ("CHEERS-2022", "24-uncertainty-effects"): "uncertainty",
    ("CHEERS-2022", "26-findings-limitations-generalisability"): "cost_effectiveness",
}
# Backward-compatible public name used by the schema 0.1 Markov fixtures.
REQUIRED_CLAIMS = MARKOV_REQUIRED_CLAIMS
ROLES = {"release_manifest", "report", "method", "input", "result", "evidence"}
AVAILABILITY = {
    "included_workspace", "public_locator", "available_on_request",
    "restricted_not_shared", "unavailable",
}
LICENSES = {"open", "permission_required", "restricted", "unknown", "not_applicable"}


def text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def objects(value: object) -> list[dict]:
    return value if isinstance(value, list) and all(isinstance(v, dict) for v in value) else []


def strings(value: object) -> list[str]:
    return value if isinstance(value, list) and all(text(v) for v in value) else []


def workspace_file(workspace: Path, relative: str) -> Path:
    pure = PurePosixPath(relative)
    if pure.is_absolute() or not pure.parts or any(part in {"", ".", ".."} for part in pure.parts):
        raise ValueError(f"unsafe workspace path: {relative}")
    root = workspace.resolve(strict=True)
    path = root.joinpath(*pure.parts)
    if path.is_symlink() or any(parent.is_symlink() for parent in path.parents if parent != root):
        raise ValueError(f"workspace path contains a symlink: {relative}")
    resolved = path.resolve(strict=True)
    if resolved != root and root not in resolved.parents:
        raise ValueError(f"workspace path escapes project: {relative}")
    return resolved


def read_bytes(workspace: Path, relative: str) -> bytes:
    path = workspace_file(workspace, relative)
    if not path.is_file() or path.stat().st_size > CAP_BYTES:
        raise ValueError(f"workspace artifact is missing or exceeds cap: {relative}")
    return path.read_bytes()


def load_object(workspace: Path, relative: str) -> tuple[dict, bytes]:
    raw = read_bytes(workspace, relative)
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError(f"{relative} must contain a JSON object")
    return value, raw


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def expected_role(key: str) -> str:
    if key == "report_package":
        return "release_manifest"
    if key == "report_document":
        return "report"
    if key == "evidence_synthesis":
        return "evidence"
    if key.endswith("_result"):
        return "result"
    if key in {
        "survival_curve_materializations", "treatment_effect_duration",
        "cost_input_normalization", "utility_inputs", "event_disutilities",
    }:
        return "input"
    return "method"


def is_decision_tree(report: dict) -> bool:
    return report.get("analysis_type") == "decision_tree"


def required_claims(report: dict) -> dict[tuple[str, str], str]:
    return DECISION_TREE_REQUIRED_CLAIMS if is_decision_tree(report) else MARKOV_REQUIRED_CLAIMS


def expected_artifacts(report: dict, report_raw: bytes, analysis: dict) -> dict[str, tuple[str, str, str]]:
    result = {"report_package": (REPORT_PATH, digest(report_raw), "release_manifest")}
    bindings = report.get("bindings")
    if not isinstance(bindings, dict):
        raise ValueError("report package bindings must be an object")
    for key, binding in bindings.items():
        if not isinstance(binding, dict) or not text(binding.get("path")) or not SHA256.fullmatch(str(binding.get("content_sha256", ""))):
            raise ValueError(f"report binding is invalid: {key}")
        result[key] = (binding["path"], binding["content_sha256"], expected_role(key))
    evidence = analysis.get("evidence_synthesis")
    if isinstance(evidence, dict):
        path = evidence.get("path")
        sha = evidence.get("content_sha256")
        if path != "heor/evidence-synthesis.json" or not SHA256.fullmatch(str(sha or "")):
            raise ValueError("analysis evidence_synthesis binding is invalid")
        result["evidence_synthesis"] = (path, sha, "evidence")
    return result


def command_specs(report: dict, loaded: dict[str, dict]) -> list[dict]:
    bindings = report["bindings"]
    if is_decision_tree(report):
        base_args = ["python", "-m", "heor_core", bindings["decision_tree_plan"]["path"]]
        return [
            {
                "execution_id": "cost_effectiveness",
                "engine_version": loaded["decision_tree_result"].get("engine_version"),
                "command": base_args,
                "input_artifact_ids": ["decision_tree_plan"],
                "output_artifact_id": "decision_tree_result",
                "determinism": "byte_replay_expected",
            },
            {
                "execution_id": "uncertainty",
                "engine_version": loaded["decision_tree_uncertainty_result"].get("engine_version"),
                "command": base_args + [
                    "--decision-tree-uncertainty-plan",
                    bindings["decision_tree_uncertainty_plan"]["path"],
                ],
                "input_artifact_ids": [
                    "decision_tree_plan", "decision_tree_uncertainty_plan",
                ],
                "output_artifact_id": "decision_tree_uncertainty_result",
                "determinism": "byte_replay_expected",
            },
        ]
    psm = "partitioned_survival_result" in bindings
    base_id = "partitioned_survival_result" if psm else "base_case_result"
    base_args = ["python", "-m", "heor_core", "heor/analysis-plan.json"]
    base_inputs = ["analysis_plan"]
    if psm:
        pairs = [
            ("--partitioned-survival-plan", "partitioned_survival_plan"),
            ("--survival-curve-materializations", "survival_curve_materializations"),
            ("--treatment-effect-duration", "treatment_effect_duration"),
            ("--cost-input-normalization", "cost_input_normalization"),
            ("--utility-inputs", "utility_inputs"),
            ("--event-disutilities", "event_disutilities"),
        ]
        for flag, key in pairs:
            base_args.extend([flag, bindings[key]["path"]])
            base_inputs.append(key)
    uncertainty_args = base_args + ["--uncertainty-plan", bindings["uncertainty_plan"]["path"]]
    uncertainty_inputs = base_inputs + ["uncertainty_plan"]
    uncertainty_plan = loaded["uncertainty_plan"]
    if uncertainty_plan.get("schema_version") == "0.14.0":
        uncertainty_args.extend([
            "--joint-survival-uncertainty-manifest", "heor/joint-survival-uncertainty.json",
            "--joint-survival-draws", "heor/joint-survival-draws.jsonl",
        ])
    return [
        {
            "execution_id": "cost_effectiveness",
            "engine_version": loaded[base_id].get("engine_version"),
            "command": base_args,
            "input_artifact_ids": base_inputs,
            "output_artifact_id": base_id,
            "determinism": "byte_replay_expected",
        },
        {
            "execution_id": "uncertainty",
            "engine_version": loaded["uncertainty_result"].get("engine_version"),
            "command": uncertainty_args,
            "input_artifact_ids": uncertainty_inputs,
            "output_artifact_id": "uncertainty_result",
            "determinism": "byte_replay_expected",
        },
        {
            "execution_id": "budget_impact",
            "engine_version": loaded["budget_impact_result"].get("engine_version"),
            "command": [
                "python", "-m", "heor_core", "heor/analysis-plan.json",
                "--budget-impact-plan", bindings["budget_impact_plan"]["path"],
            ],
            "input_artifact_ids": ["analysis_plan", "budget_impact_plan"],
            "output_artifact_id": "budget_impact_result",
            "determinism": "byte_replay_expected",
        },
    ]


def _collect_string_array_values(value: object, key: str, found: set[str]) -> None:
    if isinstance(value, dict):
        for field, child in value.items():
            if field == key:
                if not isinstance(child, list) or not all(text(item) for item in child):
                    raise ValueError(f"{key} must contain only non-empty strings")
                found.update(child)
            else:
                _collect_string_array_values(child, key, found)
    elif isinstance(value, list):
        for child in value:
            _collect_string_array_values(child, key, found)


def source_map(report: dict, loaded: dict[str, dict], errors: list[str]) -> dict[str, dict]:
    if is_decision_tree(report):
        extraction_ids: set[str] = set()
        try:
            _collect_string_array_values(
                loaded.get("decision_tree_plan", {}), "source_ids", extraction_ids
            )
        except ValueError as error:
            errors.append(str(error))
        evidence = loaded.get("evidence_synthesis", {})
        records = {
            item.get("record_id"): item
            for item in objects(evidence.get("records"))
            if text(item.get("record_id"))
        }
        extractions = {
            item.get("extraction_id"): item
            for item in objects(evidence.get("extractions"))
            if text(item.get("extraction_id"))
        }
        result: dict[str, dict] = {}
        for extraction_id in sorted(extraction_ids):
            extraction = extractions.get(extraction_id)
            record = records.get(extraction.get("record_id")) if extraction else None
            if extraction is None or record is None:
                errors.append(
                    f"decision-tree source_id does not resolve to a bound evidence record: {extraction_id}"
                )
                continue
            expected = {
                "source_id": extraction_id,
                "record_id": extraction.get("record_id"),
                "title": record.get("title"),
                "source_type": record.get("source_type"),
                "locator": record.get("locator"),
                "source_location": extraction.get("source_location"),
                "verification_status": extraction.get("verification_status"),
                "content_sha256": None,
                "data_availability_id": f"availability-{extraction_id}",
            }
            if not all(text(expected.get(field)) for field in (
                "record_id", "title", "source_type", "locator",
                "source_location", "verification_status",
            )):
                errors.append(
                    f"decision-tree evidence metadata is incomplete: {extraction_id}"
                )
                continue
            result[extraction_id] = expected
        return result

    result: dict[str, dict] = {}
    for owner, plan in (
        ("analysis", loaded.get("analysis_plan", {})),
        ("budget impact", loaded.get("budget_impact_plan", {})),
    ):
        raw = plan.get("evidence_sources")
        if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
            errors.append(f"{owner} evidence_sources must be an array of objects")
            continue
        for source in raw:
            source_id = source.get("id")
            if not text(source_id) or not SAFE_ID.fullmatch(source_id):
                errors.append(f"{owner} evidence source id is invalid")
                continue
            if source_id in result and result[source_id] != source:
                errors.append(f"evidence source {source_id} differs across plans")
            locator = source.get("url") if text(source.get("url")) else source.get("local_path")
            result[source_id] = {
                "source_id": source_id,
                "title": source.get("title"),
                "source_type": source.get("source_type"),
                "locator": locator,
                "content_sha256": source.get("content_sha256") if text(source.get("local_path")) else None,
                "data_availability_id": f"availability-{source_id}",
            }
    return result


def audit(package_path: Path, workspace: Path) -> dict:
    errors: list[str] = []
    relative = package_path.resolve(strict=True).relative_to(workspace.resolve(strict=True)).as_posix()
    if relative != REPRO_PATH:
        errors.append(f"package path must be {REPRO_PATH}")
    package, package_raw = load_object(workspace, relative)
    try:
        report, report_raw = load_object(workspace, REPORT_PATH)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        report, report_raw = {}, b""
        errors.append(str(error))

    decision_tree = is_decision_tree(report)
    expected_schema = "0.2.0" if decision_tree else "0.1.0"
    if package.get("schema_version") != expected_schema:
        errors.append(f"schema_version must be {expected_schema}")
    if decision_tree and package.get("analysis_type") != "decision_tree":
        errors.append("decision-tree reproducibility package must declare analysis_type decision_tree")
    for field in ("package_id", "analysis_id"):
        if not text(package.get(field)) or not SAFE_ID.fullmatch(str(package.get(field, ""))):
            errors.append(f"{field} must be a safe id")
    report_status = report.get("status")
    package_status = package.get("status")
    if decision_tree:
        if report_status not in {"draft", "ready_for_release_review"}:
            errors.append("decision-tree report status is invalid")
        expected_status = (
            "draft" if report_status == "draft" else "ready_for_reproducibility_review"
        )
        if package_status != expected_status:
            errors.append(
                "decision-tree reproducibility status must follow the current report status"
            )
    elif package_status != "ready_for_reproducibility_review":
        errors.append("status must be ready_for_reproducibility_review")
    if not DATE.fullmatch(str(package.get("prepared_on", ""))):
        errors.append("prepared_on must be YYYY-MM-DD")
    if package.get("analysis_id") != report.get("analysis_id"):
        errors.append("analysis_id does not match the report package")
    report_binding = package.get("report_package") if isinstance(package.get("report_package"), dict) else {}
    report_hash = digest(report_raw) if report_raw else ""
    if report_binding != {"path": REPORT_PATH, "content_sha256": report_hash}:
        errors.append("report_package binding does not match current bytes")

    loaded: dict[str, dict] = {}
    report_bindings = report.get("bindings") if isinstance(report.get("bindings"), dict) else {}
    for key, binding in report_bindings.items():
        if not isinstance(binding, dict) or not text(binding.get("path")):
            continue
        try:
            raw = read_bytes(workspace, binding["path"])
            if digest(raw) != binding.get("content_sha256"):
                errors.append(f"report binding {key} is stale")
            if binding["path"].endswith(".json"):
                value = json.loads(raw)
                if isinstance(value, dict):
                    loaded[key] = value
        except (OSError, ValueError, json.JSONDecodeError) as error:
            errors.append(str(error))
    analysis = loaded.get(
        "decision_tree_plan" if decision_tree else "analysis_plan", {}
    )

    try:
        expected = expected_artifacts(report, report_raw, analysis)
    except ValueError as error:
        expected = {}
        errors.append(str(error))
    inventory = objects(package.get("artifact_inventory"))
    by_id: dict[str, dict] = {}
    for index, item in enumerate(inventory):
        artifact_id = item.get("artifact_id")
        if not text(artifact_id) or not SAFE_ID.fullmatch(artifact_id) or artifact_id in by_id:
            errors.append(f"artifact_inventory[{index}].artifact_id is invalid or duplicated")
            continue
        by_id[artifact_id] = item
    if set(by_id) != set(expected):
        errors.append("artifact_inventory must contain exactly the report graph and declared evidence synthesis")
    for key, (path, sha, role) in expected.items():
        item = by_id.get(key, {})
        if item != {"artifact_id": key, "path": path, "content_sha256": sha, "role": role}:
            errors.append(f"artifact_inventory entry does not match current binding: {key}")
            continue
        try:
            if digest(read_bytes(workspace, path)) != sha:
                errors.append(f"artifact_inventory current bytes differ: {key}")
        except (OSError, ValueError) as error:
            errors.append(str(error))
        if role not in ROLES:
            errors.append(f"artifact_inventory role is invalid: {key}")

    try:
        expected_commands = command_specs(report, loaded)
    except (KeyError, TypeError) as error:
        expected_commands = []
        errors.append(f"cannot derive deterministic replay recipes: {error}")
    if package.get("execution_manifest") != expected_commands:
        errors.append("execution_manifest does not match the exact current replay recipes")

    environment = package.get("environment") if isinstance(package.get("environment"), dict) else {}
    for field in ("ai4heor_version", "platform", "python_version"):
        if not text(environment.get(field)):
            errors.append(f"environment.{field} is required")
    versions = sorted({str(spec.get("engine_version")) for spec in expected_commands if text(spec.get("engine_version"))})
    if environment.get("result_engine_versions") != versions:
        errors.append("environment.result_engine_versions must equal the bound result versions")
    expected_lock = {
        "status": "not_applicable_standard_library_only",
        "package_count": 0,
        "path": None,
        "content_sha256": None,
    }
    if environment.get("core_dependency_lock") != expected_lock:
        errors.append("environment.core_dependency_lock must state the exact standard-library-only boundary")

    sources = source_map(report, loaded, errors)
    source_register = objects(package.get("source_register"))
    registered: dict[str, dict] = {}
    for index, item in enumerate(source_register):
        source_id = item.get("source_id")
        if not text(source_id) or source_id in registered:
            errors.append(f"source_register[{index}].source_id is invalid or duplicated")
            continue
        registered[source_id] = item
    if set(registered) != set(sources):
        errors.append("source_register must equal the unique evidence-source union")
    for source_id, expected_source in sources.items():
        if registered.get(source_id) != expected_source:
            errors.append(f"source_register does not reproduce source metadata: {source_id}")

    availability = objects(package.get("data_availability"))
    availability_ids: set[str] = set()
    covered_sources: list[str] = []
    for index, item in enumerate(availability):
        aid = item.get("availability_id")
        source_ids = strings(item.get("source_ids"))
        if not text(aid) or not AVAILABILITY_ID.fullmatch(aid) or aid in availability_ids:
            errors.append(f"data_availability[{index}].availability_id is invalid or duplicated")
        else:
            availability_ids.add(aid)
        if item.get("status") not in AVAILABILITY or item.get("license_status") not in LICENSES:
            errors.append(f"data_availability[{index}] status or license_status is invalid")
        if not text(item.get("access_conditions")) or not text(item.get("rationale")):
            errors.append(f"data_availability[{index}] requires access_conditions and rationale")
        if not source_ids or any(source_id not in sources for source_id in source_ids):
            errors.append(f"data_availability[{index}].source_ids are invalid")
        covered_sources.extend(source_ids)
    if sorted(covered_sources) != sorted(sources) or len(set(covered_sources)) != len(covered_sources):
        errors.append("data_availability must cover every registered source exactly once")
    for source_id, item in registered.items():
        if item.get("data_availability_id") not in availability_ids:
            errors.append(f"source_register availability link is missing: {source_id}")

    claims = objects(package.get("claim_evidence_ledger"))
    required = required_claims(report)
    claim_ids: set[str] = set()
    covered_claims: set[tuple[str, str]] = set()
    if decision_tree:
        expected_result = {
            "cost_effectiveness": "decision_tree_result",
            "uncertainty": "decision_tree_uncertainty_result",
        }
    else:
        base_result = "partitioned_survival_result" if "partitioned_survival_result" in expected else "base_case_result"
        expected_result = {
            "cost_effectiveness": base_result,
            "uncertainty": "uncertainty_result",
            "budget_impact": "budget_impact_result",
        }
    for index, claim in enumerate(claims):
        claim_id = claim.get("claim_id")
        key = (str(claim.get("profile_id", "")), str(claim.get("item_id", "")))
        artifact_ids = strings(claim.get("artifact_ids"))
        source_ids_value = claim.get("source_ids")
        source_ids = strings(source_ids_value) if isinstance(source_ids_value, list) else []
        if not text(claim_id) or not SAFE_ID.fullmatch(claim_id) or claim_id in claim_ids:
            errors.append(f"claim_evidence_ledger[{index}].claim_id is invalid or duplicated")
        else:
            claim_ids.add(claim_id)
        if key not in required:
            errors.append(f"claim_evidence_ledger[{index}] reporting item is outside the required ledger")
        else:
            covered_claims.add(key)
            if expected_result[required[key]] not in artifact_ids:
                errors.append(f"claim_evidence_ledger[{index}] omits its deterministic result")
        if claim.get("claim_type") not in {"numerical", "interpretation", "limitation"}:
            errors.append(f"claim_evidence_ledger[{index}].claim_type is invalid")
        if claim.get("status") not in {"supported", "qualified"}:
            errors.append(f"claim_evidence_ledger[{index}].status cannot satisfy release traceability")
        if claim.get("status") == "qualified" and not text(claim.get("qualification")):
            errors.append(f"claim_evidence_ledger[{index}] qualified claim needs qualification")
        if not text(claim.get("statement")) or not artifact_ids:
            errors.append(f"claim_evidence_ledger[{index}] requires statement and artifact_ids")
        if not isinstance(source_ids_value, list) or len(source_ids) != len(source_ids_value):
            errors.append(f"claim_evidence_ledger[{index}].source_ids must be an explicit string array")
        if any(item not in expected for item in artifact_ids) or any(item not in sources for item in source_ids):
            errors.append(f"claim_evidence_ledger[{index}] links unknown artifacts or sources")
    if len(claims) != len(required) or covered_claims != set(required):
        errors.append(
            "claim_evidence_ledger must contain exactly the "
            f"{'three' if decision_tree else 'seven'} required reporting items"
        )

    exhibits = objects(package.get("exhibit_register"))
    by_exhibit = {item.get("exhibit_id"): item for item in exhibits if text(item.get("exhibit_id"))}
    required_exhibits = set(expected_result)
    if len(exhibits) != len(required_exhibits) or set(by_exhibit) != required_exhibits:
        errors.append(
            "exhibit_register must contain exactly the "
            f"{'two' if decision_tree else 'three'} deterministic exhibits"
        )
    for exhibit_id, result_id in expected_result.items():
        item = by_exhibit.get(exhibit_id, {})
        artifact_ids = strings(item.get("artifact_ids"))
        exhibit_claims = strings(item.get("claim_ids"))
        if not text(item.get("label")) or result_id not in artifact_ids or not exhibit_claims:
            errors.append(f"exhibit_register is incomplete: {exhibit_id}")
        if any(value not in expected for value in artifact_ids) or any(value not in claim_ids for value in exhibit_claims):
            errors.append(f"exhibit_register links unknown artifacts or claims: {exhibit_id}")

    limitations = strings(package.get("limitations"))
    if not limitations or len(set(limitations)) != len(limitations):
        errors.append("limitations must contain unique non-empty statements")

    complete = not errors
    draft_only_reasons = (
        ["current report package remains draft"]
        if complete and decision_tree and report_status == "draft"
        else []
    )
    release_companion_ready = complete and not draft_only_reasons
    return {
        "complete": complete,
        "release_companion_ready": release_companion_ready,
        "status": "draft" if draft_only_reasons else "complete" if complete else "incomplete",
        "package_id": package.get("package_id", ""),
        "analysis_id": package.get("analysis_id", ""),
        "package_sha256": digest(package_raw),
        "report_package_sha256": report_hash,
        "artifact_count": len(inventory),
        "execution_count": len(objects(package.get("execution_manifest"))),
        "source_count": len(source_register),
        "availability_count": len(availability),
        "exhibit_count": len(exhibits),
        "claim_count": len(claims),
        "required_claim_count": len(required),
        "covered_claim_count": len(covered_claims),
        "draft_only_reasons": draft_only_reasons,
        "current_platform": f"{platform.system().lower()}-{platform.machine().lower()}",
        "errors": errors,
    }


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: validate_reproducibility_package.py PACKAGE WORKSPACE", file=sys.stderr)
        return 2
    try:
        result = audit(Path(sys.argv[1]), Path(sys.argv[2]))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        result = {"complete": False, "status": "incomplete", "errors": [str(error)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("complete") else 1


if __name__ == "__main__":
    raise SystemExit(main())
