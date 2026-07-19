//! Deterministic, source-bound DOCX/PDF generation for an AI4HEOR report.
//!
//! The Agent prepares a small manifest. The native app validates the current
//! HEOR report package, re-reads the bound Markdown, and renders both files.
//! Export is a communication step; it never creates scientific or release
//! approval.

use printpdf::{
    Color, FontId, Mm, Op, PaintMode, ParsedFont, PdfDocument, PdfFontHandle, PdfPage,
    PdfSaveOptions, Point, Pt, Rect, Rgb, TextItem,
};
use sha2::{Digest, Sha256};
use std::collections::BTreeMap;
use std::io::Write;
use std::path::{Component, Path, PathBuf};
use tauri::AppHandle;

pub const REPORT_EXPORT_MANIFEST_PATH: &str = "deliverables/heor-report-export.json";
pub const REPORT_DOCX_OUTPUT_PATH: &str = "deliverables/heor-report.docx";
pub const REPORT_PDF_OUTPUT_PATH: &str = "deliverables/heor-report.pdf";
pub const REPORT_XLSX_OUTPUT_PATH: &str = "deliverables/heor-report.xlsx";
pub const REPORT_EXPORT_AUDIT_PATH: &str = "deliverables/heor-report.audit.json";
const MANIFEST_CAP_BYTES: u64 = 1024 * 1024;
const SOURCE_CAP_BYTES: u64 = 5 * 1024 * 1024;
const OUTPUT_CAP_BYTES: usize = 50 * 1024 * 1024;
const ENGINE_VERSION: &str = "0.2.0";
const WORKBOOK_SHEET_COUNT: usize = 5;
const FONT_NAME: &str = "Source Han Sans CN";
const FONT_VERSION: &str = "2.005R";
const FONT_LICENSE: &str = "OFL-1.1";
const FONT_SHA256: &str = "e2bc8a2e7f37474b774fff8db758681ece40bb6947a90d571bce9dd60671a8e4";
const DOCX_FONT_KEY: &str = "E2BC8A2E-7F37-474B-774F-FF8DB758681E";
const PDF_FONT_BYTES: &[u8] = include_bytes!(
    "../../../../runtime/assets/fonts/source-han-sans-2.005R/SourceHanSansCN-Regular.otf"
);

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct ReportExportManifest {
    schema_version: String,
    document_id: String,
    title: String,
    #[serde(default)]
    subtitle: String,
    language: String,
    prepared_on: String,
    audience: String,
    purpose: String,
    style: String,
    report_package: BoundSource,
    report_document: BoundSource,
    human_review: HumanReview,
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct BoundSource {
    path: String,
    sha256: String,
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct HumanReview {
    status: String,
}

#[derive(Clone, Debug)]
struct LoadedReport {
    manifest: ReportExportManifest,
    manifest_raw: Vec<u8>,
    package_raw: Vec<u8>,
    report_raw: Vec<u8>,
    blocks: Vec<Block>,
    table_count: usize,
}

#[derive(Clone, Debug, PartialEq, Eq)]
enum Block {
    Heading { level: u8, text: String },
    Paragraph(String),
    Bullet(String),
    Numbered(String),
    Quote(String),
    Code(String),
    Rule,
    Table(Vec<Vec<String>>),
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ResearchReportAudit {
    pub complete: bool,
    pub ready_to_generate: bool,
    pub outputs_current: bool,
    pub status: &'static str,
    pub document_id: String,
    pub title: String,
    pub manifest_path: &'static str,
    pub docx_path: &'static str,
    pub pdf_path: &'static str,
    pub xlsx_path: &'static str,
    pub audit_path: &'static str,
    pub manifest_sha256: String,
    pub report_package_sha256: String,
    pub report_document_sha256: String,
    pub docx_sha256: Option<String>,
    pub pdf_sha256: Option<String>,
    pub xlsx_sha256: Option<String>,
    pub block_count: usize,
    pub table_count: usize,
    pub workbook_sheet_count: usize,
    pub pdf_page_count: usize,
    pub human_review_status: String,
    pub font_name: &'static str,
    pub font_version: &'static str,
    pub font_license: &'static str,
    pub font_sha256: &'static str,
    pub errors: Vec<String>,
}

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize, PartialEq, Eq)]
struct GenerationRecord {
    schema_version: String,
    generator: String,
    generator_version: String,
    document_id: String,
    manifest_path: String,
    manifest_sha256: String,
    source_hashes: BTreeMap<String, String>,
    docx_path: String,
    docx_sha256: String,
    pdf_path: String,
    pdf_sha256: String,
    #[serde(default)]
    xlsx_path: Option<String>,
    #[serde(default)]
    xlsx_sha256: Option<String>,
    block_count: usize,
    table_count: usize,
    #[serde(default)]
    workbook_sheet_count: usize,
    pdf_page_count: usize,
    human_review_status: String,
    font_name: String,
    font_version: String,
    font_license: String,
    font_sha256: String,
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn valid_text(value: &str, minimum: usize, maximum: usize) -> bool {
    let value = value.trim();
    let length = value.chars().count();
    (minimum..=maximum).contains(&length)
        && !value
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
    value.len() == 10
        && value.as_bytes()[4] == b'-'
        && value.as_bytes()[7] == b'-'
        && value
            .bytes()
            .enumerate()
            .all(|(index, byte)| matches!(index, 4 | 7) || byte.is_ascii_digit())
}

fn safe_relative(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 240
        && !value.contains('\\')
        && Path::new(value)
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
}

fn resolve_regular(
    workspace: &Path,
    relative: &str,
    cap: u64,
) -> Result<(PathBuf, Vec<u8>), String> {
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
        return Err(format!("{relative} resolves outside the workspace"));
    }
    let metadata = std::fs::metadata(&canonical)
        .map_err(|error| format!("{relative} unavailable: {error}"))?;
    if !metadata.is_file() || metadata.len() > cap {
        return Err(format!(
            "{relative} must be a regular file no larger than {} MiB",
            cap / (1024 * 1024)
        ));
    }
    let raw =
        std::fs::read(&canonical).map_err(|error| format!("{relative} unavailable: {error}"))?;
    Ok((canonical, raw))
}

fn clean_inline(value: &str) -> String {
    let mut cleaned = value
        .replace("**", "")
        .replace("__", "")
        .replace('`', "")
        .trim()
        .to_string();
    while let Some(open) = cleaned.find('[') {
        let Some(middle_relative) = cleaned[open..].find("](") else {
            break;
        };
        let middle = open + middle_relative;
        let Some(close_relative) = cleaned[middle + 2..].find(')') else {
            break;
        };
        let close = middle + 2 + close_relative;
        let label = cleaned[open + 1..middle].to_string();
        let target = cleaned[middle + 2..close].to_string();
        cleaned.replace_range(open..=close, &format!("{label}（{target}）"));
    }
    cleaned
}

fn join_soft(left: &mut String, right: &str) {
    if left.is_empty() {
        left.push_str(right);
        return;
    }
    let separate = left
        .chars()
        .last()
        .zip(right.chars().next())
        .is_some_and(|(a, b)| a.is_ascii_alphanumeric() && b.is_ascii_alphanumeric());
    if separate {
        left.push(' ');
    }
    left.push_str(right);
}

fn table_cells(line: &str) -> Vec<String> {
    line.trim()
        .trim_matches('|')
        .split('|')
        .map(clean_inline)
        .collect()
}

fn table_separator(line: &str) -> bool {
    let cells = table_cells(line);
    !cells.is_empty()
        && cells.iter().all(|cell| {
            let cell = cell.trim().trim_matches(':');
            cell.len() >= 3 && cell.bytes().all(|byte| byte == b'-')
        })
}

fn parse_markdown(raw: &[u8]) -> Result<(Vec<Block>, usize), String> {
    let text = std::str::from_utf8(raw).map_err(|_| "heor/report.md must be UTF-8")?;
    if text.contains('\0') {
        return Err("heor/report.md contains a NUL byte".into());
    }
    let lines = text.lines().collect::<Vec<_>>();
    let mut blocks = Vec::new();
    let mut paragraph = String::new();
    let mut table_count = 0usize;
    let mut index = 0usize;
    let mut in_code = false;
    let mut code = String::new();

    let flush_paragraph = |blocks: &mut Vec<Block>, paragraph: &mut String| {
        if !paragraph.trim().is_empty() {
            blocks.push(Block::Paragraph(clean_inline(paragraph)));
            paragraph.clear();
        }
    };

    while index < lines.len() {
        let line = lines[index].trim_end_matches('\r');
        let trimmed = line.trim();
        if trimmed.starts_with("```") {
            flush_paragraph(&mut blocks, &mut paragraph);
            if in_code {
                blocks.push(Block::Code(code.trim_end().to_string()));
                code.clear();
            }
            in_code = !in_code;
            index += 1;
            continue;
        }
        if in_code {
            if !code.is_empty() {
                code.push('\n');
            }
            code.push_str(line);
            index += 1;
            continue;
        }
        if trimmed.starts_with("<!-- report-section:") && trimmed.ends_with("-->") {
            flush_paragraph(&mut blocks, &mut paragraph);
            index += 1;
            continue;
        }
        if trimmed.starts_with('<') && trimmed.ends_with('>') {
            return Err(format!(
                "unsupported raw HTML in heor/report.md at line {}",
                index + 1
            ));
        }
        if trimmed.is_empty() {
            flush_paragraph(&mut blocks, &mut paragraph);
            index += 1;
            continue;
        }
        if trimmed == "---" || trimmed == "***" {
            flush_paragraph(&mut blocks, &mut paragraph);
            blocks.push(Block::Rule);
            index += 1;
            continue;
        }
        if trimmed.starts_with('|') && index + 1 < lines.len() && table_separator(lines[index + 1])
        {
            flush_paragraph(&mut blocks, &mut paragraph);
            let header = table_cells(trimmed);
            if header.is_empty() || header.len() > 8 {
                return Err(format!(
                    "table at line {} must have 1 to 8 columns",
                    index + 1
                ));
            }
            let mut rows = vec![header];
            index += 2;
            while index < lines.len() && lines[index].trim().starts_with('|') {
                let row = table_cells(lines[index]);
                if row.len() != rows[0].len() {
                    return Err(format!(
                        "table row at line {} has the wrong column count",
                        index + 1
                    ));
                }
                if row.iter().any(|cell| cell.chars().count() > 1_000) {
                    return Err(format!(
                        "table cell at line {} exceeds 1000 characters",
                        index + 1
                    ));
                }
                rows.push(row);
                if rows.len() > 200 {
                    return Err(format!("table at line {} exceeds 200 rows", index + 1));
                }
                index += 1;
            }
            table_count += 1;
            blocks.push(Block::Table(rows));
            continue;
        }
        let hashes = trimmed.bytes().take_while(|byte| *byte == b'#').count();
        if (1..=6).contains(&hashes) && trimmed.as_bytes().get(hashes) == Some(&b' ') {
            flush_paragraph(&mut blocks, &mut paragraph);
            let text = clean_inline(&trimmed[hashes + 1..]);
            if !valid_text(&text, 1, 300) {
                return Err(format!(
                    "heading at line {} is empty or too long",
                    index + 1
                ));
            }
            blocks.push(Block::Heading {
                level: hashes.min(3) as u8,
                text,
            });
            index += 1;
            continue;
        }
        if let Some(value) = trimmed
            .strip_prefix("- ")
            .or_else(|| trimmed.strip_prefix("* "))
            .or_else(|| trimmed.strip_prefix("+ "))
        {
            flush_paragraph(&mut blocks, &mut paragraph);
            blocks.push(Block::Bullet(clean_inline(value)));
            index += 1;
            continue;
        }
        let digit_count = trimmed.bytes().take_while(u8::is_ascii_digit).count();
        if digit_count > 0 && trimmed[digit_count..].starts_with(". ") {
            flush_paragraph(&mut blocks, &mut paragraph);
            blocks.push(Block::Numbered(clean_inline(&trimmed[digit_count + 2..])));
            index += 1;
            continue;
        }
        if let Some(value) = trimmed.strip_prefix("> ") {
            flush_paragraph(&mut blocks, &mut paragraph);
            blocks.push(Block::Quote(clean_inline(value)));
            index += 1;
            continue;
        }
        join_soft(&mut paragraph, trimmed);
        index += 1;
    }
    if in_code {
        return Err("heor/report.md contains an unclosed code fence".into());
    }
    flush_paragraph(&mut blocks, &mut paragraph);
    if blocks.is_empty() {
        return Err("heor/report.md has no renderable content".into());
    }
    if blocks.len() > 1_500 {
        return Err("heor/report.md exceeds 1500 renderable blocks".into());
    }
    let text_count = blocks
        .iter()
        .map(|block| match block {
            Block::Heading { text, .. }
            | Block::Paragraph(text)
            | Block::Bullet(text)
            | Block::Numbered(text)
            | Block::Quote(text)
            | Block::Code(text) => text.chars().count(),
            Block::Table(rows) => rows.iter().flatten().map(|cell| cell.chars().count()).sum(),
            Block::Rule => 0,
        })
        .sum::<usize>();
    if text_count > 500_000 {
        return Err("heor/report.md exceeds 500000 renderable characters".into());
    }
    Ok((blocks, table_count))
}

fn empty_audit(manifest_sha256: String, errors: Vec<String>) -> ResearchReportAudit {
    ResearchReportAudit {
        complete: false,
        ready_to_generate: false,
        outputs_current: false,
        status: "invalid",
        document_id: String::new(),
        title: String::new(),
        manifest_path: REPORT_EXPORT_MANIFEST_PATH,
        docx_path: REPORT_DOCX_OUTPUT_PATH,
        pdf_path: REPORT_PDF_OUTPUT_PATH,
        xlsx_path: REPORT_XLSX_OUTPUT_PATH,
        audit_path: REPORT_EXPORT_AUDIT_PATH,
        manifest_sha256,
        report_package_sha256: String::new(),
        report_document_sha256: String::new(),
        docx_sha256: None,
        pdf_sha256: None,
        xlsx_sha256: None,
        block_count: 0,
        table_count: 0,
        workbook_sheet_count: 0,
        pdf_page_count: 0,
        human_review_status: String::new(),
        font_name: FONT_NAME,
        font_version: FONT_VERSION,
        font_license: FONT_LICENSE,
        font_sha256: FONT_SHA256,
        errors,
    }
}

fn load_manifest(workspace: &Path) -> (ResearchReportAudit, Option<LoadedReport>) {
    let (_, manifest_raw) =
        match resolve_regular(workspace, REPORT_EXPORT_MANIFEST_PATH, MANIFEST_CAP_BYTES) {
            Ok(value) => value,
            Err(error) => return (empty_audit(String::new(), vec![error]), None),
        };
    let manifest_sha = sha256(&manifest_raw);
    let manifest: ReportExportManifest = match serde_json::from_slice(&manifest_raw) {
        Ok(value) => value,
        Err(error) => {
            return (
                empty_audit(
                    manifest_sha,
                    vec![format!("export manifest is invalid: {error}")],
                ),
                None,
            )
        }
    };
    let mut errors = Vec::new();
    if manifest.schema_version != "0.1.0" {
        errors.push("schema_version must be 0.1.0".into());
    }
    if !safe_id(&manifest.document_id) {
        errors.push("document_id must be a lowercase safe identifier".into());
    }
    for (field, value, minimum, maximum) in [
        ("title", manifest.title.as_str(), 1, 200),
        ("subtitle", manifest.subtitle.as_str(), 0, 300),
        ("audience", manifest.audience.as_str(), 1, 500),
        ("purpose", manifest.purpose.as_str(), 1, 500),
    ] {
        if !valid_text(value, minimum, maximum) {
            errors.push(format!("{field} is empty or outside its review bound"));
        }
    }
    if !matches!(manifest.language.as_str(), "zh-Hans" | "zh-Hant" | "en") {
        errors.push("language must be zh-Hans, zh-Hant, or en".into());
    }
    if !valid_date(&manifest.prepared_on) {
        errors.push("prepared_on must be YYYY-MM-DD".into());
    }
    if manifest.style != "ai4heor-formal-report" {
        errors.push("style must be ai4heor-formal-report".into());
    }
    if manifest.human_review.status != "awaiting_human_review" {
        errors.push("human_review.status must be awaiting_human_review".into());
    }
    if manifest.report_package.path != crate::heor_reporting::REPORT_PACKAGE_PATH {
        errors.push("report_package.path must be heor/report-package.json".into());
    }
    if manifest.report_document.path != crate::heor_reporting::REPORT_DOCUMENT_PATH {
        errors.push("report_document.path must be heor/report.md".into());
    }
    for (name, source) in [
        ("report_package", &manifest.report_package),
        ("report_document", &manifest.report_document),
    ] {
        if !valid_sha256(&source.sha256) {
            errors.push(format!("{name}.sha256 must be lowercase SHA-256"));
        }
    }

    let package_raw = resolve_regular(workspace, &manifest.report_package.path, SOURCE_CAP_BYTES)
        .map(|(_, raw)| raw)
        .map_err(|error| errors.push(error))
        .ok();
    let report_raw = resolve_regular(workspace, &manifest.report_document.path, SOURCE_CAP_BYTES)
        .map(|(_, raw)| raw)
        .map_err(|error| errors.push(error))
        .ok();
    if let Some(raw) = package_raw.as_ref() {
        if sha256(raw) != manifest.report_package.sha256 {
            errors.push("report_package SHA-256 does not match current bytes".into());
        }
    }
    if let Some(raw) = report_raw.as_ref() {
        if sha256(raw) != manifest.report_document.sha256 {
            errors.push("report_document SHA-256 does not match current bytes".into());
        }
    }
    let reporting = crate::heor_reporting::audit_report_package(workspace);
    match reporting {
        Ok(audit) if audit.complete => {
            if audit.report_package_sha256 != manifest.report_package.sha256 {
                errors.push("manifest does not bind the current complete report package".into());
            }
            if audit.binding_hashes.get("report_document") != Some(&manifest.report_document.sha256)
            {
                errors.push(
                    "manifest report_document does not match the report-package binding".into(),
                );
            }
        }
        Ok(audit) => errors.extend(audit.errors),
        Err(error) => errors.push(format!("report package audit failed: {error}")),
    }
    let parsed = report_raw
        .as_deref()
        .map(parse_markdown)
        .transpose()
        .map_err(|error| errors.push(error))
        .ok()
        .flatten();
    if sha256(PDF_FONT_BYTES) != FONT_SHA256 {
        errors.push("bundled PDF font does not match the admitted SHA-256".into());
    }
    let Some(package_raw) = package_raw else {
        return (empty_audit(manifest_sha, errors), None);
    };
    let Some(report_raw) = report_raw else {
        return (empty_audit(manifest_sha, errors), None);
    };
    let Some((blocks, table_count)) = parsed else {
        return (empty_audit(manifest_sha, errors), None);
    };
    let mut audit = ResearchReportAudit {
        complete: errors.is_empty(),
        ready_to_generate: errors.is_empty(),
        outputs_current: false,
        status: if errors.is_empty() {
            "ready_to_generate"
        } else {
            "invalid"
        },
        document_id: manifest.document_id.clone(),
        title: manifest.title.clone(),
        manifest_path: REPORT_EXPORT_MANIFEST_PATH,
        docx_path: REPORT_DOCX_OUTPUT_PATH,
        pdf_path: REPORT_PDF_OUTPUT_PATH,
        xlsx_path: REPORT_XLSX_OUTPUT_PATH,
        audit_path: REPORT_EXPORT_AUDIT_PATH,
        manifest_sha256: manifest_sha,
        report_package_sha256: sha256(&package_raw),
        report_document_sha256: sha256(&report_raw),
        docx_sha256: None,
        pdf_sha256: None,
        xlsx_sha256: None,
        block_count: blocks.len(),
        table_count,
        workbook_sheet_count: 0,
        pdf_page_count: 0,
        human_review_status: manifest.human_review.status.clone(),
        font_name: FONT_NAME,
        font_version: FONT_VERSION,
        font_license: FONT_LICENSE,
        font_sha256: FONT_SHA256,
        errors,
    };
    let loaded = LoadedReport {
        manifest,
        manifest_raw,
        package_raw,
        report_raw,
        blocks,
        table_count,
    };
    apply_current_outputs(workspace, &loaded, &mut audit);
    (audit, Some(loaded))
}

fn apply_current_outputs(workspace: &Path, loaded: &LoadedReport, audit: &mut ResearchReportAudit) {
    let record = resolve_regular(workspace, REPORT_EXPORT_AUDIT_PATH, 1024 * 1024)
        .ok()
        .and_then(|(_, raw)| serde_json::from_slice::<GenerationRecord>(&raw).ok());
    let docx = resolve_regular(workspace, REPORT_DOCX_OUTPUT_PATH, OUTPUT_CAP_BYTES as u64).ok();
    let pdf = resolve_regular(workspace, REPORT_PDF_OUTPUT_PATH, OUTPUT_CAP_BYTES as u64).ok();
    let xlsx = resolve_regular(workspace, REPORT_XLSX_OUTPUT_PATH, OUTPUT_CAP_BYTES as u64).ok();
    let (Some(record), Some((_, docx)), Some((_, pdf)), Some((_, xlsx))) =
        (record, docx, pdf, xlsx)
    else {
        return;
    };
    let expected_sources = BTreeMap::from([
        ("report_document".into(), sha256(&loaded.report_raw)),
        ("report_package".into(), sha256(&loaded.package_raw)),
    ]);
    let xlsx_hash = sha256(&xlsx);
    let current = record.schema_version == "0.2.0"
        && record.generator == "ai4heor-native-report"
        && record.generator_version == ENGINE_VERSION
        && record.document_id == loaded.manifest.document_id
        && record.manifest_path == REPORT_EXPORT_MANIFEST_PATH
        && record.manifest_sha256 == sha256(&loaded.manifest_raw)
        && record.source_hashes == expected_sources
        && record.docx_path == REPORT_DOCX_OUTPUT_PATH
        && record.docx_sha256 == sha256(&docx)
        && record.pdf_path == REPORT_PDF_OUTPUT_PATH
        && record.pdf_sha256 == sha256(&pdf)
        && record.xlsx_path.as_deref() == Some(REPORT_XLSX_OUTPUT_PATH)
        && record.xlsx_sha256.as_deref() == Some(xlsx_hash.as_str())
        && record.block_count == loaded.blocks.len()
        && record.table_count == loaded.table_count
        && record.workbook_sheet_count == WORKBOOK_SHEET_COUNT
        && record.human_review_status == "awaiting_human_review"
        && record.font_name == FONT_NAME
        && record.font_version == FONT_VERSION
        && record.font_license == FONT_LICENSE
        && record.font_sha256 == FONT_SHA256;
    if current {
        audit.outputs_current = true;
        audit.status = "generated_current";
        audit.docx_sha256 = Some(record.docx_sha256);
        audit.pdf_sha256 = Some(record.pdf_sha256);
        audit.xlsx_sha256 = record.xlsx_sha256;
        audit.pdf_page_count = record.pdf_page_count;
        audit.workbook_sheet_count = record.workbook_sheet_count;
    }
}

fn xml_escape(value: &str) -> String {
    value
        .replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

fn word_run(text: &str, bold: bool, size_half_points: u16, color: &str) -> String {
    let bold_xml = if bold { "<w:b/>" } else { "" };
    format!(
        "<w:r><w:rPr><w:rFonts w:ascii=\"Source Han Sans CN\" w:hAnsi=\"Source Han Sans CN\" w:eastAsia=\"Source Han Sans CN\" w:cs=\"Source Han Sans CN\"/>{bold_xml}<w:color w:val=\"{color}\"/><w:sz w:val=\"{size_half_points}\"/><w:szCs w:val=\"{size_half_points}\"/></w:rPr><w:t xml:space=\"preserve\">{}</w:t></w:r>",
        xml_escape(text)
    )
}

fn word_paragraph(
    text: &str,
    style: &str,
    bold: bool,
    size_half_points: u16,
    color: &str,
    before: u16,
    after: u16,
    line: u16,
    numbering: Option<u8>,
) -> String {
    let numbering_xml = numbering.map_or_else(String::new, |num_id| {
        format!("<w:numPr><w:ilvl w:val=\"0\"/><w:numId w:val=\"{num_id}\"/></w:numPr>")
    });
    let keep = if style.starts_with("Heading") {
        "<w:keepNext/>"
    } else {
        ""
    };
    format!(
        "<w:p><w:pPr><w:pStyle w:val=\"{style}\"/>{keep}{numbering_xml}<w:spacing w:before=\"{before}\" w:after=\"{after}\" w:line=\"{line}\" w:lineRule=\"auto\"/></w:pPr>{}</w:p>",
        word_run(text, bold, size_half_points, color)
    )
}

fn word_table(rows: &[Vec<String>]) -> String {
    let columns = rows.first().map_or(1, Vec::len).max(1);
    let width = 9026usize;
    let base = width / columns;
    let widths = (0..columns)
        .map(|index| {
            if index + 1 == columns {
                width - base * index
            } else {
                base
            }
        })
        .collect::<Vec<_>>();
    let grid = widths
        .iter()
        .map(|value| format!("<w:gridCol w:w=\"{value}\"/>"))
        .collect::<String>();
    let body = rows
        .iter()
        .enumerate()
        .map(|(row_index, row)| {
            let header = if row_index == 0 { "<w:tblHeader/>" } else { "" };
            let cells = row
                .iter()
                .zip(&widths)
                .map(|(cell, width)| {
                    let fill = if row_index == 0 {
                        "<w:shd w:val=\"clear\" w:color=\"auto\" w:fill=\"E8EEF5\"/>"
                    } else {
                        ""
                    };
                    format!(
                        "<w:tc><w:tcPr><w:tcW w:w=\"{width}\" w:type=\"dxa\"/>{fill}<w:tcMar><w:top w:w=\"80\" w:type=\"dxa\"/><w:start w:w=\"120\" w:type=\"dxa\"/><w:bottom w:w=\"80\" w:type=\"dxa\"/><w:end w:w=\"120\" w:type=\"dxa\"/></w:tcMar></w:tcPr>{}</w:tc>",
                        word_paragraph(cell, "TableText", row_index == 0, 18, "172033", 0, 0, 260, None)
                    )
                })
                .collect::<String>();
            format!("<w:tr><w:trPr>{header}<w:cantSplit/></w:trPr>{cells}</w:tr>")
        })
        .collect::<String>();
    format!(
        "<w:tbl><w:tblPr><w:tblW w:w=\"9026\" w:type=\"dxa\"/><w:tblInd w:w=\"120\" w:type=\"dxa\"/><w:tblLayout w:type=\"fixed\"/><w:tblBorders><w:top w:val=\"single\" w:sz=\"4\" w:color=\"B8C2CC\"/><w:left w:val=\"single\" w:sz=\"4\" w:color=\"B8C2CC\"/><w:bottom w:val=\"single\" w:sz=\"4\" w:color=\"B8C2CC\"/><w:right w:val=\"single\" w:sz=\"4\" w:color=\"B8C2CC\"/><w:insideH w:val=\"single\" w:sz=\"4\" w:color=\"D7DCE2\"/><w:insideV w:val=\"single\" w:sz=\"4\" w:color=\"D7DCE2\"/></w:tblBorders></w:tblPr><w:tblGrid>{grid}</w:tblGrid>{body}</w:tbl>"
    )
}

fn xor_docx_font_prefix(font: &mut [u8]) {
    let compact = DOCX_FONT_KEY.replace('-', "");
    let mut key = [0u8; 16];
    for (index, byte) in key.iter_mut().enumerate() {
        *byte = u8::from_str_radix(&compact[index * 2..index * 2 + 2], 16)
            .expect("DOCX font key is a fixed hexadecimal GUID");
    }
    key.reverse();
    for (index, byte) in font.iter_mut().take(32).enumerate() {
        *byte ^= key[index % key.len()];
    }
}

fn obfuscated_docx_font() -> Vec<u8> {
    let mut font = PDF_FONT_BYTES.to_vec();
    xor_docx_font_prefix(&mut font);
    font
}

fn build_docx(loaded: &LoadedReport) -> Result<Vec<u8>, String> {
    let mut body = String::new();
    body.push_str(&word_paragraph(
        &loaded.manifest.title,
        "Title",
        true,
        48,
        "172033",
        0,
        100,
        280,
        None,
    ));
    if !loaded.manifest.subtitle.trim().is_empty() {
        body.push_str(&word_paragraph(
            &loaded.manifest.subtitle,
            "Subtitle",
            false,
            26,
            "5B6573",
            0,
            240,
            280,
            None,
        ));
    }
    let metadata = vec![
        vec![
            "编制日期 / Prepared on".into(),
            loaded.manifest.prepared_on.clone(),
        ],
        vec![
            "面向对象 / Audience".into(),
            loaded.manifest.audience.clone(),
        ],
        vec!["用途 / Purpose".into(), loaded.manifest.purpose.clone()],
        vec![
            "复核状态 / Review status".into(),
            "待研究者复核 / Awaiting human review".into(),
        ],
    ];
    body.push_str(&word_table(&metadata));
    body.push_str(&word_paragraph(
        "本文件由 AI4HEOR 根据当前已绑定报告包生成。生成文件不代表方法学质量、科研结论有效性、期刊接受、监管认可、支付决策或对外发布批准。",
        "Notice",
        false,
        19,
        "7A4B00",
        160,
        180,
        280,
        None,
    ));
    for block in &loaded.blocks {
        match block {
            Block::Heading { level, text } => {
                let (style, size, color, before, after) = match level {
                    1 => ("Heading1", 32, "2E5D7B", 320, 160),
                    2 => ("Heading2", 26, "2E5D7B", 240, 120),
                    _ => ("Heading3", 23, "1F4D78", 160, 80),
                };
                body.push_str(&word_paragraph(text, style, true, size, color, before, after, 280, None));
            }
            Block::Paragraph(text) => body.push_str(&word_paragraph(
                text, "Normal", false, 21, "172033", 0, 120, 290, None,
            )),
            Block::Bullet(text) => body.push_str(&word_paragraph(
                text, "ListBullet", false, 21, "172033", 0, 100, 280, Some(1),
            )),
            Block::Numbered(text) => body.push_str(&word_paragraph(
                text, "ListNumber", false, 21, "172033", 0, 100, 280, Some(2),
            )),
            Block::Quote(text) => body.push_str(&format!(
                "<w:p><w:pPr><w:pStyle w:val=\"Quote\"/><w:ind w:left=\"360\"/><w:spacing w:before=\"80\" w:after=\"120\" w:line=\"280\" w:lineRule=\"auto\"/><w:pBdr><w:left w:val=\"single\" w:sz=\"18\" w:space=\"8\" w:color=\"D3623B\"/></w:pBdr></w:pPr>{}</w:p>",
                word_run(text, false, 20, "4E5968")
            )),
            Block::Code(text) => body.push_str(&word_paragraph(
                text, "Code", false, 18, "2D3748", 80, 120, 260, None,
            )),
            Block::Rule => body.push_str("<w:p><w:pPr><w:spacing w:before=\"100\" w:after=\"100\"/><w:pBdr><w:bottom w:val=\"single\" w:sz=\"6\" w:space=\"1\" w:color=\"D7DCE2\"/></w:pBdr></w:pPr></w:p>"),
            Block::Table(rows) => body.push_str(&word_table(rows)),
        }
    }
    body.push_str("<w:p><w:r><w:br w:type=\"page\"/></w:r></w:p>");
    body.push_str(&word_paragraph(
        "附录：生成与来源记录 / Generation and source record",
        "Heading2",
        true,
        26,
        "2E5D7B",
        240,
        100,
        280,
        None,
    ));
    body.push_str(&word_table(&[
        vec!["记录项 / Record".into(), "值 / Value".into()],
        vec![
            "文档标识 / Document ID".into(),
            loaded.manifest.document_id.clone(),
        ],
        vec![
            "复核状态 / Review status".into(),
            "待研究者复核 / Awaiting human review".into(),
        ],
        vec![
            "生成器 / Generator".into(),
            format!("AI4HEOR native report renderer {ENGINE_VERSION}"),
        ],
        vec![
            "嵌入字体 / Embedded font".into(),
            format!("{FONT_NAME} {FONT_VERSION} · {FONT_LICENSE}"),
        ],
        vec!["报告包 SHA-256".into(), sha256(&loaded.package_raw)],
        vec!["报告正文 SHA-256".into(), sha256(&loaded.report_raw)],
        vec!["生成清单 SHA-256".into(), sha256(&loaded.manifest_raw)],
    ]));

    let document = format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><w:document xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"><w:body>{body}<w:sectPr><w:headerReference w:type=\"default\" r:id=\"rId1\"/><w:footerReference w:type=\"default\" r:id=\"rId2\"/><w:pgSz w:w=\"11906\" w:h=\"16838\"/><w:pgMar w:top=\"1440\" w:right=\"1440\" w:bottom=\"1440\" w:left=\"1440\" w:header=\"708\" w:footer=\"708\" w:gutter=\"0\"/><w:cols w:space=\"708\"/><w:docGrid w:linePitch=\"312\"/></w:sectPr></w:body></w:document>"
    );
    let styles = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><w:styles xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii=\"Source Han Sans CN\" w:hAnsi=\"Source Han Sans CN\" w:eastAsia=\"Source Han Sans CN\" w:cs=\"Source Han Sans CN\"/><w:sz w:val=\"21\"/><w:szCs w:val=\"21\"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after=\"120\" w:line=\"290\" w:lineRule=\"auto\"/></w:pPr></w:pPrDefault></w:docDefaults><w:style w:type=\"paragraph\" w:default=\"1\" w:styleId=\"Normal\"><w:name w:val=\"Normal\"/></w:style><w:style w:type=\"paragraph\" w:styleId=\"Title\"><w:name w:val=\"Title\"/><w:basedOn w:val=\"Normal\"/></w:style><w:style w:type=\"paragraph\" w:styleId=\"Subtitle\"><w:name w:val=\"Subtitle\"/><w:basedOn w:val=\"Normal\"/></w:style><w:style w:type=\"paragraph\" w:styleId=\"Heading1\"><w:name w:val=\"heading 1\"/><w:basedOn w:val=\"Normal\"/><w:outlineLvl w:val=\"0\"/></w:style><w:style w:type=\"paragraph\" w:styleId=\"Heading2\"><w:name w:val=\"heading 2\"/><w:basedOn w:val=\"Normal\"/><w:outlineLvl w:val=\"1\"/></w:style><w:style w:type=\"paragraph\" w:styleId=\"Heading3\"><w:name w:val=\"heading 3\"/><w:basedOn w:val=\"Normal\"/><w:outlineLvl w:val=\"2\"/></w:style><w:style w:type=\"paragraph\" w:styleId=\"ListBullet\"><w:name w:val=\"List Bullet\"/><w:basedOn w:val=\"Normal\"/></w:style><w:style w:type=\"paragraph\" w:styleId=\"ListNumber\"><w:name w:val=\"List Number\"/><w:basedOn w:val=\"Normal\"/></w:style><w:style w:type=\"paragraph\" w:styleId=\"Quote\"><w:name w:val=\"Quote\"/><w:basedOn w:val=\"Normal\"/></w:style><w:style w:type=\"paragraph\" w:styleId=\"Code\"><w:name w:val=\"Code\"/><w:basedOn w:val=\"Normal\"/><w:rPr><w:rFonts w:ascii=\"Courier New\" w:hAnsi=\"Courier New\" w:eastAsia=\"Source Han Sans CN\"/></w:rPr></w:style><w:style w:type=\"paragraph\" w:styleId=\"Notice\"><w:name w:val=\"Notice\"/><w:basedOn w:val=\"Normal\"/></w:style><w:style w:type=\"paragraph\" w:styleId=\"TableText\"><w:name w:val=\"Table Text\"/><w:basedOn w:val=\"Normal\"/></w:style><w:style w:type=\"paragraph\" w:styleId=\"SourceNote\"><w:name w:val=\"Source Note\"/><w:basedOn w:val=\"Normal\"/></w:style></w:styles>";
    let numbering = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><w:numbering xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:abstractNum w:abstractNumId=\"0\"><w:multiLevelType w:val=\"singleLevel\"/><w:lvl w:ilvl=\"0\"><w:start w:val=\"1\"/><w:numFmt w:val=\"bullet\"/><w:lvlText w:val=\"•\"/><w:lvlJc w:val=\"left\"/><w:pPr><w:tabs><w:tab w:val=\"num\" w:pos=\"720\"/></w:tabs><w:ind w:left=\"720\" w:hanging=\"360\"/></w:pPr></w:lvl></w:abstractNum><w:abstractNum w:abstractNumId=\"1\"><w:multiLevelType w:val=\"singleLevel\"/><w:lvl w:ilvl=\"0\"><w:start w:val=\"1\"/><w:numFmt w:val=\"decimal\"/><w:lvlText w:val=\"%1.\"/><w:lvlJc w:val=\"left\"/><w:pPr><w:tabs><w:tab w:val=\"num\" w:pos=\"720\"/></w:tabs><w:ind w:left=\"720\" w:hanging=\"360\"/></w:pPr></w:lvl></w:abstractNum><w:num w:numId=\"1\"><w:abstractNumId w:val=\"0\"/></w:num><w:num w:numId=\"2\"><w:abstractNumId w:val=\"1\"/></w:num></w:numbering>";
    let header = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><w:hdr xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:p><w:pPr><w:pBdr><w:bottom w:val=\"single\" w:sz=\"4\" w:space=\"4\" w:color=\"D7DCE2\"/></w:pBdr></w:pPr><w:r><w:rPr><w:color w:val=\"697386\"/><w:sz w:val=\"17\"/></w:rPr><w:t>AI4HEOR · HEOR Research Report · Awaiting Human Review</w:t></w:r></w:p></w:hdr>";
    let footer = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><w:ftr xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:p><w:pPr><w:jc w:val=\"right\"/></w:pPr><w:r><w:rPr><w:color w:val=\"697386\"/><w:sz w:val=\"17\"/></w:rPr><w:t>AI4HEOR · 第 </w:t></w:r><w:fldSimple w:instr=\"PAGE\"><w:r><w:rPr><w:color w:val=\"697386\"/><w:sz w:val=\"17\"/></w:rPr><w:t>1</w:t></w:r></w:fldSimple><w:r><w:rPr><w:color w:val=\"697386\"/><w:sz w:val=\"17\"/></w:rPr><w:t> 页</w:t></w:r></w:p></w:ftr>";
    let relationships = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/header\" Target=\"header1.xml\"/><Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer\" Target=\"footer1.xml\"/><Relationship Id=\"rId3\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles\" Target=\"styles.xml\"/><Relationship Id=\"rId4\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering\" Target=\"numbering.xml\"/><Relationship Id=\"rId5\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings\" Target=\"settings.xml\"/><Relationship Id=\"rId6\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/fontTable\" Target=\"fontTable.xml\"/></Relationships>";
    let root_relationships = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"word/document.xml\"/><Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties\" Target=\"docProps/core.xml\"/><Relationship Id=\"rId3\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties\" Target=\"docProps/app.xml\"/></Relationships>";
    let content_types = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"><Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/><Default Extension=\"xml\" ContentType=\"application/xml\"/><Default Extension=\"odttf\" ContentType=\"application/vnd.openxmlformats-officedocument.obfuscatedFont\"/><Override PartName=\"/word/document.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml\"/><Override PartName=\"/word/styles.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml\"/><Override PartName=\"/word/numbering.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml\"/><Override PartName=\"/word/settings.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml\"/><Override PartName=\"/word/fontTable.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.fontTable+xml\"/><Override PartName=\"/word/header1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml\"/><Override PartName=\"/word/footer1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml\"/><Override PartName=\"/docProps/core.xml\" ContentType=\"application/vnd.openxmlformats-package.core-properties+xml\"/><Override PartName=\"/docProps/app.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.extended-properties+xml\"/></Types>";
    let core = format!("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><cp:coreProperties xmlns:cp=\"http://schemas.openxmlformats.org/package/2006/metadata/core-properties\" xmlns:dc=\"http://purl.org/dc/elements/1.1/\" xmlns:dcterms=\"http://purl.org/dc/terms/\" xmlns:dcmitype=\"http://purl.org/dc/dcmitype/\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\"><dc:title>{}</dc:title><dc:subject>{}</dc:subject><dc:creator>AI4HEOR</dc:creator><cp:lastModifiedBy>AI4HEOR</cp:lastModifiedBy><dcterms:created xsi:type=\"dcterms:W3CDTF\">{}T00:00:00Z</dcterms:created><dcterms:modified xsi:type=\"dcterms:W3CDTF\">{}T00:00:00Z</dcterms:modified></cp:coreProperties>", xml_escape(&loaded.manifest.title), xml_escape(&loaded.manifest.purpose), loaded.manifest.prepared_on, loaded.manifest.prepared_on);
    let app = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Properties xmlns=\"http://schemas.openxmlformats.org/officeDocument/2006/extended-properties\" xmlns:vt=\"http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes\"><Application>AI4HEOR</Application><AppVersion>0.1</AppVersion></Properties>";
    let settings = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><w:settings xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\"><w:zoom w:percent=\"100\"/><w:defaultTabStop w:val=\"720\"/><w:characterSpacingControl w:val=\"doNotCompress\"/><w:updateFields w:val=\"true\"/></w:settings>";
    let font_table = format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><w:fonts xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"><w:font w:name=\"{FONT_NAME}\"><w:charset w:val=\"86\"/><w:family w:val=\"swiss\"/><w:embedRegular r:id=\"rId1\" w:fontKey=\"{{{DOCX_FONT_KEY}}}\" w:subsetted=\"false\"/></w:font></w:fonts>"
    );
    let font_relationships = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/font\" Target=\"fonts/SourceHanSansCN-Regular.odttf\"/></Relationships>";
    let docx_font = obfuscated_docx_font();
    build_stored_zip(&[
        (
            "[Content_Types].xml".into(),
            content_types.as_bytes().to_vec(),
        ),
        ("_rels/.rels".into(), root_relationships.as_bytes().to_vec()),
        ("docProps/app.xml".into(), app.as_bytes().to_vec()),
        ("docProps/core.xml".into(), core.into_bytes()),
        (
            "word/_rels/document.xml.rels".into(),
            relationships.as_bytes().to_vec(),
        ),
        (
            "word/_rels/fontTable.xml.rels".into(),
            font_relationships.as_bytes().to_vec(),
        ),
        ("word/document.xml".into(), document.into_bytes()),
        ("word/fontTable.xml".into(), font_table.into_bytes()),
        ("word/fonts/SourceHanSansCN-Regular.odttf".into(), docx_font),
        ("word/footer1.xml".into(), footer.as_bytes().to_vec()),
        ("word/header1.xml".into(), header.as_bytes().to_vec()),
        ("word/numbering.xml".into(), numbering.as_bytes().to_vec()),
        ("word/settings.xml".into(), settings.as_bytes().to_vec()),
        ("word/styles.xml".into(), styles.as_bytes().to_vec()),
    ])
}

