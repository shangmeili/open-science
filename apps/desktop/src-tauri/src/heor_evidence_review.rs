//! App-owned human verification for evidence extractions.
//!
//! The workspace synthesis is agent-writable and may describe review activity,
//! but it cannot create these events. Each event binds the exact synthesis
//! bytes and an explicit set of extraction IDs in an append-only SHA-256 chain.

use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager};

const LEGACY_SCHEMA_VERSION: u32 = 1;
const SCHEMA_VERSION: u32 = 2;
const ASSURANCE: &str = "local_human_assertion";
pub(crate) const REQUIRED_REVIEWERS_PER_EXTRACTION: usize = 2;
const MAX_LOG_BYTES: u64 = 8 * 1024 * 1024;
const MAX_EVENTS: usize = 10_000;
const MAX_EXTRACTIONS_PER_EVENT: usize = 10_000;

#[derive(Default)]
pub struct HeorEvidenceReviewState(pub Mutex<()>);

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct EvidenceVerificationRequest {
    project_id: String,
    synthesis_sha256: String,
    extraction_ids: Vec<String>,
    actor_label: String,
    rationale: String,
    decision: EvidenceReviewDecision,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum EvidenceReviewDecision {
    Confirmed,
    Rejected,
}

#[derive(Clone, Debug, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct EvidenceVerificationEvent {
    schema_version: u32,
    sequence: u64,
    event_id: String,
    project_id: String,
    synthesis_sha256: String,
    extraction_ids: Vec<String>,
    actor_label: String,
    rationale: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    decision: Option<EvidenceReviewDecision>,
    timestamp: u64,
    assurance: String,
    previous_hash: Option<String>,
    event_hash: String,
}

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct EventHashPayloadV1<'a> {
    schema_version: u32,
    sequence: u64,
    event_id: &'a str,
    project_id: &'a str,
    synthesis_sha256: &'a str,
    extraction_ids: &'a [String],
    actor_label: &'a str,
    rationale: &'a str,
    timestamp: u64,
    assurance: &'a str,
    previous_hash: &'a Option<String>,
}

#[derive(serde::Serialize)]
#[serde(rename_all = "camelCase")]
struct EventHashPayloadV2<'a> {
    schema_version: u32,
    sequence: u64,
    event_id: &'a str,
    project_id: &'a str,
    synthesis_sha256: &'a str,
    extraction_ids: &'a [String],
    actor_label: &'a str,
    rationale: &'a str,
    decision: EvidenceReviewDecision,
    timestamp: u64,
    assurance: &'a str,
    previous_hash: &'a Option<String>,
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct EvidenceVerificationLog {
    pub events: Vec<EvidenceVerificationEvent>,
    pub chain_head: Option<String>,
    pub integrity: &'static str,
    pub identity_assurance: &'static str,
}

fn review_root(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app
        .path()
        .app_data_dir()
        .map_err(|error| error.to_string())?
        .join("heor")
        .join("evidence-verification-events"))
}

fn safe_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 120
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b':' | b'.'))
}

fn validate_project_id(value: &str) -> Result<(), String> {
    if value.is_empty()
        || value.len() > 80
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
    {
        return Err("projectId must be 1-80 ASCII letters, digits, hyphens, or underscores".into());
    }
    Ok(())
}

fn validate_text(value: &str, field: &str, max_chars: usize) -> Result<(), String> {
    if value.trim() != value || value.is_empty() || value.chars().count() > max_chars {
        return Err(format!(
            "{field} must contain 1-{max_chars} characters without surrounding whitespace"
        ));
    }
    if value.chars().any(char::is_control) {
        return Err(format!("{field} must not contain control characters"));
    }
    Ok(())
}

fn is_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn project_file(root: &Path, project_id: &str) -> Result<PathBuf, String> {
    validate_project_id(project_id)?;
    Ok(root.join(format!("{project_id}.jsonl")))
}

