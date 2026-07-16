//! Native report-package audit and app-owned release boundary.
//! Reporting checklists document completeness; they are not quality scores.
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::io::Write;
use std::path::Path;
use tauri::{path::BaseDirectory, AppHandle, Manager};

pub const REPORT_PACKAGE_PATH: &str = "heor/report-package.json";
pub const REPORT_DOCUMENT_PATH: &str = "heor/report.md";
pub const BASE_CASE_RESULT_PATH: &str = "heor/results/base-case.json";
pub const UNCERTAINTY_RESULT_PATH: &str = "heor/results/uncertainty.json";
pub const BUDGET_IMPACT_RESULT_PATH: &str = "heor/results/budget-impact.json";
const OUTPUT_CAP_BYTES: usize = 25 * 1024 * 1024;
const BINDINGS: [(&str, &str); 9] = [
    ("report_document", REPORT_DOCUMENT_PATH),
    ("analysis_plan", "heor/analysis-plan.json"),
    ("conceptual_model", "heor/conceptual-model.json"),
    ("uncertainty_plan", "heor/uncertainty-plan.json"),
    ("budget_impact_plan", "heor/budget-impact-plan.json"),
    ("model_validation", "heor/model-validation.json"),
    ("base_case_result", BASE_CASE_RESULT_PATH),
    ("uncertainty_result", UNCERTAINTY_RESULT_PATH),
    ("budget_impact_result", BUDGET_IMPACT_RESULT_PATH),
];
const PARTITIONED_BINDINGS: [(&str, &str); 15] = [
    ("report_document", REPORT_DOCUMENT_PATH),
    ("analysis_plan", "heor/analysis-plan.json"),
    ("conceptual_model", "heor/conceptual-model.json"),
    ("uncertainty_plan", "heor/uncertainty-plan.json"),
    ("budget_impact_plan", "heor/budget-impact-plan.json"),
    ("model_validation", "heor/model-validation.json"),
    (
        "partitioned_survival_plan",
        crate::heor_partitioned_survival::PARTITIONED_SURVIVAL_PLAN_PATH,
    ),
    (
        "survival_curve_materializations",
        crate::heor_survival_materialization::SURVIVAL_MATERIALIZATION_PATH,
    ),
    (
        "treatment_effect_duration",
        crate::heor_treatment_effect_duration::TREATMENT_EFFECT_DURATION_PATH,
    ),
    (
        "cost_input_normalization",
        crate::heor_cost_input_normalization::COST_INPUT_NORMALIZATION_PATH,
    ),
    (
        "utility_inputs",
        crate::heor_utility_inputs::UTILITY_INPUTS_PATH,
    ),
    (
        "event_disutilities",
        crate::heor_event_disutilities::EVENT_DISUTILITIES_PATH,
    ),
    (
        "partitioned_survival_result",
        crate::heor_partitioned_survival::PARTITIONED_SURVIVAL_RESULT_PATH,
    ),
    ("uncertainty_result", UNCERTAINTY_RESULT_PATH),
    ("budget_impact_result", BUDGET_IMPACT_RESULT_PATH),
];
const ITEMS: [(&str, &str); 40] = [
    ("CHEERS-2022", "1-title"),
    ("CHEERS-2022", "2-abstract"),
    ("CHEERS-2022", "3-background-objectives"),
    ("CHEERS-2022", "4-analysis-plan"),
    ("CHEERS-2022", "5-study-population"),
    ("CHEERS-2022", "6-setting-location"),
    ("CHEERS-2022", "7-comparators"),
    ("CHEERS-2022", "8-perspective"),
    ("CHEERS-2022", "9-time-horizon"),
    ("CHEERS-2022", "10-discount-rate"),
    ("CHEERS-2022", "11-outcome-selection"),
    ("CHEERS-2022", "12-outcome-measurement"),
    ("CHEERS-2022", "13-outcome-valuation"),
    ("CHEERS-2022", "14-resources-costs"),
    ("CHEERS-2022", "15-currency-price-date"),
    ("CHEERS-2022", "16-model-rationale-description"),
    ("CHEERS-2022", "17-analytics-assumptions"),
    ("CHEERS-2022", "18-heterogeneity"),
    ("CHEERS-2022", "19-distributional-effects"),
    ("CHEERS-2022", "20-uncertainty"),
    ("CHEERS-2022", "21-engagement-approach"),
    ("CHEERS-2022", "22-study-parameters"),
    ("CHEERS-2022", "23-summary-results"),
    ("CHEERS-2022", "24-uncertainty-effects"),
    ("CHEERS-2022", "25-engagement-effects"),
    ("CHEERS-2022", "26-findings-limitations-generalisability"),
    ("CHEERS-2022", "27-funding"),
    ("CHEERS-2022", "28-conflicts"),
    (
        "ISPOR-BIA-GP-II-2014",
        "bia-1-objective-perspective-audience",
    ),
    ("ISPOR-BIA-GP-II-2014", "bia-2-context"),
    ("ISPOR-BIA-GP-II-2014", "bia-3-eligible-population"),
    ("ISPOR-BIA-GP-II-2014", "bia-4-treatment-mix"),
    ("ISPOR-BIA-GP-II-2014", "bia-5-cost-scope"),
    ("ISPOR-BIA-GP-II-2014", "bia-6-inputs-sources-derivations"),
    ("ISPOR-BIA-GP-II-2014", "bia-7-framework-calculations"),
    ("ISPOR-BIA-GP-II-2014", "bia-8-period-disaggregated-results"),
    ("ISPOR-BIA-GP-II-2014", "bia-9-cumulative-impact"),
    ("ISPOR-BIA-GP-II-2014", "bia-10-uncertainty-scenarios"),
    ("ISPOR-BIA-GP-II-2014", "bia-11-validation"),
    ("ISPOR-BIA-GP-II-2014", "bia-12-limitations-reproducibility"),
];

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ReportingAudit {
    pub complete: bool,
    pub releasable: bool,
    pub status: &'static str,
    pub package_id: String,
    pub analysis_id: String,
    pub report_package_sha256: String,
    pub release_owner_label: String,
    pub binding_hashes: HashMap<String, String>,
    pub binding_paths: HashMap<String, String>,
    pub reporting_item_count: usize,
    pub required_item_count: usize,
    pub covered_item_count: usize,
    pub missing_items: Vec<String>,
    pub invalid_items: Vec<String>,
    pub errors: Vec<String>,
}

