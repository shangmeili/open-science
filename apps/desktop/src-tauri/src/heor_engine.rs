// Desktop bridge for the deterministic HEOR engine. The Python process only
// calculates; this app layer independently verifies the input hash and applies
// workflow state from the app-owned approval chain.
use sha2::{Digest, Sha256};
use std::path::{Path, PathBuf};
use tauri::{path::BaseDirectory, AppHandle, Manager};

use crate::heor_approval::{
    ApprovalAction, ApprovalEvent, ApprovalGate, ApprovalLog, HeorApprovalState,
};
use crate::heor_evidence::{audit_plan_bytes, EvidenceAudit};
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
    approval_chain_head: Option<String>,
    approval_integrity: &'static str,
    identity_assurance: &'static str,
    evidence_audit: EvidenceAudit,
}

#[derive(Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct HeorRunResult {
    calculation: serde_json::Value,
    workflow: HeorWorkflowStatus,
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

fn registered_reference_case_status(
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

fn workflow_status(
    log: ApprovalLog,
    input_sha256: String,
    conceptual_model_matches_artifact: bool,
    reference_case_status: &str,
    evidence_audit: EvidenceAudit,
) -> HeorWorkflowStatus {
    let plan_matches =
        analysis_plan_event(&log).is_some_and(|event| event.artifact_sha256 == input_sha256);
    let locally_authorized = plan_matches
        && conceptual_model_matches_artifact
        && evidence_audit.complete
        && reference_case_status != "draft";
    let mut effective_approved_gates = log.effective_approved_gates;
    if !conceptual_model_matches_artifact {
        effective_approved_gates = effective_approved_gates
            .into_iter()
            .take_while(|gate| *gate != ApprovalGate::ConceptualModel)
            .collect();
    } else if !evidence_audit.complete {
        effective_approved_gates = effective_approved_gates
            .into_iter()
            .take_while(|gate| *gate != ApprovalGate::AnalysisPlan)
            .collect();
    }
    HeorWorkflowStatus {
        classification: if locally_authorized {
            "analysis_authorized_local_assertion"
        } else {
            "exploratory"
        },
        // Independent validation and release are separate later gates. This
        // bridge never promotes a calculation directly to decision-ready.
        decision_ready: false,
        effective_approved_gates,
        input_sha256,
        analysis_plan_matches_input: plan_matches,
        conceptual_model_matches_artifact,
        reference_case_registry_status: reference_case_status.to_string(),
        approval_chain_head: log.chain_head,
        approval_integrity: log.integrity,
        identity_assurance: log.identity_assurance,
        evidence_audit,
    }
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
    let calculation: serde_json::Value = serde_json::from_slice(&output.stdout)
        .map_err(|e| format!("HEOR engine returned invalid JSON: {e}"))?;
    let child_hash = calculation
        .get("input_sha256")
        .and_then(serde_json::Value::as_str)
        .ok_or("HEOR engine omitted input_sha256")?;
    if child_hash != input_sha256 {
        return Err("HEOR engine input hash does not match the desktop input".into());
    }
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
    // Evaluate authorization after calculation so a revocation made while the
    // engine is running cannot leave the returned status stale.
    let approval_log = {
        let _guard = approval_state
            .0
            .lock()
            .map_err(|_| "HEOR approval lock poisoned")?;
        crate::heor_approval::verified_log(&app, &project_id)?
    };
    let conceptual_model_matches_artifact =
        crate::heor_artifacts::current_conceptual_model_hash_and_audit(&root)
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
            });

    Ok(HeorRunResult {
        workflow: workflow_status(
            approval_log,
            input_sha256,
            conceptual_model_matches_artifact,
            &reference_case_status,
            evidence_audit,
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
            actor_label: "Reviewer".into(),
            rationale: "Reviewed".into(),
            timestamp: 1_700_000_000 + sequence,
            assurance: "local_human_assertion".into(),
            previous_hash: None,
            event_hash: "f".repeat(64),
        }
    }

    fn approved_log(input_hash: &str) -> ApprovalLog {
        ApprovalLog {
            events: vec![
                approval_event(1, ApprovalGate::DecisionProblem, &"a".repeat(64)),
                approval_event(2, ApprovalGate::ConceptualModel, &"b".repeat(64)),
                approval_event(3, ApprovalGate::AnalysisPlan, input_hash),
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
            complete_audit(),
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
            complete_audit(),
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
            complete_audit(),
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
            audit,
        );
        assert_eq!(status.classification, "exploratory");
        assert!(!status.evidence_audit.complete);
        assert_eq!(
            status.effective_approved_gates,
            vec![ApprovalGate::DecisionProblem, ApprovalGate::ConceptualModel]
        );
    }

    #[test]
    fn changed_or_missing_conceptual_model_cannot_be_locally_authorized() {
        let input_hash = "c".repeat(64);
        let status = workflow_status(
            approved_log(&input_hash),
            input_hash,
            false,
            "current",
            complete_audit(),
        );
        assert_eq!(status.classification, "exploratory");
        assert!(!status.conceptual_model_matches_artifact);
        assert_eq!(
            status.effective_approved_gates,
            vec![ApprovalGate::DecisionProblem]
        );
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
