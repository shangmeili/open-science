// Artifact provenance (P0-3): every agent write of a workspace file appends a
// version record to <workspace>/.openscience/provenance.jsonl — append-only,
// one JSON object per line, so any artifact can reveal its generating code,
// environment, and originating conversation, per version.
use std::collections::HashMap;
use std::path::{Component, Path, PathBuf};
use std::sync::Mutex;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::AppHandle;

use crate::runtime::workspace_dir;

const STORE_DIR: &str = ".openscience";
const STORE_FILE: &str = "provenance.jsonl";
/// Per-record content cap: keeps the store bounded; larger writes are truncated.
const CONTENT_CAP: usize = 100_000;

/// Serializes appends so two tool events can't interleave lines or race versions.
#[derive(Default)]
pub struct ProvenanceState(pub Mutex<()>);

#[derive(Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProvenanceRecord {
    /// Workspace-relative artifact path with `/` separators.
    pub path: String,
    /// 1-based version, assigned on append.
    pub version: u32,
    /// Seconds since the epoch (the frontend formats it).
    pub ts: u64,
    /// Tool that produced this version, e.g. "write".
    pub tool: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub model: Option<String>,
    /// Text the tool wrote (capped); absent for binary or indirect writes.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub content: Option<String>,
    /// Unified diff of an incremental edit (capped); the lineage of a change
    /// when the full file text wasn't in the event.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub diff: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub log: Option<String>,
    /// Runtime environment captured when the version was recorded.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub env: Option<EnvInfo>,
    /// The run that produced this version, when it came from executing code
    /// (not an authored write). Links the file to its reproducibility recipe.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub run_id: Option<String>,
}

/// The environment a version was produced in — enough to reproduce: which
/// Python, which OS/arch, which app build, and which installed packages.
/// Captured once per app run (cheap).
#[derive(Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct EnvInfo {
    /// Local Python version, e.g. "3.12.4" (the interpreter agent code runs on).
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub python: Option<String>,
    /// OS and architecture, e.g. "macos-aarch64".
    pub platform: String,
    /// Open Science app version that recorded this.
    pub app: String,
    /// Installed Python packages (pip freeze), content-addressed to a lockfile.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub packages: Option<PackageSnapshot>,
    /// Hardware the code executed on — the part software can't otherwise pin.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub hardware: Option<HardwareInfo>,
}

/// The silicon a run executed on. Every field is best-effort ("record what we
/// can"): a probe that isn't installed or fails just leaves its field absent.
/// Captured once per app run (cheap; hardware doesn't change mid-session).
#[derive(Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct HardwareInfo {
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cpu: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub cores: Option<u32>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub mem_gb: Option<u32>,
    /// GPU model(s); empty when none detected.
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub gpu: Vec<String>,
    /// Available accelerator: "cuda" | "mps" | "cpu".
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub accelerator: Option<String>,
}

/// A snapshot of the installed Python packages at record time. The full
/// `name==version` list is stored once, content-addressed, at
/// `.openscience/env/<hash>.txt`; records carry only the count + hash so the
/// store stays small and identical environments dedupe to one lockfile.
#[derive(Clone, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PackageSnapshot {
    /// Number of installed packages captured.
    pub count: u32,
    /// Short content hash; the lockfile is `.openscience/env/<hash>.txt`.
    pub hash: String,
}

const ENV_DIR: &str = "env";

fn cached_probe(
    cache: &Mutex<HashMap<String, Option<String>>>,
    interpreter: &str,
    compute: impl FnOnce() -> Option<String>,
) -> Option<String> {
    if let Ok(values) = cache.lock() {
        if let Some(value) = values.get(interpreter) {
            return value.clone();
        }
    }
    let value = compute();
    if let Ok(mut values) = cache.lock() {
        values.insert(interpreter.to_string(), value.clone());
    }
    value
}

