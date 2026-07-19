//! App-owned Human review for project-local AI4HEOR Skill candidates.
//!
//! Candidate authoring remains a natural-language Agent workflow. This module
//! is the independent native control plane: it revalidates the exact candidate
//! bytes, records an append-only Human assertion, and materializes only the
//! reviewed instruction-only Skill into the current project's
//! `.opencode/skills/` directory. It never touches bundled/core Skills.

use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet, HashMap};
use std::io::Write;
use std::path::{Component, Path, PathBuf};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::AppHandle;

const CANDIDATE_SCHEMA: &str = "ai4heor-skill-candidate/v1";
const VALIDATION_SCHEMA: &str = "ai4heor-skill-validation/v1";
const EVENT_SCHEMA: u32 = 1;
const REVIEW_ASSURANCE: &str = "app_owned_local_human_assertion";
const MAX_CANDIDATES: usize = 100;
const MAX_FILES: usize = 64;
const MAX_FILE_BYTES: u64 = 128 * 1024;
const MAX_TOTAL_BYTES: u64 = 1024 * 1024;
const MAX_LOG_BYTES: u64 = 4 * 1024 * 1024;
const MAX_EVENTS: usize = 2_000;

#[derive(Default)]
pub struct CapabilityReviewState(pub Mutex<()>);

#[derive(Clone, Copy, Debug, Eq, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "snake_case")]
pub enum SkillCandidateReviewAction {
    Activate,
    Reject,
    Revoke,
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct SkillCandidateReviewRequest {
    pub project_id: String,
    pub candidate_id: String,
    pub decision_sha256: String,
    pub acceptance_checks_sha256: String,
    pub action: SkillCandidateReviewAction,
    pub actor_label: String,
    pub rationale: String,
}

#[derive(Clone, Debug, PartialEq, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct SkillCandidateReviewEvent {
    pub schema_version: u32,
    pub sequence: u64,
    pub review_id: String,
    pub project_id: String,
    pub candidate_id: String,
    pub decision_sha256: String,
    pub acceptance_checks_sha256: String,
    pub active_tree_sha256: String,
    pub action: SkillCandidateReviewAction,
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
pub struct LocalizedCandidateCopy {
    pub display_name: String,
    pub description: String,
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SkillCandidateSummary {
    pub candidate_id: String,
    pub created_at: String,
    pub request: String,
    pub localized: BTreeMap<String, LocalizedCandidateCopy>,
    pub provider: String,
    pub model: String,
    pub license_spdx: String,
    pub license_note: String,
    pub limitations: Vec<String>,
    pub acceptance_checks: Vec<String>,
    pub acceptance_checks_sha256: String,
    pub decision_sha256: String,
    pub active_tree_sha256: String,
    pub valid: bool,
    pub validation_errors: Vec<String>,
    pub status: String,
    pub can_activate: bool,
    pub can_reject: bool,
    pub can_revoke: bool,
    pub last_action: Option<SkillCandidateReviewAction>,
    pub last_actor_label: Option<String>,
    pub last_rationale: Option<String>,
    pub last_timestamp: Option<u64>,
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SkillCandidateAudit {
    pub project_available: bool,
    pub project_id: Option<String>,
    pub complete: bool,
    pub candidates: Vec<SkillCandidateSummary>,
    pub chain_head: Option<String>,
    pub integrity: String,
    pub identity_assurance: String,
    pub errors: Vec<String>,
}

#[derive(Clone, Debug)]
struct ValidatedCandidate {
    id: String,
    created_at: String,
    request: String,
    localized: BTreeMap<String, LocalizedCandidateCopy>,
    provider: String,
    model: String,
    license_spdx: String,
    license_note: String,
    limitations: Vec<String>,
    acceptance_checks: Vec<String>,
    acceptance_checks_sha256: String,
    decision_sha256: String,
    active_tree_sha256: String,
    files: Vec<String>,
}

#[derive(Clone, Debug)]
struct CandidateInspection {
    id: String,
    candidate: Option<ValidatedCandidate>,
    errors: Vec<String>,
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

fn valid_review_text(value: &str, limit: usize) -> bool {
    !value.trim().is_empty()
        && value.len() <= limit
        && !value.chars().any(|character| {
            character == '\0' || character.is_control() && character != '\n' && character != '\t'
        })
}

fn bounded_text(value: Option<&Value>, limit: usize) -> Option<String> {
    value
        .and_then(Value::as_str)
        .filter(|text| !text.trim().is_empty() && text.len() <= limit)
        .map(str::to_string)
}

fn exact_keys(value: &Value, expected: &[&str]) -> bool {
    let Some(object) = value.as_object() else {
        return false;
    };
    object.keys().map(String::as_str).collect::<BTreeSet<_>>()
        == expected.iter().copied().collect::<BTreeSet<_>>()
}

fn safe_relative_skill_file(value: &str) -> bool {
    value == "skill/SKILL.md"
        || (value.starts_with("skill/references/")
            && value.ends_with(".md")
            && Path::new(value)
                .components()
                .all(|component| matches!(component, Component::Normal(_))))
}

fn contains_possible_secret(raw: &[u8]) -> bool {
    let text = String::from_utf8_lossy(raw);
    let lower = text.to_ascii_lowercase();
    if text.contains("-----BEGIN PRIVATE KEY-----")
        || text.contains("-----BEGIN RSA PRIVATE KEY-----")
        || text.contains("-----BEGIN EC PRIVATE KEY-----")
        || text.contains("-----BEGIN OPENSSH PRIVATE KEY-----")
    {
        return true;
    }
    if text
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
            let tail = &lower[index + marker.len()..];
            let tail = tail.trim_start();
            let Some(tail) = tail.strip_prefix(':').or_else(|| tail.strip_prefix('=')) else {
                return false;
            };
            let value = tail
                .trim_start()
                .trim_start_matches(['\'', '"'])
                .split(|character: char| {
                    character.is_whitespace() || matches!(character, '\'' | '"' | ',')
                })
                .next()
                .unwrap_or_default();
            value.len() >= 12
        })
    })
}