fn digest(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}
fn text(value: Option<&serde_json::Value>) -> Option<&str> {
    value
        .and_then(serde_json::Value::as_str)
        .filter(|v| !v.trim().is_empty())
}
fn unique_strings(value: Option<&serde_json::Value>, nonempty: bool) -> Option<HashSet<&str>> {
    let values = value?.as_array()?;
    if nonempty && values.is_empty() {
        return None;
    }
    let mut result = HashSet::new();
    for value in values {
        let value = text(Some(value))?;
        if !result.insert(value) {
            return None;
        }
    }
    Some(result)
}
fn valid_date(value: Option<&serde_json::Value>) -> bool {
    text(value).is_some_and(|value| {
        value.len() == 10
            && value.as_bytes()[4] == b'-'
            && value.as_bytes()[7] == b'-'
            && value
                .bytes()
                .enumerate()
                .all(|(i, b)| matches!(i, 4 | 7) || b.is_ascii_digit())
    })
}
fn empty(error: String) -> ReportingAudit {
    ReportingAudit {
        complete: false,
        releasable: false,
        status: "incomplete",
        package_id: String::new(),
        analysis_id: String::new(),
        report_package_sha256: String::new(),
        release_owner_label: String::new(),
        binding_hashes: HashMap::new(),
        binding_paths: HashMap::new(),
        reporting_item_count: 0,
        required_item_count: ITEMS.len(),
        covered_item_count: 0,
        missing_items: ITEMS.iter().map(|(p, i)| format!("{p}:{i}")).collect(),
        invalid_items: Vec::new(),
        errors: vec![error],
    }
}

fn read_json(workspace: &Path, relative: &str) -> Result<(serde_json::Value, Vec<u8>), String> {
    let raw = crate::heor_uncertainty::read_workspace_capped(workspace, relative)?;
    let value: serde_json::Value =
        serde_json::from_slice(&raw).map_err(|e| format!("{relative} is invalid: {e}"))?;
    if !value.is_object() {
        return Err(format!("{relative} must contain a JSON object"));
    }
    Ok((value, raw))
}

fn expected_result_summary(loaded: &HashMap<&str, serde_json::Value>) -> serde_json::Value {
    let mut expected_uncertainty = serde_json::json!({
        "iterations": loaded.get("uncertainty_result").and_then(|v| v.pointer("/probabilistic_analysis/iterations")).cloned().unwrap_or(serde_json::Value::Null),
        "cost_effective_probability": loaded.get("uncertainty_result").and_then(|v| v.pointer("/probabilistic_analysis/cost_effective_probability")).cloned().unwrap_or(serde_json::Value::Null),
        "mean_incremental_net_monetary_benefit": loaded.get("uncertainty_result").and_then(|v| v.pointer("/probabilistic_analysis/mean_incremental_net_monetary_benefit")).cloned().unwrap_or(serde_json::Value::Null)
    });
    if let Some(decision_uncertainty) = loaded
        .get("uncertainty_result")
        .and_then(|value| value.pointer("/probabilistic_analysis/decision_uncertainty"))
    {
        expected_uncertainty
            .as_object_mut()
            .expect("uncertainty summary is an object")
            .insert("decision_uncertainty".into(), decision_uncertainty.clone());
    }
    if let Some(probabilistic) = loaded
        .get("uncertainty_result")
        .and_then(|value| value.get("probabilistic_analysis"))
    {
        for field in [
            "strategy_order",
            "primary_threshold_strategy_optimal_probabilities",
            "primary_threshold_tie_probability",
            "mean_net_monetary_benefit_by_strategy",
            "net_monetary_benefit_mcse_by_strategy",
        ] {
            if let Some(value) = probabilistic.get(field) {
                expected_uncertainty
                    .as_object_mut()
                    .expect("uncertainty summary is an object")
                    .insert(field.into(), value.clone());
            }
        }
    }
    let base_case = loaded
        .get("partitioned_survival_result")
        .or_else(|| loaded.get("base_case_result"));
    let cost_effectiveness = if base_case
        .and_then(|value| value.get("fully_incremental_analysis"))
        .is_some()
    {
        let strategies = base_case
            .and_then(|value| value.get("strategies"))
            .and_then(serde_json::Value::as_object)
            .map(|items| {
                items
                    .iter()
                    .map(|(strategy_id, strategy)| {
                        (
                            strategy_id.clone(),
                            serde_json::json!({
                                "name": strategy.get("name").cloned().unwrap_or(serde_json::Value::Null),
                                "total_cost": strategy.get("total_cost").cloned().unwrap_or(serde_json::Value::Null),
                                "total_qaly": strategy.get("total_qaly").cloned().unwrap_or(serde_json::Value::Null),
                                "net_monetary_benefit": strategy.get("net_monetary_benefit").cloned().unwrap_or(serde_json::Value::Null)
                            }),
                        )
                    })
                    .collect::<serde_json::Map<_, _>>()
            })
            .map(serde_json::Value::Object)
            .unwrap_or(serde_json::Value::Null);
        serde_json::json!({
            "economic_basis": base_case.and_then(|v| v.get("economic_basis")).cloned().unwrap_or(serde_json::Value::Null),
            "strategy_order": base_case.and_then(|v| v.get("strategy_order")).cloned().unwrap_or(serde_json::Value::Null),
            "baseline_strategy_id": base_case.and_then(|v| v.get("baseline_strategy_id")).cloned().unwrap_or(serde_json::Value::Null),
            "strategies": strategies,
            "pairwise_vs_baseline": base_case.and_then(|v| v.get("pairwise_vs_baseline")).cloned().unwrap_or(serde_json::Value::Null),
            "fully_incremental_analysis": base_case.and_then(|v| v.get("fully_incremental_analysis")).cloned().unwrap_or(serde_json::Value::Null),
            "optimal_at_primary_threshold": base_case.and_then(|v| v.get("optimal_at_primary_threshold")).cloned().unwrap_or(serde_json::Value::Null)
        })
    } else {
        serde_json::json!({
            "economic_basis": base_case.and_then(|v| v.get("economic_basis")).cloned().unwrap_or(serde_json::Value::Null),
            "delta_cost": base_case.and_then(|v| v.pointer("/incremental/delta_cost")).cloned().unwrap_or(serde_json::Value::Null),
            "delta_qaly": base_case.and_then(|v| v.pointer("/incremental/delta_qaly")).cloned().unwrap_or(serde_json::Value::Null),
            "icer": base_case.and_then(|v| v.pointer("/incremental/icer")).cloned().unwrap_or(serde_json::Value::Null),
            "incremental_net_monetary_benefit": base_case.and_then(|v| v.pointer("/incremental/incremental_net_monetary_benefit")).cloned().unwrap_or(serde_json::Value::Null)
        })
    };
    serde_json::json!({
        "cost_effectiveness": cost_effectiveness,
        "uncertainty": expected_uncertainty,
        "budget_impact": {
            "annual_net_budget_impact": loaded.get("budget_impact_result").and_then(|v| v.pointer("/base_case/annual_net_budget_impact")).cloned().unwrap_or(serde_json::Value::Null),
            "cumulative_net_budget_impact": loaded.get("budget_impact_result").and_then(|v| v.pointer("/base_case/cumulative_net_budget_impact")).cloned().unwrap_or(serde_json::Value::Null)
        }
    })
}

