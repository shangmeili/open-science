//! Native audit and app-owned Human method review for bounded anchored MAIC.
//!
//! The Python evaluator replays every deterministic bootstrap refit. This module
//! independently re-reads the IPD and aggregate evidence, recalibrates weights,
//! and verifies balance, ESS, point effects, and artifact bindings. It does not
//! replay bootstrap uncertainty and must not be described as a second variance
//! implementation.

use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::io::{Read, Write};
use std::path::{Component, Path, PathBuf};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager};

const REQUEST_PATH: &str = "heor/population-adjusted-comparison-request.json";
const REQUEST_SCHEMA: &str = "0.1.0";
const RESULT_SCHEMA: &str = "0.1.0";
const REVIEW_SCHEMA: &str = "0.1.0";
const REVIEW_EVENT_SCHEMA: u32 = 1;
const REVIEW_ASSURANCE: &str = "app_owned_local_human_assertion";
const EVALUATOR: &str = "ai4heor-anchored-maic@0.1.0";
const TOLERANCE: f64 = 1e-8;
const MAX_JSON_BYTES: u64 = 16 * 1024 * 1024;
const MAX_SOURCE_BYTES: u64 = 64 * 1024 * 1024;
const MAX_ROWS: usize = 5_000;
const MAX_MODIFIERS: usize = 8;
const EVALUATOR_BYTES: &[u8] = include_bytes!(
    "../../../../runtime/skills/core/heor-population-adjusted-comparison/scripts/pac_contract.py"
);
const REVIEW_CHECKS: [&str; 8] = [
    "question_estimand_target_common_comparator",
    "randomized_connected_evidence_provenance",
    "effect_modifier_rationale_completeness",
    "ipd_integrity_privacy_missingness",
    "target_moments_overlap",
    "calibration_balance_weights_ess",
    "bootstrap_precision_failures",
    "residual_bias_transportability_downstream",
];

#[derive(Default)]
pub struct PopulationAdjustedComparisonReviewState(pub Mutex<()>);

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PopulationAdjustedComparisonAudit {
    pub complete: bool,
    pub reviewable: bool,
    pub status: String,
    pub execution_id: String,
    pub request_path: String,
    pub request_sha256: Option<String>,
    pub result_path: String,
    pub result_sha256: Option<String>,
    pub row_count: usize,
    pub modifier_count: usize,
    pub effect_measure: String,
    pub ess_overall: Option<f64>,
    pub ess_ratio: Option<f64>,
    pub maximum_weight: Option<f64>,
    pub max_abs_balance_error: Option<f64>,
    pub unadjusted_estimate: Option<f64>,
    pub adjusted_estimate: Option<f64>,
    pub indirect_estimate: Option<f64>,
    pub indirect_se: Option<f64>,
    pub bootstrap_iterations: usize,
    pub bootstrap_failures: usize,
    pub native_scope: String,
    pub limitations: Vec<String>,
    pub errors: Vec<String>,
}

impl Default for PopulationAdjustedComparisonAudit {
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
            modifier_count: 0,
            effect_measure: String::new(),
            ess_overall: None,
            ess_ratio: None,
            maximum_weight: None,
            max_abs_balance_error: None,
            unadjusted_estimate: None,
            adjusted_estimate: None,
            indirect_estimate: None,
            indirect_se: None,
            bootstrap_iterations: 0,
            bootstrap_failures: 0,
            native_scope: "calibration_and_point_estimate_only".into(),
            limitations: Vec::new(),
            errors: Vec::new(),
        }
    }
}

#[derive(Clone, Debug)]
struct SourceRow {
    treatment: String,
    outcome: f64,
    modifiers: Vec<f64>,
}

#[derive(Default)]
struct RequestFacts {
    execution_id: String,
    common: String,
    ipd_treatment: String,
    aggregate_treatment: String,
    ipd_trial: String,
    aggregate_trial: String,
    target_population: String,
    effect_measure: String,
    effect_scale: String,
    source_path: String,
    source_sha256: String,
    aggregate_path: String,
    aggregate_sha256: String,
    evidence_path: String,
    evidence_sha256: String,
    output_directory: String,
    modifier_ids: Vec<String>,
    modifier_columns: Vec<String>,
    targets: Vec<f64>,
    aggregate_effect: f64,
    aggregate_se: f64,
    bootstrap_iterations: usize,
    bootstrap_seed: u64,
    rows: Vec<SourceRow>,
    limitations: Vec<String>,
}

