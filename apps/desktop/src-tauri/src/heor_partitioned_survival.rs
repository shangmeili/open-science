//! App-owned audit and execution boundary for partitioned survival analysis.
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::path::Path;
use tauri::{path::BaseDirectory, AppHandle, Manager};

pub const PARTITIONED_SURVIVAL_PLAN_PATH: &str = "heor/partitioned-survival-plan.json";
pub const PARTITIONED_SURVIVAL_RESULT_PATH: &str = "heor/results/partitioned-survival.json";
const ANALYSIS_PLAN_PATH: &str = "heor/analysis-plan.json";
const OUTPUT_CAP_BYTES: usize = 25 * 1024 * 1024;
const TOLERANCE: f64 = 1e-9;

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PartitionedSurvivalAudit {
    pub required: bool,
    pub complete: bool,
    pub status: &'static str,
    pub psm_id: String,
    pub analysis_id: String,
    pub analysis_plan_sha256: String,
    pub partitioned_survival_sha256: String,
    pub survival_curve_materializations_sha256: String,
    pub strategy_count: usize,
    pub curve_count: usize,
    pub time_point_count: usize,
    pub artifact_bindings: Vec<crate::heor_approval::ArtifactBinding>,
    pub errors: Vec<String>,
}

#[derive(Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PartitionedSurvivalRunResult {
    workflow: crate::heor_engine::HeorWorkflowStatus,
    calculation: serde_json::Value,
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn empty_audit(plan_raw: &[u8], required: bool) -> PartitionedSurvivalAudit {
    PartitionedSurvivalAudit {
        required,
        complete: !required,
        status: if required {
            "incomplete"
        } else {
            "not_required"
        },
        psm_id: String::new(),
        analysis_id: String::new(),
        analysis_plan_sha256: sha256(plan_raw),
        partitioned_survival_sha256: String::new(),
        survival_curve_materializations_sha256: String::new(),
        strategy_count: 0,
        curve_count: 0,
        time_point_count: 0,
        artifact_bindings: Vec::new(),
        errors: Vec::new(),
    }
}

fn nonempty(value: Option<&serde_json::Value>) -> bool {
    value
        .and_then(serde_json::Value::as_str)
        .is_some_and(|value| !value.trim().is_empty())
}

fn string_set(value: Option<&serde_json::Value>) -> Option<HashSet<&str>> {
    let values = value?.as_array()?;
    let mut result = HashSet::new();
    for value in values {
        let value = value.as_str()?;
        if value.trim().is_empty() || !result.insert(value) {
            return None;
        }
    }
    (!result.is_empty()).then_some(result)
}

fn finite(value: Option<&serde_json::Value>) -> Option<f64> {
    value
        .and_then(serde_json::Value::as_f64)
        .filter(|value| value.is_finite())
}

fn valid_sha(value: Option<&serde_json::Value>) -> bool {
    value
        .and_then(serde_json::Value::as_str)
        .is_some_and(|value| {
            value.len() == 64
                && value
                    .bytes()
                    .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
        })
}

fn safe_relative_path(path: &str) -> bool {
    !path.is_empty()
        && !Path::new(path).is_absolute()
        && Path::new(path).components().all(|component| {
            matches!(
                component,
                std::path::Component::Normal(_) | std::path::Component::CurDir
            )
        })
}

