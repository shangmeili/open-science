//! Version-bound reference-case audit for HEOR analysis plans.
//!
//! The agent drafts a matrix. This app-owned boundary verifies exact profile,
//! assessment, artifact links, and method checks before approval or execution.
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::path::{Component, Path};
use tauri::{path::BaseDirectory, AppHandle, Manager};

const ASSESSMENT_PATH: &str = "heor/reference-case-assessment.json";
const ARTIFACT_CAP_BYTES: u64 = 5 * 1024 * 1024;

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ReferenceCaseAudit {
    pub complete: bool,
    pub status: &'static str,
    pub profile_id: String,
    pub profile_status: String,
    pub profile_revision: String,
    pub profile_sha256: String,
    pub assessment_sha256: Option<String>,
    pub required_count: usize,
    pub met_required_count: usize,
    pub recommended_count: usize,
    pub met_recommended_count: usize,
    pub blocking_gaps: Vec<String>,
    pub recommended_gaps: Vec<String>,
    pub unresolved_requirements: Vec<String>,
    pub not_applicable_requirements: Vec<String>,
    pub not_applicable_required_count: usize,
    pub errors: Vec<String>,
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn nonempty(value: Option<&serde_json::Value>) -> bool {
    value
        .and_then(serde_json::Value::as_str)
        .is_some_and(|value| !value.trim().is_empty())
}

fn nonempty_string_array(value: Option<&serde_json::Value>) -> bool {
    value
        .and_then(serde_json::Value::as_array)
        .is_some_and(|items| {
            !items.is_empty()
                && items
                    .iter()
                    .all(|item| item.as_str().is_some_and(|value| !value.trim().is_empty()))
        })
}

fn nonempty_decision_strategy(value: Option<&serde_json::Value>) -> bool {
    nonempty(value) || nonempty_string_array(value)
}

fn uncertainty_paths_valid(plan: &serde_json::Value, pointer: &str, probabilistic: bool) -> bool {
    let eligible = plan
        .get("input_provenance")
        .and_then(serde_json::Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|mapping| {
            let path = mapping.get("path")?.as_str()?;
            let status = mapping.get("uncertainty_status")?.as_str()?;
            let valid = if probabilistic {
                status == "distribution_available"
            } else {
                matches!(status, "range_available" | "distribution_available")
            };
            valid.then_some(path)
        })
        .collect::<HashSet<_>>();
    plan.pointer(pointer)
        .and_then(serde_json::Value::as_array)
        .is_some_and(|paths| {
            !paths.is_empty()
                && paths
                    .iter()
                    .all(|path| path.as_str().is_some_and(|path| eligible.contains(path)))
        })
}

fn is_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn is_iso_date(value: &str) -> bool {
    let mut parts = value.split('-');
    let Some(year) = parts.next() else {
        return false;
    };
    let Some(month) = parts.next() else {
        return false;
    };
    let Some(day) = parts.next() else {
        return false;
    };
    if parts.next().is_some() || year.len() != 4 || month.len() != 2 || day.len() != 2 {
        return false;
    }
    let Ok(year) = year.parse::<u16>() else {
        return false;
    };
    let Ok(month) = month.parse::<u8>() else {
        return false;
    };
    let Ok(day) = day.parse::<u8>() else {
        return false;
    };
    if year == 0 || !(1..=12).contains(&month) {
        return false;
    }
    let leap_year = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    let days_in_month = match month {
        2 if leap_year => 29,
        2 => 28,
        4 | 6 | 9 | 11 => 30,
        _ => 31,
    };
    (1..=days_in_month).contains(&day)
}

fn text_at<'a>(value: &'a serde_json::Value, pointer: &str) -> Option<&'a str> {
    value
        .pointer(pointer)
        .and_then(serde_json::Value::as_str)
        .map(str::trim)
        .filter(|value| !value.is_empty())
}

fn supported_app_check(check: &str) -> bool {
    matches!(
        check,
        "decision_scope_declared"
            | "perspective_declared"
            | "comparator_declared"
            | "jurisdiction_england"
            | "nice_nhs_pss_perspective"
            | "full_horizon_declared"
            | "discount_0_035"
            | "discount_0_045"
            | "discount_0_05"
            | "qaly_outcome"
            | "nice_eq5d_reference_case"
            | "incremental_design"
            | "conceptual_model_complete"
            | "validation_plan_documented"
            | "model_artifacts_independent"
            | "half_cycle_enabled"
            | "input_provenance_complete"
            | "assumptions_resolved"
            | "cost_scope_documented"
            | "uncertainty_plan_documented"
    )
}

fn read_capped(path: &Path, label: &str) -> Result<Vec<u8>, String> {
    let metadata =
        std::fs::metadata(path).map_err(|error| format!("{label} unavailable: {error}"))?;
    if !metadata.is_file() || metadata.len() > ARTIFACT_CAP_BYTES {
        return Err(format!("{label} is not a reviewable artifact"));
    }
    std::fs::read(path).map_err(|error| format!("{label} unavailable: {error}"))
}

