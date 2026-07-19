//! App-owned review for non-sensitive, non-scientific local work preferences.
//!
//! The Agent may draft proposals after repeated observations, but only this
//! native control may change `learning/preferences.json`. Every change is
//! bound to the current store hash, a Human assertion, a workspace snapshot,
//! and an owner-only append-only event chain.

use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::io::Write;
use std::path::{Component, Path, PathBuf};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::AppHandle;

const PROPOSAL_SCHEMA: &str = "ai4heor-preference-proposal/v1";
const STORE_SCHEMA: &str = "ai4heor-local-preferences/v1";
const EVENT_SCHEMA: u32 = 1;
const REVIEW_ASSURANCE: &str = "app_owned_local_human_assertion";
const MAX_FILE_BYTES: u64 = 128 * 1024;
const MAX_PROPOSALS: usize = 100;
const MAX_PREFERENCES: usize = 100;
const MAX_EVENTS: usize = 2_000;
const MAX_LOG_BYTES: u64 = 4 * 1024 * 1024;
const ALLOWED_SCOPES: &[&str] = &["language", "presentation", "workflow", "audit"];

#[derive(Default)]
pub struct PreferenceReviewState(pub Mutex<()>);

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct PreferenceEvidence {
    interaction_ref: String,
    observed_at: String,
    summary: String,
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct PreferenceProposal {
    schema: String,
    id: String,
    status: String,
    created_at: String,
    scope: String,
    proposed_rule: String,
    evidence: Vec<PreferenceEvidence>,
    counterexamples: Vec<String>,
    review_condition: String,
    expires_at: Option<String>,
    contains_sensitive_data: bool,
    changes_scientific_authority: bool,
}

#[derive(Clone, Debug, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(deny_unknown_fields)]
pub struct AcceptedPreference {
    pub id: String,
    pub scope: String,
    pub rule: String,
    pub source_proposal_sha256: String,
    pub accepted_at: u64,
    pub updated_at: u64,
    pub enabled: bool,
    pub review_condition: String,
    pub expires_at: Option<String>,
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct AcceptedPreferenceSummary {
    pub id: String,
    pub scope: String,
    pub rule: String,
    pub source_proposal_sha256: String,
    pub accepted_at: u64,
    pub updated_at: u64,
    pub enabled: bool,
    pub review_condition: String,
    pub expires_at: Option<String>,
}

impl From<AcceptedPreference> for AcceptedPreferenceSummary {
    fn from(value: AcceptedPreference) -> Self {
        Self {
            id: value.id,
            scope: value.scope,
            rule: value.rule,
            source_proposal_sha256: value.source_proposal_sha256,
            accepted_at: value.accepted_at,
            updated_at: value.updated_at,
            enabled: value.enabled,
            review_condition: value.review_condition,
            expires_at: value.expires_at,
        }
    }
}

#[derive(Clone, Debug, serde::Deserialize, serde::Serialize)]
#[serde(deny_unknown_fields)]
struct PreferenceStore {
    schema: String,
    updated_at: Option<u64>,
    preferences: Vec<AcceptedPreference>,
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PreferenceEvidenceSummary {
    pub interaction_ref: String,
    pub observed_at: String,
    pub summary: String,
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PreferenceProposalSummary {
    pub proposal_id: String,
    pub created_at: String,
    pub scope: String,
    pub proposed_rule: String,
    pub evidence: Vec<PreferenceEvidenceSummary>,
    pub counterexamples: Vec<String>,
    pub review_condition: String,
    pub expires_at: Option<String>,
    pub proposal_sha256: String,
    pub valid: bool,
    pub validation_errors: Vec<String>,
    pub accepted: bool,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum PreferenceReviewAction {
    Accept,
    Update,
    Enable,
    Disable,
    Delete,
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct PreferenceReviewRequest {
    pub project_id: String,
    pub preference_id: String,
    pub proposal_sha256: String,
    pub store_sha256: String,
    pub action: PreferenceReviewAction,
    pub rule: String,
    pub actor_label: String,
    pub rationale: String,
}

#[derive(Clone, Debug, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct PreferenceReviewEvent {
    pub schema_version: u32,
    pub sequence: u64,
    pub review_id: String,
    pub project_id: String,
    pub preference_id: String,
    pub proposal_sha256: String,
    pub before_store_sha256: String,
    pub after_store_sha256: String,
    pub action: PreferenceReviewAction,
    pub rule: String,
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
pub struct PreferenceAudit {
    pub project_available: bool,
    pub project_id: Option<String>,
    pub complete: bool,
    pub store_sha256: String,
    pub proposals: Vec<PreferenceProposalSummary>,
    pub preferences: Vec<AcceptedPreferenceSummary>,
    pub chain_head: Option<String>,
    pub integrity: String,
    pub identity_assurance: String,
    pub errors: Vec<String>,
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
            .is_some_and(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit())
        && value
            .bytes()
            .last()
            .is_some_and(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit())
        && value
            .bytes()
            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit() || byte == b'-')
        && !value.contains("--")
}

fn bounded_text(value: &str, limit: usize) -> bool {
    !value.trim().is_empty()
        && value.len() <= limit
        && !value.chars().any(|character| {
            character == '\0' || character.is_control() && character != '\n' && character != '\t'
        })
}

fn contains_possible_secret(text: &str) -> bool {
    let lower = text.to_ascii_lowercase();
    if text.contains("-----BEGIN PRIVATE KEY-----")
        || text.contains("-----BEGIN RSA PRIVATE KEY-----")
        || text.contains("-----BEGIN EC PRIVATE KEY-----")
        || text.contains("-----BEGIN OPENSSH PRIVATE KEY-----")
        || text
            .split(|character: char| {
                character.is_whitespace() || matches!(character, '"' | '\'' | ',' | ':' | '=')
            })
            .any(|token| token.starts_with("sk-") && token.len() >= 23)
    {
        return true;
    }
    [
        "api_key",
        "api-key",
        "access_token",
        "access-token",
        "client_secret",
        "client-secret",
    ]
    .iter()
    .any(|marker| {
        lower.match_indices(marker).any(|(index, _)| {
            let tail = lower[index + marker.len()..].trim_start();
            let Some(tail) = tail.strip_prefix(':').or_else(|| tail.strip_prefix('=')) else {
                return false;
            };
            tail.trim_start()
                .trim_start_matches(['\'', '"'])
                .split(|character: char| {
                    character.is_whitespace() || matches!(character, '\'' | '"' | ',')
                })
                .next()
                .is_some_and(|value| value.len() >= 12)
        })
    })
}

fn read_bounded_regular(path: &Path, label: &str) -> Result<Vec<u8>, String> {
    let metadata = std::fs::symlink_metadata(path)
        .map_err(|error| format!("{label} cannot be inspected: {error}"))?;
    if !metadata.is_file() || metadata.file_type().is_symlink() || metadata.len() > MAX_FILE_BYTES {
        return Err(format!("{label} must be a bounded regular file"));
    }
    std::fs::read(path).map_err(|error| format!("{label} cannot be read: {error}"))
}

fn validate_proposal(path: &Path) -> Result<(PreferenceProposal, Vec<u8>), String> {
    let raw = read_bounded_regular(path, "preference proposal")?;
    let proposal: PreferenceProposal = serde_json::from_slice(&raw)
        .map_err(|error| format!("preference proposal is invalid JSON: {error}"))?;
    let filename = path.file_stem().and_then(|name| name.to_str());
    if proposal.schema != PROPOSAL_SCHEMA
        || proposal.status != "proposal"
        || !safe_id(&proposal.id)
        || filename != Some(&proposal.id)
        || !bounded_text(&proposal.created_at, 64)
        || !proposal.created_at.ends_with('Z')
        || !ALLOWED_SCOPES.contains(&proposal.scope.as_str())
        || !bounded_text(&proposal.proposed_rule, 600)
        || !bounded_text(&proposal.review_condition, 600)
        || proposal
            .expires_at
            .as_ref()
            .is_some_and(|value| !bounded_text(value, 64) || !value.ends_with('Z'))
        || proposal.contains_sensitive_data
        || proposal.changes_scientific_authority
    {
        return Err("preference proposal violates its root contract".into());
    }
    if proposal.evidence.len() < 2 || proposal.evidence.len() > 64 {
        return Err("preference proposal requires 2-64 independent observations".into());
    }
    let mut references = HashSet::new();
    for evidence in &proposal.evidence {
        if !bounded_text(&evidence.interaction_ref, 300)
            || !references.insert(evidence.interaction_ref.clone())
            || !bounded_text(&evidence.observed_at, 64)
            || !evidence.observed_at.ends_with('Z')
            || !bounded_text(&evidence.summary, 600)
        {
            return Err("preference proposal evidence is invalid or not independent".into());
        }
    }
    if proposal.counterexamples.len() > 64
        || proposal
            .counterexamples
            .iter()
            .any(|item| !bounded_text(item, 600))
    {
        return Err("preference proposal counterexamples are invalid".into());
    }
    let text = std::str::from_utf8(&raw).map_err(|_| "preference proposal must be UTF-8")?;
    if contains_possible_secret(text) {
        return Err("preference proposal may contain a secret".into());
    }
    Ok((proposal, raw))
}

fn validate_preference(preference: &AcceptedPreference) -> Result<(), String> {
    if !safe_id(&preference.id)
        || !ALLOWED_SCOPES.contains(&preference.scope.as_str())
        || !bounded_text(&preference.rule, 600)
        || contains_possible_secret(&preference.rule)
        || !is_sha256(&preference.source_proposal_sha256)
        || preference.accepted_at == 0
        || preference.updated_at < preference.accepted_at
        || !bounded_text(&preference.review_condition, 600)
        || preference
            .expires_at
            .as_ref()
            .is_some_and(|value| !bounded_text(value, 64) || !value.ends_with('Z'))
    {
        return Err(format!("accepted preference {} is invalid", preference.id));
    }
    Ok(())
}

fn read_store(workspace: &Path) -> Result<(PreferenceStore, Vec<u8>), String> {
    let path = workspace.join("learning/preferences.json");
    let raw = read_bounded_regular(&path, "local preference store")?;
    let store: PreferenceStore = serde_json::from_slice(&raw)
        .map_err(|error| format!("local preference store is invalid JSON: {error}"))?;
    if store.schema != STORE_SCHEMA || store.preferences.len() > MAX_PREFERENCES {
        return Err("local preference store violates its root contract".into());
    }
    if store.preferences.is_empty() {
        if store.updated_at.is_some() {
            return Err("an empty preference store must have null updated_at".into());
        }
    } else if store.updated_at.is_none() {
        return Err("a non-empty preference store requires updated_at".into());
    }
    let mut ids = HashSet::new();
    for preference in &store.preferences {
        validate_preference(preference)?;
        if !ids.insert(preference.id.clone()) {
            return Err("local preference ids must be unique".into());
        }
    }
    Ok((store, raw))
}

fn proposal_summaries(
    workspace: &Path,
    accepted: &HashSet<String>,
) -> Result<Vec<PreferenceProposalSummary>, String> {
    let root = workspace.join("learning/proposals");
    let metadata = std::fs::symlink_metadata(&root)
        .map_err(|error| format!("preference proposal store cannot be inspected: {error}"))?;
    if !metadata.is_dir() || metadata.file_type().is_symlink() {
        return Err("preference proposal store must be a real directory".into());
    }
    let mut paths = Vec::new();
    for entry in std::fs::read_dir(&root)
        .map_err(|error| format!("preference proposal store cannot be read: {error}"))?
    {
        let entry =
            entry.map_err(|error| format!("preference proposal entry cannot be read: {error}"))?;
        if entry.file_name() == ".gitkeep" {
            continue;
        }
        paths.push(entry.path());
    }
    if paths.len() > MAX_PROPOSALS {
        return Err(format!(
            "preference proposal store exceeds {MAX_PROPOSALS} entries"
        ));
    }
    paths.sort();
    Ok(paths
        .into_iter()
        .map(|path| match validate_proposal(&path) {
            Ok((proposal, raw)) => PreferenceProposalSummary {
                proposal_id: proposal.id.clone(),
                created_at: proposal.created_at,
                scope: proposal.scope,
                proposed_rule: proposal.proposed_rule,
                evidence: proposal
                    .evidence
                    .into_iter()
                    .map(|item| PreferenceEvidenceSummary {
                        interaction_ref: item.interaction_ref,
                        observed_at: item.observed_at,
                        summary: item.summary,
                    })
                    .collect(),
                counterexamples: proposal.counterexamples,
                review_condition: proposal.review_condition,
                expires_at: proposal.expires_at,
                proposal_sha256: sha256(&raw),
                valid: true,
                validation_errors: Vec::new(),
                accepted: accepted.contains(&proposal.id),
            },
            Err(error) => PreferenceProposalSummary {
                proposal_id: path
                    .file_stem()
                    .and_then(|name| name.to_str())
                    .unwrap_or_default()
                    .into(),
                created_at: String::new(),
                scope: String::new(),
                proposed_rule: String::new(),
                evidence: Vec::new(),
                counterexamples: Vec::new(),
                review_condition: String::new(),
                expires_at: None,
                proposal_sha256: String::new(),
                valid: false,
                validation_errors: vec![error],
                accepted: false,
            },
        })
        .collect())
}

fn ensure_real_directory(workspace: &Path, relative: &Path) -> Result<PathBuf, String> {
    let mut current = workspace.to_path_buf();
    for component in relative.components() {
        let Component::Normal(segment) = component else {
            return Err("preference directory path is unsafe".into());
        };
        current.push(segment);
        match std::fs::symlink_metadata(&current) {
            Ok(metadata) if metadata.is_dir() && !metadata.file_type().is_symlink() => {}
            Ok(_) => {
                return Err(format!(
                    "preference directory is not a real directory: {}",
                    current.display()
                ))
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                std::fs::create_dir(&current)
                    .map_err(|error| format!("preference directory creation failed: {error}"))?;
            }
            Err(error) => return Err(format!("preference directory cannot be inspected: {error}")),
        }
    }
    Ok(current)
}

fn review_root(app: &AppHandle) -> Result<PathBuf, String> {
    use tauri::Manager;
    Ok(app
        .path()
        .app_data_dir()
        .map_err(|error| error.to_string())?
        .join("preference-reviews"))
}

fn review_log_path(root: &Path, project_id: &str) -> Result<PathBuf, String> {
    if project_id.len() != 16 || !project_id.bytes().all(|byte| byte.is_ascii_hexdigit()) {
        return Err("projectId must be the current AI4HEOR project identifier".into());
    }
    Ok(root.join(format!("{project_id}.jsonl")))
}

fn review_record_path_valid(value: &str) -> bool {
    let path = Path::new(value);
    !path.is_absolute()
        && value.starts_with("learning/reviews/")
        && value.ends_with(".json")
        && path
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
}

fn review_snapshot(event: &PreferenceReviewEvent) -> Result<Vec<u8>, String> {
    let value = serde_json::json!({
        "schema": "ai4heor-preference-review/v1",
        "review_id": event.review_id,
        "project_id": event.project_id,
        "preference_id": event.preference_id,
        "proposal_sha256": event.proposal_sha256,
        "before_store_sha256": event.before_store_sha256,
        "after_store_sha256": event.after_store_sha256,
        "action": event.action,
        "rule": event.rule,
        "actor_label": event.actor_label,
        "rationale": event.rationale,
        "timestamp": event.timestamp,
        "assurance": REVIEW_ASSURANCE,
        "decision_authority": "human_researcher",
        "scientific_authority_transferred": false,
    });
    let mut raw = serde_json::to_vec_pretty(&value).map_err(|error| error.to_string())?;
    raw.push(b'\n');
    Ok(raw)
}

fn event_hash(event: &PreferenceReviewEvent) -> Result<String, String> {
    let mut payload = event.clone();
    payload.event_hash.clear();
    serde_json::to_vec(&payload)
        .map(|raw| sha256(&raw))
        .map_err(|error| error.to_string())
}

fn read_review_record(workspace: &Path, event: &PreferenceReviewEvent) -> Result<(), String> {
    if !review_record_path_valid(&event.record_path) {
        return Err("preference review record path is unsafe".into());
    }
    let raw = read_bounded_regular(
        &workspace.join(&event.record_path),
        "preference review record",
    )?;
    if sha256(&raw) != event.record_sha256 || raw != review_snapshot(event)? {
        return Err("preference review record does not match the app-private event".into());
    }
    Ok(())
}

fn read_events(
    root: &Path,
    workspace: &Path,
    project_id: &str,
) -> Result<Vec<PreferenceReviewEvent>, String> {
    let path = review_log_path(root, project_id)?;
    let metadata = match std::fs::symlink_metadata(&path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(format!("preference review log is unavailable: {error}")),
    };
    if !metadata.is_file() || metadata.file_type().is_symlink() || metadata.len() > MAX_LOG_BYTES {
        return Err("preference review log must be a bounded regular file".into());
    }
    let raw = std::fs::read(&path)
        .map_err(|error| format!("preference review log is unavailable: {error}"))?;
    let mut events: Vec<PreferenceReviewEvent> = Vec::new();
    let mut previous_hash = None;
    for (index, line) in raw
        .split(|byte| *byte == b'\n')
        .filter(|line| !line.is_empty())
        .enumerate()
    {
        if index >= MAX_EVENTS {
            return Err(format!("preference review log exceeds {MAX_EVENTS} events"));
        }
        let event: PreferenceReviewEvent = serde_json::from_slice(line)
            .map_err(|error| format!("preference review line {} is invalid: {error}", index + 1))?;
        if event.schema_version != EVENT_SCHEMA
            || event.sequence != index as u64 + 1
            || event.project_id != project_id
            || !safe_id(&event.preference_id)
            || !is_sha256(&event.proposal_sha256)
            || !is_sha256(&event.before_store_sha256)
            || !is_sha256(&event.after_store_sha256)
            || !bounded_text(&event.rule, 600)
            || contains_possible_secret(&event.rule)
            || event.review_id.len() != 32
            || !event.review_id.bytes().all(|byte| byte.is_ascii_hexdigit())
            || !is_sha256(&event.record_sha256)
            || !is_sha256(&event.event_hash)
            || event.assurance != REVIEW_ASSURANCE
            || event.previous_hash != previous_hash
            || !bounded_text(&event.actor_label, 120)
            || !bounded_text(&event.rationale, 2_000)
            || event_hash(&event)? != event.event_hash
        {
            return Err(format!(
                "preference review line {} violates the event contract",
                index + 1
            ));
        }
        if let Some(previous) = events.last() {
            if event.before_store_sha256 != previous.after_store_sha256 {
                return Err(format!(
                    "preference review line {} breaks the store-hash chain",
                    index + 1
                ));
            }
        }
        read_review_record(workspace, &event)?;
        previous_hash = Some(event.event_hash.clone());
        events.push(event);
    }
    Ok(events)
}

fn write_review_record(workspace: &Path, event: &PreferenceReviewEvent) -> Result<(), String> {
    if !review_record_path_valid(&event.record_path) {
        return Err("preference review record path is unsafe".into());
    }
    ensure_real_directory(workspace, Path::new("learning/reviews"))?;
    let target = workspace.join(&event.record_path);
    let raw = review_snapshot(event)?;
    if sha256(&raw) != event.record_sha256 {
        return Err("preference review record hash changed before write".into());
    }
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(target)
        .map_err(|error| format!("preference review record write failed: {error}"))?;
    file.write_all(&raw)
        .and_then(|_| file.sync_all())
        .map_err(|error| format!("preference review record write failed: {error}"))
}

fn append_event(root: &Path, event: &PreferenceReviewEvent) -> Result<(), String> {
    let path = review_log_path(root, &event.project_id)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("preference review log directory failed: {error}"))?;
        crate::runtime::tighten_private(parent);
    }
    if std::fs::symlink_metadata(&path)
        .is_ok_and(|metadata| metadata.file_type().is_symlink() || !metadata.is_file())
    {
        return Err("preference review log must be a regular file".into());
    }
    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|error| format!("preference review log open failed: {error}"))?;
    crate::runtime::tighten_private(&path);
    let line = serde_json::to_string(event).map_err(|error| error.to_string())?;
    writeln!(file, "{line}")
        .and_then(|_| file.sync_all())
        .map_err(|error| format!("preference review log append failed: {error}"))
}

fn store_bytes(store: &PreferenceStore) -> Result<Vec<u8>, String> {
    let mut raw = serde_json::to_vec_pretty(store).map_err(|error| error.to_string())?;
    raw.push(b'\n');
    Ok(raw)
}

struct StoreTransition {
    target: PathBuf,
    backup: PathBuf,
}

fn replace_store(workspace: &Path, raw: &[u8]) -> Result<StoreTransition, String> {
    let learning = ensure_real_directory(workspace, Path::new("learning"))?;
    let target = learning.join("preferences.json");
    read_bounded_regular(&target, "local preference store")?;
    let suffix = crate::runtime::random_hex(8);
    let stage = learning.join(format!(".preferences-stage-{suffix}.json"));
    let backup = learning.join(format!(".preferences-backup-{suffix}.json"));
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&stage)
        .map_err(|error| format!("preference store stage failed: {error}"))?;
    file.write_all(raw)
        .and_then(|_| file.sync_all())
        .map_err(|error| format!("preference store stage failed: {error}"))?;
    std::fs::rename(&target, &backup)
        .map_err(|error| format!("preference store backup failed: {error}"))?;
    if let Err(error) = std::fs::rename(&stage, &target) {
        let _ = std::fs::rename(&backup, &target);
        let _ = std::fs::remove_file(&stage);
        return Err(format!("preference store replacement failed: {error}"));
    }
    Ok(StoreTransition { target, backup })
}

fn rollback_store(transition: &StoreTransition) {
    let _ = std::fs::remove_file(&transition.target);
    let _ = std::fs::rename(&transition.backup, &transition.target);
}

fn finish_store(transition: &StoreTransition) -> Result<(), String> {
    std::fs::remove_file(&transition.backup)
        .map_err(|error| format!("preference store backup cleanup failed: {error}"))
}

fn audit_workspace(
    workspace: &Path,
    root: &Path,
    project_id: &str,
) -> Result<PreferenceAudit, String> {
    let (store, raw) = read_store(workspace)?;
    let store_sha256 = sha256(&raw);
    let events = read_events(root, workspace, project_id)?;
    if let Some(last) = events.last() {
        if last.after_store_sha256 != store_sha256 {
            return Err(
                "local preference store no longer matches the app-owned review chain".into(),
            );
        }
    } else if !store.preferences.is_empty() {
        return Err("non-empty local preferences have no app-owned review chain".into());
    }
    let accepted = store
        .preferences
        .iter()
        .map(|preference| preference.id.clone())
        .collect::<HashSet<_>>();
    Ok(PreferenceAudit {
        project_available: true,
        project_id: Some(project_id.into()),
        complete: true,
        store_sha256,
        proposals: proposal_summaries(workspace, &accepted)?,
        preferences: store.preferences.into_iter().map(Into::into).collect(),
        chain_head: events.last().map(|event| event.event_hash.clone()),
        integrity: "verified_unanchored_sha256_chain".into(),
        identity_assurance: REVIEW_ASSURANCE.into(),
        errors: Vec::new(),
    })
}

fn apply_review(
    workspace: &Path,
    root: &Path,
    project_id: &str,
    request: PreferenceReviewRequest,
) -> Result<PreferenceReviewEvent, String> {
    if request.project_id != project_id
        || !safe_id(&request.preference_id)
        || !is_sha256(&request.proposal_sha256)
        || !is_sha256(&request.store_sha256)
        || !bounded_text(&request.rule, 600)
        || contains_possible_secret(&request.rule)
        || !bounded_text(&request.actor_label, 120)
        || !bounded_text(&request.rationale, 2_000)
    {
        return Err("preference review target, rule, actor, or rationale is invalid".into());
    }
    let (mut store, before_raw) = read_store(workspace)?;
    let before_store_sha256 = sha256(&before_raw);
    if before_store_sha256 != request.store_sha256 {
        return Err("preference review must target the exact current preference store".into());
    }
    let events = read_events(root, workspace, project_id)?;
    if let Some(last) = events.last() {
        if last.after_store_sha256 != before_store_sha256 {
            return Err("preference store does not match the app-owned review chain".into());
        }
    } else if !store.preferences.is_empty() {
        return Err("non-empty local preferences have no app-owned review chain".into());
    }
    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| error.to_string())?
        .as_secs();
    let existing_index = store
        .preferences
        .iter()
        .position(|preference| preference.id == request.preference_id);
    match request.action {
        PreferenceReviewAction::Accept => {
            if existing_index.is_some() {
                return Err("this preference id is already accepted".into());
            }
            let proposal_path = workspace
                .join("learning/proposals")
                .join(format!("{}.json", request.preference_id));
            let (proposal, proposal_raw) = validate_proposal(&proposal_path)?;
            if sha256(&proposal_raw) != request.proposal_sha256 {
                return Err("acceptance must target the exact current proposal bytes".into());
            }
            store.preferences.push(AcceptedPreference {
                id: proposal.id,
                scope: proposal.scope,
                rule: request.rule.clone(),
                source_proposal_sha256: request.proposal_sha256.clone(),
                accepted_at: now,
                updated_at: now,
                enabled: true,
                review_condition: proposal.review_condition,
                expires_at: proposal.expires_at,
            });
        }
        PreferenceReviewAction::Update => {
            let index = existing_index.ok_or("the accepted preference does not exist")?;
            let preference = &mut store.preferences[index];
            if preference.source_proposal_sha256 != request.proposal_sha256 {
                return Err("update must target the accepted proposal binding".into());
            }
            preference.rule = request.rule.clone();
            preference.updated_at = now;
        }
        PreferenceReviewAction::Enable | PreferenceReviewAction::Disable => {
            let index = existing_index.ok_or("the accepted preference does not exist")?;
            let preference = &mut store.preferences[index];
            if preference.source_proposal_sha256 != request.proposal_sha256
                || preference.rule != request.rule
            {
                return Err("state change must target the exact accepted preference".into());
            }
            let enabled = request.action == PreferenceReviewAction::Enable;
            if preference.enabled == enabled {
                return Err("the preference already has the requested state".into());
            }
            preference.enabled = enabled;
            preference.updated_at = now;
        }
        PreferenceReviewAction::Delete => {
            let index = existing_index.ok_or("the accepted preference does not exist")?;
            let preference = &store.preferences[index];
            if preference.source_proposal_sha256 != request.proposal_sha256
                || preference.rule != request.rule
            {
                return Err("deletion must target the exact accepted preference".into());
            }
            store.preferences.remove(index);
        }
    }
    store
        .preferences
        .sort_by(|left, right| left.id.cmp(&right.id));
    for preference in &store.preferences {
        validate_preference(preference)?;
    }
    store.updated_at = if store.preferences.is_empty() {
        None
    } else {
        Some(now)
    };
    let after_raw = store_bytes(&store)?;
    let after_store_sha256 = sha256(&after_raw);
    if after_store_sha256 == before_store_sha256 {
        return Err("preference review did not change the exact store bytes".into());
    }

    let review_id = crate::runtime::random_hex(16);
    let record_path = format!(
        "learning/reviews/{}-{review_id}.json",
        request.preference_id
    );
    let mut event = PreferenceReviewEvent {
        schema_version: EVENT_SCHEMA,
        sequence: events.len() as u64 + 1,
        review_id,
        project_id: project_id.into(),
        preference_id: request.preference_id,
        proposal_sha256: request.proposal_sha256,
        before_store_sha256,
        after_store_sha256,
        action: request.action,
        rule: request.rule,
        actor_label: request.actor_label,
        rationale: request.rationale,
        timestamp: now,
        record_path,
        record_sha256: String::new(),
        assurance: REVIEW_ASSURANCE.into(),
        previous_hash: events.last().map(|event| event.event_hash.clone()),
        event_hash: String::new(),
    };
    event.record_sha256 = sha256(&review_snapshot(&event)?);
    event.event_hash = event_hash(&event)?;

    let transition = replace_store(workspace, &after_raw)?;
    let persist = write_review_record(workspace, &event).and_then(|_| append_event(root, &event));
    if let Err(error) = persist {
        let _ = std::fs::remove_file(workspace.join(&event.record_path));
        rollback_store(&transition);
        return Err(error);
    }
    if let Err(error) = finish_store(&transition) {
        // The store, immutable workspace snapshot, and private audit event are
        // already committed. Backup cleanup must not make the UI report that
        // the Human decision failed and invite an unsafe retry.
        eprintln!("AI4HEOR preference-store backup cleanup failed: {error}");
    }
    crate::git_snapshot::commit_best_effort(
        workspace,
        "Record AI4HEOR local preference Human review",
    );
    Ok(event)
}

