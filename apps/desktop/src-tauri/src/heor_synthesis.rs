//! Deterministic audit and authorized-candidate import for HEOR evidence synthesis.
//!
//! The Agent owns research judgment in `heor/evidence-synthesis.json`; this
//! module owns only structural audit and a lossless import of app-authorized
//! search metadata. Import never changes screening, appraisal, or extraction
//! decisions and never treats retrieval as evidence inclusion.

use serde_json::{Map, Value};
use sha2::{Digest, Sha256};
use std::collections::{BTreeSet, HashMap, HashSet};
use std::io::Write;
use std::path::{Component, Path};
use std::sync::Mutex;
use tauri::AppHandle;

pub const EVIDENCE_SYNTHESIS_PATH: &str = "heor/evidence-synthesis.json";
const ARTIFACT_CAP_BYTES: u64 = 5 * 1024 * 1024;
const MAX_SEARCHES: usize = 1_000;
const MAX_RECORDS: usize = 50_000;
const MAX_EXTRACTIONS: usize = 50_000;
const MAX_CONFLICTS: usize = 10_000;

#[derive(Default)]
pub struct HeorSynthesisState(pub Mutex<()>);

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SynthesisAudit {
    pub complete: bool,
    pub importable: bool,
    pub status: &'static str,
    pub synthesis_id: String,
    pub synthesis_sha256: String,
    pub search_count: usize,
    pub record_count: usize,
    pub not_assessed_count: usize,
    pub included_count: usize,
    pub extraction_count: usize,
    pub eligible_extraction_ids: Vec<String>,
    pub app_verified_extraction_ids: Vec<String>,
    pub unverified_extraction_ids: Vec<String>,
    pub human_review_complete: bool,
    pub verification_integrity: &'static str,
    pub unresolved_conflicts: Vec<String>,
    pub errors: Vec<String>,
    pub import_blockers: Vec<String>,
}

#[derive(Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct ImportCandidatesRequest {
    project_id: String,
    output_path: String,
    output_sha256: String,
    synthesis_sha256: String,
}

#[derive(Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ImportCandidatesResponse {
    audit: SynthesisAudit,
    added_searches: usize,
    added_records: usize,
    reconciled_records: usize,
    source_run_path: String,
    source_run_sha256: String,
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

fn nonempty(value: Option<&Value>) -> bool {
    value
        .and_then(Value::as_str)
        .is_some_and(|value| !value.trim().is_empty() && !value.chars().any(char::is_control))
}

fn text_array(value: Option<&Value>, non_empty: bool) -> Option<Vec<&str>> {
    let values = value?.as_array()?;
    if non_empty && values.is_empty() {
        return None;
    }
    let mut output = Vec::with_capacity(values.len());
    for value in values {
        let text = value.as_str()?;
        if text.trim().is_empty() || text.chars().any(char::is_control) {
            return None;
        }
        output.push(text);
    }
    Some(output)
}

fn unknown_fields(object: &Map<String, Value>, allowed: &[&str], label: &str) -> Vec<String> {
    let allowed = allowed.iter().copied().collect::<HashSet<_>>();
    object
        .keys()
        .filter(|key| !allowed.contains(key.as_str()))
        .map(|key| format!("{label} contains unsupported field: {key}"))
        .collect()
}

fn valid_date(value: Option<&Value>) -> bool {
    let Some(value) = value.and_then(Value::as_str) else {
        return false;
    };
    if value.len() != 10 || &value[4..5] != "-" || &value[7..8] != "-" {
        return false;
    }
    let (Ok(year), Ok(month), Ok(day)) = (
        value[0..4].parse::<u32>(),
        value[5..7].parse::<u32>(),
        value[8..10].parse::<u32>(),
    ) else {
        return false;
    };
    let leap = year.is_multiple_of(4) && (!year.is_multiple_of(100) || year.is_multiple_of(400));
    let max_day = match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 if leap => 29,
        2 => 28,
        _ => return false,
    };
    (1900..=3000).contains(&year) && day > 0 && day <= max_day
}