fn pip_freeze(interpreter: &str) -> Option<String> {
    static CACHE: std::sync::OnceLock<Mutex<HashMap<String, Option<String>>>> =
        std::sync::OnceLock::new();
    cached_probe(CACHE.get_or_init(Mutex::default), interpreter, || {
        let out = crate::runtime::quiet_command(interpreter)
            .args(["-m", "pip", "freeze"])
            .output()
            .ok()?;
        if !out.status.success() {
            return None;
        }
        let text = String::from_utf8_lossy(&out.stdout).trim().to_string();
        (!text.is_empty()).then_some(text)
    })
}

/// Detect hardware once per app run by shelling out to the OS's own tools —
/// `nvidia-smi` for NVIDIA GPUs, `sysctl`/`/proc` for CPU/RAM. Best-effort:
/// any probe that isn't present just leaves its field empty.
pub(crate) fn hardware_info() -> HardwareInfo {
    static CACHE: std::sync::OnceLock<HardwareInfo> = std::sync::OnceLock::new();
    CACHE.get_or_init(probe_hardware).clone()
}

fn probe_hardware() -> HardwareInfo {
    let cores = std::thread::available_parallelism()
        .ok()
        .map(|n| n.get() as u32);
    let (cpu, mem_gb) = probe_cpu_mem();
    let gpu = probe_nvidia_gpus();
    let accelerator = if !gpu.is_empty() {
        Some("cuda".to_string())
    } else if std::env::consts::OS == "macos" && std::env::consts::ARCH == "aarch64" {
        Some("mps".to_string()) // Apple Silicon: Metal Performance Shaders
    } else {
        Some("cpu".to_string())
    };
    HardwareInfo {
        cpu,
        cores,
        mem_gb,
        gpu,
        accelerator,
    }
}

/// CPU brand + total RAM (GB). macOS via `sysctl`, Linux via `/proc`.
fn probe_cpu_mem() -> (Option<String>, Option<u32>) {
    if std::env::consts::OS == "macos" {
        let sysctl = |key: &str| {
            crate::runtime::quiet_command("sysctl")
                .args(["-n", key])
                .output()
                .ok()
                .filter(|o| o.status.success())
                .map(|o| String::from_utf8_lossy(&o.stdout).trim().to_string())
        };
        let cpu = sysctl("machdep.cpu.brand_string").filter(|s| !s.is_empty());
        let mem_gb = sysctl("hw.memsize")
            .and_then(|s| s.parse::<u64>().ok())
            .map(|b| (b / 1_073_741_824) as u32);
        (cpu, mem_gb)
    } else if std::env::consts::OS == "linux" {
        let cpu = std::fs::read_to_string("/proc/cpuinfo").ok().and_then(|t| {
            t.lines()
                .find(|l| l.starts_with("model name"))
                .and_then(|l| l.split(':').nth(1))
                .map(|s| s.trim().to_string())
        });
        let mem_gb = std::fs::read_to_string("/proc/meminfo").ok().and_then(|t| {
            t.lines()
                .find(|l| l.starts_with("MemTotal"))
                .and_then(|l| l.split_whitespace().nth(1))
                .and_then(|kb| kb.parse::<u64>().ok())
                .map(|kb| (kb / 1_048_576) as u32) // kB -> GB
        });
        (cpu, mem_gb)
    } else {
        (None, None)
    }
}

/// NVIDIA GPU model names via `nvidia-smi`; empty if the tool is absent.
fn probe_nvidia_gpus() -> Vec<String> {
    crate::runtime::quiet_command("nvidia-smi")
        .args(["--query-gpu=name", "--format=csv,noheader"])
        .output()
        .ok()
        .filter(|o| o.status.success())
        .map(|o| {
            String::from_utf8_lossy(&o.stdout)
                .lines()
                .map(|l| l.trim().to_string())
                .filter(|l| !l.is_empty())
                .collect()
        })
        .unwrap_or_default()
}

/// A short, deterministic content hash for lockfile addressing. DefaultHasher
/// uses fixed keys, so the same freeze maps to the same file across runs.
pub(crate) fn content_hash(text: &str) -> String {
    use std::hash::{Hash, Hasher};
    let mut h = std::collections::hash_map::DefaultHasher::new();
    text.hash(&mut h);
    format!("{:016x}", h.finish())
}

