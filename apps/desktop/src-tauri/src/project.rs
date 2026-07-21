// AI4HEOR projects: named HEOR workspace folders under the base dir, marked by
// the historical compatibility path `<folder>/.openscience/project.json`.
// The folder IS the workspace — sessions group under a project by their
// `directory`, so no registry or database exists to drift out of sync. Dated
// standalone conversation folders use the same marker with `kind: session` but
// are deliberately excluded from the Projects list.
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use tauri::AppHandle;

use crate::runtime::{base_workspace_dir, random_hex};

const HEOR_PROJECT_KIND: &str = "heor";
const SESSION_SCOPE_KIND: &str = "session";

fn default_project_kind() -> String {
    HEOR_PROJECT_KIND.into()
}

#[derive(Serialize, Deserialize, Clone)]
pub struct ProjectMeta {
    pub id: String,
    pub name: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(rename = "createdAt")]
    pub created_at: u64,
    #[serde(default = "default_project_kind")]
    pub kind: String,
    /// Original folder for a project copied into the AI4HEOR workspace.
    /// This is provenance only; the app always operates on the local copy.
    #[serde(
        rename = "importedFrom",
        default,
        skip_serializing_if = "Option::is_none"
    )]
    pub imported_from: Option<String>,
    pub version: u32,
}

/// What the frontend consumes: the metadata plus the folder it lives in.
#[derive(Serialize)]
pub struct ProjectInfo {
    pub id: String,
    pub name: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub description: Option<String>,
    #[serde(rename = "createdAt")]
    pub created_at: u64,
    pub kind: String,
    pub imported: bool,
    #[serde(rename = "importedFrom", skip_serializing_if = "Option::is_none")]
    pub imported_from: Option<String>,
    /// Absolute workspace folder (canonical, matches session `directory`).
    pub path: String,
}

fn meta_file(dir: &Path) -> PathBuf {
    dir.join(".openscience").join("project.json")
}

fn now_ms() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0)
}

/// A corrupt or missing scope marker is treated as absent. Opening a legacy
/// standalone folder repairs the missing marker through `set_workspace`.
fn read_meta(dir: &Path) -> Option<ProjectMeta> {
    let text = std::fs::read_to_string(meta_file(dir)).ok()?;
    serde_json::from_str(&text).ok()
}

/// The stable identity of the research scope owning `dir`. The serialized
/// field remains `projectId` for compatibility, but both named projects and
/// standalone conversations have an app-issued identity. This keeps HEOR
/// review and audit functions available without forcing a conversation into a
/// project.
pub(crate) fn require_project_id(dir: &Path) -> Result<String, String> {
    read_meta(dir)
        .filter(|meta| meta.kind == HEOR_PROJECT_KIND || meta.kind == SESSION_SCOPE_KIND)
        .map(|meta| meta.id)
        .ok_or_else(|| "HEOR work requires an AI4HEOR research scope".into())
}

fn write_meta(dir: &Path, meta: &ProjectMeta) -> Result<(), String> {
    let file = meta_file(dir);
    if let Some(parent) = file.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let json = serde_json::to_string_pretty(meta).map_err(|e| e.to_string())?;
    std::fs::write(&file, json).map_err(|e| e.to_string())
}

/// Give a standalone conversation the same stable local identity used by the
/// HEOR audit boundary, without making it appear in the Projects list.
pub(crate) fn ensure_session_scope(dir: &Path, name: &str) -> Result<String, String> {
    if let Some(meta) = read_meta(dir) {
        if meta.kind == HEOR_PROJECT_KIND || meta.kind == SESSION_SCOPE_KIND {
            return Ok(meta.id);
        }
        return Err("workspace metadata has an unsupported research-scope kind".into());
    }
    if meta_file(dir).exists() {
        return Err("workspace research-scope metadata is unreadable".into());
    }
    let meta = ProjectMeta {
        id: random_hex(8),
        name: name.trim().to_string(),
        description: None,
        created_at: now_ms(),
        kind: SESSION_SCOPE_KIND.into(),
        imported_from: None,
        version: 2,
    };
    write_meta(dir, &meta)?;
    Ok(meta.id)
}