fn load_profile(
    app: &AppHandle,
    expected_id: &str,
) -> Result<(serde_json::Value, Vec<u8>), String> {
    if expected_id.is_empty()
        || expected_id.len() > 80
        || !expected_id
            .chars()
            .all(|character| character.is_ascii_alphanumeric() || matches!(character, '-' | '_'))
    {
        return Err("invalid reference-case id".into());
    }
    let path = app
        .path()
        .resolve(
            format!("skills-core/heor-reference-case/assets/profiles/{expected_id}.json"),
            BaseDirectory::Resource,
        )
        .map_err(|error| format!("registered reference case unavailable: {error}"))?;
    let raw = read_capped(&path, "registered reference case")?;
    let value = serde_json::from_slice(&raw)
        .map_err(|error| format!("registered reference case is invalid: {error}"))?;
    Ok((value, raw))
}

fn existing_evidence_path(workspace: &Path, value: &str) -> bool {
    let relative = Path::new(value);
    if relative.is_absolute()
        || relative
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return false;
    }
    let Ok(workspace) = workspace.canonicalize() else {
        return false;
    };
    let Ok(path) = workspace.join(relative).canonicalize() else {
        return false;
    };
    path.starts_with(&workspace) && path.is_file()
}

fn automatic_check(
    check: &str,
    plan: &serde_json::Value,
    conceptual_complete: bool,
    evidence_complete: bool,
) -> bool {
    let horizon = plan
        .pointer("/decision_problem/time_horizon_years")
        .and_then(serde_json::Value::as_f64)
        .unwrap_or(0.0);
    match check {
        "decision_scope_declared" => {
            [
                "title",
                "population",
                "perspective",
                "outcome",
                "jurisdiction",
            ]
            .iter()
            .all(|field| nonempty(plan.pointer(&format!("/decision_problem/{field}"))))
                && ["intervention", "comparator"].iter().all(|field| {
                    nonempty_decision_strategy(plan.pointer(&format!("/decision_problem/{field}")))
                })
                && horizon.is_finite()
                && horizon > 0.0
        }
        "perspective_declared" => nonempty(plan.pointer("/decision_problem/perspective")),
        "comparator_declared" => {
            nonempty_decision_strategy(plan.pointer("/decision_problem/comparator"))
        }
        "jurisdiction_england" => text_at(plan, "/decision_problem/jurisdiction")
            .is_some_and(|value| value.eq_ignore_ascii_case("england")),
        "nice_nhs_pss_perspective" => {
            text_at(plan, "/decision_problem/perspective").is_some_and(|value| {
                let normalized = value.to_ascii_lowercase();
                normalized.contains("nhs")
                    && (normalized.contains("personal social services")
                        || normalized.contains("pss"))
            })
        }
        "full_horizon_declared" => {
            let cycles = plan
                .get("cycles")
                .and_then(serde_json::Value::as_f64)
                .unwrap_or(0.0);
            let length = plan
                .get("cycle_length_years")
                .and_then(serde_json::Value::as_f64)
                .unwrap_or(0.0);
            horizon > 0.0 && cycles * length + f64::EPSILON >= horizon
        }
        "discount_0_05" => {
            horizon <= 1.0
                || (plan
                    .pointer("/discount_rates/costs")
                    .and_then(serde_json::Value::as_f64)
                    == Some(0.05)
                    && plan
                        .pointer("/discount_rates/outcomes")
                        .and_then(serde_json::Value::as_f64)
                        == Some(0.05))
        }
        "discount_0_045" => {
            horizon <= 1.0
                || (plan
                    .pointer("/discount_rates/costs")
                    .and_then(serde_json::Value::as_f64)
                    == Some(0.045)
                    && plan
                        .pointer("/discount_rates/outcomes")
                        .and_then(serde_json::Value::as_f64)
                        == Some(0.045))
        }
        "discount_0_035" => {
            horizon <= 1.0
                || (plan
                    .pointer("/discount_rates/costs")
                    .and_then(serde_json::Value::as_f64)
                    == Some(0.035)
                    && plan
                        .pointer("/discount_rates/outcomes")
                        .and_then(serde_json::Value::as_f64)
                        == Some(0.035))
        }
        "qaly_outcome" => plan
            .pointer("/decision_problem/outcome")
            .and_then(serde_json::Value::as_str)
            .is_some_and(|value| value.to_ascii_lowercase().contains("qaly")),
        "nice_eq5d_reference_case" => {
            let measure =
                text_at(plan, "/methodology/health_outcomes/measure").map(str::to_ascii_lowercase);
            let data_system = text_at(plan, "/methodology/health_outcomes/data_descriptive_system")
                .map(str::to_ascii_lowercase);
            let value_set = text_at(plan, "/methodology/health_outcomes/value_set")
                .map(str::to_ascii_lowercase);
            let valuation_population =
                text_at(plan, "/methodology/health_outcomes/valuation_population")
                    .map(str::to_ascii_lowercase);
            let respondent = text_at(plan, "/methodology/health_outcomes/respondent")
                .map(str::to_ascii_lowercase);
            let mapping = text_at(plan, "/methodology/health_outcomes/mapping_method")
                .map(str::to_ascii_lowercase);
            let departure = text_at(
                plan,
                "/methodology/health_outcomes/reference_case_departure",
            );
            measure.is_some_and(|value| value.replace('-', "").contains("eq5d"))
                && value_set.is_some_and(|value| {
                    value.contains("3l") && (value.contains("uk") || value.contains("england"))
                })
                && valuation_population.is_some_and(|value| {
                    (value.contains("uk") || value.contains("united kingdom"))
                        && value.contains("general")
                })
                && respondent
                    .is_some_and(|value| value.contains("patient") || value.contains("carer"))
                && data_system.is_some_and(|value| {
                    value.contains("3l")
                        || (value.contains("5l")
                            && mapping.as_deref().is_some_and(|mapping| {
                                mapping.contains("dsu") && mapping.contains("3l")
                            }))
                })
                && departure.is_none()
        }
        "incremental_design" => {
            plan.pointer("/strategies/comparator").is_some()
                && plan.pointer("/strategies/intervention").is_some()
        }
        "conceptual_model_complete"
        | "validation_plan_documented"
        | "model_artifacts_independent" => conceptual_complete,
        "half_cycle_enabled" => {
            plan.get("half_cycle_correction")
                .and_then(serde_json::Value::as_bool)
                == Some(true)
        }
        "input_provenance_complete" => evidence_complete,
        "assumptions_resolved" => conceptual_complete && evidence_complete,
        "cost_scope_documented" => {
            nonempty_string_array(plan.pointer("/methodology/cost_scope/included_categories"))
                && nonempty(plan.pointer("/methodology/cost_scope/perspective_alignment"))
        }
        "uncertainty_plan_documented" => {
            plan.pointer("/methodology/uncertainty_analysis/deterministic/planned")
                .and_then(serde_json::Value::as_bool)
                == Some(true)
                && uncertainty_paths_valid(
                    plan,
                    "/methodology/uncertainty_analysis/deterministic/input_paths",
                    false,
                )
                && plan
                    .pointer("/methodology/uncertainty_analysis/probabilistic/planned")
                    .and_then(serde_json::Value::as_bool)
                    == Some(true)
                && plan
                    .pointer("/methodology/uncertainty_analysis/probabilistic/iterations")
                    .and_then(serde_json::Value::as_u64)
                    .is_some_and(|iterations| iterations > 0)
                && uncertainty_paths_valid(
                    plan,
                    "/methodology/uncertainty_analysis/probabilistic/input_paths",
                    true,
                )
                && nonempty_string_array(
                    plan.pointer("/methodology/uncertainty_analysis/structural_scenarios"),
                )
        }
        _ => false,
    }
}

