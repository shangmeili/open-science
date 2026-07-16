use std::path::{Path, PathBuf};
use std::sync::{Mutex, OnceLock};

use tauri::AppHandle;

use crate::runtime::quiet_command;

/// Serializes every snapshot commit process-wide. The frontend (on
/// `session.idle`) and several Rust record paths can all try to commit the same
/// workspace at once; without this they race on `.git/index.lock` and silently
/// drop snapshots. Workspaces are used one at a time, so a single global lock is
/// enough and each commit is quick.
fn git_lock() -> &'static Mutex<()> {
    static LOCK: OnceLock<Mutex<()>> = OnceLock::new();
    LOCK.get_or_init(|| Mutex::new(()))
}

const AUTHOR_NAME: &str = "Open Science Desktop";
const AUTHOR_EMAIL: &str = "open-science-desktop@local";

fn git(root: &Path) -> std::process::Command {
    let mut cmd = quiet_command("git");
    cmd.current_dir(root)
        .env("GIT_AUTHOR_NAME", AUTHOR_NAME)
        .env("GIT_AUTHOR_EMAIL", AUTHOR_EMAIL)
        .env("GIT_COMMITTER_NAME", AUTHOR_NAME)
        .env("GIT_COMMITTER_EMAIL", AUTHOR_EMAIL);
    cmd
}

pub fn git_available() -> bool {
    quiet_command("git")
        .arg("--version")
        .output()
        .map(|o| o.status.success())
        .unwrap_or(false)
}

fn run(root: &Path, args: &[&str]) -> Result<(), String> {
    let out = git(root)
        .args(args)
        .output()
        .map_err(|e| format!("git {} failed to start: {e}", args.join(" ")))?;
    if out.status.success() {
        return Ok(());
    }
    let stderr = String::from_utf8_lossy(&out.stderr).trim().to_string();
    Err(format!(
        "git {} failed{}",
        args.join(" "),
        if stderr.is_empty() {
            String::new()
        } else {
            format!(": {stderr}")
        },
    ))
}

/// Written inside `.git` the first time WE create a snapshot repo. Its presence
/// is how we recognize an app-managed repo that is safe to `add -A`/commit into;
/// we never touch a git repository the user brought into the workspace himself.
fn snapshot_marker(root: &Path) -> PathBuf {
    root.join(".git").join(".openscience-snapshots")
}

/// Ensure an app-owned snapshot repo exists. Returns `Ok(false)` when the folder
/// already holds a git repo we did not create — the caller must then NOT commit,
/// so the user's own history and staged work are left untouched.
fn ensure_owned_repo(root: &Path) -> Result<bool, String> {
    if !git_available() {
        return Err("git is not available".into());
    }
    if root.join(".git").exists() {
        // A pre-existing repo is only ours if we planted the marker at init.
        return Ok(snapshot_marker(root).exists());
    }
    run(root, &["init"])?;
    std::fs::write(snapshot_marker(root), b"1")
        .map_err(|e| format!("could not mark snapshot repo: {e}"))?;
    Ok(true)
}

pub fn commit(root: &Path, message: &str) -> Result<bool, String> {
    let _lock = git_lock().lock().map_err(|_| "git snapshot lock poisoned".to_string())?;
    if !ensure_owned_repo(root)? {
        // Not an app-managed repo — never commit into the user's own history.
        return Ok(false);
    }
    run(root, &["add", "-A", "--", "."])?;
    let status = git(root)
        .args(["diff", "--cached", "--quiet"])
        .status()
        .map_err(|e| format!("git diff failed to start: {e}"))?;
    if status.success() {
        return Ok(false);
    }
    run(root, &["commit", "-m", message])?;
    Ok(true)
}

pub fn commit_best_effort(root: &Path, message: &str) {
    if let Err(e) = commit(root, message) {
        eprintln!("workspace git snapshot skipped: {e}");
    }
}

#[tauri::command(async)]
pub fn commit_workspace_snapshot(app: AppHandle, message: String) -> Result<bool, String> {
    let root = crate::runtime::workspace_dir(&app)?;
    commit(&root, &message)
}

#[cfg(test)]
mod tests {
    use super::{commit, git_available};
    use std::fs;

    #[test]
    fn commit_initializes_repo_and_skips_clean_tree() {
        if !git_available() {
            eprintln!("git unavailable; skipping git snapshot test");
            return;
        }
        let root = std::env::temp_dir().join(format!("os-git-snapshot-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        fs::write(root.join("AGENTS.md"), "rules\n").unwrap();

        assert!(commit(&root, "Initialize workspace").unwrap());
        assert!(root.join(".git").is_dir());
        assert!(!commit(&root, "No changes").unwrap());

        fs::write(root.join("AGENTS.md"), "rules\nmore\n").unwrap();
        assert!(commit(&root, "Update workspace").unwrap());
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn commit_never_touches_a_repo_the_user_brought() {
        if !git_available() {
            eprintln!("git unavailable; skipping git snapshot test");
            return;
        }
        let root = std::env::temp_dir().join(format!("os-git-foreign-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        // A repo the user brought in: it has a .git but none of our marker.
        super::run(&root, &["init"]).unwrap();
        fs::write(root.join("data.txt"), "user work in progress\n").unwrap();

        // We must decline it, leave the tree/index alone, and plant no marker.
        assert!(!commit(&root, "should be skipped").unwrap());
        assert!(!super::snapshot_marker(&root).exists());
        let _ = fs::remove_dir_all(&root);
    }
}
