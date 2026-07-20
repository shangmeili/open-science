//! App-owned audit boundary for imported survival-extrapolation reviews.
//!
//! The agent may draft the review, but analysis-plan approval is allowed only
//! after this module independently verifies the exact target, local evidence
//! hashes, candidate set, common landmarks, diagnostics, scenarios, and gate.
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::io::Read;
use std::path::{Component, Path};

pub const SURVIVAL_REVIEW_PATH: &str = "heor/survival-extrapolation-review.json";
pub const SURVIVAL_REVIEW_INDEX_PATH: &str = "heor/survival-extrapolation-reviews.json";
const REVIEW_CAP_BYTES: u64 = 10 * 1024 * 1024;
const EVIDENCE_CAP_BYTES: u64 = 256 * 1024 * 1024;
const FAMILIES: &[&str] = &[
    "exponential",
    "weibull",
    "gompertz",
    "gamma",
    "generalized_gamma",
    "generalized_f",
    "lognormal",
    "loglogistic",
];

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SurvivalReviewAudit {
    pub complete: bool,
    pub required: bool,
    pub status: &'static str,
    pub review_sha256: Option<String>,
    pub target_count: usize,
    pub review_count: usize,
    pub analysis_id: String,
    pub target_path: Option<String>,
    pub selected_family: Option<String>,
    pub candidate_models: usize,
    pub converged_models: usize,
    pub failed_models: Vec<String>,
    pub scenario_count: usize,
    pub recommended_family: Option<String>,
    pub execution_environment: Option<String>,
    pub cross_implementation_complete: bool,
    pub artifact_bindings: Vec<crate::heor_approval::ArtifactBinding>,
    pub targets: Vec<SurvivalTargetSummary>,
    pub blocking_gaps: Vec<String>,
    pub errors: Vec<String>,
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SurvivalTargetSummary {
    pub target_path: String,
    pub selected_family: String,
    pub review_path: String,
    pub review_sha256: String,
    pub complete: bool,
    pub candidate_models: usize,
    pub converged_models: usize,
    pub failed_models: Vec<String>,
    pub scenario_count: usize,
    pub recommended_family: Option<String>,
    pub execution_environment: Option<String>,
    pub cross_implementation_complete: bool,
    pub errors: Vec<String>,
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
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

fn safe_id(value: &str) -> bool {
    let mut bytes = value.bytes();
    bytes.next().is_some_and(|byte| byte.is_ascii_lowercase())
        && value.len() <= 64
        && bytes.all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'_' | b'-')
        })
}

fn is_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn exact_fields(value: &serde_json::Value, fields: &[&str]) -> bool {
    value.as_object().is_some_and(|object| {
        object.len() == fields.len() && fields.iter().all(|field| object.contains_key(*field))
    })
}

fn survival_targets(plan: &serde_json::Value) -> Vec<(String, String)> {
    plan.get("input_provenance")
        .and_then(serde_json::Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|mapping| {
            let operation = mapping
                .pointer("/derivation/transformation/operation")
                .and_then(serde_json::Value::as_str)?;
            if operation != "parametric_survival_to_transition_schedule" {
                return None;
            }
            Some((
                mapping
                    .get("path")
                    .and_then(serde_json::Value::as_str)
                    .unwrap_or_default()
                    .to_owned(),
                mapping
                    .pointer("/derivation/transformation/distribution")
                    .and_then(serde_json::Value::as_str)
                    .unwrap_or_default()
                    .to_owned(),
            ))
        })
        .collect()
}

fn hash_capped_file(path: &Path, cap: u64, label: &str) -> Result<String, String> {
    let metadata =
        std::fs::metadata(path).map_err(|error| format!("{label} unavailable: {error}"))?;
    if !metadata.is_file() || metadata.len() > cap {
        return Err(format!("{label} is not a reviewable artifact"));
    }
    let mut file =
        std::fs::File::open(path).map_err(|error| format!("{label} unavailable: {error}"))?;
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 64 * 1024];
    loop {
        let count = file
            .read(&mut buffer)
            .map_err(|error| format!("{label} unavailable: {error}"))?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    Ok(format!("{:x}", digest.finalize()))
}

fn bound_file(
    workspace: &Path,
    path: Option<&serde_json::Value>,
    digest: Option<&serde_json::Value>,
    label: &str,
    errors: &mut Vec<String>,
) {
    let Some(relative) = text(path) else {
        errors.push(format!("{label} requires a relative path"));
        return;
    };
    let Some(expected) = digest
        .and_then(serde_json::Value::as_str)
        .filter(|v| is_sha256(v))
    else {
        errors.push(format!("{label} requires a lowercase SHA-256"));
        return;
    };
    let relative_path = Path::new(relative);
    if relative_path.is_absolute()
        || relative_path
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        errors.push(format!("{label} path must stay inside the workspace"));
        return;
    }
    let Ok(root) = workspace.canonicalize() else {
        errors.push("workspace is unavailable".into());
        return;
    };
    let Ok(resolved) = root.join(relative_path).canonicalize() else {
        errors.push(format!("{label} file is missing from the workspace"));
        return;
    };
    if !resolved.starts_with(&root) {
        errors.push(format!("{label} path must stay inside the workspace"));
        return;
    }
    match hash_capped_file(&resolved, EVIDENCE_CAP_BYTES, label) {
        Ok(actual) if actual == expected => {}
        Ok(_) => errors.push(format!("{label} SHA-256 does not match the current file")),
        Err(error) => errors.push(error),
    }
}

