//! Native fail-closed audit for evidence-linked health-state utility schedules.
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::path::Path;

pub const UTILITY_INPUTS_PATH: &str = "heor/utility-inputs.json";
const ANALYSIS_PATH: &str = "heor/analysis-plan.json";
const TOLERANCE: f64 = 1e-9;

#[derive(Clone, Debug)]
pub struct UtilityInputAudit {
    pub complete: bool,
    pub sha256: String,
    pub item_count: usize,
    pub mapped_item_count: usize,
    pub adjusted_item_count: usize,
    pub artifact_bindings: Vec<crate::heor_approval::ArtifactBinding>,
    pub errors: Vec<String>,
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn exact(value: &serde_json::Value, fields: &[&str]) -> bool {
    value.as_object().is_some_and(|object| {
        object.len() == fields.len() && fields.iter().all(|field| object.contains_key(*field))
    })
}

fn safe_id(value: &str) -> bool {
    let mut bytes = value.bytes();
    matches!(bytes.next(), Some(b'a'..=b'z'))
        && value.len() <= 64
        && bytes.all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'-' | b'_')
        })
}

fn nonempty(value: Option<&serde_json::Value>) -> bool {
    value
        .and_then(serde_json::Value::as_str)
        .is_some_and(|value| !value.trim().is_empty())
}

fn strings(value: Option<&serde_json::Value>, allow_empty: bool) -> Option<Vec<String>> {
    let values = value?.as_array()?;
    if !allow_empty && values.is_empty() {
        return None;
    }
    let mut seen = HashSet::new();
    let mut result = Vec::with_capacity(values.len());
    for value in values {
        let item = value.as_str()?.trim();
        if item.is_empty() || !seen.insert(item.to_owned()) {
            return None;
        }
        result.push(item.to_owned());
    }
    Some(result)
}

fn finite(value: Option<&serde_json::Value>) -> Option<f64> {
    value
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite())
}

fn utility(value: Option<&serde_json::Value>) -> Option<f64> {
    finite(value).filter(|value| (-1.0..=1.0).contains(value))
}

fn close(left: f64, right: f64) -> bool {
    (left - right).abs() <= (left.abs().max(right.abs()) * TOLERANCE).max(TOLERANCE)
}

fn basis_ids(plan: &serde_json::Value) -> HashSet<String> {
    let mut result = HashSet::new();
    for source in plan
        .get("evidence_sources")
        .and_then(serde_json::Value::as_array)
        .into_iter()
        .flatten()
    {
        if let Some(identifier) = source.get("id").and_then(serde_json::Value::as_str) {
            result.insert(identifier.to_owned());
        }
    }
    for assumption in plan
        .get("assumptions")
        .and_then(serde_json::Value::as_array)
        .into_iter()
        .flatten()
    {
        if assumption.get("status").and_then(serde_json::Value::as_str) == Some("proposed") {
            if let Some(identifier) = assumption.get("id").and_then(serde_json::Value::as_str) {
                result.insert(identifier.to_owned());
            }
        }
    }
    for mapping in plan
        .get("input_provenance")
        .and_then(serde_json::Value::as_array)
        .into_iter()
        .flatten()
    {
        for field in ["source_ids", "extraction_ids", "assumption_ids"] {
            for identifier in mapping
                .get(field)
                .and_then(serde_json::Value::as_array)
                .into_iter()
                .flatten()
                .filter_map(serde_json::Value::as_str)
            {
                result.insert(identifier.to_owned());
            }
        }
    }
    result
}

fn linked(value: Option<&serde_json::Value>, valid: &HashSet<String>) -> bool {
    strings(value, false).is_some_and(|values| values.iter().all(|item| valid.contains(item)))
}

fn admitted(value: Option<&serde_json::Value>, allowed: &[&str]) -> bool {
    value
        .and_then(serde_json::Value::as_str)
        .is_some_and(|value| allowed.contains(&value))
}

