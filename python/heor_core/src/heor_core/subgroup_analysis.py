"""Deterministic, source-bound subgroup analysis for current decision trees."""

from __future__ import annotations

import hashlib
import re
from itertools import combinations
from math import isfinite
from typing import Any

from .decision_tree import (
    SCHEMA_VERSION as DECISION_TREE_SCHEMA_VERSION,
    DecisionTreeSpecification,
    run_decision_tree,
)
from .model import ModelValidationError, TOLERANCE


SCHEMA_VERSION = "0.1.0"
ENGINE_VERSION = "0.1.0"
ANALYSIS_TYPE = "decision_tree_subgroup"
SAFE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SAFE_SUBGROUP_PATH = re.compile(r"^heor/subgroups/[a-zA-Z0-9._-]+\.json$")
REQUIRED_REVIEW_CHECKS = (
    "population_definition_and_overlap",
    "prespecification_or_post_hoc_status",
    "subgroup_source_eligibility",
    "interaction_or_heterogeneity_basis",
    "multiplicity_and_power",
    "interpretation_and_decision_use",
)


def _mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ModelValidationError(f"{path} must be an object")
    return value


def _exact(value: dict[str, Any], fields: set[str], path: str) -> None:
    extra = set(value) - fields
    missing = fields - set(value)
    if extra or missing:
        detail = []
        if missing:
            detail.append("missing " + ", ".join(sorted(missing)))
        if extra:
            detail.append("unsupported " + ", ".join(sorted(extra)))
        raise ModelValidationError(f"{path} has {'; '.join(detail)}")


def _text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ModelValidationError(f"{path} must be a non-empty trimmed string")
    if len(value) > 240 or any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise ModelValidationError(f"{path} contains unsupported characters or is too long")
    return value


def _identifier(value: Any, path: str) -> str:
    parsed = _text(value, path)
    if not SAFE_ID.fullmatch(parsed):
        raise ModelValidationError(f"{path} must be a safe lowercase id")
    return parsed


def _digest(value: Any, path: str) -> str:
    parsed = _text(value, path)
    if not re.fullmatch(r"[a-f0-9]{64}", parsed):
        raise ModelValidationError(f"{path} must be a SHA-256 digest")
    return parsed