fn audit_value(
    value: &Value,
    synthesis_sha256: String,
    allow_empty_searches: bool,
) -> SynthesisAudit {
    let mut audit = SynthesisAudit {
        complete: false,
        importable: false,
        status: "incomplete",
        synthesis_id: String::new(),
        synthesis_sha256,
        search_count: 0,
        record_count: 0,
        not_assessed_count: 0,
        included_count: 0,
        extraction_count: 0,
        eligible_extraction_ids: Vec::new(),
        app_verified_extraction_ids: Vec::new(),
        unverified_extraction_ids: Vec::new(),
        human_review_complete: false,
        verification_integrity: "not_checked",
        unresolved_conflicts: Vec::new(),
        errors: Vec::new(),
        import_blockers: Vec::new(),
    };
    let Some(root) = value.as_object() else {
        audit.errors.push("artifact must be a JSON object".into());
        audit.import_blockers = audit.errors.clone();
        return audit;
    };
    audit.errors.extend(unknown_fields(
        root,
        &[
            "schema_version",
            "synthesis_id",
            "status",
            "research_question",
            "eligibility",
            "searches",
            "deduplication",
            "records",
            "extractions",
            "conflicts",
            "limitations",
        ],
        "artifact",
    ));
    if root.get("schema_version").and_then(Value::as_str) != Some("0.1.0") {
        audit.errors.push("schema_version must be 0.1.0".into());
    }
    audit.synthesis_id = root
        .get("synthesis_id")
        .and_then(Value::as_str)
        .unwrap_or_default()
        .to_string();
    if !nonempty(root.get("synthesis_id")) {
        audit.errors.push("synthesis_id is required".into());
    }
    if !matches!(
        root.get("status").and_then(Value::as_str),
        Some("draft" | "ready_for_human_review")
    ) {
        audit.errors.push("status is invalid".into());
    }

    match root.get("research_question").and_then(Value::as_object) {
        Some(question) => {
            audit.errors.extend(unknown_fields(
                question,
                &[
                    "population",
                    "intervention",
                    "comparator",
                    "outcomes",
                    "study_designs",
                ],
                "research_question",
            ));
            for field in ["population", "intervention", "comparator"] {
                if !nonempty(question.get(field)) {
                    audit
                        .errors
                        .push(format!("research_question.{field} is required"));
                }
            }
            for field in ["outcomes", "study_designs"] {
                if text_array(question.get(field), true).is_none() {
                    audit.errors.push(format!(
                        "research_question.{field} must be a non-empty string array"
                    ));
                }
            }
        }
        None => audit.errors.push("research_question is required".into()),
    }
    match root.get("eligibility").and_then(Value::as_object) {
        Some(eligibility) => {
            audit.errors.extend(unknown_fields(
                eligibility,
                &["inclusion", "exclusion"],
                "eligibility",
            ));
            for field in ["inclusion", "exclusion"] {
                if text_array(eligibility.get(field), true).is_none() {
                    audit.errors.push(format!(
                        "eligibility.{field} must be a non-empty string array"
                    ));
                }
            }
        }
        None => audit.errors.push("eligibility is required".into()),
    }

    let searches = root.get("searches").and_then(Value::as_array);
    let mut search_ids = HashSet::new();
    match searches {
        Some(searches) if searches.len() <= MAX_SEARCHES => {
            audit.search_count = searches.len();
            if searches.is_empty() && !allow_empty_searches {
                audit
                    .errors
                    .push("at least one documented search is required".into());
            }
            for (index, search) in searches.iter().enumerate() {
                let label = format!("searches[{index}]");
                let Some(search) = search.as_object() else {
                    audit.errors.push(format!("{label} must be an object"));
                    continue;
                };
                audit.errors.extend(unknown_fields(
                    search,
                    &[
                        "id",
                        "source",
                        "query",
                        "searched_on",
                        "result_count",
                        "access",
                        "authorization_event_id",
                        "request_sha256",
                        "run_path",
                        "run_sha256",
                        "endpoint",
                        "response_sha256",
                    ],
                    &label,
                ));
                let id = search.get("id").and_then(Value::as_str).unwrap_or_default();
                if id.trim().is_empty() || !search_ids.insert(id) {
                    audit
                        .errors
                        .push(format!("{label}.id must be non-empty and unique"));
                }
                for field in ["source", "query"] {
                    if !nonempty(search.get(field)) {
                        audit.errors.push(format!("{label}.{field} is required"));
                    }
                }
                if !valid_date(search.get("searched_on")) {
                    audit.errors.push(format!(
                        "{label}.searched_on must be a valid YYYY-MM-DD date"
                    ));
                }
                if !search
                    .get("result_count")
                    .and_then(Value::as_u64)
                    .is_some_and(|count| count <= u32::MAX as u64)
                {
                    audit
                        .errors
                        .push(format!("{label}.result_count is invalid"));
                }
                if !matches!(
                    search.get("access").and_then(Value::as_str),
                    Some("network" | "local")
                ) {
                    audit.errors.push(format!("{label}.access is invalid"));
                }
                let binding_fields = [
                    "authorization_event_id",
                    "request_sha256",
                    "run_path",
                    "run_sha256",
                    "endpoint",
                    "response_sha256",
                ];
                let present = binding_fields
                    .iter()
                    .filter(|field| search.contains_key(**field))
                    .count();
                if present != 0 && present != binding_fields.len() {
                    audit
                        .errors
                        .push(format!("{label} has an incomplete app-search binding"));
                } else if present == binding_fields.len()
                    && (!search
                        .get("authorization_event_id")
                        .and_then(Value::as_str)
                        .is_some_and(|value| {
                            value.len() == 32
                                && value.bytes().all(|byte| {
                                    byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte)
                                })
                        })
                        || !search
                            .get("request_sha256")
                            .and_then(Value::as_str)
                            .is_some_and(is_sha256)
                        || !search
                            .get("run_path")
                            .and_then(Value::as_str)
                            .is_some_and(safe_relative_run_path)
                        || !search
                            .get("run_sha256")
                            .and_then(Value::as_str)
                            .is_some_and(is_sha256)
                        || !matches!(
                            (
                                search.get("source").and_then(Value::as_str),
                                search.get("endpoint").and_then(Value::as_str)
                            ),
                            (
                                Some("pubmed"),
                                Some("https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi")
                            ) | (
                                Some("clinicaltrials"),
                                Some("https://clinicaltrials.gov/api/v2/studies")
                            )
                        )
                        || text_array(search.get("response_sha256"), true)
                            .is_none_or(|values| values.iter().any(|value| !is_sha256(value))))
                {
                    audit
                        .errors
                        .push(format!("{label} has an invalid app-search binding"));
                }
            }
        }
        Some(_) => audit
            .errors
            .push(format!("searches exceeds the cap of {MAX_SEARCHES}")),
        None => audit.errors.push("searches must be an array".into()),
    }

    match root.get("deduplication").and_then(Value::as_object) {
        Some(deduplication) => {
            audit.errors.extend(unknown_fields(
                deduplication,
                &["method", "duplicate_records_removed"],
                "deduplication",
            ));
            if !nonempty(deduplication.get("method")) {
                audit.errors.push("deduplication.method is required".into());
            }
            if deduplication
                .get("duplicate_records_removed")
                .and_then(Value::as_u64)
                .is_none()
            {
                audit
                    .errors
                    .push("deduplication.duplicate_records_removed is invalid".into());
            }
        }
        None => audit.errors.push("deduplication is required".into()),
    }

    let records = root.get("records").and_then(Value::as_array);
    let mut record_ids = HashSet::new();
    let mut included = HashSet::new();
    let mut unclear_count = 0usize;
    match records {
        Some(records) if records.len() <= MAX_RECORDS => {
            audit.record_count = records.len();
            for (index, record) in records.iter().enumerate() {
                let label = format!("records[{index}]");
                let Some(record) = record.as_object() else {
                    audit.errors.push(format!("{label} must be an object"));
                    continue;
                };
                audit.errors.extend(unknown_fields(
                    record,
                    &[
                        "record_id",
                        "title",
                        "locator",
                        "source_type",
                        "search_ids",
                        "screening",
                        "critical_appraisal",
                        "published_on",
                        "authors",
                        "doi",
                        "retrieval_metadata",
                    ],
                    &label,
                ));
                let id = record
                    .get("record_id")
                    .and_then(Value::as_str)
                    .unwrap_or_default();
                if id.trim().is_empty() || !record_ids.insert(id) {
                    audit
                        .errors
                        .push(format!("{label}.record_id must be non-empty and unique"));
                }
                for field in ["title", "locator", "source_type"] {
                    if !nonempty(record.get(field)) {
                        audit.errors.push(format!("{label}.{field} is required"));
                    }
                }
                if record.contains_key("published_on") && !valid_date(record.get("published_on")) {
                    audit.errors.push(format!(
                        "{label}.published_on must be a valid YYYY-MM-DD date"
                    ));
                }
                if record.contains_key("authors")
                    && text_array(record.get("authors"), false).is_none()
                {
                    audit
                        .errors
                        .push(format!("{label}.authors must be a string array"));
                }
                if record.contains_key("doi") && !nonempty(record.get("doi")) {
                    audit.errors.push(format!("{label}.doi is invalid"));
                }
                if record.contains_key("retrieval_metadata")
                    && !record
                        .get("retrieval_metadata")
                        .is_some_and(Value::is_object)
                {
                    audit
                        .errors
                        .push(format!("{label}.retrieval_metadata must be an object"));
                }
                if text_array(record.get("search_ids"), true)
                    .is_none_or(|values| values.iter().any(|id| !search_ids.contains(id)))
                {
                    audit.errors.push(format!(
                        "{label}.search_ids must reference documented searches"
                    ));
                }
                let Some(screening) = record.get("screening").and_then(Value::as_object) else {
                    audit.errors.push(format!("{label}.screening is required"));
                    continue;
                };
                audit.errors.extend(unknown_fields(
                    screening,
                    &["title_abstract", "full_text", "full_text_reason"],
                    &format!("{label}.screening"),
                ));
                let title = screening.get("title_abstract").and_then(Value::as_str);
                let full = screening.get("full_text").and_then(Value::as_str);
                let valid_decision = |decision| {
                    matches!(
                        decision,
                        Some("include" | "exclude" | "unclear" | "not_assessed")
                    )
                };
                if !valid_decision(title) || !valid_decision(full) {
                    audit
                        .errors
                        .push(format!("{label}.screening decisions are invalid"));
                }
                if title == Some("not_assessed") || full == Some("not_assessed") {
                    audit.not_assessed_count += 1;
                }
                if title == Some("unclear") || full == Some("unclear") {
                    unclear_count += 1;
                }
                if full == Some("exclude") && !nonempty(screening.get("full_text_reason")) {
                    audit
                        .errors
                        .push(format!("{label}.screening.full_text_reason is required"));
                }
                if full == Some("include") {
                    included.insert(id);
                    let Some(appraisal) =
                        record.get("critical_appraisal").and_then(Value::as_object)
                    else {
                        audit
                            .errors
                            .push(format!("{label}.critical_appraisal is required"));
                        continue;
                    };
                    audit.errors.extend(unknown_fields(
                        appraisal,
                        &["status", "tool", "findings", "rationale", "checked_by"],
                        &format!("{label}.critical_appraisal"),
                    ));
                    let status = appraisal.get("status").and_then(Value::as_str);
                    if !matches!(
                        status,
                        Some("agent_draft" | "human_checked" | "not_applicable")
                    ) {
                        audit
                            .errors
                            .push(format!("{label}.critical_appraisal.status is invalid"));
                    }
                    if !nonempty(appraisal.get("tool"))
                        || !nonempty(appraisal.get("rationale"))
                        || text_array(appraisal.get("findings"), true).is_none()
                    {
                        audit
                            .errors
                            .push(format!("{label}.critical_appraisal is incomplete"));
                    }
                    if status == Some("human_checked") && !nonempty(appraisal.get("checked_by")) {
                        audit
                            .errors
                            .push(format!("{label}.critical_appraisal.checked_by is required"));
                    }
                }
            }
        }
        Some(_) => audit
            .errors
            .push(format!("records exceeds the cap of {MAX_RECORDS}")),
        None => audit.errors.push("records must be an array".into()),
    }
    audit.included_count = included.len();

    let mut extracted_records = HashSet::new();
    match root.get("extractions").and_then(Value::as_array) {
        Some(extractions) if extractions.len() <= MAX_EXTRACTIONS => {
            audit.extraction_count = extractions.len();
            let mut ids = HashSet::new();
            for (index, extraction) in extractions.iter().enumerate() {
                let label = format!("extractions[{index}]");
                let Some(extraction) = extraction.as_object() else {
                    audit.errors.push(format!("{label} must be an object"));
                    continue;
                };
                audit.errors.extend(unknown_fields(
                    extraction,
                    &[
                        "extraction_id",
                        "record_id",
                        "target",
                        "extracted_value",
                        "source_location",
                        "applicability",
                        "verification_status",
                        "verified_by",
                    ],
                    &label,
                ));
                let id = extraction
                    .get("extraction_id")
                    .and_then(Value::as_str)
                    .unwrap_or_default();
                if id.trim().is_empty() || !ids.insert(id) {
                    audit.errors.push(format!(
                        "{label}.extraction_id must be non-empty and unique"
                    ));
                }
                let record_id = extraction
                    .get("record_id")
                    .and_then(Value::as_str)
                    .unwrap_or_default();
                if !included.contains(record_id) {
                    audit.errors.push(format!(
                        "{label}.record_id must reference an included record"
                    ));
                } else {
                    extracted_records.insert(record_id);
                }
                for field in [
                    "target",
                    "extracted_value",
                    "source_location",
                    "applicability",
                ] {
                    if !nonempty(extraction.get(field)) {
                        audit.errors.push(format!("{label}.{field} is required"));
                    }
                }
                let status = extraction
                    .get("verification_status")
                    .and_then(Value::as_str);
                if !matches!(
                    status,
                    Some("agent_extracted" | "human_checked" | "conflict")
                ) {
                    audit
                        .errors
                        .push(format!("{label}.verification_status is invalid"));
                }
                if status == Some("human_checked") && !nonempty(extraction.get("verified_by")) {
                    audit
                        .errors
                        .push(format!("{label}.verified_by is required"));
                }
                if !id.trim().is_empty() && status != Some("conflict") {
                    audit.eligible_extraction_ids.push(id.to_string());
                }
            }
        }
        Some(_) => audit
            .errors
            .push(format!("extractions exceeds the cap of {MAX_EXTRACTIONS}")),
        None => audit.errors.push("extractions must be an array".into()),
    }
    let missing = included
        .difference(&extracted_records)
        .copied()
        .collect::<Vec<_>>();
    if !missing.is_empty() {
        audit.errors.push(format!(
            "included records without extraction: {}",
            missing.join(", ")
        ));
    }

    match root.get("conflicts").and_then(Value::as_array) {
        Some(conflicts) if conflicts.len() <= MAX_CONFLICTS => {
            let mut ids = HashSet::new();
            for (index, conflict) in conflicts.iter().enumerate() {
                let label = format!("conflicts[{index}]");
                let Some(conflict) = conflict.as_object() else {
                    audit.errors.push(format!("{label} must be an object"));
                    continue;
                };
                audit.errors.extend(unknown_fields(
                    conflict,
                    &["id", "topic", "record_ids", "status", "rationale"],
                    &label,
                ));
                let id = conflict
                    .get("id")
                    .and_then(Value::as_str)
                    .unwrap_or_default();
                if id.trim().is_empty() || !ids.insert(id) {
                    audit
                        .errors
                        .push(format!("{label}.id must be non-empty and unique"));
                }
                if !nonempty(conflict.get("topic")) || !nonempty(conflict.get("rationale")) {
                    audit
                        .errors
                        .push(format!("{label} requires topic and rationale"));
                }
                if text_array(conflict.get("record_ids"), true).is_none_or(|values| {
                    values.len() < 2 || values.iter().any(|id| !record_ids.contains(id))
                }) {
                    audit.errors.push(format!(
                        "{label}.record_ids must reference at least two records"
                    ));
                }
                let status = conflict.get("status").and_then(Value::as_str);
                if !matches!(
                    status,
                    Some("unresolved" | "proposed" | "resolved_by_human")
                ) {
                    audit.errors.push(format!("{label}.status is invalid"));
                } else if status == Some("unresolved") {
                    audit.unresolved_conflicts.push(id.to_string());
                }
            }
        }
        Some(_) => audit
            .errors
            .push(format!("conflicts exceeds the cap of {MAX_CONFLICTS}")),
        None => audit.errors.push("conflicts must be an array".into()),
    }
    if text_array(root.get("limitations"), true).is_none() {
        audit
            .errors
            .push("limitations must be a non-empty string array".into());
    }

    audit.import_blockers = if allow_empty_searches {
        audit.errors.clone()
    } else {
        let import_audit = audit_value(value, audit.synthesis_sha256.clone(), true);
        import_audit.import_blockers
    };
    audit.importable = audit.import_blockers.is_empty();
    if audit.not_assessed_count > 0 {
        audit.errors.push(format!(
            "{} records remain not_assessed",
            audit.not_assessed_count
        ));
    }
    if unclear_count > 0 {
        audit.errors.push(format!(
            "{unclear_count} records have unclear screening decisions"
        ));
    }
    if !audit.unresolved_conflicts.is_empty() {
        audit.errors.push(format!(
            "unresolved conflicts: {}",
            audit.unresolved_conflicts.join(", ")
        ));
    }
    audit.complete = audit.errors.is_empty();
    audit.eligible_extraction_ids.sort();
    audit.eligible_extraction_ids.dedup();
    audit.unverified_extraction_ids = audit.eligible_extraction_ids.clone();
    audit.status = if audit.complete {
        "complete"
    } else {
        "incomplete"
    };
    audit
}