fn list_candidate_files(root: &Path) -> Result<BTreeMap<String, Vec<u8>>, String> {
    fn visit(
        root: &Path,
        current: &Path,
        output: &mut BTreeMap<String, Vec<u8>>,
        total: &mut u64,
    ) -> Result<(), String> {
        for entry in std::fs::read_dir(current)
            .map_err(|error| format!("candidate directory cannot be read: {error}"))?
        {
            let entry =
                entry.map_err(|error| format!("candidate entry cannot be read: {error}"))?;
            let path = entry.path();
            let metadata = std::fs::symlink_metadata(&path)
                .map_err(|error| format!("candidate entry cannot be inspected: {error}"))?;
            let relative = path
                .strip_prefix(root)
                .map_err(|_| "candidate entry escaped its root")?
                .to_string_lossy()
                .replace('\\', "/");
            if metadata.file_type().is_symlink() {
                return Err(format!("candidate contains a symlink: {relative}"));
            }
            if relative.split('/').any(|part| part.starts_with('.')) {
                return Err(format!("candidate contains hidden content: {relative}"));
            }
            if metadata.is_dir() {
                visit(root, &path, output, total)?;
            } else if metadata.is_file() {
                if output.len() >= MAX_FILES {
                    return Err(format!("candidate exceeds {MAX_FILES} files"));
                }
                if metadata.len() > MAX_FILE_BYTES {
                    return Err(format!(
                        "candidate file exceeds {MAX_FILE_BYTES} bytes: {relative}"
                    ));
                }
                let allowed = relative == "candidate.json"
                    || relative == "validation.json"
                    || safe_relative_skill_file(&relative);
                if !allowed {
                    return Err(format!("candidate contains an unexpected file: {relative}"));
                }
                let raw = std::fs::read(&path)
                    .map_err(|error| format!("candidate file cannot be read: {error}"))?;
                if contains_possible_secret(&raw) {
                    return Err(format!("candidate may contain a secret: {relative}"));
                }
                *total += raw.len() as u64;
                if *total > MAX_TOTAL_BYTES {
                    return Err(format!("candidate exceeds {MAX_TOTAL_BYTES} bytes"));
                }
                output.insert(relative, raw);
            } else {
                return Err(format!(
                    "candidate contains an unsupported entry: {relative}"
                ));
            }
        }
        Ok(())
    }

    let metadata = std::fs::symlink_metadata(root)
        .map_err(|error| format!("candidate path cannot be inspected: {error}"))?;
    if !metadata.is_dir() || metadata.file_type().is_symlink() {
        return Err("candidate path must be a real directory".into());
    }
    let mut output = BTreeMap::new();
    let mut total = 0;
    visit(root, root, &mut output, &mut total)?;
    Ok(output)
}

fn string_array(value: Option<&Value>, limit: usize) -> Option<Vec<String>> {
    let values = value?.as_array()?;
    if values.is_empty() || values.len() > 64 {
        return None;
    }
    let mut output = Vec::with_capacity(values.len());
    for value in values {
        output.push(bounded_text(Some(value), limit)?);
    }
    Some(output)
}

fn inspect_candidate(root: &Path) -> CandidateInspection {
    let fallback_id = root
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or_default()
        .to_string();
    match validate_candidate(root) {
        Ok(candidate) => CandidateInspection {
            id: candidate.id.clone(),
            candidate: Some(candidate),
            errors: Vec::new(),
        },
        Err(error) => CandidateInspection {
            id: fallback_id,
            candidate: None,
            errors: vec![error],
        },
    }
}

