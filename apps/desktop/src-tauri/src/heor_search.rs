//! Human-authorized, app-owned HEOR evidence search.
//!
//! The agent may draft `heor/evidence-search-request.json`, but it cannot
//! execute this command or create the app-owned authorization event. Endpoints
//! and returned fields are fixed in code: no caller-controlled URL, header,
//! credential, file path, or arbitrary HEORAgent tool can cross this boundary.

use reqwest::blocking::Client;
use reqwest::redirect::Policy;
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{BTreeSet, HashSet};
use std::io::{Read, Write};
use std::path::{Component, Path, PathBuf};
use std::sync::Mutex;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager};

pub const SEARCH_REQUEST_PATH: &str = "heor/evidence-search-request.json";
const SEARCH_RUN_DIRECTORY: &str = "heor/evidence-search-runs";
const SCHEMA_VERSION: &str = "0.1.0";
const ASSURANCE: &str = "local_human_network_authorization";
const MAX_RESPONSE_BYTES: u64 = 5 * 1024 * 1024;
const MAX_EVENT_LOG_BYTES: u64 = 4 * 1024 * 1024;
const MAX_EVENTS: usize = 2_000;
const USER_AGENT: &str =
    "AI4HEOR/0.1.9 (local research desktop; https://github.com/ai4s-research/open-science)";
const PUBMED_SEARCH: &str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi";
const PUBMED_SUMMARY: &str = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi";
const CLINICAL_TRIALS_SEARCH: &str = "https://clinicaltrials.gov/api/v2/studies";

#[derive(Default)]
pub struct HeorSearchState(pub Mutex<()>);

#[derive(
    Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd, serde::Deserialize, serde::Serialize,
)]
#[serde(rename_all = "snake_case")]
enum SearchSource {
    Pubmed,
    Clinicaltrials,
}