def _strict_float(value: Any, path: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ModelValidationError(f"{path} must be a finite number")
    parsed = float(value)
    if not isfinite(parsed):
        raise ModelValidationError(f"{path} must be a finite number")
    return parsed


def _id_list(value: Any, path: str) -> list[str]:
    if not isinstance(value, list):
        raise ModelValidationError(f"{path} must be an array")
    parsed = [_identifier(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if len(set(parsed)) != len(parsed):
        raise ModelValidationError(f"{path} must not contain duplicates")
    return parsed


def _binding(value: Any, path: str, expected_path: str | None = None) -> tuple[str, str]:
    binding = _mapping(value, path)
    _exact(binding, {"path", "content_sha256"}, path)
    bound_path = _text(binding.get("path"), f"{path}.path")
    if expected_path is not None and bound_path != expected_path:
        raise ModelValidationError(f"{path}.path must be {expected_path}")
    return bound_path, _digest(binding.get("content_sha256"), f"{path}.content_sha256")


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _collect_source_ids(value: Any, found: set[str]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "source_ids":
                found.update(_id_list(item, "source_ids"))
            else:
                _collect_source_ids(item, found)
    elif isinstance(value, list):
        for item in value:
            _collect_source_ids(item, found)


def _evidence_index(evidence: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    records_raw = evidence.get("records")
    extractions_raw = evidence.get("extractions")
    if not isinstance(records_raw, list) or not isinstance(extractions_raw, list):
        raise ModelValidationError("evidence synthesis must contain records and extractions arrays")
    records: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(records_raw):
        record = _mapping(raw, f"evidence.records[{index}]")
        record_id = _identifier(record.get("record_id"), f"evidence.records[{index}].record_id")
        if record_id in records:
            raise ModelValidationError("evidence record ids must be unique")
        for field in ("title", "source_type", "locator"):
            _text(record.get(field), f"evidence.records[{index}].{field}")
        records[record_id] = record
    extractions: dict[str, dict[str, Any]] = {}
    for index, raw in enumerate(extractions_raw):
        extraction = _mapping(raw, f"evidence.extractions[{index}]")
        extraction_id = _identifier(
            extraction.get("extraction_id"), f"evidence.extractions[{index}].extraction_id"
        )
        if extraction_id in extractions:
            raise ModelValidationError("evidence extraction ids must be unique")
        record_id = _identifier(
            extraction.get("record_id"), f"evidence.extractions[{index}].record_id"
        )
        if record_id not in records:
            raise ModelValidationError(f"evidence extraction has unknown record_id: {extraction_id}")
        _text(extraction.get("source_location"), f"evidence.extractions[{index}].source_location")
        _text(
            extraction.get("verification_status"),
            f"evidence.extractions[{index}].verification_status",
        )
        extractions[extraction_id] = extraction
    return records, extractions


def _comparable(overall: DecisionTreeSpecification, subgroup: DecisionTreeSpecification) -> bool:
    return (
        subgroup.schema_version == DECISION_TREE_SCHEMA_VERSION
        and subgroup.strategy_order == overall.strategy_order
        and subgroup.baseline_strategy_id == overall.baseline_strategy_id
        and tuple(strategy.name for _, strategy in subgroup.strategies)
        == tuple(strategy.name for _, strategy in overall.strategies)
        and subgroup.reference_case_id == overall.reference_case_id
        and subgroup.reference_case_status == overall.reference_case_status
        and subgroup.economic_basis == overall.economic_basis
        and subgroup.time_horizon_years == overall.time_horizon_years
        and subgroup.cost_discount_rate == overall.cost_discount_rate
        and subgroup.outcome_discount_rate == overall.outcome_discount_rate
        and subgroup.half_cycle_correction == overall.half_cycle_correction
        and subgroup.willingness_to_pay == overall.willingness_to_pay
    )


def _strategy_values(result: dict[str, Any]) -> dict[str, dict[str, float | None | str]]:
    return {
        strategy_id: {
            "name": row["name"],
            "total_cost": row["total_cost"],
            "total_qaly": row["total_qaly"],
            "net_monetary_benefit": row["net_monetary_benefit"],
        }
        for strategy_id, row in result["strategies"].items()
    }


def _incremental(cost: float, qaly: float, base_cost: float, base_qaly: float, wtp: float | None) -> dict[str, Any]:
    delta_cost = cost - base_cost
    delta_qaly = qaly - base_qaly
    if delta_cost < 0 and delta_qaly > 0:
        interpretation = "dominant"
        icer = None
    elif delta_cost > 0 and delta_qaly < 0:
        interpretation = "dominated"
        icer = None
    elif abs(delta_qaly) <= TOLERANCE:
        interpretation = "no_effect_difference"
        icer = None
    else:
        interpretation = "tradeoff"
        icer = delta_cost / delta_qaly
    return {
        "delta_cost": delta_cost,
        "delta_qaly": delta_qaly,
        "icer": icer,
        "interpretation": interpretation,
        "incremental_net_monetary_benefit": (
            None if wtp is None else delta_qaly * wtp - delta_cost
        ),
    }


def run_subgroup_analysis(
    overall_payload: dict[str, Any],
    overall_raw: bytes,
    subgroup_plan: dict[str, Any],
    subgroup_plan_raw: bytes,
    subgroup_inputs: dict[str, tuple[dict[str, Any], bytes]],
    evidence: dict[str, Any],
    evidence_raw: bytes,
) -> dict[str, Any]:
    """Calculate prespecified or post-hoc subgroup results without inferential claims."""

    plan = _mapping(subgroup_plan, "subgroup plan")
    _exact(
        plan,
        {
            "schema_version",
            "analysis_type",
            "subgroup_analysis_id",
            "overall_analysis_input",
            "evidence_synthesis_input",
            "grouping",
            "subgroups",
            "assumptions",
        },
        "subgroup plan",
    )
    if plan.get("schema_version") != SCHEMA_VERSION or plan.get("analysis_type") != ANALYSIS_TYPE:
        raise ModelValidationError("unsupported decision-tree subgroup contract")
    subgroup_analysis_id = _identifier(plan.get("subgroup_analysis_id"), "subgroup_analysis_id")
    overall_path, overall_hash = _binding(
        plan.get("overall_analysis_input"),
        "overall_analysis_input",
        "heor/decision-tree-plan.json",
    )
    if overall_hash != _sha256(overall_raw):
        raise ModelValidationError("overall_analysis_input does not match the current overall plan bytes")
    evidence_path, evidence_hash = _binding(
        plan.get("evidence_synthesis_input"),
        "evidence_synthesis_input",
        "heor/evidence-synthesis.json",
    )
    if evidence_hash != _sha256(evidence_raw):
        raise ModelValidationError("evidence_synthesis_input does not match the current evidence bytes")

    overall = DecisionTreeSpecification.from_dict(overall_payload)
    if overall.schema_version != DECISION_TREE_SCHEMA_VERSION:
        raise ModelValidationError("subgroup analysis requires current decision-tree schema 0.2.0")
    overall_result = run_decision_tree(overall).to_dict()
    grouping = _mapping(plan.get("grouping"), "grouping")
    _exact(
        grouping,
        {
            "id",
            "label",
            "prespecification",
            "mutually_exclusive",
            "exhaustive",
            "definition_source_ids",
            "heterogeneity_basis",
        },
        "grouping",
    )
    grouping_id = _identifier(grouping.get("id"), "grouping.id")
    grouping_label = _text(grouping.get("label"), "grouping.label")
    prespecification = grouping.get("prespecification")
    if prespecification not in {"prespecified", "post_hoc"}:
        raise ModelValidationError("grouping.prespecification must be prespecified or post_hoc")
    if grouping.get("mutually_exclusive") is not True or grouping.get("exhaustive") is not True:
        raise ModelValidationError("subgroups must be explicitly mutually exclusive and exhaustive")
    definition_source_ids = _id_list(
        grouping.get("definition_source_ids"), "grouping.definition_source_ids"
    )
    if not definition_source_ids:
        raise ModelValidationError("grouping.definition_source_ids must not be empty")
    heterogeneity_basis = _mapping(grouping.get("heterogeneity_basis"), "grouping.heterogeneity_basis")
    _exact(heterogeneity_basis, {"status", "source_ids", "rationale"}, "grouping.heterogeneity_basis")
    basis_status = heterogeneity_basis.get("status")
    if basis_status not in {"descriptive_only", "interaction_evidence_available"}:
        raise ModelValidationError("unsupported grouping.heterogeneity_basis.status")
    basis_source_ids = _id_list(
        heterogeneity_basis.get("source_ids"), "grouping.heterogeneity_basis.source_ids"
    )
    if basis_status == "interaction_evidence_available" and not basis_source_ids:
        raise ModelValidationError("interaction evidence status requires at least one source_id")
    _text(heterogeneity_basis.get("rationale"), "grouping.heterogeneity_basis.rationale")

    assumptions_raw = plan.get("assumptions")
    if not isinstance(assumptions_raw, list):
        raise ModelValidationError("assumptions must be an array")
    proposed_assumptions: set[str] = set()
    for index, raw in enumerate(assumptions_raw):
        assumption = _mapping(raw, f"assumptions[{index}]")
        _exact(assumption, {"id", "status", "statement"}, f"assumptions[{index}]")
        assumption_id = _identifier(assumption.get("id"), f"assumptions[{index}].id")
        if assumption_id in proposed_assumptions or assumption.get("status") != "proposed":
            raise ModelValidationError("subgroup assumptions must be unique and proposed")
        _text(assumption.get("statement"), f"assumptions[{index}].statement")
        proposed_assumptions.add(assumption_id)

    groups_raw = plan.get("subgroups")
    if not isinstance(groups_raw, list) or not 2 <= len(groups_raw) <= 20:
        raise ModelValidationError("subgroups must contain from 2 to 20 entries")
    group_ids: set[str] = set()
    analysis_ids: set[str] = set()
    source_ids = set(definition_source_ids) | set(basis_source_ids)
    group_rows: list[dict[str, Any]] = []
    total_share = 0.0
    for index, raw in enumerate(groups_raw):
        group = _mapping(raw, f"subgroups[{index}]")
        _exact(group, {"id", "label", "population_share", "analysis_input"}, f"subgroups[{index}]")
        group_id = _identifier(group.get("id"), f"subgroups[{index}].id")
        if group_id in group_ids:
            raise ModelValidationError("subgroup ids must be unique")
        group_ids.add(group_id)
        label = _text(group.get("label"), f"subgroups[{index}].label")
        share = _mapping(group.get("population_share"), f"subgroups[{index}].population_share")
        _exact(share, {"value", "source_ids", "assumption_ids"}, f"subgroups[{index}].population_share")
        share_value = _strict_float(share.get("value"), f"subgroups[{index}].population_share.value")
        if not 0.0 < share_value < 1.0:
            raise ModelValidationError("each subgroup population share must be strictly between zero and one")
        share_source_ids = _id_list(share.get("source_ids"), f"subgroups[{index}].population_share.source_ids")
        share_assumption_ids = _id_list(share.get("assumption_ids"), f"subgroups[{index}].population_share.assumption_ids")
        if not share_source_ids and not share_assumption_ids:
            raise ModelValidationError("each subgroup population share requires a source or proposed assumption")
        if set(share_assumption_ids) - proposed_assumptions:
            raise ModelValidationError("subgroup population share refers to an unknown proposed assumption")
        source_ids.update(share_source_ids)
        total_share += share_value
        subgroup_path, subgroup_hash = _binding(group.get("analysis_input"), f"subgroups[{index}].analysis_input")
        if not SAFE_SUBGROUP_PATH.fullmatch(subgroup_path) or subgroup_path not in subgroup_inputs:
            raise ModelValidationError("subgroup analysis paths must be existing files under heor/subgroups")
        subgroup_payload, subgroup_raw = subgroup_inputs[subgroup_path]
        if subgroup_hash != _sha256(subgroup_raw):
            raise ModelValidationError(f"subgroup analysis_input hash does not match: {subgroup_path}")
        subgroup_specification = DecisionTreeSpecification.from_dict(subgroup_payload)
        if not _comparable(overall, subgroup_specification):
            raise ModelValidationError(f"subgroup analysis is not comparable with the overall plan: {group_id}")
        if subgroup_specification.analysis_id in analysis_ids:
            raise ModelValidationError("subgroup analysis ids must be unique")
        analysis_ids.add(subgroup_specification.analysis_id)
        subgroup_source_ids = set(share_source_ids)
        _collect_source_ids(subgroup_payload, subgroup_source_ids)
        source_ids.update(subgroup_source_ids)
        subgroup_result = run_decision_tree(subgroup_specification).to_dict()
        group_rows.append(
            {
                "id": group_id,
                "label": label,
                "population_share": share_value,
                "population_share_provenance": {
                    "source_ids": share_source_ids,
                    "assumption_ids": share_assumption_ids,
                },
                "analysis_id": subgroup_specification.analysis_id,
                "analysis_input_path": subgroup_path,
                "analysis_input_sha256": subgroup_hash,
                "source_ids": sorted(subgroup_source_ids),
                "strategies": _strategy_values(subgroup_result),
                "pairwise_vs_baseline": subgroup_result["pairwise_vs_baseline"],
            }
        )
    if abs(total_share - 1.0) > TOLERANCE:
        raise ModelValidationError("subgroup population shares must sum to one")

    records, extractions = _evidence_index(evidence)
    source_register = []
    for source_id in sorted(source_ids):
        extraction = extractions.get(source_id)
        if extraction is None:
            raise ModelValidationError(f"source_id does not resolve to an evidence extraction: {source_id}")
        record_id = extraction["record_id"]
        record = records[record_id]
        source_register.append(
            {
                "source_id": source_id,
                "record_id": record_id,
                "title": record["title"],
                "source_type": record["source_type"],
                "locator": record["locator"],
                "source_location": extraction["source_location"],
                "verification_status": extraction["verification_status"],
            }
        )

    weighted_strategies: dict[str, dict[str, Any]] = {}
    for strategy_id in overall.strategy_order:
        cost = sum(row["population_share"] * row["strategies"][strategy_id]["total_cost"] for row in group_rows)
        qaly = sum(row["population_share"] * row["strategies"][strategy_id]["total_qaly"] for row in group_rows)
        weighted_strategies[strategy_id] = {
            "name": overall_result["strategies"][strategy_id]["name"],
            "total_cost": cost,
            "total_qaly": qaly,
            "net_monetary_benefit": None if overall.willingness_to_pay is None else qaly * overall.willingness_to_pay - cost,
        }
    baseline = weighted_strategies[overall.baseline_strategy_id]
    weighted_pairwise = {
        strategy_id: _incremental(
            row["total_cost"],
            row["total_qaly"],
            baseline["total_cost"],
            baseline["total_qaly"],
            overall.willingness_to_pay,
        )
        for strategy_id, row in weighted_strategies.items()
        if strategy_id != overall.baseline_strategy_id
    }
    differences = {
        strategy_id: {
            "cost": weighted_strategies[strategy_id]["total_cost"] - overall_result["strategies"][strategy_id]["total_cost"],
            "qaly": weighted_strategies[strategy_id]["total_qaly"] - overall_result["strategies"][strategy_id]["total_qaly"],
        }
        for strategy_id in overall.strategy_order
    }
    max_abs_cost_difference = max(abs(row["cost"]) for row in differences.values())
    max_abs_qaly_difference = max(abs(row["qaly"]) for row in differences.values())
    descriptive_heterogeneity = []
    for left, right in combinations(group_rows, 2):
        for strategy_id in overall.strategy_order[1:]:
            left_increment = left["pairwise_vs_baseline"][strategy_id]
            right_increment = right["pairwise_vs_baseline"][strategy_id]
            left_nmb = left_increment["incremental_net_monetary_benefit"]
            right_nmb = right_increment["incremental_net_monetary_benefit"]
            descriptive_heterogeneity.append(
                {
                    "left_subgroup_id": left["id"],
                    "right_subgroup_id": right["id"],
                    "strategy_id": strategy_id,
                    "delta_cost_difference": left_increment["delta_cost"] - right_increment["delta_cost"],
                    "delta_qaly_difference": left_increment["delta_qaly"] - right_increment["delta_qaly"],
                    "incremental_nmb_difference": (
                        None if left_nmb is None or right_nmb is None else left_nmb - right_nmb
                    ),
                    "interpretation": "descriptive_contrast_not_interaction_test",
                }
            )

    warnings = [
        "This descriptive subgroup contrast does not establish interaction, treatment-effect modification, or a subgroup decision rule.",
        "Multiplicity, statistical power, transportability, equity, and decision consequences require researcher review.",
    ]
    if prespecification == "post_hoc":
        warnings.append("Post hoc subgrouping increases the risk of spurious heterogeneity and must remain explicit.")
    if max_abs_cost_difference > TOLERANCE or max_abs_qaly_difference > TOLERANCE:
        warnings.append("Weighted subgroup results do not reproduce the overall model and require reconciliation.")

    return {
        "schema_version": SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "analysis_type": ANALYSIS_TYPE,
        "subgroup_analysis_id": subgroup_analysis_id,
        "calculation_classification": "deterministic_subgroup_analysis",
        "subgroup_input_sha256": _sha256(subgroup_plan_raw),
        "overall_analysis_input": {"path": overall_path, "content_sha256": overall_hash},
        "evidence_synthesis_input": {"path": evidence_path, "content_sha256": evidence_hash},
        "economic_basis": overall.economic_basis.to_dict() if overall.economic_basis is not None else None,
        "strategy_order": list(overall.strategy_order),
        "baseline_strategy_id": overall.baseline_strategy_id,
        "grouping": {
            "id": grouping_id,
            "label": grouping_label,
            "prespecification": prespecification,
            "mutually_exclusive": True,
            "exhaustive": True,
            "definition_source_ids": definition_source_ids,
            "heterogeneity_basis": heterogeneity_basis,
        },
        "source_register": source_register,
        "subgroups": group_rows,
        "weighted_strategies": weighted_strategies,
        "weighted_pairwise_vs_baseline": weighted_pairwise,
        "overall_consistency": {
            "passed": max_abs_cost_difference <= TOLERANCE and max_abs_qaly_difference <= TOLERANCE,
            "tolerances": {"cost": TOLERANCE, "qaly": TOLERANCE},
            "max_abs_cost_difference": max_abs_cost_difference,
            "max_abs_qaly_difference": max_abs_qaly_difference,
            "differences": differences,
        },
        "descriptive_heterogeneity": descriptive_heterogeneity,
        "scientific_review": {
            "status": "awaiting_researcher_review",
            "required_checks": list(REQUIRED_REVIEW_CHECKS),
        },
        "warnings": warnings,
    }
