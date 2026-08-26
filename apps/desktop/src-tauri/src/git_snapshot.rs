use std::collections::{BTreeMap, HashMap};
use std::path::{Path, PathBuf};
use std::sync::mpsc::{self, Receiver, RecvTimeoutError, Sender};
use std::sync::{Mutex, OnceLock};
use std::time::{Duration, Instant};

use notify::{EventKind, RecommendedWatcher, RecursiveMode, Watcher};
use tauri::AppHandle;

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

fn git_error(action: &str, error: git2::Error) -> String {
    format!("local history {action} failed: {error}")
}

fn changed_paths(repo: &git2::Repository, index: &git2::Index) -> Result<Vec<PathBuf>, String> {
    let head_tree = repo.head().ok().and_then(|head| head.peel_to_tree().ok());
    let diff = repo
        .diff_tree_to_index(head_tree.as_ref(), Some(index), None)
        .map_err(|error| git_error("diff", error))?;
    let mut paths = Vec::new();
    for delta in diff.deltas() {
        let path = delta
            .new_file()
            .path()
            .or_else(|| delta.old_file().path())
            .map(Path::to_path_buf);
        if let Some(path) = path {
            paths.push(path);
        }
    }
    Ok(paths)
}

fn restore_index_entry(
    index: &mut git2::Index,
    previous: &HashMap<Vec<u8>, git2::IndexEntry>,
    path: &Path,
) -> Result<(), String> {
    let key = path.to_string_lossy().replace('\\', "/").into_bytes();
    if let Some(entry) = previous.get(&key) {
        index
            .add(entry)
            .map_err(|error| git_error("restore index entry", error))
    } else {
        match index.remove_path(path) {
            Ok(()) => Ok(()),
            Err(error) if error.code() == git2::ErrorCode::NotFound => Ok(()),
            Err(error) => Err(git_error("remove excluded index entry", error)),
        }
    }
}

