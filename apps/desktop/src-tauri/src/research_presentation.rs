//! Deterministic, source-bound research-presentation generation.
//!
//! The Agent may prepare a manifest. The native app re-reads every source and
//! image, validates the bounded contract, and renders a macro-free PPTX. This
//! is a communication artifact, not scientific or external-use approval.
use sha2::{Digest, Sha256};
use std::collections::{BTreeMap, HashMap, HashSet};
use std::io::Write;
use std::path::{Component, Path, PathBuf};
use tauri::AppHandle;

pub const PRESENTATION_MANIFEST_PATH: &str = "deliverables/research-presentation.json";
pub const PRESENTATION_OUTPUT_PATH: &str = "deliverables/research-presentation.pptx";
pub const PRESENTATION_AUDIT_PATH: &str = "deliverables/research-presentation.audit.json";
const MANIFEST_CAP_BYTES: u64 = 1024 * 1024;
const SOURCE_CAP_BYTES: u64 = 25 * 1024 * 1024;
const IMAGE_CAP_BYTES: u64 = 10 * 1024 * 1024;
const OUTPUT_CAP_BYTES: usize = 50 * 1024 * 1024;
const ENGINE_VERSION: &str = "0.1.0";

#[derive(Clone, Debug, serde::Deserialize)]
struct PresentationManifest {
    schema_version: String,
    deck_id: String,
    title: String,
    #[serde(default)]
    subtitle: String,
    language: String,
    prepared_on: String,
    audience: String,
    purpose: String,
    theme: String,
    sources: Vec<PresentationSource>,
    slides: Vec<PresentationSlide>,
    human_review: HumanReview,
}

#[derive(Clone, Debug, serde::Deserialize)]
struct PresentationSource {
    source_id: String,
    path: String,
    sha256: String,
    label: String,
}

#[derive(Clone, Debug, serde::Deserialize)]
struct PresentationSlide {
    slide_id: String,
    kind: String,
    title: String,
    #[serde(default)]
    subtitle: String,
    #[serde(default)]
    bullets: Vec<String>,
    #[serde(default)]
    source_refs: Vec<String>,
    #[serde(default)]
    columns: Vec<String>,
    #[serde(default)]
    rows: Vec<Vec<String>>,
    #[serde(default)]
    caption: String,
    #[serde(default)]
    image_path: String,
    #[serde(default)]
    image_sha256: String,
    #[serde(default)]
    alt_text: String,
}

#[derive(Clone, Debug, serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct HumanReview {
    status: String,
}

#[derive(Clone, Debug)]
struct LoadedImage {
    bytes: Vec<u8>,
    extension: &'static str,
    width: u32,
    height: u32,
}

#[derive(Clone, Debug)]
struct LoadedPresentation {
    manifest: PresentationManifest,
    manifest_raw: Vec<u8>,
    source_hashes: BTreeMap<String, String>,
    images: HashMap<String, LoadedImage>,
}

#[derive(Clone, Debug, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct ResearchPresentationAudit {
    pub complete: bool,
    pub ready_to_generate: bool,
    pub output_current: bool,
    pub status: &'static str,
    pub deck_id: String,
    pub title: String,
    pub manifest_path: &'static str,
    pub output_path: &'static str,
    pub audit_path: &'static str,
    pub manifest_sha256: String,
    pub output_sha256: Option<String>,
    pub authored_slide_count: usize,
    pub rendered_slide_count: usize,
    pub source_count: usize,
    pub human_review_status: String,
    pub errors: Vec<String>,
}