pub(crate) fn audit_bytes(raw: &[u8]) -> SynthesisAudit {
    let digest = sha256(raw);
    match serde_json::from_slice::<Value>(raw) {
        Ok(value) => audit_value(&value, digest, false),
        Err(error) => SynthesisAudit {
            complete: false,
            importable: false,
            status: "incomplete",
            synthesis_id: String::new(),
            synthesis_sha256: digest,
            search_count: 0,
            record_count: 0,
            not_assessed_count: 0,
            included_count: 0,
            extraction_count: 0,
            eligible_extraction_ids: Vec::new(),
            app_verified_extraction_ids: Vec::new(),
            unverified_extraction_ids: Vec::new(),
            human_review_complete: false,
            verification_integrity: "not_checked",
            unresolved_conflicts: Vec::new(),
            errors: vec![format!("evidence synthesis is invalid JSON: {error}")],
            import_blockers: vec![format!("evidence synthesis is invalid JSON: {error}")],
        },
    }
}

pub(crate) fn enrich_with_verification(
    app: &AppHandle,
    project_id: &str,
    mut audit: SynthesisAudit,
) -> Result<SynthesisAudit, String> {
    let log = crate::heor_evidence_review::verified_log(app, project_id)?;
    let verified =
        crate::heor_evidence_review::verified_extraction_ids(&log, &audit.synthesis_sha256);
    let eligible = audit
        .eligible_extraction_ids
        .iter()
        .cloned()
        .collect::<BTreeSet<_>>();
    audit.app_verified_extraction_ids = eligible.intersection(&verified).cloned().collect();
    audit.unverified_extraction_ids = eligible.difference(&verified).cloned().collect();
    audit.human_review_complete =
        audit.complete && !eligible.is_empty() && audit.unverified_extraction_ids.is_empty();
    audit.verification_integrity = log.integrity;
    Ok(audit)
}

