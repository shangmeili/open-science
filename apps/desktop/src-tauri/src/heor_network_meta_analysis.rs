//! Native audit and app-owned Human method review for bounded network meta-analysis.
//!
//! The optional GPL R backend estimates tau and produces diagnostics. This module
//! independently re-reads the contrast CSV, reconstructs the weighted network,
//! verifies normalized estimates and bound backend bytes, and never selects a
//! scientific model, treatment, or downstream economic input.

use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::io::{Read, Write};
use std::path::{Component, Path, PathBuf};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager};

const REQUEST_PATH: &str = "heor/network-meta-analysis-request.json";
const REQUEST_SCHEMA: &str = "0.1.0";
const RESULT_SCHEMA: &str = "0.1.0";
const REVIEW_SCHEMA: &str = "0.1.0";
const REVIEW_EVENT_SCHEMA: u32 = 1;
const REVIEW_ASSURANCE: &str = "app_owned_local_human_assertion";
const EVALUATOR: &str = "ai4heor-nma-wls@0.1.0";
const TOLERANCE: f64 = 1e-8;
const Z_95: f64 = 1.959_963_984_540_054;
const MAX_JSON_BYTES: u64 = 16 * 1024 * 1024;
const MAX_SOURCE_BYTES: u64 = 64 * 1024 * 1024;
const MAX_STUDIES: usize = 5_000;
const MAX_TREATMENTS: usize = 32;
const ADAPTER_BYTES: &[u8] = include_bytes!(
    "../../../../runtime/skills/core/heor-network-meta-analysis/scripts/netmeta_adapter.R"
);
const REVIEW_CHECKS: [&str; 8] = [
    "question_outcome_estimand",
    "nodes_connectivity_two_arm_boundary",
    "study_contrasts_provenance_risk_of_bias",
    "transitivity_effect_modifiers",
    "model_tau_method",
    "heterogeneity_prediction",
    "global_local_inconsistency",
    "ranking_transportability_limitations",
];

#[derive(Default)]
pub struct NetworkMetaAnalysisReviewState(pub Mutex<()>);

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct NetworkMetaAnalysisAudit {
    pub complete: bool,
    pub reviewable: bool,
    pub status: String,
    pub execution_id: String,
    pub request_path: String,
    pub request_sha256: Option<String>,
    pub result_path: String,
    pub result_sha256: Option<String>,
    pub study_count: usize,
    pub treatment_count: usize,
    pub direct_comparison_count: usize,
    pub cycle_rank: usize,
    pub model_type: String,
    pub tau: Option<f64>,
    pub cross_implementation_scope: String,
    pub global_inconsistency_status: String,
    pub local_inconsistency_count: usize,
    pub ranking_method: String,
    pub limitations: Vec<String>,
    pub errors: Vec<String>,
}

impl Default for NetworkMetaAnalysisAudit {
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
            study_count: 0,
            treatment_count: 0,
            direct_comparison_count: 0,
            cycle_rank: 0,
            model_type: String::new(),
            tau: None,
            cross_implementation_scope: String::new(),
            global_inconsistency_status: String::new(),
            local_inconsistency_count: 0,
            ranking_method: String::new(),
            limitations: Vec::new(),
            errors: Vec::new(),
        }
    }
}

#[derive(Clone, Debug)]
struct Contrast {
    study_id: String,
    treat1: String,
    treat2: String,
    effect: f64,
    se: f64,
}

#[derive(Default)]
struct RequestFacts {
    execution_id: String,
    treatments: Vec<String>,
    reference: String,
    model_type: String,
    effect_measure: String,
    source_path: String,
    source_sha256: String,
    evidence_path: String,
    evidence_sha256: String,
    output_directory: String,
    comparisons: Vec<String>,
    rows: Vec<Contrast>,
    cycle_rank: usize,
    limitations: Vec<String>,
}

#[derive(Clone)]
struct ExpectedEstimate {
    left: String,
    right: String,
    effect: f64,
    se: f64,
    lower: f64,
    upper: f64,
    natural: f64,
}

fn exact(value: &serde_json::Value, fields: &[&str]) -> bool {
    value.as_object().is_some_and(|object| {
        object.len() == fields.len() && fields.iter().all(|field| object.contains_key(*field))
    })
}

