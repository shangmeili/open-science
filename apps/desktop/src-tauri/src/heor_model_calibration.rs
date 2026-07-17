//! Native selected-point audit and app-owned Human review for bounded model calibration.
//!
//! Portable Python replays the complete search. This module independently rebuilds
//! the continuous-time cohort transition matrix, objective, target predictions, and
//! local identifiability diagnostic at the reported candidate. It deliberately does
//! not claim to be a second implementation of the complete optimization search.

use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::io::{Read, Write};
use std::path::{Component, Path, PathBuf};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager};

const REQUEST_PATH: &str = "heor/model-calibration-request.json";
const REQUEST_SCHEMA: &str = "0.1.0";
const RESULT_SCHEMA: &str = "0.1.0";
const REVIEW_SCHEMA: &str = "0.1.0";
const REVIEW_EVENT_SCHEMA: u32 = 1;
const REVIEW_ASSURANCE: &str = "app_owned_local_human_assertion";
const EVALUATOR: &str = "ai4heor-cohort-model-calibration@0.1.0";
const TOLERANCE: f64 = 1e-8;
const MAX_JSON_BYTES: u64 = 16 * 1024 * 1024;
const MAX_SOURCE_BYTES: u64 = 64 * 1024 * 1024;
const EVALUATOR_BYTES: &[u8] = include_bytes!(
    "../../../../runtime/skills/core/heor-model-calibration/scripts/calibration_contract.py"
);
const REVIEW_CHECKS: [&str; 8] = [
    "question_model_purpose_time_origin",
    "target_provenance_population_alignment_roles",
    "parameter_meaning_bounds_evidence",
    "goodness_of_fit_scaling_covariance_omission",
    "search_convergence_multistart_diagnostics",
    "local_identifiability_alternative_fits",
    "held_out_predictive_validation",
    "uncertainty_structure_and_downstream_limitations",
];

#[derive(Default)]
pub struct ModelCalibrationReviewState(pub Mutex<()>);

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ModelCalibrationAudit {
    pub complete: bool,
    pub reviewable: bool,
    pub status: String,
    pub calibration_id: String,
    pub request_path: String,
    pub request_sha256: Option<String>,
    pub result_path: String,
    pub result_sha256: Option<String>,
    pub state_count: usize,
    pub parameter_count: usize,
    pub training_target_count: usize,
    pub validation_target_count: usize,
    pub best_objective: Option<f64>,
    pub numerical_rank: Option<usize>,
    pub full_rank: Option<bool>,
    pub held_out_rmse: Option<f64>,
    pub search_evaluations: usize,
    pub native_scope: String,
    pub limitations: Vec<String>,
    pub errors: Vec<String>,
}

impl Default for ModelCalibrationAudit {
    fn default() -> Self {
        Self {
            complete: false,
            reviewable: false,
            status: "unavailable".into(),
            calibration_id: String::new(),
            request_path: REQUEST_PATH.into(),
            request_sha256: None,
            result_path: String::new(),
            result_sha256: None,
            state_count: 0,
            parameter_count: 0,
            training_target_count: 0,
            validation_target_count: 0,
            best_objective: None,
            numerical_rank: None,
            full_rank: None,
            held_out_rmse: None,
            search_evaluations: 0,
            native_scope: "selected_point_model_and_local_identifiability_only".into(),
            limitations: Vec::new(),
            errors: Vec::new(),
        }
    }
}

#[derive(Clone)]
struct Transition {
    from: usize,
    to: usize,
    parameter_id: Option<String>,
    fixed_rate: Option<f64>,
}

#[derive(Clone)]
struct Parameter {
    id: String,
    lower: f64,
    upper: f64,
    log_scale: bool,
}

#[derive(Clone)]
struct Target {
    id: String,
    validation: bool,
    cycle: usize,
    state: usize,
    observed: f64,
    se: f64,
}