fn validate_candidate(root: &Path) -> Result<ValidatedCandidate, String> {
    let files = list_candidate_files(root)?;
    let manifest_raw = files
        .get("candidate.json")
        .ok_or("candidate.json is required")?;
    let validation_raw = files
        .get("validation.json")
        .ok_or("validation.json is required")?;
    let manifest: Value = serde_json::from_slice(manifest_raw)
        .map_err(|error| format!("candidate.json is invalid: {error}"))?;
    if !exact_keys(
        &manifest,
        &[
            "schema",
            "id",
            "status",
            "created_at",
            "request",
            "localized",
            "authoring",
            "source",
            "permissions",
            "files",
            "limitations",
            "acceptance_checks",
        ],
    ) {
        return Err("candidate.json fields do not match the v1 contract".into());
    }
    if manifest.get("schema").and_then(Value::as_str) != Some(CANDIDATE_SCHEMA)
        || manifest.get("status").and_then(Value::as_str) != Some("candidate")
    {
        return Err("candidate schema or status is invalid".into());
    }
    let id = bounded_text(manifest.get("id"), 64).ok_or("candidate id is missing")?;
    if !safe_id(&id) || root.file_name().and_then(|name| name.to_str()) != Some(&id) {
        return Err("candidate id must match its lowercase hyphenated directory".into());
    }
    let created_at = bounded_text(manifest.get("created_at"), 64)
        .filter(|value| value.ends_with('Z'))
        .ok_or("candidate created_at must be a bounded UTC timestamp")?;
    let request = bounded_text(manifest.get("request"), 4_000)
        .ok_or("candidate request is missing or too long")?;

    let localized_value = manifest
        .get("localized")
        .and_then(Value::as_object)
        .ok_or("candidate localized metadata is missing")?;
    if !localized_value.contains_key("en") || !localized_value.contains_key("zh-Hans") {
        return Err("candidate localized metadata must include en and zh-Hans".into());
    }
    let mut localized = BTreeMap::new();
    for (locale, value) in localized_value {
        if locale.is_empty()
            || locale.len() > 32
            || !exact_keys(value, &["display_name", "description"])
        {
            return Err("candidate localized metadata is invalid".into());
        }
        let display_name = bounded_text(value.get("display_name"), 120)
            .ok_or("candidate localized display name is invalid")?;
        let description = bounded_text(value.get("description"), 600)
            .ok_or("candidate localized description is invalid")?;
        localized.insert(
            locale.clone(),
            LocalizedCandidateCopy {
                display_name,
                description,
            },
        );
    }

    let authoring = manifest
        .get("authoring")
        .ok_or("candidate authoring metadata is missing")?;
    if !exact_keys(authoring, &["provider", "model", "session_ref"]) {
        return Err("candidate authoring metadata is invalid".into());
    }
    let provider =
        bounded_text(authoring.get("provider"), 300).ok_or("candidate provider is missing")?;
    let model = bounded_text(authoring.get("model"), 300).ok_or("candidate model is missing")?;
    bounded_text(authoring.get("session_ref"), 300)
        .ok_or("candidate session reference is missing")?;

    let source = manifest
        .get("source")
        .ok_or("candidate source metadata is missing")?;
    if !exact_keys(
        source,
        &[
            "kind",
            "copyright_holder",
            "rights_basis",
            "license_spdx",
            "license_note",
        ],
    ) {
        return Err("candidate source metadata is invalid".into());
    }
    for field in ["kind", "copyright_holder", "rights_basis"] {
        bounded_text(source.get(field), 1_000)
            .ok_or_else(|| format!("candidate source {field} is missing"))?;
    }
    let license_spdx = bounded_text(source.get("license_spdx"), 1_000)
        .ok_or("candidate license identifier is missing")?;
    let license_note = bounded_text(source.get("license_note"), 1_000)
        .ok_or("candidate license note is missing")?;

    let permissions = manifest
        .get("permissions")
        .ok_or("candidate permissions are missing")?;
    if !exact_keys(
        permissions,
        &["network", "secrets", "commands", "outside_workspace"],
    ) || ["network", "secrets", "commands", "outside_workspace"]
        .iter()
        .any(|field| permissions.get(*field).and_then(Value::as_bool) != Some(false))
    {
        return Err("instruction-only candidate permissions must all be false".into());
    }

    let listed = manifest
        .get("files")
        .and_then(Value::as_array)
        .filter(|items| !items.is_empty() && items.len() <= MAX_FILES)
        .ok_or("candidate files list is missing or too large")?;
    let mut listed_paths = BTreeSet::new();
    for item in listed {
        if !exact_keys(item, &["path", "bytes", "sha256"]) {
            return Err("candidate file record is invalid".into());
        }
        let path = bounded_text(item.get("path"), 300).ok_or("candidate file path is invalid")?;
        if !safe_relative_skill_file(&path) || !listed_paths.insert(path.clone()) {
            return Err(format!(
                "candidate file path is unsafe or duplicated: {path}"
            ));
        }
        let raw = files
            .get(&path)
            .ok_or_else(|| format!("candidate listed file is missing: {path}"))?;
        if item.get("bytes").and_then(Value::as_u64) != Some(raw.len() as u64)
            || item.get("sha256").and_then(Value::as_str) != Some(&sha256(raw))
        {
            return Err(format!(
                "candidate listed file hash or size changed: {path}"
            ));
        }
    }
    let actual_paths = files
        .keys()
        .filter(|path| path.starts_with("skill/"))
        .cloned()
        .collect::<BTreeSet<_>>();
    if listed_paths != actual_paths {
        return Err("candidate files list does not exactly cover the Skill content".into());
    }

    let limitations = string_array(manifest.get("limitations"), 1_000)
        .ok_or("candidate limitations are missing or invalid")?;
    let acceptance_checks = string_array(manifest.get("acceptance_checks"), 1_000)
        .ok_or("candidate acceptance checks are missing or invalid")?;
    let acceptance_checks_raw =
        serde_json::to_vec(&acceptance_checks).map_err(|error| error.to_string())?;
    let acceptance_checks_sha256 = sha256(&acceptance_checks_raw);

    let skill_raw = files
        .get("skill/SKILL.md")
        .ok_or("skill/SKILL.md is required")?;
    let skill_text = std::str::from_utf8(skill_raw).map_err(|_| "skill/SKILL.md must be UTF-8")?;
    let mut lines = skill_text.lines();
    if lines.next() != Some("---")
        || lines.next() != Some(&format!("name: {id}"))
        || !lines
            .next()
            .is_some_and(|line| line.starts_with("description: ") && line.len() <= 613)
        || lines.next() != Some("---")
    {
        return Err("skill/SKILL.md frontmatter is invalid".into());
    }

    let mut decision = Sha256::new();
    decision.update(manifest_raw);
    for path in &listed_paths {
        decision.update([0]);
        decision.update(files.get(path).expect("listed path was checked"));
    }
    let decision_sha256 = format!("{:x}", decision.finalize());
    let validation: Value = serde_json::from_slice(validation_raw)
        .map_err(|error| format!("validation.json is invalid: {error}"))?;
    if !exact_keys(
        &validation,
        &[
            "schema",
            "candidate_id",
            "validated_at",
            "valid",
            "instruction_only",
            "decision_sha256",
            "checked_files",
            "errors",
        ],
    ) || validation.get("schema").and_then(Value::as_str) != Some(VALIDATION_SCHEMA)
        || validation.get("candidate_id").and_then(Value::as_str) != Some(&id)
        || validation.get("valid").and_then(Value::as_bool) != Some(true)
        || validation.get("instruction_only").and_then(Value::as_bool) != Some(true)
        || validation.get("decision_sha256").and_then(Value::as_str) != Some(&decision_sha256)
        || !validation
            .get("errors")
            .and_then(Value::as_array)
            .is_some_and(Vec::is_empty)
    {
        return Err("validation.json does not approve the exact current candidate bytes".into());
    }
    let checked = validation
        .get("checked_files")
        .and_then(Value::as_array)
        .ok_or("validation checked_files is invalid")?
        .iter()
        .filter_map(Value::as_str)
        .map(str::to_string)
        .collect::<BTreeSet<_>>();
    if checked != listed_paths {
        return Err("validation checked_files does not match candidate files".into());
    }
    let active_tree_sha256 = crate::asset_admission::tree_sha256(&root.join("skill"))?;

    Ok(ValidatedCandidate {
        id,
        created_at,
        request,
        localized,
        provider,
        model,
        license_spdx,
        license_note,
        limitations,
        acceptance_checks,
        acceptance_checks_sha256,
        decision_sha256,
        active_tree_sha256,
        files: listed_paths.into_iter().collect(),
    })
}

fn review_root(app: &AppHandle) -> Result<PathBuf, String> {
    use tauri::Manager;
    Ok(app
        .path()
        .app_data_dir()
        .map_err(|error| error.to_string())?
        .join("capability-reviews"))
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
        && value.starts_with("capabilities/reviews/")
        && value.ends_with(".json")
        && path
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
}

