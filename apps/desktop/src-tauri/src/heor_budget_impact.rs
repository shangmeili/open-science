//! App-owned audit and execution boundary for HEOR budget impact analysis.
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::path::Path;
use tauri::{path::BaseDirectory, AppHandle, Manager};

pub const BUDGET_IMPACT_PLAN_PATH: &str = "heor/budget-impact-plan.json";
const ANALYSIS_PLAN_PATH: &str = "heor/analysis-plan.json";
const HORIZON: usize = 3;
const MAX_COST_CATEGORIES: usize = 64;
const MAX_NON_PATIENT_COSTS: usize = 32;
const MAX_SENSITIVITY_PARAMETERS: usize = 128;
const MAX_SCENARIOS: usize = 32;
const OUTPUT_CAP_BYTES: usize = 10 * 1024 * 1024;

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BudgetImpactAudit {
    pub complete: bool,
    pub status: &'static str,
    pub bia_id: String,
    pub analysis_id: String,
    pub analysis_plan_sha256: String,
    pub budget_impact_sha256: String,
    pub horizon_years: Option<u64>,
    pub population_year_count: usize,
    pub cost_category_count: usize,
    pub non_patient_cost_count: usize,
    pub sensitivity_parameter_count: usize,
    pub scenario_count: usize,
    pub required_input_count: usize,
    pub covered_input_count: usize,
    pub invalid_inputs: Vec<String>,
    pub errors: Vec<String>,
}

#[derive(Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BudgetImpactRunResult {
    workflow: crate::heor_engine::HeorWorkflowStatus,
    calculation: serde_json::Value,
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn nonempty(value: Option<&serde_json::Value>) -> bool {
    value
        .and_then(serde_json::Value::as_str)
        .is_some_and(|value| !value.trim().is_empty())
}

fn safe_strategy_id(value: &str) -> bool {
    let mut bytes = value.bytes();
    bytes.next().is_some_and(|byte| byte.is_ascii_lowercase())
        && value.len() <= 64
        && bytes.all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'_' | b'-')
        })
}

fn finite(value: Option<&serde_json::Value>) -> Option<f64> {
    value
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite())
}

fn valid_sha256(value: Option<&serde_json::Value>) -> bool {
    value
        .and_then(serde_json::Value::as_str)
        .is_some_and(|value| {
            value.len() == 64
                && value
                    .bytes()
                    .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        })
}

fn string_set(value: Option<&serde_json::Value>) -> Option<HashSet<&str>> {
    let values = value?.as_array()?;
    let mut result = HashSet::new();
    for item in values {
        let item = item.as_str()?;
        if item.trim().is_empty() || !result.insert(item) {
            return None;
        }
    }
    Some(result)
}

fn annual_numbers(value: Option<&serde_json::Value>, shares: bool) -> Option<Vec<f64>> {
    let values = value?.as_array()?;
    if values.len() != HORIZON {
        return None;
    }
    let numbers = values
        .iter()
        .map(|item| finite(Some(item)))
        .collect::<Option<Vec<_>>>()?;
    if numbers
        .iter()
        .any(|value| *value < 0.0 || (shares && *value > 1.0))
    {
        return None;
    }
    Some(numbers)
}

fn target_allowed(target: &str) -> bool {
    let parts = target.split('/').collect::<Vec<_>>();
    matches!(
        parts.as_slice(),
        ["", "population", "annual_eligible", year]
            if year.parse::<usize>().is_ok_and(|year| year < HORIZON)
    ) || matches!(
        parts.as_slice(),
        ["", "market_scenarios", "with_new_intervention", "intervention_share_by_year", year]
            if year.parse::<usize>().is_ok_and(|year| year < HORIZON)
    ) || matches!(
        parts.as_slice(),
        ["", "cost_categories", category, "annual_per_patient", "comparator" | "intervention", year]
            if category.parse::<usize>().is_ok()
                && year.parse::<usize>().is_ok_and(|year| year < HORIZON)
    ) || matches!(
        parts.as_slice(),
        ["", "non_patient_costs", item, "annual_total", "without_new_intervention" | "with_new_intervention", year]
            if item.parse::<usize>().is_ok()
                && year.parse::<usize>().is_ok_and(|year| year < HORIZON)
    )
}

fn pointer_value<'a>(value: &'a serde_json::Value, pointer: &str) -> Option<&'a serde_json::Value> {
    target_allowed(pointer)
        .then(|| value.pointer(pointer))
        .flatten()
}

fn target_number_valid(target: &str, value: f64) -> bool {
    value.is_finite()
        && value >= 0.0
        && (!target.contains("intervention_share_by_year") || value <= 1.0)
}

