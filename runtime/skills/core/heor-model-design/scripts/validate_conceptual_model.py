#!/usr/bin/env python3
"""Deterministically audit the AI4HEOR conceptual-model JSON contract."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ASSUMPTION_STATUS = {"unresolved", "proposed", "rejected"}


def _text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _text_list(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(_text(item) for item in value)


def audit(value: Any, expected_analysis_id: str | None = None) -> dict[str, Any]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return {"complete": False, "errors": ["artifact must be a JSON object"]}
    if value.get("schema_version") != "0.1.0":
        errors.append("schema_version must be 0.1.0")
    for field in ("model_id", "analysis_id", "objective"):
        if not _text(value.get(field)):
            errors.append(f"{field} is required")
    if expected_analysis_id is not None and value.get("analysis_id") != expected_analysis_id:
        errors.append("conceptual model analysis_id does not match the current analysis plan")
    if value.get("status") not in {"draft", "ready_for_human_review"}:
        errors.append("status is invalid")

    scope = value.get("scope")
    if not isinstance(scope, dict):
        errors.append("scope is required")
    else:
        for field in (
            "population", "intervention", "comparator", "perspective",
            "time_horizon", "jurisdiction", "decision_context",
        ):
            if not _text(scope.get(field)):
                errors.append(f"scope.{field} is required")
        if not _text_list(scope.get("outcomes")):
            errors.append("scope.outcomes must be a non-empty string array")
    if not _text_list(value.get("care_pathway")):
        errors.append("care_pathway must be a non-empty string array")

    model_type = value.get("model_type")
    if not isinstance(model_type, dict) or not _text(model_type.get("proposed")) or not _text(
        model_type.get("rationale")
    ):
        errors.append("model_type requires proposed and rationale")

    states = value.get("states")
    if not isinstance(states, list) or len(states) < 2:
        errors.append("at least two states are required")
        states = []
    state_ids: set[str] = set()
    absorbing: set[str] = set()
    for index, state in enumerate(states):
        label = f"states[{index}]"
        if not isinstance(state, dict):
            errors.append(f"{label} must be an object")
            continue
        state_id = state.get("id")
        if not _text(state_id) or state_id in state_ids:
            errors.append(f"{label}.id must be non-empty and unique")
        else:
            state_ids.add(state_id)
        if not _text(state.get("label")) or not _text(state.get("definition")):
            errors.append(f"{label} requires label and definition")
        if not isinstance(state.get("absorbing"), bool):
            errors.append(f"{label}.absorbing must be boolean")
        elif state.get("absorbing") and _text(state_id):
            absorbing.add(state_id)

    transitions = value.get("transitions")
    if not isinstance(transitions, list) or not transitions:
        errors.append("at least one transition is required")
        transitions = []
    transition_ids: set[str] = set()
    outgoing: set[str] = set()
    for index, transition in enumerate(transitions):
        label = f"transitions[{index}]"
        if not isinstance(transition, dict):
            errors.append(f"{label} must be an object")
            continue
        transition_id = transition.get("id")
        if not _text(transition_id) or transition_id in transition_ids:
            errors.append(f"{label}.id must be non-empty and unique")
        else:
            transition_ids.add(transition_id)
        from_id, to_id = transition.get("from"), transition.get("to")
        if from_id not in state_ids or to_id not in state_ids:
            errors.append(f"{label} references an unknown state")
        else:
            outgoing.add(from_id)
            if from_id in absorbing and from_id != to_id:
                errors.append(f"{label} leaves absorbing state {from_id}")
        if not _text(transition.get("trigger")):
            errors.append(f"{label}.trigger is required")
    missing_outgoing = sorted(state_ids - outgoing)
    if missing_outgoing:
        errors.append("states without outgoing transitions: " + ", ".join(missing_outgoing))

    assumptions = value.get("structural_assumptions")
    if not isinstance(assumptions, list) or not assumptions:
        errors.append("at least one structural assumption is required")
        assumptions = []
    assumption_ids: set[str] = set()
    unresolved: list[str] = []
    for index, assumption in enumerate(assumptions):
        label = f"structural_assumptions[{index}]"
        if not isinstance(assumption, dict):
            errors.append(f"{label} must be an object")
            continue
        assumption_id = assumption.get("id")
        if not _text(assumption_id) or assumption_id in assumption_ids:
            errors.append(f"{label}.id must be non-empty and unique")
        else:
            assumption_ids.add(assumption_id)
        if not _text(assumption.get("statement")) or not _text(assumption.get("rationale")):
            errors.append(f"{label} requires statement and rationale")
        status = assumption.get("status")
        if status not in ASSUMPTION_STATUS:
            errors.append(f"{label}.status is invalid")
        elif status == "unresolved" and _text(assumption_id):
            unresolved.append(assumption_id)

    alternatives = value.get("structural_alternatives")
    if not isinstance(alternatives, list) or not alternatives:
        errors.append("at least one structural alternative is required")
        alternatives = []
    alternative_ids: set[str] = set()
    for index, alternative in enumerate(alternatives):
        label = f"structural_alternatives[{index}]"
        if not isinstance(alternative, dict):
            errors.append(f"{label} must be an object")
            continue
        alternative_id = alternative.get("id")
        if not _text(alternative_id) or alternative_id in alternative_ids:
            errors.append(f"{label}.id must be non-empty and unique")
        else:
            alternative_ids.add(alternative_id)
        for field in ("description", "rationale", "expected_impact"):
            if not _text(alternative.get(field)):
                errors.append(f"{label}.{field} is required")

    evidence_links = value.get("evidence_links")
    if not isinstance(evidence_links, list):
        errors.append("evidence_links must be an array")
        evidence_links = []
    for index, link in enumerate(evidence_links):
        label = f"evidence_links[{index}]"
        if not isinstance(link, dict) or not _text(link.get("claim")) or not _text_list(
            link.get("source_ids")
        ):
            errors.append(f"{label} requires claim and source_ids")

    if not _text_list(value.get("validation_questions")):
        errors.append("validation_questions must be a non-empty string array")
    if unresolved:
        errors.append("unresolved structural assumptions: " + ", ".join(unresolved))

    return {
        "complete": not errors,
        "status": "complete" if not errors else "incomplete",
        "errors": errors,
        "state_count": len(states),
        "transition_count": len(transitions),
        "assumption_count": len(assumptions),
        "alternative_count": len(alternatives),
        "unresolved_assumptions": unresolved,
    }


def main(argv: list[str]) -> int:
    if len(argv) not in {2, 3}:
        print(
            "usage: validate_conceptual_model.py ARTIFACT.json [ANALYSIS_PLAN.json]",
            file=sys.stderr,
        )
        return 2
    try:
        value = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        expected_analysis_id = None
        if len(argv) == 3:
            plan = json.loads(Path(argv[2]).read_text(encoding="utf-8"))
            expected_analysis_id = plan.get("analysis_id")
            if not _text(expected_analysis_id):
                raise ValueError("analysis plan omitted analysis_id")
        result = audit(value, expected_analysis_id)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        result = {"complete": False, "status": "incomplete", "errors": [str(error)]}
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("complete") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
