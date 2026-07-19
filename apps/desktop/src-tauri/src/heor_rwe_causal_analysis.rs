//! Native point replay and app-owned Human method review for bounded RWE IPTW.
//!
//! The portable Python evaluator replays every deterministic bootstrap refit.
//! This module independently re-reads the cohort and request, refits the fixed
//! treatment and observation models, and verifies point effects, balance,
//! overlap, weights, and artifact bindings. It does not replay bootstrap
//! uncertainty.

use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::io::{Read, Write};
use std::path::{Component, Path, PathBuf};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager};

const REQUEST_PATH: &str = "heor/rwe-causal-analysis-request.json";
const REQUEST_SCHEMA: &str = "0.2.0";
const RESULT_SCHEMA: &str = "0.2.0";
const REVIEW_SCHEMA: &str = "0.2.0";
const REVIEW_EVENT_SCHEMA: u32 = 1;
const REVIEW_ASSURANCE: &str = "app_owned_local_human_assertion";
const EVALUATOR: &str = "ai4heor-rwe-causal@0.2.0";
const TOLERANCE: f64 = 1e-8;
const PROPENSITY_BOUNDARY: f64 = 1e-12;
const MAX_JSON_BYTES: u64 = 16 * 1024 * 1024;
const MAX_SOURCE_BYTES: u64 = 64 * 1024 * 1024;
const MAX_ROWS: usize = 5_000;
const MAX_CONFOUNDERS: usize = 12;
const EVALUATOR_BYTES: &[u8] = include_bytes!(
    "../../../../runtime/skills/core/heor-rwe-causal-analysis/scripts/rwe_causal_contract.py"
);
const REVIEW_CHECKS: [&str; 8] = [
    "target_trial_estimand_time_zero",
    "data_provenance_eligibility_new_user_active_comparator",
    "confounder_causal_rationale_measurement",
    "missingness_follow_up_outcome_integrity",
    "propensity_overlap_weights_positivity",
    "balance_model_diagnostics",
    "bootstrap_precision_failures",
    "residual_bias_transportability_downstream",
];

#[derive(Default)]
pub struct RweCausalAnalysisReviewState(pub Mutex<()>);

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RweCausalAnalysisAudit {
    pub complete: bool,
    pub reviewable: bool,
    pub status: String,
    pub execution_id: String,
    pub request_path: String,
    pub request_sha256: Option<String>,
    pub result_path: String,
    pub result_sha256: Option<String>,
    pub row_count: usize,
    pub observed_outcome_count: usize,
    pub follow_up_rate: Option<f64>,
    pub confounder_count: usize,
    pub estimand: String,
    pub ess_overall: Option<f64>,
    pub ess_ratio: Option<f64>,
    pub maximum_weight: Option<f64>,
    pub maximum_observation_weight: Option<f64>,
    pub max_abs_pre_smd: Option<f64>,
    pub max_abs_post_smd: Option<f64>,
    pub unadjusted_risk_difference: Option<f64>,
    pub weighted_risk_difference: Option<f64>,
    pub weighted_standard_error: Option<f64>,
    pub weighted_lower: Option<f64>,
    pub weighted_upper: Option<f64>,
    pub overlap_lower: Option<f64>,
    pub overlap_upper: Option<f64>,
    pub bootstrap_iterations: usize,
    pub bootstrap_failures: usize,
    pub native_scope: String,
    pub limitations: Vec<String>,
    pub errors: Vec<String>,
}

impl Default for RweCausalAnalysisAudit {
    fn default() -> Self {
        Self {
            complete: false,
            reviewable: false,
            status: "unavailable".into(),
            execution_id: String::new(),
            request_path: REQUEST_PATH.into(),
            request_sha256: None,
            result_path: String::new(),
            result_sha256: None,
            row_count: 0,
            observed_outcome_count: 0,
            follow_up_rate: None,
            confounder_count: 0,
            estimand: "source_cohort_ate_risk_difference_if_no_outcome_loss".into(),
            ess_overall: None,
            ess_ratio: None,
            maximum_weight: None,
            maximum_observation_weight: None,
            max_abs_pre_smd: None,
            max_abs_post_smd: None,
            unadjusted_risk_difference: None,
            weighted_risk_difference: None,
            weighted_standard_error: None,
            weighted_lower: None,
            weighted_upper: None,
            overlap_lower: None,
            overlap_upper: None,
            bootstrap_iterations: 0,
            bootstrap_failures: 0,
            native_scope: "point_estimate_and_diagnostics_only".into(),
            limitations: Vec::new(),
            errors: Vec::new(),
        }
    }
}

#[derive(Clone, Debug)]
struct SourceRow {
    treatment: bool,
    outcome_observed: bool,
    outcome: Option<f64>,
    confounders: Vec<f64>,
}

#[derive(Default)]
struct RequestFacts {
    execution_id: String,
    treatment_id: String,
    comparator_id: String,
    source_path: String,
    source_sha256: String,
    evidence_path: String,
    evidence_sha256: String,
    output_directory: String,
    confounder_ids: Vec<String>,
    confounder_columns: Vec<String>,
    confounder_types: Vec<String>,
    convergence_tolerance: f64,
    max_iterations: usize,
    observation_predictor_indices: Vec<usize>,
    observation_convergence_tolerance: f64,
    observation_max_iterations: usize,
    bootstrap_iterations: usize,
    bootstrap_seed: u64,
    rows: Vec<SourceRow>,
    limitations: Vec<String>,
}

#[derive(Debug)]
struct PropensityFit {
    coefficients: Vec<f64>,
    probabilities: Vec<f64>,
    standardization: Vec<(f64, f64)>,
    iterations: usize,
    log_likelihood: f64,
    marginal: f64,
}

#[derive(Debug)]
struct NativeAnalysis {
    coefficients: Vec<f64>,
    standardization: Vec<(f64, f64)>,
    iterations: usize,
    log_likelihood: f64,
    marginal: f64,
    observation_fit: PropensityFit,
    observation_arm_marginals: [f64; 2],
    weights: Vec<f64>,
    ess_overall: f64,
    maximum_weight: f64,
    maximum_observation_weight: f64,
    pre_balance: Vec<Balance>,
    treatment_balance: Vec<Balance>,
    combined_balance: Vec<Balance>,
    max_abs_pre_smd: f64,
    max_abs_treatment_smd: f64,
    max_abs_combined_smd: f64,
    overlap_lower: f64,
    overlap_upper: f64,
    overlap_exists: bool,
    unadjusted: Effect,
    weighted: Effect,
}

#[derive(Clone, Copy, Debug)]
struct Balance {
    treatment_mean: f64,
    comparator_mean: f64,
    pooled_sd: f64,
    smd: f64,
}

#[derive(Clone, Copy, Debug)]
struct Effect {
    treatment_risk: f64,
    comparator_risk: f64,
    risk_difference: f64,
    risk_ratio: Option<f64>,
    odds_ratio: Option<f64>,
}

fn exact(value: &serde_json::Value, fields: &[&str]) -> bool {
    value.as_object().is_some_and(|object| {
        object.len() == fields.len() && fields.iter().all(|field| object.contains_key(*field))
    })
}

fn text(value: Option<&serde_json::Value>) -> Option<&str> {
    value
        .and_then(serde_json::Value::as_str)
        .filter(|value| !value.is_empty() && *value == value.trim())
}

fn finite(value: Option<&serde_json::Value>) -> Option<f64> {
    value
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite())
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn is_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn safe_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 64
        && value
            .bytes()
            .next()
            .is_some_and(|byte| byte.is_ascii_lowercase())
        && value.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'-' | b'_')
        })
}

fn safe_subject(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .next()
            .is_some_and(|byte| byte.is_ascii_alphanumeric())
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'-' | b'_'))
}

fn read_capped(path: &Path, cap: u64, label: &str) -> Result<Vec<u8>, String> {
    let metadata =
        std::fs::metadata(path).map_err(|error| format!("{label} unavailable: {error}"))?;
    if metadata.len() > cap {
        return Err(format!("{label} exceeds the size cap"));
    }
    let mut file =
        std::fs::File::open(path).map_err(|error| format!("{label} unavailable: {error}"))?;
    let mut raw = Vec::with_capacity(metadata.len() as usize);
    file.read_to_end(&mut raw)
        .map_err(|error| format!("{label} unreadable: {error}"))?;
    Ok(raw)
}

fn resolve_file(workspace: &Path, relative: &str, label: &str) -> Result<PathBuf, String> {
    let relative_path = Path::new(relative);
    if relative_path.is_absolute()
        || relative_path
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err(format!("{label} path is unsafe"));
    }
    let root = workspace
        .canonicalize()
        .map_err(|error| format!("workspace unavailable: {error}"))?;
    let candidate = root.join(relative_path);
    if std::fs::symlink_metadata(&candidate).is_ok_and(|metadata| metadata.file_type().is_symlink())
    {
        return Err(format!("{label} must not be a symlink"));
    }
    let resolved = candidate
        .canonicalize()
        .map_err(|error| format!("{label} unavailable: {error}"))?;
    if !resolved.starts_with(&root) || !resolved.is_file() {
        return Err(format!("{label} escapes the workspace or is not a file"));
    }
    Ok(resolved)
}

fn bound_bytes(
    workspace: &Path,
    binding: &serde_json::Value,
    expected_path: Option<&str>,
    label: &str,
    cap: u64,
    errors: &mut Vec<String>,
) -> Option<(String, Vec<u8>)> {
    if !binding
        .as_object()
        .is_some_and(|object| object.contains_key("path") && object.contains_key("sha256"))
    {
        errors.push(format!("{label} binding fields are invalid"));
        return None;
    }
    let Some(path) = text(binding.get("path")) else {
        errors.push(format!("{label} path is invalid"));
        return None;
    };
    if expected_path.is_some_and(|expected| path != expected) {
        errors.push(format!("{label} path does not match the request"));
        return None;
    }
    let Some(expected_hash) = text(binding.get("sha256")).filter(|hash| is_sha256(hash)) else {
        errors.push(format!("{label} SHA-256 is invalid"));
        return None;
    };
    let resolved = match resolve_file(workspace, path, label) {
        Ok(path) => path,
        Err(error) => {
            errors.push(error);
            return None;
        }
    };
    let raw = match read_capped(&resolved, cap, label) {
        Ok(raw) => raw,
        Err(error) => {
            errors.push(error);
            return None;
        }
    };
    if sha256(&raw) != expected_hash {
        errors.push(format!("{label} SHA-256 does not match current bytes"));
        return None;
    }
    Some((path.into(), raw))
}

fn string_array(value: Option<&serde_json::Value>) -> Option<Vec<String>> {
    value?.as_array().and_then(|items| {
        items
            .iter()
            .map(|item| text(Some(item)).map(str::to_owned))
            .collect()
    })
}