fn crc32(bytes: &[u8]) -> u32 {
    let mut crc = 0xffff_ffffu32;
    for byte in bytes {
        crc ^= u32::from(*byte);
        for _ in 0..8 {
            let mask = (crc & 1).wrapping_neg();
            crc = (crc >> 1) ^ (0xedb8_8320 & mask);
        }
    }
    !crc
}

fn push_u16(output: &mut Vec<u8>, value: u16) {
    output.extend_from_slice(&value.to_le_bytes());
}

fn push_u32(output: &mut Vec<u8>, value: u32) {
    output.extend_from_slice(&value.to_le_bytes());
}

fn build_stored_zip(entries: &[(String, Vec<u8>)]) -> Result<Vec<u8>, String> {
    let mut entries = entries.to_vec();
    entries.sort_by(|left, right| left.0.cmp(&right.0));
    let mut output = Vec::new();
    let mut central = Vec::new();
    for (name, bytes) in &entries {
        if name.is_empty() || !name.is_ascii() || name.contains("..") || name.starts_with('/') {
            return Err(format!("unsafe OOXML ZIP entry: {name}"));
        }
        let name_bytes = name.as_bytes();
        let name_len =
            u16::try_from(name_bytes.len()).map_err(|_| "OOXML ZIP entry name is too long")?;
        let size = u32::try_from(bytes.len()).map_err(|_| "OOXML ZIP entry is too large")?;
        let offset = u32::try_from(output.len()).map_err(|_| "OOXML ZIP exceeds 4 GiB")?;
        let crc = crc32(bytes);
        push_u32(&mut output, 0x0403_4b50);
        push_u16(&mut output, 20);
        push_u16(&mut output, 0x0800);
        push_u16(&mut output, 0);
        push_u16(&mut output, 0);
        push_u16(&mut output, 0);
        push_u32(&mut output, crc);
        push_u32(&mut output, size);
        push_u32(&mut output, size);
        push_u16(&mut output, name_len);
        push_u16(&mut output, 0);
        output.extend_from_slice(name_bytes);
        output.extend_from_slice(bytes);

        push_u32(&mut central, 0x0201_4b50);
        push_u16(&mut central, 20);
        push_u16(&mut central, 20);
        push_u16(&mut central, 0x0800);
        push_u16(&mut central, 0);
        push_u16(&mut central, 0);
        push_u16(&mut central, 0);
        push_u32(&mut central, crc);
        push_u32(&mut central, size);
        push_u32(&mut central, size);
        push_u16(&mut central, name_len);
        push_u16(&mut central, 0);
        push_u16(&mut central, 0);
        push_u16(&mut central, 0);
        push_u16(&mut central, 0);
        push_u32(&mut central, 0);
        push_u32(&mut central, offset);
        central.extend_from_slice(name_bytes);
    }
    let central_offset = u32::try_from(output.len()).map_err(|_| "OOXML ZIP exceeds 4 GiB")?;
    let central_size = u32::try_from(central.len()).map_err(|_| "OOXML ZIP exceeds 4 GiB")?;
    output.extend_from_slice(&central);
    push_u32(&mut output, 0x0605_4b50);
    push_u16(&mut output, 0);
    push_u16(&mut output, 0);
    let count = u16::try_from(entries.len()).map_err(|_| "OOXML ZIP has too many entries")?;
    push_u16(&mut output, count);
    push_u16(&mut output, count);
    push_u32(&mut output, central_size);
    push_u32(&mut output, central_offset);
    push_u16(&mut output, 0);
    if output.len() > OUTPUT_CAP_BYTES {
        return Err("generated OOXML exceeds the 50 MiB output cap".into());
    }
    Ok(output)
}