fn review_snapshot(event: &SkillCandidateReviewEvent) -> Result<Vec<u8>, String> {
    let status = match event.action {
        SkillCandidateReviewAction::Activate => "activated",
        SkillCandidateReviewAction::Reject => "rejected",
        SkillCandidateReviewAction::Revoke => "revoked",
    };
    let value = serde_json::json!({
        "schema": "ai4heor-skill-candidate-review/v1",
        "review_id": event.review_id,
        "project_id": event.project_id,
        "candidate_id": event.candidate_id,
        "decision_sha256": event.decision_sha256,
        "acceptance_checks_sha256": event.acceptance_checks_sha256,
        "active_tree_sha256": event.active_tree_sha256,
        "action": event.action,
        "status": status,
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

fn event_hash(event: &SkillCandidateReviewEvent) -> Result<String, String> {
    let mut payload = event.clone();
    payload.event_hash.clear();
    serde_json::to_vec(&payload)
        .map(|raw| sha256(&raw))
        .map_err(|error| error.to_string())
}

fn read_review_record(workspace: &Path, event: &SkillCandidateReviewEvent) -> Result<(), String> {
    if !review_record_path_valid(&event.record_path) {
        return Err("capability review record path is unsafe".into());
    }
    let path = workspace.join(&event.record_path);
    let metadata = std::fs::symlink_metadata(&path)
        .map_err(|error| format!("capability review record is unavailable: {error}"))?;
    if !metadata.is_file() || metadata.file_type().is_symlink() || metadata.len() > MAX_FILE_BYTES {
        return Err("capability review record must be a bounded regular file".into());
    }
    let raw = std::fs::read(&path)
        .map_err(|error| format!("capability review record is unavailable: {error}"))?;
    if sha256(&raw) != event.record_sha256 || raw != review_snapshot(event)? {
        return Err("capability review record does not match the app-private event".into());
    }
    Ok(())
}

fn read_events(
    root: &Path,
    workspace: &Path,
    project_id: &str,
) -> Result<Vec<SkillCandidateReviewEvent>, String> {
    let path = review_log_path(root, project_id)?;
    let metadata = match std::fs::symlink_metadata(&path) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(format!("capability review log is unavailable: {error}")),
    };
    if !metadata.is_file() || metadata.file_type().is_symlink() || metadata.len() > MAX_LOG_BYTES {
        return Err("capability review log must be a bounded regular file".into());
    }
    let raw = std::fs::read(&path)
        .map_err(|error| format!("capability review log is unavailable: {error}"))?;
    let mut events = Vec::new();
    let mut previous_hash = None;
    for (index, line) in raw
        .split(|byte| *byte == b'\n')
        .filter(|line| !line.is_empty())
        .enumerate()
    {
        if index >= MAX_EVENTS {
            return Err(format!("capability review log exceeds {MAX_EVENTS} events"));
        }
        let event: SkillCandidateReviewEvent = serde_json::from_slice(line)
            .map_err(|error| format!("capability review line {} is invalid: {error}", index + 1))?;
        if event.schema_version != EVENT_SCHEMA
            || event.sequence != index as u64 + 1
            || event.project_id != project_id
            || !safe_id(&event.candidate_id)
            || !is_sha256(&event.decision_sha256)
            || !is_sha256(&event.acceptance_checks_sha256)
            || !is_sha256(&event.active_tree_sha256)
            || event.review_id.len() != 32
            || !event.review_id.bytes().all(|byte| byte.is_ascii_hexdigit())
            || !is_sha256(&event.record_sha256)
            || !is_sha256(&event.event_hash)
            || event.assurance != REVIEW_ASSURANCE
            || event.previous_hash != previous_hash
            || !valid_review_text(&event.actor_label, 120)
            || !valid_review_text(&event.rationale, 2_000)
            || event_hash(&event)? != event.event_hash
        {
            return Err(format!(
                "capability review line {} violates the event contract",
                index + 1
            ));
        }
        read_review_record(workspace, &event)?;
        previous_hash = Some(event.event_hash.clone());
        events.push(event);
    }
    Ok(events)
}

fn write_review_record(workspace: &Path, event: &SkillCandidateReviewEvent) -> Result<(), String> {
    if !review_record_path_valid(&event.record_path) {
        return Err("capability review record path is unsafe".into());
    }
    let target = workspace.join(&event.record_path);
    let parent = target
        .parent()
        .ok_or("capability review record parent is invalid")?;
    ensure_real_directory(workspace, Path::new("capabilities/reviews"))?;
    let raw = review_snapshot(event)?;
    if sha256(&raw) != event.record_sha256 {
        return Err("capability review record hash changed before write".into());
    }
    let mut file = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&target)
        .map_err(|error| format!("capability review record write failed: {error}"))?;
    file.write_all(&raw)
        .and_then(|_| file.sync_all())
        .map_err(|error| format!("capability review record write failed: {error}"))?;
    let _ = parent;
    Ok(())
}

fn append_event(root: &Path, event: &SkillCandidateReviewEvent) -> Result<(), String> {
    let path = review_log_path(root, &event.project_id)?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("capability review log directory failed: {error}"))?;
        crate::runtime::tighten_private(parent);
    }
    if std::fs::symlink_metadata(&path)
        .is_ok_and(|metadata| metadata.file_type().is_symlink() || !metadata.is_file())
    {
        return Err("capability review log must be a regular file".into());
    }
    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)
        .map_err(|error| format!("capability review log open failed: {error}"))?;
    crate::runtime::tighten_private(&path);
    let line = serde_json::to_string(event).map_err(|error| error.to_string())?;
    writeln!(file, "{line}")
        .and_then(|_| file.sync_all())
        .map_err(|error| format!("capability review log append failed: {error}"))
}

fn ensure_real_directory(workspace: &Path, relative: &Path) -> Result<PathBuf, String> {
    let mut current = workspace.to_path_buf();
    for component in relative.components() {
        let Component::Normal(segment) = component else {
            return Err("capability directory path is unsafe".into());
        };
        current.push(segment);
        match std::fs::symlink_metadata(&current) {
            Ok(metadata) if metadata.is_dir() && !metadata.file_type().is_symlink() => {}
            Ok(_) => {
                return Err(format!(
                    "capability directory is not a real directory: {}",
                    current.display()
                ))
            }
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                std::fs::create_dir(&current)
                    .map_err(|error| format!("capability directory creation failed: {error}"))?;
            }
            Err(error) => return Err(format!("capability directory cannot be inspected: {error}")),
        }
    }
    Ok(current)
}