pub fn audit_report_package(workspace: &Path) -> Result<ReportingAudit, String> {
    let (package, package_raw) = match read_json(workspace, REPORT_PACKAGE_PATH) {
        Ok(value) => value,
        Err(error) => return Ok(empty(error)),
    };
    let mut audit = empty(String::new());
    audit.errors.clear();
    audit.missing_items.clear();
    audit.package_id = text(package.get("package_id"))
        .unwrap_or_default()
        .to_string();
    audit.analysis_id = text(package.get("analysis_id"))
        .unwrap_or_default()
        .to_string();
    audit.release_owner_label = text(package.get("release_owner_label"))
        .unwrap_or_default()
        .to_string();
    audit.report_package_sha256 = digest(&package_raw);
    let analysis = read_json(workspace, "heor/analysis-plan.json")
        .map(|(value, _)| value)
        .unwrap_or(serde_json::Value::Null);
    let partitioned = analysis
        .pointer("/partitioned_survival_analysis/path")
        .and_then(serde_json::Value::as_str)
        == Some(crate::heor_partitioned_survival::PARTITIONED_SURVIVAL_PLAN_PATH);
    let expected_schema = if partitioned { "0.2.0" } else { "0.1.0" };
    if text(package.get("schema_version")) != Some(expected_schema) {
        audit.errors.push(format!(
            "{} reporting requires schema_version {expected_schema}",
            if partitioned {
                "partitioned-survival"
            } else {
                "non-partitioned"
            }
        ));
    }
    let expected_bindings = if partitioned {
        PARTITIONED_BINDINGS.as_slice()
    } else {
        BINDINGS.as_slice()
    };
    for field in [
        "package_id",
        "analysis_id",
        "version",
        "intended_audience",
        "release_owner_label",
    ] {
        if text(package.get(field)).is_none() {
            audit
                .errors
                .push(format!("report package {field} is required"));
        }
    }
    if text(package.get("status")) != Some("ready_for_release_review") {
        audit
            .errors
            .push("report package must be ready_for_release_review".into());
    }
    if !valid_date(package.get("prepared_on")) {
        audit
            .errors
            .push("report package prepared_on must be YYYY-MM-DD".into());
    }
    let expected_profiles = serde_json::json!([
        {"id":"CHEERS-2022","status":"current","scope":"cost_effectiveness"},
        {"id":"ISPOR-BIA-GP-II-2014","status":"current","scope":"budget_impact"}
    ]);
    if package.get("reporting_profiles") != Some(&expected_profiles) {
        audit
            .errors
            .push("reporting profiles or their scopes are invalid".into());
    }

    let mut loaded = HashMap::<&str, serde_json::Value>::new();
    let mut report = String::new();
    let expected_keys = expected_bindings
        .iter()
        .map(|(key, _)| *key)
        .collect::<HashSet<_>>();
    if package
        .get("bindings")
        .and_then(serde_json::Value::as_object)
        .is_none_or(|value| {
            value.len() != expected_keys.len()
                || value
                    .keys()
                    .any(|key| !expected_keys.contains(key.as_str()))
        })
    {
        audit
            .errors
            .push("bindings fields do not match the report schema".into());
    }
    for &(key, relative) in expected_bindings {
        let binding = package.pointer(&format!("/bindings/{key}"));
        if binding.and_then(|v| text(v.get("path"))) != Some(relative) {
            audit
                .errors
                .push(format!("bindings.{key}.path must be {relative}"));
            continue;
        }
        let raw = match crate::heor_uncertainty::read_workspace_capped(workspace, relative) {
            Ok(raw) => raw,
            Err(error) => {
                audit.errors.push(error);
                continue;
            }
        };
        let hash = digest(&raw);
        audit.binding_hashes.insert(key.into(), hash.clone());
        audit.binding_paths.insert(key.into(), relative.into());
        if binding.and_then(|v| text(v.get("content_sha256"))) != Some(hash.as_str()) {
            audit.errors.push(format!(
                "bindings.{key}.content_sha256 does not match current bytes"
            ));
        }
        if key == "report_document" {
            match String::from_utf8(raw) {
                Ok(value) => report = value,
                Err(_) => audit.errors.push("heor/report.md must be UTF-8".into()),
            }
        } else {
            match serde_json::from_slice::<serde_json::Value>(&raw) {
                Ok(value) if value.is_object() => {
                    loaded.insert(key, value);
                }
                Ok(_) => audit
                    .errors
                    .push(format!("{relative} must contain a JSON object")),
                Err(error) => audit.errors.push(format!("{relative} is invalid: {error}")),
            }
        }
    }
    for (key, value) in &loaded {
        if text(value.get("analysis_id")) != Some(audit.analysis_id.as_str()) {
            audit.errors.push(format!(
                "{} analysis_id does not match the report package",
                audit
                    .binding_paths
                    .get(*key)
                    .map(String::as_str)
                    .unwrap_or("bound artifact")
            ));
        }
    }
    let hash = |key: &str| audit.binding_hashes.get(key).map(String::as_str);
    if loaded.get("base_case_result").is_some()
        && loaded
            .get("base_case_result")
            .and_then(|v| text(v.get("input_sha256")))
            != hash("analysis_plan")
    {
        audit.errors.push("base-case result is stale".into());
    }
    if loaded
        .get("uncertainty_result")
        .and_then(|v| text(v.get("base_analysis_sha256")))
        != hash("analysis_plan")
        || loaded
            .get("uncertainty_result")
            .and_then(|v| text(v.get("uncertainty_plan_sha256")))
            != hash("uncertainty_plan")
    {
        audit.errors.push("uncertainty result is stale".into());
    }
    if loaded
        .get("budget_impact_result")
        .and_then(|v| text(v.get("analysis_plan_sha256")))
        != hash("analysis_plan")
        || loaded
            .get("budget_impact_result")
            .and_then(|v| text(v.get("budget_impact_plan_sha256")))
            != hash("budget_impact_plan")
    {
        audit.errors.push("budget-impact result is stale".into());
    }
    if partitioned {
        for (field, key) in [
            ("analysis_plan_sha256", "analysis_plan"),
            (
                "partitioned_survival_plan_sha256",
                "partitioned_survival_plan",
            ),
            (
                "survival_curve_materializations_sha256",
                "survival_curve_materializations",
            ),
            (
                "treatment_effect_duration_sha256",
                "treatment_effect_duration",
            ),
            (
                "cost_input_normalization_sha256",
                "cost_input_normalization",
            ),
            ("utility_inputs_sha256", "utility_inputs"),
            ("event_disutilities_sha256", "event_disutilities"),
        ] {
            let expected = hash(key);
            if loaded
                .get("partitioned_survival_result")
                .and_then(|value| text(value.get(field)))
                != expected
            {
                audit.errors.push(format!(
                    "partitioned-survival result {field} does not match bound bytes"
                ));
            }
            let uncertainty_field = if field == "analysis_plan_sha256" {
                "base_analysis_sha256"
            } else {
                field
            };
            if loaded
                .get("uncertainty_result")
                .and_then(|value| text(value.get(uncertainty_field)))
                != expected
            {
                audit.errors.push(format!(
                    "uncertainty result {uncertainty_field} does not match bound bytes"
                ));
            }
        }
    }

    let expected = ITEMS.iter().copied().collect::<HashSet<_>>();
    let mut seen = HashSet::<(String, String)>::new();
    let mut sections = HashSet::<String>::new();
    let allowed_paths = expected_bindings
        .iter()
        .map(|(_, path)| *path)
        .collect::<HashSet<_>>();
    let items = package.get("items").and_then(serde_json::Value::as_array);
    audit.reporting_item_count = items.map_or(0, Vec::len);
    if audit.reporting_item_count != ITEMS.len() {
        audit.errors.push(format!(
            "items must contain exactly {} reporting items",
            ITEMS.len()
        ));
    }
    for (index, item) in items.into_iter().flatten().enumerate() {
        let profile = text(item.get("profile_id")).unwrap_or_default();
        let item_id = text(item.get("item_id")).unwrap_or_default();
        if !expected.contains(&(profile, item_id)) || !seen.insert((profile.into(), item_id.into()))
        {
            audit
                .invalid_items
                .push(format!("items[{index}] is unrecognized or duplicated"));
        }
        if !matches!(
            text(item.get("status")),
            Some("reported" | "not_applicable")
        ) || text(item.get("rationale")).is_none()
        {
            audit
                .invalid_items
                .push(format!("items[{index}] status or rationale is invalid"));
        }
        let section = text(item.get("section_id"));
        if !section.is_some_and(|section| {
            sections.insert(section.into())
                && report
                    .matches(&format!("<!-- report-section:{section} -->"))
                    .count()
                    == 1
        }) {
            audit
                .invalid_items
                .push(format!("items[{index}] report marker is invalid"));
        }
        if !unique_strings(item.get("artifact_paths"), true)
            .is_some_and(|paths| paths.iter().all(|path| allowed_paths.contains(path)))
        {
            audit
                .invalid_items
                .push(format!("items[{index}] artifact_paths are invalid"));
        }
    }
    for (profile, item) in ITEMS {
        if !seen.contains(&(profile.into(), item.into())) {
            audit.missing_items.push(format!("{profile}:{item}"));
        }
    }
    audit.covered_item_count = ITEMS.len() - audit.missing_items.len();
    audit.errors.extend(audit.invalid_items.iter().cloned());
    if !audit.missing_items.is_empty() {
        audit
            .errors
            .push("required reporting items are missing".into());
    }

    let expected_summary = expected_result_summary(&loaded);
    if package.get("result_summary") != Some(&expected_summary) {
        audit
            .errors
            .push("result_summary does not match deterministic results".into());
    }
    for key in [
        "funding",
        "conflicts_of_interest",
        "agent_contributions",
        "model_providers",
        "data_and_model_availability",
        "patient_and_public_involvement",
    ] {
        if package
            .pointer(&format!("/disclosures/{key}"))
            .and_then(|v| text(Some(v)))
            .is_none()
        {
            audit.errors.push(format!("disclosures.{key} is required"));
        }
    }
    if package
        .get("disclosures")
        .and_then(serde_json::Value::as_object)
        .is_none_or(|value| value.len() != 6)
    {
        audit
            .errors
            .push("disclosures must contain exactly the six recognized fields".into());
    }
    if !unique_strings(package.get("limitations"), true).is_some_and(|v| !v.is_empty()) {
        audit.errors.push("limitations are required".into());
    }
    if !unique_strings(package.get("release_notes"), true).is_some_and(|v| !v.is_empty()) {
        audit.errors.push("release_notes are required".into());
    }
    audit.complete = audit.errors.is_empty();
    audit.releasable = audit.complete;
    audit.status = if audit.complete {
        "complete"
    } else {
        "incomplete"
    };
    Ok(audit)
}