#[derive(Clone, Debug)]
enum XlsxValue {
    Empty,
    Text(String),
    Number(String),
    Boolean(bool),
}

#[derive(Clone, Debug)]
struct XlsxCell {
    value: XlsxValue,
    style: u8,
}

impl XlsxCell {
    fn empty() -> Self {
        Self {
            value: XlsxValue::Empty,
            style: 0,
        }
    }

    fn text(value: impl Into<String>, style: u8) -> Self {
        Self {
            value: XlsxValue::Text(value.into()),
            style,
        }
    }

    fn number(value: impl Into<String>) -> Self {
        let value = value.into();
        let style = if value
            .chars()
            .any(|character| matches!(character, '.' | 'e' | 'E'))
        {
            9
        } else {
            5
        };
        Self {
            value: XlsxValue::Number(value),
            style,
        }
    }

    fn boolean(value: bool) -> Self {
        Self {
            value: XlsxValue::Boolean(value),
            style: 4,
        }
    }
}

#[derive(Clone, Debug)]
struct XlsxSheet {
    name: String,
    rows: Vec<Vec<XlsxCell>>,
    widths: Vec<f32>,
    freeze_rows: usize,
    auto_filter: Option<(usize, usize)>,
}

fn xlsx_text(value: &str) -> Result<String, String> {
    if value.chars().count() > 32_767 {
        return Err("an XLSX cell exceeds Excel's 32767-character limit".into());
    }
    if value
        .chars()
        .any(|character| character.is_control() && !matches!(character, '\n' | '\r' | '\t'))
    {
        return Err("an XLSX cell contains an unsupported control character".into());
    }
    Ok(value.replace("\r\n", "\n").replace('\r', "\n"))
}

