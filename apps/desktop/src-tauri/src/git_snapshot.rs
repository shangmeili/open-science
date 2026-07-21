use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError, Sender};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

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

const AUTHOR_NAME: &str = "AI4HEOR Desktop";
const AUTHOR_EMAIL: &str = "ai4heor@local";

/// Keep individual files at or above this size out of automatic local
/// snapshots. The file stays in the project; only the Git snapshot omits it.
const MAX_BLOB_BYTES: u64 = 20 * 1024 * 1024;

/// A directory can contain thousands of files that are individually small but
/// collectively unsuitable for Git history. Guard the newly staged aggregate
/// for each immediate parent directory as well.
const MAX_DIR_BYTES: u64 = 50 * 1024 * 1024;

/// Written only when AI4HEOR creates the snapshot repository. Existing
/// `.gitignore` files are never replaced.
const DEFAULT_GITIGNORE: &str = "\
# Managed by AI4HEOR Desktop.\n\
# Local snapshots keep reproducible research files while excluding secrets,\n\
# dependency environments, caches and high-volume binary media.\n\
\n\
# Secrets and credentials\n\
.env\n\
.env.*\n\
!.env.example\n\
!.env.sample\n\
!.env.template\n\
*.pem\n\
*.key\n\
*.p12\n\
*.pfx\n\
.netrc\n\
credentials.json\n\
secrets.json\n\
service-account*.json\n\
.aws/\n\
.gcloud/\n\
\n\
# Operating-system and editor files\n\
.DS_Store\n\
._*\n\
.Spotlight-V100\n\
.Trashes\n\
Thumbs.db\n\
Desktop.ini\n\
$RECYCLE.BIN/\n\
.vscode/\n\
.idea/\n\
*.swp\n\
*.swo\n\
*~\n\
\n\
# Python, R and Node environments or caches\n\
__pycache__/\n\
*.py[cod]\n\
.venv/\n\
venv/\n\
env/\n\
.conda/\n\
.pytest_cache/\n\
.mypy_cache/\n\
.ruff_cache/\n\
.tox/\n\
.coverage\n\
htmlcov/\n\
.ipynb_checkpoints/\n\
.Rhistory\n\
.RData\n\
.Rproj.user/\n\
node_modules/\n\
.npm/\n\
.yarn/\n\
.pnpm-store/\n\
*-debug.log*\n\
\n\
# Temporary files and caches\n\
*.tmp\n\
*.temp\n\
*.bak\n\
.cache/\n\
tmp/\n\
.tmp/\n\
\n\
# High-volume raster, audio and video media\n\
*.mp4\n\
*.m4v\n\
*.mov\n\
*.avi\n\
*.mkv\n\
*.webm\n\
*.jpg\n\
*.jpeg\n\
*.png\n\
*.gif\n\
*.bmp\n\
*.tif\n\
*.tiff\n\
*.webp\n\
*.heic\n\
*.wav\n\
*.flac\n\
*.aac\n\
*.m4a\n\
*.mp3\n\
*.ogg\n";

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

