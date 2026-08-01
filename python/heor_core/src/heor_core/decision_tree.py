"""Validated deterministic short-horizon decision-tree analysis."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any

from .model import (
    MAX_STRATEGIES,
    STRATEGY_ID_PATTERN,
    TOLERANCE,
    IncrementalResult,
    ModelValidationError,
    StrategyResult,
    _fully_incremental_analysis,
    _incremental,
    _optimal_at_threshold,
)


LEGACY_SCHEMA_VERSION = "0.1.0"
SCHEMA_VERSION = "0.2.0"
SUPPORTED_SCHEMA_VERSIONS = (LEGACY_SCHEMA_VERSION, SCHEMA_VERSION)
LEGACY_ENGINE_VERSION = "0.1.0"
ENGINE_VERSION = "0.2.0"
ANALYSIS_TYPE = "decision_tree"


@dataclass(frozen=True)
class EconomicBasis:
    currency: str
    price_year: int
    jurisdiction: str
    perspective: str

    @classmethod
    def from_dict(cls, raw: Any) -> "EconomicBasis":
        value = _mapping(raw, "economic_basis")
        _reject_unknown_fields(
            value,
            {"currency", "price_year", "jurisdiction", "perspective"},
            "economic_basis",
        )
        currency = value.get("currency")
        if (
            not isinstance(currency, str)
            or len(currency) != 3
            or not currency.isascii()
            or not currency.isalpha()
            or currency != currency.upper()
        ):
            raise ModelValidationError(
                "economic_basis.currency must be a three-letter uppercase ISO 4217 code"
            )
        price_year = _strict_int(
            value.get("price_year"), "economic_basis.price_year"
        )
        if not 1900 <= price_year <= 2100:
            raise ModelValidationError(
                "economic_basis.price_year must be from 1900 to 2100"
            )
        return cls(
            currency=currency,
            price_year=price_year,
            jurisdiction=_bounded_text(
                value.get("jurisdiction"), "economic_basis.jurisdiction"
            ),
            perspective=_bounded_text(
                value.get("perspective"), "economic_basis.perspective"
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "price_year": self.price_year,
            "jurisdiction": self.jurisdiction,
            "perspective": self.perspective,
        }


@dataclass(frozen=True)
class SourcedValue:
    value: float
    source_ids: tuple[str, ...]
    assumption_ids: tuple[str, ...]

    @classmethod
    def from_dict(cls, raw: Any, path: str) -> "SourcedValue":
        value = _mapping(raw, path)
        _reject_unknown_fields(
            value, {"value", "source_ids", "assumption_ids"}, path
        )
        return cls(
            value=_strict_float(value.get("value"), f"{path}.value"),
            source_ids=_id_tuple(value.get("source_ids"), f"{path}.source_ids"),
            assumption_ids=_id_tuple(
                value.get("assumption_ids"), f"{path}.assumption_ids"
            ),
        )

    def validate_provenance(
        self,
        path: str,
        proposed_assumption_ids: frozenset[str],
    ) -> None:
        if not self.source_ids and not self.assumption_ids:
            raise ModelValidationError(
                f"{path} must declare at least one source_id or proposed assumption_id"
            )
        unknown = set(self.assumption_ids) - proposed_assumption_ids
        if unknown:
            raise ModelValidationError(
                f"{path}.assumption_ids must identify declared proposed assumptions: "
                + ", ".join(sorted(unknown))
            )

    def provenance_dict(self) -> dict[str, list[str]]:
        return {
            "source_ids": list(self.source_ids),
            "assumption_ids": list(self.assumption_ids),
        }


@dataclass(frozen=True)
class DecisionTreeBranch:
    child_node_id: str
    probability: SourcedValue

    @classmethod
    def from_dict(cls, raw: Any, path: str) -> "DecisionTreeBranch":
        value = _mapping(raw, path)
        _reject_unknown_fields(
            value, {"child_node_id", "probability"}, path
        )
        return cls(
            child_node_id=str(value.get("child_node_id", "")),
            probability=SourcedValue.from_dict(
                value.get("probability"), f"{path}.probability"
            ),
        )


@dataclass(frozen=True)
class DecisionTreeNode:
    node_type: str
    branches: tuple[DecisionTreeBranch, ...]
    cost: SourcedValue | None
    qaly: SourcedValue | None

    @classmethod
    def from_dict(cls, raw: Any, path: str) -> "DecisionTreeNode":
        value = _mapping(raw, path)
        node_type = str(value.get("type", ""))
        allowed_fields = (
            {"type", "branches"}
            if node_type == "chance"
            else {"type", "cost", "qaly"}
            if node_type == "terminal"
            else {"type"}
        )
        _reject_unknown_fields(value, allowed_fields, path)
        raw_branches = value.get("branches", [])
        if not isinstance(raw_branches, list):
            raise ModelValidationError(f"{path}.branches must be an array")
        return cls(
            node_type=node_type,
            branches=tuple(
                DecisionTreeBranch.from_dict(branch, f"{path}.branches[{index}]")
                for index, branch in enumerate(raw_branches)
            ),
            cost=(
                SourcedValue.from_dict(value.get("cost"), f"{path}.cost")
                if "cost" in value
                else None
            ),
            qaly=(
                SourcedValue.from_dict(value.get("qaly"), f"{path}.qaly")
                if "qaly" in value
                else None
            ),
        )


@dataclass(frozen=True)
class DecisionTreeStrategy:
    name: str
    root_node_id: str
    nodes: tuple[tuple[str, DecisionTreeNode], ...]

    @property
    def node_map(self) -> dict[str, DecisionTreeNode]:
        return dict(self.nodes)

    @classmethod
    def from_dict(cls, raw: Any, path: str) -> "DecisionTreeStrategy":
        value = _mapping(raw, path)
        _reject_unknown_fields(value, {"name", "root_node_id", "nodes"}, path)
        raw_nodes = _mapping(value.get("nodes"), f"{path}.nodes")
        return cls(
            name=str(value.get("name", "")),
            root_node_id=str(value.get("root_node_id", "")),
            nodes=tuple(
                (
                    str(node_id),
                    DecisionTreeNode.from_dict(node, f"{path}.nodes.{node_id}"),
                )
                for node_id, node in raw_nodes.items()
            ),
        )


@dataclass(frozen=True)
class DecisionTreeSpecification:
    schema_version: str
    analysis_type: str
    analysis_id: str
    reference_case_id: str
    reference_case_status: str
    economic_basis: EconomicBasis | None
    time_horizon_years: float
    cost_discount_rate: float
    outcome_discount_rate: float
    half_cycle_correction: bool
    willingness_to_pay: float | None
    strategy_order: tuple[str, ...]
    baseline_strategy_id: str
    proposed_assumption_ids: frozenset[str]
    strategies: tuple[tuple[str, DecisionTreeStrategy], ...]

    @classmethod
    def from_dict(cls, raw: Any) -> "DecisionTreeSpecification":
        value = _mapping(raw, "analysis")
        schema_version = str(value.get("schema_version", ""))
        allowed_fields = {
            "schema_version",
            "analysis_type",
            "analysis_id",
            "reference_case",
            "time_horizon_years",
            "discount_rates",
            "half_cycle_correction",
            "willingness_to_pay",
            "strategy_order",
            "baseline_strategy_id",
            "assumptions",
            "strategies",
        }
        if schema_version == SCHEMA_VERSION:
            allowed_fields.add("economic_basis")
        _reject_unknown_fields(
            value,
            allowed_fields,
            "analysis",
        )
        if "approvals" in value:
            raise ModelValidationError(
                "approvals are not analysis inputs; desktop workflow authorization is app-owned"
            )
        reference_case = _mapping(value.get("reference_case"), "reference_case")
        _reject_unknown_fields(reference_case, {"id", "status"}, "reference_case")
        discount_rates = _mapping(value.get("discount_rates"), "discount_rates")
        _reject_unknown_fields(
            discount_rates, {"costs", "outcomes"}, "discount_rates"
        )
        raw_order = value.get("strategy_order")
        if not isinstance(raw_order, list):
            raise ModelValidationError("strategy_order must be an array")
        strategy_order = tuple(str(item) for item in raw_order)
        raw_strategies = _mapping(value.get("strategies"), "strategies")
        if set(raw_strategies) != set(strategy_order):
            raise ModelValidationError(
                "strategies must contain exactly the ids declared by strategy_order"
            )
        raw_assumptions = value.get("assumptions", [])
        if not isinstance(raw_assumptions, list):
            raise ModelValidationError("assumptions must be an array")
        assumption_statuses: dict[str, str] = {}
        for index, raw_assumption in enumerate(raw_assumptions):
            assumption = _mapping(raw_assumption, f"assumptions[{index}]")
            _reject_unknown_fields(
                assumption,
                {"id", "status", "statement", "reason"},
                f"assumptions[{index}]",
            )
            assumption_id = str(assumption.get("id", ""))
            if not assumption_id:
                raise ModelValidationError(f"assumptions[{index}].id must not be empty")
            if assumption_id in assumption_statuses:
                raise ModelValidationError("assumption ids must be unique")
            assumption_statuses[assumption_id] = str(assumption.get("status", ""))
        specification = cls(
            schema_version=schema_version,
            analysis_type=str(value.get("analysis_type", "")),
            analysis_id=str(value.get("analysis_id", "")),
            reference_case_id=str(reference_case.get("id", "")),
            reference_case_status=str(reference_case.get("status", "")),
            economic_basis=(
                EconomicBasis.from_dict(value.get("economic_basis"))
                if schema_version == SCHEMA_VERSION
                else None
            ),
            time_horizon_years=_strict_float(
                value.get("time_horizon_years"), "time_horizon_years"
            ),
            cost_discount_rate=_strict_float(
                discount_rates.get("costs"), "discount_rates.costs"
            ),
            outcome_discount_rate=_strict_float(
                discount_rates.get("outcomes"), "discount_rates.outcomes"
            ),
            half_cycle_correction=_strict_bool(
                value.get("half_cycle_correction"), "half_cycle_correction"
            ),
            willingness_to_pay=(
                None
                if value.get("willingness_to_pay") is None
                else _strict_float(
                    value.get("willingness_to_pay"), "willingness_to_pay"
                )
            ),
            strategy_order=strategy_order,
            baseline_strategy_id=str(value.get("baseline_strategy_id", "")),
            proposed_assumption_ids=frozenset(
                assumption_id
                for assumption_id, status in assumption_statuses.items()
                if status == "proposed"
            ),
            strategies=tuple(
                (
                    strategy_id,
                    DecisionTreeStrategy.from_dict(
                        raw_strategies[strategy_id], f"strategies.{strategy_id}"
                    ),
                )
                for strategy_id in strategy_order
            ),
        )
        specification.validate()
        return specification

    def validate(self) -> None:
        if self.schema_version not in SUPPORTED_SCHEMA_VERSIONS:
            raise ModelValidationError(
                f"unsupported decision tree schema_version {self.schema_version!r}; expected one of {SUPPORTED_SCHEMA_VERSIONS!r}"
            )
        if self.schema_version == SCHEMA_VERSION and self.economic_basis is None:
            raise ModelValidationError(
                f"economic_basis is required for decision tree schema {SCHEMA_VERSION}"
            )
        if self.schema_version == LEGACY_SCHEMA_VERSION and self.economic_basis is not None:
            raise ModelValidationError(
                "legacy decision tree schema must not claim an economic basis"
            )
        if self.analysis_type != ANALYSIS_TYPE:
            raise ModelValidationError(
                f"analysis_type must be {ANALYSIS_TYPE!r}"
            )
        if not self.analysis_id.strip():
            raise ModelValidationError("analysis_id must not be empty")
        if not self.reference_case_id.strip():
            raise ModelValidationError("reference_case.id must not be empty")
        if self.reference_case_status not in {"current", "draft", "custom"}:
            raise ModelValidationError(
                "reference_case.status must be current, draft, or custom"
            )
        if not 0.0 < self.time_horizon_years <= 1.0:
            raise ModelValidationError(
                "decision tree time_horizon_years must be greater than zero and at most one"
            )
        if self.cost_discount_rate != 0.0 or self.outcome_discount_rate != 0.0:
            raise ModelValidationError(
                "decision tree discount rates must both be zero"
            )
        if self.half_cycle_correction:
            raise ModelValidationError(
                "decision tree does not support half_cycle_correction"
            )
        if self.willingness_to_pay is not None and self.willingness_to_pay < 0.0:
            raise ModelValidationError("willingness_to_pay must not be negative")
        if not 2 <= len(self.strategy_order) <= MAX_STRATEGIES:
            raise ModelValidationError(
                f"strategy_order must contain from 2 to {MAX_STRATEGIES} strategy ids"
            )
        if len(set(self.strategy_order)) != len(self.strategy_order):
            raise ModelValidationError("strategy_order ids must be unique")
        if any(
            not STRATEGY_ID_PATTERN.fullmatch(strategy_id)
            for strategy_id in self.strategy_order
        ):
            raise ModelValidationError(
                "strategy ids must start with a lowercase letter and contain only lowercase letters, digits, underscores, or hyphens"
            )
        if self.baseline_strategy_id != self.strategy_order[0]:
            raise ModelValidationError(
                "baseline_strategy_id must be the first strategy_order entry"
            )
        strategy_ids = tuple(strategy_id for strategy_id, _ in self.strategies)
        if strategy_ids != self.strategy_order:
            raise ModelValidationError(
                "strategies must contain exactly the ids declared by strategy_order"
            )
        names = tuple(strategy.name for _, strategy in self.strategies)
        if any(not name.strip() for name in names):
            raise ModelValidationError("strategy names must not be empty")
        if len(set(names)) != len(names):
            raise ModelValidationError("strategy names must be unique")
        for strategy_id, strategy in self.strategies:
            _validate_strategy(
                strategy_id,
                strategy,
                self.proposed_assumption_ids,
            )


@dataclass(frozen=True)
class DecisionTreeStrategyResult:
    name: str
    total_cost: float
    total_qaly: float
    net_monetary_benefit: float | None
    calculation_trace: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "total_cost": self.total_cost,
            "total_qaly": self.total_qaly,
            "net_monetary_benefit": self.net_monetary_benefit,
            "calculation_trace": [dict(item) for item in self.calculation_trace],
        }


@dataclass(frozen=True)
class DecisionTreeResult:
    specification: DecisionTreeSpecification
    strategy_results: tuple[tuple[str, DecisionTreeStrategyResult], ...]
    pairwise_vs_baseline: tuple[tuple[str, IncrementalResult], ...]
    fully_incremental_analysis: tuple[dict[str, Any], ...]
    optimal_at_primary_threshold: dict[str, Any] | None

    def to_dict(self) -> dict[str, Any]:
        specification = self.specification
        warnings = [
            "Decision-tree structure, numeric inputs, and assumptions require researcher confirmation before formal use.",
            "Reference-case compliance has not been assessed by the deterministic engine.",
        ]
        if specification.reference_case_status == "draft":
            warnings.append(
                "Draft reference case: this result must not be presented as compliance with current guidance."
            )
        if specification.schema_version == LEGACY_SCHEMA_VERSION:
            warnings.append(
                "Legacy analysis schema: monetary results have no declared economic basis and are exploratory only."
            )
        result = {
            "analysis_id": specification.analysis_id,
            "analysis_type": specification.analysis_type,
            "engine_version": (
                LEGACY_ENGINE_VERSION
                if specification.schema_version == LEGACY_SCHEMA_VERSION
                else ENGINE_VERSION
            ),
            "schema_version": specification.schema_version,
            "reference_case": {
                "id": specification.reference_case_id,
                "status": specification.reference_case_status,
                "compliance_assessed": False,
            },
            "time_horizon_years": specification.time_horizon_years,
            "discount_rates": {
                "costs": specification.cost_discount_rate,
                "outcomes": specification.outcome_discount_rate,
            },
            "half_cycle_correction": specification.half_cycle_correction,
            "calculation_classification": "deterministic_decision_tree",
            "warnings": warnings,
            "strategy_order": list(specification.strategy_order),
            "baseline_strategy_id": specification.baseline_strategy_id,
            "strategies": {
                strategy_id: result.to_dict()
                for strategy_id, result in self.strategy_results
            },
            "pairwise_vs_baseline": {
                strategy_id: incremental.to_dict()
                for strategy_id, incremental in self.pairwise_vs_baseline
            },
            "fully_incremental_analysis": [
                dict(row) for row in self.fully_incremental_analysis
            ],
            "optimal_at_primary_threshold": self.optimal_at_primary_threshold,
        }
        if specification.economic_basis is not None:
            result["economic_basis"] = specification.economic_basis.to_dict()
        return result


def run_decision_tree(
    specification: DecisionTreeSpecification,
) -> DecisionTreeResult:
    """Run a validated finite probability tree without AI or network access."""

    specification.validate()
    strategy_results = tuple(
        (
            strategy_id,
            _run_strategy(strategy, specification.willingness_to_pay),
        )
        for strategy_id, strategy in specification.strategies
    )
    generic_results = {
        strategy_id: StrategyResult(
            name=result.name,
            total_cost=result.total_cost,
            total_qaly=result.total_qaly,
            net_monetary_benefit=result.net_monetary_benefit,
            occupancy=(),
            transition_mode="decision_tree",
            transition_schedule_start_cycles=(),
        )
        for strategy_id, result in strategy_results
    }
    baseline = generic_results[specification.baseline_strategy_id]
    pairwise = tuple(
        (
            strategy_id,
            _incremental(
                baseline,
                generic_results[strategy_id],
                specification.willingness_to_pay,
            ),
        )
        for strategy_id in specification.strategy_order
        if strategy_id != specification.baseline_strategy_id
    )
    return DecisionTreeResult(
        specification=specification,
        strategy_results=strategy_results,
        pairwise_vs_baseline=pairwise,
        fully_incremental_analysis=_fully_incremental_analysis(
            specification.strategy_order,
            generic_results,
            specification.willingness_to_pay,
        ),
        optimal_at_primary_threshold=_optimal_at_threshold(
            specification.strategy_order,
            generic_results,
            specification.willingness_to_pay,
        ),
    )


def _validate_strategy(
    strategy_id: str,
    strategy: DecisionTreeStrategy,
    proposed_assumption_ids: frozenset[str],
) -> None:
    nodes = strategy.node_map
    path = f"strategies.{strategy_id}"
    if not nodes:
        raise ModelValidationError(f"{path}.nodes must not be empty")
    if strategy.root_node_id not in nodes:
        raise ModelValidationError(f"{path}.root_node_id must identify a node")
    parent_counts = {node_id: 0 for node_id in nodes}
    for node_id, node in strategy.nodes:
        node_path = f"{path}.nodes.{node_id}"
        if not STRATEGY_ID_PATTERN.fullmatch(node_id):
            raise ModelValidationError(
                f"{node_path} id must use lowercase letters, digits, underscores, or hyphens"
            )
        if node.node_type == "chance":
            if len(node.branches) < 2:
                raise ModelValidationError(
                    f"{node_path}.branches must contain at least two branches"
                )
            if node.cost is not None or node.qaly is not None:
                raise ModelValidationError(
                    f"{node_path} chance nodes must not contain cost or qaly"
                )
            probability_sum = 0.0
            for index, branch in enumerate(node.branches):
                branch_path = f"{node_path}.branches[{index}]"
                if branch.child_node_id not in nodes:
                    raise ModelValidationError(
                        f"{branch_path}.child_node_id must identify a node"
                    )
                probability = branch.probability.value
                if not 0.0 <= probability <= 1.0:
                    raise ModelValidationError(
                        f"{branch_path}.probability.value must be from zero to one"
                    )
                branch.probability.validate_provenance(
                    f"{branch_path}.probability", proposed_assumption_ids
                )
                probability_sum += probability
                parent_counts[branch.child_node_id] += 1
            if abs(probability_sum - 1.0) > TOLERANCE:
                raise ModelValidationError(
                    f"{node_path}.branches probabilities must sum to one within {TOLERANCE}"
                )
        elif node.node_type == "terminal":
            if node.branches:
                raise ModelValidationError(
                    f"{node_path} terminal nodes must not contain branches"
                )
            if node.cost is None or node.qaly is None:
                raise ModelValidationError(
                    f"{node_path} terminal nodes require cost and qaly"
                )
            if node.cost.value < 0.0:
                raise ModelValidationError(f"{node_path}.cost.value must not be negative")
            if not -1.0 <= node.qaly.value <= 1.0:
                raise ModelValidationError(
                    f"{node_path}.qaly.value must be from -1 to 1"
                )
            node.cost.validate_provenance(
                f"{node_path}.cost", proposed_assumption_ids
            )
            node.qaly.validate_provenance(
                f"{node_path}.qaly", proposed_assumption_ids
            )
        else:
            raise ModelValidationError(
                f"{node_path}.type must be 'chance' or 'terminal'"
            )
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> None:
        if node_id in visiting:
            raise ModelValidationError(f"{path}.nodes must not contain a cycle")
        if node_id in visited:
            return
        visiting.add(node_id)
        for branch in nodes[node_id].branches:
            visit(branch.child_node_id)
        visiting.remove(node_id)
        visited.add(node_id)

    visit(strategy.root_node_id)
    if parent_counts[strategy.root_node_id] != 0:
        raise ModelValidationError(f"{path}.root_node_id must not have a parent")
    wrong_parent_counts = {
        node_id: count
        for node_id, count in parent_counts.items()
        if node_id != strategy.root_node_id and count != 1
    }
    if wrong_parent_counts:
        raise ModelValidationError(
            f"{path}.nodes must form one tree; non-root nodes require exactly one parent"
        )
    if visited != set(nodes):
        raise ModelValidationError(f"{path}.nodes must all be reachable from root_node_id")


def _run_strategy(
    strategy: DecisionTreeStrategy,
    willingness_to_pay: float | None,
) -> DecisionTreeStrategyResult:
    nodes = strategy.node_map
    trace: list[dict[str, Any]] = []
    total_cost = 0.0
    total_qaly = 0.0
    terminal_probability = 0.0

    def visit(node_id: str, reached_probability: float) -> None:
        nonlocal total_cost, total_qaly, terminal_probability
        node = nodes[node_id]
        if node.node_type == "chance":
            trace.append(
                {
                    "node_id": node_id,
                    "node_type": "chance",
                    "reached_probability": reached_probability,
                    "branches": [
                        {
                            "child_node_id": branch.child_node_id,
                            "conditional_probability": branch.probability.value,
                            "child_reached_probability": reached_probability
                            * branch.probability.value,
                            "probability_provenance": branch.probability.provenance_dict(),
                        }
                        for branch in node.branches
                    ],
                }
            )
            for branch in node.branches:
                visit(
                    branch.child_node_id,
                    reached_probability * branch.probability.value,
                )
            return
        if node.cost is None or node.qaly is None:
            raise ModelValidationError(f"{node_id}: terminal node is incomplete")
        cost_contribution = reached_probability * node.cost.value
        qaly_contribution = reached_probability * node.qaly.value
        terminal_probability += reached_probability
        total_cost += cost_contribution
        total_qaly += qaly_contribution
        trace.append(
            {
                "node_id": node_id,
                "node_type": "terminal",
                "reached_probability": reached_probability,
                "path_total_cost": node.cost.value,
                "path_total_qaly": node.qaly.value,
                "expected_cost_contribution": cost_contribution,
                "expected_qaly_contribution": qaly_contribution,
                "cost_provenance": node.cost.provenance_dict(),
                "qaly_provenance": node.qaly.provenance_dict(),
            }
        )

    visit(strategy.root_node_id, 1.0)
    if abs(terminal_probability - 1.0) > TOLERANCE:
        raise ModelValidationError(
            f"{strategy.name}: terminal probabilities must sum to one"
        )
    if not all(isfinite(value) for value in (total_cost, total_qaly)):
        raise ModelValidationError(
            f"{strategy.name}: expected cost and QALY must be finite"
        )
    net_monetary_benefit = (
        None
        if willingness_to_pay is None
        else willingness_to_pay * total_qaly - total_cost
    )
    if net_monetary_benefit is not None and not isfinite(net_monetary_benefit):
        raise ModelValidationError(
            f"{strategy.name}: net monetary benefit must be finite"
        )
    return DecisionTreeStrategyResult(
        name=strategy.name,
        total_cost=total_cost,
        total_qaly=total_qaly,
        net_monetary_benefit=net_monetary_benefit,
        calculation_trace=tuple(trace),
    )


def _mapping(raw: Any, path: str) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ModelValidationError(f"{path} must be an object")
    return raw


def _reject_unknown_fields(
    value: dict[str, Any], allowed: set[str], path: str
) -> None:
    unknown = set(value) - allowed
    if unknown:
        raise ModelValidationError(
            f"{path} contains unsupported field(s): " + ", ".join(sorted(unknown))
        )


def _strict_float(raw: Any, path: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ModelValidationError(f"{path} must be a number")
    value = float(raw)
    if not isfinite(value):
        raise ModelValidationError(f"{path} must be finite")
    return value


def _strict_bool(raw: Any, path: str) -> bool:
    if not isinstance(raw, bool):
        raise ModelValidationError(f"{path} must be a boolean")
    return raw


def _strict_int(raw: Any, path: str) -> int:
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise ModelValidationError(f"{path} must be an integer")
    return raw


def _bounded_text(raw: Any, path: str) -> str:
    if not isinstance(raw, str) or not raw or raw != raw.strip():
        raise ModelValidationError(
            f"{path} must be a non-empty string without surrounding whitespace"
        )
    if len(raw) > 160 or any(ord(character) < 32 or ord(character) == 127 for character in raw):
        raise ModelValidationError(
            f"{path} must contain at most 160 characters and no control characters"
        )
    return raw


def _id_tuple(raw: Any, path: str) -> tuple[str, ...]:
    if not isinstance(raw, list):
        raise ModelValidationError(f"{path} must be an array")
    if any(not isinstance(item, str) for item in raw):
        raise ModelValidationError(f"{path} must contain string ids")
    values = tuple(raw)
    if any(not item.strip() for item in values):
        raise ModelValidationError(f"{path} must contain non-empty ids")
    if len(set(values)) != len(values):
        raise ModelValidationError(f"{path} ids must be unique")
    return values