fn required_paths(value: &serde_json::Value) -> HashSet<String> {
    let mut paths = HashSet::new();
    for year in 0..HORIZON {
        paths.insert(format!("/population/annual_eligible/{year}"));
        paths.insert(format!(
            "/market_scenarios/with_new_intervention/intervention_share_by_year/{year}"
        ));
    }
    for category in 0..value
        .get("cost_categories")
        .and_then(serde_json::Value::as_array)
        .map_or(0, Vec::len)
    {
        for role in ["comparator", "intervention"] {
            for year in 0..HORIZON {
                paths.insert(format!(
                    "/cost_categories/{category}/annual_per_patient/{role}/{year}"
                ));
            }
        }
    }
    for item in 0..value
        .get("non_patient_costs")
        .and_then(serde_json::Value::as_array)
        .map_or(0, Vec::len)
    {
        for scenario in ["without_new_intervention", "with_new_intervention"] {
            for year in 0..HORIZON {
                paths.insert(format!(
                    "/non_patient_costs/{item}/annual_total/{scenario}/{year}"
                ));
            }
        }
    }
    paths
}

fn empty_audit(plan_raw: &[u8]) -> BudgetImpactAudit {
    BudgetImpactAudit {
        complete: false,
        status: "incomplete",
        bia_id: String::new(),
        analysis_id: String::new(),
        analysis_plan_sha256: sha256(plan_raw),
        budget_impact_sha256: String::new(),
        horizon_years: None,
        population_year_count: 0,
        cost_category_count: 0,
        non_patient_cost_count: 0,
        sensitivity_parameter_count: 0,
        scenario_count: 0,
        required_input_count: 0,
        covered_input_count: 0,
        invalid_inputs: Vec::new(),
        errors: Vec::new(),
    }
}