fn hash_event(event: &EvidenceVerificationEvent) -> Result<String, String> {
    let encoded = if event.schema_version == LEGACY_SCHEMA_VERSION {
        serde_json::to_vec(&EventHashPayloadV1 {
            schema_version: event.schema_version,
            sequence: event.sequence,
            event_id: &event.event_id,
            project_id: &event.project_id,
            synthesis_sha256: &event.synthesis_sha256,
            extraction_ids: &event.extraction_ids,
            actor_label: &event.actor_label,
            rationale: &event.rationale,
            timestamp: event.timestamp,
            assurance: &event.assurance,
            previous_hash: &event.previous_hash,
        })
        .map_err(|error| error.to_string())?
    } else {
        serde_json::to_vec(&EventHashPayloadV2 {
            schema_version: event.schema_version,
            sequence: event.sequence,
            event_id: &event.event_id,
            project_id: &event.project_id,
            synthesis_sha256: &event.synthesis_sha256,
            extraction_ids: &event.extraction_ids,
            actor_label: &event.actor_label,
            rationale: &event.rationale,
            decision: event
                .decision
                .ok_or_else(|| "schema-v2 evidence review event omitted decision".to_string())?,
            timestamp: event.timestamp,
            assurance: &event.assurance,
            previous_hash: &event.previous_hash,
        })
        .map_err(|error| error.to_string())?
    };
    Ok(format!("{:x}", Sha256::digest(encoded)))
}

fn validate_event(event: &EvidenceVerificationEvent, project_id: &str) -> Result<(), String> {
    let schema_valid = match event.schema_version {
        LEGACY_SCHEMA_VERSION => event.decision.is_none(),
        SCHEMA_VERSION => event.decision.is_some(),
        _ => false,
    };
    if !schema_valid
        || event.project_id != project_id
        || event.assurance != ASSURANCE
        || event.event_id.len() != 32
        || !event.event_id.bytes().all(|byte| byte.is_ascii_hexdigit())
        || !is_sha256(&event.synthesis_sha256)
        || !is_sha256(&event.event_hash)
    {
        return Err("invalid evidence-verification event metadata".into());
    }
    validate_text(&event.actor_label, "actorLabel", 120)?;
    validate_text(&event.rationale, "rationale", 2_000)?;
    if event.extraction_ids.is_empty()
        || event.extraction_ids.len() > MAX_EXTRACTIONS_PER_EVENT
        || event
            .extraction_ids
            .windows(2)
            .any(|pair| pair[0] >= pair[1])
        || event.extraction_ids.iter().any(|id| !safe_id(id))
    {
        return Err("extractionIds must be a non-empty sorted unique list of safe IDs".into());
    }
    Ok(())
}

fn read_verified(root: &Path, project_id: &str) -> Result<Vec<EvidenceVerificationEvent>, String> {
    let file = project_file(root, project_id)?;
    let metadata = match std::fs::symlink_metadata(&file) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => {
            return Err(format!(
                "evidence-verification log metadata failed: {error}"
            ))
        }
    };
    if metadata.file_type().is_symlink() || !metadata.is_file() || metadata.len() > MAX_LOG_BYTES {
        return Err("evidence-verification log must be a capped regular non-symlink file".into());
    }
    let text = std::fs::read_to_string(&file)
        .map_err(|error| format!("evidence-verification log read failed: {error}"))?;
    let mut events = Vec::new();
    let mut previous_hash = None;
    for (index, line) in text.lines().enumerate() {
        if line.trim().is_empty() || index >= MAX_EVENTS {
            return Err(format!(
                "evidence-verification log is invalid at line {}",
                index + 1
            ));
        }
        let event: EvidenceVerificationEvent = serde_json::from_str(line).map_err(|error| {
            format!(
                "evidence-verification log line {} is invalid: {error}",
                index + 1
            )
        })?;
        validate_event(&event, project_id).map_err(|error| {
            format!(
                "evidence-verification log line {} is invalid: {error}",
                index + 1
            )
        })?;
        if event.sequence != index as u64 + 1 || event.previous_hash != previous_hash {
            return Err(format!(
                "evidence-verification chain breaks at line {}",
                index + 1
            ));
        }
        if hash_event(&event)? != event.event_hash {
            return Err(format!(
                "evidence-verification hash mismatch at line {}",
                index + 1
            ));
        }
        previous_hash = Some(event.event_hash.clone());
        events.push(event);
    }
    Ok(events)
}

fn summary(events: Vec<EvidenceVerificationEvent>) -> EvidenceVerificationLog {
    EvidenceVerificationLog {
        chain_head: events.last().map(|event| event.event_hash.clone()),
        events,
        integrity: "verified_unanchored_sha256_chain",
        identity_assurance: ASSURANCE,
    }
}