fn audit_values(
    workspace: &Path,
    plan: &serde_json::Value,
    plan_raw: &[u8],
    psm: &serde_json::Value,
    psm_raw: &[u8],
) -> PartitionedSurvivalAudit {
    let mut audit = empty_audit(plan_raw, true);
    audit.partitioned_survival_sha256 = sha256(psm_raw);
    audit.psm_id = psm
        .get("psm_id")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default()
        .to_string();
    audit.analysis_id = psm
        .get("analysis_id")
        .and_then(serde_json::Value::as_str)
        .unwrap_or_default()
        .to_string();
    if psm
        .get("schema_version")
        .and_then(serde_json::Value::as_str)
        != Some("0.2.0")
    {
        audit
            .errors
            .push("partitioned survival schema_version must be 0.2.0".into());
    }
    for field in ["psm_id", "analysis_id", "time_origin"] {
        if !nonempty(psm.get(field)) {
            audit
                .errors
                .push(format!("partitioned survival {field} is required"));
        }
    }
    if psm.get("status").and_then(serde_json::Value::as_str) != Some("ready_for_human_review") {
        audit
            .errors
            .push("partitioned survival plan must be ready_for_human_review".into());
    }
    if psm.get("analysis_id") != plan.get("analysis_id") {
        audit
            .errors
            .push("partitioned survival analysis_id does not match the analysis plan".into());
    }
    if psm
        .pointer("/base_analysis/path")
        .and_then(serde_json::Value::as_str)
        != Some(ANALYSIS_PLAN_PATH)
        || psm
            .pointer("/base_analysis/content_sha256")
            .and_then(serde_json::Value::as_str)
            != Some(audit.analysis_plan_sha256.as_str())
    {
        audit.errors.push(
            "partitioned survival base_analysis does not match current analysis-plan bytes".into(),
        );
    }
    if plan
        .pointer("/partitioned_survival_analysis/path")
        .and_then(serde_json::Value::as_str)
        != Some(PARTITIONED_SURVIVAL_PLAN_PATH)
    {
        audit.errors.push(format!(
            "analysis plan must link {PARTITIONED_SURVIVAL_PLAN_PATH}"
        ));
    }
    let expected_states = ["progression_free", "progressed", "dead"];
    if plan
        .get("states")
        .and_then(serde_json::Value::as_array)
        .map(|states| {
            states
                .iter()
                .filter_map(serde_json::Value::as_str)
                .collect::<Vec<_>>()
        })
        != Some(expected_states.to_vec())
    {
        audit.errors.push(
            "partitioned survival requires progression_free, progressed, dead states in order"
                .into(),
        );
    }
    if psm
        .pointer("/model_structure/type")
        .and_then(serde_json::Value::as_str)
        != Some("partitioned_survival")
        || psm
            .pointer("/model_structure/state_order")
            .and_then(serde_json::Value::as_array)
            .map(|states| {
                states
                    .iter()
                    .filter_map(serde_json::Value::as_str)
                    .collect::<Vec<_>>()
            })
            != Some(expected_states.to_vec())
        || psm
            .pointer("/model_structure/forward_only_disease_process")
            .and_then(serde_json::Value::as_bool)
            != Some(true)
    {
        audit
            .errors
            .push("partitioned survival model structure is invalid".into());
    }
    for field in [
        "forward_only_process",
        "population_alignment",
        "endpoint_alignment",
        "time_origin_alignment",
        "independent_extrapolation",
    ] {
        if !nonempty(psm.pointer(&format!("/conceptual_basis/{field}/rationale")))
            || string_set(psm.pointer(&format!("/conceptual_basis/{field}/basis_ids"))).is_none()
        {
            audit
                .errors
                .push(format!("conceptual_basis.{field} is incomplete"));
        }
    }

    let cycles = plan.get("cycles").and_then(serde_json::Value::as_u64);
    let cycle_length = finite(plan.get("cycle_length_years"));
    if !cycles.is_some_and(|value| value > 0) || !cycle_length.is_some_and(|value| value > 0.0) {
        audit.errors.push("analysis cycle grid is invalid".into());
    }
    let strategy_order = plan
        .get("strategy_order")
        .and_then(serde_json::Value::as_array)
        .map(|values| {
            values
                .iter()
                .filter_map(serde_json::Value::as_str)
                .collect::<Vec<_>>()
        })
        .unwrap_or_else(|| vec!["comparator", "intervention"]);
    let strategies = psm.get("strategies").and_then(serde_json::Value::as_object);
    audit.strategy_count = strategies.map_or(0, serde_json::Map::len);
    let observed_ids = strategies
        .map(|values| values.keys().map(String::as_str).collect::<HashSet<_>>())
        .unwrap_or_default();
    if observed_ids != strategy_order.iter().copied().collect::<HashSet<_>>() {
        audit
            .errors
            .push("partitioned survival strategies must match strategy_order exactly".into());
    }
    for strategy_id in strategy_order {
        let Some(strategy) = strategies.and_then(|values| values.get(strategy_id)) else {
            continue;
        };
        let mut endpoint_values: Vec<Vec<f64>> = Vec::new();
        for endpoint in ["pfs", "os"] {
            audit.curve_count += 1;
            let rows = strategy.get(endpoint).and_then(serde_json::Value::as_array);
            let expected_count = cycles.map_or(0, |value| value as usize + 1);
            if rows.map_or(0, Vec::len) != expected_count {
                audit.errors.push(format!(
                    "{strategy_id}.{endpoint} must contain time zero and every cycle endpoint"
                ));
                continue;
            }
            audit.time_point_count += rows.map_or(0, Vec::len);
            let mut values = Vec::new();
            let mut prior = 1.0;
            for (index, row) in rows.into_iter().flatten().enumerate() {
                let time = finite(row.get("time_years"));
                let survival = finite(row.get("survival"));
                let expected_time = index as f64 * cycle_length.unwrap_or(0.0);
                if !time.is_some_and(|value| (value - expected_time).abs() <= TOLERANCE) {
                    audit.errors.push(format!(
                        "{strategy_id}.{endpoint}[{index}] time grid mismatch"
                    ));
                }
                let Some(survival) = survival.filter(|value| (0.0..=1.0).contains(value)) else {
                    audit.errors.push(format!(
                        "{strategy_id}.{endpoint}[{index}] survival is invalid"
                    ));
                    continue;
                };
                if index == 0 && (survival - 1.0).abs() > TOLERANCE {
                    audit.errors.push(format!(
                        "{strategy_id}.{endpoint} survival at time zero must be 1"
                    ));
                }
                if survival > prior + TOLERANCE {
                    audit.errors.push(format!(
                        "{strategy_id}.{endpoint} survival must be non-increasing"
                    ));
                }
                if string_set(row.get("basis_ids")).is_none() {
                    audit.errors.push(format!(
                        "{strategy_id}.{endpoint}[{index}] basis_ids are required"
                    ));
                }
                prior = survival;
                values.push(survival);
            }
            endpoint_values.push(values);

            let binding = strategy.pointer(&format!("/curve_review_bindings/{endpoint}"));
            let path = binding
                .and_then(|value| value.get("path"))
                .and_then(serde_json::Value::as_str);
            let digest = binding
                .and_then(|value| value.get("content_sha256"))
                .and_then(serde_json::Value::as_str);
            let target_path = binding
                .and_then(|value| value.get("target_path"))
                .and_then(serde_json::Value::as_str);
            let selected_family = binding
                .and_then(|value| value.get("selected_family"))
                .and_then(serde_json::Value::as_str);
            let expected_target =
                format!("partitioned_survival.strategies.{strategy_id}.{endpoint}");
            if !valid_sha(binding.and_then(|value| value.get("content_sha256")))
                || !path.is_some_and(safe_relative_path)
                || target_path != Some(expected_target.as_str())
                || !selected_family.is_some_and(|value| !value.trim().is_empty())
            {
                audit.errors.push(format!(
                    "{strategy_id}.{endpoint} curve review binding is invalid"
                ));
            } else if let (Some(path), Some(digest), Some(target_path), Some(selected_family)) =
                (path, digest, target_path, selected_family)
            {
                match crate::heor_uncertainty::read_workspace_capped(workspace, path) {
                    Ok(raw) if sha256(&raw) == digest => {
                        match serde_json::from_slice::<serde_json::Value>(&raw) {
                            Ok(review) => {
                                let review_audit =
                                    crate::heor_survival_review::audit_survival_review_value(
                                        workspace,
                                        plan,
                                        &review,
                                        digest.to_string(),
                                        target_path,
                                        selected_family,
                                    );
                                let expected_endpoint = endpoint.to_ascii_uppercase();
                                if review
                                    .pointer("/context/endpoint")
                                    .and_then(serde_json::Value::as_str)
                                    != Some(expected_endpoint.as_str())
                                {
                                    audit.errors.push(format!(
                                        "{strategy_id}.{endpoint} curve review endpoint does not match"
                                    ));
                                }
                                if review
                                    .pointer("/context/time_origin")
                                    .and_then(serde_json::Value::as_str)
                                    != psm.get("time_origin").and_then(serde_json::Value::as_str)
                                    || review
                                        .pointer("/context/time_unit")
                                        .and_then(serde_json::Value::as_str)
                                        != Some("years")
                                {
                                    audit.errors.push(format!(
                                        "{strategy_id}.{endpoint} curve review time basis does not match"
                                    ));
                                }
                                if !review_audit.complete {
                                    audit.errors.extend(review_audit.errors.into_iter().map(
                                        |error| {
                                            format!(
                                                "{strategy_id}.{endpoint} curve review: {error}"
                                            )
                                        },
                                    ));
                                }
                            }
                            Err(error) => audit.errors.push(format!(
                                "{strategy_id}.{endpoint} curve review is invalid JSON: {error}"
                            )),
                        }
                        audit
                            .artifact_bindings
                            .push(crate::heor_approval::ArtifactBinding {
                                path: path.to_string(),
                                sha256: digest.to_string(),
                            });
                    }
                    Ok(_) => audit.errors.push(format!(
                        "{strategy_id}.{endpoint} curve review hash does not match bytes"
                    )),
                    Err(error) => audit.errors.push(error),
                }
            }
        }
        if endpoint_values.len() == 2 && endpoint_values[0].len() == endpoint_values[1].len() {
            for (index, (pfs, overall)) in endpoint_values[0]
                .iter()
                .zip(&endpoint_values[1])
                .enumerate()
            {
                if pfs > &(overall + TOLERANCE) {
                    audit
                        .errors
                        .push(format!("{strategy_id} PFS exceeds OS at endpoint {index}"));
                }
            }
        }
    }
    for field in ["face", "internal", "external"] {
        if string_set(psm.pointer(&format!("/validation_plan/{field}"))).is_none() {
            audit
                .errors
                .push(format!("validation_plan.{field} is required"));
        }
    }
    if string_set(psm.get("limitations")).is_none() {
        audit.errors.push("limitations are required".into());
    }
    let materialization_audit =
        crate::heor_survival_materialization::audit_survival_materializations(
            workspace, plan, plan_raw, psm,
        );
    audit.survival_curve_materializations_sha256 = materialization_audit.sha256;
    audit
        .artifact_bindings
        .extend(materialization_audit.artifact_bindings);
    if !materialization_audit.complete {
        audit.errors.extend(
            materialization_audit
                .errors
                .into_iter()
                .map(|error| format!("survival materialization: {error}")),
        );
    }
    let authority = String::from_utf8_lossy(psm_raw).to_ascii_lowercase();
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
            .push("partitioned survival plan contains a forbidden authority field".into());
    }
    audit
        .artifact_bindings
        .push(crate::heor_approval::ArtifactBinding {
            path: PARTITIONED_SURVIVAL_PLAN_PATH.into(),
            sha256: audit.partitioned_survival_sha256.clone(),
        });
    audit
        .artifact_bindings
        .sort_by(|left, right| left.path.cmp(&right.path));
    audit
        .artifact_bindings
        .dedup_by(|left, right| left.path == right.path && left.sha256 == right.sha256);
    audit.complete = audit.errors.is_empty();
    audit.status = if audit.complete {
        "complete"
    } else {
        "incomplete"
    };
    audit
}