impl SearchSource {
    fn as_str(self) -> &'static str {
        match self {
            Self::Pubmed => "pubmed",
            Self::Clinicaltrials => "clinicaltrials",
        }
    }
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct DataEgressDeclaration {
    contains_sensitive_data: bool,
    fields: Vec<String>,
    justification: String,
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct SearchRequest {
    schema_version: String,
    request_id: String,
    status: String,
    purpose: String,
    query: String,
    sources: Vec<SearchSource>,
    max_results_per_source: u32,
    #[serde(default)]
    date_from: Option<String>,
    #[serde(default)]
    date_to: Option<String>,
    data_egress: DataEgressDeclaration,
    limitations: Vec<String>,
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SearchRequestAudit {
    pub complete: bool,
    pub status: &'static str,
    pub request_id: String,
    pub request_sha256: String,
    pub query: String,
    pub sources: Vec<String>,
    pub max_results_per_source: Option<u32>,
    pub date_from: Option<String>,
    pub date_to: Option<String>,
    pub contains_sensitive_data: Option<bool>,
    pub errors: Vec<String>,
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct SearchAuthorization {
    project_id: String,
    request_sha256: String,
    actor_label: String,
    rationale: String,
    confirmed_no_sensitive_data: bool,
}

#[derive(Clone, Debug, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct SearchAuthorizationEvent {
    schema_version: u32,
    sequence: u64,
    event_id: String,
    project_id: String,
    request_sha256: String,
    sources: Vec<String>,
    actor_label: String,
    rationale: String,
    timestamp: u64,
    output_path: String,
    output_sha256: String,
    assurance: String,
    previous_hash: Option<String>,
    event_hash: String,
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SearchAuthorizationLog {
    events: Vec<SearchAuthorizationEvent>,
    chain_head: Option<String>,
    integrity: &'static str,
    identity_assurance: &'static str,
}

#[derive(Clone, Debug, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct EvidenceRecord {
    pub(crate) record_id: String,
    pub(crate) title: String,
    pub(crate) locator: String,
    pub(crate) source_type: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(crate) published_on: Option<String>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub(crate) authors: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub(crate) doi: Option<String>,
    pub(crate) metadata: Value,
}

#[derive(Clone, Debug, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct SourceSearchRun {
    pub(crate) source: String,
    pub(crate) endpoint: String,
    pub(crate) request_urls: Vec<String>,
    pub(crate) total_count: u64,
    pub(crate) fetched_count: usize,
    pub(crate) response_sha256: Vec<String>,
    pub(crate) records: Vec<EvidenceRecord>,
    pub(crate) limitations: Vec<String>,
}

#[derive(Clone, Debug, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub(crate) struct EvidenceSearchResult {
    pub(crate) schema_version: String,
    pub(crate) request_id: String,
    pub(crate) request_sha256: String,
    pub(crate) query: String,
    pub(crate) date_from: Option<String>,
    pub(crate) date_to: Option<String>,
    pub(crate) max_results_per_source: u32,
    pub(crate) executed_at: u64,
    pub(crate) executed_on: String,
    pub(crate) authorization_event_id: String,
    pub(crate) output_path: String,
    pub(crate) source_runs: Vec<SourceSearchRun>,
    pub(crate) records: Vec<EvidenceRecord>,
    pub(crate) limitations: Vec<String>,
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct SearchExecutionResponse {
    result: EvidenceSearchResult,
    authorization: SearchAuthorizationEvent,
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn unix_date(timestamp: u64) -> Result<String, String> {
    let days = i64::try_from(timestamp / 86_400)
        .map_err(|_| "search timestamp is outside the supported date range")?;
    let shifted = days + 719_468;
    let era = if shifted >= 0 {
        shifted
    } else {
        shifted - 146_096
    } / 146_097;
    let day_of_era = shifted - era * 146_097;
    let year_of_era =
        (day_of_era - day_of_era / 1_460 + day_of_era / 36_524 - day_of_era / 146_096) / 365;
    let mut year = year_of_era + era * 400;
    let day_of_year = day_of_era - (365 * year_of_era + year_of_era / 4 - year_of_era / 100);
    let month_prime = (5 * day_of_year + 2) / 153;
    let day = day_of_year - (153 * month_prime + 2) / 5 + 1;
    let month = month_prime + if month_prime < 10 { 3 } else { -9 };
    year += i64::from(month <= 2);
    if !(1900..=3000).contains(&year) {
        return Err("search timestamp is outside the supported date range".into());
    }
    Ok(format!("{year:04}-{month:02}-{day:02}"))
}

fn text(value: Option<&Value>) -> Option<&str> {
    value
        .and_then(Value::as_str)
        .filter(|value| !value.trim().is_empty())
}

fn text_array(value: Option<&Value>) -> Option<Vec<&str>> {
    let values = value?.as_array()?;
    let mut output = Vec::with_capacity(values.len());
    for value in values {
        output.push(text(Some(value))?);
    }
    Some(output)
}

fn safe_id(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 80
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
}

fn is_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn validate_text(value: &str, field: &str, max_chars: usize) -> Result<(), String> {
    let trimmed = value.trim();
    if trimmed.is_empty() || trimmed.chars().count() > max_chars {
        return Err(format!("{field} must contain 1-{max_chars} characters"));
    }
    if trimmed != value || value.chars().any(char::is_control) {
        return Err(format!(
            "{field} must not contain surrounding whitespace or control characters"
        ));
    }
    Ok(())
}

fn leap_year(year: u32) -> bool {
    year.is_multiple_of(4) && (!year.is_multiple_of(100) || year.is_multiple_of(400))
}

fn date_key(value: &str) -> Option<u32> {
    if value.len() != 10 || &value[4..5] != "-" || &value[7..8] != "-" {
        return None;
    }
    let year = value[0..4].parse::<u32>().ok()?;
    let month = value[5..7].parse::<u32>().ok()?;
    let day = value[8..10].parse::<u32>().ok()?;
    let max_day = match month {
        1 | 3 | 5 | 7 | 8 | 10 | 12 => 31,
        4 | 6 | 9 | 11 => 30,
        2 if leap_year(year) => 29,
        2 => 28,
        _ => return None,
    };
    (year >= 1900 && day > 0 && day <= max_day).then_some(year * 10_000 + month * 100 + day)
}

fn exact_keys(value: &serde_json::Map<String, Value>, allowed: &[&str]) -> Vec<String> {
    let allowed = allowed.iter().copied().collect::<HashSet<_>>();
    value
        .keys()
        .filter(|key| !allowed.contains(key.as_str()))
        .cloned()
        .collect()
}

pub(crate) fn audit_request_bytes(raw: &[u8]) -> SearchRequestAudit {
    let request_sha256 = sha256(raw);
    let value: Value = match serde_json::from_slice::<Value>(raw) {
        Ok(value) if value.is_object() => value,
        Ok(_) => {
            return SearchRequestAudit {
                complete: false,
                status: "incomplete",
                request_id: String::new(),
                request_sha256,
                query: String::new(),
                sources: Vec::new(),
                max_results_per_source: None,
                date_from: None,
                date_to: None,
                contains_sensitive_data: None,
                errors: vec!["search request must be a JSON object".into()],
            }
        }
        Err(error) => {
            return SearchRequestAudit {
                complete: false,
                status: "incomplete",
                request_id: String::new(),
                request_sha256,
                query: String::new(),
                sources: Vec::new(),
                max_results_per_source: None,
                date_from: None,
                date_to: None,
                contains_sensitive_data: None,
                errors: vec![format!("search request is invalid JSON: {error}")],
            }
        }
    };
    let object = value.as_object().unwrap();
    let request_id = text(object.get("request_id")).unwrap_or_default();
    let query = text(object.get("query")).unwrap_or_default();
    let date_from = text(object.get("date_from")).map(str::to_string);
    let date_to = text(object.get("date_to")).map(str::to_string);
    let max_results = object
        .get("max_results_per_source")
        .and_then(Value::as_u64)
        .and_then(|value| u32::try_from(value).ok());
    let source_values = text_array(object.get("sources")).unwrap_or_default();
    let sources = source_values
        .iter()
        .map(|value| (*value).to_string())
        .collect::<Vec<_>>();
    let data_egress = object.get("data_egress").and_then(Value::as_object);
    let contains_sensitive_data = data_egress
        .and_then(|value| value.get("contains_sensitive_data"))
        .and_then(Value::as_bool);
    let mut errors = Vec::new();

    for key in exact_keys(
        object,
        &[
            "schema_version",
            "request_id",
            "status",
            "purpose",
            "query",
            "sources",
            "max_results_per_source",
            "date_from",
            "date_to",
            "data_egress",
            "limitations",
        ],
    ) {
        errors.push(format!("unsupported top-level field: {key}"));
    }
    if text(object.get("schema_version")) != Some(SCHEMA_VERSION) {
        errors.push(format!("schema_version must be {SCHEMA_VERSION}"));
    }
    if !safe_id(request_id) {
        errors
            .push("request_id must be 1-80 ASCII letters, digits, hyphens, or underscores".into());
    }
    if text(object.get("status")) != Some("ready_for_human_review") {
        errors.push("status must be ready_for_human_review before network authorization".into());
    }
    if text(object.get("purpose")).is_none() {
        errors.push("purpose is required".into());
    }
    if validate_text(query, "query", 500).is_err() {
        errors.push("query must contain 1-500 characters without control characters".into());
    }
    let unique_sources = sources.iter().collect::<HashSet<_>>();
    if sources.is_empty()
        || unique_sources.len() != sources.len()
        || sources
            .iter()
            .any(|source| !matches!(source.as_str(), "pubmed" | "clinicaltrials"))
    {
        errors
            .push("sources must be a unique non-empty subset of pubmed and clinicaltrials".into());
    }
    if !max_results.is_some_and(|value| (1..=50).contains(&value)) {
        errors.push("max_results_per_source must be an integer from 1 to 50".into());
    }
    let from_key = date_from.as_deref().and_then(date_key);
    let to_key = date_to.as_deref().and_then(date_key);
    if date_from.is_some() && from_key.is_none() {
        errors.push("date_from must be a valid YYYY-MM-DD date".into());
    }
    if date_to.is_some() && to_key.is_none() {
        errors.push("date_to must be a valid YYYY-MM-DD date".into());
    }
    if matches!((from_key, to_key), (Some(from), Some(to)) if from > to) {
        errors.push("date_from must not be after date_to".into());
    }
    match data_egress {
        Some(declaration) => {
            for key in exact_keys(
                declaration,
                &["contains_sensitive_data", "fields", "justification"],
            ) {
                errors.push(format!("unsupported data_egress field: {key}"));
            }
            if contains_sensitive_data != Some(false) {
                errors.push("data_egress.contains_sensitive_data must be false".into());
            }
            let fields = text_array(declaration.get("fields")).unwrap_or_default();
            let fields = fields.into_iter().collect::<BTreeSet<_>>();
            let required = ["date_from", "date_to", "query"]
                .into_iter()
                .collect::<BTreeSet<_>>();
            if fields != required {
                errors.push(
                    "data_egress.fields must disclose exactly query, date_from, and date_to".into(),
                );
            }
            if text(declaration.get("justification")).is_none() {
                errors.push("data_egress.justification is required".into());
            }
        }
        None => errors.push("data_egress declaration is required".into()),
    }
    if text_array(object.get("limitations")).is_none_or(|items| items.is_empty()) {
        errors.push("limitations must be a non-empty string array".into());
    }
    if errors.is_empty() {
        if let Err(error) = serde_json::from_value::<SearchRequest>(value.clone()) {
            errors.push(format!("search request shape is invalid: {error}"));
        }
    }
    SearchRequestAudit {
        complete: errors.is_empty(),
        status: if errors.is_empty() {
            "complete"
        } else {
            "incomplete"
        },
        request_id: request_id.to_string(),
        request_sha256,
        query: query.to_string(),
        sources,
        max_results_per_source: max_results,
        date_from,
        date_to,
        contains_sensitive_data,
        errors,
    }
}

fn parse_request(raw: &[u8]) -> Result<(SearchRequest, SearchRequestAudit), String> {
    let audit = audit_request_bytes(raw);
    if !audit.complete {
        return Err(format!(
            "evidence search request is not authorizable: {}",
            audit.errors.join("; ")
        ));
    }
    let request = serde_json::from_slice(raw).map_err(|error| error.to_string())?;
    Ok((request, audit))
}

fn client() -> Result<Client, String> {
    Client::builder()
        .user_agent(USER_AGENT)
        .connect_timeout(Duration::from_secs(10))
        .timeout(Duration::from_secs(25))
        .redirect(Policy::none())
        .build()
        .map_err(|error| format!("evidence search HTTP client failed: {error}"))
}

fn fetch_json(client: &Client, url: reqwest::Url) -> Result<(Value, String, String), String> {
    if url.scheme() != "https" {
        return Err("evidence search endpoint must use HTTPS".into());
    }
    let request_url = url.to_string();
    let response = client
        .get(url)
        .send()
        .map_err(|error| format!("evidence source request failed: {error}"))?;
    if !response.status().is_success() {
        return Err(format!(
            "evidence source returned HTTP {}",
            response.status()
        ));
    }
    if response
        .content_length()
        .is_some_and(|length| length > MAX_RESPONSE_BYTES)
    {
        return Err("evidence source response exceeds the 5 MiB limit".into());
    }
    let content_type = response
        .headers()
        .get(reqwest::header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .unwrap_or_default()
        .to_ascii_lowercase();
    if !content_type.contains("json") {
        return Err("evidence source did not return JSON".into());
    }
    let mut bytes = Vec::new();
    response
        .take(MAX_RESPONSE_BYTES + 1)
        .read_to_end(&mut bytes)
        .map_err(|error| format!("evidence source response read failed: {error}"))?;
    if bytes.len() as u64 > MAX_RESPONSE_BYTES {
        return Err("evidence source response exceeds the 5 MiB limit".into());
    }
    let value = serde_json::from_slice(&bytes)
        .map_err(|error| format!("evidence source returned invalid JSON: {error}"))?;
    Ok((value, sha256(&bytes), request_url))
}

fn pubmed_search_url(request: &SearchRequest) -> Result<reqwest::Url, String> {
    let mut url = reqwest::Url::parse(PUBMED_SEARCH).map_err(|error| error.to_string())?;
    {
        let mut query = url.query_pairs_mut();
        query
            .append_pair("db", "pubmed")
            .append_pair("term", &request.query)
            .append_pair("retmax", &request.max_results_per_source.to_string())
            .append_pair("retmode", "json")
            .append_pair("datetype", "pdat");
        if let Some(value) = &request.date_from {
            query.append_pair("mindate", &value.replace('-', "/"));
        }
        if let Some(value) = &request.date_to {
            query.append_pair("maxdate", &value.replace('-', "/"));
        }
    }
    Ok(url)
}

fn pubmed_summary_url(ids: &[String]) -> Result<reqwest::Url, String> {
    let mut url = reqwest::Url::parse(PUBMED_SUMMARY).map_err(|error| error.to_string())?;
    url.query_pairs_mut()
        .append_pair("db", "pubmed")
        .append_pair("id", &ids.join(","))
        .append_pair("retmode", "json");
    Ok(url)
}

fn normalize_pubmed(summary: &Value, ids: &[String]) -> Vec<EvidenceRecord> {
    let result = summary.get("result").and_then(Value::as_object);
    ids.iter()
        .filter_map(|id| {
            let item = result?.get(id)?.as_object()?;
            let title = text(item.get("title"))?.trim_end_matches('.').to_string();
            let authors = item
                .get("authors")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .filter_map(|author| text(author.get("name")).map(str::to_string))
                .collect::<Vec<_>>();
            let doi = item
                .get("articleids")
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .find(|value| value.get("idtype").and_then(Value::as_str) == Some("doi"))
                .and_then(|value| text(value.get("value")))
                .map(str::to_string);
            let published_on = text(item.get("sortpubdate"))
                .and_then(|value| value.get(0..10))
                .filter(|value| date_key(value).is_some())
                .map(str::to_string);
            Some(EvidenceRecord {
                record_id: format!("pubmed:{id}"),
                title,
                locator: format!("https://pubmed.ncbi.nlm.nih.gov/{id}/"),
                source_type: "bibliographic_record".into(),
                published_on,
                authors,
                doi,
                metadata: serde_json::json!({
                    "pmid": id,
                    "journal": text(item.get("fulljournalname")).unwrap_or_default(),
                    "publicationTypes": item.get("pubtype").cloned().unwrap_or_else(|| serde_json::json!([])),
                    "hasAbstract": item.get("attributes").and_then(Value::as_array).is_some_and(|values| values.iter().any(|value| value.as_str() == Some("Has Abstract")))
                }),
            })
        })
        .collect()
}

fn search_pubmed(client: &Client, request: &SearchRequest) -> Result<SourceSearchRun, String> {
    let (search, search_hash, search_url) = fetch_json(client, pubmed_search_url(request)?)?;
    let search_result = search
        .get("esearchresult")
        .and_then(Value::as_object)
        .ok_or("PubMed ESearch response is missing esearchresult")?;
    let total_count = text(search_result.get("count"))
        .and_then(|value| value.parse().ok())
        .unwrap_or(0);
    let ids = search_result
        .get("idlist")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|value| value.as_str().map(str::to_string))
        .collect::<Vec<_>>();
    let (records, request_urls, response_sha256) = if ids.is_empty() {
        (Vec::new(), vec![search_url], vec![search_hash])
    } else {
        let (summary, summary_hash, summary_url) = fetch_json(client, pubmed_summary_url(&ids)?)?;
        (
            normalize_pubmed(&summary, &ids),
            vec![search_url, summary_url],
            vec![search_hash, summary_hash],
        )
    };
    Ok(SourceSearchRun {
        source: SearchSource::Pubmed.as_str().into(),
        endpoint: PUBMED_SEARCH.into(),
        request_urls,
        total_count,
        fetched_count: records.len(),
        response_sha256,
        records,
        limitations: vec![
            "PubMed ESearch and ESummary return bibliographic metadata, not verified full text or extracted outcomes".into(),
            "Search rankings and indexed records can change after this timestamp".into(),
        ],
    })
}

fn clinical_trials_url(request: &SearchRequest) -> Result<reqwest::Url, String> {
    let mut url = reqwest::Url::parse(CLINICAL_TRIALS_SEARCH).map_err(|error| error.to_string())?;
    url.query_pairs_mut()
        .append_pair("query.term", &request.query)
        .append_pair("pageSize", &request.max_results_per_source.to_string())
        .append_pair("format", "json")
        .append_pair("countTotal", "true")
        .append_pair(
            "fields",
            "NCTId,BriefTitle,OfficialTitle,OverallStatus,StudyType,StartDate,CompletionDate,StudyFirstPostDate,Condition,InterventionName",
        );
    Ok(url)
}

fn nested_text<'a>(value: &'a Value, path: &[&str]) -> Option<&'a str> {
    let mut current = value;
    for segment in path {
        current = current.get(*segment)?;
    }
    text(Some(current))
}

