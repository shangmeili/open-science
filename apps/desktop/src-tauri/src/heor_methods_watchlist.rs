//! Independent native audit for the dated HEOR methods watchlist.

use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::io::Write;
use std::path::{Component, Path, PathBuf};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager};

const WATCHLIST_PATH: &str = "heor/methods-watchlist.json";
const ARTIFACT_CAP_BYTES: u64 = 5 * 1024 * 1024;
const REVIEW_EVENT_SCHEMA: u32 = 1;
const REVIEW_ASSURANCE: &str = "app_owned_local_human_assertion";

#[derive(Default)]
pub struct MethodsWatchlistReviewState(pub Mutex<()>);

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MethodsWatchlistAudit {
    pub exists: bool,
    pub complete: bool,
    pub reviewable: bool,
    pub status: String,
    pub watchlist_id: String,
    pub as_of_date: String,
    pub watchlist_sha256: Option<String>,
    pub source_count: usize,
    pub current_count: usize,
    pub draft_count: usize,
    pub unknown_count: usize,
    pub overdue_count: usize,
    pub change_count: usize,
    pub reviewed_change_count: usize,
    pub unresolved_change_count: usize,
    pub affected_contract_count: usize,
    pub overdue_sources: Vec<String>,
    pub unresolved_changes: Vec<String>,
    pub acceptance_eligible_changes: Vec<String>,
    pub errors: Vec<String>,
}