fn column_name(mut index: usize) -> String {
    let mut output = Vec::new();
    loop {
        output.push((b'A' + (index % 26) as u8) as char);
        index /= 26;
        if index == 0 {
            break;
        }
        index -= 1;
    }
    output.iter().rev().collect()
}

fn xlsx_cell_xml(cell: &XlsxCell, row: usize, column: usize) -> Result<String, String> {
    let reference = format!("{}{}", column_name(column), row);
    match &cell.value {
        XlsxValue::Empty => Ok(String::new()),
        XlsxValue::Text(value) => Ok(format!(
            "<c r=\"{reference}\" s=\"{}\" t=\"inlineStr\"><is><t xml:space=\"preserve\">{}</t></is></c>",
            cell.style,
            xml_escape(&xlsx_text(value)?)
        )),
        XlsxValue::Number(value) => {
            let parsed = value
                .parse::<f64>()
                .map_err(|_| format!("invalid numeric XLSX value: {value}"))?;
            if !parsed.is_finite() {
                return Err(format!("non-finite numeric XLSX value: {value}"));
            }
            Ok(format!(
                "<c r=\"{reference}\" s=\"{}\" t=\"n\"><v>{value}</v></c>",
                cell.style
            ))
        }
        XlsxValue::Boolean(value) => Ok(format!(
            "<c r=\"{reference}\" s=\"{}\" t=\"b\"><v>{}</v></c>",
            cell.style,
            usize::from(*value)
        )),
    }
}

fn xlsx_sheet_xml(sheet: &XlsxSheet) -> Result<Vec<u8>, String> {
    if sheet.rows.is_empty() || sheet.rows.len() > 1_048_576 {
        return Err(format!(
            "XLSX sheet {} has an unsupported row count",
            sheet.name
        ));
    }
    if sheet.widths.is_empty() || sheet.widths.len() > 16_384 {
        return Err(format!(
            "XLSX sheet {} has an unsupported column count",
            sheet.name
        ));
    }
    let mut rows = String::new();
    for (row_index, row) in sheet.rows.iter().enumerate() {
        if row.len() > sheet.widths.len() {
            return Err(format!(
                "XLSX sheet {} has a row wider than declared",
                sheet.name
            ));
        }
        let number = row_index + 1;
        let height = match row.first().map(|cell| cell.style) {
            Some(1) => " ht=\"30\" customHeight=\"1\"",
            Some(2) => " ht=\"22\" customHeight=\"1\"",
            _ => "",
        };
        let mut cells = String::new();
        for (column_index, cell) in row.iter().enumerate() {
            cells.push_str(&xlsx_cell_xml(cell, number, column_index)?);
        }
        rows.push_str(&format!("<row r=\"{number}\"{height}>{cells}</row>"));
    }
    let columns = sheet
        .widths
        .iter()
        .enumerate()
        .map(|(index, width)| {
            let number = index + 1;
            format!(
                "<col min=\"{number}\" max=\"{number}\" width=\"{width:.1}\" customWidth=\"1\"/>"
            )
        })
        .collect::<String>();
    let last_column = column_name(sheet.widths.len() - 1);
    let last_row = sheet.rows.len();
    let pane = if sheet.freeze_rows == 0 {
        String::new()
    } else {
        let top = sheet.freeze_rows + 1;
        format!("<pane ySplit=\"{}\" topLeftCell=\"A{top}\" activePane=\"bottomLeft\" state=\"frozen\"/><selection pane=\"bottomLeft\" activeCell=\"A{top}\" sqref=\"A{top}\"/>", sheet.freeze_rows)
    };
    let filter = sheet.auto_filter.map_or_else(String::new, |(start, end)| {
        format!("<autoFilter ref=\"A{start}:{last_column}{end}\"/>")
    });
    Ok(format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><worksheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><dimension ref=\"A1:{last_column}{last_row}\"/><sheetViews><sheetView showGridLines=\"0\" workbookViewId=\"0\">{pane}</sheetView></sheetViews><sheetFormatPr defaultRowHeight=\"18\"/><cols>{columns}</cols><sheetData>{rows}</sheetData>{filter}<pageMargins left=\"0.35\" right=\"0.35\" top=\"0.5\" bottom=\"0.5\" header=\"0.2\" footer=\"0.2\"/><pageSetup orientation=\"landscape\" fitToWidth=\"1\" fitToHeight=\"0\"/></worksheet>"
    )
    .into_bytes())
}

fn flatten_json(
    prefix: &str,
    value: &serde_json::Value,
    output: &mut Vec<Vec<XlsxCell>>,
) -> Result<(), String> {
    if output.len() > 50_000 {
        return Err("result_summary exceeds 50000 XLSX rows".into());
    }
    match value {
        serde_json::Value::Object(values) => {
            let mut keys = values.keys().collect::<Vec<_>>();
            keys.sort();
            for key in keys {
                let path = if prefix.is_empty() {
                    key.to_string()
                } else {
                    format!("{prefix}.{key}")
                };
                flatten_json(&path, &values[key], output)?;
            }
        }
        serde_json::Value::Array(values) => {
            if values.is_empty() {
                output.push(vec![
                    XlsxCell::text(prefix, 4),
                    XlsxCell::text("array", 4),
                    XlsxCell::text("[]", 4),
                    XlsxCell::empty(),
                ]);
            } else {
                for (index, item) in values.iter().enumerate() {
                    flatten_json(&format!("{prefix}[{index}]"), item, output)?;
                }
            }
        }
        serde_json::Value::Null => output.push(vec![
            XlsxCell::text(prefix, 4),
            XlsxCell::text("null", 4),
            XlsxCell::text("null", 6),
            XlsxCell::text("The bound result contains an explicit null value.", 6),
        ]),
        serde_json::Value::Bool(value) => output.push(vec![
            XlsxCell::text(prefix, 4),
            XlsxCell::text("boolean", 4),
            XlsxCell::boolean(*value),
            XlsxCell::empty(),
        ]),
        serde_json::Value::Number(value) => output.push(vec![
            XlsxCell::text(prefix, 4),
            XlsxCell::text("number", 4),
            XlsxCell::number(value.to_string()),
            XlsxCell::empty(),
        ]),
        serde_json::Value::String(value) => output.push(vec![
            XlsxCell::text(prefix, 4),
            XlsxCell::text("string", 4),
            XlsxCell::text(value, 4),
            XlsxCell::empty(),
        ]),
    }
    Ok(())
}

