// Human approval events for decision-relevant HEOR work. The canonical log is
// app-owned, outside the agent workspace, and every append extends a verified
// SHA-256 chain. The unanchored chain detects inconsistent or partial edits,
// not an adversary who can rewrite the full log. Actor identity remains a local
// assertion until OS-backed signing is implemented.
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager};

const SCHEMA_VERSION: u32 = 2;
const ASSURANCE: &str = "local_human_assertion";

#[derive(Default)]
pub struct HeorApprovalState(pub Mutex<()>);

#[derive(Clone, Copy, Debug, Eq, Hash, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ApprovalGate {
    DecisionProblem,
    ConceptualModel,
    AnalysisPlan,
    IndependentValidation,
    Release,
}

const GATES: [ApprovalGate; 5] = [
    ApprovalGate::DecisionProblem,
    ApprovalGate::ConceptualModel,
    ApprovalGate::AnalysisPlan,
    ApprovalGate::IndependentValidation,
    ApprovalGate::Release,
];

#[derive(Clone, Copy, Debug, Eq, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum ApprovalAction {
    Approve,
    Revoke,
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ApprovalRequest {
    pub project_id: String,
    pub gate: ApprovalGate,
    pub action: ApprovalAction,
    pub artifact_sha256: String,
    pub actor_label: String,
    pub rationale: String,
}

#[derive(Clone, Debug, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ArtifactBinding {
    pub path: String,
    pub sha256: String,
}

#[derive(Clone, Debug, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ApprovalEvent {
    pub schema_version: u32,
    pub sequence: u64,
    pub event_id: String,
    pub project_id: String,
    pub gate: ApprovalGate,
    pub action: ApprovalAction,
    pub artifact_sha256: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub related_artifacts: Vec<ArtifactBinding>,
    pub actor_label: String,
    pub rationale: String,
    pub timestamp: u64,
    pub assurance: String,
    pub previous_hash: Option<String>,
    pub event_hash: String,
}

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct HashPayloadV1<'a> {
    schema_version: u32,
    sequence: u64,
    event_id: &'a str,
    project_id: &'a str,
    gate: ApprovalGate,
    action: ApprovalAction,
    artifact_sha256: &'a str,
    actor_label: &'a str,
    rationale: &'a str,
    timestamp: u64,
    assurance: &'a str,
    previous_hash: &'a Option<String>,
}

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct HashPayloadV2<'a> {
    schema_version: u32,
    sequence: u64,
    event_id: &'a str,
    project_id: &'a str,
    gate: ApprovalGate,
    action: ApprovalAction,
    artifact_sha256: &'a str,
    related_artifacts: &'a [ArtifactBinding],
    actor_label: &'a str,
    rationale: &'a str,
    timestamp: u64,
    assurance: &'a str,
    previous_hash: &'a Option<String>,
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ApprovalLog {
    pub events: Vec<ApprovalEvent>,
    pub effective_approved_gates: Vec<ApprovalGate>,
    pub chain_head: Option<String>,
    pub integrity: &'static str,
    pub identity_assurance: &'static str,
}

fn approval_root(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app
        .path()
        .app_data_dir()
        .map_err(|e| e.to_string())?
        .join("heor")
        .join("approval-events"))
}

fn project_file(root: &Path, project_id: &str) -> Result<PathBuf, String> {
    validate_project_id(project_id)?;
    Ok(root.join(format!("{project_id}.jsonl")))
}

fn validate_project_id(value: &str) -> Result<(), String> {
    if value.is_empty()
        || value.len() > 80
        || !value
            .chars()
            .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
    {
        return Err("projectId must be 1-80 ASCII letters, digits, hyphens, or underscores".into());
    }
    Ok(())
}

fn validate_text(value: &str, name: &str, max_chars: usize) -> Result<(), String> {
    let trimmed = value.trim();
    if trimmed.is_empty() || trimmed.chars().count() > max_chars {
        return Err(format!("{name} must contain 1-{max_chars} characters"));
    }
    if trimmed != value {
        return Err(format!(
            "{name} must not have leading or trailing whitespace"
        ));
    }
    Ok(())
}

fn is_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
}