fn capture(root: &Path, args: &[&str]) -> Result<Vec<u8>, String> {
    let out = git(root)
        .args(args)
        .output()
        .map_err(|e| format!("git {} failed to start: {e}", args.join(" ")))?;
    if out.status.success() {
        return Ok(out.stdout);
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

fn unstage_oversized(root: &Path) -> Result<(), String> {
    let stdout = capture(root, &["diff", "--cached", "--name-only", "-z"])?;
    let mut skipped = Vec::new();
    for name in stdout
        .split(|byte| *byte == 0)
        .filter(|name| !name.is_empty())
    {
        let rel = String::from_utf8_lossy(name).into_owned();
        if std::fs::metadata(root.join(&rel))
            .map(|meta| meta.is_file() && meta.len() >= MAX_BLOB_BYTES)
            .unwrap_or(false)
        {
            skipped.push(rel);
        }
    }
    if skipped.is_empty() {
        return Ok(());
    }
    let mut args = vec!["reset", "--quiet", "--"];
    args.extend(skipped.iter().map(String::as_str));
    run(root, &args)
}

fn unstage_bulk_dirs(root: &Path) -> Result<(), String> {
    use std::collections::BTreeMap;

    let stdout = capture(root, &["diff", "--cached", "--name-only", "-z"])?;
    let mut by_dir: BTreeMap<String, u64> = BTreeMap::new();
    for name in stdout
        .split(|byte| *byte == 0)
        .filter(|name| !name.is_empty())
    {
        let rel = String::from_utf8_lossy(name).into_owned();
        let Some(separator) = rel.rfind('/') else {
            continue;
        };
        let size = std::fs::metadata(root.join(&rel))
            .map(|meta| if meta.is_file() { meta.len() } else { 0 })
            .unwrap_or(0);
        *by_dir.entry(rel[..separator].to_string()).or_default() += size;
    }
    for (dir, _) in by_dir
        .into_iter()
        .filter(|(_, bytes)| *bytes >= MAX_DIR_BYTES)
    {
        run(root, &["reset", "--quiet", "--", &dir])?;
    }
    Ok(())
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
    let gitignore = root.join(".gitignore");
    if !gitignore.exists() {
        std::fs::write(&gitignore, DEFAULT_GITIGNORE)
            .map_err(|e| format!("could not write .gitignore: {e}"))?;
    }
    Ok(true)
}

pub fn commit(root: &Path, message: &str) -> Result<bool, String> {
    let _lock = git_lock()
        .lock()
        .map_err(|_| "git snapshot lock poisoned".to_string())?;
    if !ensure_owned_repo(root)? {
        // Not an app-managed repo — never commit into the user's own history.
        return Ok(false);
    }
    run(root, &["add", "-A", "--", "."])?;
    unstage_oversized(root)?;
    unstage_bulk_dirs(root)?;
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

const SNAPSHOT_DEBOUNCE: Duration = Duration::from_secs(3);
const SNAPSHOT_MAX_WAIT: Duration = Duration::from_secs(30);

#[derive(Clone, Copy)]
struct PendingSnapshot {
    first: Instant,
    last: Instant,
}

fn snapshot_due(since_last: Duration, since_first: Duration) -> bool {
    since_last >= SNAPSHOT_DEBOUNCE || since_first >= SNAPSHOT_MAX_WAIT
}

fn snapshot_sender() -> &'static Sender<PathBuf> {
    static SENDER: OnceLock<Sender<PathBuf>> = OnceLock::new();
    SENDER.get_or_init(|| {
        let (sender, receiver) = mpsc::channel();
        if let Err(error) = std::thread::Builder::new()
            .name("ai4heor-git-snapshot".into())
            .spawn(move || snapshot_loop(receiver))
        {
            eprintln!("workspace snapshot thread unavailable: {error}");
        }
        sender
    })
}

fn snapshot_loop(receiver: Receiver<PathBuf>) {
    let mut pending: HashMap<PathBuf, PendingSnapshot> = HashMap::new();
    loop {
        let timeout = pending
            .values()
            .map(|item| {
                SNAPSHOT_DEBOUNCE
                    .saturating_sub(item.last.elapsed())
                    .min(SNAPSHOT_MAX_WAIT.saturating_sub(item.first.elapsed()))
            })
            .min()
            .unwrap_or(Duration::from_secs(3600));
        match receiver.recv_timeout(timeout) {
            Ok(root) => {
                let now = Instant::now();
                pending
                    .entry(root)
                    .and_modify(|item| item.last = now)
                    .or_insert(PendingSnapshot {
                        first: now,
                        last: now,
                    });
            }
            Err(RecvTimeoutError::Timeout) => {}
            Err(RecvTimeoutError::Disconnected) => return,
        }
        let due: Vec<PathBuf> = pending
            .iter()
            .filter(|(_, item)| snapshot_due(item.last.elapsed(), item.first.elapsed()))
            .map(|(root, _)| root.clone())
            .collect();
        for root in due {
            pending.remove(&root);
            if let Err(error) = commit(&root, "Snapshot workspace changes") {
                eprintln!("workspace git snapshot skipped: {error}");
            }
        }
    }
}

/// Queue a local snapshot and return immediately. Bursts of file writes become
/// one background commit after a quiet window instead of blocking every write.
pub fn commit_best_effort(root: &Path, _message: &str) {
    let _ = snapshot_sender().send(root.to_path_buf());
}

#[tauri::command(async)]
pub fn commit_workspace_snapshot(app: AppHandle, message: String) -> Result<bool, String> {
    let root = crate::runtime::workspace_dir(&app)?;
    commit(&root, &message)
}

#[cfg(test)]
mod tests {
    use super::{commit, git_available, snapshot_due, SNAPSHOT_DEBOUNCE, SNAPSHOT_MAX_WAIT};
    use std::fs;
    use std::time::Duration;

    #[test]
    fn snapshot_requests_debounce_bursts_and_have_a_starvation_cap() {
        assert!(!snapshot_due(
            Duration::from_millis(500),
            Duration::from_secs(2),
        ));
        assert!(snapshot_due(SNAPSHOT_DEBOUNCE, Duration::from_secs(5)));
        assert!(snapshot_due(Duration::from_millis(100), SNAPSHOT_MAX_WAIT,));
    }

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
    fn commit_writes_safe_default_ignore_without_replacing_user_rules() {
        if !git_available() {
            return;
        }
        let root = std::env::temp_dir().join(format!("ai4heor-git-ignore-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        fs::write(root.join("analysis.R"), "print('ok')\n").unwrap();
        commit(&root, "Initialize workspace").unwrap();
        let generated = fs::read_to_string(root.join(".gitignore")).unwrap();
        assert!(generated.contains("Managed by AI4HEOR Desktop"));
        assert!(generated.contains(".env"));
        assert!(generated.contains("node_modules/"));

        let root2 = root.with_extension("user-ignore");
        let _ = fs::remove_dir_all(&root2);
        fs::create_dir_all(&root2).unwrap();
        fs::write(root2.join(".gitignore"), "research-cache/\n").unwrap();
        fs::write(root2.join("analysis.R"), "print('ok')\n").unwrap();
        commit(&root2, "Initialize workspace").unwrap();
        assert_eq!(
            fs::read_to_string(root2.join(".gitignore")).unwrap(),
            "research-cache/\n"
        );
        let _ = fs::remove_dir_all(&root);
        let _ = fs::remove_dir_all(&root2);
    }

    #[test]
    fn commit_omits_oversized_file_without_deleting_it() {
        if !git_available() {
            return;
        }
        let root = std::env::temp_dir().join(format!("ai4heor-git-large-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        fs::write(root.join("analysis.R"), "print('ok')\n").unwrap();
        let large = root.join("claims.parquet");
        let file = fs::File::create(&large).unwrap();
        file.set_len(super::MAX_BLOB_BYTES).unwrap();
        commit(&root, "Initialize workspace").unwrap();
        let tracked = String::from_utf8(super::capture(&root, &["ls-files"]).unwrap()).unwrap();
        assert!(tracked.contains("analysis.R"));
        assert!(!tracked.contains("claims.parquet"));
        assert!(large.exists());
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn commit_omits_bulk_directory_without_deleting_files() {
        if !git_available() {
            return;
        }
        let root = std::env::temp_dir().join(format!("ai4heor-git-bulk-{}", std::process::id()));
        let data = root.join("claims");
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&data).unwrap();
        fs::write(root.join("analysis.R"), "print('ok')\n").unwrap();
        for index in 0..4 {
            let file = fs::File::create(data.join(format!("part-{index}.bin"))).unwrap();
            file.set_len(15 * 1024 * 1024).unwrap();
        }
        commit(&root, "Initialize workspace").unwrap();
        let tracked = String::from_utf8(super::capture(&root, &["ls-files"]).unwrap()).unwrap();
        assert!(tracked.contains("analysis.R"));
        assert!(!tracked.contains("claims/"));
        assert!(data.join("part-0.bin").exists());
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
