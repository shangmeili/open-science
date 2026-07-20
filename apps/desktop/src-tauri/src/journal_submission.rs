//! Deterministic, source-bound target-journal submission checks for AI4HEOR.
//!
//! The Agent prepares a bounded manifest from a researcher-provided author-guide
//! snapshot. Native code revalidates every byte and performs only explicit,
//! mechanical checks. A pass never becomes journal or submission approval.

use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::io::Write;
#[cfg(test)]
use std::path::PathBuf;
use std::path::{Component, Path};
use tauri::AppHandle;

pub const JOURNAL_SUBMISSION_MANIFEST_PATH: &str = "deliverables/journal-submission-check.json";
pub const JOURNAL_SUBMISSION_MARKDOWN_PATH: &str = "deliverables/journal-submission-check.md";
pub const JOURNAL_SUBMISSION_RESULTS_PATH: &str =
    "deliverables/journal-submission-check.results.json";
pub const JOURNAL_SUBMISSION_AUDIT_PATH: &str = "deliverables/journal-submission-check.audit.json";
const SCHEMA_VERSION: &str = "ai4heor-journal-submission-check/v1";
const ENGINE_VERSION: &str = "0.1.0";
const MANIFEST_CAP_BYTES: u64 = 4 * 1024 * 1024;
const FILE_CAP_BYTES: u64 = 50 * 1024 * 1024;

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct SubmissionManifest {
    schema_version: String,
    check_id: String,
    title: String,
    language: String,
    prepared_on: String,
    journal: JournalSpec,
    files: Vec<FileBinding>,
    rules: Vec<SubmissionRule>,
    human_review: HumanReview,
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct JournalSpec {
    name: String,
    article_type: String,
    guide_url: String,
    accessed_on: String,
    version_label: String,
    source_path: String,
    source_sha256: String,
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct FileBinding {
    role: String,
    label: String,
    path: String,
    sha256: String,
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct SubmissionRule {
    id: String,
    label: String,
    kind: String,
    severity: String,
    guide_locator: String,
    note: String,
    #[serde(default)]
    file_role: String,
    #[serde(default)]
    limit: Option<u64>,
    #[serde(default)]
    value: Option<String>,
    #[serde(default)]
    allowed: Option<Vec<String>>,
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct HumanReview {
    status: String,
}

#[derive(Clone, Debug)]
struct LoadedSubmission {
    manifest: SubmissionManifest,
    manifest_raw: Vec<u8>,
    guide_raw: Vec<u8>,
    files_raw: BTreeMap<String, Vec<u8>>,
    results: Vec<RuleResult>,
}

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
struct RuleResult {
    id: String,
    label: String,
    kind: String,
    severity: String,
    outcome: String,
    measured: String,
    expected: String,
    guide_locator: String,
    note: String,
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct JournalSubmissionAudit {
    pub complete: bool,
    pub ready_to_generate: bool,
    pub outputs_current: bool,
    pub status: &'static str,
    pub check_id: String,
    pub title: String,
    pub journal_name: String,
    pub article_type: String,
    pub guide_accessed_on: String,
    pub manifest_path: &'static str,
    pub markdown_path: &'static str,
    pub results_path: &'static str,
    pub audit_path: &'static str,
    pub manifest_sha256: String,
    pub file_count: usize,
    pub rule_count: usize,
    pub passed_count: usize,
    pub failed_required_count: usize,
    pub review_issue_count: usize,
    pub unresolved_count: usize,
    pub human_review_status: String,
    pub errors: Vec<String>,
    pub warnings: Vec<String>,
}

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize, PartialEq, Eq)]
struct GenerationRecord {
    schema_version: String,
    generator: String,
    generator_version: String,
    check_id: String,
    manifest_path: String,
    manifest_sha256: String,
    guide_path: String,
    guide_sha256: String,
    file_hashes: BTreeMap<String, String>,
    markdown_path: String,
    markdown_sha256: String,
    results_path: String,
    results_sha256: String,
    rule_count: usize,
    failed_required_count: usize,
    review_issue_count: usize,
    unresolved_count: usize,
    human_review_status: String,
}

#[derive(serde::Serialize)]
struct ResultsPackage<'a> {
    schema_version: &'static str,
    generator: &'static str,
    generator_version: &'static str,
    check_id: &'a str,
    title: &'a str,
    language: &'a str,
    prepared_on: &'a str,
    journal: ResultsJournal<'a>,
    manifest_path: &'static str,
    manifest_sha256: String,
    file_hashes: BTreeMap<String, String>,
    summary: ResultsSummary,
    results: &'a [RuleResult],
    counting_method: [&'static str; 3],
    limitations: [&'static str; 5],
    human_review_status: &'static str,
}

#[derive(serde::Serialize)]
struct ResultsJournal<'a> {
    name: &'a str,
    article_type: &'a str,
    guide_url: &'a str,
    accessed_on: &'a str,
    version_label: &'a str,
    source_path: &'a str,
    source_sha256: &'a str,
}

#[derive(serde::Serialize)]
struct ResultsSummary {
    passed: usize,
    failed_required: usize,
    review_issues: usize,
    unresolved: usize,
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn valid_text(value: &str, minimum: usize, maximum: usize) -> bool {
    let trimmed = value.trim();
    let length = trimmed.chars().count();
    (minimum..=maximum).contains(&length)
        && !trimmed
            .chars()
            .any(|character| character.is_control() && !matches!(character, '\n' | '\r' | '\t'))
}

fn safe_id(value: &str) -> bool {
    if value.is_empty() || value.len() > 64 {
        return false;
    }
    value.bytes().enumerate().all(|(index, byte)| {
        if index == 0 {
            byte.is_ascii_lowercase()
        } else {
            byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-')
        }
    })
}

fn valid_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn valid_date(value: &str) -> bool {
    if value.len() != 10 || value.as_bytes()[4] != b'-' || value.as_bytes()[7] != b'-' {
        return false;
    }
    let Ok(year) = value[0..4].parse::<i32>() else {
        return false;
    };
    let Ok(month) = value[5..7].parse::<u32>() else {
        return false;
    };
    let Ok(day) = value[8..10].parse::<u32>() else {
        return false;
    };
    if !(1900..=9999).contains(&year) || !(1..=12).contains(&month) {
        return false;
    }
    let leap = year % 4 == 0 && (year % 100 != 0 || year % 400 == 0);
    let days = [
        31,
        if leap { 29 } else { 28 },
        31,
        30,
        31,
        30,
        31,
        31,
        30,
        31,
        30,
        31,
    ];
    (1..=days[(month - 1) as usize]).contains(&day)
}

fn valid_https(value: &str) -> bool {
    valid_text(value, 12, 500)
        && value.starts_with("https://")
        && value[8..].split('/').next().is_some_and(|host| {
            !host.is_empty()
                && !host.contains('@')
                && !host.contains(':')
                && host.contains('.')
                && host
                    .bytes()
                    .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'-'))
        })
}

fn safe_relative(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 240
        && !value.contains('\\')
        && Path::new(value)
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
}

fn is_reserved_path(value: &str) -> bool {
    matches!(
        value,
        JOURNAL_SUBMISSION_MANIFEST_PATH
            | JOURNAL_SUBMISSION_MARKDOWN_PATH
            | JOURNAL_SUBMISSION_RESULTS_PATH
            | JOURNAL_SUBMISSION_AUDIT_PATH
    )
}

fn resolve_regular(workspace: &Path, relative: &str) -> Result<Vec<u8>, String> {
    if !safe_relative(relative) || is_reserved_path(relative) {
        return Err(format!("{relative} is not a safe source path"));
    }
    let root = workspace
        .canonicalize()
        .map_err(|error| format!("workspace unavailable: {error}"))?;
    let mut current = root.clone();
    for component in Path::new(relative).components() {
        let Component::Normal(part) = component else {
            return Err(format!("{relative} is not a safe source path"));
        };
        current.push(part);
        let metadata = std::fs::symlink_metadata(&current)
            .map_err(|error| format!("{relative} unavailable: {error}"))?;
        if metadata.file_type().is_symlink() {
            return Err(format!("{relative} traverses a symlink"));
        }
    }
    let canonical = current
        .canonicalize()
        .map_err(|error| format!("{relative} unavailable: {error}"))?;
    if !canonical.starts_with(&root) {
        return Err(format!("{relative} escapes the workspace"));
    }
    let metadata = canonical
        .metadata()
        .map_err(|error| format!("{relative} unavailable: {error}"))?;
    if !metadata.is_file() || metadata.len() > FILE_CAP_BYTES {
        return Err(format!("{relative} is not a supported regular file"));
    }
    std::fs::read(canonical).map_err(|error| format!("cannot read {relative}: {error}"))
}

fn normalise_heading(value: &str) -> String {
    value
        .split_whitespace()
        .collect::<Vec<_>>()
        .join(" ")
        .to_lowercase()
}

fn visible_markdown(raw: &str) -> (Vec<String>, Vec<(usize, String, usize)>) {
    let lines = raw.lines().collect::<Vec<_>>();
    let mut visible = Vec::new();
    let mut headings = Vec::new();
    let mut in_front_matter = lines.first().is_some_and(|line| line.trim() == "---");
    let mut front_matter_closed = !in_front_matter;
    let mut in_fence = false;
    for (index, line) in lines.iter().enumerate() {
        let trimmed = line.trim();
        if in_front_matter {
            if index > 0 && trimmed == "---" {
                in_front_matter = false;
                front_matter_closed = true;
            }
            continue;
        }
        if !front_matter_closed {
            continue;
        }
        if trimmed.starts_with("```") || trimmed.starts_with("~~~") {
            in_fence = !in_fence;
            continue;
        }
        if in_fence {
            continue;
        }
        if let Some((level, text)) = markdown_heading(trimmed) {
            headings.push((level, text.to_string(), visible.len()));
            visible.push(text.to_string());
        } else {
            visible.push((*line).to_string());
        }
    }
    (visible, headings)
}

fn markdown_heading(line: &str) -> Option<(usize, &str)> {
    let level = line.bytes().take_while(|byte| *byte == b'#').count();
    if !(1..=6).contains(&level) || line.as_bytes().get(level) != Some(&b' ') {
        return None;
    }
    let text = line[level + 1..].trim().trim_end_matches('#').trim();
    (!text.is_empty()).then_some((level, text))
}

fn is_cjk(character: char) -> bool {
    matches!(character as u32, 0x3400..=0x4DBF | 0x4E00..=0x9FFF | 0xF900..=0xFAFF)
}

fn count_words(text: &str) -> usize {
    let mut count = 0usize;
    let mut in_word = false;
    for character in text.chars() {
        if is_cjk(character) {
            count += 1;
            in_word = false;
        } else if character.is_alphanumeric() {
            if !in_word {
                count += 1;
                in_word = true;
            }
        } else if !matches!(character, '\'' | '’' | '-') {
            in_word = false;
        }
    }
    count
}

fn count_characters(text: &str) -> usize {
    text.chars()
        .filter(|character| !character.is_whitespace())
        .count()
}

fn section_text(
    visible: &[String],
    headings: &[(usize, String, usize)],
    requested: &str,
) -> Option<String> {
    let target = normalise_heading(requested);
    let (index, (level, _, start)) = headings
        .iter()
        .enumerate()
        .find(|(_, (_, heading, _))| normalise_heading(heading) == target)?;
    let end = headings
        .iter()
        .skip(index + 1)
        .find(|(next_level, _, _)| next_level <= level)
        .map(|(_, _, line)| *line)
        .unwrap_or(visible.len());
    Some(visible[start + 1..end].join("\n"))
}

fn markdown_table_count(lines: &[String]) -> usize {
    lines
        .iter()
        .filter(|line| {
            let cells = line.trim().trim_matches('|').split('|').collect::<Vec<_>>();
            cells.len() >= 2
                && cells.iter().all(|cell| {
                    let cell = cell.trim().trim_matches(':');
                    cell.len() >= 3 && cell.bytes().all(|byte| byte == b'-')
                })
        })
        .count()
}

fn markdown_figure_count(lines: &[String]) -> usize {
    lines
        .iter()
        .map(|line| line.match_indices("![").count())
        .sum()
}

fn expected_fields(kind: &str) -> Option<(bool, bool, bool)> {
    match kind {
        "required_file" => Some((false, false, false)),
        "file_extension_in" => Some((false, false, true)),
        "file_size_max_bytes"
        | "title_characters_max"
        | "document_words_max"
        | "document_characters_max"
        | "table_count_max"
        | "figure_count_max" => Some((true, false, false)),
        "section_words_max" | "section_characters_max" => Some((true, true, false)),
        "required_heading" => Some((false, true, false)),
        _ => None,
    }
}

fn validate_rule_shapes(value: &serde_json::Value) -> Vec<String> {
    const BASE: &[&str] = &[
        "id",
        "label",
        "kind",
        "severity",
        "guide_locator",
        "note",
        "file_role",
    ];
    let mut errors = Vec::new();
    let Some(rules) = value.get("rules").and_then(serde_json::Value::as_array) else {
        return errors;
    };
    for (index, rule) in rules.iter().enumerate() {
        let Some(object) = rule.as_object() else {
            continue;
        };
        let kind = object
            .get("kind")
            .and_then(serde_json::Value::as_str)
            .unwrap_or_default();
        let mut expected = BASE.iter().copied().collect::<BTreeSet<_>>();
        match kind {
            "file_extension_in" => {
                expected.insert("allowed");
            }
            "file_size_max_bytes"
            | "title_characters_max"
            | "document_words_max"
            | "document_characters_max"
            | "table_count_max"
            | "figure_count_max" => {
                expected.insert("limit");
            }
            "section_words_max" | "section_characters_max" => {
                expected.insert("limit");
                expected.insert("value");
            }
            "required_heading" => {
                expected.insert("value");
            }
            "required_file" => {}
            _ => continue,
        }
        let actual = object.keys().map(String::as_str).collect::<BTreeSet<_>>();
        if actual != expected {
            errors.push(format!(
                "rule at index {index} fields do not exactly match kind {kind}"
            ));
        }
    }
    errors
}

fn evaluate_rule(rule: &SubmissionRule, file: &FileBinding, raw: &[u8]) -> RuleResult {
    let unresolved = |measured: &str, expected: String| RuleResult {
        id: rule.id.clone(),
        label: rule.label.clone(),
        kind: rule.kind.clone(),
        severity: rule.severity.clone(),
        outcome: "unresolved".into(),
        measured: measured.into(),
        expected,
        guide_locator: rule.guide_locator.clone(),
        note: rule.note.clone(),
    };
    let result = |passes: bool, measured: String, expected: String| RuleResult {
        id: rule.id.clone(),
        label: rule.label.clone(),
        kind: rule.kind.clone(),
        severity: rule.severity.clone(),
        outcome: if passes { "pass" } else { "fail" }.into(),
        measured,
        expected,
        guide_locator: rule.guide_locator.clone(),
        note: rule.note.clone(),
    };
    match rule.kind.as_str() {
        "required_file" => result(
            true,
            file.path.clone(),
            format!("role {} present", file.role),
        ),
        "file_extension_in" => {
            let allowed = rule.allowed.as_ref().cloned().unwrap_or_default();
            let path = file.path.to_lowercase();
            result(
                allowed.iter().any(|extension| path.ends_with(extension)),
                Path::new(&file.path)
                    .extension()
                    .and_then(|value| value.to_str())
                    .map(|value| format!(".{value}"))
                    .unwrap_or_default(),
                allowed.join(", "),
            )
        }
        "file_size_max_bytes" => result(
            raw.len() as u64 <= rule.limit.unwrap_or_default(),
            raw.len().to_string(),
            format!("≤ {} bytes", rule.limit.unwrap_or_default()),
        ),
        kind => {
            let Ok(markdown) = std::str::from_utf8(raw) else {
                return unresolved("not UTF-8 Markdown", "mechanical Markdown check".into());
            };
            let (visible, headings) = visible_markdown(markdown);
            let joined = visible.join("\n");
            match kind {
                "title_characters_max" => {
                    let Some((_, title, _)) = headings.iter().find(|(level, _, _)| *level == 1)
                    else {
                        return unresolved(
                            "no level-one title",
                            format!("≤ {} characters", rule.limit.unwrap_or_default()),
                        );
                    };
                    let measured = count_characters(title);
                    result(
                        measured as u64 <= rule.limit.unwrap_or_default(),
                        measured.to_string(),
                        format!("≤ {} characters", rule.limit.unwrap_or_default()),
                    )
                }
                "document_words_max" => {
                    let measured = count_words(&joined);
                    result(
                        measured as u64 <= rule.limit.unwrap_or_default(),
                        measured.to_string(),
                        format!("≤ {} tokens", rule.limit.unwrap_or_default()),
                    )
                }
                "document_characters_max" => {
                    let measured = count_characters(&joined);
                    result(
                        measured as u64 <= rule.limit.unwrap_or_default(),
                        measured.to_string(),
                        format!("≤ {} characters", rule.limit.unwrap_or_default()),
                    )
                }
                "section_words_max" | "section_characters_max" => {
                    let section_name = rule.value.as_deref().unwrap_or_default();
                    let Some(section) = section_text(&visible, &headings, section_name) else {
                        return unresolved(
                            "section not found",
                            format!(
                                "section {section_name} ≤ {}",
                                rule.limit.unwrap_or_default()
                            ),
                        );
                    };
                    let measured = if kind == "section_words_max" {
                        count_words(&section)
                    } else {
                        count_characters(&section)
                    };
                    let unit = if kind == "section_words_max" {
                        "tokens"
                    } else {
                        "characters"
                    };
                    result(
                        measured as u64 <= rule.limit.unwrap_or_default(),
                        measured.to_string(),
                        format!("≤ {} {unit}", rule.limit.unwrap_or_default()),
                    )
                }
                "table_count_max" => {
                    let measured = markdown_table_count(&visible);
                    result(
                        measured as u64 <= rule.limit.unwrap_or_default(),
                        measured.to_string(),
                        format!("≤ {} tables", rule.limit.unwrap_or_default()),
                    )
                }
                "figure_count_max" => {
                    let measured = markdown_figure_count(&visible);
                    result(
                        measured as u64 <= rule.limit.unwrap_or_default(),
                        measured.to_string(),
                        format!("≤ {} figures", rule.limit.unwrap_or_default()),
                    )
                }
                "required_heading" => {
                    let requested = rule.value.as_deref().unwrap_or_default();
                    let present = headings.iter().any(|(_, heading, _)| {
                        normalise_heading(heading) == normalise_heading(requested)
                    });
                    result(
                        present,
                        if present { "present" } else { "missing" }.into(),
                        format!("heading: {requested}"),
                    )
                }
                _ => unresolved("unsupported", "supported deterministic rule".into()),
            }
        }
    }
}

fn validate_manifest(
    workspace: &Path,
    manifest: SubmissionManifest,
    manifest_raw: Vec<u8>,
) -> Result<LoadedSubmission, Vec<String>> {
    let mut errors = Vec::new();
    if manifest.schema_version != SCHEMA_VERSION {
        errors.push(format!("schema_version must be {SCHEMA_VERSION}"));
    }
    if !safe_id(&manifest.check_id) {
        errors.push("check_id must be a safe lowercase identifier".into());
    }
    if !valid_text(&manifest.title, 3, 160) {
        errors.push("title is missing or outside its supported length".into());
    }
    if !matches!(manifest.language.as_str(), "zh-CN" | "en") {
        errors.push("language must be zh-CN or en".into());
    }
    if !valid_date(&manifest.prepared_on) {
        errors.push("prepared_on must be a valid YYYY-MM-DD date".into());
    }
    if manifest.human_review.status != "awaiting_human_review" {
        errors.push("human_review.status must remain awaiting_human_review".into());
    }
    for (field, value, minimum, maximum) in [
        ("journal.name", manifest.journal.name.as_str(), 2, 160),
        (
            "journal.article_type",
            manifest.journal.article_type.as_str(),
            2,
            160,
        ),
        (
            "journal.version_label",
            manifest.journal.version_label.as_str(),
            1,
            160,
        ),
    ] {
        if !valid_text(value, minimum, maximum) {
            errors.push(format!(
                "{field} is missing or outside its supported length"
            ));
        }
    }
    if !valid_https(&manifest.journal.guide_url) {
        errors.push("journal.guide_url must be an official HTTPS URL without credentials".into());
    }
    if !valid_date(&manifest.journal.accessed_on) {
        errors.push("journal.accessed_on must be a valid YYYY-MM-DD date".into());
    }
    if !valid_sha256(&manifest.journal.source_sha256) {
        errors.push("journal.source_sha256 must be a lowercase SHA-256".into());
    }
    let guide_raw = match resolve_regular(workspace, &manifest.journal.source_path) {
        Ok(raw) if sha256(&raw) == manifest.journal.source_sha256 => raw,
        Ok(_) => {
            errors.push("journal guide snapshot SHA-256 does not match".into());
            Vec::new()
        }
        Err(error) => {
            errors.push(error);
            Vec::new()
        }
    };
    if manifest.files.is_empty() || manifest.files.len() > 32 {
        errors.push("files must contain between 1 and 32 items".into());
    }
    if manifest.rules.is_empty() || manifest.rules.len() > 64 {
        errors.push("rules must contain between 1 and 64 items".into());
    }
    let mut roles = BTreeSet::new();
    let mut paths = BTreeSet::new();
    let mut bindings = BTreeMap::new();
    let mut files_raw = BTreeMap::new();
    for file in &manifest.files {
        if !safe_id(&file.role) || !roles.insert(file.role.clone()) {
            errors.push(format!("file role is invalid or duplicated: {}", file.role));
        }
        if !valid_text(&file.label, 1, 160) {
            errors.push(format!("file {} needs a bounded label", file.role));
        }
        if !safe_relative(&file.path)
            || is_reserved_path(&file.path)
            || file.path == manifest.journal.source_path
            || !paths.insert(file.path.to_lowercase())
        {
            errors.push(format!("file path is invalid or duplicated: {}", file.path));
            continue;
        }
        if !valid_sha256(&file.sha256) {
            errors.push(format!("file {} has an invalid SHA-256", file.role));
            continue;
        }
        match resolve_regular(workspace, &file.path) {
            Ok(raw) if sha256(&raw) == file.sha256 => {
                bindings.insert(file.role.clone(), file);
                files_raw.insert(file.role.clone(), raw);
            }
            Ok(_) => errors.push(format!("file {} SHA-256 does not match", file.role)),
            Err(error) => errors.push(error),
        }
    }
    if !bindings.contains_key("manuscript") {
        errors.push("files must contain exactly one manuscript role".into());
    } else if !bindings["manuscript"].path.to_lowercase().ends_with(".md") {
        errors.push("the manuscript file must be Markdown (.md)".into());
    }
    let mut rule_ids = BTreeSet::new();
    let mut results = Vec::new();
    for rule in &manifest.rules {
        if !safe_id(&rule.id) || !rule_ids.insert(rule.id.clone()) {
            errors.push(format!("rule id is invalid or duplicated: {}", rule.id));
        }
        if !valid_text(&rule.label, 2, 160)
            || !valid_text(&rule.guide_locator, 1, 240)
            || !valid_text(&rule.note, 0, 500)
        {
            errors.push(format!("rule {} has invalid descriptive text", rule.id));
        }
        if !matches!(rule.severity.as_str(), "required" | "review") {
            errors.push(format!("rule {} has unsupported severity", rule.id));
        }
        let Some((needs_limit, needs_value, needs_allowed)) = expected_fields(&rule.kind) else {
            errors.push(format!("rule {} has unsupported kind", rule.id));
            continue;
        };
        if needs_limit != rule.limit.is_some()
            || needs_value != rule.value.is_some()
            || needs_allowed != rule.allowed.is_some()
        {
            errors.push(format!("rule {} fields do not match its kind", rule.id));
        }
        if rule.limit.is_some_and(|limit| limit > 1_000_000_000) {
            errors.push(format!(
                "rule {} limit exceeds the supported range",
                rule.id
            ));
        }
        if rule
            .value
            .as_deref()
            .is_some_and(|value| !valid_text(value, 1, 160))
        {
            errors.push(format!("rule {} value is invalid", rule.id));
        }
        if let Some(allowed) = &rule.allowed {
            let distinct = allowed.iter().collect::<BTreeSet<_>>();
            if allowed.is_empty()
                || allowed.len() > 16
                || distinct.len() != allowed.len()
                || allowed.iter().any(|extension| {
                    extension.len() < 2
                        || extension.len() > 11
                        || !extension.starts_with('.')
                        || !extension[1..]
                            .bytes()
                            .all(|byte| byte.is_ascii_lowercase() || byte.is_ascii_digit())
                })
            {
                errors.push(format!("rule {} allowed extensions are invalid", rule.id));
            }
        }
        let Some(file) = bindings.get(&rule.file_role) else {
            errors.push(format!("rule {} references an unknown file role", rule.id));
            continue;
        };
        let content_rule = !matches!(
            rule.kind.as_str(),
            "required_file" | "file_extension_in" | "file_size_max_bytes"
        );
        if content_rule && !file.path.to_lowercase().ends_with(".md") {
            errors.push(format!("rule {} requires a Markdown file", rule.id));
            continue;
        }
        if let Some(raw) = files_raw.get(&rule.file_role) {
            results.push(evaluate_rule(rule, file, raw));
        }
    }
    if errors.is_empty() {
        Ok(LoadedSubmission {
            manifest,
            manifest_raw,
            guide_raw,
            files_raw,
            results,
        })
    } else {
        Err(errors)
    }
}

fn counts(results: &[RuleResult]) -> (usize, usize, usize, usize) {
    let passed = results
        .iter()
        .filter(|result| result.outcome == "pass")
        .count();
    let failed_required = results
        .iter()
        .filter(|result| result.outcome == "fail" && result.severity == "required")
        .count();
    let review_issues = results
        .iter()
        .filter(|result| result.outcome == "fail" && result.severity == "review")
        .count();
    let unresolved = results
        .iter()
        .filter(|result| result.outcome == "unresolved")
        .count();
    (passed, failed_required, review_issues, unresolved)
}

fn empty_audit(errors: Vec<String>) -> JournalSubmissionAudit {
    JournalSubmissionAudit {
        complete: false,
        ready_to_generate: false,
        outputs_current: false,
        status: if errors.is_empty() {
            "missing"
        } else {
            "invalid"
        },
        check_id: String::new(),
        title: String::new(),
        journal_name: String::new(),
        article_type: String::new(),
        guide_accessed_on: String::new(),
        manifest_path: JOURNAL_SUBMISSION_MANIFEST_PATH,
        markdown_path: JOURNAL_SUBMISSION_MARKDOWN_PATH,
        results_path: JOURNAL_SUBMISSION_RESULTS_PATH,
        audit_path: JOURNAL_SUBMISSION_AUDIT_PATH,
        manifest_sha256: String::new(),
        file_count: 0,
        rule_count: 0,
        passed_count: 0,
        failed_required_count: 0,
        review_issue_count: 0,
        unresolved_count: 0,
        human_review_status: "awaiting_human_review".into(),
        errors,
        warnings: Vec::new(),
    }
}

fn record_matches(workspace: &Path, loaded: &LoadedSubmission) -> Option<GenerationRecord> {
    let raw = std::fs::read(workspace.join(JOURNAL_SUBMISSION_AUDIT_PATH)).ok()?;
    let record: GenerationRecord = serde_json::from_slice(&raw).ok()?;
    let (_, failed_required, review_issues, unresolved) = counts(&loaded.results);
    let file_hashes = loaded
        .files_raw
        .iter()
        .map(|(role, raw)| (role.clone(), sha256(raw)))
        .collect::<BTreeMap<_, _>>();
    (record.schema_version == "0.1.0"
        && record.generator == "ai4heor-native-journal-submission-check"
        && record.generator_version == ENGINE_VERSION
        && record.check_id == loaded.manifest.check_id
        && record.manifest_path == JOURNAL_SUBMISSION_MANIFEST_PATH
        && record.manifest_sha256 == sha256(&loaded.manifest_raw)
        && record.guide_path == loaded.manifest.journal.source_path
        && record.guide_sha256 == sha256(&loaded.guide_raw)
        && record.file_hashes == file_hashes
        && record.markdown_path == JOURNAL_SUBMISSION_MARKDOWN_PATH
        && record.results_path == JOURNAL_SUBMISSION_RESULTS_PATH
        && record.rule_count == loaded.results.len()
        && record.failed_required_count == failed_required
        && record.review_issue_count == review_issues
        && record.unresolved_count == unresolved
        && record.human_review_status == "awaiting_human_review")
        .then_some(record)
}

fn apply_current_outputs(
    workspace: &Path,
    loaded: &LoadedSubmission,
    audit: &mut JournalSubmissionAudit,
) {
    let Some(record) = record_matches(workspace, loaded) else {
        return;
    };
    let Ok(markdown) = std::fs::read(workspace.join(JOURNAL_SUBMISSION_MARKDOWN_PATH)) else {
        return;
    };
    let Ok(results) = std::fs::read(workspace.join(JOURNAL_SUBMISSION_RESULTS_PATH)) else {
        return;
    };
    if sha256(&markdown) != record.markdown_sha256 || sha256(&results) != record.results_sha256 {
        return;
    }
    audit.outputs_current = true;
    audit.status = "current";
}

fn audit_at(workspace: &Path) -> (JournalSubmissionAudit, Option<LoadedSubmission>) {
    let manifest_raw = match std::fs::read(workspace.join(JOURNAL_SUBMISSION_MANIFEST_PATH)) {
        Ok(raw) if raw.len() as u64 <= MANIFEST_CAP_BYTES => raw,
        _ => {
            return (
                empty_audit(vec![format!(
                    "{JOURNAL_SUBMISSION_MANIFEST_PATH} is required"
                )]),
                None,
            )
        }
    };
    let untyped = match serde_json::from_slice::<serde_json::Value>(&manifest_raw) {
        Ok(value) => value,
        Err(error) => {
            return (
                empty_audit(vec![format!(
                    "journal submission manifest is invalid: {error}"
                )]),
                None,
            )
        }
    };
    let shape_errors = validate_rule_shapes(&untyped);
    if !shape_errors.is_empty() {
        return (empty_audit(shape_errors), None);
    }
    let manifest = match serde_json::from_value::<SubmissionManifest>(untyped) {
        Ok(value) => value,
        Err(error) => {
            return (
                empty_audit(vec![format!(
                    "journal submission manifest is invalid: {error}"
                )]),
                None,
            )
        }
    };
    let loaded = match validate_manifest(workspace, manifest, manifest_raw) {
        Ok(value) => value,
        Err(errors) => return (empty_audit(errors), None),
    };
    let (passed, failed_required, review_issues, unresolved) = counts(&loaded.results);
    let mut warnings = vec![
        "Mechanical checks do not establish journal compliance or permission to submit.".into(),
    ];
    if unresolved > 0 {
        warnings.push(format!("{unresolved} checks need researcher resolution"));
    }
    let mut audit = JournalSubmissionAudit {
        complete: true,
        ready_to_generate: true,
        outputs_current: false,
        status: "ready",
        check_id: loaded.manifest.check_id.clone(),
        title: loaded.manifest.title.clone(),
        journal_name: loaded.manifest.journal.name.clone(),
        article_type: loaded.manifest.journal.article_type.clone(),
        guide_accessed_on: loaded.manifest.journal.accessed_on.clone(),
        manifest_path: JOURNAL_SUBMISSION_MANIFEST_PATH,
        markdown_path: JOURNAL_SUBMISSION_MARKDOWN_PATH,
        results_path: JOURNAL_SUBMISSION_RESULTS_PATH,
        audit_path: JOURNAL_SUBMISSION_AUDIT_PATH,
        manifest_sha256: sha256(&loaded.manifest_raw),
        file_count: loaded.manifest.files.len(),
        rule_count: loaded.results.len(),
        passed_count: passed,
        failed_required_count: failed_required,
        review_issue_count: review_issues,
        unresolved_count: unresolved,
        human_review_status: loaded.manifest.human_review.status.clone(),
        errors: Vec::new(),
        warnings,
    };
    apply_current_outputs(workspace, &loaded, &mut audit);
    (audit, Some(loaded))
}

fn markdown_cell(value: &str) -> String {
    value.replace('|', "\\|").replace(['\n', '\r'], " ")
}

fn build_markdown(loaded: &LoadedSubmission) -> Vec<u8> {
    let (passed, failed_required, review_issues, unresolved) = counts(&loaded.results);
    let mut output = format!(
        "# {}\n\n- 目标期刊 / Target journal: {}\n- 文章类型 / Article type: {}\n- 作者指南 / Author guide: {}\n- 访问日期 / Accessed: {}\n- 版本标识 / Version label: {}\n- 指南快照 / Guide snapshot: `{}`\n- 指南 SHA-256 / Guide SHA-256: `{}`\n- 复核状态 / Review: `awaiting_human_review`\n\n## 核对概览 / Summary\n\n- 通过 / Passed: {passed}\n- 必须项未通过 / Failed required: {failed_required}\n- 待复核问题 / Review issues: {review_issues}\n- 无法确定 / Unresolved: {unresolved}\n\n## 逐项核对 / Checks\n\n| 结果 | 严重性 | 核对项 | 当前值 | 要求 | 指南定位 |\n| --- | --- | --- | --- | --- | --- |\n",
        loaded.manifest.title,
        loaded.manifest.journal.name,
        loaded.manifest.journal.article_type,
        loaded.manifest.journal.guide_url,
        loaded.manifest.journal.accessed_on,
        loaded.manifest.journal.version_label,
        loaded.manifest.journal.source_path,
        loaded.manifest.journal.source_sha256,
    );
    for result in &loaded.results {
        output.push_str(&format!(
            "| {} | {} | {} | {} | {} | {} |\n",
            markdown_cell(&result.outcome),
            markdown_cell(&result.severity),
            markdown_cell(&result.label),
            markdown_cell(&result.measured),
            markdown_cell(&result.expected),
            markdown_cell(&result.guide_locator),
        ));
        if !result.note.is_empty() {
            output.push_str(&format!(
                "\n> **{}:** {}\n\n",
                markdown_cell(&result.label),
                result.note
            ));
        }
    }
    output.push_str(
        "\n## 计数口径 / Counting method\n\n- 排除 Markdown front matter 和围栏代码；标题文字计入全文计数。 / Markdown front matter and fenced code are excluded; heading text remains included.\n- 拉丁字母和数字的连续序列计为一个 token；每个中日韩统一表意字符计为一个 token。 / Contiguous Latin letters or digits form one token; each CJK unified ideograph forms one token.\n- 表格和图片只按 Markdown 语法计数，不检查最终 DOCX/PDF 版式。 / Tables and figures are counted from Markdown syntax, not final DOCX or PDF layout.\n\n## 边界 / Limitations\n\n- 本报告不复制或认证目标期刊的作者指南。 / This report does not reproduce or certify the target journal author guide.\n- 机械通过不代表符合投稿要求、出版伦理或报告规范。 / A mechanical pass does not establish journal compliance, publication ethics or reporting completeness.\n- 题名、摘要、正文、声明和附件仍须研究者逐项核对。 / The researcher must still review the title, abstract, text, declarations and files.\n- 作者指南可能在访问日期后变化，投稿前必须回到期刊官网确认。 / The author guide may change after the access date and must be checked again before submission.\n- AI4HEOR 不替研究者决定投稿、署名、披露或对外发布。 / AI4HEOR does not decide submission, authorship, disclosure or external release.\n",
    );
    output.into_bytes()
}

fn build_results(loaded: &LoadedSubmission) -> Result<Vec<u8>, String> {
    let (passed, failed_required, review_issues, unresolved) = counts(&loaded.results);
    let package = ResultsPackage {
        schema_version: "ai4heor-journal-submission-results/v1",
        generator: "ai4heor-native-journal-submission-check",
        generator_version: ENGINE_VERSION,
        check_id: &loaded.manifest.check_id,
        title: &loaded.manifest.title,
        language: &loaded.manifest.language,
        prepared_on: &loaded.manifest.prepared_on,
        journal: ResultsJournal {
            name: &loaded.manifest.journal.name,
            article_type: &loaded.manifest.journal.article_type,
            guide_url: &loaded.manifest.journal.guide_url,
            accessed_on: &loaded.manifest.journal.accessed_on,
            version_label: &loaded.manifest.journal.version_label,
            source_path: &loaded.manifest.journal.source_path,
            source_sha256: &loaded.manifest.journal.source_sha256,
        },
        manifest_path: JOURNAL_SUBMISSION_MANIFEST_PATH,
        manifest_sha256: sha256(&loaded.manifest_raw),
        file_hashes: loaded
            .files_raw
            .iter()
            .map(|(role, raw)| (role.clone(), sha256(raw)))
            .collect(),
        summary: ResultsSummary {
            passed,
            failed_required,
            review_issues,
            unresolved,
        },
        results: &loaded.results,
        counting_method: [
            "Markdown front matter and fenced code are excluded; heading text remains included.",
            "Contiguous Latin letters or digits form one token; each CJK unified ideograph forms one token.",
            "Tables and figures are counted from Markdown syntax, not final DOCX or PDF layout.",
        ],
        limitations: [
            "The report does not reproduce or certify the target journal author guide.",
            "A mechanical pass does not establish journal compliance, reporting completeness or publication ethics.",
            "Authorship, disclosure, ethics, copyright and permission decisions remain Human responsibilities.",
            "The author guide may change after the recorded access date and must be checked again before submission.",
            "The result never grants submission or external-release authority.",
        ],
        human_review_status: "awaiting_human_review",
    };
    serde_json::to_vec_pretty(&package)
        .map_err(|error| format!("cannot serialize journal submission results: {error}"))
}

fn write_atomic(path: &Path, bytes: &[u8]) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("cannot create submission-check directory: {error}"))?;
    }
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("submission-check-output");
    let temporary = path.with_file_name(format!(".{file_name}.tmp"));
    {
        let mut file = std::fs::File::create(&temporary)
            .map_err(|error| format!("cannot stage submission-check output: {error}"))?;
        file.write_all(bytes)
            .and_then(|_| file.sync_all())
            .map_err(|error| format!("cannot flush submission-check output: {error}"))?;
    }
    if std::fs::rename(&temporary, path).is_err() {
        let result = std::fs::write(path, bytes)
            .map_err(|error| format!("cannot replace submission-check output: {error}"));
        let _ = std::fs::remove_file(&temporary);
        result?;
    }
    Ok(())
}

