//! Independent native audit for the dated HEOR methods watchlist.

use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::path::{Component, Path};
use tauri::AppHandle;

const WATCHLIST_PATH: &str = "heor/methods-watchlist.json";
const ARTIFACT_CAP_BYTES: u64 = 5 * 1024 * 1024;

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct MethodsWatchlistAudit {
    pub exists: bool,
    pub complete: bool,
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
    pub unresolved_change_count: usize,
    pub affected_contract_count: usize,
    pub overdue_sources: Vec<String>,
    pub unresolved_changes: Vec<String>,
    pub errors: Vec<String>,
}

impl MethodsWatchlistAudit {
    fn missing() -> Self {
        Self {
            exists: false,
            complete: false,
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
            unresolved_change_count: 0,
            affected_contract_count: 0,
            overdue_sources: Vec::new(),
            unresolved_changes: Vec::new(),
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
    human_disposition: String,
    evidence_paths: Vec<String>,
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

fn audit_value(workspace: &Path, raw: &[u8]) -> MethodsWatchlistAudit {
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
    if watchlist.schema_version != "0.1.0" {
        audit.errors.push("schema_version must be 0.1.0".into());
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
            ("local_snapshot", rights, Some(snapshot))
                if matches!(
                    rights,
                    "permission_confirmed" | "open_licence" | "personal_research"
                ) =>
            {
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
        if !matches!(
            change.change_status.as_str(),
            "suspected" | "confirmed" | "dismissed"
        ) || !matches!(
            change.revalidation_status.as_str(),
            "not_started" | "in_progress" | "complete" | "not_required"
        ) || !matches!(
            change.human_disposition.as_str(),
            "pending" | "accepted" | "rejected"
        ) {
            audit
                .errors
                .push(format!("change {change_id} has an invalid state"));
        }
        if change.change_status == "dismissed"
            && (change.human_disposition != "rejected"
                || change.revalidation_status != "not_required")
        {
            audit.errors.push(format!(
                "dismissed change {change_id} requires rejected/not_required"
            ));
        }
        if matches!(change.change_status.as_str(), "suspected" | "confirmed")
            && (change.human_disposition == "pending"
                || !matches!(
                    change.revalidation_status.as_str(),
                    "complete" | "not_required"
                ))
        {
            audit.unresolved_changes.push(change_id.clone());
        }
    }
    audit.overdue_count = audit.overdue_sources.len();
    audit.unresolved_change_count = audit.unresolved_changes.len();
    audit.affected_contract_count = affected.len();
    audit.complete = audit.errors.is_empty()
        && audit.status == "ready_for_human_review"
        && audit.source_count > 0
        && audit.overdue_sources.is_empty()
        && audit.unresolved_changes.is_empty();
    audit
}

pub fn audit_workspace(workspace: &Path) -> MethodsWatchlistAudit {
    let path = workspace.join(WATCHLIST_PATH);
    if !path.exists() {
        return MethodsWatchlistAudit::missing();
    }
    match read_artifact(&path) {
        Ok(raw) => audit_value(workspace, &raw),
        Err(error) => {
            let mut audit = MethodsWatchlistAudit::missing();
            audit.exists = true;
            audit.status = "invalid".into();
            audit.errors.push(error);
            audit
        }
    }
}

#[tauri::command(async)]
pub fn audit_heor_methods_watchlist(app: AppHandle) -> Result<MethodsWatchlistAudit, String> {
    Ok(audit_workspace(&crate::runtime::workspace_dir(&app)?))
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
            "schema_version": "0.1.0", "watchlist_id": "methods-2026-07",
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
        let audit = audit_value(&directory, &raw);
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
            "revalidation_status": "not_started", "human_disposition": "pending", "evidence_paths": []
        }});
        let audit = audit_value(&directory, &serde_json::to_vec(&value).unwrap());
        assert!(!audit.complete);
        assert_eq!(audit.overdue_sources, ["nice"]);
        assert_eq!(audit.unresolved_changes, ["update"]);
        std::fs::remove_dir_all(directory).unwrap();
    }

    #[test]
    fn rejects_unknown_fields_and_unsafe_snapshot() {
        let directory = workspace("invalid");
        let mut value = fixture();
        value["approval"] = serde_json::json!(true);
        let audit = audit_value(&directory, &serde_json::to_vec(&value).unwrap());
        assert!(!audit.errors.is_empty());
        std::fs::remove_dir_all(directory).unwrap();
    }
}
