//! Native audit, execution, and replay challenge for bounded advanced VOI.
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::io::Write;
use std::path::{Component, Path, PathBuf};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{path::BaseDirectory, AppHandle, Manager};

pub const ADVANCED_VOI_PLAN_PATH: &str = "heor/advanced-voi-plan.json";
pub const ADVANCED_VOI_RESULT_PATH: &str = "heor/results/advanced-voi.json";
pub const ADVANCED_VOI_REPLAY_PATH: &str = "heor/results/advanced-voi-replay.json";
const ANALYSIS_PLAN_PATH: &str = "heor/analysis-plan.json";
const UNCERTAINTY_PLAN_PATH: &str = "heor/uncertainty-plan.json";
const UNCERTAINTY_RESULT_PATH: &str = "heor/results/uncertainty.json";
const OUTPUT_CAP_BYTES: usize = 25 * 1024 * 1024;
const REVIEW_EVENT_SCHEMA: u32 = 1;
const REVIEW_ASSURANCE: &str = "app_owned_local_human_assertion";
const REQUIRED_LIMITATIONS: [&str; 5] = [
    "model_and_parameter_scope",
    "population_and_implementation_scope",
    "evppi_nested_monte_carlo_error",
    "evsi_normal_normal_study_model",
    "decision_authority_remains_human",
];

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AdvancedVoiAudit {
    pub complete: bool,
    pub reviewable: bool,
    pub status: &'static str,
    pub voi_id: String,
    pub analysis_id: String,
    pub uncertainty_id: String,
    pub advanced_voi_plan_sha256: String,
    pub analysis_plan_sha256: String,
    pub uncertainty_plan_sha256: String,
    pub uncertainty_result_sha256: String,
    pub uncertainty_schema_version: String,
    pub decision_threshold: Option<f64>,
    pub population_year_count: usize,
    pub effective_population: Option<f64>,
    pub evppi_group_count: usize,
    pub evppi_evaluation_count: Option<u64>,
    pub evsi_design_count: usize,
    pub evsi_evaluation_count: Option<u64>,
    pub evsi_target_parameter_id: String,
    pub result_sha256: Option<String>,
    pub replay_sha256: Option<String>,
    pub errors: Vec<String>,
}

#[derive(Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AdvancedVoiRunResult {
    pub audit: AdvancedVoiAudit,
    pub calculation: serde_json::Value,
    pub result_sha256: String,
    pub replay_sha256: String,
    pub review_status: &'static str,
}

#[derive(Default)]
pub struct AdvancedVoiReviewState(pub Mutex<()>);

#[derive(Clone, Copy, Debug, Eq, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum AdvancedVoiReviewAction {
    Accept,
    Reject,
}

#[derive(Clone, Debug, Eq, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct AdvancedVoiReviewChecklist {
    pub decision_scope_threshold_reviewed: bool,
    pub population_lifetime_implementation_reviewed: bool,
    pub represented_omitted_uncertainty_reviewed: bool,
    pub evppi_grouping_correlation_reviewed: bool,
    pub nested_monte_carlo_precision_bias_reviewed: bool,
    pub evsi_prior_likelihood_data_model_reviewed: bool,
    pub research_delay_cost_opportunity_cost_reviewed: bool,
    pub limitations_no_decision_authority_reviewed: bool,
}