#[derive(Clone, Debug, serde::Serialize, serde::Deserialize, PartialEq, Eq)]
struct GenerationRecord {
    schema_version: String,
    generator: String,
    generator_version: String,
    deck_id: String,
    manifest_path: String,
    manifest_sha256: String,
    source_hashes: BTreeMap<String, String>,
    output_path: String,
    output_sha256: String,
    authored_slide_count: usize,
    rendered_slide_count: usize,
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

fn safe_id(value: &str, lowercase_first: bool) -> bool {
    if value.is_empty() || value.len() > 64 {
        return false;
    }
    value.bytes().enumerate().all(|(index, byte)| {
        if index == 0 && lowercase_first {
            byte.is_ascii_lowercase()
        } else if index == 0 {
            byte.is_ascii_alphanumeric()
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

fn valid_language(value: &str) -> bool {
    if !(2..=16).contains(&value.len()) {
        return false;
    }
    let parts = value.split('-').collect::<Vec<_>>();
    if !(1..=3).contains(&parts.len()) {
        return false;
    }
    parts.iter().enumerate().all(|(index, part)| {
        let range = if index == 0 { 2..=8 } else { 2..=8 };
        range.contains(&part.len())
            && part.bytes().all(|byte| {
                if index == 0 {
                    byte.is_ascii_alphabetic()
                } else {
                    byte.is_ascii_alphanumeric()
                }
            })
    })
}

fn safe_relative(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 240
        && !value.contains('\\')
        && value != PRESENTATION_OUTPUT_PATH
        && value != PRESENTATION_AUDIT_PATH
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

fn image_dimensions(raw: &[u8], extension: &str) -> Option<(u32, u32)> {
    if extension == "png" {
        if raw.len() >= 24 && raw.starts_with(b"\x89PNG\r\n\x1a\n") {
            let width = u32::from_be_bytes(raw[16..20].try_into().ok()?);
            let height = u32::from_be_bytes(raw[20..24].try_into().ok()?);
            return (width > 0 && height > 0).then_some((width, height));
        }
        return None;
    }
    if extension != "jpeg" || raw.len() < 4 || !raw.starts_with(&[0xff, 0xd8]) {
        return None;
    }
    let mut offset = 2usize;
    while offset + 4 <= raw.len() {
        if raw[offset] != 0xff {
            offset += 1;
            continue;
        }
        let marker = raw[offset + 1];
        offset += 2;
        if matches!(marker, 0xd8 | 0xd9) || (0xd0..=0xd7).contains(&marker) {
            continue;
        }
        if offset + 2 > raw.len() {
            return None;
        }
        let length = u16::from_be_bytes([raw[offset], raw[offset + 1]]) as usize;
        if length < 2 || offset + length > raw.len() {
            return None;
        }
        if matches!(
            marker,
            0xc0 | 0xc1
                | 0xc2
                | 0xc3
                | 0xc5
                | 0xc6
                | 0xc7
                | 0xc9
                | 0xca
                | 0xcb
                | 0xcd
                | 0xce
                | 0xcf
        ) && length >= 7
        {
            let height = u16::from_be_bytes([raw[offset + 3], raw[offset + 4]]) as u32;
            let width = u16::from_be_bytes([raw[offset + 5], raw[offset + 6]]) as u32;
            return (width > 0 && height > 0).then_some((width, height));
        }
        offset += length;
    }
    None
}

fn unique_texts(values: &[String], minimum: usize, maximum: usize, length: usize) -> bool {
    (minimum..=maximum).contains(&values.len())
        && values.iter().all(|value| valid_text(value, 1, length))
        && values.iter().collect::<HashSet<_>>().len() == values.len()
}

fn validate_manifest(
    workspace: &Path,
    raw: Vec<u8>,
) -> (ResearchPresentationAudit, Option<LoadedPresentation>) {
    let manifest_sha256 = sha256(&raw);
    let parsed = serde_json::from_slice::<PresentationManifest>(&raw);
    let mut audit = ResearchPresentationAudit {
        complete: false,
        ready_to_generate: false,
        output_current: false,
        status: "invalid",
        deck_id: String::new(),
        title: String::new(),
        manifest_path: PRESENTATION_MANIFEST_PATH,
        output_path: PRESENTATION_OUTPUT_PATH,
        audit_path: PRESENTATION_AUDIT_PATH,
        manifest_sha256,
        output_sha256: None,
        authored_slide_count: 0,
        rendered_slide_count: 0,
        source_count: 0,
        human_review_status: String::new(),
        errors: Vec::new(),
    };
    let Ok(manifest) = parsed else {
        audit.errors.push(format!(
            "{PRESENTATION_MANIFEST_PATH} is invalid JSON: {}",
            parsed.unwrap_err()
        ));
        return (audit, None);
    };
    audit.deck_id = manifest.deck_id.clone();
    audit.title = manifest.title.clone();
    audit.authored_slide_count = manifest.slides.len();
    audit.source_count = manifest.sources.len();
    audit.human_review_status = manifest.human_review.status.clone();
    if manifest.schema_version != "0.1.0" {
        audit.errors.push("schema_version must be 0.1.0".into());
    }
    if !safe_id(&manifest.deck_id, true) {
        audit
            .errors
            .push("deck_id must be a lowercase safe 1-64 character ID".into());
    }
    for (field, value, maximum) in [
        ("title", manifest.title.as_str(), 120),
        ("audience", manifest.audience.as_str(), 160),
        ("purpose", manifest.purpose.as_str(), 240),
    ] {
        if !valid_text(value, 1, maximum) {
            audit.errors.push(format!(
                "{field} is required and must be at most {maximum} characters"
            ));
        }
    }
    if !valid_text(&manifest.subtitle, 0, 200) {
        audit
            .errors
            .push("subtitle must be at most 200 characters".into());
    }
    if !valid_language(&manifest.language) {
        audit
            .errors
            .push("language must be a compact BCP-47 language tag".into());
    }
    if !valid_date(&manifest.prepared_on) {
        audit.errors.push("prepared_on must be YYYY-MM-DD".into());
    }
    if manifest.theme != "ai4heor-paper" {
        audit.errors.push("theme must be ai4heor-paper".into());
    }
    if manifest.human_review.status != "awaiting_human_review" {
        audit
            .errors
            .push("human_review.status must be awaiting_human_review".into());
    }
    if !(1..=30).contains(&manifest.sources.len()) {
        audit
            .errors
            .push("sources must contain 1-30 entries".into());
    }
    if !(3..=30).contains(&manifest.slides.len()) {
        audit
            .errors
            .push("slides must contain 3-30 authored slides".into());
    }

    let mut source_ids = HashSet::new();
    let mut source_paths = HashSet::new();
    let mut source_hashes = BTreeMap::new();
    for (index, source) in manifest.sources.iter().enumerate() {
        let prefix = format!("sources[{index}]");
        if !safe_id(&source.source_id, false) || !source_ids.insert(source.source_id.clone()) {
            audit
                .errors
                .push(format!("{prefix}.source_id must be a unique safe ID"));
        }
        if !safe_relative(&source.path) || !source_paths.insert(source.path.clone()) {
            audit.errors.push(format!(
                "{prefix}.path must be a unique safe workspace-relative path"
            ));
            continue;
        }
        if !valid_sha256(&source.sha256) {
            audit
                .errors
                .push(format!("{prefix}.sha256 must be a lowercase SHA-256"));
        }
        if !valid_text(&source.label, 1, 160) {
            audit.errors.push(format!(
                "{prefix}.label is required and must be at most 160 characters"
            ));
        }
        match resolve_regular(workspace, &source.path, SOURCE_CAP_BYTES) {
            Ok((_, bytes)) => {
                let actual = sha256(&bytes);
                if actual != source.sha256 {
                    audit.errors.push(format!(
                        "{} does not match its declared SHA-256",
                        source.path
                    ));
                }
                source_hashes.insert(source.source_id.clone(), actual);
            }
            Err(error) => audit.errors.push(error),
        }
    }

    if manifest
        .slides
        .first()
        .is_none_or(|slide| slide.kind != "title")
    {
        audit
            .errors
            .push("the first slide must have kind=title".into());
    }
    if manifest
        .slides
        .last()
        .is_none_or(|slide| slide.kind != "closing")
    {
        audit
            .errors
            .push("the last slide must have kind=closing".into());
    }
    let mut slide_ids = HashSet::new();
    let mut limitation_count = 0usize;
    let mut images = HashMap::new();
    for (index, slide) in manifest.slides.iter().enumerate() {
        let prefix = format!("slides[{index}]");
        if !safe_id(&slide.slide_id, false) || !slide_ids.insert(slide.slide_id.clone()) {
            audit
                .errors
                .push(format!("{prefix}.slide_id must be a unique safe ID"));
        }
        if !matches!(
            slide.kind.as_str(),
            "title" | "section" | "content" | "table" | "figure" | "limitations" | "closing"
        ) {
            audit.errors.push(format!("{prefix}.kind is not supported"));
            continue;
        }
        if !valid_text(&slide.title, 1, 120) {
            audit.errors.push(format!(
                "{prefix}.title is required and must be at most 120 characters"
            ));
        }
        let evidence_bearing = matches!(
            slide.kind.as_str(),
            "content" | "table" | "figure" | "limitations"
        );
        if evidence_bearing {
            if !unique_texts(&slide.source_refs, 1, 8, 64)
                || slide
                    .source_refs
                    .iter()
                    .any(|reference| !source_ids.contains(reference))
            {
                audit.errors.push(format!(
                    "{prefix}.source_refs must contain 1-8 unique declared source IDs"
                ));
            }
        } else if !slide.source_refs.is_empty() {
            audit.errors.push(format!(
                "{prefix}.source_refs is not allowed for {} slides",
                slide.kind
            ));
        }
        if matches!(slide.kind.as_str(), "title" | "section")
            && !valid_text(&slide.subtitle, 0, 200)
        {
            audit
                .errors
                .push(format!("{prefix}.subtitle must be at most 200 characters"));
        }
        if matches!(slide.kind.as_str(), "content" | "limitations" | "closing") {
            let maximum = if slide.kind == "closing" { 5 } else { 8 };
            if !unique_texts(&slide.bullets, 1, maximum, 240) {
                audit.errors.push(format!(
                    "{prefix}.bullets must contain 1-{maximum} unique entries of at most 240 characters"
                ));
            }
        }
        if slide.kind == "limitations" {
            limitation_count += 1;
        }
        if slide.kind == "table" {
            if !unique_texts(&slide.columns, 2, 8, 80) {
                audit
                    .errors
                    .push(format!("{prefix}.columns must contain 2-8 unique labels"));
            }
            if !(1..=20).contains(&slide.rows.len()) {
                audit
                    .errors
                    .push(format!("{prefix}.rows must contain 1-20 rows"));
            }
            for (row_index, row) in slide.rows.iter().enumerate() {
                if row.len() != slide.columns.len()
                    || row.iter().any(|cell| !valid_text(cell, 0, 120))
                {
                    audit.errors.push(format!(
                        "{prefix}.rows[{row_index}] must match the columns and contain cells of at most 120 characters"
                    ));
                }
            }
            if !valid_text(&slide.caption, 0, 300) {
                audit
                    .errors
                    .push(format!("{prefix}.caption must be at most 300 characters"));
            }
        }
        if slide.kind == "figure" {
            let extension = Path::new(&slide.image_path)
                .extension()
                .and_then(|value| value.to_str())
                .map(str::to_ascii_lowercase);
            let normalized_extension = match extension.as_deref() {
                Some("png") => Some("png"),
                Some("jpg" | "jpeg") => Some("jpeg"),
                _ => None,
            };
            if !safe_relative(&slide.image_path) || normalized_extension.is_none() {
                audit.errors.push(format!(
                    "{prefix}.image_path must be a safe local PNG or JPEG path"
                ));
            }
            if !valid_sha256(&slide.image_sha256) {
                audit
                    .errors
                    .push(format!("{prefix}.image_sha256 must be a lowercase SHA-256"));
            }
            if !valid_text(&slide.alt_text, 10, 400) {
                audit
                    .errors
                    .push(format!("{prefix}.alt_text must contain 10-400 characters"));
            }
            if !valid_text(&slide.caption, 0, 300) {
                audit
                    .errors
                    .push(format!("{prefix}.caption must be at most 300 characters"));
            }
            if let Some(extension) = normalized_extension {
                match resolve_regular(workspace, &slide.image_path, IMAGE_CAP_BYTES) {
                    Ok((_, bytes)) => {
                        let actual = sha256(&bytes);
                        if actual != slide.image_sha256 {
                            audit.errors.push(format!(
                                "{} does not match its declared image SHA-256",
                                slide.image_path
                            ));
                        }
                        match image_dimensions(&bytes, extension) {
                            Some((width, height)) => {
                                images.insert(
                                    slide.slide_id.clone(),
                                    LoadedImage {
                                        bytes,
                                        extension,
                                        width,
                                        height,
                                    },
                                );
                            }
                            None => audit.errors.push(format!(
                                "{} is not a readable {extension} image",
                                slide.image_path
                            )),
                        }
                    }
                    Err(error) => audit.errors.push(error),
                }
            }
        }
    }
    if limitation_count == 0 {
        audit
            .errors
            .push("at least one limitations slide is required".into());
    }
    let source_slide_count = manifest.sources.len().div_ceil(6);
    audit.rendered_slide_count = manifest.slides.len() + source_slide_count;
    if !audit.errors.is_empty() {
        return (audit, None);
    }
    audit.complete = true;
    audit.ready_to_generate = true;
    audit.status = "ready_to_generate";
    let loaded = LoadedPresentation {
        manifest,
        manifest_raw: raw,
        source_hashes,
        images,
    };
    (audit, Some(loaded))
}

fn read_manifest(workspace: &Path) -> Result<Vec<u8>, String> {
    let path = workspace.join(PRESENTATION_MANIFEST_PATH);
    let metadata = std::fs::symlink_metadata(&path)
        .map_err(|error| format!("{PRESENTATION_MANIFEST_PATH} unavailable: {error}"))?;
    if metadata.file_type().is_symlink()
        || !metadata.is_file()
        || metadata.len() > MANIFEST_CAP_BYTES
    {
        return Err(format!(
            "{PRESENTATION_MANIFEST_PATH} must be a regular JSON file no larger than 1 MiB"
        ));
    }
    std::fs::read(path)
        .map_err(|error| format!("{PRESENTATION_MANIFEST_PATH} unavailable: {error}"))
}

fn audit_at(workspace: &Path) -> (ResearchPresentationAudit, Option<LoadedPresentation>) {
    let raw = match read_manifest(workspace) {
        Ok(raw) => raw,
        Err(error) => {
            return (
                ResearchPresentationAudit {
                    complete: false,
                    ready_to_generate: false,
                    output_current: false,
                    status: "missing",
                    deck_id: String::new(),
                    title: String::new(),
                    manifest_path: PRESENTATION_MANIFEST_PATH,
                    output_path: PRESENTATION_OUTPUT_PATH,
                    audit_path: PRESENTATION_AUDIT_PATH,
                    manifest_sha256: String::new(),
                    output_sha256: None,
                    authored_slide_count: 0,
                    rendered_slide_count: 0,
                    source_count: 0,
                    human_review_status: "awaiting_human_review".into(),
                    errors: vec![error],
                },
                None,
            );
        }
    };
    let (mut audit, loaded) = validate_manifest(workspace, raw);
    let Some(loaded_ref) = loaded.as_ref() else {
        return (audit, loaded);
    };
    let record_raw = std::fs::read(workspace.join(PRESENTATION_AUDIT_PATH)).ok();
    let output_raw = std::fs::read(workspace.join(PRESENTATION_OUTPUT_PATH)).ok();
    if let (Some(record_raw), Some(output_raw)) = (record_raw, output_raw) {
        let actual_output = sha256(&output_raw);
        let expected = GenerationRecord {
            schema_version: "0.1.0".into(),
            generator: "ai4heor-native-presentation".into(),
            generator_version: ENGINE_VERSION.into(),
            deck_id: loaded_ref.manifest.deck_id.clone(),
            manifest_path: PRESENTATION_MANIFEST_PATH.into(),
            manifest_sha256: sha256(&loaded_ref.manifest_raw),
            source_hashes: loaded_ref.source_hashes.clone(),
            output_path: PRESENTATION_OUTPUT_PATH.into(),
            output_sha256: actual_output.clone(),
            authored_slide_count: loaded_ref.manifest.slides.len(),
            rendered_slide_count: audit.rendered_slide_count,
            human_review_status: "awaiting_human_review".into(),
        };
        if serde_json::from_slice::<GenerationRecord>(&record_raw)
            .ok()
            .as_ref()
            == Some(&expected)
        {
            audit.output_current = true;
            audit.output_sha256 = Some(actual_output);
            audit.status = "generated_current";
        }
    }
    (audit, loaded)
}

fn xml_escape(value: &str) -> String {
    let mut result = String::with_capacity(value.len());
    for character in value.chars() {
        match character {
            '&' => result.push_str("&amp;"),
            '<' => result.push_str("&lt;"),
            '>' => result.push_str("&gt;"),
            '"' => result.push_str("&quot;"),
            '\'' => result.push_str("&apos;"),
            _ => result.push(character),
        }
    }
    result
}

const EMU: i64 = 914_400;
fn inch(value: f64) -> i64 {
    (value * EMU as f64).round() as i64
}

#[derive(Clone)]
struct Paragraph<'a> {
    text: &'a str,
    size: u32,
    bold: bool,
    color: &'a str,
    bullet: bool,
    align: &'a str,
}

fn paragraph_xml(paragraph: &Paragraph<'_>) -> String {
    let bullet = if paragraph.bullet {
        "<a:buChar char=\"\u{2022}\"/>"
    } else {
        "<a:buNone/>"
    };
    let margins = if paragraph.bullet {
        " marL=\"342900\" indent=\"-228600\""
    } else {
        ""
    };
    format!(
        "<a:p><a:pPr algn=\"{}\"{}>{}</a:pPr><a:r><a:rPr lang=\"en-US\" sz=\"{}\" b=\"{}\"><a:solidFill><a:srgbClr val=\"{}\"/></a:solidFill><a:latin typeface=\"Aptos\"/><a:ea typeface=\"Aptos\"/></a:rPr><a:t>{}</a:t></a:r><a:endParaRPr lang=\"en-US\" sz=\"{}\"/></a:p>",
        paragraph.align,
        margins,
        bullet,
        paragraph.size,
        if paragraph.bold { 1 } else { 0 },
        paragraph.color,
        xml_escape(paragraph.text),
        paragraph.size,
    )
}

#[allow(clippy::too_many_arguments)]
fn text_box(
    id: u32,
    name: &str,
    x: f64,
    y: f64,
    width: f64,
    height: f64,
    paragraphs: &[Paragraph<'_>],
    fill: Option<&str>,
    line: Option<&str>,
    margin: f64,
    vertical: &str,
) -> String {
    let fill = fill.map_or_else(
        || "<a:noFill/>".to_string(),
        |color| format!("<a:solidFill><a:srgbClr val=\"{color}\"/></a:solidFill>"),
    );
    let line = line.map_or_else(
        || "<a:ln><a:noFill/></a:ln>".to_string(),
        |color| {
            format!(
                "<a:ln w=\"12700\"><a:solidFill><a:srgbClr val=\"{color}\"/></a:solidFill></a:ln>"
            )
        },
    );
    let body = paragraphs.iter().map(paragraph_xml).collect::<String>();
    let margin = inch(margin);
    format!(
        "<p:sp><p:nvSpPr><p:cNvPr id=\"{id}\" name=\"{}\"/><p:cNvSpPr txBox=\"1\"/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x=\"{}\" y=\"{}\"/><a:ext cx=\"{}\" cy=\"{}\"/></a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom>{fill}{line}</p:spPr><p:txBody><a:bodyPr wrap=\"square\" anchor=\"{vertical}\" lIns=\"{margin}\" rIns=\"{margin}\" tIns=\"{margin}\" bIns=\"{margin}\"/><a:lstStyle/>{body}</p:txBody></p:sp>",
        xml_escape(name),
        inch(x),
        inch(y),
        inch(width),
        inch(height),
    )
}

fn rect_shape(id: u32, name: &str, x: f64, y: f64, width: f64, height: f64, fill: &str) -> String {
    format!(
        "<p:sp><p:nvSpPr><p:cNvPr id=\"{id}\" name=\"{}\"/><p:cNvSpPr/><p:nvPr/></p:nvSpPr><p:spPr><a:xfrm><a:off x=\"{}\" y=\"{}\"/><a:ext cx=\"{}\" cy=\"{}\"/></a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom><a:solidFill><a:srgbClr val=\"{fill}\"/></a:solidFill><a:ln><a:noFill/></a:ln></p:spPr></p:sp>",
        xml_escape(name), inch(x), inch(y), inch(width), inch(height)
    )
}

#[allow(clippy::too_many_arguments)]
fn picture_shape(
    id: u32,
    name: &str,
    description: &str,
    relationship: &str,
    x: f64,
    y: f64,
    width: f64,
    height: f64,
) -> String {
    format!(
        "<p:pic><p:nvPicPr><p:cNvPr id=\"{id}\" name=\"{}\" descr=\"{}\"/><p:cNvPicPr><a:picLocks noChangeAspect=\"1\"/></p:cNvPicPr><p:nvPr/></p:nvPicPr><p:blipFill><a:blip r:embed=\"{relationship}\"/><a:stretch><a:fillRect/></a:stretch></p:blipFill><p:spPr><a:xfrm><a:off x=\"{}\" y=\"{}\"/><a:ext cx=\"{}\" cy=\"{}\"/></a:xfrm><a:prstGeom prst=\"rect\"><a:avLst/></a:prstGeom></p:spPr></p:pic>",
        xml_escape(name),
        xml_escape(description),
        inch(x), inch(y), inch(width), inch(height)
    )
}

fn body_font_size(bullets: &[String]) -> u32 {
    let longest = bullets
        .iter()
        .map(|value| value.chars().count())
        .max()
        .unwrap_or(0);
    if bullets.len() <= 5 && longest <= 100 {
        1_800
    } else if bullets.len() <= 7 && longest <= 160 {
        1_550
    } else {
        1_350
    }
}

fn source_footer(slide: &PresentationSlide) -> String {
    if slide.source_refs.is_empty() {
        String::new()
    } else {
        format!("Sources: {}", slide.source_refs.join(" · "))
    }
}

fn base_slide_shapes(slide_number: usize, title: &str, accent: &str) -> String {
    let mut shapes = rect_shape(2, "Background", 0.0, 0.0, 13.333, 7.5, "F7F5EF");
    shapes.push_str(&rect_shape(3, "Accent", 0.0, 0.0, 0.16, 7.5, accent));
    shapes.push_str(&text_box(
        4,
        "AI4HEOR",
        0.68,
        0.28,
        2.0,
        0.35,
        &[Paragraph {
            text: "AI4HEOR",
            size: 900,
            bold: true,
            color: accent,
            bullet: false,
            align: "l",
        }],
        None,
        None,
        0.0,
        "ctr",
    ));
    shapes.push_str(&text_box(
        5,
        "Slide title",
        0.68,
        0.7,
        11.7,
        0.78,
        &[Paragraph {
            text: title,
            size: 2_500,
            bold: true,
            color: "2A2723",
            bullet: false,
            align: "l",
        }],
        None,
        None,
        0.0,
        "ctr",
    ));
    shapes.push_str(&text_box(
        6,
        "Slide number",
        12.2,
        7.08,
        0.5,
        0.2,
        &[Paragraph {
            text: &slide_number.to_string(),
            size: 800,
            bold: false,
            color: "746F67",
            bullet: false,
            align: "r",
        }],
        None,
        None,
        0.0,
        "ctr",
    ));
    shapes
}

fn standard_slide_shapes(
    slide: &PresentationSlide,
    slide_number: usize,
) -> (String, Option<String>) {
    let accent = if slide.kind == "limitations" {
        "AD5335"
    } else {
        "2A78D6"
    };
    let mut shapes = base_slide_shapes(slide_number, &slide.title, accent);
    let mut image_relationship = None;
    match slide.kind.as_str() {
        "title" => {
            shapes = rect_shape(2, "Background", 0.0, 0.0, 13.333, 7.5, "F7F5EF");
            shapes.push_str(&rect_shape(3, "Accent", 0.0, 0.0, 0.22, 7.5, "AD5335"));
            shapes.push_str(&text_box(
                4,
                "Wordmark",
                0.9,
                0.72,
                2.5,
                0.45,
                &[Paragraph {
                    text: "AI4HEOR",
                    size: 1_100,
                    bold: true,
                    color: "AD5335",
                    bullet: false,
                    align: "l",
                }],
                None,
                None,
                0.0,
                "ctr",
            ));
            shapes.push_str(&text_box(
                5,
                "Title",
                0.9,
                1.7,
                11.3,
                2.0,
                &[Paragraph {
                    text: &slide.title,
                    size: 3_600,
                    bold: true,
                    color: "2A2723",
                    bullet: false,
                    align: "l",
                }],
                None,
                None,
                0.0,
                "ctr",
            ));
            if !slide.subtitle.is_empty() {
                shapes.push_str(&text_box(
                    6,
                    "Subtitle",
                    0.92,
                    4.0,
                    10.8,
                    1.0,
                    &[Paragraph {
                        text: &slide.subtitle,
                        size: 1_800,
                        bold: false,
                        color: "746F67",
                        bullet: false,
                        align: "l",
                    }],
                    None,
                    None,
                    0.0,
                    "t",
                ));
            }
        }
        "section" => {
            shapes = rect_shape(2, "Background", 0.0, 0.0, 13.333, 7.5, "2A2723");
            shapes.push_str(&rect_shape(3, "Accent", 0.0, 0.0, 0.22, 7.5, "AD5335"));
            shapes.push_str(&text_box(
                4,
                "Section title",
                1.0,
                2.15,
                11.0,
                1.6,
                &[Paragraph {
                    text: &slide.title,
                    size: 3_400,
                    bold: true,
                    color: "FFFFFF",
                    bullet: false,
                    align: "l",
                }],
                None,
                None,
                0.0,
                "ctr",
            ));
            if !slide.subtitle.is_empty() {
                shapes.push_str(&text_box(
                    5,
                    "Section subtitle",
                    1.02,
                    4.0,
                    10.5,
                    0.9,
                    &[Paragraph {
                        text: &slide.subtitle,
                        size: 1_700,
                        bold: false,
                        color: "CBC6BB",
                        bullet: false,
                        align: "l",
                    }],
                    None,
                    None,
                    0.0,
                    "t",
                ));
            }
        }
        "content" | "limitations" | "closing" => {
            let size = body_font_size(&slide.bullets);
            let paragraphs = slide
                .bullets
                .iter()
                .map(|bullet| Paragraph {
                    text: bullet,
                    size,
                    bold: false,
                    color: "2A2723",
                    bullet: true,
                    align: "l",
                })
                .collect::<Vec<_>>();
            shapes.push_str(&text_box(
                7,
                "Bullets",
                0.84,
                1.65,
                11.6,
                4.9,
                &paragraphs,
                if slide.kind == "limitations" {
                    Some("F2EFE7")
                } else {
                    None
                },
                if slide.kind == "limitations" {
                    Some("E7E3DA")
                } else {
                    None
                },
                if slide.kind == "limitations" {
                    0.28
                } else {
                    0.0
                },
                "t",
            ));
        }
        "table" => {
            let rows = slide.rows.len() + 1;
            let row_height = 4.65 / rows as f64;
            let column_width = 11.65 / slide.columns.len() as f64;
            let size = if rows <= 9 {
                1_100
            } else if rows <= 15 {
                900
            } else {
                750
            };
            let mut id = 7u32;
            for (row_index, row) in std::iter::once(&slide.columns)
                .chain(slide.rows.iter())
                .enumerate()
            {
                for (column_index, cell) in row.iter().enumerate() {
                    shapes.push_str(&text_box(
                        id,
                        "Table cell",
                        0.82 + column_width * column_index as f64,
                        1.58 + row_height * row_index as f64,
                        column_width,
                        row_height,
                        &[Paragraph {
                            text: cell,
                            size,
                            bold: row_index == 0,
                            color: if row_index == 0 { "FFFFFF" } else { "2A2723" },
                            bullet: false,
                            align: if column_index == 0 { "l" } else { "ctr" },
                        }],
                        Some(if row_index == 0 {
                            "2A2723"
                        } else if row_index % 2 == 0 {
                            "F2EFE7"
                        } else {
                            "FFFFFF"
                        }),
                        Some("E7E3DA"),
                        0.06,
                        "ctr",
                    ));
                    id += 1;
                }
            }
            if !slide.caption.is_empty() {
                shapes.push_str(&text_box(
                    id,
                    "Table caption",
                    0.84,
                    6.36,
                    11.4,
                    0.42,
                    &[Paragraph {
                        text: &slide.caption,
                        size: 900,
                        bold: false,
                        color: "746F67",
                        bullet: false,
                        align: "l",
                    }],
                    None,
                    None,
                    0.0,
                    "t",
                ));
            }
        }
        "figure" => {
            image_relationship = Some(slide.slide_id.clone());
        }
        _ => {}
    }
    let footer = source_footer(slide);
    if !footer.is_empty() {
        shapes.push_str(&text_box(
            240,
            "Source references",
            0.84,
            6.86,
            10.8,
            0.24,
            &[Paragraph {
                text: &footer,
                size: 750,
                bold: false,
                color: "746F67",
                bullet: false,
                align: "l",
            }],
            None,
            None,
            0.0,
            "ctr",
        ));
    }
    (shapes, image_relationship)
}

fn sources_title(language: &str) -> &'static str {
    if language.starts_with("zh") {
        "资料与文件"
    } else if language.starts_with("ja") {
        "資料とファイル"
    } else if language.starts_with("ko") {
        "출처 및 파일"
    } else if language.starts_with("de") {
        "Quellen und Dateien"
    } else if language.starts_with("fr") {
        "Sources et fichiers"
    } else if language.starts_with("es") {
        "Fuentes y archivos"
    } else {
        "Sources and files"
    }
}

fn source_slide_shapes(sources: &[PresentationSource], title: &str, slide_number: usize) -> String {
    let mut shapes = base_slide_shapes(slide_number, title, "2A78D6");
    let lines = sources
        .iter()
        .map(|source| {
            let hash = source.sha256.get(..12).unwrap_or(&source.sha256);
            format!(
                "{}  {}  ·  {}  ·  {}\u{2026}",
                source.source_id, source.label, source.path, hash
            )
        })
        .collect::<Vec<_>>();
    let paragraphs = lines
        .iter()
        .map(|line| Paragraph {
            text: line,
            size: 1_150,
            bold: false,
            color: "2A2723",
            bullet: false,
            align: "l",
        })
        .collect::<Vec<_>>();
    shapes.push_str(&text_box(
        7,
        "Sources",
        0.84,
        1.62,
        11.6,
        5.3,
        &paragraphs,
        Some("FFFFFF"),
        Some("E7E3DA"),
        0.26,
        "t",
    ));
    shapes
}

fn slide_xml(shapes: &str) -> Vec<u8> {
    format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><p:sld xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"><p:cSld><p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/><a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm></p:grpSpPr>{shapes}</p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sld>"
    )
    .into_bytes()
}

fn slide_rels(image: Option<(usize, &str)>) -> Vec<u8> {
    let mut relationships = String::from(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout\" Target=\"../slideLayouts/slideLayout1.xml\"/>",
    );
    if let Some((media_index, extension)) = image {
        relationships.push_str(&format!("<Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/image\" Target=\"../media/image{media_index}.{extension}\"/>"));
    }
    relationships.push_str("</Relationships>");
    relationships.into_bytes()
}

fn fixed_package_parts(
    manifest: &PresentationManifest,
    slide_count: usize,
) -> Vec<(String, Vec<u8>)> {
    let slide_overrides = (1..=slide_count)
        .map(|index| format!("<Override PartName=\"/ppt/slides/slide{index}.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.slide+xml\"/>"))
        .collect::<String>();
    let content_types = format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\"><Default Extension=\"rels\" ContentType=\"application/vnd.openxmlformats-package.relationships+xml\"/><Default Extension=\"xml\" ContentType=\"application/xml\"/><Default Extension=\"png\" ContentType=\"image/png\"/><Default Extension=\"jpeg\" ContentType=\"image/jpeg\"/><Override PartName=\"/ppt/presentation.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml\"/><Override PartName=\"/ppt/slideMasters/slideMaster1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.slideMaster+xml\"/><Override PartName=\"/ppt/slideLayouts/slideLayout1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.slideLayout+xml\"/><Override PartName=\"/ppt/theme/theme1.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.theme+xml\"/><Override PartName=\"/ppt/presProps.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.presProps+xml\"/><Override PartName=\"/ppt/viewProps.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.viewProps+xml\"/><Override PartName=\"/ppt/tableStyles.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.presentationml.tableStyles+xml\"/><Override PartName=\"/docProps/core.xml\" ContentType=\"application/vnd.openxmlformats-package.core-properties+xml\"/><Override PartName=\"/docProps/app.xml\" ContentType=\"application/vnd.openxmlformats-officedocument.extended-properties+xml\"/>{slide_overrides}</Types>"
    );
    let slide_ids = (1..=slide_count)
        .map(|index| {
            format!(
                "<p:sldId id=\"{}\" r:id=\"rId{}\"/>",
                255 + index,
                index + 4
            )
        })
        .collect::<String>();
    let presentation = format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><p:presentation xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"><p:sldMasterIdLst><p:sldMasterId id=\"2147483648\" r:id=\"rId1\"/></p:sldMasterIdLst><p:sldIdLst>{slide_ids}</p:sldIdLst><p:sldSz cx=\"12192000\" cy=\"6858000\" type=\"screen16x9\"/><p:notesSz cx=\"6858000\" cy=\"9144000\"/><p:defaultTextStyle><a:defPPr><a:defRPr lang=\"{}\"/></a:defPPr></p:defaultTextStyle></p:presentation>",
        xml_escape(&manifest.language)
    );
    let slide_relationships = (1..=slide_count)
        .map(|index| format!("<Relationship Id=\"rId{}\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slide\" Target=\"slides/slide{index}.xml\"/>", index + 4))
        .collect::<String>();
    let presentation_rels = format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster\" Target=\"slideMasters/slideMaster1.xml\"/><Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/presProps\" Target=\"presProps.xml\"/><Relationship Id=\"rId3\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/viewProps\" Target=\"viewProps.xml\"/><Relationship Id=\"rId4\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/tableStyles\" Target=\"tableStyles.xml\"/>{slide_relationships}</Relationships>"
    );
    let core = format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><cp:coreProperties xmlns:cp=\"http://schemas.openxmlformats.org/package/2006/metadata/core-properties\" xmlns:dc=\"http://purl.org/dc/elements/1.1/\" xmlns:dcterms=\"http://purl.org/dc/terms/\" xmlns:dcmitype=\"http://purl.org/dc/dcmitype/\" xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\"><dc:title>{}</dc:title><dc:subject>{}</dc:subject><dc:creator>AI4HEOR</dc:creator><cp:lastModifiedBy>AI4HEOR</cp:lastModifiedBy><dcterms:created xsi:type=\"dcterms:W3CDTF\">{}T00:00:00Z</dcterms:created><dcterms:modified xsi:type=\"dcterms:W3CDTF\">{}T00:00:00Z</dcterms:modified></cp:coreProperties>",
        xml_escape(&manifest.title),
        xml_escape(&manifest.purpose),
        manifest.prepared_on,
        manifest.prepared_on,
    );
    let app = format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Properties xmlns=\"http://schemas.openxmlformats.org/officeDocument/2006/extended-properties\" xmlns:vt=\"http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes\"><Application>AI4HEOR</Application><PresentationFormat>Widescreen</PresentationFormat><Slides>{slide_count}</Slides><Company>AI4HEOR</Company><AppVersion>0.1</AppVersion></Properties>"
    );
    let root_rels = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument\" Target=\"ppt/presentation.xml\"/><Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties\" Target=\"docProps/core.xml\"/><Relationship Id=\"rId3\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties\" Target=\"docProps/app.xml\"/></Relationships>";
    let master = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><p:sldMaster xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"><p:cSld name=\"AI4HEOR\"><p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/><a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld><p:clrMap accent1=\"accent1\" accent2=\"accent2\" accent3=\"accent3\" accent4=\"accent4\" accent5=\"accent5\" accent6=\"accent6\" bg1=\"lt1\" bg2=\"lt2\" folHlink=\"folHlink\" hlink=\"hlink\" tx1=\"dk1\" tx2=\"dk2\"/><p:sldLayoutIdLst><p:sldLayoutId id=\"1\" r:id=\"rId1\"/></p:sldLayoutIdLst><p:txStyles><p:titleStyle><a:lvl1pPr algn=\"l\"><a:defRPr sz=\"3200\" b=\"1\"/></a:lvl1pPr></p:titleStyle><p:bodyStyle><a:lvl1pPr marL=\"342900\" indent=\"-228600\"><a:buChar char=\"\u{2022}\"/><a:defRPr sz=\"1800\"/></a:lvl1pPr></p:bodyStyle><p:otherStyle><a:defPPr><a:defRPr sz=\"1200\"/></a:defPPr></p:otherStyle></p:txStyles></p:sldMaster>";
    let master_rels = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideLayout\" Target=\"../slideLayouts/slideLayout1.xml\"/><Relationship Id=\"rId2\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/theme\" Target=\"../theme/theme1.xml\"/></Relationships>";
    let layout = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><p:sldLayout xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\" type=\"blank\" preserve=\"1\"><p:cSld name=\"Blank\"><p:spTree><p:nvGrpSpPr><p:cNvPr id=\"1\" name=\"\"/><p:cNvGrpSpPr/><p:nvPr/></p:nvGrpSpPr><p:grpSpPr><a:xfrm><a:off x=\"0\" y=\"0\"/><a:ext cx=\"0\" cy=\"0\"/><a:chOff x=\"0\" y=\"0\"/><a:chExt cx=\"0\" cy=\"0\"/></a:xfrm></p:grpSpPr></p:spTree></p:cSld><p:clrMapOvr><a:masterClrMapping/></p:clrMapOvr></p:sldLayout>";
    let layout_rels = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\"><Relationship Id=\"rId1\" Type=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships/slideMaster\" Target=\"../slideMasters/slideMaster1.xml\"/></Relationships>";
    let theme = "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><a:theme xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" name=\"AI4HEOR Paper\"><a:themeElements><a:clrScheme name=\"AI4HEOR\"><a:dk1><a:srgbClr val=\"2A2723\"/></a:dk1><a:lt1><a:srgbClr val=\"F7F5EF\"/></a:lt1><a:dk2><a:srgbClr val=\"746F67\"/></a:dk2><a:lt2><a:srgbClr val=\"FFFFFF\"/></a:lt2><a:accent1><a:srgbClr val=\"AD5335\"/></a:accent1><a:accent2><a:srgbClr val=\"2A78D6\"/></a:accent2><a:accent3><a:srgbClr val=\"1BAF7A\"/></a:accent3><a:accent4><a:srgbClr val=\"EDA100\"/></a:accent4><a:accent5><a:srgbClr val=\"4A3AA7\"/></a:accent5><a:accent6><a:srgbClr val=\"E34948\"/></a:accent6><a:hlink><a:srgbClr val=\"2A6FDB\"/></a:hlink><a:folHlink><a:srgbClr val=\"4A3AA7\"/></a:folHlink></a:clrScheme><a:fontScheme name=\"AI4HEOR\"><a:majorFont><a:latin typeface=\"Aptos Display\"/><a:ea typeface=\"Aptos\"/><a:cs typeface=\"Aptos\"/></a:majorFont><a:minorFont><a:latin typeface=\"Aptos\"/><a:ea typeface=\"Aptos\"/><a:cs typeface=\"Aptos\"/></a:minorFont></a:fontScheme><a:fmtScheme name=\"AI4HEOR\"><a:fillStyleLst><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill><a:gradFill rotWithShape=\"1\"><a:gsLst><a:gs pos=\"0\"><a:schemeClr val=\"phClr\"><a:tint val=\"50000\"/><a:satMod val=\"300000\"/></a:schemeClr></a:gs><a:gs pos=\"100000\"><a:schemeClr val=\"phClr\"><a:shade val=\"50000\"/><a:satMod val=\"200000\"/></a:schemeClr></a:gs></a:gsLst><a:lin ang=\"16200000\" scaled=\"1\"/></a:gradFill><a:noFill/></a:fillStyleLst><a:lnStyleLst><a:ln w=\"6350\"><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill><a:prstDash val=\"solid\"/></a:ln><a:ln w=\"12700\"><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill><a:prstDash val=\"solid\"/></a:ln><a:ln w=\"19050\"><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill><a:prstDash val=\"solid\"/></a:ln></a:lnStyleLst><a:effectStyleLst><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle><a:effectStyle><a:effectLst/></a:effectStyle></a:effectStyleLst><a:bgFillStyleLst><a:solidFill><a:schemeClr val=\"phClr\"/></a:solidFill><a:solidFill><a:schemeClr val=\"phClr\"><a:tint val=\"95000\"/></a:schemeClr></a:solidFill><a:solidFill><a:schemeClr val=\"phClr\"><a:shade val=\"80000\"/></a:schemeClr></a:solidFill></a:bgFillStyleLst></a:fmtScheme></a:themeElements></a:theme>";
    vec![
        ("[Content_Types].xml".into(), content_types.into_bytes()),
        ("_rels/.rels".into(), root_rels.as_bytes().to_vec()),
        ("docProps/core.xml".into(), core.into_bytes()),
        ("docProps/app.xml".into(), app.into_bytes()),
        ("ppt/presentation.xml".into(), presentation.into_bytes()),
        ("ppt/_rels/presentation.xml.rels".into(), presentation_rels.into_bytes()),
        ("ppt/slideMasters/slideMaster1.xml".into(), master.as_bytes().to_vec()),
        ("ppt/slideMasters/_rels/slideMaster1.xml.rels".into(), master_rels.as_bytes().to_vec()),
        ("ppt/slideLayouts/slideLayout1.xml".into(), layout.as_bytes().to_vec()),
        ("ppt/slideLayouts/_rels/slideLayout1.xml.rels".into(), layout_rels.as_bytes().to_vec()),
        ("ppt/theme/theme1.xml".into(), theme.as_bytes().to_vec()),
        ("ppt/presProps.xml".into(), b"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><p:presentationPr xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"/>".to_vec()),
        ("ppt/viewProps.xml".into(), b"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><p:viewPr xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" xmlns:p=\"http://schemas.openxmlformats.org/presentationml/2006/main\"><p:normalViewPr/><p:slideViewPr/><p:notesTextViewPr/></p:viewPr>".to_vec()),
        ("ppt/tableStyles.xml".into(), b"<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?><a:tblStyleLst xmlns:a=\"http://schemas.openxmlformats.org/drawingml/2006/main\" def=\"{5C22544A-7EE6-4342-B048-85BDC9FD1C3A}\"/>".to_vec()),
    ]
}