fn audit_values(
    workspace: &Path,
    plan: &serde_json::Value,
    plan_raw: &[u8],
    budget: &serde_json::Value,
    budget_raw: &[u8],
) -> BudgetImpactAudit {
    let mut audit = empty_audit(plan_raw);
    audit.budget_impact_sha256 = sha256(budget_raw);
    audit.bia_id = budget
        .get("bia_id")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default()
        .to_string();
    audit.analysis_id = budget
        .get("analysis_id")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default()
        .to_string();
    audit.horizon_years = budget
        .get("horizon_years")
        .and_then(serde_json::Value::as_u64);

    if budget
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some("0.1.0")
    {
        audit
            .errors
            .push("budget impact schema_version must be 0.1.0".into());
    }
    for field in ["bia_id", "analysis_id"] {
        if !nonempty(budget.get(field)) {
            audit
                .errors
                .push(format!("budget impact {field} is required"));
        }
    }
    if budget.get("status").and_then(serde_json::Value::as_str) != Some("ready_for_human_review") {
        audit
            .errors
            .push("budget impact plan must be ready_for_human_review".into());
    }
    if budget.get("analysis_id") != plan.get("analysis_id") {
        audit
            .errors
            .push("budget impact analysis_id does not match the analysis plan".into());
    }
    if budget
        .pointer("/base_analysis/path")
        .and_then(serde_json::Value::as_str)
        != Some(ANALYSIS_PLAN_PATH)
        || budget
            .pointer("/base_analysis/content_sha256")
            .and_then(serde_json::Value::as_str)
            != Some(audit.analysis_plan_sha256.as_str())
    {
        audit.errors.push(
            "budget impact base_analysis does not match the current analysis-plan bytes".into(),
        );
    }
    if plan
        .pointer("/budget_impact_analysis/path")
        .and_then(serde_json::Value::as_str)
        != Some(BUDGET_IMPACT_PLAN_PATH)
    {
        audit
            .errors
            .push("analysis plan must link heor/budget-impact-plan.json".into());
    }

    let perspective = budget.get("perspective");
    if perspective
        .and_then(|value| value.get("type"))
        .and_then(serde_json::Value::as_str)
        != Some("budget_holder")
    {
        audit
            .errors
            .push("BIA perspective must be budget_holder".into());
    }
    for field in [
        "budget_holder",
        "jurisdiction",
        "currency",
        "alignment_rationale",
    ] {
        if !nonempty(perspective.and_then(|value| value.get(field))) {
            audit
                .errors
                .push(format!("BIA perspective.{field} is required"));
        }
    }
    let price_year = perspective
        .and_then(|value| value.get("price_year"))
        .and_then(serde_json::Value::as_i64);
    if !price_year.is_some_and(|year| (1900..=2100).contains(&year)) {
        audit
            .errors
            .push("BIA perspective.price_year must be from 1900 to 2100".into());
    }
    let jurisdiction = perspective
        .and_then(|value| value.get("jurisdiction"))
        .and_then(serde_json::Value::as_str);
    let plan_jurisdiction = plan
        .pointer("/decision_problem/jurisdiction")
        .and_then(serde_json::Value::as_str);
    if plan_jurisdiction.is_some() && jurisdiction != plan_jurisdiction {
        audit
            .errors
            .push("BIA jurisdiction does not match the analysis plan".into());
    }
    if audit.horizon_years != Some(HORIZON as u64) {
        audit
            .errors
            .push("BIA horizon must be exactly 3 years".into());
    }
    if finite(budget.get("discount_rate")) != Some(0.0) {
        audit.errors.push("BIA discount_rate must be 0".into());
    }

    if !nonempty(budget.pointer("/population/label"))
        || !nonempty(budget.pointer("/population/derivation"))
    {
        audit
            .errors
            .push("BIA population requires label and derivation".into());
    }
    audit.population_year_count = budget
        .pointer("/population/annual_eligible")
        .and_then(serde_json::Value::as_array)
        .map_or(0, Vec::len);
    if annual_numbers(budget.pointer("/population/annual_eligible"), false).is_none() {
        audit
            .errors
            .push("BIA annual eligible population must contain three non-negative values".into());
    }

    let multi_strategy_ids = if plan
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        == Some("0.8.0")
    {
        string_set(plan.get("strategy_order")).filter(|ids| {
            ids.len() >= 2 && ids.iter().all(|strategy_id| safe_strategy_id(strategy_id))
        })
    } else {
        None
    };
    let plan_strategies = plan
        .get("strategies")
        .and_then(serde_json::Value::as_object);
    for role in ["comparator", "intervention"] {
        if !nonempty(budget.pointer(&format!("/strategies/{role}/id")))
            || !nonempty(budget.pointer(&format!("/strategies/{role}/label")))
        {
            audit
                .errors
                .push(format!("BIA strategies.{role} is incomplete"));
        }
        let budget_id = budget
            .pointer(&format!("/strategies/{role}/id"))
            .and_then(serde_json::Value::as_str);
        let matches_plan = if multi_strategy_ids.is_some() {
            budget_id.is_some_and(|strategy_id| {
                safe_strategy_id(strategy_id)
                    && multi_strategy_ids
                        .as_ref()
                        .is_some_and(|ids| ids.contains(strategy_id))
                    && plan_strategies
                        .is_some_and(|strategies| strategies.contains_key(strategy_id))
            })
        } else if plan
            .get("schema_version")
            .and_then(serde_json::Value::as_str)
            == Some("0.8.0")
        {
            false
        } else {
            budget.pointer(&format!("/strategies/{role}/id"))
                == plan.pointer(&format!("/strategies/{role}/name"))
        };
        if !matches_plan {
            audit.errors.push(format!(
                "BIA strategies.{role}.id does not match the analysis plan"
            ));
        }
    }
    if budget.pointer("/strategies/comparator/id") == budget.pointer("/strategies/intervention/id")
    {
        audit
            .errors
            .push("BIA strategy ids must be different".into());
    }

    for scenario in ["without_new_intervention", "with_new_intervention"] {
        if !nonempty(budget.pointer(&format!("/market_scenarios/{scenario}/label"))) {
            audit
                .errors
                .push(format!("BIA market scenario {scenario} needs a label"));
        }
        if annual_numbers(
            budget.pointer(&format!(
                "/market_scenarios/{scenario}/intervention_share_by_year"
            )),
            true,
        )
        .is_none()
        {
            audit
                .errors
                .push(format!("BIA {scenario} shares are invalid"));
        }
    }
    if annual_numbers(
        budget.pointer("/market_scenarios/without_new_intervention/intervention_share_by_year"),
        true,
    )
    .is_some_and(|values| values.iter().any(|value| value.abs() > 1e-9))
    {
        audit
            .errors
            .push("without-new-intervention shares must be zero".into());
    }

    let categories = budget
        .get("cost_categories")
        .and_then(serde_json::Value::as_array);
    audit.cost_category_count = categories.map_or(0, Vec::len);
    if !(2..=MAX_COST_CATEGORIES).contains(&audit.cost_category_count) {
        audit.errors.push(format!(
            "BIA cost_categories must contain 2 to {MAX_COST_CATEGORIES} entries"
        ));
    }
    let mut category_ids = HashSet::new();
    let mut category_types = HashSet::new();
    for (index, category) in categories.into_iter().flatten().enumerate() {
        let id = category.get("id").and_then(serde_json::Value::as_str);
        if !id.is_some_and(|id| !id.trim().is_empty() && category_ids.insert(id)) {
            audit
                .errors
                .push(format!("BIA cost category {index} id is invalid"));
        }
        for field in ["label", "rationale"] {
            if !nonempty(category.get(field)) {
                audit
                    .errors
                    .push(format!("BIA cost category {index} {field} is required"));
            }
        }
        let category_type = category.get("type").and_then(serde_json::Value::as_str);
        if !matches!(category_type, Some("intervention" | "condition_related")) {
            audit
                .errors
                .push(format!("BIA cost category {index} type is invalid"));
        } else {
            category_types.insert(category_type.unwrap());
        }
        if category
            .get("included")
            .and_then(serde_json::Value::as_bool)
            != Some(true)
        {
            audit
                .errors
                .push(format!("BIA cost category {index} must be included"));
        }
        for role in ["comparator", "intervention"] {
            if annual_numbers(
                category.pointer(&format!("/annual_per_patient/{role}")),
                false,
            )
            .is_none()
            {
                audit.errors.push(format!(
                    "BIA cost category {index} {role} annual values are invalid"
                ));
            }
        }
    }
    if category_types != HashSet::from(["intervention", "condition_related"]) {
        audit
            .errors
            .push("BIA must include intervention and condition-related cost categories".into());
    }

    let exclusions = budget
        .get("excluded_cost_categories")
        .and_then(serde_json::Value::as_array);
    if exclusions.is_none() {
        audit
            .errors
            .push("excluded_cost_categories must be an array".into());
    }
    for (index, exclusion) in exclusions.into_iter().flatten().enumerate() {
        if !nonempty(exclusion.get("category")) || !nonempty(exclusion.get("rationale")) {
            audit
                .errors
                .push(format!("BIA excluded cost category {index} is incomplete"));
        }
    }

    let non_patient = budget
        .get("non_patient_costs")
        .and_then(serde_json::Value::as_array);
    audit.non_patient_cost_count = non_patient.map_or(0, Vec::len);
    if non_patient.is_none() || audit.non_patient_cost_count > MAX_NON_PATIENT_COSTS {
        audit.errors.push(format!(
            "BIA non_patient_costs must contain at most {MAX_NON_PATIENT_COSTS} entries"
        ));
    }
    let mut non_patient_ids = HashSet::new();
    for (index, item) in non_patient.into_iter().flatten().enumerate() {
        let id = item.get("id").and_then(serde_json::Value::as_str);
        if !id.is_some_and(|id| !id.trim().is_empty() && non_patient_ids.insert(id)) {
            audit
                .errors
                .push(format!("BIA non-patient cost {index} id is invalid"));
        }
        if !nonempty(item.get("label")) || !nonempty(item.get("rationale")) {
            audit
                .errors
                .push(format!("BIA non-patient cost {index} is incomplete"));
        }
        if item.get("type").and_then(serde_json::Value::as_str) != Some("implementation")
            || item.get("included").and_then(serde_json::Value::as_bool) != Some(true)
        {
            audit.errors.push(format!(
                "BIA non-patient cost {index} must be an included implementation cost"
            ));
        }
        for scenario in ["without_new_intervention", "with_new_intervention"] {
            if annual_numbers(item.pointer(&format!("/annual_total/{scenario}")), false).is_none() {
                audit.errors.push(format!(
                    "BIA non-patient cost {index} {scenario} annual totals are invalid"
                ));
            }
        }
    }

    let mut source_ids = HashSet::new();
    let sources = budget
        .get("evidence_sources")
        .and_then(serde_json::Value::as_array);
    if sources.is_none() {
        audit
            .errors
            .push("BIA evidence_sources must be an array".into());
    }
    for (index, source) in sources.into_iter().flatten().enumerate() {
        let id = source.get("id").and_then(serde_json::Value::as_str);
        if !id.is_some_and(|id| !id.trim().is_empty() && source_ids.insert(id)) {
            audit
                .errors
                .push(format!("BIA evidence source {index} id is invalid"));
        }
        for field in ["title", "source_type", "accessed_on"] {
            if !nonempty(source.get(field)) {
                audit
                    .errors
                    .push(format!("BIA evidence source {index} {field} is required"));
            }
        }
        let has_url = nonempty(source.get("url"));
        let local_path = source.get("local_path").and_then(serde_json::Value::as_str);
        if !has_url && local_path.is_none() {
            audit
                .errors
                .push(format!("BIA evidence source {index} needs a locator"));
        }
        if let Some(local_path) = local_path {
            if !valid_sha256(source.get("content_sha256")) {
                audit
                    .errors
                    .push(format!("BIA evidence source {index} hash is invalid"));
            } else {
                match crate::heor_uncertainty::read_workspace_capped(workspace, local_path) {
                    Ok(raw)
                        if source
                            .get("content_sha256")
                            .and_then(serde_json::Value::as_str)
                            == Some(sha256(&raw).as_str()) => {}
                    Ok(_) => audit
                        .errors
                        .push(format!("BIA evidence source {index} hash does not match")),
                    Err(error) => audit.errors.push(error),
                }
            }
        }
    }

    let assumptions = budget
        .get("assumptions")
        .and_then(serde_json::Value::as_array);
    if assumptions.is_none() {
        audit.errors.push("BIA assumptions must be an array".into());
    }
    let mut assumption_status = HashMap::new();
    for (index, assumption) in assumptions.into_iter().flatten().enumerate() {
        let id = assumption.get("id").and_then(serde_json::Value::as_str);
        if !id.is_some_and(|id| !id.trim().is_empty() && !assumption_status.contains_key(id)) {
            audit
                .errors
                .push(format!("BIA assumption {index} id is invalid"));
        }
        for field in ["statement", "reason"] {
            if !nonempty(assumption.get(field)) {
                audit
                    .errors
                    .push(format!("BIA assumption {index} {field} is required"));
            }
        }
        let status = assumption.get("status").and_then(serde_json::Value::as_str);
        if !matches!(status, Some("unresolved" | "proposed" | "rejected")) {
            audit
                .errors
                .push(format!("BIA assumption {index} status is invalid"));
        } else if status == Some("unresolved") {
            audit
                .errors
                .push(format!("BIA assumption {index} remains unresolved"));
        }
        if let (Some(id), Some(status)) = (id, status) {
            assumption_status.insert(id, status);
        }
    }

    let required = required_paths(budget);
    audit.required_input_count = required.len();
    let mut covered: HashSet<String> = HashSet::new();
    let mappings = budget
        .get("input_provenance")
        .and_then(serde_json::Value::as_array);
    if mappings.is_none() {
        audit
            .errors
            .push("BIA input_provenance must be an array".into());
    }
    for (index, mapping) in mappings.into_iter().flatten().enumerate() {
        let path = mapping.get("path").and_then(serde_json::Value::as_str);
        let mut reasons = Vec::new();
        if !path.is_some_and(|path| required.contains(path)) {
            reasons.push("path is not a required BIA input");
        }
        if path.is_some_and(|path| covered.contains(path)) {
            reasons.push("path is duplicated");
        }
        for field in ["unit", "jurisdiction", "selection_rationale"] {
            if !nonempty(mapping.get(field)) {
                reasons.push("metadata is incomplete");
                break;
            }
        }
        if mapping
            .get("jurisdiction")
            .and_then(serde_json::Value::as_str)
            != jurisdiction
        {
            reasons.push("jurisdiction does not match");
        }
        if !matches!(
            mapping
                .get("uncertainty_status")
                .and_then(serde_json::Value::as_str),
            Some("fixed" | "range_available" | "distribution_available")
        ) {
            reasons.push("uncertainty status is invalid");
        }
        if path.is_some_and(|path| {
            path.starts_with("/cost_categories/") || path.starts_with("/non_patient_costs/")
        }) && !mapping
            .get("price_year")
            .and_then(serde_json::Value::as_i64)
            .is_some_and(|year| (1900..=2100).contains(&year))
        {
            reasons.push("price year is invalid");
        }
        let linked_sources = string_set(mapping.get("source_ids")).unwrap_or_default();
        let linked_assumptions = string_set(mapping.get("assumption_ids")).unwrap_or_default();
        if linked_sources.is_empty() && linked_assumptions.is_empty() {
            reasons.push("no evidence or proposed assumption is linked");
        }
        if linked_sources.iter().any(|id| !source_ids.contains(id)) {
            reasons.push("source link is invalid");
        }
        if linked_assumptions
            .iter()
            .any(|id| assumption_status.get(id) != Some(&"proposed"))
        {
            reasons.push("assumption link is not proposed");
        }
        if reasons.is_empty() {
            covered.insert(path.unwrap().to_string());
        } else {
            audit
                .invalid_inputs
                .push(format!("input_provenance[{index}]: {}", reasons.join("; ")));
        }
    }
    audit.covered_input_count = covered.len();
    for missing in required.difference(&covered).take(5) {
        audit
            .invalid_inputs
            .push(format!("missing provenance: {missing}"));
    }

    let allowed_basis = source_ids
        .iter()
        .copied()
        .chain(
            assumption_status
                .iter()
                .filter_map(|(id, status)| (*status == "proposed").then_some(*id)),
        )
        .collect::<HashSet<_>>();
    let parameters = budget
        .get("sensitivity_parameters")
        .and_then(serde_json::Value::as_array);
    audit.sensitivity_parameter_count = parameters.map_or(0, Vec::len);
    if !(1..=MAX_SENSITIVITY_PARAMETERS).contains(&audit.sensitivity_parameter_count) {
        audit.errors.push(format!(
            "BIA sensitivity_parameters must contain 1 to {MAX_SENSITIVITY_PARAMETERS} entries"
        ));
    }
    let mut parameter_ids = HashSet::new();
    let mut parameter_targets = HashSet::new();
    for (index, parameter) in parameters.into_iter().flatten().enumerate() {
        let id = parameter.get("id").and_then(serde_json::Value::as_str);
        if !id.is_some_and(|id| !id.trim().is_empty() && parameter_ids.insert(id)) {
            audit
                .errors
                .push(format!("BIA sensitivity parameter {index} id is invalid"));
        }
        if !nonempty(parameter.get("label")) {
            audit.errors.push(format!(
                "BIA sensitivity parameter {index} label is required"
            ));
        }
        let target = parameter.get("target").and_then(serde_json::Value::as_str);
        let base = target
            .and_then(|target| pointer_value(budget, target))
            .and_then(|value| finite(Some(value)));
        if !target.is_some_and(|target| parameter_targets.insert(target)) || base.is_none() {
            audit.errors.push(format!(
                "BIA sensitivity parameter {index} target is invalid"
            ));
            continue;
        }
        let low = finite(parameter.get("low"));
        let high = finite(parameter.get("high"));
        if !matches!((low, base, high), (Some(low), Some(base), Some(high)) if low <= base && base <= high && low != high && target_number_valid(target.unwrap(), low) && target_number_valid(target.unwrap(), high))
        {
            audit.errors.push(format!(
                "BIA sensitivity parameter {index} range is invalid"
            ));
        }
        let basis = string_set(parameter.get("basis_ids"));
        if !basis.is_some_and(|basis| {
            !basis.is_empty() && basis.iter().all(|id| allowed_basis.contains(id))
        }) {
            audit.errors.push(format!(
                "BIA sensitivity parameter {index} basis is invalid"
            ));
        }
    }

    let scenarios = budget
        .get("alternative_scenarios")
        .and_then(serde_json::Value::as_array);
    audit.scenario_count = scenarios.map_or(0, Vec::len);
    if !(1..=MAX_SCENARIOS).contains(&audit.scenario_count) {
        audit.errors.push(format!(
            "BIA alternative_scenarios must contain 1 to {MAX_SCENARIOS} entries"
        ));
    }
    let mut scenario_ids = HashSet::new();
    for (index, scenario) in scenarios.into_iter().flatten().enumerate() {
        let id = scenario
            .get("scenario_id")
            .and_then(serde_json::Value::as_str);
        if !id.is_some_and(|id| !id.trim().is_empty() && scenario_ids.insert(id)) {
            audit
                .errors
                .push(format!("BIA scenario {index} id is invalid"));
        }
        if !nonempty(scenario.get("label")) || !nonempty(scenario.get("rationale")) {
            audit
                .errors
                .push(format!("BIA scenario {index} metadata is incomplete"));
        }
        let basis = string_set(scenario.get("basis_ids"));
        if !basis.is_some_and(|basis| {
            !basis.is_empty() && basis.iter().all(|id| allowed_basis.contains(id))
        }) {
            audit
                .errors
                .push(format!("BIA scenario {index} basis is invalid"));
        }
        let overrides = scenario
            .get("overrides")
            .and_then(serde_json::Value::as_array);
        if overrides.is_none_or(Vec::is_empty) {
            audit
                .errors
                .push(format!("BIA scenario {index} overrides are required"));
        }
        let mut targets = HashSet::new();
        for (override_index, replacement) in overrides.into_iter().flatten().enumerate() {
            let target = replacement
                .get("target")
                .and_then(serde_json::Value::as_str);
            let value = finite(replacement.get("value"));
            if !target.is_some_and(|target| {
                targets.insert(target)
                    && pointer_value(budget, target).is_some()
                    && value.is_some_and(|value| target_number_valid(target, value))
            }) {
                audit.errors.push(format!(
                    "BIA scenario {index} override {override_index} is invalid"
                ));
            }
        }
    }

    for field in ["face", "internal", "external"] {
        if !string_set(budget.pointer(&format!("/validation_plan/{field}")))
            .is_some_and(|values| !values.is_empty())
        {
            audit
                .errors
                .push(format!("BIA validation_plan.{field} is required"));
        }
    }
    if !string_set(budget.get("limitations")).is_some_and(|values| !values.is_empty()) {
        audit
            .errors
            .push("BIA limitations must not be empty".into());
    }

    audit.complete = audit.errors.is_empty()
        && audit.invalid_inputs.is_empty()
        && audit.covered_input_count == audit.required_input_count;
    audit.status = if audit.complete {
        "complete"
    } else {
        "incomplete"
    };
    audit
}