pub(crate) fn audit_current_with_verification(
    app: &AppHandle,
    workspace: &Path,
) -> Result<SynthesisAudit, String> {
    let project_id = crate::project::require_project_id(workspace)?;
    let raw = crate::heor_uncertainty::read_workspace_capped(workspace, EVIDENCE_SYNTHESIS_PATH)?;
    enrich_with_verification(app, &project_id, audit_bytes(&raw))
}

#[derive(Clone, Debug)]
pub(crate) struct ExtractionLink {
    pub record_id: String,
    pub target: String,
}

pub(crate) fn extraction_index(raw: &[u8]) -> Result<HashMap<String, ExtractionLink>, String> {
    let audit = audit_bytes(raw);
    if !audit.complete {
        return Err(format!(
            "evidence synthesis is structurally incomplete: {}",
            audit.errors.join("; ")
        ));
    }
    let value: Value = serde_json::from_slice(raw)
        .map_err(|error| format!("evidence synthesis is invalid JSON: {error}"))?;
    let mut output = HashMap::new();
    for extraction in value
        .get("extractions")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
    {
        if extraction
            .get("verification_status")
            .and_then(Value::as_str)
            == Some("conflict")
        {
            continue;
        }
        let id = extraction
            .get("extraction_id")
            .and_then(Value::as_str)
            .ok_or("evidence extraction omitted extraction_id")?;
        let record_id = extraction
            .get("record_id")
            .and_then(Value::as_str)
            .ok_or("evidence extraction omitted record_id")?;
        let target = extraction
            .get("target")
            .and_then(Value::as_str)
            .ok_or("evidence extraction omitted target")?;
        output.insert(
            id.to_string(),
            ExtractionLink {
                record_id: record_id.to_string(),
                target: target.to_string(),
            },
        );
    }
    Ok(output)
}