fn copy_candidate_skill(
    candidate_root: &Path,
    stage: &Path,
    candidate: &ValidatedCandidate,
) -> Result<(), String> {
    std::fs::create_dir(stage)
        .map_err(|error| format!("capability activation stage failed: {error}"))?;
    for listed in &candidate.files {
        let relative = listed
            .strip_prefix("skill/")
            .ok_or("candidate file is outside the Skill tree")?;
        let source = candidate_root.join(listed);
        let target = stage.join(relative);
        if let Some(parent) = target.parent() {
            std::fs::create_dir_all(parent)
                .map_err(|error| format!("capability activation stage failed: {error}"))?;
        }
        let raw = std::fs::read(&source)
            .map_err(|error| format!("candidate changed during activation: {error}"))?;
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&target)
            .map_err(|error| format!("capability activation stage failed: {error}"))?;
        file.write_all(&raw)
            .and_then(|_| file.sync_all())
            .map_err(|error| format!("capability activation stage failed: {error}"))?;
    }
    let copied_hash = crate::asset_admission::tree_sha256(stage)?;
    if copied_hash != candidate.active_tree_sha256 {
        return Err("activated Skill stage does not match the reviewed candidate bytes".into());
    }
    Ok(())
}

fn active_skill_path(workspace: &Path, candidate_id: &str) -> PathBuf {
    workspace
        .join(".opencode")
        .join("skills")
        .join(candidate_id)
}

fn active_tree_state(path: &Path, expected: &str) -> &'static str {
    match std::fs::symlink_metadata(path) {
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => "missing",
        Ok(metadata) if metadata.is_dir() && !metadata.file_type().is_symlink() => {
            match crate::asset_admission::tree_sha256(path) {
                Ok(actual) if actual == expected => "exact",
                _ => "drifted",
            }
        }
        _ => "drifted",
    }
}

fn latest_by_candidate(
    events: &[SkillCandidateReviewEvent],
) -> HashMap<String, &SkillCandidateReviewEvent> {
    let mut latest = HashMap::new();
    for event in events {
        latest.insert(event.candidate_id.clone(), event);
    }
    latest
}

fn inspect_candidates(workspace: &Path) -> Result<Vec<CandidateInspection>, String> {
    let root = workspace.join("capabilities/candidates");
    let metadata = match std::fs::symlink_metadata(&root) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(format!("candidate store cannot be inspected: {error}")),
    };
    if !metadata.is_dir() || metadata.file_type().is_symlink() {
        return Err("candidate store must be a real directory".into());
    }
    let mut directories = Vec::new();
    for entry in std::fs::read_dir(&root)
        .map_err(|error| format!("candidate store cannot be read: {error}"))?
    {
        let entry =
            entry.map_err(|error| format!("candidate store entry cannot be read: {error}"))?;
        let name = entry.file_name();
        let name = name.to_string_lossy();
        if name == ".gitkeep" {
            continue;
        }
        let metadata = std::fs::symlink_metadata(entry.path())
            .map_err(|error| format!("candidate store entry cannot be inspected: {error}"))?;
        if !metadata.is_dir() || metadata.file_type().is_symlink() {
            return Err(format!(
                "candidate store contains a non-directory entry: {name}"
            ));
        }
        directories.push(entry.path());
    }
    if directories.len() > MAX_CANDIDATES {
        return Err(format!(
            "candidate store exceeds {MAX_CANDIDATES} candidates"
        ));
    }
    directories.sort();
    Ok(directories
        .iter()
        .map(|path| inspect_candidate(path))
        .collect())
}

fn audit_workspace(
    workspace: &Path,
    root: &Path,
    project_id: &str,
) -> Result<SkillCandidateAudit, String> {
    let events = read_events(root, workspace, project_id)?;
    let latest = latest_by_candidate(&events);
    let inspections = inspect_candidates(workspace)?;
    let mut ids = inspections
        .iter()
        .map(|item| item.id.clone())
        .collect::<BTreeSet<_>>();
    ids.extend(latest.keys().cloned());
    let by_id = inspections
        .into_iter()
        .map(|item| (item.id.clone(), item))
        .collect::<HashMap<_, _>>();
    let mut candidates = Vec::new();
    for id in ids {
        let inspection = by_id.get(&id);
        let candidate = inspection.and_then(|item| item.candidate.as_ref());
        let last = latest.get(&id).copied();
        let active_path = active_skill_path(workspace, &id);
        let active_state = match last {
            Some(event) if event.action == SkillCandidateReviewAction::Activate => {
                active_tree_state(&active_path, &event.active_tree_sha256)
            }
            _ => match std::fs::symlink_metadata(&active_path) {
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => "missing",
                _ => "unmanaged",
            },
        };
        let current_matches_last = candidate.zip(last).is_some_and(|(candidate, event)| {
            candidate.decision_sha256 == event.decision_sha256
                && candidate.active_tree_sha256 == event.active_tree_sha256
        });
        let status = if candidate.is_none() && last.is_none() {
            "invalid"
        } else if last.is_some_and(|event| event.action == SkillCandidateReviewAction::Activate) {
            if active_state == "exact" {
                if current_matches_last {
                    "active"
                } else {
                    "active_candidate_changed"
                }
            } else {
                "drifted"
            }
        } else if active_state == "unmanaged" {
            "unmanaged_conflict"
        } else if let Some(review) = last.filter(|_| current_matches_last) {
            match review.action {
                SkillCandidateReviewAction::Reject => "rejected",
                SkillCandidateReviewAction::Revoke => "revoked",
                SkillCandidateReviewAction::Activate => unreachable!(),
            }
        } else if candidate.is_some() {
            "inactive"
        } else {
            "candidate_missing"
        };
        let valid = candidate.is_some();
        let can_revoke = last
            .is_some_and(|event| event.action == SkillCandidateReviewAction::Activate)
            && active_state == "exact";
        let can_activate = valid && active_state == "missing" && !can_revoke;
        let can_reject = valid && active_state == "missing" && !can_revoke && status != "rejected";
        let mut validation_errors = inspection
            .map(|item| item.errors.clone())
            .unwrap_or_default();
        if status == "drifted" {
            validation_errors
                .push("active Skill bytes no longer match the activation record".into());
        } else if status == "unmanaged_conflict" {
            validation_errors
                .push("an unreviewed project Skill already uses this candidate id".into());
        } else if status == "candidate_missing" {
            validation_errors.push("the reviewed candidate directory is missing".into());
        }
        candidates.push(SkillCandidateSummary {
            candidate_id: id,
            created_at: candidate
                .map(|item| item.created_at.clone())
                .unwrap_or_default(),
            request: candidate
                .map(|item| item.request.clone())
                .unwrap_or_default(),
            localized: candidate
                .map(|item| item.localized.clone())
                .unwrap_or_default(),
            provider: candidate
                .map(|item| item.provider.clone())
                .unwrap_or_default(),
            model: candidate.map(|item| item.model.clone()).unwrap_or_default(),
            license_spdx: candidate
                .map(|item| item.license_spdx.clone())
                .unwrap_or_default(),
            license_note: candidate
                .map(|item| item.license_note.clone())
                .unwrap_or_default(),
            limitations: candidate
                .map(|item| item.limitations.clone())
                .unwrap_or_default(),
            acceptance_checks: candidate
                .map(|item| item.acceptance_checks.clone())
                .unwrap_or_default(),
            acceptance_checks_sha256: if can_revoke {
                last.map(|event| event.acceptance_checks_sha256.clone())
            } else {
                candidate.map(|item| item.acceptance_checks_sha256.clone())
            }
            .unwrap_or_default(),
            decision_sha256: if can_revoke {
                last.map(|event| event.decision_sha256.clone())
            } else {
                candidate.map(|item| item.decision_sha256.clone())
            }
            .unwrap_or_default(),
            active_tree_sha256: if can_revoke {
                last.map(|event| event.active_tree_sha256.clone())
            } else {
                candidate.map(|item| item.active_tree_sha256.clone())
            }
            .unwrap_or_default(),
            valid,
            validation_errors,
            status: status.into(),
            can_activate,
            can_reject,
            can_revoke,
            last_action: last.map(|event| event.action),
            last_actor_label: last.map(|event| event.actor_label.clone()),
            last_rationale: last.map(|event| event.rationale.clone()),
            last_timestamp: last.map(|event| event.timestamp),
        });
    }
    Ok(SkillCandidateAudit {
        project_available: true,
        project_id: Some(project_id.into()),
        complete: true,
        candidates,
        chain_head: events.last().map(|event| event.event_hash.clone()),
        integrity: "verified_unanchored_sha256_chain".into(),
        identity_assurance: REVIEW_ASSURANCE.into(),
        errors: Vec::new(),
    })
}