fn string_values(value: Option<&Value>) -> Vec<String> {
    value
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|value| value.as_str().map(str::to_string))
        .collect()
}

fn normalize_clinical_trials(value: &Value) -> Vec<EvidenceRecord> {
    value
        .get("studies")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|study| {
            let protocol = study.get("protocolSection")?;
            let nct_id = nested_text(protocol, &["identificationModule", "nctId"])?;
            let title = nested_text(protocol, &["identificationModule", "briefTitle"])
                .or_else(|| nested_text(protocol, &["identificationModule", "officialTitle"]))?;
            let conditions = string_values(
                protocol
                    .get("conditionsModule")
                    .and_then(|value| value.get("conditions")),
            );
            let interventions = protocol
                .get("armsInterventionsModule")
                .and_then(|value| value.get("interventions"))
                .and_then(Value::as_array)
                .into_iter()
                .flatten()
                .filter_map(|value| text(value.get("name")).map(str::to_string))
                .collect::<Vec<_>>();
            Some(EvidenceRecord {
                record_id: format!("clinicaltrials:{nct_id}"),
                title: title.to_string(),
                locator: format!("https://clinicaltrials.gov/study/{nct_id}"),
                source_type: "trial_registry_record".into(),
                published_on: nested_text(
                    protocol,
                    &["statusModule", "studyFirstPostDateStruct", "date"],
                )
                .filter(|value| date_key(value).is_some())
                .map(str::to_string),
                authors: Vec::new(),
                doi: None,
                metadata: serde_json::json!({
                    "nctId": nct_id,
                    "overallStatus": nested_text(protocol, &["statusModule", "overallStatus"]),
                    "studyType": nested_text(protocol, &["designModule", "studyType"]),
                    "startDate": nested_text(protocol, &["statusModule", "startDateStruct", "date"]),
                    "completionDate": nested_text(protocol, &["statusModule", "completionDateStruct", "date"]),
                    "conditions": conditions,
                    "interventions": interventions,
                }),
            })
        })
        .collect()
}

