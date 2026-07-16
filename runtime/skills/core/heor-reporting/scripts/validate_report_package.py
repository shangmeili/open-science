#!/usr/bin/env python3
"""Portable, fail-closed validator for an AI4HEOR report package."""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path, PurePosixPath


CAP_BYTES = 5 * 1024 * 1024
SHA256 = re.compile(r"^[a-f0-9]{64}$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LEGACY_BINDINGS = {
    "report_document": "heor/report.md",
    "analysis_plan": "heor/analysis-plan.json",
    "conceptual_model": "heor/conceptual-model.json",
    "uncertainty_plan": "heor/uncertainty-plan.json",
    "budget_impact_plan": "heor/budget-impact-plan.json",
    "model_validation": "heor/model-validation.json",
    "base_case_result": "heor/results/base-case.json",
    "uncertainty_result": "heor/results/uncertainty.json",
    "budget_impact_result": "heor/results/budget-impact.json",
}
BINDINGS = LEGACY_BINDINGS
PARTITIONED_BINDINGS = {
    "report_document": "heor/report.md",
    "analysis_plan": "heor/analysis-plan.json",
    "conceptual_model": "heor/conceptual-model.json",
    "uncertainty_plan": "heor/uncertainty-plan.json",
    "budget_impact_plan": "heor/budget-impact-plan.json",
    "model_validation": "heor/model-validation.json",
    "partitioned_survival_plan": "heor/partitioned-survival-plan.json",
    "survival_curve_materializations": "heor/survival-curve-materializations.json",
    "treatment_effect_duration": "heor/treatment-effect-duration.json",
    "cost_input_normalization": "heor/cost-input-normalization.json",
    "utility_inputs": "heor/utility-inputs.json",
    "event_disutilities": "heor/event-disutilities.json",
    "partitioned_survival_result": "heor/results/partitioned-survival.json",
    "uncertainty_result": "heor/results/uncertainty.json",
    "budget_impact_result": "heor/results/budget-impact.json",
}
PROFILES = [
    {"id": "CHEERS-2022", "status": "current", "scope": "cost_effectiveness"},
    {"id": "ISPOR-BIA-GP-II-2014", "status": "current", "scope": "budget_impact"},
]
CHEERS_ITEMS = [
    "1-title", "2-abstract", "3-background-objectives", "4-analysis-plan",
    "5-study-population", "6-setting-location", "7-comparators", "8-perspective",
    "9-time-horizon", "10-discount-rate", "11-outcome-selection",
    "12-outcome-measurement", "13-outcome-valuation", "14-resources-costs",
    "15-currency-price-date", "16-model-rationale-description",
    "17-analytics-assumptions", "18-heterogeneity", "19-distributional-effects",
    "20-uncertainty", "21-engagement-approach", "22-study-parameters",
    "23-summary-results", "24-uncertainty-effects", "25-engagement-effects",
    "26-findings-limitations-generalisability", "27-funding", "28-conflicts",
]
BIA_ITEMS = [
    "bia-1-objective-perspective-audience", "bia-2-context",
    "bia-3-eligible-population", "bia-4-treatment-mix", "bia-5-cost-scope",
    "bia-6-inputs-sources-derivations", "bia-7-framework-calculations",
    "bia-8-period-disaggregated-results", "bia-9-cumulative-impact",
    "bia-10-uncertainty-scenarios", "bia-11-validation",
    "bia-12-limitations-reproducibility",
]
REQUIRED_ITEMS = {
    **{("CHEERS-2022", item): "cost_effectiveness" for item in CHEERS_ITEMS},
    **{("ISPOR-BIA-GP-II-2014", item): "budget_impact" for item in BIA_ITEMS},
}
DISCLOSURES = {
    "funding", "conflicts_of_interest", "agent_contributions", "model_providers",
    "data_and_model_availability", "patient_and_public_involvement",
}


def text(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def strings(value: object, *, nonempty: bool = False) -> bool:
    return (
        isinstance(value, list)
        and (bool(value) or not nonempty)
        and all(text(item) for item in value)
        and len(value) == len(set(value))
    )


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
        posix.is_absolute() or "\\" in relative or not posix.parts
        or any(part in {"", ".", ".."} for part in posix.parts)
    ):
        raise ValueError(f"unsafe workspace path: {relative}")
    root = workspace.resolve(strict=True)
    target = (root / Path(*posix.parts)).resolve(strict=True)
    if root not in target.parents or not target.is_file():
        raise ValueError(f"workspace artifact is unavailable: {relative}")
    if target.stat().st_size > CAP_BYTES:
        raise ValueError(f"workspace artifact exceeds the 5 MiB review cap: {relative}")
    return target


