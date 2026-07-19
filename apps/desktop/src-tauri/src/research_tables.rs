//! Deterministic, source-bound research tables for AI4HEOR.
//!
//! The Agent prepares a bounded manifest through the conversation. The native
//! app re-reads every declared source, validates every typed cell and writes a
//! formula-free workbook plus one CSV per table. Generation never creates a
//! scientific, submission, reimbursement or release approval.

use crate::research_report::{build_xlsx_workbook, XlsxCell, XlsxSheet};
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, BTreeSet};
use std::io::Write;
#[cfg(test)]
use std::path::PathBuf;
use std::path::{Component, Path};
use tauri::AppHandle;

pub const RESEARCH_TABLES_MANIFEST_PATH: &str = "deliverables/research-tables.json";
pub const RESEARCH_TABLES_XLSX_PATH: &str = "deliverables/research-tables.xlsx";
pub const RESEARCH_TABLES_CSV_DIRECTORY: &str = "deliverables/research-tables";
pub const RESEARCH_TABLES_AUDIT_PATH: &str = "deliverables/research-tables.audit.json";
const SCHEMA_VERSION: &str = "ai4heor-research-tables/v1";
const ENGINE_VERSION: &str = "0.1.0";
const MANIFEST_CAP_BYTES: u64 = 4 * 1024 * 1024;
const SOURCE_CAP_BYTES: u64 = 20 * 1024 * 1024;
const OUTPUT_CAP_BYTES: usize = 50 * 1024 * 1024;
const MAX_TOTAL_ROWS: usize = 50_000;

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct ResearchTablesManifest {
    schema_version: String,
    workbook_id: String,
    title: String,
    language: String,
    prepared_on: String,
    audience: String,
    purpose: String,
    sources: Vec<SourceBinding>,
    tables: Vec<TableSpec>,
    human_review: HumanReview,
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct SourceBinding {
    id: String,
    path: String,
    sha256: String,
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct TableSpec {
    id: String,
    title: String,
    sheet_name: String,
    purpose: String,
    columns: Vec<ColumnSpec>,
    rows: Vec<RowSpec>,
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct ColumnSpec {
    id: String,
    label: String,
    value_type: String,
    #[serde(default)]
    unit: String,
    #[serde(default)]
    nullable: bool,
    #[serde(default)]
    width: Option<f32>,
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct RowSpec {
    row_id: String,
    values: BTreeMap<String, serde_json::Value>,
    basis: String,
    #[serde(default)]
    source_refs: Vec<SourceReference>,
    #[serde(default)]
    note: String,
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct SourceReference {
    source_id: String,
    locator: String,
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct HumanReview {
    status: String,
}

#[derive(Clone, Debug)]
struct LoadedTables {
    manifest: ResearchTablesManifest,
    manifest_raw: Vec<u8>,
    source_raw: BTreeMap<String, Vec<u8>>,
    row_count: usize,
    neutralized_text_count: usize,
    assumption_count: usize,
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ResearchTablesAudit {
    pub complete: bool,
    pub ready_to_generate: bool,
    pub outputs_current: bool,
    pub status: &'static str,
    pub workbook_id: String,
    pub title: String,
    pub manifest_path: &'static str,
    pub xlsx_path: &'static str,
    pub csv_directory: &'static str,
    pub audit_path: &'static str,
    pub manifest_sha256: String,
    pub source_count: usize,
    pub table_count: usize,
    pub row_count: usize,
    pub csv_file_count: usize,
    pub xlsx_sha256: Option<String>,
    pub human_review_status: String,
    pub neutralized_text_count: usize,
    pub errors: Vec<String>,
    pub warnings: Vec<String>,
}

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize, PartialEq, Eq)]
struct GenerationRecord {
    schema_version: String,
    generator: String,
    generator_version: String,
    workbook_id: String,
    manifest_path: String,
    manifest_sha256: String,
    source_hashes: BTreeMap<String, String>,
    xlsx_path: String,
    xlsx_sha256: String,
    csv_directory: String,
    csv_hashes: BTreeMap<String, String>,
    table_count: usize,
    row_count: usize,
    neutralized_text_count: usize,
    human_review_status: String,
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

fn safe_relative(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 240
        && !value.contains('\\')
        && Path::new(value)
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
}

fn resolve_regular(workspace: &Path, relative: &str, cap: u64) -> Result<Vec<u8>, String> {
    if !safe_relative(relative) {
        return Err(format!("{relative} is not a safe workspace-relative path"));
    }
    let root = workspace
        .canonicalize()
        .map_err(|error| format!("workspace unavailable: {error}"))?;
    let mut current = root.clone();
    for component in Path::new(relative).components() {
        let Component::Normal(part) = component else {
            return Err(format!("{relative} is not a safe workspace-relative path"));
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
    if !metadata.is_file() || metadata.len() > cap {
        return Err(format!("{relative} is not a supported regular file"));
    }
    std::fs::read(canonical).map_err(|error| format!("cannot read {relative}: {error}"))
}

fn valid_date_parts(value: &str) -> Option<(i32, u32, u32)> {
    if value.len() != 10 || value.as_bytes()[4] != b'-' || value.as_bytes()[7] != b'-' {
        return None;
    }
    let year = value[0..4].parse::<i32>().ok()?;
    let month = value[5..7].parse::<u32>().ok()?;
    let day = value[8..10].parse::<u32>().ok()?;
    if !(1900..=9999).contains(&year) || !(1..=12).contains(&month) {
        return None;
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
    (1..=days[(month - 1) as usize])
        .contains(&day)
        .then_some((year, month, day))
}

fn days_from_civil(year: i32, month: u32, day: u32) -> i64 {
    let year = year - i32::from(month <= 2);
    let era = if year >= 0 { year } else { year - 399 } / 400;
    let year_of_era = year - era * 400;
    let shifted_month = month as i32 + if month > 2 { -3 } else { 9 };
    let day_of_year = (153 * shifted_month + 2) / 5 + day as i32 - 1;
    let day_of_era = year_of_era * 365 + year_of_era / 4 - year_of_era / 100 + day_of_year;
    (era * 146_097 + day_of_era - 719_468) as i64
}

fn excel_date_serial(value: &str) -> Result<i64, String> {
    let (year, month, day) =
        valid_date_parts(value).ok_or_else(|| format!("invalid ISO date: {value}"))?;
    Ok(days_from_civil(year, month, day) + 25_569)
}

fn formula_like(value: &str) -> bool {
    matches!(
        value.trim_start().chars().next(),
        Some('=' | '+' | '-' | '@')
    )
}

fn validate_cell(column: &ColumnSpec, value: &serde_json::Value) -> Result<(), String> {
    if value.is_null() {
        return column
            .nullable
            .then_some(())
            .ok_or_else(|| format!("column {} does not allow null", column.id));
    }
    match column.value_type.as_str() {
        "text" => value
            .as_str()
            .filter(|text| valid_text(text, 0, 32_767))
            .map(|_| ())
            .ok_or_else(|| format!("column {} requires bounded text", column.id)),
        "integer" => value
            .as_i64()
            .filter(|number| number.unsigned_abs() <= 9_007_199_254_740_991)
            .map(|_| ())
            .ok_or_else(|| format!("column {} requires an exact safe integer", column.id)),
        "number" | "percent" | "currency" => value
            .as_f64()
            .filter(|number| number.is_finite())
            .map(|_| ())
            .ok_or_else(|| format!("column {} requires a finite number", column.id)),
        "boolean" => value
            .as_bool()
            .map(|_| ())
            .ok_or_else(|| format!("column {} requires a boolean", column.id)),
        "date" => value
            .as_str()
            .and_then(valid_date_parts)
            .map(|_| ())
            .ok_or_else(|| format!("column {} requires YYYY-MM-DD", column.id)),
        _ => Err(format!(
            "column {} has unsupported type {}",
            column.id, column.value_type
        )),
    }
}

fn validate_manifest(
    workspace: &Path,
    manifest: ResearchTablesManifest,
    manifest_raw: Vec<u8>,
) -> Result<LoadedTables, Vec<String>> {
    let mut errors = Vec::new();
    if manifest.schema_version != SCHEMA_VERSION {
        errors.push(format!("schema_version must be {SCHEMA_VERSION}"));
    }
    if !safe_id(&manifest.workbook_id) {
        errors.push("workbook_id must be a safe lowercase identifier".into());
    }
    for (name, value, minimum, maximum) in [
        ("title", manifest.title.as_str(), 3, 160),
        ("audience", manifest.audience.as_str(), 2, 160),
        ("purpose", manifest.purpose.as_str(), 8, 500),
    ] {
        if !valid_text(value, minimum, maximum) {
            errors.push(format!("{name} is missing or outside its supported length"));
        }
    }
    if !matches!(manifest.language.as_str(), "zh-CN" | "en") {
        errors.push("language must be zh-CN or en".into());
    }
    if valid_date_parts(&manifest.prepared_on).is_none() {
        errors.push("prepared_on must be a valid YYYY-MM-DD date".into());
    }
    if manifest.human_review.status != "awaiting_human_review" {
        errors.push("human_review.status must remain awaiting_human_review".into());
    }
    if manifest.sources.is_empty() || manifest.sources.len() > 32 {
        errors.push("sources must contain between 1 and 32 items".into());
    }
    if manifest.tables.is_empty() || manifest.tables.len() > 16 {
        errors.push("tables must contain between 1 and 16 items".into());
    }

    let mut source_ids = BTreeSet::new();
    let mut source_paths = BTreeSet::new();
    let mut source_raw = BTreeMap::new();
    for source in &manifest.sources {
        if !safe_id(&source.id) || !source_ids.insert(source.id.clone()) {
            errors.push(format!("source id is invalid or duplicated: {}", source.id));
        }
        if !safe_relative(&source.path)
            || !source_paths.insert(source.path.to_lowercase())
            || source.path == RESEARCH_TABLES_MANIFEST_PATH
            || source.path == RESEARCH_TABLES_XLSX_PATH
            || source.path == RESEARCH_TABLES_AUDIT_PATH
            || source
                .path
                .starts_with(&format!("{RESEARCH_TABLES_CSV_DIRECTORY}/"))
        {
            errors.push(format!(
                "source path is invalid, duplicated or reserved: {}",
                source.path
            ));
            continue;
        }
        if !valid_sha256(&source.sha256) {
            errors.push(format!("source {} has an invalid SHA-256", source.id));
            continue;
        }
        match resolve_regular(workspace, &source.path, SOURCE_CAP_BYTES) {
            Ok(raw) if sha256(&raw) == source.sha256 => {
                source_raw.insert(source.id.clone(), raw);
            }
            Ok(_) => errors.push(format!("source {} SHA-256 does not match", source.id)),
            Err(error) => errors.push(error),
        }
    }

    let mut table_ids = BTreeSet::new();
    let mut sheet_names = BTreeSet::new();
    let mut row_count = 0usize;
    let mut neutralized_text_count = 0usize;
    let mut assumption_count = 0usize;
    for table in &manifest.tables {
        if !safe_id(&table.id) || !table_ids.insert(table.id.clone()) {
            errors.push(format!("table id is invalid or duplicated: {}", table.id));
        }
        if !valid_text(&table.title, 2, 160) || !valid_text(&table.purpose, 5, 300) {
            errors.push(format!(
                "table {} needs a bounded title and purpose",
                table.id
            ));
        }
        let sheet = table.sheet_name.trim();
        if sheet.is_empty()
            || sheet.chars().count() > 31
            || sheet
                .chars()
                .any(|character| "[]:*?/\\".contains(character))
            || !sheet_names.insert(sheet.to_lowercase())
            || sheet.eq_ignore_ascii_case("Readme 说明")
        {
            errors.push(format!(
                "table {} has an invalid or duplicate sheet_name",
                table.id
            ));
        }
        if table.columns.is_empty() || table.columns.len() > 24 {
            errors.push(format!("table {} must contain 1 to 24 columns", table.id));
        }
        if table.rows.len() > 10_000 {
            errors.push(format!("table {} exceeds 10000 rows", table.id));
        }
        row_count = row_count.saturating_add(table.rows.len());
        let mut column_ids = BTreeSet::new();
        for column in &table.columns {
            if !safe_id(&column.id) || !column_ids.insert(column.id.clone()) {
                errors.push(format!(
                    "table {} has an invalid or duplicate column id: {}",
                    table.id, column.id
                ));
            }
            if !valid_text(&column.label, 1, 120) {
                errors.push(format!("column {} needs a bounded label", column.id));
            }
            let numeric = matches!(
                column.value_type.as_str(),
                "integer" | "number" | "percent" | "currency"
            );
            if numeric && !valid_text(&column.unit, 1, 40) {
                errors.push(format!("numeric column {} must declare a unit", column.id));
            }
            if !numeric && !column.unit.is_empty() {
                errors.push(format!(
                    "non-numeric column {} cannot declare a unit",
                    column.id
                ));
            }
            if let Some(width) = column.width {
                if !(8.0..=60.0).contains(&width) {
                    errors.push(format!(
                        "column {} width must be between 8 and 60",
                        column.id
                    ));
                }
            }
            if !matches!(
                column.value_type.as_str(),
                "text" | "integer" | "number" | "percent" | "currency" | "boolean" | "date"
            ) {
                errors.push(format!("column {} has unsupported value_type", column.id));
            }
        }
        let mut row_ids = BTreeSet::new();
        for row in &table.rows {
            if !safe_id(&row.row_id) || !row_ids.insert(row.row_id.clone()) {
                errors.push(format!(
                    "table {} has an invalid or duplicate row_id: {}",
                    table.id, row.row_id
                ));
            }
            let actual = row.values.keys().cloned().collect::<BTreeSet<_>>();
            if actual != column_ids {
                errors.push(format!(
                    "row {} values must exactly match the table columns",
                    row.row_id
                ));
            }
            for column in &table.columns {
                if let Some(value) = row.values.get(&column.id) {
                    if let Err(error) = validate_cell(column, value) {
                        errors.push(format!("row {}: {error}", row.row_id));
                    }
                    if value.as_str().is_some_and(formula_like) {
                        neutralized_text_count += 1;
                    }
                }
            }
            match row.basis.as_str() {
                "evidence" | "analysis_output" => {
                    if row.source_refs.is_empty() {
                        errors.push(format!(
                            "row {} requires at least one source reference",
                            row.row_id
                        ));
                    }
                }
                "assumption" => {
                    assumption_count += 1;
                    if !row.source_refs.is_empty() || !valid_text(&row.note, 5, 500) {
                        errors.push(format!(
                            "assumption row {} needs a note and no source references",
                            row.row_id
                        ));
                    }
                }
                _ => errors.push(format!("row {} has an unsupported basis", row.row_id)),
            }
            for reference in &row.source_refs {
                if !source_ids.contains(&reference.source_id)
                    || !valid_text(&reference.locator, 1, 240)
                {
                    errors.push(format!(
                        "row {} has an invalid source reference",
                        row.row_id
                    ));
                }
            }
            if !row.note.is_empty() && !valid_text(&row.note, 1, 500) {
                errors.push(format!(
                    "row {} note is outside the supported length",
                    row.row_id
                ));
            }
        }
    }
    if row_count > MAX_TOTAL_ROWS {
        errors.push(format!("all tables together exceed {MAX_TOTAL_ROWS} rows"));
    }
    if errors.is_empty() {
        Ok(LoadedTables {
            manifest,
            manifest_raw,
            source_raw,
            row_count,
            neutralized_text_count,
            assumption_count,
        })
    } else {
        Err(errors)
    }
}

fn empty_audit(errors: Vec<String>) -> ResearchTablesAudit {
    ResearchTablesAudit {
        complete: false,
        ready_to_generate: false,
        outputs_current: false,
        status: if errors.is_empty() {
            "missing"
        } else {
            "invalid"
        },
        workbook_id: String::new(),
        title: String::new(),
        manifest_path: RESEARCH_TABLES_MANIFEST_PATH,
        xlsx_path: RESEARCH_TABLES_XLSX_PATH,
        csv_directory: RESEARCH_TABLES_CSV_DIRECTORY,
        audit_path: RESEARCH_TABLES_AUDIT_PATH,
        manifest_sha256: String::new(),
        source_count: 0,
        table_count: 0,
        row_count: 0,
        csv_file_count: 0,
        xlsx_sha256: None,
        human_review_status: "awaiting_human_review".into(),
        neutralized_text_count: 0,
        errors,
        warnings: Vec::new(),
    }
}

fn record_matches(workspace: &Path, loaded: &LoadedTables) -> Option<GenerationRecord> {
    let raw = resolve_regular(workspace, RESEARCH_TABLES_AUDIT_PATH, MANIFEST_CAP_BYTES).ok()?;
    let record: GenerationRecord = serde_json::from_slice(&raw).ok()?;
    if record.schema_version != "0.1.0"
        || record.generator != "ai4heor-native-research-tables"
        || record.generator_version != ENGINE_VERSION
        || record.workbook_id != loaded.manifest.workbook_id
        || record.manifest_path != RESEARCH_TABLES_MANIFEST_PATH
        || record.manifest_sha256 != sha256(&loaded.manifest_raw)
        || record.xlsx_path != RESEARCH_TABLES_XLSX_PATH
        || record.csv_directory != RESEARCH_TABLES_CSV_DIRECTORY
        || record.table_count != loaded.manifest.tables.len()
        || record.row_count != loaded.row_count
        || record.neutralized_text_count != loaded.neutralized_text_count
        || record.human_review_status != "awaiting_human_review"
    {
        return None;
    }
    let expected_sources = loaded
        .source_raw
        .iter()
        .map(|(id, raw)| (id.clone(), sha256(raw)))
        .collect::<BTreeMap<_, _>>();
    (record.source_hashes == expected_sources).then_some(record)
}

fn apply_current_outputs(workspace: &Path, loaded: &LoadedTables, audit: &mut ResearchTablesAudit) {
    let Some(record) = record_matches(workspace, loaded) else {
        return;
    };
    let Ok(xlsx) = resolve_regular(
        workspace,
        RESEARCH_TABLES_XLSX_PATH,
        OUTPUT_CAP_BYTES as u64,
    ) else {
        return;
    };
    if sha256(&xlsx) != record.xlsx_sha256
        || record.csv_hashes.len() != loaded.manifest.tables.len()
    {
        return;
    }
    let csv_directory = workspace.join(RESEARCH_TABLES_CSV_DIRECTORY);
    let Ok(entries) = std::fs::read_dir(csv_directory) else {
        return;
    };
    let mut actual_csv_files = BTreeSet::new();
    for entry in entries {
        let Ok(entry) = entry else {
            return;
        };
        let Ok(metadata) = entry.metadata() else {
            return;
        };
        if !metadata.is_file() {
            return;
        }
        actual_csv_files.insert(entry.file_name().to_string_lossy().to_string());
    }
    if actual_csv_files != record.csv_hashes.keys().cloned().collect() {
        return;
    }
    for table in &loaded.manifest.tables {
        let filename = format!("{}.csv", table.id);
        let Some(expected) = record.csv_hashes.get(&filename) else {
            return;
        };
        let path = format!("{RESEARCH_TABLES_CSV_DIRECTORY}/{filename}");
        let Ok(csv) = resolve_regular(workspace, &path, OUTPUT_CAP_BYTES as u64) else {
            return;
        };
        if sha256(&csv) != *expected {
            return;
        }
    }
    audit.outputs_current = true;
    audit.status = "current";
    audit.xlsx_sha256 = Some(record.xlsx_sha256);
    audit.csv_file_count = record.csv_hashes.len();
}

fn audit_at(workspace: &Path) -> (ResearchTablesAudit, Option<LoadedTables>) {
    let manifest_raw =
        match resolve_regular(workspace, RESEARCH_TABLES_MANIFEST_PATH, MANIFEST_CAP_BYTES) {
            Ok(raw) => raw,
            Err(_) => {
                return (
                    empty_audit(vec![format!("{RESEARCH_TABLES_MANIFEST_PATH} is required")]),
                    None,
                )
            }
        };
    let manifest = match serde_json::from_slice::<ResearchTablesManifest>(&manifest_raw) {
        Ok(value) => value,
        Err(error) => {
            return (
                empty_audit(vec![format!(
                    "research tables manifest is invalid: {error}"
                )]),
                None,
            )
        }
    };
    let loaded = match validate_manifest(workspace, manifest, manifest_raw) {
        Ok(value) => value,
        Err(errors) => return (empty_audit(errors), None),
    };
    let mut warnings = Vec::new();
    if loaded.neutralized_text_count > 0 {
        warnings.push(format!(
            "{} formula-like text values will be prefixed with an apostrophe in CSV files",
            loaded.neutralized_text_count
        ));
    }
    if loaded.assumption_count > 0 {
        warnings.push(format!(
            "{} rows are explicitly marked as assumptions",
            loaded.assumption_count
        ));
    }
    let mut audit = ResearchTablesAudit {
        complete: true,
        ready_to_generate: true,
        outputs_current: false,
        status: "ready",
        workbook_id: loaded.manifest.workbook_id.clone(),
        title: loaded.manifest.title.clone(),
        manifest_path: RESEARCH_TABLES_MANIFEST_PATH,
        xlsx_path: RESEARCH_TABLES_XLSX_PATH,
        csv_directory: RESEARCH_TABLES_CSV_DIRECTORY,
        audit_path: RESEARCH_TABLES_AUDIT_PATH,
        manifest_sha256: sha256(&loaded.manifest_raw),
        source_count: loaded.source_raw.len(),
        table_count: loaded.manifest.tables.len(),
        row_count: loaded.row_count,
        csv_file_count: 0,
        xlsx_sha256: None,
        human_review_status: loaded.manifest.human_review.status.clone(),
        neutralized_text_count: loaded.neutralized_text_count,
        errors: Vec::new(),
        warnings,
    };
    apply_current_outputs(workspace, &loaded, &mut audit);
    (audit, Some(loaded))
}

fn source_refs_text(row: &RowSpec) -> String {
    row.source_refs
        .iter()
        .map(|reference| format!("{}: {}", reference.source_id, reference.locator.trim()))
        .collect::<Vec<_>>()
        .join(" | ")
}

fn value_to_cell(column: &ColumnSpec, value: &serde_json::Value) -> Result<XlsxCell, String> {
    if value.is_null() {
        return Ok(XlsxCell::empty());
    }
    match column.value_type.as_str() {
        "text" => Ok(XlsxCell::text(value.as_str().unwrap_or_default(), 4)),
        "integer" => Ok(XlsxCell::number(
            value.as_i64().unwrap_or_default().to_string(),
        )),
        "number" => Ok(XlsxCell::number_with_style(value.to_string(), 9)),
        "percent" => Ok(XlsxCell::number_with_style(value.to_string(), 10)),
        "currency" => Ok(XlsxCell::number_with_style(value.to_string(), 11)),
        "boolean" => Ok(XlsxCell::boolean(value.as_bool().unwrap_or(false))),
        "date" => Ok(XlsxCell::number_with_style(
            excel_date_serial(value.as_str().unwrap_or_default())?.to_string(),
            12,
        )),
        _ => Err(format!("unsupported column type: {}", column.value_type)),
    }
}

fn build_xlsx(loaded: &LoadedTables) -> Result<Vec<u8>, String> {
    let mut readme_rows = vec![
        vec![XlsxCell::text(&loaded.manifest.title, 1)],
        vec![
            XlsxCell::text("About / 说明", 8),
            XlsxCell::text(
                "This workbook copies typed, source-bound rows without formulas. Every table remains awaiting Human review. / 本工作簿只复制带类型和来源绑定的行，不包含公式；所有表格仍待研究者复核。",
                6,
            ),
        ],
        vec![XlsxCell::empty()],
        vec![XlsxCell::text("Workbook / 工作簿", 2)],
        vec![XlsxCell::text("ID", 8), XlsxCell::text(&loaded.manifest.workbook_id, 4)],
        vec![XlsxCell::text("Purpose / 用途", 8), XlsxCell::text(&loaded.manifest.purpose, 4)],
        vec![XlsxCell::text("Audience / 使用对象", 8), XlsxCell::text(&loaded.manifest.audience, 4)],
        vec![XlsxCell::text("Prepared / 编制日期", 8), XlsxCell::text(&loaded.manifest.prepared_on, 4)],
        vec![
            XlsxCell::text("Review / 复核状态", 8),
            XlsxCell::text("待研究者复核 / awaiting_human_review", 6),
        ],
        vec![XlsxCell::empty()],
        vec![XlsxCell::text("Sources / 来源", 2)],
        vec![XlsxCell::text("ID", 3), XlsxCell::text("Path / 路径", 3), XlsxCell::text("SHA-256", 3)],
    ];
    for source in &loaded.manifest.sources {
        readme_rows.push(vec![
            XlsxCell::text(&source.id, 4),
            XlsxCell::text(&source.path, 4),
            XlsxCell::text(&source.sha256, 7),
        ]);
    }
    let mut sheets = vec![XlsxSheet {
        name: "Readme 说明".into(),
        rows: readme_rows,
        widths: vec![26.0, 62.0, 68.0],
        freeze_rows: 4,
        auto_filter: None,
    }];
    for table in &loaded.manifest.tables {
        let mut rows = vec![
            vec![XlsxCell::text(&table.title, 1)],
            vec![XlsxCell::text(&table.purpose, 6)],
            vec![XlsxCell::empty()],
        ];
        let mut headers = table
            .columns
            .iter()
            .map(|column| {
                let label = if column.unit.is_empty() {
                    column.label.clone()
                } else {
                    format!("{} [{}]", column.label, column.unit)
                };
                XlsxCell::text(label, 3)
            })
            .collect::<Vec<_>>();
        headers.extend([
            XlsxCell::text("Basis / 依据性质", 3),
            XlsxCell::text("Source refs / 来源定位", 3),
            XlsxCell::text("Note / 说明", 3),
        ]);
        rows.push(headers);
        for row in &table.rows {
            let mut cells = table
                .columns
                .iter()
                .map(|column| value_to_cell(column, &row.values[&column.id]))
                .collect::<Result<Vec<_>, _>>()?;
            let basis = match row.basis.as_str() {
                "evidence" => "evidence / 证据",
                "analysis_output" => "analysis_output / 分析输出",
                "assumption" => "assumption / 假设",
                _ => row.basis.as_str(),
            };
            cells.extend([
                XlsxCell::text(basis, 4),
                XlsxCell::text(source_refs_text(row), 4),
                XlsxCell::text(&row.note, 4),
            ]);
            rows.push(cells);
        }
        let mut widths = table
            .columns
            .iter()
            .map(|column| {
                column.width.unwrap_or(match column.value_type.as_str() {
                    "text" => 24.0,
                    "date" => 13.0,
                    "boolean" => 11.0,
                    _ => 16.0,
                })
            })
            .collect::<Vec<_>>();
        widths.extend([18.0, 42.0, 36.0]);
        let last_row = rows.len();
        sheets.push(XlsxSheet {
            name: table.sheet_name.clone(),
            rows,
            widths,
            freeze_rows: 4,
            auto_filter: Some((4, last_row)),
        });
    }
    build_xlsx_workbook(
        &loaded.manifest.title,
        &loaded.manifest.purpose,
        &loaded.manifest.prepared_on,
        &sheets,
    )
}

fn csv_escape(value: &str) -> String {
    let value = if formula_like(value) {
        format!("'{value}")
    } else {
        value.to_string()
    };
    if value.contains([',', '"', '\n', '\r']) {
        format!("\"{}\"", value.replace('"', "\"\""))
    } else {
        value
    }
}

fn csv_value(column: &ColumnSpec, value: &serde_json::Value) -> String {
    if value.is_null() {
        return String::new();
    }
    match column.value_type.as_str() {
        "text" | "date" => csv_escape(value.as_str().unwrap_or_default()),
        "boolean" => value.as_bool().unwrap_or(false).to_string(),
        _ => value.to_string(),
    }
}

fn build_csv(table: &TableSpec) -> Vec<u8> {
    let mut lines = Vec::with_capacity(table.rows.len() + 1);
    let mut headers = table
        .columns
        .iter()
        .map(|column| {
            let label = if column.unit.is_empty() {
                column.label.clone()
            } else {
                format!("{} [{}]", column.label, column.unit)
            };
            csv_escape(&label)
        })
        .collect::<Vec<_>>();
    headers.extend(["_basis".into(), "_source_refs".into(), "_note".into()]);
    lines.push(headers.join(","));
    for row in &table.rows {
        let mut values = table
            .columns
            .iter()
            .map(|column| csv_value(column, &row.values[&column.id]))
            .collect::<Vec<_>>();
        values.extend([
            csv_escape(&row.basis),
            csv_escape(&source_refs_text(row)),
            csv_escape(&row.note),
        ]);
        lines.push(values.join(","));
    }
    let mut output = lines.join("\r\n").into_bytes();
    output.extend_from_slice(b"\r\n");
    output
}

fn write_atomic(path: &Path, bytes: &[u8]) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("cannot create research table output directory: {error}"))?;
    }
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("research-table-output");
    let temporary = path.with_file_name(format!(".{file_name}.tmp"));
    {
        let mut file = std::fs::File::create(&temporary)
            .map_err(|error| format!("cannot stage research table output: {error}"))?;
        file.write_all(bytes)
            .and_then(|_| file.sync_all())
            .map_err(|error| format!("cannot flush research table output: {error}"))?;
    }
    if std::fs::rename(&temporary, path).is_err() {
        let result = std::fs::write(path, bytes)
            .map_err(|error| format!("cannot replace research table output: {error}"));
        let _ = std::fs::remove_file(&temporary);
        result?;
    }
    Ok(())
}

fn existing_outputs_replaceable(workspace: &Path) -> Result<Option<GenerationRecord>, String> {
    let xlsx = workspace.join(RESEARCH_TABLES_XLSX_PATH);
    let csv_directory = workspace.join(RESEARCH_TABLES_CSV_DIRECTORY);
    if !xlsx.exists() && !csv_directory.exists() {
        return Ok(None);
    }
    let raw = std::fs::read(workspace.join(RESEARCH_TABLES_AUDIT_PATH)).map_err(|_| {
        "existing research table outputs have no matching app audit; move or remove them before generating".to_string()
    })?;
    let record: GenerationRecord = serde_json::from_slice(&raw).map_err(|_| {
        "existing research table outputs have an unreadable app audit; move or remove them before generating".to_string()
    })?;
    let xlsx_raw = std::fs::read(&xlsx)
        .map_err(|_| "existing research table workbook is incomplete".to_string())?;
    if sha256(&xlsx_raw) != record.xlsx_sha256 {
        return Err("the existing research table workbook was changed outside AI4HEOR; move or rename it before generating".into());
    }
    let mut actual = BTreeSet::new();
    for entry in std::fs::read_dir(&csv_directory)
        .map_err(|_| "existing research table CSV directory is unavailable".to_string())?
    {
        let entry =
            entry.map_err(|_| "existing research table CSV directory is unreadable".to_string())?;
        let metadata = entry
            .metadata()
            .map_err(|_| "existing research table CSV metadata is unreadable".to_string())?;
        let name = entry.file_name().to_string_lossy().to_string();
        if !metadata.is_file() || !record.csv_hashes.contains_key(&name) {
            return Err("the existing research table CSV directory contains an untracked or non-file entry; move it before generating".into());
        }
        let bytes = std::fs::read(entry.path())
            .map_err(|_| "existing research table CSV is unreadable".to_string())?;
        if sha256(&bytes) != record.csv_hashes[&name] {
            return Err("an existing research table CSV was changed outside AI4HEOR; move or rename it before generating".into());
        }
        actual.insert(name);
    }
    if actual != record.csv_hashes.keys().cloned().collect() {
        return Err("existing research table CSV outputs are incomplete".into());
    }
    Ok(Some(record))
}

fn generate_at(workspace: &Path) -> Result<ResearchTablesAudit, String> {
    let (audit, loaded) = audit_at(workspace);
    let loaded = loaded.ok_or_else(|| audit.errors.join("; "))?;
    if audit.outputs_current {
        return Ok(audit);
    }
    let previous = existing_outputs_replaceable(workspace)?;
    let xlsx = build_xlsx(&loaded)?;
    if xlsx.len() > OUTPUT_CAP_BYTES {
        return Err("generated research table workbook exceeds 50 MiB".into());
    }
    let mut csv_files = BTreeMap::new();
    for table in &loaded.manifest.tables {
        let filename = format!("{}.csv", table.id);
        let bytes = build_csv(table);
        if bytes.len() > OUTPUT_CAP_BYTES {
            return Err(format!("generated CSV {filename} exceeds 50 MiB"));
        }
        csv_files.insert(filename, bytes);
    }
    let record = GenerationRecord {
        schema_version: "0.1.0".into(),
        generator: "ai4heor-native-research-tables".into(),
        generator_version: ENGINE_VERSION.into(),
        workbook_id: loaded.manifest.workbook_id.clone(),
        manifest_path: RESEARCH_TABLES_MANIFEST_PATH.into(),
        manifest_sha256: sha256(&loaded.manifest_raw),
        source_hashes: loaded
            .source_raw
            .iter()
            .map(|(id, raw)| (id.clone(), sha256(raw)))
            .collect(),
        xlsx_path: RESEARCH_TABLES_XLSX_PATH.into(),
        xlsx_sha256: sha256(&xlsx),
        csv_directory: RESEARCH_TABLES_CSV_DIRECTORY.into(),
        csv_hashes: csv_files
            .iter()
            .map(|(name, raw)| (name.clone(), sha256(raw)))
            .collect(),
        table_count: loaded.manifest.tables.len(),
        row_count: loaded.row_count,
        neutralized_text_count: loaded.neutralized_text_count,
        human_review_status: "awaiting_human_review".into(),
    };
    write_atomic(&workspace.join(RESEARCH_TABLES_XLSX_PATH), &xlsx)?;
    for (name, raw) in &csv_files {
        write_atomic(
            &workspace.join(RESEARCH_TABLES_CSV_DIRECTORY).join(name),
            raw,
        )?;
    }
    if let Some(previous) = previous {
        for name in previous.csv_hashes.keys() {
            if !csv_files.contains_key(name) {
                std::fs::remove_file(workspace.join(RESEARCH_TABLES_CSV_DIRECTORY).join(name))
                    .map_err(|error| {
                        format!("cannot remove obsolete audited CSV {name}: {error}")
                    })?;
            }
        }
    }
    let record_raw = serde_json::to_vec_pretty(&record)
        .map_err(|error| format!("cannot serialize research table audit: {error}"))?;
    write_atomic(&workspace.join(RESEARCH_TABLES_AUDIT_PATH), &record_raw)?;
    Ok(audit_at(workspace).0)
}

#[tauri::command(async)]
pub fn audit_research_tables(app: AppHandle) -> Result<ResearchTablesAudit, String> {
    Ok(audit_at(&crate::runtime::workspace_dir(&app)?).0)
}

#[tauri::command(async)]
pub fn generate_research_tables(app: AppHandle) -> Result<ResearchTablesAudit, String> {
    generate_at(&crate::runtime::workspace_dir(&app)?)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn fixture_root(name: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!(
            "ai4heor-research-tables-{name}-{}-{}",
            std::process::id(),
            std::thread::current().name().unwrap_or("test")
        ));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("deliverables")).unwrap();
        std::fs::create_dir_all(root.join("heor/results")).unwrap();
        root
    }

    fn write_fixture(root: &Path) {
        let source = br#"{"delta_cost":12000,"delta_qaly":0.42}"#;
        std::fs::write(root.join("heor/results/base-case.json"), source).unwrap();
        let manifest = serde_json::json!({
            "schema_version": SCHEMA_VERSION,
            "workbook_id": "cea-summary-tables",
            "title": "成本效果分析结果表",
            "language": "zh-CN",
            "prepared_on": "2026-07-20",
            "audience": "项目研究团队",
            "purpose": "整理已审计的基线结果和需要明确标示的分析假设。",
            "sources": [{
                "id": "base-case",
                "path": "heor/results/base-case.json",
                "sha256": sha256(source)
            }],
            "tables": [{
                "id": "base_case",
                "title": "基线分析",
                "sheet_name": "基线分析",
                "purpose": "按策略呈现成本、QALY 和增量结果。",
                "columns": [
                    {"id":"strategy","label":"策略","value_type":"text","width":20},
                    {"id":"cost","label":"总成本","value_type":"currency","unit":"CNY 2026"},
                    {"id":"qaly","label":"QALY","value_type":"number","unit":"QALY"},
                    {"id":"ce_probability","label":"成本效果概率","value_type":"percent","unit":"proportion"},
                    {"id":"run_date","label":"运行日期","value_type":"date"},
                    {"id":"selected","label":"纳入展示","value_type":"boolean"},
                    {"id":"rank","label":"顺序","value_type":"integer","unit":"count"}
                ],
                "rows": [
                    {
                        "row_id":"comparator",
                        "values":{"strategy":"对照","cost":100000,"qaly":1.2,"ce_probability":0.21,"run_date":"2026-07-20","selected":true,"rank":1},
                        "basis":"analysis_output",
                        "source_refs":[{"source_id":"base-case","locator":"base_case.comparator"}],
                        "note":""
                    },
                    {
                        "row_id":"intervention",
                        "values":{"strategy":"=SUM(A1:A2)","cost":112000,"qaly":1.62,"ce_probability":0.79,"run_date":"2026-07-20","selected":true,"rank":2},
                        "basis":"assumption",
                        "source_refs":[],
                        "note":"该展示标签仅用于测试 CSV 公式注入防护。"
                    }
                ]
            }],
            "human_review":{"status":"awaiting_human_review"}
        });
        std::fs::write(
            root.join(RESEARCH_TABLES_MANIFEST_PATH),
            serde_json::to_vec_pretty(&manifest).unwrap(),
        )
        .unwrap();
    }

    #[test]
    fn typed_source_bound_workbook_and_csv_are_deterministic() {
        let root = fixture_root("typed");
        write_fixture(&root);
        let (_, loaded) = audit_at(&root);
        let loaded = loaded.unwrap();
        let first = build_xlsx(&loaded).unwrap();
        let second = build_xlsx(&loaded).unwrap();
        assert_eq!(first, second);
        assert!(first.starts_with(b"PK\x03\x04"));
        assert!(first
            .windows(b"numFmtId=\"166\"".len())
            .any(|part| part == b"numFmtId=\"166\""));
        assert!(first
            .windows("基线分析".as_bytes().len())
            .any(|part| part == "基线分析".as_bytes()));
        assert!(!first.windows(b"<f>".len()).any(|part| part == b"<f>"));

        let generated = generate_at(&root).unwrap();
        assert!(generated.outputs_current);
        assert_eq!(generated.table_count, 1);
        assert_eq!(generated.row_count, 2);
        assert_eq!(generated.neutralized_text_count, 1);
        let csv = std::fs::read_to_string(
            root.join(RESEARCH_TABLES_CSV_DIRECTORY)
                .join("base_case.csv"),
        )
        .unwrap();
        assert!(csv.contains("'=SUM(A1:A2)"));
        assert!(csv.contains("0.79"));
        assert!(csv.contains("base-case: base_case.comparator"));
        if let Some(directory) = std::env::var_os("AI4HEOR_KEEP_TEST_RESEARCH_TABLES") {
            let directory = PathBuf::from(directory);
            std::fs::create_dir_all(&directory).unwrap();
            std::fs::copy(
                root.join(RESEARCH_TABLES_XLSX_PATH),
                directory.join("research-tables.xlsx"),
            )
            .unwrap();
            std::fs::copy(
                root.join(RESEARCH_TABLES_CSV_DIRECTORY)
                    .join("base_case.csv"),
                directory.join("base_case.csv"),
            )
            .unwrap();
        }
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn stale_source_invalid_type_and_human_approval_fail_closed() {
        let root = fixture_root("invalid");
        write_fixture(&root);
        let path = root.join(RESEARCH_TABLES_MANIFEST_PATH);
        let mut manifest: serde_json::Value =
            serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
        manifest["sources"][0]["sha256"] = serde_json::Value::String("0".repeat(64));
        manifest["tables"][0]["columns"][1]["unit"] = serde_json::Value::String(String::new());
        manifest["tables"][0]["rows"][0]["values"]["selected"] = serde_json::json!("yes");
        manifest["human_review"]["status"] = serde_json::json!("approved");
        std::fs::write(&path, serde_json::to_vec_pretty(&manifest).unwrap()).unwrap();
        let audit = audit_at(&root).0;
        assert!(!audit.complete);
        assert!(audit.errors.iter().any(|error| error.contains("SHA-256")));
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("must declare a unit")));
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("requires a boolean")));
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("awaiting_human_review")));
        assert!(generate_at(&root).is_err());
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn changed_outputs_are_never_overwritten() {
        let root = fixture_root("tamper");
        write_fixture(&root);
        generate_at(&root).unwrap();
        let xlsx_path = root.join(RESEARCH_TABLES_XLSX_PATH);
        let mut changed = std::fs::read(&xlsx_path).unwrap();
        changed.push(b'!');
        std::fs::write(&xlsx_path, &changed).unwrap();
        assert!(!audit_at(&root).0.outputs_current);
        let error = generate_at(&root).unwrap_err();
        assert!(error.contains("changed outside AI4HEOR"));
        assert_eq!(std::fs::read(&xlsx_path).unwrap(), changed);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn untracked_csv_files_make_outputs_non_current_and_block_regeneration() {
        let root = fixture_root("extra-csv");
        write_fixture(&root);
        generate_at(&root).unwrap();
        let extra_path = root.join(RESEARCH_TABLES_CSV_DIRECTORY).join("extra.csv");
        std::fs::write(&extra_path, b"untracked\n").unwrap();
        assert!(!audit_at(&root).0.outputs_current);
        let error = generate_at(&root).unwrap_err();
        assert!(error.contains("untracked or non-file entry"));
        assert_eq!(std::fs::read(&extra_path).unwrap(), b"untracked\n");
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn dates_and_csv_escaping_are_stable() {
        assert_eq!(excel_date_serial("1970-01-01").unwrap(), 25_569);
        assert_eq!(excel_date_serial("2026-07-20").unwrap(), 46_223);
        assert!(excel_date_serial("2026-02-29").is_err());
        assert_eq!(csv_escape("plain"), "plain");
        assert_eq!(csv_escape("+cmd"), "'+cmd");
        assert_eq!(csv_escape("a,b"), "\"a,b\"");
        assert_eq!(csv_escape("a\"b"), "\"a\"\"b\"");
    }
}
