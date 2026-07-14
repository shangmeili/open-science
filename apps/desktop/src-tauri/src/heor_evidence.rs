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

fn currency_code(value: Option<&serde_json::Value>) -> Option<&str> {
    value.and_then(serde_json::Value::as_str).filter(|value| {
        value.len() == 3
            && value
                .bytes()
                .all(|byte| byte.is_ascii_alphabetic() && byte.is_ascii_uppercase())
    })
}

fn model_value<'a>(plan: &'a serde_json::Value, path: &str) -> Option<&'a serde_json::Value> {
    path.split('.')
        .try_fold(plan, |current, token| current.get(token))
}

fn json_equivalent(left: &serde_json::Value, right: &serde_json::Value) -> bool {
    match (left, right) {
        (serde_json::Value::Number(a), serde_json::Value::Number(b)) => {
            match (a.as_f64(), b.as_f64()) {
                (Some(a), Some(b)) if a.is_finite() && b.is_finite() => {
                    let tolerance = (a.abs().max(b.abs()) * 1e-12).max(1e-12);
                    (a - b).abs() <= tolerance
                }
                _ => false,
            }
        }
        (serde_json::Value::Array(a), serde_json::Value::Array(b)) => {
            a.len() == b.len()
                && a.iter()
                    .zip(b.iter())
                    .all(|(left, right)| json_equivalent(left, right))
        }
        (serde_json::Value::Object(a), serde_json::Value::Object(b)) => {
            a.len() == b.len()
                && a.iter().all(|(key, value)| {
                    b.get(key)
                        .is_some_and(|other| json_equivalent(value, other))
                })
        }
        _ => left == right,
    }
}

fn derivation_declaration_reasons(
    plan: &serde_json::Value,
    path: &str,
    mapping: &serde_json::Value,
    source_ids: &[&str],
    assumption_ids: &[&str],
    extraction_ids: &[&str],
) -> Vec<String> {
    let mut reasons = Vec::new();
    let Some(derivation) = mapping
        .get("derivation")
        .and_then(serde_json::Value::as_object)
    else {
        return vec!["derivation must be an object".into()];
    };
    let target_matches = model_value(plan, path)
        .filter(|target| !target.is_null())
        .is_some_and(|target| {
            derivation
                .get("model_value")
                .is_some_and(|value| json_equivalent(value, target))
        });
    if !target_matches {
        reasons.push("derivation.model_value does not match the current model input".into());
    }
    let method = derivation
        .get("method")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default();
    if source_ids.is_empty() {
        if method != "explicit_assumption" {
            reasons.push(
                "assumption-only input must use derivation method explicit_assumption".into(),
            );
        }
        if !extraction_ids.is_empty() {
            reasons.push("explicit_assumption derivation must not claim extraction IDs".into());
        }
        if assumption_ids.is_empty() {
            reasons.push("explicit_assumption derivation requires a proposed assumption".into());
        }
    } else {
        let expected = if monetary_path(path) {
            "monetary_adjustment"
        } else {
            "direct_evidence"
        };
        if method != expected {
            reasons.push(format!(
                "source-based input must use derivation method {expected}"
            ));
        } else if method == "direct_evidence" && extraction_ids.len() != 1 {
            reasons.push("direct_evidence requires exactly one extraction".into());
        }
    }
    reasons
}