struct Calibration {
    alpha: Vec<f64>,
    weights: Vec<f64>,
    iterations: usize,
    weighted_means: Vec<f64>,
    balance_errors: Vec<f64>,
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

fn is_iso_utc(value: &str) -> bool {
    let bytes = value.as_bytes();
    bytes.len() == 20
        && bytes[4] == b'-'
        && bytes[7] == b'-'
        && bytes[10] == b'T'
        && bytes[13] == b':'
        && bytes[16] == b':'
        && bytes[19] == b'Z'
        && bytes.iter().enumerate().all(|(index, byte)| {
            matches!(index, 4 | 7 | 10 | 13 | 16 | 19) || byte.is_ascii_digit()
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
    common: &str,
    treatment: &str,
    measure: &str,
    errors: &mut Vec<String>,
) -> Vec<SourceRow> {
    let Ok(content) = std::str::from_utf8(raw) else {
        errors.push("MAIC IPD CSV must be UTF-8".into());
        return Vec::new();
    };
    let mut lines = content.lines();
    if lines.next() != Some(columns.join(",").as_str()) {
        errors.push("MAIC IPD CSV columns do not match the request".into());
        return Vec::new();
    }
    let mut subjects = HashSet::new();
    let mut rows = Vec::new();
    let mut arm_counts = [(common, 0usize), (treatment, 0usize)];
    let mut binary = [(common, [0usize; 2]), (treatment, [0usize; 2])];
    for (line_index, line) in lines.enumerate() {
        let cells: Vec<&str> = line.split(',').collect();
        if cells.len() != columns.len()
            || cells
                .iter()
                .any(|cell| cell.is_empty() || cell.trim() != *cell)
        {
            errors.push(format!(
                "MAIC IPD row {} violates the fixed CSV format",
                line_index + 2
            ));
            continue;
        }
        if !safe_subject(cells[0]) || !subjects.insert(cells[0].to_string()) {
            errors.push(format!(
                "MAIC IPD row {} has an unsafe or duplicate subject",
                line_index + 2
            ));
        }
        if cells[1] != common && cells[1] != treatment {
            errors.push(format!(
                "MAIC IPD row {} treatment is outside the randomized arms",
                line_index + 2
            ));
            continue;
        }
        let Ok(outcome) = cells[2].parse::<f64>() else {
            errors.push(format!(
                "MAIC IPD row {} outcome is not numeric",
                line_index + 2
            ));
            continue;
        };
        let modifiers: Result<Vec<f64>, _> = cells[3..]
            .iter()
            .map(|value| value.parse::<f64>())
            .collect();
        let Ok(modifiers) = modifiers else {
            errors.push(format!(
                "MAIC IPD row {} modifier is not numeric",
                line_index + 2
            ));
            continue;
        };
        if !outcome.is_finite()
            || outcome.abs() > 1e12
            || modifiers
                .iter()
                .any(|value| !value.is_finite() || value.abs() > 1e12)
        {
            errors.push(format!(
                "MAIC IPD row {} contains non-finite or unsafe values",
                line_index + 2
            ));
            continue;
        }
        if measure == "log_odds_ratio" && !matches!(outcome, 0.0 | 1.0) {
            errors.push(format!(
                "MAIC IPD row {} binary outcome is not 0 or 1",
                line_index + 2
            ));
            continue;
        }
        for (arm, count) in &mut arm_counts {
            if cells[1] == *arm {
                *count += 1;
            }
        }
        if measure == "log_odds_ratio" {
            for (arm, counts) in &mut binary {
                if cells[1] == *arm {
                    counts[outcome as usize] += 1;
                }
            }
        }
        rows.push(SourceRow {
            treatment: cells[1].into(),
            outcome,
            modifiers,
        });
        if rows.len() > MAX_ROWS {
            errors.push("MAIC IPD exceeds 5,000 rows".into());
            break;
        }
    }
    for (arm, count) in arm_counts {
        if count < 20 {
            errors.push(format!("MAIC randomized arm {arm} has fewer than 20 rows"));
        }
    }
    if measure == "log_odds_ratio" {
        for (arm, counts) in binary {
            if counts[0] < 2 || counts[1] < 2 {
                errors.push(format!(
                    "MAIC randomized arm {arm} lacks two events or non-events"
                ));
            }
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
            "method",
            "evidence_synthesis",
            "source_data",
            "aggregate_evidence",
            "effect_modifiers",
            "effect",
            "weighting",
            "uncertainty",
            "output",
            "study_provenance",
            "human_authorization",
            "limitations",
            "human_gate",
        ],
    ) {
        errors.push("MAIC request fields are not the exact schema 0.1.0 contract".into());
        return facts;
    }
    if text(request.get("schema_version")) != Some(REQUEST_SCHEMA)
        || text(request.get("status")) != Some("ready_for_execution")
    {
        errors.push("MAIC request schema or status is invalid".into());
    }
    facts.execution_id = text(request.get("execution_id")).unwrap_or_default().into();
    if !safe_id(&facts.execution_id) {
        errors.push("MAIC execution_id is invalid".into());
    }
    let method = &request["method"];
    if !exact(
        method,
        &[
            "family",
            "network",
            "trial_relationship",
            "ipd_trial_id",
            "aggregate_trial_id",
            "common_comparator_id",
            "ipd_treatment_id",
            "aggregate_treatment_id",
            "target_population",
            "outcome",
            "timepoint",
            "estimand",
        ],
    ) || text(method.get("family")) != Some("anchored_maic")
        || text(method.get("network")) != Some("connected_two_trial_common_comparator")
        || text(method.get("trial_relationship")) != Some("independent_parallel_randomized_trials")
    {
        errors.push(
            "MAIC method is outside the connected independent randomized anchored boundary".into(),
        );
    }
    facts.ipd_trial = text(method.get("ipd_trial_id")).unwrap_or_default().into();
    facts.aggregate_trial = text(method.get("aggregate_trial_id"))
        .unwrap_or_default()
        .into();
    facts.common = text(method.get("common_comparator_id"))
        .unwrap_or_default()
        .into();
    facts.ipd_treatment = text(method.get("ipd_treatment_id"))
        .unwrap_or_default()
        .into();
    facts.aggregate_treatment = text(method.get("aggregate_treatment_id"))
        .unwrap_or_default()
        .into();
    facts.target_population = text(method.get("target_population"))
        .unwrap_or_default()
        .into();
    let role_ids = [
        &facts.common,
        &facts.ipd_treatment,
        &facts.aggregate_treatment,
    ];
    if !safe_id(&facts.ipd_trial)
        || !safe_id(&facts.aggregate_trial)
        || facts.ipd_trial == facts.aggregate_trial
        || role_ids.iter().any(|value| !safe_id(value))
        || role_ids.iter().collect::<HashSet<_>>().len() != 3
        || facts.target_population.is_empty()
        || ["outcome", "timepoint", "estimand"]
            .iter()
            .any(|field| text(method.get(*field)).is_none())
    {
        errors.push(
            "MAIC trial, treatment, target, outcome, timepoint, or estimand is invalid".into(),
        );
    }
    let effect = &request["effect"];
    facts.effect_measure = text(effect.get("measure")).unwrap_or_default().into();
    facts.effect_scale = text(effect.get("scale")).unwrap_or_default().into();
    if !exact(
        effect,
        &[
            "measure",
            "scale",
            "confidence_level",
            "favorable_direction",
        ],
    ) || !matches!(
        facts.effect_measure.as_str(),
        "log_odds_ratio" | "mean_difference"
    ) || (facts.effect_measure == "log_odds_ratio" && facts.effect_scale != "logit")
        || (facts.effect_measure == "mean_difference" && facts.effect_scale != "identity")
        || finite(effect.get("confidence_level")) != Some(0.95)
        || !matches!(
            text(effect.get("favorable_direction")),
            Some("lower" | "higher")
        )
    {
        errors.push("MAIC effect measure, scale, confidence level, or direction is invalid".into());
    }
    let evidence = &request["evidence_synthesis"];
    let included = string_array(evidence.get("included_record_ids")).unwrap_or_default();
    if !exact(evidence, &["path", "sha256", "included_record_ids"])
        || included.len() < 2
        || included.iter().any(|id| !safe_id(id))
        || included.iter().collect::<HashSet<_>>().len() != included.len()
    {
        errors.push("MAIC evidence record IDs are invalid".into());
    }
    if let Some((path, _)) = bound_bytes(
        workspace,
        evidence,
        None,
        "MAIC evidence synthesis",
        MAX_JSON_BYTES,
        errors,
    ) {
        facts.evidence_path = path;
        facts.evidence_sha256 = text(evidence.get("sha256")).unwrap_or_default().into();
    }

    let Some(modifiers) = request
        .get("effect_modifiers")
        .and_then(serde_json::Value::as_array)
    else {
        errors.push("MAIC effect_modifiers must be an array".into());
        return facts;
    };
    if !(1..=MAX_MODIFIERS).contains(&modifiers.len()) {
        errors.push("MAIC must declare one to eight effect modifiers".into());
    }
    let mut modifier_records = HashSet::new();
    for modifier in modifiers {
        if !exact(
            modifier,
            &["id", "column", "label", "rationale", "evidence_record_ids"],
        ) {
            errors.push("MAIC effect modifier fields are invalid".into());
            continue;
        }
        let id = text(modifier.get("id")).unwrap_or_default();
        let column = text(modifier.get("column")).unwrap_or_default();
        let records = string_array(modifier.get("evidence_record_ids")).unwrap_or_default();
        if !safe_id(id)
            || !safe_id(column)
            || matches!(column, "subject_id" | "treatment" | "outcome")
            || text(modifier.get("label")).is_none()
            || text(modifier.get("rationale")).is_none()
            || records.is_empty()
            || records.iter().any(|record| !included.contains(record))
        {
            errors.push("MAIC effect modifier identity, rationale, or evidence is invalid".into());
        }
        if !modifier_records.insert((id.to_string(), column.to_string())) {
            errors.push("MAIC effect modifiers must be unique".into());
        }
        facts.modifier_ids.push(id.into());
        facts.modifier_columns.push(column.into());
    }
    if facts.modifier_ids.iter().collect::<HashSet<_>>().len() != facts.modifier_ids.len()
        || facts.modifier_columns.iter().collect::<HashSet<_>>().len()
            != facts.modifier_columns.len()
    {
        errors.push("MAIC modifier IDs and columns must each be unique".into());
    }

    let source = &request["source_data"];
    let expected_columns: Vec<String> = ["subject_id", "treatment", "outcome"]
        .into_iter()
        .map(str::to_string)
        .chain(facts.modifier_columns.iter().cloned())
        .collect();
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
            "treatment_assignment",
        ],
    ) || !matches!(
        text(source.get("classification")),
        Some("public" | "non_sensitive" | "restricted")
    ) || text(source.get("execution_boundary")) != Some("local_only")
        || text(source.get("format")) != Some("ipd_csv")
        || bool_value(source.get("contains_direct_identifiers")) != Some(false)
        || text(source.get("missing_policy")) != Some("reject")
        || text(source.get("treatment_assignment")) != Some("randomized_parallel_two_arm")
        || string_array(source.get("columns")) != Some(expected_columns.clone())
    {
        errors.push("MAIC source data contract is invalid".into());
    }
    if let Some((path, raw)) = bound_bytes(
        workspace,
        source,
        None,
        "MAIC IPD",
        MAX_SOURCE_BYTES,
        errors,
    ) {
        facts.source_path = path;
        facts.source_sha256 = text(source.get("sha256")).unwrap_or_default().into();
        facts.rows = parse_source(
            &raw,
            &expected_columns,
            &facts.common,
            &facts.ipd_treatment,
            &facts.effect_measure,
            errors,
        );
        if source.get("row_count").and_then(serde_json::Value::as_u64)
            != Some(facts.rows.len() as u64)
        {
            errors.push("MAIC source row_count does not match current bytes".into());
        }
    }

    let aggregate_binding = &request["aggregate_evidence"];
    if !exact(aggregate_binding, &["path", "sha256"]) {
        errors.push("MAIC aggregate evidence binding fields are invalid".into());
    }
    if let Some((path, raw)) = bound_bytes(
        workspace,
        aggregate_binding,
        None,
        "MAIC aggregate evidence",
        MAX_JSON_BYTES,
        errors,
    ) {
        facts.aggregate_path = path;
        facts.aggregate_sha256 = text(aggregate_binding.get("sha256"))
            .unwrap_or_default()
            .into();
        let aggregate: serde_json::Value = match serde_json::from_slice(&raw) {
            Ok(value) => value,
            Err(error) => {
                errors.push(format!("MAIC aggregate evidence is invalid JSON: {error}"));
                serde_json::Value::Null
            }
        };
        if !exact(
            &aggregate,
            &[
                "schema_version",
                "trial_id",
                "target_population",
                "common_comparator_id",
                "aggregate_treatment_id",
                "outcome",
                "timepoint",
                "effect",
                "target_moments",
                "source_ids",
                "limitations",
            ],
        ) || text(aggregate.get("schema_version")) != Some(REQUEST_SCHEMA)
            || text(aggregate.get("trial_id")) != Some(&facts.aggregate_trial)
            || text(aggregate.get("target_population")) != Some(&facts.target_population)
            || text(aggregate.get("common_comparator_id")) != Some(&facts.common)
            || text(aggregate.get("aggregate_treatment_id")) != Some(&facts.aggregate_treatment)
            || aggregate.get("outcome") != method.get("outcome")
            || aggregate.get("timepoint") != method.get("timepoint")
        {
            errors.push("MAIC aggregate evidence identity does not match the request".into());
        }
        let aggregate_effect = &aggregate["effect"];
        facts.aggregate_effect = finite(aggregate_effect.get("estimate")).unwrap_or(f64::NAN);
        facts.aggregate_se = finite(aggregate_effect.get("se")).unwrap_or(f64::NAN);
        if !exact(aggregate_effect, &["measure", "scale", "estimate", "se"])
            || text(aggregate_effect.get("measure")) != Some(&facts.effect_measure)
            || text(aggregate_effect.get("scale")) != Some(&facts.effect_scale)
            || !facts.aggregate_effect.is_finite()
            || facts.aggregate_effect.abs() > 100.0
            || !facts.aggregate_se.is_finite()
            || !(0.0..=100.0).contains(&facts.aggregate_se)
            || facts.aggregate_se == 0.0
        {
            errors.push("MAIC aggregate effect or standard error is invalid".into());
        }
        let moments = aggregate
            .get("target_moments")
            .and_then(serde_json::Value::as_array);
        if moments.is_none_or(|values| values.len() != facts.modifier_ids.len()) {
            errors.push("MAIC target moments must cover every modifier".into());
        } else if let Some(moments) = moments {
            for (index, moment) in moments.iter().enumerate() {
                let target = finite(moment.get("mean"));
                if !exact(moment, &["id", "mean"])
                    || text(moment.get("id")) != Some(&facts.modifier_ids[index])
                    || target.is_none_or(|value| value.abs() > 1e12)
                {
                    errors.push("MAIC target moment is invalid or out of order".into());
                }
                facts.targets.push(target.unwrap_or_default());
            }
        }
        let source_ids = string_array(aggregate.get("source_ids")).unwrap_or_default();
        if source_ids.is_empty() || source_ids.iter().any(|id| !included.contains(id)) {
            errors.push("MAIC aggregate source IDs are not bound evidence records".into());
        }
        if string_array(aggregate.get("limitations")).is_none_or(|values| values.is_empty()) {
            errors.push("MAIC aggregate limitations are invalid".into());
        }
    }
    let weighting = &request["weighting"];
    if !exact(
        weighting,
        &[
            "method",
            "balance_moments",
            "normalization",
            "convergence_tolerance",
            "max_iterations",
            "weight_cap",
            "trimming",
        ],
    ) || text(weighting.get("method")) != Some("method_of_moments_exponential_tilting")
        || text(weighting.get("balance_moments")) != Some("means")
        || text(weighting.get("normalization")) != Some("mean_one")
        || finite(weighting.get("convergence_tolerance")) != Some(1e-10)
        || weighting
            .get("max_iterations")
            .and_then(serde_json::Value::as_u64)
            != Some(200)
        || text(weighting.get("weight_cap")) != Some("none")
        || text(weighting.get("trimming")) != Some("none")
    {
        errors.push("MAIC weighting contract is invalid".into());
    }
    let uncertainty = &request["uncertainty"];
    facts.bootstrap_iterations = uncertainty
        .get("iterations")
        .and_then(serde_json::Value::as_u64)
        .unwrap_or_default() as usize;
    facts.bootstrap_seed = uncertainty
        .get("seed")
        .and_then(serde_json::Value::as_u64)
        .unwrap_or_default();
    if !exact(
        uncertainty,
        &["method", "iterations", "seed", "prng", "failure_policy"],
    ) || text(uncertainty.get("method")) != Some("stratified_nonparametric_bootstrap_refit")
        || !(1_000..=5_000).contains(&facts.bootstrap_iterations)
        || uncertainty
            .get("seed")
            .and_then(serde_json::Value::as_u64)
            .is_none()
        || uncertainty.get("prng")
            != Some(&serde_json::json!({"algorithm": "pcg32-xsh-rr", "version": "1"}))
        || text(uncertainty.get("failure_policy")) != Some("retain_and_block_review")
    {
        errors.push("MAIC uncertainty contract is invalid".into());
    }
    let output = &request["output"];
    facts.output_directory = text(output.get("directory")).unwrap_or_default().into();
    if !exact(output, &["directory"])
        || facts.output_directory
            != format!(
                "heor/population-adjusted-comparison-runs/{}",
                facts.execution_id
            )
    {
        errors.push("MAIC output directory is invalid".into());
    }
    let provenance = request
        .get("study_provenance")
        .and_then(serde_json::Value::as_array);
    if provenance.is_none_or(|rows| rows.len() != 2) {
        errors.push("MAIC study provenance must cover exactly two trials".into());
    } else if let Some(provenance) = provenance {
        for (index, expected_trial) in [&facts.ipd_trial, &facts.aggregate_trial]
            .iter()
            .enumerate()
        {
            let row = &provenance[index];
            let record_ids = string_array(row.get("evidence_record_ids")).unwrap_or_default();
            if !exact(row, &["trial_id", "evidence_record_ids", "risk_of_bias"])
                || text(row.get("trial_id")) != Some(expected_trial)
                || record_ids.is_empty()
                || record_ids.iter().any(|record| !included.contains(record))
                || !matches!(
                    text(row.get("risk_of_bias")),
                    Some("low" | "some_concerns" | "high" | "awaiting_human_review")
                )
            {
                errors.push(format!("MAIC study provenance row {index} is invalid"));
            }
        }
    }
    let authorization = &request["human_authorization"];
    if !exact(authorization, &["actor", "authorized_at", "scope"])
        || text(authorization.get("actor")).is_none()
        || text(authorization.get("authorized_at")).is_none_or(|value| !is_iso_utc(value))
        || text(authorization.get("scope")) != Some("execute_local_anchored_maic")
    {
        errors.push("MAIC Human command authorization is invalid".into());
    }
    facts.limitations = string_array(request.get("limitations")).unwrap_or_default();
    if facts.limitations.is_empty() {
        errors.push("MAIC limitations must be non-empty".into());
    }
    if !exact(&request["human_gate"], &["status", "required_checks"])
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
        errors.push("MAIC Human gate must contain the exact eight checks".into());
    }
    facts
}

