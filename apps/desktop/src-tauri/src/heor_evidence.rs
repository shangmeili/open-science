use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};

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
        if source_ids.is_empty() && assumption_ids.is_empty() {
            reasons.push("no evidence source or reviewable assumption is linked");
        }
        if source_ids.iter().any(|id| !valid_sources.contains(id)) {
            reasons.push("source link is missing or source metadata is incomplete");
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
    }
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
        first["assumption_ids"] = serde_json::json!(["assumption-1"]);
        assert!(audit_plan(&plan).complete);
    }
}