fn monetary_adjustment_reasons(
    plan: &serde_json::Value,
    path: &str,
    mapping: &serde_json::Value,
    economic_basis: Option<(&str, u64)>,
    valid_sources: &HashSet<&str>,
    assumption_statuses: &HashMap<&str, &str>,
) -> Vec<String> {
    let Some((currency, price_year)) = economic_basis else {
        return vec!["current economic_basis is missing or invalid".into()];
    };
    let mut reasons = Vec::new();
    if currency_code(mapping.get("currency")) != Some(currency) {
        reasons.push("currency does not match economic_basis.currency".into());
    }
    if mapping
        .get("price_year")
        .and_then(serde_json::Value::as_u64)
        != Some(price_year)
    {
        reasons.push("price_year does not match economic_basis.price_year".into());
    }
    let Some(target) = model_value(plan, path) else {
        reasons.push("model monetary value is missing".into());
        return reasons;
    };
    let target_values = match target.as_array() {
        Some(values) if !values.is_empty() => values
            .iter()
            .filter_map(serde_json::Value::as_f64)
            .collect::<Vec<_>>(),
        Some(_) => Vec::new(),
        None => target.as_f64().into_iter().collect::<Vec<_>>(),
    };
    if target_values.is_empty()
        || target_values.len() != target.as_array().map_or(1, Vec::len)
        || target_values
            .iter()
            .any(|value| !value.is_finite() || *value < 0.0)
    {
        reasons.push("model monetary value is missing, non-finite, or negative".into());
        return reasons;
    }
    let Some(adjustments) = mapping
        .get("monetary_adjustments")
        .and_then(serde_json::Value::as_array)
    else {
        reasons.push("monetary_adjustments must cover every model value exactly once".into());
        return reasons;
    };
    if adjustments.len() != target_values.len() {
        reasons.push("monetary_adjustments must cover every model value exactly once".into());
        return reasons;
    }
    let target_is_array = target.is_array();
    let mut seen = HashSet::new();
    for (position, adjustment) in adjustments.iter().enumerate() {
        let label = format!("monetary_adjustments[{position}]");
        let Some(adjustment) = adjustment.as_object() else {
            reasons.push(format!("{label} must be an object"));
            continue;
        };
        let target_index = if target_is_array {
            let Some(index) = adjustment
                .get("target_index")
                .and_then(serde_json::Value::as_u64)
                .and_then(|value| usize::try_from(value).ok())
                .filter(|value| *value < target_values.len())
            else {
                reasons.push(format!("{label}.target_index is invalid"));
                continue;
            };
            index
        } else {
            if adjustment.contains_key("target_index") {
                reasons.push(format!("{label}.target_index must be omitted for a scalar"));
            }
            0
        };
        if !seen.insert(target_index) {
            reasons.push(format!("{label}.target_index is duplicated"));
            continue;
        }
        let Some(source_value) = adjustment
            .get("source_value")
            .and_then(serde_json::Value::as_f64)
            .filter(|value| value.is_finite() && *value >= 0.0)
        else {
            reasons.push(format!(
                "{label}.source_value must be finite and non-negative"
            ));
            continue;
        };
        let Some(factor) = adjustment
            .get("factor")
            .and_then(serde_json::Value::as_f64)
            .filter(|value| value.is_finite() && *value > 0.0)
        else {
            reasons.push(format!("{label}.factor must be finite and positive"));
            continue;
        };
        let source_currency = currency_code(adjustment.get("source_currency"));
        if source_currency.is_none() {
            reasons.push(format!(
                "{label}.source_currency must be an ISO 4217-format code"
            ));
        }
        let source_year = adjustment
            .get("source_price_year")
            .and_then(serde_json::Value::as_u64)
            .filter(|year| (1900..=2100).contains(year));
        if source_year.is_none() {
            reasons.push(format!(
                "{label}.source_price_year must be from 1900 to 2100"
            ));
        }
        let target_value = target_values[target_index];
        let difference = (source_value * factor - target_value).abs();
        let tolerance = (target_value.abs() * 1e-9).max(1e-6);
        if difference > tolerance {
            reasons.push(format!("{label} does not reproduce model value"));
        }
        let basis_ids = adjustment
            .get("basis_ids")
            .and_then(serde_json::Value::as_array)
            .filter(|values| {
                values.iter().all(|value| {
                    value
                        .as_str()
                        .is_some_and(|identifier| !identifier.trim().is_empty())
                })
            });
        if basis_ids.is_none() {
            reasons.push(format!("{label}.basis_ids must be an array"));
        }
        let basis_ids = basis_ids
            .into_iter()
            .flatten()
            .filter_map(serde_json::Value::as_str);
        let basis_ids = basis_ids.collect::<Vec<_>>();
        let same_basis = source_currency == Some(currency) && source_year == Some(price_year);
        let method = adjustment
            .get("method")
            .and_then(serde_json::Value::as_str)
            .unwrap_or("");
        if same_basis && (factor - 1.0).abs() <= 1e-12 {
            if method != "none" || !basis_ids.is_empty() {
                reasons.push(format!(
                    "{label} must use method none and no basis_ids when no adjustment is needed"
                ));
            }
        } else {
            if method.trim().is_empty() || method.eq_ignore_ascii_case("none") {
                reasons.push(format!(
                    "{label}.method must explain the applied adjustment"
                ));
            }
            if basis_ids.is_empty()
                || basis_ids.iter().any(|identifier| {
                    !valid_sources.contains(identifier)
                        && assumption_statuses.get(identifier).copied() != Some("proposed")
                })
            {
                reasons.push(format!(
                    "{label}.basis_ids must link valid evidence or proposed assumptions"
                ));
            }
        }
    }
    if seen.len() != target_values.len() {
        reasons.push("monetary_adjustments do not cover every target index".into());
    }
    reasons
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
    if plan
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some("0.3.0")
    {
        invalid_mappings.push("schema_version must be 0.3.0 for approval review".into());
    }
    let economic_basis = plan
        .get("economic_basis")
        .and_then(serde_json::Value::as_object)
        .and_then(|basis| {
            let currency = currency_code(basis.get("currency"))?;
            let price_year = basis
                .get("price_year")
                .and_then(serde_json::Value::as_u64)
                .filter(|year| (1900..=2100).contains(year))?;
            Some((currency, price_year))
        });
    if economic_basis.is_none() {
        invalid_mappings.push("economic_basis must declare a valid currency and price_year".into());
    }
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
        let mut reasons: Vec<String> = Vec::new();
        if !required_set.contains(path) {
            reasons.push("path is not a required model input".into());
        }
        if !seen.insert(path) {
            reasons.push("path is duplicated".into());
        }
        if !nonempty(mapping.get("unit")) {
            reasons.push("unit is missing".into());
        }
        if !nonempty(mapping.get("jurisdiction")) {
            reasons.push("jurisdiction is missing".into());
        }
        if !nonempty(mapping.get("selection_rationale")) {
            reasons.push("selection rationale is missing".into());
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
            reasons.push("uncertainty status is invalid".into());
        }
        let source_ids = string_list(mapping.get("source_ids")).unwrap_or_default();
        let assumption_ids = string_list(mapping.get("assumption_ids")).unwrap_or_default();
        let extraction_ids = string_list(mapping.get("extraction_ids")).unwrap_or_default();
        if monetary_path(path) {
            reasons.extend(monetary_adjustment_reasons(
                plan,
                path,
                mapping,
                economic_basis,
                &valid_sources,
                &assumption_statuses,
            ));
        }
        reasons.extend(derivation_declaration_reasons(
            plan,
            path,
            mapping,
            &source_ids,
            &assumption_ids,
            &extraction_ids,
        ));
        if source_ids.is_empty() && assumption_ids.is_empty() {
            reasons.push("no evidence source or reviewable assumption is linked".into());
        }
        if source_ids.iter().any(|id| !valid_sources.contains(id)) {
            reasons.push("source link is missing or source metadata is incomplete".into());
        }
        if !source_ids.is_empty() {
            source_based_inputs += 1;
            if !synthesis_binding_valid {
                reasons.push("current evidence synthesis binding is missing or invalid".into());
            }
            if extraction_ids.is_empty() {
                reasons.push("source-based input has no selected extraction".into());
            }
            let unique = extraction_ids.iter().copied().collect::<HashSet<_>>();
            if unique.len() != extraction_ids.len() {
                reasons.push("selected extraction IDs are duplicated".into());
            }
            selected_extractions.extend(extraction_ids.iter().map(|id| (*id).to_string()));
        } else if !extraction_ids.is_empty() {
            reasons.push("extraction IDs require at least one evidence source".into());
        }
        if assumption_ids
            .iter()
            .any(|id| assumption_statuses.get(id).copied() != Some("proposed"))
        {
            reasons.push("assumption link is missing or is not proposed for human review".into());
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

fn extraction_derivation_reasons(
    plan: &serde_json::Value,
    mapping: &serde_json::Value,
    extraction_index: &HashMap<String, crate::heor_synthesis::ExtractionLink>,
) -> Vec<String> {
    let path = mapping
        .get("path")
        .and_then(serde_json::Value::as_str)
        .unwrap_or("mapping");
    let source_ids = string_list(mapping.get("source_ids")).unwrap_or_default();
    if source_ids.is_empty() {
        return Vec::new();
    }
    let extraction_ids = string_list(mapping.get("extraction_ids")).unwrap_or_default();
    if !monetary_path(path) {
        let [extraction_id] = extraction_ids.as_slice() else {
            return Vec::new();
        };
        let Some(extraction) = extraction_index.get(*extraction_id) else {
            return Vec::new();
        };
        let Ok(extracted) = serde_json::from_str::<serde_json::Value>(&extraction.extracted_value)
        else {
            return vec![format!(
                "{extraction_id}.extracted_value must be strict JSON"
            )];
        };
        if model_value(plan, path).is_some_and(|target| json_equivalent(&extracted, target)) {
            return Vec::new();
        }
        return vec![format!(
            "{extraction_id}.extracted_value does not equal the model input"
        )];
    }

    let selected = extraction_ids.iter().copied().collect::<HashSet<_>>();
    let mut used = HashSet::new();
    let mut reasons = Vec::new();
    let adjustments = mapping
        .get("monetary_adjustments")
        .and_then(serde_json::Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    for (position, adjustment) in adjustments.iter().enumerate() {
        let label = format!("monetary_adjustments[{position}]");
        let Some(adjustment) = adjustment.as_object() else {
            continue;
        };
        let Some(extraction_id) = adjustment
            .get("source_extraction_id")
            .and_then(serde_json::Value::as_str)
            .filter(|identifier| selected.contains(identifier))
        else {
            reasons.push(format!(
                "{label}.source_extraction_id must reference a selected extraction"
            ));
            continue;
        };
        used.insert(extraction_id);
        let Some(extraction) = extraction_index.get(extraction_id) else {
            continue;
        };
        let Ok(extracted) = serde_json::from_str::<serde_json::Value>(&extraction.extracted_value)
        else {
            reasons.push(format!(
                "{label} source extraction must contain strict JSON"
            ));
            continue;
        };
        let extracted_source = if let Some(values) = extracted.as_array() {
            let Some(index) = adjustment
                .get("source_index")
                .and_then(serde_json::Value::as_u64)
                .and_then(|value| usize::try_from(value).ok())
                .filter(|value| *value < values.len())
            else {
                reasons.push(format!("{label}.source_index is invalid"));
                continue;
            };
            &values[index]
        } else {
            if adjustment.contains_key("source_index") {
                reasons.push(format!(
                    "{label}.source_index must be omitted for a scalar extraction"
                ));
            }
            &extracted
        };
        if !adjustment
            .get("source_value")
            .is_some_and(|value| json_equivalent(value, extracted_source))
        {
            reasons.push(format!(
                "{label}.source_value does not match the bound extraction"
            ));
        }
    }
    if used != selected {
        reasons.push("monetary_adjustments must use every selected extraction".into());
    }
    reasons
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
        invalid_selections.extend(
            extraction_derivation_reasons(&plan, mapping, &extraction_index)
                .into_iter()
                .map(|reason| format!("{path}: {reason}")),
        );
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

    fn monetary_adjustments(path: &str) -> serde_json::Value {
        let values: Vec<f64> = match path {
            "strategies.comparator.state_costs" => vec![1000.0, 3000.0, 0.0],
            "strategies.intervention.state_costs" => vec![4000.0, 3000.0, 0.0],
            "willingness_to_pay" => vec![100000.0],
            _ => return serde_json::Value::Null,
        };
        serde_json::Value::Array(
            values
                .into_iter()
                .enumerate()
                .map(|(index, value)| {
                    let mut item = serde_json::json!({
                        "source_value": value,
                        "source_currency": "CNY",
                        "source_price_year": 2026,
                        "factor": 1.0,
                        "method": "none",
                        "basis_ids": [],
                        "source_extraction_id": format!("extract-{}", path.replace('.', "-"))
                    });
                    if path.ends_with("state_costs") {
                        item["target_index"] = serde_json::json!(index);
                        item["source_index"] = serde_json::json!(index);
                    }
                    item
                })
                .collect(),
        )
    }

    fn complete_plan() -> serde_json::Value {
        let paths = required_input_paths(&serde_json::json!({ "willingness_to_pay": 100000 }));
        let mut plan = serde_json::json!({
            "schema_version": "0.3.0",
            "economic_basis": {"currency": "CNY", "price_year": 2026},
            "willingness_to_pay": 100000,
            "cycles": 3,
            "cycle_length_years": 1.0,
            "discount_rates": {"costs": 0.05, "outcomes": 0.05},
            "half_cycle_correction": true,
            "strategies": {
                "comparator": {
                    "initial_distribution": [1.0, 0.0, 0.0],
                    "transition_matrix": [[0.7, 0.2, 0.1], [0.0, 0.7, 0.3], [0.0, 0.0, 1.0]],
                    "state_costs": [1000.0, 3000.0, 0.0],
                    "state_utilities": [0.8, 0.5, 0.0]
                },
                "intervention": {
                    "initial_distribution": [1.0, 0.0, 0.0],
                    "transition_matrix": [[0.8, 0.15, 0.05], [0.0, 0.75, 0.25], [0.0, 0.0, 1.0]],
                    "state_costs": [4000.0, 3000.0, 0.0],
                    "state_utilities": [0.8, 0.5, 0.0]
                }
            },
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
            "input_provenance": []
        });
        plan["input_provenance"] = serde_json::Value::Array(paths.into_iter().map(|path| serde_json::json!({
                "path": path,
                "source_ids": ["source-1"],
                "extraction_ids": [format!("extract-{}", path.replace('.', "-"))],
                "assumption_ids": [],
                "unit": "model-specific",
                "jurisdiction": "China",
                "currency": if monetary_path(path) { Some("CNY") } else { None },
                "price_year": if monetary_path(path) { Some(2026) } else { None },
                "monetary_adjustments": monetary_adjustments(path),
                "derivation": {
                    "method": if monetary_path(path) { "monetary_adjustment" } else { "direct_evidence" },
                    "model_value": model_value(&plan, path).cloned().unwrap()
                },
                "selection_rationale": "Pre-specified source",
                "uncertainty_status": "fixed"
            })).collect());
        plan
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
        first["derivation"]["method"] = serde_json::json!("explicit_assumption");
        assert!(audit_plan(&plan).complete);
    }

    #[test]
    fn monetary_adjustment_must_reproduce_the_model_value() {
        let mut plan = complete_plan();
        let mapping = plan["input_provenance"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .find(|item| item["path"] == "strategies.intervention.state_costs")
            .unwrap();
        mapping["monetary_adjustments"][0]["source_value"] = serde_json::json!(3999.0);

        let audit = audit_plan(&plan);

        assert!(!audit.complete);
        assert!(audit
            .invalid_mappings
            .join("; ")
            .contains("does not reproduce model value"));
    }

    #[test]
    fn documented_cross_basis_adjustment_is_eligible() {
        let mut plan = complete_plan();
        let mapping = plan["input_provenance"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .find(|item| item["path"] == "willingness_to_pay")
            .unwrap();
        mapping["monetary_adjustments"] = serde_json::json!([{
            "source_value": 12500.0,
            "source_currency": "USD",
            "source_price_year": 2024,
            "factor": 8.0,
            "method": "Documented inflation and exchange-rate composite factor",
            "basis_ids": ["source-1"],
            "source_extraction_id": "extract-willingness_to_pay"
        }]);

        assert!(audit_plan(&plan).complete);
    }

    #[test]
    fn prior_schema_and_stale_derivation_snapshot_fail_closed() {
        let mut plan = complete_plan();
        plan["schema_version"] = serde_json::json!("0.2.0");
        plan["input_provenance"][0]["derivation"]["model_value"] = serde_json::json!(999);

        let audit = audit_plan(&plan);

        assert!(!audit.complete);
        let errors = audit.invalid_mappings.join("; ");
        assert!(errors.contains("schema_version must be 0.3.0"));
        assert!(errors.contains("does not match the current model input"));
    }

    #[test]
    fn native_derivation_rejects_changed_extracted_value() {
        let plan = complete_plan();
        let mapping = &plan["input_provenance"][0];
        let extraction_id = mapping["extraction_ids"][0].as_str().unwrap();
        let mut index = HashMap::new();
        index.insert(
            extraction_id.to_string(),
            crate::heor_synthesis::ExtractionLink {
                record_id: "source-1".into(),
                target: "cycles".into(),
                extracted_value: "4".into(),
            },
        );

        assert!(extraction_derivation_reasons(&plan, mapping, &index)
            .join("; ")
            .contains("does not equal the model input"));
    }

    #[test]
    fn native_derivation_rejects_narrative_and_changed_monetary_source_values() {
        let plan = complete_plan();
        let direct = &plan["input_provenance"][0];
        let direct_id = direct["extraction_ids"][0].as_str().unwrap();
        let mut direct_index = HashMap::new();
        direct_index.insert(
            direct_id.to_string(),
            crate::heor_synthesis::ExtractionLink {
                record_id: "source-1".into(),
                target: "cycles".into(),
                extracted_value: "three cycles".into(),
            },
        );
        assert!(extraction_derivation_reasons(&plan, direct, &direct_index)
            .join("; ")
            .contains("must be strict JSON"));

        let monetary = plan["input_provenance"]
            .as_array()
            .unwrap()
            .iter()
            .find(|mapping| mapping["path"] == "strategies.intervention.state_costs")
            .unwrap();
        let monetary_id = monetary["extraction_ids"][0].as_str().unwrap();
        let mut monetary_index = HashMap::new();
        monetary_index.insert(
            monetary_id.to_string(),
            crate::heor_synthesis::ExtractionLink {
                record_id: "source-1".into(),
                target: "strategies.intervention.state_costs".into(),
                extracted_value: "[3999,3000,0]".into(),
            },
        );
        assert!(
            extraction_derivation_reasons(&plan, monetary, &monetary_index)
                .join("; ")
                .contains("source_value does not match the bound extraction")
        );
    }
}