fn existing_outputs_replaceable(workspace: &Path) -> Result<(), String> {
    let outputs = [
        JOURNAL_SUBMISSION_MARKDOWN_PATH,
        JOURNAL_SUBMISSION_RESULTS_PATH,
    ];
    if outputs.iter().all(|path| !workspace.join(path).exists()) {
        return Ok(());
    }
    let raw = std::fs::read(workspace.join(JOURNAL_SUBMISSION_AUDIT_PATH)).map_err(|_| {
        "existing submission-check outputs have no matching app audit; move or rename them before generating".to_string()
    })?;
    let record: GenerationRecord = serde_json::from_slice(&raw).map_err(|_| {
        "existing submission-check outputs have an unreadable app audit; move or rename them before generating".to_string()
    })?;
    for (path, expected) in [
        (
            JOURNAL_SUBMISSION_MARKDOWN_PATH,
            record.markdown_sha256.as_str(),
        ),
        (
            JOURNAL_SUBMISSION_RESULTS_PATH,
            record.results_sha256.as_str(),
        ),
    ] {
        let bytes = std::fs::read(workspace.join(path))
            .map_err(|_| format!("existing submission-check output is incomplete: {path}"))?;
        if sha256(&bytes) != expected {
            return Err(format!(
                "{path} changed outside AI4HEOR; move or rename it before generating"
            ));
        }
    }
    Ok(())
}