fn solve(matrix: &[Vec<f64>], vector: &[f64]) -> Result<Vec<f64>, String> {
    let size = vector.len();
    let mut augmented: Vec<Vec<f64>> = matrix
        .iter()
        .enumerate()
        .map(|(index, row)| {
            let mut values = row.clone();
            values.push(vector[index]);
            values
        })
        .collect();
    for column in 0..size {
        let pivot = (column..size)
            .max_by(|left, right| {
                augmented[*left][column]
                    .abs()
                    .total_cmp(&augmented[*right][column].abs())
            })
            .ok_or_else(|| "calibration Hessian is singular".to_string())?;
        if augmented[pivot][column].abs() < 1e-14 {
            return Err("calibration Hessian is singular".into());
        }
        augmented.swap(column, pivot);
        let scale = augmented[column][column];
        for value in &mut augmented[column] {
            *value /= scale;
        }
        let pivot_row = augmented[column].clone();
        for (row_index, row) in augmented.iter_mut().enumerate() {
            if row_index == column {
                continue;
            }
            let factor = row[column];
            for index in column..=size {
                row[index] -= factor * pivot_row[index];
            }
        }
    }
    let result: Vec<f64> = augmented.iter().map(|row| row[size]).collect();
    if result.iter().any(|value| !value.is_finite()) {
        return Err("calibration solve produced non-finite values".into());
    }
    Ok(result)
}

