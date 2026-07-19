//! Deterministic, source-bound reference formatting for project CSL-JSON metadata.
//!
//! This is deliberately not a generic CSL processor. AI4HEOR owns three small,
//! documented rendering profiles and never loads executable styles or downloads
//! metadata. The researcher remains responsible for checking the target journal.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use std::collections::{HashMap, HashSet};
use std::io::Write;
use std::path::{Component, Path};
use tauri::AppHandle;

pub const PLAN_PATH: &str = "references/citation-plan.json";
pub const LIBRARY_PATH: &str = "references/library.json";
pub const OUTPUT_PATH: &str = "deliverables/references.md";
pub const AUDIT_PATH: &str = "deliverables/references.audit.json";
const ENGINE_VERSION: &str = "0.1.0";
const INPUT_CAP_BYTES: u64 = 10 * 1024 * 1024;
const OUTPUT_CAP_BYTES: usize = 10 * 1024 * 1024;
const MAX_RECORDS: usize = 10_000;
const MAX_CLUSTERS: usize = 10_000;
const SHA256_LENGTH: usize = 64;

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct CitationPlan {
    schema_version: String,
    document_id: String,
    title: String,
    language: String,
    style_id: String,
    library: SourceBinding,
    citations: Vec<CitationCluster>,
    bibliography: BibliographyPlan,
    human_review_status: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct SourceBinding {
    path: String,
    sha256: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct CitationCluster {
    id: String,
    reference_ids: Vec<String>,
    #[serde(default)]
    locator: Option<CitationLocator>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct CitationLocator {
    label: String,
    value: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(deny_unknown_fields)]
struct BibliographyPlan {
    include_uncited: bool,
}

#[derive(Clone, Debug)]
struct ReferenceRecord {
    id: String,
    kind: String,
    title: String,
    authors: Vec<Name>,
    year: Option<i64>,
    container: Option<String>,
    volume: Option<String>,
    issue: Option<String>,
    page: Option<String>,
    publisher: Option<String>,
    publisher_place: Option<String>,
    doi: Option<String>,
    pmid: Option<String>,
    url: Option<String>,
}

#[derive(Clone, Debug)]
struct Name {
    family: Option<String>,
    given: Option<String>,
    literal: Option<String>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct GenerationRecord {
    schema_version: String,
    generator: String,
    generator_version: String,
    document_id: String,
    style_id: String,
    plan_path: String,
    plan_sha256: String,
    library_path: String,
    library_sha256: String,
    output_path: String,
    output_sha256: String,
    citation_count: usize,
    bibliography_count: usize,
    metadata_warning_count: usize,
    human_review_status: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct CitationFormattingAudit {
    pub complete: bool,
    pub ready_to_generate: bool,
    pub output_current: bool,
    pub status: &'static str,
    pub document_id: String,
    pub title: String,
    pub style_id: String,
    pub plan_path: &'static str,
    pub library_path: String,
    pub output_path: &'static str,
    pub audit_path: &'static str,
    pub plan_sha256: String,
    pub library_sha256: String,
    pub output_sha256: Option<String>,
    pub citation_count: usize,
    pub bibliography_count: usize,
    pub metadata_warning_count: usize,
    pub human_review_status: String,
    pub errors: Vec<String>,
    pub warnings: Vec<String>,
}

struct Loaded {
    plan: CitationPlan,
    plan_sha256: String,
    library_sha256: String,
    records: Vec<ReferenceRecord>,
    by_id: HashMap<String, usize>,
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn bounded_text(value: &str, label: &str, maximum: usize) -> Result<(), String> {
    let length = value.chars().count();
    if value.trim().is_empty() || length > maximum {
        return Err(format!("{label} must contain 1 to {maximum} characters"));
    }
    if value
        .chars()
        .any(|character| character.is_control() && !matches!(character, '\t'))
    {
        return Err(format!("{label} contains an unsupported control character"));
    }
    Ok(())
}

fn validate_relative_path(value: &str) -> Result<(), String> {
    let path = Path::new(value);
    if path.is_absolute()
        || path.components().any(|component| {
            matches!(
                component,
                Component::ParentDir | Component::RootDir | Component::Prefix(_)
            )
        })
    {
        return Err("library.path must be a project-relative path".into());
    }
    if value != LIBRARY_PATH {
        return Err(format!("library.path must be {LIBRARY_PATH}"));
    }
    Ok(())
}

fn read_required(workspace: &Path, relative: &str, cap: u64) -> Result<Vec<u8>, String> {
    let root = workspace
        .canonicalize()
        .map_err(|error| format!("workspace unavailable: {error}"))?;
    let path = workspace.join(relative);
    let metadata = std::fs::symlink_metadata(&path)
        .map_err(|error| format!("{relative} unavailable: {error}"))?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(format!("{relative} must be an ordinary project file"));
    }
    if metadata.len() > cap {
        return Err(format!(
            "{relative} exceeds the {} MiB limit",
            cap / 1024 / 1024
        ));
    }
    let canonical = path
        .canonicalize()
        .map_err(|error| format!("{relative} unavailable: {error}"))?;
    if !canonical.starts_with(root) {
        return Err(format!("{relative} resolves outside the workspace"));
    }
    std::fs::read(path).map_err(|error| format!("cannot read {relative}: {error}"))
}

fn read_optional(workspace: &Path, relative: &str, cap: u64) -> Result<Option<Vec<u8>>, String> {
    if !workspace.join(relative).exists() {
        return Ok(None);
    }
    read_required(workspace, relative, cap).map(Some)
}

fn string_field(object: &serde_json::Map<String, Value>, field: &str) -> Option<String> {
    object
        .get(field)
        .and_then(Value::as_str)
        .map(ToOwned::to_owned)
}

fn parse_name(value: &Value, label: &str) -> Result<Name, String> {
    let object = value
        .as_object()
        .ok_or_else(|| format!("{label} must be an object"))?;
    let unknown: Vec<_> = object
        .keys()
        .filter(|key| !matches!(key.as_str(), "family" | "given" | "literal"))
        .collect();
    if !unknown.is_empty() {
        return Err(format!("{label} contains unsupported name fields"));
    }
    let name = Name {
        family: string_field(object, "family"),
        given: string_field(object, "given"),
        literal: string_field(object, "literal"),
    };
    if name.literal.is_some() == name.family.is_some()
        || name.literal.is_some() && name.given.is_some()
    {
        return Err(format!(
            "{label} must contain either literal or family with optional given"
        ));
    }
    for (field, value) in [
        ("family", name.family.as_deref()),
        ("given", name.given.as_deref()),
        ("literal", name.literal.as_deref()),
    ] {
        if let Some(value) = value {
            bounded_text(value, &format!("{label}.{field}"), 500)?;
        }
    }
    Ok(name)
}

fn parse_record(value: &Value, index: usize) -> Result<ReferenceRecord, String> {
    let object = value
        .as_object()
        .ok_or_else(|| format!("records[{index}] must be an object"))?;
    let allowed = [
        "id",
        "type",
        "citation-key",
        "title",
        "container-title",
        "container-title-short",
        "abstract",
        "volume",
        "issue",
        "page",
        "publisher",
        "publisher-place",
        "DOI",
        "PMID",
        "PMCID",
        "ISBN",
        "ISSN",
        "URL",
        "language",
        "keyword",
        "note",
        "genre",
        "author",
        "editor",
        "issued",
        "source_bindings",
        "conflicts",
    ];
    if let Some(field) = object
        .keys()
        .find(|field| !allowed.contains(&field.as_str()))
    {
        return Err(format!(
            "records[{index}] contains unsupported field {field}"
        ));
    }
    let id =
        string_field(object, "id").ok_or_else(|| format!("records[{index}].id is required"))?;
    let kind =
        string_field(object, "type").ok_or_else(|| format!("records[{index}].type is required"))?;
    let title = string_field(object, "title")
        .ok_or_else(|| format!("records[{index}].title is required"))?;
    bounded_text(&id, &format!("records[{index}].id"), 500)?;
    bounded_text(&kind, &format!("records[{index}].type"), 100)?;
    bounded_text(&title, &format!("records[{index}].title"), 2_000)?;
    let authors = object
        .get("author")
        .map(|value| {
            value
                .as_array()
                .ok_or_else(|| format!("records[{index}].author must be an array"))?
                .iter()
                .enumerate()
                .map(|(author_index, name)| {
                    parse_name(name, &format!("records[{index}].author[{author_index}]"))
                })
                .collect::<Result<Vec<_>, _>>()
        })
        .transpose()?
        .unwrap_or_default();
    let year = object
        .get("issued")
        .and_then(|issued| issued.get("date-parts"))
        .and_then(Value::as_array)
        .and_then(|parts| parts.first())
        .and_then(Value::as_array)
        .and_then(|date| date.first())
        .and_then(Value::as_i64);
    let optional = |field: &str| -> Result<Option<String>, String> {
        let value = string_field(object, field);
        if let Some(value) = value.as_deref() {
            bounded_text(value, &format!("records[{index}].{field}"), 2_000)?;
        }
        Ok(value)
    };
    Ok(ReferenceRecord {
        id,
        kind,
        title,
        authors,
        year,
        container: optional("container-title")?,
        volume: optional("volume")?,
        issue: optional("issue")?,
        page: optional("page")?,
        publisher: optional("publisher")?,
        publisher_place: optional("publisher-place")?,
        doi: optional("DOI")?,
        pmid: optional("PMID")?,
        url: optional("URL")?,
    })
}

fn load(workspace: &Path) -> Result<Loaded, String> {
    let plan_raw = read_required(workspace, PLAN_PATH, INPUT_CAP_BYTES)?;
    let plan: CitationPlan = serde_json::from_slice(&plan_raw)
        .map_err(|error| format!("{PLAN_PATH} is invalid: {error}"))?;
    if plan.schema_version != "ai4heor-citation-plan/v1" {
        return Err(format!("{PLAN_PATH} has an unsupported schema_version"));
    }
    for (label, value, maximum) in [
        ("document_id", plan.document_id.as_str(), 200),
        ("title", plan.title.as_str(), 500),
    ] {
        bounded_text(value, label, maximum)?;
    }
    if !matches!(plan.language.as_str(), "zh-Hans" | "en") {
        return Err("language must be zh-Hans or en".into());
    }
    if !matches!(
        plan.style_id.as_str(),
        "ai4heor-cn-medical-numeric-v1" | "ai4heor-vancouver-numeric-v1" | "ai4heor-author-date-v1"
    ) {
        return Err("style_id is not one of the three AI4HEOR built-in profiles".into());
    }
    if plan.human_review_status != "awaiting_human_review" {
        return Err("human_review_status must be awaiting_human_review".into());
    }
    validate_relative_path(&plan.library.path)?;
    if plan.library.sha256.len() != SHA256_LENGTH
        || !plan
            .library
            .sha256
            .bytes()
            .all(|byte| byte.is_ascii_hexdigit())
    {
        return Err("library.sha256 must be a 64-character SHA-256 value".into());
    }
    if plan.citations.is_empty() || plan.citations.len() > MAX_CLUSTERS {
        return Err(format!(
            "citations must contain 1 to {MAX_CLUSTERS} clusters"
        ));
    }
    let mut cluster_ids = HashSet::new();
    for (index, cluster) in plan.citations.iter().enumerate() {
        bounded_text(&cluster.id, &format!("citations[{index}].id"), 200)?;
        if !cluster_ids.insert(cluster.id.as_str()) {
            return Err("citation cluster IDs must be unique".into());
        }
        if cluster.reference_ids.is_empty() || cluster.reference_ids.len() > 100 {
            return Err(format!(
                "citations[{index}].reference_ids must contain 1 to 100 IDs"
            ));
        }
        let mut ids = HashSet::new();
        for reference_id in &cluster.reference_ids {
            bounded_text(
                reference_id,
                &format!("citations[{index}].reference_ids"),
                500,
            )?;
            if !ids.insert(reference_id) {
                return Err(format!(
                    "citations[{index}] repeats reference ID {reference_id}"
                ));
            }
        }
        if let Some(locator) = &cluster.locator {
            if cluster.reference_ids.len() != 1 {
                return Err(format!(
                    "citations[{index}].locator requires exactly one reference"
                ));
            }
            if !matches!(
                locator.label.as_str(),
                "page" | "chapter" | "section" | "figure" | "table" | "supplement"
            ) {
                return Err(format!("citations[{index}].locator.label is unsupported"));
            }
            bounded_text(
                &locator.value,
                &format!("citations[{index}].locator.value"),
                100,
            )?;
        }
    }
    let library_raw = read_required(workspace, &plan.library.path, INPUT_CAP_BYTES)?;
    let library_sha256 = sha256(&library_raw);
    if library_sha256 != plan.library.sha256.to_ascii_lowercase() {
        return Err("reference library changed after the citation plan was prepared".into());
    }
    let library: Value = serde_json::from_slice(&library_raw)
        .map_err(|error| format!("{} is invalid: {error}", plan.library.path))?;
    let object = library
        .as_object()
        .ok_or_else(|| format!("{} must be a JSON object", plan.library.path))?;
    if object.get("schema_version").and_then(Value::as_str) != Some("ai4heor-reference-library/v1")
        || object
            .keys()
            .any(|key| !matches!(key.as_str(), "schema_version" | "records"))
    {
        return Err(format!(
            "{} does not match ai4heor-reference-library/v1",
            plan.library.path
        ));
    }
    let values = object
        .get("records")
        .and_then(Value::as_array)
        .ok_or_else(|| format!("{}.records must be an array", plan.library.path))?;
    if values.is_empty() || values.len() > MAX_RECORDS {
        return Err(format!(
            "reference library must contain 1 to {MAX_RECORDS} records"
        ));
    }
    let records = values
        .iter()
        .enumerate()
        .map(|(index, value)| parse_record(value, index))
        .collect::<Result<Vec<_>, _>>()?;
    let mut by_id = HashMap::new();
    for (index, record) in records.iter().enumerate() {
        if by_id.insert(record.id.clone(), index).is_some() {
            return Err(format!("reference library repeats record ID {}", record.id));
        }
    }
    for cluster in &plan.citations {
        for reference_id in &cluster.reference_ids {
            if !by_id.contains_key(reference_id) {
                return Err(format!(
                    "citation {} references unknown record {reference_id}",
                    cluster.id
                ));
            }
        }
    }
    Ok(Loaded {
        plan,
        plan_sha256: sha256(&plan_raw),
        library_sha256,
        records,
        by_id,
    })
}

fn markdown(value: &str) -> String {
    value
        .replace('\\', "\\\\")
        .replace('`', "\\`")
        .replace('*', "\\*")
        .replace('_', "\\_")
        .replace('[', "\\[")
        .replace(']', "\\]")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

fn initials(given: &str) -> String {
    given
        .split(|character: char| character.is_whitespace() || character == '-')
        .filter_map(|part| part.chars().next())
        .collect::<String>()
}

fn display_name(name: &Name, compact: bool) -> String {
    if let Some(literal) = &name.literal {
        return markdown(literal);
    }
    let family = markdown(name.family.as_deref().unwrap_or(""));
    let Some(given) = name.given.as_deref() else {
        return family;
    };
    if compact {
        format!("{family} {}", markdown(&initials(given)))
    } else {
        format!("{family}, {}", markdown(given))
    }
}

fn author_list(record: &ReferenceRecord, compact: bool) -> String {
    if record.authors.is_empty() {
        return String::new();
    }
    let maximum = if compact { 6 } else { 20 };
    let mut rendered: Vec<_> = record
        .authors
        .iter()
        .take(maximum)
        .map(|name| display_name(name, compact))
        .collect();
    if record.authors.len() > maximum {
        rendered.push("et al.".into());
    }
    rendered.join(", ")
}

fn author_label(record: &ReferenceRecord) -> String {
    let labels: Vec<_> = record
        .authors
        .iter()
        .take(2)
        .map(|name| {
            name.literal
                .as_deref()
                .or(name.family.as_deref())
                .unwrap_or("Anonymous")
                .to_owned()
        })
        .collect();
    match (labels.as_slice(), record.authors.len()) {
        ([], _) => record.title.chars().take(30).collect(),
        ([one], _) => one.clone(),
        ([one, two], 2) => format!("{one} & {two}"),
        ([one, ..], _) => format!("{one} et al."),
    }
}

fn type_code(kind: &str) -> &'static str {
    match kind {
        "article" | "article-journal" | "article-magazine" | "article-newspaper" => "J",
        "book" | "chapter" => "M",
        "report" => "R",
        "standard" => "S",
        "dataset" => "DS",
        "thesis" => "D",
        "webpage" | "post" | "post-weblog" => "EB/OL",
        _ => "Z",
    }
}

fn identifiers(record: &ReferenceRecord) -> String {
    if let Some(doi) = &record.doi {
        format!(" doi:{}", markdown(doi))
    } else if let Some(pmid) = &record.pmid {
        format!(" PMID:{}", markdown(pmid))
    } else if let Some(url) = &record.url {
        format!(" {}", markdown(url))
    } else {
        String::new()
    }
}

fn render_bibliography(record: &ReferenceRecord, style: &str, year_suffix: &str) -> String {
    let year = record
        .year
        .map(|value| value.to_string())
        .unwrap_or_else(|| "n.d.".into());
    let authors_compact = author_list(record, true);
    let authors_long = author_list(record, false);
    let title = markdown(&record.title);
    let container = record
        .container
        .as_deref()
        .map(markdown)
        .unwrap_or_default();
    let volume_issue = match (&record.volume, &record.issue) {
        (Some(volume), Some(issue)) => format!("{}({})", markdown(volume), markdown(issue)),
        (Some(volume), None) => markdown(volume),
        (None, Some(issue)) => format!("({})", markdown(issue)),
        (None, None) => String::new(),
    };
    let pages = record.page.as_deref().map(markdown).unwrap_or_default();
    let publication = if !container.is_empty() {
        container
    } else {
        [
            record.publisher_place.as_deref(),
            record.publisher.as_deref(),
        ]
        .into_iter()
        .flatten()
        .map(markdown)
        .collect::<Vec<_>>()
        .join(": ")
    };
    match style {
        "ai4heor-cn-medical-numeric-v1" => {
            let author_part = if authors_compact.is_empty() {
                String::new()
            } else {
                format!("{authors_compact}. ")
            };
            let publication_part = if publication.is_empty() {
                String::new()
            } else {
                format!(" {publication},")
            };
            let volume_part = if volume_issue.is_empty() {
                String::new()
            } else {
                format!(" {volume_issue}")
            };
            let page_part = if pages.is_empty() {
                String::new()
            } else {
                format!(":{pages}")
            };
            format!(
                "{author_part}{title}\\[{}\\].{publication_part} {year}{volume_part}{page_part}.{}",
                type_code(&record.kind),
                identifiers(record)
            )
            .replace("  ", " ")
        }
        "ai4heor-vancouver-numeric-v1" => {
            let author_part = if authors_compact.is_empty() {
                String::new()
            } else {
                format!("{authors_compact}. ")
            };
            let publication_part = if publication.is_empty() {
                String::new()
            } else {
                format!(" {publication}.")
            };
            let volume_part = if volume_issue.is_empty() {
                String::new()
            } else {
                format!(";{volume_issue}")
            };
            let page_part = if pages.is_empty() {
                String::new()
            } else {
                format!(":{pages}")
            };
            format!(
                "{author_part}{title}.{publication_part} {year}{volume_part}{page_part}.{}",
                identifiers(record)
            )
            .replace("  ", " ")
        }
        _ => {
            let author_part = if authors_long.is_empty() {
                String::new()
            } else {
                format!("{authors_long} ")
            };
            let publication_part = if publication.is_empty() {
                String::new()
            } else {
                format!(" *{publication}*,")
            };
            let volume_part = if volume_issue.is_empty() {
                String::new()
            } else {
                format!(" {volume_issue}")
            };
            let page_part = if pages.is_empty() {
                String::new()
            } else {
                format!(", {pages}")
            };
            format!("{author_part}({year}{year_suffix}). {title}.{publication_part}{volume_part}{page_part}.{}", identifiers(record)).replace("  ", " ")
        }
    }
}

fn locator_label(locator: &CitationLocator, language: &str) -> String {
    let label = if language == "zh-Hans" {
        match locator.label.as_str() {
            "page" => "第",
            "chapter" => "第",
            "section" => "第",
            "figure" => "图",
            "table" => "表",
            "supplement" => "补充材料",
            _ => "",
        }
    } else {
        match locator.label.as_str() {
            "page" => "p.",
            "chapter" => "ch.",
            "section" => "sec.",
            "figure" => "fig.",
            "table" => "table",
            "supplement" => "supp.",
            _ => "",
        }
    };
    let suffix = if language == "zh-Hans"
        && matches!(locator.label.as_str(), "page" | "chapter" | "section")
    {
        match locator.label.as_str() {
            "page" => "页",
            "chapter" => "章",
            "section" => "节",
            _ => "",
        }
    } else {
        ""
    };
    if language == "zh-Hans" {
        format!("{label}{}{suffix}", markdown(&locator.value))
    } else {
        format!("{label} {}", markdown(&locator.value))
    }
}

fn compress_numbers(numbers: &[usize]) -> String {
    let mut sorted = numbers.to_vec();
    sorted.sort_unstable();
    sorted.dedup();
    let mut parts = Vec::new();
    let mut index = 0;
    while index < sorted.len() {
        let start = sorted[index];
        let mut end = start;
        while index + 1 < sorted.len() && sorted[index + 1] == end + 1 {
            index += 1;
            end = sorted[index];
        }
        if end >= start + 2 {
            parts.push(format!("{start}–{end}"));
        } else if end == start + 1 {
            parts.push(start.to_string());
            parts.push(end.to_string());
        } else {
            parts.push(start.to_string());
        }
        index += 1;
    }
    parts.join(",")
}

fn metadata_warnings(records: &[&ReferenceRecord]) -> Vec<String> {
    let mut warnings = Vec::new();
    for record in records {
        let mut missing = Vec::new();
        if record.authors.is_empty() {
            missing.push("author");
        }
        if record.year.is_none() {
            missing.push("issued");
        }
        if record.kind == "article-journal" && record.container.is_none() {
            missing.push("container-title");
        }
        if record.kind == "article-journal" && record.page.is_none() {
            missing.push("page");
        }
        if record.doi.is_none() && record.pmid.is_none() && record.url.is_none() {
            missing.push("DOI/PMID/URL");
        }
        if !missing.is_empty() {
            warnings.push(format!("{}: missing {}", record.id, missing.join(", ")));
        }
    }
    warnings
}

fn render(loaded: &Loaded) -> Result<(Vec<u8>, usize, Vec<String>), String> {
    let mut ordered_ids = Vec::new();
    let mut seen = HashSet::new();
    for cluster in &loaded.plan.citations {
        for reference_id in &cluster.reference_ids {
            if seen.insert(reference_id.clone()) {
                ordered_ids.push(reference_id.clone());
            }
        }
    }
    if loaded.plan.bibliography.include_uncited {
        let mut uncited: Vec<_> = loaded
            .records
            .iter()
            .map(|record| record.id.clone())
            .filter(|id| !seen.contains(id))
            .collect();
        uncited.sort();
        ordered_ids.extend(uncited);
    }
    let author_date = loaded.plan.style_id == "ai4heor-author-date-v1";
    if author_date {
        ordered_ids.sort_by_key(|id| {
            let record = &loaded.records[loaded.by_id[id]];
            (
                author_label(record).to_lowercase(),
                record.year.unwrap_or(0),
                record.title.to_lowercase(),
                id.clone(),
            )
        });
    }
    let records: Vec<_> = ordered_ids
        .iter()
        .map(|id| &loaded.records[loaded.by_id[id]])
        .collect();
    let warnings = metadata_warnings(&records);
    let number_by_id: HashMap<_, _> = ordered_ids
        .iter()
        .enumerate()
        .map(|(index, id)| (id.as_str(), index + 1))
        .collect();
    let mut suffix_by_id: HashMap<&str, String> = HashMap::new();
    if author_date {
        let mut groups: HashMap<(String, Option<i64>), Vec<&str>> = HashMap::new();
        for record in &records {
            groups
                .entry((author_label(record), record.year))
                .or_default()
                .push(&record.id);
        }
        for ids in groups.values_mut() {
            ids.sort();
            if ids.len() > 1 {
                for (index, id) in ids.iter().enumerate() {
                    let suffix = char::from_u32('a' as u32 + index as u32)
                        .map(|value| value.to_string())
                        .unwrap_or_else(|| format!("-{}", index + 1));
                    suffix_by_id.insert(id, suffix);
                }
            }
        }
    }
    let zh = loaded.plan.language == "zh-Hans";
    let mut output = String::new();
    output.push_str(&format!("# {}\n\n", markdown(&loaded.plan.title)));
    output.push_str(if zh {
        "> 本文件由 AI4HEOR 根据已校验的本地文献库确定性生成。内置版式用于研究写作，不代表目标期刊已经验收；提交前须由研究者逐条核对。\n\n"
    } else {
        "> AI4HEOR generated this file deterministically from the validated local reference library. The built-in profile supports research writing; it is not journal acceptance or compliance certification. Human review is required before submission.\n\n"
    });
    output.push_str(if zh {
        "## 正文引用\n\n"
    } else {
        "## In-text citations\n\n"
    });
    for cluster in &loaded.plan.citations {
        let citation = if author_date {
            let labels = cluster
                .reference_ids
                .iter()
                .map(|id| {
                    let record = &loaded.records[loaded.by_id[id]];
                    let year = record
                        .year
                        .map(|value| value.to_string())
                        .unwrap_or_else(|| {
                            if zh {
                                "无日期".into()
                            } else {
                                "n.d.".into()
                            }
                        });
                    format!(
                        "{}, {}{}",
                        markdown(&author_label(record)),
                        year,
                        suffix_by_id.get(id.as_str()).cloned().unwrap_or_default()
                    )
                })
                .collect::<Vec<_>>()
                .join("; ");
            format!("({labels})")
        } else {
            let numbers = cluster
                .reference_ids
                .iter()
                .map(|id| number_by_id[id.as_str()])
                .collect::<Vec<_>>();
            format!("[{}]", compress_numbers(&numbers))
        };
        let locator = cluster
            .locator
            .as_ref()
            .map(|value| format!(", {}", locator_label(value, &loaded.plan.language)))
            .unwrap_or_default();
        output.push_str(&format!(
            "- `{}`: {}{}\n",
            markdown(&cluster.id),
            citation,
            locator
        ));
    }
    output.push_str(if zh {
        "\n## 参考文献\n\n"
    } else {
        "\n## References\n\n"
    });
    for (index, record) in records.iter().enumerate() {
        let entry = render_bibliography(
            record,
            &loaded.plan.style_id,
            suffix_by_id
                .get(record.id.as_str())
                .map(String::as_str)
                .unwrap_or(""),
        );
        if author_date {
            output.push_str(&format!("- {entry}\n"));
        } else {
            output.push_str(&format!("{}. {entry}\n", index + 1));
        }
    }
    if !warnings.is_empty() {
        output.push_str(if zh {
            "\n## 待核对的文献数据\n\n"
        } else {
            "\n## Metadata requiring review\n\n"
        });
        for warning in &warnings {
            output.push_str(&format!("- {}\n", markdown(warning)));
        }
    }
    output.push_str(if zh {
        "\n## 生成依据\n\n"
    } else {
        "\n## Generation basis\n\n"
    });
    output.push_str(&format!(
        "- `{}`: `{}`\n",
        loaded.plan.library.path, loaded.library_sha256
    ));
    output.push_str(&format!("- `{PLAN_PATH}`: `{}`\n", loaded.plan_sha256));
    output.push_str(&format!("- style: `{}`\n", loaded.plan.style_id));
    output.push_str(if zh {
        "- 状态：待研究者核对\n"
    } else {
        "- Status: awaiting Human review\n"
    });
    if output.len() > OUTPUT_CAP_BYTES {
        return Err("generated reference output exceeds the 10 MiB limit".into());
    }
    Ok((output.into_bytes(), records.len(), warnings))
}

fn empty_audit() -> CitationFormattingAudit {
    CitationFormattingAudit {
        complete: false,
        ready_to_generate: false,
        output_current: false,
        status: "missing",
        document_id: String::new(),
        title: String::new(),
        style_id: String::new(),
        plan_path: PLAN_PATH,
        library_path: LIBRARY_PATH.into(),
        output_path: OUTPUT_PATH,
        audit_path: AUDIT_PATH,
        plan_sha256: String::new(),
        library_sha256: String::new(),
        output_sha256: None,
        citation_count: 0,
        bibliography_count: 0,
        metadata_warning_count: 0,
        human_review_status: "awaiting_human_review".into(),
        errors: Vec::new(),
        warnings: Vec::new(),
    }
}

fn audit_at(workspace: &Path) -> CitationFormattingAudit {
    let mut audit = empty_audit();
    let loaded = match load(workspace) {
        Ok(loaded) => loaded,
        Err(error) => {
            audit.status = if workspace.join(PLAN_PATH).exists() {
                "invalid"
            } else {
                "missing"
            };
            audit.errors.push(error);
            return audit;
        }
    };
    let (expected_output, bibliography_count, warnings) = match render(&loaded) {
        Ok(value) => value,
        Err(error) => {
            audit.status = "invalid";
            audit.errors.push(error);
            return audit;
        }
    };
    audit.complete = true;
    audit.ready_to_generate = true;
    audit.status = "ready_to_generate";
    audit.document_id = loaded.plan.document_id.clone();
    audit.title = loaded.plan.title.clone();
    audit.style_id = loaded.plan.style_id.clone();
    audit.library_path = loaded.plan.library.path.clone();
    audit.plan_sha256 = loaded.plan_sha256.clone();
    audit.library_sha256 = loaded.library_sha256.clone();
    audit.citation_count = loaded.plan.citations.len();
    audit.bibliography_count = bibliography_count;
    audit.metadata_warning_count = warnings.len();
    audit.warnings = warnings;
    let output = read_optional(workspace, OUTPUT_PATH, OUTPUT_CAP_BYTES as u64)
        .ok()
        .flatten();
    let record = read_optional(workspace, AUDIT_PATH, INPUT_CAP_BYTES)
        .ok()
        .flatten()
        .and_then(|raw| serde_json::from_slice::<GenerationRecord>(&raw).ok());
    if let (Some(output), Some(record)) = (output, record) {
        let output_sha256 = sha256(&output);
        let current = output == expected_output
            && record.schema_version == "ai4heor-citation-formatting/v1"
            && record.generator == "ai4heor-citation-formatting"
            && record.generator_version == ENGINE_VERSION
            && record.document_id == loaded.plan.document_id
            && record.style_id == loaded.plan.style_id
            && record.plan_path == PLAN_PATH
            && record.plan_sha256 == loaded.plan_sha256
            && record.library_path == loaded.plan.library.path
            && record.library_sha256 == loaded.library_sha256
            && record.output_path == OUTPUT_PATH
            && record.output_sha256 == output_sha256
            && record.citation_count == loaded.plan.citations.len()
            && record.bibliography_count == bibliography_count
            && record.metadata_warning_count == audit.metadata_warning_count
            && record.human_review_status == "awaiting_human_review";
        if current {
            audit.output_current = true;
            audit.status = "generated_current";
            audit.output_sha256 = Some(output_sha256);
        }
    }
    audit
}

fn write_atomic(workspace: &Path, relative: &str, raw: &[u8]) -> Result<(), String> {
    let root = workspace
        .canonicalize()
        .map_err(|error| format!("workspace unavailable: {error}"))?;
    let path = workspace.join(relative);
    let parent = path
        .parent()
        .ok_or_else(|| format!("{relative} has no parent"))?;
    std::fs::create_dir_all(parent)
        .map_err(|error| format!("cannot create {}: {error}", parent.display()))?;
    let canonical_parent = parent
        .canonicalize()
        .map_err(|error| format!("{} unavailable: {error}", parent.display()))?;
    if !canonical_parent.starts_with(root) {
        return Err(format!("{relative} resolves outside the workspace"));
    }
    if let Ok(metadata) = std::fs::symlink_metadata(&path) {
        if metadata.file_type().is_symlink() {
            return Err(format!("{relative} is a symbolic link"));
        }
    }
    let temporary = parent.join(format!(
        ".{}.{}.tmp",
        path.file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("references"),
        std::process::id()
    ));
    let mut file = std::fs::File::create(&temporary)
        .map_err(|error| format!("cannot prepare {relative}: {error}"))?;
    file.write_all(raw)
        .and_then(|()| file.sync_all())
        .map_err(|error| format!("cannot write {relative}: {error}"))?;
    std::fs::rename(&temporary, &path)
        .map_err(|error| format!("cannot replace {relative}: {error}"))
}

fn existing_outputs_replaceable(workspace: &Path) -> Result<(), String> {
    let record_raw = read_optional(workspace, AUDIT_PATH, INPUT_CAP_BYTES)?;
    let Some(record_raw) = record_raw else {
        if workspace.join(OUTPUT_PATH).exists() {
            return Err(format!("{OUTPUT_PATH} exists without an AI4HEOR generation record; move or rename it before generating"));
        }
        return Ok(());
    };
    let record: GenerationRecord = serde_json::from_slice(&record_raw)
        .map_err(|error| format!("{AUDIT_PATH} cannot authorize replacement: {error}"))?;
    if let Some(output) = read_optional(workspace, OUTPUT_PATH, OUTPUT_CAP_BYTES as u64)? {
        if sha256(&output) != record.output_sha256 {
            return Err(format!(
                "{OUTPUT_PATH} changed outside AI4HEOR; move or rename it before replacing it"
            ));
        }
    }
    Ok(())
}

fn generate_at(workspace: &Path) -> Result<CitationFormattingAudit, String> {
    let loaded = load(workspace)?;
    let (output, bibliography_count, warnings) = render(&loaded)?;
    if audit_at(workspace).output_current {
        return Ok(audit_at(workspace));
    }
    existing_outputs_replaceable(workspace)?;
    let record = GenerationRecord {
        schema_version: "ai4heor-citation-formatting/v1".into(),
        generator: "ai4heor-citation-formatting".into(),
        generator_version: ENGINE_VERSION.into(),
        document_id: loaded.plan.document_id,
        style_id: loaded.plan.style_id,
        plan_path: PLAN_PATH.into(),
        plan_sha256: loaded.plan_sha256,
        library_path: loaded.plan.library.path,
        library_sha256: loaded.library_sha256,
        output_path: OUTPUT_PATH.into(),
        output_sha256: sha256(&output),
        citation_count: loaded.plan.citations.len(),
        bibliography_count,
        metadata_warning_count: warnings.len(),
        human_review_status: "awaiting_human_review".into(),
    };
    let record_raw = serde_json::to_vec_pretty(&record)
        .map_err(|error| format!("cannot serialize citation audit: {error}"))?;
    write_atomic(workspace, OUTPUT_PATH, &output)?;
    write_atomic(workspace, AUDIT_PATH, &record_raw)?;
    Ok(audit_at(workspace))
}

#[tauri::command(async)]
pub fn audit_citation_formatting(app: AppHandle) -> Result<CitationFormattingAudit, String> {
    Ok(audit_at(&crate::runtime::workspace_dir(&app)?))
}

#[tauri::command(async)]
pub fn generate_citation_formatting(app: AppHandle) -> Result<CitationFormattingAudit, String> {
    generate_at(&crate::runtime::workspace_dir(&app)?)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::path::PathBuf;
    use std::sync::atomic::{AtomicU64, Ordering};
    use std::time::{SystemTime, UNIX_EPOCH};

    static WORKSPACE_SEQUENCE: AtomicU64 = AtomicU64::new(0);

    struct TestWorkspace(PathBuf);

    impl TestWorkspace {
        fn path(&self) -> &Path {
            &self.0
        }
    }

    impl Drop for TestWorkspace {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.0);
        }
    }

    fn workspace() -> TestWorkspace {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let sequence = WORKSPACE_SEQUENCE.fetch_add(1, Ordering::Relaxed);
        let path = std::env::temp_dir().join(format!(
            "ai4heor-citations-{}-{nonce}-{sequence}",
            std::process::id()
        ));
        std::fs::create_dir_all(&path).unwrap();
        TestWorkspace(path)
    }

    fn prepare(root: &Path, style: &str) {
        std::fs::create_dir_all(root.join("references")).unwrap();
        let library = serde_json::json!({
            "schema_version": "ai4heor-reference-library/v1",
            "records": [
                {
                    "id": "smith-2023", "type": "article-journal", "title": "Economic evaluation methods",
                    "author": [{"family": "Smith", "given": "Alice"}, {"family": "Li", "given": "Ming"}],
                    "issued": {"date-parts": [[2023]]}, "container-title": "Value in Health",
                    "volume": "26", "issue": "2", "page": "10-18", "DOI": "10.1000/example"
                },
                {
                    "id": "who-2024", "type": "report", "title": "Health technology assessment",
                    "author": [{"literal": "World Health Organization"}], "issued": {"date-parts": [[2024]]},
                    "publisher": "WHO", "URL": "https://example.org/hta"
                }
            ]
        });
        let library_raw = serde_json::to_vec_pretty(&library).unwrap();
        std::fs::write(root.join(LIBRARY_PATH), &library_raw).unwrap();
        let plan = serde_json::json!({
            "schema_version": "ai4heor-citation-plan/v1",
            "document_id": "study-report", "title": "研究报告参考文献", "language": "zh-Hans",
            "style_id": style,
            "library": {"path": LIBRARY_PATH, "sha256": sha256(&library_raw)},
            "citations": [
                {"id": "methods", "reference_ids": ["smith-2023"], "locator": {"label": "page", "value": "12"}},
                {"id": "context", "reference_ids": ["smith-2023", "who-2024"]}
            ],
            "bibliography": {"include_uncited": false},
            "human_review_status": "awaiting_human_review"
        });
        std::fs::write(
            root.join(PLAN_PATH),
            serde_json::to_vec_pretty(&plan).unwrap(),
        )
        .unwrap();
    }

    #[test]
    fn renders_source_bound_numeric_references_and_audits_current_output() {
        let temp = workspace();
        prepare(temp.path(), "ai4heor-cn-medical-numeric-v1");
        let before = audit_at(temp.path());
        assert!(before.ready_to_generate);
        assert!(!before.output_current);
        let generated = generate_at(temp.path()).unwrap();
        assert!(generated.output_current);
        assert_eq!(generated.citation_count, 2);
        assert_eq!(generated.bibliography_count, 2);
        let output = std::fs::read_to_string(temp.path().join(OUTPUT_PATH)).unwrap();
        assert!(output.contains("`methods`: [1], 第12页"));
        assert!(output.contains("`context`: [1,2]"));
        assert!(output.contains("Economic evaluation methods\\[J\\]"));
        assert!(output.contains("提交前须由研究者逐条核对"));
    }

    #[test]
    fn renders_author_date_without_changing_the_library() {
        let temp = workspace();
        prepare(temp.path(), "ai4heor-author-date-v1");
        let library_before = std::fs::read(temp.path().join(LIBRARY_PATH)).unwrap();
        generate_at(temp.path()).unwrap();
        let output = std::fs::read_to_string(temp.path().join(OUTPUT_PATH)).unwrap();
        assert!(output.contains("(Smith & Li, 2023)"));
        assert!(output.contains("(Smith & Li, 2023; World Health Organization, 2024)"));
        assert_eq!(
            library_before,
            std::fs::read(temp.path().join(LIBRARY_PATH)).unwrap()
        );
    }

    #[test]
    fn fails_closed_when_the_bound_library_changes() {
        let temp = workspace();
        prepare(temp.path(), "ai4heor-vancouver-numeric-v1");
        std::fs::write(temp.path().join(LIBRARY_PATH), b"{}\n").unwrap();
        let audit = audit_at(temp.path());
        assert!(!audit.complete);
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("changed after")));
    }

    #[test]
    fn preserves_a_human_edited_output() {
        let temp = workspace();
        prepare(temp.path(), "ai4heor-vancouver-numeric-v1");
        generate_at(temp.path()).unwrap();
        std::fs::write(temp.path().join(OUTPUT_PATH), "human edit\n").unwrap();
        let error = generate_at(temp.path()).unwrap_err();
        assert!(error.contains("changed outside AI4HEOR"));
    }

    #[test]
    fn rejects_unknown_styles_and_unknown_reference_ids() {
        let temp = workspace();
        prepare(temp.path(), "third-party-style");
        let audit = audit_at(temp.path());
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("three AI4HEOR built-in")));

        prepare(temp.path(), "ai4heor-vancouver-numeric-v1");
        let path = temp.path().join(PLAN_PATH);
        let mut plan: Value = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
        plan["citations"][0]["reference_ids"][0] = Value::String("missing".into());
        std::fs::write(path, serde_json::to_vec_pretty(&plan).unwrap()).unwrap();
        let audit = audit_at(temp.path());
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("unknown record missing")));
    }
}