/// Write `freeze` to a content-addressed lockfile (once) and return its snapshot.
fn write_lockfile(root: &Path, freeze: &str) -> Result<PackageSnapshot, String> {
    let count = freeze.lines().filter(|l| !l.trim().is_empty()).count() as u32;
    let hash = content_hash(freeze);
    let dir = root.join(STORE_DIR).join(ENV_DIR);
    std::fs::create_dir_all(&dir).map_err(|e| e.to_string())?;
    let path = dir.join(format!("{hash}.txt"));
    if !path.exists() {
        std::fs::write(&path, freeze).map_err(|e| e.to_string())?;
    }
    Ok(PackageSnapshot { count, hash })
}

fn python_version(interpreter: &str) -> Option<String> {
    static CACHE: std::sync::OnceLock<Mutex<HashMap<String, Option<String>>>> =
        std::sync::OnceLock::new();
    cached_probe(CACHE.get_or_init(Mutex::default), interpreter, || {
        let out = crate::runtime::quiet_command(interpreter)
            .arg("--version")
            .output()
            .ok()?;
        let stdout = String::from_utf8_lossy(&out.stdout).trim().to_string();
        let text = if stdout.is_empty() {
            String::from_utf8_lossy(&out.stderr).trim().to_string()
        } else {
            stdout
        };
        Some(text.strip_prefix("Python ").unwrap_or(&text).to_string())
    })
}

enum RunInterpreter {
    Explicit(PathBuf),
    Missing,
}

fn first_token(segment: &str) -> String {
    let text = segment.trim_start();
    for quote in ['"', '\''] {
        if let Some(rest) = text.strip_prefix(quote) {
            if let Some(end) = rest.find(quote) {
                return rest[..end].to_string();
            }
        }
    }
    text.split_whitespace().next().unwrap_or("").to_string()
}

fn strip_env_assignment(text: &str) -> Option<&str> {
    let bytes = text.as_bytes();
    let mut index = 0;
    if bytes
        .first()
        .is_none_or(|byte| !(byte.is_ascii_alphabetic() || *byte == b'_'))
    {
        return None;
    }
    while index < bytes.len() && (bytes[index].is_ascii_alphanumeric() || bytes[index] == b'_') {
        index += 1;
    }
    if index >= bytes.len() || bytes[index] != b'=' {
        return None;
    }
    let mut end = index + 1;
    while end < bytes.len() && !bytes[end].is_ascii_whitespace() {
        end += 1;
    }
    (end < bytes.len()).then(|| text[end..].trim_start())
}

fn strip_segment_prefixes(segment: &str) -> String {
    let mut text = segment.trim();
    loop {
        if let Some(rest) = text.strip_prefix('&') {
            text = rest.trim_start();
            continue;
        }
        if let Some(rest) = strip_env_assignment(text) {
            text = rest;
            continue;
        }
        return text.trim().to_string();
    }
}

fn interpreter_from_command(command: &str, root: &Path) -> Option<RunInterpreter> {
    for segment in command
        .split('\n')
        .flat_map(|value| value.split("&&"))
        .flat_map(|value| value.split(';'))
        .flat_map(|value| value.split('|'))
    {
        let token = first_token(&strip_segment_prefixes(segment));
        let base = token.rsplit(['/', '\\']).next().unwrap_or(&token);
        let stem = base
            .strip_suffix(".exe")
            .or_else(|| base.strip_suffix(".EXE"))
            .unwrap_or(base);
        if (token.contains('/') || token.contains('\\')) && stem.starts_with("python") {
            let path = Path::new(&token);
            let resolved = if path.is_absolute() {
                path.to_path_buf()
            } else {
                root.join(path)
            };
            return Some(if resolved.is_file() {
                RunInterpreter::Explicit(resolved)
            } else {
                RunInterpreter::Missing
            });
        }
    }
    None
}