pub fn audit_partitioned_survival_for_plan(
    workspace: &Path,
    plan_raw: &[u8],
) -> Result<PartitionedSurvivalAudit, String> {
    let plan: serde_json::Value = serde_json::from_slice(plan_raw)
        .map_err(|error| format!("partitioned survival audit failed: {error}"))?;
    let link = plan.get("partitioned_survival_analysis");
    if link.is_none() {
        return Ok(empty_audit(plan_raw, false));
    }
    if plan
        .pointer("/partitioned_survival_analysis/path")
        .and_then(serde_json::Value::as_str)
        != Some(PARTITIONED_SURVIVAL_PLAN_PATH)
    {
        let mut audit = empty_audit(plan_raw, true);
        audit.errors.push(format!(
            "analysis plan must link {PARTITIONED_SURVIVAL_PLAN_PATH}"
        ));
        return Ok(audit);
    }
    let psm_raw = match crate::heor_uncertainty::read_workspace_capped(
        workspace,
        PARTITIONED_SURVIVAL_PLAN_PATH,
    ) {
        Ok(raw) => raw,
        Err(error) => {
            let mut audit = empty_audit(plan_raw, true);
            audit.errors.push(error);
            return Ok(audit);
        }
    };
    let psm: serde_json::Value = serde_json::from_slice(&psm_raw)
        .map_err(|error| format!("partitioned survival plan is invalid: {error}"))?;
    Ok(audit_values(workspace, &plan, plan_raw, &psm, &psm_raw))
}