fn parse_source(
    raw: &[u8],
    columns: &[String],
    treatment_id: &str,
    comparator_id: &str,
    confounder_types: &[String],
    errors: &mut Vec<String>,
) -> Vec<SourceRow> {
    let Ok(content) = std::str::from_utf8(raw) else {
        errors.push("RWE cohort CSV must be UTF-8".into());
        return Vec::new();
    };
    let mut lines = content.lines();
    if lines.next() != Some(columns.join(",").as_str()) {
        errors.push("RWE cohort CSV columns do not match the request".into());
        return Vec::new();
    }
    let mut subjects = HashSet::new();
    let mut rows = Vec::new();
    let mut arm_counts = [0usize; 2];
    let mut outcome_counts = [[0usize; 2]; 2];
    let mut observation_counts = [[0usize; 2]; 2];
    for (line_index, line) in lines.enumerate() {
        let cells: Vec<&str> = line.split(',').collect();
        if cells.len() != columns.len()
            || cells
                .iter()
                .enumerate()
                .any(|(index, cell)| cell.trim() != *cell || (index != 3 && cell.is_empty()))
        {
            errors.push(format!(
                "RWE cohort row {} violates the fixed CSV format",
                line_index + 2
            ));
            continue;
        }
        if !safe_subject(cells[0]) || !subjects.insert(cells[0].to_string()) {
            errors.push(format!(
                "RWE cohort row {} has an unsafe or duplicate subject",
                line_index + 2
            ));
        }
        let arm = if cells[1] == treatment_id {
            1usize
        } else if cells[1] == comparator_id {
            0usize
        } else {
            errors.push(format!(
                "RWE cohort row {} treatment is outside the two strategies",
                line_index + 2
            ));
            continue;
        };
        let Ok(observation) = cells[2].parse::<f64>() else {
            errors.push(format!(
                "RWE cohort row {} observation indicator is not numeric",
                line_index + 2
            ));
            continue;
        };
        if !matches!(observation, 0.0 | 1.0) {
            errors.push(format!(
                "RWE cohort row {} observation indicator is not 0 or 1",
                line_index + 2
            ));
            continue;
        }
        let outcome_observed = observation == 1.0;
        let outcome = if outcome_observed {
            match cells[3].parse::<f64>() {
                Ok(value) if matches!(value, 0.0 | 1.0) => Some(value),
                _ => {
                    errors.push(format!(
                        "RWE cohort row {} observed outcome is not 0 or 1",
                        line_index + 2
                    ));
                    continue;
                }
            }
        } else if cells[3].is_empty() {
            None
        } else {
            errors.push(format!(
                "RWE cohort row {} outcome must be blank when not observed",
                line_index + 2
            ));
            continue;
        };
        let confounders: Result<Vec<f64>, _> = cells[4..]
            .iter()
            .map(|value| value.parse::<f64>())
            .collect();
        let Ok(confounders) = confounders else {
            errors.push(format!(
                "RWE cohort row {} confounder is not numeric",
                line_index + 2
            ));
            continue;
        };
        if confounders.len() != confounder_types.len()
            || confounders
                .iter()
                .any(|value| !value.is_finite() || value.abs() > 1e12)
        {
            errors.push(format!(
                "RWE cohort row {} has unsafe confounders",
                line_index + 2
            ));
            continue;
        }
        if confounders
            .iter()
            .zip(confounder_types)
            .any(|(value, kind)| kind == "binary" && !matches!(value, 0.0 | 1.0))
        {
            errors.push(format!(
                "RWE cohort row {} has a nonbinary binary confounder",
                line_index + 2
            ));
            continue;
        }
        arm_counts[arm] += 1;
        observation_counts[arm][outcome_observed as usize] += 1;
        if let Some(outcome) = outcome {
            outcome_counts[arm][outcome as usize] += 1;
        }
        rows.push(SourceRow {
            treatment: arm == 1,
            outcome_observed,
            outcome,
            confounders,
        });
        if rows.len() > MAX_ROWS {
            errors.push("RWE cohort exceeds 5,000 rows".into());
            break;
        }
    }
    for (arm, count) in arm_counts.iter().enumerate() {
        if *count < 20 {
            errors.push(format!("RWE cohort arm {arm} has fewer than 20 rows"));
        }
        if observation_counts[arm][0] < 2 || observation_counts[arm][1] < 2 {
            errors.push(format!(
                "RWE cohort arm {arm} lacks two observed or not-observed outcomes"
            ));
        }
        if outcome_counts[arm][0] < 2 || outcome_counts[arm][1] < 2 {
            errors.push(format!(
                "RWE cohort arm {arm} lacks two events or non-events"
            ));
        }
    }
    rows
}

fn validate_request(
    workspace: &Path,
    request: &serde_json::Value,
    errors: &mut Vec<String>,
) -> RequestFacts {
    let mut facts = RequestFacts::default();
    if !exact(
        request,
        &[
            "schema_version",
            "execution_id",
            "status",
            "target_trial",
            "estimand",
            "evidence_synthesis",
            "source_data",
            "confounders",
            "propensity_score",
            "observation_model",
            "weighting",
            "diagnostics",
            "uncertainty",
            "output",
            "human_authorization",
            "limitations",
            "human_gate",
        ],
    ) {
        errors.push("RWE request fields are not the exact schema 0.2.0 contract".into());
        return facts;
    }
    if text(request.get("schema_version")) != Some(REQUEST_SCHEMA)
        || text(request.get("status")) != Some("ready_for_execution")
    {
        errors.push("RWE request schema or status is invalid".into());
    }
    facts.execution_id = text(request.get("execution_id")).unwrap_or_default().into();
    if !safe_id(&facts.execution_id) {
        errors.push("RWE execution_id is invalid".into());
    }
    let target = &request["target_trial"];
    if !exact(
        target,
        &[
            "design",
            "population",
            "eligibility_criteria",
            "treatment_strategy",
            "comparator_strategy",
            "assignment",
            "time_zero",
            "follow_up",
            "outcome",
            "causal_contrast",
        ],
    ) || text(target.get("design")) != Some("active_comparator_new_user_observational_cohort")
        || text(target.get("assignment")) != Some("observational_at_baseline")
        || text(target.get("causal_contrast")) != Some("intention_to_treat_analog")
    {
        errors.push("RWE target trial contract is invalid".into());
    }
    facts.treatment_id = text(target.pointer("/treatment_strategy/id"))
        .unwrap_or_default()
        .into();
    facts.comparator_id = text(target.pointer("/comparator_strategy/id"))
        .unwrap_or_default()
        .into();
    if !safe_id(&facts.treatment_id)
        || !safe_id(&facts.comparator_id)
        || facts.treatment_id == facts.comparator_id
    {
        errors.push("RWE treatment strategy IDs are invalid".into());
    }
    if request["estimand"]
        != serde_json::json!({
            "population": "analyzed_source_cohort",
            "treatment_contrast": "treatment_vs_comparator",
            "measure": "risk_difference",
            "favorable_direction": request["estimand"]["favorable_direction"],
        })
        || !matches!(
            text(request["estimand"].get("favorable_direction")),
            Some("higher" | "lower")
        )
    {
        errors.push("RWE estimand is not the fixed source-cohort ATE risk difference".into());
    }
    let confounders = request["confounders"].as_array();
    let mut observation_role_ids = HashSet::new();
    if !confounders.is_some_and(|items| !items.is_empty() && items.len() <= MAX_CONFOUNDERS) {
        errors.push("RWE confounders must contain 1 to 12 variables".into());
    } else if let Some(confounders) = confounders {
        let mut ids = HashSet::new();
        let mut columns = HashSet::new();
        for (index, item) in confounders.iter().enumerate() {
            if !exact(
                item,
                &[
                    "id",
                    "column",
                    "label",
                    "type",
                    "timing",
                    "roles",
                    "rationale",
                    "evidence_record_ids",
                ],
            ) {
                errors.push(format!("RWE confounder {index} fields are invalid"));
                continue;
            }
            let id = text(item.get("id")).unwrap_or_default();
            let column = text(item.get("column")).unwrap_or_default();
            let kind = text(item.get("type")).unwrap_or_default();
            let roles = string_array(item.get("roles")).unwrap_or_default();
            if !safe_id(id)
                || !safe_id(column)
                || !matches!(kind, "binary" | "continuous")
                || text(item.get("timing")) != Some("baseline_pre_treatment")
                || !roles
                    .iter()
                    .any(|role| role == "treatment_outcome_common_cause")
                || roles.iter().any(|role| {
                    !matches!(
                        role.as_str(),
                        "treatment_outcome_common_cause" | "observation_outcome_common_cause"
                    )
                })
                || !ids.insert(id.to_string())
                || !columns.insert(column.to_string())
            {
                errors.push(format!("RWE confounder {index} is invalid or duplicated"));
            }
            if roles
                .iter()
                .any(|role| role == "observation_outcome_common_cause")
            {
                observation_role_ids.insert(id.to_string());
            }
            facts.confounder_ids.push(id.into());
            facts.confounder_columns.push(column.into());
            facts.confounder_types.push(kind.into());
        }
    }
    let evidence = &request["evidence_synthesis"];
    if let Some((path, raw)) = bound_bytes(
        workspace,
        evidence,
        None,
        "RWE evidence synthesis",
        MAX_JSON_BYTES,
        errors,
    ) {
        facts.evidence_path = path;
        facts.evidence_sha256 = sha256(&raw);
        if serde_json::from_slice::<serde_json::Value>(&raw).is_err() {
            errors.push("RWE evidence synthesis is invalid JSON".into());
        }
    }
    let source = &request["source_data"];
    if !exact(
        source,
        &[
            "classification",
            "execution_boundary",
            "format",
            "path",
            "sha256",
            "columns",
            "row_count",
            "contains_direct_identifiers",
            "missing_policy",
            "one_row_per_person",
            "baseline_covariates_only",
            "fixed_horizon_outcome",
            "outcome_observation",
            "treatment_assignment",
        ],
    ) || !matches!(
        text(source.get("classification")),
        Some("restricted" | "confidential")
    ) || text(source.get("execution_boundary")) != Some("local_only")
        || text(source.get("format")) != Some("one_row_per_person_csv")
        || source
            .get("contains_direct_identifiers")
            .and_then(|value| value.as_bool())
            != Some(false)
        || text(source.get("missing_policy")) != Some("outcome_blank_only_when_not_observed")
        || source
            .get("one_row_per_person")
            .and_then(|value| value.as_bool())
            != Some(true)
        || source
            .get("baseline_covariates_only")
            .and_then(|value| value.as_bool())
            != Some(true)
        || source
            .get("fixed_horizon_outcome")
            .and_then(|value| value.as_bool())
            != Some(true)
        || source["outcome_observation"]
            != serde_json::json!({
                "indicator_column": "outcome_observed",
                "observed_value": 1,
                "not_observed_value": 0,
            })
        || text(source.get("treatment_assignment"))
            != Some("observational_active_comparator_new_user")
    {
        errors.push("RWE source_data contract is invalid".into());
    }
    let expected_columns = [
        vec![
            "subject_id".into(),
            "treatment".into(),
            "outcome_observed".into(),
            "outcome".into(),
        ],
        facts.confounder_columns.clone(),
    ]
    .concat();
    let columns = string_array(source.get("columns")).unwrap_or_default();
    if columns != expected_columns {
        errors.push("RWE source_data columns are invalid".into());
    }
    if let Some((path, raw)) = bound_bytes(
        workspace,
        source,
        text(source.get("path")),
        "RWE cohort",
        MAX_SOURCE_BYTES,
        errors,
    ) {
        facts.source_path = path;
        facts.source_sha256 = sha256(&raw);
        facts.rows = parse_source(
            &raw,
            &columns,
            &facts.treatment_id,
            &facts.comparator_id,
            &facts.confounder_types,
            errors,
        );
        if source.get("row_count").and_then(|value| value.as_u64()) != Some(facts.rows.len() as u64)
        {
            errors.push("RWE source_data row_count does not match parsed rows".into());
        }
    }
    let propensity = &request["propensity_score"];
    if !exact(
        propensity,
        &[
            "model",
            "treatment_encoding",
            "intercept",
            "continuous_standardization",
            "nonlinear_terms",
            "interactions",
            "penalty",
            "convergence_tolerance",
            "max_iterations",
        ],
    ) || text(propensity.get("model")) != Some("logistic_regression_main_effects")
        || text(propensity.get("treatment_encoding")) != Some("treatment_strategy_id_is_one")
        || propensity
            .get("intercept")
            .and_then(|value| value.as_bool())
            != Some(true)
        || text(propensity.get("continuous_standardization"))
            != Some("sample_mean_standard_deviation")
        || text(propensity.get("nonlinear_terms")) != Some("none")
        || text(propensity.get("interactions")) != Some("none")
        || text(propensity.get("penalty")) != Some("none")
    {
        errors.push("RWE propensity model contract is invalid".into());
    }
    facts.convergence_tolerance = finite(propensity.get("convergence_tolerance")).unwrap_or(0.0);
    facts.max_iterations = propensity
        .get("max_iterations")
        .and_then(|value| value.as_u64())
        .unwrap_or_default() as usize;
    if !(1e-12..=1e-8).contains(&facts.convergence_tolerance)
        || !(20..=500).contains(&facts.max_iterations)
    {
        errors.push("RWE propensity convergence settings are invalid".into());
    }
    let observation = &request["observation_model"];
    if !exact(
        observation,
        &[
            "model",
            "response_encoding",
            "predictor_ids",
            "includes_treatment",
            "intercept",
            "continuous_standardization",
            "nonlinear_terms",
            "interactions",
            "penalty",
            "convergence_tolerance",
            "max_iterations",
        ],
    ) || text(observation.get("model")) != Some("logistic_regression_main_effects")
        || text(observation.get("response_encoding")) != Some("outcome_observed_is_one")
        || observation
            .get("includes_treatment")
            .and_then(|value| value.as_bool())
            != Some(true)
        || observation
            .get("intercept")
            .and_then(|value| value.as_bool())
            != Some(true)
        || text(observation.get("continuous_standardization"))
            != Some("sample_mean_standard_deviation")
        || text(observation.get("nonlinear_terms")) != Some("none")
        || text(observation.get("interactions")) != Some("none")
        || text(observation.get("penalty")) != Some("none")
    {
        errors.push("RWE observation model contract is invalid".into());
    }
    let predictor_ids = string_array(observation.get("predictor_ids")).unwrap_or_default();
    let mut predictor_seen = HashSet::new();
    for predictor_id in predictor_ids {
        let Some(index) = facts
            .confounder_ids
            .iter()
            .position(|candidate| candidate == &predictor_id)
        else {
            errors.push("RWE observation predictor is not a declared confounder".into());
            continue;
        };
        if !predictor_seen.insert(predictor_id.clone())
            || !observation_role_ids.contains(&predictor_id)
        {
            errors.push("RWE observation predictor lacks a unique Human-prespecified observation-outcome role".into());
        }
        facts.observation_predictor_indices.push(index);
    }
    if facts.observation_predictor_indices.is_empty() {
        errors.push("RWE observation model requires at least one predictor".into());
    }
    facts.observation_convergence_tolerance =
        finite(observation.get("convergence_tolerance")).unwrap_or(0.0);
    facts.observation_max_iterations = observation
        .get("max_iterations")
        .and_then(|value| value.as_u64())
        .unwrap_or_default() as usize;
    if !(1e-12..=1e-8).contains(&facts.observation_convergence_tolerance)
        || !(20..=500).contains(&facts.observation_max_iterations)
    {
        errors.push("RWE observation-model convergence settings are invalid".into());
    }
    if request["weighting"]
        != serde_json::json!({
            "estimand": "source_cohort_ate",
            "method": "stabilized_inverse_probability_of_treatment_and_observation_weighting",
            "treatment_numerator": "marginal_treatment_probability",
            "observation_numerator": "treatment_arm_observation_probability",
            "outcome_rows": "observed_only",
            "trimming": "none",
            "weight_cap": "none",
            "renormalization": "none",
        })
    {
        errors.push("RWE weighting contract is invalid".into());
    }
    if request["diagnostics"]
        != serde_json::json!({
            "balance_metric": "standardized_mean_difference",
            "balance_denominator": "state_specific_two_arm_pooled_standard_deviation",
            "overlap": "empirical_propensity_range_intersection",
            "automatic_acceptance_thresholds": "none",
        })
    {
        errors.push("RWE diagnostics contract is invalid".into());
    }
    let uncertainty = &request["uncertainty"];
    if !exact(
        uncertainty,
        &[
            "method",
            "iterations",
            "seed",
            "prng",
            "interval",
            "failure_policy",
        ],
    ) || text(uncertainty.get("method")) != Some("arm_stratified_nonparametric_bootstrap_refit")
        || uncertainty["prng"] != serde_json::json!({"algorithm": "pcg32-xsh-rr", "version": "1"})
        || text(uncertainty.get("interval")) != Some("normal_bootstrap_95_percent")
        || text(uncertainty.get("failure_policy")) != Some("retain_and_block_review")
    {
        errors.push("RWE uncertainty contract is invalid".into());
    }
    facts.bootstrap_iterations = uncertainty
        .get("iterations")
        .and_then(|value| value.as_u64())
        .unwrap_or_default() as usize;
    facts.bootstrap_seed = uncertainty
        .get("seed")
        .and_then(|value| value.as_u64())
        .unwrap_or_default();
    if !(1_000..=5_000).contains(&facts.bootstrap_iterations) {
        errors.push("RWE bootstrap iteration count is invalid".into());
    }
    facts.output_directory = text(request.pointer("/output/directory"))
        .unwrap_or_default()
        .into();
    if facts.output_directory != format!("heor/rwe-causal-analysis-runs/{}", facts.execution_id) {
        errors.push("RWE output directory is invalid".into());
    }
    if text(request.pointer("/human_authorization/scope"))
        != Some("execute_local_rwe_causal_analysis")
    {
        errors.push("RWE Human authorization scope is invalid".into());
    }
    facts.limitations = string_array(request.get("limitations")).unwrap_or_default();
    if facts.limitations.is_empty() {
        errors.push("RWE limitations are missing".into());
    }
    if text(request.pointer("/human_gate/status")) != Some("awaiting_method_review")
        || string_array(request.pointer("/human_gate/required_checks"))
            != Some(REVIEW_CHECKS.iter().map(|value| (*value).into()).collect())
    {
        errors.push("RWE Human gate is invalid".into());
    }
    facts
}

