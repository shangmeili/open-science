#!/usr/bin/env python3
"""Create a complete synthetic HEOR workspace fixture for desktop acceptance.

The generated numbers are contract-test assumptions, not clinical or economic
evidence. The fixture exists to exercise AI4HEOR's review and deterministic
calculation path without touching a researcher's project.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
GOLDEN = ROOT / "python/heor_core/golden_cases"
PROFILE = (
    ROOT
    / "runtime/skills/core/heor-reference-case/assets/profiles/CN-2020-current.json"
)
ASSUMPTION_ID = "synthetic-acceptance-inputs"


def canonical_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def model_value(plan: dict, path: str) -> object:
    current: object = plan
    for token in path.split("."):
        if not isinstance(current, dict):
            raise ValueError(f"{path} does not resolve in the analysis plan")
        current = current[token]
    return current


def provenance_mapping(plan: dict, path: str) -> dict:
    value = model_value(plan, path)
    mapping = {
        "path": path,
        "assumption_ids": [ASSUMPTION_ID],
        "unit": {
            "cycles": "cycles",
            "cycle_length_years": "years/cycle",
            "discount_rates.costs": "proportion/year",
            "discount_rates.outcomes": "proportion/year",
            "half_cycle_correction": "boolean",
            "willingness_to_pay": "CNY/QALY",
        }.get(path, "model input"),
        "jurisdiction": "China",
        "selection_rationale": (
            "Synthetic value retained only to exercise the AI4HEOR acceptance contract."
        ),
        "uncertainty_status": (
            "distribution_available"
            if path
            in {
                "strategies.intervention.state_costs",
                "strategies.intervention.transition_matrix",
            }
            else "fixed"
        ),
        "derivation": {
            "method": "explicit_assumption",
            "model_value": value,
        },
    }
    if path.endswith("state_costs") or path == "willingness_to_pay":
        values = value if isinstance(value, list) else [value]
        mapping.update({"currency": "CNY", "price_year": 2026})
        mapping["monetary_adjustments"] = [
            {
                **({"target_index": index} if isinstance(value, list) else {}),
                "source_value": item,
                "factor": 1.0,
                "source_currency": "CNY",
                "source_price_year": 2026,
                "method": "none",
                "basis_ids": [],
            }
            for index, item in enumerate(values)
        ]
    return mapping


def analysis_plan(assessment_sha256: str) -> dict:
    plan = json.loads((GOLDEN / "two_strategy_markov.json").read_text())
    plan.update(
        {
            "input_status": "ready_for_human_review",
            "decision_problem": {
                "title": "Synthetic acceptance test of a new treatment versus standard care",
                "population": "Synthetic eligible adult cohort",
                "intervention": "New treatment",
                "comparator": "Standard care",
                "perspective": "Chinese healthcare system",
                "time_horizon_years": 3,
                "outcome": "QALY",
                "jurisdiction": "China",
            },
            "reference_case_assessment": {
                "path": "heor/reference-case-assessment.json",
                "content_sha256": assessment_sha256,
            },
            "uncertainty_analysis": {"path": "heor/uncertainty-plan.json"},
            "budget_impact_analysis": {"path": "heor/budget-impact-plan.json"},
            "methodology": {
                "health_outcomes": {
                    "measure": "QALY",
                    "data_descriptive_system": "Synthetic utility inputs",
                    "value_set": "Not applicable to this synthetic fixture",
                    "valuation_population": "Not applicable to this synthetic fixture",
                    "respondent": "Not applicable to this synthetic fixture",
                    "mapping_method": "None",
                    "reference_case_departure": None,
                },
                "cost_scope": {
                    "included_categories": [
                        "Synthetic direct medical treatment and disease-management costs"
                    ],
                    "perspective_alignment": (
                        "Only synthetic direct medical costs are included for the acceptance test."
                    ),
                    "exclusions": ["Indirect and non-medical costs"],
                },
                "uncertainty_analysis": {
                    "deterministic": {
                        "planned": True,
                        "input_paths": [
                            "strategies.intervention.state_costs",
                            "strategies.intervention.transition_matrix",
                        ],
                    },
                    "probabilistic": {
                        "planned": True,
                        "input_paths": [
                            "strategies.intervention.state_costs",
                            "strategies.intervention.transition_matrix",
                        ],
                        "iterations": 1000,
                    },
                    "structural_scenarios": ["five-year-horizon"],
                },
            },
            "evidence_sources": [],
            "assumptions": [
                {
                    "id": ASSUMPTION_ID,
                    "statement": (
                        "Every numeric input is synthetic and is used only for product acceptance testing."
                    ),
                    "reason": (
                        "The fixture must be reproducible without implying clinical evidence or a policy conclusion."
                    ),
                    "status": "proposed",
                }
            ],
        }
    )
    required = [
        "cycles",
        "cycle_length_years",
        "discount_rates.costs",
        "discount_rates.outcomes",
        "half_cycle_correction",
        "strategies.comparator.initial_distribution",
        "strategies.comparator.transition_matrix",
        "strategies.comparator.state_costs",
        "strategies.comparator.state_utilities",
        "strategies.intervention.initial_distribution",
        "strategies.intervention.transition_matrix",
        "strategies.intervention.state_costs",
        "strategies.intervention.state_utilities",
        "willingness_to_pay",
    ]
    plan["input_provenance"] = [provenance_mapping(plan, path) for path in required]
    return plan


def conceptual_model() -> dict:
    return {
        "schema_version": "0.1.0",
        "model_id": "synthetic-acceptance-conceptual-model",
        "analysis_id": "golden-two-strategy-markov",
        "status": "ready_for_human_review",
        "objective": (
            "Exercise the complete AI4HEOR review and deterministic calculation workflow."
        ),
        "scope": {
            "population": "Synthetic eligible adult cohort",
            "intervention": "New treatment",
            "comparator": "Standard care",
            "perspective": "Chinese healthcare system",
            "time_horizon": "Three years, selected only for a bounded acceptance test",
            "outcomes": ["QALY", "cost"],
            "jurisdiction": "China",
            "decision_context": "Product acceptance testing; not a reimbursement decision",
        },
        "care_pathway": [
            "Enter the stable state",
            "Remain stable, progress, or die",
            "Remain progressed or die",
        ],
        "model_type": {
            "proposed": "cohort_state_transition",
            "rationale": (
                "Three mutually exclusive states provide a compact deterministic test case."
            ),
        },
        "states": [
            {
                "id": "stable",
                "label": "Stable",
                "definition": "Synthetic cohort without progression",
                "absorbing": False,
            },
            {
                "id": "progressed",
                "label": "Progressed",
                "definition": "Synthetic cohort after progression",
                "absorbing": False,
            },
            {
                "id": "dead",
                "label": "Dead",
                "definition": "Absorbing all-cause death state",
                "absorbing": True,
            },
        ],
        "transitions": [
            {"id": "stable-stable", "from": "stable", "to": "stable", "trigger": "No event"},
            {"id": "stable-progressed", "from": "stable", "to": "progressed", "trigger": "Progression"},
            {"id": "stable-dead", "from": "stable", "to": "dead", "trigger": "Death"},
            {"id": "progressed-progressed", "from": "progressed", "to": "progressed", "trigger": "No death"},
            {"id": "progressed-dead", "from": "progressed", "to": "dead", "trigger": "Death"},
            {"id": "dead-dead", "from": "dead", "to": "dead", "trigger": "Absorbing state"},
        ],
        "structural_assumptions": [
            {
                "id": "memoryless-synthetic-model",
                "statement": "Transition probabilities depend only on the current state.",
                "rationale": "Required for this bounded cohort state-transition fixture.",
                "status": "proposed",
            }
        ],
        "structural_alternatives": [
            {
                "id": "partitioned-survival-alternative",
                "description": "Partitioned survival structure",
                "rationale": "Recorded to prove that structural alternatives are not hidden.",
                "expected_impact": "Could alter state occupancy and extrapolation.",
            }
        ],
        "evidence_links": [
            {
                "claim": "All values and pathways are synthetic acceptance assumptions.",
                "source_ids": [ASSUMPTION_ID],
            }
        ],
        "validation_plan": {
            "face": ["Confirm the synthetic state definitions and pathway are internally coherent."],
            "internal": ["Check probability mass, boundary values, hashes, and repeat-run equality."],
            "external": ["No external validity claim is made for this synthetic fixture."],
        },
        "validation_questions": [
            "Does the workbench preserve the explicit synthetic and non-decision boundary?"
        ],
    }


def reference_assessment(profile: dict, profile_sha256: str) -> dict:
    return {
        "schema_version": "0.1.0",
        "assessment_id": "synthetic-acceptance-cn-2020",
        "analysis_id": "golden-two-strategy-markov",
        "status": "ready_for_human_review",
        "assessed_on": "2026-07-21",
        "profile": {
            "id": profile["id"],
            "revision": profile["revision"],
            "status": profile["status"],
            "content_sha256": profile_sha256,
        },
        "requirements": [
            {
                "requirement_id": requirement["id"],
                "status": "met",
                "rationale": (
                    "The current synthetic plan and conceptual model expose this field for workflow testing."
                ),
                "evidence_paths": [
                    "heor/analysis-plan.json",
                    "heor/conceptual-model.json",
                ],
            }
            for requirement in profile["requirements"]
        ],
        "limitations": [
            "This matrix tests product controls only and does not establish guideline compliance."
        ],
    }


def build(output: Path) -> dict:
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"output directory is not empty: {output}")
    heor = output / "heor"
    heor.mkdir(parents=True, exist_ok=True)

    profile_raw = PROFILE.read_bytes()
    profile = json.loads(profile_raw)
    assessment = reference_assessment(profile, digest(profile_raw))
    assessment_raw = canonical_bytes(assessment)
    plan = analysis_plan(digest(assessment_raw))
    plan_raw = canonical_bytes(plan)

    uncertainty = json.loads((GOLDEN / "two_strategy_uncertainty.json").read_text())
    uncertainty["base_analysis"]["content_sha256"] = digest(plan_raw)
    for parameter in uncertainty["parameters"]:
        parameter["probabilistic"]["basis_ids"] = [ASSUMPTION_ID]

    budget = json.loads((GOLDEN / "two_strategy_budget_impact.json").read_text())
    budget["base_analysis"]["content_sha256"] = digest(plan_raw)

    artifacts = {
        "heor/analysis-plan.json": plan_raw,
        "heor/conceptual-model.json": canonical_bytes(conceptual_model()),
        "heor/reference-case-assessment.json": assessment_raw,
        "heor/uncertainty-plan.json": canonical_bytes(uncertainty),
        "heor/budget-impact-plan.json": canonical_bytes(budget),
    }
    for relative, raw in artifacts.items():
        target = output / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)

    (output / "ACCEPTANCE_FIXTURE.txt").write_text(
        "AI4HEOR synthetic acceptance fixture.\n"
        "No value is clinical evidence and no output is a reimbursement, pricing, or policy conclusion.\n"
    )
    return {
        "output": str(output.resolve()),
        "analysis_id": plan["analysis_id"],
        "analysis_plan_sha256": digest(plan_raw),
        "artifacts": {
            relative: digest(raw) for relative, raw in sorted(artifacts.items())
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--replace",
        action="store_true",
        help="replace an existing fixture directory (never use for a research project)",
    )
    args = parser.parse_args()
    if args.output.exists() and args.replace:
        shutil.rmtree(args.output)
    summary = build(args.output)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