/// Project name → folder name: one path segment, no whitespace (the agent runs
/// unquoted shell commands against workspace paths), no path-unsafe characters.
/// Unicode (e.g. CJK project names) passes through untouched.
fn folder_slug(name: &str) -> String {
    let cleaned: String = name
        .trim()
        .chars()
        .map(|c| match c {
            '/' | '\\' | ':' | '*' | '?' | '"' | '<' | '>' | '|' => '-',
            c if c.is_whitespace() => '-',
            c => c,
        })
        .collect();
    let collapsed = cleaned
        .split('-')
        .filter(|s| !s.is_empty() && !s.chars().all(|c| c == '.'))
        .collect::<Vec<_>>()
        .join("-");
    let trimmed = collapsed.trim_matches('.').to_string();
    if trimmed.is_empty() {
        "project".into()
    } else {
        trimmed
    }
}

fn info_of(meta: ProjectMeta, dir: &Path) -> ProjectInfo {
    let canon = dir.canonicalize().unwrap_or_else(|_| dir.to_path_buf());
    let imported = meta.imported_from.is_some();
    ProjectInfo {
        id: meta.id,
        name: meta.name,
        description: meta.description,
        created_at: meta.created_at,
        kind: meta.kind,
        imported,
        imported_from: meta.imported_from,
        path: canon.to_string_lossy().to_string(),
    }
}

/// Create the folder + metadata under `base`. Split from the command so the
/// filesystem logic is unit-testable without an AppHandle.
fn create_in(base: &Path, name: &str) -> Result<(PathBuf, ProjectMeta), String> {
    let name = name.trim();
    if name.is_empty() {
        return Err("project name is empty".into());
    }
    let slug = folder_slug(name);
    let mut dir = base.join(&slug);
    for n in 2..100 {
        if !dir.exists() {
            break;
        }
        dir = base.join(format!("{slug}-{n}"));
    }
    if dir.exists() {
        return Err(format!("a folder named \"{slug}\" already exists"));
    }
    let meta = ProjectMeta {
        id: random_hex(8),
        name: name.to_string(),
        description: None,
        created_at: now_ms(),
        kind: HEOR_PROJECT_KIND.into(),
        imported_from: None,
        version: 2,
    };
    write_meta(&dir, &meta)?;
    Ok((dir, meta))
}

/// Copy an existing folder without following links. Internal links remain
/// links in the copy; sockets, FIFOs and device nodes are skipped so a stale
/// runtime file cannot block the whole import.
fn copy_tree(source: &Path, destination: &Path) -> std::io::Result<()> {
    std::fs::create_dir_all(destination)?;
    for entry in std::fs::read_dir(source)? {
        let entry = entry?;
        let from = entry.path();
        let to = destination.join(entry.file_name());
        let file_type = entry.file_type()?;
        if file_type.is_symlink() {
            symlink_any(&std::fs::read_link(&from)?, &to)?;
        } else if file_type.is_dir() {
            copy_tree(&from, &to)?;
            if let Ok(metadata) = std::fs::metadata(&from) {
                let _ = std::fs::set_permissions(&to, metadata.permissions());
            }
        } else if file_type.is_file() {
            std::fs::copy(&from, &to)?;
        }
    }
    Ok(())
}

#[cfg(unix)]
fn symlink_any(target: &Path, link: &Path) -> std::io::Result<()> {
    std::os::unix::fs::symlink(target, link)
}

#[cfg(windows)]
fn symlink_any(target: &Path, link: &Path) -> std::io::Result<()> {
    let probe = if target.is_absolute() {
        target.to_path_buf()
    } else {
        link.parent().unwrap_or_else(|| Path::new(".")).join(target)
    };
    if probe.is_dir() {
        std::os::windows::fs::symlink_dir(target, link)
    } else {
        std::os::windows::fs::symlink_file(target, link)
    }
}