fn text(value: Option<&serde_json::Value>) -> Option<&str> {
    value
        .and_then(serde_json::Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
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

fn read_capped(path: &Path, cap: u64, label: &str) -> Result<Vec<u8>, String> {
    let metadata =
        std::fs::metadata(path).map_err(|error| format!("{label} unavailable: {error}"))?;
    if !metadata.is_file() || metadata.len() > cap {
        return Err(format!("{label} is not a bounded regular file"));
    }
    let mut raw = Vec::with_capacity(metadata.len() as usize);
    std::fs::File::open(path)
        .and_then(|mut file| file.read_to_end(&mut raw))
        .map_err(|error| format!("{label} unavailable: {error}"))?;
    Ok(raw)
}

fn resolve_file(workspace: &Path, relative: &str, label: &str) -> Result<PathBuf, String> {
    let relative_path = Path::new(relative);
    if relative_path.is_absolute()
        || relative_path
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err(format!("{label} path must stay inside the workspace"));
    }
    let root = workspace
        .canonicalize()
        .map_err(|error| format!("workspace unavailable: {error}"))?;
    let mut unresolved = root.clone();
    for component in relative_path.components() {
        let Component::Normal(component) = component else {
            return Err(format!("{label} path must stay inside the workspace"));
        };
        unresolved.push(component);
        if std::fs::symlink_metadata(&unresolved)
            .is_ok_and(|metadata| metadata.file_type().is_symlink())
        {
            return Err(format!("{label} path must not traverse a symlink"));
        }
    }
    let resolved = unresolved
        .canonicalize()
        .map_err(|error| format!("{label} unavailable: {error}"))?;
    if !resolved.starts_with(&root) || !resolved.is_file() {
        return Err(format!("{label} path must stay inside the workspace"));
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
    if !exact(binding, &["path", "sha256"]) {
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
    let Some(expected_sha) = text(binding.get("sha256")).filter(|value| is_sha256(value)) else {
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
    if sha256(&raw) != expected_sha {
        errors.push(format!("{label} SHA-256 does not match current bytes"));
        return None;
    }
    Some((path.into(), raw))
}

fn comparison(left: &str, right: &str) -> String {
    if left < right {
        format!("{left}:{right}")
    } else {
        format!("{right}:{left}")
    }
}

fn parse_contrasts(raw: &[u8], errors: &mut Vec<String>) -> Vec<Contrast> {
    let Ok(content) = std::str::from_utf8(raw) else {
        errors.push("source CSV must be UTF-8".into());
        return Vec::new();
    };
    let mut lines = content.lines();
    if lines.next() != Some("study_id,treat1,treat2,effect,se") {
        errors.push("source CSV columns must be exactly study_id,treat1,treat2,effect,se".into());
        return Vec::new();
    }
    let mut rows = Vec::new();
    for (index, line) in lines.enumerate() {
        if line.is_empty() {
            errors.push(format!("source CSV row {} is blank", index + 2));
            continue;
        }
        let cells: Vec<&str> = line.split(',').collect();
        if cells.len() != 5
            || cells
                .iter()
                .any(|cell| cell.trim() != *cell || cell.is_empty())
        {
            errors.push(format!(
                "source CSV row {} violates the fixed contrast format",
                index + 2
            ));
            continue;
        }
        let (study_id, treat1, treat2) = (cells[0], cells[1], cells[2]);
        let effect = cells[3].parse::<f64>();
        let se = cells[4].parse::<f64>();
        if !safe_id(study_id)
            || !safe_id(treat1)
            || !safe_id(treat2)
            || treat1 == treat2
            || effect
                .as_ref()
                .map_or(true, |value| !value.is_finite() || value.abs() > 100.0)
            || se.as_ref().map_or(true, |value| {
                !value.is_finite() || *value <= 0.0 || *value > 100.0
            })
        {
            errors.push(format!(
                "source CSV row {} contains invalid values",
                index + 2
            ));
            continue;
        }
        rows.push(Contrast {
            study_id: study_id.into(),
            treat1: treat1.into(),
            treat2: treat2.into(),
            effect: effect.unwrap_or_default(),
            se: se.unwrap_or_default(),
        });
    }
    rows
}

fn string_array(value: Option<&serde_json::Value>) -> Option<Vec<String>> {
    value.as_ref()?.as_array().and_then(|values| {
        values
            .iter()
            .map(|value| text(Some(value)).map(str::to_owned))
            .collect()
    })
}

fn validate_request(
    workspace: &Path,
    request: &serde_json::Value,
    request_raw: &[u8],
    errors: &mut Vec<String>,
) -> RequestFacts {
    let mut facts = RequestFacts::default();
    if !exact(
        request,
        &[
            "schema_version",
            "execution_id",
            "status",
            "question",
            "evidence_synthesis",
            "source_data",
            "treatments",
            "reference_treatment",
            "effect",
            "model",
            "transitivity",
            "diagnostics",
            "runtime",
            "output",
            "study_provenance",
            "limitations",
            "human_gate",
        ],
    ) {
        errors.push("NMA request fields are not the exact supported contract".into());
        return facts;
    }
    if text(request.get("schema_version")) != Some(REQUEST_SCHEMA)
        || text(request.get("status")) != Some("ready_for_execution")
    {
        errors.push("request schema or status is invalid".into());
    }
    facts.execution_id = text(request.get("execution_id")).unwrap_or_default().into();
    if !safe_id(&facts.execution_id) {
        errors.push("request execution_id is invalid".into());
    }
    let question = &request["question"];
    if !exact(
        question,
        &[
            "population",
            "intervention_network",
            "outcome",
            "timepoint",
            "estimand",
            "study_design",
        ],
    ) || text(question.get("study_design")) != Some("randomized_parallel_two_arm")
        || [
            "population",
            "intervention_network",
            "outcome",
            "timepoint",
            "estimand",
        ]
        .iter()
        .any(|field| text(question.get(*field)).is_none())
    {
        errors.push(
            "request question is incomplete or outside the two-arm randomized boundary".into(),
        );
    }

    let evidence = &request["evidence_synthesis"];
    let included_record_ids = string_array(evidence.get("included_record_ids")).unwrap_or_default();
    if !exact(evidence, &["path", "sha256", "included_record_ids"])
        || included_record_ids.is_empty()
        || included_record_ids.iter().any(|id| !safe_id(id))
        || included_record_ids.iter().collect::<HashSet<_>>().len() != included_record_ids.len()
    {
        errors.push("request evidence synthesis binding is invalid".into());
    }
    facts.evidence_path = text(evidence.get("path")).unwrap_or_default().into();
    facts.evidence_sha256 = text(evidence.get("sha256")).unwrap_or_default().into();
    let _ = bound_bytes(
        workspace,
        &serde_json::json!({"path": facts.evidence_path, "sha256": facts.evidence_sha256}),
        Some(&facts.evidence_path),
        "evidence synthesis",
        MAX_JSON_BYTES,
        errors,
    );

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
            "study_count",
            "contains_direct_identifiers",
            "missing_policy",
            "multiarm_policy",
        ],
    ) || text(source.get("execution_boundary")) != Some("local_only")
        || text(source.get("format")) != Some("contrast_csv")
        || source
            .get("contains_direct_identifiers")
            .and_then(serde_json::Value::as_bool)
            != Some(false)
        || text(source.get("missing_policy")) != Some("reject")
        || text(source.get("multiarm_policy")) != Some("reject")
    {
        errors.push("request source-data contract is invalid".into());
    }
    facts.source_path = text(source.get("path")).unwrap_or_default().into();
    facts.source_sha256 = text(source.get("sha256")).unwrap_or_default().into();
    if let Some((_, source_raw)) = bound_bytes(
        workspace,
        &serde_json::json!({"path": facts.source_path, "sha256": facts.source_sha256}),
        Some(&facts.source_path),
        "source data",
        MAX_SOURCE_BYTES,
        errors,
    ) {
        facts.rows = parse_contrasts(&source_raw, errors);
    }
    if !(3..=MAX_STUDIES).contains(&facts.rows.len()) {
        errors.push("source data must contain 3 to 5,000 studies".into());
    }
    let study_ids: HashSet<&str> = facts.rows.iter().map(|row| row.study_id.as_str()).collect();
    if study_ids.len() != facts.rows.len() {
        errors.push(
            "every study_id must occur once; multi-arm or duplicate studies are rejected".into(),
        );
    }

    let Some(treatments) = request
        .get("treatments")
        .and_then(serde_json::Value::as_array)
    else {
        errors.push("request treatments must be an array".into());
        return facts;
    };
    for treatment in treatments {
        if !exact(
            treatment,
            &["id", "label", "node_definition", "merging_rationale"],
        ) || ["id", "label", "node_definition", "merging_rationale"]
            .iter()
            .any(|field| text(treatment.get(*field)).is_none())
        {
            errors.push("request treatment node is invalid".into());
            continue;
        }
        facts
            .treatments
            .push(text(treatment.get("id")).unwrap_or_default().into());
    }
    if !(3..=MAX_TREATMENTS).contains(&facts.treatments.len())
        || facts.treatments.iter().any(|id| !safe_id(id))
        || facts.treatments.iter().collect::<HashSet<_>>().len() != facts.treatments.len()
    {
        errors.push("request must declare 3 to 32 unique safe treatment nodes".into());
    }
    let csv_treatments: HashSet<&str> = facts
        .rows
        .iter()
        .flat_map(|row| [row.treat1.as_str(), row.treat2.as_str()])
        .collect();
    if csv_treatments != facts.treatments.iter().map(String::as_str).collect() {
        errors.push("declared treatments do not match the source network".into());
    }
    facts.reference = text(request.get("reference_treatment"))
        .unwrap_or_default()
        .into();
    if !facts.treatments.contains(&facts.reference) {
        errors.push("reference treatment is not declared".into());
    }
    facts.comparisons = facts
        .rows
        .iter()
        .map(|row| comparison(&row.treat1, &row.treat2))
        .collect::<HashSet<_>>()
        .into_iter()
        .collect();
    facts.comparisons.sort();
    let mut adjacency: HashMap<&str, HashSet<&str>> = facts
        .treatments
        .iter()
        .map(|treatment| (treatment.as_str(), HashSet::new()))
        .collect();
    for row in &facts.rows {
        adjacency
            .entry(&row.treat1)
            .or_default()
            .insert(&row.treat2);
        adjacency
            .entry(&row.treat2)
            .or_default()
            .insert(&row.treat1);
    }
    let mut visited = HashSet::new();
    let mut stack = facts
        .treatments
        .first()
        .map_or_else(Vec::new, |value| vec![value.as_str()]);
    while let Some(current) = stack.pop() {
        if visited.insert(current) {
            stack.extend(adjacency.get(current).into_iter().flatten().copied());
        }
    }
    if visited.len() != facts.treatments.len() {
        errors.push("treatment network is disconnected".into());
    } else {
        facts.cycle_rank = facts
            .comparisons
            .len()
            .saturating_sub(facts.treatments.len())
            + 1;
    }
    if source.get("row_count").and_then(serde_json::Value::as_u64) != Some(facts.rows.len() as u64)
        || source
            .get("study_count")
            .and_then(serde_json::Value::as_u64)
            != Some(study_ids.len() as u64)
    {
        errors.push("source-data counts do not match current bytes".into());
    }

    let effect = &request["effect"];
    facts.effect_measure = text(effect.get("measure")).unwrap_or_default().into();
    let expected_scale = match facts.effect_measure.as_str() {
        "log_odds_ratio" | "log_risk_ratio" | "log_hazard_ratio" => Some("log"),
        "mean_difference" | "standardized_mean_difference" => Some("identity"),
        _ => None,
    };
    if !exact(
        effect,
        &[
            "measure",
            "scale",
            "likelihood",
            "link",
            "confidence_level",
            "favorable_direction",
        ],
    ) || text(effect.get("scale")) != expected_scale
        || text(effect.get("likelihood")) != Some("normal")
        || text(effect.get("link")) != Some("identity")
        || finite(effect.get("confidence_level")) != Some(0.95)
        || !matches!(
            text(effect.get("favorable_direction")),
            Some("lower" | "higher")
        )
    {
        errors.push("request effect contract is invalid".into());
    }
    let model = &request["model"];
    facts.model_type = text(model.get("type")).unwrap_or_default().into();
    let model_valid = exact(
        model,
        &[
            "type",
            "heterogeneity_variance",
            "tau_method",
            "prediction_interval",
        ],
    ) && match facts.model_type.as_str() {
        "common" => {
            text(model.get("heterogeneity_variance")) == Some("none")
                && text(model.get("tau_method")) == Some("none")
                && model
                    .get("prediction_interval")
                    .and_then(serde_json::Value::as_bool)
                    == Some(false)
        }
        "random" => {
            text(model.get("heterogeneity_variance")) == Some("common_tau_squared")
                && text(model.get("tau_method")) == Some("REML")
                && model
                    .get("prediction_interval")
                    .and_then(serde_json::Value::as_bool)
                    == Some(true)
        }
        _ => false,
    };
    if !model_valid {
        errors.push("request model contract is invalid".into());
    }
    let diagnostics = &request["diagnostics"];
    if !exact(
        diagnostics,
        &["global_inconsistency", "local_inconsistency", "ranking"],
    ) || text(diagnostics.get("global_inconsistency")) != Some("design_decomposition")
        || text(diagnostics.get("local_inconsistency")) != Some("node_splitting")
        || !matches!(text(diagnostics.get("ranking")), Some("none" | "p_score"))
    {
        errors.push("request diagnostics contract is invalid".into());
    }
    let transitivity = &request["transitivity"];
    if !exact(
        transitivity,
        &[
            "status",
            "joint_randomizability_rationale",
            "effect_modifiers",
            "concerns",
        ],
    ) || text(transitivity.get("status")) != Some("awaiting_human_review")
        || text(transitivity.get("joint_randomizability_rationale")).is_none()
        || string_array(transitivity.get("concerns")).is_none()
    {
        errors.push("request transitivity assessment is invalid".into());
    }
    let modifiers = transitivity
        .get("effect_modifiers")
        .and_then(serde_json::Value::as_array);
    if modifiers.is_none_or(Vec::is_empty) {
        errors.push("request must assess at least one effect modifier".into());
    } else if let Some(modifiers) = modifiers {
        let expected_comparisons: HashSet<&str> =
            facts.comparisons.iter().map(String::as_str).collect();
        let mut modifier_ids = HashSet::new();
        for modifier in modifiers {
            let modifier_id = text(modifier.get("id")).unwrap_or_default();
            if !exact(
                modifier,
                &["id", "label", "rationale", "comparison_summaries"],
            ) || !safe_id(modifier_id)
                || !modifier_ids.insert(modifier_id)
                || text(modifier.get("label")).is_none()
                || text(modifier.get("rationale")).is_none()
            {
                errors.push("effect modifier contract is invalid".into());
            }
            let mut seen = HashSet::new();
            if let Some(summaries) = modifier
                .get("comparison_summaries")
                .and_then(serde_json::Value::as_array)
            {
                for summary in summaries {
                    let comparison_id = text(summary.get("comparison")).unwrap_or_default();
                    let source_ids = string_array(summary.get("source_ids")).unwrap_or_default();
                    if !exact(summary, &["comparison", "summary", "source_ids"])
                        || !expected_comparisons.contains(comparison_id)
                        || !seen.insert(comparison_id)
                        || text(summary.get("summary")).is_none()
                        || source_ids.is_empty()
                        || source_ids
                            .iter()
                            .any(|id| !included_record_ids.contains(id))
                    {
                        errors.push("effect-modifier comparison summary is invalid".into());
                    }
                }
            }
            if seen != expected_comparisons {
                errors.push("every effect modifier must summarize every direct comparison".into());
            }
        }
    }
    let provenance = request
        .get("study_provenance")
        .and_then(serde_json::Value::as_array);
    let expected_studies: HashSet<&str> =
        facts.rows.iter().map(|row| row.study_id.as_str()).collect();
    let mut seen_studies = HashSet::new();
    if let Some(provenance) = provenance {
        for item in provenance {
            let study_id = text(item.get("study_id")).unwrap_or_default();
            let record_ids = string_array(item.get("evidence_record_ids")).unwrap_or_default();
            let extraction_ids = string_array(item.get("extraction_ids")).unwrap_or_default();
            if !exact(
                item,
                &[
                    "study_id",
                    "evidence_record_ids",
                    "extraction_ids",
                    "risk_of_bias",
                ],
            ) || !expected_studies.contains(study_id)
                || !seen_studies.insert(study_id)
                || record_ids.is_empty()
                || record_ids
                    .iter()
                    .any(|id| !included_record_ids.contains(id))
                || extraction_ids.is_empty()
                || extraction_ids.iter().any(|id| !safe_id(id))
                || !matches!(
                    text(item.get("risk_of_bias")),
                    Some("low" | "some_concerns" | "high" | "not_assessed")
                )
            {
                errors.push("study provenance contract is invalid".into());
            }
        }
    } else {
        errors.push("study provenance must be an array".into());
    }
    if seen_studies != expected_studies {
        errors.push("study provenance must cover every source study exactly once".into());
    }
    let runtime = &request["runtime"];
    if !exact(
        runtime,
        &["r_version", "package_versions", "adapter_sha256"],
    ) || text(runtime.get("adapter_sha256")) != Some(sha256(ADAPTER_BYTES).as_str())
        || runtime
            .get("package_versions")
            .and_then(serde_json::Value::as_object)
            .is_none_or(|packages| {
                packages.len() != 3
                    || ["netmeta", "meta", "metafor"]
                        .iter()
                        .any(|package| text(packages.get(*package)).is_none())
            })
    {
        errors.push("request runtime does not bind the current fixed adapter".into());
    }
    if !exact(&request["output"], &["directory"]) {
        errors.push("request output fields are invalid".into());
    }
    facts.output_directory = text(request.pointer("/output/directory"))
        .unwrap_or_default()
        .into();
    if facts.output_directory != format!("heor/network-meta-analysis-runs/{}", facts.execution_id) {
        errors.push("request output directory is not execution-specific".into());
    }
    facts.limitations = string_array(request.get("limitations")).unwrap_or_default();
    if facts.limitations.is_empty() {
        errors.push("request limitations are missing".into());
    }
    if !exact(&request["human_gate"], &["status", "required_checks"])
        || request
            .pointer("/human_gate/status")
            .and_then(serde_json::Value::as_str)
            != Some("awaiting_model_review")
        || string_array(request.pointer("/human_gate/required_checks"))
            != Some(
                REVIEW_CHECKS
                    .iter()
                    .map(|value| (*value).to_owned())
                    .collect(),
            )
    {
        errors.push("request Human model-review gate is invalid".into());
    }
    if request_raw.len() > MAX_JSON_BYTES as usize {
        errors.push("request exceeds the JSON size cap".into());
    }
    facts
}

fn invert(mut matrix: Vec<Vec<f64>>) -> Result<Vec<Vec<f64>>, String> {
    let size = matrix.len();
    for (row_index, row) in matrix.iter_mut().enumerate() {
        row.extend((0..size).map(|column| usize::from(row_index == column) as f64));
    }
    for column in 0..size {
        let pivot = (column..size)
            .max_by(|left, right| {
                matrix[*left][column]
                    .abs()
                    .total_cmp(&matrix[*right][column].abs())
            })
            .ok_or_else(|| "network design matrix is singular".to_string())?;
        if matrix[pivot][column].abs() < 1e-14 {
            return Err("network design matrix is singular".into());
        }
        matrix.swap(column, pivot);
        let scale = matrix[column][column];
        for value in &mut matrix[column] {
            *value /= scale;
        }
        let pivot_row = matrix[column].clone();
        for (row_index, row_values) in matrix.iter_mut().enumerate().take(size) {
            if row_index == column {
                continue;
            }
            let factor = row_values[column];
            for (value, pivot_value) in row_values.iter_mut().zip(&pivot_row) {
                *value -= factor * pivot_value;
            }
        }
    }
    Ok(matrix.into_iter().map(|row| row[size..].to_vec()).collect())
}

fn expected_estimates(facts: &RequestFacts, tau: f64) -> Result<Vec<ExpectedEstimate>, String> {
    let non_reference: Vec<&str> = facts
        .treatments
        .iter()
        .map(String::as_str)
        .filter(|treatment| *treatment != facts.reference)
        .collect();
    let positions: HashMap<&str, usize> = non_reference
        .iter()
        .enumerate()
        .map(|(index, treatment)| (*treatment, index))
        .collect();
    let size = non_reference.len();
    let mut information = vec![vec![0.0; size]; size];
    let mut rhs = vec![0.0; size];
    for row in &facts.rows {
        let mut design = vec![0.0; size];
        if let Some(position) = positions.get(row.treat1.as_str()) {
            design[*position] += 1.0;
        }
        if let Some(position) = positions.get(row.treat2.as_str()) {
            design[*position] -= 1.0;
        }
        let weight = 1.0 / (row.se * row.se + tau * tau);
        for left in 0..size {
            rhs[left] += weight * design[left] * row.effect;
            for right in 0..size {
                information[left][right] += weight * design[left] * design[right];
            }
        }
    }
    let covariance = invert(information)?;
    let beta: Vec<f64> = (0..size)
        .map(|row| {
            (0..size)
                .map(|column| covariance[row][column] * rhs[column])
                .sum()
        })
        .collect();
    let mut effects: HashMap<&str, f64> = HashMap::from([(facts.reference.as_str(), 0.0)]);
    for (index, treatment) in non_reference.iter().enumerate() {
        effects.insert(*treatment, beta[index]);
    }
    let mut estimates = Vec::new();
    for left in &facts.treatments {
        for right in &facts.treatments {
            if left == right {
                continue;
            }
            let effect = effects[left.as_str()] - effects[right.as_str()];
            let mut variance = 0.0;
            if let Some(position) = positions.get(left.as_str()) {
                variance += covariance[*position][*position];
            }
            if let Some(position) = positions.get(right.as_str()) {
                variance += covariance[*position][*position];
            }
            if let (Some(left_position), Some(right_position)) =
                (positions.get(left.as_str()), positions.get(right.as_str()))
            {
                variance -= 2.0 * covariance[*left_position][*right_position];
            }
            if variance < -1e-12 {
                return Err("network covariance produced a negative contrast variance".into());
            }
            let se = variance.max(0.0).sqrt();
            estimates.push(ExpectedEstimate {
                left: left.clone(),
                right: right.clone(),
                effect,
                se,
                lower: effect - Z_95 * se,
                upper: effect + Z_95 * se,
                natural: if facts.effect_measure.starts_with("log_") {
                    effect.exp()
                } else {
                    effect
                },
            });
        }
    }
    Ok(estimates)
}

fn close(observed: Option<&serde_json::Value>, expected: f64) -> bool {
    finite(observed)
        .is_some_and(|value| (value - expected).abs() <= TOLERANCE * expected.abs().max(1.0))
}

fn audit_estimates(
    result: &serde_json::Value,
    facts: &RequestFacts,
    expected: &[ExpectedEstimate],
    prediction_required: bool,
    errors: &mut Vec<String>,
) {
    let Some(league) = result
        .get("league_table")
        .and_then(serde_json::Value::as_array)
    else {
        errors.push("result league_table must be an array".into());
        return;
    };
    if league.len() != expected.len() {
        errors.push("result league_table does not cover the ordered network".into());
    }
    let expected_map: HashMap<(&str, &str), &ExpectedEstimate> = expected
        .iter()
        .map(|row| ((row.left.as_str(), row.right.as_str()), row))
        .collect();
    let mut seen = HashSet::new();
    for (index, row) in league.iter().enumerate() {
        if !exact(
            row,
            &[
                "treat1",
                "treat2",
                "effect",
                "se",
                "lower",
                "upper",
                "natural_effect",
                "prediction_lower",
                "prediction_upper",
            ],
        ) {
            errors.push(format!("league_table row {index} fields are invalid"));
            continue;
        }
        let key = (
            text(row.get("treat1")).unwrap_or_default(),
            text(row.get("treat2")).unwrap_or_default(),
        );
        let Some(expected) = expected_map.get(&key) else {
            errors.push(format!("league_table row {index} key is invalid"));
            continue;
        };
        if !seen.insert(key) {
            errors.push(format!("league_table row {index} key is duplicated"));
        }
        for (field, value) in [
            ("effect", expected.effect),
            ("se", expected.se),
            ("lower", expected.lower),
            ("upper", expected.upper),
            ("natural_effect", expected.natural),
        ] {
            if !close(row.get(field), value) {
                errors.push(format!(
                    "league_table row {index} {field} does not match native WLS"
                ));
            }
        }
        let prediction = (
            finite(row.get("prediction_lower")),
            finite(row.get("prediction_upper")),
        );
        if prediction_required {
            if prediction.0.is_none_or(|lower| lower > expected.effect)
                || prediction.1.is_none_or(|upper| upper < expected.effect)
            {
                errors.push(format!(
                    "league_table row {index} prediction interval is invalid"
                ));
            }
        } else if !row["prediction_lower"].is_null() || !row["prediction_upper"].is_null() {
            errors.push(format!(
                "league_table row {index} common-model prediction must be null"
            ));
        }
    }
    let Some(reference_rows) = result
        .get("estimates_vs_reference")
        .and_then(serde_json::Value::as_array)
    else {
        errors.push("result estimates_vs_reference must be an array".into());
        return;
    };
    if reference_rows.len() + 1 != facts.treatments.len() {
        errors.push("estimates_vs_reference does not cover every non-reference treatment".into());
    }
    for (index, row) in reference_rows.iter().enumerate() {
        let treatment = text(row.get("treatment")).unwrap_or_default();
        let Some(expected) = expected_map.get(&(treatment, facts.reference.as_str())) else {
            errors.push(format!(
                "estimates_vs_reference row {index} treatment is invalid"
            ));
            continue;
        };
        for (field, value) in [
            ("effect", expected.effect),
            ("se", expected.se),
            ("lower", expected.lower),
            ("upper", expected.upper),
            ("natural_effect", expected.natural),
        ] {
            if !close(row.get(field), value) {
                errors.push(format!(
                    "estimates_vs_reference row {index} {field} does not match native WLS"
                ));
            }
        }
    }
}

fn dedup_errors(errors: &mut Vec<String>) {
    let mut seen = HashSet::new();
    errors.retain(|error| seen.insert(error.clone()));
}

fn audit_path(workspace: &Path, result_path: &str) -> NetworkMetaAnalysisAudit {
    let mut audit = NetworkMetaAnalysisAudit {
        result_path: result_path.into(),
        ..NetworkMetaAnalysisAudit::default()
    };
    let request_path = match resolve_file(workspace, REQUEST_PATH, "NMA request") {
        Ok(path) => path,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    let request_raw = match read_capped(&request_path, MAX_JSON_BYTES, "NMA request") {
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
                .push(format!("NMA request is invalid JSON: {error}"));
            return audit;
        }
    };
    let facts = validate_request(workspace, &request, &request_raw, &mut audit.errors);
    audit.execution_id = facts.execution_id.clone();
    audit.study_count = facts.rows.len();
    audit.treatment_count = facts.treatments.len();
    audit.direct_comparison_count = facts.comparisons.len();
    audit.cycle_rank = facts.cycle_rank;
    audit.model_type = facts.model_type.clone();
    audit.limitations = facts.limitations.clone();
    if result_path != format!("{}/manifest.json", facts.output_directory) {
        audit
            .errors
            .push("result path does not match the request output directory".into());
    }
    let result_file = match resolve_file(workspace, result_path, "NMA result") {
        Ok(path) => path,
        Err(error) => {
            audit.errors.push(error);
            return audit;
        }
    };
    let result_raw = match read_capped(&result_file, MAX_JSON_BYTES, "NMA result") {
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
                .push(format!("NMA result is invalid JSON: {error}"));
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
            "backend_outputs",
            "network",
            "model",
            "estimates_vs_reference",
            "league_table",
            "heterogeneity",
            "inconsistency",
            "ranking",
            "cross_implementation",
            "warnings",
            "limitations",
            "human_gate",
        ],
    ) || text(result.get("schema_version")) != Some(RESULT_SCHEMA)
        || text(result.get("status")) != Some("awaiting_model_review")
        || text(result.get("execution_id")) != Some(&facts.execution_id)
    {
        audit
            .errors
            .push("NMA result top-level contract is invalid".into());
    }
    audit.status = text(result.get("status")).unwrap_or("invalid").into();
    let request_binding = &result["request"];
    if text(request_binding.get("path")) != Some(REQUEST_PATH)
        || text(request_binding.get("sha256")) != audit.request_sha256.as_deref()
    {
        audit
            .errors
            .push("result does not bind the exact current request".into());
    }
    for (label, path, hash) in [
        (
            "source data",
            facts.source_path.as_str(),
            facts.source_sha256.as_str(),
        ),
        (
            "evidence synthesis",
            facts.evidence_path.as_str(),
            facts.evidence_sha256.as_str(),
        ),
    ] {
        let field = if label == "source data" {
            "source_data"
        } else {
            "evidence_synthesis"
        };
        if text(result.pointer(&format!("/{field}/path"))) != Some(path)
            || text(result.pointer(&format!("/{field}/sha256"))) != Some(hash)
        {
            audit
                .errors
                .push(format!("result {label} binding does not match request"));
        }
    }
    let result_runtime = &result["runtime"];
    if !exact(
        result_runtime,
        &[
            "r_version",
            "rscript_path",
            "rscript_sha256",
            "package_versions",
            "adapter",
        ],
    ) || result_runtime.get("r_version") != request.pointer("/runtime/r_version")
        || result_runtime.get("package_versions") != request.pointer("/runtime/package_versions")
        || text(result_runtime.get("rscript_path")).is_none()
        || text(result_runtime.get("rscript_sha256")).is_none_or(|hash| !is_sha256(hash))
    {
        audit
            .errors
            .push("result runtime identity does not match the request".into());
    }
    let adapter = &result_runtime["adapter"];
    if let Some((_, raw)) = bound_bytes(
        workspace,
        adapter,
        None,
        "NMA adapter",
        MAX_SOURCE_BYTES,
        &mut audit.errors,
    ) {
        if raw != ADAPTER_BYTES
            || text(adapter.get("sha256")) != Some(sha256(ADAPTER_BYTES).as_str())
        {
            audit
                .errors
                .push("result adapter does not match the bundled fixed adapter".into());
        }
    }
    let mut backend_ids = HashSet::new();
    let Some(outputs) = result
        .get("backend_outputs")
        .and_then(serde_json::Value::as_array)
    else {
        audit
            .errors
            .push("result backend_outputs must be an array".into());
        return audit;
    };
    for output in outputs {
        let Some(id) = text(output.get("id")) else {
            audit.errors.push("backend output ID is invalid".into());
            continue;
        };
        if !exact(output, &["id", "path", "sha256"])
            || !matches!(
                id,
                "matrix" | "diagnostics" | "local_inconsistency" | "ranking" | "warnings"
            )
            || !backend_ids.insert(id)
        {
            audit
                .errors
                .push("backend output contract is invalid".into());
            continue;
        }
        let output_binding = serde_json::json!({
            "path": output.get("path"),
            "sha256": output.get("sha256"),
        });
        let _ = bound_bytes(
            workspace,
            &output_binding,
            None,
            "NMA backend output",
            MAX_SOURCE_BYTES,
            &mut audit.errors,
        );
    }
    if backend_ids.len() != 5 {
        audit
            .errors
            .push("result must bind the exact five backend outputs".into());
    }
    let model = &result["model"];
    let tau = finite(model.get("tau"));
    audit.tau = tau;
    if !exact(
        model,
        &[
            "effect_measure",
            "scale",
            "likelihood",
            "link",
            "type",
            "tau_method",
            "tau",
            "tau_squared",
            "prediction_interval",
        ],
    ) || text(model.get("effect_measure")) != Some(&facts.effect_measure)
        || text(model.get("type")) != Some(&facts.model_type)
        || tau.is_none_or(|value| value < 0.0)
        || !close(model.get("tau_squared"), tau.unwrap_or_default().powi(2))
        || (facts.model_type == "common" && tau != Some(0.0))
    {
        audit
            .errors
            .push("result model or tau contract is invalid".into());
    }
    let heterogeneity = &result["heterogeneity"];
    if !exact(
        heterogeneity,
        &[
            "tau",
            "tau_squared",
            "q_total",
            "df_total",
            "p_total",
            "q_heterogeneity",
            "df_heterogeneity",
            "p_heterogeneity",
        ],
    ) || !close(heterogeneity.get("tau"), tau.unwrap_or_default())
        || !close(
            heterogeneity.get("tau_squared"),
            tau.unwrap_or_default().powi(2),
        )
        || finite(heterogeneity.get("q_total")).is_none_or(|value| value < 0.0)
        || finite(heterogeneity.get("q_heterogeneity")).is_none_or(|value| value < 0.0)
    {
        audit
            .errors
            .push("result heterogeneity contract is invalid".into());
    }
    let expected = expected_estimates(&facts, tau.unwrap_or_default());
    match expected {
        Ok(expected) => audit_estimates(
            &result,
            &facts,
            &expected,
            facts.model_type == "random",
            &mut audit.errors,
        ),
        Err(error) => audit.errors.push(format!("native WLS failed: {error}")),
    }
    let network = &result["network"];
    if string_array(network.get("treatments")) != Some(facts.treatments.clone())
        || text(network.get("reference_treatment")) != Some(&facts.reference)
        || network
            .get("study_count")
            .and_then(serde_json::Value::as_u64)
            != Some(facts.rows.len() as u64)
        || network
            .get("direct_comparison_count")
            .and_then(serde_json::Value::as_u64)
            != Some(facts.comparisons.len() as u64)
        || network
            .get("cycle_rank")
            .and_then(serde_json::Value::as_u64)
            != Some(facts.cycle_rank as u64)
        || network
            .get("connected")
            .and_then(serde_json::Value::as_bool)
            != Some(true)
    {
        audit
            .errors
            .push("result network geometry does not match the current source".into());
    }
    audit.global_inconsistency_status = text(result.pointer("/inconsistency/global/status"))
        .unwrap_or_default()
        .into();
    let expected_global = if facts.cycle_rank > 0 {
        "estimable"
    } else {
        "not_estimable_tree_network"
    };
    if audit.global_inconsistency_status != expected_global {
        audit
            .errors
            .push("global inconsistency status does not match network geometry".into());
    }
    audit.local_inconsistency_count = result
        .pointer("/inconsistency/local")
        .and_then(serde_json::Value::as_array)
        .map_or(0, Vec::len);
    let mut local_comparisons = HashSet::new();
    if let Some(local) = result
        .pointer("/inconsistency/local")
        .and_then(serde_json::Value::as_array)
    {
        for row in local {
            let comparison_id = text(row.get("comparison")).unwrap_or_default();
            let direct = finite(row.get("direct_effect"));
            let indirect = finite(row.get("indirect_effect"));
            if !exact(
                row,
                &[
                    "comparison",
                    "network_effect",
                    "direct_effect",
                    "indirect_effect",
                    "difference",
                    "se_difference",
                    "p_value",
                ],
            ) || !facts.comparisons.iter().any(|value| value == comparison_id)
                || !local_comparisons.insert(comparison_id)
                || finite(row.get("network_effect")).is_none()
                || direct.is_none()
                || indirect.is_none()
                || finite(row.get("se_difference")).is_none_or(|value| value <= 0.0)
                || finite(row.get("p_value")).is_none_or(|value| !(0.0..=1.0).contains(&value))
                || !close(
                    row.get("difference"),
                    direct.unwrap_or_default() - indirect.unwrap_or_default(),
                )
            {
                audit
                    .errors
                    .push("result local inconsistency row is invalid".into());
            }
        }
    } else {
        audit
            .errors
            .push("result local inconsistency must be an array".into());
    }
    audit.ranking_method = text(result.pointer("/ranking/method"))
        .unwrap_or_default()
        .into();
    if audit.ranking_method != text(request.pointer("/diagnostics/ranking")).unwrap_or_default() {
        audit
            .errors
            .push("result ranking method does not match the researcher request".into());
    }
    let ranking_rows = result
        .pointer("/ranking/rows")
        .and_then(serde_json::Value::as_array);
    if audit.ranking_method == "none" {
        if ranking_rows.is_none_or(|rows| !rows.is_empty()) {
            audit
                .errors
                .push("disabled ranking must contain no rows".into());
        }
    } else if ranking_rows.is_none_or(|rows| rows.len() != facts.treatments.len()) {
        audit
            .errors
            .push("P-score ranking must cover every treatment".into());
    } else if let Some(rows) = ranking_rows {
        let mut treatments = HashSet::new();
        for row in rows {
            let treatment = text(row.get("treatment")).unwrap_or_default();
            if !exact(row, &["treatment", "p_score"])
                || !facts.treatments.iter().any(|value| value == treatment)
                || !treatments.insert(treatment)
                || finite(row.get("p_score")).is_none_or(|value| !(0.0..=1.0).contains(&value))
            {
                audit.errors.push("P-score ranking row is invalid".into());
            }
        }
    }
    let cross = &result["cross_implementation"];
    let expected_scope = if facts.model_type == "common" {
        "complete_common_effect"
    } else {
        "conditional_on_backend_tau"
    };
    audit.cross_implementation_scope = text(cross.get("scope")).unwrap_or_default().into();
    if text(cross.get("evaluator")) != Some(EVALUATOR)
        || audit.cross_implementation_scope != expected_scope
        || finite(cross.get("tolerance")) != Some(TOLERANCE)
        || cross.get("passed").and_then(serde_json::Value::as_bool) != Some(true)
        || finite(cross.get("max_abs_reference_error")).is_none_or(|value| value > TOLERANCE)
        || finite(cross.get("max_abs_league_error")).is_none_or(|value| value > TOLERANCE)
    {
        audit
            .errors
            .push("result cross-implementation contract is invalid".into());
    }
    if string_array(result.get("limitations")) != Some(facts.limitations.clone())
        || result.get("human_gate") != request.get("human_gate")
    {
        audit
            .errors
            .push("result limitations or Human gate drifted from the request".into());
    }
    if string_array(result.get("warnings")).is_none() {
        audit
            .errors
            .push("result warnings must be a string array".into());
    }
    dedup_errors(&mut audit.errors);
    audit.complete = audit.errors.is_empty();
    audit.reviewable = audit.complete && audit.status == "awaiting_model_review";
    audit
}

fn result_path_from_request(workspace: &Path) -> Result<String, String> {
    let request_path = resolve_file(workspace, REQUEST_PATH, "NMA request")?;
    let raw = read_capped(&request_path, MAX_JSON_BYTES, "NMA request")?;
    let value: serde_json::Value = serde_json::from_slice(&raw)
        .map_err(|error| format!("NMA request is invalid JSON: {error}"))?;
    let output = text(value.pointer("/output/directory"))
        .ok_or_else(|| "NMA request output.directory is invalid".to_string())?;
    Ok(format!("{output}/manifest.json"))
}

#[tauri::command]
pub fn audit_heor_network_meta_analysis(
    app: AppHandle,
) -> Result<NetworkMetaAnalysisAudit, String> {
    let workspace = crate::runtime::workspace_dir(&app)?;
    match result_path_from_request(&workspace) {
        Ok(path) => Ok(audit_path(&workspace, &path)),
        Err(error) => Ok(NetworkMetaAnalysisAudit {
            errors: vec![error],
            ..NetworkMetaAnalysisAudit::default()
        }),
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum NetworkMetaAnalysisReviewAction {
    Accept,
    Reject,
}

#[derive(Clone, Debug, Eq, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct NetworkMetaAnalysisChecklist {
    pub question_outcome_estimand_reviewed: bool,
    pub nodes_connectivity_two_arm_boundary_reviewed: bool,
    pub study_contrasts_provenance_risk_of_bias_reviewed: bool,
    pub transitivity_effect_modifiers_reviewed: bool,
    pub model_tau_method_reviewed: bool,
    pub heterogeneity_prediction_reviewed: bool,
    pub global_local_inconsistency_reviewed: bool,
    pub ranking_transportability_limitations_reviewed: bool,
}

impl NetworkMetaAnalysisChecklist {
    fn all_confirmed(&self) -> bool {
        self.question_outcome_estimand_reviewed
            && self.nodes_connectivity_two_arm_boundary_reviewed
            && self.study_contrasts_provenance_risk_of_bias_reviewed
            && self.transitivity_effect_modifiers_reviewed
            && self.model_tau_method_reviewed
            && self.heterogeneity_prediction_reviewed
            && self.global_local_inconsistency_reviewed
            && self.ranking_transportability_limitations_reviewed
    }
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct NetworkMetaAnalysisReviewRequest {
    pub project_id: String,
    pub result_path: String,
    pub result_sha256: String,
    pub action: NetworkMetaAnalysisReviewAction,
    pub checklist: NetworkMetaAnalysisChecklist,
    pub actor_label: String,
    pub rationale: String,
}

#[derive(Clone, Debug, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct NetworkMetaAnalysisReviewEvent {
    pub schema_version: u32,
    pub sequence: u64,
    pub review_id: String,
    pub project_id: String,
    pub execution_id: String,
    pub action: NetworkMetaAnalysisReviewAction,
    pub result_path: String,
    pub result_sha256: String,
    pub related_artifacts: Vec<crate::heor_approval::ArtifactBinding>,
    pub checklist: NetworkMetaAnalysisChecklist,
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
pub struct NetworkMetaAnalysisReviewLog {
    pub events: Vec<NetworkMetaAnalysisReviewEvent>,
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
    action: NetworkMetaAnalysisReviewAction,
    status: &'static str,
    result_path: &'a str,
    result_sha256: &'a str,
    related_artifacts: &'a [crate::heor_approval::ArtifactBinding],
    checklist: &'a NetworkMetaAnalysisChecklist,
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
    action: NetworkMetaAnalysisReviewAction,
    result_path: &'a str,
    result_sha256: &'a str,
    related_artifacts: &'a [crate::heor_approval::ArtifactBinding],
    checklist: &'a NetworkMetaAnalysisChecklist,
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
        .join("network-meta-analysis-reviews"))
}

fn review_log_path(root: &Path, project_id: &str) -> Result<PathBuf, String> {
    if !validate_project_id(project_id) {
        return Err("projectId must be a safe identifier".into());
    }
    Ok(root.join(format!("{project_id}.jsonl")))
}

fn hash_review_event(event: &NetworkMetaAnalysisReviewEvent) -> Result<String, String> {
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

fn snapshot_bytes(event: &NetworkMetaAnalysisReviewEvent) -> Result<Vec<u8>, String> {
    let snapshot = ReviewSnapshot {
        schema_version: REVIEW_SCHEMA,
        review_id: &event.review_id,
        project_id: &event.project_id,
        execution_id: &event.execution_id,
        action: event.action,
        status: if event.action == NetworkMetaAnalysisReviewAction::Accept {
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
    audit: &NetworkMetaAnalysisAudit,
) -> Result<Vec<crate::heor_approval::ArtifactBinding>, String> {
    let result_path = resolve_file(workspace, &audit.result_path, "NMA result")?;
    let result_raw = read_capped(&result_path, MAX_JSON_BYTES, "NMA result")?;
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
    add(&result["runtime"]["adapter"]);
    if let Some(outputs) = result
        .get("backend_outputs")
        .and_then(serde_json::Value::as_array)
    {
        for output in outputs {
            add(output);
        }
    }
    let mut seen = HashSet::new();
    bindings.retain(|binding| seen.insert(binding.path.clone()));
    if bindings.len() != 10 || bindings.iter().any(|binding| !is_sha256(&binding.sha256)) {
        return Err("NMA review could not bind the complete ten-artifact execution graph".into());
    }
    for binding in &bindings {
        let path = resolve_file(workspace, &binding.path, "NMA review artifact")?;
        let raw = read_capped(&path, MAX_SOURCE_BYTES, "NMA review artifact")?;
        if sha256(&raw) != binding.sha256 {
            return Err("NMA review artifact changed during submission".into());
        }
    }
    Ok(bindings)
}

fn read_review_events(
    root: &Path,
    workspace: &Path,
    project_id: &str,
) -> Result<Vec<NetworkMetaAnalysisReviewEvent>, String> {
    let path = review_log_path(root, project_id)?;
    let raw = match std::fs::read(&path) {
        Ok(raw) => raw,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(format!("NMA review log unavailable: {error}")),
    };
    if raw.len() > 4 * 1024 * 1024 {
        return Err("NMA review log exceeds 4 MB".into());
    }
    let mut events = Vec::new();
    let mut previous_hash = None;
    for (index, line) in raw
        .split(|byte| *byte == b'\n')
        .filter(|line| !line.is_empty())
        .enumerate()
    {
        if events.len() >= 2_000 {
            return Err("NMA review log exceeds 2,000 events".into());
        }
        let event: NetworkMetaAnalysisReviewEvent = serde_json::from_slice(line)
            .map_err(|error| format!("NMA review log line {} is invalid: {error}", index + 1))?;
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
                "NMA review log line {} violates the event contract",
                index + 1
            ));
        }
        let record = resolve_file(workspace, &event.record_path, "NMA review record")?;
        let record_raw = read_capped(&record, MAX_JSON_BYTES, "NMA review record")?;
        if sha256(&record_raw) != event.record_sha256 || record_raw != snapshot_bytes(&event)? {
            return Err(format!(
                "NMA review log line {} record binding is invalid",
                index + 1
            ));
        }
        previous_hash = Some(event.event_hash.clone());
        events.push(event);
    }
    Ok(events)
}

fn latest_review_for_execution<'a>(
    events: &'a [NetworkMetaAnalysisReviewEvent],
    execution_id: &str,
) -> Option<&'a NetworkMetaAnalysisReviewEvent> {
    events
        .iter()
        .rev()
        .find(|event| event.execution_id == execution_id)
}