fn validate_request(request: &ApprovalRequest) -> Result<(), String> {
    validate_project_id(&request.project_id)?;
    if !is_sha256(&request.artifact_sha256) {
        return Err("artifactSha256 must be 64 lowercase hexadecimal characters".into());
    }
    validate_text(&request.actor_label, "actorLabel", 120)?;
    validate_text(&request.rationale, "rationale", 2_000)
}

fn hash_event(event: &ApprovalEvent) -> Result<String, String> {
    let encoded = match event.schema_version {
        1 => serde_json::to_vec(&HashPayloadV1 {
            schema_version: event.schema_version,
            sequence: event.sequence,
            event_id: &event.event_id,
            project_id: &event.project_id,
            gate: event.gate,
            action: event.action,
            artifact_sha256: &event.artifact_sha256,
            actor_label: &event.actor_label,
            rationale: &event.rationale,
            timestamp: event.timestamp,
            assurance: &event.assurance,
            previous_hash: &event.previous_hash,
        }),
        2 => serde_json::to_vec(&HashPayloadV2 {
            schema_version: event.schema_version,
            sequence: event.sequence,
            event_id: &event.event_id,
            project_id: &event.project_id,
            gate: event.gate,
            action: event.action,
            artifact_sha256: &event.artifact_sha256,
            related_artifacts: &event.related_artifacts,
            actor_label: &event.actor_label,
            rationale: &event.rationale,
            timestamp: event.timestamp,
            assurance: &event.assurance,
            previous_hash: &event.previous_hash,
        }),
        _ => return Err("unsupported approval schema version".into()),
    };
    let encoded = encoded.map_err(|e| e.to_string())?;
    Ok(format!("{:x}", Sha256::digest(encoded)))
}

fn validate_event(event: &ApprovalEvent, project_id: &str) -> Result<(), String> {
    if !matches!(event.schema_version, 1 | SCHEMA_VERSION) {
        return Err(format!(
            "unsupported approval schema version {}",
            event.schema_version
        ));
    }
    if event.project_id != project_id {
        return Err("approval event belongs to a different project".into());
    }
    if event.assurance != ASSURANCE {
        return Err("unsupported approval identity assurance".into());
    }
    if event.event_id.len() != 32 || !event.event_id.bytes().all(|b| b.is_ascii_hexdigit()) {
        return Err("invalid approval event id".into());
    }
    validate_text(&event.actor_label, "actorLabel", 120)?;
    validate_text(&event.rationale, "rationale", 2_000)?;
    if !is_sha256(&event.artifact_sha256) || !is_sha256(&event.event_hash) {
        return Err("invalid approval event hash".into());
    }
    if event.schema_version == 1 && !event.related_artifacts.is_empty() {
        return Err("approval schema version 1 cannot bind related artifacts".into());
    }
    let mut paths = std::collections::HashSet::new();
    for binding in &event.related_artifacts {
        let path = Path::new(&binding.path);
        if path.is_absolute()
            || path
                .components()
                .any(|component| !matches!(component, std::path::Component::Normal(_)))
            || !paths.insert(binding.path.as_str())
            || !is_sha256(&binding.sha256)
        {
            return Err("invalid related artifact binding".into());
        }
    }
    Ok(())
}

fn read_verified(root: &Path, project_id: &str) -> Result<Vec<ApprovalEvent>, String> {
    let file = project_file(root, project_id)?;
    let text = match std::fs::read_to_string(&file) {
        Ok(text) => text,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(format!("approval log read failed: {error}")),
    };
    let mut events = Vec::new();
    let mut previous_hash: Option<String> = None;
    for (index, line) in text.lines().enumerate() {
        if line.trim().is_empty() {
            return Err(format!(
                "approval log contains a blank line at {}",
                index + 1
            ));
        }
        let event: ApprovalEvent = serde_json::from_str(line)
            .map_err(|e| format!("approval log line {} is invalid: {e}", index + 1))?;
        validate_event(&event, project_id)
            .map_err(|e| format!("approval log line {} is invalid: {e}", index + 1))?;
        let expected_sequence = index as u64 + 1;
        if event.sequence != expected_sequence {
            return Err(format!(
                "approval log sequence breaks at line {}",
                index + 1
            ));
        }
        if event.previous_hash != previous_hash {
            return Err(format!("approval hash chain breaks at line {}", index + 1));
        }
        if hash_event(&event)? != event.event_hash {
            return Err(format!(
                "approval event hash mismatch at line {}",
                index + 1
            ));
        }
        previous_hash = Some(event.event_hash.clone());
        events.push(event);
    }
    Ok(events)
}