fn mean(values: &[f64]) -> Result<f64, String> {
    if values.is_empty() {
        return Err("mean requires data".into());
    }
    Ok(values.iter().sum::<f64>() / values.len() as f64)
}

fn sample_variance(values: &[f64]) -> Result<f64, String> {
    if values.len() < 2 {
        return Err("sample variance requires two values".into());
    }
    let center = mean(values)?;
    Ok(values
        .iter()
        .map(|value| (value - center).powi(2))
        .sum::<f64>()
        / (values.len() - 1) as f64)
}

fn solve(mut matrix: Vec<Vec<f64>>, mut vector: Vec<f64>) -> Result<Vec<f64>, String> {
    let size = vector.len();
    for column in 0..size {
        let pivot = (column..size)
            .max_by(|left, right| {
                matrix[*left][column]
                    .abs()
                    .total_cmp(&matrix[*right][column].abs())
            })
            .unwrap_or(column);
        if matrix[pivot][column].abs() < 1e-14 {
            return Err("propensity information matrix is singular".into());
        }
        matrix.swap(column, pivot);
        vector.swap(column, pivot);
        let scale = matrix[column][column];
        for value in &mut matrix[column][column..] {
            *value /= scale;
        }
        vector[column] /= scale;
        let pivot_tail = matrix[column][column..].to_vec();
        for row in 0..size {
            if row == column {
                continue;
            }
            let factor = matrix[row][column];
            for (value, pivot_value) in matrix[row][column..].iter_mut().zip(&pivot_tail) {
                *value -= factor * pivot_value;
            }
            vector[row] -= factor * vector[column];
        }
    }
    if vector.iter().any(|value| !value.is_finite()) {
        return Err("propensity linear solve is non-finite".into());
    }
    Ok(vector)
}

fn sigmoid(value: f64) -> f64 {
    if value >= 0.0 {
        let inverse = (-value).exp();
        1.0 / (1.0 + inverse)
    } else {
        let direct = value.exp();
        direct / (1.0 + direct)
    }
}

fn softplus(value: f64) -> f64 {
    if value > 0.0 {
        value + (-value).exp().ln_1p()
    } else {
        value.exp().ln_1p()
    }
}

fn log_likelihood(design: &[Vec<f64>], observed: &[f64], beta: &[f64]) -> f64 {
    design
        .iter()
        .zip(observed)
        .map(|(row, outcome)| {
            let eta = row
                .iter()
                .zip(beta)
                .map(|(value, coefficient)| value * coefficient)
                .sum::<f64>();
            outcome * eta - softplus(eta)
        })
        .sum()
}

fn fit_propensity(facts: &RequestFacts) -> Result<PropensityFit, String> {
    let mut design = vec![vec![1.0]; facts.rows.len()];
    let mut standardization = Vec::new();
    for (index, kind) in facts.confounder_types.iter().enumerate() {
        let values: Vec<f64> = facts
            .rows
            .iter()
            .map(|row| row.confounders[index])
            .collect();
        let (center, scale) = if kind == "continuous" {
            let center = mean(&values)?;
            let variance = sample_variance(&values)?;
            if !variance.is_finite() || variance <= 1e-14 {
                return Err(format!(
                    "continuous confounder {index} has no usable variation"
                ));
            }
            (center, variance.sqrt())
        } else {
            if values.iter().any(|value| !matches!(value, 0.0 | 1.0))
                || values.iter().all(|value| *value == values[0])
            {
                return Err(format!("binary confounder {index} has invalid variation"));
            }
            (0.0, 1.0)
        };
        for (row, value) in design.iter_mut().zip(values) {
            row.push((value - center) / scale);
        }
        standardization.push((center, scale));
    }
    let observed: Vec<f64> = facts
        .rows
        .iter()
        .map(|row| if row.treatment { 1.0 } else { 0.0 })
        .collect();
    let marginal = observed.iter().sum::<f64>() / observed.len() as f64;
    if !(0.0..1.0).contains(&marginal) || marginal == 0.0 {
        return Err("both treatment strategies must be present".into());
    }
    let mut beta = vec![0.0; design[0].len()];
    beta[0] = (marginal / (1.0 - marginal)).ln();
    let mut converged = None;
    for iteration in 0..=facts.max_iterations {
        let probabilities: Vec<f64> = design
            .iter()
            .map(|row| {
                sigmoid(
                    row.iter()
                        .zip(&beta)
                        .map(|(value, coefficient)| value * coefficient)
                        .sum(),
                )
            })
            .collect();
        let gradient: Vec<f64> = (0..beta.len())
            .map(|column| {
                design
                    .iter()
                    .zip(&observed)
                    .zip(&probabilities)
                    .map(|((row, outcome), probability)| row[column] * (outcome - probability))
                    .sum()
            })
            .collect();
        if gradient.iter().map(|value| value.abs()).fold(0.0, f64::max) / facts.rows.len() as f64
            <= facts.convergence_tolerance
        {
            converged = Some(iteration);
            break;
        }
        if iteration == facts.max_iterations {
            return Err("propensity model did not converge".into());
        }
        let information: Vec<Vec<f64>> = (0..beta.len())
            .map(|left| {
                (0..beta.len())
                    .map(|right| {
                        design
                            .iter()
                            .zip(&probabilities)
                            .map(|(row, probability)| {
                                row[left] * row[right] * probability * (1.0 - probability)
                            })
                            .sum()
                    })
                    .collect()
            })
            .collect();
        let delta = solve(information, gradient)?;
        let current = log_likelihood(&design, &observed, &beta);
        let mut accepted = false;
        let mut step = 1.0;
        for _ in 0..50 {
            let candidate: Vec<f64> = beta
                .iter()
                .zip(&delta)
                .map(|(value, change)| value + step * change)
                .collect();
            let likelihood = log_likelihood(&design, &observed, &candidate);
            if likelihood.is_finite() && likelihood >= current - 1e-12 {
                beta = candidate;
                accepted = true;
                break;
            }
            step *= 0.5;
        }
        if !accepted {
            return Err("propensity line search failed".into());
        }
    }
    let probabilities: Vec<f64> = design
        .iter()
        .map(|row| {
            sigmoid(
                row.iter()
                    .zip(&beta)
                    .map(|(value, coefficient)| value * coefficient)
                    .sum(),
            )
        })
        .collect();
    if probabilities.iter().any(|value| {
        !value.is_finite() || *value <= PROPENSITY_BOUNDARY || *value >= 1.0 - PROPENSITY_BOUNDARY
    }) {
        return Err("propensity reached the computational positivity boundary".into());
    }
    let likelihood = log_likelihood(&design, &observed, &beta);
    Ok(PropensityFit {
        coefficients: beta,
        probabilities,
        standardization,
        iterations: converged.unwrap_or_default(),
        log_likelihood: likelihood,
        marginal,
    })
}

