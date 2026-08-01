//! Small, local-only checks for the files AI4HEOR needs before research work.
//!
//! This is intentionally not a scientific validation and does not probe a
//! model provider or the network. It only proves that the active project
//! folder is writable and that the packaged Skills, HEOR engine, and project
//! harness needed by the desktop app are present as regular local files.

use serde::Serialize;
use std::fs::{self, OpenOptions};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager};

const MIN_FIRST_PARTY_SKILLS: usize = 53;
const ESSENTIAL_SKILLS: [&str; 9] = [
    "ai4heor-preference-learning",
    "ai4heor-skill-authoring",
    "heor-decision-tree",
    "heor-reference-case",
    "heor-reporting",
    "heor-reproducibility-package",
    "heor-workbench",
    "research-presentation",
    "traceability-review",
];
const HEOR_ENGINE_FILES: [&str; 5] = [
    "__init__.py",
    "cli.py",
    "decision_tree.py",
    "decision_tree_uncertainty.py",
    "model.py",
];
const HARNESS_FILES: [&str; 4] = [
    "AGENTS.md",
    "KNOWLEDGE.md",
    "learning/preferences.json",
    "policy.json",
];

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct StartupEnvironmentCheck {
    id: String,
    ready: bool,
    detail: String,
}

impl StartupEnvironmentCheck {
    fn ready(id: &str, detail: impl Into<String>) -> Self {
        Self {
            id: id.into(),
            ready: true,
            detail: detail.into(),
        }
    }

    fn failed(id: &str, detail: impl Into<String>) -> Self {
        Self {
            id: id.into(),
            ready: false,
            detail: detail.into(),
        }
    }
}

#[derive(Debug, Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct StartupEnvironmentAudit {
    desktop: bool,
    required_ready: bool,
    workspace_path: Option<String>,
    checks: Vec<StartupEnvironmentCheck>,
}

fn regular_file(path: &Path) -> bool {
    fs::symlink_metadata(path)
        .map(|metadata| metadata.file_type().is_file() && !metadata.file_type().is_symlink())
        .unwrap_or(false)
}

fn write_probe(directory: &Path) -> Result<(), String> {
    if !directory.is_dir() {
        return Err(format!(
            "project folder is unavailable: {}",
            directory.display()
        ));
    }
    let nonce = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|error| error.to_string())?
        .as_nanos();
    let probe = directory.join(format!(
        ".ai4heor-startup-check-{}-{nonce}",
        std::process::id()
    ));
    let result = (|| -> Result<(), String> {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&probe)
            .map_err(|error| format!("project folder is not writable: {error}"))?;
        file.write_all(b"AI4HEOR local startup check\n")
            .map_err(|error| format!("project folder write failed: {error}"))?;
        file.flush()
            .map_err(|error| format!("project folder write failed: {error}"))?;
        Ok(())
    })();
    let cleanup = if probe.exists() {
        fs::remove_file(&probe)
            .map_err(|error| format!("could not remove startup check file: {error}"))
    } else {
        Ok(())
    };
    result.and(cleanup)
}

fn inspect_skills(root: &Path) -> Result<usize, String> {
    let metadata = fs::symlink_metadata(root)
        .map_err(|error| format!("could not read packaged Skills: {error}"))?;
    if !metadata.file_type().is_dir() || metadata.file_type().is_symlink() {
        return Err("packaged Skills path is not a regular directory".into());
    }
    let mut count = 0usize;
    for entry in fs::read_dir(root).map_err(|error| error.to_string())? {
        let entry = entry.map_err(|error| error.to_string())?;
        let kind = entry.file_type().map_err(|error| error.to_string())?;
        if kind.is_symlink() {
            return Err(format!(
                "packaged Skill path is a link: {}",
                entry.path().display()
            ));
        }
        if kind.is_dir() && regular_file(&entry.path().join("SKILL.md")) {
            count += 1;
        }
    }
    if count < MIN_FIRST_PARTY_SKILLS {
        return Err(format!(
            "only {count} of at least {MIN_FIRST_PARTY_SKILLS} first-party Skills are available"
        ));
    }
    for name in ESSENTIAL_SKILLS {
        if !regular_file(&root.join(name).join("SKILL.md")) {
            return Err(format!("required Skill is unavailable: {name}"));
        }
    }
    Ok(count)
}

fn inspect_required_files(root: &Path, relative: &[&str]) -> Result<usize, String> {
    let metadata = fs::symlink_metadata(root)
        .map_err(|error| format!("could not read {}: {error}", root.display()))?;
    if !metadata.file_type().is_dir() || metadata.file_type().is_symlink() {
        return Err(format!(
            "required resource is not a regular directory: {}",
            root.display()
        ));
    }
    for name in relative {
        if !regular_file(&root.join(name)) {
            return Err(format!("required resource is unavailable: {name}"));
        }
    }
    Ok(relative.len())
}

fn run_audit(
    workspace: PathBuf,
    skills: Result<PathBuf, String>,
    heor_engine: Result<PathBuf, String>,
    harness: Result<PathBuf, String>,
) -> StartupEnvironmentAudit {
    let workspace_path = Some(workspace.to_string_lossy().to_string());
    let mut checks = Vec::with_capacity(4);
    checks.push(match write_probe(&workspace) {
        Ok(()) => StartupEnvironmentCheck::ready("workspace", workspace.display().to_string()),
        Err(error) => StartupEnvironmentCheck::failed("workspace", error),
    });
    checks.push(match skills.and_then(|path| inspect_skills(&path)) {
        Ok(count) => StartupEnvironmentCheck::ready("skills", count.to_string()),
        Err(error) => StartupEnvironmentCheck::failed("skills", error),
    });
    checks.push(
        match heor_engine.and_then(|path| inspect_required_files(&path, &HEOR_ENGINE_FILES)) {
            Ok(count) => StartupEnvironmentCheck::ready("heorCore", format!("{count}/{count}")),
            Err(error) => StartupEnvironmentCheck::failed("heorCore", error),
        },
    );
    checks.push(
        match harness.and_then(|path| inspect_required_files(&path, &HARNESS_FILES)) {
            Ok(count) => StartupEnvironmentCheck::ready("harness", format!("{count}/{count}")),
            Err(error) => StartupEnvironmentCheck::failed("harness", error),
        },
    );
    StartupEnvironmentAudit {
        desktop: true,
        required_ready: checks.iter().all(|check| check.ready),
        workspace_path,
        checks,
    }
}