fn latest_by_gate(events: &[ApprovalEvent]) -> HashMap<ApprovalGate, &ApprovalEvent> {
    let mut latest = HashMap::new();
    for event in events {
        latest.insert(event.gate, event);
    }
    latest
}

fn effective_gates(events: &[ApprovalEvent]) -> Vec<ApprovalGate> {
    let latest = latest_by_gate(events);
    let mut approved = Vec::new();
    let mut prerequisite_sequence = 0;
    for gate in GATES {
        let Some(event) = latest.get(&gate) else {
            break;
        };
        if event.action != ApprovalAction::Approve || event.sequence <= prerequisite_sequence {
            break;
        }
        approved.push(gate);
        prerequisite_sequence = event.sequence;
    }
    approved
}

fn validate_transition(events: &[ApprovalEvent], request: &ApprovalRequest) -> Result<(), String> {
    let latest = latest_by_gate(events);
    let current = latest.get(&request.gate);
    match request.action {
        ApprovalAction::Approve => {
            let effective = effective_gates(events);
            if effective.contains(&request.gate) {
                return Err(
                    "gate is already approved; revoke it before approving a new artifact".into(),
                );
            }
            let gate_index = GATES.iter().position(|gate| *gate == request.gate).unwrap();
            if effective.len() < gate_index {
                return Err("all preceding HEOR gates must be effectively approved first".into());
            }
        }
        ApprovalAction::Revoke => {
            if !current.is_some_and(|event| event.action == ApprovalAction::Approve) {
                return Err("only a currently approved gate can be revoked".into());
            }
            if !current.is_some_and(|event| event.artifact_sha256 == request.artifact_sha256) {
                return Err(
                    "revocation artifact must match the currently approved artifact".into(),
                );
            }
        }
    }
    Ok(())
}

fn append_at(
    root: &Path,
    request: ApprovalRequest,
    timestamp: u64,
    event_id: String,
    related_artifacts: Vec<ArtifactBinding>,
) -> Result<ApprovalEvent, String> {
    validate_request(&request)?;
    let events = read_verified(root, &request.project_id)?;
    validate_transition(&events, &request)?;
    let mut event = ApprovalEvent {
        schema_version: SCHEMA_VERSION,
        sequence: events.len() as u64 + 1,
        event_id,
        project_id: request.project_id,
        gate: request.gate,
        action: request.action,
        artifact_sha256: request.artifact_sha256,
        related_artifacts,
        actor_label: request.actor_label,
        rationale: request.rationale,
        timestamp,
        assurance: ASSURANCE.to_string(),
        previous_hash: events.last().map(|event| event.event_hash.clone()),
        event_hash: String::new(),
    };
    event.event_hash = hash_event(&event)?;

    let file = project_file(root, &event.project_id)?;
    if let Some(parent) = file.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|e| format!("approval log directory failed: {e}"))?;
        crate::runtime::tighten_private(parent);
    }
    let line = serde_json::to_string(&event).map_err(|e| e.to_string())?;
    let mut output = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&file)
        .map_err(|e| format!("approval log open failed: {e}"))?;
    crate::runtime::tighten_private(&file);
    writeln!(output, "{line}").map_err(|e| format!("approval log write failed: {e}"))?;
    output
        .sync_all()
        .map_err(|e| format!("approval log sync failed: {e}"))?;
    Ok(event)
}

fn log_summary(events: Vec<ApprovalEvent>) -> ApprovalLog {
    ApprovalLog {
        effective_approved_gates: effective_gates(&events),
        chain_head: events.last().map(|event| event.event_hash.clone()),
        events,
        integrity: "verified_unanchored_sha256_chain",
        identity_assurance: ASSURANCE,
    }
}

pub(crate) fn verified_log(app: &AppHandle, project_id: &str) -> Result<ApprovalLog, String> {
    Ok(log_summary(read_verified(
        &approval_root(app)?,
        project_id,
    )?))
}