fn requirement_applicable(requirement: &serde_json::Value, plan: &serde_json::Value) -> bool {
    match requirement
        .get("applicability")
        .and_then(serde_json::Value::as_str)
        .unwrap_or("invalid")
    {
        "always" | "model_based" | "markov_model" | "markov_or_partitioned_survival" => true,
        "horizon_over_one_year" => plan
            .pointer("/decision_problem/time_horizon_years")
            .and_then(serde_json::Value::as_f64)
            .is_some_and(|horizon| horizon > 1.0),
        "cost_utility_analysis" => plan
            .pointer("/decision_problem/outcome")
            .and_then(serde_json::Value::as_str)
            .is_some_and(|outcome| outcome.to_ascii_lowercase().contains("qaly")),
        _ => true,
    }
}

fn audit_values(
    workspace: &Path,
    plan: &serde_json::Value,
    profile: &serde_json::Value,
    profile_raw: &[u8],
    assessment: Option<(&serde_json::Value, &[u8])>,
) -> ReferenceCaseAudit {
    let profile_id = profile
        .get("id")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default()
        .to_string();
    let profile_status = profile
        .get("status")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default()
        .to_string();
    let profile_revision = profile
        .get("revision")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default()
        .to_string();
    let profile_sha256 = sha256(profile_raw);
    let requirements = profile
        .get("requirements")
        .and_then(serde_json::Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    let required_count = requirements
        .iter()
        .filter(|item| item.get("level").and_then(serde_json::Value::as_str) == Some("required"))
        .count();
    let recommended_count = requirements.len().saturating_sub(required_count);
    let mut audit = ReferenceCaseAudit {
        complete: false,
        status: "incomplete",
        profile_id,
        profile_status,
        profile_revision,
        profile_sha256,
        assessment_sha256: assessment.map(|(_, raw)| sha256(raw)),
        required_count,
        met_required_count: 0,
        recommended_count,
        met_recommended_count: 0,
        blocking_gaps: Vec::new(),
        recommended_gaps: Vec::new(),
        unresolved_requirements: Vec::new(),
        not_applicable_requirements: Vec::new(),
        not_applicable_required_count: 0,
        errors: Vec::new(),
    };

    if profile
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some("0.2.0")
    {
        audit
            .errors
            .push("reference-case profile schema_version must be 0.2.0".into());
    }
    for field in [
        "id",
        "title",
        "revision",
        "checked_on",
        "source_url",
        "source_sha256",
    ] {
        if !nonempty(profile.get(field)) {
            audit
                .errors
                .push(format!("reference-case profile {field} is required"));
        }
    }
    if !profile
        .get("source_url")
        .and_then(serde_json::Value::as_str)
        .is_some_and(|value| value.starts_with("https://"))
    {
        audit
            .errors
            .push("reference-case profile source_url must use HTTPS".into());
    }
    if !profile
        .get("source_sha256")
        .and_then(serde_json::Value::as_str)
        .is_some_and(is_sha256)
    {
        audit
            .errors
            .push("reference-case profile source_sha256 is invalid".into());
    }
    if profile.get("canonical_source_url").is_some()
        && !profile
            .get("canonical_source_url")
            .and_then(serde_json::Value::as_str)
            .is_some_and(|value| value.starts_with("https://"))
    {
        audit
            .errors
            .push("reference-case profile canonical_source_url must use HTTPS".into());
    }
    if profile.get("source_media_type").is_some() && !nonempty(profile.get("source_media_type")) {
        audit
            .errors
            .push("reference-case profile source_media_type is invalid".into());
    }
    if profile.get("source_bytes").is_some()
        && !profile
            .get("source_bytes")
            .and_then(serde_json::Value::as_u64)
            .is_some_and(|value| value > 0)
    {
        audit
            .errors
            .push("reference-case profile source_bytes must be positive".into());
    }
    if !profile
        .get("checked_on")
        .and_then(serde_json::Value::as_str)
        .is_some_and(is_iso_date)
    {
        audit
            .errors
            .push("reference-case profile checked_on must be an ISO date".into());
    }
    if audit.profile_status == "current"
        && !profile
            .get("effective_on")
            .and_then(serde_json::Value::as_str)
            .is_some_and(is_iso_date)
    {
        audit
            .errors
            .push("current reference-case profile effective_on must be an ISO date".into());
    }
    if requirements.is_empty() {
        audit
            .errors
            .push("reference-case profile has no requirements".into());
    }
    let mut profile_ids = HashSet::new();
    for (index, requirement) in requirements.iter().enumerate() {
        let id = requirement.get("id").and_then(serde_json::Value::as_str);
        if !id.is_some_and(|id| !id.trim().is_empty() && profile_ids.insert(id)) {
            audit.errors.push(format!(
                "registered requirement {index} has a missing or duplicate id"
            ));
        }
        for field in [
            "category",
            "title",
            "source_locator",
            "app_check",
            "applicability",
        ] {
            if !nonempty(requirement.get(field)) {
                audit
                    .errors
                    .push(format!("registered requirement {index} omitted {field}"));
            }
        }
        if !matches!(
            requirement.get("level").and_then(serde_json::Value::as_str),
            Some("required" | "recommended")
        ) {
            audit
                .errors
                .push(format!("registered requirement {index} has invalid level"));
        }
        if !requirement
            .get("app_check")
            .and_then(serde_json::Value::as_str)
            .is_some_and(supported_app_check)
        {
            audit.errors.push(format!(
                "registered requirement {index} has unsupported app_check"
            ));
        }
        if !matches!(
            requirement
                .get("applicability")
                .and_then(serde_json::Value::as_str),
            Some(
                "always"
                    | "horizon_over_one_year"
                    | "cost_utility_analysis"
                    | "model_based"
                    | "markov_model"
                    | "markov_or_partitioned_survival"
            )
        ) {
            audit.errors.push(format!(
                "registered requirement {index} has unsupported applicability"
            ));
        }
    }
    if !matches!(audit.profile_status.as_str(), "current" | "draft") {
        audit
            .errors
            .push("reference-case profile status is invalid".into());
    }
    if audit.profile_status == "draft" {
        audit
            .errors
            .push("draft reference-case profiles cannot authorize an analysis".into());
    }
    let selected_id = plan
        .pointer("/reference_case/id")
        .and_then(serde_json::Value::as_str);
    let selected_status = plan
        .pointer("/reference_case/status")
        .and_then(serde_json::Value::as_str);
    if selected_id != Some(audit.profile_id.as_str())
        || selected_status != Some(audit.profile_status.as_str())
    {
        audit
            .errors
            .push("analysis plan reference_case does not match the registered profile".into());
    }

    let Some((assessment, assessment_raw)) = assessment else {
        audit.errors.push(format!("{ASSESSMENT_PATH} is required"));
        return audit;
    };
    if assessment
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some("0.1.0")
    {
        audit
            .errors
            .push("reference-case assessment schema_version must be 0.1.0".into());
    }
    for field in ["assessment_id", "analysis_id", "assessed_on"] {
        if !nonempty(assessment.get(field)) {
            audit
                .errors
                .push(format!("reference-case assessment {field} is required"));
        }
    }
    if assessment.get("analysis_id") != plan.get("analysis_id") {
        audit
            .errors
            .push("reference-case assessment analysis_id does not match the plan".into());
    }
    match assessment.get("status").and_then(serde_json::Value::as_str) {
        Some("ready_for_human_review") => {}
        Some("draft") => audit
            .errors
            .push("reference-case assessment is still draft".into()),
        _ => audit
            .errors
            .push("reference-case assessment status is invalid".into()),
    }
    let assessment_profile = assessment
        .get("profile")
        .and_then(serde_json::Value::as_object);
    for (field, expected) in [
        ("id", audit.profile_id.as_str()),
        ("status", audit.profile_status.as_str()),
        ("revision", audit.profile_revision.as_str()),
        ("content_sha256", audit.profile_sha256.as_str()),
    ] {
        if assessment_profile
            .and_then(|value| value.get(field))
            .and_then(serde_json::Value::as_str)
            != Some(expected)
        {
            audit.errors.push(format!(
                "reference-case assessment profile.{field} does not match the registered profile"
            ));
        }
    }
    let link = plan
        .get("reference_case_assessment")
        .and_then(serde_json::Value::as_object);
    if link
        .and_then(|value| value.get("path"))
        .and_then(serde_json::Value::as_str)
        != Some(ASSESSMENT_PATH)
    {
        audit
            .errors
            .push(format!("analysis plan must link {ASSESSMENT_PATH}"));
    }
    let linked_hash = link
        .and_then(|value| value.get("content_sha256"))
        .and_then(serde_json::Value::as_str);
    let assessment_sha256 = sha256(assessment_raw);
    if !linked_hash.is_some_and(is_sha256) || linked_hash != Some(assessment_sha256.as_str()) {
        audit.errors.push(
            "analysis plan reference-case assessment hash does not match the current artifact"
                .into(),
        );
    }

    let conceptual_complete =
        crate::heor_artifacts::current_conceptual_model_hash_and_audit(workspace)
            .ok()
            .is_some_and(|(_, conceptual)| conceptual.complete);
    let evidence_complete = crate::heor_evidence::audit_plan(plan).complete;
    let rows = assessment
        .get("requirements")
        .and_then(serde_json::Value::as_array)
        .map(Vec::as_slice)
        .unwrap_or(&[]);
    let mut row_map = HashMap::new();
    let expected_ids = requirements
        .iter()
        .filter_map(|requirement| requirement.get("id").and_then(serde_json::Value::as_str))
        .collect::<HashSet<_>>();
    for (index, row) in rows.iter().enumerate() {
        let Some(id) = row
            .get("requirement_id")
            .and_then(serde_json::Value::as_str)
        else {
            audit
                .errors
                .push(format!("requirements[{index}] omitted requirement_id"));
            continue;
        };
        if !expected_ids.contains(id) {
            audit.errors.push(format!(
                "requirements[{index}] references unknown requirement {id}"
            ));
        } else if row_map.insert(id, row).is_some() {
            audit
                .errors
                .push(format!("requirements[{index}] duplicates {id}"));
        }
    }

    for requirement in requirements {
        let Some(id) = requirement.get("id").and_then(serde_json::Value::as_str) else {
            audit
                .errors
                .push("registered requirement omitted id".into());
            continue;
        };
        let level = requirement
            .get("level")
            .and_then(serde_json::Value::as_str)
            .unwrap_or("invalid");
        if !matches!(level, "required" | "recommended") {
            audit
                .errors
                .push(format!("registered requirement {id} has invalid level"));
        }
        let Some(row) = row_map.get(id) else {
            audit
                .errors
                .push(format!("assessment omitted requirement {id}"));
            continue;
        };
        if !nonempty(row.get("rationale")) {
            audit
                .errors
                .push(format!("requirement {id} needs a rationale"));
        }
        let paths = row
            .get("evidence_paths")
            .and_then(serde_json::Value::as_array)
            .map(Vec::as_slice)
            .unwrap_or(&[]);
        let paths_valid = paths.iter().all(|path| {
            path.as_str()
                .is_some_and(|value| existing_evidence_path(workspace, value))
        });
        let status = row.get("status").and_then(serde_json::Value::as_str);
        let applicable = requirement_applicable(requirement, plan);
        match status {
            Some("met") => {
                if !applicable {
                    audit.errors.push(format!(
                        "requirement {id} is not applicable to the current analysis and must not be marked met"
                    ));
                    continue;
                }
                if paths.is_empty() || !paths_valid {
                    audit.errors.push(format!(
                        "requirement {id} needs existing workspace evidence paths"
                    ));
                    continue;
                }
                let check = requirement
                    .get("app_check")
                    .and_then(serde_json::Value::as_str)
                    .unwrap_or_default();
                if !automatic_check(check, plan, conceptual_complete, evidence_complete) {
                    audit.errors.push(format!(
                        "requirement {id} conflicts with the current artifacts"
                    ));
                } else if level == "required" {
                    audit.met_required_count += 1;
                } else {
                    audit.met_recommended_count += 1;
                }
            }
            Some("gap") if level == "required" => audit.blocking_gaps.push(id.into()),
            Some("gap") => audit.recommended_gaps.push(id.into()),
            Some("unresolved") => audit.unresolved_requirements.push(id.into()),
            Some("not_applicable") if applicable => audit.errors.push(format!(
                "requirement {id} is applicable to the current analysis"
            )),
            Some("not_applicable") => audit.not_applicable_requirements.push(id.into()),
            _ => audit
                .errors
                .push(format!("requirement {id} has invalid status")),
        }
    }

    let required_not_applicable = requirements
        .iter()
        .filter(|requirement| {
            requirement.get("level").and_then(serde_json::Value::as_str) == Some("required")
                && requirement
                    .get("id")
                    .and_then(serde_json::Value::as_str)
                    .is_some_and(|id| {
                        audit
                            .not_applicable_requirements
                            .iter()
                            .any(|item| item == id)
                    })
        })
        .count();
    audit.not_applicable_required_count = required_not_applicable;
    audit.complete = audit.errors.is_empty()
        && audit.blocking_gaps.is_empty()
        && audit.unresolved_requirements.is_empty()
        && audit.met_required_count + required_not_applicable == audit.required_count;
    if audit.complete {
        audit.status = "complete";
    }
    audit
}

pub fn audit_reference_case_for_plan(
    app: &AppHandle,
    workspace: &Path,
    plan_raw: &[u8],
) -> Result<ReferenceCaseAudit, String> {
    let plan: serde_json::Value = serde_json::from_slice(plan_raw)
        .map_err(|error| format!("reference-case plan audit failed: {error}"))?;
    let profile_id = plan
        .pointer("/reference_case/id")
        .and_then(serde_json::Value::as_str)
        .ok_or("analysis plan omitted reference-case id")?;
    let (profile, profile_raw) = load_profile(app, profile_id)?;
    let assessment_raw = read_capped(&workspace.join(ASSESSMENT_PATH), ASSESSMENT_PATH).ok();
    let assessment = assessment_raw
        .as_deref()
        .map(|raw| {
            serde_json::from_slice(raw)
                .map_err(|error| format!("reference-case assessment is invalid: {error}"))
        })
        .transpose()?;
    Ok(audit_values(
        workspace,
        &plan,
        &profile,
        &profile_raw,
        assessment.as_ref().zip(assessment_raw.as_deref()),
    ))
}

pub fn require_analysis_plan_approvable(
    app: &AppHandle,
    workspace: &Path,
    plan_raw: &[u8],
) -> Result<(), String> {
    let audit = audit_reference_case_for_plan(app, workspace, plan_raw)?;
    if !audit.complete {
        return Err(format!(
            "reference-case audit is incomplete: {}/{} required items met, {} blocking gaps, {} unresolved items, {} errors",
            audit.met_required_count,
            audit.required_count,
            audit.blocking_gaps.len(),
            audit.unresolved_requirements.len(),
            audit.errors.len()
        ));
    }
    Ok(())
}

#[tauri::command(async)]
pub fn audit_heor_reference_case(app: AppHandle) -> Result<ReferenceCaseAudit, String> {
    let workspace = crate::runtime::workspace_dir(&app)?;
    let raw = read_capped(
        &workspace.join("heor/analysis-plan.json"),
        "heor/analysis-plan.json",
    )?;
    audit_reference_case_for_plan(&app, &workspace, &raw)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unsafe_evidence_paths_fail_closed() {
        let root =
            std::env::temp_dir().join(format!("heor-reference-case-path-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        assert!(!existing_evidence_path(&root, "../outside.json"));
        assert!(!existing_evidence_path(&root, "/tmp/outside.json"));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn automatic_checks_reject_wrong_discount_and_short_model() {
        let plan = serde_json::json!({
            "decision_problem": {
                "time_horizon_years": 10,
                "perspective": "Healthcare system",
                "comparator": "Standard care",
                "outcome": "QALY"
            },
            "cycles": 5,
            "cycle_length_years": 1,
            "discount_rates": {"costs": 0.03, "outcomes": 0.03},
            "half_cycle_correction": true,
            "strategies": {"comparator": {}, "intervention": {}}
        });
        assert!(!automatic_check("full_horizon_declared", &plan, true, true));
        assert!(!automatic_check("discount_0_05", &plan, true, true));
        assert!(automatic_check("qaly_outcome", &plan, true, true));
        assert!(!automatic_check("cost_scope_documented", &plan, true, true));
        assert!(!automatic_check(
            "uncertainty_plan_documented",
            &plan,
            true,
            true
        ));
    }

    #[test]
    fn automatic_checks_enforce_nice_jurisdiction_perspective_and_discount() {
        let mut plan = serde_json::json!({
            "decision_problem": {
                "title": "Technology appraisal",
                "population": "Adults with advanced disease",
                "intervention": "New treatment",
                "comparator": "Established NHS practice",
                "perspective": "NHS and personal social services (PSS)",
                "time_horizon_years": 20,
                "outcome": "QALY",
                "jurisdiction": "England"
            },
            "cycles": 20,
            "cycle_length_years": 1,
            "discount_rates": {"costs": 0.035, "outcomes": 0.035},
            "methodology": {
                "health_outcomes": {
                    "measure": "EQ-5D",
                    "data_descriptive_system": "5L",
                    "value_set": "UK EQ-5D-3L",
                    "valuation_population": "UK general population",
                    "respondent": "patient_or_carer",
                    "mapping_method": "NICE DSU EEPRU mapping to 3L",
                    "reference_case_departure": null
                }
            },
            "strategies": {"comparator": {}, "intervention": {}}
        });
        assert!(automatic_check(
            "decision_scope_declared",
            &plan,
            true,
            true
        ));
        plan["decision_problem"]["intervention"] = serde_json::json!(["New treatment"]);
        plan["decision_problem"]["comparator"] = serde_json::json!(["Established NHS practice"]);
        assert!(automatic_check(
            "decision_scope_declared",
            &plan,
            true,
            true
        ));
        assert!(automatic_check("comparator_declared", &plan, true, true));
        assert!(automatic_check("jurisdiction_england", &plan, true, true));
        assert!(automatic_check(
            "nice_nhs_pss_perspective",
            &plan,
            true,
            true
        ));
        assert!(automatic_check("discount_0_035", &plan, true, true));
        assert!(automatic_check(
            "nice_eq5d_reference_case",
            &plan,
            true,
            true
        ));

        plan["decision_problem"]["jurisdiction"] = serde_json::json!("Scotland");
        assert!(!automatic_check("jurisdiction_england", &plan, true, true));
        plan["decision_problem"]["jurisdiction"] = serde_json::json!("England");
        plan["decision_problem"]["perspective"] = serde_json::json!("NHS only");
        assert!(!automatic_check(
            "nice_nhs_pss_perspective",
            &plan,
            true,
            true
        ));
        plan["decision_problem"]["perspective"] =
            serde_json::json!("NHS and personal social services (PSS)");
        plan["discount_rates"]["costs"] = serde_json::json!(0.05);
        assert!(!automatic_check("discount_0_035", &plan, true, true));
        plan["methodology"]["health_outcomes"]["value_set"] = serde_json::json!("EQ-5D-5L England");
        assert!(!automatic_check(
            "nice_eq5d_reference_case",
            &plan,
            true,
            true
        ));
    }

    #[test]
    fn malformed_profile_source_and_unknown_app_check_fail_closed() {
        let root = std::env::temp_dir().join(format!(
            "heor-reference-case-profile-contract-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        let profile = serde_json::json!({
            "schema_version": "0.2.0",
            "id": "test-current",
            "title": "Test profile",
            "revision": "test-1",
            "status": "current",
            "effective_on": "2026-04-31",
            "checked_on": "2026-02-31",
            "source_url": "http://example.test/profile.pdf",
            "source_sha256": "not-a-sha256",
            "requirements": [{
                "id": "perspective",
                "category": "decision_problem",
                "level": "required",
                "title": "Perspective",
                "source_locator": "Test 1",
                "app_check": "unknown_check",
                "applicability": "always"
            }]
        });
        let profile_raw = serde_json::to_vec(&profile).unwrap();
        let plan = serde_json::json!({
            "reference_case": {"id": "test-current", "status": "current"}
        });
        let audit = audit_values(&root, &plan, &profile, &profile_raw, None);
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("source_url must use HTTPS")));
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("source_sha256 is invalid")));
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("checked_on must be an ISO date")));
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("effective_on must be an ISO date")));
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("unsupported app_check")));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn packaged_nice_profile_contract_is_native_auditable() {
        let raw = include_bytes!(
            "../../../../runtime/skills/core/heor-reference-case/assets/profiles/NICE-PMG36-2026-current.json"
        );
        let profile: serde_json::Value = serde_json::from_slice(raw).unwrap();
        let plan = serde_json::json!({
            "reference_case": {
                "id": "NICE-PMG36-2026-current",
                "status": "current"
            }
        });
        let root = std::env::temp_dir().join(format!(
            "heor-reference-case-packaged-profile-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();

        let audit = audit_values(&root, &plan, &profile, raw, None);

        assert_eq!(audit.profile_id, "NICE-PMG36-2026-current");
        assert_eq!(audit.required_count + audit.recommended_count, 15);
        assert_eq!(audit.errors, vec![format!("{ASSESSMENT_PATH} is required")]);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn structured_cost_and_uncertainty_plans_are_machine_checkable() {
        let plan = serde_json::json!({
            "methodology": {
                "cost_scope": {
                    "included_categories": ["direct medical costs"],
                    "perspective_alignment": "Matches the healthcare-system perspective"
                },
                "uncertainty_analysis": {
                    "deterministic": {"planned": true, "input_paths": ["cycles"]},
                    "probabilistic": {
                        "planned": true,
                        "input_paths": ["transition_matrix"],
                        "iterations": 1000
                    },
                    "structural_scenarios": ["Alternative time horizon"]
                }
            },
            "input_provenance": [
                {"path": "cycles", "uncertainty_status": "range_available"},
                {"path": "transition_matrix", "uncertainty_status": "distribution_available"}
            ]
        });
        assert!(automatic_check(
            "cost_scope_documented",
            &plan,
            false,
            false
        ));
        assert!(automatic_check(
            "uncertainty_plan_documented",
            &plan,
            false,
            false
        ));
    }

    #[test]
    fn required_items_pass_while_recommended_gaps_remain_visible() {
        let root =
            std::env::temp_dir().join(format!("heor-reference-case-matrix-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("heor")).unwrap();
        let profile = serde_json::json!({
            "schema_version": "0.2.0",
            "id": "test-current",
            "title": "Test current profile",
            "revision": "test-1",
            "status": "current",
            "effective_on": "2026-01-01",
            "checked_on": "2026-07-14",
            "source_url": "https://example.test/profile.pdf",
            "source_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "requirements": [
                {
                    "id": "perspective", "category": "decision_problem", "level": "required",
                    "title": "Perspective", "source_locator": "Test 1",
                    "app_check": "perspective_declared", "applicability": "always"
                },
                {
                    "id": "half-cycle", "category": "model", "level": "recommended",
                    "title": "Half cycle", "source_locator": "Test 2",
                    "app_check": "half_cycle_enabled", "applicability": "markov_model"
                },
                {
                    "id": "discount", "category": "discounting", "level": "required",
                    "title": "Discount", "source_locator": "Test 3",
                    "app_check": "discount_0_05", "applicability": "horizon_over_one_year"
                }
            ]
        });
        let profile_raw = serde_json::to_vec(&profile).unwrap();
        let assessment = serde_json::json!({
            "schema_version": "0.1.0",
            "assessment_id": "assessment-1",
            "analysis_id": "analysis-1",
            "status": "ready_for_human_review",
            "assessed_on": "2026-07-14",
            "profile": {
                "id": "test-current",
                "revision": "test-1",
                "status": "current",
                "content_sha256": sha256(&profile_raw)
            },
            "requirements": [
                {
                    "requirement_id": "perspective", "status": "met",
                    "rationale": "Declared", "evidence_paths": ["heor/analysis-plan.json"]
                },
                {
                    "requirement_id": "half-cycle", "status": "gap",
                    "rationale": "Not yet applied", "evidence_paths": []
                },
                {
                    "requirement_id": "discount", "status": "not_applicable",
                    "rationale": "The horizon is one year", "evidence_paths": []
                }
            ]
        });
        let assessment_raw = serde_json::to_vec(&assessment).unwrap();
        std::fs::write(root.join(ASSESSMENT_PATH), &assessment_raw).unwrap();
        let plan = serde_json::json!({
            "analysis_id": "analysis-1",
            "decision_problem": {
                "perspective": "Healthcare system",
                "time_horizon_years": 1.0
            },
            "reference_case": {"id": "test-current", "status": "current"},
            "reference_case_assessment": {
                "path": ASSESSMENT_PATH,
                "content_sha256": sha256(&assessment_raw)
            }
        });
        std::fs::write(
            root.join("heor/analysis-plan.json"),
            serde_json::to_vec(&plan).unwrap(),
        )
        .unwrap();

        let audit = audit_values(
            &root,
            &plan,
            &profile,
            &profile_raw,
            Some((&assessment, &assessment_raw)),
        );
        assert!(audit.complete, "{:?}", audit.errors);
        assert_eq!(audit.met_required_count, 1);
        assert_eq!(audit.not_applicable_required_count, 1);
        assert_eq!(audit.not_applicable_requirements, vec!["discount"]);
        assert_eq!(audit.recommended_gaps, vec!["half-cycle"]);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn not_applicable_requires_a_matching_machine_checkable_condition() {
        let discount = serde_json::json!({"applicability": "horizon_over_one_year"});
        let short_plan = serde_json::json!({
            "decision_problem": {"time_horizon_years": 1.0, "outcome": "QALY"}
        });
        let long_plan = serde_json::json!({
            "decision_problem": {"time_horizon_years": 5.0, "outcome": "QALY"}
        });
        assert!(!requirement_applicable(&discount, &short_plan));
        assert!(requirement_applicable(&discount, &long_plan));

        let qaly = serde_json::json!({"applicability": "cost_utility_analysis"});
        let non_cua = serde_json::json!({
            "decision_problem": {"time_horizon_years": 5.0, "outcome": "Life-years gained"}
        });
        assert!(!requirement_applicable(&qaly, &non_cua));
        assert!(requirement_applicable(&qaly, &long_plan));
    }
}