fn json_text(value: Option<&serde_json::Value>) -> String {
    match value {
        None | Some(serde_json::Value::Null) => "null".into(),
        Some(serde_json::Value::String(value)) => value.clone(),
        Some(serde_json::Value::Array(values)) => values
            .iter()
            .map(|value| json_text(Some(value)))
            .collect::<Vec<_>>()
            .join("; "),
        Some(value) => value.to_string(),
    }
}

fn report_table_rows(blocks: &[Block]) -> Vec<Vec<XlsxCell>> {
    let mut output = vec![vec![XlsxCell::text("Report tables / 报告表格", 1)]];
    let mut heading = String::new();
    let mut table_number = 0usize;
    for block in blocks {
        match block {
            Block::Heading { text, .. } => heading = text.clone(),
            Block::Table(rows) => {
                table_number += 1;
                output.push(vec![XlsxCell::empty()]);
                output.push(vec![XlsxCell::text(
                    if heading.is_empty() {
                        format!("Table {table_number} / 表 {table_number}")
                    } else {
                        format!("Table {table_number} / 表 {table_number} · {heading}")
                    },
                    2,
                )]);
                for (row_index, row) in rows.iter().enumerate() {
                    output.push(
                        row.iter()
                            .map(|value| XlsxCell::text(value, if row_index == 0 { 3 } else { 4 }))
                            .collect(),
                    );
                }
            }
            _ => {}
        }
    }
    if table_number == 0 {
        output.push(vec![XlsxCell::text(
            "No tables in the current report document / 当前报告正文没有表格",
            6,
        )]);
    }
    output
}

fn build_xlsx(loaded: &LoadedReport) -> Result<Vec<u8>, String> {
    let package: serde_json::Value = serde_json::from_slice(&loaded.package_raw)
        .map_err(|error| format!("cannot parse audited report package for XLSX: {error}"))?;

    let summary = XlsxSheet {
        name: "Summary 摘要".into(),
        rows: vec![
            vec![XlsxCell::text(&loaded.manifest.title, 1)],
            vec![XlsxCell::text(&loaded.manifest.subtitle, 4)],
            vec![XlsxCell::text(
                "This workbook copies the audited report package without recalculating the model. It is not research, reimbursement, or release approval. / 本工作簿复制已审计报告包，不重新计算模型，也不代表研究、支付或发布批准。",
                6,
            )],
            vec![XlsxCell::text("Record / 记录项", 3), XlsxCell::text("Value / 值", 3)],
            vec![XlsxCell::text("Document ID / 文档标识", 8), XlsxCell::text(&loaded.manifest.document_id, 4)],
            vec![XlsxCell::text("Prepared on / 编制日期", 8), XlsxCell::text(&loaded.manifest.prepared_on, 4)],
            vec![XlsxCell::text("Audience / 使用对象", 8), XlsxCell::text(&loaded.manifest.audience, 4)],
            vec![XlsxCell::text("Purpose / 用途", 8), XlsxCell::text(&loaded.manifest.purpose, 4)],
            vec![XlsxCell::text("Language / 语言", 8), XlsxCell::text(&loaded.manifest.language, 4)],
            vec![XlsxCell::text("Review status / 复核状态", 8), XlsxCell::text("awaiting_human_review", 6)],
            vec![XlsxCell::text("Report blocks / 报告内容块", 8), XlsxCell::number(loaded.blocks.len().to_string())],
            vec![XlsxCell::text("Report tables / 报告表格", 8), XlsxCell::number(loaded.table_count.to_string())],
        ],
        widths: vec![26.0, 72.0],
        freeze_rows: 4,
        auto_filter: None,
    };

    let mut result_rows = vec![
        vec![XlsxCell::text("Result summary / 结果指标", 1)],
        vec![XlsxCell::text(
            "Values come directly from the bound report-package.json; paths retain their hierarchy and null is not changed to zero. / 数值直接来自已绑定的报告包，null 不会改写为零。",
            6,
        )],
        vec![
            XlsxCell::text("Field path / 字段路径", 3),
            XlsxCell::text("Type / 类型", 3),
            XlsxCell::text("Value / 值", 3),
            XlsxCell::text("Note / 说明", 3),
        ],
    ];
    let result_summary = package
        .get("result_summary")
        .ok_or_else(|| "audited report package has no result_summary".to_string())?;
    flatten_json("", result_summary, &mut result_rows)?;
    let result_end = result_rows.len();
    let results = XlsxSheet {
        name: "Results 结果".into(),
        rows: result_rows,
        widths: vec![54.0, 14.0, 28.0, 58.0],
        freeze_rows: 3,
        auto_filter: Some((3, result_end)),
    };

    let report_tables = XlsxSheet {
        name: "Report Tables 报告表".into(),
        rows: report_table_rows(&loaded.blocks),
        widths: vec![28.0, 22.0, 22.0, 22.0, 22.0, 22.0, 22.0, 22.0],
        freeze_rows: 1,
        auto_filter: None,
    };

    let mut matrix_rows = vec![
        vec![XlsxCell::text("Reporting matrix / 报告规范", 1)],
        vec![XlsxCell::text(
            "Status records reporting coverage, not methodological quality. / 状态表示报告覆盖情况，不是方法学质量评分。",
            6,
        )],
        vec![
            XlsxCell::text("Profile / 规范", 3),
            XlsxCell::text("Item / 条目", 3),
            XlsxCell::text("Status / 状态", 3),
            XlsxCell::text("Section / 报告章节", 3),
            XlsxCell::text("Rationale / 理由", 3),
            XlsxCell::text("Supporting files / 支持文件", 3),
        ],
    ];
    let items = package
        .get("items")
        .and_then(serde_json::Value::as_array)
        .ok_or_else(|| "audited report package has no reporting items".to_string())?;
    for item in items {
        matrix_rows.push(vec![
            XlsxCell::text(json_text(item.get("profile_id")), 4),
            XlsxCell::text(json_text(item.get("item_id")), 4),
            XlsxCell::text(json_text(item.get("status")), 4),
            XlsxCell::text(json_text(item.get("section_id")), 4),
            XlsxCell::text(json_text(item.get("rationale")), 4),
            XlsxCell::text(json_text(item.get("artifact_paths")), 4),
        ]);
    }
    let matrix_end = matrix_rows.len();
    let matrix = XlsxSheet {
        name: "Reporting Matrix 报告规范".into(),
        rows: matrix_rows,
        widths: vec![20.0, 30.0, 16.0, 34.0, 42.0, 46.0],
        freeze_rows: 3,
        auto_filter: Some((3, matrix_end)),
    };

    let mut source_rows = vec![
        vec![XlsxCell::text("Sources and review / 来源与复核", 1)],
        vec![XlsxCell::text(
            "SHA-256 binding detects source drift; it does not prove correctness, identity, or approval. / SHA-256 绑定用于发现来源漂移，不证明内容正确、身份真实或研究获得批准。",
            6,
        )],
        vec![XlsxCell::text("Generation record / 生成记录", 2)],
        vec![XlsxCell::text("Record / 项目", 3), XlsxCell::text("Value / 值", 3), XlsxCell::text("SHA-256", 3)],
        vec![XlsxCell::text("Generator / 生成器", 8), XlsxCell::text(format!("AI4HEOR native report renderer {ENGINE_VERSION}"), 4)],
        vec![XlsxCell::text("Manifest / 生成清单", 8), XlsxCell::text(REPORT_EXPORT_MANIFEST_PATH, 4), XlsxCell::text(sha256(&loaded.manifest_raw), 7)],
        vec![XlsxCell::text("Report package / 报告包", 8), XlsxCell::text(&loaded.manifest.report_package.path, 4), XlsxCell::text(sha256(&loaded.package_raw), 7)],
        vec![XlsxCell::text("Report document / 报告正文", 8), XlsxCell::text(&loaded.manifest.report_document.path, 4), XlsxCell::text(sha256(&loaded.report_raw), 7)],
        vec![XlsxCell::text("Review status / 复核状态", 8), XlsxCell::text("awaiting_human_review", 6)],
        vec![XlsxCell::empty()],
        vec![XlsxCell::text("Bindings / 报告包绑定", 2)],
        vec![XlsxCell::text("Binding / 绑定名称", 3), XlsxCell::text("Path / 路径", 3), XlsxCell::text("SHA-256", 3)],
    ];
    let bindings = package
        .get("bindings")
        .and_then(serde_json::Value::as_object)
        .ok_or_else(|| "audited report package has no bindings".to_string())?;
    let mut binding_names = bindings.keys().collect::<Vec<_>>();
    binding_names.sort();
    for name in binding_names {
        let binding = &bindings[name];
        source_rows.push(vec![
            XlsxCell::text(name, 4),
            XlsxCell::text(json_text(binding.get("path")), 4),
            XlsxCell::text(
                binding
                    .get("content_sha256")
                    .or_else(|| binding.get("sha256"))
                    .map_or_else(String::new, |value| json_text(Some(value))),
                7,
            ),
        ]);
    }
    source_rows.push(vec![XlsxCell::empty()]);
    source_rows.push(vec![XlsxCell::text("Disclosures / 披露", 2)]);
    source_rows.push(vec![
        XlsxCell::text("Item / 项目", 3),
        XlsxCell::text("Content / 内容", 3),
    ]);
    if let Some(disclosures) = package
        .get("disclosures")
        .and_then(serde_json::Value::as_object)
    {
        let mut names = disclosures.keys().collect::<Vec<_>>();
        names.sort();
        for name in names {
            source_rows.push(vec![
                XlsxCell::text(name, 4),
                XlsxCell::text(json_text(Some(&disclosures[name])), 4),
            ]);
        }
    }
    source_rows.push(vec![XlsxCell::empty()]);
    source_rows.push(vec![XlsxCell::text("Limitations / 局限性", 2)]);
    source_rows.push(vec![
        XlsxCell::text("No. / 序号", 3),
        XlsxCell::text("Content / 内容", 3),
    ]);
    if let Some(limitations) = package
        .get("limitations")
        .and_then(serde_json::Value::as_array)
    {
        for (index, limitation) in limitations.iter().enumerate() {
            source_rows.push(vec![
                XlsxCell::number((index + 1).to_string()),
                XlsxCell::text(json_text(Some(limitation)), 4),
            ]);
        }
    }
    let sources = XlsxSheet {
        name: "Sources & Review 来源复核".into(),
        rows: source_rows,
        widths: vec![28.0, 58.0, 58.0],
        freeze_rows: 4,
        auto_filter: None,
    };

    let sheets = vec![summary, results, report_tables, matrix, sources];
    let sheet_entries = sheets
        .iter()
        .enumerate()
        .map(|(index, sheet)| {
            Ok((
                format!("xl/worksheets/sheet{}.xml", index + 1),
                xlsx_sheet_xml(sheet)?,
            ))
        })
        .collect::<Result<Vec<(String, Vec<u8>)>, String>>()?;
    let sheet_nodes = sheets
        .iter()
        .enumerate()
        .map(|(index, sheet)| {
            format!(
                "<sheet name=\"{}\" sheetId=\"{}\" r:id=\"rId{}\"/>",
                xml_escape(&sheet.name),
                index + 1,
                index + 1
            )
        })
        .collect::<String>();
    let workbook = format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><workbook xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\"><fileVersion appName=\"AI4HEOR\"/><workbookPr date1904=\"0\"/><bookViews><workbookView xWindow=\"0\" yWindow=\"0\" windowWidth=\"24000\" windowHeight=\"14000\"/></bookViews><sheets>{sheet_nodes}</sheets><calcPr calcId=\"0\" calcMode=\"manual\"/></workbook>"
    );
    let workbook_relationships = sheets
        .iter()
        .enumerate()
        .map(|(index, _)| format!("<Relationship Id=\"rId{}\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet\" Target=\"worksheets/sheet{}.xml\"/>", index + 1, index + 1))
        .chain([format!("<Relationship Id=\"rId{}\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles\" Target=\"styles.xml\"/>", sheets.len() + 1)])
        .collect::<String>();
    let workbook_relationships = format!("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\">{workbook_relationships}</Relationships>");
    let content_overrides = (1..=sheets.len())
        .map(|index| format!("<Override PartName=\"/xl/worksheets/sheet{index}.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml\"/>"))
        .collect::<String>();
    let content_types = format!("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"><Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/><Default Extension=\"xml\" ContentType=\"application/xml\"/><Override PartName=\"/xl/workbook.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml\"/><Override PartName=\"/xl/styles.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml\"/>{content_overrides}<Override PartName=\"/docProps/core.xml\" ContentType=\"application/vnd.openxmlformats-package.core-properties+xml\"/><Override PartName=\"/docProps/app.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.extended-properties+xml\"/></Types>");
    let root_relationships = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"xl/workbook.xml\"/><Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties\" Target=\"docProps/core.xml\"/><Relationship Id=\"rId3\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties\" Target=\"docProps/app.xml\"/></Relationships>";
    let core = format!("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><cp:coreProperties xmlns:cp=\"http://schemas.openxmlformats.org/package/2006/metadata/core-properties\" xmlns:dc=\"http://purl.org/dc/elements/1.1/\" xmlns:dcterms=\"http://purl.org/dc/terms/\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\"><dc:title>{}</dc:title><dc:subject>{}</dc:subject><dc:creator>AI4HEOR</dc:creator><cp:lastModifiedBy>AI4HEOR</cp:lastModifiedBy><dcterms:created xsi:type=\"dcterms:W3CDTF\">{}T00:00:00Z</dcterms:created><dcterms:modified xsi:type=\"dcterms:W3CDTF\">{}T00:00:00Z</dcterms:modified></cp:coreProperties>", xml_escape(&loaded.manifest.title), xml_escape(&loaded.manifest.purpose), loaded.manifest.prepared_on, loaded.manifest.prepared_on);
    let sheet_titles = sheets
        .iter()
        .map(|sheet| format!("<vt:lpstr>{}</vt:lpstr>", xml_escape(&sheet.name)))
        .collect::<String>();
    let app = format!("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Properties xmlns=\"http://schemas.openxmlformats.org/officeDocument/2006/extended-properties\" xmlns:vt=\"http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes\"><Application>AI4HEOR</Application><AppVersion>0.2</AppVersion><HeadingPairs><vt:vector size=\"2\" baseType=\"variant\"><vt:variant><vt:lpstr>Worksheets</vt:lpstr></vt:variant><vt:variant><vt:i4>{}</vt:i4></vt:variant></vt:vector></HeadingPairs><TitlesOfParts><vt:vector size=\"{}\" baseType=\"lpstr\">{sheet_titles}</vt:vector></TitlesOfParts></Properties>", sheets.len(), sheets.len());
    let styles = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><styleSheet xmlns=\"http://schemas.openxmlformats.org/spreadsheetml/2006/main\"><numFmts count=\"2\"><numFmt numFmtId=\"164\" formatCode=\"#,##0\"/><numFmt numFmtId=\"165\" formatCode=\"#,##0.##########\"/></numFmts><fonts count=\"6\"><font><sz val=\"10\"/><name val=\"Arial\"/><color rgb=\"FF172033\"/></font><font><b/><sz val=\"18\"/><name val=\"Arial\"/><color rgb=\"FF172033\"/></font><font><b/><sz val=\"11\"/><name val=\"Arial\"/><color rgb=\"FFFFFFFF\"/></font><font><b/><sz val=\"10\"/><name val=\"Arial\"/><color rgb=\"FF172033\"/></font><font><i/><sz val=\"10\"/><name val=\"Arial\"/><color rgb=\"FF7A4B00\"/></font><font><sz val=\"9\"/><name val=\"Menlo\"/><color rgb=\"FF4E5968\"/></font></fonts><fills count=\"5\"><fill><patternFill patternType=\"none\"/></fill><fill><patternFill patternType=\"gray125\"/></fill><fill><patternFill patternType=\"solid\"><fgColor rgb=\"FF2E5D7B\"/><bgColor indexed=\"64\"/></patternFill></fill><fill><patternFill patternType=\"solid\"><fgColor rgb=\"FFE8EEF5\"/><bgColor indexed=\"64\"/></patternFill></fill><fill><patternFill patternType=\"solid\"><fgColor rgb=\"FFFFF4CC\"/><bgColor indexed=\"64\"/></patternFill></fill></fills><borders count=\"2\"><border><left/><right/><top/><bottom/><diagonal/></border><border><left/><right/><top/><bottom style=\"thin\"><color rgb=\"FFD7DCE2\"/></bottom><diagonal/></border></borders><cellStyleXfs count=\"1\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\"/></cellStyleXfs><cellXfs count=\"10\"><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"0\" xfId=\"0\"/><xf numFmtId=\"0\" fontId=\"1\" fillId=\"0\" borderId=\"0\" xfId=\"0\" applyFont=\"1\" applyAlignment=\"1\"><alignment vertical=\"center\"/></xf><xf numFmtId=\"0\" fontId=\"2\" fillId=\"2\" borderId=\"0\" xfId=\"0\" applyFont=\"1\" applyFill=\"1\" applyAlignment=\"1\"><alignment vertical=\"center\"/></xf><xf numFmtId=\"0\" fontId=\"3\" fillId=\"3\" borderId=\"1\" xfId=\"0\" applyFont=\"1\" applyFill=\"1\" applyBorder=\"1\" applyAlignment=\"1\"><alignment vertical=\"center\" wrapText=\"1\"/></xf><xf numFmtId=\"0\" fontId=\"0\" fillId=\"0\" borderId=\"1\" xfId=\"0\" applyBorder=\"1\" applyAlignment=\"1\"><alignment vertical=\"top\" wrapText=\"1\"/></xf><xf numFmtId=\"164\" fontId=\"0\" fillId=\"0\" borderId=\"1\" xfId=\"0\" applyNumberFormat=\"1\" applyBorder=\"1\" applyAlignment=\"1\"><alignment horizontal=\"right\" vertical=\"top\"/></xf><xf numFmtId=\"0\" fontId=\"4\" fillId=\"4\" borderId=\"0\" xfId=\"0\" applyFont=\"1\" applyFill=\"1\" applyAlignment=\"1\"><alignment vertical=\"top\" wrapText=\"1\"/></xf><xf numFmtId=\"0\" fontId=\"5\" fillId=\"0\" borderId=\"1\" xfId=\"0\" applyFont=\"1\" applyBorder=\"1\" applyAlignment=\"1\"><alignment vertical=\"top\" wrapText=\"1\"/></xf><xf numFmtId=\"0\" fontId=\"3\" fillId=\"0\" borderId=\"1\" xfId=\"0\" applyFont=\"1\" applyBorder=\"1\" applyAlignment=\"1\"><alignment vertical=\"top\" wrapText=\"1\"/></xf><xf numFmtId=\"165\" fontId=\"0\" fillId=\"0\" borderId=\"1\" xfId=\"0\" applyNumberFormat=\"1\" applyBorder=\"1\" applyAlignment=\"1\"><alignment horizontal=\"right\" vertical=\"top\"/></xf></cellXfs><cellStyles count=\"1\"><cellStyle name=\"Normal\" xfId=\"0\" builtinId=\"0\"/></cellStyles></styleSheet>";
    let mut entries = vec![
        ("[Content_Types].xml".into(), content_types.into_bytes()),
        ("_rels/.rels".into(), root_relationships.as_bytes().to_vec()),
        ("docProps/app.xml".into(), app.into_bytes()),
        ("docProps/core.xml".into(), core.into_bytes()),
        (
            "xl/_rels/workbook.xml.rels".into(),
            workbook_relationships.into_bytes(),
        ),
        ("xl/styles.xml".into(), styles.as_bytes().to_vec()),
        ("xl/workbook.xml".into(), workbook.into_bytes()),
    ];
    entries.extend(sheet_entries);
    build_stored_zip(&entries)
}