fn restore_owner_write(dir: &Path) {
    let Ok(metadata) = std::fs::symlink_metadata(dir) else {
        return;
    };
    if !metadata.is_dir() {
        return;
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut permissions = metadata.permissions();
        permissions.set_mode(permissions.mode() | 0o700);
        let _ = std::fs::set_permissions(dir, permissions);
    }
    if let Ok(entries) = std::fs::read_dir(dir) {
        for entry in entries.flatten() {
            if entry.file_type().map(|kind| kind.is_dir()).unwrap_or(false) {
                restore_owner_write(&entry.path());
            }
        }
    }
}

fn remove_tree(dir: &Path) -> std::io::Result<()> {
    restore_owner_write(dir);
    std::fs::remove_dir_all(dir)
}

/// Import by faithful copy. The original is never moved, edited, used as the
/// runtime workspace, or given AI4HEOR metadata. Hidden provenance is kept in
/// the copy and excluded from the Research files surface.
#[tauri::command(async)]
pub fn import_project(app: AppHandle, path: String) -> Result<ProjectInfo, String> {
    let base = base_workspace_dir(&app)?;
    let selected = PathBuf::from(path.trim());
    if path.trim().is_empty() || !selected.is_dir() {
        return Err("the selected folder does not exist".into());
    }
    let source = selected
        .canonicalize()
        .map_err(|error| format!("could not resolve the selected folder: {error}"))?;
    let base_canonical = base
        .canonicalize()
        .map_err(|error| format!("could not resolve the AI4HEOR workspace: {error}"))?;
    if source == base_canonical || source.starts_with(&base_canonical) {
        return Err("this folder is already managed by AI4HEOR".into());
    }
    if base_canonical.starts_with(&source) {
        return Err("cannot import a folder that contains the AI4HEOR workspace".into());
    }
    let name = source
        .file_name()
        .map(|value| value.to_string_lossy().to_string())
        .filter(|value| !value.trim().is_empty())
        .unwrap_or_else(|| "imported-project".into());
    let (destination, mut meta) = create_in(&base, &name)?;
    let result = (|| {
        copy_tree(&source, &destination)
            .map_err(|error| format!("could not copy the selected folder: {error}"))?;
        let copied_control = destination.join(".openscience");
        if copied_control.exists() {
            remove_tree(&copied_control)
                .map_err(|error| format!("could not replace copied app metadata: {error}"))?;
        }
        meta.imported_from = Some(source.to_string_lossy().to_string());
        write_meta(&destination, &meta)?;
        crate::harness::seed_harness(&app, &destination).map_err(|error| {
            format!("could not initialize the AI4HEOR research contract: {error}")
        })?;
        let provenance = destination.join(".openscience").join("IMPORTED_FROM.md");
        std::fs::write(
            provenance,
            format!(
                "# Imported project\n\nAI4HEOR copied this project from:\n\n`{}`\n\nThe original folder is not modified. All tasks run against this local copy.\n",
                source.display()
            ),
        )
        .map_err(|error| format!("could not record import provenance: {error}"))?;
        crate::git_snapshot::commit_best_effort(&destination, "Import project");
        Ok(info_of(meta.clone(), &destination))
    })();
    if result.is_err() {
        let _ = remove_tree(&destination);
    }
    result
}

/// Create an AI4HEOR project: a fresh folder under the base dir with typed HEOR
/// metadata, the researcher-led assistant harness, and an initial git snapshot.
/// Does NOT switch the active workspace; the frontend decides when to move into it.
#[tauri::command(async)]
pub fn create_project(app: AppHandle, name: String) -> Result<ProjectInfo, String> {
    let base = base_workspace_dir(&app)?;
    let (dir, meta) = create_in(&base, &name)?;
    if let Err(error) = crate::harness::seed_harness(&app, &dir) {
        let rollback = std::fs::remove_dir_all(&dir);
        return Err(match rollback {
            Ok(()) => format!("could not initialize the AI4HEOR research contract: {error}"),
            Err(cleanup_error) => format!(
                "could not initialize the AI4HEOR research contract: {error}; \
                 could not remove incomplete project {}: {cleanup_error}",
                dir.display()
            ),
        });
    }
    crate::git_snapshot::commit_best_effort(&dir, "Initialize project");
    Ok(info_of(meta, &dir))
}