impl AdvancedVoiReviewChecklist {
    fn all_confirmed(&self) -> bool {
        self.decision_scope_threshold_reviewed
            && self.population_lifetime_implementation_reviewed
            && self.represented_omitted_uncertainty_reviewed
            && self.evppi_grouping_correlation_reviewed
            && self.nested_monte_carlo_precision_bias_reviewed
            && self.evsi_prior_likelihood_data_model_reviewed
            && self.research_delay_cost_opportunity_cost_reviewed
            && self.limitations_no_decision_authority_reviewed
    }
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct AdvancedVoiReviewRequest {
    pub project_id: String,
    pub action: AdvancedVoiReviewAction,
    pub result_sha256: String,
    pub replay_sha256: String,
    pub checklist: AdvancedVoiReviewChecklist,
    pub actor_label: String,
    pub rationale: String,
}

#[derive(Clone, Debug, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct AdvancedVoiReviewEvent {
    pub schema_version: u32,
    pub sequence: u64,
    pub review_id: String,
    pub project_id: String,
    pub voi_id: String,
    pub action: AdvancedVoiReviewAction,
    pub plan_sha256: String,
    pub result_sha256: String,
    pub replay_sha256: String,
    pub checklist: AdvancedVoiReviewChecklist,
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
pub struct AdvancedVoiReviewLog {
    pub events: Vec<AdvancedVoiReviewEvent>,
    pub chain_head: Option<String>,
    pub integrity: &'static str,
    pub identity_assurance: &'static str,
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn finite(value: Option<&serde_json::Value>) -> Option<f64> {
    value
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite())
}

fn nonempty(value: Option<&serde_json::Value>) -> Option<&str> {
    value
        .and_then(serde_json::Value::as_str)
        .filter(|value| !value.trim().is_empty())
}

fn string_set(value: Option<&serde_json::Value>) -> Option<HashSet<&str>> {
    let values = value?.as_array()?;
    let mut result = HashSet::new();
    for value in values {
        let value = nonempty(Some(value))?;
        if !result.insert(value) {
            return None;
        }
    }
    Some(result)
}

fn exact_keys(value: &serde_json::Value, expected: &[&str]) -> bool {
    value.as_object().is_some_and(|object| {
        object.len() == expected.len() && expected.iter().all(|key| object.contains_key(*key))
    })
}

fn binding_matches(value: Option<&serde_json::Value>, path: &str, raw: &[u8]) -> bool {
    let expected_sha256 = sha256(raw);
    value.is_some_and(|value| {
        exact_keys(value, &["path", "content_sha256"])
            && value.get("path").and_then(serde_json::Value::as_str) == Some(path)
            && value
                .get("content_sha256")
                .and_then(serde_json::Value::as_str)
                == Some(expected_sha256.as_str())
    })
}

fn empty_audit(
    plan_raw: &[u8],
    analysis_raw: &[u8],
    uncertainty_raw: &[u8],
    uncertainty_result_raw: &[u8],
) -> AdvancedVoiAudit {
    AdvancedVoiAudit {
        complete: false,
        reviewable: false,
        status: "incomplete",
        voi_id: String::new(),
        analysis_id: String::new(),
        uncertainty_id: String::new(),
        advanced_voi_plan_sha256: sha256(plan_raw),
        analysis_plan_sha256: sha256(analysis_raw),
        uncertainty_plan_sha256: sha256(uncertainty_raw),
        uncertainty_result_sha256: sha256(uncertainty_result_raw),
        uncertainty_schema_version: String::new(),
        decision_threshold: None,
        population_year_count: 0,
        effective_population: None,
        evppi_group_count: 0,
        evppi_evaluation_count: None,
        evsi_design_count: 0,
        evsi_evaluation_count: None,
        evsi_target_parameter_id: String::new(),
        result_sha256: None,
        replay_sha256: None,
        errors: Vec::new(),
    }
}

fn effective_population(values: &[f64], rate: f64, delay: usize) -> f64 {
    values
        .iter()
        .enumerate()
        .filter(|(year, _)| *year >= delay)
        .map(|(year, value)| value / (1.0 + rate).powi(year as i32))
        .sum()
}

fn audit_values(
    plan_raw: &[u8],
    analysis_raw: &[u8],
    uncertainty_raw: &[u8],
    uncertainty_result_raw: &[u8],
) -> AdvancedVoiAudit {
    let mut audit = empty_audit(
        plan_raw,
        analysis_raw,
        uncertainty_raw,
        uncertainty_result_raw,
    );
    let plan = match serde_json::from_slice::<serde_json::Value>(plan_raw) {
        Ok(value) => value,
        Err(error) => {
            audit
                .errors
                .push(format!("advanced VOI plan is invalid JSON: {error}"));
            return audit;
        }
    };
    let analysis = match serde_json::from_slice::<serde_json::Value>(analysis_raw) {
        Ok(value) => value,
        Err(error) => {
            audit
                .errors
                .push(format!("analysis plan is invalid JSON: {error}"));
            return audit;
        }
    };
    let uncertainty = match serde_json::from_slice::<serde_json::Value>(uncertainty_raw) {
        Ok(value) => value,
        Err(error) => {
            audit
                .errors
                .push(format!("uncertainty plan is invalid JSON: {error}"));
            return audit;
        }
    };
    let uncertainty_result =
        match serde_json::from_slice::<serde_json::Value>(uncertainty_result_raw) {
            Ok(value) => value,
            Err(error) => {
                audit
                    .errors
                    .push(format!("uncertainty result is invalid JSON: {error}"));
                return audit;
            }
        };
    if !exact_keys(
        &plan,
        &[
            "schema_version",
            "voi_id",
            "analysis_id",
            "uncertainty_id",
            "status",
            "bindings",
            "decision_threshold",
            "population",
            "evppi",
            "evsi",
            "limitations",
        ],
    ) {
        audit
            .errors
            .push("advanced VOI plan fields are invalid".into());
    }
    if plan
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some("0.1.0")
    {
        audit
            .errors
            .push("advanced VOI schema_version must be 0.1.0".into());
    }
    if plan.get("status").and_then(serde_json::Value::as_str) != Some("ready_for_human_review") {
        audit
            .errors
            .push("advanced VOI plan must be ready_for_human_review".into());
    }
    audit.voi_id = nonempty(plan.get("voi_id")).unwrap_or_default().to_string();
    audit.analysis_id = nonempty(plan.get("analysis_id"))
        .unwrap_or_default()
        .to_string();
    audit.uncertainty_id = nonempty(plan.get("uncertainty_id"))
        .unwrap_or_default()
        .to_string();
    if audit.voi_id.is_empty() || audit.analysis_id.is_empty() || audit.uncertainty_id.is_empty() {
        audit
            .errors
            .push("advanced VOI ids must be non-empty".into());
    }
    if nonempty(analysis.get("analysis_id")) != Some(audit.analysis_id.as_str())
        || nonempty(uncertainty.get("uncertainty_id")) != Some(audit.uncertainty_id.as_str())
    {
        audit
            .errors
            .push("advanced VOI ids do not match current model artifacts".into());
    }
    let bindings = plan.get("bindings");
    if !bindings.is_some_and(|value| {
        exact_keys(
            value,
            &["analysis_plan", "uncertainty_plan", "uncertainty_result"],
        )
    }) {
        audit
            .errors
            .push("advanced VOI bindings are invalid".into());
    } else {
        for (field, path, raw) in [
            ("analysis_plan", ANALYSIS_PLAN_PATH, analysis_raw),
            ("uncertainty_plan", UNCERTAINTY_PLAN_PATH, uncertainty_raw),
            (
                "uncertainty_result",
                UNCERTAINTY_RESULT_PATH,
                uncertainty_result_raw,
            ),
        ] {
            if !binding_matches(bindings.and_then(|value| value.get(field)), path, raw) {
                audit
                    .errors
                    .push(format!("advanced VOI {field} binding is stale"));
            }
        }
    }
    audit.uncertainty_schema_version = nonempty(uncertainty.get("schema_version"))
        .unwrap_or_default()
        .to_string();
    if !matches!(
        audit.uncertainty_schema_version.as_str(),
        "0.9.0" | "0.13.0"
    ) {
        audit.errors.push(
            "advanced VOI supports odds-ratio uncertainty schema 0.9.0 or fixed-survival component schema 0.13.0"
                .into(),
        );
    }
    if uncertainty_result
        .pointer("/probabilistic_analysis/convergence/passed")
        .and_then(serde_json::Value::as_bool)
        != Some(true)
    {
        audit
            .errors
            .push("advanced VOI requires a converged uncertainty result".into());
    }
    if uncertainty_result
        .get("base_analysis_sha256")
        .and_then(serde_json::Value::as_str)
        != Some(audit.analysis_plan_sha256.as_str())
        || uncertainty_result
            .get("uncertainty_plan_sha256")
            .and_then(serde_json::Value::as_str)
            != Some(audit.uncertainty_plan_sha256.as_str())
    {
        audit
            .errors
            .push("uncertainty result bindings are stale".into());
    }
    audit.decision_threshold = finite(plan.get("decision_threshold"));
    if audit.decision_threshold.is_none()
        || audit.decision_threshold != finite(analysis.get("willingness_to_pay"))
    {
        audit
            .errors
            .push("advanced VOI threshold must equal the analysis primary threshold".into());
    }

    let population = plan.get("population");
    let annual = population
        .and_then(|value| value.get("annual_affected_population"))
        .and_then(serde_json::Value::as_array)
        .map(|values| {
            values
                .iter()
                .map(|value| finite(Some(value)))
                .collect::<Option<Vec<_>>>()
        });
    let rate = population
        .and_then(|value| finite(value.get("discount_rate")))
        .filter(|value| (0.0..=0.2).contains(value));
    match (annual, rate) {
        (Some(Some(values)), Some(rate))
            if (1..=30).contains(&values.len())
                && values.iter().all(|value| *value >= 0.0)
                && values.iter().any(|value| *value > 0.0) =>
        {
            audit.population_year_count = values.len();
            audit.effective_population = Some(effective_population(&values, rate, 0));
        }
        _ => audit
            .errors
            .push("advanced VOI population inputs are invalid".into()),
    }
    if population
        .and_then(|value| string_set(value.get("basis_ids")))
        .is_none_or(|basis| basis.is_empty())
        || population
            .and_then(|value| nonempty(value.get("rationale")))
            .is_none()
    {
        audit
            .errors
            .push("advanced VOI population basis and rationale are required".into());
    }

    let parameter_ids = uncertainty
        .get("parameters")
        .and_then(serde_json::Value::as_array)
        .map(|values| {
            values
                .iter()
                .filter_map(|value| nonempty(value.get("id")))
                .collect::<HashSet<_>>()
        })
        .unwrap_or_default();
    let correlation_groups = uncertainty
        .pointer("/probabilistic_analysis/correlation_handling/groups")
        .and_then(serde_json::Value::as_array)
        .map(|groups| {
            groups
                .iter()
                .filter_map(|group| string_set(group.get("parameter_ids")))
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    let evppi = plan.get("evppi");
    if evppi
        .and_then(|value| value.get("method"))
        .and_then(serde_json::Value::as_str)
        != Some("nested_monte_carlo")
    {
        audit
            .errors
            .push("EVPPI method must be nested_monte_carlo".into());
    }
    let outer = evppi
        .and_then(|value| value.get("outer_iterations"))
        .and_then(serde_json::Value::as_u64);
    let inner = evppi
        .and_then(|value| value.get("inner_iterations"))
        .and_then(serde_json::Value::as_u64);
    let mut group_members = HashMap::<String, Vec<String>>::new();
    if let Some(groups) = evppi
        .and_then(|value| value.get("parameter_groups"))
        .and_then(serde_json::Value::as_array)
    {
        audit.evppi_group_count = groups.len();
        if !(1..=8).contains(&groups.len()) {
            audit
                .errors
                .push("EVPPI requires 1 to 8 parameter groups".into());
        }
        for group in groups {
            let id = nonempty(group.get("id")).unwrap_or_default();
            let members = group
                .get("parameter_ids")
                .and_then(serde_json::Value::as_array)
                .map(|values| {
                    values
                        .iter()
                        .filter_map(|value| nonempty(Some(value)))
                        .map(str::to_string)
                        .collect::<Vec<_>>()
                })
                .unwrap_or_default();
            if id.is_empty()
                || group_members.contains_key(id)
                || !(1..=32).contains(&members.len())
                || members.iter().collect::<HashSet<_>>().len() != members.len()
                || members
                    .iter()
                    .any(|member| !parameter_ids.contains(member.as_str()))
                || group
                    .get("basis_ids")
                    .and_then(|value| string_set(Some(value)))
                    .is_none_or(|set| set.is_empty())
                || nonempty(group.get("rationale")).is_none()
            {
                audit.errors.push(format!("EVPPI group {id:?} is invalid"));
            }
            let selected = members.iter().map(String::as_str).collect::<HashSet<_>>();
            for correlation in &correlation_groups {
                if !selected.is_disjoint(correlation) && !correlation.is_subset(&selected) {
                    audit
                        .errors
                        .push(format!("EVPPI group {id:?} splits a correlation group"));
                }
            }
            group_members.insert(id.to_string(), members);
        }
    } else {
        audit
            .errors
            .push("EVPPI parameter groups are required".into());
    }
    match (outer, inner) {
        (Some(outer @ 100..=1_000), Some(inner @ 20..=500)) => {
            let evaluations = outer * inner * audit.evppi_group_count as u64;
            audit.evppi_evaluation_count = Some(evaluations);
            if evaluations > 100_000 {
                audit
                    .errors
                    .push("EVPPI exceeds 100000 model evaluations".into());
            }
        }
        _ => audit
            .errors
            .push("EVPPI iteration counts are invalid".into()),
    }

    let evsi = plan.get("evsi");
    if evsi
        .and_then(|value| value.get("method"))
        .and_then(serde_json::Value::as_str)
        != Some("normal_normal_nested_monte_carlo")
    {
        audit
            .errors
            .push("EVSI method must be normal_normal_nested_monte_carlo".into());
    }
    audit.evsi_target_parameter_id = evsi
        .and_then(|value| nonempty(value.get("target_parameter_id")))
        .unwrap_or_default()
        .to_string();
    let target_group = evsi
        .and_then(|value| nonempty(value.get("target_group_id")))
        .unwrap_or_default();
    if group_members
        .get(target_group)
        .is_none_or(|members| members.len() != 1 || members[0] != audit.evsi_target_parameter_id)
    {
        audit
            .errors
            .push("EVSI target group must contain exactly the target parameter".into());
    }
    let target = uncertainty
        .get("parameters")
        .and_then(serde_json::Value::as_array)
        .and_then(|parameters| {
            parameters.iter().find(|parameter| {
                nonempty(parameter.get("id")) == Some(audit.evsi_target_parameter_id.as_str())
            })
        });
    if target
        .and_then(|value| value.pointer("/probabilistic/type"))
        .and_then(serde_json::Value::as_str)
        != Some("lognormal")
        || target
            .and_then(|value| value.pointer("/probabilistic/sigma_log"))
            .and_then(serde_json::Value::as_f64)
            .is_none_or(|value| !value.is_finite() || value <= 0.0)
        || correlation_groups
            .iter()
            .any(|group| group.contains(audit.evsi_target_parameter_id.as_str()))
    {
        audit
            .errors
            .push("EVSI target must be an independent Lognormal parameter".into());
    }
    if evsi
        .and_then(|value| finite(value.get("sampling_standard_deviation")))
        .is_none_or(|value| value <= 0.0)
    {
        audit
            .errors
            .push("EVSI sampling standard deviation must be positive".into());
    }
    let sizes = evsi
        .and_then(|value| value.get("sample_sizes"))
        .and_then(serde_json::Value::as_array)
        .map(|values| {
            values
                .iter()
                .map(serde_json::Value::as_u64)
                .collect::<Option<Vec<_>>>()
        });
    if let Some(Some(sizes)) = sizes {
        audit.evsi_design_count = sizes.len();
        if !(1..=8).contains(&sizes.len())
            || sizes.iter().any(|size| !(2..=100_000).contains(size))
            || sizes.windows(2).any(|pair| pair[0] >= pair[1])
        {
            audit.errors.push("EVSI sample sizes are invalid".into());
        }
    } else {
        audit.errors.push("EVSI sample sizes are required".into());
    }
    let evsi_outer = evsi
        .and_then(|value| value.get("outer_iterations"))
        .and_then(serde_json::Value::as_u64);
    let evsi_inner = evsi
        .and_then(|value| value.get("inner_iterations"))
        .and_then(serde_json::Value::as_u64);
    match (evsi_outer, evsi_inner) {
        (Some(outer @ 100..=1_000), Some(inner @ 20..=500)) => {
            let evaluations = outer * inner * audit.evsi_design_count as u64;
            audit.evsi_evaluation_count = Some(evaluations);
            if evaluations > 100_000 {
                audit
                    .errors
                    .push("EVSI exceeds 100000 model evaluations".into());
            }
        }
        _ => audit
            .errors
            .push("EVSI iteration counts are invalid".into()),
    }
    let delay = evsi
        .and_then(|value| value.get("study_delay_years"))
        .and_then(serde_json::Value::as_u64);
    if delay.is_none_or(|delay| delay as usize >= audit.population_year_count) {
        audit
            .errors
            .push("EVSI study delay is outside the population horizon".into());
    }
    let study_cost = evsi.and_then(|value| value.get("study_cost"));
    let currency = study_cost.and_then(|value| nonempty(value.get("currency")));
    if study_cost
        .and_then(|value| finite(value.get("fixed")))
        .is_none_or(|value| value < 0.0)
        || study_cost
            .and_then(|value| finite(value.get("per_participant")))
            .is_none_or(|value| value < 0.0)
        || currency.is_none_or(|value| {
            value.len() != 3 || !value.bytes().all(|byte| byte.is_ascii_uppercase())
        })
        || study_cost
            .and_then(|value| value.get("price_year"))
            .and_then(serde_json::Value::as_u64)
            .is_none_or(|value| !(1900..=2200).contains(&value))
        || study_cost
            .and_then(|value| string_set(value.get("basis_ids")))
            .is_none_or(|value| value.is_empty())
        || study_cost
            .and_then(|value| nonempty(value.get("rationale")))
            .is_none()
    {
        audit.errors.push("EVSI study cost basis is invalid".into());
    }
    if evsi
        .and_then(|value| string_set(value.get("basis_ids")))
        .is_none_or(|set| set.is_empty())
        || evsi
            .and_then(|value| nonempty(value.get("rationale")))
            .is_none()
    {
        audit
            .errors
            .push("EVSI design basis and rationale are required".into());
    }
    let limitations = string_set(plan.get("limitations"));
    if limitations.is_none_or(|values| {
        REQUIRED_LIMITATIONS
            .iter()
            .any(|required| !values.contains(required))
    }) {
        audit
            .errors
            .push("advanced VOI limitations omit required boundaries".into());
    }
    audit.complete = audit.errors.is_empty();
    audit.status = if audit.complete {
        "complete"
    } else {
        "incomplete"
    };
    audit
}

pub fn audit_advanced_voi(workspace: &Path) -> Result<AdvancedVoiAudit, String> {
    let plan_raw =
        crate::heor_uncertainty::read_workspace_capped(workspace, ADVANCED_VOI_PLAN_PATH)?;
    let analysis_raw =
        crate::heor_uncertainty::read_workspace_capped(workspace, ANALYSIS_PLAN_PATH)?;
    let uncertainty_raw =
        crate::heor_uncertainty::read_workspace_capped(workspace, UNCERTAINTY_PLAN_PATH)?;
    let uncertainty_result_raw =
        crate::heor_uncertainty::read_workspace_capped(workspace, UNCERTAINTY_RESULT_PATH)?;
    let mut audit = audit_values(
        &plan_raw,
        &analysis_raw,
        &uncertainty_raw,
        &uncertainty_result_raw,
    );
    if audit.complete {
        if let Ok((result_sha256, replay_sha256)) = verify_current_result(workspace, &audit) {
            audit.reviewable = true;
            audit.result_sha256 = Some(result_sha256);
            audit.replay_sha256 = Some(replay_sha256);
        }
    }
    Ok(audit)
}

#[tauri::command(async)]
pub fn audit_heor_advanced_voi(app: AppHandle) -> Result<AdvancedVoiAudit, String> {
    audit_advanced_voi(&crate::runtime::workspace_dir(&app)?)
}

fn model_input_hashes(
    workspace: &Path,
    uncertainty_schema_version: &str,
) -> Result<HashMap<String, String>, String> {
    let mut hashes = HashMap::from([
        (
            "analysis_plan".to_string(),
            sha256(&crate::heor_uncertainty::read_workspace_capped(
                workspace,
                ANALYSIS_PLAN_PATH,
            )?),
        ),
        (
            "uncertainty_plan".to_string(),
            sha256(&crate::heor_uncertainty::read_workspace_capped(
                workspace,
                UNCERTAINTY_PLAN_PATH,
            )?),
        ),
    ]);
    if uncertainty_schema_version == "0.13.0" {
        for (name, path) in [
            (
                "partitioned_survival_plan",
                crate::heor_partitioned_survival::PARTITIONED_SURVIVAL_PLAN_PATH,
            ),
            (
                "curve_materializations",
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
        ] {
            hashes.insert(
                name.to_string(),
                sha256(&crate::heor_uncertainty::read_workspace_capped(
                    workspace, path,
                )?),
            );
        }
    }
    Ok(hashes)
}

fn mean_mcse(values: &[f64]) -> Result<(f64, f64), String> {
    if values.len() < 2 || values.iter().any(|value| !value.is_finite()) {
        return Err("advanced VOI replay has invalid outer values".into());
    }
    let mean = values.iter().sum::<f64>() / values.len() as f64;
    let variance = values
        .iter()
        .map(|value| (value - mean).powi(2))
        .sum::<f64>()
        / (values.len() - 1) as f64;
    Ok((mean, (variance / values.len() as f64).sqrt()))
}

fn summarize_rows(rows: &serde_json::Value, strategy_order: &[&str]) -> Result<(f64, f64), String> {
    let rows = rows
        .as_array()
        .filter(|rows| rows.len() >= 2)
        .ok_or("advanced VOI replay rows are invalid")?;
    let mut expected = vec![0.0; strategy_order.len()];
    for row in rows {
        let values = row
            .get("expected_nmb_by_strategy")
            .and_then(serde_json::Value::as_object)
            .ok_or("advanced VOI replay row omitted expected NMB")?;
        if values.len() != strategy_order.len() {
            return Err("advanced VOI replay row strategy set differs".into());
        }
        for (index, strategy) in strategy_order.iter().enumerate() {
            expected[index] +=
                finite(values.get(*strategy)).ok_or("advanced VOI replay NMB is invalid")?;
        }
    }
    for value in &mut expected {
        *value /= rows.len() as f64;
    }
    let current = expected
        .iter()
        .enumerate()
        .max_by(|left, right| left.1.total_cmp(right.1))
        .map(|(index, _)| index)
        .ok_or("advanced VOI replay has no strategies")?;
    let mut gains = Vec::with_capacity(rows.len());
    for row in rows {
        let values = row
            .get("expected_nmb_by_strategy")
            .and_then(serde_json::Value::as_object)
            .ok_or("advanced VOI replay row omitted expected NMB")?;
        let current_value = finite(values.get(strategy_order[current]))
            .ok_or("advanced VOI replay current NMB is invalid")?;
        let mut best = f64::NEG_INFINITY;
        for strategy in strategy_order {
            best = best.max(
                finite(values.get(*strategy))
                    .ok_or("advanced VOI replay strategy NMB is invalid")?,
            );
        }
        gains.push(best - current_value);
    }
    mean_mcse(&gains)
}

fn close(actual: f64, expected: f64) -> bool {
    actual.is_finite()
        && expected.is_finite()
        && (actual - expected).abs() <= 1e-9 * expected.abs().max(1.0)
}

fn require_close(
    value: Option<&serde_json::Value>,
    expected: f64,
    label: &str,
) -> Result<(), String> {
    if finite(value).is_some_and(|actual| close(actual, expected)) {
        Ok(())
    } else {
        Err(format!("advanced VOI {label} differs from native replay"))
    }
}

fn verify_output(
    plan: &serde_json::Value,
    uncertainty_result: &serde_json::Value,
    result: &serde_json::Value,
    replay: &serde_json::Value,
    replay_raw: &[u8],
    audit: &AdvancedVoiAudit,
    expected_model_input_hashes: &HashMap<String, String>,
) -> Result<(), String> {
    if result
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some("0.1.0")
        || result
            .get("engine_version")
            .and_then(serde_json::Value::as_str)
            != Some("0.1.0")
        || result.get("voi_id").and_then(serde_json::Value::as_str) != Some(audit.voi_id.as_str())
        || result
            .get("analysis_id")
            .and_then(serde_json::Value::as_str)
            != Some(audit.analysis_id.as_str())
        || result
            .get("uncertainty_id")
            .and_then(serde_json::Value::as_str)
            != Some(audit.uncertainty_id.as_str())
        || result
            .get("advanced_voi_plan_sha256")
            .and_then(serde_json::Value::as_str)
            != Some(audit.advanced_voi_plan_sha256.as_str())
        || result
            .get("uncertainty_result_sha256")
            .and_then(serde_json::Value::as_str)
            != Some(audit.uncertainty_result_sha256.as_str())
        || result
            .get("replay_sha256")
            .and_then(serde_json::Value::as_str)
            != Some(sha256(replay_raw).as_str())
    {
        return Err("advanced VOI result identity or hashes differ".into());
    }
    if replay
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some("0.1.0")
        || replay.get("voi_id").and_then(serde_json::Value::as_str) != Some(audit.voi_id.as_str())
        || replay
            .get("advanced_voi_plan_sha256")
            .and_then(serde_json::Value::as_str)
            != Some(audit.advanced_voi_plan_sha256.as_str())
    {
        return Err("advanced VOI replay identity differs".into());
    }
    let replay_hashes = replay
        .get("model_input_hashes")
        .and_then(serde_json::Value::as_object)
        .ok_or("advanced VOI replay omitted model input hashes")?;
    if replay_hashes.len() != expected_model_input_hashes.len()
        || expected_model_input_hashes.iter().any(|(name, expected)| {
            replay_hashes.get(name).and_then(serde_json::Value::as_str) != Some(expected.as_str())
        })
    {
        return Err("advanced VOI replay model input hashes differ".into());
    }
    if finite(replay.get("decision_threshold")) != audit.decision_threshold {
        return Err("advanced VOI replay decision threshold differs".into());
    }
    for (section, method) in [
        ("evppi", "nested_monte_carlo"),
        ("evsi", "normal_normal_nested_monte_carlo"),
    ] {
        let replay_section = replay
            .get(section)
            .ok_or_else(|| format!("advanced VOI replay omitted {section}"))?;
        let plan_section = plan
            .get(section)
            .ok_or_else(|| format!("advanced VOI plan omitted {section}"))?;
        if replay_section
            .get("method")
            .and_then(serde_json::Value::as_str)
            != Some(method)
            || replay_section
                .get("seed")
                .and_then(serde_json::Value::as_u64)
                != plan_section.get("seed").and_then(serde_json::Value::as_u64)
            || replay_section
                .get("outer_iterations")
                .and_then(serde_json::Value::as_u64)
                != plan_section
                    .get("outer_iterations")
                    .and_then(serde_json::Value::as_u64)
            || replay_section
                .get("inner_iterations")
                .and_then(serde_json::Value::as_u64)
                != plan_section
                    .get("inner_iterations")
                    .and_then(serde_json::Value::as_u64)
        {
            return Err(format!("advanced VOI replay {section} algorithm differs"));
        }
    }
    if replay
        .pointer("/evsi/target_parameter_id")
        .and_then(serde_json::Value::as_str)
        != Some(audit.evsi_target_parameter_id.as_str())
        || finite(replay.pointer("/evsi/sampling_standard_deviation"))
            != finite(plan.pointer("/evsi/sampling_standard_deviation"))
    {
        return Err("advanced VOI replay EVSI target or likelihood differs".into());
    }
    let strategy_order = replay
        .get("strategy_order")
        .and_then(serde_json::Value::as_array)
        .ok_or("advanced VOI replay omitted strategy_order")?
        .iter()
        .map(|value| nonempty(Some(value)).ok_or("advanced VOI replay strategy is invalid"))
        .collect::<Result<Vec<_>, _>>()?;
    if strategy_order.len() < 2
        || strategy_order.iter().collect::<HashSet<_>>().len() != strategy_order.len()
        || result
            .get("strategy_order")
            .and_then(serde_json::Value::as_array)
            .is_none_or(|values| {
                values.len() != strategy_order.len()
                    || values
                        .iter()
                        .zip(&strategy_order)
                        .any(|(value, expected)| value.as_str() != Some(*expected))
            })
    {
        return Err("advanced VOI replay strategy_order is invalid".into());
    }
    let annual = plan
        .pointer("/population/annual_affected_population")
        .and_then(serde_json::Value::as_array)
        .ok_or("advanced VOI plan population changed before replay verification")?
        .iter()
        .map(|value| finite(Some(value)).ok_or("advanced VOI annual population is invalid"))
        .collect::<Result<Vec<_>, _>>()?;
    let rate = finite(plan.pointer("/population/discount_rate"))
        .ok_or("advanced VOI population discount rate is invalid")?;
    let effective = effective_population(&annual, rate, 0);
    require_close(
        result.pointer("/population/effective_population"),
        effective,
        "effective_population",
    )?;
    let threshold = audit
        .decision_threshold
        .ok_or("advanced VOI decision threshold is unavailable")?;
    let primary = uncertainty_result
        .pointer("/probabilistic_analysis/decision_uncertainty/threshold_results")
        .and_then(serde_json::Value::as_array)
        .and_then(|rows| {
            rows.iter()
                .find(|row| finite(row.get("threshold")) == Some(threshold))
        })
        .ok_or("uncertainty result omitted primary EVPI")?;
    let per_person_evpi =
        finite(primary.get("per_person_evpi")).ok_or("uncertainty EVPI is invalid")?;
    let per_person_evpi_mcse =
        finite(primary.get("per_person_evpi_mcse")).ok_or("uncertainty EVPI MCSE is invalid")?;
    require_close(
        result.pointer("/population_evpi/per_person_evpi"),
        per_person_evpi,
        "per_person_evpi",
    )?;
    require_close(
        result.pointer("/population_evpi/per_person_evpi_mcse"),
        per_person_evpi_mcse,
        "per_person_evpi_mcse",
    )?;
    require_close(
        result.pointer("/population_evpi/population_evpi"),
        per_person_evpi * effective,
        "population_evpi",
    )?;
    require_close(
        result.pointer("/population_evpi/population_evpi_mcse"),
        per_person_evpi_mcse * effective,
        "population_evpi_mcse",
    )?;

    let result_groups = result
        .get("evppi")
        .and_then(serde_json::Value::as_array)
        .ok_or("advanced VOI result omitted EVPPI")?;
    let replay_groups = replay
        .pointer("/evppi/groups")
        .and_then(serde_json::Value::as_array)
        .ok_or("advanced VOI replay omitted EVPPI")?;
    if result_groups.len() != replay_groups.len() {
        return Err("advanced VOI EVPPI result/replay count differs".into());
    }
    for replay_group in replay_groups {
        let id =
            nonempty(replay_group.get("group_id")).ok_or("EVPPI replay group id is invalid")?;
        let actual = result_groups
            .iter()
            .find(|value| nonempty(value.get("group_id")) == Some(id))
            .ok_or("advanced VOI result omitted an EVPPI group")?;
        let (value, mcse) = summarize_rows(
            replay_group
                .get("rows")
                .ok_or("EVPPI replay omitted rows")?,
            &strategy_order,
        )?;
        require_close(actual.get("per_person_evppi"), value, "per_person_evppi")?;
        require_close(
            actual.get("per_person_evppi_mcse"),
            mcse,
            "per_person_evppi_mcse",
        )?;
        require_close(
            actual.get("population_evppi"),
            value * effective,
            "population_evppi",
        )?;
    }

    let delay = plan
        .pointer("/evsi/study_delay_years")
        .and_then(serde_json::Value::as_u64)
        .ok_or("advanced VOI study delay is invalid")? as usize;
    let research_population = effective_population(&annual, rate, delay);
    let fixed = finite(plan.pointer("/evsi/study_cost/fixed"))
        .ok_or("advanced VOI fixed study cost is invalid")?;
    let per_participant = finite(plan.pointer("/evsi/study_cost/per_participant"))
        .ok_or("advanced VOI per-participant study cost is invalid")?;
    let result_designs = result
        .pointer("/evsi/designs")
        .and_then(serde_json::Value::as_array)
        .ok_or("advanced VOI result omitted EVSI designs")?;
    let replay_designs = replay
        .pointer("/evsi/designs")
        .and_then(serde_json::Value::as_array)
        .ok_or("advanced VOI replay omitted EVSI designs")?;
    if result_designs.len() != replay_designs.len() {
        return Err("advanced VOI EVSI result/replay count differs".into());
    }
    for replay_design in replay_designs {
        let sample_size = replay_design
            .get("sample_size")
            .and_then(serde_json::Value::as_u64)
            .ok_or("EVSI replay sample size is invalid")?;
        let actual = result_designs
            .iter()
            .find(|value| {
                value.get("sample_size").and_then(serde_json::Value::as_u64) == Some(sample_size)
            })
            .ok_or("advanced VOI result omitted an EVSI design")?;
        let (value, mcse) = summarize_rows(
            replay_design
                .get("rows")
                .ok_or("EVSI replay omitted rows")?,
            &strategy_order,
        )?;
        let population_evsi = value * research_population;
        let study_cost = fixed + per_participant * sample_size as f64;
        require_close(actual.get("per_person_evsi"), value, "per_person_evsi")?;
        require_close(
            actual.get("per_person_evsi_mcse"),
            mcse,
            "per_person_evsi_mcse",
        )?;
        require_close(
            actual.get("research_effective_population"),
            research_population,
            "research_effective_population",
        )?;
        require_close(
            actual.get("population_evsi"),
            population_evsi,
            "population_evsi",
        )?;
        require_close(actual.get("study_cost"), study_cost, "study_cost")?;
        require_close(
            actual.get("expected_net_benefit_of_sampling"),
            population_evsi - study_cost,
            "expected_net_benefit_of_sampling",
        )?;
    }
    Ok(())
}

fn capped_stderr(bytes: &[u8]) -> String {
    String::from_utf8_lossy(&bytes[..bytes.len().min(4_000)])
        .trim()
        .to_string()
}

#[tauri::command(async)]
pub fn run_heor_advanced_voi(
    app: AppHandle,
    project_id: String,
) -> Result<AdvancedVoiRunResult, String> {
    let workspace = crate::runtime::workspace_dir(&app)?;
    if crate::project::require_project_id(&workspace)? != project_id {
        return Err("HEOR projectId does not match the current project".into());
    }
    let audit = audit_advanced_voi(&workspace)?;
    if !audit.complete {
        return Err(format!(
            "advanced VOI audit is incomplete: {} errors",
            audit.errors.len()
        ));
    }
    let analysis_raw =
        crate::heor_uncertainty::read_workspace_capped(&workspace, ANALYSIS_PLAN_PATH)?;
    crate::heor_uncertainty::require_uncertainty_plan_approvable(&workspace, &analysis_raw)?;
    let plan = serde_json::from_slice::<serde_json::Value>(
        &crate::heor_uncertainty::read_workspace_capped(&workspace, ADVANCED_VOI_PLAN_PATH)?,
    )
    .map_err(|error| format!("advanced VOI plan is invalid: {error}"))?;
    let uncertainty_result_raw =
        crate::heor_uncertainty::read_workspace_capped(&workspace, UNCERTAINTY_RESULT_PATH)?;
    let uncertainty_result = serde_json::from_slice::<serde_json::Value>(&uncertainty_result_raw)
        .map_err(|error| format!("uncertainty result is invalid: {error}"))?;
    let model_input_hashes = model_input_hashes(&workspace, &audit.uncertainty_schema_version)?;
    let package_src = app
        .path()
        .resolve("heor-core/src", BaseDirectory::Resource)
        .map_err(|error| format!("bundled HEOR engine unavailable: {error}"))?;
    if !package_src.join("heor_core/advanced_voi.py").is_file() {
        return Err("bundled advanced VOI engine is missing".into());
    }
    let (python, _) = crate::kernel::python_bin(&app)?;
    let mut command = crate::runtime::quiet_command(python);
    command
        .args(["-m", "heor_core"])
        .arg(workspace.join(ANALYSIS_PLAN_PATH))
        .arg("--uncertainty-plan")
        .arg(workspace.join(UNCERTAINTY_PLAN_PATH))
        .arg("--advanced-voi-plan")
        .arg(workspace.join(ADVANCED_VOI_PLAN_PATH))
        .arg("--uncertainty-result")
        .arg(workspace.join(UNCERTAINTY_RESULT_PATH));
    if audit.uncertainty_schema_version == "0.13.0" {
        for (flag, path) in [
            (
                "--partitioned-survival-plan",
                crate::heor_partitioned_survival::PARTITIONED_SURVIVAL_PLAN_PATH,
            ),
            (
                "--survival-curve-materializations",
                crate::heor_survival_materialization::SURVIVAL_MATERIALIZATION_PATH,
            ),
            (
                "--treatment-effect-duration",
                crate::heor_treatment_effect_duration::TREATMENT_EFFECT_DURATION_PATH,
            ),
            (
                "--cost-input-normalization",
                crate::heor_cost_input_normalization::COST_INPUT_NORMALIZATION_PATH,
            ),
            (
                "--utility-inputs",
                crate::heor_utility_inputs::UTILITY_INPUTS_PATH,
            ),
            (
                "--event-disutilities",
                crate::heor_event_disutilities::EVENT_DISUTILITIES_PATH,
            ),
        ] {
            command.arg(flag).arg(workspace.join(path));
        }
    }
    let output = command
        .current_dir(&workspace)
        .env("PYTHONPATH", package_src)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("PYTHONNOUSERSITE", "1")
        .output()
        .map_err(|error| format!("advanced VOI engine failed to start: {error}"))?;
    if !output.status.success() {
        let message = capped_stderr(&output.stderr);
        return Err(if message.is_empty() {
            format!("advanced VOI engine exited with {}", output.status)
        } else {
            message
        });
    }
    if output.stdout.len() > OUTPUT_CAP_BYTES {
        return Err("advanced VOI engine output exceeds 25 MB".into());
    }
    let wrapper = serde_json::from_slice::<serde_json::Value>(&output.stdout)
        .map_err(|error| format!("advanced VOI engine returned invalid JSON: {error}"))?;
    let replay_raw = wrapper
        .get("replay_json")
        .and_then(serde_json::Value::as_str)
        .ok_or("advanced VOI engine omitted replay_json")?
        .as_bytes()
        .to_vec();
    if replay_raw.len() > OUTPUT_CAP_BYTES {
        return Err("advanced VOI replay exceeds 25 MB".into());
    }
    let replay = serde_json::from_slice::<serde_json::Value>(&replay_raw)
        .map_err(|error| format!("advanced VOI replay is invalid: {error}"))?;
    let calculation = wrapper
        .get("result")
        .cloned()
        .ok_or("advanced VOI engine omitted result")?;
    verify_output(
        &plan,
        &uncertainty_result,
        &calculation,
        &replay,
        &replay_raw,
        &audit,
        &model_input_hashes,
    )?;
    let result_raw = serde_json::to_vec_pretty(&calculation)
        .map_err(|error| format!("advanced VOI result serialization failed: {error}"))?;
    crate::heor_reporting::write_result(&workspace, ADVANCED_VOI_REPLAY_PATH, &replay_raw)?;
    crate::heor_reporting::write_result(&workspace, ADVANCED_VOI_RESULT_PATH, &result_raw)?;
    Ok(AdvancedVoiRunResult {
        audit,
        calculation,
        result_sha256: sha256(&result_raw),
        replay_sha256: sha256(&replay_raw),
        review_status: "awaiting_human_review",
    })
}

fn safe_identifier(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 80
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
}

fn valid_review_text(value: &str, maximum: usize) -> bool {
    value == value.trim() && !value.is_empty() && value.chars().count() <= maximum
}

fn is_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn review_root(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app
        .path()
        .app_data_dir()
        .map_err(|error| error.to_string())?
        .join("heor")
        .join("advanced-voi-reviews"))
}

fn review_log_path(root: &Path, project_id: &str) -> Result<PathBuf, String> {
    if !safe_identifier(project_id) {
        return Err("projectId must be a safe identifier".into());
    }
    Ok(root.join(format!("{project_id}.jsonl")))
}

fn event_hash(event: &AdvancedVoiReviewEvent) -> Result<String, String> {
    let mut payload = event.clone();
    payload.event_hash.clear();
    serde_json::to_vec(&payload)
        .map(|raw| sha256(&raw))
        .map_err(|error| error.to_string())
}

fn review_snapshot(event: &AdvancedVoiReviewEvent) -> Result<Vec<u8>, String> {
    let value = serde_json::json!({
        "schema_version": "0.1.0",
        "review_id": event.review_id,
        "project_id": event.project_id,
        "voi_id": event.voi_id,
        "action": event.action,
        "status": if event.action == AdvancedVoiReviewAction::Accept {
            "accepted_for_research_prioritization_use"
        } else {
            "rejected_for_research_prioritization_use"
        },
        "plan_sha256": event.plan_sha256,
        "result_sha256": event.result_sha256,
        "replay_sha256": event.replay_sha256,
        "checklist": event.checklist,
        "actor_label": event.actor_label,
        "rationale": event.rationale,
        "timestamp": event.timestamp,
        "assurance": REVIEW_ASSURANCE,
        "decision_authority": "human_researcher",
    });
    let mut raw = serde_json::to_vec_pretty(&value).map_err(|error| error.to_string())?;
    raw.push(b'\n');
    Ok(raw)
}

fn verify_current_result(
    workspace: &Path,
    audit: &AdvancedVoiAudit,
) -> Result<(String, String), String> {
    if !audit.complete {
        return Err("advanced VOI plan is not reviewable".into());
    }
    let plan_raw =
        crate::heor_uncertainty::read_workspace_capped(workspace, ADVANCED_VOI_PLAN_PATH)?;
    if sha256(&plan_raw) != audit.advanced_voi_plan_sha256 {
        return Err("advanced VOI plan changed during review".into());
    }
    let plan = serde_json::from_slice::<serde_json::Value>(&plan_raw)
        .map_err(|error| format!("advanced VOI plan is invalid: {error}"))?;
    let uncertainty_result_raw =
        crate::heor_uncertainty::read_workspace_capped(workspace, UNCERTAINTY_RESULT_PATH)?;
    let uncertainty_result = serde_json::from_slice::<serde_json::Value>(&uncertainty_result_raw)
        .map_err(|error| format!("uncertainty result is invalid: {error}"))?;
    let result_raw =
        crate::heor_uncertainty::read_workspace_capped(workspace, ADVANCED_VOI_RESULT_PATH)?;
    let replay_raw =
        crate::heor_uncertainty::read_workspace_capped(workspace, ADVANCED_VOI_REPLAY_PATH)?;
    let result = serde_json::from_slice::<serde_json::Value>(&result_raw)
        .map_err(|error| format!("advanced VOI result is invalid: {error}"))?;
    let replay = serde_json::from_slice::<serde_json::Value>(&replay_raw)
        .map_err(|error| format!("advanced VOI replay is invalid: {error}"))?;
    verify_output(
        &plan,
        &uncertainty_result,
        &result,
        &replay,
        &replay_raw,
        audit,
        &model_input_hashes(workspace, &audit.uncertainty_schema_version)?,
    )?;
    Ok((sha256(&result_raw), sha256(&replay_raw)))
}

fn read_review_events(
    root: &Path,
    workspace: &Path,
    project_id: &str,
) -> Result<Vec<AdvancedVoiReviewEvent>, String> {
    let raw = match std::fs::read(review_log_path(root, project_id)?) {
        Ok(raw) => raw,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(format!("advanced VOI review log unavailable: {error}")),
    };
    if raw.len() > 4 * 1024 * 1024 {
        return Err("advanced VOI review log exceeds 4 MB".into());
    }
    let mut events = Vec::new();
    let mut previous_hash = None;
    for (index, line) in raw
        .split(|byte| *byte == b'\n')
        .filter(|line| !line.is_empty())
        .enumerate()
    {
        if events.len() >= 2_000 {
            return Err("advanced VOI review log exceeds 2,000 events".into());
        }
        let event: AdvancedVoiReviewEvent = serde_json::from_slice(line).map_err(|error| {
            format!("advanced VOI review line {} is invalid: {error}", index + 1)
        })?;
        if event.schema_version != REVIEW_EVENT_SCHEMA
            || event.sequence != index as u64 + 1
            || event.project_id != project_id
            || !safe_identifier(&event.voi_id)
            || event.review_id.len() != 32
            || !event.review_id.bytes().all(|byte| byte.is_ascii_hexdigit())
            || !is_sha256(&event.plan_sha256)
            || !is_sha256(&event.result_sha256)
            || !is_sha256(&event.replay_sha256)
            || !is_sha256(&event.record_sha256)
            || !is_sha256(&event.event_hash)
            || event.assurance != REVIEW_ASSURANCE
            || event.previous_hash != previous_hash
            || !valid_review_text(&event.actor_label, 120)
            || !valid_review_text(&event.rationale, 2_000)
            || event_hash(&event)? != event.event_hash
        {
            return Err(format!(
                "advanced VOI review line {} violates the event contract",
                index + 1
            ));
        }
        let relative = Path::new(&event.record_path);
        if relative.is_absolute()
            || relative
                .components()
                .any(|component| !matches!(component, Component::Normal(_)))
            || !event.record_path.starts_with("heor/advanced-voi-reviews/")
        {
            return Err("advanced VOI review record path is unsafe".into());
        }
        let record = crate::heor_uncertainty::read_workspace_capped(workspace, &event.record_path)?;
        if sha256(&record) != event.record_sha256 || record != review_snapshot(&event)? {
            return Err(format!(
                "advanced VOI review line {} record binding is invalid",
                index + 1
            ));
        }
        previous_hash = Some(event.event_hash.clone());
        events.push(event);
    }
    Ok(events)
}

fn write_review_record(workspace: &Path, event: &AdvancedVoiReviewEvent) -> Result<(), String> {
    let root = workspace
        .canonicalize()
        .map_err(|error| error.to_string())?;
    let target = root.join(&event.record_path);
    let parent = target
        .parent()
        .ok_or("advanced VOI review record parent is invalid")?;
    std::fs::create_dir_all(parent)
        .map_err(|error| format!("advanced VOI review directory failed: {error}"))?;
    if std::fs::symlink_metadata(parent).is_ok_and(|metadata| metadata.file_type().is_symlink()) {
        return Err("advanced VOI review directory must not be a symlink".into());
    }
    let raw = review_snapshot(event)?;
    if sha256(&raw) != event.record_sha256 {
        return Err("advanced VOI review record hash changed before write".into());
    }
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&target)
        .map_err(|error| format!("advanced VOI review record write failed: {error}"))?;
    file.write_all(&raw)
        .and_then(|_| file.sync_all())
        .map_err(|error| format!("advanced VOI review record write failed: {error}"))
}

fn append_review_event(root: &Path, event: &AdvancedVoiReviewEvent) -> Result<(), String> {
    let path = review_log_path(root, &event.project_id)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("advanced VOI review log directory failed: {error}"))?;
        crate::runtime::tighten_private(parent);
    }
    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|error| format!("advanced VOI review log open failed: {error}"))?;
    crate::runtime::tighten_private(&path);
    let line = serde_json::to_string(event).map_err(|error| error.to_string())?;
    writeln!(file, "{line}")
        .and_then(|_| file.sync_all())
        .map_err(|error| format!("advanced VOI review log append failed: {error}"))
}