pub(crate) fn capture_env(
    app: &tauri::AppHandle,
    root: &Path,
    app_version: String,
    command: Option<&str>,
) -> EnvInfo {
    let interpreter = match command.and_then(|value| interpreter_from_command(value, root)) {
        Some(RunInterpreter::Explicit(path)) => Some(path.to_string_lossy().into_owned()),
        Some(RunInterpreter::Missing) => None,
        None => crate::kernel::python_bin(app).ok().map(|(path, _)| path),
    };
    let (python, packages) = match interpreter {
        Some(path) => (
            python_version(&path),
            pip_freeze(&path).and_then(|freeze| write_lockfile(root, &freeze).ok()),
        ),
        None => (None, None),
    };
    EnvInfo {
        python,
        platform: format!("{}-{}", std::env::consts::OS, std::env::consts::ARCH),
        app: app_version,
        packages,
        hardware: Some(hardware_info()),
    }
}

/// Normalize an artifact path (absolute or relative, from tool input) to a
/// workspace-relative `/`-separated key. Paths escaping the workspace are rejected.
fn normalize_rel(root: &Path, path: &str) -> Result<String, String> {
    let p = Path::new(path);
    let rel: PathBuf = if p.is_absolute() {
        let stripped = match (p.canonicalize(), root.canonicalize()) {
            // Prefer canonical forms (resolves /var vs /private/var on macOS)…
            (Ok(full), Ok(root_c)) => full.strip_prefix(&root_c).map(Path::to_path_buf),
            // …but the file may not exist yet — fall back to a lexical strip.
            _ => p.strip_prefix(root).map(Path::to_path_buf),
        };
        stripped.map_err(|_| "path is outside the workspace".to_string())?
    } else {
        p.to_path_buf()
    };
    if rel.as_os_str().is_empty() || rel.components().any(|c| !matches!(c, Component::Normal(_))) {
        return Err("path must stay inside the workspace".into());
    }
    Ok(rel
        .components()
        .map(|c| c.as_os_str().to_string_lossy().into_owned())
        .collect::<Vec<_>>()
        .join("/"))
}

fn store_file(root: &Path) -> PathBuf {
    root.join(STORE_DIR).join(STORE_FILE)
}

/// All records in the store. Unparseable lines are skipped, never fatal — the
/// store must survive a corrupt line without losing the rest of the history.
fn read_all(file: &Path) -> Vec<ProvenanceRecord> {
    let Ok(text) = std::fs::read_to_string(file) else {
        return Vec::new();
    };
    text.lines()
        .filter_map(|l| serde_json::from_str(l).ok())
        .collect()
}

fn cap_content(mut c: String) -> String {
    if c.len() > CONTENT_CAP {
        let mut end = CONTENT_CAP;
        while !c.is_char_boundary(end) {
            end -= 1;
        }
        c.truncate(end);
        c.push_str("\n… [truncated]");
    }
    c
}

/// Append one version record for `path`, assigning the next version number.
#[allow(clippy::too_many_arguments)]
pub fn append_record(
    root: &Path,
    path: &str,
    tool: &str,
    session_id: Option<String>,
    model: Option<String>,
    content: Option<String>,
    diff: Option<String>,
    log: Option<String>,
    env: Option<EnvInfo>,
    run_id: Option<String>,
) -> Result<ProvenanceRecord, String> {
    let rel = normalize_rel(root, path)?;
    let file = store_file(root);
    if let Some(dir) = file.parent() {
        std::fs::create_dir_all(dir).map_err(|e| format!("provenance dir failed: {e}"))?;
    }
    let version = read_all(&file)
        .iter()
        .filter(|r| r.path == rel)
        .map(|r| r.version)
        .max()
        .unwrap_or(0)
        + 1;
    let record = ProvenanceRecord {
        path: rel,
        version,
        ts: SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs(),
        tool: tool.to_string(),
        session_id,
        model,
        content: content.map(cap_content),
        diff: diff.map(cap_content),
        log,
        env,
        run_id,
    };
    let line = serde_json::to_string(&record).map_err(|e| e.to_string())?;
    use std::io::Write;
    let mut f = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&file)
        .map_err(|e| format!("provenance open failed: {e}"))?;
    writeln!(f, "{line}").map_err(|e| format!("provenance write failed: {e}"))?;
    Ok(record)
}

