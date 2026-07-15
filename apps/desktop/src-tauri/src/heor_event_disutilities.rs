//! Native fail-closed audit for event-related QALY losses.
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::path::Path;

pub const EVENT_DISUTILITIES_PATH: &str = "heor/event-disutilities.json";
const ANALYSIS_PATH: &str = "heor/analysis-plan.json";
const UTILITY_INPUTS_PATH: &str = "heor/utility-inputs.json";
const TOLERANCE: f64 = 1e-9;

#[derive(Clone, Debug)]
pub struct EventDisutilityAudit {
    pub complete: bool,
    pub sha256: String,
    pub event_disutility_id: String,
    pub item_count: usize,
    pub one_time_item_count: usize,
    pub recurrent_item_count: usize,
    pub continuous_exposure_item_count: usize,
    pub cycle_state_qaly_losses: HashMap<String, Vec<Vec<f64>>>,
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

fn numbers(value: Option<&serde_json::Value>) -> Option<Vec<f64>> {
    value?
        .as_array()?
        .iter()
        .map(|value| value.as_f64().filter(|value| value.is_finite()))
        .collect()
}

fn finite(value: Option<&serde_json::Value>) -> Option<f64> {
    value
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite())
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

fn binding(value: Option<&serde_json::Value>, path: &str, raw: &[u8]) -> bool {
    let Some(value) = value else {
        return false;
    };
    exact(value, &["path", "content_sha256"])
        && value.get("path").and_then(serde_json::Value::as_str) == Some(path)
        && value
            .get("content_sha256")
            .and_then(serde_json::Value::as_str)
            == Some(sha256(raw).as_str())
}

/// Audit the exact event-disutility bytes bound by a partitioned-survival plan.
///
/// The utility artifact is passed explicitly because event overlap and the
/// implied utility floor are cross-artifact invariants. Its own native audit
/// remains a separate prerequisite for executing the model.
pub fn audit_event_disutilities(
    workspace: &Path,
    plan: &serde_json::Value,
    plan_raw: &[u8],
    psm: &serde_json::Value,
    utility_inputs: &serde_json::Value,
    utility_inputs_raw: &[u8],
) -> EventDisutilityAudit {
    let mut audit = EventDisutilityAudit {
        complete: false,
        sha256: String::new(),
        event_disutility_id: String::new(),
        item_count: 0,
        one_time_item_count: 0,
        recurrent_item_count: 0,
        continuous_exposure_item_count: 0,
        cycle_state_qaly_losses: HashMap::new(),
        artifact_bindings: Vec::new(),
        errors: Vec::new(),
    };
    let link = psm
        .get("event_disutilities")
        .unwrap_or(&serde_json::Value::Null);
    if !exact(link, &["path", "content_sha256"])
        || link.get("path").and_then(serde_json::Value::as_str) != Some(EVENT_DISUTILITIES_PATH)
    {
        audit.errors.push(format!(
            "event_disutilities must bind {EVENT_DISUTILITIES_PATH}"
        ));
        return audit;
    }
    let expected_sha = link
        .get("content_sha256")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default();
    let raw =
        match crate::heor_uncertainty::read_workspace_capped(workspace, EVENT_DISUTILITIES_PATH) {
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
            .push("event-disutility hash does not match current bytes".into());
    }
    audit
        .artifact_bindings
        .push(crate::heor_approval::ArtifactBinding {
            path: EVENT_DISUTILITIES_PATH.into(),
            sha256: audit.sha256.clone(),
        });
    let value: serde_json::Value = match serde_json::from_slice(&raw) {
        Ok(value) => value,
        Err(error) => {
            audit
                .errors
                .push(format!("event disutilities are invalid JSON: {error}"));
            return audit;
        }
    };
    match serde_json::from_slice::<serde_json::Value>(utility_inputs_raw) {
        Ok(parsed) if &parsed == utility_inputs => {}
        Ok(_) => audit
            .errors
            .push("utility-input value does not match its current bytes".into()),
        Err(error) => audit
            .errors
            .push(format!("utility-input bytes are invalid JSON: {error}")),
    }

    if plan
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some("0.15.0")
    {
        audit
            .errors
            .push("event disutilities require analysis schema 0.15.0".into());
    }
    if !exact(
        &value,
        &[
            "schema_version",
            "event_disutility_id",
            "analysis_id",
            "status",
            "base_analysis",
            "base_utility_inputs",
            "day_count_convention",
            "combination_rule",
            "item_order",
            "items",
            "cycle_state_qaly_losses",
            "limitations",
        ],
    ) {
        audit
            .errors
            .push("event-disutility fields are not the exact contract".into());
    }
    audit.event_disutility_id = value
        .get("event_disutility_id")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default()
        .to_owned();
    if value
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some("0.1.0")
        || value.get("status").and_then(serde_json::Value::as_str) != Some("ready_for_human_review")
        || value.get("analysis_id") != plan.get("analysis_id")
        || !safe_id(&audit.event_disutility_id)
    {
        audit
            .errors
            .push("event-disutility identity or status is invalid".into());
    }
    if !binding(value.get("base_analysis"), ANALYSIS_PATH, plan_raw) {
        audit
            .errors
            .push("event-disutility base_analysis is stale".into());
    }
    if !binding(
        value.get("base_utility_inputs"),
        UTILITY_INPUTS_PATH,
        utility_inputs_raw,
    ) {
        audit
            .errors
            .push("event-disutility base_utility_inputs is stale".into());
    }

    let valid_ids = basis_ids(plan);
    let day_count = value
        .get("day_count_convention")
        .unwrap_or(&serde_json::Value::Null);
    let days_per_year = finite(day_count.get("days_per_year"));
    if !exact(day_count, &["days_per_year", "rationale", "basis_ids"])
        || !days_per_year.is_some_and(|value| value == 365.0 || value == 365.25)
        || !nonempty(day_count.get("rationale"))
        || !linked(day_count.get("basis_ids"), &valid_ids)
    {
        audit
            .errors
            .push("event-disutility day-count convention is invalid".into());
    }
    let combination = value
        .get("combination_rule")
        .unwrap_or(&serde_json::Value::Null);
    if !exact(combination, &["method", "rationale", "basis_ids"])
        || combination
            .get("method")
            .and_then(serde_json::Value::as_str)
            != Some("additive_expected_qaly_loss")
        || !nonempty(combination.get("rationale"))
        || !linked(combination.get("basis_ids"), &valid_ids)
    {
        audit
            .errors
            .push("event-disutility combination rule is invalid".into());
    }

    let cycles = plan
        .get("cycles")
        .and_then(serde_json::Value::as_u64)
        .unwrap_or_default() as usize;
    let cycle_length = finite(plan.get("cycle_length_years"));
    let order = strings(plan.get("strategy_order"), false).unwrap_or_default();
    let states = strings(plan.get("states"), false).unwrap_or_default();
    if cycles == 0
        || cycles > 10_000
        || cycle_length.is_none_or(|value| value <= 0.0)
        || order.is_empty()
        || order.iter().any(|identifier| !safe_id(identifier))
        || states.is_empty()
        || !states.iter().any(|state| state == "dead")
    {
        audit
            .errors
            .push("event-disutility analysis dimensions are invalid".into());
    }
    let cycle_length = cycle_length.unwrap_or(1.0);
    let days_per_year = days_per_year.unwrap_or(365.25);
    let cycle_days = cycle_length * days_per_year;

    let utility_items = utility_inputs
        .get("items")
        .and_then(serde_json::Value::as_object);
    let mut utility_by_pair: HashMap<(String, String), (String, &serde_json::Value)> =
        HashMap::new();
    if let Some(utility_items) = utility_items {
        for (item_id, item) in utility_items {
            let strategy = item
                .get("strategy_id")
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default();
            let state = item
                .get("state_id")
                .and_then(serde_json::Value::as_str)
                .unwrap_or_default();
            if strategy.is_empty()
                || state.is_empty()
                || utility_by_pair
                    .insert(
                        (strategy.to_owned(), state.to_owned()),
                        (item_id.to_owned(), item),
                    )
                    .is_some()
            {
                audit.errors.push(format!(
                    "utility item {item_id} has invalid or duplicate strategy/state identity"
                ));
            }
        }
    } else {
        audit
            .errors
            .push("utility inputs must contain items for event overlap review".into());
    }
    let utility_schedule = utility_inputs
        .get("cycle_state_utilities")
        .and_then(serde_json::Value::as_object);
    let mut base_utilities: HashMap<String, Vec<Vec<f64>>> = HashMap::new();
    if utility_schedule.is_none_or(|schedule| schedule.len() != order.len()) {
        audit
            .errors
            .push("utility schedule strategies do not match event dimensions".into());
    }
    for strategy in &order {
        let rows = utility_schedule
            .and_then(|schedule| schedule.get(strategy))
            .and_then(serde_json::Value::as_array);
        let mut normalized = Vec::with_capacity(cycles);
        if rows.is_none_or(|rows| rows.len() != cycles) {
            audit.errors.push(format!(
                "utility schedule for {strategy} does not match event cycles"
            ));
        }
        for (cycle, row) in rows.into_iter().flatten().enumerate() {
            let values = numbers(Some(row));
            if values.as_ref().is_none_or(|values| {
                values.len() != states.len()
                    || values.iter().any(|value| !(-1.0..=1.0).contains(value))
            }) {
                audit.errors.push(format!(
                    "utility schedule for {strategy} cycle {cycle} is invalid"
                ));
            }
            normalized.push(values.unwrap_or_default());
        }
        base_utilities.insert(strategy.clone(), normalized);
    }

    let item_order = strings(value.get("item_order"), false).unwrap_or_default();
    audit.item_count = item_order.len();
    if item_order.is_empty() || item_order.iter().any(|identifier| !safe_id(identifier)) {
        audit
            .errors
            .push("event-disutility item_order is invalid".into());
    }
    let items = value.get("items").and_then(serde_json::Value::as_object);
    if items.is_none_or(|items| {
        items.len() != item_order.len() || item_order.iter().any(|item| !items.contains_key(item))
    }) {
        audit
            .errors
            .push("event-disutility items do not match item_order".into());
    }
    let mut computed: HashMap<String, Vec<Vec<f64>>> = order
        .iter()
        .map(|strategy| (strategy.clone(), vec![vec![0.0; states.len()]; cycles]))
        .collect();
    let mut observed_events = HashSet::new();
    for item_id in &item_order {
        let Some(item) = items.and_then(|items| items.get(item_id)) else {
            continue;
        };
        if !exact(
            item,
            &[
                "item_id",
                "event_id",
                "strategy_id",
                "label",
                "event",
                "application",
                "health_impact",
                "occurrence",
                "utility_overlap",
                "cycle_qaly_loss_per_eligible_person",
                "uncertainty",
            ],
        ) {
            audit
                .errors
                .push(format!("event item {item_id} fields are invalid"));
        }
        let event_id = item
            .get("event_id")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        let strategy = item
            .get("strategy_id")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        if item.get("item_id").and_then(serde_json::Value::as_str) != Some(item_id)
            || !safe_id(event_id)
            || !order.iter().any(|candidate| candidate == strategy)
            || !observed_events.insert((strategy.to_owned(), event_id.to_owned()))
            || !nonempty(item.get("label"))
        {
            audit.errors.push(format!(
                "event item {item_id} identity is invalid or duplicated"
            ));
        }

        let event = item.get("event").unwrap_or(&serde_json::Value::Null);
        let severity = event.get("severity").unwrap_or(&serde_json::Value::Null);
        if !exact(
            event,
            &[
                "category",
                "terminology_system",
                "terminology_code",
                "severity",
            ],
        ) || !matches!(
            event.get("category").and_then(serde_json::Value::as_str),
            Some(
                "adverse_event"
                    | "treatment_process"
                    | "procedure"
                    | "diagnostic_consequence"
                    | "other"
            )
        ) || !nonempty(event.get("terminology_system"))
            || event.get("terminology_code").is_none_or(|value| {
                !value.is_null() && !value.as_str().is_some_and(|value| !value.trim().is_empty())
            })
            || !exact(severity, &["system", "grade", "rationale"])
            || !["system", "grade", "rationale"]
                .iter()
                .all(|field| nonempty(severity.get(*field)))
        {
            audit.errors.push(format!(
                "event item {item_id} terminology or severity is invalid"
            ));
        }

        let application = item.get("application").unwrap_or(&serde_json::Value::Null);
        let mode = application
            .get("mode")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        match mode {
            "one_time" => audit.one_time_item_count += 1,
            "recurrent" => audit.recurrent_item_count += 1,
            "continuous_exposure" => audit.continuous_exposure_item_count += 1,
            _ => audit
                .errors
                .push(format!("event item {item_id} application mode is invalid")),
        }
        let eligible_states = strings(application.get("eligible_states"), false);
        if !exact(
            application,
            &[
                "mode",
                "eligible_states",
                "timing",
                "cost_handling",
                "rationale",
                "basis_ids",
            ],
        ) || eligible_states.as_ref().is_none_or(|eligible| {
            eligible
                .iter()
                .any(|state| state == "dead" || !states.contains(state))
        }) || application
            .get("timing")
            .and_then(serde_json::Value::as_str)
            != Some("cycle_average")
            || application
                .get("cost_handling")
                .and_then(serde_json::Value::as_str)
                != Some("not_in_this_artifact")
            || !nonempty(application.get("rationale"))
            || !linked(application.get("basis_ids"), &valid_ids)
        {
            audit
                .errors
                .push(format!("event item {item_id} application is invalid"));
        }
        let eligible_states = eligible_states.unwrap_or_default();

        let impact = item
            .get("health_impact")
            .unwrap_or(&serde_json::Value::Null);
        let decrement = finite(impact.get("utility_decrement"));
        if !exact(
            impact,
            &[
                "utility_decrement",
                "decrement_scale",
                "duration_days",
                "qaly_loss_per_occurrence",
                "instrument_or_method",
                "respondent",
                "source_population",
                "basis_ids",
            ],
        ) || decrement.is_none_or(|value| value <= 0.0 || value > 2.0)
            || impact
                .get("decrement_scale")
                .and_then(serde_json::Value::as_str)
                != Some("absolute_utility_decrement")
            || !["instrument_or_method", "respondent", "source_population"]
                .iter()
                .all(|field| nonempty(impact.get(*field)))
            || !linked(impact.get("basis_ids"), &valid_ids)
        {
            audit
                .errors
                .push(format!("event item {item_id} health impact is invalid"));
        }

        let occurrence = item.get("occurrence").unwrap_or(&serde_json::Value::Null);
        let schedule = numbers(occurrence.get("schedule"));
        let expected_measure = match mode {
            "one_time" => "probability",
            "recurrent" => "expected_events",
            "continuous_exposure" => "exposure_fraction",
            _ => "",
        };
        if !exact(
            occurrence,
            &[
                "measure",
                "schedule",
                "source_population",
                "observation_window",
                "basis_ids",
            ],
        ) || occurrence
            .get("measure")
            .and_then(serde_json::Value::as_str)
            != Some(expected_measure)
            || schedule.as_ref().is_none_or(|values| {
                values.len() != cycles
                    || values.iter().any(|value| *value < 0.0)
                    || !values.iter().any(|value| *value > 0.0)
            })
            || !["source_population", "observation_window"]
                .iter()
                .all(|field| nonempty(occurrence.get(*field)))
            || !linked(occurrence.get("basis_ids"), &valid_ids)
        {
            audit
                .errors
                .push(format!("event item {item_id} occurrence is invalid"));
        }
        let schedule = schedule.unwrap_or_default();
        if mode == "one_time"
            && (schedule.iter().filter(|value| **value > 0.0).count() != 1
                || schedule.iter().any(|value| *value > 1.0))
        {
            audit.errors.push(format!(
                "event item {item_id} one-time probability must occur in exactly one cycle and not exceed 1"
            ));
        }
        if mode == "continuous_exposure" && schedule.iter().any(|value| *value > 1.0) {
            audit.errors.push(format!(
                "event item {item_id} exposure fractions must not exceed 1"
            ));
        }

        let decrement = decrement.unwrap_or_default();
        let expected_losses = if mode == "continuous_exposure" {
            if impact
                .get("duration_days")
                .is_none_or(|value| !value.is_null())
                || impact
                    .get("qaly_loss_per_occurrence")
                    .is_none_or(|value| !value.is_null())
            {
                audit.errors.push(format!(
                    "event item {item_id} continuous exposure must not declare per-occurrence duration or loss"
                ));
            }
            schedule
                .iter()
                .map(|fraction| fraction * decrement * cycle_length)
                .collect::<Vec<_>>()
        } else {
            let duration = finite(impact.get("duration_days"));
            let declared_qaly = finite(impact.get("qaly_loss_per_occurrence"));
            if duration.is_none_or(|value| value <= 0.0 || value > cycle_days + TOLERANCE)
                || declared_qaly.is_none_or(|value| value <= 0.0)
            {
                audit.errors.push(format!(
                    "event item {item_id} duration or per-occurrence QALY loss is invalid"
                ));
            }
            if let (Some(duration), Some(declared_qaly)) = (duration, declared_qaly) {
                let expected_qaly = decrement * duration / days_per_year;
                if !close(expected_qaly, declared_qaly) {
                    audit.errors.push(format!(
                        "event item {item_id} per-occurrence QALY arithmetic drifted"
                    ));
                }
                schedule
                    .iter()
                    .map(|number| number * declared_qaly)
                    .collect::<Vec<_>>()
            } else {
                Vec::new()
            }
        };
        let declared_losses = numbers(item.get("cycle_qaly_loss_per_eligible_person"));
        if declared_losses
            .as_ref()
            .is_none_or(|values| values.len() != cycles || values.iter().any(|value| *value < 0.0))
        {
            audit.errors.push(format!(
                "event item {item_id} cycle losses do not match model dimensions"
            ));
        }
        let declared_losses = declared_losses.unwrap_or_default();
        if expected_losses.len() == declared_losses.len()
            && expected_losses
                .iter()
                .zip(&declared_losses)
                .any(|(expected, actual)| !close(*expected, *actual))
        {
            audit.errors.push(format!(
                "event item {item_id} cycle QALY-loss arithmetic drifted"
            ));
        }

        let overlap = item
            .get("utility_overlap")
            .unwrap_or(&serde_json::Value::Null);
        let reviewed = strings(overlap.get("reviewed_utility_item_ids"), false);
        let mut expected_utility_ids = HashSet::new();
        let mut overlap_valid = true;
        for state in &eligible_states {
            let Some((utility_item_id, utility_item)) =
                utility_by_pair.get(&(strategy.to_owned(), state.to_owned()))
            else {
                audit.errors.push(format!(
                    "event item {item_id} has no utility item for eligible state {state}"
                ));
                overlap_valid = false;
                continue;
            };
            expected_utility_ids.insert(utility_item_id.to_owned());
            let application = utility_item
                .get("application")
                .unwrap_or(&serde_json::Value::Null);
            let captured = strings(application.get("captured_effects"), false);
            let excluded = strings(application.get("excluded_effects"), true);
            if captured
                .as_ref()
                .is_none_or(|values| values.iter().any(|value| value == event_id))
                || excluded
                    .as_ref()
                    .is_none_or(|values| !values.iter().any(|value| value == event_id))
            {
                audit.errors.push(format!(
                    "utility item {utility_item_id} must explicitly exclude event {event_id}"
                ));
                overlap_valid = false;
            }
        }
        if !exact(
            overlap,
            &[
                "status",
                "reviewed_utility_item_ids",
                "rationale",
                "basis_ids",
            ],
        ) || overlap.get("status").and_then(serde_json::Value::as_str)
            != Some("excluded_from_health_state_utility")
            || reviewed.as_ref().is_none_or(|reviewed| {
                reviewed.iter().cloned().collect::<HashSet<_>>() != expected_utility_ids
            })
            || !nonempty(overlap.get("rationale"))
            || !linked(overlap.get("basis_ids"), &valid_ids)
        {
            overlap_valid = false;
            audit
                .errors
                .push(format!("event item {item_id} utility overlap is invalid"));
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
                .push(format!("event item {item_id} uncertainty is invalid"));
        }

        if overlap_valid && declared_losses.len() == cycles {
            if let Some(strategy_schedule) = computed.get_mut(strategy) {
                for state in &eligible_states {
                    if let Some(state_index) =
                        states.iter().position(|candidate| candidate == state)
                    {
                        for (cycle, loss) in declared_losses.iter().enumerate() {
                            strategy_schedule[cycle][state_index] += loss;
                        }
                    }
                }
            }
        }
    }

    let declared = value
        .get("cycle_state_qaly_losses")
        .and_then(serde_json::Value::as_object);
    if declared.is_none_or(|declared| declared.len() != order.len()) {
        audit
            .errors
            .push("event QALY-loss strategy dimensions are invalid".into());
    }
    for strategy in &order {
        let rows = declared
            .and_then(|declared| declared.get(strategy))
            .and_then(serde_json::Value::as_array);
        if rows.is_none_or(|rows| rows.len() != cycles) {
            audit.errors.push(format!(
                "event QALY-loss schedule for {strategy} has invalid cycles"
            ));
            continue;
        }
        let mut normalized = Vec::with_capacity(cycles);
        for (cycle, row) in rows.into_iter().flatten().enumerate() {
            let values = numbers(Some(row));
            if values.as_ref().is_none_or(|values| {
                values.len() != states.len() || values.iter().any(|value| *value < 0.0)
            }) {
                audit.errors.push(format!(
                    "event QALY-loss schedule for {strategy} cycle {cycle} is invalid"
                ));
                normalized.push(Vec::new());
                continue;
            }
            let values = values.unwrap_or_default();
            for (state_index, actual) in values.iter().enumerate() {
                let expected = computed
                    .get(strategy)
                    .and_then(|rows| rows.get(cycle))
                    .and_then(|row| row.get(state_index))
                    .copied();
                if expected.is_none_or(|expected| !close(expected, *actual)) {
                    audit.errors.push(format!(
                        "event QALY-loss schedule for {strategy} cycle {cycle} state {state_index} drifted"
                    ));
                }
                let base_utility = base_utilities
                    .get(strategy)
                    .and_then(|rows| rows.get(cycle))
                    .and_then(|row| row.get(state_index))
                    .copied();
                if base_utility.is_none_or(|base| base - actual / cycle_length < -1.0 - TOLERANCE) {
                    audit.errors.push(format!(
                        "event losses imply utility below -1 for {strategy} cycle {cycle} state {}",
                        states
                            .get(state_index)
                            .map(String::as_str)
                            .unwrap_or("unknown")
                    ));
                }
                if states.get(state_index).is_some_and(|state| state == "dead")
                    && !close(*actual, 0.0)
                {
                    audit
                        .errors
                        .push("dead-state event QALY loss must be zero".into());
                }
            }
            normalized.push(values);
        }
        audit
            .cycle_state_qaly_losses
            .insert(strategy.clone(), normalized);
    }
    if strings(value.get("limitations"), false).is_none() {
        audit
            .errors
            .push("event-disutility limitations are required".into());
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
            .push("event disutilities contain a forbidden authority field".into());
    }
    audit.complete = audit.errors.is_empty();
    audit
}

#[cfg(test)]
mod tests {
    use super::*;