pub(crate) fn verified_log(
    app: &AppHandle,
    project_id: &str,
) -> Result<EvidenceVerificationLog, String> {
    Ok(summary(read_verified(&review_root(app)?, project_id)?))
}

#[derive(Clone, Debug)]
pub(crate) struct EvidenceReviewStatus {
    pub verified_extraction_ids: BTreeSet<String>,
    pub pending_extraction_ids: BTreeSet<String>,
    pub rejected_extraction_ids: BTreeSet<String>,
    pub confirmation_count: usize,
}

fn event_decision(event: &EvidenceVerificationEvent) -> EvidenceReviewDecision {
    event.decision.unwrap_or(EvidenceReviewDecision::Confirmed)
}

pub(crate) fn review_status(
    log: &EvidenceVerificationLog,
    synthesis_sha256: &str,
    eligible: &BTreeSet<String>,
) -> EvidenceReviewStatus {
    let mut decisions = BTreeMap::<String, BTreeMap<String, EvidenceReviewDecision>>::new();
    for event in log
        .events
        .iter()
        .filter(|event| event.synthesis_sha256 == synthesis_sha256)
    {
        let actor = event.actor_label.to_lowercase();
        for extraction_id in event
            .extraction_ids
            .iter()
            .filter(|id| eligible.contains(*id))
        {
            decisions
                .entry(extraction_id.clone())
                .or_default()
                .entry(actor.clone())
                .or_insert_with(|| event_decision(event));
        }
    }
    let mut verified_extraction_ids = BTreeSet::new();
    let mut rejected_extraction_ids = BTreeSet::new();
    let mut confirmation_count = 0usize;
    for extraction_id in eligible {
        let per_actor = decisions.get(extraction_id);
        let confirmations = per_actor
            .into_iter()
            .flat_map(|values| values.values())
            .filter(|decision| **decision == EvidenceReviewDecision::Confirmed)
            .count();
        confirmation_count += confirmations;
        let rejected = per_actor.is_some_and(|values| {
            values
                .values()
                .any(|decision| *decision == EvidenceReviewDecision::Rejected)
        });
        if rejected {
            rejected_extraction_ids.insert(extraction_id.clone());
        } else if confirmations >= REQUIRED_REVIEWERS_PER_EXTRACTION {
            verified_extraction_ids.insert(extraction_id.clone());
        }
    }
    let pending_extraction_ids = eligible
        .difference(&verified_extraction_ids)
        .filter(|id| !rejected_extraction_ids.contains(*id))
        .cloned()
        .collect();
    EvidenceReviewStatus {
        verified_extraction_ids,
        pending_extraction_ids,
        rejected_extraction_ids,
        confirmation_count,
    }
}

fn append_at(
    root: &Path,
    request: EvidenceVerificationRequest,
    timestamp: u64,
    event_id: String,
) -> Result<EvidenceVerificationEvent, String> {
    let events = read_verified(root, &request.project_id)?;
    if events.len() >= MAX_EVENTS {
        return Err("evidence-verification event cap reached".into());
    }
    let actor = request.actor_label.to_lowercase();
    let duplicate = events.iter().any(|event| {
        event.synthesis_sha256 == request.synthesis_sha256
            && event.actor_label.to_lowercase() == actor
            && event
                .extraction_ids
                .iter()
                .any(|id| request.extraction_ids.contains(id))
    });
    if duplicate {
        return Err(
            "this reviewer label already reviewed at least one selected extraction for the current synthesis"
                .into(),
        );
    }
    let mut event = EvidenceVerificationEvent {
        schema_version: SCHEMA_VERSION,
        sequence: events.len() as u64 + 1,
        event_id,
        project_id: request.project_id,
        synthesis_sha256: request.synthesis_sha256,
        extraction_ids: request.extraction_ids,
        actor_label: request.actor_label,
        rationale: request.rationale,
        decision: Some(request.decision),
        timestamp,
        assurance: ASSURANCE.into(),
        previous_hash: events.last().map(|event| event.event_hash.clone()),
        event_hash: "0".repeat(64),
    };
    validate_event(&event, &event.project_id)?;
    event.event_hash = hash_event(&event)?;
    let file = project_file(root, &event.project_id)?;
    if let Some(parent) = file.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("evidence-verification log directory failed: {error}"))?;
        crate::runtime::tighten_private(parent);
    }
    let line = serde_json::to_string(&event).map_err(|error| error.to_string())?;
    let mut output = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&file)
        .map_err(|error| format!("evidence-verification log open failed: {error}"))?;
    crate::runtime::tighten_private(&file);
    writeln!(output, "{line}")
        .and_then(|_| output.sync_all())
        .map_err(|error| format!("evidence-verification log write failed: {error}"))?;
    Ok(event)
}