pub(crate) fn event_binds_artifact(event: &ApprovalEvent, path: &str, sha256: &str) -> bool {
    event
        .related_artifacts
        .iter()
        .any(|binding| binding.path == path && binding.sha256 == sha256)
}

#[tauri::command(async)]
pub fn append_heor_approval(
    app: AppHandle,
    state: tauri::State<HeorApprovalState>,
    request: ApprovalRequest,
) -> Result<ApprovalEvent, String> {
    let _guard = state.0.lock().map_err(|_| "HEOR approval lock poisoned")?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    if crate::project::require_project_id(&workspace)? != request.project_id {
        return Err("approval projectId does not match the current project".into());
    }
    let mut related_artifacts = Vec::new();
    if request.action == ApprovalAction::Approve {
        match request.gate {
            ApprovalGate::DecisionProblem => {
                crate::heor_artifacts::require_decision_problem_approvable(
                    &workspace,
                    &request.artifact_sha256,
                )?;
            }
            ApprovalGate::ConceptualModel => {
                crate::heor_artifacts::require_conceptual_model_approvable(
                    &workspace,
                    &request.artifact_sha256,
                )?;
            }
            ApprovalGate::AnalysisPlan => {
                let raw = crate::heor_uncertainty::read_workspace_capped(
                    &workspace,
                    "heor/analysis-plan.json",
                )?;
                crate::heor_evidence::require_analysis_plan_approvable(
                    &raw,
                    &request.artifact_sha256,
                )?;
                if format!("{:x}", Sha256::digest(&raw)) != request.artifact_sha256 {
                    return Err(
                        "analysis-plan approval must target the current heor/analysis-plan.json"
                            .into(),
                    );
                }
                crate::heor_reference_case::require_analysis_plan_approvable(
                    &app, &workspace, &raw,
                )?;
                let evidence_selection =
                    crate::heor_evidence::require_evidence_selection_approvable(
                        &app,
                        &workspace,
                        &request.project_id,
                        &raw,
                    )?;
                if !evidence_selection.synthesis_sha256.is_empty() {
                    related_artifacts.push(ArtifactBinding {
                        path: crate::heor_synthesis::EVIDENCE_SYNTHESIS_PATH.into(),
                        sha256: evidence_selection.synthesis_sha256,
                    });
                }
                let uncertainty =
                    crate::heor_uncertainty::require_uncertainty_plan_approvable(&workspace, &raw)?;
                related_artifacts.push(ArtifactBinding {
                    path: crate::heor_uncertainty::UNCERTAINTY_PLAN_PATH.into(),
                    sha256: uncertainty.uncertainty_sha256,
                });
                if let Some(binding) =
                    crate::heor_paired_survival_bootstrap::require_current_review_for_joint_manifest(
                        &app,
                        &workspace,
                        &request.project_id,
                    )?
                {
                    related_artifacts.push(binding);
                }
                let budget_impact =
                    crate::heor_budget_impact::require_budget_impact_plan_approvable(
                        &workspace, &raw,
                    )?;
                related_artifacts.push(ArtifactBinding {
                    path: crate::heor_budget_impact::BUDGET_IMPACT_PLAN_PATH.into(),
                    sha256: budget_impact.budget_impact_sha256,
                });
                related_artifacts.extend(
                    crate::heor_survival_review::require_survival_review_approvable(
                        &workspace, &raw,
                    )?,
                );
                let partitioned =
                    crate::heor_partitioned_survival::audit_partitioned_survival_for_plan(
                        &workspace, &raw,
                    )?;
                if partitioned.required {
                    related_artifacts.extend(
                        crate::heor_partitioned_survival::require_partitioned_survival_approvable(
                            &workspace, &raw,
                        )?
                        .artifact_bindings,
                    );
                }
            }
            ApprovalGate::IndependentValidation => {
                let validation = crate::heor_validation::require_model_validation_approvable(
                    &workspace,
                    &request.artifact_sha256,
                    &request.actor_label,
                )?;
                let log = verified_log(&app, &request.project_id)?;
                if !crate::heor_validation::analysis_plan_approval_is_current(&log, &validation) {
                    return Err(
                        "independent validation requires current conceptual-model and analysis-plan approvals"
                            .into(),
                    );
                }
                related_artifacts = crate::heor_validation::approval_bindings(&validation);
            }
            ApprovalGate::Release => {
                let log = verified_log(&app, &request.project_id)?;
                let report = crate::heor_reporting::require_report_releasable(
                    &app,
                    &workspace,
                    &request.artifact_sha256,
                    &request.actor_label,
                    &log,
                )?;
                related_artifacts = crate::heor_reporting::approval_bindings(&report);
            }
        }
    }
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|e| e.to_string())?
        .as_secs();
    append_at(
        &approval_root(&app)?,
        request,
        timestamp,
        crate::runtime::random_hex(16),
        related_artifacts,
    )
}