fn search_clinical_trials(
    client: &Client,
    request: &SearchRequest,
) -> Result<SourceSearchRun, String> {
    let (response, response_hash, request_url) = fetch_json(client, clinical_trials_url(request)?)?;
    let mut records = normalize_clinical_trials(&response);
    if request.date_from.is_some() || request.date_to.is_some() {
        let from = request.date_from.as_deref().and_then(date_key);
        let to = request.date_to.as_deref().and_then(date_key);
        records.retain(|record| {
            record
                .published_on
                .as_deref()
                .and_then(date_key)
                .is_some_and(|date| {
                    from.is_none_or(|min| date >= min) && to.is_none_or(|max| date <= max)
                })
        });
    }
    let total_count = response
        .get("totalCount")
        .and_then(Value::as_u64)
        .unwrap_or(records.len() as u64);
    Ok(SourceSearchRun {
        source: SearchSource::Clinicaltrials.as_str().into(),
        endpoint: CLINICAL_TRIALS_SEARCH.into(),
        request_urls: vec![request_url],
        total_count,
        fetched_count: records.len(),
        response_sha256: vec![response_hash],
        records,
        limitations: vec![
            "ClinicalTrials.gov is a study registry; registration is not peer review and does not establish results validity".into(),
            "The optional date range is applied locally to the first-posted date after the bounded API page is returned".into(),
        ],
    })
}