#[tauri::command(async)]
pub fn audit_local_preferences(
    app: AppHandle,
    state: tauri::State<PreferenceReviewState>,
) -> Result<PreferenceAudit, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "preference review lock poisoned")?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    let project_id = match crate::project::require_project_id(&workspace) {
        Ok(project_id) => project_id,
        Err(_) => {
            return Ok(PreferenceAudit {
                project_available: false,
                project_id: None,
                complete: true,
                store_sha256: String::new(),
                proposals: Vec::new(),
                preferences: Vec::new(),
                chain_head: None,
                integrity: "not_applicable".into(),
                identity_assurance: REVIEW_ASSURANCE.into(),
                errors: Vec::new(),
            });
        }
    };
    audit_workspace(&workspace, &review_root(&app)?, &project_id)
}

#[tauri::command(async)]
pub fn append_local_preference_review(
    app: AppHandle,
    state: tauri::State<PreferenceReviewState>,
    request: PreferenceReviewRequest,
) -> Result<PreferenceReviewEvent, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "preference review lock poisoned")?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    let project_id = crate::project::require_project_id(&workspace)?;
    apply_review(&workspace, &review_root(&app)?, &project_id, request)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn workspace(tag: &str) -> (PathBuf, PathBuf, String) {
        let root = std::env::temp_dir().join(format!(
            "ai4heor-preference-{tag}-{}-{}",
            std::process::id(),
            crate::runtime::random_hex(4)
        ));
        let workspace = root.join("workspace");
        let reviews = root.join("private");
        std::fs::create_dir_all(workspace.join("learning/proposals")).unwrap();
        std::fs::create_dir_all(workspace.join("learning/reviews")).unwrap();
        std::fs::write(
            workspace.join("learning/preferences.json"),
            b"{\n  \"schema\": \"ai4heor-local-preferences/v1\",\n  \"updated_at\": null,\n  \"preferences\": []\n}\n",
        )
        .unwrap();
        (workspace, reviews, "0123456789abcdef".into())
    }

    fn proposal(workspace: &Path, id: &str) -> String {
        let value = serde_json::json!({
            "schema": PROPOSAL_SCHEMA,
            "id": id,
            "status": "proposal",
            "created_at": "2026-07-19T13:00:00Z",
            "scope": "presentation",
            "proposed_rule": "Use a concise Chinese note below every HEOR result table.",
            "evidence": [
                {"interaction_ref": "session-a", "observed_at": "2026-07-19T12:00:00Z", "summary": "Researcher requested a concise Chinese note."},
                {"interaction_ref": "session-b", "observed_at": "2026-07-19T12:30:00Z", "summary": "The same presentation preference was requested again."}
            ],
            "counterexamples": [],
            "review_condition": "Review if the output language changes.",
            "expires_at": null,
            "contains_sensitive_data": false,
            "changes_scientific_authority": false
        });
        let raw = serde_json::to_vec_pretty(&value).unwrap();
        std::fs::write(
            workspace
                .join("learning/proposals")
                .join(format!("{id}.json")),
            &raw,
        )
        .unwrap();
        sha256(&raw)
    }

    fn request(
        project_id: &str,
        proposal_sha256: &str,
        store_sha256: &str,
        action: PreferenceReviewAction,
        rule: &str,
    ) -> PreferenceReviewRequest {
        PreferenceReviewRequest {
            project_id: project_id.into(),
            preference_id: "table-note-language".into(),
            proposal_sha256: proposal_sha256.into(),
            store_sha256: store_sha256.into(),
            action,
            rule: rule.into(),
            actor_label: "Local researcher".into(),
            rationale: "Observed twice and reviewed as a presentation preference only.".into(),
        }
    }

    #[test]
    fn preference_roundtrip_is_human_owned_hash_bound_and_reversible() {
        let (workspace, reviews, project_id) = workspace("roundtrip");
        let proposal_sha = proposal(&workspace, "table-note-language");
        let audit = audit_workspace(&workspace, &reviews, &project_id).unwrap();
        let accepted = apply_review(
            &workspace,
            &reviews,
            &project_id,
            request(
                &project_id,
                &proposal_sha,
                &audit.store_sha256,
                PreferenceReviewAction::Accept,
                "Use concise Chinese notes below reviewed HEOR result tables.",
            ),
        )
        .unwrap();
        let audit = audit_workspace(&workspace, &reviews, &project_id).unwrap();
        assert_eq!(audit.preferences.len(), 1);
        assert!(audit.preferences[0].enabled);
        assert!(audit.proposals[0].accepted);

        let updated = apply_review(
            &workspace,
            &reviews,
            &project_id,
            request(
                &project_id,
                &proposal_sha,
                &audit.store_sha256,
                PreferenceReviewAction::Update,
                "Use one concise Chinese note below reviewed HEOR result tables.",
            ),
        )
        .unwrap();
        assert_eq!(
            updated.previous_hash.as_deref(),
            Some(accepted.event_hash.as_str())
        );
        let audit = audit_workspace(&workspace, &reviews, &project_id).unwrap();
        assert_eq!(
            audit.preferences[0].rule,
            "Use one concise Chinese note below reviewed HEOR result tables."
        );

        let disabled = apply_review(
            &workspace,
            &reviews,
            &project_id,
            request(
                &project_id,
                &proposal_sha,
                &audit.store_sha256,
                PreferenceReviewAction::Disable,
                &audit.preferences[0].rule,
            ),
        )
        .unwrap();
        assert_eq!(
            disabled.previous_hash.as_deref(),
            Some(updated.event_hash.as_str())
        );
        let audit = audit_workspace(&workspace, &reviews, &project_id).unwrap();
        assert!(!audit.preferences[0].enabled);

        apply_review(
            &workspace,
            &reviews,
            &project_id,
            request(
                &project_id,
                &proposal_sha,
                &audit.store_sha256,
                PreferenceReviewAction::Enable,
                &audit.preferences[0].rule,
            ),
        )
        .unwrap();
        let audit = audit_workspace(&workspace, &reviews, &project_id).unwrap();
        assert!(audit.preferences[0].enabled);

        apply_review(
            &workspace,
            &reviews,
            &project_id,
            request(
                &project_id,
                &proposal_sha,
                &audit.store_sha256,
                PreferenceReviewAction::Delete,
                &audit.preferences[0].rule,
            ),
        )
        .unwrap();
        let audit = audit_workspace(&workspace, &reviews, &project_id).unwrap();
        assert!(audit.preferences.is_empty());
        assert_eq!(audit.proposals.len(), 1);
        std::fs::remove_dir_all(workspace.parent().unwrap()).unwrap();
    }

    #[test]
    fn one_observation_or_sensitive_proposal_never_enters_the_store() {
        let (workspace, reviews, project_id) = workspace("invalid-proposal");
        let proposal_sha = proposal(&workspace, "table-note-language");
        let path = workspace.join("learning/proposals/table-note-language.json");
        let mut value: serde_json::Value =
            serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
        value["evidence"] = serde_json::json!([value["evidence"][0].clone()]);
        value["contains_sensitive_data"] = serde_json::json!(true);
        std::fs::write(&path, serde_json::to_vec_pretty(&value).unwrap()).unwrap();
        let audit = audit_workspace(&workspace, &reviews, &project_id).unwrap();
        assert!(!audit.proposals[0].valid);
        let error = apply_review(
            &workspace,
            &reviews,
            &project_id,
            request(
                &project_id,
                &proposal_sha,
                &audit.store_sha256,
                PreferenceReviewAction::Accept,
                "Use Chinese notes.",
            ),
        )
        .unwrap_err();
        assert!(error.contains("violates") || error.contains("requires"));
        assert!(read_store(&workspace).unwrap().0.preferences.is_empty());
        std::fs::remove_dir_all(workspace.parent().unwrap()).unwrap();
    }

    #[test]
    fn stale_store_hash_and_manual_store_edits_fail_closed() {
        let (workspace, reviews, project_id) = workspace("store-drift");
        let proposal_sha = proposal(&workspace, "table-note-language");
        let audit = audit_workspace(&workspace, &reviews, &project_id).unwrap();
        let stale = "0".repeat(64);
        assert!(apply_review(
            &workspace,
            &reviews,
            &project_id,
            request(
                &project_id,
                &proposal_sha,
                &stale,
                PreferenceReviewAction::Accept,
                "Use Chinese notes.",
            ),
        )
        .unwrap_err()
        .contains("exact current"));
        apply_review(
            &workspace,
            &reviews,
            &project_id,
            request(
                &project_id,
                &proposal_sha,
                &audit.store_sha256,
                PreferenceReviewAction::Accept,
                "Use Chinese notes.",
            ),
        )
        .unwrap();
        let path = workspace.join("learning/preferences.json");
        let mut raw = std::fs::read(&path).unwrap();
        raw.push(b' ');
        std::fs::write(path, raw).unwrap();
        assert!(audit_workspace(&workspace, &reviews, &project_id)
            .unwrap_err()
            .contains("no longer matches"));
        std::fs::remove_dir_all(workspace.parent().unwrap()).unwrap();
    }

    #[test]
    fn tampered_preference_review_snapshot_breaks_the_chain() {
        let (workspace, reviews, project_id) = workspace("snapshot-drift");
        let proposal_sha = proposal(&workspace, "table-note-language");
        let audit = audit_workspace(&workspace, &reviews, &project_id).unwrap();
        let event = apply_review(
            &workspace,
            &reviews,
            &project_id,
            request(
                &project_id,
                &proposal_sha,
                &audit.store_sha256,
                PreferenceReviewAction::Accept,
                "Use Chinese notes.",
            ),
        )
        .unwrap();
        std::fs::write(workspace.join(event.record_path), b"{}\n").unwrap();
        assert!(audit_workspace(&workspace, &reviews, &project_id)
            .unwrap_err()
            .contains("does not match"));
        std::fs::remove_dir_all(workspace.parent().unwrap()).unwrap();
    }
}
