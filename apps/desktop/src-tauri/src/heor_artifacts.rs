//! App-owned validation for decision-problem and conceptual-model approval targets.
//!
//! Skills may draft these artifacts, but only this module decides whether the
//! exact current workspace bytes are structurally eligible for human review.
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::path::Path;

const ARTIFACT_CAP_BYTES: u64 = 5 * 1024 * 1024;

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ConceptualModelAudit {
    pub complete: bool,
    pub status: &'static str,
    pub errors: Vec<String>,
    pub state_count: usize,
    pub transition_count: usize,
    pub assumption_count: usize,
    pub alternative_count: usize,
    pub unresolved_assumptions: Vec<String>,
}

fn nonempty(value: Option<&serde_json::Value>) -> bool {
    value
        .and_then(serde_json::Value::as_str)
        .is_some_and(|value| !value.trim().is_empty())
}

fn nonempty_string_array(value: Option<&serde_json::Value>) -> bool {
    value
        .and_then(serde_json::Value::as_array)
        .is_some_and(|items| {
            !items.is_empty()
                && items
                    .iter()
                    .all(|item| item.as_str().is_some_and(|value| !value.trim().is_empty()))
        })
}

fn current_artifact(
    workspace: &Path,
    relative_path: &str,
    expected_sha256: &str,
) -> Result<Vec<u8>, String> {
    let path = workspace.join(relative_path);
    let metadata = std::fs::metadata(&path)
        .map_err(|error| format!("{relative_path} unavailable for review: {error}"))?;
    if !metadata.is_file() || metadata.len() > ARTIFACT_CAP_BYTES {
        return Err(format!("{relative_path} is not a reviewable artifact"));
    }
    let raw = std::fs::read(&path)
        .map_err(|error| format!("{relative_path} unavailable for review: {error}"))?;
    if format!("{:x}", Sha256::digest(&raw)) != expected_sha256 {
        return Err(format!("approval must target the current {relative_path}"));
    }
    Ok(raw)
}

pub fn require_decision_problem_approvable(
    workspace: &Path,
    expected_sha256: &str,
) -> Result<(), String> {
    let raw = current_artifact(workspace, "heor/analysis-plan.json", expected_sha256)?;
    let value: serde_json::Value = serde_json::from_slice(&raw)
        .map_err(|error| format!("decision problem artifact is invalid: {error}"))?;
    let problem = value
        .get("decision_problem")
        .and_then(serde_json::Value::as_object)
        .ok_or("analysis plan must include decision_problem metadata")?;
    for field in [
        "title",
        "population",
        "intervention",
        "comparator",
        "perspective",
        "outcome",
    ] {
        if !nonempty(problem.get(field)) {
            return Err(format!("decision_problem.{field} is required"));
        }
    }
    if !problem
        .get("time_horizon_years")
        .and_then(serde_json::Value::as_f64)
        .is_some_and(|value| value.is_finite() && value > 0.0)
    {
        return Err("decision_problem.time_horizon_years must be positive".into());
    }
    Ok(())
}

pub fn audit_conceptual_model_bytes(raw: &[u8]) -> Result<ConceptualModelAudit, String> {
    let value: serde_json::Value = serde_json::from_slice(raw)
        .map_err(|error| format!("conceptual model audit failed: {error}"))?;
    Ok(audit_conceptual_model(&value))
}

fn require_conceptual_analysis_link(workspace: &Path, raw: &[u8]) -> Result<(), String> {
    let model: serde_json::Value = serde_json::from_slice(raw)
        .map_err(|error| format!("conceptual model audit failed: {error}"))?;
    let model_analysis_id = model
        .get("analysis_id")
        .and_then(serde_json::Value::as_str)
        .ok_or("conceptual model omitted analysis_id")?;
    let plan_raw = std::fs::read(workspace.join("heor/analysis-plan.json"))
        .map_err(|error| format!("analysis plan unavailable for conceptual-model link: {error}"))?;
    let plan: serde_json::Value = serde_json::from_slice(&plan_raw)
        .map_err(|error| format!("analysis plan is invalid: {error}"))?;
    let plan_analysis_id = plan
        .get("analysis_id")
        .and_then(serde_json::Value::as_str)
        .ok_or("analysis plan omitted analysis_id")?;
    if model_analysis_id != plan_analysis_id {
        return Err("conceptual model analysis_id does not match the current analysis plan".into());
    }
    Ok(())
}