fn write_review_record(
    workspace: &Path,
    event: &NetworkMetaAnalysisReviewEvent,
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
        return Err("NMA review record path is unsafe".into());
    }
    let target = root.join(relative);
    let parent = target
        .parent()
        .ok_or_else(|| "NMA review record parent is invalid".to_string())?;
    std::fs::create_dir_all(parent)
        .map_err(|error| format!("NMA review directory failed: {error}"))?;
    if std::fs::symlink_metadata(parent).is_ok_and(|metadata| metadata.file_type().is_symlink()) {
        return Err("NMA review directory must not be a symlink".into());
    }
    let raw = snapshot_bytes(event)?;
    if sha256(&raw) != event.record_sha256 {
        return Err("NMA review record hash changed before write".into());
    }
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&target)
        .map_err(|error| format!("NMA review record write failed: {error}"))?;
    file.write_all(&raw)
        .and_then(|_| file.sync_all())
        .map_err(|error| format!("NMA review record write failed: {error}"))
}

fn append_review_event(root: &Path, event: &NetworkMetaAnalysisReviewEvent) -> Result<(), String> {
    let path = review_log_path(root, &event.project_id)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("NMA review log directory failed: {error}"))?;
        crate::runtime::tighten_private(parent);
    }
    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|error| format!("NMA review log open failed: {error}"))?;
    crate::runtime::tighten_private(&path);
    let line = serde_json::to_string(event).map_err(|error| error.to_string())?;
    writeln!(file, "{line}")
        .and_then(|_| file.sync_all())
        .map_err(|error| format!("NMA review log append failed: {error}"))
}