fn rgb(hex: &str) -> Color {
    let value = u32::from_str_radix(hex, 16).unwrap_or(0);
    Color::Rgb(Rgb::new(
        ((value >> 16) & 0xff) as f32 / 255.0,
        ((value >> 8) & 0xff) as f32 / 255.0,
        (value & 0xff) as f32 / 255.0,
        None,
    ))
}

fn character_units(character: char) -> f32 {
    if character.is_whitespace() {
        0.30
    } else if character.is_ascii_uppercase() {
        0.64
    } else if character.is_ascii_lowercase() || character.is_ascii_digit() {
        0.55
    } else if character.is_ascii_punctuation() {
        0.42
    } else {
        1.0
    }
}

fn wrap_text(value: &str, max_width_points: f32, font_size: f32) -> Vec<String> {
    let max_units = (max_width_points / font_size).max(1.0);
    let mut output = Vec::new();
    for source_line in value.lines().chain((value.is_empty()).then_some("")) {
        if source_line.is_empty() {
            output.push(String::new());
            continue;
        }
        let mut line = String::new();
        let mut units = 0.0f32;
        let mut last_space = None;
        for character in source_line.chars() {
            let next = character_units(character);
            if !line.is_empty() && units + next > max_units {
                if let Some(space) = last_space.filter(|space| *space > line.len() / 3) {
                    let rest = line[space + 1..].to_string();
                    line.truncate(space);
                    output.push(line.trim_end().to_string());
                    line = rest;
                    units = line.chars().map(character_units).sum();
                } else {
                    output.push(line.trim_end().to_string());
                    line.clear();
                    units = 0.0;
                }
                last_space = None;
            }
            if character == ' ' {
                last_space = Some(line.len());
            }
            line.push(character);
            units += next;
        }
        if !line.is_empty() {
            output.push(line.trim_end().to_string());
        }
    }
    if output.is_empty() {
        output.push(String::new());
    }
    output
}

struct PdfComposer {
    font_id: FontId,
    title: String,
    pages: Vec<Vec<Op>>,
    current: Vec<Op>,
    y: f32,
}

impl PdfComposer {
    const PAGE_WIDTH: f32 = 595.28;
    const LEFT: f32 = 58.0;
    const RIGHT: f32 = 58.0;
    const TOP: f32 = 780.0;
    const BOTTOM: f32 = 58.0;

    fn new(font_id: FontId, title: String) -> Self {
        let mut value = Self {
            font_id,
            title,
            pages: Vec::new(),
            current: Vec::new(),
            y: Self::TOP,
        };
        value.start_page();
        value
    }

    fn content_width() -> f32 {
        Self::PAGE_WIDTH - Self::LEFT - Self::RIGHT
    }

    fn start_page(&mut self) {
        if !self.current.is_empty() {
            self.pages.push(std::mem::take(&mut self.current));
        }
        self.y = Self::TOP;
        self.text_at(
            Self::LEFT,
            815.0,
            8.2,
            "697386",
            &format!("AI4HEOR · {}", truncate_text(&self.title, 56)),
        );
        self.current
            .push(Op::SetOutlineColor { col: rgb("D7DCE2") });
        self.current.push(Op::SetOutlineThickness { pt: Pt(0.5) });
        self.current.push(Op::DrawRectangle {
            rectangle: Rect {
                x: Pt(Self::LEFT),
                y: Pt(805.0),
                width: Pt(Self::content_width()),
                height: Pt(0.1),
                mode: Some(PaintMode::Stroke),
                winding_order: None,
            },
        });
    }

    fn ensure(&mut self, height: f32) {
        if self.y - height < Self::BOTTOM {
            self.start_page();
        }
    }

    fn text_at(&mut self, x: f32, y: f32, size: f32, color: &str, text: &str) {
        self.current.extend([
            Op::StartTextSection,
            Op::SetTextCursor {
                pos: Point { x: Pt(x), y: Pt(y) },
            },
            Op::SetFont {
                font: PdfFontHandle::External(self.font_id.clone()),
                size: Pt(size),
            },
            Op::SetCharacterSpacing { multiplier: 0.0 },
            Op::SetFillColor { col: rgb(color) },
            Op::ShowText {
                items: vec![TextItem::Text(text.to_string())],
            },
            Op::EndTextSection,
        ]);
    }

    fn add_lines(
        &mut self,
        text: &str,
        size: f32,
        line_height: f32,
        color: &str,
        indent: f32,
        before: f32,
        after: f32,
    ) {
        self.y -= before;
        let width = Self::content_width() - indent;
        for line in wrap_text(text, width, size) {
            self.ensure(line_height);
            self.text_at(Self::LEFT + indent, self.y, size, color, &line);
            self.y -= line_height;
        }
        self.y -= after;
    }

    fn heading(&mut self, level: u8, text: &str) {
        let (size, line_height, color, before, after) = match level {
            1 => (16.0, 22.0, "2E5D7B", 16.0, 7.0),
            2 => (13.0, 18.0, "2E5D7B", 12.0, 5.0),
            _ => (11.5, 16.0, "1F4D78", 9.0, 4.0),
        };
        let lines = wrap_text(text, Self::content_width(), size);
        self.ensure(before + line_height * lines.len() as f32 + after);
        self.y -= before;
        for line in lines {
            self.text_at(Self::LEFT, self.y, size, color, &line);
            self.y -= line_height;
        }
        self.y -= after;
    }

    fn quote(&mut self, text: &str) {
        let lines = wrap_text(text, Self::content_width() - 28.0, 10.0);
        let height = lines.len() as f32 * 14.0 + 12.0;
        self.ensure(height + 8.0);
        self.y -= 4.0;
        self.current.push(Op::SetFillColor { col: rgb("D3623B") });
        self.current.push(Op::DrawRectangle {
            rectangle: Rect {
                x: Pt(Self::LEFT),
                y: Pt(self.y - height + 5.0),
                width: Pt(3.0),
                height: Pt(height),
                mode: Some(PaintMode::Fill),
                winding_order: None,
            },
        });
        for line in lines {
            self.text_at(Self::LEFT + 16.0, self.y, 10.0, "4E5968", &line);
            self.y -= 14.0;
        }
        self.y -= 8.0;
    }

    fn rule(&mut self) {
        self.ensure(18.0);
        self.y -= 8.0;
        self.current
            .push(Op::SetOutlineColor { col: rgb("D7DCE2") });
        self.current.push(Op::SetOutlineThickness { pt: Pt(0.6) });
        self.current.push(Op::DrawRectangle {
            rectangle: Rect {
                x: Pt(Self::LEFT),
                y: Pt(self.y),
                width: Pt(Self::content_width()),
                height: Pt(0.1),
                mode: Some(PaintMode::Stroke),
                winding_order: None,
            },
        });
        self.y -= 10.0;
    }