fn normalized_weights(centered: &[Vec<f64>], alpha: &[f64]) -> Result<Vec<f64>, String> {
    let logits: Vec<f64> = centered
        .iter()
        .map(|row| {
            row.iter()
                .zip(alpha)
                .map(|(value, coefficient)| value * coefficient)
                .sum()
        })
        .collect();
    if logits.iter().any(|value| !value.is_finite()) {
        return Err("calibration logits are non-finite".into());
    }
    let shift = logits.iter().copied().fold(f64::NEG_INFINITY, f64::max);
    let raw: Vec<f64> = logits.iter().map(|value| (value - shift).exp()).collect();
    let total: f64 = raw.iter().sum();
    if !total.is_finite() || total <= 0.0 {
        return Err("calibration weights are invalid".into());
    }
    let scale = raw.len() as f64 / total;
    let weights: Vec<f64> = raw.iter().map(|value| value * scale).collect();
    if weights
        .iter()
        .any(|value| !value.is_finite() || *value <= 0.0)
    {
        return Err("calibration weights are not finite and positive".into());
    }
    Ok(weights)
}

fn gradient(centered: &[Vec<f64>], weights: &[f64]) -> Vec<f64> {
    let total: f64 = weights.iter().sum();
    (0..centered[0].len())
        .map(|index| {
            centered
                .iter()
                .zip(weights)
                .map(|(row, weight)| row[index] * weight)
                .sum::<f64>()
                / total
        })
        .collect()
}

fn calibrate(rows: &[SourceRow], targets: &[f64]) -> Result<Calibration, String> {
    if rows.is_empty()
        || targets.is_empty()
        || rows.iter().any(|row| row.modifiers.len() != targets.len())
    {
        return Err("calibration inputs are incomplete".into());
    }
    let centered: Vec<Vec<f64>> = rows
        .iter()
        .map(|row| {
            row.modifiers
                .iter()
                .zip(targets)
                .map(|(value, target)| value - target)
                .collect()
        })
        .collect();
    let mut alpha = vec![0.0; targets.len()];
    let mut iteration = 0;
    loop {
        let weights = normalized_weights(&centered, &alpha)?;
        let current_gradient = gradient(&centered, &weights);
        let norm = current_gradient
            .iter()
            .copied()
            .map(f64::abs)
            .fold(0.0, f64::max);
        if norm <= 1e-10 {
            break;
        }
        if iteration == 200 {
            return Err("calibration did not converge within 200 iterations".into());
        }
        let total: f64 = weights.iter().sum();
        let hessian: Vec<Vec<f64>> = (0..targets.len())
            .map(|left| {
                (0..targets.len())
                    .map(|right| {
                        centered
                            .iter()
                            .zip(&weights)
                            .map(|(row, weight)| weight * row[left] * row[right])
                            .sum::<f64>()
                            / total
                            - current_gradient[left] * current_gradient[right]
                    })
                    .collect()
            })
            .collect();
        let delta = solve(&hessian, &current_gradient)?;
        let mut step = 1.0;
        let mut accepted = None;
        for _ in 0..40 {
            let candidate: Vec<f64> = alpha
                .iter()
                .zip(&delta)
                .map(|(value, change)| value - step * change)
                .collect();
            let candidate_weights = normalized_weights(&centered, &candidate)?;
            let candidate_norm = gradient(&centered, &candidate_weights)
                .iter()
                .copied()
                .map(f64::abs)
                .fold(0.0, f64::max);
            if candidate_norm < norm {
                accepted = Some(candidate);
                break;
            }
            step *= 0.5;
        }
        alpha = accepted
            .ok_or_else(|| "calibration line search could not reduce imbalance".to_string())?;
        iteration += 1;
    }
    let weights = normalized_weights(&centered, &alpha)?;
    let total: f64 = weights.iter().sum();
    let weighted_means: Vec<f64> = (0..targets.len())
        .map(|index| {
            rows.iter()
                .zip(&weights)
                .map(|(row, weight)| row.modifiers[index] * weight)
                .sum::<f64>()
                / total
        })
        .collect();
    let balance_errors: Vec<f64> = weighted_means
        .iter()
        .zip(targets)
        .map(|(value, target)| value - target)
        .collect();
    if balance_errors.iter().any(|value| value.abs() > 1e-9) {
        return Err("calibration residual balance exceeds tolerance".into());
    }
    Ok(Calibration {
        alpha,
        weights,
        iterations: iteration,
        weighted_means,
        balance_errors,
    })
}

fn ess(weights: &[f64]) -> f64 {
    weights.iter().sum::<f64>().powi(2) / weights.iter().map(|value| value * value).sum::<f64>()
}

fn quantile(values: &[f64], probability: f64) -> f64 {
    let mut ordered = values.to_vec();
    ordered.sort_by(f64::total_cmp);
    let position = probability * (ordered.len() - 1) as f64;
    let lower = position.floor() as usize;
    let upper = position.ceil() as usize;
    ordered[lower] * (1.0 - (position - lower as f64)) + ordered[upper] * (position - lower as f64)
}

fn coefficient_of_variation(weights: &[f64]) -> f64 {
    let mean = weights.iter().sum::<f64>() / weights.len() as f64;
    (weights
        .iter()
        .map(|weight| (weight - mean).powi(2))
        .sum::<f64>()
        / weights.len() as f64)
        .sqrt()
        / mean
}

fn natural_effect(measure: &str, value: f64) -> f64 {
    if measure == "log_odds_ratio" {
        value.exp()
    } else {
        value
    }
}

fn validate_draw_rows(raw: &[u8], facts: &RequestFacts, errors: &mut Vec<String>) {
    let Ok(content) = std::str::from_utf8(raw) else {
        errors.push("MAIC bootstrap draws must be UTF-8 CSV".into());
        return;
    };
    let mut lines = content.lines();
    if lines.next() != Some("iteration,status,ipd_effect,indirect_effect,error") {
        errors.push("MAIC bootstrap draw columns are invalid".into());
        return;
    }
    let mut count = 0usize;
    for (index, line) in lines.enumerate() {
        let cells: Vec<&str> = line.split(',').collect();
        let ipd = cells.get(2).and_then(|value| value.parse::<f64>().ok());
        let indirect = cells.get(3).and_then(|value| value.parse::<f64>().ok());
        if cells.len() != 5
            || cells[0].parse::<usize>().ok() != Some(index + 1)
            || cells[1] != "ok"
            || !cells[4].is_empty()
            || ipd.is_none_or(|value| !value.is_finite() || value.abs() > 100.0)
            || indirect.is_none_or(|value| !value.is_finite() || value.abs() > 100.0)
            || (ipd.unwrap_or_default() - facts.aggregate_effect - indirect.unwrap_or_default())
                .abs()
                > TOLERANCE
        {
            errors.push(format!(
                "MAIC bootstrap draw {} is structurally invalid",
                index + 1
            ));
            return;
        }
        count += 1;
    }
    if count != facts.bootstrap_iterations {
        errors.push("MAIC bootstrap draw count does not match the request".into());
    }
}