fn remove_exact_tree(path: &Path) -> Result<(), String> {
    std::fs::remove_dir_all(path)
        .map_err(|error| format!("capability staging cleanup failed: {error}"))
}

fn apply_review(
    workspace: &Path,
    root: &Path,
    project_id: &str,
    request: SkillCandidateReviewRequest,
) -> Result<SkillCandidateReviewEvent, String> {
    if request.project_id != project_id
        || !safe_id(&request.candidate_id)
        || !is_sha256(&request.decision_sha256)
        || !is_sha256(&request.acceptance_checks_sha256)
        || !valid_review_text(&request.actor_label, 120)
        || !valid_review_text(&request.rationale, 2_000)
    {
        return Err("capability review target, actor, or rationale is invalid".into());
    }
    let events = read_events(root, workspace, project_id)?;
    let latest = events
        .iter()
        .rev()
        .find(|event| event.candidate_id == request.candidate_id);
    let candidate_root = workspace
        .join("capabilities/candidates")
        .join(&request.candidate_id);
    let candidate = if request.action == SkillCandidateReviewAction::Revoke {
        None
    } else {
        let candidate = validate_candidate(&candidate_root)?;
        if candidate.decision_sha256 != request.decision_sha256
            || candidate.acceptance_checks_sha256 != request.acceptance_checks_sha256
        {
            return Err(
                "review must target the exact current candidate and acceptance checks".into(),
            );
        }
        Some(candidate)
    };
    let (decision_sha256, acceptance_checks_sha256, active_tree_sha256) = match request.action {
        SkillCandidateReviewAction::Activate | SkillCandidateReviewAction::Reject => {
            let candidate = candidate
                .as_ref()
                .expect("candidate required for this action");
            (
                candidate.decision_sha256.clone(),
                candidate.acceptance_checks_sha256.clone(),
                candidate.active_tree_sha256.clone(),
            )
        }
        SkillCandidateReviewAction::Revoke => {
            let last = latest.ok_or("there is no reviewed activation to revoke")?;
            if last.action != SkillCandidateReviewAction::Activate {
                return Err("the latest Human review is not an active capability".into());
            }
            if last.decision_sha256 != request.decision_sha256
                || last.acceptance_checks_sha256 != request.acceptance_checks_sha256
            {
                return Err("revocation must target the exact active review".into());
            }
            (
                last.decision_sha256.clone(),
                last.acceptance_checks_sha256.clone(),
                last.active_tree_sha256.clone(),
            )
        }
    };
    if latest.is_some_and(|event| {
        event.action == request.action && event.decision_sha256 == decision_sha256
    }) {
        return Err("the latest review already records this action for the exact candidate".into());
    }

    let active = active_skill_path(workspace, &request.candidate_id);
    let mut rollback: Option<(PathBuf, PathBuf)> = None;
    match request.action {
        SkillCandidateReviewAction::Activate => {
            let active_parent = ensure_real_directory(workspace, Path::new(".opencode/skills"))?;
            if std::fs::symlink_metadata(&active).is_ok() {
                return Err("a project Skill already uses this candidate id; activation will not overwrite it".into());
            }
            let stage = active_parent.join(format!(
                ".ai4heor-activate-{}-{}",
                request.candidate_id,
                crate::runtime::random_hex(8)
            ));
            let candidate = candidate
                .as_ref()
                .expect("activation candidate was validated");
            if let Err(error) = copy_candidate_skill(&candidate_root, &stage, candidate) {
                let _ = remove_exact_tree(&stage);
                return Err(error);
            }
            std::fs::rename(&stage, &active)
                .map_err(|error| format!("capability activation failed: {error}"))?;
            rollback = Some((active.clone(), stage));
        }
        SkillCandidateReviewAction::Reject => {
            if std::fs::symlink_metadata(&active).is_ok() {
                return Err("an active or unmanaged project Skill must be revoked or resolved before rejection".into());
            }
        }
        SkillCandidateReviewAction::Revoke => {
            if active_tree_state(&active, &active_tree_sha256) != "exact" {
                return Err("active Skill bytes do not exactly match the activation record; revocation will not delete changed content".into());
            }
            let active_parent = ensure_real_directory(workspace, Path::new(".opencode/skills"))?;
            let stage = active_parent.join(format!(
                ".ai4heor-revoke-{}-{}",
                request.candidate_id,
                crate::runtime::random_hex(8)
            ));
            std::fs::rename(&active, &stage)
                .map_err(|error| format!("capability revocation staging failed: {error}"))?;
            rollback = Some((stage, active.clone()));
        }
    }

    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| error.to_string())?
        .as_secs();
    let review_id = crate::runtime::random_hex(16);
    let record_path = format!(
        "capabilities/reviews/{}-{review_id}.json",
        request.candidate_id
    );
    let mut event = SkillCandidateReviewEvent {
        schema_version: EVENT_SCHEMA,
        sequence: events.len() as u64 + 1,
        review_id,
        project_id: project_id.into(),
        candidate_id: request.candidate_id,
        decision_sha256,
        acceptance_checks_sha256,
        active_tree_sha256,
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
    event.event_hash = event_hash(&event)?;

    let persist = write_review_record(workspace, &event).and_then(|_| append_event(root, &event));
    if let Err(error) = persist {
        let _ = std::fs::remove_file(workspace.join(&event.record_path));
        if let Some((from, to)) = &rollback {
            if std::fs::rename(from, to).is_ok()
                && event.action == SkillCandidateReviewAction::Activate
            {
                let _ = remove_exact_tree(to);
            }
        }
        return Err(error);
    }
    if event.action == SkillCandidateReviewAction::Revoke {
        if let Some((stage, _)) = &rollback {
            remove_exact_tree(stage)?;
        }
    }
    crate::git_snapshot::commit_best_effort(workspace, "Record AI4HEOR capability Human review");
    Ok(event)
}