pub fn require_partitioned_survival_approvable(
    workspace: &Path,
    plan_raw: &[u8],
) -> Result<PartitionedSurvivalAudit, String> {
    let audit = audit_partitioned_survival_for_plan(workspace, plan_raw)?;
    if !audit.required || !audit.complete {
        return Err(format!(
            "partitioned survival audit is not approvable: required={}, {} errors",
            audit.required,
            audit.errors.len()
        ));
    }
    Ok(audit)
}

#[tauri::command(async)]
pub fn audit_heor_partitioned_survival(app: AppHandle) -> Result<PartitionedSurvivalAudit, String> {
    let workspace = crate::runtime::workspace_dir(&app)?;
    let plan_raw = crate::heor_uncertainty::read_workspace_capped(&workspace, ANALYSIS_PLAN_PATH)?;
    audit_partitioned_survival_for_plan(&workspace, &plan_raw)
}

#[tauri::command(async)]
pub fn run_heor_partitioned_survival(
    app: AppHandle,
    approval_state: tauri::State<crate::heor_approval::HeorApprovalState>,
    project_id: String,
) -> Result<PartitionedSurvivalRunResult, String> {
    let workspace = crate::runtime::workspace_dir(&app)?;
    if crate::project::require_project_id(&workspace)? != project_id {
        return Err("HEOR projectId does not match the current project".into());
    }
    let plan_path = workspace.join(ANALYSIS_PLAN_PATH);
    let psm_path = workspace.join(PARTITIONED_SURVIVAL_PLAN_PATH);
    let materializations_path =
        workspace.join(crate::heor_survival_materialization::SURVIVAL_MATERIALIZATION_PATH);
    let plan_raw = crate::heor_uncertainty::read_workspace_capped(&workspace, ANALYSIS_PLAN_PATH)?;
    let audit = require_partitioned_survival_approvable(&workspace, &plan_raw)?;

    let package_src = app
        .path()
        .resolve("heor-core/src", BaseDirectory::Resource)
        .map_err(|error| format!("bundled HEOR engine unavailable: {error}"))?;
    let (python, _) = crate::kernel::python_bin(&app)?;
    let output = crate::runtime::quiet_command(python)
        .args(["-m", "heor_core"])
        .arg(&plan_path)
        .arg("--partitioned-survival-plan")
        .arg(&psm_path)
        .arg("--survival-curve-materializations")
        .arg(&materializations_path)
        .current_dir(&workspace)
        .env("PYTHONPATH", &package_src)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("PYTHONNOUSERSITE", "1")
        .output()
        .map_err(|error| format!("partitioned survival engine failed to start: {error}"))?;
    if !output.status.success() {
        let message = String::from_utf8_lossy(&output.stderr[..output.stderr.len().min(4_000)])
            .trim()
            .to_string();
        return Err(if message.is_empty() {
            format!("partitioned survival engine exited with {}", output.status)
        } else {
            message
        });
    }
    if output.stdout.len() > OUTPUT_CAP_BYTES {
        return Err("partitioned survival output exceeds the 25 MB limit".into());
    }
    let calculation: serde_json::Value = serde_json::from_slice(&output.stdout)
        .map_err(|error| format!("partitioned survival engine returned invalid JSON: {error}"))?;
    if calculation
        .get("analysis_plan_sha256")
        .and_then(serde_json::Value::as_str)
        != Some(audit.analysis_plan_sha256.as_str())
        || calculation
            .get("partitioned_survival_plan_sha256")
            .and_then(serde_json::Value::as_str)
            != Some(audit.partitioned_survival_sha256.as_str())
        || calculation
            .get("survival_curve_materializations_sha256")
            .and_then(serde_json::Value::as_str)
            != Some(audit.survival_curve_materializations_sha256.as_str())
    {
        return Err("partitioned survival engine hashes do not match audited inputs".into());
    }
    crate::heor_reporting::write_result(
        &workspace,
        PARTITIONED_SURVIVAL_RESULT_PATH,
        &output.stdout,
    )?;

    let plan: serde_json::Value = serde_json::from_slice(&plan_raw)
        .map_err(|error| format!("analysis plan is invalid: {error}"))?;
    let reference_case_id = plan
        .pointer("/reference_case/id")
        .and_then(serde_json::Value::as_str)
        .ok_or("analysis plan omitted reference-case id")?;
    let claimed_status = plan
        .pointer("/reference_case/status")
        .and_then(serde_json::Value::as_str)
        .ok_or("analysis plan omitted reference-case status")?;
    let reference_case_status = crate::heor_engine::registered_reference_case_status(
        &app,
        reference_case_id,
        claimed_status,
    )?;
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
        audit.analysis_plan_sha256.clone(),
        conceptual_model_matches_artifact,
        &reference_case_status,
        crate::heor_engine::HeorWorkflowAudits {
            evidence: crate::heor_evidence::audit_plan_bytes(&plan_raw)?,
            evidence_selection: crate::heor_evidence::audit_evidence_selection_for_plan(
                &app,
                &workspace,
                &project_id,
                &plan_raw,
            ),
            reference_case: crate::heor_reference_case::audit_reference_case_for_plan(
                &app, &workspace, &plan_raw,
            )?,
            uncertainty: crate::heor_uncertainty::audit_uncertainty_plan_for_plan(
                &workspace, &plan_raw,
            )?,
            budget_impact: crate::heor_budget_impact::audit_budget_impact_for_plan(
                &workspace, &plan_raw,
            )?,
            partitioned_survival: audit,
            survival_review: crate::heor_survival_review::audit_survival_review_for_plan(
                &workspace, &plan_raw,
            ),
            validation: crate::heor_validation::audit_model_validation_for_plan(
                &workspace, &plan_raw,
            )?,
            reporting: crate::heor_reporting::audit_report_package(&workspace)?,
        },
    );
    Ok(PartitionedSurvivalRunResult {
        workflow,
        calculation,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unlinked_partitioned_survival_is_not_required() {
        let root = std::env::temp_dir();
        let raw = br#"{"analysis_id":"a"}"#;
        let audit = audit_partitioned_survival_for_plan(&root, raw).unwrap();
        assert!(!audit.required);
        assert!(audit.complete);
        assert_eq!(audit.status, "not_required");
    }

    #[test]
    fn wrong_link_fails_closed() {
        let root = std::env::temp_dir();
        let raw = br#"{"analysis_id":"a","partitioned_survival_analysis":{"path":"wrong.json"}}"#;
        let audit = audit_partitioned_survival_for_plan(&root, raw).unwrap();
        assert!(audit.required);
        assert!(!audit.complete);
        assert_eq!(audit.errors.len(), 1);
    }
}