fn validate_authorization(value: &SearchAuthorization) -> Result<(), String> {
    if !safe_id(&value.project_id) {
        return Err("projectId is invalid".into());
    }
    if !is_sha256(&value.request_sha256) {
        return Err("requestSha256 must be 64 lowercase hexadecimal characters".into());
    }
    validate_text(&value.actor_label, "actorLabel", 120)?;
    validate_text(&value.rationale, "rationale", 2_000)?;
    if !value.confirmed_no_sensitive_data {
        return Err("human confirmation of non-sensitive network egress is required".into());
    }
    Ok(())
}

fn event_root(app: &AppHandle) -> Result<PathBuf, String> {
    Ok(app
        .path()
        .app_data_dir()
        .map_err(|error| error.to_string())?
        .join("heor")
        .join("evidence-search-events"))
}

fn event_file(root: &Path, project_id: &str) -> Result<PathBuf, String> {
    if !safe_id(project_id) {
        return Err("projectId is invalid".into());
    }
    Ok(root.join(format!("{project_id}.jsonl")))
}

fn hash_event(event: &SearchAuthorizationEvent) -> Result<String, String> {
    let mut payload = event.clone();
    payload.event_hash.clear();
    serde_json::to_vec(&payload)
        .map(|raw| sha256(&raw))
        .map_err(|error| error.to_string())
}

fn read_verified_events(
    root: &Path,
    project_id: &str,
) -> Result<Vec<SearchAuthorizationEvent>, String> {
    let file = event_file(root, project_id)?;
    let metadata = match std::fs::metadata(&file) {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(Vec::new()),
        Err(error) => return Err(format!("search authorization log unavailable: {error}")),
    };
    if !metadata.is_file() || metadata.len() > MAX_EVENT_LOG_BYTES {
        return Err("search authorization log is not a bounded regular file".into());
    }
    let text = std::fs::read_to_string(&file)
        .map_err(|error| format!("search authorization log read failed: {error}"))?;
    let mut events = Vec::new();
    let mut previous_hash = None;
    for (index, line) in text.lines().enumerate() {
        if line.trim().is_empty() || index >= MAX_EVENTS {
            return Err("search authorization log is malformed or exceeds its event cap".into());
        }
        let event: SearchAuthorizationEvent = serde_json::from_str(line).map_err(|error| {
            format!(
                "search authorization log line {} is invalid: {error}",
                index + 1
            )
        })?;
        if event.schema_version != 1
            || event.sequence != index as u64 + 1
            || event.project_id != project_id
            || event.assurance != ASSURANCE
            || event.previous_hash != previous_hash
            || !is_sha256(&event.request_sha256)
            || !is_sha256(&event.output_sha256)
            || !is_sha256(&event.event_hash)
            || hash_event(&event)? != event.event_hash
        {
            return Err(format!(
                "search authorization log integrity failed at line {}",
                index + 1
            ));
        }
        previous_hash = Some(event.event_hash.clone());
        events.push(event);
    }
    Ok(events)
}

fn append_event(
    root: &Path,
    mut event: SearchAuthorizationEvent,
) -> Result<SearchAuthorizationEvent, String> {
    let events = read_verified_events(root, &event.project_id)?;
    if events.len() >= MAX_EVENTS {
        return Err("search authorization event cap reached".into());
    }
    event.sequence = events.len() as u64 + 1;
    event.previous_hash = events.last().map(|event| event.event_hash.clone());
    event.event_hash = hash_event(&event)?;
    std::fs::create_dir_all(root)
        .map_err(|error| format!("search authorization directory failed: {error}"))?;
    crate::runtime::tighten_private(root);
    let file = event_file(root, &event.project_id)?;
    let mut output = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&file)
        .map_err(|error| format!("search authorization log open failed: {error}"))?;
    crate::runtime::tighten_private(&file);
    writeln!(
        output,
        "{}",
        serde_json::to_string(&event).map_err(|error| error.to_string())?
    )
    .and_then(|_| output.sync_all())
    .map_err(|error| format!("search authorization log write failed: {error}"))?;
    Ok(event)
}

fn ensure_directory(workspace: &Path, relative: &str) -> Result<PathBuf, String> {
    let root = workspace
        .canonicalize()
        .map_err(|error| format!("workspace unavailable: {error}"))?;
    let mut current = root.clone();
    for component in Path::new(relative).components() {
        let Component::Normal(segment) = component else {
            return Err("search output directory is unsafe".into());
        };
        current.push(segment);
        match std::fs::symlink_metadata(&current) {
            Ok(metadata) if metadata.file_type().is_symlink() || !metadata.is_dir() => {
                return Err("search output directory cannot contain symlinks or files".into())
            }
            Ok(_) => {}
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                std::fs::create_dir(&current)
                    .map_err(|error| format!("search output directory failed: {error}"))?;
            }
            Err(error) => return Err(format!("search output directory failed: {error}")),
        }
    }
    let canonical = current
        .canonicalize()
        .map_err(|error| format!("search output directory unavailable: {error}"))?;
    if !canonical.starts_with(root) {
        return Err("search output directory escaped the current workspace".into());
    }
    Ok(canonical)
}