#[tauri::command(async)]
pub fn append_heor_advanced_voi_review(
    app: AppHandle,
    state: tauri::State<AdvancedVoiReviewState>,
    request: AdvancedVoiReviewRequest,
) -> Result<AdvancedVoiReviewEvent, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "advanced VOI review lock poisoned")?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    if crate::project::require_project_id(&workspace)? != request.project_id {
        return Err("review projectId does not match the current project".into());
    }
    if !valid_review_text(&request.actor_label, 120)
        || !valid_review_text(&request.rationale, 2_000)
        || !is_sha256(&request.result_sha256)
        || !is_sha256(&request.replay_sha256)
    {
        return Err("review actor, rationale, or artifact hash is invalid".into());
    }
    if request.action == AdvancedVoiReviewAction::Accept && !request.checklist.all_confirmed() {
        return Err("acceptance requires all eight Human method checks".into());
    }
    let audit = audit_advanced_voi(&workspace)?;
    let (result_sha256, replay_sha256) = verify_current_result(&workspace, &audit)?;
    if request.result_sha256 != result_sha256 || request.replay_sha256 != replay_sha256 {
        return Err("review must target the exact current advanced VOI result and replay".into());
    }
    let root = review_root(&app)?;
    let events = read_review_events(&root, &workspace, &request.project_id)?;
    if events.last().is_some_and(|event| {
        event.voi_id == audit.voi_id
            && event.result_sha256 == result_sha256
            && event.replay_sha256 == replay_sha256
            && event.action == request.action
    }) {
        return Err("the latest advanced VOI review already records this action".into());
    }
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| error.to_string())?
        .as_secs();
    let review_id = crate::runtime::random_hex(16);
    let record_path = format!(
        "heor/advanced-voi-reviews/{}-{review_id}.json",
        audit.voi_id
    );
    let mut event = AdvancedVoiReviewEvent {
        schema_version: REVIEW_EVENT_SCHEMA,
        sequence: events.len() as u64 + 1,
        review_id,
        project_id: request.project_id,
        voi_id: audit.voi_id,
        action: request.action,
        plan_sha256: audit.advanced_voi_plan_sha256,
        result_sha256,
        replay_sha256,
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
    event.record_sha256 = sha256(&review_snapshot(&event)?);
    event.event_hash = event_hash(&event)?;
    write_review_record(&workspace, &event)?;
    if let Err(error) = append_review_event(&root, &event) {
        let _ = std::fs::remove_file(workspace.join(&event.record_path));
        return Err(error);
    }
    crate::git_snapshot::commit_best_effort(&workspace, "Record advanced VOI Human review");
    Ok(event)
}