fn fit_observation(facts: &RequestFacts) -> Result<(PropensityFit, [f64; 2]), String> {
    let mut design: Vec<Vec<f64>> = facts
        .rows
        .iter()
        .map(|row| vec![1.0, if row.treatment { 1.0 } else { 0.0 }])
        .collect();
    let mut standardization = Vec::new();
    for index in &facts.observation_predictor_indices {
        let values: Vec<f64> = facts
            .rows
            .iter()
            .map(|row| row.confounders[*index])
            .collect();
        let (center, scale) = if facts.confounder_types[*index] == "continuous" {
            let center = mean(&values)?;
            let variance = sample_variance(&values)?;
            if !variance.is_finite() || variance <= 1e-14 {
                return Err(format!(
                    "observation predictor {index} has no usable variation"
                ));
            }
            (center, variance.sqrt())
        } else {
            if values.iter().any(|value| !matches!(value, 0.0 | 1.0))
                || values.iter().all(|value| *value == values[0])
            {
                return Err(format!(
                    "observation predictor {index} has invalid variation"
                ));
            }
            (0.0, 1.0)
        };
        for (row, value) in design.iter_mut().zip(values) {
            row.push((value - center) / scale);
        }
        standardization.push((center, scale));
    }
    let observed: Vec<f64> = facts
        .rows
        .iter()
        .map(|row| if row.outcome_observed { 1.0 } else { 0.0 })
        .collect();
    let marginal = observed.iter().sum::<f64>() / observed.len() as f64;
    if !(0.0..1.0).contains(&marginal) || marginal == 0.0 {
        return Err("observation model requires observed and not-observed outcomes".into());
    }
    let mut beta = vec![0.0; design[0].len()];
    beta[0] = (marginal / (1.0 - marginal)).ln();
    let mut converged = None;
    for iteration in 0..=facts.observation_max_iterations {
        let probabilities: Vec<f64> = design
            .iter()
            .map(|row| {
                sigmoid(
                    row.iter()
                        .zip(&beta)
                        .map(|(value, coefficient)| value * coefficient)
                        .sum(),
                )
            })
            .collect();
        let gradient: Vec<f64> = (0..beta.len())
            .map(|column| {
                design
                    .iter()
                    .zip(&observed)
                    .zip(&probabilities)
                    .map(|((row, outcome), probability)| row[column] * (outcome - probability))
                    .sum()
            })
            .collect();
        if gradient.iter().map(|value| value.abs()).fold(0.0, f64::max) / facts.rows.len() as f64
            <= facts.observation_convergence_tolerance
        {
            converged = Some(iteration);
            break;
        }
        if iteration == facts.observation_max_iterations {
            return Err("observation model did not converge".into());
        }
        let information: Vec<Vec<f64>> = (0..beta.len())
            .map(|left| {
                (0..beta.len())
                    .map(|right| {
                        design
                            .iter()
                            .zip(&probabilities)
                            .map(|(row, probability)| {
                                row[left] * row[right] * probability * (1.0 - probability)
                            })
                            .sum()
                    })
                    .collect()
            })
            .collect();
        let delta = solve(information, gradient)?;
        let current = log_likelihood(&design, &observed, &beta);
        let mut accepted = false;
        let mut step = 1.0;
        for _ in 0..50 {
            let candidate: Vec<f64> = beta
                .iter()
                .zip(&delta)
                .map(|(value, change)| value + step * change)
                .collect();
            let likelihood = log_likelihood(&design, &observed, &candidate);
            if likelihood.is_finite() && likelihood >= current - 1e-12 {
                beta = candidate;
                accepted = true;
                break;
            }
            step *= 0.5;
        }
        if !accepted {
            return Err("observation-model line search failed".into());
        }
    }
    let probabilities: Vec<f64> = design
        .iter()
        .map(|row| {
            sigmoid(
                row.iter()
                    .zip(&beta)
                    .map(|(value, coefficient)| value * coefficient)
                    .sum(),
            )
        })
        .collect();
    if probabilities.iter().any(|value| {
        !value.is_finite() || *value <= PROPENSITY_BOUNDARY || *value >= 1.0 - PROPENSITY_BOUNDARY
    }) {
        return Err("observation probability reached the computational positivity boundary".into());
    }
    let mut arm_observed = [0usize; 2];
    let mut arm_total = [0usize; 2];
    for row in &facts.rows {
        let arm = row.treatment as usize;
        arm_total[arm] += 1;
        arm_observed[arm] += row.outcome_observed as usize;
    }
    let arm_marginals = [
        arm_observed[0] as f64 / arm_total[0] as f64,
        arm_observed[1] as f64 / arm_total[1] as f64,
    ];
    if arm_marginals
        .iter()
        .any(|value| !(*value > 0.0 && *value < 1.0))
    {
        return Err("each treatment arm requires observed and not-observed outcomes".into());
    }
    let likelihood = log_likelihood(&design, &observed, &beta);
    Ok((
        PropensityFit {
            coefficients: beta,
            probabilities,
            standardization,
            iterations: converged.unwrap_or_default(),
            log_likelihood: likelihood,
            marginal,
        },
        arm_marginals,
    ))
}

fn weighted_mean(values: &[f64], weights: &[f64]) -> Result<f64, String> {
    let total: f64 = weights.iter().sum();
    if !total.is_finite() || total <= 0.0 {
        return Err("weighted mean has no finite mass".into());
    }
    Ok(values
        .iter()
        .zip(weights)
        .map(|(value, weight)| value * weight)
        .sum::<f64>()
        / total)
}

fn weighted_variance(values: &[f64], weights: &[f64]) -> Result<f64, String> {
    let center = weighted_mean(values, weights)?;
    let total: f64 = weights.iter().sum();
    Ok(values
        .iter()
        .zip(weights)
        .map(|(value, weight)| weight * (value - center).powi(2))
        .sum::<f64>()
        / total)
}

fn balance(facts: &RequestFacts, weights: &[f64]) -> Result<Vec<Balance>, String> {
    let mut result = Vec::new();
    for index in 0..facts.confounder_ids.len() {
        let treatment_values: Vec<f64> = facts
            .rows
            .iter()
            .filter(|row| row.treatment)
            .map(|row| row.confounders[index])
            .collect();
        let comparator_values: Vec<f64> = facts
            .rows
            .iter()
            .filter(|row| !row.treatment)
            .map(|row| row.confounders[index])
            .collect();
        let treatment_weights: Vec<f64> = facts
            .rows
            .iter()
            .zip(weights)
            .filter(|(row, _)| row.treatment)
            .map(|(_, weight)| *weight)
            .collect();
        let comparator_weights: Vec<f64> = facts
            .rows
            .iter()
            .zip(weights)
            .filter(|(row, _)| !row.treatment)
            .map(|(_, weight)| *weight)
            .collect();
        let treatment_mean = weighted_mean(&treatment_values, &treatment_weights)?;
        let comparator_mean = weighted_mean(&comparator_values, &comparator_weights)?;
        let pooled_sd = ((weighted_variance(&treatment_values, &treatment_weights)?
            + weighted_variance(&comparator_values, &comparator_weights)?)
            / 2.0)
            .sqrt();
        if !pooled_sd.is_finite() || pooled_sd <= 1e-14 {
            return Err(format!("confounder {index} has a zero SMD denominator"));
        }
        result.push(Balance {
            treatment_mean,
            comparator_mean,
            pooled_sd,
            smd: (treatment_mean - comparator_mean) / pooled_sd,
        });
    }
    Ok(result)
}

fn effect(facts: &RequestFacts, weights: &[f64]) -> Result<Effect, String> {
    let treatment_pairs: Vec<(f64, f64)> = facts
        .rows
        .iter()
        .zip(weights)
        .filter_map(|(row, weight)| {
            (row.treatment && *weight > 0.0)
                .then(|| row.outcome.map(|value| (value, *weight)))
                .flatten()
        })
        .collect();
    let comparator_pairs: Vec<(f64, f64)> = facts
        .rows
        .iter()
        .zip(weights)
        .filter_map(|(row, weight)| {
            (!row.treatment && *weight > 0.0)
                .then(|| row.outcome.map(|value| (value, *weight)))
                .flatten()
        })
        .collect();
    let treatment_values: Vec<f64> = treatment_pairs.iter().map(|(value, _)| *value).collect();
    let comparator_values: Vec<f64> = comparator_pairs.iter().map(|(value, _)| *value).collect();
    let treatment_weights: Vec<f64> = treatment_pairs.iter().map(|(_, weight)| *weight).collect();
    let comparator_weights: Vec<f64> = comparator_pairs.iter().map(|(_, weight)| *weight).collect();
    let treatment_risk = weighted_mean(&treatment_values, &treatment_weights)?;
    let comparator_risk = weighted_mean(&comparator_values, &comparator_weights)?;
    Ok(Effect {
        treatment_risk,
        comparator_risk,
        risk_difference: treatment_risk - comparator_risk,
        risk_ratio: (comparator_risk > 0.0).then_some(treatment_risk / comparator_risk),
        odds_ratio: (0.0 < treatment_risk
            && treatment_risk < 1.0
            && 0.0 < comparator_risk
            && comparator_risk < 1.0)
            .then_some(
                (treatment_risk / (1.0 - treatment_risk))
                    / (comparator_risk / (1.0 - comparator_risk)),
            ),
    })
}

