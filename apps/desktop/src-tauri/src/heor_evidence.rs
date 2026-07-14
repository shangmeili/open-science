use sha2::{Digest, Sha256};
use std::collections::{BTreeSet, HashMap, HashSet};
use std::path::Path;
use tauri::AppHandle;

const BASE_INPUT_PATHS: [&str; 12] = [
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
];

const FINAL_INPUT_PATH: &str = "strategies.intervention.state_utilities";

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EvidenceAudit {
    pub complete: bool,
    pub status: &'static str,
    pub required_inputs: usize,
    pub covered_inputs: usize,
    pub unsupported_inputs: Vec<String>,
    pub invalid_mappings: Vec<String>,
    pub unresolved_assumptions: Vec<String>,
    pub source_count: usize,
    pub mapping_count: usize,
    pub source_based_inputs: usize,
    pub selected_extraction_count: usize,
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EvidenceSelectionAudit {
    pub complete: bool,
    pub status: &'static str,
    pub synthesis_sha256: String,
    pub selected_input_count: usize,
    pub selected_extraction_count: usize,
    pub verified_extraction_count: usize,
    pub unverified_extraction_ids: Vec<String>,
    pub rejected_extraction_ids: Vec<String>,
    pub invalid_selections: Vec<String>,
    pub errors: Vec<String>,
    pub verification_integrity: &'static str,
}

fn nonempty(value: Option<&serde_json::Value>) -> bool {
    value
        .and_then(serde_json::Value::as_str)
        .is_some_and(|value| !value.trim().is_empty())
}

fn string_list(value: Option<&serde_json::Value>) -> Option<Vec<&str>> {
    value?.as_array().map(|items| {
        items
            .iter()
            .filter_map(serde_json::Value::as_str)
            .filter(|value| !value.trim().is_empty())
            .collect()
    })
}

fn is_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn required_input_paths(plan: &serde_json::Value) -> Vec<&'static str> {
    let mut paths = Vec::from(BASE_INPUT_PATHS);
    paths.push(FINAL_INPUT_PATH);
    if !plan
        .get("willingness_to_pay")
        .is_none_or(serde_json::Value::is_null)
    {
        paths.push("willingness_to_pay");
    }
    paths
}

fn monetary_path(path: &str) -> bool {
    path.ends_with("state_costs") || path == "willingness_to_pay"
}

pub fn audit_plan_bytes(raw: &[u8]) -> Result<EvidenceAudit, String> {
    let plan: serde_json::Value = serde_json::from_slice(raw)
        .map_err(|error| format!("analysis plan evidence audit failed: {error}"))?;
    Ok(audit_plan(&plan))
}

