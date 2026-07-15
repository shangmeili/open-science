// Desktop bridge for the deterministic HEOR engine. The Python process only
// calculates; this app layer independently verifies the input hash and applies
// workflow state from the app-owned approval chain.
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};
use tauri::{path::BaseDirectory, AppHandle, Manager};

use crate::heor_approval::{
    ApprovalAction, ApprovalEvent, ApprovalGate, ApprovalLog, HeorApprovalState,
};
use crate::heor_budget_impact::{audit_budget_impact_for_plan, BudgetImpactAudit};
use crate::heor_evidence::{
    audit_evidence_selection_for_plan, audit_plan_bytes, EvidenceAudit, EvidenceSelectionAudit,
};
use crate::heor_partitioned_survival::{
    audit_partitioned_survival_for_plan, PartitionedSurvivalAudit,
};
use crate::heor_reference_case::{audit_reference_case_for_plan, ReferenceCaseAudit};
use crate::heor_reporting::{audit_report_package, ReportingAudit};
use crate::heor_survival_review::{audit_survival_review_for_plan, SurvivalReviewAudit};
use crate::heor_uncertainty::{audit_uncertainty_plan_for_plan, UncertaintyAudit};
use crate::heor_validation::{audit_model_validation_for_plan, ModelValidationAudit};
use crate::runtime::workspace_dir;

const INPUT_CAP_BYTES: u64 = 5 * 1024 * 1024;

#[derive(Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HeorWorkflowStatus {
    classification: &'static str,
    decision_ready: bool,
    effective_approved_gates: Vec<ApprovalGate>,
    input_sha256: String,
    analysis_plan_matches_input: bool,
    conceptual_model_matches_artifact: bool,
    reference_case_registry_status: String,
    reference_case_audit: ReferenceCaseAudit,
    uncertainty_plan_matches_approval: bool,
    uncertainty_audit: UncertaintyAudit,
    budget_impact_plan_matches_approval: bool,
    budget_impact_audit: BudgetImpactAudit,
    partitioned_survival_matches_approval: bool,
    partitioned_survival_audit: PartitionedSurvivalAudit,
    survival_review_matches_approval: bool,
    survival_review_audit: SurvivalReviewAudit,
    independent_validation_matches_approval: bool,
    validation_audit: ModelValidationAudit,
    release_matches_approval: bool,
    reporting_audit: ReportingAudit,
    approval_chain_head: Option<String>,
    approval_integrity: &'static str,
    identity_assurance: &'static str,
    evidence_audit: EvidenceAudit,
    evidence_selection_audit: EvidenceSelectionAudit,
    evidence_synthesis_matches_approval: bool,
}

#[derive(Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HeorRunResult {
    calculation: serde_json::Value,
    workflow: HeorWorkflowStatus,
}

pub(crate) struct HeorWorkflowAudits {
    pub evidence: EvidenceAudit,
    pub evidence_selection: EvidenceSelectionAudit,
    pub reference_case: ReferenceCaseAudit,
    pub uncertainty: UncertaintyAudit,
    pub budget_impact: BudgetImpactAudit,
    pub partitioned_survival: PartitionedSurvivalAudit,
    pub survival_review: SurvivalReviewAudit,
    pub validation: ModelValidationAudit,
    pub reporting: ReportingAudit,
}

fn resolve_workspace_input(root: &Path, value: &str) -> Result<PathBuf, String> {
    if value.trim().is_empty() {
        return Err("inputPath must not be empty".into());
    }
    let candidate = Path::new(value);
    let joined = if candidate.is_absolute() {
        candidate.to_path_buf()
    } else {
        root.join(candidate)
    };
    let root = root
        .canonicalize()
        .map_err(|e| format!("workspace unavailable: {e}"))?;
    let input = joined
        .canonicalize()
        .map_err(|e| format!("HEOR input unavailable: {e}"))?;
    if !input.starts_with(&root) || !input.is_file() {
        return Err("HEOR input must be a file inside the current workspace".into());
    }
    let size = input
        .metadata()
        .map_err(|e| format!("HEOR input metadata failed: {e}"))?
        .len();
    if size > INPUT_CAP_BYTES {
        return Err(format!(
            "HEOR input exceeds the {} MB limit",
            INPUT_CAP_BYTES / 1024 / 1024
        ));
    }
    Ok(input)
}

fn sha256_bytes(value: &[u8]) -> String {
    format!("{:x}", Sha256::digest(value))
}

fn validate_reference_case_profile(
    profile: &serde_json::Value,
    expected_id: &str,
    claimed_status: &str,
) -> Result<String, String> {
    let profile_id = profile
        .get("id")
        .and_then(serde_json::Value::as_str)
        .ok_or("reference-case profile omitted id")?;
    let status = profile
        .get("status")
        .and_then(serde_json::Value::as_str)
        .ok_or("reference-case profile omitted status")?;
    if profile_id != expected_id {
        return Err("reference-case profile id does not match the analysis".into());
    }
    if !matches!(status, "current" | "draft") {
        return Err("reference-case registry status must be current or draft".into());
    }
    if status != claimed_status {
        return Err(format!(
            "analysis reference-case status {claimed_status:?} conflicts with registered status {status:?}"
        ));
    }
    Ok(status.to_string())
}