#[tauri::command(async)]
pub fn audit_skill_candidates(
    app: AppHandle,
    state: tauri::State<CapabilityReviewState>,
) -> Result<SkillCandidateAudit, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "capability review lock poisoned")?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    let project_id = match crate::project::require_project_id(&workspace) {
        Ok(project_id) => project_id,
        Err(_) => {
            return Ok(SkillCandidateAudit {
                project_available: false,
                project_id: None,
                complete: true,
                candidates: Vec::new(),
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
pub fn append_skill_candidate_review(
    app: AppHandle,
    capability_state: tauri::State<CapabilityReviewState>,
    runtime_state: tauri::State<crate::runtime::RuntimeState>,
    request: SkillCandidateReviewRequest,
) -> Result<SkillCandidateReviewEvent, String> {
    let _guard = capability_state
        .0
        .lock()
        .map_err(|_| "capability review lock poisoned")?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    let project_id = crate::project::require_project_id(&workspace)?;
    let event = apply_review(&workspace, &review_root(&app)?, &project_id, request)?;
    if matches!(
        event.action,
        SkillCandidateReviewAction::Activate | SkillCandidateReviewAction::Revoke
    ) {
        if let Err(error) = crate::runtime::restart_sidecar_if_running(&app, &runtime_state) {
            // The Human decision and exact filesystem transition are already
            // committed. Do not misreport them as failed because the runtime
            // restart is separately recoverable through the normal reconnect.
            eprintln!("capability review recorded; runtime restart must be retried: {error}");
        }
    }
    Ok(event)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn workspace(tag: &str) -> (PathBuf, PathBuf, String) {
        let root = std::env::temp_dir().join(format!(
            "ai4heor-capability-{tag}-{}-{}",
            std::process::id(),
            crate::runtime::random_hex(4)
        ));
        let workspace = root.join("workspace");
        let reviews = root.join("private");
        std::fs::create_dir_all(workspace.join("capabilities/candidates")).unwrap();
        std::fs::create_dir_all(workspace.join("capabilities/reviews")).unwrap();
        (workspace, reviews, "0123456789abcdef".into())
    }

    fn fixture(workspace: &Path, id: &str) -> ValidatedCandidate {
        let root = workspace.join("capabilities/candidates").join(id);
        std::fs::create_dir_all(root.join("skill/references")).unwrap();
        let skill = format!(
            "---\nname: {id}\ndescription: Format a reviewed HEOR table without changing its scientific content.\n---\n\n# Instructions\n\nPreserve every value and limitation.\n"
        );
        let reference = "# Boundary\n\nPresentation only.\n";
        std::fs::write(root.join("skill/SKILL.md"), &skill).unwrap();
        std::fs::write(root.join("skill/references/boundary.md"), reference).unwrap();
        let records = [
            ("skill/SKILL.md", skill.as_bytes()),
            ("skill/references/boundary.md", reference.as_bytes()),
        ]
        .into_iter()
        .map(|(path, raw)| serde_json::json!({"path": path, "bytes": raw.len(), "sha256": sha256(raw)}))
        .collect::<Vec<_>>();
        let manifest = serde_json::json!({
            "schema": CANDIDATE_SCHEMA,
            "id": id,
            "status": "candidate",
            "created_at": "2026-07-19T13:00:00Z",
            "request": "Keep a reusable Chinese HEOR table note style.",
            "localized": {
                "en": {"display_name": "HEOR table notes", "description": "Format reviewed table notes."},
                "zh-Hans": {"display_name": "药物经济学表注", "description": "整理已经复核的表注。"}
            },
            "authoring": {"provider": "test-provider", "model": "test-model", "session_ref": "local-test"},
            "source": {
                "kind": "researcher-request",
                "copyright_holder": "Researcher",
                "rights_basis": "Original instructions",
                "license_spdx": "LicenseRef-Project-Private",
                "license_note": "Local project use only"
            },
            "permissions": {"network": false, "secrets": false, "commands": false, "outside_workspace": false},
            "files": records,
            "limitations": ["Presentation only"],
            "acceptance_checks": ["Values remain unchanged", "Limitations remain visible"]
        });
        let manifest_raw = serde_json::to_vec_pretty(&manifest).unwrap();
        std::fs::write(root.join("candidate.json"), &manifest_raw).unwrap();
        let mut decision = Sha256::new();
        decision.update(&manifest_raw);
        decision.update([0]);
        decision.update(skill.as_bytes());
        decision.update([0]);
        decision.update(reference.as_bytes());
        let decision_sha256 = format!("{:x}", decision.finalize());
        let validation = serde_json::json!({
            "schema": VALIDATION_SCHEMA,
            "candidate_id": id,
            "validated_at": "2026-07-19T13:01:00Z",
            "valid": true,
            "instruction_only": true,
            "decision_sha256": decision_sha256,
            "checked_files": ["skill/SKILL.md", "skill/references/boundary.md"],
            "errors": []
        });
        std::fs::write(
            root.join("validation.json"),
            serde_json::to_vec_pretty(&validation).unwrap(),
        )
        .unwrap();
        validate_candidate(&root).unwrap()
    }

    fn request(
        project_id: &str,
        candidate: &ValidatedCandidate,
        action: SkillCandidateReviewAction,
    ) -> SkillCandidateReviewRequest {
        SkillCandidateReviewRequest {
            project_id: project_id.into(),
            candidate_id: candidate.id.clone(),
            decision_sha256: candidate.decision_sha256.clone(),
            acceptance_checks_sha256: candidate.acceptance_checks_sha256.clone(),
            action,
            actor_label: "Local researcher".into(),
            rationale:
                "Reviewed the exact instructions, limits, rights note, and acceptance checks."
                    .into(),
        }
    }

    #[test]
    fn exact_candidate_can_be_activated_and_revoked_with_a_verified_chain() {
        let (workspace, reviews, project_id) = workspace("roundtrip");
        let candidate = fixture(&workspace, "table-note-style");
        let activated = apply_review(
            &workspace,
            &reviews,
            &project_id,
            request(
                &project_id,
                &candidate,
                SkillCandidateReviewAction::Activate,
            ),
        )
        .unwrap();
        assert_eq!(activated.action, SkillCandidateReviewAction::Activate);
        assert_eq!(
            crate::asset_admission::tree_sha256(&active_skill_path(&workspace, &candidate.id))
                .unwrap(),
            candidate.active_tree_sha256
        );
        let audit = audit_workspace(&workspace, &reviews, &project_id).unwrap();
        assert_eq!(audit.candidates[0].status, "active");
        assert!(audit.candidates[0].can_revoke);

        let revoked = apply_review(
            &workspace,
            &reviews,
            &project_id,
            request(&project_id, &candidate, SkillCandidateReviewAction::Revoke),
        )
        .unwrap();
        assert_eq!(
            revoked.previous_hash.as_deref(),
            Some(activated.event_hash.as_str())
        );
        assert!(!active_skill_path(&workspace, &candidate.id).exists());
        let audit = audit_workspace(&workspace, &reviews, &project_id).unwrap();
        assert_eq!(audit.candidates[0].status, "revoked");
        assert!(audit.candidates[0].can_activate);
        std::fs::remove_dir_all(workspace.parent().unwrap()).unwrap();
    }

    #[test]
    fn changed_candidate_is_rejected_before_activation() {
        let (workspace, reviews, project_id) = workspace("candidate-drift");
        let candidate = fixture(&workspace, "table-note-style");
        std::fs::write(
            workspace.join("capabilities/candidates/table-note-style/skill/SKILL.md"),
            "changed",
        )
        .unwrap();
        let error = apply_review(
            &workspace,
            &reviews,
            &project_id,
            request(
                &project_id,
                &candidate,
                SkillCandidateReviewAction::Activate,
            ),
        )
        .unwrap_err();
        assert!(error.contains("hash or size changed"));
        assert!(!active_skill_path(&workspace, &candidate.id).exists());
        std::fs::remove_dir_all(workspace.parent().unwrap()).unwrap();
    }

    #[test]
    fn changed_active_skill_is_never_deleted_by_revocation() {
        let (workspace, reviews, project_id) = workspace("active-drift");
        let candidate = fixture(&workspace, "table-note-style");
        apply_review(
            &workspace,
            &reviews,
            &project_id,
            request(
                &project_id,
                &candidate,
                SkillCandidateReviewAction::Activate,
            ),
        )
        .unwrap();
        let active = active_skill_path(&workspace, &candidate.id);
        std::fs::write(active.join("SKILL.md"), "researcher edit").unwrap();
        let error = apply_review(
            &workspace,
            &reviews,
            &project_id,
            request(&project_id, &candidate, SkillCandidateReviewAction::Revoke),
        )
        .unwrap_err();
        assert!(error.contains("will not delete changed content"));
        assert_eq!(
            std::fs::read_to_string(active.join("SKILL.md")).unwrap(),
            "researcher edit"
        );
        let audit = audit_workspace(&workspace, &reviews, &project_id).unwrap();
        assert_eq!(audit.candidates[0].status, "drifted");
        std::fs::remove_dir_all(workspace.parent().unwrap()).unwrap();
    }

    #[test]
    fn rejection_records_the_exact_candidate_without_loading_it() {
        let (workspace, reviews, project_id) = workspace("reject");
        let candidate = fixture(&workspace, "table-note-style");
        apply_review(
            &workspace,
            &reviews,
            &project_id,
            request(&project_id, &candidate, SkillCandidateReviewAction::Reject),
        )
        .unwrap();
        assert!(!active_skill_path(&workspace, &candidate.id).exists());
        let audit = audit_workspace(&workspace, &reviews, &project_id).unwrap();
        assert_eq!(audit.candidates[0].status, "rejected");
        assert!(!audit.candidates[0].can_reject);
        std::fs::remove_dir_all(workspace.parent().unwrap()).unwrap();
    }

    #[test]
    fn tampered_review_snapshot_fails_the_entire_audit_closed() {
        let (workspace, reviews, project_id) = workspace("log-tamper");
        let candidate = fixture(&workspace, "table-note-style");
        let event = apply_review(
            &workspace,
            &reviews,
            &project_id,
            request(&project_id, &candidate, SkillCandidateReviewAction::Reject),
        )
        .unwrap();
        std::fs::write(workspace.join(event.record_path), b"{}\n").unwrap();
        assert!(audit_workspace(&workspace, &reviews, &project_id)
            .unwrap_err()
            .contains("does not match"));
        std::fs::remove_dir_all(workspace.parent().unwrap()).unwrap();
    }
}