fn build_pptx(loaded: &LoadedPresentation) -> Result<Vec<u8>, String> {
    let source_slide_count = loaded.manifest.sources.len().div_ceil(6);
    let slide_count = loaded.manifest.slides.len() + source_slide_count;
    let mut entries = fixed_package_parts(&loaded.manifest, slide_count);
    let mut media_index = 0usize;
    for (index, slide) in loaded.manifest.slides.iter().enumerate() {
        let slide_number = index + 1;
        let (mut shapes, image_key) = standard_slide_shapes(slide, slide_number);
        let mut image_relationship = None;
        if let Some(image_key) = image_key {
            let image = loaded
                .images
                .get(&image_key)
                .ok_or_else(|| format!("validated image is unavailable for {image_key}"))?;
            media_index += 1;
            let max_width = 11.4f64;
            let max_height = if slide.caption.is_empty() { 4.85 } else { 4.45 };
            let aspect = image.width as f64 / image.height as f64;
            let (width, height) = if max_width / max_height > aspect {
                (max_height * aspect, max_height)
            } else {
                (max_width, max_width / aspect)
            };
            let x = 0.84 + (max_width - width) / 2.0;
            let y = 1.55 + (max_height - height) / 2.0;
            shapes.push_str(&picture_shape(
                7,
                "Research figure",
                &slide.alt_text,
                "rId2",
                x,
                y,
                width,
                height,
            ));
            if !slide.caption.is_empty() {
                shapes.push_str(&text_box(
                    8,
                    "Figure caption",
                    0.84,
                    6.15,
                    11.4,
                    0.46,
                    &[Paragraph {
                        text: &slide.caption,
                        size: 900,
                        bold: false,
                        color: "746F67",
                        bullet: false,
                        align: "ctr",
                    }],
                    None,
                    None,
                    0.0,
                    "ctr",
                ));
            }
            entries.push((
                format!("ppt/media/image{media_index}.{}", image.extension),
                image.bytes.clone(),
            ));
            image_relationship = Some((media_index, image.extension));
        }
        entries.push((
            format!("ppt/slides/slide{slide_number}.xml"),
            slide_xml(&shapes),
        ));
        entries.push((
            format!("ppt/slides/_rels/slide{slide_number}.xml.rels"),
            slide_rels(image_relationship),
        ));
    }
    let source_title = sources_title(&loaded.manifest.language);
    for (chunk_index, chunk) in loaded.manifest.sources.chunks(6).enumerate() {
        let slide_number = loaded.manifest.slides.len() + chunk_index + 1;
        let title = if source_slide_count == 1 {
            source_title.to_string()
        } else {
            format!("{source_title} {}/{}", chunk_index + 1, source_slide_count)
        };
        let shapes = source_slide_shapes(chunk, &title, slide_number);
        entries.push((
            format!("ppt/slides/slide{slide_number}.xml"),
            slide_xml(&shapes),
        ));
        entries.push((
            format!("ppt/slides/_rels/slide{slide_number}.xml.rels"),
            slide_rels(None),
        ));
    }
    let output = build_stored_zip(&entries)?;
    if output.len() > OUTPUT_CAP_BYTES {
        return Err("generated presentation exceeds the 50 MiB output cap".into());
    }
    Ok(output)
}