pub fn write_result(workspace: &Path, relative: &str, raw: &[u8]) -> Result<(), String> {
    if raw.len() > OUTPUT_CAP_BYTES
        || !matches!(
            relative,
            BASE_CASE_RESULT_PATH
                | UNCERTAINTY_RESULT_PATH
                | BUDGET_IMPACT_RESULT_PATH
                | crate::heor_partitioned_survival::PARTITIONED_SURVIVAL_RESULT_PATH
        )
    {
        return Err("HEOR result is not a bounded first-party result artifact".into());
    }
    serde_json::from_slice::<serde_json::Value>(raw)
        .map_err(|e| format!("HEOR result is invalid: {e}"))?;
    let root = workspace
        .canonicalize()
        .map_err(|e| format!("workspace unavailable: {e}"))?;
    let target = root.join(relative);
    let parent = target.parent().ok_or("HEOR result path has no parent")?;
    std::fs::create_dir_all(parent).map_err(|e| format!("HEOR result directory failed: {e}"))?;
    let temporary = parent.join(format!(".result-{}.tmp", crate::runtime::random_hex(8)));
    let mut file = std::fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(&temporary)
        .map_err(|e| format!("HEOR result staging failed: {e}"))?;
    file.write_all(raw)
        .and_then(|_| file.sync_all())
        .map_err(|e| format!("HEOR result write failed: {e}"))?;
    std::fs::rename(&temporary, &target).map_err(|e| {
        let _ = std::fs::remove_file(&temporary);
        format!("HEOR result commit failed: {e}")
    })
}