impl MethodsWatchlistAudit {
    fn missing() -> Self {
        Self {
            exists: false,
            complete: false,
            reviewable: false,
            status: "missing".into(),
            watchlist_id: String::new(),
            as_of_date: String::new(),
            watchlist_sha256: None,
            source_count: 0,
            current_count: 0,
            draft_count: 0,
            unknown_count: 0,
            overdue_count: 0,
            change_count: 0,
            reviewed_change_count: 0,
            unresolved_change_count: 0,
            affected_contract_count: 0,
            overdue_sources: Vec::new(),
            unresolved_changes: Vec::new(),
            acceptance_eligible_changes: Vec::new(),
            errors: Vec::new(),
        }
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Watchlist {
    schema_version: String,
    watchlist_id: String,
    status: String,
    as_of_date: String,
    source_order: Vec<String>,
    sources: HashMap<String, Source>,
    change_order: Vec<String>,
    changes: HashMap<String, Change>,
    limitations: Vec<String>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Source {
    source_id: String,
    title: String,
    organization: String,
    jurisdiction: String,
    source_type: String,
    publication_status: String,
    canonical_url: String,
    access_mode: String,
    rights_status: String,
    rights_note: String,
    revision: Revision,
    snapshot: Option<Snapshot>,
    affected_contracts: Vec<String>,
    monitoring_notes: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Revision {
    label: String,
    published_on: Option<String>,
    last_checked_on: String,
    next_check_due: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Snapshot {
    path: String,
    content_sha256: String,
    media_type: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Change {
    change_id: String,
    source_id: String,
    detected_on: String,
    change_status: String,
    previous_revision: String,
    current_revision: String,
    changed_sections: Vec<String>,
    summary: String,
    affected_contracts: Vec<String>,
    required_actions: Vec<String>,
    revalidation_status: String,
    evidence_paths: Vec<String>,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum MethodsWatchlistReviewAction {
    AcceptRevalidation,
    DismissChange,
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct MethodsWatchlistReviewRequest {
    pub project_id: String,
    pub watchlist_sha256: String,
    pub change_id: String,
    pub action: MethodsWatchlistReviewAction,
    pub actor_label: String,
    pub rationale: String,
}

#[derive(Clone, Debug, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct MethodsWatchlistReviewEvent {
    pub schema_version: u32,
    pub sequence: u64,
    pub review_id: String,
    pub project_id: String,
    pub watchlist_id: String,
    pub watchlist_sha256: String,
    pub change_id: String,
    pub action: MethodsWatchlistReviewAction,
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
pub struct MethodsWatchlistReviewLog {
    pub events: Vec<MethodsWatchlistReviewEvent>,
    pub chain_head: Option<String>,
    pub integrity: &'static str,
    pub identity_assurance: &'static str,
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn is_nonempty(value: &str) -> bool {
    !value.trim().is_empty() && value.len() <= 2_000
}

fn is_safe_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 128
        && value
            .bytes()
            .next()
            .is_some_and(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit())
        && value.bytes().all(|byte| {
            byte.is_ascii_lowercase() || byte.is_ascii_digit() || matches!(byte, b'.' | b'_' | b'-')
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
    let (Some(year), Some(month), Some(day)) = (parts.next(), parts.next(), parts.next()) else {
        return false;
    };
    if parts.next().is_some() || year.len() != 4 || month.len() != 2 || day.len() != 2 {
        return false;
    }
    let (Ok(year), Ok(month), Ok(day)) =
        (year.parse::<u16>(), month.parse::<u8>(), day.parse::<u8>())
    else {
        return false;
    };
    if year == 0 || !(1..=12).contains(&month) {
        return false;
    }
    let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    let maximum = match month {
        2 if leap => 29,
        2 => 28,
        4 | 6 | 9 | 11 => 30,
        _ => 31,
    };
    (1..=maximum).contains(&day)
}

fn unique_nonempty(values: &[String], required: bool) -> bool {
    (!required || !values.is_empty())
        && values.len() <= 256
        && values
            .iter()
            .all(|value| is_nonempty(value) && value.len() <= 500)
        && values.iter().collect::<HashSet<_>>().len() == values.len()
}

fn safe_local_file(workspace: &Path, relative: &str) -> Result<std::path::PathBuf, String> {
    let relative_path = Path::new(relative);
    if !relative.starts_with("heor/method-sources/")
        || relative_path.is_absolute()
        || relative_path
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err(format!(
            "{relative} must be a safe path below heor/method-sources/"
        ));
    }
    let path = workspace.join(relative_path);
    let metadata = std::fs::symlink_metadata(&path)
        .map_err(|_| format!("{relative} must identify an existing regular file"))?;
    if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
        return Err(format!(
            "{relative} must identify a regular non-symlink file"
        ));
    }
    let workspace = workspace
        .canonicalize()
        .map_err(|error| error.to_string())?;
    let canonical = path.canonicalize().map_err(|error| error.to_string())?;
    if !canonical.starts_with(&workspace) {
        return Err(format!("{relative} escapes the workspace"));
    }
    Ok(canonical)
}

fn read_artifact(path: &Path) -> Result<Vec<u8>, String> {
    let metadata = std::fs::symlink_metadata(path).map_err(|error| error.to_string())?;
    if !metadata.file_type().is_file()
        || metadata.file_type().is_symlink()
        || metadata.len() > ARTIFACT_CAP_BYTES
    {
        return Err("methods watchlist is not a reviewable regular file".into());
    }
    std::fs::read(path).map_err(|error| error.to_string())
}

fn audit_value(
    workspace: &Path,
    raw: &[u8],
    reviewed_changes: &HashSet<String>,
) -> MethodsWatchlistAudit {
    let mut audit = MethodsWatchlistAudit::missing();
    audit.exists = true;
    audit.status = "invalid".into();
    audit.watchlist_sha256 = Some(sha256(raw));
    let watchlist: Watchlist = match serde_json::from_slice(raw) {
        Ok(value) => value,
        Err(error) => {
            audit
                .errors
                .push(format!("methods watchlist is invalid: {error}"));
            return audit;
        }
    };
    audit.status.clone_from(&watchlist.status);
    audit.watchlist_id.clone_from(&watchlist.watchlist_id);
    audit.as_of_date.clone_from(&watchlist.as_of_date);
    audit.source_count = watchlist.sources.len();
    audit.change_count = watchlist.changes.len();
    if watchlist.schema_version != "0.2.0" {
        audit.errors.push("schema_version must be 0.2.0".into());
    }
    if !is_safe_id(&watchlist.watchlist_id) {
        audit.errors.push("watchlist_id is invalid".into());
    }
    if !matches!(
        watchlist.status.as_str(),
        "draft" | "ready_for_human_review"
    ) {
        audit.errors.push("status is invalid".into());
    }
    if !is_iso_date(&watchlist.as_of_date) {
        audit.errors.push("as_of_date is invalid".into());
    }
    if !unique_nonempty(&watchlist.source_order, false)
        || watchlist.source_order.iter().collect::<HashSet<_>>()
            != watchlist.sources.keys().collect::<HashSet<_>>()
    {
        audit
            .errors
            .push("source_order must contain each source exactly once".into());
    }
    if !unique_nonempty(&watchlist.change_order, false)
        || watchlist.change_order.iter().collect::<HashSet<_>>()
            != watchlist.changes.keys().collect::<HashSet<_>>()
    {
        audit
            .errors
            .push("change_order must contain each change exactly once".into());
    }
    if !unique_nonempty(&watchlist.limitations, true) {
        audit
            .errors
            .push("limitations must contain unique non-empty strings".into());
    }
    let mut affected = HashSet::new();
    for source_id in &watchlist.source_order {
        let Some(source) = watchlist.sources.get(source_id) else {
            continue;
        };
        if !is_safe_id(source_id) || source.source_id != *source_id {
            audit
                .errors
                .push(format!("source {source_id} has an invalid identity"));
        }
        if [
            &source.title,
            &source.organization,
            &source.jurisdiction,
            &source.rights_note,
            &source.monitoring_notes,
        ]
        .iter()
        .any(|value| !is_nonempty(value))
        {
            audit
                .errors
                .push(format!("source {source_id} has empty descriptive fields"));
        }
        if !matches!(
            source.source_type.as_str(),
            "reference_case"
                | "reporting_standard"
                | "method_guideline"
                | "regulation"
                | "consultation_draft"
                | "technical_standard"
        ) {
            audit
                .errors
                .push(format!("source {source_id} has an unsupported type"));
        }
        match source.publication_status.as_str() {
            "current" => audit.current_count += 1,
            "draft" => audit.draft_count += 1,
            "unknown" => audit.unknown_count += 1,
            "superseded" | "withdrawn" => {}
            _ => audit.errors.push(format!(
                "source {source_id} has an invalid publication status"
            )),
        }
        if !source.canonical_url.starts_with("https://")
            || source.canonical_url[8..]
                .split('/')
                .next()
                .unwrap_or_default()
                .is_empty()
        {
            audit.errors.push(format!(
                "source {source_id} requires an HTTPS canonical URL"
            ));
        }
        if !unique_nonempty(&source.affected_contracts, true) {
            audit
                .errors
                .push(format!("source {source_id} has invalid affected contracts"));
        }
        affected.extend(source.affected_contracts.iter().cloned());
        let revision = &source.revision;
        if !is_nonempty(&revision.label)
            || !is_iso_date(&revision.last_checked_on)
            || !is_iso_date(&revision.next_check_due)
            || revision
                .published_on
                .as_deref()
                .is_some_and(|value| !is_iso_date(value))
        {
            audit
                .errors
                .push(format!("source {source_id} has invalid revision dates"));
        } else {
            if revision
                .published_on
                .as_deref()
                .is_some_and(|value| value > revision.last_checked_on.as_str())
                || revision.last_checked_on > watchlist.as_of_date
                || revision.next_check_due < revision.last_checked_on
            {
                audit.errors.push(format!(
                    "source {source_id} has inconsistent revision dates"
                ));
            }
            if revision.next_check_due < watchlist.as_of_date {
                audit.overdue_sources.push(source_id.clone());
            }
        }
        match (
            source.access_mode.as_str(),
            source.rights_status.as_str(),
            &source.snapshot,
        ) {
            ("link_only", "link_only", None) => {}
            (
                "local_snapshot",
                "permission_confirmed" | "open_licence" | "personal_research",
                Some(snapshot),
            ) => {
                if !matches!(
                    snapshot.media_type.as_str(),
                    "application/pdf"
                        | "text/html"
                        | "text/markdown"
                        | "text/plain"
                        | "application/json"
                ) || !is_sha256(&snapshot.content_sha256)
                {
                    audit
                        .errors
                        .push(format!("source {source_id} has invalid snapshot metadata"));
                } else {
                    match safe_local_file(workspace, &snapshot.path) {
                        Ok(path) => match std::fs::read(path) {
                            Ok(bytes) if sha256(&bytes) == snapshot.content_sha256 => {}
                            Ok(_) => audit
                                .errors
                                .push(format!("source {source_id} snapshot hash differs")),
                            Err(error) => audit.errors.push(error.to_string()),
                        },
                        Err(error) => audit.errors.push(error),
                    }
                }
            }
            _ => audit.errors.push(format!(
                "source {source_id} has an invalid access/rights boundary"
            )),
        }
    }
    for change_id in &watchlist.change_order {
        let Some(change) = watchlist.changes.get(change_id) else {
            continue;
        };
        if !is_safe_id(change_id)
            || change.change_id != *change_id
            || !watchlist.sources.contains_key(&change.source_id)
        {
            audit.errors.push(format!(
                "change {change_id} has an invalid identity or source"
            ));
        }
        if !is_iso_date(&change.detected_on) || change.detected_on > watchlist.as_of_date {
            audit
                .errors
                .push(format!("change {change_id} has an invalid detected date"));
        }
        if [
            &change.previous_revision,
            &change.current_revision,
            &change.summary,
        ]
        .iter()
        .any(|value| !is_nonempty(value))
            || !unique_nonempty(&change.changed_sections, true)
            || !unique_nonempty(&change.affected_contracts, true)
            || !unique_nonempty(&change.required_actions, true)
            || !unique_nonempty(&change.evidence_paths, false)
        {
            audit
                .errors
                .push(format!("change {change_id} has invalid details"));
        }
        affected.extend(change.affected_contracts.iter().cloned());
        for path in &change.evidence_paths {
            if let Err(error) = safe_local_file(workspace, path) {
                audit.errors.push(error);
            }
        }
        if !matches!(change.change_status.as_str(), "suspected" | "confirmed")
            || !matches!(
                change.revalidation_status.as_str(),
                "not_started" | "in_progress" | "ready_for_human_review"
            )
        {
            audit
                .errors
                .push(format!("change {change_id} has an invalid state"));
        }
        if reviewed_changes.contains(change_id) {
            audit.reviewed_change_count += 1;
        } else {
            audit.unresolved_changes.push(change_id.clone());
            if change.change_status == "confirmed"
                && change.revalidation_status == "ready_for_human_review"
            {
                audit.acceptance_eligible_changes.push(change_id.clone());
            }
        }
    }
    audit.overdue_count = audit.overdue_sources.len();
    audit.unresolved_change_count = audit.unresolved_changes.len();
    audit.affected_contract_count = affected.len();
    audit.reviewable = audit.errors.is_empty()
        && audit.status == "ready_for_human_review"
        && audit.source_count > 0
        && audit.change_count > 0;
    audit.complete = audit.errors.is_empty()
        && audit.status == "ready_for_human_review"
        && audit.source_count > 0
        && audit.overdue_sources.is_empty()
        && audit.unresolved_changes.is_empty();
    audit
}

fn valid_project_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 80
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
}

fn valid_review_text(value: &str, maximum: usize) -> bool {
    value == value.trim() && !value.is_empty() && value.chars().count() <= maximum
}

fn review_root(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app
        .path()
        .app_data_dir()
        .map_err(|error| error.to_string())?
        .join("heor")
        .join("methods-watchlist-reviews"))
}

fn review_log_path(root: &Path, project_id: &str) -> Result<PathBuf, String> {
    if !valid_project_id(project_id) {
        return Err("projectId must be a safe identifier".into());
    }
    Ok(root.join(format!("{project_id}.jsonl")))
}

fn review_event_hash(event: &MethodsWatchlistReviewEvent) -> Result<String, String> {
    let mut payload = event.clone();
    payload.event_hash.clear();
    serde_json::to_vec(&payload)
        .map(|raw| sha256(&raw))
        .map_err(|error| error.to_string())
}

fn review_snapshot(event: &MethodsWatchlistReviewEvent) -> Result<Vec<u8>, String> {
    let value = serde_json::json!({
        "schema_version": "0.1.0",
        "review_id": event.review_id,
        "project_id": event.project_id,
        "watchlist_id": event.watchlist_id,
        "watchlist_sha256": event.watchlist_sha256,
        "change_id": event.change_id,
        "action": event.action,
        "status": match event.action {
            MethodsWatchlistReviewAction::AcceptRevalidation => "revalidation_accepted",
            MethodsWatchlistReviewAction::DismissChange => "change_dismissed",
        },
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

fn review_record_path_valid(value: &str) -> bool {
    let relative = Path::new(value);
    !relative.is_absolute()
        && value.starts_with("heor/methods-watchlist-reviews/")
        && relative
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
}

fn read_review_record(workspace: &Path, relative: &str) -> Result<Vec<u8>, String> {
    if !review_record_path_valid(relative) {
        return Err("methods watchlist review record path is unsafe".into());
    }
    let path = workspace.join(relative);
    let metadata = std::fs::symlink_metadata(&path)
        .map_err(|error| format!("methods watchlist review record unavailable: {error}"))?;
    if !metadata.file_type().is_file()
        || metadata.file_type().is_symlink()
        || metadata.len() > ARTIFACT_CAP_BYTES
    {
        return Err("methods watchlist review record is not a regular bounded file".into());
    }
    std::fs::read(path)
        .map_err(|error| format!("methods watchlist review record unavailable: {error}"))
}

fn read_review_events(
    root: &Path,
    workspace: &Path,
    project_id: &str,
) -> Result<Vec<MethodsWatchlistReviewEvent>, String> {
    let path = review_log_path(root, project_id)?;
    let metadata = match std::fs::symlink_metadata(&path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(format!("methods watchlist review log unavailable: {error}")),
    };
    if !metadata.file_type().is_file()
        || metadata.file_type().is_symlink()
        || metadata.len() > 4 * 1024 * 1024
    {
        return Err("methods watchlist review log is not a regular bounded file".into());
    }
    let raw = std::fs::read(&path)
        .map_err(|error| format!("methods watchlist review log unavailable: {error}"))?;
    let mut events = Vec::new();
    let mut previous_hash = None;
    for (index, line) in raw
        .split(|byte| *byte == b'\n')
        .filter(|line| !line.is_empty())
        .enumerate()
    {
        if events.len() >= 2_000 {
            return Err("methods watchlist review log exceeds 2,000 events".into());
        }
        let event: MethodsWatchlistReviewEvent = serde_json::from_slice(line).map_err(|error| {
            format!(
                "methods watchlist review line {} is invalid: {error}",
                index + 1
            )
        })?;
        if event.schema_version != REVIEW_EVENT_SCHEMA
            || event.sequence != index as u64 + 1
            || event.project_id != project_id
            || !is_safe_id(&event.watchlist_id)
            || !is_safe_id(&event.change_id)
            || event.review_id.len() != 32
            || !event.review_id.bytes().all(|byte| byte.is_ascii_hexdigit())
            || !is_sha256(&event.watchlist_sha256)
            || !is_sha256(&event.record_sha256)
            || !is_sha256(&event.event_hash)
            || event.assurance != REVIEW_ASSURANCE
            || event.previous_hash != previous_hash
            || !valid_review_text(&event.actor_label, 120)
            || !valid_review_text(&event.rationale, 2_000)
            || review_event_hash(&event)? != event.event_hash
        {
            return Err(format!(
                "methods watchlist review line {} violates the event contract",
                index + 1
            ));
        }
        let record = read_review_record(workspace, &event.record_path)?;
        if sha256(&record) != event.record_sha256 || record != review_snapshot(&event)? {
            return Err(format!(
                "methods watchlist review line {} record binding is invalid",
                index + 1
            ));
        }
        previous_hash = Some(event.event_hash.clone());
        events.push(event);
    }
    Ok(events)
}

fn effective_reviewed_changes(
    events: &[MethodsWatchlistReviewEvent],
    watchlist_sha256: &str,
) -> HashSet<String> {
    events
        .iter()
        .filter(|event| event.watchlist_sha256 == watchlist_sha256)
        .map(|event| event.change_id.clone())
        .collect()
}

fn write_review_record(
    workspace: &Path,
    event: &MethodsWatchlistReviewEvent,
) -> Result<(), String> {
    if !review_record_path_valid(&event.record_path) {
        return Err("methods watchlist review record path is unsafe".into());
    }
    let target = workspace.join(&event.record_path);
    let parent = target
        .parent()
        .ok_or("methods watchlist review record parent is invalid")?;
    std::fs::create_dir_all(parent)
        .map_err(|error| format!("methods watchlist review directory failed: {error}"))?;
    if std::fs::symlink_metadata(parent).is_ok_and(|metadata| metadata.file_type().is_symlink()) {
        return Err("methods watchlist review directory must not be a symlink".into());
    }
    let raw = review_snapshot(event)?;
    if sha256(&raw) != event.record_sha256 {
        return Err("methods watchlist review record hash changed before write".into());
    }
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(target)
        .map_err(|error| format!("methods watchlist review record write failed: {error}"))?;
    file.write_all(&raw)
        .and_then(|_| file.sync_all())
        .map_err(|error| format!("methods watchlist review record write failed: {error}"))
}

fn append_review_event(root: &Path, event: &MethodsWatchlistReviewEvent) -> Result<(), String> {
    let path = review_log_path(root, &event.project_id)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("methods watchlist review log directory failed: {error}"))?;
        crate::runtime::tighten_private(parent);
    }
    if std::fs::symlink_metadata(&path)
        .is_ok_and(|metadata| metadata.file_type().is_symlink() || !metadata.file_type().is_file())
    {
        return Err("methods watchlist review log must be a regular file".into());
    }
    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|error| format!("methods watchlist review log open failed: {error}"))?;
    crate::runtime::tighten_private(&path);
    let line = serde_json::to_string(event).map_err(|error| error.to_string())?;
    writeln!(file, "{line}")
        .and_then(|_| file.sync_all())
        .map_err(|error| format!("methods watchlist review log append failed: {error}"))
}

#[tauri::command(async)]
pub fn audit_heor_methods_watchlist(
    app: AppHandle,
    state: tauri::State<MethodsWatchlistReviewState>,
) -> Result<MethodsWatchlistAudit, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "methods watchlist review lock poisoned")?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    let path = workspace.join(WATCHLIST_PATH);
    if !path.exists() {
        return Ok(MethodsWatchlistAudit::missing());
    }
    let raw = read_artifact(&path)?;
    let digest = sha256(&raw);
    let project_id = crate::project::require_project_id(&workspace)?;
    let events = read_review_events(&review_root(&app)?, &workspace, &project_id)?;
    Ok(audit_value(
        &workspace,
        &raw,
        &effective_reviewed_changes(&events, &digest),
    ))
}

#[tauri::command(async)]
pub fn append_heor_methods_watchlist_review(
    app: AppHandle,
    state: tauri::State<MethodsWatchlistReviewState>,
    request: MethodsWatchlistReviewRequest,
) -> Result<MethodsWatchlistReviewEvent, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "methods watchlist review lock poisoned")?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    if crate::project::require_project_id(&workspace)? != request.project_id {
        return Err("review projectId does not match the current project".into());
    }
    if !is_sha256(&request.watchlist_sha256)
        || !is_safe_id(&request.change_id)
        || !valid_review_text(&request.actor_label, 120)
        || !valid_review_text(&request.rationale, 2_000)
    {
        return Err("review target, actor, or rationale is invalid".into());
    }
    let raw = read_artifact(&workspace.join(WATCHLIST_PATH))?;
    if sha256(&raw) != request.watchlist_sha256 {
        return Err("review must target the exact current methods watchlist".into());
    }
    let watchlist: Watchlist = serde_json::from_slice(&raw)
        .map_err(|error| format!("methods watchlist is invalid: {error}"))?;
    let audit = audit_value(&workspace, &raw, &HashSet::new());
    if !audit.reviewable {
        return Err("methods watchlist is not structurally reviewable".into());
    }
    let change = watchlist
        .changes
        .get(&request.change_id)
        .ok_or("review changeId does not exist in the current watchlist")?;
    if request.action == MethodsWatchlistReviewAction::AcceptRevalidation
        && (change.change_status != "confirmed"
            || change.revalidation_status != "ready_for_human_review")
    {
        return Err(
            "accept_revalidation requires a confirmed change ready for Human review".into(),
        );
    }
    let root = review_root(&app)?;
    let events = read_review_events(&root, &workspace, &request.project_id)?;
    if events.last().is_some_and(|event| {
        event.watchlist_sha256 == request.watchlist_sha256
            && event.change_id == request.change_id
            && event.action == request.action
    }) {
        return Err("the latest review already records this action for the exact change".into());
    }
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| error.to_string())?
        .as_secs();
    let review_id = crate::runtime::random_hex(16);
    let record_path = format!(
        "heor/methods-watchlist-reviews/{}-{review_id}.json",
        request.change_id
    );
    let mut event = MethodsWatchlistReviewEvent {
        schema_version: REVIEW_EVENT_SCHEMA,
        sequence: events.len() as u64 + 1,
        review_id,
        project_id: request.project_id,
        watchlist_id: watchlist.watchlist_id,
        watchlist_sha256: request.watchlist_sha256,
        change_id: request.change_id,
        action: request.action,
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
    event.event_hash = review_event_hash(&event)?;
    write_review_record(&workspace, &event)?;
    if let Err(error) = append_review_event(&root, &event) {
        let _ = std::fs::remove_file(workspace.join(&event.record_path));
        return Err(error);
    }
    crate::git_snapshot::commit_best_effort(&workspace, "Record methods watchlist Human review");
    Ok(event)
}

#[tauri::command(async)]
pub fn list_heor_methods_watchlist_reviews(
    app: AppHandle,
    state: tauri::State<MethodsWatchlistReviewState>,
    project_id: String,
) -> Result<MethodsWatchlistReviewLog, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "methods watchlist review lock poisoned")?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    if crate::project::require_project_id(&workspace)? != project_id {
        return Err("review projectId does not match the current project".into());
    }
    let events = read_review_events(&review_root(&app)?, &workspace, &project_id)?;
    Ok(MethodsWatchlistReviewLog {
        chain_head: events.last().map(|event| event.event_hash.clone()),
        events,
        integrity: "verified_unanchored_sha256_chain",
        identity_assurance: REVIEW_ASSURANCE,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn workspace(tag: &str) -> std::path::PathBuf {
        let path =
            std::env::temp_dir().join(format!("ai4heor-methods-{tag}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&path);
        std::fs::create_dir_all(&path).unwrap();
        path
    }

    fn fixture() -> serde_json::Value {
        serde_json::json!({
            "schema_version": "0.2.0", "watchlist_id": "methods-2026-07",
            "status": "ready_for_human_review", "as_of_date": "2026-07-17",
            "source_order": ["nice"], "sources": {"nice": {
                "source_id": "nice", "title": "Methods manual", "organization": "NICE",
                "jurisdiction": "England", "source_type": "method_guideline",
                "publication_status": "current", "canonical_url": "https://www.nice.org.uk/process/pmg36",
                "access_mode": "link_only", "rights_status": "link_only",
                "rights_note": "Link only.", "revision": {"label": "PMG36", "published_on": null,
                    "last_checked_on": "2026-07-17", "next_check_due": "2026-10-17"},
                "snapshot": null, "affected_contracts": ["heor-reference-case"],
                "monitoring_notes": "A Human checks the official source."
            }}, "change_order": [], "changes": {},
            "limitations": ["A dated currency check is not approval."]
        })
    }

    #[test]
    fn audits_link_only_snapshot_as_complete() {
        let directory = workspace("complete");
        let raw = serde_json::to_vec(&fixture()).unwrap();
        let audit = audit_value(&directory, &raw, &HashSet::new());
        assert!(audit.complete, "{:?}", audit.errors);
        assert_eq!(audit.current_count, 1);
        std::fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn detects_overdue_and_unresolved_changes() {
        let directory = workspace("overdue");
        let mut value = fixture();
        value
            .pointer_mut("/sources/nice/revision/next_check_due")
            .unwrap()
            .clone_from(&serde_json::json!("2026-07-16"));
        value["change_order"] = serde_json::json!(["update"]);
        value["changes"] = serde_json::json!({"update": {
            "change_id": "update", "source_id": "nice", "detected_on": "2026-07-17",
            "change_status": "confirmed", "previous_revision": "old", "current_revision": "new",
            "changed_sections": ["discounting"], "summary": "Changed.",
            "affected_contracts": ["heor-reference-case"], "required_actions": ["Review."],
            "revalidation_status": "ready_for_human_review", "evidence_paths": []
        }});
        let raw = serde_json::to_vec(&value).unwrap();
        let audit = audit_value(&directory, &raw, &HashSet::new());
        assert!(!audit.complete);
        assert_eq!(audit.overdue_sources, ["nice"]);
        assert_eq!(audit.unresolved_changes, ["update"]);
        assert_eq!(audit.acceptance_eligible_changes, ["update"]);
        let reviewed = HashSet::from(["update".to_string()]);
        let reviewed_audit = audit_value(&directory, &raw, &reviewed);
        assert_eq!(reviewed_audit.reviewed_change_count, 1);
        assert!(reviewed_audit.unresolved_changes.is_empty());
        assert!(reviewed_audit.acceptance_eligible_changes.is_empty());
        assert!(
            !reviewed_audit.complete,
            "the source check is still overdue"
        );
        std::fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn rejects_unknown_fields_and_unsafe_snapshot() {
        let directory = workspace("invalid");
        let mut value = fixture();
        value["approval"] = serde_json::json!(true);
        let audit = audit_value(
            &directory,
            &serde_json::to_vec(&value).unwrap(),
            &HashSet::new(),
        );
        assert!(!audit.errors.is_empty());

        value.as_object_mut().unwrap().remove("approval");
        value["change_order"] = serde_json::json!(["update"]);
        value["changes"] = serde_json::json!({"update": {
            "change_id": "update", "source_id": "nice", "detected_on": "2026-07-17",
            "change_status": "confirmed", "previous_revision": "old", "current_revision": "new",
            "changed_sections": ["discounting"], "summary": "Changed.",
            "affected_contracts": ["heor-reference-case"], "required_actions": ["Review."],
            "revalidation_status": "ready_for_human_review", "evidence_paths": [],
            "human_disposition": "accepted"
        }});
        let forged = audit_value(
            &directory,
            &serde_json::to_vec(&value).unwrap(),
            &HashSet::new(),
        );
        assert!(forged
            .errors
            .iter()
            .any(|error| error.contains("unknown field")));
        std::fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn review_event_hash_binds_action_and_watchlist_bytes() {
        let mut event = MethodsWatchlistReviewEvent {
            schema_version: REVIEW_EVENT_SCHEMA,
            sequence: 1,
            review_id: "a".repeat(32),
            project_id: "project-1".into(),
            watchlist_id: "methods-2026-07".into(),
            watchlist_sha256: "b".repeat(64),
            change_id: "update".into(),
            action: MethodsWatchlistReviewAction::DismissChange,
            actor_label: "Researcher".into(),
            rationale: "The observed edit does not affect this study.".into(),
            timestamp: 1,
            record_path: "heor/methods-watchlist-reviews/update-a.json".into(),
            record_sha256: "c".repeat(64),
            assurance: REVIEW_ASSURANCE.into(),
            previous_hash: None,
            event_hash: String::new(),
        };
        let initial = review_event_hash(&event).unwrap();
        event.action = MethodsWatchlistReviewAction::AcceptRevalidation;
        assert_ne!(initial, review_event_hash(&event).unwrap());
        event.action = MethodsWatchlistReviewAction::DismissChange;
        event.watchlist_sha256 = "d".repeat(64);
        assert_ne!(initial, review_event_hash(&event).unwrap());
    }

    #[test]
    fn private_chain_rejects_a_tampered_exported_record() {
        let directory = workspace("tampered-record");
        let root = directory.join("private");
        std::fs::create_dir_all(&root).unwrap();
        let mut event = MethodsWatchlistReviewEvent {
            schema_version: REVIEW_EVENT_SCHEMA,
            sequence: 1,
            review_id: "a".repeat(32),
            project_id: "project-1".into(),
            watchlist_id: "methods-2026-07".into(),
            watchlist_sha256: "b".repeat(64),
            change_id: "update".into(),
            action: MethodsWatchlistReviewAction::DismissChange,
            actor_label: "Researcher".into(),
            rationale: "The observed edit does not affect this study.".into(),
            timestamp: 1,
            record_path: "heor/methods-watchlist-reviews/update-a.json".into(),
            record_sha256: String::new(),
            assurance: REVIEW_ASSURANCE.into(),
            previous_hash: None,
            event_hash: String::new(),
        };
        event.record_sha256 = sha256(&review_snapshot(&event).unwrap());
        event.event_hash = review_event_hash(&event).unwrap();
        write_review_record(&directory, &event).unwrap();
        append_review_event(&root, &event).unwrap();
        assert_eq!(
            read_review_events(&root, &directory, "project-1")
                .unwrap()
                .len(),
            1
        );
        std::fs::write(directory.join(&event.record_path), b"{}\n").unwrap();
        assert!(read_review_events(&root, &directory, "project-1").is_err());
        std::fs::remove_dir_all(directory).unwrap();
    }
}