/// Append a `run`-produced version record for each of `paths` in ONE pass:
/// reads the store once to compute per-path next versions, then writes all
/// lines together. Used by runs.rs to link a run's outputs — a single read +
/// write instead of one full store re-read per output, and the caller holds the
/// same `ProvenanceState` lock as `record_provenance` so the two never race the
/// version-then-append on `provenance.jsonl`.
pub fn link_run_outputs(
    root: &Path,
    paths: &[String],
    session_id: Option<String>,
    model: Option<String>,
    log: Option<String>,
    env: Option<EnvInfo>,
    run_id: String,
) -> Result<(), String> {
    if paths.is_empty() {
        return Ok(());
    }
    let file = store_file(root);
    if let Some(dir) = file.parent() {
        std::fs::create_dir_all(dir).map_err(|e| format!("provenance dir failed: {e}"))?;
    }
    // Read once; compute the current max version per path.
    let mut max_ver: std::collections::HashMap<String, u32> = std::collections::HashMap::new();
    for r in read_all(&file) {
        let e = max_ver.entry(r.path).or_insert(0);
        *e = (*e).max(r.version);
    }
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs();
    let mut buf = String::new();
    for p in paths {
        let rel = normalize_rel(root, p)?;
        let v = max_ver.entry(rel.clone()).or_insert(0);
        *v += 1;
        let record = ProvenanceRecord {
            path: rel,
            version: *v,
            ts,
            tool: "run".to_string(),
            session_id: session_id.clone(),
            model: model.clone(),
            content: None,
            diff: None,
            log: log.clone(),
            env: env.clone(),
            run_id: Some(run_id.clone()),
        };
        buf.push_str(&serde_json::to_string(&record).map_err(|e| e.to_string())?);
        buf.push('\n');
    }
    use std::io::Write;
    let mut f = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&file)
        .map_err(|e| format!("provenance open failed: {e}"))?;
    f.write_all(buf.as_bytes())
        .map_err(|e| format!("provenance write failed: {e}"))?;
    Ok(())
}

/// All recorded versions of one artifact, oldest first.
pub fn versions_for(root: &Path, path: &str) -> Result<Vec<ProvenanceRecord>, String> {
    let rel = normalize_rel(root, path)?;
    let mut v: Vec<ProvenanceRecord> = read_all(&store_file(root))
        .into_iter()
        .filter(|r| r.path == rel)
        .collect();
    v.sort_by_key(|r| r.version);
    Ok(v)
}

/// `async`: fired on every agent write; the first call shells out to
/// `pip freeze` (seconds) and every call re-reads the whole store — none of
/// which may run on the UI thread.
#[tauri::command(async)]
#[allow(clippy::too_many_arguments)]
pub fn record_provenance(
    app: AppHandle,
    state: tauri::State<ProvenanceState>,
    path: String,
    tool: String,
    session_id: Option<String>,
    model: Option<String>,
    content: Option<String>,
    diff: Option<String>,
    log: Option<String>,
) -> Result<ProvenanceRecord, String> {
    let _guard = state.0.lock().map_err(|_| "provenance lock poisoned")?;
    let root = workspace_dir(&app)?;
    let env = capture_env(&app, &root, app.package_info().version.to_string(), None);
    // Writes are authored, not runs — no run_id here (runs.rs sets it for
    // files produced by executing code).
    let record = append_record(
        &root,
        &path,
        &tool,
        session_id,
        model,
        content,
        diff,
        log,
        Some(env),
        None,
    )?;
    drop(_guard);
    crate::git_snapshot::commit_best_effort(&root, &format!("Record {}", record.path));
    Ok(record)
}

/// `async`: reads the whole (unbounded) store off the UI thread.
#[tauri::command(async)]
pub fn list_provenance(app: AppHandle, path: String) -> Result<Vec<ProvenanceRecord>, String> {
    versions_for(&workspace_dir(&app)?, &path)
}