fn run_engine(
    app: &AppHandle,
    workspace: &Path,
    extra: &[(&str, &str)],
) -> Result<Vec<u8>, String> {
    let package_src = app
        .path()
        .resolve("heor-core/src", BaseDirectory::Resource)
        .map_err(|e| format!("bundled HEOR engine unavailable: {e}"))?;
    let (python, _) = crate::kernel::python_bin(app)?;
    let mut command = crate::runtime::quiet_command(python);
    command
        .args(["-m", "heor_core"])
        .arg(workspace.join("heor/analysis-plan.json"));
    for (flag, relative) in extra {
        command.arg(flag).arg(workspace.join(relative));
    }
    let output = command
        .current_dir(workspace)
        .env("PYTHONPATH", package_src)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("PYTHONNOUSERSITE", "1")
        .output()
        .map_err(|e| format!("release verification engine failed to start: {e}"))?;
    if !output.status.success() {
        return Err("release verification engine failed".into());
    }
    if output.stdout.len() > OUTPUT_CAP_BYTES {
        return Err("release verification output exceeds cap".into());
    }
    serde_json::from_slice::<serde_json::Value>(&output.stdout)
        .map_err(|e| format!("release verification engine returned invalid JSON: {e}"))?;
    Ok(output.stdout)
}

fn reexecute_result_hashes(
    app: &AppHandle,
    workspace: &Path,
) -> Result<HashMap<&'static str, String>, String> {
    let plan_raw =
        crate::heor_uncertainty::read_workspace_capped(workspace, "heor/analysis-plan.json")?;
    let partitioned = crate::heor_partitioned_survival::audit_partitioned_survival_for_plan(
        workspace, &plan_raw,
    )?;
    let mut model_args = Vec::new();
    if partitioned.required {
        if !partitioned.complete {
            return Err(
                "release verification requires a complete partitioned-survival audit".into(),
            );
        }
        model_args.extend([
            (
                "--partitioned-survival-plan",
                crate::heor_partitioned_survival::PARTITIONED_SURVIVAL_PLAN_PATH,
            ),
            (
                "--survival-curve-materializations",
                crate::heor_survival_materialization::SURVIVAL_MATERIALIZATION_PATH,
            ),
        ]);
        if partitioned.treatment_effect_duration_required {
            model_args.push((
                "--treatment-effect-duration",
                crate::heor_treatment_effect_duration::TREATMENT_EFFECT_DURATION_PATH,
            ));
        }
        if partitioned.cost_input_normalization_required {
            model_args.push((
                "--cost-input-normalization",
                crate::heor_cost_input_normalization::COST_INPUT_NORMALIZATION_PATH,
            ));
        }
        if partitioned.utility_inputs_required {
            model_args.push((
                "--utility-inputs",
                crate::heor_utility_inputs::UTILITY_INPUTS_PATH,
            ));
        }
        if partitioned.event_disutilities_required {
            model_args.push((
                "--event-disutilities",
                crate::heor_event_disutilities::EVENT_DISUTILITIES_PATH,
            ));
        }
    }
    let base = run_engine(app, workspace, &model_args)?;

    let mut uncertainty_args = vec![(
        "--uncertainty-plan",
        crate::heor_uncertainty::UNCERTAINTY_PLAN_PATH,
    )];
    uncertainty_args.extend(model_args.iter().copied());
    if partitioned.required {
        let uncertainty_audit =
            crate::heor_uncertainty::audit_uncertainty_plan_for_plan(workspace, &plan_raw)?;
        if !uncertainty_audit.complete {
            return Err("release verification requires a complete uncertainty audit".into());
        }
        if uncertainty_audit.joint_survival_required {
            uncertainty_args.extend([
                (
                    "--joint-survival-uncertainty-manifest",
                    crate::heor_joint_survival_uncertainty::MANIFEST_PATH,
                ),
                (
                    "--joint-survival-draws",
                    crate::heor_joint_survival_uncertainty::DRAWS_PATH,
                ),
            ]);
        }
    }
    let uncertainty = run_engine(app, workspace, &uncertainty_args)?;
    let budget = run_engine(
        app,
        workspace,
        &[(
            "--budget-impact-plan",
            crate::heor_budget_impact::BUDGET_IMPACT_PLAN_PATH,
        )],
    )?;
    let mut hashes = HashMap::from([
        ("uncertainty_result", digest(&uncertainty)),
        ("budget_impact_result", digest(&budget)),
    ]);
    hashes.insert(
        if partitioned.required {
            "partitioned_survival_result"
        } else {
            "base_case_result"
        },
        digest(&base),
    );
    Ok(hashes)
}

pub fn release_matches_approval(
    log: &crate::heor_approval::ApprovalLog,
    audit: &ReportingAudit,
    reproducibility: &crate::heor_reproducibility::ReproducibilityAudit,
) -> bool {
    log.effective_approved_gates
        .contains(&crate::heor_approval::ApprovalGate::Release)
        && log
            .events
            .iter()
            .rev()
            .find(|event| event.gate == crate::heor_approval::ApprovalGate::Release)
            .is_some_and(|event| {
                event.action == crate::heor_approval::ApprovalAction::Approve
                    && event.artifact_sha256 == audit.report_package_sha256
                    && event.actor_label == audit.release_owner_label
                    && audit.releasable
                    && reproducibility.release_companion_ready
                    && reproducibility.report_package_sha256 == audit.report_package_sha256
                    && crate::heor_approval::event_binds_artifact(
                        event,
                        crate::heor_reproducibility::REPRODUCIBILITY_PACKAGE_PATH,
                        &reproducibility.package_sha256,
                    )
                    && approval_bindings(audit).iter().all(|binding| {
                        crate::heor_approval::event_binds_artifact(
                            event,
                            &binding.path,
                            &binding.sha256,
                        )
                    })
            })
}

pub fn release_approval_bindings(
    audit: &ReportingAudit,
    reproducibility: &crate::heor_reproducibility::ReproducibilityAudit,
) -> Vec<crate::heor_approval::ArtifactBinding> {
    let mut bindings = approval_bindings(audit);
    bindings.push(crate::heor_reproducibility::approval_binding(
        reproducibility,
    ));
    bindings.sort_by(|left, right| left.path.cmp(&right.path));
    bindings
}

pub fn approval_bindings(audit: &ReportingAudit) -> Vec<crate::heor_approval::ArtifactBinding> {
    let mut bindings = audit
        .binding_paths
        .iter()
        .filter_map(|(key, path)| {
            audit
                .binding_hashes
                .get(key)
                .map(|sha256| crate::heor_approval::ArtifactBinding {
                    path: path.clone(),
                    sha256: sha256.clone(),
                })
        })
        .collect::<Vec<_>>();
    bindings.sort_by(|left, right| left.path.cmp(&right.path));
    bindings
}

pub fn require_report_releasable(
    app: &AppHandle,
    workspace: &Path,
    expected_hash: &str,
    actor: &str,
    log: &crate::heor_approval::ApprovalLog,
) -> Result<
    (
        ReportingAudit,
        crate::heor_reproducibility::ReproducibilityAudit,
    ),
    String,