pub fn audit_budget_impact_for_plan(
    workspace: &Path,
    plan_raw: &[u8],
) -> Result<BudgetImpactAudit, String> {
    let plan: serde_json::Value = serde_json::from_slice(plan_raw)
        .map_err(|error| format!("budget impact audit failed: {error}"))?;
    let budget_raw =
        match crate::heor_uncertainty::read_workspace_capped(workspace, BUDGET_IMPACT_PLAN_PATH) {
            Ok(raw) => raw,
            Err(error) => {
                let mut audit = empty_audit(plan_raw);
                audit.errors.push(error);
                return Ok(audit);
            }
        };
    let budget: serde_json::Value = serde_json::from_slice(&budget_raw)
        .map_err(|error| format!("budget impact plan is invalid: {error}"))?;
    Ok(audit_values(
        workspace,
        &plan,
        plan_raw,
        &budget,
        &budget_raw,
    ))
}

pub fn require_budget_impact_plan_approvable(
    workspace: &Path,
    plan_raw: &[u8],
) -> Result<BudgetImpactAudit, String> {
    let audit = audit_budget_impact_for_plan(workspace, plan_raw)?;
    if !audit.complete {
        return Err(format!(
            "budget impact audit is incomplete: {} cost categories, {} sensitivity parameters, {} scenarios, {} invalid inputs, {} errors",
            audit.cost_category_count,
            audit.sensitivity_parameter_count,
            audit.scenario_count,
            audit.invalid_inputs.len(),
            audit.errors.len()
        ));
    }
    Ok(audit)
}