#[tauri::command(async)]
pub fn append_heor_network_meta_analysis_review(
    app: AppHandle,
    state: tauri::State<NetworkMetaAnalysisReviewState>,
    request: NetworkMetaAnalysisReviewRequest,
) -> Result<NetworkMetaAnalysisReviewEvent, String> {
    let _guard = state.0.lock().map_err(|_| "NMA review lock poisoned")?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    if crate::project::require_project_id(&workspace)? != request.project_id {
        return Err("review projectId does not match the current project".into());
    }
    if !validate_review_text(&request.actor_label, 120)
        || !validate_review_text(&request.rationale, 2_000)
        || !is_sha256(&request.result_sha256)
    {
        return Err("review actor, rationale, or result hash is invalid".into());
    }
    let audit = audit_path(&workspace, &request.result_path);
    if audit.result_sha256.as_deref() != Some(&request.result_sha256) {
        return Err("review must target the exact current NMA result".into());
    }
    if request.action == NetworkMetaAnalysisReviewAction::Accept
        && (!audit.reviewable || !request.checklist.all_confirmed())
    {
        return Err(
            "acceptance requires a complete native audit and all eight Human method checks".into(),
        );
    }
    if audit.execution_id.is_empty() {
        return Err("review result has no valid execution identity".into());
    }
    let root = review_root(&app)?;
    let events = read_review_events(&root, &workspace, &request.project_id)?;
    if latest_review_for_execution(&events, &audit.execution_id).is_some_and(|event| {
        event.result_sha256 == request.result_sha256 && event.action == request.action
    }) {
        return Err(
            "the latest NMA method review already records this action for the exact result".into(),
        );
    }
    let related_artifacts = collect_related_artifacts(&workspace, &audit)?;
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| error.to_string())?
        .as_secs();
    let review_id = crate::runtime::random_hex(16);
    let record_path = format!(
        "heor/network-meta-analysis-reviews/{}-{review_id}.json",
        audit.execution_id
    );
    let mut event = NetworkMetaAnalysisReviewEvent {
        schema_version: REVIEW_EVENT_SCHEMA,
        sequence: events.len() as u64 + 1,
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
    if let Err(error) = append_review_event(&root, &event) {
        let _ = std::fs::remove_file(workspace.join(&event.record_path));
        return Err(error);
    }
    crate::git_snapshot::commit_best_effort(&workspace, "Record NMA method review");
    Ok(event)
}