fn write_result(workspace: &Path, relative: &str, raw: &[u8]) -> Result<PathBuf, String> {
    if raw.len() as u64 > MAX_RESPONSE_BYTES || Path::new(relative).is_absolute() {
        return Err("search result is not a bounded workspace artifact".into());
    }
    let parent = ensure_directory(workspace, SEARCH_RUN_DIRECTORY)?;
    let name = Path::new(relative)
        .file_name()
        .ok_or("search result filename is missing")?;
    let target = parent.join(name);
    let temporary = parent.join(format!(".search-{}.tmp", crate::runtime::random_hex(8)));
    let mut output = std::fs::OpenOptions::new()
        .create_new(true)
        .write(true)
        .open(&temporary)
        .map_err(|error| format!("search result staging failed: {error}"))?;
    output
        .write_all(raw)
        .and_then(|_| output.sync_all())
        .map_err(|error| format!("search result write failed: {error}"))?;
    if target.exists() {
        let _ = std::fs::remove_file(&temporary);
        return Err("search result already exists; existing evidence is never overwritten".into());
    }
    std::fs::rename(&temporary, &target).map_err(|error| {
        let _ = std::fs::remove_file(&temporary);
        format!("search result commit failed: {error}")
    })?;
    Ok(target)
}

fn execute_at(
    app: &AppHandle,
    authorization: SearchAuthorization,
    timestamp: u64,
    event_id: String,
) -> Result<SearchExecutionResponse, String> {
    validate_authorization(&authorization)?;
    let workspace = crate::runtime::workspace_dir(app)?;
    if crate::project::require_project_id(&workspace)? != authorization.project_id {
        return Err("search authorization projectId does not match the current project".into());
    }
    let raw = crate::heor_uncertainty::read_workspace_capped(&workspace, SEARCH_REQUEST_PATH)?;
    let (request, audit) = parse_request(&raw)?;
    if audit.request_sha256 != authorization.request_sha256 {
        return Err("search authorization must bind the exact current request bytes".into());
    }
    if request.schema_version != SCHEMA_VERSION
        || request.status != "ready_for_human_review"
        || request.data_egress.contains_sensitive_data
        || request.data_egress.fields.is_empty()
        || request.data_egress.justification.trim().is_empty()
        || request.purpose.trim().is_empty()
        || request.limitations.is_empty()
    {
        return Err("search request changed after audit".into());
    }
    let client = client()?;
    let mut source_runs = Vec::new();
    for source in &request.sources {
        source_runs.push(match source {
            SearchSource::Pubmed => search_pubmed(&client, &request)?,
            SearchSource::Clinicaltrials => search_clinical_trials(&client, &request)?,
        });
    }
    let mut seen = HashSet::new();
    let mut records = Vec::new();
    for run in &source_runs {
        for record in &run.records {
            if seen.insert(record.record_id.clone()) {
                records.push(record.clone());
            }
        }
    }
    let output_path = format!(
        "{SEARCH_RUN_DIRECTORY}/{}-{timestamp}-{}.json",
        request.request_id,
        &event_id[..8]
    );
    let result = EvidenceSearchResult {
        schema_version: SCHEMA_VERSION.into(),
        request_id: request.request_id,
        request_sha256: audit.request_sha256.clone(),
        query: request.query,
        date_from: request.date_from,
        date_to: request.date_to,
        max_results_per_source: request.max_results_per_source,
        executed_at: timestamp,
        executed_on: unix_date(timestamp)?,
        authorization_event_id: event_id.clone(),
        output_path: output_path.clone(),
        source_runs,
        records,
        limitations: vec![
            "This is a bounded metadata retrieval, not a systematic-review completeness claim".into(),
            "All records require screening, full-text assessment, critical appraisal, extraction, and human review before decision use".into(),
            "No economic calculation, evidence grading, approval, or reimbursement conclusion is produced by this connector".into(),
        ],
    };
    let mut output_raw = serde_json::to_vec_pretty(&result).map_err(|error| error.to_string())?;
    output_raw.push(b'\n');
    let output_sha256 = sha256(&output_raw);
    let output = write_result(&workspace, &output_path, &output_raw)?;
    let event = SearchAuthorizationEvent {
        schema_version: 1,
        sequence: 0,
        event_id,
        project_id: authorization.project_id,
        request_sha256: audit.request_sha256,
        sources: request
            .sources
            .iter()
            .map(|source| source.as_str().to_string())
            .collect(),
        actor_label: authorization.actor_label,
        rationale: authorization.rationale,
        timestamp,
        output_path,
        output_sha256,
        assurance: ASSURANCE.into(),
        previous_hash: None,
        event_hash: String::new(),
    };
    let event = match append_event(&event_root(app)?, event) {
        Ok(event) => event,
        Err(error) => {
            let _ = std::fs::remove_file(output);
            return Err(error);
        }
    };
    Ok(SearchExecutionResponse {
        result,
        authorization: event,
    })
}