#[tauri::command(async)]
pub fn list_heor_approvals(
    app: AppHandle,
    state: tauri::State<HeorApprovalState>,
    project_id: String,
) -> Result<ApprovalLog, String> {
    let _guard = state.0.lock().map_err(|_| "HEOR approval lock poisoned")?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    if crate::project::require_project_id(&workspace)? != project_id {
        return Err("approval projectId does not match the current project".into());
    }
    verified_log(&app, &project_id)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn temp_root(tag: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!("heor-approval-{tag}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        root
    }

    fn request(gate: ApprovalGate, action: ApprovalAction, marker: char) -> ApprovalRequest {
        ApprovalRequest {
            project_id: "project-1".into(),
            gate,
            action,
            artifact_sha256: marker.to_string().repeat(64),
            actor_label: "Qualified human reviewer".into(),
            rationale: "Reviewed against the gate checklist.".into(),
        }
    }

    fn append(
        root: &Path,
        gate: ApprovalGate,
        action: ApprovalAction,
        sequence: u64,
    ) -> Result<ApprovalEvent, String> {
        let mut approval_request = request(
            gate,
            action,
            char::from_digit((sequence % 6 + 10) as u32, 16).unwrap(),
        );
        if action == ApprovalAction::Revoke {
            approval_request.artifact_sha256 = read_verified(root, "project-1")?
                .iter()
                .rev()
                .find(|event| event.gate == gate && event.action == ApprovalAction::Approve)
                .ok_or("no approved artifact to revoke")?
                .artifact_sha256
                .clone();
        }
        append_at(
            root,
            approval_request,
            1_700_000_000 + sequence,
            format!("{sequence:032x}"),
            Vec::new(),
        )
    }

    #[test]
    fn ordered_approvals_form_a_verified_chain() {
        let root = temp_root("chain");
        for (index, gate) in GATES.into_iter().enumerate() {
            append(&root, gate, ApprovalAction::Approve, index as u64 + 1).unwrap();
        }

        let events = read_verified(&root, "project-1").unwrap();
        let summary = log_summary(events.clone());
        assert_eq!(events.len(), 5);
        assert_eq!(summary.effective_approved_gates, GATES);
        assert_eq!(summary.chain_head, Some(events[4].event_hash.clone()));
        assert_eq!(events[1].previous_hash, Some(events[0].event_hash.clone()));

        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn approval_order_and_duplicate_actions_are_rejected() {
        let root = temp_root("order");
        let out_of_order = append(
            &root,
            ApprovalGate::AnalysisPlan,
            ApprovalAction::Approve,
            1,
        );
        assert!(out_of_order.unwrap_err().contains("preceding HEOR gates"));

        append(
            &root,
            ApprovalGate::DecisionProblem,
            ApprovalAction::Approve,
            2,
        )
        .unwrap();
        let duplicate = append(
            &root,
            ApprovalGate::DecisionProblem,
            ApprovalAction::Approve,
            3,
        );
        assert!(duplicate.unwrap_err().contains("already approved"));

        let mismatched_revoke = append_at(
            &root,
            request(ApprovalGate::DecisionProblem, ApprovalAction::Revoke, 'f'),
            1_700_000_004,
            "4".repeat(32),
            Vec::new(),
        );
        assert!(mismatched_revoke
            .unwrap_err()
            .contains("must match the currently approved artifact"));

        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn upstream_reapproval_does_not_reactivate_stale_downstream_approval() {
        let root = temp_root("cascade");
        append(
            &root,
            ApprovalGate::DecisionProblem,
            ApprovalAction::Approve,
            1,
        )
        .unwrap();
        append(
            &root,
            ApprovalGate::ConceptualModel,
            ApprovalAction::Approve,
            2,
        )
        .unwrap();
        append(
            &root,
            ApprovalGate::DecisionProblem,
            ApprovalAction::Revoke,
            3,
        )
        .unwrap();
        append(
            &root,
            ApprovalGate::DecisionProblem,
            ApprovalAction::Approve,
            4,
        )
        .unwrap();

        assert_eq!(
            effective_gates(&read_verified(&root, "project-1").unwrap()),
            vec![ApprovalGate::DecisionProblem]
        );
        append(
            &root,
            ApprovalGate::ConceptualModel,
            ApprovalAction::Approve,
            5,
        )
        .unwrap();
        assert_eq!(
            effective_gates(&read_verified(&root, "project-1").unwrap()),
            vec![ApprovalGate::DecisionProblem, ApprovalGate::ConceptualModel]
        );

        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn any_existing_log_modification_fails_closed() {
        let root = temp_root("tamper");
        append(
            &root,
            ApprovalGate::DecisionProblem,
            ApprovalAction::Approve,
            1,
        )
        .unwrap();
        let file = project_file(&root, "project-1").unwrap();
        let changed = std::fs::read_to_string(&file)
            .unwrap()
            .replace("Qualified human reviewer", "Agent impersonation");
        std::fs::write(&file, changed).unwrap();

        let error = read_verified(&root, "project-1").unwrap_err();
        assert!(error.contains("hash mismatch"));
        assert!(append(
            &root,
            ApprovalGate::ConceptualModel,
            ApprovalAction::Approve,
            2
        )
        .is_err());

        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn schema_one_logs_remain_verifiable_after_related_artifact_upgrade() {
        let root = temp_root("schema-one");
        let mut event = ApprovalEvent {
            schema_version: 1,
            sequence: 1,
            event_id: "1".repeat(32),
            project_id: "project-1".into(),
            gate: ApprovalGate::DecisionProblem,
            action: ApprovalAction::Approve,
            artifact_sha256: "a".repeat(64),
            related_artifacts: Vec::new(),
            actor_label: "Reviewer".into(),
            rationale: "Reviewed legacy event".into(),
            timestamp: 1_700_000_000,
            assurance: ASSURANCE.into(),
            previous_hash: None,
            event_hash: String::new(),
        };
        event.event_hash = hash_event(&event).unwrap();
        let file = project_file(&root, "project-1").unwrap();
        std::fs::write(
            file,
            format!("{}\n", serde_json::to_string(&event).unwrap()),
        )
        .unwrap();

        let events = read_verified(&root, "project-1").unwrap();
        assert_eq!(events, vec![event]);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn related_artifact_binding_is_covered_by_the_event_hash() {
        let root = temp_root("related-tamper");
        append_at(
            &root,
            request(ApprovalGate::DecisionProblem, ApprovalAction::Approve, 'a'),
            1_700_000_000,
            "1".repeat(32),
            vec![ArtifactBinding {
                path: "heor/uncertainty-plan.json".into(),
                sha256: "b".repeat(64),
            }],
        )
        .unwrap();
        let file = project_file(&root, "project-1").unwrap();
        let changed = std::fs::read_to_string(&file)
            .unwrap()
            .replace(&"b".repeat(64), &"c".repeat(64));
        std::fs::write(&file, changed).unwrap();

        assert!(read_verified(&root, "project-1")
            .unwrap_err()
            .contains("hash mismatch"));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn project_and_artifact_identifiers_cannot_escape_the_store() {
        let root = temp_root("validation");
        let mut invalid_project =
            request(ApprovalGate::DecisionProblem, ApprovalAction::Approve, 'a');
        invalid_project.project_id = "../outside".into();
        assert!(append_at(&root, invalid_project, 1, "0".repeat(32), Vec::new()).is_err());

        let mut invalid_hash = request(ApprovalGate::DecisionProblem, ApprovalAction::Approve, 'a');
        invalid_hash.artifact_sha256 = "ABC".into();
        assert!(append_at(&root, invalid_hash, 1, "0".repeat(32), Vec::new()).is_err());

        let _ = std::fs::remove_dir_all(root);
    }
}