    fn event_item(
        item_id: &str,
        event_id: &str,
        mode: &str,
        decrement: f64,
        duration: Option<f64>,
        per_occurrence: Option<f64>,
        measure: &str,
        schedule: serde_json::Value,
        losses: serde_json::Value,
    ) -> serde_json::Value {
        serde_json::json!({
            "item_id": item_id, "event_id": event_id, "strategy_id": "comparator", "label": event_id,
            "event": {"category": "adverse_event", "terminology_system": "Test", "terminology_code": event_id,
                "severity": {"system": "Test", "grade": "reviewed", "rationale": "Explicit severity."}},
            "application": {"mode": mode, "eligible_states": ["alive"], "timing": "cycle_average",
                "cost_handling": "not_in_this_artifact", "rationale": "Declared at-risk state.", "basis_ids": ["method"]},
            "health_impact": {"utility_decrement": decrement, "decrement_scale": "absolute_utility_decrement",
                "duration_days": duration, "qaly_loss_per_occurrence": per_occurrence,
                "instrument_or_method": "Reviewed decrement", "respondent": "patient",
                "source_population": "Trial", "basis_ids": ["impact"]},
            "occurrence": {"measure": measure, "schedule": schedule, "source_population": "Trial",
                "observation_window": "Cycle aligned", "basis_ids": ["frequency"]},
            "utility_overlap": {"status": "excluded_from_health_state_utility",
                "reviewed_utility_item_ids": ["comparator-alive"], "rationale": "Explicit exclusion.", "basis_ids": ["overlap"]},
            "cycle_qaly_loss_per_eligible_person": losses,
            "uncertainty": {"status": "fixed", "basis_ids": ["impact"], "limitations": ["Not executed."]}
        })
    }