fn safe_relative_run_path(value: &str) -> bool {
    !Path::new(value).is_absolute()
        && value.starts_with("heor/evidence-search-runs/")
        && Path::new(value)
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
}

fn write_synthesis(workspace: &Path, raw: &[u8]) -> Result<(), String> {
    if raw.len() as u64 > ARTIFACT_CAP_BYTES {
        return Err("evidence synthesis exceeds the artifact cap".into());
    }
    let root = workspace
        .canonicalize()
        .map_err(|error| format!("workspace unavailable: {error}"))?;
    let target = root.join(EVIDENCE_SYNTHESIS_PATH);
    let metadata = std::fs::symlink_metadata(&target)
        .map_err(|error| format!("evidence synthesis unavailable: {error}"))?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err("evidence synthesis must be a regular non-symlink file".into());
    }
    let canonical = target
        .canonicalize()
        .map_err(|error| format!("evidence synthesis unavailable: {error}"))?;
    if !canonical.starts_with(&root) {
        return Err("evidence synthesis escaped the workspace".into());
    }
    let parent = canonical
        .parent()
        .ok_or("evidence synthesis has no parent")?;
    let stage = parent.join(format!(
        ".evidence-synthesis-{}.tmp",
        crate::runtime::random_hex(8)
    ));
    let backup = parent.join(format!(
        ".evidence-synthesis-{}.bak",
        crate::runtime::random_hex(8)
    ));
    let mut file = std::fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(&stage)
        .map_err(|error| format!("evidence synthesis staging failed: {error}"))?;
    file.write_all(raw)
        .and_then(|_| file.sync_all())
        .map_err(|error| format!("evidence synthesis staging failed: {error}"))?;
    std::fs::rename(&canonical, &backup)
        .map_err(|error| format!("evidence synthesis backup failed: {error}"))?;
    if let Err(error) = std::fs::rename(&stage, &canonical) {
        let _ = std::fs::rename(&backup, &canonical);
        let _ = std::fs::remove_file(&stage);
        return Err(format!("evidence synthesis commit failed: {error}"));
    }
    let _ = std::fs::remove_file(backup);
    Ok(())
}

