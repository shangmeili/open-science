#!/usr/bin/env python3
"""Validate an AI4HEOR survival extrapolation review without selecting a curve."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any


SAFE_ID = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
FAMILIES = {
    "exponential",
    "weibull",
    "gompertz",
    "gamma",
    "generalized_gamma",
    "generalized_f",
    "lognormal",
    "loglogistic",
}
TOP_LEVEL = {
    "schema_version",
    "review_id",
    "status",
    "context",
    "source_data",
    "pre_specification",
    "execution",
    "models",
    "diagnostics",
    "structural_scenarios",
    "analyst_recommendation",
    "limitations",
    "human_gate",
}


def text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def number(value: Any, *, minimum: float | None = None) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    value = float(value)
    return math.isfinite(value) and (minimum is None or value >= minimum)


def exact_object(value: Any, fields: set[str], label: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return False
    if set(value) != fields:
        errors.append(f"{label} fields are not the exact supported contract")
        return False
    return True


def hash_file(workspace: Path | None, path: Any, digest: Any, label: str, errors: list[str]) -> None:
    if not text(path) or not isinstance(digest, str) or not SHA256.fullmatch(digest):
        errors.append(f"{label} requires a relative path and lowercase SHA-256")
        return
    candidate = Path(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        errors.append(f"{label} path must stay inside the workspace")
        return
    if workspace is None:
        return
    resolved = (workspace / candidate).resolve()
    if not resolved.is_relative_to(workspace.resolve()) or not resolved.is_file():
        errors.append(f"{label} file is missing from the workspace")
        return
    actual = hashlib.sha256(resolved.read_bytes()).hexdigest()
    if actual != digest:
        errors.append(f"{label} SHA-256 does not match the current file")


def audit(value: Any, workspace: Path | None = None) -> dict[str, Any]:
    errors: list[str] = []
    if not exact_object(value, TOP_LEVEL, "review", errors):
        return {"complete": False, "errors": errors, "candidate_models": 0, "converged_models": 0}

    if value["schema_version"] != "0.1.0":
        errors.append("schema_version must be 0.1.0")
    if not isinstance(value["review_id"], str) or not SAFE_ID.fullmatch(value["review_id"]):
        errors.append("review_id must be a safe lowercase identifier")
    if value["status"] not in {"draft", "ready_for_human_review"}:
        errors.append("status must be draft or ready_for_human_review")

    context_fields = {
        "endpoint", "population", "curve_label", "time_origin", "time_unit",
        "observed_follow_up", "model_horizon",
    }
    context = value["context"]
    if exact_object(context, context_fields, "context", errors):
        for field in ("endpoint", "population", "curve_label", "time_origin"):
            if not text(context[field]):
                errors.append(f"context.{field} must be non-empty")
        if context["time_unit"] not in {"days", "weeks", "months", "years"}:
            errors.append("context.time_unit is unsupported")
        observed = context["observed_follow_up"]
        horizon = context["model_horizon"]
        if not number(observed, minimum=0) or float(observed) <= 0:
            errors.append("context.observed_follow_up must be positive")
        if not number(horizon, minimum=0) or not number(observed, minimum=0) or float(horizon) <= float(observed):
            errors.append("context.model_horizon must exceed observed_follow_up")

    source_fields = {
        "classification", "execution_boundary", "format", "path", "sha256",
        "time_variable", "event_definition", "censor_definition",
    }
    source = value["source_data"]
    if exact_object(source, source_fields, "source_data", errors):
        if source["classification"] not in {"public", "non_sensitive", "restricted", "unknown"}:
            errors.append("source_data.classification is unsupported")
        if source["execution_boundary"] != "local_only":
            errors.append("source_data.execution_boundary must be local_only")
        if source["format"] != "precomputed_survival_fit_bundle":
            errors.append("source_data.format must be precomputed_survival_fit_bundle")
        for field in ("time_variable", "event_definition", "censor_definition"):
            if not text(source[field]):
                errors.append(f"source_data.{field} must be non-empty")
        hash_file(workspace, source["path"], source["sha256"], "source_data", errors)

    prespec_fields = {"fit_method", "candidate_models", "protocol_deviations"}
    prespec = value["pre_specification"]
    candidates: list[str] = []
    if exact_object(prespec, prespec_fields, "pre_specification", errors):
        if prespec["fit_method"] != "maximum_likelihood":
            errors.append("pre_specification.fit_method must be maximum_likelihood")
        raw_candidates = prespec["candidate_models"]
        if not isinstance(raw_candidates, list) or not 2 <= len(raw_candidates) <= 8:
            errors.append("candidate_models must contain 2-8 entries")
        else:
            for index, item in enumerate(raw_candidates):
                if not exact_object(item, {"family", "rationale"}, f"candidate_models[{index}]", errors):
                    continue
                family = item["family"]
                if family not in FAMILIES:
                    errors.append(f"candidate_models[{index}].family is unsupported")
                else:
                    candidates.append(family)
                if not text(item["rationale"]):
                    errors.append(f"candidate_models[{index}].rationale must be non-empty")
            if len(candidates) != len(set(candidates)):
                errors.append("candidate model families must be unique")
        deviations = prespec["protocol_deviations"]
        if not isinstance(deviations, list) or any(not text(item) for item in deviations):
            errors.append("protocol_deviations must be a list of non-empty strings")

    execution_fields = {
        "backend", "environment", "r_version",
        "package_versions", "command_path", "command_sha256", "session_info_path",
        "session_info_sha256",
    }
    execution = value["execution"]
    if exact_object(execution, execution_fields, "execution", errors):
        if execution["backend"] != "survHE" or execution["environment"] != "external_local_fit_import":
            errors.append("execution must record an imported local survHE fit")
        if not text(execution["r_version"]):
            errors.append("execution.r_version must be recorded")
        packages = execution["package_versions"]
        if not isinstance(packages, dict) or any(not text(k) or not text(v) for k, v in packages.items()):
            errors.append("execution.package_versions must map package names to versions")
        elif not {"survHE", "flexsurv", "survival"}.issubset(packages):
            errors.append("package_versions must include survHE, flexsurv, and survival")
        hash_file(workspace, execution["command_path"], execution["command_sha256"], "execution command", errors)
        hash_file(workspace, execution["session_info_path"], execution["session_info_sha256"], "session info", errors)

    models = value["models"]
    converged = 0
    result_families: list[str] = []
    common_times: list[float] | None = None
    if not isinstance(models, list):
        errors.append("models must be a list")
        models = []
    model_fields = {
        "family", "status", "aic", "bic", "log_likelihood", "parameterization",
        "fit_output_path", "fit_output_sha256", "landmarks", "warnings",
    }
    landmark_fields = {"time", "survival", "hazard"}
    for index, model in enumerate(models):
        label = f"models[{index}]"
        if not exact_object(model, model_fields, label, errors):
            continue
        family = model["family"]
        if family not in FAMILIES:
            errors.append(f"{label}.family is unsupported")
        else:
            result_families.append(family)
        if model["status"] not in {"converged", "failed"}:
            errors.append(f"{label}.status must be converged or failed")
        if not isinstance(model["warnings"], list) or any(not text(item) for item in model["warnings"]):
            errors.append(f"{label}.warnings must be non-empty strings when present")
        if model["status"] == "failed":
            if any(model[field] is not None for field in ("aic", "bic", "log_likelihood")):
                errors.append(f"{label} failed fit statistics must be null")
            if model["landmarks"] != []:
                errors.append(f"{label} failed landmarks must be empty")
            continue
        converged += 1
        for field in ("aic", "bic", "log_likelihood"):
            if not number(model[field]):
                errors.append(f"{label}.{field} must be finite")
        if not text(model["parameterization"]):
            errors.append(f"{label}.parameterization must be recorded")
        hash_file(workspace, model["fit_output_path"], model["fit_output_sha256"], f"{label} fit output", errors)
        landmarks = model["landmarks"]
        times: list[float] = []
        previous_time = -1.0
        previous_survival = 1.0
        if not isinstance(landmarks, list) or len(landmarks) < 3:
            errors.append(f"{label}.landmarks must contain at least three common times")
            continue
        for landmark_index, landmark in enumerate(landmarks):
            landmark_label = f"{label}.landmarks[{landmark_index}]"
            if not exact_object(landmark, landmark_fields, landmark_label, errors):
                continue
            time = landmark["time"]
            survival = landmark["survival"]
            hazard = landmark["hazard"]
            if not number(time, minimum=0) or float(time) <= previous_time:
                errors.append(f"{landmark_label}.time must be finite and strictly increasing")
                continue
            if not number(survival, minimum=0) or float(survival) > 1 or float(survival) > previous_survival + 1e-12:
                errors.append(f"{landmark_label}.survival must be finite, bounded, and non-increasing")
            if not number(hazard, minimum=0):
                errors.append(f"{landmark_label}.hazard must be finite and non-negative")
            times.append(float(time))
            previous_time = float(time)
            if number(survival):
                previous_survival = float(survival)
        if landmarks and (landmarks[0].get("time") != 0 or landmarks[0].get("survival") != 1):
            errors.append(f"{label}.landmarks must start at time 0 with survival 1")
        if isinstance(context, dict) and number(context.get("observed_follow_up")) and times:
            observed = float(context["observed_follow_up"])
            horizon = float(context.get("model_horizon", 0)) if number(context.get("model_horizon")) else 0
            if not any(0 < time <= observed for time in times):
                errors.append(f"{label}.landmarks require a positive observed-period time")
            if not any(observed < time <= horizon for time in times):
                errors.append(f"{label}.landmarks require an extrapolated-period time within the horizon")
        if common_times is None:
            common_times = times
        elif times != common_times:
            errors.append("all converged models must use identical landmark times")

    if result_families != candidates:
        errors.append("model results must match the pre-specified candidate order")
    if converged < 2:
        errors.append("at least two candidate models must converge")

    diagnostic_fields = {
        "km_overlay_path", "km_overlay_sha256", "log_cumulative_hazard_path",
        "log_cumulative_hazard_sha256", "hazard_plot_path", "hazard_plot_sha256",
        "internal_validity_assessment", "external_validity_assessment",
        "external_sources", "clinical_plausibility_assessment",
    }
    diagnostics = value["diagnostics"]
    if exact_object(diagnostics, diagnostic_fields, "diagnostics", errors):
        hash_file(workspace, diagnostics["km_overlay_path"], diagnostics["km_overlay_sha256"], "KM overlay", errors)
        hash_file(workspace, diagnostics["log_cumulative_hazard_path"], diagnostics["log_cumulative_hazard_sha256"], "log-cumulative-hazard plot", errors)
        hash_file(workspace, diagnostics["hazard_plot_path"], diagnostics["hazard_plot_sha256"], "hazard plot", errors)
        for field in ("internal_validity_assessment", "external_validity_assessment", "clinical_plausibility_assessment"):
            if not text(diagnostics[field]):
                errors.append(f"diagnostics.{field} must be non-empty")
        sources = diagnostics["external_sources"]
        if not isinstance(sources, list) or any(not text(item) for item in sources):
            errors.append("diagnostics.external_sources must be non-empty strings when present")
        if not sources and "unresolved" not in str(diagnostics["external_validity_assessment"]).lower():
            errors.append("external validity needs a source or an explicit unresolved statement")

    scenarios = value["structural_scenarios"]
    if not isinstance(scenarios, list) or len(scenarios) < 2 or any(item not in result_families for item in scenarios):
        errors.append("structural_scenarios must contain at least two fitted candidate families")
    elif len(scenarios) != len(set(scenarios)):
        errors.append("structural_scenarios must be unique")

    recommendation = value["analyst_recommendation"]
    if recommendation is not None:
        if exact_object(recommendation, {"family", "rationale", "alternatives"}, "analyst_recommendation", errors):
            if recommendation["family"] not in result_families:
                errors.append("recommended family must be a fitted candidate")
            else:
                match = next((model for model in models if model.get("family") == recommendation["family"]), None)
                if not match or match.get("status") != "converged":
                    errors.append("recommended family must have converged")
            if not text(recommendation["rationale"]):
                errors.append("recommendation rationale must be non-empty")
            alternatives = recommendation["alternatives"]
            if not isinstance(alternatives, list) or not alternatives or any(item not in result_families or item == recommendation["family"] for item in alternatives):
                errors.append("recommendation must name at least one different fitted alternative")
            if recommendation["family"] not in scenarios:
                errors.append("recommended family must appear in structural_scenarios")

    limitations = value["limitations"]
    if not isinstance(limitations, list) or not limitations or any(not text(item) for item in limitations):
        errors.append("limitations must contain non-empty strings")

    gate = value["human_gate"]
    if not exact_object(gate, {"state", "required_action"}, "human_gate", errors) or gate != {
        "state": "awaiting_human_selection",
        "required_action": "select_curve_in_analysis_plan",
    }:
        errors.append("human_gate must remain awaiting Human selection in the analysis plan")

    forbidden = re.compile(r'"(?:approved|accepted|selected|approval_timestamp|reviewer_signature)"\s*:')
    if forbidden.search(json.dumps(value, sort_keys=True)):
        errors.append("review contains a forbidden approval or selection authority field")
    if value.get("status") != "ready_for_human_review":
        errors.append("status must be ready_for_human_review for a complete audit")
    return {
        "complete": not errors,
        "errors": errors,
        "candidate_models": len(candidates),
        "converged_models": converged,
        "human_gate": "awaiting_human_selection",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("review", type=Path)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    value = json.loads(args.review.read_text(encoding="utf-8"))
    result = audit(value, args.workspace)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