#[tauri::command(async)]
pub fn verify_heor_evidence_extractions(
    app: AppHandle,
    state: tauri::State<HeorEvidenceReviewState>,
    request: EvidenceVerificationRequest,
) -> Result<crate::heor_synthesis::SynthesisAudit, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "HEOR evidence-review lock poisoned")?;
    validate_project_id(&request.project_id)?;
    validate_text(&request.actor_label, "actorLabel", 120)?;
    validate_text(&request.rationale, "rationale", 2_000)?;
    if !is_sha256(&request.synthesis_sha256) {
        return Err("synthesisSha256 must be 64 lowercase hexadecimal characters".into());
    }
    let requested = request
        .extraction_ids
        .iter()
        .cloned()
        .collect::<BTreeSet<_>>();
    if requested.len() != request.extraction_ids.len()
        || requested.is_empty()
        || requested.len() > MAX_EXTRACTIONS_PER_EVENT
        || requested.iter().any(|id| !safe_id(id))
    {
        return Err("extractionIds must be a non-empty unique list of safe IDs".into());
    }
    let workspace = crate::runtime::workspace_dir(&app)?;
    if crate::project::require_project_id(&workspace)? != request.project_id {
        return Err("evidence verification projectId does not match the current project".into());
    }
    let raw = crate::heor_uncertainty::read_workspace_capped(
        &workspace,
        crate::heor_synthesis::EVIDENCE_SYNTHESIS_PATH,
    )?;
    let audit = crate::heor_synthesis::audit_bytes(&raw);
    if !audit.complete || audit.synthesis_sha256 != request.synthesis_sha256 {
        return Err(
            "evidence verification must target the exact current structurally complete synthesis"
                .into(),
        );
    }
    let eligible = audit
        .eligible_extraction_ids
        .iter()
        .cloned()
        .collect::<BTreeSet<_>>();
    if !requested.is_subset(&eligible) {
        return Err(
            "evidence verification contains an ineligible or conflicting extraction".into(),
        );
    }
    let normalized = EvidenceVerificationRequest {
        extraction_ids: requested.into_iter().collect(),
        ..request
    };
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| error.to_string())?
        .as_secs();
    append_at(
        &review_root(&app)?,
        normalized,
        timestamp,
        crate::runtime::random_hex(16),
    )?;
    crate::heor_synthesis::audit_current_with_verification(&app, &workspace)
}