fn analyze(facts: &RequestFacts) -> Result<NativeAnalysis, String> {
    let fit = fit_propensity(facts)?;
    let treatment_weights: Vec<f64> = facts
        .rows
        .iter()
        .zip(&fit.probabilities)
        .map(|(row, probability)| {
            if row.treatment {
                fit.marginal / probability
            } else {
                (1.0 - fit.marginal) / (1.0 - probability)
            }
        })
        .collect();
    if treatment_weights
        .iter()
        .any(|value| !value.is_finite() || *value <= 0.0)
    {
        return Err("stabilized IPTW weights are invalid".into());
    }
    let (observation_fit, observation_arm_marginals) = fit_observation(facts)?;
    let observation_weights: Vec<f64> = facts
        .rows
        .iter()
        .zip(&observation_fit.probabilities)
        .map(|(row, probability)| {
            if row.outcome_observed {
                observation_arm_marginals[row.treatment as usize] / probability
            } else {
                0.0
            }
        })
        .collect();
    if observation_weights
        .iter()
        .any(|value| !value.is_finite() || *value < 0.0)
    {
        return Err("stabilized observation weights are invalid".into());
    }
    let weights: Vec<f64> = treatment_weights
        .iter()
        .zip(&observation_weights)
        .map(|(treatment, observation)| treatment * observation)
        .collect();
    let positive_observation_weights: Vec<f64> = observation_weights
        .iter()
        .copied()
        .filter(|value| *value > 0.0)
        .collect();
    let unit = vec![1.0; facts.rows.len()];
    let observed_unit: Vec<f64> = facts
        .rows
        .iter()
        .map(|row| if row.outcome_observed { 1.0 } else { 0.0 })
        .collect();
    let pre_balance = balance(facts, &unit)?;
    let treatment_balance = balance(facts, &treatment_weights)?;
    let combined_balance = balance(facts, &weights)?;
    let max_abs_pre_smd = pre_balance
        .iter()
        .map(|value| value.smd.abs())
        .fold(0.0, f64::max);
    let max_abs_treatment_smd = treatment_balance
        .iter()
        .map(|value| value.smd.abs())
        .fold(0.0, f64::max);
    let max_abs_combined_smd = combined_balance
        .iter()
        .map(|value| value.smd.abs())
        .fold(0.0, f64::max);
    let treatment_probabilities: Vec<f64> = facts
        .rows
        .iter()
        .zip(&fit.probabilities)
        .filter(|(row, _)| row.treatment)
        .map(|(_, value)| *value)
        .collect();
    let comparator_probabilities: Vec<f64> = facts
        .rows
        .iter()
        .zip(&fit.probabilities)
        .filter(|(row, _)| !row.treatment)
        .map(|(_, value)| *value)
        .collect();
    let overlap_lower = treatment_probabilities
        .iter()
        .copied()
        .fold(f64::INFINITY, f64::min)
        .max(
            comparator_probabilities
                .iter()
                .copied()
                .fold(f64::INFINITY, f64::min),
        );
    let overlap_upper = treatment_probabilities
        .iter()
        .copied()
        .fold(f64::NEG_INFINITY, f64::max)
        .min(
            comparator_probabilities
                .iter()
                .copied()
                .fold(f64::NEG_INFINITY, f64::max),
        );
    let positive_weights: Vec<f64> = weights
        .iter()
        .copied()
        .filter(|value| *value > 0.0)
        .collect();
    let weight_sum: f64 = positive_weights.iter().sum();
    let ess_overall = weight_sum.powi(2)
        / positive_weights
            .iter()
            .map(|value| value.powi(2))
            .sum::<f64>();
    let unadjusted = effect(facts, &observed_unit)?;
    let weighted = effect(facts, &weights)?;
    Ok(NativeAnalysis {
        coefficients: fit.coefficients,
        standardization: fit.standardization,
        iterations: fit.iterations,
        log_likelihood: fit.log_likelihood,
        marginal: fit.marginal,
        observation_fit,
        observation_arm_marginals,
        maximum_weight: positive_weights
            .iter()
            .copied()
            .fold(f64::NEG_INFINITY, f64::max),
        maximum_observation_weight: positive_observation_weights
            .iter()
            .copied()
            .fold(f64::NEG_INFINITY, f64::max),
        weights,
        ess_overall,
        pre_balance,
        treatment_balance,
        combined_balance,
        max_abs_pre_smd,
        max_abs_treatment_smd,
        max_abs_combined_smd,
        overlap_lower,
        overlap_upper,
        overlap_exists: overlap_upper >= overlap_lower,
        unadjusted,
        weighted,
    })
}

fn close(left: Option<f64>, right: f64) -> bool {
    left.is_some_and(|left| {
        (left - right).abs() <= TOLERANCE * left.abs().max(right.abs()).max(1.0)
    })
}

fn optional_close(value: Option<&serde_json::Value>, expected: Option<f64>) -> bool {
    match expected {
        Some(expected) => close(finite(value), expected),
        None => value.is_some_and(serde_json::Value::is_null),
    }
}

fn compare_effect(
    value: &serde_json::Value,
    expected: Effect,
    label: &str,
    errors: &mut Vec<String>,
) {
    if !exact(
        value,
        &[
            "treatment_risk",
            "comparator_risk",
            "risk_difference",
            "risk_ratio",
            "odds_ratio",
        ],
    ) || !close(finite(value.get("treatment_risk")), expected.treatment_risk)
        || !close(
            finite(value.get("comparator_risk")),
            expected.comparator_risk,
        )
        || !close(
            finite(value.get("risk_difference")),
            expected.risk_difference,
        )
        || !optional_close(value.get("risk_ratio"), expected.risk_ratio)
        || !optional_close(value.get("odds_ratio"), expected.odds_ratio)
    {
        errors.push(format!("RWE {label} differs from native point replay"));
    }
}

fn dedup_errors(errors: &mut Vec<String>) {
    let mut seen = HashSet::new();
    errors.retain(|error| seen.insert(error.clone()));
}