def nested(value: dict, *parts: str) -> object:
    current: object = value
    for part in parts:
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def expected_result_summary(loaded: dict[str, dict]) -> dict:
    """Return the exact bounded summary for legacy or multi-strategy results."""
    base_case = loaded.get("partitioned_survival_result", loaded.get("base_case_result", {}))
    uncertainty_result = loaded.get("uncertainty_result", {})
    probabilistic = uncertainty_result.get("probabilistic_analysis", {})
    if not isinstance(probabilistic, dict):
        probabilistic = {}

    expected_uncertainty = {
        "iterations": probabilistic.get("iterations"),
        "cost_effective_probability": probabilistic.get("cost_effective_probability"),
        "mean_incremental_net_monetary_benefit": probabilistic.get(
            "mean_incremental_net_monetary_benefit"
        ),
    }
    if "decision_uncertainty" in probabilistic:
        expected_uncertainty["decision_uncertainty"] = probabilistic[
            "decision_uncertainty"
        ]
    for field in (
        "strategy_order",
        "primary_threshold_strategy_optimal_probabilities",
        "primary_threshold_tie_probability",
        "mean_net_monetary_benefit_by_strategy",
        "net_monetary_benefit_mcse_by_strategy",
    ):
        if field in probabilistic:
            expected_uncertainty[field] = probabilistic[field]

    if "fully_incremental_analysis" in base_case:
        raw_strategies = base_case.get("strategies", {})
        if not isinstance(raw_strategies, dict) or any(
            not text(strategy_id) or not isinstance(strategy, dict)
            for strategy_id, strategy in raw_strategies.items()
        ):
            raise ValueError(
                "multi-strategy base-case strategies must be an object of strategy result objects"
            )
        strategies = {
            strategy_id: {
                "name": strategy.get("name"),
                "total_cost": strategy.get("total_cost"),
                "total_qaly": strategy.get("total_qaly"),
                "net_monetary_benefit": strategy.get("net_monetary_benefit"),
            }
            for strategy_id, strategy in raw_strategies.items()
        }
        cost_effectiveness = {
            "economic_basis": base_case.get("economic_basis"),
            "strategy_order": base_case.get("strategy_order"),
            "baseline_strategy_id": base_case.get("baseline_strategy_id"),
            "strategies": strategies,
            "pairwise_vs_baseline": base_case.get("pairwise_vs_baseline"),
            "fully_incremental_analysis": base_case.get("fully_incremental_analysis"),
            "optimal_at_primary_threshold": base_case.get(
                "optimal_at_primary_threshold"
            ),
        }
    else:
        cost_effectiveness = {
            "economic_basis": base_case.get("economic_basis"),
            "delta_cost": nested(base_case, "incremental", "delta_cost"),
            "delta_qaly": nested(base_case, "incremental", "delta_qaly"),
            "icer": nested(base_case, "incremental", "icer"),
            "incremental_net_monetary_benefit": nested(
                base_case, "incremental", "incremental_net_monetary_benefit"
            ),
        }

    bia_result = loaded.get("budget_impact_result", {})
    return {
        "cost_effectiveness": cost_effectiveness,
        "uncertainty": expected_uncertainty,
        "budget_impact": {
            "annual_net_budget_impact": nested(
                bia_result, "base_case", "annual_net_budget_impact"
            ),
            "cumulative_net_budget_impact": nested(
                bia_result, "base_case", "cumulative_net_budget_impact"
            ),
        },
    }


def binding_contract(package: dict, analysis: dict, errors: list[str]) -> dict[str, str]:
    partitioned = analysis.get("partitioned_survival_analysis") == {
        "path": "heor/partitioned-survival-plan.json"
    }
    if partitioned:
        if package.get("schema_version") != "0.2.0":
            errors.append("partitioned-survival reporting requires schema_version 0.2.0")
        return dict(PARTITIONED_BINDINGS)
    if package.get("schema_version") != "0.1.0":
        errors.append("non-partitioned reporting requires schema_version 0.1.0")
    return dict(LEGACY_BINDINGS)