pub(crate) fn registered_reference_case_status(
    app: &AppHandle,
    id: &str,
    claimed_status: &str,
) -> Result<String, String> {
    if id.is_empty()
        || id.len() > 80
        || !id
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
    {
        return Err("invalid reference-case id".into());
    }
    let profile_path = app
        .path()
        .resolve(
            format!("reference-cases/{id}.json"),
            BaseDirectory::Resource,
        )
        .map_err(|e| format!("registered reference case unavailable: {e}"))?;
    let raw = std::fs::read(&profile_path)
        .map_err(|e| format!("registered reference case unavailable: {e}"))?;
    let profile: serde_json::Value = serde_json::from_slice(&raw)
        .map_err(|e| format!("registered reference case is invalid: {e}"))?;
    validate_reference_case_profile(&profile, id, claimed_status)
}

fn analysis_plan_event(log: &ApprovalLog) -> Option<&ApprovalEvent> {
    if !log
        .effective_approved_gates
        .contains(&ApprovalGate::AnalysisPlan)
    {
        return None;
    }
    log.events.iter().rev().find(|event| {
        event.gate == ApprovalGate::AnalysisPlan && event.action == ApprovalAction::Approve
    })
}

pub(crate) fn workflow_status(
    log: ApprovalLog,
    input_sha256: String,
    conceptual_model_matches_artifact: bool,
    reference_case_status: &str,
    audits: HeorWorkflowAudits,
) -> HeorWorkflowStatus {
    let HeorWorkflowAudits {
        evidence: evidence_audit,
        evidence_selection: evidence_selection_audit,
        reference_case: reference_case_audit,
        uncertainty: uncertainty_audit,
        budget_impact: budget_impact_audit,
        partitioned_survival: partitioned_survival_audit,
        survival_review: survival_review_audit,
        validation: validation_audit,
        reporting: reporting_audit,
    } = audits;
    let plan_matches =
        analysis_plan_event(&log).is_some_and(|event| event.artifact_sha256 == input_sha256);
    let uncertainty_plan_matches_approval = analysis_plan_event(&log).is_some_and(|event| {
        crate::heor_approval::event_binds_artifact(
            event,
            crate::heor_uncertainty::UNCERTAINTY_PLAN_PATH,
            &uncertainty_audit.uncertainty_sha256,
        )
    });
    let budget_impact_plan_matches_approval = analysis_plan_event(&log).is_some_and(|event| {
        crate::heor_approval::event_binds_artifact(
            event,
            crate::heor_budget_impact::BUDGET_IMPACT_PLAN_PATH,
            &budget_impact_audit.budget_impact_sha256,
        )
    });
    let partitioned_survival_matches_approval = !partitioned_survival_audit.required
        || (partitioned_survival_audit.complete
            && !partitioned_survival_audit.artifact_bindings.is_empty()
            && analysis_plan_event(&log).is_some_and(|event| {
                partitioned_survival_audit
                    .artifact_bindings
                    .iter()
                    .all(|binding| {
                        crate::heor_approval::event_binds_artifact(
                            event,
                            &binding.path,
                            &binding.sha256,
                        )
                    })
            }));
    let survival_review_matches_approval = !survival_review_audit.required
        || (survival_review_audit.complete
            && !survival_review_audit.artifact_bindings.is_empty()
            && analysis_plan_event(&log).is_some_and(|event| {
                survival_review_audit
                    .artifact_bindings
                    .iter()
                    .all(|binding| {
                        crate::heor_approval::event_binds_artifact(
                            event,
                            &binding.path,
                            &binding.sha256,
                        )
                    })
            }));
    let evidence_synthesis_matches_approval = evidence_selection_audit.synthesis_sha256.is_empty()
        || analysis_plan_event(&log).is_some_and(|event| {
            crate::heor_approval::event_binds_artifact(
                event,
                crate::heor_synthesis::EVIDENCE_SYNTHESIS_PATH,
                &evidence_selection_audit.synthesis_sha256,
            )
        });
    let independent_validation_matches_approval = log
        .effective_approved_gates
        .contains(&ApprovalGate::IndependentValidation)
        && log
            .events
            .iter()
            .rev()
            .find(|event| event.gate == ApprovalGate::IndependentValidation)
            .is_some_and(|event| {
                event.action == ApprovalAction::Approve
                    && event.artifact_sha256 == validation_audit.validation_sha256
                    && event.actor_label == validation_audit.reviewer_label
                    && validation_audit.complete
                    && validation_audit.approvable
                    && crate::heor_validation::analysis_plan_approval_is_current(
                        &log,
                        &validation_audit,
                    )
                    && crate::heor_validation::approval_bindings(&validation_audit)
                        .iter()
                        .all(|binding| {
                            crate::heor_approval::event_binds_artifact(
                                event,
                                &binding.path,
                                &binding.sha256,
                            )
                        })
            });
    let release_matches_approval = independent_validation_matches_approval
        && !partitioned_survival_audit.required
        && crate::heor_reporting::release_matches_approval(&log, &reporting_audit);
    let locally_authorized = plan_matches
        && conceptual_model_matches_artifact
        && evidence_audit.complete
        && evidence_selection_audit.complete
        && evidence_synthesis_matches_approval
        && reference_case_audit.complete
        && uncertainty_audit.complete
        && uncertainty_plan_matches_approval
        && budget_impact_audit.complete
        && budget_impact_plan_matches_approval
        && partitioned_survival_audit.complete
        && partitioned_survival_matches_approval
        && survival_review_audit.complete
        && survival_review_matches_approval
        && reference_case_status != "draft";
    let mut effective_approved_gates = log.effective_approved_gates;
    if !conceptual_model_matches_artifact {
        effective_approved_gates = effective_approved_gates
            .into_iter()
            .take_while(|gate| *gate != ApprovalGate::ConceptualModel)
            .collect();
    } else if !evidence_audit.complete
        || !evidence_selection_audit.complete
        || !evidence_synthesis_matches_approval
        || !reference_case_audit.complete
        || !uncertainty_audit.complete
        || !uncertainty_plan_matches_approval
        || !budget_impact_audit.complete
        || !budget_impact_plan_matches_approval
        || !partitioned_survival_audit.complete
        || !partitioned_survival_matches_approval
        || !survival_review_audit.complete
        || !survival_review_matches_approval
    {
        effective_approved_gates = effective_approved_gates
            .into_iter()
            .take_while(|gate| *gate != ApprovalGate::AnalysisPlan)
            .collect();
    }
    if !independent_validation_matches_approval {
        effective_approved_gates.retain(|gate| {
            !matches!(
                gate,
                ApprovalGate::IndependentValidation | ApprovalGate::Release
            )
        });
    }
    if !release_matches_approval {
        effective_approved_gates.retain(|gate| *gate != ApprovalGate::Release);
    }
    let decision_ready = locally_authorized
        && independent_validation_matches_approval
        && release_matches_approval
        && reporting_audit.releasable;
    HeorWorkflowStatus {
        classification: if decision_ready {
            "decision_ready_local_release_assertion"
        } else if locally_authorized {
            "analysis_authorized_local_assertion"
        } else {
            "exploratory"
        },
        decision_ready,
        effective_approved_gates,
        input_sha256,
        analysis_plan_matches_input: plan_matches,
        conceptual_model_matches_artifact,
        reference_case_registry_status: reference_case_status.to_string(),
        reference_case_audit,
        uncertainty_plan_matches_approval,
        uncertainty_audit,
        budget_impact_plan_matches_approval,
        budget_impact_audit,
        partitioned_survival_matches_approval,
        partitioned_survival_audit,
        survival_review_matches_approval,
        survival_review_audit,
        independent_validation_matches_approval,
        validation_audit,
        release_matches_approval,
        reporting_audit,
        approval_chain_head: log.chain_head,
        approval_integrity: log.integrity,
        identity_assurance: log.identity_assurance,
        evidence_audit,
        evidence_selection_audit,
        evidence_synthesis_matches_approval,
    }
}