pub fn audit_utility_inputs(
    workspace: &Path,
    plan: &serde_json::Value,
    plan_raw: &[u8],
    psm: &serde_json::Value,
) -> UtilityInputAudit {
    let mut audit = UtilityInputAudit {
        complete: false,
        sha256: String::new(),
        item_count: 0,
        mapped_item_count: 0,
        adjusted_item_count: 0,
        artifact_bindings: Vec::new(),
        errors: Vec::new(),
    };
    let link = psm
        .get("utility_inputs")
        .unwrap_or(&serde_json::Value::Null);
    if !exact(link, &["path", "content_sha256"])
        || link.get("path").and_then(serde_json::Value::as_str) != Some(UTILITY_INPUTS_PATH)
    {
        audit
            .errors
            .push(format!("utility_inputs must bind {UTILITY_INPUTS_PATH}"));
        return audit;
    }
    let expected_sha = link
        .get("content_sha256")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default();
    let raw = match crate::heor_uncertainty::read_workspace_capped(workspace, UTILITY_INPUTS_PATH) {
        Ok(raw) => raw,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    audit.sha256 = sha256(&raw);
    if audit.sha256 != expected_sha {
        audit
            .errors
            .push("utility-input hash does not match current bytes".into());
    }
    audit
        .artifact_bindings
        .push(crate::heor_approval::ArtifactBinding {
            path: UTILITY_INPUTS_PATH.into(),
            sha256: audit.sha256.clone(),
        });
    let value: serde_json::Value = match serde_json::from_slice(&raw) {
        Ok(value) => value,
        Err(error) => {
            audit
                .errors
                .push(format!("utility inputs are invalid JSON: {error}"));
            return audit;
        }
    };
    if plan
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        .is_none_or(|schema| !matches!(schema, "0.14.0" | "0.15.0"))
    {
        audit
            .errors
            .push("utility inputs require analysis schema 0.14.0 or 0.15.0".into());
    }
    if !exact(
        &value,
        &[
            "schema_version",
            "utility_input_id",
            "analysis_id",
            "status",
            "base_analysis",
            "target_context",
            "cycle_value_timing",
            "item_order",
            "items",
            "cycle_state_utilities",
            "limitations",
        ],
    ) {
        audit
            .errors
            .push("utility-input fields are not the exact contract".into());
    }
    if value
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some("0.1.0")
        || value.get("status").and_then(serde_json::Value::as_str) != Some("ready_for_human_review")
        || value.get("analysis_id") != plan.get("analysis_id")
        || !value
            .get("utility_input_id")
            .and_then(serde_json::Value::as_str)
            .is_some_and(safe_id)
    {
        audit
            .errors
            .push("utility-input identity or status is invalid".into());
    }
    if !exact(
        value
            .get("base_analysis")
            .unwrap_or(&serde_json::Value::Null),
        &["path", "content_sha256"],
    ) || value
        .pointer("/base_analysis/path")
        .and_then(serde_json::Value::as_str)
        != Some(ANALYSIS_PATH)
        || value
            .pointer("/base_analysis/content_sha256")
            .and_then(serde_json::Value::as_str)
            != Some(sha256(plan_raw).as_str())
    {
        audit
            .errors
            .push("utility-input base_analysis is stale".into());
    }
    let target = value
        .get("target_context")
        .unwrap_or(&serde_json::Value::Null);
    if !exact(target, &["jurisdiction", "population", "outcome"])
        || target.get("jurisdiction") != plan.pointer("/decision_problem/jurisdiction")
        || target.get("population") != plan.pointer("/decision_problem/population")
        || target.get("outcome").and_then(serde_json::Value::as_str) != Some("QALY")
        || value
            .get("cycle_value_timing")
            .and_then(serde_json::Value::as_str)
            != Some("cycle_average")
    {
        audit
            .errors
            .push("utility-input target context or timing does not match analysis".into());
    }
    let cycles = plan
        .get("cycles")
        .and_then(serde_json::Value::as_u64)
        .unwrap_or_default() as usize;
    let order = strings(plan.get("strategy_order"), false).unwrap_or_default();
    let states = strings(plan.get("states"), false).unwrap_or_default();
    let strategy_keys = plan
        .get("strategies")
        .and_then(serde_json::Value::as_object)
        .map(|strategies| strategies.keys().cloned().collect::<HashSet<_>>())
        .unwrap_or_default();
    let valid_ids = basis_ids(plan);
    let item_order = strings(value.get("item_order"), false).unwrap_or_default();
    audit.item_count = item_order.len();
    if cycles == 0
        || cycles > 10_000
        || order.is_empty()
        || states.is_empty()
        || strategy_keys != order.iter().cloned().collect::<HashSet<_>>()
        || item_order.len() != order.len() * states.len()
        || item_order.iter().any(|item| !safe_id(item))
    {
        audit
            .errors
            .push("utility-input dimensions or item_order are invalid".into());
    }
    let items = value.get("items").and_then(serde_json::Value::as_object);
    if items.is_none_or(|items| {
        items.len() != item_order.len() || item_order.iter().any(|item| !items.contains_key(item))
    }) {
        audit
            .errors
            .push("utility-input items do not match item_order".into());
    }
    let mut computed: HashMap<String, Vec<Vec<f64>>> = order
        .iter()
        .map(|strategy| (strategy.clone(), vec![vec![0.0; states.len()]; cycles]))
        .collect();
    let mut pairs = HashSet::new();
    for item_id in &item_order {
        let Some(item) = items.and_then(|items| items.get(item_id)) else {
            continue;
        };
        if !exact(
            item,
            &[
                "item_id",
                "strategy_id",
                "state_id",
                "description",
                "application",
                "measurement",
                "valuation",
                "mapping",
                "source_utility",
                "adjustments",
                "cycle_values",
                "uncertainty",
            ],
        ) {
            audit
                .errors
                .push(format!("utility item {item_id} fields are invalid"));
            continue;
        }
        let strategy = item
            .get("strategy_id")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        let state = item
            .get("state_id")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        if item.get("item_id").and_then(serde_json::Value::as_str) != Some(item_id)
            || !order.iter().any(|candidate| candidate == strategy)
            || !states.iter().any(|candidate| candidate == state)
            || !pairs.insert((strategy.to_owned(), state.to_owned()))
            || !nonempty(item.get("description"))
        {
            audit
                .errors
                .push(format!("utility item {item_id} identity is invalid"));
        }
        let application = item.get("application").unwrap_or(&serde_json::Value::Null);
        let overlap = application
            .get("overlap_assessment")
            .unwrap_or(&serde_json::Value::Null);
        if !exact(
            application,
            &[
                "type",
                "timing",
                "captured_effects",
                "excluded_effects",
                "overlap_assessment",
            ],
        ) || application.get("type").and_then(serde_json::Value::as_str)
            != Some("health_state_utility")
            || application
                .get("timing")
                .and_then(serde_json::Value::as_str)
                != Some("cycle_average_while_in_state")
            || strings(application.get("captured_effects"), false).is_none()
            || strings(application.get("excluded_effects"), true).is_none()
            || !exact(overlap, &["rationale", "basis_ids"])
            || !nonempty(overlap.get("rationale"))
            || !linked(overlap.get("basis_ids"), &valid_ids)
        {
            audit.errors.push(format!(
                "utility item {item_id} application or overlap is invalid"
            ));
        }
        let measurement = item.get("measurement").unwrap_or(&serde_json::Value::Null);
        if !exact(
            measurement,
            &[
                "source_design",
                "instrument_name",
                "instrument_version",
                "instrument_class",
                "respondent",
                "source_population",
                "sample_size",
                "assessment_timing",
                "basis_ids",
            ],
        ) || ![
            "instrument_name",
            "instrument_version",
            "source_population",
            "assessment_timing",
        ]
        .iter()
        .all(|field| nonempty(measurement.get(*field)))
            || !admitted(
                measurement.get("source_design"),
                &[
                    "randomized_trial",
                    "observational_study",
                    "systematic_review",
                    "published_model",
                    "elicitation_study",
                    "anchor",
                    "other",
                ],
            )
            || !admitted(
                measurement.get("instrument_class"),
                &[
                    "generic_preference_based",
                    "condition_specific_preference_based",
                    "direct_valuation",
                    "mapped_non_preference_measure",
                    "qaly_anchor",
                    "other",
                ],
            )
            || !admitted(
                measurement.get("respondent"),
                &[
                    "patient",
                    "proxy",
                    "carer",
                    "general_public",
                    "mixed",
                    "not_applicable",
                ],
            )
            || !linked(measurement.get("basis_ids"), &valid_ids)
            || measurement.get("sample_size").is_some_and(|sample| {
                !sample.is_null() && sample.as_u64().is_none_or(|sample| sample == 0)
            })
        {
            audit
                .errors
                .push(format!("utility item {item_id} measurement is invalid"));
        }
        let valuation = item.get("valuation").unwrap_or(&serde_json::Value::Null);
        let origin = valuation
            .get("value_origin")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        if !exact(
            valuation,
            &[
                "value_origin",
                "value_set_id",
                "value_set_jurisdiction",
                "preference_population",
                "valuation_method",
                "anchor",
                "license_status",
                "basis_ids",
            ],
        ) || !matches!(
            origin,
            "value_set" | "direct_valuation" | "mapped" | "anchor"
        ) || valuation.get("anchor").and_then(serde_json::Value::as_str)
            != Some("dead_0_full_health_1")
            || !nonempty(valuation.get("preference_population"))
            || !admitted(
                valuation.get("valuation_method"),
                &[
                    "time_trade_off",
                    "standard_gamble",
                    "discrete_choice_experiment",
                    "hybrid",
                    "algorithmic_mapping",
                    "anchor",
                    "other",
                ],
            )
            || !admitted(
                valuation.get("license_status"),
                &[
                    "public",
                    "registered_noncommercial",
                    "licensed_local",
                    "link_only",
                    "not_applicable",
                ],
            )
            || !linked(valuation.get("basis_ids"), &valid_ids)
            || (matches!(origin, "value_set" | "mapped")
                && (!nonempty(valuation.get("value_set_id"))
                    || !nonempty(valuation.get("value_set_jurisdiction"))))
            || (!matches!(origin, "value_set" | "mapped")
                && (!valuation
                    .get("value_set_id")
                    .is_some_and(serde_json::Value::is_null)
                    || !valuation
                        .get("value_set_jurisdiction")
                        .is_some_and(serde_json::Value::is_null)))
            || (state != "dead" && origin == "anchor")
        {
            audit
                .errors
                .push(format!("utility item {item_id} valuation is invalid"));
        }
        if origin == "mapped" {
            audit.mapped_item_count += 1;
            let mapping = item.get("mapping").unwrap_or(&serde_json::Value::Null);
            if valuation
                .get("valuation_method")
                .and_then(serde_json::Value::as_str)
                != Some("algorithmic_mapping")
                || !exact(
                    mapping,
                    &[
                        "source_measure",
                        "target_measure",
                        "algorithm_id",
                        "estimation_population",
                        "validation_status",
                        "performance_basis_ids",
                        "license_status",
                    ],
                )
                || ![
                    "source_measure",
                    "target_measure",
                    "algorithm_id",
                    "estimation_population",
                ]
                .iter()
                .all(|field| nonempty(mapping.get(*field)))
                || !admitted(
                    mapping.get("validation_status"),
                    &["internal", "external", "both"],
                )
                || !admitted(
                    mapping.get("license_status"),
                    &[
                        "public",
                        "registered_noncommercial",
                        "licensed_local",
                        "link_only",
                    ],
                )
                || !linked(mapping.get("performance_basis_ids"), &valid_ids)
            {
                audit
                    .errors
                    .push(format!("utility item {item_id} mapping is invalid"));
            }
        } else if item.get("mapping").is_none_or(|mapping| !mapping.is_null()) {
            audit
                .errors
                .push(format!("utility item {item_id} mapping must be null"));
        }
        let source = item
            .get("source_utility")
            .unwrap_or(&serde_json::Value::Null);
        let source_value = utility(source.get("value"));
        if !exact(source, &["value", "basis_ids"])
            || source_value.is_none()
            || !linked(source.get("basis_ids"), &valid_ids)
        {
            audit
                .errors
                .push(format!("utility item {item_id} source utility is invalid"));
        }
        let mut factors = vec![1.0; cycles];
        let adjustments = item
            .get("adjustments")
            .and_then(serde_json::Value::as_array);
        let mut kinds = HashSet::new();
        if adjustments.is_none_or(|items| items.len() > 3) {
            audit
                .errors
                .push(format!("utility item {item_id} adjustments are invalid"));
        } else if let Some(adjustments) = adjustments {
            if !adjustments.is_empty() {
                audit.adjusted_item_count += 1;
            }
            for adjustment in adjustments {
                let kind = adjustment
                    .get("kind")
                    .and_then(serde_json::Value::as_str)
                    .unwrap_or_default();
                let values = adjustment
                    .get("factors")
                    .and_then(serde_json::Value::as_array);
                if !exact(
                    adjustment,
                    &["kind", "operation", "method", "factors", "basis_ids"],
                ) || !matches!(
                    kind,
                    "age_adjustment" | "comorbidity_adjustment" | "population_alignment"
                ) || !kinds.insert(kind)
                    || adjustment
                        .get("operation")
                        .and_then(serde_json::Value::as_str)
                        != Some("multiply")
                    || !nonempty(adjustment.get("method"))
                    || !linked(adjustment.get("basis_ids"), &valid_ids)
                    || values.is_none_or(|values| values.len() != cycles)
                {
                    audit
                        .errors
                        .push(format!("utility item {item_id} adjustment is invalid"));
                    continue;
                }
                for (cycle, value) in values.into_iter().flatten().enumerate() {
                    if let Some(factor) = finite(Some(value)).filter(|factor| *factor > 0.0) {
                        factors[cycle] *= factor;
                    } else {
                        audit.errors.push(format!(
                            "utility item {item_id} adjustment factor is invalid"
                        ));
                    }
                }
            }
        }
        let values = item
            .get("cycle_values")
            .and_then(serde_json::Value::as_array);
        if values.is_none_or(|values| values.len() != cycles) {
            audit
                .errors
                .push(format!("utility item {item_id} cycle values are invalid"));
        } else if let (Some(source_value), Some(values), Some(state_index), Some(schedule)) = (
            source_value,
            values,
            states.iter().position(|candidate| candidate == state),
            computed.get_mut(strategy),
        ) {
            for (cycle, raw_value) in values.iter().enumerate() {
                if let Some(actual) = utility(Some(raw_value)) {
                    if !close(actual, source_value * factors[cycle]) {
                        audit
                            .errors
                            .push(format!("utility item {item_id} cycle arithmetic drifted"));
                    }
                    schedule[cycle][state_index] = actual;
                } else {
                    audit
                        .errors
                        .push(format!("utility item {item_id} cycle utility is invalid"));
                }
            }
            if state == "dead"
                && (!close(source_value, 0.0)
                    || !adjustments.is_some_and(Vec::is_empty)
                    || origin != "anchor"
                    || measurement
                        .get("source_design")
                        .and_then(serde_json::Value::as_str)
                        != Some("anchor")
                    || measurement
                        .get("instrument_class")
                        .and_then(serde_json::Value::as_str)
                        != Some("qaly_anchor")
                    || measurement
                        .get("respondent")
                        .and_then(serde_json::Value::as_str)
                        != Some("not_applicable")
                    || !measurement
                        .get("sample_size")
                        .is_some_and(serde_json::Value::is_null)
                    || valuation
                        .get("valuation_method")
                        .and_then(serde_json::Value::as_str)
                        != Some("anchor")
                    || valuation
                        .get("license_status")
                        .and_then(serde_json::Value::as_str)
                        != Some("not_applicable"))
            {
                audit.errors.push(format!(
                    "utility item {item_id} dead state is not the zero anchor"
                ));
            }
        }
        let uncertainty = item.get("uncertainty").unwrap_or(&serde_json::Value::Null);
        if !exact(uncertainty, &["status", "basis_ids", "limitations"])
            || !matches!(
                uncertainty
                    .get("status")
                    .and_then(serde_json::Value::as_str),
                Some("fixed" | "range_available" | "distribution_available")
            )
            || !linked(uncertainty.get("basis_ids"), &valid_ids)
            || strings(uncertainty.get("limitations"), false).is_none()
        {
            audit
                .errors
                .push(format!("utility item {item_id} uncertainty is invalid"));
        }
    }
    let declared = value
        .get("cycle_state_utilities")
        .and_then(serde_json::Value::as_object);
    if declared.is_none_or(|declared| declared.len() != order.len()) {
        audit
            .errors
            .push("cycle_state_utilities strategies are invalid".into());
    }
    for strategy in &order {
        let rows = declared
            .and_then(|declared| declared.get(strategy))
            .and_then(serde_json::Value::as_array);
        let aggregate = plan
            .pointer(&format!("/strategies/{strategy}/state_utilities"))
            .and_then(serde_json::Value::as_array);
        if rows.is_none_or(|rows| rows.len() != cycles)
            || aggregate.is_none_or(|values| values.len() != states.len())
        {
            audit.errors.push(format!(
                "utility schedule for {strategy} has invalid dimensions"
            ));
            continue;
        }
        for (cycle, row) in rows.into_iter().flatten().enumerate() {
            let values = row.as_array();
            if values.is_none_or(|values| values.len() != states.len()) {
                audit.errors.push(format!(
                    "utility schedule for {strategy} cycle {cycle} is invalid"
                ));
                continue;
            }
            for (state, raw_value) in values.into_iter().flatten().enumerate() {
                let actual = utility(Some(raw_value));
                let expected = computed
                    .get(strategy)
                    .and_then(|rows| rows.get(cycle))
                    .and_then(|row| row.get(state))
                    .copied();
                if actual
                    .zip(expected)
                    .is_none_or(|(actual, expected)| !close(actual, expected))
                {
                    audit.errors.push(format!(
                        "utility schedule for {strategy} cycle {cycle} drifted"
                    ));
                }
                if cycle == 0 {
                    let analysis_value = aggregate
                        .and_then(|values| values.get(state))
                        .and_then(|value| finite(Some(value)));
                    if actual
                        .zip(analysis_value)
                        .is_none_or(|(actual, expected)| !close(actual, expected))
                    {
                        audit.errors.push(format!("utility schedule for {strategy} does not match first-cycle analysis utilities"));
                    }
                }
            }
        }
    }
    if strings(value.get("limitations"), false).is_none() {
        audit
            .errors
            .push("utility-input limitations are required".into());
    }
    let authority = String::from_utf8_lossy(&raw).to_ascii_lowercase();
    if [
        "\"approved\":",
        "\"approval_timestamp\":",
        "\"independently_validated\":",
    ]
    .iter()
    .any(|field| authority.contains(field))
    {
        audit
            .errors
            .push("utility inputs contain a forbidden authority field".into());
    }
    audit.complete = audit.errors.is_empty();
    audit
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture(
        tag: &str,
    ) -> (
        std::path::PathBuf,
        serde_json::Value,
        Vec<u8>,
        serde_json::Value,
        serde_json::Value,
    ) {
        let root =
            std::env::temp_dir().join(format!("ai4heor-utility-{tag}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("heor")).unwrap();
        let plan = serde_json::json!({
            "schema_version": "0.14.0", "analysis_id": "utility-native-test",
            "decision_problem": {"jurisdiction": "England", "population": "Adults"},
            "cycles": 1, "states": ["alive", "dead"], "strategy_order": ["comparator"],
            "strategies": {"comparator": {"state_utilities": [0.8, 0.0]}},
            "evidence_sources": [{"id": "utility-source"}, {"id": "value-set-source"}],
            "assumptions": [{"id": "overlap", "status": "proposed"}, {"id": "dead-anchor", "status": "proposed"}],
            "input_provenance": []
        });
        let plan_raw = serde_json::to_vec(&plan).unwrap();
        let artifact = serde_json::json!({
            "schema_version": "0.1.0", "utility_input_id": "utility-inputs",
            "analysis_id": "utility-native-test", "status": "ready_for_human_review",
            "base_analysis": {"path": "heor/analysis-plan.json", "content_sha256": sha256(&plan_raw)},
            "target_context": {"jurisdiction": "England", "population": "Adults", "outcome": "QALY"},
            "cycle_value_timing": "cycle_average",
            "item_order": ["comparator-alive", "comparator-dead"],
            "items": {
                "comparator-alive": {
                    "item_id": "comparator-alive", "strategy_id": "comparator", "state_id": "alive", "description": "Alive utility",
                    "application": {"type": "health_state_utility", "timing": "cycle_average_while_in_state", "captured_effects": ["health_state"], "excluded_effects": ["events"], "overlap_assessment": {"rationale": "Events are excluded.", "basis_ids": ["overlap"]}},
                    "measurement": {"source_design": "randomized_trial", "instrument_name": "EQ-5D", "instrument_version": "5L", "instrument_class": "generic_preference_based", "respondent": "patient", "source_population": "Trial", "sample_size": 100, "assessment_timing": "Visit", "basis_ids": ["utility-source"]},
                    "valuation": {"value_origin": "value_set", "value_set_id": "reviewed-set", "value_set_jurisdiction": "England", "preference_population": "General population", "valuation_method": "time_trade_off", "anchor": "dead_0_full_health_1", "license_status": "link_only", "basis_ids": ["value-set-source"]},
                    "mapping": null, "source_utility": {"value": 0.8, "basis_ids": ["utility-source"]}, "adjustments": [], "cycle_values": [0.8],
                    "uncertainty": {"status": "fixed", "basis_ids": ["utility-source"], "limitations": ["Not executed."]}
                },
                "comparator-dead": {
                    "item_id": "comparator-dead", "strategy_id": "comparator", "state_id": "dead", "description": "Dead anchor",
                    "application": {"type": "health_state_utility", "timing": "cycle_average_while_in_state", "captured_effects": ["death"], "excluded_effects": ["events"], "overlap_assessment": {"rationale": "QALY anchor.", "basis_ids": ["dead-anchor"]}},
                    "measurement": {"source_design": "anchor", "instrument_name": "QALY anchor", "instrument_version": "not_applicable", "instrument_class": "qaly_anchor", "respondent": "not_applicable", "source_population": "Definition", "sample_size": null, "assessment_timing": "not_applicable", "basis_ids": ["dead-anchor"]},
                    "valuation": {"value_origin": "anchor", "value_set_id": null, "value_set_jurisdiction": null, "preference_population": "not_applicable", "valuation_method": "anchor", "anchor": "dead_0_full_health_1", "license_status": "not_applicable", "basis_ids": ["dead-anchor"]},
                    "mapping": null, "source_utility": {"value": 0.0, "basis_ids": ["dead-anchor"]}, "adjustments": [], "cycle_values": [0.0],
                    "uncertainty": {"status": "fixed", "basis_ids": ["dead-anchor"], "limitations": ["Not executed."]}
                }
            },
            "cycle_state_utilities": {"comparator": [[0.8, 0.0]]},
            "limitations": ["Event disutilities are excluded."]
        });
        let raw = serde_json::to_vec(&artifact).unwrap();
        let psm = serde_json::json!({"utility_inputs": {"path": UTILITY_INPUTS_PATH, "content_sha256": sha256(&raw)}});
        std::fs::write(root.join(UTILITY_INPUTS_PATH), raw).unwrap();
        (root, plan, plan_raw, psm, artifact)
    }

    #[test]
    fn audits_valid_schedule_and_rejects_arithmetic_drift() {
        let (root, plan, plan_raw, mut psm, mut artifact) = fixture("arithmetic");
        let valid = audit_utility_inputs(&root, &plan, &plan_raw, &psm);
        assert!(valid.complete, "{:?}", valid.errors);
        artifact["items"]["comparator-alive"]["cycle_values"][0] = serde_json::json!(0.7);
        let raw = serde_json::to_vec(&artifact).unwrap();
        psm["utility_inputs"]["content_sha256"] = serde_json::json!(sha256(&raw));
        std::fs::write(root.join(UTILITY_INPUTS_PATH), raw).unwrap();
        let drift = audit_utility_inputs(&root, &plan, &plan_raw, &psm);
        assert!(!drift.complete);
        assert!(drift
            .errors
            .iter()
            .any(|error| error.contains("arithmetic drifted")));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn rejects_legacy_schema_and_dead_metadata_drift() {
        let (root, mut plan, _, mut psm, mut artifact) = fixture("boundary");
        plan["schema_version"] = serde_json::json!("0.13.0");
        let mut plan_raw = serde_json::to_vec(&plan).unwrap();
        artifact["base_analysis"]["content_sha256"] = serde_json::json!(sha256(&plan_raw));
        let raw = serde_json::to_vec(&artifact).unwrap();
        psm["utility_inputs"]["content_sha256"] = serde_json::json!(sha256(&raw));
        std::fs::write(root.join(UTILITY_INPUTS_PATH), raw).unwrap();
        let legacy = audit_utility_inputs(&root, &plan, &plan_raw, &psm);
        assert!(!legacy.complete);
        assert!(legacy
            .errors
            .iter()
            .any(|error| error.contains("analysis schema 0.14.0")));

        plan["schema_version"] = serde_json::json!("0.14.0");
        plan_raw = serde_json::to_vec(&plan).unwrap();
        artifact["base_analysis"]["content_sha256"] = serde_json::json!(sha256(&plan_raw));
        artifact["items"]["comparator-dead"]["measurement"]["respondent"] =
            serde_json::json!("patient");
        let raw = serde_json::to_vec(&artifact).unwrap();
        psm["utility_inputs"]["content_sha256"] = serde_json::json!(sha256(&raw));
        std::fs::write(root.join(UTILITY_INPUTS_PATH), raw).unwrap();
        let metadata = audit_utility_inputs(&root, &plan, &plan_raw, &psm);
        assert!(!metadata.complete);
        assert!(metadata
            .errors
            .iter()
            .any(|error| error.contains("dead state is not the zero anchor")));
        let _ = std::fs::remove_dir_all(root);
    }
}
