// AI4HEOR projects: named HEOR workspace folders under the base dir, marked by
// the historical compatibility path `<folder>/.openscience/project.json`.
// The folder IS the workspace — sessions group under a project by their
// `directory`, so no registry or database exists to drift out of sync. Folders
// without the marker stay plain dated session workspaces.
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use tauri::AppHandle;

use crate::runtime::{base_workspace_dir, random_hex};

const HEOR_PROJECT_KIND: &str = "heor";

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

/// A corrupt or missing project.json makes the folder a plain workspace again
/// — never an error the UI has to handle.
fn read_meta(dir: &Path) -> Option<ProjectMeta> {
    let text = std::fs::read_to_string(meta_file(dir)).ok()?;
    serde_json::from_str(&text).ok()
}

/// The stable identity of the project owning `dir`. Decision-relevant HEOR
/// state must bind to this marker instead of accepting a caller-selected id.
pub(crate) fn require_project_id(dir: &Path) -> Result<String, String> {
    read_meta(dir)
        .filter(|meta| meta.kind == HEOR_PROJECT_KIND)
        .map(|meta| meta.id)
        .ok_or_else(|| "HEOR work requires the current workspace to be an AI4HEOR project".into())
}

fn write_meta(dir: &Path, meta: &ProjectMeta) -> Result<(), String> {
    let file = meta_file(dir);
    if let Some(parent) = file.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }
    let json = serde_json::to_string_pretty(meta).map_err(|e| e.to_string())?;
    std::fs::write(&file, json).map_err(|e| e.to_string())
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
    ProjectInfo {
        id: meta.id,
        name: meta.name,
        description: meta.description,
        created_at: meta.created_at,
        kind: meta.kind,
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
        version: 2,
    };
    write_meta(&dir, &meta)?;
    Ok((dir, meta))
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

/// Every project under the base dir (first-level folders carrying a readable
/// project.json), sorted by name for a stable sidebar.
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
            if let Some(meta) = read_meta(&dir) {
                out.push(info_of(meta, &dir));
            }
        }
    }
    out.sort_by_key(|project| project.name.to_lowercase());
    Ok(out)
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
    let mut meta = read_meta(&dir).ok_or("not a project folder")?;
    meta.name = name.to_string();
    write_meta(&dir, &meta)
}

#[cfg(test)]
mod tests {
    use super::{create_in, folder_slug, read_meta, require_project_id, HEOR_PROJECT_KIND};
    use std::fs;

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
    fn corrupt_meta_reads_as_no_project() {
        let base = std::env::temp_dir().join(format!("os-project-bad-{}", std::process::id()));
        let _ = fs::remove_dir_all(&base);
        let dir = base.join("broken");
        fs::create_dir_all(dir.join(".openscience")).unwrap();
        fs::write(dir.join(".openscience").join("project.json"), "{not json").unwrap();
        assert!(read_meta(&dir).is_none());
        assert!(require_project_id(&dir).is_err());
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
}