#[tauri::command(async)]
pub fn list_heor_network_meta_analysis_reviews(
    app: AppHandle,
    state: tauri::State<NetworkMetaAnalysisReviewState>,
    project_id: String,
) -> Result<NetworkMetaAnalysisReviewLog, String> {
    let _guard = state.0.lock().map_err(|_| "NMA review lock poisoned")?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    if crate::project::require_project_id(&workspace)? != project_id {
        return Err("review projectId does not match the current project".into());
    }
    let events = read_review_events(&review_root(&app)?, &workspace, &project_id)?;
    Ok(NetworkMetaAnalysisReviewLog {
        chain_head: events.last().map(|event| event.event_hash.clone()),
        events,
        integrity: "verified_unanchored_sha256_chain",
        identity_assurance: REVIEW_ASSURANCE,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn write(path: &Path, raw: &[u8]) -> String {
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(path, raw).unwrap();
        sha256(raw)
    }

    fn write_json(path: &Path, value: &serde_json::Value) -> String {
        let mut raw = serde_json::to_vec_pretty(value).unwrap();
        raw.push(b'\n');
        write(path, &raw)
    }

    #[test]
    fn weighted_network_reproduces_a_three_node_cycle() {
        let facts = RequestFacts {
            treatments: vec!["a".into(), "b".into(), "c".into()],
            reference: "a".into(),
            effect_measure: "log_odds_ratio".into(),
            rows: vec![
                Contrast {
                    study_id: "s1".into(),
                    treat1: "a".into(),
                    treat2: "b".into(),
                    effect: 0.2,
                    se: 0.1,
                },
                Contrast {
                    study_id: "s2".into(),
                    treat1: "b".into(),
                    treat2: "c".into(),
                    effect: 0.1,
                    se: 0.12,
                },
                Contrast {
                    study_id: "s3".into(),
                    treat1: "a".into(),
                    treat2: "c".into(),
                    effect: 0.4,
                    se: 0.15,
                },
            ],
            ..RequestFacts::default()
        };
        let estimates = expected_estimates(&facts, 0.0).unwrap();
        assert_eq!(estimates.len(), 6);
        let ab = estimates
            .iter()
            .find(|row| row.left == "a" && row.right == "b")
            .unwrap();
        let ba = estimates
            .iter()
            .find(|row| row.left == "b" && row.right == "a")
            .unwrap();
        assert!((ab.effect + ba.effect).abs() < 1e-12);
        assert!((ab.se - ba.se).abs() < 1e-12);
    }

    #[test]
    fn acceptance_requires_all_eight_method_checks() {
        let checklist = NetworkMetaAnalysisChecklist {
            question_outcome_estimand_reviewed: true,
            nodes_connectivity_two_arm_boundary_reviewed: true,
            study_contrasts_provenance_risk_of_bias_reviewed: true,
            transitivity_effect_modifiers_reviewed: true,
            model_tau_method_reviewed: true,
            heterogeneity_prediction_reviewed: true,
            global_local_inconsistency_reviewed: true,
            ranking_transportability_limitations_reviewed: false,
        };
        assert!(!checklist.all_confirmed());
    }

    #[test]
    fn review_event_chain_binds_the_exact_result_and_snapshot() {
        let workspace = std::env::temp_dir().join(format!(
            "ai4heor-nma-review-workspace-{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        let log_root = std::env::temp_dir().join(format!(
            "ai4heor-nma-review-log-{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&workspace).unwrap();
        let checklist = NetworkMetaAnalysisChecklist {
            question_outcome_estimand_reviewed: true,
            nodes_connectivity_two_arm_boundary_reviewed: true,
            study_contrasts_provenance_risk_of_bias_reviewed: true,
            transitivity_effect_modifiers_reviewed: true,
            model_tau_method_reviewed: true,
            heterogeneity_prediction_reviewed: true,
            global_local_inconsistency_reviewed: true,
            ranking_transportability_limitations_reviewed: true,
        };
        let mut event = NetworkMetaAnalysisReviewEvent {
            schema_version: REVIEW_EVENT_SCHEMA,
            sequence: 1,
            review_id: "1".repeat(32),
            project_id: "project-1".into(),
            execution_id: "nma-run-1".into(),
            action: NetworkMetaAnalysisReviewAction::Accept,
            result_path: "heor/network-meta-analysis-runs/nma-run-1/manifest.json".into(),
            result_sha256: "a".repeat(64),
            related_artifacts: vec![crate::heor_approval::ArtifactBinding {
                path: "heor/network-meta-analysis-runs/nma-run-1/manifest.json".into(),
                sha256: "a".repeat(64),
            }],
            checklist,
            actor_label: "Methods reviewer".into(),
            rationale: "Reviewed the exact network and method limitations.".into(),
            timestamp: 1,
            record_path: "heor/network-meta-analysis-reviews/nma-run-1-review.json".into(),
            record_sha256: String::new(),
            assurance: REVIEW_ASSURANCE.into(),
            previous_hash: None,
            event_hash: String::new(),
        };
        event.record_sha256 = sha256(&snapshot_bytes(&event).unwrap());
        event.event_hash = hash_review_event(&event).unwrap();
        write_review_record(&workspace, &event).unwrap();
        append_review_event(&log_root, &event).unwrap();
        let events = read_review_events(&log_root, &workspace, "project-1").unwrap();
        assert_eq!(events, vec![event]);
        let log_path = review_log_path(&log_root, "project-1").unwrap();
        let mut raw = std::fs::read_to_string(&log_path).unwrap();
        raw = raw.replacen("Methods reviewer", "Tampered reviewer", 1);
        std::fs::write(log_path, raw).unwrap();
        assert!(read_review_events(&log_root, &workspace, "project-1").is_err());
        std::fs::remove_dir_all(workspace).unwrap();
        std::fs::remove_dir_all(log_root).unwrap();
    }

    #[test]
    fn native_audit_accepts_a_complete_hash_bound_common_effect_fixture() {
        let root = std::env::temp_dir().join(format!(
            "ai4heor-nma-native-{}",
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ));
        std::fs::create_dir_all(&root).unwrap();
        let evidence_sha = write_json(
            &root.join("heor/evidence-synthesis.json"),
            &serde_json::json!({"schema_version": "test", "records": ["rec1", "rec2", "rec3"]}),
        );
        let source_sha = write(
            &root.join("heor/nma-data/contrasts.csv"),
            b"study_id,treat1,treat2,effect,se\nstudy1,a,b,0.20,0.10\nstudy2,b,c,0.10,0.12\nstudy3,a,c,0.40,0.15\n",
        );
        let checks: Vec<&str> = REVIEW_CHECKS.into_iter().collect();
        let request = serde_json::json!({
            "schema_version": REQUEST_SCHEMA,
            "execution_id": "nma-native-test",
            "status": "ready_for_execution",
            "question": {
                "population": "Adults", "intervention_network": "A, B, C",
                "outcome": "Response", "timepoint": "Twelve weeks",
                "estimand": "Randomized contrast", "study_design": "randomized_parallel_two_arm"
            },
            "evidence_synthesis": {
                "path": "heor/evidence-synthesis.json", "sha256": evidence_sha,
                "included_record_ids": ["rec1", "rec2", "rec3"]
            },
            "source_data": {
                "classification": "public", "execution_boundary": "local_only", "format": "contrast_csv",
                "path": "heor/nma-data/contrasts.csv", "sha256": source_sha,
                "columns": ["study_id", "treat1", "treat2", "effect", "se"],
                "row_count": 3, "study_count": 3, "contains_direct_identifiers": false,
                "missing_policy": "reject", "multiarm_policy": "reject"
            },
            "treatments": [
                {"id": "a", "label": "A", "node_definition": "A", "merging_rationale": "No merging"},
                {"id": "b", "label": "B", "node_definition": "B", "merging_rationale": "No merging"},
                {"id": "c", "label": "C", "node_definition": "C", "merging_rationale": "No merging"}
            ],
            "reference_treatment": "a",
            "effect": {
                "measure": "log_odds_ratio", "scale": "log", "likelihood": "normal", "link": "identity",
                "confidence_level": 0.95, "favorable_direction": "lower"
            },
            "model": {"type": "common", "heterogeneity_variance": "none", "tau_method": "none", "prediction_interval": false},
            "transitivity": {
                "status": "awaiting_human_review", "joint_randomizability_rationale": "Prespecified",
                "effect_modifiers": [{"id": "risk", "label": "Risk", "rationale": "Prespecified", "comparison_summaries": [
                    {"comparison": "a:b", "summary": "Recorded", "source_ids": ["rec1"]},
                    {"comparison": "a:c", "summary": "Recorded", "source_ids": ["rec3"]},
                    {"comparison": "b:c", "summary": "Recorded", "source_ids": ["rec2"]}
                ]}],
                "concerns": []
            },
            "diagnostics": {"global_inconsistency": "design_decomposition", "local_inconsistency": "node_splitting", "ranking": "none"},
            "runtime": {
                "r_version": "4.6.1", "package_versions": {"netmeta": "3.6.1", "meta": "8.5.0", "metafor": "5.0.1"},
                "adapter_sha256": sha256(ADAPTER_BYTES)
            },
            "output": {"directory": "heor/network-meta-analysis-runs/nma-native-test"},
            "study_provenance": [
                {"study_id": "study1", "evidence_record_ids": ["rec1"], "extraction_ids": ["extract1"], "risk_of_bias": "some_concerns"},
                {"study_id": "study2", "evidence_record_ids": ["rec2"], "extraction_ids": ["extract2"], "risk_of_bias": "some_concerns"},
                {"study_id": "study3", "evidence_record_ids": ["rec3"], "extraction_ids": ["extract3"], "risk_of_bias": "some_concerns"}
            ],
            "limitations": ["Synthetic interface fixture."],
            "human_gate": {"status": "awaiting_model_review", "required_checks": checks}
        });
        let request_sha = write_json(&root.join(REQUEST_PATH), &request);
        let request_raw = std::fs::read(root.join(REQUEST_PATH)).unwrap();
        let mut request_errors = Vec::new();
        let facts = validate_request(&root, &request, &request_raw, &mut request_errors);
        assert!(request_errors.is_empty(), "{request_errors:?}");
        let expected = expected_estimates(&facts, 0.0).unwrap();
        let league: Vec<serde_json::Value> = expected
            .iter()
            .map(|row| {
                serde_json::json!({
                    "treat1": row.left, "treat2": row.right, "effect": row.effect, "se": row.se,
                    "lower": row.lower, "upper": row.upper, "natural_effect": row.natural,
                    "prediction_lower": null, "prediction_upper": null
                })
            })
            .collect();
        let reference: Vec<serde_json::Value> = expected
            .iter()
            .filter(|row| row.right == "a")
            .map(|row| {
                serde_json::json!({
                    "treatment": row.left, "effect": row.effect, "se": row.se,
                    "lower": row.lower, "upper": row.upper, "natural_effect": row.natural,
                    "prediction_lower": null, "prediction_upper": null
                })
            })
            .collect();
        let output = root.join("heor/network-meta-analysis-runs/nma-native-test");
        let adapter_sha = write(&output.join("adapter/netmeta_adapter.R"), ADAPTER_BYTES);
        let mut backend = Vec::new();
        for (id, name) in [
            ("matrix", "matrix.tsv"),
            ("diagnostics", "diagnostics.tsv"),
            ("local_inconsistency", "local-inconsistency.tsv"),
            ("ranking", "ranking.tsv"),
            ("warnings", "warnings.txt"),
        ] {
            let relative =
                format!("heor/network-meta-analysis-runs/nma-native-test/backend/{name}");
            let hash = write(&root.join(&relative), format!("{id}\n").as_bytes());
            backend.push(serde_json::json!({"id": id, "path": relative, "sha256": hash}));
        }
        let result = serde_json::json!({
            "schema_version": RESULT_SCHEMA, "execution_id": "nma-native-test", "status": "awaiting_model_review",
            "request": {"path": REQUEST_PATH, "sha256": request_sha},
            "source_data": {"path": "heor/nma-data/contrasts.csv", "sha256": source_sha},
            "evidence_synthesis": {"path": "heor/evidence-synthesis.json", "sha256": evidence_sha},
            "runtime": {
                "r_version": "4.6.1", "rscript_path": "/test/Rscript", "rscript_sha256": "1".repeat(64),
                "package_versions": {"netmeta": "3.6.1", "meta": "8.5.0", "metafor": "5.0.1"},
                "adapter": {"path": "heor/network-meta-analysis-runs/nma-native-test/adapter/netmeta_adapter.R", "sha256": adapter_sha}
            },
            "backend_outputs": backend,
            "network": {"treatments": ["a", "b", "c"], "reference_treatment": "a", "study_count": 3, "direct_comparison_count": 3, "cycle_rank": 1, "connected": true},
            "model": {"effect_measure": "log_odds_ratio", "scale": "log", "likelihood": "normal", "link": "identity", "type": "common", "tau_method": "none", "tau": 0.0, "tau_squared": 0.0, "prediction_interval": false},
            "estimates_vs_reference": reference, "league_table": league,
            "heterogeneity": {"tau": 0.0, "tau_squared": 0.0, "q_total": 1.0, "df_total": 1, "p_total": 0.5, "q_heterogeneity": 0.5, "df_heterogeneity": 1, "p_heterogeneity": 0.5},
            "inconsistency": {"global": {"method": "design_decomposition", "status": "estimable", "q": 0.5, "df": 1, "p_value": 0.5}, "local": []},
            "ranking": {"method": "none", "rows": []},
            "cross_implementation": {"evaluator": EVALUATOR, "scope": "complete_common_effect", "max_abs_reference_error": 0.0, "max_abs_league_error": 0.0, "tolerance": TOLERANCE, "passed": true},
            "warnings": [], "limitations": ["Synthetic interface fixture."],
            "human_gate": request["human_gate"]
        });
        let result_path = "heor/network-meta-analysis-runs/nma-native-test/manifest.json";
        write_json(&root.join(result_path), &result);
        let audit = audit_path(&root, result_path);
        assert!(audit.complete, "{:?}", audit.errors);
        assert!(audit.reviewable);
        std::fs::remove_dir_all(root).unwrap();
    }
}