    fn table(&mut self, rows: &[Vec<String>]) {
        let columns = rows.first().map_or(1, Vec::len).max(1);
        let cell_width = Self::content_width() / columns as f32;
        for (row_index, row) in rows.iter().enumerate() {
            let font_size = if columns > 5 { 7.2 } else { 8.2 };
            let line_height = font_size + 3.0;
            let wrapped = row
                .iter()
                .map(|cell| wrap_text(cell, cell_width - 10.0, font_size))
                .collect::<Vec<_>>();
            let row_height =
                wrapped.iter().map(Vec::len).max().unwrap_or(1) as f32 * line_height + 10.0;
            self.ensure(row_height + 2.0);
            for (column, lines) in wrapped.iter().enumerate() {
                let x = Self::LEFT + column as f32 * cell_width;
                let fill = if row_index == 0 { "E8EEF5" } else { "FFFFFF" };
                self.current.push(Op::SetFillColor { col: rgb(fill) });
                self.current
                    .push(Op::SetOutlineColor { col: rgb("B8C2CC") });
                self.current.push(Op::SetOutlineThickness { pt: Pt(0.45) });
                self.current.push(Op::DrawRectangle {
                    rectangle: Rect {
                        x: Pt(x),
                        y: Pt(self.y - row_height),
                        width: Pt(cell_width),
                        height: Pt(row_height),
                        mode: Some(PaintMode::FillStroke),
                        winding_order: None,
                    },
                });
                for (line_index, line) in lines.iter().enumerate() {
                    self.text_at(
                        x + 5.0,
                        self.y - 5.0 - font_size - line_index as f32 * line_height,
                        font_size,
                        "172033",
                        line,
                    );
                }
            }
            self.y -= row_height;
        }
        self.y -= 9.0;
    }

    fn finish(mut self) -> Vec<PdfPage> {
        if !self.current.is_empty() {
            self.pages.push(std::mem::take(&mut self.current));
        }
        let total = self.pages.len();
        for (index, operations) in self.pages.iter_mut().enumerate() {
            operations.extend([
                Op::StartTextSection,
                Op::SetTextCursor {
                    pos: Point {
                        x: Pt(Self::LEFT),
                        y: Pt(30.0),
                    },
                },
                Op::SetFont {
                    font: PdfFontHandle::External(self.font_id.clone()),
                    size: Pt(8.0),
                },
                Op::SetFillColor { col: rgb("697386") },
                Op::ShowText {
                    items: vec![TextItem::Text(format!(
                        "AI4HEOR · 待研究者复核 · 第 {} / {} 页",
                        index + 1,
                        total
                    ))],
                },
                Op::EndTextSection,
            ]);
        }
        self.pages
            .into_iter()
            .map(|operations| PdfPage::new(Mm(210.0), Mm(297.0), operations))
            .collect()
    }
}

fn truncate_text(value: &str, maximum: usize) -> String {
    let mut output = value.chars().take(maximum).collect::<String>();
    if value.chars().count() > maximum {
        output.push('…');
    }
    output
}

fn normalize_pdf_ids(bytes: &mut [u8], stable: &str) -> Result<(), String> {
    let trailer = bytes
        .windows(7)
        .rposition(|window| window == b"trailer")
        .ok_or("generated PDF has no trailer")?;
    let id = bytes[trailer..]
        .windows(3)
        .position(|window| window == b"/ID")
        .map(|offset| trailer + offset)
        .ok_or("generated PDF has no trailer ID")?;
    let mut cursor = id;
    for replacement in [&stable.as_bytes()[..32], &stable.as_bytes()[32..64]] {
        let open = bytes[cursor..]
            .iter()
            .position(|byte| *byte == b'(')
            .map(|offset| cursor + offset)
            .ok_or("generated PDF trailer ID is malformed")?;
        let close = bytes[open + 1..]
            .iter()
            .position(|byte| *byte == b')')
            .map(|offset| open + 1 + offset)
            .ok_or("generated PDF trailer ID is malformed")?;
        if close - open - 1 != 32 {
            return Err("generated PDF trailer ID has an unexpected length".into());
        }
        bytes[open + 1..close].copy_from_slice(replacement);
        cursor = close + 1;
    }
    Ok(())
}

fn build_pdf(loaded: &LoadedReport) -> Result<(Vec<u8>, usize), String> {
    let mut font_warnings = Vec::new();
    let parsed_font = ParsedFont::from_bytes(PDF_FONT_BYTES, 0, &mut font_warnings)
        .ok_or("bundled Source Han Sans font could not be parsed")?;
    if !font_warnings.is_empty() {
        return Err(format!(
            "bundled Source Han Sans font reported {} parse warnings",
            font_warnings.len()
        ));
    }
    let font_id = FontId("AI4HEORSourceHanSansCN".into());
    let mut document = PdfDocument::new(&loaded.manifest.title);
    document
        .resources
        .fonts
        .map
        .insert(font_id.clone(), printpdf::font::PdfFont::new(parsed_font));
    document.metadata.info.author = "AI4HEOR".into();
    document.metadata.info.creator = "AI4HEOR native report renderer".into();
    document.metadata.info.producer = format!("AI4HEOR report renderer {ENGINE_VERSION}");
    document.metadata.info.subject = loaded.manifest.purpose.clone();
    document.metadata.info.identifier = loaded.manifest.document_id.clone();

    let mut pdf = PdfComposer::new(font_id, loaded.manifest.title.clone());
    pdf.add_lines(
        "AI4HEOR · 药物经济学与 HEOR 研究报告",
        9.0,
        13.0,
        "D3623B",
        0.0,
        3.0,
        10.0,
    );
    pdf.add_lines(&loaded.manifest.title, 22.0, 29.0, "172033", 0.0, 0.0, 4.0);
    if !loaded.manifest.subtitle.trim().is_empty() {
        pdf.add_lines(
            &loaded.manifest.subtitle,
            12.0,
            17.0,
            "5B6573",
            0.0,
            0.0,
            15.0,
        );
    }
    let metadata = [
        ("编制日期", loaded.manifest.prepared_on.as_str()),
        ("面向对象", loaded.manifest.audience.as_str()),
        ("用途", loaded.manifest.purpose.as_str()),
        ("复核状态", "待研究者复核"),
    ];
    for (label, value) in metadata {
        pdf.add_lines(
            &format!("{label}：{value}"),
            9.5,
            14.0,
            "4E5968",
            0.0,
            0.0,
            2.0,
        );
    }
    pdf.quote("本文件由 AI4HEOR 根据当前已绑定报告包生成。生成文件不代表方法学质量、科研结论有效性、期刊接受、监管认可、支付决策或对外发布批准。");
    pdf.rule();
    let mut numbered_item = 0usize;
    for block in &loaded.blocks {
        if matches!(block, Block::Numbered(_)) {
            numbered_item += 1;
        } else {
            numbered_item = 0;
        }
        match block {
            Block::Heading { level, text } => pdf.heading(*level, text),
            Block::Paragraph(text) => pdf.add_lines(text, 10.5, 15.0, "172033", 0.0, 0.0, 7.0),
            Block::Bullet(text) => {
                pdf.add_lines(&format!("• {text}"), 10.5, 15.0, "172033", 15.0, 0.0, 5.0)
            }
            Block::Numbered(text) => pdf.add_lines(
                &format!("{numbered_item}. {text}"),
                10.5,
                15.0,
                "172033",
                15.0,
                0.0,
                5.0,
            ),
            Block::Quote(text) => pdf.quote(text),
            Block::Code(text) => pdf.add_lines(text, 8.5, 12.0, "2D3748", 12.0, 4.0, 7.0),
            Block::Rule => pdf.rule(),
            Block::Table(rows) => pdf.table(rows),
        }
    }
    pdf.heading(2, "来源绑定 / Source binding");
    pdf.add_lines(
        &format!(
            "报告包 SHA-256：{}\n报告正文 SHA-256：{}\n生成清单 SHA-256：{}",
            sha256(&loaded.package_raw),
            sha256(&loaded.report_raw),
            sha256(&loaded.manifest_raw)
        ),
        7.8,
        11.0,
        "697386",
        0.0,
        0.0,
        0.0,
    );
    let pages = pdf.finish();
    let page_count = pages.len();
    let mut options = PdfSaveOptions::default();
    options.subset_fonts = false;
    options.optimize = true;
    options.secure = true;
    let mut pdf_warnings = Vec::new();
    let mut bytes = document.with_pages(pages).save(&options, &mut pdf_warnings);
    if bytes.len() > OUTPUT_CAP_BYTES {
        return Err("generated PDF exceeds the 50 MiB output cap".into());
    }
    if pdf_warnings
        .iter()
        .any(|warning| !matches!(warning.severity, printpdf::PdfParseErrorSeverity::Info))
    {
        return Err(format!(
            "PDF renderer reported {} warnings",
            pdf_warnings.len()
        ));
    }
    let stable = sha256(
        &[
            loaded.manifest_raw.as_slice(),
            loaded.package_raw.as_slice(),
            loaded.report_raw.as_slice(),
            FONT_SHA256.as_bytes(),
        ]
        .concat(),
    );
    normalize_pdf_ids(&mut bytes, &stable)?;
    Ok((bytes, page_count))
}

fn write_atomic(path: &Path, bytes: &[u8]) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("cannot create report output directory: {error}"))?;
    }
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("report-output");
    let temporary = path.with_file_name(format!(".{file_name}.tmp"));
    {
        let mut file = std::fs::File::create(&temporary)
            .map_err(|error| format!("cannot stage report output: {error}"))?;
        file.write_all(bytes)
            .and_then(|_| file.sync_all())
            .map_err(|error| format!("cannot flush report output: {error}"))?;
    }
    if std::fs::rename(&temporary, path).is_err() {
        let result = std::fs::write(path, bytes)
            .map_err(|error| format!("cannot replace report output: {error}"));
        let _ = std::fs::remove_file(&temporary);
        result?;
    }
    Ok(())
}

fn existing_outputs_replaceable(workspace: &Path) -> Result<(), String> {
    let docx = workspace.join(REPORT_DOCX_OUTPUT_PATH);
    let pdf = workspace.join(REPORT_PDF_OUTPUT_PATH);
    let xlsx = workspace.join(REPORT_XLSX_OUTPUT_PATH);
    if !docx.exists() && !pdf.exists() && !xlsx.exists() {
        return Ok(());
    }
    let record_raw = std::fs::read(workspace.join(REPORT_EXPORT_AUDIT_PATH)).map_err(|_| {
        "existing report exports have no matching app audit; move or remove them before generating"
            .to_string()
    })?;
    let record: GenerationRecord = serde_json::from_slice(&record_raw).map_err(|_| {
        "existing report exports have an unreadable app audit; move or remove them before generating"
            .to_string()
    })?;
    for (path, expected) in [
        (&docx, record.docx_sha256.as_str()),
        (&pdf, record.pdf_sha256.as_str()),
    ] {
        let raw = std::fs::read(path).map_err(|_| {
            "existing report exports are incomplete; move or remove them before generating"
                .to_string()
        })?;
        if sha256(&raw) != expected {
            return Err(
                "an existing report export was changed outside AI4HEOR; move or rename it before generating"
                    .into(),
            );
        }
    }
    if xlsx.exists() {
        let expected = record.xlsx_sha256.as_deref().ok_or_else(|| {
            "existing XLSX has no matching app audit; move or remove it before generating"
                .to_string()
        })?;
        let raw = std::fs::read(&xlsx).map_err(|_| {
            "existing report exports are incomplete; move or remove them before generating"
                .to_string()
        })?;
        if sha256(&raw) != expected {
            return Err(
                "an existing report export was changed outside AI4HEOR; move or rename it before generating"
                    .into(),
            );
        }
    }
    Ok(())
}

fn audit_at(workspace: &Path) -> (ResearchReportAudit, Option<LoadedReport>) {
    load_manifest(workspace)
}

fn generate_at(workspace: &Path) -> Result<ResearchReportAudit, String> {
    let (audit, loaded) = audit_at(workspace);
    let loaded = loaded.ok_or_else(|| audit.errors.join("; "))?;
    if !audit.ready_to_generate {
        return Err(audit.errors.join("; "));
    }
    if audit.outputs_current {
        return Ok(audit);
    }
    existing_outputs_replaceable(workspace)?;
    let docx = build_docx(&loaded)?;
    let (pdf, page_count) = build_pdf(&loaded)?;
    let xlsx = build_xlsx(&loaded)?;
    let record = GenerationRecord {
        schema_version: "0.2.0".into(),
        generator: "ai4heor-native-report".into(),
        generator_version: ENGINE_VERSION.into(),
        document_id: loaded.manifest.document_id.clone(),
        manifest_path: REPORT_EXPORT_MANIFEST_PATH.into(),
        manifest_sha256: sha256(&loaded.manifest_raw),
        source_hashes: BTreeMap::from([
            ("report_document".into(), sha256(&loaded.report_raw)),
            ("report_package".into(), sha256(&loaded.package_raw)),
        ]),
        docx_path: REPORT_DOCX_OUTPUT_PATH.into(),
        docx_sha256: sha256(&docx),
        pdf_path: REPORT_PDF_OUTPUT_PATH.into(),
        pdf_sha256: sha256(&pdf),
        xlsx_path: Some(REPORT_XLSX_OUTPUT_PATH.into()),
        xlsx_sha256: Some(sha256(&xlsx)),
        block_count: loaded.blocks.len(),
        table_count: loaded.table_count,
        workbook_sheet_count: WORKBOOK_SHEET_COUNT,
        pdf_page_count: page_count,
        human_review_status: "awaiting_human_review".into(),
        font_name: FONT_NAME.into(),
        font_version: FONT_VERSION.into(),
        font_license: FONT_LICENSE.into(),
        font_sha256: FONT_SHA256.into(),
    };
    let record_raw = serde_json::to_vec_pretty(&record)
        .map_err(|error| format!("cannot serialize report audit: {error}"))?;
    write_atomic(&workspace.join(REPORT_DOCX_OUTPUT_PATH), &docx)?;
    write_atomic(&workspace.join(REPORT_PDF_OUTPUT_PATH), &pdf)?;
    write_atomic(&workspace.join(REPORT_XLSX_OUTPUT_PATH), &xlsx)?;
    write_atomic(&workspace.join(REPORT_EXPORT_AUDIT_PATH), &record_raw)?;
    Ok(audit_at(workspace).0)
}