fn empty_audit(required: bool, status: &'static str, analysis_id: String) -> SurvivalReviewAudit {
    SurvivalReviewAudit {
        complete: !required,
        required,
        status,
        review_sha256: None,
        target_count: 0,
        review_count: 0,
        analysis_id,
        target_path: None,
        selected_family: None,
        candidate_models: 0,
        converged_models: 0,
        failed_models: Vec::new(),
        scenario_count: 0,
        recommended_family: None,
        execution_environment: None,
        cross_implementation_complete: false,
        artifact_bindings: Vec::new(),
        targets: Vec::new(),
        blocking_gaps: Vec::new(),
        errors: Vec::new(),
    }
}

pub(crate) fn audit_survival_review_value(
    workspace: &Path,
    plan: &serde_json::Value,
    review: &serde_json::Value,
    review_sha256: String,
    target_path: &str,
    selected_family: &str,
) -> SurvivalReviewAudit {
    let analysis_id = text(plan.get("analysis_id")).unwrap_or_default().to_owned();
    let mut audit = empty_audit(true, "incomplete", analysis_id.clone());
    audit.review_sha256 = Some(review_sha256);
    audit.target_path = Some(target_path.to_owned());
    audit.selected_family = Some(selected_family.to_owned());
    let errors = &mut audit.errors;

    if !exact_fields(
        review,
        &[
            "schema_version",
            "review_id",
            "status",
            "analysis_target",
            "context",
            "source_data",
            "pre_specification",
            "execution",
            "models",
            "diagnostics",
            "structural_scenarios",
            "analyst_recommendation",
            "limitations",
            "human_gate",
        ],
    ) {
        errors.push("review fields are not the exact supported contract".into());
        audit.blocking_gaps = errors.clone();
        return audit;
    }
    let schema_version = review
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default();
    if !matches!(schema_version, "0.2.0" | "0.3.0") {
        errors.push("schema_version must be 0.2.0 or 0.3.0".into());
    }
    if !review
        .get("review_id")
        .and_then(serde_json::Value::as_str)
        .is_some_and(safe_id)
    {
        errors.push("review_id must be a safe lowercase identifier".into());
    }
    if review.get("status").and_then(serde_json::Value::as_str) != Some("ready_for_human_review") {
        errors.push("status must be ready_for_human_review for approval".into());
    }
    let target = review
        .get("analysis_target")
        .unwrap_or(&serde_json::Value::Null);
    if !exact_fields(target, &["analysis_id", "path"])
        || target
            .get("analysis_id")
            .and_then(serde_json::Value::as_str)
            != Some(&analysis_id)
        || target.get("path").and_then(serde_json::Value::as_str) != Some(target_path)
    {
        errors.push(
            "analysis_target must match the current analysis id and survival mapping path".into(),
        );
    }

    let context = review.get("context").unwrap_or(&serde_json::Value::Null);
    if !exact_fields(
        context,
        &[
            "endpoint",
            "population",
            "curve_label",
            "time_origin",
            "time_unit",
            "observed_follow_up",
            "model_horizon",
        ],
    ) {
        errors.push("context fields are not the exact supported contract".into());
    } else {
        for field in ["endpoint", "population", "curve_label", "time_origin"] {
            if text(context.get(field)).is_none() {
                errors.push(format!("context.{field} must be non-empty"));
            }
        }
        if !matches!(
            context.get("time_unit").and_then(serde_json::Value::as_str),
            Some("days" | "weeks" | "months" | "years")
        ) {
            errors.push("context.time_unit is unsupported".into());
        }
        match (
            finite(context.get("observed_follow_up")),
            finite(context.get("model_horizon")),
        ) {
            (Some(observed), Some(horizon)) if observed > 0.0 && horizon > observed => {}
            _ => errors.push("model_horizon must exceed a positive observed_follow_up".into()),
        }
    }

    let source = review
        .get("source_data")
        .unwrap_or(&serde_json::Value::Null);
    if !exact_fields(
        source,
        &[
            "classification",
            "execution_boundary",
            "format",
            "path",
            "sha256",
            "time_variable",
            "event_definition",
            "censor_definition",
        ],
    ) {
        errors.push("source_data fields are not the exact supported contract".into());
    } else {
        let classification = source
            .get("classification")
            .and_then(serde_json::Value::as_str);
        if !matches!(
            classification,
            Some("public" | "non_sensitive" | "restricted")
        ) && !(schema_version == "0.2.0" && classification == Some("unknown"))
        {
            errors.push("source_data.classification is unsupported".into());
        }
        if source
            .get("execution_boundary")
            .and_then(serde_json::Value::as_str)
            != Some("local_only")
            || source.get("format").and_then(serde_json::Value::as_str)
                != Some("precomputed_survival_fit_bundle")
        {
            errors.push("source_data must be a local precomputed survival fit bundle".into());
        }
        for field in ["time_variable", "event_definition", "censor_definition"] {
            if text(source.get(field)).is_none() {
                errors.push(format!("source_data.{field} must be non-empty"));
            }
        }
        bound_file(
            workspace,
            source.get("path"),
            source.get("sha256"),
            "source_data",
            errors,
        );
    }

    let prespec = review
        .get("pre_specification")
        .unwrap_or(&serde_json::Value::Null);
    let mut candidates = Vec::new();
    if !exact_fields(
        prespec,
        &["fit_method", "candidate_models", "protocol_deviations"],
    ) || prespec
        .get("fit_method")
        .and_then(serde_json::Value::as_str)
        != Some("maximum_likelihood")
    {
        errors.push("pre_specification is invalid".into());
    } else if let Some(items) = prespec
        .get("candidate_models")
        .and_then(serde_json::Value::as_array)
    {
        if !(2..=8).contains(&items.len()) {
            errors.push("candidate_models must contain 2-8 entries".into());
        }
        for (index, item) in items.iter().enumerate() {
            let family = item.get("family").and_then(serde_json::Value::as_str);
            if !exact_fields(item, &["family", "rationale"])
                || !family.is_some_and(|value| FAMILIES.contains(&value))
                || text(item.get("rationale")).is_none()
            {
                errors.push(format!("candidate_models[{index}] is invalid"));
            } else {
                candidates.push(family.unwrap().to_owned());
            }
        }
        if candidates.iter().collect::<HashSet<_>>().len() != candidates.len() {
            errors.push("candidate model families must be unique".into());
        }
        if !prespec
            .get("protocol_deviations")
            .and_then(serde_json::Value::as_array)
            .is_some_and(|items| items.iter().all(|item| text(Some(item)).is_some()))
        {
            errors.push("protocol_deviations must be a list of non-empty strings".into());
        }
    } else {
        errors.push("candidate_models must be a list".into());
    }
    audit.candidate_models = candidates.len();

    let execution = review.get("execution").unwrap_or(&serde_json::Value::Null);
    let expected_environment = if schema_version == "0.3.0" {
        "ai4heor_isolated_local_mle"
    } else {
        "external_local_fit_import"
    };
    audit.execution_environment = text(execution.get("environment")).map(str::to_owned);
    if !exact_fields(
        execution,
        &[
            "backend",
            "environment",
            "r_version",
            "package_versions",
            "command_path",
            "command_sha256",
            "session_info_path",
            "session_info_sha256",
        ],
    ) || execution.get("backend").and_then(serde_json::Value::as_str) != Some("survHE")
        || execution
            .get("environment")
            .and_then(serde_json::Value::as_str)
            != Some(expected_environment)
    {
        errors.push(format!(
            "execution.environment must be {expected_environment}"
        ));
    } else {
        if text(execution.get("r_version")).is_none() {
            errors.push("execution.r_version must be recorded".into());
        }
        let packages = execution
            .get("package_versions")
            .and_then(serde_json::Value::as_object);
        if !["survHE", "flexsurv", "survival"].iter().all(|name| {
            packages
                .and_then(|map| map.get(*name))
                .and_then(serde_json::Value::as_str)
                .is_some_and(|v| !v.trim().is_empty())
        }) {
            errors.push("package_versions must include survHE, flexsurv, and survival".into());
        }
        bound_file(
            workspace,
            execution.get("command_path"),
            execution.get("command_sha256"),
            "execution command",
            errors,
        );
        bound_file(
            workspace,
            execution.get("session_info_path"),
            execution.get("session_info_sha256"),
            "session info",
            errors,
        );
    }

    if schema_version == "0.3.0" {
        let manifest_path = text(source.get("path")).unwrap_or_default();
        let (execution_audit, execution_errors) =
            crate::heor_survival_execution::audit_survival_fit_execution_for_review(
                workspace,
                manifest_path,
                review,
            );
        audit.cross_implementation_complete = execution_audit.cross_implementation_complete;
        errors.extend(execution_errors);
    }

    let models = review.get("models").and_then(serde_json::Value::as_array);
    let mut result_families = Vec::new();
    let mut converged = HashSet::new();
    let mut common_times: Option<Vec<f64>> = None;
    if let Some(models) = models {
        for (index, model) in models.iter().enumerate() {
            let label = format!("models[{index}]");
            if !exact_fields(
                model,
                &[
                    "family",
                    "status",
                    "aic",
                    "bic",
                    "log_likelihood",
                    "parameterization",
                    "fit_output_path",
                    "fit_output_sha256",
                    "landmarks",
                    "warnings",
                ],
            ) {
                errors.push(format!("{label} fields are invalid"));
                continue;
            }
            let Some(family) = model.get("family").and_then(serde_json::Value::as_str) else {
                errors.push(format!("{label}.family is missing"));
                continue;
            };
            result_families.push(family.to_owned());
            if !model
                .get("warnings")
                .and_then(serde_json::Value::as_array)
                .is_some_and(|items| items.iter().all(|item| text(Some(item)).is_some()))
            {
                errors.push(format!(
                    "{label}.warnings must be non-empty strings when present"
                ));
            }
            match model.get("status").and_then(serde_json::Value::as_str) {
                Some("failed") => {
                    audit.failed_models.push(family.to_owned());
                    if ["aic", "bic", "log_likelihood"]
                        .iter()
                        .any(|field| !model.get(*field).is_some_and(serde_json::Value::is_null))
                        || !model
                            .get("landmarks")
                            .and_then(serde_json::Value::as_array)
                            .is_some_and(Vec::is_empty)
                    {
                        errors.push(format!(
                            "{label} failed fit statistics must be null and landmarks empty"
                        ));
                    }
                }
                Some("converged") => {
                    converged.insert(family.to_owned());
                    if ["aic", "bic", "log_likelihood"]
                        .iter()
                        .any(|field| finite(model.get(*field)).is_none())
                        || text(model.get("parameterization")).is_none()
                    {
                        errors.push(format!(
                            "{label} fit statistics or parameterization are invalid"
                        ));
                    }
                    bound_file(
                        workspace,
                        model.get("fit_output_path"),
                        model.get("fit_output_sha256"),
                        &format!("{label} fit output"),
                        errors,
                    );
                    let mut times = Vec::new();
                    let mut previous_time = -1.0;
                    let mut previous_survival = 1.0;
                    if let Some(landmarks) = model
                        .get("landmarks")
                        .and_then(serde_json::Value::as_array)
                        .filter(|items| items.len() >= 3)
                    {
                        for landmark in landmarks {
                            let Some(time) = finite(landmark.get("time")) else {
                                errors.push(format!("{label} landmark time is invalid"));
                                continue;
                            };
                            let survival = finite(landmark.get("survival"));
                            let hazard = finite(landmark.get("hazard"));
                            if !exact_fields(landmark, &["time", "survival", "hazard"])
                                || time < 0.0
                                || time <= previous_time
                                || !survival.is_some_and(|value| {
                                    value >= 0.0
                                        && value <= 1.0
                                        && value <= previous_survival + 1e-12
                                })
                                || !hazard.is_some_and(|value| value >= 0.0)
                            {
                                errors.push(format!("{label} landmarks are invalid"));
                                break;
                            }
                            times.push(time);
                            previous_time = time;
                            previous_survival = survival.unwrap();
                        }
                        if times.first() != Some(&0.0)
                            || landmarks
                                .first()
                                .and_then(|v| v.get("survival"))
                                .and_then(serde_json::Value::as_f64)
                                != Some(1.0)
                        {
                            errors.push(format!(
                                "{label} landmarks must start at time 0 with survival 1"
                            ));
                        }
                        if let (Some(observed), Some(horizon)) = (
                            finite(context.get("observed_follow_up")),
                            finite(context.get("model_horizon")),
                        ) {
                            if !times.iter().any(|time| *time > 0.0 && *time <= observed)
                                || !times
                                    .iter()
                                    .any(|time| *time > observed && *time <= horizon)
                            {
                                errors.push(format!("{label} landmarks must cover observed and extrapolated periods"));
                            }
                        }
                        if common_times.as_ref().is_some_and(|common| common != &times) {
                            errors.push(
                                "all converged models must use identical landmark times".into(),
                            );
                        } else if common_times.is_none() {
                            common_times = Some(times);
                        }
                    } else {
                        errors.push(format!(
                            "{label}.landmarks must contain at least three common times"
                        ));
                    }
                }
                _ => errors.push(format!("{label}.status must be converged or failed")),
            }
        }
    } else {
        errors.push("models must be a list".into());
    }
    if result_families != candidates {
        errors.push("model results must match the pre-specified candidate order".into());
    }
    if converged.len() < 2 {
        errors.push("at least two candidate models must converge".into());
    }
    if !converged.contains(selected_family) {
        errors.push("analysis-plan selected distribution must be a converged candidate".into());
    }
    audit.converged_models = converged.len();

    let diagnostics = review
        .get("diagnostics")
        .unwrap_or(&serde_json::Value::Null);
    if !exact_fields(
        diagnostics,
        &[
            "km_overlay_path",
            "km_overlay_sha256",
            "log_cumulative_hazard_path",
            "log_cumulative_hazard_sha256",
            "hazard_plot_path",
            "hazard_plot_sha256",
            "internal_validity_assessment",
            "external_validity_assessment",
            "external_sources",
            "clinical_plausibility_assessment",
        ],
    ) {
        errors.push("diagnostics fields are invalid".into());
    } else {
        for (path, digest, label) in [
            ("km_overlay_path", "km_overlay_sha256", "KM overlay"),
            (
                "log_cumulative_hazard_path",
                "log_cumulative_hazard_sha256",
                "log-cumulative-hazard plot",
            ),
            ("hazard_plot_path", "hazard_plot_sha256", "hazard plot"),
        ] {
            bound_file(
                workspace,
                diagnostics.get(path),
                diagnostics.get(digest),
                label,
                errors,
            );
        }
        for field in [
            "internal_validity_assessment",
            "external_validity_assessment",
            "clinical_plausibility_assessment",
        ] {
            if text(diagnostics.get(field)).is_none() {
                errors.push(format!("diagnostics.{field} must be non-empty"));
            }
        }
        let sources = diagnostics
            .get("external_sources")
            .and_then(serde_json::Value::as_array);
        let unresolved = text(diagnostics.get("external_validity_assessment"))
            .is_some_and(|v| v.to_ascii_lowercase().contains("unresolved"));
        if !sources.is_some_and(|items| items.iter().all(|item| text(Some(item)).is_some()))
            || (sources.is_some_and(Vec::is_empty) && !unresolved)
        {
            errors.push(
                "external validity needs a source or an explicit unresolved statement".into(),
            );
        }
    }

    let scenarios = review
        .get("structural_scenarios")
        .and_then(serde_json::Value::as_array);
    let scenario_families = scenarios
        .map(|items| {
            items
                .iter()
                .filter_map(serde_json::Value::as_str)
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    audit.scenario_count = scenario_families.len();
    if scenario_families.len() < 2
        || scenario_families
            .iter()
            .any(|family| !converged.contains(*family))
        || scenario_families.iter().collect::<HashSet<_>>().len() != scenario_families.len()
    {
        errors.push(
            "structural_scenarios must contain at least two unique converged families".into(),
        );
    }

    if let Some(recommendation) = review
        .get("analyst_recommendation")
        .filter(|value| !value.is_null())
    {
        if !exact_fields(recommendation, &["family", "rationale", "alternatives"]) {
            errors.push("analyst_recommendation fields are invalid".into());
        } else if let Some(family) = recommendation
            .get("family")
            .and_then(serde_json::Value::as_str)
        {
            audit.recommended_family = Some(family.to_owned());
            let alternatives = recommendation
                .get("alternatives")
                .and_then(serde_json::Value::as_array);
            if !converged.contains(family)
                || !scenario_families.contains(&family)
                || text(recommendation.get("rationale")).is_none()
                || !alternatives.is_some_and(|items| {
                    !items.is_empty()
                        && items.iter().all(|item| {
                            item.as_str()
                                .is_some_and(|value| value != family && converged.contains(value))
                        })
                })
            {
                errors.push(
                    "analyst_recommendation must name a converged scenario and alternatives".into(),
                );
            }
        } else {
            errors.push("analyst_recommendation.family is missing".into());
        }
    }
    if !review
        .get("limitations")
        .and_then(serde_json::Value::as_array)
        .is_some_and(|items| {
            !items.is_empty() && items.iter().all(|item| text(Some(item)).is_some())
        })
    {
        errors.push("limitations must contain non-empty strings".into());
    }
    let gate = review.get("human_gate").unwrap_or(&serde_json::Value::Null);
    if !exact_fields(gate, &["state", "required_action"])
        || gate.get("state").and_then(serde_json::Value::as_str) != Some("awaiting_human_selection")
        || gate
            .get("required_action")
            .and_then(serde_json::Value::as_str)
            != Some("select_curve_in_analysis_plan")
    {
        errors.push("human_gate must remain awaiting Human selection in the analysis plan".into());
    }
    let serialized = serde_json::to_string(review)
        .unwrap_or_default()
        .to_ascii_lowercase();
    for key in [
        "\"approved\":",
        "\"accepted\":",
        "\"selected\":",
        "\"approval_timestamp\":",
        "\"reviewer_signature\":",
    ] {
        if serialized.contains(key) {
            errors.push("review contains a forbidden approval or selection authority field".into());
            break;
        }
    }

    audit.complete = errors.is_empty();
    audit.status = if audit.complete {
        "complete"
    } else {
        "incomplete"
    };
    audit.blocking_gaps = errors.clone();
    audit
}

fn target_summary(audit: &SurvivalReviewAudit, review_path: &str) -> SurvivalTargetSummary {
    SurvivalTargetSummary {
        target_path: audit.target_path.clone().unwrap_or_default(),
        selected_family: audit.selected_family.clone().unwrap_or_default(),
        review_path: review_path.into(),
        review_sha256: audit.review_sha256.clone().unwrap_or_default(),
        complete: audit.complete,
        candidate_models: audit.candidate_models,
        converged_models: audit.converged_models,
        failed_models: audit.failed_models.clone(),
        scenario_count: audit.scenario_count,
        recommended_family: audit.recommended_family.clone(),
        execution_environment: audit.execution_environment.clone(),
        cross_implementation_complete: audit.cross_implementation_complete,
        errors: audit.errors.clone(),
    }
}

fn fixed_collection_review_path(value: &str) -> bool {
    let components = Path::new(value).components().collect::<Vec<_>>();
    if !matches!(
        components.as_slice(),
        [Component::Normal(heor), Component::Normal(directory), Component::Normal(file)]
            if *heor == "heor" && *directory == "survival-extrapolation-reviews"
                && Path::new(file).extension().and_then(|extension| extension.to_str()) == Some("json")
    ) {
        return false;
    }
    Path::new(value)
        .file_stem()
        .and_then(|stem| stem.to_str())
        .is_some_and(safe_id)
}

fn audit_collection(
    workspace: &Path,
    plan: &serde_json::Value,
    targets: &[(String, String)],
) -> SurvivalReviewAudit {
    let analysis_id = text(plan.get("analysis_id")).unwrap_or_default().to_owned();
    let mut aggregate = empty_audit(true, "incomplete", analysis_id.clone());
    aggregate.target_count = targets.len();
    if targets.len() > 32 {
        aggregate
            .errors
            .push("survival review collection supports at most 32 targets".into());
        aggregate.blocking_gaps = aggregate.errors.clone();
        return aggregate;
    }
    let index_raw =
        match crate::heor_uncertainty::read_workspace_capped(workspace, SURVIVAL_REVIEW_INDEX_PATH)
        {
            Ok(raw) if raw.len() as u64 <= REVIEW_CAP_BYTES => raw,
            Ok(_) => {
                aggregate
                    .errors
                    .push(format!("{SURVIVAL_REVIEW_INDEX_PATH} is too large"));
                aggregate.blocking_gaps = aggregate.errors.clone();
                return aggregate;
            }
            Err(error) => {
                aggregate.errors.push(error);
                aggregate.blocking_gaps = aggregate.errors.clone();
                return aggregate;
            }
        };
    let index_sha256 = sha256(&index_raw);
    aggregate.review_sha256 = Some(index_sha256.clone());
    aggregate
        .artifact_bindings
        .push(crate::heor_approval::ArtifactBinding {
            path: SURVIVAL_REVIEW_INDEX_PATH.into(),
            sha256: index_sha256,
        });
    let index: serde_json::Value = match serde_json::from_slice(&index_raw) {
        Ok(value) => value,
        Err(error) => {
            aggregate.errors.push(format!(
                "survival review collection is invalid JSON: {error}"
            ));
            aggregate.blocking_gaps = aggregate.errors.clone();
            return aggregate;
        }
    };
    if !exact_fields(&index, &["schema_version", "analysis_id", "reviews"])
        || index
            .get("schema_version")
            .and_then(serde_json::Value::as_str)
            != Some("0.1.0")
    {
        aggregate.errors.push(
            "survival review collection fields or schema_version are not the exact 0.1.0 contract"
                .into(),
        );
    }
    if index.get("analysis_id").and_then(serde_json::Value::as_str) != Some(&analysis_id) {
        aggregate
            .errors
            .push("survival review collection analysis_id must match the current plan".into());
    }
    let Some(entries) = index.get("reviews").and_then(serde_json::Value::as_array) else {
        aggregate
            .errors
            .push("survival review collection reviews must be an array".into());
        aggregate.blocking_gaps = aggregate.errors.clone();
        return aggregate;
    };
    aggregate.review_count = entries.len();
    if entries.len() != targets.len() {
        aggregate.errors.push(format!(
            "survival review collection must contain exactly {} reviews in plan-target order",
            targets.len()
        ));
    }
    let mut seen_targets = HashSet::new();
    let mut seen_paths = HashSet::new();
    for (index, (target_path, selected_family)) in targets.iter().enumerate() {
        let Some(entry) = entries.get(index) else {
            aggregate.errors.push(format!(
                "missing collection review for target {target_path}"
            ));
            continue;
        };
        if !exact_fields(entry, &["target_path", "review_path", "review_sha256"]) {
            aggregate.errors.push(format!(
                "reviews[{index}] fields are not the exact contract"
            ));
            continue;
        }
        let declared_target = text(entry.get("target_path")).unwrap_or_default();
        let review_path = text(entry.get("review_path")).unwrap_or_default();
        let declared_sha256 = entry
            .get("review_sha256")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        if declared_target != target_path {
            aggregate.errors.push(format!(
                "reviews[{index}].target_path must equal {target_path} in plan-target order"
            ));
        }
        if !seen_targets.insert(declared_target.to_owned()) {
            aggregate
                .errors
                .push(format!("duplicate collection target {declared_target}"));
        }
        if !fixed_collection_review_path(review_path) {
            aggregate.errors.push(format!(
                "reviews[{index}].review_path must be one safe JSON file in heor/survival-extrapolation-reviews"
            ));
            continue;
        }
        if !seen_paths.insert(review_path.to_owned()) {
            aggregate
                .errors
                .push(format!("duplicate collection review path {review_path}"));
            continue;
        }
        if !is_sha256(declared_sha256) {
            aggregate.errors.push(format!(
                "reviews[{index}].review_sha256 must be lowercase SHA-256"
            ));
            continue;
        }
        let review_raw =
            match crate::heor_uncertainty::read_workspace_capped(workspace, review_path) {
                Ok(raw) if raw.len() as u64 <= REVIEW_CAP_BYTES => raw,
                Ok(_) => {
                    aggregate.errors.push(format!("{review_path} is too large"));
                    continue;
                }
                Err(error) => {
                    aggregate.errors.push(error);
                    continue;
                }
            };
        let actual_sha256 = sha256(&review_raw);
        if actual_sha256 != declared_sha256 {
            aggregate.errors.push(format!(
                "reviews[{index}].review_sha256 does not match {review_path}"
            ));
        }
        aggregate
            .artifact_bindings
            .push(crate::heor_approval::ArtifactBinding {
                path: review_path.into(),
                sha256: actual_sha256.clone(),
            });
        let review: serde_json::Value = match serde_json::from_slice(&review_raw) {
            Ok(value) => value,
            Err(error) => {
                aggregate
                    .errors
                    .push(format!("{review_path} is invalid JSON: {error}"));
                continue;
            }
        };
        let target_audit = audit_survival_review_value(
            workspace,
            plan,
            &review,
            actual_sha256,
            target_path,
            selected_family,
        );
        aggregate.candidate_models += target_audit.candidate_models;
        aggregate.converged_models += target_audit.converged_models;
        aggregate.scenario_count += target_audit.scenario_count;
        aggregate.failed_models.extend(
            target_audit
                .failed_models
                .iter()
                .map(|family| format!("{target_path}:{family}")),
        );
        aggregate.errors.extend(
            target_audit
                .errors
                .iter()
                .map(|error| format!("{target_path}: {error}")),
        );
        aggregate
            .targets
            .push(target_summary(&target_audit, review_path));
    }
    if entries.len() > targets.len() {
        aggregate
            .errors
            .push("survival review collection contains reviews for undeclared targets".into());
    }
    aggregate.complete = aggregate.errors.is_empty()
        && aggregate.targets.len() == targets.len()
        && aggregate.targets.iter().all(|target| target.complete);
    aggregate.status = if aggregate.complete {
        "complete"
    } else {
        "incomplete"
    };
    aggregate.blocking_gaps = aggregate.errors.clone();
    aggregate
}

pub fn audit_survival_review_for_plan(workspace: &Path, plan_raw: &[u8]) -> SurvivalReviewAudit {
    let plan: serde_json::Value = match serde_json::from_slice(plan_raw) {
        Ok(value) => value,
        Err(error) => {
            let mut audit = empty_audit(true, "incomplete", String::new());
            audit
                .errors
                .push(format!("analysis plan is invalid: {error}"));
            audit.blocking_gaps = audit.errors.clone();
            return audit;
        }
    };
    let analysis_id = text(plan.get("analysis_id")).unwrap_or_default().to_owned();
    let targets = survival_targets(&plan);
    if targets.is_empty() {
        return empty_audit(false, "not_required", analysis_id);
    }
    if targets.len() > 1 {
        return audit_collection(workspace, &plan, &targets);
    }
    let review_raw =
        match crate::heor_uncertainty::read_workspace_capped(workspace, SURVIVAL_REVIEW_PATH) {
            Ok(raw) if raw.len() as u64 <= REVIEW_CAP_BYTES => raw,
            Ok(_) => {
                let mut audit = empty_audit(true, "incomplete", analysis_id);
                audit
                    .errors
                    .push(format!("{SURVIVAL_REVIEW_PATH} is too large"));
                audit.blocking_gaps = audit.errors.clone();
                return audit;
            }
            Err(error) => {
                let mut audit = empty_audit(true, "incomplete", analysis_id);
                audit.errors.push(error);
                audit.blocking_gaps = audit.errors.clone();
                return audit;
            }
        };
    let review: serde_json::Value = match serde_json::from_slice(&review_raw) {
        Ok(value) => value,
        Err(error) => {
            let mut audit = empty_audit(true, "incomplete", analysis_id);
            audit.review_sha256 = Some(sha256(&review_raw));
            audit
                .errors
                .push(format!("survival review is invalid JSON: {error}"));
            audit.blocking_gaps = audit.errors.clone();
            return audit;
        }
    };
    let mut audit = audit_survival_review_value(
        workspace,
        &plan,
        &review,
        sha256(&review_raw),
        &targets[0].0,
        &targets[0].1,
    );
    audit.target_count = 1;
    audit.review_count = 1;
    audit
        .artifact_bindings
        .push(crate::heor_approval::ArtifactBinding {
            path: SURVIVAL_REVIEW_PATH.into(),
            sha256: sha256(&review_raw),
        });
    audit
        .targets
        .push(target_summary(&audit, SURVIVAL_REVIEW_PATH));
    audit
}

pub fn require_survival_review_approvable(
    workspace: &Path,
    plan_raw: &[u8],
) -> Result<Vec<crate::heor_approval::ArtifactBinding>, String> {
    let audit = audit_survival_review_for_plan(workspace, plan_raw);
    if !audit.required {
        return Ok(Vec::new());
    }
    if !audit.complete {
        return Err(format!(
            "survival extrapolation review is incomplete: {}",
            audit.errors.join("; ")
        ));
    }
    Ok(audit.artifact_bindings)
}

#[tauri::command]
pub fn audit_heor_survival_extrapolation(
    app: tauri::AppHandle,
) -> Result<SurvivalReviewAudit, String> {
    let workspace = crate::runtime::workspace_dir(&app)?;
    let plan =
        crate::heor_uncertainty::read_workspace_capped(&workspace, "heor/analysis-plan.json")?;
    Ok(audit_survival_review_for_plan(&workspace, &plan))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::time::{SystemTime, UNIX_EPOCH};

    static NEXT_WORKSPACE_ID: AtomicU64 = AtomicU64::new(0);

    fn workspace() -> std::path::PathBuf {
        let path = std::env::temp_dir().join(format!(
            "ai4heor-survival-review-{}-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos(),
            NEXT_WORKSPACE_ID.fetch_add(1, Ordering::Relaxed)
        ));
        fs::create_dir_all(path.join("heor/evidence")).unwrap();
        path
    }

    fn plan(targets: usize) -> Vec<u8> {
        let mappings = (0..targets)
            .map(|index| {
                serde_json::json!({
                    "path": format!("strategies.treatment_{index}.transition_schedule"),
                    "derivation": {"transformation": {
                        "operation": "parametric_survival_to_transition_schedule",
                        "distribution": "weibull"
                    }}
                })
            })
            .collect::<Vec<_>>();
        serde_json::to_vec(
            &serde_json::json!({"analysis_id": "analysis-one", "input_provenance": mappings}),
        )
        .unwrap()
    }

    fn write_file(root: &Path, name: &str, contents: &[u8]) -> (String, String) {
        let relative = format!("heor/evidence/{name}");
        fs::write(root.join(&relative), contents).unwrap();
        (relative, sha256(contents))
    }

    fn named_review(root: &Path, prefix: &str) -> serde_json::Value {
        let name = |suffix: &str| format!("{prefix}-{suffix}");
        let (bundle_path, bundle_hash) = write_file(root, &name("bundle.json"), b"bundle");
        let (command_path, command_hash) = write_file(root, &name("fit.R"), b"fit");
        let (session_path, session_hash) = write_file(root, &name("session.txt"), b"session");
        let (exp_path, exp_hash) = write_file(root, &name("exp.json"), b"exp");
        let (wei_path, wei_hash) = write_file(root, &name("wei.json"), b"wei");
        let (km_path, km_hash) = write_file(root, &name("km.svg"), b"km");
        let (lch_path, lch_hash) = write_file(root, &name("lch.svg"), b"lch");
        let (hazard_path, hazard_hash) = write_file(root, &name("hazard.svg"), b"hazard");
        let landmarks = serde_json::json!([
            {"time": 0.0, "survival": 1.0, "hazard": 0.1},
            {"time": 1.0, "survival": 0.8, "hazard": 0.2},
            {"time": 3.0, "survival": 0.5, "hazard": 0.3}
        ]);
        serde_json::json!({
            "schema_version": "0.2.0",
            "review_id": "review-one",
            "status": "ready_for_human_review",
            "analysis_target": {"analysis_id": "analysis-one", "path": "strategies.treatment_0.transition_schedule"},
            "context": {"endpoint": "OS", "population": "Adults", "curve_label": "Treatment OS", "time_origin": "randomisation", "time_unit": "years", "observed_follow_up": 2.0, "model_horizon": 3.0},
            "source_data": {"classification": "non_sensitive", "execution_boundary": "local_only", "format": "precomputed_survival_fit_bundle", "path": bundle_path, "sha256": bundle_hash, "time_variable": "time", "event_definition": "death", "censor_definition": "right censoring"},
            "pre_specification": {"fit_method": "maximum_likelihood", "candidate_models": [
                {"family": "exponential", "rationale": "Simple reference"},
                {"family": "weibull", "rationale": "Allows monotone hazard"}
            ], "protocol_deviations": []},
            "execution": {"backend": "survHE", "environment": "external_local_fit_import", "r_version": "R 4.4.0", "package_versions": {"survHE": "2", "flexsurv": "2", "survival": "3"}, "command_path": command_path, "command_sha256": command_hash, "session_info_path": session_path, "session_info_sha256": session_hash},
            "models": [
                {"family": "exponential", "status": "converged", "aic": 10.0, "bic": 11.0, "log_likelihood": -4.0, "parameterization": "rate", "fit_output_path": exp_path, "fit_output_sha256": exp_hash, "landmarks": landmarks.clone(), "warnings": []},
                {"family": "weibull", "status": "converged", "aic": 9.0, "bic": 10.0, "log_likelihood": -3.0, "parameterization": "shape-scale", "fit_output_path": wei_path, "fit_output_sha256": wei_hash, "landmarks": landmarks, "warnings": []}
            ],
            "diagnostics": {"km_overlay_path": km_path, "km_overlay_sha256": km_hash, "log_cumulative_hazard_path": lch_path, "log_cumulative_hazard_sha256": lch_hash, "hazard_plot_path": hazard_path, "hazard_plot_sha256": hazard_hash, "internal_validity_assessment": "Both fit", "external_validity_assessment": "Unresolved pending external data", "external_sources": [], "clinical_plausibility_assessment": "Reviewed"},
            "structural_scenarios": ["exponential", "weibull"],
            "analyst_recommendation": {"family": "weibull", "rationale": "Plausible hazard", "alternatives": ["exponential"]},
            "limitations": ["No patient-level fitting in AI4HEOR"],
            "human_gate": {"state": "awaiting_human_selection", "required_action": "select_curve_in_analysis_plan"}
        })
    }

    fn valid_review(root: &Path) -> serde_json::Value {
        named_review(root, "single")
    }

    #[test]
    fn review_is_not_required_without_a_survival_target() {
        let root = workspace();
        let audit = audit_survival_review_for_plan(&root, &plan(0));
        assert!(audit.complete);
        assert!(!audit.required);
        assert_eq!(audit.status, "not_required");
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn complete_review_binds_the_exact_target_and_files() {
        let root = workspace();
        let review = valid_review(&root);
        fs::write(
            root.join(SURVIVAL_REVIEW_PATH),
            serde_json::to_vec_pretty(&review).unwrap(),
        )
        .unwrap();
        let audit = audit_survival_review_for_plan(&root, &plan(1));
        assert!(audit.complete, "{:?}", audit.errors);
        assert_eq!(audit.selected_family.as_deref(), Some("weibull"));
        assert_eq!(audit.converged_models, 2);
        assert_eq!(
            require_survival_review_approvable(&root, &plan(1))
                .unwrap()
                .len(),
            1
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn target_and_hash_drift_fail_closed() {
        let root = workspace();
        let mut review = valid_review(&root);
        review["analysis_target"]["path"] =
            serde_json::json!("strategies.other.transition_schedule");
        fs::write(
            root.join(SURVIVAL_REVIEW_PATH),
            serde_json::to_vec(&review).unwrap(),
        )
        .unwrap();
        let audit = audit_survival_review_for_plan(&root, &plan(1));
        assert!(!audit.complete);
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("analysis_target")));
        review["analysis_target"]["path"] =
            serde_json::json!("strategies.treatment_0.transition_schedule");
        review["source_data"]["sha256"] = serde_json::json!("0".repeat(64));
        fs::write(
            root.join(SURVIVAL_REVIEW_PATH),
            serde_json::to_vec(&review).unwrap(),
        )
        .unwrap();
        let audit = audit_survival_review_for_plan(&root, &plan(1));
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("source_data SHA-256")));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn multiple_targets_require_a_complete_collection() {
        let root = workspace();
        let audit = audit_survival_review_for_plan(&root, &plan(2));
        assert!(audit.required);
        assert!(!audit.complete);
        assert!(audit.errors[0].contains(SURVIVAL_REVIEW_INDEX_PATH));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn complete_collection_covers_every_plan_target_and_binds_every_file() {
        let root = workspace();
        fs::create_dir_all(root.join("heor/survival-extrapolation-reviews")).unwrap();
        let mut entries = Vec::new();
        for index in 0..2 {
            let mut review = named_review(&root, &format!("review-{index}"));
            let target_path = format!("strategies.treatment_{index}.transition_schedule");
            review["review_id"] = serde_json::json!(format!("review-{index}"));
            review["analysis_target"]["path"] = serde_json::json!(target_path.clone());
            let review_path = format!("heor/survival-extrapolation-reviews/review-{index}.json");
            let raw = serde_json::to_vec_pretty(&review).unwrap();
            fs::write(root.join(&review_path), &raw).unwrap();
            entries.push(serde_json::json!({
                "target_path": target_path,
                "review_path": review_path,
                "review_sha256": sha256(&raw)
            }));
        }
        let collection = serde_json::json!({
            "schema_version": "0.1.0",
            "analysis_id": "analysis-one",
            "reviews": entries
        });
        fs::write(
            root.join(SURVIVAL_REVIEW_INDEX_PATH),
            serde_json::to_vec_pretty(&collection).unwrap(),
        )
        .unwrap();
        let audit = audit_survival_review_for_plan(&root, &plan(2));
        assert!(audit.complete, "{:?}", audit.errors);
        assert_eq!(audit.target_count, 2);
        assert_eq!(audit.review_count, 2);
        assert_eq!(audit.targets.len(), 2);
        assert_eq!(audit.artifact_bindings.len(), 3);
        assert_eq!(
            require_survival_review_approvable(&root, &plan(2))
                .unwrap()
                .len(),
            3
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn malformed_survival_mapping_cannot_disappear_as_not_required() {
        let root = workspace();
        let mut value: serde_json::Value = serde_json::from_slice(&plan(1)).unwrap();
        value["input_provenance"][0]["derivation"]["transformation"]
            .as_object_mut()
            .unwrap()
            .remove("distribution");
        let audit = audit_survival_review_for_plan(&root, &serde_json::to_vec(&value).unwrap());
        assert!(audit.required);
        assert!(!audit.complete);
        fs::remove_dir_all(root).unwrap();
    }
}
