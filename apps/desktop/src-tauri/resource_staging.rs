use std::fs;
use std::io::ErrorKind;
use std::path::{Path, PathBuf};

const ADMITTED_SKILL_STAGING_DIRECTORY: &str = "skills-admitted-ai4s";

pub fn staged_admitted_skills_path(out_dir: &Path) -> Result<PathBuf, String> {
    let package_build_dir = out_dir
        .parent()
        .filter(|_| out_dir.file_name().is_some_and(|name| name == "out"))
        .ok_or_else(|| format!("unexpected Cargo OUT_DIR: {}", out_dir.display()))?;
    let build_dir = package_build_dir
        .parent()
        .filter(|_| {
            package_build_dir
                .file_name()
                .is_some_and(|name| name.to_string_lossy().starts_with("ai4s-workbench-"))
        })
        .ok_or_else(|| format!("unexpected Cargo OUT_DIR: {}", out_dir.display()))?;
    let profile_dir = build_dir
        .parent()
        .filter(|_| build_dir.file_name().is_some_and(|name| name == "build"))
        .ok_or_else(|| format!("unexpected Cargo OUT_DIR: {}", out_dir.display()))?;
    Ok(profile_dir.join(ADMITTED_SKILL_STAGING_DIRECTORY))
}

pub fn clean_staged_admitted_skills(out_dir: &Path) -> Result<PathBuf, String> {
    let staged = staged_admitted_skills_path(out_dir)?;
    match fs::symlink_metadata(&staged) {
        Ok(metadata) if metadata.is_dir() && !metadata.file_type().is_symlink() => {
            fs::remove_dir_all(&staged).map_err(|error| {
                format!(
                    "cannot clean admitted Skill staging directory {}: {error}",
                    staged.display()
                )
            })?;
        }
        Ok(_) => {
            fs::remove_file(&staged).map_err(|error| {
                format!(
                    "cannot clean invalid admitted Skill staging entry {}: {error}",
                    staged.display()
                )
            })?;
        }
        Err(error) if error.kind() == ErrorKind::NotFound => {}
        Err(error) => {
            return Err(format!(
                "cannot inspect admitted Skill staging entry {}: {error}",
                staged.display()
            ));
        }
    }
    Ok(staged)
}