fn import_candidates(
    synthesis_raw: &[u8],
    run: &crate::heor_search::EvidenceSearchResult,
    output_sha256: &str,
) -> Result<(Vec<u8>, usize, usize, usize), String> {
    let mut synthesis: Value = serde_json::from_slice(synthesis_raw)
        .map_err(|error| format!("evidence synthesis is invalid JSON: {error}"))?;
    let import_audit = audit_value(&synthesis, sha256(synthesis_raw), false);
    if !import_audit.importable {
        return Err(format!(
            "evidence synthesis is not importable: {}",
            import_audit.import_blockers.join("; ")
        ));
    }
    let root = synthesis
        .as_object_mut()
        .ok_or("evidence synthesis must be an object")?;
    root.insert("status".into(), Value::String("draft".into()));
    let mut searches = root
        .remove("searches")
        .and_then(|value| value.as_array().cloned())
        .ok_or("evidence synthesis searches must be an array")?;
    let mut existing_searches = searches
        .iter()
        .filter_map(|search| search.get("id").and_then(Value::as_str).map(str::to_string))
        .collect::<HashSet<_>>();
    let mut records = root
        .remove("records")
        .and_then(|value| value.as_array().cloned())
        .ok_or("evidence synthesis records must be an array")?;
    let mut record_index = records
        .iter()
        .enumerate()
        .filter_map(|(index, record)| {
            record
                .get("record_id")
                .and_then(Value::as_str)
                .map(|id| (id.to_string(), index))
        })
        .collect::<HashMap<_, _>>();

    let mut added_searches = 0usize;
    let mut added_records = 0usize;
    let mut reconciled = HashSet::new();
    for source_run in &run.source_runs {
        let search_id = format!("app-{}-{}", run.authorization_event_id, source_run.source);
        if existing_searches.contains(&search_id) {
            continue;
        }
        searches.push(serde_json::json!({
            "id": search_id,
            "source": source_run.source,
            "query": run.query,
            "searched_on": run.executed_on,
            "result_count": source_run.total_count,
            "access": "network",
            "authorization_event_id": run.authorization_event_id,
            "request_sha256": run.request_sha256,
            "run_path": run.output_path,
            "run_sha256": output_sha256,
            "endpoint": source_run.endpoint,
            "response_sha256": source_run.response_sha256,
        }));
        existing_searches.insert(search_id.clone());
        added_searches += 1;
        for candidate in &source_run.records {
            if let Some(index) = record_index.get(&candidate.record_id).copied() {
                let search_ids = records[index]
                    .get_mut("search_ids")
                    .and_then(Value::as_array_mut)
                    .ok_or("existing evidence record has invalid search_ids")?;
                if !search_ids
                    .iter()
                    .any(|value| value.as_str() == Some(&search_id))
                {
                    search_ids.push(Value::String(search_id.clone()));
                    reconciled.insert(candidate.record_id.clone());
                }
                continue;
            }
            let mut record = serde_json::json!({
                "record_id": candidate.record_id,
                "title": candidate.title,
                "locator": candidate.locator,
                "source_type": candidate.source_type,
                "search_ids": [search_id],
                "screening": {
                    "title_abstract": "not_assessed",
                    "full_text": "not_assessed"
                },
                "retrieval_metadata": {
                    "source": source_run.source,
                    "run_path": run.output_path,
                    "run_sha256": output_sha256,
                    "response_sha256": source_run.response_sha256,
                    "metadata": candidate.metadata
                }
            });
            if let Some(value) = &candidate.published_on {
                record["published_on"] = Value::String(value.clone());
            }
            if !candidate.authors.is_empty() {
                record["authors"] = serde_json::json!(candidate.authors);
            }
            if let Some(value) = &candidate.doi {
                record["doi"] = Value::String(value.clone());
            }
            records.push(record);
            record_index.insert(candidate.record_id.clone(), records.len() - 1);
            added_records += 1;
        }
    }
    root.insert("searches".into(), Value::Array(searches));
    root.insert("records".into(), Value::Array(records));
    if !reconciled.is_empty() {
        let deduplication = root
            .get_mut("deduplication")
            .and_then(Value::as_object_mut)
            .ok_or("deduplication must be an object")?;
        let current = deduplication
            .get("duplicate_records_removed")
            .and_then(Value::as_u64)
            .ok_or("duplicate_records_removed must be a non-negative integer")?;
        deduplication.insert(
            "duplicate_records_removed".into(),
            Value::from(current.saturating_add(reconciled.len() as u64)),
        );
    }
    let mut raw = serde_json::to_vec_pretty(&synthesis).map_err(|error| error.to_string())?;
    raw.push(b'\n');
    let final_audit = audit_bytes(&raw);
    if !final_audit.importable {
        return Err(format!(
            "candidate import produced an invalid evidence synthesis: {}",
            final_audit.import_blockers.join("; ")
        ));
    }
    Ok((raw, added_searches, added_records, reconciled.len()))
}