fn audit_path(workspace: &Path, result_path: &str) -> RweCausalAnalysisAudit {
    let mut audit = RweCausalAnalysisAudit {
        result_path: result_path.into(),
        ..RweCausalAnalysisAudit::default()
    };
    let mut request_value = serde_json::Value::Null;
    let mut facts = RequestFacts::default();
    let request_file = match resolve_file(workspace, REQUEST_PATH, "RWE request") {
        Ok(path) => path,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    let request_raw = match read_capped(&request_file, MAX_JSON_BYTES, "RWE request") {
        Ok(raw) => raw,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    audit.request_sha256 = Some(sha256(&request_raw));
    match serde_json::from_slice::<serde_json::Value>(&request_raw) {
        Ok(value) => {
            facts = validate_request(workspace, &value, &mut audit.errors);
            audit.execution_id = facts.execution_id.clone();
            audit.row_count = facts.rows.len();
            audit.observed_outcome_count =
                facts.rows.iter().filter(|row| row.outcome_observed).count();
            audit.follow_up_rate = (audit.row_count > 0)
                .then_some(audit.observed_outcome_count as f64 / audit.row_count as f64);
            audit.confounder_count = facts.confounder_ids.len();
            audit.limitations = facts.limitations.clone();
            request_value = value;
        }
        Err(error) => audit
            .errors
            .push(format!("RWE request is invalid JSON: {error}")),
    }
    let result_file = match resolve_file(workspace, result_path, "RWE result") {
        Ok(path) => path,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    let result_raw = match read_capped(&result_file, MAX_JSON_BYTES, "RWE result") {
        Ok(raw) => raw,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    audit.result_sha256 = Some(sha256(&result_raw));
    let result: serde_json::Value = match serde_json::from_slice(&result_raw) {
        Ok(value) => value,
        Err(error) => {
            audit
                .errors
                .push(format!("RWE result is invalid JSON: {error}"));
            return audit;
        }
    };
    if !exact(
        &result,
        &[
            "schema_version",
            "execution_id",
            "status",
            "request",
            "source_data",
            "evidence_synthesis",
            "runtime",
            "target_trial",
            "estimand",
            "propensity_score",
            "observation_model",
            "weighting",
            "diagnostics",
            "effects",
            "bootstrap",
            "cross_implementation",
            "warnings",
            "limitations",
            "human_gate",
        ],
    ) || text(result.get("schema_version")) != Some(RESULT_SCHEMA)
    {
        audit
            .errors
            .push("RWE result fields or schema are invalid".into());
    }
    audit.status = text(result.get("status")).unwrap_or("invalid").into();
    if text(result.get("execution_id")) != Some(facts.execution_id.as_str()) {
        audit
            .errors
            .push("RWE result execution_id does not match request".into());
    }
    if result["request"]
        != serde_json::json!({"path": REQUEST_PATH, "sha256": audit.request_sha256})
    {
        audit
            .errors
            .push("RWE result request binding is invalid".into());
    }
    if result["source_data"]
        != serde_json::json!({"path": facts.source_path, "sha256": facts.source_sha256})
        || result["evidence_synthesis"]
            != serde_json::json!({"path": facts.evidence_path, "sha256": facts.evidence_sha256})
    {
        audit
            .errors
            .push("RWE result source bindings are invalid".into());
    }
    if result["target_trial"] != request_value["target_trial"]
        || result["estimand"] != request_value["estimand"]
    {
        audit
            .errors
            .push("RWE result target trial or estimand changed".into());
    }
    let runtime = &result["runtime"];
    if text(runtime.get("evaluator")) != Some(EVALUATOR) {
        audit
            .errors
            .push("RWE evaluator identity is invalid".into());
    }
    if let Some((_, evaluator_raw)) = bound_bytes(
        workspace,
        &runtime["evaluator_source"],
        Some(&format!(
            "{}/engine/rwe_causal_contract.py",
            facts.output_directory
        )),
        "RWE evaluator source",
        MAX_JSON_BYTES,
        &mut audit.errors,
    ) {
        if evaluator_raw != EVALUATOR_BYTES {
            audit
                .errors
                .push("RWE evaluator source is not the bundled evaluator".into());
        }
    }
    let bootstrap = &result["bootstrap"];
    audit.bootstrap_iterations = bootstrap
        .get("iterations")
        .and_then(|value| value.as_u64())
        .unwrap_or_default() as usize;
    audit.bootstrap_failures = bootstrap
        .get("failed")
        .and_then(|value| value.as_u64())
        .unwrap_or_default() as usize;
    if audit.bootstrap_iterations != facts.bootstrap_iterations
        || bootstrap.get("seed").and_then(|value| value.as_u64()) != Some(facts.bootstrap_seed)
        || text(bootstrap.get("method")) != Some("arm_stratified_nonparametric_bootstrap_refit")
        || text(bootstrap.get("failure_policy")) != Some("retain_and_block_review")
    {
        audit.errors.push("RWE bootstrap summary is invalid".into());
    }
    let expected_draws = format!("{}/bootstrap-draws.csv", facts.output_directory);
    bound_bytes(
        workspace,
        &bootstrap["draws"],
        Some(&expected_draws),
        "RWE bootstrap draws",
        MAX_SOURCE_BYTES,
        &mut audit.errors,
    );
    match analyze(&facts) {
        Ok(native) => {
            let propensity = &result["propensity_score"];
            if text(propensity.get("model")) != Some("logistic_regression_main_effects")
                || propensity
                    .get("converged")
                    .and_then(|value| value.as_bool())
                    != Some(true)
                || propensity
                    .get("iterations")
                    .and_then(|value| value.as_u64())
                    != Some(native.iterations as u64)
                || !close(
                    finite(propensity.get("log_likelihood")),
                    native.log_likelihood,
                )
                || !close(
                    finite(propensity.get("marginal_treatment_probability")),
                    native.marginal,
                )
            {
                audit
                    .errors
                    .push("RWE propensity fit differs from native replay".into());
            }
            let coefficients = propensity
                .get("coefficients")
                .and_then(|value| value.as_array());
            if !coefficients.is_some_and(|values| {
                values.len() == native.coefficients.len()
                    && values
                        .iter()
                        .zip(&native.coefficients)
                        .all(|(value, expected)| close(finite(value.get("value")), *expected))
            }) {
                audit
                    .errors
                    .push("RWE propensity coefficients differ from native replay".into());
            }
            let standardization = propensity
                .get("standardization")
                .and_then(|value| value.as_array());
            if !standardization.is_some_and(|values| {
                values.len() == native.standardization.len()
                    && values
                        .iter()
                        .zip(&native.standardization)
                        .all(|(value, (center, scale))| {
                            close(finite(value.get("mean")), *center)
                                && close(finite(value.get("scale")), *scale)
                        })
            }) {
                audit
                    .errors
                    .push("RWE propensity standardization differs from native replay".into());
            }
            let observation = &result["observation_model"];
            if text(observation.get("model")) != Some("logistic_regression_main_effects")
                || observation
                    .get("converged")
                    .and_then(|value| value.as_bool())
                    != Some(true)
                || observation
                    .get("iterations")
                    .and_then(|value| value.as_u64())
                    != Some(native.observation_fit.iterations as u64)
                || !close(
                    finite(observation.get("log_likelihood")),
                    native.observation_fit.log_likelihood,
                )
                || !close(
                    finite(observation.get("marginal_observation_probability")),
                    native.observation_fit.marginal,
                )
                || !close(
                    finite(
                        observation.pointer("/treatment_arm_observation_probabilities/comparator"),
                    ),
                    native.observation_arm_marginals[0],
                )
                || !close(
                    finite(
                        observation.pointer("/treatment_arm_observation_probabilities/treatment"),
                    ),
                    native.observation_arm_marginals[1],
                )
            {
                audit
                    .errors
                    .push("RWE observation fit differs from native replay".into());
            }
            let observation_coefficients = observation
                .get("coefficients")
                .and_then(|value| value.as_array());
            if !observation_coefficients.is_some_and(|values| {
                values.len() == native.observation_fit.coefficients.len()
                    && values
                        .iter()
                        .zip(&native.observation_fit.coefficients)
                        .all(|(value, expected)| close(finite(value.get("value")), *expected))
            }) {
                audit
                    .errors
                    .push("RWE observation coefficients differ from native replay".into());
            }
            let observation_standardization = observation
                .get("standardization")
                .and_then(|value| value.as_array());
            if !observation_standardization.is_some_and(|values| {
                values.len() == native.observation_fit.standardization.len()
                    && values
                        .iter()
                        .zip(&native.observation_fit.standardization)
                        .all(|(value, (center, scale))| {
                            close(finite(value.get("mean")), *center)
                                && close(finite(value.get("scale")), *scale)
                        })
            }) {
                audit
                    .errors
                    .push("RWE observation standardization differs from native replay".into());
            }
            audit.ess_overall =
                finite(result.pointer("/weighting/effective_sample_size_observed/overall"));
            audit.ess_ratio = audit
                .ess_overall
                .filter(|_| audit.observed_outcome_count > 0)
                .map(|value| value / audit.observed_outcome_count as f64);
            audit.maximum_weight =
                finite(result.pointer("/weighting/combined_observed_rows/overall/maximum"));
            audit.maximum_observation_weight =
                finite(result.pointer("/weighting/observation_observed_rows/maximum"));
            if !close(audit.ess_overall, native.ess_overall)
                || !close(audit.maximum_weight, native.maximum_weight)
                || !close(
                    audit.maximum_observation_weight,
                    native.maximum_observation_weight,
                )
                || native.weights.len() != facts.rows.len()
            {
                audit
                    .errors
                    .push("RWE weight diagnostics differ from native replay".into());
            }
            audit.max_abs_pre_smd = finite(result.pointer("/diagnostics/max_abs_pre_smd"));
            let max_abs_treatment_smd =
                finite(result.pointer("/diagnostics/max_abs_treatment_weight_smd"));
            audit.max_abs_post_smd =
                finite(result.pointer("/diagnostics/max_abs_combined_observed_weight_smd"));
            if !close(audit.max_abs_pre_smd, native.max_abs_pre_smd)
                || !close(max_abs_treatment_smd, native.max_abs_treatment_smd)
                || !close(audit.max_abs_post_smd, native.max_abs_combined_smd)
            {
                audit
                    .errors
                    .push("RWE balance maxima differ from native replay".into());
            }
            if let Some(balance) = result
                .pointer("/diagnostics/balance")
                .and_then(|value| value.as_array())
            {
                if balance.len() != native.pre_balance.len()
                    || balance
                        .iter()
                        .zip(
                            native.pre_balance.iter().zip(
                                native
                                    .treatment_balance
                                    .iter()
                                    .zip(&native.combined_balance),
                            ),
                        )
                        .any(|(value, (pre, (treatment, combined)))| {
                            !close(
                                finite(value.pointer("/pre_weight/treatment_mean")),
                                pre.treatment_mean,
                            ) || !close(
                                finite(value.pointer("/pre_weight/comparator_mean")),
                                pre.comparator_mean,
                            ) || !close(
                                finite(value.pointer("/pre_weight/pooled_standard_deviation")),
                                pre.pooled_sd,
                            ) || !close(
                                finite(value.pointer("/pre_weight/standardized_mean_difference")),
                                pre.smd,
                            ) || !close(
                                finite(value.pointer("/treatment_weight/treatment_mean")),
                                treatment.treatment_mean,
                            ) || !close(
                                finite(value.pointer("/treatment_weight/comparator_mean")),
                                treatment.comparator_mean,
                            ) || !close(
                                finite(
                                    value.pointer("/treatment_weight/pooled_standard_deviation"),
                                ),
                                treatment.pooled_sd,
                            ) || !close(
                                finite(
                                    value.pointer("/treatment_weight/standardized_mean_difference"),
                                ),
                                treatment.smd,
                            ) || !close(
                                finite(value.pointer("/combined_observed_weight/treatment_mean")),
                                combined.treatment_mean,
                            ) || !close(
                                finite(value.pointer("/combined_observed_weight/comparator_mean")),
                                combined.comparator_mean,
                            ) || !close(
                                finite(value.pointer(
                                    "/combined_observed_weight/pooled_standard_deviation",
                                )),
                                combined.pooled_sd,
                            ) || !close(
                                finite(value.pointer(
                                    "/combined_observed_weight/standardized_mean_difference",
                                )),
                                combined.smd,
                            )
                        })
                {
                    audit
                        .errors
                        .push("RWE covariate balance differs from native replay".into());
                }
            } else {
                audit.errors.push("RWE covariate balance is missing".into());
            }
            audit.overlap_lower = finite(
                result.pointer("/diagnostics/propensity/empirical_range_intersection/lower"),
            );
            audit.overlap_upper = finite(
                result.pointer("/diagnostics/propensity/empirical_range_intersection/upper"),
            );
            if !close(audit.overlap_lower, native.overlap_lower)
                || !close(audit.overlap_upper, native.overlap_upper)
                || result
                    .pointer("/diagnostics/propensity/empirical_range_intersection/exists")
                    .and_then(|value| value.as_bool())
                    != Some(native.overlap_exists)
            {
                audit
                    .errors
                    .push("RWE propensity overlap differs from native replay".into());
            }
            compare_effect(
                &result["effects"]["observed_complete_case_unadjusted"],
                native.unadjusted,
                "unadjusted effect",
                &mut audit.errors,
            );
            let weighted = &result["effects"]["stabilized_ate_iptw_ipow"];
            let weighted_point = serde_json::json!({
                "treatment_risk": weighted["treatment_risk"],
                "comparator_risk": weighted["comparator_risk"],
                "risk_difference": weighted["risk_difference"],
                "risk_ratio": weighted["risk_ratio"],
                "odds_ratio": weighted["odds_ratio"],
            });
            compare_effect(
                &weighted_point,
                native.weighted,
                "weighted effect",
                &mut audit.errors,
            );
            audit.unadjusted_risk_difference = finite(
                result.pointer("/effects/observed_complete_case_unadjusted/risk_difference"),
            );
            audit.weighted_risk_difference = finite(weighted.get("risk_difference"));
            audit.weighted_standard_error = finite(weighted.get("risk_difference_standard_error"));
            audit.weighted_lower = finite(weighted.get("risk_difference_lower"));
            audit.weighted_upper = finite(weighted.get("risk_difference_upper"));
        }
        Err(error) => audit
            .errors
            .push(format!("RWE native point replay failed: {error}")),
    }
    if result["cross_implementation"]
        != serde_json::json!({
            "portable_replay": "complete_point_diagnostics_and_bootstrap",
            "native_replay": "point_estimate_and_diagnostics_only",
            "uncertainty_native_replay": false,
        })
    {
        audit
            .errors
            .push("RWE cross-implementation scope is invalid".into());
    }
    if result
        .pointer("/effects/causal_validity_determined")
        .and_then(|value| value.as_bool())
        != Some(false)
        || result
            .pointer("/human_gate/automatic_downstream_use")
            .and_then(|value| value.as_bool())
            != Some(false)
        || result
            .pointer("/human_gate/causal_validity_determined")
            .and_then(|value| value.as_bool())
            != Some(false)
    {
        audit
            .errors
            .push("RWE result overstates causal or downstream authority".into());
    }
    if string_array(result.get("limitations")) != Some(facts.limitations.clone()) {
        audit
            .errors
            .push("RWE result limitations changed from the request".into());
    }
    dedup_errors(&mut audit.errors);
    audit.complete = audit.errors.is_empty();
    audit.reviewable =
        audit.complete && audit.status == "awaiting_method_review" && audit.bootstrap_failures == 0;
    audit
}

fn result_path_from_request(workspace: &Path) -> Result<String, String> {
    let request_path = resolve_file(workspace, REQUEST_PATH, "RWE request")?;
    let raw = read_capped(&request_path, MAX_JSON_BYTES, "RWE request")?;
    let value: serde_json::Value = serde_json::from_slice(&raw)
        .map_err(|error| format!("RWE request is invalid JSON: {error}"))?;
    let output = text(value.pointer("/output/directory"))
        .ok_or_else(|| "RWE output.directory is invalid".to_string())?;
    Ok(format!("{output}/manifest.json"))
}

#[tauri::command]
pub fn audit_heor_rwe_causal_analysis(app: AppHandle) -> Result<RweCausalAnalysisAudit, String> {
    let workspace = crate::runtime::workspace_dir(&app)?;
    match result_path_from_request(&workspace) {
        Ok(path) => Ok(audit_path(&workspace, &path)),
        Err(error) => Ok(RweCausalAnalysisAudit {
            errors: vec![error],
            ..RweCausalAnalysisAudit::default()
        }),
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum RweCausalAnalysisReviewAction {
    Accept,
    Reject,
}

#[derive(Clone, Debug, Eq, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RweCausalAnalysisChecklist {
    pub target_trial_estimand_time_zero_reviewed: bool,
    pub data_provenance_eligibility_new_user_active_comparator_reviewed: bool,
    pub confounder_causal_rationale_measurement_reviewed: bool,
    pub missingness_follow_up_outcome_integrity_reviewed: bool,
    pub propensity_overlap_weights_positivity_reviewed: bool,
    pub balance_model_diagnostics_reviewed: bool,
    pub bootstrap_precision_failures_reviewed: bool,
    pub residual_bias_transportability_downstream_reviewed: bool,
}

impl RweCausalAnalysisChecklist {
    fn all_confirmed(&self) -> bool {
        self.target_trial_estimand_time_zero_reviewed
            && self.data_provenance_eligibility_new_user_active_comparator_reviewed
            && self.confounder_causal_rationale_measurement_reviewed
            && self.missingness_follow_up_outcome_integrity_reviewed
            && self.propensity_overlap_weights_positivity_reviewed
            && self.balance_model_diagnostics_reviewed
            && self.bootstrap_precision_failures_reviewed
            && self.residual_bias_transportability_downstream_reviewed
    }
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RweCausalAnalysisReviewRequest {
    pub project_id: String,
    pub result_path: String,
    pub result_sha256: String,
    pub action: RweCausalAnalysisReviewAction,
    pub checklist: RweCausalAnalysisChecklist,
    pub actor_label: String,
    pub rationale: String,
}

#[derive(Clone, Debug, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct RweCausalAnalysisReviewEvent {
    pub schema_version: u32,
    pub sequence: u64,
    pub review_id: String,
    pub project_id: String,
    pub execution_id: String,
    pub action: RweCausalAnalysisReviewAction,
    pub result_path: String,
    pub result_sha256: String,
    pub related_artifacts: Vec<crate::heor_approval::ArtifactBinding>,
    pub checklist: RweCausalAnalysisChecklist,
    pub actor_label: String,
    pub rationale: String,
    pub timestamp: u64,
    pub record_path: String,
    pub record_sha256: String,
    pub assurance: String,
    pub previous_hash: Option<String>,
    pub event_hash: String,
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RweCausalAnalysisReviewLog {
    pub events: Vec<RweCausalAnalysisReviewEvent>,
    pub chain_head: Option<String>,
    pub integrity: &'static str,
    pub identity_assurance: &'static str,
}

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct ReviewSnapshot<'a> {
    schema_version: &'static str,
    review_id: &'a str,
    project_id: &'a str,
    execution_id: &'a str,
    action: RweCausalAnalysisReviewAction,
    status: &'static str,
    result_path: &'a str,
    result_sha256: &'a str,
    related_artifacts: &'a [crate::heor_approval::ArtifactBinding],
    checklist: &'a RweCausalAnalysisChecklist,
    actor_label: &'a str,
    rationale: &'a str,
    timestamp: u64,
    assurance: &'static str,
}

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct ReviewHashPayload<'a> {
    schema_version: u32,
    sequence: u64,
    review_id: &'a str,
    project_id: &'a str,
    execution_id: &'a str,
    action: RweCausalAnalysisReviewAction,
    result_path: &'a str,
    result_sha256: &'a str,
    related_artifacts: &'a [crate::heor_approval::ArtifactBinding],
    checklist: &'a RweCausalAnalysisChecklist,
    actor_label: &'a str,
    rationale: &'a str,
    timestamp: u64,
    record_path: &'a str,
    record_sha256: &'a str,
    assurance: &'a str,
    previous_hash: &'a Option<String>,
}

fn validate_project_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 80
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
}

fn validate_review_text(value: &str, maximum: usize) -> bool {
    value == value.trim() && !value.is_empty() && value.chars().count() <= maximum
}

fn review_root(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app
        .path()
        .app_data_dir()
        .map_err(|error| error.to_string())?
        .join("heor")
        .join("rwe-causal-analysis-reviews"))
}

fn review_log_path(root: &Path, project_id: &str) -> Result<PathBuf, String> {
    if !validate_project_id(project_id) {
        return Err("projectId must be a safe identifier".into());
    }
    Ok(root.join(format!("{project_id}.jsonl")))
}

fn hash_review_event(event: &RweCausalAnalysisReviewEvent) -> Result<String, String> {
    let raw = serde_json::to_vec(&ReviewHashPayload {
        schema_version: event.schema_version,
        sequence: event.sequence,
        review_id: &event.review_id,
        project_id: &event.project_id,
        execution_id: &event.execution_id,
        action: event.action,
        result_path: &event.result_path,
        result_sha256: &event.result_sha256,
        related_artifacts: &event.related_artifacts,
        checklist: &event.checklist,
        actor_label: &event.actor_label,
        rationale: &event.rationale,
        timestamp: event.timestamp,
        record_path: &event.record_path,
        record_sha256: &event.record_sha256,
        assurance: &event.assurance,
        previous_hash: &event.previous_hash,
    })
    .map_err(|error| error.to_string())?;
    Ok(sha256(&raw))
}

fn snapshot_bytes(event: &RweCausalAnalysisReviewEvent) -> Result<Vec<u8>, String> {
    let snapshot = ReviewSnapshot {
        schema_version: REVIEW_SCHEMA,
        review_id: &event.review_id,
        project_id: &event.project_id,
        execution_id: &event.execution_id,
        action: event.action,
        status: if event.action == RweCausalAnalysisReviewAction::Accept {
            "accepted_for_downstream_selection"
        } else {
            "rejected_for_downstream_selection"
        },
        result_path: &event.result_path,
        result_sha256: &event.result_sha256,
        related_artifacts: &event.related_artifacts,
        checklist: &event.checklist,
        actor_label: &event.actor_label,
        rationale: &event.rationale,
        timestamp: event.timestamp,
        assurance: REVIEW_ASSURANCE,
    };
    let mut raw = serde_json::to_vec_pretty(&snapshot).map_err(|error| error.to_string())?;
    raw.push(b'\n');
    Ok(raw)
}

fn collect_related_artifacts(
    workspace: &Path,
    audit: &RweCausalAnalysisAudit,
) -> Result<Vec<crate::heor_approval::ArtifactBinding>, String> {
    let result_path = resolve_file(workspace, &audit.result_path, "RWE result")?;
    let result_raw = read_capped(&result_path, MAX_JSON_BYTES, "RWE result")?;
    let result: serde_json::Value =
        serde_json::from_slice(&result_raw).map_err(|error| error.to_string())?;
    let mut bindings = vec![crate::heor_approval::ArtifactBinding {
        path: audit.result_path.clone(),
        sha256: audit.result_sha256.clone().unwrap_or_default(),
    }];
    let mut add = |binding: &serde_json::Value| {
        if let (Some(path), Some(hash)) = (text(binding.get("path")), text(binding.get("sha256"))) {
            bindings.push(crate::heor_approval::ArtifactBinding {
                path: path.into(),
                sha256: hash.into(),
            });
        }
    };
    for field in ["request", "source_data", "evidence_synthesis"] {
        add(&result[field]);
    }
    add(&result["runtime"]["evaluator_source"]);
    add(&result["bootstrap"]["draws"]);
    let mut seen = HashSet::new();
    bindings.retain(|binding| seen.insert(binding.path.clone()));
    if bindings.len() != 6 || bindings.iter().any(|binding| !is_sha256(&binding.sha256)) {
        return Err("RWE review could not bind the complete six-artifact graph".into());
    }
    for binding in &bindings {
        let path = resolve_file(workspace, &binding.path, "RWE review artifact")?;
        let raw = read_capped(&path, MAX_SOURCE_BYTES, "RWE review artifact")?;
        if sha256(&raw) != binding.sha256 {
            return Err("RWE review artifact changed during submission".into());
        }
    }
    Ok(bindings)
}

fn read_review_events(
    root: &Path,
    workspace: &Path,
    project_id: &str,
) -> Result<Vec<RweCausalAnalysisReviewEvent>, String> {
    let path = review_log_path(root, project_id)?;
    let raw = match std::fs::read(&path) {
        Ok(raw) => raw,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(format!("RWE review log unavailable: {error}")),
    };
    if raw.len() > 4 * 1024 * 1024 {
        return Err("RWE review log exceeds 4 MB".into());
    }
    let mut events = Vec::new();
    let mut previous_hash = None;
    for (index, line) in raw
        .split(|byte| *byte == b'\n')
        .filter(|line| !line.is_empty())
        .enumerate()
    {
        if events.len() >= 2_000 {
            return Err("RWE review log exceeds 2,000 events".into());
        }
        let event: RweCausalAnalysisReviewEvent = serde_json::from_slice(line)
            .map_err(|error| format!("RWE review log line {} is invalid: {error}", index + 1))?;
        if event.schema_version != REVIEW_EVENT_SCHEMA
            || event.sequence != index as u64 + 1
            || event.project_id != project_id
            || !safe_id(&event.execution_id)
            || event.review_id.len() != 32
            || !event.review_id.bytes().all(|byte| byte.is_ascii_hexdigit())
            || !is_sha256(&event.result_sha256)
            || !is_sha256(&event.record_sha256)
            || !is_sha256(&event.event_hash)
            || event.assurance != REVIEW_ASSURANCE
            || event.previous_hash != previous_hash
            || !validate_review_text(&event.actor_label, 120)
            || !validate_review_text(&event.rationale, 2_000)
            || hash_review_event(&event)? != event.event_hash
        {
            return Err(format!(
                "RWE review log line {} violates the event contract",
                index + 1
            ));
        }
        let record = resolve_file(workspace, &event.record_path, "RWE review record")?;
        let record_raw = read_capped(&record, MAX_JSON_BYTES, "RWE review record")?;
        if sha256(&record_raw) != event.record_sha256 || record_raw != snapshot_bytes(&event)? {
            return Err(format!(
                "RWE review log line {} record binding is invalid",
                index + 1
            ));
        }
        previous_hash = Some(event.event_hash.clone());
        events.push(event);
    }
    Ok(events)
}

fn write_review_record(
    workspace: &Path,
    event: &RweCausalAnalysisReviewEvent,
) -> Result<(), String> {
    let root = workspace
        .canonicalize()
        .map_err(|error| error.to_string())?;
    let relative = Path::new(&event.record_path);
    if relative.is_absolute()
        || relative
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err("RWE review record path is unsafe".into());
    }
    let target = root.join(relative);
    let parent = target
        .parent()
        .ok_or_else(|| "RWE review record parent is invalid".to_string())?;
    std::fs::create_dir_all(parent)
        .map_err(|error| format!("RWE review directory failed: {error}"))?;
    if std::fs::symlink_metadata(parent).is_ok_and(|metadata| metadata.file_type().is_symlink()) {
        return Err("RWE review directory must not be a symlink".into());
    }
    let raw = snapshot_bytes(event)?;
    if sha256(&raw) != event.record_sha256 {
        return Err("RWE review record hash changed before write".into());
    }
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&target)
        .map_err(|error| format!("RWE review record write failed: {error}"))?;
    file.write_all(&raw)
        .and_then(|_| file.sync_all())
        .map_err(|error| format!("RWE review record write failed: {error}"))
}