fn crc32(data: &[u8]) -> u32 {
    let mut crc = 0xffff_ffffu32;
    for byte in data {
        crc ^= *byte as u32;
        for _ in 0..8 {
            crc = if crc & 1 == 1 {
                (crc >> 1) ^ 0xedb8_8320
            } else {
                crc >> 1
            };
        }
    }
    !crc
}

fn write_u16(output: &mut Vec<u8>, value: u16) {
    output.extend_from_slice(&value.to_le_bytes());
}

fn write_u32(output: &mut Vec<u8>, value: u32) {
    output.extend_from_slice(&value.to_le_bytes());
}

fn build_stored_zip(entries: &[(String, Vec<u8>)]) -> Result<Vec<u8>, String> {
    let mut output = Vec::new();
    let mut central = Vec::new();
    for (name, data) in entries {
        let name_bytes = name.as_bytes();
        let name_len = u16::try_from(name_bytes.len()).map_err(|_| "ZIP entry name is too long")?;
        let size = u32::try_from(data.len()).map_err(|_| "ZIP entry is too large")?;
        let offset = u32::try_from(output.len()).map_err(|_| "ZIP archive is too large")?;
        let crc = crc32(data);
        write_u32(&mut output, 0x0403_4b50);
        write_u16(&mut output, 20);
        write_u16(&mut output, 0x0800);
        write_u16(&mut output, 0);
        write_u16(&mut output, 0);
        write_u16(&mut output, 0x0021);
        write_u32(&mut output, crc);
        write_u32(&mut output, size);
        write_u32(&mut output, size);
        write_u16(&mut output, name_len);
        write_u16(&mut output, 0);
        output.extend_from_slice(name_bytes);
        output.extend_from_slice(data);

        write_u32(&mut central, 0x0201_4b50);
        write_u16(&mut central, 20);
        write_u16(&mut central, 20);
        write_u16(&mut central, 0x0800);
        write_u16(&mut central, 0);
        write_u16(&mut central, 0);
        write_u16(&mut central, 0x0021);
        write_u32(&mut central, crc);
        write_u32(&mut central, size);
        write_u32(&mut central, size);
        write_u16(&mut central, name_len);
        write_u16(&mut central, 0);
        write_u16(&mut central, 0);
        write_u16(&mut central, 0);
        write_u16(&mut central, 0);
        write_u32(&mut central, 0);
        write_u32(&mut central, offset);
        central.extend_from_slice(name_bytes);
    }
    let central_offset = u32::try_from(output.len()).map_err(|_| "ZIP archive is too large")?;
    let central_size = u32::try_from(central.len()).map_err(|_| "ZIP archive is too large")?;
    output.extend_from_slice(&central);
    write_u32(&mut output, 0x0605_4b50);
    write_u16(&mut output, 0);
    write_u16(&mut output, 0);
    let count = u16::try_from(entries.len()).map_err(|_| "ZIP archive has too many entries")?;
    write_u16(&mut output, count);
    write_u16(&mut output, count);
    write_u32(&mut output, central_size);
    write_u32(&mut output, central_offset);
    write_u16(&mut output, 0);
    Ok(output)
}