pub(crate) fn verified_search_result(
    app: &AppHandle,
    project_id: &str,
    output_path: &str,
    expected_output_sha256: &str,
) -> Result<EvidenceSearchResult, String> {
    if !safe_id(project_id)
        || !is_sha256(expected_output_sha256)
        || Path::new(output_path).is_absolute()
        || !output_path.starts_with(&format!("{SEARCH_RUN_DIRECTORY}/"))
        || Path::new(output_path)
            .components()
            .any(|component| !matches!(component, Component::Normal(_)))
    {
        return Err("evidence-search import reference is invalid".into());
    }
    let workspace = crate::runtime::workspace_dir(app)?;
    if crate::project::require_project_id(&workspace)? != project_id {
        return Err("evidence-search import projectId does not match the current project".into());
    }
    let events = read_verified_events(&event_root(app)?, project_id)?;
    let event = events
        .iter()
        .find(|event| event.output_path == output_path)
        .ok_or("evidence-search run has no verified app-owned authorization event")?;
    if event.output_sha256 != expected_output_sha256 {
        return Err("evidence-search run hash does not match its authorization event".into());
    }
    let raw = crate::heor_uncertainty::read_workspace_capped(&workspace, output_path)?;
    if sha256(&raw) != expected_output_sha256 {
        return Err("evidence-search run bytes changed after authorization".into());
    }
    let result: EvidenceSearchResult = serde_json::from_slice(&raw)
        .map_err(|error| format!("evidence-search run contract is invalid: {error}"))?;
    if result.schema_version != SCHEMA_VERSION
        || result.output_path != output_path
        || result.authorization_event_id != event.event_id
        || result.request_sha256 != event.request_sha256
        || result.executed_at != event.timestamp
        || date_key(&result.executed_on).is_none()
        || result.source_runs.is_empty()
        || result.source_runs.len() > 2
        || result.max_results_per_source == 0
        || result.max_results_per_source > 50
    {
        return Err("evidence-search run does not match its authorization event".into());
    }
    let mut sources = BTreeSet::new();
    let mut record_ids = HashSet::new();
    for run in &result.source_runs {
        let (endpoint, host) = match run.source.as_str() {
            "pubmed" => (PUBMED_SEARCH, "eutils.ncbi.nlm.nih.gov"),
            "clinicaltrials" => (CLINICAL_TRIALS_SEARCH, "clinicaltrials.gov"),
            _ => return Err("evidence-search run contains an unsupported source".into()),
        };
        if !sources.insert(run.source.clone())
            || run.endpoint != endpoint
            || run.fetched_count != run.records.len()
            || run.fetched_count > result.max_results_per_source as usize
            || run.response_sha256.is_empty()
            || run.response_sha256.iter().any(|value| !is_sha256(value))
            || run.request_urls.is_empty()
        {
            return Err("evidence-search source run is internally inconsistent".into());
        }
        for request_url in &run.request_urls {
            let url = reqwest::Url::parse(request_url)
                .map_err(|_| "evidence-search run contains an invalid request URL")?;
            if url.scheme() != "https" || url.host_str() != Some(host) {
                return Err("evidence-search run contains a non-allowlisted request URL".into());
            }
        }
        for record in &run.records {
            if !record_ids.insert(record.record_id.clone()) {
                return Err("evidence-search run contains duplicate source record IDs".into());
            }
        }
    }
    if sources != event.sources.iter().cloned().collect::<BTreeSet<_>>() {
        return Err("evidence-search run sources do not match its authorization event".into());
    }
    let combined_ids = result
        .records
        .iter()
        .map(|record| record.record_id.as_str())
        .collect::<HashSet<_>>();
    if combined_ids.len() != result.records.len()
        || combined_ids.len() != record_ids.len()
        || !record_ids
            .iter()
            .all(|record_id| combined_ids.contains(record_id.as_str()))
    {
        return Err("evidence-search combined records do not match its source runs".into());
    }
    Ok(result)
}

#[tauri::command]
pub fn audit_heor_evidence_search(app: AppHandle) -> Result<SearchRequestAudit, String> {
    let workspace = crate::runtime::workspace_dir(&app)?;
    match crate::heor_uncertainty::read_workspace_capped(&workspace, SEARCH_REQUEST_PATH) {
        Ok(raw) => Ok(audit_request_bytes(&raw)),
        Err(error) => Ok(SearchRequestAudit {
            complete: false,
            status: "incomplete",
            request_id: String::new(),
            request_sha256: String::new(),
            query: String::new(),
            sources: Vec::new(),
            max_results_per_source: None,
            date_from: None,
            date_to: None,
            contains_sensitive_data: None,
            errors: vec![error],
        }),
    }
}

#[tauri::command(async)]
pub fn execute_heor_evidence_search(
    app: AppHandle,
    state: tauri::State<HeorSearchState>,
    authorization: SearchAuthorization,
) -> Result<SearchExecutionResponse, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "HEOR evidence-search lock poisoned")?;
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| error.to_string())?
        .as_secs();
    execute_at(
        &app,
        authorization,
        timestamp,
        crate::runtime::random_hex(16),
    )
}