#[tauri::command(async)]
pub fn audit_research_report(app: AppHandle) -> Result<ResearchReportAudit, String> {
    Ok(audit_at(&crate::runtime::workspace_dir(&app)?).0)
}

#[tauri::command(async)]
pub fn generate_research_report(app: AppHandle) -> Result<ResearchReportAudit, String> {
    generate_at(&crate::runtime::workspace_dir(&app)?)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn loaded_report(markdown: &str) -> LoadedReport {
        let (blocks, table_count) = parse_markdown(markdown.as_bytes()).unwrap();
        let report_raw = markdown.as_bytes().to_vec();
        let package_raw = serde_json::to_vec(&serde_json::json!({
            "package_id": "fixture",
            "analysis_id": "fixture-analysis",
            "status": "draft",
            "result_summary": {
                "cost_effectiveness": {
                    "economic_basis": {"currency": "CNY", "price_year": 2026},
                    "delta_cost": 10000,
                    "delta_qaly": 0.5,
                    "icer": 20000
                },
                "uncertainty": {"iterations": 1000, "cost_effective_probability": 0.72},
                "budget_impact": {"annual_net_budget_impact": [1200000, 1750000]}
            },
            "items": [{
                "profile_id": "CHEERS-2022",
                "item_id": "23-summary-results",
                "status": "reported",
                "section_id": "results.summary",
                "rationale": "Bound to the deterministic result",
                "artifact_paths": ["heor/results/base-case.json"]
            }],
            "bindings": {
                "base_case_result": {"path": "heor/results/base-case.json", "content_sha256": "a".repeat(64)}
            },
            "disclosures": {"funding": "Researcher-provided disclosure"},
            "limitations": ["Not all structural uncertainty is represented."]
        }))
        .unwrap();
        let manifest = ReportExportManifest {
            schema_version: "0.1.0".into(),
            document_id: "fixture-report".into(),
            title: "某药物成本效果分析与预算影响分析".into(),
            subtitle: "研究者复核稿".into(),
            language: "zh-Hans".into(),
            prepared_on: "2026-07-20".into(),
            audience: "药物经济学研究团队".into(),
            purpose: "复核当前分析结果、假设与局限性".into(),
            style: "ai4heor-formal-report".into(),
            report_package: BoundSource {
                path: crate::heor_reporting::REPORT_PACKAGE_PATH.into(),
                sha256: sha256(&package_raw),
            },
            report_document: BoundSource {
                path: crate::heor_reporting::REPORT_DOCUMENT_PATH.into(),
                sha256: sha256(&report_raw),
            },
            human_review: HumanReview {
                status: "awaiting_human_review".into(),
            },
        };
        let manifest_raw = serde_json::to_vec(&serde_json::json!({
            "schema_version": "0.1.0",
            "document_id": "fixture-report"
        }))
        .unwrap();
        LoadedReport {
            manifest,
            manifest_raw,
            package_raw,
            report_raw,
            blocks,
            table_count,
        }
    }

    #[test]
    fn markdown_parser_keeps_real_tables_and_omits_report_markers() {
        let source = "<!-- report-section:title -->\n# 标题\n\n正文第一行\n继续说明。\n\n| 策略 | 成本 | QALY |\n| --- | ---: | ---: |\n| 对照 | 100 | 1.0 |\n\n- 局限性一\n";
        let (blocks, tables) = parse_markdown(source.as_bytes()).unwrap();
        assert_eq!(tables, 1);
        assert_eq!(
            blocks[0],
            Block::Heading {
                level: 1,
                text: "标题".into()
            }
        );
        assert!(matches!(&blocks[1], Block::Paragraph(value) if value == "正文第一行继续说明。"));
        assert!(matches!(&blocks[2], Block::Table(rows) if rows.len() == 2 && rows[0].len() == 3));
        assert!(blocks.iter().all(
            |block| !matches!(block, Block::Paragraph(value) if value.contains("report-section"))
        ));
    }

    #[test]
    fn markdown_parser_rejects_raw_html_unclosed_code_and_oversized_tables() {
        assert!(parse_markdown(b"<script>alert(1)</script>").is_err());
        assert!(parse_markdown(b"```\nunclosed").is_err());
        assert!(
            parse_markdown(b"|1|2|3|4|5|6|7|8|9|\n|---|---|---|---|---|---|---|---|---|\n")
                .is_err()
        );
    }

    #[test]
    fn docx_and_pdf_are_source_bound_deterministic_and_extractable() {
        let loaded = loaded_report(
            "# 摘要\n\n本研究比较干预策略与对照策略。\n\n## 结果\n\n| 策略 | 成本（元） | QALY |\n| --- | ---: | ---: |\n| 对照 | 10000 | 1.00 |\n| 干预 | 20000 | 1.50 |\n\n> 结果仍需研究者结合证据与模型假设复核。\n\n## 复核顺序\n\n1. 先核对输入证据。\n2. 再核对模型假设。\n\n## 局限性\n\n- 未覆盖全部结构不确定性。\n",
        );
        let first_docx = build_docx(&loaded).unwrap();
        let second_docx = build_docx(&loaded).unwrap();
        assert_eq!(first_docx, second_docx);
        assert!(first_docx.starts_with(b"PK\x03\x04"));
        assert!(first_docx
            .windows(b"word/document.xml".len())
            .any(|part| part == b"word/document.xml"));
        assert!(first_docx
            .windows(b"word/fontTable.xml".len())
            .any(|part| part == b"word/fontTable.xml"));
        assert!(first_docx
            .windows(b"SourceHanSansCN-Regular.odttf".len())
            .any(|part| part == b"SourceHanSansCN-Regular.odttf"));

        let (first_pdf, pages) = build_pdf(&loaded).unwrap();
        let (second_pdf, second_pages) = build_pdf(&loaded).unwrap();
        assert_eq!(pages, second_pages);
        assert_eq!(first_pdf, second_pdf);
        assert!(first_pdf.starts_with(b"%PDF-"));
        assert!(pages >= 1);
        let text = pdf_extract::extract_text_from_mem(&first_pdf).unwrap();
        assert!(text.contains("药物经济学"));
        assert!(text.contains("局限性"));
        assert!(text.contains("待研究者复核"));
        assert!(text.contains("1. 先核对输入证据"));
        assert!(text.contains("2. 再核对模型假设"));
        if let Some(directory) = std::env::var_os("AI4HEOR_KEEP_TEST_REPORT") {
            let directory = PathBuf::from(directory);
            std::fs::create_dir_all(&directory).unwrap();
            std::fs::write(directory.join("heor-report.docx"), first_docx).unwrap();
            std::fs::write(directory.join("heor-report.pdf"), first_pdf).unwrap();
        }
    }

    #[test]
    fn xlsx_is_source_bound_deterministic_typed_and_formula_free() {
        let loaded = loaded_report(
            "# 摘要\n\n## 结果\n\n| 策略 | 成本（元） | QALY |\n| --- | ---: | ---: |\n| 对照 | 10000 | 1.00 |\n| 干预 | 20000 | 1.50 |\n\n## 局限性\n\n- 未覆盖全部结构不确定性。\n",
        );
        let first = build_xlsx(&loaded).unwrap();
        let second = build_xlsx(&loaded).unwrap();
        assert_eq!(first, second);
        assert!(first.starts_with(b"PK\x03\x04"));
        for required in [
            b"xl/workbook.xml".as_slice(),
            b"xl/styles.xml".as_slice(),
            b"xl/worksheets/sheet1.xml".as_slice(),
            b"xl/worksheets/sheet5.xml".as_slice(),
            "结果指标".as_bytes(),
            b"cost_effectiveness.delta_cost".as_slice(),
            b"heor/results/base-case.json".as_slice(),
            b"awaiting_human_review".as_slice(),
        ] {
            assert!(first.windows(required.len()).any(|part| part == required));
        }
        assert!(first
            .windows(b"t=\"n\"".len())
            .any(|part| part == b"t=\"n\""));
        assert!(!first.windows(b"<f>".len()).any(|part| part == b"<f>"));
        assert!(!first.windows(b"<f ".len()).any(|part| part == b"<f "));
        if let Some(directory) = std::env::var_os("AI4HEOR_KEEP_TEST_WORKBOOK") {
            let directory = PathBuf::from(directory);
            std::fs::create_dir_all(&directory).unwrap();
            std::fs::write(directory.join("heor-report.xlsx"), first).unwrap();
        }
    }

    #[test]
    fn xlsx_hash_participates_in_currentness_and_overwrite_protection() {
        let root = std::env::temp_dir().join(format!(
            "ai4heor-report-xlsx-current-{}",
            std::process::id()
        ));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("deliverables")).unwrap();
        let loaded = loaded_report(
            "# 摘要\n\n| 策略 | 成本（元） | QALY |\n| --- | ---: | ---: |\n| 对照 | 10000 | 1.00 |\n",
        );
        let docx = build_docx(&loaded).unwrap();
        let (pdf, page_count) = build_pdf(&loaded).unwrap();
        let xlsx = build_xlsx(&loaded).unwrap();
        let record = GenerationRecord {
            schema_version: "0.2.0".into(),
            generator: "ai4heor-native-report".into(),
            generator_version: ENGINE_VERSION.into(),
            document_id: loaded.manifest.document_id.clone(),
            manifest_path: REPORT_EXPORT_MANIFEST_PATH.into(),
            manifest_sha256: sha256(&loaded.manifest_raw),
            source_hashes: BTreeMap::from([
                ("report_document".into(), sha256(&loaded.report_raw)),
                ("report_package".into(), sha256(&loaded.package_raw)),
            ]),
            docx_path: REPORT_DOCX_OUTPUT_PATH.into(),
            docx_sha256: sha256(&docx),
            pdf_path: REPORT_PDF_OUTPUT_PATH.into(),
            pdf_sha256: sha256(&pdf),
            xlsx_path: Some(REPORT_XLSX_OUTPUT_PATH.into()),
            xlsx_sha256: Some(sha256(&xlsx)),
            block_count: loaded.blocks.len(),
            table_count: loaded.table_count,
            workbook_sheet_count: WORKBOOK_SHEET_COUNT,
            pdf_page_count: page_count,
            human_review_status: "awaiting_human_review".into(),
            font_name: FONT_NAME.into(),
            font_version: FONT_VERSION.into(),
            font_license: FONT_LICENSE.into(),
            font_sha256: FONT_SHA256.into(),
        };
        std::fs::write(root.join(REPORT_DOCX_OUTPUT_PATH), docx).unwrap();
        std::fs::write(root.join(REPORT_PDF_OUTPUT_PATH), pdf).unwrap();
        std::fs::write(root.join(REPORT_XLSX_OUTPUT_PATH), &xlsx).unwrap();
        std::fs::write(
            root.join(REPORT_EXPORT_AUDIT_PATH),
            serde_json::to_vec_pretty(&record).unwrap(),
        )
        .unwrap();

        let mut audit = empty_audit(String::new(), Vec::new());
        apply_current_outputs(&root, &loaded, &mut audit);
        assert!(audit.outputs_current);
        assert_eq!(audit.xlsx_sha256.as_deref(), Some(sha256(&xlsx).as_str()));
        assert_eq!(audit.workbook_sheet_count, WORKBOOK_SHEET_COUNT);
        assert!(existing_outputs_replaceable(&root).is_ok());

        let mut changed = xlsx;
        changed.push(b'!');
        std::fs::write(root.join(REPORT_XLSX_OUTPUT_PATH), changed).unwrap();
        let mut changed_audit = empty_audit(String::new(), Vec::new());
        apply_current_outputs(&root, &loaded, &mut changed_audit);
        assert!(!changed_audit.outputs_current);
        assert!(existing_outputs_replaceable(&root).is_err());
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn output_paths_and_font_admission_are_fixed() {
        assert!(safe_relative("heor/report.md"));
        assert!(!safe_relative("../report.md"));
        assert!(safe_relative(REPORT_DOCX_OUTPUT_PATH));
        assert!(safe_relative(REPORT_XLSX_OUTPUT_PATH));
        assert_eq!(sha256(PDF_FONT_BYTES), FONT_SHA256);
        let obfuscated = obfuscated_docx_font();
        assert_eq!(obfuscated.len(), PDF_FONT_BYTES.len());
        assert_ne!(&obfuscated[..32], &PDF_FONT_BYTES[..32]);
        assert_eq!(&obfuscated[32..], &PDF_FONT_BYTES[32..]);
        let mut recovered = obfuscated;
        xor_docx_font_prefix(&mut recovered);
        assert_eq!(sha256(&recovered), FONT_SHA256);
        assert_eq!(crc32(b"123456789"), 0xcbf4_3926);
    }
}