fn write_atomic(path: &Path, bytes: &[u8]) -> Result<(), String> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("cannot create output directory: {error}"))?;
    }
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or("output");
    let temp = path.with_file_name(format!(".{file_name}.tmp"));
    {
        let mut file = std::fs::File::create(&temp)
            .map_err(|error| format!("cannot create temporary output: {error}"))?;
        file.write_all(bytes)
            .map_err(|error| format!("cannot write temporary output: {error}"))?;
        file.sync_all()
            .map_err(|error| format!("cannot flush temporary output: {error}"))?;
    }
    if std::fs::rename(&temp, path).is_err() {
        let result =
            std::fs::write(path, bytes).map_err(|error| format!("cannot replace output: {error}"));
        let _ = std::fs::remove_file(temp);
        result?;
    }
    Ok(())
}

#[tauri::command(async)]
pub fn audit_research_presentation(app: AppHandle) -> Result<ResearchPresentationAudit, String> {
    Ok(audit_at(&crate::runtime::workspace_dir(&app)?).0)
}

fn generate_at(workspace: &Path) -> Result<ResearchPresentationAudit, String> {
    let (audit, loaded) = audit_at(&workspace);
    let loaded = loaded.ok_or_else(|| audit.errors.join("; "))?;
    let pptx = build_pptx(&loaded)?;
    let output_sha256 = sha256(&pptx);
    let record = GenerationRecord {
        schema_version: "0.1.0".into(),
        generator: "ai4heor-native-presentation".into(),
        generator_version: ENGINE_VERSION.into(),
        deck_id: loaded.manifest.deck_id.clone(),
        manifest_path: PRESENTATION_MANIFEST_PATH.into(),
        manifest_sha256: sha256(&loaded.manifest_raw),
        source_hashes: loaded.source_hashes.clone(),
        output_path: PRESENTATION_OUTPUT_PATH.into(),
        output_sha256,
        authored_slide_count: loaded.manifest.slides.len(),
        rendered_slide_count: audit.rendered_slide_count,
        human_review_status: "awaiting_human_review".into(),
    };
    let record_raw = serde_json::to_vec_pretty(&record)
        .map_err(|error| format!("cannot serialize presentation audit: {error}"))?;
    write_atomic(&workspace.join(PRESENTATION_OUTPUT_PATH), &pptx)?;
    write_atomic(&workspace.join(PRESENTATION_AUDIT_PATH), &record_raw)?;
    Ok(audit_at(&workspace).0)
}