#[tauri::command(async)]
pub fn audit_heor_budget_impact(app: AppHandle) -> Result<BudgetImpactAudit, String> {
    let workspace = crate::runtime::workspace_dir(&app)?;
    let plan_raw = crate::heor_uncertainty::read_workspace_capped(&workspace, ANALYSIS_PLAN_PATH)?;
    audit_budget_impact_for_plan(&workspace, &plan_raw)
}

fn capped_stderr(bytes: &[u8]) -> String {
    String::from_utf8_lossy(&bytes[..bytes.len().min(4_000)])
        .trim()
        .to_string()
}

#[tauri::command(async)]
pub fn run_heor_budget_impact(
    app: AppHandle,
    approval_state: tauri::State<crate::heor_approval::HeorApprovalState>,
    project_id: String,
) -> Result<BudgetImpactRunResult, String> {
    let workspace = crate::runtime::workspace_dir(&app)?;
    if crate::project::require_project_id(&workspace)? != project_id {
        return Err("HEOR projectId does not match the current project".into());
    }
    let plan_path = workspace.join(ANALYSIS_PLAN_PATH);
    let plan_raw = crate::heor_uncertainty::read_workspace_capped(&workspace, ANALYSIS_PLAN_PATH)?;
    let evidence_audit = crate::heor_evidence::audit_plan_bytes(&plan_raw)?;
    let budget_audit = require_budget_impact_plan_approvable(&workspace, &plan_raw)?;
    let budget_path = workspace.join(BUDGET_IMPACT_PLAN_PATH);

    let package_src = app
        .path()
        .resolve("heor-core/src", BaseDirectory::Resource)
        .map_err(|error| format!("bundled HEOR engine unavailable: {error}"))?;
    if !package_src.join("heor_core").is_dir() {
        return Err("bundled HEOR engine source is missing".into());
    }
    let (python, _) = crate::kernel::python_bin(&app)?;
    let output = crate::runtime::quiet_command(python)
        .args(["-m", "heor_core"])
        .arg(&plan_path)
        .arg("--budget-impact-plan")
        .arg(&budget_path)
        .current_dir(&workspace)
        .env("PYTHONPATH", &package_src)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("PYTHONNOUSERSITE", "1")
        .output()
        .map_err(|error| format!("HEOR budget impact engine failed to start: {error}"))?;
    if !output.status.success() {
        let message = capped_stderr(&output.stderr);
        return Err(if message.is_empty() {
            format!("HEOR budget impact engine exited with {}", output.status)
        } else {
            message
        });
    }
    if output.stdout.len() > OUTPUT_CAP_BYTES {
        return Err(format!(
            "HEOR budget impact output exceeds the {} MB limit",
            OUTPUT_CAP_BYTES / 1024 / 1024
        ));
    }
    let calculation: serde_json::Value = serde_json::from_slice(&output.stdout)
        .map_err(|error| format!("HEOR budget impact engine returned invalid JSON: {error}"))?;
    if calculation
        .get("analysis_plan_sha256")
        .and_then(serde_json::Value::as_str)
        != Some(budget_audit.analysis_plan_sha256.as_str())
        || calculation
            .get("budget_impact_plan_sha256")
            .and_then(serde_json::Value::as_str)
            != Some(budget_audit.budget_impact_sha256.as_str())
    {
        return Err("HEOR budget impact engine hashes do not match desktop-audited inputs".into());
    }
    crate::heor_reporting::write_result(
        &workspace,
        crate::heor_reporting::BUDGET_IMPACT_RESULT_PATH,
        &output.stdout,
    )?;

    let plan: serde_json::Value = serde_json::from_slice(&plan_raw)
        .map_err(|error| format!("analysis plan is invalid: {error}"))?;
    let reference_case_id = plan
        .pointer("/reference_case/id")
        .and_then(serde_json::Value::as_str)
        .ok_or("analysis plan omitted reference-case id")?;
    let claimed_reference_case_status = plan
        .pointer("/reference_case/status")
        .and_then(serde_json::Value::as_str)
        .ok_or("analysis plan omitted reference-case status")?;
    let reference_case_status = crate::heor_engine::registered_reference_case_status(
        &app,
        reference_case_id,
        claimed_reference_case_status,
    )?;
    let reference_case_audit =
        crate::heor_reference_case::audit_reference_case_for_plan(&app, &workspace, &plan_raw)?;
    let uncertainty_audit =
        crate::heor_uncertainty::audit_uncertainty_plan_for_plan(&workspace, &plan_raw)?;
    let validation_audit =
        crate::heor_validation::audit_model_validation_for_plan(&workspace, &plan_raw)?;
    let reporting_audit = crate::heor_reporting::audit_report_package(&workspace)?;
    let evidence_selection = crate::heor_evidence::audit_evidence_selection_for_plan(
        &app,
        &workspace,
        &project_id,
        &plan_raw,
    );
    let approval_log = {
        let _guard = approval_state
            .0
            .lock()
            .map_err(|_| "HEOR approval lock poisoned")?;
        crate::heor_approval::verified_log(&app, &project_id)?
    };
    let conceptual_model_matches_artifact =
        crate::heor_engine::conceptual_model_matches_approval(&workspace, &approval_log);
    let workflow = crate::heor_engine::workflow_status(
        approval_log,
        budget_audit.analysis_plan_sha256.clone(),
        conceptual_model_matches_artifact,
        &reference_case_status,
        crate::heor_engine::HeorWorkflowAudits {
            evidence: evidence_audit,
            evidence_selection,
            reference_case: reference_case_audit,
            uncertainty: uncertainty_audit,
            budget_impact: budget_audit,
            validation: validation_audit,
            reporting: reporting_audit,
        },
    );
    Ok(BudgetImpactRunResult {
        workflow,
        calculation,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_workspace(tag: &str) -> std::path::PathBuf {
        let root =
            std::env::temp_dir().join(format!("heor-budget-impact-{tag}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("heor")).unwrap();
        root
    }

    fn fixture() -> (serde_json::Value, Vec<u8>, serde_json::Value, Vec<u8>) {
        let plan_raw = include_bytes!(
            "../../../../python/heor_core/golden_cases/two_strategy_budget_base.json"
        )
        .to_vec();
        let budget_raw = include_bytes!(
            "../../../../python/heor_core/golden_cases/two_strategy_budget_impact.json"
        )
        .to_vec();
        (
            serde_json::from_slice(&plan_raw).unwrap(),
            plan_raw,
            serde_json::from_slice(&budget_raw).unwrap(),
            budget_raw,
        )
    }

    #[test]
    fn complete_budget_impact_plan_is_machine_reviewable() {
        let root = temp_workspace("complete");
        let (plan, plan_raw, budget, budget_raw) = fixture();
        let audit = audit_values(&root, &plan, &plan_raw, &budget, &budget_raw);

        assert!(audit.complete, "{:?}", audit.errors);
        assert_eq!(audit.required_input_count, 24);
        assert_eq!(audit.covered_input_count, 24);
        assert_eq!(audit.cost_category_count, 2);
        assert_eq!(audit.sensitivity_parameter_count, 2);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn multi_strategy_plan_can_bind_an_explicit_budget_pair() {
        let root = temp_workspace("multi-pair");
        let (mut plan, _, mut budget, _) = fixture();
        plan["schema_version"] = serde_json::json!("0.8.0");
        plan["baseline_strategy_id"] = serde_json::json!("standard_care");
        plan["strategy_order"] =
            serde_json::json!(["standard_care", "new_treatment", "alternative"]);
        let comparator = plan["strategies"]
            .as_object_mut()
            .unwrap()
            .remove("comparator")
            .unwrap();
        let intervention = plan["strategies"]
            .as_object_mut()
            .unwrap()
            .remove("intervention")
            .unwrap();
        plan["strategies"]["standard_care"] = comparator;
        plan["strategies"]["new_treatment"] = intervention.clone();
        plan["strategies"]["alternative"] = intervention;
        let plan_raw = serde_json::to_vec(&plan).unwrap();
        budget["base_analysis"]["content_sha256"] = serde_json::json!(sha256(&plan_raw));
        let budget_raw = serde_json::to_vec(&budget).unwrap();

        let audit = audit_values(&root, &plan, &plan_raw, &budget, &budget_raw);

        assert!(audit.complete, "{:?}", audit.errors);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn multi_strategy_budget_pair_requires_exact_safe_declared_keys() {
        let root = temp_workspace("multi-pair-invalid-id");
        let (mut plan, _, mut budget, _) = fixture();
        plan["schema_version"] = serde_json::json!("0.8.0");
        plan["baseline_strategy_id"] = serde_json::json!("standard_care");
        plan["strategy_order"] =
            serde_json::json!(["standard_care", "new_treatment", "alternative"]);
        let comparator = plan["strategies"]
            .as_object_mut()
            .unwrap()
            .remove("comparator")
            .unwrap();
        let intervention = plan["strategies"]
            .as_object_mut()
            .unwrap()
            .remove("intervention")
            .unwrap();
        plan["strategies"]["standard_care"] = comparator;
        plan["strategies"]["new_treatment"] = intervention.clone();
        plan["strategies"]["alternative"] = intervention;
        let plan_raw = serde_json::to_vec(&plan).unwrap();
        budget["base_analysis"]["content_sha256"] = serde_json::json!(sha256(&plan_raw));
        budget["strategies"]["comparator"]["id"] = serde_json::json!("standard_care/name");
        let budget_raw = serde_json::to_vec(&budget).unwrap();

        let audit = audit_values(&root, &plan, &plan_raw, &budget, &budget_raw);

        assert!(!audit.complete);
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("strategies.comparator.id does not match")));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn changed_hash_and_missing_provenance_fail_closed() {
        let root = temp_workspace("invalid");
        let (plan, plan_raw, mut budget, _) = fixture();
        budget["base_analysis"]["content_sha256"] = serde_json::json!("0".repeat(64));
        budget["input_provenance"].as_array_mut().unwrap().pop();
        let budget_raw = serde_json::to_vec(&budget).unwrap();
        let audit = audit_values(&root, &plan, &plan_raw, &budget, &budget_raw);

        assert!(!audit.complete);
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("does not match")));
        assert!(audit
            .invalid_inputs
            .iter()
            .any(|error| error.contains("missing provenance")));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn target_allowlist_rejects_authority_fields() {
        assert!(target_allowed("/population/annual_eligible/0"));
        assert!(target_allowed(
            "/cost_categories/0/annual_per_patient/intervention/2"
        ));
        assert!(!target_allowed("/perspective/price_year"));
        assert!(!target_allowed("/base_analysis/content_sha256"));
    }
}
