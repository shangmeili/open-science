//! Privacy-preserving diagnostics for product-owner acceptance and support.
//!
//! Raw frontend diagnostics can contain local paths, model output, command
//! fragments, or provider error messages. They must never be copied into an
//! export. This module reports only fixed product/platform fields and aggregate
//! event counts from a bounded tail of `debug.log`.

use serde::Serialize;
use std::fs::{self, File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::Path;
use std::time::{SystemTime, UNIX_EPOCH};
use tauri::{AppHandle, Manager, State};

const REPORT_SCHEMA: &str = "1.0.0";
const MAX_LOG_SAMPLE_BYTES: u64 = 1024 * 1024;

#[derive(Debug, Default, Serialize)]
#[serde(rename_all = "camelCase")]
struct DiagnosticLogSummary {
    status: &'static str,
    truncated: bool,
    sampled_bytes: u64,
    entries: usize,
    error_entries: usize,
    turn_entries: usize,
    connection_entries: usize,
    runtime_entries: usize,
    event_entries: usize,
    raw_content_included: bool,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
struct SupportReport<'a> {
    schema_version: &'static str,
    product: &'static str,
    app_version: &'a str,
    generated_at_unix_ms: u128,
    platform: &'static str,
    architecture: &'static str,
    local_runtime_managed_by_app: bool,
    local_runtime_process_tracked: bool,
    diagnostic_log: DiagnosticLogSummary,
    exclusions: [&'static str; 6],
}

fn unix_millis() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or(0)
}

fn summarize_log_text(text: &str, truncated: bool, sampled_bytes: u64) -> DiagnosticLogSummary {
    let mut summary = DiagnosticLogSummary {
        status: "summarized",
        truncated,
        sampled_bytes,
        raw_content_included: false,
        ..DiagnosticLogSummary::default()
    };
    for line in text.lines().filter(|line| !line.trim().is_empty()) {
        summary.entries += 1;
        let line = line.to_ascii_lowercase();
        if line.contains("failed") || line.contains("error") {
            summary.error_entries += 1;
        }
        if line.contains("turn ") {
            summary.turn_entries += 1;
        }
        if line.contains("connect") {
            summary.connection_entries += 1;
        }
        if line.contains("runtime") || line.contains("bootstrap") {
            summary.runtime_entries += 1;
        }
        if line.contains("event ") {
            summary.event_entries += 1;
        }
    }
    summary
}

fn summarize_log_file(path: &Path) -> DiagnosticLogSummary {
    let Ok(metadata) = fs::symlink_metadata(path) else {
        return DiagnosticLogSummary {
            status: "missing",
            ..DiagnosticLogSummary::default()
        };
    };
    if !metadata.file_type().is_file() || metadata.file_type().is_symlink() {
        return DiagnosticLogSummary {
            status: "unavailable",
            ..DiagnosticLogSummary::default()
        };
    }
    let total_bytes = metadata.len();
    let sampled_bytes = total_bytes.min(MAX_LOG_SAMPLE_BYTES);
    let truncated = sampled_bytes < total_bytes;
    let Ok(mut file) = File::open(path) else {
        return DiagnosticLogSummary {
            status: "unavailable",
            ..DiagnosticLogSummary::default()
        };
    };
    if truncated && file.seek(SeekFrom::End(-(sampled_bytes as i64))).is_err() {
        return DiagnosticLogSummary {
            status: "unavailable",
            ..DiagnosticLogSummary::default()
        };
    }
    let mut bytes = Vec::with_capacity(sampled_bytes as usize);
    if file.take(sampled_bytes).read_to_end(&mut bytes).is_err() {
        return DiagnosticLogSummary {
            status: "unavailable",
            ..DiagnosticLogSummary::default()
        };
    }
    let text = String::from_utf8_lossy(&bytes);
    // A tail sample can begin in the middle of a line. Drop that fragment so
    // one event is never counted twice across reports.
    let sample = if truncated {
        text.split_once('\n').map(|(_, rest)| rest).unwrap_or("")
    } else {
        text.as_ref()
    };
    summarize_log_text(sample, truncated, bytes.len() as u64)
}

fn build_report_json(
    app_version: &str,
    local_runtime_process_tracked: bool,
    diagnostic_log: DiagnosticLogSummary,
    generated_at_unix_ms: u128,
) -> Result<String, String> {
    let report = SupportReport {
        schema_version: REPORT_SCHEMA,
        product: "AI4HEOR",
        app_version,
        generated_at_unix_ms,
        platform: std::env::consts::OS,
        architecture: std::env::consts::ARCH,
        local_runtime_managed_by_app: true,
        local_runtime_process_tracked,
        diagnostic_log,
        exclusions: [
            "provider_credentials",
            "authentication_files",
            "workspace_paths",
            "workspace_files",
            "conversation_content",
            "raw_diagnostic_log",
        ],
    };
    serde_json::to_string_pretty(&report)
        .map(|json| format!("{json}\n"))
        .map_err(|error| error.to_string())
}

/// Export a deliberately narrow report through a native Save dialog. The
/// report contains no raw log lines, credentials, project paths, research data,
/// messages, endpoint URLs, provider names, model IDs, or command output.
#[tauri::command(async)]
pub async fn export_support_report(
    app: AppHandle,
    state: State<'_, crate::runtime::RuntimeState>,
) -> Result<Option<String>, String> {
    use tauri_plugin_dialog::DialogExt;

    let app_version = app.package_info().version.to_string();
    let log_path = app
        .path()
        .app_data_dir()
        .map_err(|error| error.to_string())?
        .join("debug.log");
    let report = build_report_json(
        &app_version,
        crate::runtime::runtime_process_tracked(state.inner()),
        summarize_log_file(&log_path),
        unix_millis(),
    )?;
    let filename = format!("AI4HEOR-{app_version}-diagnostic-report.json");
    let Some(choice) = app
        .dialog()
        .file()
        .set_file_name(&filename)
        .blocking_save_file()
    else {
        return Ok(None);
    };
    let path = choice.into_path().map_err(|error| error.to_string())?;
    let mut options = OpenOptions::new();
    options.write(true).create(true).truncate(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600);
    }
    let mut file = options
        .open(&path)
        .map_err(|error| format!("could not create the diagnostic report: {error}"))?;
    file.write_all(report.as_bytes())
        .and_then(|_| file.flush())
        .map_err(|error| format!("could not write the diagnostic report: {error}"))?;
    #[cfg(unix)]
    fs::set_permissions(&path, std::os::unix::fs::PermissionsExt::from_mode(0o600))
        .map_err(|error| format!("could not protect the diagnostic report: {error}"))?;
    Ok(Some(path.to_string_lossy().to_string()))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn report_exports_counts_but_never_raw_diagnostic_content() {
        let raw = concat!(
            "100 bootstrap: runtime at http://127.0.0.1:4096\n",
            "101 turn FAILED: provider rejected sk-test-secret\n",
            "102 provenance FAILED for /Users/Alice/private-study.csv\n",
            "103 event ← session.updated private-session-id\n",
        );
        let summary = summarize_log_text(raw, false, raw.len() as u64);
        let report = build_report_json("0.1.52", true, summary, 123).unwrap();
        let parsed: serde_json::Value = serde_json::from_str(&report).unwrap();

        assert_eq!(parsed["product"], "AI4HEOR");
        assert_eq!(parsed["appVersion"], "0.1.52");
        assert_eq!(parsed["localRuntimeProcessTracked"], true);
        assert_eq!(parsed["diagnosticLog"]["entries"], 4);
        assert_eq!(parsed["diagnosticLog"]["errorEntries"], 2);
        assert_eq!(parsed["diagnosticLog"]["rawContentIncluded"], false);
        for forbidden in [
            "sk-test-secret",
            "/Users/Alice",
            "private-study.csv",
            "private-session-id",
            "127.0.0.1",
        ] {
            assert!(!report.contains(forbidden));
        }
    }

    #[test]
    fn missing_and_non_regular_logs_are_never_followed_or_exported() {
        let root = std::env::temp_dir().join(format!(
            "ai4heor-support-report-{}-{}",
            std::process::id(),
            unix_millis()
        ));
        fs::create_dir_all(&root).unwrap();
        let missing = summarize_log_file(&root.join("missing.log"));
        assert_eq!(missing.status, "missing");

        let directory = root.join("debug.log");
        fs::create_dir_all(&directory).unwrap();
        let unavailable = summarize_log_file(&directory);
        assert_eq!(unavailable.status, "unavailable");
        fs::remove_dir_all(root).unwrap();
    }
}