fn exclude_large_changes(
    repo: &git2::Repository,
    root: &Path,
    index: &mut git2::Index,
    previous: &HashMap<Vec<u8>, git2::IndexEntry>,
) -> Result<(), String> {
    let changed = changed_paths(repo, index)?;
    let mut excluded = Vec::new();
    let mut by_dir: BTreeMap<PathBuf, u64> = BTreeMap::new();

    for path in &changed {
        let size = std::fs::metadata(root.join(path))
            .map(|meta| if meta.is_file() { meta.len() } else { 0 })
            .unwrap_or(0);
        if size >= MAX_BLOB_BYTES {
            excluded.push(path.clone());
        }
        if let Some(parent) = path
            .parent()
            .filter(|parent| !parent.as_os_str().is_empty())
        {
            *by_dir.entry(parent.to_path_buf()).or_default() += size;
        }
    }
    for (dir, _) in by_dir
        .into_iter()
        .filter(|(_, bytes)| *bytes >= MAX_DIR_BYTES)
    {
        excluded.extend(
            changed
                .iter()
                .filter(|path| path.starts_with(&dir))
                .cloned(),
        );
    }
    excluded.sort();
    excluded.dedup();
    for path in excluded {
        restore_index_entry(index, previous, &path)?;
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
    if root.join(".git").exists() {
        // A pre-existing repo is only ours if we planted the marker at init.
        return Ok(snapshot_marker(root).exists());
    }
    git2::Repository::init(root).map_err(|error| git_error("initialization", error))?;
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
    let repo = git2::Repository::open(root).map_err(|error| git_error("open", error))?;
    let mut index = repo
        .index()
        .map_err(|error| git_error("read index", error))?;
    let previous: HashMap<Vec<u8>, git2::IndexEntry> = index
        .iter()
        .map(|entry| (entry.path.clone(), entry))
        .collect();
    index
        .add_all(["*"], git2::IndexAddOption::DEFAULT, None)
        .map_err(|error| git_error("stage", error))?;
    exclude_large_changes(&repo, root, &mut index, &previous)?;
    index
        .write()
        .map_err(|error| git_error("write index", error))?;
    if changed_paths(&repo, &index)?.is_empty() {
        return Ok(false);
    }
    let tree_id = index
        .write_tree()
        .map_err(|error| git_error("write tree", error))?;
    let tree = repo
        .find_tree(tree_id)
        .map_err(|error| git_error("read tree", error))?;
    let signature = git2::Signature::now(AUTHOR_NAME, AUTHOR_EMAIL)
        .map_err(|error| git_error("create signature", error))?;
    let parent = repo.head().ok().and_then(|head| head.peel_to_commit().ok());
    let parents: Vec<&git2::Commit<'_>> = parent.iter().collect();
    repo.commit(
        Some("HEAD"),
        &signature,
        &signature,
        message,
        &tree,
        &parents,
    )
    .map_err(|error| git_error("commit", error))?;
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

#[allow(clippy::type_complexity)]
fn workspace_watcher() -> &'static Mutex<Option<(RecommendedWatcher, PathBuf)>> {
    static WATCHER: OnceLock<Mutex<Option<(RecommendedWatcher, PathBuf)>>> = OnceLock::new();
    WATCHER.get_or_init(|| Mutex::new(None))
}

/// Watch the active workspace so work produced by external editors or detached
/// analysis processes is included in the same debounced local provenance log.
pub fn watch_workspace(root: &Path) {
    let Ok(mut slot) = workspace_watcher().lock() else {
        return;
    };
    if slot.as_ref().is_some_and(|(_, current)| current == root) {
        return;
    }
    let callback_root = root.to_path_buf();
    let handler = move |result: notify::Result<notify::Event>| {
        let Ok(event) = result else { return };
        if matches!(event.kind, EventKind::Access(_)) {
            return;
        }
        if event
            .paths
            .iter()
            .any(|path| path.components().any(|part| part.as_os_str() == ".git"))
        {
            return;
        }
        commit_best_effort(&callback_root, "Snapshot workspace changes");
    };
    let mut watcher = match notify::recommended_watcher(handler) {
        Ok(watcher) => watcher,
        Err(error) => {
            eprintln!("workspace watcher unavailable: {error}");
            return;
        }
    };
    if let Err(error) = watcher.watch(root, RecursiveMode::Recursive) {
        eprintln!(
            "workspace watcher could not watch {}: {error}",
            root.display()
        );
        return;
    }
    *slot = Some((watcher, root.to_path_buf()));
}

#[tauri::command(async)]
pub fn commit_workspace_snapshot(app: AppHandle, message: String) -> Result<bool, String> {
    let root = crate::runtime::workspace_dir(&app)?;
    commit(&root, &message)
}

#[cfg(test)]
mod tests {
    use super::{commit, snapshot_due, SNAPSHOT_DEBOUNCE, SNAPSHOT_MAX_WAIT};
    use std::fs;
    use std::time::Duration;

    fn tracked_paths(root: &std::path::Path) -> Vec<String> {
        let repo = git2::Repository::open(root).unwrap();
        let index = repo.index().unwrap();
        index
            .iter()
            .map(|entry| String::from_utf8(entry.path).unwrap())
            .collect()
    }

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
    fn commit_initializes_repo_without_system_git() {
        const CHILD: &str = "AI4HEOR_TEST_WITHOUT_SYSTEM_GIT";
        if std::env::var_os(CHILD).is_some() {
            let root =
                std::env::temp_dir().join(format!("ai4heor-embedded-git-{}", std::process::id()));
            let _ = fs::remove_dir_all(&root);
            fs::create_dir_all(&root).unwrap();
            fs::write(root.join("AGENTS.md"), "rules\n").unwrap();

            assert!(commit(&root, "Initialize workspace").unwrap());
            assert!(root.join(".git").is_dir());
            assert!(root.join(".git/.openscience-snapshots").is_file());
            let _ = fs::remove_dir_all(&root);
            return;
        }

        let status = std::process::Command::new(std::env::current_exe().unwrap())
            .args([
                "--exact",
                "git_snapshot::tests::commit_initializes_repo_without_system_git",
                "--nocapture",
            ])
            .env(CHILD, "1")
            .env("PATH", "")
            .status()
            .unwrap();
        assert!(
            status.success(),
            "local task history must not depend on a system Git installation"
        );
    }

    #[test]
    fn commit_writes_safe_default_ignore_without_replacing_user_rules() {
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
    fn commit_respects_generated_secret_ignores() {
        let root = std::env::temp_dir().join(format!("ai4heor-git-secret-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        fs::write(root.join("analysis.R"), "print('ok')\n").unwrap();
        fs::write(root.join(".env"), "API_KEY=do-not-snapshot\n").unwrap();

        commit(&root, "Initialize workspace").unwrap();
        let tracked = tracked_paths(&root);
        assert!(tracked.contains(&"analysis.R".to_string()));
        assert!(!tracked.contains(&".env".to_string()));
        assert!(root.join(".env").is_file());
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn commit_records_tracked_file_deletion() {
        let root = std::env::temp_dir().join(format!("ai4heor-git-delete-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        let analysis = root.join("analysis.R");
        fs::write(&analysis, "print('ok')\n").unwrap();
        commit(&root, "Initialize workspace").unwrap();

        fs::remove_file(&analysis).unwrap();
        assert!(commit(&root, "Remove analysis").unwrap());
        assert!(!tracked_paths(&root).contains(&"analysis.R".to_string()));
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn commit_omits_oversized_file_without_deleting_it() {
        let root = std::env::temp_dir().join(format!("ai4heor-git-large-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        fs::write(root.join("analysis.R"), "print('ok')\n").unwrap();
        let large = root.join("claims.parquet");
        let file = fs::File::create(&large).unwrap();
        file.set_len(super::MAX_BLOB_BYTES).unwrap();
        commit(&root, "Initialize workspace").unwrap();
        let tracked = tracked_paths(&root);
        assert!(tracked.contains(&"analysis.R".to_string()));
        assert!(!tracked.contains(&"claims.parquet".to_string()));
        assert!(large.exists());
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn commit_preserves_prior_snapshot_when_a_tracked_file_becomes_oversized() {
        let root = std::env::temp_dir().join(format!("ai4heor-git-growing-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        let data = root.join("claims.parquet");
        fs::write(&data, b"small reviewed input\n").unwrap();
        commit(&root, "Initialize workspace").unwrap();

        fs::OpenOptions::new()
            .write(true)
            .open(&data)
            .unwrap()
            .set_len(super::MAX_BLOB_BYTES)
            .unwrap();
        assert!(!commit(&root, "Oversized update").unwrap());

        let repo = git2::Repository::open(&root).unwrap();
        let tree = repo.head().unwrap().peel_to_tree().unwrap();
        let blob = tree
            .get_path(std::path::Path::new("claims.parquet"))
            .unwrap()
            .to_object(&repo)
            .unwrap()
            .peel_to_blob()
            .unwrap();
        assert_eq!(blob.content(), b"small reviewed input\n");
        assert_eq!(fs::metadata(&data).unwrap().len(), super::MAX_BLOB_BYTES);
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn commit_omits_bulk_directory_without_deleting_files() {
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
        let tracked = tracked_paths(&root);
        assert!(tracked.contains(&"analysis.R".to_string()));
        assert!(!tracked.iter().any(|path| path.starts_with("claims/")));
        assert!(data.join("part-0.bin").exists());
        let _ = fs::remove_dir_all(&root);
    }

    #[test]
    fn commit_never_touches_a_repo_the_user_brought() {
        let root = std::env::temp_dir().join(format!("os-git-foreign-{}", std::process::id()));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        // A repo the user brought in: it has a .git but none of our marker.
        git2::Repository::init(&root).unwrap();
        fs::write(root.join("data.txt"), "user work in progress\n").unwrap();

        // We must decline it, leave the tree/index alone, and plant no marker.
        assert!(!commit(&root, "should be skipped").unwrap());
        assert!(!super::snapshot_marker(&root).exists());
        let _ = fs::remove_dir_all(&root);
    }
}