/// Read a content-addressed package lockfile (`.openscience/env/<hash>.txt`).
/// `hash` is validated to hex so it cannot escape the env directory.
#[tauri::command]
pub fn read_env_lockfile(app: AppHandle, hash: String) -> Result<String, String> {
    if hash.is_empty() || !hash.chars().all(|c| c.is_ascii_hexdigit()) {
        return Err("invalid lockfile id".into());
    }
    let path = workspace_dir(&app)?
        .join(STORE_DIR)
        .join(ENV_DIR)
        .join(format!("{hash}.txt"));
    std::fs::read_to_string(&path).map_err(|e| format!("lockfile unavailable: {e}"))
}

#[cfg(test)]
mod tests {
    use super::{append_record, cap_content, normalize_rel, versions_for, CONTENT_CAP};

    fn temp_root(tag: &str) -> std::path::PathBuf {
        let dir = std::env::temp_dir().join(format!("ai4s-prov-{tag}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).unwrap();
        dir
    }

    #[test]
    fn versions_increment_per_path_and_round_trip() {
        let root = temp_root("versions");
        let r1 = append_record(
            &root,
            "fig/plot.py",
            "write",
            Some("ses_1".into()),
            Some("m".into()),
            Some("print(1)".into()),
            None,
            None,
            None,
            None,
        )
        .unwrap();
        // A file produced by a run carries its run_id (link to the recipe).
        let r2 = append_record(
            &root,
            "fig/plot.py",
            "run",
            Some("ses_1".into()),
            None,
            None,
            None,
            None,
            None,
            Some("run_abc".into()),
        )
        .unwrap();
        // An edit records its diff for lineage (no full content).
        let e = append_record(
            &root,
            "fig/plot.py",
            "edit",
            None,
            None,
            None,
            Some("@@ -1 +1 @@\n-print(1)\n+print(2)".into()),
            None,
            None,
            None,
        )
        .unwrap();
        assert_eq!(e.version, 3);
        assert!(e.content.is_none());
        assert_eq!(e.diff.as_deref(), Some("@@ -1 +1 @@\n-print(1)\n+print(2)"));
        let other = append_record(
            &root,
            "report.md",
            "write",
            None,
            None,
            None,
            None,
            Some("wrote report.md".into()),
            Some(super::EnvInfo {
                python: Some("3.12.4".into()),
                platform: "macos-aarch64".into(),
                app: "0.1.0".into(),
                packages: Some(super::PackageSnapshot {
                    count: 2,
                    hash: "abc123".into(),
                }),
                hardware: None,
            }),
            None,
        )
        .unwrap();
        assert_eq!((r1.version, r2.version, other.version), (1, 2, 1));

        let v = versions_for(&root, "fig/plot.py").unwrap();
        assert_eq!(v.len(), 3);
        assert_eq!(v[0].content.as_deref(), Some("print(1)"));
        assert_eq!(v[0].run_id, None); // an authored write has no run
        assert_eq!(
            v[2].diff.as_deref(),
            Some("@@ -1 +1 @@\n-print(1)\n+print(2)")
        );
        assert_eq!(v[1].tool, "run");
        assert_eq!(v[1].run_id.as_deref(), Some("run_abc")); // round-trips
        assert_eq!(v[1].session_id.as_deref(), Some("ses_1"));
        assert!(v[1].ts > 0);
        // env round-trips (and its absence stays absent).
        assert!(v[0].env.is_none());
        let report = versions_for(&root, "report.md").unwrap();
        let env = report[0].env.as_ref().expect("env recorded");
        assert_eq!(env.python.as_deref(), Some("3.12.4"));
        assert_eq!(env.platform, "macos-aarch64");
        assert_eq!(env.app, "0.1.0");
        let pkgs = env.packages.as_ref().expect("packages recorded");
        assert_eq!((pkgs.count, pkgs.hash.as_str()), (2, "abc123"));

        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn lockfile_is_content_addressed_and_deduped() {
        use super::{content_hash, write_lockfile};
        let root = temp_root("lockfile");
        let freeze = "numpy==2.0.1\npandas==2.2.2\n\nscipy==1.14.0\n";
        let s1 = write_lockfile(&root, freeze).unwrap();
        // Blank lines are not counted as packages.
        assert_eq!(s1.count, 3);
        assert_eq!(s1.hash, content_hash(freeze)); // deterministic addressing
        let lock = root
            .join(".openscience/env")
            .join(format!("{}.txt", s1.hash));
        assert_eq!(std::fs::read_to_string(&lock).unwrap(), freeze);

        // Same environment -> same hash, no duplicate file rewrite.
        let s2 = write_lockfile(&root, freeze).unwrap();
        assert_eq!(s2.hash, s1.hash);
        // A different environment -> a different lockfile.
        let s3 = write_lockfile(&root, "numpy==2.0.1\n").unwrap();
        assert_ne!(s3.hash, s1.hash);
        assert_eq!(s3.count, 1);

        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn absolute_paths_normalize_and_escapes_are_rejected() {
        let root = temp_root("norm");
        // Absolute path under the workspace → same key as the relative form.
        let abs = root.join("a/b.txt");
        append_record(
            &root,
            abs.to_str().unwrap(),
            "write",
            None,
            None,
            None,
            None,
            None,
            None,
            None,
        )
        .unwrap();
        let v = versions_for(&root, "a/b.txt").unwrap();
        assert_eq!(v.len(), 1);
        assert_eq!(v[0].path, "a/b.txt");

        assert!(normalize_rel(&root, "../outside.txt").is_err());
        assert!(normalize_rel(&root, "/etc/hosts").is_err());
        assert!(normalize_rel(&root, "").is_err());

        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn corrupt_lines_are_skipped_and_content_is_capped() {
        let root = temp_root("corrupt");
        append_record(
            &root, "x.py", "write", None, None, None, None, None, None, None,
        )
        .unwrap();
        // A corrupt line must not lose the rest of the history.
        use std::io::Write;
        let file = root.join(".openscience/provenance.jsonl");
        let mut f = std::fs::OpenOptions::new()
            .append(true)
            .open(&file)
            .unwrap();
        writeln!(f, "not json").unwrap();
        append_record(
            &root, "x.py", "write", None, None, None, None, None, None, None,
        )
        .unwrap();
        let v = versions_for(&root, "x.py").unwrap();
        assert_eq!(v.iter().map(|r| r.version).collect::<Vec<_>>(), vec![1, 2]);

        let big = "é".repeat(CONTENT_CAP); // multi-byte: cap must respect char boundaries
        let capped = cap_content(big);
        assert!(capped.len() <= CONTENT_CAP + 20);
        assert!(capped.ends_with("[truncated]"));

        let _ = std::fs::remove_dir_all(root);
    }

    #[test]
    fn identifies_the_exact_project_python_interpreter() {
        use super::{interpreter_from_command, RunInterpreter};
        let root = temp_root("interpreter");
        let bin = root.join(".venv/bin");
        std::fs::create_dir_all(&bin).unwrap();
        let python = bin.join("python");
        std::fs::write(&python, "#!/bin/sh\n").unwrap();

        let explicit = |command: &str| match interpreter_from_command(command, &root) {
            Some(RunInterpreter::Explicit(path)) => path,
            _ => panic!("expected explicit interpreter for {command}"),
        };
        assert_eq!(explicit(".venv/bin/python model.py"), python);
        assert_eq!(explicit("ENV=prod .venv/bin/python model.py"), python);
        assert_eq!(explicit("& \".venv/bin/python\" model.py"), python);
        assert!(matches!(
            interpreter_from_command("python model.py", &root),
            None
        ));
        assert!(matches!(
            interpreter_from_command(".venv/bin/python-missing model.py", &root),
            Some(RunInterpreter::Missing)
        ));

        let _ = std::fs::remove_dir_all(root);
    }
}