#[tauri::command(async)]
pub fn generate_research_presentation(app: AppHandle) -> Result<ResearchPresentationAudit, String> {
    generate_at(&crate::runtime::workspace_dir(&app)?)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_workspace() -> PathBuf {
        let stamp = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        std::env::temp_dir().join(format!(
            "ai4heor-presentation-{}-{stamp}",
            std::process::id()
        ))
    }

    #[test]
    fn stored_zip_has_valid_headers_and_crc() {
        let zip = build_stored_zip(&[("a.txt".into(), b"hello".to_vec())]).unwrap();
        assert_eq!(&zip[..4], &0x0403_4b50u32.to_le_bytes());
        assert!(zip
            .windows(4)
            .any(|window| window == 0x0201_4b50u32.to_le_bytes()));
        assert!(zip.ends_with(&[0, 0]));
        assert_eq!(crc32(b"123456789"), 0xcbf4_3926);
    }

    #[test]
    fn image_dimensions_rejects_fake_images_and_reads_png() {
        let mut png = b"\x89PNG\r\n\x1a\n".to_vec();
        png.extend_from_slice(&[0; 8]);
        png.extend_from_slice(&640u32.to_be_bytes());
        png.extend_from_slice(&360u32.to_be_bytes());
        assert_eq!(image_dimensions(&png, "png"), Some((640, 360)));
        assert_eq!(image_dimensions(b"not an image", "jpeg"), None);
    }

    #[test]
    fn safe_paths_reject_generated_and_traversal_targets() {
        assert!(safe_relative("heor/report.md"));
        assert!(!safe_relative("../report.md"));
        assert!(!safe_relative("/tmp/report.md"));
        assert!(!safe_relative(PRESENTATION_OUTPUT_PATH));
    }

    #[test]
    fn slide_content_is_xml_escaped() {
        assert_eq!(xml_escape("A & B < C"), "A &amp; B &lt; C");
    }

    #[test]
    fn valid_manifest_generates_current_deterministic_pptx_and_detects_source_drift() {
        let workspace = test_workspace();
        std::fs::create_dir_all(workspace.join("heor")).unwrap();
        std::fs::create_dir_all(workspace.join("deliverables")).unwrap();
        let source = b"# Reviewed report\n\nICER: CNY 125,000/QALY.\n";
        std::fs::write(workspace.join("heor/report.md"), source).unwrap();
        let manifest = serde_json::json!({
            "schema_version": "0.1.0",
            "deck_id": "project-readout",
            "title": "Cost-effectiveness results",
            "subtitle": "Researcher review draft",
            "language": "zh-Hans",
            "prepared_on": "2026-07-19",
            "audience": "Project research group",
            "purpose": "Review the current findings and limitations",
            "theme": "ai4heor-paper",
            "sources": [{
                "source_id": "S1",
                "path": "heor/report.md",
                "sha256": sha256(source),
                "label": "Reviewed report"
            }],
            "slides": [
                {"slide_id": "title", "kind": "title", "title": "Cost-effectiveness results", "subtitle": "Researcher review draft"},
                {"slide_id": "result", "kind": "content", "title": "Current result", "bullets": ["The reported ICER is CNY 125,000/QALY."], "source_refs": ["S1"]},
                {"slide_id": "limits", "kind": "limitations", "title": "Limitations", "bullets": ["Interpretation remains conditional on the reviewed input assumptions."], "source_refs": ["S1"]},
                {"slide_id": "close", "kind": "closing", "title": "Researcher review", "bullets": ["Check every number and interpretation before external use."]}
            ],
            "human_review": {"status": "awaiting_human_review"}
        });
        std::fs::write(
            workspace.join(PRESENTATION_MANIFEST_PATH),
            serde_json::to_vec_pretty(&manifest).unwrap(),
        )
        .unwrap();

        let before = audit_at(&workspace).0;
        assert!(before.ready_to_generate);
        assert!(!before.output_current);
        let generated = generate_at(&workspace).unwrap();
        assert!(generated.output_current);
        assert_eq!(generated.status, "generated_current");
        assert_eq!(generated.authored_slide_count, 4);
        assert_eq!(generated.rendered_slide_count, 5);
        let first = std::fs::read(workspace.join(PRESENTATION_OUTPUT_PATH)).unwrap();
        assert!(first.starts_with(b"PK\x03\x04"));
        assert!(first
            .windows(b"[Content_Types].xml".len())
            .any(|part| part == b"[Content_Types].xml"));
        assert!(first
            .windows(b"ppt/slides/slide5.xml".len())
            .any(|part| part == b"ppt/slides/slide5.xml"));

        generate_at(&workspace).unwrap();
        let second = std::fs::read(workspace.join(PRESENTATION_OUTPUT_PATH)).unwrap();
        assert_eq!(first, second);

        std::fs::write(workspace.join("heor/report.md"), b"changed source").unwrap();
        let drifted = audit_at(&workspace).0;
        assert!(!drifted.complete);
        assert!(!drifted.output_current);
        assert!(drifted.errors.iter().any(|error| error.contains("SHA-256")));
        if std::env::var_os("AI4HEOR_KEEP_TEST_PRESENTATION").is_some() {
            eprintln!("kept presentation fixture at {}", workspace.display());
        } else {
            let _ = std::fs::remove_dir_all(workspace);
        }
    }
}