#[tauri::command(async)]
pub fn list_heor_search_authorizations(
    app: AppHandle,
    state: tauri::State<HeorSearchState>,
    project_id: String,
) -> Result<SearchAuthorizationLog, String> {
    let _guard = state
        .0
        .lock()
        .map_err(|_| "HEOR evidence-search lock poisoned")?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    if crate::project::require_project_id(&workspace)? != project_id {
        return Err("search authorization projectId does not match the current project".into());
    }
    let events = read_verified_events(&event_root(&app)?, &project_id)?;
    Ok(SearchAuthorizationLog {
        chain_head: events.last().map(|event| event.event_hash.clone()),
        events,
        integrity: "verified_unanchored_sha256_chain",
        identity_assurance: ASSURANCE,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid_request() -> Value {
        serde_json::json!({
            "schema_version": "0.1.0",
            "request_id": "semaglutide-t2d",
            "status": "ready_for_human_review",
            "purpose": "Identify clinical and economic evidence candidates for screening",
            "query": "semaglutide type 2 diabetes cost effectiveness",
            "sources": ["pubmed", "clinicaltrials"],
            "max_results_per_source": 10,
            "date_from": "2020-01-01",
            "date_to": "2026-07-14",
            "data_egress": {
                "contains_sensitive_data": false,
                "fields": ["query", "date_from", "date_to"],
                "justification": "Public bibliographic and trial-registry search"
            },
            "limitations": ["Search metadata requires human screening"]
        })
    }

    #[test]
    fn complete_request_is_authorizable() {
        let raw = serde_json::to_vec(&valid_request()).unwrap();
        let audit = audit_request_bytes(&raw);
        assert!(audit.complete, "{:?}", audit.errors);
        assert_eq!(audit.sources, ["pubmed", "clinicaltrials"]);
    }

    #[test]
    fn arbitrary_endpoints_and_hidden_fields_fail_closed() {
        let mut value = valid_request();
        value["sources"] = serde_json::json!(["https://attacker.invalid/search"]);
        value["headers"] = serde_json::json!({"Authorization": "secret"});
        let audit = audit_request_bytes(&serde_json::to_vec(&value).unwrap());
        assert!(!audit.complete);
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("unsupported top-level")));
        assert!(audit.errors.iter().any(|error| error.contains("sources")));
    }

    #[test]
    fn sensitive_or_undeclared_egress_fails_closed() {
        let mut value = valid_request();
        value["data_egress"]["contains_sensitive_data"] = serde_json::json!(true);
        value["data_egress"]["fields"] = serde_json::json!(["query"]);
        let audit = audit_request_bytes(&serde_json::to_vec(&value).unwrap());
        assert!(!audit.complete);
        assert_eq!(audit.contains_sensitive_data, Some(true));
    }

    #[test]
    fn dates_are_calendar_valid_and_ordered() {
        let mut value = valid_request();
        value["date_from"] = serde_json::json!("2025-02-29");
        value["date_to"] = serde_json::json!("2024-01-01");
        let audit = audit_request_bytes(&serde_json::to_vec(&value).unwrap());
        assert!(!audit.complete);
        assert!(audit.errors.iter().any(|error| error.contains("date_from")));
    }

    #[test]
    fn fixed_urls_encode_query_instead_of_accepting_a_host() {
        let request: SearchRequest = serde_json::from_value(valid_request()).unwrap();
        let pubmed = pubmed_search_url(&request).unwrap();
        let trials = clinical_trials_url(&request).unwrap();
        assert_eq!(pubmed.host_str(), Some("eutils.ncbi.nlm.nih.gov"));
        assert_eq!(trials.host_str(), Some("clinicaltrials.gov"));
        assert!(pubmed
            .query_pairs()
            .any(|(key, value)| key == "term" && value == request.query));
        assert!(trials
            .query_pairs()
            .any(|(key, value)| key == "query.term" && value == request.query));
    }

    #[test]
    fn provider_responses_normalize_to_bounded_records() {
        let pubmed = serde_json::json!({"result": {"1": {
            "title": "Study title.",
            "authors": [{"name": "A Author"}],
            "sortpubdate": "2025/04/02 00:00",
            "articleids": [{"idtype": "doi", "value": "10.1/example"}],
            "fulljournalname": "Journal",
            "pubtype": ["Journal Article"],
            "attributes": ["Has Abstract"]
        }}});
        let records = normalize_pubmed(&pubmed, &["1".into()]);
        assert_eq!(records.len(), 1);
        assert_eq!(records[0].record_id, "pubmed:1");
        assert_eq!(records[0].doi.as_deref(), Some("10.1/example"));

        let trials = serde_json::json!({"studies": [{"protocolSection": {
            "identificationModule": {"nctId": "NCT00000001", "briefTitle": "Trial"},
            "statusModule": {"overallStatus": "COMPLETED", "studyFirstPostDateStruct": {"date": "2024-01-02"}},
            "designModule": {"studyType": "INTERVENTIONAL"},
            "conditionsModule": {"conditions": ["Condition"]},
            "armsInterventionsModule": {"interventions": [{"name": "Drug"}]}
        }}]});
        let records = normalize_clinical_trials(&trials);
        assert_eq!(records.len(), 1);
        assert_eq!(records[0].record_id, "clinicaltrials:NCT00000001");
    }

    #[test]
    #[ignore = "calls the fixed public PubMed and ClinicalTrials.gov APIs"]
    fn live_public_sources_return_bounded_metadata() {
        let mut value = valid_request();
        value["query"] = serde_json::json!("semaglutide type 2 diabetes");
        value["max_results_per_source"] = serde_json::json!(2);
        value["date_from"] = Value::Null;
        value["date_to"] = Value::Null;
        let request: SearchRequest = serde_json::from_value(value).unwrap();
        let client = client().unwrap();
        let pubmed = search_pubmed(&client, &request).unwrap();
        let trials = search_clinical_trials(&client, &request).unwrap();
        assert_eq!(pubmed.source, "pubmed");
        assert_eq!(trials.source, "clinicaltrials");
        assert!(pubmed.fetched_count <= 2);
        assert!(trials.fetched_count <= 2);
        assert!(!pubmed.response_sha256.is_empty());
        assert!(!trials.response_sha256.is_empty());
    }

    #[cfg(unix)]
    #[test]
    fn output_directory_rejects_symlinks() {
        use std::os::unix::fs::symlink;
        let root = std::env::temp_dir().join(format!("heor-search-symlink-{}", std::process::id()));
        let outside =
            std::env::temp_dir().join(format!("heor-search-outside-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let _ = std::fs::remove_dir_all(&outside);
        std::fs::create_dir_all(&root).unwrap();
        std::fs::create_dir_all(&outside).unwrap();
        symlink(&outside, root.join("heor")).unwrap();
        assert!(ensure_directory(&root, SEARCH_RUN_DIRECTORY).is_err());
        let _ = std::fs::remove_dir_all(&root);
        let _ = std::fs::remove_dir_all(&outside);
    }

    #[test]
    fn app_owned_event_chain_detects_tampering() {
        let root = std::env::temp_dir().join(format!("heor-search-events-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let base = SearchAuthorizationEvent {
            schema_version: 1,
            sequence: 0,
            event_id: "1".repeat(32),
            project_id: "project-1".into(),
            request_sha256: "a".repeat(64),
            sources: vec!["pubmed".into()],
            actor_label: "Human reviewer".into(),
            rationale: "Approved the disclosed query and source.".into(),
            timestamp: 1_700_000_000,
            output_path: "heor/evidence-search-runs/run.json".into(),
            output_sha256: "b".repeat(64),
            assurance: ASSURANCE.into(),
            previous_hash: None,
            event_hash: String::new(),
        };
        append_event(&root, base).unwrap();
        let file = event_file(&root, "project-1").unwrap();
        let changed = std::fs::read_to_string(&file)
            .unwrap()
            .replace("Human reviewer", "Agent");
        std::fs::write(&file, changed).unwrap();
        assert!(read_verified_events(&root, "project-1").is_err());
        let _ = std::fs::remove_dir_all(&root);
    }
}