pub fn audit_conceptual_model(value: &serde_json::Value) -> ConceptualModelAudit {
    let mut errors = Vec::new();
    if value
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some("0.1.0")
    {
        errors.push("schema_version must be 0.1.0".into());
    }
    for field in ["model_id", "analysis_id", "objective"] {
        if !nonempty(value.get(field)) {
            errors.push(format!("{field} is required"));
        }
    }
    if !value
        .get("status")
        .and_then(serde_json::Value::as_str)
        .is_some_and(|status| matches!(status, "draft" | "ready_for_human_review"))
    {
        errors.push("status is invalid".into());
    }

    let scope = value.get("scope").and_then(serde_json::Value::as_object);
    match scope {
        None => errors.push("scope is required".into()),
        Some(scope) => {
            for field in [
                "population",
                "intervention",
                "comparator",
                "perspective",
                "time_horizon",
                "jurisdiction",
                "decision_context",
            ] {
                if !nonempty(scope.get(field)) {
                    errors.push(format!("scope.{field} is required"));
                }
            }
            if !nonempty_string_array(scope.get("outcomes")) {
                errors.push("scope.outcomes must be a non-empty string array".into());
            }
        }
    }
    if !nonempty_string_array(value.get("care_pathway")) {
        errors.push("care_pathway must be a non-empty string array".into());
    }
    let model_type = value
        .get("model_type")
        .and_then(serde_json::Value::as_object);
    if model_type.is_none()
        || !nonempty(model_type.and_then(|item| item.get("proposed")))
        || !nonempty(model_type.and_then(|item| item.get("rationale")))
    {
        errors.push("model_type requires proposed and rationale".into());
    }

    let states = value
        .get("states")
        .and_then(serde_json::Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    if states.len() < 2 {
        errors.push("at least two states are required".into());
    }
    let mut state_ids = HashSet::new();
    let mut absorbing = HashSet::new();
    for (index, state) in states.iter().enumerate() {
        let id = state.get("id").and_then(serde_json::Value::as_str);
        if !id.is_some_and(|id| !id.trim().is_empty() && state_ids.insert(id)) {
            errors.push(format!("states[{index}].id must be non-empty and unique"));
        }
        if !nonempty(state.get("label")) || !nonempty(state.get("definition")) {
            errors.push(format!("states[{index}] requires label and definition"));
        }
        match state.get("absorbing").and_then(serde_json::Value::as_bool) {
            Some(true) => {
                if let Some(id) = id {
                    absorbing.insert(id);
                }
            }
            Some(false) => {}
            None => errors.push(format!("states[{index}].absorbing must be boolean")),
        }
    }

    let transitions = value
        .get("transitions")
        .and_then(serde_json::Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    if transitions.is_empty() {
        errors.push("at least one transition is required".into());
    }
    let mut transition_ids = HashSet::new();
    let mut outgoing = HashSet::new();
    for (index, transition) in transitions.iter().enumerate() {
        let id = transition.get("id").and_then(serde_json::Value::as_str);
        if !id.is_some_and(|id| !id.trim().is_empty() && transition_ids.insert(id)) {
            errors.push(format!(
                "transitions[{index}].id must be non-empty and unique"
            ));
        }
        let from = transition.get("from").and_then(serde_json::Value::as_str);
        let to = transition.get("to").and_then(serde_json::Value::as_str);
        if let (Some(from), Some(to)) = (from, to) {
            if state_ids.contains(from) && state_ids.contains(to) {
                outgoing.insert(from);
                if absorbing.contains(from) && from != to {
                    errors.push(format!(
                        "transitions[{index}] leaves absorbing state {from}"
                    ));
                }
            } else {
                errors.push(format!("transitions[{index}] references an unknown state"));
            }
        } else {
            errors.push(format!("transitions[{index}] references an unknown state"));
        }
        if !nonempty(transition.get("trigger")) {
            errors.push(format!("transitions[{index}].trigger is required"));
        }
    }
    let mut missing_outgoing = state_ids.difference(&outgoing).copied().collect::<Vec<_>>();
    missing_outgoing.sort_unstable();
    if !missing_outgoing.is_empty() {
        errors.push(format!(
            "states without outgoing transitions: {}",
            missing_outgoing.join(", ")
        ));
    }

    let assumptions = value
        .get("structural_assumptions")
        .and_then(serde_json::Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    if assumptions.is_empty() {
        errors.push("at least one structural assumption is required".into());
    }
    let mut assumption_ids = HashSet::new();
    let mut unresolved_assumptions = Vec::new();
    for (index, assumption) in assumptions.iter().enumerate() {
        let id = assumption.get("id").and_then(serde_json::Value::as_str);
        if !id.is_some_and(|id| !id.trim().is_empty() && assumption_ids.insert(id)) {
            errors.push(format!(
                "structural_assumptions[{index}].id must be non-empty and unique"
            ));
        }
        if !nonempty(assumption.get("statement")) || !nonempty(assumption.get("rationale")) {
            errors.push(format!(
                "structural_assumptions[{index}] requires statement and rationale"
            ));
        }
        match assumption.get("status").and_then(serde_json::Value::as_str) {
            Some("unresolved") => {
                if let Some(id) = id {
                    unresolved_assumptions.push(id.to_string());
                }
            }
            Some("proposed" | "rejected") => {}
            _ => errors.push(format!("structural_assumptions[{index}].status is invalid")),
        }
    }

    let alternatives = value
        .get("structural_alternatives")
        .and_then(serde_json::Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    if alternatives.is_empty() {
        errors.push("at least one structural alternative is required".into());
    }
    let mut alternative_ids = HashSet::new();
    for (index, alternative) in alternatives.iter().enumerate() {
        let id = alternative.get("id").and_then(serde_json::Value::as_str);
        if !id.is_some_and(|id| !id.trim().is_empty() && alternative_ids.insert(id)) {
            errors.push(format!(
                "structural_alternatives[{index}].id must be non-empty and unique"
            ));
        }
        for field in ["description", "rationale", "expected_impact"] {
            if !nonempty(alternative.get(field)) {
                errors.push(format!(
                    "structural_alternatives[{index}].{field} is required"
                ));
            }
        }
    }

    match value
        .get("evidence_links")
        .and_then(serde_json::Value::as_array)
    {
        None => errors.push("evidence_links must be an array".into()),
        Some(links) => {
            for (index, link) in links.iter().enumerate() {
                if !nonempty(link.get("claim")) || !nonempty_string_array(link.get("source_ids")) {
                    errors.push(format!(
                        "evidence_links[{index}] requires claim and source_ids"
                    ));
                }
            }
        }
    }
    if !nonempty_string_array(value.get("validation_questions")) {
        errors.push("validation_questions must be a non-empty string array".into());
    }
    let validation_plan = value
        .get("validation_plan")
        .and_then(serde_json::Value::as_object);
    for field in ["face", "internal", "external"] {
        if !nonempty_string_array(validation_plan.and_then(|plan| plan.get(field))) {
            errors.push(format!(
                "validation_plan.{field} must be a non-empty string array"
            ));
        }
    }
    if !unresolved_assumptions.is_empty() {
        errors.push(format!(
            "unresolved structural assumptions: {}",
            unresolved_assumptions.join(", ")
        ));
    }

    let complete = errors.is_empty();
    ConceptualModelAudit {
        complete,
        status: if complete { "complete" } else { "incomplete" },
        errors,
        state_count: states.len(),
        transition_count: transitions.len(),
        assumption_count: assumptions.len(),
        alternative_count: alternatives.len(),
        unresolved_assumptions,
    }
}

pub fn require_conceptual_model_approvable(
    workspace: &Path,
    expected_sha256: &str,
) -> Result<(), String> {
    let raw = current_artifact(workspace, "heor/conceptual-model.json", expected_sha256)?;
    let audit = audit_conceptual_model_bytes(&raw)?;
    if !audit.complete {
        return Err(format!(
            "conceptual model audit is incomplete: {} errors, {} unresolved assumptions",
            audit.errors.len(),
            audit.unresolved_assumptions.len()
        ));
    }
    require_conceptual_analysis_link(workspace, &raw)?;
    Ok(())
}

pub fn current_conceptual_model_hash_and_audit(
    workspace: &Path,
) -> Result<(String, ConceptualModelAudit), String> {
    let path = workspace.join("heor/conceptual-model.json");
    let raw = std::fs::read(&path)
        .map_err(|error| format!("heor/conceptual-model.json unavailable: {error}"))?;
    if raw.len() as u64 > ARTIFACT_CAP_BYTES {
        return Err("heor/conceptual-model.json exceeds the review limit".into());
    }
    let hash = format!("{:x}", Sha256::digest(&raw));
    let mut audit = audit_conceptual_model_bytes(&raw)?;
    if let Err(error) = require_conceptual_analysis_link(workspace, &raw) {
        audit.complete = false;
        audit.status = "incomplete";
        audit.errors.push(error);
    }
    Ok((hash, audit))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn complete_model() -> serde_json::Value {
        serde_json::json!({
            "schema_version": "0.1.0",
            "model_id": "model-1",
            "analysis_id": "analysis-1",
            "status": "ready_for_human_review",
            "objective": "Estimate incremental cost and QALY",
            "scope": {
                "population": "Adults", "intervention": "A", "comparator": "B",
                "perspective": "Healthcare system", "time_horizon": "Lifetime",
                "outcomes": ["cost", "QALY"], "jurisdiction": "China",
                "decision_context": "Reimbursement"
            },
            "care_pathway": ["Treat", "Progress", "Death"],
            "model_type": {"proposed": "cohort_state_transition", "rationale": "Adequate states"},
            "states": [
                {"id": "stable", "label": "Stable", "definition": "Stable", "absorbing": false},
                {"id": "dead", "label": "Dead", "definition": "Death", "absorbing": true}
            ],
            "transitions": [
                {"id": "stable-stable", "from": "stable", "to": "stable", "trigger": "Remain"},
                {"id": "stable-dead", "from": "stable", "to": "dead", "trigger": "Death"},
                {"id": "dead-dead", "from": "dead", "to": "dead", "trigger": "Absorbing"}
            ],
            "structural_assumptions": [{
                "id": "memoryless", "statement": "Memoryless", "rationale": "Model form", "status": "proposed"
            }],
            "structural_alternatives": [{
                "id": "alt", "description": "Alternative", "rationale": "Plausible", "expected_impact": "Occupancy"
            }],
            "evidence_links": [{"claim": "Pathway", "source_ids": ["source-1"]}],
            "validation_plan": {
                "face": ["Expert pathway review"],
                "internal": ["Formula and boundary checks"],
                "external": ["Independent outcome comparison"]
            },
            "validation_questions": ["Are states exhaustive?"]
        })
    }

    #[test]
    fn complete_conceptual_model_is_reviewable() {
        let audit = audit_conceptual_model(&complete_model());
        assert!(audit.complete);
        assert_eq!(audit.state_count, 2);
    }

    #[test]
    fn unresolved_assumption_and_absorbing_exit_fail_closed() {
        let mut value = complete_model();
        value["structural_assumptions"][0]["status"] = serde_json::json!("unresolved");
        value["transitions"]
            .as_array_mut()
            .unwrap()
            .push(serde_json::json!({
                "id": "dead-stable", "from": "dead", "to": "stable", "trigger": "Invalid"
            }));
        let audit = audit_conceptual_model(&value);
        assert!(!audit.complete);
        assert_eq!(audit.unresolved_assumptions, vec!["memoryless"]);
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("absorbing state")));
    }

    #[test]
    fn incomplete_validation_plan_fails_closed() {
        let mut value = complete_model();
        value["validation_plan"]["external"] = serde_json::json!([]);
        let audit = audit_conceptual_model(&value);
        assert!(!audit.complete);
        assert!(audit
            .errors
            .iter()
            .any(|error| error == "validation_plan.external must be a non-empty string array"));
    }

    #[test]
    fn approval_requires_the_exact_current_conceptual_artifact() {
        let root =
            std::env::temp_dir().join(format!("heor-conceptual-artifact-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("heor")).unwrap();
        let raw = serde_json::to_vec_pretty(&complete_model()).unwrap();
        std::fs::write(root.join("heor/conceptual-model.json"), &raw).unwrap();
        std::fs::write(
            root.join("heor/analysis-plan.json"),
            serde_json::to_vec(&serde_json::json!({"analysis_id": "analysis-1"})).unwrap(),
        )
        .unwrap();
        let hash = format!("{:x}", Sha256::digest(&raw));

        require_conceptual_model_approvable(&root, &hash).unwrap();
        assert!(require_conceptual_model_approvable(&root, &"f".repeat(64))
            .unwrap_err()
            .contains("current heor/conceptual-model.json"));
        std::fs::write(
            root.join("heor/analysis-plan.json"),
            serde_json::to_vec(&serde_json::json!({"analysis_id": "another-analysis"})).unwrap(),
        )
        .unwrap();
        assert!(require_conceptual_model_approvable(&root, &hash)
            .unwrap_err()
            .contains("does not match"));
        let (_, audit) = current_conceptual_model_hash_and_audit(&root).unwrap();
        assert!(!audit.complete);
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("does not match")));

        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn decision_problem_requires_current_plan_and_complete_scope() {
        let root =
            std::env::temp_dir().join(format!("heor-decision-artifact-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("heor")).unwrap();
        let plan = serde_json::json!({
            "decision_problem": {
                "title": "Decision", "population": "Adults", "intervention": "A",
                "comparator": "B", "perspective": "Payer", "outcome": "QALY",
                "time_horizon_years": 10
            }
        });
        let raw = serde_json::to_vec_pretty(&plan).unwrap();
        std::fs::write(root.join("heor/analysis-plan.json"), &raw).unwrap();
        let hash = format!("{:x}", Sha256::digest(&raw));
        require_decision_problem_approvable(&root, &hash).unwrap();

        let mut invalid = plan;
        invalid["decision_problem"]["population"] = serde_json::json!("");
        let invalid_raw = serde_json::to_vec_pretty(&invalid).unwrap();
        std::fs::write(root.join("heor/analysis-plan.json"), &invalid_raw).unwrap();
        let invalid_hash = format!("{:x}", Sha256::digest(&invalid_raw));
        assert!(require_decision_problem_approvable(&root, &invalid_hash)
            .unwrap_err()
            .contains("population"));

        let _ = std::fs::remove_dir_all(root);
    }
}