#[tauri::command(async)]
pub fn list_heor_evidence_verifications(
    app: AppHandle,
    state: tauri::State<HeorEvidenceReviewState>,
    project_id: String,
) -> Result<EvidenceVerificationLog, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "HEOR evidence-review lock poisoned")?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    if crate::project::require_project_id(&workspace)? != project_id {
        return Err("evidence verification projectId does not match the current project".into());
    }
    verified_log(&app, &project_id)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request(
        ids: &[&str],
        actor_label: &str,
        decision: EvidenceReviewDecision,
    ) -> EvidenceVerificationRequest {
        EvidenceVerificationRequest {
            project_id: "project-1".into(),
            synthesis_sha256: "a".repeat(64),
            extraction_ids: ids.iter().map(|id| (*id).into()).collect(),
            actor_label: actor_label.into(),
            rationale: "Checked source location and value against the report".into(),
            decision,
        }
    }

    #[test]
    fn verification_events_form_a_hash_chain_and_are_synthesis_scoped() {
        let root =
            std::env::temp_dir().join(format!("heor-evidence-review-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        append_at(
            &root,
            request(
                &["extract-2", "extract-1"],
                "Reviewer one",
                EvidenceReviewDecision::Confirmed,
            ),
            1,
            "1".repeat(32),
        )
        .unwrap_err();
        let mut first = request(
            &["extract-1", "extract-2"],
            "Reviewer one",
            EvidenceReviewDecision::Confirmed,
        );
        first.extraction_ids.sort();
        append_at(&root, first, 1, "1".repeat(32)).unwrap();
        let second = request(
            &["extract-3"],
            "Reviewer two",
            EvidenceReviewDecision::Confirmed,
        );
        append_at(&root, second, 2, "2".repeat(32)).unwrap();
        let log = summary(read_verified(&root, "project-1").unwrap());
        let eligible = ["extract-1", "extract-2", "extract-3"]
            .into_iter()
            .map(str::to_string)
            .collect();
        let review = review_status(&log, &"a".repeat(64), &eligible);
        assert!(review.verified_extraction_ids.is_empty());
        assert_eq!(review.confirmation_count, 3);
        assert_eq!(review.pending_extraction_ids.len(), 3);
        assert_eq!(
            log.events[1].previous_hash,
            Some(log.events[0].event_hash.clone())
        );
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn two_distinct_confirmations_are_required_and_rejection_blocks() {
        let root =
            std::env::temp_dir().join(format!("heor-evidence-review-dual-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        append_at(
            &root,
            request(
                &["extract-1", "extract-2"],
                "Reviewer one",
                EvidenceReviewDecision::Confirmed,
            ),
            1,
            "1".repeat(32),
        )
        .unwrap();
        append_at(
            &root,
            request(
                &["extract-1", "extract-2"],
                "Reviewer two",
                EvidenceReviewDecision::Confirmed,
            ),
            2,
            "2".repeat(32),
        )
        .unwrap();
        append_at(
            &root,
            request(
                &["extract-2"],
                "Reviewer three",
                EvidenceReviewDecision::Rejected,
            ),
            3,
            "3".repeat(32),
        )
        .unwrap();
        let log = summary(read_verified(&root, "project-1").unwrap());
        let eligible = ["extract-1", "extract-2"]
            .into_iter()
            .map(str::to_string)
            .collect();
        let review = review_status(&log, &"a".repeat(64), &eligible);
        assert_eq!(review.verified_extraction_ids, ["extract-1".into()].into());
        assert_eq!(review.rejected_extraction_ids, ["extract-2".into()].into());
        assert_eq!(review.confirmation_count, 4);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn one_label_cannot_review_the_same_extraction_twice() {
        let root = std::env::temp_dir().join(format!(
            "heor-evidence-review-duplicate-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        append_at(
            &root,
            request(
                &["extract-1"],
                "Reviewer One",
                EvidenceReviewDecision::Confirmed,
            ),
            1,
            "1".repeat(32),
        )
        .unwrap();
        let error = append_at(
            &root,
            request(
                &["extract-1"],
                "reviewer one",
                EvidenceReviewDecision::Confirmed,
            ),
            2,
            "2".repeat(32),
        )
        .unwrap_err();
        assert!(error.contains("already reviewed"));
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn legacy_single_reviewer_event_remains_valid_but_is_not_dual_confirmation() {
        let mut event = EvidenceVerificationEvent {
            schema_version: LEGACY_SCHEMA_VERSION,
            sequence: 1,
            event_id: "1".repeat(32),
            project_id: "project-1".into(),
            synthesis_sha256: "a".repeat(64),
            extraction_ids: vec!["extract-1".into()],
            actor_label: "Legacy reviewer".into(),
            rationale: "Checked source location and value against the report".into(),
            decision: None,
            timestamp: 1,
            assurance: ASSURANCE.into(),
            previous_hash: None,
            event_hash: "0".repeat(64),
        };
        event.event_hash = hash_event(&event).unwrap();
        validate_event(&event, "project-1").unwrap();
        let eligible = ["extract-1".to_string()].into();
        let review = review_status(&summary(vec![event]), &"a".repeat(64), &eligible);
        assert!(review.verified_extraction_ids.is_empty());
        assert_eq!(review.confirmation_count, 1);
        assert_eq!(review.pending_extraction_ids, eligible);
    }

    #[test]
    fn tampering_fails_closed() {
        let root = std::env::temp_dir().join(format!(
            "heor-evidence-review-tamper-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        append_at(
            &root,
            request(
                &["extract-1"],
                "Reviewer one",
                EvidenceReviewDecision::Confirmed,
            ),
            1,
            "1".repeat(32),
        )
        .unwrap();
        let file = root.join("project-1.jsonl");
        let changed = std::fs::read_to_string(&file)
            .unwrap()
            .replace("extract-1", "extract-9");
        std::fs::write(&file, changed).unwrap();
        assert!(read_verified(&root, "project-1").is_err());
        let _ = std::fs::remove_dir_all(root);
    }
}