pub(crate) fn conceptual_model_matches_approval(
    workspace: &Path,
    approval_log: &ApprovalLog,
) -> bool {
    crate::heor_artifacts::current_conceptual_model_hash_and_audit(workspace)
        .ok()
        .filter(|(_, audit)| audit.complete)
        .is_some_and(|(hash, _)| {
            approval_log
                .effective_approved_gates
                .contains(&ApprovalGate::ConceptualModel)
                && approval_log.events.iter().rev().any(|event| {
                    event.gate == ApprovalGate::ConceptualModel
                        && event.action == ApprovalAction::Approve
                        && event.artifact_sha256 == hash
                })
        })
}

fn capped_stderr(bytes: &[u8]) -> String {
    String::from_utf8_lossy(&bytes[..bytes.len().min(4_000)])
        .trim()
        .to_string()
}

#[tauri::command(async)]
pub fn run_heor_markov(
    app: AppHandle,
    approval_state: tauri::State<HeorApprovalState>,
    project_id: String,
    input_path: String,
) -> Result<HeorRunResult, String> {
    let root = workspace_dir(&app)?;
    if crate::project::require_project_id(&root)? != project_id {
        return Err("HEOR projectId does not match the current project".into());
    }
    let input = resolve_workspace_input(&root, &input_path)?;
    let raw = std::fs::read(&input).map_err(|e| format!("HEOR input read failed: {e}"))?;
    let input_sha256 = sha256_bytes(&raw);
    let evidence_audit = audit_plan_bytes(&raw)?;
    let evidence_selection_audit =
        audit_evidence_selection_for_plan(&app, &root, &project_id, &raw);

    let package_src = app
        .path()
        .resolve("heor-core/src", BaseDirectory::Resource)
        .map_err(|e| format!("bundled HEOR engine unavailable: {e}"))?;
    if !package_src.join("heor_core").is_dir() {
        return Err("bundled HEOR engine source is missing".into());
    }
    let (python, _) = crate::kernel::python_bin(&app)?;
    let output = crate::runtime::quiet_command(python)
        .args(["-m", "heor_core"])
        .arg(&input)
        .current_dir(&root)
        .env("PYTHONPATH", &package_src)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("PYTHONNOUSERSITE", "1")
        .output()
        .map_err(|e| format!("HEOR engine failed to start: {e}"))?;
    if !output.status.success() {
        let message = capped_stderr(&output.stderr);
        return Err(if message.is_empty() {
            format!("HEOR engine exited with {}", output.status)
        } else {
            message
        });
    }
    if output.stdout.len() > 25 * 1024 * 1024 {
        return Err("HEOR engine output exceeds the 25 MB limit".into());
    }
    let calculation: serde_json::Value = serde_json::from_slice(&output.stdout)
        .map_err(|e| format!("HEOR engine returned invalid JSON: {e}"))?;
    let child_hash = calculation
        .get("input_sha256")
        .and_then(serde_json::Value::as_str)
        .ok_or("HEOR engine omitted input_sha256")?;
    if child_hash != input_sha256 {
        return Err("HEOR engine input hash does not match the desktop input".into());
    }
    crate::heor_reporting::write_result(
        &root,
        crate::heor_reporting::BASE_CASE_RESULT_PATH,
        &output.stdout,
    )?;
    let reference_case_status = calculation
        .pointer("/reference_case/status")
        .and_then(serde_json::Value::as_str)
        .ok_or("HEOR engine omitted reference-case status")?;
    let reference_case_id = calculation
        .pointer("/reference_case/id")
        .and_then(serde_json::Value::as_str)
        .ok_or("HEOR engine omitted reference-case id")?;
    let reference_case_status =
        registered_reference_case_status(&app, reference_case_id, reference_case_status)?;
    let reference_case_audit = audit_reference_case_for_plan(&app, &root, &raw)?;
    let uncertainty_audit = audit_uncertainty_plan_for_plan(&root, &raw)?;
    let budget_impact_audit = audit_budget_impact_for_plan(&root, &raw)?;
    let partitioned_survival_audit = audit_partitioned_survival_for_plan(&root, &raw)?;
    let survival_review_audit = audit_survival_review_for_plan(&root, &raw);
    let validation_audit = audit_model_validation_for_plan(&root, &raw)?;
    let reporting_audit = audit_report_package(&root)?;
    // Evaluate authorization after calculation so a revocation made while the
    // engine is running cannot leave the returned status stale.
    let approval_log = {
        let _guard = approval_state
            .0
            .lock()
            .map_err(|_| "HEOR approval lock poisoned")?;
        crate::heor_approval::verified_log(&app, &project_id)?
    };
    let conceptual_model_matches_artifact = conceptual_model_matches_approval(&root, &approval_log);

    Ok(HeorRunResult {
        workflow: workflow_status(
            approval_log,
            input_sha256,
            conceptual_model_matches_artifact,
            &reference_case_status,
            HeorWorkflowAudits {
                evidence: evidence_audit,
                evidence_selection: evidence_selection_audit,
                reference_case: reference_case_audit,
                uncertainty: uncertainty_audit,
                budget_impact: budget_impact_audit,
                partitioned_survival: partitioned_survival_audit,
                survival_review: survival_review_audit,
                validation: validation_audit,
                reporting: reporting_audit,
            },
        ),
        calculation,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn approval_event(sequence: u64, gate: ApprovalGate, hash: &str) -> ApprovalEvent {
        ApprovalEvent {
            schema_version: 1,
            sequence,
            event_id: format!("{sequence:032x}"),
            project_id: "project-1".into(),
            gate,
            action: ApprovalAction::Approve,
            artifact_sha256: hash.into(),
            related_artifacts: Vec::new(),
            actor_label: "Reviewer".into(),
            rationale: "Reviewed".into(),
            timestamp: 1_700_000_000 + sequence,
            assurance: "local_human_assertion".into(),
            previous_hash: None,
            event_hash: "f".repeat(64),
        }
    }

    fn approved_log(input_hash: &str) -> ApprovalLog {
        let mut analysis_plan = approval_event(3, ApprovalGate::AnalysisPlan, input_hash);
        analysis_plan.schema_version = 2;
        analysis_plan.related_artifacts = vec![
            crate::heor_approval::ArtifactBinding {
                path: crate::heor_uncertainty::UNCERTAINTY_PLAN_PATH.into(),
                sha256: "f".repeat(64),
            },
            crate::heor_approval::ArtifactBinding {
                path: crate::heor_budget_impact::BUDGET_IMPACT_PLAN_PATH.into(),
                sha256: "9".repeat(64),
            },
            crate::heor_approval::ArtifactBinding {
                path: crate::heor_synthesis::EVIDENCE_SYNTHESIS_PATH.into(),
                sha256: "7".repeat(64),
            },
        ];
        ApprovalLog {
            events: vec![
                approval_event(1, ApprovalGate::DecisionProblem, &"a".repeat(64)),
                approval_event(2, ApprovalGate::ConceptualModel, &"b".repeat(64)),
                analysis_plan,
            ],
            effective_approved_gates: vec![
                ApprovalGate::DecisionProblem,
                ApprovalGate::ConceptualModel,
                ApprovalGate::AnalysisPlan,
            ],
            chain_head: Some("f".repeat(64)),
            integrity: "verified_unanchored_sha256_chain",
            identity_assurance: "local_human_assertion",
        }
    }

    fn validated_log(input_hash: &str) -> ApprovalLog {
        let mut log = approved_log(input_hash);
        let audit = complete_validation_audit();
        let mut validation = approval_event(
            4,
            ApprovalGate::IndependentValidation,
            &audit.validation_sha256,
        );
        validation.schema_version = 2;
        validation.actor_label = audit.reviewer_label.clone();
        validation.related_artifacts = crate::heor_validation::approval_bindings(&audit);
        log.events.push(validation);
        log.effective_approved_gates
            .push(ApprovalGate::IndependentValidation);
        log
    }

    fn complete_audit() -> EvidenceAudit {
        EvidenceAudit {
            complete: true,
            status: "complete",
            required_inputs: 12,
            covered_inputs: 12,
            unsupported_inputs: Vec::new(),
            invalid_mappings: Vec::new(),
            unresolved_assumptions: Vec::new(),
            source_count: 1,
            mapping_count: 12,
            source_based_inputs: 12,
            selected_extraction_count: 12,
        }
    }

    fn complete_evidence_selection_audit() -> EvidenceSelectionAudit {
        EvidenceSelectionAudit {
            complete: true,
            status: "complete",
            synthesis_sha256: "7".repeat(64),
            selected_input_count: 12,
            selected_extraction_count: 12,
            verified_extraction_count: 12,
            unverified_extraction_ids: Vec::new(),
            rejected_extraction_ids: Vec::new(),
            invalid_selections: Vec::new(),
            errors: Vec::new(),
            verification_integrity: "verified_unanchored_sha256_chain",
        }
    }

    fn complete_reference_case_audit() -> ReferenceCaseAudit {
        ReferenceCaseAudit {
            complete: true,
            status: "complete",
            profile_id: "CN-2020-current".into(),
            profile_status: "current".into(),
            profile_revision: "T/CPHARMA 003-2020".into(),
            profile_sha256: "e".repeat(64),
            assessment_sha256: Some("f".repeat(64)),
            required_count: 13,
            met_required_count: 13,
            recommended_count: 1,
            met_recommended_count: 1,
            blocking_gaps: Vec::new(),
            recommended_gaps: Vec::new(),
            unresolved_requirements: Vec::new(),
            not_applicable_requirements: Vec::new(),
            not_applicable_required_count: 0,
            errors: Vec::new(),
        }
    }

    fn complete_uncertainty_audit() -> UncertaintyAudit {
        UncertaintyAudit {
            complete: true,
            status: "complete",
            uncertainty_id: "uncertainty-1".into(),
            analysis_id: "analysis-1".into(),
            analysis_plan_sha256: "c".repeat(64),
            uncertainty_sha256: "f".repeat(64),
            seed: Some("42".into()),
            parameter_count: 2,
            correlation_group_count: 0,
            scenario_count: 1,
            iterations: Some(1000),
            primary_threshold: Some(100000.0),
            threshold_count: 5,
            omitted_parameter_count: 0,
            joint_survival_required: false,
            joint_survival_manifest_sha256: None,
            joint_survival_draws_sha256: None,
            joint_survival_draw_count: None,
            invalid_parameters: Vec::new(),
            errors: Vec::new(),
        }
    }

    fn complete_budget_impact_audit() -> BudgetImpactAudit {
        BudgetImpactAudit {
            complete: true,
            status: "complete",
            bia_id: "bia-1".into(),
            analysis_id: "analysis-1".into(),
            analysis_plan_sha256: "c".repeat(64),
            budget_impact_sha256: "9".repeat(64),
            horizon_years: Some(3),
            population_year_count: 3,
            cost_category_count: 2,
            non_patient_cost_count: 1,
            sensitivity_parameter_count: 2,
            scenario_count: 1,
            required_input_count: 24,
            covered_input_count: 24,
            invalid_inputs: Vec::new(),
            errors: Vec::new(),
        }
    }

    fn complete_validation_audit() -> ModelValidationAudit {
        ModelValidationAudit {
            complete: true,
            approvable: true,
            status: "complete",
            validation_id: "validation-1".into(),
            analysis_id: "analysis-1".into(),
            validation_sha256: "8".repeat(64),
            analysis_plan_sha256: "c".repeat(64),
            conceptual_model_sha256: "b".repeat(64),
            uncertainty_plan_sha256: "f".repeat(64),
            budget_impact_plan_sha256: "9".repeat(64),
            reviewer_label: "Independent reviewer".into(),
            recommendation: "approve_for_intended_use".into(),
            evidence_count: 1,
            check_count: 18,
            required_coverage_count: 18,
            covered_requirement_count: 18,
            issue_count: 0,
            open_blocking_issue_count: 0,
            open_minor_issue_count: 0,
            invalid_evidence: Vec::new(),
            missing_coverage: Vec::new(),
            errors: Vec::new(),
        }
    }

    fn complete_reporting_audit() -> ReportingAudit {
        let binding_hashes = [
            ("report_document", "1"),
            ("analysis_plan", "c"),
            ("conceptual_model", "b"),
            ("uncertainty_plan", "f"),
            ("budget_impact_plan", "9"),
            ("model_validation", "8"),
            ("base_case_result", "2"),
            ("uncertainty_result", "3"),
            ("budget_impact_result", "4"),
        ]
        .into_iter()
        .map(|(key, marker)| (key.into(), marker.repeat(64)))
        .collect();
        ReportingAudit {
            complete: true,
            releasable: true,
            status: "complete",
            package_id: "report-1".into(),
            analysis_id: "analysis-1".into(),
            report_package_sha256: "7".repeat(64),
            release_owner_label: "Release owner".into(),
            binding_hashes,
            reporting_item_count: 40,
            required_item_count: 40,
            covered_item_count: 40,
            missing_items: Vec::new(),
            invalid_items: Vec::new(),
            errors: Vec::new(),
        }
    }

    fn complete_workflow_audits() -> HeorWorkflowAudits {
        HeorWorkflowAudits {
            evidence: complete_audit(),
            evidence_selection: complete_evidence_selection_audit(),
            reference_case: complete_reference_case_audit(),
            uncertainty: complete_uncertainty_audit(),
            budget_impact: complete_budget_impact_audit(),
            partitioned_survival: PartitionedSurvivalAudit {
                required: false,
                complete: true,
                status: "not_required",
                psm_id: String::new(),
                analysis_id: "analysis-1".into(),
                analysis_plan_sha256: "c".repeat(64),
                partitioned_survival_sha256: String::new(),
                survival_curve_materializations_sha256: String::new(),
                treatment_effect_duration_required: false,
                treatment_effect_duration_sha256: None,
                treatment_effect_duration_scenario_count: None,
                treatment_effect_duration_base_case_id: None,
                strategy_count: 0,
                curve_count: 0,
                time_point_count: 0,
                artifact_bindings: Vec::new(),
                errors: Vec::new(),
            },
            survival_review: SurvivalReviewAudit {
                complete: true,
                required: false,
                status: "not_required",
                review_sha256: None,
                target_count: 0,
                review_count: 0,
                analysis_id: "analysis-1".into(),
                target_path: None,
                selected_family: None,
                candidate_models: 0,
                converged_models: 0,
                failed_models: Vec::new(),
                scenario_count: 0,
                recommended_family: None,
                artifact_bindings: Vec::new(),
                targets: Vec::new(),
                blocking_gaps: Vec::new(),
                errors: Vec::new(),
            },
            validation: complete_validation_audit(),
            reporting: complete_reporting_audit(),
        }
    }

    #[test]
    fn authorization_requires_the_approved_analysis_plan_to_match_the_input() {
        let input_hash = "c".repeat(64);
        let authorized = workflow_status(
            approved_log(&input_hash),
            input_hash.clone(),
            true,
            "current",
            complete_workflow_audits(),
        );
        assert_eq!(
            authorized.classification,
            "analysis_authorized_local_assertion"
        );
        assert!(authorized.analysis_plan_matches_input);
        assert!(!authorized.decision_ready);

        let changed = workflow_status(
            approved_log(&input_hash),
            "d".repeat(64),
            true,
            "current",
            complete_workflow_audits(),
        );
        assert_eq!(changed.classification, "exploratory");
        assert!(!changed.analysis_plan_matches_input);
    }

    #[test]
    fn draft_reference_case_cannot_be_locally_authorized() {
        let input_hash = "c".repeat(64);
        let status = workflow_status(
            approved_log(&input_hash),
            input_hash,
            true,
            "draft",
            complete_workflow_audits(),
        );
        assert_eq!(status.classification, "exploratory");
        assert!(status.analysis_plan_matches_input);
    }

    #[test]
    fn incomplete_evidence_cannot_be_locally_authorized() {
        let input_hash = "c".repeat(64);
        let mut audit = complete_audit();
        audit.complete = false;
        audit.status = "incomplete";
        audit.covered_inputs = 11;
        audit.unsupported_inputs = vec!["cycles".into()];
        let status = workflow_status(
            approved_log(&input_hash),
            input_hash,
            true,
            "current",
            HeorWorkflowAudits {
                evidence: audit,
                ..complete_workflow_audits()
            },
        );
        assert_eq!(status.classification, "exploratory");
        assert!(!status.evidence_audit.complete);
        assert_eq!(
            status.effective_approved_gates,
            vec![ApprovalGate::DecisionProblem, ApprovalGate::ConceptualModel]
        );
    }

    #[test]
    fn unverified_or_changed_evidence_selection_invalidates_authorization() {
        let input_hash = "c".repeat(64);
        let mut unverified = complete_evidence_selection_audit();
        unverified.complete = false;
        unverified.status = "incomplete";
        unverified.verified_extraction_count = 11;
        unverified.unverified_extraction_ids = vec!["extract-12".into()];
        let status = workflow_status(
            approved_log(&input_hash),
            input_hash.clone(),
            true,
            "current",
            HeorWorkflowAudits {
                evidence_selection: unverified,
                ..complete_workflow_audits()
            },
        );
        assert_eq!(status.classification, "exploratory");
        assert!(!status.evidence_selection_audit.complete);

        let mut changed = complete_evidence_selection_audit();
        changed.synthesis_sha256 = "0".repeat(64);
        let status = workflow_status(
            approved_log(&input_hash),
            input_hash,
            true,
            "current",
            HeorWorkflowAudits {
                evidence_selection: changed,
                ..complete_workflow_audits()
            },
        );
        assert!(!status.evidence_synthesis_matches_approval);
        assert_eq!(status.classification, "exploratory");
    }

    #[test]
    fn changed_uncertainty_plan_invalidates_analysis_plan_authorization() {
        let input_hash = "c".repeat(64);
        let mut uncertainty = complete_uncertainty_audit();
        uncertainty.uncertainty_sha256 = "0".repeat(64);
        let status = workflow_status(
            approved_log(&input_hash),
            input_hash,
            true,
            "current",
            HeorWorkflowAudits {
                uncertainty,
                ..complete_workflow_audits()
            },
        );
        assert_eq!(status.classification, "exploratory");
        assert!(!status.uncertainty_plan_matches_approval);
        assert_eq!(
            status.effective_approved_gates,
            vec![ApprovalGate::DecisionProblem, ApprovalGate::ConceptualModel]
        );
    }

    #[test]
    fn changed_budget_impact_plan_invalidates_analysis_plan_authorization() {
        let input_hash = "c".repeat(64);
        let mut budget_impact = complete_budget_impact_audit();
        budget_impact.budget_impact_sha256 = "0".repeat(64);
        let status = workflow_status(
            approved_log(&input_hash),
            input_hash,
            true,
            "current",
            HeorWorkflowAudits {
                budget_impact,
                ..complete_workflow_audits()
            },
        );
        assert_eq!(status.classification, "exploratory");
        assert!(!status.budget_impact_plan_matches_approval);
        assert_eq!(
            status.effective_approved_gates,
            vec![ApprovalGate::DecisionProblem, ApprovalGate::ConceptualModel]
        );
    }

    #[test]
    fn required_survival_review_must_match_the_analysis_plan_approval() {
        let input_hash = "c".repeat(64);
        let digest = "8".repeat(64);
        let review_digest = "6".repeat(64);
        let mut audits = complete_workflow_audits();
        audits.survival_review.required = true;
        audits.survival_review.review_sha256 = Some(digest.clone());
        audits.survival_review.target_count = 2;
        audits.survival_review.review_count = 2;
        audits.survival_review.artifact_bindings = vec![
            crate::heor_approval::ArtifactBinding {
                path: crate::heor_survival_review::SURVIVAL_REVIEW_INDEX_PATH.into(),
                sha256: digest.clone(),
            },
            crate::heor_approval::ArtifactBinding {
                path: "heor/survival-extrapolation-reviews/review-0.json".into(),
                sha256: review_digest.clone(),
            },
        ];
        let status = workflow_status(
            approved_log(&input_hash),
            input_hash.clone(),
            true,
            "current",
            audits,
        );
        assert_eq!(status.classification, "exploratory");
        assert!(!status.survival_review_matches_approval);

        let mut log = approved_log(&input_hash);
        log.events
            .iter_mut()
            .find(|event| event.gate == ApprovalGate::AnalysisPlan)
            .unwrap()
            .related_artifacts
            .push(crate::heor_approval::ArtifactBinding {
                path: crate::heor_survival_review::SURVIVAL_REVIEW_INDEX_PATH.into(),
                sha256: digest.clone(),
            });
        log.events
            .iter_mut()
            .find(|event| event.gate == ApprovalGate::AnalysisPlan)
            .unwrap()
            .related_artifacts
            .push(crate::heor_approval::ArtifactBinding {
                path: "heor/survival-extrapolation-reviews/review-0.json".into(),
                sha256: review_digest.clone(),
            });
        let mut audits = complete_workflow_audits();
        audits.survival_review.required = true;
        audits.survival_review.review_sha256 = Some(digest);
        audits.survival_review.target_count = 2;
        audits.survival_review.review_count = 2;
        audits.survival_review.artifact_bindings = vec![
            crate::heor_approval::ArtifactBinding {
                path: crate::heor_survival_review::SURVIVAL_REVIEW_INDEX_PATH.into(),
                sha256: "8".repeat(64),
            },
            crate::heor_approval::ArtifactBinding {
                path: "heor/survival-extrapolation-reviews/review-0.json".into(),
                sha256: review_digest,
            },
        ];
        let status = workflow_status(log, input_hash, true, "current", audits);
        assert_eq!(status.classification, "analysis_authorized_local_assertion");
        assert!(status.survival_review_matches_approval);
    }

    #[test]
    fn changed_or_missing_conceptual_model_cannot_be_locally_authorized() {
        let input_hash = "c".repeat(64);
        let status = workflow_status(
            approved_log(&input_hash),
            input_hash,
            false,
            "current",
            complete_workflow_audits(),
        );
        assert_eq!(status.classification, "exploratory");
        assert!(!status.conceptual_model_matches_artifact);
        assert_eq!(
            status.effective_approved_gates,
            vec![ApprovalGate::DecisionProblem]
        );
    }

    #[test]
    fn independent_validation_requires_current_bindings_and_reviewer_identity() {
        let input_hash = "c".repeat(64);
        let valid = workflow_status(
            validated_log(&input_hash),
            input_hash.clone(),
            true,
            "current",
            complete_workflow_audits(),
        );
        assert!(valid.independent_validation_matches_approval);
        assert!(valid
            .effective_approved_gates
            .contains(&ApprovalGate::IndependentValidation));
        assert!(!valid.decision_ready);

        let mut stale_audits = complete_workflow_audits();
        stale_audits.validation.validation_sha256 = "0".repeat(64);
        let stale = workflow_status(
            validated_log(&input_hash),
            input_hash.clone(),
            true,
            "current",
            stale_audits,
        );
        assert!(!stale.independent_validation_matches_approval);
        assert_eq!(stale.classification, "analysis_authorized_local_assertion");
        assert!(!stale
            .effective_approved_gates
            .contains(&ApprovalGate::IndependentValidation));

        let mut wrong_reviewer_log = validated_log(&input_hash);
        wrong_reviewer_log.events.last_mut().unwrap().actor_label = "Another reviewer".into();
        let wrong_reviewer = workflow_status(
            wrong_reviewer_log,
            input_hash,
            true,
            "current",
            complete_workflow_audits(),
        );
        assert!(!wrong_reviewer.independent_validation_matches_approval);
    }

    #[test]
    fn analysis_cannot_self_promote_a_registered_draft_reference_case() {
        let profile = serde_json::json!({
            "id": "CN-2026-draft",
            "status": "draft"
        });
        assert_eq!(
            validate_reference_case_profile(&profile, "CN-2026-draft", "draft").unwrap(),
            "draft"
        );
        let error =
            validate_reference_case_profile(&profile, "CN-2026-draft", "current").unwrap_err();
        assert!(error.contains("conflicts with registered status"));
        assert!(validate_reference_case_profile(&profile, "another-id", "draft").is_err());
    }

    #[test]
    fn input_resolution_rejects_paths_outside_the_workspace() {
        let root = std::env::temp_dir().join(format!("heor-engine-{}", std::process::id()));
        let outside = std::env::temp_dir().join(format!("heor-outside-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let _ = std::fs::remove_file(&outside);
        std::fs::create_dir_all(&root).unwrap();
        std::fs::write(root.join("model.json"), "{}").unwrap();
        std::fs::write(&outside, "{}").unwrap();

        assert_eq!(
            resolve_workspace_input(&root, "model.json").unwrap(),
            root.join("model.json").canonicalize().unwrap()
        );
        assert!(resolve_workspace_input(&root, outside.to_str().unwrap()).is_err());

        let _ = std::fs::remove_dir_all(root);
        let _ = std::fs::remove_file(outside);
    }
}