fn append_review_event(root: &Path, event: &RweCausalAnalysisReviewEvent) -> Result<(), String> {
    let path = review_log_path(root, &event.project_id)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("RWE review log directory failed: {error}"))?;
        crate::runtime::tighten_private(parent);
    }
    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|error| format!("RWE review log write failed: {error}"))?;
    let mut raw = serde_json::to_vec(event).map_err(|error| error.to_string())?;
    raw.push(b'\n');
    file.write_all(&raw)
        .and_then(|_| file.sync_all())
        .map_err(|error| format!("RWE review log write failed: {error}"))
}

#[tauri::command]
pub fn append_heor_rwe_causal_analysis_review(
    app: AppHandle,
    state: tauri::State<RweCausalAnalysisReviewState>,
    request: RweCausalAnalysisReviewRequest,
) -> Result<RweCausalAnalysisReviewEvent, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "RWE review lock poisoned".to_string())?;
    if !validate_project_id(&request.project_id)
        || !is_sha256(&request.result_sha256)
        || !validate_review_text(&request.actor_label, 120)
        || !validate_review_text(&request.rationale, 2_000)
    {
        return Err("RWE review request contains invalid identity, hash, or text".into());
    }
    if request.action == RweCausalAnalysisReviewAction::Accept && !request.checklist.all_confirmed()
    {
        return Err("all eight RWE method checks are required for acceptance".into());
    }
    let workspace = crate::runtime::workspace_dir(&app)?;
    let audit = audit_path(&workspace, &request.result_path);
    if !audit.complete || !audit.reviewable {
        return Err(format!(
            "RWE result is not reviewable: {}",
            audit.errors.join("; ")
        ));
    }
    if audit.result_path != request.result_path
        || audit.result_sha256.as_deref() != Some(&request.result_sha256)
    {
        return Err("RWE review request does not bind the current audited result".into());
    }
    let related_artifacts = collect_related_artifacts(&workspace, &audit)?;
    let root = review_root(&app)?;
    let events = read_review_events(&root, &workspace, &request.project_id)?;
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| error.to_string())?
        .as_secs();
    let sequence = events.len() as u64 + 1;
    let review_id = sha256(
        format!(
            "{}:{}:{}:{}",
            request.project_id, audit.execution_id, sequence, timestamp
        )
        .as_bytes(),
    )[..32]
        .to_string();
    let record_path = format!("heor/rwe-causal-analysis-reviews/{review_id}.json");
    let mut event = RweCausalAnalysisReviewEvent {
        schema_version: REVIEW_EVENT_SCHEMA,
        sequence,
        review_id,
        project_id: request.project_id,
        execution_id: audit.execution_id,
        action: request.action,
        result_path: request.result_path,
        result_sha256: request.result_sha256,
        related_artifacts,
        checklist: request.checklist,
        actor_label: request.actor_label,
        rationale: request.rationale,
        timestamp,
        record_path,
        record_sha256: String::new(),
        assurance: REVIEW_ASSURANCE.into(),
        previous_hash: events.last().map(|event| event.event_hash.clone()),
        event_hash: String::new(),
    };
    event.record_sha256 = sha256(&snapshot_bytes(&event)?);
    event.event_hash = hash_review_event(&event)?;
    write_review_record(&workspace, &event)?;
    append_review_event(&root, &event)?;
    Ok(event)
}