fn generate_at(workspace: &Path) -> Result<JournalSubmissionAudit, String> {
    let (audit, loaded) = audit_at(workspace);
    let loaded = loaded.ok_or_else(|| audit.errors.join("; "))?;
    if audit.outputs_current {
        return Ok(audit);
    }
    existing_outputs_replaceable(workspace)?;
    let markdown = build_markdown(&loaded);
    let results = build_results(&loaded)?;
    let (_, failed_required, review_issues, unresolved) = counts(&loaded.results);
    let record = GenerationRecord {
        schema_version: "0.1.0".into(),
        generator: "ai4heor-native-journal-submission-check".into(),
        generator_version: ENGINE_VERSION.into(),
        check_id: loaded.manifest.check_id.clone(),
        manifest_path: JOURNAL_SUBMISSION_MANIFEST_PATH.into(),
        manifest_sha256: sha256(&loaded.manifest_raw),
        guide_path: loaded.manifest.journal.source_path.clone(),
        guide_sha256: sha256(&loaded.guide_raw),
        file_hashes: loaded
            .files_raw
            .iter()
            .map(|(role, raw)| (role.clone(), sha256(raw)))
            .collect(),
        markdown_path: JOURNAL_SUBMISSION_MARKDOWN_PATH.into(),
        markdown_sha256: sha256(&markdown),
        results_path: JOURNAL_SUBMISSION_RESULTS_PATH.into(),
        results_sha256: sha256(&results),
        rule_count: loaded.results.len(),
        failed_required_count: failed_required,
        review_issue_count: review_issues,
        unresolved_count: unresolved,
        human_review_status: "awaiting_human_review".into(),
    };
    write_atomic(&workspace.join(JOURNAL_SUBMISSION_MARKDOWN_PATH), &markdown)?;
    write_atomic(&workspace.join(JOURNAL_SUBMISSION_RESULTS_PATH), &results)?;
    let record_raw = serde_json::to_vec_pretty(&record)
        .map_err(|error| format!("cannot serialize submission-check audit: {error}"))?;
    write_atomic(&workspace.join(JOURNAL_SUBMISSION_AUDIT_PATH), &record_raw)?;
    Ok(audit_at(workspace).0)
}