/// Every named HEOR project under the base dir, sorted by name for a stable
/// sidebar. Standalone conversation scopes are intentionally excluded.
#[tauri::command(async)]
pub fn list_projects(app: AppHandle) -> Result<Vec<ProjectInfo>, String> {
    let base = base_workspace_dir(&app)?;
    let mut out: Vec<ProjectInfo> = Vec::new();
    if let Ok(entries) = std::fs::read_dir(&base) {
        for entry in entries.flatten() {
            let dir = entry.path();
            if !dir.is_dir() {
                continue;
            }
            if let Some(meta) = read_meta(&dir).filter(|meta| meta.kind == HEOR_PROJECT_KIND) {
                out.push(info_of(meta, &dir));
            }
        }
    }
    out.sort_by_key(|project| project.name.to_lowercase());
    Ok(out)
}

/// The active named project or standalone conversation scope. This is kept
/// separate from `list_projects`: a standalone conversation can use the full
/// HEOR review surface without appearing as a project in the sidebar.
#[tauri::command]
pub fn current_research_scope(app: AppHandle) -> Result<Option<ProjectInfo>, String> {
    let dir = crate::runtime::workspace_dir(&app)?;
    Ok(read_meta(&dir)
        .filter(|meta| meta.kind == HEOR_PROJECT_KIND || meta.kind == SESSION_SCOPE_KIND)
        .map(|meta| info_of(meta, &dir)))
}

/// Rename the project's display name only — the folder never moves, so session
/// `directory` grouping stays intact.
#[tauri::command(async)]
pub fn rename_project(path: String, name: String) -> Result<(), String> {
    let name = name.trim();
    if name.is_empty() {
        return Err("project name is empty".into());
    }
    let dir = PathBuf::from(&path);
    let mut meta = read_meta(&dir)
        .filter(|meta| meta.kind == HEOR_PROJECT_KIND)
        .ok_or("not a project folder")?;
    meta.name = name.to_string();
    write_meta(&dir, &meta)
}

#[cfg(test)]
mod tests {
    use super::{
        copy_tree, create_in, ensure_session_scope, folder_slug, now_ms, read_meta,
        require_project_id, HEOR_PROJECT_KIND, SESSION_SCOPE_KIND,
    };
    use std::{fs, path::PathBuf};

    #[test]
    fn slug_is_one_safe_path_segment() {
        assert_eq!(folder_slug("BCI Trends 2026"), "BCI-Trends-2026");
        assert_eq!(folder_slug("  a/b\\c:d  "), "a-b-c-d");
        assert_eq!(folder_slug("脑机接口趋势"), "脑机接口趋势");
        assert_eq!(folder_slug("..."), "project");
        assert_eq!(folder_slug(""), "project");
        assert_eq!(folder_slug("../etc"), "etc"); // no traversal segments survive
    }