#[tauri::command]
pub fn list_heor_rwe_causal_analysis_reviews(
    app: AppHandle,
    state: tauri::State<RweCausalAnalysisReviewState>,
    project_id: String,
) -> Result<RweCausalAnalysisReviewLog, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "RWE review lock poisoned".to_string())?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    let events = read_review_events(&review_root(&app)?, &workspace, &project_id)?;
    Ok(RweCausalAnalysisReviewLog {
        chain_head: events.last().map(|event| event.event_hash.clone()),
        events,
        integrity: "verified_unanchored_sha256_chain",
        identity_assurance: REVIEW_ASSURANCE,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::process::Command;

    fn checklist(value: bool) -> RweCausalAnalysisChecklist {
        RweCausalAnalysisChecklist {
            target_trial_estimand_time_zero_reviewed: value,
            data_provenance_eligibility_new_user_active_comparator_reviewed: value,
            confounder_causal_rationale_measurement_reviewed: value,
            missingness_follow_up_outcome_integrity_reviewed: value,
            propensity_overlap_weights_positivity_reviewed: value,
            balance_model_diagnostics_reviewed: value,
            bootstrap_precision_failures_reviewed: value,
            residual_bias_transportability_downstream_reviewed: value,
        }
    }

    #[test]
    fn acceptance_requires_all_eight_method_checks() {
        assert!(checklist(true).all_confirmed());
        let mut incomplete = checklist(true);
        incomplete.propensity_overlap_weights_positivity_reviewed = false;
        assert!(!incomplete.all_confirmed());
    }

    #[test]
    fn native_propensity_weighting_improves_synthetic_balance() {
        let mut rows = Vec::new();
        for index in 0..160 {
            let age = 35.0 + ((index * 7) % 45) as f64;
            let risk = if index % 5 == 0 || index % 5 == 1 {
                1.0
            } else {
                0.0
            };
            let threshold = 28 + ((age - 35.0) * 0.55) as usize + 15 * risk as usize;
            let treatment = (index * 37 + 11) % 100 < threshold;
            let outcome_threshold = 13i32 + ((age - 35.0) * 0.28) as i32 + 18 * risk as i32
                - if treatment { 5 } else { 0 };
            let outcome = if (((index * 53 + 7) % 100) as i32) < outcome_threshold {
                1.0
            } else {
                0.0
            };
            let observation_threshold = 82 - 12 * risk as usize - if treatment { 6 } else { 0 };
            let outcome_observed = (index * 29 + 17) % 100 < observation_threshold;
            rows.push(SourceRow {
                treatment,
                outcome_observed,
                outcome: outcome_observed.then_some(outcome),
                confounders: vec![age, risk],
            });
        }
        let facts = RequestFacts {
            confounder_ids: vec!["age".into(), "risk".into()],
            confounder_types: vec!["continuous".into(), "binary".into()],
            convergence_tolerance: 1e-10,
            max_iterations: 100,
            observation_predictor_indices: vec![0, 1],
            observation_convergence_tolerance: 1e-10,
            observation_max_iterations: 100,
            rows,
            ..RequestFacts::default()
        };
        let analysis = analyze(&facts).unwrap();
        assert!(analysis.max_abs_treatment_smd < analysis.max_abs_pre_smd);
        assert!(analysis.weights.contains(&0.0));
        assert!(analysis.weights.iter().any(|weight| *weight > 0.0));
        assert!((-1.0..=1.0).contains(&analysis.weighted.risk_difference));
        let python_golden = [
            -0.41031189451876593,
            0.35230231151150515,
            0.5686275375723997,
        ];
        assert_eq!(analysis.iterations, 4);
        for (actual, expected) in analysis.coefficients.iter().zip(python_golden) {
            assert!((actual - expected).abs() < 1e-10);
        }
        assert!((analysis.log_likelihood - -106.7461883101995).abs() < 1e-10);
        assert!((analysis.marginal - 0.45625).abs() < 1e-12);
        assert!(analysis.ess_overall > 0.0);
        assert!(analysis.maximum_weight > 0.0);
        assert!((analysis.max_abs_pre_smd - 0.3246295869856218).abs() < 1e-10);
        assert!(analysis.max_abs_combined_smd.is_finite());
        assert!((analysis.overlap_lower - 0.27393269474629256).abs() < 1e-10);
        assert!((analysis.overlap_upper - 0.669106471764519).abs() < 1e-10);
        assert!(analysis.unadjusted.risk_difference.is_finite());
        assert!(analysis.weighted.risk_difference.is_finite());
    }

    #[test]
    fn review_snapshot_and_event_hash_are_tamper_evident() {
        let mut event = RweCausalAnalysisReviewEvent {
            schema_version: REVIEW_EVENT_SCHEMA,
            sequence: 1,
            review_id: "0123456789abcdef0123456789abcdef".into(),
            project_id: "project".into(),
            execution_id: "rwe-test".into(),
            action: RweCausalAnalysisReviewAction::Accept,
            result_path: "heor/rwe-causal-analysis-runs/rwe-test/manifest.json".into(),
            result_sha256: "a".repeat(64),
            related_artifacts: Vec::new(),
            checklist: checklist(true),
            actor_label: "reviewer".into(),
            rationale: "Reviewed the target trial and diagnostics.".into(),
            timestamp: 1,
            record_path: "heor/rwe-causal-analysis-reviews/review.json".into(),
            record_sha256: String::new(),
            assurance: REVIEW_ASSURANCE.into(),
            previous_hash: None,
            event_hash: String::new(),
        };
        event.record_sha256 = sha256(&snapshot_bytes(&event).unwrap());
        event.event_hash = hash_review_event(&event).unwrap();
        assert_eq!(hash_review_event(&event).unwrap(), event.event_hash);
        event.rationale.push_str(" changed");
        assert_ne!(hash_review_event(&event).unwrap(), event.event_hash);
    }

    #[test]
    fn generated_portable_fixture_passes_native_audit_and_tampering_fails() {
        let root = std::env::temp_dir().join(format!(
            "ai4heor-rwe-native-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(root.join("heor/rwe-causal-data")).unwrap();
        let evidence_raw =
            b"{\n  \"records\": [\"rwe-source-record\", \"confounder-rationale-record\"]\n}\n";
        std::fs::write(root.join("heor/evidence-synthesis.json"), evidence_raw).unwrap();
        let mut csv =
            String::from("subject_id,treatment,outcome_observed,outcome,age,baseline_risk\n");
        for index in 0..160 {
            let age = 35.0 + ((index * 7) % 45) as f64;
            let risk = if index % 5 == 0 || index % 5 == 1 {
                1usize
            } else {
                0usize
            };
            let threshold = 28 + ((age - 35.0) * 0.55) as usize + 15 * risk;
            let treatment = (index * 37 + 11) % 100 < threshold;
            let outcome_threshold = 13i32 + ((age - 35.0) * 0.28) as i32 + 18 * risk as i32
                - if treatment { 5 } else { 0 };
            let outcome = usize::from((((index * 53 + 7) % 100) as i32) < outcome_threshold);
            let observation_threshold = 82 - 12 * risk - if treatment { 6 } else { 0 };
            let observed = usize::from((index * 29 + 17) % 100 < observation_threshold);
            let outcome_cell = if observed == 1 {
                outcome.to_string()
            } else {
                String::new()
            };
            csv.push_str(&format!(
                "p{:04},{},{},{},{},{}\n",
                index + 1,
                if treatment { "treatment" } else { "comparator" },
                observed,
                outcome_cell,
                age as usize,
                risk
            ));
        }
        let source_raw = csv.as_bytes();
        std::fs::write(root.join("heor/rwe-causal-data/cohort.csv"), source_raw).unwrap();
        let mut request: serde_json::Value = serde_json::from_str(include_str!(
            "../../../../runtime/skills/core/heor-rwe-causal-analysis/assets/rwe-causal-analysis-request.template.json"
        ))
        .unwrap();
        request["execution_id"] = serde_json::json!("rwe-native-fixture");
        request["evidence_synthesis"]["sha256"] = serde_json::json!(sha256(evidence_raw));
        request["source_data"]["sha256"] = serde_json::json!(sha256(source_raw));
        request["source_data"]["row_count"] = serde_json::json!(160);
        request["output"]["directory"] =
            serde_json::json!("heor/rwe-causal-analysis-runs/rwe-native-fixture");
        let mut request_raw = serde_json::to_vec_pretty(&request).unwrap();
        request_raw.push(b'\n');
        std::fs::write(root.join(REQUEST_PATH), request_raw).unwrap();
        let runner = Path::new(env!("CARGO_MANIFEST_DIR")).join(
            "../../../runtime/skills/core/heor-rwe-causal-analysis/scripts/run_rwe_causal_analysis.py",
        );
        let output = Command::new("python3")
            .env("PYTHONDONTWRITEBYTECODE", "1")
            .arg(runner)
            .arg("--workspace")
            .arg(&root)
            .arg("--request")
            .arg(REQUEST_PATH)
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "{}{}",
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        );
        let result_path = "heor/rwe-causal-analysis-runs/rwe-native-fixture/manifest.json";
        let audit = audit_path(&root, result_path);
        assert!(audit.complete, "{}", audit.errors.join("; "));
        assert!(audit.reviewable);
        let manifest_path = root.join(result_path);
        let mut manifest: serde_json::Value =
            serde_json::from_slice(&std::fs::read(&manifest_path).unwrap()).unwrap();
        manifest["effects"]["stabilized_ate_iptw_ipow"]["risk_difference"] =
            serde_json::json!(0.99);
        let mut tampered = serde_json::to_vec_pretty(&manifest).unwrap();
        tampered.push(b'\n');
        std::fs::write(&manifest_path, tampered).unwrap();
        let tampered_audit = audit_path(&root, result_path);
        assert!(!tampered_audit.complete);
        assert!(tampered_audit
            .errors
            .iter()
            .any(|error| error.contains("weighted effect")));
        std::fs::remove_dir_all(root).unwrap();
    }
}