> {
    let audit = audit_report_package(workspace)?;
    if !audit.releasable || audit.report_package_sha256 != expected_hash {
        return Err("release approval must target the current complete report package".into());
    }
    if actor != audit.release_owner_label {
        return Err("release actorLabel must exactly match release_owner_label".into());
    }
    let reproducibility =
        crate::heor_reproducibility::audit_reproducibility_package(app, workspace)?;
    if !reproducibility.release_companion_ready
        || reproducibility.analysis_id != audit.analysis_id
        || reproducibility.report_package_sha256 != audit.report_package_sha256
    {
        return Err("release requires a complete current reproducibility companion".into());
    }
    let plan_raw =
        crate::heor_uncertainty::read_workspace_capped(workspace, "heor/analysis-plan.json")?;
    let partitioned = crate::heor_partitioned_survival::audit_partitioned_survival_for_plan(
        workspace, &plan_raw,
    )?;
    if partitioned.required {
        if !partitioned.complete {
            return Err("release requires a complete partitioned-survival audit".into());
        }
        let analysis_current = log
            .effective_approved_gates
            .contains(&crate::heor_approval::ApprovalGate::AnalysisPlan)
            && log
                .events
                .iter()
                .rev()
                .find(|event| event.gate == crate::heor_approval::ApprovalGate::AnalysisPlan)
                .is_some_and(|event| {
                    event.action == crate::heor_approval::ApprovalAction::Approve
                        && event.artifact_sha256 == partitioned.analysis_plan_sha256
                        && partitioned.artifact_bindings.iter().all(|binding| {
                            crate::heor_approval::event_binds_artifact(
                                event,
                                &binding.path,
                                &binding.sha256,
                            )
                        })
                });
        if !analysis_current {
            return Err(
                "release requires a current analysis-plan approval binding every PSM input".into(),
            );
        }
    }
    let validation = crate::heor_validation::audit_model_validation_for_plan(workspace, &plan_raw)?;
    let validation_current = log
        .effective_approved_gates
        .contains(&crate::heor_approval::ApprovalGate::IndependentValidation)
        && log
            .events
            .iter()
            .rev()
            .find(|event| event.gate == crate::heor_approval::ApprovalGate::IndependentValidation)
            .is_some_and(|event| {
                event.action == crate::heor_approval::ApprovalAction::Approve
                    && event.artifact_sha256 == validation.validation_sha256
                    && event.actor_label == validation.reviewer_label
                    && validation.approvable
                    && crate::heor_validation::analysis_plan_approval_is_current(log, &validation)
                    && crate::heor_validation::approval_bindings(&validation)
                        .iter()
                        .all(|binding| {
                            crate::heor_approval::event_binds_artifact(
                                event,
                                &binding.path,
                                &binding.sha256,
                            )
                        })
            });
    if !validation_current {
        return Err("release requires a current independent-validation approval".into());
    }
    for (key, actual) in reexecute_result_hashes(app, workspace)? {
        if audit.binding_hashes.get(key) != Some(&actual) {
            return Err(format!("release verification reproduced a different {key}"));
        }
    }
    let refreshed = audit_report_package(workspace)?;
    let refreshed_reproducibility =
        crate::heor_reproducibility::audit_reproducibility_package(app, workspace)?;
    if !refreshed.releasable
        || refreshed.report_package_sha256 != expected_hash
        || refreshed.release_owner_label != actor
        || refreshed.binding_hashes != audit.binding_hashes
        || !refreshed_reproducibility.release_companion_ready
        || refreshed_reproducibility.package_sha256 != reproducibility.package_sha256
        || refreshed_reproducibility.report_package_sha256 != refreshed.report_package_sha256
    {
        return Err(
            "report package or a bound artifact changed during release verification".into(),
        );
    }
    Ok((refreshed, refreshed_reproducibility))
}