    fn fixture(
        tag: &str,
    ) -> (
        std::path::PathBuf,
        serde_json::Value,
        Vec<u8>,
        serde_json::Value,
        Vec<u8>,
        serde_json::Value,
        serde_json::Value,
    ) {
        let root = std::env::temp_dir().join(format!(
            "ai4heor-event-disutility-{tag}-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("heor")).unwrap();
        let plan = serde_json::json!({
            "schema_version": "0.15.0", "analysis_id": "event-native-test",
            "cycle_length_years": 0.5, "cycles": 2, "states": ["alive", "dead"],
            "strategy_order": ["comparator"], "evidence_sources": [{"id": "method"}, {"id": "impact"}, {"id": "frequency"}],
            "assumptions": [{"id": "overlap", "status": "proposed"}], "input_provenance": []
        });
        let plan_raw = serde_json::to_vec(&plan).unwrap();
        let utility = serde_json::json!({
            "items": {
                "comparator-alive": {"strategy_id": "comparator", "state_id": "alive",
                    "application": {"captured_effects": ["health_state"], "excluded_effects": ["acute-event", "recurrent-event", "continuous-event"]}},
                "comparator-dead": {"strategy_id": "comparator", "state_id": "dead",
                    "application": {"captured_effects": ["death"], "excluded_effects": []}}
            },
            "cycle_state_utilities": {"comparator": [[0.8, 0.0], [0.8, 0.0]]}
        });
        let utility_raw = serde_json::to_vec(&utility).unwrap();
        let days = 365.25;
        let acute = 0.2 * 7.0 / days;
        let recurrent = 0.05 * 14.0 / days;
        let mut items = serde_json::Map::new();
        items.insert(
            "acute-item".into(),
            event_item(
                "acute-item",
                "acute-event",
                "one_time",
                0.2,
                Some(7.0),
                Some(acute),
                "probability",
                serde_json::json!([0.2, 0.0]),
                serde_json::json!([0.2 * acute, 0.0]),
            ),
        );
        items.insert(
            "recurrent-item".into(),
            event_item(
                "recurrent-item",
                "recurrent-event",
                "recurrent",
                0.05,
                Some(14.0),
                Some(recurrent),
                "expected_events",
                serde_json::json!([0.5, 0.25]),
                serde_json::json!([0.5 * recurrent, 0.25 * recurrent]),
            ),
        );
        items.insert(
            "continuous-item".into(),
            event_item(
                "continuous-item",
                "continuous-event",
                "continuous_exposure",
                0.02,
                None,
                None,
                "exposure_fraction",
                serde_json::json!([1.0, 0.5]),
                serde_json::json!([0.01, 0.005]),
            ),
        );
        let artifact = serde_json::json!({
            "schema_version": "0.1.0", "event_disutility_id": "event-inputs",
            "analysis_id": "event-native-test", "status": "ready_for_human_review",
            "base_analysis": {"path": ANALYSIS_PATH, "content_sha256": sha256(&plan_raw)},
            "base_utility_inputs": {"path": UTILITY_INPUTS_PATH, "content_sha256": sha256(&utility_raw)},
            "day_count_convention": {"days_per_year": days, "rationale": "Reviewed convention.", "basis_ids": ["method"]},
            "combination_rule": {"method": "additive_expected_qaly_loss", "rationale": "Add excluded losses.", "basis_ids": ["method"]},
            "item_order": ["acute-item", "recurrent-item", "continuous-item"], "items": items,
            "cycle_state_qaly_losses": {"comparator": [
                [0.2 * acute + 0.5 * recurrent + 0.01, 0.0],
                [0.25 * recurrent + 0.005, 0.0]
            ]},
            "limitations": ["Interactions and component uncertainty are not executed."]
        });
        let raw = serde_json::to_vec(&artifact).unwrap();
        let psm = serde_json::json!({
            "event_disutilities": {"path": EVENT_DISUTILITIES_PATH, "content_sha256": sha256(&raw)}
        });
        std::fs::write(root.join(EVENT_DISUTILITIES_PATH), raw).unwrap();
        (root, plan, plan_raw, utility, utility_raw, psm, artifact)
    }

    fn write_artifact(root: &Path, psm: &mut serde_json::Value, artifact: &serde_json::Value) {
        let raw = serde_json::to_vec(artifact).unwrap();
        psm["event_disutilities"]["content_sha256"] = serde_json::json!(sha256(&raw));
        std::fs::write(root.join(EVENT_DISUTILITIES_PATH), raw).unwrap();
    }

    #[test]
    fn audits_all_three_modes_and_rejects_arithmetic_drift() {
        let (root, plan, plan_raw, utility, utility_raw, mut psm, mut artifact) =
            fixture("arithmetic");
        let valid = audit_event_disutilities(&root, &plan, &plan_raw, &psm, &utility, &utility_raw);
        assert!(valid.complete, "{:?}", valid.errors);
        assert_eq!(valid.item_count, 3);
        assert_eq!(valid.one_time_item_count, 1);
        assert_eq!(valid.recurrent_item_count, 1);
        assert_eq!(valid.continuous_exposure_item_count, 1);

        artifact["items"]["acute-item"]["cycle_qaly_loss_per_eligible_person"][0] =
            serde_json::json!(0.2);
        write_artifact(&root, &mut psm, &artifact);
        let drift = audit_event_disutilities(&root, &plan, &plan_raw, &psm, &utility, &utility_raw);
        assert!(!drift.complete);
        assert!(drift
            .errors
            .iter()
            .any(|error| error.contains("cycle QALY-loss arithmetic drifted")));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn rejects_overlap_hash_and_implied_utility_drift() {
        let (root, plan, plan_raw, mut utility, utility_raw, mut psm, mut artifact) =
            fixture("cross-artifact");
        utility["items"]["comparator-alive"]["application"]["excluded_effects"] =
            serde_json::json!(["recurrent-event", "continuous-event"]);
        let overlap =
            audit_event_disutilities(&root, &plan, &plan_raw, &psm, &utility, &utility_raw);
        assert!(!overlap.complete);
        assert!(overlap
            .errors
            .iter()
            .any(|error| error.contains("must explicitly exclude event acute-event")));

        artifact["cycle_state_qaly_losses"]["comparator"][0][0] = serde_json::json!(1.0);
        write_artifact(&root, &mut psm, &artifact);
        psm["event_disutilities"]["content_sha256"] = serde_json::json!("0".repeat(64));
        let drift = audit_event_disutilities(&root, &plan, &plan_raw, &psm, &utility, &utility_raw);
        assert!(!drift.complete);
        assert!(drift
            .errors
            .iter()
            .any(|error| error.contains("hash does not match")));
        assert!(drift
            .errors
            .iter()
            .any(|error| error.contains("imply utility below -1")));
        let _ = std::fs::remove_dir_all(root);
    }
}