pub fn audit_plan(plan: &serde_json::Value) -> EvidenceAudit {
    let required = required_input_paths(plan);
    let required_set: HashSet<&str> = required.iter().copied().collect();
    let sources = plan
        .get("evidence_sources")
        .and_then(serde_json::Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    let assumptions = plan
        .get("assumptions")
        .and_then(serde_json::Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    let mappings = plan
        .get("input_provenance")
        .and_then(serde_json::Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[]);

    let source_id_counts = sources.iter().fold(HashMap::new(), |mut counts, source| {
        if let Some(id) = source.get("id").and_then(serde_json::Value::as_str) {
            *counts.entry(id).or_insert(0usize) += 1;
        }
        counts
    });
    let mut valid_sources = HashSet::new();
    for source in sources {
        let Some(id) = source.get("id").and_then(serde_json::Value::as_str) else {
            continue;
        };
        let local_path = source.get("local_path").and_then(serde_json::Value::as_str);
        let locator_valid =
            nonempty(source.get("url")) || local_path.is_some_and(|v| !v.trim().is_empty());
        let local_snapshot_valid = local_path.is_none_or(|_| {
            source
                .get("content_sha256")
                .and_then(serde_json::Value::as_str)
                .is_some_and(is_sha256)
        });
        if !id.trim().is_empty()
            && source_id_counts.get(id) == Some(&1)
            && nonempty(source.get("title"))
            && nonempty(source.get("source_type"))
            && nonempty(source.get("accessed_on"))
            && locator_valid
            && local_snapshot_valid
        {
            valid_sources.insert(id);
        }
    }

    let mut assumption_statuses = HashMap::new();
    let mut unresolved_assumptions = Vec::new();
    for assumption in assumptions {
        let Some(id) = assumption.get("id").and_then(serde_json::Value::as_str) else {
            continue;
        };
        let status = assumption
            .get("status")
            .and_then(serde_json::Value::as_str)
            .unwrap_or("unresolved");
        if !id.trim().is_empty()
            && nonempty(assumption.get("statement"))
            && nonempty(assumption.get("reason"))
        {
            assumption_statuses.insert(id, status);
        }
        if status == "unresolved" {
            unresolved_assumptions.push(id.to_string());
        }
    }

    let mut seen = HashSet::new();
    let mut covered = HashSet::new();
    let mut invalid_mappings = Vec::new();
    let mut source_based_inputs = 0usize;
    let mut selected_extractions = HashSet::new();
    let synthesis_binding = plan
        .get("evidence_synthesis")
        .and_then(serde_json::Value::as_object);
    let synthesis_binding_valid = synthesis_binding.is_some_and(|binding| {
        binding.get("path").and_then(serde_json::Value::as_str)
            == Some(crate::heor_synthesis::EVIDENCE_SYNTHESIS_PATH)
            && binding
                .get("content_sha256")
                .and_then(serde_json::Value::as_str)
                .is_some_and(is_sha256)
    });
    for mapping in mappings {
        let Some(path) = mapping.get("path").and_then(serde_json::Value::as_str) else {
            invalid_mappings.push("mapping omitted path".into());
            continue;
        };
        let mut reasons = Vec::new();
        if !required_set.contains(path) {
            reasons.push("path is not a required model input");
        }
        if !seen.insert(path) {
            reasons.push("path is duplicated");
        }
        if !nonempty(mapping.get("unit")) {
            reasons.push("unit is missing");
        }
        if !nonempty(mapping.get("jurisdiction")) {
            reasons.push("jurisdiction is missing");
        }
        if !nonempty(mapping.get("selection_rationale")) {
            reasons.push("selection rationale is missing");
        }
        let uncertainty_valid = mapping
            .get("uncertainty_status")
            .and_then(serde_json::Value::as_str)
            .is_some_and(|value| {
                matches!(
                    value,
                    "fixed" | "range_available" | "distribution_available"
                )
            });
        if !uncertainty_valid {
            reasons.push("uncertainty status is invalid");
        }
        if monetary_path(path)
            && !mapping
                .get("price_year")
                .and_then(serde_json::Value::as_u64)
                .is_some_and(|year| (1900..=3000).contains(&year))
        {
            reasons.push("price year is missing");
        }

        let source_ids = string_list(mapping.get("source_ids")).unwrap_or_default();
        let assumption_ids = string_list(mapping.get("assumption_ids")).unwrap_or_default();
        let extraction_ids = string_list(mapping.get("extraction_ids")).unwrap_or_default();
        if source_ids.is_empty() && assumption_ids.is_empty() {
            reasons.push("no evidence source or reviewable assumption is linked");
        }
        if source_ids.iter().any(|id| !valid_sources.contains(id)) {
            reasons.push("source link is missing or source metadata is incomplete");
        }
        if !source_ids.is_empty() {
            source_based_inputs += 1;
            if !synthesis_binding_valid {
                reasons.push("current evidence synthesis binding is missing or invalid");
            }
            if extraction_ids.is_empty() {
                reasons.push("source-based input has no selected extraction");
            }
            let unique = extraction_ids.iter().copied().collect::<HashSet<_>>();
            if unique.len() != extraction_ids.len() {
                reasons.push("selected extraction IDs are duplicated");
            }
            selected_extractions.extend(extraction_ids.iter().map(|id| (*id).to_string()));
        } else if !extraction_ids.is_empty() {
            reasons.push("extraction IDs require at least one evidence source");
        }
        if assumption_ids
            .iter()
            .any(|id| assumption_statuses.get(id).copied() != Some("proposed"))
        {
            reasons.push("assumption link is missing or is not proposed for human review");
        }

        if reasons.is_empty() {
            covered.insert(path);
        } else {
            invalid_mappings.push(format!("{path}: {}", reasons.join("; ")));
        }
    }

    let unsupported_inputs = required
        .iter()
        .filter(|path| !covered.contains(**path))
        .map(|path| (*path).to_string())
        .collect::<Vec<_>>();
    let complete = unsupported_inputs.is_empty()
        && invalid_mappings.is_empty()
        && unresolved_assumptions.is_empty();
    EvidenceAudit {
        complete,
        status: if complete { "complete" } else { "incomplete" },
        required_inputs: required.len(),
        covered_inputs: covered.len(),
        unsupported_inputs,
        invalid_mappings,
        unresolved_assumptions,
        source_count: valid_sources.len(),
        mapping_count: mappings.len(),
        source_based_inputs,
        selected_extraction_count: selected_extractions.len(),
    }
}

fn incomplete_selection(error: String) -> EvidenceSelectionAudit {
    EvidenceSelectionAudit {
        complete: false,
        status: "incomplete",
        synthesis_sha256: String::new(),
        selected_input_count: 0,
        selected_extraction_count: 0,
        verified_extraction_count: 0,
        unverified_extraction_ids: Vec::new(),
        rejected_extraction_ids: Vec::new(),
        invalid_selections: Vec::new(),
        errors: vec![error],
        verification_integrity: "not_checked",
    }
}

pub(crate) fn audit_evidence_selection_for_plan(
    app: &AppHandle,
    workspace: &Path,
    project_id: &str,
    plan_raw: &[u8],
) -> EvidenceSelectionAudit {
    let plan: serde_json::Value = match serde_json::from_slice(plan_raw) {
        Ok(value) => value,
        Err(error) => {
            return incomplete_selection(format!("analysis plan is invalid JSON: {error}"))
        }
    };
    let source_based_input_count = plan
        .get("input_provenance")
        .and_then(serde_json::Value::as_array)
        .into_iter()
        .flatten()
        .filter(|mapping| string_list(mapping.get("source_ids")).is_some_and(|ids| !ids.is_empty()))
        .count();
    if source_based_input_count == 0 {
        return EvidenceSelectionAudit {
            complete: true,
            status: "complete",
            synthesis_sha256: String::new(),
            selected_input_count: 0,
            selected_extraction_count: 0,
            verified_extraction_count: 0,
            unverified_extraction_ids: Vec::new(),
            rejected_extraction_ids: Vec::new(),
            invalid_selections: Vec::new(),
            errors: Vec::new(),
            verification_integrity: "not_applicable_no_source_based_inputs",
        };
    }
    let binding = plan
        .get("evidence_synthesis")
        .and_then(serde_json::Value::as_object);
    let claimed_path = binding
        .and_then(|value| value.get("path"))
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default();
    let claimed_sha256 = binding
        .and_then(|value| value.get("content_sha256"))
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default();
    let synthesis_raw = match crate::heor_uncertainty::read_workspace_capped(
        workspace,
        crate::heor_synthesis::EVIDENCE_SYNTHESIS_PATH,
    ) {
        Ok(raw) => raw,
        Err(error) => return incomplete_selection(error),
    };
    let synthesis_sha256 = format!("{:x}", Sha256::digest(&synthesis_raw));
    let mut errors = Vec::new();
    if claimed_path != crate::heor_synthesis::EVIDENCE_SYNTHESIS_PATH {
        errors.push("analysis plan must bind heor/evidence-synthesis.json".into());
    }
    if claimed_sha256 != synthesis_sha256 {
        errors.push("analysis plan evidence-synthesis hash is stale or missing".into());
    }
    let extraction_index = match crate::heor_synthesis::extraction_index(&synthesis_raw) {
        Ok(index) => index,
        Err(error) => {
            errors.push(error);
            HashMap::new()
        }
    };
    let verification_log = match crate::heor_evidence_review::verified_log(app, project_id) {
        Ok(log) => log,
        Err(error) => return incomplete_selection(error),
    };
    let eligible = extraction_index.keys().cloned().collect::<BTreeSet<_>>();
    let review =
        crate::heor_evidence_review::review_status(&verification_log, &synthesis_sha256, &eligible);
    let verified = review.verified_extraction_ids;
    let rejected = review.rejected_extraction_ids;
    let mut selected_inputs = 0usize;
    let mut selected_ids = BTreeSet::new();
    let mut unverified = BTreeSet::new();
    let mut invalid_selections = Vec::new();
    for mapping in plan
        .get("input_provenance")
        .and_then(serde_json::Value::as_array)
        .into_iter()
        .flatten()
    {
        let path = mapping
            .get("path")
            .and_then(serde_json::Value::as_str)
            .unwrap_or("mapping");
        let source_ids = string_list(mapping.get("source_ids")).unwrap_or_default();
        if source_ids.is_empty() {
            continue;
        }
        selected_inputs += 1;
        let extraction_ids = string_list(mapping.get("extraction_ids")).unwrap_or_default();
        if extraction_ids.is_empty() {
            invalid_selections.push(format!("{path}: no selected extraction"));
            continue;
        }
        let unique = extraction_ids.iter().copied().collect::<HashSet<_>>();
        if unique.len() != extraction_ids.len() {
            invalid_selections.push(format!("{path}: selected extraction IDs are duplicated"));
        }
        for extraction_id in unique {
            selected_ids.insert(extraction_id.to_string());
            match extraction_index.get(extraction_id) {
                Some(extraction)
                    if extraction.target == path
                        && source_ids.contains(&extraction.record_id.as_str()) => {}
                Some(extraction) if extraction.target != path => invalid_selections.push(format!(
                    "{path}: {extraction_id} targets {}",
                    extraction.target
                )),
                Some(extraction) => invalid_selections.push(format!(
                    "{path}: {extraction_id} record {} is not a linked source",
                    extraction.record_id
                )),
                None => invalid_selections.push(format!(
                    "{path}: {extraction_id} is absent, conflicting, or ineligible"
                )),
            }
            if !verified.contains(extraction_id) {
                unverified.insert(extraction_id.to_string());
            }
        }
    }
    let complete = errors.is_empty()
        && invalid_selections.is_empty()
        && unverified.is_empty()
        && selected_inputs > 0;
    EvidenceSelectionAudit {
        complete,
        status: if complete { "complete" } else { "incomplete" },
        synthesis_sha256,
        selected_input_count: selected_inputs,
        selected_extraction_count: selected_ids.len(),
        verified_extraction_count: selected_ids.intersection(&verified).count(),
        unverified_extraction_ids: unverified.into_iter().collect(),
        rejected_extraction_ids: selected_ids.intersection(&rejected).cloned().collect(),
        invalid_selections,
        errors,
        verification_integrity: verification_log.integrity,
    }
}

pub(crate) fn require_evidence_selection_approvable(
    app: &AppHandle,
    workspace: &Path,
    project_id: &str,
    plan_raw: &[u8],
) -> Result<EvidenceSelectionAudit, String> {
    let audit = audit_evidence_selection_for_plan(app, workspace, project_id, plan_raw);
    if !audit.complete {
        return Err(format!(
            "evidence-to-input selection is incomplete: {} unverified extractions, {} invalid selections, {} errors",
            audit.unverified_extraction_ids.len(),
            audit.invalid_selections.len(),
            audit.errors.len()
        ));
    }
    Ok(audit)
}

#[tauri::command]
pub fn audit_heor_evidence_selection(app: AppHandle) -> Result<EvidenceSelectionAudit, String> {
    let workspace = crate::runtime::workspace_dir(&app)?;
    let project_id = crate::project::require_project_id(&workspace)?;
    let raw =
        crate::heor_uncertainty::read_workspace_capped(&workspace, "heor/analysis-plan.json")?;
    Ok(audit_evidence_selection_for_plan(
        &app,
        &workspace,
        &project_id,
        &raw,
    ))
}

pub fn require_analysis_plan_approvable(raw: &[u8], expected_sha256: &str) -> Result<(), String> {
    let actual_sha256 = format!("{:x}", Sha256::digest(raw));
    if actual_sha256 != expected_sha256 {
        return Err(
            "analysis-plan approval must target the current heor/analysis-plan.json".into(),
        );
    }
    let audit = audit_plan_bytes(raw)?;
    if !audit.complete {
        return Err(format!(
            "analysis plan evidence audit is incomplete: {}/{} inputs covered, {} unresolved assumptions, {} invalid mappings",
            audit.covered_inputs,
            audit.required_inputs,
            audit.unresolved_assumptions.len(),
            audit.invalid_mappings.len()
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn complete_plan() -> serde_json::Value {
        let paths = required_input_paths(&serde_json::json!({ "willingness_to_pay": 100000 }));
        serde_json::json!({
            "willingness_to_pay": 100000,
            "evidence_synthesis": {
                "path": "heor/evidence-synthesis.json",
                "content_sha256": "a".repeat(64)
            },
            "evidence_sources": [{
                "id": "source-1",
                "title": "Model inputs",
                "source_type": "peer_reviewed_study",
                "url": "https://example.test/study",
                "accessed_on": "2026-07-14"
            }],
            "assumptions": [],
            "input_provenance": paths.into_iter().map(|path| serde_json::json!({
                "path": path,
                "source_ids": ["source-1"],
                "extraction_ids": [format!("extract-{}", path.replace('.', "-"))],
                "assumption_ids": [],
                "unit": "model-specific",
                "jurisdiction": "China",
                "price_year": if monetary_path(path) { Some(2026) } else { None },
                "selection_rationale": "Pre-specified source",
                "uncertainty_status": "fixed"
            })).collect::<Vec<_>>()
        })
    }

    #[test]
    fn every_required_input_can_be_covered() {
        let audit = audit_plan(&complete_plan());
        assert!(audit.complete);
        assert_eq!(audit.required_inputs, 14);
        assert_eq!(audit.covered_inputs, 14);
    }

    #[test]
    fn missing_mapping_and_unresolved_assumption_fail_closed() {
        let mut plan = complete_plan();
        plan["input_provenance"].as_array_mut().unwrap().pop();
        plan["assumptions"] = serde_json::json!([{
            "id": "open-1",
            "statement": "Unknown transition estimate",
            "reason": "Evidence has not been selected",
            "status": "unresolved"
        }]);
        let audit = audit_plan(&plan);
        assert!(!audit.complete);
        assert_eq!(audit.covered_inputs, 13);
        assert_eq!(audit.unresolved_assumptions, vec!["open-1"]);
    }

    #[test]
    fn proposed_assumption_is_explicitly_reviewable() {
        let mut plan = complete_plan();
        plan["assumptions"] = serde_json::json!([{
            "id": "assumption-1",
            "statement": "Synthetic terminal-state utility",
            "reason": "No directly applicable evidence",
            "status": "proposed"
        }]);
        let first = plan["input_provenance"]
            .as_array_mut()
            .unwrap()
            .first_mut()
            .unwrap();
        first["source_ids"] = serde_json::json!([]);
        first["extraction_ids"] = serde_json::json!([]);
        first["assumption_ids"] = serde_json::json!(["assumption-1"]);
        assert!(audit_plan(&plan).complete);
    }
}