    #[test]
    fn create_writes_meta_and_dedupes_folder_names() {
        let base = std::env::temp_dir().join(format!("os-project-{}", std::process::id()));
        let _ = fs::remove_dir_all(&base);
        fs::create_dir_all(&base).unwrap();

        let (dir1, meta1) = create_in(&base, "My Study").unwrap();
        assert_eq!(dir1, base.join("My-Study"));
        assert_eq!(meta1.name, "My Study");
        let read = read_meta(&dir1).unwrap();
        assert_eq!(read.id, meta1.id);
        assert_eq!(read.kind, HEOR_PROJECT_KIND);
        assert_eq!(read.imported_from, None);
        assert_eq!(read.version, 2);
        assert_eq!(require_project_id(&dir1).unwrap(), meta1.id);

        // Same name again → a distinct folder, its own identity.
        let (dir2, meta2) = create_in(&base, "My Study").unwrap();
        assert_eq!(dir2, base.join("My-Study-2"));
        assert_ne!(meta2.id, meta1.id);

        assert!(create_in(&base, "   ").is_err());
        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn copy_tree_preserves_project_files_without_touching_the_source() {
        let root = std::env::temp_dir().join(format!(
            "ai4heor-project-copy-{}-{}",
            std::process::id(),
            now_ms()
        ));
        let source = root.join("source");
        let destination = root.join("destination");
        fs::create_dir_all(source.join("data")).unwrap();
        fs::write(source.join("README.md"), "original\n").unwrap();
        fs::write(source.join("data/input.csv"), "cost,qaly\n100,2\n").unwrap();

        copy_tree(&source, &destination).unwrap();

        assert_eq!(
            fs::read_to_string(destination.join("README.md")).unwrap(),
            "original\n"
        );
        assert_eq!(
            fs::read_to_string(destination.join("data/input.csv")).unwrap(),
            "cost,qaly\n100,2\n"
        );
        fs::write(destination.join("README.md"), "copy changed\n").unwrap();
        assert_eq!(
            fs::read_to_string(source.join("README.md")).unwrap(),
            "original\n"
        );

        let _ = fs::remove_dir_all(root);
    }

    #[cfg(unix)]
    #[test]
    fn copy_tree_preserves_symlinks_instead_of_following_them() {
        use std::os::unix::fs::symlink;

        let root = std::env::temp_dir().join(format!(
            "ai4heor-project-link-{}-{}",
            std::process::id(),
            now_ms()
        ));
        let source = root.join("source");
        let destination = root.join("destination");
        fs::create_dir_all(&source).unwrap();
        fs::write(source.join("target.txt"), "target\n").unwrap();
        symlink("target.txt", source.join("link.txt")).unwrap();

        copy_tree(&source, &destination).unwrap();

        assert!(fs::symlink_metadata(destination.join("link.txt"))
            .unwrap()
            .file_type()
            .is_symlink());
        assert_eq!(
            fs::read_link(destination.join("link.txt")).unwrap(),
            PathBuf::from("target.txt")
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn corrupt_meta_reads_as_no_project() {
        let base = std::env::temp_dir().join(format!("os-project-bad-{}", std::process::id()));
        let _ = fs::remove_dir_all(&base);
        let dir = base.join("broken");
        fs::create_dir_all(dir.join(".openscience")).unwrap();
        fs::write(dir.join(".openscience").join("project.json"), "{not json").unwrap();
        assert!(read_meta(&dir).is_none());
        assert!(require_project_id(&dir).is_err());
        assert!(ensure_session_scope(&dir, "broken").is_err());
        assert_eq!(
            fs::read_to_string(dir.join(".openscience").join("project.json")).unwrap(),
            "{not json"
        );
        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn legacy_project_meta_defaults_to_heor_kind() {
        let base =
            std::env::temp_dir().join(format!("ai4heor-project-legacy-{}", std::process::id()));
        let _ = fs::remove_dir_all(&base);
        let dir = base.join("legacy");
        fs::create_dir_all(dir.join(".openscience")).unwrap();
        fs::write(
            dir.join(".openscience").join("project.json"),
            r#"{"id":"legacy-id","name":"Legacy HEOR","createdAt":1,"version":1}"#,
        )
        .unwrap();

        let meta = read_meta(&dir).unwrap();
        assert_eq!(meta.kind, HEOR_PROJECT_KIND);
        assert_eq!(require_project_id(&dir).unwrap(), "legacy-id");
        let _ = fs::remove_dir_all(&base);
    }

    #[test]
    fn standalone_conversation_has_a_stable_non_project_research_scope() {
        let base =
            std::env::temp_dir().join(format!("ai4heor-session-scope-{}", std::process::id()));
        let _ = fs::remove_dir_all(&base);
        fs::create_dir_all(&base).unwrap();

        let id = ensure_session_scope(&base, "2026-07-20-1200").unwrap();
        let meta = read_meta(&base).unwrap();
        assert_eq!(meta.kind, SESSION_SCOPE_KIND);
        assert_eq!(meta.name, "2026-07-20-1200");
        assert_eq!(require_project_id(&base).unwrap(), id);
        assert_eq!(ensure_session_scope(&base, "ignored").unwrap(), id);

        let _ = fs::remove_dir_all(&base);
    }
}