#[tauri::command(async)]
pub fn audit_heor_reporting(app: AppHandle) -> Result<ReportingAudit, String> {
    audit_report_package(&crate::runtime::workspace_dir(&app)?)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn complete_audit() -> ReportingAudit {
        ReportingAudit {
            complete: true,
            releasable: true,
            status: "complete",
            package_id: "report-1".into(),
            analysis_id: "analysis-1".into(),
            report_package_sha256: "a".repeat(64),
            release_owner_label: "Release owner".into(),
            binding_hashes: BINDINGS
                .iter()
                .map(|(key, _)| ((*key).into(), "b".repeat(64)))
                .collect(),
            binding_paths: BINDINGS
                .iter()
                .map(|(key, path)| ((*key).into(), (*path).into()))
                .collect(),
            reporting_item_count: 40,
            required_item_count: 40,
            covered_item_count: 40,
            missing_items: Vec::new(),
            invalid_items: Vec::new(),
            errors: Vec::new(),
        }
    }

    #[test]
    fn result_summary_copies_decision_uncertainty_without_inference() {
        let decision_uncertainty = serde_json::json!({
            "threshold_results": [{"threshold": 100000.0, "per_person_evpi": 125.0}],
            "population_evpi": null,
            "evppi": null
        });
        let loaded = HashMap::from([
            ("base_case_result", serde_json::json!({"incremental": {}})),
            (
                "uncertainty_result",
                serde_json::json!({"probabilistic_analysis": {
                    "decision_uncertainty": decision_uncertainty
                }}),
            ),
            ("budget_impact_result", serde_json::json!({"base_case": {}})),
        ]);
        let summary = expected_result_summary(&loaded);
        assert_eq!(
            summary.pointer("/uncertainty/decision_uncertainty"),
            loaded["uncertainty_result"].pointer("/probabilistic_analysis/decision_uncertainty")
        );
        assert!(summary
            .pointer("/uncertainty/decision_uncertainty/population_evpi")
            .is_some_and(serde_json::Value::is_null));
        assert!(summary
            .pointer("/cost_effectiveness/economic_basis")
            .is_some_and(serde_json::Value::is_null));
    }

    #[test]
    fn legacy_result_summary_does_not_manufacture_decision_uncertainty() {
        let loaded = HashMap::from([
            ("base_case_result", serde_json::json!({"incremental": {}})),
            (
                "uncertainty_result",
                serde_json::json!({"probabilistic_analysis": {"iterations": 1000}}),
            ),
            ("budget_impact_result", serde_json::json!({"base_case": {}})),
        ]);
        let summary = expected_result_summary(&loaded);
        assert!(summary
            .pointer("/uncertainty/decision_uncertainty")
            .is_none());
    }

    #[test]
    fn multi_strategy_result_summary_preserves_frontier_and_strategy_probabilities() {
        let frontier = serde_json::json!([
            {"strategy_id": "standard", "status": "frontier", "icer": null},
            {"strategy_id": "treatment", "status": "frontier", "icer": 50000}
        ]);
        let probabilities = serde_json::json!({"standard": 0.25, "treatment": 0.75});
        let loaded = HashMap::from([
            (
                "base_case_result",
                serde_json::json!({
                    "economic_basis": {"currency": "CNY", "price_year": 2026},
                    "strategy_order": ["standard", "treatment"],
                    "baseline_strategy_id": "standard",
                    "strategies": {
                        "standard": {"name": "Standard", "total_cost": 0, "total_qaly": 1, "net_monetary_benefit": 100000, "occupancy": [[1]]},
                        "treatment": {"name": "Treatment", "total_cost": 50000, "total_qaly": 2, "net_monetary_benefit": 150000, "occupancy": [[1]]}
                    },
                    "pairwise_vs_baseline": {"treatment": {"delta_cost": 50000}},
                    "fully_incremental_analysis": frontier,
                    "optimal_at_primary_threshold": {"strategy_id": "treatment"}
                }),
            ),
            (
                "uncertainty_result",
                serde_json::json!({"probabilistic_analysis": {
                    "iterations": 1000,
                    "strategy_order": ["standard", "treatment"],
                    "primary_threshold_strategy_optimal_probabilities": probabilities
                }}),
            ),
            ("budget_impact_result", serde_json::json!({"base_case": {}})),
        ]);

        let summary = expected_result_summary(&loaded);

        assert_eq!(
            summary.pointer("/cost_effectiveness/fully_incremental_analysis"),
            Some(&frontier)
        );
        assert_eq!(
            summary.pointer("/uncertainty/primary_threshold_strategy_optimal_probabilities"),
            Some(&probabilities)
        );
        assert!(summary
            .pointer("/cost_effectiveness/strategies/standard/occupancy")
            .is_none());
        assert!(summary.pointer("/cost_effectiveness/delta_cost").is_none());
    }

    #[test]
    fn complete_multi_strategy_report_package_is_natively_auditable() {
        let root =
            std::env::temp_dir().join(format!("heor-report-multi-package-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("heor/results")).unwrap();

        let analysis_plan = serde_json::json!({
            "analysis_id": "analysis-1",
            "schema_version": "0.9.0"
        });
        let analysis_raw = serde_json::to_vec(&analysis_plan).unwrap();
        let analysis_hash = digest(&analysis_raw);
        let uncertainty_plan = serde_json::json!({
            "analysis_id": "analysis-1",
            "schema_version": "0.8.0"
        });
        let uncertainty_plan_raw = serde_json::to_vec(&uncertainty_plan).unwrap();
        let uncertainty_plan_hash = digest(&uncertainty_plan_raw);
        let budget_plan = serde_json::json!({
            "analysis_id": "analysis-1",
            "schema_version": "0.1.0"
        });
        let budget_plan_raw = serde_json::to_vec(&budget_plan).unwrap();
        let budget_plan_hash = digest(&budget_plan_raw);
        let base_case = serde_json::json!({
            "analysis_id": "analysis-1",
            "input_sha256": analysis_hash,
            "economic_basis": {"currency": "CNY", "price_year": 2026},
            "strategy_order": ["standard", "treatment"],
            "baseline_strategy_id": "standard",
            "strategies": {
                "standard": {"name": "Standard", "total_cost": 10000, "total_qaly": 1, "net_monetary_benefit": 90000},
                "treatment": {"name": "Treatment", "total_cost": 20000, "total_qaly": 1.5, "net_monetary_benefit": 130000}
            },
            "pairwise_vs_baseline": {"treatment": {"delta_cost": 10000, "delta_qaly": 0.5, "icer": 20000}},
            "fully_incremental_analysis": [
                {"strategy_id": "standard", "status": "frontier", "icer": null},
                {"strategy_id": "treatment", "status": "frontier", "icer": 20000}
            ],
            "optimal_at_primary_threshold": {"strategy_id": "treatment"}
        });
        let uncertainty_result = serde_json::json!({
            "analysis_id": "analysis-1",
            "base_analysis_sha256": analysis_hash,
            "uncertainty_plan_sha256": uncertainty_plan_hash,
            "probabilistic_analysis": {
                "iterations": 1000,
                "strategy_order": ["standard", "treatment"],
                "primary_threshold_strategy_optimal_probabilities": {"standard": 0.2, "treatment": 0.8},
                "primary_threshold_tie_probability": 0,
                "mean_net_monetary_benefit_by_strategy": {"standard": 90000, "treatment": 130000},
                "net_monetary_benefit_mcse_by_strategy": {"standard": 100, "treatment": 120},
                "decision_uncertainty": {
                    "strategy_order": ["standard", "treatment"],
                    "threshold_results": []
                }
            }
        });
        let budget_result = serde_json::json!({
            "analysis_id": "analysis-1",
            "analysis_plan_sha256": analysis_hash,
            "budget_impact_plan_sha256": budget_plan_hash,
            "base_case": {
                "annual_net_budget_impact": [1, 2, 3],
                "cumulative_net_budget_impact": 6
            }
        });
        let conceptual_model = serde_json::json!({"analysis_id": "analysis-1"});
        let model_validation = serde_json::json!({"analysis_id": "analysis-1"});
        let report = ITEMS
            .iter()
            .enumerate()
            .map(|(index, _)| format!("<!-- report-section:section-{index} -->\nSection {index}\n"))
            .collect::<String>();

        let artifacts = HashMap::from([
            (REPORT_DOCUMENT_PATH, report.into_bytes()),
            ("heor/analysis-plan.json", analysis_raw),
            (
                "heor/conceptual-model.json",
                serde_json::to_vec(&conceptual_model).unwrap(),
            ),
            ("heor/uncertainty-plan.json", uncertainty_plan_raw),
            ("heor/budget-impact-plan.json", budget_plan_raw),
            (
                "heor/model-validation.json",
                serde_json::to_vec(&model_validation).unwrap(),
            ),
            (
                BASE_CASE_RESULT_PATH,
                serde_json::to_vec(&base_case).unwrap(),
            ),
            (
                UNCERTAINTY_RESULT_PATH,
                serde_json::to_vec(&uncertainty_result).unwrap(),
            ),
            (
                BUDGET_IMPACT_RESULT_PATH,
                serde_json::to_vec(&budget_result).unwrap(),
            ),
        ]);
        for (relative, raw) in &artifacts {
            let target = root.join(relative);
            std::fs::create_dir_all(target.parent().unwrap()).unwrap();
            std::fs::write(target, raw).unwrap();
        }

        let bindings = BINDINGS
            .iter()
            .map(|(key, relative)| {
                (
                    (*key).to_string(),
                    serde_json::json!({
                        "path": relative,
                        "content_sha256": digest(artifacts.get(relative).unwrap())
                    }),
                )
            })
            .collect::<serde_json::Map<_, _>>();
        let items = ITEMS
            .iter()
            .enumerate()
            .map(|(index, (profile_id, item_id))| {
                serde_json::json!({
                    "profile_id": profile_id,
                    "item_id": item_id,
                    "status": "reported",
                    "rationale": "Reported in the bound document.",
                    "section_id": format!("section-{index}"),
                    "artifact_paths": [REPORT_DOCUMENT_PATH]
                })
            })
            .collect::<Vec<_>>();
        let loaded = HashMap::from([
            ("base_case_result", base_case),
            ("uncertainty_result", uncertainty_result),
            ("budget_impact_result", budget_result),
        ]);
        let package = serde_json::json!({
            "schema_version": "0.1.0",
            "package_id": "report-1",
            "analysis_id": "analysis-1",
            "version": "1.0",
            "status": "ready_for_release_review",
            "prepared_on": "2026-03-18",
            "intended_audience": "Health technology assessment reviewers",
            "release_owner_label": "Release owner",
            "reporting_profiles": [
                {"id":"CHEERS-2022","status":"current","scope":"cost_effectiveness"},
                {"id":"ISPOR-BIA-GP-II-2014","status":"current","scope":"budget_impact"}
            ],
            "bindings": bindings,
            "items": items,
            "result_summary": expected_result_summary(&loaded),
            "disclosures": {
                "funding": "None",
                "conflicts_of_interest": "None",
                "agent_contributions": "Documented",
                "model_providers": "Documented",
                "data_and_model_availability": "Documented",
                "patient_and_public_involvement": "Not involved"
            },
            "limitations": ["Illustrative package"],
            "release_notes": ["Initial release"]
        });
        std::fs::write(
            root.join(REPORT_PACKAGE_PATH),
            serde_json::to_vec(&package).unwrap(),
        )
        .unwrap();

        let audit = audit_report_package(&root).unwrap();

        assert!(audit.complete, "{:?}", audit.errors);
        assert!(audit.releasable);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn result_writer_rejects_unrecognized_paths() {
        let root = std::env::temp_dir().join(format!("heor-report-writer-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        assert!(write_result(&root, "heor/results/other.json", b"{}").is_err());
    }

    #[test]
    fn result_writer_replaces_only_a_valid_first_party_result() {
        let root =
            std::env::temp_dir().join(format!("heor-report-writer-replace-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        write_result(&root, BASE_CASE_RESULT_PATH, br#"{"value":1}"#).unwrap();
        write_result(&root, BASE_CASE_RESULT_PATH, br#"{"value":2}"#).unwrap();
        assert_eq!(
            std::fs::read(root.join(BASE_CASE_RESULT_PATH)).unwrap(),
            br#"{"value":2}"#
        );
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn result_writer_accepts_partitioned_survival_result() {
        let root = std::env::temp_dir().join(format!(
            "heor-report-writer-partitioned-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        write_result(
            &root,
            crate::heor_partitioned_survival::PARTITIONED_SURVIVAL_RESULT_PATH,
            br#"{"analysis_id":"analysis-1"}"#,
        )
        .unwrap();
        assert!(root
            .join(crate::heor_partitioned_survival::PARTITIONED_SURVIVAL_RESULT_PATH)
            .is_file());
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn approval_bindings_follow_the_schema_selected_paths() {
        let mut audit = complete_audit();
        audit.binding_paths = PARTITIONED_BINDINGS
            .iter()
            .map(|(key, path)| ((*key).into(), (*path).into()))
            .collect();
        audit.binding_hashes = PARTITIONED_BINDINGS
            .iter()
            .map(|(key, _)| ((*key).into(), "c".repeat(64)))
            .collect();

        let bindings = approval_bindings(&audit);

        assert_eq!(bindings.len(), PARTITIONED_BINDINGS.len());
        assert!(bindings.iter().any(|binding| {
            binding.path == crate::heor_partitioned_survival::PARTITIONED_SURVIVAL_RESULT_PATH
        }));
        assert!(bindings.windows(2).all(|pair| pair[0].path <= pair[1].path));
    }

    #[test]
    fn release_match_requires_effective_gate_actor_and_all_bindings() {
        let audit = complete_audit();
        let reproducibility = crate::heor_reproducibility::ReproducibilityAudit {
            complete: true,
            release_companion_ready: true,
            status: "complete",
            package_id: "repro-1".into(),
            analysis_id: audit.analysis_id.clone(),
            package_sha256: "6".repeat(64),
            report_package_sha256: audit.report_package_sha256.clone(),
            runtime_matches: true,
            artifact_count: 10,
            execution_count: 3,
            source_count: 1,
            availability_count: 1,
            exhibit_count: 3,
            claim_count: 7,
            required_claim_count: 7,
            covered_claim_count: 7,
            errors: Vec::new(),
        };
        let event = crate::heor_approval::ApprovalEvent {
            schema_version: 2,
            sequence: 5,
            event_id: "1".repeat(32),
            project_id: "project-1".into(),
            gate: crate::heor_approval::ApprovalGate::Release,
            action: crate::heor_approval::ApprovalAction::Approve,
            artifact_sha256: audit.report_package_sha256.clone(),
            related_artifacts: release_approval_bindings(&audit, &reproducibility),
            actor_label: audit.release_owner_label.clone(),
            rationale: "Reviewed complete report".into(),
            timestamp: 1,
            assurance: "local_human_assertion".into(),
            previous_hash: None,
            event_hash: "f".repeat(64),
        };
        let mut log = crate::heor_approval::ApprovalLog {
            events: vec![event],
            effective_approved_gates: vec![crate::heor_approval::ApprovalGate::Release],
            chain_head: None,
            integrity: "verified_unanchored_sha256_chain",
            identity_assurance: "local_human_assertion",
        };
        assert!(release_matches_approval(&log, &audit, &reproducibility));
        log.effective_approved_gates.clear();
        assert!(!release_matches_approval(&log, &audit, &reproducibility));
        log.effective_approved_gates
            .push(crate::heor_approval::ApprovalGate::Release);
        log.events[0].actor_label = "Another owner".into();
        assert!(!release_matches_approval(&log, &audit, &reproducibility));
        log.events[0].actor_label = audit.release_owner_label.clone();
        log.events[0].related_artifacts.retain(|binding| {
            binding.path != crate::heor_reproducibility::REPRODUCIBILITY_PACKAGE_PATH
        });
        assert!(!release_matches_approval(&log, &audit, &reproducibility));
    }
}