def validate_partitioned_consistency(
    loaded: dict[str, dict], binding_hashes: dict[str, str], errors: list[str]
) -> None:
    if "partitioned_survival_plan" not in loaded:
        return
    expected_inputs = {
        "analysis_plan_sha256": "analysis_plan",
        "partitioned_survival_plan_sha256": "partitioned_survival_plan",
        "survival_curve_materializations_sha256": "survival_curve_materializations",
        "treatment_effect_duration_sha256": "treatment_effect_duration",
        "cost_input_normalization_sha256": "cost_input_normalization",
        "utility_inputs_sha256": "utility_inputs",
        "event_disutilities_sha256": "event_disutilities",
    }
    base = loaded.get("partitioned_survival_result", {})
    uncertainty = loaded.get("uncertainty_result", {})
    for field, key in expected_inputs.items():
        expected = binding_hashes.get(key)
        if base.get(field) != expected:
            errors.append(f"partitioned-survival result {field} does not match bound bytes")
        uncertainty_field = "base_analysis_sha256" if field == "analysis_plan_sha256" else field
        if uncertainty.get(uncertainty_field) != expected:
            errors.append(f"uncertainty result {uncertainty_field} does not match bound bytes")


def audit(package_path: Path, workspace: Path) -> dict:
    package, package_raw = load_object(package_path)
    errors: list[str] = []
    missing_items: list[str] = []
    invalid_items: list[str] = []

    for field in ("package_id", "analysis_id", "version", "intended_audience", "release_owner_label"):
        if not text(package.get(field)):
            errors.append(f"{field} is required")
    if package.get("status") != "ready_for_release_review":
        errors.append("status must be ready_for_release_review")
    if not DATE.fullmatch(str(package.get("prepared_on", ""))):
        errors.append("prepared_on must be YYYY-MM-DD")
    if package.get("reporting_profiles") != PROFILES:
        errors.append("reporting_profiles must contain the scoped CHEERS 2022 and ISPOR BIA profiles")

    try:
        analysis, _ = load_object(workspace_file(workspace, "heor/analysis-plan.json"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        analysis = {}
        errors.append(str(error))
    expected_bindings = binding_contract(package, analysis, errors)
    bindings = package.get("bindings") if isinstance(package.get("bindings"), dict) else {}
    if set(bindings) != set(expected_bindings):
        errors.append("bindings fields do not match the report schema")
    loaded: dict[str, dict] = {}
    binding_hashes: dict[str, str] = {}
    report_text = ""
    for key, expected_path in expected_bindings.items():
        binding = bindings.get(key) if isinstance(bindings.get(key), dict) else {}
        if binding.get("path") != expected_path:
            errors.append(f"bindings.{key}.path must be {expected_path}")
            continue
        try:
            path = workspace_file(workspace, expected_path)
            raw = path.read_bytes()
            if key == "report_document":
                report_text = raw.decode("utf-8")
            else:
                value = json.loads(raw)
                if not isinstance(value, dict):
                    raise ValueError(f"{expected_path} must contain a JSON object")
                loaded[key] = value
        except (OSError, UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
            errors.append(str(error))
            continue
        digest = hashlib.sha256(raw).hexdigest()
        binding_hashes[key] = digest
        if binding.get("content_sha256") != digest or not SHA256.fullmatch(str(binding.get("content_sha256", ""))):
            errors.append(f"bindings.{key}.content_sha256 does not match current bytes")

    for key, value in loaded.items():
        if value.get("analysis_id") != package.get("analysis_id"):
            errors.append(f"{expected_bindings[key]} analysis_id does not match the report package")

    analysis_hash = binding_hashes.get("analysis_plan")
    uncertainty_plan_hash = binding_hashes.get("uncertainty_plan")
    bia_plan_hash = binding_hashes.get("budget_impact_plan")
    if "base_case_result" in loaded and loaded["base_case_result"].get("input_sha256") != analysis_hash:
        errors.append("base-case result is not bound to the current analysis plan")
    uncertainty_result = loaded.get("uncertainty_result", {})
    if uncertainty_result.get("base_analysis_sha256") != analysis_hash:
        errors.append("uncertainty result is not bound to the current analysis plan")
    if uncertainty_result.get("uncertainty_plan_sha256") != uncertainty_plan_hash:
        errors.append("uncertainty result is not bound to the current uncertainty plan")
    bia_result = loaded.get("budget_impact_result", {})
    if bia_result.get("analysis_plan_sha256") != analysis_hash:
        errors.append("budget-impact result is not bound to the current analysis plan")
    if bia_result.get("budget_impact_plan_sha256") != bia_plan_hash:
        errors.append("budget-impact result is not bound to the current budget-impact plan")
    validate_partitioned_consistency(loaded, binding_hashes, errors)

    raw_items = package.get("items")
    items = raw_items if isinstance(raw_items, list) and all(isinstance(item, dict) for item in raw_items) else []
    if len(items) != len(REQUIRED_ITEMS):
        errors.append(f"items must contain exactly {len(REQUIRED_ITEMS)} reporting items")
    seen: set[tuple[str, str]] = set()
    sections: set[str] = set()
    allowed_paths = set(expected_bindings.values())
    for index, item in enumerate(items):
        key = (str(item.get("profile_id", "")), str(item.get("item_id", "")))
        if key in seen:
            invalid_items.append(f"items[{index}] duplicates {key[0]}:{key[1]}")
        seen.add(key)
        if key not in REQUIRED_ITEMS:
            invalid_items.append(f"items[{index}] is not a scoped reporting item")
        if item.get("status") not in {"reported", "not_applicable"}:
            invalid_items.append(f"items[{index}].status must be reported or not_applicable")
        if not text(item.get("section_id")) or item.get("section_id") in sections:
            invalid_items.append(f"items[{index}].section_id must be non-empty and unique")
        else:
            section_id = str(item["section_id"])
            sections.add(section_id)
            if report_text.count(f"<!-- report-section:{section_id} -->") != 1:
                invalid_items.append(f"report marker for {section_id} must occur exactly once")
        if not text(item.get("rationale")):
            invalid_items.append(f"items[{index}].rationale is required")
        paths = item.get("artifact_paths")
        if not strings(paths, nonempty=True) or not set(paths or []).issubset(allowed_paths):
            invalid_items.append(f"items[{index}].artifact_paths must reference bound artifacts")
    for key in REQUIRED_ITEMS:
        if key not in seen:
            missing_items.append(f"{key[0]}:{key[1]}")
    errors.extend(invalid_items)
    if missing_items:
        errors.append("missing reporting items: " + ", ".join(missing_items))

    summary = package.get("result_summary") if isinstance(package.get("result_summary"), dict) else {}
    try:
        expected_summary = expected_result_summary(loaded)
    except ValueError as error:
        errors.append(f"bound result artifacts are invalid: {error}")
    else:
        if summary != expected_summary:
            errors.append("result_summary must exactly match the bound deterministic result artifacts")

    disclosures = package.get("disclosures") if isinstance(package.get("disclosures"), dict) else {}
    if set(disclosures) != DISCLOSURES or not all(text(disclosures.get(key)) for key in DISCLOSURES):
        errors.append("all six disclosures are required and no unrecognized disclosure is allowed")
    if not strings(package.get("limitations"), nonempty=True):
        errors.append("limitations must be a non-empty unique string array")
    if not strings(package.get("release_notes"), nonempty=True):
        errors.append("release_notes must be a non-empty unique string array")

    complete = not errors
    return {
        "complete": complete,
        "releasable": complete,
        "status": "complete" if complete else "incomplete",
        "package_id": str(package.get("package_id", "")),
        "analysis_id": str(package.get("analysis_id", "")),
        "report_package_sha256": hashlib.sha256(package_raw).hexdigest(),
        "release_owner_label": str(package.get("release_owner_label", "")),
        "binding_hashes": binding_hashes,
        "reporting_item_count": len(items),
        "required_item_count": len(REQUIRED_ITEMS),
        "covered_item_count": len(REQUIRED_ITEMS) - len(missing_items),
        "missing_items": missing_items,
        "invalid_items": invalid_items,
        "errors": errors,
    }


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: validate_report_package.py REPORT_PACKAGE_JSON WORKSPACE", file=sys.stderr)
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
    print("valid (releasable after app-owned human approval)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