fn effect_estimate(
    rows: &[SourceRow],
    weights: &[f64],
    common: &str,
    treatment: &str,
    measure: &str,
) -> Result<f64, String> {
    let arm_mean = |arm: &str| -> Result<f64, String> {
        let total: f64 = rows
            .iter()
            .zip(weights)
            .filter(|(row, _)| row.treatment == arm)
            .map(|(_, weight)| weight)
            .sum();
        if total <= 0.0 {
            return Err("weighted arm has no mass".into());
        }
        Ok(rows
            .iter()
            .zip(weights)
            .filter(|(row, _)| row.treatment == arm)
            .map(|(row, weight)| row.outcome * weight)
            .sum::<f64>()
            / total)
    };
    let common_mean = arm_mean(common)?;
    let treatment_mean = arm_mean(treatment)?;
    let estimate = if measure == "mean_difference" {
        treatment_mean - common_mean
    } else if measure == "log_odds_ratio" {
        if !(0.0..1.0).contains(&common_mean) || !(0.0..1.0).contains(&treatment_mean) {
            return Err("weighted binary risks must be strictly between zero and one".into());
        }
        (treatment_mean / (1.0 - treatment_mean)).ln() - (common_mean / (1.0 - common_mean)).ln()
    } else {
        return Err("effect measure is unsupported".into());
    };
    if !estimate.is_finite() || estimate.abs() > 100.0 {
        return Err("effect estimate is outside the numeric safety bound".into());
    }
    Ok(estimate)
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

fn audit_path(workspace: &Path, result_path: &str) -> PopulationAdjustedComparisonAudit {
    let mut audit = PopulationAdjustedComparisonAudit {
        result_path: result_path.into(),
        ..PopulationAdjustedComparisonAudit::default()
    };
    let request_path = match resolve_file(workspace, REQUEST_PATH, "MAIC request") {
        Ok(path) => path,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    let request_raw = match read_capped(&request_path, MAX_JSON_BYTES, "MAIC request") {
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
            audit
                .errors
                .push(format!("MAIC request is invalid JSON: {error}"));
            return audit;
        }
    };
    let facts = validate_request(workspace, &request, &mut audit.errors);
    audit.execution_id = facts.execution_id.clone();
    audit.row_count = facts.rows.len();
    audit.modifier_count = facts.modifier_ids.len();
    audit.effect_measure = facts.effect_measure.clone();
    audit.bootstrap_iterations = facts.bootstrap_iterations;
    audit.limitations = facts.limitations.clone();
    if !audit.errors.is_empty() {
        dedup_errors(&mut audit.errors);
        return audit;
    }
    let result_file = match resolve_file(workspace, result_path, "MAIC result") {
        Ok(path) => path,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    let result_raw = match read_capped(&result_file, MAX_JSON_BYTES, "MAIC result") {
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
                .push(format!("MAIC result is invalid JSON: {error}"));
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
            "aggregate_evidence",
            "evidence_synthesis",
            "runtime",
            "method",
            "calibration",
            "effects",
            "bootstrap",
            "cross_implementation",
            "warnings",
            "limitations",
            "human_gate",
        ],
    ) || text(result.get("schema_version")) != Some(RESULT_SCHEMA)
        || text(result.get("execution_id")) != Some(&facts.execution_id)
        || text(result.get("status")) != Some("awaiting_method_review")
    {
        audit
            .errors
            .push("MAIC result top-level contract is invalid".into());
    }
    audit.status = text(result.get("status")).unwrap_or("invalid").into();
    if !exact(&result["request"], &["path", "sha256"])
        || text(result.pointer("/request/path")) != Some(REQUEST_PATH)
        || text(result.pointer("/request/sha256")) != audit.request_sha256.as_deref()
    {
        audit
            .errors
            .push("MAIC result does not bind the exact current request".into());
    }
    for (field, path, hash) in [
        ("source_data", &facts.source_path, &facts.source_sha256),
        (
            "aggregate_evidence",
            &facts.aggregate_path,
            &facts.aggregate_sha256,
        ),
        (
            "evidence_synthesis",
            &facts.evidence_path,
            &facts.evidence_sha256,
        ),
    ] {
        if !exact(&result[field], &["path", "sha256"])
            || text(result.pointer(&format!("/{field}/path"))) != Some(path)
            || text(result.pointer(&format!("/{field}/sha256"))) != Some(hash)
        {
            audit
                .errors
                .push(format!("MAIC result {field} binding drifted"));
        }
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
        || !exact(&runtime["evaluator_source"], &["path", "sha256"])
    {
        audit.errors.push("MAIC runtime identity is invalid".into());
    }
    if let Some((_, raw)) = bound_bytes(
        workspace,
        &runtime["evaluator_source"],
        None,
        "MAIC evaluator",
        MAX_SOURCE_BYTES,
        &mut audit.errors,
    ) {
        if raw != EVALUATOR_BYTES
            || text(runtime.pointer("/evaluator_source/sha256"))
                != Some(sha256(EVALUATOR_BYTES).as_str())
        {
            audit
                .errors
                .push("MAIC evaluator is not the current bundled source".into());
        }
    }
    let method = &result["method"];
    if !exact(
        method,
        &[
            "family",
            "target_population",
            "ipd_trial_id",
            "aggregate_trial_id",
            "common_comparator_id",
            "ipd_treatment_id",
            "aggregate_treatment_id",
            "effect_measure",
            "scale",
        ],
    ) || text(method.get("family")) != Some("anchored_maic")
        || text(method.get("target_population")) != Some(&facts.target_population)
        || text(method.get("ipd_trial_id")) != Some(&facts.ipd_trial)
        || text(method.get("aggregate_trial_id")) != Some(&facts.aggregate_trial)
        || text(method.get("common_comparator_id")) != Some(&facts.common)
        || text(method.get("ipd_treatment_id")) != Some(&facts.ipd_treatment)
        || text(method.get("aggregate_treatment_id")) != Some(&facts.aggregate_treatment)
        || text(method.get("effect_measure")) != Some(&facts.effect_measure)
        || text(method.get("scale")) != Some(&facts.effect_scale)
    {
        audit
            .errors
            .push("MAIC result method does not match the request".into());
    }
    let calibration = match calibrate(&facts.rows, &facts.targets) {
        Ok(value) => value,
        Err(error) => {
            audit
                .errors
                .push(format!("native MAIC calibration failed: {error}"));
            dedup_errors(&mut audit.errors);
            return audit;
        }
    };
    let calibration_result = &result["calibration"];
    let expected_ess = ess(&calibration.weights);
    audit.ess_overall = Some(expected_ess);
    audit.ess_ratio = Some(expected_ess / facts.rows.len() as f64);
    audit.maximum_weight = calibration.weights.iter().copied().max_by(f64::total_cmp);
    audit.max_abs_balance_error = calibration
        .balance_errors
        .iter()
        .copied()
        .map(f64::abs)
        .max_by(f64::total_cmp);
    if !exact(
        calibration_result,
        &[
            "converged",
            "iterations",
            "coefficients",
            "balance",
            "max_abs_balance_error",
            "ess",
            "weights",
        ],
    ) || bool_value(calibration_result.get("converged")) != Some(true)
        || !exact(
            &calibration_result["ess"],
            &["overall", "common_comparator", "ipd_treatment"],
        )
        || !exact(
            &calibration_result["weights"],
            &[
                "minimum",
                "p01",
                "p05",
                "median",
                "p95",
                "p99",
                "maximum",
                "coefficient_of_variation",
            ],
        )
        || calibration_result
            .get("iterations")
            .and_then(serde_json::Value::as_u64)
            != Some(calibration.iterations as u64)
        || !close(
            calibration_result.get("max_abs_balance_error"),
            audit.max_abs_balance_error.unwrap_or_default(),
        )
        || !close(calibration_result.pointer("/ess/overall"), expected_ess)
        || !close(
            calibration_result.pointer("/weights/minimum"),
            calibration
                .weights
                .iter()
                .copied()
                .min_by(f64::total_cmp)
                .unwrap_or_default(),
        )
        || !close(
            calibration_result.pointer("/weights/p01"),
            quantile(&calibration.weights, 0.01),
        )
        || !close(
            calibration_result.pointer("/weights/p05"),
            quantile(&calibration.weights, 0.05),
        )
        || !close(
            calibration_result.pointer("/weights/median"),
            quantile(&calibration.weights, 0.5),
        )
        || !close(
            calibration_result.pointer("/weights/p95"),
            quantile(&calibration.weights, 0.95),
        )
        || !close(
            calibration_result.pointer("/weights/p99"),
            quantile(&calibration.weights, 0.99),
        )
        || !close(
            calibration_result.pointer("/weights/maximum"),
            audit.maximum_weight.unwrap_or_default(),
        )
        || !close(
            calibration_result.pointer("/weights/coefficient_of_variation"),
            coefficient_of_variation(&calibration.weights),
        )
    {
        audit
            .errors
            .push("MAIC calibration summary differs from native recomputation".into());
    }
    let coefficients = calibration_result
        .get("coefficients")
        .and_then(serde_json::Value::as_array);
    if coefficients.is_none_or(|values| values.len() != facts.modifier_ids.len()) {
        audit
            .errors
            .push("MAIC calibration coefficients are incomplete".into());
    } else if let Some(coefficients) = coefficients {
        for (index, row) in coefficients.iter().enumerate() {
            if !exact(row, &["id", "value"])
                || text(row.get("id")) != Some(&facts.modifier_ids[index])
                || !close(row.get("value"), calibration.alpha[index])
            {
                audit
                    .errors
                    .push("MAIC calibration coefficient differs from native recomputation".into());
            }
        }
    }
    let balance = calibration_result
        .get("balance")
        .and_then(serde_json::Value::as_array);
    if balance.is_none_or(|values| values.len() != facts.modifier_ids.len()) {
        audit.errors.push("MAIC balance rows are incomplete".into());
    } else if let Some(balance) = balance {
        for (index, row) in balance.iter().enumerate() {
            let unweighted = facts
                .rows
                .iter()
                .map(|source| source.modifiers[index])
                .sum::<f64>()
                / facts.rows.len() as f64;
            if !exact(
                row,
                &[
                    "id",
                    "target_mean",
                    "unweighted_mean",
                    "weighted_mean",
                    "weighted_minus_target",
                ],
            ) || text(row.get("id")) != Some(&facts.modifier_ids[index])
                || !close(row.get("target_mean"), facts.targets[index])
                || !close(row.get("unweighted_mean"), unweighted)
                || !close(row.get("weighted_mean"), calibration.weighted_means[index])
                || !close(
                    row.get("weighted_minus_target"),
                    calibration.balance_errors[index],
                )
            {
                audit
                    .errors
                    .push("MAIC balance row differs from native recomputation".into());
            }
        }
    }
    let arm_ess = |arm: &str| {
        let weights: Vec<f64> = facts
            .rows
            .iter()
            .zip(&calibration.weights)
            .filter(|(row, _)| row.treatment == arm)
            .map(|(_, weight)| *weight)
            .collect();
        ess(&weights)
    };
    if !close(
        calibration_result.pointer("/ess/common_comparator"),
        arm_ess(&facts.common),
    ) || !close(
        calibration_result.pointer("/ess/ipd_treatment"),
        arm_ess(&facts.ipd_treatment),
    ) {
        audit
            .errors
            .push("MAIC arm ESS differs from native recomputation".into());
    }
    let unadjusted = effect_estimate(
        &facts.rows,
        &vec![1.0; facts.rows.len()],
        &facts.common,
        &facts.ipd_treatment,
        &facts.effect_measure,
    );
    let adjusted = effect_estimate(
        &facts.rows,
        &calibration.weights,
        &facts.common,
        &facts.ipd_treatment,
        &facts.effect_measure,
    );
    match (unadjusted, adjusted) {
        (Ok(unadjusted), Ok(adjusted)) => {
            let indirect = adjusted - facts.aggregate_effect;
            let effects = &result["effects"];
            let unadjusted_result = &effects["unadjusted_ipd_vs_common"];
            let adjusted_result = &effects["adjusted_ipd_vs_common"];
            let aggregate_result = &effects["aggregate_vs_common"];
            let indirect_result = &effects["indirect_ipd_vs_aggregate"];
            audit.unadjusted_estimate = Some(unadjusted);
            audit.adjusted_estimate = Some(adjusted);
            audit.indirect_estimate = Some(indirect);
            let bootstrap_se = finite(adjusted_result.get("bootstrap_se"));
            let indirect_se = bootstrap_se.map(|value| value.hypot(facts.aggregate_se));
            let lower = indirect_se.map(|value| indirect - 1.959_963_984_540_054 * value);
            let upper = indirect_se.map(|value| indirect + 1.959_963_984_540_054 * value);
            audit.indirect_se = indirect_se;
            if !exact(
                effects,
                &[
                    "unadjusted_ipd_vs_common",
                    "adjusted_ipd_vs_common",
                    "aggregate_vs_common",
                    "indirect_ipd_vs_aggregate",
                ],
            ) || !exact(unadjusted_result, &["estimate", "natural_estimate"])
                || !exact(
                    adjusted_result,
                    &["estimate", "bootstrap_se", "natural_estimate"],
                )
                || !exact(aggregate_result, &["estimate", "se", "natural_estimate"])
                || !exact(
                    indirect_result,
                    &[
                        "estimate",
                        "se",
                        "lower",
                        "upper",
                        "natural_estimate",
                        "natural_lower",
                        "natural_upper",
                    ],
                )
                || !close(unadjusted_result.get("estimate"), unadjusted)
                || !close(
                    unadjusted_result.get("natural_estimate"),
                    natural_effect(&facts.effect_measure, unadjusted),
                )
                || !close(adjusted_result.get("estimate"), adjusted)
                || bootstrap_se.is_none_or(|value| value <= 0.0 || value > 100.0)
                || !close(
                    adjusted_result.get("natural_estimate"),
                    natural_effect(&facts.effect_measure, adjusted),
                )
                || !close(aggregate_result.get("estimate"), facts.aggregate_effect)
                || !close(aggregate_result.get("se"), facts.aggregate_se)
                || !close(
                    aggregate_result.get("natural_estimate"),
                    natural_effect(&facts.effect_measure, facts.aggregate_effect),
                )
                || !close(indirect_result.get("estimate"), indirect)
                || indirect_se.is_none_or(|value| !close(indirect_result.get("se"), value))
                || lower.is_none_or(|value| !close(indirect_result.get("lower"), value))
                || upper.is_none_or(|value| !close(indirect_result.get("upper"), value))
                || !close(
                    indirect_result.get("natural_estimate"),
                    natural_effect(&facts.effect_measure, indirect),
                )
                || lower.is_none_or(|value| {
                    !close(
                        indirect_result.get("natural_lower"),
                        natural_effect(&facts.effect_measure, value),
                    )
                })
                || upper.is_none_or(|value| {
                    !close(
                        indirect_result.get("natural_upper"),
                        natural_effect(&facts.effect_measure, value),
                    )
                })
            {
                audit.errors.push(
                    "MAIC effect summaries differ from native recomputation or arithmetic".into(),
                );
            }
        }
        (Err(error), _) | (_, Err(error)) => audit
            .errors
            .push(format!("native MAIC point estimate failed: {error}")),
    }
    let bootstrap = &result["bootstrap"];
    audit.bootstrap_iterations = bootstrap
        .get("iterations")
        .and_then(serde_json::Value::as_u64)
        .unwrap_or_default() as usize;
    audit.bootstrap_failures = bootstrap
        .get("failed")
        .and_then(serde_json::Value::as_u64)
        .unwrap_or_default() as usize;
    if !exact(
        bootstrap,
        &[
            "method",
            "iterations",
            "successful",
            "failed",
            "seed",
            "prng",
            "failure_policy",
            "draws",
        ],
    ) || text(bootstrap.get("method")) != Some("stratified_nonparametric_bootstrap_refit")
        || audit.bootstrap_iterations != facts.bootstrap_iterations
        || bootstrap
            .get("successful")
            .and_then(serde_json::Value::as_u64)
            != Some(facts.bootstrap_iterations as u64)
        || audit.bootstrap_failures != 0
        || bootstrap.get("seed").and_then(serde_json::Value::as_u64) != Some(facts.bootstrap_seed)
        || bootstrap.get("prng")
            != Some(&serde_json::json!({"algorithm": "pcg32-xsh-rr", "version": "1"}))
        || text(bootstrap.get("failure_policy")) != Some("retain_and_block_review")
        || !exact(&bootstrap["draws"], &["path", "sha256"])
    {
        audit
            .errors
            .push("MAIC bootstrap completeness contract is invalid".into());
    }
    if let Some((_, raw)) = bound_bytes(
        workspace,
        &bootstrap["draws"],
        None,
        "MAIC bootstrap draws",
        MAX_SOURCE_BYTES,
        &mut audit.errors,
    ) {
        validate_draw_rows(&raw, &facts, &mut audit.errors);
    }
    if result.get("cross_implementation")
        != Some(&serde_json::json!({
            "portable_replay": "complete_calibration_point_and_bootstrap",
            "native_replay": "calibration_and_point_estimate_only",
            "uncertainty_native_replay": false
        }))
    {
        audit
            .errors
            .push("MAIC cross-implementation scope is invalid".into());
    }
    if string_array(result.get("limitations")) != Some(facts.limitations.clone())
        || !exact(
            &result["human_gate"],
            &["status", "required_checks", "automatic_downstream_use"],
        )
        || result
            .pointer("/human_gate/status")
            .and_then(serde_json::Value::as_str)
            != Some("awaiting_method_review")
        || bool_value(result.pointer("/human_gate/automatic_downstream_use")) != Some(false)
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
            .push("MAIC limitations or Human gate drifted".into());
    }
    if string_array(result.get("warnings")).is_none() {
        audit
            .errors
            .push("MAIC warnings must be an array of text".into());
    }
    dedup_errors(&mut audit.errors);
    audit.complete = audit.errors.is_empty();
    audit.reviewable =
        audit.complete && audit.status == "awaiting_method_review" && audit.bootstrap_failures == 0;
    audit
}

fn result_path_from_request(workspace: &Path) -> Result<String, String> {
    let request_path = resolve_file(workspace, REQUEST_PATH, "MAIC request")?;
    let raw = read_capped(&request_path, MAX_JSON_BYTES, "MAIC request")?;
    let value: serde_json::Value = serde_json::from_slice(&raw)
        .map_err(|error| format!("MAIC request is invalid JSON: {error}"))?;
    let output = text(value.pointer("/output/directory"))
        .ok_or_else(|| "MAIC output.directory is invalid".to_string())?;
    Ok(format!("{output}/manifest.json"))
}

#[tauri::command]
pub fn audit_heor_population_adjusted_comparison(
    app: AppHandle,
) -> Result<PopulationAdjustedComparisonAudit, String> {
    let workspace = crate::runtime::workspace_dir(&app)?;
    match result_path_from_request(&workspace) {
        Ok(path) => Ok(audit_path(&workspace, &path)),
        Err(error) => Ok(PopulationAdjustedComparisonAudit {
            errors: vec![error],
            ..PopulationAdjustedComparisonAudit::default()
        }),
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum PopulationAdjustedComparisonReviewAction {
    Accept,
    Reject,
}

#[derive(Clone, Debug, Eq, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct PopulationAdjustedComparisonChecklist {
    pub question_estimand_target_common_comparator_reviewed: bool,
    pub randomized_connected_evidence_provenance_reviewed: bool,
    pub effect_modifier_rationale_completeness_reviewed: bool,
    pub ipd_integrity_privacy_missingness_reviewed: bool,
    pub target_moments_overlap_reviewed: bool,
    pub calibration_balance_weights_ess_reviewed: bool,
    pub bootstrap_precision_failures_reviewed: bool,
    pub residual_bias_transportability_downstream_reviewed: bool,
}

impl PopulationAdjustedComparisonChecklist {
    fn all_confirmed(&self) -> bool {
        self.question_estimand_target_common_comparator_reviewed
            && self.randomized_connected_evidence_provenance_reviewed
            && self.effect_modifier_rationale_completeness_reviewed
            && self.ipd_integrity_privacy_missingness_reviewed
            && self.target_moments_overlap_reviewed
            && self.calibration_balance_weights_ess_reviewed
            && self.bootstrap_precision_failures_reviewed
            && self.residual_bias_transportability_downstream_reviewed
    }
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct PopulationAdjustedComparisonReviewRequest {
    pub project_id: String,
    pub result_path: String,
    pub result_sha256: String,
    pub action: PopulationAdjustedComparisonReviewAction,
    pub checklist: PopulationAdjustedComparisonChecklist,
    pub actor_label: String,
    pub rationale: String,
}

#[derive(Clone, Debug, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct PopulationAdjustedComparisonReviewEvent {
    pub schema_version: u32,
    pub sequence: u64,
    pub review_id: String,
    pub project_id: String,
    pub execution_id: String,
    pub action: PopulationAdjustedComparisonReviewAction,
    pub result_path: String,
    pub result_sha256: String,
    pub related_artifacts: Vec<crate::heor_approval::ArtifactBinding>,
    pub checklist: PopulationAdjustedComparisonChecklist,
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
pub struct PopulationAdjustedComparisonReviewLog {
    pub events: Vec<PopulationAdjustedComparisonReviewEvent>,
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
    action: PopulationAdjustedComparisonReviewAction,
    status: &'static str,
    result_path: &'a str,
    result_sha256: &'a str,
    related_artifacts: &'a [crate::heor_approval::ArtifactBinding],
    checklist: &'a PopulationAdjustedComparisonChecklist,
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
    action: PopulationAdjustedComparisonReviewAction,
    result_path: &'a str,
    result_sha256: &'a str,
    related_artifacts: &'a [crate::heor_approval::ArtifactBinding],
    checklist: &'a PopulationAdjustedComparisonChecklist,
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
        .join("population-adjusted-comparison-reviews"))
}

fn review_log_path(root: &Path, project_id: &str) -> Result<PathBuf, String> {
    if !validate_project_id(project_id) {
        return Err("projectId must be a safe identifier".into());
    }
    Ok(root.join(format!("{project_id}.jsonl")))
}

fn hash_review_event(event: &PopulationAdjustedComparisonReviewEvent) -> Result<String, String> {
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

fn snapshot_bytes(event: &PopulationAdjustedComparisonReviewEvent) -> Result<Vec<u8>, String> {
    let snapshot = ReviewSnapshot {
        schema_version: REVIEW_SCHEMA,
        review_id: &event.review_id,
        project_id: &event.project_id,
        execution_id: &event.execution_id,
        action: event.action,
        status: if event.action == PopulationAdjustedComparisonReviewAction::Accept {
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
    audit: &PopulationAdjustedComparisonAudit,
) -> Result<Vec<crate::heor_approval::ArtifactBinding>, String> {
    let result_path = resolve_file(workspace, &audit.result_path, "MAIC result")?;
    let result_raw = read_capped(&result_path, MAX_JSON_BYTES, "MAIC result")?;
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
    for field in [
        "request",
        "source_data",
        "aggregate_evidence",
        "evidence_synthesis",
    ] {
        add(&result[field]);
    }
    add(&result["runtime"]["evaluator_source"]);
    add(&result["bootstrap"]["draws"]);
    let mut seen = HashSet::new();
    bindings.retain(|binding| seen.insert(binding.path.clone()));
    if bindings.len() != 7 || bindings.iter().any(|binding| !is_sha256(&binding.sha256)) {
        return Err("MAIC review could not bind the complete seven-artifact graph".into());
    }
    for binding in &bindings {
        let path = resolve_file(workspace, &binding.path, "MAIC review artifact")?;
        let raw = read_capped(&path, MAX_SOURCE_BYTES, "MAIC review artifact")?;
        if sha256(&raw) != binding.sha256 {
            return Err("MAIC review artifact changed during submission".into());
        }
    }
    Ok(bindings)
}

fn read_review_events(
    root: &Path,
    workspace: &Path,
    project_id: &str,
) -> Result<Vec<PopulationAdjustedComparisonReviewEvent>, String> {
    let path = review_log_path(root, project_id)?;
    let raw = match std::fs::read(&path) {
        Ok(raw) => raw,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(format!("MAIC review log unavailable: {error}")),
    };
    if raw.len() > 4 * 1024 * 1024 {
        return Err("MAIC review log exceeds 4 MB".into());
    }
    let mut events = Vec::new();
    let mut previous_hash = None;
    for (index, line) in raw
        .split(|byte| *byte == b'\n')
        .filter(|line| !line.is_empty())
        .enumerate()
    {
        if events.len() >= 2_000 {
            return Err("MAIC review log exceeds 2,000 events".into());
        }
        let event: PopulationAdjustedComparisonReviewEvent = serde_json::from_slice(line)
            .map_err(|error| format!("MAIC review log line {} is invalid: {error}", index + 1))?;
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
                "MAIC review log line {} violates the event contract",
                index + 1
            ));
        }
        let record = resolve_file(workspace, &event.record_path, "MAIC review record")?;
        let record_raw = read_capped(&record, MAX_JSON_BYTES, "MAIC review record")?;
        if sha256(&record_raw) != event.record_sha256 || record_raw != snapshot_bytes(&event)? {
            return Err(format!(
                "MAIC review log line {} record binding is invalid",
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
    event: &PopulationAdjustedComparisonReviewEvent,
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
        return Err("MAIC review record path is unsafe".into());
    }
    let target = root.join(relative);
    let parent = target
        .parent()
        .ok_or_else(|| "MAIC review record parent is invalid".to_string())?;
    std::fs::create_dir_all(parent)
        .map_err(|error| format!("MAIC review directory failed: {error}"))?;
    if std::fs::symlink_metadata(parent).is_ok_and(|metadata| metadata.file_type().is_symlink()) {
        return Err("MAIC review directory must not be a symlink".into());
    }
    let raw = snapshot_bytes(event)?;
    if sha256(&raw) != event.record_sha256 {
        return Err("MAIC review record hash changed before write".into());
    }
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&target)
        .map_err(|error| format!("MAIC review record write failed: {error}"))?;
    file.write_all(&raw)
        .and_then(|_| file.sync_all())
        .map_err(|error| format!("MAIC review record write failed: {error}"))
}

fn append_review_event(
    root: &Path,
    event: &PopulationAdjustedComparisonReviewEvent,
) -> Result<(), String> {
    let path = review_log_path(root, &event.project_id)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("MAIC review log directory failed: {error}"))?;
        crate::runtime::tighten_private(parent);
    }
    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)
        .map_err(|error| format!("MAIC review log write failed: {error}"))?;
    let mut raw = serde_json::to_vec(event).map_err(|error| error.to_string())?;
    raw.push(b'\n');
    file.write_all(&raw)
        .and_then(|_| file.sync_all())
        .map_err(|error| format!("MAIC review log write failed: {error}"))
}

#[tauri::command]
pub fn append_heor_population_adjusted_comparison_review(
    app: AppHandle,
    state: tauri::State<PopulationAdjustedComparisonReviewState>,
    request: PopulationAdjustedComparisonReviewRequest,
) -> Result<PopulationAdjustedComparisonReviewEvent, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "MAIC review lock poisoned".to_string())?;
    if !validate_project_id(&request.project_id)
        || !is_sha256(&request.result_sha256)
        || !validate_review_text(&request.actor_label, 120)
        || !validate_review_text(&request.rationale, 2_000)
    {
        return Err("MAIC review request contains invalid identity, hash, or text".into());
    }
    if request.action == PopulationAdjustedComparisonReviewAction::Accept
        && !request.checklist.all_confirmed()
    {
        return Err("all eight MAIC method checks are required for acceptance".into());
    }
    let workspace = crate::runtime::workspace_dir(&app)?;
    let audit = audit_path(&workspace, &request.result_path);
    if !audit.complete || !audit.reviewable {
        return Err(format!(
            "MAIC result is not reviewable: {}",
            audit.errors.join("; ")
        ));
    }
    if audit.result_path != request.result_path
        || audit.result_sha256.as_deref() != Some(&request.result_sha256)
    {
        return Err("MAIC review request does not bind the current audited result".into());
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
    let record_path = format!("heor/population-adjusted-comparison-reviews/{review_id}.json");
    let mut event = PopulationAdjustedComparisonReviewEvent {
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
pub fn list_heor_population_adjusted_comparison_reviews(
    app: AppHandle,
    state: tauri::State<PopulationAdjustedComparisonReviewState>,
    project_id: String,
) -> Result<PopulationAdjustedComparisonReviewLog, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "MAIC review lock poisoned".to_string())?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    let events = read_review_events(&review_root(&app)?, &workspace, &project_id)?;
    Ok(PopulationAdjustedComparisonReviewLog {
        chain_head: events.last().map(|event| event.event_hash.clone()),
        events,
        integrity: "verified_unanchored_sha256_chain",
        identity_assurance: REVIEW_ASSURANCE,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn checklist(value: bool) -> PopulationAdjustedComparisonChecklist {
        PopulationAdjustedComparisonChecklist {
            question_estimand_target_common_comparator_reviewed: value,
            randomized_connected_evidence_provenance_reviewed: value,
            effect_modifier_rationale_completeness_reviewed: value,
            ipd_integrity_privacy_missingness_reviewed: value,
            target_moments_overlap_reviewed: value,
            calibration_balance_weights_ess_reviewed: value,
            bootstrap_precision_failures_reviewed: value,
            residual_bias_transportability_downstream_reviewed: value,
        }
    }

    #[test]
    fn acceptance_requires_all_eight_method_checks() {
        assert!(checklist(true).all_confirmed());
        let mut incomplete = checklist(true);
        incomplete.target_moments_overlap_reviewed = false;
        assert!(!incomplete.all_confirmed());
    }

    #[test]
    fn native_calibration_balances_target_and_recomputes_effect() {
        let mut rows = Vec::new();
        for arm in ["a", "b"] {
            for index in 0..40 {
                let modifier = index as f64 / 20.0 + if arm == "b" { 0.25 / 20.0 } else { 0.0 };
                rows.push(SourceRow {
                    treatment: arm.into(),
                    outcome: 5.0
                        + 0.4 * modifier
                        + if arm == "b" {
                            1.0 + 0.3 * modifier
                        } else {
                            0.0
                        },
                    modifiers: vec![modifier],
                });
            }
        }
        let calibration = calibrate(&rows, &[0.8]).unwrap();
        assert!(calibration.balance_errors[0].abs() < 1e-9);
        assert!((ess(&calibration.weights) - 80.0).abs() > 0.01);
        let adjusted =
            effect_estimate(&rows, &calibration.weights, "a", "b", "mean_difference").unwrap();
        let unadjusted =
            effect_estimate(&rows, &vec![1.0; rows.len()], "a", "b", "mean_difference").unwrap();
        assert!((adjusted - unadjusted).abs() > 1e-6);
    }

    #[test]
    fn review_snapshot_and_event_hash_are_tamper_evident() {
        let mut event = PopulationAdjustedComparisonReviewEvent {
            schema_version: 1,
            sequence: 1,
            review_id: "0123456789abcdef0123456789abcdef".into(),
            project_id: "project-1".into(),
            execution_id: "maic-1".into(),
            action: PopulationAdjustedComparisonReviewAction::Accept,
            result_path: "heor/population-adjusted-comparison-runs/maic-1/manifest.json".into(),
            result_sha256: "a".repeat(64),
            related_artifacts: vec![],
            checklist: checklist(true),
            actor_label: "reviewer".into(),
            rationale: "Reviewed the exact bounded method.".into(),
            timestamp: 1,
            record_path: "heor/population-adjusted-comparison-reviews/review.json".into(),
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
    fn native_audit_accepts_a_portable_fixture_when_supplied() {
        let Ok(workspace) = std::env::var("AI4HEOR_MAIC_FIXTURE") else {
            return;
        };
        let result = "heor/population-adjusted-comparison-runs/maic-test-001/manifest.json";
        let audit = audit_path(Path::new(&workspace), result);
        assert!(audit.complete, "{}", audit.errors.join("; "));
        assert!(audit.reviewable);
    }
}
