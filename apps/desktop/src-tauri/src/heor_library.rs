//! Local-first HEOR evidence library.
//!
//! Source documents stay in `heor/library/`. The native app hashes every byte,
//! extracts searchable text without a model or network call, and stores the
//! derived index in the app-owned `.openscience` area. The reviewable manifest
//! binds the index to exact source bytes. Unsupported, encrypted, scanned, or
//! malformed documents remain visible as issues instead of being silently
//! treated as indexed evidence.

use rusqlite::{params, Connection};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use tauri::{path::BaseDirectory, AppHandle, Manager};

pub const LIBRARY_DIR: &str = "heor/library";
pub const LIBRARY_MANIFEST_PATH: &str = "heor/evidence-library.json";
const INDEX_PATH: &str = ".openscience/heor-library.sqlite";
const SCHEMA_VERSION: &str = "0.1.0";
const EXTRACTOR: &str = "ai4heor-native/pdf-extract-0.12.0";
const MAX_FILES: usize = 500;
const MAX_FILE_BYTES: u64 = 25 * 1024 * 1024;
const MAX_TOTAL_BYTES: u64 = 500 * 1024 * 1024;
const MAX_EXTRACTED_BYTES: usize = 12 * 1024 * 1024;
const MAX_TOTAL_EXTRACTED_BYTES: usize = 250 * 1024 * 1024;
const MAX_QUERY_CHARS: usize = 500;
const BUNDLED_LIBRARY_RESOURCE: &str = "knowledge-base/zh-Hans";
const BUNDLED_LIBRARY_SCHEMA: &str = "ai4heor-bundled-knowledge-base/v1";
const BUNDLED_LIBRARY_ID: &str = "ai4heor-pharmacoeconomics-foundations-zh-Hans-2026-07";
const BUNDLED_LIBRARY_DESTINATION: &str = "ai4heor-pharmacoeconomics-foundations-zh-Hans-2026-07";
const BUNDLED_LIBRARY_MANIFEST_COPY: &str = "_AI4HEOR-BUNDLE.json";
const MAX_BUNDLED_SOURCE_BYTES: u64 = 1024 * 1024;

#[derive(Default)]
pub struct HeorLibraryState(pub Mutex<()>);

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct LibraryManifest {
    schema_version: String,
    project_id: String,
    library_path: String,
    index_path: String,
    index_sha256: String,
    extractor: String,
    documents: Vec<LibraryDocument>,
}