#[tauri::command(async)]
pub fn audit_journal_submission(app: AppHandle) -> Result<JournalSubmissionAudit, String> {
    Ok(audit_at(&crate::runtime::workspace_dir(&app)?).0)
}

#[tauri::command(async)]
pub fn generate_journal_submission(app: AppHandle) -> Result<JournalSubmissionAudit, String> {
    generate_at(&crate::runtime::workspace_dir(&app)?)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture_root(name: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!(
            "ai4heor-journal-submission-{name}-{}-{}",
            std::process::id(),
            std::thread::current().name().unwrap_or("test")
        ));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("deliverables")).unwrap();
        std::fs::create_dir_all(root.join("references")).unwrap();
        std::fs::create_dir_all(root.join("heor")).unwrap();
        root
    }

    fn manifest(root: &Path) -> serde_json::Value {
        let guide = b"Target journal author guide snapshot";
        let manuscript = br#"---
draft: true
---
# A short title

## Abstract

This is a concise abstract.

## Methods

Economic evaluation methods.

| Item | Value |
| --- | --- |
| Cost | 10 |

![Result](figure.png)

## References

One reference.
"#;
        std::fs::write(root.join("references/guide.pdf"), guide).unwrap();
        std::fs::write(root.join("heor/report.md"), manuscript).unwrap();
        serde_json::json!({
            "schema_version": SCHEMA_VERSION,
            "check_id": "target-journal",
            "title": "Target journal check",
            "language": "en",
            "prepared_on": "2026-07-20",
            "journal": {
                "name": "Example Journal",
                "article_type": "Economic Evaluation",
                "guide_url": "https://journal.example.org/authors",
                "accessed_on": "2026-07-20",
                "version_label": "2026 author guide",
                "source_path": "references/guide.pdf",
                "source_sha256": sha256(guide)
            },
            "files": [{
                "role": "manuscript",
                "label": "Manuscript",
                "path": "heor/report.md",
                "sha256": sha256(manuscript)
            }],
            "rules": [
                {"id":"manuscript-required","label":"Manuscript file","kind":"required_file","severity":"required","guide_locator":"Files > Manuscript","note":"","file_role":"manuscript"},
                {"id":"title-max","label":"Title length","kind":"title_characters_max","severity":"required","guide_locator":"Title page","note":"","file_role":"manuscript","limit":40},
                {"id":"abstract-max","label":"Abstract words","kind":"section_words_max","severity":"review","guide_locator":"Abstract","note":"Journal count needs Human confirmation.","file_role":"manuscript","value":"Abstract","limit":3},
                {"id":"methods-heading","label":"Methods heading","kind":"required_heading","severity":"required","guide_locator":"Structure","note":"","file_role":"manuscript","value":"Methods"},
                {"id":"table-max","label":"Table count","kind":"table_count_max","severity":"required","guide_locator":"Tables","note":"","file_role":"manuscript","limit":1},
                {"id":"figure-max","label":"Figure count","kind":"figure_count_max","severity":"required","guide_locator":"Figures","note":"","file_role":"manuscript","limit":1}
            ],
            "human_review": {"status":"awaiting_human_review"}
        })
    }

    fn write_manifest(root: &Path, value: &serde_json::Value) {
        std::fs::write(
            root.join(JOURNAL_SUBMISSION_MANIFEST_PATH),
            serde_json::to_vec_pretty(value).unwrap(),
        )
        .unwrap();
    }

    #[test]
    fn source_bound_check_is_deterministic_and_never_approves_submission() {
        let root = fixture_root("deterministic");
        write_manifest(&root, &manifest(&root));
        let ready = audit_at(&root).0;
        assert!(ready.ready_to_generate);
        assert_eq!(ready.failed_required_count, 0);
        assert_eq!(ready.review_issue_count, 1);
        let generated = generate_at(&root).unwrap();
        assert!(generated.outputs_current);
        assert_eq!(
            generate_at(&root).unwrap().manifest_sha256,
            generated.manifest_sha256
        );
        let markdown =
            std::fs::read_to_string(root.join(JOURNAL_SUBMISSION_MARKDOWN_PATH)).unwrap();
        assert!(markdown.contains("待复核问题 / Review issues: 1"));
        assert!(markdown.contains("does not establish journal compliance"));
        let results: serde_json::Value = serde_json::from_slice(
            &std::fs::read(root.join(JOURNAL_SUBMISSION_RESULTS_PATH)).unwrap(),
        )
        .unwrap();
        assert_eq!(results["human_review_status"], "awaiting_human_review");
        assert!(results.get("approved").is_none());
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn stale_sources_symlinks_unknown_fields_and_approval_fail_closed() {
        let root = fixture_root("invalid");
        let mut value = manifest(&root);
        value["human_review"]["status"] = serde_json::json!("approved");
        value["journal"]["unexpected"] = serde_json::json!(true);
        value["files"][0]["sha256"] = serde_json::json!("0".repeat(64));
        write_manifest(&root, &value);
        let audit = audit_at(&root).0;
        assert!(!audit.ready_to_generate);
        assert!(audit.errors.iter().any(|error| error.contains("invalid")));

        #[cfg(unix)]
        {
            use std::os::unix::fs::symlink;
            let mut value = manifest(&root);
            std::fs::remove_file(root.join("heor/report.md")).unwrap();
            symlink(
                root.join("references/guide.pdf"),
                root.join("heor/report.md"),
            )
            .unwrap();
            value["files"][0]["sha256"] =
                serde_json::json!(sha256(b"Target journal author guide snapshot"));
            write_manifest(&root, &value);
            assert!(audit_at(&root)
                .0
                .errors
                .iter()
                .any(|error| error.contains("symlink")));
        }
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn missing_section_is_unresolved_and_required_failure_stays_visible() {
        let root = fixture_root("outcomes");
        let mut value = manifest(&root);
        value["rules"][1]["limit"] = serde_json::json!(3);
        value["rules"][2]["value"] = serde_json::json!("Structured Abstract");
        write_manifest(&root, &value);
        let audit = audit_at(&root).0;
        assert_eq!(audit.failed_required_count, 1);
        assert_eq!(audit.unresolved_count, 1);
        assert!(audit.ready_to_generate);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn externally_changed_outputs_are_never_overwritten() {
        let root = fixture_root("overwrite");
        let mut value = manifest(&root);
        write_manifest(&root, &value);
        generate_at(&root).unwrap();
        std::fs::write(root.join(JOURNAL_SUBMISSION_MARKDOWN_PATH), b"Human edit").unwrap();
        value["prepared_on"] = serde_json::json!("2026-07-21");
        write_manifest(&root, &value);
        let error = generate_at(&root).unwrap_err();
        assert!(error.contains("changed outside AI4HEOR"));
        assert_eq!(
            std::fs::read(root.join(JOURNAL_SUBMISSION_MARKDOWN_PATH)).unwrap(),
            b"Human edit"
        );
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn word_character_table_and_figure_counters_are_explicit() {
        assert_eq!(count_words("cost effect 成本效果"), 6);
        assert_eq!(count_characters(" A 成 本 "), 3);
        let (visible, headings) = visible_markdown("# T\n\n## A\n\nword 字\n\n## B\n\nother");
        assert_eq!(
            section_text(&visible, &headings, "A").as_deref(),
            Some("\nword 字\n")
        );
        assert_eq!(markdown_table_count(&["| --- | :---: |".into()]), 1);
        assert_eq!(
            markdown_figure_count(&["![a](a.png) ![b](b.png)".into()]),
            2
        );
    }
}