#[derive(Default)]
struct RequestFacts {
    calibration_id: String,
    evidence_path: String,
    evidence_sha256: String,
    output_directory: String,
    states: Vec<String>,
    initial: Vec<f64>,
    cycle_length: f64,
    cycles: usize,
    transitions: Vec<Transition>,
    parameters: Vec<Parameter>,
    targets: Vec<Target>,
    limitations: Vec<String>,
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

fn bool_value(value: Option<&serde_json::Value>) -> Option<bool> {
    value.and_then(serde_json::Value::as_bool)
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
    errors: &mut Vec<String>,
) -> Option<(PathBuf, Vec<u8>)> {
    if !exact(binding, &["path", "sha256"]) {
        errors.push(format!("{label} binding fields are invalid"));
        return None;
    }
    let path = text(binding.get("path"))?;
    let expected_hash = text(binding.get("sha256"))?;
    if expected_path.is_some_and(|expected| expected != path) || !is_sha256(expected_hash) {
        errors.push(format!("{label} binding is invalid"));
        return None;
    }
    let resolved = match resolve_file(workspace, path, label) {
        Ok(path) => path,
        Err(error) => {
            errors.push(error);
            return None;
        }
    };
    let raw = match read_capped(&resolved, MAX_SOURCE_BYTES, label) {
        Ok(raw) => raw,
        Err(error) => {
            errors.push(error);
            return None;
        }
    };
    if sha256(&raw) != expected_hash {
        errors.push(format!("{label} sha256 does not match current bytes"));
    }
    Some((resolved, raw))
}

fn string_array(value: Option<&serde_json::Value>) -> Option<Vec<String>> {
    value
        .and_then(serde_json::Value::as_array)
        .and_then(|values| {
            values
                .iter()
                .map(|value| text(Some(value)).map(str::to_string))
                .collect()
        })
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
            "calibration_id",
            "status",
            "question",
            "evidence_synthesis",
            "model",
            "parameters",
            "targets",
            "goodness_of_fit",
            "search",
            "identifiability",
            "output",
            "human_authorization",
            "limitations",
            "human_gate",
        ],
    ) || text(request.get("schema_version")) != Some(REQUEST_SCHEMA)
        || text(request.get("status")) != Some("ready_for_execution")
    {
        errors.push("model calibration request top-level contract is invalid".into());
    }
    if let Some(id) = text(request.get("calibration_id")).filter(|value| safe_id(value)) {
        facts.calibration_id = id.into();
    } else {
        errors.push("model calibration id is invalid".into());
    }
    if !exact(
        &request["question"],
        &["population", "purpose", "time_origin", "intended_use"],
    ) || ["population", "purpose", "time_origin", "intended_use"]
        .iter()
        .any(|field| text(request["question"].get(*field)).is_none())
    {
        errors.push("model calibration question is incomplete".into());
    }
    let evidence = &request["evidence_synthesis"];
    let mut bound_evidence_ids = HashSet::new();
    if !exact(evidence, &["path", "sha256", "included_record_ids"])
        || text(evidence.get("path")).is_none()
        || text(evidence.get("sha256")).is_none_or(|hash| !is_sha256(hash))
        || string_array(evidence.get("included_record_ids")).is_none_or(|values| values.is_empty())
    {
        errors.push("model calibration evidence binding is invalid".into());
    } else {
        facts.evidence_path = text(evidence.get("path")).unwrap_or_default().into();
        facts.evidence_sha256 = text(evidence.get("sha256")).unwrap_or_default().into();
        let simple = serde_json::json!({
            "path": facts.evidence_path.clone(),
            "sha256": facts.evidence_sha256.clone()
        });
        if let Some((_, raw)) = bound_bytes(
            workspace,
            &simple,
            None,
            "model calibration evidence",
            errors,
        ) {
            if let Ok(value) = serde_json::from_slice::<serde_json::Value>(&raw) {
                let available: HashSet<String> = value
                    .get("records")
                    .and_then(serde_json::Value::as_array)
                    .into_iter()
                    .flatten()
                    .filter_map(|record| {
                        record
                            .as_str()
                            .or_else(|| text(record.get("id")))
                            .map(str::to_string)
                    })
                    .collect();
                bound_evidence_ids = string_array(evidence.get("included_record_ids"))
                    .unwrap_or_default()
                    .into_iter()
                    .collect();
                if !bound_evidence_ids.is_subset(&available) {
                    errors
                        .push("model calibration included evidence records are unavailable".into());
                }
            } else {
                errors.push("model calibration evidence is invalid JSON".into());
            }
        }
    }
    let model = &request["model"];
    if !exact(
        model,
        &[
            "type",
            "states",
            "initial_distribution",
            "cycle_length_years",
            "cycles",
            "matrix_exponential",
            "transitions",
        ],
    ) || text(model.get("type")) != Some("homogeneous_continuous_time_cohort_state_transition")
        || model.get("matrix_exponential")
            != Some(&serde_json::json!({
                "method": "uniformization", "tail_tolerance": 1e-14, "maximum_terms": 512
            }))
    {
        errors.push("model calibration model contract is invalid".into());
    }
    facts.states = string_array(model.get("states")).unwrap_or_default();
    if !(2..=6).contains(&facts.states.len())
        || facts.states.iter().any(|state| !safe_id(state))
        || facts.states.iter().collect::<HashSet<_>>().len() != facts.states.len()
    {
        errors.push("model calibration states are invalid".into());
    }
    facts.initial = model
        .get("initial_distribution")
        .and_then(serde_json::Value::as_array)
        .map(|values| {
            values
                .iter()
                .filter_map(|value| finite(Some(value)))
                .collect()
        })
        .unwrap_or_default();
    if facts.initial.len() != facts.states.len()
        || facts
            .initial
            .iter()
            .any(|value| !(0.0..=1.0).contains(value))
        || (facts.initial.iter().sum::<f64>() - 1.0).abs() > 1e-10
    {
        errors.push("model calibration initial distribution is invalid".into());
    }
    facts.cycle_length = finite(model.get("cycle_length_years")).unwrap_or_default();
    facts.cycles = model
        .get("cycles")
        .and_then(serde_json::Value::as_u64)
        .unwrap_or_default() as usize;
    if !(0.0..=10.0).contains(&facts.cycle_length)
        || facts.cycle_length == 0.0
        || !(1..=2_000).contains(&facts.cycles)
    {
        errors.push("model calibration cycle specification is invalid".into());
    }
    let state_index: HashMap<&str, usize> = facts
        .states
        .iter()
        .enumerate()
        .map(|(index, value)| (value.as_str(), index))
        .collect();
    let transition_values = model
        .get("transitions")
        .and_then(serde_json::Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut transition_ids = HashSet::new();
    let mut transition_pairs = HashSet::new();
    for transition in transition_values {
        let source = text(transition.get("source"));
        let fields = if source == Some("calibrated_parameter") {
            &["id", "from_state", "to_state", "source", "parameter_id"][..]
        } else {
            &[
                "id",
                "from_state",
                "to_state",
                "source",
                "rate_per_year",
                "rationale",
                "evidence_record_ids",
            ][..]
        };
        let id = text(transition.get("id")).unwrap_or_default();
        let from_name = text(transition.get("from_state")).unwrap_or_default();
        let to_name = text(transition.get("to_state")).unwrap_or_default();
        let from = state_index.get(from_name).copied();
        let to = state_index.get(to_name).copied();
        if !exact(&transition, fields)
            || !safe_id(id)
            || from.is_none()
            || to.is_none()
            || from == to
            || !transition_ids.insert(id.to_string())
            || !transition_pairs.insert((from, to))
        {
            errors.push("model calibration transition graph is invalid".into());
            continue;
        }
        let (parameter_id, fixed_rate) = if source == Some("calibrated_parameter") {
            (
                text(transition.get("parameter_id")).map(str::to_string),
                None,
            )
        } else {
            (None, finite(transition.get("rate_per_year")))
        };
        if parameter_id.as_deref().is_some_and(|value| !safe_id(value))
            || fixed_rate.is_some_and(|value| value < 0.0)
            || (parameter_id.is_none() && fixed_rate.is_none())
        {
            errors.push("model calibration transition rate is invalid".into());
        }
        if source == Some("fixed_rate")
            && string_array(transition.get("evidence_record_ids")).is_none_or(|ids| {
                ids.is_empty() || ids.iter().any(|id| !bound_evidence_ids.contains(id))
            })
        {
            errors.push("model calibration fixed-rate evidence is not bound".into());
        }
        facts.transitions.push(Transition {
            from: from.unwrap_or_default(),
            to: to.unwrap_or_default(),
            parameter_id,
            fixed_rate,
        });
    }
    let parameter_values = request
        .get("parameters")
        .and_then(serde_json::Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut parameter_ids = HashSet::new();
    for parameter in parameter_values {
        if !exact(
            &parameter,
            &[
                "id",
                "label",
                "transition_id",
                "unit",
                "lower",
                "upper",
                "search_scale",
                "status",
                "rationale",
                "evidence_record_ids",
            ],
        ) || text(parameter.get("status")) != Some("unobservable_natural_history_parameter")
        {
            errors.push("model calibration parameter fields are invalid".into());
            continue;
        }
        let id = text(parameter.get("id")).unwrap_or_default();
        let lower = finite(parameter.get("lower")).unwrap_or(f64::NAN);
        let upper = finite(parameter.get("upper")).unwrap_or(f64::NAN);
        let scale = text(parameter.get("search_scale"));
        if !safe_id(id)
            || !parameter_ids.insert(id.to_string())
            || lower < 0.0
            || lower >= upper
            || !matches!(scale, Some("linear" | "log"))
            || (scale == Some("log") && lower <= 0.0)
        {
            errors.push("model calibration parameter bounds or scale are invalid".into());
        }
        if string_array(parameter.get("evidence_record_ids")).is_none_or(|ids| {
            ids.is_empty() || ids.iter().any(|id| !bound_evidence_ids.contains(id))
        }) {
            errors.push("model calibration parameter evidence is not bound".into());
        }
        facts.parameters.push(Parameter {
            id: id.into(),
            lower,
            upper,
            log_scale: scale == Some("log"),
        });
    }
    if !(1..=4).contains(&facts.parameters.len()) {
        errors.push("model calibration requires one to four parameters".into());
    }
    let calibrated: Vec<&str> = facts
        .transitions
        .iter()
        .filter_map(|transition| transition.parameter_id.as_deref())
        .collect();
    if calibrated.len() != facts.parameters.len()
        || calibrated.iter().copied().collect::<HashSet<_>>().len() != calibrated.len()
        || facts
            .parameters
            .iter()
            .any(|parameter| !calibrated.contains(&parameter.id.as_str()))
    {
        errors.push("model calibration transition-parameter binding is invalid".into());
    }
    let upper_by_id: HashMap<&str, f64> = facts
        .parameters
        .iter()
        .map(|parameter| (parameter.id.as_str(), parameter.upper))
        .collect();
    let mut maximum_exit = vec![0.0; facts.states.len()];
    for transition in &facts.transitions {
        maximum_exit[transition.from] += transition
            .parameter_id
            .as_deref()
            .and_then(|id| upper_by_id.get(id).copied())
            .or(transition.fixed_rate)
            .unwrap_or(f64::INFINITY);
    }
    if maximum_exit.into_iter().fold(0.0_f64, f64::max) * facts.cycle_length > 30.0 {
        errors.push("model calibration maximum uniformization intensity exceeds 30".into());
    }
    let target_values = request
        .get("targets")
        .and_then(serde_json::Value::as_array)
        .cloned()
        .unwrap_or_default();
    let mut target_ids = HashSet::new();
    for target in target_values {
        if !exact(
            &target,
            &[
                "id",
                "role",
                "cycle",
                "state",
                "measure",
                "observed",
                "standard_error",
                "population_alignment",
                "evidence_record_ids",
            ],
        ) || text(target.get("measure")) != Some("state_occupancy_proportion")
        {
            errors.push("model calibration target fields are invalid".into());
            continue;
        }
        let id = text(target.get("id")).unwrap_or_default();
        let role = text(target.get("role"));
        let cycle = target
            .get("cycle")
            .and_then(serde_json::Value::as_u64)
            .unwrap_or_default() as usize;
        let state = text(target.get("state")).and_then(|value| state_index.get(value).copied());
        let observed = finite(target.get("observed")).unwrap_or(f64::NAN);
        let se = finite(target.get("standard_error")).unwrap_or(f64::NAN);
        if !safe_id(id)
            || !target_ids.insert(id.to_string())
            || !matches!(role, Some("calibration" | "validation"))
            || !(1..=facts.cycles).contains(&cycle)
            || state.is_none()
            || !(0.0..=1.0).contains(&observed)
            || se <= 0.0
        {
            errors.push("model calibration target values are invalid".into());
        }
        if string_array(target.get("evidence_record_ids")).is_none_or(|ids| {
            ids.is_empty() || ids.iter().any(|id| !bound_evidence_ids.contains(id))
        }) {
            errors.push("model calibration target evidence is not bound".into());
        }
        facts.targets.push(Target {
            id: id.into(),
            validation: role == Some("validation"),
            cycle,
            state: state.unwrap_or_default(),
            observed,
            se,
        });
    }
    let training = facts
        .targets
        .iter()
        .filter(|target| !target.validation)
        .count();
    let validation = facts
        .targets
        .iter()
        .filter(|target| target.validation)
        .count();
    if training <= facts.parameters.len() || validation == 0 {
        errors.push("model calibration requires more training targets than parameters and held-out validation".into());
    }
    if request.get("goodness_of_fit")
        != Some(&serde_json::json!({
            "training_loss": "sum_squared_standardized_residuals",
            "standard_error_use": "target_specific_scaling_only",
            "target_covariance": "not_modeled",
            "automatic_fit_thresholds": "none"
        }))
        || request.get("search")
            != Some(&serde_json::json!({
                "method": "deterministic_grid_multistart_pattern_search",
                "grid_levels_per_parameter": 7,
                "local_start_count": 8,
                "minimum_normalized_step": 1e-7,
                "maximum_iterations_per_start": 500,
                "tie_break": "objective_then_lexicographic_normalized_parameters"
            }))
        || request.get("identifiability")
            != Some(&serde_json::json!({
                "method": "finite_difference_scaled_target_jacobian",
                "normalized_derivative_step": 1e-5,
                "relative_rank_tolerance": 1e-8,
                "automatic_acceptance_thresholds": "none"
            }))
    {
        errors.push("model calibration fixed method settings drifted".into());
    }
    facts.output_directory = text(request.pointer("/output/directory"))
        .unwrap_or_default()
        .into();
    if facts.output_directory != format!("heor/model-calibration-runs/{}", facts.calibration_id) {
        errors.push("model calibration output directory is invalid".into());
    }
    if !exact(
        &request["human_authorization"],
        &["actor", "authorized_at", "scope"],
    ) || text(request.pointer("/human_authorization/actor")).is_none()
        || text(request.pointer("/human_authorization/authorized_at")).is_none_or(|value| {
            let bytes = value.as_bytes();
            bytes.len() != 20
                || bytes[4] != b'-'
                || bytes[7] != b'-'
                || bytes[10] != b'T'
                || bytes[13] != b':'
                || bytes[16] != b':'
                || bytes[19] != b'Z'
        })
        || text(request.pointer("/human_authorization/scope"))
            != Some("execute_local_model_calibration")
    {
        errors.push("model calibration Human command authorization is invalid".into());
    }
    facts.limitations = string_array(request.get("limitations")).unwrap_or_default();
    if facts.limitations.len() < 2
        || request
            .pointer("/human_gate/status")
            .and_then(serde_json::Value::as_str)
            != Some("awaiting_method_review")
        || string_array(request.pointer("/human_gate/required_checks"))
            != Some(
                REVIEW_CHECKS
                    .iter()
                    .map(|value| (*value).to_string())
                    .collect(),
            )
    {
        errors.push("model calibration limitations or Human gate are invalid".into());
    }
    facts
}

fn matmul(left: &[Vec<f64>], right: &[Vec<f64>]) -> Vec<Vec<f64>> {
    (0..left.len())
        .map(|row| {
            (0..right[0].len())
                .map(|column| {
                    (0..right.len())
                        .map(|inner| left[row][inner] * right[inner][column])
                        .sum()
                })
                .collect()
        })
        .collect()
}

fn transition_matrix(
    facts: &RequestFacts,
    values: &HashMap<String, f64>,
) -> Result<Vec<Vec<f64>>, String> {
    let count = facts.states.len();
    let mut generator = vec![vec![0.0; count]; count];
    for transition in &facts.transitions {
        let rate = transition
            .parameter_id
            .as_ref()
            .and_then(|id| values.get(id))
            .copied()
            .or(transition.fixed_rate)
            .ok_or_else(|| "calibration rate is unavailable".to_string())?;
        generator[transition.from][transition.to] += rate;
        generator[transition.from][transition.from] -= rate;
    }
    let maximum_exit = (0..count)
        .map(|index| -generator[index][index])
        .max_by(f64::total_cmp)
        .unwrap_or_default();
    let identity: Vec<Vec<f64>> = (0..count)
        .map(|row| {
            (0..count)
                .map(|column| if row == column { 1.0 } else { 0.0 })
                .collect()
        })
        .collect();
    if maximum_exit == 0.0 {
        return Ok(identity);
    }
    let embedded: Vec<Vec<f64>> = (0..count)
        .map(|row| {
            (0..count)
                .map(|column| identity[row][column] + generator[row][column] / maximum_exit)
                .collect()
        })
        .collect();
    let intensity = maximum_exit * facts.cycle_length;
    if intensity > 30.0 {
        return Err("uniformization intensity exceeds the native bound".into());
    }
    let mut probability = (-intensity).exp();
    let mut cumulative = probability;
    let mut power = identity;
    let mut result: Vec<Vec<f64>> = power
        .iter()
        .map(|row| row.iter().map(|value| probability * value).collect())
        .collect();
    let mut converged = false;
    for order in 1..512 {
        power = matmul(&power, &embedded);
        probability *= intensity / order as f64;
        cumulative += probability;
        for row in 0..count {
            for column in 0..count {
                result[row][column] += probability * power[row][column];
            }
        }
        if 1.0 - cumulative <= 1e-14 {
            converged = true;
            break;
        }
    }
    if !converged {
        return Err("uniformization did not reach the declared tolerance".into());
    }
    for row in &mut result {
        let total: f64 = row.iter().sum();
        if total <= 0.0
            || row
                .iter()
                .any(|value| !value.is_finite() || *value < -1e-12)
        {
            return Err("uniformization produced an invalid transition matrix".into());
        }
        for value in row {
            *value = value.max(0.0) / total;
        }
    }
    Ok(result)
}

fn predictions(
    facts: &RequestFacts,
    values: &HashMap<String, f64>,
) -> Result<HashMap<String, f64>, String> {
    let transition = transition_matrix(facts, values)?;
    let mut rows = vec![facts.initial.clone()];
    for _ in 0..facts.cycles {
        let current = rows.last().cloned().unwrap_or_default();
        let next: Vec<f64> = (0..facts.states.len())
            .map(|destination| {
                (0..facts.states.len())
                    .map(|source| current[source] * transition[source][destination])
                    .sum()
            })
            .collect();
        let total: f64 = next.iter().sum();
        rows.push(next.iter().map(|value| value.max(0.0) / total).collect());
    }
    Ok(facts
        .targets
        .iter()
        .map(|target| (target.id.clone(), rows[target.cycle][target.state]))
        .collect())
}

fn actual_values(facts: &RequestFacts, normalized: &[f64]) -> HashMap<String, f64> {
    facts
        .parameters
        .iter()
        .zip(normalized)
        .map(|(parameter, coordinate)| {
            let value = if parameter.log_scale {
                (parameter.lower.ln() + coordinate * (parameter.upper.ln() - parameter.lower.ln()))
                    .exp()
            } else {
                parameter.lower + coordinate * (parameter.upper - parameter.lower)
            };
            (parameter.id.clone(), value)
        })
        .collect()
}

fn jacobi_eigenvalues(mut matrix: Vec<Vec<f64>>) -> Vec<f64> {
    let size = matrix.len();
    for _ in 0..100 * size.max(1) * size.max(1) {
        let Some((row, column)) = (0..size)
            .flat_map(|row| (row + 1..size).map(move |column| (row, column)))
            .max_by(|left, right| {
                matrix[left.0][left.1]
                    .abs()
                    .total_cmp(&matrix[right.0][right.1].abs())
            })
        else {
            break;
        };
        if matrix[row][column].abs() <= 1e-15 {
            break;
        }
        let angle =
            0.5 * (2.0 * matrix[row][column]).atan2(matrix[column][column] - matrix[row][row]);
        let (sine, cosine) = angle.sin_cos();
        for index in 0..size {
            if index == row || index == column {
                continue;
            }
            let left = matrix[index][row];
            let right = matrix[index][column];
            matrix[index][row] = cosine * left - sine * right;
            matrix[row][index] = matrix[index][row];
            matrix[index][column] = sine * left + cosine * right;
            matrix[column][index] = matrix[index][column];
        }
        let a = matrix[row][row];
        let b = matrix[row][column];
        let d = matrix[column][column];
        matrix[row][row] = cosine * cosine * a - 2.0 * sine * cosine * b + sine * sine * d;
        matrix[column][column] = sine * sine * a + 2.0 * sine * cosine * b + cosine * cosine * d;
        matrix[row][column] = 0.0;
        matrix[column][row] = 0.0;
    }
    let mut result: Vec<f64> = (0..size)
        .map(|index| matrix[index][index].max(0.0))
        .collect();
    result.sort_by(|left, right| right.total_cmp(left));
    result
}

fn identifiability(
    facts: &RequestFacts,
    normalized: &[f64],
) -> Result<(usize, Vec<f64>, Option<f64>), String> {
    let training: Vec<&Target> = facts
        .targets
        .iter()
        .filter(|target| !target.validation)
        .collect();
    let mut columns = Vec::new();
    for parameter_index in 0..normalized.len() {
        let mut lower = normalized.to_vec();
        let mut upper = normalized.to_vec();
        lower[parameter_index] = (lower[parameter_index] - 1e-5).max(0.0);
        upper[parameter_index] = (upper[parameter_index] + 1e-5).min(1.0);
        let denominator = upper[parameter_index] - lower[parameter_index];
        let low = predictions(facts, &actual_values(facts, &lower))?;
        let high = predictions(facts, &actual_values(facts, &upper))?;
        columns.push(
            training
                .iter()
                .map(|target| (high[&target.id] - low[&target.id]) / denominator / target.se)
                .collect::<Vec<_>>(),
        );
    }
    let size = normalized.len();
    let information: Vec<Vec<f64>> = (0..size)
        .map(|left| {
            (0..size)
                .map(|right| {
                    (0..training.len())
                        .map(|row| columns[left][row] * columns[right][row])
                        .sum()
                })
                .collect()
        })
        .collect();
    let eigenvalues = jacobi_eigenvalues(information);
    let maximum = eigenvalues.first().copied().unwrap_or_default();
    let rank = if maximum > 0.0 {
        eigenvalues
            .iter()
            .filter(|value| **value > maximum * 1e-16)
            .count()
    } else {
        0
    };
    let positive: Vec<f64> = eigenvalues
        .iter()
        .copied()
        .filter(|value| *value > maximum * 1e-16)
        .collect();
    let condition = positive.last().map(|minimum| (maximum / minimum).sqrt());
    Ok((rank, eigenvalues, condition))
}

fn close(value: Option<&serde_json::Value>, expected: f64) -> bool {
    finite(value).is_some_and(|actual| {
        (actual - expected).abs() <= TOLERANCE * actual.abs().max(expected.abs()).max(1.0)
    })
}

fn dedup_errors(errors: &mut Vec<String>) {
    let mut seen = HashSet::new();
    errors.retain(|error| seen.insert(error.clone()));
}

fn audit_path(workspace: &Path, result_path: &str) -> ModelCalibrationAudit {
    let mut audit = ModelCalibrationAudit {
        result_path: result_path.into(),
        ..ModelCalibrationAudit::default()
    };
    let request_path = match resolve_file(workspace, REQUEST_PATH, "model calibration request") {
        Ok(path) => path,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    let request_raw = match read_capped(&request_path, MAX_JSON_BYTES, "model calibration request")
    {
        Ok(raw) => raw,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    audit.request_sha256 = Some(sha256(&request_raw));
    let request: serde_json::Value = match serde_json::from_slice(&request_raw) {
        Ok(value) => value,
        Err(error) => {
            audit.errors.push(format!(
                "model calibration request is invalid JSON: {error}"
            ));
            return audit;
        }
    };
    let facts = validate_request(workspace, &request, &mut audit.errors);
    audit.calibration_id = facts.calibration_id.clone();
    audit.state_count = facts.states.len();
    audit.parameter_count = facts.parameters.len();
    audit.training_target_count = facts
        .targets
        .iter()
        .filter(|target| !target.validation)
        .count();
    audit.validation_target_count = facts
        .targets
        .iter()
        .filter(|target| target.validation)
        .count();
    audit.limitations = facts.limitations.clone();
    if !audit.errors.is_empty() {
        dedup_errors(&mut audit.errors);
        return audit;
    }
    let result_file = match resolve_file(workspace, result_path, "model calibration result") {
        Ok(path) => path,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    let result_raw = match read_capped(&result_file, MAX_JSON_BYTES, "model calibration result") {
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
                .push(format!("model calibration result is invalid JSON: {error}"));
            return audit;
        }
    };
    if !exact(
        &result,
        &[
            "schema_version",
            "calibration_id",
            "status",
            "request",
            "evidence_synthesis",
            "runtime",
            "method",
            "best_fit",
            "target_fit",
            "search",
            "identifiability",
            "validation",
            "cross_implementation",
            "warnings",
            "limitations",
            "human_gate",
        ],
    ) || text(result.get("schema_version")) != Some(RESULT_SCHEMA)
        || text(result.get("calibration_id")) != Some(&facts.calibration_id)
        || text(result.get("status")) != Some("awaiting_method_review")
    {
        audit
            .errors
            .push("model calibration result top-level contract is invalid".into());
    }
    audit.status = text(result.get("status")).unwrap_or("invalid").into();
    if !exact(&result["request"], &["path", "sha256"])
        || text(result.pointer("/request/path")) != Some(REQUEST_PATH)
        || text(result.pointer("/request/sha256")) != audit.request_sha256.as_deref()
    {
        audit
            .errors
            .push("model calibration result does not bind the current request".into());
    }
    if result.get("evidence_synthesis")
        != Some(&serde_json::json!({"path": facts.evidence_path, "sha256": facts.evidence_sha256}))
    {
        audit
            .errors
            .push("model calibration evidence binding drifted".into());
    }
    let runtime = &result["runtime"];
    if !exact(
        runtime,
        &[
            "evaluator",
            "python_version",
            "python_executable_sha256",
            "evaluator_source",
        ],
    ) || text(runtime.get("evaluator")) != Some(EVALUATOR)
        || text(runtime.get("python_version")).is_none()
        || text(runtime.get("python_executable_sha256")).is_none_or(|hash| !is_sha256(hash))
    {
        audit
            .errors
            .push("model calibration runtime identity is invalid".into());
    }
    if let Some((_, raw)) = bound_bytes(
        workspace,
        &runtime["evaluator_source"],
        None,
        "model calibration evaluator",
        &mut audit.errors,
    ) {
        if raw != EVALUATOR_BYTES
            || text(runtime.pointer("/evaluator_source/sha256"))
                != Some(sha256(EVALUATOR_BYTES).as_str())
        {
            audit
                .errors
                .push("model calibration evaluator is not the current bundled source".into());
        }
    }
    if let Some((_, raw)) = bound_bytes(
        workspace,
        &result["search"]["trace"],
        None,
        "model calibration search trace",
        &mut audit.errors,
    ) {
        audit.search_evaluations = raw
            .split(|byte| *byte == b'\n')
            .filter(|line| !line.is_empty())
            .count()
            .saturating_sub(1);
    }
    let search = &result["search"];
    let expected_grid = 7_usize.pow(facts.parameters.len() as u32);
    if !exact(
        search,
        &[
            "method",
            "grid_evaluations",
            "total_evaluations",
            "training_target_count",
            "validation_target_count",
            "local_solutions",
            "stopping_rule",
            "automatic_fit_thresholds",
            "trace",
        ],
    ) || text(search.get("method")) != Some("deterministic_grid_multistart_pattern_search")
        || search
            .get("grid_evaluations")
            .and_then(serde_json::Value::as_u64)
            != Some(expected_grid as u64)
        || search
            .get("total_evaluations")
            .and_then(serde_json::Value::as_u64)
            != Some(audit.search_evaluations as u64)
        || search
            .get("training_target_count")
            .and_then(serde_json::Value::as_u64)
            != Some(audit.training_target_count as u64)
        || search
            .get("validation_target_count")
            .and_then(serde_json::Value::as_u64)
            != Some(audit.validation_target_count as u64)
        || search
            .get("local_solutions")
            .and_then(serde_json::Value::as_array)
            .is_none_or(|values| values.len() != 8)
        || search.get("stopping_rule")
            != Some(&serde_json::json!({
                "minimum_normalized_step": 1e-7,
                "maximum_iterations_per_start": 500
            }))
        || text(search.get("automatic_fit_thresholds")) != Some("none")
    {
        audit
            .errors
            .push("model calibration search summary or trace count is invalid".into());
    }
    if !exact(
        &result["best_fit"],
        &["objective", "normalized_parameters", "parameters"],
    ) {
        audit
            .errors
            .push("model calibration best-fit fields are invalid".into());
    }
    let normalized = result
        .pointer("/best_fit/normalized_parameters")
        .and_then(serde_json::Value::as_array)
        .map(|values| {
            values
                .iter()
                .filter_map(|value| finite(Some(value)))
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    if normalized.len() != facts.parameters.len()
        || normalized.iter().any(|value| !(0.0..=1.0).contains(value))
    {
        audit
            .errors
            .push("model calibration normalized candidate is invalid".into());
    } else {
        let values = actual_values(&facts, &normalized);
        let predictions = predictions(&facts, &values);
        match predictions {
            Ok(predictions) => {
                let objective: f64 = facts
                    .targets
                    .iter()
                    .filter(|target| !target.validation)
                    .map(|target| ((predictions[&target.id] - target.observed) / target.se).powi(2))
                    .sum();
                audit.best_objective = Some(objective);
                if !close(result.pointer("/best_fit/objective"), objective) {
                    audit.errors.push("model calibration objective differs from native selected-point recomputation".into());
                }
                let reported_parameters = result
                    .pointer("/best_fit/parameters")
                    .and_then(serde_json::Value::as_object);
                if reported_parameters.is_none_or(|reported| {
                    reported.len() != values.len()
                        || values
                            .iter()
                            .any(|(id, value)| !close(reported.get(id), *value))
                }) {
                    audit.errors.push("model calibration parameter values differ from bounded-scale recomputation".into());
                }
                let target_rows = result
                    .get("target_fit")
                    .and_then(serde_json::Value::as_array);
                if target_rows.is_none_or(|rows| rows.len() != facts.targets.len()) {
                    audit
                        .errors
                        .push("model calibration target-fit rows are incomplete".into());
                } else if let Some(rows) = target_rows {
                    for (target, row) in facts.targets.iter().zip(rows) {
                        let predicted = predictions[&target.id];
                        let residual = predicted - target.observed;
                        if !exact(
                            row,
                            &[
                                "id",
                                "role",
                                "cycle",
                                "state",
                                "observed",
                                "predicted",
                                "residual",
                                "standard_error",
                                "standardized_residual",
                            ],
                        ) || text(row.get("id")) != Some(&target.id)
                            || text(row.get("role"))
                                != Some(if target.validation {
                                    "validation"
                                } else {
                                    "calibration"
                                })
                            || row.get("cycle").and_then(serde_json::Value::as_u64)
                                != Some(target.cycle as u64)
                            || text(row.get("state")) != Some(&facts.states[target.state])
                            || !close(row.get("observed"), target.observed)
                            || !close(row.get("standard_error"), target.se)
                            || !close(row.get("predicted"), predicted)
                            || !close(row.get("residual"), residual)
                            || !close(row.get("standardized_residual"), residual / target.se)
                        {
                            audit.errors.push("model calibration target-fit row differs from native recomputation".into());
                        }
                    }
                }
                let heldout: Vec<f64> = facts
                    .targets
                    .iter()
                    .filter(|target| target.validation)
                    .map(|target| predictions[&target.id] - target.observed)
                    .collect();
                let rmse = (heldout.iter().map(|value| value * value).sum::<f64>()
                    / heldout.len() as f64)
                    .sqrt();
                audit.held_out_rmse = Some(rmse);
                if !close(result.pointer("/validation/rmse"), rmse) {
                    audit.errors.push(
                        "model calibration held-out RMSE differs from native recomputation".into(),
                    );
                }
            }
            Err(error) => audit.errors.push(format!(
                "native model calibration simulation failed: {error}"
            )),
        }
        match identifiability(&facts, &normalized) {
            Ok((rank, eigenvalues, condition)) => {
                audit.numerical_rank = Some(rank);
                audit.full_rank = Some(rank == facts.parameters.len());
                let reported_eigenvalues = result
                    .pointer("/identifiability/information_eigenvalues")
                    .and_then(serde_json::Value::as_array);
                if result
                    .pointer("/identifiability/numerical_rank")
                    .and_then(serde_json::Value::as_u64)
                    != Some(rank as u64)
                    || bool_value(result.pointer("/identifiability/full_rank"))
                        != Some(rank == facts.parameters.len())
                    || reported_eigenvalues.is_none_or(|values| {
                        values.len() != eigenvalues.len()
                            || values
                                .iter()
                                .zip(&eigenvalues)
                                .any(|(value, expected)| !close(Some(value), *expected))
                    })
                    || condition.is_some_and(|expected| {
                        !close(
                            result
                                .pointer("/identifiability/condition_index_identifiable_subspace"),
                            expected,
                        )
                    })
                {
                    audit.errors.push(
                        "model calibration identifiability differs from native local diagnostic"
                            .into(),
                    );
                }
            }
            Err(error) => audit.errors.push(format!(
                "native model calibration identifiability failed: {error}"
            )),
        }
    }
    if !exact(
        &result["identifiability"],
        &[
            "method",
            "scope",
            "numerical_rank",
            "parameter_count",
            "full_rank",
            "information_eigenvalues",
            "condition_index_identifiable_subspace",
            "relative_rank_tolerance",
            "automatic_acceptance_thresholds",
        ],
    ) || text(result.pointer("/identifiability/method"))
        != Some("finite_difference_scaled_target_jacobian")
        || text(result.pointer("/identifiability/scope"))
            != Some("local_scaled_training_target_jacobian_only")
        || close(
            result.pointer("/identifiability/relative_rank_tolerance"),
            1e-8,
        ) == false
        || text(result.pointer("/identifiability/automatic_acceptance_thresholds")) != Some("none")
        || !exact(
            &result["validation"],
            &[
                "held_out_target_count",
                "rmse",
                "maximum_absolute_residual",
                "automatic_acceptance_thresholds",
            ],
        )
        || result
            .pointer("/validation/held_out_target_count")
            .and_then(serde_json::Value::as_u64)
            != Some(audit.validation_target_count as u64)
        || text(result.pointer("/validation/automatic_acceptance_thresholds")) != Some("none")
    {
        audit
            .errors
            .push("model calibration diagnostic or validation scope is invalid".into());
    }
    if string_array(result.get("warnings")).is_none() {
        audit
            .errors
            .push("model calibration warnings must be an array of text".into());
    }
    let expected_cross = serde_json::json!({
        "portable_replay": "complete_search_and_diagnostics",
        "native_replay": "selected_point_model_and_local_identifiability_only"
    });
    if result.get("cross_implementation") != Some(&expected_cross) {
        audit
            .errors
            .push("model calibration cross-implementation scope is invalid".into());
    }
    if result.get("method")
        != Some(&serde_json::json!({
            "family": "bounded_continuous_time_cohort_natural_history_point_calibration",
            "training_loss": "sum_squared_standardized_residuals",
            "target_covariance": "not_modeled",
            "parameter_uncertainty": "not_propagated"
        }))
        || string_array(result.get("limitations")) != Some(facts.limitations.clone())
        || result
            .pointer("/human_gate/status")
            .and_then(serde_json::Value::as_str)
            != Some("awaiting_method_review")
        || bool_value(result.pointer("/human_gate/automatic_model_input_update")) != Some(false)
        || string_array(result.pointer("/human_gate/required_checks"))
            != Some(
                REVIEW_CHECKS
                    .iter()
                    .map(|value| (*value).to_string())
                    .collect(),
            )
    {
        audit
            .errors
            .push("model calibration method, limitations, or Human gate drifted".into());
    }
    dedup_errors(&mut audit.errors);
    audit.complete = audit.errors.is_empty();
    audit.reviewable = audit.complete && audit.status == "awaiting_method_review";
    audit
}

fn result_path_from_request(workspace: &Path) -> Result<String, String> {
    let request_path = resolve_file(workspace, REQUEST_PATH, "model calibration request")?;
    let raw = read_capped(&request_path, MAX_JSON_BYTES, "model calibration request")?;
    let value: serde_json::Value = serde_json::from_slice(&raw)
        .map_err(|error| format!("model calibration request is invalid JSON: {error}"))?;
    let output = text(value.pointer("/output/directory"))
        .ok_or_else(|| "model calibration output.directory is invalid".to_string())?;
    Ok(format!("{output}/manifest.json"))
}

#[tauri::command]
pub fn audit_heor_model_calibration(app: AppHandle) -> Result<ModelCalibrationAudit, String> {
    let workspace = crate::runtime::workspace_dir(&app)?;
    match result_path_from_request(&workspace) {
        Ok(path) => Ok(audit_path(&workspace, &path)),
        Err(error) => Ok(ModelCalibrationAudit {
            errors: vec![error],
            ..ModelCalibrationAudit::default()
        }),
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ModelCalibrationReviewAction {
    Accept,
    Reject,
}

#[derive(Clone, Debug, Eq, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ModelCalibrationChecklist {
    pub question_model_purpose_time_origin_reviewed: bool,
    pub target_provenance_population_alignment_roles_reviewed: bool,
    pub parameter_meaning_bounds_evidence_reviewed: bool,
    pub goodness_of_fit_scaling_covariance_omission_reviewed: bool,
    pub search_convergence_multistart_diagnostics_reviewed: bool,
    pub local_identifiability_alternative_fits_reviewed: bool,
    pub held_out_predictive_validation_reviewed: bool,
    pub uncertainty_structure_downstream_limitations_reviewed: bool,
}

impl ModelCalibrationChecklist {
    fn all_confirmed(&self) -> bool {
        self.question_model_purpose_time_origin_reviewed
            && self.target_provenance_population_alignment_roles_reviewed
            && self.parameter_meaning_bounds_evidence_reviewed
            && self.goodness_of_fit_scaling_covariance_omission_reviewed
            && self.search_convergence_multistart_diagnostics_reviewed
            && self.local_identifiability_alternative_fits_reviewed
            && self.held_out_predictive_validation_reviewed
            && self.uncertainty_structure_downstream_limitations_reviewed
    }
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ModelCalibrationReviewRequest {
    pub project_id: String,
    pub result_path: String,
    pub result_sha256: String,
    pub action: ModelCalibrationReviewAction,
    pub checklist: ModelCalibrationChecklist,
    pub actor_label: String,
    pub rationale: String,
}

#[derive(Clone, Debug, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ModelCalibrationReviewEvent {
    pub schema_version: u32,
    pub sequence: u64,
    pub review_id: String,
    pub project_id: String,
    pub calibration_id: String,
    pub action: ModelCalibrationReviewAction,
    pub result_path: String,
    pub result_sha256: String,
    pub related_artifacts: Vec<crate::heor_approval::ArtifactBinding>,
    pub checklist: ModelCalibrationChecklist,
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
pub struct ModelCalibrationReviewLog {
    pub events: Vec<ModelCalibrationReviewEvent>,
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
    calibration_id: &'a str,
    action: ModelCalibrationReviewAction,
    status: &'static str,
    result_path: &'a str,
    result_sha256: &'a str,
    related_artifacts: &'a [crate::heor_approval::ArtifactBinding],
    checklist: &'a ModelCalibrationChecklist,
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
    calibration_id: &'a str,
    action: ModelCalibrationReviewAction,
    result_path: &'a str,
    result_sha256: &'a str,
    related_artifacts: &'a [crate::heor_approval::ArtifactBinding],
    checklist: &'a ModelCalibrationChecklist,
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
        .join("model-calibration-reviews"))
}

fn review_log_path(root: &Path, project_id: &str) -> Result<PathBuf, String> {
    if !validate_project_id(project_id) {
        return Err("projectId must be a safe identifier".into());
    }
    Ok(root.join(format!("{project_id}.jsonl")))
}

fn hash_review_event(event: &ModelCalibrationReviewEvent) -> Result<String, String> {
    let raw = serde_json::to_vec(&ReviewHashPayload {
        schema_version: event.schema_version,
        sequence: event.sequence,
        review_id: &event.review_id,
        project_id: &event.project_id,
        calibration_id: &event.calibration_id,
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

fn snapshot_bytes(event: &ModelCalibrationReviewEvent) -> Result<Vec<u8>, String> {
    let snapshot = ReviewSnapshot {
        schema_version: REVIEW_SCHEMA,
        review_id: &event.review_id,
        project_id: &event.project_id,
        calibration_id: &event.calibration_id,
        action: event.action,
        status: if event.action == ModelCalibrationReviewAction::Accept {
            "accepted_candidate_for_later_input_selection"
        } else {
            "rejected_candidate_for_later_input_selection"
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
    audit: &ModelCalibrationAudit,
) -> Result<Vec<crate::heor_approval::ArtifactBinding>, String> {
    let result_path = resolve_file(workspace, &audit.result_path, "model calibration result")?;
    let result_raw = read_capped(&result_path, MAX_JSON_BYTES, "model calibration result")?;
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
    add(&result["request"]);
    add(&result["evidence_synthesis"]);
    add(&result["runtime"]["evaluator_source"]);
    add(&result["search"]["trace"]);
    let mut seen = HashSet::new();
    bindings.retain(|binding| seen.insert(binding.path.clone()));
    if bindings.len() != 5 || bindings.iter().any(|binding| !is_sha256(&binding.sha256)) {
        return Err(
            "model calibration review could not bind the complete five-artifact graph".into(),
        );
    }
    for binding in &bindings {
        let path = resolve_file(
            workspace,
            &binding.path,
            "model calibration review artifact",
        )?;
        let raw = read_capped(&path, MAX_SOURCE_BYTES, "model calibration review artifact")?;
        if sha256(&raw) != binding.sha256 {
            return Err("model calibration review artifact changed during submission".into());
        }
    }
    Ok(bindings)
}

fn read_review_events(
    root: &Path,
    workspace: &Path,
    project_id: &str,
) -> Result<Vec<ModelCalibrationReviewEvent>, String> {
    let path = review_log_path(root, project_id)?;
    let raw = match std::fs::read(&path) {
        Ok(raw) => raw,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(format!("model calibration review log unavailable: {error}")),
    };
    if raw.len() > 4 * 1024 * 1024 {
        return Err("model calibration review log exceeds 4 MB".into());
    }
    let mut events = Vec::new();
    let mut previous_hash = None;
    for (index, line) in raw
        .split(|byte| *byte == b'\n')
        .filter(|line| !line.is_empty())
        .enumerate()
    {
        if events.len() >= 2_000 {
            return Err("model calibration review log exceeds 2,000 events".into());
        }
        let event: ModelCalibrationReviewEvent = serde_json::from_slice(line).map_err(|error| {
            format!(
                "model calibration review log line {} is invalid: {error}",
                index + 1
            )
        })?;
        if event.schema_version != REVIEW_EVENT_SCHEMA
            || event.sequence != index as u64 + 1
            || event.project_id != project_id
            || !safe_id(&event.calibration_id)
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
                "model calibration review log line {} violates the event contract",
                index + 1
            ));
        }
        let record = resolve_file(
            workspace,
            &event.record_path,
            "model calibration review record",
        )?;
        let record_raw = read_capped(&record, MAX_JSON_BYTES, "model calibration review record")?;
        if sha256(&record_raw) != event.record_sha256 || record_raw != snapshot_bytes(&event)? {
            return Err(format!(
                "model calibration review log line {} record binding is invalid",
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
    event: &ModelCalibrationReviewEvent,
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
        return Err("model calibration review record path is unsafe".into());
    }
    let target = root.join(relative);
    let parent = target
        .parent()
        .ok_or_else(|| "model calibration review record parent is invalid".to_string())?;
    std::fs::create_dir_all(parent)
        .map_err(|error| format!("model calibration review directory failed: {error}"))?;
    if std::fs::symlink_metadata(parent).is_ok_and(|metadata| metadata.file_type().is_symlink()) {
        return Err("model calibration review directory must not be a symlink".into());
    }
    let raw = snapshot_bytes(event)?;
    if sha256(&raw) != event.record_sha256 {
        return Err("model calibration review record hash changed before write".into());
    }
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&target)
        .map_err(|error| format!("model calibration review record write failed: {error}"))?;
    file.write_all(&raw)
        .and_then(|_| file.sync_all())
        .map_err(|error| format!("model calibration review record write failed: {error}"))
}

fn append_review_event(root: &Path, event: &ModelCalibrationReviewEvent) -> Result<(), String> {
    let path = review_log_path(root, &event.project_id)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("model calibration review log directory failed: {error}"))?;
        crate::runtime::tighten_private(parent);
    }
    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|error| format!("model calibration review log write failed: {error}"))?;
    let mut raw = serde_json::to_vec(event).map_err(|error| error.to_string())?;
    raw.push(b'\n');
    file.write_all(&raw)
        .and_then(|_| file.sync_all())
        .map_err(|error| format!("model calibration review log write failed: {error}"))
}

#[tauri::command]
pub fn append_heor_model_calibration_review(
    app: AppHandle,
    state: tauri::State<ModelCalibrationReviewState>,
    request: ModelCalibrationReviewRequest,
) -> Result<ModelCalibrationReviewEvent, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "model calibration review lock poisoned".to_string())?;
    if !validate_project_id(&request.project_id)
        || !is_sha256(&request.result_sha256)
        || !validate_review_text(&request.actor_label, 120)
        || !validate_review_text(&request.rationale, 2_000)
    {
        return Err(
            "model calibration review request contains invalid identity, hash, or text".into(),
        );
    }
    if request.action == ModelCalibrationReviewAction::Accept && !request.checklist.all_confirmed()
    {
        return Err("all eight model calibration method checks are required for acceptance".into());
    }
    let workspace = crate::runtime::workspace_dir(&app)?;
    let audit = audit_path(&workspace, &request.result_path);
    if !audit.complete || !audit.reviewable {
        return Err(format!(
            "model calibration result is not reviewable: {}",
            audit.errors.join("; ")
        ));
    }
    if audit.result_path != request.result_path
        || audit.result_sha256.as_deref() != Some(&request.result_sha256)
    {
        return Err(
            "model calibration review request does not bind the current audited result".into(),
        );
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
            request.project_id, audit.calibration_id, sequence, timestamp
        )
        .as_bytes(),
    )[..32]
        .to_string();
    let record_path = format!("heor/model-calibration-reviews/{review_id}.json");
    let mut event = ModelCalibrationReviewEvent {
        schema_version: REVIEW_EVENT_SCHEMA,
        sequence,
        review_id,
        project_id: request.project_id,
        calibration_id: audit.calibration_id,
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
pub fn list_heor_model_calibration_reviews(
    app: AppHandle,
    state: tauri::State<ModelCalibrationReviewState>,
    project_id: String,
) -> Result<ModelCalibrationReviewLog, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "model calibration review lock poisoned".to_string())?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    let events = read_review_events(&review_root(&app)?, &workspace, &project_id)?;
    Ok(ModelCalibrationReviewLog {
        chain_head: events.last().map(|event| event.event_hash.clone()),
        events,
        integrity: "verified_unanchored_sha256_chain",
        identity_assurance: REVIEW_ASSURANCE,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn checklist(value: bool) -> ModelCalibrationChecklist {
        ModelCalibrationChecklist {
            question_model_purpose_time_origin_reviewed: value,
            target_provenance_population_alignment_roles_reviewed: value,
            parameter_meaning_bounds_evidence_reviewed: value,
            goodness_of_fit_scaling_covariance_omission_reviewed: value,
            search_convergence_multistart_diagnostics_reviewed: value,
            local_identifiability_alternative_fits_reviewed: value,
            held_out_predictive_validation_reviewed: value,
            uncertainty_structure_downstream_limitations_reviewed: value,
        }
    }

    #[test]
    fn acceptance_requires_all_eight_method_checks() {
        assert!(checklist(true).all_confirmed());
        let mut incomplete = checklist(true);
        incomplete.local_identifiability_alternative_fits_reviewed = false;
        assert!(!incomplete.all_confirmed());
    }

    #[test]
    fn jacobi_reports_rank_deficiency() {
        let eigenvalues = jacobi_eigenvalues(vec![vec![2.0, 2.0], vec![2.0, 2.0]]);
        assert!((eigenvalues[0] - 4.0).abs() < 1e-10);
        assert!(eigenvalues[1].abs() < 1e-10);
    }

    #[test]
    fn native_uniformization_matches_the_portable_reference_fixture() {
        let facts = RequestFacts {
            states: vec!["healthy".into(), "diseased".into(), "dead".into()],
            initial: vec![1.0, 0.0, 0.0],
            cycle_length: 1.0,
            cycles: 12,
            transitions: vec![
                Transition {
                    from: 0,
                    to: 1,
                    parameter_id: Some("incidence".into()),
                    fixed_rate: None,
                },
                Transition {
                    from: 0,
                    to: 2,
                    parameter_id: None,
                    fixed_rate: Some(0.025),
                },
                Transition {
                    from: 1,
                    to: 2,
                    parameter_id: Some("case-fatality".into()),
                    fixed_rate: None,
                },
            ],
            parameters: vec![
                Parameter {
                    id: "incidence".into(),
                    lower: 0.02,
                    upper: 0.25,
                    log_scale: false,
                },
                Parameter {
                    id: "case-fatality".into(),
                    lower: 0.05,
                    upper: 0.4,
                    log_scale: false,
                },
            ],
            targets: vec![
                Target {
                    id: "disease-c3".into(),
                    validation: false,
                    cycle: 3,
                    state: 1,
                    observed: 0.205_892_031_850_962_64,
                    se: 0.02,
                },
                Target {
                    id: "healthy-c5".into(),
                    validation: false,
                    cycle: 5,
                    state: 0,
                    observed: 0.509_156_420_607_549_2,
                    se: 0.02,
                },
                Target {
                    id: "death-c7".into(),
                    validation: false,
                    cycle: 7,
                    state: 2,
                    observed: 0.354_591_320_560_067_15,
                    se: 0.02,
                },
                Target {
                    id: "death-c10".into(),
                    validation: false,
                    cycle: 10,
                    state: 2,
                    observed: 0.511_125_273_428_029_6,
                    se: 0.02,
                },
                Target {
                    id: "disease-c12".into(),
                    validation: true,
                    cycle: 12,
                    state: 1,
                    observed: 0.201_846_524_111_349_7,
                    se: 0.02,
                },
            ],
            ..RequestFacts::default()
        };
        let normalized = vec![(0.11 - 0.02) / (0.25 - 0.02), (0.18 - 0.05) / (0.4 - 0.05)];
        let values = actual_values(&facts, &normalized);
        let predicted = predictions(&facts, &values).expect("native fixture should simulate");
        for target in &facts.targets {
            assert!(
                (predicted[&target.id] - target.observed).abs() < 1e-12,
                "{}",
                target.id
            );
        }
        let (rank, _, _) =
            identifiability(&facts, &normalized).expect("native Jacobian should evaluate");
        assert_eq!(rank, 2);
    }

    #[test]
    fn native_audit_accepts_the_portable_runner_fixture() {
        let repo = Path::new(env!("CARGO_MANIFEST_DIR")).join("../../..");
        let root = std::env::temp_dir().join(format!(
            "ai4heor-model-calibration-native-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).expect("fixture root");
        let prepare = std::process::Command::new("python3")
            .current_dir(&repo)
            .args([
                "-c",
                "import sys; from pathlib import Path; from scripts.dev.test_model_calibration import build_workspace; build_workspace(Path(sys.argv[1]))",
                root.to_str().expect("UTF-8 fixture path"),
            ])
            .status();
        let Ok(prepare) = prepare else {
            let _ = std::fs::remove_dir_all(&root);
            return;
        };
        assert!(prepare.success(), "portable fixture preparation failed");
        let runner = repo
            .join("runtime/skills/core/heor-model-calibration/scripts/run_model_calibration.py");
        let run = std::process::Command::new("python3")
            .args([
                runner.to_str().expect("UTF-8 runner path"),
                "--workspace",
                root.to_str().expect("UTF-8 fixture path"),
                "--request",
                REQUEST_PATH,
            ])
            .status()
            .expect("portable runner should launch");
        assert!(run.success(), "portable model calibration runner failed");
        let result_path = "heor/model-calibration-runs/calibration-test-001/manifest.json";
        let audit = audit_path(&root, result_path);
        let _ = std::fs::remove_dir_all(&root);
        assert!(audit.complete, "{}", audit.errors.join("; "));
        assert!(audit.reviewable);
        assert_eq!(audit.numerical_rank, Some(2));
    }
}