#[tauri::command]
pub fn audit_heor_evidence_synthesis(app: AppHandle) -> Result<SynthesisAudit, String> {
    let workspace = crate::runtime::workspace_dir(&app)?;
    match crate::heor_uncertainty::read_workspace_capped(&workspace, EVIDENCE_SYNTHESIS_PATH) {
        Ok(raw) => {
            let project_id = crate::project::require_project_id(&workspace)?;
            enrich_with_verification(&app, &project_id, audit_bytes(&raw))
        }
        Err(error) => Ok(SynthesisAudit {
            complete: false,
            importable: false,
            status: "incomplete",
            synthesis_id: String::new(),
            synthesis_sha256: String::new(),
            search_count: 0,
            record_count: 0,
            not_assessed_count: 0,
            included_count: 0,
            extraction_count: 0,
            eligible_extraction_ids: Vec::new(),
            app_verified_extraction_ids: Vec::new(),
            unverified_extraction_ids: Vec::new(),
            human_review_complete: false,
            verification_integrity: "not_checked",
            unresolved_conflicts: Vec::new(),
            errors: vec![error.clone()],
            import_blockers: vec![error],
        }),
    }
}

#[tauri::command]
pub fn import_heor_search_candidates(
    app: AppHandle,
    state: tauri::State<HeorSynthesisState>,
    request: ImportCandidatesRequest,
) -> Result<ImportCandidatesResponse, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "HEOR evidence-synthesis lock poisoned")?;
    if request.project_id.trim().is_empty()
        || !safe_relative_run_path(&request.output_path)
        || !is_sha256(&request.output_sha256)
        || !is_sha256(&request.synthesis_sha256)
    {
        return Err("candidate import request is invalid".into());
    }
    let workspace = crate::runtime::workspace_dir(&app)?;
    if crate::project::require_project_id(&workspace)? != request.project_id {
        return Err("candidate import projectId does not match the current project".into());
    }
    let synthesis_raw =
        crate::heor_uncertainty::read_workspace_capped(&workspace, EVIDENCE_SYNTHESIS_PATH)?;
    if synthesis_raw.len() as u64 > ARTIFACT_CAP_BYTES
        || sha256(&synthesis_raw) != request.synthesis_sha256
    {
        return Err("candidate import must bind the exact current evidence synthesis bytes".into());
    }
    let run = crate::heor_search::verified_search_result(
        &app,
        &request.project_id,
        &request.output_path,
        &request.output_sha256,
    )?;
    let (raw, added_searches, added_records, reconciled_records) =
        import_candidates(&synthesis_raw, &run, &request.output_sha256)?;
    write_synthesis(&workspace, &raw)?;
    crate::git_snapshot::commit_best_effort(&workspace, "Import authorized evidence candidates");
    Ok(ImportCandidatesResponse {
        audit: enrich_with_verification(&app, &request.project_id, audit_bytes(&raw))?,
        added_searches,
        added_records,
        reconciled_records,
        source_run_path: request.output_path,
        source_run_sha256: request.output_sha256,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn skeleton() -> Value {
        serde_json::json!({
            "schema_version": "0.1.0",
            "synthesis_id": "t2d-evidence",
            "status": "draft",
            "research_question": {
                "population": "Adults with type 2 diabetes",
                "intervention": "Semaglutide",
                "comparator": "Standard care",
                "outcomes": ["HbA1c", "cost", "quality of life"],
                "study_designs": ["randomized trial", "economic evaluation"]
            },
            "eligibility": {
                "inclusion": ["Adults with type 2 diabetes"],
                "exclusion": ["Non-human studies"]
            },
            "searches": [],
            "deduplication": {
                "method": "Stable source record ID; DOI then normalized title for later review",
                "duplicate_records_removed": 0
            },
            "records": [],
            "extractions": [],
            "conflicts": [],
            "limitations": ["Screening and full-text retrieval are pending"]
        })
    }

    fn run() -> crate::heor_search::EvidenceSearchResult {
        crate::heor_search::EvidenceSearchResult {
            schema_version: "0.1.0".into(),
            request_id: "semaglutide-t2d".into(),
            request_sha256: "a".repeat(64),
            query: "semaglutide AND type 2 diabetes".into(),
            date_from: Some("2020-01-01".into()),
            date_to: Some("2026-07-14".into()),
            max_results_per_source: 10,
            executed_at: 1_752_451_200,
            executed_on: "2025-07-14".into(),
            authorization_event_id: "1".repeat(32),
            output_path: "heor/evidence-search-runs/run.json".into(),
            source_runs: vec![crate::heor_search::SourceSearchRun {
                source: "pubmed".into(),
                endpoint: "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi".into(),
                request_urls: vec![
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed".into(),
                ],
                total_count: 1,
                fetched_count: 1,
                response_sha256: vec!["b".repeat(64)],
                records: vec![crate::heor_search::EvidenceRecord {
                    record_id: "pubmed:1".into(),
                    title: "Trial".into(),
                    locator: "https://pubmed.ncbi.nlm.nih.gov/1/".into(),
                    source_type: "bibliographic_record".into(),
                    published_on: Some("2024-01-01".into()),
                    authors: vec!["A Author".into()],
                    doi: Some("10.1/example".into()),
                    metadata: serde_json::json!({"pmid": "1"}),
                }],
                limitations: vec!["Metadata only".into()],
            }],
            records: vec![],
            limitations: vec!["Candidate metadata only".into()],
        }
    }

    #[test]
    fn prepared_empty_synthesis_is_importable_but_not_complete() {
        let raw = serde_json::to_vec(&skeleton()).unwrap();
        let audit = audit_bytes(&raw);
        assert!(!audit.complete);
        assert!(audit.importable, "{:?}", audit.import_blockers);
    }

    #[test]
    fn import_adds_not_assessed_candidates_and_is_idempotent() {
        let raw = serde_json::to_vec(&skeleton()).unwrap();
        let (imported, searches, records, reconciled) =
            import_candidates(&raw, &run(), &"c".repeat(64)).unwrap();
        assert_eq!((searches, records, reconciled), (1, 1, 0));
        let audit = audit_bytes(&imported);
        assert!(!audit.complete);
        assert!(audit.importable, "{:?}", audit.import_blockers);
        assert_eq!(audit.not_assessed_count, 1);
        assert!(audit
            .errors
            .iter()
            .any(|error| error == "1 records remain not_assessed"));
        let (again, searches, records, reconciled) =
            import_candidates(&imported, &run(), &"c".repeat(64)).unwrap();
        assert_eq!((searches, records, reconciled), (0, 0, 0));
        assert_eq!(again, imported);
    }

    #[test]
    fn import_preserves_existing_screening_decisions() {
        let raw = serde_json::to_vec(&skeleton()).unwrap();
        let (imported, _, _, _) = import_candidates(&raw, &run(), &"c".repeat(64)).unwrap();
        let mut value: Value = serde_json::from_slice(&imported).unwrap();
        value["records"][0]["screening"]["title_abstract"] = Value::String("include".into());
        let changed = serde_json::to_vec(&value).unwrap();
        let (again, _, _, _) = import_candidates(&changed, &run(), &"c".repeat(64)).unwrap();
        let value: Value = serde_json::from_slice(&again).unwrap();
        assert_eq!(
            value["records"][0]["screening"]["title_abstract"],
            "include"
        );
    }

    #[test]
    fn unknown_fields_and_bad_links_fail_closed() {
        let mut value = skeleton();
        value["endpoint"] = Value::String("https://attacker.invalid".into());
        let audit = audit_bytes(&serde_json::to_vec(&value).unwrap());
        assert!(!audit.importable);
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("unsupported field")));
    }
}