/// Audit only local, required startup resources. No provider, model, network,
/// Python, Jupyter, or scientific-validity check is performed here.
#[tauri::command(async)]
pub async fn audit_startup_environment(app: AppHandle) -> Result<StartupEnvironmentAudit, String> {
    let workspace = crate::runtime::workspace_dir(&app)?;
    let resolve = |name: &str| {
        app.path()
            .resolve(name, tauri::path::BaseDirectory::Resource)
            .map_err(|error| error.to_string())
    };
    let skills = resolve("skills-core");
    let heor_engine = resolve("heor-core/src/heor_core");
    let harness = resolve("harness");
    tauri::async_runtime::spawn_blocking(move || run_audit(workspace, skills, heor_engine, harness))
        .await
        .map_err(|error| format!("startup check did not finish: {error}"))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    fn fixture(label: &str) -> PathBuf {
        std::env::temp_dir().join(format!(
            "ai4heor-startup-audit-{label}-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap()
                .as_nanos()
        ))
    }

    fn valid_fixture(root: &Path) -> (PathBuf, PathBuf, PathBuf, PathBuf) {
        let workspace = root.join("workspace");
        let skills = root.join("skills-core");
        let engine = root.join("heor-core/src/heor_core");
        let harness = root.join("harness");
        fs::create_dir_all(&workspace).unwrap();
        fs::create_dir_all(&engine).unwrap();
        fs::create_dir_all(harness.join("learning")).unwrap();
        for name in HEOR_ENGINE_FILES {
            fs::write(engine.join(name), "# fixture\n").unwrap();
        }
        for name in HARNESS_FILES {
            fs::write(harness.join(name), "fixture\n").unwrap();
        }
        let mut names: Vec<String> = ESSENTIAL_SKILLS
            .iter()
            .map(|name| name.to_string())
            .collect();
        while names.len() < MIN_FIRST_PARTY_SKILLS {
            names.push(format!("fixture-skill-{:02}", names.len()));
        }
        for name in names {
            let dir = skills.join(name);
            fs::create_dir_all(&dir).unwrap();
            fs::write(dir.join("SKILL.md"), "---\nname: fixture\n---\n").unwrap();
        }
        (workspace, skills, engine, harness)
    }

    #[test]
    fn complete_local_fixture_is_ready_and_leaves_no_probe() {
        let root = fixture("ready");
        let (workspace, skills, engine, harness) = valid_fixture(&root);
        let audit = run_audit(workspace.clone(), Ok(skills), Ok(engine), Ok(harness));
        assert!(audit.required_ready);
        assert!(audit.checks.iter().all(|check| check.ready));
        assert_eq!(fs::read_dir(&workspace).unwrap().count(), 0);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn missing_required_skill_fails_closed() {
        let root = fixture("missing-skill");
        let (workspace, skills, engine, harness) = valid_fixture(&root);
        fs::remove_file(skills.join("heor-workbench/SKILL.md")).unwrap();
        let audit = run_audit(workspace, Ok(skills), Ok(engine), Ok(harness));
        assert!(!audit.required_ready);
        let check = audit
            .checks
            .iter()
            .find(|check| check.id == "skills")
            .unwrap();
        assert!(!check.ready);
        assert!(check.detail.contains("53") || check.detail.contains("heor-workbench"));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn incomplete_current_first_party_catalog_fails_closed() {
        let root = fixture("incomplete-current-catalog");
        let (workspace, skills, engine, harness) = valid_fixture(&root);
        fs::remove_dir_all(skills.join("fixture-skill-52")).unwrap();

        let audit = run_audit(workspace, Ok(skills), Ok(engine), Ok(harness));

        assert!(!audit.required_ready);
        assert!(audit
            .checks
            .iter()
            .any(|check| check.id == "skills" && check.detail.contains("53")));
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn missing_harness_file_fails_closed() {
        let root = fixture("missing-harness");
        let (workspace, skills, engine, harness) = valid_fixture(&root);
        fs::remove_file(harness.join("policy.json")).unwrap();
        let audit = run_audit(workspace, Ok(skills), Ok(engine), Ok(harness));
        assert!(!audit.required_ready);
        assert!(audit
            .checks
            .iter()
            .any(|check| check.id == "harness" && !check.ready));
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn linked_skill_tree_fails_closed() {
        use std::os::unix::fs::symlink;

        let root = fixture("linked-skill");
        let (workspace, skills, engine, harness) = valid_fixture(&root);
        let target = skills.join("real-linked-skill");
        fs::create_dir_all(&target).unwrap();
        fs::write(target.join("SKILL.md"), "fixture\n").unwrap();
        symlink(&target, skills.join("linked-skill")).unwrap();
        let audit = run_audit(workspace, Ok(skills), Ok(engine), Ok(harness));
        assert!(!audit.required_ready);
        assert!(audit
            .checks
            .iter()
            .any(|check| check.id == "skills" && check.detail.contains("link")));
        fs::remove_dir_all(root).unwrap();
    }
}