#[tauri::command(async)]
pub fn list_heor_advanced_voi_reviews(
    app: AppHandle,
    state: tauri::State<AdvancedVoiReviewState>,
    project_id: String,
) -> Result<AdvancedVoiReviewLog, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "advanced VOI review lock poisoned")?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    if crate::project::require_project_id(&workspace)? != project_id {
        return Err("review projectId does not match the current project".into());
    }
    let events = read_review_events(&review_root(&app)?, &workspace, &project_id)?;
    Ok(AdvancedVoiReviewLog {
        chain_head: events.last().map(|event| event.event_hash.clone()),
        events,
        integrity: "verified_unanchored_sha256_chain",
        identity_assurance: REVIEW_ASSURANCE,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn native_summary_uses_expected_nmb_then_opportunity_gain() {
        let rows = serde_json::json!([
            {"expected_nmb_by_strategy": {"a": 10.0, "b": 0.0}},
            {"expected_nmb_by_strategy": {"a": 0.0, "b": 8.0}},
            {"expected_nmb_by_strategy": {"a": 9.0, "b": 1.0}}
        ]);
        let (value, mcse) = summarize_rows(&rows, &["a", "b"]).unwrap();
        assert!(close(value, 8.0 / 3.0));
        assert!(mcse > 0.0);
    }

    #[test]
    fn population_discounting_honors_delay() {
        let annual = [100.0, 100.0, 100.0];
        assert!(close(effective_population(&annual, 0.0, 0), 300.0));
        assert!(close(effective_population(&annual, 0.0, 1), 200.0));
        assert!(effective_population(&annual, 0.03, 0) < 300.0);
    }

    #[test]
    fn acceptance_requires_every_human_method_check() {
        let mut checklist = AdvancedVoiReviewChecklist {
            decision_scope_threshold_reviewed: true,
            population_lifetime_implementation_reviewed: true,
            represented_omitted_uncertainty_reviewed: true,
            evppi_grouping_correlation_reviewed: true,
            nested_monte_carlo_precision_bias_reviewed: true,
            evsi_prior_likelihood_data_model_reviewed: true,
            research_delay_cost_opportunity_cost_reviewed: true,
            limitations_no_decision_authority_reviewed: true,
        };
        assert!(checklist.all_confirmed());
        checklist.limitations_no_decision_authority_reviewed = false;
        assert!(!checklist.all_confirmed());
    }

    #[test]
    fn review_event_hash_binds_checklist_and_previous_hash() {
        let checklist = AdvancedVoiReviewChecklist {
            decision_scope_threshold_reviewed: true,
            population_lifetime_implementation_reviewed: true,
            represented_omitted_uncertainty_reviewed: true,
            evppi_grouping_correlation_reviewed: true,
            nested_monte_carlo_precision_bias_reviewed: true,
            evsi_prior_likelihood_data_model_reviewed: true,
            research_delay_cost_opportunity_cost_reviewed: true,
            limitations_no_decision_authority_reviewed: true,
        };
        let mut event = AdvancedVoiReviewEvent {
            schema_version: REVIEW_EVENT_SCHEMA,
            sequence: 1,
            review_id: "1".repeat(32),
            project_id: "project-1".into(),
            voi_id: "voi-1".into(),
            action: AdvancedVoiReviewAction::Accept,
            plan_sha256: "a".repeat(64),
            result_sha256: "b".repeat(64),
            replay_sha256: "c".repeat(64),
            checklist,
            actor_label: "Researcher".into(),
            rationale: "Reviewed for research prioritization only.".into(),
            timestamp: 1,
            record_path: "heor/advanced-voi-reviews/voi-1-review.json".into(),
            record_sha256: "d".repeat(64),
            assurance: REVIEW_ASSURANCE.into(),
            previous_hash: None,
            event_hash: String::new(),
        };
        let first = event_hash(&event).unwrap();
        event.previous_hash = Some("e".repeat(64));
        assert_ne!(first, event_hash(&event).unwrap());
    }
}