#[derive(Clone, Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
pub struct LibraryDocument {
    pub path: String,
    pub sha256: String,
    pub bytes: u64,
    pub media_type: String,
    pub extraction_status: String,
    pub page_count: usize,
    pub text_sha256: Option<String>,
    pub issue: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LibraryAudit {
    pub complete: bool,
    pub searchable: bool,
    pub stale: bool,
    pub status: &'static str,
    pub manifest_sha256: String,
    pub document_count: usize,
    pub indexed_count: usize,
    pub requires_ocr_count: usize,
    pub failed_count: usize,
    pub total_bytes: u64,
    pub errors: Vec<String>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LibrarySearchHit {
    pub path: String,
    pub source_sha256: String,
    pub page: usize,
    pub score: u64,
    pub snippet: String,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LibrarySearchResponse {
    pub audit: LibraryAudit,
    pub query: String,
    pub hits: Vec<LibrarySearchHit>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct LibraryDirectoryImport {
    pub added: Vec<String>,
    pub skipped: Vec<String>,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct BundledLibraryFile {
    path: String,
    sha256: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct BundledLibraryBoundaries {
    stable_content: Vec<String>,
    dated_content: Vec<String>,
    scientific_authority: String,
    policy_status: String,
}

#[derive(Clone, Debug, Deserialize)]
#[serde(rename_all = "camelCase", deny_unknown_fields)]
struct BundledLibraryManifest {
    schema_version: String,
    bundle_id: String,
    title: String,
    locale: String,
    updated: String,
    status: String,
    boundaries: BundledLibraryBoundaries,
    files: Vec<BundledLibraryFile>,
}

#[derive(Clone, Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BundledLibraryInstall {
    schema: &'static str,
    bundle_id: String,
    title: String,
    locale: String,
    updated: String,
    manifest_sha256: String,
    added: Vec<String>,
    already_installed: bool,
    audit: LibraryAudit,
}

#[derive(Debug)]
struct SourceFile {
    path: String,
    full_path: PathBuf,
    bytes: u64,
    sha256: String,
    media_type: Option<&'static str>,
}

fn sha256(raw: &[u8]) -> String {
    format!("{:x}", Sha256::digest(raw))
}

fn sha256_file(path: &Path) -> Result<String, String> {
    let mut file = std::fs::File::open(path)
        .map_err(|error| format!("could not hash local evidence index: {error}"))?;
    let mut hasher = Sha256::new();
    let mut buffer = [0u8; 64 * 1024];
    loop {
        let read = file
            .read(&mut buffer)
            .map_err(|error| format!("could not hash local evidence index: {error}"))?;
        if read == 0 {
            break;
        }
        hasher.update(&buffer[..read]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

fn media_type(path: &Path) -> Option<&'static str> {
    match path.extension()?.to_str()?.to_ascii_lowercase().as_str() {
        "pdf" => Some("application/pdf"),
        "txt" => Some("text/plain"),
        "md" => Some("text/markdown"),
        "csv" => Some("text/csv"),
        "json" => Some("application/json"),
        _ => None,
    }
}

fn relative_slash(path: &Path, root: &Path) -> Result<String, String> {
    let relative = path
        .strip_prefix(root)
        .map_err(|_| "library file escaped the current workspace")?;
    Ok(relative
        .components()
        .map(|part| part.as_os_str().to_string_lossy())
        .collect::<Vec<_>>()
        .join("/"))
}

fn ensure_library(workspace: &Path) -> Result<PathBuf, String> {
    let root = workspace
        .canonicalize()
        .map_err(|error| format!("workspace unavailable: {error}"))?;
    let heor = root.join("heor");
    if heor.exists()
        && std::fs::symlink_metadata(&heor)
            .map_err(|e| e.to_string())?
            .file_type()
            .is_symlink()
    {
        return Err("heor must not be a symbolic link".into());
    }
    std::fs::create_dir_all(heor.join("library"))
        .map_err(|error| format!("could not create HEOR library: {error}"))?;
    let library = heor
        .join("library")
        .canonicalize()
        .map_err(|error| format!("HEOR library unavailable: {error}"))?;
    if !library.starts_with(&root) {
        return Err("HEOR library must stay inside the current workspace".into());
    }
    Ok(library)
}

fn discover(workspace: &Path) -> Result<(Vec<SourceFile>, Vec<String>), String> {
    let root = workspace
        .canonicalize()
        .map_err(|error| format!("workspace unavailable: {error}"))?;
    let library = ensure_library(&root)?;
    let mut stack = vec![library];
    let mut files = Vec::new();
    let mut issues = Vec::new();
    let mut total = 0u64;
    while let Some(directory) = stack.pop() {
        let mut entries = std::fs::read_dir(&directory)
            .map_err(|error| format!("could not read HEOR library: {error}"))?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| format!("could not read HEOR library entry: {error}"))?;
        entries.sort_by_key(|entry| entry.file_name());
        for entry in entries {
            let file_type = entry
                .file_type()
                .map_err(|error| format!("could not inspect library entry: {error}"))?;
            let path = entry.path();
            let relative = relative_slash(&path, &root)?;
            if file_type.is_symlink() {
                issues.push(format!("{relative}: symbolic links are not indexed"));
                continue;
            }
            if file_type.is_dir() {
                stack.push(path);
                continue;
            }
            if !file_type.is_file() {
                issues.push(format!("{relative}: entry is not a regular file"));
                continue;
            }
            if files.len() >= MAX_FILES {
                return Err(format!(
                    "HEOR library exceeds the {MAX_FILES}-file safety cap"
                ));
            }
            let metadata = entry
                .metadata()
                .map_err(|error| format!("could not inspect {relative}: {error}"))?;
            if metadata.len() > MAX_FILE_BYTES {
                issues.push(format!("{relative}: file exceeds the 25 MiB safety cap"));
                continue;
            }
            total = total.saturating_add(metadata.len());
            if total > MAX_TOTAL_BYTES {
                return Err("HEOR library exceeds the 500 MiB safety cap".into());
            }
            let raw = std::fs::read(&path)
                .map_err(|error| format!("could not read {relative}: {error}"))?;
            files.push(SourceFile {
                path: relative,
                full_path: path,
                bytes: metadata.len(),
                sha256: sha256(&raw),
                media_type: media_type(entry.path().as_path()),
            });
        }
    }
    files.sort_by(|left, right| left.path.cmp(&right.path));
    Ok((files, issues))
}

fn validate_import_sources(workspace: &Path, selected: &[PathBuf]) -> Result<Vec<u64>, String> {
    let (existing, issues) = discover(workspace)?;
    if !issues.is_empty() {
        return Err(format!(
            "resolve unsafe HEOR library entries before importing: {}",
            issues.join("; ")
        ));
    }
    if existing.len().saturating_add(selected.len()) > MAX_FILES {
        return Err(format!(
            "HEOR library import would exceed the {MAX_FILES}-file safety cap"
        ));
    }
    let mut total = existing.iter().map(|source| source.bytes).sum::<u64>();
    let mut sizes = Vec::with_capacity(selected.len());
    for source in selected {
        let metadata = std::fs::symlink_metadata(source)
            .map_err(|error| format!("could not inspect selected file: {error}"))?;
        if metadata.file_type().is_symlink() {
            return Err("selected evidence must not be a symbolic link".into());
        }
        if !metadata.is_file() || metadata.len() > MAX_FILE_BYTES || media_type(source).is_none() {
            return Err(
                "selected evidence must be a supported regular file no larger than 25 MiB".into(),
            );
        }
        total = total
            .checked_add(metadata.len())
            .ok_or("HEOR library import size overflow")?;
        if total > MAX_TOTAL_BYTES {
            return Err("HEOR library import would exceed the 500 MiB safety cap".into());
        }
        sizes.push(metadata.len());
    }
    Ok(sizes)
}

fn copy_checked(source: &Path, destination: &Path, expected_bytes: u64) -> Result<(), String> {
    let mut input = std::fs::File::open(source)
        .map_err(|error| format!("could not open selected evidence: {error}"))?;
    let mut output = std::fs::OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(destination)
        .map_err(|error| format!("could not create evidence destination: {error}"))?;
    let copied = std::io::copy(&mut input, &mut output)
        .map_err(|error| format!("could not copy evidence: {error}"))?;
    if copied != expected_bytes || copied > MAX_FILE_BYTES {
        return Err("selected evidence changed during import".into());
    }
    output
        .sync_all()
        .map_err(|error| format!("could not sync imported evidence: {error}"))?;
    Ok(())
}

fn safe_bundle_relative(value: &str) -> Result<PathBuf, String> {
    let path = PathBuf::from(value);
    if value.is_empty()
        || path.is_absolute()
        || path
            .components()
            .any(|component| !matches!(component, std::path::Component::Normal(_)))
    {
        return Err(format!("bundled knowledge-base path is unsafe: {value}"));
    }
    Ok(path)
}

fn read_bundled_manifest(resource: &Path) -> Result<(BundledLibraryManifest, Vec<u8>), String> {
    let manifest_path = resource.join("manifest.json");
    let metadata = std::fs::symlink_metadata(&manifest_path)
        .map_err(|error| format!("bundled knowledge-base manifest is unavailable: {error}"))?;
    if metadata.file_type().is_symlink()
        || !metadata.is_file()
        || metadata.len() > MAX_BUNDLED_SOURCE_BYTES
    {
        return Err("bundled knowledge-base manifest must be a bounded regular file".into());
    }
    let raw = std::fs::read(&manifest_path)
        .map_err(|error| format!("bundled knowledge-base manifest could not be read: {error}"))?;
    let manifest: BundledLibraryManifest = serde_json::from_slice(&raw)
        .map_err(|error| format!("bundled knowledge-base manifest is invalid: {error}"))?;
    if manifest.schema_version != BUNDLED_LIBRARY_SCHEMA
        || manifest.bundle_id != BUNDLED_LIBRARY_ID
        || manifest.locale != "zh-Hans"
        || manifest.updated != "2026-07-14"
        || manifest.status != "dated_learning_material"
        || manifest.boundaries.scientific_authority != "human_researcher"
        || manifest.boundaries.policy_status != "verify_current_sources_before_use"
        || manifest.boundaries.stable_content.is_empty()
        || manifest.boundaries.dated_content.is_empty()
        || manifest.files.is_empty()
    {
        return Err(
            "bundled knowledge-base manifest contract does not match the supported release".into(),
        );
    }
    Ok((manifest, raw))
}

fn discover_bundle_tree(root: &Path) -> Result<Vec<String>, String> {
    let root = root
        .canonicalize()
        .map_err(|error| format!("bundled knowledge base is unavailable: {error}"))?;
    let mut directories = vec![root.clone()];
    let mut files = Vec::new();
    while let Some(directory) = directories.pop() {
        let mut entries = std::fs::read_dir(&directory)
            .map_err(|error| format!("could not read bundled knowledge base: {error}"))?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| format!("could not read bundled knowledge-base entry: {error}"))?;
        entries.sort_by_key(|entry| entry.file_name());
        for entry in entries {
            let path = entry.path();
            let relative = relative_slash(&path, &root)?;
            let file_type = entry
                .file_type()
                .map_err(|error| format!("could not inspect bundled source {relative}: {error}"))?;
            if file_type.is_symlink() {
                return Err(format!(
                    "bundled knowledge base contains a symbolic link: {relative}"
                ));
            }
            if file_type.is_dir() {
                directories.push(path);
            } else if file_type.is_file() {
                files.push(relative);
            } else {
                return Err(format!(
                    "bundled knowledge base contains a non-regular entry: {relative}"
                ));
            }
        }
    }
    files.sort();
    Ok(files)
}

fn validate_bundled_library(resource: &Path) -> Result<(BundledLibraryManifest, Vec<u8>), String> {
    let resource_metadata = std::fs::symlink_metadata(resource)
        .map_err(|error| format!("bundled knowledge base is unavailable: {error}"))?;
    if resource_metadata.file_type().is_symlink() || !resource_metadata.is_dir() {
        return Err("bundled knowledge base must be a regular resource directory".into());
    }
    let (manifest, manifest_raw) = read_bundled_manifest(resource)?;
    let mut expected = vec!["manifest.json".to_string()];
    let mut previous = None::<String>;
    for file in &manifest.files {
        let relative = safe_bundle_relative(&file.path)?;
        if previous
            .as_deref()
            .is_some_and(|value| value >= file.path.as_str())
        {
            return Err("bundled knowledge-base manifest files must be unique and sorted".into());
        }
        previous = Some(file.path.clone());
        let source = resource.join(&relative);
        let metadata = std::fs::symlink_metadata(&source)
            .map_err(|error| format!("bundled source {} is unavailable: {error}", file.path))?;
        if metadata.file_type().is_symlink()
            || !metadata.is_file()
            || metadata.len() > MAX_BUNDLED_SOURCE_BYTES
        {
            return Err(format!(
                "bundled source {} must be a bounded regular file",
                file.path
            ));
        }
        let raw = std::fs::read(&source)
            .map_err(|error| format!("bundled source {} could not be read: {error}", file.path))?;
        if sha256(&raw) != file.sha256 {
            return Err(format!(
                "bundled source {} failed SHA-256 verification",
                file.path
            ));
        }
        expected.push(file.path.clone());
    }
    expected.sort();
    if discover_bundle_tree(resource)? != expected {
        return Err("bundled knowledge-base resource tree differs from its manifest".into());
    }
    Ok((manifest, manifest_raw))
}

fn verify_installed_bundle(
    destination: &Path,
    manifest: &BundledLibraryManifest,
    manifest_raw: &[u8],
) -> Result<(), String> {
    let metadata = std::fs::symlink_metadata(destination)
        .map_err(|error| format!("bundled knowledge-base destination is unavailable: {error}"))?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err("bundled knowledge-base destination must be a regular directory".into());
    }
    let mut expected = manifest
        .files
        .iter()
        .map(|file| file.path.clone())
        .collect::<Vec<_>>();
    expected.push(BUNDLED_LIBRARY_MANIFEST_COPY.into());
    expected.sort();
    if discover_bundle_tree(destination)? != expected {
        return Err("bundled knowledge-base destination contains missing or extra files".into());
    }
    for file in &manifest.files {
        let installed = destination.join(safe_bundle_relative(&file.path)?);
        let metadata = std::fs::symlink_metadata(&installed)
            .map_err(|error| format!("installed source {} is unavailable: {error}", file.path))?;
        if metadata.file_type().is_symlink()
            || !metadata.is_file()
            || metadata.len() > MAX_BUNDLED_SOURCE_BYTES
        {
            return Err(format!(
                "installed source {} must remain a bounded regular file",
                file.path
            ));
        }
        let raw = std::fs::read(&installed).map_err(|error| {
            format!("installed source {} could not be read: {error}", file.path)
        })?;
        if sha256(&raw) != file.sha256 {
            return Err(format!(
                "installed source {} differs from the bundled version",
                file.path
            ));
        }
    }
    let installed_manifest_path = destination.join(BUNDLED_LIBRARY_MANIFEST_COPY);
    let installed_manifest_metadata = std::fs::symlink_metadata(&installed_manifest_path)
        .map_err(|error| format!("installed bundle manifest is unavailable: {error}"))?;
    if installed_manifest_metadata.file_type().is_symlink()
        || !installed_manifest_metadata.is_file()
        || installed_manifest_metadata.len() > MAX_BUNDLED_SOURCE_BYTES
    {
        return Err("installed bundle manifest must remain a bounded regular file".into());
    }
    let installed_manifest = std::fs::read(installed_manifest_path)
        .map_err(|error| format!("installed bundle manifest could not be read: {error}"))?;
    if installed_manifest != manifest_raw {
        return Err("installed bundle manifest differs from the bundled version".into());
    }
    Ok(())
}

fn install_bundled_library_from(
    workspace: &Path,
    resource: &Path,
    project_id: &str,
) -> Result<BundledLibraryInstall, String> {
    if crate::project::require_project_id(workspace)? != project_id {
        return Err("bundled knowledge-base projectId does not match the current project".into());
    }
    let (manifest, manifest_raw) = validate_bundled_library(resource)?;
    let manifest_sha256 = sha256(&manifest_raw);
    let library = ensure_library(workspace)?;
    let destination = library.join(BUNDLED_LIBRARY_DESTINATION);
    let already_installed = std::fs::symlink_metadata(&destination).is_ok();
    let mut added = Vec::new();
    if already_installed {
        verify_installed_bundle(&destination, &manifest, &manifest_raw).map_err(|error| {
            format!("{error}; existing files were preserved and were not replaced")
        })?;
    } else {
        std::fs::create_dir(&destination).map_err(|error| {
            format!("could not create bundled knowledge-base destination: {error}")
        })?;
        let copy_result = (|| -> Result<(), String> {
            for file in &manifest.files {
                let relative = safe_bundle_relative(&file.path)?;
                let source = resource.join(&relative);
                let target = destination.join(&relative);
                std::fs::create_dir_all(
                    target
                        .parent()
                        .ok_or("invalid bundled knowledge-base destination")?,
                )
                .map_err(|error| format!("could not create knowledge-base hierarchy: {error}"))?;
                let bytes = std::fs::symlink_metadata(&source)
                    .map_err(|error| format!("could not inspect bundled source: {error}"))?
                    .len();
                copy_checked(&source, &target, bytes)?;
            }
            let manifest_target = destination.join(BUNDLED_LIBRARY_MANIFEST_COPY);
            let mut output = std::fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&manifest_target)
                .map_err(|error| format!("could not create installed bundle manifest: {error}"))?;
            output
                .write_all(&manifest_raw)
                .map_err(|error| format!("could not write installed bundle manifest: {error}"))?;
            output
                .sync_all()
                .map_err(|error| format!("could not sync installed bundle manifest: {error}"))?;
            verify_installed_bundle(&destination, &manifest, &manifest_raw)
        })();
        if let Err(error) = copy_result {
            let _ = std::fs::remove_dir_all(&destination);
            return Err(error);
        }
        let canonical_workspace = workspace
            .canonicalize()
            .map_err(|error| format!("workspace unavailable: {error}"))?;
        added = discover_bundle_tree(&destination)?
            .into_iter()
            .map(|relative| relative_slash(&destination.join(relative), &canonical_workspace))
            .collect::<Result<Vec<_>, _>>()?;
    }
    let current_audit = already_installed.then(|| audit_library(workspace));
    let audit = match current_audit {
        Some(audit) if audit.complete && audit.searchable && !audit.stale => audit,
        _ => {
            build_index(workspace, project_id)?;
            audit_library(workspace)
        }
    };
    Ok(BundledLibraryInstall {
        schema: BUNDLED_LIBRARY_SCHEMA,
        bundle_id: manifest.bundle_id,
        title: manifest.title,
        locale: manifest.locale,
        updated: manifest.updated,
        manifest_sha256,
        added,
        already_installed,
        audit,
    })
}

fn import_library_directory(
    workspace: &Path,
    selected_directory: &Path,
) -> Result<LibraryDirectoryImport, String> {
    let workspace = workspace
        .canonicalize()
        .map_err(|error| format!("workspace unavailable: {error}"))?;
    let selected_metadata = std::fs::symlink_metadata(selected_directory)
        .map_err(|error| format!("could not inspect selected directory: {error}"))?;
    if selected_metadata.file_type().is_symlink() || !selected_metadata.is_dir() {
        return Err(
            "selected knowledge base must be a regular directory, not a symbolic link".into(),
        );
    }
    let selected = selected_directory
        .canonicalize()
        .map_err(|error| format!("selected knowledge base unavailable: {error}"))?;
    if selected.starts_with(&workspace) || workspace.starts_with(&selected) {
        return Err(
            "selected knowledge base must not contain, or be contained by, the current workspace"
                .into(),
        );
    }

    let mut directories = vec![selected.clone()];
    let mut sources = Vec::<(PathBuf, PathBuf)>::new();
    let mut skipped = Vec::new();
    while let Some(directory) = directories.pop() {
        let mut entries = std::fs::read_dir(&directory)
            .map_err(|error| format!("could not read selected knowledge base: {error}"))?
            .collect::<Result<Vec<_>, _>>()
            .map_err(|error| format!("could not read selected knowledge-base entry: {error}"))?;
        entries.sort_by_key(|entry| entry.file_name());
        for entry in entries {
            let path = entry.path();
            let relative = path
                .strip_prefix(&selected)
                .map_err(|_| "selected knowledge-base entry escaped its directory")?
                .to_path_buf();
            let relative_label = relative
                .components()
                .map(|part| part.as_os_str().to_string_lossy())
                .collect::<Vec<_>>()
                .join("/");
            let file_type = entry.file_type().map_err(|error| {
                format!("could not inspect selected entry {relative_label}: {error}")
            })?;
            if file_type.is_symlink() {
                return Err(format!(
                    "selected knowledge base contains a symbolic link: {relative_label}"
                ));
            }
            let hidden = entry.file_name().to_string_lossy().starts_with('.');
            if hidden {
                skipped.push(if file_type.is_dir() {
                    format!("{relative_label}/")
                } else {
                    relative_label
                });
                continue;
            }
            if file_type.is_dir() {
                directories.push(path);
            } else if file_type.is_file() {
                if media_type(&path).is_some() {
                    sources.push((path, relative));
                } else {
                    skipped.push(relative_label);
                }
            } else {
                return Err(format!(
                    "selected knowledge base contains a non-regular entry: {relative_label}"
                ));
            }
        }
    }
    sources.sort_by(|left, right| left.1.cmp(&right.1));
    skipped.sort();
    if sources.is_empty() {
        return Err(
            "selected knowledge base contains no supported PDF, TXT, Markdown, CSV, or JSON files"
                .into(),
        );
    }

    let selected_files = sources
        .iter()
        .map(|(source, _)| source.clone())
        .collect::<Vec<_>>();
    let sizes = validate_import_sources(&workspace, &selected_files)?;
    let library = ensure_library(&workspace)?;
    let source_name = selected
        .file_name()
        .ok_or("selected knowledge base has no directory name")?
        .to_string_lossy()
        .to_string();
    let destination_root = (0..10_000)
        .map(|number| {
            if number == 0 {
                library.join(&source_name)
            } else {
                library.join(format!("{source_name}-{number}"))
            }
        })
        .find(|candidate| std::fs::symlink_metadata(candidate).is_err())
        .ok_or("could not allocate a unique knowledge-base directory name")?;
    std::fs::create_dir(&destination_root)
        .map_err(|error| format!("could not create knowledge-base destination: {error}"))?;

    let import_result = (|| -> Result<Vec<String>, String> {
        let mut added = Vec::with_capacity(sources.len());
        for ((source, relative), expected_bytes) in sources.iter().zip(sizes) {
            let destination = destination_root.join(relative);
            let parent = destination
                .parent()
                .ok_or("invalid knowledge-base destination")?;
            std::fs::create_dir_all(parent)
                .map_err(|error| format!("could not create knowledge-base hierarchy: {error}"))?;
            copy_checked(source, &destination, expected_bytes)?;
            added.push(relative_slash(&destination, &workspace)?);
        }
        Ok(added)
    })();
    match import_result {
        Ok(added) => Ok(LibraryDirectoryImport { added, skipped }),
        Err(error) => {
            let _ = std::fs::remove_dir_all(&destination_root);
            Err(error)
        }
    }
}

fn extract_pages(source: &SourceFile) -> Result<Vec<String>, String> {
    let raw = std::fs::read(&source.full_path)
        .map_err(|error| format!("source became unavailable: {error}"))?;
    let pages = match source.media_type {
        Some("application/pdf") => {
            std::panic::catch_unwind(|| pdf_extract::extract_text_from_mem_by_pages(&raw))
                .map_err(|_| "PDF text extraction aborted safely".to_string())?
                .map_err(|error| format!("PDF text extraction failed: {error}"))?
        }
        Some(_) => {
            vec![String::from_utf8(raw).map_err(|_| "text source is not valid UTF-8".to_string())?]
        }
        None => return Err("unsupported format; use PDF, TXT, Markdown, CSV, or JSON".into()),
    };
    let size = pages.iter().map(String::len).sum::<usize>();
    if size > MAX_EXTRACTED_BYTES {
        return Err("extracted text exceeds the 12 MiB per-document safety cap".into());
    }
    Ok(pages)
}

fn index_path(workspace: &Path) -> PathBuf {
    workspace.join(INDEX_PATH)
}

fn write_manifest(workspace: &Path, manifest: &LibraryManifest) -> Result<Vec<u8>, String> {
    let target = workspace.join(LIBRARY_MANIFEST_PATH);
    let parent = target.parent().ok_or("invalid library manifest path")?;
    std::fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    let mut raw = serde_json::to_vec_pretty(manifest).map_err(|error| error.to_string())?;
    raw.push(b'\n');
    let stage = target.with_extension("json.tmp");
    let mut file = std::fs::File::create(&stage)
        .map_err(|error| format!("could not stage library manifest: {error}"))?;
    file.write_all(&raw)
        .map_err(|error| format!("could not stage library manifest: {error}"))?;
    file.sync_all()
        .map_err(|error| format!("could not sync library manifest: {error}"))?;
    let backup = target.with_extension("json.bak");
    if target.exists() {
        let _ = std::fs::remove_file(&backup);
        std::fs::rename(&target, &backup)
            .map_err(|error| format!("could not rotate library manifest: {error}"))?;
    }
    if let Err(error) = std::fs::rename(&stage, &target) {
        let _ = std::fs::rename(&backup, &target);
        return Err(format!("could not publish library manifest: {error}"));
    }
    let _ = std::fs::remove_file(&backup);
    Ok(raw)
}

fn build_index(workspace: &Path, project_id: &str) -> Result<Vec<u8>, String> {
    let (sources, discovery_issues) = discover(workspace)?;
    let db_path = index_path(workspace);
    if let Some(parent) = db_path.parent() {
        std::fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let mut connection = Connection::open(&db_path)
        .map_err(|error| format!("could not open local evidence index: {error}"))?;
    let transaction = connection
        .transaction()
        .map_err(|error| format!("could not start local evidence index: {error}"))?;
    transaction
        .execute_batch(
            "DROP TABLE IF EXISTS pages;
         DROP TABLE IF EXISTS documents;
         CREATE TABLE documents (
           path TEXT PRIMARY KEY, source_sha256 TEXT NOT NULL, bytes INTEGER NOT NULL,
           media_type TEXT NOT NULL, extraction_status TEXT NOT NULL,
           page_count INTEGER NOT NULL, text_sha256 TEXT, issue TEXT
         );
         CREATE TABLE pages (
           document_path TEXT NOT NULL, page_number INTEGER NOT NULL,
           text TEXT NOT NULL, text_sha256 TEXT NOT NULL,
           PRIMARY KEY(document_path, page_number)
         );",
        )
        .map_err(|error| format!("could not initialize local evidence index: {error}"))?;

    let mut documents = Vec::with_capacity(sources.len() + discovery_issues.len());
    let mut total_extracted = 0usize;
    for source in sources {
        let media = source
            .media_type
            .unwrap_or("application/octet-stream")
            .to_string();
        let (status, pages, issue) = match extract_pages(&source) {
            Ok(pages)
                if pages.iter().all(|page| page.trim().is_empty())
                    && source.media_type == Some("application/pdf") =>
            {
                (
                    "requires_ocr".to_string(),
                    Vec::new(),
                    Some("no searchable text was extracted; OCR is required".to_string()),
                )
            }
            Ok(pages) if pages.iter().all(|page| page.trim().is_empty()) => (
                "failed".to_string(),
                Vec::new(),
                Some("text source contains no searchable content".to_string()),
            ),
            Ok(pages) => ("indexed".to_string(), pages, None),
            Err(error) if source.media_type.is_none() => {
                ("unsupported".to_string(), Vec::new(), Some(error))
            }
            Err(error) => ("failed".to_string(), Vec::new(), Some(error)),
        };
        total_extracted =
            total_extracted.saturating_add(pages.iter().map(String::len).sum::<usize>());
        if total_extracted > MAX_TOTAL_EXTRACTED_BYTES {
            return Err(
                "local evidence index exceeds the 250 MiB extracted-text safety cap".into(),
            );
        }
        let joined = pages.join("\u{c}");
        let text_hash = (!pages.is_empty()).then(|| sha256(joined.as_bytes()));
        for (index, text) in pages.iter().enumerate() {
            transaction.execute(
                "INSERT INTO pages(document_path,page_number,text,text_sha256) VALUES (?1,?2,?3,?4)",
                params![source.path, index + 1, text, sha256(text.as_bytes())],
            ).map_err(|error| format!("could not index {}: {error}", source.path))?;
        }
        transaction.execute(
            "INSERT INTO documents(path,source_sha256,bytes,media_type,extraction_status,page_count,text_sha256,issue)
             VALUES (?1,?2,?3,?4,?5,?6,?7,?8)",
            params![source.path, source.sha256, source.bytes, media, status, pages.len(), text_hash, issue],
        ).map_err(|error| format!("could not record {}: {error}", source.path))?;
        documents.push(LibraryDocument {
            path: source.path,
            sha256: source.sha256,
            bytes: source.bytes,
            media_type: media,
            extraction_status: status,
            page_count: pages.len(),
            text_sha256: text_hash,
            issue,
        });
    }
    for issue in discovery_issues {
        documents.push(LibraryDocument {
            path: issue
                .split(':')
                .next()
                .unwrap_or("library entry")
                .to_string(),
            sha256: String::new(),
            bytes: 0,
            media_type: "application/octet-stream".into(),
            extraction_status: "failed".into(),
            page_count: 0,
            text_sha256: None,
            issue: Some(issue),
        });
    }
    documents.sort_by(|left, right| left.path.cmp(&right.path));
    transaction
        .commit()
        .map_err(|error| format!("could not publish local evidence index: {error}"))?;
    drop(connection);
    let index_sha256 = sha256_file(&db_path)?;
    write_manifest(
        workspace,
        &LibraryManifest {
            schema_version: SCHEMA_VERSION.into(),
            project_id: project_id.into(),
            library_path: LIBRARY_DIR.into(),
            index_path: INDEX_PATH.into(),
            index_sha256,
            extractor: EXTRACTOR.into(),
            documents,
        },
    )
}

fn empty_audit(error: String) -> LibraryAudit {
    LibraryAudit {
        complete: false,
        searchable: false,
        stale: true,
        status: "incomplete",
        manifest_sha256: String::new(),
        document_count: 0,
        indexed_count: 0,
        requires_ocr_count: 0,
        failed_count: 0,
        total_bytes: 0,
        errors: vec![error],
    }
}

fn audit_library(workspace: &Path) -> LibraryAudit {
    let raw = match crate::heor_uncertainty::read_workspace_capped(workspace, LIBRARY_MANIFEST_PATH)
    {
        Ok(raw) => raw,
        Err(error) => return empty_audit(error),
    };
    let manifest: LibraryManifest = match serde_json::from_slice(&raw) {
        Ok(value) => value,
        Err(error) => return empty_audit(format!("library manifest is invalid: {error}")),
    };
    let mut errors = Vec::new();
    if manifest.schema_version != SCHEMA_VERSION
        || manifest.library_path != LIBRARY_DIR
        || manifest.index_path != INDEX_PATH
        || manifest.extractor != EXTRACTOR
    {
        errors.push("library manifest contract is unsupported".into());
    }
    match crate::project::require_project_id(workspace) {
        Ok(project_id) if project_id == manifest.project_id => {}
        Ok(_) => errors.push("library manifest belongs to another project".into()),
        Err(error) => errors.push(error),
    }
    let (sources, discovery_issues) = match discover(workspace) {
        Ok(value) => value,
        Err(error) => return empty_audit(error),
    };
    let unsafe_discovery = !discovery_issues.is_empty();
    errors.extend(discovery_issues);
    let current = sources
        .iter()
        .map(|source| (source.path.as_str(), (source.sha256.as_str(), source.bytes)))
        .collect::<HashMap<_, _>>();
    let recorded = manifest
        .documents
        .iter()
        .filter(|document| !document.sha256.is_empty())
        .map(|document| {
            (
                document.path.as_str(),
                (document.sha256.as_str(), document.bytes),
            )
        })
        .collect::<HashMap<_, _>>();
    if current != recorded {
        errors.push("library source bytes changed after the last sync".into());
    }
    let mut db_valid = index_path(workspace).is_file();
    if db_valid {
        match sha256_file(&index_path(workspace)) {
            Ok(hash) if hash == manifest.index_sha256 => {}
            Ok(_) => {
                errors.push("local evidence index SHA-256 does not match the manifest".into());
                db_valid = false;
            }
            Err(error) => {
                errors.push(error);
                db_valid = false;
            }
        }
    }
    if db_valid {
        match Connection::open(index_path(workspace)) {
            Ok(connection) => {
                let rows = connection
                    .prepare("SELECT path, source_sha256, bytes FROM documents")
                    .and_then(|mut statement| {
                        statement
                            .query_map([], |row| {
                                Ok((
                                    row.get::<_, String>(0)?,
                                    row.get::<_, String>(1)?,
                                    row.get::<_, u64>(2)?,
                                ))
                            })?
                            .collect::<Result<Vec<_>, _>>()
                    });
                let indexed_bindings = rows.ok().map(|rows| {
                    rows.into_iter()
                        .filter(|(_, hash, _)| !hash.is_empty())
                        .map(|(path, hash, bytes)| (path, (hash, bytes)))
                        .collect::<HashMap<_, _>>()
                });
                let manifest_bindings = manifest
                    .documents
                    .iter()
                    .filter(|document| !document.sha256.is_empty())
                    .map(|document| {
                        (
                            document.path.clone(),
                            (document.sha256.clone(), document.bytes),
                        )
                    })
                    .collect::<HashMap<_, _>>();
                if indexed_bindings.as_ref() != Some(&manifest_bindings) {
                    errors.push("local evidence index does not match the manifest".into());
                    db_valid = false;
                }
            }
            Err(error) => {
                errors.push(format!("local evidence index unavailable: {error}"));
                db_valid = false;
            }
        }
    } else {
        errors.push("local evidence index is missing".into());
    }
    for document in &manifest.documents {
        if let Some(issue) = &document.issue {
            errors.push(format!("{}: {issue}", document.path));
        }
    }
    let indexed_count = manifest
        .documents
        .iter()
        .filter(|d| d.extraction_status == "indexed")
        .count();
    let requires_ocr_count = manifest
        .documents
        .iter()
        .filter(|d| d.extraction_status == "requires_ocr")
        .count();
    let failed_count = manifest
        .documents
        .len()
        .saturating_sub(indexed_count + requires_ocr_count);
    let stale = unsafe_discovery
        || errors.iter().any(|error| {
            error.contains("changed after")
                || error.contains("does not match")
                || error.contains("missing")
                || error.contains("another project")
                || error.contains("contract")
        });
    let complete = !manifest.documents.is_empty() && errors.is_empty();
    LibraryAudit {
        complete,
        searchable: indexed_count > 0 && db_valid && !stale,
        stale,
        status: if complete { "complete" } else { "incomplete" },
        manifest_sha256: sha256(&raw),
        document_count: manifest.documents.len(),
        indexed_count,
        requires_ocr_count,
        failed_count,
        total_bytes: manifest
            .documents
            .iter()
            .map(|document| document.bytes)
            .sum(),
        errors,
    }
}

fn tokens(value: &str) -> Vec<String> {
    let normalized = value.to_lowercase();
    let mut output = Vec::new();
    let mut word = String::new();
    let mut cjk = Vec::new();
    let flush_word = |word: &mut String, output: &mut Vec<String>| {
        if !word.is_empty() {
            output.push(std::mem::take(word));
        }
    };
    let flush_cjk = |cjk: &mut Vec<char>, output: &mut Vec<String>| {
        match cjk.len() {
            0 => {}
            1 => output.push(cjk[0].to_string()),
            _ => output.extend(cjk.windows(2).map(|pair| pair.iter().collect())),
        }
        cjk.clear();
    };
    for character in normalized.chars() {
        let is_cjk =
            matches!(character as u32, 0x3400..=0x4dbf | 0x4e00..=0x9fff | 0xf900..=0xfaff);
        if is_cjk {
            flush_word(&mut word, &mut output);
            cjk.push(character);
        } else if character.is_alphanumeric() {
            flush_cjk(&mut cjk, &mut output);
            word.push(character);
        } else {
            flush_word(&mut word, &mut output);
            flush_cjk(&mut cjk, &mut output);
        }
    }
    flush_word(&mut word, &mut output);
    flush_cjk(&mut cjk, &mut output);
    output.sort();
    output.dedup();
    output
}

fn score(text: &str, query: &str, query_tokens: &[String]) -> u64 {
    let normalized = text.to_lowercase();
    let phrase = normalized.matches(&query.to_lowercase()).count() as u64;
    let token_score = query_tokens
        .iter()
        .map(|token| normalized.matches(token).count() as u64)
        .sum::<u64>();
    phrase.saturating_mul(1000).saturating_add(token_score)
}

fn snippet(text: &str, query_tokens: &[String]) -> String {
    let lowered = text.to_lowercase();
    let start_byte = query_tokens
        .iter()
        .filter_map(|token| lowered.find(token))
        .min()
        .unwrap_or(0);
    let start_char = lowered[..start_byte].chars().count().saturating_sub(80);
    let value = text.chars().skip(start_char).take(360).collect::<String>();
    value.split_whitespace().collect::<Vec<_>>().join(" ")
}

#[tauri::command]
pub fn sync_heor_evidence_library(
    app: AppHandle,
    state: tauri::State<HeorLibraryState>,
    project_id: String,
) -> Result<LibraryAudit, String> {
    let _guard = state.0.lock().map_err(|_| "HEOR library lock poisoned")?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    if crate::project::require_project_id(&workspace)? != project_id {
        return Err("library sync projectId does not match the current project".into());
    }
    build_index(&workspace, &project_id)?;
    crate::git_snapshot::commit_best_effort(&workspace, "Sync local HEOR evidence library");
    Ok(audit_library(&workspace))
}

#[tauri::command]
pub fn audit_heor_evidence_library(
    app: AppHandle,
    state: tauri::State<HeorLibraryState>,
) -> Result<LibraryAudit, String> {
    let _guard = state.0.lock().map_err(|_| "HEOR library lock poisoned")?;
    Ok(audit_library(&crate::runtime::workspace_dir(&app)?))
}

#[tauri::command]
pub fn search_heor_evidence_library(
    app: AppHandle,
    state: tauri::State<HeorLibraryState>,
    query: String,
    limit: usize,
) -> Result<LibrarySearchResponse, String> {
    let _guard = state.0.lock().map_err(|_| "HEOR library lock poisoned")?;
    search_library(&crate::runtime::workspace_dir(&app)?, query, limit)
}

fn search_library(
    workspace: &Path,
    query: String,
    limit: usize,
) -> Result<LibrarySearchResponse, String> {
    let query = query.trim().to_string();
    if query.is_empty() || query.chars().count() > MAX_QUERY_CHARS || !(1..=50).contains(&limit) {
        return Err(
            "local library search requires a 1-500 character query and a 1-50 result limit".into(),
        );
    }
    let audit = audit_library(workspace);
    if !audit.searchable {
        return Err(format!(
            "local evidence library is not safely searchable: {}",
            audit.errors.join("; ")
        ));
    }
    let query_tokens = tokens(&query);
    if query_tokens.is_empty() {
        return Err("local library search query has no searchable terms".into());
    }
    let connection = Connection::open(index_path(workspace))
        .map_err(|error| format!("local evidence index unavailable: {error}"))?;
    let mut statement = connection
        .prepare(
            "SELECT p.document_path,d.source_sha256,p.page_number,p.text,p.text_sha256
         FROM pages p JOIN documents d ON d.path=p.document_path
         WHERE d.extraction_status='indexed'",
        )
        .map_err(|error| error.to_string())?;
    let rows = statement
        .query_map([], |row| {
            Ok((
                row.get::<_, String>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, usize>(2)?,
                row.get::<_, String>(3)?,
                row.get::<_, String>(4)?,
            ))
        })
        .map_err(|error| error.to_string())?;
    let mut hits = Vec::new();
    for row in rows {
        let (path, source_sha256, page, text, text_sha256) =
            row.map_err(|error| error.to_string())?;
        if sha256(text.as_bytes()) != text_sha256 {
            return Err(format!(
                "local evidence index text hash failed for {path} page {page}"
            ));
        }
        let rank = score(&text, &query, &query_tokens);
        if rank > 0 {
            hits.push(LibrarySearchHit {
                path,
                source_sha256,
                page,
                score: rank,
                snippet: snippet(&text, &query_tokens),
            });
        }
    }
    hits.sort_by(|left, right| {
        right
            .score
            .cmp(&left.score)
            .then_with(|| left.path.cmp(&right.path))
            .then_with(|| left.page.cmp(&right.page))
    });
    hits.truncate(limit);
    Ok(LibrarySearchResponse { audit, query, hits })
}

#[tauri::command]
pub fn add_heor_library_files(
    app: AppHandle,
    state: tauri::State<HeorLibraryState>,
) -> Result<Vec<String>, String> {
    use tauri_plugin_dialog::DialogExt;
    let _guard = state.0.lock().map_err(|_| "HEOR library lock poisoned")?;
    let Some(picked) = app
        .dialog()
        .file()
        .add_filter("Evidence documents", &["pdf", "txt", "md", "csv", "json"])
        .blocking_pick_files()
    else {
        return Ok(Vec::new());
    };
    let workspace = crate::runtime::workspace_dir(&app)?;
    let library = ensure_library(&workspace)?;
    let selected = picked
        .into_iter()
        .map(|file| file.into_path().map_err(|error| error.to_string()))
        .collect::<Result<Vec<_>, _>>()?;
    let sizes = validate_import_sources(&workspace, &selected)?;
    let mut added = Vec::new();
    for (source, expected_bytes) in selected.into_iter().zip(sizes) {
        let name = source
            .file_name()
            .ok_or("selected evidence has no file name")?
            .to_string_lossy()
            .to_string();
        let destination = if std::fs::symlink_metadata(library.join(&name)).is_ok() {
            let stem = source
                .file_stem()
                .and_then(|value| value.to_str())
                .unwrap_or("evidence");
            let extension = source
                .extension()
                .and_then(|value| value.to_str())
                .unwrap_or("pdf");
            (1..10_000)
                .map(|number| library.join(format!("{stem}-{number}.{extension}")))
                .find(|candidate| std::fs::symlink_metadata(candidate).is_err())
                .ok_or("could not allocate a unique evidence file name")?
        } else {
            library.join(&name)
        };
        let copy_result = copy_checked(&source, &destination, expected_bytes);
        if let Err(error) = copy_result {
            let _ = std::fs::remove_file(&destination);
            return Err(error);
        }
        added.push(relative_slash(
            &destination,
            &workspace.canonicalize().map_err(|e| e.to_string())?,
        )?);
    }
    Ok(added)
}

#[tauri::command]
pub fn add_heor_library_directory(
    app: AppHandle,
    state: tauri::State<HeorLibraryState>,
) -> Result<LibraryDirectoryImport, String> {
    use tauri_plugin_dialog::DialogExt;
    let _guard = state.0.lock().map_err(|_| "HEOR library lock poisoned")?;
    let Some(picked) = app.dialog().file().blocking_pick_folder() else {
        return Ok(LibraryDirectoryImport {
            added: Vec::new(),
            skipped: Vec::new(),
        });
    };
    let selected = picked.into_path().map_err(|error| error.to_string())?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    import_library_directory(&workspace, &selected)
}

#[tauri::command]
pub fn install_bundled_heor_knowledge_base(
    app: AppHandle,
    state: tauri::State<HeorLibraryState>,
    project_id: String,
) -> Result<BundledLibraryInstall, String> {
    let _guard = state.0.lock().map_err(|_| "HEOR library lock poisoned")?;
    let resource = app
        .path()
        .resolve(BUNDLED_LIBRARY_RESOURCE, BaseDirectory::Resource)
        .map_err(|error| format!("bundled knowledge base is unavailable: {error}"))?;
    let workspace = crate::runtime::workspace_dir(&app)?;
    let result = install_bundled_library_from(&workspace, &resource, &project_id)?;
    crate::git_snapshot::commit_best_effort(
        &workspace,
        "Install bundled pharmacoeconomics knowledge base",
    );
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn workspace(tag: &str) -> PathBuf {
        let root =
            std::env::temp_dir().join(format!("ai4heor-library-{tag}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("heor/library")).unwrap();
        std::fs::create_dir_all(root.join(".openscience")).unwrap();
        std::fs::write(
            root.join(".openscience/project.json"),
            serde_json::json!({
                "id": "test-project", "name": "Test", "createdAt": 1, "version": 1
            })
            .to_string(),
        )
        .unwrap();
        root
    }

    #[test]
    fn indexes_and_searches_utf8_sources_with_hash_bound_pages() {
        let root = workspace("search");
        std::fs::write(
            root.join("heor/library/evidence.md"),
            "成本效果分析 compares incremental cost and QALY.",
        )
        .unwrap();
        build_index(&root, "test-project").unwrap();
        let audit = audit_library(&root);
        assert!(audit.complete, "{:?}", audit.errors);
        assert!(audit.searchable);
        let connection = Connection::open(index_path(&root)).unwrap();
        let text: String = connection
            .query_row("SELECT text FROM pages", [], |row| row.get(0))
            .unwrap();
        assert!(score(&text, "成本效果", &tokens("成本效果")) > 0);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn changed_source_bytes_fail_closed_until_resync() {
        let root = workspace("stale");
        std::fs::write(root.join("heor/library/source.txt"), "original evidence").unwrap();
        build_index(&root, "test-project").unwrap();
        std::fs::write(root.join("heor/library/source.txt"), "changed evidence").unwrap();
        let audit = audit_library(&root);
        assert!(audit.stale);
        assert!(!audit.searchable);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn empty_text_does_not_claim_success() {
        let root = workspace("empty");
        std::fs::write(root.join("heor/library/empty.txt"), "   \n").unwrap();
        build_index(&root, "test-project").unwrap();
        let audit = audit_library(&root);
        assert_eq!(audit.failed_count, 1);
        assert!(!audit.complete);
        let _ = std::fs::remove_dir_all(root);
    }

    #[cfg(unix)]
    #[test]
    fn library_symlinks_are_never_followed() {
        use std::os::unix::fs::symlink;
        let root = workspace("symlink");
        let outside = root.parent().unwrap().join("ai4heor-outside.txt");
        std::fs::write(&outside, "secret").unwrap();
        symlink(&outside, root.join("heor/library/link.txt")).unwrap();
        build_index(&root, "test-project").unwrap();
        let audit = audit_library(&root);
        assert!(!audit.complete);
        assert!(audit
            .errors
            .iter()
            .any(|error| error.contains("symbolic links")));
        let _ = std::fs::remove_file(outside);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn import_preflight_enforces_the_total_file_cap() {
        let root = workspace("import-cap");
        let repeated = vec![root.join("selected.txt"); MAX_FILES + 1];
        let error = validate_import_sources(&root, &repeated).unwrap_err();
        assert!(error.contains("500-file"));
        let _ = std::fs::remove_dir_all(root);
    }

    #[cfg(unix)]
    #[test]
    fn import_preflight_rejects_selected_symlinks() {
        use std::os::unix::fs::symlink;
        let root = workspace("import-selected-symlink");
        let outside = root.parent().unwrap().join("ai4heor-selected-outside.txt");
        let selected = root.parent().unwrap().join("ai4heor-selected-link.txt");
        std::fs::write(&outside, "evidence").unwrap();
        symlink(&outside, &selected).unwrap();
        let error = validate_import_sources(&root, std::slice::from_ref(&selected)).unwrap_err();
        assert!(error.contains("symbolic link"));
        let _ = std::fs::remove_file(selected);
        let _ = std::fs::remove_file(outside);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn directory_import_preserves_hierarchy_and_reports_skipped_entries() {
        let root = workspace("directory-import");
        let source = root
            .parent()
            .unwrap()
            .join(format!("ai4heor-kb-source-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&source);
        std::fs::create_dir_all(source.join("00-navigation")).unwrap();
        std::fs::create_dir_all(source.join("02-methods")).unwrap();
        std::fs::create_dir_all(source.join(".private")).unwrap();
        std::fs::write(source.join("00-navigation/map.md"), "Knowledge map").unwrap();
        std::fs::write(source.join("02-methods/cea.txt"), "Cost effectiveness").unwrap();
        std::fs::write(source.join("cover.png"), b"not imported").unwrap();
        std::fs::write(source.join(".DS_Store"), b"hidden").unwrap();
        std::fs::write(source.join(".private/notes.md"), "hidden subtree").unwrap();

        let imported = import_library_directory(&root, &source).unwrap();
        let source_name = source.file_name().unwrap().to_string_lossy();
        assert_eq!(
            imported.added,
            vec![
                format!("heor/library/{source_name}/00-navigation/map.md"),
                format!("heor/library/{source_name}/02-methods/cea.txt"),
            ]
        );
        assert_eq!(
            imported.skipped,
            vec![".DS_Store", ".private/", "cover.png"]
        );
        assert_eq!(
            std::fs::read_to_string(root.join(&imported.added[1])).unwrap(),
            "Cost effectiveness"
        );
        let second = import_library_directory(&root, &source).unwrap();
        assert!(second.added[0].contains(&format!("{source_name}-1/")));

        let _ = std::fs::remove_dir_all(source);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn directory_import_rejects_workspace_overlap() {
        let root = workspace("directory-overlap");
        let error = import_library_directory(&root, &root.join("heor")).unwrap_err();
        assert!(error.contains("must not contain, or be contained by"));
        let error = import_library_directory(&root, root.parent().unwrap()).unwrap_err();
        assert!(error.contains("must not contain, or be contained by"));
        let _ = std::fs::remove_dir_all(root);
    }

    #[cfg(unix)]
    #[test]
    fn directory_import_rejects_nested_symlinks() {
        use std::os::unix::fs::symlink;
        let root = workspace("directory-symlink");
        let source = root
            .parent()
            .unwrap()
            .join(format!("ai4heor-kb-symlink-source-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&source);
        std::fs::create_dir_all(&source).unwrap();
        std::fs::write(source.join("source.md"), "evidence").unwrap();
        symlink(source.join("source.md"), source.join("link.md")).unwrap();
        let error = import_library_directory(&root, &source).unwrap_err();
        assert!(error.contains("contains a symbolic link"));
        let _ = std::fs::remove_dir_all(source);
        let _ = std::fs::remove_dir_all(root);
    }

    fn bundled_source() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../runtime/knowledge-base/zh-Hans")
    }

    #[test]
    fn bundled_learning_library_is_hash_bound_and_searchable() {
        let root = workspace("bundled-learning-library");
        let result =
            install_bundled_library_from(&root, &bundled_source(), "test-project").unwrap();
        assert_eq!(result.schema, BUNDLED_LIBRARY_SCHEMA);
        assert_eq!(result.bundle_id, BUNDLED_LIBRARY_ID);
        assert_eq!(result.added.len(), 26);
        assert!(!result.already_installed);
        assert!(result.audit.complete, "{:?}", result.audit.errors);
        assert!(result.audit.searchable);
        assert_eq!(result.audit.document_count, 26);
        assert!(root
            .join("heor/library")
            .join(BUNDLED_LIBRARY_DESTINATION)
            .join("04-最新进展/截至2026-07的方法学与政策进展.md")
            .is_file());
        let search = search_library(&root, "机会成本".into(), 5).unwrap();
        assert!(!search.hits.is_empty());
        assert!(search.hits.iter().any(|hit| {
            hit.path
                .ends_with("01-基础理论/01-稀缺性、效率与机会成本.md")
                && hit.source_sha256.len() == 64
                && hit.page == 1
        }));

        let manifest_before = std::fs::read(root.join(LIBRARY_MANIFEST_PATH)).unwrap();
        let index_before = std::fs::read(index_path(&root)).unwrap();
        let second =
            install_bundled_library_from(&root, &bundled_source(), "test-project").unwrap();
        assert!(second.already_installed);
        assert!(second.added.is_empty());
        assert_eq!(
            std::fs::read(root.join(LIBRARY_MANIFEST_PATH)).unwrap(),
            manifest_before
        );
        assert_eq!(std::fs::read(index_path(&root)).unwrap(), index_before);
        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn edited_bundled_learning_library_is_preserved_and_rejected() {
        let root = workspace("bundled-learning-library-edited");
        install_bundled_library_from(&root, &bundled_source(), "test-project").unwrap();
        let edited = root
            .join("heor/library")
            .join(BUNDLED_LIBRARY_DESTINATION)
            .join("README.md");
        std::fs::write(&edited, "researcher edit\n").unwrap();
        let error =
            install_bundled_library_from(&root, &bundled_source(), "test-project").unwrap_err();
        assert!(error.contains("existing files were preserved"));
        assert_eq!(
            std::fs::read_to_string(edited).unwrap(),
            "researcher edit\n"
        );
        let _ = std::fs::remove_dir_all(root);
    }
}
